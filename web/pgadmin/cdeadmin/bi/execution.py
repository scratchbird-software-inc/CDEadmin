##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Run saved questions through the existing Data Studio and result services.

Nothing here executes SQL itself or renders rows.  A question is compiled by
``BIService`` (bound parameters only), submitted with
``DataStudioService.execute``/``poll``, admitted by ``ResultService`` as a
typed descriptor, narrowed by the question's result policy
(``ResultService.restrict``) and paged/exported by ``ResultService``.

Sharing never widens run-time data access: a shared question always runs
with the RUNNER's connection (the ``context``/``endpoint`` of the runner's
own workspace) and the RUNNER's ``security_context`` (so semantic row
policies see the runner's claims), never the owner's.  A runner below
``edit`` on a raw-SQL question never receives its SQL text.

The cache keeps the admitted ``result_id`` per ``(question, revision,
parameters, principal, endpoint)``.  The rows stay in ``ResultService``'s
bounded store; a cache hit re-renders from it, and eviction or invalidation
releases the descriptor.
"""

from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
from dataclasses import dataclass, field

from pgadmin.cdeadmin.results.models import ResultRegistryError
from pgadmin.cdeadmin.semantic_models.models import SemanticModelError

from .models import BIError

DEFAULT_MAX_ENTRIES = 64
PAGE_LEASE_SECONDS = 600
MAX_POLLS = 400


def _digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(',', ':'), default=repr,
        ensure_ascii=False).encode('utf-8')).hexdigest()


@dataclass
class _Entry:
    key: str
    result_id: str
    user_id: int
    endpoint_id: str
    question_id: str | None
    revision: int | None
    policy: dict
    columns: list | None
    sql: str
    plan: str
    created: float
    reuse_until: float
    lease_until: float
    cacheable: bool
    reproducibility: dict | None = None
    hits: int = 0
    parameter_count: int = 0
    meta: dict = field(default_factory=dict)
    principal: str | None = None


class BIExecutor:
    """Execute, cache, page and export saved questions."""

    def __init__(self, bi_service, studio_service, result_service, *,
                 clock=time.monotonic, sleeper=time.sleep,
                 max_entries=DEFAULT_MAX_ENTRIES, poll_interval=0.05,
                 max_polls=MAX_POLLS):
        self.bi = bi_service
        self.studio = studio_service
        self.results = result_service
        self.clock = clock
        self.sleeper = sleeper
        self.max_entries = max_entries
        self.poll_interval = poll_interval
        self.max_polls = max_polls
        self._by_key = {}
        self._by_result = {}
        self._lock = threading.RLock()
        self.stats = {'hits': 0, 'misses': 0, 'evictions': 0,
                      'invalidations': 0}
        # a shared question changes for every principal that ran it
        bi_service.on_question_change(
            lambda _user_id, endpoint_id, question_id: self.invalidate(
                endpoint_id=endpoint_id, question_id=question_id))

    # execution -----------------------------------------------------------
    def run(self, *, provider, context, endpoint, user_id,
            question_id=None, revision=None, definition=None,
            parameters=None, extra_filters=(), page_size=None,
            bypass_cache=False, ttl_seconds=None, security_context=None,
            principal=None):
        """Run a question.

        ``principal`` names a non-interactive principal context (signed
        embedding, ``embed:<id>:<claims digest>``).  It is part of the cache
        key together with the digest of the security context, and the result
        can later be paged or exported only by the same principal; an
        interactive run (``principal=None``) never sees such an entry and the
        other way round.
        """
        endpoint_id = context.endpoint_id
        question, resolved_revision, owner_id, redact = self._resolve(
            user_id, endpoint_id, question_id, revision, definition)
        policy = question['result_policy']
        try:
            compiled = self.bi.compile_definition(
                provider, user_id, endpoint_id, question,
                parameters=parameters, bind=True,
                extra_filters=list(extra_filters or ()),
                security_context=security_context or {
                    'claims': {'user_id': user_id}},
                owner_id=owner_id)
        except BIError:
            raise
        except SemanticModelError as exc:
            raise BIError(str(exc)) from None
        plan = _digest([compiled['source'], compiled['parameters']])
        key = _digest([
            question_id or ('adhoc:' + _digest(question)),
            resolved_revision, _digest([parameters or {},
                                        list(extra_filters or ())]),
            plan, user_id, endpoint_id] + (
            [principal, _digest(security_context)]
            if principal is not None else []))
        ttl = policy['cache_ttl_seconds']
        if ttl_seconds is not None:
            if isinstance(ttl_seconds, bool) or not isinstance(
                    ttl_seconds, int) or ttl_seconds < 0:
                raise BIError('cache ttl_seconds must be a non-negative '
                              'integer')
            ttl = min(ttl, ttl_seconds)
        size = page_size if page_size is not None else policy['page_size']
        if isinstance(size, bool) or not isinstance(size, int) or not (
                1 <= size <= 500):
            raise BIError('page_size must be an integer from 1 to 500')
        now = self.clock()
        with self._lock:
            self._sweep(now)
            entry = self._by_key.get(key)
            if entry is not None and not bypass_cache and ttl > 0 and (
                    now < entry.reuse_until) and self._alive(entry):
                entry.hits += 1
                self.stats['hits'] += 1
                return self._response(entry, compiled, size, None, hit=True,
                                      now=now, redact=redact)
        self.stats['misses'] += 1
        result_id = self._execute(
            provider, context, endpoint, compiled, policy, redact)
        entry = _Entry(
            key=key, result_id=result_id, user_id=user_id,
            endpoint_id=endpoint_id, question_id=question_id,
            revision=resolved_revision, policy=copy.deepcopy(policy),
            columns=copy.deepcopy(compiled.get('output_columns')),
            sql=compiled['source'], plan=plan, created=now,
            reuse_until=now + ttl if ttl > 0 else now,
            lease_until=now + max(ttl, PAGE_LEASE_SECONDS),
            cacheable=ttl > 0,
            reproducibility=copy.deepcopy(compiled.get('reproducibility')),
            parameter_count=len(compiled['parameters']),
            principal=principal)
        with self._lock:
            previous = self._by_key.get(key)
            if previous is not None and previous.result_id != result_id:
                self._drop(previous)
            self._by_result[result_id] = entry
            if entry.cacheable:
                self._by_key[key] = entry
            while len(self._by_result) > self.max_entries:
                oldest = min(self._by_result.values(),
                             key=lambda item: item.created)
                self.stats['evictions'] += 1
                self._drop(oldest)
        return self._response(entry, compiled, size, None, hit=False,
                              now=now, redact=redact)

    def _resolve(self, user_id, endpoint_id, question_id, revision,
                 definition):
        """``(question, revision, owner_id, redact_sql)`` for the RUNNER.

        Access is re-checked on every run (before any cache lookup), so a
        revoked viewer cannot be served from the cache.
        """
        from .models import validate_question
        if question_id is None:
            return validate_question(definition), None, None, False
        stored = self.bi.stored_for_run(user_id, endpoint_id, question_id,
                                        revision)
        if stored['status'] != 'active':
            # archiving retires the question, pinned revisions included
            raise BIError('archived saved questions do not run')
        return (self._normalized(stored['definition']), stored['revision'],
                stored['owner_id'], stored['redact_sql'])

    @staticmethod
    def _normalized(definition):
        """Fill policy defaults for questions stored before they existed."""
        from .models import validate_result_policy
        item = copy.deepcopy(definition)
        item['result_policy'] = validate_result_policy(
            item.get('result_policy'))
        return item

    def _execute(self, provider, context, endpoint, compiled, policy,
                 hide_sql=False):
        language = compiled.get('language_profile')
        if not language:
            raise BIError('provider did not name a language profile')
        redact = list(policy['redact_columns'])
        session_id = None
        try:
            opened = self.studio.open_session(context, endpoint, language)
            session_id = opened['provider_session']['session_id']
            submitted = self.studio.execute(
                context, session_id, compiled['source'],
                parameters=compiled['parameters'],
                output_policy={'redact_keys': redact})
            occurrence_id = submitted['occurrence_id']
            polled = self._poll(context, occurrence_id)
            result = polled.get('result')
            if result is None:
                raise BIError('provider completed without a result')
            renderer = provider.select_renderer(copy.deepcopy(result))
            descriptor = self.studio.admit_result(
                context, occurrence_id, renderer.get('capability_ids', ()))
            self.results.restrict(
                descriptor['result_id'], endpoint_id=context.endpoint_id,
                redact_keys=redact,
                export_enabled=policy['export']['enabled'],
                export_formats=policy['export']['formats'])
            return descriptor['result_id']
        except BIError:
            raise
        except Exception as exc:  # native messages may carry SQL or paths
            if hide_sql:  # the caller may not read the statement text
                raise BIError('question execution failed') from None
            raise BIError(self._failure(exc)) from None
        finally:
            if session_id is not None:
                try:
                    self.studio.close_session(context, session_id)
                except Exception:
                    pass

    @staticmethod
    def _failure(exc):
        try:
            from pgadmin.cdeadmin.sdk.relational import RelationalClientError
        except Exception:  # pragma: no cover
            RelationalClientError = ()
        if isinstance(exc, (RelationalClientError, ResultRegistryError)):
            return f'question execution failed: {exc}'
        return f'question execution failed ({type(exc).__name__})'

    def _poll(self, context, occurrence_id):
        for _ in range(self.max_polls):
            polled = self.studio.poll(context, occurrence_id)
            if polled['operation']['terminal']:
                return polled
            self.sleeper(self.poll_interval)
        try:
            self.studio.request_cancel(context, occurrence_id)
        except Exception:
            pass
        raise BIError('question execution timed out and cancellation was '
                      'requested')

    # response / paging / export -------------------------------------------
    def _response(self, entry, compiled, size, cursor, *, hit, now,
                  redact=False):
        try:
            page = self.results.render(
                entry.result_id, page_size=size, cursor=cursor,
                endpoint_id=entry.endpoint_id)
            descriptor = self.results.descriptor(
                entry.result_id, endpoint_id=entry.endpoint_id)
        except ResultRegistryError as exc:
            raise BIError(f'result page is unavailable: {exc}') from None
        export = entry.policy['export']
        return {
            'question_id': entry.question_id, 'revision': entry.revision,
            'kind': compiled.get('kind'),
            'result': descriptor,
            'columns': entry.columns,
            'page': page,
            'sql': None if redact else entry.sql,
            'sql_redacted': redact,
            'bound_parameter_count': entry.parameter_count,
            'cache': {
                'hit': hit, 'cacheable': entry.cacheable,
                'key': entry.key[:16], 'hits': entry.hits,
                'age_seconds': round(max(0.0, now - entry.created), 3),
                'expires_in_seconds': round(max(
                    0.0, entry.reuse_until - now), 3),
            },
            'export': {
                'enabled': export['enabled'],
                'formats': list(export['formats']) if export['enabled']
                else [],
            },
            'redacted_columns': list(entry.policy['redact_columns']),
            'reproducibility': copy.deepcopy(entry.reproducibility),
        }

    def page(self, user_id, endpoint_id, result_id, cursor=None,
             page_size=None, principal=None):
        entry = self._owned(user_id, endpoint_id, result_id, principal)
        size = page_size if page_size is not None else (
            entry.policy['page_size'])
        if isinstance(size, bool) or not isinstance(size, int) or size < 1:
            raise BIError('page_size must be a positive integer')
        try:
            return self.results.render(
                result_id, page_size=size, cursor=cursor,
                endpoint_id=endpoint_id)
        except ResultRegistryError as exc:
            raise BIError(f'result page is unavailable: {exc}') from None

    def export(self, user_id, endpoint_id, result_id, export_format,
               principal=None):
        entry = self._owned(user_id, endpoint_id, result_id, principal)
        export = entry.policy['export']
        if not export['enabled']:
            raise BIError('export is not enabled by this question\'s '
                          'result policy')
        if export_format not in export['formats']:
            raise BIError('export format is not allowed by this question\'s '
                          'result policy')
        try:
            return self.results.export(result_id, export_format,
                                       endpoint_id=endpoint_id)
        except ResultRegistryError as exc:
            raise BIError(f'export is unavailable: {exc}') from None

    def entry_info(self, result_id):
        """``(question_id, principal)`` of a held result, else ``None``."""
        with self._lock:
            entry = self._by_result.get(result_id)
        return None if entry is None else (entry.question_id,
                                           entry.principal)

    def _owned(self, user_id, endpoint_id, result_id, principal=None):
        with self._lock:
            self._sweep(self.clock())
            entry = self._by_result.get(result_id)
        if entry is None or entry.user_id != user_id or (
                entry.endpoint_id != endpoint_id) or (
                entry.principal != principal):
            raise BIError('result is unavailable')
        if entry.question_id is not None and self.bi.access.level(
                user_id, 'question', endpoint_id,
                entry.question_id) is None:
            # access was revoked after the run: the page lease ends with it
            raise BIError('result is unavailable')
        return entry

    # cache management -----------------------------------------------------
    def invalidate(self, *, user_id=None, endpoint_id=None, question_id=None,
                   result_id=None):
        """Release every entry matching all supplied filters."""
        if user_id is None and endpoint_id is None and (
                question_id is None and result_id is None):
            raise BIError('invalidation needs at least one scope')
        released = 0
        with self._lock:
            for entry in list(self._by_result.values()):
                if (user_id is not None and entry.user_id != user_id) or (
                        endpoint_id is not None and
                        entry.endpoint_id != endpoint_id) or (
                        question_id is not None and
                        entry.question_id != question_id) or (
                        result_id is not None and
                        entry.result_id != result_id):
                    continue
                self._drop(entry)
                released += 1
            self.stats['invalidations'] += released
        return released

    def cache_info(self, user_id, endpoint_id):
        now = self.clock()
        with self._lock:
            self._sweep(now)
            return [{
                'result_id': e.result_id, 'question_id': e.question_id,
                'revision': e.revision, 'cacheable': e.cacheable,
                'hits': e.hits,
                'expires_in_seconds': round(max(0.0, e.reuse_until - now), 3),
            } for e in self._by_result.values()
                if e.user_id == user_id and e.endpoint_id == endpoint_id
                and e.principal is None]

    def _alive(self, entry):
        try:
            self.results.descriptor(entry.result_id,
                                    endpoint_id=entry.endpoint_id)
            return True
        except ResultRegistryError:
            self._drop(entry)
            return False

    def _sweep(self, now):
        for entry in list(self._by_result.values()):
            if now >= entry.lease_until:
                self._drop(entry)

    def _drop(self, entry):
        self._by_result.pop(entry.result_id, None)
        if self._by_key.get(entry.key) is entry:
            del self._by_key[entry.key]
        try:
            self.results.release(entry.result_id,
                                 endpoint_id=entry.endpoint_id)
        except ResultRegistryError:
            pass

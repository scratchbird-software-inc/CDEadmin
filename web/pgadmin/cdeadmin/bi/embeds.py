##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Signed embedding of BI dashboards and questions.

See ``docs/en_US/bi_embedding.rst`` (design, threat model, residual risks).

Two halves share this module:

* The *management* actions (``bi_embed_*``) are ordinary authenticated BI
  actions.  They go through ``BIAccess`` (``manage`` on the resource), and
  only the embed owner can change, enable, rotate or revoke an embed.
* The *runtime* (``authenticate`` and the ``view``/``run_*``/``page``/
  ``export``/``drill`` methods) is called by the unauthenticated blueprint
  (``embed_public.py``) with nothing but a token.  It is deny by default:
  every refusal raises ``EmbedDenied`` and the blueprint turns all of them
  into the same 404.

An embedded run executes with the owner's DELEGATED credentials (the report
scheduler's envelope machinery, never stored in the token or sent to a
browser), under a distinct ``embedding`` principal context: the semantic
``security_context`` carries only the token's signed claims, the executor
cache key and result ownership include the principal, and the row policies
therefore see the embedding site's claims and nothing of the owner's.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

from pgadmin.cdeadmin.report_scheduler.crypto import WorkerKeyError
from pgadmin.cdeadmin.report_scheduler.models import (
    ReportSchedulerAccessError, ReportSchedulerConflict,
    ReportSchedulerError,
)

from . import embed_tokens as tokens
from .access import BIPermissionDenied
from .dashboard_models import resolve_drill, resolve_filters
from .embed_models import (
    claim_requirements, frame_ancestors, parameter_modes,
    resource_parameters, validate_embed,
)
from .embed_tokens import EmbedTokenError
from .models import BIError

APP_EXTENSION_KEY = 'cdeadmin_bi_embed_service'
KEY_SCHEMA = 'cdeadmin.bi-embed-key.v1'
MEDIA_TYPES = {
    'csv': 'text/csv', 'json': 'application/json',
    'jsonl': 'application/x-ndjson',
    'xlsx': ('application/vnd.openxmlformats-officedocument.'
             'spreadsheetml.sheet'),
    'svg': 'image/svg+xml', 'pdf': 'application/pdf',
}
DEFAULTS = {
    'enabled': False,
    'allow_raw_sql': False,
    'allow_downloads': False,
    'max_token_lifetime': 3600,
    'clock_skew': 15,
    'max_page_size': 200,
    'max_rows': 5000,
    'max_embeds_per_user': 25,
    'ip_rate': (120, 2.0),        # burst, tokens per second
    'embed_rate': (300, 10.0),
    'preview_seconds': 120,
    'mint_max_seconds': 3600,
    'served_keep': 4096,
}
ACTIONS = frozenset((
    'bi_embed_catalog', 'bi_embed_list', 'bi_embed_get', 'bi_embed_create',
    'bi_embed_update', 'bi_embed_enable', 'bi_embed_disable',
    'bi_embed_rotate', 'bi_embed_retire_key', 'bi_embed_revoke',
    'bi_embed_delete', 'bi_embed_mint', 'bi_embed_preview',
    'bi_embed_check_token', 'bi_embed_stats',
))


class EmbedDenied(Exception):
    """The caller gets the uniform 404; ``code`` is for logs and tests."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


class EmbedInvalid(Exception):
    """An authenticated caller sent a request outside the embed's rules."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


class EmbedRateLimited(Exception):
    def __init__(self, retry_after):
        super().__init__('rate limited')
        self.retry_after = max(1, int(retry_after + 0.999))


class TokenBuckets:
    """In-process token buckets, bounded and least-recently-used evicted.

    The state is per worker process; behind several workers the effective
    limit is the configured one times the number of workers.
    """

    def __init__(self, burst, per_second, clock=time.monotonic, keep=10000):
        self.burst, self.per_second = float(burst), float(per_second)
        self.clock, self.keep = clock, keep
        self._buckets = OrderedDict()
        self._lock = threading.Lock()

    def take(self, key):
        """``(allowed, seconds_until_a_token)``."""
        now = self.clock()
        with self._lock:
            level, stamp = self._buckets.pop(key, (self.burst, now))
            level = min(self.burst, level + (now - stamp) * self.per_second)
            allowed = level >= 1.0
            if allowed:
                level -= 1.0
            self._buckets[key] = (level, now)
            while len(self._buckets) > self.keep:
                self._buckets.popitem(last=False)
        wait = 0.0 if allowed else (1.0 - level) / self.per_second
        return allowed, wait


class EmbedSession:
    """What a verified token grants for one request."""

    def __init__(self, row, definition, checked, kid):
        self.row, self.definition, self.kid = row, definition, kid
        self.embed_id = row.id
        self.owner_id, self.endpoint_id = row.user_id, row.endpoint_id
        self.resource_type, self.resource_id = (row.resource_type,
                                                row.resource_id)
        self.revision = row.resource_revision
        self.params, self.exp = checked['params'], checked['exp']
        self.jti, self.preview = checked['jti'], checked['prv']
        self.claims = checked['claims']
        self.principal = 'embed:%s:%s' % (
            row.id, tokens.claims_digest(self.claims)[:32])
        self.security_context = {'claims': {
            **self.claims, 'principal': 'embedding', 'embed_id': row.id}}

    @property
    def frame_ancestors(self):
        value = frame_ancestors(self.definition)
        if self.preview:  # a server-minted preview, framed by the BI UI
            return "'self'" if value == "'none'" else value + " 'self'"
        return value


def _naive(moment):
    return moment.astimezone(timezone.utc).replace(tzinfo=None) if (
        moment.tzinfo) else moment


def _iso(moment):
    return None if moment is None else moment.replace(
        tzinfo=timezone.utc).isoformat()


class BIEmbedService:
    ACTIONS = ACTIONS

    def __init__(self, bi, repository, *, executor=None, dashboards=None,
                 scheduler=None, key_ring=None, config=None, clock=None,
                 monotonic=time.monotonic):
        self.bi = bi
        self.repository = repository
        self.executor = executor if executor is not None else getattr(
            bi, 'executor', None)
        self.dashboards = dashboards if dashboards is not None else getattr(
            bi, 'dashboards', None)
        self.scheduler = scheduler
        self.key_ring = key_ring if key_ring is not None else getattr(
            scheduler, 'key_ring', None)
        self.config = {**DEFAULTS, **(config or {})}
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        ip, per = self.config['ip_rate']
        self._ip = TokenBuckets(ip, per, monotonic)
        burst, per = self.config['embed_rate']
        self._embed = TokenBuckets(burst, per, monotonic)
        self._served = OrderedDict()
        self._lock = threading.Lock()
        bi.access.on_purge(self._resource_deleted)

    # ------------------------------------------------------------------
    # small helpers
    # ------------------------------------------------------------------
    def _now(self):
        return _naive(self.clock())

    def _epoch(self):
        return int(self.clock().timestamp())

    @property
    def caps(self):
        return {'max_token_lifetime': int(self.config['max_token_lifetime']),
                'max_page_size': int(self.config['max_page_size']),
                'max_rows': int(self.config['max_rows'])}

    @property
    def available(self):
        return bool(self.config['enabled'] and self.scheduler is not None
                    and self.key_ring is not None and self.key_ring.available
                    and self.executor is not None)

    def _require_available(self):
        if not self.available:
            raise BIError('signed embedding is not enabled on this server')

    def _record(self, actor_id, action, row, detail=None):
        self.bi.access.record(
            actor_id, action, row.endpoint_id, row.resource_type,
            row.resource_id, {'embed_id': row.id, **(detail or {})})

    # ------------------------------------------------------------------
    # secrets
    # ------------------------------------------------------------------
    @staticmethod
    def _scope(embed_id, kid):
        return {'schema': KEY_SCHEMA, 'embed_id': embed_id, 'kid': kid}

    def _new_secret(self, row):
        """Install a fresh signing secret; the text is returned ONCE."""
        secret = secrets.token_urlsafe(32)
        kid = 'k' + secrets.token_hex(4)
        envelope = self.key_ring.encrypt(secret.encode('utf-8'),
                                         self._scope(row.id, kid))
        self.repository.install_key(
            row.id, kid=kid, key_id=self.key_ring.active_key_id,
            encrypted_value=envelope, now=self._now())
        return {'kid': kid, 'secret': secret, 'algorithm': tokens.ALGORITHM}

    def _secrets(self, row):
        """``{kid: secret text}`` of the keys that verify; fail closed."""
        found = {}
        if self.key_ring is None or not self.key_ring.available:
            return found
        for key in self.repository.keys(row.id):
            try:
                found[key.kid] = self.key_ring.decrypt(
                    key.encrypted_value,
                    self._scope(row.id, key.kid)).decode('utf-8')
            except (WorkerKeyError, UnicodeDecodeError):
                continue
        return found

    def _current_secret(self, row):
        for key in self.repository.keys(row.id):
            if key.slot == 'current':
                secret = self._secrets(row).get(key.kid)
                if secret is not None:
                    return key.kid, secret
        raise BIError('embed has no signing key')

    def rotate_encryption(self):
        """Re-encrypt every stored embed secret under the active ring key."""
        if self.key_ring is None or not self.key_ring.available:
            raise BIError('worker key authority is not configured')
        rotated = 0
        for key in self.repository.all_keys():
            if key.key_id == self.key_ring.active_key_id:
                continue
            scope = self._scope(key.embed_id, key.kid)
            key.encrypted_value = self.key_ring.rotate(key.encrypted_value,
                                                       scope)
            key.key_id = self.key_ring.active_key_id
            rotated += 1
        self.repository.save_keys()
        return {'rotated': rotated,
                'active_key_id': self.key_ring.active_key_id}

    # ------------------------------------------------------------------
    # presentation
    # ------------------------------------------------------------------
    def _present(self, row, viewer_id, frame_url=None):
        definition = json.loads(row.definition)
        owner = row.user_id == viewer_id
        delegation = (self.scheduler.delegation_for(row.id)
                      if (owner and self.scheduler is not None) else None)
        result = {
            'embed_id': row.id, 'name': row.name,
            'resource': definition['resource'],
            'status': row.status, 'enabled': row.status == 'enabled',
            'disabled_reason': row.disabled_reason,
            'revision': row.revision, 'is_owner': owner,
            'owner_name': self.bi.access.actor_name(viewer_id, row.user_id),
            'created_at': _iso(row.created_at),
            'updated_at': _iso(row.updated_at),
            'definition': definition,
            'frame_path': (frame_url(row.id) if frame_url
                           else '/cdeadmin/embed/%s/frame' % row.id),
            'keys': [], 'run_as': None,
        }
        if owner:
            result['keys'] = [
                {'kid': k.kid, 'slot': k.slot,
                 'created_at': _iso(k.created_at)}
                for k in self.repository.keys(row.id)]
            result['run_as'] = {
                'principal': 'embedding',
                'delegation': ({'state': delegation.state,
                                'expires_at': _iso(delegation.expires_at)}
                               if delegation is not None else None),
            }
        return result

    # ------------------------------------------------------------------
    # management
    # ------------------------------------------------------------------
    def handle(self, action, request, *, user_id, endpoint_id, server=None,
               frame_url=None):
        if action not in ACTIONS or not isinstance(request, dict):
            raise BIError('BI action is unavailable')
        ident = request.get('embed_id')
        if action == 'bi_embed_catalog':
            return self.catalog()
        if action == 'bi_embed_list':
            return self.list(user_id, endpoint_id,
                             request.get('resource_type'),
                             request.get('resource_id'), frame_url)
        if action == 'bi_embed_create':
            return self.create(user_id, endpoint_id, request.get('embed'),
                               frame_url)
        if action == 'bi_embed_get':
            return self.get(user_id, endpoint_id, ident, frame_url)
        if action == 'bi_embed_update':
            return self.update(user_id, endpoint_id, ident,
                               request.get('expected_revision'),
                               request.get('embed'), frame_url)
        if action == 'bi_embed_enable':
            return self.enable(user_id, endpoint_id, ident, server,
                               request.get('delegation_days', 30), frame_url)
        if action == 'bi_embed_disable':
            return self.disable(user_id, endpoint_id, ident, frame_url)
        if action == 'bi_embed_rotate':
            return self.rotate(user_id, endpoint_id, ident, frame_url)
        if action == 'bi_embed_retire_key':
            return self.retire_previous_key(user_id, endpoint_id, ident,
                                            frame_url)
        if action == 'bi_embed_revoke':
            return self.revoke(user_id, endpoint_id, ident, frame_url)
        if action == 'bi_embed_delete':
            return self.delete(user_id, endpoint_id, ident)
        if action == 'bi_embed_mint':
            return self.mint(user_id, endpoint_id, ident,
                             request.get('params'), request.get('claims'),
                             request.get('ttl_seconds'), frame_url)
        if action == 'bi_embed_preview':
            return self.preview(user_id, endpoint_id, ident,
                                request.get('params'), request.get('claims'),
                                frame_url)
        if action == 'bi_embed_check_token':
            return self.check_token(user_id, endpoint_id, ident,
                                    request.get('token'))
        return self.stats(user_id, endpoint_id, ident, request.get('days'))

    def catalog(self):
        return {
            'available': self.available,
            'enabled': bool(self.config['enabled']),
            'key_authority': bool(self.key_ring is not None and
                                  self.key_ring.available),
            'raw_sql_allowed': bool(self.config['allow_raw_sql']),
            'downloads_allowed': bool(self.config['allow_downloads']),
            'max_token_lifetime_seconds': self.caps['max_token_lifetime'],
            'max_page_size': self.caps['max_page_size'],
            'max_rows': self.caps['max_rows'],
            'algorithm': tokens.ALGORITHM,
            'reserved_claims': sorted(tokens.RESERVED_CLAIMS),
            'preview_seconds': int(self.config['preview_seconds']),
        }

    def _row(self, user_id, endpoint_id, embed_id, *, owner=True):
        """The embed for its owner, or for a manager of its resource."""
        row = self.repository.get(embed_id)
        if row is None or row.endpoint_id != endpoint_id:
            raise BIError('embed is unavailable')
        if owner and row.user_id != user_id:
            raise BIError('embed is unavailable')
        self.bi.access.require(user_id, row.resource_type, endpoint_id,
                               row.resource_id, 'manage', 'embed')
        return row

    def list(self, user_id, endpoint_id, resource_type, resource_id,
             frame_url=None):
        if resource_type not in ('question', 'dashboard') or not isinstance(
                resource_id, str):
            raise BIError('embed list needs a question or dashboard')
        self.bi.access.require(user_id, resource_type, endpoint_id,
                               resource_id, 'manage', 'embed')
        return {'items': [
            self._present(row, user_id, frame_url)
            for row in self.repository.list(
                endpoint_id, resource_type=resource_type,
                resource_id=resource_id)]}

    def get(self, user_id, endpoint_id, embed_id, frame_url=None):
        row = self._row(user_id, endpoint_id, embed_id, owner=False)
        return self._present(row, user_id, frame_url)

    # resource inspection ---------------------------------------------------
    def _resource_definition(self, user_id, endpoint_id, kind, rid,
                             revision):
        """The (pinned) definition of the resource for the OWNER."""
        if kind == 'dashboard':
            if revision is None:
                found = self.dashboards.get(user_id, endpoint_id, rid)
            else:
                found = self.dashboards.revision(user_id, endpoint_id, rid,
                                                 revision)
            return found['definition']
        return self.bi.stored_for_run(user_id, endpoint_id, rid,
                                      revision)['definition']

    def _questions(self, user_id, endpoint_id, kind, rid, revision,
                   definition):
        """``[(question_id, revision, definition)]`` the embed can run."""
        if kind == 'question':
            return [(rid, revision, definition)]
        found = []
        for card in definition['cards']:
            if card['type'] != 'question':
                continue
            pin = card['question']
            stored = self.bi.stored_for_run(
                user_id, endpoint_id, pin['question_id'], pin['revision'])
            found.append((pin['question_id'], pin['revision'],
                          stored['definition']))
        return found

    def _raw_refusal(self, user_id, endpoint_id, questions, declares_claims):
        """Why raw SQL in this embed is refused, or ``None``."""
        for _qid, _rev, question in questions:
            if question['query']['kind'] != 'sql':
                continue
            if not self.config['allow_raw_sql']:
                return ('raw SQL questions cannot be embedded: the server '
                        'setting CDEADMIN_BI_EMBED_ALLOW_RAW_SQL is off')
            if declares_claims:
                return ('raw SQL does not pass through semantic row '
                        'policies, so it cannot be embedded with claims')
            try:
                self.bi.assert_raw_sql_allowed(user_id, endpoint_id)
            except BIError as exc:
                return str(exc)
        return None

    def _inspect(self, user_id, endpoint_id, definition):
        """Check an embed definition against its resource; return the row."""
        resource = definition['resource']
        kind, rid = resource['type'], resource['id']
        row, _level = self.bi.access.require(
            user_id, kind, endpoint_id, rid, 'manage', 'embed')
        if row.status != 'active':
            raise BIError('archived content cannot be embedded')
        content = self._resource_definition(
            user_id, endpoint_id, kind, rid, resource['revision'])
        known = resource_parameters(kind, content)
        declared = parameter_modes(definition)
        missing = sorted(set(declared) - set(known))
        if missing:
            raise BIError('embed declares parameters the %s does not have: '
                          '%s' % (kind, ', '.join(missing)))
        for pid, item in known.items():
            if item.get('required') and 'default' not in item and (
                    pid not in declared):
                raise BIError('required parameter %r must be declared so '
                              'the token or the viewer can supply it' % pid)
        refusal = self._raw_refusal(
            user_id, endpoint_id,
            self._questions(user_id, endpoint_id, kind, rid,
                            resource['revision'], content),
            bool(definition['claims']))
        if refusal:
            raise BIError(refusal)
        if definition['display']['download'] and not (
                self.config['allow_downloads']):
            raise BIError('downloads from embeds are disabled on this '
                          'server (CDEADMIN_BI_EMBED_ALLOW_DOWNLOADS)')
        return row

    # lifecycle ---------------------------------------------------------------
    def create(self, user_id, endpoint_id, value, frame_url=None):
        """A new, DISABLED embed with its first signing secret (shown once)."""
        self._require_available()
        definition = validate_embed(value, caps=self.caps)
        self._inspect(user_id, endpoint_id, definition)
        if self.repository.count(user_id, endpoint_id) >= int(
                self.config['max_embeds_per_user']):
            raise BIError('the embed limit for this user is reached')
        now = self._now()
        row = self.repository.new(
            id=str(uuid.uuid4()), user_id=user_id, endpoint_id=endpoint_id,
            name=definition['name'],
            resource_type=definition['resource']['type'],
            resource_id=definition['resource']['id'],
            resource_revision=definition['resource']['revision'],
            status='disabled', disabled_reason='not_enabled',
            expires_at=self._expiry(definition), revision=1,
            definition=json.dumps(definition), created_at=now,
            updated_at=now)
        self.repository.add(row)
        secret = self._new_secret(row)
        self._record(user_id, 'embed.create', row)
        return {'embed': self._present(row, user_id, frame_url),
                'secret': secret}

    @staticmethod
    def _expiry(definition):
        text = definition['expires_at']
        if text is None:
            return None
        return _naive(datetime.fromisoformat(text))

    def update(self, user_id, endpoint_id, embed_id, expected_revision,
               value, frame_url=None):
        self._require_available()
        row = self._row(user_id, endpoint_id, embed_id)
        if row.status == 'revoked':
            raise BIError('a revoked embed cannot be changed')
        if isinstance(expected_revision, bool) or not isinstance(
                expected_revision, int) or expected_revision != row.revision:
            from .models import BIConflict
            raise BIConflict('embed revision has changed')
        definition = validate_embed(value, caps=self.caps)
        current = json.loads(row.definition)['resource']
        if (definition['resource']['type'], definition['resource']['id']) != (
                current['type'], current['id']):
            raise BIError('an embed cannot move to another resource; '
                          'create a new embed')
        self._inspect(user_id, endpoint_id, definition)
        row.name = definition['name']
        row.resource_revision = definition['resource']['revision']
        row.expires_at = self._expiry(definition)
        row.definition = json.dumps(definition)
        row.revision += 1
        row.updated_at = self._now()
        self.repository.save(row)
        self._record(user_id, 'embed.update', row)
        return self._present(row, user_id, frame_url)

    def enable(self, user_id, endpoint_id, embed_id, server,
               delegation_days=30, frame_url=None):
        """Authorize the owner's credentials for embedded runs and enable."""
        self._require_available()
        row = self._row(user_id, endpoint_id, embed_id)
        if row.status == 'revoked':
            raise BIError('a revoked embed cannot be enabled')
        definition = json.loads(row.definition)
        self._inspect(user_id, endpoint_id, definition)
        if not self.repository.keys(row.id):
            raise BIError('embed has no signing key')
        try:
            self.scheduler.authorize_embed(server, row, delegation_days)
        except (ReportSchedulerAccessError, ReportSchedulerError) as exc:
            raise BIError(str(exc)) from None
        row.status, row.disabled_reason = 'enabled', None
        row.updated_at = self._now()
        self.repository.save(row)
        self._record(user_id, 'embed.enable', row,
                     {'delegation_days': delegation_days})
        return self._present(row, user_id, frame_url)

    def disable(self, user_id, endpoint_id, embed_id, frame_url=None):
        row = self._row(user_id, endpoint_id, embed_id, owner=False)
        if row.status == 'revoked':
            raise BIError('embed is already revoked')
        self._disable(row, 'manual', actor_id=user_id)
        return self._present(row, user_id, frame_url)

    def _disable(self, row, reason, actor_id=None):
        if row.status == 'enabled':
            row.status, row.disabled_reason = 'disabled', reason
            row.updated_at = self._now()
            self.repository.save(row)
        if self.scheduler is not None:
            self.scheduler.revoke_embed(row.id)
        self._record(actor_id, 'embed.disable', row, {'reason': reason})

    def rotate(self, user_id, endpoint_id, embed_id, frame_url=None):
        self._require_available()
        row = self._row(user_id, endpoint_id, embed_id)
        if row.status == 'revoked':
            raise BIError('a revoked embed has no keys')
        secret = self._new_secret(row)
        self._record(user_id, 'embed.rotate', row, {'kid': secret['kid']})
        return {'embed': self._present(row, user_id, frame_url),
                'secret': secret}

    def retire_previous_key(self, user_id, endpoint_id, embed_id,
                            frame_url=None):
        row = self._row(user_id, endpoint_id, embed_id)
        dropped = self.repository.drop_previous(row.id)
        self._record(user_id, 'embed.retire_key', row, {'dropped': dropped})
        return self._present(row, user_id, frame_url)

    def revoke(self, user_id, endpoint_id, embed_id, frame_url=None):
        """Permanent: no token verifies again and the credentials go."""
        row = self._row(user_id, endpoint_id, embed_id, owner=False)
        row.status, row.disabled_reason = 'revoked', 'revoked'
        row.updated_at = self._now()
        self.repository.save(row)
        self.repository.drop_keys(row.id)
        if self.scheduler is not None:
            self.scheduler.revoke_embed(row.id)
        self._record(user_id, 'embed.revoke', row)
        return self._present(row, user_id, frame_url)

    def delete(self, user_id, endpoint_id, embed_id):
        row = self._row(user_id, endpoint_id, embed_id)
        if row.status == 'enabled':
            raise BIError('disable or revoke the embed before deleting it')
        if self.scheduler is not None:
            self.scheduler.revoke_embed(row.id)
        self._record(user_id, 'embed.delete', row)
        self.repository.delete(row)
        return {'embed_id': embed_id, 'deleted': True}

    def _resource_deleted(self, kind, resource_id):
        if kind in ('question', 'dashboard'):
            self.repository.purge_resource(kind, resource_id)

    # tokens for the owner -------------------------------------------------------
    def _mint(self, row, params, claims, ttl, *, preview):
        definition = json.loads(row.definition)
        now = self._epoch()
        payload = {'aud': row.id, 'iat': now, 'nbf': now, 'exp': now + ttl}
        if params:
            payload['params'] = params
        if claims:
            payload['claims'] = claims
        if definition['require_jti'] or preview:
            payload['jti'] = secrets.token_urlsafe(16)
        if preview:
            payload['prv'] = True
        # the helper never produces a token the runtime would refuse
        try:
            checked = tokens.check_claims(
                payload, embed_id=row.id, now=now,
                max_lifetime=self._max_lifetime(definition),
                leeway=int(self.config['clock_skew']))
            tokens.apply_policy(
                checked, parameters=parameter_modes(definition),
                claims=claim_requirements(definition))
        except EmbedTokenError as exc:
            raise BIError('the token would be refused (%s)' % exc.code) \
                from None
        kid, secret = self._current_secret(row)
        return tokens.sign(secret, kid, payload), now + ttl

    def _max_lifetime(self, definition):
        return min(definition['max_token_lifetime_seconds'],
                   self.caps['max_token_lifetime'])

    def mint(self, user_id, endpoint_id, embed_id, params=None, claims=None,
             ttl_seconds=None, frame_url=None):
        """A token for testing, signed with the current key."""
        self._require_available()
        row = self._row(user_id, endpoint_id, embed_id)
        if row.status == 'revoked':
            raise BIError('a revoked embed has no keys')
        definition = json.loads(row.definition)
        ttl = ttl_seconds if ttl_seconds is not None else min(
            300, self._max_lifetime(definition))
        if isinstance(ttl, bool) or not isinstance(ttl, int) or not (
                1 <= ttl <= min(self._max_lifetime(definition),
                                int(self.config['mint_max_seconds']))):
            raise BIError('ttl_seconds is outside the embed lifetime cap')
        token, exp = self._mint(row, params or {}, claims or {}, ttl,
                                preview=False)
        self._record(user_id, 'embed.mint', row, {'ttl': ttl})
        return {'token': token, 'expires_at': _iso(datetime.fromtimestamp(
            exp, timezone.utc).replace(tzinfo=None)),
            'frame_path': (frame_url(row.id) if frame_url
                           else '/cdeadmin/embed/%s/frame' % row.id)}

    def preview(self, user_id, endpoint_id, embed_id, params=None,
                claims=None, frame_url=None):
        """A short-lived, one-time token the BI UI may frame itself."""
        self._require_available()
        row = self._row(user_id, endpoint_id, embed_id)
        if row.status != 'enabled':
            raise BIError('enable the embed to preview it')
        definition = json.loads(row.definition)
        ttl = min(int(self.config['preview_seconds']),
                  self._max_lifetime(definition))
        token, exp = self._mint(row, params or {}, claims or {}, ttl,
                                preview=True)
        return {'token': token, 'expires_in': ttl,
                'frame_path': (frame_url(row.id) if frame_url
                               else '/cdeadmin/embed/%s/frame' % row.id)}

    def check_token(self, user_id, endpoint_id, embed_id, token):
        """Why a token is (not) accepted: the owner's diagnostic."""
        row = self._row(user_id, endpoint_id, embed_id)
        try:
            session = self.authenticate(token, row.id, diagnose=True)
        except EmbedDenied as exc:
            return {'valid': False, 'reason': exc.code}
        return {'valid': True, 'reason': None,
                'expires_in': max(0, session.exp - self._epoch()),
                'params': sorted(session.params),
                'claims': sorted(session.claims),
                'one_time': session.jti is not None}

    def stats(self, user_id, endpoint_id, embed_id, days=None):
        row = self._row(user_id, endpoint_id, embed_id, owner=False)
        if days is None:
            days = 30
        if isinstance(days, bool) or not isinstance(days, int) or not (
                1 <= days <= 365):
            raise BIError('days must be from 1 to 365')
        since = (self.clock() - timedelta(days=days - 1)).strftime(
            '%Y-%m-%d')
        series = self.repository.stats(row.id, since)
        return {'embed_id': row.id, 'days': days, 'series': series,
                'totals': {
                    'views': sum(d['views'] for d in series),
                    'card_runs': sum(d['card_runs'] for d in series),
                    'errors': sum(d['errors'] for d in series)}}

    # ------------------------------------------------------------------
    # runtime: authentication
    # ------------------------------------------------------------------
    def admit_ip(self, address):
        """Per-client budget, spent before anything is looked up."""
        allowed, wait = self._ip.take(address or 'unknown')
        if not allowed:
            raise EmbedRateLimited(wait)

    def authenticate(self, token, embed_id, *, use='continue',
                     diagnose=False):
        """The verified :class:`EmbedSession`, or :class:`EmbedDenied`.

        Order: syntax, embed lookup, signature (always one constant-time
        comparison), status, claims and lifetime, declared parameters and
        claims, per-embed budget, one-time id, then the owner's live rights.
        Nothing about the embed is revealed before the signature verifies.

        ``use`` matters only for a token with a ``jti`` (one-time open):
        ``open`` (the frame page) needs the id unused, ``consume`` (the first
        data call) marks it used and fails on a replay, and ``continue``
        (card runs, paging, export) needs it to have been consumed by the
        opening call, so a token that was never opened cannot run anything.
        """
        if not self.available and not diagnose:
            raise EmbedDenied('unavailable')
        try:
            parsed = tokens.parse(token)
        except EmbedTokenError as exc:
            tokens.verify_signature(_PLACEHOLDER, {})
            raise EmbedDenied(exc.code) from None
        row = self.repository.get(embed_id)
        keys = self._secrets(row) if row is not None else {}
        verified = tokens.verify_signature(parsed, keys)
        if row is None:
            raise EmbedDenied('unknown_embed')
        if not verified:
            raise EmbedDenied('signature')
        if row.status != 'enabled':
            raise EmbedDenied('disabled')
        now = self._epoch()
        if row.expires_at is not None and row.expires_at <= self._now():
            raise EmbedDenied('embed_expired')
        definition = json.loads(row.definition)
        try:
            checked = tokens.check_claims(
                parsed.payload, embed_id=row.id, now=now,
                max_lifetime=self._max_lifetime(definition),
                leeway=int(self.config['clock_skew']))
            tokens.apply_policy(
                checked, parameters=parameter_modes(definition),
                claims=claim_requirements(definition))
        except EmbedTokenError as exc:
            raise EmbedDenied(exc.code) from None
        if definition['require_jti'] and checked['jti'] is None:
            raise EmbedDenied('jti_required')
        if not diagnose:
            allowed, wait = self._embed.take(row.id)
            if not allowed:
                raise EmbedRateLimited(wait)
        if checked['jti'] is not None:
            when = datetime.fromtimestamp(checked['exp'], timezone.utc
                                          ).replace(tzinfo=None)
            if diagnose:
                use = 'open'
            if use == 'consume':
                if not self.repository.consume_jti(
                        row.id, checked['jti'], when, self._now()):
                    raise EmbedDenied('replay')
            else:
                used = self.repository.jti_consumed(
                    row.id, checked['jti'], self._now())
                if use == 'open' and used:
                    raise EmbedDenied('replay')
                if use == 'continue' and not used:
                    raise EmbedDenied('not_opened')
        session = EmbedSession(row, definition, checked, parsed.kid)
        self._live_checks(session, diagnose)
        return session

    def _live_checks(self, session, diagnose):
        """The owner must still manage the resource, which must be live."""
        row = session.row
        try:
            resource, _level = self.bi.access.require(
                session.owner_id, session.resource_type,
                session.endpoint_id, session.resource_id, 'manage',
                'embed')
        except (BIPermissionDenied, BIError):
            if not diagnose:
                self._disable(row, 'owner_access_lost')
            raise EmbedDenied('owner_access_lost') from None
        if resource.status != 'active':
            raise EmbedDenied('resource_unavailable')

    # ------------------------------------------------------------------
    # runtime: what a verified session may do
    # ------------------------------------------------------------------
    def _day(self):
        return self.clock().strftime('%Y-%m-%d')

    def _count(self, session, **counts):
        try:
            self.repository.bump(session.embed_id, self._day(), **counts)
        except Exception:  # counters never break a view
            pass

    def _runtime(self, session):
        delegation = (self.scheduler.delegation_for(session.embed_id)
                      if self.scheduler is not None else None)
        if delegation is None:
            raise EmbedDenied('no_delegation')
        try:
            return self.scheduler.runtime(delegation)
        except ReportSchedulerConflict:
            self._disable(session.row, 'endpoint_changed')
            raise EmbedDenied('endpoint_changed') from None
        except (ReportSchedulerAccessError, ReportSchedulerError):
            if delegation.state != 'active' or (
                    delegation.expires_at <= self._now()):
                self._disable(session.row, 'delegation_expired')
            raise EmbedDenied('delegation_unavailable') from None

    def _dashboard(self, session):
        return self._resource_definition(
            session.owner_id, session.endpoint_id, 'dashboard',
            session.resource_id, session.revision)

    def _question(self, session):
        return self._resource_definition(
            session.owner_id, session.endpoint_id, 'question',
            session.resource_id, session.revision)

    def _viewer_values(self, session, values, label):
        """Viewer-supplied values are limited to editable parameters."""
        if values is None:
            return {}
        if not isinstance(values, dict):
            raise EmbedInvalid('invalid_' + label)
        modes = parameter_modes(session.definition)
        for name in values:
            if modes.get(name) != 'editable':
                raise EmbedInvalid('parameter_not_editable')
        return dict(values)

    def _effective(self, session, viewer):
        """Token values for every declared parameter, then the viewer's
        editable ones on top.  Locked and hidden values can only come from
        the token (or the resource default)."""
        values = dict(session.params)
        values.update({k: v for k, v in viewer.items() if v is not None})
        return values

    def _page_size(self, session, requested):
        cap = min(int(session.definition['page_size']),
                  self.caps['max_page_size'], int(session.definition[
                      'max_rows']))
        if requested is None:
            return cap
        if isinstance(requested, bool) or not isinstance(requested, int) or (
                requested < 1):
            raise EmbedInvalid('invalid_page_size')
        return min(requested, cap)

    # views ---------------------------------------------------------------------
    def view(self, session):
        """Everything the page needs except the results; no ids, no SQL."""
        self._count(session, views=1)
        display = dict(session.definition['display'])
        display['download'] = bool(display['download'] and
                                   self.config['allow_downloads'])
        modes = parameter_modes(session.definition)
        if session.resource_type == 'dashboard':
            dashboard = self._dashboard(session)
            return {
                'kind': 'dashboard', 'name': dashboard['name'],
                'description': dashboard['description'],
                'display': display, 'tabs': dashboard['tabs'],
                'cards': [self._card_view(card) for card in
                          dashboard['cards']],
                'parameters': self._parameter_views(
                    session, dashboard['filters'], modes),
                'drills': self._drill_views(dashboard),
                'page_size': self._page_size(session, None),
            }
        question = self._question(session)
        return {
            'kind': 'question', 'name': question['name'],
            'description': question.get('description', ''),
            'display': display,
            'parameters': self._parameter_views(
                session, question['parameters'], modes),
            'visualization': question.get('visualization'),
            'page_size': self._page_size(session, None),
        }

    @staticmethod
    def _card_view(card):
        view = {'id': card['id'], 'tab_id': card['tab_id'],
                'type': card['type'], 'layout': card['layout'],
                'title': card.get('title', '')}
        if card['type'] == 'question':
            view['visualization'] = card.get('visualization')
        elif card['type'] == 'text':
            view['text'] = card['text']['markdown']
        else:  # a monitoring panel has no embedded form
            view['type'] = 'unsupported'
        return view

    def _parameter_views(self, session, known, modes):
        """Editable and locked parameters; hidden ones are not shown."""
        views = []
        for item in known:
            mode = modes.get(item['id'])
            if mode is None or mode == 'hidden':
                continue
            view = {
                'id': item['id'], 'name': item.get('name', item['id']),
                'type': item.get('type', 'string'), 'mode': mode,
                'widget': item.get('widget', 'text'),
                'multiple': bool(item.get('multiple', False)),
                'required': bool(item.get('required', False)),
                'allowed_values': list(item.get('allowed_values', [])),
            }
            if 'default' in item:
                view['default'] = item['default']
            if item['id'] in session.params:
                view['value'] = session.params[item['id']]
            views.append(view)
        return views

    @staticmethod
    def _pins(dashboard):
        return {(c['question']['question_id'], c['question']['revision']):
                c['id'] for c in dashboard['cards']
                if c['type'] == 'question'}

    def _drill_views(self, dashboard):
        """Drill-throughs to a question that is itself a card of this
        dashboard; nothing else is inside the embed."""
        pins = self._pins(dashboard)
        views = []
        for drill in dashboard['drill_throughs']:
            target = drill['target']
            if target['kind'] != 'question' or (
                    target['question_id'], target['revision']) not in pins:
                continue
            views.append({'id': drill['id'],
                          'source_card_id': drill['source_card_id'],
                          'label': drill['label'],
                          'trigger': drill['trigger']})
        return views

    # results -----------------------------------------------------------------
    def _question_blocked(self, session, question):
        return self._raw_refusal(
            session.owner_id, session.endpoint_id,
            [(None, None, question)], bool(session.definition['claims']))

    def _failure(self, session, exc):
        self._count(session, errors=1)
        message = str(exc)
        if message.endswith('is unavailable') or 'archived' in message:
            return {'status': 'unavailable'}
        return {'status': 'error', 'code': 'failed'}

    def run_card(self, session, card_id, filters=None, page_size=None):
        if session.resource_type != 'dashboard':
            raise EmbedDenied('not_a_dashboard')
        viewer = self._viewer_values(session, filters, 'filters')
        size = self._page_size(session, page_size)
        dashboard = self._dashboard(session)
        card = next((c for c in dashboard['cards']
                     if c['id'] == card_id and c['type'] == 'question'),
                    None)
        if card is None:
            raise EmbedDenied('no_card')
        values = self._effective(session, viewer)
        try:
            stored = self.bi.stored_for_run(
                session.owner_id, session.endpoint_id,
                card['question']['question_id'],
                card['question']['revision'])
            if self._question_blocked(session, stored['definition']):
                self._count(session, errors=1)
                return {'status': 'unavailable', 'card_id': card_id}
            try:  # the typed binder of normal runs, before anything executes
                resolve_filters(dashboard, values)
            except BIError:
                raise EmbedInvalid('invalid_filters') from None
            provider, context, endpoint = self._runtime(session)
            out = self.dashboards.run_card(
                provider=provider, context=context, endpoint=endpoint,
                user_id=session.owner_id, dashboard_id=session.resource_id,
                card_id=card_id, filters=values, revision=session.revision,
                page_size=size,
                security_context=session.security_context,
                principal=session.principal)
        except (EmbedDenied, EmbedInvalid):
            raise
        except BIError as exc:
            return {**self._failure(session, exc), 'card_id': card_id}
        if out.get('no_access'):
            return {'status': 'unavailable', 'card_id': card_id}
        self._count(session, card_runs=1)
        return self._public(session, out, card_id)

    def run_question(self, session, parameters=None, page_size=None):
        if session.resource_type != 'question':
            raise EmbedDenied('not_a_question')
        viewer = self._viewer_values(session, parameters, 'parameters')
        size = self._page_size(session, page_size)
        values = self._effective(session, viewer)
        try:
            question = self._question(session)
            if self._question_blocked(session, question):
                self._count(session, errors=1)
                return {'status': 'unavailable'}
            provider, context, endpoint = self._runtime(session)
            out = self.executor.run(
                provider=provider, context=context, endpoint=endpoint,
                user_id=session.owner_id, question_id=session.resource_id,
                revision=session.revision, parameters=values or None,
                page_size=size, security_context=session.security_context,
                principal=session.principal)
        except EmbedDenied:
            raise
        except BIError as exc:
            return self._failure(session, exc)
        self._count(session, card_runs=1)
        return self._public(session, out, None)

    def drill(self, session, drill_id, row, filters=None):
        """Run a drill-through target that is a card of the same dashboard.

        Locked and hidden values always win over what the clicked row maps
        to; the claims are the token's.  Any other target is refused.
        """
        if session.resource_type != 'dashboard':
            raise EmbedDenied('not_a_dashboard')
        viewer = self._viewer_values(session, filters, 'filters')
        dashboard = self._dashboard(session)
        values = self._effective(session, viewer)
        try:
            target = resolve_drill(dashboard, drill_id, row, values)
        except BIError:
            raise EmbedInvalid('invalid_drill') from None
        pins = self._pins(dashboard)
        key = (target.get('question_id'), target.get('revision'))
        if target['kind'] != 'question' or key not in pins:
            raise EmbedDenied('drill_outside_embed')
        card_id = pins[key]
        try:
            resolved = resolve_filters(dashboard, values)
        except BIError:
            raise EmbedInvalid('invalid_filters') from None
        binding = resolved['cards'][card_id]
        locked = set()
        modes = parameter_modes(session.definition)
        for flt in dashboard['filters']:
            if modes.get(flt['id']) in ('locked', 'hidden', None):
                locked.update(t['parameter_id'] for t in flt['targets']
                              if t['card_id'] == card_id and
                              'parameter_id' in t)
        parameters = {k: v for k, v in target['parameters'].items()
                      if k not in locked}
        parameters = {**binding['parameters'], **parameters}
        size = self._page_size(session, None)
        try:
            stored = self.bi.stored_for_run(
                session.owner_id, session.endpoint_id, key[0], key[1])
            if self._question_blocked(session, stored['definition']):
                return {'status': 'unavailable', 'card_id': card_id}
            provider, context, endpoint = self._runtime(session)
            out = self.executor.run(
                provider=provider, context=context, endpoint=endpoint,
                user_id=session.owner_id, question_id=key[0],
                revision=key[1], parameters=parameters or None,
                extra_filters=binding['extra_filters'], page_size=size,
                security_context=session.security_context,
                principal=session.principal)
        except EmbedDenied:
            raise
        except BIError as exc:
            return {**self._failure(session, exc), 'card_id': card_id}
        self._count(session, card_runs=1)
        return self._public(session, out, card_id)

    # paging / export -------------------------------------------------------------
    def _held(self, session, result_id):
        """The result must be held for THIS principal and belong to the
        embedded resource."""
        info = self.executor.entry_info(result_id)
        if info is None or info[1] != session.principal:
            raise EmbedDenied('no_result')
        return info[0]

    def page(self, session, result_id, cursor, page_size=None):
        self._held(session, result_id)
        size = self._page_size(session, page_size)
        cap = int(session.definition['max_rows'])
        key = (session.principal, result_id)
        with self._lock:
            served = self._served.get(key, 0)
        if served >= cap:
            raise EmbedInvalid('row_limit')
        try:
            out = self.executor.page(
                session.owner_id, session.endpoint_id, result_id,
                cursor=cursor, page_size=min(size, cap - served),
                principal=session.principal)
        except BIError:
            raise EmbedDenied('no_result') from None
        rows = self._records(out)
        self._served_add(key, len(rows))
        more = out['page'].get('next_cursor')
        capped = served + len(rows) >= cap
        return {'rows': rows, 'next_cursor': None if capped else more,
                'truncated': bool(more) and capped}

    def export(self, session, result_id, export_format):
        if not (session.definition['display']['download'] and
                self.config['allow_downloads']):
            raise EmbedDenied('downloads_disabled')
        self._held(session, result_id)
        try:
            exported = self.executor.export(
                session.owner_id, session.endpoint_id, result_id,
                export_format, principal=session.principal)
        except BIError:
            raise EmbedDenied('export_refused') from None
        content = exported.pop('content')
        return content, MEDIA_TYPES.get(export_format,
                                        'application/octet-stream')

    # shaping ---------------------------------------------------------------------
    @staticmethod
    def _records(page):
        view = page['view_model']
        rows = view.get('rows', view.get('records', []))
        return [dict(row) for row in rows]

    def _served_add(self, key, count, *, reset=False):
        """Rows handed out for a result; a fresh run restarts the count at
        its first page, so re-running a card does not use up the cap."""
        with self._lock:
            self._served[key] = (0 if reset else self._served.get(
                key, 0)) + count
            self._served.move_to_end(key)
            while len(self._served) > int(self.config['served_keep']):
                self._served.popitem(last=False)

    def _public(self, session, out, card_id):
        """The response whitelist: rows and what a table needs, no SQL, no
        plan, no cache internals, no reproducibility manifest."""
        rows = self._records(out['page'])
        cap = int(session.definition['max_rows'])
        rows = rows[:cap]
        result_id = out['result']['result_id']
        self._served_add((session.principal, result_id), len(rows),
                         reset=True)
        columns = [c['name'] for c in
                   out['result'].get('schema', {}).get('columns', [])]
        if not columns and rows:
            columns = list(rows[0])
        cursor = out['page']['page'].get('next_cursor')
        if len(rows) >= cap:
            cursor = None
        export = out.get('export') or {}
        download = bool(session.definition['display']['download'] and
                        self.config['allow_downloads'] and
                        export.get('enabled'))
        public = {
            'status': 'ok', 'columns': columns, 'rows': rows,
            'row_count': out['page']['page'].get('source_count'),
            'next_cursor': cursor, 'result_id': result_id,
            'visualization': out.get('visualization'),
            'download': {'formats': list(export.get('formats', []))}
            if download else None,
        }
        if card_id is not None:
            public['card_id'] = card_id
        return public


# a parse failure still burns one constant-time comparison
_PLACEHOLDER = tokens.ParsedToken(
    {'kid': 'none0000'}, {}, b'', b'\x00' * 32)


def init_app(app, bi_service, endpoint_service, report_scheduler):
    """Install the embed service next to the report scheduler."""
    existing = app.extensions.get(APP_EXTENSION_KEY)
    if existing is not None:
        return existing
    from .embed_scheduler import BIEmbedScheduler
    from .embed_store import DatabaseEmbedRepository
    config = {
        # server mode only: desktop mode signs every request in as one user
        'enabled': bool(app.config.get('CDEADMIN_BI_EMBED_ENABLED', False)
                        and app.config.get('SERVER_MODE', False)),
        'allow_raw_sql': bool(app.config.get(
            'CDEADMIN_BI_EMBED_ALLOW_RAW_SQL', False)),
        'allow_downloads': bool(app.config.get(
            'CDEADMIN_BI_EMBED_ALLOW_DOWNLOADS', False)),
    }
    for name, setting in (
            ('max_token_lifetime', 'CDEADMIN_BI_EMBED_MAX_TOKEN_LIFETIME'),
            ('clock_skew', 'CDEADMIN_BI_EMBED_CLOCK_SKEW'),
            ('max_page_size', 'CDEADMIN_BI_EMBED_MAX_PAGE_SIZE'),
            ('max_rows', 'CDEADMIN_BI_EMBED_MAX_ROWS'),
            ('max_embeds_per_user', 'CDEADMIN_BI_EMBED_MAX_PER_USER'),
            ('ip_rate', 'CDEADMIN_BI_EMBED_IP_RATE'),
            ('embed_rate', 'CDEADMIN_BI_EMBED_RATE')):
        if app.config.get(setting) is not None:
            config[name] = app.config[setting]
    scheduler = None
    if report_scheduler is not None:
        scheduler = BIEmbedScheduler(
            endpoint_service, report_scheduler.security_service,
            report_scheduler.key_ring)
    service = BIEmbedService(
        bi_service, DatabaseEmbedRepository(), scheduler=scheduler,
        config=config)
    app.extensions[APP_EXTENSION_KEY] = service
    _register_command(app, service)
    if config['enabled']:
        from .embed_public import register
        register(app, service)
    return service


def _register_command(app, service):
    import click

    @app.cli.command('cde-bi-embed-rotate-keys')
    def rotate_embed_keys():
        """Re-encrypt embed secrets and delegations under the active key."""
        summary = {'secrets': service.rotate_encryption()}
        if service.scheduler is not None:
            summary['delegations'] = service.scheduler.rotate_keys()
        click.echo(json.dumps(summary, sort_keys=True))


__all__ = (
    'ACTIONS', 'BIEmbedService', 'EmbedDenied', 'EmbedInvalid',
    'EmbedRateLimited', 'EmbedSession', 'TokenBuckets', 'init_app',
)

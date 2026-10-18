##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Provider-neutral Data Studio orchestration and bounded history."""

from __future__ import annotations

from .language_tools import capabilities
from .scripts import serialized_execution, serialized_close

import copy
import hashlib
import json
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from pgadmin.cdeadmin.contracts.v1.runtime import (
    ContractValidationError,
    validate_contract,
)
from pgadmin.cdeadmin.security.redaction import redact

from .models import (
    CHANNELS,
    ChannelMessage,
    CompletionContribution,
    DataStudioAccessError,
    DataStudioError,
    ExecutionContribution,
    ExecutionOccurrence,
    FixtureExecutionError,
    LanguageContribution,
    SessionContribution,
    StudioSession,
)


MAX_CHANNEL_MESSAGES = 200
FIXTURE_MARKER = 'cdeadmin_fixture'


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


class BoundedHistory:
    """Redacted occurrence history bounded by count and encoded size."""

    def __init__(self, max_entries=100, max_bytes=1024 * 1024):
        if max_entries < 1 or max_bytes < 256:
            raise DataStudioError('history bounds are invalid')
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self._entries: deque[tuple[int, dict[str, Any]]] = deque()
        self._bytes = 0
        self._lock = threading.RLock()

    def append(self, event_kind, subject_id, payload, extra_keys=()):
        entry = {
            'event_kind': str(event_kind),
            'subject_id': str(subject_id),
            'occurred_at': _now(),
            'payload': redact(payload, extra_keys),
        }
        encoded = json.dumps(
            entry, sort_keys=True, separators=(',', ':'), default=repr
        ).encode('utf-8')
        if len(encoded) > self.max_bytes:
            entry['payload'] = {
                'omitted': True,
                'reason': 'entry exceeds bounded history byte limit',
                'sha256': hashlib.sha256(encoded).hexdigest(),
            }
            encoded = json.dumps(
                entry, sort_keys=True, separators=(',', ':')
            ).encode('utf-8')
        with self._lock:
            self._entries.append((len(encoded), entry))
            self._bytes += len(encoded)
            while (
                len(self._entries) > self.max_entries or
                self._bytes > self.max_bytes
            ):
                size, _discarded = self._entries.popleft()
                self._bytes -= size

    def export(self) -> list[dict[str, Any]]:
        with self._lock:
            return [copy.deepcopy(entry) for _size, entry in self._entries]

    @property
    def encoded_bytes(self):
        with self._lock:
            return self._bytes


class DataStudioContributionRegistry:
    """Language-keyed contributions without provider-name branching."""

    def __init__(self):
        self._languages: dict[str, LanguageContribution] = {}
        self._completions: dict[str, CompletionContribution] = {}
        self._sessions: dict[str, SessionContribution] = {}
        self._executions: dict[str, ExecutionContribution] = {}

    def register_language(self, contribution):
        self._register_one(
            self._languages, contribution.language_profile, contribution
        )

    def register_completion(self, contribution):
        self._register_profiles(self._completions, contribution)

    def register_session(self, contribution):
        self._register_profiles(self._sessions, contribution)

    def register_execution(self, contribution):
        self._register_profiles(self._executions, contribution)

    @staticmethod
    def _register_one(collection, key, contribution):
        if key in collection:
            raise DataStudioError(
                f'Data Studio contribution already exists for {key!r}'
            )
        collection[key] = contribution

    def _register_profiles(self, collection, contribution):
        for profile in contribution.language_profiles:
            self._register_one(collection, profile, contribution)

    def language(self, profile):
        return self._required(self._languages, profile, 'language')

    def completion(self, profile):
        return self._required(self._completions, profile, 'completion')

    def session(self, profile):
        return self._required(self._sessions, profile, 'session')

    def execution(self, profile):
        return self._required(self._executions, profile, 'execution')

    @staticmethod
    def _required(collection, profile, kind):
        try:
            return collection[profile]
        except KeyError as exc:
            raise DataStudioAccessError(
                f'Data Studio {kind} is unavailable for this language profile'
            ) from exc

    def languages(self):
        return tuple(self._languages.values())


class DataStudioService:
    """Common request orchestration with provider-owned execution semantics."""

    def __init__(
        self, provider_registry, contributions=None, history=None,
        result_service=None,
    ):
        from .scripts import ScriptCoordinator
        self.scripts = ScriptCoordinator(self)
        self.provider_registry = provider_registry
        self.contributions = (
            contributions or DataStudioContributionRegistry()
        )
        self.history = history or BoundedHistory()
        self.result_service = result_service
        self._sessions: dict[str, StudioSession] = {}
        self._occurrences: dict[str, ExecutionOccurrence] = {}
        self._contributed_providers: set[tuple[str, str]] = set()
        self._provider_languages: dict[
            tuple[str, str], tuple[str, ...]
        ] = {}
        self._lock = threading.RLock()

    def languages(self, context):
        """Return editor metadata contributed by the active provider."""
        binding = self.provider_registry.resolve(context)
        self._ensure_contributions(binding)
        identity = binding.manifest['identity']
        key = (identity['provider_id'], identity['provider_version'])
        profiles = self._provider_languages.get(key, ())
        def tooling(profile):
            result = capabilities(profile)
            if callable(getattr(type(binding.instance), 'source_tooling', None)):
                result.update(binding.instance.source_tooling(profile))
            return result
        return tuple({
            'language_profile': item.language_profile,
            'title': item.title,
            'editor_mode': item.editor_mode,
            'tooling': tooling(item.language_profile),
            'model_families': sorted(item.model_families),
            'source_kind': item.source_kind,
            'parameter_shape': item.parameter_shape,
            'parameter_hint': item.parameter_hint,
            'starter_source': item.starter_source,
            'source_presets': [
                {'label': label, 'source': source}
                for label, source in item.source_presets
            ],
            'query_plan_templates': [
                {'label': label, 'source_template': source_template}
                for label, source_template in item.query_plan_templates
            ],
            'dialect_contract_id': item.dialect_contract_id,
            'dialect_evidence': list(item.dialect_evidence),
            'transaction_actions': sorted(
                self.contributions.session(
                    item.language_profile
                ).transaction_actions
            ),
        } for item in (
            self.contributions.language(profile) for profile in profiles
        ))

    def open_session(self, context, endpoint_payload, language_profile):
        endpoint = self._contract('Endpoint', endpoint_payload)
        if endpoint['endpoint_id'] != context.endpoint_id:
            raise DataStudioAccessError(
                'session endpoint does not match the active endpoint'
            )
        binding = self.provider_registry.resolve(context)
        self._ensure_contributions(binding)
        identity = binding.manifest['identity']
        admitted = self._provider_languages.get((identity['provider_id'], identity['provider_version']), ())
        if language_profile not in admitted:
            raise DataStudioAccessError('Language is not admitted by the selected provider')
        language = self.contributions.language(language_profile)
        contribution = self.contributions.session(language.language_profile)
        provider_session = self._contract(
            'Session', contribution.open_session(binding, endpoint)
        )
        if (
            provider_session['endpoint_id'] != context.endpoint_id or
            provider_session['language_profile'] != language_profile
        ):
            raise DataStudioAccessError(
                'provider session changed endpoint or language identity'
            )
        execution = self.contributions.execution(language_profile)
        try:
            completion = self.contributions.completion(language_profile)
        except DataStudioAccessError:
            completion = None
        session = StudioSession(
            context.endpoint_id,
            language_profile,
            provider_session,
            contribution.contribution_id,
            execution.contribution_id,
            completion.contribution_id if completion else None,
        )
        with self._lock:
            if session.session_id in self._sessions:
                raise DataStudioAccessError(
                    'provider returned a duplicate session identity'
                )
            self._sessions[session.session_id] = session
        self.history.append('session.opened', session.session_id, {
            'endpoint_id': session.endpoint_id,
            'language_profile': session.language_profile,
            'fixture': False,
        })
        return session.to_dict()

    @serialized_execution
    def complete(
        self, context, session_id, full_source, source_before_cursor, *, client_sql_dialect=None
    ):
        session, binding = self._operational_session(context, session_id)
        contribution = self.contributions.completion(
            session.language_profile
        )
        request = {
            'session_id': session.session_id,
            'full_source': str(full_source),
            'source_before_cursor': str(source_before_cursor),
        }
        if client_sql_dialect is not None:
            if session.language_profile != 'firebird-sql' or type(client_sql_dialect) is not int or client_sql_dialect not in {1, 2, 3}:
                raise DataStudioAccessError('Invalid native editor dialect')
            request['client_sql_dialect'] = client_sql_dialect
        return contribution.complete(binding, request)

    @serialized_execution
    def execute(
        self, context, session_id, source, *, parameters=None,
        deadline=None, output_policy=None,
    ):
        session, binding = self._operational_session(context, session_id)
        contribution = self.contributions.execution(
            session.language_profile
        )
        language = self.contributions.language(session.language_profile)
        if parameters is None or (language.parameter_shape == 'array' and
                                  isinstance(parameters, dict) and
                                  not parameters):
            parameters = [] if language.parameter_shape == 'array' else {}
        expected = ((dict, list)
                    if language.parameter_shape == 'object-or-array' else
                    list if language.parameter_shape == 'array' else dict)
        if not isinstance(parameters, expected):
            raise DataStudioAccessError(
                'This provider language requires a JSON parameter ' +
                language.parameter_shape)
        execution_id = str(uuid.uuid4())
        occurrence_id = str(uuid.uuid4())
        policy = dict(output_policy or {})
        redaction_keys = policy.get('redact_keys', ())
        if not isinstance(redaction_keys, (list, tuple)) or not all(
            isinstance(item, str) and item
            for item in redaction_keys
        ):
            raise DataStudioAccessError(
                'output_policy.redact_keys must be an array of strings'
            )
        redaction_keys = tuple(redaction_keys)
        execution = self._contract('Execution', {
            'identity': dict(binding.manifest['identity']),
            'execution_id': execution_id,
            'session_id': session.session_id,
            'language_profile': session.language_profile,
            'source': str(source),
            'parameters': copy.deepcopy(parameters),
            'deadline': deadline,
            'output_policy': policy,
            'extensions': {
                'cdeadmin': {'occurrence_id': occurrence_id},
            },
        })
        summary = self._execution_summary(execution)
        occurrence = ExecutionOccurrence(
            occurrence_id,
            execution_id,
            session.session_id,
            session.language_profile,
            summary,
            redaction_keys,
        )
        with self._lock:
            self._occurrences[occurrence_id] = occurrence
        self.history.append(
            'execution.requested', occurrence_id, summary,
            policy.get('redact_keys', ()),
        )
        try:
            operation = self._contract(
                'Operation', contribution.execute(binding, execution)
            )
        except Exception:
            occurrence.lifecycle_state = 'submission_failed'
            self.history.append(
                'execution.submission_failed', occurrence_id,
                {'provider_disposition': 'unavailable'},
            )
            raise
        occurrence.operation = operation
        occurrence.lifecycle_state = (
            'provider_terminal' if operation['terminal']
            else 'provider_active'
        )
        self._ingest_channels(occurrence, operation)
        self.history.append(
            'execution.provider_response', occurrence_id,
            self._provider_summary(operation),
            occurrence.redaction_keys,
        )
        return occurrence.to_dict()

    def poll(self, context, occurrence_id):
        occurrence, session, binding = self._operational_occurrence(
            context, occurrence_id
        )
        contribution = self.contributions.execution(
            session.language_profile
        )
        operation, result = contribution.poll(
            binding, copy.deepcopy(occurrence.operation)
        )
        operation = self._contract('Operation', operation)
        result = self._contract('Result', result) if result else None
        self._require_occurrence_identity(occurrence, operation, result)
        occurrence.operation = operation
        occurrence.result = result
        occurrence.lifecycle_state = (
            'provider_terminal' if operation['terminal']
            else 'provider_active'
        )
        self._ingest_channels(occurrence, operation)
        if result:
            self._ingest_channels(occurrence, result)
        self.history.append(
            'execution.polled', occurrence_id,
            {
                'operation': self._provider_summary(operation),
                'result': self._result_summary(result),
            },
            occurrence.redaction_keys,
        )
        return occurrence.to_dict()

    def request_cancel(self, context, occurrence_id):
        occurrence, session, binding = self._operational_occurrence(
            context, occurrence_id
        )
        occurrence.cancellation_state = 'requested'
        self.history.append(
            'cancellation.requested', occurrence_id,
            {'provider_outcome': 'not_yet_available'},
        )
        contribution = self.contributions.execution(
            session.language_profile
        )
        try:
            operation = self._contract(
                'Operation', contribution.cancel(
                    binding, copy.deepcopy(occurrence.operation)
                )
            )
            self._require_occurrence_identity(occurrence, operation, None)
        except Exception:
            occurrence.cancellation_state = 'provider_response_failed'
            self.history.append(
                'cancellation.provider_response_failed', occurrence_id,
                {'provider_outcome': 'unknown'},
            )
            raise
        occurrence.operation = operation
        occurrence.cancellation_state = 'provider_response_recorded'
        occurrence.lifecycle_state = (
            'provider_terminal' if operation['terminal']
            else 'provider_active'
        )
        self._ingest_channels(occurrence, operation)
        self.history.append(
            'cancellation.provider_response_recorded', occurrence_id,
            self._provider_summary(operation),
            occurrence.redaction_keys,
        )
        return occurrence.to_dict()

    def admit_result(
        self, context, occurrence_id, provider_capabilities
    ):
        """Pass a polled provider result to the typed result boundary."""
        occurrence, _session, _binding = self._operational_occurrence(
            context, occurrence_id
        )
        if occurrence.result is None:
            raise DataStudioAccessError(
                'execution occurrence has no result to admit'
            )
        if self.result_service is None:
            raise DataStudioAccessError(
                'CDEadmin typed result service is unavailable'
            )
        return self.result_service.admit_provider_result(
            context,
            copy.deepcopy(occurrence.result),
            provider_capabilities,
        )

    def refresh_transaction(self, context, session_id):
        session, binding = self._operational_session(context, session_id)
        contribution = self.contributions.session(session.language_profile)
        presentation = self._contract(
            'TransactionPresentation',
            contribution.describe_transaction(
                binding, copy.deepcopy(session.provider_session)
            ),
        )
        if presentation['session_id'] != session.session_id:
            raise DataStudioAccessError(
                'provider transaction presentation changed session identity'
            )
        session.transaction_presentation = presentation
        self.history.append(
            'transaction.presentation_refreshed', session_id,
            {
                'transaction_model': presentation['transaction_model'],
                'authority_reference': presentation['authority_reference'],
                'provider_payload': presentation['provider_payload'],
            },
        )
        return copy.deepcopy(presentation)

    @serialized_execution
    def control_transaction(self, context, session_id, action):
        """Dispatch an advertised action and return provider-owned state."""
        session, binding = self._operational_session(context, session_id)
        contribution = self.contributions.session(session.language_profile)
        if action not in contribution.transaction_actions:
            raise DataStudioAccessError(
                'transaction action is unavailable for this provider'
            )
        self.history.append(
            'transaction.action_requested', session_id,
            {'action': action, 'finality': 'provider-owned'},
        )
        try:
            presentation = self._contract(
                'TransactionPresentation',
                contribution.control_transaction(binding, {
                    **copy.deepcopy(session.provider_session),
                    'action': action,
                }),
            )
        except Exception:
            self.history.append(
                'transaction.action_response_failed', session_id,
                {'action': action, 'outcome': 'unknown'},
            )
            raise
        if presentation['session_id'] != session.session_id:
            raise DataStudioAccessError(
                'provider transaction action changed session identity'
            )
        session.transaction_presentation = presentation
        self.history.append(
            'transaction.action_provider_response', session_id,
            {
                'action': action,
                'authority_reference': presentation['authority_reference'],
                'provider_payload': presentation['provider_payload'],
            },
        )
        return copy.deepcopy(presentation)

    @serialized_execution
    def session_catalog(self, context, session_id, *, include_system=False):
        session, binding = self._operational_session(context, session_id)
        if type(include_system) is not bool:
            raise DataStudioAccessError('Invalid system-object selection')
        engines={'postgresql-sql':'postgresql','duckdb-sql':'duckdb','sqlite-sql':'sqlite'}
        engine=engines.get(session.language_profile)
        if engine is None or not callable(
                getattr(type(binding.instance), 'capture_session_catalog', None)):
            raise DataStudioAccessError('Retained-session catalog is unavailable for this provider')
        result = binding.instance.capture_session_catalog({
            'session_id': session.provider_session['session_id'],
            'language_profile': session.language_profile, 'include_system': include_system})
        from ..workspace.firebird_catalog_export import build_export
        try:
            result['document'] = build_export(result['resources'], endpoint_id=context.endpoint_id,
                target_id='postgresql-database:' + str(result['database_oid']) if engine=='postgresql' else result['catalog_target_id'],
                generation=result['generation'], include_system=include_system,
                refreshed=True, engine=engine)
        except ValueError:
            result['document'] = None
            result['export_warning'] = 'This catalog exceeds the DDN export bounds. Native inspection remains available.'
        result['engine']=engine
        from .catalog_values import exact_native_integers
        for resource in result['resources']:exact_native_integers(resource)
        return result

    @serialized_execution
    def sqlite_extension_action(self, context, session_id, request):
        session, binding = self._operational_session(context, session_id)
        if session.language_profile != 'sqlite-sql' or context.provider_id != 'org.cdeadmin.sqlite':
            raise DataStudioAccessError('Native SQLite query session required')
        import config
        try:
            return binding.instance.extension_action({**request,
                'session_id': session.provider_session['session_id'],
                'language_profile': session.language_profile},
                config.CDEADMIN_SQLITE_EXTENSION_MANIFEST)
        except (ValueError, OSError) as error:
            raise DataStudioAccessError(str(error)) from None

    @serialized_execution
    def sqlite_native_session_action(self, context, session_id, request):
        session,binding=self._operational_session(context,session_id)
        if session.language_profile!='sqlite-sql' or context.provider_id!='org.cdeadmin.sqlite':
            raise DataStudioAccessError('Native SQLite query session required')
        import config
        try:
            return binding.instance.native_session_action({**request,'session_id':session.provider_session['session_id'],
                'language_profile':session.language_profile},getattr(config,'CDEADMIN_SQLITE_SESSION_LIBRARY',None))
        except (ValueError,OSError) as error:raise DataStudioAccessError(str(error)) from None

    @serialized_execution
    def sqlite_native_array_action(self, context, session_id, request):
        session,binding=self._operational_session(context,session_id)
        if session.language_profile!='sqlite-sql' or context.provider_id!='org.cdeadmin.sqlite':
            raise DataStudioAccessError('Native SQLite query session required')
        import config
        try:
            return binding.instance.native_array_action({**request,'session_id':session.provider_session['session_id'],
                'language_profile':session.language_profile},getattr(config,'CDEADMIN_SQLITE_ARRAY_LIBRARY',None),
                getattr(config,'CDEADMIN_SQLITE_ARRAY_MAX_BYTES',None))
        except (ValueError,OSError) as error:raise DataStudioAccessError(str(error)) from None

    @serialized_execution
    def sqlite_native_preupdate_action(self, context, session_id, request):
        session,binding=self._operational_session(context,session_id)
        if session.language_profile!='sqlite-sql' or context.provider_id!='org.cdeadmin.sqlite':
            raise DataStudioAccessError('Native SQLite query session required')
        import config
        try:
            return binding.instance.native_preupdate_action({**request,'session_id':session.provider_session['session_id'],
                'language_profile':session.language_profile},getattr(config,'CDEADMIN_SQLITE_PREUPDATE_LIBRARY',None))
        except (ValueError,OSError) as error:raise DataStudioAccessError(str(error)) from None

    @serialized_execution
    def sqlite_transform_binding(self, context, session_id, library, database=None):
        session,binding=self._operational_session(context,session_id)
        if session.language_profile!='sqlite-sql' or context.provider_id!='org.cdeadmin.sqlite':
            raise DataStudioAccessError('Native SQLite query session required')
        from ..providers.sqlite.session_api import SessionAPI,SessionAPIError
        from ..providers.sqlite.transform_context import retained_snapshot
        provider=binding.instance;provider._require('execute');provider._require('administer')
        handle=provider._editor_session({'session_id':session.provider_session['session_id']})
        with provider.client._lock:
            provider.client._require_idle(handle)
            api=handle._cdeadmin_session_api or SessionAPI(handle,library,owner_shutdown=provider.client.close)
            if api.program.get('native_session_revision',0)<3:raise SessionAPIError('The retained helper lacks native changegroups')
            source=retained_snapshot(handle,api,session_id,database)
            return {'client':provider.client,'handle':handle,'api':api,'source':source,'program':api.program}

    @serialized_execution
    def sqlite_capture_binding(self, context, session_id, capture_id):
        session,binding=self._operational_session(context,session_id)
        if session.language_profile!='sqlite-sql' or context.provider_id!='org.cdeadmin.sqlite':
            raise DataStudioAccessError('Native SQLite query session required')
        provider=binding.instance;provider._require('execute');provider._require('administer')
        handle=provider._editor_session({'session_id':session.provider_session['session_id']})
        with provider.client._lock:
            provider.client._require_idle(handle)
            api=handle._cdeadmin_session_api
            if api is None or capture_id not in api.captures:raise DataStudioAccessError('Native capture belongs to another or closed query connection')
            observed=api.status(capture_id)
            source={'studio_session_id':session_id,'capture_id':capture_id,'database':observed['database'],
                'databases':[list(row) for row in handle.execute('PRAGMA database_list')]}
            return {'client':provider.client,'handle':handle,'api':api,'source':source,'program':api.program}

    @serialized_execution
    def validate_source(self, context, session_id, source, *, client_sql_dialect=None, script=False):
        from .language_tools import analyze
        session, binding = self._operational_session(context, session_id)
        options = {}
        if type(script) is not bool:
            raise DataStudioAccessError('Script checking requires a boolean')
        if script:
            options['script'] = True
        if client_sql_dialect is not None:
            if session.language_profile != 'firebird-sql' or type(client_sql_dialect) is not int or client_sql_dialect not in {1, 2, 3}:
                raise DataStudioAccessError('Invalid native editor dialect')
            options['client_sql_dialect'] = client_sql_dialect
        # Providers may supply an explicitly non-executing native validator.
        validator = getattr(binding.instance, 'validate_source_without_execution', None)
        if callable(validator):
            return validator({
                'session_id': session.provider_session['session_id'],
                'language_profile': session.language_profile,
                'source': source, **options})
        return analyze(source, session.language_profile, script=script)

    def preview_script(self, context, session_id, source):
        session, binding = self._operational_session(context, session_id)
        if context.provider_id not in {
                'org.cdeadmin.firebird', 'org.cdeadmin.firebird.embedded'}:
            raise DataStudioAccessError('Provider has not admitted scripts')
        return binding.instance.preview_script({
            'source': source,
            'session_id': session.provider_session['session_id'],
        })

    @serialized_execution
    def query_stream(self, context, session_id, request):
        session, binding = self._operational_session(context, session_id)
        if context.provider_id not in {
                'org.cdeadmin.firebird', 'org.cdeadmin.firebird.embedded'}:
            raise DataStudioAccessError('Provider has not admitted streaming')
        self.history.append('stream.requested', session_id, {
            'action': request.get('stream_action'),
            'finality': 'provider-owned',
        })
        return binding.instance.query_stream({
            **copy.deepcopy(request),
            'session_id': session.provider_session['session_id'],
        })

    @serialized_close
    def close_session(self, context, session_id):
        """Close a provider-owned session and forget its local presentation."""
        session, binding = self._operational_session(context, session_id)
        contribution = self.contributions.session(session.language_profile)
        if not callable(contribution.close_session):
            raise DataStudioAccessError(
                'session close is unavailable for this provider'
            )
        response = contribution.close_session(
            binding, copy.deepcopy(session.provider_session)
        )
        if not isinstance(response, Mapping) or (
                response.get('session_id') != session.session_id or
                response.get('provider_closed') is not True):
            raise DataStudioAccessError(
                'provider did not confirm session closure'
            )
        with self._lock:
            self._sessions.pop(session.session_id, None)
        self.scripts.forget_closed_session(session.session_id)
        self.history.append('session.closed', session.session_id, {
            'endpoint_id': session.endpoint_id,
            'provider_closed': True,
            'finality': 'provider-owned',
        })
        return copy.deepcopy(dict(response))

    def publish_channel(self, occurrence_id, channel, payload):
        if channel not in CHANNELS:
            raise DataStudioAccessError('Data Studio channel is unknown')
        occurrence = self._occurrence(occurrence_id)
        message = ChannelMessage(
            channel, _now(), redact(payload, occurrence.redaction_keys)
        )
        occurrence.channels.append(message)
        if len(occurrence.channels) > MAX_CHANNEL_MESSAGES:
            del occurrence.channels[:-MAX_CHANNEL_MESSAGES]
        self.history.append(
            f'channel.{channel}', occurrence_id, message.payload,
            occurrence.redaction_keys,
        )
        return message.to_dict()

    def occurrence(self, occurrence_id):
        return self._occurrence(occurrence_id).to_dict()

    def session(self, session_id):
        try:
            return self._sessions[session_id].to_dict()
        except KeyError as exc:
            raise DataStudioAccessError(
                'Data Studio session is unavailable'
            ) from exc

    def export_history(self):
        return self.history.export()

    def load_fixture_story(self, context, path: Path):
        payload = json.loads(path.read_text(encoding='utf-8'))
        marker = payload.get(FIXTURE_MARKER, {})
        if payload.get('production') is not False or not (
            isinstance(marker, Mapping) and marker.get('non_production')
        ):
            raise DataStudioAccessError(
                'Data Studio fixture lacks a non-production marker'
            )
        loaded = []
        for raw in payload.get('sessions', []):
            provider_session = self._contract('Session', raw)
            if provider_session['endpoint_id'] != context.endpoint_id:
                raise DataStudioAccessError(
                    'fixture session belongs to another endpoint'
                )
            session = StudioSession(
                context.endpoint_id,
                provider_session['language_profile'],
                provider_session,
                None,
                None,
                None,
                fixture=True,
                execution_enabled=False,
            )
            with self._lock:
                self._sessions[session.session_id] = session
            loaded.append(session.to_dict())
            self.history.append(
                'fixture.session_loaded', session.session_id,
                {'fixture': True, 'execution_enabled': False},
            )
        return tuple(loaded)

    def _operational_session(self, context, session_id):
        try:
            session = self._sessions[session_id]
        except KeyError as exc:
            raise DataStudioAccessError(
                'Data Studio session is unavailable'
            ) from exc
        if session.endpoint_id != context.endpoint_id:
            raise DataStudioAccessError(
                'Data Studio session belongs to another endpoint'
            )
        if session.fixture or not session.execution_enabled:
            raise FixtureExecutionError(
                'non-production Data Studio fixtures cannot execute'
            )
        binding = self.provider_registry.resolve(context)
        # Evidence references describe qualification provenance. A provider's
        # session citation may differ from its package citation without changing
        # the contract/provider/profile identity that owns the retained handle.
        identity_keys = ('contract_version', 'provider_id', 'provider_version', 'profile_id', 'profile_version')
        if any(session.provider_session['identity'].get(key) != binding.manifest['identity'].get(key)
               for key in identity_keys):
            raise DataStudioAccessError('Retained session provider identity changed')
        self._ensure_contributions(binding)
        return session, binding

    def _operational_occurrence(self, context, occurrence_id):
        occurrence = self._occurrence(occurrence_id)
        session, binding = self._operational_session(
            context, occurrence.session_id
        )
        if occurrence.operation is None:
            raise DataStudioAccessError(
                'execution has no provider operation to control'
            )
        return occurrence, session, binding

    def _occurrence(self, occurrence_id):
        try:
            return self._occurrences[occurrence_id]
        except KeyError as exc:
            raise DataStudioAccessError(
                'Data Studio execution occurrence is unavailable'
            ) from exc

    def _ensure_contributions(self, binding):
        identity = binding.manifest['identity']
        key = (identity['provider_id'], identity['provider_version'])
        with self._lock:
            if key in self._contributed_providers:
                return
            contributor = getattr(
                binding.instance, 'data_studio_contributions', None
            )
            if not callable(contributor):
                raise DataStudioAccessError(
                    'provider has no Data Studio contributions'
                )
            payload = contributor()
            if not isinstance(payload, Mapping) or set(payload).difference({
                'languages', 'completions', 'sessions', 'executions'
            }):
                raise DataStudioError(
                    'provider Data Studio contributions are invalid'
                )
            expected = {
                'languages': LanguageContribution,
                'completions': CompletionContribution,
                'sessions': SessionContribution,
                'executions': ExecutionContribution,
            }
            registrars = {
                'languages': self.contributions.register_language,
                'completions': self.contributions.register_completion,
                'sessions': self.contributions.register_session,
                'executions': self.contributions.register_execution,
            }
            for collection, expected_type in expected.items():
                for contribution in payload.get(collection, ()):
                    if not isinstance(contribution, expected_type):
                        raise DataStudioError(
                            f'provider {collection} contribution is invalid'
                        )
                    self._reject_endpoint_bound_callbacks(contribution)
                    registrars[collection](contribution)
            self._provider_languages[key] = tuple(
                item.language_profile
                for item in payload.get('languages', ())
            )
            self._contributed_providers.add(key)

    @staticmethod
    def _contract(name, payload):
        try:
            return validate_contract(name, payload)
        except ContractValidationError as exc:
            raise DataStudioAccessError(
                f'provider returned an invalid {name}'
            ) from exc

    @staticmethod
    def _reject_endpoint_bound_callbacks(contribution):
        callbacks = (
            getattr(contribution, name, None)
            for name in (
                'complete', 'open_session', 'describe_transaction',
                'control_transaction', 'close_session', 'execute', 'poll',
                'cancel',
            )
        )
        for callback in callbacks:
            owner = getattr(callback, '__self__', None)
            if owner is not None and not isinstance(owner, type):
                raise DataStudioError(
                    'provider contribution callback captures endpoint state'
                )

    @staticmethod
    def _execution_summary(execution):
        source = execution['source'].encode('utf-8')
        parameters = execution['parameters']
        return {
            'execution_id': execution['execution_id'],
            'session_id': execution['session_id'],
            'language_profile': execution['language_profile'],
            'source_length': len(source),
            'source_sha256': hashlib.sha256(source).hexdigest(),
            'parameter_names': (sorted(str(key) for key in parameters)
                                if isinstance(parameters, dict) else []),
            'parameter_shape': (
                'object' if isinstance(parameters, dict) else 'array'),
            'parameter_count': len(parameters),
            'deadline': execution['deadline'],
        }

    @staticmethod
    def _provider_summary(operation):
        return {
            'operation_id': operation['operation_id'],
            'operation_kind': operation['operation_kind'],
            'terminal': operation['terminal'],
            'provider_state': operation['provider_state'],
            'provider_receipt': operation['provider_receipt'],
        }

    @staticmethod
    def _result_summary(result):
        if result is None:
            return None
        return {
            'result_id': result['result_id'],
            'execution_id': result['execution_id'],
            'result_kind': result['result_kind'],
            'complete': result['complete'],
            'continuation': result.get('continuation'),
        }

    @staticmethod
    def _require_occurrence_identity(occurrence, operation, result):
        if operation['operation_id'] != occurrence.operation['operation_id']:
            raise DataStudioAccessError(
                'provider changed operation identity during execution'
            )
        if result is not None and (
            result['execution_id'] != occurrence.execution_id
        ):
            raise DataStudioAccessError(
                'provider result belongs to another execution'
            )

    def _ingest_channels(self, occurrence, payload):
        extensions = payload.get('extensions', {})
        if not isinstance(extensions, Mapping):
            return
        messages = extensions.get('cdeadmin_channels', ())
        if not isinstance(messages, (list, tuple)):
            return
        for item in messages:
            if not isinstance(item, Mapping):
                continue
            channel = item.get('channel')
            if channel in CHANNELS:
                self.publish_channel(
                    occurrence.occurrence_id,
                    channel,
                    item.get('payload', {}),
                )

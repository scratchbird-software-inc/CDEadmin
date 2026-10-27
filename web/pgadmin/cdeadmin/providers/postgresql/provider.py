##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""PostgreSQL provider adapters around preserved pgAdmin behavior.

This module owns PostgreSQL-specific catalog templates, driver calls and
transaction presentation.  Common CDEadmin code treats every provider-native
transaction payload as opaque.
"""

from __future__ import annotations

import copy
import json
import uuid
import threading
from contextlib import ExitStack, contextmanager
from functools import wraps
from dataclasses import dataclass, field
from typing import Any, Mapping

from flask import render_template

from pgadmin.utils.compile_template_name import compile_template_path
from pgadmin.utils.driver.registry import DriverRegistry
from pgadmin.cdeadmin.data_studio import (
    CompletionContribution,
    ExecutionContribution,
    LanguageContribution,
    SessionContribution,
)
from pgadmin.cdeadmin.results import ResultAdapterContribution
from pgadmin.cdeadmin.resources.models import (
    ResourceCommandContribution,
    ResourceInspectorContribution,
)
from pgadmin.cdeadmin.resources.properties import (
    normalize_resource_properties,
)
from pgadmin.cdeadmin.visual_admin import (
    ProviderVisualAdministration,
    enrich_engine_experience,
)
from .execution import (
    Execution, parameters as native_parameters, control as native_control,
)
from .native_admin import (
    PostgreSQLNativeAdminError, compile_native_admin,
)
from .catalog_capture import CAPTURE_RESOURCE_KINDS
from .preserved_surface import (
    SURFACE_ID, adapt_catalog, concept_declarations, administration_operations,
)


PROVIDER_ID = 'org.pgadmin.postgresql'
PROVIDER_VERSION = '9.17.0'
PROFILE_ID = 'postgresql-native'
PROFILE_VERSION = '18.3'
LEGACY_DRIVER_TYPE = 'psycopg3'
APPROVED_DRIVER_VERSIONS = frozenset({'3.2.13', '3.3.4'})
EVIDENCE_REFERENCE = 'cde-prep-050:postgresql-preservation-20260831'
CATALOG_KINDS = frozenset({'database', 'schema', 'table', 'conversion',
                           'operator-class', 'operator-family', 'access-method', 'transform', 'operator', 'aggregate', 'large-object'})
TABULAR_RENDER_CAPABILITY = 'postgresql.result.tabular.render'

TOOL_DISPOSITIONS = {
    'backup': 'provider-local-existing-tool',
    'restore': 'provider-local-existing-tool',
    'maintenance': 'provider-local-existing-tool',
    'psql': 'provider-local-existing-tool',
    'debugger': 'provider-local-existing-tool',
}

POSTGRESQL_CONCEPT_DECLARATIONS = {
    'relational': concept_declarations(),
}
POSTGRESQL_ADMIN_OPERATIONS = administration_operations()


class PostgreSQLProviderError(RuntimeError):
    """A PostgreSQL provider operation cannot be completed safely."""


def _mapping(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    to_dict = getattr(value, 'to_dict', None)
    if callable(to_dict):
        return to_dict()
    raise PostgreSQLProviderError('provider request must be a contract DTO')


def _extension(payload: Mapping[str, Any]) -> dict[str, Any]:
    extensions = payload.get('extensions', {})
    if not isinstance(extensions, Mapping):
        raise PostgreSQLProviderError('extensions must be an object')
    value = extensions.get('postgresql', {})
    if not isinstance(value, Mapping):
        raise PostgreSQLProviderError(
            'extensions.postgresql must be an object'
        )
    return dict(value)


def _required_int(value: Mapping[str, Any], name: str) -> int:
    item = value.get(name)
    if isinstance(item, bool) or not isinstance(item, int):
        raise PostgreSQLProviderError(f'postgresql.{name} must be an integer')
    return item


def _required_text(value, label):
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise PostgreSQLProviderError(f'{label} must not be empty')
    return value.strip()


def _provider_serialized(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self._state_lock:
            return method(self, *args, **kwargs)
    return call


def _session_serialized(method):
    @_provider_serialized
    @wraps(method)
    def call(self, request):
        payload = _mapping(request)
        session_id = payload.get('session_id')
        if not session_id and payload.get('operation_id'):
            session_id = self._operation(payload['operation_id']).session_id
        state = self._sessions.get(session_id)
        if state is None:
            # Terminal receipts remain observable after explicit session close.
            return method(self, request)
        with state.lock:
            return method(self, request)
    return call


@dataclass
class _SessionState:
    server_id: int
    database_id: int | None
    connection_id: str
    connection: object
    manager: object
    uncertain: bool = False
    attached: bool = False
    lock: object = field(default_factory=threading.RLock)


@dataclass
class _OperationState:
    operation: dict[str, Any]
    execution_id: str
    session_id: str
    connection: object
    result: dict[str, Any] | None = None
    execution: object = None


class PostgreSQLCatalogSource:
    """Execute preserved PostgreSQL browser templates without moving them."""

    def __init__(self, driver, renderer=render_template):
        self._driver = driver
        self._renderer = renderer

    def read(
        self,
        catalog_kind: str,
        route: Mapping[str, Any],
        object_id: int | None = None,
    ) -> list[dict[str, Any]]:
        if catalog_kind not in CATALOG_KINDS:
            raise PostgreSQLProviderError(
                f'unsupported PostgreSQL catalog kind {catalog_kind!r}'
            )
        server_id = _required_int(route, 'server_id')
        manager = self._driver.connection_manager(server_id)
        if manager is None:
            raise PostgreSQLProviderError('PostgreSQL server is unavailable')
        if catalog_kind == 'database':
            return self._databases(manager, object_id)
        database_id = _required_int(route, 'database_id')
        connection = manager.connection(did=database_id)
        if catalog_kind in {'conversion', 'operator-class', 'operator-family', 'access-method', 'transform', 'operator', 'aggregate', 'large-object'}:
            return self._advanced(connection, catalog_kind, route, object_id)
        if catalog_kind == 'schema':
            return self._schemas(manager, connection, route, object_id)
        return self._tables(manager, connection, route, object_id)

    def _advanced(self, connection, kind, route, object_id):
        if not connection.connected():
            raise PostgreSQLProviderError('Connect to the selected database before browsing objects')
        queries = {
            'large-object': ('SELECT c.oid,c.oid::text AS name,pg_catalog.pg_get_userbyid(c.lomowner) AS owner '
                'FROM pg_catalog.pg_largeobject_metadata c', None),
            'aggregate': ('SELECT c.oid, c.proname AS name, n.nspname AS schema, '
                'pg_catalog.pg_get_function_identity_arguments(c.oid) AS identity_arguments '
                ', (pg_catalog.pg_identify_object(\'pg_catalog.pg_proc\'::regclass,c.oid,0)).identity AS sql_identity '
                'FROM pg_catalog.pg_proc c JOIN pg_catalog.pg_aggregate a ON a.aggfnoid=c.oid '
                'JOIN pg_catalog.pg_namespace n ON n.oid=c.pronamespace', 'n.oid'),
            'operator': ('SELECT c.oid, c.oprname AS name, n.nspname AS schema, '
                'CASE WHEN c.oprleft=0 THEN NULL ELSE (pg_catalog.pg_identify_object(\'pg_catalog.pg_type\'::regclass,c.oprleft,0)).identity END AS left_type, '
                '(pg_catalog.pg_identify_object(\'pg_catalog.pg_type\'::regclass,c.oprright,0)).identity AS right_type '
                'FROM pg_catalog.pg_operator c JOIN pg_catalog.pg_namespace n ON n.oid=c.oprnamespace', 'n.oid'),
            'access-method': ('SELECT c.oid, c.amname AS name, c.amtype AS method_type, '
                'c.amhandler::pg_catalog.regproc::text AS handler FROM pg_catalog.pg_am c', None),
            'transform': ("SELECT c.oid, pg_catalog.quote_ident(n.nspname) || '.' || pg_catalog.quote_ident(t.typname) || ' / ' || l.lanname AS name, "
                "pg_catalog.quote_ident(n.nspname) || '.' || pg_catalog.quote_ident(t.typname) AS data_type, l.lanname AS language "
                'FROM pg_catalog.pg_transform c JOIN pg_catalog.pg_language l ON l.oid=c.trflang '
                'JOIN pg_catalog.pg_type t ON t.oid=c.trftype '
                'JOIN pg_catalog.pg_namespace n ON n.oid=t.typnamespace', None),
            'conversion': ('SELECT c.oid, c.conname AS name, n.nspname AS schema '
                'FROM pg_catalog.pg_conversion c JOIN pg_catalog.pg_namespace n ON n.oid=c.connamespace', 'n.oid'),
            'operator-class': ('SELECT c.oid, c.opcname AS name, n.nspname AS schema, a.amname AS index_method '
                'FROM pg_catalog.pg_opclass c JOIN pg_catalog.pg_namespace n ON n.oid=c.opcnamespace '
                'JOIN pg_catalog.pg_am a ON a.oid=c.opcmethod', 'n.oid'),
            'operator-family': ('SELECT c.oid, c.opfname AS name, n.nspname AS schema, a.amname AS index_method '
                'FROM pg_catalog.pg_opfamily c JOIN pg_catalog.pg_namespace n ON n.oid=c.opfnamespace '
                'JOIN pg_catalog.pg_am a ON a.oid=c.opfmethod', 'n.oid'),
        }
        statement, schema_column = queries[kind]
        clauses, parameters = [], []
        if schema_column:
            clauses.append(schema_column + '=%s')
            parameters.append(_required_int(route, 'schema_id'))
        if object_id is not None:
            clauses.append('c.oid=%s')
            parameters.append(object_id)
        if clauses:
            statement += ' WHERE ' + ' AND '.join(clauses)
        statement += ' ORDER BY name, c.oid LIMIT 1001'
        status, result = connection.execute_dict(statement, parameters)
        rows = self._rows(status, result)
        if len(rows) > 1000:
            raise PostgreSQLProviderError('Advanced-object catalog exceeds 1000 objects; narrow the scope')
        return rows

    def _databases(self, manager, object_id):
        connection = manager.connection()
        template = 'databases/sql/#{0}#/nodes.sql'.format(manager.version)
        sql = self._renderer(
            template,
            did=object_id,
            conn=connection,
            last_system_oid=0,
            show_system_objects=True,
            db_restrictions=None,
        )
        status, result = connection.execute_dict(sql)
        return self._rows(status, result)

    def _schemas(self, manager, connection, route, object_id):
        template = 'schemas/{0}/#{1}#/sql/nodes.sql'.format(
            manager.server_type, manager.version
        )
        sql = self._renderer(
            template,
            show_sysobj=bool(route.get('show_system_objects', False)),
            scid=object_id,
            schema_restrictions=None,
            conn=connection,
        )
        status, result = connection.execute_2darray(sql)
        return self._rows(status, result)

    def _tables(self, manager, connection, route, object_id):
        schema_id = _required_int(route, 'schema_id')
        template = '/'.join((
            compile_template_path('tables/sql', manager.version),
            'nodes.sql',
        ))
        sql = self._renderer(
            template,
            scid=schema_id,
            tid=object_id,
        )
        status, result = connection.execute_2darray(sql)
        return self._rows(status, result)

    @staticmethod
    def _rows(status, result):
        if not status:
            raise PostgreSQLProviderError(str(result))
        if not isinstance(result, Mapping) or not isinstance(
            result.get('rows'), list
        ):
            raise PostgreSQLProviderError(
                'PostgreSQL catalog response has no row collection'
            )
        return [dict(row) for row in result['rows']]


class PostgreSQLProvider:
    """Endpoint-isolated facade over the existing PostgreSQL implementation."""

    def __init__(self, context, permissions, driver=None, catalog_source=None):
        self.context = context
        self.permissions = permissions
        self._driver = driver or DriverRegistry.get(LEGACY_DRIVER_TYPE)
        self._catalog = catalog_source or PostgreSQLCatalogSource(self._driver)
        self._sessions: dict[str, _SessionState] = {}
        self._operations: dict[str, _OperationState] = {}
        self._completion_adapters: dict[str, object] = {}
        self._closed = False
        self._state_lock = threading.RLock()
        self._visual_admin = ProviderVisualAdministration(
            context, permissions, 'postgresql', PROFILE_VERSION,
            client=self, operation_gate=self.supports_admin_operation,
        )

    @staticmethod
    def supports_admin_operation(resource_kind, operation_id):
        return operation_id in POSTGRESQL_ADMIN_OPERATIONS.get(
            resource_kind, frozenset()
        )

    @staticmethod
    def engine_contract_descriptor():
        from ...engine_contracts import contract_descriptor
        from .contracts import PROFILE,dialect_task_ids
        return contract_descriptor(PROFILE,__name__,dialect_task_ids())

    @staticmethod
    def visual_admin_catalog(catalog):
        """Expose only operations routed to the preserved PostgreSQL UI."""
        return adapt_catalog(catalog)

    @staticmethod
    def _native_admin_route(request):
        route = request.get('_provider_route') or {}
        if not isinstance(route, Mapping):
            raise PostgreSQLProviderError(
                'PostgreSQL provider route is invalid'
            )
        return {
            'server_id': _required_int(route, 'server_id'),
            'database_id': _required_int(route, 'database_id'),
        }

    @classmethod
    def _compile_native_admin(cls, request):
        try:
            return compile_native_admin(request)
        except PostgreSQLNativeAdminError as exc:
            raise PostgreSQLProviderError(str(exc)) from exc

    def plan_admin_operation(self, request):
        compiled = self._compile_native_admin(request)
        payload = {
            'resource_kind': request['resource_kind'],
            'operation_id': request['operation_id'],
            'target_resource': copy.deepcopy(request.get('target_resource')),
            'draft': copy.deepcopy(request.get('draft') or {}),
            'route': self._native_admin_route(request),
            'statement': compiled['statement'],
            'read_only': compiled['read_only'],
            **{key: compiled[key] for key in ('returns_rows', 'post_statement', 'expected_sha256', 'server_file_operation') if key in compiled},
        }
        return {
            'command_preview': {
                'language': 'postgresql-sql',
                'statement': compiled['statement'],
                'provider_owned': True,
                **({'verification_statement': compiled['post_statement']} if 'post_statement' in compiled else {}),
            },
            'provider_payload': payload,
            'warnings': (['File paths refer to the database server host. Native function privileges and OS file access apply.'] +
                         (['Export can overwrite the selected file. SQL rollback does not undo server filesystem output.']
                          if compiled.get('server_file_operation') == 'export' else []))
                        if compiled.get('server_file_operation') else [],
            'receipt': {
                'provider_owned': True,
                'automatic_mutation_retry': False,
                'common_transaction_finality_inference': False,
            },
        }

    @_provider_serialized
    def apply_admin_operation(self, request):
        payload = request.get('provider_payload') or {}
        if not isinstance(payload, Mapping):
            raise PostgreSQLProviderError('provider plan is invalid')
        route = payload.get('route') or {}
        statement = _required_text(payload.get('statement'), 'statement')
        compiled = self._compile_native_admin(payload)
        expected = {'statement': statement, 'read_only': payload.get('read_only')}
        for key in ('returns_rows', 'post_statement', 'expected_sha256', 'server_file_operation'):
            if key in compiled:
                expected[key] = payload.get(key)
        if compiled != expected:
            raise PostgreSQLProviderError('Retained administrative statement changed')
        self.permissions.require('data_read' if compiled['read_only'] else 'administer')
        self.permissions.require('execute')
        database_id = _required_int(route, 'database_id')
        session = self.open_session({'route': route})
        state = self._sessions[session['session_id']]
        response = None
        committing = False
        file_export_dispatched = False
        try:
            self._ensure_native_connection(state)
            connection = state.connection
            if connection.transaction_status() != 0:
                raise PostgreSQLProviderError('Administrative connection must be idle')
            status, _ = native_control(connection.conn,
                'BEGIN READ ONLY' if compiled['read_only'] else 'BEGIN')
            if not status:
                raise PostgreSQLProviderError('Administrative transaction could not start')
            status, _ = native_control(connection.conn, 'SET LOCAL standard_conforming_strings = on')
            if not status:
                raise PostgreSQLProviderError('Administrative literal policy could not be established')
            status, identity = connection.execute_dict(
                'SELECT oid FROM pg_catalog.pg_database WHERE datname = current_database()')
            if not status or identity.get('rows') != [{'oid': database_id}]:
                raise PostgreSQLProviderError('Selected administrative database identity changed')
            file_export_dispatched = compiled.get('server_file_operation') == 'export'
            status, result = (connection.execute_dict(statement) if compiled['read_only'] or compiled.get('returns_rows')
                              else connection.execute_void(statement))
            if not status:
                raise PostgreSQLProviderError('PostgreSQL rejected the administrative statement')
            if compiled.get('server_file_operation'):
                rows = result.get('rows', [])
                if (len(rows) != 1 or
                        compiled['server_file_operation'] == 'export' and rows[0].get('native_result') != 1 or
                        compiled['server_file_operation'] == 'import' and
                        (type(rows[0].get('oid')) is not int or not 1 <= rows[0]['oid'] <= 2**32-1)):
                    raise PostgreSQLProviderError('Native PostgreSQL server-file acknowledgement is unavailable')
            if compiled.get('post_statement'):
                status, result = connection.execute_dict(compiled['post_statement'])
                if (not status or len(result.get('rows', [])) != 1 or
                        result['rows'][0].get('observed_sha256') != compiled['expected_sha256']):
                    raise PostgreSQLProviderError('PostgreSQL large-object write verification failed before commit')
            committing = True
            status, command = native_control(connection.conn, 'COMMIT')
            if not status or command != 'COMMIT':
                raise PostgreSQLProviderError('Administrative commit was not confirmed')
            response = {
                'provider_owned': True, 'native_outcome': 'observed',
                'transaction_outcome': 'committed', 'independent_attachment': True,
                'result': copy.deepcopy(result), 'automatic_retry_performed': False,
                'common_finality_inference': False,
            }
            if compiled.get('server_file_operation'):
                response['file_effects'] = {'host':'database-server','operation':compiled['server_file_operation'],
                    'native_function_acknowledged':True,'independent_file_verification':False,
                    'filesystem_write_rolled_back_by_sql':False}
        except Exception:
            if committing:
                state.uncertain = True
                raise PostgreSQLProviderError(
                    'PostgreSQL administrative commit outcome is unknown; do not replay' +
                    ('. Database-server file output may already exist and is not undone by SQL rollback'
                     if file_export_dispatched else '')) from None
            if file_export_dispatched:
                raise PostgreSQLProviderError('PostgreSQL server-file export outcome is unconfirmed; SQL rollback does not undo file output. Inspect the destination before retrying') from None
            raise
        finally:
            try:
                self.close_session(session)
            except Exception:
                if response is None:
                    if file_export_dispatched:
                        raise PostgreSQLProviderError('PostgreSQL server-file export outcome and connection release remain unconfirmed; SQL rollback does not undo file output. Inspect the destination before retrying') from None
                    raise PostgreSQLProviderError('Administrative connection release remains unconfirmed') from None
                response.update(release_status='unconfirmed',
                                release_pending_session_id=session['session_id'])
            else:
                if response is not None:
                    response['release_status'] = 'confirmed'
        return response

    def visual_admin_descriptor(self):
        """Describe PostgreSQL objects for the common administration UI."""
        descriptor = self._visual_admin.descriptor()
        descriptor['administration_surface'] = {
            'surface_id': 'pgadmin.preserved-postgresql-administration',
            'workflow': 'legacy_preserved',
            'object_dialogs': True,
            'editable_grid': True,
            'maintenance_tools': True,
            'provider_owned': True,
            'common_provider_reimplementation_required': False,
        }
        descriptor['concept_declarations'] = copy.deepcopy(
            POSTGRESQL_CONCEPT_DECLARATIONS
        )
        return enrich_engine_experience(descriptor)

    def validate_visual_admin(self, request):
        return self._visual_admin.validate(request)

    def plan_visual_admin(self, request):
        return self._visual_admin.plan(request)

    def apply_visual_admin(self, request):
        return self._visual_admin.apply(request)

    @staticmethod
    def semantic_model_descriptor():
        """Declare PostgreSQL semantic-query compilation explicitly."""
        return {
            'provider_id': PROVIDER_ID,
            'engine_id': 'postgresql',
            'model_family': 'relational',
            'execution_available': True,
            'language_profile': 'postgresql-sql',
            'compiler_kind': 'sql',
            'time_intelligence': {
                'operations': [
                    'as_of', 'range', 'period_to_date',
                    'period_comparison',
                ],
                'periods': [
                    'day', 'week', 'month', 'quarter', 'year',
                    'fiscal_quarter', 'fiscal_year',
                ],
            },
            'analytical_windows': {'operations': [
                'running_sum', 'moving_sum', 'moving_average', 'lag',
                'delta', 'percent_change', 'rank', 'dense_rank',
            ]},
            'materialization': 'provider_planned',
            'reason': None,
        }

    @staticmethod
    def compile_semantic_query(model, query):
        """Compile through the PostgreSQL provider-owned dialect choice."""
        from pgadmin.cdeadmin.semantic_models.compiler import compile_sql
        return compile_sql(model, query, {
            'language_profile': 'postgresql-sql',
            'quote_open': '"', 'quote_close': '"',
            'supports_rollup': True, 'limit_style': 'limit',
            'true_literal': 'TRUE', 'false_literal': 'FALSE',
            'time_operations': (
                'as_of', 'range', 'period_to_date', 'period_comparison',
            ),
            'window_operations': (
                'running_sum', 'moving_sum', 'moving_average', 'lag',
                'delta', 'percent_change', 'rank', 'dense_rank',
            ),
            'contract_complete': True,
        })

    def describe_semantics(self, request):
        """Implement semantic discovery without replacing PostgreSQL UI."""
        _mapping(request)
        return {
            'identity': self._identity(),
            'endpoint_id': self.context.endpoint_id,
            'resource_id': 'postgresql:semantic-model-descriptor',
            'identity_kind': 'provider-native-id',
            'resource_kind': 'semantic-model-descriptor',
            'model_family': 'relational',
            'display_name': 'PostgreSQL semantic model support',
            'parent_resource_id': None,
            'display_path': ['PostgreSQL', 'Semantic models'],
            'authority_path': ['postgresql', 'semantic-model-descriptor'],
            'is_virtual': True, 'generation': PROFILE_VERSION,
            'capability_ids': ['postgresql.semantic-query.execute'],
            'extensions': {
                'postgresql': self.semantic_model_descriptor(),
            },
        }

    def execute_analysis(self, request):
        """Compile and execute a semantic request through PostgreSQL."""
        payload = _mapping(request)
        compiled = self.compile_semantic_query(
            payload.get('semantic_model'), payload.get('semantic_query')
        )
        payload['source'] = compiled['source']
        payload['parameters'] = compiled.get('parameters', {})
        return self.execute(payload)

    def _identity(self) -> dict[str, str]:
        return {
            'contract_version': '1.0.0',
            'provider_id': PROVIDER_ID,
            'provider_version': PROVIDER_VERSION,
            'profile_id': PROFILE_ID,
            'profile_version': PROFILE_VERSION,
            'evidence_reference': EVIDENCE_REFERENCE,
        }

    def _diagnostic(
        self, code: str, message: str, severity: str = 'info',
        retryable: bool = False, details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            'identity': self._identity(),
            'diagnostic_id': str(uuid.uuid4()),
            'severity': severity,
            'code': code,
            'message': message,
            'retryable': retryable,
            'details': dict(details or {}),
            'extensions': {'postgresql': {'provider_owned': True}},
        }

    def get_legacy_driver(self, driver_type):
        if driver_type != LEGACY_DRIVER_TYPE:
            raise PostgreSQLProviderError(
                'PostgreSQL provider only preserves the psycopg3 driver'
            )
        return self._driver

    @staticmethod
    def _inspect_catalog_resource(binding, resource):
        return binding.instance.inspect_resource(resource)

    @staticmethod
    def _invoke_catalog_inspector(binding, resource, _payload):
        return binding.instance.inspect_resource(resource)

    @classmethod
    def resource_contributions(cls):
        """Describe PostgreSQL explorer behavior without common branching."""
        resource_kinds = (frozenset(POSTGRESQL_ADMIN_OPERATIONS)
                          | CATALOG_KINDS | CAPTURE_RESOURCE_KINDS)
        return {
            'inspectors': (
                ResourceInspectorContribution(
                    'postgresql.catalog.inspector',
                    resource_kinds,
                    cls._inspect_catalog_resource,
                ),
            ),
            'commands': (
                ResourceCommandContribution(
                    'postgresql.catalog.inspect',
                    'Inspect properties',
                    'postgresql.catalog.read',
                    resource_kinds,
                    mutation_class='read',
                    required_permission='data_read',
                    invoke=cls._invoke_catalog_inspector,
                ),
            ),
        }

    @staticmethod
    def _studio_open_session(binding, request):
        return binding.instance.open_session(request)

    @staticmethod
    def _studio_describe_transaction(binding, request):
        return binding.instance.describe_transaction(request)

    @staticmethod
    def _studio_control_transaction(binding, request):
        return binding.instance.control_transaction(request)

    @staticmethod
    def _studio_close_session(binding, request):
        return binding.instance.close_session(request)

    @staticmethod
    def _studio_execute(binding, request):
        return binding.instance.execute(request)

    @staticmethod
    def _studio_poll(binding, request):
        result = binding.instance.describe_result(request)
        operation = binding.instance.get_operation(request)
        return operation, result

    @staticmethod
    def _studio_cancel(binding, request):
        return binding.instance.cancel(request)

    @staticmethod
    def _studio_complete(binding, request):
        provider = binding.instance
        with provider._state_lock:
            state = provider._require_idle_session(request.get('session_id'))
            with state.lock:
                completions = provider.complete(request)
                context = provider._editor_context(state, request.get('full_source', ''))
        return {'completions': dict(list(completions.items())[:1000]), 'editor_context': {
            'context': context, 'truncated': len(completions) > 1000,
            'coverage': 'Authorized PostgreSQL session completion', 'completion_count': len(completions)}}

    @classmethod
    def data_studio_contributions(cls):
        """Expose the preserved PostgreSQL Query Tool through common ports."""
        profiles = frozenset({'postgresql-sql'})
        return {
            'languages': (
                LanguageContribution(
                    'postgresql-sql',
                    'PostgreSQL SQL',
                    'text/x-pgsql',
                    frozenset({'relational'}),
                    parameter_shape='object-or-array',
                    dialect_contract_id='postgresql.shared-explain.18.3.v1',
                    dialect_evidence=(
                        'postgresql-18.3-explain-sgml-43bc7ee2b009',
                        'shared-editor-native-plan-estimate-analyze-bindings',
                    ),
                    query_plan_templates=(
                        ('PostgreSQL estimated plan',
                         'EXPLAIN (FORMAT JSON) {source}'),
                        ('Explain Analyze (executes statement)',
                         'EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {source}'),
                    ),
                ),
            ),
            'completions': (
                CompletionContribution(
                    'postgresql.query-tool.completion',
                    profiles,
                    cls._studio_complete,
                ),
            ),
            'sessions': (
                SessionContribution(
                    'postgresql.query-tool.session',
                    profiles,
                    cls._studio_open_session,
                    cls._studio_describe_transaction,
                    frozenset({'commit', 'rollback',
                               'autocommit_on', 'autocommit_off'}),
                    cls._studio_control_transaction,
                    cls._studio_close_session,
                ),
            ),
            'executions': (
                ExecutionContribution(
                    'postgresql.query-tool.execution',
                    profiles,
                    cls._studio_execute,
                    cls._studio_poll,
                    cls._studio_cancel,
                ),
            ),
        }

    @staticmethod
    def _describe_tabular_result(_binding, result):
        extensions = result.get('extensions', {}).get('postgresql', {})
        rows = extensions.get('rows')
        if rows is None:
            rows = []
        if not isinstance(rows, list):
            raise PostgreSQLProviderError(
                'PostgreSQL tabular result rows must be an array'
            )
        return {
            'descriptor_version': '1.0.0',
            'capability_id': TABULAR_RENDER_CAPABILITY,
            'records': copy.deepcopy(rows),
            'limits': {
                'max_records': 10000,
                'max_page_size': 500,
                'max_record_bytes': 256 * 1024,
                'max_descriptor_bytes': 4 * 1024 * 1024,
            },
            'sampling': {'mode': 'head', 'limit': min(
                max(len(rows), 1), 10000
            )},
            'export_policy': {
                'enabled': True,
                'formats': ['csv', 'json', 'xlsx', 'svg', 'pdf', 'ddn'],
                'max_records': 10000,
                'max_bytes': 8 * 1024 * 1024,
                'redact_keys': [],
            },
            'worker_policy': {
                'required': False,
                'timeout_seconds': 2.0,
            },
            'renderer_id': 'cdeadmin.result.tabular.legacy-grid',
            'component_reference': 'SchemaView/DataGridView',
        }

    @classmethod
    def result_contributions(cls):
        """Normalize PostgreSQL rows without copying the production grid."""
        return {
            'adapters': (
                ResultAdapterContribution(
                    'postgresql.result.tabular.adapter',
                    frozenset({'tabular'}),
                    TABULAR_RENDER_CAPABILITY,
                    cls._describe_tabular_result,
                ),
            ),
        }

    def query_tool_connection_manager(self, server_id, legacy_manager):
        """Return the provider-owned manager for the preserved Query Tool."""
        # get_driver() has already resolved this provider and obtained the
        # manager. Do not repeat the lookup: the legacy call owns exception
        # timing and some manager registries expose stateful retrieval.
        if not isinstance(server_id, int):
            raise PostgreSQLProviderError(
                'PostgreSQL server identity must be an integer'
            )
        return legacy_manager

    @staticmethod
    def query_tool_execute_async(connection, source, server_cursor=False):
        """Preserve psycopg3 asynchronous Query Tool execution."""
        return connection.execute_async(
            source, server_cursor=server_cursor
        )

    @staticmethod
    def query_tool_poll(connection, **kwargs):
        """Preserve psycopg3 Query Tool result polling."""
        return connection.poll(**kwargs)

    @staticmethod
    def query_tool_fetch(connection, *args, **kwargs):
        """Preserve psycopg3 Query Tool result-window fetching."""
        return connection.async_fetchmany_2darray(*args, **kwargs)

    def validate_endpoint(self, request):
        payload = _mapping(request)
        try:
            route = payload.get('route', {})
            _required_int(route, 'server_id')
        except PostgreSQLProviderError as exc:
            return self._diagnostic(
                'CDE_PG_ENDPOINT_INVALID', str(exc), severity='error'
            )
        return self._diagnostic(
            'CDE_PG_ENDPOINT_VALID',
            'PostgreSQL endpoint is structurally valid',
        )

    def discover_endpoint(self, request):
        payload = copy.deepcopy(_mapping(request))
        route = payload.get('route', {})
        server_id = _required_int(route, 'server_id')
        manager = self._driver.connection_manager(server_id)
        if manager is None:
            raise PostgreSQLProviderError('PostgreSQL server is unavailable')
        native_version = manager.version
        # The preserved driver exposes libpq's server_version integer;
        # template selection must retain that integer, but profile identity
        # uses PostgreSQL's public major.minor release notation.
        runtime_version = (
            f'{native_version // 10000}.{native_version % 10000}'
            if isinstance(native_version, int) and native_version >= 100000
            else str(native_version)
        )
        driver_version = str(self._driver.version())
        if runtime_version != PROFILE_VERSION:
            raise PostgreSQLProviderError(
                'PostgreSQL runtime does not match exact profile 18.3'
            )
        if driver_version not in APPROVED_DRIVER_VERSIONS:
            raise PostgreSQLProviderError(
                'psycopg runtime is outside the approved exact versions'
            )
        payload['identity'] = self._identity()
        payload['verified_runtime'] = {
            'engine': 'PostgreSQL',
            'server_version': runtime_version,
            'driver': LEGACY_DRIVER_TYPE,
            'driver_version': driver_version,
            'verification_state': 'verified',
        }
        return payload

    def list_resources(self, request):
        self.permissions.require('data_read', 'resource')
        payload = _mapping(request)
        extension = _extension(payload)
        route = payload.get('route') or {}
        if payload.get('resource_kind') == 'server' and route.get('database_id') is not None:
            return self._captured_resources(payload, route)
        catalog_kind = extension.get('child_kind')
        rows = self._catalog.read(catalog_kind, extension)
        return [
            self._resource(payload, extension, catalog_kind, row)
            for row in rows
        ]

    def inspect_resource(self, request):
        self.permissions.require('data_read', 'resource')
        payload = _mapping(request)
        extension = _extension(payload)
        if extension.get('capture_identity'):
            route = {key: extension[key] for key in ('server_id', 'database_id')}
            parent = {'resource_id': payload.get('parent_resource_id'),
                      'authority_path': payload.get('authority_path', [])[:-2]}
            rows = [row for row in self._captured_resources(parent, route)
                    if row['resource_id'] == payload['resource_id']]
            if len(rows) != 1:
                raise PostgreSQLProviderError('Selected native catalog object no longer exists')
            return rows[0]
        catalog_kind = extension.get('catalog_kind')
        object_id = _required_int(extension, 'object_id')
        rows = self._catalog.read(catalog_kind, extension, object_id)
        if len(rows) != 1:
            raise PostgreSQLProviderError(
                'PostgreSQL resource identity did not resolve exactly once'
            )
        return self._resource(payload, extension, catalog_kind, rows[0])

    def _captured_resources(self, parent, route):
        capture = self.capture_catalog(route, include_system=False)
        result = []
        for item in capture['resources']:
            native = copy.deepcopy(item['native'])
            native['name'] = item['display_name']
            raw = native.get('catalog_row', {})
            if item['resource_kind'] == 'aggregate':
                native['identity_arguments'] = raw['identity_arguments']
            if item['resource_kind'] == 'operator':
                native.update(left_type=raw['left_type_identity'], right_type=raw['right_type_identity'])
            if item['resource_kind'] in {'operator-class', 'operator-family'}:
                native['index_method'] = raw['index_method_name']
            if item['resource_kind'] == 'transform':
                native.update(data_type=raw['data_type_identity'], language=raw['language_name'],
                              name=raw['data_type_identity'] + ' / ' + raw['language_name'])
            result.append({
                'identity': self._identity(), 'endpoint_id': self.context.endpoint_id,
                'resource_id': item['resource_id'], 'identity_kind': 'postgresql-catalog-oid',
                'resource_kind': {'policy': 'row-policy'}.get(
                    item['resource_kind'], item['resource_kind']),
                'model_family': 'relational',
                'display_name': item['display_name'], 'display_path': item['display_path'],
                'parent_resource_id': parent.get('resource_id'),
                'authority_path': list(parent.get('authority_path', [])) + [native['catalog'], str(native['oid'])],
                'is_virtual': False, 'generation': parent.get('generation', self.context.cache_namespace),
                'capability_ids': ['postgresql.catalog.read'],
                'extensions': {'postgresql': {
                    'server_id': route['server_id'], 'database_id': route['database_id'],
                    'catalog_kind': item['resource_kind'], 'object_id': native['oid'],
                    'capture_identity': True, 'native': normalize_resource_properties(native)}}})
        return result

    def _resource(self, parent, route, catalog_kind, row):
        id_field = 'did' if catalog_kind == 'database' else 'oid'
        object_id = row.get(id_field)
        name = row.get('name')
        if object_id is None or not isinstance(name, str):
            raise PostgreSQLProviderError(
                'PostgreSQL catalog row lacks provider authority identity'
            )
        authority_path = list(parent.get('authority_path', []))
        authority_path.extend((catalog_kind, str(object_id)))
        display_path = list(parent.get('display_path', []))
        display_path.append(name)
        resource_id = 'postgresql:' + '/'.join(authority_path)
        resource_route = {
            key: route[key]
            for key in ('server_id', 'database_id', 'schema_id')
            if key in route
        }
        resource_route.update({
            'catalog_kind': catalog_kind,
            'object_id': object_id,
            'legacy_metadata': dict(row),
            'native': normalize_resource_properties({
                **{key: row[key] for key in ('schema', 'name', 'index_method', 'data_type', 'language', 'left_type', 'right_type', 'identity_arguments', 'sql_identity', 'oid') if key in row},
                'catalog_metadata': dict(row),
            }),
        })
        return {
            'identity': self._identity(),
            'endpoint_id': self.context.endpoint_id,
            'resource_id': resource_id,
            'identity_kind': 'postgresql-oid',
            'resource_kind': catalog_kind,
            'model_family': 'relational',
            'display_name': name,
            'parent_resource_id': parent.get('resource_id'),
            'display_path': display_path,
            'authority_path': authority_path,
            'is_virtual': False,
            'generation': parent.get(
                'generation', self.context.cache_namespace
            ),
            'capability_ids': ['postgresql.catalog.read'],
            'extensions': {'postgresql': resource_route},
        }

    @_provider_serialized
    def open_session(self, request, *, _resolved_database=None):
        self.permissions.require('network')
        if self._closed:
            raise PostgreSQLProviderError('PostgreSQL provider is closed')
        payload = _mapping(request)
        route = payload.get('route', {})
        server_id = _required_int(route, 'server_id')
        database_id = route.get('database_id')
        if database_id is not None:
            database_id = _required_int(route, 'database_id')
            if not 1 <= database_id <= 4294967295:
                raise PostgreSQLProviderError('Selected database OID is invalid')
        principal = route.get('principal_reference', '')
        if principal.startswith('worker:'):
            owner_id = _required_int(route, 'owner_id')
            manager = self._driver.delegated_connection_manager(
                server_id, owner_id,
                route.get('source_kind', 'server'),
            )
        else:
            manager = self._driver.connection_manager(server_id)
        connection_id = str(uuid.uuid4())
        selected_database = {}
        if _resolved_database is not None:
            if not isinstance(_resolved_database, str) or not _resolved_database or '\x00' in _resolved_database or database_id is None:
                raise PostgreSQLProviderError('Exact resolved database name and OID are required')
            selected_database['database'] = _resolved_database
        elif principal.startswith('worker:') and database_id is not None:
            selected_database['database'] = self._resolve_delegated_database(route, database_id)
        connection = manager.connection(
            did=database_id, conn_id=connection_id, auto_reconnect=False,
            async_=False, **selected_database
        )
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = _SessionState(
            server_id, database_id, connection_id, connection, manager
        )
        try:
            self._connect_delegated_route(connection, manager, route)
            self._sessions[session_id].attached = connection.connected()
            if selected_database:
                self._ensure_native_connection(self._sessions[session_id])
                status, result = connection.execute_dict(
                    'SELECT oid FROM pg_catalog.pg_database WHERE datname = current_database()')
                if (not status or len(result.get('rows', [])) != 1 or
                        result['rows'][0]['oid'] != database_id):
                    raise PostgreSQLProviderError('Selected database identity changed')
        except Exception:
            self._sessions[session_id].uncertain = True
            manager.release(conn_id=connection_id)
            self._sessions.pop(session_id, None)
            raise PostgreSQLProviderError(
                'PostgreSQL delegated session could not be opened') from None
        return {
            'identity': self._identity(),
            'session_id': session_id,
            'endpoint_id': self.context.endpoint_id,
            'route_id': str(route.get('route_id', 'legacy-pgadmin-server')),
            'principal_reference': str(
                route.get('principal_reference', 'pgadmin-session')
            ),
            'language_profile': 'postgresql-sql',
            'transaction_model': 'postgresql-native',
            'provider_state': {
                'server_id': server_id,
                'database_id': database_id,
                'connection_id': connection_id,
            },
            'occurrence_id': self.context.session_namespace,
            'limits': {},
            'extensions': {'postgresql': {'provider_owned': True}},
        }

    def capture_catalog(self, route, *, include_system=False):
        """Read native metadata on a private, transaction-bounded attachment."""
        from .catalog_capture import capture
        self.permissions.require('data_read', 'resource')
        opened = self.open_session({'route': route})
        try:
            state = self._sessions[opened['session_id']]
            with state.lock:
                self._ensure_native_connection(state)
                return capture(state.connection.conn, route.get('database_id'),
                               include_system=include_system)
        finally:
            self.close_session(opened)

    @_session_serialized
    def capture_session_catalog(self, request):
        self.permissions.require('data_read', 'resource')
        payload = _mapping(request)
        if payload.get('language_profile') != 'postgresql-sql' or type(payload.get('include_system', False)) is not bool:
            raise PostgreSQLProviderError('Invalid PostgreSQL session catalog selection')
        state = self._require_idle_session(payload.get('session_id'))
        self._ensure_native_connection(state)
        from .session_catalog import observe
        try:
            return observe(state, include_system=payload.get('include_system', False))
        except ValueError as error:
            raise PostgreSQLProviderError(str(error)) from None
        except Exception:
            if state.connection.conn.closed or state.connection.conn.broken:
                state.uncertain = True
            raise PostgreSQLProviderError('Session catalog capture failed; ' +
                ('cleanup is unconfirmed, close this session without replay' if state.uncertain else
                 'pending work and session settings were preserved')) from None

    def _resolve_delegated_database(self, route, database_id):
        # A fresh delegated manager has no interactive db_info cache. Resolve
        # through its own authenticated attachment, never a guessed DB name.
        bootstrap = self.open_session({'route': {
            key: value for key, value in route.items() if key != 'database_id'}})
        try:
            connection = self._sessions[bootstrap['session_id']].connection
            status, result = connection.execute_dict(
                'SELECT datname FROM pg_catalog.pg_database '
                'WHERE oid = %s AND datallowconn', (database_id,))
            rows = result.get('rows', []) if status else []
            if len(rows) != 1 or not isinstance(rows[0].get('datname'), str):
                raise PostgreSQLProviderError('Selected database is unavailable')
            return rows[0]['datname']
        finally:
            self.close_session(bootstrap)

    def _connect_delegated_route(self, connection, manager, route):
        """Connect a worker route without synthesizing an interactive user."""
        references = dict(route.get('credential_references', {}))
        primary = route.get('credential_reference_id')
        primary_kind = route.get('credential_kind', 'database_password')
        if primary is not None:
            references.setdefault(primary_kind, primary)
        if not references:
            return
        unsupported = set(references).difference({
            'database_password', 'tunnel_password',
        })
        if unsupported:
            raise PostgreSQLProviderError(
                'PostgreSQL delegated credential kind is unsupported'
            )
        principal = route.get('principal_reference')
        if not isinstance(principal, str) or not principal.startswith(
                'worker:'):
            raise PostgreSQLProviderError(
                'PostgreSQL delegated route principal is invalid'
            )
        values = {}
        with ExitStack() as stack:
            for kind, reference_id in references.items():
                lease = stack.enter_context(self.permissions.acquire_secret(
                    reference_id, principal, 'connect', kind
                ))
                values[kind] = lease.use(
                    lambda value: bytes(value).decode('utf-8')
                )
            status, error = connection.connect(
                user=manager.user,
                password=values.get('database_password'),
                tunnel_password=values.get('tunnel_password', ''),
            )
            values.clear()
        if not status:
            raise PostgreSQLProviderError(
                'PostgreSQL delegated connection failed'
            )

    def source_tooling(self, language_profile):
        if language_profile != 'postgresql-sql':
            raise PostgreSQLProviderError('PostgreSQL SQL language binding required')
        return {'validation_authority': 'postgresql-offline-grammar',
                'native_validation_available': True, 'nonexecuting': True,
                'session_catalog': True,
                'parser_binding': 'pglast 8.5; PostgreSQL 18.6; native options revision 2'}

    @_session_serialized
    def validate_source_without_execution(self, request):
        from .language import analyze
        payload = _mapping(request)
        if payload.get('language_profile') != 'postgresql-sql':
            raise PostgreSQLProviderError('PostgreSQL SQL language binding required')
        state = self._require_idle_session(payload.get('session_id'))
        self._ensure_native_connection(state)
        connection = state.connection.conn
        context = self._editor_context(state, payload.get('source'))
        result = analyze(payload.get('source'), script=payload.get('script', False),
                         standard_strings=context['standard_conforming_strings'],
                         backslash_quote=context['backslash_quote'])
        result['server_version'] = connection.info.server_version
        return result

    @staticmethod
    def _editor_context(state, source):
        from .editor_context import observe
        try:
            return observe(state)
        except RuntimeError as error:
            raise PostgreSQLProviderError(str(error)) from None

    def _require_idle_session(self, session_id):
        state = self._sessions.get(session_id)
        if state is None:
            raise PostgreSQLProviderError('PostgreSQL session is unavailable')
        if state.uncertain:
            raise PostgreSQLProviderError(
                'PostgreSQL connection state is unknown; close this session')
        if any(op.session_id == session_id and not op.operation['terminal']
               for op in self._operations.values()):
            raise PostgreSQLProviderError(
                'PostgreSQL session execution is active')
        return state

    @staticmethod
    def _ensure_native_connection(state):
        if not state.connection.connected():
            if state.attached:
                state.uncertain = True
                raise PostgreSQLProviderError(
                    'PostgreSQL connection was lost; do not replay')
            try:
                status, _detail = state.connection.connect()
            except Exception:
                raise PostgreSQLProviderError(
                    'PostgreSQL connection failed') from None
            if not status:
                raise PostgreSQLProviderError('PostgreSQL connection failed')
        state.attached = True

    @_session_serialized
    def describe_transaction(self, request):
        payload = _mapping(request)
        session_id = payload.get('session_id')
        state = self._sessions.get(session_id)
        if state is None:
            raise PostgreSQLProviderError('PostgreSQL session is unavailable')
        if not state.uncertain:
            self._ensure_native_connection(state)
        return {
            'identity': self._identity(),
            'session_id': session_id,
            'transaction_model': 'postgresql-native',
            'provider_payload': {
                'transaction_status': (None if state.uncertain else
                                       state.connection.transaction_status()),
                'autocommit': (None if state.uncertain else
                               getattr(state.connection.conn, 'autocommit', None)),
                'session_reuse_blocked': state.uncertain,
                'interpretation': 'PostgreSQL provider-owned opaque value',
            },
            'authority_reference': 'provider:org.pgadmin.postgresql',
            'extensions': {},
        }

    @_session_serialized
    def control_transaction(self, request):
        """Execute native PostgreSQL transaction control on this session."""
        payload = _mapping(request)
        state = self._sessions.get(payload.get('session_id'))
        if state is None:
            raise PostgreSQLProviderError('PostgreSQL session is unavailable')
        action = payload.get('action')
        statements = {'commit': 'COMMIT;', 'rollback': 'ROLLBACK;'}
        policies = {'autocommit_on': True, 'autocommit_off': False}
        if action not in statements and action not in policies:
            raise PostgreSQLProviderError(
                'PostgreSQL transaction action is unavailable'
            )
        self.permissions.require('execute')
        with state.lock:
            self._require_idle_session(payload.get('session_id'))
            self._ensure_native_connection(state)
            if action in policies:
                native = state.connection.conn
                desired = policies[action]
                current = getattr(native, 'autocommit', None)
                if not isinstance(current, bool):
                    raise PostgreSQLProviderError(
                        'PostgreSQL autocommit policy is unavailable')
                if desired != current:
                    if state.connection.transaction_status() != 0:
                        raise PostgreSQLProviderError(
                            'Commit or roll back the pending transaction '
                            'before changing autocommit')
                    try:
                        native.autocommit = desired
                    except Exception:
                        if not state.connection.connected():
                            state.uncertain = True
                        raise PostgreSQLProviderError(
                            'PostgreSQL autocommit change was not acknowledged; '
                            'refresh transaction state before executing') from None
                return self.describe_transaction(payload)
            try:
                status, _detail = native_control(
                    state.connection.conn, statements[action])
            except Exception:
                state.uncertain = True
                raise PostgreSQLProviderError(
                    'PostgreSQL transaction outcome is unknown; '
                    'do not replay') from None
            if not status:
                state.uncertain = True
                raise PostgreSQLProviderError(
                    'PostgreSQL transaction outcome is unknown; do not replay')
        observation = self.describe_transaction({
            'session_id': payload.get('session_id'),
        })
        observation['provider_payload']['command_status'] = _detail
        return observation

    @_session_serialized
    def close_session(self, request):
        """Roll back and release one retained PostgreSQL connection."""
        payload = _mapping(request)
        session_id = payload.get('session_id')
        state = self._sessions.get(session_id)
        if state is None:
            raise PostgreSQLProviderError('PostgreSQL session is unavailable')
        with state.lock:
            for op in self._operations.values():
                if op.session_id != session_id or op.operation['terminal']:
                    continue
                token = op.execution
                try:
                    token.cancel()
                except Exception:
                    state.uncertain = True
                token.discard.set()
                token.worker.join(timeout=5)
                if not token.finished.is_set():
                    raise PostgreSQLProviderError(
                        'PostgreSQL execution still owns its connection')
                state.uncertain |= token.uncertain
                # Keep the final native observation after release for polling.
                while not op.operation['terminal']:
                    self.describe_result(op.operation)
            rollback_status = False
            rollback_requested = not state.uncertain and state.attached
            try:
                if rollback_requested:
                    rollback_status, _detail = native_control(
                        state.connection.conn, 'ROLLBACK;')
                    if not rollback_status:
                        state.uncertain = True
            except Exception:
                state.uncertain = True
            finally:
                try:
                    state.manager.release(conn_id=state.connection_id)
                except Exception:
                    state.uncertain = True
                    raise PostgreSQLProviderError(
                        'PostgreSQL connection release failed') from None
            self._sessions.pop(session_id, None)
            self._completion_adapters.pop(session_id, None)
        return {
            'session_id': session_id,
            'provider_closed': True,
            'provider_payload': {
                'rollback_requested': rollback_requested,
                'outcome_unknown': state.uncertain,
                'rollback_driver_response': bool(rollback_status),
                'connection_released': True,
            },
            'provider_finality_authority': True,
            'common_finality_interpreted': False,
        }

    @_session_serialized
    def complete(self, request):
        """Use pgAdmin's existing PostgreSQL completion implementation."""
        payload = _mapping(request)
        session_id = payload.get('session_id')
        state = self._sessions.get(session_id)
        if state is None:
            raise PostgreSQLProviderError('PostgreSQL session is unavailable')
        self._require_idle_session(session_id)
        self._ensure_native_connection(state)
        from .editor_context import read_scope
        from psycopg.pq import TransactionStatus
        try:
            with read_scope(state):
                adapter = self._completion_adapters.get(session_id)
                if adapter is None:
                    # Import lazily so provider registration does not make the legacy
                    # Query Tool completion dependency part of common app startup.
                    from pgadmin.utils.sqlautocomplete.autocomplete import (
                        SQLAutoComplete,
                    )
                    adapter = SQLAutoComplete(
                        sid=state.server_id,
                        did=state.database_id,
                        conn=state.connection,
                        manager=state.manager,
                    )
                    # Rebuild native metadata for each request. The legacy adapter
                    # extends cached objects and can retain dropped objects, revoked
                    # visibility or a previous search_path when reused indefinitely.
                    # Session ownership remains cached; catalog suggestions do not.
                result = adapter.get_completions(
                    str(payload.get('full_source', '')),
                    str(payload.get('source_before_cursor', '')),
                )
                if state.connection.conn.info.transaction_status != TransactionStatus.INTRANS:
                    raise PostgreSQLProviderError('Native completion metadata is unavailable')
                return result
        except (ValueError, RuntimeError) as error:
            raise PostgreSQLProviderError(str(error)) from None

    @_session_serialized
    def execute(self, request):
        self.permissions.require('execute')
        payload = _mapping(request)
        session_id = payload.get('session_id')
        state = self._sessions.get(session_id)
        if state is None:
            raise PostgreSQLProviderError('PostgreSQL session is unavailable')
        source = payload.get('source')
        if not isinstance(source, str) or not source.strip():
            raise PostgreSQLProviderError(
                'PostgreSQL query source is required')
        bound = native_parameters(payload.get('parameters'))
        with state.lock:
            self._require_idle_session(session_id)
            self._ensure_native_connection(state)
            if payload.get('output_policy', {}).get('postgresql_plan'):
                from .execution import validate_plan
                validate_plan(state.connection.conn, source, bound)
            execution = Execution(state.connection.conn, source, bound)
            return self._start_execution(payload, session_id, state, execution)

    def _start_execution(self, payload, session_id, state, execution):
        operation_id = str(uuid.uuid4())
        operation = {
            'identity': self._identity(),
            'operation_id': operation_id,
            'operation_kind': 'postgresql-query',
            'target_resource_id': None,
            'capability_id': 'postgresql.query.execute',
            'risk_class': 'unknown',
            'provider_state': {
                'session_id': session_id,
                'accepted': True,
            },
            'terminal': False,
            'provider_receipt': None,
            'extensions': {'postgresql': {'provider_owned': True}},
        }
        self._operations[operation_id] = _OperationState(
            operation, payload.get('execution_id', ''), session_id,
            state.connection, execution=execution,
        )
        try:
            execution.start()
        except Exception:
            self._operations.pop(operation_id, None)
            raise PostgreSQLProviderError(
                'PostgreSQL execution worker could not start') from None
        return copy.deepcopy(operation)

    @_session_serialized
    def cancel(self, request):
        self.permissions.require('execute')
        payload = _mapping(request)
        state = self._operation(payload.get('operation_id'))
        if state.operation['terminal']:
            return copy.deepcopy(state.operation)
        try:
            status = state.execution.cancel()
        except Exception:
            self._sessions[state.session_id].uncertain = True
            raise PostgreSQLProviderError(
                'PostgreSQL cancellation state is unknown') from None
        state.operation['provider_receipt'] = {
            'cancel_request_accepted': bool(status),
            'detail': None,
            'outcome': 'pending-provider-observation',
        }
        return copy.deepcopy(state.operation)

    def script_statement_outcome(self, occurrence):
        from pgadmin.cdeadmin.data_studio.scripts import retained_outcome
        return retained_outcome(occurrence, 'postgresql')

    @_session_serialized
    def describe_result(self, request):
        payload = _mapping(request)
        state = self._operation(payload.get('operation_id'))
        if state.result is not None:
            return copy.deepcopy(state.result)
        page = state.execution.poll()
        complete = page.pop('complete')
        if page.get('session_reuse_blocked'):
            self._sessions[state.session_id].uncertain = True
        result = {
            'identity': self._identity(),
            'result_id': str(uuid.uuid4()),
            'execution_id': state.execution_id,
            'result_kind': 'tabular',
            'schema': {
                'columns': page.pop('columns'),
            },
            'stream_reference': None,
            'complete': complete,
            'continuation': (
                None if complete else state.operation['operation_id']
            ),
            'extensions': {
                'postgresql': {
                    **page,
                    'payload': copy.deepcopy(page),
                    'provider_owned': True,
                }
            },
        }
        if complete:
            state.result = copy.deepcopy(result)
            state.operation['terminal'] = True
        return result

    def select_renderer(self, request):
        """Select the preserved pgAdmin grid for PostgreSQL tabular rows."""
        payload = _mapping(request)
        if payload.get('result_kind') != 'tabular':
            raise PostgreSQLProviderError(
                'PostgreSQL provider has no renderer for this result kind'
            )
        return {
            'identity': self._identity(),
            'endpoint_id': self.context.endpoint_id,
            'resource_id': 'postgresql:renderer:legacy-data-grid',
            'identity_kind': 'provider-renderer-id',
            'resource_kind': 'result-renderer',
            'model_family': 'relational',
            'display_name': 'PostgreSQL tabular data grid',
            'parent_resource_id': None,
            'display_path': ['PostgreSQL', 'Result renderers', 'Data grid'],
            'authority_path': [
                'postgresql', 'result-renderer', 'legacy-data-grid'
            ],
            'is_virtual': True,
            'generation': self.context.cache_namespace,
            'capability_ids': [TABULAR_RENDER_CAPABILITY],
            'extensions': {
                'postgresql': {
                    'component_reference': 'SchemaView/DataGridView',
                    'provider_owned': True,
                },
            },
        }

    def translate_diagnostic(self, request):
        payload = _mapping(request)
        return self._diagnostic(
            str(payload.get('code', 'CDE_PG_DIAGNOSTIC')),
            str(payload.get('message', 'PostgreSQL provider diagnostic')),
            severity=str(payload.get('severity', 'unknown')),
            retryable=bool(payload.get('retryable', False)),
            details=payload.get('details', {}),
        )

    def get_operation(self, request):
        payload = _mapping(request)
        return copy.deepcopy(
            self._operation(payload.get('operation_id')).operation
        )

    def list_tools(self, request):
        _mapping(request)
        return [
            {
                'identity': self._identity(),
                'endpoint_id': self.context.endpoint_id,
                'resource_id': f'postgresql-tool:{tool_id}',
                'identity_kind': 'provider-tool-id',
                'resource_kind': 'tool',
                'model_family': 'relational',
                'display_name': tool_id,
                'parent_resource_id': None,
                'display_path': [tool_id],
                'authority_path': ['postgresql', 'tool', tool_id],
                'is_virtual': True,
                'generation': self.context.cache_namespace,
                'capability_ids': [],
                'extensions': {
                    'postgresql': {
                        'disposition': disposition,
                        'ownership': 'provider-local',
                        'common_service': False,
                    }
                },
            }
            for tool_id, disposition in TOOL_DISPOSITIONS.items()
        ]

    def _operation(self, operation_id):
        try:
            return self._operations[operation_id]
        except KeyError as exc:
            raise PostgreSQLProviderError(
                'PostgreSQL operation is unavailable'
            ) from exc

    @contextmanager
    def profile_change_guard(self):
        """Keep routing/credentials alive until explicitly owned work is closed."""
        with self._state_lock:
            if self._sessions:
                raise PostgreSQLProviderError('Close PostgreSQL SQL sessions before disconnecting')
            yield

    def release_for_profile_change(self):
        self.close()

    @_provider_serialized
    def close(self):
        """Release owned sessions; retain any failed cleanup for retry."""
        self._closed = True
        failures = []
        for session_id in list(self._sessions):
            try:
                self.close_session({'session_id': session_id})
            except Exception as exc:
                failures.append(type(exc).__name__)
        if failures:
            raise PostgreSQLProviderError(
                'PostgreSQL session cleanup is incomplete')
        self._operations.clear()
        self._completion_adapters.clear()


def create_provider(context, permissions):
    """Create one endpoint-isolated PostgreSQL provider instance."""
    return PostgreSQLProvider(context, permissions)

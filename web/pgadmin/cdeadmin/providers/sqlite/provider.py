"""SQLite 3.53.0 exact-version native provider."""

import json
import os
import re
import sqlite3
import stat
import uuid
from collections.abc import Mapping
from importlib import resources as package_resources

from pgadmin.cdeadmin.sdk import (
    ActualEnginePilotProvider,
    PilotProfile,
    RelationalClientConfig,
    RelationalClientError,
)
from .driver import SQLiteClient, SQLiteConnection
from ..native_editor import NativeEditorProvider
from .values import text as native_text
from .modules import family as virtual_family,declaration as module_declaration
from .backup import database_operation as _sqlite_database_operation
from ..relational_admin import (
    RelationalAdministration,
    RelationalAdminDialect,
)
from ..embedded_route import contained_database, sqlite_arguments


PROFILE = PilotProfile(
    'org.cdeadmin.sqlite', 'sqlite-native', 'sqlite', 'SQLite', '3.53.0',
    'embedded_sqlite', 'relational', 'sqlite-sql', 'SQLite SQL',
    'sqlite-native-transaction', 'tabular',
    ('database', 'attached-database', 'table', 'column', 'view', 'index',
     'constraint', 'trigger', 'virtual-table', 'fts-table', 'pragma',
     'extension', 'metric', 'native-function', 'collation', 'compile-option'),
    ('sqlite-shell', 'backup', 'integrity-check', 'vacuum'),
    ('embedded_runtime', 'filesystem'),
    semantic_sql_dialect={
        'contract_complete': True,
        'language_profile': 'sqlite-sql', 'quote_open': '"',
        'quote_close': '"',
        'supports_rollup': False,
        'limit_style': 'limit',
        'true_literal': '1', 'false_literal': '0',
        'percent_change_numerator_cast': 'REAL',
        'time_operations': (
            'as_of', 'range', 'period_to_date', 'period_comparison',
        ),
        'window_operations': (
            'running_sum', 'moving_sum', 'moving_average', 'lag', 'delta',
            'percent_change', 'rank', 'dense_rank',
        ),
    },
    parameter_shape='object-or-array',
    parameter_hint=('Named :name or positional ? bindings; '
                    'exact integer and base64 envelopes.'),
    dialect_contract_id='sqlite.dialect.3.53.0.v1',
    dialect_evidence=(
        'sqlite-3.53.0-source-grammar',
        'sqlite-3.53.0-task-live-execution',
    ),
    dialect_contract_file='sqlite_dialect_3_53_0.json',
    metrics_contract_file='sqlite_metrics_3_53_0.json',
    query_plan_templates=(
        ('SQLite query plan', 'EXPLAIN QUERY PLAN {source}'),
        ('SQLite virtual-machine bytecode', 'EXPLAIN {source}'),
    ),
)


class SQLiteAdministration(RelationalAdministration):
    def _form(self, kind, operation):
        from .virtual_tables import KINDS, form
        if kind in KINDS and operation == 'create':
            return form(self._field, kind)
        return super()._form(kind, operation)

    def _normalize_draft(self, kind, operation, draft):
        from .virtual_tables import KINDS
        if kind in KINDS and operation == 'create' and isinstance(draft, Mapping):
            draft = dict(draft)
            if 'options' in draft and not isinstance(draft['options'], Mapping):
                raise RelationalClientError('create options must be an object')
            if 'module_options' in draft:
                options = draft.get('options', {})
                if not isinstance(options, Mapping):
                    raise RelationalClientError('create options must be an object')
                draft['options'] = {**options, 'module_options': draft.pop('module_options')}
        return super()._normalize_draft(kind, operation, draft)

    def validate(self, request):
        from .virtual_tables import KINDS
        result = super().validate(request)
        if request.get('resource_kind') in KINDS and request.get('operation_id') == 'create':
            try:
                normalized = {**request, 'draft': self._normalize_draft(
                    request['resource_kind'], 'create', request.get('draft', {}))}
                self._compile_create(normalized)
            except (RelationalClientError, KeyError) as error:
                result['errors'].append({'field_id': 'module_options',
                    'code': 'invalid_sqlite_virtual_constructor', 'message': str(error)})
        return result

    def _compile_create(self, request):
        from .virtual_tables import KINDS, arguments
        if request['resource_kind'] not in KINDS:
            return super()._compile_create(request)
        draft = request['draft']
        options = draft.get('options') or {}
        if not isinstance(options, Mapping):
            raise RelationalClientError('create options must be an object')
        if set(options) - {'parent', 'database', 'schema', 'module', 'columns', 'module_options'}:
            raise RelationalClientError('Unknown SQLite virtual-table create option')
        name = self._identifier(draft['name'])
        parent = options.get('parent') or options.get('schema') or options.get('database') or 'main'
        path = self._path_value(parent)
        if len(path) != 1:
            raise RelationalClientError('SQLite virtual-table database must be a single path component')
        module = options.get('module')
        args = arguments(module, options.get('columns'), options.get('module_options', {}), schema=path[0])
        qualified = self._new_object_name(name, {**options, 'parent': path})
        return [{'source': f'CREATE VIRTUAL TABLE {qualified} USING {module}' +
                 (' (' + args + ')' if args else ''), 'parameters': ()}]

    def _compile(self, request):
        from .virtual_tables import KINDS
        result = super()._compile(request)
        if request['resource_kind'] in KINDS and request['operation_id'] == 'create':
            options = request['draft'].get('options') or {}
            parent = options.get('parent') or options.get('schema') or options.get('database') or 'main'
            result['sqlite_virtual_constructor'] = {
                'schema': self._path_value(parent)[0], 'name': request['draft']['name'],
                'module': options['module'],
            }
            result['warnings'] = [
                'SQLite checks installed modules, tokenizer availability and native constructor constraints at execution.',
                'TEMP and attached database objects require the retained session. Session operations remain staged until its transaction is committed.',
                'External-content indexes require explicit population and synchronization with their content table.',
            ]
        return result

    def apply(self, client, request, connection=None):
        from .virtual_tables import apply_creation
        compiled = (request.get('provider_payload') or {}).get('compiled') or {}
        if 'sqlite_virtual_constructor' in compiled:
            with client._lock:
                return apply_creation(client, request, connection)
        return super().apply(client, request, connection)

    def validate_operation_post_state(self, client, request):
        from .virtual_tables import observe_creation
        compiled = (request.get('provider_payload') or {}).get('compiled') or {}
        if 'sqlite_virtual_constructor' in compiled:
            with client._lock:
                return observe_creation(client, request)
        return {'confirmed': False, 'reason': 'provider_post_state_validator_unavailable'}

    @staticmethod
    def _validate_sqlite_database_operation(operation, draft, route):
        validate = RelationalAdministration._validate_sqlite_database_operation
        native_draft = dict(draft)
        if operation not in {'backup', 'restore'}:
            return validate(operation, native_draft, route)
        timeout = native_draft.pop('backup_timeout', 30)
        errors = validate(operation, native_draft, route)
        if (isinstance(timeout, bool) or
                not isinstance(timeout, (int, float)) or
                not 0 < timeout <= 3600):
            errors.append({
                'field_id': 'backup_timeout',
                'code': 'invalid_sqlite_backup_timeout',
                'message': ('SQLite backup timeout must be above 0 '
                            'and at most 3600 seconds.'),
            })
        return errors


ADMINISTRATION = SQLiteAdministration(RelationalAdminDialect(
    engine_id='sqlite',
    supports_cascade=False,
    embedded_database=True,
    database_create_mode='embedded-file',
    database_extension='.sqlite',
    not_applicable_concepts=frozenset({
        'servers', 'materialized_views', 'domains', 'types', 'sequences',
        'functions', 'procedures', 'roles_and_grants', 'partitions',
        'tablespaces_and_filespaces', 'replication_objects',
        'jobs_and_events',
    }),
    concept_resource_kinds={'schemas': ('database', 'attached-database')},
    supported={
        'database': frozenset({
            'inspect', 'create', 'alter', 'drop', 'backup', 'restore',
            'integrity_check', 'quick_check', 'foreign_key_check', 'vacuum',
            'incremental_vacuum', 'optimize', 'analyze', 'reindex',
            'wal_checkpoint',
        }),
        'attached-database': frozenset({'inspect'}),
        'table': frozenset({
            'inspect', 'create', 'alter', 'rename', 'drop',
            'insert', 'update', 'delete',
        }),
        'view': frozenset({'inspect', 'create', 'drop'}),
        'column': frozenset({'inspect', 'create', 'rename', 'drop'}),
        'index': frozenset({'inspect', 'create', 'drop'}),
        'trigger': frozenset({'inspect', 'create', 'drop'}),
        'constraint': frozenset({'inspect'}),
        'virtual-table': frozenset({
            'inspect', 'create', 'rename', 'drop',
        }),
        'fts-table': frozenset({
            'inspect', 'create', 'rename', 'drop',
        }),
        'pragma': frozenset({'inspect'}),
        'extension': frozenset({'inspect'}),
        'native-function': frozenset({'inspect'}),
        'collation': frozenset({'inspect'}),
        'compile-option': frozenset({'inspect'}),
    },
))


class SQLiteProvider(NativeEditorProvider, ActualEnginePilotProvider):
    def __init__(self, context, permissions, client):
        super().__init__(context, permissions, client, PROFILE)

    def _discard_unverified_session(self, handle):
        self.client._discard_failed_session(handle)

    def extension_action(self, request, manifest):
        from .extensions import action
        self._require('execute')
        if request.get('operation') in {'review', 'load'}:
            self._require('administer')
            self._require('filesystem')
        handle = self._editor_session(request)
        with self.client._lock:
            # A receipt is readable after an uncertain initialization has
            # blocked further use of this connection.
            if request.get('operation') != 'receipt':
                self.client._require_idle(handle)
            return action(self.client, handle, {key: value for key, value in request.items()
                if key not in {'session_id', 'language_profile'}}, manifest)

    def validate_source_without_execution(self, request):
        from pgadmin.cdeadmin.data_studio.language_tools import analyze
        if (not isinstance(request, dict) or
                request.get('language_profile') != 'sqlite-sql'):
            raise RelationalClientError('SQLite SQL language binding required')
        session = self._sessions.get(request.get('session_id'))
        if session is None:
            raise RelationalClientError('SQLite session is unavailable')
        source = request.get('source')
        result = analyze(source, 'sqlite-sql', script=request.get('script', False))
        if result['diagnostics'] or not result['statements']:
            return result
        all_valid = True
        pragma_suppressed = False
        for statement in result['statements']:
            native = self.client.validate_parse_only(session.handle, statement['source'])
            pragma_suppressed = pragma_suppressed or native.get('pragma_preparation_suppressed', False)
            if native['grammar_valid'] is False:
                result['diagnostics'].append({**native['diagnostic'],
                    'offset': statement['start'],
                    'line': source.count('\n', 0, statement['start']) + 1,
                    'column': statement['start'] - source.rfind('\n', 0, statement['start'])})
                all_valid = False
            elif native['grammar_valid'] is None:
                if all_valid is True:
                    all_valid = None
                if native.get('diagnostic'):
                    result['diagnostics'].append({**native['diagnostic'],
                        'offset': statement['start'],
                        'line': source.count('\n', 0, statement['start']) + 1,
                        'column': statement['start'] - source.rfind('\n', 0, statement['start'])})
        result['grammar_valid'] = all_valid
        result['authority'] = 'sqlite-native-explain-compile'
        result['scope'] = ('SQLite native compilation against the retained session; '
                           'EXPLAIN does not execute the submitted SQL. '
                           'PRAGMA settings and VFS callbacks are suppressed during preparation. '
                           'Context or parameter binding errors leave grammar unconfirmed.')
        if pragma_suppressed:
            result['pragma_context_evaluated'] = False
        if all_valid is False:
            result['syntax_valid'] = False
            result['script_ready'] = False
        return result

    def capture_catalog(self, route, *, include_system=False):
        """Observe a registered file in a separate short read transaction."""
        self._require('data_read', 'resource')
        path = contained_database(route)
        if path == ':memory:':
            raise RelationalClientError(
                'An independent in-memory connection is a different SQLite database')
        if not os.path.isfile(path):
            raise RelationalClientError(
                'SQLite catalog capture requires an existing registered file')
        initial_info = os.stat(path)
        if not stat.S_ISREG(initial_info.st_mode):
            raise RelationalClientError('SQLite catalog requires a regular registered file')
        connection = self.client._connect({'route': route})
        try:
            connection.execute('BEGIN')
            resources = _resources(connection, {
                'capability_generation': str(uuid.uuid4())})
            connection.execute('ROLLBACK')
            file_info = os.stat(path)
            if (not stat.S_ISREG(file_info.st_mode) or
                    (file_info.st_dev, file_info.st_ino) !=
                    (initial_info.st_dev, initial_info.st_ino)):
                raise RelationalClientError('SQLite registered file changed during capture')
            unavailable=[]
            for row in resources:
                if (row['native'].get('column_observation',{}).get('available') is False or
                        row['native'].get('view_binding_observation',{}).get('available') is False or
                        row['native'].get('module_observation',{}).get('available') is False or
                        row['native'].get('fts_configuration',{}).get('available') is False or
                        row['native'].get('table_function_observation',{}).get('observation_complete') is False):
                    unavailable.append(row)
            for item in resources:
                if item['resource_kind'] in {'database',
                                             'attached-database'}:
                    if item['resource_kind'] == 'database':
                        item['native']['registered_file_identity'] = [
                            file_info.st_dev, file_info.st_ino]
                    item['native']['catalog_observations'] = [{
                        'source': 'sqlite_schema/table_list/table_xinfo/index_list/index_xinfo/foreign_key_list/function_list/native-table-functions/collation_list/compile_options/pragma_list',
                        'available': True,
                    }]
                    item['native']['coverage_complete'] = False
                    item['native']['catalog_warnings'] = [
                        'CHECK expressions and all table options remain in exact native CREATE SQL; they are not separately decomposed.',
                        'Connection-local objects and uncommitted changes on other handles are outside this capture.',
                    ]
                    missing=[row['resource_id'] for row in unavailable if row['display_path'][0]==item['display_name'] or
                             row['native'].get('scope')=='connection']
                    if missing:
                        item['native']['catalog_observations'].append({'source':'native-relation-columns-binding-and-fts-settings',
                            'available':False,'unavailable_resource_ids':missing})
                        item['native']['catalog_warnings'].append('Some relation columns, bindings, FTS settings or table-function observations are unavailable. Their native definitions and identities are retained; inspect the affected observations before migration.')
            if len(resources) > 20_000:
                raise RelationalClientError(
                    'SQLite catalog exceeds the 20,000-resource limit')
            if not include_system:
                resources = [item for item in resources if
                    item['native'].get('system_object') is not True]
            return {'resources': resources,
                    'generation': resources[0]['generation'] if resources else str(uuid.uuid4()),
                    'consistency': 'owned-native-read-transaction',
                    'complete': not unavailable}
        except BaseException:
            if connection.in_transaction:
                try:
                    connection.execute('ROLLBACK')
                except Exception:
                    pass
            raise
        finally:
            self.client._discard_failed_session(connection)

    def capture_data(self, route, resource_id, *, endpoint_id, target_id,
                     mode='sample', row_limit=100):
        from .data_capture import capture
        return capture(self, route, resource_id, endpoint_id=endpoint_id,
                       target_id=target_id, mode=mode, row_limit=row_limit)

    def export_data_script(self, route, resource_id, *, endpoint_id, target_id):
        from .data_script import export
        return export(self, route, resource_id, endpoint_id=endpoint_id,
                      target_id=target_id)


def _route_arguments(route):
    return {**sqlite_arguments(route), 'factory': SQLiteConnection}


def _metric_records():
    """Load only scalar metrics admitted by the exact contract."""
    artifact = package_resources.files(__package__).joinpath(
        PROFILE.metrics_contract_file
    )
    document = json.loads(artifact.read_text(encoding='utf-8'))
    observations = {
        item['observation_id']: item
        for item in document['native_observations']
    }
    return [{
        **observations[item['observation_id']], **item,
    } for item in document['metrics']]


def _resource_id(kind, path, name):
    """Encode native path segments without conflating names containing ':'."""
    return 'sqlite:' + json.dumps(
        [kind, *[str(part) for part in path], str(name)],
        ensure_ascii=False, separators=(',', ':'),
    )


def _resources(connection, request):
    generation = str(request.get('capability_generation') or 'current')
    cursor = connection.cursor()
    try:
        cursor.execute('PRAGMA database_list')
        resources = {}
        databases = cursor.fetchall()

        def quote(value):
            return '"' + str(value).replace('"', '""') + '"'

        def add(kind, path, name, native=None):
            path = [str(item) for item in path]
            name = str(name)
            resource_id = _resource_id(kind, path, name)
            native = dict(native or {})
            native.setdefault('system_object', False)
            if path:
                if len(path) == 1:
                    parent = _resource_id(
                        'database' if path[0] == 'main' else
                        'attached-database', [], path[0])
                else:
                    parent_kind = relation_kinds.get(
                        (path[0], path[-1]), 'table')
                    parent = _resource_id(
                        parent_kind, path[:-1], path[-1])
                native.setdefault('navigator_parent_resource_id', parent)
            resources[resource_id] = {
                'resource_id': resource_id,
                'resource_kind': kind,
                'display_name': name,
                'display_path': [*path, name],
                'authority_path': [*path, kind, name],
                'generation': generation,
            }
            resources[resource_id]['native'] = native
            return resources[resource_id]

        def pragma_value(schema_name, pragma_name):
            cursor.execute(
                f'PRAGMA {quote(schema_name)}.{pragma_name}'
            )
            row = cursor.fetchone()
            return row[0] if row else None

        def database_properties(sequence, schema_name, database_path):
            database_path = str(database_path or '')
            page_size = pragma_value(schema_name, 'page_size')
            page_count = pragma_value(schema_name, 'page_count')
            physical_bytes = None
            if database_path and os.path.isfile(database_path):
                physical_bytes = os.path.getsize(database_path)
            from .table_functions import native_runtime
            runtime = native_runtime()
            return {
                'database_name': database_path,
                'schema_name': schema_name,
                'attachment_sequence': int(sequence),
                'encoding': pragma_value(schema_name, 'encoding'),
                'page_size_bytes': page_size,
                'page_count': page_count,
                'logical_size_bytes': (
                    int(page_size) * int(page_count)
                    if page_size is not None and page_count is not None
                    else None
                ),
                'physical_file_bytes': physical_bytes,
                'free_list_pages': pragma_value(
                    schema_name, 'freelist_count'
                ),
                'maximum_page_count': pragma_value(
                    schema_name, 'max_page_count'
                ),
                'auto_vacuum_code': pragma_value(
                    schema_name, 'auto_vacuum'
                ),
                'journal_mode': pragma_value(
                    schema_name, 'journal_mode'
                ),
                'synchronous_code': pragma_value(
                    schema_name, 'synchronous'
                ),
                'locking_mode': pragma_value(
                    schema_name, 'locking_mode'
                ),
                'secure_delete_code': pragma_value(
                    schema_name, 'secure_delete'
                ),
                'application_id': pragma_value(
                    schema_name, 'application_id'
                ),
                'user_version': pragma_value(schema_name, 'user_version'),
                'schema_version': pragma_value(
                    schema_name, 'schema_version'
                ),
                'sqlite_runtime_version': runtime[0],
                'sqlite_source_id': runtime[1],
            }

        relation_kinds = {}
        for sequence, name, path in databases:
            name = str(name)
            kind = 'database' if name == 'main' else 'attached-database'
            add(kind, [], name, database_properties(sequence, name, path))
        for _sequence, schema_name, _path in databases:
            schema_name = str(schema_name)
            cursor.execute(f'PRAGMA {quote(schema_name)}.table_list')
            table_options = {
                str(row[1]): {'type': str(row[2]),
                              'without_rowid': bool(row[4]),
                              'strict': bool(row[5])}
                for row in cursor.fetchall()
                if str(row[0]) == schema_name
            }
            cursor.execute(
                f'SELECT type, name, tbl_name, sql FROM '
                f'{quote(schema_name)}.sqlite_schema '
                'ORDER BY type, name'
            )
            schema_rows = cursor.fetchall()
            relation_system = {}
            for native_kind, name, _table_name, source in schema_rows:
                kind = str(native_kind)
                if kind == 'table' and re.match(
                        r'^\s*CREATE\s+VIRTUAL\s+TABLE',
                        str(source or ''), re.I):
                    kind = virtual_family(source)
                if kind in {'table', 'view', 'fts-table', 'virtual-table'}:
                    relation_kinds[(schema_name, str(name))] = kind
                    relation_system[(schema_name, str(name))] = (
                        str(name).startswith('sqlite_') or
                        table_options.get(str(name), {}).get('type') == 'shadow')
            relation_names = []
            for native_kind, name, table_name, source in schema_rows:
                native_kind = str(native_kind)
                name = str(name)
                source_value = str(source or '')
                kind = native_kind
                if native_kind == 'table' and re.match(
                    r'^\s*CREATE\s+VIRTUAL\s+TABLE', source_value, re.I
                ):
                    kind = virtual_family(source_value)
                if kind not in {
                    'table', 'view', 'index', 'trigger', 'virtual-table',
                    'fts-table',
                }:
                    continue
                system_object = (name.startswith('sqlite_') or
                                 table_options.get(name, {}).get('type') == 'shadow' or
                                 (kind in {'index', 'trigger'} and
                                  (schema_name, str(table_name)) in relation_system and
                                  relation_system[(schema_name, str(table_name))]))
                native = {
                    'system_object': system_object,
                    'catalog_metadata': {
                        'schema_object_type': native_kind,
                        'table_name': str(table_name),
                        'table_list_type': table_options.get(name, {}).get('type'),
                        'without_rowid': table_options.get(name, {}).get('without_rowid'),
                        'strict': table_options.get(name, {}).get('strict'),
                    },
                    'ddl': source_value,
                }
                if kind in {'table', 'virtual-table', 'fts-table'}:
                    native.update({
                        'columns': [], 'constraints': [], 'indexes': [],
                        'triggers': [],
                    })
                elif kind == 'view':
                    native.update({'columns': [], 'triggers': []})
                owner_path = ([schema_name, str(table_name)]
                              if kind in {'index', 'trigger'} and
                              (schema_name, str(table_name)) in relation_kinds
                              else [schema_name])
                resource = add(kind, owner_path, name, native)
                if kind in {'fts-table','virtual-table'}:
                    declared=module_declaration(source_value)
                    resource['native']['module_observation']={'available':declared is not None,
                        'authority':'native-nonexecuting-create-vtable-authorization',
                        'module':declared[1] if declared else None}
                    if declared and declared[1].lower() in {'fts3','fts4','fts5'}:
                        from .fts_configuration import capture as capture_fts_configuration
                        resource['native']['fts_configuration']=capture_fts_configuration(connection,schema_name,name,declared[1])
                if native_kind in {'table', 'view'}:
                    relation_system[(schema_name, name)] = system_object
                    relation_names.append((name, resource['resource_id']))
            for table_name, relation_id in relation_names:
                relation=resources[relation_id]
                is_view=relation['resource_kind']=='view'
                def view_error(error):
                    code=getattr(error,'sqlite_errorcode',None)
                    virtual=relation['resource_kind'] in {'fts-table','virtual-table'}
                    if type(code) is not int or not (virtual or code & 255 in {sqlite3.SQLITE_ERROR,sqlite3.SQLITE_AUTH}):
                        raise error
                    return {'available':False,'native_error_code':code,'native_error_name':getattr(error,'sqlite_errorname',None)}
                try:
                    cursor.execute(f'PRAGMA {quote(schema_name)}.table_xinfo({quote(table_name)})')
                    columns = cursor.fetchall()
                    relation['native']['column_observation']={'available':True}
                except sqlite3.Error as error:
                    relation['native']['column_observation']=view_error(error)
                    columns=[]
                if is_view:
                    try:
                        cursor.execute('EXPLAIN SELECT * FROM '+quote(schema_name)+'.'+quote(table_name)+' LIMIT 0')
                        cursor.fetchone()
                        relation['native']['view_binding_observation']={'available':True,'authority':'native-nonexecuting-prepare'}
                    except sqlite3.Error as error:
                        relation['native']['view_binding_observation']={**view_error(error),'authority':'native-nonexecuting-prepare'}
                primary = []
                for _cid, name, data_type, not_null, default, pk, hidden in (
                    columns
                ):
                    native = {'system_object': relation_system[(schema_name, table_name)],
                              'catalog_metadata': {
                        'ordinal_position': int(_cid),
                        'data_type': str(data_type or ''),
                        'nullable': not bool(not_null),
                        'default': default,
                        'primary_key_position': int(pk or 0),
                        'hidden': int(hidden or 0),
                    }}
                    column = add(
                        'column', [schema_name, table_name], name, native
                    )
                    resources[relation_id]['native']['columns'].append({
                        'resource_id': column['resource_id'],
                        'name': str(name),
                        **native['catalog_metadata'],
                    })
                    if int(pk or 0):
                        primary.append((int(pk), str(name)))
                if primary:
                    constraint = add(
                        'constraint', [schema_name, table_name],
                        f'pk_{table_name}', {
                            'system_object': relation_system[(schema_name, table_name)],
                            'catalog_metadata': {
                                'constraint_type': 'PRIMARY KEY',
                                'columns': [
                                    name for _position, name in sorted(
                                        primary
                                    )
                                ],
                            },
                        })
                    resources[relation_id]['native'][
                        'constraints'
                    ].append({
                        'resource_id': constraint['resource_id'],
                        'name': f'pk_{table_name}',
                        **constraint['native']['catalog_metadata'],
                    })
                for item in resources.values():
                    if (
                        item['resource_kind'] == 'trigger' and
                        item['display_path'][0] == schema_name and
                        item['native']['catalog_metadata']['table_name'] ==
                        table_name
                    ):
                        resources[relation_id]['native']['triggers'].append({
                            'resource_id': item['resource_id'],
                            'name': item['display_name'],
                            'ddl': item['native'].get('ddl'),
                        })
                # Views expose columns but do not admit table-only PRAGMAs.
                if resources[relation_id]['resource_kind'] == 'view' or relation['native'].get('column_observation',{}).get('available') is False:
                    continue
                cursor.execute(
                    f'PRAGMA {quote(schema_name)}.foreign_key_list('
                    f'{quote(table_name)})'
                )
                foreign_keys = {}
                for row in cursor.fetchall():
                    foreign_keys.setdefault(int(row[0]), []).append(row)
                for foreign_id, rows in foreign_keys.items():
                    constraint_name = f'fk_{table_name}_{foreign_id}'
                    dependency = {
                        'relationship': 'foreign-key',
                        'referenced_table': str(rows[0][2]),
                        'referenced_columns': [str(row[4]) for row in rows],
                    }
                    constraint = add(
                        'constraint', [schema_name, table_name],
                        constraint_name, {
                            'system_object': relation_system[(schema_name, table_name)],
                            'catalog_metadata': {
                                'constraint_type': 'FOREIGN KEY',
                                'columns': [str(row[3]) for row in rows],
                                'referenced_table': str(rows[0][2]),
                                'referenced_columns': [
                                    str(row[4]) for row in rows
                                ],
                                'on_update': str(rows[0][5]),
                                'on_delete': str(rows[0][6]),
                                'match': str(rows[0][7]),
                            },
                            'dependencies': [dependency],
                        })
                    resources[relation_id]['native'][
                        'constraints'
                    ].append({
                        'resource_id': constraint['resource_id'],
                        'name': constraint_name,
                        **constraint['native']['catalog_metadata'],
                    })
                    resources[relation_id]['native'].setdefault(
                        'dependencies', []
                    ).append({
                        **dependency, 'constraint_name': constraint_name,
                    })

                cursor.execute(
                    f'PRAGMA {quote(schema_name)}.index_list('
                    f'{quote(table_name)})'
                )
                for index_row in cursor.fetchall():
                    index_name = str(index_row[1])
                    index_id = _resource_id(
                        'index', [schema_name, table_name], index_name)
                    index = resources.get(index_id)
                    cursor.execute(
                        f'PRAGMA {quote(schema_name)}.index_xinfo('
                        f'{quote(index_name)})')
                    keys = [{
                        'sequence': int(row[0]), 'column_id': int(row[1]),
                        'name': row[2], 'descending': bool(row[3]),
                        'collation': row[4], 'is_key': bool(row[5]),
                    } for row in cursor.fetchall()]
                    details = {
                        'resource_id': index_id, 'name': index_name,
                        'unique': bool(index_row[2]),
                        'origin': str(index_row[3]),
                        'partial': bool(index_row[4]),
                        'keys': keys,
                    }
                    if index is None:
                        index = add('index', [schema_name, table_name],
                                    index_name, {
                            'system_object': True,
                            'ddl': None,
                            'catalog_metadata': {
                                'schema_object_type': 'index',
                                'table_name': table_name,
                                'implicit': True,
                            }})
                    index['native']['catalog_metadata'].update({
                        'unique': details['unique'],
                        'origin': details['origin'],
                        'partial': details['partial'],
                        'keys': keys,
                    })
                    details['ddl'] = index['native'].get('ddl')
                    resources[relation_id]['native']['indexes'].append(details)
                    if str(index_row[3]) == 'u':
                        constraint_name = 'unique_' + index_name
                        constraint = add('constraint',
                            [schema_name, table_name], constraint_name, {
                                'system_object': relation_system[(schema_name, table_name)],
                                'catalog_metadata': {
                                    'constraint_type': 'UNIQUE',
                                    'columns': [key['name'] for key in keys
                                                if key['is_key']],
                                    'backing_index_resource_id': index_id,
                                }})
                        resources[relation_id]['native'][
                            'constraints'].append({
                                'resource_id': constraint['resource_id'],
                                'name': constraint_name,
                                **constraint['native']['catalog_metadata'],
                            })
        cursor.execute('PRAGMA pragma_list')
        for (name,) in cursor.fetchall():
            add('pragma', [], name, {'native_name': name, 'scope': 'connection',
                                     'observation': 'supported pragma name; not executed'})
        cursor.execute('PRAGMA function_list')
        for name, builtin, kind, encoding, arity, flags in cursor.fetchall():
            identity = json.dumps([name, builtin, kind, encoding, arity], ensure_ascii=False, separators=(',', ':'))
            item = add('native-function', [], identity, {
                'name': name, 'builtin': bool(builtin), 'function_type': kind,
                'encoding': encoding, 'argument_count': arity, 'flags': flags,
                'loaded_in_connection': True, 'scope': 'connection',
                'system_object': bool(builtin)})
            item['display_name'] = f'{name} ({arity}; {encoding}; {kind})'
        from .table_functions import discover
        for function in discover(cursor, [str(row[1]) for row in databases], relation_kinds):
            name = function['name']
            identity = json.dumps([name, 'table-function'], ensure_ascii=False, separators=(',', ':'))
            item = add('native-function', [], identity, {'name': name, 'function_type': 'table',
                'scope': 'connection', 'system_object': True, 'table_function_observation': function})
            item['display_name'] = name + ' (table function)'
        cursor.execute('PRAGMA collation_list')
        for ordinal, name in cursor.fetchall():
            add('collation', [], name, {'native_name': name, 'ordinal': ordinal,
                                       'scope': 'connection', 'loaded_in_connection': True})
        cursor.execute('PRAGMA compile_options')
        for (option,) in cursor.fetchall():
            add('compile-option', [], option, {'native_option': option, 'scope': 'runtime'})
        cursor.execute('PRAGMA module_list')
        module_names=sorted(row[0] for row in cursor.fetchall())
        fold=str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')
        registered={name.translate(fold) for name in module_names}
        for resource in resources.values():
            observation=resource['native'].get('module_observation')
            if observation is not None:
                module=observation.get('module')
                observation['registered_in_session']=module is not None and module.translate(fold) in registered
        for name in module_names:
            add('extension', [], name, {
                'extension_kind': 'virtual-table-module',
                'loaded_in_connection': True,
            })
        for metric in _metric_records():
            cursor.execute(metric['source'])
            row = cursor.fetchone()
            add('metric', ['Metrics'], metric['native_name'], {
                **metric,
                # Metrics is a visual folder, not an attached database.
                'navigator_parent_resource_id': None,
                'value': row[0] if row else None,
                'observation_error': None if row else (
                    'scalar PRAGMA returned no row'
                ),
            })
        return list(resources.values())
    finally:
        cursor.close()


def _security(connection, request):
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT 'embedded-process'")
        current_user = str(cursor.fetchone()[0])
        return {
            'resource_id': f'authorization:{current_user}',
            'display_name': current_user,
            'authority_path': ['authorization', current_user],
            'generation': str(
                request.get('capability_generation') or 'current'
            ),
            'native': {'authorization_model': current_user},
        }
    finally:
        cursor.close()


def _initialize_connection(connection, route):
    connection.text_factory = native_text
    attachments = route.get('attached_databases', [])
    if not isinstance(attachments, list):
        raise RelationalClientError(
            'SQLite attached databases must be an array'
        )
    cursor = connection.cursor()
    try:
        for attachment in attachments:
            if not isinstance(attachment, Mapping):
                raise RelationalClientError(
                    'SQLite attachment must be an object'
                )
            name = attachment.get('name')
            database = attachment.get('database')
            if (not isinstance(name, str) or not name or len(name) > 128 or
                    '\x00' in name or name.lower() in {'main', 'temp'}):
                raise RelationalClientError(
                    'SQLite attachment name is invalid'
                )
            attached_route = dict(route)
            attached_route['database'] = database
            path = sqlite_arguments(attached_route)['database']
            cursor.execute(
                'ATTACH DATABASE ? AS "' + name.replace('"', '""') + '"',
                (path,),
            )
    finally:
        cursor.close()


def _initialize_database(connection, options):
    """Apply settings that SQLite admits before the first schema object."""
    admitted = {
        'page_size', 'encoding', 'auto_vacuum',
        'application_id', 'user_version',
    }
    if set(options).difference(admitted):
        raise RelationalClientError(
            'SQLite database creation options are unsupported'
        )
    page_size = str(options.get('page_size', '4096'))
    if page_size not in {
        '512', '1024', '2048', '4096', '8192', '16384', '32768',
        '65536',
    }:
        raise RelationalClientError('SQLite page size is invalid')
    encoding = options.get('encoding', 'UTF-8')
    if encoding not in {'UTF-8', 'UTF-16', 'UTF-16le', 'UTF-16be'}:
        raise RelationalClientError('SQLite encoding is invalid')
    auto_vacuum = options.get('auto_vacuum', 'NONE')
    if auto_vacuum not in {'NONE', 'FULL', 'INCREMENTAL'}:
        raise RelationalClientError('SQLite auto-vacuum mode is invalid')
    integers = {}
    for field_id in ('application_id', 'user_version'):
        value = options.get(field_id, 0)
        if isinstance(value, bool) or not isinstance(value, int) or not (
                -2147483648 <= value <= 2147483647):
            raise RelationalClientError(
                f'SQLite {field_id.replace("_", " ")} is invalid'
            )
        integers[field_id] = value
    cursor = connection.cursor()
    observed = {}
    try:
        cursor.execute(f'PRAGMA page_size = {page_size}')
        cursor.execute(f"PRAGMA encoding = '{encoding}'")
        cursor.execute(f'PRAGMA auto_vacuum = {auto_vacuum}')
        for field_id, value in integers.items():
            cursor.execute(f'PRAGMA {field_id} = {value}')
        for field_id in (
            'page_size', 'encoding', 'auto_vacuum',
            'application_id', 'user_version',
        ):
            cursor.execute(f'PRAGMA {field_id}')
            row = cursor.fetchone()
            observed[field_id] = row[0] if row else None
        connection.commit()
    finally:
        cursor.close()
    return {
        'settings_applied': True,
        'observed': observed,
        'transaction_finality_interpreted_by_common_code': False,
    }


def _drop_database_file(route, database):
    """Delete one contained, offline SQLite file without inventing SQL."""
    path = contained_database(route)
    if path != os.path.realpath(database):
        raise RelationalClientError(
            'SQLite deletion target does not match the trusted route'
        )
    if route.get('read_only') is True or route.get('uri_immutable') is True:
        raise RelationalClientError(
            'SQLite read-only routes cannot delete database files'
        )
    sidecars = [path + suffix for suffix in ('-journal', '-wal', '-shm')]
    if any(os.path.lexists(item) for item in sidecars):
        raise RelationalClientError(
            'SQLite database has journal or WAL sidecars; close external '
            'sessions and checkpoint it before deletion'
        )
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RelationalClientError(
            f'SQLite database file cannot be opened ({type(exc).__name__})'
        ) from None
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode):
            raise RelationalClientError(
                'SQLite deletion target is not a regular file'
            )
        header = os.read(descriptor, 16)
        if details.st_size and header != b'SQLite format 3\x00':
            raise RelationalClientError(
                'SQLite deletion target has no SQLite database header'
            )
        identity = (details.st_dev, details.st_ino)
    finally:
        os.close(descriptor)
    current = os.lstat(path)
    if stat.S_ISLNK(current.st_mode) or (
            current.st_dev, current.st_ino) != identity:
        raise RelationalClientError(
            'SQLite deletion target changed during verification'
        )
    os.unlink(path)
    return {
        'driver_operation': 'embedded-drop-database',
        'driver_returned': True,
        'database': path,
        'file_deleted': True,
        'transaction_finality_interpreted_by_common_code': False,
    }


def _create_client():
    return SQLiteClient(RelationalClientConfig(
        profile=PROFILE,
        module_name='sqlite3',
        version_query='SELECT sqlite_version()',
        connect_arguments=_route_arguments,
        metadata_reader=_resources,
        security_reader=_security,
        administration=ADMINISTRATION,
        connection_initializer=_initialize_connection,
        database_initializer=_initialize_database,
        database_dropper=_drop_database_file,
        database_operation_runner=_sqlite_database_operation,
    ))


def create_provider(context, permissions, client=None):
    return SQLiteProvider(context, permissions, client or _create_client())

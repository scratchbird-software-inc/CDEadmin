"""DuckDB retained-session administration and catalog-aware row identity."""
from contextlib import contextmanager
from copy import deepcopy
import os

from ..relational_admin import RelationalAdministration
from ...sdk.relational import RelationalClientError


class DuckDBAdministration(RelationalAdministration):
    def catalog(self, catalog):
        from .object_metadata import KINDS
        from .extension_updates import OPERATIONS
        value = deepcopy(catalog)
        for resource in value.get('objects', []):
            for kind, operation in sorted(OPERATIONS):
                if resource['resource_kind'] == kind:
                    resource['operations'] = [row for row in resource.get('operations', [])
                        if row['operation_id'] != operation] + [{
                            'operation_id': operation,
                            'title': 'Update native extension' if kind == 'extension' else 'Update installed extensions',
                            'mutation_class': 'admin', 'target_required': True,
                            'confirmation_required': True, 'long_running': False,
                            'cancellable': False, 'post_state_required': False}]
            if resource['resource_kind'] in KINDS:
                resource['operations'] = [row for row in resource.get('operations', [])
                    if row['operation_id'] != 'comment'] + [{
                        'operation_id': 'comment', 'title': 'Edit native comment',
                        'mutation_class': 'admin', 'target_required': True,
                        'confirmation_required': True, 'long_running': False,
                        'cancellable': False, 'post_state_required': False}]
        return super().catalog(value)

    def _form(self, kind, operation):
        from .extension_updates import OPERATIONS, form
        if (kind, operation) in OPERATIONS:
            return form(kind, operation, self._field)
        if operation == 'comment':
            return {'form_id': f'duckdb.{kind}.comment', 'title': 'Edit native DuckDB comment',
                'fields': [{**self._field('comment', 'Comment', 'multiline'),
                    'submit_unchanged': True,
                    'initial_value_path': ['catalog_metadata', 'comment'],
                    'visible_when': {'field_id': 'clear_comment', 'equals': False}},
                    self._field('clear_comment', 'Remove comment', 'boolean', default=False),
                    self._field('confirmation', 'Exact object name', 'text', True)]}
        if operation == 'alter' and kind in {'view', 'macro'}:
            fields = [self._field(
                'query' if kind == 'view' else 'source',
                'Replacement SELECT/WITH query' if kind == 'view' else
                'Complete qualified CREATE OR REPLACE MACRO statement',
                'code', True,
                'DuckDB replaces the entire definition and all macro overloads.'
                if kind == 'macro' else 'Enter one SELECT or WITH query.')]
            fields.extend((
                self._field('complete_definition_confirmed',
                    'I reviewed the complete replacement definition', 'boolean', True),
                self._field('metadata_reset_acknowledged',
                    'I accept that native replacement clears comments and tags',
                    'boolean', True),
            ))
            return {'form_id': f'duckdb.{kind}.alter',
                'title': f'Replace DuckDB {kind}', 'fields': fields}
        if kind == 'database' and operation in {'export_database', 'import_database'}:
            exporting = operation == 'export_database'
            fields = [self._field('directory', 'Export directory' if exporting else 'Import directory',
                'text', True, 'Absolute path under the registered filesystem root.')]
            if exporting:
                fields.append(self._field('format', 'Native format', 'select', False,
                    default='PARQUET', options=('PARQUET', 'CSV')))
            return {'form_id': f'duckdb.database.{operation}',
                'title': 'Export DuckDB logical database' if exporting else 'Import DuckDB logical database',
                'fields': fields}
        return super()._form(kind, operation)

    def _definition_replacement(self, request):
        kind = request['resource_kind']
        draft = request.get('draft') or {}
        expected = ({'query', 'definition'} if kind == 'view' else {'source'}) | {
            'complete_definition_confirmed', 'metadata_reset_acknowledged'}
        if (set(draft) - expected - {'changes'} or draft.get('changes') or
                (kind == 'view' and 'query' in draft and 'definition' in draft) or
                draft.get('complete_definition_confirmed') is not True or
                draft.get('metadata_reset_acknowledged') is not True):
            raise RelationalClientError(
                'DuckDB replacement requires one complete definition and explicit metadata-reset acknowledgement')
        path = self._target_path(request.get('target_resource'))
        if len(path) != 3:
            raise RelationalClientError('DuckDB replacement requires the exact catalog, schema and object')
        if kind == 'view':
            source = ('CREATE OR REPLACE VIEW ' + self._qualified(path) +
                      ' AS ' + self._query_body(draft.get('query', draft.get('definition'))))
        else:
            source = draft.get('source')
        from ...workspace.duckdb_schema_plan import _validated_ddl
        try:
            source = _validated_ddl(source, kind, path, replace=True)
        except ValueError as error:
            raise RelationalClientError(str(error)) from None
        return {'statements': [{'source': source, 'parameters': ()}],
            'warnings': [
                'Native replacement clears existing comments and tags; restore them separately if needed.',
                'The complete macro signature set, including defaults, is operator-authored.'
                if kind == 'macro' else
                'The replacement view query is bound and checked by DuckDB at execution.',
            ]}

    def validate(self, request):
        from .extension_updates import OPERATIONS, compile_operation
        if (request.get('resource_kind'), request.get('operation_id')) in OPERATIONS:
            try:
                compile_operation(self, request)
                return {'errors': []}
            except RelationalClientError as error:
                return {'errors': [{'field_id': None,
                    'code': 'invalid_duckdb_extension_update', 'message': str(error)}]}
        if request.get('operation_id') == 'comment':
            try:
                from .object_metadata import compile_operation
                compile_operation(self, request)
                return {'errors': []}
            except RelationalClientError as error:
                return {'errors': [{'field_id': None,
                    'code': 'invalid_duckdb_comment', 'message': str(error)}]}
        result = super().validate(request)
        if (not result['errors'] and request.get('operation_id') == 'alter' and
                request.get('resource_kind') in {'view', 'macro'}):
            try:
                self._definition_replacement(request)
            except RelationalClientError as error:
                result['errors'].append({'field_id': None,
                    'code': 'invalid_duckdb_definition_replacement',
                    'message': str(error)})
        return result

    def _compile(self, request):
        from .extension_updates import OPERATIONS, compile_operation
        if (request.get('resource_kind'), request.get('operation_id')) in OPERATIONS:
            return compile_operation(self, request)
        if request.get('operation_id') == 'comment':
            from .object_metadata import compile_operation
            return compile_operation(self, request)
        if (request['operation_id'] == 'alter' and
                request['resource_kind'] in {'view', 'macro'}):
            return self._definition_replacement(request)
        return super()._compile(request)

    def plan(self, request):
        result = super().plan(request)
        if (request.get('operation_id') == 'alter' and
                request.get('resource_kind') == 'macro'):
            result['command_preview']['provider_constructed'] = False
            result['command_preview']['source_origin'] = 'operator-reviewed-native-statement'
        return result

    @staticmethod
    def _duckdb_operation_directory(route, value, importing=False):
        directory = RelationalAdministration._duckdb_operation_directory(route, value, importing)
        if importing:
            for name in ('schema.sql', 'load.sql'):
                path = os.path.join(directory, name)
                if os.path.islink(path) or os.path.dirname(os.path.realpath(path)) != directory:
                    raise RelationalClientError('DuckDB import control files must reside in the reviewed directory')
        return directory

    def _compile_duckdb_database_operation(self, request):
        compiled = super()._compile_duckdb_database_operation(request)
        if request['operation_id'] == 'export_database':
            compiled.setdefault('warnings', []).extend((
                'EXPORT DATABASE is a logical native export, not a physical backup.',
                'Rollback does not remove files already written by EXPORT DATABASE.',
            ))
        elif request['operation_id'] == 'import_database':
            compiled.setdefault('warnings', []).append(
                'IMPORT DATABASE reads native export files; review their contents before execution.')
        return compiled

    @contextmanager
    def _borrow(self, client, connection):
        if connection is None:
            yield
            return
        with client._lock:
            client._require_idle(connection)
            client._busy.add(id(connection))
        try:
            yield
        finally:
            with client._lock:
                client._busy.discard(id(connection))

    def apply(self, client, request, connection=None):
        with self._borrow(client, connection):
            if 'duckdb_extension_update' in (request.get('provider_payload') or {}).get('compiled', {}):
                from .extension_updates import apply
                return apply(self, client, request, connection)
            if 'duckdb_comment' in (request.get('provider_payload') or {}).get('compiled', {}):
                from .object_metadata import apply
                return apply(self, client, request, connection)
            return super().apply(client, request, connection=connection)

    def read_rows(self, client, request, connection=None):
        with self._borrow(client, connection):
            return super().read_rows(client, request, connection=connection)

    def _primary_key(self, connection, path):
        schema, table = self._schema_table(path, 'main')
        catalog = path[-3] if len(path) >= 3 else connection.execute(
            'SELECT current_database()').fetchone()[0]
        connection.execute(
            'SELECT kcu.column_name FROM information_schema.'
            'table_constraints tc JOIN '
            'information_schema.key_column_usage kcu '
            'ON tc.constraint_catalog=kcu.constraint_catalog AND '
            'tc.constraint_schema=kcu.constraint_schema AND '
            'tc.constraint_name=kcu.constraint_name '
            "WHERE tc.constraint_type='PRIMARY KEY' AND tc.table_catalog=? "
            'AND tc.table_schema=? AND tc.table_name=? '
            'ORDER BY kcu.ordinal_position', (catalog, schema, table))
        return [str(row[0]) for row in connection.fetchall()]

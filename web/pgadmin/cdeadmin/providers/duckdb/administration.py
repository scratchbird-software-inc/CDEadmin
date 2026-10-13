"""DuckDB retained-session administration and catalog-aware row identity."""
from contextlib import contextmanager
import os

from ..relational_admin import RelationalAdministration
from ...sdk.relational import RelationalClientError


class DuckDBAdministration(RelationalAdministration):
    def _form(self, kind, operation):
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

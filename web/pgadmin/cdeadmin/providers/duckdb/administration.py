"""DuckDB retained-session administration and catalog-aware row identity."""
from contextlib import contextmanager

from ..relational_admin import RelationalAdministration


class DuckDBAdministration(RelationalAdministration):
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

"""Savepoint-isolated optional metadata on a retained PG-wire session."""
from .pgwire_driver import native


class CatalogCursor:
    _cde_catalog_isolated = True

    def __init__(self, connection):
        self.connection = connection
        self.cursor = connection.cursor()

    def __getattr__(self, name):
        return getattr(self.cursor, name)

    def cde_optional_rows(self, source, parameters=()):
        # psycopg transaction() uses a savepoint inside existing native work.
        # A failure to recover that savepoint propagates; no whole rollback.
        try:
            with self.connection.transaction():
                self.cursor.execute(source, parameters)
                return list(self.cursor.fetchall())
        except Exception as exc:
            if (getattr(exc, 'sqlstate', None) in
                    {'42P01', '42703', '42883', '0A000', '42501'} and
                    self.connection.info.transaction_status.name in
                    {'IDLE', 'INTRANS'}):
                return []
            raise


class CatalogConnection:
    def __init__(self, handle):
        self.connection = native(handle)

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def cursor(self):
        return CatalogCursor(self.connection)

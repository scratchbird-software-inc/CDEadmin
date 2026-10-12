"""Opaque native row identity admission within one attachment/transaction."""
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def available(connection, target):
    import firebird.driver as native
    from firebird.driver.types import SQLDataType
    with connection.cursor() as query:
        statement = None
        try:
            statement = query.prepare(
                'SELECT RDB$DB_KEY, RDB$RECORD_VERSION FROM ' + target +
                ' WHERE RDB$DB_KEY=? AND RDB$RECORD_VERSION=?')
            columns = statement._out_desc
            return (isinstance(columns, (list, tuple)) and len(columns) == 2
                    and columns[0].datatype == SQLDataType.TEXT
                    and columns[0].charset == 1 and columns[0].length == 8
                    and columns[1].datatype == SQLDataType.INT64
                    and columns[1].scale == 0)
        except native.DatabaseError as error:
            if str(error.sqlstate).startswith('08'):
                raise
            return False
        finally:
            if statement is not None:
                statement.free()


def owner(connection):
    if not connection.main_transaction.is_active():
        raise RelationalClientError(
            'Native row identity requires its original active transaction; '
            'refresh the row page')
    result = (connection.info.id, connection.main_transaction.info.id)
    if any(type(value) is not int for value in result):
        raise RelationalClientError('Native row identity owner unavailable')
    return result


def verify_owner(connection, expected):
    if (not isinstance(expected, (list, tuple)) or len(expected) != 2 or
            any(type(value) is not int for value in expected) or
            owner(connection) != tuple(expected)):
        raise RelationalClientError(
            'Native row identity belongs to another attachment or '
            'transaction; '
            'refresh the row page')

"""Nonexecuting statement preparation on the retained MariaDB connection."""

from uuid import uuid4

from ...sdk import RelationalClientError
from .mariadb_editor_context import observe
from .mysql_script import Statements
from .mysql_charsets import codec
from .native_prepare_fields import native_fields, parameter_slots


def describe(client, handle, source):
    if not isinstance(source, str) or not source.strip() or '\x00' in source:
        raise RelationalClientError('Valid MariaDB statement source is required')
    try:
        context = observe(client, handle)
    except Exception:
        client._uncertain_sessions.add(id(handle))
        raise RelationalClientError('MariaDB session identity is unconfirmed; close this session') from None
    version, mode = context['version'], context['sql_mode']
    script = Statements(source, mariadb=True)
    statement = script.next(version, mode)
    if statement is None or script.has_next(version, mode):
        raise RelationalClientError('Select exactly one MariaDB statement to prepare')

    cursor = handle.cursor()
    if callable(getattr(cursor, 'cdeadmin_describe', None)):
        return _describe_binary(client, handle, cursor, statement, context)
    name = f'sr_describe_{uuid4().hex}'
    prepared = False
    try:
        cursor.execute(f'SET @{name} = CONVERT(? USING utf8mb4)', (statement.encode('utf8'),))
        cursor.execute(f'PREPARE {name} FROM @{name}')
        prepared = True
        # SQL PREPARE acknowledges compilation but returns no field packets.
        return {
            'statement_type': 'MariaDB PREPARE',
            'statement_execution_requested': False,
            'columns_complete': False,
            'parameters_complete': False,
            'columns': [],
            'parameters': [],
        }
    finally:
        try:
            try:
                if prepared:
                    cursor.execute(f'DEALLOCATE PREPARE {name}')
                cursor.execute(f'SET @{name} = NULL')
            finally:
                cursor.close()
        except Exception:
            client._uncertain_sessions.add(id(handle))
            raise RelationalClientError(
                'MariaDB prepared statement cleanup is unconfirmed; close this session') from None


def _describe_binary(client, handle, cursor, statement, context):
    from mariadb import constants, Error

    try:
        count, rows = cursor.cdeadmin_describe(statement.encode(codec(context['character_set_client'])))
        types = {value: name for name, value in vars(constants.FIELD_TYPE).items() if type(value) is int}
        return {
            'statement_type': 'MariaDB COM_STMT_PREPARE',
            'statement_execution_requested': False,
            'columns_complete': True,
            'parameters_complete': count == 0,
            'columns': native_fields(rows, context['character_set_results'], types.get),
            'parameters': parameter_slots(count),
        }
    except (Error, RuntimeError) as error:
        if not getattr(error, 'errno', None) or error.errno in {2006, 2013, 2055}:
            client._uncertain_sessions.add(id(handle))
        raise
    finally:
        try:
            cursor.close()
        except Exception:
            client._uncertain_sessions.add(id(handle))
            raise RelationalClientError(
                'MariaDB prepared statement cleanup is unconfirmed; close this session') from None

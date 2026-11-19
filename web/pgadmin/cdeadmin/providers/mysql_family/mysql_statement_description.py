"""Describe a statement through Connector/Python's COM_STMT_PREPARE API."""

from mysql.connector import Error
from mysql.connector.constants import FieldType

from ...data_studio.mysql_quoting import available
from ...sdk import RelationalClientError
from ..native_editor import mysql_bind_markers
from .mysql_script import Statements
from .mysql_session_variables import invalidate
from .mysql_values import observed_language
from .native_prepare_fields import native_fields, parameter_slots


def _fields(rows):
    return [
        {'position': position, 'name': row[0], 'native_type': FieldType.get_info(row[1]) or str(row[1]),
         'type_code': row[1]}
        for position, row in enumerate(rows, start=1)
    ]


def describe(client, handle, source):
    if not isinstance(source, str) or not source.strip() or '\x00' in source:
        raise RelationalClientError('Valid MySQL statement source is required')
    version, mode = observed_language(handle)
    script = Statements(source)
    statement = script.next(version, mode)
    if statement is None or script.has_next(version, mode):
        raise RelationalClientError('Select exactly one MySQL statement to prepare')
    native_sql = mysql_bind_markers(
        statement, set(mode.split(',')), dollar_quotes=available(version), surface_markers=True,
    )
    encoded = native_sql.encode(handle.python_charset)
    invalidate(handle)
    try:
        prepared = handle.cmd_stmt_prepare(encoded)
    except Error as error:
        if not getattr(error, 'errno', None) or error.errno in {2006, 2013, 2055}:
            client._uncertain_sessions.add(id(handle))
            raise RelationalClientError('MySQL preparation state is unconfirmed; close this session') from None
        raise RelationalClientError(f'MySQL rejected statement preparation (error {error.errno})') from None

    pure = isinstance(prepared, dict)
    statement_id = prepared['statement_id'] if pure else prepared
    try:
        if pure:
            columns = _fields(prepared['columns'])
            parameters = _fields(prepared['parameters'])
            columns_complete = len(columns) == prepared['num_columns']
            parameters_complete = len(parameters) == prepared['num_params']
        elif callable(getattr(prepared, 'cdeadmin_describe', None)):
            count, fields = prepared.cdeadmin_describe()
            charset = (getattr(handle, '_cdeadmin_charset_variables', {}) or {}).get(
                'character_set_results', handle.charset,
            )
            columns = native_fields(fields, charset, FieldType.get_info)
            parameters = parameter_slots(count)
            columns_complete = True
            parameters_complete = not parameters
        else:
            columns = []
            parameters = parameter_slots(prepared.param_count)
            columns_complete = False
            parameters_complete = not parameters
        return {
            'statement_type': 'MySQL COM_STMT_PREPARE',
            'statement_execution_requested': False,
            'columns_complete': columns_complete,
            'parameters_complete': parameters_complete,
            'columns': columns,
            'parameters': parameters,
        }
    finally:
        try:
            handle.cmd_stmt_close(statement_id)
        except Exception:
            client._uncertain_sessions.add(id(handle))
            raise RelationalClientError('MySQL prepared statement release is unconfirmed; close this session') from None

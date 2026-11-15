"""Typed sqlite3_limit controls on the caller's original SQLite handle.

No SQL, replacement connection, transaction finalization, authorizer or hook
changes. Native hard caps may clamp a requested value; report the observed value.
"""
from ...sdk import RelationalClientError

LIMITS = {
    'vdbe_op': 'SQLITE_LIMIT_VDBE_OP',
    'worker_threads': 'SQLITE_LIMIT_WORKER_THREADS',
    'length': 'SQLITE_LIMIT_LENGTH',
    'sql_length': 'SQLITE_LIMIT_SQL_LENGTH',
    'column': 'SQLITE_LIMIT_COLUMN',
    'expr_depth': 'SQLITE_LIMIT_EXPR_DEPTH',
    'compound_select': 'SQLITE_LIMIT_COMPOUND_SELECT',
    'trigger_depth': 'SQLITE_LIMIT_TRIGGER_DEPTH',
    'variable_number': 'SQLITE_LIMIT_VARIABLE_NUMBER',
    'like_pattern_length': 'SQLITE_LIMIT_LIKE_PATTERN_LENGTH',
    'attached': 'SQLITE_LIMIT_ATTACHED',
    'function_arg': 'SQLITE_LIMIT_FUNCTION_ARG',
}
MAXIMUM = 2147483647


def action(connection, module, request):
    if not isinstance(request, dict):
        raise RelationalClientError('Select a typed native connection limit')
    operation = request.get('operation')
    fields = {'inspect': {'operation', 'limit'},
              'review': {'operation', 'limit', 'value'},
              'set_connection_limit': {'operation', 'limit', 'value', 'expected_value', 'confirmed'}}
    if not isinstance(operation, str) or operation not in fields or set(request) - fields[operation]:
        raise RelationalClientError('Select a typed native connection limit operation')
    name = request.get('limit')
    if not isinstance(name, str) or name not in LIMITS:
        raise RelationalClientError('Native limit is not admitted')
    code = getattr(module, LIMITS[name], None)
    if (type(code) is not int or not callable(getattr(connection, 'getlimit', None))
            or not callable(getattr(connection, 'setlimit', None))):
        raise RelationalClientError('This interpreter/runtime has no native limit API')
    if operation != 'inspect':
        if type(request.get('value')) is not int or not 0 <= request['value'] <= MAXIMUM:
            raise RelationalClientError('Native limit requires an integer from 0 through 2147483647')
    if operation == 'set_connection_limit':
        if request.get('confirmed') is not True:
            raise RelationalClientError('Confirm the original connection limit change')
        if type(request.get('expected_value')) is not int or not 0 <= request['expected_value'] <= MAXIMUM:
            raise RelationalClientError('Refresh the original native limit')
    before = connection.getlimit(code)
    if type(before) is not int or before < 0:
        raise RelationalClientError('Native limit observation is unavailable')
    if operation == 'set_connection_limit':
        if before != request['expected_value']:
            raise RelationalClientError('Original native limit changed; inspect and review again')
        # Review/compare/dispatch are serialized by the provider's original-handle
        # lock. Never probe a hard maximum by temporarily changing the limit.
        try:
            previous = connection.setlimit(code, request['value'])
            after = connection.getlimit(code)
        except Exception as error:
            failure = RelationalClientError('Native limit outcome is unconfirmed; inspect before retrying')
            failure.native_outcome = 'unknown_outcome'
            raise failure from error
        if previous != before or type(after) is not int or after < 0:
            failure = RelationalClientError('Native limit postcondition is unconfirmed; inspect before retrying')
            failure.native_outcome = 'unknown_outcome'
            raise failure
    else:
        after = before
    result = {'limit': name, 'native_constant': LIMITS[name], 'before_value': before,
              'effective_value': after, 'scope': 'original-connection',
              'file_persisted': False, 'future_connection_defaults_changed': False,
              'commit_requested': False, 'rollback_requested': False,
              'transaction_open': connection.in_transaction, 'automatic_retry': False}
    if operation != 'inspect':
        result.update(requested_value=request['value'], expected_value=before)
    if operation == 'review':
        result.update(ready_to_apply=True, hard_cap='native; not probed',
                      warning='Native limits are connection state, not transactional state; ROLLBACK does not restore them.')
    if operation == 'set_connection_limit':
        result.update(outcome='applied' if after == request['value'] else 'native_adjusted',
                      native_previous_value=previous)
    return result

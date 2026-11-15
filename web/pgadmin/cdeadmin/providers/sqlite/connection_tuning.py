"""Bounded original-handle numeric PRAGMAs with explicit callback replacement."""
from ...sdk import RelationalClientError

NAMES = ('busy_timeout', 'analysis_limit', 'wal_autocheckpoint',)
CALLBACKS = {'busy_timeout': 'busy_handler', 'wal_autocheckpoint': 'wal_hook'}
UNITS = {'busy_timeout': 'milliseconds', 'wal_autocheckpoint': 'pages', 'analysis_limit': 'rows_per_index'}
MAXIMUM = 2147483647


def action(connection, request):
    operation = request.get('operation')
    name = request.get('pragma')
    fields = {
        'inspect': {'operation', 'pragma'},
        'review': {'operation', 'pragma', 'value'},
        'set_connection_pragma': {'operation', 'pragma', 'value', 'expected_value', 'confirmed'},
    }
    if name not in NAMES or not isinstance(operation, str) or operation not in fields:
        raise RelationalClientError('Select an admitted numeric PRAGMA')
    allowed = fields[operation] | ({'replace_callback_confirmed'} if name in CALLBACKS and operation == 'set_connection_pragma' else set())
    if set(request) - allowed:
        raise RelationalClientError('Unknown numeric connection PRAGMA argument')
    if operation != 'inspect' and (type(request.get('value')) is not int or not 0 <= request['value'] <= MAXIMUM):
        raise RelationalClientError('Select an integer from 0 through 2147483647')
    if operation == 'set_connection_pragma':
        if request.get('confirmed') is not True:
            raise RelationalClientError('Confirm the original connection setting')
        if type(request.get('expected_value')) is not int or not 0 <= request['expected_value'] <= MAXIMUM:
            raise RelationalClientError('Refresh the original native setting')
        if name in CALLBACKS and request.get('replace_callback_confirmed') is not True:
            raise RelationalClientError('Confirm replacement of the native callback policy')
    cursor = connection.cursor()
    try:
        def read():
            row = cursor.execute('PRAGMA ' + name).fetchone()
            if not row or type(row[0]) is not int or not 0 <= row[0] <= MAXIMUM:
                raise RelationalClientError('Native numeric PRAGMA unavailable or unrecognized')
            return row[0]
        try:
            before = read()
        except Exception as error:
            failure = RelationalClientError('Native setting observation unavailable or refused; setter not dispatched')
            failure.native_outcome = 'not_dispatched'
            raise failure from error
        statement = 'PRAGMA ' + name + '=' + str(request.get('value', before))
        if operation == 'set_connection_pragma':
            if before != request['expected_value']:
                raise RelationalClientError('Original native setting changed; inspect and review again')
            try:
                cursor.execute(statement)
                after = read()
            except Exception as error:
                failure = RelationalClientError('Native numeric PRAGMA outcome is unconfirmed; inspect before retrying')
                failure.native_outcome = 'unknown_outcome'
                raise failure from error
            if after != request['value']:
                failure = RelationalClientError('Native numeric PRAGMA postcondition is unconfirmed; inspect before retrying')
                failure.native_outcome = 'unknown_outcome'
                raise failure
        else:
            after = before
        result = {'pragma': name, 'units': UNITS[name], 'scope': 'original-connection',
            'before_value': before, 'effective_value': after,
            'transaction_open': connection.in_transaction, 'commit_requested': False,
            'rollback_requested': False, 'file_persisted': False,
            'future_connection_defaults_changed': False, 'automatic_retry': False}
        if name in CALLBACKS:
            result.update(callback_policy=CALLBACKS[name],
                previous_callback_identity='unobservable',
                callback_replacement_requested=operation == 'set_connection_pragma',
                callback_restoration_claimed=False)
        if operation != 'inspect':
            result.update(expected_value=before, requested_value=request['value'], native_statement=statement)
        if operation == 'review':
            result.update(ready_to_apply=True, warning='Native connection configuration is not restored by transaction rollback.')
        if operation == 'set_connection_pragma':
            result['outcome'] = 'applied'
        return result
    finally:
        cursor.close()

"""Original main-connection synchronous policy; never a file-wide default."""
from ...sdk.relational import RelationalClientError

MODES = {'OFF': 0, 'NORMAL': 1, 'FULL': 2, 'EXTRA': 3}


def action(connection, request):
    operation = request.get('operation')
    fields = {'inspect': {'operation'}, 'review': {'operation', 'value'},
        'set_connection_synchronous': {'operation', 'value', 'expected_code', 'confirmed'}}
    if not isinstance(operation, str) or operation not in fields or set(request) - fields[operation]:
        raise RelationalClientError('Select a typed original-connection setting')
    if operation != 'inspect' and (not isinstance(request.get('value'), str) or request['value'] not in MODES):
        raise RelationalClientError('Select a native synchronous mode')
    if operation == 'set_connection_synchronous':
        if request.get('confirmed') is not True:
            raise RelationalClientError('Confirm a native synchronous mode')
        if type(request.get('expected_code')) is not int or request['expected_code'] not in MODES.values():
            raise RelationalClientError('Refresh the original synchronous mode')
        if connection.in_transaction:
            raise RelationalClientError('End the caller transaction before changing synchronous')
    cursor = connection.cursor()
    try:
        def read():
            row = cursor.execute('PRAGMA main.synchronous').fetchone()
            if not row or type(row[0]) is not int or row[0] not in MODES.values():
                raise RelationalClientError('Native synchronous observation unavailable; inspect the original connection before retrying')
            return row[0]
        before = read()
        if operation == 'set_connection_synchronous':
            if before != request['expected_code']:
                raise RelationalClientError('Original synchronous policy changed; refresh and review')
            cursor.execute('PRAGMA main.synchronous=' + request['value'])
        after = read()
        if operation == 'set_connection_synchronous' and after != MODES[request['value']]:
            raise RelationalClientError('Native synchronous postcondition is unconfirmed; inspect before retrying')
        return {'scope': 'original-connection-main', 'before_code': before,
            'effective_code': after, 'effective_mode': next(name for name, code in MODES.items() if code == after),
            'file_persisted': False, 'future_connection_defaults_changed': False,
            'commit_requested': False, 'rollback_requested': False,
            'transaction_open': connection.in_transaction,
            **({'native_statement': 'PRAGMA main.synchronous=' + request['value'],
                'expected_code': before, 'ready_to_apply': not connection.in_transaction}
               if operation == 'review' else {})}
    finally:
        cursor.close()

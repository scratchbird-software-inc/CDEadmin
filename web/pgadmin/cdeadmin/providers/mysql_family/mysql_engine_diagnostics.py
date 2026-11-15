"""Reviewed native engine diagnostics on a dedicated MySQL connection."""
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone

from ...sdk import RelationalClientError
from .mysql_instance import environment, target_uuid

OPERATIONS = {
    'show_engine_status': 'Inspect native engine status',
    'show_engine_logs': 'Inspect native engine logs',
    'show_engine_mutex': 'Inspect native engine mutex diagnostics',
}
SUFFIXES = dict(zip(OPERATIONS, ('STATUS', 'LOGS', 'MUTEX')))
MAX_ROWS = 256
MAX_BYTES = 1024 * 1024
ALL_MAX_ROWS = 4096
ALL_MAX_BYTES = 8 * 1024 * 1024


def compile_operation(operation, draft, target):
    if operation not in OPERATIONS or not isinstance(draft, Mapping):
        raise RelationalClientError('Select a native MySQL engine diagnostic')
    uuid = target_uuid(target)
    if (set(draft) - {'engine', 'engine_scope', 'private_data_confirmed', 'confirmation'} or
            not {'private_data_confirmed', 'confirmation'} <= set(draft)):
        raise RelationalClientError('Select the exact engine and private diagnostic review fields')
    scope = draft.get('engine_scope', 'ENGINE')
    if not isinstance(scope, str) or scope not in {'ENGINE', 'ALL'}:
        raise RelationalClientError('Select one installed engine or native ALL-engine scope')
    engine = draft.get('engine')
    if scope == 'ALL':
        if engine not in (None, ''):
            raise RelationalClientError('Omit the individual engine name when selecting all engines')
        selection = 'ALL'
    else:
        if not isinstance(engine, str) or not engine or len(engine) > 64 or '\x00' in engine:
            raise RelationalClientError('Select one installed native engine name')
        selection = '`' + engine.replace('`', '``') + '`'
    if draft['private_data_confirmed'] is not True or draft['confirmation'] != target['display_name']:
        raise RelationalClientError('Confirm private diagnostic access and the exact native server')
    return {'statements': [{'source': 'SHOW ENGINE ' + selection + ' ' + SUFFIXES[operation],
                            'parameters': ()}],
            'mysql_engine_diagnostics': {'operation': operation, 'draft': dict(draft),
                'target': deepcopy(dict(target)), 'server_uuid': uuid, 'engine_scope': scope},
            'warnings': [
                'Native engine diagnostics can contain other sessions\' SQL, transaction details and server paths. Explicit private inspection is required.',
                'STATUS and MUTEX require native PROCESS privilege; LOGS requires native FILE privilege. The server checks current effective privileges.',
                'Single-engine output is bounded to 256 rows and 1 MiB; ALL output to 4096 rows and 8 MiB. Truncation is explicit. No returned rows means only that the native handler returned no rows, not that the engine implements that diagnostic.',
                'This is a dedicated native observer, not an interactive session or a monitoring-history write. No action is automatically replayed.',
            ]}


def engine_state(cursor, name, scope='ENGINE'):
    if scope == 'ALL':
        cursor.execute('SELECT ENGINE,SUPPORT FROM information_schema.ENGINES ORDER BY ENGINE LIMIT 129')
        rows = cursor.fetchmany(129)
        if not rows or len(rows) > 128 or any(
                len(row) != 2 or not isinstance(row[0], str) or
                row[1] not in {'YES', 'DEFAULT', 'NO', 'DISABLED'} for row in rows):
            raise RelationalClientError('The complete native storage-engine inventory is unavailable')
        return {'scope': 'ALL', 'engines': [list(row) for row in rows]}
    cursor.execute('SELECT ENGINE,SUPPORT FROM information_schema.ENGINES WHERE ENGINE=%s', (name,))
    rows = cursor.fetchmany(2)
    if len(rows) != 1 or rows[0][1] not in {'YES', 'DEFAULT'}:
        raise RelationalClientError('The selected native storage engine is unavailable or disabled')
    return {'engine': rows[0][0], 'support': rows[0][1]}


def observer_route(payload):
    route = dict(payload['route'])
    for key in ('pool_name', 'pool_size', 'pool_reset_connection', 'pool_reset_session'):
        route.pop(key, None)
    route.update(connection_timeout=5, read_timeout=5, write_timeout=5)
    return route


def release(client, handle, cursor):
    """Report cleanup separately; leave a failed handle owned by the client."""
    receipt = {'cursor_released': cursor is None, 'connection_released': False}
    if cursor is not None:
        try:
            cursor.close()
            receipt['cursor_released'] = True
        except Exception:
            # An unread truncated result may prevent cursor close. The
            # dedicated connection must still be closed, never pooled.
            pass
    try:
        handle.close()
        receipt['connection_released'] = True
    except Exception:
        pass
    if receipt['connection_released']:
        client._forget_connection(handle)
    return receipt


def bind_review(client, planned):
    payload = planned['provider_payload']; intent = payload['compiled']['mysql_engine_diagnostics']
    handle = client._connect({'route': observer_route(payload)}); cursor = None
    ready = False
    try:
        handle.autocommit = True; cursor = handle.cursor(); identity = environment(cursor)
        if identity['server_uuid'] != intent['server_uuid']:
            raise RelationalClientError('The native diagnostic server differs from the selected server')
        selected = engine_state(cursor, intent['draft'].get('engine'), intent['engine_scope'])
        intent['review'] = {'execution_identity': identity, 'engine': selected}
        planned['command_preview'].update(native_execution_identity=identity, native_engine=selected)
        ready = True
        return planned
    finally:
        cleanup = release(client, handle, cursor)
        if ready and not cleanup['connection_released']:
            raise RelationalClientError('Diagnostic review connection release is unconfirmed')


def bounded_result(cursor, all_engines=False):
    """Native values remain text; do not parse or invent engine-specific facts."""
    columns = [item[0] for item in cursor.description or ()]
    if columns != ['Type', 'Name', 'Status']:
        raise RelationalClientError('Native engine diagnostic result metadata changed')
    limit = ALL_MAX_ROWS if all_engines else MAX_ROWS
    byte_limit = ALL_MAX_BYTES if all_engines else MAX_BYTES
    rows, size, truncated = [], 0, False
    for _ in range(limit + 1):
        row = cursor.fetchone()
        if row is None:
            break
        if len(row) != 3 or any(not isinstance(value, str) for value in row):
            raise RelationalClientError('Native engine diagnostic text is unavailable')
        cost = sum(len(value.encode('utf8')) for value in row)
        if len(rows) >= limit or size + cost > byte_limit:
            truncated = True
            break
        rows.append(list(row)); size += cost
    return {'columns': columns, 'rows': rows, 'complete': not truncated,
            'truncated': truncated, 'row_limit': limit, 'text_byte_limit': byte_limit,
            'returned_text_bytes': size,
            'interpretation': ('bounded-native-partial-output' if truncated else
                               'native-rows' if rows else 'native-no-rows-returned')}


def apply(client, request, connection=None):
    if connection is not None:
        raise RelationalClientError('Engine diagnostics require an independently owned connection')
    payload = request['provider_payload']; compiled = payload['compiled']
    intent = compiled['mysql_engine_diagnostics']; checked = deepcopy(compiled)
    review = checked['mysql_engine_diagnostics'].pop('review', None)
    if not isinstance(review, Mapping) or compile_operation(intent['operation'], intent['draft'], intent['target']) != checked:
        raise RelationalClientError('Review the exact native engine diagnostic before dispatch')
    handle = client._connect({'route': observer_route(payload)}); cursor = None
    dispatched = acknowledged = False
    response = failure = None
    try:
        handle.autocommit = True; cursor = handle.cursor(); identity = environment(cursor)
        selected = engine_state(cursor, intent['draft'].get('engine'), intent['engine_scope'])
        if identity != review['execution_identity'] or selected != review['engine']:
            raise RelationalClientError('Native server, principal, roles or installed engine changed since review')
        dispatched = True
        cursor.execute(compiled['statements'][0]['source'])
        result = bounded_result(cursor, intent['engine_scope'] == 'ALL')
        acknowledged = result['complete']
        response = {'accepted': True, 'native_implicit_commit': False,
                'commit_requested': False, 'rollback_requested': False,
                'staged_in_provider_session': False, 'automatic_retry': False,
                'transaction_finality_interpreted_by_common_code': False,
                'engine_diagnostic': {**result, 'operation': intent['operation'],
                    'engine': selected, 'execution_identity': identity,
                    'observed_at': datetime.now(timezone.utc).isoformat(),
                    'native_dispatched': True, 'native_acknowledged': acknowledged,
                    'native_completion': ('acknowledged' if acknowledged else
                                          'unconfirmed-output-truncated'),
                    'connection': 'dedicated-observer', 'private_content': True}}
        return response
    except Exception as error:
        failure = error if isinstance(error, RelationalClientError) else RelationalClientError(
            'Native MySQL engine diagnostic failed (' + type(error).__name__ + ')')
        failure.native_dispatched = dispatched; failure.native_acknowledged = acknowledged
        failure.automatic_retry = False
        failure.errno = getattr(error, 'errno', None); failure.sqlstate = getattr(error, 'sqlstate', None)
        failure.native_status_codes = (failure.errno,) if type(failure.errno) is int else ()
        raise failure from None
    finally:
        # An incomplete native result is discarded with this owned connection;
        # it must never be returned to an interactive connection/pool.
        cleanup = release(client, handle, cursor)
        if response is not None:
            response['connection_release'] = cleanup
        elif failure is not None:
            failure.connection_release = cleanup

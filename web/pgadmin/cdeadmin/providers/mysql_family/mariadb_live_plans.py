"""Review-bound native MariaDB SHOW EXPLAIN / ANALYZE observers."""
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
import re

from ...sdk import RelationalClientError
from .mariadb_server_diagnostics import target_uid, environment, form as diagnostic_form
from .mysql_engine_diagnostics import observer_route, release
from .mariadb_values import value

OPERATIONS = {
    'inspect_live_explain': ('Inspect running query plan', 'EXPLAIN'),
    'inspect_live_analyze': ('Inspect running query execution statistics', 'ANALYZE'),
}
KEY = 'mariadb_live_plan'
MAX_ROWS = 256
MAX_BYTES = 1024 * 1024


def form(operation):
    return diagnostic_form(operation)


def compile_operation(operation, draft, target):
    if operation not in OPERATIONS or not isinstance(draft, Mapping):
        raise RelationalClientError('Select a typed MariaDB running-query diagnostic')
    uid = target_uid(target)
    if set(draft) - {'connection_id', 'output_format', 'private_data_confirmed', 'confirmation'}:
        raise RelationalClientError('Select only typed running-query diagnostic fields')
    identifier = draft.get('connection_id')
    if (not isinstance(identifier, str) or not re.fullmatch(r'[1-9][0-9]{0,19}', identifier)
            or int(identifier) > 18446744073709551615):
        raise RelationalClientError('Select an exact positive unsigned native connection ID')
    output = draft.get('output_format', 'TABULAR')
    if output not in ('TABULAR', 'JSON'):
        raise RelationalClientError('Select native TABULAR or JSON output')
    if draft.get('private_data_confirmed') is not True or draft.get('confirmation') != target['display_name']:
        raise RelationalClientError('Confirm private plan access and the exact native server')
    sql = 'SHOW ' + OPERATIONS[operation][1] + (' FORMAT=JSON' if output == 'JSON' else '') + ' FOR ' + identifier
    return {'statements': [{'source': sql, 'parameters': ()}],
            KEY: {'operation': operation, 'draft': deepcopy(dict(draft)), 'target': deepcopy(dict(target)), 'server_uid': uid},
            'warnings': [
                'Private running-query plans can expose SQL expressions, object names and values from other sessions.',
                'Native users may inspect their own user sessions; inspecting another user requires native PROCESS authority. Visibility is not an existence proof.',
                'Review and execution compare native QUERY_ID and session facts; this is not an atomic reservation of a running query.',
                'The observer uses a dedicated connection and never executes ANALYZE on the original session. No monitoring history is written.',
                'Output is bounded to 256 rows/1 MiB. Native requests may wait up to 30 seconds; a client timeout does not prove server cancellation. No automatic retry.',
            ]}


def subject(cursor, identifier):
    cursor.execute('SELECT ID,USER,HOST,DB,COMMAND,QUERY_ID FROM information_schema.PROCESSLIST WHERE ID=%s', (int(identifier),))
    rows = cursor.fetchmany(2)
    if len(rows) != 1 or len(rows[0]) != 6 or rows[0][4] != 'Query' or not rows[0][5]:
        raise RelationalClientError('The selected active query is unavailable or not visible to this native principal')
    # QUERY_ID is a native generation, not the query text or a fabricated hash.
    return dict(zip(('connection_id', 'user', 'host', 'database', 'command', 'query_id'),
                    [str(v) if type(v) is int else v for v in rows[0]]))


def bind_review(client, planned):
    payload = planned['provider_payload']; intent = payload['compiled'][KEY]
    handle = client._connect({'route': observer_route(payload)}); cursor = None
    try:
        handle.autocommit = True; cursor = handle.cursor()
        identity = environment(cursor)
        if identity['server_uid'] != intent['server_uid']:
            raise RelationalClientError('The running-query server differs from the selected server')
        observed = subject(cursor, intent['draft']['connection_id'])
        intent['review'] = {'execution_identity': identity, 'subject': observed}
        planned['command_preview'].update(native_execution_identity=identity, native_query_identity=observed)
        return planned
    finally:
        if not release(client, handle, cursor)['connection_released']:
            raise RelationalClientError('Running-query review connection release is unconfirmed')


def bounded_result(cursor):
    columns = [item[0] for item in cursor.description or ()]
    if not columns or len(columns) > 64 or any(not isinstance(c, str) for c in columns):
        raise RelationalClientError('Native running-query result metadata is unavailable')
    rows = []; size = 0; truncated = False
    for _ in range(MAX_ROWS + 1):
        row = cursor.fetchone()
        if row is None:
            break
        if len(row) != len(columns):
            raise RelationalClientError('Native running-query result width changed')
        import json
        cells = [value(cell) for cell in row]
        cost = len(json.dumps(cells, ensure_ascii=False).encode('utf8'))
        if len(rows) >= MAX_ROWS or size + cost > MAX_BYTES:
            truncated = True; break
        rows.append(cells); size += cost
    return dict(columns=columns, rows=rows, complete=not truncated, truncated=truncated,
                row_limit=MAX_ROWS, text_byte_limit=MAX_BYTES, returned_text_bytes=size)


def apply(client, request, connection=None):
    if connection is not None:
        raise RelationalClientError('Running-query inspection requires a dedicated observer')
    payload = request['provider_payload']; compiled = payload['compiled']; intent = compiled[KEY]
    checked = deepcopy(compiled); review = checked[KEY].pop('review', None)
    if not isinstance(review, Mapping) or compile_operation(intent['operation'], intent['draft'], intent['target']) != checked:
        raise RelationalClientError('Review the exact native running-query diagnostic before dispatch')
    handle = client._connect({'route': observer_route(payload)}); cursor = None
    dispatched = acknowledged = False; result = failure = None
    try:
        handle.autocommit = True; cursor = handle.cursor()
        identity = environment(cursor)
        observed = subject(cursor, intent['draft']['connection_id'])
        if identity != review['execution_identity'] or observed != review['subject']:
            raise RelationalClientError('Native execution identity or running query changed after review')
        dispatched = True; cursor.execute(compiled['statements'][0]['source'])
        output = bounded_result(cursor)
        if output['complete']:
            if subject(cursor, intent['draft']['connection_id']) != observed:
                raise RelationalClientError('The running query changed during observation; its output is withheld')
            acknowledged = True
        else:
            # No further query may run with an unread native result. Discard it
            # by closing the owned observer and withhold unfenced partial rows.
            output['rows'] = []
            output['returned_text_bytes'] = 0
        result = dict(accepted=True, commit_requested=False, rollback_requested=False,
            native_implicit_commit=False, staged_in_provider_session=False, automatic_retry=False,
            transaction_finality_interpreted_by_common_code=False,
            live_plan={**output, 'operation': intent['operation'], 'execution_identity': identity,
                'subject': observed, 'native_dispatched': True, 'native_acknowledged': acknowledged,
                'identity_revalidated_after_read': acknowledged, 'atomic_query_reservation': False,
                'native_completion': 'acknowledged' if acknowledged else 'unconfirmed-output-truncated',
                'private_content': True, 'connection': 'dedicated-observer',
                'observed_at': datetime.now(timezone.utc).isoformat()})
        return result
    except Exception as error:
        failure = error if isinstance(error, RelationalClientError) else RelationalClientError(
            'Native MariaDB running-query diagnostic failed (' + type(error).__name__ + ')')
        failure.errno = getattr(error, 'errno', None); failure.sqlstate = getattr(error, 'sqlstate', None)
        failure.native_dispatched = dispatched; failure.native_acknowledged = acknowledged
        failure.automatic_retry = False
        failure.native_status_codes = (failure.errno,) if type(failure.errno) is int else ()
        raise failure from None
    finally:
        cleanup = release(client, handle, cursor)
        if result is not None: result['connection_release'] = cleanup
        elif failure is not None: failure.connection_release = cleanup

"""Review-bound native MySQL 9.7 EXPLAIN FOR CONNECTION observer."""
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
import json
import re
import uuid

from ...sdk import RelationalClientError
from .mysql_catalog import _value
from .mysql_engine_diagnostics import observer_route, release
from .mysql_instance import environment, target_uuid

KEY = 'mysql_live_plan'
OPERATIONS = {
    'explain_for_connection': 'Inspect running query plan',
}
SESSION_OPERATIONS = {
    'explain_for_connection': 'Inspect session query plan',
}
FORMATS = ('TRADITIONAL', 'JSON', 'TREE')
MAX_ROWS = 512
MAX_BYTES = 2 * 1024 * 1024


def _resolve_target_uuid_and_conn(draft, target):
    if not isinstance(target, Mapping):
        raise RelationalClientError('Select a native MySQL server or session')
    kind = target.get('resource_kind')
    if kind == 'server':
        server_uuid = target_uuid(target)
        conn_id = draft.get('connection_id')
    elif kind == 'session':
        native = target.get('native') or {}
        server_uuid = native.get('server_uuid')
        if server_uuid is not None and (
            not isinstance(server_uuid, str)
            or not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', server_uuid)
        ):
            raise RelationalClientError('Invalid MySQL server_uuid on session resource')
        conn_id = draft.get('connection_id') or native.get('processlist_id') or target.get('display_name')
    else:
        raise RelationalClientError('Select a native MySQL server or session resource')
    if isinstance(conn_id, int) and not isinstance(conn_id, bool):
        conn_id = str(conn_id)
    if (
        not isinstance(conn_id, str)
        or not re.fullmatch(r'[1-9][0-9]{0,19}', conn_id)
        or int(conn_id) > 18446744073709551615
    ):
        raise RelationalClientError('Select an exact positive unsigned MySQL connection ID')
    return kind, server_uuid, conn_id


def compile_operation(operation, draft, target):
    if operation != 'explain_for_connection' or not isinstance(draft, Mapping):
        raise RelationalClientError('Select typed MySQL EXPLAIN FOR CONNECTION options')
    allowed = {'connection_id', 'output_format', 'private_data_confirmed', 'confirmation'}
    if set(draft) - allowed:
        raise RelationalClientError('Unknown MySQL EXPLAIN FOR CONNECTION option')
    kind, server_uuid, conn_id = _resolve_target_uuid_and_conn(draft, target)
    output_format = draft.get('output_format', 'TRADITIONAL') or 'TRADITIONAL'
    if output_format not in FORMATS:
        raise RelationalClientError('Select TRADITIONAL, JSON, or TREE output format')
    if draft.get('private_data_confirmed') is not True or draft.get('confirmation') != target.get('display_name'):
        raise RelationalClientError('Confirm private plan access and the exact target display name')
    sql = f'EXPLAIN FORMAT={output_format} FOR CONNECTION {conn_id}'
    return {
        'statements': [{'source': sql, 'parameters': ()}],
        KEY: {
            'resource_kind': kind,
            'operation': operation,
            'connection_id': conn_id,
            'output_format': output_format,
            'draft': deepcopy(dict(draft)),
            'target': deepcopy(dict(target)),
            'server_uuid': server_uuid,
        },
        'warnings': [
            'EXPLAIN FOR CONNECTION can expose table names, predicates, and literal values from another session.',
            'Inspecting another MySQL user session requires native PROCESS privilege; same-user sessions are permitted natively.',
            'This observer never executes user SQL. Idle connections or non-explainable statements (error 3012) and unknown threads (error 1094) are reported distinctly.',
        ],
    }


def observe_subject(cursor, conn_id):
    try:
        cursor.execute(
            'SELECT CAST(PROCESSLIST_ID AS CHAR), PROCESSLIST_USER, PROCESSLIST_HOST, '
            'PROCESSLIST_DB, PROCESSLIST_COMMAND, PROCESSLIST_STATE, CAST(THREAD_ID AS CHAR) '
            'FROM performance_schema.threads WHERE PROCESSLIST_ID = %s',
            (int(conn_id),),
        )
        rows = cursor.fetchall()
        if len(rows) == 1:
            r = rows[0]
            return {
                'visible': True,
                'source': 'performance_schema.threads',
                'connection_id': str(r[0]),
                'user': r[1],
                'host': r[2],
                'database': r[3],
                'command': r[4],
                'state': r[5],
                'thread_id': str(r[6]),
            }
    except Exception as exc:
        if getattr(exc, 'errno', None) not in {1142, 1044}:
            raise
    cursor.execute(
        'SELECT CAST(ID AS CHAR), USER, HOST, DB, COMMAND, STATE '
        'FROM information_schema.PROCESSLIST WHERE ID = %s',
        (int(conn_id),),
    )
    prows = cursor.fetchall()
    if len(prows) == 1:
        r = prows[0]
        return {
            'visible': True,
            'source': 'information_schema.PROCESSLIST',
            'connection_id': str(r[0]),
            'user': r[1],
            'host': r[2],
            'database': r[3],
            'command': r[4],
            'state': r[5],
            'thread_id': None,
        }
    return {'visible': False, 'connection_id': str(conn_id)}


def _has_process_privilege(cursor):
    try:
        cursor.execute(
            "SELECT 1 FROM information_schema.USER_PRIVILEGES WHERE PRIVILEGE_TYPE = 'PROCESS' LIMIT 1"
        )
        if cursor.fetchall():
            return True
        cursor.execute(
            "SELECT 1 FROM performance_schema.threads WHERE TYPE = 'BACKGROUND' LIMIT 1"
        )
        return bool(cursor.fetchall())
    except Exception:
        return False


def bind_review(client, planned):
    payload = planned['provider_payload']
    intent = payload['compiled'][KEY]
    handle = client._connect({'route': observer_route(payload)})
    cursor = None
    ready = False
    try:
        handle.autocommit = True
        cursor = handle.cursor()
        identity = environment(cursor)
        if intent.get('server_uuid') and identity['server_uuid'] != intent['server_uuid']:
            raise RelationalClientError('Live MySQL server_uuid differs from the selected target')
        intent['server_uuid'] = identity['server_uuid']
        subject = observe_subject(cursor, intent['connection_id'])
        has_process = _has_process_privilege(cursor)
        intent['review'] = {
            'execution_identity': identity,
            'subject': subject,
            'has_process_privilege': has_process,
            'review_nonce': uuid.uuid4().hex,
        }
        planned['command_preview'].update(
            native_execution_identity=identity,
            native_query_subject=subject,
            process_privilege_observed=has_process,
        )
        ready = True
        return planned
    finally:
        cleanup = release(client, handle, cursor)
        if ready and not cleanup['connection_released']:
            raise RelationalClientError('MySQL EXPLAIN FOR CONNECTION review connection release is unconfirmed')


def _bounded_explain_rows(cursor, output_format):
    columns = [str(col[0]) for col in (cursor.description or ())]
    rows = []
    size = 0
    truncated = False
    for _ in range(MAX_ROWS + 1):
        row = cursor.fetchone()
        if row is None:
            break
        cells = [_value(cell) for cell in row]
        cost = len(json.dumps(cells, ensure_ascii=False).encode('utf-8'))
        if len(rows) >= MAX_ROWS or size + cost > MAX_BYTES:
            truncated = True
            break
        rows.append(cells)
        size += cost
    parsed_json = None
    if not truncated and output_format == 'JSON' and len(rows) == 1 and len(rows[0]) == 1 and isinstance(rows[0][0], str):
        try:
            parsed_json = json.loads(rows[0][0])
        except ValueError:
            parsed_json = None
    return {
        'columns': columns,
        'rows': rows if not truncated else [],
        'complete': not truncated,
        'truncated': truncated,
        'row_limit': MAX_ROWS,
        'text_byte_limit': MAX_BYTES,
        'returned_text_bytes': size if not truncated else 0,
        'parsed_json': parsed_json,
    }


def apply(client, request, connection=None):
    if connection is not None:
        raise RelationalClientError('MySQL EXPLAIN FOR CONNECTION requires a dedicated observer connection')
    payload = request['provider_payload']
    compiled = payload['compiled']
    intent = compiled[KEY]
    checked = deepcopy(compiled)
    review = checked[KEY].pop('review', None)
    # Restore original target's server_uuid before deterministic compile comparison
    orig_target_uuid = (intent['target'].get('native') or {}).get('server_uuid')
    if checked[KEY]['resource_kind'] == 'session' and orig_target_uuid is None:
        checked[KEY]['server_uuid'] = None
    if not isinstance(review, Mapping) or compile_operation(
        intent['operation'], intent['draft'], intent['target']
    ) != checked:
        raise RelationalClientError('Review the exact MySQL EXPLAIN FOR CONNECTION request before dispatch')
    consumed = getattr(client, '_consumed_live_plan_reviews', None)
    if consumed is None:
        consumed = set()
        client._consumed_live_plan_reviews = consumed
    nonce = review.get('review_nonce')
    if not isinstance(nonce, str) or nonce in consumed:
        raise RelationalClientError('This reviewed EXPLAIN FOR CONNECTION plan was already consumed; replay is refused')

    handle = client._connect({'route': observer_route(payload)})
    cursor = None
    dispatched = acknowledged = False
    response = failure = None
    try:
        handle.autocommit = True
        cursor = handle.cursor()
        identity = environment(cursor)
        if identity != review.get('execution_identity'):
            raise RelationalClientError('MySQL server, principal, or active role changed since review')
        subject_before = observe_subject(cursor, intent['connection_id'])
        consumed.add(nonce)
        dispatched = True
        cursor.execute(compiled['statements'][0]['source'])
        output = _bounded_explain_rows(cursor, intent['output_format'])
        acknowledged = output['complete']
        subject_after = observe_subject(cursor, intent['connection_id']) if output['complete'] else None
        plan_state = (
            'truncated_withheld' if output['truncated']
            else 'idle_no_explainable_statement' if len(output['rows']) == 0
            else 'captured'
        )
        response = {
            'accepted': True,
            'commit_requested': False,
            'rollback_requested': False,
            'native_implicit_commit': False,
            'staged_in_provider_session': False,
            'automatic_retry': False,
            'sql_executed_from_user_input': False,
            'transaction_finality_interpreted_by_common_code': False,
            'live_plan': {
                **output,
                'operation': intent['operation'],
                'connection_id': intent['connection_id'],
                'output_format': intent['output_format'],
                'plan_state': plan_state,
                'execution_identity': identity,
                'subject_before': subject_before,
                'subject_after': subject_after,
                'native_dispatched': True,
                'native_acknowledged': acknowledged,
                'native_completion': 'acknowledged' if acknowledged else 'unconfirmed-output-truncated',
                'connection': 'dedicated-observer',
                'private_content': True,
                'observed_at': datetime.now(timezone.utc).isoformat(),
            },
        }
        return response
    except Exception as exc:
        errno = getattr(exc, 'errno', None)
        sqlstate = getattr(exc, 'sqlstate', None)
        if isinstance(exc, RelationalClientError):
            failure = exc
        elif errno == 3012:
            failure = RelationalClientError(
                f'Target connection {intent["connection_id"]} is idle or executing a non-explainable statement (MySQL error 3012)'
            )
            failure.native_outcome = 'idle_or_non_explainable'
        elif errno == 1094:
            failure = RelationalClientError(
                f'Unknown MySQL connection thread ID {intent["connection_id"]} (MySQL error 1094)'
            )
            failure.native_outcome = 'unknown_thread'
        elif errno in {1044, 1045, 1142, 1227}:
            failure = RelationalClientError(
                f'Native privilege denied inspecting connection {intent["connection_id"]} (PROCESS required for other users; error {errno})'
            )
            failure.native_outcome = 'privilege_denied'
        else:
            failure = RelationalClientError(
                f'Native MySQL EXPLAIN FOR CONNECTION failed ({type(exc).__name__}): {exc}'
            )
            failure.native_outcome = 'failed'
        failure.errno = errno
        failure.sqlstate = sqlstate
        failure.native_status_codes = (errno,) if type(errno) is int else ()
        failure.native_dispatched = dispatched
        failure.native_acknowledged = acknowledged
        failure.automatic_retry = False
        raise failure from None
    finally:
        cleanup = release(client, handle, cursor)
        if response is not None:
            response['connection_release'] = cleanup
        elif failure is not None:
            failure.connection_release = cleanup

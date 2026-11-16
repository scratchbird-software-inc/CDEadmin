"""Native MariaDB prepared-XID observation and externally authorized resolution."""
from collections.abc import Mapping
from copy import deepcopy
import re

from ...sdk import RelationalClientError
from .mariadb_server_diagnostics import environment, target_uid, form
from .mysql_engine_diagnostics import observer_route, release

KEY = 'mariadb_prepared_xa'
RECOVER = 'XA RECOVER FORMAT=RAW'
OPERATIONS = {op: (title, '') for op, title in (
    ('inspect_prepared_xa', 'Inspect prepared transactions'),
    ('commit_prepared_xa', 'Commit a prepared transaction'),
    ('rollback_prepared_xa', 'Roll back a prepared transaction'))}


def identity(draft):
    result = {}
    for name in ('gtrid_hex', 'bqual_hex'):
        value = draft.get(name)
        if not isinstance(value, str) or not re.fullmatch(r'(?:[0-9a-fA-F]{2}){0,64}', value):
            raise RelationalClientError('Select exact hexadecimal XID parts of at most 64 bytes each')
        result[name] = value.upper()
        result[name.replace('_hex', '_length')] = len(value) // 2
    fmt = draft.get('format_id')
    if not isinstance(fmt, str) or not re.fullmatch(r'(?:0|[1-9][0-9]{0,9})', fmt) or not 0 <= int(fmt) <= 2**31-1:
        raise RelationalClientError('Native SQL resolution requires exact format ID text from 0 through 2147483647')
    result['format_id'] = str(int(fmt))
    return result


def xid_source(xid):
    return "X'" + xid['gtrid_hex'] + "',X'" + xid['bqual_hex'] + "'," + xid['format_id']


def observe(cursor):
    cursor.execute(RECOVER)
    if [c[0] for c in cursor.description or ()] != ['formatID', 'gtrid_length', 'bqual_length', 'data']:
        raise RelationalClientError('Native XA recovery metadata changed')
    result = []
    for _ in range(20001):
        row = cursor.fetchone()
        if row is None: break
        if (len(row) != 4 or type(row[0]) is not int or not -(2**63) <= row[0] < 2**63
                or any(type(n) is not int or not 0 <= n <= 64 for n in row[1:3])
                or not isinstance(row[3], bytes) or len(row[3]) != row[1] + row[2]):
            raise RelationalClientError('Native XA recovery did not return exact binary identities')
        if len(result) == 20000:
            raise RelationalClientError('Native XA recovery exceeds the 20000-branch budget')
        result.append(dict(format_id=str(row[0]), gtrid_length=row[1], bqual_length=row[2],
            gtrid_hex=row[3][:row[1]].hex().upper(), bqual_hex=row[3][row[1]:].hex().upper()))
    result.sort(key=lambda v: (int(v['format_id']), v['gtrid_hex'], v['bqual_hex']))
    if any(a == b for a, b in zip(result, result[1:])):
        raise RelationalClientError('Native XA recovery has ambiguous duplicate identities')
    return result


def compile_operation(operation, draft, target):
    if operation not in OPERATIONS or not isinstance(draft, Mapping):
        raise RelationalClientError('Select a native prepared transaction workflow')
    uid = target_uid(target)
    inspection = operation == 'inspect_prepared_xa'
    allowed = {'confirmation'} if inspection else {'confirmation', 'gtrid_hex', 'bqual_hex', 'format_id', 'decision_reference'}
    if set(draft) - allowed or draft.get('confirmation') != target['display_name']:
        raise RelationalClientError('Confirm the exact native server and typed XA fields')
    xid = None
    if not inspection:
        reference = draft.get('decision_reference')
        if not isinstance(reference, str) or not reference.strip() or len(reference) > 1024 or '\0' in reference:
            raise RelationalClientError('Record the authorized external transaction-manager decision')
        xid = identity(draft)
    sql = RECOVER if inspection else ('XA COMMIT ' if operation == 'commit_prepared_xa' else 'XA ROLLBACK ') + xid_source(xid)
    return {'statements': [{'source': sql, 'parameters': ()}], KEY: {
        'operation': operation, 'draft': deepcopy(dict(draft)), 'target': deepcopy(dict(target)),
        'server_uid': uid, 'xid': xid}, 'warnings': [
        'Native RAW recovery returns binary XID bytes, not MySQL CONVERT XID or connection-charset text.',
        'Native SQL format IDs are 0 through 2147483647. Recovery reports out-of-range external XIDs exactly, but this native SQL interface cannot resolve them.',
        'The external transaction manager owns the decision. Record its instruction; this console does not infer global commit or participant state.',
        'A matching XID has no exposed branch-generation token. XID reuse cannot be fenced by discovery; review under the external coordinator authority.',
        'This owns an independent connection. No original-session transaction is committed or rolled back; no reconnect or replay.',
        'Native acknowledgement, later prepared-list presence and connection release are independent observations. Absence alone does not prove commit or rollback.']}


def bind_review(client, planned):
    payload = planned['provider_payload']; intent = payload['compiled'][KEY]
    handle = client._connect({'route': observer_route(payload)}); cursor = None
    try:
        handle.autocommit = True; cursor = handle.cursor(); actor = environment(cursor)
        if actor['server_uid'] != intent['server_uid']:
            raise RelationalClientError('The selected XA server differs')
        rows = observe(cursor)
        if intent['xid'] is not None and intent['xid'] not in rows:
            raise RelationalClientError('The exact XID is not currently prepared')
        intent['review'] = {'execution_identity': actor, 'selected_xid': intent['xid']}
        planned['command_preview'].update(native_execution_identity=actor, native_prepared_xa=rows)
        return planned
    finally:
        if not release(client, handle, cursor)['connection_released']:
            raise RelationalClientError('XA review connection release is unconfirmed')


def apply(client, request, connection=None):
    if connection is not None: raise RelationalClientError('Prepared XA management requires an independent connection')
    payload = request['provider_payload']; compiled = payload['compiled']; intent = compiled[KEY]
    checked = deepcopy(compiled); review = checked[KEY].pop('review', None)
    if not isinstance(review, Mapping) or compile_operation(intent['operation'], intent['draft'], intent['target']) != checked:
        raise RelationalClientError('Review the exact native XA request before dispatch')
    handle = client._connect({'route': observer_route(payload)}); cursor = None
    dispatched = acknowledged = False; result = failure = None
    try:
        handle.autocommit = True; cursor = handle.cursor(); actor = environment(cursor)
        if actor != review['execution_identity'] or review['selected_xid'] != intent['xid']:
            raise RelationalClientError('Native XA identity changed after review')
        dispatched = intent['xid'] is None
        before = observe(cursor)
        if intent['xid'] is not None and intent['xid'] not in before:
            raise RelationalClientError('The exact XID is no longer prepared')
        dispatched = True
        if intent['xid'] is None: after = before
        else:
            cursor.execute('SET SESSION lock_wait_timeout=15')
            cursor.execute(compiled['statements'][0]['source'])
            acknowledged = True
            after = observe(cursor)
        acknowledged = True
        result = dict(accepted=True, native_implicit_commit=False, commit_requested=False,
            rollback_requested=False, staged_in_provider_session=False, automatic_retry=False,
            transaction_finality_interpreted_by_common_code=False,
            xa_observation=dict(operation=intent['operation'], native_dispatched=True, native_acknowledged=True,
                execution_identity=actor, selected_xid=intent['xid'], prepared_after=after,
                sql_resolution_format_id_range=['0','2147483647'],
                external_decision_reference=intent['draft'].get('decision_reference'),
                global_transaction_decision_inferred=False, branch_generation_attested=False))
        return result
    except Exception as error:
        failure = error if isinstance(error, RelationalClientError) else RelationalClientError('Native prepared transaction workflow failed (' + type(error).__name__ + ')')
        failure.errno = getattr(error, 'errno', None); failure.sqlstate = getattr(error, 'sqlstate', None)
        failure.native_dispatched = dispatched; failure.native_acknowledged = acknowledged
        failure.native_status_codes = (failure.errno,) if type(failure.errno) is int else ()
        failure.automatic_retry = False
        raise failure from None
    finally:
        cleanup = release(client, handle, cursor)
        if result is not None: result['connection_release'] = cleanup
        elif failure is not None: failure.connection_release = cleanup

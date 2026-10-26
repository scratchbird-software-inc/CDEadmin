"""Native prepared XA inspection and explicitly requested branch resolution."""
from collections.abc import Mapping
from copy import deepcopy
import re

from ...sdk import RelationalClientError
from .mysql_instance import environment, target_uuid

RECOVER = 'XA RECOVER CONVERT XID'
OPERATIONS = {
    'inspect_prepared_xa': 'Inspect prepared XA transactions',
    'commit_prepared_xa': 'Commit a prepared XA transaction',
    'rollback_prepared_xa': 'Roll back a prepared XA transaction',
}
MAX_ROWS = 20000


def decode_row(row):
    """Decode the native binary-safe projection without a connection charset."""
    if len(row) != 4:
        raise RelationalClientError('The native XA recovery projection differs')
    format_id, gtrid_length, bqual_length, data = row
    if (type(format_id) is not int or not -(2**63) <= format_id < 2**63 or
            any(type(value) is not int or not 0 <= value <= 64
                for value in (gtrid_length, bqual_length))):
        raise RelationalClientError('Native XA identity lengths or format ID differ')
    if isinstance(data, (bytes, bytearray)):
        data = bytes(data).decode('ascii')
    if (not isinstance(data, str) or not re.fullmatch(r'0x(?:[0-9a-fA-F]{2})*', data) or
            len(data) != 2 + 2 * (gtrid_length + bqual_length)):
        raise RelationalClientError('Native XA recovery did not return exact hexadecimal bytes')
    return {'format_id': str(format_id), 'gtrid_hex': data[2:2+2*gtrid_length].upper(),
            'bqual_hex': data[2+2*gtrid_length:].upper(),
            'gtrid_length': gtrid_length, 'bqual_length': bqual_length}


def identity(draft):
    parts = []
    for key in ('gtrid_hex', 'bqual_hex'):
        value = draft.get(key)
        if not isinstance(value, str) or not re.fullmatch(r'(?:[0-9a-fA-F]{2}){0,64}', value):
            raise RelationalClientError('Use hexadecimal bytes, at most 64 per XA identity part')
        parts.append(value.upper())
    value = draft.get('format_id')
    if (not isinstance(value, str) or not re.fullmatch(r'(?:0|[1-9][0-9]{0,18})', value) or
            int(value) > 2**63-1):
        raise RelationalClientError('Use exact nonnegative native XA format ID decimal text')
    return {'format_id': value, 'gtrid_hex': parts[0], 'bqual_hex': parts[1],
            'gtrid_length': len(parts[0])//2, 'bqual_length': len(parts[1])//2}


def xid_source(xid):
    return "X'"+xid['gtrid_hex']+"',X'"+xid['bqual_hex']+"',"+xid['format_id']


def compile_operation(operation, draft, target):
    if operation not in OPERATIONS or not isinstance(draft, Mapping):
        raise RelationalClientError('Select a native prepared XA workflow')
    uuid = target_uuid(target)
    inspection = operation == 'inspect_prepared_xa'
    allowed = set() if inspection else {'gtrid_hex', 'bqual_hex', 'format_id',
        'decision_reference', 'confirmation', 'lock_wait_seconds'}
    if set(draft)-allowed:
        raise RelationalClientError('Select exact native XA workflow options')
    xid = None
    if not inspection:
        if draft.get('confirmation') != target['display_name']:
            raise RelationalClientError('Confirm the exact native XA server name')
        reference = draft.get('decision_reference')
        if not isinstance(reference, str) or not reference.strip() or len(reference) > 1024 or '\0' in reference:
            raise RelationalClientError('Record the external transaction manager decision or authorized recovery instruction')
        timeout = draft.get('lock_wait_seconds', 15)
        if type(timeout) is not int or not 1 <= timeout <= 120:
            raise RelationalClientError('Native metadata lock wait requires 1 to 120 seconds')
        xid = identity(draft)
    statement = RECOVER if inspection else ('XA COMMIT ' if operation == 'commit_prepared_xa' else 'XA ROLLBACK ') + xid_source(xid)
    return {'statements': [{'source': statement, 'parameters': ()}],
        'mysql_xa': {'operation': operation, 'server_uuid': uuid, 'xid': xid,
            'draft': dict(draft), 'target': deepcopy(dict(target))},
        'warnings': ['XA RECOVER observes server-local prepared branches. It does not establish the global transaction decision, origin, participants or branch generation.',
            'Resolve only under an authorized transaction manager decision or recovery instruction. XID reuse cannot be distinguished from the original branch by XA RECOVER.',
            'The server owns branch resolution. Native acknowledgement and later recovery-list observations are separate; an absent XID alone does not prove commit or rollback. This operation is never automatically replayed.']}


def execute_recovery(cursor):
    try:
        cursor.execute(RECOVER)
    except Exception as error:
        # Native XA recovery reports RMERR as the primary error and the
        # missing privilege as a supplementary condition. Preserve both.
        if getattr(error, 'errno', None) == 1401:
            conditions = []
            try:
                # This fixed ASCII diagnostic read needs no charset discovery.
                # On an unadmitted C observer profile the ordinary adapter's
                # fallback discovery query would replace the error area.
                if type(cursor).__module__.startswith('mysql.connector.'):
                    type(cursor).execute(cursor, b'SHOW WARNINGS LIMIT 16')
                else:
                    cursor.execute('SHOW WARNINGS LIMIT 16')
                conditions = [{'level': level, 'code': code, 'message': text}
                    for level, code, text in cursor.fetchall()]
            except Exception:
                pass  # An auxiliary read must not replace the native error.
            error.native_conditions = conditions
        raise


def failure(error, dispatched=False, acknowledged=False):
    value = error if isinstance(error, RelationalClientError) else RelationalClientError('Native MySQL prepared XA workflow failed ('+type(error).__name__+')')
    value.native_dispatched = dispatched; value.native_acknowledged = acknowledged
    value.automatic_retry = False; value.errno = getattr(error, 'errno', None)
    value.sqlstate = getattr(error, 'sqlstate', None)
    value.native_conditions = getattr(error, 'native_conditions', [])
    value.native_status_codes = tuple(dict.fromkeys(code for code in
        [value.errno]+[item['code'] for item in value.native_conditions] if type(code) is int))
    return value


def observe(cursor):
    execute_recovery(cursor)
    rows = []
    while True:
        batch = cursor.fetchmany(128)
        if not batch:
            break
        for row in batch:
            rows.append(decode_row(row))
            if len(rows) > MAX_ROWS:
                raise RelationalClientError('Native prepared XA inventory exceeds 20,000 branches')
    rows.sort(key=lambda row: (int(row['format_id']), row['gtrid_hex'], row['bqual_hex']))
    if any(a == b for a, b in zip(rows, rows[1:])):
        raise RelationalClientError('Native XA recovery returned duplicate identities')
    return rows


def bind_review(client, planned):
    payload = planned['provider_payload']; intent = payload['compiled']['mysql_xa']
    handle = client._connect({'route': payload['route']}); cursor = None
    try:
        handle.autocommit = True; cursor = handle.cursor()
        actor = environment(cursor)
        if actor['server_uuid'] != intent['server_uuid']:
            raise RelationalClientError('Native XA server differs from the selected instance')
        rows = observe(cursor)
        if intent['xid'] is not None and intent['xid'] not in rows:
            raise RelationalClientError('The exact selected XA identity is not currently prepared')
        intent['review'] = {'execution_identity': actor, 'selected_prepared_xid': intent['xid']}
        planned['command_preview'].update(native_execution_identity=actor, native_prepared_xa=rows)
        return planned
    except Exception as error:
        raise failure(error) from None
    finally:
        if cursor is not None: client._safe_close(cursor)
        client._forget_and_close(handle)


def apply(client, request, connection=None):
    if connection is not None:
        raise RelationalClientError('XA recovery requires an independently owned connection')
    payload = request['provider_payload']; compiled = payload['compiled']; intent = compiled['mysql_xa']
    checked = deepcopy(compiled); review = checked['mysql_xa'].pop('review', None)
    if (not isinstance(review, Mapping) or
            compile_operation(intent['operation'], intent['draft'], intent['target']) != checked or
            review.get('selected_prepared_xid') != intent['xid']):
        raise RelationalClientError('Review the exact native prepared XA workflow before dispatch')
    handle = client._connect({'route': payload['route']}); cursor = None
    dispatched = acknowledged = False
    try:
        handle.autocommit = True; cursor = handle.cursor()
        actor = environment(cursor)
        if actor != review['execution_identity']:
            raise RelationalClientError('Native XA execution identity changed since review')
        inspection = intent['operation'] == 'inspect_prepared_xa'
        if inspection:
            dispatched = True; after = observe(cursor); acknowledged = True
        else:
            cursor.execute('SET SESSION lock_wait_timeout=%s', (intent['draft'].get('lock_wait_seconds', 15),))
            before = observe(cursor)
            if intent['xid'] not in before:
                raise RelationalClientError('The exact selected XA identity is no longer prepared')
            dispatched = True
            cursor.execute(compiled['statements'][0]['source']); acknowledged = True
            after = observe(cursor)
        return {'accepted': True, 'native_implicit_commit': False,
            'commit_requested': intent['operation'] == 'commit_prepared_xa',
            'rollback_requested': intent['operation'] == 'rollback_prepared_xa',
            'staged_in_provider_session': False, 'automatic_retry': False,
            'driver_observation_only': True, 'transaction_finality_interpreted_by_common_code': False,
            'xa_observation': {'operation': intent['operation'], 'native_acknowledged': acknowledged,
                'execution_identity': actor, 'selected_xid': intent['xid'], 'prepared_after': after,
                'global_transaction_decision_inferred': False, 'branch_generation_attested': False,
                'decision_reference': intent['draft'].get('decision_reference')}}
    except Exception as error:
        raise failure(error, dispatched, acknowledged) from None
    finally:
        if cursor is not None: client._safe_close(cursor)
        client._forget_and_close(handle)

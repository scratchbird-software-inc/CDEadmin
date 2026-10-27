"""Native MariaDB backup stages, bound to the original idle query session."""
from copy import deepcopy
import hashlib
import json
import time
import uuid

from ...sdk import RelationalClientError

STAGES = frozenset({'START', 'FLUSH', 'BLOCK_DDL', 'BLOCK_COMMIT', 'END'})
MAX_LOCK_WAIT = 3600 * 24 * 365  # Native LONG_TIMEOUT in the pinned sql_const.h.
PRIVATE = frozenset({'connection', 'token', 'baseline', 'deadline'})


def public(record):
    return deepcopy({key: value for key, value in record.items() if key not in PRIVATE})


def compile_operation(draft):
    if (not isinstance(draft, dict) or type(draft.get('lock_wait_seconds')) is not int or
            not 0 <= draft['lock_wait_seconds'] <= MAX_LOCK_WAIT):
        raise ValueError('Select a native MariaDB backup stage and integer lock wait from 0 to 31536000 seconds')
    action = draft.get('action', 'stage')
    if (action == 'stage' and set(draft) == {'stage', 'lock_wait_seconds'} and
            isinstance(draft.get('stage'), str) and draft['stage'] in STAGES):
        source = 'BACKUP STAGE ' + draft['stage']
    elif action == 'unlock' and set(draft) == {'action', 'lock_wait_seconds'}:
        source = 'BACKUP UNLOCK'
    elif action == 'lock' and set(draft) == {'action', 'database', 'table', 'lock_wait_seconds'}:
        from .mysql_catalog import identifier
        for field in ('database', 'table'):
            value = draft[field]
            if not isinstance(value, str) or not value or '\x00' in value or len(value) > 64:
                raise ValueError('Select exact native database and table identifiers')
        source = 'BACKUP LOCK ' + identifier(draft['database']) + '.' + identifier(draft['table'])
    else:
        raise ValueError('Select one exact native backup stage, table LOCK or UNLOCK')
    return 'SET STATEMENT lock_wait_timeout=' + str(draft['lock_wait_seconds']) + ' FOR ' + source


def observe(connection):
    cursor = connection.cursor()
    try:
        cursor.execute('SELECT @@server_uid,CONNECTION_ID(),CURRENT_USER(),USER(),CURRENT_ROLE(),'
            '@@version,@@sql_mode,@@in_transaction,@@autocommit')
        row = cursor.fetchone()
        if row is None or len(row) != 9:
            raise RelationalClientError('Native MariaDB backup connection identity is unavailable')
        return dict(zip(('server_uid', 'connection_id', 'effective_principal', 'authenticated_principal',
            'current_role', 'version', 'sql_mode', 'in_transaction', 'autocommit'),
            [str(row[0]), str(row[1]), *row[2:7], bool(row[7]), bool(row[8])]))
    finally:
        cursor.close()


def idle(client, connection):
    if connection not in client._connections or id(connection) not in client._session_requests:
        raise RelationalClientError('The original native MariaDB session is unavailable')
    client._executions.require_idle(connection)
    client._require_usable_session(connection)


def receipt(client, record):
    token = record.get('token')
    if record['state'] != 'executing':
        return public(record)
    page = client.describe_result(token)
    record.update(native_dispatched=token.native_dispatched, native_acknowledged=token.native_acknowledged,
        cancellation_requested=token.cancelled)
    if page['complete']:
        payload = page['payload']
        uncertain = bool(payload.get('session_reuse_blocked'))
        record.update(state='acknowledged' if token.native_acknowledged else
            'unknown_outcome' if uncertain and token.native_dispatched else
            'cancelled' if token.cancelled else 'refused',
            error=deepcopy(payload.get('error')), statement_metrics=payload.get('statement_metrics'),
            session_reuse_blocked=uncertain)
        record.pop('token', None)
        if not uncertain:
            try:
                idle(client, record['connection'])
                record['native_session_after'] = observe(record['connection'])
            except Exception as error:
                record['post_observation_error_type'] = type(error).__name__
        # The native command acknowledgement does not assert independently
        # observed global lock state, nor successful physical backup files.
        record['lock_state_independently_observed'] = False
    return public(record)


def action(client, connection, request):
    if not isinstance(request, dict):
        raise ValueError('Select a native MariaDB backup-stage request')
    operation = request.get('operation')
    allowed = {'inventory': {'operation'}, 'review': {'operation', 'draft'},
        'apply': {'operation', 'review_id', 'review_digest', 'confirmation', 'confirmed'},
        'receipt': {'operation', 'review_id'}, 'cancel': {'operation', 'review_id'},
        'discard': {'operation', 'review_id', 'review_digest'}}
    if operation not in allowed or set(request) != allowed[operation]:
        raise ValueError('Unknown native MariaDB backup-stage request')
    with client._executions.lock:
        records = client._backup_stage_reviews
        if operation not in {'inventory', 'review'}:
            record = records.get(request['review_id'])
            if record is None or record['connection'] is not connection:
                raise ValueError('The backup-stage receipt belongs to another or closed native session')
            if operation in {'apply', 'discard'} and request['review_digest'] != record['review_digest']:
                raise ValueError('Select the exact native backup-stage review')
            if operation == 'receipt':
                return receipt(client, record)
            if operation == 'cancel':
                if record['state'] == 'executing':
                    client.cancel(record['token'])
                return receipt(client, record)
            if record['state'] != 'reviewed':
                return receipt(client, record)
            if operation == 'discard':
                record.update(state='discarded')
                return public(record)
            if (record['deadline'] < time.monotonic() or request['confirmed'] is not True or
                    request['confirmation'] != record['stage']):
                raise ValueError('Confirm the current reviewed native backup stage')
        idle(client, connection)
        current = observe(connection)
        if operation == 'inventory':
            return {'native_session': current, 'stages': sorted(STAGES),
                'stage_observation': 'Native stage/lock ownership is not inferred from application receipts',
                'table_lock_controls': ['LOCK', 'UNLOCK'], 'active_transaction_refused': current['in_transaction']}
        if current['in_transaction']:
            raise RelationalClientError('BACKUP STAGE implicitly commits. Explicitly commit or roll back the active transaction before reviewing or applying it')
        if operation == 'review':
            for key in list(records):
                old = records[key]
                if old['state'] != 'executing' and (old['deadline'] < time.monotonic() or old['connection'] not in client._connections):
                    del records[key]
            if len(records) >= 64:
                raise ValueError('Close old backup-stage reviews before creating another')
            source = compile_operation(request['draft'])
            record = {'review_id': str(uuid.uuid4()), 'state': 'reviewed', 'connection': connection,
                'baseline': current, 'native_session': current, 'deadline': time.monotonic() + 300,
                'source': source, 'draft': deepcopy(request['draft']),
                'stage': request['draft'].get('stage', request['draft'].get('action', '').upper()),
                'native_dispatched': False, 'native_acknowledged': False, 'automatic_retry': False,
                'caller_transaction_decision_requested': False,
                'warnings': ['BACKUP STAGE has server-wide effects and performs native implicit commits. This workflow refuses an already active transaction.',
                    'Stages stay on this original native connection. Native stage order, forward jumps, authority and lock waits are enforced by MariaDB.',
                    'Use END for backup stages and UNLOCK for a table backup lock. Closing the original native session releases its backup locks. A cancelled or failed transition can leave earlier locks active.',
                    'BACKUP LOCK releases an earlier table backup lock before trying the new one; a failed replacement can leave that earlier table unlocked.',
                    'This controls native backup locking; it does not copy or verify physical database files.',
                    'Receipts are scoped to this live native session. Native lock state is not inferred from the last acknowledged command.']}
            record['review_digest'] = hashlib.sha256(json.dumps(public(record), sort_keys=True, default=str).encode()).hexdigest()
            records[record['review_id']] = record
            return public(record)
        if current != record['baseline'] or compile_operation(record['draft']) != record['source']:
            record.update(state='refused', reason='Native connection, principal, mode or transaction changed since review')
            return public(record)
        # The existing native execution owner provides progress, exact server
        # diagnostics and cancellation through an independently verified peer.
        record['state'] = 'executing'
        client._backup_stage_handles.add(id(connection))
        try:
            record['token'] = client.execute(connection, {'source': record['source']})
        except Exception:
            record.update(state='refused', native_dispatched=False, native_acknowledged=False)
            raise
        return public(record)

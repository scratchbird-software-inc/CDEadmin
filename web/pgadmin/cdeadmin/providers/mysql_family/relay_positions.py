"""Wide replication integers bound to the target's unsigned-long ceiling."""
from contextlib import contextmanager
import hashlib
import json
import re
from ...sdk import RelationalClientError

QUERY = ("SELECT @@server_uuid,MAX_VALUE,VERSION() FROM performance_schema.variables_metadata "
         "WHERE VARIABLE_NAME='bulk_insert_buffer_size'")


def position(compiled):
    for statement in compiled.get('statements', []):
        source = statement.get('source', '')
        if source.startswith(('CHANGE REPLICATION SOURCE TO ', 'START REPLICA')):
            values = re.findall(r'\b(?:RELAY_LOG_POS|SOURCE_RETRY_COUNT)=([0-9]+)(?:,| FOR CHANNEL)', source)
            value = max(values, key=int, default='0')
            if int(value) > 2**32-1:
                if len(compiled['statements']) != 1:
                    raise RelationalClientError('Review one native channel statement')
                return value


def evidence_key(compiled):
    return 'native_unsigned_long' if 'SOURCE_RETRY_COUNT=' in compiled['statements'][0]['source'] else 'native_relay_position'


def signature(compiled):
    return hashlib.sha256(json.dumps(compiled['statements'], sort_keys=True).encode()).hexdigest()


def observe(cursor, requested):
    # The native Sys_var_ulong range is 0..ULONG_MAX; no session value is read.
    cursor.execute(QUERY)
    rows = cursor.fetchall()
    if (len(rows) != 1 or len(rows[0]) != 3 or str(rows[0][2]).split('-')[0] != '9.7.0' or
            not isinstance(rows[0][0], str) or not rows[0][0] or
            str(rows[0][1]) not in {str(2**32-1), str(2**64-1)}):
        raise RelationalClientError('The target unsigned-long ceiling is unavailable')
    if requested is None or int(requested) > int(rows[0][1]):
        raise RelationalClientError('Value exceeds the target unsigned-long ceiling')
    return {'server_uuid': rows[0][0], 'maximum': str(rows[0][1]), 'requested': requested}


@contextmanager
def peer(client, payload):
    handle = client._connect({'route': {**payload['route'], 'database': None}})
    cursor = None; primary = False
    try:
        handle.autocommit = True; cursor = handle.cursor()
        yield cursor
    except BaseException:
        primary = True; raise
    finally:
        if cursor is not None: client._safe_close(cursor)
        try: client._forget_and_close(handle)
        except Exception:
            if not primary: raise


def bind_review(client, planned):
    payload = planned['provider_payload']; compiled = payload['compiled']
    try:
        with peer(client, payload) as cursor:
            observed = observe(cursor, position(compiled))
            compiled['mysql_relay_review'] = {**observed, 'statement_sha256': signature(compiled)}
            planned['command_preview'][evidence_key(compiled)] = observed
    except Exception as error:
        raise failure(error) from None
    return planned


def apply(client, request, connection=None):
    if connection is not None:
        raise RelationalClientError('Use an independent connection for wide integers')
    payload = request['provider_payload']; compiled = payload['compiled']
    review = compiled.get('mysql_relay_review')
    if not isinstance(review, dict) or review.get('statement_sha256') != signature(compiled):
        raise RelationalClientError('Review the native channel statement before dispatch')
    dispatched = acknowledged = False
    try:
        with peer(client, payload) as cursor:
            observed = observe(cursor, position(compiled))
            if observed != {key: review.get(key) for key in observed}:
                raise RelationalClientError('The target instance or ceiling changed')
            statement = compiled['statements'][0]; dispatched = True
            cursor.execute(statement['source'], statement['parameters'] or None); acknowledged = True
            rows = cursor.fetchall() if cursor.description else []
            return {'accepted': True, 'native_acknowledged': True, 'automatic_retry': False,
                    'statement_results': [{'rowcount': cursor.rowcount, 'rows': rows}],
                    'commit_requested': False, 'rollback_requested': False,
                    'staged_in_provider_session': False, 'driver_observation_only': True,
                    'transaction_finality_interpreted_by_common_code': False,
                    evidence_key(compiled): observed}
    except Exception as error:
        raise failure(error, dispatched, acknowledged) from None


def failure(error, dispatched=False, acknowledged=False):
    failure = error if isinstance(error, RelationalClientError) else RelationalClientError(
        'Native channel operation failed ('+type(error).__name__+')')
    failure.native_dispatched = dispatched; failure.native_acknowledged = acknowledged
    failure.automatic_retry = False
    failure.errno = getattr(error, 'errno', None); failure.sqlstate = getattr(error, 'sqlstate', None)
    return failure

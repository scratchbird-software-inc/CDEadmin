"""Native ownership evidence for an acceptance job's private SQL locks."""
from copy import deepcopy
import uuid

from .mysql_binlog_archives import BinlogArchiveError, rows


def lock_name(job_id):
    if not isinstance(job_id, str) or str(uuid.UUID(job_id)) != job_id:
        raise BinlogArchiveError('Invalid independent acceptance identity')
    return 'sr:dump-check:' + job_id


def private_thread(connection):
    """Require positive native instrumentation and handshake observations."""
    attribute = deepcopy(getattr(connection, '_cdeadmin_observer_attribute', None))
    if not isinstance(attribute, dict) or set(attribute) != {'name', 'value'}:
        raise BinlogArchiveError('The private native handshake identity is unavailable')
    current = rows(connection, 'SELECT @@server_uuid AS server_uuid,@@performance_schema AS enabled,'
        'IF(@@performance_schema,PS_CURRENT_THREAD_ID(),NULL) AS thread_id,CONNECTION_ID() AS connection_id')[0]
    if not current['enabled'] or any(type(current[key]) is not int or current[key] <= 0 for key in ('thread_id', 'connection_id')):
        raise BinlogArchiveError('Native private-thread instrumentation is unavailable')
    threads = rows(connection, 'SELECT THREAD_ID FROM performance_schema.threads WHERE THREAD_ID=%s AND PROCESSLIST_ID=%s',
        (current['thread_id'], current['connection_id']))
    attributes = rows(connection, 'SELECT PROCESSLIST_ID FROM performance_schema.session_account_connect_attrs '
        'WHERE PROCESSLIST_ID=%s AND ATTR_NAME=%s AND ATTR_VALUE=%s',
        (current['connection_id'], attribute['name'], attribute['value']))
    if len(threads) != 1 or len(attributes) != 1:
        raise BinlogArchiveError('Native private-thread visibility is unqualified')
    return current


def acquire(connection, job_id, target_uuid):
    """Persist this returned witness before acquiring either acceptance lock."""
    try:
        current = private_thread(connection)
    except Exception as error:
        return {'admitted': False, 'reason': 'private-lock-owner-observation-unavailable',
                'error_type': type(error).__name__, 'native_code': getattr(error, 'errno', None)}
    if current['server_uuid'] != target_uuid:
        raise BinlogArchiveError('Native private-lock target changed')
    name = lock_name(job_id)
    if rows(connection, 'SELECT GET_LOCK(%s,0) AS acquired', (name,))[0]['acquired'] != 1:
        raise BinlogArchiveError('Another native connection owns this acceptance identity')
    return {'admitted': True, 'server_uuid': target_uuid, 'thread_id': str(current['thread_id']),
            'connection_id': str(current['connection_id']), 'lock_name': name}


def observe(connection, record):
    """A free user lock alone does not establish instance backup-lock cleanup."""
    witness = record.get('server_lock_owner')
    if not isinstance(witness, dict) or witness.get('admitted') is not True:
        return {'qualified': False, 'released': None, 'reason': 'no-admitted-private-lock-owner'}
    try:
        if (set(witness) != {'admitted', 'server_uuid', 'thread_id', 'connection_id', 'lock_name'} or
                witness['server_uuid'] != record['source']['server_uuid'] or
                witness['lock_name'] != lock_name(record['job_id']) or
                any(not isinstance(witness[key], str) or not witness[key].isascii() or
                    not witness[key].isdigit() or int(witness[key]) <= 0 for key in ('thread_id', 'connection_id'))):
            raise BinlogArchiveError('The admitted private-lock identity changed')
        current = private_thread(connection)
        if current['server_uuid'] != witness['server_uuid']:
            raise BinlogArchiveError('Native private-lock observation reached another server')
        # The pinned native connection lifecycle removes its PFS thread only
        # after THD resource/lock cleanup. Any surviving/reused thread ID stays
        # conservative, regardless of its current connection or attributes.
        present = rows(connection, 'SELECT THREAD_ID FROM performance_schema.threads WHERE THREAD_ID=%s',
                       (int(witness['thread_id']),))
        free = rows(connection, 'SELECT IS_FREE_LOCK(%s) AS free', (witness['lock_name'],))[0]['free']
        return {'qualified': True, 'released': not present and free == 1,
                'original_thread_absent': not present, 'private_owner_lock_free': free == 1,
                'thread_id': witness['thread_id'], 'connection_id': witness['connection_id'],
                'scope': 'Original private SQL session and its server locks only; no utility termination or restored-data inference'}
    except Exception as error:
        return {'qualified': False, 'released': None, 'reason': 'private-lock-owner-observation-unavailable',
                'error_type': type(error).__name__, 'native_code': getattr(error, 'errno', None)}

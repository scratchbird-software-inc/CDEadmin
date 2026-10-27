"""Native evidence for interrupted AdminAPI connections and clone workers.

Client exit is separate from server-side completion. The pinned libmysql sends
its process ID on each connection; absence is useful only with positive native
visibility and unchanged thread/attribute loss counters.
"""
import hashlib
import inspect
import json
from pathlib import Path

from .mysql_binlog_archives import BinlogArchiveError, rows

ATTRIBUTE = 'cdeadmin_topology_job'
OWNER_FILE = 'native-topology-owner.json'
POLICY = 'mysqlsh-9.7-server-connections-v1'


def native_profile(query, marker, pid=None):
    """Shared application/Shell probe; query returns ordered native rows."""
    current = query('SELECT @@server_uuid,VERSION(),CURRENT_USER(),CURRENT_ROLE(),'
        '@@performance_schema,IF(@@performance_schema,CAST(PS_CURRENT_THREAD_ID() AS CHAR),NULL),'
        'CAST(CONNECTION_ID() AS CHAR),@@performance_schema_session_connect_attrs_size')[0]
    if not current[4] or int(current[7]) == 0 or any(
            not str(value).isascii() or not str(value).isdigit() or int(value) <= 0 for value in current[5:7]):
        raise ValueError('Native thread and handshake instrumentation is unavailable')
    attributes = dict(query('SELECT ATTR_NAME,ATTR_VALUE FROM performance_schema.session_connect_attrs '
        'WHERE PROCESSLIST_ID=CONNECTION_ID()'))
    if not marker or attributes.get(marker['name']) != marker['value'] or '_truncated' in attributes:
        raise ValueError('Native observer handshake is unqualified')
    if pid is not None and (attributes.get('_pid') != str(pid) or
            attributes.get('_client_name') != 'libmysql' or attributes.get('program_name') != 'mysqlsh'):
        raise ValueError('Native utility process handshake is unqualified')
    source = 'SHOW GRANTS FOR CURRENT_USER()'
    if current[3] != 'NONE': source += ' USING '+current[3]
    process_visible = False
    for row in query(source):
        grant = row[0]
        prefix, separator, _account = grant.partition(' ON *.* TO ')
        # A quoted column or role name can contain "PROCESS ON *.* TO".
        # Global privilege lists contain unquoted privilege tokens only.
        if separator and prefix.startswith('GRANT ') and all(
                character in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_, ' for character in prefix[6:]):
            privileges = {value.strip().upper() for value in prefix[6:].split(',')}
            process_visible = process_visible or bool(privileges & {'PROCESS', 'ALL PRIVILEGES'})
    if not process_visible: raise ValueError('Native global process visibility is unqualified')
    counters = dict(query("SELECT VARIABLE_NAME,VARIABLE_VALUE FROM performance_schema.global_status "
        "WHERE VARIABLE_NAME IN ('Performance_schema_session_connect_attrs_lost','Performance_schema_thread_instances_lost')"))
    counters = {key.lower(): str(value) for key, value in counters.items()}
    if set(counters) != {'performance_schema_session_connect_attrs_lost', 'performance_schema_thread_instances_lost'} or any(
            not value.isascii() or not value.isdigit() for value in counters.values()):
        raise ValueError('Native connection instrumentation loss counters are unavailable')
    return {'identity': dict(zip(('server_uuid','version','authenticated_principal','active_role'), current[:4])),
        'thread_id': str(current[5]), 'connection_id': str(current[6]), 'loss_counters': counters}


def profile_source():
    return inspect.getsource(native_profile)


def load(directory, record):
    reference = record.get('native_topology_owner')
    if not isinstance(reference, dict) or set(reference) != {'policy', 'nonce', 'script_sha256'} or reference['policy'] != POLICY:
        raise BinlogArchiveError('No admitted native topology connection owner')
    directory = Path(directory); script = directory/'native-topology.py'; path = directory/OWNER_FILE
    if script.is_symlink() or hashlib.sha256(script.read_bytes()).hexdigest() != reference['script_sha256']:
        raise BinlogArchiveError('Native topology owner script changed')
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise BinlogArchiveError('Native topology owner witness is unavailable')
    witness = json.loads(path.read_text())
    if (not isinstance(witness, dict) or set(witness) != {'policy','nonce','pid','targets'} or
            witness['policy'] != POLICY or witness['nonce'] != reference['nonce'] or
            type(witness['pid']) is not int or witness['pid'] <= 0 or not isinstance(witness['targets'], dict)):
        raise BinlogArchiveError('Native topology owner witness changed')
    utility = record.get('interrupted_utility_observation') or {}
    if (utility.get('cleanup_confirmed') is not True or utility.get('credential_file_cleanup_confirmed') is not True or
            (utility.get('native_process_identity') or {}).get('pid') != witness['pid']):
        raise BinlogArchiveError('Original native utility identity and termination are unconfirmed')
    return witness


def observe(connection, original, pid):
    try:
        marker = getattr(connection, '_cdeadmin_observer_attribute', None)
        def query(source, parameters=()): return [list(row.values()) for row in rows(connection, source, parameters)]
        current = native_profile(query, marker)
        if original.get('admitted') is not True or current['identity'] != original.get('profile', {}).get('identity'):
            raise BinlogArchiveError('Original native connection identity is unqualified')
        prior = original['profile']
        if current['loss_counters'] != prior['loss_counters']:
            raise BinlogArchiveError('Native connection instrumentation lost or reset evidence')
        # Clone recovery restarts its recipient. A bare PFS thread ID can then
        # name an unrelated new thread. Require the original native client PID
        # as well, under the positively admitted handshake coverage below.
        present = query('SELECT CAST(t.THREAD_ID AS CHAR) FROM performance_schema.threads t '
            'JOIN performance_schema.session_connect_attrs a ON a.PROCESSLIST_ID=t.PROCESSLIST_ID '
            "WHERE t.THREAD_ID=%s AND a.ATTR_NAME='_pid' AND a.ATTR_VALUE=%s", (prior['thread_id'], str(pid)))
        sessions = query("SELECT CAST(PROCESSLIST_ID AS CHAR) FROM performance_schema.session_connect_attrs "
            "WHERE ATTR_NAME='_pid' AND ATTR_VALUE=%s ORDER BY PROCESSLIST_ID", (str(pid),))
        plugins = query("SELECT PLUGIN_STATUS FROM information_schema.PLUGINS WHERE PLUGIN_NAME='clone'")
        clone = []
        if plugins:
            if plugins != [['ACTIVE']]: raise BinlogArchiveError('Native clone plugin state is unconfirmed')
            clone = query('SELECT CAST(ID AS CHAR),STATE,CAST(BEGIN_TIME AS CHAR),CAST(END_TIME AS CHAR),'
                'CAST(PID AS CHAR) FROM performance_schema.clone_status')
        after = dict(query("SELECT VARIABLE_NAME,VARIABLE_VALUE FROM performance_schema.global_status "
            "WHERE VARIABLE_NAME IN ('Performance_schema_session_connect_attrs_lost','Performance_schema_thread_instances_lost')"))
        after = {key.lower(): str(value) for key, value in after.items()}
        if after != current['loss_counters']:
            raise BinlogArchiveError('Native connection evidence changed during observation')
        idle = all(row[1] in {'Not Started', 'Completed', 'Failed'} for row in clone)
        return {'qualified': True, 'idle': not present and not sessions and idle,
            'native_tool_pid': str(pid), 'original_thread_id': prior['thread_id'],
            'original_thread_absent': not present, 'remaining_native_session_ids': [row[0] for row in sessions],
            'clone_status': clone, 'loss_counters': after,
            'scope': 'Original native utility connections and current clone activity only; no original reply or recovered-data inference'}
    except Exception as error:
        return {'qualified': False, 'idle': None, 'error_type': type(error).__name__,
            'native_code': getattr(error, 'errno', None)}

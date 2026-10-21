"""Native server log purging, separate from application archive retention."""
from copy import deepcopy
from datetime import datetime
import hashlib
from pathlib import Path
import threading

from .mysql_binlog_archives import BinlogArchiveError, capture
from .mysql_clone import rows, thread_identity, thread_matches


def options(value):
    if not isinstance(value, dict) or set(value) - {'mode', 'to_file', 'before_utc', 'timeout_seconds'}:
        raise BinlogArchiveError('Select a native log filename or UTC cutoff')
    mode = value.get('mode')
    timeout = value.get('timeout_seconds', 60)
    if timeout is not None and (type(timeout) is not int or not 1 <= timeout <= 2147483647):
        raise BinlogArchiveError('Select positive client read-timeout seconds or null')
    if mode == 'TO':
        selected = value.get('to_file')
        if (not isinstance(selected, str) or not selected or '\x00' in selected or
                len(selected.encode('utf8')) > 1024 or 'before_utc' in value):
            raise BinlogArchiveError('Select an exact available native log filename')
        return {'mode': mode, 'to_file': selected, 'timeout_seconds': timeout}
    if mode == 'BEFORE':
        selected = value.get('before_utc')
        try:
            if not isinstance(selected, str) or datetime.strptime(selected, '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M:%S') != selected or 'to_file' in value:
                raise ValueError()
        except ValueError:
            raise BinlogArchiveError('Select an exact UTC cutoff as YYYY-MM-DD HH:MM:SS') from None
        return {'mode': mode, 'before_utc': selected, 'timeout_seconds': timeout}
    raise BinlogArchiveError('Select native TO filename or BEFORE UTC time')


def names(observed):
    result = [row['Log_name'] for row in observed['logs']]
    if (not result or len(result) != len(set(result)) or
            observed['current'] is None or observed['current']['File'] != result[-1]):
        raise BinlogArchiveError('The native binary-log index and active log are unconfirmed')
    return result


def selection(connection, observed, selected):
    if observed['status'] != 'available':
        raise BinlogArchiveError('Native binary logging is disabled')
    logs = names(observed)
    if selected['mode'] == 'TO':
        if selected['to_file'] not in logs:
            raise BinlogArchiveError('The selected native boundary log is unavailable')
        return {'before_names': logs, 'candidate_names': logs[:logs.index(selected['to_file'])],
                'candidate_selection': 'exact-native-index-before-boundary'}
    epoch = rows(connection, 'SELECT CAST(UNIX_TIMESTAMP(CAST(%s AS DATETIME)) AS CHAR) AS native_epoch',
                 (selected['before_utc'],))[0]['native_epoch']
    if epoch is None:
        raise BinlogArchiveError('The native server could not evaluate this UTC cutoff')
    return {'before_names': logs, 'candidate_names': logs[:-1], 'native_epoch': str(epoch),
            'candidate_selection': 'potential-closed-logs-native-server-evaluates-file-timestamps'}


def program(observed):
    return {'adapter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'execution_host': {'kind': 'native-database-server', 'platform': 'mysql',
                               'server_uuid': observed['identity']['server_uuid']}}


def error_observation(error):
    return {'type': type(error).__name__, 'errno': getattr(error, 'errno', None),
            'sqlstate': getattr(error, 'sqlstate', None)}


def private_connection(client, route):
    """Admit job-owned I/O without sharing interactive client shutdown."""
    with client._executions.lock:
        if client._executions.closing:
            raise BinlogArchiveError('The native client is closing; prepare a new source log request')
        connection = client._connect({'route': route})
        try:
            client._forget_connection(connection)
        except BaseException:
            client._discard_failed_session(connection)
            raise
        return connection


class Transport:
    def __init__(self, client, worker, monitor, observed, selected):
        self.client, self.worker, self.monitor = client, worker, monitor
        self.observed, self.selected = observed, selected
        self.monitor_lock = threading.RLock()

    def close(self):
        with self.monitor_lock:
            for name in ('worker', 'monitor'):
                connection = getattr(self, name)
                if connection is not None:
                    setattr(self, name, None)
                    self.client._discard_failed_session(connection)

    def observe(self):
        with self.monitor_lock:
            current = capture(self.monitor)
            if current['identity'] != self.observed['identity']:
                raise BinlogArchiveError('Native log administration reached another server or principal')
            return current

    def matches(self, identity, attribute, *, active=False):
        with self.monitor_lock:
            current = rows(self.monitor, 'SELECT @@server_uuid AS server_uuid')[0]['server_uuid']
            if current != self.observed['identity']['server_uuid'] or not thread_matches(self.monitor, identity):
                return False
            if not isinstance(attribute, dict) or set(attribute) != {'name', 'value'}:
                return False
            found = rows(self.monitor, 'SELECT PROCESSLIST_ID FROM performance_schema.session_account_connect_attrs '
                'WHERE PROCESSLIST_ID=%s AND ATTR_NAME=%s AND ATTR_VALUE=%s',
                (identity['connection_id'], attribute['name'], attribute['value']))
            if len(found) != 1:
                return False
            if active:
                current = rows(self.monitor, 'SELECT PROCESSLIST_INFO FROM performance_schema.threads '
                    'WHERE THREAD_ID=%s AND PROCESSLIST_ID=%s', (identity['thread_id'], identity['connection_id']))
                return len(current) == 1 and isinstance(current[0]['PROCESSLIST_INFO'], str) and current[0]['PROCESSLIST_INFO'].lstrip().startswith('PURGE BINARY LOGS ')
            return True

    def execute(self, record, cancel, boundary, progress):
        current = capture(self.worker)
        if current['identity'] != record['source'] or selection(self.worker, current, record['options']) != record['source_state']['purge_selection']:
            raise BinlogArchiveError('The native log index, boundary or execution identity changed; prepare a new review')
        if current['state']['gtid_mode'] != record['source_state']['gtid_mode'] or rows(self.worker,
                'SELECT GTID_SUBSET(%s,@@global.gtid_executed) AS valid',
                (record['source_state']['gtid_executed'],))[0]['valid'] != 1:
            raise BinlogArchiveError('Native log mode or observed GTID lineage changed; prepare a new review')
        identity = thread_identity(self.worker)
        attribute = deepcopy(getattr(self.worker, '_cdeadmin_observer_attribute', None))
        try:
            can_cancel = self.matches(identity, attribute)
        except Exception:
            can_cancel = False
        progress({'cancel_capability': {'available': can_cancel, 'identity': 'native-thread-processlist-and-handshake-attribute'},
                  'native_thread': identity})
        lock = 'sr:log-purge:' + record['source']['server_uuid']
        if rows(self.worker, 'SELECT GET_LOCK(%s,0) AS acquired', (lock,))[0]['acquired'] != 1:
            raise BinlogArchiveError('Another application log purge holds the native server lock')
        done, started = threading.Event(), threading.Event()
        cancellation = {'requested': False, 'kill_query_sent': False}
        watcher = None
        try:
            if cancel.is_set():
                raise InterruptedError('Native log purge cancelled before dispatch')
            def watch():
                while not done.wait(.1):
                    if not started.is_set() or not cancel.is_set():
                        continue
                    cancellation['requested'] = True
                    if can_cancel:
                        try:
                            with self.monitor_lock:
                                if self.matches(identity, attribute, active=True) and not done.is_set():
                                    rows(self.monitor, 'KILL QUERY ' + identity['connection_id'])
                                    cancellation['kill_query_sent'] = True
                                    return
                        except Exception as error:
                            cancellation['error'] = error_observation(error)
                            return
                    else:
                        return
            watcher = threading.Thread(target=watch, daemon=True, name='mysql-log-purge-cancel')
            watcher.start()
            self.worker.get_warnings = False
            self.worker.raise_on_warnings = False
            cursor = self.worker.cursor()
            result = {'native_acknowledged': False, 'native_error_returned': False}
            try:
                boundary()
                started.set()
            except BaseException:
                done.set()
                cursor.close()
                raise
            try:
                source, value = ('PURGE BINARY LOGS TO %s', record['options']['to_file']) if record['options']['mode'] == 'TO' else (
                    'PURGE BINARY LOGS BEFORE %s', record['options']['before_utc'])
                cursor.execute(source, (value,))
                done.set()
                result = {'native_acknowledged': True, 'native_error': None}
            except Exception as error:
                code, state = getattr(error, 'errno', None), getattr(error, 'sqlstate', None)
                server_error = type(code) is int and code >= 1000 and not 2000 <= code < 3000 and isinstance(state, str) and len(state) == 5
                result = {'native_acknowledged': False, 'native_error_returned': server_error,
                          'native_error': error_observation(error)}
            finally:
                done.set()
                try:
                    cursor.close()
                except Exception as error:
                    result['cursor_cleanup_error'] = error_observation(error)
            progress({key: result[key] for key in ('native_acknowledged', 'native_error_returned', 'native_error') if key in result})
            watcher.join(timeout=6)
            if watcher.is_alive():
                raise BinlogArchiveError('Native cancellation observation is still active; do not replay this purge')
            result['cancellation'] = cancellation
            if result['native_acknowledged']:
                try:
                    result['warnings'] = rows(self.worker, 'SHOW WARNINGS')
                except Exception as error:
                    result['warning_observation_error'] = error_observation(error)
            try:
                after = self.observe()
                before_names = record['source_state']['purge_selection']['before_names']
                after_names = names(after)
                result['after'] = after
                result['removed_names_observed'] = [name for name in before_names if name not in after_names]
                result['retained_names_observed'] = [name for name in before_names if name in after_names]
                if record['options']['mode'] == 'TO':
                    candidates = record['source_state']['purge_selection']['candidate_names']
                    result['requested_prefix_absent'] = all(name not in after_names for name in candidates)
            except Exception as error:
                result['postcondition_error'] = error_observation(error)
            return result
        finally:
            done.set()
            if watcher is not None:
                watcher.join(timeout=6)
            try:
                rows(self.worker, 'SELECT RELEASE_LOCK(%s) AS released', (lock,))
            except Exception:
                pass  # Connection close also releases this private native lock.

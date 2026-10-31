"""Read retained MySQL session variables on a separately authenticated peer.

Admission occurs before user execution. Loss, denial and disabled observation
never authorize an editor query on the original session. A denied candidate can
be readmitted on the authenticated editor path without reconnecting the source.
"""
from copy import deepcopy
from contextlib import contextmanager
import re
import threading
import weakref

from ...sdk import RelationalClientError

VARIABLES = ('sql_mode', 'character_set_client', 'character_set_connection',
             'character_set_results', 'collation_connection')
QUERY = """SELECT v.VARIABLE_NAME,v.VARIABLE_VALUE
FROM performance_schema.variables_by_thread AS v
JOIN performance_schema.session_account_connect_attrs AS a
  ON a.PROCESSLIST_ID=%s AND a.ATTR_NAME=%s AND a.ATTR_VALUE=%s
WHERE v.THREAD_ID=%s AND v.VARIABLE_NAME IN
 ('sql_mode','character_set_client','character_set_connection','character_set_results','collation_connection')
ORDER BY v.VARIABLE_NAME"""


def _text(value):
    return value.decode('ascii') if isinstance(value, bytes) else value


class ObserverUnavailable(RelationalClientError):
    pass


class SourceIdentityUnavailable(ObserverUnavailable):
    pass


class EditorObservationUnavailable(ObserverUnavailable):
    """Only fixed operator guidance and a numeric native errno are public."""
    def __init__(self, reason, errno=None):
        guidance = {
            'disabled': 'Enable native Performance Schema in the server configuration and reconnect after its reviewed restart.',
            'denied': ('The registered account needs native access to performance_schema.variables_by_thread, '
                'performance_schema.session_account_connect_attrs and performance_schema.threads. '
                'After restoring access, retry the editor request on this same session.'),
        }.get(reason, 'Open a fresh native editor session with independent observation enabled.')
        self.native_observer_errno = errno if type(errno) is int else None
        super().__init__('Private MySQL editor observation is unavailable. '+guidance+
            (' Native errno '+str(self.native_observer_errno)+'.' if self.native_observer_errno is not None else '')+
            ' No original-session metadata command was substituted.')
        self.original_diagnostics_preserved = True
        self.original_session_commands_sent = 0


class SessionVariables:
    def __init__(self, source, connector, identity, attribute):
        self.source = weakref.ref(source)
        self.connector = connector
        self.identity = identity
        self.attribute = attribute
        self.last_observation = None
        self.cached = None
        self.connection = None
        self.opened = False
        self.needs_connection_refresh = False
        self.parser_database = None
        self.escaping_context = None
        self.lock = threading.RLock()

    def observe(self):
        with self.lock:
            return self._observe()

    def _observe(self):
        source = self.source()
        if source is None or source.connection_id != self.identity['connection_id']:
            raise SourceIdentityUnavailable('The original MySQL session identity changed')
        if self.cached is not None:
            return deepcopy(self.cached)
        if self.connection is None:
            if self.opened:
                raise ObserverUnavailable('The independent MySQL observation connection is closed')
            peer = self.connector()
            if peer is source or getattr(peer, 'connection_id', None) == self.identity['connection_id']:
                raise ObserverUnavailable('The MySQL observer must own a different native connection')
            self.connection = peer
            self.opened = True
            self.parser_database = None
            self.escaping_context = None
        connection = self.connection
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute('SELECT @@server_uuid,HEX(CURRENT_USER()),VERSION()')
            server, principal, version = map(_text, cursor.fetchone())
            if (server != self.identity['server_uuid'] or principal != self.identity['principal_hex'] or
                    version != self.identity['version']):
                raise ObserverUnavailable('The private MySQL observer reached another native peer or principal')
            cursor.execute(QUERY, (self.identity['connection_id'], self.attribute['name'],
                                  self.attribute['value'], self.identity['thread_id']))
            rows = cursor.fetchall()
            if not rows:
                cursor.execute('SELECT PROCESSLIST_ID FROM performance_schema.session_account_connect_attrs '
                    'WHERE PROCESSLIST_ID=%s AND ATTR_NAME=%s AND ATTR_VALUE=%s',
                    (self.identity['connection_id'], self.attribute['name'], self.attribute['value']))
                if not cursor.fetchall():
                    raise SourceIdentityUnavailable('The original MySQL session handshake identity is unavailable')
            result = {}
            for key, value in rows:
                key, value = _text(key), _text(value)
                if key not in VARIABLES or key in result or not isinstance(value, str):
                    raise ObserverUnavailable('The original MySQL variable observation is incomplete or ambiguous')
                if key == 'character_set_results' and value == '':
                    value = None  # Native P_S represents this core nullable variable as an empty value.
                if key != 'sql_mode' and value is not None and not re.fullmatch(r'[A-Za-z0-9_]{1,128}', value):
                    raise ObserverUnavailable('The original MySQL character-set observation is unavailable')
                if key == 'sql_mode' and (len(value) > 4096 or not re.fullmatch(r'[A-Z0-9_,]*', value)):
                    raise ObserverUnavailable('The original MySQL language observation is unavailable')
                result[key] = value
            if set(result) != set(VARIABLES):
                raise ObserverUnavailable('The original MySQL thread/connection attribute or complete variable set is unavailable')
            if source.connection_id != self.identity['connection_id']:
                raise SourceIdentityUnavailable('The original MySQL session changed during variable observation')
            self.last_observation = {'observation_source': 'native-performance-schema-independent-connection',
                'original_session_commands_sent': 0, 'thread_id': self.identity['thread_id'],
                'connection_id': self.identity['connection_id'], 'version': version,
                'variables': deepcopy(result)}
            self.cached = deepcopy(self.last_observation)
            return deepcopy(self.last_observation)
        finally:
            if cursor is not None:
                cursor.close()

    def close(self):
        with self.lock:
            connection = self.connection
            self.connection = None
            self.opened = True
            self.cached = None
            if connection is not None:
                connection.close()

    def renew(self):
        """Called on the authenticated request path, never by the SQL worker."""
        with self.lock:
            try:
                self.close()
                self.opened = False
                result = self._observe()
            except Exception:
                # A failed authenticated acquisition must not enable an
                # acquisition attempt from a later execution worker.
                self.opened = True
                self.needs_connection_refresh = True
                raise
            self.needs_connection_refresh = False
            return result

    @contextmanager
    def parser_session(self):
        """Borrow only the private peer; never send a command on the source."""
        with self.lock:
            self.cached = None
            cursor = None
            try:
                observed = self._observe()
                self.escaping_context = None
                if self.connection.charset != 'utf8mb4':
                    self.connection.set_charset_collation('utf8mb4')
                cursor = self.connection.cursor()
                cursor.execute('SELECT t.PROCESSLIST_DB FROM performance_schema.threads AS t '
                    'JOIN performance_schema.session_account_connect_attrs AS a ON a.PROCESSLIST_ID=t.PROCESSLIST_ID '
                    'WHERE t.THREAD_ID=%s AND t.PROCESSLIST_ID=%s AND a.ATTR_NAME=%s AND a.ATTR_VALUE=%s',
                    (self.identity['thread_id'], self.identity['connection_id'], self.attribute['name'], self.attribute['value']))
                rows = cursor.fetchall()
                if len(rows) != 1 or rows[0][0] is not None and not isinstance(rows[0][0], str):
                    raise SourceIdentityUnavailable('The original MySQL parser database identity is unavailable')
                database = rows[0][0]
                cursor.close(); cursor = None
                if database is None and self.parser_database is not None:
                    # The observer connector deliberately omits a database and
                    # init command. A new private peer restores the empty scope.
                    observed = self.renew()
                if database is not None and database != self.parser_database:
                    cursor = self.connection.cursor()
                    cursor.execute('USE `' + database.replace('`', '``') + '`')
                    cursor.close(); cursor = None
                    self.parser_database = database
                self.connection.sql_mode = observed['variables']['sql_mode']
                yield self.connection, {**observed, 'default_schema': database,
                    'database_observation_source': 'native-performance-schema-threads-and-source-handshake',
                    'original_active_roles_observed': False, 'original_temporary_objects_observed': False}
            except BaseException:
                self.needs_connection_refresh = True
                try: self.close()
                except Exception: pass
                # The connection owns the failed cursor. Closing it again
                # must not replace the original identity/context failure.
                cursor = None
                raise
            finally:
                if cursor is not None: cursor.close()

    def native_literals(self, parameters, mode):
        """Use the same C driver on the private peer for verified escaping."""
        from mysql.connector.constants import ServerFlag
        with self.lock:
            try:
                observed = self._observe()
                if observed['variables']['sql_mode'] != mode or getattr(self.connection, '_cmysql', None) is None:
                    raise ObserverUnavailable('The private native C conversion context is unavailable')
                charset = observed['variables']['character_set_client']
                context = charset, mode
                if self.escaping_context != context:
                    self.connection.set_charset_collation(charset)
                    self.connection.sql_mode = mode
                    self.escaping_context = context
                acknowledged = bool(self.connection._cmysql.st_server_status() & ServerFlag.STATUS_NO_BACKSLASH_ESCAPES)
                if acknowledged != ('NO_BACKSLASH_ESCAPES' in mode.split(',')):
                    raise ObserverUnavailable('The private C client did not acknowledge the observed native escape mode')
                return self.connection.prepare_for_mysql(parameters)
            except BaseException:
                self.needs_connection_refresh = True
                try: self.close()
                except Exception: pass
                raise


def install(client, handle, request):
    attribute = getattr(handle, '_cdeadmin_observer_attribute', None)
    if not isinstance(attribute, dict) or set(attribute) != {'name', 'value'}:
        return  # Third-party test doubles and other client implementations are not qualified here.
    source = handle.cursor()
    try:
        source.execute('SELECT @@server_uuid,CONNECTION_ID(),HEX(CURRENT_USER()),VERSION(),'
                       '@@performance_schema,IF(@@performance_schema,PS_CURRENT_THREAD_ID(),NULL)')
        server, connection_id, principal, version, enabled, thread_id = source.fetchone()
        source.fetchall()
    finally:
        source.close()
    identity = {'server_uuid': _text(server), 'connection_id': connection_id,
                'principal_hex': _text(principal), 'version': _text(version), 'thread_id': thread_id}
    if connection_id != handle.connection_id or type(connection_id) is not int or connection_id <= 0:
        raise ObserverUnavailable('The retained MySQL observer identity is unavailable')
    handle._cdeadmin_session_variable_observer_status = {'admitted': False,
        'admission_observation_only': True,
        'original_observation_path_qualified': False, 'reason': 'performance-schema-disabled'}
    if not enabled or type(thread_id) is not int or thread_id <= 0:
        return
    reference, owner = weakref.ref(handle), weakref.ref(client)
    session_request = deepcopy(dict(request))
    def connect():
        current, client = reference(), owner()
        if current is None or client is None:
            raise ObserverUnavailable('The retained MySQL observation owner is unavailable')
        def arguments(route):
            selected = dict(client.config.connect_arguments(route))
            for name in ('pool_name', 'pool_size', 'pool_reset_session', 'failover', 'dns_srv',
                         'database', 'init_command', 'sql_mode', 'time_zone', 'collation'):
                selected.pop(name, None)
            selected.update(host=current.server_host, port=current.server_port,
                unix_socket=current.unix_socket, autocommit=True, charset='utf8mb4',
                connection_timeout=5, read_timeout=5, write_timeout=5)
            selected['conn_attrs'] = {**dict(selected.get('conn_attrs') or {}),
                                      'scratchrobin_observer': str(connection_id)}
            return selected
        return client._invoke_connector(session_request, client.module.connect, connect_arguments=arguments)
    observer = SessionVariables(handle, connect, identity, deepcopy(attribute))
    try:
        observer.observe()
    except Exception as error:
        observer.close()
        # A denied/missing native dependency at admission preserves existing
        # functionality. It is an explicit unqualified profile, not a claim
        # that an intrusive observation preserves the native diagnostic area.
        if (not isinstance(error, RelationalClientError) and
                getattr(error, 'errno', None) not in {1040, 1044, 1045, 1142, 1143, 1203, 1226, 1227}):
            raise
        handle._cdeadmin_session_variable_observer_status = {'admitted': False,
            'admission_observation_only': True,
            'original_observation_path_qualified': False, 'reason': 'native-observer-admission-denied',
            'native_errno': getattr(error, 'errno', None), 'native_sqlstate': getattr(error, 'sqlstate', None)}
        handle._cdeadmin_session_variable_observer_candidate = observer
        return
    handle._cdeadmin_session_variable_observer = observer
    handle._cdeadmin_session_variable_observer_status = {'admitted': True,
        'admission_observation_only': True,
        'observation_source': 'native-performance-schema-independent-connection',
        'original_session_commands_sent': 0, 'thread_id': str(thread_id), 'connection_id': str(connection_id),
        'private_observer_connection_retained': True}


def _promote(handle, candidate):
    handle._cdeadmin_session_variable_observer = candidate
    delattr(handle, '_cdeadmin_session_variable_observer_candidate')
    handle._cdeadmin_session_variable_observer_status = {'admitted': True,
        'admission_observation_only': True,
        'observation_source': 'native-performance-schema-independent-connection',
        'original_session_commands_sent': 0,
        'thread_id': str(candidate.identity['thread_id']),
        'connection_id': str(candidate.identity['connection_id']),
        'private_observer_connection_retained': True,
        'readmitted_without_source_commands': True}


def editor_observer(client, handle):
    """Acquire an independent editor observer; never inspect source SQL state."""
    observer = getattr(handle, '_cdeadmin_session_variable_observer', None)
    if isinstance(observer, SessionVariables):
        return observer
    candidate = getattr(handle, '_cdeadmin_session_variable_observer_candidate', None)
    if isinstance(candidate, SessionVariables):
        try:
            candidate.renew()
        except SourceIdentityUnavailable:
            client._uncertain_sessions.add(id(handle))
            raise RelationalClientError('The original MySQL session identity is unconfirmed; close this session') from None
        except Exception as error:
            handle._cdeadmin_session_variable_observer_status = {
                **getattr(handle, '_cdeadmin_session_variable_observer_status', {}),
                'native_errno': getattr(error, 'errno', None),
                'native_sqlstate': getattr(error, 'sqlstate', None)}
        else:
            _promote(handle, candidate)
            return candidate
    profile = getattr(handle, '_cdeadmin_session_variable_observer_status', None)
    profile = profile if isinstance(profile, dict) else {}
    reason = ('disabled' if profile.get('reason') == 'performance-schema-disabled' else
        'denied' if isinstance(candidate, SessionVariables) else 'unadmitted')
    raise EditorObservationUnavailable(reason, profile.get('native_errno'))


def observe(handle):
    observer = getattr(handle, '_cdeadmin_session_variable_observer', None)
    if not isinstance(observer, SessionVariables):
        return None
    try:
        observed = observer.observe()
        current = getattr(handle, '_cdeadmin_charset_variables', None)
        if isinstance(current, dict):
            handle._cdeadmin_charset_variables = {key: observed['variables'][key] for key in current}
            sync = getattr(handle, '_cdeadmin_sync_charset', None)
            if callable(sync):
                sync()
        return observed
    except Exception as error:
        from .mysql_values import MySQLParameterAdmissionError
        result = MySQLParameterAdmissionError('Independent MySQL session variables are unavailable; the user command was not dispatched and no original-session metadata query was substituted')
        result.native_observer_errno = getattr(error, 'errno', None)
        result.native_observer_error_type = type(error).__name__
        handle._cdeadmin_session_variable_observer_status = {
            **getattr(handle, '_cdeadmin_session_variable_observer_status', {}),
            'last_failure_type': type(error).__name__,
            'last_failure_errno': getattr(error, 'errno', None)}
        result.original_session_identity_unconfirmed = isinstance(error, SourceIdentityUnavailable)
        result.original_diagnostics_preserved = not result.original_session_identity_unconfirmed
        observer.needs_connection_refresh = getattr(error, 'errno', None) not in {1044, 1045, 1142, 1143, 1227}
        raise result from None


def require_observation(handle):
    """Admission is a dependency, never permission to query the user's session."""
    observed = observe(handle)
    if observed is not None:
        return observed
    # MySQL-wire engines without this observer declare their own source.
    wire = getattr(handle, '_cdeadmin_wire_language', None)
    if callable(wire) and not hasattr(
            handle, '_cdeadmin_session_variable_observer_status'):
        return wire()
    from .mysql_values import MySQLParameterAdmissionError
    status = getattr(handle, '_cdeadmin_session_variable_observer_status', {})
    status = status if isinstance(status, dict) else {}
    reason = ('disabled' if status.get('reason') == 'performance-schema-disabled' else
        'denied' if status.get('reason') == 'native-observer-admission-denied' else 'unadmitted')
    guidance = EditorObservationUnavailable(reason, status.get('native_errno'))
    failure = MySQLParameterAdmissionError(str(guidance))
    failure.original_diagnostics_preserved = True
    failure.original_session_commands_sent = 0
    failure.native_observer_errno = guidance.native_observer_errno
    failure.native_observer_error_type = 'ObserverUnavailable'
    failure.observation_guidance = str(guidance)
    raise failure


def invalidate(handle):
    observer = getattr(handle, '_cdeadmin_session_variable_observer', None)
    if isinstance(observer, SessionVariables):
        with observer.lock:
            observer.cached = None


def prepare(handle):
    # Execution, like editor assistance, enters here on the authenticated
    # request thread. Restoring grants can readmit the existing source without
    # acquiring credentials or reconnecting either peer from the SQL worker.
    candidate = getattr(handle, '_cdeadmin_session_variable_observer_candidate', None)
    if isinstance(candidate, SessionVariables):
        try:
            candidate.renew()
        except SourceIdentityUnavailable:
            raise
        except Exception as error:
            handle._cdeadmin_session_variable_observer_status = {
                **getattr(handle, '_cdeadmin_session_variable_observer_status', {}),
                'native_errno': getattr(error, 'errno', None),
                'native_sqlstate': getattr(error, 'sqlstate', None)}
        else:
            _promote(handle, candidate)
    observer = getattr(handle, '_cdeadmin_session_variable_observer', None)
    if isinstance(observer, SessionVariables) and observer.needs_connection_refresh:
        observer.renew()


def uninstall(handle):
    native = getattr(handle, '_native', handle)
    if native is None:
        return
    for name in ('_cdeadmin_session_variable_observer', '_cdeadmin_session_variable_observer_candidate'):
        observer = getattr(native, name, None)
        if isinstance(observer, SessionVariables):
            observer.close()
    for name in ('_cdeadmin_session_variable_observer', '_cdeadmin_session_variable_observer_candidate',
                 '_cdeadmin_session_variable_observer_status', '_cdeadmin_admitted_runtime_identity'):
        if hasattr(native, name):
            delattr(native, name)

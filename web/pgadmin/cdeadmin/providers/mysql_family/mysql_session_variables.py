"""Read retained MySQL session variables on a separately authenticated peer.

Admission occurs before user execution. Once admitted, loss or denial never
falls back to an intrusive query on the original session. Unavailable admission
is recorded separately; the pre-existing unqualified observation path remains
available for those profiles until its own workflow is completed.
"""
from copy import deepcopy
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
            self.connection = self.connector()
            self.opened = True
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
        return
    handle._cdeadmin_session_variable_observer = observer
    handle._cdeadmin_session_variable_observer_status = {'admitted': True,
        'admission_observation_only': True,
        'observation_source': 'native-performance-schema-independent-connection',
        'original_session_commands_sent': 0, 'thread_id': str(thread_id), 'connection_id': str(connection_id),
        'private_observer_connection_retained': True}


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


def invalidate(handle):
    observer = getattr(handle, '_cdeadmin_session_variable_observer', None)
    if isinstance(observer, SessionVariables):
        with observer.lock:
            observer.cached = None


def prepare(handle):
    observer = getattr(handle, '_cdeadmin_session_variable_observer', None)
    if isinstance(observer, SessionVariables) and observer.needs_connection_refresh:
        observer.renew()


def uninstall(handle):
    native = getattr(handle, '_native', handle)
    if native is None:
        return
    observer = getattr(native, '_cdeadmin_session_variable_observer', None)
    if isinstance(observer, SessionVariables):
        observer.close()
    for name in ('_cdeadmin_session_variable_observer', '_cdeadmin_session_variable_observer_status'):
        if hasattr(native, name):
            delattr(native, name)

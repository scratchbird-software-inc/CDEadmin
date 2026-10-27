"""Retained native identity and passive, packet-derived session observations.

Identity discovery belongs to session opening. PING and SELECT are commands:
neither is a harmless way to observe a user's diagnostics area or ROW_COUNT().
"""
from copy import deepcopy
from ...sdk import RelationalClientError


class SessionIdentities:
    def __init__(self, engine):
        self.engine = engine
        self.entries = {}
        self.status_unknown = set()

    def register(self, handle):
        variable = 'server_uuid' if self.engine == 'MySQL' else 'server_uid'
        cursor = handle.cursor()
        try:
            cursor.execute(f'SELECT @@{variable}, CONNECTION_ID()')
            server, thread = cursor.fetchone()
            cursor.fetchall()
        finally:
            cursor.close()
        if (not isinstance(server, str) or not server or
                type(thread) is not int or thread <= 0 or
                handle.connection_id != thread):
            raise RelationalClientError(
                self.engine + ' retained native session identity is unavailable')
        self.entries[id(handle)] = (handle, server, thread)
        self.status_unknown.discard(id(handle))

    def get(self, handle):
        entry = self.entries.get(id(handle))
        if entry is None or entry[0] is not handle:
            raise RelationalClientError(
                self.engine + ' retained native session identity is unavailable')
        # Both pinned connectors expose the handshake/native thread id without
        # sending SQL or a ping. An implicit reconnection is never admitted.
        try:
            thread = handle.connection_id
        except Exception:
            raise RelationalClientError(
                self.engine + ' retained native session identity is unavailable') from None
        if type(thread) is not int or thread != entry[2]:
            raise RelationalClientError(
                self.engine + ' retained native session identity changed')
        return entry[1:]

    def forget(self, handle):
        self.entries.pop(id(handle), None)
        self.status_unknown.discard(id(handle))


def transaction_observation(handle, engine, identities, uncertain):
    result = {'driver_observation_only': True,
              'finality_interpreted_by_common_code': False,
              'connection_health_checked': False,
              'observation_source': 'last-native-protocol-status'}
    if engine == 'MySQL':
        observer = getattr(handle, '_cdeadmin_session_variable_observer_status', None)
        if isinstance(observer, dict):
            result['session_variable_observer'] = deepcopy(observer)
    if id(handle) in uncertain:
        return dict(result, state='unknown', connection_usable=False)
    try:
        identities.get(handle)
        if id(handle) in identities.status_unknown:
            # ERR packets do not carry a fresh transaction/autocommit status.
            # A routine may have changed both before reporting its error.
            return dict(result, state='unknown', connection_usable=True,
                        status_current=False)
        if engine == 'MariaDB':
            status = handle.server_status
        else:
            c_api = getattr(handle, '_cmysql', None)
            status = (c_api.st_server_status() if c_api is not None else
                      handle._cdeadmin_server_status)
        if type(status) is not int:
            raise RelationalClientError('Native session status is unavailable')
    except Exception:
        # Failure to observe a local identity/status is not proof of native
        # finality. Do not send a health probe or publish old policy as current.
        return dict(result, state='unknown', connection_usable=False,
                    status_current=False)
    active = bool(status & 1)
    return dict(result, state='active' if active else 'idle',
                autocommit=bool(status & 2), in_transaction=active,
                connection_usable=True, status_current=True)

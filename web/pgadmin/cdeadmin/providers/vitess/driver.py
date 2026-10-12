"""VTGate retained ownership without unsafe gateway-local cancellation."""
import socket

from pgadmin.cdeadmin.sdk import RelationalClientError
from ..mysql_family.mysql_connections import Lease
from ..mysql_wire_driver import RetainedMySQLWireClient


class VitessNativeClient(RetainedMySQLWireClient):
    def error_outcome_known(self, exc):
        # A VTGate ERR can represent a tablet/RPC failure after a dispatch.
        return (super().error_outcome_known(exc) and
                getattr(exc, 'errno', None) in {
                    1044, 1045, 1046, 1051, 1054, 1062, 1064,
                    1146, 1205, 1213, 1235})

    def control_transaction(self, handle, action):
        try:
            return super().control_transaction(handle, action)
        except RelationalClientError:
            state = self._states.get(id(handle), {})
            if state.get('command') == action and not state.get(
                    'command_returned'):
                state.update(outcome_unknown=True, session_reuse_blocked=True)
            raise

    def cancellation_identity(self, handle):
        # Only the socket attached to this retained connection is admissible.
        native = handle._native if isinstance(handle, Lease) else handle
        return getattr(getattr(native, '_socket', None), 'sock', None)

    def cancel_native(self, token):
        native_socket = self.cancellation_identity(token.handle)
        if native_socket is None or native_socket is not token.identity:
            raise RelationalClientError('VTGate retained socket unavailable')
        self._states[id(token.handle)].update(
            session_reuse_blocked=True, outcome_unknown=True,
            cancellation_mode='retained-transport-abort')
        token.uncertain = True
        native_socket.shutdown(socket.SHUT_RDWR)

    def describe_result(self, token):
        result = super().describe_result(token)
        if self._blocked(token.handle):
            result['payload'].update(session_reuse_blocked=True,
                                     outcome_unknown=True)
        return result

    def _forget_and_close(self, handle):
        if not isinstance(handle, Lease):
            return super()._forget_and_close(handle)
        # A successful VTGate reset does not prove complete session isolation.
        try:
            if handle._native is not None:
                handle._native.close()
            handle.discard()
        except Exception:
            self._states.setdefault(id(handle), {})[
                'session_reuse_blocked'] = True
            raise RelationalClientError(
                'Native VTGate connection release failed') from None
        self._forget_connection(handle)
        self._states.pop(id(handle), None)
        self._requests.pop(id(handle), None)
        self._operations = [
            t for t in self._operations if t.handle is not handle]

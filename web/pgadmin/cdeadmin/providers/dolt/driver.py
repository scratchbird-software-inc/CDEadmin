"""Retained Dolt transport with native SQL/version-control separation."""
import socket
from dataclasses import dataclass

from mysql.connector.conversion import MySQLConverter

from pgadmin.cdeadmin.sdk import RelationalClientError
from ..mysql_family.mysql_connections import Lease
from ..mysql_wire_driver import RetainedMySQLWireClient


@dataclass(frozen=True)
class _BinaryParameter:
    value: bytes


class DoltConverter(MySQLConverter):
    def _bytes_to_mysql(self, value):
        return _BinaryParameter(bytes(value))

    def _bytearray_to_mysql(self, value):
        return _BinaryParameter(bytes(value))

    @staticmethod
    def quote(value):
        if isinstance(value, _BinaryParameter):
            return b"X'" + value.value.hex().encode('ascii') + b"'"
        return MySQLConverter.quote(value)


class DoltNativeClient(RetainedMySQLWireClient):
    def _connect(self, request):
        handle = super()._connect(request)
        try:
            handle.set_converter_class(DoltConverter)
        except Exception:
            self._discard_failed_session(handle)
            raise
        return handle

    def cancellation_identity(self, handle):
        # Only the socket attached to this retained connection is admissible.
        native = handle._native if isinstance(handle, Lease) else handle
        return getattr(getattr(native, '_socket', None), 'sock', None)

    def cancel_native(self, token):
        native_socket = self.cancellation_identity(token.handle)
        if native_socket is None or native_socket is not token.identity:
            raise RelationalClientError('Dolt retained socket unavailable')
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
        # A wire reset alone does not prove Dolt branch-state isolation.
        try:
            if handle._native is not None:
                handle._native.close()
            handle.discard()
        except Exception:
            self._states.setdefault(id(handle), {})[
                'session_reuse_blocked'] = True
            raise RelationalClientError(
                'Native Dolt connection release failed') from None
        self._forget_connection(handle)
        self._states.pop(id(handle), None)
        self._requests.pop(id(handle), None)
        self._operations = [
            t for t in self._operations if t.handle is not handle]

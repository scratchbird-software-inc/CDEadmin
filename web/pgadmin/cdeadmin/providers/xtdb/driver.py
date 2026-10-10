"""XTDB-native retained execution and bitemporal value preservation."""
import base64
import math
from collections.abc import Mapping

from .client import XTDBClient, XTDBClientError, MAX_SOURCE_BYTES
from ..pgwire_driver import PoolConnector, native, uncertain
from ..temporal_wire import TemporalOwnership


class XTDBNativeClient(TemporalOwnership, XTDBClient):
    error_class = XTDBClientError
    result_kind = 'document'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._connector = PoolConnector(
            self.module, kwargs.get('pool_namespace', 'xtdb-unscoped'),
            kwargs.get('pool_module'))
        self.initialize_ownership()

    def _connect(self, request):
        with self._ownership_lock:
            if self._closing:
                raise XTDBClientError('XTDB owner is closed')
            return super()._connect(request)

    @staticmethod
    def leased_connection(handle):
        return handle.connection

    @staticmethod
    def native_connection(handle):
        return native(handle.connection)

    def _register_string_dumper(self, connection):
        try:
            super()._register_string_dumper(connection)
        except Exception:
            native(connection).close()
            connection.close()
            raise

    def _forget_and_close(self, session):
        self.release(session)

    def runtime_identity(self, request, handle=None):
        with self._ownership_lock:
            if handle is not None:
                self.idle(handle)
            return super().runtime_identity(request, handle)

    def observe_command(self, handle, command):
        handle.transaction_observation = str(command or 'native-empty-command')

    def describe_transaction(self, handle):
        value = super().describe_transaction(handle)
        value.update(session_reuse_blocked=self.blocked(handle),
                     outcome_unknown=self.blocked(handle))
        return value

    def control_transaction(self, handle, action):
        if action not in self.transaction_actions:
            raise XTDBClientError('XTDB transaction action unavailable')
        with self._ownership_lock:
            self.idle(handle)
            source = self._apply_transaction_defaults(
                action.upper(), handle.route)
            cursor = None
            try:
                cursor = handle.connection.cursor()
                cursor.execute(source)
                self.observe_command(handle, cursor.statusmessage)
            except Exception as exc:
                if uncertain(exc):
                    self.block(handle)
                raise XTDBClientError(
                    'XTDB transaction command failed') from None
            finally:
                if cursor is not None:
                    cursor.close()

    def execute(self, handle, request):
        source = request.get('source')
        if not isinstance(source, str) or not source.strip():
            raise XTDBClientError('XTDB SQL source required')
        if len(source.encode('utf-8')) > MAX_SOURCE_BYTES:
            raise XTDBClientError('XTDB SQL source exceeds limit')
        if handle.route.get('read_only') and self._is_mutation(source):
            raise XTDBClientError('mutations refused on read-only route')
        source = self._apply_transaction_defaults(source, handle.route)
        bound = request.get('parameters') or ()
        if not isinstance(bound, (Mapping, list, tuple)):
            raise XTDBClientError('XTDB bindings require object or array')
        return self.start_operation(
            handle, source, self._adapt_parameters(bound))

    def _adapt_value(self, value):
        if type(value) is int and abs(value) > 2**53 - 1:
            raise XTDBClientError('Use an exact integer envelope')
        if isinstance(value, float) and not math.isfinite(value):
            raise XTDBClientError('Nonfinite JSON number is not admitted')
        if isinstance(value, Mapping):
            if set(value) == {'$xtdb_type', 'value'} and value[
                    '$xtdb_type'] == 'integer':
                text = value['value']
                if not isinstance(text, str) or len(text) > 20:
                    raise XTDBClientError('Invalid integer envelope')
                number = int(text)
                if not -(2**63) <= number < 2**63:
                    raise XTDBClientError('XTDB integer outside int64')
                return number
            if set(value) == {'$xtdb_type', 'base64'} and value[
                    '$xtdb_type'] == 'varbinary':
                return base64.b64decode(value['base64'], validate=True)
        return super()._adapt_value(value)

    @classmethod
    def _json_value(cls, value, depth=0):
        if type(value) is int and abs(value) > 2**53 - 1:
            return {'$xtdb_type': 'integer', 'value': str(value)}
        if isinstance(value, float) and not math.isfinite(value):
            return {'$xtdb_type': 'float', 'value': str(value)}
        return super()._json_value(value, depth)

    def json_value(self, value):
        return self._json_value(value)

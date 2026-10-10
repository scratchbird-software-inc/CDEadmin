"""immudb SQL transport; native REST administration stays separate."""
import base64
import datetime
from decimal import Decimal
import math

from psycopg.adapt import Dumper
from pgadmin.cdeadmin.sdk import RelationalClientError
from ..pgwire_driver import PoolConnector, native, exact_parameters
from ..temporal_wire import TemporalOwnership


class BlobDumper(Dumper):
    oid = 0

    def dump(self, value):
        return bytes(value)

    def quote(self, value):
        return b"x'" + bytes(value).hex().encode('ascii') + b"'"


class ImmudbNativeMixin(TemporalOwnership):
    error_class = RelationalClientError
    result_kind = 'tabular'
    transaction_actions = ('begin', 'commit', 'rollback')

    def __init__(self, config, pool_namespace, module=None, pool_module=None):
        super().__init__(config, pool_namespace, module=module,
                         pool_module=pool_module)
        self._pool_connector = PoolConnector(
            self.module, pool_namespace, pool_module)
        self._connector = self._pool_connector
        self._observations = {}
        self.initialize_ownership()

    @staticmethod
    def native_connection(handle):
        return native(handle)

    @staticmethod
    def leased_connection(handle):
        return handle

    def _connect(self, request, overrides=None):
        with self._ownership_lock:
            if self._closing:
                raise RelationalClientError('immudb owner is closed')
            handle = self._open_connection(request, overrides)
            try:
                for kind in (bytes, bytearray, memoryview):
                    handle.adapters.register_dumper(kind, BlobDumper)
            except Exception:
                self.release(handle)
                raise
            return handle

    def release(self, handle):
        super().release(handle)
        self._observations.pop(id(handle), None)
        self._connection_databases.pop(id(handle), None)

    def _forget_and_close(self, handle):
        self.release(handle)

    def _discard_failed_session(self, handle):
        self.block(handle)
        self.release(handle)

    def observe_command(self, handle, command):
        self._observations[id(handle)] = str(command or 'native-empty-command')

    def describe_transaction(self, handle):
        return dict(native_observation=self._observations.get(id(handle)),
                    native_status=native(handle).info.transaction_status.name,
                    outcome_unknown=self.blocked(handle),
                    session_reuse_blocked=self.blocked(handle),
                    driver_observation_only=True,
                    finality_interpreted_by_common_code=False,
                    automatic_replay=False)

    def control_transaction(self, handle, action):
        if action not in self.transaction_actions:
            raise RelationalClientError(
                'immudb transaction action unavailable')
        with self._ownership_lock:
            self.idle(handle)
            cursor = None
            try:
                cursor = handle.cursor()
                cursor.execute(action.upper())
                self.observe_command(handle, cursor.statusmessage)
            except Exception:
                self.block(handle)
                raise RelationalClientError(
                    'immudb transaction command outcome unknown') from None
            finally:
                if cursor is not None:
                    cursor.close()

    def execute(self, handle, request):
        source = request.get('source')
        if not isinstance(source, str) or not source.strip():
            raise RelationalClientError('immudb SQL source required')
        bound = exact_parameters(request.get('parameters'))
        return self.start_operation(handle, source, bound)

    def runtime_identity(self, request, handle=None):
        with self._ownership_lock:
            if handle is not None:
                self.idle(handle)
            return self._runtime_identity(request, handle)

    def list_resources(self, request):
        # Catalog compatibility fallbacks may reset their own temporary work.
        independent = dict(request)
        independent.pop('_provider_session_handle', None)
        return super().list_resources(independent)

    def _owned_admin(self, method, request):
        handle = request.get('_provider_session_handle')
        with self._ownership_lock:
            if handle is not None:
                self.idle(handle)
            try:
                return method(request)
            except Exception:
                if handle is not None:
                    self.block(handle)
                raise

    def apply_admin_operation(self, request):
        return self._owned_admin(super().apply_admin_operation, request)

    def read_admin_rows(self, request):
        return self._owned_admin(super().read_admin_rows, request)

    @classmethod
    def json_value(cls, value):
        if type(value) is int and abs(value) > 2**53 - 1:
            return {'type': 'integer', 'value': str(value)}
        if isinstance(value, (bytes, bytearray, memoryview)):
            return dict(encoding='base64', data=base64.b64encode(
                bytes(value)).decode('ascii'), byte_length=len(value))
        if isinstance(value, (datetime.date, datetime.time)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return {'type': 'decimal', 'value': str(value)}
        if isinstance(value, float) and not math.isfinite(value):
            return {'type': 'float', 'value': str(value)}
        if isinstance(value, dict):
            return {k: cls.json_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls.json_value(v) for v in value]
        return value

"""Explicitly admitted retained PG-wire transport mechanics."""
import copy
import hashlib
import hmac
import json
import math
import secrets
import threading
import uuid

from pgadmin.cdeadmin.sdk import RelationalClientError
from .distributed_sql import (
    PsycopgPoolDBAPIClient, _PsycopgPoolConnector, _PooledConnectionLease,
)
from .postgresql.execution import Execution, result_pages, parameters, control


def native(handle):
    return getattr(handle, '_connection', handle)


def uncertain(exc):
    code = getattr(exc, 'sqlstate', None)
    return not code or code == '40003' or code.startswith('08')


class PoolLease(_PooledConnectionLease):
    def close(self):
        if self._closed:
            return
        connection = self._connection
        if not connection.closed:
            try:
                connection.rollback()
                connection.autocommit = True
                connection.execute('DISCARD ALL')
                connection.isolation_level = None
                connection.read_only = None
                connection.deferrable = None
                connection.autocommit = False
            except Exception:
                # A failed reset cannot release another user's session state.
                connection.close()
        super().close()


class PoolConnector(_PsycopgPoolConnector):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._key = secrets.token_bytes(32)
        self._lock = threading.RLock()
        self._closed = False

    def __call__(self, *args, **kwargs):
        options = dict(kwargs)
        # DISCARD ALL invalidates server prepared statements between leases.
        # Disable implicit preparation so no client cache survives that reset.
        options['prepare_threshold'] = None
        encoded = json.dumps(options, sort_keys=True, default=str).encode()
        options['cde_route_id'] = hmac.new(
            self._key, encoded, hashlib.sha256).hexdigest()
        with self._lock:
            if self._closed:
                raise RelationalClientError('PG-wire pool owner is closed')
            handle = super().__call__(*args, **options)
            if isinstance(handle, _PooledConnectionLease):
                return PoolLease(handle._pool, handle._connection)
            return handle

    def close(self):
        with self._lock:
            self._closed = True
            failures = []
            for key, pool in list(self._pools.items()):
                try:
                    pool.close()
                    del self._pools[key]
                except Exception:
                    failures.append(key)
            if failures:
                raise RelationalClientError('PG-wire pool cleanup failed')


class PGWireExecution(Execution):
    def __init__(self, handle, source, bound):
        super().__init__(native(handle), source, bound)
        self.handle = handle
        self.reference = str(uuid.uuid4())
        self.final = None
        self.describe_lock = threading.Lock()
        self.cancel_transport_error = None

    def _run(self):
        try:
            for page in result_pages(self.connection, self.source,
                                     self.parameters):
                self._put(page)
        except Exception as exc:
            code = getattr(exc, 'sqlstate', None)
            self.error = {'type': type(exc).__name__, 'sqlstate': code,
                          'transaction_retry_required': code == '40001',
                          'outcome_unknown': code == '40003'}
            self.uncertain = uncertain(exc) or bool(self.connection.closed)
        finally:
            self.source = self.parameters = None
            self.finished.set()

    def cancel(self):
        if self.finished.is_set():
            return False
        self.discard.set()
        try:
            self.connection.cancel_safe(timeout=5)
        except Exception as exc:
            # The cancel socket can fail after delivery. The retained query
            # still owns its connection and determines the actual outcome.
            self.cancel_transport_error = type(exc).__name__
            return False
        return True

    def describe(self):
        with self.describe_lock:
            if self.final is not None:
                return copy.deepcopy(self.final)
            page = self.poll()
            columns = page.pop('columns', [])
            complete = page.pop('complete')
            if self.cancel_transport_error:
                page['cancel_transport_error_type'] = (
                    self.cancel_transport_error)
            result = dict(result_kind='tabular', schema={'columns': columns},
                          payload=page, stream_reference=self.reference,
                          complete=complete)
            if complete:
                self.final = copy.deepcopy(result)
            return result


def exact_parameters(value):
    if value is not None and not isinstance(value, (dict, list, tuple)):
        raise RelationalClientError(
            'PG-wire bindings need object or array')
    items = value.values() if isinstance(value, dict) else value or []
    for item in items:
        if isinstance(item, bool):
            continue
        if isinstance(item, int) and abs(item) > 2**53 - 1:
            raise RelationalClientError('Use an exact integer envelope')
        if isinstance(item, float) and not math.isfinite(item):
            raise RelationalClientError('Use an exact numeric envelope')
    try:
        return parameters(value)
    except (ValueError, TypeError, ArithmeticError):
        raise RelationalClientError(
            'PG-wire query bindings invalid') from None


class RetainedPGWireClient(PsycopgPoolDBAPIClient):
    def __init__(self, config, pool_namespace, module=None, pool_module=None):
        super().__init__(config, pool_namespace, module, pool_module)
        self._pool_connector = PoolConnector(self.module, pool_namespace,
                                             pool_module)
        self._connector = self._pool_connector
        self._lock = threading.RLock()
        self._executions = []
        self._states = {}
        self._busy = set()
        self._closing = False

    def _connect(self, request):
        with self._lock:
            if self._closing:
                raise RelationalClientError('PG-wire client is closed')
            handle = super()._connect(request)
            self._states[id(handle)] = {}
            return handle

    def _idle(self, handle):
        if handle not in self._connections:
            raise RelationalClientError('PG-wire session is unavailable')
        if id(handle) in self._busy or any(
                token.handle is handle and token.final is None
                for token in self._executions):
            raise RelationalClientError(
                'PG-wire session execution is active')
        if self._blocked(handle) or native(handle).closed:
            raise RelationalClientError(
                'PG-wire session unknown; close it')

    def _blocked(self, handle):
        blocked = self._states.get(id(handle), {}).get('session_reuse_blocked')
        return blocked or any(
            token.handle is handle and token.uncertain
            for token in self._executions)

    def list_resources(self, request):
        from .pgwire_catalog import CatalogConnection
        handle = request.get('_provider_session_handle')
        owned = handle is None
        if owned:
            handle = self._connect(request)
        with self._lock:
            self._idle(handle)
            self._busy.add(id(handle))
        try:
            return copy.deepcopy(self.config.metadata_reader(
                CatalogConnection(handle), request))
        finally:
            with self._lock:
                self._busy.discard(id(handle))
                if owned:
                    self._forget_and_close(handle)

    def _admin(self, callback, request):
        handle = request.get('_provider_session_handle')
        if handle is None:
            return callback(request)
        with self._lock:
            self._idle(handle)
            self._busy.add(id(handle))
        try:
            return callback(request)
        finally:
            with self._lock:
                self._busy.discard(id(handle))

    def read_admin_rows(self, request):
        return self._admin(super().read_admin_rows, request)

    def apply_admin_operation(self, request):
        return self._admin(super().apply_admin_operation, request)

    def execute(self, handle, request):
        source = request.get('source')
        if not isinstance(source, str) or not source.strip():
            raise RelationalClientError('PG-wire query source is required')
        bound = exact_parameters(request.get('parameters'))
        with self._lock:
            self._idle(handle)
            token = PGWireExecution(handle, source, bound)
            self._executions.append(token)
            try:
                token.start()
            except Exception:
                self._executions.remove(token)
                raise RelationalClientError(
                    'PG-wire execution could not start') from None
            return token

    def describe_result(self, token):
        if token not in self._executions:
            raise RelationalClientError('PG-wire result token is invalid')
        return token.describe()

    def cancel(self, token):
        with self._lock:
            if token not in self._executions:
                raise RelationalClientError(
                    'PG-wire result token is invalid')
            try:
                return token.cancel()
            except Exception as exc:
                token.uncertain = True
                raise RelationalClientError(
                    'PG-wire cancellation outcome unknown') from None

    def describe_transaction(self, handle):
        if handle not in self._connections:
            raise RelationalClientError('PG-wire session is unavailable')
        return dict(self._states[id(handle)],
                    native_transaction_status=native(handle).info.
                    transaction_status.name,
                    session_reuse_blocked=bool(self._blocked(handle)),
                    driver_observation_only=True,
                    finality_interpreted_by_common_code=False)

    def control_transaction(self, handle, action):
        if action not in self.transaction_actions:
            raise RelationalClientError(
                'PG-wire transaction action invalid')
        with self._lock:
            self._idle(handle)
            self._busy.add(id(handle))
        state = self._states[id(handle)]
        state.clear()
        try:
            returned, status = control(native(handle), action.upper())
            state.update(command_returned=returned, command_status=status,
                         outcome_unknown=False)
        except Exception as exc:
            code = getattr(exc, 'sqlstate', None)
            state.update(command_returned=False, error_type=type(exc).__name__,
                         sqlstate=code,
                         transaction_retry_required=code == '40001',
                         outcome_unknown=uncertain(exc),
                         session_reuse_blocked=uncertain(exc))
            raise RelationalClientError(
                'PG-wire transaction command failed: ' +
                type(exc).__name__ + (' ' + code if code else '')) from None
        finally:
            with self._lock:
                self._busy.discard(id(handle))

    def _forget_and_close(self, handle):
        try:
            if self._blocked(handle):
                native(handle).close()
            handle.close()
        except Exception:
            self._states.setdefault(id(handle), {})[
                'session_reuse_blocked'] = True
            raise RelationalClientError('PG-wire release failed') from None
        self._forget_connection(handle)
        self._states.pop(id(handle), None)
        self._executions = [
            t for t in self._executions if t.handle is not handle]

    def _discard_failed_session(self, handle):
        self._states.setdefault(id(handle), {})['session_reuse_blocked'] = True
        self._forget_and_close(handle)

    def close_session(self, handle):
        with self._lock:
            if handle not in self._connections:
                raise RelationalClientError('PG-wire session unavailable')
            if id(handle) in self._busy:
                raise RelationalClientError(
                    'PG-wire session operation active')
            for token in self._executions:
                if token.handle is not handle:
                    continue
                if not token.finished.is_set():
                    try:
                        token.cancel()
                    except Exception:
                        token.uncertain = True
                        token.discard.set()
                        native(handle).close()
                token.worker.join(timeout=5)
                if not token.finished.is_set():
                    raise RelationalClientError(
                        'PG-wire worker still owns session')
                while token.final is None:
                    token.describe()
            state = self.describe_transaction(handle)
            if not self._blocked(handle) and not native(handle).closed:
                try:
                    native(handle).rollback()
                except Exception:
                    self._states[id(handle)]['session_reuse_blocked'] = True
                    state['outcome_unknown'] = True
            self._forget_and_close(handle)
            return dict(state, connection_released=True)

    def close(self):
        with self._lock:
            self._closing = True
            failures = []
            for handle in list(self._connections):
                try:
                    self.close_session(handle)
                except Exception:
                    failures.append(True)
            if failures:
                raise RelationalClientError(
                    'PG-wire session cleanup incomplete')
            self._pool_connector.close()

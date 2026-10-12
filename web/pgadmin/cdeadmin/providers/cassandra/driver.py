"""Cassandra-only admission of retained native CQL wire mechanics."""
import threading
import ipaddress

from .client import CassandraClient, CassandraClientError
from ..cql_native import MAX_QUERY_BYTES
from ..yugabytedb_ycql.driver import (
    YCQLExecution, bindings as cql_bindings, prepared_bindings,
)

ERROR = CassandraClientError


def bindings(values):
    def native(value):
        if isinstance(value, dict):
            if set(value) == {'type', 'value'}:
                if value['type'] == 'inet':
                    return str(ipaddress.ip_address(value['value']))
                if value['type'] == 'duration':
                    from cassandra.util import Duration
                    parts = value['value']
                    keys = ('months', 'days', 'nanoseconds')
                    if not isinstance(parts, dict) or set(parts) != set(keys):
                        raise ValueError('Duration fields invalid')
                    if not all(isinstance(parts[k], str) for k in keys):
                        raise ValueError('Duration fields require exact text')
                    return Duration(*(int(parts[k]) for k in keys))
            return {k: native(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [native(v) for v in value]
        return value
    try:
        return cql_bindings(native(values))
    except (ValueError, TypeError, ArithmeticError):
        raise ERROR('Cassandra exact parameter invalid') from None


class NativeCassandraClient(CassandraClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lock = threading.RLock()
        self._closing = False
        self._owned_operations = []
        self._pending_native_cleanup = []

    def _cluster_options(self, *args, **kwargs):
        from cassandra.policies import FallthroughRetryPolicy
        options = super()._cluster_options(*args, **kwargs)
        options['default_retry_policy'] = FallthroughRetryPolicy()
        # Legacy execution mode uses NoSpeculativeExecutionPolicy in 3.30.1;
        # every statement is also explicitly non-idempotent.
        return options

    def _close_native(self, cluster, session):
        failed = False
        for value in (session, cluster):
            if value is not None:
                try:
                    value.shutdown()
                except Exception:
                    failed = True
        pair = (cluster, session)
        if failed:
            if pair not in self._pending_native_cleanup:
                self._pending_native_cleanup.append(pair)
            raise ERROR('Cassandra temporary cleanup incomplete')
        if pair in self._pending_native_cleanup:
            self._pending_native_cleanup.remove(pair)

    def _connect(self, request):
        if self._closing:
            raise ERROR('Cassandra client is closed')
        return super()._connect(request)

    def open_session(self, request):
        with self._lock:
            if self._closing:
                raise ERROR('Cassandra client is closed')
            return super().open_session(request)

    def runtime_identity(self, request, handle=None):
        with self._lock:
            if handle is not None:
                self._idle(handle)
            return super().runtime_identity(request, handle)

    def _idle(self, handle):
        if handle not in self._sessions or handle.closed:
            raise ERROR('Cassandra session is unavailable')
        for token in self._owned_operations:
            if token.handle is handle:
                if token.final is None:
                    raise ERROR('Cassandra session execution is active')
                if token.uncertain:
                    raise ERROR('Cassandra outcome is unknown; close session')

    def execute(self, handle, request):
        source = request.get('source')
        if (not isinstance(source, str) or not source.strip() or
                len(source.encode('utf-8')) > MAX_QUERY_BYTES):
            raise ERROR('Cassandra query source is invalid')
        trace = request.get('trace', False)
        if not isinstance(trace, bool):
            raise ERROR('Cassandra trace flag must be boolean')
        try:
            bound = bindings(request.get('parameters'))
        except CassandraClientError as exc:
            raise ERROR(str(exc).replace('YCQL', 'Cassandra')) from None
        if bound:
            try:
                source, bound = prepared_bindings(source, bound)
            except CassandraClientError as exc:
                raise ERROR(str(exc).replace('YCQL', 'Cassandra')) from None
        with self._lock:
            self._idle(handle)
            statement = self._statement(source, handle.route, fetch_size=500)
            statement.is_idempotent = False
            token = YCQLExecution(handle, source, bound, statement, trace)
            self._owned_operations.append(token)
            try:
                token.start()
            except Exception:
                self._owned_operations.remove(token)
                raise ERROR('Cassandra worker could not start') from None
            return token

    def describe_result(self, token):
        if token not in self._owned_operations:
            raise ERROR('Cassandra result token is invalid')
        result = token.describe()
        if token.trace:
            traces = getattr(token.future, '_query_traces', None) or ()
            trace_ids = [str(t.trace_id) for t in traces]
            trace_id = trace_ids[-1] if trace_ids else None
            observation = result['schema']['native_observation']
            observation['trace_id'] = trace_id
            observation['trace_ids'] = trace_ids
            observation['trace_storage'] = 'system_traces'
            result['payload'].update(observation)
        return result

    def cancel(self, token):
        with self._lock:
            if token not in self._owned_operations:
                raise ERROR('Cassandra result token is invalid')
            return token.cancel()

    def describe_transaction(self, handle):
        state = super().describe_transaction(handle)
        state['session_reuse_blocked'] = any(
            t.handle is handle and t.uncertain for t in self._owned_operations)
        return state

    def close_session(self, handle):
        with self._lock:
            if handle not in self._sessions:
                raise ERROR('Cassandra session is unavailable')
            for token in self._owned_operations:
                if token.handle is handle:
                    token.cancel()
                    token.worker.join(timeout=5)
                    if not token.finished.is_set():
                        raise ERROR('Cassandra operation still owns session')
            state = self.describe_transaction(handle)
            failures = []
            for native in (handle.session, handle.cluster):
                try:
                    native.shutdown()
                except Exception:
                    failures.append(True)
            if failures:
                raise ERROR('Cassandra native cleanup incomplete')
            handle.closed = True
            self._sessions.remove(handle)
            self._owned_operations = [t for t in self._owned_operations
                                      if t.handle is not handle]
            return dict(state, connection_released=True)

    def close(self):
        with self._lock:
            self._closing = True
            failures = []
            for handle in list(self._sessions):
                try:
                    self.close_session(handle)
                except Exception:
                    failures.append(True)
            for cluster, session in list(self._pending_native_cleanup):
                try:
                    self._close_native(cluster, session)
                except Exception:
                    failures.append(True)
            if failures:
                raise ERROR('Cassandra owned cleanup incomplete')
            self._results.clear()
            self._row_identities.clear()
            self._admin_cursors.clear()

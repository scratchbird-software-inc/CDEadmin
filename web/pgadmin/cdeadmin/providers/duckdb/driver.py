"""DuckDB-owned retained sessions, lossless execution and interruption."""
import copy
import json
import queue
import threading
import uuid

from pgadmin.cdeadmin.sdk import (
    RelationalDBAPIClient, RelationalClientError, load_optional_module,
)
from .values import parameters, scalar
from .unions import project, restore


def identity(exc):
    # Driver messages can contain SQL, paths, secrets or bound values.
    return {'type': type(exc).__name__}


def uncertain(exc):
    import duckdb
    return not isinstance(exc, duckdb.Error) or isinstance(
        exc, (duckdb.IOException, duckdb.FatalException,
              duckdb.InternalException))


def viability(connection):
    import duckdb
    try:
        connection.execute('SELECT current_transaction_id()').fetchone()
        return 'viable'
    except duckdb.TransactionException as exc:
        if 'current transaction is aborted' in str(exc).lower():
            return 'aborted'
        raise


class Execution:
    def __init__(self, connection, source, bound, observe):
        self.connection, self.source, self.bound = connection, source, bound
        self.observe = observe
        self.reference = str(uuid.uuid4())
        self.pages = queue.Queue(2)
        self.finished, self.stop = threading.Event(), threading.Event()
        self.lock = threading.Lock()
        self.error, self.final = None, None
        self.uncertain = False
        self.index = 0
        self.worker = threading.Thread(target=self._run, daemon=True,
                                       name='cdeadmin-duckdb-query')

    def _put(self, columns, rows, offset, end):
        page = {'schema': {'columns': columns}, 'payload': {
            'rows': rows, 'has_page': True, 'row_offset': offset,
            'result_set_index': self.index, 'result_set_end': end,
            'rowcount': None}}
        while not self.stop.is_set():
            try:
                self.pages.put(page, timeout=.05)
                return
            except queue.Full:
                pass

    def _run(self):
        import duckdb
        reader = None
        try:
            statements = self.connection.extract_statements(self.source)
            if len(statements) != 1 and self.bound:
                self.error = {'type': 'ParameterShapeError',
                              'statement_index': None}
                return
            for self.index, statement in enumerate(statements):
                if self.stop.is_set():
                    break
                if statement.type != duckdb.StatementType.TRANSACTION:
                    self.connection.execute(
                        'SET arrow_lossless_conversion=true')
                kinds = None
                if (duckdb.ExpectedResultType.QUERY_RESULT in
                        statement.expected_result_type):
                    relation = self.connection.sql(statement.query,
                                                   params=self.bound)
                    if relation is None:
                        # sql() executes non-returning DML once; this API does
                        # not expose its count. Never replay to obtain one.
                        self._put([], [], 0, True)
                        continue
                    names = list(relation.columns)
                    relation, kinds = project(relation)
                    native = list(zip(names, kinds))
                    reader = relation.to_arrow_reader(256)
                else:
                    self.connection.execute(statement, self.bound)
                    native = list(self.connection.description or ())
                    reader = self.connection.to_arrow_reader(256)
                columns = [{'name': native[i][0], 'key': str(i), 'ordinal': i,
                            'native_type': str(native[i][1]),
                            'arrow_type': str(field.type)}
                           for i, field in enumerate(reader.schema)]
                offset, rows, size = 0, [], 0
                for batch in reader:
                    for index in range(batch.num_rows):
                        if self.stop.is_set():
                            break
                        row = [scalar(column[index])
                               for column in batch.columns]
                        if kinds is not None:
                            row = [restore(value, kind)
                                   for value, kind in zip(row, kinds)]
                        length = len(json.dumps(row, ensure_ascii=True))
                        if rows and (len(rows) >= 256 or
                                     size + length > 1024 * 1024):
                            self._put(columns, rows, offset, False)
                            offset += len(rows)
                            rows, size = [], 0
                        rows.append(row)
                        size += length
                    if self.stop.is_set():
                        break
                reader.close()
                reader = None
                self._put(columns, rows, offset, True)
        except Exception as exc:
            self.error = dict(identity(exc), statement_index=self.index)
            self.uncertain = uncertain(exc)
        finally:
            if reader is not None:
                try:
                    reader.close()
                except Exception as exc:
                    self.error, self.uncertain = identity(exc), True
            try:
                self.observe(self.connection, self.uncertain)
            except Exception as exc:
                self.error, self.uncertain = identity(exc), True
            self.source = self.bound = None
            self.finished.set()

    def cancel(self):
        if self.finished.is_set():
            return False
        self.stop.set()
        self.connection.interrupt()
        return True

    def describe(self):
        with self.lock:
            if self.final is not None:
                return copy.deepcopy(self.final)
            try:
                page = self.pages.get(timeout=.05)
            except queue.Empty:
                page = {'schema': {'columns': []},
                        'payload': {'rows': [], 'has_page': False}}
            complete = self.finished.is_set() and self.pages.empty()
            page.update(result_kind='columnar', complete=complete,
                        stream_reference=self.reference)
            page['payload']['cancel_requested'] = self.stop.is_set()
            if complete:
                page['payload'].update(error=self.error,
                                       session_reuse_blocked=self.uncertain)
                self.final = copy.deepcopy(page)
            return page


class DuckDBClient(RelationalDBAPIClient):
    def __init__(self, config, module=None):
        super().__init__(config, module)
        load_optional_module('pyarrow')
        self._lock = threading.RLock()
        self._executions = []
        self._states = {}
        self._busy = set()
        self._closing = False

    def _connect(self, request):
        with self._lock:
            if self._closing:
                raise RelationalClientError('DuckDB client is closed')
            handle = super()._connect(request)
            self._states[id(handle)] = {'session_reuse_blocked': False}
            return handle

    def _require_idle(self, handle):
        if handle not in self._connections:
            raise RelationalClientError('DuckDB session is unavailable')
        if id(handle) in self._busy or any(
                token.connection is handle and token.final is None
                for token in self._executions):
            raise RelationalClientError('DuckDB session execution is active')
        if self._states[id(handle)].get('session_reuse_blocked'):
            raise RelationalClientError(
                'DuckDB session state unknown; close it')

    def _observe(self, handle, blocked=False):
        state = self._states[id(handle)]
        if blocked:
            state['session_reuse_blocked'] = True
        else:
            state['native_transaction_viability'] = viability(handle)

    def execute(self, handle, request):
        source = request.get('source')
        if not isinstance(source, str) or not source.strip():
            raise RelationalClientError('DuckDB source is required')
        bound = parameters(request.get('parameters'))
        with self._lock:
            self._require_idle(handle)
            token = Execution(handle, source, bound, self._observe)
            self._executions.append(token)
            token.worker.start()
            return token

    def describe_result(self, token):
        if token not in self._executions:
            raise RelationalClientError('DuckDB result token is invalid')
        return token.describe()

    def cancel(self, token):
        with self._lock:
            if token not in self._executions:
                raise RelationalClientError('DuckDB result token is invalid')
            return token.cancel()

    def describe_transaction(self, handle):
        with self._lock:
            if handle not in self._connections:
                raise RelationalClientError('DuckDB session is unavailable')
            return dict(self._states[id(handle)], driver_observation_only=True,
                        finality_interpreted_by_common_code=False)

    def control_transaction(self, handle, action):
        if action not in self.transaction_actions:
            raise RelationalClientError('DuckDB transaction action is invalid')
        with self._lock:
            self._require_idle(handle)
            self._busy.add(id(handle))
        state = self._states[id(handle)]
        try:
            prior = viability(handle)
            handle.execute(action.upper())
            state['last_decision'] = ('rollback' if prior == 'aborted'
                                      else action)
            state['decision_returned'] = True
            state['next_transaction_started'] = False
            try:
                handle.execute('BEGIN TRANSACTION')
                state['next_transaction_started'] = True
                state['native_transaction_viability'] = 'viable'
            except Exception as exc:
                state['next_transaction_error'] = identity(exc)
                state['session_reuse_blocked'] = True
        except Exception as exc:
            state['decision_returned'] = False
            state['decision_error'] = identity(exc)
            if uncertain(exc):
                state['session_reuse_blocked'] = True
            raise RelationalClientError(
                'DuckDB transaction command failed: ' +
                type(exc).__name__) from None
        finally:
            with self._lock:
                self._busy.discard(id(handle))

    def list_resources(self, request):
        with self._lock:
            handle = request.get('_provider_session_handle')
            if handle is not None:
                self._require_idle(handle)
            return super().list_resources(request)

    def _forget_and_close(self, handle):
        try:
            handle.close()
        except Exception:
            self._states.setdefault(id(handle), {})[
                'session_reuse_blocked'] = True
            raise RelationalClientError(
                'DuckDB native release failed') from None
        self._forget_connection(handle)
        self._states.pop(id(handle), None)
        self._executions = [token for token in self._executions
                            if token.connection is not handle]

    def _discard_failed_session(self, handle):
        self._forget_and_close(handle)

    def close_session(self, handle):
        with self._lock:
            if id(handle) in self._busy:
                raise RelationalClientError(
                    'DuckDB session operation is active')
            if handle not in self._connections:
                raise RelationalClientError('DuckDB session is unavailable')
            for token in self._executions:
                if token.connection is handle:
                    token.cancel()
                    token.worker.join(timeout=5)
                    if not token.finished.is_set():
                        raise RelationalClientError(
                            'DuckDB worker still owns the connection')
                    while token.final is None:
                        token.describe()
            state = copy.deepcopy(self._states[id(handle)])
            self._forget_and_close(handle)
            return dict(state, connection_released=True,
                        native_close_discards_uncommitted=True,
                        driver_observation_only=True)

    def close(self):
        with self._lock:
            self._closing = True
            failures = []
            for handle in list(self._connections):
                try:
                    self.close_session(handle)
                except Exception as exc:
                    failures.append(type(exc).__name__)
            if failures:
                raise RelationalClientError('DuckDB cleanup is incomplete')
            self._executions.clear()

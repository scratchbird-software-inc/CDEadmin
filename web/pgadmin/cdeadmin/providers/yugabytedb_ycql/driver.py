"""Retained YCQL operations with native paging and no mutation replay."""
import base64
import copy
import hashlib
import time
from datetime import date, datetime, time as datetime_time
from decimal import Decimal
import ipaddress
import json
import math
import re
import threading
import uuid

from ..postgresql.execution import Execution
from ..cql_native import MAX_QUERY_BYTES
from .client import YugabyteDBYCQLClient, YugabyteDBYCQLClientError


ERROR = YugabyteDBYCQLClientError


def exact(value):
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return value if abs(value) <= 2**53 - 1 else {'$integer': str(value)}
    if isinstance(value, float):
        return value if math.isfinite(value) else {'$float': str(value)}
    if isinstance(value, Decimal):
        return {'$decimal': str(value)}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {'$binary': base64.b64encode(bytes(value)).decode('ascii'),
                '$encoding': 'base64', 'byte_length': len(value)}
    if isinstance(value, (uuid.UUID, ipaddress.IPv4Address,
                          ipaddress.IPv6Address)):
        return {'$type': type(value).__name__, '$value': str(value)}
    if isinstance(value, (date, datetime, datetime_time)) or (
            type(value).__module__ == 'cassandra.util' and
            type(value).__name__ in {'Date', 'Time', 'Duration'}):
        return {'$temporal': type(value).__name__, '$value': str(value)}
    if isinstance(value, dict):
        return {'$map': [[exact(k), exact(v)] for k, v in value.items()]}
    if hasattr(value, '_asdict'):
        return {'$udt': {k: exact(v) for k, v in value._asdict().items()}}
    if isinstance(value, tuple):
        return {'$tuple': [exact(v) for v in value]}
    if isinstance(value, (set, frozenset)) or (
            type(value).__module__ == 'cassandra.util' and
            type(value).__name__ == 'SortedSet'):
        return {'$set': sorted([exact(v) for v in value],
                               key=lambda v: json.dumps(v, sort_keys=True))}
    if isinstance(value, list):
        return [exact(v) for v in value]
    # Cassandra ordered maps need not subclass dict.
    if hasattr(value, 'items'):
        return {'$map': [[exact(k), exact(v)] for k, v in value.items()]}
    raise ERROR('YCQL result type cannot be represented exactly')


def bindings(values):
    from cassandra.util import Date, Time

    def scalar(value):
        if isinstance(value, int) and not isinstance(value, bool):
            if abs(value) > 2**53 - 1:
                raise ValueError('Use an exact integer envelope')
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('Use an exact float envelope')
        if isinstance(value, dict):
            if set(value) == {'type', 'value'}:
                kind, data = value['type'], value['value']
                if kind in {'set', 'tuple'} and isinstance(data, list):
                    return (set if kind == 'set' else tuple)(
                        scalar(item) for item in data)
                if kind == 'map' and isinstance(data, list):
                    return {scalar(k): scalar(v) for k, v in data}
                if not isinstance(data, str):
                    raise ValueError('Exact scalar needs text')
                constructors = {
                    'integer': int, 'decimal': Decimal, 'float': float,
                    'uuid': uuid.UUID, 'inet': ipaddress.ip_address,
                    'date': Date, 'time': Time,
                    'timestamp': datetime.fromisoformat,
                    'binary': lambda v: base64.b64decode(v, validate=True),
                }
                if kind not in constructors:
                    raise ValueError('Unknown exact scalar')
                return constructors[kind](data)
            return {key: scalar(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [scalar(item) for item in value]
        return value

    if values is None:
        return ()
    if not isinstance(values, (dict, list, tuple)):
        raise ERROR('YCQL parameters need an object or array')
    try:
        return ({key: scalar(value) for key, value in values.items()}
                if isinstance(values, dict) else [scalar(v) for v in values])
    except (TypeError, ValueError, ArithmeticError):
        raise ERROR('YCQL exact parameter is invalid') from None


def prepared_bindings(source, values):
    """Translate placeholders outside CQL quoted/comment tokens only."""
    tokens = re.compile(
        r"'(''|[^'])*'|\"(\"\"|[^\"])*\"|--[^\n]*|//[^\n]*|"
        r"/\*[\s\S]*?\*/|%\(([^)]+)\)s|%s|\?")
    ordered, positional = [], 0
    mapping = isinstance(values, dict)

    def replace(match):
        nonlocal positional
        token = match.group()
        if token.startswith(("'", '\"', '--', '//', '/*')):
            return token
        if token.startswith('%('):
            if not mapping:
                raise ValueError('Named binding needs object')
            ordered.append(values[match.group(3)])
        else:
            if mapping:
                raise ValueError('Positional binding needs array')
            ordered.append(values[positional])
            positional += 1
        return '?'

    try:
        prepared = tokens.sub(replace, source)
        if not mapping and positional != len(values):
            raise ValueError('Parameter count mismatch')
        return prepared, ordered
    except (KeyError, IndexError, TypeError, ValueError):
        raise ERROR(
            'YCQL parameter placeholders do not match bindings') from None


def ordinal_rows(names, rows):
    """Capture ordinal rows before dispatch; preserve repeated labels."""
    return [tuple(row) for row in rows]


class YCQLExecution(Execution):
    def __init__(self, handle, source, parameters, statement, trace):
        super().__init__(handle, source, parameters)
        self.handle = handle
        self.statement = statement
        self.trace = trace
        self.source_sha256 = hashlib.sha256(source.encode()).hexdigest()
        self.future = None
        self.reference = str(uuid.uuid4())
        self.final = None
        self.observe_lock = threading.Lock()
        self.local_stop = False
        self.native_warnings = []
        self.worker.name = 'cdeadmin-ycql-query'

    def _run(self):
        try:
            session = self.handle.session
            statement = self.statement
            if self.parameters:
                prepared = session.prepare(self.source)
                statement = prepared.bind(self.parameters)
                statement.consistency_level = self.statement.consistency_level
                statement.serial_consistency_level = (
                    self.statement.serial_consistency_level)
                statement.fetch_size = 500
                statement.is_idempotent = False
            previous = session.row_factory
            try:
                session.row_factory = ordinal_rows
                self.future = session.execute_async(
                    statement, trace=self.trace)
            finally:
                session.row_factory = previous
            result = self.future.result()
            offset, page_index = 0, 0
            while True:
                self.native_warnings = [str(v) for v in
                                        getattr(self.future, 'warnings', ())
                                        or ()]
                names = list(result.column_names or [])
                types = list(result.column_types or [])
                columns = [dict(name=name, key=str(i), pos=i,
                                type=str(types[i]) if i < len(types)
                                else 'ycql-native')
                           for i, name in enumerate(names)]
                rows, size = [], 0
                for row in result.current_rows or []:
                    value = {str(i): exact(v) for i, v in enumerate(row)}
                    length = len(json.dumps(value, ensure_ascii=True))
                    if rows and (len(rows) >= 256 or size + length > 1048576):
                        self._page(columns, rows, page_index, offset, False)
                        offset += len(rows)
                        page_index += 1
                        rows, size = [], 0
                    rows.append(value)
                    size += length
                more = bool(result.has_more_pages)
                self._page(columns, rows, page_index, offset, not more)
                offset += len(rows)
                page_index += 1
                if not more or self.discard.is_set():
                    break
                result.fetch_next_page()
        except Exception as exc:
            name = type(exc).__name__
            self.uncertain = name not in {
                'InvalidRequest', 'SyntaxException', 'Unauthorized',
                'AuthenticationFailed', 'AlreadyExists',
                'ConfigurationException',
            }
            self.error = dict(type=name,
                              native_code=getattr(exc, 'code', None),
                              outcome_unknown=self.uncertain)
        finally:
            self.source = self.parameters = self.statement = None
            self.finished.set()

    def _page(self, columns, rows, page_index, offset, end):
        self._put(dict(columns=columns, rows=rows, has_page=True,
                       page_index=page_index, result_set_index=0,
                       row_offset=offset, result_set_end=end))

    def cancel(self):
        if self.finished.is_set():
            return False
        self.local_stop = True
        self.discard.set()
        return True

    def describe(self):
        with self.observe_lock:
            if self.final is not None:
                return copy.deepcopy(self.final)
            page = self.poll()
            columns, complete = page.pop('columns', []), page.pop('complete')
            trace_id = getattr(self.future, 'trace_id', None)
            observation = dict(local_delivery_stopped=self.local_stop,
                               server_cancellation_confirmed=False,
                               common_finality_inference=False,
                               trace_requested=self.trace,
                               trace_id=str(trace_id) if trace_id else None,
                               warnings=list(self.native_warnings))
            page.update(observation)
            result = dict(result_kind='wide_column',
                          schema={'columns': columns,
                                  'native_observation': observation},
                          payload=page, complete=complete,
                          stream_reference=self.reference)
            if complete:
                self.final = copy.deepcopy(result)
            return result


class NativeYCQLClient(YugabyteDBYCQLClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lock = threading.RLock()
        self._closing = False
        self._owned_operations = []

    def _cluster_options(self, *args, **kwargs):
        from cassandra.policies import FallthroughRetryPolicy
        options = super()._cluster_options(*args, **kwargs)
        options['default_retry_policy'] = FallthroughRetryPolicy()
        # Legacy execution mode uses NoSpeculativeExecutionPolicy in 3.30.1;
        # every statement is also explicitly non-idempotent.
        return options

    def _connect(self, request):
        if self._closing:
            raise ERROR('YCQL client is closed')
        return super()._connect(request)

    def open_session(self, request):
        with self._lock:
            if self._closing:
                raise ERROR('YCQL client is closed')
            return super().open_session(request)

    def _idle(self, handle):
        if handle not in self._sessions or handle.closed:
            raise ERROR('YCQL session is unavailable')
        for token in self._owned_operations:
            if token.handle is handle:
                if token.final is None:
                    raise ERROR('YCQL session execution is active')
                if token.uncertain:
                    raise ERROR('YCQL outcome is unknown; close session')

    def execute(self, handle, request):
        source = request.get('source')
        if (not isinstance(source, str) or not source.strip() or
                len(source.encode('utf-8')) > MAX_QUERY_BYTES):
            raise ERROR('YCQL query source is invalid')
        trace = request.get('trace', False)
        if not isinstance(trace, bool):
            raise ERROR('YCQL trace flag must be boolean')
        bound = bindings(request.get('parameters'))
        if bound:
            source, bound = prepared_bindings(source, bound)
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
                raise ERROR('YCQL worker could not start') from None
            return token

    def describe_result(self, token):
        if token not in self._owned_operations:
            raise ERROR('YCQL result token is invalid')
        result = token.describe()
        if token.trace:
            observation = result['schema']['native_observation']
            trace_id = observation['trace_id']
            storage = 'rpc-response-receipt' if trace_id else 'server-log'
            self._trace_receipts[token.reference] = {
                'session_id': token.reference, 'trace_id': trace_id,
                'trace_requested': True, 'source_sha256': token.source_sha256,
                'observed_at_unix': time.time(),
                'server_trace_storage': storage,
            }
            if len(self._trace_receipts) > 1024:
                self._trace_receipts.pop(next(iter(self._trace_receipts)))
            observation.update(trace_request_receipt_id=token.reference,
                               trace_storage=storage)
        return result

    def cancel(self, token):
        with self._lock:
            if token not in self._owned_operations:
                raise ERROR('YCQL result token is invalid')
            return token.cancel()

    def describe_transaction(self, handle):
        state = super().describe_transaction(handle)
        state['session_reuse_blocked'] = any(
            t.handle is handle and t.uncertain for t in self._owned_operations)
        return state

    def close_session(self, handle):
        with self._lock:
            if handle not in self._sessions:
                raise ERROR('YCQL session is unavailable')
            for token in self._owned_operations:
                if token.handle is handle:
                    token.cancel()
                    token.worker.join(timeout=5)
                    if not token.finished.is_set():
                        raise ERROR('YCQL operation still owns session')
            state = self.describe_transaction(handle)
            failures = []
            for native in (handle.session, handle.cluster):
                try:
                    native.shutdown()
                except Exception:
                    failures.append(True)
            if failures:
                raise ERROR('YCQL native cleanup incomplete')
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
            if failures:
                raise ERROR('YCQL owned cleanup incomplete')
            self._results.clear()
            self._row_identities.clear()
            self._admin_cursors.clear()

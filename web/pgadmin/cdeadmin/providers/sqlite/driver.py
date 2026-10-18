"""SQLite-owned execution, interruption and retained connection lifecycle."""
import copy
import json
import os
import queue
import re
import shutil
import sqlite3
import threading
import time
import uuid

from pgadmin.cdeadmin.sdk import RelationalClientError, RelationalDBAPIClient
from .values import parameters, value


def error_identity(exc):
    return {key: item for key, item in {
        'type': type(exc).__name__,
        'sqlite_errorcode': getattr(exc, 'sqlite_errorcode', None),
        'sqlite_errorname': getattr(exc, 'sqlite_errorname', None),
    }.items() if isinstance(item, (str, int))}


def uncertain_error(exc):
    code = getattr(exc, 'sqlite_errorcode', None)
    return code is None or (
        code & 255) in {
        sqlite3.SQLITE_IOERR,
        sqlite3.SQLITE_CORRUPT,
        sqlite3.SQLITE_NOTADB,
        sqlite3.SQLITE_PROTOCOL,
        sqlite3.SQLITE_INTERNAL,
        sqlite3.SQLITE_MISUSE,
    }


class SQLiteConnection(sqlite3.Connection):
    """Retain authorization policy so editor compilation can compose it."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cdeadmin_authorizer = None
        self._cdeadmin_progress_handler = (None, 0)
        self._cdeadmin_extension_directories = []
        self._cdeadmin_internal_sql = threading.local()
        self._cdeadmin_session_api = None
        self._cdeadmin_array_api = None
        self._cdeadmin_preupdate_api = None
        self._cdeadmin_trace_callback = None

    def close(self):
        if self._cdeadmin_preupdate_api is not None:
            self._cdeadmin_preupdate_api.close_all()
        if self._cdeadmin_array_api is not None:
            self._cdeadmin_array_api.close_all()
        if self._cdeadmin_session_api is not None:
            self._cdeadmin_session_api.close_all()
        super().close()
        self._cdeadmin_session_api = None
        self._cdeadmin_array_api = None
        self._cdeadmin_preupdate_api = None
        for directory in self._cdeadmin_extension_directories:
            shutil.rmtree(directory, ignore_errors=True)
        self._cdeadmin_extension_directories.clear()

    def set_trace_callback(self, callback):
        if callback is not None and not callable(callback):
            raise TypeError('SQLite trace callback must be callable or None')
        self._cdeadmin_trace_callback = callback
        def trace(source):
            if not getattr(self._cdeadmin_internal_sql, 'session_api', False) and not getattr(self._cdeadmin_internal_sql, 'array_api', False) and not getattr(self._cdeadmin_internal_sql, 'preupdate_api', False):
                return callback(source)
        super().set_trace_callback(None if callback is None else trace)

    def set_authorizer(self, callback):
        super().set_authorizer(callback)
        self._cdeadmin_authorizer = callback

    def set_progress_handler(self, callback, n):
        super().set_progress_handler(callback, n)
        self._cdeadmin_progress_handler = (callback, n) if callback is not None and n > 0 else (None, 0)


class Execution:
    def __init__(self, connection, source, bound):
        self.connection = connection
        self.source, self.bound = source, bound
        self.reference = str(uuid.uuid4())
        self.pages = queue.Queue(2)
        self.finished = threading.Event()
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.error = None
        self.uncertain = False
        self.final = None
        self.metrics = None
        self.worker = threading.Thread(target=self._run, daemon=True,
                                       name='cdeadmin-sqlite-query')

    def _put(self, page):
        while not self.stop.is_set():
            try:
                self.pages.put(page, timeout=.05)
                return
            except queue.Full:
                pass

    def _run(self):
        cursor = None
        started = time.perf_counter()
        dispatched = None
        buffered = 0
        try:
            if self.stop.is_set():
                return
            cursor = self.connection.cursor()
            cursor.execute(self.source, self.bound)
            dispatched = time.perf_counter()
            columns = [{'name': item[0], 'key': str(i), 'ordinal': i,
                        'native_type': 'dynamic'}
                       for i, item in enumerate(cursor.description or ())]
            offset, rows, size = 0, [], 0
            while cursor.description and not self.stop.is_set():
                native = cursor.fetchone()
                if native is None:
                    break
                row = [value(item) for item in native]
                length = len(json.dumps(row, ensure_ascii=True))
                if rows and (len(rows) >= 256 or size + length > 1024 * 1024):
                    self._put(self._page(columns, rows, offset, False, None))
                    offset += len(rows)
                    rows, size = [], 0
                rows.append(row)
                size += length
                buffered += 1
            self._put(self._page(columns, rows, offset, True, cursor.rowcount))
        except Exception as exc:
            self.error = error_identity(exc)
            self.uncertain = uncertain_error(exc)
        finally:
            ended = time.perf_counter()
            self.metrics = {
                'prepare_ms': None,
                'dispatch_ms': round((dispatched - started) * 1000, 3)
                    if dispatched is not None else None,
                'fetch_ms': round((ended - dispatched) * 1000, 3)
                    if dispatched is not None else None,
                'execute_ms': round((ended - started) * 1000, 3),
                'rows_buffered': buffered,
                'plan': None,
                'measurement_scope': (
                    'Client dispatch through final local row fetch and encoding; '
                    'may include consumer backpressure. Preparation is not '
                    'separately measured. No plan is inferred.'),
            }
            if cursor is not None:
                try:
                    cursor.close()
                except Exception as exc:
                    self.error = error_identity(exc)
                    self.uncertain = True
            self.source = self.bound = None
            self.finished.set()

    @staticmethod
    def _page(columns, rows, offset, end, rowcount):
        return {
            'schema': {
                'columns': columns},
            'payload': {
                'rows': rows,
                'has_page': True,
                'row_offset': offset,
                'result_set_index': 0,
                'result_set_end': end,
                'rowcount': rowcount}}

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
            page.update(result_kind='tabular', complete=complete,
                        stream_reference=self.reference)
            page['payload']['cancel_requested'] = self.stop.is_set()
            if complete:
                page['payload'].update(error=self.error,
                                       session_reuse_blocked=self.uncertain,
                                       statement_metrics=self.metrics)
                self.final = copy.deepcopy(page)
            return page


class SQLiteClient(RelationalDBAPIClient):
    def __init__(self, config, module=None):
        super().__init__(config, module)
        if getattr(self.module, 'threadsafety', 0) == 0:
            raise RelationalClientError('SQLite runtime must support threads')
        self._lock = threading.RLock()
        self._executions = []
        self._uncertain = set()
        self._busy = set()
        self._closing = False

    def _connect(self, request):
        with self._lock:
            if self._closing:
                raise RelationalClientError('SQLite client is closed')
            observed = getattr(self.module, 'sqlite_version', None)
            if observed != self.config.profile.exact_version:
                raise RelationalClientError(
                    'SQLite native runtime does not match the admitted '
                    f'{self.config.profile.exact_version} profile')
            return super()._connect(request)

    def _require_idle(self, handle):
        if handle not in self._connections:
            raise RelationalClientError('SQLite session is unavailable')
        if id(handle) in self._busy:
            raise RelationalClientError('SQLite session operation is active')
        for token in self._executions:
            if token.connection is handle:
                if token.final is None:
                    raise RelationalClientError(
                        'SQLite session execution is active')
                if token.uncertain:
                    self._uncertain.add(id(handle))
        if id(handle) in self._uncertain:
            raise RelationalClientError(
                'SQLite session state is unknown; close it')

    def validate_parse_only(self, handle, source):
        """Compile on the retained SQLite schema without executing the VM."""
        if not isinstance(source, str) or not source.strip():
            raise RelationalClientError('SQLite source is required')
        with self._lock:
            self._require_idle(handle)
            self._busy.add(id(handle))
        try:
            statement = source.strip()
            leading = re.sub(r'^(?:(?:[\s\ufeff]+)|(?:--[^\r\n]*(?:\r?\n|$))|(?:/\*[\s\S]*?\*/))*', '', statement)
            if not re.match(r'^EXPLAIN\b', leading, re.I):
                statement = 'EXPLAIN ' + statement
            if not isinstance(handle, SQLiteConnection):
                return {'grammar_valid': None, 'scope': 'SQLite editor authorization policy is unavailable; compilation was not attempted.'}
            previous = handle._cdeadmin_authorizer
            suppressed = False
            def authorize(action, first, second, database, context):
                nonlocal suppressed
                admitted = (previous(action, first, second, database, context)
                    if previous is not None else sqlite3.SQLITE_OK)
                if admitted != sqlite3.SQLITE_OK:
                    return admitted
                if action == sqlite3.SQLITE_PRAGMA:
                    # pragma.c checks authorization before settings changes or
                    # SQLITE_FCNTL_PRAGMA callbacks. IGNORE parses native SQL
                    # syntax while suppressing those prepare-time effects.
                    suppressed = True
                    return sqlite3.SQLITE_IGNORE
                return sqlite3.SQLITE_OK
            cursor = handle.cursor()
            handle.set_authorizer(authorize)
            try:
                cursor.execute(statement)
                cursor.fetchone()
                return {'grammar_valid': True, 'pragma_preparation_suppressed': suppressed,
                    'scope': 'SQLite native EXPLAIN compilation; PRAGMA settings and VFS callbacks are suppressed; no submitted statement VM was executed.'}
            except sqlite3.ProgrammingError as error:
                if 'binding' in str(error).lower():
                    return {'grammar_valid': None,
                        'scope': 'SQLite parsed a parameterized statement; bindings are required for full native validation.'}
                raise
            except sqlite3.Error as error:
                message = str(error)
                syntax = any(marker in message.lower() for marker in (
                    'syntax error', 'incomplete input', 'unrecognized token'))
                return {'grammar_valid': False if syntax else None,
                    'scope': 'SQLite native compilation; submitted SQL was not executed.',
                    'diagnostic': {'code': 'SQLITE_NATIVE_SYNTAX' if syntax else 'SQLITE_NATIVE_CONTEXT',
                        'message': message[:400], 'severity': 'error' if syntax else 'warning'}}
            finally:
                try:
                    handle.set_authorizer(previous)
                except Exception:
                    with self._lock:
                        self._uncertain.add(id(handle))
                    raise RelationalClientError('SQLite editor authorization cleanup is unconfirmed; close this session') from None
                finally:
                    cursor.close()
        finally:
            with self._lock:
                self._busy.discard(id(handle))

    def execute(self, handle, request):
        source = request.get('source')
        if not isinstance(source, str) or not source.strip():
            raise RelationalClientError('SQLite query source is required')
        bound = parameters(request.get('parameters'))
        with self._lock:
            self._require_idle(handle)
            from .array_bindings import bind_arrays
            source,bound=bind_arrays(handle,source,bound)
            token = Execution(handle, source, bound)
            token.worker.start()
            self._executions.append(token)
            return token

    def describe_result(self, token):
        if token not in self._executions:
            raise RelationalClientError('SQLite result token is invalid')
        return token.describe()

    def cancel(self, token):
        with self._lock:
            if token not in self._executions:
                raise RelationalClientError('SQLite result token is invalid')
            return token.cancel()

    def describe_transaction(self, handle):
        with self._lock:
            uncertain = (id(handle) in self._uncertain or any(
                token.connection is handle and token.uncertain
                for token in self._executions))
            return dict(super().describe_transaction(handle),
                        session_reuse_blocked=uncertain)

    def control_transaction(self, handle, action):
        if action not in self.transaction_actions:
            raise RelationalClientError('SQLite transaction action is invalid')
        with self._lock:
            self._require_idle(handle)
            self._busy.add(id(handle))
        try:
            getattr(handle, action)()
        except Exception as exc:
            with self._lock:
                if uncertain_error(exc):
                    self._uncertain.add(id(handle))
            identity = error_identity(exc)
            raise RelationalClientError(
                'SQLite transaction command failed: ' +
                json.dumps(identity, sort_keys=True)) from None
        finally:
            with self._lock:
                self._busy.discard(id(handle))

    def close_session(self, handle):
        with self._lock:
            if id(handle) in self._busy:
                raise RelationalClientError(
                    'SQLite session operation is active')
            if handle not in self._connections:
                raise RelationalClientError('SQLite session is unavailable')
            for token in self._executions:
                if token.connection is not handle:
                    continue
                token.cancel()
                token.worker.join(timeout=5)
                if not token.finished.is_set():
                    raise RelationalClientError(
                        'SQLite worker still owns the session')
                while token.final is None:
                    token.describe()
                if token.uncertain:
                    self._uncertain.add(id(handle))
            rollback_requested = False
            rollback_error = None
            try:
                if id(handle) not in self._uncertain and handle.in_transaction:
                    rollback_requested = True
                    handle.rollback()
            except Exception as exc:
                rollback_error = error_identity(exc)
                self._uncertain.add(id(handle))
            uncertain = id(handle) in self._uncertain
            self._forget_and_close(handle)
            return {'connection_released': True,
                    'rollback_requested': rollback_requested,
                    'rollback_error': rollback_error,
                    'outcome_unknown': uncertain,
                    'driver_observation_only': True}

    def _forget_and_close(self, connection):
        # Never remove the last owner before native release succeeds.
        try:
            connection.close()
        except Exception:
            self._uncertain.add(id(connection))
            raise RelationalClientError(
                'SQLite connection release failed') from None
        self._forget_connection(connection)
        self._uncertain.discard(id(connection))

    def _discard_failed_session(self, connection):
        self._forget_and_close(connection)

    def run_database_operation(self, connection, route, operation_id, options):
        with self._lock:
            self._require_idle(connection)
            if operation_id == 'backup':
                from ..embedded_route import contained_database
                target = contained_database(
                    dict(route, database=options.get('backup_path')))
                for other in self._connections:
                    database = self._connection_databases.get(id(other))
                    if (other is connection or not database or
                            database == ':memory:'):
                        continue
                    if os.path.realpath(database) == target or (
                            os.path.exists(database) and os.path.exists(target)
                            and os.path.samefile(database, target)):
                        raise RelationalClientError(
                            'SQLite backup destination is attached')
            self._busy.add(id(connection))
        try:
            return super().run_database_operation(connection, route,
                                                  operation_id, options)
        except RelationalClientError as exc:
            if getattr(exc, 'session_reuse_blocked', False):
                with self._lock:
                    self._uncertain.add(id(connection))
            raise
        finally:
            with self._lock:
                self._busy.discard(id(connection))

    def list_resources(self, request):
        with self._lock:
            handle = request.get('_provider_session_handle')
            if handle is not None:
                self._require_idle(handle)
            return super().list_resources(request)

    def close(self):
        with self._lock:
            self._closing = True
            failures = []
            for connection in list(self._connections):
                try:
                    self.close_session(connection)
                except Exception as exc:
                    failures.append(type(exc).__name__)
            if failures:
                raise RelationalClientError(
                    'SQLite session cleanup is incomplete')
            self._executions.clear()

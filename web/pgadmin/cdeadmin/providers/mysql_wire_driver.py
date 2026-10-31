"""Retained MySQL-wire mechanics with explicit engine-owned cancellation."""
import copy
from dataclasses import replace
import json
import threading
import uuid

from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.sdk.relational import RelationalDBAPIClient
from .mysql_family.mysql_connections import Connector, Lease
from .mysql_family.mysql_values import Cursor, columns, parameters
from .postgresql.execution import Execution


ERROR = RelationalClientError


def server_error(exc):
    number = getattr(exc, 'errno', None)
    state = getattr(exc, 'sqlstate', None)
    return (isinstance(number, int) and number >= 1000 and
            not 2000 <= number < 3000 and isinstance(state, str) and
            len(state) == 5)


def session_language(handle):
    """Read the native language on the session itself, as before 2026-10-25.

    Dolt, TiDB and Vitess have no MySQL Performance Schema session observer,
    so the MySQL family's independent observation cannot be admitted for
    them. The source is labelled so it is never taken for that observation.
    """
    cursor = handle.cursor()
    try:
        cursor.execute('SELECT VERSION(), @@SESSION.sql_mode')
        version, mode = cursor.fetchone()
    finally:
        cursor.close()
    if isinstance(mode, bytes):
        mode = mode.decode('ascii')
    if isinstance(version, bytes):
        version = version.decode('ascii')
    return {'observation_source': 'mysql-wire-original-session',
            'original_session_commands_sent': 1, 'version': version,
            'variables': {'sql_mode': mode}}


class CatalogCursor:
    _cde_catalog_isolated = True

    def __init__(self, native):
        self.native = native

    def __getattr__(self, name):
        return getattr(self.native, name)

    def cde_optional_rows(self, source, bound=()):
        try:
            self.native.execute(source, bound)
            return list(self.native.fetchall())
        except Exception as exc:
            if getattr(exc, 'errno', None) in {1054, 1146, 1142, 1227, 1235}:
                return []
            raise


class CatalogConnection:
    def __init__(self, native):
        self.native = native

    def cursor(self, *args, **kwargs):
        return CatalogCursor(self.native.cursor(*args, **kwargs))

    def __getattr__(self, name):
        return getattr(self.native, name)


class WireExecution(Execution):
    def __init__(self, client, handle, source, bound, request):
        super().__init__(handle, source, bound)
        self.client, self.handle, self.request = client, handle, request
        self.reference = str(uuid.uuid4())
        self.final, self.identity, self.cancel_error = None, None, None
        self.observe_lock = threading.Lock()
        self.worker.name = 'cdeadmin-mysql-wire-query'

    def _run(self):
        cursor = None
        try:
            self.identity = self.client.cancellation_identity(self.handle)
            cursor = Cursor(self.handle)
            cursor.execute(self.source, self.parameters or None)
            index = 0
            while True:
                schema = columns(cursor)
                rows, size, offset = [], 0, 0
                if cursor.description:
                    while True:
                        row = (cursor.native.fetchone()
                               if self.discard.is_set() else cursor.fetchone())
                        if row is None:
                            break
                        if self.discard.is_set():
                            rows = []
                            continue
                        length = len(json.dumps(row, ensure_ascii=True))
                        if rows and (len(rows) >= 256 or size +
                                     length > 1048576):
                            self._page(
                                schema, rows, index, offset, False, None)
                            offset += len(rows)
                            rows, size = [], 0
                        rows.append(row)
                        size += length
                self._page(schema, rows, index, offset, True, cursor.rowcount)
                if not cursor.nextset():
                    break
                index += 1
        except Exception as exc:
            self.error = dict(type=type(exc).__name__,
                              errno=getattr(exc, 'errno', None),
                              sqlstate=getattr(exc, 'sqlstate', None),
                              transaction_retry_required=(
                                  getattr(exc, 'errno', None) in
                                  self.client.retry_errors))
            self.uncertain = not self.client.error_outcome_known(exc)
        finally:
            if cursor is not None and not self.uncertain:
                try:
                    cursor.close()
                except Exception:
                    self.uncertain = True
            self.source = self.parameters = None
            self.finished.set()

    def _page(self, schema, rows, index, offset, end, count):
        self._put(dict(columns=schema, rows=rows, has_page=True,
                       result_set_index=index, row_offset=offset,
                       result_set_end=end, rowcount=count))

    def cancel(self):
        if self.finished.is_set():
            return False
        if self.identity is None:
            raise ERROR('Native cancellation identity is unavailable')
        try:
            self.client.cancel_native(self)
            self.discard.set()
            return True
        except Exception as exc:
            self.cancel_error = type(exc).__name__
            return False

    def describe(self):
        with self.observe_lock:
            if self.final is not None:
                return copy.deepcopy(self.final)
            page = self.poll()
            schema, complete = page.pop('columns', []), page.pop('complete')
            page.update(cancel_request_sent=self.discard.is_set(),
                        cancel_error_type=self.cancel_error)
            result = dict(schema={'columns': schema}, payload=page,
                          complete=complete, result_kind='tabular',
                          stream_reference=self.reference)
            if complete:
                self.final = copy.deepcopy(result)
            return result


class RetainedMySQLWireClient(RelationalDBAPIClient):
    retry_errors = frozenset({1213})

    def __init__(self, config, module=None):
        route_arguments = config.connect_arguments

        def arguments(route):
            pure = route.get('use_pure', True)
            if type(pure) is not bool:
                raise ERROR('MySQL-wire use_pure must be Boolean')
            return dict(route_arguments(route), use_pure=pure)

        super().__init__(replace(config, connect_arguments=arguments), module)
        self._wire_connector = Connector(self.module)
        self._connector = self._wire_connector
        self._lock = threading.RLock()
        self._operations, self._states, self._requests = [], {}, {}
        self._busy = set()
        self._closing = False

    def _connect(self, request):
        with self._lock:
            if self._closing:
                raise ERROR('MySQL-wire owner is closed')
            handle = super()._connect(request)
            handle._cdeadmin_wire_language = (
                lambda: session_language(handle))
            self._states[id(handle)] = {}
            self._requests[id(handle)] = copy.deepcopy(request)
            return handle

    def _blocked(self, handle):
        blocked = self._states.get(id(handle), {}).get('session_reuse_blocked')
        return blocked or any(
            t.handle is handle and t.uncertain for t in self._operations)

    def _idle(self, handle):
        if handle not in self._connections:
            raise ERROR('MySQL-wire session is unavailable')
        if id(handle) in self._busy or any(
                t.handle is handle and t.final is None
                for t in self._operations):
            raise ERROR('MySQL-wire session execution is active')
        if self._blocked(handle):
            raise ERROR('MySQL-wire outcome unknown; close session')

    def error_outcome_known(self, exc):
        return server_error(exc)

    def cancellation_identity(self, handle):
        raise NotImplementedError('Engine must admit cancellation identity')

    def cancel_native(self, token):
        raise NotImplementedError('Engine must admit native cancellation')

    def execute(self, handle, request):
        source = request.get('source')
        if not isinstance(source, str) or not source.strip():
            raise ERROR('MySQL-wire query source required')
        bound = parameters(request.get('parameters'))
        with self._lock:
            self._idle(handle)
            token = WireExecution(self, handle, source, bound,
                                  self._requests[id(handle)])
            self._operations.append(token)
            try:
                token.start()
            except Exception:
                self._operations.remove(token)
                raise ERROR('MySQL-wire worker could not start') from None
            return token

    def describe_result(self, token):
        if token not in self._operations:
            raise ERROR('MySQL-wire result token is invalid')
        return token.describe()

    def cancel(self, token):
        with self._lock:
            if token not in self._operations:
                raise ERROR('MySQL-wire result token is invalid')
            return token.cancel()

    def describe_transaction(self, handle):
        if handle not in self._connections:
            raise ERROR('MySQL-wire session is unavailable')
        try:
            active = handle.in_transaction
        except Exception:
            active = None
            self._states[id(handle)]['session_reuse_blocked'] = True
        return dict(self._states[id(handle)],
                    in_transaction=active,
                    session_reuse_blocked=bool(self._blocked(handle)),
                    driver_observation_only=True,
                    finality_interpreted_by_common_code=False)

    def control_transaction(self, handle, action):
        if action not in self.transaction_actions:
            raise ERROR('MySQL-wire transaction action invalid')
        with self._lock:
            self._idle(handle)
            self._busy.add(id(handle))
        state = self._states[id(handle)]
        state.clear()
        try:
            getattr(handle, action)()
            state.update(command_returned=True, command=action,
                         outcome_unknown=False)
        except Exception as exc:
            state.update(command_returned=False, command=action,
                         error_type=type(exc).__name__,
                         errno=getattr(exc, 'errno', None),
                         sqlstate=getattr(exc, 'sqlstate', None),
                         transaction_retry_required=(
                             getattr(exc, 'errno', None) in self.retry_errors),
                         outcome_unknown=not server_error(exc),
                         session_reuse_blocked=not server_error(exc))
            raise ERROR('Native transaction command failed') from None
        finally:
            with self._lock:
                self._busy.discard(id(handle))

    def list_resources(self, request):
        handle = request.get('_provider_session_handle')
        owned = handle is None
        if owned:
            handle = self._connect(request)
        with self._lock:
            self._idle(handle)
            self._busy.add(id(handle))
        try:
            return self.config.metadata_reader(
                CatalogConnection(handle), request)
        except Exception as exc:
            if not self.error_outcome_known(exc):
                self._states[id(handle)].update(
                    session_reuse_blocked=True, outcome_unknown=True)
            raise
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
        except Exception as exc:
            if not self.error_outcome_known(exc):
                self._states[id(handle)].update(
                    session_reuse_blocked=True, outcome_unknown=True)
            raise
        finally:
            with self._lock:
                self._busy.discard(id(handle))

    def apply_admin_operation(self, request):
        return self._admin(super().apply_admin_operation, request)

    def read_admin_rows(self, request):
        return self._admin(super().read_admin_rows, request)

    def _forget_and_close(self, handle):
        try:
            if self._blocked(handle):
                native = handle._native if isinstance(
                    handle, Lease) else handle
                if native is not None:
                    native.close()
                if isinstance(handle, Lease):
                    handle.discard()
            else:
                handle.close()
        except Exception:
            self._states.setdefault(id(handle), {})[
                'session_reuse_blocked'] = True
            raise ERROR('Native connection release failed') from None
        self._forget_connection(handle)
        self._states.pop(id(handle), None)
        self._requests.pop(id(handle), None)
        self._operations = [
            t for t in self._operations if t.handle is not handle]

    def _discard_failed_session(self, handle):
        self._states.setdefault(id(handle), {})['session_reuse_blocked'] = True
        self._forget_and_close(handle)

    def close_session(self, handle):
        with self._lock:
            if id(handle) in self._busy:
                raise ERROR('MySQL-wire session operation active')
            for token in self._operations:
                if token.handle is handle and not token.finished.is_set():
                    token.discard.set()
                    try:
                        token.cancel()
                    except Exception:
                        pass
                    token.worker.join(5)
                    if not token.finished.is_set():
                        raise ERROR('MySQL-wire worker still owns session')
            state = self.describe_transaction(handle)
            if not self._blocked(handle):
                try:
                    handle.rollback()
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
                raise ERROR('Native session cleanup incomplete')
            self._wire_connector.close()

"""Retained transport mechanics explicitly admitted by temporal clients."""
import copy
import json
import socket
import threading
import uuid

from .postgresql.execution import Execution
from .pgwire_driver import uncertain


class TemporalExecution(Execution):
    def __init__(self, client, handle, source, bound):
        self.client, self.handle = client, handle
        super().__init__(client.native_connection(handle), source, bound)
        self.reference, self.final = str(uuid.uuid4()), None
        self.observe_lock = threading.Lock()

    def _run(self):
        cursor = None
        try:
            cursor = self.connection.cursor()
            cursor.execute(self.source, self.parameters or None)
            index = 0
            while True:
                descriptions = cursor.description or ()
                names = [str(d[0]) for d in descriptions]
                reserved, used, columns = set(names), set(), []
                for i, d in enumerate(descriptions):
                    key, suffix = names[i], 2
                    while key in used:
                        key = names[i] + '#' + str(suffix)
                        suffix += 1
                        if key in reserved:
                            key = names[i]
                    used.add(key)
                    columns.append(dict(name=names[i], key=key, ordinal=i,
                                        native_type=str(d[1])))
                rows, size, offset = [], 0, 0
                if columns:
                    while True:
                        row = cursor.fetchone()
                        if row is None:
                            break
                        if self.discard.is_set():
                            rows = []
                            continue
                        record = {columns[i]['key']: self.client.json_value(v)
                                  for i, v in enumerate(row)}
                        length = len(json.dumps(record, ensure_ascii=True))
                        if rows and (len(rows) >= 256 or
                                     size + length > 1048576):
                            self._page(columns, rows, index, offset, False)
                            offset += len(rows)
                            rows, size = [], 0
                        rows.append(record)
                        size += length
                self._page(columns, rows, index, offset, True,
                           cursor.statusmessage)
                self.client.observe_command(self.handle, cursor.statusmessage)
                if not cursor.nextset():
                    break
                index += 1
        except Exception as exc:
            self.error = dict(type=type(exc).__name__,
                              sqlstate=getattr(exc, 'sqlstate', None))
            self.uncertain = uncertain(exc) or self.connection.closed
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    self.uncertain = True
            self.source = self.parameters = None
            self.finished.set()

    def _page(self, columns, rows, index, offset, end, command=None):
        self._put(dict(columns=columns, rows=rows, has_page=True,
                       result_set_index=index, row_offset=offset,
                       result_set_end=end, command=command))

    def cancel(self):
        if self.finished.is_set():
            return False
        self.client.block(self.handle)
        self.uncertain = True
        self.discard.set()
        # Borrow the retained descriptor without transferring close ownership.
        borrowed = socket.socket(fileno=self.connection.pgconn.socket)
        try:
            borrowed.shutdown(socket.SHUT_RDWR)
        finally:
            borrowed.detach()
        return True

    def describe(self):
        with self.observe_lock:
            if self.final is not None:
                return copy.deepcopy(self.final)
            page = self.poll()
            columns, complete = page.pop('columns', []), page.pop('complete')
            if self.client.blocked(self.handle):
                page.update(session_reuse_blocked=True, outcome_unknown=True)
            result = dict(result_kind=self.client.result_kind,
                          schema={'columns': columns}, payload=page,
                          complete=complete, stream_reference=self.reference)
            if complete:
                self.final = copy.deepcopy(result)
            return result


class TemporalOwnership:
    """Mix into an engine adapter; no SQL transaction policy is supplied."""

    def initialize_ownership(self):
        self._operations, self._blocked_handles = [], set()
        self._ownership_lock = threading.RLock()
        self._closing = False

    def block(self, handle):
        self._blocked_handles.add(id(handle))

    def blocked(self, handle):
        return id(handle) in self._blocked_handles or any(
            t.handle is handle and t.uncertain for t in self._operations)

    def idle(self, handle):
        if handle not in self._connections:
            raise self.error_class('Native session is unavailable')
        if self.blocked(handle):
            raise self.error_class('Native outcome unknown; close session')
        if any(t.handle is handle and t.final is None
               for t in self._operations):
            raise self.error_class('Native session execution is active')

    def start_operation(self, handle, source, bound):
        with self._ownership_lock:
            self.idle(handle)
            token = TemporalExecution(self, handle, source, bound)
            self._operations.append(token)
            try:
                token.start()
            except Exception:
                self._operations.remove(token)
                raise
            return token

    def describe_result(self, token):
        if token not in self._operations:
            raise self.error_class('Native result token is invalid')
        return token.describe()

    def cancel(self, token):
        with self._ownership_lock:
            if token not in self._operations:
                raise self.error_class('Native result token is invalid')
            return token.cancel()

    def release(self, handle):
        with self._ownership_lock:
            for token in self._operations:
                if token.handle is handle and not token.finished.is_set():
                    token.discard.set()
                    token.cancel()
                    token.worker.join(5)
                    if not token.finished.is_set():
                        raise self.error_class(
                            'Native worker still owns session')
            connection = self.native_connection(handle)
            try:
                connection.close()
                leased = self.leased_connection(handle)
                if leased is not connection:
                    leased.close()
            except Exception:
                self.block(handle)
                raise self.error_class(
                    'Native session cleanup failed') from None
            self._connections.remove(handle)
            self._blocked_handles.discard(id(handle))
            self._operations = [
                t for t in self._operations if t.handle is not handle]

    def close_session(self, handle):
        observation = self.describe_transaction(handle)
        self.release(handle)
        return dict(observation, connection_released=True)

    def close(self):
        with self._ownership_lock:
            self._closing = True
            failures = []
            for handle in list(self._connections):
                try:
                    self.release(handle)
                except Exception:
                    failures.append(True)
            if failures:
                raise self.error_class('Native session cleanup incomplete')
            super().close()

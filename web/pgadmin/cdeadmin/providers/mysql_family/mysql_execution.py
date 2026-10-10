"""One protocol owner per MySQL execution, bounded ordered native results."""
import copy
import json
import queue
import threading
import uuid
from dataclasses import dataclass, field

from pgadmin.cdeadmin.sdk import RelationalClientError
from .mysql_values import Cursor, columns, parameters


@dataclass(eq=False)
class Execution:
    connection: object
    request: dict
    reference: str = field(default_factory=lambda: str(uuid.uuid4()))
    pages: queue.Queue = field(default_factory=lambda: queue.Queue(2))
    finished: threading.Event = field(default_factory=threading.Event)
    worker: object = None
    identity: object = None
    cancelled: bool = False
    closed: bool = False
    error: object = None
    cleanup_failed: bool = False
    poll_lock: object = field(default_factory=threading.Lock)


class Executions:
    PAGE_ROWS = 256
    PAGE_BYTES = 1024 * 1024

    def __init__(self, client):
        self.client = client
        self.tokens = []
        self.lock = threading.RLock()

    def active(self, handle):
        return next((t for t in self.tokens if t.connection is handle
                     and not t.finished.is_set()), None)

    def require_idle(self, handle):
        if self.active(handle):
            raise RelationalClientError('MySQL session execution is active')

    def execute(self, handle, request, session_request):
        source = request.get('source')
        if not isinstance(source, str) or not source.strip():
            raise RelationalClientError('MySQL query source is required')
        bound = parameters(request.get('parameters', ()))
        with self.lock:
            self.require_idle(handle)
            self.client._require_usable_session(handle)
            token = Execution(handle, copy.deepcopy(session_request))
            token.worker = threading.Thread(
                target=self._run, args=(token, source, bound), daemon=True,
                name='cdeadmin-mysql-' + token.reference[:8])
            self.tokens.append(token)
            token.worker.start()
            return token

    def _put(self, token, page):
        while not token.cancelled:
            try:
                token.pages.put(page, timeout=0.1)
                return
            except queue.Full:
                pass

    @staticmethod
    def _error(exc):
        return {key: item for key, item in {
            'type': type(exc).__name__, 'errno': getattr(exc, 'errno', None),
            'sqlstate': getattr(exc, 'sqlstate', None),
        }.items() if isinstance(item, (str, int))}

    def _run(self, token, source, bound):
        cursor = None
        try:
            identity_cursor = token.connection.cursor()
            try:
                identity_cursor.execute(
                    'SELECT @@server_uuid, CONNECTION_ID()')
                server, connection_id = identity_cursor.fetchone()
                token.identity = (str(server), int(connection_id))
            finally:
                identity_cursor.close()
            cursor = Cursor(token.connection)
            if bound:
                cursor.execute(source, bound)
            else:
                cursor.execute(source)
            index = 0
            while True:
                schema = columns(cursor)
                offset, rows, size = 0, [], 0
                if cursor.description:
                    while True:
                        # Cancelled streams drain without converting or storing
                        # discarded values. Native packets are still consumed.
                        row = (cursor.native.fetchone() if token.cancelled
                               else cursor.fetchone())
                        if row is None:
                            break
                        if token.cancelled:
                            rows = []
                            continue
                        row_size = len(json.dumps(row, ensure_ascii=True))
                        if rows and (len(rows) >= self.PAGE_ROWS or
                                     size + row_size > self.PAGE_BYTES):
                            self._put(token, self._page(
                                schema, rows, index, offset, False, None))
                            offset += len(rows)
                            rows, size = [], 0
                        rows.append(row)
                        size += row_size
                self._put(token, self._page(
                    schema, rows, index, offset, True, cursor.rowcount))
                if not cursor.nextset():
                    break
                index += 1
        except Exception as exc:
            token.error = self._error(exc)
            # Only a decoded server error establishes a command boundary.
            # A local refusal (notably LOCAL INFILE) may leave the server
            # awaiting data: sending PING then would corrupt/hang the exchange.
            errno = getattr(exc, 'errno', None)
            sqlstate = getattr(exc, 'sqlstate', None)
            server_error = (isinstance(errno, int) and errno >= 1000 and
                            not 2000 <= errno < 3000 and
                            isinstance(sqlstate, str) and len(sqlstate) == 5)
            if not server_error:
                token.cleanup_failed = True
            else:
                try:
                    token.connection.ping(reconnect=False)
                except Exception:
                    token.cleanup_failed = True
        finally:
            if cursor is not None and not token.cleanup_failed:
                try:
                    cursor.close()
                except Exception:
                    token.cleanup_failed = True
            with self.lock:
                if token.cleanup_failed:
                    self.client._uncertain_sessions.add(id(token.connection))
                token.finished.set()

    @staticmethod
    def _page(schema, rows, index, offset, end, rowcount):
        return {'schema': {'columns': schema}, 'payload': {
            'rows': rows, 'result_set_index': index, 'row_offset': offset,
            'result_set_end': end, 'rowcount': rowcount, 'has_page': True}}

    def _validate(self, token):
        if token not in self.tokens or token.closed:
            raise RelationalClientError('MySQL execution token is invalid')

    def describe(self, token):
        if not isinstance(token, Execution):
            raise RelationalClientError('MySQL execution token is invalid')
        with token.poll_lock:
            return self._describe_page(token)

    def _describe_page(self, token):
        self._validate(token)
        try:
            page = token.pages.get(timeout=0.05)
        except queue.Empty:
            page = {'schema': {'columns': []}, 'payload': {
                'rows': [], 'has_page': False}}
        complete = token.finished.is_set() and token.pages.empty()
        payload = page['payload']
        payload.update(cancelled=token.cancelled, streamed_by_provider=True)
        if complete:
            payload.update(error=token.error,
                           session_reuse_blocked=token.cleanup_failed)
            token.closed = True
            with self.lock:
                if token in self.tokens:
                    self.tokens.remove(token)
        return dict(page, complete=complete, result_kind='tabular',
                    stream_reference=token.reference)

    def cancel(self, token):
        with self.lock:
            self._validate(token)
            if token.finished.is_set():
                return False
            if token.identity is None:
                raise RelationalClientError(
                    'MySQL cancellation identity is not available yet')
            control = cursor = None
            try:
                def arguments(route):
                    options = dict(self.client.config.connect_arguments(route))
                    for name in ('pool_name', 'pool_size',
                                 'pool_reset_session',
                                 'failover', 'dns_srv'):
                        options.pop(name, None)
                    options.update(host=token.connection.server_host,
                                   port=token.connection.server_port)
                    options['unix_socket'] = token.connection.unix_socket
                    return options

                control = self.client._invoke_connector(
                    token.request, self.client.module.connect,
                    connect_arguments=arguments)
                cursor = control.cursor()
                cursor.execute('SELECT @@server_uuid')
                if str(cursor.fetchone()[0]) != token.identity[0]:
                    raise RelationalClientError(
                        'MySQL cancellation server identity changed')
                cursor.execute(f'KILL QUERY {token.identity[1]}')
                token.cancelled = True
                return True
            except Exception as exc:
                raise RelationalClientError(
                    'MySQL native cancellation failed (' +
                    type(exc).__name__ + ')') from None
            finally:
                self.client._safe_close(cursor)
                self.client._safe_close(control)

    def close(self):
        for token in self.tokens:
            if not token.finished.is_set():
                self.cancel(token)
                token.worker.join(timeout=5)
                if not token.finished.is_set():
                    raise RelationalClientError(
                        'MySQL execution still owns its connection')
        self.tokens.clear()

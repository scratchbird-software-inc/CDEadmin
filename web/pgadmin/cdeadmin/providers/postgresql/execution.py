"""Retained PostgreSQL execution, independent of the preserved Query Tool."""
import base64
import copy
import json
import queue
import threading
import time
from decimal import Decimal


class Execution:
    """One native protocol owner; bounded browser pages, no SQL replay."""

    def __init__(self, connection, source, parameters):
        self.connection = connection
        self.source = source
        self.parameters = parameters
        self.pages = queue.Queue(2)
        self.finished = threading.Event()
        self.discard = threading.Event()
        self.poll_lock = threading.Lock()
        self.error = None
        self.statement_metrics = None
        self.uncertain = False
        self.worker = threading.Thread(target=self._run, daemon=True,
                                       name='cdeadmin-postgresql-query')

    def start(self):
        self.worker.start()

    def _put(self, page):
        while not self.discard.is_set():
            try:
                self.pages.put(page, timeout=0.05)
                return
            except queue.Full:
                pass

    def _run(self):
        try:
            for page in result_pages(self.connection, self.source,
                                     self.parameters):
                self.statement_metrics = page.get(
                    "statement_metrics", self.statement_metrics)
                self._put(page)
        except Exception as exc:
            self.error = {'type': type(exc).__name__,
                          'sqlstate': getattr(exc, 'sqlstate', None)}
            diagnostic = getattr(exc, 'diag', None)
            if self.error['sqlstate'] and diagnostic is not None:
                for field in ('severity_nonlocalized', 'message_primary',
                              'message_detail', 'message_hint',
                              'statement_position'):
                    text = getattr(diagnostic, field, None)
                    if text:
                        self.error[field] = str(text)[:16384]
            self.uncertain = (not bool(self.error['sqlstate']) or
                              bool(getattr(self.connection, 'closed', False)))
        finally:
            self.source = self.parameters = None
            self.finished.set()

    def poll(self):
        with self.poll_lock:
            try:
                page = self.pages.get(timeout=0.05)
            except queue.Empty:
                page = {'rows': [], 'columns': [], 'has_page': False}
            complete = self.finished.is_set() and self.pages.empty()
            if complete:
                page.update(error=self.error,
                            session_reuse_blocked=self.uncertain)
            if self.statement_metrics is not None:
                page.setdefault('statement_metrics', self.statement_metrics)
            return dict(page, complete=complete)

    def cancel(self):
        if self.finished.is_set():
            return False
        # libpq's cancel packet is bound to this connection's backend key.
        # No second authenticated SQL connection or caller-supplied PID.
        self.connection.cancel()
        self.discard.set()
        return True


def parameters(value):
    """Bind ordinary JSON and explicit exact scalar envelopes via psycopg."""
    if value is None:
        return None
    if not isinstance(value, (list, tuple, dict)):
        raise ValueError('PostgreSQL parameters must be an object or array')

    def scalar(item):
        if not isinstance(item, dict):
            return item
        if set(item) == {'type', 'value'}:
            kind, data = item['type'], item['value']
            if not isinstance(data, str):
                raise ValueError('PostgreSQL exact parameter needs text')
            if kind == 'decimal':
                return Decimal(data)
            if kind == 'integer':
                return int(data)
            if kind == 'binary':
                return base64.b64decode(data, validate=True)
        raise ValueError('PostgreSQL parameter envelope is invalid')

    return ({key: scalar(item) for key, item in value.items()}
            if isinstance(value, dict) else [scalar(item) for item in value])


def result_pages(connection, source, bound):
    """Use text PGresults directly, avoiding narrowing Python type loaders."""
    import psycopg
    with psycopg.Cursor(connection) as cursor:
        started = time.perf_counter()
        cursor.execute(source, bound or None, binary=False)
        metrics = {
            'dispatch_ms': round((time.perf_counter() - started) * 1000, 3),
            'scope': 'client-execute-including-transfer-and-native-buffering',
            'prepare_ms': None, 'execute_ms': None, 'plan': None,
        }
        index = 0
        while True:
            result = cursor.pgresult
            columns = []
            if result is not None:
                for i in range(result.nfields):
                    columns.append({
                        'name': result.fname(i).decode(
                            connection.info.encoding),
                        'key': str(i), 'pos': i, 'type_code': result.ftype(i),
                        'format': 'postgresql-text',
                        'table_oid': result.ftable(i),
                        'table_column': result.ftablecol(i),
                    })
            rows, size, offset = [], 0, 0
            for rownum in range(result.ntuples if result else 0):
                row = []
                for col in range(result.nfields):
                    raw = result.get_value(rownum, col)
                    row.append(value(raw, connection.info.encoding))
                length = len(json.dumps(row, ensure_ascii=True))
                if rows and (len(rows) >= 256 or size + length > 1024 * 1024):
                    yield dict(_page(columns, rows, index, offset, False, None),
                               statement_metrics=metrics)
                    offset += len(rows)
                    rows, size = [], 0
                rows.append(row)
                size += length
            yield dict(_page(columns, rows, index, offset, True,
                             cursor.statusmessage), statement_metrics=metrics)
            if not cursor.nextset():
                break
            index += 1


def _page(columns, rows, index, offset, end, status):
    return {'columns': copy.deepcopy(columns), 'rows': rows,
            'result_set_index': index, 'row_offset': offset,
            'result_set_end': end, 'command_status': status, 'has_page': True}


def control(connection, statement):
    import psycopg
    with psycopg.Cursor(connection) as cursor:
        cursor.execute(statement)
        return True, cursor.statusmessage


def value(raw, encoding):
    if raw is None:
        return None
    try:
        return raw.decode(encoding)
    except UnicodeDecodeError:
        if encoding.lower() not in {'ascii', 'sql_ascii'}:
            raise
        return {'encoding': 'base64',
                'data': base64.b64encode(raw).decode('ascii'),
                'byte_length': len(raw), 'native_encoding': 'SQL_ASCII'}


def validate_plan(connection, source, bound):
    """Validate an explicit Explain request without executing its SQL."""
    import psycopg
    from pglast import ast, parse_sql
    from .language import analyze
    with psycopg.ClientCursor(connection) as cursor:
        adapted = cursor.mogrify(source, bound or None)
    checked = analyze(adapted, standard_strings=connection.info.parameter_status(
        'standard_conforming_strings'))
    if not checked.get('syntax_valid'):
        raise ValueError('Plan source could not be validated for this session')
    statements = parse_sql(adapted)
    if len(statements) != 1 or not isinstance(statements[0].stmt, ast.ExplainStmt):
        raise ValueError('Plan requests require exactly one EXPLAIN statement')

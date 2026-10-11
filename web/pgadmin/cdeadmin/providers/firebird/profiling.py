"""Explicit same-attachment profiling without finalizing user transactions."""
from contextlib import contextmanager
from .error_diagnostics import status_codes
from .grid_values import normalize_value
from ...sdk.relational import RelationalClientError


SECTIONS = {
    'statements': ('PLG$PROF_STATEMENTS', 'STATEMENT_ID, PARENT_STATEMENT_ID, STATEMENT_TYPE, PACKAGE_NAME, ROUTINE_NAME'),
    'requests': ('PLG$PROF_REQUESTS', 'STATEMENT_ID, REQUEST_ID, TOTAL_ELAPSED_TIME'),
    'psql': ('PLG$PROF_PSQL_STATS', 'STATEMENT_ID, REQUEST_ID, LINE_NUM, COLUMN_NUM, COUNTER, MIN_ELAPSED_TIME, MAX_ELAPSED_TIME, TOTAL_ELAPSED_TIME'),
    'record_sources': ('PLG$PROF_RECORD_SOURCE_STATS', 'STATEMENT_ID, REQUEST_ID, CURSOR_ID, RECORD_SOURCE_ID, OPEN_COUNTER, OPEN_MIN_ELAPSED_TIME, OPEN_MAX_ELAPSED_TIME, OPEN_TOTAL_ELAPSED_TIME, FETCH_COUNTER, FETCH_MIN_ELAPSED_TIME, FETCH_MAX_ELAPSED_TIME, FETCH_TOTAL_ELAPSED_TIME'),
    'access_paths': ('PLG$PROF_RECORD_SOURCES', 'STATEMENT_ID, CURSOR_ID, RECORD_SOURCE_ID, PARENT_RECORD_SOURCE_ID, LEVEL, ACCESS_PATH'),
}
LIMIT = 200


@contextmanager
def transaction(connection, *, write=False):
    from firebird.driver import tpb, Isolation, TraAccessMode
    manager = connection.transaction_manager(tpb(
        isolation=Isolation.READ_COMMITTED_RECORD_VERSION,
        access_mode=TraAccessMode.WRITE if write else TraAccessMode.READ,
        lock_timeout=5))
    try:
        manager.begin()
        with manager.cursor() as cursor:
            yield cursor
        manager.commit()
    finally:
        try:
            manager.close()
        except BaseException as error:
            failure = RelationalClientError('Diagnostic transaction cleanup did not complete')
            failure.diagnostic_cleanup_failed = True
            raise failure from error


class ProfileRun:
    def __init__(self, connection):
        self.connection = connection
        self.started = False
        self.uncertain = False
        self.receipt = {'state': 'not-started', 'profile_id': None,
                        'scope': 'same attachment; fetched execution only',
                        'elapsed_unit': 'nanoseconds', 'section_limit': LIMIT,
                        'sections': {}, 'errors': []}

    def _error(self, stage, error):
        self.receipt['errors'].append({'stage': stage, 'error_type': type(error).__name__,
                                       'native_status_codes': list(status_codes(error))})

    def start(self):
        with transaction(self.connection) as cursor:
            cursor.execute("SELECT 1 FROM RDB$PACKAGES WHERE RDB$PACKAGE_NAME = 'RDB$PROFILER'")
            if cursor.fetchone() is None:
                raise RelationalClientError('Native Firebird profiler package is unavailable')
        self.uncertain = True
        self.receipt['state'] = 'start-unknown'
        try:
            with transaction(self.connection, write=True) as cursor:
                cursor.execute("SELECT RDB$PROFILER.START_SESSION(?, NULL, NULL, 'Default_Profiler') FROM RDB$DATABASE",
                               ('ScratchRobin explicit statement profile',))
                row = cursor.fetchone()
                if not row or type(row[0]) is not int:
                    raise RelationalClientError('Native profiler did not return a profile identity')
                self.receipt['profile_id'] = str(row[0])
            self.started = True
            self.uncertain = False
            self.receipt['state'] = 'active'
        except BaseException as error:
            self._error('start', error)
            raise

    def finish(self):
        if not self.started:
            return
        self.uncertain = True
        self.receipt['state'] = 'finish-unknown'
        try:
            with transaction(self.connection, write=True) as cursor:
                cursor.execute('EXECUTE PROCEDURE RDB$PROFILER.FINISH_SESSION(TRUE)')
            self.uncertain = False
            self.receipt['state'] = 'flushed'
        except Exception as error:
            self._error('finish', error)
            return
        try:
            with transaction(self.connection) as cursor:
                for key, (table, fields) in SECTIONS.items():
                    cursor.execute(f'SELECT FIRST {LIMIT + 1} {fields} FROM {table} WHERE PROFILE_ID = ? ORDER BY 1, 2',
                                   (int(self.receipt['profile_id']),))
                    rows = cursor.fetchall()
                    names = [item[0] for item in cursor.description]
                    self.receipt['sections'][key] = {
                        'rows': [{name: normalize_value(value) for name, value in zip(names, row)} for row in rows[:LIMIT]],
                        'truncated': len(rows) > LIMIT}
            self.receipt['state'] = 'complete'
        except Exception as error:
            self.receipt['state'] = 'read-incomplete'
            self.uncertain = bool(getattr(error, 'diagnostic_cleanup_failed', False))
            self._error('read', error)

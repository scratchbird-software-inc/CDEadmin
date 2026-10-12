"""Fresh attachment measurements, deliberately distinct from query finality."""
import time
from .profiling import transaction
from .error_diagnostics import status_codes
from .query_values import normalize_value

COUNTERS = ('page_reads', 'page_writes', 'page_fetches', 'page_marks',
            'record_seq_reads', 'record_idx_reads', 'record_inserts',
            'record_updates', 'record_deletes', 'record_backouts',
            'record_purges', 'record_expunges')
SOURCE = ('SELECT A.MON$ATTACHMENT_ID, ' + ', '.join(
    ('I.' if name.startswith('page_') else 'R.') + 'MON$' + name.upper()
    for name in COUNTERS) +
    ' FROM MON$ATTACHMENTS A JOIN MON$IO_STATS I ON I.MON$STAT_ID = A.MON$STAT_ID'
    ' AND I.MON$STAT_GROUP = 1 JOIN MON$RECORD_STATS R ON R.MON$STAT_ID = A.MON$STAT_ID'
    ' AND R.MON$STAT_GROUP = 1 WHERE A.MON$ATTACHMENT_ID = CURRENT_CONNECTION')


class QueryStatistics:
    def __init__(self, connection):
        self.connection = connection
        self.cleanup_failed = False
        self.started = None
        self.receipt = {'scope': 'current attachment sampling window, including monitoring overhead',
                        'timing_scope': 'host native dispatch, execution, fetch and cursor release',
                        'elapsed_unit': 'nanoseconds', 'elapsed': None,
                        'before': None, 'after': None, 'deltas': {}, 'errors': []}

    def capture(self, stage):
        try:
            with transaction(self.connection) as cursor:
                cursor.execute(SOURCE)
                row = cursor.fetchone()
                if row is None or len(row) != len(COUNTERS) + 1 or any(type(v) is not int for v in row):
                    raise ValueError('Native attachment statistics are incomplete')
                self.receipt[stage] = {'attachment_id': str(row[0]),
                                       'counters': dict(zip(COUNTERS, row[1:]))}
        except Exception as error:
            self.cleanup_failed |= bool(getattr(error, 'diagnostic_cleanup_failed', False))
            self.receipt['errors'].append({'stage': stage, 'error_type': type(error).__name__,
                                           'native_status_codes': list(status_codes(error))})

    def start(self):
        self.capture('before')
        self.started = time.perf_counter_ns()

    def finish(self):
        self.receipt['elapsed'] = time.perf_counter_ns() - self.started
        self.capture('after')
        before, after = self.receipt['before'], self.receipt['after']
        if before and after and before['attachment_id'] == after['attachment_id']:
            for name in COUNTERS:
                delta = after['counters'][name] - before['counters'][name]
                self.receipt['deltas'][name] = delta if delta >= 0 else None
        self.receipt['complete'] = bool(before and after and before['attachment_id'] == after['attachment_id'] and
                                        not self.receipt['errors'] and
                                        all(value is not None for value in self.receipt['deltas'].values()))
        for sample in (before, after):
            if sample:
                sample['counters'] = {name: normalize_value(value) for name, value in sample['counters'].items()}
        self.receipt['deltas'] = {name: normalize_value(value) for name, value in self.receipt['deltas'].items()}
        self.receipt['elapsed'] = normalize_value(self.receipt['elapsed'])

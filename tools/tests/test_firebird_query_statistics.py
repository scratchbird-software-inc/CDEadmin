from contextlib import contextmanager
from unittest.mock import Mock, patch
import config  # Initialize the application's configuration before ORM imports.

from pgadmin.cdeadmin.providers.firebird.query_statistics import QueryStatistics, COUNTERS


def test_samples_use_fresh_transactions_and_identify_counter_resets():
    cursor = Mock()
    cursor.fetchone.side_effect = [(123, *([10] * len(COUNTERS))), (123, 9, *([12] * (len(COUNTERS)-1)))]
    transactions = []
    @contextmanager
    def separate(_connection):
        transactions.append(object())
        yield cursor
    with patch('pgadmin.cdeadmin.providers.firebird.query_statistics.transaction', separate):
        sample = QueryStatistics(object())
        sample.start()
        sample.finish()
    assert len(transactions) == 2
    assert sample.receipt['deltas']['page_reads'] is None
    assert sample.receipt['deltas']['record_inserts'] == 2
    assert not sample.receipt['complete']
    assert sample.receipt['reset_counters'] == ['page_reads']
    assert sample.receipt['unavailable_reasons'] == ['counter-reset']
    assert sample.receipt['elapsed'] >= 0


def test_unavailable_statistics_are_not_zero_measurements():
    with patch('pgadmin.cdeadmin.providers.firebird.query_statistics.transaction', side_effect=RuntimeError('unavailable')):
        sample = QueryStatistics(object())
        sample.start()
        sample.finish()
    assert sample.receipt['before'] is None and sample.receipt['after'] is None
    assert sample.receipt['deltas'] == {}
    assert not sample.receipt['complete']
    assert not sample.cleanup_failed
    assert sample.receipt['unavailable_reasons'] == ['before-unavailable', 'after-unavailable']


def test_attachment_change_is_not_a_valid_delta_and_large_counts_remain_exact():
    cursor = Mock()
    counter = 2 ** 60 + 1
    cursor.fetchone.side_effect = [(123, *([counter] * len(COUNTERS))), (124, *([counter+1] * len(COUNTERS)))]
    @contextmanager
    def separate(_connection):
        yield cursor
    with patch('pgadmin.cdeadmin.providers.firebird.query_statistics.transaction', separate):
        sample = QueryStatistics(object())
        sample.start()
        sample.finish()
    assert not sample.receipt['complete']
    assert sample.receipt['deltas'] == {}
    assert sample.receipt['unavailable_reasons'] == ['attachment-changed']
    assert sample.receipt['before']['counters']['page_reads'] == str(counter)

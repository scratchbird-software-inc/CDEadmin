"""SQLite collector samples its own file connection and refreshes transactions."""

import sqlite3

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.monitoring import SQLiteMonitor
from pgadmin.cdeadmin.sdk import RelationalClientError


def test_file_monitor_uses_independent_completed_read_transactions(tmp_path):
    path = tmp_path / 'monitored.sqlite'
    owner = sqlite3.connect(path)
    owner.execute('CREATE TABLE committed(id INTEGER PRIMARY KEY)')
    owner.commit()
    owner.execute('BEGIN')
    owner.execute('CREATE TABLE uncommitted(secret TEXT)')
    monitor = SQLiteMonitor({
        'database': str(path), 'filesystem_root': str(tmp_path)},
        target_id='owned-file')
    try:
        first = monitor.sample()
        second = monitor.sample()
        assert first['status'] == second['status'] == 'available'
        assert first['identity']['target_id'] == 'owned-file'
        assert first['source_epoch'] == second['source_epoch']
        assert first['sample_id'] != second['sample_id']
        assert first['transaction_refresh']['status'] == 'completed'
        assert monitor._connection.in_transaction is False
        assert first['groups']['storage']['rows'][0]['page_count'] >= 1
        assert owner.in_transaction
    finally:
        monitor.close()
        owner.rollback()
        owner.close()


def test_independent_memory_monitor_is_refused():
    with pytest.raises(RelationalClientError, match='different SQLite database'):
        SQLiteMonitor({'database': ':memory:', 'allow_memory': True},
                      target_id='memory')

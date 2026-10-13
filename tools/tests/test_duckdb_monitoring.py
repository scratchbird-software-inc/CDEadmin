"""DuckDB monitoring uses an independent short native transaction."""

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.monitoring import DuckDBMonitor
from pgadmin.cdeadmin.sdk import RelationalClientError


def test_native_file_sample_is_independent_and_heartbeat_evidence_is_completed(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    path = tmp_path / 'observed.duckdb'
    owner = duckdb.connect(str(path))
    owner.execute('CREATE TABLE facts(id INTEGER)')
    owner.execute('BEGIN TRANSACTION')
    owner.execute('INSERT INTO facts VALUES (7)')
    owner.execute('CREATE TEMP TABLE hidden(id INTEGER)')
    monitor = DuckDBMonitor({'database': str(path), 'filesystem_root': str(tmp_path)},
        target_id='registered-file')
    try:
        sample = monitor.sample()
        assert sample['status'] == 'available' and sample['scope'] == 'database'
        assert sample['identity']['target_id'] == 'registered-file'
        assert sample['identity']['database_name'] == path.stem
        assert sample['groups']['storage']['rows'][0]['database_name'] == path.stem
        assert sample['groups']['extensions']['rows'][0]['available'] >= 1
        assert sample['transaction_refresh']['status'] == 'completed'
        assert owner.execute('SELECT COUNT(*) FROM facts').fetchone() == (1,)
        assert owner.execute('SELECT COUNT(*) FROM hidden').fetchone() == (0,)
        owner.execute('ROLLBACK')
        assert monitor.sample()['source_epoch'] == sample['source_epoch']
    finally:
        monitor.close(); owner.close()


def test_missing_or_memory_database_does_not_open_monitor(tmp_path):
    with pytest.raises(RelationalClientError):
        DuckDBMonitor({'database': ':memory:', 'allow_memory': True}, target_id='memory')
    missing = tmp_path / 'missing.duckdb'
    with pytest.raises(RelationalClientError):
        DuckDBMonitor({'database': str(missing), 'filesystem_root': str(tmp_path)}, target_id='missing')
    assert not missing.exists()

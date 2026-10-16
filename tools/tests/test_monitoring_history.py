"""Archive contract tests. SQLite is a SQL test double, never a product store."""
import json
import sqlite3
import threading
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from tools.cdeadmin_firebird_admin_mapping_gate import _create_client  # noqa: F401
from pgadmin.cdeadmin.workspace.monitoring import MonitoringPolicy, MonitoringRuntime
from pgadmin.cdeadmin.workspace.monitoring_history import MonitoringHistory, HistoryUnavailable

NOW = 1791993600

def iso(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def policy(owner=1, **kwargs):
    return MonitoringPolicy(owner, 'endpoint', 'target', **kwargs)


def sample(identity='one', epoch='source', age=0):
    return {'sample_id': identity, 'source_epoch': epoch, 'ended_at': iso(NOW-age),
            'status': 'available', 'coverage': {'scope': 'database'},
            'groups': {'memory': {'values': {'used': '9007199254740993', 'password': 'never'}}},
            'sql_text': 'never', 'credentials': {'password': 'never'}}


@pytest.fixture
def archive(tmp_path):
    path = str(tmp_path/'unit-only.sqlite')
    store = MonitoringHistory(lambda: sqlite3.connect(path), namespace='installation', clock=lambda: NOW)
    store.initialize()
    return store


def query(store, owner=1, **kwargs):
    return store.query(policy(owner), 'firebird', start=iso(NOW-86400), end=iso(NOW+1), **kwargs)


def test_restart_exact_values_owner_engine_target_isolation_and_redaction(archive):
    archive.write(policy(), 'firebird', 'policy1', 'route1', sample())
    restarted = MonitoringHistory(archive.connect, namespace='installation', clock=lambda: NOW)
    result = query(restarted)
    item = result['samples'][0]
    assert item['groups']['memory']['values'] == {'used': '9007199254740993'}
    assert 'never' not in json.dumps(result)
    assert item['history_provenance']['observed_us'] == NOW*1000000
    assert item['history_provenance']['policy_revision'] == 'policy1'
    assert query(restarted, 2)['samples'] == []
    assert restarted.query(policy(), 'mysql', start=iso(NOW-10), end=iso(NOW+1))['samples'] == []


def test_idempotency_collision_pagination_and_rollup_epochs(archive):
    for value in (sample('a', age=2), sample('b', age=1), sample('c', epoch='reset')):
        archive.write(policy(), 'firebird', 'p', 'r', value)
    archive.write(policy(), 'firebird', 'p', 'r', sample('a', age=2))
    with pytest.raises(ValueError):
        archive.write(policy(), 'firebird', 'p', 'r', sample('a', age=1))
    first = query(archive, limit=2)
    assert first['next']
    second = query(archive, limit=2, after=first['next'])
    assert len(second['samples']) == 1 and second['next'] is None
    rollups = query(archive, tier='rollup')['samples']
    assert len(rollups) == 2
    assert sum(item['history_provenance']['aggregation']['count'] for item in rollups) == 3
    assert all(item['rates']['status'] == 'gap' for item in rollups)
    measure = rollups[0]['history_provenance']['aggregation']['measures']['groups/memory/values/used']
    assert measure['min'] == measure['max'] == '9007199254740993'


def test_retention_hides_expired_samples_even_before_maintenance(archive):
    archive.write(policy(), 'firebird', 'p', 'r', sample('old', age=8*86400))
    assert archive.query(policy(), 'firebird', start=iso(NOW-9*86400), end=iso(NOW+1))['samples'] == []
    assert archive.query(policy(), 'firebird', tier='rollup', start=iso(NOW-9*86400), end=iso(NOW+1))['samples']
    archive.clock = lambda: NOW+91*86400
    archive.maintain()
    with archive.connect() as connection:
        assert connection.execute('SELECT COUNT(*) FROM cde_monitor_history').fetchone()[0] == 0


def test_failed_commit_never_replayed(archive):
    real = archive.connect
    opened = []
    class LostCommit:
        def __init__(self):
            self.connection = real()
        def cursor(self):
            return self.connection.cursor()
        def commit(self):
            self.connection.commit()
            raise OSError('sensitive native diagnostics')
        def rollback(self):
            self.connection.rollback()
        def close(self):
            self.connection.close()
    def connect():
        opened.append(1)
        return LostCommit()
    archive.connect = connect
    with pytest.raises(HistoryUnavailable) as error:
        archive.write(policy(), 'firebird', 'p', 'r', sample())
    assert error.value.phase == 'commit' and len(opened) == 1
    archive.connect = real
    assert len(query(archive)['samples']) == 1


def test_history_failure_keeps_live_collector_running():
    written = threading.Event()
    def fail(*args):
        written.set()
        raise HistoryUnavailable('commit')
    source = Mock(sample=Mock(return_value=sample()))
    runtime = MonitoringRuntime()
    config = policy(history_enabled=True)
    try:
        runtime.enable(config, lambda _: source, lambda *_: True, history_writer=fail)
        assert written.wait(2)
        # Synchronize with the writer's status publication.
        job = runtime._jobs[config.key]
        with job.lock:
            pass
        result = runtime.snapshot(config, lambda *_: True)
        assert result['samples'] and result['state'] == 'collecting'
        assert result['history_storage']['status'] == 'unconfirmed'
    finally:
        runtime.close()


def test_unconfigured_history_fails_before_opening_source():
    factory = Mock()
    with pytest.raises(ValueError):
        MonitoringRuntime().enable(policy(history_enabled=True), factory, lambda *_: True)
    factory.assert_not_called()


def test_page_record_cap_and_metadata_version_boundaries(archive):
    for index in range(33):
        value = sample(str(index))
        value['groups']['configuration_details'] = {'status': 'available', 'values': {'cache': str(index % 2)}}
        archive.write(policy(), 'firebird', 'p', 'r', value)
    first = query(archive, limit=720)
    assert len(first['samples']) == 32 and first['next']
    assert len(query(archive, after=first['next'], limit=720)['samples']) == 1
    rollups = query(archive, tier='rollup')['samples']
    assert len(rollups) == 2
    assert len({item['history_provenance']['metadata_revision'] for item in rollups}) == 2


def test_mysql_native_identity_exact_row_rollups_and_metadata_boundaries(archive):
    for index in range(3):
        value = {**sample(str(index)), 'transaction_completed': True,
                 'identity': {'server_uuid': 'native-instance', 'database_name': 'db', 'version': '9.7.0',
                              'account': 'excluded-account', 'collector_id': 'excluded-connection'},
                 'groups': {'status': {'rows': [{'variable_name': 'Bytes_sent', 'variable_value': '9007199254740993'}]},
                            'settings': {'rows': [{'read_only': str(index % 2)}], 'observed_at': iso(NOW-index)}}}
        archive.write(policy(), 'mysql', 'p', 'r', value)
    result = archive.query(policy(), 'mysql', start=iso(NOW-10), end=iso(NOW+1))
    assert len(result['samples']) == 3
    assert result['samples'][0]['identity']['server_uuid'] == 'native-instance'
    assert result['samples'][0]['transaction_completed'] is True
    assert 'excluded-' not in json.dumps(result)
    rollup = archive.query(policy(), 'mysql', start=iso(NOW-10), end=iso(NOW+1), tier='rollup')
    assert len(rollup['samples']) == 2
    measure = rollup['samples'][0]['history_provenance']['aggregation']['measures']['groups/status/rows/"Bytes_sent"/variable_value']
    assert measure['min'] == measure['max'] == '9007199254740993'
    assert not query(archive)['samples']


def test_mariadb_native_identity_exact_row_rollups_and_metadata_boundaries(archive):
    for index in range(3):
        value = {**sample(str(index)), 'transaction_completed': True,
                 'identity': {'server_uid': 'native-instance', 'database_name': 'db', 'version': '12.2.2',
                              'account': 'excluded-account', 'collector_id': 'excluded-connection'},
                 'groups': {'status': {'rows': [{'variable_name': 'Bytes_sent', 'variable_value': '9007199254740993'}]},
                            'settings': {'rows': [{'read_only': str(index % 2)}], 'observed_at': iso(NOW-index)}}}
        archive.write(policy(), 'mariadb', 'p', 'r', value)
    result = archive.query(policy(), 'mariadb', start=iso(NOW-10), end=iso(NOW+1))
    assert len(result['samples']) == 3
    assert result['samples'][0]['identity']['server_uid'] == 'native-instance'
    assert result['samples'][0]['transaction_completed'] is True
    assert 'excluded-' not in json.dumps(result)
    rollup = archive.query(policy(), 'mariadb', start=iso(NOW-10), end=iso(NOW+1), tier='rollup')
    assert len(rollup['samples']) == 2
    measure = rollup['samples'][0]['history_provenance']['aggregation']['measures']['groups/status/rows/"Bytes_sent"/variable_value']
    assert measure['min'] == measure['max'] == '9007199254740993'
    assert not query(archive)['samples']

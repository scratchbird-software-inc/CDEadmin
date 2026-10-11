"""Exact counters, reset epochs and retained collector ownership."""
import importlib.util
from pathlib import Path
from decimal import Decimal
from unittest.mock import Mock

import pytest

path = Path(__file__).resolve().parents[2] / 'web/pgadmin/cdeadmin/providers/postgresql/monitoring.py'
spec = importlib.util.spec_from_file_location('pg_monitor', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def source():
    return module.PostgreSQLMonitor(Mock(), {'database': 'qa'})


def sample(value=0, reset='one'):
    return {'groups': {'database': {'rows': [
        {'datid': 7, 'stats_reset': reset, **dict.fromkeys(module.COUNTERS, value)}]}}}


def test_rates_require_same_epoch_and_non_decreasing_exact_counters():
    monitor = source()
    a = sample(2**60);monitor._rates(a, 10**9, 'start')
    assert a['groups']['database']['rows'][0]['rates_per_second'] is None
    b = sample(2**60+3);monitor._rates(b, 3*10**9, 'start')
    row = b['groups']['database']['rows'][0]
    assert row['rates_per_second']['xact_commit'] == Decimal('1.5')
    assert module.wire(row)['xact_commit'] == str(2**60+3)
    for value, reset, started in [(0,'one','start'), (1,'two','start'), (2,'two','restart')]:
        c=sample(value,reset);monitor._rates(c, 4*10**9, started)
        assert c['groups']['database']['rows'][0]['rates_per_second'] is None


def test_missing_group_breaks_counter_baseline():
    monitor=source();monitor._rates(sample(1), 10**9, 'start')
    monitor._rates({'groups': {}}, 2*10**9, 'start')
    last=sample(3);monitor._rates(last, 3*10**9, 'start')
    assert last['groups']['database']['rows'][0]['rates_per_second'] is None


def test_failed_close_remains_owned_until_retry():
    monitor=source();connection=Mock()
    connection.close.side_effect=[OSError('private'), None]
    monitor._connection=connection
    with pytest.raises(OSError):monitor.close()
    assert monitor._connection is connection and monitor._needs_release
    assert not monitor._closed
    monitor.close()
    assert monitor._connection is None and monitor._closed
    with pytest.raises(module.PostgreSQLMonitoringError):monitor.sample()


def test_open_failure_is_redacted_and_does_not_publish_heartbeat():
    monitor=source();monitor._connect=Mock(side_effect=OSError('secret password'))
    monitor._open=Mock(side_effect=OSError('secret password'))
    result=monitor.sample()
    assert result['status']=='unavailable'
    assert result['transaction_completed'] is False
    assert result['last_success_at'] is None
    assert 'secret' not in str(result)


@pytest.mark.parametrize('route,scope', [({},'database'), ({'database':'qa','password':'x'},'database'), ({'database':'qa'},'wrong')])
def test_no_implicit_database_or_plaintext_secret(route,scope):
    with pytest.raises(ValueError):module.PostgreSQLMonitor(Mock(),route,scope=scope)


@pytest.mark.parametrize('oid', [True, '42', 0, -1, 4294967296])
def test_database_identity_is_canonical_native_oid(oid):
    with pytest.raises(ValueError):
        module.PostgreSQLMonitor(Mock(), {'database': 'qa', 'database_oid': oid})


def test_interruption_clears_rate_baseline_and_releases_connection():
    monitor = source()
    connection = Mock()
    monitor._connection = connection
    monitor._rates(sample(3), 10**9, 'start')
    connection.transaction.side_effect = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        monitor.sample()
    connection.close.assert_called_once()
    assert monitor._previous == {} and monitor._connection is None

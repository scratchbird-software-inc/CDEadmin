"""Workload privacy, native normalization and incomplete coverage contracts."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from mysql.connector.errors import DatabaseError
from pgadmin.cdeadmin.providers.mysql_family import mysql_workload as native
from pgadmin.cdeadmin.providers.mysql_family.mysql_monitoring import MySQLMonitor
from pgadmin.cdeadmin.workspace import mysql_workload_service as service


def test_rankings_use_native_order_and_preserve_scope_and_no_private_samples():
    observer = MySQLMonitor(None, {'database': 'private`schema'})
    observer._read = Mock(return_value=[])
    for rank, field in native.RANKS.items():
        result = native.observe(observer, 'private`schema', rank)
        source, params = observer._read.call_args_list[-7].args
        assert 'ORDER BY ' + field + ' DESC' in source
        assert params == ('private`schema',)
        assert 'QUERY_SAMPLE' not in source
        assert result['groups']['workload_digests']['scope'] == 'database'
        assert result['groups']['workload_waits']['scope'] == 'server'
        assert result['reset']['undetected_reset_possible'] is True
    assert all('LIMIT 101' in call.args[0] or call.args[0].startswith('SELECT @@')
               for call in observer._read.call_args_list)


def test_denied_instrumentation_does_not_become_empty_zero_or_leak_sql():
    observer = MySQLMonitor(None, {}, scope='server')
    observer._read = Mock(side_effect=DatabaseError('secret source SQL', errno=1142, sqlstate='42000'))
    result = native.observe(observer)
    assert all(group['status'] == 'unavailable' and group['error_code'] == 1142 for group in result['groups'].values())
    assert 'secret source' not in str(result)


def test_epoch_detects_native_first_seen_change_and_exact_large_counter_decrease():
    row = {'schema_name': 'db', 'digest': 'a'*64, 'first_seen': {'temporal': '2026-01-01'},
        'count_star': '9007199254740994', 'sum_timer_wait': '9999999999999999999',
        'sum_rows_examined': '0', 'sum_created_tmp_tables': '0', 'sum_created_tmp_disk_tables': '0'}
    before = {'source_epoch': 'a', 'groups': {'workload_digests': {'status': 'available', 'rows': [row]}}}
    after = deepcopy(before)
    assert native.reset_evidence(before, after)['state'] == 'no-reset-observed'
    after['groups']['workload_digests']['rows'][0]['count_star'] = '9007199254740993'
    assert native.reset_evidence(before, after)['state'] == 'reset-observed'
    after = deepcopy(before)
    after['groups']['workload_digests']['rows'][0]['first_seen'] = {'temporal': '2026-02-01'}
    assert native.reset_evidence(before, after)['state'] == 'reset-observed'
    after['source_epoch'] = 'b'
    assert native.reset_evidence(before, after)['state'] == 'baseline-unavailable'


LOG = ('# Time: 2026-10-22T12:00:00.000000Z\n# User@Host: root[root] @ localhost []  Id: 1\n'
       '# Query_time: 0.123456  Lock_time: 0.000001 Rows_sent: 1 Rows_examined: 2 Created_tmp_tables: 0\n'
       'use demo;\nSET insert_id=9,timestamp=1792670400;\nSELECT \'private literal\';\n')


def test_native_slow_log_scope_window_and_multiline_use_context():
    entries = native.parse_slow_file(LOG + LOG.replace('use demo;\n', '').replace('0.123456', '0.000001'),
        'demo', datetime(2026, 10, 22, 11), datetime(2026, 10, 22, 13))
    assert len(entries) == 2 and entries[0]['query_time'] == Decimal('0.123456')
    assert not native.parse_slow_file(LOG, 'other', datetime(2026, 10, 22, 11), datetime(2026, 10, 22, 13))
    observer = SimpleNamespace(_read=Mock(return_value=[{'digest': 'a'*64, 'digest_text': 'SELECT ?'}]))
    result = native.aggregate_log(observer, entries, source='uploaded-native-slow-log')
    assert result['rows'][0]['total_seconds'] == '0.123457'
    assert result['rows'][0]['mean_seconds'] == '0.0617285'
    assert result['rows'][0]['count'] == '2'
    assert 'private literal' not in str(result)
    for call in observer._read.call_args_list:
        assert call.args[0] == 'SELECT STATEMENT_DIGEST(%s) AS digest,STATEMENT_DIGEST_TEXT(%s) AS digest_text'
        assert call.args[1] == ("SELECT 'private literal';",)*2


@pytest.mark.parametrize('text', [LOG[:-2], LOG.replace('# User@Host:', '# Missing:'),
    LOG.replace('SET insert_id=9,timestamp=', 'SET other='), LOG.replace('SELECT', '# Time: ambiguous\nSELECT'),
    'x'*(1024*1024+1), LOG*501])
def test_partial_ambiguous_and_excessive_slow_log_input_is_refused(text):
    with pytest.raises(native.WorkloadError):
        native.parse_slow_file(text, 'demo', datetime(2026, 10, 22, 11), datetime(2026, 10, 22, 13))


@pytest.mark.parametrize('confirmed', [None, False, 'true', 1])
def test_private_actions_require_explicit_boolean_consent_before_connection(monkeypatch, confirmed):
    engine = SimpleNamespace(endpoint_service=SimpleNamespace(
        workspace=Mock(return_value=('context', {'route': {}}, None)),
        provider_registry=SimpleNamespace(admitted_permissions=Mock(return_value={'administer'}),
            resolve=Mock(return_value=SimpleNamespace(permissions=None)))))
    server = SimpleNamespace(endpoint_profile=SimpleNamespace(profile_id='mysql-native', provider_id='org.cdeadmin.mysql'))
    observer = Mock()
    monkeypatch.setattr(service, 'MySQLMonitor', observer)
    with pytest.raises(native.WorkloadError, match='Explicit private'):
        service.action(engine, server, 'sample', {'schema_name': 'db', 'digest': 'a'*64, 'confirmed': confirmed})
    observer.assert_not_called()


def test_private_sample_has_fingerprint_and_never_uses_source_as_sql():
    observer = SimpleNamespace(_read=Mock(return_value=[{'query_sample_text': "SELECT 'secret'", 'first_seen': None}]))
    result = native.private_sample(observer, {'schema_name': "db'", 'digest': 'a'*64})
    assert len(result['sample_sha256']) == 64 and result['query_sample_text'] == "SELECT 'secret'"
    source, params = observer._read.call_args.args
    assert "db'" not in source and params == ("db'", 'a'*64)


def test_native_non_sql_log_commands_are_reported_without_raw_source_or_fake_digest():
    reader = SimpleNamespace(_read=Mock(side_effect=DatabaseError('private source', errno=3676, sqlstate='HY000')))
    result = native.aggregate_log(reader, [{'sql': '# administrator command: Init DB;', 'schema_name': 'db'}], source='mysql.slow_log')
    assert result['entries'] == 1 and result['normalized_entries'] == 0 and not result['rows']
    assert result['unparsed'] == [{'input_index': 0, 'error_code': 3676, 'sqlstate': 'HY000'}]
    assert 'private source' not in str(result)


def test_native_privilege_failure_is_source_free_at_service_boundary():
    from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceError, ProviderWorkspaceService
    # Use the actual public wrapper without constructing unrelated workspaces.
    engine = SimpleNamespace(endpoint_service=SimpleNamespace(workspace=Mock(side_effect=
        DatabaseError('private SQL and password', errno=1142, sqlstate='42000'))))
    server = SimpleNamespace(endpoint_profile=SimpleNamespace(profile_id='mysql-native', provider_id='org.cdeadmin.mysql'))
    with pytest.raises(ProviderWorkspaceError) as error:
        ProviderWorkspaceService.mysql_workload(engine, server, 'snapshot', {})
    assert '1142' in str(error.value) and 'private' not in str(error.value)

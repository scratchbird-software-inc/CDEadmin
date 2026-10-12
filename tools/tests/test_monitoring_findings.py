"""Policy findings require actual scoped observations and continuous intervals."""
from tools.cdeadmin_firebird_admin_mapping_gate import _create_client  # noqa: F401
from pgadmin.cdeadmin.workspace.monitoring import MonitoringPolicy
from pgadmin.cdeadmin.workspace.monitoring_findings import findings


def observation(age='100', backup='1', epoch='one', elapsed=100):
    return {'status': 'available', 'source_epoch': epoch, 'sample_id': 'sample',
            'runtime_elapsed_seconds': elapsed, 'groups': {
                'transactions': {'status': 'available', 'values': {'oldest_age_seconds': age}},
                'database': {'status': 'available', 'values': {'backup_state': backup, 'crypt_state': '0'}}}}


def test_thresholds_disabled_and_missing_values_do_not_create_health_findings():
    policy = MonitoringPolicy(1, 'endpoint', 'target')
    assert findings(policy, observation(), []) == []
    policy = MonitoringPolicy(1, 'endpoint', 'target', max_transaction_age_seconds=20)
    assert findings(policy, observation(age=None), []) == []
    assert findings(policy, {'status': 'unavailable'}, []) == []
    assert findings(policy, observation(), [])[0]['code'] == 'old-transaction'


def test_backup_duration_cannot_bridge_failure_or_connection_epoch():
    policy = MonitoringPolicy(1, 'endpoint', 'target', max_backup_state_seconds=10)
    assert findings(policy, observation(elapsed=20), [observation(elapsed=0)])[0]['code'] == 'prolonged-backup-state'
    assert findings(policy, observation(elapsed=20, epoch='two'), [observation(elapsed=0)]) == []
    assert findings(policy, observation(elapsed=20), [observation(elapsed=0), {'status': 'unavailable'}]) == []


def test_local_and_unknown_security_flags_are_not_unencrypted_wire():
    policy = MonitoringPolicy(1, 'endpoint', 'target', require_wire_encryption=True)
    sample = observation()
    sample['groups']['wire_counts'] = {'status': 'available', 'values': {'rows': [
        {'transport': 'local', 'encrypted': False, 'count': '2'},
        {'transport': 'wire', 'encrypted': None, 'count': '1'}]}}
    assert findings(policy, sample, []) == []
    sample['groups']['wire_counts']['values']['rows'].append(
        {'transport': 'wire', 'encrypted': False, 'count': '3'})
    assert findings(policy, sample, [])[0]['value'] == '3'

"""Fleet evidence must not invent reachability, inventory or unique instances."""
from tools.cdeadmin_firebird_admin_mapping_gate import _create_client  # noqa: F401
from pgadmin.cdeadmin.workspace.monitoring_fleet import fleet_snapshot, observation


def snapshot(**overrides):
    return {'state': 'collecting', 'sample_age_seconds': 1,
            'stale_after_seconds': 45, 'samples': [{
                'status': 'partial', 'service_probe': {'status': 'completed'},
                'groups': {'version': {'status': 'available', 'values': '5.0'},
                           'architecture': {'status': 'unavailable'},
                           'attached_databases': {'status': 'available',
                                                  'values': ['demo.fdb']}}}],
            **overrides}


def test_current_completed_partial_probe_and_missing_groups():
    row = observation(snapshot(), 'server')
    assert row['status'] == 'reachable'
    assert row['version'] == '5.0'
    assert row['architecture'] is None
    assert row['attached_databases'] == ['demo.fdb']


def test_old_stopped_denied_and_failed_samples_never_supply_current_metrics():
    for change, expected in [({'sample_age_seconds': 46}, 'stale'),
                             ({'state': 'expired'}, 'stale'),
                             ({'state': 'authorization-denied'}, 'permission-limited'),
                             ({'samples': []}, 'unknown'),
                             ({'samples': [{'status': 'unavailable'}]}, 'failed')]:
        row = observation(snapshot(**change), 'server')
        assert row['status'] == expected
        assert row['version'] is None
        assert row['attached_databases'] is None
    assert observation(snapshot(), 'database')['status'] == 'unknown'


def test_empty_and_mixed_inventory_authorize_each_scope_without_deduplicating():
    assert fleet_snapshot([], lambda *_: None)['registered_endpoints'] == 0
    calls = []

    def read(sid, target):
        calls.append((sid, target))
        if sid == 2:
            raise PermissionError('secret details')
        if target:
            return {'state': 'disabled'}
        return snapshot()

    servers = [{'server_id': sid, 'name': 'Same label',
                'databases': [{'target_id': 'one', 'name': 'DB'}]}
               for sid in [1, 2]]
    result = fleet_snapshot(servers, read)
    assert calls == [(1, None), (1, 'one'), (2, None), (2, 'one')]
    assert result['registered_endpoints'] == 2
    assert result['status_counts'] == {'reachable': 1, 'permission-limited': 1,
                                      'stale': 0, 'unknown': 0, 'failed': 0}
    assert result['servers'][0]['known_databases'] == 1
    assert result['servers'][0]['monitored_databases'] == 0
    assert 'secret details' not in str(result)
    assert result['servers'][1]['version'] is None


def test_database_aggregation_preserves_exact_values_and_identity_coverage():
    from pgadmin.cdeadmin.workspace.monitoring_fleet import aggregate
    row = {'database_identity': {'guid': 'g', 'file_id': 'f'},
           'coverage': 'database', 'sample_age_seconds': 1,
           'metrics': {'allocated_bytes': str(2**100), 'user_attachments': '2'}}
    another = {**row, 'database_identity': {'guid': 'g', 'file_id': 'other'}}
    result = aggregate([row, row, another, {'status': 'stale'}])
    assert result['identified_databases'] == 2
    assert result['alias_targets'] == 1
    assert result['unidentified_targets'] == 1
    assert result['metrics']['allocated_bytes']['value'] == str(2**101)
    assert result['metrics']['memory_used']['value'] is None
    assert result['metrics']['user_attachments']['observed_databases'] == 2


def test_stale_database_identity_and_metrics_do_not_contribute_to_totals():
    sample = {'status': 'available', 'transaction_refresh': {'status': 'completed'},
              'derived': {'allocated_bytes': '100'},
              'groups': {'database': {'status': 'available', 'values': {
                  'guid': 'g', 'file_id': 'f'}}}}
    row = observation(snapshot(samples=[sample], sample_age_seconds=100), 'database')
    assert row['database_identity']['guid'] is None
    assert row['metrics']['allocated_bytes'] is None


def test_nonidentical_rate_windows_are_not_silently_summed():
    from pgadmin.cdeadmin.workspace.monitoring_fleet import aggregate
    def row(identity, ended):
        return {'database_identity': {'guid': identity, 'file_id': identity},
                'rate_window': {'ended_at': ended, 'elapsed_seconds': '5'},
                'metrics': {'page_reads_per_second': '2'}}
    assert aggregate([row('a', 'one'), row('b', 'two')])['metrics']['page_reads_per_second']['value'] is None
    result = aggregate([row('a', 'one'), row('b', 'one')])['metrics']['page_reads_per_second']
    assert result['value'] == '4' and result['status'] == 'available'

"""Receipts preserve actual finality and never infer database attribution."""
from tools.cdeadmin_firebird_admin_mapping_gate import _create_client  # noqa: F401
from pgadmin.cdeadmin.workspace.monitoring_receipts import project_receipts


def test_receipts_filter_native_engine_and_exact_database_without_exposing_payload():
    records = [
        {'engine_id': 'firebird', 'operation_id': 'one', 'unknown_outcome': True,
         'provider_result': {'database': 'a.fdb', 'password': 'secret', 'server_completed': False}},
        {'engine_id': 'firebird', 'operation_id': 'two', 'provider_result': {'database': 'b.fdb'}},
        {'engine_id': 'mysql', 'operation_id': 'three', 'provider_result': {'database': 'a.fdb'}},
        {'engine_id': 'firebird', 'operation_id': 'unattributed'},
    ]
    value = project_receipts(records, 'a.fdb')
    assert [row['operation_id'] for row in value['rows']] == ['one']
    assert value['rows'][0]['unknown_outcome'] is True
    assert value['rows'][0]['server_completed'] is False
    assert 'secret' not in str(value)
    assert len(project_receipts(records)['rows']) == 3


def test_receipts_are_bounded_and_do_not_promote_missing_finality_to_success():
    value = project_receipts([{'engine_id': 'firebird', 'operation_id': str(i)} for i in range(101)])
    assert value['truncated'] and len(value['rows']) == 100
    assert all(row['server_completed'] is None for row in value['rows'])

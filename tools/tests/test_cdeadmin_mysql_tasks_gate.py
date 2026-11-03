import json

from tools.cdeadmin_mysql_tasks_gate import ROOT, declared, reconcile

DIALECT = ROOT / 'web/pgadmin/cdeadmin/providers/mysql_family/mysql_dialect_9_7_0.json'


def test_task_inventory_and_failed_specialized_receipts_cannot_close_coverage():
    # 105 at the gate's introduction; 154 after the masking, failover,
    # server-link, rewrite-rule, XA, key-cache, page-tracking, keyring and
    # spatial-reference-system tasks. A change here must be a declared task.
    assert len(declared()) == 154
    dialect = json.loads(DIALECT.read_text())
    rows = dialect['task_templates']
    assert len(rows) == len({row['task_id'] for row in rows})
    kinds = {proof['evidence_id']: proof['evidence_kind'] for proof in dialect['proof_records']}
    for row in rows:
        # Only visual_admin tasks can be closed by a specialized receipt, and
        # each cites recorded parser acceptance and live execution proof.
        assert row['task_id'].startswith('visual_admin.')
        assert {kinds[proof] for proof in row['proof_ids']} == {'parser_acceptance', 'live_execution'}
        assert row['source'].strip()
    receipt = {'passed': True, 'engine_version': '9.7.0', 'owned_cleanup_confirmed': True,
               'task_evidence': {'visual_admin.role.grant': {'live_execution': 'passed'},
                                 'visual_admin.role.revoke': {'live_execution': 'not-dispatched'}}}
    assert reconcile('role', receipt, 0) == {'visual_admin.role.grant'}
    for change in ({'passed': False}, {'engine_version': '12.2.2'}, {'owned_cleanup_confirmed': False}, {'failures': ['native']}):
        assert reconcile('role', {**receipt, **change}, 0) is None
    assert reconcile('role', receipt, 1) is None


def test_application_tool_receipts_close_only_tasks_acknowledged_on_both_interfaces():
    from tools.cdeadmin_mysql_tasks_gate import application_evidence
    expected = declared()
    fixture = {'engine_version': '9.7.0', 'owned_server_stopped': True}
    def receipts(*rows):
        return {'complete': True, 'owned_server_stopped': True,
                'application': {'complete': True, 'operations': [
                    {'use_pure': pure, 'operation': operation, 'reviewed_native_acknowledged': acknowledged}
                    for operation, pure, acknowledged in rows]}}
    proof = receipts(('commit_prepared_xa', True, True), ('commit_prepared_xa', False, True),
                     ('rollback_prepared_xa', True, True),                      # one interface only
                     ('inspect_prepared_xa', True, True), ('inspect_prepared_xa', False, False),
                     ('not_a_declared_operation', True, True), ('not_a_declared_operation', False, True))
    receipt = application_evidence(proof, fixture, expected)
    assert set(receipt['task_evidence']) == {'visual_admin.server.commit_prepared_xa'}
    assert reconcile('xa', receipt, 0) == {'visual_admin.server.commit_prepared_xa'}
    # Incomplete tools, unstopped servers or another version close nothing.
    for change, version in (({'complete': False}, '9.7.0'), ({'owned_server_stopped': False}, '9.7.0'), ({}, '9.6.0')):
        failed = application_evidence({**proof, **change}, {**fixture, 'engine_version': version}, expected)
        assert reconcile('xa', failed, 0) is None
    assert reconcile('xa', application_evidence({**proof, 'application': {'complete': False, 'operations':
                     proof['application']['operations']}}, fixture, expected), 0) is None
    assert reconcile('xa', receipt, 1) is None

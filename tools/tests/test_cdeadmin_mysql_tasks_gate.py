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

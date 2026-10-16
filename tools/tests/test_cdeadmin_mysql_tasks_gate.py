from tools.cdeadmin_mysql_tasks_gate import declared, reconcile


def test_task_inventory_and_failed_specialized_receipts_cannot_close_coverage():
    assert len(declared()) == 105
    receipt = {'passed': True, 'engine_version': '9.7.0', 'owned_cleanup_confirmed': True,
               'task_evidence': {'visual_admin.role.grant': {'live_execution': 'passed'},
                                 'visual_admin.role.revoke': {'live_execution': 'not-dispatched'}}}
    assert reconcile('role', receipt, 0) == {'visual_admin.role.grant'}
    for change in ({'passed': False}, {'engine_version': '12.2.2'}, {'owned_cleanup_confirmed': False}, {'failures': ['native']}):
        assert reconcile('role', {**receipt, **change}, 0) is None
    assert reconcile('role', receipt, 1) is None

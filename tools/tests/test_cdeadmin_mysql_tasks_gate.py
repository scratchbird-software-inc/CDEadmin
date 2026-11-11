import json

from tools.cdeadmin_mysql_tasks_gate import ROOT, declared, reconcile

DIALECT = ROOT / 'web/pgadmin/cdeadmin/providers/mysql_family/mysql_dialect_9_7_0.json'


def test_task_inventory_and_failed_specialized_receipts_cannot_close_coverage():
    # 105 at the gate's introduction; 154 after the masking, failover,
    # server-link, rewrite-rule, XA, key-cache, page-tracking, keyring and
    # spatial-reference-system tasks; 155 with the index alter (2026-11-05,
    # qualified and added to the contract 2026-11-10). A change here must
    # be a declared task.
    assert len(declared()) == 155
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
    fixtures = [{'engine_version': '9.7.0', 'owned_server_stopped': True}]
    def receipts(*rows):
        return {'complete': True, 'owned_server_stopped': True,
                'application': {'complete': True, 'operations': [
                    {'use_pure': pure, 'operation': operation, 'reviewed_native_acknowledged': acknowledged}
                    for operation, pure, acknowledged in rows]}}
    proof = receipts(('commit_prepared_xa', True, True), ('commit_prepared_xa', False, True),
                     ('rollback_prepared_xa', True, True),                      # one interface only
                     ('inspect_prepared_xa', True, True), ('inspect_prepared_xa', False, False),
                     ('not_a_declared_operation', True, True), ('not_a_declared_operation', False, True))
    receipt = application_evidence(proof, fixtures, expected)
    assert set(receipt['task_evidence']) == {'visual_admin.server.commit_prepared_xa'}
    assert reconcile('xa', receipt, 0) == {'visual_admin.server.commit_prepared_xa'}
    # Incomplete tools, unstopped servers or another version close nothing.
    for change, version in (({'complete': False}, '9.7.0'), ({'owned_server_stopped': False}, '9.7.0'), ({}, '9.6.0')):
        failed = application_evidence({**proof, **change}, [{**fixtures[0], 'engine_version': version}], expected)
        assert reconcile('xa', failed, 0) is None
    # Several owned fixtures: all must be the checked version and stopped.
    several = {**proof, 'owned_server_stopped': None, 'owned_servers_stopped': True}
    assert reconcile('xa', application_evidence(several, fixtures * 2, expected), 0) == {'visual_admin.server.commit_prepared_xa'}
    for other in ({'engine_version': '9.6.0', 'owned_server_stopped': True}, {'engine_version': '9.7.0', 'owned_server_stopped': False}):
        assert reconcile('xa', application_evidence(several, [*fixtures, other], expected), 0) is None
    assert reconcile('xa', application_evidence(proof, [], expected), 0) is None
    assert reconcile('xa', application_evidence({**proof, 'application': {'complete': False, 'operations':
                     proof['application']['operations']}}, fixtures, expected), 0) is None
    assert reconcile('xa', receipt, 1) is None
    # An operation shared by many kinds closes only the kind its receipt names.
    shared = {'complete': True, 'owned_server_stopped': True, 'application': {'complete': True, 'operations': [
        {'use_pure': pure, 'resource_kind': kind, 'operation': 'create', 'native_acknowledged': True}
        for pure in (True, False) for kind in ('spatial-reference-system', 'not-a-kind')]}}
    assert reconcile('spatial_reference', application_evidence(shared, fixtures, expected), 0) == {
        'visual_admin.spatial-reference-system.create'}
    unnamed = {**shared, 'application': {'complete': True, 'operations': [
        {key: value for key, value in row.items() if key != 'resource_kind'} for row in shared['application']['operations']]}}
    assert reconcile('spatial_reference', application_evidence(unnamed, fixtures, expected), 0) is None


def test_ddn_revision_alone_does_not_void_a_run_but_any_vendored_change_does(tmp_path, monkeypatch):
    import copy
    import tools.cdeadmin_mysql_tasks_gate as gate
    manifest = json.loads((ROOT / gate.DDN_MANIFEST).read_text())
    copied = tmp_path / gate.DDN_MANIFEST
    copied.parent.mkdir(parents=True)
    # Only the manifest is relocated; every other bound file is the real one.
    real = gate.ROOT
    monkeypatch.setattr(gate, 'ROOT', tmp_path)
    for relative in ('web/pgadmin/cdeadmin', 'tools'):
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        if not (tmp_path / relative).exists():
            (tmp_path / relative).symlink_to(real / relative)
    def bound(document):
        copied.write_text(json.dumps(document))
        return gate.bindings()[gate.DDN_MANIFEST]
    original = bound(manifest)
    moved = copy.deepcopy(manifest); moved['source']['revision'] = '0' * 40
    assert bound(moved) == original
    assert gate.ddn_revision() == '0' * 40
    changes = []
    for path, value in ((('source', 'files'), 'changed'), (('release_hash',), 'changed'), (('source', 'subtree'), 'changed')):
        document = copy.deepcopy(manifest)
        holder = document
        for key in path[:-1]:
            holder = holder[key]
        if path[-1] == 'files':
            name = next(iter(holder['files']))
            holder['files'][name] = 'f' * 64
        else:
            holder[path[-1]] = value
        changes.append(bound(document))
    assert original not in changes and len(set(changes)) == 3

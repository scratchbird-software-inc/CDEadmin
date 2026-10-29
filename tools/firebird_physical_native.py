"""Diagram physical-schema edits (indexes, constraints, FK actions, drops) through a real
Firebird: ERD -> vocabulary edit -> handoff -> reviewed plan -> owned-transaction apply ->
rediscovery -> converged re-plan."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = 'relations.ddn'


def qualify(connection, provider, route, root):
    from pgadmin.cdeadmin.providers.firebird.provider import _resources
    from pgadmin.cdeadmin.providers.firebird.schema_application import apply_review
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
    from pgadmin.cdeadmin.workspace.firebird_relational_review import handoff
    from pgadmin.cdeadmin.workspace.firebird_schema_apply import SchemaApplications
    from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan
    store = SchemaApplications(root / 'physical-receipts.json')

    def sql(source):
        with connection.cursor() as cursor:
            cursor.execute(source)
            return cursor.fetchall() if cursor.description else []

    def resources():
        if connection.main_transaction.is_active():
            connection.rollback()
        rows = _resources(connection, {})
        connection.rollback()
        return rows

    def export():
        catalog = build_export(resources(), endpoint_id='owned', target_id='owned', generation='physical')
        return catalog, catalog['diagram']

    def edit(diagram, resource_id, **values):
        key = next(k for k, v in diagram['resource_mapping'].items() if v == resource_id)
        edits = [{'target': {'file': FILE, 'id': 'relations.mapping_' + key},
                  'path': 'metadata.x_record.record.' + name, 'value': value} for name, value in values.items()]
        done = subprocess.run(['node', str(ROOT / 'tools/ddn_edit.mjs')], input=json.dumps(
            {'snapshot': diagram['snapshot'], 'edits': edits}), text=True, capture_output=True, timeout=60, check=True)
        return json.loads(done.stdout)

    def review(catalog, diagram, edited):
        result = handoff(catalog['snapshot'], diagram['snapshot'], edited)
        baseline, desired = read_catalog(result['baseline']), read_catalog(result['desired'])

        def plan():
            current = build_export(resources(), endpoint_id='owned', target_id='owned', generation='physical',
                                   include_system=True, native_model=True)
            return build_plan(baseline, desired, current)
        return baseline, desired, plan

    def settle(catalog, diagram, edited):
        baseline, desired, plan = review(catalog, diagram, edited)
        first = plan()
        assert first['status'] == 'review-ready', first['blockers']
        reviewed = store.review(first, baseline, desired, 'owner', 'binding', route['database'])
        outcome = store.apply({'review_id': reviewed['review_id'], 'review_digest': reviewed['review_digest'],
                               'confirmed': True}, 'owner', 'binding',
                              lambda record: apply_review(provider, route, record))['outcome']
        assert outcome['native_commit_returned'] and outcome['rediscovery']['available'], outcome
        assert all(item['matches_reviewed_properties'] for item in outcome['rediscovery']['objects']), outcome
        again = plan()
        assert again['status'] == 'no-op' and not again['blockers'], again
        return first

    sql('CREATE TABLE PH_PARENT (ID INTEGER NOT NULL PRIMARY KEY, CODE VARCHAR(10), CONSTRAINT PH_CODE UNIQUE (CODE))')
    sql('CREATE TABLE PH_CHILD (ID INTEGER NOT NULL, P INTEGER, AMOUNT INTEGER, '
        'CONSTRAINT PH_FK FOREIGN KEY (P) REFERENCES PH_PARENT (ID) ON DELETE CASCADE, CONSTRAINT PH_CK CHECK (AMOUNT > 0))')
    sql('CREATE INDEX PH_IDX ON PH_CHILD (AMOUNT)')
    connection.commit()
    catalog, diagram = export()
    # Index: definition change is a reviewed DROP + CREATE; ACTIVE/INACTIVE is ALTER INDEX.
    plan = settle(catalog, diagram, edit(diagram, 'index:PH_CHILD:PH_IDX', unique=True, descending=True, columns_json='["ID","AMOUNT"]'))
    assert plan['operations'][0]['operation'] == 'replace'
    assert sql("SELECT RDB$UNIQUE_FLAG, RDB$INDEX_TYPE FROM RDB$INDICES WHERE RDB$INDEX_NAME = 'PH_IDX'") == [(1, 1)]
    catalog, diagram = export()
    settle(catalog, diagram, edit(diagram, 'index:PH_CHILD:PH_IDX', inactive=True))
    assert sql("SELECT RDB$INDEX_INACTIVE FROM RDB$INDICES WHERE RDB$INDEX_NAME = 'PH_IDX'") == [(1,)]
    # Constraint: FK actions and CHECK expression replace the constraint natively.
    catalog, diagram = export()
    settle(catalog, diagram, edit(diagram, 'constraint:PH_CHILD:PH_FK', on_delete='SET NULL', on_update='CASCADE'))
    assert [tuple(rule.strip() for rule in row) for row in sql(
        "SELECT RDB$UPDATE_RULE, RDB$DELETE_RULE FROM RDB$REF_CONSTRAINTS WHERE RDB$CONSTRAINT_NAME = 'PH_FK'")] == [('CASCADE', 'SET NULL')]
    catalog, diagram = export()
    settle(catalog, diagram, edit(diagram, 'constraint:PH_CHILD:PH_CK', expression='(AMOUNT >= 10)'))
    # Explicit drops: flagged destructive, exact confirmation.
    catalog, diagram = export()
    plan = settle(catalog, diagram, edit(diagram, 'index:PH_CHILD:PH_IDX', drop=True, drop_confirmation='PH_IDX'))
    assert plan['operations'][0]['destructive'] is True
    assert sql("SELECT COUNT(*) FROM RDB$INDICES WHERE RDB$INDEX_NAME = 'PH_IDX'") == [(0,)]
    catalog, diagram = export()
    settle(catalog, diagram, edit(diagram, 'constraint:PH_CHILD:PH_FK', drop=True, drop_confirmation='PH_FK'))
    # New objects drafted in the diagram, and a rename Firebird 5.0 cannot do.
    catalog, diagram = export()
    owner = 'table:PH_CHILD'
    uid = 'firebird:owned:owned:' + owner
    import sys
    sys.path.insert(0, str(ROOT / 'tools/tests'))
    import physical_roundtrip as rt
    edited, _ = rt.add_draft_element(diagram, diagram['snapshot'], owner, uid, 'index', 'PH_NEW_IDX',
        {'physical_kind': 'index', 'physical_name': 'PH_NEW_IDX', 'columns_json': '["P","AMOUNT"]', 'unique': True}, 'firebird')
    edited, _ = rt.add_draft_element(diagram, edited, owner, uid, 'constraint', 'PH_NEW_UQ',
        {'physical_kind': 'unique', 'physical_name': 'PH_NEW_UQ', 'columns_json': '["ID"]'}, 'firebird')
    plan = settle(catalog, diagram, edited)
    assert {item['operation'] for item in plan['operations']} == {'create'}, plan['operations']
    assert sql("SELECT COUNT(*) FROM RDB$INDICES WHERE RDB$INDEX_NAME IN ('PH_NEW_IDX', 'PH_NEW_UQ')") == [(2,)]
    catalog, diagram = export()
    try:
        review(catalog, diagram, edit(diagram, 'constraint:PH_CHILD:PH_NEW_UQ', physical_name='PH_UQ2', rename_from='PH_NEW_UQ'))
        raise AssertionError('a constraint rename must not be carried')
    except ValueError as error:
        assert 'Not carried to Firebird' in str(error), error
    sql('SELECT 1 FROM RDB$DATABASE')
    connection.rollback()
    return {'drafted_index_and_unique': True, 'rename_not_carried': True, 'index_replace_active_inactive_drop': True, 'constraint_replace_and_drop': True,
            'fk_actions': True, 'converged_replan': True, 'native_rediscovery': True}

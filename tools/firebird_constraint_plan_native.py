"""Existing-table CHECK/key replacement with native data validation and rollback."""
from copy import deepcopy


def qualify(connection, provider, route, root):
    from pgadmin.cdeadmin.providers.firebird.schema_application import capture, apply_review
    from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan, digest
    from pgadmin.cdeadmin.workspace.firebird_schema_apply import SchemaApplications
    target = {'endpoint_id': 'owned', 'database_target_id': 'owned', 'generation': 'constraint-native'}
    store = SchemaApplications(root / 'constraint-receipts.json')
    def sql(source):
        with connection.cursor() as cursor:
            cursor.execute(source)
            return cursor.fetchall() if cursor.description else []
    def snapshot():
        if connection.main_transaction.is_active():
            connection.rollback()
        result = capture(connection, target)
        connection.rollback()
        return result
    def application(base, desired):
        desired['sha256'] = digest(desired['rows'])
        plan = build_plan(base, desired, base)
        assert plan['status'] == 'review-ready', plan['blockers']
        review = store.review(plan, base, desired, 'owned', 'owned', route['database'])
        return SchemaApplications(store.path).apply({'review_id': review['review_id'],
            'review_digest': review['review_digest'], 'confirmed': True}, 'owned', 'owned',
            lambda record: apply_review(provider, route, record))['outcome']
    def expect_commit(outcome):
        assert outcome['native_commit_returned'] and outcome['attachment_released'], outcome
        assert outcome['rediscovery']['available'], outcome
        assert all(item['matches_reviewed_properties'] for item in outcome['rediscovery']['objects']), outcome
    def add(desired, name, native):
        identity = 'constraint:C_DATA:' + name
        desired['rows'][identity] = {'resource_id': identity, 'kind': 'constraint',
            'name': name, 'path': ['C_DATA', name], 'system': 'false', 'native': native}
        if native.get('backing_index'):
            backing = native['backing_index']; index_id = 'index:C_DATA:' + backing['name']
            desired['rows'][index_id] = {'resource_id': index_id, 'kind': 'index',
                'name': backing['name'], 'path': ['C_DATA', backing['name']], 'system': 'false',
                'native': {key: deepcopy(value) for key, value in backing.items() if key != 'name'}}
    def index(name, field, unique=True):
        return {'name': name, 'unique': 1 if unique else 0, 'inactive': 0, 'index_type': 1,
            'segments': [{'field_name': field, 'position': 0}], 'description': 'backing comment'}
    sql('CREATE TABLE C_PARENT (ID INTEGER PRIMARY KEY)')
    sql('CREATE TABLE C_DATA (ID INTEGER NOT NULL, V INTEGER, P INTEGER)')
    connection.commit()
    sql('INSERT INTO C_PARENT VALUES (1)'); sql('INSERT INTO C_DATA VALUES (1, 7, 1)')
    connection.commit()
    base = snapshot(); desired = deepcopy(base)
    add(desired, 'C_CHECK', {'constraint_type': 'CHECK', 'check_source': 'CHECK (V >= 0)'})
    add(desired, 'C_PRIMARY', {'constraint_type': 'PRIMARY KEY', 'index_name': 'IX_PRIMARY', 'backing_index': index('IX_PRIMARY', 'ID')})
    add(desired, 'C_UNIQUE', {'constraint_type': 'UNIQUE', 'index_name': 'IX_UNIQUE', 'backing_index': index('IX_UNIQUE', 'V')})
    parent = next(row for row in base['rows'].values() if row['kind'] == 'constraint' and row['path'][0] == 'C_PARENT' and row['native']['constraint_type'] == 'PRIMARY KEY')
    add(desired, 'C_FOREIGN', {'constraint_type': 'FOREIGN KEY', 'index_name': 'IX_FOREIGN',
        'backing_index': index('IX_FOREIGN', 'P', False), 'referenced_relation': 'C_PARENT',
        'referenced_index': parent['native']['index_name'], 'update_rule': 'CASCADE', 'delete_rule': 'SET NULL'})
    expect_commit(application(base, desired))
    base = snapshot(); desired = deepcopy(base)
    desired['rows']['constraint:C_DATA:C_CHECK']['native']['check_source'] = 'CHECK (V >= 5)'
    desired['rows']['constraint:C_DATA:C_FOREIGN']['native']['delete_rule'] = 'CASCADE'
    desired['rows']['constraint:C_DATA:C_UNIQUE']['native']['backing_index']['index_type'] = 0
    desired['rows']['index:C_DATA:IX_UNIQUE']['native']['index_type'] = 0
    expect_commit(application(base, desired))
    sql('DELETE FROM C_PARENT WHERE ID=1')
    assert sql('SELECT COUNT(*) FROM C_DATA') == [(0,)]
    connection.rollback()
    base = snapshot(); desired = deepcopy(base)
    desired['rows']['constraint:C_DATA:C_CHECK']['native']['check_source'] = 'CHECK (V >= 10)'
    expect_commit(application(base, desired))
    assert sql('SELECT V FROM C_DATA') == [(7,)]  # Native CHECK does not scan existing rows.
    connection.rollback()
    base = snapshot(); desired = deepcopy(base)
    desired['rows']['constraint:C_DATA:C_CHECK']['native']['check_source'] = 'CHECK (V >= 5)'
    expect_commit(application(base, desired))
    sql('INSERT INTO C_DATA VALUES (2, 8, 1)'); connection.commit()
    base = snapshot(); desired = deepcopy(base)
    desired['rows']['constraint:C_DATA:C_CHECK']['native']['check_source'] = 'CHECK (V >= 6)'
    desired['rows']['constraint:C_DATA:C_UNIQUE']['native']['backing_index']['segments'] = [{'field_name': 'P', 'position': 0}]
    desired['rows']['index:C_DATA:IX_UNIQUE']['native']['segments'] = [{'field_name': 'P', 'position': 0}]
    failure = application(base, desired)
    assert failure['native_rollback_returned'] and not failure['native_commit_returned'], failure
    assert snapshot()['rows']['constraint:C_DATA:C_CHECK']['native']['check_source'] == base['rows']['constraint:C_DATA:C_CHECK']['native']['check_source']
    # A failed replacement leaves the old check enforced, not merely present.
    try:
        sql('INSERT INTO C_DATA VALUES (3, 1, 1)')
    except Exception as error:
        assert getattr(error, 'sqlcode', None) is not None or getattr(error, 'gds_codes', None), type(error)
        connection.rollback()
    else:
        raise AssertionError('Old native CHECK did not survive rollback')
    assert sql("SELECT COUNT(*) FROM RDB$INDICES WHERE RDB$INDEX_NAME IN ('IX_PRIMARY','IX_UNIQUE','IX_FOREIGN') AND RDB$DESCRIPTION IS NOT NULL") == [(3,)]
    connection.rollback()
    return {'durable_reviews': True, 'check_primary_unique_foreign_created': True,
        'matching_index_projections_created_and_changed_once': True,
        'check_foreign_and_index_direction_replaced': True, 'cascade_effect_observed': True,
        'invalid_data_restores_original_constraint': True, 'restored_check_enforced': True,
        'check_does_not_revalidate_existing_rows': True, 'backing_comments_preserved': True, 'native_rediscovery': True}

"""Owned native table creation/alteration and rediscovery through plan apply."""
from copy import deepcopy


def qualify(connection, provider, route):
    from pgadmin.cdeadmin.providers.firebird.schema_application import capture, apply_review
    from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan, digest
    target = {'endpoint_id': 'owned', 'database_target_id': 'owned', 'generation': 'table-native'}
    def snapshot():
        if connection.main_transaction.is_active():
            connection.rollback()
        value = capture(connection, target)
        connection.rollback()
        return value
    def apply(base, desired):
        desired['sha256'] = digest(desired['rows'])
        plan = build_plan(base, desired, base)
        assert plan['status'] == 'review-ready', plan['blockers']
        value = apply_review(provider, route, {'plan': plan, 'baseline': base, 'desired': desired})
        assert value['native_commit_returned'], value
        if not value['rediscovery']['available']:
            from pgadmin.cdeadmin.workspace.firebird_table_plan import creation_model
            from pgadmin.cdeadmin.workspace.firebird_schema_plan import _model
            observed = snapshot()
            for operation in plan['operations']:
                _model(observed['rows'][operation['resource_id']])
                if 'creation_table' in operation['after']:
                    creation_model(observed['rows'][operation['resource_id']], observed, observed=True)
        assert value['rediscovery']['available'], value
        assert all(item['matches_reviewed_properties'] for item in value['rediscovery']['objects']), value
        return value
    results = []
    for kind in (0, 4, 5):
        name = 'TABLE_PLAN_' + str(kind)
        base = snapshot(); desired = deepcopy(base)
        identity = 'table:' + name
        desired['rows'][identity] = {'resource_id': identity, 'kind': 'table', 'path': [name],
            'name': name, 'system': 'false', 'native': {'relation_type': kind,
            'sql_security': '0', 'publication_enabled': False, 'description': 'Created from native design',
            'columns': [{'name': 'Exact"ID', 'position': 0, 'field_type': 8,
                         'field_sub_type': 0, 'field_scale': 0, 'dimensions': 0, 'description': 'Exact field comment'}]}}
        results.append(apply(base, desired))
        base = snapshot(); desired = deepcopy(base)
        desired['rows'][identity]['native']['sql_security'] = '1'
        desired['rows'][identity]['native']['publication_enabled'] = True
        desired['rows'][identity]['native']['description'] = 'Altered without recreation'
        results.append(apply(base, desired))
    with connection.cursor() as cursor:
        cursor.execute('CREATE DOMAIN TABLE_PLAN_DOMAIN AS INTEGER NOT NULL')
        cursor.execute("CREATE TABLE TABLE_PLAN_SOURCE (A INTEGER[-2:2], D TABLE_PLAN_DOMAIN, I BIGINT GENERATED ALWAYS AS IDENTITY (START WITH 42 INCREMENT BY 3), C INTEGER COMPUTED BY (I + 1), TXT VARCHAR(20) CHARACTER SET UTF8 DEFAULT 'a')")
    connection.commit()
    base = snapshot(); desired = deepcopy(base)
    prototype = deepcopy(base['rows']['table:TABLE_PLAN_SOURCE']['native'])
    assert str(prototype['columns'][1]['domain_not_null']) == '1'
    # Authored design copies structured column facts, never the source DDL.
    desired['rows']['table:TABLE_PLAN_TYPES'] = {'resource_id': 'table:TABLE_PLAN_TYPES',
        'kind': 'table', 'path': ['TABLE_PLAN_TYPES'], 'name': 'TABLE_PLAN_TYPES', 'system': 'false',
        'native': {key: prototype[key] for key in ('relation_type', 'sql_security', 'publication_enabled', 'description', 'columns')}}
    try:
        results.append(apply(base, desired))
    except AssertionError:
        print('Native type facts:', [{key: col.get(key) for key in ('name', 'field_type', 'field_sub_type', 'field_precision', 'field_scale', 'computed_source')} for col in prototype['columns']])
        raise
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO TABLE_PLAN_TYPES (D, TXT) VALUES (7, 'value') RETURNING I, C")
        assert cursor.fetchone() == (42, 43)
    connection.rollback()
    base = snapshot(); desired = deepcopy(base)
    invalid = deepcopy(desired['rows']['table:TABLE_PLAN_TYPES'])
    invalid.update(resource_id='table:TABLE_PLAN_INVALID', path=['TABLE_PLAN_INVALID'], name='TABLE_PLAN_INVALID')
    invalid['native'] = {key: invalid['native'][key] for key in ('relation_type', 'sql_security', 'publication_enabled', 'description', 'columns')}
    invalid['native']['columns'] = [dict(invalid['native']['columns'][3], position=0, computed_source='(UNKNOWN_NATIVE_FIELD + 1)')]
    desired['rows'][invalid['resource_id']] = invalid
    desired['sha256'] = digest(desired['rows'])
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    refused = apply_review(provider, route, {'plan': plan, 'baseline': base, 'desired': desired})
    assert refused['native_rollback_returned'] and not refused['native_commit_returned'], refused
    assert invalid['resource_id'] not in snapshot()['rows']
    base = snapshot(); desired = deepcopy(base)
    def column(name, position, required=False):
        return {'name': name, 'position': position, 'field_type': 8, 'field_sub_type': 0,
                'field_scale': 0, 'dimensions': 0, 'not_null': 1 if required else None}
    def index(name, field, unique=False, direction=0, **extra):
        return {'name': name, 'unique': 1 if unique else 0, 'inactive': 0, 'index_type': direction,
                'segments': [{'field_name': field, 'position': 0}], **extra}
    identity = 'table:TABLE_PLAN_KEYS'
    desired['rows'][identity] = {'resource_id': identity, 'kind': 'table', 'path': ['TABLE_PLAN_KEYS'],
        'name': 'TABLE_PLAN_KEYS', 'system': 'false', 'native': {'relation_type': 0, 'sql_security': None,
        'publication_enabled': False, 'description': None,
        'columns': [column('ID', 0, True), column('PARENT_ID', 1), column('U', 2, True)],
        'constraints': [
            {'name': 'TP_PK', 'constraint_type': 'PRIMARY KEY', 'index_name': 'TP_PK_IDX'},
            {'name': 'TP_UQ', 'constraint_type': 'UNIQUE', 'index_name': 'TP_UQ_IDX'},
            {'name': 'TP_NN', 'constraint_type': 'NOT NULL', 'not_null_column': 'U'},
            {'name': 'TP_CK', 'constraint_type': 'CHECK', 'check_source': 'CHECK (ID > 0)'},
            {'name': 'TP_FK', 'constraint_type': 'FOREIGN KEY', 'index_name': 'TP_FK_IDX',
             'referenced_relation': 'TABLE_PLAN_KEYS', 'referenced_index': 'TP_PK_IDX',
             'update_rule': 'CASCADE', 'delete_rule': 'SET NULL'}],
        'indexes': [index('TP_PK_IDX', 'ID', True), index('TP_UQ_IDX', 'U', True, 1),
                    index('TP_FK_IDX', 'PARENT_ID'), index('TP_PARTIAL', 'ID', condition_source='WHERE ID > 1', description='Exact index comment')]}}
    results.append(apply(base, desired))
    with connection.cursor() as cursor:
        cursor.execute('INSERT INTO TABLE_PLAN_KEYS VALUES (1, NULL, 10)')
        cursor.execute('INSERT INTO TABLE_PLAN_KEYS VALUES (2, 1, 20)')
        cursor.execute('UPDATE TABLE_PLAN_KEYS SET ID=3 WHERE ID=1')
        cursor.execute('SELECT PARENT_ID FROM TABLE_PLAN_KEYS WHERE ID=2')
        assert cursor.fetchone() == (3,)
        cursor.execute('DELETE FROM TABLE_PLAN_KEYS WHERE ID=3')
        cursor.execute('SELECT PARENT_ID FROM TABLE_PLAN_KEYS WHERE ID=2')
        assert cursor.fetchone() == (None,)
    connection.rollback()
    base = snapshot(); desired = deepcopy(base)
    identity = 'table:TABLE_PLAN_REFERENCING'
    desired['rows'][identity] = {'resource_id': identity, 'kind': 'table', 'path': ['TABLE_PLAN_REFERENCING'],
        'name': 'TABLE_PLAN_REFERENCING', 'system': 'false', 'native': {'relation_type': 0, 'sql_security': None,
        'publication_enabled': False, 'description': None, 'columns': [column('PARENT_ID', 0)],
        'constraints': [{'name': 'TP_EXTERNAL_FK', 'constraint_type': 'FOREIGN KEY', 'index_name': 'TP_EXTERNAL_IDX',
             'referenced_relation': 'TABLE_PLAN_KEYS', 'referenced_index': 'TP_PK_IDX',
             'update_rule': 'CASCADE', 'delete_rule': 'SET NULL'}],
        'indexes': [index('TP_EXTERNAL_IDX', 'PARENT_ID')]}}
    results.append(apply(base, desired))
    with connection.cursor() as cursor:
        cursor.execute('CREATE TRIGGER U FOR TABLE_PLAN_KEYS ACTIVE BEFORE INSERT AS BEGIN END')
    connection.commit()
    observed = snapshot()
    generated = observed['rows']['table:TABLE_PLAN_KEYS']['native']['triggers']
    assert any(item.get('constraint_owner') == 'TP_EXTERNAL_FK' for item in generated), generated
    from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION
    managed = next(item for item in generated if item.get('constraint_owner'))
    assert managed['administration']['allowed_operations'] == ['inspect'], managed
    request = {'resource_kind': 'trigger', 'operation_id': 'drop',
               'target_resource': {'resource_kind': 'trigger', 'display_name': managed['name'], 'native': managed}, 'draft': {}}
    assert ADMINISTRATION.validate(request)['errors'][0]['code'] == 'constraint_owned_trigger'
    user_trigger = next(item for item in generated if item['name'] == 'U')
    assert 'constraint_owner' not in user_trigger, user_trigger
    # Multiple new domains/tables/indexes/views are one native dependency plan.
    base = snapshot(); desired = deepcopy(base)
    def authored(kind, name, native, parent=None):
        path = [parent, name] if parent else [name]
        identity = ':'.join([kind, *path])
        desired['rows'][identity] = {'resource_id': identity, 'kind': kind,
            'name': name, 'path': path, 'system': 'false', 'native': native}
        return identity
    domain_native = {'field_type': 8, 'field_sub_type': 0, 'field_scale': 0,
        'dimensions': 0, 'not_null': 1, 'default_source': None, 'validation_source': None, 'description': None}
    domain_id = authored('domain', 'GRAPH_Z_DOMAIN', domain_native)
    parent_id = authored('table', 'GRAPH_Z_PARENT', {'relation_type': 0, 'sql_security': None,
        'publication_enabled': False, 'columns': [{**column('ID', 0, True), 'domain': 'GRAPH_Z_DOMAIN', 'domain_not_null': 1}],
        'constraints': [{'name': 'GRAPH_PK', 'constraint_type': 'PRIMARY KEY', 'index_name': 'GRAPH_PK_IDX'}],
        'indexes': [index('GRAPH_PK_IDX', 'ID', True)]})
    child_id = authored('table', 'GRAPH_A_CHILD', {'relation_type': 0, 'sql_security': None,
        'publication_enabled': False, 'columns': [column('PARENT_ID', 0)],
        'constraints': [{'name': 'GRAPH_FK', 'constraint_type': 'FOREIGN KEY', 'index_name': 'GRAPH_FK_IDX',
            'referenced_relation': 'GRAPH_Z_PARENT', 'referenced_index': 'GRAPH_PK_IDX',
            'update_rule': 'CASCADE', 'delete_rule': 'SET NULL'}],
        'indexes': [index('GRAPH_FK_IDX', 'PARENT_ID'), index('GRAPH_NESTED_IDX', 'PARENT_ID', direction=1)]})
    index_id = authored('index', 'GRAPH_EXTRA_IDX', {key: value for key, value in index('GRAPH_EXTRA_IDX', 'PARENT_ID', description='Separate authored index').items() if key != 'name'}, 'GRAPH_A_CHILD')
    nested_id = authored('index', 'GRAPH_NESTED_IDX', {key: value for key, value in index('GRAPH_NESTED_IDX', 'PARENT_ID', direction=1).items() if key != 'name'}, 'GRAPH_A_CHILD')
    view_z = authored('view', 'GRAPH_Z_VIEW', {'relation_type': 1,
        'definition': 'SELECT ID FROM GRAPH_Z_PARENT', 'columns': [{'name': 'ID', 'position': 0}],
        'creation_dependencies': [parent_id]})
    view_a = authored('view', 'GRAPH_A_VIEW', {'relation_type': 1,
        'definition': 'SELECT ID FROM GRAPH_Z_VIEW', 'columns': [{'name': 'ID', 'position': 0}],
        'creation_dependencies': [view_z]})
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    ordered = [item['resource_id'] for item in plan['operations']]
    for prerequisite, consumer in [(domain_id, parent_id), (child_id, index_id), (parent_id, view_z), (view_z, view_a)]:
        assert ordered.index(prerequisite) < ordered.index(consumer), plan
    assert plan['script'].count('INDEX "GRAPH_NESTED_IDX" ON') == 1
    assert next(item for item in plan['operations'] if item['resource_id'] == nested_id)['embedded_index_definition']
    graph_receipt = apply(base, desired)
    with connection.cursor() as cursor:
        cursor.execute('INSERT INTO GRAPH_Z_PARENT VALUES (9)')
        cursor.execute('INSERT INTO GRAPH_A_CHILD VALUES (9)')
        cursor.execute('UPDATE GRAPH_Z_PARENT SET ID=10 WHERE ID=9')
        cursor.execute('SELECT PARENT_ID FROM GRAPH_A_CHILD')
        assert cursor.fetchall() == [(10,)]
        cursor.execute('SELECT ID FROM GRAPH_A_VIEW')
        assert cursor.fetchall() == [(10,)]
    connection.rollback()
    base = snapshot(); desired = deepcopy(base)
    for name, other in [('CYCLE_A', 'CYCLE_B'), ('CYCLE_B', 'CYCLE_A')]:
        authored('table', name, {'relation_type': 0, 'sql_security': None,
            'publication_enabled': False, 'columns': [column('ID', 0, True), column('OTHER_ID', 1)],
            'constraints': [{'name': name + '_PK', 'constraint_type': 'PRIMARY KEY', 'index_name': name + '_PK_I'},
                {'name': name + '_FK', 'constraint_type': 'FOREIGN KEY', 'index_name': name + '_FK_I',
                 'referenced_relation': other, 'referenced_index': other + '_PK_I',
                 'update_rule': 'CASCADE', 'delete_rule': 'SET NULL'}],
            'indexes': [index(name + '_PK_I', 'ID', True), index(name + '_FK_I', 'OTHER_ID', description='deferred index')]})
    cycle_receipt = apply(base, desired)
    with connection.cursor() as cursor:
        cursor.execute('INSERT INTO CYCLE_A VALUES (1, NULL)')
        cursor.execute('INSERT INTO CYCLE_B VALUES (2, 1)')
        cursor.execute('UPDATE CYCLE_A SET OTHER_ID=2 WHERE ID=1')
        cursor.execute('UPDATE CYCLE_B SET ID=3 WHERE ID=2')
        cursor.execute('SELECT OTHER_ID FROM CYCLE_A')
        assert cursor.fetchall() == [(3,)]
    connection.rollback()
    base = snapshot(); desired = deepcopy(base)
    late_parent = authored('table', 'LATE_BAD_PARENT', {'relation_type': 0, 'sql_security': None,
        'publication_enabled': False, 'columns': [column('ID', 0, True)],
        'constraints': [{'name': 'LATE_PK', 'constraint_type': 'PRIMARY KEY', 'index_name': 'LATE_PK_I'}],
        'indexes': [index('LATE_PK_I', 'ID', True)]})
    late_child = authored('table', 'LATE_BAD_CHILD', {'relation_type': 0, 'sql_security': None,
        'publication_enabled': False, 'columns': [{**column('REF_ID', 0), 'field_type': 35}],
        'constraints': [{'name': 'LATE_FK', 'constraint_type': 'FOREIGN KEY', 'index_name': 'LATE_FK_I',
            'referenced_relation': 'LATE_BAD_PARENT', 'referenced_index': 'LATE_PK_I',
            'update_rule': 'NO ACTION', 'delete_rule': 'NO ACTION'}],
        'indexes': [index('LATE_FK_I', 'REF_ID')]})
    desired['sha256'] = digest(desired['rows'])
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    late_failure = apply_review(provider, route, {'plan': plan, 'baseline': base, 'desired': desired})
    assert late_failure['native_rollback_returned'] and not late_failure['native_commit_returned'], late_failure
    assert late_failure['statements_completed'] >= 2, late_failure
    observed = snapshot()
    assert late_parent not in observed['rows'] and late_child not in observed['rows']
    base = snapshot(); desired = deepcopy(base)
    bad_domain = authored('domain', 'GRAPH_BAD_DOMAIN', domain_native)
    bad_table = authored('table', 'GRAPH_BAD_TABLE', {'relation_type': 0, 'sql_security': None,
        'publication_enabled': False, 'columns': [{**column('ID', 0), 'domain': 'GRAPH_BAD_DOMAIN', 'domain_not_null': 1}]})
    bad_view = authored('view', 'GRAPH_BAD_VIEW', {'relation_type': 1,
        'definition': 'SELECT UNKNOWN_FIELD FROM GRAPH_BAD_TABLE', 'columns': [{'name': 'ID', 'position': 0}],
        'creation_dependencies': [bad_table]})
    desired['sha256'] = digest(desired['rows'])
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    graph_failure = apply_review(provider, route, {'plan': plan, 'baseline': base, 'desired': desired})
    assert graph_failure['native_rollback_returned'] and not graph_failure['native_commit_returned'], graph_failure
    after = snapshot()
    assert all(identity not in after['rows'] for identity in (bad_domain, bad_table, bad_view))
    return {'passed': True, 'creation_graph': graph_receipt, 'cyclic_foreign_keys': cycle_receipt, 'deferred_constraint_failure': late_failure, 'creation_graph_failure': graph_failure, 'external_reference_and_not_null_trigger_collision': True, 'named_constraints_and_self_reference': True, 'identity_and_computed_values': [42, 43], 'native_failure': refused, 'native_kinds': [0, 4, 5], 'results': results}

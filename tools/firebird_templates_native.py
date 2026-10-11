"""Qualify object-context template SQL against a disposable native database."""
def qualify(connection):
    from pgadmin.cdeadmin.providers.firebird.provider import _resources
    from pgadmin.cdeadmin.workspace.firebird_templates import context, render, DEFAULTS
    with connection.cursor() as cursor:
        cursor.execute('CREATE TABLE TEMPLATE_NATIVE (ID BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, V INTEGER, C COMPUTED BY (V + 1))')
    connection.commit()
    rows = _resources(connection, {})
    selected = next(row for row in rows if row['resource_kind'] == 'table' and row['display_name'] == 'TEMPLATE_NATIVE')
    value = context({'generation': 'native', 'resources': rows}, selected['resource_id'])
    assert value['parameter_columns'] == ['V'], value
    connection.rollback()
    with connection.cursor() as cursor:
        for family, name in [('procedure', 'TEMPLATE_PROC'), ('trigger', 'TEMPLATE_TRIGGER'), ('execute-block', None)]:
            cursor.execute(render(value, DEFAULTS[family], name)['source'])
        cursor.execute(render(value, DEFAULTS['insert'])['source'], [41])
        cursor.execute(render(value, DEFAULTS['update'])['source'], [99])
        cursor.execute(render(value, DEFAULTS['delete'])['source'])
        cursor.execute(render(value, DEFAULTS['select'])['source'])
        result = cursor.fetchall()
        assert len(result) == 1 and result[0][1:] == (41, 42), result
    connection.rollback()
    with connection.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) FROM TEMPLATE_NATIVE')
        assert cursor.fetchone()[0] == 0
        cursor.execute("SELECT COUNT(*) FROM RDB$PROCEDURES WHERE RDB$PROCEDURE_NAME = 'TEMPLATE_PROC'")
        assert cursor.fetchone()[0] == 0
    connection.rollback()
    return {'passed': True, 'native_scaffolds': ['procedure', 'trigger', 'execute-block'],
            'identity_computed_excluded': True, 'safe_false_predicates': True, 'rollback_preserved': True}

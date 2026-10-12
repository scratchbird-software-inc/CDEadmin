"""Native export preserves executable boundaries and visible prerequisites."""
import pytest
from tools.cdeadmin_firebird_admin_mapping_gate import _create_client  # noqa: F401
from pgadmin.cdeadmin.workspace.firebird_sql_export import build_metadata, script, grant_statement


def row(name, kind='table', statements=None, **native):
    if statements is not None:
        native['recreation_statements'] = statements
    return {'resource_id': name, 'name': name, 'path': [name], 'kind': kind,
            'system': 'false', 'native': native}


def build(*rows):
    return build_metadata({'rows': {r['resource_id']: r for r in rows},
                           'provenance': {'coverage': 'visible-catalog'}})


def test_psql_and_literals_keep_whole_native_statements():
    definition = "CREATE PROCEDURE P AS BEGIN A = ';^'; /* ^ */ SUSPEND; END"
    text = script([definition, "COMMENT ON PROCEDURE P IS 'x;y'"])
    assert text.splitlines()[0] == 'SET AUTODDL OFF;'
    term = text.splitlines()[1].split()[2]
    assert term not in definition
    assert definition in text
    assert text.endswith('SET TERM ; ' + term + '\n')
    assert 'COMMIT' not in text and 'CONNECT' not in text


def test_creation_order_comments_owner_and_external_dependencies():
    domain = row('Z_DOMAIN', 'domain', ['CREATE DOMAIN Z_DOMAIN AS INT'])
    table = row('A_TABLE', statements=['CREATE TABLE A_TABLE (V Z_DOMAIN)',
        "COMMENT ON TABLE A_TABLE IS 'owner''s table'"], owner='ALICE',
        columns=[{'name': 'V', 'domain': 'Z_DOMAIN'}])
    view = row('V', 'view', definition='SELECT V FROM A_TABLE', relation_type=1,
        columns=[{'name': 'V', 'position': 0}],
        dependencies=[{'object_name': 'A_TABLE', 'object_type_code': 0}])
    result = build(view, table, domain)
    assert not result['blockers']
    assert result['objects'] == ['Z_DOMAIN', 'A_TABLE', 'V']
    assert 'CREATE VIEW "V" ("V") AS' in result['download_text']
    assert result['ownership_requirements'] == [{'resource_id': 'A_TABLE', 'execute_as_user': 'ALICE'}]
    branch = build(view)
    assert branch['external_prerequisites'] == [{'resource_id': 'V', 'name': 'A_TABLE', 'kinds': ['table', 'view']}]


def test_unknown_ddl_or_cycle_never_yields_partial_script():
    a = row('A', statements=['CREATE TABLE A (V INT)'],
            dependencies=[{'object_name': 'B', 'object_type_code': 0}])
    b = row('B', statements=['CREATE TABLE B (V INT)'],
            dependencies=[{'object_name': 'A', 'object_type_code': 0}])
    result = build(a, b)
    assert len(result['blockers']) == 2 and result['download_text'] is None
    result = build(a, row('B'))
    assert result['download_text'] is None and result['blockers'][0]['resource_id'] == 'B'


def grant(**changes):
    return dict({'privilege': 'U', 'object_type': 0, 'object_name': 'A',
                 'field': 'C', 'user_type': 8, 'grantee': 'BOB',
                 'grantor': 'ALICE', 'grant_option': 1,
                 'target_resolution': {'state': 'resolved'}}, **changes)


def test_grants_preserve_column_principal_grantor_and_option():
    assert grant_statement(grant()) == 'GRANT UPDATE ("C") ON TABLE "A" TO USER "BOB" WITH GRANT OPTION GRANTED BY USER "ALICE"'
    membership = grant_statement(grant(privilege='M', object_type=13,
        object_name='WRITERS', field=None, default_role=True, grant_option=2))
    assert membership == 'GRANT DEFAULT "WRITERS" TO USER "BOB" WITH ADMIN OPTION GRANTED BY USER "ALICE"'
    with pytest.raises(ValueError, match='uniquely'):
        grant_statement(grant(target_resolution={'state': 'ambiguous'}))
    result = build(row('A', statements=['CREATE TABLE A (C INT)'], privileges=[grant()]),
                   row('grant', 'privilege', **grant()))
    assert result['download_text'].count('GRANT UPDATE') == 1


def test_native_maintained_children_and_system_objects_not_duplicated():
    table = row('A', statements=['CREATE TABLE A (C INT PRIMARY KEY)'])
    constraint = row('PK', 'constraint', index_name='PK_INDEX'); constraint['path'] = ['A', 'PK']
    index = row('PK_INDEX', 'index')
    trigger = row('CHECK_TRIGGER', 'trigger', constraint_owner='PK')
    member = row('P', 'procedure', package='PACK')
    package = row('PACK', 'package', ['CREATE PACKAGE PACK AS BEGIN PROCEDURE P; END'])
    system = row('SYSTEM', statements=['DO NOT RECREATE']); system['system'] = 'true'
    result = build(table, constraint, index, trigger, member, package, system)
    assert not result['blockers']
    assert result['objects'] == ['A', 'PACK']


def test_invalid_grant_is_visible_and_disables_download():
    result = build(row('A', statements=['CREATE TABLE A (C INT)'],
                       privileges=[grant(privilege='INVALID')]))
    assert result['download_text'] is None
    assert result['blockers'][0]['reason'] == 'Unknown native object privilege'


def test_package_body_cycles_do_not_order_headers_as_a_cycle():
    a = row('A', 'package', ['CREATE PACKAGE A AS BEGIN FUNCTION F RETURNS INT; END',
        'CREATE PACKAGE BODY A AS BEGIN FUNCTION F RETURNS INT AS BEGIN RETURN B.F(); END END'],
        dependencies=[{'object_name': 'B', 'object_type_code': 18, 'dependent_type_code': 19}])
    b = row('B', 'package', ['CREATE PACKAGE B AS BEGIN FUNCTION F RETURNS INT; END',
        'CREATE PACKAGE BODY B AS BEGIN FUNCTION F RETURNS INT AS BEGIN RETURN A.F(); END END'],
        dependencies=[{'object_name': 'A', 'object_type_code': 18, 'dependent_type_code': 19}])
    result = build(a, b)
    assert not result['blockers'], result['blockers']
    source = result['download_text']
    assert source.index('CREATE PACKAGE B AS') < source.index('CREATE PACKAGE BODY A AS')
    for item in (a, b):
        item['native']['dependencies'][0]['dependent_type_code'] = 18
    assert build(a, b)['download_text'] is None


def test_foreign_key_cycles_use_native_stages_and_retain_outside_prerequisites():
    def table(name, parent):
        return row(name, statements=['full inspection rendering'],
            recreation_primary_statements=['CREATE TABLE ' + name + ' (ID INT PRIMARY KEY, P INT)'],
            recreation_deferred_statements=['ALTER TABLE ' + name + ' ADD FOREIGN KEY (P) REFERENCES ' + parent + '(ID)'],
            constraints=[{'constraint_type': 'FOREIGN KEY', 'referenced_relation': parent}])
    result = build(table('A', 'B'), table('B', 'A'))
    assert not result['blockers']
    text = result['download_text']
    assert text.index('CREATE TABLE B') < text.index('ALTER TABLE A')
    assert 'full inspection rendering' not in text
    branch = build(table('A', 'B'))
    assert branch['external_prerequisites'] == [{'resource_id': 'A', 'name': 'B', 'kinds': ['table']}]


@pytest.mark.parametrize('primary,deferred', [(None, []), ([], []), (['CREATE TABLE A (ID INT)'], []),
    (['CREATE TABLE A (ID INT)'], [None]), (['CREATE TABLE A (ID INT)'], 'ALTER TABLE')])
def test_incomplete_native_staged_tables_block(primary, deferred):
    result = build(row('A', statements=['old rendering'], recreation_primary_statements=primary,
        recreation_deferred_statements=deferred, constraints=[{'constraint_type': 'FOREIGN KEY', 'referenced_relation': 'B'}]))
    assert result['blockers'] and result['download_text'] is None

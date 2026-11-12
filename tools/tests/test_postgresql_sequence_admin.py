"""PostgreSQL sequence create/alter/drop compile to exact native
statements (M4)."""
import pytest
from pgadmin.cdeadmin.providers.postgresql.native_admin import (
    compile_native_admin, PostgreSQLNativeAdminError,
)
from pgadmin.cdeadmin.providers.postgresql.sequences import facts, form

NATIVE = {
    'schema': 'service', 'name': 'inspection_number', 'comment': None,
    'catalog_row': {'relname': 'inspection_number', 'relpersistence': 'p',
                    'relacl': ['app_owner=rwU/app_owner']},
    'children': {'pg_sequence': [{
        'seqstart': 5000, 'seqincrement': 1, 'seqmin': 1,
        'seqmax': 9223372036854775807, 'seqcache': 1, 'seqcycle': False}]},
}


def compile_sequence(operation, draft, native=NATIVE):
    return compile_native_admin({
        'resource_kind': 'sequence', 'operation_id': operation, 'draft': draft,
        'target_resource': {'extensions': {'postgresql': {'native': native}}}})


def statements(operation, draft, native=NATIVE):
    return compile_sequence(operation, draft, native)['statement'].split(';\n')


def test_facts_read_the_captured_row_and_child():
    assert facts(NATIVE) == {
        'schema': 'service', 'name': 'inspection_number', 'comment': None,
        'cycled': False, 'relpersistence': 'logged',
        'relacl': ['app_owner=rwU/app_owner'], 'increment': 1, 'start': 5000,
        'minimum': 1, 'maximum': 9223372036854775807, 'cache': 1}
    assert facts({})['name'] is None


def test_create_compiles_every_clause_in_native_order():
    from pglast import parse_sql
    text = compile_sequence('create', {
        'schema': 'Mixed schema', 'name': 'é seq', 'seqowner': 'app_owner',
        'comment': "it's", 'increment': 2, 'start': 10, 'minimum': 1,
        'maximum': 100, 'cache': 5, 'cycled': True,
        'relpersistence': 'unlogged', 'owned_table': 'assets',
        'owned_column': 'asset_id',
        'relacl': [{'grantee': 'reader', 'privileges': 'rU'},
                   {'grantee': 'public', 'privileges': ['r', 'w', 'U'],
                    'with_grant': True}],
        'securities': [{'provider': 'selinux', 'label': 'secret'}],
    })['statement']
    assert text.split(';\n') == [
        'CREATE UNLOGGED SEQUENCE "Mixed schema"."é seq" INCREMENT BY 2 '
        'START WITH 10 MINVALUE 1 MAXVALUE 100 CACHE 5 CYCLE',
        'ALTER SEQUENCE "Mixed schema"."é seq" OWNER TO "app_owner"',
        'ALTER SEQUENCE "Mixed schema"."é seq" OWNED BY '
        '"Mixed schema"."assets"."asset_id"',
        'COMMENT ON SEQUENCE "Mixed schema"."é seq" IS \'it\'\'s\'',
        'SECURITY LABEL FOR "selinux" ON SEQUENCE "Mixed schema"."é seq" '
        "IS 'secret'",
        'GRANT SELECT, USAGE ON SEQUENCE "Mixed schema"."é seq" TO "reader"',
        'GRANT ALL ON SEQUENCE "Mixed schema"."é seq" TO PUBLIC '
        'WITH GRANT OPTION']
    assert len(parse_sql(text)) == 7


def test_create_minimal_is_one_statement():
    assert statements('create', {'schema': 's', 'name': 'n',
                                 'relpersistence': 'logged', 'cycled': False,
                                 'minimum': None, 'no_maximum': True}) == [
        'CREATE SEQUENCE "s"."n" NO CYCLE']


def test_alter_emits_only_what_changed():
    assert statements('alter', {
        'name': 'inspection_number', 'schema': 'service', 'comment': None,
        'increment': 1, 'start': 5000, 'minimum': 1,
        'maximum': 9223372036854775807, 'cache': 1, 'cycled': False,
        'current_value': 7000, 'relpersistence': ''}) == [
        'SELECT pg_catalog.setval(\'"service"."inspection_number"\''
        '::regclass, 7000, false)']
    assert statements('alter', {
        'name': 'ticket_number', 'schema': 'archive', 'seqowner': 'dba',
        'comment': 'renamed', 'increment': 5, 'minimum': 1, 'no_minimum': True,
        'cycled': True,
        'relpersistence': 'unlogged', 'owned_by_none': True,
        'revoke': [{'grantee': 'app_owner'}],
        'relacl': [{'grantee': 'dba', 'privileges': 'rwU'}]}) == [
        'ALTER SEQUENCE "service"."inspection_number" RENAME TO '
        '"ticket_number"',
        'ALTER SEQUENCE "service"."ticket_number" OWNER TO "dba"',
        'ALTER SEQUENCE "service"."ticket_number" OWNED BY NONE',
        'ALTER SEQUENCE "service"."ticket_number" INCREMENT BY 5 '
        'NO MINVALUE CYCLE',
        'ALTER SEQUENCE "service"."ticket_number" SET UNLOGGED',
        'COMMENT ON SEQUENCE "service"."ticket_number" IS \'renamed\'',
        'REVOKE ALL ON SEQUENCE "service"."ticket_number" FROM "app_owner"',
        'GRANT ALL ON SEQUENCE "service"."ticket_number" TO "dba"',
        'ALTER SEQUENCE "service"."ticket_number" SET SCHEMA "archive"']


def test_alter_clears_a_comment_and_refuses_no_change():
    assert statements('alter', {'comment': ''}, dict(NATIVE, comment='x')) \
        == ['COMMENT ON SEQUENCE "service"."inspection_number" IS NULL']
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_sequence('alter', {'name': 'inspection_number'})


def test_drop_needs_the_typed_name():
    assert statements('drop', {'confirmation': 'inspection_number',
                               'cascade': True}) == [
        'DROP SEQUENCE "service"."inspection_number" CASCADE']
    assert statements('drop', {'confirmation': 'inspection_number'}) == [
        'DROP SEQUENCE "service"."inspection_number" RESTRICT']
    with pytest.raises(PostgreSQLNativeAdminError, match='confirmation'):
        compile_sequence('drop', {'confirmation': 'other'})


@pytest.mark.parametrize('operation, draft, message', [
    ('create', {'schema': 's', 'name': 'n', 'cache': 0}, 'cache is at least'),
    ('create', {'schema': 's', 'name': 'n', 'increment': 0}, 'not be zero'),
    ('create', {'schema': 's', 'name': 'n', 'start': 1.5}, 'whole number'),
    ('create', {'schema': 's', 'name': 'n', 'start': True}, 'whole number'),
    ('create', {'schema': 's', 'name': 'n', 'maximum': 2 ** 63}, 'bigint'),
    ('create', {'schema': 's', 'name': 'n', 'owned_table': 't'}, 'both'),
    ('create', {'schema': 's', 'name': 'n', 'relpersistence': 'temp'},
     'logged or unlogged'),
    ('create', {'schema': 's', 'name': 'n',
                'relacl': [{'grantee': 'r', 'privileges': 'x'}]}, 'privileges are among'),
    ('create', {'schema': 's', 'name': 'n', 'relacl': 'reader'}, 'list'),
    ('create', {'schema': 's', 'name': 'n; DROP TABLE t'},
     None),
    ('inspect', {}, 'stays with the provider tree'),
])
def test_refusals(operation, draft, message):
    if message is None:
        # A hostile name is quoted, never parsed as structure.
        from pglast import parse_sql
        text = compile_sequence(operation, draft)['statement']
        assert len(parse_sql(text)) == 1 and '"n; DROP TABLE t"' in text
        return
    with pytest.raises(PostgreSQLNativeAdminError, match=message):
        compile_sequence(operation, draft)


def test_forms_follow_the_inherited_field_ids():
    def field(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    create = {f['field_id']: f for f in form('create', field)['fields']}
    alter = {f['field_id']: f for f in form('alter', field)['fields']}
    drop = {f['field_id']: f for f in form('drop', field)['fields']}
    assert create['name']['required'] and create['schema']['required']
    assert 'current_value' not in create and 'revoke' not in create
    assert alter['start']['initial_value_path'] == ['sequence_facts', 'start']
    assert alter['cycled']['initial_value_path'] == [
        'sequence_facts', 'cycled']
    assert 'initial_value_path' not in alter['relacl']
    assert alter['owned_by_none']['control'] == 'boolean'
    assert drop['confirmation']['required'] and 'cascade' in drop
    assert create['relpersistence']['default'] == 'logged'
    assert 'default' not in alter['relpersistence']


def test_catalog_routes_sequence_lifecycle_to_the_provider():
    from pgadmin.cdeadmin.providers.postgresql.preserved_surface import (
        adapt_catalog)
    catalog = adapt_catalog({'objects': []})
    sequence = next(item for item in catalog['objects']
                    if item['resource_kind'] == 'sequence')
    routes = {op['operation_id']: op['execution_route']
              for op in sequence['operations']}
    assert routes == {'create': 'provider-native', 'alter': 'provider-native',
                      'drop': 'provider-native', 'inspect': 'legacy-preserved'}
    drop = next(op for op in sequence['operations']
                if op['operation_id'] == 'drop')
    assert drop['confirmation_required'] and drop['mutation_class'] == \
        'destructive'

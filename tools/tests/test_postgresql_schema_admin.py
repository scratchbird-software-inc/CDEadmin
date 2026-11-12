"""PostgreSQL schema create/alter/drop compile to exact native statements
(M4)."""
import pytest
from pgadmin.cdeadmin.providers.postgresql.native_admin import (
    compile_native_admin, PostgreSQLNativeAdminError,
)
from pgadmin.cdeadmin.providers.postgresql.schemas import facts, form

NATIVE = {'schema': 'service', 'name': 'service', 'comment': 'ops',
          'catalog_row': {'nspname': 'service', 'nspowner': '10',
                          'nspacl': ['app_owner=UC/app_owner']}}


def compile_schema(operation, draft, native=NATIVE):
    return compile_native_admin({
        'resource_kind': 'schema', 'operation_id': operation, 'draft': draft,
        'target_resource': {'extensions': {'postgresql': {'native': native}}}})


def statements(operation, draft, native=NATIVE):
    return compile_schema(operation, draft, native)['statement'].split(';\n')


def test_facts_read_the_captured_row():
    assert facts(NATIVE) == {'name': 'service', 'description': 'ops',
                             'nspacl': ['app_owner=UC/app_owner']}


def test_create_with_every_clause():
    from pglast import parse_sql
    text = compile_schema('create', {
        'name': 'Mixed schema', 'namespaceowner': 'app_owner',
        'description': "it's",
        'nspacl': [{'grantee': 'reader', 'privileges': 'U'},
                   {'grantee': 'public', 'privileges': 'U, C',
                    'with_grant': True}],
        'default_privileges': [
            {'object_type': 'tables', 'grantee': 'reader',
             'privileges': 'select, insert'},
            {'object_type': 'FUNCTIONS', 'grantee': 'public',
             'privileges': 'ALL'}],
        'seclabels': [{'provider': 'selinux', 'label': 'secret'}]})[
        'statement']
    assert text.split(';\n') == [
        'CREATE SCHEMA "Mixed schema" AUTHORIZATION "app_owner"',
        'COMMENT ON SCHEMA "Mixed schema" IS \'it\'\'s\'',
        'SECURITY LABEL FOR "selinux" ON SCHEMA "Mixed schema" IS \'secret\'',
        'GRANT USAGE ON SCHEMA "Mixed schema" TO "reader"',
        'GRANT ALL ON SCHEMA "Mixed schema" TO PUBLIC WITH GRANT OPTION',
        'ALTER DEFAULT PRIVILEGES IN SCHEMA "Mixed schema" GRANT SELECT, '
        'INSERT ON TABLES TO "reader"',
        'ALTER DEFAULT PRIVILEGES IN SCHEMA "Mixed schema" GRANT ALL ON '
        'FUNCTIONS TO PUBLIC']
    assert len(parse_sql(text)) == 7
    assert statements('create', {'name': 'plain'}) == ['CREATE SCHEMA "plain"']


def test_alter_emits_only_differences():
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_schema('alter', {'name': 'service', 'description': 'ops'})
    assert statements('alter', {
        'name': 'operations', 'namespaceowner': 'dba', 'description': '',
        'revoke': [{'grantee': 'app_owner'}],
        'nspacl': [{'grantee': 'dba', 'privileges': 'UC'}],
        'default_revoke': [{'object_type': 'sequences', 'grantee': 'public'}],
        'default_privileges': [{'object_type': 'types', 'grantee': 'dba',
                                'privileges': 'usage'}]}) == [
        'ALTER SCHEMA "service" RENAME TO "operations"',
        'ALTER SCHEMA "operations" OWNER TO "dba"',
        'COMMENT ON SCHEMA "operations" IS NULL',
        'REVOKE ALL ON SCHEMA "operations" FROM "app_owner"',
        'GRANT ALL ON SCHEMA "operations" TO "dba"',
        'ALTER DEFAULT PRIVILEGES IN SCHEMA "operations" REVOKE ALL ON '
        'SEQUENCES FROM PUBLIC',
        'ALTER DEFAULT PRIVILEGES IN SCHEMA "operations" GRANT USAGE ON '
        'TYPES TO "dba"']


def test_drop_needs_the_typed_name():
    assert statements('drop', {'confirmation': 'service', 'cascade': True}) \
        == ['DROP SCHEMA "service" CASCADE']
    assert statements('drop', {'confirmation': 'service'}) == [
        'DROP SCHEMA "service" RESTRICT']
    with pytest.raises(PostgreSQLNativeAdminError, match='confirmation'):
        compile_schema('drop', {'confirmation': 'other'})


@pytest.mark.parametrize('draft, message', [
    ({'name': 's', 'nspacl': [{'grantee': 'r', 'privileges': 'X'}]}, 'privileges are among'),
    ({'name': 's', 'default_privileges': [
        {'object_type': 'views', 'grantee': 'r', 'privileges': 'ALL'}]},
     'apply to'),
    ({'name': 's', 'default_privileges': [
        {'object_type': 'types', 'grantee': 'r', 'privileges': 'SELECT'}]},
     'among ALL'),
    ({'name': 's', 'nspacl': 'reader'}, 'list of rows'),
    ({'name': 's', 'seclabels': [{'label': 'x'}]}, 'provider'),
    ({'name': 's', 'namespaceowner': 'a"b; DROP'}, None),
])
def test_refusals_and_quoting(draft, message):
    if message is None:
        from pglast import parse_sql
        text = compile_schema('create', draft)['statement']
        assert len(parse_sql(text)) == 1 and 'AUTHORIZATION "a""b; DROP"' \
            in text
        return
    with pytest.raises(PostgreSQLNativeAdminError, match=message):
        compile_schema('create', draft)


def test_forms_and_catalog_route():
    def field(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    create = {f['field_id']: f for f in form('create', field)['fields']}
    alter = {f['field_id']: f for f in form('alter', field)['fields']}
    assert set(create) == {'name', 'namespaceowner', 'description', 'nspacl',
                           'default_privileges', 'seclabels'}
    assert set(alter) == set(create) | {'revoke', 'default_revoke'}
    assert alter['description']['initial_value_path'] == [
        'schema_facts', 'description']
    assert 'initial_value_path' not in alter['namespaceowner']
    from pgadmin.cdeadmin.providers.postgresql.preserved_surface import (
        adapt_catalog)
    catalog = adapt_catalog({'objects': []})
    schema = next(item for item in catalog['objects']
                  if item['resource_kind'] == 'schema')
    routes = {op['operation_id']: op['execution_route']
              for op in schema['operations']}
    # reindex (maintenance) was provider-native already.
    assert routes == {
        'create': 'provider-native', 'alter': 'provider-native',
        'drop': 'provider-native', 'inspect': 'legacy-preserved',
        'reindex': 'provider-native',
        # M6.2 (2026-11-11): schema-scope VACUUM and ANALYZE.
        'vacuum': 'provider-native', 'analyze': 'provider-native'}

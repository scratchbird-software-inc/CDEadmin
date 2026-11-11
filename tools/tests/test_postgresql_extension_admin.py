"""PostgreSQL extension create/alter/drop compile to exact native
statements (M4)."""
import pytest
from pgadmin.cdeadmin.providers.postgresql.native_admin import (
    compile_native_admin, PostgreSQLNativeAdminError,
)
from pgadmin.cdeadmin.providers.postgresql.extensions import facts, form

NATIVE = {'schema': 'public', 'name': 'pg_trgm', 'comment': 'trigrams',
          'catalog_row': {'extname': 'pg_trgm', 'extversion': '1.6',
                          'extrelocatable': True}}


def compile_extension(operation, draft, native=NATIVE):
    return compile_native_admin({
        'resource_kind': 'extension', 'operation_id': operation,
        'draft': draft,
        'target_resource': {'extensions': {'postgresql': {'native': native}}}})


def statements(operation, draft, native=NATIVE):
    return compile_extension(operation, draft, native)['statement'].split(
        ';\n')


def test_facts_read_the_captured_row():
    assert facts(NATIVE) == {'name': 'pg_trgm', 'schema': 'public',
                             'version': '1.6', 'relocatable': True,
                             'comment': 'trigrams'}


def test_create_with_every_clause():
    from pglast import parse_sql
    text = compile_extension('create', {
        'name': 'pg_trgm', 'schema': 'Ext schema', 'version': '1.6',
        'cascade': True, 'comment': "it's"})['statement']
    assert text.split(';\n') == [
        'CREATE EXTENSION "pg_trgm" WITH SCHEMA "Ext schema" VERSION "1.6" '
        'CASCADE',
        'COMMENT ON EXTENSION "pg_trgm" IS \'it\'\'s\'']
    assert len(parse_sql(text)) == 2
    assert statements('create', {'name': 'hstore', 'cascade': False}) == [
        'CREATE EXTENSION "hstore"']


def test_alter_emits_only_differences_and_respects_relocatability():
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_extension('alter', {'schema': 'public', 'version': '1.6',
                                    'comment': 'trigrams'})
    assert statements('alter', {'schema': 'tools', 'version': '1.7',
                                'comment': ''}) == [
        'ALTER EXTENSION "pg_trgm" UPDATE TO "1.7"',
        'ALTER EXTENSION "pg_trgm" SET SCHEMA "tools"',
        'COMMENT ON EXTENSION "pg_trgm" IS NULL']
    pinned = dict(NATIVE, catalog_row=dict(NATIVE['catalog_row'],
                                           extrelocatable=False))
    with pytest.raises(PostgreSQLNativeAdminError, match='not relocatable'):
        compile_extension('alter', {'schema': 'tools'}, pinned)


def test_drop_needs_the_typed_name():
    assert statements('drop', {'confirmation': 'pg_trgm', 'cascade': True}) \
        == ['DROP EXTENSION "pg_trgm" CASCADE']
    assert statements('drop', {'confirmation': 'pg_trgm'}) == [
        'DROP EXTENSION "pg_trgm" RESTRICT']
    with pytest.raises(PostgreSQLNativeAdminError, match='confirmation'):
        compile_extension('drop', {'confirmation': 'other'})


@pytest.mark.parametrize('draft, message', [
    ({'name': 'x', 'version': '1.0; DROP'}, 'version name'),
    ({'name': 'x', 'cascade': 'yes'}, 'boolean'),
    ({'name': ''}, 'not be empty'),
])
def test_create_refusals(draft, message):
    with pytest.raises(PostgreSQLNativeAdminError, match=message):
        compile_extension('create', draft)


def test_hostile_name_is_quoted_not_parsed():
    from pglast import parse_sql
    text = compile_extension('create', {'name': 'x; DROP TABLE t'})[
        'statement']
    assert len(parse_sql(text)) == 1 and '"x; DROP TABLE t"' in text


def test_forms_and_catalog_route():
    def field(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    create = {f['field_id'] for f in form('create', field)['fields']}
    assert create == {'name', 'schema', 'version', 'cascade', 'comment'}
    alter = {f['field_id']: f for f in form('alter', field)['fields']}
    assert set(alter) == {'schema', 'version', 'comment'}
    assert alter['version']['initial_value_path'] == [
        'extension_facts', 'version']
    from pgadmin.cdeadmin.providers.postgresql.preserved_surface import (
        adapt_catalog)
    catalog = adapt_catalog({'objects': []})
    extension = next(item for item in catalog['objects']
                     if item['resource_kind'] == 'extension')
    assert {op['operation_id']: op['execution_route']
            for op in extension['operations']} == {
        'create': 'provider-native', 'alter': 'provider-native',
        'drop': 'provider-native', 'inspect': 'legacy-preserved'}

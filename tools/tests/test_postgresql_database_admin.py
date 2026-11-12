"""PostgreSQL database create/alter compile to exact native statements
(M4)."""
import pytest
from pgadmin.cdeadmin.providers.postgresql.native_admin import (
    compile_native_admin, PostgreSQLNativeAdminError,
)
from pgadmin.cdeadmin.providers.postgresql.databases import facts, form

NATIVE = {'name': 'appdb', 'catalog_metadata': {
    'did': 10, 'name': 'appdb', 'spcname': 'pg_default',
    'datallowconn': True, 'is_template': False, 'owner': 10,
    'description': 'the app'}}


def compile_database(operation, draft, native=NATIVE):
    return compile_native_admin({
        'resource_kind': 'database', 'operation_id': operation,
        'draft': draft,
        'target_resource': {'extensions': {'postgresql': {'native': native}}}})


def test_facts_read_the_server_scope_row_or_the_captured_row():
    assert facts(NATIVE) == {
        'name': 'appdb', 'spcname': 'pg_default', 'datconnlimit': None,
        'is_template': False, 'datallowconn': True, 'comments': 'the app',
        'datacl': [], 'variables': []}
    captured = {'name': 'appdb', 'comment': None, 'catalog_row': {
        'datname': 'appdb', 'datconnlimit': 5, 'datistemplate': True,
        'datallowconn': False, 'datacl': ['=Tc/postgres']}}
    assert facts(captured) == {
        'name': 'appdb', 'spcname': None, 'datconnlimit': 5,
        'is_template': True, 'datallowconn': False, 'comments': None,
        'datacl': ['=Tc/postgres'], 'variables': []}


def test_create_is_one_autocommit_statement():
    from pglast import parse_sql
    compiled = compile_database('create', {
        'name': 'New db', 'datowner': 'app_owner', 'template': 'template0',
        'encoding': 'UTF8', 'datlocaleprovider': 'icu',
        'datcollate': 'C', 'datctype': 'C', 'daticulocale': 'en-US',
        'spcname': 'pg_default', 'datconnlimit': 20, 'datallowconn': True,
        'is_template': False})
    assert compiled == {
        'statement': 'CREATE DATABASE "New db" WITH OWNER = "app_owner" '
                     'TEMPLATE = "template0" ENCODING = \'UTF8\' '
                     "LOCALE_PROVIDER = icu LC_COLLATE = 'C' LC_CTYPE = 'C' "
                     "ICU_LOCALE = 'en-US' TABLESPACE = \"pg_default\" "
                     'CONNECTION LIMIT = 20 ALLOW_CONNECTIONS = true '
                     'IS_TEMPLATE = false',
        'read_only': False, 'autocommit': True}
    assert len(parse_sql(compiled['statement'])) == 1
    assert compile_database('create', {'name': 'plain'})['statement'] == \
        'CREATE DATABASE "plain"'


@pytest.mark.parametrize('draft, message', [
    ({'name': 'd', 'datlocaleprovider': 'icu'}, 'needs an ICU locale'),
    ({'name': 'd', 'daticulocale': 'en'}, 'needs the icu'),
    ({'name': 'd', 'datlocaleprovider': 'builtin'}, 'builtin locale'),
    ({'name': 'd', 'datlocaleprovider': 'glibc'}, 'locale provider is'),
    ({'name': 'd', 'encoding': "UTF8'; --"}, 'encoding name'),
    ({'name': 'd', 'datconnlimit': -2}, 'connection limit'),
    ({'name': 'd', 'datcollate': 'C; DROP'}, 'locale name'),
])
def test_create_refusals(draft, message):
    with pytest.raises(PostgreSQLNativeAdminError, match=message):
        compile_database('create', draft)


def test_alter_runs_in_one_transaction_except_the_tablespace():
    compiled = compile_database('alter', {
        'name': 'renamed', 'datowner': 'dba', 'datconnlimit': 3,
        'datallowconn': False, 'is_template': False, 'comments': '',
        'revoke': [{'grantee': 'public'}],
        'datacl': [{'grantee': 'dba', 'privileges': 'CTc',
                    'with_grant': True}]})
    assert compiled == {'statement': '\n'.join([
        'ALTER DATABASE "appdb" RENAME TO "renamed";',
        'ALTER DATABASE "renamed" OWNER TO "dba";',
        'ALTER DATABASE "renamed" CONNECTION LIMIT 3;',
        'ALTER DATABASE "renamed" WITH ALLOW_CONNECTIONS false;',
        'COMMENT ON DATABASE "renamed" IS NULL;',
        'REVOKE ALL ON DATABASE "renamed" FROM PUBLIC;',
        'GRANT ALL ON DATABASE "renamed" TO "dba" WITH GRANT OPTION']),
        'read_only': False}
    assert compile_database('alter', {'spcname': 'fast'}) == {
        'statement': 'ALTER DATABASE "appdb" SET TABLESPACE "fast"',
        'read_only': False, 'autocommit': True}
    with pytest.raises(PostgreSQLNativeAdminError, match='runs alone'):
        compile_database('alter', {'spcname': 'fast', 'comments': 'x'})
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_database('alter', {'name': 'appdb', 'spcname': 'pg_default',
                                   'comments': 'the app'})


def test_drop_is_native_with_force_and_inspect_stays_inherited():
    # M6 (2026-11-11): drop joined the editor, typed name, optional FORCE.
    assert compile_database('drop', {'confirmation': 'appdb'}) == {
        'statement': 'DROP DATABASE "appdb"', 'read_only': False,
        'autocommit': True}
    assert compile_database('drop', {'confirmation': 'appdb',
                                     'force': True})['statement'] == \
        'DROP DATABASE "appdb" WITH (FORCE)'
    with pytest.raises(PostgreSQLNativeAdminError, match='confirmation'):
        compile_database('drop', {'confirmation': 'other'})
    with pytest.raises(PostgreSQLNativeAdminError, match='provider tree'):
        compile_database('inspect', {})
    from pgadmin.cdeadmin.providers.postgresql.preserved_surface import (
        adapt_catalog)
    catalog = adapt_catalog({'objects': []})
    database = next(item for item in catalog['objects']
                    if item['resource_kind'] == 'database')
    routes = {op['operation_id']: op['execution_route']
              for op in database['operations']}
    assert routes['create'] == routes['alter'] == routes['drop'] == \
        'provider-native'
    assert routes['inspect'] == 'legacy-preserved'


def test_forms_follow_the_inherited_ids():
    def field(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    create = {f['field_id']: f for f in form('create', field)['fields']}
    alter = {f['field_id']: f for f in form('alter', field)['fields']}
    # Every family field id is admitted (owner direction 2026-11-11), so
    # the dialog's draft is never refused as unknown.
    import json, pathlib
    family = json.loads(pathlib.Path(
        'web/pgadmin/cdeadmin/ui_descriptors/postgresql/forms/'
        'database.form.json').read_text())
    for operation, served in (('create', create), ('alter', alter)):
        for item in family['fields']:
            if not item.get('modes') or operation in item['modes']:
                assert item['field_id'] in served, (operation, item['field_id'])
    assert create['name']['required'] and 'revoke' in alter
    assert alter['datconnlimit']['initial_value_path'] == [
        'database_facts', 'datconnlimit']
    assert create['daticulocale']['visible_when'] == {
        'field': 'datlocaleprovider', 'field_id': 'datlocaleprovider',
        'equals': 'icu'}


def test_provider_route_needs_no_database_for_database_changes():
    from pgadmin.cdeadmin.providers.postgresql.provider import (
        PostgreSQLProvider, PostgreSQLProviderError)
    route = PostgreSQLProvider._native_admin_route(
        {'resource_kind': 'database', '_provider_route': {'server_id': 7}})
    assert route == {'server_id': 7, 'database_id': None}
    with pytest.raises(PostgreSQLProviderError):
        PostgreSQLProvider._native_admin_route(
            {'resource_kind': 'schema', '_provider_route': {'server_id': 7}})


def test_strategy_follow_ups_and_hidden_locale_values_on_create():
    assert compile_database('create', {
        'name': 'd', 'datstrategy': 'file_copy', 'datlocaleprovider': 'libc',
        'datcollate': 'C', 'daticulocale': 'en'})['statement'] == (
        'CREATE DATABASE "d" WITH LOCALE_PROVIDER = libc '
        "LC_COLLATE = 'C' STRATEGY = file_copy")
    with pytest.raises(PostgreSQLNativeAdminError, match='runs alone'):
        compile_database('create', {'name': 'd', 'datacl': [
            {'grantee': 'r', 'privileges': ['CONNECT']}]})
    with pytest.raises(PostgreSQLNativeAdminError, match='browsing preference'):
        compile_database('create', {'name': 'd', 'schema_res': ['public']})
    with pytest.raises(PostgreSQLNativeAdminError, match='strategy is'):
        compile_database('create', {'name': 'd', 'datstrategy': 'copy'})


def test_alter_settings_labels_default_privileges_and_words():
    settings = dict(NATIVE, settings=[{'name': 'work_mem', 'value': '8MB'},
                                      {'name': 'search_path', 'value': 'app',
                                       'role': 'reporter'}])
    assert facts(settings)['variables'][1]['role'] == 'reporter'
    lines = compile_database('alter', {
        'datacl': [{'grantee': 'reader', 'privileges': ['CONNECT', 'temporary']}],
        'seclabels': [{'provider': 'selinux', 'label': 'x'}],
        'variables': [{'name': 'work_mem', 'value': '16MB'},
                      {'name': 'statement_timeout', 'value': ''}],
        'deftblacl': [{'grantee': 'reader', 'privileges': ['SELECT']}],
        'defseqacl': [{'grantee': 'reader', 'privileges': 'U'}]},
        settings)['statement'].split(';\n')
    assert lines == [
        'GRANT TEMPORARY, CONNECT ON DATABASE "appdb" TO "reader"',
        'SECURITY LABEL FOR "selinux" ON DATABASE "appdb" IS \'x\'',
        'ALTER DATABASE "appdb" SET work_mem TO \'16MB\'',
        'ALTER DATABASE "appdb" RESET statement_timeout',
        'ALTER ROLE "reporter" IN DATABASE "appdb" RESET search_path',
        'ALTER DEFAULT PRIVILEGES GRANT SELECT ON TABLES TO "reader"',
        'ALTER DEFAULT PRIVILEGES GRANT USAGE ON SEQUENCES TO "reader"']
    with pytest.raises(PostgreSQLNativeAdminError, match='rename it separately'):
        compile_database('alter', {'name': 'other', 'deftypeacl': [
            {'grantee': 'r', 'privileges': ['USAGE']}]})
    with pytest.raises(PostgreSQLNativeAdminError, match='privileges are among'):
        compile_database('alter', {'datacl': [{'grantee': 'r',
                                               'privileges': ['SELECT']}]})
    with pytest.raises(PostgreSQLNativeAdminError, match='parameter name'):
        compile_database('alter', {'variables': [{'name': 'x; drop',
                                                  'value': '1'}]})
    # A plan with default privileges attaches to the database itself.
    from pgadmin.cdeadmin.providers.postgresql.provider import (
        PostgreSQLProvider)
    request = {'resource_kind': 'database', 'operation_id': 'alter',
               '_provider_route': {'server_id': 7},
               'target_resource': {'extensions': {'postgresql': {
                   'native': NATIVE}}},
               'draft': {'deftblacl': [{'grantee': 'r', 'privileges': 'r'}]}}
    assert PostgreSQLProvider._native_admin_route(request) == {
        'server_id': 7, 'database_id': 10}
    request['draft'] = {'comments': 'x'}
    assert PostgreSQLProvider._native_admin_route(request) == {
        'server_id': 7, 'database_id': None}

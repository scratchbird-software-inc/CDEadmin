"""PostgreSQL role and tablespace create/alter/drop compile to exact
native statements (M4)."""
import pytest
from pgadmin.cdeadmin.providers.postgresql.cluster import (
    role_facts, role_form, tablespace_facts, tablespace_form,
)
from pgadmin.cdeadmin.providers.postgresql.native_admin import (
    compile_native_admin, PostgreSQLNativeAdminError,
)

ROLE = {'name': 'app_owner', 'catalog_metadata': {
    'rolname': 'app_owner', 'rolcanlogin': True, 'rolsuper': False,
    'description': 'owns'}}
TABLESPACE = {'name': 'fast', 'catalog_metadata': {
    'name': 'fast', 'owner': 10, 'description': None}}


def compile_kind(kind, operation, draft, native=None):
    native = dict(native or (ROLE if kind == 'role' else TABLESPACE))
    native['role_facts' if kind == 'role' else 'tablespace_facts'] = (
        role_facts if kind == 'role' else tablespace_facts)(native)
    return compile_native_admin({
        'resource_kind': kind, 'operation_id': operation, 'draft': draft,
        'target_resource': {'extensions': {'postgresql': {'native': native}}}})


def statements(kind, operation, draft, native=None):
    return compile_kind(kind, operation, draft, native)['statement'].split(
        ';\n')


def test_facts_read_the_server_scope_rows():
    assert role_facts(ROLE) == {'rolname': 'app_owner', 'rolcanlogin': True,
                                'rolsuper': False, 'description': 'owns'}
    full = role_facts({'name': 'r', 'catalog_metadata': {
        'rolname': 'r', 'rolcanlogin': False, 'rolsuper': True,
        'rolcreatedb': True, 'rolinherit': False, 'rolconnlimit': 3,
        'rolvaliduntil': None, 'comment': 'c'}})
    assert (full['rolcreatedb'], full['rolinherit'], full['rolconnlimit'],
            full['description']) == (True, False, 3, 'c')
    assert tablespace_facts(TABLESPACE) == {'name': 'fast',
                                            'description': None}


def test_role_create_with_every_clause_and_no_password():
    from pglast import parse_sql
    text = compile_kind('role', 'create', {
        'rolname': 'app user', 'rolcanlogin': True, 'rolsuper': False,
        'rolcreatedb': True, 'rolinherit': False, 'rolconnlimit': 5,
        'rolvaliduntil': '2030-01-01 00:00:00+00',
        'rolmembership': [{'role': 'readers', 'admin': True}],
        'rolmembers': [{'role': 'bob'}],
        'variables': [{'name': 'work_mem', 'value': '4MB'},
                      {'name': 'search_path', 'value': 'app',
                       'database': 'appdb'}],
        'description': "it's"})['statement']
    assert text.split(';\n') == [
        'CREATE ROLE "app user" WITH LOGIN NOSUPERUSER CREATEDB NOCREATEROLE '
        'NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 5 VALID UNTIL '
        "'2030-01-01 00:00:00+00'",
        'GRANT "readers" TO "app user" WITH ADMIN OPTION',
        'GRANT "app user" TO "bob"',
        "ALTER ROLE \"app user\" SET work_mem = '4MB'",
        'ALTER ROLE "app user" IN DATABASE "appdb" SET search_path = '
        "'app'",
        'COMMENT ON ROLE "app user" IS \'it\'\'s\'']
    assert len(parse_sql(text)) == 6
    with pytest.raises(PostgreSQLNativeAdminError, match='never carries a password'):
        compile_kind('role', 'create', {'rolname': 'x', 'rolpassword': 's3'})


def test_role_alter_emits_only_chosen_attributes():
    assert statements('role', 'alter', {
        'rolname': 'app_owner', 'rolcanlogin': '', 'rolsuper': 'no',
        'rolcreatedb': 'yes', 'rolconnlimit': 3, 'rolvaliduntil': 'infinity',
        'revoke_membership': [{'role': 'readers', 'admin_only': True}],
        'rolmembership': [{'role': 'writers'}],
        'revoke_members': [{'role': 'bob'}],
        'reset_variables': [{'name': 'work_mem'}],
        'variables': [{'name': 'statement_timeout', 'value': '5s'}],
        'description': ''}) == [
        'ALTER ROLE "app_owner" WITH CREATEDB CONNECTION LIMIT 3 VALID UNTIL '
        "'infinity'",
        'REVOKE ADMIN OPTION FOR "readers" FROM "app_owner"',
        'GRANT "writers" TO "app_owner"',
        'REVOKE "app_owner" FROM "bob"',
        'ALTER ROLE "app_owner" RESET work_mem',
        "ALTER ROLE \"app_owner\" SET statement_timeout = '5s'",
        'COMMENT ON ROLE "app_owner" IS NULL']
    assert statements('role', 'alter', {'rolname': 'owner', 'rolcanlogin':
                                        'yes'}) == [
        'ALTER ROLE "app_owner" RENAME TO "owner"']
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_kind('role', 'alter', {'rolname': 'app_owner'})
    with pytest.raises(PostgreSQLNativeAdminError, match='yes, no or empty'):
        compile_kind('role', 'alter', {'rolsuper': 'maybe'})
    with pytest.raises(PostgreSQLNativeAdminError, match='timestamp'):
        compile_kind('role', 'alter', {'rolvaliduntil': "x'; DROP"})
    assert statements('role', 'drop', {'confirmation': 'app_owner'}) == [
        'DROP ROLE "app_owner"']


def test_tablespace_lifecycle():
    assert compile_kind('tablespace', 'create', {
        'name': 'fast', 'spcuser': 'dba', 'spclocation': '/mnt/fast',
        'spcoptions': [{'name': 'random_page_cost', 'value': 1.1}]}) == {
        'statement': 'CREATE TABLESPACE "fast" OWNER "dba" LOCATION '
                     "'/mnt/fast' WITH (random_page_cost = 1.1)",
        'read_only': False, 'autocommit': True}
    with pytest.raises(PostgreSQLNativeAdminError, match='absolute'):
        compile_kind('tablespace', 'create', {'name': 't',
                                              'spclocation': 'relative'})
    with pytest.raises(PostgreSQLNativeAdminError, match='runs alone'):
        compile_kind('tablespace', 'create', {
            'name': 't', 'spclocation': '/x', 'description': 'c'})
    assert compile_kind('tablespace', 'alter', {
        'name': 'faster', 'spcuser': 'dba',
        'spcoptions': [{'name': 'seq_page_cost', 'value': '0.5'}],
        'reset_options': [{'name': 'random_page_cost'}],
        'revoke': [{'grantee': 'public'}],
        'spcacl': [{'grantee': 'app', 'with_grant': True}],
        'description': 'ssd'})['statement'] == '\n'.join([
            'ALTER TABLESPACE "fast" RENAME TO "faster";',
            'ALTER TABLESPACE "faster" OWNER TO "dba";',
            'ALTER TABLESPACE "faster" SET (seq_page_cost = 0.5);',
            'ALTER TABLESPACE "faster" RESET (random_page_cost);',
            'REVOKE ALL ON TABLESPACE "faster" FROM PUBLIC;',
            'GRANT CREATE ON TABLESPACE "faster" TO "app" WITH GRANT OPTION;',
            'COMMENT ON TABLESPACE "faster" IS \'ssd\''])
    with pytest.raises(PostgreSQLNativeAdminError, match='takes a number'):
        compile_kind('tablespace', 'alter', {'spcoptions': [
            {'name': 'seq_page_cost', 'value': 'x; drop'}]})
    assert compile_kind('tablespace', 'drop', {'confirmation': 'fast'}) == {
        'statement': 'DROP TABLESPACE "fast"', 'read_only': False,
        'autocommit': True}


def test_forms_routes_and_server_scope_route():
    def field(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    create = {f['field_id']: f for f in role_form('create', field)['fields']}
    alter = {f['field_id']: f for f in role_form('alter', field)['fields']}
    # Every family field id is admitted (owner direction 2026-11-11); the
    # password field exists only to be refused.
    import json, pathlib
    family = json.loads(pathlib.Path(
        'web/pgadmin/cdeadmin/ui_descriptors/postgresql/forms/'
        'role.form.json').read_text())
    for operation, served in (('create', create), ('alter', alter)):
        for item in family['fields']:
            if not item.get('modes') or operation in item['modes']:
                assert item['field_id'] in served, (operation, item['field_id'])
    assert create['rolinherit']['default'] is True
    assert alter['rolsuper']['control'] == 'boolean'
    assert {'revoke_membership', 'revoke_members', 'reset_variables'} <= set(
        alter)
    ts = {f['field_id']: f for f in tablespace_form('create', field)['fields']}
    assert ts['spclocation']['required']
    from pgadmin.cdeadmin.providers.postgresql.preserved_surface import (
        adapt_catalog)
    from pgadmin.cdeadmin.providers.postgresql.provider import (
        PostgreSQLProvider)
    catalog = adapt_catalog({'objects': []})
    for kind in ('role', 'tablespace'):
        resource = next(item for item in catalog['objects']
                        if item['resource_kind'] == kind)
        routes = {op['operation_id']: op['execution_route']
                  for op in resource['operations']}
        assert routes['create'] == routes['alter'] == routes['drop'] == \
            'provider-native', kind
        assert routes['inspect'] == 'legacy-preserved', kind
        assert PostgreSQLProvider._native_admin_route(
            {'resource_kind': kind, '_provider_route': {'server_id': 7}}) \
            == {'server_id': 7, 'database_id': None}


def test_role_family_shapes_inherit_set_labels_and_known_attributes():
    full = {'name': 'app_owner', 'catalog_metadata': {
        'rolname': 'app_owner', 'rolcanlogin': True, 'rolsuper': False,
        'rolcreatedb': True, 'rolinherit': True, 'rolconnlimit': 3,
        'rolvaliduntil': None, 'comment': None}}
    # Booleans equal to the known attributes are no change; the PostgreSQL
    # 16 membership options and a security label compile.
    assert statements('role', 'alter', {
        'rolcanlogin': True, 'rolcreatedb': False, 'rolconnlimit': 3,
        'rolmembership': [{'role': 'readers', 'admin': False,
                           'inherit': False, 'set': True}],
        'seclabels': [{'provider': 'selinux', 'label': 'x'}]}, full) == [
        'ALTER ROLE "app_owner" WITH NOCREATEDB',
        'GRANT "readers" TO "app_owner" WITH ADMIN FALSE, INHERIT FALSE, '
        'SET TRUE',
        'SECURITY LABEL FOR "selinux" ON ROLE "app_owner" IS \'x\'']
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_kind('role', 'alter', {'rolcanlogin': True, 'rolconnlimit': 3},
                     full)
    with pytest.raises(PostgreSQLNativeAdminError, match='never carries'):
        compile_kind('role', 'alter', {'rolpassword': 'x'}, full)

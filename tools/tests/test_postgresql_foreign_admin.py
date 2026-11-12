"""PostgreSQL foreign data wrapper, foreign server and user mapping
create/alter/drop compile to exact native statements (M5)."""
import pytest
from pgadmin.cdeadmin.providers.postgresql.foreign_objects import (
    FACTS, form, mapping_facts, server_facts, wrapper_facts,
)
from pgadmin.cdeadmin.providers.postgresql.native_admin import (
    compile_native_admin, PostgreSQLNativeAdminError,
)

WRAPPER = {'name': 'postgres_fdw', 'comment': None,
           'catalog_row': {'fdwname': 'postgres_fdw'}}
SERVER = {'name': 'remote', 'comment': 'far away',
          'catalog_row': {'srvname': 'remote', 'srvfdw': '57514',
                          'srvtype': 'pg', 'srvversion': '18'}}
MAPPING = {'name': 'app_owner / remote',
           'sql_identity': 'app_owner on server remote',
           'catalog_row': {'options_redacted': True}}
NATIVES = {'foreign-data-wrapper': WRAPPER, 'foreign-server': SERVER,
           'user-mapping': MAPPING}


def compile_kind(kind, operation, draft, native=None):
    native = dict(native or NATIVES[kind])
    key, reader = FACTS[kind]
    native[key] = reader(native, {57514: 'postgres_fdw'}) if kind == \
        'foreign-server' else reader(native)
    return compile_native_admin({
        'resource_kind': kind, 'operation_id': operation, 'draft': draft,
        'target_resource': {'extensions': {'postgresql': {'native': native}}}})


def statements(kind, operation, draft, native=None):
    return compile_kind(kind, operation, draft, native)['statement'].split(
        ';\n')


def test_facts_resolve_the_wrapper_and_the_mapping_identity():
    assert wrapper_facts(WRAPPER) == {'name': 'postgres_fdw',
                                      'description': None}
    assert server_facts(SERVER, {57514: 'postgres_fdw'}) == {
        'name': 'remote', 'fdwname': 'postgres_fdw', 'fsrvtype': 'pg',
        'fsrvversion': '18', 'description': 'far away'}
    assert mapping_facts(MAPPING) == {'name': 'app_owner', 'server': 'remote',
                                      'display_name': 'app_owner / remote'}


def test_wrapper_lifecycle():
    assert statements('foreign-data-wrapper', 'create', {
        'name': 'my fdw', 'fdwhan': 'public.handler',
        'fdwvalue': 'public.validator',
        'fdwoptions': [{'name': 'debug', 'value': "it's"}],
        'fdwowner': 'dba', 'description': 'c'}) == [
        'CREATE FOREIGN DATA WRAPPER "my fdw" HANDLER public.handler '
        "VALIDATOR public.validator OPTIONS (\"debug\" 'it''s')",
        'ALTER FOREIGN DATA WRAPPER "my fdw" OWNER TO "dba"',
        'COMMENT ON FOREIGN DATA WRAPPER "my fdw" IS \'c\'']
    assert statements('foreign-data-wrapper', 'alter', {
        'name': 'pg_fdw', 'fdwowner': 'dba', 'no_handler': True,
        'fdwvalue': 'public.v',
        'add_options': [{'name': 'a', 'value': '1'}],
        'set_options': [{'name': 'b', 'value': '2'}],
        'drop_options': [{'name': 'c'}], 'description': 'd'}) == [
        'ALTER FOREIGN DATA WRAPPER "postgres_fdw" RENAME TO "pg_fdw"',
        'ALTER FOREIGN DATA WRAPPER "pg_fdw" OWNER TO "dba"',
        'ALTER FOREIGN DATA WRAPPER "pg_fdw" NO HANDLER VALIDATOR public.v '
        "OPTIONS (ADD \"a\" '1', SET \"b\" '2', DROP \"c\")",
        'COMMENT ON FOREIGN DATA WRAPPER "pg_fdw" IS \'d\'']
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_kind('foreign-data-wrapper', 'alter', {'name': 'postgres_fdw'})
    assert statements('foreign-data-wrapper', 'drop', {
        'confirmation': 'postgres_fdw', 'cascade': True}) == [
        'DROP FOREIGN DATA WRAPPER "postgres_fdw" CASCADE']


def test_server_lifecycle():
    assert statements('foreign-server', 'create', {
        'name': 'remote', 'fdwname': 'postgres_fdw', 'fsrvtype': 'pg',
        'fsrvversion': '18',
        'fsrvoptions': [{'name': 'host', 'value': '10.0.0.9'},
                        {'name': 'dbname', 'value': 'app'}],
        'fsrvowner': 'dba', 'description': 'c'}) == [
        "CREATE SERVER \"remote\" TYPE 'pg' VERSION '18' FOREIGN DATA WRAPPER "
        "\"postgres_fdw\" OPTIONS (\"host\" '10.0.0.9', \"dbname\" 'app')",
        'ALTER SERVER "remote" OWNER TO "dba"',
        'COMMENT ON SERVER "remote" IS \'c\'']
    assert statements('foreign-server', 'alter', {
        'name': 'remote2', 'fsrvversion': '19',
        'set_options': [{'name': 'host', 'value': '10.0.0.10'}],
        'drop_options': [{'name': 'dbname'}], 'description': ''}) == [
        'ALTER SERVER "remote" RENAME TO "remote2"',
        "ALTER SERVER \"remote2\" VERSION '19' OPTIONS (SET \"host\" "
        "'10.0.0.10', DROP \"dbname\")",
        'COMMENT ON SERVER "remote2" IS NULL']
    with pytest.raises(PostgreSQLNativeAdminError, match='fixed once'):
        compile_kind('foreign-server', 'alter', {'fdwname': 'other'})
    assert statements('foreign-server', 'drop', {'confirmation': 'remote'}) \
        == ['DROP SERVER "remote" RESTRICT']


def test_mapping_lifecycle_and_secret_options():
    assert statements('user-mapping', 'create', {
        'name': 'public', 'server': 'remote',
        'umoptions': [{'name': 'user', 'value': 'reader'}]}) == [
        'CREATE USER MAPPING FOR PUBLIC SERVER "remote" OPTIONS ("user" '
        "'reader')"]
    assert statements('user-mapping', 'alter', {
        'set_options': [{'name': 'user', 'value': 'writer'}]}) == [
        'ALTER USER MAPPING FOR "app_owner" SERVER "remote" OPTIONS (SET '
        "\"user\" 'writer')"]
    for kind, operation, draft in (
            ('user-mapping', 'create', {'name': 'a', 'server': 's',
                                        'umoptions': [{'name': 'password',
                                                       'value': 'x'}]}),
            ('foreign-server', 'alter', {'add_options': [
                {'name': 'passfile', 'value': '/x'}]}),
            ('foreign-data-wrapper', 'create', {'name': 'w', 'fdwoptions': [
                {'name': 'sslkey', 'value': 'k'}]})):
        with pytest.raises(PostgreSQLNativeAdminError, match='credential'):
            compile_kind(kind, operation, draft)
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_kind('user-mapping', 'alter', {})
    assert statements('user-mapping', 'drop', {
        'confirmation': 'app_owner / remote'}) == [
        'DROP USER MAPPING FOR "app_owner" SERVER "remote"']
    with pytest.raises(PostgreSQLNativeAdminError, match='confirmation'):
        compile_kind('user-mapping', 'drop', {'confirmation': 'other'})


def test_forms_and_routes():
    def field(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    server = {f['field_id']: f
              for f in form('foreign-server', 'alter', field)['fields']}
    assert server['fdwname']['initial_value_path'] == ['server_facts',
                                                       'fdwname']
    assert {'add_options', 'set_options', 'drop_options'} <= set(server)
    mapping = {f['field_id'] for f in form('user-mapping', 'create', field)[
        'fields']}
    assert mapping == {'name', 'server', 'umoptions'}
    from pgadmin.cdeadmin.providers.postgresql.preserved_surface import (
        adapt_catalog)
    catalog = adapt_catalog({'objects': []})
    for kind in ('foreign-data-wrapper', 'foreign-server', 'user-mapping'):
        resource = next(item for item in catalog['objects']
                        if item['resource_kind'] == kind)
        routes = {op['operation_id']: op['execution_route']
                  for op in resource['operations']}
        assert routes['create'] == routes['alter'] == routes['drop'] == \
            'provider-native', kind
        assert routes['inspect'] == 'legacy-preserved', kind

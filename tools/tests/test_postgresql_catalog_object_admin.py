"""PostgreSQL cast, collation and language create/alter/drop compile to
exact native statements (M5)."""
import pytest
from pgadmin.cdeadmin.providers.postgresql.catalog_objects import (
    FACTS, cast_facts, collation_facts, form, language_facts,
)
from pgadmin.cdeadmin.providers.postgresql.native_admin import (
    compile_native_admin, PostgreSQLNativeAdminError,
)

CAST = {'name': 'bigint AS smallint', 'comment': None,
        'sql_identity': '(bigint AS smallint)',
        'catalog_row': {'castcontext': 'a', 'castmethod': 'f'}}
COLLATION = {'schema': 'service', 'name': 'c_coll', 'comment': None,
             'catalog_row': {'collname': 'c_coll', 'collprovider': 'i',
                             'colllocale': 'en-US', 'collcollate': None,
                             'collctype': None, 'collisdeterministic': False,
                             'collicurules': None, 'collversion': '153.128'}}
LANGUAGE = {'name': 'plpgsql', 'comment': 'PL/pgSQL',
            'catalog_row': {'lanname': 'plpgsql', 'lanpltrusted': True,
                            'lanispl': True}}
NATIVES = {'cast': CAST, 'collation': COLLATION, 'language': LANGUAGE}


def compile_kind(kind, operation, draft, native=None):
    native = dict(native or NATIVES[kind])
    key, reader = FACTS[kind]
    native[key] = reader(native)
    return compile_native_admin({
        'resource_kind': kind, 'operation_id': operation, 'draft': draft,
        'target_resource': {'extensions': {'postgresql': {'native': native}}}})


def statements(kind, operation, draft, native=None):
    return compile_kind(kind, operation, draft, native)['statement'].split(
        ';\n')


def test_facts_read_the_captured_rows():
    assert cast_facts(CAST) == {'name': 'bigint AS smallint',
                                'srctyp': 'bigint', 'trgtyp': 'smallint',
                                'castcontext': 'assignment',
                                'castmethod': 'function',
                                'description': None}
    assert collation_facts(COLLATION)['provider'] == 'icu'
    assert collation_facts(COLLATION)['is_deterministic'] is False
    assert language_facts(LANGUAGE) == {'name': 'plpgsql', 'trusted': True,
                                        'is_procedural': True,
                                        'description': 'PL/pgSQL'}


def test_cast_lifecycle():
    from pglast import parse_sql
    text = compile_kind('cast', 'create', {
        'srctyp': 'text', 'trgtyp': 'integer', 'castmethod': 'function',
        'proname': 'service.to_int(text)', 'castcontext': 'assignment',
        'description': "it's"})['statement']
    assert text.split(';\n') == [
        'CREATE CAST (text AS integer) WITH FUNCTION service.to_int (text) '
        'AS ASSIGNMENT',
        'COMMENT ON CAST (text AS integer) IS \'it\'\'s\'']
    assert len(parse_sql(text)) == 2
    assert statements('cast', 'create', {
        'srctyp': 'varchar', 'trgtyp': 'text', 'castmethod': 'binary',
        'castcontext': 'implicit'}) == [
        'CREATE CAST (varchar AS text) WITHOUT FUNCTION AS IMPLICIT']
    assert statements('cast', 'create', {
        'srctyp': 'a', 'trgtyp': 'b', 'castmethod': 'inout'}) == [
        'CREATE CAST (a AS b) WITH INOUT']
    # The preserved surface admits no cast alter, so neither does the provider.
    with pytest.raises(PostgreSQLNativeAdminError):
        compile_kind('cast', 'alter', {'description': 'narrow'})
    with pytest.raises(PostgreSQLNativeAdminError, match='argument types'):
        compile_kind('cast', 'create', {'srctyp': 'a', 'trgtyp': 'b',
                                        'proname': 'f'})
    assert statements('cast', 'drop', {'confirmation': 'bigint AS smallint',
                                       'cascade': True}) == [
        'DROP CAST (bigint AS smallint) CASCADE']


def test_collation_lifecycle():
    assert statements('collation', 'create', {
        'name': 'c one', 'schema': 'Sch ema', 'provider': 'icu',
        'locale': 'en-US', 'is_deterministic': False,
        'rules': '&a < b', 'owner': 'dba', 'description': 'c'}) == [
        'CREATE COLLATION "Sch ema"."c one" (LOCALE = \'en-US\', PROVIDER = '
        "icu, DETERMINISTIC = false, RULES = '&a < b')",
        'ALTER COLLATION "Sch ema"."c one" OWNER TO "dba"',
        'COMMENT ON COLLATION "Sch ema"."c one" IS \'c\'']
    assert statements('collation', 'create', {
        'name': 'c', 'schema': 's', 'lc_collate': 'C', 'lc_type': 'C',
        'provider': 'libc', 'is_deterministic': True}) == [
        "CREATE COLLATION \"s\".\"c\" (LC_COLLATE = 'C', LC_CTYPE = 'C', "
        'PROVIDER = libc, DETERMINISTIC = true)']
    assert statements('collation', 'create', {
        'name': 'c', 'schema': 's', 'copy_collation': 'pg_catalog."C"'}) == [
        'CREATE COLLATION "s"."c" FROM pg_catalog."C"']
    with pytest.raises(PostgreSQLNativeAdminError, match='go together'):
        compile_kind('collation', 'create', {'name': 'c', 'schema': 's',
                                             'lc_collate': 'C'})
    assert statements('collation', 'alter', {
        'name': 'c_two', 'schema': 'archive', 'owner': 'dba',
        'refresh_version': True, 'description': 'd',
        'locale': 'en-US', 'provider': 'icu', 'is_deterministic': False}) == [
        'ALTER COLLATION "service"."c_coll" REFRESH VERSION',
        'ALTER COLLATION "service"."c_coll" OWNER TO "dba"',
        'COMMENT ON COLLATION "service"."c_coll" IS \'d\'',
        'ALTER COLLATION "service"."c_coll" RENAME TO "c_two"',
        'ALTER COLLATION "service"."c_two" SET SCHEMA "archive"']
    # A changed locale drops and recreates with the merged definition.
    assert statements('collation', 'alter', {'locale': 'de-DE',
                                             'is_deterministic': False}) == [
        'DROP COLLATION "service"."c_coll"',
        'CREATE COLLATION "service"."c_coll" (LOCALE = \'de-DE\', PROVIDER = '
        "icu, DETERMINISTIC = false, VERSION = '153.128')"]
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_kind('collation', 'alter', {'name': 'c_coll'})
    assert statements('collation', 'drop', {'confirmation': 'c_coll'}) == [
        'DROP COLLATION "service"."c_coll" RESTRICT']


def test_language_lifecycle():
    assert statements('language', 'create', {
        'name': 'pl one', 'trusted': True, 'lanproc': 'plpgsql_call_handler',
        'laninl': 'plpgsql_inline_handler', 'lanval': 'plpgsql_validator',
        'lanowner': 'dba', 'description': 'c'}) == [
        'CREATE TRUSTED PROCEDURAL LANGUAGE "pl one" HANDLER '
        'plpgsql_call_handler INLINE plpgsql_inline_handler VALIDATOR '
        'plpgsql_validator',
        'ALTER LANGUAGE "pl one" OWNER TO "dba"',
        'COMMENT ON LANGUAGE "pl one" IS \'c\'']
    assert statements('language', 'create', {'name': 'plperl',
                                             'is_template': True}) == [
        'CREATE LANGUAGE "plperl"']
    with pytest.raises(PostgreSQLNativeAdminError, match='handler'):
        compile_kind('language', 'create', {'name': 'x'})
    assert statements('language', 'alter', {'lanowner': 'dba',
                                            'description': '',
                                            'name': 'plpgsql2'}) == [
        'ALTER LANGUAGE "plpgsql" OWNER TO "dba"',
        'COMMENT ON LANGUAGE "plpgsql" IS NULL',
        'ALTER LANGUAGE "plpgsql" RENAME TO "plpgsql2"']
    with pytest.raises(PostgreSQLNativeAdminError, match='fixed once'):
        compile_kind('language', 'alter', {'trusted': False})
    assert statements('language', 'drop', {'confirmation': 'plpgsql'}) == [
        'DROP LANGUAGE "plpgsql" RESTRICT']


def test_forms_and_routes():
    def field(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    cast = {f['field_id'] for f in form('cast', 'create', field)['fields']}
    assert cast == {'srctyp', 'trgtyp', 'castmethod', 'proname',
                    'castcontext', 'description'}
    collation = {f['field_id']: f
                 for f in form('collation', 'alter', field)['fields']}
    assert collation['locale']['initial_value_path'] == [
        'collation_facts', 'locale']
    language = {f['field_id'] for f in form('language', 'alter', field)[
        'fields']}
    assert 'lanproc' not in language
    from pgadmin.cdeadmin.providers.postgresql.preserved_surface import (
        adapt_catalog)
    catalog = adapt_catalog({'objects': []})
    for kind in ('cast', 'collation', 'language'):
        resource = next(item for item in catalog['objects']
                        if item['resource_kind'] == kind)
        routes = {op['operation_id']: op['execution_route']
                  for op in resource['operations']}
        assert routes['create'] == routes['drop'] == 'provider-native', kind
        assert routes['inspect'] == 'legacy-preserved', kind
        if kind == 'cast':
            assert 'alter' not in routes
        else:
            assert routes['alter'] == 'provider-native', kind

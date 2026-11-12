"""PostgreSQL function and procedure create/alter/drop compile to exact
native statements (M4)."""
import pytest
from pgadmin.cdeadmin.providers.postgresql.native_admin import (
    compile_native_admin, PostgreSQLNativeAdminError,
)
from pgadmin.cdeadmin.providers.postgresql.routines import facts, form

DEFINITION = (
    'CREATE OR REPLACE FUNCTION service.priority_label(value integer, '
    "OUT label text, VARIADIC tags text[] DEFAULT ARRAY['a'])\n"
    ' RETURNS text\n'
    ' LANGUAGE sql\n'
    ' IMMUTABLE STRICT PARALLEL SAFE COST 50\n'
    " SET search_path TO 'service', 'pg_temp'\n"
    " SET work_mem TO '4MB'\n"
    "AS $function$ SELECT CASE WHEN value >= 4 THEN 'urgent' ELSE 'normal' "
    'END $function$\n')
FUNCTION = {'schema': 'service', 'name': 'priority_label', 'comment': None,
            'definition': DEFINITION,
            'sql_identity': 'service.priority_label(integer,text[])',
            'catalog_row': {'proname': 'priority_label', 'prokind': 'f',
                            'provolatile': 'i', 'proisstrict': True,
                            'prosecdef': False, 'proleakproof': False,
                            'proparallel': 's', 'procost': 50,
                            'prorows': 0}}
PROCEDURE = {'schema': 'service', 'name': 'bump', 'comment': 'adds one',
             'definition': 'CREATE OR REPLACE PROCEDURE service.bump(INOUT x '
                           'integer)\n LANGUAGE plpgsql\nAS $procedure$ '
                           'begin x := x + 1; end $procedure$\n',
             'sql_identity': 'service.bump(integer)',
             'catalog_row': {'proname': 'bump', 'prokind': 'p'}}


def compile_kind(kind, operation, draft, native):
    native = dict(native, routine_facts=facts(native))
    return compile_native_admin({
        'resource_kind': kind, 'operation_id': operation, 'draft': draft,
        'target_resource': {'extensions': {'postgresql': {'native': native}}}})


def statements(kind, operation, draft, native=None):
    native = native or (FUNCTION if kind == 'function' else PROCEDURE)
    return compile_kind(kind, operation, draft, native)['statement'].split(
        ';\n')


def test_facts_read_the_definition_back_through_the_parser():
    current = facts(FUNCTION)
    assert current['definition_parsed'] is True
    assert current['arguments'] == [
        {'argmode': 'IN', 'argname': 'value', 'argtype': 'integer',
         'argdefval': None},
        {'argmode': 'OUT', 'argname': 'label', 'argtype': 'text',
         'argdefval': None},
        {'argmode': 'VARIADIC', 'argname': 'tags', 'argtype': 'text[]',
         'argdefval': "ARRAY['a']"}]
    assert (current['prorettypename'], current['lanname']) == ('text', 'sql')
    assert current['prosrc'].strip().startswith('SELECT CASE')
    assert current['variables'] == [
        {'name': 'search_path', 'value': 'service, pg_temp'},
        {'name': 'work_mem', 'value': '4MB'}]
    # The dialog's codes for volatility and parallel safety.
    assert (current['provolatile'], current['proisstrict'],
            current['proparallel'], current['procost']) == (
        'i', True, 's', 50)
    table = facts({'definition': 'CREATE FUNCTION t.g() RETURNS TABLE(a int, '
                                 "b text) LANGUAGE sql AS $$ select 1, 'x' $$",
                   'catalog_row': {}})
    assert table['prorettypename'] == 'TABLE("a" integer, "b" text)'
    assert facts({'definition': 'garbage', 'catalog_row': {}})[
        'definition_parsed'] is False


def test_function_create_with_every_clause():
    from pglast import parse_sql
    text = compile_kind('function', 'create', {
        'name': 'is big', 'pronamespace': 'Mixed schema',
        'arguments': [{'argmode': 'IN', 'argname': 'n', 'argtype': 'integer',
                       'argdefval': '0'},
                      {'argmode': 'OUT', 'argname': 'big', 'argtype': 'bool'}],
        'prorettypename': 'SETOF boolean', 'lanname': 'SQL',
        'prosrc': "SELECT n > 10 -- $BODY$ inside\n",
        'provolatile': 'stable', 'proisstrict': True, 'proleakproof': True,
        'prosecdef': True, 'proparallel': 'safe', 'procost': 10,
        'prorows': 5, 'variables': [{'name': 'search_path',
                                     'value': 'public, pg_temp'},
                                    {'name': 'work_mem', 'value': "4'MB"}],
        'funcowner': 'app_owner', 'description': "it's"}, FUNCTION)[
        'statement']
    assert text.split(';\n') == [
        'CREATE FUNCTION "Mixed schema"."is big"("n" integer DEFAULT 0, '
        'OUT "big" bool) RETURNS SETOF boolean LANGUAGE sql STABLE LEAKPROOF '
        'STRICT SECURITY DEFINER PARALLEL SAFE COST 10 ROWS 5 '
        "SET search_path = public, pg_temp SET work_mem = '4''MB' "
        'AS $BODY_$SELECT n > 10 -- $BODY$ inside\n$BODY_$',
        'ALTER FUNCTION "Mixed schema"."is big"(integer) OWNER TO '
        '"app_owner"',
        'COMMENT ON FUNCTION "Mixed schema"."is big"(integer) IS \'it\'\'s\'']
    assert len(parse_sql(text)) == 3


def test_procedure_create_and_table_returns():
    assert statements('procedure', 'create', {
        'name': 'bump', 'pronamespace': 's', 'lanname': 'plpgsql',
        'arguments': [{'argmode': 'INOUT', 'argname': 'x',
                       'argtype': 'int'}],
        'prosrc': 'begin x := x + 1; end', 'prosecdef': False}) == [
        'CREATE PROCEDURE "s"."bump"(INOUT "x" int) LANGUAGE plpgsql AS '
        '$BODY$begin x := x + 1; end$BODY$']
    assert statements('function', 'create', {
        'name': 'rows', 'pronamespace': 's', 'lanname': 'sql',
        'prorettypename': 'TABLE(a int, "B x" text)', 'prosrc': 'select 1',
        'provolatile': None, 'proparallel': None}) == [
        'CREATE FUNCTION "s"."rows"() RETURNS TABLE("a" int, "B x" text) '
        'LANGUAGE sql VOLATILE PARALLEL UNSAFE AS $BODY$select 1$BODY$']


@pytest.mark.parametrize('draft, message', [
    ({'lanname': 'c'}, 'object file'),
    ({'lanname': 'sql; drop'}, 'language name'),
    ({'prosrc': ''}, 'must not be empty'),
    ({'arguments': [{'argmode': 'TABLE', 'argtype': 'int'}]}, 'RETURNS TABLE'),
    ({'arguments': [{'argmode': 'IN', 'argtype': 'int; drop'}]}, 'type'),
    ({'arguments': [{'argmode': 'IN', 'argtype': 'int',
                     'argdefval': '1); drop'}]}, 'unsafe'),
    ({'variables': [{'name': 'search_path', 'value': 'a; drop'}]},
     'search_path'),
    ({'prorettypename': 'TABLE()'}, 'at least one column'),
    ({'provolatile': 'often'}, 'volatility'),
    ({'procost': -1}, 'cost'),
])
def test_create_refusals(draft, message):
    base = {'name': 'f', 'pronamespace': 's', 'lanname': 'sql',
            'prorettypename': 'int', 'prosrc': 'select 1'}
    with pytest.raises(PostgreSQLNativeAdminError, match=message):
        compile_kind('function', 'create', {**base, **draft}, FUNCTION)


def test_alter_replaces_the_body_with_the_fixed_signature():
    current = facts(FUNCTION)
    assert statements('function', 'alter', {
        'name': 'priority_label', 'pronamespace': 'service',
        'arguments': current['arguments'],
        'prorettypename': 'text', 'lanname': 'sql',
        'prosrc': "SELECT 'x'", 'provolatile': 'STABLE',
        'proisstrict': True, 'proleakproof': False, 'proparallel': 'SAFE',
        'procost': 50, 'prorows': 0, 'variables': current['variables'],
        'description': 'labels'}) == [
        'CREATE OR REPLACE FUNCTION "service"."priority_label"("value" '
        'integer, OUT "label" text, VARIADIC "tags" text[] DEFAULT '
        "ARRAY['a']) RETURNS text LANGUAGE sql STABLE STRICT PARALLEL SAFE "
        "COST 50 SET search_path = service, pg_temp SET work_mem = '4MB' "
        "AS $BODY$SELECT 'x'$BODY$",
        'COMMENT ON FUNCTION "service"."priority_label"(integer,text[]) IS '
        "'labels'"]
    assert statements('function', 'alter', {
        'name': 'label_of', 'pronamespace': 'archive',
        'funcowner': 'dba'}) == [
        'ALTER FUNCTION "service"."priority_label"(integer,text[]) OWNER TO '
        '"dba"',
        'ALTER FUNCTION "service"."priority_label"(integer,text[]) RENAME TO '
        '"label_of"',
        'ALTER FUNCTION "service"."label_of"(integer,text[]) SET SCHEMA '
        '"archive"']
    with pytest.raises(PostgreSQLNativeAdminError,
                       match='arguments are fixed'):
        compile_kind('function', 'alter', {'arguments': []}, FUNCTION)
    with pytest.raises(PostgreSQLNativeAdminError, match='return type'):
        compile_kind('function', 'alter', {'prorettypename': 'int'},
                     FUNCTION)
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_kind('function', 'alter', {'name': 'priority_label'},
                     FUNCTION)
    assert statements('procedure', 'alter', {'prosrc': 'begin end',
                                             'description': ''}) == [
        'CREATE OR REPLACE PROCEDURE "service"."bump"(INOUT "x" integer) '
        'LANGUAGE plpgsql AS $BODY$begin end$BODY$',
        'COMMENT ON PROCEDURE "service"."bump"(integer) IS NULL']


def test_drop_uses_the_catalog_identity():
    assert statements('function', 'drop', {'confirmation': 'priority_label',
                                           'cascade': True}) == [
        'DROP FUNCTION "service"."priority_label"(integer,text[]) CASCADE']
    assert statements('procedure', 'drop', {'confirmation': 'bump'}) == [
        'DROP PROCEDURE "service"."bump"(integer) RESTRICT']
    with pytest.raises(PostgreSQLNativeAdminError, match='confirmation'):
        compile_kind('function', 'drop', {'confirmation': 'x'}, FUNCTION)


def test_forms_and_routes():
    def field(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    function = {f['field_id']: f
                for f in form('function', 'alter', field)['fields']}
    procedure = {f['field_id']: f
                 for f in form('procedure', 'create', field)['fields']}
    assert function['prosrc']['initial_value_path'] == [
        'routine_facts', 'prosrc']
    # Every family field id is admitted (owner direction 2026-11-11).
    import json, pathlib
    family = json.loads(pathlib.Path(
        'web/pgadmin/cdeadmin/ui_descriptors/postgresql/forms/'
        'routine.form.json').read_text())
    for operation, served in (('alter', function), ('create', procedure)):
        for item in family['fields']:
            if not item.get('modes') or operation in item['modes']:
                assert item['field_id'] in served, (operation, item['field_id'])
    assert procedure['prorettypename']['required'] is False
    assert 'revoke' in function and 'revoke' not in procedure
    from pgadmin.cdeadmin.providers.postgresql.preserved_surface import (
        adapt_catalog)
    catalog = adapt_catalog({'objects': []})
    for kind in ('function', 'procedure'):
        resource = next(item for item in catalog['objects']
                        if item['resource_kind'] == kind)
        routes = {op['operation_id']: op['execution_route']
                  for op in resource['operations']}
        assert routes['create'] == routes['alter'] == routes['drop'] == \
            'provider-native', kind
        assert routes['inspect'] == 'legacy-preserved', kind


def test_family_codes_setof_window_support_c_and_extras():
    # Codes for volatility and parallel safety, SETOF through the flag,
    # SUPPORT, grants, labels and an extension dependency on create.
    lines = statements('function', 'create', {
        'name': 'f', 'pronamespace': 's', 'lanname': 'sql',
        'prorettypename': 'integer', 'proretset': True, 'prosrc': 'select 1',
        'provolatile': 's', 'proparallel': 'r', 'prosupportfunc': 'sup',
        'acl': [{'grantee': 'app', 'privileges': ['EXECUTE']}],
        'seclabels': [{'provider': 'selinux', 'label': 'x'}],
        'dependsonextensions': ['plpgsql']})
    assert lines == [
        'CREATE FUNCTION "s"."f"() RETURNS SETOF integer LANGUAGE sql STABLE '
        'PARALLEL RESTRICTED SUPPORT sup AS $BODY$select 1$BODY$',
        'GRANT EXECUTE ON FUNCTION "s"."f"() TO "app"',
        'SECURITY LABEL FOR "selinux" ON FUNCTION "s"."f"() IS \'x\'',
        'ALTER FUNCTION "s"."f"() DEPENDS ON EXTENSION "plpgsql"']
    # A C-language window function names its object file and symbol.
    assert statements('function', 'create', {
        'name': 'w', 'pronamespace': 's', 'lanname': 'c',
        'prorettypename': 'integer', 'proiswindow': True,
        'probin': '$libdir/mine', 'prosrc_c': 'my_window'}) == [
        'CREATE FUNCTION "s"."w"() RETURNS integer LANGUAGE c WINDOW VOLATILE '
        "PARALLEL UNSAFE AS '$libdir/mine', 'my_window'"]
    # Alter: the same codes as the facts are no change; revoke and grant.
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_kind('function', 'alter', {'provolatile': 'i',
                                           'proparallel': 's'}, FUNCTION)
    assert statements('function', 'alter', {
        'revoke': [{'grantee': 'public'}],
        'acl': [{'grantee': 'app', 'privileges': 'X', 'with_grant': True}]}) == [
        'REVOKE ALL ON FUNCTION "service"."priority_label"(integer,text[]) '
        'FROM PUBLIC',
        'GRANT EXECUTE ON FUNCTION "service"."priority_label"(integer,text[]) '
        'TO "app" WITH GRANT OPTION']
    with pytest.raises(PostgreSQLNativeAdminError, match='privileges are among'):
        compile_kind('function', 'alter', {'acl': [{'grantee': 'a',
                                                    'privileges': ['SELECT']}]},
                     FUNCTION)
    c_facts = facts({'definition': "CREATE FUNCTION s.w() RETURNS integer "
                                   "LANGUAGE c WINDOW AS '$libdir/mine', "
                                   "'my_window'", 'catalog_row': {}})
    assert (c_facts['probin'], c_facts['prosrc_c'], c_facts['proiswindow'],
            c_facts['prosrc']) == ('$libdir/mine', 'my_window', True, None)

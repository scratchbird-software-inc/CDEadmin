"""PostgreSQL object privileges (Decision 21): the compiler, and live GRANT/REVOKE round trips.

The structural tests always run. The live tests reuse the harness of
``test_ui_descriptor_operations_postgresql`` (a throwaway database on the server named by
``CDEADMIN_ROUNDTRIP_POSTGRESQL``) and read every effect back from the server's ACLs;
nothing is judged from the statement text alone.
"""
import json
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT / 'web'), str(ROOT / 'tools'), str(ROOT / 'tools/tests')):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from pgadmin.cdeadmin.providers.postgresql.native_admin import PostgreSQLNativeAdminError  # noqa: E402
from pgadmin.cdeadmin.providers.postgresql.privileges import OBJECTS, compile_operation  # noqa: E402
from test_ui_descriptor_operations_postgresql import (  # noqa: E402,F401
    DATABASE, SETTINGS, live, live_only, query, run)

U = uuid.uuid4().hex[:6]
READER, WRITER = f'sr_reader_{U}', f'sr_writer_{U}'


def draft(**values):
    return {'object_type': 'TABLE', 'schema': 'public', 'object': 't', 'privileges': [{'privilege': 'SELECT'}],
            'grantees': [{'role': 'app'}], **values}


# --- the compiler ---------------------------------------------------------------------------------

def test_grant_and_revoke_statements_quote_everything():
    grant = compile_operation('grant', {}, draft(object='we"ird', privileges=[
        {'privilege': 'SELECT', 'columns': 'a, b c'}, {'privilege': 'UPDATE'}],
        grantees=[{'role': 'app'}, {'role': 'PUBLIC'}], with_grant=True))
    assert grant['statement'] == ('GRANT SELECT ("a", "b c"), UPDATE ON TABLE "public"."we""ird" '
                                  'TO "app", PUBLIC WITH GRANT OPTION')
    revoke = compile_operation('revoke', {}, draft(privileges=[{'privilege': 'ALL'}], grant_option_only=True, cascade=True))
    assert revoke['statement'] == 'REVOKE GRANT OPTION FOR ALL PRIVILEGES ON TABLE "public"."t" FROM "app" CASCADE'
    assert compile_operation('revoke', {}, draft())['statement'].endswith('FROM "app" RESTRICT')


@pytest.mark.parametrize('bad,message', [
    ({'object_type': 'WARLOCK'}, 'object family'),
    ({'privileges': [{'privilege': 'EXECUTE'}]}, 'match the object family'),
    ({'privileges': [{'privilege': 'DELETE', 'columns': 'a'}]}, 'column list'),
    ({'privileges': [{'privilege': 'ALL'}, {'privilege': 'SELECT'}]}, 'ALL must be the only'),
    ({'privileges': [{'privilege': 'SELECT'}, {'privilege': 'SELECT'}]}, 'distinct'),
    ({'grantees': [{'role': 'a'}, {'role': 'a'}]}, 'distinct'),
    ({'grantees': []}, 'bounded'),
    ({'privileges': 'SELECT'}, 'bounded'),
    ({'cascade': True}, 'belong to revoke'),
    ({'object': ''}, 'must not be empty'),
])
def test_a_malformed_grant_is_refused_before_any_statement(bad, message):
    with pytest.raises(PostgreSQLNativeAdminError, match=message):
        compile_operation('grant', {}, draft(**bad))


def test_revoke_only_options_and_grant_only_options_do_not_mix():
    with pytest.raises(PostgreSQLNativeAdminError, match='belongs to grant'):
        compile_operation('revoke', {}, draft(with_grant=True))


def test_a_typed_confirmation_must_name_the_object_but_is_otherwise_accepted():
    ok = compile_operation('revoke', {}, draft(confirmation='t'))
    assert ok['statement'].startswith('REVOKE SELECT ON TABLE "public"."t" FROM')
    with pytest.raises(PostgreSQLNativeAdminError, match='confirmation does not match'):
        compile_operation('revoke', {}, draft(confirmation='other'))
    assert 'REVOKE' not in compile_operation('grant', {}, draft())['statement'][:6]


def test_only_a_function_family_takes_argument_types_and_only_plain_ones():
    ok = compile_operation('grant', {}, draft(object_type='FUNCTION', object='f', arguments='integer, "My Type"[]',
                                              privileges=[{'privilege': 'EXECUTE'}]))
    assert 'ON FUNCTION "public"."f"(integer, "My Type"[])' in ok['statement']
    for hostile in ('integer); DROP TABLE x; --', 'a"b', 'x/*', "x'y"):
        with pytest.raises(PostgreSQLNativeAdminError, match='plain type list'):
            compile_operation('grant', {}, draft(object_type='FUNCTION', object='f', arguments=hostile,
                                                  privileges=[{'privilege': 'EXECUTE'}]))


def test_bulk_grants_name_schemas_not_objects_and_take_no_columns():
    statement = compile_operation('grant', {}, {'object_type': 'ALL TABLES IN SCHEMA', 'schemas': [{'schema': 's'}],
                                                'privileges': [{'privilege': 'SELECT'}], 'grantees': [{'role': 'r'}]})
    assert statement['statement'] == 'GRANT SELECT ON ALL TABLES IN SCHEMA "s" TO "r"'
    assert 'observation_statement' not in statement
    with pytest.raises(PostgreSQLNativeAdminError, match='column list'):
        compile_operation('grant', {}, {'object_type': 'ALL TABLES IN SCHEMA', 'schemas': [{'schema': 's'}],
                                        'privileges': [{'privilege': 'SELECT', 'columns': 'a'}], 'grantees': [{'role': 'r'}]})


def test_maintain_needs_postgresql_17_and_a_large_object_is_an_oid():
    assert compile_operation('grant', {}, draft(privileges=[{'privilege': 'MAINTAIN'}]))['minimum_server_version'] == 170000
    with pytest.raises(PostgreSQLNativeAdminError, match='OID'):
        compile_operation('grant', {}, draft(object_type='LARGE OBJECT', object='12; DROP'))


def test_every_family_has_privileges_and_a_default_acl_code():
    for family, (words, code, _qualified) in OBJECTS.items():
        assert words and len(code) == 1, family


# --- live -----------------------------------------------------------------------------------------

def acl(sql):
    """The effective ACL of one object as (grantee, privilege, grantable) rows; NULL means the default."""
    return sorted(query(sql))


def table_acl(name, schema='public'):
    return acl(f"""SELECT CASE WHEN a.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END, a.privilege_type, a.is_grantable
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace,
        LATERAL aclexplode(COALESCE(c.relacl, acldefault('r', c.relowner))) a
        WHERE n.nspname = '{schema}' AND c.relname = '{name}'""")


def held(rows, role):
    return {(privilege, grantable) for grantee, privilege, grantable in rows if grantee == role}


@pytest.fixture
def roles(live):
    for role in (READER, WRITER):
        query(f'DROP ROLE IF EXISTS "{role}"', database=DATABASE)
        query(f'CREATE ROLE "{role}"', database=DATABASE)
    yield READER, WRITER
    for role in (READER, WRITER):
        query(f'DROP OWNED BY "{role}"', database=DATABASE)
        query(f'DROP ROLE IF EXISTS "{role}"', database=DATABASE)


def grant(live, operation, **values):
    return run(live, operation, {'schema': 'public', **values}, kind='privilege')


def test_database_and_tablespace_rows_get_their_stored_acl_without_inventing_one():
    """The inherited node queries do not select the ACL; it is read separately, and NULL stays the default."""
    from pgadmin.cdeadmin.providers.postgresql.cluster import parse_acl_items
    from pgadmin.cdeadmin.providers.postgresql.privileges import apply_default_acl
    from pgadmin.cdeadmin.providers.postgresql.provider import PostgreSQLCatalogSource

    class Connection:
        def __init__(self, rows):
            self.rows, self.sql = rows, []

        def execute_dict(self, sql, *_):
            self.sql.append(sql)
            return True, {'rows': self.rows}

    rows = [{'did': 5}, {'did': 6}, {'did': 7}]
    connection = Connection([{'oid': 5, 'acl': None}, {'oid': 6, 'acl': ['r1=c/own', '=Tc/own']}])
    out = PostgreSQLCatalogSource._with_acls(connection, rows, 'pg_database', 'did', 'datacl', 'datacl')
    assert out[0]['datacl'] is None and out[1]['datacl'] == ['r1=c/own', '=Tc/own']
    assert 'datacl' not in out[2]  # not read: no grants are claimed for it
    assert 'FROM pg_catalog.pg_database' in connection.sql[0] and 'datacl IS NULL' in connection.sql[0]
    codes = {'C': 'CREATE', 'T': 'TEMPORARY', 'c': 'CONNECT'}
    held = {(r['grantee'], r['privilege']) for r in parse_acl_items(out[1]['datacl'], codes)}
    assert held == {('r1', 'CONNECT'), ('PUBLIC', 'TEMPORARY'), ('PUBLIC', 'CONNECT')}
    native = {}
    apply_default_acl('database', native, {'datacl': None, 'datdba': 'own'}, 0)
    assert native['privileges_default'] is True
    assert ('PUBLIC', 'CONNECT') in {(r['grantee'], r['privilege']) for r in native['privileges']}
    # A failed read leaves the rows untouched instead of reporting an empty ACL.
    class Broken:
        def execute_dict(self, *_):
            raise RuntimeError('boom')
    untouched = [{'did': 5}]
    assert PostgreSQLCatalogSource._with_acls(Broken(), untouched, 'pg_database', 'did', 'datacl', 'datacl') == [{'did': 5}]


@live_only
def test_table_grant_with_grant_option_then_revoke_the_option_then_the_privilege(live, roles):
    reader, _ = roles
    query('CREATE TABLE public.sr_t (a int, b int, c int)', database=DATABASE)
    plan, outcome = grant(live, 'grant', object_type='TABLE', object='sr_t', grantees=[{'role': reader}],
                          privileges=[{'privilege': 'SELECT'}, {'privilege': 'INSERT'}], with_grant=True)
    assert held(table_acl('sr_t'), reader) == {('SELECT', True), ('INSERT', True)}
    # The in-transaction readback names the object's resulting ACL.
    observed = outcome['native_observation']['rows'][0]
    assert observed['catalog'] == 'pg_class' and any(reader in item for item in observed['acl'])
    grant(live, 'revoke', object_type='TABLE', object='sr_t', grantees=[{'role': reader}],
          privileges=[{'privilege': 'SELECT'}], grant_option_only=True)
    assert held(table_acl('sr_t'), reader) == {('SELECT', False), ('INSERT', True)}
    grant(live, 'revoke', object_type='TABLE', object='sr_t', grantees=[{'role': reader}],
          privileges=[{'privilege': 'ALL'}])
    assert held(table_acl('sr_t'), reader) == set()


@live_only
def test_column_privileges_live_in_attacl_and_the_readback_shows_them(live, roles):
    reader, _ = roles
    query('CREATE TABLE public.sr_cols (a int, b int, c int)', database=DATABASE)
    _, outcome = grant(live, 'grant', object_type='TABLE', object='sr_cols', grantees=[{'role': reader}],
                       privileges=[{'privilege': 'SELECT', 'columns': 'a, b'}, {'privilege': 'UPDATE', 'columns': 'c'}])
    columns = query("""SELECT a.attname, a.attacl::text FROM pg_attribute a WHERE a.attrelid = 'public.sr_cols'::regclass
        AND a.attacl IS NOT NULL ORDER BY a.attnum""", database=DATABASE)
    assert [name for name, _ in columns] == ['a', 'b', 'c']
    assert held(table_acl('sr_cols'), reader) == set()  # not table-wide
    shown = {item['column'] for item in outcome['native_observation']['rows'][0]['column_acls']}
    assert shown == {'a', 'b', 'c'}
    grant(live, 'revoke', object_type='TABLE', object='sr_cols', grantees=[{'role': reader}],
          privileges=[{'privilege': 'SELECT', 'columns': 'a, b'}, {'privilege': 'UPDATE', 'columns': 'c'}])
    assert query("SELECT count(*) FROM pg_attribute a WHERE a.attrelid = 'public.sr_cols'::regclass "
                 f"AND a.attacl::text LIKE '%{reader}%'", database=DATABASE)[0][0] == 0


@live_only
def test_a_new_function_is_executable_by_public_and_revoking_that_is_visible(live, roles):
    """NULL proacl means the default (PUBLIC EXECUTE), not 'no grants'; the readback shows the default."""
    reader, _ = roles
    query('CREATE FUNCTION public.sr_f(integer) RETURNS int LANGUAGE sql AS $$ SELECT 1 $$', database=DATABASE)
    query('CREATE FUNCTION public.sr_f(text) RETURNS int LANGUAGE sql AS $$ SELECT 2 $$', database=DATABASE)
    assert query("SELECT proacl IS NULL FROM pg_proc WHERE oid = 'public.sr_f(integer)'::regprocedure", database=DATABASE)[0][0]
    _, outcome = grant(live, 'revoke', object_type='FUNCTION', object='sr_f', arguments='integer',
                       grantees=[{'role': 'PUBLIC'}], privileges=[{'privilege': 'EXECUTE'}])
    row = outcome['native_observation']['rows'][0]
    assert row['catalog'] == 'pg_proc' and row['default_acl'] and any('=X/' in item for item in row['default_acl'])
    # Only the integer overload changed.
    assert not query("SELECT has_function_privilege('" + reader + "', 'public.sr_f(integer)', 'EXECUTE')", database=DATABASE)[0][0]
    assert query("SELECT has_function_privilege('" + reader + "', 'public.sr_f(text)', 'EXECUTE')", database=DATABASE)[0][0]
    grant(live, 'grant', object_type='FUNCTION', object='sr_f', arguments='integer',
          grantees=[{'role': reader}], privileges=[{'privilege': 'EXECUTE'}])
    assert query("SELECT has_function_privilege('" + reader + "', 'public.sr_f(integer)', 'EXECUTE')", database=DATABASE)[0][0]


@live_only
def test_other_families_sequence_schema_database_domain_type(live, roles):
    reader, _ = roles
    query('CREATE SEQUENCE public.sr_seq', database=DATABASE)
    query('CREATE DOMAIN public.sr_dom AS int', database=DATABASE)
    query("CREATE TYPE public.sr_enum AS ENUM ('a')", database=DATABASE)
    query('CREATE SCHEMA sr_sch', database=DATABASE)
    for object_type, name, schema, word, check in (
            ('SEQUENCE', 'sr_seq', 'public', 'USAGE', "has_sequence_privilege('{r}', 'public.sr_seq', 'USAGE')"),
            ('SCHEMA', 'sr_sch', None, 'CREATE', "has_schema_privilege('{r}', 'sr_sch', 'CREATE')"),
            ('DATABASE', DATABASE, None, 'CREATE', "has_database_privilege('{r}', '" + DATABASE + "', 'CREATE')"),
            ('DOMAIN', 'sr_dom', 'public', 'USAGE', "has_type_privilege('{r}', 'public.sr_dom', 'USAGE')"),
            ('TYPE', 'sr_enum', 'public', 'USAGE', "has_type_privilege('{r}', 'public.sr_enum', 'USAGE')")):
        values = {'object_type': object_type, 'object': name, 'grantees': [{'role': reader}], 'privileges': [{'privilege': word}]}
        if schema:
            values['schema'] = schema
        probe = f"SELECT {check.format(r=reader)}"
        before = query(probe, database=DATABASE)[0][0]
        assert run(live, 'grant', values, kind='privilege')
        assert query(probe, database=DATABASE)[0][0] is True, object_type
        run(live, 'revoke', values, kind='privilege')
        # DOMAIN and TYPE default to PUBLIC USAGE, so revoking from the role leaves what PUBLIC gives.
        if not before:
            assert query(probe, database=DATABASE)[0][0] is False, object_type


@live_only
def test_all_tables_in_schema_reaches_every_table_and_a_failed_revoke_changes_nothing(live, roles):
    reader, writer = roles
    query('CREATE SCHEMA sr_bulk', database=DATABASE)
    query('CREATE TABLE sr_bulk.a (x int)', database=DATABASE)
    query('CREATE TABLE sr_bulk.b (x int)', database=DATABASE)
    run(live, 'grant', {'object_type': 'ALL TABLES IN SCHEMA', 'schemas': [{'schema': 'sr_bulk'}],
                        'grantees': [{'role': reader}], 'privileges': [{'privilege': 'SELECT'}], 'with_grant': True}, kind='privilege')
    assert held(table_acl('a', 'sr_bulk'), reader) == {('SELECT', True)} == held(table_acl('b', 'sr_bulk'), reader)
    # reader re-grants to writer, so revoking reader's option under RESTRICT must fail and change nothing.
    query(f'GRANT USAGE ON SCHEMA sr_bulk TO "{reader}"', database=DATABASE)
    query(f'SET ROLE "{reader}"; GRANT SELECT ON sr_bulk.a TO "{writer}"', database=DATABASE)
    with pytest.raises(Exception):
        run(live, 'revoke', {'object_type': 'TABLE', 'schema': 'sr_bulk', 'object': 'a', 'grantees': [{'role': reader}],
                             'privileges': [{'privilege': 'SELECT'}]}, kind='privilege')
    assert held(table_acl('a', 'sr_bulk'), reader) == {('SELECT', True)}


@live_only
def test_a_hostile_object_name_is_one_quoted_identifier(live, roles):
    reader, _ = roles
    name = 'x"; DROP TABLE public.sr_victim; --'
    query('CREATE TABLE public.sr_victim (a int)', database=DATABASE)
    query('CREATE TABLE public."' + name.replace('"', '""') + '" (a int)', database=DATABASE)
    run(live, 'grant', {'object_type': 'TABLE', 'schema': 'public', 'object': name, 'grantees': [{'role': reader}],
                        'privileges': [{'privilege': 'SELECT'}]}, kind='privilege')
    assert query("SELECT to_regclass('public.sr_victim') IS NOT NULL", database=DATABASE)[0][0]
    assert held(table_acl(name), reader) == {('SELECT', False)}


# --- the listing's default ACL and column ACLs ----------------------------------------------------

from pgadmin.cdeadmin.providers.postgresql.privileges import (  # noqa: E402
    ACL_COLUMNS, DEFAULT_FAMILY, OBJECTS as _OBJECTS, apply_default_acl, default_acl)


def test_a_null_acl_becomes_the_default_and_is_flagged():
    native, raw = {}, {'relacl': None, 'owner_name': 'alice'}
    apply_default_acl('table', native, raw, 180003)
    assert native['privileges_default'] is True
    assert {row['grantee'] for row in native['privileges']} == {'alice'}
    assert 'MAINTAIN' in {row['privilege'] for row in native['privileges']}
    older = {}
    apply_default_acl('table', older, raw, 160000)
    assert 'MAINTAIN' not in {row['privilege'] for row in older['privileges']}
    function = {}
    apply_default_acl('function', function, {'proacl': None, 'proowner': '10'}, 180003)
    assert ('PUBLIC', 'EXECUTE') in {(row['grantee'], row['privilege']) for row in function['privileges']}
    assert function['privileges'][0]['grantee'] == '(owner)'


def test_an_explicit_acl_is_left_alone_and_not_flagged_default():
    native = {'privileges': [{'grantee': 'x'}]}
    apply_default_acl('table', native, {'relacl': ['a=r/b']}, 180003)
    assert native == {'privileges': [{'grantee': 'x'}], 'privileges_default': False}
    unknown = {}
    apply_default_acl('column', unknown, {'attacl': None}, 180003)  # column ACLs have no default
    assert unknown == {'privileges_default': False}


@live_only
def test_every_default_matches_what_the_server_reports(live):
    version = int(query('SHOW server_version_num', database=DATABASE)[0][0])
    codes = {'TABLE': 'r', 'SEQUENCE': 's', 'DATABASE': 'd', 'FUNCTION': 'f', 'LANGUAGE': 'l', 'SCHEMA': 'n',
             'TABLESPACE': 't', 'FOREIGN DATA WRAPPER': 'F', 'FOREIGN SERVER': 'S', 'TYPE': 'T'}
    for kind, family in DEFAULT_FAMILY.items():
        assert _OBJECTS[family][1] == codes[family], family
        server = {(('PUBLIC' if grantee == 0 else 'owner'), privilege) for grantee, privilege in query(
            f"SELECT a.grantee, a.privilege_type FROM aclexplode(acldefault('{codes[family]}', 10)) a", database=DATABASE)}
        mine = {(('PUBLIC' if row['grantee'] == 'PUBLIC' else 'owner'), row['privilege'])
                for row in default_acl(kind, {}, {}, version)}
        assert mine == server, (kind, mine ^ server)
    assert set(ACL_COLUMNS) == set(DEFAULT_FAMILY)

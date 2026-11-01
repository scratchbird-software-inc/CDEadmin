"""YugabyteDB event triggers, rules, collations and publications.

Each statement shape was executed live on YugabyteDB 2025.2.2.2
(2026-11-01) before it was offered.
"""
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.providers.yugabytedb.catalog_objects import (  # noqa
    rule_native,
)
from pgadmin.cdeadmin.providers.yugabytedb.provider import (  # noqa: E402
    ADMINISTRATION,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402


def sql(kind, operation, draft, target=None):
    planned = ADMINISTRATION.plan({
        'resource_kind': kind, 'operation_id': operation, 'draft': draft,
        'target_resource': target, '_provider_route': {'database': 'd'}})
    return [item['source'] for item in
            planned['provider_payload']['compiled']['statements']]


def target(kind, path, native):
    return {'resource_id': ':'.join([kind, *path]), 'resource_kind': kind,
            'display_name': path[-1], 'display_path': path, 'native': native}


def test_event_trigger():
    assert sql('event-trigger', 'create', {
        'name': 'et', 'event': 'ddl_command_end',
        'function': ['public', 'evt()'], 'tags': [{'value': 'CREATE TABLE'}],
        'enabled': 'ALWAYS', 'comment': "it's"}) == [
        'CREATE EVENT TRIGGER "et" ON ddl_command_end WHEN TAG IN '
        "('CREATE TABLE') EXECUTE FUNCTION \"public\".\"evt\"()",
        'ALTER EVENT TRIGGER "et" ENABLE ALWAYS',
        "COMMENT ON EVENT TRIGGER \"et\" IS 'it''s'"]
    native = {'event': 'sql_drop', 'function': 'public.evt', 'tags': [],
              'enabled': 'ORIGIN', 'comment': None}
    existing = target('event-trigger', ['et'], native)
    assert sql('event-trigger', 'alter', {
        'name': 'et2', 'enabled': 'DISABLED'}, existing) == [
        'ALTER EVENT TRIGGER "et" DISABLE',
        'ALTER EVENT TRIGGER "et" RENAME TO "et2"']
    with pytest.raises(RelationalClientError, match='in place'):
        sql('event-trigger', 'alter', {'event': 'ddl_command_start'},
            existing)
    for bad in ({'event': 'ddl_command_now'}, {'tags': ['create table']}):
        with pytest.raises(RelationalClientError):
            sql('event-trigger', 'create', {
                'name': 'et', 'event': 'sql_drop', 'function': 'public.evt',
                **bad})


def test_rule():
    assert sql('rule', 'create', {
        'name': 'r', 'table': ['public', 't'], 'event': 'INSERT',
        'condition': 'NEW.v > 1', 'instead': False,
        'actions': "INSERT INTO l VALUES ('a;b')"}) == [
        'CREATE RULE "r" AS ON INSERT TO "public"."t" WHERE NEW.v > 1 DO '
        "ALSO (INSERT INTO l VALUES ('a;b'))"]
    assert sql('rule', 'create', {
        'name': 'r', 'table': 'public.t', 'event': 'DELETE',
        'instead': True}) == [
        'CREATE RULE "r" AS ON DELETE TO "public"."t" DO INSTEAD NOTHING']
    native = rule_native(
        'CREATE RULE r AS\n    ON DELETE TO public.t DO INSTEAD NOTHING;',
        None)
    existing = target('rule', ['public', 't', 'r'], native)
    assert sql('rule', 'alter', {'instead': False}, existing) == [
        'CREATE OR REPLACE RULE "r" AS ON DELETE TO "public"."t" DO ALSO '
        'NOTHING']
    with pytest.raises(RelationalClientError, match='keeps its name'):
        sql('rule', 'alter', {'name': 'r2'}, existing)
    assert sql('rule', 'drop', {'confirmation': 'r'}, existing) == [
        'DROP RULE "r" ON "public"."t"']


def test_rule_definitions_read_back_into_the_form():
    assert rule_native(
        'CREATE RULE r1 AS\n    ON INSERT TO public.rt\n   WHERE (new.v > 10)'
        ' DO  INSERT INTO rlog (id)\n  VALUES (new.id);', 'c') == {
        'definition': 'CREATE RULE r1 AS\n    ON INSERT TO public.rt\n   '
        'WHERE (new.v > 10) DO  INSERT INTO rlog (id)\n  VALUES (new.id);',
        'event': 'INSERT', 'condition': 'new.v > 10', 'instead': False,
        'actions': 'INSERT INTO rlog (id) VALUES (new.id)', 'comment': 'c'}
    multiple = rule_native(
        'CREATE RULE r3 AS\n    ON UPDATE TO public.rt DO INSTEAD ( INSERT '
        'INTO rlog (id)\n  VALUES (old.id);\n INSERT INTO rlog (id)\n  '
        'VALUES (new.id);\n);', None)
    assert multiple['instead'] and multiple['event'] == 'UPDATE'
    assert multiple['actions'] == ('INSERT INTO rlog (id) VALUES (old.id); '
                                   'INSERT INTO rlog (id) VALUES (new.id);')


def test_collation():
    assert sql('collation', 'create', {
        'name': 'c', 'parent': 'public', 'provider': 'icu',
        'locale': 'de-DE'}) == [
        'CREATE COLLATION "public"."c" (provider = icu, locale = '
        "'de-DE')"]
    for bad in ({'provider': 'other'}, {'locale': "de'DE"}):
        with pytest.raises(RelationalClientError):
            sql('collation', 'create', {'name': 'c', 'locale': 'C', **bad})
    existing = target('collation', ['public', 'c'],
                      {'provider': 'icu', 'locale': 'de-DE'})
    assert sql('collation', 'alter', {'name': 'c2', 'parent': 's2'},
               existing) == [
        'ALTER COLLATION "public"."c" RENAME TO "c2"',
        'ALTER COLLATION "public"."c2" SET SCHEMA "s2"']
    with pytest.raises(RelationalClientError, match='cannot change'):
        sql('collation', 'alter', {'locale': 'fr-FR'}, existing)


def test_publication():
    assert sql('publication', 'create', {
        'name': 'p', 'tables': [{'value': 'public.t1'}, ['s', 't2']]}) == [
        'CREATE PUBLICATION "p" FOR TABLE "public"."t1", "s"."t2"']
    assert sql('publication', 'create', {'name': 'p', 'all_tables': True}) \
        == ['CREATE PUBLICATION "p" FOR ALL TABLES']
    with pytest.raises(RelationalClientError, match='lists no tables'):
        sql('publication', 'create', {'name': 'p', 'all_tables': True,
                                      'tables': ['public.t']})
    existing = target('publication', ['p'], {
        'all_tables': False, 'tables': ['public.t1']})
    assert sql('publication', 'alter', {
        'tables': ['public.t1', 'public.t2']}, existing) == [
        'ALTER PUBLICATION "p" SET TABLE "public"."t1", "public"."t2"']
    assert sql('publication', 'alter', {'tables': []}, existing) == [
        'ALTER PUBLICATION "p" DROP TABLE "public"."t1"']
    with pytest.raises(RelationalClientError, match='ALL TABLES'):
        sql('publication', 'alter', {'all_tables': True}, existing)


def test_event_trigger_alter_form_carries_no_create_defaults():
    form = ADMINISTRATION._form('event-trigger', 'alter')
    assert not any('default' in item for item in form['fields'])
    existing = target('event-trigger', ['et'], {
        'event': 'sql_drop', 'function': 'public.evt',
        'tags': ['CREATE TABLE'], 'enabled': 'ORIGIN'})
    assert sql('event-trigger', 'alter', {
        'enabled': 'DISABLED', 'tags': [{'value': 'CREATE TABLE'}]},
        existing) == ['ALTER EVENT TRIGGER "et" DISABLE']


def test_aggregate():
    assert sql('aggregate', 'create', {
        'name': 'agg', 'parent': 'public', 'parameters': [{'type': 'int'}],
        'state_function': 'int4pl', 'state_type': 'int',
        'final_function': ['public', 'fin(integer)'],
        'combine_function': 'int4pl', 'initial_condition': '0',
        'parallel': 'SAFE', 'sort_operator': '<', 'comment': 'c'}) == [
        'CREATE AGGREGATE "public"."agg"(int) (SFUNC = "int4pl", STYPE = '
        'int, FINALFUNC = "public"."fin", COMBINEFUNC = "int4pl", INITCOND '
        "= '0', PARALLEL = SAFE, SORTOP = <)",
        "COMMENT ON AGGREGATE \"public\".\"agg\"(int) IS 'c'"]
    native = {'name': 'agg', 'argument_types': ['integer'],
              'state_function': 'int4pl', 'state_type': 'integer',
              'initial_condition': '0', 'owner': 'yugabyte'}
    existing = target('aggregate', ['public', 'agg(integer)'], native)
    assert sql('aggregate', 'alter', {
        'initial_condition': '5', 'owner': 'o', 'name': 'agg2'},
        existing) == [
        'CREATE OR REPLACE AGGREGATE "public"."agg"(integer) (SFUNC = '
        "\"int4pl\", STYPE = integer, INITCOND = '5')",
        'ALTER AGGREGATE "public"."agg"(integer) OWNER TO "o"',
        'ALTER AGGREGATE "public"."agg"(integer) RENAME TO "agg2"']
    with pytest.raises(RelationalClientError, match='SET SCHEMA'):
        sql('aggregate', 'alter', {'parent': 's2'}, existing)
    with pytest.raises(RelationalClientError, match='inputs'):
        sql('aggregate', 'alter', {'parameters': [{'type': 'bigint'}]},
            existing)
    assert sql('aggregate', 'drop', {'confirmation': 'x'}, existing) == [
        'DROP AGGREGATE "public"."agg"(integer)']


def test_operator():
    assert sql('operator', 'create', {
        'name': '===', 'parent': 'public', 'left_type': 'int',
        'right_type': 'int', 'function': 'public.eqf',
        'commutator': '===', 'restrict': 'eqsel', 'join': 'eqjoinsel',
        'hashes': True, 'merges': False}) == [
        'CREATE OPERATOR "public".=== (LEFTARG = int, RIGHTARG = int, '
        'FUNCTION = "public"."eqf", COMMUTATOR = ===, RESTRICT = eqsel, '
        'JOIN = eqjoinsel, HASHES)']
    with pytest.raises(RelationalClientError, match='symbols'):
        sql('operator', 'create', {'name': 'eq; DROP', 'right_type': 'int',
                                   'function': 'f'})
    native = {'name': '===', 'left_type': 'integer',
              'right_type': 'integer', 'function': 'eqf',
              'restrict': 'eqsel', 'join': 'eqjoinsel', 'owner': 'yugabyte'}
    existing = target('operator', ['public', '===(integer, integer)'],
                      native)
    assert sql('operator', 'alter', {
        'restrict': '', 'join': '', 'parent': 's2'}, existing) == [
        'ALTER OPERATOR "public".===(integer, integer) SET (RESTRICT = '
        'NONE, JOIN = NONE)',
        'ALTER OPERATOR "public".===(integer, integer) SET SCHEMA "s2"']
    with pytest.raises(RelationalClientError, match='in place'):
        sql('operator', 'alter', {'function': 'other'}, existing)
    prefix = target('operator', ['public', '!!!(NONE, integer)'], {
        'name': '!!!', 'left_type': None, 'right_type': 'integer'})
    assert sql('operator', 'drop', {'confirmation': 'x'}, prefix) == [
        'DROP OPERATOR "public".!!!(NONE, integer)']


def test_cast():
    assert sql('cast', 'create', {
        'source_type': 'public.mood', 'target_type': 'int',
        'method': 'FUNCTION', 'function': 'public.mood_int',
        'context': 'ASSIGNMENT'}) == [
        'CREATE CAST (public.mood AS int) WITH FUNCTION '
        '"public"."mood_int"(public.mood) AS ASSIGNMENT']
    assert sql('cast', 'create', {
        'source_type': 'int', 'target_type': 'public.mood',
        'method': 'INOUT', 'context': 'IMPLICIT'}) == [
        'CREATE CAST (int AS public.mood) WITH INOUT AS IMPLICIT']
    existing = target('cast', ['mood AS integer'], {
        'source_type': 'mood', 'target_type': 'integer',
        'method': 'FUNCTION', 'context': 'ASSIGNMENT'})
    assert sql('cast', 'alter', {'comment': 'c'}, existing) == [
        "COMMENT ON CAST (mood AS integer) IS 'c'"]
    with pytest.raises(RelationalClientError, match='only its comment'):
        sql('cast', 'alter', {'context': 'IMPLICIT'}, existing)
    assert sql('cast', 'drop', {'confirmation': 'x'}, existing) == [
        'DROP CAST (mood AS integer)']


def test_foreign_server_and_user_mapping():
    assert sql('foreign-server', 'create', {
        'name': 's', 'wrapper': 'postgres_fdw', 'version': '1',
        'options': [{'name': 'host', 'value': "h'x"},
                    {'name': 'port', 'value': '5433'}], 'comment': 'c'}) == [
        "CREATE SERVER \"s\" VERSION '1' FOREIGN DATA WRAPPER "
        "\"postgres_fdw\" OPTIONS (host 'h''x', port '5433')",
        "COMMENT ON SERVER \"s\" IS 'c'"]
    existing = target('foreign-server', ['s'], {
        'wrapper': 'postgres_fdw', 'option_values': {
            'host': 'h', 'port': '5433', 'dbname': 'd'}})
    assert sql('foreign-server', 'alter', {
        'options': [{'name': 'host', 'value': 'h'},
                    {'name': 'port', 'value': '5434'},
                    {'name': 'fetch_size', 'value': '100'}],
        'name': 's2'}, existing) == [
        "ALTER SERVER \"s\" OPTIONS (DROP dbname, SET port '5434', ADD "
        "fetch_size '100')",
        'ALTER SERVER "s" RENAME TO "s2"']
    assert sql('foreign-server', 'drop', {'cascade': True}, existing) == [
        'DROP SERVER "s" CASCADE']
    # Secrets never travel as plain options.
    with pytest.raises(RelationalClientError, match='secret'):
        sql('user-mapping', 'create', {
            'user': 'u', 'server': 's',
            'options': [{'name': 'password', 'value': 'x'}]})
    assert sql('user-mapping', 'create', {
        'user': 'PUBLIC', 'server': 's'}) == [
        'CREATE USER MAPPING FOR PUBLIC SERVER "s"']
    mapping = target('user-mapping', ['s', 'u'], {
        'option_values': {'user': 'remote'}})
    assert sql('user-mapping', 'alter', {
        'options': [{'name': 'user', 'value': 'remote2'}]}, mapping) == [
        "ALTER USER MAPPING FOR \"u\" SERVER \"s\" OPTIONS (SET user "
        "'remote2')"]
    assert sql('user-mapping', 'drop', {'confirmation': 'x'}, mapping) == [
        'DROP USER MAPPING FOR "u" SERVER "s"']


def test_foreign_table():
    assert sql('foreign-table', 'create', {
        'name': 'ft', 'parent': 'public', 'server': 's',
        'columns': [{'name': 'id', 'type': 'int', 'nullable': False},
                    {'name': 'v', 'type': 'text'}],
        'options': [{'name': 'table_name', 'value': 'src'}]}) == [
        'CREATE FOREIGN TABLE "public"."ft" ("id" int NOT NULL, "v" text) '
        "SERVER \"s\" OPTIONS (table_name 'src')"]
    with pytest.raises(RelationalClientError, match='primary key'):
        sql('foreign-table', 'create', {
            'name': 'ft', 'server': 's', 'columns': [
                {'name': 'id', 'type': 'int', 'primary_key': True}]})
    existing = target('foreign-table', ['public', 'ft'], {
        'server': 's', 'option_values': {'table_name': 'src'}})
    assert sql('foreign-table', 'alter', {
        'add_columns': [{'name': 'w', 'type': 'int'}],
        'options': [{'name': 'table_name', 'value': 'src2'}],
        'name': 'ft2'}, existing) == [
        'ALTER FOREIGN TABLE "public"."ft" ADD COLUMN "w" int',
        "ALTER FOREIGN TABLE \"public\".\"ft\" OPTIONS (SET table_name "
        "'src2')",
        'ALTER FOREIGN TABLE "public"."ft" RENAME TO "ft2"']
    with pytest.raises(RelationalClientError, match='another server'):
        sql('foreign-table', 'alter', {'server': 'other'}, existing)
    assert sql('foreign-table', 'drop', {'confirmation': 'x'}, existing) == [
        'DROP FOREIGN TABLE "public"."ft"']

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

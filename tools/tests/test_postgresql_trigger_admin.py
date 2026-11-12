"""PostgreSQL trigger, event trigger and rule create/alter/drop compile to
exact native statements (M4)."""
import pytest
from pgadmin.cdeadmin.providers.postgresql.native_admin import (
    compile_native_admin, PostgreSQLNativeAdminError,
)
from pgadmin.cdeadmin.providers.postgresql.triggers import (
    event_trigger_facts, form, rule_facts, trigger_facts,
)

TRIGGER = {'schema': 'service', 'name': 'audit', 'comment': None,
           'definition': 'CREATE TRIGGER audit AFTER INSERT OR UPDATE OF '
                         'status ON service.work_orders REFERENCING NEW '
                         'TABLE AS newrows FOR EACH ROW WHEN ((new.status <> '
                         "old.status)) EXECUTE FUNCTION service.log_it('a')",
           'catalog_row': {'tgname': 'audit', 'tgenabled': 'O',
                           'tgisinternal': False}}
CONSTRAINT = dict(TRIGGER, name='check_it', definition=(
    'CREATE CONSTRAINT TRIGGER check_it AFTER DELETE ON service.customers '
    'DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION '
    'service.check_it()'), catalog_row={'tgname': 'check_it',
                                         'tgenabled': 'O',
                                         'tgisinternal': False})
RULE = {'schema': 'service', 'name': 'log_updates', 'comment': 'log',
        'definition': 'CREATE RULE log_updates AS ON UPDATE TO '
                      'service.work_orders WHERE (old.status <> new.status) '
                      'DO ALSO INSERT INTO service.log VALUES (1)',
        'catalog_row': {'rulename': 'log_updates', 'ev_enabled': 'O',
                        'is_instead': False}}
EVENT = {'name': 'no_drops', 'comment': None,
         'catalog_row': {'evtname': 'no_drops', 'evtevent': 'sql_drop',
                         'evttags': ['DROP TABLE'], 'evtenabled': 'O'}}
FACTS = {'trigger': ('trigger_facts', trigger_facts),
         'event-trigger': ('event_trigger_facts', event_trigger_facts),
         'rule': ('rule_facts', rule_facts)}


def compile_kind(kind, operation, draft, native):
    key, reader = FACTS[kind]
    native = dict(native, **{key: reader(native)})
    return compile_native_admin({
        'resource_kind': kind, 'operation_id': operation, 'draft': draft,
        'target_resource': {'extensions': {'postgresql': {'native': native}}}})


def statements(kind, operation, draft, native):
    return compile_kind(kind, operation, draft, native)['statement'].split(
        ';\n')


def test_trigger_facts_decode_the_definition():
    current = trigger_facts(TRIGGER)
    assert current['definition_parsed']
    assert (current['table'], current['fires'], current['evnt_insert'],
            current['evnt_update'], current['evnt_delete'],
            current['columns'], current['is_row_trigger'],
            current['tgnewtable'], current['tgoldtable']) == (
        'work_orders', 'AFTER', True, True, False, ['status'], True,
        'newrows', None)
    assert (current['whenclause'], current['tfunction'], current['tgargs']) \
        == ('new.status <> old.status', '"service"."log_it"', 'a')
    constraint = trigger_facts(CONSTRAINT)
    assert (constraint['is_constraint_trigger'], constraint['tgdeferrable'],
            constraint['tginitdeferred']) == (True, True, True)


def test_rule_and_event_trigger_facts():
    current = rule_facts(RULE)
    assert (current['view'], current['event'], current['do_instead'],
            current['condition'], current['statements']) == (
        'work_orders', 'UPDATE', False, 'old.status <> new.status',
        'INSERT INTO service.log VALUES (1)')
    event = event_trigger_facts(EVENT)
    assert (event['eventname'], event['when'], event['enabled']) == (
        'SQL_DROP', 'DROP TABLE', 'O')


def test_trigger_create_with_every_clause():
    from pglast import parse_sql
    text = compile_kind('trigger', 'create', {
        'name': 'trg one', 'schema': 'Sch ema', 'table': 'orders',
        'fires': 'before', 'evnt_insert': True, 'evnt_update': True,
        'evnt_delete': False, 'columns': [{'column': 'status'}, 'priority'],
        'is_row_trigger': True, 'tgnewtable': 'newrows',
        'tgoldtable': 'oldrows', 'whenclause': 'new.status <> old.status',
        'tfunction': 'audit.log_it', 'tgargs': "a, it's",
        'description': 'c'}, TRIGGER)['statement']
    assert text.split(';\n') == [
        'CREATE TRIGGER "trg one" BEFORE INSERT OR UPDATE OF "status", '
        '"priority" ON "Sch ema"."orders" REFERENCING NEW TABLE AS "newrows" '
        'OLD TABLE AS "oldrows" FOR EACH ROW WHEN (new.status <> old.status) '
        "EXECUTE FUNCTION audit.log_it('a', 'it''s')",
        'COMMENT ON TRIGGER "trg one" ON "Sch ema"."orders" IS \'c\'']
    assert len(parse_sql(text)) == 2
    constraint = compile_kind('trigger', 'create', {
        'name': 'c', 'schema': 's', 'table': 't',
        'is_constraint_trigger': True,
        'fires': 'AFTER', 'evnt_delete': True, 'tgdeferrable': True,
        'tginitdeferred': True, 'is_row_trigger': True, 'tfunction': 'f'},
        TRIGGER)['statement']
    assert constraint == ('CREATE CONSTRAINT TRIGGER "c" AFTER DELETE ON '
                          '"s"."t" DEFERRABLE INITIALLY DEFERRED FOR EACH ROW '
                          'EXECUTE FUNCTION f()')


@pytest.mark.parametrize('draft, message', [
    ({'fires': 'DURING'}, 'fires is'),
    ({'evnt_insert': False}, 'at least one event'),
    ({'tfunction': 'f(); drop'}, 'catalog reference'),
    ({'whenclause': 'a) or (b'}, 'unsafe'),
])
def test_trigger_create_refusals(draft, message):
    base = {'name': 't', 'schema': 's', 'table': 't', 'evnt_insert': True,
            'tfunction': 'f'}
    with pytest.raises(PostgreSQLNativeAdminError, match=message):
        compile_kind('trigger', 'create', {**base, **draft}, TRIGGER)


def test_trigger_alter_replaces_enables_comments_and_renames():
    assert statements('trigger', 'alter', {
        'evnt_delete': True, 'whenclause': None, 'is_enable_trigger': 'D',
        'description': 'audit rows', 'name': 'audit_rows'}, TRIGGER) == [
        'CREATE OR REPLACE TRIGGER "audit" AFTER INSERT OR DELETE OR UPDATE '
        'OF "status" ON "service"."work_orders" REFERENCING NEW TABLE AS '
        '"newrows" FOR EACH ROW WHEN (new.status <> old.status) EXECUTE '
        "FUNCTION \"service\".\"log_it\"('a')",
        'ALTER TABLE "service"."work_orders" DISABLE TRIGGER "audit"',
        'COMMENT ON TRIGGER "audit" ON "service"."work_orders" IS '
        "'audit rows'",
        'ALTER TRIGGER "audit" ON "service"."work_orders" RENAME TO '
        '"audit_rows"']
    # A constraint trigger has no OR REPLACE: drop and create.
    assert statements('trigger', 'alter', {'tginitdeferred': False},
                      CONSTRAINT) == [
        'DROP TRIGGER "check_it" ON "service"."customers"',
        'CREATE CONSTRAINT TRIGGER "check_it" AFTER DELETE ON '
        '"service"."customers" DEFERRABLE FOR EACH ROW EXECUTE FUNCTION '
        '"service"."check_it"()']
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_kind('trigger', 'alter', {'name': 'audit'}, TRIGGER)
    internal = dict(TRIGGER, catalog_row=dict(TRIGGER['catalog_row'],
                                              tgisinternal=True))
    with pytest.raises(PostgreSQLNativeAdminError, match='internal'):
        compile_kind('trigger', 'alter', {'name': 'x'}, internal)
    assert statements('trigger', 'drop', {'confirmation': 'audit',
                                          'cascade': True}, TRIGGER) == [
        'DROP TRIGGER "audit" ON "service"."work_orders" CASCADE']


def test_event_trigger_lifecycle():
    assert statements('event-trigger', 'create', {
        'name': 'no_drops', 'eventname': 'sql_drop',
        'when': 'DROP TABLE, DROP VIEW', 'eventfunname': 'audit.refuse',
        'eventowner': 'dba', 'comment': 'c'}, EVENT) == [
        "CREATE EVENT TRIGGER \"no_drops\" ON sql_drop WHEN TAG IN ('DROP "
        "TABLE', 'DROP VIEW') EXECUTE FUNCTION audit.refuse()",
        'ALTER EVENT TRIGGER "no_drops" OWNER TO "dba"',
        'COMMENT ON EVENT TRIGGER "no_drops" IS \'c\'']
    assert statements('event-trigger', 'alter', {
        'enabled': 'D', 'comment': 'off', 'name': 'drops_off'}, EVENT) == [
        'ALTER EVENT TRIGGER "no_drops" DISABLE',
        'COMMENT ON EVENT TRIGGER "no_drops" IS \'off\'',
        'ALTER EVENT TRIGGER "no_drops" RENAME TO "drops_off"']
    assert statements('event-trigger', 'alter', {
        'when': 'DROP TABLE, DROP INDEX', 'eventfunname': 'audit.refuse'},
        EVENT) == [
        'DROP EVENT TRIGGER "no_drops"',
        "CREATE EVENT TRIGGER \"no_drops\" ON sql_drop WHEN TAG IN ('DROP "
        "TABLE', 'DROP INDEX') EXECUTE FUNCTION audit.refuse()"]
    with pytest.raises(PostgreSQLNativeAdminError,
                       match='function is required'):
        compile_kind('event-trigger', 'alter', {'when': 'DROP VIEW'}, EVENT)
    with pytest.raises(PostgreSQLNativeAdminError, match='event is'):
        compile_kind('event-trigger', 'create', {
            'name': 'e', 'eventname': 'logout', 'eventfunname': 'f'}, EVENT)
    assert statements('event-trigger', 'drop', {'confirmation': 'no_drops'},
                      EVENT) == ['DROP EVENT TRIGGER "no_drops" RESTRICT']


def test_rule_lifecycle():
    assert statements('rule', 'create', {
        'name': 'r one', 'schema': 'Sch ema', 'view': 'v', 'event': 'insert',
        'do_instead': True, 'condition': 'new.id > 0',
        'statements': 'INSERT INTO s.log VALUES (1); NOTIFY changed',
        'comment': 'c'}, RULE) == [
        'CREATE RULE "r one" AS ON INSERT TO "Sch ema"."v" WHERE '
        '(new.id > 0) DO INSTEAD (INSERT INTO s.log VALUES (1); NOTIFY '
        'changed)',
        'COMMENT ON RULE "r one" ON "Sch ema"."v" IS \'c\'']
    assert statements('rule', 'create', {
        'name': 'r', 'schema': 's', 'view': 'v', 'event': 'DELETE',
        'do_instead': True, 'statements': 'nothing'}, RULE) == [
        'CREATE RULE "r" AS ON DELETE TO "s"."v" DO INSTEAD NOTHING']
    assert statements('rule', 'alter', {
        'condition': 'old.status <> new.status', 'do_instead': True,
        'is_enable_rule': 'D', 'comment': '', 'name': 'log_it'}, RULE) == [
        'CREATE OR REPLACE RULE "log_updates" AS ON UPDATE TO '
        '"service"."work_orders" WHERE (old.status <> new.status) DO '
        'INSTEAD (INSERT INTO service.log VALUES (1))',
        'ALTER TABLE "service"."work_orders" DISABLE RULE "log_updates"',
        'COMMENT ON RULE "log_updates" ON "service"."work_orders" IS NULL',
        'ALTER RULE "log_updates" ON "service"."work_orders" RENAME TO '
        '"log_it"']
    with pytest.raises(PostgreSQLNativeAdminError, match='SELECT, INSERT'):
        compile_kind('rule', 'create', {
            'name': 'r', 'schema': 's', 'view': 'v', 'event': 'DELETE',
            'statements': 'DROP TABLE t'}, RULE)
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_kind('rule', 'alter', {'name': 'log_updates'}, RULE)
    assert statements('rule', 'drop', {'confirmation': 'log_updates'},
                      RULE) == [
        'DROP RULE "log_updates" ON "service"."work_orders" RESTRICT']


def test_forms_and_routes():
    def field(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    trigger = {f['field_id']: f
               for f in form('trigger', 'alter', field)['fields']}
    assert trigger['tfunction']['initial_value_path'] == [
        'trigger_facts', 'tfunction']
    assert 'is_enable_trigger' in trigger and 'schema' not in trigger
    # Every family field id is admitted for both variants (owner direction
    # 2026-11-11).
    import json, pathlib
    family = json.loads(pathlib.Path(
        'web/pgadmin/cdeadmin/ui_descriptors/postgresql/forms/'
        'trigger.form.json').read_text())
    event = {f['field_id']: f
             for f in form('event-trigger', 'create', field)['fields']}
    for operation, served in (('alter', trigger), ('create', event)):
        for item in family['fields']:
            if not item.get('modes') or operation in item['modes']:
                assert item['field_id'] in served, (operation, item['field_id'])
    assert event['eventname']['required'] and 'schema' not in event
    rule = {f['field_id']: f for f in form('rule', 'create', field)['fields']}
    assert rule['event']['default'] == 'SELECT'
    from pgadmin.cdeadmin.providers.postgresql.preserved_surface import (
        adapt_catalog)
    catalog = adapt_catalog({'objects': []})
    for kind in ('trigger', 'event-trigger', 'rule'):
        resource = next(item for item in catalog['objects']
                        if item['resource_kind'] == kind)
        routes = {op['operation_id']: op['execution_route']
                  for op in resource['operations']}
        assert routes['create'] == routes['alter'] == routes['drop'] == \
            'provider-native', kind
        assert routes['inspect'] == 'legacy-preserved', kind


def test_family_shapes_for_triggers_and_event_triggers():
    # The dialog's column list is plain names; inline code is refused.
    assert statements('trigger', 'create', {
        'name': 't', 'schema': 's', 'table': 'o', 'fires': 'BEFORE',
        'evnt_update': True, 'columns': ['status', 'note'],
        'tfunction': 's.f'}, TRIGGER) == [
        'CREATE TRIGGER "t" BEFORE UPDATE OF "status", "note" ON "s"."o" FOR '
        'EACH ROW EXECUTE FUNCTION s.f()']
    with pytest.raises(PostgreSQLNativeAdminError, match='EDB feature'):
        compile_kind('trigger', 'alter', {'prosrc': 'begin end'}, TRIGGER)
    # The event name as the dialog's upper-case option; the facts match it;
    # security labels compile.
    assert event_trigger_facts(EVENT)['eventname'] == 'SQL_DROP'
    assert statements('event-trigger', 'create', {
        'name': 'e', 'eventname': 'DDL_COMMAND_END', 'eventfunname': 'f',
        'seclabels': [{'provider': 'selinux', 'label': 'x'}]}, EVENT) == [
        'CREATE EVENT TRIGGER "e" ON ddl_command_end EXECUTE FUNCTION f()',
        'SECURITY LABEL FOR "selinux" ON EVENT TRIGGER "e" IS \'x\'']
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_kind('event-trigger', 'alter', {'eventname': 'SQL_DROP'},
                     EVENT)

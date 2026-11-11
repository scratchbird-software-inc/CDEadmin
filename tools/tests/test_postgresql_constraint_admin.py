"""PostgreSQL table constraints create/alter/drop compile to exact native
statements (M7, 2026-11-11)."""
import pytest
from pgadmin.cdeadmin.providers.postgresql.constraints import facts, form
from pgadmin.cdeadmin.providers.postgresql.native_admin import (
    compile_native_admin, PostgreSQLNativeAdminError,
)

TABLE = {'catalog': 'pg_constraint', 'oid': 1, 'name': 'orders_pkey',
         'schema': 'shop', 'table': 'orders', 'comment': 'pk',
         'definition': 'PRIMARY KEY (id)',
         'catalog_row': {'conname': 'orders_pkey', 'contype': 'p',
                         'conrelid': 24601, 'condeferrable': False,
                         'condeferred': False, 'convalidated': True,
                         'connoinherit': False}}
FK = dict(TABLE, name='orders_customer_fkey', comment='',
          definition='FOREIGN KEY (customer_id) REFERENCES shop.customers(id)',
          catalog_row=dict(TABLE['catalog_row'], conname='orders_customer_fkey',
                           contype='f', confrelid=24700, convalidated=False,
                           confupdtype='a', confdeltype='c',
                           confmatchtype='s'))
CHECK = dict(TABLE, name='orders_qty_check', comment='',
             catalog_row=dict(TABLE['catalog_row'], conname='orders_qty_check',
                              contype='c', convalidated=False))


def compile_constraint(operation, draft, native=TABLE):
    native = dict(native)
    native['constraint_facts'] = facts(native)
    return compile_native_admin({
        'resource_kind': 'constraint', 'operation_id': operation,
        'draft': draft,
        'target_resource': {'extensions': {'postgresql': {'native': native}}}})


def statements(operation, draft, native=TABLE):
    return compile_constraint(operation, draft, native)['statement'].split(
        ';\n')


def test_facts_read_the_captured_row_and_relation_map():
    current = facts(FK, {24700: ('shop', 'customers')})
    assert (current['contype'], current['convalidated'], current['confdeltype'],
            current['referenced_table']) == (
        'f', False, 'c', {'schema': 'shop', 'name': 'customers'})
    assert facts(TABLE)['convalidated'] is True


def test_create_each_kind_as_the_inherited_templates():
    assert statements('create', {
        'name': 'orders_pkey', 'contype': 'p', 'columns': 'id, Tag',
        'include': ['note'], 'fillfactor': 90, 'spcname': 'fast',
        'condeferrable': True, 'condeferred': True, 'comment': 'pk'}) == [
        'ALTER TABLE "shop"."orders" ADD CONSTRAINT "orders_pkey" PRIMARY KEY '
        '("id", "Tag") INCLUDE ("note") WITH (FILLFACTOR=90) USING INDEX '
        'TABLESPACE "fast" DEFERRABLE INITIALLY DEFERRED',
        'COMMENT ON CONSTRAINT "orders_pkey" ON "shop"."orders" IS \'pk\'']
    assert statements('create', {'contype': 'u', 'index': 'orders_tag_ix'}) == [
        'ALTER TABLE "shop"."orders" ADD UNIQUE USING INDEX "orders_tag_ix"']
    assert statements('create', {
        'name': 'fk', 'contype': 'f',
        'fk_columns': [{'local_column': 'customer_id', 'referenced': 'id'}],
        'remote_schema': 'shop', 'remote_table': 'customers',
        'confmatchtype': True, 'confupdtype': 'a', 'confdeltype': 'c',
        'condeferrable': True, 'not_valid': True}) == [
        'ALTER TABLE "shop"."orders" ADD CONSTRAINT "fk" FOREIGN KEY '
        '("customer_id") REFERENCES "shop"."customers" ("id") MATCH FULL '
        'ON UPDATE NO ACTION ON DELETE CASCADE DEFERRABLE NOT VALID']
    assert statements('create', {
        'name': 'qty_ok', 'contype': 'c', 'consrc': 'qty > 0',
        'not_valid': True, 'connoinherit': True}) == [
        'ALTER TABLE "shop"."orders" ADD CONSTRAINT "qty_ok" CHECK (qty > 0) '
        'NOT VALID NO INHERIT']
    assert statements('create', {
        'name': 'no_overlap', 'contype': 'x', 'amname': 'gist',
        'elements': [{'column': 'room', 'operator': '='},
                     {'column': 'tstzrange(starts, ends)', 'is_exp': True,
                      'operator': '&&'}],
        'indconstraint': 'cancelled = false', 'fillfactor': 70}) == [
        'ALTER TABLE "shop"."orders" ADD CONSTRAINT "no_overlap" EXCLUDE '
        'USING "gist" ("room" WITH =, (tstzrange(starts, ends)) WITH &&) '
        'WITH (FILLFACTOR=70) WHERE (cancelled = false)']


def test_alter_emits_one_statement_per_changed_fact():
    assert statements('alter', {'name': 'orders_pk', 'fillfactor': 80,
                                'spcname': 'fast', 'comment': ''}) == [
        'ALTER TABLE "shop"."orders" RENAME CONSTRAINT "orders_pkey" TO "orders_pk"',
        'ALTER INDEX "shop"."orders_pk" SET (FILLFACTOR=80)',
        'ALTER INDEX "shop"."orders_pk" SET TABLESPACE "fast"',
        'COMMENT ON CONSTRAINT "orders_pk" ON "shop"."orders" IS NULL']
    assert statements('alter', {'reset_fillfactor': True}) == [
        'ALTER INDEX "shop"."orders_pkey" RESET (FILLFACTOR)']
    assert statements('alter', {'validate': True, 'condeferrable': True,
                                'condeferred': True}, FK) == [
        'ALTER TABLE "shop"."orders" VALIDATE CONSTRAINT "orders_customer_fkey"',
        'ALTER TABLE "shop"."orders" ALTER CONSTRAINT "orders_customer_fkey" '
        'DEFERRABLE INITIALLY DEFERRED']
    assert statements('alter', {'validate': True, 'comment': 'checked'},
                      CHECK) == [
        'ALTER TABLE "shop"."orders" VALIDATE CONSTRAINT "orders_qty_check"',
        'COMMENT ON CONSTRAINT "orders_qty_check" ON "shop"."orders" IS '
        "'checked'"]
    # Validating an already valid constraint, or no change, is refused.
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_constraint('alter', {'validate': True, 'comment': 'pk'})


def test_refusals_keep_text_as_data():
    bad = [
        ('create', {'contype': 'k'}, 'contype'),
        ('create', {'contype': 'p'}, 'columns'),
        ('create', {'contype': 'c', 'consrc': 'qty > 0); DROP TABLE t; --'},
         'unsafe'),
        ('create', {'contype': 'f', 'fk_columns': [{'local_column': 'a',
                                                    'referenced': 'b'}],
                    'remote_schema': 's', 'remote_table': 't',
                    'confdeltype': 'x'}, 'confdeltype'),
        ('create', {'contype': 'x', 'elements': [{'column': 'c',
                                                  'operator': '= ; --'}]},
         'operator'),
        ('create', {'contype': 'p', 'columns': 'id', 'fillfactor': 5},
         'fillfactor'),
        ('create', {'contype': 'p', 'columns': 'id', 'comment': 'x'}, 'name'),
        ('drop', {'confirmation': 'other'}, 'confirmation'),
    ]
    for operation, draft, message in bad:
        with pytest.raises(PostgreSQLNativeAdminError, match=message):
            compile_constraint(operation, draft)


def test_drop_with_cascade_and_typed_name():
    assert statements('drop', {'confirmation': 'orders_pkey'}) == [
        'ALTER TABLE "shop"."orders" DROP CONSTRAINT "orders_pkey"']
    assert statements('drop', {'confirmation': 'orders_pkey',
                               'cascade': True}) == [
        'ALTER TABLE "shop"."orders" DROP CONSTRAINT "orders_pkey" CASCADE']


def test_forms_follow_the_inherited_ids():
    def field(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    create = form('create', field)['fields']
    ids = [f['field_id'] for f in create]
    assert len(ids) == len(set(ids)), 'field ids must be unique'
    by_id = {f['field_id']: f for f in create}
    assert by_id['contype']['required'] and by_id['contype']['default'] == 'p'
    assert by_id['fk_columns']['visible_when'] == {
        'field': 'contype', 'field_id': 'contype', 'equals': 'f'}
    assert by_id['fillfactor']['visible_when']['in'] == ['p', 'u', 'x']
    alter = {f['field_id']: f for f in form('alter', field)['fields']}
    assert alter['name']['initial_value_path'] == ['constraint_facts', 'name']
    assert {'validate', 'condeferrable', 'fillfactor', 'spcname',
            'comment'} <= set(alter)
    drop = {f['field_id'] for f in form('drop', field)['fields']}
    assert drop == {'cascade', 'confirmation'}

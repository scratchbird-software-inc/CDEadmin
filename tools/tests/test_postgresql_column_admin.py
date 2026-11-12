"""PostgreSQL column create/alter/drop compile to exact native statements
(M7, 2026-11-11)."""
import pytest
from pgadmin.cdeadmin.providers.postgresql.columns import facts, form
from pgadmin.cdeadmin.providers.postgresql.native_admin import (
    compile_native_admin, PostgreSQLNativeAdminError,
)

COLUMN = {'catalog': 'pg_attribute', 'oid': 24601, 'attnum': 3,
          'name': 'amount', 'schema': 'shop', 'table': 'orders',
          'data_type': 'numeric(10,2)', 'not_null': False,
          'comment': 'gross', 'default_expression': '0',
          'catalog_row': {'attname': 'amount', 'attnotnull': False,
                          'attidentity': '', 'attgenerated': '',
                          'attstattarget': -1, 'attstorage': 'm',
                          'attcompression': ''}}


def compile_column(operation, draft, native=COLUMN):
    native = dict(native)
    native['column_facts'] = facts(native)
    return compile_native_admin({
        'resource_kind': 'column', 'operation_id': operation,
        'draft': draft,
        'target_resource': {'extensions': {'postgresql': {'native': native}}}})


def statements(operation, draft, native=COLUMN):
    return compile_column(operation, draft, native)['statement'].split(';\n')


def test_facts_read_the_captured_attribute():
    assert facts(COLUMN) == {
        'schema': 'shop', 'table': 'orders', 'name': 'amount', 'attnum': 3,
        'cltype': 'numeric(10,2)', 'attnotnull': False, 'defval': '0',
        'description': 'gross', 'colconstype': 'n', 'attidentity': '',
        'attstattarget': -1, 'attstorage': 'm', 'attcompression': '',
        'attacl': [], 'attoptions': [], 'seclabels': []}
    identity = dict(COLUMN, catalog_row=dict(COLUMN['catalog_row'],
                                             attidentity='a'))
    assert facts(identity)['colconstype'] == 'i'
    # PostgreSQL 17+ stores the default statistics target as NULL.
    modern = dict(COLUMN, catalog_row=dict(COLUMN['catalog_row'],
                                           attstattarget=None))
    assert facts(modern)['attstattarget'] == -1


def test_create_renders_every_clause_as_the_inherited_template():
    lines = statements('create', {
        'name': 'Net Total', 'cltype': 'numeric(12, 2)', 'collspcname': '"C"',
        'attnotnull': True, 'defval': '0', 'description': "it's",
        'attstattarget': 500, 'attstorage': 'p', 'attcompression': 'lz4'})
    assert lines == [
        'ALTER TABLE "shop"."orders" ADD COLUMN "Net Total" numeric(12, 2) '
        'COLLATE "C" NOT NULL DEFAULT 0',
        'COMMENT ON COLUMN "shop"."orders"."Net Total" IS \'it\'\'s\'',
        'ALTER TABLE "shop"."orders" ALTER COLUMN "Net Total" SET STATISTICS 500',
        'ALTER TABLE "shop"."orders" ALTER COLUMN "Net Total" SET STORAGE PLAIN',
        'ALTER TABLE "shop"."orders" ALTER COLUMN "Net Total" SET COMPRESSION lz4',
    ]
    identity = statements('create', {
        'name': 'id', 'cltype': 'bigint', 'colconstype': 'i',
        'attidentity': 'a', 'seqstart': 10, 'seqincrement': 2,
        'seqcycle': True})
    assert identity == ['ALTER TABLE "shop"."orders" ADD COLUMN "id" bigint '
                        'GENERATED ALWAYS AS IDENTITY (CYCLE INCREMENT 2 '
                        'START 10)']
    generated = statements('create', {
        'name': 'total', 'cltype': 'numeric', 'colconstype': 'g',
        'genexpr': 'amount * qty', 'defval': 'ignored'})
    assert generated == ['ALTER TABLE "shop"."orders" ADD COLUMN "total" numeric '
                         'GENERATED ALWAYS AS (amount * qty) STORED']


def test_alter_emits_one_statement_per_changed_fact():
    lines = statements('alter', {
        'name': 'gross', 'cltype': 'numeric(14,2)', 'defval': '',
        'attnotnull': True, 'attstattarget': 100, 'attstorage': 'x',
        'description': ''})
    assert lines == [
        'ALTER TABLE "shop"."orders" RENAME "amount" TO "gross"',
        'ALTER TABLE "shop"."orders" ALTER COLUMN "gross" TYPE numeric(14, 2)',
        'ALTER TABLE "shop"."orders" ALTER COLUMN "gross" DROP DEFAULT',
        'ALTER TABLE "shop"."orders" ALTER COLUMN "gross" SET NOT NULL',
        'ALTER TABLE "shop"."orders" ALTER COLUMN "gross" SET STATISTICS 100',
        'ALTER TABLE "shop"."orders" ALTER COLUMN "gross" SET STORAGE EXTENDED',
        'COMMENT ON COLUMN "shop"."orders"."gross" IS NULL',
    ]
    # Unchanged values emit nothing; an identical draft is refused.
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_column('alter', {'cltype': 'numeric(10,2)', 'defval': '0',
                                 'attnotnull': False, 'attstorage': 'm',
                                 'description': 'gross'})
    assert statements('alter', {'defval': "now()"}) == [
        'ALTER TABLE "shop"."orders" ALTER COLUMN "amount" SET DEFAULT now()']


def test_identity_transitions():
    assert statements('alter', {'colconstype': 'i', 'attidentity': 'd'}) == [
        'ALTER TABLE "shop"."orders" ALTER COLUMN "amount" ADD GENERATED BY '
        'DEFAULT AS IDENTITY']
    identity = dict(COLUMN, catalog_row=dict(COLUMN['catalog_row'],
                                             attidentity='d'))
    assert statements('alter', {'colconstype': 'i', 'attidentity': 'a',
                                'seqmax': 999, 'seqcycle': False},
                      identity) == [
        'ALTER TABLE "shop"."orders" ALTER COLUMN "amount" SET GENERATED ALWAYS',
        'ALTER TABLE "shop"."orders" ALTER COLUMN "amount" SET MAXVALUE 999 '
        'SET NO CYCLE']
    assert statements('alter', {'colconstype': 'n'}, identity) == [
        'ALTER TABLE "shop"."orders" ALTER COLUMN "amount" DROP IDENTITY']
    generated = dict(COLUMN, catalog_row=dict(COLUMN['catalog_row'],
                                              attgenerated='s'))
    with pytest.raises(PostgreSQLNativeAdminError, match='generated'):
        compile_column('alter', {'colconstype': 'i', 'attidentity': 'a'},
                       generated)
    with pytest.raises(PostgreSQLNativeAdminError, match='generated'):
        compile_column('alter', {'colconstype': 'g', 'genexpr': '1'})


def test_refusals_keep_text_as_data():
    bad = [
        ('create', {'name': 'x', 'cltype': 'int; DROP TABLE t'}, 'cltype'),
        ('create', {'name': 'x', 'cltype': 'int', 'defval': "1); --"},
         'unsafe'),
        ('create', {'name': 'x', 'cltype': 'int', 'attstorage': 'z'},
         'attstorage'),
        ('create', {'name': 'x', 'cltype': 'int', 'attcompression': 'zstd'},
         'attcompression'),
        ('create', {'name': 'x', 'cltype': 'int', 'colconstype': 'i',
                    'attidentity': 'x'}, 'attidentity'),
        ('create', {'name': 'x', 'cltype': 'int', 'colconstype': 'g'},
         'genexpr'),
        ('create', {'name': 'x', 'cltype': 'int', 'attstattarget': 'many'},
         'whole number'),
        ('drop', {'confirmation': 'other'}, 'confirmation'),
        ('create', {'cltype': 'int'}, 'name'),
    ]
    for operation, draft, message in bad:
        with pytest.raises(PostgreSQLNativeAdminError, match=message):
            compile_column(operation, draft)


def test_drop_with_cascade_and_typed_name():
    assert compile_column('drop', {'confirmation': 'amount'}) == {
        'statement': 'ALTER TABLE "shop"."orders" DROP COLUMN "amount"',
        'read_only': False}
    assert statements('drop', {'confirmation': 'amount', 'cascade': True}) \
        == ['ALTER TABLE "shop"."orders" DROP COLUMN "amount" CASCADE']


def test_forms_follow_the_inherited_ids():
    def field(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    create = {f['field_id']: f for f in form('create', field)['fields']}
    alter = {f['field_id']: f for f in form('alter', field)['fields']}
    assert create['name']['required'] and create['cltype']['required']
    assert not alter['name']['required']
    assert alter['cltype']['initial_value_path'] == ['column_facts', 'cltype']
    assert {'colconstype', 'attidentity', 'genexpr', 'attstattarget',
            'attstorage', 'attcompression', 'description'} <= set(create)
    assert create['genexpr']['visible_when'] == {
        'field': 'colconstype', 'field_id': 'colconstype', 'equals': 'g'}
    drop = {f['field_id'] for f in form('drop', field)['fields']}
    assert drop == {'cascade', 'confirmation'}


def test_privileges_labels_options_and_using():
    # Facts read the aclitem, option and label rows the capture carries.
    rich = dict(COLUMN, security_labels=[{'provider': 'selinux', 'label': 'x',
                                          'objsubid': 3}],
                catalog_row=dict(COLUMN['catalog_row'],
                                 attacl=['reader=r/app', 'ops=rw*/app'],
                                 attoptions=['n_distinct=10']))
    current = facts(rich)
    assert current['attacl'] == [
        {'grantee': 'reader', 'privileges': 'r', 'with_grant': False,
         'grantor': 'app'},
        {'grantee': 'ops', 'privileges': 'rw', 'with_grant': True,
         'grantor': 'app'}]
    assert current['attoptions'] == [{'name': 'n_distinct', 'value': '10'}]
    assert current['seclabels'] == [{'provider': 'selinux', 'label': 'x'}]
    # Create states grants, labels and options after the column.
    lines = statements('create', {
        'name': 'c', 'cltype': 'int',
        'attoptions': [{'name': 'n_distinct', 'value': '-0.5'}],
        'attacl': [{'grantee': 'reader', 'privileges': 'rx'}],
        'seclabels': [{'provider': 'selinux', 'label': 'l'}]})
    assert lines[1:] == [
        'ALTER TABLE "shop"."orders" ALTER COLUMN "c" SET (n_distinct=-0.5)',
        'GRANT SELECT ("c"), REFERENCES ("c") ON "shop"."orders" TO "reader"',
        'SECURITY LABEL FOR "selinux" ON COLUMN "shop"."orders"."c" IS \'l\'']
    # Alter adds revocations, option resets and the USING expression.
    assert statements('alter', {
        'cltype': 'integer', 'using': 'amount::integer',
        'reset_options': [{'name': 'n_distinct'}],
        'revoke': [{'grantee': 'public'}],
        'attacl': [{'grantee': 'ops', 'privileges': 'w', 'with_grant': True}]}) == [
        'ALTER TABLE "shop"."orders" ALTER COLUMN "amount" TYPE integer '
        'USING amount::integer',
        'ALTER TABLE "shop"."orders" ALTER COLUMN "amount" RESET (n_distinct)',
        'GRANT UPDATE ("amount") ON "shop"."orders" TO "ops" WITH GRANT OPTION',
        'REVOKE ALL ("amount") ON "shop"."orders" FROM PUBLIC']
    for draft, message in (
            ({'using': 'x'}, 'type change'),
            ({'attoptions': [{'name': 'work_mem', 'value': '1'}]}, 'attoptions'),
            ({'attacl': [{'grantee': 'r', 'privileges': 'd'}]}, 'privileges'),
            ({'seclabels': [{'provider': 'p', 'label': ''}]}, 'label')):
        with pytest.raises(PostgreSQLNativeAdminError, match=message):
            compile_column('alter', draft)
    def field(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    alter = {f['field_id'] for f in form('alter', field)['fields']}
    assert {'using', 'attoptions', 'reset_options', 'attacl', 'revoke',
            'seclabels'} <= alter
    create = {f['field_id'] for f in form('create', field)['fields']}
    assert 'using' not in create and 'revoke' not in create

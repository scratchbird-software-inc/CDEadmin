"""PostgreSQL table create/alter/drop compile to exact native statements
(M7, 2026-11-11)."""
import pytest
from pgadmin.cdeadmin.providers.postgresql.native_admin import (
    compile_native_admin, PostgreSQLNativeAdminError,
)
from pgadmin.cdeadmin.providers.postgresql.tables import facts, form

TABLE = {'catalog': 'pg_class', 'oid': 24601, 'name': 'orders',
         'schema': 'shop', 'comment': 'sales',
         'catalog_row': {'relname': 'orders', 'relkind': 'r',
                         'relpersistence': 'p', 'relrowsecurity': False,
                         'relforcerowsecurity': False, 'relreplident': 'd',
                         'reloptions': ['fillfactor=90',
                                        'autovacuum_enabled=false',
                                        'autovacuum_vacuum_threshold=100']}}


def compile_table(operation, draft, native=TABLE):
    native = dict(native)
    native['table_facts'] = facts(native)
    return compile_native_admin({
        'resource_kind': 'table', 'operation_id': operation, 'draft': draft,
        'target_resource': {'extensions': {'postgresql': {'native': native}}}})


def statements(operation, draft, native=TABLE):
    return compile_table(operation, draft, native)['statement'].split(';\n')


def test_facts_read_the_captured_relation():
    current = facts(TABLE)
    assert (current['fillfactor'], current['autovacuum_enabled'],
            current['autovacuum_custom'], current['vacuum_settings'],
            current['replica_identity'], current['is_partitioned']) == (
        90, 'f', True, {'autovacuum_enabled': 'false',
                        'autovacuum_vacuum_threshold': '100'}, 'DEFAULT', False)


def test_create_renders_the_inherited_template_as_one_statement():
    lines = statements('create', {
        'name': 'Orders', 'schema': 'shop', 'relowner': 'app',
        'relpersistence': True, 'description': "it's",
        'columns': [
            {'name': 'id', 'cltype': 'bigint', 'colconstype': 'i',
             'attidentity': 'a', 'attnotnull': True},
            {'name': 'qty', 'cltype': 'integer', 'attnotnull': True,
             'defval': '1', 'description': 'count'},
            {'name': 'total', 'cltype': 'numeric', 'colconstype': 'g',
             'genexpr': 'qty * 2'},
            {'name': '', 'cltype': 'text'}],
        'primary_key': [{'name': 'orders_pk', 'columns': [{'column': 'id'}],
                         'fillfactor': 80, 'comment': 'pk'}],
        'unique_constraint': [{'columns': 'qty', 'include': 'total'}],
        'foreign_key': [{'name': 'fk', 'columns': [
            {'local_column': 'qty', 'referenced': 'id'}],
            'references_table_name': 'shop.customers', 'confdeltype': 'c',
            'convalidated': False}],
        'check_constraint': [{'name': 'qty_ok', 'consrc': 'qty > 0',
                              'connoinherit': True}],
        'exclude_constraint': [{'amname': 'gist', 'columns': [
            {'column': 'qty', 'operator': '='}]}],
        'is_partitioned': True, 'partition_type': 'range',
        'partition_keys': [{'key_type': 'column', 'pt_column': 'id'},
                           {'key_type': 'expression',
                            'expression': 'lower(x)'}],
        'coll_inherits': ['shop.base'], 'amname': 'heap',
        'fillfactor': 70, 'parallel_workers': 4, 'autovacuum_enabled': 't',
        'autovacuum_custom': True,
        'vacuum_table': [{'name': 'autovacuum_vacuum_threshold',
                          'value': 50}],
        'spcname': 'fast', 'rlspolicy': True, 'forcerlspolicy': True,
        'seclabels': [{'provider': 'selinux', 'label': 'x'}],
        'relacl': [{'grantee': 'reader', 'privileges': 'r'}]})
    assert lines[0] == (
        'CREATE UNLOGGED TABLE "shop"."Orders" ('
        '"id" bigint NOT NULL GENERATED ALWAYS AS IDENTITY, '
        '"qty" integer NOT NULL DEFAULT 1, '
        '"total" numeric GENERATED ALWAYS AS (qty * 2) STORED, '
        'CONSTRAINT "orders_pk" PRIMARY KEY ("id") WITH (FILLFACTOR=80), '
        'UNIQUE ("qty") INCLUDE ("total"), '
        'CONSTRAINT "fk" FOREIGN KEY ("qty") REFERENCES "shop"."customers" '
        '("id") ON DELETE CASCADE NOT VALID, '
        'CONSTRAINT "qty_ok" CHECK (qty > 0) NO INHERIT, '
        'EXCLUDE USING "gist" ("qty" WITH =)) '
        'PARTITION BY RANGE ("id", (lower(x))) INHERITS (shop.base) '
        'USING "heap" WITH (fillfactor=70, parallel_workers=4, '
        'autovacuum_enabled=true, autovacuum_vacuum_threshold=50) '
        'TABLESPACE "fast"')
    assert lines[1:] == [
        'ALTER TABLE "shop"."Orders" OWNER TO "app"',
        'ALTER TABLE "shop"."Orders" ENABLE ROW LEVEL SECURITY',
        'ALTER TABLE "shop"."Orders" FORCE ROW LEVEL SECURITY',
        'SECURITY LABEL FOR "selinux" ON TABLE "shop"."Orders" IS \'x\'',
        'GRANT SELECT ON TABLE "shop"."Orders" TO "reader"',
        'COMMENT ON TABLE "shop"."Orders" IS \'it\'\'s\'',
        'COMMENT ON COLUMN "shop"."Orders"."qty" IS \'count\'',
        'COMMENT ON CONSTRAINT "orders_pk" ON "shop"."Orders" IS \'pk\'',
    ]
    # A typed table and a LIKE source.
    assert statements('create', {'name': 't', 'schema': 's', 'typname': 's.ty'}) == [
        'CREATE TABLE "s"."t" OF s.ty']
    assert statements('create', {
        'name': 't', 'schema': 's', 'like_relation': 's.src',
        'like_defaults': True, 'like_default_value': True,
        'like_indexes': True})[0] == (
        'CREATE TABLE "s"."t" (LIKE s.src INCLUDING DEFAULTS INCLUDING INDEXES)')
    assert statements('create', {'name': 't', 'schema': 's'}) == [
        'CREATE TABLE "s"."t" ()']


def test_alter_emits_one_statement_per_changed_table_fact():
    lines = statements('alter', {
        'name': 'orders2', 'schema': 'archive', 'relowner': 'dba',
        'relpersistence': True, 'spcname': 'slow', 'rlspolicy': True,
        'fillfactor': 50, 'reset_parallel_workers': True,
        'autovacuum_enabled': 't', 'autovacuum_custom': True,
        'vacuum_table': [{'name': 'autovacuum_vacuum_threshold',
                          'value': '100'},
                         {'name': 'autovacuum_analyze_threshold',
                          'value': 20}],
        'replica_identity': 'FULL', 'description': '',
        'relacl': [{'grantee': 'reader', 'privileges': 'rw',
                    'with_grant': True}],
        'revoke': [{'grantee': 'public'}],
        # Grids of an existing table are not compiled here.
        'columns': [{'name': 'id', 'cltype': 'int'}],
        'primary_key': [{'columns': 'id'}]})
    assert lines == [
        'ALTER TABLE "shop"."orders" RENAME TO "orders2"',
        'ALTER TABLE "shop"."orders2" SET SCHEMA "archive"',
        'ALTER TABLE "archive"."orders2" OWNER TO "dba"',
        'ALTER TABLE "archive"."orders2" SET UNLOGGED',
        'ALTER TABLE "archive"."orders2" SET TABLESPACE "slow"',
        'ALTER TABLE "archive"."orders2" ENABLE ROW LEVEL SECURITY',
        'ALTER TABLE "archive"."orders2" SET (fillfactor=50, '
        'autovacuum_enabled=true, autovacuum_analyze_threshold=20)',
        'ALTER TABLE "archive"."orders2" RESET (parallel_workers)',
        'ALTER TABLE "archive"."orders2" REPLICA IDENTITY FULL',
        'GRANT SELECT, UPDATE ON TABLE "archive"."orders2" TO "reader" '
        'WITH GRANT OPTION',
        'REVOKE ALL ON TABLE "archive"."orders2" FROM PUBLIC',
        'COMMENT ON TABLE "archive"."orders2" IS NULL',
    ]
    assert statements('alter', {'autovacuum_custom': False,
                                'autovacuum_enabled': 'x'}) == [
        'ALTER TABLE "shop"."orders" RESET (autovacuum_enabled, '
        'autovacuum_vacuum_threshold)']
    assert statements('alter', {'replica_identity': 'using index orders_pk'}) == [
        'ALTER TABLE "shop"."orders" REPLICA IDENTITY USING INDEX "orders_pk"']
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_table('alter', {'fillfactor': 90, 'description': 'sales',
                                'autovacuum_enabled': 'f'})


def test_refusals_keep_text_as_data():
    bad = [
        ('create', {'schema': 's'}, 'name'),
        ('create', {'name': 't', 'schema': 's', 'fillfactor': 5}, 'fillfactor'),
        ('create', {'name': 't', 'schema': 's', 'is_partitioned': True,
                    'partition_type': 'range'}, 'partition key'),
        ('create', {'name': 't', 'schema': 's', 'is_partitioned': True,
                    'partition_type': 'weekly',
                    'partition_keys': [{'pt_column': 'id'}]}, 'partition_type'),
        ('create', {'name': 't', 'schema': 's', 'primary_key': [
            {'columns': 'a'}, {'columns': 'b'}]}, 'one primary key'),
        ('create', {'name': 't', 'schema': 's', 'foreign_key': [
            {'columns': [{'local_column': 'a', 'referenced': 'b'}],
             'references_table_name': 'nodot'}]}, 'schema.table'),
        ('create', {'name': 't', 'schema': 's', 'columns': [
            {'name': 'c', 'cltype': 'int; DROP TABLE x'}]}, 'cltype'),
        ('create', {'name': 't', 'schema': 's', 'autovacuum_custom': True,
                    'vacuum_table': [{'name': 'work_mem', 'value': 1}]},
         'autovacuum'),
        ('create', {'name': 't', 'schema': 's',
                    'relacl': [{'grantee': 'r', 'privileges': 'z'}]},
         'privileges'),
        ('alter', {'replica_identity': 'SOMETHING'}, 'replica_identity'),
        ('drop', {'confirmation': 'other'}, 'confirmation'),
    ]
    for operation, draft, message in bad:
        with pytest.raises(PostgreSQLNativeAdminError, match=message):
            compile_table(operation, draft)


def test_drop_with_cascade_and_typed_name():
    assert statements('drop', {'confirmation': 'orders'}) == [
        'DROP TABLE "shop"."orders"']
    assert statements('drop', {'confirmation': 'orders', 'cascade': True}) == [
        'DROP TABLE "shop"."orders" CASCADE']


def test_forms_admit_every_family_field():
    import json
    import pathlib
    def field(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    root = pathlib.Path(__file__).resolve().parents[2]
    family = json.loads((root / 'web/pgadmin/cdeadmin/ui_descriptors/'
                         'postgresql/forms/table.form.json').read_text())
    for mode in ('create', 'alter'):
        sent = {f['field_id'] for f in family['fields']
                if not f.get('modes') or mode in f['modes']}
        declared = {f['field_id'] for f in form(mode, field)['fields']}
        assert sent <= declared, (mode, sorted(sent - declared))
    create = {f['field_id']: f for f in form('create', field)['fields']}
    assert create['name']['required'] and create['schema']['required']
    drop = {f['field_id'] for f in form('drop', field)['fields']}
    assert drop == {'cascade', 'confirmation'}

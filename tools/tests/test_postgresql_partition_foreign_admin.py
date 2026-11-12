"""PostgreSQL partitions (create, attach, detach) and foreign tables
compile to exact native statements (M7, 2026-11-11)."""
import pytest
from pgadmin.cdeadmin.providers.postgresql.foreign_tables import (
    facts as foreign_facts, form as foreign_form,
)
from pgadmin.cdeadmin.providers.postgresql.native_admin import (
    compile_native_admin, PostgreSQLNativeAdminError,
)
from pgadmin.cdeadmin.providers.postgresql.partitions import (
    bound, partition_facts,
)

PARENT = {'catalog': 'pg_class', 'oid': 1, 'name': 'events', 'schema': 'app',
          'catalog_row': {'relname': 'events', 'relkind': 'p',
                          'partition_key_sql': 'RANGE (at)'}}
CHILD = {'catalog': 'pg_class', 'oid': 2, 'name': 'events_2026',
         'schema': 'app', 'parent_table': {'schema': 'app', 'name': 'events'},
         'catalog_row': {'relname': 'events_2026', 'relkind': 'r',
                         'relispartition': True,
                         'partition_bound_sql': "FOR VALUES FROM ('2026-01-01') "
                                                "TO ('2027-01-01')"}}
FOREIGN = {'catalog': 'pg_class', 'oid': 3, 'name': 'remote_orders',
           'schema': 'ext', 'comment': 'mirror',
           'catalog_row': {'relname': 'remote_orders', 'relkind': 'f'},
           'children': {'pg_foreign_table': [{'ftserver': 77}]}}


def compile_kind(kind, operation, draft, native):
    return compile_native_admin({
        'resource_kind': kind, 'operation_id': operation, 'draft': draft,
        'target_resource': {'extensions': {'postgresql': {'native': native}}}})


def test_partition_facts_and_bound_parsing():
    assert partition_facts(CHILD) == {
        'is_partition': True, 'parent': {'schema': 'app', 'name': 'events'},
        'partition_bound': "FOR VALUES FROM ('2026-01-01') TO ('2027-01-01')",
        'partition_key': None}
    inherits = dict(CHILD, parent_table=None,
                    children={'pg_inherits': [{'inhparent': 1}]})
    assert partition_facts(inherits, {1: ('app', 'events')})['parent'] == {
        'schema': 'app', 'name': 'events'}
    assert bound(' FOR VALUES IN (1, 2) ') == 'FOR VALUES IN (1, 2)'
    assert bound('DEFAULT') == 'DEFAULT'
    for text in ('FROM (1)', 'FOR VALUES FROM (1) TO (2); DROP TABLE x',
                 'FOR VALUES WITH (MODULUS a)', '', None):
        with pytest.raises(PostgreSQLNativeAdminError):
            bound(text)


def test_create_attach_and_detach_partitions():
    created = compile_kind('partitioned-table', 'create-partition', {
        'name': 'events_2027', 'is_default': False,
        'partition_value': "FOR VALUES FROM ('2027-01-01') TO ('2028-01-01')",
        'is_partitioned': True, 'partition_type': 'hash',
        'partition_keys': [{'pt_column': 'id'}], 'fillfactor': 80,
        'spcname': 'fast', 'relowner': 'app', 'description': 'next'}, PARENT)
    assert created['statement'] == (
        'CREATE TABLE "app"."events_2027" PARTITION OF "app"."events" '
        "FOR VALUES FROM ('2027-01-01') TO ('2028-01-01') "
        'PARTITION BY HASH ("id") WITH (fillfactor=80) TABLESPACE "fast";\n'
        'ALTER TABLE "app"."events_2027" OWNER TO "app";\n'
        'COMMENT ON TABLE "app"."events_2027" IS \'next\'')
    assert created['maintenance']['transaction_mode'] == 'transaction'
    default = compile_kind('table', 'create-partition', {
        'name': 'events_rest', 'schema': 'arch', 'is_default': True,
        'relpersistence': True}, PARENT)
    assert default['statement'] == ('CREATE UNLOGGED TABLE "arch"."events_rest" '
                                    'PARTITION OF "app"."events" DEFAULT')
    attached = compile_kind('partitioned-table', 'attach-partition', {
        'partition': 'arch.events_old',
        'partition_value': "FOR VALUES FROM ('2020-01-01') TO ('2021-01-01')"},
        PARENT)
    assert attached['statement'] == (
        'ALTER TABLE "app"."events" ATTACH PARTITION "arch"."events_old" '
        "FOR VALUES FROM ('2020-01-01') TO ('2021-01-01')")
    for mode, suffix, autocommit in (('plain', '', False),
                                     ('concurrently', ' CONCURRENTLY', True),
                                     ('finalize', ' FINALIZE', False)):
        detached = compile_kind('table', 'detach-partition', {'mode': mode},
                                CHILD)
        assert detached['statement'] == ('ALTER TABLE "app"."events" DETACH '
                                         'PARTITION "app"."events_2026"'
                                         + suffix)
        assert detached['autocommit'] is autocommit
    with pytest.raises(PostgreSQLNativeAdminError, match='not a partition'):
        compile_kind('table', 'detach-partition', {'mode': 'plain'}, PARENT)
    with pytest.raises(PostgreSQLNativeAdminError, match='schema.table'):
        compile_kind('table', 'attach-partition', {'partition': 'nodot',
                                                   'is_default': True},
                     PARENT)
    with pytest.raises(PostgreSQLNativeAdminError, match='partition bound'):
        compile_kind('table', 'create-partition', {'name': 'x'}, PARENT)


def test_foreign_table_lifecycle():
    assert foreign_facts(FOREIGN, {77: 'remote'})['ftsrvname'] == 'remote'
    created = compile_kind('foreign-table', 'create', {
        'name': 'remote_orders', 'schema': 'ext', 'ftsrvname': 'remote',
        'columns': [{'name': 'id', 'cltype': 'integer', 'attnotnull': True,
                     'coloptions': [{'name': 'column_name', 'value': 'ID'}]},
                    {'name': 'note', 'cltype': 'text', 'description': 'n'}],
        'ftoptions': [{'name': 'schema_name', 'value': 'public'},
                      {'name': 'table_name', 'value': 'orders'}],
        'relowner': 'app', 'description': 'mirror',
        'check_constraint': [{'name': 'id_ok', 'consrc': 'id > 0',
                              'convalidated': False}],
        'relacl': [{'grantee': 'reader', 'privileges': 'r'}],
        'seclabels': [{'provider': 'selinux', 'label': 'x'}]}, FOREIGN)
    assert created['statement'].split(';\n') == [
        'CREATE FOREIGN TABLE "ext"."remote_orders" ("id" integer NOT NULL '
        'OPTIONS ("column_name" \'ID\'), "note" text) SERVER "remote" '
        'OPTIONS ("schema_name" \'public\', "table_name" \'orders\')',
        'ALTER FOREIGN TABLE "ext"."remote_orders" OWNER TO "app"',
        'ALTER FOREIGN TABLE "ext"."remote_orders" ADD CONSTRAINT "id_ok" '
        'CHECK (id > 0) NOT VALID',
        'COMMENT ON FOREIGN TABLE "ext"."remote_orders" IS \'mirror\'',
        'COMMENT ON COLUMN "ext"."remote_orders"."note" IS \'n\'',
        'GRANT SELECT ON TABLE "ext"."remote_orders" TO "reader"',
        'SECURITY LABEL FOR "selinux" ON FOREIGN TABLE "ext"."remote_orders" '
        "IS 'x'"]
    altered = compile_kind('foreign-table', 'alter', {
        'name': 'orders_mirror', 'schema': 'app', 'relowner': 'dba',
        'add_options': [{'name': 'updatable', 'value': 'false'}],
        'set_options': [{'name': 'table_name', 'value': 'orders_v2'}],
        'drop_options': [{'name': 'schema_name'}], 'description': '',
        'revoke': [{'grantee': 'reader'}]}, FOREIGN)
    assert altered['statement'].split(';\n') == [
        'ALTER FOREIGN TABLE "ext"."remote_orders" RENAME TO "orders_mirror"',
        'ALTER FOREIGN TABLE "ext"."orders_mirror" SET SCHEMA "app"',
        'ALTER FOREIGN TABLE "app"."orders_mirror" OWNER TO "dba"',
        'ALTER FOREIGN TABLE "app"."orders_mirror" OPTIONS (ADD "updatable" '
        '\'false\', SET "table_name" \'orders_v2\', DROP "schema_name")',
        'REVOKE ALL ON TABLE "app"."orders_mirror" FROM "reader"',
        'COMMENT ON FOREIGN TABLE "app"."orders_mirror" IS NULL']
    dropped = compile_kind('foreign-table', 'drop',
                           {'confirmation': 'remote_orders', 'cascade': True},
                           FOREIGN)
    assert dropped['statement'] == 'DROP FOREIGN TABLE "ext"."remote_orders" CASCADE'
    for draft, message in (
            ({'name': 't', 'schema': 's'}, 'foreign server'),
            ({'name': 't', 'schema': 's', 'ftsrvname': 'r', 'columns': [
                {'name': 'c', 'cltype': 'int', 'colconstype': 'i',
                 'attidentity': 'a'}]}, 'identity'),
            ({'name': 't', 'schema': 's', 'ftsrvname': 'r',
              'ftoptions': [{'name': 'password', 'value': 'x'}]}, 'credential')):
        with pytest.raises(PostgreSQLNativeAdminError, match=message):
            compile_kind('foreign-table', 'create', draft, FOREIGN)
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_kind('foreign-table', 'alter', {'description': 'mirror'},
                     FOREIGN)


def test_foreign_table_form_admits_the_family_fields():
    def field(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    create = {f['field_id'] for f in foreign_form('create', field)['fields']}
    assert {'name', 'schema', 'ftsrvname', 'ftoptions', 'columns',
            'check_constraint', 'relacl', 'seclabels'} <= create
    alter = {f['field_id'] for f in foreign_form('alter', field)['fields']}
    assert {'add_options', 'set_options', 'drop_options', 'revoke'} <= alter
    assert foreign_form('drop', field)['title'] == 'Drop foreign table'

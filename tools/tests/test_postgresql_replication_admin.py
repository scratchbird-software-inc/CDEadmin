"""PostgreSQL publication and subscription create/alter/drop compile to
exact native statements (M5)."""
import pytest
from pgadmin.cdeadmin.providers.postgresql.native_admin import (
    compile_native_admin, PostgreSQLNativeAdminError,
)
from pgadmin.cdeadmin.providers.postgresql.replication import (
    form, publication_facts, subscription_facts,
)

PUBLICATION = {
    'name': 'pub', 'comment': None,
    'catalog_row': {'pubname': 'pub', 'puballtables': False,
                    'pubinsert': True, 'pubupdate': True, 'pubdelete': False,
                    'pubtruncate': False, 'pubviaroot': True},
    'children': {'pg_publication_rel': [
        {'prrelid': '16393', 'prattrs': [1, 3], 'row_filter_sql': '(id > 0)'},
        {'prrelid': '16386', 'prattrs': None, 'row_filter_sql': None}],
        'pg_publication_namespace': [{'pnnspid': '16385'}]}}
RELATIONS = {16393: ('service', 'assets'), 16386: ('service', 'customers')}
ATTRIBUTES = {16393: [{'attnum': 1, 'attname': 'asset_id'},
                      {'attnum': 2, 'attname': 'owner'},
                      {'attnum': 3, 'attname': 'tag'}]}
SCHEMAS = {16385: 'service'}
SUBSCRIPTION = {
    'name': 'sub', 'comment': 'c',
    'catalog_row': {'subname': 'sub', 'subpublications': ['pub'],
                    'subenabled': False, 'subslotname': None,
                    'subsynccommit': 'off', 'subbinary': False,
                    'substream': 'p', 'subtwophasestate': 'd',
                    'subdisableonerr': False, 'subrunasowner': False,
                    'subpasswordrequired': True, 'suborigin': 'any',
                    'subfailover': False, 'connection_redacted': True}}


def compile_kind(kind, operation, draft, native=None):
    if kind == 'publication':
        native = dict(native or PUBLICATION)
        native['publication_facts'] = publication_facts(
            native, RELATIONS, ATTRIBUTES, SCHEMAS)
    else:
        native = dict(native or SUBSCRIPTION)
        native['subscription_facts'] = subscription_facts(native)
    return compile_native_admin({
        'resource_kind': kind, 'operation_id': operation, 'draft': draft,
        'target_resource': {'extensions': {'postgresql': {'native': native}}}})


def statements(kind, operation, draft, native=None):
    return compile_kind(kind, operation, draft, native)['statement'].split(
        ';\n')


def test_publication_facts_resolve_tables_columns_and_schemas():
    current = publication_facts(PUBLICATION, RELATIONS, ATTRIBUTES, SCHEMAS)
    assert current['pubtable'] == [
        {'table_name': 'service.assets', 'columns': 'asset_id, tag',
         'where': '(id > 0)'},
        {'table_name': 'service.customers', 'columns': '', 'where': None}]
    assert current['pubschema'] == [{'schema': 'service'}]
    assert (current['evnt_delete'], current['publish_via_partition_root']) \
        == (False, True)
    assert subscription_facts(SUBSCRIPTION)['streaming'] == 'parallel'


def test_publication_create_with_every_clause():
    from pglast import parse_sql
    text = compile_kind('publication', 'create', {
        'name': 'my pub', 'only_table': True,
        'pubtable': [{'table_name': 'service.assets',
                      'columns': 'asset_id, tag', 'where': 'asset_id > 0'},
                     {'table_name': '"Sch ema".orders'}],
        'pubschema': [{'schema': 'archive'}],
        'evnt_insert': True, 'evnt_update': True, 'evnt_delete': False,
        'evnt_truncate': False, 'publish_via_partition_root': True,
        'pubowner': 'dba', 'description': "it's"})['statement']
    assert text.split(';\n') == [
        'CREATE PUBLICATION "my pub" FOR TABLE ONLY "service"."assets" '
        '("asset_id", "tag") WHERE (asset_id > 0), "Sch ema"."orders", '
        "TABLES IN SCHEMA \"archive\" WITH (publish = 'insert, update', "
        'publish_via_partition_root = true)',
        'ALTER PUBLICATION "my pub" OWNER TO "dba"',
        'COMMENT ON PUBLICATION "my pub" IS \'it\'\'s\'']
    assert len(parse_sql(text)) == 3
    assert statements('publication', 'create', {'name': 'all',
                                                'all_table': True}) == [
        "CREATE PUBLICATION \"all\" FOR ALL TABLES WITH (publish = 'insert, "
        "update, delete, truncate')"]
    with pytest.raises(PostgreSQLNativeAdminError, match='no table'):
        compile_kind('publication', 'create', {
            'name': 'x', 'all_table': True,
            'pubtable': [{'table_name': 's.t'}]})
    with pytest.raises(PostgreSQLNativeAdminError, match='at least one'):
        compile_kind('publication', 'create', {
            'name': 'x', 'evnt_insert': False, 'evnt_update': False,
            'evnt_delete': False, 'evnt_truncate': False})


def test_publication_alter_changes_members_and_options():
    assert statements('publication', 'alter', {
        'name': 'pub2', 'pubowner': 'dba', 'evnt_delete': True,
        'drop_tables': [{'table_name': 'service.customers'}],
        'add_tables': [{'table_name': 'service.work_orders',
                        'where': 'priority > 1'}],
        'add_schemas': [{'schema': 'archive'}],
        'drop_schemas': [{'schema': 'service'}], 'description': 'd'}) == [
        'ALTER PUBLICATION "pub" RENAME TO "pub2"',
        'ALTER PUBLICATION "pub2" OWNER TO "dba"',
        "ALTER PUBLICATION \"pub2\" SET (publish = 'insert, update, delete', "
        'publish_via_partition_root = true)',
        'ALTER PUBLICATION "pub2" DROP TABLE "service"."customers"',
        'ALTER PUBLICATION "pub2" ADD TABLE "service"."work_orders" WHERE '
        '(priority > 1)',
        'ALTER PUBLICATION "pub2" DROP TABLES IN SCHEMA "service"',
        'ALTER PUBLICATION "pub2" ADD TABLES IN SCHEMA "archive"',
        'COMMENT ON PUBLICATION "pub2" IS \'d\'']
    with pytest.raises(PostgreSQLNativeAdminError, match='fixed once'):
        compile_kind('publication', 'alter', {'all_table': True})
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_kind('publication', 'alter', {'name': 'pub'})
    assert compile_kind('publication', 'drop', {'confirmation': 'pub'}) == {
        'statement': 'DROP PUBLICATION "pub" RESTRICT', 'read_only': False}


def test_subscription_create_without_a_password_runs_alone():
    compiled = compile_kind('subscription', 'create', {
        'name': 'my sub', 'host': '10.0.0.9', 'port': 5432, 'db': 'app',
        'username': 'repl', 'passfile': '/var/lib/pg/.pgpass',
        'sslmode': 'require', 'pub': 'pub, pub2', 'connect': True,
        'enabled': False, 'copy_data': False, 'create_slot': True,
        'slot_name': 'my_slot', 'sync': 'remote_apply', 'streaming': 'on',
        'binary': True, 'two_phase': False, 'origin': 'none'})
    assert compiled == {
        'statement': "CREATE SUBSCRIPTION \"my sub\" CONNECTION 'host=10.0.0.9"
                     " port=5432 dbname=app user=repl "
                     "passfile=/var/lib/pg/.pgpass sslmode=require' "
                     'PUBLICATION "pub", "pub2" WITH (connect = true, '
                     'enabled = false, copy_data = false, create_slot = true, '
                     'slot_name = my_slot, '
                     "synchronous_commit = 'remote_apply',"
                     " streaming = 'on', binary = true, two_phase = false, "
                     "origin = 'none')",
        'read_only': False, 'autocommit': True}
    assert 'password' not in compiled['statement']
    with pytest.raises(PostgreSQLNativeAdminError, match='create_slot = false'):
        compile_kind('subscription', 'create', {
            'name': 's', 'host': 'h', 'pub': 'p', 'connect': False})
    with pytest.raises(PostgreSQLNativeAdminError, match='connection value'):
        compile_kind('subscription', 'create', {
            'name': 's', 'host': "h' password=x", 'pub': 'p'})
    with pytest.raises(PostgreSQLNativeAdminError, match='runs alone'):
        compile_kind('subscription', 'create', {
            'name': 's', 'host': 'h', 'pub': 'p', 'description': 'c'})


def test_subscription_alter_and_refresh():
    assert statements('subscription', 'alter', {
        'name': 'sub2', 'subowner': 'dba', 'enabled': True,
        'slot_name': 'new_slot', 'sync': 'on', 'streaming': 'parallel',
        'binary': True, 'pub': 'pub, extra', 'description': ''}) == [
        'ALTER SUBSCRIPTION "sub" RENAME TO "sub2"',
        'ALTER SUBSCRIPTION "sub2" OWNER TO "dba"',
        "ALTER SUBSCRIPTION \"sub2\" SET (slot_name = new_slot, "
        "synchronous_commit = 'on', binary = true)",
        'ALTER SUBSCRIPTION "sub2" SET PUBLICATION "pub", "extra"',
        'ALTER SUBSCRIPTION "sub2" ENABLE',
        'COMMENT ON SUBSCRIPTION "sub2" IS NULL']
    # Disabled stays disabled: a publication change then refreshes nothing.
    assert statements('subscription', 'alter', {'pub': 'other',
                                                'enabled': False}) == [
        'ALTER SUBSCRIPTION "sub" SET PUBLICATION "other" WITH (refresh = '
        'false)']
    assert compile_kind('subscription', 'alter', {
        'refresh_pub': True, 'copy_data_after_refresh': False}) == {
        'statement': 'ALTER SUBSCRIPTION "sub" REFRESH PUBLICATION WITH '
                     '(copy_data = false)',
        'read_only': False, 'autocommit': True}
    with pytest.raises(PostgreSQLNativeAdminError, match='runs alone'):
        compile_kind('subscription', 'alter', {'refresh_pub': True,
                                               'binary': True})
    with pytest.raises(PostgreSQLNativeAdminError, match='credentials'):
        compile_kind('subscription', 'alter', {'host': 'elsewhere'})
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_kind('subscription', 'alter', {'name': 'sub'})
    assert compile_kind('subscription', 'drop', {'confirmation': 'sub'}) == {
        'statement': 'DROP SUBSCRIPTION "sub" RESTRICT', 'read_only': False,
        'autocommit': True}


def test_forms_and_routes():
    def field(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    create = {f['field_id'] for f in form('subscription', 'create', field)[
        'fields']}
    assert 'password' not in create and 'host' in create
    alter = {f['field_id']: f for f in form('subscription', 'alter', field)[
        'fields']}
    assert 'host' not in alter and alter['pub']['initial_value_path'] == [
        'subscription_facts', 'pub']
    publication = {f['field_id'] for f in form('publication', 'alter',
                                               field)['fields']}
    assert {'add_tables', 'drop_tables', 'add_schemas',
            'drop_schemas'} <= publication
    from pgadmin.cdeadmin.providers.postgresql.preserved_surface import (
        adapt_catalog)
    catalog = adapt_catalog({'objects': []})
    for kind in ('publication', 'subscription'):
        resource = next(item for item in catalog['objects']
                        if item['resource_kind'] == kind)
        routes = {op['operation_id']: op['execution_route']
                  for op in resource['operations']}
        assert routes['create'] == routes['alter'] == routes['drop'] == \
            'provider-native', kind
        assert routes['inspect'] == 'legacy-preserved', kind

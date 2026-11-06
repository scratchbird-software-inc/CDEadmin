"""Browse data on every connector (owner direction 2026-11-06).

Each connector's provider builds, in its own editor language, the text that
reads every record of a resource; CDEadmin puts it in the editor and never
runs it. Resource shapes below follow what each client's list_resources
builds (cited in the provider modules). The kinds a connector offers come
from its manifest; these tests also tie the manifests to the builders.
"""
import base64
import importlib
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT / 'web') not in sys.path:
    sys.path.insert(0, str(ROOT / 'web'))

from pgadmin.cdeadmin.providers import (  # noqa: E402
    BUILTIN_PACKAGES, browse_builders as b)
from pgadmin.cdeadmin.sdk.actual_engine import (  # noqa: E402
    ActualEnginePilotProvider, PilotProfile, PilotProviderError,
)
from pgadmin.cdeadmin.sdk.browse import (  # noqa: E402
    BrowseUnavailable, path_columns)

PROVIDERS = ROOT / 'web/pgadmin/cdeadmin/providers'


def res(kind, path, native=None, **extra):
    return {'resource_kind': kind, 'display_name': path[-1],
            'display_path': list(path), 'native': native or {}, **extra}


def build(builder, resource, catalog=(), language=None):
    return builder(None, resource, resource.get('native', {}),
                   list(catalog), language)


# -- Manifests and builders agree --------------------------------------------

def _declarations():
    for manifest, module in BUILTIN_PACKAGES:
        document = json.loads((PROVIDERS / manifest).read_text())
        kinds = document['registration'].get('browse_data', {}).get(
            'resource_kinds', [])
        yield manifest, module, document['identity']['profile_id'], kinds


def test_every_connector_but_legacy_postgresql_declares_browse_data():
    declared = {profile: kinds for _m, _mod, profile, kinds in _declarations()}
    assert declared.pop('postgresql-native') == []
    assert all(declared.values()), declared
    assert len(declared) == 26


@pytest.mark.parametrize('manifest,module,profile_id,kinds',
                         [item for item in _declarations() if item[3]])
def test_declared_kinds_are_profile_kinds_with_a_builder(
        manifest, module, profile_id, kinds):
    loaded = importlib.import_module(module)
    profiles = [value for value in vars(loaded).values()
                if isinstance(value, PilotProfile) and
                value.profile_id == profile_id]
    assert len(profiles) == 1, profile_id
    assert set(kinds) <= set(profiles[0].resource_kinds), (
        set(kinds) - set(profiles[0].resource_kinds))
    providers = [value for value in vars(loaded).values()
                 if isinstance(value, type) and
                 issubclass(value, ActualEnginePilotProvider) and
                 value.__module__ == loaded.__name__ and
                 value._browse_text is not
                 ActualEnginePilotProvider._browse_text]
    assert providers, f'{module} has no Browse data builder'


# -- Shared helpers ----------------------------------------------------------

def test_path_columns_orders_by_position_and_skips_other_relations():
    table = res('table', ['service', 'assets'])
    catalog = [
        res('column', ['service', 'assets', 'tag'], {'ordinal_position': 2}),
        res('column', ['service', 'assets', 'id'], {'ordinal_position': 1}),
        res('column', ['service', 'other', 'x'], {'ordinal_position': 1}),
        res('index', ['service', 'assets', 'pk'], {}),
    ]
    assert path_columns(table, catalog) == ['id', 'tag']
    # Without positions on every column, catalog order is kept.
    catalog[0]['native'] = {}
    assert path_columns(table, catalog) == ['tag', 'id']


def test_admitted_resources_are_read_from_their_extension():
    table = {'resource_kind': 'table', 'display_name': 'ASSETS',
             'display_path': ['ASSETS'],
             'extensions': {'firebird': {'native': {'system_object': False}}}}
    column = {'resource_kind': 'column', 'display_name': 'ID',
              'display_path': ['ASSETS', 'ID'],
              'extensions': {'firebird': {'native': {'position': 0}}}}
    assert build(b.firebird, table, [column]) == 'SELECT "ID"\nFROM "ASSETS"'


# -- Native-editor SQL connectors -------------------------------------------

def test_firebird_lists_columns_in_position_order():
    table = res('table', ['ASSETS'])
    catalog = [res('column', ['ASSETS', 'TAG'], {'position': 1}),
               res('column', ['ASSETS', 'Mixed "Case"'], {'position': 2}),
               res('column', ['ASSETS', 'ASSET_ID'], {'position': 0})]
    assert build(b.firebird, table, catalog) == (
        'SELECT "ASSET_ID", "TAG", "Mixed ""Case"""\nFROM "ASSETS"')


def test_firebird_dialect_1_writes_regular_names_and_refuses_others():
    table = res('table', ['ASSETS'], client_sql_dialect=1)
    catalog = [res('column', ['ASSETS', 'ASSET_ID'], {'position': 0})]
    assert build(b.firebird, table, catalog) == 'SELECT ASSET_ID\nFROM ASSETS'
    catalog.append(res('column', ['ASSETS', 'lower'], {'position': 1}))
    with pytest.raises(BrowseUnavailable, match='SQL dialect 1 cannot name'):
        build(b.firebird, table, catalog)


def test_mysql_family_uses_backticks_and_catalog_order():
    table = res('table', ['shop', 'order`s'])
    catalog = [res('column', ['shop', 'order`s', 'id']),
               res('column', ['shop', 'order`s', 'total'])]
    assert build(b.mysql_family, table, catalog) == (
        'SELECT `id`, `total`\nFROM `shop`.`order``s`')


def test_sqlite_leaves_out_hidden_virtual_table_columns():
    table = res('table', ['main', 'docs'])

    def meta(position, hidden=0):
        return {'catalog_metadata': {
            'ordinal_position': position, 'hidden': hidden}}
    catalog = [res('column', ['main', 'docs', 'body'], meta(0)),
               res('column', ['main', 'docs', 'rank'], meta(1, hidden=1)),
               res('column', ['main', 'docs', 'total'], meta(2, hidden=3))]
    assert build(b.sqlite, table, catalog) == (
        'SELECT "body", "total"\nFROM "main"."docs"')


def test_duckdb_qualifies_with_database_and_schema():
    view = res('view', ['memory', 'main', 'v'])
    catalog = [res('column', ['memory', 'main', 'v', 'a'],
                   {'catalog_metadata': {'ordinal_position': 1}})]
    assert build(b.duckdb, view, catalog) == (
        'SELECT "a"\nFROM "memory"."main"."v"')


# -- Wire-compatible distributed SQL ----------------------------------------

def test_cockroachdb_drops_engine_hidden_columns():
    table = res('table', ['service', 'customers'],
                {'table_type': 'BASE TABLE'})
    catalog = [
        res('column', ['service', 'customers', 'id'], {'ordinal_position': 1}),
        res('column', ['service', 'customers', 'rowid'],
            {'ordinal_position': 2, 'hidden': True}),
        res('column', ['service', 'customers', 'name'],
            {'ordinal_position': 3})]
    assert build(b.cockroachdb, table, catalog) == (
        'SELECT "id", "name"\nFROM "service"."customers"')


def test_materialized_views_use_their_column_names():
    view = res('materialized-view', ['service', 'workload'],
               {'column_names': ['asset_id', 'open_orders']})
    for builder in (b.cockroachdb, b.yugabytedb):
        assert build(builder, view) == (
            'SELECT "asset_id", "open_orders"\nFROM "service"."workload"')


def test_yugabytedb_foreign_table():
    table = res('foreign-table', ['ext', 'remote'])
    catalog = [res('column', ['ext', 'remote', 'k'], {'ordinal_position': 1})]
    assert build(b.yugabytedb, table, catalog) == (
        'SELECT "k"\nFROM "ext"."remote"')


@pytest.mark.parametrize('builder', [b.tidb, b.vitess, b.dolt])
def test_mysql_wire_tables_and_sequences(builder):
    table = res('table', ['cdeadmin_demo', 'customers'],
                {'table_type': 'BASE TABLE'})
    catalog = [res('column', ['cdeadmin_demo', 'customers', 'customer_id'],
                   {'ordinal_position': 1}),
               res('column', ['cdeadmin_demo', 'customers', 'name'],
                   {'ordinal_position': 2})]
    assert build(builder, table, catalog) == (
        'SELECT `customer_id`, `name`\nFROM `cdeadmin_demo`.`customers`')
    with pytest.raises(BrowseUnavailable, match='sequence'):
        build(builder, res('table', ['d', 's'], {'table_type': 'SEQUENCE'}))


# -- Other SQL and CQL -------------------------------------------------------

def test_clickhouse_orders_by_position_and_skips_ephemeral_columns():
    table = res('table', ['table', 'cdeadmin_demo', 'work_orders'],
                {'database': 'cdeadmin_demo', 'name': 'work_orders'})

    def column(name, position, kind=''):
        return res(
            'column', ['column', 'cdeadmin_demo', 'work_orders', name],
            {'database': 'cdeadmin_demo', 'table': 'work_orders',
             'name': name, 'position': position, 'default_kind': kind})
    catalog = [column('status', 2), column('id', 1),
               column('scratch', 3, 'EPHEMERAL'), column('total', 4, 'ALIAS'),
               res('column', ['column', 'other', 'work_orders', 'x'],
                   {'database': 'other', 'table': 'work_orders', 'name': 'x',
                    'position': 1})]
    assert build(b.clickhouse, table, catalog) == (
        'SELECT `id`, `status`, `total`\nFROM `cdeadmin_demo`.`work_orders`')


def test_cassandra_table_and_materialized_view():
    table = res('table', ['cassandra', 'keyspace', 'cdeadmin_demo', 'table',
                          'work_orders'],
                {'keyspace_name': 'cdeadmin_demo', 'table_name': 'work_orders',
                 'columns': [{'column_name': 'status'},
                             {'column_name': 'work_order_id'}]})
    assert build(b.cassandra, table) == (
        'SELECT "status", "work_order_id"\nFROM "cdeadmin_demo"."work_orders"')
    view = res('materialized-view', ['cassandra', 'keyspace', 'cdeadmin_demo',
                                     'materialized-view', 'by_status'],
               {'keyspace_name': 'cdeadmin_demo', 'view_name': 'by_status'})
    catalog = [res('column', ['c', 'by_status', 'status'],
                   {'keyspace_name': 'cdeadmin_demo',
                    'table_name': 'by_status', 'column_name': 'status'})]
    assert build(b.cassandra, view, catalog) == (
        'SELECT "status"\nFROM "cdeadmin_demo"."by_status"')


def test_ycql_qualifies_from_native_keyspace_not_the_path():
    table = res('table', ['yugabytedb', 'ycql', 'keyspace', 'ks', 'table', 't',
                          'table', 't'],
                {'keyspace_name': 'ks', 'table_name': 't',
                 'columns': [{'column_name': 'k'}, {'column_name': 'v'}]})
    assert build(b.yugabytedb_ycql, table) == 'SELECT "k", "v"\nFROM "ks"."t"'


def test_xtdb_leaves_out_temporal_columns():
    table = res('table', ['table', 'xtdb', 'public.work_orders'],
                {'schema': 'public', 'table': 'work_orders', 'columns': [
                    {'name': '_id', 'temporal': False},
                    {'name': '_system_from', 'temporal': True},
                    {'name': 'status', 'temporal': False}]})
    assert build(b.xtdb, table) == (
        'SELECT "_id", "status"\nFROM "public"."work_orders"')


def test_immudb_names_the_table_unqualified():
    table = res('table', ['public', 'work_orders'],
                {'columns': [{'name': 'id'}, {'name': 'key'}]})
    assert build(b.immudb, table) == 'SELECT "id", "key"\nFROM "work_orders"'


def test_influxdb_sql_and_influxql_in_the_session_database():
    table = res('table', ['database', 'demo', 'table', 'sensor'],
                {'database': 'demo', 'table_name': 'sensor'},
                route={'database': 'demo'})

    def column(name):
        return res('column', ['x', name], {
            'database': 'demo', 'table': 'sensor', 'column_name': name})
    catalog = [column('asset'), column('temperature'), column('time')]
    assert build(b.influxdb, table, catalog, 'influxdb3-sql') == (
        'SELECT "asset", "temperature", "time"\nFROM "sensor"',
        'influxdb3-sql')
    assert build(b.influxdb, table, catalog, 'influxdb3-influxql') == (
        'SELECT "asset", "temperature"\nFROM "sensor"', 'influxdb3-influxql')
    table['route'] = {'database': 'other'}
    with pytest.raises(BrowseUnavailable, match='reads database other'):
        build(b.influxdb, table, catalog)


def test_apache_ignite_uses_the_schema_envelope():
    table = res('table', ['PUBLIC', 'CITY'],
                {'SCHEMA_NAME': 'PUBLIC', 'TABLE_NAME': 'CITY'})
    catalog = [res('column', ['PUBLIC', 'CITY'],
                   {'SCHEMA_NAME': 'PUBLIC', 'TABLE_NAME': 'CITY',
                    'COLUMN_NAME': name}) for name in ('ID', 'NAME')]
    assert json.loads(build(b.apache_ignite, table, catalog)) == {
        'operation': 'sql', 'schema': 'PUBLIC',
        'source': 'SELECT "ID", "NAME"\nFROM "PUBLIC"."CITY"'}
    view = res('view', ['APP', 'V'], {'SCHEMA_NAME': 'APP', 'VIEW_NAME': 'V'})
    assert json.loads(build(b.apache_ignite, view))['source'] == (
        'SELECT *\nFROM "APP"."V"')


def test_opensearch_sql_and_ppl_list_mapping_fields():
    index = res('index', ['search', 'index', 'work-orders'])
    mapping = res('mapping', ['search', 'mapping', 'work-orders'], {
        'mapping': {'properties': {'asset_id': {}, 'status': {}}}})
    assert build(b.opensearch_sql_ppl, index, [mapping]) == (
        'SELECT `asset_id`, `status`\nFROM `work-orders`', 'opensearch-sql')
    assert build(b.opensearch_sql_ppl, index, [mapping], 'opensearch-ppl') == (
        'source=`work-orders` | fields `asset_id`, `status`', 'opensearch-ppl')
    alias = res('alias', ['search', 'alias', 'work-orders', 'current'],
                {'index': 'work-orders'})
    assert build(b.opensearch_sql_ppl, alias, [mapping])[0] == (
        'SELECT `asset_id`, `status`\nFROM `current`')


# -- Document, graph, search, vector and key-value --------------------------

def test_mongodb_find_every_document():
    collection = res('collection', ['MongoDB', 'demo', 'work_orders'],
                     {'database': 'demo', 'collection': 'work_orders'})
    assert json.loads(build(b.mongodb, collection)) == {
        'operation': 'find', 'database': 'demo', 'collection': 'work_orders',
        'filter': {}}


def test_neo4j_labels_and_relationship_types():
    assert build(b.neo4j, res('label', ['neo4j', 'label', 'Work`Order'])) == (
        'MATCH (n:`Work``Order`)\nRETURN n')
    assert build(b.neo4j, res('relationship-type',
                              ['neo4j', 'relationship-type', 'OWNED_BY'])) == (
        'MATCH ()-[r:`OWNED_BY`]->()\nRETURN r')


def test_opensearch_scrolls_every_document():
    index = res('index', ['index', 'cdeadmin-work-orders-000001'])
    assert json.loads(build(b.opensearch, index)) == {
        'operation': 'scan', 'index': 'cdeadmin-work-orders-000001',
        'body': {'query': {'match_all': {}}}}


def test_milvus_collections_and_partitions_in_the_session_database():
    collection = res('collection', ['database', 'demo', 'collection', 'vec'],
                     {'database': 'demo'}, route={'database': 'demo'})
    assert json.loads(build(b.milvus, collection)) == {
        'operation': 'query', 'collection_name': 'vec', 'filter': '',
        'output_fields': ['*']}
    partition = res('partition', ['database', 'demo', 'collection', 'vec',
                                  'partition', 'p1'],
                    {'database': 'demo', 'collection_name': 'vec'})
    assert json.loads(build(b.milvus, partition))['partition_names'] == ['p1']
    collection['route'] = {'database': 'other'}
    with pytest.raises(BrowseUnavailable, match='reads database other'):
        build(b.milvus, collection)


def test_redis_reads_each_key_by_type():
    def key(data_type, name='cdeadmin:demo:1'):
        return res('key', [name], {'key': name, 'data_type': data_type})
    assert build(b.redis, key('hash')) == 'HGETALL cdeadmin:demo:1'
    assert build(b.redis, key('list')) == 'LRANGE cdeadmin:demo:1 0 -1'
    assert build(b.redis, key('sorted-set')) == (
        'ZRANGE cdeadmin:demo:1 0 -1 WITHSCORES')
    assert build(b.redis, key('string', "it's a key")) == (
        'GET \'it\'"\'"\'s a key\'')
    binary = res('key', ['k'], {'key': {'$binary': 'AP8='},
                                'data_type': 'set'})
    assert json.loads(build(b.redis, binary)) == {
        'operation': 'command', 'arguments': ['SMEMBERS', {'$binary': 'AP8='}]}
    with pytest.raises(BrowseUnavailable):
        build(b.redis, key('vector-set'))


def test_tikv_scans_the_whole_key_space():
    source = build(b.tikv, res('key-range', ['bounded-key-browser']))
    assert json.loads(source) == {
        'operation': 'scan_all', 'start_key': '', 'end_key': ''}


def test_foundationdb_ranges():
    whole = json.loads(build(b.foundationdb,
                             res('key-range', ['bounded-key-browser'])))
    assert base64.b64decode(whole['end']) == b'\xff'
    prefix = base64.b64encode(b'\x15\x01\xff').decode()
    sub = json.loads(build(b.foundationdb, res(
        'subspace', ['demo', 'data'], {'prefix_base64': prefix})))
    assert base64.b64decode(sub['begin']) == b'\x15\x01\xff'
    assert base64.b64decode(sub['end']) == b'\x15\x02'
    assert sub['limit'] == 0


def test_kinds_a_builder_does_not_read_are_refused():
    with pytest.raises(BrowseUnavailable, match='cannot read a keyspace'):
        build(b.tikv, res('keyspace', ['k']))
    with pytest.raises(BrowseUnavailable, match='cannot read a document'):
        build(b.xtdb, res('document', ['d']))


# -- The provider entry point ------------------------------------------------

class _Provider(ActualEnginePilotProvider):
    _browse_text = b.neo4j

    def __init__(self):  # no client: only the Browse data path is used
        self.profile = type('P', (), {'language_profile': 'cypher'})()

    def _require(self, permission, scope='endpoint'):
        self.required = (permission, scope)


def test_provider_returns_text_and_language_and_reports_refusals():
    provider = _Provider()
    assert provider.browse_source(res('label', ['neo4j', 'label', 'A'])) == {
        'source': 'MATCH (n:`A`)\nRETURN n', 'language_profile': 'cypher'}
    assert provider.required == ('data_read', 'resource')
    with pytest.raises(PilotProviderError, match='cannot read a node'):
        provider.browse_source(res('node', ['n']))
    with pytest.raises(PilotProviderError, match='not available'):
        ActualEnginePilotProvider.browse_source(
            type('Bare', (ActualEnginePilotProvider,), {
                '__init__': lambda self: None,
                '_require': lambda self, *a: None,
                'profile': _Provider().profile})(),
            res('table', ['t']))

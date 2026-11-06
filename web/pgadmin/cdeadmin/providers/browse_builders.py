##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Browse data text for each connector (owner direction 2026-11-06).

Each function is a provider's ``_browse_text(resource, native, catalog,
language)``: it returns the text, in the connector's own editor language,
that reads every record of one resource with all of its columns or fields.
CDEadmin puts the text in the editor and never runs it. The resource kinds
each connector supports are declared in its provider manifest
(registration.browse_data); a kind not handled here raises BrowseUnavailable.

The forms follow what each connector's studio execute path accepts. Where a
column list is known it is listed; otherwise the language's whole-record read
is used (``SELECT *``, a document find, ``RETURN n``, a key range).
"""

from __future__ import annotations

import re
import shlex

from pgadmin.cdeadmin.sdk.browse import (
    BrowseUnavailable, json_source, native_of, path_columns, quote,
    sql_select,
)


def _kind(resource, *kinds):
    kind = resource.get('resource_kind')
    if kind not in kinds:
        raise BrowseUnavailable(
            f'Browse data cannot read a {kind or "resource"}.')
    return kind


def _double(name):
    return quote(name, '"')


def _backtick(name):
    return quote(name, '`')


def _route(resource):
    route = resource.get('route')
    return route if isinstance(route, dict) else {}


def _catalog_columns(catalog, match, *, order=None, exclude=None,
                     kind='column', name='name'):
    """Column names of catalog ``kind`` resources whose native matches."""
    found = [native_of(item) for item in catalog
             if item.get('resource_kind') == kind and match(native_of(item))]
    found = [item for item in found if not (exclude and exclude(item))]
    if order is not None and all(isinstance(item.get(order), int)
                                 for item in found):
        found = sorted(found, key=lambda item: item[order])
    return [str(item.get(name)) for item in found]


# -- Embedded and native-editor SQL connectors --------------------------------

_FIREBIRD_REGULAR = re.compile(r'[A-Z][A-Z0-9_$]*')


def firebird(self, resource, native, catalog, language):
    _kind(resource, 'table', 'view')
    columns = path_columns(resource, catalog)
    if resource.get('client_sql_dialect') == 1:
        # SQL dialect 1 has no delimited identifiers: a double-quoted name
        # is a string. Only names that are already regular can be written.
        names = [*resource.get('display_path', ()), *columns]
        irregular = [name for name in names
                     if not _FIREBIRD_REGULAR.fullmatch(name)]
        if irregular:
            raise BrowseUnavailable(
                'SQL dialect 1 cannot name ' + ', '.join(irregular[:3]) +
                '; switch the editor to SQL dialect 3.')
        return sql_select(columns, resource['display_path'], str)
    return sql_select(columns, resource['display_path'], _double)


def mysql_family(self, resource, native, catalog, language):
    _kind(resource, 'table', 'view')
    # Backticks delimit identifiers in every sql_mode, ANSI_QUOTES included.
    return sql_select(path_columns(resource, catalog),
                      resource['display_path'], _backtick)


def sqlite(self, resource, native, catalog, language):
    _kind(resource, 'table', 'view')
    # Hidden columns of virtual tables (hidden = 1) are not in SELECT *;
    # generated columns (2, 3) are.
    columns = path_columns(resource, catalog, exclude=lambda column: (
        column.get('catalog_metadata') or {}).get('hidden') == 1)
    return sql_select(columns, resource['display_path'], _double)


def duckdb(self, resource, native, catalog, language):
    _kind(resource, 'table', 'view')
    return sql_select(path_columns(resource, catalog),
                      resource['display_path'], _double)


# -- PostgreSQL-wire and MySQL-wire distributed SQL ---------------------------

def _pg_wire(resource, native, catalog):
    kind = resource.get('resource_kind')
    if kind == 'materialized-view' and isinstance(
            native.get('column_names'), list):
        columns = [str(name) for name in native['column_names']]
    else:
        # Engine-owned columns (CockroachDB rowid, crdb_internal_*) are
        # not part of SELECT *.
        columns = path_columns(resource, catalog,
                               exclude=lambda column: column.get('hidden'))
    return sql_select(columns, resource['display_path'], _double)


def cockroachdb(self, resource, native, catalog, language):
    _kind(resource, 'table', 'view', 'materialized-view')
    return _pg_wire(resource, native, catalog)


def yugabytedb(self, resource, native, catalog, language):
    _kind(resource, 'table', 'view', 'materialized-view', 'foreign-table')
    return _pg_wire(resource, native, catalog)


def _mysql_wire(resource, native, catalog):
    if resource.get('resource_kind') == 'table' and str(
            native.get('table_type') or '').upper() == 'SEQUENCE':
        raise BrowseUnavailable('A sequence has no rows to browse.')
    return sql_select(path_columns(resource, catalog),
                      resource['display_path'], _backtick)


def tidb(self, resource, native, catalog, language):
    _kind(resource, 'table', 'view')
    return _mysql_wire(resource, native, catalog)


def vitess(self, resource, native, catalog, language):
    _kind(resource, 'table', 'view')
    return _mysql_wire(resource, native, catalog)


def dolt(self, resource, native, catalog, language):
    _kind(resource, 'table', 'view')
    return _mysql_wire(resource, native, catalog)


# -- Other SQL and CQL connectors ---------------------------------------------

def clickhouse(self, resource, native, catalog, language):
    _kind(resource, 'table', 'view', 'materialized-view')
    database, table = native.get('database'), native.get('name')
    columns = _catalog_columns(
        catalog, lambda column: (column.get('database') == database and
                                 column.get('table') == table),
        order='position',
        # EPHEMERAL columns exist only for inserts and cannot be selected.
        exclude=lambda column: str(
            column.get('default_kind') or '').upper() == 'EPHEMERAL')
    return sql_select(columns, [database, table], _backtick)


def _cql(native, catalog, kind, name):
    keyspace = native.get('keyspace_name')
    if kind == 'table' and isinstance(native.get('columns'), list):
        columns = [str(column.get('column_name'))
                   for column in native['columns']]
    else:
        columns = _catalog_columns(
            catalog, lambda column: (
                column.get('keyspace_name') == keyspace and
                column.get('table_name') == name),
            name='column_name')
    return sql_select(columns, [keyspace, name], _double)


def cassandra(self, resource, native, catalog, language):
    kind = _kind(resource, 'table', 'materialized-view')
    name = (native.get('table_name') if kind == 'table'
            else native.get('view_name')) or resource.get('display_name')
    return _cql(native, catalog, kind, name)


def yugabytedb_ycql(self, resource, native, catalog, language):
    kind = _kind(resource, 'table')
    return _cql(native, catalog, kind, native.get('table_name'))


def xtdb(self, resource, native, catalog, language):
    _kind(resource, 'table')
    # SELECT * in XTDB leaves out the valid/system time columns.
    columns = [str(column.get('name')) for column in
               native.get('columns') or () if not column.get('temporal')]
    return sql_select(columns, [native.get('schema'), native.get('table')],
                      _double)


def immudb(self, resource, native, catalog, language):
    _kind(resource, 'table')
    # immudb SQL has no schema-qualified names.
    columns = [str(column.get('name'))
               for column in native.get('columns') or ()]
    return sql_select(columns, [resource.get('display_name')], _double)


def influxdb(self, resource, native, catalog, language):
    _kind(resource, 'table')
    database = native.get('database') or native.get('database_name')
    table = native.get('table_name') or resource.get('display_name')
    session_database = _route(resource).get('database')
    if session_database and database != session_database:
        raise BrowseUnavailable(
            f'The query editor reads database {session_database}; this '
            f'table is in {database}.')
    columns = _catalog_columns(
        catalog, lambda column: (column.get('database') == database and
                                 column.get('table') == table),
        name='column_name')
    if language == 'influxdb3-influxql':
        # InfluxQL returns time with every row and selects fields and tags.
        return (sql_select([name for name in columns if name != 'time'],
                           [table], _double), language)
    return sql_select(columns, [table], _double), 'influxdb3-sql'


def apache_ignite(self, resource, native, catalog, language):
    kind = _kind(resource, 'table', 'view')
    schema = native.get('SCHEMA_NAME') or (
        resource.get('display_path') or ['PUBLIC'])[0]
    name = (native.get('TABLE_NAME') or native.get('VIEW_NAME') or
            resource.get('display_name'))
    columns = [] if kind == 'view' else _catalog_columns(
        catalog, lambda column: (column.get('SCHEMA_NAME') == schema and
                                 column.get('TABLE_NAME') == name),
        name='COLUMN_NAME')
    # The JSON envelope is the editor's form that sets the schema.
    return json_source({'operation': 'sql', 'schema': schema,
                        'source': sql_select(columns, [schema, name],
                                             _double)})


def opensearch_sql_ppl(self, resource, native, catalog, language):
    kind = _kind(resource, 'index', 'alias')
    index = (native.get('index') if kind == 'alias'
             else resource.get('display_name'))
    target = resource.get('display_name') if kind == 'alias' else index
    mapping = next((native_of(item) for item in catalog
                    if item.get('resource_kind') == 'mapping' and
                    item.get('display_name') == index), {})
    fields = [str(name) for name in (
        (mapping.get('mapping') or {}).get('properties') or {})]
    if language == 'opensearch-ppl':
        source = 'source=' + _backtick(target)
        if fields:
            source += ' | fields ' + ', '.join(
                _backtick(name) for name in fields)
        return source, language
    return sql_select(fields, [target], _backtick), 'opensearch-sql'


# -- Document, graph, search and vector connectors ----------------------------

def mongodb(self, resource, native, catalog, language):
    _kind(resource, 'collection', 'view')
    return json_source({'operation': 'find',
                        'database': native.get('database'),
                        'collection': native.get('collection') or
                        resource.get('display_name'),
                        'filter': {}})


def neo4j(self, resource, native, catalog, language):
    kind = _kind(resource, 'label', 'relationship-type')
    name = resource.get('display_name')
    if kind == 'label':
        return f'MATCH (n:{_backtick(name)})\nRETURN n'
    return f'MATCH ()-[r:{_backtick(name)}]->()\nRETURN r'


def opensearch(self, resource, native, catalog, language):
    _kind(resource, 'index', 'alias', 'data-stream')
    # A scroll reads every document; a plain search stops at its size.
    return json_source({'operation': 'scan',
                        'index': resource.get('display_name'),
                        'body': {'query': {'match_all': {}}}})


def milvus(self, resource, native, catalog, language):
    kind = _kind(resource, 'collection', 'partition')
    session_database = _route(resource).get('database')
    if session_database and native.get('database') not in (
            None, session_database):
        raise BrowseUnavailable(
            f'The query editor reads database {session_database}; this '
            f'collection is in {native.get("database")}.')
    command = {'operation': 'query',
               'collection_name': (native.get('collection_name')
                                   if kind == 'partition' else
                                   resource.get('display_name')),
               'filter': '', 'output_fields': ['*']}
    if kind == 'partition':
        command['partition_names'] = [resource.get('display_name')]
    return json_source(command)


_REDIS_READS = {
    'string': ('GET',), 'hash': ('HGETALL',), 'list': ('LRANGE', '0', '-1'),
    'set': ('SMEMBERS',), 'sorted-set': ('ZRANGE', '0', '-1', 'WITHSCORES'),
    'zset': ('ZRANGE', '0', '-1', 'WITHSCORES'),
    'stream': ('XRANGE', '-', '+'),
}


def redis(self, resource, native, catalog, language):
    kind = _kind(resource, 'key', 'database')
    if kind == 'database':
        return json_source({'operation': 'scan', 'match': '*'})
    read = _REDIS_READS.get(str(native.get('data_type') or ''))
    if read is None:
        raise BrowseUnavailable(
            f'Browse data cannot read a Redis {native.get("data_type")} key.')
    key = native.get('key')
    command, *rest = read
    if isinstance(key, dict):
        # A key that is not printable text travels as a binary token.
        return json_source({'operation': 'command',
                            'arguments': [command, key, *rest]})
    return ' '.join([command, shlex.quote(str(key)), *rest])


def tikv(self, resource, native, catalog, language):
    _kind(resource, 'key-range')
    # scan_all pages through the whole raw key space.
    return json_source({'operation': 'scan_all', 'start_key': '',
                        'end_key': ''})


def _strinc(prefix: bytes) -> bytes:
    stripped = prefix.rstrip(b'\xff')
    if not stripped:
        raise BrowseUnavailable('The key prefix has no upper bound.')
    return stripped[:-1] + bytes([stripped[-1] + 1])


def foundationdb(self, resource, native, catalog, language):
    import base64
    kind = _kind(resource, 'key-range', 'subspace')
    if kind == 'key-range':
        return json_source({'operation': 'range', 'begin': '',
                            'end': base64.b64encode(b'\xff').decode(),
                            'end_encoding': 'base64', 'limit': 0})
    prefix = native.get('prefix_base64')
    if not isinstance(prefix, str) or not prefix:
        raise BrowseUnavailable('The subspace prefix is unknown.')
    end = base64.b64encode(_strinc(base64.b64decode(prefix))).decode()
    return json_source({'operation': 'range', 'begin': prefix,
                        'begin_encoding': 'base64', 'end': end,
                        'end_encoding': 'base64', 'limit': 0})

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

Names are delimited only where the dialect needs it (owner direction
2026-11-06): a name is written bare when it is a regular identifier in the
case the dialect folds to and is not a keyword the dialect's contract
reserves (SqlNames). Where a contract does not say which keywords are
reserved, every keyword is delimited; a connector with no keyword list in
its contract delimits every name.
"""

from __future__ import annotations

import re
import shlex

from pgadmin.cdeadmin.sdk.browse import (
    BrowseUnavailable, SqlNames, contract_keywords, json_source, native_of,
    path_columns, quote, sql_select,
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


# Undelimited names each dialect reads back unchanged. Only ASCII names are
# written bare. PostgreSQL-wire SQL and CQL fold undelimited names to lower
# case and Firebird (SQL dialect 3) to upper case; SQLite and DuckDB match
# names without regard to case, and quoting never changes a name's case in
# the MySQL family. A MySQL-family name may not start with an underscore,
# which can begin a character set introducer (_utf8mb4); CQL and immudb
# names start with a letter.
_LOWER = re.compile(r'[a-z_][a-z0-9_]*')
_LOWER_LETTER = re.compile(r'[a-z][a-z0-9_]*')
_UPPER = re.compile(r'[A-Z][A-Z0-9_$]*')
_ANY_CASE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
_MYSQL = re.compile(r'[A-Za-z][A-Za-z0-9_]*')


# Which contract keywords a name must not be. Only unreserved keywords are
# written bare in the PostgreSQL-derived grammars, as PostgreSQL's
# quote_ident does; Cassandra quotes the reserved keywords its own
# identifier quoting does. A contract row with no classification counts as
# reserved, so MariaDB, Vitess, SQLite and immudb delimit every keyword.
# The MySQL family's classifications do not say where a keyword can stand
# bare: MySQL 9.7.0 rejected eight keywords it marks non-reserved in a
# SELECT list (CUBE, EXTERNAL, MANUAL, PARALLEL, QUALIFY and TABLESAMPLE
# anywhere; SQL_BUFFER_RESULT and SQL_NO_CACHE first), and TiDB 8.5.6
# rejected three of its unreserved keywords first in one (SQL_BUFFER_RESULT,
# SQL_CACHE, SQL_NO_CACHE). MySQL, TiDB and Dolt delimit every keyword.

def _pg_reserved(row):  # pg_get_keywords(): CockroachDB, YugabyteDB YSQL
    return row.get('category_code') != 'U'


def _duckdb_reserved(row):  # duckdb_keywords()
    return row.get('category') != 'unreserved'


def _ycql_reserved(row):
    return row.get('category') != 'UNRESERVED_KEYWORD'


def _cassandra_reserved(row):
    return row.get('category') == 'reserved_keyword'


def _firebird_reserved(row):
    return row.get('non_reserved') is not True


def _every_keyword(row):
    return True


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

def firebird(self, resource, native, catalog, language):
    _kind(resource, 'table', 'view')
    columns = path_columns(resource, catalog)
    names = SqlNames('"', regular=_UPPER,
                     reserved=contract_keywords(self, _firebird_reserved))
    if resource.get('client_sql_dialect') == 1:
        # SQL dialect 1 has no delimited identifiers: a double-quoted name
        # is a string. Only names that need no quotes can be written.
        irregular = [name for name in
                     [*resource.get('display_path', ()), *columns]
                     if not names.bare(name)]
        if irregular:
            raise BrowseUnavailable(
                'SQL dialect 1 cannot name ' + ', '.join(irregular[:3]) +
                '; switch the editor to SQL dialect 3.')
        return sql_select(columns, resource['display_path'], str)
    return sql_select(columns, resource['display_path'], names)


def mysql_names(provider):
    """MySQL-family names (also the SQL builder's).

    Backticks delimit identifiers in every sql_mode, ANSI_QUOTES included.
    """
    return SqlNames('`', regular=_MYSQL,
                    reserved=contract_keywords(provider, _every_keyword))


def mysql_family(self, resource, native, catalog, language):
    _kind(resource, 'table', 'view')
    return sql_select(path_columns(resource, catalog),
                      resource['display_path'], mysql_names(self))


def _sqlite_keywords(provider):
    # The keywords of the SQLite library that runs the editor's statements,
    # as the provider reports them; the contract's list when it cannot. The
    # provider owns the lookup, so shared code imports no provider package.
    report = getattr(provider, 'browse_runtime_keywords', None)
    words = report() if callable(report) else None
    if words is not None:
        return frozenset(str(word).upper() for word in words)
    return contract_keywords(provider, _every_keyword)


def sqlite_names(self):
    """SQLite names, delimited only when needed (also the SQL builder's)."""
    return SqlNames('"', regular=_ANY_CASE, reserved=_sqlite_keywords(self))


def duckdb_names(self):
    """DuckDB names, delimited only when needed (also the SQL builder's)."""
    return SqlNames('"', regular=_ANY_CASE,
                    reserved=contract_keywords(self, _duckdb_reserved))


def sqlite(self, resource, native, catalog, language):
    _kind(resource, 'table', 'view')
    # Hidden columns of virtual tables (hidden = 1) are not in SELECT *;
    # generated columns (2, 3) are.
    columns = path_columns(resource, catalog, exclude=lambda column: (
        column.get('catalog_metadata') or {}).get('hidden') == 1)
    return sql_select(columns, resource['display_path'], sqlite_names(self))


def duckdb(self, resource, native, catalog, language):
    _kind(resource, 'table', 'view')
    return sql_select(path_columns(resource, catalog),
                      resource['display_path'], duckdb_names(self))


# -- PostgreSQL-wire and MySQL-wire distributed SQL ---------------------------

def _pg_wire(provider, resource, native, catalog):
    kind = resource.get('resource_kind')
    if kind == 'materialized-view' and isinstance(
            native.get('column_names'), list):
        columns = [str(name) for name in native['column_names']]
    else:
        # Engine-owned columns (CockroachDB rowid, crdb_internal_*) are
        # not part of SELECT *.
        columns = path_columns(resource, catalog,
                               exclude=lambda column: column.get('hidden'))
    return sql_select(columns, resource['display_path'], SqlNames(
        '"', regular=_LOWER,
        reserved=contract_keywords(provider, _pg_reserved)))


def postgresql(self, resource, native, catalog, language):
    """PostgreSQL on the provider tree (M6, 2026-11-11). Names are quoted
    exactly as the inherited Browse data route quotes them: pgAdmin's
    keyword-aware ``Driver.qtIdent`` (owner direction 2026-11-06), so the
    two paths render the same text."""
    _kind(resource, 'table', 'partitioned-table', 'partition', 'view',
          'materialized-view', 'foreign-table')
    from pgadmin.utils.driver.psycopg3 import Driver
    columns = path_columns(resource, catalog)
    # The provider tree's path starts with the database; PostgreSQL reads a
    # relation as schema.name (the inherited route's form).
    relation = list(resource.get('display_path') or ())[-2:]
    return sql_select(columns, relation,
                      lambda name: Driver.qtIdent(None, str(name)))


def cockroachdb(self, resource, native, catalog, language):
    _kind(resource, 'table', 'view', 'materialized-view')
    return _pg_wire(self, resource, native, catalog)


def yugabytedb(self, resource, native, catalog, language):
    _kind(resource, 'table', 'view', 'materialized-view', 'foreign-table')
    return _pg_wire(self, resource, native, catalog)


def _mysql_wire(provider, resource, native, catalog):
    if resource.get('resource_kind') == 'table' and str(
            native.get('table_type') or '').upper() == 'SEQUENCE':
        raise BrowseUnavailable('A sequence has no rows to browse.')
    return sql_select(path_columns(resource, catalog),
                      resource['display_path'], mysql_names(provider))


def tidb(self, resource, native, catalog, language):
    _kind(resource, 'table', 'view')
    return _mysql_wire(self, resource, native, catalog)


def vitess(self, resource, native, catalog, language):
    _kind(resource, 'table', 'view')
    return _mysql_wire(self, resource, native, catalog)


def dolt(self, resource, native, catalog, language):
    _kind(resource, 'table', 'view')
    return _mysql_wire(self, resource, native, catalog)


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


def _cql(native, catalog, kind, name, names):
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
    return sql_select(columns, [keyspace, name], names)


def cassandra(self, resource, native, catalog, language):
    kind = _kind(resource, 'table', 'materialized-view')
    name = (native.get('table_name') if kind == 'table'
            else native.get('view_name')) or resource.get('display_name')
    return _cql(native, catalog, kind, name, SqlNames(
        '"', regular=_LOWER_LETTER,
        reserved=contract_keywords(self, _cassandra_reserved)))


def yugabytedb_ycql(self, resource, native, catalog, language):
    kind = _kind(resource, 'table')
    return _cql(native, catalog, kind, native.get('table_name'), SqlNames(
        '"', regular=_LOWER_LETTER,
        reserved=contract_keywords(self, _ycql_reserved)))


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
    return sql_select(columns, [resource.get('display_name')], SqlNames(
        '"', regular=_LOWER_LETTER,
        reserved=contract_keywords(self, _every_keyword)))


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

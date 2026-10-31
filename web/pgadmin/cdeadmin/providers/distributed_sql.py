##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Wire-compatible foundations for distributed SQL providers.

This module shares transport mechanics, not engine identity or semantics.
Every provider supplies its own version parser, profile, metadata extensions,
and administration policy. A ScratchBird-compatible listener follows exactly
the same path as the corresponding reference engine.
"""

from __future__ import annotations

import copy
import hashlib
import re
from typing import Any, Callable, Mapping

from .catalog_presentation import annotate_relation_ownership

from pgadmin.cdeadmin.sdk import (
    RelationalClientConfig,
    RelationalClientError,
    RelationalDBAPIClient,
    load_optional_module,
)
from .relational_admin import (
    RelationalAdministration,
    RelationalAdminDialect,
)


_MYSQL_LITERAL_TYPES = re.compile(
    r'^(tinyint|smallint|mediumint|int|integer|bigint|decimal|numeric|'
    r'float|double|real|bit|bool|boolean|year)\b', re.IGNORECASE)
_MYSQL_TIME_DEFAULTS = re.compile(
    r'^(current_timestamp|now|localtime|localtimestamp)(\(\d*\))?$',
    re.IGNORECASE)


def mysql_default_expression(data_type, default, extra):
    """Render information_schema COLUMN_DEFAULT as a DEFAULT expression.

    The catalog reports a string literal unquoted ('x' as x) and marks
    expression defaults with DEFAULT_GENERATED; an editor needs the clause
    text it would write back.
    """
    if default is None:
        return None
    text = str(default)
    if 'DEFAULT_GENERATED' in str(extra or '').upper() or (
            _MYSQL_TIME_DEFAULTS.match(text)):
        return text
    if _MYSQL_LITERAL_TYPES.match(str(data_type or '')):
        return text
    return "'" + text.replace('\\', '\\\\').replace("'", "''") + "'"


def mysql_grant(grantee, object_type, object_name, privilege, grantable):
    """Native facts for one grant; GRANTEE arrives as 'user'@'host'."""
    principal = '@'.join(
        part.strip("'") for part in str(grantee).split("'@'", 1))
    return {
        'principal': principal, 'object_type': object_type,
        'object_name': object_name, 'privilege': str(privilege),
        'grantable': None if grantable is None else
        str(grantable).upper() == 'YES',
    }


def _schema_where(column, schema, keyword='WHERE'):
    """``(clause, parameters)`` limiting a catalog read to one schema.

    Vitess routes an ``information_schema`` read to the keyspace an equality
    predicate names; with none it reads the session keyspace, and an ``IN``
    list returns no rows (live, 23.0.3). So a schema is always one equality.
    """
    if schema is None:
        return '', ()
    return f'{keyword} {column} = %s ', (schema,)


def mysql_constraint_details(cursor, schema=None):
    """Key columns, references, rules and check clauses per constraint.

    Lets an editor re-open an existing table's constraints. Each catalog is
    optional: a missing one leaves only the constraint type. ``schema`` reads
    one schema only (see ``_schema_where``).
    """
    found = {}
    where, parameters = _schema_where('TABLE_SCHEMA', schema)
    for database, table, name, column, ref_database, ref_table, \
            ref_column in optional_rows(
                cursor,
                'SELECT TABLE_SCHEMA, TABLE_NAME, CONSTRAINT_NAME, '
                'COLUMN_NAME, REFERENCED_TABLE_SCHEMA, REFERENCED_TABLE_NAME, '
                'REFERENCED_COLUMN_NAME '
                f'FROM information_schema.KEY_COLUMN_USAGE {where}'
                'ORDER BY 1, 2, 3, ORDINAL_POSITION', parameters):
        entry = found.setdefault((database, table, name), {'columns': []})
        entry['columns'].append(str(column))
        if ref_table is not None:
            entry['referenced_database'] = str(ref_database)
            entry['referenced_table'] = str(ref_table)
            entry.setdefault('referenced_columns', []).append(
                str(ref_column))
    for database, table, name, update_rule, delete_rule in optional_rows(
            cursor,
            'SELECT CONSTRAINT_SCHEMA, TABLE_NAME, CONSTRAINT_NAME, '
            'UPDATE_RULE, DELETE_RULE '
            'FROM information_schema.REFERENTIAL_CONSTRAINTS ' +
            _schema_where('CONSTRAINT_SCHEMA', schema)[0], parameters):
        entry = found.setdefault((database, table, name), {})
        entry.update(update_rule=str(update_rule),
                     delete_rule=str(delete_rule))
    checks = {
        (database, name): str(clause) for database, name, clause in
        optional_rows(
            cursor,
            'SELECT CONSTRAINT_SCHEMA, CONSTRAINT_NAME, CHECK_CLAUSE '
            'FROM information_schema.CHECK_CONSTRAINTS ' +
            _schema_where('CONSTRAINT_SCHEMA', schema)[0], parameters)
    }
    for database, table, name in optional_rows(
            cursor,
            "SELECT TABLE_SCHEMA, TABLE_NAME, CONSTRAINT_NAME "
            "FROM information_schema.TABLE_CONSTRAINTS "
            "WHERE CONSTRAINT_TYPE = 'CHECK' " +
            _schema_where('TABLE_SCHEMA', schema, 'AND')[0], parameters):
        clause = checks.get((database, name))
        if clause is not None:
            found.setdefault((database, table, name), {})[
                'check_clause'] = clause
    return found


def mysql_procedures(cursor, schema=None):
    """[(schema, name, native)] for stored procedures.

    ``schema`` adds ``ROUTINE_SCHEMA = %s`` (Vitess routes
    ``information_schema`` reads to the keyspace that predicate names).
    """
    where, parameters = '', ()
    if schema is not None:
        where, parameters = 'AND SPECIFIC_SCHEMA = %s ', (schema,)
    found = {}
    for database, routine, mode, name, data_type in optional_rows(
        cursor,
        'SELECT SPECIFIC_SCHEMA, SPECIFIC_NAME, PARAMETER_MODE, '
        'PARAMETER_NAME, DTD_IDENTIFIER FROM information_schema.PARAMETERS '
        f'WHERE PARAMETER_NAME IS NOT NULL {where}'
        'ORDER BY 1, 2, ORDINAL_POSITION', parameters,
    ):
        found.setdefault((database, routine), []).append({
            'name': str(name), 'type': str(data_type),
            'mode': str(mode or 'IN'),
        })
    where = '' if schema is None else 'WHERE ROUTINE_SCHEMA = %s '
    routines = optional_rows(
        cursor,
        'SELECT ROUTINE_SCHEMA, ROUTINE_NAME, ROUTINE_TYPE, DATA_TYPE, '
        'ROUTINE_DEFINITION, SECURITY_TYPE, IS_DETERMINISTIC, '
        'SQL_DATA_ACCESS, ROUTINE_COMMENT '
        f'FROM information_schema.ROUTINES {where}ORDER BY 1, 2', parameters,
    )
    values = []
    for database, name, routine_type, data_type, body, security_type, \
            deterministic, data_access, comment in routines:
        if str(routine_type).upper() != 'PROCEDURE':
            continue
        values.append((database, name, {
            'routine_type': 'PROCEDURE', 'data_type': str(data_type),
            'body': None if body is None else str(body),
            'parameters': found.get((database, name), []),
            'sql_security': str(security_type),
            'deterministic': str(deterministic).upper() == 'YES',
            'data_access': str(data_access),
            'comment': str(comment or ''),
        }))
    return values


def resource(kind, path, name, generation, native=None):
    """Build one provider-native resource before common normalization."""
    parts = [str(item) for item in path]
    item = {
        'resource_id': ':'.join([kind, *parts, str(name)]),
        'resource_kind': kind,
        'display_name': str(name),
        'display_path': [*parts, str(name)],
        'authority_path': [*parts, kind, str(name)],
        'generation': generation,
    }
    if native:
        value = copy.deepcopy(dict(native))
        evidence = copy.deepcopy(value)
        if kind in {
            'database', 'schema', 'table', 'view', 'materialized-view',
            'column', 'index', 'constraint', 'trigger', 'sequence', 'type',
            'procedure', 'function', 'partition', 'region', 'zone',
            'placement-policy', 'resource-group', 'keyspace',
            'cache-template', 'cache', 'data-region', 'sql-schema',
            'configuration', 'directory',
            'collection', 'collection-index', 'key-range',
        } and 'definition' not in value:
            value['definition'] = evidence
        elif kind in {
            'cluster', 'node', 'server', 'replica', 'range', 'tablet',
            'shard', 'topology', 'session', 'transaction', 'lock',
            'changefeed', 'replication-channel', 'job', 'operation',
            'baseline-topology', 'coordinator', 'process', 'store', 'peer',
            'scheduler', 'service', 'compute-task', 'ttl',
        }:
            value['state'] = evidence
        elif kind in {'role', 'user'}:
            value['security'] = evidence
        elif kind == 'privilege':
            value['security'] = evidence
            value['privileges'] = [copy.deepcopy(evidence)]
        elif kind in {'metric', 'statistics', 'table-storage'}:
            value['statistics'] = evidence
        elif kind in {'key', 'revision', 'document'}:
            value['data'] = evidence
        item['native'] = value
    return item


def optional_rows(cursor, source, parameters=()):
    """Read an optional catalog surface without widening its permissions."""
    if getattr(cursor, '_cde_catalog_isolated', False) is True:
        return cursor.cde_optional_rows(source, parameters)
    try:
        cursor.execute(source, parameters)
        return list(cursor.fetchall())
    except Exception:
        try:
            cursor.connection.rollback()
        except Exception:
            pass
        return []


def postgresql_route(route):
    allowed = {
        'host', 'port', 'user', 'dbname', 'connect_timeout', 'sslmode',
        'hostaddr', 'client_encoding', 'options', 'application_name',
        'fallback_application_name', 'keepalives', 'keepalives_idle',
        'keepalives_interval', 'keepalives_count', 'tcp_user_timeout',
        'replication', 'channel_binding', 'gssencmode', 'sslcompression',
        'sslcert', 'sslkey',
        'sslrootcert', 'sslcrl', 'sslcrldir', 'sslsni', 'requirepeer',
        'ssl_min_protocol_version', 'ssl_max_protocol_version',
        'krbsrvname', 'gsslib', 'target_session_attrs',
        'load_balance_hosts', 'gssdelegation', 'require_auth',
        'sslnegotiation', 'sslkeylogfile', 'min_protocol_version',
        'max_protocol_version', 'oauth_issuer', 'oauth_client_id',
        'oauth_scope', 'pool_enabled', 'pool_min_size', 'pool_max_size',
        'pool_acquisition_timeout', 'pool_max_waiting',
        'pool_max_lifetime', 'pool_max_idle', 'pool_reconnect_timeout',
        'pool_workers', 'pool_check_connection',
    }
    result = {key: value for key, value in route.items() if key in allowed}
    if 'database' in route and 'dbname' not in result:
        result['dbname'] = route['database']
    if route.get('route_id'):
        result['cde_route_id'] = str(route['route_id'])
    return result


class _PooledConnectionLease:
    """Return a checked-out psycopg connection exactly once."""

    def __init__(self, pool, connection):
        object.__setattr__(self, '_pool', pool)
        object.__setattr__(self, '_connection', connection)
        object.__setattr__(self, '_closed', False)

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def __setattr__(self, name, value):
        if name.startswith('_'):
            object.__setattr__(self, name, value)
        else:
            setattr(self._connection, name, value)

    def close(self):
        if self._closed:
            return
        self._pool.putconn(self._connection)
        object.__setattr__(self, '_closed', True)


class _PsycopgPoolConnector:
    """Adapt psycopg_pool to the synchronous DB-API connector boundary."""

    _POOL_ARGUMENTS = frozenset({
        'pool_enabled', 'pool_min_size', 'pool_max_size',
        'pool_acquisition_timeout', 'pool_max_waiting',
        'pool_max_lifetime', 'pool_max_idle', 'pool_reconnect_timeout',
        'pool_workers', 'pool_check_connection',
        'cde_route_id',
    })

    def __init__(self, module, pool_namespace, pool_module=None):
        self.module = module
        self.pool_namespace = str(pool_namespace)
        self.pool_module = pool_module
        self._pools = {}

    def __call__(self, *args, **kwargs):
        if not kwargs.get('pool_enabled'):
            options = dict(kwargs)
            for key in self._POOL_ARGUMENTS:
                options.pop(key, None)
            return self.module.connect(*args, **options)
        if args:
            raise RelationalClientError(
                'pooled PostgreSQL-wire connections require named arguments'
            )
        options = dict(kwargs)
        pool_options = {
            key: options.pop(key)
            for key in tuple(options)
            if key in self._POOL_ARGUMENTS
        }
        pool_options.pop('pool_enabled', None)
        route_id = pool_options.pop('cde_route_id', None)
        key = str(route_id or (
            str(options.get('host') or '') + ':' +
            str(options.get('port') or '') + '/' +
            str(options.get('dbname') or '') + ':' +
            str(options.get('user') or '')
        ))
        pool_key = self.pool_namespace + ':' + key
        pool = self._pools.get(pool_key)
        if pool is None:
            namespace = self.pool_module or load_optional_module(
                'psycopg_pool'
            )
            pool_type = getattr(namespace, 'ConnectionPool', None)
            if not callable(pool_type):
                raise RelationalClientError(
                    'psycopg_pool has no synchronous ConnectionPool'
                )
            check = None
            if pool_options.pop('pool_check_connection', True):
                check = getattr(pool_type, 'check_connection', None)
            pool = pool_type(
                kwargs=options,
                min_size=pool_options.pop('pool_min_size', 1),
                max_size=pool_options.pop('pool_max_size', 10),
                timeout=pool_options.pop('pool_acquisition_timeout', 30),
                max_waiting=pool_options.pop('pool_max_waiting', 0),
                max_lifetime=pool_options.pop('pool_max_lifetime', 3600),
                max_idle=pool_options.pop('pool_max_idle', 600),
                reconnect_timeout=pool_options.pop(
                    'pool_reconnect_timeout', 300
                ),
                num_workers=pool_options.pop('pool_workers', 3),
                check=check,
                open=True,
            )
            self._pools[pool_key] = pool
        return _PooledConnectionLease(pool, pool.getconn())

    def close(self):
        for pool in tuple(self._pools.values()):
            close = getattr(pool, 'close', None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
        self._pools.clear()


class PsycopgPoolDBAPIClient(RelationalDBAPIClient):
    """PostgreSQL-wire client with optional native psycopg pooling."""

    def __init__(self, config, pool_namespace, module=None, pool_module=None):
        super().__init__(config, module)
        self._pool_connector = _PsycopgPoolConnector(
            self.module, pool_namespace, pool_module
        )
        self._connector = self._pool_connector

    def close(self):
        super().close()
        self._pool_connector.close()


def _initialize_postgresql_connection(connection, route):
    connection.set_autocommit(route.get('autocommit', False) is True)
    isolation = route.get('transaction_isolation', 'server')
    if isolation != 'server':
        module = load_optional_module('psycopg')
        try:
            value = module.IsolationLevel[isolation]
        except KeyError as exc:
            raise RelationalClientError(
                'PostgreSQL-wire transaction isolation is invalid'
            ) from exc
        connection.set_isolation_level(value)
    read_mode = route.get('transaction_read_only', 'server')
    if read_mode not in {'server', 'read-only', 'read-write'}:
        raise RelationalClientError(
            'PostgreSQL-wire transaction read mode is invalid'
        )
    if read_mode != 'server':
        connection.set_read_only(read_mode == 'read-only')
    deferrable = route.get('transaction_deferrable', 'server')
    if deferrable not in {'server', 'deferrable', 'not-deferrable'}:
        raise RelationalClientError(
            'PostgreSQL-wire transaction deferrability is invalid'
        )
    if deferrable != 'server':
        connection.set_deferrable(deferrable == 'deferrable')


def _initialize_mysql_connection(connection, route):
    """Apply session-only MySQL-wire defaults after authentication.

    Transaction isolation is deliberately not interpolated from arbitrary
    text.  The finite allowlist is shared by Dolt, TiDB and Vitess because
    they expose the same admitted MySQL wire statement.
    """
    isolation = route.get('transaction_isolation')
    if isolation is None:
        return
    allowed = {
        'READ UNCOMMITTED', 'READ COMMITTED', 'REPEATABLE READ',
        'SERIALIZABLE',
    }
    if isolation not in allowed:
        raise RelationalClientError(
            'MySQL-wire transaction isolation is invalid'
        )
    cursor = connection.cursor()
    try:
        cursor.execute(
            f'SET SESSION TRANSACTION ISOLATION LEVEL {isolation}'
        )
    finally:
        cursor.close()


def mysql_route(route):
    allowed = {
        'host', 'port', 'user', 'database', 'unix_socket',
        'connection_timeout', 'read_timeout', 'write_timeout',
        'ssl_ca', 'ssl_cert', 'ssl_key', 'ssl_verify_cert',
        'ssl_verify_identity', 'ssl_cipher', 'tls_ciphersuites',
        'ssl_disabled', 'tls_versions', 'compress', 'force_ipv6',
        'auth_plugin', 'krb_service_principal', 'kerberos_auth_mode',
        'oci_config_file', 'oci_config_profile', 'openid_token_file',
        'dns_srv', 'charset', 'collation', 'autocommit', 'time_zone',
        'sql_mode', 'init_command', 'conn_attrs', 'pool_name', 'pool_size',
        'pool_reset_session', 'failover',
    }
    result = {key: value for key, value in route.items() if key in allowed}
    if result.get('auth_plugin') == 'auto':
        result.pop('auth_plugin')
    if result.get('pool_size') and not result.get('pool_name'):
        route_id = str(route.get('route_id') or 'unscoped')
        result['pool_name'] = 'cde_' + hashlib.sha256(
            route_id.encode('utf-8')
        ).hexdigest()[:24]
    return result


# pg_extension is CockroachDB's schema for spatial_ref_sys and the geometry
# catalogs, which the engine maintains.
POSTGRESQL_SYSTEM_SCHEMAS = frozenset({
    'pg_catalog', 'information_schema', 'crdb_internal', 'pg_extension'})


_FOREIGN_KEY_RULES = {'a': 'NO ACTION', 'r': 'RESTRICT', 'c': 'CASCADE',
                      'n': 'SET NULL', 'd': 'SET DEFAULT'}


def postgresql_constraint_details(cursor):
    """{(schema, table, name): details} from pg_constraint.

    Key columns in order, a foreign key's referenced table, columns and
    rules, and a check clause, so an editor can re-open a table's
    constraints. pg_constraint ties each constraint to its table, where
    information_schema names a check or foreign key by schema only and
    PostgreSQL constraint names are unique per table. Optional: a missing
    catalog leaves only the constraint type.
    """
    names = {}
    for relation, number, name in optional_rows(
            cursor,
            'SELECT attrelid, attnum, attname FROM pg_catalog.pg_attribute '
            'WHERE attnum > 0'):
        names[(int(relation), int(number))] = str(name)
    found = {}
    for schema, table, name, kind, keys, relation, ref_schema, ref_table, \
            ref_keys, ref_relation, update_rule, delete_rule, definition in \
            optional_rows(
                cursor,
                'SELECT n.nspname, cl.relname, co.conname, co.contype, '
                'co.conkey, co.conrelid, fn.nspname, fcl.relname, '
                'co.confkey, co.confrelid, co.confupdtype, co.confdeltype, '
                'pg_catalog.pg_get_constraintdef(co.oid) '
                'FROM pg_catalog.pg_constraint co '
                'JOIN pg_catalog.pg_class cl ON cl.oid = co.conrelid '
                'JOIN pg_catalog.pg_namespace n ON n.oid = cl.relnamespace '
                'LEFT JOIN pg_catalog.pg_class fcl ON fcl.oid = co.confrelid '
                'LEFT JOIN pg_catalog.pg_namespace fn '
                'ON fn.oid = fcl.relnamespace '
                "WHERE co.contype IN ('p', 'u', 'f', 'c')"):
        entry = {'columns': [names.get((int(relation), int(key)), str(key))
                             for key in (keys or [])]}
        if str(kind) == 'f' and ref_table is not None:
            entry.update(
                referenced_schema=str(ref_schema),
                referenced_table=str(ref_table),
                referenced_columns=[
                    names.get((int(ref_relation), int(key)), str(key))
                    for key in (ref_keys or [])],
                update_rule=_FOREIGN_KEY_RULES.get(str(update_rule),
                                                   str(update_rule)),
                delete_rule=_FOREIGN_KEY_RULES.get(str(delete_rule),
                                                   str(delete_rule)))
        if str(kind) == 'c':
            # information_schema's form: the expression in parentheses.
            match = re.match(r'^CHECK\s*(\(.*\))\s*(NOT VALID)?$',
                             str(definition or ''), re.S)
            entry['check_clause'] = match.group(1) if match else str(
                definition)
        found[(str(schema), str(table), str(name))] = entry
    return found


def postgresql_catalog(connection, request, engine_name, extras=None):
    """Read portable SQL catalogs plus provider-selected topology extras."""
    generation = str(request.get('capability_generation') or 'current')
    values = {resource('cluster', [], engine_name, generation)['resource_id']:
              resource('cluster', [], engine_name, generation)}
    native_cursor = connection.cursor()

    class CatalogCursor:
        def __getattr__(self, key):
            return getattr(native_cursor, key)

        @staticmethod
        def _source(source):
            # Preserve native system catalogs and the caller's rights.
            return re.sub(
                r"[A-Za-z_.]+ NOT IN \('pg_catalog', 'information_schema'"
                r"(?:, 'crdb_internal')?\)", 'TRUE', source)

        def execute(self, source, parameters=()):
            return native_cursor.execute(self._source(source), parameters)

        def cde_optional_rows(self, source, parameters=()):
            return native_cursor.cde_optional_rows(
                self._source(source), parameters)

    cursor = CatalogCursor()
    try:
        # A database that refuses connections is still one to edit;
        # template0 (a template that refuses them) is left out. A catalog
        # without datistemplate (not checked on every engine here) gets
        # the earlier connectable-only list.
        databases = optional_rows(
            cursor,
            'SELECT datname FROM pg_catalog.pg_database '
            'WHERE datallowconn OR NOT datistemplate ORDER BY datname',
        ) or optional_rows(
            cursor,
            'SELECT datname FROM pg_catalog.pg_database '
            'WHERE datallowconn ORDER BY datname',
        )
        for row in databases:
            item = resource('database', [], row[0], generation)
            values[item['resource_id']] = item
        schemas = optional_rows(
            cursor,
            'SELECT schema_name FROM information_schema.schemata '
            'WHERE schema_name NOT IN '
            "('pg_catalog', 'information_schema', 'crdb_internal') "
            'ORDER BY 1',
        )
        for row in schemas:
            item = resource('schema', [], row[0], generation)
            values[item['resource_id']] = item
        relations = optional_rows(
            cursor,
            'SELECT table_schema, table_name, table_type '
            'FROM information_schema.tables WHERE table_schema NOT IN '
            "('pg_catalog', 'information_schema', 'crdb_internal') "
            'ORDER BY 1, 2',
        )
        for schema, name, table_type in relations:
            schema_item = resource('schema', [], schema, generation)
            values[schema_item['resource_id']] = schema_item
            kind = 'view' if 'VIEW' in str(table_type).upper() else 'table'
            item = resource(
                kind, [schema], name, generation,
                {'table_type': str(table_type)},
            )
            values[item['resource_id']] = item
        # Definition order, defaults, generation and identity let an editor
        # re-open an existing table; the narrower query remains the fallback.
        columns = optional_rows(
            cursor,
            'SELECT table_schema, table_name, column_name, data_type, '
            'is_nullable, ordinal_position, column_default, is_generated, '
            'generation_expression, is_identity '
            'FROM information_schema.columns WHERE table_schema NOT IN '
            "('pg_catalog', 'information_schema', 'crdb_internal') "
            'ORDER BY 1, 2, ordinal_position',
        ) or [(*row, None, None, None, None, None) for row in optional_rows(
            cursor,
            'SELECT table_schema, table_name, column_name, data_type, '
            'is_nullable FROM information_schema.columns '
            'WHERE table_schema NOT IN '
            "('pg_catalog', 'information_schema', 'crdb_internal') "
            'ORDER BY 1, 2, 3',
        )]
        for schema, table, name, data_type, nullable, position, default, \
                generated, expression, identity in columns:
            native = {'data_type': str(data_type),
                      'is_nullable': str(nullable)}
            if position is not None:
                native.update({
                    'ordinal_position': int(position),
                    'column_default': (
                        None if default is None else str(default)),
                    'default_expression': (
                        None if default is None else str(default)),
                    'is_generated': str(generated or 'NEVER'),
                    'generation_expression': (
                        None if not expression else str(expression)),
                    'is_identity': str(identity or 'NO') == 'YES',
                })
            item = resource('column', [schema, table], name, generation,
                            native)
            values[item['resource_id']] = item
        indexes = optional_rows(
            cursor,
            'SELECT schemaname, tablename, indexname, indexdef '
            'FROM pg_catalog.pg_indexes WHERE schemaname NOT IN '
            "('pg_catalog', 'information_schema', 'crdb_internal') "
            'ORDER BY 1, 2, 3',
        )
        for schema, table, name, definition in indexes:
            item = resource('index', [schema, table], name, generation, {
                'definition': str(definition),
            })
            values[item['resource_id']] = item
        if extras:
            for item in extras(cursor, request, generation):
                values[item['resource_id']] = item
        for item in values.values():
            path = item.get('display_path', [])
            if path and path[0] in POSTGRESQL_SYSTEM_SCHEMAS:
                item.setdefault('native', {})['system_object'] = True
        return annotate_relation_ownership(list(values.values()))
    finally:
        cursor.close()


def mysql_catalog(connection, request, engine_name, extras=None,
                  schema=None):
    """Read MySQL-wire catalogs plus provider-selected topology extras.

    ``schema`` reads one schema only (see ``_schema_where``).
    """
    generation = str(request.get('capability_generation') or 'current')
    where, parameters = _schema_where('TABLE_SCHEMA', schema)
    cluster = resource('cluster', [], engine_name, generation)
    values = {cluster['resource_id']: cluster}
    cursor = connection.cursor()
    try:
        rows = optional_rows(
            cursor,
            'SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE '
            f'FROM information_schema.TABLES {where}ORDER BY 1, 2',
            parameters,
        )
        for database, name, table_type in rows:
            database_item = resource('database', [], database, generation)
            values[database_item['resource_id']] = database_item
            kind = 'view' if 'VIEW' in str(table_type).upper() else 'table'
            item = resource(kind, [database], name, generation, {
                'table_type': str(table_type),
            })
            values[item['resource_id']] = item
        # Definition order, defaults and key membership let an editor re-open
        # an existing table; the narrower query remains the fallback.
        rows = optional_rows(
            cursor,
            'SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, '
            'IS_NULLABLE, ORDINAL_POSITION, COLUMN_DEFAULT, COLUMN_KEY, '
            f'EXTRA FROM information_schema.COLUMNS {where}'
            'ORDER BY 1, 2, ORDINAL_POSITION', parameters,
        ) or [
            (*row, None, None, None, None) for row in optional_rows(
                cursor,
                'SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, '
                f'IS_NULLABLE FROM information_schema.COLUMNS {where}'
                'ORDER BY 1, 2, 3', parameters,
            )
        ]
        for database, table, name, data_type, nullable, position, \
                default, column_key, extra in rows:
            native = {
                'data_type': str(data_type), 'is_nullable': str(nullable),
            }
            if position is not None:
                native.update({
                    'ordinal_position': int(position),
                    'column_default': (
                        None if default is None else str(default)),
                    'default_expression': mysql_default_expression(
                        data_type, default, extra),
                    'column_key': str(column_key or ''),
                    'extra': str(extra or ''),
                })
            item = resource('column', [database, table], name, generation,
                            native)
            values[item['resource_id']] = item
        rows = optional_rows(
            cursor,
            'SELECT TABLE_SCHEMA, TABLE_NAME, INDEX_NAME, NON_UNIQUE, '
            'INDEX_TYPE, SEQ_IN_INDEX, COLUMN_NAME '
            f'FROM information_schema.STATISTICS {where}'
            'ORDER BY 1, 2, 3, 6', parameters,
        ) or [
            (*row, None, None) for row in optional_rows(
                cursor,
                'SELECT DISTINCT TABLE_SCHEMA, TABLE_NAME, INDEX_NAME, '
                'NON_UNIQUE, INDEX_TYPE FROM information_schema.STATISTICS '
                f'{where}ORDER BY 1, 2, 3', parameters,
            )
        ]
        for database, table, name, non_unique, index_type, _sequence, \
                column in rows:
            # TiDB reports NON_UNIQUE as the string '0'/'1', so bool() would
            # call every index non-unique.
            item = resource('index', [database, table], name, generation, {
                'unique': str(non_unique).strip() in {'0', 'False', 'false'},
                'index_type': str(index_type),
            })
            existing = values.get(item['resource_id'])
            if existing is not None:
                item = existing
            elif column is not None:
                item['native']['columns'] = []
                item['native']['definition']['columns'] = []
            if column is not None:
                item['native']['columns'].append(str(column))
                item['native']['definition']['columns'].append(str(column))
            values[item['resource_id']] = item
        if extras:
            for item in extras(cursor, request, generation):
                values[item['resource_id']] = item
        return annotate_relation_ownership(list(values.values()))
    finally:
        cursor.close()


def postgresql_security(connection, request):
    cursor = connection.cursor()
    try:
        cursor.execute('SELECT current_user, session_user')
        current, session = cursor.fetchone()
        generation = str(request.get('capability_generation') or 'current')
        return resource('role', [], current, generation, {
            'current_user': str(current), 'session_user': str(session),
            'authorization_model': 'postgresql-wire-native',
        })
    finally:
        cursor.close()


def mysql_security(connection, request):
    cursor = connection.cursor()
    try:
        cursor.execute('SELECT CURRENT_USER(), USER()')
        current, session = cursor.fetchone()
        generation = str(request.get('capability_generation') or 'current')
        return resource('user', [], current, generation, {
            'current_user': str(current), 'session_user': str(session),
            'authorization_model': 'mysql-wire-native',
        })
    finally:
        cursor.close()


def create_sql_client(
    profile,
    permissions,
    *,
    wire,
    version_query,
    version_parser,
    metadata_reader: Callable[[object, Mapping[str, Any]], list[dict]],
    administration,
    client_class=RelationalDBAPIClient,
    client_options=None,
    security_reader_override=None,
    pool_namespace=None,
    tool_credential_kinds=frozenset(),
):
    """Create a DB-API adapter from one provider-owned distributed spec."""
    if wire == 'postgresql':
        module_name = 'psycopg'
        route_builder = postgresql_route
        security_reader = postgresql_security
        credential_arguments = {
            'database_password': 'password',
            'tls_private_key_password': 'sslpassword',
            'oauth_client_secret': 'oauth_client_secret',
        }
    elif wire == 'mysql':
        module_name = 'mysql.connector'
        route_builder = mysql_route
        security_reader = mysql_security
        credential_arguments = {
            'database_password': 'password',
            'database_password_2': 'password2',
            'database_password_3': 'password3',
        }
    else:
        raise ValueError('distributed SQL wire must be provider-selected')
    config = RelationalClientConfig(
        profile=profile,
        module_name=module_name,
        version_query=version_query,
        version_parser=version_parser,
        connect_arguments=route_builder,
        metadata_reader=metadata_reader,
        security_reader=security_reader_override or security_reader,
        credential_arguments=credential_arguments,
        tool_credential_kinds=frozenset(tool_credential_kinds),
        secret_acquirer=permissions.acquire_secret,
        connection_initializer=(
            _initialize_postgresql_connection
            if wire == 'postgresql' else _initialize_mysql_connection
        ),
        administration=administration,
    )
    options = dict(client_options or {})
    if wire == 'postgresql' and client_class is RelationalDBAPIClient:
        if pool_namespace is None:
            raise ValueError(
                'PostgreSQL-wire client requires a pool namespace'
            )
        return PsycopgPoolDBAPIClient(
            config, pool_namespace, **options
        )
    return client_class(config, **options)


def sql_administration(
    engine_id, wire, native_read_only=(), provider_read_only=(),
):
    """Construct the safe common SQL admin subset for one provider."""
    namespace = frozenset({'inspect', 'create', 'alter', 'drop'})
    definition = frozenset({'inspect', 'create', 'drop'})
    supported = {
        'cluster': frozenset({'inspect'}),
        'database': namespace,
        'schema': namespace,
        'table': frozenset({
            'inspect', 'create', 'alter', 'rename', 'drop',
            'insert', 'update', 'delete',
        }),
        'column': frozenset({
            'inspect', 'create', 'alter', 'rename', 'drop',
        }),
        'view': frozenset({'inspect', 'create', 'alter', 'drop'}),
        'index': definition,
        'constraint': definition,
        'sequence': frozenset({
            'inspect', 'create', 'alter', 'rename', 'drop',
        }),
        'user': frozenset({'inspect', 'create', 'alter', 'drop'}),
        'role': frozenset({'inspect', 'create', 'alter', 'drop'}),
        'privilege': frozenset({'inspect', 'grant', 'revoke'}),
    }
    for kind in native_read_only:
        supported[kind] = frozenset({'inspect'})
    for kind in provider_read_only:
        supported[kind] = frozenset({'inspect'})
    mysql = wire == 'mysql'
    return RelationalAdministration(RelationalAdminDialect(
        engine_id=engine_id,
        quote_open='`' if mysql else '"',
        quote_close='`' if mysql else '"',
        parameter='%s',
        supported=supported,
        syntax_family=wire,
    ))


def mysql_account_resources(cursor, generation):
    """Users, roles and global, database and table grants (MySQL dialect).

    Roles are locked passwordless accounts or role_edges sources (Dolt and
    TiDB implement MySQL roles that way). Records carry the user and host
    parts so an editor can re-open an account.
    """
    values = []
    roles = set()
    for user, host in optional_rows(
        cursor,
        'SELECT DISTINCT FROM_USER, FROM_HOST FROM mysql.role_edges '
        'ORDER BY 1, 2',
    ):
        account = (str(user), str(host))
        roles.add(account)
        values.append(resource(
            'role', [], f'{account[0]}@{account[1]}', generation,
            {'user': account[0], 'host': account[1]},
        ))
    accounts = optional_rows(
        cursor,
        'SELECT User, Host, account_locked, authentication_string '
        'FROM mysql.user ORDER BY 1, 2',
    )
    for user, host, locked, authentication in accounts:
        account = (str(user), str(host))
        # Dolt implements MySQL roles as locked, passwordless accounts. This
        # also preserves unassigned roles, which have no mysql.role_edges row.
        is_role = (
            str(locked).upper() == 'Y' and not str(authentication or '')
        )
        if is_role and account not in roles:
            roles.add(account)
            values.append(resource(
                'role', [], f'{account[0]}@{account[1]}', generation,
                {'user': account[0], 'host': account[1]},
            ))
        elif account not in roles:
            values.append(resource(
                'user', [], f'{account[0]}@{account[1]}', generation,
                {'account_locked': str(locked), 'user': account[0],
                 'host': account[1]},
            ))
    for grantee, privilege in optional_rows(
        cursor,
        'SELECT GRANTEE, PRIVILEGE_TYPE '
        'FROM information_schema.USER_PRIVILEGES ORDER BY 1, 2',
    ):
        values.append(resource(
            'privilege', [grantee], privilege, generation,
            mysql_grant(grantee, 'GLOBAL', '*.*', privilege, None),
        ))
    # Database- and table-level grants, so the tree shows every grant a
    # REVOKE can name, not only global ones.
    for grantee, schema, privilege, grantable in optional_rows(
        cursor,
        'SELECT GRANTEE, TABLE_SCHEMA, PRIVILEGE_TYPE, IS_GRANTABLE '
        'FROM information_schema.SCHEMA_PRIVILEGES ORDER BY 1, 2, 3',
    ):
        values.append(resource(
            'privilege', [grantee, schema], privilege, generation,
            mysql_grant(grantee, 'DATABASE', schema, privilege, grantable),
        ))
    for grantee, schema, table, privilege, grantable in optional_rows(
        cursor,
        'SELECT GRANTEE, TABLE_SCHEMA, TABLE_NAME, PRIVILEGE_TYPE, '
        'IS_GRANTABLE FROM information_schema.TABLE_PRIVILEGES '
        'ORDER BY 1, 2, 3, 4',
    ):
        values.append(resource(
            'privilege', [grantee, schema, table], privilege, generation,
            mysql_grant(grantee, 'TABLE', f'{schema}.{table}', privilege,
                        grantable),
        ))
    return values

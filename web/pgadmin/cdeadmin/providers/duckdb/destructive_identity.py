"""Reviewed native DuckDB catalog and file continuity guard (DU-AUD-01).

Generic administration operations (DROP, ALTER, RENAME, column DDL, and
database maintenance/drop) must never equate a display path or SQL identifier
with the originally reviewed object. At plan time we bind the physical file
identity (device/inode when file-backed), database OID, schema OID, object OID
and structural catalog projection digest; at apply time we re-observe inside
the executing connection before dispatching any native command so same-name
replacements and caller-owned transactions remain intact.
"""
from collections.abc import Mapping
import hashlib
import json
import os
import stat

from ...sdk.relational import RelationalClientError


GUARDED_KINDS = frozenset({
    'database', 'schema', 'table', 'view', 'column',
    'constraint', 'index', 'sequence', 'type', 'macro',
})
NON_EXISTING_OPERATIONS = frozenset({
    'inspect', 'create', 'insert', 'update', 'delete',
    'comment', 'update_extensions',
})


def _refused(message):
    error = RelationalClientError(message)
    error.code = 'DUCKDB_STALE_NATIVE_TARGET'
    error.rejected = True
    error.nothing_changed = True
    error.native_dispatched = False
    error.automatic_retry = False
    return error


def _digest(payload):
    encoded = json.dumps(
        payload, sort_keys=True, separators=(',', ':'), default=str,
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _file_identity(route):
    if not isinstance(route, Mapping):
        return None
    raw = route.get('database')
    if not isinstance(raw, str) or not raw.strip() or raw.strip() == ':memory:':
        return {'storage': 'memory'}
    from ..embedded_route import contained_database
    path = contained_database(route)
    if not os.path.lexists(path):
        return None
    st = os.lstat(path)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise _refused('DuckDB target file is not a regular non-symlink file')
    return {
        'storage': 'file',
        'realpath': os.path.realpath(path),
        'dev': int(st.st_dev),
        'ino': int(st.st_ino),
    }


def selection(request, administration):
    if not isinstance(request, Mapping):
        return None
    kind = request.get('resource_kind')
    operation = request.get('operation_id')
    if kind not in GUARDED_KINDS:
        return None
    target = request.get('target_resource')
    if kind == 'column' and operation == 'create':
        if isinstance(target, Mapping) and target.get('resource_kind') == 'table':
            return {
                'resource_kind': 'table',
                'path': [str(part) for part in administration._target_path(target)],
            }
        return None
    if operation in NON_EXISTING_OPERATIONS:
        return None
    if kind == 'database':
        route = request.get('_provider_route') or {}
        db_name = None
        if isinstance(target, Mapping):
            db_name = target.get('display_name')
        return {
            'resource_kind': 'database',
            'path': [str(db_name or route.get('database') or '')],
        }
    if not isinstance(target, Mapping):
        return None
    path = [str(part) for part in administration._target_path(target)]
    if not path:
        return None
    return {'resource_kind': str(kind), 'path': path}


def _resolve_scope(connection, kind, path):
    cur_db, cur_schema = connection.execute(
        'SELECT current_database(), current_schema()'
    ).fetchone()
    if kind == 'database':
        return str(cur_db), None, None, str(cur_db)
    if kind == 'schema':
        if len(path) >= 2:
            return path[-2], path[-1], None, path[-1]
        return str(cur_db), path[0], None, path[0]
    if kind in {'column', 'index', 'constraint'}:
        if len(path) >= 4:
            return path[-4], path[-3], path[-2], path[-1]
        if len(path) == 3:
            return str(cur_db), path[0], path[1], path[2]
        if len(path) == 2:
            return str(cur_db), str(cur_schema), path[0], path[1]
        raise _refused(f'DuckDB {kind} target path is incomplete')
    if len(path) >= 3:
        return path[-3], path[-2], None, path[-1]
    if len(path) == 2:
        return str(cur_db), path[0], None, path[1]
    return str(cur_db), str(cur_schema), None, path[0]


def observe(connection, route, selected):
    kind = selected.get('resource_kind')
    path = selected.get('path')
    if kind not in GUARDED_KINDS or not isinstance(path, list) or not path:
        raise _refused('Native DuckDB target binding is invalid')
    file_id = _file_identity(route)
    catalog, schema, parent_table, name = _resolve_scope(connection, kind, path)
    db_row = connection.execute(
        'SELECT database_name, database_oid, type, readonly '
        'FROM "system"."main".duckdb_databases() WHERE database_name = ?',
        [catalog],
    ).fetchone()
    if db_row is None:
        raise _refused('Native DuckDB catalog is absent; refresh and review again')
    db_identity = {
        'database_name': str(db_row[0]),
        'database_oid': int(db_row[1]),
        'type': str(db_row[2]),
        'readonly': bool(db_row[3]),
    }
    if kind == 'database':
        return {
            'schema': 'scratchrobin.duckdb.native-target@1',
            'mode': 'live',
            'resource_kind': 'database',
            'path': list(path),
            'file_identity': file_id,
            'database': db_identity,
            'record': {'oid': db_identity['database_oid']},
        }

    schema_row = connection.execute(
        'SELECT schema_name, oid, sql FROM "system"."main".duckdb_schemas() '
        'WHERE database_name = ? AND schema_name = ?',
        [catalog, schema],
    ).fetchone()
    if schema_row is None:
        raise _refused('Native DuckDB schema is absent; refresh and review again')
    schema_identity = {
        'schema_name': str(schema_row[0]),
        'oid': int(schema_row[1]),
        'sql_sha256': _digest(schema_row[2]),
    }
    if kind == 'schema':
        return {
            'schema': 'scratchrobin.duckdb.native-target@1',
            'mode': 'live',
            'resource_kind': 'schema',
            'path': list(path),
            'file_identity': file_id,
            'database': db_identity,
            'schema_identity': schema_identity,
            'record': schema_identity,
        }

    if kind == 'table':
        row = connection.execute(
            'SELECT table_oid, temporary, has_primary_key, sql '
            'FROM "system"."main".duckdb_tables() '
            'WHERE database_name = ? AND schema_name = ? AND table_name = ? '
            'AND NOT internal',
            [catalog, schema, name],
        ).fetchone()
        if row is None:
            raise _refused('Native DuckDB table target is absent; refresh and review again')
        cols = connection.execute(
            'SELECT column_name, column_index, data_type, is_nullable, column_default '
            'FROM "system"."main".duckdb_columns() '
            'WHERE database_name = ? AND schema_name = ? AND table_name = ? '
            'AND NOT internal ORDER BY column_index',
            [catalog, schema, name],
        ).fetchall()
        cons = connection.execute(
            'SELECT constraint_index, constraint_type, constraint_text '
            'FROM "system"."main".duckdb_constraints() '
            'WHERE database_name = ? AND schema_name = ? AND table_name = ? '
            'ORDER BY constraint_index',
            [catalog, schema, name],
        ).fetchall()
        record = {
            'oid': int(row[0]),
            'temporary': bool(row[1]),
            'has_primary_key': bool(row[2]),
            'projection_sha256': _digest({
                'sql': row[3],
                'columns': [list(c) for c in cols],
                'constraints': [list(c) for c in cons],
            }),
        }
    elif kind == 'view':
        row = connection.execute(
            'SELECT view_oid, temporary, sql '
            'FROM "system"."main".duckdb_views() '
            'WHERE database_name = ? AND schema_name = ? AND view_name = ? '
            'AND NOT internal',
            [catalog, schema, name],
        ).fetchone()
        if row is None:
            raise _refused('Native DuckDB view target is absent; refresh and review again')
        record = {
            'oid': int(row[0]),
            'temporary': bool(row[1]),
            'projection_sha256': _digest({'sql': row[2]}),
        }
    elif kind == 'column':
        parent = connection.execute(
            'SELECT table_oid FROM "system"."main".duckdb_tables() '
            'WHERE database_name = ? AND schema_name = ? AND table_name = ? '
            'AND NOT internal',
            [catalog, schema, parent_table],
        ).fetchone()
        col = connection.execute(
            'SELECT column_index, data_type, is_nullable, column_default '
            'FROM "system"."main".duckdb_columns() '
            'WHERE database_name = ? AND schema_name = ? AND table_name = ? '
            'AND column_name = ? AND NOT internal',
            [catalog, schema, parent_table, name],
        ).fetchone()
        if parent is None or col is None:
            raise _refused('Native DuckDB column target is absent; refresh and review again')
        record = {
            'owner_oid': int(parent[0]),
            'ordinal_position': int(col[0]),
            'projection_sha256': _digest(list(col)),
        }
    elif kind == 'index':
        parent = connection.execute(
            'SELECT table_oid FROM "system"."main".duckdb_tables() '
            'WHERE database_name = ? AND schema_name = ? AND table_name = ? '
            'AND NOT internal',
            [catalog, schema, parent_table],
        ).fetchone()
        idx = connection.execute(
            'SELECT index_oid, is_unique, is_primary, expressions, sql '
            'FROM "system"."main".duckdb_indexes() '
            'WHERE database_name = ? AND schema_name = ? AND table_name = ? '
            'AND index_name = ?',
            [catalog, schema, parent_table, name],
        ).fetchone()
        if parent is None or idx is None:
            raise _refused('Native DuckDB index target is absent; refresh and review again')
        record = {
            'owner_oid': int(parent[0]),
            'oid': int(idx[0]),
            'projection_sha256': _digest(list(idx)),
        }
    elif kind == 'constraint':
        parent = connection.execute(
            'SELECT table_oid FROM "system"."main".duckdb_tables() '
            'WHERE database_name = ? AND schema_name = ? AND table_name = ? '
            'AND NOT internal',
            [catalog, schema, parent_table],
        ).fetchone()
        con_rows = connection.execute(
            'SELECT constraint_index, constraint_type, constraint_text '
            'FROM "system"."main".duckdb_constraints() '
            'WHERE database_name = ? AND schema_name = ? AND table_name = ? '
            'AND constraint_name = ? ORDER BY constraint_index',
            [catalog, schema, parent_table, name],
        ).fetchall()
        if parent is None or len(con_rows) != 1:
            raise _refused('Native DuckDB constraint target is absent or ambiguous; refresh and review again')
        record = {
            'owner_oid': int(parent[0]),
            'constraint_index': int(con_rows[0][0]),
            'projection_sha256': _digest(list(con_rows[0])),
        }
    elif kind == 'sequence':
        seq = connection.execute(
            'SELECT sequence_oid, temporary, start_value, min_value, max_value, '
            'increment_by, cycle, sql '
            'FROM "system"."main".duckdb_sequences() '
            'WHERE database_name = ? AND schema_name = ? AND sequence_name = ?',
            [catalog, schema, name],
        ).fetchone()
        if seq is None:
            raise _refused('Native DuckDB sequence target is absent; refresh and review again')
        record = {
            'oid': int(seq[0]),
            'temporary': bool(seq[1]),
            'projection_sha256': _digest(list(seq)),
        }
    elif kind == 'type':
        tp = connection.execute(
            'SELECT type_oid, logical_type, type_category, labels '
            'FROM "system"."main".duckdb_types() '
            'WHERE database_name = ? AND schema_name = ? AND type_name = ? '
            'AND NOT internal',
            [catalog, schema, name],
        ).fetchone()
        if tp is None:
            raise _refused('Native DuckDB type target is absent; refresh and review again')
        record = {
            'oid': int(tp[0]),
            'projection_sha256': _digest(list(tp)),
        }
    elif kind == 'macro':
        overloads = connection.execute(
            'SELECT function_oid, function_type, parameters, parameter_types, '
            'varargs, macro_definition '
            'FROM "system"."main".duckdb_functions() '
            'WHERE database_name = ? AND schema_name = ? AND function_name = ? '
            "AND function_type IN ('macro', 'table_macro') AND NOT internal "
            'ORDER BY function_oid, function_type, macro_definition',
            [catalog, schema, name],
        ).fetchall()
        if not overloads:
            raise _refused('Native DuckDB macro target is absent; refresh and review again')
        record = {
            'oids': sorted({int(item[0]) for item in overloads if item[0] is not None}),
            'projection_sha256': _digest([list(item) for item in overloads]),
        }
    else:
        raise _refused(f'Unsupported DuckDB continuity target kind: {kind}')

    return {
        'schema': 'scratchrobin.duckdb.native-target@1',
        'mode': 'live',
        'resource_kind': kind,
        'path': list(path),
        'resolved': {
            'catalog': catalog,
            'schema': schema,
            'parent_table': parent_table,
            'name': name,
        },
        'file_identity': file_id,
        'database': db_identity,
        'schema_identity': schema_identity,
        'record': record,
    }


def _snapshot_from_target_resource(target, route, selected):
    if not isinstance(target, Mapping):
        return None
    native = target.get('native')
    if not isinstance(native, Mapping):
        ext = (target.get('extensions') or {}).get('duckdb')
        native = ext.get('native', ext) if isinstance(ext, Mapping) else None
    if not isinstance(native, Mapping):
        return None
    meta = native.get('catalog_metadata')
    meta = meta if isinstance(meta, Mapping) else native
    oid = meta.get('oid', native.get('database_oid'))
    overloads = native.get('overloads')
    oids = (
        sorted({
            int(item['catalog_metadata']['oid'])
            for item in overloads
            if isinstance(item, Mapping)
            and isinstance(item.get('catalog_metadata'), Mapping)
            and item['catalog_metadata'].get('oid') is not None
        })
        if isinstance(overloads, list) else None
    )
    if oid is None and not oids:
        return None
    return {
        'schema': 'scratchrobin.duckdb.native-target@1',
        'mode': 'resource-snapshot',
        'resource_kind': selected['resource_kind'],
        'path': list(selected['path']),
        'file_identity': _file_identity(route),
        'oid': int(oid) if oid is not None else None,
        'oids': oids,
        'ddl': native.get('ddl'),
    }


def observe_for_plan(request, administration):
    selected = selection(request, administration)
    if selected is None:
        return None
    route = request.get('_provider_route') or {}
    handle = request.get('_provider_session_handle')
    if handle is not None:
        return observe(handle, route, selected)
    file_id = _file_identity(route)
    if file_id is not None and file_id.get('storage') == 'file':
        import duckdb
        from .provider import _initialize_connection, _route_arguments
        arguments = _route_arguments(route)
        connection = duckdb.connect(**arguments)
        try:
            _initialize_connection(connection, route)
            return observe(connection, route, selected)
        finally:
            connection.close()
    return _snapshot_from_target_resource(
        request.get('target_resource'), route, selected,
    )


def verify(connection, route, expected):
    if not isinstance(expected, Mapping) or (
        expected.get('schema') != 'scratchrobin.duckdb.native-target@1'
    ):
        raise _refused('Native DuckDB target binding is missing or invalid; refresh and review again')
    selected = {
        'resource_kind': expected.get('resource_kind'),
        'path': expected.get('path'),
    }
    if expected.get('mode') == 'resource-snapshot':
        actual = observe(connection, route, selected)
        if expected.get('file_identity') and actual.get('file_identity') != expected.get('file_identity'):
            raise _refused('Native DuckDB file identity changed since review; refresh and review again')
        rec = actual['record']
        if expected.get('oids') is not None:
            if rec.get('oids') != expected['oids']:
                raise _refused('Native DuckDB macro identity changed since review; refresh and review again')
        elif expected.get('oid') is not None and rec.get('oid') != expected['oid']:
            raise _refused('Native DuckDB object identity changed since review; refresh and review again')
        return actual

    actual = observe(connection, route, selected)
    if actual != expected:
        raise _refused('Native DuckDB object changed since review; refresh and review again')
    return actual


def verify_offline_file(route, expected):
    """Verify physical file + database OID before an offline file drop."""
    if not isinstance(expected, Mapping) or (
        expected.get('schema') != 'scratchrobin.duckdb.native-target@1'
    ):
        raise _refused('Native DuckDB database drop binding is missing; refresh and review again')
    current_file = _file_identity(route)
    if current_file is None or current_file != expected.get('file_identity'):
        raise _refused('Native DuckDB database file changed since review; refresh and review again')
    if expected.get('mode') == 'live':
        import duckdb
        from .provider import _route_arguments
        connection = duckdb.connect(**_route_arguments(route))
        try:
            actual = observe(connection, route, {
                'resource_kind': 'database',
                'path': expected.get('path') or [str(route.get('database') or '')],
            })
        finally:
            connection.close()
        if actual != expected:
            raise _refused('Native DuckDB database catalog changed since review; refresh and review again')

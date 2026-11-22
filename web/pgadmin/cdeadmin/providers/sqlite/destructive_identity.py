"""Race-safe native file, schema-cookie and catalog-object continuity for SQLite mutations (SQ-AUD-01).

During plan, observe the target SQLite file identity (st_dev, st_ino for file routes),
namespace (main, temp or attached alias), PRAGMA <schema>.schema_version, and the exact
sqlite_schema row (type, name, tbl_name, rootpage, sha256(sql)) plus table_xinfo column
signature without holding locks across user review.

During apply, acquire an immediate write lock (BEGIN IMMEDIATE on an owned connection, or
an atomic SAVEPOINT on a caller-retained connection), re-observe file identity,
schema_version, rootpage, and DDL/column digests while holding that lock, and refuse with
a stale-target conflict before dispatching DDL if the object or schema was replaced.
"""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import closing
import hashlib
import json
import os
import sqlite3
import stat
import uuid

from pgadmin.cdeadmin.sdk import RelationalClientError
from ..embedded_route import contained_database, sqlite_arguments
from .declarations import quote

GUARDED_OPERATIONS = {
    'table': frozenset({'drop', 'alter', 'rename'}),
    'view': frozenset({'drop'}),
    'index': frozenset({'drop'}),
    'trigger': frozenset({'drop'}),
    'virtual-table': frozenset({'drop', 'rename'}),
    'fts-table': frozenset({'drop', 'rename'}),
    'column': frozenset({'drop', 'rename'}),
}

_SCHEMA_OBJECT_TYPE = {
    'table': 'table',
    'virtual-table': 'table',
    'fts-table': 'table',
    'view': 'view',
    'index': 'index',
    'trigger': 'trigger',
    'column': 'table',
}


def applies(request: Mapping) -> bool:
    if not isinstance(request, Mapping):
        return False
    kind = request.get('resource_kind')
    op = request.get('operation_id')
    return kind in GUARDED_OPERATIONS and op in GUARDED_OPERATIONS[kind] and isinstance(request.get('target_resource'), Mapping)


def _sha256(value: object) -> str:
    raw = value if isinstance(value, str) else json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf8', errors='surrogateescape')).hexdigest()


def stale_target_error(message: str, *, reason: str, details: dict | None = None) -> RelationalClientError:
    err = RelationalClientError(message)
    err.stale_target_conflict = True
    err.conflict_reason = reason
    err.native_dispatched = False
    err.native_acknowledged = False
    err.automatic_retry = False
    if details is not None:
        err.conflict_details = details
    return err


def _extract_target_spec(target: Mapping) -> dict:
    kind = str(target.get('resource_kind') or '')
    path = list(target.get('display_path') or ())
    name = str(target.get('display_name') or (path[-1] if path else ''))
    if not path or not name:
        raise RelationalClientError('SQLite target resource requires display_path and display_name')
    schema_name = str(path[0])
    if kind == 'column':
        if len(path) < 3:
            raise RelationalClientError('SQLite column target requires [schema, table, column] path')
        lookup_name = str(path[1])
        column_name = name
    else:
        lookup_name = name
        column_name = None
    native = target.get('native')
    if not isinstance(native, Mapping):
        ext = target.get('extensions')
        if isinstance(ext, Mapping) and isinstance(ext.get('sqlite'), Mapping):
            sub = ext['sqlite'].get('native', ext['sqlite'])
            if isinstance(sub, Mapping):
                native = sub
    native = native if isinstance(native, Mapping) else {}
    return {
        'resource_kind': kind,
        'resource_id': target.get('resource_id'),
        'schema': schema_name,
        'schema_object_type': _SCHEMA_OBJECT_TYPE[kind],
        'lookup_name': lookup_name,
        'column_name': column_name,
        'expected_ddl': native.get('ddl') if isinstance(native.get('ddl'), str) else None,
    }


def _file_identity_for_schema(connection: sqlite3.Connection, route: Mapping, schema_name: str) -> list[int] | None:
    if schema_name.lower() == 'temp':
        return None
    db_rows = {str(r[1]): str(r[2] or '') for r in connection.execute('PRAGMA database_list').fetchall()}
    db_file = db_rows.get(schema_name, '')
    if not db_file or db_file == ':memory:' or db_file.startswith('file::memory:'):
        if schema_name == 'main' and isinstance(route, Mapping):
            raw_db = route.get('database')
            if isinstance(raw_db, str) and raw_db and raw_db != ':memory:':
                try:
                    resolved = contained_database(route)
                    st = os.stat(resolved)
                    if stat.S_ISREG(st.st_mode):
                        return [int(st.st_dev), int(st.st_ino)]
                except Exception:
                    return None
        return None
    try:
        st = os.stat(db_file)
        if stat.S_ISREG(st.st_mode):
            return [int(st.st_dev), int(st.st_ino)]
    except OSError:
        return None
    return None


def _attach_route_databases(connection: sqlite3.Connection, route: Mapping) -> None:
    attachments = route.get('attached_databases', ()) if isinstance(route, Mapping) else ()
    if not isinstance(attachments, (list, tuple)):
        return
    existing = {str(r[1]) for r in connection.execute('PRAGMA database_list').fetchall()}
    for item in attachments:
        if not isinstance(item, Mapping):
            continue
        alias = item.get('name')
        db_val = item.get('database')
        if not isinstance(alias, str) or not alias or alias in existing or alias.lower() in {'main', 'temp'}:
            continue
        sub_route = dict(route, database=db_val)
        db_arg = sqlite_arguments(sub_route)['database']
        connection.execute('ATTACH DATABASE ? AS ' + quote(alias), (db_arg,))


def observe_object_identity(connection: sqlite3.Connection, route: Mapping, spec: dict) -> dict | None:
    schema_name = spec['schema']
    q_schema = quote(schema_name)
    known_schemas = {str(r[1]) for r in connection.execute('PRAGMA database_list').fetchall()} | {'temp'}
    if schema_name not in known_schemas:
        return None
    schema_ver_row = connection.execute(f'PRAGMA {q_schema}.schema_version').fetchone()
    schema_version = int(schema_ver_row[0]) if schema_ver_row is not None else None
    row = connection.execute(
        f'SELECT type, name, tbl_name, rootpage, sql FROM {q_schema}.sqlite_schema WHERE type = ? AND name = ?',
        (spec['schema_object_type'], spec['lookup_name']),
    ).fetchone()
    if row is None:
        return None
    obj_type, obj_name, tbl_name, rootpage, ddl = row
    col_sig = None
    if spec['schema_object_type'] in {'table', 'view'}:
        try:
            cols = connection.execute(f'PRAGMA {q_schema}.table_xinfo({quote(obj_name)})').fetchall()
            col_list = [
                [int(c[0]), str(c[1]), str(c[2] or ''), int(c[3] or 0), c[4], int(c[5] or 0), int(c[6] or 0)]
                for c in cols
            ]
            if spec.get('column_name') is not None and not any(c[1] == spec['column_name'] for c in col_list):
                return None
            col_sig = _sha256(col_list)
        except sqlite3.Error:
            col_sig = None
    return {
        'schema': schema_name,
        'schema_version': schema_version,
        'file_identity': _file_identity_for_schema(connection, route, schema_name),
        'type': str(obj_type),
        'name': str(obj_name),
        'tbl_name': str(tbl_name),
        'rootpage': int(rootpage) if rootpage is not None else None,
        'ddl_sha256': _sha256(str(ddl or '')),
        'ddl': str(ddl or ''),
        'columns_sha256': col_sig,
        'column_name': spec.get('column_name'),
    }


def capture_plan_binding(request: Mapping) -> dict | None:
    if not applies(request):
        return None
    route = request.get('_provider_route')
    if not isinstance(route, Mapping):
        return None
    spec = _extract_target_spec(request['target_resource'])
    handle = request.get('_provider_session_handle')
    if handle is not None:
        observed = observe_object_identity(handle, route, spec)
    else:
        db_val = route.get('database')
        if not isinstance(db_val, str) or not db_val or db_val == ':memory:':
            return None
        try:
            resolved = contained_database(route)
        except Exception:
            return None
        if not os.path.isfile(resolved):
            return None
        args = sqlite_arguments(route)
        with closing(sqlite3.connect(**args)) as probe:
            _attach_route_databases(probe, route)
            observed = observe_object_identity(probe, route, spec)

    if observed is None:
        raise stale_target_error(
            f'SQLite target {spec["schema"]}.{spec["lookup_name"]} no longer exists; refresh catalog before planning',
            reason='target_missing_at_plan',
        )
    if spec['expected_ddl'] is not None and spec['expected_ddl'] != observed['ddl']:
        raise stale_target_error(
            f'SQLite target {spec["schema"]}.{spec["lookup_name"]} DDL changed after catalog capture; refresh catalog before planning',
            reason='ddl_changed_before_plan',
            details={'expected_ddl_sha256': _sha256(spec['expected_ddl']), 'observed_ddl_sha256': observed['ddl_sha256']},
        )
    binding = dict(observed)
    binding.pop('ddl', None)
    binding['spec'] = {k: v for k, v in spec.items() if k != 'expected_ddl'}
    return binding


def verify_binding_under_lock(connection: sqlite3.Connection, route: Mapping, binding: Mapping) -> None:
    spec = binding['spec']
    current = observe_object_identity(connection, route, spec)
    if current is None:
        raise stale_target_error(
            f'SQLite target {spec["schema"]}.{spec["lookup_name"]} was removed or replaced before apply; capture a fresh review',
            reason='target_missing_at_apply',
        )
    if binding.get('file_identity') is not None and current.get('file_identity') != binding.get('file_identity'):
        raise stale_target_error(
            'SQLite database file inode changed since review; capture a fresh review',
            reason='file_identity_changed',
            details={'planned': binding.get('file_identity'), 'observed': current.get('file_identity')},
        )
    for key in ('schema_version', 'type', 'name', 'tbl_name', 'rootpage', 'ddl_sha256', 'columns_sha256'):
        if binding.get(key) != current.get(key):
            raise stale_target_error(
                f'SQLite target {spec["schema"]}.{spec["lookup_name"]} changed since planning ({key} mismatch); replacement object preserved',
                reason=f'stale_{key}',
                details={'field': key, 'planned': binding.get(key), 'observed': current.get(key)},
            )


def apply_with_guard(adapter, client, request: Mapping, connection: sqlite3.Connection | None = None) -> dict:
    payload = request.get('provider_payload') or {}
    binding = payload.get('sqlite_target_identity')
    if not isinstance(binding, Mapping):
        return super(type(adapter), adapter).apply(client, request, connection)
    route = payload.get('route') or {}
    compiled = payload.get('compiled') or {}
    owns_connection = connection is None
    conn = connection or client._connect({'route': route})
    savepoint = None
    locked_tx = False
    commit_requested = False
    rollback_requested = False
    results = []
    try:
        if owns_connection:
            conn.execute('BEGIN IMMEDIATE')
            locked_tx = True
        else:
            savepoint = f'sr_sq_guard_{uuid.uuid4().hex}'
            conn.execute(f'SAVEPOINT {savepoint}')
        verify_binding_under_lock(conn, route, binding)
        cur = conn.cursor()
        try:
            for stmt in compiled.get('statements', ()):
                params = stmt.get('parameters', ())
                if params:
                    cur.execute(stmt['source'], params)
                else:
                    cur.execute(stmt['source'])
                desc = getattr(cur, 'description', None)
                rows = list(cur.fetchall()) if desc else []
                rc = getattr(cur, 'rowcount', None)
                results.append({
                    'rowcount': rc if isinstance(rc, int) else None,
                    'rows': rows,
                })
        finally:
            cur.close()
        if savepoint is not None:
            conn.execute(f'RELEASE SAVEPOINT {savepoint}')
            savepoint = None
        if owns_connection:
            commit_requested = True
            conn.commit()
            locked_tx = False
    except RelationalClientError:
        if savepoint is not None:
            try:
                conn.execute(f'ROLLBACK TO SAVEPOINT {savepoint}')
                conn.execute(f'RELEASE SAVEPOINT {savepoint}')
            except Exception:
                pass
        elif owns_connection and locked_tx:
            try:
                rollback_requested = True
                conn.rollback()
            except Exception:
                pass
        raise
    except Exception as exc:
        if savepoint is not None:
            try:
                conn.execute(f'ROLLBACK TO SAVEPOINT {savepoint}')
                conn.execute(f'RELEASE SAVEPOINT {savepoint}')
            except Exception:
                pass
        elif owns_connection and locked_tx:
            try:
                rollback_requested = True
                conn.rollback()
            except Exception:
                pass
        native_code = getattr(exc, 'sqlite_errorcode', None)
        failure = RelationalClientError(
            f'relational administration execution failed ({type(exc).__name__}): {exc}'
        )
        failure.native_status_codes = (native_code,) if isinstance(native_code, int) else ()
        raise failure from None
    finally:
        if owns_connection:
            client._forget_and_close(conn)
    return {
        'accepted': True,
        'statement_results': results,
        'commit_requested': commit_requested,
        'rollback_requested': rollback_requested,
        'driver_observation_only': True,
        'transaction_finality_interpreted_by_common_code': False,
        'staged_in_provider_session': not owns_connection,
    }

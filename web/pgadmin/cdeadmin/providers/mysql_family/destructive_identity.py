"""Race-safe native server/schema/table continuity for reviewed table DROP.

During plan, observe exact server identity (MySQL server_uuid / MariaDB
server_uid), schema, table name, TABLE_TYPE, ENGINE, CREATE_TIME, and native
InnoDB TABLE_ID without holding table locks across user review. During apply,
on a dedicated administrative connection, verify server continuity, acquire
LOCK TABLES <schema>.<table> WRITE, re-observe the exact target identity while
holding that lock, refuse stale/replaced targets without dispatching DROP, and
always UNLOCK TABLES and release the dedicated connection in finally.
"""
from collections.abc import Mapping
from copy import deepcopy
import re
import uuid

from ...sdk import RelationalClientError
from .mysql_engine_diagnostics import observer_route, release

PRIVILEGE_DENIED_CODES = frozenset({1044, 1045, 1142, 1143, 1227})
MISSING_TABLE_CODES = frozenset({1051, 1146})


def applies(request):
    return (
        isinstance(request, Mapping)
        and request.get('resource_kind') == 'table'
        and request.get('operation_id') == 'drop'
    )


def _quote_ident(name):
    if not isinstance(name, str) or not name or len(name) > 64 or '\x00' in name:
        raise RelationalClientError('Native table identifier requires 1 to 64 characters without NUL')
    return '`' + name.replace('`', '``') + '`'


def _encode_innodb_part(part):
    out = []
    for ch in part:
        code = ord(ch)
        if ('a' <= ch <= 'z') or ('A' <= ch <= 'Z') or ('0' <= ch <= '9') or ch == '_':
            out.append(ch)
        elif code <= 0xFFFF:
            out.append(f'@{code:04x}')
        else:
            out.append(ch)
    return ''.join(out)


def _innodb_name_candidates(schema, table_name, lower_case):
    candidates = []
    pairs = [(schema, table_name)]
    if lower_case in (1, 2, '1', '2'):
        pairs.append((schema.lower(), table_name.lower()))
    for s_val, t_val in pairs:
        for candidate in (
            f'{s_val}/{t_val}',
            f'{_encode_innodb_part(s_val)}/{_encode_innodb_part(t_val)}',
        ):
            if candidate not in candidates:
                candidates.append(candidate)
    return tuple(candidates)


def resolve_target(request, route=None):
    target = request.get('target_resource')
    if not isinstance(target, Mapping) or target.get('resource_kind') != 'table':
        raise RelationalClientError('Select an observed native base table before reviewing DROP')
    native = target.get('native')
    if not isinstance(native, Mapping):
        extensions = target.get('extensions')
        if isinstance(extensions, Mapping):
            for engine_key in ('mysql', 'mariadb'):
                sub = extensions.get(engine_key)
                if isinstance(sub, Mapping) and isinstance(sub.get('native'), Mapping):
                    native = sub['native']
                    break
    native = native if isinstance(native, Mapping) else {}
    if native.get('temporary') is True or str(native.get('table_type', '')).upper() == 'TEMPORARY':
        raise RelationalClientError('Session temporary tables must use explicit retained-session temporary DROP')
    path = target.get('display_path')
    schema = None
    table_name = None
    if isinstance(path, (list, tuple)) and len(path) == 2 and all(isinstance(p, str) and p for p in path):
        schema, table_name = path[0], path[1]
    elif isinstance(path, (list, tuple)) and len(path) == 1 and isinstance(path[0], str) and path[0]:
        table_name = path[0]
        db_candidate = native.get('database') or (route.get('database') if isinstance(route, Mapping) else None)
        if isinstance(db_candidate, str) and db_candidate:
            schema = db_candidate
    if not schema or not table_name:
        raise RelationalClientError('Select a schema-qualified native table before reviewing DROP')
    display_name = target.get('display_name')
    if isinstance(display_name, str) and display_name and display_name != table_name:
        raise RelationalClientError('Target display_name conflicts with display_path')
    _quote_ident(schema)
    _quote_ident(table_name)
    return {
        'schema': schema,
        'table_name': table_name,
        'resource_id': target.get('resource_id'),
        'hints': {
            key: native[key]
            for key in ('server_uuid', 'server_uid', 'innodb_table_id', 'engine', 'table_type')
            if native.get(key) not in (None, '')
        },
    }


def _stale_error(message, *, reason, details=None):
    error = RelationalClientError(message)
    error.stale_target_conflict = True
    error.conflict_reason = reason
    error.native_dispatched = False
    error.native_acknowledged = False
    error.automatic_retry = False
    if details is not None:
        error.conflict_details = details
    return error


def _exec(cursor, engine, mysql_sql, mariadb_sql, params=()):
    sql = mysql_sql if engine == 'mysql' else mariadb_sql
    if params:
        cursor.execute(sql, params)
    else:
        cursor.execute(sql)
    rows = cursor.fetchall()
    return rows


def observe_server(cursor, engine):
    if engine == 'mysql':
        rows = _exec(
            cursor, engine,
            'SELECT VERSION(), @@server_uuid, @@lower_case_table_names, CURRENT_USER(), USER()',
            '',
        )
        if len(rows) != 1:
            raise RelationalClientError('Native MySQL server identity is unavailable')
        version, server_uuid, lower_case, effective_user, session_user = rows[0]
        if str(version).split('-')[0] != '9.7.0' or not isinstance(server_uuid, str) or not re.fullmatch(
            r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', server_uuid
        ):
            raise RelationalClientError('Exact native MySQL 9.7.0 server_uuid is required')
        return {
            'engine': 'mysql',
            'version': str(version),
            'server_uuid': server_uuid,
            'lower_case_table_names': int(lower_case) if lower_case is not None else 0,
            'effective_principal': str(effective_user),
            'authenticated_principal': str(session_user),
        }
    if engine == 'mariadb':
        rows = _exec(
            cursor, engine, '',
            'SELECT VERSION(), @@server_uid, CAST(@@server_id AS CHAR), @@lower_case_table_names, CURRENT_USER(), USER()',
        )
        if len(rows) != 1:
            raise RelationalClientError('Native MariaDB server identity is unavailable')
        version, server_uid, server_id, lower_case, effective_user, session_user = rows[0]
        if str(version).split('-')[0] != '12.2.2' or not isinstance(server_uid, str) or not re.fullmatch(
            r'[A-Za-z0-9+/]{27}=', server_uid
        ):
            raise RelationalClientError('Exact native MariaDB 12.2.2 server_uid is required')
        return {
            'engine': 'mariadb',
            'version': str(version),
            'server_uid': server_uid,
            'server_id': str(server_id),
            'lower_case_table_names': int(lower_case) if lower_case is not None else 0,
            'effective_principal': str(effective_user),
            'authenticated_principal': str(session_user),
        }
    raise RelationalClientError(f'Unsupported destructive-identity engine: {engine}')


def observe_target(cursor, engine, schema, table_name, *, server_info=None):
    server_info = server_info or observe_server(cursor, engine)
    if engine == 'mysql':
        rows = _exec(
            cursor, engine,
            'SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE, ENGINE, '
            'CAST(CREATE_TIME AS CHAR), TABLE_COLLATION '
            'FROM information_schema.TABLES '
            'WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s',
            '',
            (schema, table_name),
        )
    else:
        rows = _exec(
            cursor, engine, '',
            'SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE, ENGINE, '
            'CAST(CREATE_TIME AS CHAR), TABLE_COLLATION '
            'FROM information_schema.TABLES '
            "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? AND TEMPORARY = 'N'",
            (schema, table_name),
        )
    if len(rows) != 1:
        raise _stale_error(
            f'Native table `{schema}`.`{table_name}` does not exist or is not visible; refresh and review DROP again',
            reason='target_missing',
        )
    observed_schema, observed_name, table_type, storage_engine, create_time, collation = rows[0]
    if str(table_type).upper() != 'BASE TABLE':
        raise _stale_error(
            f'Native object `{schema}`.`{table_name}` is `{table_type}`, not a BASE TABLE; refresh and review again',
            reason='table_type_mismatch',
        )
    innodb_id = None
    innodb_space = None
    innodb_name = None
    innodb_status = 'not_applicable'
    if str(storage_engine or '').upper() == 'INNODB':
        candidates = _innodb_name_candidates(
            str(observed_schema), str(observed_name), server_info['lower_case_table_names']
        )
        try:
            if engine == 'mysql':
                placeholders = ', '.join(['%s'] * len(candidates))
                id_rows = _exec(
                    cursor, engine,
                    f'SELECT CAST(TABLE_ID AS CHAR), CAST(SPACE AS CHAR), NAME '
                    f'FROM information_schema.INNODB_TABLES WHERE NAME IN ({placeholders}) ORDER BY TABLE_ID',
                    '',
                    candidates,
                )
            else:
                placeholders = ', '.join(['?'] * len(candidates))
                id_rows = _exec(
                    cursor, engine, '',
                    f'SELECT CAST(TABLE_ID AS CHAR), CAST(SPACE AS CHAR), NAME '
                    f'FROM information_schema.INNODB_SYS_TABLES WHERE NAME IN ({placeholders}) ORDER BY TABLE_ID',
                    candidates,
                )
            if len(id_rows) != 1:
                raise _stale_error(
                    f'Native InnoDB TABLE_ID for `{schema}`.`{table_name}` is unavailable or ambiguous; refresh and review again',
                    reason='innodb_identity_missing',
                )
            innodb_id = str(id_rows[0][0])
            innodb_space = str(id_rows[0][1]) if id_rows[0][1] is not None else None
            innodb_name = str(id_rows[0][2])
            innodb_status = 'observed'
        except RelationalClientError:
            raise
        except Exception as exc:
            errno = getattr(exc, 'errno', None)
            if errno not in PRIVILEGE_DENIED_CODES:
                raise
            innodb_status = 'permission_denied'
    return {
        'engine_id': engine,
        'server_identity': server_info,
        'schema': str(observed_schema),
        'table_name': str(observed_name),
        'table_type': str(table_type),
        'storage_engine': str(storage_engine) if storage_engine is not None else None,
        'create_time': str(create_time) if create_time is not None else None,
        'table_collation': str(collation) if collation is not None else None,
        'innodb_identity_status': innodb_status,
        'innodb_table_id': innodb_id,
        'innodb_space_id': innodb_space,
        'innodb_name': innodb_name,
    }


def _check_hints(observed, hints):
    server_info = observed['server_identity']
    if 'server_uuid' in hints and str(hints['server_uuid']) != server_info.get('server_uuid'):
        raise _stale_error(
            'Selected table server_uuid differs from the live MySQL server; refresh before reviewing DROP',
            reason='server_identity_mismatch',
        )
    if 'server_uid' in hints and str(hints['server_uid']) != server_info.get('server_uid'):
        raise _stale_error(
            'Selected table server_uid differs from the live MariaDB server; refresh before reviewing DROP',
            reason='server_identity_mismatch',
        )
    if 'innodb_table_id' in hints and observed['innodb_identity_status'] == 'observed':
        if str(hints['innodb_table_id']) != observed['innodb_table_id']:
            raise _stale_error(
                'Selected table InnoDB TABLE_ID already changed before review; refresh before reviewing DROP',
                reason='table_id_changed_before_review',
            )
    if 'engine' in hints and observed['storage_engine'] is not None:
        if str(hints['engine']).upper() != observed['storage_engine'].upper():
            raise _stale_error(
                'Selected table storage engine changed before review; refresh before reviewing DROP',
                reason='engine_changed_before_review',
            )
    if 'table_type' in hints and str(hints['table_type']).upper() != observed['table_type'].upper():
        raise _stale_error(
            'Selected table type changed before review; refresh before reviewing DROP',
            reason='table_type_changed_before_review',
        )


def _continuity_tuple(binding):
    server_info = binding['server_identity']
    server_token = server_info.get('server_uuid') if binding['engine_id'] == 'mysql' else server_info.get('server_uid')
    return (
        binding['engine_id'],
        server_token,
        server_info.get('effective_principal'),
        binding['schema'],
        binding['table_name'],
        binding['table_type'],
        binding['storage_engine'],
        binding['create_time'],
        binding['table_collation'],
        binding['innodb_identity_status'],
        binding['innodb_table_id'],
        binding['innodb_space_id'],
    )


def _verify_compiled_drop_sql(compiled, schema, table_name, engine):
    statements = compiled.get('statements')
    if not isinstance(statements, list) or len(statements) != 1:
        raise RelationalClientError('Guarded table DROP requires exactly one native DROP TABLE statement')
    stmt = statements[0]
    if stmt.get('parameters'):
        raise RelationalClientError('Guarded table DROP does not admit bound parameters')
    qualified = f'{_quote_ident(schema)}.{_quote_ident(table_name)}'
    unqualified = _quote_ident(table_name)
    allowed = {
        f'DROP TABLE {qualified}',
        f'DROP TABLE {qualified} RESTRICT',
        f'DROP TABLE {qualified} CASCADE',
        f'DROP TABLE {unqualified}',
        f'DROP TABLE {unqualified} RESTRICT',
        f'DROP TABLE {unqualified} CASCADE',
    }
    if stmt.get('source') not in allowed:
        raise _stale_error(
            'Compiled DROP TABLE target does not match the reviewed native table identity',
            reason='statement_target_mismatch',
        )
    # Always execute fully schema-qualified DROP TABLE so default-schema drift
    # cannot redirect the mutation to another schema.
    source = stmt['source']
    if source.startswith(f'DROP TABLE {unqualified}') and not source.startswith(f'DROP TABLE {qualified}'):
        suffix = source[len(f'DROP TABLE {unqualified}'):]
        source = f'DROP TABLE {qualified}{suffix}'
    return source


def bind_review(client, planned, engine):
    payload = planned.get('provider_payload')
    if not isinstance(payload, Mapping):
        raise RelationalClientError('Table DROP plan payload is invalid')
    compiled = payload.get('compiled')
    if not isinstance(compiled, Mapping):
        raise RelationalClientError('Table DROP compiled plan is invalid')
    spec = resolve_target(compiled, payload.get('route'))
    _verify_compiled_drop_sql(compiled, spec['schema'], spec['table_name'], engine)
    route = observer_route(payload)
    handle = client._connect({'route': route})
    cursor = None
    ready = False
    try:
        handle.autocommit = True
        cursor = handle.cursor()
        observed = observe_target(cursor, engine, spec['schema'], spec['table_name'])
        _check_hints(observed, spec['hints'])
        binding = {
            **observed,
            'requested_schema': spec['schema'],
            'requested_table_name': spec['table_name'],
            'review_nonce': uuid.uuid4().hex,
        }
        payload['destructive_identity'] = deepcopy(binding)
        planned['command_preview']['native_target_identity'] = deepcopy(binding)
        planned.setdefault('warnings', []).append(
            'Guarded DROP TABLE re-verifies native server identity, schema, table type, storage engine, '
            'creation timestamp and InnoDB TABLE_ID while holding LOCK TABLES ... WRITE on a dedicated '
            'administrative connection. Same-name replacements and replayed plans are refused.'
        )
        ready = True
        return planned
    finally:
        cleanup = release(client, handle, cursor)
        if ready and not cleanup['connection_released']:
            raise RelationalClientError('Table DROP review connection release is unconfirmed')


def apply(client, request, connection, engine):
    if connection is not None:
        raise RelationalClientError('Guarded table DROP requires an independently owned administrative connection')
    payload = request.get('provider_payload')
    if not isinstance(payload, Mapping):
        raise RelationalClientError('Table DROP plan payload is invalid')
    compiled = payload.get('compiled')
    binding = payload.get('destructive_identity')
    if not isinstance(compiled, Mapping) or not isinstance(binding, Mapping):
        raise _stale_error(
            'Guarded table DROP requires a server-observed destructive_identity review; refresh and review again',
            reason='missing_destructive_identity',
        )
    if binding.get('engine_id') != engine or not isinstance(binding.get('review_nonce'), str) or not binding['review_nonce']:
        raise _stale_error(
            'Retained destructive_identity does not match this native engine; create a new review',
            reason='invalid_destructive_identity',
        )
    consumed = getattr(client, '_consumed_destructive_reviews', None)
    if consumed is None:
        consumed = set()
        client._consumed_destructive_reviews = consumed
    nonce = binding['review_nonce']
    if nonce in consumed:
        raise _stale_error(
            'This reviewed table DROP plan was already applied or consumed; replay is refused',
            reason='replay_refused',
        )
    spec = resolve_target(compiled, payload.get('route'))
    if spec['schema'] != binding.get('requested_schema') or spec['table_name'] != binding.get('requested_table_name'):
        raise _stale_error(
            'Target resource differs from the reviewed destructive_identity; create a new review',
            reason='target_mismatch',
        )
    drop_sql = _verify_compiled_drop_sql(compiled, binding['schema'], binding['table_name'], engine)
    route = dict(observer_route(payload))
    route.update(read_timeout=15, write_timeout=15)
    handle = client._connect({'route': route})
    cursor = None
    locked = False
    dispatched = False
    acknowledged = False
    response = None
    failure = None
    try:
        handle.autocommit = True
        cursor = handle.cursor()
        cursor.execute('SET SESSION lock_wait_timeout = 5')
        live_server = observe_server(cursor, engine)
        expected_server = binding['server_identity']
        id_key = 'server_uuid' if engine == 'mysql' else 'server_uid'
        if live_server.get(id_key) != expected_server.get(id_key):
            raise _stale_error(
                f'Live {engine} {id_key} differs from the reviewed server; cross-server DROP is refused',
                reason='server_identity_mismatch',
                details={'reviewed': expected_server.get(id_key), 'live': live_server.get(id_key)},
            )
        if live_server.get('effective_principal') != expected_server.get('effective_principal'):
            raise _stale_error(
                'Effective database principal changed since review; refresh and review DROP again',
                reason='principal_changed',
            )
        # Pre-check existence and identity before acquiring WRITE lock so missing or
        # already-replaced tables fail cleanly without unnecessary lock contention.
        pre_lock = observe_target(cursor, engine, binding['schema'], binding['table_name'], server_info=live_server)
        if _continuity_tuple(pre_lock) != _continuity_tuple(binding):
            raise _stale_error(
                'Native table identity changed since review (same-name replacement or altered engine/metadata); DROP refused',
                reason='target_replaced_before_lock',
                details={
                    'reviewed_innodb_table_id': binding.get('innodb_table_id'),
                    'live_innodb_table_id': pre_lock.get('innodb_table_id'),
                },
            )
        qualified = f"{_quote_ident(binding['schema'])}.{_quote_ident(binding['table_name'])}"
        try:
            cursor.execute(f'LOCK TABLES {qualified} WRITE')
            locked = True
        except Exception as lock_exc:
            if getattr(lock_exc, 'errno', None) in MISSING_TABLE_CODES:
                raise _stale_error(
                    f'Native table {qualified} was removed before lock acquisition; DROP refused',
                    reason='target_missing_at_lock',
                ) from None
            raise
        under_lock = observe_target(cursor, engine, binding['schema'], binding['table_name'])
        if _continuity_tuple(under_lock) != _continuity_tuple(binding):
            raise _stale_error(
                'Native table identity changed at lock acquisition (concurrent replacement); DROP refused with replacement preserved',
                reason='target_replaced_under_lock',
                details={
                    'reviewed_innodb_table_id': binding.get('innodb_table_id'),
                    'live_innodb_table_id': under_lock.get('innodb_table_id'),
                },
            )
        consumed.add(nonce)
        dispatched = True
        cursor.execute(drop_sql)
        acknowledged = True
        response = {
            'accepted': True,
            'statement_results': [{
                'source': drop_sql,
                'rowcount': getattr(cursor, 'rowcount', 0),
                'columns': [],
                'rows': [],
            }],
            'commit_requested': False,
            'rollback_requested': False,
            'native_implicit_commit': True,
            'staged_in_provider_session': False,
            'automatic_retry': False,
            'transaction_finality_interpreted_by_common_code': False,
            'destructive_identity_verified': deepcopy(under_lock),
            'lock_held_during_drop': True,
        }
        return response
    except Exception as exc:
        if isinstance(exc, RelationalClientError):
            failure = exc
            if not hasattr(failure, 'native_dispatched'):
                failure.native_dispatched = dispatched
            if not hasattr(failure, 'native_acknowledged'):
                failure.native_acknowledged = acknowledged
            if not hasattr(failure, 'automatic_retry'):
                failure.automatic_retry = False
        else:
            failure = RelationalClientError(
                f'Native {engine} guarded table DROP failed ({type(exc).__name__}): {exc}'
            )
            failure.errno = getattr(exc, 'errno', None)
            failure.sqlstate = getattr(exc, 'sqlstate', None)
            failure.native_status_codes = (failure.errno,) if type(failure.errno) is int else ()
            failure.native_dispatched = dispatched
            failure.native_acknowledged = acknowledged
            failure.automatic_retry = False
        raise failure from None
    finally:
        unlocked = not locked
        if locked and cursor is not None:
            try:
                cursor.execute('UNLOCK TABLES')
                unlocked = True
            except Exception:
                unlocked = False
        cleanup = release(client, handle, cursor)
        cleanup['tables_unlocked'] = unlocked
        if response is not None:
            response['connection_release'] = cleanup
        elif failure is not None:
            failure.connection_release = cleanup

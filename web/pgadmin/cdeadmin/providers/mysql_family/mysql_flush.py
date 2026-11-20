"""Reviewed native MySQL 9.7 FLUSH server and table workflows."""
from collections.abc import Mapping
from copy import deepcopy
import re
import uuid

from ...sdk import RelationalClientError
from .mysql_engine_diagnostics import observer_route, release
from .mysql_instance import environment, target_uuid

KEY = 'mysql_flush'
SERVER_OPERATIONS = {'flush': 'Flush server logs, caches, or status'}
TABLE_OPERATIONS = {'flush': 'Flush table'}
OPERATIONS = SERVER_OPERATIONS

SERVER_TARGETS = (
    'BINARY LOGS',
    'ENGINE LOGS',
    'ERROR LOGS',
    'GENERAL LOGS',
    'LOGS',
    'OPTIMIZER_COSTS',
    'PRIVILEGES',
    'RELAY LOGS',
    'SLOW LOGS',
    'STATUS',
    'USER_RESOURCES',
)
BINLOG_MODES = ('DEFAULT', 'NO_WRITE_TO_BINLOG', 'LOCAL')
TABLE_LOCK_MODES = ('NONE', 'WITH_READ_LOCK', 'FOR_EXPORT', 'UNLOCK')


def _quote_ident(name):
    if not isinstance(name, str) or not name or len(name) > 64 or '\x00' in name:
        raise RelationalClientError('Native MySQL identifier requires 1 to 64 characters without NUL')
    return '`' + name.replace('`', '``') + '`'


def _quote_channel(channel):
    if not isinstance(channel, str) or not channel or len(channel) > 64 or '\x00' in channel:
        raise RelationalClientError('Replication channel name requires 1 to 64 characters without NUL')
    return "'" + channel.replace('\\', '\\\\').replace("'", "''") + "'"


def _table_path(target):
    if not isinstance(target, Mapping) or target.get('resource_kind') != 'table':
        raise RelationalClientError('Select an exact native MySQL base table')
    native = target.get('native') or {}
    if native.get('temporary') is True:
        raise RelationalClientError('Temporary tables do not use base-table FLUSH administration')
    path = target.get('display_path')
    if not isinstance(path, (list, tuple)) or len(path) != 2 or any(
        not isinstance(part, str) or not part for part in path
    ):
        raise RelationalClientError('Select a schema-qualified MySQL table')
    _quote_ident(path[0])
    _quote_ident(path[1])
    return path[0], path[1]


def compile_server_flush(operation, draft, target):
    if operation != 'flush' or not isinstance(draft, Mapping):
        raise RelationalClientError('Select typed native MySQL server FLUSH options')
    server_uuid = target_uuid(target)
    allowed = {'targets', 'binlog_mode', 'relay_channel', 'lock_wait_seconds', 'confirmation'}
    if set(draft) - allowed:
        raise RelationalClientError('Unknown MySQL server FLUSH option')
    if draft.get('confirmation') != target.get('display_name'):
        raise RelationalClientError('Confirm the exact MySQL server display name')
    raw_targets = draft.get('targets')
    if isinstance(raw_targets, str) and raw_targets:
        raw_targets = [raw_targets]
    if not isinstance(raw_targets, list) or not (1 <= len(raw_targets) <= len(SERVER_TARGETS)):
        raise RelationalClientError('Select at least one native MySQL 9.7 FLUSH target')
    targets = []
    for item in raw_targets:
        val = item.get('value') if isinstance(item, Mapping) else item
        if val == 'HOSTS':
            err = RelationalClientError(
                'MySQL 9.7 removed FLUSH HOSTS; use TRUNCATE TABLE performance_schema.host_cache'
            )
            err.error_code = 'flush_hosts_removed_in_9_7'
            raise err
        if val not in SERVER_TARGETS:
            raise RelationalClientError(f'Unsupported MySQL 9.7 FLUSH target: {val}')
        if val in targets:
            raise RelationalClientError('Duplicate FLUSH target selected')
        targets.append(val)
    binlog_mode = draft.get('binlog_mode', 'DEFAULT') or 'DEFAULT'
    if binlog_mode not in BINLOG_MODES:
        raise RelationalClientError('Select DEFAULT, NO_WRITE_TO_BINLOG, or LOCAL binary-log mode')
    channel = draft.get('relay_channel')
    if channel not in (None, ''):
        if 'RELAY LOGS' not in targets:
            raise RelationalClientError('Relay channel applies only when RELAY LOGS is selected')
        channel_clause = ' FOR CHANNEL ' + _quote_channel(channel)
    else:
        channel_clause = ''
    timeout = draft.get('lock_wait_seconds', 15)
    if type(timeout) is not int or not (1 <= timeout <= 120):
        raise RelationalClientError('Native lock wait requires 1 to 120 seconds')
    prefix = 'FLUSH ' + ('' if binlog_mode == 'DEFAULT' else binlog_mode + ' ')
    parts = [t + (channel_clause if t == 'RELAY LOGS' else '') for t in targets]
    sql = prefix + ', '.join(parts)
    warnings = [
        'Server FLUSH runs on a dedicated administrative connection with an implicit commit and no automatic replay.',
        'MySQL enforces RELOAD or granular FLUSH_OPTIMIZER_COSTS / FLUSH_PRIVILEGES / FLUSH_STATUS / FLUSH_USER_RESOURCES privileges.',
    ]
    if 'PRIVILEGES' in targets:
        warnings.append('FLUSH PRIVILEGES is deprecated in MySQL 9.7 when grant tables were not modified directly.')
    return {
        'statements': [{'source': sql, 'parameters': ()}],
        KEY: {
            'scope': 'server',
            'operation': 'flush',
            'targets': targets,
            'binlog_mode': binlog_mode,
            'relay_channel': channel or None,
            'lock_wait_seconds': timeout,
            'draft': deepcopy(dict(draft)),
            'target': deepcopy(dict(target)),
            'server_uuid': server_uuid,
            'retained_session_required': False,
        },
        'warnings': warnings,
    }


def compile_table_flush(operation, draft, target):
    if operation != 'flush' or not isinstance(draft, Mapping):
        raise RelationalClientError('Select typed native MySQL table FLUSH options')
    schema, table_name = _table_path(target)
    allowed = {'binlog_mode', 'lock_mode', 'lock_wait_seconds', 'confirmation'}
    if set(draft) - allowed:
        raise RelationalClientError('Unknown MySQL table FLUSH option')
    if draft.get('confirmation') != target.get('display_name'):
        raise RelationalClientError('Confirm the exact MySQL table name')
    binlog_mode = draft.get('binlog_mode', 'DEFAULT') or 'DEFAULT'
    if binlog_mode not in BINLOG_MODES:
        raise RelationalClientError('Select DEFAULT, NO_WRITE_TO_BINLOG, or LOCAL binary-log mode')
    lock_mode = draft.get('lock_mode', 'NONE') or 'NONE'
    if lock_mode not in TABLE_LOCK_MODES:
        raise RelationalClientError('Select NONE, WITH_READ_LOCK, FOR_EXPORT, or UNLOCK table flush mode')
    timeout = draft.get('lock_wait_seconds', 15)
    if type(timeout) is not int or not (1 <= timeout <= 120):
        raise RelationalClientError('Native lock wait requires 1 to 120 seconds')
    qualified = f'{_quote_ident(schema)}.{_quote_ident(table_name)}'
    if lock_mode == 'UNLOCK':
        if binlog_mode != 'DEFAULT':
            raise RelationalClientError('UNLOCK TABLES does not accept binary-log modifiers')
        sql = 'UNLOCK TABLES'
    else:
        prefix = 'FLUSH ' + ('' if binlog_mode == 'DEFAULT' else binlog_mode + ' ')
        suffix = (
            ' WITH READ LOCK' if lock_mode == 'WITH_READ_LOCK'
            else ' FOR EXPORT' if lock_mode == 'FOR_EXPORT'
            else ''
        )
        sql = f'{prefix}TABLES {qualified}{suffix}'
    retained = lock_mode in {'WITH_READ_LOCK', 'FOR_EXPORT', 'UNLOCK'}
    native = target.get('native') or {}
    warnings = [
        (
            'Retained-session table FLUSH lock holds native metadata/read locks on your selected session '
            'until you explicitly run UNLOCK TABLES or close that session.'
            if retained else
            'Table FLUSH closes cached table handles on a dedicated administrative connection; MySQL enforces RELOAD or FLUSH_TABLES.'
        )
    ]
    return {
        'statements': [{'source': sql, 'parameters': ()}],
        KEY: {
            'scope': 'table',
            'operation': 'flush',
            'schema': schema,
            'table_name': table_name,
            'binlog_mode': binlog_mode,
            'lock_mode': lock_mode,
            'lock_wait_seconds': timeout,
            'draft': deepcopy(dict(draft)),
            'target': deepcopy(dict(target)),
            'server_uuid': native.get('server_uuid'),
            'retained_session_required': retained,
        },
        'warnings': warnings,
    }


def compile_operation(operation, draft, target):
    if isinstance(target, Mapping) and target.get('resource_kind') == 'table':
        return compile_table_flush(operation, draft, target)
    return compile_server_flush(operation, draft, target)


def _observe_flush_state(cursor, intent):
    cursor.execute(
        "SELECT VARIABLE_NAME, VARIABLE_VALUE FROM performance_schema.global_status "
        "WHERE VARIABLE_NAME IN ('Flush_commands', 'Uptime_since_flush_status') ORDER BY VARIABLE_NAME"
    )
    status = {str(k): str(v) for k, v in cursor.fetchall()}
    out = {'global_status': status}
    if intent['scope'] == 'table' and intent.get('lock_mode') != 'UNLOCK':
        cursor.execute(
            'SELECT TABLE_TYPE, ENGINE FROM information_schema.TABLES '
            'WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s',
            (intent['schema'], intent['table_name']),
        )
        rows = cursor.fetchall()
        if len(rows) != 1 or str(rows[0][0]).upper() != 'BASE TABLE':
            raise RelationalClientError('Selected MySQL base table is missing or no longer a BASE TABLE')
        out['table'] = {'table_type': str(rows[0][0]), 'engine': str(rows[0][1])}
        if intent.get('lock_mode') == 'FOR_EXPORT' and str(rows[0][1]).upper() != 'INNODB':
            raise RelationalClientError('FLUSH TABLES ... FOR EXPORT requires an InnoDB base table')
    return out


def bind_review(client, planned):
    payload = planned['provider_payload']
    intent = payload['compiled'][KEY]
    if intent.get('retained_session_required'):
        # Retained-session locks bind to the caller's selected session_id.
        intent['review'] = {'review_nonce': uuid.uuid4().hex, 'retained_session': True}
        planned['command_preview']['retained_session_lock'] = {
            'lock_mode': intent['lock_mode'],
            'schema': intent['schema'],
            'table_name': intent['table_name'],
        }
        return planned
    handle = client._connect({'route': observer_route(payload)})
    cursor = None
    ready = False
    try:
        handle.autocommit = True
        cursor = handle.cursor()
        identity = environment(cursor)
        if intent.get('server_uuid') and identity['server_uuid'] != intent['server_uuid']:
            raise RelationalClientError('Live MySQL server_uuid differs from the selected target')
        before = _observe_flush_state(cursor, intent)
        intent['review'] = {
            'execution_identity': identity,
            'before': before,
            'review_nonce': uuid.uuid4().hex,
        }
        planned['command_preview'].update(
            native_execution_identity=identity,
            native_flush_observation=before,
        )
        ready = True
        return planned
    finally:
        cleanup = release(client, handle, cursor)
        if ready and not cleanup['connection_released']:
            raise RelationalClientError('MySQL FLUSH review connection release is unconfirmed')


def apply(client, request, connection=None):
    payload = request['provider_payload']
    compiled = payload['compiled']
    intent = compiled[KEY]
    checked = deepcopy(compiled)
    review = checked[KEY].pop('review', None)
    checked[KEY].pop('mysql_session_id', None)
    if not isinstance(review, Mapping) or compile_operation(
        intent['operation'], intent['draft'], intent['target']
    ) != checked:
        raise RelationalClientError('Review the exact native MySQL FLUSH command before dispatch')
    consumed = getattr(client, '_consumed_flush_reviews', None)
    if consumed is None:
        consumed = set()
        client._consumed_flush_reviews = consumed
    nonce = review.get('review_nonce')
    if not isinstance(nonce, str) or nonce in consumed:
        raise RelationalClientError('This reviewed MySQL FLUSH plan was already consumed; replay is refused')

    if intent.get('retained_session_required'):
        if connection is None or not intent.get('mysql_session_id'):
            raise RelationalClientError(
                'FLUSH TABLES WITH READ LOCK / FOR EXPORT / UNLOCK requires a retained session'
            )
        from ..native_editor import session_access
        with session_access(client, connection, 'mysql'):
            client._executions.sessions.get(connection)
            cursor = connection.cursor()
            dispatched = acknowledged = False
            try:
                cursor.execute('SET SESSION lock_wait_timeout = %s', (intent['lock_wait_seconds'],))
                if intent['lock_mode'] != 'UNLOCK':
                    _observe_flush_state(cursor, intent)
                consumed.add(nonce)
                dispatched = True
                cursor.execute(compiled['statements'][0]['source'])
                acknowledged = True
                cursor.execute('SHOW WARNINGS LIMIT 64')
                warnings = [
                    {'level': str(r[0]), 'code': int(r[1]), 'message': str(r[2])}
                    for r in cursor.fetchall()
                ]
                locked_now = intent['lock_mode'] in {'WITH_READ_LOCK', 'FOR_EXPORT'}
                connection._cdeadmin_retained_flush_lock = locked_now
                return {
                    'accepted': True,
                    'commit_requested': False,
                    'rollback_requested': False,
                    'native_implicit_commit': True,
                    'staged_in_provider_session': True,
                    'automatic_retry': False,
                    'transaction_finality_interpreted_by_common_code': False,
                    'flush_observation': {
                        'scope': 'table',
                        'lock_mode': intent['lock_mode'],
                        'retained_lock_active': locked_now,
                        'native_dispatched': True,
                        'native_acknowledged': True,
                        'native_warnings': warnings,
                    },
                }
            except Exception as exc:
                err = exc if isinstance(exc, RelationalClientError) else RelationalClientError(
                    f'Native MySQL retained-session FLUSH failed ({type(exc).__name__}): {exc}'
                )
                err.errno = getattr(exc, 'errno', None)
                err.sqlstate = getattr(exc, 'sqlstate', None)
                err.native_status_codes = (err.errno,) if type(err.errno) is int else ()
                err.native_dispatched = dispatched
                err.native_acknowledged = acknowledged
                err.automatic_retry = False
                raise err from None
            finally:
                cursor.close()

    if connection is not None:
        raise RelationalClientError('MySQL FLUSH requires a dedicated administrative connection')
    handle = client._connect({'route': observer_route(payload)})
    cursor = None
    dispatched = acknowledged = False
    response = failure = None
    try:
        handle.autocommit = True
        cursor = handle.cursor()
        identity = environment(cursor)
        if identity != review.get('execution_identity'):
            raise RelationalClientError('MySQL server or principal identity changed since review')
        before = _observe_flush_state(cursor, intent)
        cursor.execute('SET SESSION lock_wait_timeout = %s', (intent['lock_wait_seconds'],))
        consumed.add(nonce)
        dispatched = True
        cursor.execute(compiled['statements'][0]['source'])
        acknowledged = True
        cursor.execute('SHOW WARNINGS LIMIT 64')
        warnings = [
            {'level': str(r[0]), 'code': int(r[1]), 'message': str(r[2])}
            for r in cursor.fetchall()
        ]
        after = _observe_flush_state(cursor, intent)
        response = {
            'accepted': True,
            'commit_requested': False,
            'rollback_requested': False,
            'native_implicit_commit': True,
            'staged_in_provider_session': False,
            'automatic_retry': False,
            'transaction_finality_interpreted_by_common_code': False,
            'flush_observation': {
                'scope': intent['scope'],
                'targets': intent.get('targets'),
                'binlog_mode': intent['binlog_mode'],
                'execution_identity': identity,
                'before': before,
                'after': after,
                'native_warnings': warnings,
                'native_dispatched': True,
                'native_acknowledged': True,
            },
        }
        return response
    except Exception as exc:
        failure = exc if isinstance(exc, RelationalClientError) else RelationalClientError(
            f'Native MySQL FLUSH failed ({type(exc).__name__}): {exc}'
        )
        failure.errno = getattr(exc, 'errno', None)
        failure.sqlstate = getattr(exc, 'sqlstate', None)
        failure.native_status_codes = (failure.errno,) if type(failure.errno) is int else ()
        failure.native_dispatched = dispatched
        failure.native_acknowledged = acknowledged
        failure.automatic_retry = False
        raise failure from None
    finally:
        cleanup = release(client, handle, cursor)
        if response is not None:
            response['connection_release'] = cleanup
        elif failure is not None:
            failure.connection_release = cleanup

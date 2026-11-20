"""Reviewed native MariaDB 12.2.2 FLUSH server and table workflows."""
from collections.abc import Mapping
from copy import deepcopy
import uuid

from ...sdk import RelationalClientError
from .mariadb_server_diagnostics import environment, target_uid
from .mysql_engine_diagnostics import observer_route, release

KEY = 'mariadb_flush'
OPERATIONS = {
    'flush': ('Flush server logs, caches, or statistics', 'FLUSH'),
}
TABLE_OPERATIONS = {
    'flush': ('Flush table', 'FLUSH TABLES'),
}

SERVER_TARGETS = (
    'BINARY LOGS',
    'CLIENT_STATISTICS',
    'ENGINE LOGS',
    'ERROR LOGS',
    'GENERAL LOGS',
    'GLOBAL STATUS',
    'HOSTS',
    'INDEX_STATISTICS',
    'LOGS',
    'PRIVILEGES',
    'QUERY_RESPONSE_TIME',
    'RELAY LOGS',
    'SLOW LOGS',
    'SSL',
    'STATUS',
    'TABLE_STATISTICS',
    'THREADS',
    'USER_RESOURCES',
    'USER_STATISTICS',
)
BINLOG_MODES = ('DEFAULT', 'NO_WRITE_TO_BINLOG', 'LOCAL')
TABLE_LOCK_MODES = ('NONE', 'WITH_READ_LOCK', 'FOR_EXPORT', 'UNLOCK')


def _quote_ident(name):
    if not isinstance(name, str) or not name or len(name) > 64 or '\x00' in name:
        raise RelationalClientError('Native MariaDB identifier requires 1 to 64 characters without NUL')
    return '`' + name.replace('`', '``') + '`'


def _quote_channel(channel):
    if not isinstance(channel, str) or not channel or len(channel) > 64 or '\x00' in channel:
        raise RelationalClientError('MariaDB replication connection name requires 1 to 64 characters without NUL')
    return "'" + channel.replace('\\', '\\\\').replace("'", "''") + "'"


def form(operation, resource_kind='server'):
    from ...ui_descriptors import UIDescriptorService
    from .descriptor_contracts import field_contract
    row = next(
        value for value in UIDescriptorService().engine('mariadb')['operations']
        if value['operation_id'] == operation and value['resource_kind'] == resource_kind
    )
    return {
        'form_id': f'mariadb.{resource_kind}.{operation}',
        'title': row['title'],
        'fields': [field_contract(value) for value in row['fields']],
    }


def _table_path(target):
    if not isinstance(target, Mapping) or target.get('resource_kind') != 'table':
        raise RelationalClientError('Select an exact native MariaDB base table')
    native = target.get('native') or {}
    if native.get('temporary') is True or str(native.get('temporary', '')).upper() == 'Y':
        raise RelationalClientError('Session temporary tables do not use base-table FLUSH administration')
    path = target.get('display_path')
    if not isinstance(path, (list, tuple)) or len(path) != 2 or any(
        not isinstance(part, str) or not part for part in path
    ):
        raise RelationalClientError('Select a schema-qualified MariaDB table')
    _quote_ident(path[0])
    _quote_ident(path[1])
    return path[0], path[1]


def compile_server_flush(operation, draft, target):
    if operation != 'flush' or not isinstance(draft, Mapping):
        raise RelationalClientError('Select typed native MariaDB server FLUSH options')
    uid = target_uid(target)
    allowed = {'targets', 'binlog_mode', 'relay_channel', 'lock_wait_seconds', 'confirmation'}
    if set(draft) - allowed:
        raise RelationalClientError('Unknown MariaDB server FLUSH option')
    if draft.get('confirmation') != target.get('display_name'):
        raise RelationalClientError('Confirm the exact MariaDB server display name')
    raw_targets = draft.get('targets')
    if isinstance(raw_targets, str) and raw_targets:
        raw_targets = [raw_targets]
    if not isinstance(raw_targets, list) or not (1 <= len(raw_targets) <= len(SERVER_TARGETS)):
        raise RelationalClientError('Select at least one native MariaDB FLUSH target')
    targets = []
    for item in raw_targets:
        val = item.get('value') if isinstance(item, Mapping) else item
        if val not in SERVER_TARGETS:
            raise RelationalClientError(f'Unsupported MariaDB 12.2.2 FLUSH target: {val}')
        if val in targets:
            raise RelationalClientError('Duplicate MariaDB FLUSH target selected')
        targets.append(val)
    binlog_mode = draft.get('binlog_mode', 'DEFAULT') or 'DEFAULT'
    if binlog_mode not in BINLOG_MODES:
        raise RelationalClientError('Select DEFAULT, NO_WRITE_TO_BINLOG, or LOCAL binary-log mode')
    channel = draft.get('relay_channel')
    if channel not in (None, ''):
        if 'RELAY LOGS' not in targets:
            raise RelationalClientError('Relay connection name applies only when RELAY LOGS is selected')
        channel_clause = ' ' + _quote_channel(channel)
    else:
        channel_clause = ''
    timeout = draft.get('lock_wait_seconds', 15)
    if type(timeout) is not int or not (1 <= timeout <= 120):
        raise RelationalClientError('Native lock wait requires 1 to 120 seconds')
    prefix = 'FLUSH ' + ('' if binlog_mode == 'DEFAULT' else binlog_mode + ' ')
    parts = [t + (channel_clause if t == 'RELAY LOGS' else '') for t in targets]
    sql = prefix + ', '.join(parts)
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
            'server_uid': uid,
            'retained_session_required': False,
        },
        'warnings': [
            'MariaDB server FLUSH runs on a dedicated connection with an implicit commit and no automatic replay.',
            'Native RELOAD / BINLOG ADMIN / REPLICATION_SLAVE_ADMIN privileges remain authoritative.',
        ],
    }


def compile_table_flush(operation, draft, target):
    if operation != 'flush' or not isinstance(draft, Mapping):
        raise RelationalClientError('Select typed native MariaDB table FLUSH options')
    schema, table_name = _table_path(target)
    allowed = {'binlog_mode', 'lock_mode', 'lock_wait_seconds', 'confirmation'}
    if set(draft) - allowed:
        raise RelationalClientError('Unknown MariaDB table FLUSH option')
    if draft.get('confirmation') != target.get('display_name'):
        raise RelationalClientError('Confirm the exact MariaDB table name')
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
            'server_uid': native.get('server_uid'),
            'retained_session_required': retained,
        },
        'warnings': [
            (
                'Retained-session table FLUSH lock holds native locks on your selected session '
                'until you explicitly run UNLOCK TABLES or close that session.'
                if retained else
                'MariaDB table FLUSH runs on a dedicated administrative connection; native RELOAD privilege applies.'
            )
        ],
    }


def compile_operation(operation, draft, target):
    if isinstance(target, Mapping) and target.get('resource_kind') == 'table':
        return compile_table_flush(operation, draft, target)
    return compile_server_flush(operation, draft, target)


def _observe_flush_state(cursor, intent):
    cursor.execute(
        "SELECT VARIABLE_NAME, VARIABLE_VALUE FROM information_schema.GLOBAL_STATUS "
        "WHERE VARIABLE_NAME IN ('FLUSH_COMMANDS', 'UPTIME_SINCE_FLUSH_STATUS') ORDER BY VARIABLE_NAME"
    )
    status = {str(k): str(v) for k, v in cursor.fetchall()}
    out = {'global_status': status}
    if intent['scope'] == 'server' and 'QUERY_RESPONSE_TIME' in intent.get('targets', ()):
        cursor.execute(
            "SELECT PLUGIN_STATUS FROM information_schema.PLUGINS WHERE PLUGIN_NAME = 'QUERY_RESPONSE_TIME'"
        )
        rows = cursor.fetchall()
        if not rows or str(rows[0][0]).upper() != 'ACTIVE':
            err = RelationalClientError(
                'MariaDB QUERY_RESPONSE_TIME plugin is not installed or active; FLUSH QUERY_RESPONSE_TIME is unavailable'
            )
            err.error_code = 'plugin_not_installed'
            raise err
        out['query_response_time_plugin'] = 'ACTIVE'
    if intent['scope'] == 'table' and intent.get('lock_mode') != 'UNLOCK':
        cursor.execute(
            "SELECT TABLE_TYPE, ENGINE FROM information_schema.TABLES "
            "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? AND TEMPORARY = 'N'",
            (intent['schema'], intent['table_name']),
        )
        rows = cursor.fetchall()
        if len(rows) != 1 or str(rows[0][0]).upper() != 'BASE TABLE':
            raise RelationalClientError('Selected MariaDB base table is missing or no longer a BASE TABLE')
        out['table'] = {'table_type': str(rows[0][0]), 'engine': str(rows[0][1])}
    return out


def bind_review(client, planned):
    payload = planned['provider_payload']
    intent = payload['compiled'][KEY]
    if intent.get('retained_session_required'):
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
        if intent.get('server_uid') and identity['server_uid'] != intent['server_uid']:
            raise RelationalClientError('Live MariaDB server_uid differs from the selected target')
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
            raise RelationalClientError('MariaDB FLUSH review connection release is unconfirmed')


def apply(client, request, connection=None):
    payload = request['provider_payload']
    compiled = payload['compiled']
    intent = compiled[KEY]
    checked = deepcopy(compiled)
    review = checked[KEY].pop('review', None)
    checked[KEY].pop('mariadb_session_id', None)
    if not isinstance(review, Mapping) or compile_operation(
        intent['operation'], intent['draft'], intent['target']
    ) != checked:
        raise RelationalClientError('Review the exact native MariaDB FLUSH command before dispatch')
    consumed = getattr(client, '_consumed_flush_reviews', None)
    if consumed is None:
        consumed = set()
        client._consumed_flush_reviews = consumed
    nonce = review.get('review_nonce')
    if not isinstance(nonce, str) or nonce in consumed:
        raise RelationalClientError('This reviewed MariaDB FLUSH plan was already consumed; replay is refused')

    if intent.get('retained_session_required'):
        if connection is None or not intent.get('mariadb_session_id'):
            raise RelationalClientError(
                'MariaDB FLUSH TABLES WITH READ LOCK / FOR EXPORT / UNLOCK requires a retained session'
            )
        from ..native_editor import session_access
        with session_access(client, connection, 'mariadb'):
            client._executions.sessions.get(connection)
            cursor = connection.cursor()
            dispatched = acknowledged = False
            try:
                cursor.execute(f"SET SESSION lock_wait_timeout = {int(intent['lock_wait_seconds'])}")
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
                    f'Native MariaDB retained-session FLUSH failed ({type(exc).__name__}): {exc}'
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
        raise RelationalClientError('MariaDB FLUSH requires a dedicated administrative connection')
    handle = client._connect({'route': observer_route(payload)})
    cursor = None
    dispatched = acknowledged = False
    response = failure = None
    try:
        handle.autocommit = True
        cursor = handle.cursor()
        identity = environment(cursor)
        if identity != review.get('execution_identity'):
            raise RelationalClientError('MariaDB server or principal identity changed since review')
        before = _observe_flush_state(cursor, intent)
        cursor.execute(f"SET SESSION lock_wait_timeout = {int(intent['lock_wait_seconds'])}")
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
            f'Native MariaDB FLUSH failed ({type(exc).__name__}): {exc}'
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

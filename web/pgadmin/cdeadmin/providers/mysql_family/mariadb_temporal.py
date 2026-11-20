"""Reviewed MariaDB system-versioning and application-time period lifecycle.

MariaDB SQL temporal tables (WITH SYSTEM VERSIONING and application-time
PERIOD FOR) are native relational schema/data features completely distinct from
ScratchBird monitoring history. Destructive history or period-boundary removals
require explicit destructive_history_confirmed=True and exact server_uid/table
continuity revalidation before dispatch.
"""
from collections.abc import Mapping
from copy import deepcopy
import re

from ...sdk import RelationalClientError
from .mariadb_catalog import identifier as quote_identifier
from .mariadb_server_diagnostics import environment
from .mysql_engine_diagnostics import observer_route, release
from .mysql_indexes import structural_definition

KEY = 'mariadb_temporal_lifecycle'
TABLE_OPERATIONS = {
    'add_system_versioning': ('Add system versioning', 'ADD SYSTEM VERSIONING'),
    'drop_system_versioning': ('Drop system versioning', 'DROP SYSTEM VERSIONING'),
    'truncate_system_versioning_history': ('Truncate system-versioning history', 'DELETE HISTORY'),
    'rotate_system_time_partitions': ('Add system-time history partitions', 'ADD PARTITION'),
    'add_application_period': ('Add application-time period', 'ADD PERIOD FOR'),
    'drop_application_period': ('Drop application-time period', 'DROP PERIOD FOR'),
}
DESTRUCTIVE_OPERATIONS = frozenset({
    'drop_system_versioning',
    'truncate_system_versioning_history',
    'drop_application_period',
})
DESTRUCTIVE = DESTRUCTIVE_OPERATIONS


def identifier(value):
    try:
        if isinstance(value, str):
            value.encode('utf8')
        return quote_identifier(value)
    except ValueError:
        raise RelationalClientError('Native MariaDB identifier must be nonempty text without NUL') from None


def form(operation, kind='table'):
    from ...ui_descriptors import UIDescriptorService
    from .descriptor_contracts import field_contract
    row = next(
        item for item in UIDescriptorService().engine('mariadb')['operations']
        if item['resource_kind'] == kind and item['operation_id'] == operation
    )
    return {
        'form_id': f'mariadb.{kind}.{operation}',
        'title': row['title'],
        'fields': [field_contract(field) for field in row['fields']],
    }


def _target_identity(target):
    if not isinstance(target, Mapping) or target.get('resource_kind') != 'table':
        raise RelationalClientError('Select a committed MariaDB table')
    path = target.get('display_path')
    if not isinstance(path, list) or len(path) != 2:
        raise RelationalClientError('Exact MariaDB database and table identity is required')
    native = target.get('native')
    if not isinstance(native, Mapping):
        ext = (target.get('extensions') or {}).get('mariadb')
        native = ext.get('native') if isinstance(ext, Mapping) else {}
    if isinstance(native, Mapping) and native.get('temporary') is True:
        raise RelationalClientError('MariaDB temporary tables do not support system-versioning lifecycle operations')
    uid = native.get('server_uid') if isinstance(native, Mapping) else None
    if uid is not None and (not isinstance(uid, str) or not uid):
        raise RelationalClientError('Invalid target server_uid metadata')
    return [str(path[0]), str(path[1])], uid


def compile_operation(operation, draft, target):
    if operation not in TABLE_OPERATIONS or not isinstance(draft, Mapping):
        raise RelationalClientError('Select a MariaDB temporal lifecycle operation')
    path, target_uid = _target_identity(target)
    draft = deepcopy(dict(draft))
    if draft.get('confirmation') != target.get('display_name'):
        raise RelationalClientError('Confirm the exact MariaDB table name')

    qualified = '.'.join(identifier(part) for part in path)
    parameters = []

    if operation in DESTRUCTIVE_OPERATIONS and draft.get('destructive_history_confirmed') is not True:
        raise RelationalClientError(
            'Confirm irreversible MariaDB temporal history or period-boundary removal (destructive_history_confirmed=True)'
        )

    if operation == 'add_system_versioning':
        allowed = {'start_column', 'end_column', 'invisible_period_columns', 'confirmation'}
        if set(draft) - allowed:
            raise RelationalClientError('Unknown add_system_versioning option')
        start_col = draft.get('start_column') or ''
        end_col = draft.get('end_column') or ''
        invisible = draft.get('invisible_period_columns', True)
        if type(invisible) is not bool:
            raise RelationalClientError('invisible_period_columns must be boolean')
        if bool(start_col) != bool(end_col):
            raise RelationalClientError('Supply both start_column and end_column or leave both empty for implicit period columns')
        if start_col and end_col:
            if start_col == end_col:
                raise RelationalClientError('System-time start_column and end_column must be distinct')
            inv = ' INVISIBLE' if invisible else ''
            sql = (
                f'ALTER TABLE {qualified} '
                f'ADD COLUMN {identifier(start_col)} TIMESTAMP(6) GENERATED ALWAYS AS ROW START{inv}, '
                f'ADD COLUMN {identifier(end_col)} TIMESTAMP(6) GENERATED ALWAYS AS ROW END{inv}, '
                f'ADD PERIOD FOR SYSTEM_TIME ({identifier(start_col)}, {identifier(end_col)}), '
                'ADD SYSTEM VERSIONING'
            )
        else:
            sql = f'ALTER TABLE {qualified} ADD SYSTEM VERSIONING'

    elif operation == 'drop_system_versioning':
        allowed = {'drop_period_columns', 'start_column', 'end_column', 'destructive_history_confirmed', 'confirmation'}
        if set(draft) - allowed:
            raise RelationalClientError('Unknown drop_system_versioning option')
        drop_cols = draft.get('drop_period_columns', False)
        if type(drop_cols) is not bool:
            raise RelationalClientError('drop_period_columns must be boolean')
        parts = []
        if drop_cols:
            s_col, e_col = draft.get('start_column'), draft.get('end_column')
            if not s_col or not e_col or s_col == e_col:
                raise RelationalClientError('Supply distinct start_column and end_column when dropping explicit period columns')
            parts.append(f'DROP COLUMN {identifier(s_col)}')
            parts.append(f'DROP COLUMN {identifier(e_col)}')
        parts.append('DROP SYSTEM VERSIONING')
        sql = f"ALTER TABLE {qualified} {', '.join(parts)}"

    elif operation == 'truncate_system_versioning_history':
        allowed = {'cutoff_mode', 'before_timestamp', 'before_transaction', 'destructive_history_confirmed', 'confirmation'}
        if set(draft) - allowed:
            raise RelationalClientError('Unknown truncate_system_versioning_history option')
        mode = draft.get('cutoff_mode', 'ALL')
        if mode not in {'ALL', 'BEFORE_TIMESTAMP', 'BEFORE_TRANSACTION'}:
            raise RelationalClientError('Select ALL, BEFORE_TIMESTAMP or BEFORE_TRANSACTION history truncation mode')
        sql = f'DELETE HISTORY FROM {qualified}'
        if mode == 'BEFORE_TIMESTAMP':
            ts = draft.get('before_timestamp')
            if not isinstance(ts, str) or not ts.strip() or '\x00' in ts or len(ts) > 64:
                raise RelationalClientError('Supply a bounded MariaDB timestamp for BEFORE SYSTEM_TIME')
            sql += ' BEFORE SYSTEM_TIME TIMESTAMP %s'
            parameters.append(ts.strip())
        elif mode == 'BEFORE_TRANSACTION':
            trx = draft.get('before_transaction')
            if not isinstance(trx, str) or not re.fullmatch(r'(?:0|[1-9][0-9]{0,19})', trx) or int(trx) > 2**64 - 1:
                raise RelationalClientError('Supply exact unsigned decimal transaction ID for BEFORE SYSTEM_TIME TRANSACTION')
            sql += f' BEFORE SYSTEM_TIME TRANSACTION {trx}'

    elif operation == 'rotate_system_time_partitions':
        allowed = {
            'rotation_action',
            'partitions_to_add',
            'partition_count',
            'row_limit',
            'interval_value',
            'interval_unit',
            'history_partitions',
            'confirmation',
        }
        if set(draft) - allowed:
            raise RelationalClientError('Unknown rotate_system_time_partitions option')
        action = str(draft.get('rotation_action') or 'ADD_HISTORY_PARTITIONS').upper()
        if action == 'ADD_HISTORY_PARTITIONS':
            count = draft.get('partitions_to_add', draft.get('partition_count', 1))
            if type(count) is not int or not 1 <= count <= 1024:
                raise RelationalClientError('partitions_to_add must be an integer from 1 to 1024')
            sql = f'ALTER TABLE {qualified} ADD PARTITION PARTITIONS {count}'
        elif action == 'PARTITION_BY_LIMIT':
            row_limit = draft.get('row_limit')
            hist_parts = draft.get('history_partitions', 2)
            if type(row_limit) is not int or not 1 <= row_limit <= 2147483647:
                raise RelationalClientError('row_limit must be a positive integer')
            if type(hist_parts) is not int or not 1 <= hist_parts <= 1024:
                raise RelationalClientError('history_partitions must be an integer from 1 to 1024')
            total_parts = hist_parts + 1
            sql = f'ALTER TABLE {qualified} PARTITION BY SYSTEM_TIME LIMIT {row_limit} PARTITIONS {total_parts}'
        elif action == 'PARTITION_BY_INTERVAL':
            ival = draft.get('interval_value')
            iunit = str(draft.get('interval_unit') or 'DAY').upper()
            hist_parts = draft.get('history_partitions', 2)
            if type(ival) is not int or not 1 <= ival <= 1000000:
                raise RelationalClientError('interval_value must be a positive integer')
            if iunit not in {'SECOND', 'MINUTE', 'HOUR', 'DAY', 'MONTH', 'YEAR'}:
                raise RelationalClientError('Select SECOND, MINUTE, HOUR, DAY, MONTH or YEAR interval_unit')
            if type(hist_parts) is not int or not 1 <= hist_parts <= 1024:
                raise RelationalClientError('history_partitions must be an integer from 1 to 1024')
            total_parts = hist_parts + 1
            sql = f'ALTER TABLE {qualified} PARTITION BY SYSTEM_TIME INTERVAL {ival} {iunit} PARTITIONS {total_parts}'
        else:
            raise RelationalClientError('Select ADD_HISTORY_PARTITIONS, PARTITION_BY_LIMIT or PARTITION_BY_INTERVAL')

    elif operation == 'add_application_period':
        allowed = {'period_name', 'start_column', 'end_column', 'create_boundary_columns', 'boundary_type', 'confirmation'}
        if set(draft) - allowed:
            raise RelationalClientError('Unknown add_application_period option')
        p_name = draft.get('period_name')
        s_col = draft.get('start_column')
        e_col = draft.get('end_column')
        if not isinstance(p_name, str) or not p_name or p_name.strip().upper() == 'SYSTEM_TIME':
            raise RelationalClientError('Application period name is required and cannot be SYSTEM_TIME')
        if not s_col or not e_col or s_col == e_col:
            raise RelationalClientError('Application period requires distinct start_column and end_column')
        create_cols = draft.get('create_boundary_columns', False)
        if type(create_cols) is not bool:
            raise RelationalClientError('create_boundary_columns must be boolean')
        clauses = []
        if create_cols:
            b_type = str(draft.get('boundary_type') or 'DATETIME(6)').upper()
            if b_type not in {'DATE', 'DATETIME', 'DATETIME(6)', 'TIMESTAMP', 'TIMESTAMP(6)'}:
                raise RelationalClientError('Select DATE, DATETIME, DATETIME(6), TIMESTAMP or TIMESTAMP(6) boundary type')
            clauses.append(f'ADD COLUMN {identifier(s_col)} {b_type} NOT NULL')
            clauses.append(f'ADD COLUMN {identifier(e_col)} {b_type} NOT NULL')
        clauses.append(f'ADD PERIOD FOR {identifier(p_name)} ({identifier(s_col)}, {identifier(e_col)})')
        sql = f"ALTER TABLE {qualified} {', '.join(clauses)}"

    else:
        allowed = {'period_name', 'destructive_history_confirmed', 'confirmation'}
        if set(draft) - allowed:
            raise RelationalClientError('Unknown drop_application_period option')
        p_name = draft.get('period_name')
        if not isinstance(p_name, str) or not p_name or p_name.strip().upper() == 'SYSTEM_TIME':
            raise RelationalClientError('Select a non-SYSTEM_TIME application period name to drop')
        sql = f'ALTER TABLE {qualified} DROP PERIOD FOR {identifier(p_name)}'

    implicit_commit = operation != 'truncate_system_versioning_history'
    return {
        'statements': [{'source': sql, 'parameters': tuple(parameters)}],
        KEY: {
            'operation': operation,
            'table': path,
            'expected_server_uid': target_uid,
            'destructive': operation in DESTRUCTIVE_OPERATIONS,
            'destructive_history_confirmed': bool(draft.get('destructive_history_confirmed')),
            'implicit_commit': implicit_commit,
            'draft': draft,
        },
        'warnings': [
            'Executes MariaDB native SQL temporal lifecycle on an independently owned connection.',
            'Historical row removal or DROP SYSTEM VERSIONING permanently discards MariaDB system-versioned row history.',
        ],
    }


def _observe_table(cursor, path, sql_mode):
    qualified = '.'.join(identifier(part) for part in path)
    cursor.execute('SHOW CREATE TABLE ' + qualified)
    row = cursor.fetchone()
    if not row or len(row) < 2 or not isinstance(row[1], str):
        raise RelationalClientError('Target MariaDB table is unavailable')
    ddl = row[1]
    cursor.execute(
        'SELECT PERIOD, START_COLUMN_NAME, END_COLUMN_NAME '
        'FROM information_schema.PERIODS '
        'WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s ORDER BY PERIOD',
        (path[0], path[1]),
    )
    periods = [
        {'period_name': r[0], 'start_column': r[1], 'end_column': r[2]}
        for r in cursor.fetchall()
    ]
    cursor.execute(
        'SELECT PARTITION_NAME, PARTITION_METHOD, PARTITION_DESCRIPTION '
        'FROM information_schema.PARTITIONS '
        'WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND PARTITION_NAME IS NOT NULL '
        'ORDER BY PARTITION_ORDINAL_POSITION',
        (path[0], path[1]),
    )
    partitions = [
        {'name': r[0], 'method': r[1], 'description': r[2]}
        for r in cursor.fetchall()
    ]
    sys_ver = 'WITH SYSTEM VERSIONING' in ddl.upper() or any(
        str(p['period_name']).upper() == 'SYSTEM_TIME' for p in periods
    )
    current_rows = 0
    historical_rows = 0
    cursor.execute(f'SELECT COUNT(*) FROM {qualified}')
    (c_cnt,) = cursor.fetchone()
    current_rows = int(c_cnt or 0)
    if sys_ver:
        cursor.execute(f'SELECT COUNT(*) FROM {qualified} FOR SYSTEM_TIME ALL')
        (all_cnt,) = cursor.fetchone()
        historical_rows = max(0, int(all_cnt or 0) - current_rows)
    return {
        'ddl': ddl,
        'table_structure_sha256': structural_definition(ddl, sql_mode),
        'system_versioned': sys_ver,
        'system_time_partitioned': 'PARTITION BY SYSTEM_TIME' in ddl.upper() or any(
            str(p['method'] or '').upper() == 'SYSTEM_TIME' for p in partitions
        ),
        'current_rows': current_rows,
        'historical_rows': historical_rows,
        'periods': periods,
        'partitions': partitions,
    }


def _public(obs):
    return {k: v for k, v in obs.items() if k != 'ddl'}


def _validate_preconditions(operation, draft, obs):
    if operation == 'add_system_versioning' and obs['system_versioned']:
        raise RelationalClientError('Target MariaDB table is already system-versioned')
    if operation in {'drop_system_versioning', 'truncate_system_versioning_history'} and not obs['system_versioned']:
        raise RelationalClientError('Target MariaDB table does not have WITH SYSTEM VERSIONING enabled')
    if operation == 'rotate_system_time_partitions':
        action = str(draft.get('rotation_action') or 'ADD_HISTORY_PARTITIONS').upper()
        if action == 'ADD_HISTORY_PARTITIONS' and not obs['system_time_partitioned']:
            raise RelationalClientError('Target MariaDB table is not partitioned by SYSTEM_TIME')
        if action in {'PARTITION_BY_LIMIT', 'PARTITION_BY_INTERVAL'} and not obs['system_versioned']:
            raise RelationalClientError('Target MariaDB table does not have WITH SYSTEM VERSIONING enabled')
    if operation == 'drop_application_period':
        wanted = draft.get('period_name')
        if not any(p['period_name'] == wanted and str(p['period_name']).upper() != 'SYSTEM_TIME' for p in obs['periods']):
            raise RelationalClientError(f'Application period {wanted!r} does not exist on the target table')


def bind_review(client, planned):
    payload = planned['provider_payload']
    intent = payload['compiled'][KEY]
    handle = client._connect({'route': observer_route(payload)})
    cursor = None
    try:
        handle.autocommit = True
        cursor = handle.cursor()
        env = environment(cursor)
        if intent['expected_server_uid'] and env['server_uid'] != intent['expected_server_uid']:
            raise RelationalClientError('MariaDB server_uid differs from the selected table registration')
        before = _observe_table(cursor, intent['table'], env['sql_mode'])
        _validate_preconditions(intent['operation'], intent['draft'], before)
        intent['review'] = {
            'execution_identity': env,
            'before': _public(before),
        }
        planned['command_preview'].update(
            native_execution_identity=env,
            temporal_table_observation=_public(before),
        )
        return planned
    finally:
        release(client, handle, cursor)


def apply(client, request, connection=None):
    if connection is not None:
        raise RelationalClientError('MariaDB temporal lifecycle operations require an independently owned connection')
    payload = request['provider_payload']
    compiled = payload['compiled']
    intent = compiled[KEY]
    review = intent.get('review')
    if not isinstance(review, Mapping):
        raise RelationalClientError('Review the MariaDB temporal lifecycle operation before execution')
    if intent['destructive'] and not intent.get('destructive_history_confirmed'):
        raise RelationalClientError('Irreversible MariaDB temporal history loss was not confirmed')

    handle = client._connect({'route': observer_route(payload)})
    cursor = None
    dispatched = acknowledged = False
    try:
        handle.autocommit = True
        cursor = handle.cursor()
        env = environment(cursor)
        before = _observe_table(cursor, intent['table'], env['sql_mode'])
        if (
            env['server_uid'] != review['execution_identity']['server_uid']
            or before['table_structure_sha256'] != review['before']['table_structure_sha256']
        ):
            raise RelationalClientError('MariaDB server_uid or table schema changed since review')
        _validate_preconditions(intent['operation'], intent['draft'], before)
        cursor.execute('SET SESSION system_versioning_alter_history = KEEP')

        stmt = compiled['statements'][0]
        params = stmt.get('parameters') or ()
        dispatched = True
        if params:
            cursor.execute(stmt['source'], params)
        else:
            cursor.execute(stmt['source'])
        acknowledged = True
        affected_rows = cursor.rowcount
        cursor.execute('SHOW WARNINGS')
        warnings = [
            {'level': str(level), 'code': int(code), 'message': str(msg)}
            for level, code, msg in cursor.fetchall()
        ]
        after = _observe_table(cursor, intent['table'], env['sql_mode'])
        return {
            'accepted': True,
            'native_acknowledged': True,
            'native_implicit_commit': intent['implicit_commit'],
            'destructive_history_confirmed': intent['destructive_history_confirmed'],
            'rows_affected': affected_rows,
            'commit_requested': False,
            'rollback_requested': False,
            'staged_in_provider_session': False,
            'automatic_retry': False,
            'native_warnings': warnings,
            'driver_observation_only': True,
            'transaction_finality_interpreted_by_common_code': False,
            'temporal_observation': {
                'execution_identity': env,
                'before': _public(before),
                'after': _public(after),
                'concurrent_external_ddl_fenced': False,
            },
        }
    except Exception as error:
        failure = error if isinstance(error, RelationalClientError) else RelationalClientError(
            f'MariaDB temporal lifecycle operation failed ({type(error).__name__}: {error})'
        )
        failure.native_dispatched = dispatched
        failure.native_acknowledged = acknowledged
        failure.automatic_retry = False
        failure.errno = getattr(error, 'errno', None)
        failure.sqlstate = getattr(error, 'sqlstate', None)
        raise failure from None
    finally:
        release(client, handle, cursor)

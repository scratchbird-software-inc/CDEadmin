"""Native Community page tracking; SQL replies and UDF outcomes stay separate."""
from collections.abc import Mapping
from copy import deepcopy
import re

from ...sdk import RelationalClientError
from .mysql_instance import environment, target_uuid

OPERATIONS = {
    'inspect_page_tracking': 'Inspect native InnoDB page tracking',
    'start_page_tracking': 'Start or reset native InnoDB page tracking',
    'stop_page_tracking': 'Stop native InnoDB page tracking',
    'count_tracked_pages': 'Count native tracked page IDs',
    'set_page_tracking_backup_id': 'Set native page-tracking backup ID',
    'export_tracked_pages': 'Export native tracked page IDs',
    'purge_page_tracking': 'Purge native page-tracking files',
}
READS = {'inspect_page_tracking', 'count_tracked_pages'}
FUNCTIONS = ('mysqlbackup_page_track_set', 'mysqlbackup_page_track_get_start_lsn',
             'mysqlbackup_page_track_get_changed_page_count',
             'mysqlbackup_page_track_get_changed_pages', 'mysqlbackup_page_track_purge_up_to')


def number(draft, name):
    value = draft.get(name)
    if not isinstance(value, str) or not re.fullmatch(r'(?:0|[1-9][0-9]{0,19})', value) or int(value) > 2**64 - 1:
        raise RelationalClientError('Use exact unsigned 64-bit decimal text for native LSN inputs')
    return int(value)


def compile_operation(operation, draft, target):
    if operation not in OPERATIONS or not isinstance(draft, Mapping):
        raise RelationalClientError('Select a native MySQL page-tracking operation')
    uuid = target_uuid(target); allowed = set(); params = ()
    if operation not in READS: allowed.add('confirmation')
    if operation in {'start_page_tracking', 'stop_page_tracking', 'set_page_tracking_backup_id', 'purge_page_tracking'}:
        allowed.add('coordinated_backup_window')
        if draft.get('coordinated_backup_window') is not True:
            raise RelationalClientError('Confirm coordination with all native backup/page-tracking clients')
    if operation in {'count_tracked_pages', 'export_tracked_pages'}:
        allowed.update(('start_lsn', 'stop_lsn'))
        params = (number(draft, 'start_lsn'), number(draft, 'stop_lsn'))
    if operation == 'purge_page_tracking':
        allowed.update(('purge_lsn', 'tracking_files_not_required'))
        params = (number(draft, 'purge_lsn'),)
        if draft.get('tracking_files_not_required') is not True:
            raise RelationalClientError('Confirm that the native tracking files are no longer required by any backup')
    if operation == 'set_page_tracking_backup_id':
        allowed.update(('value_mode', 'backup_id', 'prior_index_removal_confirmed'))
        if draft.get('prior_index_removal_confirmed') is not True:
            raise RelationalClientError('Confirm that changing the native backup ID can delete the prior exported index file')
        mode = draft.get('value_mode', 'VALUE')
        if mode not in {'VALUE', 'NULL', 'DEFAULT'}:
            raise RelationalClientError('Select a native backup ID value, NULL or DEFAULT')
        value = draft.get('backup_id')
        if mode == 'VALUE' and (not isinstance(value, str) or len(value) > 4096 or '\0' in value):
            raise RelationalClientError('Use native backup ID text of at most 4096 characters')
        source = 'SET GLOBAL `mysqlbackup.backupid` = ' + ('%s' if mode == 'VALUE' else mode)
        params = (value,) if mode == 'VALUE' else ()
    else:
        suffix = {'inspect_page_tracking': 'get_start_lsn()', 'start_page_tracking': 'set(1)',
                  'stop_page_tracking': 'set(0)', 'count_tracked_pages': 'get_changed_page_count(%s,%s)',
                  'export_tracked_pages': 'get_changed_pages(%s,%s)', 'purge_page_tracking': 'purge_up_to(%s)'}[operation]
        source = 'SELECT mysqlbackup_page_track_' + suffix
    if set(draft) - allowed or operation not in READS and draft.get('confirmation') != target['display_name']:
        raise RelationalClientError('Confirm the exact native MySQL server and page-tracking options')
    return {'statements': [{'source': source, 'parameters': params}],
            'mysql_page_tracking': {'operation': operation, 'draft': dict(draft),
                                    'target': deepcopy(dict(target)), 'server_uuid': uuid},
            'warnings': [
                'These native Community component interfaces manage page-ID tracking. They do not copy data files, construct an incremental backup or establish recoverability.',
                'Start resets an already active native tracking window. Native stop first starts/resets tracking and then stops it. Coordinate with other backup clients; review does not fence them.',
                'Setting mysqlbackup.backupid can interrupt a transfer and delete the component\'s prior exported index, even when assigning the same ID. Export is a separate action and never changes the backup ID.',
                'Native range inputs may be expanded internally. Zero selects the native current group/checkpoint where supported; adjusted endpoints are not returned by these UDFs. An SQL acknowledgement is separate from the native scalar result.',
                'The index is written on the database host in datadir/#meb, not on the application host. No file existence, complete backup chain, restored data or production cutover is attested. No action is automatically replayed.',
            ]}


def form(operation, field):
    fields = []
    if operation in {'count_tracked_pages', 'export_tracked_pages'}:
        fields += [field('start_lsn', 'Native start LSN (0 selects current group)', 'text', True, default='0'),
                   field('stop_lsn', 'Native stop LSN (0 selects latest tracked checkpoint)', 'text', True, default='0')]
    if operation == 'purge_page_tracking':
        fields += [field('purge_lsn', 'Native purge LSN (0 selects checkpoint)', 'text', True, default='0'),
                   field('tracking_files_not_required', 'Tracking files are no longer required by any backup', 'boolean', True, default=False)]
    if operation == 'set_page_tracking_backup_id':
        fields += [field('value_mode', 'Native backup ID source', 'select', default='VALUE', options=('VALUE', 'NULL', 'DEFAULT')),
                   {**field('backup_id', 'Native backup ID text (export requires digits)', 'text'), 'visible_when': {'field_id': 'value_mode', 'equals': 'VALUE'}},
                   field('prior_index_removal_confirmed', 'The prior exported index may be deleted, including when reusing the same ID', 'boolean', True, default=False)]
    if operation in {'start_page_tracking', 'stop_page_tracking', 'set_page_tracking_backup_id', 'purge_page_tracking'}:
        fields.append(field('coordinated_backup_window', 'This change is coordinated with all native backup/page-tracking clients', 'boolean', True, default=False))
    if operation not in READS: fields.append(field('confirmation', 'Exact server name', 'text', True))
    return {'form_id': 'mysql.server.' + operation, 'title': OPERATIONS[operation], 'fields': fields}


def scalar(cursor, source, parameters=()):
    cursor.execute(source, parameters); row = cursor.fetchone()
    if not row or len(row) != 1 or type(row[0]) is not int or not -(2**63) <= row[0] <= 2**63 - 1:
        raise RelationalClientError('An exact native signed integer UDF result is required')
    return row[0]


def observe(cursor):
    cursor.execute("SELECT component_id,component_group_id,component_urn FROM mysql.component WHERE component_urn='file://component_mysqlbackup'")
    components = cursor.fetchall()
    if len(components) != 1:
        raise RelationalClientError('Install the native Community mysqlbackup component before using page tracking')
    # The native getter checks BACKUP_ADMIN on this independent connection.
    first = scalar(cursor, 'SELECT mysqlbackup_page_track_get_start_lsn()')
    cursor.execute('SELECT @@GLOBAL.`mysqlbackup.backupid`,@@GLOBAL.datadir')
    backup_id, directory = cursor.fetchone()
    if backup_id is not None and (not isinstance(backup_id, str) or len(backup_id) > 4096):
        raise RelationalClientError('The current native backup ID exceeds the bounded review')
    if not isinstance(directory, str) or not directory:
        raise RelationalClientError('The native page-tracking host directory is unavailable')
    return {'component': list(components[0]), 'native_first_active_start_lsn': str(first),
            'native_active_window_observed': first > 0, 'native_backup_id': backup_id,
            'native_host_directory': directory + '#meb',
            'native_export_filename': backup_id + '.idx' if backup_id and re.fullmatch(r'[0-9]+', backup_id) else None,
            'export_file_observed': False, 'all_native_reset_points_enumerated': False}


def bind_review(client, planned):
    payload = planned['provider_payload']; intent = payload['compiled']['mysql_page_tracking']
    handle = client._connect({'route': payload['route']}); cursor = None
    try:
        handle.autocommit = True; cursor = handle.cursor(); identity = environment(cursor)
        if identity['server_uuid'] != intent['server_uuid']:
            raise RelationalClientError('Native MySQL instance differs from the selected page-tracking server')
        before = observe(cursor)
        intent['review'] = {'execution_identity': identity, 'before': before}
        planned['command_preview'].update(native_execution_identity=identity, native_page_tracking=before)
        return planned
    finally:
        if cursor is not None: client._safe_close(cursor)
        client._forget_and_close(handle)


def apply(client, request, connection=None):
    if connection is not None:
        raise RelationalClientError('Page tracking requires an independently owned connection')
    payload = request['provider_payload']; compiled = payload['compiled']; intent = compiled['mysql_page_tracking']
    checked = deepcopy(compiled); review = checked['mysql_page_tracking'].pop('review', None)
    if not isinstance(review, Mapping) or compile_operation(intent['operation'], intent['draft'], intent['target']) != checked:
        raise RelationalClientError('Review the exact native page-tracking action before dispatch')
    handle = client._connect({'route': payload['route']}); cursor = None; dispatched = acknowledged = False
    try:
        handle.autocommit = True; handle.get_warnings = True; handle.raise_on_warnings = False
        cursor = handle.cursor(); identity = environment(cursor)
        if identity != review['execution_identity']:
            raise RelationalClientError('Native page-tracking execution identity changed since review')
        before = observe(cursor); operation = intent['operation']
        if operation not in READS and before != review['before']:
            raise RelationalClientError('Native page-tracking inputs changed since review')
        statement = compiled['statements'][0]; result = None; later_error = None
        dispatched = True
        if operation == 'set_page_tracking_backup_id': cursor.execute(statement['source'], statement['parameters'])
        else: result = scalar(cursor, statement['source'], statement['parameters'])
        acknowledged = True
        warnings = [{'level': level, 'code': code, 'message': text} for level, code, text in (cursor.warnings or ())]
        try: after = observe(cursor)
        except Exception as error:
            after = None; later_error = {'error_type': type(error).__name__, 'native_error_code': getattr(error, 'errno', None)}
        # Native count returns negative error codes; export returns a status code.
        # Purge's LSN_MAX sentinel is not evidence that anything was removed.
        interpretation = ('setting-acknowledged' if result is None else
                          'native-returned-failure' if result < 0 or operation == 'export_tracked_pages' and result != 0 else
                          'native-no-purge-boundary-sentinel' if operation == 'purge_page_tracking' and result == 2**63 - 1 else
                          'native-status-zero' if operation == 'export_tracked_pages' else 'native-integer-result')
        return {'accepted': True, 'native_implicit_commit': False, 'commit_requested': False, 'rollback_requested': False,
                'staged_in_provider_session': False, 'automatic_retry': False, 'native_warnings': warnings,
                'driver_observation_only': True, 'transaction_finality_interpreted_by_common_code': False,
                'page_tracking_observation': {'operation': operation, 'execution_identity': identity,
                    'native_dispatched': dispatched, 'native_acknowledged': acknowledged,
                    'native_scalar_result': None if result is None else str(result), 'native_result_interpretation': interpretation,
                    'native_outcome_failed': interpretation == 'native-returned-failure',
                    'before': before, 'after': after, 'later_observation_error': later_error,
                    'prior_export_removal_possible': operation == 'set_page_tracking_backup_id',
                    'native_range_endpoints_adjusted_observed': False, 'export_file_observed': False,
                    'incremental_backup_established': False, 'recoverability_established': False}}
    except Exception as error:
        failure = error if isinstance(error, RelationalClientError) else RelationalClientError('Native MySQL page-tracking action failed (' + type(error).__name__ + ')')
        failure.native_dispatched = dispatched; failure.native_acknowledged = acknowledged; failure.automatic_retry = False
        failure.errno = getattr(error, 'errno', None); failure.sqlstate = getattr(error, 'sqlstate', None)
        failure.native_status_codes = (failure.errno,) if type(failure.errno) is int else ()
        raise failure from None
    finally:
        if cursor is not None: client._safe_close(cursor)
        client._forget_and_close(handle)

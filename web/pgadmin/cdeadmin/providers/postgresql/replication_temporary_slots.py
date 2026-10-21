"""Temporary replication slots and snapshots on one native walsender.

Status and review read local acknowledgements. Sending an observation command
would invalidate an exported snapshot. Cached receipts are never a slot catalog.
"""
from copy import deepcopy
from collections import deque, OrderedDict
import hashlib
from pathlib import Path
import re
import uuid

from .temporary_slots import TemporarySlotError, name


def options(operation, value):
    if not isinstance(value, dict) or not isinstance(operation, str) or operation not in {'physical_create', 'logical_create', 'drop', 'logical_stream', 'snapshot_end', 'snapshot_tables', 'snapshot_inspect', 'snapshot_copy'}:
        raise TemporarySlotError('Select a native temporary replication command')
    allowed = {'timeout_seconds', 'invalidate_snapshot'}
    if operation == 'snapshot_end':
        allowed.add('decision')
    elif operation in {'snapshot_tables', 'snapshot_inspect', 'snapshot_copy'}:
        allowed.update(('offset', 'limit', 'schema') if operation == 'snapshot_tables' else
                       ('relation_oid',) if operation == 'snapshot_inspect' else ('relation_oid', 'include_descendants', 'format', 'copy_options'))
    else:
        allowed.add('slot')
    if operation == 'physical_create':
        allowed.add('reserve_wal')
    if operation == 'logical_create':
        allowed.update(('plugin', 'two_phase', 'failover', 'snapshot'))
    if operation == 'logical_stream':
        allowed.update(('start_lsn', 'plugin_options', 'max_messages', 'max_capture_bytes',
                        'max_duration_seconds', 'acknowledge_flush'))
    if set(value) - allowed:
        raise TemporarySlotError('Select exact native temporary replication options')
    result = {'timeout_seconds': value.get('timeout_seconds', 30),
              'invalidate_snapshot': value.get('invalidate_snapshot', False)}
    if operation == 'snapshot_end':
        if value.get('decision') not in ('commit', 'rollback'):
            raise TemporarySlotError('Select an explicit native snapshot transaction end')
        result['decision'] = value['decision']
    elif operation not in {'snapshot_tables', 'snapshot_inspect', 'snapshot_copy'}:
        result['slot'] = name(value.get('slot'))
    if operation in {'snapshot_tables', 'snapshot_inspect', 'snapshot_copy'}:
        from .replication_snapshot_copy import options as copy_options
        result.update(copy_options(operation, {key: item for key, item in value.items()
                                               if key not in {'timeout_seconds', 'invalidate_snapshot'}}))
    timeout = result['timeout_seconds']
    if timeout is not None and (type(timeout) is not int or not 1 <= timeout <= 2147483647):
        raise TemporarySlotError('Select a native command deadline or no deadline')
    if operation == 'physical_create':
        result['reserve_wal'] = value.get('reserve_wal', False)
    if operation == 'logical_create':
        result.update(plugin=value.get('plugin', 'pgoutput'), snapshot=value.get('snapshot', 'export'),
                      two_phase=value.get('two_phase', False), failover=value.get('failover', False))
        plugin = result['plugin']
        try:
            valid = isinstance(plugin, str) and 1 <= len(plugin.encode('utf8')) <= 63 and '\0' not in plugin
        except UnicodeError:
            valid = False
        if not valid:
            raise TemporarySlotError('Select an exact UTF8 native output plugin of at most 63 bytes')
        if '"' in plugin:
            raise TemporarySlotError('The pinned 18.3 replication parser cannot represent an embedded plugin quote; use the native SQL slot workflow')
        if not isinstance(result['snapshot'], str) or result['snapshot'] not in {'export', 'nothing', 'use'}:
            raise TemporarySlotError('Select native snapshot export, no snapshot or an owned snapshot transaction')
    if operation == 'logical_stream':
        from .replication_stream_options import options as stream_options
        result.update(stream_options({key: item for key, item in value.items()
                                      if key not in {'slot', 'timeout_seconds', 'invalidate_snapshot'}}))
    for key in ('invalidate_snapshot', 'reserve_wal', 'two_phase', 'failover'):
        if key in result and type(result[key]) is not bool:
            raise TemporarySlotError('Native temporary replication switches require booleans')
    return result


def statement(operation, selected):
    from psycopg import sql
    if operation == 'snapshot_end':
        return sql.SQL('COMMIT' if selected['decision'] == 'commit' else 'ROLLBACK')
    slot = sql.Identifier(selected['slot'])
    if operation == 'drop':
        return sql.SQL('DROP_REPLICATION_SLOT {}').format(slot)
    if operation == 'physical_create':
        return sql.SQL('CREATE_REPLICATION_SLOT {} TEMPORARY PHYSICAL (RESERVE_WAL {})').format(
            slot, sql.SQL('true' if selected['reserve_wal'] else 'false'))
    return sql.SQL('CREATE_REPLICATION_SLOT {} TEMPORARY LOGICAL {} (SNAPSHOT {}, TWO_PHASE {}, FAILOVER {})').format(
        slot, sql.Identifier(selected['plugin']), sql.Literal(selected['snapshot']),
        sql.SQL('true' if selected['two_phase'] else 'false'), sql.SQL('true' if selected['failover'] else 'false'))


def _text(value):
    return value.decode('utf8') if isinstance(value, bytes) else value


class ReplicationTemporarySlots:
    """One command owner; no reconnect and no SQL catalog/health commands."""
    def __init__(self, connection, source):
        from psycopg import ClientCursor
        from psycopg.rows import tuple_row
        self.connection = connection
        self.resource_id = str(uuid.uuid4())
        self.usable = True
        self.acknowledgements = deque(maxlen=100)
        self.acknowledgement_count = 0
        self.owned_slots = set()
        self.owned_slot_kinds = {}
        self.snapshot = None
        self.used_snapshot = None
        self.owns_snapshot_transaction = False
        self.copy_sources = OrderedDict()
        self.require_idle()
        if connection.info.server_version != 180003:
            raise TemporarySlotError('Temporary replication requires native PostgreSQL18.3')
        with ClientCursor(connection, row_factory=tuple_row) as cursor:
            cursor.execute('IDENTIFY_SYSTEM')
            identity, timeline, _lsn, database = map(_text, cursor.fetchone())
        observed = {'system_identifier': identity, 'timeline': int(timeline),
                    'server_version': connection.info.server_version,
                    'authenticated_principal': connection.info.user,
                    'database': database,
                    'database_target_id': 'postgresql-replication-database:' + database.encode('utf8').hex()
                    if isinstance(database, str) else None,
                    'admission_interface': 'logical-replication'}
        if any(observed[key] != source.get(key) for key in observed):
            raise TemporarySlotError('The retained replication backend reached another reviewed identity')
        self.source = observed
        self.backend_pid = str(connection.info.backend_pid)
        self.backend_started_epoch = None
        self.adapter_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

    def require_idle(self):
        from psycopg.pq import TransactionStatus
        connection = self.connection
        expected = TransactionStatus.INTRANS if getattr(self, 'owns_snapshot_transaction', False) else TransactionStatus.IDLE
        if (not self.usable or connection.closed or connection.broken or
                not connection.autocommit or connection.info.transaction_status != expected):
            raise TemporarySlotError('The original native replication backend is unavailable; reconnect never recreates its slots or snapshot')

    def inventory(self, offset=0, limit=25):
        if type(offset) is not int or not 0 <= offset <= 9223372036854775807 or type(limit) is not int or not 1 <= limit <= 100:
            raise TemporarySlotError('Select a bounded native acknowledgement page')
        self.require_idle()
        first = self.acknowledgement_count - len(self.acknowledgements)
        selected_offset = max(offset, first)
        recent = list(self.acknowledgements)
        return {'acknowledgements': deepcopy(recent[selected_offset - first:selected_offset - first + limit]),
                'acknowledgement_count': self.acknowledgement_count,
                'acknowledgement_window_start': first, 'full_command_receipts_separately_paged': True,
                'offset': selected_offset, 'limit': limit, 'more': selected_offset + limit < self.acknowledgement_count,
                'slot_catalog_observed': False, 'snapshot': deepcopy(self.snapshot),
                'used_snapshot': deepcopy(getattr(self, 'used_snapshot', None)),
                'owns_snapshot_transaction': getattr(self, 'owns_snapshot_transaction', False),
                'copy_sources_cached': len(getattr(self, 'copy_sources', {})), 'copy_source_cache_limit': 100,
                'complete_copy_catalog_cached': False,
                'acknowledged_owned_slot_count': len(self.owned_slots),
                'observation_source': 'retained-native-command-acknowledgements',
                'server_health_checked': False}

    def review(self, operation, value):
        self.require_idle()
        selected = options(operation, value)
        if getattr(self, 'owns_snapshot_transaction', False) and operation not in {'snapshot_end', 'snapshot_tables', 'snapshot_inspect', 'snapshot_copy'}:
            raise TemporarySlotError('End the original snapshot transaction before another replication command')
        if operation in {'snapshot_end', 'snapshot_tables', 'snapshot_inspect', 'snapshot_copy'} and not getattr(self, 'owns_snapshot_transaction', False):
            raise TemporarySlotError('No owned native snapshot transaction is open')
        if self.snapshot is not None and not selected['invalidate_snapshot']:
            raise TemporarySlotError('Confirm invalidation of the current exported snapshot before another native command')
        if operation == 'drop' and selected['slot'] not in self.owned_slots:
            raise TemporarySlotError('Only a temporary slot acknowledged on this original backend can be dropped')
        if operation == 'logical_stream' and self.owned_slot_kinds.get(selected['slot']) != 'logical':
            raise TemporarySlotError('Select a logical temporary slot acknowledged on this original backend')
        reviewed = {'operation': operation, 'options': selected, 'resource_id': self.resource_id,
                'backend_pid': self.backend_pid, 'source': deepcopy(self.source),
                'snapshot_before': deepcopy(self.snapshot), 'acknowledgement_count': self.acknowledgement_count,
                'used_snapshot_before': deepcopy(getattr(self, 'used_snapshot', None)),
                'adapter_sha256': self.adapter_sha256, 'slot_catalog_observed': False}
        if operation == 'snapshot_copy':
            source = self.copy_sources.get(selected['relation_oid'])
            if source is None:
                raise TemporarySlotError('Inspect the selected relation on this original snapshot before reviewing its COPY')
            reviewed['copy_source'] = {**deepcopy(source), 'include_descendants': selected['include_descendants'],
                                       'copy_format': selected['format'], 'copy_options': deepcopy(selected['copy_options'])}
            reviewed['copy_source']['used_snapshot'] = deepcopy(self.used_snapshot)
        return reviewed

    def command(self, reviewed, acknowledge, *, dispatching=None, finished=None):
        from psycopg import ClientCursor, Error as NativeError
        from psycopg.rows import tuple_row
        if self.review(reviewed['operation'], reviewed['options']) != reviewed:
            raise TemporarySlotError('The retained replication command or snapshot changed after review')
        selected, operation = reviewed['options'], reviewed['operation']
        native_attempted = False
        close_required = False
        def record(result):
            self.acknowledgements.append(deepcopy(result))
            self.acknowledgement_count += 1
            if operation == 'snapshot_end':
                self.owns_snapshot_transaction = False
                self.used_snapshot = None
                self.copy_sources.clear()
            elif operation == 'drop':
                self.owned_slots.remove(selected['slot'])
                self.owned_slot_kinds.pop(selected['slot'], None)
            elif operation.endswith('_create'):
                self.owned_slots.add(selected['slot'])
                self.owned_slot_kinds[selected['slot']] = operation.removesuffix('_create')
            acknowledge(result)
        try:
            if operation == 'snapshot_copy':
                def copy_starting():
                    nonlocal native_attempted
                    if dispatching is not None:
                        dispatching()
                    native_attempted = True
                def copy_acknowledged(capture):
                    nonlocal result
                    result = {'resource_id': self.resource_id, 'backend_pid': self.backend_pid,
                              'operation': operation, 'temporary': True, 'native_command_returned': True,
                              'capture': capture, 'snapshot': None,
                              'used_snapshot': deepcopy(self.used_snapshot), 'slot_catalog_observed': False}
                    record(result)
                artifact = self.snapshot_copy_capture(self.connection, reviewed['copy_source'], selected,
                                                     copy_acknowledged, copy_starting)
                return {'acknowledgement': result, 'snapshot_copy_artifact': artifact,
                        'owned_temporary_slots': self.inventory()}
            if operation == 'logical_stream':
                def stream_starting():
                    nonlocal native_attempted
                    if dispatching is not None:
                        dispatching()
                    self.snapshot = None
                    native_attempted = True
                def stream_acknowledged(capture):
                    nonlocal result
                    result = {'resource_id': self.resource_id, 'backend_pid': self.backend_pid,
                              'slot': selected['slot'], 'operation': operation, 'temporary': True,
                              'native_command_returned': True, 'capture': capture,
                              'snapshot': None, 'slot_catalog_observed': False}
                    record(result)
                artifact = self.stream_capture(self.connection, selected, stream_acknowledged, stream_starting)
                return {'acknowledgement': result, 'protocol_stream_artifact': artifact,
                        'owned_temporary_slots': self.inventory()}
            with ClientCursor(self.connection, row_factory=tuple_row) as cursor:
                if dispatching is not None:
                    dispatching()
                # A new command invalidates a prior export even if that command
                # later fails. Fence the local claim before possible dispatch.
                self.snapshot = None
                native_attempted = True
                phases = []
                if operation == 'logical_create' and selected['snapshot'] == 'use':
                    cursor.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
                    self.owns_snapshot_transaction = True
                    self.require_idle()
                    phases.append({'phase': 'snapshot_transaction_begin', 'native_command_returned': True,
                                   'isolation': 'repeatable read', 'read_only': True})
                    phase_acknowledge = getattr(self, 'phase_acknowledge', None)
                    if phase_acknowledge is not None:
                        phase_acknowledge(deepcopy(phases))
                    if dispatching is not None:
                        dispatching()
                if operation == 'snapshot_tables':
                    from .replication_snapshot_copy import catalog
                    row = catalog(cursor, selected)
                elif operation == 'snapshot_inspect':
                    from .replication_snapshot_copy import relation
                    row = relation(self.connection, selected)
                    self.copy_sources[selected['relation_oid']] = deepcopy(row)
                    self.copy_sources.move_to_end(selected['relation_oid'])
                    while len(self.copy_sources) > 100:
                        self.copy_sources.popitem(last=False)
                else:
                    cursor.execute(statement(operation, selected))
                    row = tuple(map(_text, cursor.fetchone())) if cursor.description else None
                if operation.endswith('_create'):
                    if row is None or len(row) != 4 or row[0] != selected['slot'] or not isinstance(row[1], str) or not re.fullmatch(r'[0-9A-F]+/[0-9A-F]+', row[1]):
                        raise TemporarySlotError('The native temporary slot response is unconfirmed; do not replay')
                    if (operation == 'physical_create' and (row[2] is not None or row[3] is not None) or
                            operation == 'logical_create' and (row[3] != selected['plugin'] or
                            (row[2] is not None) != (selected['snapshot'] == 'export'))):
                        raise TemporarySlotError('The native temporary slot kind, plugin or snapshot response is unconfirmed')
                    if row[2] is not None:
                        if not isinstance(row[2], str) or not re.fullmatch(r'[0-9A-Fa-f-]+', row[2]):
                            raise TemporarySlotError('The native exported snapshot response is unconfirmed')
                        self.snapshot = {'snapshot_name': row[2], 'consistent_point': row[1],
                                         'slot': row[0], 'owner_connection_required': True,
                                         'catalog_liveness_observed': False}
                    if operation == 'logical_create' and selected['snapshot'] == 'use':
                        self.used_snapshot = {'consistent_point': row[1], 'slot': row[0],
                                              'owner_connection_required': True, 'read_only': True,
                                              'isolation': 'repeatable read', 'native_snapshot_installed': True}
                if operation == 'snapshot_end':
                    from psycopg.pq import TransactionStatus
                    if self.connection.info.transaction_status != TransactionStatus.IDLE:
                        raise TemporarySlotError('The native snapshot transaction end is unconfirmed; do not replay')
                result = {'resource_id': self.resource_id, 'backend_pid': self.backend_pid,
                          'slot': selected.get('slot'), 'operation': operation, 'temporary': True,
                          'native_command_returned': True, 'native_result': row,
                          'snapshot': deepcopy(self.snapshot), 'slot_catalog_observed': False,
                          'used_snapshot': None if operation == 'snapshot_end' else deepcopy(getattr(self, 'used_snapshot', None)),
                          'native_phases': phases}
                record(result)
        except NativeError as error:
            close_required = native_attempted
            primary = error.diag.message_primary
            reason = (primary[:8192] if error.sqlstate and isinstance(primary, str) else
                      'Native replication outcome is unconfirmed; do not replay')
            reported = TemporarySlotError(reason)
            reported.sqlstate = error.sqlstate
            raise reported from None
        except BaseException:
            # A native error may remove every temporary slot on this backend.
            # Cached acknowledgements cannot establish current ownership after
            # that event. End this owner instead of dropping a reused name or
            # reconnecting/recreating anything from its old history.
            close_required = native_attempted
            raise
        finally:
            try:
                if finished is not None:
                    finished()
            finally:
                # Join the observer before requiring owner closure. Native ERR
                # is a known command boundary; a close policy must not masquerade
                # as cancellation cleanup failure and erase its SQLSTATE.
                if close_required:
                    self.usable = False
        return {'acknowledgement': result, 'owned_temporary_slots': self.inventory()}

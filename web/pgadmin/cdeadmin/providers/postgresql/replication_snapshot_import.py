"""Import an acknowledged export on a new, independently owned connection."""
from copy import deepcopy
import re
import uuid

from .temporary_slots import TemporarySlotError

IDENTITY_KEYS = ('system_identifier', 'timeline', 'server_version',
                 'authenticated_principal', 'database', 'database_target_id',
                 'admission_interface')


def reference(value):
    """Validate a server-derived reference, never an arbitrary snapshot name."""
    try:
        if not isinstance(value, dict) or set(value) != {
                'exporter_job_id', 'exporter_resource_id', 'exporter_backend_pid',
                'source', 'snapshot'}:
            raise ValueError
        for key in ('exporter_job_id', 'exporter_resource_id'):
            if not isinstance(value[key], str) or str(uuid.UUID(value[key])) != value[key]:
                raise ValueError
        pid = value['exporter_backend_pid']
        if not isinstance(pid, str) or not re.fullmatch(r'[1-9][0-9]{0,9}', pid) or int(pid) > 2147483647:
            raise ValueError
        snapshot = value['snapshot']
        if not isinstance(snapshot, dict) or set(snapshot) != {'snapshot_name', 'consistent_point', 'slot'}:
            raise ValueError
        if not isinstance(snapshot['snapshot_name'], str) or not re.fullmatch(r'[0-9A-F-]{1,128}', snapshot['snapshot_name']):
            raise ValueError
        if not isinstance(snapshot['consistent_point'], str) or not re.fullmatch(r'[0-9A-F]{1,8}/[0-9A-F]{1,8}', snapshot['consistent_point']):
            raise ValueError
        from .temporary_slots import name
        name(snapshot['slot'])
        if not isinstance(value['source'], dict) or not all(key in value['source'] for key in IDENTITY_KEYS):
            raise ValueError
    except (ValueError, TypeError, AttributeError, KeyError):
        raise TemporarySlotError('Select a server-derived original exported-snapshot reference') from None
    return deepcopy(value)


def install(native, selected, acknowledge, dispatching):
    """BEGIN/import ACKs survive failed verification or local publication."""
    from psycopg import ClientCursor, Error as NativeError
    from psycopg.rows import tuple_row
    selected = reference(selected)
    native.require_idle()
    if any(native.source.get(key) != selected['source'][key] for key in IDENTITY_KEYS):
        raise TemporarySlotError('The snapshot consumer reached another native source identity')
    if native.snapshot is not None or native.owned_slots or native.owns_snapshot_transaction:
        raise TemporarySlotError('Snapshot import requires a new independent replication resource')
    query = """SELECT datname, usename, application_name,
                      extract(epoch FROM backend_start)::pg_catalog.text, backend_type
                 FROM pg_catalog.pg_stat_activity WHERE pid=%s::pg_catalog.int4"""
    expected = (selected['source']['database'], selected['source']['authenticated_principal'],
                'ScratchRobin repl temp ' + selected['exporter_job_id'])

    def observe(cursor):
        dispatching()
        cursor.execute(query, (int(selected['exporter_backend_pid']),))
        row = cursor.fetchone()
        if row is not None:
            row = tuple(value.decode('utf8') if isinstance(value, bytes) else value for value in row)
        if (row is None or len(row) != 5 or row[:3] != expected or row[4] != 'walsender' or
                not isinstance(row[3], str) or not re.fullmatch(r'[0-9]+\.[0-9]+', row[3])):
            raise TemporarySlotError('The original snapshot exporter backend identity is unavailable or changed')
        return row

    try:
        with ClientCursor(native.connection, row_factory=tuple_row) as cursor:
            before = observe(cursor)
            acknowledge({'snapshot_exporter_preverified': True,
                         'snapshot_exporter_backend_started_epoch': before[3]})
            dispatching()
            cursor.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
            native.owns_snapshot_transaction = True
            native.require_idle()
            acknowledge({'snapshot_transaction_begin_acknowledged': True,
                         'snapshot_transaction_isolation': 'repeatable read',
                         'snapshot_transaction_read_only': True})
            dispatching()
            # This must be the first command after BEGIN. ClientCursor binds a
            # literal using the connection's exact native encoding/escaping.
            cursor.execute('SET TRANSACTION SNAPSHOT %s', (selected['snapshot']['snapshot_name'],))
            acknowledge({'snapshot_import_acknowledged': True,
                         'imported_snapshot_reference': selected})
            after = observe(cursor)
            if after != before:
                raise TemporarySlotError('The original snapshot exporter changed during native import')
            native.require_idle()
            native.used_snapshot = {
                'origin': 'imported-exported-snapshot',
                'snapshot_name': selected['snapshot']['snapshot_name'],
                'consistent_point': selected['snapshot']['consistent_point'],
                'source_slot': selected['snapshot']['slot'],
                'exporter_job_id': selected['exporter_job_id'],
                'exporter_resource_id': selected['exporter_resource_id'],
                'exporter_backend_pid': selected['exporter_backend_pid'],
                'exporter_backend_started_epoch': before[3],
                'exporter_connection_required_after_import': False,
                'consumer_connection_required': True,
                'read_only': True, 'isolation': 'repeatable read',
                'native_snapshot_installed': True,
            }
            acknowledge({'snapshot_exporter_postverified': True,
                         'snapshot_import_verified': True})
    except NativeError as error:
        native.usable = False
        primary = error.diag.message_primary
        result = TemporarySlotError(primary[:8192] if error.sqlstate and isinstance(primary, str)
                                    else 'Native snapshot import outcome is unconfirmed; do not replay')
        result.sqlstate = error.sqlstate
        raise result from None
    except BaseException:
        native.usable = False
        raise

"""An original replication connection behind durable temporary-slot requests."""
import hashlib
from pathlib import Path
import socket
import sys
import threading
import time

from ..providers.postgresql.replication_temporary_slots import (
    ReplicationTemporarySlots, TemporarySlotError, options,
)
from .postgresql_temporary_slot_jobs import TemporarySlotCommands, TemporarySlotResources


def program():
    from ..providers.postgresql import replication_admission, replication_temporary_slots, replication_stream_options, replication_snapshot_copy, replication_snapshot_import
    from . import postgresql_temporary_slot_jobs, postgresql_replication_stream, postgresql_snapshot_copy
    return {'kind': 'native-postgresql-replication-temporary-slot-resource',
            'adapter_sha256': hashlib.sha256(Path(replication_temporary_slots.__file__).read_bytes()).hexdigest(),
            'channel_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'service_sha256': hashlib.sha256(Path(__file__).with_name('postgresql_replication_temporary_service.py').read_bytes()).hexdigest(),
            'request_owner_sha256': hashlib.sha256(Path(postgresql_temporary_slot_jobs.__file__).read_bytes()).hexdigest(),
            'admission_sha256': hashlib.sha256(Path(replication_admission.__file__).read_bytes()).hexdigest(),
            'stream_options_sha256': hashlib.sha256(Path(replication_stream_options.__file__).read_bytes()).hexdigest(),
            'stream_capture_sha256': hashlib.sha256(Path(postgresql_replication_stream.__file__).read_bytes()).hexdigest(),
            'snapshot_options_sha256': hashlib.sha256(Path(replication_snapshot_copy.__file__).read_bytes()).hexdigest(),
            'snapshot_copy_sha256': hashlib.sha256(Path(postgresql_snapshot_copy.__file__).read_bytes()).hexdigest(),
            'snapshot_import_sha256': hashlib.sha256(Path(replication_snapshot_import.__file__).read_bytes()).hexdigest(),
            'execution_host': {'kind': 'application-host', 'hostname': socket.gethostname(), 'platform': sys.platform}}


class ReplicationTemporaryCommands(TemporarySlotCommands):
    operation = 'postgresql_replication_temporary_slot_command'
    review_warnings = (
        'Dispatch one command on this original native replication backend. A native error can remove all its temporary slots.',
        'A new command invalidates its earlier exported snapshot. Review and local status send no native command. Explicit snapshot relation inspection reads the owned USE transaction catalog before COPY review.',
        'Native acknowledgement is distinct from current slot/snapshot liveness. Unknown commands never replay.',
        'Logical streaming captures native frames on this backend. Optional flush feedback advances only to fsynced data-start positions; it can consume slot output. No application apply position is reported.',
        'SNAPSHOT USE starts an owned read-only repeatable-read transaction, then creates its slot as the first command. Native BEGIN and slot acknowledgement remain separate. End that transaction explicitly before replication streaming.',
        'Snapshot COPY uses the native SELECT permission and row-security scope. Native metadata and a locked relation identity bind its native binary/text/CSV artifact. Views, foreign sources and concurrent DDL retain their native snapshot limitations.',
    )


class ReplicationTemporaryResources(TemporarySlotResources):
    operation = 'postgresql_replication_temporary_slot_resource'
    review_warnings = (
        'Retain one native database replication connection. Temporary slots disappear on its termination or a native error; an old backend is never reconnected.',
        'An exported snapshot requires this original connection and expires on its next native command. Local status, review and acknowledgement pages send no native command. Explicit snapshot relation inspection reads the owned USE transaction catalog.',
        'Acknowledgements are not a SQL slot catalog or a current health check. Closing the viewer does not release this resource. WAL retention can consume server storage.',
        'Native command acknowledgement, local connection close and independently observed backend cleanup remain separate facts. Lost commands never replay.',
        'An independent snapshot consumer imports the original acknowledged export using its own connection and transport. Native BEGIN, import and exporter verification have separate receipts. After verified import it can keep copying after exporter release; it does not own or stream the source slot.',
    )

    def snapshot_reference(self, job_id, owner, endpoint, source, expected_program):
        from ..providers.postgresql.replication_snapshot_import import reference
        current = self.load(job_id, owner, endpoint)
        self.require_open(current)
        if current['program'] != expected_program or current['source'] != source:
            raise TemporarySlotError('The snapshot exporter belongs to another native source, provider scope or adapter')
        snapshot = (current.get('latest_native_inventory') or {}).get('snapshot')
        if not snapshot:
            raise TemporarySlotError('The original backend has no acknowledged current exported snapshot')
        return reference({'exporter_job_id': current['job_id'],
                          'exporter_resource_id': current.get('native_resource_id'),
                          'exporter_backend_pid': current.get('backend_pid'),
                          'source': current['source'],
                          'snapshot': {key: snapshot.get(key) for key in ('snapshot_name', 'consistent_point', 'slot')}})

    def queue_review(self, job_id, owner, endpoint, operation, value):
        return self.queue_request(job_id, owner, endpoint, 'review', operation, options(operation, value))

    def commands(self, record):
        commands = ReplicationTemporaryCommands(str(self.path) + '.commands.' + record['job_id'],
            self.directory(record) / 'commands')
        commands.resource_jobs = self
        commands.resource_id = record['job_id']
        return commands

    def process(self, record, native, cancel, expired=lambda: False):
        current = self.load(record['job_id'], record['owner'], record['endpoint_id'])
        pending = current.get('pending_command')
        if not pending:
            return False
        commands = self.commands(current)
        child = commands.load(pending['job_id'], record['owner'], record['endpoint_id'])
        if pending['kind'] != 'execute':
            return super().process(record, native, cancel, expired)
        native.phase_acknowledge = lambda phases: commands.update(child, native_phase_acknowledgements=phases)
        if child['options']['operation'] == 'snapshot_copy':
            from . import postgresql_snapshot_copy
            def snapshot_capture(connection, source, selected, acknowledge, dispatching):
                artifact = postgresql_snapshot_copy.capture(connection, commands.directory(child), source, selected,
                    acknowledge=acknowledge, progress=lambda value: commands.update(child, progress=value),
                    dispatching=dispatching)
                commands.update(child, snapshot_copy_artifact=artifact)
                return artifact
            native.snapshot_copy_capture = snapshot_capture
            try:
                return super().process(record, native, cancel, expired)
            finally:
                del native.snapshot_copy_capture
                del native.phase_acknowledge
        if child['options']['operation'] != 'logical_stream':
            try:
                return super().process(record, native, cancel, expired)
            finally:
                del native.phase_acknowledge
        from . import postgresql_replication_stream
        def capture(connection, selected, acknowledge, dispatching):
            artifact = postgresql_replication_stream.capture(connection, commands.directory(child), selected,
                acknowledge=acknowledge, progress=lambda value: commands.update(child, progress=value),
                dispatching=dispatching)
            commands.update(child, protocol_stream_artifact=artifact)
            return artifact
        native.stream_capture = capture
        try:
            return super().process(record, native, cancel, expired)
        finally:
            del native.stream_capture
            del native.phase_acknowledge


class ReplicationTemporaryTransport:
    def __init__(self, transport):
        self.transport = transport

    def close(self):
        self.transport.close()

    def execute(self, record, jobs, cancel):
        import psycopg
        connection = None
        closed = False
        opened = time.monotonic()
        last_observed = 0
        lifetime = record['options']['max_lifetime_seconds']
        try:
            with self.transport.parameters() as parameters:
                if cancel.is_set():
                    raise TemporarySlotError('The replication resource was cancelled before attachment')
                if program() != record['program']:
                    raise TemporarySlotError('The temporary replication owner changed before attachment')
                connection = psycopg.connect(**{**parameters, 'replication': 'database', 'autocommit': True,
                    'connect_timeout': 5, 'client_encoding': 'UTF8',
                    'application_name': 'ScratchRobin repl temp ' + record['job_id']})
                native = ReplicationTemporarySlots(connection, record['source'])
                jobs.update(record, native_resource_open_returned=True, native_resource_id=native.resource_id,
                    backend_pid=native.backend_pid, backend_started_epoch=None, source_role_identity=native.source,
                    native_adapter_sha256=native.adapter_sha256, ready=False, owner_heartbeat_at=time.time(),
                    sql_admission_performed=False, slot_catalog_observed=False)
                try:
                    selected = record['options'].get('snapshot_import')
                    if selected is not None:
                        # Recheck local ownership after the new connection is
                        # open, without touching the original native socket.
                        if jobs.snapshot_reference(selected['exporter_job_id'], record['owner'], record['endpoint_id'],
                                                   record['source'], record['program']) != selected:
                            raise TemporarySlotError('The original exported snapshot changed before consumer import')
                        done = threading.Event()
                        observer_failed = threading.Event()
                        def stopped():
                            return cancel.is_set() or lifetime is not None and time.monotonic() - opened >= lifetime
                        def dispatching():
                            if stopped() or observer_failed.is_set():
                                raise TemporarySlotError('Snapshot consumer opening stopped before native dispatch')
                        def observe():
                            while not done.wait(.1):
                                try:
                                    if stopped():
                                        connection.cancel_safe(timeout=1)
                                        return
                                except BaseException:
                                    observer_failed.set()
                                    try:
                                        connection.cancel_safe(timeout=1)
                                    except BaseException:
                                        pass
                                    return
                        watcher = threading.Thread(target=observe, daemon=True, name='postgresql-snapshot-import-cancel')
                        watcher.start()
                        try:
                            from ..providers.postgresql.replication_snapshot_import import install
                            install(native, selected, lambda values: jobs.update(record, **values), dispatching)
                            dispatching()
                        finally:
                            done.set()
                            watcher.join(timeout=2)
                        if watcher.is_alive() or observer_failed.is_set():
                            raise TemporarySlotError('Snapshot import cancellation observer cleanup is unconfirmed; do not replay')
                    jobs.update(record, ready=True, latest_native_inventory=native.inventory(),
                                latest_inventory_observed_at=time.time(), owner_heartbeat_at=time.time())
                    while not cancel.is_set():
                        if lifetime is not None and time.monotonic() - opened >= lifetime:
                            jobs.update(record, lifetime_expired=True)
                            break
                        if jobs.process(record, native, cancel,
                                expired=lambda: lifetime is not None and time.monotonic() - opened >= lifetime):
                            jobs.update(record, latest_native_inventory=native.inventory(),
                                latest_inventory_observed_at=time.time(), owner_heartbeat_at=time.time())
                            last_observed = time.monotonic()
                            continue
                        if time.monotonic() - last_observed >= 5:
                            # This is a local acknowledgement read. A native
                            # IDENTIFY/SHOW/catalog heartbeat would invalidate
                            # the exported snapshot we are keeping alive.
                            jobs.update(record, latest_native_inventory=native.inventory(),
                                latest_inventory_observed_at=time.time(), owner_heartbeat_at=time.time())
                            last_observed = time.monotonic()
                        cancel.wait(.1)
                finally:
                    connection.close()
                    closed = True
                    jobs.update(record, native_owner_connection_close_returned=True, ready=False,
                        owner_connection_closed_at=time.time(), remote_cleanup_inferred=False)
        finally:
            if connection is not None and not closed:
                connection.close()
                jobs.update(record, native_owner_connection_close_returned=True, ready=False,
                    owner_connection_closed_at=time.time(), remote_cleanup_inferred=False)
        return {'owner_connection_close_returned': True, 'remote_cleanup_inferred': False,
                'cancel_requested': cancel.is_set(),
                'lifetime_expired': lifetime is not None and time.monotonic() - opened >= lifetime}

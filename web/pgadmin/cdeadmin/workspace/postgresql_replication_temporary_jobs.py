"""An original replication connection behind durable temporary-slot requests."""
import hashlib
from pathlib import Path
import socket
import sys
import time

from ..providers.postgresql.replication_temporary_slots import (
    ReplicationTemporarySlots, TemporarySlotError, options,
)
from .postgresql_temporary_slot_jobs import TemporarySlotCommands, TemporarySlotResources


def program():
    from ..providers.postgresql import replication_admission, replication_temporary_slots
    from . import postgresql_temporary_slot_jobs
    return {'kind': 'native-postgresql-replication-temporary-slot-resource',
            'adapter_sha256': hashlib.sha256(Path(replication_temporary_slots.__file__).read_bytes()).hexdigest(),
            'channel_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'service_sha256': hashlib.sha256(Path(__file__).with_name('postgresql_replication_temporary_service.py').read_bytes()).hexdigest(),
            'request_owner_sha256': hashlib.sha256(Path(postgresql_temporary_slot_jobs.__file__).read_bytes()).hexdigest(),
            'admission_sha256': hashlib.sha256(Path(replication_admission.__file__).read_bytes()).hexdigest(),
            'execution_host': {'kind': 'application-host', 'hostname': socket.gethostname(), 'platform': sys.platform}}


class ReplicationTemporaryCommands(TemporarySlotCommands):
    operation = 'postgresql_replication_temporary_slot_command'
    review_warnings = (
        'Dispatch one command on this original native replication backend. A native error can remove all its temporary slots.',
        'A new command invalidates its earlier exported snapshot. Review and status do not send native commands.',
        'Native acknowledgement is distinct from current slot/snapshot liveness. Unknown commands never replay.',
    )


class ReplicationTemporaryResources(TemporarySlotResources):
    operation = 'postgresql_replication_temporary_slot_resource'
    review_warnings = (
        'Retain one native database replication connection. Temporary slots disappear on its termination or a native error; an old backend is never reconnected.',
        'An exported snapshot requires this original connection and expires on its next native command. Status, review and acknowledgement pages send no native command.',
        'Acknowledgements are not a SQL slot catalog or a current health check. Closing the viewer does not release this resource. WAL retention can consume server storage.',
        'Native command acknowledgement, local connection close and independently observed backend cleanup remain separate facts. Lost commands never replay.',
    )

    def queue_review(self, job_id, owner, endpoint, operation, value):
        return self.queue_request(job_id, owner, endpoint, 'review', operation, options(operation, value))

    def commands(self, record):
        commands = ReplicationTemporaryCommands(str(self.path) + '.commands.' + record['job_id'],
            self.directory(record) / 'commands')
        commands.resource_jobs = self
        commands.resource_id = record['job_id']
        return commands


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
                    native_adapter_sha256=native.adapter_sha256, ready=True, owner_heartbeat_at=time.time(),
                    sql_admission_performed=False, slot_catalog_observed=False)
                try:
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

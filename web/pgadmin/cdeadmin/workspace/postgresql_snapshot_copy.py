"""Private native COPY artifacts from an owned decoding snapshot."""
import base64
from contextlib import contextmanager
import hashlib
import os
import re

from ..operations.fileio import durable_replace, private_file
from ..providers.postgresql.replication_snapshot_copy import lock_and_verify
from ..providers.postgresql.temporary_slots import TemporarySlotError
from .postgresql_slot_changes import regular_file, file_identity, artifact_lock

FILENAME = 'snapshot.copy'
PARTIAL = FILENAME + '.partial'


def commands_running(jobs, record):
    return jobs.observed(record).get('worker_io_closed') is not True


def capture(connection, directory, source, selected, *, acknowledge, progress, dispatching):
    from psycopg import ClientCursor
    from psycopg.pq import TransactionStatus
    from psycopg.rows import tuple_row
    path, destination = directory / PARTIAL, directory / FILENAME
    if destination.exists() or destination.is_symlink():
        raise TemporarySlotError('The original snapshot COPY artifact already exists')
    checksum = hashlib.sha256()
    size = 0
    prefix = b''
    tail = b''
    with path.open('xb') as output:
        private_file(path)
        with ClientCursor(connection, row_factory=tuple_row) as cursor:
            dispatching()
            command = lock_and_verify(cursor, source)
            with cursor.copy(command) as copy:
                for part in copy:
                    data = bytes(part)
                    output.write(data)
                    checksum.update(data)
                    size += len(data)
                    prefix = (prefix + data)[:11]
                    tail = (tail + data)[-2:]
                    progress({'artifact_bytes': str(size), 'format': 'postgresql-native-copy', 'copy_format': source['copy_format']})
            if (source['copy_format'] == 'binary' and (prefix != b'PGCOPY\n\xff\r\n\0' or tail != b'\xff\xff') or cursor.rowcount < 0 or
                    connection.info.transaction_status != TransactionStatus.INTRANS):
                raise TemporarySlotError('Native COPY completion or the owned snapshot is unconfirmed; do not replay')
            observed = {'filename': FILENAME, 'format': 'postgresql-native-copy', 'copy_format': source['copy_format'], 'rows': str(cursor.rowcount),
                        'artifact_bytes': str(size), 'sha256': checksum.hexdigest(), 'source': source,
                        'native_command_returned': True, 'original_snapshot_transaction_retained': True,
                        'complete_database_backup': False, 'slot_flush_checkpoint_advanced': False}
            acknowledge(observed)
        output.flush()
        os.fsync(output.fileno())
    durable_replace(path, destination)
    return {**observed, 'state': 'verified', 'writer_closed': True,
            'file_identity': file_identity(destination.stat())}


@contextmanager
def payload(jobs, record):
    artifact = record.get('snapshot_copy_artifact') or {}
    if (record.get('options', {}).get('operation') != 'snapshot_copy' or record.get('artifact_removed') or
            artifact.get('state') not in {'verified', 'partial'} or not artifact.get('writer_closed') or
            artifact.get('filename') not in {FILENAME, PARTIAL} or
            artifact['state'] == 'verified' and not record.get('native_command_acknowledged')):
        raise TemporarySlotError('Select an inspected stopped original-snapshot COPY artifact')
    with regular_file(jobs.directory(record) / artifact['filename']) as source:
        if file_identity(os.fstat(source.fileno())) != artifact['file_identity']:
            raise TemporarySlotError('The original snapshot COPY bytes changed')
        yield source


def reconcile(jobs, record):
    with artifact_lock(jobs, record) as current:
        if current.get('artifact_removed') or jobs.observed(current).get('worker_io_closed') is not True:
            raise TemporarySlotError('Wait for the original snapshot COPY writer to stop')
        if current.get('options', {}).get('operation') != 'snapshot_copy':
            raise TemporarySlotError('Select an original-snapshot COPY command')
        path = next((jobs.directory(current) / name for name in (FILENAME, PARTIAL)
                     if (jobs.directory(current) / name).exists() or (jobs.directory(current) / name).is_symlink()), None)
        if path is None:
            raise TemporarySlotError('No original snapshot COPY bytes are available')
        checksum = hashlib.sha256()
        size = 0
        prefix = b''
        tail = b''
        with regular_file(path, writable=True) as source:
            before = file_identity(os.fstat(source.fileno()))
            while data := source.read(1048576):
                checksum.update(data)
                size += len(data)
                prefix = (prefix + data)[:11]
                tail = (tail + data)[-2:]
            if before != file_identity(os.fstat(source.fileno())):
                raise TemporarySlotError('Original snapshot COPY bytes changed during inspection')
            os.fsync(source.fileno())
        expected = (current.get('native_acknowledgement') or {}).get('capture') or {}
        complete = (current.get('native_command_acknowledged') is True and
                    expected.get('sha256') == checksum.hexdigest() and expected.get('artifact_bytes') == str(size) and
                    (expected.get('copy_format') in {'text', 'csv'} or
                     expected.get('copy_format') == 'binary' and prefix == b'PGCOPY\n\xff\r\n\0' and tail == b'\xff\xff'))
        if complete and path.name != FILENAME:
            durable_replace(path, jobs.directory(current) / FILENAME)
            path = jobs.directory(current) / FILENAME
        artifact = {**(expected if complete else {}), 'filename': path.name, 'format': 'postgresql-native-copy',
                    'copy_format': current['options']['native_options']['format'],
                    'artifact_bytes': str(size), 'sha256': checksum.hexdigest(), 'writer_closed': True,
                    'state': 'verified' if complete else 'partial', 'native_binary_header': prefix == b'PGCOPY\n\xff\r\n\0',
                    'native_binary_trailer': tail == b'\xff\xff', 'publication_reconciled': complete,
                    'file_identity': file_identity(path.stat())}
        jobs.update(current, snapshot_copy_artifact=artifact)
    return jobs.public(jobs.observed(jobs.load(current['job_id'], current['owner'], current['endpoint_id'])))


def preview(jobs, record, request):
    offset, length = request.get('offset', '0'), request.get('length', 4096)
    if (not isinstance(offset, str) or not re.fullmatch(r'0|[1-9][0-9]{0,18}', offset) or
            type(length) is not int or not 1 <= length <= 65536):
        raise TemporarySlotError('Select a bounded native COPY byte preview')
    with payload(jobs, record) as source:
        identity = file_identity(os.fstat(source.fileno()))
        start = int(offset)
        if start > identity[2]:
            raise TemporarySlotError('Native COPY preview offset is beyond the artifact')
        source.seek(start)
        data = source.read(length)
        end = source.tell()
        if identity != file_identity(os.fstat(source.fileno())):
            raise TemporarySlotError('Original snapshot COPY bytes changed during preview')
    return {'offset': offset, 'byte_length': str(len(data)), 'data_base64': base64.b64encode(data).decode('ascii'),
            'next_offset': str(end) if end < identity[2] else None,
            'artifact_state': record['snapshot_copy_artifact']['state'], 'source': record['snapshot_copy_artifact'].get('source'),
            'format': 'postgresql-native-copy', 'copy_format': record['snapshot_copy_artifact']['copy_format'], 'native_values_decoded': False}

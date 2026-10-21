"""Exact logical replication frames from an original retained walsender.

Only fsynced XLogData start positions can be offered as flush feedback. Server
WAL-end hints and application apply positions never advance that feedback.
"""
import base64
from contextlib import contextmanager
import hashlib
import json
import os
import re
import select
import struct
import time

from ..operations.fileio import durable_replace, private_file
from ..providers.postgresql.temporary_slots import TemporarySlotError
from .postgresql_slot_changes import regular_file, file_identity, artifact_lock

FILENAME = 'replication-frames.jsonl'
PARTIAL = FILENAME + '.partial'


from ..providers.postgresql.replication_stream_options import options, statement


def _lsn(value):
    return f'{value >> 32:X}/{value & 0xffffffff:X}'


def capture(connection, directory, selected, *, acknowledge, progress, dispatching):
    """Return only after both native CommandComplete responses and ReadyForQuery.

    One native COPY frame and its encoded record can be buffered at a time.
    A local capture bound is not a transaction boundary or a complete WAL archive.
    """
    from psycopg import errors
    from psycopg.pq import ExecStatus, TransactionStatus
    pg = connection.pgconn
    if not pg.nonblocking:
        raise TemporarySlotError('Logical capture requires the native nonblocking libpq connection')
    path, destination = directory / PARTIAL, directory / FILENAME
    if destination.exists() or destination.is_symlink():
        raise TemporarySlotError('The original logical stream artifact already exists')
    command = statement(selected).as_bytes(connection)
    checksum = hashlib.sha256()
    messages = size = keepalives = discarded = 0
    durable_lsn = 0
    feedback_lsn = 0
    started = last_feedback = time.monotonic()

    def readable():
        select.select([pg.socket], [], [], .1)
        pg.consume_input()

    def flush():
        while pg.flush():
            select.select([], [pg.socket], [], .1)

    def feedback():
        nonlocal last_feedback, feedback_lsn
        position = durable_lsn if selected['acknowledge_flush'] else 0
        payload = b'r' + struct.pack('!QQQqB', position, position, 0,
            int((time.time() - 946684800) * 1000000), 0)
        while not pg.put_copy_data(payload):
            flush()
        flush()
        feedback_lsn = position
        last_feedback = time.monotonic()

    def result():
        while pg.is_busy():
            readable()
        value = pg.get_result()
        if value is not None and value.status == ExecStatus.FATAL_ERROR:
            raise errors.error_from_result(value, encoding=connection.info.encoding)
        return value

    with path.open('xb') as output, connection.lock:
        private_file(path)
        dispatching()
        pg.send_query(command)
        flush()
        first = result()
        if first is None or first.status != ExecStatus.COPY_BOTH:
            raise TemporarySlotError('Native logical replication did not enter COPY BOTH; do not replay')
        reason = None
        server_final = None
        server_ended = False
        while reason is None:
            elapsed = time.monotonic() - started
            if selected['max_duration_seconds'] is not None and elapsed >= selected['max_duration_seconds']:
                reason = 'duration_bound'
                break
            length, data = pg.get_copy_data(1)
            if length == 0:
                if time.monotonic() - last_feedback >= 1:
                    feedback()
                readable()
                continue
            if length < 0:
                # Obtain a decoded native ERR when available, preserving SQLSTATE.
                server_final = result()
                if length < -1 or server_final is None:
                    raise TemporarySlotError('The native logical stream end is unconfirmed; do not replay')
                server_ended = True
                reason = 'native_stream_end'
                break
            data = bytes(data)
            if data[:1] == b'k' and len(data) == 18 and data[-1] in (0, 1):
                keepalives += 1
                if data[-1] or time.monotonic() - last_feedback >= 1:
                    feedback()
                continue
            if data[:1] != b'w' or len(data) < 25:
                raise TemporarySlotError('Unrecognized native logical replication frame; do not replay')
            position, wal_end, sent_at = struct.unpack('!QQq', data[1:25])
            record = {'start_lsn': _lsn(position), 'server_wal_end': _lsn(wal_end),
                      'server_time_microseconds': str(sent_at),
                      'wire_base64': base64.b64encode(data).decode('ascii')}
            encoded = (json.dumps(record, separators=(',', ':')) + '\n').encode('utf8')
            if selected['max_capture_bytes'] is not None and size + len(encoded) > selected['max_capture_bytes']:
                discarded += 1
                reason = 'byte_bound_before_frame'
                break
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
            checksum.update(encoded)
            size += len(encoded)
            messages += 1
            durable_lsn = max(durable_lsn, position)
            feedback()
            progress({'messages': str(messages), 'artifact_bytes': str(size),
                      'last_durable_data_start_lsn': _lsn(durable_lsn),
                      'last_sent_flush_lsn': _lsn(feedback_lsn), 'application_apply_lsn': '0/0'})
            if selected['max_messages'] is not None and messages >= selected['max_messages']:
                reason = 'message_bound'
        # CopyDone changes the libpq state. Consume its COPY_OUT transition
        # before draining the remaining server frames; send no later feedback.
        if not server_ended:
            feedback()
        if not server_ended or server_final.status == ExecStatus.COPY_IN:
            while not pg.put_copy_end(None):
                flush()
            flush()
            server_final = None
        completions = 0
        while True:
            value = server_final if server_final is not None else result()
            server_final = None
            if value is None:
                break
            if value.status == ExecStatus.COPY_OUT:
                while True:
                    length, data = pg.get_copy_data(1)
                    if length == 0:
                        readable()
                        continue
                    if length == -1:
                        break
                    if length < -1:
                        final = result()
                        raise TemporarySlotError('Native logical stream drain failed; do not replay')
                    discarded += 1
            elif value.status == ExecStatus.COMMAND_OK:
                completions += 1
            else:
                raise TemporarySlotError('Unexpected native logical stream final response; do not replay')
        if completions != 2 or connection.info.transaction_status != TransactionStatus.IDLE:
            raise TemporarySlotError('Both native logical stream command completions are unconfirmed; do not replay')
        observed = {'filename': FILENAME, 'messages': str(messages), 'artifact_bytes': str(size),
                    'sha256': checksum.hexdigest(), 'stop_reason': reason,
                    'keepalives_received': str(keepalives), 'trailing_frames_not_captured': str(discarded),
                    'last_durable_data_start_lsn': _lsn(durable_lsn),
                    'last_sent_flush_lsn': _lsn(feedback_lsn), 'application_apply_lsn': '0/0',
                    'server_flush_checkpoint_observed': False, 'complete_transaction_boundary': False,
                    'native_command_completions': completions, 'wire_format': 'base64-XLogData-frame',
                    'client_buffering': 'one native COPY frame and its encoded artifact record'}
        acknowledge(observed)
        output.flush()
        os.fsync(output.fileno())
    durable_replace(path, destination)
    return {**observed, 'state': 'verified', 'writer_closed': True,
            'file_identity': file_identity(destination.stat())}


@contextmanager
def payload(jobs, record):
    artifact = record.get('protocol_stream_artifact') or {}
    if (record.get('options', {}).get('operation') != 'logical_stream' or record.get('artifact_removed') or
            artifact.get('state') not in {'verified', 'partial'} or
            artifact.get('filename') not in {FILENAME, PARTIAL} or not artifact.get('writer_closed') or
            artifact['state'] == 'verified' and not record.get('native_command_acknowledged')):
        raise TemporarySlotError('Select an inspected stopped native replication capture')
    with regular_file(jobs.directory(record) / artifact['filename']) as source:
        if file_identity(os.fstat(source.fileno())) != artifact['file_identity']:
            raise TemporarySlotError('The captured native replication bytes changed')
        yield source


def reconcile(jobs, record):
    with artifact_lock(jobs, record) as current:
        if current.get('artifact_removed') or commands_running(jobs, current):
            raise TemporarySlotError('Wait for the original replication artifact writer to stop')
        path = next((jobs.directory(current) / name for name in (FILENAME, PARTIAL)
                     if (jobs.directory(current) / name).exists() or (jobs.directory(current) / name).is_symlink()), None)
        if path is None:
            raise TemporarySlotError('No captured original replication bytes are available')
        checksum = hashlib.sha256()
        size = lines = 0
        last = b''
        with regular_file(path, writable=True) as source:
            before = file_identity(os.fstat(source.fileno()))
            while data := source.read(1048576):
                checksum.update(data)
                size += len(data)
                lines += data.count(b'\n')
                last = data[-1:]
            if before != file_identity(os.fstat(source.fileno())):
                raise TemporarySlotError('Native replication bytes changed during inspection')
            os.fsync(source.fileno())
        expected = (current.get('native_acknowledgement') or {}).get('capture') or {}
        complete = (current.get('native_command_acknowledged') is True and expected.get('messages') == str(lines) and
                    expected.get('sha256') == checksum.hexdigest() and expected.get('artifact_bytes') == str(size) and
                    last in (b'', b'\n'))
        if complete and path.name != FILENAME:
            durable_replace(path, jobs.directory(current) / FILENAME)
            path = jobs.directory(current) / FILENAME
        artifact = {**(expected if complete else {}), 'filename': path.name, 'artifact_bytes': str(size),
                    'messages': str(lines), 'sha256': checksum.hexdigest(), 'writer_closed': True,
                    'state': 'verified' if complete else 'partial', 'incomplete_tail': last not in (b'', b'\n'),
                    'file_identity': file_identity(path.stat()), 'publication_reconciled': complete}
        jobs.update(current, protocol_stream_artifact=artifact)
    return jobs.public(jobs.observed(jobs.load(current['job_id'], current['owner'], current['endpoint_id'])))


def commands_running(jobs, record):
    return jobs.observed(record).get('worker_io_closed') is not True


def preview(jobs, record, request):
    offset, limit = request.get('offset', '0'), request.get('limit', 25)
    if (not isinstance(offset, str) or not re.fullmatch(r'0|[1-9][0-9]{0,18}', offset) or
            type(limit) is not int or not 1 <= limit <= 50):
        raise TemporarySlotError('Select a bounded replication frame preview')
    rows = []
    with payload(jobs, record) as source:
        identity = file_identity(os.fstat(source.fileno()))
        start = int(offset)
        if start > identity[2]:
            raise TemporarySlotError('Replication preview offset is beyond the owned artifact')
        if start:
            source.seek(start - 1)
            if source.read(1) != b'\n':
                raise TemporarySlotError('Replication preview requires a complete record boundary')
        for _ in range(limit):
            beginning = source.tell()
            line = source.readline(1048577)
            if not line:
                break
            if len(line) > 1048576 or not line.endswith(b'\n'):
                while line and not line.endswith(b'\n'):
                    line = source.readline(65536)
                rows.append({'record_offset': str(beginning), 'message': 'Large or incomplete frame; download the exact owned bytes'})
                continue
            row = json.loads(line)
            wire = base64.b64decode(row.pop('wire_base64'), validate=True)
            row.update(wire_bytes=str(len(wire)), payload_base64=base64.b64encode(wire[25:25 + 3072]).decode('ascii'),
                       payload_preview_truncated=len(wire) > 25 + 3072)
            rows.append(row)
        end = source.tell()
        if identity != file_identity(os.fstat(source.fileno())):
            raise TemporarySlotError('Native replication artifact changed during preview')
    return {'rows': rows, 'offset': offset, 'next_offset': str(end) if end < identity[2] else None,
            'artifact_state': record['protocol_stream_artifact']['state'],
            'native_command_acknowledged': record.get('native_command_acknowledged') is True}

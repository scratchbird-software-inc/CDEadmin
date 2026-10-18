"""Bounded client streaming of native logical decoding into private artifacts."""
from contextlib import contextmanager
import hashlib
import json
import os
import re
import stat
import time

from ..operations.fileio import durable_replace, private_file
from ..providers.postgresql import large_object_files as private_sql
from ..providers.postgresql.continuity import ContinuityError

OPERATIONS = {'wal_slot_sql_peek_text', 'wal_slot_sql_get_text',
              'wal_slot_sql_peek_binary', 'wal_slot_sql_get_binary'}
FILENAME = 'slot-changes.jsonl'
PARTIAL = FILENAME + '.partial'


def options(value):
    fields = {'slot', 'timeout_seconds', 'upto_lsn', 'upto_nchanges', 'plugin_options'}
    if set(value) - fields: raise ContinuityError('Invalid native logical change options')
    from .postgresql_continuity_slot_sql import options as slot_options
    selected = slot_options('wal_slot_sql_drop', {key: value[key] for key in ('slot', 'timeout_seconds') if key in value})
    lsn = value.get('upto_lsn')
    if lsn not in (None, ''):
        if not isinstance(lsn, str) or re.fullmatch(r'[0-9A-Fa-f]{1,8}/[0-9A-Fa-f]{1,8}', lsn) is None:
            raise ContinuityError('Select a native logical decoding WAL position')
        lsn = lsn.upper()
    selected['upto_lsn'] = lsn or None
    count = value.get('upto_nchanges', 100)
    if count is not None and (type(count) is not int or not -2147483648 <= count <= 2147483647):
        raise ContinuityError('Native change threshold requires an int32 value or no limit')
    selected['upto_nchanges'] = count
    pairs = value.get('plugin_options', [])
    if not isinstance(pairs, list) or len(pairs) > 128:
        raise ContinuityError('Select a bounded native output plugin option list')
    selected['plugin_options'] = []
    for pair in pairs:
        if (not isinstance(pair, dict) or set(pair) != {'name', 'value'} or
                not isinstance(pair['name'], str) or not pair['name'] or '\x00' in pair['name'] or
                not isinstance(pair['value'], str) or '\x00' in pair['value'] or
                len(pair['name']) > 1024 or len(pair['value']) > 1048576):
            raise ContinuityError('Native output plugin options require exact name/value strings')
        try:
            pair['name'].encode('utf8'); pair['value'].encode('utf8')
        except UnicodeError:
            raise ContinuityError('Native output plugin options require valid Unicode strings') from None
        selected['plugin_options'].append(dict(pair))
    return selected


def statement(operation, selected, *, raw_text=False):
    if operation not in OPERATIONS: raise ContinuityError('Native logical change operation is unavailable')
    binary = operation.endswith('_binary')
    function = ('pg_logical_slot_peek_' if '_peek_' in operation else 'pg_logical_slot_get_') + ('binary_changes' if binary else 'changes')
    data = "pg_catalog.encode(data,'base64')" if binary else 'data'
    if raw_text and not binary:
        data = "pg_catalog.encode(pg_catalog.convert_to(data,pg_catalog.current_setting('server_encoding')::pg_catalog.name),'base64')"
    command = ('SELECT lsn::pg_catalog.text,xid::pg_catalog.text,' + data +
               ' FROM pg_catalog.' + function + '(%s::pg_catalog.name,%s::pg_catalog.pg_lsn,%s::pg_catalog.int4,VARIADIC %s::pg_catalog.text[])')
    parameters = (selected['slot'], selected['upto_lsn'], selected['upto_nchanges'],
                  [part for pair in selected['plugin_options'] for part in (pair['name'], pair['value'])])
    return command, parameters


def file_identity(value):
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def stream(connection, directory, operation, selected, *, acknowledge, progress, check_cancel):
    parameter_status = getattr(getattr(connection, 'pgconn', None), 'parameter_status', lambda _name: None)
    server_encoding = private_sql.native_text(parameter_status(b'server_encoding'))
    client_encoding = private_sql.native_text(parameter_status(b'client_encoding'))
    raw_text = 'SQL_ASCII' in (server_encoding, client_encoding)
    command, parameters = statement(operation, selected, raw_text=raw_text)
    checksum = hashlib.sha256(); rows = 0; size = 0
    encoding = 'base64' if operation.endswith('_binary') else 'base64-native-text' if raw_text else 'unicode-text'
    path = directory/PARTIAL; destination = directory/FILENAME
    if destination.exists() or destination.is_symlink():
        raise ContinuityError('Native change artifact already exists')
    # The owning job directory is private. A partial artifact is never offered
    # as complete, and this once-only job never reopens it for an append/retry.
    with path.open('xb') as output:
        private_file(path)
        with private_sql.cursor(connection) as query:
            for lsn, xid, data in query.stream(command, parameters, size=1):
                check_cancel()
                row = {'lsn': private_sql.native_text(lsn), 'xid': private_sql.native_text(xid),
                       'data_encoding': encoding, 'data': private_sql.native_text(data)}
                payload = (json.dumps(row, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode('utf8')
                output.write(payload); checksum.update(payload); size += len(payload); rows += 1
                progress({'rows': str(rows), 'artifact_bytes': str(size)})
        result = {'rows': str(rows), 'artifact_bytes': str(size), 'sha256': checksum.hexdigest(),
                  'filename': FILENAME, 'data_encoding': encoding,
                  'native_server_encoding': server_encoding, 'native_client_encoding': client_encoding,
                  'native_threshold_is_hard_row_limit': False, 'client_buffering': 'one native row and its encoded artifact record'}
        # Exhausting the stream received the native command's final response.
        # Persist that fact before an application artifact flush can fail.
        acknowledge(result)
        output.flush(); os.fsync(output.fileno())
    durable_replace(path, destination)
    return {**result, 'file_identity': file_identity(destination.stat())}


@contextmanager
def regular_file(path, *, writable=False):
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or getattr(before, 'st_file_attributes', 0) & 0x400 or path.resolve() != path):
        raise ContinuityError('Native change artifact is not an owned regular file')
    descriptor = os.open(path, (os.O_RDWR if writable else os.O_RDONLY) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
    with os.fdopen(descriptor, 'r+b' if writable else 'rb') as source:
        if file_identity(os.fstat(source.fileno())) != file_identity(before):
            raise ContinuityError('Native change artifact changed while opening')
        yield source


@contextmanager
def payload(jobs, record):
    artifact = record.get('change_artifact') or {}
    if (record['operation'] not in OPERATIONS or artifact.get('state') not in {'verified', 'partial'} or artifact.get('filename') not in {FILENAME, PARTIAL} or
            artifact['state'] == 'verified' and record.get('native_sql_acknowledged') is not True or
            artifact['state'] == 'partial' and artifact.get('writer_closed') is not True):
        raise ContinuityError('Select a verified artifact or inspected incomplete native change capture')
    path = jobs.directory(record)/artifact['filename']
    with regular_file(path) as source:
        identity = file_identity(os.fstat(source.fileno()))
        if identity != artifact['file_identity']:
            raise ContinuityError('Native change artifact changed after verification')
        yield source


@contextmanager
def artifact_lock(jobs, record):
    """Serialize stopped-file inspection and removal across HTTP workers."""
    from ..operations.fileio import exclusive_file_lock
    path = jobs.directory(record)/'.logical-artifact.lock'
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        private_file(path)
        with exclusive_file_lock(descriptor):
            current = jobs.load(record['job_id'], record['owner'], record['endpoint_id'])
            yield current
    finally:
        os.close(descriptor)


def reconcile(jobs, record):
    with artifact_lock(jobs, record) as current:
        if current.get('artifact_removed'):
            raise ContinuityError('The owned logical capture was removed')
        return _reconcile(jobs, current)


def _reconcile(jobs, record):
    """Inspect owned bytes; only an already recorded native ACK can prove completion."""
    if record['operation'] not in OPERATIONS:
        raise ContinuityError('Select a native logical change job')
    if jobs.observed(record)['state'] not in {'unknown', 'completed', 'not_dispatched', 'cancelled', 'failed'}:
        raise ContinuityError('Wait for the native logical change writer to stop')
    with jobs._worker_maps_lock: worker = jobs.workers.get(record['job_id'])
    if worker is not None and worker[0].is_alive():
        raise ContinuityError('The local native change worker is still stopping')
    directory = jobs.directory(record)
    path = next((directory/name for name in (FILENAME, PARTIAL) if (directory/name).exists() or (directory/name).is_symlink()), None)
    if path is None: raise ContinuityError('No captured native logical change bytes are available')
    checksum = hashlib.sha256(); size = 0; lines = 0; last = b''
    with regular_file(path, writable=True) as source:
        before = file_identity(os.fstat(source.fileno()))
        while data := source.read(1048576):
            checksum.update(data); size += len(data); lines += data.count(b'\n'); last = data[-1:]
        if before != file_identity(os.fstat(source.fileno())):
            raise ContinuityError('Captured native changes changed during inspection')
        os.fsync(source.fileno())
    actual = {'filename': path.name, 'artifact_bytes': str(size), 'sha256': checksum.hexdigest(),
              'complete_record_lines': str(lines), 'incomplete_tail': last not in (b'', b'\n'),
              'writer_closed': True, 'inspected_at': time.time()}
    expected = record.get('native_sql_result') or {}
    complete = (record.get('native_sql_acknowledged') is True and expected.get('sha256') == actual['sha256'] and
                expected.get('artifact_bytes') == actual['artifact_bytes'] and expected.get('rows') == actual['complete_record_lines'] and not actual['incomplete_tail'])
    if complete and path.name != FILENAME:
        durable_replace(path, directory/FILENAME); path = directory/FILENAME
    artifact = {**(expected if complete else {}), **actual, 'filename': path.name,
                'state': 'verified' if complete else 'partial', 'publication_reconciled': complete,
                'file_identity': file_identity(path.stat())}
    jobs.update(record, change_artifact=artifact)
    # No slot query or native redispatch is performed, and no original unknown
    # outcome is promoted by the presence of bytes or the current slot catalog.
    return jobs.get(record['job_id'], record['owner'], record['endpoint_id'])


def preview(jobs, record, request):
    if set(request) - {'job_id', 'offset', 'limit'}: raise ContinuityError('Invalid native change preview')
    offset = request.get('offset', '0'); limit = request.get('limit', 25)
    if (not isinstance(offset, str) or not offset.isascii() or not offset.isdecimal() or len(offset) > 19 or
            offset != str(int(offset)) or type(limit) is not int or not 1 <= limit <= 50):
        raise ContinuityError('Select a bounded native change preview page')
    result = []; start = int(offset)
    with payload(jobs, record) as source:
        identity = file_identity(os.fstat(source.fileno())); length = identity[2]
        if start > length: raise ContinuityError('Native change preview offset is beyond the artifact')
        if start:
            source.seek(start - 1)
            if source.read(1) != b'\n': raise ContinuityError('Native change preview requires a complete record boundary')
        else: source.seek(0)
        for _index in range(limit):
            beginning = source.tell(); line = source.readline(1048577)
            if not line: break
            if len(line) > 1048576 or not line.endswith(b'\n'):
                while line and not line.endswith(b'\n'): line = source.readline(65536)
                result.append({'record_offset': str(beginning), 'record_bytes': str(source.tell() - beginning),
                               'native_values_previewed': False, 'message': 'Large or incomplete record; download the exact captured bytes'})
            else:
                try:
                    row = json.loads(line)
                    if (not isinstance(row, dict) or set(row) != {'lsn', 'xid', 'data_encoding', 'data'} or
                            any(not isinstance(row[key], str) for key in row)):
                        raise ValueError('Unrecognized captured record')
                except (ValueError, UnicodeError):
                    result.append({'record_offset': str(beginning), 'record_bytes': str(source.tell() - beginning),
                                   'native_values_previewed': False, 'message': 'Unparseable captured record; download the exact captured bytes'})
                else:
                    text = row['data']; row['data'] = text[:4096]; row['data_preview_truncated'] = len(text) > 4096
                    result.append(row)
        end = source.tell()
        if identity != file_identity(os.fstat(source.fileno())):
            raise ContinuityError('Native change artifact changed during preview')
    return {'rows': result, 'offset': offset, 'next_offset': str(end) if end < length else None,
            'artifact_state': record['change_artifact']['state'], 'native_sql_acknowledged': record.get('native_sql_acknowledged') is True,
            'preview_data_characters': 4096, 'complete_record_decode_limit_bytes': 1048576}

"""Pull-based, cursor-owned Firebird results; never materialize a BLOB.

Pages replace (not append to) their predecessor. BLOB references expire when
advancing the page. Closing releases resources, never transaction finality.
"""
import base64
import codecs
import copy
import json
import tempfile
import threading
import uuid

from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from .query_values import normalize_value

PAGE_ROWS = 100
PAGE_BYTES = 1024 * 1024
BLOB_BYTES = 64 * 1024
UPLOAD_BYTES = 256 * 1024 * 1024


class UploadBudget:
    """Process-local admission shared across native sessions and providers."""

    def __init__(self, slots=16, byte_limit=1024 * 1024 * 1024):
        self.slots = slots
        self.byte_limit = byte_limit
        self._lock = threading.Lock()
        self._reservations = {}
        self._bytes = 0

    def acquire(self):
        with self._lock:
            if len(self._reservations) >= self.slots:
                raise RelationalClientError(
                    'Firebird process upload slot limit reached; '
                    'close an existing upload before retrying')
            token = object()
            self._reservations[token] = 0
            return token

    def reserve(self, token, size):
        with self._lock:
            if self._bytes + size > self.byte_limit:
                raise RelationalClientError(
                    'Firebird process upload byte limit reached; '
                    'close an existing upload before retrying')
            self._reservations[token] += size
            self._bytes += size

    def release(self, token):
        with self._lock:
            self._bytes -= self._reservations.pop(token, 0)


_UPLOAD_BUDGET = UploadBudget()


class BlobUpload:
    """Session-owned disk spool; client and driver both use bounded chunks."""
    kind = 'blob'

    def __init__(self):
        self.reference = str(uuid.uuid4())
        self._budget = _UPLOAD_BUDGET
        self._reservation = self._budget.acquire()
        try:
            self.file = tempfile.TemporaryFile(mode='w+b')
        except BaseException:
            self._budget.release(self._reservation)
            raise
        self.size = 0
        self.ready = False
        self.failed = False
        self.last = None
        self.closed = False

    def _check_usable(self):
        if self.closed:
            raise RelationalClientError('Upload is closed')
        if self.failed:
            raise RelationalClientError('Failed upload must be closed')

    def append(self, offset, encoded):
        self._check_usable()
        if (type(offset) is not int or not isinstance(encoded, str) or
                len(encoded) > 4 * ((BLOB_BYTES + 2) // 3)):
            raise RelationalClientError('Invalid upload chunk')
        try:
            data = base64.b64decode(encoded, validate=True)
        except ValueError:
            raise RelationalClientError(
                'Invalid base64 upload chunk') from None
        if len(data) > BLOB_BYTES:
            raise RelationalClientError('Upload chunk exceeds the byte budget')
        if self.last == (offset, data):
            return self.size
        if self.ready or offset != self.size or not data:
            raise RelationalClientError('Upload offset is out of sequence')
        if self.size + len(data) > UPLOAD_BYTES:
            raise RelationalClientError('Upload exceeds the 256 MiB limit')
        self._budget.reserve(self._reservation, len(data))
        try:
            if self.file.write(data) != len(data):
                raise RelationalClientError('Incomplete upload spool write')
        except BaseException:
            self.failed = True
            raise
        self.size += len(data)
        self.last = (offset, data)
        return self.size

    def finish(self):
        self._check_usable()
        try:
            self.file.flush()
            self.file.seek(0)
        except BaseException:
            self.failed = True
            raise
        self.ready = True
        return self.file

    def close(self):
        if self.closed:
            return
        try:
            self.file.close()
        except BaseException:
            self.failed = True
            raise
        self.closed = True
        self.last = None
        self._budget.release(self._reservation)


class ResultStream:
    def __init__(self, cursor, columns, blob_type, array_type=(), *,
                 validate_text_encoding=None, page_rows=PAGE_ROWS):
        if type(page_rows) is not int or not 1 <= page_rows <= 500:
            raise RelationalClientError('Stream page rows must be an integer from 1 to 500')
        self.page_rows = page_rows
        self.cursor = cursor
        self.columns = list(columns)
        self.blob_type = blob_type
        self.array_type = array_type
        self.validate_text_encoding = validate_text_encoding
        self.reference = str(uuid.uuid4())
        self.sequence = -1
        self.page = None
        self.blobs = {}
        self.arrays = {}
        self.eof = False
        self.closed = False
        self.failed = False
        self.rows_read = 0
        self.download = None

    def _release_blobs(self):
        failures = []
        for resources in (self.blobs, self.arrays):
            for reference, entry in tuple(resources.items()):
                try:
                    entry['reader'].close()
                    del resources[reference]
                except Exception as exc:
                    failures.append(exc)
        if failures:
            raise failures[0]

    def close(self):
        if self.download is not None:
            self.download.abort()
        # Retain failed owners for a cleanup retry.
        self._release_blobs()
        if not self.closed:
            self.cursor.close()
        self.closed = True
        self.page = None

    def _value(self, value):
        if isinstance(value, self.array_type):
            reference = str(uuid.uuid4())
            self.arrays[reference] = {
                'reader': value, 'offset': 0, 'last': None,
            }
            return {'array_reference': reference, **value.describe()}
        if isinstance(value, self.blob_type):
            reference = str(uuid.uuid4())
            subtype = value.sub_type
            # The installed driver's text read(size) decodes each byte chunk
            # independently. Raw bytes preserve multibyte boundaries.
            value.sub_type = 0
            self.blobs[reference] = {
                'reader': value, 'offset': 0, 'last': None,
                'decoder': (codecs.getincrementaldecoder(
                    self.validate_text_encoding)() if subtype == 1 and
                    self.validate_text_encoding else None),
            }
            return {'blob_reference': reference, 'sub_type': subtype,
                    'transfer_encoding': 'base64'}
        return normalize_value(value)

    def fetch(self, sequence):
        if type(sequence) is not int or sequence < 0:
            raise RelationalClientError('Invalid result page sequence')
        if self.failed:
            raise RelationalClientError('Failed result stream must be closed')
        if sequence == self.sequence and self.page is not None:
            return copy.deepcopy(self.page)
        if self.closed or self.eof or sequence != self.sequence + 1:
            raise RelationalClientError('Result page is no longer available')
        try:
            self._release_blobs()
            rows, size = [], 0
            while len(rows) < self.page_rows and size < PAGE_BYTES:
                row = self.cursor.fetchone()
                if row is None:
                    self.eof = True
                    break
                # Register native owners before converting other values.
                converted = [self._value(value) if (
                    isinstance(value, self.blob_type) or
                    isinstance(value, self.array_type)) else value
                    for value in row]
                converted = [value if isinstance(value, dict) and
                             ('blob_reference' in value or
                              'array_reference' in value) else
                             normalize_value(value) for value in converted]
                row_size = len(json.dumps(converted, ensure_ascii=True,
                                          allow_nan=False).encode('utf-8'))
                if row_size > PAGE_BYTES:
                    raise RelationalClientError(
                        'A non-BLOB row exceeds the streaming page budget')
                rows.append(converted)
                size += row_size
                self.rows_read += 1
            # No lookahead: fetching selectable PSQL can execute native work.
            self.sequence = sequence
            self.page = {
                'stream_reference': self.reference, 'sequence': sequence,
                'columns': self.columns, 'rows': rows,
                'end_of_cursor': self.eof, 'rows_read': self.rows_read,
                'transaction_finality_changed': False,
            }
            return copy.deepcopy(self.page)
        except Exception:
            self.failed = True
            raise

    def read_array(self, reference, offset):
        if self.closed or self.failed or reference not in self.arrays:
            raise RelationalClientError('ARRAY reference is unavailable')
        if type(offset) is not int or offset < 0:
            raise RelationalClientError('Invalid ARRAY element offset')
        entry = self.arrays[reference]
        if entry['last'] is not None and offset == entry['last']['offset']:
            return copy.deepcopy(entry['last'])
        if offset != entry['offset'] or (
                entry['last'] is not None and entry['last']['complete']):
            raise RelationalClientError('ARRAY element offset out of sequence')
        try:
            result = {'array_reference': reference,
                      **entry['reader'].read(offset)}
            if len(json.dumps(result, ensure_ascii=True, allow_nan=False)
                   .encode('utf-8')) > PAGE_BYTES:
                raise RelationalClientError('ARRAY slice exceeds byte budget')
            if result['complete']:
                entry['reader'].close()
            entry['offset'] = result['next_offset']
            entry['last'] = result
            return copy.deepcopy(result)
        except Exception:
            self.failed = True
            raise

    def read_blob(self, reference, offset):
        if self.closed or self.failed or reference not in self.blobs:
            raise RelationalClientError('BLOB reference is unavailable')
        if type(offset) is not int or offset < 0:
            raise RelationalClientError('Invalid BLOB byte offset')
        entry = self.blobs[reference]
        if entry['last'] is not None and offset == entry['last']['offset']:
            return dict(entry['last'])
        if offset != entry['offset'] or (
                entry['last'] is not None and entry['last']['complete']):
            raise RelationalClientError('BLOB byte offset is out of sequence')
        try:
            raw = entry['reader'].read(BLOB_BYTES)
            if not isinstance(raw, bytes) or len(raw) > BLOB_BYTES:
                raise RelationalClientError('Invalid native BLOB chunk')
            decoder = entry.get('decoder')
            if decoder is not None:
                try:
                    decoder.decode(raw, final=len(raw) < BLOB_BYTES)
                except UnicodeDecodeError:
                    raise RelationalClientError(
                        'Native UNICODE_FSS text BLOB conversion is not '
                        'lossless; use a UTF8 attachment') from None
            result = {'blob_reference': reference, 'offset': offset,
                      'next_offset': offset + len(raw),
                      'data': base64.b64encode(raw).decode('ascii'),
                      'encoding': 'base64', 'complete': len(raw) < BLOB_BYTES}
            if result['complete']:
                entry['reader'].close()
            entry['offset'] = result['next_offset']
            entry['last'] = result
            return dict(result)
        except Exception:
            self.failed = True
            raise

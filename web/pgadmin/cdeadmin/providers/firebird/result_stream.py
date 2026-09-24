"""Pull-based, cursor-owned Firebird results; never materialize a BLOB.

Pages replace (not append to) their predecessor. BLOB references expire when
advancing the page. Closing releases resources, never transaction finality.
"""
import base64
import copy
import json
import tempfile
import uuid

from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from .query_values import normalize_value

PAGE_ROWS = 100
PAGE_BYTES = 1024 * 1024
BLOB_BYTES = 64 * 1024
UPLOAD_BYTES = 256 * 1024 * 1024


class BlobUpload:
    """Session-owned disk spool; client and driver both use bounded chunks."""
    def __init__(self):
        self.reference = str(uuid.uuid4())
        self.file = tempfile.TemporaryFile(mode='w+b')
        self.size = 0
        self.ready = False
        self.failed = False
        self.last = None

    def append(self, offset, encoded):
        if self.failed:
            raise RelationalClientError('Failed upload must be closed')
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
        try:
            self.file.write(data)
        except OSError:
            self.failed = True
            raise
        self.size += len(data)
        self.last = (offset, data)
        return self.size

    def finish(self):
        if self.failed:
            raise RelationalClientError('Failed upload must be closed')
        try:
            self.file.flush()
            self.file.seek(0)
        except OSError:
            self.failed = True
            raise
        self.ready = True
        return self.file

    def close(self):
        self.file.close()


class ResultStream:
    def __init__(self, cursor, columns, blob_type):
        self.cursor = cursor
        self.columns = list(columns)
        self.blob_type = blob_type
        self.reference = str(uuid.uuid4())
        self.sequence = -1
        self.page = None
        self.blobs = {}
        self.eof = False
        self.closed = False
        self.failed = False
        self.rows_read = 0

    def _release_blobs(self):
        failures = []
        for reference, entry in tuple(self.blobs.items()):
            try:
                entry['reader'].close()
                del self.blobs[reference]
            except Exception as exc:
                failures.append(exc)
        if failures:
            raise failures[0]

    def close(self):
        # Retain failed owners for a cleanup retry.
        self._release_blobs()
        if not self.closed:
            self.cursor.close()
        self.closed = True
        self.page = None

    def _value(self, value):
        if isinstance(value, self.blob_type):
            reference = str(uuid.uuid4())
            subtype = value.sub_type
            # The installed driver's text read(size) decodes each byte chunk
            # independently. Raw bytes preserve multibyte boundaries.
            value.sub_type = 0
            self.blobs[reference] = {
                'reader': value, 'offset': 0, 'last': None,
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
            while len(rows) < PAGE_ROWS and size < PAGE_BYTES:
                row = self.cursor.fetchone()
                if row is None:
                    self.eof = True
                    break
                # Register all BLOB owners before converting other values.
                converted = [self._value(value) if isinstance(
                    value, self.blob_type) else value for value in row]
                converted = [value if isinstance(value, dict) and
                             'blob_reference' in value else
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

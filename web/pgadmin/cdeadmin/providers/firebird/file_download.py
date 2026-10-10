"""Bounded browser-managed file delivery from a retained result page."""
import base64
import json
import threading
import uuid

from ...sdk.relational import RelationalClientError


class FileDownload:
    def __init__(self, stream, kind, reference):
        if kind not in ('blob', 'array') or stream.closed or stream.failed:
            raise RelationalClientError('File value is unavailable')
        entries = stream.blobs if kind == 'blob' else stream.arrays
        entry = entries.get(reference)
        if entry is None or entry['offset'] != 0 or entry['last'] is not None:
            raise RelationalClientError(
                'File delivery requires an unread value')
        self.lock = threading.RLock()
        self.identifier = str(uuid.uuid4())
        self.stream = stream
        self.kind = kind
        self.reference = reference
        self.state = 'reserved'
        self.sequence = 0
        self.offset = 0
        self.bytes = 0
        self.payload_complete = False
        self.descriptor = (entry['reader'].describe() if kind == 'array'
                           else None)
        self.length = entry['reader'].length if kind == 'blob' else None
        if kind == 'blob' and (type(self.length) is not int or
                               self.length < 0):
            raise RelationalClientError('Invalid native BLOB length')

    @property
    def active(self):
        with self.lock:
            return self.state in ('reserved', 'sending')

    def status(self):
        with self.lock:
            return {'download_id': self.identifier, 'state': self.state,
                    'kind': self.kind, 'bytes': self.bytes,
                    'content_length': self.length,
                    'transaction_finality_changed': False}

    def abort(self):
        with self.lock:
            if self.active:
                self.state = 'interrupted'
            return self.status()

    def dispatch(self, action, request):
        with self.lock:
            if request.get('download_id') != self.identifier:
                raise RelationalClientError('File delivery is unavailable')
            if action == 'download_status':
                return self.status()
            if action == 'download_abort':
                return self.abort()
            if action == 'download_open':
                if self.state != 'reserved':
                    raise RelationalClientError(
                        'File delivery already claimed')
                self.state = 'sending'
                return self.status()
            if action == 'download_finish':
                if self.state != 'sending' or not self.payload_complete:
                    raise RelationalClientError('File delivery is incomplete')
                self.state = 'sent'
                return self.status()
            if action != 'download_chunk' or self.state != 'sending' or (
                    self.payload_complete or type(request.get('sequence')) is
                    not int or request['sequence'] != self.sequence):
                raise RelationalClientError(
                    'Invalid file delivery continuation')
        try:
            # Do not hold the local status/stop lock during native I/O.
            data = self._chunk()
            with self.lock:
                if self.state != 'sending':
                    raise RelationalClientError('File delivery was stopped')
                if len(data) > 1048576:
                    raise RelationalClientError(
                        'File record exceeds byte budget')
                self.bytes += len(data)
                result = {'sequence': self.sequence,
                          'data': base64.b64encode(data).decode('ascii'),
                          'complete': self.payload_complete}
                self.sequence += 1
                return result
        except Exception:
            self.abort()
            raise

    @staticmethod
    def _record(value):
        return (json.dumps(value, ensure_ascii=True, allow_nan=False,
                           separators=(',', ':')) + '\n').encode('utf-8')

    def _chunk(self):
        if self.kind == 'blob':
            part = self.stream.read_blob(self.reference, self.offset)
            raw = base64.b64decode(part['data'], validate=True)
            if (part['offset'] != self.offset or
                    part['next_offset'] != self.offset + len(raw) or
                    part['next_offset'] > self.length or
                    (part['complete'] and
                     part['next_offset'] != self.length)):
                raise RelationalClientError('Native BLOB length changed')
            self.offset = part['next_offset']
            self.payload_complete = part['complete']
            return raw
        if self.sequence == 0:
            keys = ('bounds', 'element_count', 'native_element_type',
                    'scale', 'subtype', 'charset_id')
            header = {key: self.descriptor[key] for key in keys}
            return self._record({'format': 'cdeadmin.firebird-array.v1',
                                 **header})
        if self.offset == self.descriptor['element_count']:
            self.payload_complete = True
            return self._record({'complete': True,
                                 'element_count': self.offset})
        part = self.stream.read_array(self.reference, self.offset)
        if (part['offset'] != self.offset or not part['values'] or
                part['next_offset'] != self.offset + len(part['values']) or
                part['next_offset'] > self.descriptor['element_count'] or
                part['complete'] != (part['next_offset'] ==
                                     self.descriptor['element_count'])):
            raise RelationalClientError('Invalid native ARRAY continuation')
        self.offset = part['next_offset']
        return self._record({key: part[key] for key in
                             ('offset', 'coordinates', 'values')})

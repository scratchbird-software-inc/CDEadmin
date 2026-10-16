"""Read PostgreSQL manifest identity without retaining its entire file inventory."""
import codecs
import hashlib
import json
from pathlib import Path


class NativeManifestError(ValueError):
    pass


class Reader:
    # Native file entries contain bounded paths and fixed-length checksums.
    # The complete Files array may describe millions of files.
    value_limit=1024*1024

    def __init__(self, stream, *, progress=None, cancel_signal=None):
        self.stream=stream;self.progress=progress;self.cancel_signal=cancel_signal
        self.buffer='';self.position=0;self.eof=False;self.bytes_read=0
        self.digest=hashlib.sha256();self.decoder=json.JSONDecoder(parse_constant=self.invalid_constant)
        self.utf8=codecs.getincrementaldecoder('utf8')()

    @staticmethod
    def invalid_constant(_value):
        raise NativeManifestError('Non-JSON value in native backup manifest')

    def fill(self):
        if self.cancel_signal is not None and self.cancel_signal.is_set():
            raise NativeManifestError('Native backup manifest inspection was cancelled')
        raw=self.stream.read(65536)
        self.eof=not raw;self.digest.update(raw);self.bytes_read+=len(raw)
        try:text=self.utf8.decode(raw,final=self.eof)
        except UnicodeError:raise NativeManifestError('Native backup manifest is not UTF-8') from None
        self.buffer=self.buffer[self.position:]+text;self.position=0
        if self.progress is not None:self.progress({'manifest_bytes_read':self.bytes_read})

    def token(self):
        while True:
            while self.position<len(self.buffer) and self.buffer[self.position] in ' \t\r\n':self.position+=1
            if self.position<len(self.buffer):return self.buffer[self.position]
            if self.eof:return None
            self.fill()

    def take(self, expected):
        if self.token()!=expected:raise NativeManifestError('Malformed native backup manifest')
        self.position+=1

    def value(self):
        if self.token() is None:raise NativeManifestError('Incomplete native backup manifest')
        while True:
            if len(self.buffer)-self.position>self.value_limit:
                raise NativeManifestError('Native backup manifest entry exceeds the native metadata bound')
            try:
                value,end=self.decoder.raw_decode(self.buffer,self.position)
                # A number can continue across an input boundary.
                if end<len(self.buffer) and self.buffer[end] in ' \t\r\n,:]}' or end==len(self.buffer) and self.eof:
                    self.position=end;return value
                if self.eof:raise NativeManifestError('Malformed native backup manifest')
            except json.JSONDecodeError:
                if self.eof:raise NativeManifestError('Malformed native backup manifest') from None
            self.fill()


def read_manifest(path, *, progress=None, cancel_signal=None):
    filename=Path(path)/'backup_manifest'
    try:stream=filename.open('rb')
    except OSError:raise NativeManifestError('Native backup manifest is unavailable') from None
    with stream:
        reader=Reader(stream,progress=progress,cancel_signal=cancel_signal)
        data={};count=None;checksum_count=0;algorithms=set()
        reader.take('{')
        while reader.token()!='}':
            key=reader.value()
            if not isinstance(key,str) or key in data:raise NativeManifestError('Duplicate or invalid native manifest field')
            reader.take(':')
            if key=='Files':
                reader.take('[');count=0
                while reader.token()!=']':
                    entry=reader.value()
                    if not isinstance(entry,dict):raise NativeManifestError('Invalid native manifest file entry')
                    algorithm=entry.get('Checksum-Algorithm')
                    if algorithm is not None:
                        if not isinstance(algorithm,str) or algorithm not in {'CRC32C','SHA224','SHA256','SHA384','SHA512'}:
                            raise NativeManifestError('Unknown native manifest checksum algorithm')
                        checksum_count+=1;algorithms.add(algorithm)
                    count+=1
                    if reader.token()==']':break
                    reader.take(',')
                    if reader.token()==']':raise NativeManifestError('Invalid native manifest file separator')
                reader.take(']');data[key]=None
            else:data[key]=reader.value()
            if reader.token()=='}':break
            reader.take(',')
            if reader.token()=='}':raise NativeManifestError('Invalid native manifest field separator')
        reader.take('}')
        if reader.token() is not None:raise NativeManifestError('Trailing data in native backup manifest')
    system=data.get('System-Identifier');version=data.get('PostgreSQL-Backup-Manifest-Version');ranges=data.get('WAL-Ranges')
    if type(system) is not int or not 0<system<2**64 or type(version) is not int or version!=2:
        raise NativeManifestError('PostgreSQL 18 backup manifest identity is unavailable')
    if count is None or not isinstance(ranges,list) or not ranges:
        raise NativeManifestError('Native backup manifest files or WAL ranges are unavailable')
    return {'system_identifier':str(system),'manifest_sha256':reader.digest.hexdigest(),
            'files':count,'wal_ranges':ranges,'manifest_version':version,
            'files_with_checksums':checksum_count,'files_without_checksums':count-checksum_count,
            'checksum_algorithms':sorted(algorithms)}

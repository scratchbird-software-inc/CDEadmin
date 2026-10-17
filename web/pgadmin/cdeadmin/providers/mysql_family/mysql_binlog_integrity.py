"""Streaming native v4 log framing and CRC32, including FDE flag handling.

Authority: MySQL9.7 sql/log_event.cc and libs/mysql/binlog/event; this checks
bytes and framing, not transaction replay or data recovery postconditions.
"""
from contextlib import contextmanager
import gzip
import os
import re
import stat
import zlib


class BinlogIntegrityError(ValueError):
    pass


@contextmanager
def decoded(path,compression):
    descriptor=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0))
    with os.fdopen(descriptor,'rb') as raw:
        info=os.fstat(raw.fileno())
        if not stat.S_ISREG(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
            raise BinlogIntegrityError('Native binary log is not a regular file')
        if compression=='none':yield raw
        elif compression=='gzip':
            try:
                with gzip.GzipFile(fileobj=raw,mode='rb') as stream:yield stream
            except (gzip.BadGzipFile,EOFError,zlib.error):
                raise BinlogIntegrityError('Native gzip binary-log stream is damaged') from None
        elif compression=='zstd':
            from compression.zstd import ZstdFile,ZstdError
            try:
                with ZstdFile(raw,mode='rb') as stream:yield stream
            except (ZstdError,EOFError):raise BinlogIntegrityError('Native Zstandard binary-log stream is damaged') from None
        else:raise BinlogIntegrityError('Native binary-log compression is unavailable')


def verify_frames(path,compression,expected_bytes,expected_events,*,cancel=None):
    if type(expected_bytes) is not int or expected_bytes<4 or type(expected_events) is not int or expected_events<1:
        raise BinlogIntegrityError('Native binary-log byte/event counts are invalid')
    consumed=0;events=0;algorithm=None;checksummed=0
    with decoded(path,compression) as stream:
        def read(size,*,eof=False):
            nonlocal consumed
            result=bytearray()
            while len(result)<size:
                if cancel is not None and cancel.is_set():raise InterruptedError('Binary-log integrity verification cancelled')
                data=stream.read(min(size-len(result),1024*1024))
                if not data:break
                result.extend(data);consumed+=len(data)
                if consumed>expected_bytes:raise BinlogIntegrityError('Native binary log exceeds its declared decoded length')
            if len(result)!=size and not (eof and not result):raise BinlogIntegrityError('Native binary log has a truncated event')
            return bytes(result)
        if read(4)!=b'\xfebin':raise BinlogIntegrityError('Native binary-log magic differs')
        while header:=read(19,eof=True):
            length=int.from_bytes(header[9:13],'little');kind=header[4]
            if length<19 or length>expected_bytes-consumed+19:
                raise BinlogIntegrityError('Native binary-log event length differs')
            if events==0 and kind!=15:raise BinlogIntegrityError('Native binary log lacks its format-description event')
            if kind==15:
                if not 76<=length<=4096:raise BinlogIntegrityError('Native format-description event length differs')
                event=header+read(length-19)
                if int.from_bytes(event[19:21],'little')!=4 or event[75]!=19:
                    raise BinlogIntegrityError('Native binary-log version or common header length is unsupported')
                version=re.match(rb'(\d+)\.(\d+)\.(\d+)',event[21:71])
                if not version:raise BinlogIntegrityError('Native binary-log format version identity is unavailable')
                has_descriptor=tuple(map(int,version.groups()))>=(5,6,1)
                if has_descriptor:
                    algorithm=event[-5]
                    if algorithm not in {0,1}:raise BinlogIntegrityError('Native binary-log checksum algorithm is unsupported')
                    # FDE is checksummed even when following events omit CRC.
                    # BINLOG_IN_USE_F may change when the original log closes.
                    checked=bytearray(event[:-4]);checked[17]&=~1
                    if zlib.crc32(checked)!=int.from_bytes(event[-4:],'little'):
                        raise BinlogIntegrityError('Native format-description checksum differs')
                    checksummed+=1
                else:algorithm=0
            else:
                checksum=algorithm==1
                if length<19+4*checksum:raise BinlogIntegrityError('Native binary-log checksum footer is truncated')
                remaining=length-19-4*checksum;crc=zlib.crc32(header)
                while remaining:
                    data=read(min(remaining,1024*1024));remaining-=len(data)
                    if checksum:crc=zlib.crc32(data,crc)
                if checksum:
                    if crc!=int.from_bytes(read(4),'little'):raise BinlogIntegrityError('Native binary-log event checksum differs')
                    checksummed+=1
            events+=1
            if events>expected_events:raise BinlogIntegrityError('Native binary log exceeds its declared event count')
        if consumed!=expected_bytes or events!=expected_events:
            raise BinlogIntegrityError('Native binary-log decoded bytes or event count differs')
    return {'decoded_bytes':str(consumed),'event_count':str(events),'checksummed_events':str(checksummed),
        'checksum_algorithm':'crc32' if algorithm==1 else 'native_none',
        'native_framing_verified':True,'native_checksums_verified_where_present':True}

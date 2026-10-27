"""Publish completed native receiver files without overwriting an archive.

These checks establish file/cluster identity, not record CRCs or recoverability.
Native PostgreSQL verification and recovery retain that authority.
"""
from contextlib import ExitStack
import gzip
import hashlib
import os
from pathlib import Path
import re
import struct
import uuid

from ...operations.fileio import private_file
from .continuity import ContinuityError
from .continuity_wal import _regular, _identity, _digest

SEGMENT=re.compile(r'[0-9A-F]{24}\Z')
HISTORY=re.compile(r'[0-9A-F]{8}\.history\Z')
COMPLETE=re.compile(r'([0-9A-F]{24})(\.gz|\.lz4)?\Z')
TRANSIENT=re.compile(r'(?:[0-9A-F]{24}(?:\.gz|\.lz4)?\.partial|[0-9A-F]{8}\.history\.tmp)\Z')


def geometry(source):
    size,block=source.get('wal_segment_bytes'),source.get('wal_block_bytes')
    if (type(size) is not int or not 1024**2<=size<=1024**3 or size&(size-1) or
            type(block) is not int or not 512<=block<=65536 or block&(block-1) or size%block):
        raise ContinuityError('Native WAL segment and block geometry is unavailable')
    identity=source.get('system_identifier')
    if not isinstance(identity,str) or not identity.isascii() or not identity.isdigit() or not 0<int(identity)<2**64:
        raise ContinuityError('Native WAL cluster identity is unavailable')
    return size,block,int(identity)


def inspect_header(header, name, source):
    """Observe the selected PostgreSQL 18 native 64 bit long-page header."""
    size,block,identity=geometry(source)
    if len(header)<40:raise ContinuityError('Completed native WAL file has no long page header')
    endian='<' if header[:2]==b'\x18\xd1' else '>' if header[:2]==b'\xd1\x18' else None
    if endian is None:raise ContinuityError('Native WAL page format differs from PostgreSQL 18')
    magic,flags,timeline,address=struct.unpack_from(endian+'HHIQ',header)
    system,segment_bytes,block_bytes=struct.unpack_from(endian+'QII',header,24)
    log,segment=int(name[8:16],16),int(name[16:24],16)
    # A promoted timeline can retain ancestor page headers in its first file.
    # PostgreSQL recovery, rather than a filename comparison, proves ancestry.
    if (not flags&2 or not 0<timeline<=int(name[:8],16) or
            system!=identity or segment_bytes!=size or block_bytes!=block or
            segment>=2**32//size or address!=log*2**32+segment*size):
        raise ContinuityError('Completed native WAL file does not match its cluster, geometry or segment address')
    return {'system_identifier':str(system),'page_timeline':timeline,'file_timeline':int(name[:8],16),
            'segment_bytes':size,'block_bytes':block,'native_record_verification':False}


def _sync_directory(path):
    descriptor=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)


def _publish_exclusive(source,target):
    if os.name!='nt':
        os.link(source,target);_sync_directory(target.parent)
        return
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.MoveFileExW.argtypes=[wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.DWORD]
    kernel.MoveFileExW.restype=wintypes.BOOL
    # WRITE_THROUGH without REPLACE_EXISTING or COPY_ALLOWED: publication is
    # exclusive and stays on one volume, including after native Windows flush.
    if not kernel.MoveFileExW(os.fspath(source),os.fspath(target),8):
        raise ctypes.WinError(ctypes.get_last_error())


def publish_file(path, archive, source, *, cancel_signal=None, check_cancel=None):
    """Decode one closed receiver file and exclusively publish its raw bytes."""
    path,archive=Path(path),Path(archive)
    if check_cancel is not None:check_cancel()
    if cancel_signal is not None and cancel_signal.is_set():raise ContinuityError('Native WAL publication was cancelled')
    match=COMPLETE.fullmatch(path.name)
    history=HISTORY.fullmatch(path.name)
    if match is None and history is None:raise ContinuityError('Select a completed native receiver file')
    if archive.is_symlink() or not archive.is_dir() or archive.resolve()!=archive:
        raise ContinuityError('Native WAL publication requires a private owned archive directory')
    size,_block,_identity_value=geometry(source)
    name=match[1] if match else path.name
    maximum=size if match else 1024*1024
    before=_regular(path)
    temporary=archive.parent/('.scratchrobin-wal-'+str(uuid.uuid4()))
    digest=hashlib.sha256();count=0;header=bytearray()
    try:
        with ExitStack() as stack:
            descriptor=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0))
            raw=stack.enter_context(os.fdopen(descriptor,'rb'))
            if _identity(os.fstat(raw.fileno()))!=_identity(before):
                raise ContinuityError('Completed native receiver file changed before publication')
            incoming=raw
            if match and match[2]=='.gz':incoming=stack.enter_context(gzip.GzipFile(fileobj=raw,mode='rb'))
            elif match and match[2]=='.lz4':
                import lz4.frame
                incoming=stack.enter_context(lz4.frame.open(raw,'rb'))
            outgoing=stack.enter_context(temporary.open('xb'));private_file(temporary)
            while chunk:=incoming.read(1024*1024):
                if check_cancel is not None:check_cancel()
                if cancel_signal is not None and cancel_signal.is_set():raise ContinuityError('Native WAL publication was cancelled')
                count+=len(chunk)
                if count>maximum:raise ContinuityError('Completed native receiver file exceeds its native size')
                if len(header)<40:header.extend(chunk[:40-len(header)])
                digest.update(chunk);outgoing.write(chunk)
            if _identity(os.fstat(raw.fileno()))!=_identity(before) or _identity(_regular(path))!=_identity(before):
                raise ContinuityError('Completed native receiver file changed during publication')
            if match and count!=size or history and not count:
                raise ContinuityError('Completed native receiver file has an incomplete native size')
            identity=inspect_header(header,name,source) if match else {'native_record_verification':False}
            outgoing.flush();os.fsync(outgoing.fileno())
        result={'name':name,'bytes':count,'sha256':digest.hexdigest()}
        target=archive/name
        try:_publish_exclusive(temporary,target)
        except FileExistsError:
            if _digest(target)!=result:
                raise ContinuityError('The archive already contains different bytes for this native WAL identity') from None
            published=False
        else:
            published=True
        return {**result,**identity,'published':published,'source_file':path.name,'completed_native_file_observed':True}
    finally:temporary.unlink(missing_ok=True)


def iter_completed(staging,archive,source,*,observed=None,cancel_signal=None,check_cancel=None):
    """Inspect closed native names only; partial files remain with their job."""
    if check_cancel is not None:check_cancel()
    if cancel_signal is not None and cancel_signal.is_set():
        raise ContinuityError('Native WAL publication was cancelled')
    with os.scandir(staging) as entries:
        for entry in entries:
            if check_cancel is not None:check_cancel()
            if cancel_signal is not None and cancel_signal.is_set():
                raise ContinuityError('Native WAL publication was cancelled')
            if TRANSIENT.fullmatch(entry.name):continue
            if COMPLETE.fullmatch(entry.name) is None and HISTORY.fullmatch(entry.name) is None:
                raise ContinuityError('The native receiver workspace contains an unexpected file')
            if observed is not None and entry.name in observed:continue
            receipt=publish_file(Path(entry.path),archive,source,cancel_signal=cancel_signal,check_cancel=check_cancel)
            if observed is not None:observed.add(entry.name)
            yield receipt


def publish_completed(staging,archive,source,*,observed=None,cancel_signal=None,check_cancel=None):
    return list(iter_completed(staging,archive,source,observed=observed,cancel_signal=cancel_signal,check_cancel=check_cancel))

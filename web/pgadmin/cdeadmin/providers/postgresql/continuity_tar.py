"""Bounded materialization of native PostgreSQL directory TAR backups."""
from contextlib import ExitStack
from contextlib import contextmanager
import gzip
import hashlib
from importlib.metadata import version
import os
from pathlib import Path, PurePosixPath
import platform
import re
import tarfile

from ...operations.fileio import private_directory, private_file
from .continuity import ContinuityError


SUFFIXES=('.tar','.tar.gz','.tar.lz4','.tar.zst')


@contextmanager
def decoded(path):
    """Use streaming native archive codecs, including concatenated frames."""
    with ExitStack() as stack:
        incoming=stack.enter_context(path.open('rb'))
        codec='none';decoder={}
        if path.name.endswith('.gz'):
            import zlib
            incoming=stack.enter_context(gzip.GzipFile(fileobj=incoming,mode='rb'));codec='gzip'
            decoder={'implementation':'gzip.GzipFile','zlib':zlib.ZLIB_RUNTIME_VERSION}
        elif path.name.endswith('.lz4'):
            import lz4.frame
            incoming=stack.enter_context(lz4.frame.open(incoming,mode='rb'));codec='lz4'
            decoder={'implementation':'lz4.frame','package':version('lz4'),'library':lz4.library_version_string()}
        elif path.name.endswith('.zst'):
            from compression.zstd import ZstdFile,zstd_version
            incoming=stack.enter_context(ZstdFile(incoming,mode='rb'));codec='zstd'
            decoder={'implementation':'compression.zstd','library':zstd_version}
        yield incoming,codec,decoder


def parse_tablespace_map(data):
    """Decode native escaped bytes; paths are observations, never destinations."""
    if not isinstance(data,bytes) or len(data)>16*1024**2 or b'\0' in data:
        raise ContinuityError('Native tablespace map exceeds its admitted byte representation')
    lines=[];line=bytearray();escaped=False
    for value in data:
        if escaped:line.append(value);escaped=False
        elif value==92:escaped=True
        elif value in (10,13):
            if line:lines.append(bytes(line));line.clear()
        else:line.append(value)
    if escaped or line:raise ContinuityError('Native tablespace map is incomplete')
    result=[];seen=set()
    for line in lines:
        oid,separator,path=line.partition(b' ')
        if (not separator or re.fullmatch(rb'[1-9][0-9]{0,9}',oid) is None or
                int(oid)>4294967295 or not path or oid in seen or len(path)>=1024):
            raise ContinuityError('Native tablespace map has an invalid or duplicate identity')
        try:location=path.decode('utf8')
        except UnicodeError:raise ContinuityError('Native tablespace path requires a lossless UTF8 representation') from None
        seen.add(oid);result.append({'oid':int(oid),'location':location,'name_observed':False})
    return result


def tablespace_observation(source,*,progress,cancel_signal):
    """Read native backup metadata after separate native file verification."""
    source=Path(source);entries=list(source.iterdir())
    bases=[entry for entry in entries if entry.name in {'base'+suffix for suffix in SUFFIXES}]
    if len(bases)!=1:raise ContinuityError('Select one native base TAR for tablespace observation')
    if any(not entry.is_file() or entry.is_symlink() or getattr(entry.lstat(),'st_file_attributes',0)&0x400 for entry in entries):
        raise ContinuityError('Native TAR metadata requires regular managed files')
    archived=[]
    for entry in entries:
        for suffix in SUFFIXES:
            if entry.name.endswith(suffix):
                stem=entry.name[:-len(suffix)]
                if stem not in {'base','pg_wal'}:
                    if re.fullmatch(r'[1-9][0-9]{0,9}',stem) is None or int(stem)>4294967295:
                        raise ContinuityError('Native tablespace archive has an invalid OID')
                    archived.append(int(stem))
    if len(archived)!=len(set(archived)):raise ContinuityError('Duplicate native tablespace archives are unavailable')
    data=None;members=0
    def tick():
        progress({'phase':'reading_native_tablespace_map','archive_members':members})
        if cancel_signal.is_set():raise ContinuityError('Native tablespace observation was cancelled')
    # Native backups put the map near the beginning. No other file content or
    # source-host path is opened. pg_verifybackup already checked the archive.
    with decoded(bases[0]) as (incoming,_codec,_decoder):
        with tarfile.open(fileobj=incoming,mode='r|',stream=True) as archive:
            for member in archive:
                tick();members+=1
                if member.name in {'tablespace_map','./tablespace_map'}:
                    if not member.isreg() or member.size>16*1024**2:
                        raise ContinuityError('Native tablespace map is not a bounded regular member')
                    with archive.extractfile(member) as contents:data=contents.read(16*1024**2+1)
                    break
                # A native map is sent immediately after backup_label. Once a
                # normal file follows that preamble, an absent map is empty.
                if member.name not in {'backup_label','./backup_label'}:break
    tablespaces=parse_tablespace_map(data or b'')
    if sorted(archived)!=sorted(item['oid'] for item in tablespaces):
        raise ContinuityError('Native tablespace map and archive identities differ')
    tick()
    return {'source':'native-backup-tablespace-map','tablespaces':tablespaces,
        'tablespace_catalog_observed':False,'native_names_observed':False,
        'source_host_paths_opened':False,'map_sha256':hashlib.sha256(data or b'').hexdigest()}


def materialize(source, destination, tablespaces, wal_method, *, progress, cancel_signal):
    source,destination=Path(source),Path(destination)
    if tablespaces is None:
        tablespaces=tablespace_observation(source,progress=progress,cancel_signal=cancel_signal)['tablespaces']
    spaces={str(item['oid']) for item in tablespaces if item.get('location')}
    prefixes={'base',*spaces,*({'pg_wal'} if wal_method=='stream' else set())}
    archives={}
    entries=list(source.iterdir())
    for prefix in prefixes:
        candidates=[path for path in entries if path.name in {prefix+suffix for suffix in SUFFIXES}]
        if len(candidates)!=1:raise ContinuityError('Native TAR backup requires one exact archive per base, tablespace and streamed WAL scope')
        archives[prefix]=candidates[0]
    expected={'backup_manifest',*(path.name for path in archives.values())}
    if {path.name for path in entries}!=expected:
        raise ContinuityError('Native TAR backup contains an unexpected artifact')
    for path in entries:
        info=path.lstat()
        if not path.is_file() or path.is_symlink() or getattr(info,'st_file_attributes',0)&0x400:
            raise ContinuityError('Native TAR input must contain regular managed files')
    total=0;members=0;codecs=set();decoders={}
    def tick():
        progress({'phase':'materializing_recovery_artifact','copied_bytes':total,'archive_members':members})
        if cancel_signal.is_set():raise ContinuityError('Native TAR recovery materialization was cancelled')
    def directory(path):
        path.mkdir(mode=0o700,parents=True,exist_ok=True);private_directory(path)
    def copy(incoming,path):
        nonlocal total
        with path.open('xb') as outgoing:
            private_file(path)
            while block:=incoming.read(1024*1024):
                outgoing.write(block);total+=len(block);tick()
            outgoing.flush();os.fsync(outgoing.fileno())
    def extract(path,target):
        nonlocal members
        directory(target)
        with decoded(path) as (incoming,codec,decoder):
            codecs.add(codec)
            if decoder:decoders[codec]=decoder
            with tarfile.open(fileobj=incoming,mode='r|',stream=True) as archive:
                for member in archive:
                    tick();members+=1
                    name=member.name.rstrip('/') if member.isdir() else member.name
                    # pg_basebackup synthesizes ./pg_wal/archive_status and
                    # ./pg_wal/summaries directories. Leading current-directory
                    # prefixes are relative; internal or parent traversal is not.
                    while name.startswith('./'):name=name[2:]
                    if name=='.' and member.isdir():continue
                    parts=name.split('/')
                    if (not name or '\x00' in name or PurePosixPath(name).is_absolute() or
                            any(part in {'','.','..'} for part in parts) or
                            os.name=='nt' and any('\\' in part or ':' in part for part in parts)):
                        raise ContinuityError('Native TAR member cannot be represented inside its recovery scope')
                    if not (member.isdir() or member.isreg()) or member.sparse is not None:
                        raise ContinuityError('Native TAR links, sparse entries and special files are not admitted')
                    output=target.joinpath(*parts)
                    if member.isdir():directory(output)
                    else:
                        directory(output.parent)
                        with archive.extractfile(member) as contents:copy(contents,output)
                # Finish the actual compressed stream, including its checksum
                # and concatenated frames. Do not accept hidden payload after
                # the native TAR end marker or ignore a damaged final trailer.
                while tail:=archive.fileobj.read(1024*1024):
                    tick()
                    if any(tail):raise ContinuityError('Unexpected data follows the native TAR end marker')
    tick()
    if destination.exists():raise ContinuityError('Native recovery destination already exists; replay is refused')
    try:
        extract(archives['base'],destination)
        for oid in sorted(spaces):
            mapped=destination.parent/'tablespaces'/oid
            extract(archives[oid],mapped)
            directory(destination/'pg_tblspc')
            (destination/'pg_tblspc'/oid).symlink_to(mapped,target_is_directory=True)
        if wal_method=='stream':extract(archives['pg_wal'],destination/'pg_wal')
        with (source/'backup_manifest').open('rb') as incoming:copy(incoming,destination/'backup_manifest')
    except Exception as error:
        if isinstance(error,ContinuityError):raise
        raise ContinuityError('Native TAR materialization failed: '+type(error).__name__) from None
    tick()
    return {'independent_byte_copy':True,'materialized_format':'plain','source_format':'tar',
            'copied_bytes':total,'archive_members':members,'compression':sorted(codecs),'decoders':decoders,
            'python':platform.python_version(),'tablespace_links_remapped':True}

"""Bounded materialization of native PostgreSQL directory TAR backups."""
from contextlib import ExitStack
import gzip
from importlib.metadata import version
import os
from pathlib import Path, PurePosixPath
import platform
import tarfile

from ...operations.fileio import private_directory, private_file
from .continuity import ContinuityError


SUFFIXES=('.tar','.tar.gz','.tar.lz4','.tar.zst')


def materialize(source, destination, tablespaces, wal_method, *, progress, cancel_signal):
    source,destination=Path(source),Path(destination)
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
        with ExitStack() as stack:
            incoming=stack.enter_context(path.open('rb'))
            # PostgreSQL's gzip WAL writer concatenates streams, including an
            # initial empty stream. tarfile's r|gz decoder stops at that first
            # stream; GzipFile correctly reads every native member.
            if path.name.endswith('.gz'):
                import zlib
                incoming=stack.enter_context(gzip.GzipFile(fileobj=incoming,mode='rb'));codecs.add('gzip')
                decoders['gzip']={'implementation':'gzip.GzipFile','zlib':zlib.ZLIB_RUNTIME_VERSION}
            elif path.name.endswith('.lz4'):
                import lz4.frame
                incoming=stack.enter_context(lz4.frame.open(incoming,mode='rb'));codecs.add('lz4')
                decoders['lz4']={'implementation':'lz4.frame','package':version('lz4'),'library':lz4.library_version_string()}
            elif path.name.endswith('.zst'):
                from compression.zstd import ZstdFile, zstd_version
                incoming=stack.enter_context(ZstdFile(incoming,mode='rb'));codecs.add('zstd')
                decoders['zstd']={'implementation':'compression.zstd','library':zstd_version}
            else:codecs.add('none')
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

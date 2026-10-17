"""Read-only native WAL archive review and staging into an independent copy."""
import hashlib
import os
from pathlib import Path
import re
import stat

from ...operations.fileio import private_file
from .continuity import ContinuityError

NATIVE_FILE = re.compile(r'(?:[0-9A-F]{24}|[0-9A-F]{8}\.history|[0-9A-F]{24}\.[0-9A-F]{8}\.backup)\Z')
ARCHIVE_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
MAX_FILES = 100000


def _regular(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ContinuityError('WAL archives require regular native files without links or reparse points')
    return info


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _digest(path, output=None, *, progress=None, cancel_signal=None):
    before = _regular(path)
    digest = hashlib.sha256(); size = 0
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
    with os.fdopen(descriptor, 'rb') as stream:
        if _identity(os.fstat(stream.fileno())) != _identity(before):
            raise ContinuityError('WAL archive file changed before observation')
        while block := stream.read(1024 * 1024):
            if cancel_signal is not None and cancel_signal.is_set():
                raise ContinuityError('WAL staging was cancelled')
            digest.update(block); size += len(block)
            if output is not None: output.write(block)
            if progress is not None: progress(size)
        if _identity(os.fstat(stream.fileno())) != _identity(before) or _identity(_regular(path)) != _identity(before):
            raise ContinuityError('WAL archive file changed during observation')
    return {'name': path.name, 'bytes': size, 'sha256': digest.hexdigest()}


def directory(root, name):
    if not isinstance(name, str) or ARCHIVE_NAME.fullmatch(name) is None:
        raise ContinuityError('Select one registered native WAL archive name')
    root = Path(root).resolve()
    selected = root / name
    if selected.is_symlink() or not selected.is_dir() or selected.resolve() != selected:
        raise ContinuityError('The selected owner/endpoint WAL archive is unavailable')
    if getattr(selected.lstat(), 'st_file_attributes', 0) & 0x400:
        raise ContinuityError('WAL archive directories cannot be reparse points')
    return selected


def freeze(root, name):
    selected = directory(root, name)
    files = []
    with os.scandir(selected) as entries:
        for entry in entries:
            if NATIVE_FILE.fullmatch(entry.name) is None:
                raise ContinuityError('The WAL archive contains an incomplete or non-native file')
            if len(files) >= MAX_FILES:
                raise ContinuityError('Select at most 100000 completed native WAL archive files per recovery review')
            files.append(_digest(Path(entry.path)))
    if not any(re.fullmatch(r'[0-9A-F]{24}', item['name']) for item in files):
        raise ContinuityError('The WAL archive has no completed native segments')
    files.sort(key=lambda item: item['name'])
    return {'name': name, 'files': files, 'bytes': sum(item['bytes'] for item in files),
            'reviewed_content_sha256': True}


def stage(root, reviewed, clone, *, progress, cancel_signal):
    selected = directory(root, reviewed['name'])
    # Refuse additions/removals as well as changed bytes. Native PostgreSQL
    # validates segment headers, cluster identity, CRCs, timeline and ancestry.
    if {entry.name for entry in selected.iterdir()} != {item['name'] for item in reviewed['files']}:
        raise ContinuityError('WAL archive inventory changed after review')
    target = Path(clone) / 'pg_wal'
    if target.is_symlink() or not target.is_dir():
        raise ContinuityError('The independent recovery copy has no private WAL directory')
    total = 0; aggregate = hashlib.sha256()
    for item in reviewed['files']:
        if NATIVE_FILE.fullmatch(item['name']) is None:
            raise ContinuityError('Invalid reviewed native WAL identity')
        output = target / item['name']
        if output.exists(): _regular(output)
        temporary = target / ('.scratchrobin-' + item['name'])
        def tick(count):
            progress({'phase': 'staging_recovery_wal', 'copied_bytes': total + count,
                      'archive_file': item['name']})
        try:
            with temporary.open('xb') as stream:
                private_file(temporary)
                actual = _digest(selected / item['name'], stream, progress=tick, cancel_signal=cancel_signal)
                stream.flush(); os.fsync(stream.fileno())
            if actual != item:
                raise ContinuityError('WAL archive content changed after review')
            os.replace(temporary, output)
        finally: temporary.unlink(missing_ok=True)
        total += item['bytes']; aggregate.update((item['name'] + ':' + item['sha256'] + '\n').encode('ascii'))
    return {'files': len(reviewed['files']), 'bytes': total, 'content_sha256': aggregate.hexdigest(),
            'reviewed_content_matched': True, 'source_files_modified': False}

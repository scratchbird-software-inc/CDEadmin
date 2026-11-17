"""Approved local logical backup outputs, reserved without overwriting files."""
from contextlib import contextmanager
from contextvars import ContextVar
import copy
import os
from pathlib import Path
import stat

from ...sdk import RelationalClientError
from .embedded import embedded_route
from .backup_volumes import logical_backup_volumes

_OUTPUTS = ContextVar('firebird_local_backup_outputs', default=None)


def _identity(info):
    return {'device': str(info.st_dev), 'inode': str(info.st_ino)}


def selection(route, options, *, require_absent=True):
    files, sizes = logical_backup_volumes(options)
    result = []
    for index, filename in enumerate(files):
        path = embedded_route({**route, 'database': filename})['database']
        if path != filename:
            raise RelationalClientError('Select canonical absolute local backup filenames')
        target = Path(path)
        if target == Path(route['database']):
            raise RelationalClientError('Backup output must differ from its source database')
        if require_absent and os.path.lexists(path):
            raise RelationalClientError('Local backup output already exists; select unused filenames')
        parent = target.parent.stat()
        result.append({'filename': path, 'parent_identity': _identity(parent),
                       'size_bytes': sizes[index] if index < len(sizes) else None})
    return result


def dispatch_options(options):
    active = _OUTPUTS.get()
    files, _sizes = logical_backup_volumes(options)
    if active is None or files != [row['filename'] for row in active]:
        raise RelationalClientError('Local backup requires its reviewed output reservations')
    result = copy.deepcopy(dict(options))
    if result.get('split_backup'):
        for row, reservation in zip(result['backup_volumes'], active):
            row['filename'] = reservation['native_filename']
    else:
        result['backup_file'] = active[0]['native_filename']
    return result


@contextmanager
def reserve(route, options, reviewed):
    """Retain original output inodes even if a pathname changes during gbak.

    Native Engine13 runs in this process and opens these Linux descriptor
    aliases. Requested files are visible during backup and remain on failure;
    they must never be interpreted as complete merely because they exist.
    """
    handles, records = [], []
    token = None
    created = 0
    try:
        current = selection(route, options)
        if current != reviewed:
            raise RelationalClientError('Local backup directories changed since review')
        for row in current:
            path = Path(row['filename'])
            parent = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            handles.append(parent)
            if _identity(os.fstat(parent)) != row['parent_identity']:
                raise RelationalClientError('Local backup directory changed before reservation')
            descriptor = os.open(path.name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=parent)
            handles.append(descriptor)
            created += 1
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise RelationalClientError('Local backup output is not a regular file')
            records.append({**row, 'identity': _identity(info), 'descriptor': descriptor,
                            'parent_descriptor': parent,
                            'native_filename': '/proc/self/fd/'+str(descriptor)})
        token = _OUTPUTS.set(records)
        yield records
    except (OSError, RelationalClientError) as original:
        error = RelationalClientError(
            'Local backup output reservation failed; inspect the reviewed filenames. '
            'Any files already reserved may be partial and are retained.')
        # Once even an empty output exists, never report "nothing changed".
        if token is None and created == 0:
            error.rejected = error.nothing_changed = True
            error.native_dispatched = error.automatic_retry = False
        if token is not None:
            raise
        raise error from original
    finally:
        if token is not None: _OUTPUTS.reset(token)
        for handle in reversed(handles): os.close(handle)


def observations(records):
    result = []
    for row in records:
        info = os.fstat(row['descriptor'])
        try:
            named = os.stat(Path(row['filename']).name, dir_fd=row['parent_descriptor'], follow_symlinks=False)
            matches = _identity(named) == row['identity'] and stat.S_ISREG(named.st_mode)
            parent_matches = _identity(Path(row['filename']).parent.stat()) == row['parent_identity']
        except OSError:
            matches = parent_matches = False
        result.append({'filename': row['filename'], 'identity': row['identity'],
            'bytes_observed': info.st_size, 'requested_path_still_names_output': matches and parent_matches,
            'output_inode_pinned': True, 'native_filename': row['native_filename'],
            'restore_verified': False})
    return result

"""Approved local physical backup output (nbackup), without overwriting files.

Native Firebird nbackup creates its destination with O_CREAT | O_EXCL and stores
the canonical backup filename in RDB$BACKUP_HISTORY for incremental chains.
Unlike gbak, passing a pre-opened /proc/self/fd alias is rejected natively with
337117230 ("File exists") and would record an ephemeral descriptor path in
RDB$BACKUP_HISTORY. We therefore pin and recheck the approved parent directory
via O_DIRECTORY | O_NOFOLLOW, verify destination absence before dispatch, rely
on native O_EXCL to prevent overwriting any raced file, and report honest
post-dispatch regular-file observations without claiming an OS rename fence.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import stat

from ...sdk import RelationalClientError
from .embedded import embedded_route


def _refused(message):
    error = RelationalClientError(message)
    error.rejected = error.nothing_changed = True
    error.native_dispatched = error.automatic_retry = False
    return error


def _identity(info):
    return {'device': str(info.st_dev), 'inode': str(info.st_ino)}


def selection(route, options, *, require_absent=True):
    filename = options.get('backup_file')
    if not isinstance(filename, str) or not filename.strip():
        raise _refused('Select a canonical absolute local physical backup filename')
    try:
        path = embedded_route({**route, 'database': filename})['database']
    except RelationalClientError as error:
        raise _refused(str(error)) from error
    if path != filename:
        raise _refused('Select a canonical absolute local physical backup filename')
    target = Path(path)
    if target == Path(route['database']):
        raise _refused('Physical backup output must differ from its source database')
    if require_absent and os.path.lexists(path):
        raise _refused('Local physical backup output already exists; select an unused filename')
    try:
        parent = target.parent.stat()
    except OSError as error:
        raise _refused('Approved local physical backup parent directory is unavailable') from error
    return [{'filename': path, 'parent_identity': _identity(parent)}]


@contextmanager
def execution(route, options, reviewed):
    """Verify parent directory identity and destination absence before nbackup."""
    handles, records = [], []
    dispatched = False
    try:
        current = selection(route, options, require_absent=True)
        if current != reviewed:
            raise _refused('Local physical backup directory changed since review')
        for row in current:
            path = Path(row['filename'])
            parent = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            handles.append(parent)
            if _identity(os.fstat(parent)) != row['parent_identity']:
                raise _refused('Local physical backup directory changed before dispatch')
            try:
                os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise _refused('Local physical backup output already exists; select an unused filename')
            records.append({**row, 'parent_descriptor': parent})
        dispatched = True
        yield records
    except (OSError, RelationalClientError) as original:
        if dispatched:
            raise
        if isinstance(original, RelationalClientError):
            raise
        raise _refused('Local physical backup directory check failed before dispatch') from original
    finally:
        for handle in reversed(handles):
            os.close(handle)


def observations(records):
    result = []
    for row in records:
        path = Path(row['filename'])
        try:
            named = os.stat(path.name, dir_fd=row['parent_descriptor'], follow_symlinks=False)
            regular = stat.S_ISREG(named.st_mode)
            observed_id = _identity(named) if regular else None
            observed_bytes = named.st_size if regular else None
            parent_matches = _identity(path.parent.stat()) == row['parent_identity']
        except OSError:
            regular = False
            observed_id = None
            observed_bytes = None
            parent_matches = False
        result.append({
            'filename': row['filename'],
            'identity': observed_id,
            'bytes_observed': observed_bytes,
            'requested_path_names_regular_file': regular and parent_matches,
            'parent_identity_unchanged': parent_matches,
            'output_inode_pinned': False,
            'native_exclusive_create': True,
            'rename_race_fenced': False,
            'restore_verified': False,
        })
    return result

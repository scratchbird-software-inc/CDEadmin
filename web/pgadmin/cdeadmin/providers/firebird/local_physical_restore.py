"""Reviewed local nbackup inputs and canonical native database destination."""
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
import copy
import hashlib
import os
from pathlib import Path
import stat

from ...sdk import RelationalClientError
from .backup_volumes import MAX_BACKUP_VOLUMES
from .embedded import embedded_route
from .restore_policy import physical_restore_policy

_INPUTS = ContextVar('firebird_local_physical_restore_inputs', default=None)


def _refused(message):
    error = RelationalClientError(message)
    error.rejected = error.nothing_changed = True
    error.native_dispatched = error.automatic_retry = False
    return error


def _identity(value):
    return {'device': str(value.st_dev), 'inode': str(value.st_ino)}


def _state(value):
    if not stat.S_ISREG(value.st_mode):
        raise _refused('Physical restore files must be regular files')
    return {**_identity(value), 'bytes': value.st_size,
            'mtime_ns': value.st_mtime_ns, 'ctime_ns': value.st_ctime_ns}


def _canonical(route, filename):
    if not isinstance(filename, str) or not filename.strip():
        raise _refused('Select canonical absolute application-host physical restore filenames')
    try:
        selected = embedded_route({**route, 'database': filename})['database']
    except RelationalClientError as error:
        raise _refused(str(error)) from error
    if selected != filename:
        raise _refused('Select canonical absolute application-host physical restore filenames')
    return Path(selected)


def _digest(descriptor):
    before = _state(os.fstat(descriptor))
    digest = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    while chunk := os.read(descriptor, 1024 * 1024):
        digest.update(chunk)
    os.lseek(descriptor, 0, os.SEEK_SET)
    if _state(os.fstat(descriptor)) != before:
        raise _refused('Physical backup input changed while its bytes were being reviewed')
    return {**before, 'sha256': digest.hexdigest()}


def _backup_filenames(options):
    raw = options.get('backup_files')
    if not isinstance(raw, list) or not raw or len(raw) > MAX_BACKUP_VOLUMES:
        raise _refused('Select an ordered non-empty physical backup file list')
    names = []
    for item in raw:
        if isinstance(item, Mapping) and set(item) <= {'value', '_id'}:
            item = item.get('value')
        if not isinstance(item, str) or not item.strip() or any(
                ch in item for ch in ('\x00', '\r', '\n')):
            raise _refused('Physical restore requires exact canonical backup filenames')
        names.append(item)
    return names


def _selection(route, options, hash_inputs):
    policy = physical_restore_policy('restore_physical', options)
    names = _backup_filenames(options)
    inputs, seen = [], set()
    for name in names:
        path = _canonical(route, name)
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            observed = _digest(descriptor) if hash_inputs else _state(os.fstat(descriptor))
        finally:
            os.close(descriptor)
        key = (observed['device'], observed['inode'])
        if key in seen or observed['bytes'] == 0:
            raise _refused('Physical restore requires distinct nonempty backup file inodes')
        seen.add(key)
        inputs.append({'filename': str(path), **observed})

    dest_path = _canonical(route, options.get('restore_database'))
    in_place = policy['mode'] == 'IN_PLACE'
    info = dest_path.lstat() if os.path.lexists(dest_path) else None
    state = _state(info) if info is not None else None
    if in_place:
        if state is None:
            raise _refused('In-place physical restore requires an existing approved offline database file')
        if (state['device'], state['inode']) in seen:
            raise _refused('Physical restore destination must not be one of its backup inputs')
        if options.get('confirmation') != str(dest_path):
            raise _refused('Confirm the exact destination database filename for in-place physical restore')
    elif state is not None:
        raise _refused('New physical restore will not overwrite an existing file; select an unused destination')

    outputs = [{
        'filename': str(dest_path),
        'existing': state,
        'parent_identity': _identity(dest_path.parent.stat()),
        'mode': policy['mode'],
    }]
    return {
        'inputs': inputs,
        'outputs': outputs,
        'in_place': in_place,
        'policy': policy,
    }


def selection(route, options, *, hash_inputs=True):
    try:
        return _selection(route, options, hash_inputs)
    except OSError as error:
        raise _refused('The approved physical backup files or destination directory are unavailable') from error


def metadata_selection(value):
    result = copy.deepcopy(value)
    for row in result.get('inputs', ()):
        row.pop('sha256', None)
    return result


@contextmanager
def execution(route, options, reviewed):
    """Pin reviewed physical backup inodes via /proc/self/fd; keep destination canonical."""
    descriptors, records = [], []
    token = None
    try:
        if selection(route, options, hash_inputs=False) != metadata_selection(reviewed):
            raise _refused('Physical restore inputs or destination changed since review')
        for row in reviewed['inputs']:
            descriptor = os.open(row['filename'], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            descriptors.append(descriptor)
            if {'filename': row['filename'], **_digest(descriptor)} != row:
                raise _refused('Physical backup input changed before restore dispatch')
            records.append({
                **row,
                'descriptor': descriptor,
                'native_filename': '/proc/self/fd/' + str(descriptor),
            })
        for row in reviewed['outputs']:
            dest = Path(row['filename'])
            parent = os.open(str(dest.parent), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            descriptors.append(parent)
            if _identity(os.fstat(parent)) != row['parent_identity']:
                raise _refused('Physical restore destination directory changed before dispatch')
            if reviewed['in_place']:
                try:
                    stat_now = os.stat(dest.name, dir_fd=parent, follow_symlinks=False)
                except OSError as error:
                    raise _refused('In-place physical restore destination disappeared before dispatch') from error
                if _state(stat_now) != row['existing']:
                    raise _refused('In-place physical restore destination changed before dispatch')
            else:
                try:
                    os.stat(dest.name, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    raise _refused('Physical restore destination appeared before dispatch')
        token = _INPUTS.set(records)
        yield records
    except (OSError, RelationalClientError) as error:
        if token is not None:
            raise
        if isinstance(error, RelationalClientError):
            raise
        raise _refused('Cannot retain the approved physical restore input and destination identities') from error
    finally:
        if token is not None:
            _INPUTS.reset(token)
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def dispatch_options(options):
    records = _INPUTS.get()
    names = _backup_filenames(options)
    if records is None or names != [row['filename'] for row in records]:
        raise _refused('Local physical restore requires its reviewed native input handles')
    result = copy.deepcopy(dict(options))
    result['backup_files'] = [row['native_filename'] for row in records]
    result.pop('confirmation', None)
    return result


def observations(records, reviewed):
    inputs = []
    for row in records:
        try:
            named = _identity(Path(row['filename']).lstat()) == {
                key: row[key] for key in ('device', 'inode')}
        except OSError:
            named = False
        inputs.append({
            'filename': row['filename'],
            'sha256': row['sha256'],
            'input_inode_pinned': True,
            'requested_path_still_names_input': named,
            'unchanged': _state(os.fstat(row['descriptor'])) == {
                key: row[key] for key in ('device', 'inode', 'bytes', 'mtime_ns', 'ctime_ns')},
        })
    outputs = []
    for row in reviewed['outputs']:
        path = Path(row['filename'])
        try:
            info = _state(path.lstat())
        except (OSError, RelationalClientError):
            info = None
        outputs.append({
            'filename': str(path),
            'mode': row['mode'],
            'observed_file': info,
            'native_filename_rechecked': True,
            'rename_race_fenced': False,
        })
    return {
        'backup_inputs': inputs,
        'database_files': outputs,
        'inputs_unchanged': all(row['unchanged'] for row in inputs),
        'data_readback_verified': False,
    }

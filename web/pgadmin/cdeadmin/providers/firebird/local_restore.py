"""Reviewed local gbak inputs and canonical native database destinations."""
from contextlib import contextmanager
from contextvars import ContextVar
import copy
import hashlib
import os
from pathlib import Path
import stat

from ...sdk import RelationalClientError
from .embedded import embedded_route
from .restore_files import logical_restore_files
from .backup_volumes import MAX_BACKUP_VOLUMES

_INPUTS = ContextVar('firebird_local_restore_inputs', default=None)


def _refused(message):
    error = RelationalClientError(message)
    error.rejected = error.nothing_changed = True
    error.native_dispatched = error.automatic_retry = False
    return error


def _identity(value):
    return {'device': str(value.st_dev), 'inode': str(value.st_ino)}


def _state(value):
    if not stat.S_ISREG(value.st_mode):
        raise _refused('Restore files must be regular files')
    return {**_identity(value), 'bytes': value.st_size,
            'mtime_ns': value.st_mtime_ns, 'ctime_ns': value.st_ctime_ns}


def _canonical(route, filename):
    selected = embedded_route({**route, 'database': filename})['database']
    if selected != filename:
        raise _refused('Select canonical absolute application-host restore filenames')
    return Path(selected)


def _digest(descriptor):
    before = _state(os.fstat(descriptor)); digest = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    while chunk := os.read(descriptor, 1024*1024): digest.update(chunk)
    os.lseek(descriptor, 0, os.SEEK_SET)
    if _state(os.fstat(descriptor)) != before:
        raise _refused('Backup input changed while its bytes were being reviewed')
    return {**before, 'sha256': digest.hexdigest()}


def _selection(route, options, hash_inputs):
    additional = options.get('additional_backup_files')
    if additional is None: additional = []
    if not isinstance(additional, list) or len(additional) >= MAX_BACKUP_VOLUMES:
        raise _refused('Select an ordered native backup volume list')
    names = [options.get('backup_file'), *additional]
    inputs, seen = [], set()
    for name in names:
        path = _canonical(route, name)
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try: observed = _digest(descriptor) if hash_inputs else _state(os.fstat(descriptor))
        finally: os.close(descriptor)
        key = (observed['device'], observed['inode'])
        if key in seen or observed['bytes'] == 0:
            raise _refused('Restore requires distinct nonempty backup volume inodes')
        seen.add(key); inputs.append({'filename': str(path), **observed})
    files, pages = logical_restore_files(options)
    replacing = options.get('replace_existing', False)
    if type(replacing) is not bool:
        raise _refused('Select create or explicit replacement for restore')
    if replacing and options.get('confirmation') != files[0]:
        raise _refused('Confirm the exact primary filename before replacing a database')
    outputs = []
    for index, name in enumerate(files):
        path = _canonical(route, name)
        info = path.lstat() if os.path.lexists(path) else None
        state = _state(info) if info is not None else None
        if state is not None:
            if (state['device'],state['inode']) in seen:
                raise _refused('A restored database must not overwrite a backup input')
            if index > 0 or not replacing:
                raise _refused('Existing restore destinations require explicit primary replacement; secondary files must be new')
        outputs.append({'filename': str(path), 'existing': state,
            'parent_identity': _identity(path.parent.stat()),
            'pages': pages[index] if index < len(pages) else None})
    return {'inputs': inputs, 'outputs': outputs, 'replace_existing': replacing}


def selection(route, options, *, hash_inputs=True):
    try: return _selection(route, options, hash_inputs)
    except OSError as error:
        raise _refused('The approved restore files or destination directories are unavailable') from error


def metadata_selection(value):
    result = copy.deepcopy(value)
    for row in result['inputs']: row.pop('sha256', None)
    return result


@contextmanager
def execution(route, options, reviewed):
    """Pin reviewed backup inodes; native database filenames stay canonical.

    A pinned input cannot be redirected by a filename replacement. Canonical
    native output paths are rechecked, but no external-process rename fence or
    native exclusive-access guarantee is implied.
    """
    descriptors, records = [], []
    token = None
    try:
        if selection(route, options, hash_inputs=False) != metadata_selection(reviewed):
            raise _refused('Restore inputs or destinations changed since review')
        for row in reviewed['inputs']:
            descriptor = os.open(row['filename'], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            descriptors.append(descriptor)
            if {'filename':row['filename'], **_digest(descriptor)} != row:
                raise _refused('Backup input changed before restore dispatch')
            records.append({**row, 'descriptor': descriptor,
                            'native_filename': '/proc/self/fd/'+str(descriptor)})
        for row in reviewed['outputs']:
            parent = os.open(str(Path(row['filename']).parent), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            descriptors.append(parent)
            if _identity(os.fstat(parent)) != row['parent_identity']:
                raise _refused('Restore destination directory changed before dispatch')
        token = _INPUTS.set(records)
        yield records
    except (OSError, RelationalClientError) as error:
        if token is not None: raise
        if isinstance(error, RelationalClientError): raise
        raise _refused('Cannot retain the approved restore input and destination identities') from error
    finally:
        if token is not None: _INPUTS.reset(token)
        for descriptor in reversed(descriptors): os.close(descriptor)


def dispatch_options(options):
    records = _INPUTS.get()
    names = [options.get('backup_file'), *(options.get('additional_backup_files') or [])]
    if records is None or names != [row['filename'] for row in records]:
        raise _refused('Local restore requires its reviewed native input handles')
    result = copy.deepcopy(dict(options))
    result['backup_file'] = records[0]['native_filename']
    result['additional_backup_files'] = [row['native_filename'] for row in records[1:]]
    result.pop('confirmation', None)
    return result


def observations(records, reviewed):
    inputs = []
    for row in records:
        try: named = _identity(Path(row['filename']).lstat()) == {key:row[key] for key in ('device','inode')}
        except OSError: named = False
        inputs.append({'filename': row['filename'], 'sha256': row['sha256'],
            'input_inode_pinned': True, 'requested_path_still_names_input': named,
            'unchanged': _state(os.fstat(row['descriptor'])) == {
                key:row[key] for key in ('device','inode','bytes','mtime_ns','ctime_ns')}})
    outputs = []
    for row in reviewed['outputs']:
        path = Path(row['filename'])
        try: info = _state(path.lstat())
        except (OSError, RelationalClientError): info = None
        outputs.append({'filename': str(path), 'observed_file': info,
                        'native_filename_rechecked': True, 'rename_race_fenced': False})
    return {'backup_inputs': inputs, 'database_files': outputs,
            'inputs_unchanged': all(row['unchanged'] for row in inputs),
            'data_readback_verified': False}

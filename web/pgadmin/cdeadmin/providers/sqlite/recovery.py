"""Native SQLite recovery admission and isolated, typed file reconstruction."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import sys
import time

from ...operations.fileio import private_file
from ...sdk.tool_process import observe_process
from ..embedded_route import contained_database


class RecoveryError(ValueError):
    pass


RECOVERY_SOURCES = {
    'sqlite3recover.c': 'bc56c1131dfdc979fd93a7e013856f4c2a98570c722c069600f6c66d2d47743f',
    'sqlite3recover.h': 'c088088d15af055304e931842f7c197024d46ff1b7077912ec42149e9fa4f9bb',
    'dbdata.c': '0a57eae22b51507c28f6c647fba00ccacd39b5aaf3393dfe9435fb04810a6e0e',
}


def options(value):
    if not isinstance(value, dict) or set(value) - {
            'output_path', 'source_isolated', 'include_freelist',
            'preserve_rowids', 'lost_and_found', 'timeout_seconds'}:
        raise RecoveryError('Select exact native SQLite recovery options')
    result = {'include_freelist': False, 'preserve_rowids': True,
              'lost_and_found': 'recovered_orphans', 'timeout_seconds': 3600, **deepcopy(value)}
    if result.get('source_isolated') is not True:
        raise RecoveryError('Confirm that writers to the source file are stopped or isolated')
    for name in ('include_freelist', 'preserve_rowids'):
        if type(result[name]) is not bool: raise RecoveryError('Recovery switches must be boolean')
    name = result['lost_and_found']
    if not isinstance(name, str) or not name or '\x00' in name or len(name.encode('utf8')) > 255:
        raise RecoveryError('Select a bounded native lost-and-found table name')
    timeout = result['timeout_seconds']
    if type(timeout) is not int or not 1 <= timeout <= 86400:
        raise RecoveryError('Recovery runtime must be one to 86400 seconds')
    output = result.get('output_path')
    if not isinstance(output, str) or not output or '\x00' in output or not Path(output).is_absolute():
        raise RecoveryError('Select an absolute new recovered database filename')
    return result


def host():
    return {'name': socket.getfqdn(), 'scope': 'application-host-filesystem', 'platform': sys.platform}


def installed_library():
    name = ('cdeadmin_sqlite_recovery.dll' if os.name == 'nt' else
            'libcdeadmin_sqlite_recovery.dylib' if sys.platform == 'darwin' else 'libcdeadmin_sqlite_recovery.so')
    candidates = [Path(prefix) / folder / name for prefix in dict.fromkeys((sys.prefix, sys.base_prefix))
                  for folder in ('bin', 'lib', 'DLLs')]
    candidates.append(Path(__file__).resolve().parents[2] / 'native' / name)
    return next((str(path) for path in candidates if path.is_file() and Path(str(path) + '.json').is_file()), '')


def identity(path):
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode): raise RecoveryError('Recovery input must be a regular file')
    return {'device': info.st_dev, 'inode': info.st_ino, 'size': str(info.st_size),
            'modified_ns': str(info.st_mtime_ns)}


def source_state(route, selected):
    source = Path(contained_database(route))
    if str(source) == ':memory:' or not source.is_file():
        raise RecoveryError('Select an existing registered SQLite file')
    source = source.resolve(strict=True)
    target = Path(contained_database({**route, 'database': selected['output_path']}))
    if target == source or os.path.lexists(target):
        raise RecoveryError('The recovered database must have a new, distinct filename')
    parent = target.parent.resolve(strict=True)
    if target.parent != parent or not parent.is_dir():
        raise RecoveryError('The recovered database directory changed')
    if any(os.path.lexists(str(target) + suffix) for suffix in ('-wal', '-journal', '-shm')):
        raise RecoveryError('The recovery destination has SQLite sidecars')
    files = {'': identity(source)}
    for suffix in ('-wal', '-journal'):
        path = Path(str(source) + suffix)
        if os.path.lexists(path): files[suffix] = identity(path)
    info = parent.stat()
    return {'path': str(source), 'files': files, 'output_path': str(target),
            'output_parent_identity': [info.st_dev, info.st_ino]}


def digest_file(path):
    checksum = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): checksum.update(block)
    return checksum.hexdigest()


def process(spec, directory, timeout, *, cancel=None, progress=None):
    worker = Path(__file__).with_name('recovery_worker.py')
    observed = observe_process([sys.executable, '-I', '-B', str(worker)],
        workspace=str(directory), environment=dict(os.environ),
        input_bytes=json.dumps(spec, ensure_ascii=True).encode('ascii'), input_stream=None,
        timeout=timeout, capture_limit=1024 * 1024, cancel_signal=cancel, progress=progress)
    try:
        result = json.loads(observed['stdout'])
        if not isinstance(result, dict): raise ValueError()
    except (ValueError, TypeError): result = {'completed': False, 'error_type': 'NativeRecoveryReplyUnavailable'}
    public = {key: value for key, value in observed.items() if key not in {'stdout', 'stderr'}}
    return result, public


def _runtime_range():
    from .native_helpers import HELPER_MINIMUM
    from .provider import PROFILE
    return {'floor': PROFILE.minimum_version,
            'minimum': HELPER_MINIMUM['recovery']}


def program(path, directory):
    if not isinstance(path, str) or not path:
        raise RecoveryError('SQLite recovery runtime is unavailable on this application host')
    library = Path(path).resolve(strict=True)
    if not library.is_file(): raise RecoveryError('Native SQLite recovery library is unavailable')
    checksum = digest_file(library)
    manifest = Path(str(library) + '.json')
    if manifest.stat().st_size > 16384: raise RecoveryError('Native recovery provenance is too large')
    provenance = json.loads(manifest.read_text(encoding='utf8'))
    from .native_helpers import built_against_admitted
    if (provenance.get('library_sha256') != checksum or
            not built_against_admitted('recovery', provenance.get('sqlite_version')) or
            provenance.get('adapter_abi') != 1 or
            any(provenance.get(name) != value for name, value in RECOVERY_SOURCES.items())):
        raise RecoveryError('Native SQLite recovery build provenance does not match the qualified profile')
    worker_sha = digest_file(Path(__file__).with_name('recovery_worker.py'))
    spec = {'action': 'probe', 'library': str(library), 'library_sha256': checksum, 'worker_sha256': worker_sha,
            'runtime_range': _runtime_range()}
    result, observed = process(spec, directory, 15)
    if observed['return_code'] != 0 or observed['cleanup_confirmed'] is not True or result.get('available') is not True:
        raise RecoveryError('The native SQLite recovery library is not usable with this SQLite runtime')
    return {**spec, 'native': result['native'], 'execution_host': host(),
            'provenance_sha256': digest_file(manifest), 'recovery_sources': RECOVERY_SOURCES,
            'worker_sha256': worker_sha}


def stage(source, directory, *, cancel, progress, deadline):
    original = Path(source['path']); image = directory / 'image.sqlite'; images = {}
    copied = 0; total = sum(int(value['size']) for value in source['files'].values())
    for suffix, expected in source['files'].items():
        path, destination = Path(str(original) + suffix), Path(str(image) + suffix)
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        try:
            actual = os.fstat(descriptor)
            if (not stat.S_ISREG(actual.st_mode) or
                    [actual.st_dev, actual.st_ino, str(actual.st_size), str(actual.st_mtime_ns)] !=
                    [expected['device'], expected['inode'], expected['size'], expected['modified_ns']]):
                raise RecoveryError('The reviewed SQLite source image changed')
            checksum = hashlib.sha256()
            with os.fdopen(descriptor, 'rb', closefd=False) as incoming, destination.open('xb') as output:
                private_file(destination)
                while True:
                    if cancel.is_set(): raise RecoveryError('SQLite recovery image capture was cancelled')
                    if time.monotonic() >= deadline: raise TimeoutError('SQLite recovery image capture timed out')
                    block = incoming.read(1024 * 1024)
                    if not block: break
                    output.write(block); checksum.update(block); copied += len(block)
                    progress({'stage': 'capturing-image', 'copied_bytes': str(copied), 'total_image_bytes': str(total)})
                output.flush(); os.fsync(output.fileno())
            if identity(path) != expected or digest_file(destination) != checksum.hexdigest():
                raise RecoveryError('SQLite source changed during image capture')
            images[suffix] = {'sha256': checksum.hexdigest(), **expected}
        finally:
            os.close(descriptor)
    # SHM is native derived state. The private worker recreates it from the WAL;
    # it is neither copied from nor written back to the registered source.
    for suffix in ('-wal', '-journal'):
        if os.path.lexists(str(original) + suffix) != (suffix in source['files']):
            raise RecoveryError('SQLite journal membership changed during image capture')
    return image, images


def recover(record, directory, *, cancel, progress):
    selected, source, runtime = record['options'], record['source'], record['program']
    deadline = time.monotonic() + selected['timeout_seconds']
    if host() != runtime['execution_host']:
        raise RecoveryError('SQLite recovery execution host changed')
    if (digest_file(runtime['library']) != runtime['library_sha256'] or
            digest_file(runtime['library'] + '.json') != runtime['provenance_sha256'] or
            digest_file(Path(__file__).with_name('recovery_worker.py')) != runtime['worker_sha256']):
        raise RecoveryError('The reviewed SQLite recovery runtime changed')
    if source_state(record['route'], selected) != source:
        raise RecoveryError('The reviewed SQLite source or output directory changed')
    image, images = stage(source, directory, cancel=cancel, progress=progress, deadline=deadline)
    target, progress_path = directory / 'recovered.sqlite', directory / 'progress.json'
    native_options = {key: selected[key] for key in ('include_freelist', 'preserve_rowids', 'lost_and_found')}
    def observed(event):
        values = {'stage': 'recovering', 'process': event}
        if progress_path.is_file():
            try:
                if progress_path.stat().st_size <= 4096:
                    values.update(json.loads(progress_path.read_text(encoding='utf8')))
            except (OSError, ValueError): pass
        progress(values)
    result, execution = process({'action': 'recover', 'library': runtime['library'],
        'library_sha256': runtime['library_sha256'], 'worker_sha256': runtime['worker_sha256'],
        'source': str(image), 'target': str(target),
        'progress_file': str(progress_path), 'options': native_options,
        'runtime_range': _runtime_range()}, directory,
        max(.01, deadline - time.monotonic()), cancel=cancel, progress=observed)
    result.update(process_observation=execution, source_images=images,
                  original_files_opened_read_only=True, automatic_retry=False)
    if (execution['return_code'] != 0 or execution['cleanup_confirmed'] is not True or
            execution['cancel_requested'] or execution['timed_out'] or result.get('completed') is not True):
        result['completed'] = False
        return result
    if result.get('native') != runtime['native'] or digest_file(target) != result.get('artifact_sha256'):
        raise RecoveryError('Native recovered artifact or runtime identity differs from its reply')
    private_file(target)
    with target.open('r+b') as stream: os.fsync(stream.fileno())
    return result

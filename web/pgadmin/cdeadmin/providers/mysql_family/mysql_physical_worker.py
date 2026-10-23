"""Standalone, private host-side XtraBackup jobs; native utilities own recovery."""
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
import uuid

try:
    import _cdeadmin_native_worker as host
except ModuleNotFoundError:
    from . import mysql_host_worker as host

Refused = host.Refused
VERSION = '9.7.1-rc1'
REVISION = 'b1c9c34183de95316d8889ea3d4cb31e31ffddc5'
MAX_FILES = 200000
MAX_OUTPUT = 128 * 1024


def public(value):
    if isinstance(value, list): return [public(item) for item in value]
    if isinstance(value, dict):
        return {**{key: public(item) for key, item in value.items() if key != 'files'},
            **({'file_count': len(value['files'])} if isinstance(value.get('files'), list) else {})}
    return value


def absolute(value):
    path = Path(host.text(value))
    if not path.is_absolute() or path.is_symlink():
        raise Refused('Select an absolute native path without a symbolic link')
    return path.resolve()


def root_directory(value, binding):
    root = absolute(value)
    data = absolute(binding['datadir'])
    if root in {Path(root.anchor), Path.home().resolve()} or root.is_relative_to(data) or data.is_relative_to(root):
        raise Refused('Physical recovery workspace must be separate from the active data directory and its ancestors')
    if root.exists():
        info = root.stat()
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise Refused('Physical workspace must be private to the authenticated OS account')
    return root


def job_id(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise Refused('Select an exact native physical job identity')
    return value


def host_scope(request, *, live=False):
    if live: return host.binding(request['binding'])
    binding = request['binding']
    if not isinstance(binding, dict) or set(binding) != {'server_uuid', 'hostname', 'datadir'}:
        raise Refused('Select the original physical source binding')
    job_id(binding['server_uuid'])
    if binding['hostname'] != socket.gethostname():
        raise Refused('The authenticated SSH host differs from this physical artifact host')
    return {'server_uuid': binding['server_uuid'], 'hostname': binding['hostname'],
        'datadir': str(absolute(binding['datadir'])), 'platform': sys.platform,
        'python_version': list(sys.version_info[:3]), 'execution_host_kind': 'database-server-ssh-host',
        'source_identity_scope': 'recorded_backup_source; live source not required'}


def read_json(path):
    with host.regular_stream(path) as stream:
        value = stream.read(32 * 1024 * 1024 + 1)
    if len(value) > 32 * 1024 * 1024:
        raise Refused('Native physical receipt exceeds its observation bound')
    return json.loads(value)


def metadata(path, maximum=1024 * 1024):
    with host.regular_stream(path) as stream:
        value = stream.read(maximum + 1)
    if len(value) > maximum:
        raise Refused('Native physical metadata exceeds its observation bound')
    return value.decode('utf8')


def properties(path):
    result = {}
    for line in metadata(path).splitlines():
        if not line.strip():
            continue
        key, separator, value = line.partition('=')
        if not separator or key.strip() in result:
            raise Refused('Native physical metadata has invalid or duplicate fields')
        result[key.strip()] = value.strip()
    return result


def manifest(directory):
    directory = absolute(str(directory))
    files = []
    for parent, dirs, names in os.walk(directory, followlinks=False):
        for name in dirs:
            if (Path(parent) / name).is_symlink():
                raise Refused('Physical artifact directories cannot contain symbolic links')
        for name in names:
            path = Path(parent) / name
            if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
                raise Refused('Physical artifacts must contain only regular files')
            before = path.stat()
            checksum = host.file_hash(path)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
                raise Refused('Physical artifact changed during observation')
            files.append({'path': str(path.relative_to(directory)), 'bytes': str(after.st_size), 'sha256': checksum})
            if len(files) > MAX_FILES:
                raise Refused('Physical artifact exceeds its file observation bound')
    return sorted(files, key=lambda item: item['path'])


def artifact(directory, *, prepared=None):
    checkpoint = properties(directory / 'xtrabackup_checkpoints')
    info = properties(directory / 'xtrabackup_info')
    tablespaces = read_json(directory / 'xtrabackup_tablespaces')
    # Native copy-back can recreate original external paths. This workflow
    # admits self-contained instances, rather than granting those paths.
    if tablespaces != {'version': 3, 'external_tablespaces': []}:
        raise Refused('External tablespaces require a separately reviewed physical path mapping')
    if (info.get('server_version') != '9.7.0' or info.get('tool_version') != VERSION or
            info.get('partial') != 'N' or info.get('incremental') != 'N' or
            info.get('compressed') != 'N' or info.get('encrypted') != 'N' or
            checkpoint.get('backup_type') not in {'full-backuped', 'full-prepared'}):
        raise Refused('Select an admitted complete, uncompressed full MySQL9.7.0 physical artifact')
    if prepared is not None and (checkpoint['backup_type'] == 'full-prepared') != prepared:
        raise Refused('Physical artifact preparation state differs from its selected operation')
    for key in ('from_lsn', 'to_lsn', 'last_lsn'):
        if not re.fullmatch(r'[0-9]+', checkpoint.get(key, '')):
            raise Refused('Native physical LSN metadata is unavailable')
    files = manifest(directory)
    return {'format': 'xtrabackup-9.7-full', 'checkpoint': checkpoint,
        'backup_uuid': info['uuid'], 'server_version': info['server_version'],
        'tool_version': info['tool_version'], 'binlog_info': metadata(directory / 'xtrabackup_binlog_info'),
        'files': files, 'manifest_sha256': host.digest(files), 'total_bytes': str(sum(int(item['bytes']) for item in files)),
        'prepared': checkpoint['backup_type'] == 'full-prepared', 'database_recovery_verified': False}


def executable(path, kind):
    path = absolute(path)
    if path.name != kind or not os.access(path, os.X_OK):
        raise Refused('Select the native ' + kind + ' executable')
    value = subprocess.run([str(path), '--no-defaults', '--version'], capture_output=True, timeout=15,
        env={**os.environ, 'LC_ALL': 'C'}, check=False)
    output = (value.stdout + value.stderr).decode('utf8', errors='replace')
    pattern = r'xtrabackup version 9\.7\.1-rc1\b.*revision id: b1c9c341' if kind == 'xtrabackup' else r'\b(?:Ver|Distrib)\s+9\.7\.0\b'
    if value.returncode or not re.search(pattern, output):
        raise Refused('The selected native ' + kind + ' does not match the admitted version/revision')
    return {'path': str(path), 'sha256': host.file_hash(path), 'version_output': output.strip()}


def inspection(request):
    if not sys.platform.startswith('linux'):
        raise Refused('The admitted XtraBackup backend requires a native Linux database host')
    binding = host_scope(request, live=request['phase'] == 'backup')
    root = root_directory(request['workspace'], binding)
    observed = {'host': binding, 'workspace': str(root), 'xtrabackup': executable(request['executable'], 'xtrabackup'),
        'release_status': 'RC1', 'source_revision': REVISION}
    phase = request['phase']
    for name, low, high in [('parallel', 1, 64), ('memory_bytes', 67108864, 17179869184), ('timeout_seconds', 1, 604800)]:
        if type(request.get(name)) is not int or not low <= request[name] <= high:
            raise Refused('Select bounded native physical ' + name)
    if phase == 'backup':
        observed['mysql'] = executable(request['mysql'], 'mysql')
        if type(request.get('sql_port')) is not int or not 1 <= request['sql_port'] <= 65535:
            raise Refused('Select the source TCP port reachable from the database host')
        host.text(request['sql_host'])
    elif phase in {'prepare', 'copy_back'}:
        source = root / job_id(request['input_job_id'])
        receipt = read_json(source / 'result.json')
        if (receipt.get('state') != 'native_returned' or receipt.get('return_code') != 0 or not receipt.get('artifact') or
                receipt.get('error_type') or receipt.get('process_termination_confirmed') is not True or
                receipt.get('credential_cleanup_confirmed') is not True):
            raise Refused('Select a completed verified native physical input')
        verified = artifact(source / 'artifact', prepared=phase == 'copy_back')
        if verified != receipt['artifact']:
            raise Refused('Physical input bytes changed after native publication')
        observed['input'] = {'job_id': request['input_job_id'], 'artifact': public(verified)}
    else:
        raise Refused('Select a native backup, prepare or isolated copy-back operation')
    return observed


def native_environment(directory):
    return {'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
        'LC_ALL': 'C', 'HOME': str(directory), 'TMPDIR': str(directory)}


def client_options(request, directory):
    credentials = request['database_credentials']
    if not isinstance(credentials, dict) or set(credentials) != {'user', 'password'}:
        raise Refused('Delegate the selected single-factor native database credential explicitly')
    def quote(value):
        if not isinstance(value, str) or '\x00' in value:
            raise Refused('Native client option text is invalid')
        return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t') + '"'
    path = directory / 'client.cnf'
    with path.open('x', encoding='utf8') as stream:
        host.private_file(path)
        stream.write('[client]\nuser=' + quote(credentials['user']) + '\npassword=' + quote(credentials['password']) +
            '\nhost=' + quote(request['sql_host']) + '\nport=' + str(request['sql_port']) + '\nprotocol=tcp\nssl-mode=REQUIRED\n')
    return path


def identity(request, observed, option_file, directory):
    # CURRENT_ROLE has a binary string type. Native JSON otherwise represents
    # it as an opaque base64 value, rather than the session's actual role text.
    source = "SELECT JSON_OBJECT('version',VERSION(),'server_uuid',@@server_uuid,'datadir',@@datadir,'authenticated_principal',CURRENT_USER(),'active_role',CAST(CURRENT_ROLE() AS CHAR CHARACTER SET utf8mb4))"
    response = subprocess.run([observed['mysql']['path'], '--defaults-file=' + str(option_file), '--batch', '--raw',
        '--skip-column-names', '--default-character-set=utf8mb4', '--execute=' + source],
        capture_output=True, timeout=15, cwd=directory, env=native_environment(directory), check=False)
    if response.returncode:
        raise Refused('Native source authentication or identity inspection failed')
    value = json.loads(response.stdout.decode('utf8'))
    expected = request['source_identity']
    differences = [key for key in ('version', 'server_uuid', 'authenticated_principal', 'active_role') if value.get(key) != expected.get(key)]
    if absolute(value['datadir']) != absolute(request['binding']['datadir']): differences.append('datadir')
    if differences:
        error = Refused('The native backup SQL peer differs from the reviewed source identity: ' + ', '.join(differences))
        error.observed_identity = value
        raise error
    return value


def finish(directory, value):
    host.save(directory / 'result.json', value)


def execute(directory):
    """Detached supervisor. It survives loss of the web worker or SSH reply."""
    directory = Path(directory)
    request = read_json(directory / 'request.json')
    value = {'state': 'native_dispatch', 'job_id': request['job_id'], 'input_digest': request['input_digest'],
        'automatic_retry': False, 'native_may_have_dispatched': False, 'process_termination_confirmed': False,
        'credential_cleanup_confirmed': False, 'supervisor_finished': False, 'started_at': time.time()}
    child = option_file = None
    try:
        observed = inspection(request)
        if observed != request['reviewed']:
            raise Refused('Native physical source, utility or artifact changed after review')
        phase = request['phase']; target = directory / 'artifact'
        if phase == 'backup':
            option_file = client_options(request, directory)
            value['sql_identity'] = identity(request, observed, option_file, directory)
            args = ['--defaults-file=' + str(option_file), '--backup', '--datadir=' + observed['host']['datadir'],
                '--target-dir=' + str(target), '--parallel=' + str(request['parallel'])]
        else:
            original = Path(observed['workspace']) / request['input_job_id'] / 'artifact'
            if phase == 'prepare':
                # Prepare mutates a private derived copy; the original base and
                # its dependency boundary remain immutable and independently usable.
                shutil.copytree(original, target)
                if public(artifact(target, prepared=False)) != observed['input']['artifact']:
                    raise Refused('Staged physical bytes differ from the selected immutable base')
                args = ['--no-defaults', '--prepare', '--target-dir=' + str(target), '--use-memory=' + str(request['memory_bytes'])]
            else:
                target.mkdir(mode=0o700)
                args = ['--no-defaults', '--copy-back', '--target-dir=' + str(original), '--datadir=' + str(target),
                    '--innodb-data-home-dir=' + str(target), '--innodb-undo-directory=' + str(target),
                    '--innodb-log-group-home-dir=' + str(target)]
        if (directory / 'cancel').exists():
            raise InterruptedError('Cancelled before native dispatch')
        value.update(native_may_have_dispatched=True, phase=phase)
        finish(directory, value)
        with (directory / 'stdout').open('xb') as stdout, (directory / 'stderr').open('xb') as stderr:
            host.private_file(directory / 'stdout'); host.private_file(directory / 'stderr')
            child = subprocess.Popen([observed['xtrabackup']['path'], *args], stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, cwd=directory, env=native_environment(directory), start_new_session=True)
            value['native_pid'] = child.pid
            finish(directory, value)
            deadline = time.monotonic() + request['timeout_seconds']
            while child.poll() is None:
                if (directory / 'cancel').exists() or time.monotonic() > deadline:
                    value['cancel_requested'] = (directory / 'cancel').exists()
                    value['timeout_reached'] = time.monotonic() > deadline
                    os.killpg(child.pid, signal.SIGTERM)
                    try: child.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL); child.wait(timeout=15)
                    break
                time.sleep(.1)
        value.update(state='native_returned', return_code=child.returncode,
            process_termination_confirmed=True, native_reply_observed=True, finished_at=time.time())
        # Native completion is a fact before hashing/metadata/cleanup can fail.
        finish(directory, value)
        if child.returncode == 0:
            if phase == 'copy_back':
                copied = manifest(target)
                value['restored_files'] = {'files': copied, 'manifest_sha256': host.digest(copied),
                    'total_bytes': str(sum(int(item['bytes']) for item in copied)), 'database_started': False,
                    'data_directory': str(target), 'database_recovery_verified': False}
            else:
                value['artifact'] = artifact(target, prepared=phase == 'prepare')
            if phase != 'backup' and public(artifact(original, prepared=phase == 'copy_back')) != observed['input']['artifact']:
                raise Refused('Original physical input changed during the native operation')
    except BaseException as error:
        if child is not None and child.poll() is None:
            try: os.killpg(child.pid, signal.SIGKILL); child.wait(timeout=15)
            except (ProcessLookupError, subprocess.TimeoutExpired): pass
        value.update(state=value['state'] if value.get('native_reply_observed') else 'unknown' if value['native_may_have_dispatched'] else 'not_dispatched',
            error_type=type(error).__name__, error_message=str(error) if isinstance(error, (Refused, InterruptedError)) else None,
            process_termination_confirmed=child is None or child.poll() is not None)
        if getattr(error, 'observed_identity', None) is not None:
            value['observed_sql_identity'] = error.observed_identity
    finally:
        # Invocation secrets are never part of a public receipt or retained
        # executable. A later observer can distinguish an incomplete cleanup.
        try:
            if option_file is not None: option_file.unlink(missing_ok=True)
            request['database_credentials'] = None
            host.save(directory / 'request.json', request)
            value['credential_cleanup_confirmed'] = True
        except Exception as error:
            value['credential_cleanup_error_type'] = type(error).__name__
        value.update(supervisor_finished=True, supervisor_finished_at=time.time())
        finish(directory, value)


def dispatch(request, launch_source=None):
    if not isinstance(request, dict) or request.get('schema') != 'cdeadmin.mysql-physical.v1':
        raise Refused('Select the native physical host protocol')
    action = request.get('action')
    if action == 'inspect':
        return inspection(request)
    binding = host_scope(request)
    root = root_directory(request['workspace'], binding)
    selected = job_id(request['job_id']); directory = root / selected
    if action in {'status', 'cancel', 'output'}:
        if not directory.is_dir() or directory.is_symlink():
            return {'state': 'unknown', 'remote_receipt_available': False, 'automatic_retry': False}
        record = read_json(directory / 'result.json')
        if record.get('input_digest') != request['input_digest']:
            raise Refused('Physical receipt belongs to another reviewed input')
        if action == 'cancel' and not record.get('process_termination_confirmed'):
            with (directory / 'cancel').open('ab') as stream: host.private_file(directory / 'cancel')
        if action == 'output':
            record = {'job_id': selected, 'input_digest': request['input_digest'], 'outputs': {}}
            for name in ('stdout', 'stderr'):
                path = directory / name
                if path.exists():
                    with host.regular_stream(path) as stream:
                        stream.seek(max(0, path.stat().st_size - MAX_OUTPUT))
                        record['outputs'][name] = stream.read(MAX_OUTPUT).decode('utf8', errors='replace')
        return public(record)
    if action != 'start' or launch_source is None:
        raise Refused('Native physical action is unavailable')
    if directory.exists():
        return dispatch({**request, 'action': 'status'})
    observed = inspection(request)
    if observed != request.get('reviewed'):
        raise Refused('Native physical inputs changed after review')
    root.mkdir(parents=True, exist_ok=True, mode=0o700); host.private_directory(root)
    directory.mkdir(mode=0o700); host.private_directory(directory)
    # This exclusive durable claim prevents retries, including a killed SSH
    # worker between claim and child launch. Missing admission stays unknown.
    finish(directory, {'state': 'claimed', 'job_id': selected, 'input_digest': request['input_digest'],
        'automatic_retry': False, 'process_termination_confirmed': False, 'credential_cleanup_confirmed': False})
    host.save(directory / 'request.json', request)
    path = directory / 'supervisor.py'
    with path.open('x', encoding='utf8') as stream:
        host.private_file(path); stream.write(launch_source)
        stream.flush(); os.fsync(stream.fileno())
    try:
        subprocess.Popen([sys.executable, '-u', str(path), str(directory)], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
            cwd=directory, env=native_environment(directory))
    except BaseException:
        request['database_credentials'] = None
        host.save(directory / 'request.json', request)
        finish(directory, {'state': 'not_dispatched', 'job_id': selected, 'input_digest': request['input_digest'],
            'automatic_retry': False, 'process_termination_confirmed': True, 'credential_cleanup_confirmed': True,
            'native_may_have_dispatched': False, 'supervisor_finished': True, 'error_type': 'supervisor_launch_failed'})
        raise
    return {'state': 'admitted', 'job_id': selected, 'input_digest': request['input_digest'],
        'automatic_retry': False, 'process_termination_confirmed': False}

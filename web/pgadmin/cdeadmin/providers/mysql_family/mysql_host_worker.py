"""Standalone host-side MySQL diagnostics, launched only by the pinned SSH port.

This module deliberately needs only the Python standard library and the
ScratchRobin file-permission helper injected by the transport. It can run on a
database host without installing the web application or its database drivers.
"""
import base64
import configparser
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid

try:
    from _cdeadmin_native_fileio import durable_replace, private_directory, private_file
except ModuleNotFoundError:
    from ...operations.fileio import durable_replace, private_directory, private_file

MAX_OUTPUT = 512 * 1024


class Refused(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def text(value):
    if not isinstance(value, str) or not value or '\x00' in value or len(value.encode('utf8')) > 32768:
        raise Refused('Select bounded native host text')
    return value


def regular(path):
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise Refused('The selected native host file is not regular')
    return info


def file_hash(path):
    regular(path)
    value = hashlib.sha256()
    with path.open('rb') as stream:
        while True:
            data = stream.read(1024 * 1024)
            if not data:
                break
            value.update(data)
    return value.hexdigest()


def binding(value):
    if not isinstance(value, dict) or set(value) != {'server_uuid', 'hostname', 'datadir'}:
        raise Refused('Select an observed native database host binding')
    if str(uuid.UUID(value['server_uuid'])) != value['server_uuid']:
        raise Refused('The native source UUID is unavailable')
    hostname = socket.gethostname()
    expected = text(value['hostname'])
    matching = hostname.casefold() == expected.casefold() if os.name == 'nt' else hostname == expected
    if not matching:
        raise Refused('The authenticated SSH host is not the observed database host')
    directory = Path(text(value['datadir']))
    if not directory.is_absolute():
        raise Refused('The observed native data directory is not absolute on this SSH host')
    directory = directory.resolve(strict=True)
    auto = directory / 'auto.cnf'
    regular(auto)
    with auto.open('r', encoding='utf8') as stream:
        data = stream.read(65537)
    if len(data) > 65536:
        raise Refused('Native instance identity metadata exceeds its observation bound')
    parsed = configparser.ConfigParser(interpolation=None)
    parsed.read_string(data)
    if parsed.get('auto', 'server-uuid', fallback=None) != value['server_uuid']:
        raise Refused('The authenticated SSH host does not contain the selected native instance')
    return {'server_uuid': value['server_uuid'], 'hostname': hostname, 'datadir': str(directory),
            'platform': sys.platform, 'python_version': list(sys.version_info[:3]),
            'execution_host_kind': 'database-server-ssh-host'}


def environment(executable, workspace):
    if os.name == 'nt':
        root = os.environ.get('SystemRoot') or os.environ.get('SYSTEMROOT')
        if not root:
            raise Refused('Native Windows host execution requires SystemRoot')
        return {'SYSTEMROOT': root, 'WINDIR': root, 'USERPROFILE': str(workspace),
                'TEMP': str(workspace), 'TMP': str(workspace),
                'PATH': os.pathsep.join((str(executable.parent), str(Path(root) / 'System32'), root))}
    locale = 'C' if sys.platform == 'darwin' else 'C.UTF-8'
    return {'LANG': locale, 'LC_ALL': locale, 'HOME': str(workspace),
            'TMPDIR': str(workspace), 'PATH': os.pathsep.join((str(executable.parent), os.defpath))}


def process(executable, arguments, workspace, timeout):
    started = time.time()
    child = subprocess.Popen([str(executable), *arguments], cwd=str(workspace),
        env=environment(executable, workspace), stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
    observations = {}
    def read(name, stream):
        kept = bytearray(); total = 0; checksum = hashlib.sha256()
        try:
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    break
                total += len(chunk); checksum.update(chunk)
                kept.extend(chunk[:max(0, MAX_OUTPUT - len(kept))])
        finally:
            stream.close()
            observations[name] = {'base64': base64.b64encode(kept).decode('ascii'),
                'total_bytes': str(total), 'sha256': checksum.hexdigest(), 'truncated': total > len(kept)}
    readers = [threading.Thread(target=read, args=(name, stream), daemon=True)
               for name, stream in (('stdout', child.stdout), ('stderr', child.stderr))]
    for reader in readers:
        reader.start()
    timed_out = False
    try:
        child.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True; child.kill(); child.wait()
    for reader in readers:
        reader.join(timeout=5)
    return {'return_code': child.returncode, 'timed_out': timed_out,
            'streams_closed': not any(reader.is_alive() for reader in readers),
            'outputs': observations, 'started_at': started, 'finished_at': time.time(),
            'native_process_termination_observed': child.returncode is not None}


def inspect(request, expected=None):
    host = binding(request['binding'])
    selected = text(request.get('executable', 'mysqld'))
    resolved = shutil.which(selected)
    if resolved is None:
        raise Refused('The selected native mysqld executable is unavailable on this SSH host')
    executable = Path(resolved).resolve(strict=True)
    if executable.name.lower() not in {'mysqld', 'mysqld.exe'}:
        raise Refused('Select the native mysqld executable')
    checksum = file_hash(executable)
    config = request.get('configuration_file')
    configuration = None
    if config is not None:
        path = Path(text(config))
        if not path.is_absolute():
            raise Refused('Select an absolute native configuration filename')
        path = path.resolve(strict=True)
        configuration = {'path': str(path), 'sha256': file_hash(path)}
    if expected is not None and (host != expected.get('host') or
            str(executable) != expected.get('program', {}).get('path') or
            checksum != expected.get('program', {}).get('sha256') or
            configuration != expected.get('configuration')):
        raise Refused('The native host, executable or configuration changed after review')
    with tempfile.TemporaryDirectory(prefix='scratchrobin-mysql-version-') as temporary:
        version = process(executable, ['--no-defaults', '--version'], Path(temporary), 15)
    output = b''.join(base64.b64decode(version['outputs'].get(key, {}).get('base64', '')) for key in ('stdout', 'stderr')).decode('utf8', errors='replace')
    import re
    if version['return_code'] != 0 or not re.search(r'\bVer\s+9\.7\.0(?:\s|[-(])', output):
        raise Refused('Select the native MySQL9.7.0 mysqld on this database host')
    return {'host': host, 'program': {'path': str(executable), 'sha256': checksum, 'version_output': output.strip()},
            'configuration': configuration, 'included_configuration_files_attested': False}


def save(path, value):
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf8', dir=str(path.parent), delete=False) as stream:
        temporary = Path(stream.name); private_file(temporary)
        json.dump(value, stream, ensure_ascii=True); stream.flush(); os.fsync(stream.fileno())
    durable_replace(temporary, path)


def dispatch(request):
    if not isinstance(request, dict) or request.get('schema') != 'cdeadmin.mysql-native-host.v1':
        raise Refused('Select the native MySQL host protocol')
    action = request.get('action')
    if action == 'inspect':
        return inspect(request)
    if action not in {'validate_config', 'status'}:
        raise Refused('The native MySQL host action is unavailable')
    host = binding(request['binding'])
    root = Path(text(request['workspace']))
    if not root.is_absolute():
        raise Refused('Select an absolute private host workspace')
    root = root.resolve()
    if root in {Path(root.anchor), Path.home().resolve()} or root.is_relative_to(Path(host['datadir'])):
        raise Refused('Select a bounded host workspace separate from the active data directory')
    job_id = text(request['job_id'])
    if str(uuid.UUID(job_id)) != job_id:
        raise Refused('Select an exact native host job identity')
    directory = root / job_id; receipt = directory / 'result.json'
    expected = text(request['input_digest'])
    unavailable = {'state': 'unknown', 'job_id': job_id, 'input_digest': expected,
                   'remote_receipt_available': False, 'automatic_retry': False}
    if action == 'status' or directory.exists():
        if not receipt.is_file():
            return unavailable
        value = json.loads(receipt.read_text(encoding='utf8'))
        if value.get('input_digest') != expected:
            raise Refused('The remote host receipt belongs to another reviewed input')
        return value
    observed = inspect(request, request.get('reviewed', {}))
    if observed != request.get('reviewed'):
        raise Refused('The native host, executable or configuration changed after review')
    timeout = request.get('timeout_seconds', 60)
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise Refused('Select a native diagnostic runtime from 1 through 3600 seconds')
    root.mkdir(parents=True, exist_ok=True); private_directory(root)
    try:
        directory.mkdir(mode=0o700)
    except FileExistsError:
        return unavailable
    private_directory(directory)
    value = {'state': 'native_dispatch', 'job_id': job_id, 'input_digest': expected,
             'observation': observed, 'automatic_retry': False, 'remote_database_mutation': False,
             'validation_scope': 'native mysqld configuration check; not server readiness or upgrade acceptance'}
    save(receipt, value)
    configuration = observed['configuration']
    arguments = ['--defaults-file=' + configuration['path']] if configuration else ['--no-defaults']
    result = process(Path(observed['program']['path']), [*arguments, '--validate-config'], directory, timeout)
    value.update(state='native_process_returned', result=result)
    save(receipt, value)
    return value

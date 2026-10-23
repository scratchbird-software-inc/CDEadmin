"""Private native utility receipts owned independently of a web worker."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import time
import uuid

import psutil

from ..operations.fileio import durable_replace, private_directory, private_file


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path = Path(path)
    temporary = path.with_name('.' + path.name + '-' + uuid.uuid4().hex)
    with temporary.open('x', encoding='utf8') as stream:
        private_file(temporary)
        json.dump(value, stream, ensure_ascii=True, allow_nan=False)
        stream.flush(); os.fsync(stream.fileno())
    durable_replace(temporary, path)


def directory(workspace, name):
    if not isinstance(name, str) or re.fullmatch(r'[a-z][a-z0-9-]{0,63}', name) is None:
        raise ValueError('Invalid durable native utility name')
    return Path(workspace) / ('.cdeadmin-tool-' + name)


def host():
    return {'hostname': socket.gethostname(), 'platform': sys.platform, 'boot_time': psutil.boot_time()}


def stage_input(path,workspace,root):
    """Own regular stdin bytes before handing their descriptor to a guardian."""
    path=Path(path)
    if not path.resolve(strict=True).is_relative_to(Path(workspace).resolve()):raise ValueError('Native input escapes its workspace')
    descriptor=os.open(path,os.O_RDONLY|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0))
    target=root/'stdin.bin';digest=hashlib.sha256();size=0
    with os.fdopen(descriptor,'rb') as incoming:
        before=os.fstat(incoming.fileno())
        if not stat.S_ISREG(before.st_mode):raise ValueError('Native input is not a regular file')
        with target.open('xb') as outgoing:
            private_file(target)
            while data:=incoming.read(1024*1024):outgoing.write(data);digest.update(data);size+=len(data)
            outgoing.flush();os.fsync(outgoing.fileno())
        after=os.fstat(incoming.fileno())
        if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns) or size!=before.st_size:
            target.unlink();raise ValueError('Native input changed during handoff')
    return {'path':str(target),'bytes':str(size),'sha256':digest.hexdigest()}


def observe(workspace, reference, expected_executable_sha256):
    """Return sanitized facts; never dispatch, retry or infer database finality."""
    if not isinstance(reference, dict) or set(reference) != {'name', 'nonce', 'request_sha256', 'host'}:
        raise ValueError('The durable native utility reference is unavailable')
    root = directory(workspace, reference['name'])
    if root.is_symlink() or not root.is_dir() or root.resolve().parent != Path(workspace).resolve():
        raise ValueError('The durable native utility directory changed')
    intent_path = root / 'request.json'
    if intent_path.is_symlink() or sha(intent_path) != reference['request_sha256']:
        raise ValueError('The durable native utility request changed')
    intent = json.loads(intent_path.read_text())
    if (intent['nonce'] != reference['nonce'] or intent['host'] != reference['host'] or
            intent['executable_sha256'] != expected_executable_sha256 or any(
                intent['host'].get(key) != host().get(key) for key in ('hostname', 'platform'))):
        raise ValueError('Durable native utility identity or execution host changed')
    path = root / 'result.json'
    if not path.exists():
        return {'complete': False, 'cleanup_confirmed': None, 'native_outcome_inferred': False}
    if path.is_symlink() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('The durable native utility receipt is unsafe')
    result = json.loads(path.read_text())
    if result.get('nonce') != reference['nonce'] or result.get('request_sha256') != reference['request_sha256']:
        raise ValueError('The durable native utility receipt belongs to another invocation')
    native = result.get('observation')
    return {'complete': True, 'cleanup_confirmed': native.get('cleanup_confirmed') is True if isinstance(native, dict) else True if result.get('native_may_have_dispatched') is False else None,
            'return_code': native.get('return_code') if isinstance(native, dict) else None,
            'native_outcome_inferred': False, 'receipt_sha256': sha(path),
            'credential_file_cleanup_confirmed': result.get('credential_file_cleanup_confirmed') is True,
            'input_file_cleanup_confirmed': result.get('input_file_cleanup_confirmed') is True if intent.get('input_file') else True,
            'native_may_have_dispatched':result.get('native_may_have_dispatched'),
            'native_process_identity': {'pid': native.get('pid'), 'process_create_time': native.get('process_create_time')}
                if isinstance(native, dict) else None,
            'supervision_error_type': result.get('error_type')}


def cancel(workspace, reference, expected_executable_sha256):
    result = observe(workspace, reference, expected_executable_sha256)
    if not result['complete']:
        write(directory(workspace, reference['name']) / 'cancel.json', {'nonce': reference['nonce']})
    return {**result, 'cancellation_requested': not result['complete']}


def run(command, *, workspace, environment, timeout, capture_limit, name,
        credential_file=None, input_path=None, cancel_signal=None, progress=None, handoff=None):
    """A detached guardian owns one invocation, its pipes and credential cleanup."""
    root = directory(workspace, name)
    root.mkdir(mode=0o700, exist_ok=False); private_directory(root)
    helper = Path(__file__).with_name('tool_guardian.py')
    process_helper = Path(__file__).with_name('tool_process.py')
    file_helper = Path(__file__).parent.parent / 'operations' / 'fileio.py'
    input_file=stage_input(input_path,workspace,root) if input_path is not None else None
    intent = {'nonce': str(uuid.uuid4()), 'command': command, 'workspace': str(workspace),
        'input_file':input_file,
        'environment': environment, 'timeout': timeout, 'capture_limit': capture_limit,
        'credential_file': str(credential_file) if credential_file is not None else None,
        'host': host(), 'executable_sha256': sha(command[0]),
        'helpers': {str(path): sha(path) for path in (helper, process_helper, file_helper)}}
    write(root / 'request.json', intent)
    reference = {'name': name, 'nonce': intent['nonce'], 'request_sha256': sha(root / 'request.json'), 'host': intent['host']}
    # Persist the recovery reference before the guardian can dispatch anything.
    if progress is not None: progress({'durable_tool': reference})
    options = {'start_new_session': True} if os.name != 'nt' else {
        'creationflags': subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    guardian_environment = {key: os.environ[key] for key in ('SYSTEMROOT', 'SystemRoot', 'WINDIR',
        'LD_LIBRARY_PATH', 'DYLD_LIBRARY_PATH', 'LANG', 'LC_ALL') if key in os.environ}
    process = subprocess.Popen([sys.executable, '-I', str(helper), str(root), reference['request_sha256']],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=guardian_environment, close_fds=True, **options)
    if handoff is not None: handoff()
    last_progress = None
    while True:
        if cancel_signal is not None and cancel_signal.is_set() and not (root / 'cancel.json').exists():
            write(root / 'cancel.json', {'nonce': reference['nonce']})
        result_path = root / 'result.json'
        if result_path.exists():
            observed = observe(workspace, reference, intent['executable_sha256'])
            if observed['complete']:
                result = json.loads(result_path.read_text())
                native = result.get('observation')
                if not isinstance(native, dict):
                    error = RuntimeError('Durable native utility supervision failed')
                    error.durable_tool = reference
                    raise error
                native['stdout'] = base64.b64decode(native['stdout'], validate=True)
                native['stderr'] = base64.b64decode(native['stderr'], validate=True)
                native['durable_tool'] = reference
                native['credential_file_cleanup_confirmed']=observed['credential_file_cleanup_confirmed']
                native['input_file_cleanup_confirmed']=observed['input_file_cleanup_confirmed']
                try: process.wait(timeout=1)
                except subprocess.TimeoutExpired: pass
                return native
        if process.poll() is not None:
            # The guardian publishes before exiting. Its final rename can land
            # between our first existence check and poll observing that exit.
            if result_path.exists():
                continue
            # A guardian without its durable final receipt is unknown. PID
            # absence is deliberately not converted into utility cleanup.
            error = RuntimeError('Durable native utility guardian exited without a final receipt')
            error.durable_tool = reference
            raise error
        path = root / 'progress.json'
        if progress is not None and path.exists():
            value = path.read_bytes()
            if value != last_progress:
                last_progress = value
                event = json.loads(value)
                if event.get('nonce') == reference['nonce']:
                    try: progress(event['observation'])
                    except Exception: pass  # The guardian retains its own facts.
        time.sleep(.05)

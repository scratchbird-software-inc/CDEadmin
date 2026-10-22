"""Standalone native utility supervisor; intentionally imports no web app."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import threading
import uuid


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path, expected):
    if sha(path) != expected: raise ValueError('Native supervision helper changed')
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    if sha(path) != expected: raise ValueError('Native supervision helper changed during admission')
    return result


def main(root, expected):
    root = Path(root)
    request = root / 'request.json'
    if request.is_symlink() or sha(request) != expected: raise ValueError('Native supervision request changed')
    intent = json.loads(request.read_text())
    own = Path(__file__).resolve()
    if sha(own) != intent['helpers'].get(str(own)): raise ValueError('Native guardian changed')
    files_path = own.parent.parent / 'operations' / 'fileio.py'
    files = module('cdeadmin_guardian_fileio', files_path, intent['helpers'][str(files_path)])
    def write(path, value):
        temporary = path.with_name('.' + path.name + '-' + uuid.uuid4().hex)
        with temporary.open('x', encoding='utf8') as stream:
            files.private_file(temporary); json.dump(value, stream, ensure_ascii=True, allow_nan=False)
            stream.flush(); os.fsync(stream.fileno())
        files.durable_replace(temporary, path)
    process_path = own.with_name('tool_process.py')
    processes = module('cdeadmin_guardian_process', process_path, intent['helpers'][str(process_path)])
    descriptor = os.open(root / 'guardian.lock', os.O_RDWR | os.O_CREAT, 0o600)
    try:
        with files.exclusive_file_lock(descriptor, blocking=False):
            # A completed or previously admitted guardian is never relaunched.
            if (root / 'started.json').exists() or (root / 'result.json').exists():
                raise ValueError('This native invocation already has a guardian')
            write(root / 'started.json', {'nonce': intent['nonce'], 'request_sha256': expected, 'guardian_pid': os.getpid()})
            result = {'nonce': intent['nonce'], 'request_sha256': expected, 'credential_file_cleanup_confirmed': False}
            class Cancellation:
                def is_set(self):
                    path = root / 'cancel.json'
                    return path.exists() and json.loads(path.read_text()).get('nonce') == intent['nonce']
                def wait(self, timeout):
                    threading.Event().wait(timeout)
                    return self.is_set()
            try:
                if sha(intent['command'][0]) != intent['executable_sha256']:
                    raise ValueError('Native executable changed before guardian dispatch')
                observed = processes.observe_process(intent['command'], workspace=intent['workspace'],
                    environment=intent['environment'], input_bytes=b'', input_stream=None,
                    timeout=intent['timeout'], capture_limit=intent['capture_limit'], cancel_signal=Cancellation(),
                    progress=lambda event: write(root / 'progress.json', {'nonce': intent['nonce'], 'observation': event}))
                observed['stdout'] = base64.b64encode(observed['stdout']).decode('ascii')
                observed['stderr'] = base64.b64encode(observed['stderr']).decode('ascii')
                result['observation'] = observed
            except BaseException as error:
                result['error_type'] = type(error).__name__
                observed = getattr(error, 'observation', None)
                if observed is not None:
                    for key in ('stdout', 'stderr'): observed[key] = base64.b64encode(observed[key]).decode('ascii')
                    result['observation'] = observed
            finally:
                try:
                    if intent['credential_file'] is not None:
                        path = Path(intent['credential_file'])
                        if path.parent.resolve() != Path(intent['workspace']).resolve() or path.is_symlink():
                            raise ValueError('Native credential cleanup scope changed')
                        if path.exists():
                            with path.open('r+b') as stream:
                                stream.write(b'\x00' * path.stat().st_size); stream.flush(); os.fsync(stream.fileno())
                            path.unlink()
                    result['credential_file_cleanup_confirmed'] = True
                except Exception as error: result['credential_cleanup_error_type'] = type(error).__name__
                write(root / 'result.json', result)
    finally: os.close(descriptor)


if __name__ == '__main__':
    main(*sys.argv[1:])

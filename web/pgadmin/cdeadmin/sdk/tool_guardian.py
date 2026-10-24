"""Standalone native utility supervisor; intentionally imports no web app."""
import base64
import hashlib
import importlib.util
import json
import os
import socket
import stat
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
            result = {'nonce': intent['nonce'], 'request_sha256': expected, 'credential_file_cleanup_confirmed': False,
                'input_file_cleanup_confirmed':intent.get('input_file') is None,'native_may_have_dispatched':False}
            input_stream=None;reservation=None
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
                selected_reservation=intent.get('endpoint_reservation')
                if selected_reservation is not None:
                    fd=selected_reservation['fd'];facts=os.fstat(fd)
                    if os.name!='posix' or (facts.st_dev,facts.st_ino)!=(selected_reservation['device'],selected_reservation['inode']):
                        raise ValueError('Native endpoint reservation changed before dispatch')
                    reservation=socket.socket(fileno=fd)
                    if reservation.family!=socket.AF_INET or list(reservation.getsockname())!=selected_reservation['address'] or reservation.getsockname()[0]!='127.0.0.1' or not reservation.getsockopt(socket.SOL_SOCKET,socket.SO_ACCEPTCONN):
                        raise ValueError('Native endpoint reservation is not the original listener')
                selected=intent.get('input_file')
                if selected is not None:
                    path=Path(selected['path'])
                    if path!=root/'stdin.bin' or path.is_symlink():raise ValueError('Native input handoff scope changed')
                    input_descriptor=os.open(path,os.O_RDONLY|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0))
                    input_stream=os.fdopen(input_descriptor,'rb');digest=hashlib.sha256();size=0
                    if not stat.S_ISREG(os.fstat(input_stream.fileno()).st_mode):raise ValueError('Native input handoff is not regular')
                    while data:=input_stream.read(1024*1024):digest.update(data);size+=len(data)
                    if str(size)!=selected['bytes'] or digest.hexdigest()!=selected['sha256']:raise ValueError('Native input bytes changed after handoff')
                    input_stream.seek(0)
                result['native_may_have_dispatched']=True
                observed = processes.observe_process(intent['command'], workspace=intent['workspace'],
                    environment=intent['environment'], input_bytes=b'', input_stream=input_stream,
                    timeout=intent['timeout'], capture_limit=intent['capture_limit'], cancel_signal=Cancellation(),
                    inherited_fds=() if reservation is None else (reservation.fileno(),),
                    guardian_parent=os.getpid() if intent.get('kernel_policy')=='linux-parent-death-kill-v1' else None,
                    progress=lambda event: write(root / 'progress.json', {'nonce': intent['nonce'], 'observation': event}))
                observed['endpoint_reservation_inherited']=reservation is not None and observed.get('started') is True
                observed['stdout'] = base64.b64encode(observed['stdout']).decode('ascii')
                observed['stderr'] = base64.b64encode(observed['stderr']).decode('ascii')
                result['observation'] = observed
            except BaseException as error:
                result['error_type'] = type(error).__name__
                observed = getattr(error, 'observation', None)
                if observed is not None:
                    observed['endpoint_reservation_inherited']=reservation is not None and observed.get('started') is True
                    for key in ('stdout', 'stderr'): observed[key] = base64.b64encode(observed[key]).decode('ascii')
                    result['observation'] = observed
            finally:
                if input_stream is not None:input_stream.close()
                if reservation is not None:reservation.close()
                try:
                    if intent.get('input_file') and (result['native_may_have_dispatched'] is False or (result.get('observation') or {}).get('cleanup_confirmed') is True):
                        path=root/'stdin.bin'
                        if path.is_symlink():raise ValueError('Native input cleanup scope changed')
                        path.unlink(missing_ok=True);result['input_file_cleanup_confirmed']=True
                except Exception as error:result['input_cleanup_error_type']=type(error).__name__
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

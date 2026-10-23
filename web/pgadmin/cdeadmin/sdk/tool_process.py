"""Bounded native process observations; database finality remains provider-owned."""
import os
import subprocess
import threading
import time

import psutil


class ToolProcessFailure(RuntimeError):
    def __init__(self, observation):
        super().__init__('Native process output supervision could not be started')
        self.observation = observation


def _stop_owned_process(process, identity):
    """Stop this observed process tree without targeting a reused native PID."""
    if process.poll() is not None:
        return True
    try:
        owner = psutil.Process(process.pid)
        if identity is None:
            process.kill(); process.wait(timeout=3)
            return False
        if owner.create_time() != identity:
            return False
        children = owner.children(recursive=True)
        # psutil also checks each captured process's creation identity on kill.
        for child in reversed(children):
            try: child.kill()
            except psutil.NoSuchProcess: pass
        try: owner.kill()
        except psutil.NoSuchProcess: pass
        _gone, alive = psutil.wait_procs(children, timeout=2)
        process.wait(timeout=3)
        return not any(item.is_running() and item.status() not in {psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD} for item in alive)
    except (psutil.Error, OSError, subprocess.TimeoutExpired):
        try:
            process.kill(); process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            pass
        return False


def observe_process(command, *, workspace, environment, input_bytes, input_stream,
                    timeout, capture_limit, cancel_signal=None, progress=None,inherited_fds=()):
    """Drain both streams with bounded memory and report numeric live progress."""
    if cancel_signal is not None and cancel_signal.is_set():
        return {'started':False, 'return_code':None, 'stdout':b'', 'stderr':b'',
                'stdout_bytes':0, 'stderr_bytes':0, 'cancel_requested':True,
                'timed_out':False, 'cleanup_confirmed':True, 'elapsed_seconds':0}
    started = time.monotonic()
    options={}
    if inherited_fds:
        if os.name!='posix':raise ValueError('Native endpoint descriptor inheritance requires POSIX')
        options['pass_fds']=tuple(inherited_fds)
    process = subprocess.Popen(command, cwd=workspace, env=environment,
        stdin=input_stream if input_stream is not None else subprocess.PIPE if input_bytes else subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, close_fds=True, bufsize=0,**options)
    try:
        identity = psutil.Process(process.pid).create_time()
    except psutil.Error:
        identity = None
    buffers = {'stdout':bytearray(), 'stderr':bytearray()}
    counts = {'stdout':0, 'stderr':0}
    failures = []
    lock = threading.Lock()

    def read(stream, name):
        try:
            while True:
                data = os.read(stream.fileno(), 65536)
                if not data:break
                with lock:
                    counts[name] += len(data)
                    available = max(0, capture_limit - len(buffers[name]))
                    buffers[name].extend(data[:available])
        except (OSError, ValueError):
            with lock:failures.append(name)

    threads = [threading.Thread(target=read, args=(stream,name), daemon=True)
               for stream,name in ((process.stdout,'stdout'),(process.stderr,'stderr'))]
    def start_thread(thread):
        try:
            thread.start()
        except Exception as error:
            cleanup = _stop_owned_process(process, identity)
            for reader in threads:
                if reader.ident is not None:reader.join(timeout=2)
            for stream in (process.stdout,process.stderr,process.stdin):
                if stream is not None:stream.close()
            with lock:
                observation = {'started':True, 'pid':process.pid, 'process_create_time':identity,
                    'return_code':process.poll(), 'stdout':bytes(buffers['stdout']), 'stderr':bytes(buffers['stderr']),
                    'stdout_bytes':counts['stdout'], 'stderr_bytes':counts['stderr'],
                    'cancel_requested':False, 'timed_out':False, 'cleanup_confirmed':cleanup,
                    'elapsed_seconds':round(time.monotonic()-started,3), 'output_collection_incomplete':True,
                    'supervision_error_type':type(error).__name__}
            raise ToolProcessFailure(observation) from None
    for thread in threads:start_thread(thread)
    writer = None
    if input_stream is None and input_bytes:
        def write():
            try:
                view = memoryview(input_bytes)
                while view:
                    sent = os.write(process.stdin.fileno(), view[:65536])
                    view = view[sent:]
            except (OSError, ValueError):
                with lock:failures.append('stdin')
            finally:
                process.stdin.close()
        writer = threading.Thread(target=write, daemon=True)
        start_thread(writer)
    cancelled = timed_out = False
    cleanup = True
    progress_error = None
    next_progress = 0
    try:
        while process.poll() is None:
            elapsed = time.monotonic() - started
            if timeout is not None and elapsed >= timeout or cancel_signal is not None and cancel_signal.is_set():
                timed_out, cancelled = timeout is not None and elapsed >= timeout, cancel_signal is not None and cancel_signal.is_set()
                cleanup = _stop_owned_process(process, identity)
                break
            if progress is not None and elapsed >= next_progress and progress_error is None:
                with lock:
                    event = {'pid':process.pid, 'process_create_time':identity, 'elapsed_seconds':round(elapsed,3),
                             'stdout_bytes':counts['stdout'], 'stderr_bytes':counts['stderr']}
                try:progress(event)
                except Exception as error:progress_error = type(error).__name__
                next_progress = elapsed + .25
            if cancel_signal is not None:cancel_signal.wait(.05)
            else:time.sleep(.05)
    except BaseException:
        _stop_owned_process(process, identity)
        raise
    finally:
        for thread in threads:thread.join(timeout=2)
        if writer is not None:writer.join(timeout=2)
        for stream in (process.stdout, process.stderr, process.stdin):
            if stream is not None:stream.close()
    with lock:
        return {'started':True, 'pid':process.pid, 'process_create_time':identity, 'return_code':process.poll(),
                'stdout':bytes(buffers['stdout']), 'stderr':bytes(buffers['stderr']),
                'stdout_bytes':counts['stdout'], 'stderr_bytes':counts['stderr'],
                'cancel_requested':cancelled, 'timed_out':timed_out, 'cleanup_confirmed':cleanup,
                'elapsed_seconds':round(time.monotonic()-started,3),
                'output_collection_incomplete':bool(failures or any(thread.is_alive() for thread in threads)),
                'progress_delivery_error_type':progress_error}

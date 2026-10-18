"""Real host locks and private durable receipt publication, including spawn."""
import multiprocessing
import os
import queue
import importlib.util
from pathlib import Path
import subprocess
import threading

import pytest

# The helper is stdlib-only; exercise actual host APIs without importing the app.
_spec = importlib.util.spec_from_file_location('native_receipt_fileio',
    Path(__file__).resolve().parents[2] / 'web/pgadmin/cdeadmin/operations/fileio.py')
_fileio = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fileio)
durable_replace = _fileio.durable_replace
exclusive_file_lock = _fileio.exclusive_file_lock
has_private_file_permissions = _fileio.has_private_file_permissions
private_file = _fileio.private_file



def lock_worker(path, messages, release):
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        messages.put('started')
        with exclusive_file_lock(descriptor):
            messages.put('locked')
            if not release.wait(15):
                raise TimeoutError('Owned lock fixture was not released')
    finally:
        os.close(descriptor)


def test_native_lock_serializes_independent_processes(tmp_path):
    context = multiprocessing.get_context('spawn')
    first_messages, second_messages = context.Queue(), context.Queue()
    first_release, second_release = context.Event(), context.Event()
    processes = [context.Process(target=lock_worker, args=(
        str(tmp_path / 'receipt.lock'), messages, release))
        for messages, release in ((first_messages, first_release),
                                  (second_messages, second_release))]
    try:
        processes[0].start()
        assert first_messages.get(timeout=15) == 'started'
        assert first_messages.get(timeout=15) == 'locked'
        processes[1].start()
        assert second_messages.get(timeout=15) == 'started'
        try:
            second_messages.get(timeout=.2)
        except queue.Empty:
            pass
        else:
            raise AssertionError('Second process bypassed the native receipt lock')
        first_release.set()
        assert second_messages.get(timeout=15) == 'locked'
        second_release.set()
        for process in processes:
            process.join(timeout=15)
            assert process.exitcode == 0
    finally:
        first_release.set()
        second_release.set()
        for process in processes:
            if process.pid and process.is_alive():
                process.terminate()
                process.join(timeout=5)
        for messages in (first_messages, second_messages):
            messages.close()
            messages.join_thread()


def test_private_receipt_survives_atomic_publication(tmp_path):
    staging, target = tmp_path / 'staging.json', tmp_path / 'review.json'
    with staging.open('wb') as stream:
        private_file(staging)
        stream.write(b'{"state":"unknown_outcome"}')
        stream.flush()
        os.fsync(stream.fileno())
    assert has_private_file_permissions(staging)
    durable_replace(staging, target)
    assert target.read_bytes() == b'{"state":"unknown_outcome"}'
    assert has_private_file_permissions(target)
    assert not staging.exists()


def test_private_policy_detects_additional_reader(tmp_path):
    path = tmp_path / 'policy.json'
    path.write_bytes(b'{}')
    private_file(path)
    assert has_private_file_permissions(path)
    if os.name == 'nt':
        executable = Path(os.environ['SystemRoot']) / 'System32/icacls.exe'
        subprocess.run([str(executable), str(path), '/grant', '*S-1-1-0:R', '/Q'], check=True)
    else:
        path.chmod(0o644)
    assert not has_private_file_permissions(path)
    private_file(path)
    assert has_private_file_permissions(path)


def test_nonblocking_native_lock_reports_contention_without_waiting_for_the_owner(tmp_path):
    context=multiprocessing.get_context('spawn');messages=context.Queue();release=context.Event()
    path=tmp_path/'nonblocking.lock';process=context.Process(target=lock_worker,args=(str(path),messages,release))
    descriptor=None;timer=None
    try:
        process.start();assert messages.get(timeout=15)=='started';assert messages.get(timeout=15)=='locked'
        descriptor=os.open(path,os.O_RDWR)
        # If a regression blocks, release its owned fixture so the test fails
        # instead of leaving a child or locked test process behind.
        timer=threading.Timer(3,release.set);timer.start()
        with pytest.raises(OSError):
            with exclusive_file_lock(descriptor,blocking=False):pytest.fail('A contended native lock was acquired')
    finally:
        if timer is not None:timer.cancel()
        if descriptor is not None:os.close(descriptor)
        release.set()
        if process.pid is not None:
            process.join(timeout=15)
            if process.is_alive():process.terminate();process.join(timeout=5)
        messages.close();messages.join_thread()
    assert process.exitcode==0

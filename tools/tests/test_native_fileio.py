"""Real host locks and private durable receipt publication, including spawn."""
import multiprocessing
import os
import queue

from pgadmin.cdeadmin.operations.fileio import (
    durable_replace, exclusive_file_lock, has_private_file_permissions, private_file,
)


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

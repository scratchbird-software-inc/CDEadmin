"""Bounded, process-local idle cleanup scheduling; no transaction finality."""
import os
import queue
import threading
import weakref

IDLE_SECONDS = 300
SWEEP_SECONDS = 30


class StreamLeaseSweeper:
    def __init__(self):
        self._lock = threading.Lock()
        self._clients = weakref.WeakSet()
        self._pending = weakref.WeakSet()
        self._queue = queue.Queue(maxsize=16)
        self._started = False
        self._offset = 0

    def watch(self, client):
        with self._lock:
            self._clients.add(client)
            if self._started:
                return
            self._started = True
            for index in range(2):
                worker = threading.Thread(
                    target=self._worker, daemon=True,
                    name=f'firebird-stream-cleanup-{index}')
                worker.start()
            threading.Thread(target=self._timer, daemon=True,
                             name='firebird-stream-leases').start()

    def schedule(self):
        with self._lock:
            clients = tuple(self._clients)
            if not clients:
                return
            start = self._offset % len(clients)
            for index in range(len(clients)):
                position = (start + index) % len(clients)
                client = clients[position]
                self._offset = (position + 1) % len(clients)
                if client in self._pending:
                    continue
                try:
                    self._queue.put_nowait(client)
                except queue.Full:
                    self._offset = position
                    break
                self._pending.add(client)

    def _worker(self):
        while True:
            client = self._queue.get()
            try:
                client.reap_idle_streams()
            except Exception:
                # Resource failures remain recorded on their attachment. A
                # racing client shutdown must not kill the cleanup worker.
                pass
            finally:
                with self._lock:
                    self._pending.discard(client)
                self._queue.task_done()
                # Do not keep an otherwise idle client alive between jobs.
                del client

    def _timer(self):
        tick = threading.Event()
        while not tick.wait(SWEEP_SECONDS):
            self.schedule()


_sweeper = StreamLeaseSweeper()


def _after_fork():
    # Native attachments are not portable across fork. Do not carry the
    # parent's queued owners or synchronization primitives into a child.
    global _sweeper
    _sweeper = StreamLeaseSweeper()


if hasattr(os, 'register_at_fork'):
    os.register_at_fork(after_in_child=_after_fork)


def watch(client):
    _sweeper.watch(client)

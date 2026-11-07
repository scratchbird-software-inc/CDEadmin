"""Worker liveness for durable job receipts.

A job receipt names the application process that runs its worker
(``worker_identity``: process id and process creation time); a worker in this
process is also tracked as a thread. A worker stores its terminal receipt and
then stops, so a reader that loads a receipt outside the store lock can see the
worker stop after that load. A stopped worker writes nothing more: a receipt
loaded after the worker was seen stopped holds its last write. Readers that
find a stopped worker behind an unfinished receipt therefore load it once more
and judge that copy, so a finished job is never reported as abandoned.

Code that reads a receipt while holding its store lock needs no second load:
the worker's terminal write takes the same lock.
"""
import psutil


def worker_stopped(record, own_identity, local_worker):
    """True when the worker named by ``record`` is not running.

    The worker is stopped when its recorded process no longer exists, or when
    the receipt belongs to this process and ``local_worker`` (this process's
    ``(thread, signal)`` entry for the job, or None) is not a running thread.
    """
    pid, created = record.get('worker_identity', (None, None))
    try:
        alive = (pid is not None and
                 psutil.Process(pid).create_time() == created)
    except psutil.Error:
        alive = False
    if not alive:
        return True
    own = list(record['worker_identity']) == list(own_identity)
    running = local_worker is not None and local_worker[0].is_alive()
    return own and not running


def read_settled(load, view, unsettled):
    """Load a receipt and return ``view`` of it.

    When ``unsettled(record, shown)`` holds, the view judged a stopped worker
    against that copy, so the receipt is loaded and viewed once more.
    """
    record = load()
    shown = view(record)
    if unsettled(record, shown):
        shown = view(load())
    return shown

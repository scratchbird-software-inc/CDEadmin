"""Lease-bound native subscriptions; event counts are not durable history."""
from dataclasses import dataclass, field
import threading
import time
import uuid


def names(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 15:
        raise ValueError('Select 1–15 event names')
    if any(not isinstance(item, str) or not item or '\0' in item or len(item.encode('utf-8')) > 127 for item in value):
        raise ValueError('Event names require 1–127 UTF-8 bytes without NUL')
    if len(set(value)) != len(value):
        raise ValueError('Event names must be unique')
    return tuple(value)


@dataclass
class Subscription:
    owner: str
    binding: str
    names: tuple
    identity: str = field(default_factory=lambda: uuid.uuid4().hex)
    state: str = 'starting'
    counts: dict = field(default_factory=dict)
    error_type: str | None = None
    cleanup_confirmed: bool = False
    gap: bool = False
    lease: float = field(default_factory=time.monotonic)
    updated: float = field(default_factory=time.time)
    stop: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)
    lock: threading.RLock = field(default_factory=threading.RLock)

    def snapshot(self):
        with self.lock:
            return {'subscription_id': self.identity, 'state': self.state,
                    'counts': {key: str(value) for key, value in self.counts.items()},
                    'error_type': self.error_type, 'cleanup_confirmed': self.cleanup_confirmed,
                    'delivery_gap': self.gap, 'updated_at': self.updated,
                    'scope': 'observed since this native subscription; no replay or durable delivery',
                    'idle_expiry_seconds': 120, 'requires_process_affinity': True}


def heartbeat(connection):
    from .profiling import transaction
    with transaction(connection) as cursor:
        cursor.execute('SELECT 1 FROM RDB$DATABASE')
        cursor.fetchone()


class EventSubscriptions:
    def __init__(self):
        self.lock = threading.RLock()
        self.items = {}
        self.closed = False

    def start(self, owner, binding, event_names, connect, close):
        event_names = names(event_names)
        with self.lock:
            if self.closed:
                raise ValueError('Native event service is shutting down')
            now = time.monotonic()
            self.items = {key: item for key, item in self.items.items()
                          if not item.done.is_set() or now - item.lease < 600}
            if len(self.items) >= 1000:
                oldest = next((key for key, value in self.items.items() if value.done.is_set()), None)
                if oldest is not None:
                    del self.items[oldest]
                else:
                    raise ValueError('Native event receipt limit reached')
            active = [item for item in self.items.values() if not item.done.is_set()]
            if len(active) >= 32 or sum(item.owner == owner for item in active) >= 4:
                raise ValueError('Native event subscription limit reached')
            item = Subscription(owner, binding, event_names, counts=dict.fromkeys(event_names, 0))
            self.items[item.identity] = item
        # Protected endpoint credentials require the authenticated request
        # context. Resolve/open here; the worker receives only its owned native
        # attachment, not a copied web session or a password-bearing context.
        try:
            connection = connect()
        except Exception as error:
            with item.lock:
                item.state = 'cleanup-unknown'
                item.error_type = type(error).__name__
                item.gap = True
            item.done.set()
            return item.snapshot()
        try:
            threading.Thread(target=self._run, args=(item, lambda: connection, close), daemon=True,
                             name='firebird-events-' + item.identity[:8]).start()
        except Exception as error:
            with item.lock:
                item.state = 'cleanup-unknown'
                item.error_type = type(error).__name__
                item.gap = True
            try:
                close(connection)
                item.cleanup_confirmed = True
                item.state = 'failed'
            except Exception as cleanup_error:
                # Preserve the subscription receipt even when thread startup
                # and attachment release both fail.
                item.error_type = type(cleanup_error).__name__
            finally:
                item.done.set()
        return item.snapshot()

    def close(self):
        with self.lock:
            self.closed = True
            items = tuple(self.items.values())
            for item in items:
                item.stop.set()
        deadline = time.monotonic() + 2
        for item in items:
            item.done.wait(max(0, deadline - time.monotonic()))
        return all(item.cleanup_confirmed for item in items)

    def action(self, owner, binding, identity, *, stop=False):
        with self.lock:
            item = self.items.get(identity)
            if item is None or item.owner != owner or item.binding != binding:
                raise ValueError('Event subscription unavailable in this process or scope')
        with item.lock:
            item.lease = time.monotonic()
            if stop:
                item.stop.set()
                if not item.done.is_set():
                    item.state = 'stopping'
        if stop:
            item.done.wait(2)
        return item.snapshot()

    @staticmethod
    def _run(item, connect, close):
        connection = collector = None
        terminal = 'stopped'
        connect_failed = False
        try:
            connection = connect()
            if item.stop.is_set():
                return
            collector = connection.event_collector(item.names)
            collector.begin()
            heartbeat(connection)
            next_probe = time.monotonic() + 10
            with item.lock:
                item.state = 'listening'
            while not item.stop.wait(.25):
                now = time.monotonic()
                if now - item.lease >= 120:
                    terminal = 'expired'
                    break
                # The pinned driver owns its callback thread. Failure of that
                # thread otherwise leaves wait() returning stale counters.
                native_thread = getattr(collector, '_EventCollector__process_thread', None)
                if native_thread is None or not native_thread.is_alive():
                    raise RuntimeError('Native event callback thread unavailable')
                counts = collector.wait(0)
                if not isinstance(counts, dict) or set(counts) != set(item.names):
                    raise RuntimeError('Invalid native event counters')
                with item.lock:
                    if any(type(value) is not int or value < item.counts[key] for key, value in counts.items()):
                        raise RuntimeError('Native event counter reset')
                    item.counts = dict(counts)
                    item.updated = time.time()
                if now >= next_probe:
                    heartbeat(connection)
                    next_probe = now + 10
        except Exception as error:
            connect_failed = connection is None
            terminal = 'failed'
            with item.lock:
                item.error_type = type(error).__name__
                item.gap = True
        finally:
            released = not connect_failed
            with item.lock:
                item.state = 'stopping'
            if collector is not None:
                try:
                    collector.close()
                except Exception as error:
                    released = False
                    item.error_type = type(error).__name__
            if connection is not None:
                try:
                    close(connection)
                except Exception as error:
                    released = False
                    item.error_type = type(error).__name__
            with item.lock:
                item.cleanup_confirmed = released
                item.state = terminal if released else 'cleanup-unknown'
                item.gap = item.gap or not released or terminal == 'expired'
                item.updated = time.time()
            item.done.set()

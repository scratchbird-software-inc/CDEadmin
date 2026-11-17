"""Owned user-trace streams. Captured text is private, bounded and volatile."""
from collections import deque
from dataclasses import dataclass, field
import threading
import time
import uuid

from .trace_config import normalize, render, text

MAX_LINES = 2000
MAX_BYTES = 1024 * 1024
IDLE_SECONDS = 120
LIFETIME_SECONDS = 3600


@dataclass
class Trace:
    owner: str
    binding: str
    scope: dict
    options: dict
    name: str
    connect: object
    release: object
    on_finish: object = None
    identity: str = field(default_factory=lambda: uuid.uuid4().hex)
    state: str = 'starting'
    native_id: int | None = None
    producer: object = None
    controller: object = None
    native_started: bool = False
    native_stop_acknowledged: bool = False
    native_end_observed: bool = False
    cleanup_confirmed: bool = False
    error_type: str | None = None
    plugin_diagnostic_observed: bool = False
    closing: bool = False
    lines: deque = field(default_factory=deque)
    byte_count: int = 0
    sequence: int = 0
    dropped: int = 0
    created: float = field(default_factory=time.monotonic)
    lease: float = field(default_factory=time.monotonic)
    lock: object = field(default_factory=threading.RLock)
    stop: object = field(default_factory=threading.Event)
    done: object = field(default_factory=threading.Event)

    def snapshot(self, after=None, limit=200):
        with self.lock:
            result = {'trace_id': self.identity, 'native_session_id': self.native_id,
                      'name': self.name, 'state': self.state, 'native_started': self.native_started,
                      'native_stop_acknowledged': self.native_stop_acknowledged,
                      'native_end_observed': self.native_end_observed,
                      'cleanup_confirmed': self.cleanup_confirmed, 'error_type': self.error_type,
                      'plugin_diagnostic_observed': self.plugin_diagnostic_observed,
                      'capture_success_inferred': False, 'automatic_retry': False,
                      'requires_process_affinity': True, 'output_persisted': False,
                      'idle_expiry_seconds': IDLE_SECONDS, 'maximum_lifetime_seconds': LIFETIME_SECONDS,
                      'dropped_lines': self.dropped, 'last_sequence': self.sequence}
            if after is not None:
                first = self.lines[0]['sequence'] if self.lines else self.sequence + 1
                rows = [dict(row) for row in self.lines if row['sequence'] > after][:limit]
                result.update(lines=rows, delivery_gap=after < first - 1,
                              next_sequence=rows[-1]['sequence'] if rows else after)
            return result


class TraceSessions:
    def __init__(self):
        self.lock = threading.RLock()
        self.items = {}
        self.closed = False

    def _get(self, owner, binding, identity):
        with self.lock:
            item = self.items.get(identity)
            if item is None or item.owner != owner or item.binding != binding:
                raise ValueError('Trace unavailable for this owner, target or process')
            return item

    def start(self, owner, binding, scope, options, name, connect, release, on_finish=None):
        options = normalize(options)
        name = text(name, 128)
        config = render(scope['database'], options, scope.get('attachment_names', ()))
        with self.lock:
            if self.closed:
                raise ValueError('Trace service is shutting down')
            active = [item for item in self.items.values() if not item.done.is_set()]
            if (len(active) >= 16 or sum(item.owner == owner for item in active) >= 4
                    or len(self.items) >= 32):
                raise ValueError('Trace capacity reached; stop or forget finished owned traces')
            item = Trace(owner, binding, dict(scope), options, name, connect, release, on_finish)
            self.items[item.identity] = item
        try:
            # Credentials are resolved on the authenticated request thread.
            item.producer, item.controller = connect(), connect()
            item.connect = None
            item.native_id = item.producer.trace.start(config=config, name=name)
            if type(item.native_id) is not int or item.native_id <= 0:
                raise ValueError('Native trace identifier was not returned')
            item.native_started = True
            item.state = 'started'
            worker = threading.Thread(target=self._run, args=(item,), daemon=True,
                                      name='firebird-trace-' + item.identity[:8])
            worker.start()
        except BaseException as error:
            item.error_type = type(error).__name__
            if 'worker' in locals() and worker.ident is not None:
                item.stop.set()
                item.done.wait(2)
            else:
                self._finish(item, 'unknown_outcome')
            if not isinstance(error, Exception):
                raise
        return item.snapshot()

    def poll(self, owner, binding, identity, after=0, limit=200):
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('Trace cursor/limit is invalid')
        item = self._get(owner, binding, identity)
        with item.lock:
            if after > item.sequence:
                raise ValueError('Trace cursor is ahead of observed output')
            item.lease = time.monotonic()
            return item.snapshot(after, limit)

    def listing(self, owner, binding):
        with self.lock:
            items = [item for item in self.items.values() if item.owner ==
                     owner and item.binding == binding]
        result = []
        for item in items:
            with item.lock:
                observed = None
                if not item.closing and not item.done.is_set() and item.controller is not None:
                    try:
                        native = item.controller.trace.sessions.get(item.native_id)
                        observed = {'present': native is not None,
                                    'flags': list(native.flags) if native is not None else []}
                    except Exception as error:
                        observed = {'present': None, 'error_type': type(error).__name__}
                result.append({**item.snapshot(), 'native_list_observation': observed})
        return {'items': result, 'scope': 'managed traces for this owner and registered target'}

    def control(self, owner, binding, identity, operation):
        item = self._get(owner, binding, identity)
        if operation == 'forget':
            with self.lock, item.lock:
                if not item.done.is_set() or not item.cleanup_confirmed:
                    raise ValueError('Only a finished trace with released handles can be forgotten')
                self.items.pop(identity, None)
                item.lines.clear()
                item.byte_count = 0
                return {'trace_id': identity, 'state': 'forgotten', 'output_persisted': False}
        with item.lock:
            if operation == 'release':
                if not item.done.is_set():
                    raise ValueError('Stop and finish the trace before retrying handle release')
                item.cleanup_confirmed = item.release() is True
                if item.cleanup_confirmed:
                    item.state = 'released'
                    item.producer = item.controller = item.connect = None
                    item.release = lambda: True
                if item.on_finish is not None:
                    item.on_finish(item.snapshot())
                return item.snapshot()
            if item.closing or item.done.is_set() or item.native_id is None:
                raise ValueError('Trace no longer admits native controls')
            if operation == 'stop':
                item.state = 'stopping'
                item.stop.set()
            elif operation in {'suspend', 'resume'}:
                try:
                    getattr(item.controller.trace, operation)(session_id=item.native_id)
                    item.state = 'suspended' if operation == 'suspend' else 'started'
                except Exception as error:
                    item.state = 'unknown_outcome'
                    item.error_type = type(error).__name__
                    raise
            else:
                raise ValueError('Unknown trace control')
        if operation == 'stop':
            item.done.wait(2)
        return item.snapshot()

    @staticmethod
    def _append(item, value):
        raw = value.encode('utf-8', errors='replace')
        clipped = len(raw) > 32768
        value = raw[:32768].decode('utf-8', errors='ignore')
        size = len(value.encode('utf-8'))
        with item.lock:
            item.sequence += 1
            item.lines.append({'sequence': item.sequence, 'text': value, 'truncated': clipped})
            item.byte_count += size
            while len(item.lines) > MAX_LINES or item.byte_count > MAX_BYTES:
                item.byte_count -= len(item.lines.popleft()['text'].encode('utf-8'))
                item.dropped += 1
            if value.startswith(('Error creating trace session', 'Error parsing trace')):
                item.plugin_diagnostic_observed = True
                item.stop.set()

    def _run(self, item):
        terminal = 'stopped'
        try:
            while not item.stop.is_set():
                now = time.monotonic()
                if now - item.lease > IDLE_SECONDS or now - item.created > LIFETIME_SECONDS:
                    terminal = 'expired'
                    break
                line = item.producer.readline_timed(1)
                if isinstance(line, str):
                    self._append(item, line)
                elif line is None and not item.producer.is_running():
                    item.native_end_observed = True
                    terminal = 'ended'
                    break
            if item.plugin_diagnostic_observed:
                terminal = 'plugin_error'
        except BaseException as error:
            item.error_type = type(error).__name__
            terminal = 'unknown_outcome'
        finally:
            self._finish(item, terminal)

    @staticmethod
    def _finish(item, terminal):
        with item.lock:
            item.closing = True
            if item.native_id is not None and not item.native_end_observed:
                try:
                    item.controller.trace.stop(session_id=item.native_id)
                    item.native_stop_acknowledged = True
                except Exception as error:
                    item.error_type = type(error).__name__
                    terminal = 'unknown_outcome'
            try:
                item.cleanup_confirmed = item.release() is True
            except Exception as error:
                item.error_type = type(error).__name__
                terminal = 'unknown_outcome'
            item.state = terminal if item.cleanup_confirmed else 'cleanup_unknown'
            if item.cleanup_confirmed:
                item.producer = item.controller = item.connect = None
                item.release = lambda: True
            item.done.set()
        if item.on_finish is not None:
            try:
                item.on_finish(item.snapshot())
            except Exception:
                # A durable pre-dispatch receipt already forbids replay.
                # Do not repeat a native action to repair an audit write.
                with item.lock:
                    item.error_type = 'TraceReceiptPersistenceFailure'

    def close(self):
        with self.lock:
            self.closed = True
            items = list(self.items.values())
            for item in items:
                item.stop.set()
        deadline = time.monotonic() + 2
        for item in items:
            item.done.wait(max(0, deadline - time.monotonic()))
        return all(item.cleanup_confirmed for item in items)

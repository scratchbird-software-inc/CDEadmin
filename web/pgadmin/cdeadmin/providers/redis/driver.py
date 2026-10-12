"""Retained Redis connections, native transactions and exact RESP3 values."""
import base64
import copy
from collections.abc import Mapping
import json
import math
import time
from types import SimpleNamespace

from .client import RedisClient, RedisClientError, _binary
from ..native_distributed import NativeResult
from ..retained_native import RetainedNativeClient


def exact(value, depth=0):
    if depth > 32:
        raise RedisClientError('Redis reply nesting exceeds bounds')
    if type(value) is int and abs(value) > 2**53 - 1:
        return {'$integer': str(value)}
    if isinstance(value, float) and not math.isfinite(value):
        return {'$float': str(value)}
    if isinstance(value, bytes):
        try:
            text = value.decode('utf8')
            if all(x.isprintable() or x in '\r\n\t' for x in text):
                return text
        except UnicodeDecodeError:
            pass
        return {'$binary': base64.b64encode(value).decode()}
    if isinstance(value, Mapping):
        return {'$map': [[exact(k, depth + 1), exact(v, depth + 1)]
                         for k, v in value.items()]}
    if isinstance(value, set):
        return {'$set': [exact(x, depth + 1) for x in value]}
    if isinstance(value, (list, tuple)):
        return [exact(x, depth + 1) for x in value]
    if isinstance(value, Exception):
        return {'$error': {'type': type(value).__name__}}
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise RedisClientError('Redis reply type lacks an exact representation')


def argument(value):
    if isinstance(value, dict) and set(value) == {'$integer'}:
        text = value['$integer']
        if not isinstance(text, str) or str(int(text)) != text:
            raise RedisClientError('Redis exact integer invalid')
        return text.encode('ascii')
    if type(value) is int and abs(value) > 2**53 - 1:
        raise RedisClientError('Use an exact Redis integer envelope')
    if isinstance(value, float) and not math.isfinite(value):
        raise RedisClientError(
            'Redis nonfinite argument requires explicit text')
    return _binary(value, 'command argument')


class RedisOwner:
    def __init__(self, client, topology, route):
        self.client, self.topology, self.route = client, topology, route
        self.connection = None
        self.pipeline = None
        self.pending_cleanup = []
        self.state = 'idle'
        self.last_decision = None
        self.selected_database = route['database']


class RedisDriverBackend(RedisClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pending_native_cleanup = []

    def _close_native(self, client, topology=None):
        failed = False
        for item in (client, topology):
            close = getattr(item, 'close', None)
            if callable(close):
                try:
                    close()
                except Exception:
                    failed = True
        pair = (client, topology)
        if failed:
            if pair not in self._pending_native_cleanup:
                self._pending_native_cleanup.append(pair)
            raise RedisClientError('Redis temporary cleanup incomplete')
        if pair in self._pending_native_cleanup:
            self._pending_native_cleanup.remove(pair)

    @classmethod
    def _route(cls, request):
        route = super()._route(request)
        # Legacy route defaults allowed cluster error retries. They may replay
        # an ambiguous write, so the retained driver never admits them.
        original = request.get('route') or request.get('_provider_route') or {}
        if original.get('cluster_error_retry_attempts', 0) != 0:
            raise RedisClientError(
                'Redis cluster mutation retries must be zero')
        route['cluster_error_retry_attempts'] = 0
        return route

    def open_session(self, request):
        client, topology, route = self._connect(request)
        owner = RedisOwner(client, topology, route)
        self._sessions.append(owner)
        try:
            if route['topology_mode'] == 'cluster':
                client.ping()
            else:
                owner.connection = client.connection_pool.get_connection()
                self._send(owner, (b'PING',))
            return owner
        except Exception:
            self.close_session(owner, True)
            raise

    @staticmethod
    def _send(owner, arguments):
        connection = owner.connection
        connection.send_command(*arguments)
        return connection.read_response()

    def describe_transaction(self, owner):
        return dict(
            super().describe_transaction(owner),
            native_state=owner.state,
            selected_database=owner.selected_database,
            native_connection_reserved=owner.connection is not None,
            cluster_error_retries=0,
            last_exec_result=exact(owner.last_decision))

    def _arguments(self, command, parameters):
        if isinstance(command, dict):
            if command.get('operation') != 'command':
                raise RedisClientError('Redis command operation invalid')
            command = command.get('arguments')
        if isinstance(command, list):
            command = [argument(x) for x in command]
        if parameters is not None:
            if not isinstance(parameters, (list, tuple)):
                raise RedisClientError('Redis parameters must be an array')
            parameters = [argument(x) for x in parameters]
        return self._source_arguments({'source': command,
                                       'parameters': parameters or []})

    def _command(self, owner, arguments):
        name = self._command_key(arguments)
        if name in {'SUBSCRIBE', 'PSUBSCRIBE', 'SSUBSCRIBE', 'MONITOR',
                    'UNSUBSCRIBE', 'PUNSUBSCRIBE', 'SUNSUBSCRIBE'}:
            raise RedisClientError('Use a dedicated Redis streaming operation')
        if name == 'HELLO' and len(arguments) > 1 and arguments[1] != b'3':
            raise RedisClientError('Redis driver requires RESP3')
        if owner.route['topology_mode'] != 'cluster':
            if name == 'EXEC':
                owner.state = 'exec-unknown'
            value = self._send(owner, arguments)
            if name == 'MULTI':
                owner.state = 'multi'
            elif name == 'WATCH':
                owner.state = 'watching'
            elif name == 'EXEC':
                owner.state = ('watch-aborted' if value is None
                               else 'exec-returned')
                owner.last_decision = value
            elif name in {'DISCARD', 'UNWATCH'}:
                owner.state = 'idle'
            elif name == 'SELECT' and value == b'OK':
                owner.selected_database = int(arguments[1])
            return value
        # redis-py Cluster's command catalog uses textual command names.
        arguments = self._cluster_arguments(arguments)
        # Native ClusterPipeline owns same-slot validation and routing.
        if name in {'WATCH', 'MULTI'}:
            if owner.pipeline is None:
                owner.pipeline = owner.client.pipeline(transaction=True)
            if name == 'WATCH':
                value = owner.pipeline.watch(*arguments[1:])
                owner.state = 'watching'
            else:
                value = owner.pipeline.multi()
                owner.state = 'client-queued-multi'
            return b'OK' if value is None else value
        if name in {'EXEC', 'DISCARD', 'UNWATCH'}:
            pipeline = owner.pipeline
            if pipeline is None:
                raise RedisClientError('Redis Cluster transaction unavailable')
            owner.pipeline = None
            owner.pending_cleanup.append(pipeline)
            try:
                if name == 'EXEC':
                    owner.state = 'exec-unknown'
                    try:
                        value = pipeline.execute(raise_on_error=False)
                    except self.module.WatchError as exc:
                        # Pinned redis-py also uses WatchError for connection
                        # failures. Only its explicit native abort is final.
                        if str(exc) != 'Watched variable changed.':
                            raise
                        owner.state = 'watch-aborted'
                        owner.last_decision = None
                        return None
                    owner.state = 'exec-returned'
                    owner.last_decision = value
                    return value
                owner.state = 'idle'
                return b'OK'
            finally:
                pipeline.reset()
                owner.pending_cleanup.remove(pipeline)
        if owner.pipeline is not None:
            value = owner.pipeline.execute_command(*arguments)
            return b'QUEUED' if value is owner.pipeline else value
        return owner.client.execute_command(*arguments)

    @classmethod
    def _cluster_arguments(cls, arguments):
        if not isinstance(arguments[0], bytes):
            return arguments
        command = cls._command_key(arguments)
        if '|' in command:
            return (command.replace('|', ' '), *arguments[2:])
        return (arguments[0].decode('ascii').upper(), *arguments[1:])

    def _execute_compiled(self, client, compiled, payload, route):
        if route['topology_mode'] == 'cluster':
            compiled = copy.deepcopy(compiled)
            compiled['commands'] = [self._cluster_arguments(
                command) for command in compiled.get('commands', [])]
        return super()._execute_compiled(client, compiled, payload, route)

    def control_transaction(self, owner, action):
        names = {'begin': b'MULTI', 'commit': b'EXEC', 'rollback': b'DISCARD'}
        self._command(owner, (names[action],))

    @staticmethod
    def _page(rows, operation, offset, **native):
        return NativeResult(
            'key_value', 'entries', rows, {
                'fields': [
                    'command', 'value', 'outcome', 'ordinal']}, dict(
                operation=operation, row_offset=offset, **native))

    def _pages(self, values, operation, owner):
        rows, size, offset = [], 0, 0
        for value in values:
            row = {'command': operation, 'value': exact(value),
                   'outcome': owner.state, 'ordinal': offset + len(rows)}
            width = len(json.dumps(row).encode())
            if rows and (len(rows) >= 256 or size + width > 1048576):
                yield self._page(rows, operation, offset, state=owner.state)
                offset += len(rows)
                rows, size = [], 0
                row['ordinal'] = offset
            rows.append(row)
            size += width
        yield self._page(rows, operation, offset, state=owner.state)

    def _scan(self, owner, command):
        if owner.state in {'multi', 'watching', 'client-queued-multi'}:
            raise RedisClientError('Redis cursor scan needs an idle session')
        match = argument(command.get('match', '*'))
        if owner.route['topology_mode'] == 'cluster':
            yield from owner.client.scan_iter(match=match, count=256)
        else:
            cursor = b'0'
            while True:
                arguments = (b'SCAN', cursor, b'MATCH', match,
                             b'COUNT', b'256')
                cursor, keys = self._send(owner, arguments)
                yield from keys
                if int(cursor) == 0:
                    break

    def _messages(self, owner, command):
        operation = command['operation']
        limit = command.get('limit', 100)
        timeout = command.get('timeout_seconds', 10)
        if type(limit) is not int or not 1 <= limit <= 10000:
            raise RedisClientError('Redis stream limit invalid')
        if type(timeout) not in (int, float) or not 0 < timeout <= 60:
            raise RedisClientError('Redis stream timeout invalid')
        channels = command.get('channels')
        if not isinstance(channels, list) or not 1 <= len(channels) <= 256:
            raise RedisClientError('Redis stream channels invalid')
        pubsub = owner.client.pubsub(ignore_subscribe_messages=False)
        owner.pending_cleanup.append(pubsub)
        try:
            getattr(pubsub, operation)(*[argument(x) for x in channels])
            deadline = time.monotonic() + timeout
            count = 0
            while count < limit and time.monotonic() < deadline:
                method = (getattr(pubsub, 'get_sharded_message',
                                  pubsub.get_message)
                          if operation == 'ssubscribe' else pubsub.get_message)
                value = method(
                    timeout=min(
                        0.5, max(
                            0, deadline - time.monotonic())))
                if value is not None:
                    count += 1
                    yield value
        finally:
            pubsub.close()
            owner.pending_cleanup.remove(pubsub)

    def _monitor(self, owner, command):
        limit, timeout = command.get(
            'limit', 100), command.get(
            'timeout_seconds', 10)
        if type(limit) is not int or not 1 <= limit <= 10000:
            raise RedisClientError('Redis monitor limit invalid')
        if type(timeout) not in (int, float) or not 0 < timeout <= 60:
            raise RedisClientError('Redis monitor timeout invalid')
        client = owner.client
        if owner.route['topology_mode'] == 'cluster':
            client = client.get_redis_connection(client.get_default_node())
        monitor = client.monitor()
        lease = SimpleNamespace(
            close=lambda: monitor.__exit__(
                None, None, None))
        owner.pending_cleanup.append(lease)
        try:
            monitor.__enter__()
            deadline = time.monotonic() + timeout
            count = 0
            while count < limit and time.monotonic() < deadline:
                if monitor.connection.can_read(timeout=min(0.5, max(
                        0, deadline - time.monotonic()))):
                    value = monitor.connection.read_response()
                    count += 1
                    yield value
        finally:
            lease.close()
            owner.pending_cleanup.remove(lease)

    def iterate(self, owner, command, parameters):
        operation = command.get('operation') if isinstance(
            command, dict) else None
        if operation in {
            'scan',
            'subscribe',
            'psubscribe',
            'ssubscribe',
                'monitor'}:
            if parameters:
                raise RedisClientError(
                    'Redis streaming parameters belong in JSON')
            callback = (self._scan if operation == 'scan' else
                        self._monitor if operation == 'monitor'
                        else self._messages)
            values = callback(owner, command)
            # Streaming replies are emitted immediately, rather than waiting
            # for 256 Pub/Sub messages before the first observation.
            if operation != 'scan':
                for index, value in enumerate(values):
                    rows = [{'value': exact(value)}]
                    yield self._page(rows, operation, index)
            else:
                yield from self._pages(values, operation, owner)
            return
        arguments = self._arguments(command, parameters)
        value = self._command(owner, arguments)
        values = value if isinstance(value, (list, tuple)) else [value]
        yield from self._pages(values, self._command_key(arguments), owner)

    def close_session(self, owner, _unknown=False):
        failures = []
        for item in list(owner.pending_cleanup) + \
                ([owner.pipeline] if owner.pipeline is not None else []):
            try:
                callback = getattr(item, 'reset', None) or item.close
                callback()
                if item in owner.pending_cleanup:
                    owner.pending_cleanup.remove(item)
                if item is owner.pipeline:
                    owner.pipeline = None
            except Exception:
                failures.append(True)
        if owner.connection is not None:
            try:
                owner.connection.disconnect()
                owner.client.connection_pool.release(owner.connection)
                owner.connection = None
            except Exception:
                failures.append(True)
        for name in ('client', 'topology'):
            if name == 'client' and owner.connection is not None:
                continue
            item = getattr(owner, name)
            if item is not None:
                try:
                    callback = getattr(item, 'close', None)
                    if callable(callback):
                        callback()
                    setattr(owner, name, None)
                except Exception:
                    failures.append(True)
        if failures:
            raise RedisClientError('Redis owned cleanup incomplete')
        if owner in self._sessions:
            self._sessions.remove(owner)

    @staticmethod
    def complete(_request):
        return []

    def close(self):
        failed = False
        for owner in list(self._sessions):
            try:
                self.close_session(owner, True)
            except Exception:
                failed = True
        for pair in list(self._pending_native_cleanup):
            try:
                self._close_native(*pair)
            except Exception:
                failed = True
        if failed:
            raise RedisClientError('Redis cleanup incomplete')
        super().close()


class RedisDriver(RetainedNativeClient):
    transaction_actions = ('begin', 'commit', 'rollback')

    def __getattr__(self, name):
        return getattr(self.backend, name)

    def inspect_resource(self, request):
        return self.backend.inspect_resource(request)

    def describe_transaction(self, session):
        with session.lock:
            if session.active is None:
                session.observation = self.backend.describe_transaction(
                    session.handle)
            return super().describe_transaction(session)

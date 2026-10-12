"""Ignite thin-client worker and exact-value admission."""
import base64
import contextvars
import datetime
from decimal import Decimal
import json
import math
import uuid

from .client import IgniteBackend
from ..native_distributed import NativeDistributedError, NativeResult
from ..retained_native import RetainedNativeClient


def exact(value):
    if type(value) is int and abs(value) > 2**53 - 1:
        return {'type': 'integer', 'value': str(value)}
    if isinstance(value, Decimal):
        return {'type': 'decimal', 'value': str(value)}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {'type': 'binary', 'value': base64.b64encode(value).decode()}
    if isinstance(value, uuid.UUID):
        return {'type': 'uuid', 'value': str(value)}
    if isinstance(value, (datetime.date, datetime.time)):
        kind = ('timestamp' if isinstance(value, datetime.datetime) else
                'date' if isinstance(value, datetime.date) else 'time')
        return {'type': kind, 'value': value.isoformat()}
    if isinstance(value, float) and not math.isfinite(value):
        return {'type': 'float', 'value': str(value)}
    if isinstance(value, dict):
        return {'type': 'map', 'value': [[exact(k), exact(v)]
                                         for k, v in value.items()]}
    if isinstance(value, tuple):
        return {'type': 'tuple', 'value': [exact(v) for v in value]}
    if isinstance(value, list):
        return [exact(v) for v in value]
    if hasattr(value, 'schema') and hasattr(value, 'type_name'):
        return {'type': 'binary-object', 'value': {
            'name': value.type_name,
            'schema': {k: v.__name__ for k, v in value.schema.items()},
            'fields': {k: exact(getattr(value, k)) for k in value.schema}}}
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise NativeDistributedError('Ignite value has no exact representation')


def bound(value):
    if isinstance(value, dict) and set(value) == {'type', 'value'}:
        kind, data = value['type'], value['value']
        if kind in {'map', 'tuple'} and isinstance(data, list):
            if kind == 'map':
                return (1, {bound(k): bound(v) for k, v in data})
            return tuple(bound(v) for v in data)
        if kind == 'binary-object' and isinstance(data, dict):
            from pyignite import GenericObjectMeta, datatypes
            allowed = {
                'BoolObject', 'ByteObject', 'ShortObject', 'IntObject',
                'LongObject', 'FloatObject', 'DoubleObject', 'CharObject',
                'String', 'DecimalObject', 'UUIDObject', 'DateObject',
                'TimeObject', 'TimestampObject', 'ByteArrayObject',
                'IntArrayObject', 'LongArrayObject', 'StringArrayObject',
                'ObjectArrayObject', 'MapObject', 'CollectionObject',
                'BinaryObject',
            }
            schema = data.get('schema', {})
            if not schema or len(schema) > 256 or any(
                    not isinstance(k, str) or not k or k.startswith('_') or
                    v not in allowed for k, v in schema.items()):
                raise NativeDistributedError('Ignite binary schema invalid')
            native_schema = {k: getattr(datatypes, v)
                             for k, v in schema.items()}
            model = GenericObjectMeta('OwnedValue', (), {},
                                      type_name=str(data['name']),
                                      schema=native_schema)
            if set(data.get('fields', {})) != set(schema):
                raise NativeDistributedError('Ignite binary fields invalid')
            return model(**{k: bound(v) for k, v in data['fields'].items()})
        if not isinstance(data, str):
            raise NativeDistributedError('Exact value needs text')
        if kind == 'integer':
            result = int(data)
            if not -(2**63) <= result < 2**63:
                raise NativeDistributedError('Ignite integer outside int64')
            return result
        if kind == 'decimal':
            return Decimal(data)
        if kind == 'binary':
            return base64.b64decode(data, validate=True)
        if kind == 'uuid':
            return uuid.UUID(data)
        if kind in {'timestamp', 'date', 'time'}:
            cls = {'timestamp': datetime.datetime, 'date': datetime.date,
                   'time': datetime.time}[kind]
            return cls.fromisoformat(data)
        raise NativeDistributedError('Unsupported exact value')
    if type(value) is int and abs(value) > 2**53 - 1:
        raise NativeDistributedError('Use an exact integer envelope')
    if isinstance(value, float) and not math.isfinite(value):
        raise NativeDistributedError('Nonfinite parameter unavailable')
    return value


class IgniteDriverBackend(IgniteBackend):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.transactions = {}
        self._temporary_clients = contextvars.ContextVar(
            'ignite_temporary_clients', default=None)

    @staticmethod
    def _route(request):
        original = request.get('route') or request.get('_provider_route') or {}
        candidate = dict(original)
        if candidate.get('tls_mode') == 'verify-full':
            candidate['tls_mode'] = 'verify-ca'
        route = IgniteBackend._route({'route': candidate})
        if original.get('tls_mode') == 'verify-full':
            route['tls_mode'] = 'verify-full'
        if route.get(
                'tls_check_hostname') and route['tls_mode'] != 'verify-full':
            raise NativeDistributedError('Hostname checks require verify-full')
        if str(route.get('tls_min_version', '1.2')) not in {'1.2', '1.3'}:
            raise NativeDistributedError('Ignite minimum TLS version invalid')
        for host, port in route['contact_points']:
            if not host or not 1 <= port <= 65535:
                raise NativeDistributedError('Ignite endpoint invalid')
        return route

    def open_session(self, request):
        from .transport import connect
        route = self._route(request)
        client = self._with_secrets(
            route, lambda secrets: connect(self.module, route, secrets))
        self._clients.append(client)
        temporary = self._temporary_clients.get()
        if temporary is not None:
            temporary.append(client)
        return client

    def _temporary(self, callback, request):
        handles = []
        context = self._temporary_clients.set(handles)
        try:
            return callback(request)
        finally:
            self._temporary_clients.reset(context)
            failures = []
            for handle in handles:
                try:
                    self.close_session(handle)
                except Exception:
                    failures.append(True)
            if failures:
                raise NativeDistributedError('Ignite temporary cleanup failed')

    def list_resources(self, request):
        return self._temporary(super().list_resources, request)

    def apply_admin_operation(self, request):
        return self._temporary(super().apply_admin_operation, request)

    def read_admin_rows(self, request):
        return self._temporary(super().read_admin_rows, request)

    def inspect_admin_operation(self, request):
        return self._temporary(super().inspect_admin_operation, request)

    def validate_admin_post_state(self, request):
        return self._temporary(super().validate_admin_post_state, request)

    def control_transaction(self, handle, action):
        tx = self.transactions.get(id(handle))
        if action == 'begin':
            if tx is not None:
                raise NativeDistributedError('Ignite transaction already open')
            from pyignite.datatypes import TransactionConcurrency
            from pyignite.datatypes import TransactionIsolation
            route = handle._cdeadmin_route
            self.transactions[id(handle)] = handle.tx_start(
                concurrency=getattr(TransactionConcurrency,
                                    route['transaction_concurrency'].upper()),
                isolation=getattr(TransactionIsolation,
                                  route['transaction_isolation'].upper(
                                  ).replace('-', '_')),
                timeout=route['transaction_timeout'],
                label=route.get('transaction_label'))
        elif tx is not None:
            # Remove before invoking: a missing reply must never repeat a
            # decision.
            self.transactions.pop(id(handle))
            getattr(tx, action)()
        else:
            raise NativeDistributedError('Ignite transaction is not open')

    def describe_transaction(self, handle):
        return dict(super().describe_transaction(handle),
                    cache_transaction_open=id(handle) in self.transactions,
                    sql_enlisted_in_cache_transaction=False)

    def close_session(self, handle, unknown=False):
        tx = self.transactions.pop(id(handle), None)
        if tx is not None and not unknown:
            tx.rollback()
        handle.close()
        if handle in self._clients:
            self._clients.remove(handle)

    def iterate(self, handle, command, parameters):
        if not isinstance(command, dict):
            command = {'operation': 'sql', 'source': command}
        operation = command.get('operation')
        if operation != 'sql':
            command = dict(command)
            for key in ('key', 'value'):
                if key in command:
                    command[key] = bound(command[key])
            result = super().execute(handle, command, parameters)
            result.records = [{k: exact(v) for k, v in row.items()}
                              for row in result.records]
            result.native.update(row_offset=0, result_set_index=0,
                                 result_set_end=True)
            yield result
            return
        if id(handle) in self.transactions:
            raise NativeDistributedError(
                'Ignite SQL cannot join this cache transaction')
        args = parameters if parameters is not None else command.get(
            'parameters', [])
        if not isinstance(args, (list, tuple)):
            raise NativeDistributedError(
                'Ignite SQL needs positional bindings')
        with handle.sql(str(command.get('source', '')),
                        query_args=[bound(v) for v in args],
                        schema=command.get('schema', 'PUBLIC'), page_size=256,
                        include_field_names=True) as cursor:
            names = next(cursor, [])
            schema = {'columns': [{'name': str(n), 'key': 'c' + str(i),
                                   'ordinal': i} for i, n in enumerate(names)]}
            rows, size, offset = [], 0, 0
            for row in cursor:
                record = {'c' + str(i): exact(v) for i, v in enumerate(row)}
                length = len(json.dumps(record))
                if rows and (len(rows) >= 256 or size + length > 1048576):
                    yield NativeResult('key_value', 'entries', rows, schema,
                                       dict(row_offset=offset,
                                            result_set_index=0,
                                            result_set_end=False))
                    offset += len(rows)
                    rows, size = [], 0
                rows.append(record)
                size += length
            yield NativeResult('key_value', 'entries', rows, schema,
                               dict(row_offset=offset, result_set_index=0,
                                    result_set_end=True))


class IgniteDriver(RetainedNativeClient):
    transaction_actions = ('begin', 'commit', 'rollback')

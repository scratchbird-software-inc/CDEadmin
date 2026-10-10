"""Retained Milvus iterators, exact values and isolated no-replay channels."""
import base64
from collections import namedtuple
from collections.abc import Sequence
import json
import math
from pathlib import Path
import uuid

from .client import MilvusClientAdapter, MilvusClientError
from ..native_distributed import NativeResult
from ..retained_native import RetainedNativeClient


class MilvusNativeFailure(RuntimeError):
    """Not a grpc/Milvus exception: the SDK must not replay this failure."""


def exact(value):
    if isinstance(value, (bytes, bytearray)):
        return {'$binary': base64.b64encode(value).decode()}
    if type(value) is int and abs(value) > 2**53 - 1:
        return {'$integer': str(value)}
    if isinstance(value, float) and not math.isfinite(value):
        return {'$float': str(value)}
    if isinstance(value, dict):
        if value and all(type(k) is int for k in value):
            return {'$sparse': [[k, exact(v)] for k, v in value.items()]}
        return {str(k): exact(v) for k, v in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [exact(v) for v in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    callback = getattr(
        value,
        'to_dict',
        None) or getattr(
        value,
        'tolist',
        None)
    if callable(callback):
        return exact(callback())
    raise MilvusClientError('Milvus value lacks an exact representation')


def native(value):
    if isinstance(value, dict):
        if set(value) == {'$integer'}:
            text = value['$integer']
            number = int(text)
            if str(number) != text or not -(2**63) <= number < 2**63:
                raise MilvusClientError('Milvus Int64 invalid')
            return number
        if set(value) == {'$binary'}:
            return base64.b64decode(value['$binary'], validate=True)
        if set(value) == {'$float'}:
            if value['$float'] not in {'nan', 'inf', '-inf'}:
                raise MilvusClientError('Milvus float invalid')
            return float(value['$float'])
        if set(value) == {'$sparse'}:
            pairs = value['$sparse']
            result = {}
            for key, item in pairs:
                if type(key) is not int or key < 0 or key in result:
                    raise MilvusClientError('Sparse dimension invalid')
                result[key] = native(item)
            return result
        return {k: native(v) for k, v in value.items()}
    if isinstance(value, list):
        return [native(v) for v in value]
    return value


def no_replay_channel(route):
    import grpc

    class Details(namedtuple('Details', ('method', 'timeout', 'metadata',
                                         'credentials', 'wait_for_ready',
                                         'compression')),
                  grpc.ClientCallDetails):
        pass

    class Interceptor(grpc.UnaryUnaryClientInterceptor):
        def intercept_unary_unary(self, continuation, details, request):
            timeout = details.timeout or route['operation_timeout']
            call = continuation(Details(
                details.method, timeout, details.metadata,
                details.credentials, details.wait_for_ready,
                details.compression), request)
            try:
                response = call.result()
            except grpc.RpcError:
                raise MilvusNativeFailure(
                    'Milvus RPC outcome unknown') from None
            status = getattr(response, 'status', response)
            if getattr(status, 'error_code', 0) or getattr(status, 'code', 0):
                raise MilvusNativeFailure('Milvus server rejected RPC')
            return call

    target = f'{route["host"]}:{route["port"]}'
    options = [('grpc.enable_retries', 0),
               ('grpc.max_receive_message_length', 64 * 1024 * 1024),
               ('grpc.max_send_message_length', 64 * 1024 * 1024)]
    if route['keep_alive']:
        options.append(('grpc.keepalive_time_ms', 55000))
    if route.get('server_name'):
        options.append(('grpc.ssl_target_name_override', route['server_name']))
    if route['tls_mode'] == 'disable':
        channel = grpc.insecure_channel(target, options=options)
    else:
        def data(name):
            return Path(route[name]).read_bytes() if route.get(name) else None
        credentials = grpc.ssl_channel_credentials(
            root_certificates=data('tls_ca_file'),
            private_key=data('tls_key_file'),
            certificate_chain=data('tls_certificate_file'))
        channel = grpc.secure_channel(target, credentials, options=options)

    class OwnedChannel(grpc.Channel):
        # PyMilvus copies connection keyword arguments for idle reconnect.
        # An owned channel is not duplicable, and idle reconnect is disabled.
        def __deepcopy__(self, _memo):
            return self

        def subscribe(self, *args, **kwargs):
            return channel.subscribe(*args, **kwargs)

        def unsubscribe(self, *args, **kwargs):
            return channel.unsubscribe(*args, **kwargs)

        def unary_unary(self, *args, **kwargs):
            return intercepted.unary_unary(*args, **kwargs)

        def unary_stream(self, *args, **kwargs):
            return intercepted.unary_stream(*args, **kwargs)

        def stream_unary(self, *args, **kwargs):
            return intercepted.stream_unary(*args, **kwargs)

        def stream_stream(self, *args, **kwargs):
            return intercepted.stream_stream(*args, **kwargs)

        def close(self):
            channel.close()

    intercepted = grpc.intercept_channel(channel, Interceptor())
    return OwnedChannel()


class OwnedClient:
    def __init__(self, client, channel, alias, registry):
        self.client, self.channel, self.alias = client, channel, alias
        self.registry, self.closed = registry, False

    def __getattr__(self, name):
        return getattr(self.client, name)

    def close(self):
        if self.closed:
            return
        from pymilvus import connections
        self.client.close()
        connections.remove_connection(self.alias)
        self.channel.close()
        self.closed = True
        if self in self.registry:
            self.registry.remove(self)


class MilvusDriverBackend(MilvusClientAdapter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._owned_clients = []
        self._iterators = []

    def _connect(self, request):
        if self.module is None or self.module.__version__ != '2.6.5':
            raise MilvusClientError('Qualified PyMilvus 2.6.5 is required')
        route = self._route(request)
        alias = 'cde-' + uuid.uuid4().hex
        channel = no_replay_channel(route)

        def connect(secrets):
            return self._connector(
                uri=f'http://{route["host"]}:{route["port"]}',
                db_name=route['database'], alias=alias, channel=channel,
                timeout=route['connect_timeout'], keep_alive=False,
                user=route.get('username', ''),
                password=secrets.get('database_password', ''),
                token=secrets.get('api_token', ''))
        try:
            client = OwnedClient(self._with_credentials(route, connect),
                                 channel, alias, self._owned_clients)
            self._owned_clients.append(client)
            client.list_collections(timeout=route['operation_timeout'])
            return client, route
        except Exception:
            channel.close()
            from pymilvus import connections
            connections.remove_connection(alias)
            raise MilvusClientError('Milvus connection failed') from None

    def iterate(self, owner, command, parameters):
        if not isinstance(command, dict) or parameters:
            raise MilvusClientError('Milvus arguments belong in query JSON')
        options = native(dict(command))
        operation = options.pop('operation', 'search')
        if operation not in {'query', 'query_iterator', 'search',
                             'search_iterator', 'hybrid_search', 'get',
                             'insert', 'upsert', 'delete'}:
            raise MilvusClientError('Milvus operation unavailable')
        if owner.route['read_only'] and operation in {'insert', 'upsert',
                                                      'delete'}:
            raise MilvusClientError('Milvus read-only route refuses writes')
        options.setdefault('timeout', owner.route['operation_timeout'])
        options.setdefault(
            'consistency_level',
            owner.route['consistency_level'])
        options['retry_on_rate_limit'] = False
        if operation == 'hybrid_search':
            options['reqs'] = [self.module.AnnSearchRequest(**r)
                               for r in options['reqs']]
            ranker = options.pop('ranker', {'type': 'rrf'})
            if ranker['type'] == 'rrf':
                options['ranker'] = self.module.RRFRanker(ranker.get('k', 60))
            elif ranker['type'] == 'weighted':
                options['ranker'] = self.module.WeightedRanker(
                    *ranker['weights'])
            else:
                raise MilvusClientError('Milvus ranker unavailable')
        method = operation
        if operation == 'query' and options.get(
                'output_fields') != ['count(*)']:
            method = 'query_iterator'
        iterator = None
        try:
            if method.endswith('_iterator'):
                options.setdefault('batch_size', 256)
                iterator = getattr(owner.client, method)(**options)
                state = {'owner': owner, 'iterator': iterator}
                self._iterators.append(state)

                def next_batches():
                    while True:
                        value = iterator.next()
                        if not value:
                            return
                        yield value
                batches = next_batches()
            else:
                batches = [getattr(owner.client, method)(**options)]
            offset = 0
            for batch in batches:
                if not isinstance(batch, (list, dict)):
                    batch = [item.to_dict() for item in batch]
                rows = self._normalize_matches(batch)
                page, size = [], 0
                for row in rows:
                    row = exact(row)
                    length = len(json.dumps(row).encode())
                    if page and (len(page) >= 256 or size + length > 1048576):
                        yield self._page(page, operation, offset)
                        offset += len(page)
                        page, size = [], 0
                    page.append(row)
                    size += length
                if page:
                    yield self._page(page, operation, offset)
                    offset += len(page)
            owner.last_observation = f'native-{operation}-response-observed'
        finally:
            if iterator is not None:
                iterator.close()
                self._iterators.remove(state)

    @staticmethod
    def _page(rows, operation, offset):
        return NativeResult(
            'vector', 'matches', rows, {
                'operation': operation}, {
                'row_offset': offset, 'result_set_index': 0})

    def close_session(self, owner, _unknown=False):
        for state in list(self._iterators):
            if state['owner'] is owner:
                state['iterator'].close()
                self._iterators.remove(state)
        owner.client.close()
        owner.closed = True
        self._sessions.remove(owner)

    def close(self):
        for state in list(self._iterators):
            state['iterator'].close()
            self._iterators.remove(state)
        for owner in list(self._sessions):
            self.close_session(owner, True)
        for client in list(self._owned_clients):
            client.close()

    @staticmethod
    def complete(_request):
        return []


class MilvusDriver(RetainedNativeClient):
    def __getattr__(self, name):
        return getattr(self.backend, name)

    def inspect_resource(self, request):
        return self.backend.inspect_resource(request)

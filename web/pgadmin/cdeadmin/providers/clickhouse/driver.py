"""Retained ClickHouse HTTP sessions and typed ordinal streaming."""
import json
import uuid

from .client import ClickHouseClient, ClickHouseClientError
from ..analytic_stream import open_stream, lines
from ..native_distributed import NativeResult
from ..retained_native import RetainedNativeClient


class ClickHouseDriverBackend(ClickHouseClient):
    def open_session(self, request):
        owner = super().open_session(request)
        owner.route.setdefault('session_id', str(uuid.uuid4()))
        return owner

    def iterate(self, owner, source, parameters):
        if not isinstance(source, str):
            raise ClickHouseClientError('ClickHouse source must be SQL')
        query_id = str(uuid.uuid4())
        args = {
            'database': owner.route['database'], 'query_id': query_id,
            'session_id': owner.route['session_id'],
            'default_format': 'JSONCompactEachRowWithNamesAndTypes',
            'max_execution_time': owner.route['statement_timeout'],
            'output_format_json_quote_64bit_integers': 1,
            'output_format_json_quote_decimals': 1,
            'output_format_json_quote_denormals': 1,
            'max_result_rows': 0, 'result_overflow_mode': 'throw',
            'mutations_sync': 2, 'alter_sync': 2,
        }
        if owner.route['read_only']:
            args['readonly'] = 1
        for key in ('quota_key', 'role'):
            if owner.route.get(key):
                args[key] = owner.route[key]
        if parameters is not None and not isinstance(parameters, dict):
            raise ClickHouseClientError('ClickHouse parameters must be named')
        for name, value in (parameters or {}).items():
            args['param_' + name] = self._parameter_text(value)
        response = open_stream(self.transport,
                               owner.route,
                               '/',
                               source.encode(),
                               args,
                               {'X-ClickHouse-User': owner.route['username']})
        try:
            iterator = iter(lines(response))
            first = next(iterator, None)
            if first is None:
                owner.last_observation = 'native-response-observed'
                yield self._page([], [], query_id, 0)
                return
            names = json.loads(first)
            types = json.loads(next(iterator))
            if not isinstance(names, list) or not isinstance(types, list) or \
                    len(names) != len(types):
                raise ClickHouseClientError('ClickHouse stream schema invalid')
            columns = [{'name': n, 'type': t, 'ordinal': i}
                       for i, (n, t) in enumerate(zip(names, types))]
            page, size, offset = [], 0, 0
            for line in iterator:
                row = json.loads(line)
                if not isinstance(row, list) or len(row) != len(columns):
                    raise ClickHouseClientError(
                        'ClickHouse stream row invalid')
                if page and (len(page) >= 256 or size + len(line) > 1048576):
                    yield self._page(page, columns, query_id, offset)
                    offset += len(page)
                    page, size = [], 0
                page.append(row)
                size += len(line)
            yield self._page(page, columns, query_id, offset)
            owner.last_observation = 'native-response-observed'
        finally:
            response.close()
            response.release_conn()

    @staticmethod
    def _page(rows, columns, query_id, offset):
        return NativeResult('columnar', 'rows', rows, {'columns': columns},
                            {'query_id': query_id, 'row_offset': offset,
                             'result_set_index': 0})

    def close_session(self, owner, _unknown=False):
        if owner in self._sessions:
            self._sessions.remove(owner)

    @staticmethod
    def complete(_request):
        return []


class ClickHouseDriver(RetainedNativeClient):
    def __getattr__(self, name):
        return getattr(self.backend, name)

    def inspect_resource(self, request):
        return self.backend.inspect_resource(request)

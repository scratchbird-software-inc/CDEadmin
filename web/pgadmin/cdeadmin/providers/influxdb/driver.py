"""InfluxDB native JSONL query streams and explicit line-protocol writes."""
import json

from .client import InfluxDBClient, InfluxDBClientError
from ..analytic_stream import open_stream, lines
from ..native_distributed import NativeResult
from ..retained_native import RetainedNativeClient


def exact(value):
    if type(value) is int and abs(value) > 2**53 - 1:
        return {'$integer': str(value)}
    if isinstance(value, list):
        return [exact(v) for v in value]
    if isinstance(value, dict):
        return {k: exact(v) for k, v in value.items()}
    return value


def parameters_native(value):
    if isinstance(value, dict):
        if set(value) == {'$integer'}:
            text = value['$integer']
            if not isinstance(text, str) or str(int(text)) != text:
                raise InfluxDBClientError('Exact integer is invalid')
            return int(text)
        return {k: parameters_native(v) for k, v in value.items()}
    if isinstance(value, list):
        return [parameters_native(v) for v in value]
    return value


class InfluxDBDriverBackend(InfluxDBClient):
    def iterate(self, owner, command, parameters):
        if isinstance(command, dict) and command.get('operation') == 'write':
            if owner.route['read_only']:
                raise InfluxDBClientError('Read-only route refuses writes')
            if parameters:
                raise InfluxDBClientError('Write parameters belong in JSON')
            source = command.get('line_protocol')
            if not isinstance(source, str) or not source.strip():
                raise InfluxDBClientError('Line protocol text is required')
            precision = command.get('precision', 'ns')
            if precision not in {'ns', 'us', 'ms', 's'}:
                raise InfluxDBClientError('Write precision is invalid')
            query = {'db': owner.route['database'], 'precision': precision}
            for name in ('accept_partial', 'no_sync'):
                value = command.get(name, False)
                if not isinstance(value, bool):
                    raise InfluxDBClientError('Write flags must be booleans')
                query[name] = str(value).lower()
            self._request(
                owner.route,
                '/api/v3/write_lp',
                method='POST',
                query=query,
                body=source.encode(),
                mutating=True,
                headers={
                    'Content-Type': 'text/plain; charset=utf-8'})
            owner.last_observation = 'native-write-response-observed'
            yield self._page([], [], 0, 'write')
            return
        language = owner.route['query_language']
        if isinstance(command, dict):
            if command.get('operation') != 'query':
                raise InfluxDBClientError('InfluxDB JSON operation invalid')
            language = command.get('language', language)
            parameters = command.get('parameters', parameters)
            command = command.get('source')
        if language not in {'sql', 'influxql'} or not isinstance(command, str):
            raise InfluxDBClientError('InfluxDB query language/source invalid')
        if parameters is not None and not isinstance(parameters, dict):
            raise InfluxDBClientError('InfluxDB parameters must be named')
        body = json.dumps({'db': owner.route['database'], 'q': command,
                           'format': 'jsonl',
                           'params': parameters_native(parameters or {})})
        response = open_stream(self.transport, owner.route,
                               '/api/v3/query_' + language, body.encode(),
                               headers={'Content-Type': 'application/json'})
        page, columns, size, offset = [], [], 0, 0
        try:
            for line in lines(response):
                row = exact(json.loads(line))
                if not isinstance(row, dict):
                    raise InfluxDBClientError(
                        'InfluxDB point must be an object')
                if page and (len(page) >= 256 or size + len(line) > 1048576):
                    yield self._page(page, columns, offset, language)
                    offset += len(page)
                    page, size = [], 0
                for name in row:
                    if name not in [c['name'] for c in columns]:
                        columns.append({'name': name, 'type': 'native-json'})
                page.append(row)
                size += len(line)
            yield self._page(page, columns, offset, language)
            owner.last_observation = 'native-query-response-observed'
        finally:
            response.close()
            response.release_conn()

    @staticmethod
    def _page(rows, columns, offset, language):
        return NativeResult('time_series', 'points', rows,
                            {'columns': list(columns), 'time_field': 'time'},
                            {'row_offset': offset, 'language': language,
                             'result_set_index': 0})

    def close_session(self, owner, _unknown=False):
        owner.close()
        if owner in self._sessions:
            self._sessions.remove(owner)

    @staticmethod
    def complete(_request):
        return []


class InfluxDBDriver(RetainedNativeClient):
    def execute(self, session, request):
        language = request.get('language') or request.get('language_profile')
        if language:
            source = request.get('source')
            try:
                parsed = json.loads(source)
            except (ValueError, TypeError):
                parsed = source
            if not isinstance(parsed, dict):
                selected = self.backend._language(
                    language, session.handle.route['query_language'])
                request = dict(request, source=json.dumps({
                    'operation': 'query', 'language': selected,
                    'source': source, 'parameters': request.get('parameters'),
                }))
        return super().execute(session, request)

    def __getattr__(self, name):
        return getattr(self.backend, name)

    def inspect_resource(self, request):
        return self.backend.inspect_resource(request)

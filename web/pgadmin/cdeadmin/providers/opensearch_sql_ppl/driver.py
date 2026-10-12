"""Retained SQL cursor ownership and native PPL result limits."""
import json

from .client import OpenSearchSQLPPLClient, OpenSearchSQLPPLClientError
from ..opensearch.driver import exact, native, pages
from ..opensearch.transport import OpenSearchHTTPTransport
from ..retained_native import RetainedNativeClient


class OpenSearchSQLPPLDriverBackend(OpenSearchSQLPPLClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        previous = self.transport
        self.transport = OpenSearchHTTPTransport(
            previous.secret_acquirer, urlopen=previous._urlopen)
        previous.close()
        self._cursors = []

    @staticmethod
    def _route(request):
        route = OpenSearchSQLPPLClient._route(request)
        supplied = request.get('route', request)
        route['explicit_fetch_size'] = supplied.get('fetch_size') is not None
        if not route['explicit_fetch_size']:
            route['fetch_size'] = 256
        return route

    def _clear_cursor(self, state):
        response = self._request(
            state['owner'].route, '/_plugins/_sql/close', method='POST',
            json_body={'cursor': state['id']}, mutating=True).json()
        if not response.get('succeeded'):
            raise OpenSearchSQLPPLClientError('Cursor cleanup not confirmed')
        self._cursors.remove(state)

    def iterate(self, owner, command, parameters):
        options = command if isinstance(command, dict) else {'source': command}
        source = options.get('source')
        if not isinstance(source, str) or not source.strip():
            raise OpenSearchSQLPPLClientError('Query source required')
        language = self._language(options.get('language'),
                                  owner.route['query_language'])
        body = {'query': source}
        if (language == 'sql' or owner.route['explicit_fetch_size']
                or 'fetch_size' in options):
            amount = options.get('fetch_size', owner.route['fetch_size'])
            if type(amount) is not int or not 1 <= amount <= 10000:
                raise OpenSearchSQLPPLClientError(
                    'Fetch size must be 1..10000')
            body['fetch_size'] = amount
        bindings = options.get('parameters', parameters)
        if bindings:
            if not isinstance(bindings, (dict, list)):
                raise OpenSearchSQLPPLClientError('Invalid query parameters')
            body['parameters'] = native(bindings)
        if owner.route.get('data_source'):
            body['datasource'] = owner.route['data_source']
        endpoint = '/_plugins/_' + language
        state, offset, columns = None, 0, []
        try:
            while True:
                document = self._request(
                    owner.route, endpoint, method='POST', query={
                        'format': 'jdbc'}, json_body=body).json()
                cursor = document.get('cursor')
                if cursor:
                    if state is None:
                        state = {'owner': owner, 'id': cursor}
                        self._cursors.append(state)
                    state['id'] = cursor
                elif state is not None:
                    self._cursors.remove(state)
                    state = None
                columns = document.get('schema', columns)
                rows = document.get('datarows', document.get('rows', []))
                if not isinstance(rows, list):
                    raise OpenSearchSQLPPLClientError('Invalid native rows')
                metadata = exact({k: v for k, v in document.items()
                                  if k not in {
                                 'datarows', 'rows', 'cursor', 'schema'}})
                metadata.update(
                    language=language,
                    cursor_supported=language == 'sql',
                    server_limit_applies=True)
                yield from pages(rows, 'columnar', 'rows',
                                 {'columns': columns}, metadata, offset)
                offset += len(rows)
                if not cursor:
                    break
                if language != 'sql':
                    raise OpenSearchSQLPPLClientError('Unexpected PPL cursor')
                body = {'cursor': cursor}
            owner.last_observation = 'native-query-response-observed'
        finally:
            if state is not None:
                self._clear_cursor(state)

    def close_session(self, owner, _unknown=False):
        for state in list(self._cursors):
            if state['owner'] is owner:
                self._clear_cursor(state)
        owner.close()
        if owner in self._sessions:
            self._sessions.remove(owner)

    def close(self):
        for state in list(self._cursors):
            self._clear_cursor(state)
        super().close()

    @staticmethod
    def complete(_request):
        return []


class OpenSearchSQLPPLDriver(RetainedNativeClient):
    def execute(self, session, request):
        language = request.get('language') or request.get('language_profile')
        if language:
            request = dict(request)
            source = request.get('source')
            try:
                command = json.loads(source)
            except (ValueError, TypeError):
                command = {'source': source}
            if isinstance(command, dict):
                command.setdefault('language', language)
                request['source'] = json.dumps(command)
        return super().execute(session, request)

    def __getattr__(self, name):
        return getattr(self.backend, name)

    def inspect_resource(self, request):
        return self.backend.inspect_resource(request)

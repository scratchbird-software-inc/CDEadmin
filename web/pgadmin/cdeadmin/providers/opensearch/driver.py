"""Retained native REST, scroll ownership and bulk item observations."""
import json
from urllib.parse import quote

from .client import OpenSearchClient, OpenSearchClientError
from ..native_distributed import NativeResult
from ..opensearch.transport import OpenSearchHTTPTransport
from ..retained_native import RetainedNativeClient


def exact(value):
    if type(value) is int and abs(value) > 2**53 - 1:
        return {'$integer': str(value)}
    if isinstance(value, dict):
        return {k: exact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [exact(v) for v in value]
    return value


def native(value):
    if isinstance(value, dict):
        if set(value) == {'$integer'}:
            text = value['$integer']
            if not isinstance(text, str) or str(int(text)) != text:
                raise OpenSearchClientError('Exact JSON integer invalid')
            return int(text)
        return {k: native(v) for k, v in value.items()}
    if isinstance(value, list):
        return [native(v) for v in value]
    return value


def pages(rows, kind, field, schema, metadata, offset=0):
    page, size = [], 0
    for row in rows:
        row = exact(row)
        length = len(json.dumps(row).encode())
        if page and (len(page) >= 256 or size + length > 1048576):
            yield NativeResult(kind, field, page, schema,
                               dict(metadata, row_offset=offset,
                                    result_set_index=0))
            offset += len(page)
            page, size = [], 0
        page.append(row)
        size += length
    yield NativeResult(kind, field, page, schema,
                       dict(metadata, row_offset=offset, result_set_index=0))


class OpenSearchDriverBackend(OpenSearchClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        previous = self.transport
        self.transport = OpenSearchHTTPTransport(
            previous.secret_acquirer, urlopen=previous._urlopen)
        previous.close()
        self._scrolls = []

    def _clear_scroll(self, state):
        self._request(state['route'], '/_search/scroll', method='DELETE',
                      json_body={'scroll_id': [state['id']]}, mutating=True)
        if state in self._scrolls:
            self._scrolls.remove(state)

    def iterate(self, owner, command, parameters):
        if not isinstance(command, dict):
            raise OpenSearchClientError('Native query must be JSON')
        command, parameters = native(command), native(parameters or {})
        if not isinstance(parameters, dict):
            raise OpenSearchClientError('Native parameters must be named')
        operation = command.get('operation', 'search')
        index = command.get('index', parameters.get('index',
                                                    owner.route.get('index')))
        path = '/' + quote(index, safe='*,') if index else ''
        if operation == 'request':
            method, path = command.get('method', 'GET'), command.get('path')
            if method not in {'GET', 'HEAD', 'POST', 'PUT', 'DELETE', 'PATCH'}:
                raise OpenSearchClientError('Native HTTP method invalid')
            if not isinstance(path, str) or not path.startswith('/') or \
                    path.startswith('//') or any(c in path for c in '?#\r\n'):
                raise OpenSearchClientError(
                    'Native REST path must be relative')
            mutating = method not in {'GET', 'HEAD'}
            if owner.route['read_only'] and mutating:
                raise OpenSearchClientError('Read-only route refuses mutation')
            body = command.get('body')
            options = {'json_body': body}
            if isinstance(body, str):
                options = {'body': body, 'headers': {
                    'Content-Type': 'application/x-ndjson'}}
            response = self._request(owner.route, path, method=method,
                                     query=command.get('query'),
                                     mutating=mutating, **options)
            document = response.json() if response.body else {
                'status': response.status}
            yield from pages([document], 'search', 'hits', {},
                             {'operation': operation,
                              'status': response.status})
            return
        if operation == 'bulk':
            if owner.route['read_only']:
                raise OpenSearchClientError('Read-only route refuses bulk')
            actions = command.get('actions')
            if not isinstance(actions, list) or not actions:
                raise OpenSearchClientError('Bulk actions are required')
            body = '\n'.join(json.dumps(a) for a in actions) + '\n'
            document = self._request(
                owner.route, path + '/_bulk', method='POST', body=body,
                query=command.get('query'), mutating=True,
                headers={'Content-Type': 'application/x-ndjson'}).json()
            yield from pages(document['items'], 'search', 'hits', {},
                             {'operation': operation,
                              'bulk_errors': document.get('errors'),
                              'took': document.get('took')})
            return
        if operation not in {'search', 'scan'}:
            raise OpenSearchClientError('Native operation unavailable')
        body = dict(
            command.get(
                'body',
                {})) if 'operation' in command else dict(command)
        scan = operation == 'scan'
        query = dict(
            command.get(
                'query',
                {})) if 'operation' in command else {}
        state, offset = None, 0
        if scan:
            amount = command.get('batch_size', 256)
            if type(amount) is not int or not 1 <= amount <= 256:
                raise OpenSearchClientError('Scroll batch size must be 1..256')
            body['size'] = amount
            body.setdefault('sort', ['_doc'])
            query['scroll'] = command.get('scroll', '1m')
        try:
            document = self._request(owner.route, path + '/_search',
                                     method='POST', json_body=body,
                                     query=query).json()
            while True:
                if scan and document.get('_scroll_id'):
                    if state is None:
                        state = {
                            'route': owner.route,
                            'owner': owner,
                            'id': None}
                        self._scrolls.append(state)
                    state['id'] = document['_scroll_id']
                hits = document.get('hits', {}).get('hits', [])
                if 'semantic_rows' in body.get('aggs', {}):
                    hits = self._semantic_aggregation_rows(
                        document, parameters.get('semantic_axes', []),
                        parameters.get('semantic_count_measures', []))
                partial = bool(document.get('timed_out') or
                               document.get('_shards', {}).get('failed'))
                metadata = exact({k: v for k, v in document.items()
                                  if k not in {'hits', '_scroll_id'}})
                metadata.update(operation=operation, partial=partial,
                                total=exact(document.get('hits', {}).get(
                                    'total')))
                yield from pages(hits, 'search', 'hits', metadata, metadata,
                                 offset)
                offset += len(hits)
                if scan and partial:
                    raise OpenSearchClientError('Partial scroll result')
                if not scan or not hits:
                    break
                if state is None:
                    raise OpenSearchClientError('Scroll continuation missing')
                document = self._request(
                    owner.route, '/_search/scroll', method='POST',
                    json_body={'scroll_id': state['id'],
                               'scroll': query['scroll']}).json()
            owner.last_observation = 'native-response-observed'
        finally:
            if state is not None:
                self._clear_scroll(state)

    def close_session(self, owner, _unknown=False):
        for state in list(self._scrolls):
            if state['owner'] is owner:
                self._clear_scroll(state)
        owner.close()
        if owner in self._sessions:
            self._sessions.remove(owner)

    def close(self):
        for state in list(self._scrolls):
            self._clear_scroll(state)
        super().close()

    @staticmethod
    def complete(_request):
        return []


class OpenSearchDriver(RetainedNativeClient):
    def __getattr__(self, name):
        return getattr(self.backend, name)

    def inspect_resource(self, request):
        return self.backend.inspect_resource(request)

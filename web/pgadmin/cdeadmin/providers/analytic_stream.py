"""Owned, no-retry HTTP streams for native analytic query drivers."""
import gzip
import urllib.parse

import urllib3

from pgadmin.cdeadmin.transports.analytics_http import AnalyticHTTPError


def open_stream(transport, route, path, body, query=None, headers=None):
    scheme = 'http' if route['tls_mode'] == 'disable' else 'https'
    url = f'{scheme}://{route["host"]}:{route["port"]}{path}'
    if query:
        url += '?' + urllib.parse.urlencode(query)
    headers = dict(headers or {})
    if route.get('http_compression') == 'gzip':
        body = gzip.compress(body)
        headers.update({'Content-Encoding': 'gzip', 'Accept-Encoding': 'gzip'})

    def connect(secrets):
        native_headers = dict(headers or {})
        transport._authorize(route, 'POST', url, body, native_headers, secrets)
        # Authentication is leased until dispatch has returned the response.
        # A stream owns its connection until closed; there is no request
        # replay.
        response = transport._pool(route, secrets).request(
            'POST', url, body=body, headers=native_headers,
            timeout=urllib3.Timeout(connect=route['connect_timeout'],
                                    read=route['statement_timeout']),
            retries=False, redirect=False, preload_content=False,
            decode_content=True)
        if not 200 <= response.status < 300:
            status = response.status
            response.close()
            response.release_conn()
            raise AnalyticHTTPError(
                'Native HTTP request failed', status=status)
        return response

    return transport._with_secrets(route, connect)


def lines(response, maximum=16 * 1024 * 1024):
    buffer = b''
    for chunk in response.stream(65536, decode_content=True):
        buffer += chunk
        while b'\n' in buffer:
            line, buffer = buffer.split(b'\n', 1)
            if len(line) > maximum:
                raise AnalyticHTTPError('Native response line exceeds bound')
            if line.strip():
                yield line
        if len(buffer) > maximum:
            raise AnalyticHTTPError('Native response line exceeds bound')
    if buffer.strip():
        yield buffer

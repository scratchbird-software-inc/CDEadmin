"""Discard incomplete HTTP responses before returning a pooled connection."""
import urllib3

from ...transports.analytics_http import (
    AnalyticHTTPError, BoundedJSONHTTPTransport)


class OpenSearchHTTPTransport(BoundedJSONHTTPTransport):
    def _pooled_request(self, route, method, url, body, headers, secrets):
        response = self._pool(route, secrets).request(
            method, url, body=body, headers=headers,
            timeout=urllib3.Timeout(connect=route['connect_timeout'],
                                    read=route['statement_timeout']),
            retries=False, redirect=False, preload_content=False)
        try:
            payload = response.read(self.max_response_bytes + 1)
            if len(payload) > self.max_response_bytes:
                raise AnalyticHTTPError('Response exceeds admitted size')
            status, response_headers = int(response.status), response.headers
            if status >= 400:
                raise AnalyticHTTPError(
                    f'Native HTTP request failed ({status})', status=status,
                    native_payload=payload)
            return payload, status, response_headers
        finally:
            # Close also discards partial data after read/decode exceptions.
            # urllib3 has already returned fully consumed responses to its
            # pool.
            response.close()
            response.release_conn()

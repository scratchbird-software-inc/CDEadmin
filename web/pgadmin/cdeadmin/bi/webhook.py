##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Signed, SSRF-guarded webhook delivery for BI alerts and subscriptions.

* The destination host must be on a server-side allow-list; each entry also
  holds the HMAC key for that host (never shown to users).
* The host is resolved once, every address must be globally routable, and
  the connection is pinned to the chosen address (TLS still verifies the
  host name), so a second DNS answer cannot redirect the request.
* No redirect is followed, the timeout is short and the response body is
  not kept.
* The body is signed with HMAC-SHA256 over ``<timestamp>.<body>``.
"""

from __future__ import annotations

import hashlib
import hmac
import http.client
import ipaddress
import json
import socket
import ssl
import time
from urllib.parse import urlsplit

SIGNATURE_VERSION = 'v1'
MAX_BODY_BYTES = 256 * 1024
MAX_URL_LENGTH = 1024
DEFAULT_TIMEOUT = 5.0
MAX_TIMEOUT = 15.0


class WebhookError(RuntimeError):
    """A webhook was refused or failed; ``code`` is a stable reason."""

    def __init__(self, code, message=None, *, outcome_unknown=False):
        super().__init__(message or code)
        self.code = code
        self.outcome_unknown = outcome_unknown


def public_address(text):
    """The parsed address when it is publicly routable, otherwise ``None``.

    IPv4-mapped, 6to4 and Teredo IPv6 forms are judged by the IPv4 address
    they carry.
    """
    try:
        address = ipaddress.ip_address(text.split('%', 1)[0])
    except ValueError:
        return None
    candidates = [address]
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            candidates.append(address.ipv4_mapped)
        if address.sixtofour is not None:
            candidates.append(address.sixtofour)
        if address.teredo is not None:
            candidates.extend(address.teredo)
    for item in candidates:
        if (item.is_private or item.is_loopback or item.is_link_local or
                item.is_multicast or item.is_reserved or
                item.is_unspecified or not item.is_global):
            return None
    return address


class PinnedHTTPSTransport:
    """POST to an already-validated address; TLS names the original host."""

    def post(self, *, address, port, host, target, headers, body, timeout):
        context = ssl.create_default_context()

        class Pinned(http.client.HTTPSConnection):
            def connect(self_inner):  # noqa: N805
                raw = socket.create_connection((address, port), timeout)
                self_inner.sock = context.wrap_socket(
                    raw, server_hostname=host)

        connection = Pinned(host, port, timeout=timeout, context=context)
        try:
            connection.request('POST', target, body=body, headers=headers)
            response = connection.getresponse()
            response.read(4096)
            return response.status
        finally:
            connection.close()


class WebhookChannel:
    """Validate, sign and send one webhook."""

    def __init__(self, hosts=None, *, resolver=None, transport=None,
                 clock=time.time, timeout=DEFAULT_TIMEOUT):
        self.hosts = self._hosts(hosts or {})
        self.resolver = resolver or socket.getaddrinfo
        self.transport = transport or PinnedHTTPSTransport()
        self.clock = clock
        self.timeout = max(0.5, min(float(timeout), MAX_TIMEOUT))

    @staticmethod
    def _hosts(raw):
        if not isinstance(raw, dict) or len(raw) > 64:
            raise WebhookError('configuration',
                               'webhook hosts must be an object')
        hosts = {}
        for name, entry in raw.items():
            if not isinstance(name, str) or not isinstance(entry, dict):
                raise WebhookError('configuration', 'webhook host is invalid')
            host = name.strip().lower().rstrip('.')
            try:
                ipaddress.ip_address(host)
            except ValueError:
                pass
            else:
                raise WebhookError('configuration',
                                   'webhook hosts must be names, not IPs')
            secret = entry.get('secret')
            if not isinstance(secret, str) or len(secret) < 16:
                raise WebhookError(
                    'configuration',
                    'a webhook host needs a secret of 16+ characters')
            port = entry.get('port', 443)
            if isinstance(port, bool) or not isinstance(port, int) or not (
                    1 <= port <= 65535):
                raise WebhookError('configuration', 'webhook port is invalid')
            key_id = str(entry.get('key_id', 'default'))[:32]
            hosts[host] = {'secret': secret.encode('utf-8'), 'port': port,
                           'key_id': key_id,
                           'label': str(entry.get('label', host))[:128]}
        return hosts

    def catalog(self):
        return [{'host': host, 'label': entry['label']}
                for host, entry in sorted(self.hosts.items())]

    # validation -------------------------------------------------------------
    def check_url(self, url):
        """``(host, port, target)`` for an admitted URL, or a refusal."""
        if not isinstance(url, str) or not url or len(url) > MAX_URL_LENGTH:
            raise WebhookError('url_invalid', 'webhook URL is invalid')
        if any(ord(ch) < 33 or ord(ch) == 127 for ch in url):
            raise WebhookError('url_invalid', 'webhook URL is invalid')
        try:
            parts = urlsplit(url)
            port = parts.port
        except ValueError:
            raise WebhookError('url_invalid',
                               'webhook URL is invalid') from None
        if parts.scheme != 'https':
            raise WebhookError('url_scheme', 'webhook URLs must use https')
        if parts.username is not None or parts.password is not None:
            raise WebhookError('url_userinfo',
                               'webhook URLs must not carry credentials')
        if parts.fragment:
            raise WebhookError('url_invalid', 'webhook URL is invalid')
        host = (parts.hostname or '').lower().rstrip('.')
        entry = self.hosts.get(host)
        if not host or entry is None:
            raise WebhookError('host_not_allowed',
                               'webhook host is not on the allow-list')
        if port is not None and port != entry['port']:
            raise WebhookError('host_not_allowed',
                               'webhook port is not allowed')
        target = parts.path or '/'
        if parts.query:
            target += '?' + parts.query
        return host, entry['port'], target

    def resolve(self, host, port):
        """Resolve once; every answer must be public.  Returns the pin."""
        try:
            answers = self.resolver(host, port, type=socket.SOCK_STREAM)
        except OSError:
            raise WebhookError('dns_failed',
                               'webhook host did not resolve') from None
        addresses = []
        for answer in answers:
            text = answer[4][0]
            if public_address(text) is None:
                raise WebhookError(
                    'address_refused',
                    'webhook host resolves to a non-public address')
            addresses.append(text)
        if not addresses:
            raise WebhookError('dns_failed', 'webhook host did not resolve')
        return addresses[0]

    # signing ----------------------------------------------------------------
    def sign(self, host, body, timestamp):
        entry = self.hosts[host]
        digest = hmac.new(entry['secret'],
                          str(timestamp).encode('ascii') + b'.' + body,
                          hashlib.sha256).hexdigest()
        return f'{SIGNATURE_VERSION}={digest}'

    @staticmethod
    def encode(payload):
        body = json.dumps(payload, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=True, default=str).encode('ascii')
        if len(body) > MAX_BODY_BYTES:
            raise WebhookError('body_too_large',
                               'webhook body exceeds its limit')
        return body

    # sending ----------------------------------------------------------------
    def prepare(self, url):
        """Validate and resolve without sending (used by dry runs)."""
        host, port, target = self.check_url(url)
        return host, port, target, self.resolve(host, port)

    def send(self, url, payload, delivery_id):
        host, port, target, address = self.prepare(url)
        body = self.encode(payload)
        timestamp = int(self.clock())
        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'CDEadmin-BI/1',
            'X-CDEadmin-Timestamp': str(timestamp),
            'X-CDEadmin-Signature': self.sign(host, body, timestamp),
            'X-CDEadmin-Key-Id': self.hosts[host]['key_id'],
            'X-CDEadmin-Delivery': delivery_id,
        }
        try:
            status = self.transport.post(
                address=address, port=port, host=host, target=target,
                headers=headers, body=body, timeout=self.timeout)
        except Exception:
            # the request may have reached the receiver
            raise WebhookError('transport_failed', 'webhook request failed',
                               outcome_unknown=True) from None
        if 300 <= status < 400:
            raise WebhookError('redirect_refused',
                               'webhook redirects are not followed',
                               outcome_unknown=True)
        if not 200 <= status < 300:
            raise WebhookError('http_error',
                               f'webhook receiver answered {status}',
                               outcome_unknown=status >= 500)
        return {'transport': 'webhook', 'host': host, 'status': status}

"""Compression is used only when the server's greeting offers it.

Connector/Python 26.7 switched to the compressed protocol whenever compress was
requested; Dolt 1.86.6 and Vitess 23.0.3 do not advertise CLIENT_COMPRESS, and
the handshake then hung (live on the demos, 2026-11-04).
"""
import struct
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

import pytest  # noqa: E402

pytest.importorskip('mysql.connector')
from mysql.connector.connection import MySQLConnection  # noqa: E402
from mysql.connector.constants import ClientFlag  # noqa: E402
from mysql.connector.protocol import MySQLProtocol  # noqa: E402

from pgadmin.cdeadmin.providers.mysql_family.mysql_connections import (  # noqa: E402
    install_compression_negotiation,
)


def greeting(capabilities, version=b'8.0.33'):
    """A protocol-10 server greeting with the given capability flags."""
    body = (b'\x0a' + version + b'\x00' + struct.pack('<I', 7) + b'abcdefgh' + b'\x00' +
            struct.pack('<H', capabilities & 0xffff) + b'\x21' + struct.pack('<H', 2) +
            struct.pack('<H', capabilities >> 16) + b'\x15' + b'\x00' * 10 + b'ijklmnopqrst\x00' +
            b'mysql_native_password\x00')
    return struct.pack('<I', len(body))[:3] + b'\x00' + body


class Socket:
    def __init__(self, packet):
        self.packet = packet

    def recv(self):
        return self.packet


def handshake(capabilities):
    install_compression_negotiation()
    connection = MySQLConnection()
    connection._protocol = MySQLProtocol()
    connection._socket = Socket(greeting(capabilities))
    connection._ssl_disabled = True
    connection._client_flags |= ClientFlag.COMPRESS
    connection._compress = True
    connection._do_handshake()
    return connection


BASE = ClientFlag.PROTOCOL_41 | ClientFlag.SECURE_CONNECTION | ClientFlag.PLUGIN_AUTH


def test_compression_is_dropped_when_the_server_does_not_offer_it():
    connection = handshake(BASE)
    assert not connection._client_flags & ClientFlag.COMPRESS
    assert connection._compress is False


def test_compression_is_kept_when_the_server_offers_it():
    connection = handshake(BASE | ClientFlag.COMPRESS)
    assert connection._client_flags & ClientFlag.COMPRESS
    assert connection._compress is True

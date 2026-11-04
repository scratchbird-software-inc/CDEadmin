"""Connection attributes reach the MySQL handshake length-encoded, in bytes.

Connector/Python 26.7 packs each attribute length and their total into one
byte, so the provider's observer attribute plus any user attribute failed the
handshake ("'B' format requires 0 <= number <= 255"; live on the Dolt, TiDB and
Vitess demos, 2026-11-04).
"""
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
from mysql.connector.protocol import MySQLProtocol  # noqa: E402
from mysql.connector.utils import read_lc_int, read_lc_string  # noqa: E402

from pgadmin.cdeadmin.providers.mysql_family.mysql_connections import (  # noqa: E402
    encode_conn_attrs, install_conn_attrs_encoding,
)


def decode(packet):
    rest, total = read_lc_int(packet)
    assert len(rest) == total
    attributes = {}
    while rest:
        rest, key = read_lc_string(rest)
        rest, value = read_lc_string(rest)
        attributes[key.decode('utf-8')] = value.decode('utf-8')
    return attributes


def test_short_ascii_attributes_keep_the_connector_bytes():
    # The bytes Connector/Python 26.7 itself writes for these attributes.
    assert encode_conn_attrs({'_os': 'Linux', 'a': ''}) == b'\r\x03_os\x05Linux\x01a\x00'


def test_long_and_non_ascii_attributes_round_trip():
    attributes = {'_client_name': 'mysql-connector-python', '_client_version': '9.0.0',
                  'scratchrobin_0123456789abcdef': 'f' * 48, 'program_name': 'cdeadmin-rt',
                  'note': 'é' * 200, 'blank': None}
    packet = encode_conn_attrs(dict(attributes))
    assert len(packet) > 255
    assert decode(packet) == {**attributes, 'blank': ''}


def test_installed_encoder_accepts_attributes_past_one_byte():
    install_conn_attrs_encoding()
    attributes = {'scratchrobin_0123456789abcdef': 'f' * 48, 'program_name': 'x' * 300}
    assert decode(MySQLProtocol.make_conn_attrs(dict(attributes))) == attributes

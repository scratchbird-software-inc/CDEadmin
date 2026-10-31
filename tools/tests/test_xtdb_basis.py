"""XTDB database names from the snapshot token, and the typed first
document (providers/xtdb/basis.py, providers/xtdb/client.py)."""
import base64
import datetime
import decimal
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.providers.xtdb import basis  # noqa: E402
from pgadmin.cdeadmin.providers.xtdb.client import (  # noqa: E402
    XTDBClientError, _initial_document,
)

# SHOW SNAPSHOT_TOKEN on the 2.1.0 demo with probe_db1 attached (live).
TWO_DATABASES = 'ChYKBHh0ZGISDgoMCKbGl9cGEInswZoBCg8KCXByb2JlX2RiMRICCgA='
# The same server with only the primary database.
PRIMARY_ONLY = 'ChUKBHh0ZGISDQoLCK/Fl9cGEOva7A0='


def test_captured_tokens_name_every_attached_database():
    assert basis.database_names(TWO_DATABASES) == ['probe_db1', 'xtdb']
    assert basis.database_names(PRIMARY_ONLY) == ['xtdb']


@pytest.mark.parametrize('token, reason', [
    (None, 'no snapshot token'),
    ('not base64!', 'not base64'),
    (base64.b64encode(b'\x0a\x05\x0a\x03ab').decode(), 'truncated'),
    (base64.b64encode(b'\x0a\x02\x12\x00').decode(), 'no database name'),
    (base64.b64encode(b'').decode(), 'no snapshot token'),
    (base64.b64encode(b'\x12\x00').decode(), 'names no database'),
])
def test_unreadable_tokens_are_reported_not_empty(token, reason):
    with pytest.raises(basis.Unread, match=reason):
        basis.database_names(token)


def test_first_document_is_typed_by_its_grid_rows():
    assert _initial_document({'document_fields': [
        {'name': '_id', 'value_type': 'integer', 'value': '7'},
        {'name': 'item', 'value': 'bolt'},
        {'name': 'price', 'value_type': 'decimal', 'value': '2.50'},
        {'name': 'rush', 'value_type': 'boolean', 'value': 'TRUE'},
        {'name': 'due', 'value_type': 'date', 'value': '2026-12-01'},
        {'name': 'tags', 'value_type': 'nested', 'value': '{"bin": "A4"}'},
    ]}) == {'_id': 7, 'item': 'bolt', 'price': decimal.Decimal('2.50'),
            'rush': True, 'due': datetime.date(2026, 12, 1),
            'tags': {'bin': 'A4'}}
    # The values mapping the live gate sends still works.
    assert _initial_document({'values': {'_id': 1}}) == {'_id': 1}


@pytest.mark.parametrize('rows, reason', [
    ([{'name': 'a', 'value_type': 'integer', 'value': '1.5'}],
     'not a valid integer'),
    ([{'name': 'a', 'value_type': 'boolean', 'value': 'yes'}],
     'not a valid boolean'),
    ([{'name': 'a', 'value_type': 'nested', 'value': '3'}],
     'not a valid nested'),
    ([{'name': 'a', 'value_type': 'money', 'value': '3'}], 'one of'),
    ([{'name': 'a', 'value': '1'}, {'name': 'a', 'value': '2'}],
     'repeated'),
])
def test_bad_rows_are_refused(rows, reason):
    with pytest.raises(XTDBClientError, match=reason):
        _initial_document({'document_fields': rows})

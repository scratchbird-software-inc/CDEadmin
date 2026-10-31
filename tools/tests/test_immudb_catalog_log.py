"""immudb catalog-log reader, on entries captured live from 1.11.0."""
import base64
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

from pgadmin.cdeadmin.providers.immudb import catalog_log  # noqa: E402


def ids(*values):
    return b''.join(value.to_bytes(4, 'big') for value in values)


TABLE_T = (b'\x02CTL.TABLE.' + ids(1, 2), b't')
# Captured on the demo, 2026-10-31.
COLUMNS = [
    (b'\x02CTL.COLUMN.' + ids(1, 2, 1) + b'INTEGER',
     b'\x02\x00\x00\x00\x08id'),
    (b'\x02CTL.COLUMN.' + ids(1, 2, 2) + b'VARCHAR',
     b"\x05\x00\x00\x00 \x00\x04name'x'"),
    (b'\x02CTL.COLUMN.' + ids(1, 2, 3) + b'FLOAT',
     b'\x04\x00\x00\x00\x08\x00\x05score1.5'),
    (b'\x02CTL.COLUMN.' + ids(1, 2, 4) + b'TIMESTAMP',
     b'\x04\x00\x00\x00\x08\x00\x02tsnow()'),
]
CHECKS = [
    (b'\x02CTL.CHECK.' + ids(1, 2, 0), b'\x02pos(score >= 0)\x00'),
    (b'\x02CTL.CHECK.' + ids(1, 2, 1), b'\x07t_check1(id > 0)\x00'),
]
ROW = (b'\x02R.' + ids(1, 2, 0) + b'\x80\x01', b'row bytes')


def entry(key, value=b'', deleted=False):
    item = {'key': base64.b64encode(key).decode(),
            'value': base64.b64encode(value).decode()}
    if deleted:
        item['metadata'] = {'deleted': True}
    return item


class Log:
    """TxScan over a list of transactions; records the reads made."""

    def __init__(self, txs):
        self.txs = txs
        self.calls = []

    def scan(self, start, action, limit):
        self.calls.append((start, action, limit))
        found = [tx for tx in self.txs if int(tx['header']['id']) >= start]
        found = found[:limit or 1000]
        if action == 'ONLY_DIGEST':
            found = [{**tx, 'entries': [
                {**item, 'value': ''} for item in tx['entries']]}
                for tx in found]
        return found


def tx(number, *entries, metadata=None, digest=None):
    return {'header': {'id': str(number), 'eH': digest or f'h{number}',
                       'metadata': metadata or {}},
            'entries': list(entries)}


def created():
    return [tx(1, entry(*TABLE_T), *(entry(*item) for item in COLUMNS),
               *(entry(*item) for item in CHECKS)),
            tx(2, entry(*ROW)), tx(3, entry(*ROW))]


@pytest.fixture(autouse=True)
def clean_cache():
    catalog_log._CACHE.clear()
    yield
    catalog_log._CACHE.clear()


def test_defaults_and_checks_as_the_engine_stores_them():
    assert catalog_log.read(Log(created()).scan) == {'t': {
        'defaults': {'name': "'x'", 'score': '1.5', 'ts': 'now()'},
        'checks': [{'name': 'pos', 'expression': '(score >= 0)'},
                   {'name': 't_check1', 'expression': '(id > 0)'}]}}


def test_only_catalog_transactions_are_read_with_values():
    log = Log(created())
    catalog_log.read(log.scan)
    assert [call for call in log.calls if call[1] == 'RAW_VALUE'] == [
        (1, 'RAW_VALUE', 1)]


def test_deletions_and_renames_follow_the_latest_entry():
    txs = created() + [
        tx(4, entry(CHECKS[0][0], deleted=True)),
        tx(5, entry(TABLE_T[0], b'renamed')),
        tx(6, entry(COLUMNS[1][0], deleted=True)),
    ]
    assert catalog_log.read(Log(txs).scan) == {'renamed': {
        'defaults': {'score': '1.5', 'ts': 'now()'},
        'checks': [{'name': 't_check1', 'expression': '(id > 0)'}]}}
    dropped = txs + [tx(7, entry(TABLE_T[0], deleted=True))]
    assert catalog_log.read(Log(dropped).scan) == {}


def test_a_truncation_copy_restarts_the_state():
    txs = created() + [
        tx(9, entry(b'\x02CTL.TABLE.' + ids(1, 5), b'kept'),
           metadata={'truncatedTxID': '8'}),
    ]
    assert catalog_log.read(Log(txs).scan) == {
        'kept': {'defaults': {}, 'checks': []}}


def test_cache_reads_only_new_transactions_while_the_last_one_matches():
    log = Log(created())
    catalog_log.read(log.scan, cache_key='k')
    log.txs.append(tx(4, entry(CHECKS[0][0], deleted=True)))
    log.calls.clear()
    result = catalog_log.read(log.scan, cache_key='k')
    assert [check['name'] for check in result['t']['checks']] == [
        't_check1']
    assert log.calls[:2] == [(3, 'ONLY_DIGEST', 1), (4, 'ONLY_DIGEST', 0)]


def test_a_recreated_database_is_read_afresh():
    catalog_log.read(Log(created()).scan, cache_key='k')
    # Same ids, different transactions: the hash no longer matches.
    other = [tx(1, entry(b'\x02CTL.TABLE.' + ids(1, 1), b'other'),
                digest='x1'),
             tx(2, entry(*ROW), digest='x2'),
             tx(3, entry(*ROW), digest='x3')]
    assert catalog_log.read(Log(other).scan, cache_key='k') == {
        'other': {'defaults': {}, 'checks': []}}


def test_unread_rather_than_empty():
    log = Log(created())
    with pytest.raises(catalog_log.Unread, match='2 transactions read so'):
        catalog_log.read(log.scan, cache_key='big', budget=2)
    # The next read resumes after transaction 2 and finishes.
    log.calls.clear()
    assert 't' in catalog_log.read(log.scan, cache_key='big', budget=2)
    assert log.calls[:2] == [(2, 'ONLY_DIGEST', 1), (3, 'ONLY_DIGEST', 0)]

    class Gone(Log):
        def scan(self, start, action, limit):
            return [] if action == 'RAW_VALUE' else super().scan(
                start, action, limit)

    with pytest.raises(catalog_log.Unread, match='transaction 1'):
        catalog_log.read(Gone(created()).scan)
    with pytest.raises(catalog_log.Unread):
        catalog_log.decode(b'\x02CTL.CHECK.' + ids(1), b'')


def test_other_keys_are_ignored():
    assert catalog_log.decode(*ROW) is None
    assert catalog_log.decode(b'\x00plain kv', b'v') is None

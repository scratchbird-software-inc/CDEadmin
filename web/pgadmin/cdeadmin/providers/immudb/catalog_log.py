"""immudb SQL catalog facts that no catalog query returns.

Checked on 1.11.0 (source and live): column defaults and CHECK
constraints are kept in the database's own SQL catalog entries, but
COLUMNS(), SHOW TABLE, information_schema (column_default is the literal
'DEFAULT') and pg_constraint (primary and unique only) do not return
them. The entries are in the transaction log, which the native TxScan
endpoint (POST /db/tx) returns. Owner direction 2026-10-31: offer only
what can be read back, by any engine method, SQL or not.

Key layouts are 1.11.0's own (embedded/sql/stmt.go:37-58, catalog.go):
  CTL.TABLE.{db}{table}            -> name
  CTL.COLUMN.{db}{table}{col}{TYPE} -> {flags}{maxLen}[{nameLen:2}]{name}
                                       [{default SQL}] (flag 4: default)
  CTL.CHECK.{db}{table}{check}     -> {nameLen-1}{name}{expression}\\0
A deleted entry carries metadata deleted. A truncation commits a full
copy of the catalog as one transaction whose metadata names the
truncation point (pkg/database/sql.go CopySQLCatalog), so state restarts
from the latest such copy. Views and sequences are not read here: on
1.11.0 a view does not survive a database reload and a sequence restarts
(both live), and foreign keys are not stored at all.

The scan reads keys only (ONLY_DIGEST), so row contents are not fetched;
the few transactions with catalog keys are then read with their values.
Anything not established is reported unread, never empty. A key-only scan
does not read the value log (pkg/database/database.go serializeTx), and a
truncation discards value logs but keeps the transaction log, so a
truncated database still scans; values are read only from the latest
catalog copy on. A read that reaches the budget keeps what it read, so the
next read resumes from there.
"""
import base64
import binascii
import struct

SUPPORTED_VERSION = '1.11.0'
_SQL_PREFIX = b'\x02'
_TABLE = b'CTL.TABLE.'
_COLUMN = b'CTL.COLUMN.'
_CHECK = b'CTL.CHECK.'
_CATALOG = _SQL_PREFIX + b'CTL.'
_ID = 4
_HAS_DEFAULT = 4
# Transactions read per catalog read before giving up (about 20,000 a
# second were read live on the demo).
DEFAULT_BUDGET = 500000
_CACHE = {}


class Unread(Exception):
    """The catalog log could not be read completely."""


def _ids(rest, count):
    if len(rest) < count * _ID:
        raise Unread('catalog key is shorter than its identifiers')
    return [struct.unpack('>I', rest[index * _ID:(index + 1) * _ID])[0]
            for index in range(count)], rest[count * _ID:]


def decode(key, value, deleted=False):
    """One catalog entry as (kind, identity, facts); None if not one."""
    if not key.startswith(_SQL_PREFIX):
        return None
    body = key[len(_SQL_PREFIX):]
    if body.startswith(_TABLE):
        (database, table), _ = _ids(body[len(_TABLE):], 2)
        return 'table', (database, table), None if deleted else {
            'name': value.decode('utf-8')}
    if body.startswith(_COLUMN):
        (database, table, column), kind = _ids(body[len(_COLUMN):], 3)
        if deleted:
            return 'column', (database, table, column), None
        if len(value) < 5:
            raise Unread('column entry is too short')
        flags = value[0]
        if flags & _HAS_DEFAULT and len(value) >= 7:
            length = struct.unpack('>H', value[5:7])[0]
            name = value[7:7 + length].decode('utf-8')
            default = value[7 + length:].decode('utf-8') or None
        else:
            name, default = value[5:].decode('utf-8'), None
        return 'column', (database, table, column), {
            'name': name, 'type': kind.decode('utf-8'), 'default': default}
    if body.startswith(_CHECK):
        (database, table, check), _ = _ids(body[len(_CHECK):], 3)
        if deleted:
            return 'check', (database, table, check), None
        if not value:
            raise Unread('check entry is empty')
        length = value[0] + 1
        name = value[1:1 + length].decode('utf-8')
        # persistCheck allocates one byte more than it writes.
        expression = value[1 + length:].rstrip(b'\x00').decode('utf-8')
        return 'check', (database, table, check), {
            'name': name, 'expression': expression}
    return None


class State:
    """The latest catalog entries, as the engine would load them."""

    def __init__(self):
        self.entries = {}

    def apply(self, key, value, deleted=False):
        decoded = decode(key, value, deleted)
        if decoded is None:
            return
        kind, identity, facts = decoded
        if facts is None:
            self.entries.pop((kind, identity), None)
        else:
            self.entries[(kind, identity)] = facts

    def tables(self):
        """{table name: {'defaults': {column: sql}, 'checks': [...]}}"""
        names = {identity[1]: facts['name']
                 for (kind, identity), facts in self.entries.items()
                 if kind == 'table'}
        out = {name: {'defaults': {}, 'checks': []}
               for name in names.values()}
        for (kind, identity), facts in sorted(self.entries.items()):
            name = names.get(identity[1])
            if name is None:
                continue
            if kind == 'column' and facts['default'] is not None:
                out[name]['defaults'][facts['name']] = facts['default']
            elif kind == 'check':
                out[name]['checks'].append(dict(facts))
        return out


def _bytes(text):
    try:
        return base64.b64decode(text or '', validate=True)
    except (binascii.Error, ValueError):
        raise Unread('catalog entry is not base64') from None


def _entries(tx):
    for entry in tx.get('entries') or ():
        metadata = entry.get('metadata') or {}
        yield (_bytes(entry.get('key')), _bytes(entry.get('value')),
               bool(metadata.get('deleted')))


def _has_catalog(tx):
    return any(key.startswith(_CATALOG) for key, _, _ in _entries(tx))


def _truncation_copy(tx):
    metadata = (tx.get('header') or {}).get('metadata') or {}
    return bool(metadata.get('truncatedTxID'))


def read(scan, cache_key=None, budget=DEFAULT_BUDGET):
    """Catalog facts per table, read through scan(start, action, limit).

    scan returns up to limit transactions from start on (TxScan; 0 for the
    server's page size); an empty list ends the log. A cached state is
    reused when its last transaction is still the same one (same id and
    entries hash), so a database recreated under the same name is read
    afresh.
    """
    cached = _CACHE.get(cache_key) if cache_key is not None else None
    state, start, catalog_txs = State(), 1, []
    if cached:
        probe = scan(cached['last_id'], 'ONLY_DIGEST', 1)
        if probe and str(probe[0]['header'].get('id')) == str(
                cached['last_id']) and probe[0]['header'].get('eH') == \
                cached['last_hash']:
            state.entries = dict(cached['entries'])
            start = int(cached['last_id']) + 1
    last = cached if start > 1 else None
    seen, finished = 0, False
    while seen < budget:
        page = scan(start, 'ONLY_DIGEST', 0)
        if not page:
            finished = True
            break
        page = page[:budget - seen]
        for tx in page:
            if _truncation_copy(tx):
                # A full copy: what came before it no longer counts.
                state, catalog_txs = State(), []
            if _truncation_copy(tx) or _has_catalog(tx):
                catalog_txs.append(int(tx['header']['id']))
        seen += len(page)
        header = page[-1]['header']
        last = {'last_id': int(header['id']), 'last_hash': header.get('eH')}
        start = last['last_id'] + 1
    for tx_id in catalog_txs:
        page = scan(tx_id, 'RAW_VALUE', 1)
        if not page or int(page[0]['header']['id']) != tx_id:
            raise Unread(f'transaction {tx_id} could not be read')
        for key, value, deleted in _entries(page[0]):
            state.apply(key, value, deleted)
    if cache_key is not None and last:
        _CACHE[cache_key] = {**last, 'entries': dict(state.entries)}
    if not finished:
        raise Unread(f'{seen} transactions read so far (budget {budget}); '
                     'the next read continues')
    return state.tables()


def forget(cache_key):
    _CACHE.pop(cache_key, None)

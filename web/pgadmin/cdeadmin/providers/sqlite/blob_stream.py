"""Native Incremental Large-BLOB Transfer via `sqlite3_blob_*` (`Connection.blobopen`) (SQ-AUD-12).

Enforces proved integer rowid identity (refusing WITHOUT ROWID tables, views, virtual tables,
and unshadowable rowids), distinguishes SQL NULL from zeroblob(0) and non-BLOB affinities,
performs bounded chunked streaming without materializing full large BLOBs in memory, handles
concurrent row-update `SQLITE_ABORT` handle invalidation cleanly, and closes every handle.
"""
from __future__ import annotations

import base64
from contextlib import closing
import hashlib
import sqlite3
import uuid

from .declarations import quote

MAX_CHUNK_BYTES = 4 * 1024 * 1024
MAX_ZEROBLOB_BYTES = 512 * 1024 * 1024


class BlobStreamError(ValueError):
    pass


def _resolve_rowid_table(connection: sqlite3.Connection, schema_name: str, table_name: str, column_name: str) -> dict:
    if not callable(getattr(connection, 'blobopen', None)):
        raise BlobStreamError('Python sqlite3.Connection.blobopen is unavailable in this runtime')
    known_schemas = {str(r[1]) for r in connection.execute('PRAGMA database_list').fetchall()} | {'temp'}
    if schema_name not in known_schemas:
        raise BlobStreamError(f'Unknown SQLite database namespace {schema_name!r}')
    q_schema = quote(schema_name)
    row = connection.execute(
        f'SELECT type, rootpage, sql FROM {q_schema}.sqlite_schema WHERE name = ?', (table_name,)
    ).fetchone()
    if row is None or row[0] != 'table':
        raise BlobStreamError(f'{schema_name}.{table_name} must be an ordinary SQLite table (views are not supported)')
    rootpage, ddl = row[1], str(row[2] or '')
    tlist = connection.execute(f'PRAGMA {q_schema}.table_list').fetchall()
    tmeta = next((r for r in tlist if str(r[0]) == schema_name and str(r[1]) == table_name), None)
    if tmeta is not None:
        if str(tmeta[2]) == 'virtual':
            raise BlobStreamError(f'{schema_name}.{table_name} is a virtual table and does not support sqlite3_blob_open')
        if bool(tmeta[4]):
            raise BlobStreamError(f'{schema_name}.{table_name} is WITHOUT ROWID and cannot be opened via sqlite3_blob_open')
    elif (rootpage in (0, None)) or ddl.lstrip().upper().startswith('CREATE VIRTUAL TABLE'):
        raise BlobStreamError(f'{schema_name}.{table_name} is a virtual table and does not support sqlite3_blob_open')
    cols = connection.execute(f'PRAGMA {q_schema}.table_xinfo({quote(table_name)})').fetchall()
    col_names = {str(c[1]) for c in cols}
    target_col = next((c for c in cols if str(c[1]) == column_name and not c[6]), None)
    if target_col is None:
        raise BlobStreamError(f'Column {column_name!r} is not an ordinary stored column of {schema_name}.{table_name}')

    # Find an unshadowed physical rowid alias (or declared INTEGER PRIMARY KEY alias)
    pks = [c for c in cols if c[5]]
    ipk_alias = None
    if len(pks) == 1 and str(pks[0][2] or '').strip().upper() == 'INTEGER':
        # Note: in SQLite `INTEGER PRIMARY KEY DESC` is NOT a rowid alias; check via EXPLAIN or unshadowed alias
        ipk_alias = str(pks[0][1])
    rowid_alias = next((alias for alias in ('_rowid_', 'rowid', 'oid') if alias not in col_names), ipk_alias)
    if rowid_alias is None:
        raise BlobStreamError(f'All physical rowid aliases (rowid, _rowid_, oid) are shadowed on {schema_name}.{table_name}')
    if tmeta is None:
        unshadowed = next((alias for alias in ('_rowid_', 'rowid', 'oid') if alias not in col_names), None)
        if unshadowed is not None:
            try:
                connection.execute(f'SELECT {quote(unshadowed)} FROM {q_schema}.{quote(table_name)} LIMIT 0')
            except sqlite3.OperationalError as exc:
                raise BlobStreamError(
                    f'{schema_name}.{table_name} is WITHOUT ROWID and cannot be opened via sqlite3_blob_open'
                ) from exc
    return {
        'schema': schema_name,
        'table': table_name,
        'column': column_name,
        'rowid_alias': rowid_alias,
    }


def inspect_cell(connection: sqlite3.Connection, *, schema_name: str = 'main', table_name: str, column_name: str, rowid: int) -> dict:
    if type(rowid) is not int:
        raise BlobStreamError('Incremental BLOB streaming requires an exact 64-bit integer rowid')
    meta = _resolve_rowid_table(connection, schema_name, table_name, column_name)
    q_schema = quote(schema_name)
    q_table = quote(table_name)
    q_col = quote(column_name)
    q_rid = quote(meta['rowid_alias'])
    cell = connection.execute(
        f'SELECT typeof({q_col}), length({q_col}), CASE WHEN typeof({q_col})=\'blob\' THEN length({q_col}) ELSE length(CAST({q_col} AS BLOB)) END '
        f'FROM {q_schema}.{q_table} WHERE {q_rid} = ?',
        (rowid,),
    ).fetchone()
    if cell is None:
        raise BlobStreamError(f'Row with rowid={rowid} does not exist in {schema_name}.{table_name}')
    val_type, char_or_byte_len, byte_len = str(cell[0]), int(cell[1] or 0), int(cell[2] or 0)
    return {
        'schema': schema_name,
        'table': table_name,
        'column': column_name,
        'rowid': rowid,
        'rowid_alias': meta['rowid_alias'],
        'typeof': val_type,
        'is_null': val_type == 'null',
        'is_empty_zeroblob': val_type == 'blob' and byte_len == 0,
        'streamable_blob': val_type == 'blob',
        'byte_length': byte_len if val_type == 'blob' else None,
        'text_or_scalar_bytes': byte_len if val_type != 'blob' and val_type != 'null' else None,
    }


def read_blob_chunk(
    connection: sqlite3.Connection,
    *,
    schema_name: str = 'main',
    table_name: str,
    column_name: str,
    rowid: int,
    offset: int = 0,
    length: int = 65536,
    encoding: str = 'base64',
) -> dict:
    if type(offset) is not int or offset < 0:
        raise BlobStreamError('offset must be a non-negative integer')
    if type(length) is not int or not 1 <= length <= MAX_CHUNK_BYTES:
        raise BlobStreamError(f'length must be between 1 and {MAX_CHUNK_BYTES} bytes')
    if encoding not in {'base64', 'hex'}:
        raise BlobStreamError('encoding must be base64 or hex')

    info = inspect_cell(connection, schema_name=schema_name, table_name=table_name, column_name=column_name, rowid=rowid)
    if info['is_null']:
        raise BlobStreamError('Cell is SQL NULL (not a BLOB); incremental BLOB handle cannot open SQL NULL')
    if not info['streamable_blob']:
        raise BlobStreamError(f'Cell storage class is {info["typeof"]!r}; incremental BLOB streaming requires typeof=\'blob\'')

    blob = connection.blobopen(table_name, column_name, rowid, readonly=True, name=schema_name)
    try:
        total_len = len(blob)
        if offset > total_len:
            raise BlobStreamError(f'offset {offset} exceeds BLOB length {total_len}')
        read_size = min(length, total_len - offset)
        if read_size == 0:
            chunk = b''
        else:
            blob.seek(offset)
            chunk = blob.read(read_size)
        return {
            'schema': schema_name,
            'table': table_name,
            'column': column_name,
            'rowid': rowid,
            'total_bytes': total_len,
            'offset': offset,
            'chunk_bytes': len(chunk),
            'eof': (offset + len(chunk)) >= total_len,
            'chunk_sha256': hashlib.sha256(chunk).hexdigest(),
            'encoding': encoding,
            'data': base64.b64encode(chunk).decode('ascii') if encoding == 'base64' else chunk.hex(),
            'handle_closed': True,
        }
    except sqlite3.OperationalError as exc:
        err_code = getattr(exc, 'sqlite_errorcode', None)
        if err_code == sqlite3.SQLITE_ABORT or 'expired' in str(exc).lower() or 'abort' in str(exc).lower():
            raise BlobStreamError('BLOB handle was invalidated by a concurrent update to the row (SQLITE_ABORT); reopen and retry') from None
        raise BlobStreamError(f'Native sqlite3_blob_read failed: {exc}') from None
    finally:
        blob.close()


def allocate_zeroblob(
    connection: sqlite3.Connection,
    *,
    schema_name: str = 'main',
    table_name: str,
    column_name: str,
    rowid: int,
    byte_length: int,
    owned_transaction: bool = True,
) -> dict:
    if type(byte_length) is not int or not 0 <= byte_length <= MAX_ZEROBLOB_BYTES:
        raise BlobStreamError(f'byte_length must be between 0 and {MAX_ZEROBLOB_BYTES} bytes')
    meta = _resolve_rowid_table(connection, schema_name, table_name, column_name)
    q_schema = quote(schema_name)
    q_table = quote(table_name)
    q_col = quote(column_name)
    q_rid = quote(meta['rowid_alias'])

    sp = 'sr_zblob_' + uuid.uuid4().hex
    started = False
    try:
        if owned_transaction and not connection.in_transaction:
            connection.execute('BEGIN IMMEDIATE')
            started = True
        else:
            connection.execute(f'SAVEPOINT {sp}')
        cur = connection.execute(
            f'UPDATE {q_schema}.{q_table} SET {q_col} = zeroblob(?) WHERE {q_rid} = ?',
            (byte_length, rowid),
        )
        if cur.rowcount != 1:
            raise BlobStreamError(f'Target rowid={rowid} was not found or modified {cur.rowcount} rows')
        if started:
            connection.commit()
        else:
            connection.execute(f'RELEASE SAVEPOINT {sp}')
        after = inspect_cell(connection, schema_name=schema_name, table_name=table_name, column_name=column_name, rowid=rowid)
        return {
            'allocated': True,
            'committed': started,
            'byte_length': byte_length,
            'cell': after,
        }
    except Exception:
        if started:
            connection.rollback()
        elif connection.in_transaction:
            connection.execute(f'ROLLBACK TO SAVEPOINT {sp}')
            connection.execute(f'RELEASE SAVEPOINT {sp}')
        raise


def write_blob_chunk(
    connection: sqlite3.Connection,
    *,
    schema_name: str = 'main',
    table_name: str,
    column_name: str,
    rowid: int,
    offset: int,
    payload: bytes,
    owned_transaction: bool = True,
) -> dict:
    if type(offset) is not int or offset < 0:
        raise BlobStreamError('offset must be a non-negative integer')
    if not isinstance(payload, (bytes, bytearray, memoryview)) or len(payload) > MAX_CHUNK_BYTES:
        raise BlobStreamError(f'Chunk payload must be bytes up to {MAX_CHUNK_BYTES} bytes')
    raw = bytes(payload)
    info = inspect_cell(connection, schema_name=schema_name, table_name=table_name, column_name=column_name, rowid=rowid)
    if info['is_null'] or not info['streamable_blob']:
        raise BlobStreamError(
            'sqlite3_blob_write cannot resize or replace SQL NULL/non-BLOB values; '
            'allocate the exact BLOB length via allocate_zeroblob first'
        )
    sp = 'sr_bwrite_' + uuid.uuid4().hex
    started = False
    blob = None
    try:
        if owned_transaction and not connection.in_transaction:
            connection.execute('BEGIN IMMEDIATE')
            started = True
        else:
            connection.execute(f'SAVEPOINT {sp}')
        blob = connection.blobopen(table_name, column_name, rowid, readonly=False, name=schema_name)
        total_len = len(blob)
        if offset + len(raw) > total_len:
            raise BlobStreamError(
                f'Chunk write [offset={offset}, len={len(raw)}] exceeds allocated BLOB size {total_len}; '
                'sqlite3_blob_write cannot extend a BLOB without allocate_zeroblob'
            )
        if raw:
            blob.seek(offset)
            blob.write(raw)
        blob.close()
        blob = None
        if started:
            connection.commit()
        else:
            connection.execute(f'RELEASE SAVEPOINT {sp}')
        return {
            'written': True,
            'committed': started,
            'schema': schema_name,
            'table': table_name,
            'column': column_name,
            'rowid': rowid,
            'offset': offset,
            'written_bytes': len(raw),
            'total_bytes': total_len,
            'chunk_sha256': hashlib.sha256(raw).hexdigest(),
            'handle_closed': True,
        }
    except sqlite3.OperationalError as exc:
        if blob is not None:
            try:
                blob.close()
            except Exception:
                pass
            blob = None
        if started:
            connection.rollback()
        elif connection.in_transaction:
            connection.execute(f'ROLLBACK TO SAVEPOINT {sp}')
            connection.execute(f'RELEASE SAVEPOINT {sp}')
        err_code = getattr(exc, 'sqlite_errorcode', None)
        if err_code == sqlite3.SQLITE_ABORT or 'expired' in str(exc).lower() or 'abort' in str(exc).lower():
            raise BlobStreamError('BLOB handle was invalidated by a concurrent row modification (SQLITE_ABORT)') from None
        raise BlobStreamError(f'Native sqlite3_blob_write failed: {exc}') from None
    except Exception:
        if blob is not None:
            try:
                blob.close()
            except Exception:
                pass
        if started:
            connection.rollback()
        elif connection.in_transaction:
            connection.execute(f'ROLLBACK TO SAVEPOINT {sp}')
            connection.execute(f'RELEASE SAVEPOINT {sp}')
        raise

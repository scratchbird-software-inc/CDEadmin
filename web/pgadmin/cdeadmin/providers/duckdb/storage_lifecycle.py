"""DuckDB Runtime & Storage Lifecycle Management (DU-AUD-21).

Implements exact binary file-header inspection and storage migration/reopen
verification matching DuckDB 1.5.2 ``single_file_block_manager.cpp`` and
``storage_info.cpp``:
- Parses ``MainHeader`` (magic ``b'DUCK'`` at byte 8, ``version_number`` uint64,
  ``flags[4]``, ``ENCRYPTED_DATABASE_FLAG``, ``library_git_desc``,
  ``library_git_hash``, ``encryption_cipher``, ``db_identifier``) and
  unencrypted ``DatabaseHeader`` slots ``h1`` (4096) / ``h2`` (8192)
  (``iteration``, ``block_count``, ``block_alloc_size``, ``vector_size``,
  ``serialization_compatibility``).
- Never infers file storage format from version labels or ``ATTACH`` arguments:
  opening an existing ``v1.0.0`` (``version_number == 64``) file with
  ``storage_compatibility_version`` does NOT rewrite the existing file header.
- Provides reviewed storage conversion via ``ATTACH ... (STORAGE_VERSION ...)``
  + ``COPY FROM DATABASE`` + ``CHECKPOINT`` with independent post-copy binary
  header proof, exact row-count verification, downgrade refusal reporting, and
  encrypted key/wrong-key verification (binding keys via ``ENCRYPTION_KEY ?``).
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import struct
import uuid

import duckdb

from ..embedded_route import contained_database, resolve_contained_path


class DuckDBStorageLifecycleError(ValueError):
    pass


FILE_HEADER_SIZE = 4096
BLOCK_HEADER_SIZE = 8
MAGIC_BYTES = b'DUCK'
ENCRYPTED_DATABASE_FLAG = 1
VERSION_NUMBER_LOWER = 64
VERSION_NUMBER_UPPER = 68
STANDARD_VECTOR_SIZE = 2048
DEFAULT_BLOCK_ALLOC_SIZE = 262144

VERSION_NUMBER_RANGES = {
    64: 'v0.9.0 - v1.1.3',
    65: 'v1.2.0 - v1.2.2',
    66: 'v1.3.0 - v1.3.2',
    67: 'v1.4.0 - v1.4.4',
    68: 'v1.5.0 - v1.5.2',
}

SERIALIZATION_VERSION_LABELS = {
    1: 'v1.0.0+',
    2: 'v1.0.0+',
    3: 'v1.0.0+',
    4: 'v1.2.0+',
    5: 'v1.3.0+',
    6: 'v1.4.0+',
    7: 'v1.5.0+',
}

CIPHER_CODES = {
    0: None,
    1: 'GCM',
    2: 'CTR',
}

ADMITTED_STORAGE_VERSIONS = (
    'v1.0.0', 'v1.1.0', 'v1.2.0', 'v1.3.0', 'v1.4.0', 'v1.5.0', 'v1.5.2', 'latest',
)


def _quote(ident: str) -> str:
    return '"' + str(ident).replace('"', '""') + '"'


def _clean_c_str(raw: bytes) -> str:
    nul = raw.find(b'\x00')
    trimmed = raw[:nul] if nul >= 0 else raw
    return trimmed.decode('utf-8', errors='replace')


def inspect_storage_header(file_path: str | Path) -> dict:
    """Read actual binary ``MainHeader`` and ``DatabaseHeader`` from a ``.duckdb`` file."""
    p = Path(file_path)
    if not p.is_file():
        raise DuckDBStorageLifecycleError(f'DuckDB file does not exist: {file_path}')
    st = p.stat()
    size = st.st_size
    if size < BLOCK_HEADER_SIZE + 4:
        return {
            'path': str(p),
            'size_bytes': size,
            'inode': [st.st_dev, st.st_ino],
            'valid_duckdb_magic': False,
            'compatible_with_runtime_1_5_2': False,
            'incompatibility_reason': 'File is smaller than DuckDB MainHeader magic offset (12 bytes)',
        }

    with p.open('rb') as f:
        header_bytes = f.read(FILE_HEADER_SIZE * 3)

    magic = header_bytes[8:12]
    if magic != MAGIC_BYTES:
        return {
            'path': str(p),
            'size_bytes': size,
            'inode': [st.st_dev, st.st_ino],
            'valid_duckdb_magic': False,
            'compatible_with_runtime_1_5_2': False,
            'incompatibility_reason': 'File does not contain DuckDB magic bytes (DUCK) at offset 8',
        }

    if len(header_bytes) < 140:
        raise DuckDBStorageLifecycleError('Truncated DuckDB MainHeader (< 140 bytes)')

    version_number = struct.unpack_from('<Q', header_bytes, 12)[0]
    flags = list(struct.unpack_from('<4Q', header_bytes, 20))
    lib_git_desc = _clean_c_str(header_bytes[52:84])
    lib_git_hash = _clean_c_str(header_bytes[84:116])
    enc_meta = header_bytes[116:124]
    db_identifier = header_bytes[124:140].hex()

    encrypted = bool(flags[0] & ENCRYPTED_DATABASE_FLAG)
    cipher_code = enc_meta[2] if encrypted else 0
    cipher_name = CIPHER_CODES.get(cipher_code, f'UNKNOWN({cipher_code})') if encrypted else None

    version_ok = VERSION_NUMBER_LOWER <= version_number <= VERSION_NUMBER_UPPER
    incompat_reason = None
    if not version_ok:
        direction = 'older' if version_number < VERSION_NUMBER_LOWER else 'newer'
        incompat_reason = (
            f'File storage version_number={version_number} ({direction}) is outside DuckDB 1.5.2 '
            f'supported range [{VERSION_NUMBER_LOWER}..{VERSION_NUMBER_UPPER}]'
        )

    db_header_info = None
    vector_ok = True
    if not encrypted and len(header_bytes) >= FILE_HEADER_SIZE * 3:
        slots = []
        for slot_idx, base in ((0, FILE_HEADER_SIZE), (1, FILE_HEADER_SIZE * 2)):
            pay = base + BLOCK_HEADER_SIZE
            iteration, meta_block, free_list, block_count, block_alloc_size, vector_size = struct.unpack_from(
                '<6Q', header_bytes, pay
            )
            ser_compat = (
                1 if version_number == 64
                else struct.unpack_from('<Q', header_bytes, pay + 48)[0]
            )
            slots.append({
                'slot': slot_idx,
                'iteration': iteration,
                'meta_block': meta_block,
                'free_list': free_list,
                'block_count': block_count,
                'block_alloc_size': block_alloc_size or DEFAULT_BLOCK_ALLOC_SIZE,
                'vector_size': vector_size or STANDARD_VECTOR_SIZE,
                'serialization_compatibility': ser_compat,
                'storage_version_label': SERIALIZATION_VERSION_LABELS.get(ser_compat, f'unknown({ser_compat})'),
            })
        active = max(slots, key=lambda s: s['iteration'])
        db_header_info = {
            'active_slot': active['slot'],
            'iteration': active['iteration'],
            'block_count': active['block_count'],
            'block_alloc_size': active['block_alloc_size'],
            'vector_size': active['vector_size'],
            'serialization_compatibility': active['serialization_compatibility'],
            'storage_version_label': active['storage_version_label'],
        }
        if active['vector_size'] != STANDARD_VECTOR_SIZE:
            vector_ok = False
            incompat_reason = (
                f"File vector_size={active['vector_size']} differs from runtime vector_size={STANDARD_VECTOR_SIZE}"
            )

    wal_path = Path(str(p) + '.wal')
    return {
        'path': str(p),
        'size_bytes': size,
        'inode': [st.st_dev, st.st_ino],
        'valid_duckdb_magic': True,
        'version_number': version_number,
        'duckdb_version_family': VERSION_NUMBER_RANGES.get(version_number, f'unmapped({version_number})'),
        'flags': flags,
        'encrypted': encrypted,
        'encryption_cipher': cipher_name,
        'created_by_library_version': lib_git_desc,
        'created_by_source_id': lib_git_hash,
        'db_identifier_hex': db_identifier,
        'database_header': db_header_info,
        'wal_present': wal_path.is_file(),
        'wal_size_bytes': wal_path.stat().st_size if wal_path.is_file() else 0,
        'compatible_with_runtime_1_5_2': bool(version_ok and vector_ok),
        'incompatibility_reason': incompat_reason,
    }


def _attach_db_on_memory(
    con,
    file_path: str,
    alias: str,
    *,
    read_only: bool,
    encryption_key: str | None = None,
    encryption_cipher: str | None = None,
    storage_version: str | None = None,
    block_size: int | None = None,
    row_group_size: int | None = None,
) -> None:
    opts = ['READ_ONLY' if read_only else 'READ_WRITE']
    params = []
    if storage_version is not None:
        if storage_version not in ADMITTED_STORAGE_VERSIONS:
            raise DuckDBStorageLifecycleError(f'Unsupported DuckDB storage_version: {storage_version!r}')
        opts.append("STORAGE_VERSION '" + storage_version + "'")
    if block_size is not None:
        opts.append(f'BLOCK_SIZE {int(block_size)}')
    if row_group_size is not None:
        opts.append(f'ROW_GROUP_SIZE {int(row_group_size)}')
    if encryption_key is not None:
        if not isinstance(encryption_key, str) or not encryption_key or '\x00' in encryption_key:
            raise DuckDBStorageLifecycleError('Encryption key must be non-empty text without NUL')
        opts.append('ENCRYPTION_KEY ?')
        params.append(encryption_key)
        if encryption_cipher is not None:
            if encryption_cipher not in {'GCM', 'CTR'}:
                raise DuckDBStorageLifecycleError('encryption_cipher must be GCM or CTR')
            opts.append(f"ENCRYPTION_CIPHER '{encryption_cipher}'")
    lit_path = "'" + str(file_path).replace("'", "''") + "'"
    sql = f'ATTACH {lit_path} AS {_quote(alias)} ({", ".join(opts)})'
    con.execute(sql, params)


def probe_reopen_compatibility(
    file_path: str | Path,
    *,
    encryption_key: str | None = None,
    encryption_cipher: str | None = None,
    storage_compatibility_version: str | None = None,
) -> dict:
    """Verify actual native DuckDB reopen, key validity, and on-disk vs runtime storage tags."""
    header_before = inspect_storage_header(file_path)
    if not header_before['valid_duckdb_magic']:
        return {
            'reopen_succeeded': False,
            'header_before': header_before,
            'failure_kind': 'invalid_magic',
            'error': header_before['incompatibility_reason'],
        }
    if not header_before['compatible_with_runtime_1_5_2']:
        return {
            'reopen_succeeded': False,
            'header_before': header_before,
            'failure_kind': 'incompatible_storage_version',
            'error': header_before['incompatibility_reason'],
        }
    if header_before['encrypted'] and not encryption_key:
        return {
            'reopen_succeeded': False,
            'header_before': header_before,
            'failure_kind': 'encryption_key_required',
            'error': 'Encrypted DuckDB database requires its private encryption_key to reopen',
        }

    cfg = {'storage_compatibility_version': storage_compatibility_version} if storage_compatibility_version else {}
    con = duckdb.connect(':memory:', config=cfg) if cfg else duckdb.connect(':memory:')
    alias = 'probe_' + uuid.uuid4().hex[:8]
    try:
        _attach_db_on_memory(
            con, str(file_path), alias,
            read_only=True,
            encryption_key=encryption_key,
            encryption_cipher=encryption_cipher,
        )
        db_row = con.execute(
            'SELECT tags, encrypted, cipher FROM duckdb_databases() WHERE database_name=?',
            [alias],
        ).fetchone()
        tags = dict(db_row[0] or {}) if db_row else {}
        tbl_count = con.execute(
            'SELECT count(*) FROM duckdb_tables() WHERE database_name=? AND NOT internal',
            [alias],
        ).fetchone()[0]
        con.execute(f'DETACH {_quote(alias)}')
    except duckdb.Error as exc:
        msg = str(exc)
        kind = 'wrong_encryption_key' if 'encryption key' in msg.lower() else 'native_open_refused'
        return {
            'reopen_succeeded': False,
            'header_before': header_before,
            'failure_kind': kind,
            'error_type': type(exc).__name__,
            'error': msg[:300],
        }
    finally:
        con.close()

    header_after = inspect_storage_header(file_path)
    return {
        'reopen_succeeded': True,
        'header_before': header_before,
        'header_after': header_after,
        'physical_header_rewritten_by_open': (
            header_before.get('version_number') != header_after.get('version_number') or
            header_before.get('database_header') != header_after.get('database_header')
        ),
        'live_catalog_tags': tags,
        'table_count': tbl_count,
    }


def migrate_storage_profile(
    route: dict,
    request: dict,
) -> dict:
    """Convert a DuckDB database to an explicit target storage version / block size / encryption profile by copy.

    Proves the conversion via independent binary ``MainHeader`` + ``DatabaseHeader``
    inspection and exact row-count verification on a separate reopen. Never mutates
    the active source file in place; source replacement requires explicit cutover.
    """
    allowed = {
        'target_path', 'target_storage_version', 'block_size', 'row_group_size',
        'source_encryption_key', 'source_encryption_cipher',
        'target_encryption_key', 'target_encryption_cipher',
    }
    if not isinstance(request, dict) or set(request) - allowed:
        raise DuckDBStorageLifecycleError('Invalid storage lifecycle migration request')

    fs_root = route.get('filesystem_root')
    if not fs_root:
        raise DuckDBStorageLifecycleError('Storage migration requires a configured filesystem_root')

    src_path = contained_database(route)
    if src_path == ':memory:' or not Path(src_path).is_file():
        raise DuckDBStorageLifecycleError('Storage migration requires an existing file-backed DuckDB source')

    target_raw = request.get('target_path')
    if not isinstance(target_raw, str) or not target_raw.strip():
        raise DuckDBStorageLifecycleError('Provide a contained target_path for the converted DuckDB file')
    dst_path = resolve_contained_path(fs_root, target_raw, must_exist=False)
    if os.path.abspath(dst_path) == os.path.abspath(src_path):
        raise DuckDBStorageLifecycleError('Storage migration writes a new file; in-place overwrite/REKEY is forbidden')
    if Path(dst_path).exists():
        raise DuckDBStorageLifecycleError('target_path already exists; choose a fresh file path for storage conversion')

    target_sv = request.get('target_storage_version', 'v1.5.2')
    if target_sv not in ADMITTED_STORAGE_VERSIONS:
        raise DuckDBStorageLifecycleError(f'target_storage_version must be one of {ADMITTED_STORAGE_VERSIONS}')

    src_header = inspect_storage_header(src_path)
    if not src_header['compatible_with_runtime_1_5_2']:
        raise DuckDBStorageLifecycleError(src_header['incompatibility_reason'] or 'Incompatible source DuckDB file')

    con = duckdb.connect(':memory:')
    src_alias = 'mig_src_' + uuid.uuid4().hex[:8]
    dst_alias = 'mig_dst_' + uuid.uuid4().hex[:8]
    try:
        _attach_db_on_memory(
            con, src_path, src_alias,
            read_only=True,
            encryption_key=request.get('source_encryption_key'),
            encryption_cipher=request.get('source_encryption_cipher'),
        )
        src_counts = {
            f'{r[0]}.{r[1]}': con.execute(f'SELECT count(*) FROM {_quote(src_alias)}.{_quote(r[0])}.{_quote(r[1])}').fetchone()[0]
            for r in con.execute(
                'SELECT schema_name, table_name FROM duckdb_tables() WHERE database_name=? AND NOT internal ORDER BY schema_name, table_name',
                [src_alias],
            ).fetchall()
        }
        if target_sv in {'v1.0.0', 'v1.1.0', 'v1.2.0', 'v1.3.0'}:
            typed_macros = con.execute(
                "SELECT function_name, parameter_types FROM duckdb_functions() "
                "WHERE database_name=? AND NOT internal AND function_type IN ('macro', 'table_macro')",
                [src_alias],
            ).fetchall()
            for fname, ptypes in typed_macros:
                if ptypes and any(pt is not None and str(pt).upper() != 'ANY' for pt in ptypes):
                    raise DuckDBStorageLifecycleError(
                        f'Native DuckDB storage conversion refused: macro {fname!r} uses typed parameters '
                        f'requiring storage_version >= v1.4.0 (target requested {target_sv})'
                    )
        _attach_db_on_memory(
            con, dst_path, dst_alias,
            read_only=False,
            storage_version=target_sv,
            block_size=request.get('block_size'),
            row_group_size=request.get('row_group_size'),
            encryption_key=request.get('target_encryption_key'),
            encryption_cipher=request.get('target_encryption_cipher'),
        )
        con.execute(f'COPY FROM DATABASE {_quote(src_alias)} TO {_quote(dst_alias)}')
        con.execute(f'CHECKPOINT {_quote(dst_alias)}')
        con.execute(f'DETACH {_quote(dst_alias)}')
        con.execute(f'DETACH {_quote(src_alias)}')
    except BaseException as exc:
        con.close()
        for p in (Path(dst_path), Path(dst_path + '.wal')):
            p.unlink(missing_ok=True)
        if isinstance(exc, DuckDBStorageLifecycleError):
            raise
        if isinstance(exc, duckdb.Error):
            raise DuckDBStorageLifecycleError(f'Native DuckDB storage conversion refused or failed: {exc}') from None
        raise
    con.close()

    # Independent binary header & reopen verification on dst_path!
    dst_header = inspect_storage_header(dst_path)
    reopen = probe_reopen_compatibility(
        dst_path,
        encryption_key=request.get('target_encryption_key'),
        encryption_cipher=request.get('target_encryption_cipher'),
    )
    if not reopen['reopen_succeeded']:
        raise DuckDBStorageLifecycleError(f"Converted target failed independent reopen: {reopen.get('error')}")

    # Verify exact row counts on independent connection
    vcon = duckdb.connect(':memory:')
    valias = 'ver_' + uuid.uuid4().hex[:8]
    try:
        _attach_db_on_memory(
            vcon, dst_path, valias,
            read_only=True,
            encryption_key=request.get('target_encryption_key'),
            encryption_cipher=request.get('target_encryption_cipher'),
        )
        dst_counts = {
            f'{r[0]}.{r[1]}': vcon.execute(f'SELECT count(*) FROM {_quote(valias)}.{_quote(r[0])}.{_quote(r[1])}').fetchone()[0]
            for r in vcon.execute(
                'SELECT schema_name, table_name FROM duckdb_tables() WHERE database_name=? AND NOT internal ORDER BY schema_name, table_name',
                [valias],
            ).fetchall()
        }
        vcon.execute(f'DETACH {_quote(valias)}')
    finally:
        vcon.close()

    if dst_counts != src_counts:
        raise DuckDBStorageLifecycleError('Converted target table row counts differed from source')

    return {
        'state': 'migrated_and_verified',
        'source_header': src_header,
        'target_header': dst_header,
        'target_live_storage_tags': reopen['live_catalog_tags'],
        'verified_table_row_counts': dst_counts,
        'cutover_implied': False,
    }

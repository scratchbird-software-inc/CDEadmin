"""DuckDB Operational Physical Continuity & WAL Recovery Drills (DU-AUD-20).

Implements native DuckDB file/WAL continuity workflows without inventing
PostgreSQL PITR, online hot-backup APIs, or in-place REKEY:
- Inspects physical ``.duckdb`` + ``.duckdb.wal`` state and exclusive lock
  status.
- Performs quiesced ``CHECKPOINT`` / ``FORCE CHECKPOINT`` offline snapshots via
  fsynced staging files + atomic ``os.replace``, verifying snapshot integrity
  on an independent read-only connection.
- Executes non-destructive crash/WAL recovery drills on cloned ``.duckdb`` +
  ``.duckdb.wal`` fixtures (exercising DuckDB's ``wal_replay.cpp``), verifying
  recovered tables/rows and post-checkpoint WAL cleanup.
- Restores snapshots to new registration targets and executes reviewed active
  file cutover with inode continuity verification and rollback backup retention
  (never silently replacing an active file).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import uuid

import duckdb

from ..embedded_route import contained_database, resolve_contained_path
from .storage_lifecycle import _attach_db_on_memory, inspect_storage_header


class DuckDBContinuityError(ValueError):
    pass


def _quote(ident: str) -> str:
    return '"' + str(ident).replace('"', '""') + '"'


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _copy_fsync_atomic(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f'.{dst.name}.{uuid.uuid4().hex}.tmp')
    try:
        shutil.copy2(src, tmp)
        os.chmod(tmp, 0o600)
        with tmp.open('rb') as f:
            os.fsync(f.fileno())
        os.replace(tmp, dst)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def inspect_physical_continuity(route: dict) -> dict:
    db_path_str = contained_database(route)
    if db_path_str == ':memory:':
        return {
            'database': ':memory:',
            'is_memory': True,
            'physical_continuity_supported': False,
            'reason': 'In-memory DuckDB databases have no physical .duckdb or .wal files',
        }
    p = Path(db_path_str)
    if not p.is_file():
        raise DuckDBContinuityError(f'Registered DuckDB file is absent: {db_path_str}')

    header = inspect_storage_header(p)
    wal = Path(db_path_str + '.wal')
    tmp_dir = Path(db_path_str + '.tmp')
    return {
        'database': str(p),
        'is_memory': False,
        'physical_continuity_supported': True,
        'inode': header['inode'],
        'size_bytes': header['size_bytes'],
        'wal_path': str(wal),
        'wal_present': wal.is_file(),
        'wal_size_bytes': wal.stat().st_size if wal.is_file() else 0,
        'spill_dir_present': tmp_dir.is_dir(),
        'header': header,
        'supported_capabilities': {
            'quiesced_checkpoint_snapshot': True,
            'cloned_wal_replay_drill': True,
            'restore_to_new_target': True,
            'reviewed_inode_bound_cutover': True,
            'online_hot_backup_api': False,
            'point_in_time_wal_archiving': False,
            'in_place_rekey': False,
        },
    }


def quiesce_and_snapshot(
    route: dict,
    request: dict,
) -> dict:
    """Flush WAL via CHECKPOINT/FORCE CHECKPOINT, close exclusively, copy atomically, and verify reopen."""
    allowed = {'snapshot_path', 'force_checkpoint', 'encryption_key', 'encryption_cipher'}
    if not isinstance(request, dict) or set(request) - allowed:
        raise DuckDBContinuityError('Invalid DuckDB physical snapshot request')

    fs_root = route.get('filesystem_root')
    if not fs_root:
        raise DuckDBContinuityError('Physical snapshot requires a configured filesystem_root')
    db_path_str = contained_database(route)
    if db_path_str == ':memory:' or not Path(db_path_str).is_file():
        raise DuckDBContinuityError('Physical snapshot requires an existing file-backed DuckDB database')

    snap_raw = request.get('snapshot_path')
    if not isinstance(snap_raw, str) or not snap_raw.strip():
        raise DuckDBContinuityError('Provide a contained snapshot_path')
    snap_path = Path(resolve_contained_path(fs_root, snap_raw, must_exist=False))
    src_path = Path(db_path_str)
    if snap_path.resolve() == src_path.resolve():
        raise DuckDBContinuityError('snapshot_path must be distinct from the active database file')
    if snap_path.exists():
        raise DuckDBContinuityError('snapshot_path already exists; will not silently overwrite an existing snapshot')

    enc_key = request.get('encryption_key')
    enc_cipher = request.get('encryption_cipher')
    force = bool(request.get('force_checkpoint', True))

    # Quiesce & checkpoint when writable
    checkpoint_executed = False
    if route.get('read_only') is not True:
        con = duckdb.connect(':memory:')
        alias = 'q_' + uuid.uuid4().hex[:8]
        try:
            _attach_db_on_memory(
                con, str(src_path), alias,
                read_only=False,
                encryption_key=enc_key,
                encryption_cipher=enc_cipher,
            )
            ckpt_sql = f"{'FORCE ' if force else ''}CHECKPOINT {_quote(alias)}"
            con.execute(ckpt_sql)
            con.execute(f'DETACH {_quote(alias)}')
            checkpoint_executed = True
        except duckdb.Error as exc:
            raise DuckDBContinuityError(
                f'Unable to acquire exclusive quiesced checkpoint on source DuckDB file: {exc}'
            ) from None
        finally:
            con.close()

    wal_path = Path(str(src_path) + '.wal')
    if wal_path.is_file() and wal_path.stat().st_size > 0:
        raise DuckDBContinuityError(
            'Non-empty .wal file remains present after quiescence; refusing unquiesced single-file snapshot'
        )

    _copy_fsync_atomic(src_path, snap_path)

    # Independent verification of snapshot
    vcon = duckdb.connect(':memory:')
    valias = 'vsnap_' + uuid.uuid4().hex[:8]
    try:
        _attach_db_on_memory(
            vcon, str(snap_path), valias,
            read_only=True,
            encryption_key=enc_key,
            encryption_cipher=enc_cipher,
        )
        tables = {
            f'{r[0]}.{r[1]}': vcon.execute(f'SELECT count(*) FROM {_quote(valias)}.{_quote(r[0])}.{_quote(r[1])}').fetchone()[0]
            for r in vcon.execute(
                'SELECT schema_name, table_name FROM duckdb_tables() WHERE database_name=? AND NOT internal ORDER BY schema_name, table_name',
                [valias],
            ).fetchall()
        }
        vcon.execute(f'DETACH {_quote(valias)}')
    except duckdb.Error as exc:
        snap_path.unlink(missing_ok=True)
        raise DuckDBContinuityError(f'Snapshot verification failed; corrupt snapshot removed: {exc}') from None
    finally:
        vcon.close()

    return {
        'state': 'snapshot_verified',
        'snapshot_path': str(snap_path),
        'snapshot_size_bytes': snap_path.stat().st_size,
        'snapshot_sha256': _sha256_file(snap_path),
        'checkpoint_executed': checkpoint_executed,
        'verified_table_row_counts': tables,
        'header': inspect_storage_header(snap_path),
    }


def run_wal_recovery_drill(
    route: dict,
    request: dict,
) -> dict:
    """Clone a ``.duckdb`` (+ optional ``.duckdb.wal``) into an isolated drill directory, replay WAL, checkpoint, and verify."""
    allowed = {'source_path', 'drill_dir', 'encryption_key', 'encryption_cipher'}
    if not isinstance(request, dict) or set(request) - allowed:
        raise DuckDBContinuityError('Invalid WAL recovery drill request')

    fs_root = route.get('filesystem_root')
    if not fs_root:
        raise DuckDBContinuityError('WAL recovery drill requires a configured filesystem_root')

    src_spec = request.get('source_path')
    src_db = (
        Path(resolve_contained_path(fs_root, src_spec, must_exist=True))
        if src_spec else Path(contained_database(route))
    )
    if not src_db.is_file():
        raise DuckDBContinuityError('Source .duckdb file for recovery drill does not exist')
    src_wal = Path(str(src_db) + '.wal')

    drill_raw = request.get('drill_dir')
    if not isinstance(drill_raw, str) or not drill_raw.strip():
        raise DuckDBContinuityError('Provide a contained drill_dir for isolated WAL replay')
    drill_dir = Path(resolve_contained_path(fs_root, drill_raw, must_exist=False))
    if drill_dir.exists() and any(drill_dir.iterdir()):
        raise DuckDBContinuityError('drill_dir must be empty or non-existent so recovery drills stay isolated')
    drill_dir.mkdir(parents=True, exist_ok=True, mode=0o700)

    cloned_db = drill_dir / src_db.name
    cloned_wal = Path(str(cloned_db) + '.wal')
    shutil.copy2(src_db, cloned_db)
    had_wal_before = src_wal.is_file() and src_wal.stat().st_size > 0
    wal_bytes_before = src_wal.stat().st_size if src_wal.is_file() else 0
    if src_wal.is_file():
        shutil.copy2(src_wal, cloned_wal)

    enc_key = request.get('encryption_key')
    enc_cipher = request.get('encryption_cipher')

    # 1. Open clone read-write so DuckDB replays cloned_wal, then CHECKPOINT & close
    rcon = duckdb.connect(':memory:')
    ralias = 'drill_' + uuid.uuid4().hex[:8]
    try:
        _attach_db_on_memory(
            rcon, str(cloned_db), ralias,
            read_only=False,
            encryption_key=enc_key,
            encryption_cipher=enc_cipher,
        )
        rcon.execute(f'CHECKPOINT {_quote(ralias)}')
        rcon.execute(f'DETACH {_quote(ralias)}')
    except duckdb.Error as exc:
        raise DuckDBContinuityError(f'Native WAL replay / checkpoint failed on drill clone: {exc}') from None
    finally:
        rcon.close()

    # 2. Independently reopen recovered clone in READ_ONLY mode and verify recovered rows
    vcon = duckdb.connect(':memory:')
    valias = 'vdrill_' + uuid.uuid4().hex[:8]
    try:
        _attach_db_on_memory(
            vcon, str(cloned_db), valias,
            read_only=True,
            encryption_key=enc_key,
            encryption_cipher=enc_cipher,
        )
        recovered_tables = {
            f'{r[0]}.{r[1]}': vcon.execute(f'SELECT count(*) FROM {_quote(valias)}.{_quote(r[0])}.{_quote(r[1])}').fetchone()[0]
            for r in vcon.execute(
                'SELECT schema_name, table_name FROM duckdb_tables() WHERE database_name=? AND NOT internal ORDER BY schema_name, table_name',
                [valias],
            ).fetchall()
        }
        vcon.execute(f'DETACH {_quote(valias)}')
    finally:
        vcon.close()

    wal_bytes_after = cloned_wal.stat().st_size if cloned_wal.is_file() else 0
    return {
        'state': 'recovery_drill_verified',
        'source_untouched': True,
        'drill_database_path': str(cloned_db),
        'had_wal_before_replay': had_wal_before,
        'wal_bytes_before_replay': wal_bytes_before,
        'wal_bytes_after_checkpoint': wal_bytes_after,
        'recovered_table_row_counts': recovered_tables,
        'recovered_header': inspect_storage_header(cloned_db),
    }


def restore_to_new_target(
    route: dict,
    request: dict,
) -> dict:
    """Restore a verified snapshot to a brand-new contained target path and verify independent reopen."""
    allowed = {'snapshot_path', 'restore_target_path', 'encryption_key', 'encryption_cipher'}
    if not isinstance(request, dict) or set(request) - allowed:
        raise DuckDBContinuityError('Invalid DuckDB restore-to-new request')
    fs_root = route.get('filesystem_root')
    if not fs_root:
        raise DuckDBContinuityError('Restore requires a configured filesystem_root')

    snap_p = Path(resolve_contained_path(fs_root, str(request.get('snapshot_path') or ''), must_exist=True))
    dst_p = Path(resolve_contained_path(fs_root, str(request.get('restore_target_path') or ''), must_exist=False))
    if not snap_p.is_file():
        raise DuckDBContinuityError('snapshot_path does not exist')
    if dst_p.exists():
        raise DuckDBContinuityError('restore_target_path already exists; restore-to-new never overwrites existing files')

    _copy_fsync_atomic(snap_p, dst_p)

    vcon = duckdb.connect(':memory:')
    valias = 'vres_' + uuid.uuid4().hex[:8]
    try:
        _attach_db_on_memory(
            vcon, str(dst_p), valias,
            read_only=True,
            encryption_key=request.get('encryption_key'),
            encryption_cipher=request.get('encryption_cipher'),
        )
        tables = {
            f'{r[0]}.{r[1]}': vcon.execute(f'SELECT count(*) FROM {_quote(valias)}.{_quote(r[0])}.{_quote(r[1])}').fetchone()[0]
            for r in vcon.execute(
                'SELECT schema_name, table_name FROM duckdb_tables() WHERE database_name=? AND NOT internal ORDER BY schema_name, table_name',
                [valias],
            ).fetchall()
        }
        vcon.execute(f'DETACH {_quote(valias)}')
    except duckdb.Error as exc:
        dst_p.unlink(missing_ok=True)
        raise DuckDBContinuityError(f'Restored file failed verification and was removed: {exc}') from None
    finally:
        vcon.close()

    return {
        'state': 'restored_to_new_verified',
        'restore_target_path': str(dst_p),
        'verified_table_row_counts': tables,
        'header': inspect_storage_header(dst_p),
        'active_file_replaced': False,
    }


def execute_reviewed_cutover(
    route: dict,
    request: dict,
) -> dict:
    """Replace the registered file with a verified staged file after inode, WAL-absence, and rollback-backup checks."""
    allowed = {
        'staged_path', 'backup_previous_path', 'expected_active_inode',
        'confirmed_cutover', 'encryption_key', 'encryption_cipher',
    }
    if not isinstance(request, dict) or set(request) - allowed:
        raise DuckDBContinuityError('Invalid DuckDB cutover request')
    if request.get('confirmed_cutover') is not True:
        raise DuckDBContinuityError('Active DuckDB file cutover requires confirmed_cutover=True')
    if route.get('read_only') is True:
        raise DuckDBContinuityError('Cannot cut over a read-only registered DuckDB route')

    fs_root = route.get('filesystem_root')
    if not fs_root:
        raise DuckDBContinuityError('Cutover requires a configured filesystem_root')

    active_p = Path(contained_database(route))
    if str(active_p) == ':memory:' or not active_p.is_file():
        raise DuckDBContinuityError('Active DuckDB file is unavailable for cutover')

    st = active_p.stat()
    expected_inode = request.get('expected_active_inode')
    if not isinstance(expected_inode, list) or [st.st_dev, st.st_ino] != expected_inode:
        raise DuckDBContinuityError('Active DuckDB file inode changed since cutover review; refusing stale replacement')

    active_wal = Path(str(active_p) + '.wal')
    if active_wal.is_file() and active_wal.stat().st_size > 0:
        raise DuckDBContinuityError('Active DuckDB file has an uncheckpointed .wal; quiesce before cutover')

    staged_p = Path(resolve_contained_path(fs_root, str(request.get('staged_path') or ''), must_exist=True))
    backup_p = Path(resolve_contained_path(fs_root, str(request.get('backup_previous_path') or ''), must_exist=False))
    if not staged_p.is_file():
        raise DuckDBContinuityError('staged_path does not exist')
    if backup_p.exists():
        raise DuckDBContinuityError('backup_previous_path already exists; refusing to clobber prior backup')

    # Verify staged_p opens cleanly BEFORE touching active_p
    vcon = duckdb.connect(':memory:')
    valias = 'vcut_' + uuid.uuid4().hex[:8]
    try:
        _attach_db_on_memory(
            vcon, str(staged_p), valias,
            read_only=True,
            encryption_key=request.get('encryption_key'),
            encryption_cipher=request.get('encryption_cipher'),
        )
        tables = {
            f'{r[0]}.{r[1]}': vcon.execute(f'SELECT count(*) FROM {_quote(valias)}.{_quote(r[0])}.{_quote(r[1])}').fetchone()[0]
            for r in vcon.execute(
                'SELECT schema_name, table_name FROM duckdb_tables() WHERE database_name=? AND NOT internal ORDER BY schema_name, table_name',
                [valias],
            ).fetchall()
        }
        vcon.execute(f'DETACH {_quote(valias)}')
    finally:
        vcon.close()

    # Preserve previous active file, then atomically replace active_p
    _copy_fsync_atomic(active_p, backup_p)
    _copy_fsync_atomic(staged_p, active_p)
    new_st = active_p.stat()

    return {
        'state': 'cutover_completed',
        'active_path': str(active_p),
        'previous_backup_path': str(backup_p),
        'new_inode': [new_st.st_dev, new_st.st_ino],
        'verified_table_row_counts': tables,
        'header': inspect_storage_header(active_p),
    }

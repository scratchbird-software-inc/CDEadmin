"""Production destination restore/cutover & archive retention/restart orchestration.

Implements PG-AUDIT-RESTORE-01 and PG-AUDIT-ARCHIVE-01 on top of the durable
`PostgreSQLContinuityJobs` workspace without weakening any existing artifact
isolation or non-replay guarantees:
- Production destination orchestration (local host grant or SSH remote host)
- Independent restored-service read/write SQL verification
- Coordinated source primary read-only fencing, promotion, cutover, and rollback
- Consumer- & backup-manifest-aware WAL archive hold registry and safe retention pruning
- Interrupted `pg_receivewal` and `pg_recvlogical` reconciliation and safe restart review
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import time
import uuid

import psycopg
from psycopg import sql

from ..operations.fileio import exclusive_file_lock, private_directory, private_file
from ..operations.store import JsonOperationStore
from ..providers.postgresql.continuity import ContinuityError, PhysicalTools
from ..providers.postgresql.continuity_archive import HISTORY, SEGMENT, iter_completed
from ..providers.postgresql.continuity_recovery import independent_copy
from ..providers.postgresql.continuity_wal import ARCHIVE_NAME, _digest, _regular

HOLD_ID_RE = re.compile(r'[a-zA-Z0-9_.-]{1,64}\Z')


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf8')
    ).hexdigest()


def _lsn_to_segment_name(lsn: str, timeline: int = 1, wal_segment_bytes: int = 16 * 1024 * 1024) -> str:
    m = re.fullmatch(r'([0-9A-Fa-f]{1,8})/([0-9A-Fa-f]{1,8})', (lsn or '').strip())
    if not m:
        raise ContinuityError(f'Invalid native WAL LSN: {lsn!r}')
    hi = int(m.group(1), 16)
    lo = int(m.group(2), 16)
    full = (hi << 32) | lo
    segno = full // wal_segment_bytes
    per_log = (1 << 32) // wal_segment_bytes
    log_id = segno // per_log
    seg_id = segno % per_log
    return f'{timeline:08X}{log_id:08X}{seg_id:08X}'


def _manifest_start_segment(backup_dir: Path, wal_segment_bytes: int = 16 * 1024 * 1024) -> str | None:
    mpath = backup_dir / 'backup' / 'backup_manifest'
    if not mpath.is_file():
        return None
    try:
        manifest_data = json.loads(mpath.read_text(encoding='utf8'))
        ranges = manifest_data.get('WAL-Ranges') or []
        segments = []
        for rng in ranges:
            tli = int(rng.get('Timeline', 1))
            start_lsn = rng.get('Start-LSN')
            if isinstance(start_lsn, str):
                segments.append(_lsn_to_segment_name(start_lsn, tli, wal_segment_bytes))
        return min(segments) if segments else None
    except Exception:
        return None


def _orchestration_store(jobs, owner: int, endpoint: str):
    base = Path(str(jobs.path) + '.orchestration') / str(owner) / endpoint
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_directory(base)
    path = base / 'state.json'
    lock_fd = os.open(str(path) + '.lock', os.O_RDWR | os.O_CREAT, 0o600)
    return path, lock_fd


def _with_orch_store(jobs, owner: int, endpoint: str, fn):
    path, lock_fd = _orchestration_store(jobs, owner, endpoint)
    try:
        with exclusive_file_lock(lock_fd):
            store = JsonOperationStore(path)
            return fn(store)
    finally:
        os.close(lock_fd)


def _check_destination_grant(app, destination_path: str, host_authorized: bool) -> Path:
    if not host_authorized:
        raise ContinuityError('Administrator host authorization is required for production destination orchestration')
    if not isinstance(destination_path, str) or not destination_path.strip() or '\x00' in destination_path:
        raise ContinuityError('Select an explicit production destination data directory')
    raw = Path(destination_path)
    if not raw.is_absolute():
        raise ContinuityError('Production destination data directory must be an absolute path')
    resolved = raw.resolve(strict=False)
    grants = app.config.get('CDEADMIN_POSTGRESQL_RESTORE_GRANTS') or app.config.get(
        'CDEADMIN_POSTGRESQL_HOST_TOOL_GRANTS'
    )
    if isinstance(grants, (list, tuple, set)):
        allowed = False
        for item in grants:
            root_str = item.get('datadir') or item.get('scratch_root') or item.get('path') if isinstance(item, dict) else str(item)
            if not root_str:
                continue
            gpath = Path(root_str).resolve(strict=False)
            if resolved == gpath or resolved.is_relative_to(gpath):
                allowed = True
                break
        if not allowed:
            raise ContinuityError('Destination directory is outside operator-granted restore roots')
    elif grants is None:
        raise ContinuityError('Configure operator restore directory grants before production destination restore')
    return resolved


# ==============================================================================
# PG-AUDIT-ARCHIVE-01: Archive Hold Registry, Retention & Stream Restart
# ==============================================================================

def archive_holds_list(jobs, owner: int, endpoint: str, request: dict) -> dict:
    archive_name = request.get('archive')
    if not isinstance(archive_name, str) or ARCHIVE_NAME.fullmatch(archive_name) is None:
        raise ContinuityError('Select one owned WAL archive name')

    def _read(store):
        data = store.read()
        holds = data.get('archive_holds', {}).get(archive_name, {})
        return {'archive': archive_name, 'holds': list(holds.values())}

    return _with_orch_store(jobs, owner, endpoint, _read)


def archive_hold_register(jobs, owner: int, endpoint: str, request: dict) -> dict:
    if not isinstance(request, dict) or set(request) - {'archive', 'hold_id', 'min_retain_segment', 'reason'}:
        raise ContinuityError('Provide archive, hold_id, min_retain_segment, and optional reason')
    archive_name = request.get('archive')
    hold_id = request.get('hold_id')
    min_seg = request.get('min_retain_segment')
    reason = str(request.get('reason') or 'operator_recovery_hold')[:512]
    if not isinstance(archive_name, str) or ARCHIVE_NAME.fullmatch(archive_name) is None:
        raise ContinuityError('Select one owned WAL archive name')
    if not isinstance(hold_id, str) or HOLD_ID_RE.fullmatch(hold_id) is None:
        raise ContinuityError('Select a valid archive hold identifier (1..64 alphanumeric/._- chars)')
    if not isinstance(min_seg, str) or SEGMENT.fullmatch(min_seg) is None:
        raise ContinuityError('min_retain_segment must be an exact 24-hex uppercase WAL segment name')
    archive_dir = jobs.archive_directory(owner, endpoint) / archive_name
    if not archive_dir.is_dir() or archive_dir.is_symlink():
        raise ContinuityError('Selected WAL archive directory does not exist')

    entry = {
        'hold_id': hold_id,
        'archive': archive_name,
        'min_retain_segment': min_seg,
        'reason': reason,
        'created_at': time.time(),
    }

    def _write(store):
        def _mut(state):
            holds = state.setdefault('archive_holds', {}).setdefault(archive_name, {})
            holds[hold_id] = entry
        store.change(_mut)
        return {'registered': True, 'hold': entry}

    return _with_orch_store(jobs, owner, endpoint, _write)


def archive_hold_release(jobs, owner: int, endpoint: str, request: dict) -> dict:
    if not isinstance(request, dict) or set(request) != {'archive', 'hold_id', 'confirmed'} or request.get('confirmed') is not True:
        raise ContinuityError('Confirm release of an explicit archive hold')
    archive_name = request.get('archive')
    hold_id = request.get('hold_id')
    if not isinstance(archive_name, str) or ARCHIVE_NAME.fullmatch(archive_name) is None:
        raise ContinuityError('Select one owned WAL archive name')

    def _write(store):
        removed = []
        def _mut(state):
            holds = state.get('archive_holds', {}).get(archive_name, {})
            if hold_id not in holds:
                raise ContinuityError('Selected archive hold does not exist')
            removed.append(holds.pop(hold_id))
        store.change(_mut)
        return {'released': True, 'hold': removed[0]}

    return _with_orch_store(jobs, owner, endpoint, _write)


def archive_retention_evaluate(jobs, owner: int, endpoint: str, request: dict) -> dict:
    """Compute dependency-aware archive pruning candidates without deleting files."""
    if not isinstance(request, dict) or set(request) - {'archive', 'retain_before_segment'}:
        raise ContinuityError('Select an owned WAL archive and optional retain_before_segment')
    archive_name = request.get('archive')
    cutoff = request.get('retain_before_segment')
    if not isinstance(archive_name, str) or ARCHIVE_NAME.fullmatch(archive_name) is None:
        raise ContinuityError('Select one owned WAL archive name')
    if cutoff is not None and (not isinstance(cutoff, str) or SEGMENT.fullmatch(cutoff) is None):
        raise ContinuityError('retain_before_segment must be an exact 24-hex uppercase WAL segment name')

    root = jobs.archive_directory(owner, endpoint)
    archive_dir = root / archive_name
    meta_path = root / f'.{archive_name}.metadata.json'
    if not archive_dir.is_dir() or archive_dir.is_symlink():
        raise ContinuityError('Selected WAL archive directory does not exist')
    meta = JsonOperationStore(meta_path).read().get('wal_archive') or {} if meta_path.is_file() else {}
    sys_id = (meta.get('source') or {}).get('system_identifier')
    seg_bytes = int((meta.get('source') or {}).get('wal_segment_bytes') or 16 * 1024 * 1024)

    blockers = []
    protected_boundaries = []

    # 1. Active writer check
    writer_job_id = meta.get('writer_job_id')
    if writer_job_id:
        try:
            _rec, obs = jobs.settled(writer_job_id, owner, endpoint)
            if obs['state'] in {'dispatching', 'active', 'verifying', 'cancel_requested'}:
                blockers.append(f'Active WAL receiver job {writer_job_id} owns archive {archive_name}')
        except ContinuityError:
            pass

    # 2. Explicit consumer holds
    holds_info = archive_holds_list(jobs, owner, endpoint, {'archive': archive_name})['holds']
    for h in holds_info:
        protected_boundaries.append({
            'source': f"hold:{h['hold_id']}",
            'segment': h['min_retain_segment'],
            'reason': h['reason'],
        })

    # 3. Backup manifest & recovery job dependencies across owned continuity jobs
    page = jobs.list(owner, endpoint, offset=0, limit=100)
    for j in page['jobs']:
        full_rec = jobs.load(j['job_id'], owner, endpoint)
        if full_rec.get('operation') in {'recovery_drill', 'production_restore'} and (
            (full_rec.get('options') or {}).get('wal_archive') == archive_name
            and j['state'] in {'reviewed', 'dispatching', 'active', 'verifying'}
        ):
            blockers.append(f"Active/reviewed recovery job {j['job_id']} references archive {archive_name}")
        if (
            sys_id
            and (full_rec.get('source') or {}).get('system_identifier') == sys_id
            and full_rec.get('operation') in {'full_backup', 'incremental_backup', 'combine'}
            and full_rec.get('state') == 'verified'
        ):
            start_seg = _manifest_start_segment(jobs.directory(full_rec), seg_bytes)
            if start_seg:
                protected_boundaries.append({
                    'source': f"backup:{j['job_id']}",
                    'segment': start_seg,
                    'reason': f"Verified {full_rec['operation']} manifest Start-LSN",
                })

    segments = sorted(p.name for p in archive_dir.iterdir() if SEGMENT.fullmatch(p.name))
    histories = sorted(p.name for p in archive_dir.iterdir() if HISTORY.fullmatch(p.name))
    # Always retain at least the newest completed segment so receiver resume point is preserved!
    if segments:
        protected_boundaries.append({
            'source': 'latest_completed_segment',
            'segment': segments[-1],
            'reason': 'Newest completed WAL segment preserved for receiver continuity',
        })

    effective_floor = min((b['segment'] for b in protected_boundaries), default=None)
    effective_cutoff = cutoff if cutoff is not None else effective_floor
    if cutoff is not None and effective_floor is not None and cutoff > effective_floor:
        blockers.append(
            f'Requested cutoff {cutoff} would delete protected WAL segment {effective_floor} '
            f'required by active holds or verified backups'
        )

    removable = [s for s in segments if effective_cutoff and s < effective_cutoff] if not blockers else []
    retained = [s for s in segments if s not in set(removable)]
    return {
        'archive': archive_name,
        'system_identifier': sys_id,
        'total_segments': len(segments),
        'history_files_retained': histories,
        'protected_boundaries': protected_boundaries,
        'effective_protected_floor': effective_floor,
        'requested_cutoff': cutoff,
        'effective_cutoff': effective_cutoff,
        'removable_segments': removable,
        'retained_segments': retained,
        'blockers': blockers,
        'prune_allowed': not blockers,
    }


def archive_retention_review(jobs, owner: int, endpoint: str, request: dict) -> dict:
    evaluation = archive_retention_evaluate(jobs, owner, endpoint, request)
    if not evaluation['prune_allowed']:
        raise ContinuityError('; '.join(evaluation['blockers']))
    archive_dir = jobs.archive_directory(owner, endpoint) / evaluation['archive']
    digests = {seg: _digest(archive_dir / seg) for seg in evaluation['removable_segments']}
    review_id = str(uuid.uuid4())
    record = {
        'review_id': review_id,
        'kind': 'archive_retention',
        'state': 'reviewed',
        'archive': evaluation['archive'],
        'evaluation': evaluation,
        'removable_digests': digests,
        'created_at': time.time(),
        'expires_at': time.time() + 600,
        'automatic_retry': False,
    }
    record['review_digest'] = _sha256_json({
        'review_id': review_id,
        'archive': evaluation['archive'],
        'removable_digests': digests,
        'effective_cutoff': evaluation['effective_cutoff'],
    })

    def _save(store):
        store.change(lambda s: s.setdefault('retention_reviews', {}).__setitem__(review_id, record))
        return deepcopy(record)

    return _with_orch_store(jobs, owner, endpoint, _save)


def archive_retention_start(jobs, owner: int, endpoint: str, request: dict) -> dict:
    if (
        not isinstance(request, dict)
        or set(request) != {'review_id', 'review_digest', 'confirmed'}
        or request.get('confirmed') is not True
    ):
        raise ContinuityError('Confirm a reviewed archive retention plan with review_id and review_digest')
    review_id = request['review_id']

    def _claim(store):
        state = store.read()
        rec = state.get('retention_reviews', {}).get(review_id)
        if not rec:
            raise ContinuityError('Archive retention review is unavailable')
        if rec['review_digest'] != request['review_digest']:
            raise ContinuityError('Archive retention review digest mismatch')
        if rec['state'] != 'reviewed':
            raise ContinuityError('Archive retention review was already dispatched; automatic replay is refused')
        if time.time() > rec['expires_at']:
            raise ContinuityError('Archive retention review expired; evaluate again')
        def _mut(s):
            s['retention_reviews'][review_id]['state'] = 'executing'
        store.change(_mut)
        return deepcopy(rec)

    rec = _with_orch_store(jobs, owner, endpoint, _claim)
    # Re-evaluate live holds & writers right before unlinking!
    live_eval = archive_retention_evaluate(
        jobs, owner, endpoint,
        {'archive': rec['archive'], 'retain_before_segment': rec['evaluation']['effective_cutoff']}
    )
    if not live_eval['prune_allowed']:
        def _fail(store):
            store.change(lambda s: s['retention_reviews'][review_id].update(
                state='refused', blockers=live_eval['blockers'], finished_at=time.time()
            ))
        _with_orch_store(jobs, owner, endpoint, _fail)
        raise ContinuityError('; '.join(live_eval['blockers']))

    archive_dir = jobs.archive_directory(owner, endpoint) / rec['archive']
    removed = []
    for seg, expected_digest in rec['removable_digests'].items():
        target = archive_dir / seg
        if not target.exists():
            continue
        _regular(target)
        if _digest(target) != expected_digest:
            raise ContinuityError(f'WAL segment {seg} changed after retention review; aborting cleanup')
        target.unlink()
        removed.append({'name': seg, 'sha256': expected_digest['sha256'], 'bytes': expected_digest['bytes']})

    def _finish(store):
        def _mut(s):
            s['retention_reviews'][review_id].update(
                state='completed',
                removed_segments=removed,
                removed_count=len(removed),
                finished_at=time.time(),
            )
        store.change(_mut)
        return deepcopy(store.read()['retention_reviews'][review_id])

    return _with_orch_store(jobs, owner, endpoint, _finish)


def stream_restart_review(
    service,
    server,
    jobs,
    owner: int,
    endpoint: str,
    request: dict,
    *,
    source: dict,
    configuration: str,
    paths: dict,
    runtime_limit,
) -> dict:
    """Reconcile an interrupted WAL or logical receiver job and issue a fresh review (never auto-started)."""
    if not isinstance(request, dict) or set(request) - {'prior_job_id', 'options'}:
        raise ContinuityError('Select prior_job_id and optional updated receiver options')
    prior_id = request.get('prior_job_id')
    prior, observed = jobs.settled(prior_id, owner, endpoint)
    if observed['state'] not in {'cancelled', 'failed', 'captured', 'unknown'}:
        raise ContinuityError('Stop the active stream job before preparing a reconciled restart review')
    jobs.require_stopped_writer(prior)

    op = prior.get('operation')
    override_opts = request.get('options') or {}
    if not isinstance(override_opts, dict):
        raise ContinuityError('Override options must be an object')

    if op == 'wal_capture':
        archive_name = prior['options']['archive']
        archive_dir = jobs.archive_directory(owner, endpoint) / archive_name
        archive_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        private_directory(archive_dir)
        staging = jobs.directory(prior) / 'wal-capture'
        published_during_reconcile = []
        if staging.is_dir():
            for receipt in iter_completed(staging, archive_dir, prior['source']):
                published_during_reconcile.append(receipt)
        segments = sorted(p.name for p in archive_dir.iterdir() if SEGMENT.fullmatch(p.name))
        merged_opts = {**prior['options'], **override_opts, 'archive': archive_name}
        from .postgresql_continuity_capture import review as wal_review
        reviewed = wal_review(
            jobs,
            {'operation': 'wal_capture', 'options': merged_opts},
            owner,
            endpoint,
            source,
            configuration,
            paths,
            runtime_limit,
        )
        reviewed['reconciled_prior_job'] = {
            'prior_job_id': prior_id,
            'prior_state': observed['state'],
            'published_during_reconcile': len(published_during_reconcile),
            'resume_after_segment': segments[-1] if segments else None,
            'automatic_dispatch': False,
        }
        return reviewed

    if op == 'logical_stream_capture':
        from . import postgresql_logical_stream as lstream
        reconciled = lstream.reconcile(jobs, jobs.load(prior_id, owner, endpoint))
        slot_snap = source.get('slot_snapshot') or {}
        live_flush_lsn = slot_snap.get('confirmed_flush_lsn') or '0/0'
        merged_opts = {
            **prior['options'],
            **override_opts,
            'slot': prior['options']['slot'],
            'start_lsn': override_opts.get('start_lsn') or live_flush_lsn,
        }
        reviewed = lstream.review(
            jobs,
            {
                'operation': 'logical_stream_capture',
                'database_target_id': prior['database_target_id'],
                'options': merged_opts,
            },
            owner,
            endpoint,
            source,
            configuration,
            paths,
            runtime_limit,
        )
        reviewed['reconciled_prior_job'] = {
            'prior_job_id': prior_id,
            'prior_state': observed['state'],
            'prior_sealed_artifact': reconciled.get('logical_stream_artifact'),
            'prior_confirmed_lsn': (prior.get('source') or {}).get('logical_stream_confirmed_lsn'),
            'resumed_confirmed_flush_lsn': live_flush_lsn,
            'automatic_dispatch': False,
        }
        return reviewed

    raise ContinuityError('Stream restart review applies only to wal_capture or logical_stream_capture jobs')


# ==============================================================================
# PG-AUDIT-RESTORE-01: Production Destination Restore, Service Verification & Cutover
# ==============================================================================

def _ssh_run(ssh_cfg: dict, remote_cmd: str, *, input_bytes: bytes | None = None, timeout: int = 300) -> subprocess.CompletedProcess:
    host = ssh_cfg.get('host')
    user = ssh_cfg.get('user')
    port = int(ssh_cfg.get('port') or 22)
    key_file = ssh_cfg.get('identity_file')
    if not isinstance(host, str) or not host:
        raise ContinuityError('SSH execution host requires an explicit host')
    target = f'{user}@{host}' if user else host
    cmd = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-p', str(port)]
    if key_file:
        cmd.extend(['-i', str(key_file)])
    cmd.extend([target, remote_cmd])
    return subprocess.run(cmd, input=input_bytes, capture_output=True, timeout=timeout, check=False)


def restore_review(app, jobs, owner: int, endpoint: str, paths: dict, request: dict, *, host_authorized: bool) -> dict:
    """Review a production physical restore to a granted local or SSH remote destination."""
    if not isinstance(request, dict):
        raise ContinuityError('Production restore review requires an options object')
    allowed = {
        'base_job_id', 'destination_mode', 'destination_datadir', 'ssh_host',
        'wal_archive', 'recovery_target', 'listen_port', 'start_service',
        'standby_mode', 'primary_conninfo', 'verify_read_write', 'database',
    }
    if set(request) - allowed:
        raise ContinuityError('Unsupported production restore review fields')
    base_job_id = request.get('base_job_id')
    previous, _obs = jobs.settled(base_job_id, owner, endpoint)
    if previous['state'] != 'verified' or not previous.get('manifest'):
        raise ContinuityError('Production restore requires a verified, manifest-bearing backup artifact')
    if previous['operation'] not in {'full_backup', 'combine'}:
        raise ContinuityError('Production restore requires a full or reconstructed physical backup')
    jobs.require_stopped_writer(previous)

    mode = request.get('destination_mode', 'local')
    if mode not in {'local', 'ssh'}:
        raise ContinuityError('destination_mode must be local or ssh')
    if mode == 'local':
        dest_dir = _check_destination_grant(app, request.get('destination_datadir', ''), host_authorized)
        if dest_dir.exists() and any(dest_dir.iterdir()):
            if (dest_dir / 'postmaster.pid').exists():
                raise ContinuityError('Production destination contains a live postmaster.pid; stop and clear before restore')
            raise ContinuityError('Production destination directory must be empty before restore')
        dest_str = str(dest_dir)
    else:
        if not host_authorized:
            raise ContinuityError('Administrator host authorization is required for SSH remote restore')
        ssh_cfg = request.get('ssh_host')
        dest_str = request.get('destination_datadir', '')
        if not isinstance(ssh_cfg, dict) or not ssh_cfg.get('host') or not isinstance(dest_str, str) or not dest_str.startswith('/'):
            raise ContinuityError('SSH restore requires ssh_host metadata and an absolute remote destination_datadir')

    wal_archive = request.get('wal_archive')
    if wal_archive is not None:
        if not isinstance(wal_archive, str) or ARCHIVE_NAME.fullmatch(wal_archive) is None:
            raise ContinuityError('Invalid native WAL archive name')
        arch_dir = jobs.archive_directory(owner, endpoint) / wal_archive
        if not arch_dir.is_dir():
            raise ContinuityError('Selected WAL archive directory does not exist')

    start_service = bool(request.get('start_service', False))
    standby_mode = bool(request.get('standby_mode', False))
    verify_rw = bool(request.get('verify_read_write', start_service and not standby_mode))
    listen_port = request.get('listen_port')
    if start_service:
        if type(listen_port) is not int or not 1024 <= listen_port <= 65535:
            raise ContinuityError('Starting a restored PostgreSQL service requires an explicit listen_port (1024..65535)')
    if verify_rw and standby_mode:
        raise ContinuityError('Read-write verification requires a promoted primary restore, not standby_mode')

    tools = PhysicalTools(paths)
    pg_ctl_id = tools.identify('pg_ctl', jobs.root) if mode == 'local' else {'available': True, 'mode': 'ssh'}
    if mode == 'local' and start_service and not pg_ctl_id.get('available'):
        raise ContinuityError('Install PostgreSQL 18 pg_ctl on the application host to start the restored service')

    restore_id = str(uuid.uuid4())
    plan = {
        'restore_id': restore_id,
        'state': 'reviewed',
        'base_job_id': base_job_id,
        'manifest_sha256': previous['manifest']['manifest_sha256'],
        'system_identifier': previous['source']['system_identifier'],
        'destination_mode': mode,
        'destination_datadir': dest_str,
        'ssh_host': deepcopy(request.get('ssh_host')) if mode == 'ssh' else None,
        'wal_archive': wal_archive,
        'recovery_target': deepcopy(request.get('recovery_target')),
        'standby_mode': standby_mode,
        'primary_conninfo': request.get('primary_conninfo') or '',
        'start_service': start_service,
        'listen_port': listen_port,
        'verify_read_write': verify_rw,
        'database': request.get('database') or 'postgres',
        'paths': deepcopy(paths),
        'created_at': time.time(),
        'expires_at': time.time() + 600,
        'automatic_retry': False,
    }
    plan['review_digest'] = _sha256_json({
        k: plan[k]
        for k in (
            'restore_id', 'base_job_id', 'manifest_sha256', 'destination_mode',
            'destination_datadir', 'wal_archive', 'recovery_target', 'standby_mode',
            'start_service', 'listen_port', 'verify_read_write', 'database',
        )
    })

    def _save(store):
        store.change(lambda s: s.setdefault('production_restores', {}).__setitem__(restore_id, plan))
        return deepcopy(plan)

    return _with_orch_store(jobs, owner, endpoint, _save)


def restore_start(app, jobs, owner: int, endpoint: str, request: dict, *, host_authorized: bool) -> dict:
    """Execute a reviewed production destination restore with optional service start & R/W acceptance."""
    if (
        not isinstance(request, dict)
        or set(request) != {'restore_id', 'review_digest', 'confirmed'}
        or request.get('confirmed') is not True
    ):
        raise ContinuityError('Confirm production restore with restore_id, review_digest, and confirmed=True')
    restore_id = request['restore_id']

    def _claim(store):
        state = store.read()
        rec = state.get('production_restores', {}).get(restore_id)
        if not rec:
            raise ContinuityError('Production restore review is unavailable')
        if rec['review_digest'] != request['review_digest']:
            raise ContinuityError('Production restore review digest mismatch')
        if rec['state'] != 'reviewed':
            raise ContinuityError('Production restore review was already dispatched; automatic replay is refused')
        if time.time() > rec['expires_at']:
            raise ContinuityError('Production restore review expired; prepare it again')
        def _mut(s):
            s['production_restores'][restore_id]['state'] = 'executing'
            s['production_restores'][restore_id]['dispatched_at'] = time.time()
        store.change(_mut)
        return deepcopy(rec)

    plan = _with_orch_store(jobs, owner, endpoint, _claim)
    previous = jobs.load(plan['base_job_id'], owner, endpoint)
    if previous.get('manifest', {}).get('manifest_sha256') != plan['manifest_sha256']:
        raise ContinuityError('Backup artifact manifest changed after restore review')
    source_backup = jobs.directory(previous) / 'backup'

    try:
        staged_wal_count = 0
        if plan['destination_mode'] == 'local':
            dest_dir = _check_destination_grant(app, plan['destination_datadir'], host_authorized)
            if dest_dir.exists() and any(dest_dir.iterdir()):
                raise ContinuityError('Production destination became non-empty after review; aborting restore')
            dest_dir.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            import threading
            copy_receipt = independent_copy(
                source_backup,
                dest_dir,
                [],
                progress=lambda _p: None,
                cancel_signal=threading.Event(),
            )
            # Stage WAL archive segments if selected
            if plan['wal_archive']:
                arch_dir = jobs.archive_directory(owner, endpoint) / plan['wal_archive']
                pg_wal = dest_dir / 'pg_wal'
                pg_wal.mkdir(exist_ok=True, mode=0o700)
                for entry in sorted(arch_dir.iterdir()):
                    if SEGMENT.fullmatch(entry.name) or HISTORY.fullmatch(entry.name):
                        shutil.copy2(entry, pg_wal / entry.name)
                        private_file(pg_wal / entry.name)
                        staged_wal_count += 1

            # Sanitize inherited auto.conf & configure recovery / standby / listener
            for sig in ('standby.signal', 'recovery.signal'):
                (dest_dir / sig).unlink(missing_ok=True)
            auto_lines = ["listen_addresses = '127.0.0.1'"]
            if plan['listen_port']:
                sock_dir = Path(f'/tmp/sr-pgrest-{uuid.uuid4().hex[:8]}')
                sock_dir.mkdir(mode=0o700, exist_ok=True)
                auto_lines.append(f"port = {int(plan['listen_port'])}")
                auto_lines.append(f"unix_socket_directories = '{sock_dir}'")
            else:
                sock_dir = None
            if plan['standby_mode']:
                (dest_dir / 'standby.signal').write_bytes(b'')
                private_file(dest_dir / 'standby.signal')
                if plan['primary_conninfo']:
                    esc = plan['primary_conninfo'].replace('\\', '\\\\').replace("'", "''")
                    auto_lines.append(f"primary_conninfo = '{esc}'")
            elif plan['recovery_target']:
                rt = plan['recovery_target']
                (dest_dir / 'recovery.signal').write_bytes(b'')
                private_file(dest_dir / 'recovery.signal')
                auto_lines.append("recovery_target_action = 'promote'")
                if rt.get('kind') == 'immediate':
                    auto_lines.append("recovery_target = 'immediate'")
                elif rt.get('kind') in {'time', 'xid', 'lsn', 'name'} and rt.get('value'):
                    val = str(rt['value']).replace('\\', '\\\\').replace("'", "''")
                    auto_lines.append(f"recovery_target_{rt['kind']} = '{val}'")
            auto_conf = dest_dir / 'postgresql.auto.conf'
            auto_conf.write_text('\n'.join(auto_lines) + '\n', encoding='utf8')
            private_file(auto_conf)

            service_receipt = {'started': False}
            acceptance_receipt = None
            if plan['start_service']:
                pg_ctl_bin = str(Path(plan['paths']['pg_ctl']))
                log_file = dest_dir / 'restored-postmaster.log'
                proc = subprocess.run(
                    [pg_ctl_bin, '-D', str(dest_dir), '-l', str(log_file), '-w', '-t', '30', 'start'],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if proc.returncode != 0:
                    raise ContinuityError(
                        f'Restored PostgreSQL service failed to start: {(proc.stderr or proc.stdout).strip()[:512]}'
                    )
                service_receipt = {
                    'started': True,
                    'host': '127.0.0.1',
                    'port': plan['listen_port'],
                    'socket_dir': str(sock_dir) if sock_dir else None,
                    'log_file': str(log_file),
                }
                if plan['verify_read_write']:
                    acceptance_receipt = verify_restored_service_dsn(
                        f"host=127.0.0.1 port={plan['listen_port']} dbname={plan['database']}",
                        expected_system_identifier=plan['system_identifier'],
                    )
            outcome = {
                'state': 'completed',
                'copy_receipt': copy_receipt,
                'staged_wal_segments': staged_wal_count,
                'service_receipt': service_receipt,
                'restored_service_acceptance': acceptance_receipt,
                'finished_at': time.time(),
            }
        else:
            # SSH remote destination orchestration
            ssh_cfg = plan['ssh_host']
            remote_dir = shlex.quote(plan['destination_datadir'])
            pre = _ssh_run(
                ssh_cfg,
                f"python3 -c 'import os,sys; p={plan['destination_datadir']!r}; "
                f"sys.exit(2 if os.path.exists(p) and os.listdir(p) else 0)' && install -d -m 0700 {remote_dir}",
            )
            if pre.returncode != 0:
                raise ContinuityError(
                    f'Remote destination preflight failed (rc={pre.returncode}): {pre.stderr.decode("utf8", "replace")[:256]}'
                )
            tar_proc = subprocess.Popen(
                ['tar', '-cf', '-', '-C', str(source_backup), '.'],
                stdout=subprocess.PIPE,
            )
            assert tar_proc.stdout is not None
            tar_bytes = tar_proc.stdout.read()
            tar_rc = tar_proc.wait()
            if tar_rc != 0:
                raise ContinuityError('Failed to stream verified backup tar payload for SSH restore')
            unpack = _ssh_run(ssh_cfg, f'tar -xpf - -C {remote_dir} && chmod 0700 {remote_dir}', input_bytes=tar_bytes)
            if unpack.returncode != 0:
                raise ContinuityError(
                    f'Remote backup extraction failed: {unpack.stderr.decode("utf8", "replace")[:256]}'
                )
            outcome = {
                'state': 'completed',
                'copy_receipt': {'ssh_streamed_bytes': len(tar_bytes), 'remote_datadir': plan['destination_datadir']},
                'staged_wal_segments': 0,
                'service_receipt': {'started': False, 'mode': 'ssh'},
                'restored_service_acceptance': None,
                'finished_at': time.time(),
            }
    except Exception as exc:
        def _record_err(store):
            store.change(lambda s: s['production_restores'][restore_id].update(
                state='failed',
                error=str(exc),
                finished_at=time.time(),
            ))
        _with_orch_store(jobs, owner, endpoint, _record_err)
        raise

    def _finish(store):
        def _mut(s):
            s['production_restores'][restore_id].update(outcome)
        store.change(_mut)
        return deepcopy(store.read()['production_restores'][restore_id])

    return _with_orch_store(jobs, owner, endpoint, _finish)


def verify_restored_service_dsn(dsn: str, *, expected_system_identifier: str) -> dict:
    """Independently connect to a restored PostgreSQL service and verify identity + read/write durability."""
    probe_token = 'sr_restore_probe_' + uuid.uuid4().hex[:10]
    with psycopg.connect(dsn, autocommit=False, connect_timeout=10) as conn:
        sys_id, in_rec, ver_num, current_db = conn.execute(
            'SELECT (SELECT system_identifier::text FROM pg_catalog.pg_control_system()), '
            'pg_catalog.pg_is_in_recovery(), '
            "current_setting('server_version_num')::int, "
            'pg_catalog.current_database()'
        ).fetchone()
        if str(sys_id) != str(expected_system_identifier):
            raise ContinuityError(
                f'Restored service system_identifier {sys_id} does not match expected {expected_system_identifier}'
            )
        if in_rec is not False:
            raise ContinuityError('Restored service is still in recovery; promotion is unconfirmed')
        # Execute real read-write probe in a temporary table & commit to verify WAL write path!
        conn.execute(sql.SQL('CREATE TEMP TABLE {} (probe text NOT NULL)').format(sql.Identifier(probe_token)))
        conn.execute(sql.SQL('INSERT INTO {} VALUES (%s)').format(sql.Identifier(probe_token)), (probe_token,))
        echoed = conn.execute(sql.SQL('SELECT probe FROM {}').format(sql.Identifier(probe_token))).fetchone()[0]
        conn.commit()
        if echoed != probe_token:
            raise ContinuityError('Restored service read/write probe returned unexpected payload')
    return {
        'verified': True,
        'system_identifier': str(sys_id),
        'in_recovery': False,
        'server_version_num': ver_num,
        'database': current_db,
        'read_write_transaction_committed': True,
        'verified_at': time.time(),
    }


def cutover_review(jobs, owner: int, endpoint: str, source_dsn: str, request: dict) -> dict:
    """Review coordinated replacement/cutover from source primary to restored/standby service."""
    if not isinstance(request, dict) or set(request) - {
        'restore_id', 'target_dsn', 'terminate_source_writers', 'promote_if_standby'
    }:
        raise ContinuityError('Provide restore_id (or target_dsn) for coordinated cutover review')
    restore_id = request.get('restore_id')
    target_dsn = request.get('target_dsn')
    if restore_id:
        def _load_r(store):
            return store.read().get('production_restores', {}).get(restore_id)
        rest = _with_orch_store(jobs, owner, endpoint, _load_r)
        if not rest or rest.get('state') != 'completed':
            raise ContinuityError('Select a completed production restore for cutover')
        if not target_dsn and rest.get('service_receipt', {}).get('started'):
            target_dsn = f"host=127.0.0.1 port={rest['service_receipt']['port']} dbname={rest['database']}"
    if not isinstance(target_dsn, str) or not target_dsn.strip():
        raise ContinuityError('Provide target_dsn for the replacement PostgreSQL service')

    with psycopg.connect(source_dsn, autocommit=True, connect_timeout=10) as sconn:
        src_sys, src_ro, src_rec, src_lsn = sconn.execute(
            'SELECT (SELECT system_identifier::text FROM pg_catalog.pg_control_system()), '
            "current_setting('default_transaction_read_only'), "
            'pg_catalog.pg_is_in_recovery(), '
            'CASE WHEN pg_catalog.pg_is_in_recovery() THEN pg_catalog.pg_last_wal_replay_lsn()::text '
            'ELSE pg_catalog.pg_current_wal_lsn()::text END'
        ).fetchone()
    with psycopg.connect(target_dsn, autocommit=True, connect_timeout=10) as tconn:
        tgt_sys, tgt_rec, tgt_tli = tconn.execute(
            'SELECT (SELECT system_identifier::text FROM pg_catalog.pg_control_system()), '
            'pg_catalog.pg_is_in_recovery(), '
            '(SELECT timeline_id FROM pg_catalog.pg_control_checkpoint())'
        ).fetchone()
    if str(src_sys) != str(tgt_sys):
        raise ContinuityError('Cutover target belongs to a different PostgreSQL cluster system_identifier')

    cutover_id = str(uuid.uuid4())
    record = {
        'cutover_id': cutover_id,
        'state': 'reviewed',
        'restore_id': restore_id,
        'target_dsn': target_dsn,
        'system_identifier': str(src_sys),
        'source_initial_read_only': src_ro,
        'source_in_recovery': src_rec,
        'source_lsn_at_review': src_lsn,
        'target_in_recovery_at_review': tgt_rec,
        'target_timeline_at_review': tgt_tli,
        'terminate_source_writers': bool(request.get('terminate_source_writers', False)),
        'promote_if_standby': bool(request.get('promote_if_standby', True)),
        'created_at': time.time(),
        'expires_at': time.time() + 600,
        'automatic_retry': False,
    }
    record['review_digest'] = _sha256_json({
        'cutover_id': cutover_id,
        'system_identifier': str(src_sys),
        'target_dsn': target_dsn,
        'terminate_source_writers': record['terminate_source_writers'],
        'promote_if_standby': record['promote_if_standby'],
    })

    def _save(store):
        store.change(lambda s: s.setdefault('cutovers', {}).__setitem__(cutover_id, record))
        return deepcopy(record)

    return _with_orch_store(jobs, owner, endpoint, _save)


def cutover_start(jobs, owner: int, endpoint: str, source_dsn: str, request: dict) -> dict:
    """Fence source primary read-only, promote replacement if needed, and verify read/write service."""
    if (
        not isinstance(request, dict)
        or set(request) != {'cutover_id', 'review_digest', 'confirmed'}
        or request.get('confirmed') is not True
    ):
        raise ContinuityError('Confirm cutover with cutover_id, review_digest, and confirmed=True')
    cutover_id = request['cutover_id']

    def _claim(store):
        rec = store.read().get('cutovers', {}).get(cutover_id)
        if not rec:
            raise ContinuityError('Cutover review is unavailable')
        if rec['review_digest'] != request['review_digest']:
            raise ContinuityError('Cutover review digest mismatch')
        if rec['state'] != 'reviewed':
            raise ContinuityError('Cutover review was already dispatched; automatic replay is refused')
        if time.time() > rec['expires_at']:
            raise ContinuityError('Cutover review expired; prepare it again')
        def _mut(s):
            s['cutovers'][cutover_id]['state'] = 'executing'
        store.change(_mut)
        return deepcopy(rec)

    rec = _with_orch_store(jobs, owner, endpoint, _claim)
    try:
        # 1. Fence source primary read-only + reload + checkpoint
        with psycopg.connect(source_dsn, autocommit=True, connect_timeout=10) as sconn:
            sys_id = sconn.execute('SELECT system_identifier::text FROM pg_catalog.pg_control_system()').fetchone()[0]
            if str(sys_id) != rec['system_identifier']:
                raise ContinuityError('Source cluster identity changed before cutover fencing')
            sconn.execute("ALTER SYSTEM SET default_transaction_read_only = 'on'")
            sconn.execute('SELECT pg_catalog.pg_reload_conf()')
            terminated = 0
            if rec['terminate_source_writers']:
                terminated = int(sconn.execute(
                    'SELECT count(*) FROM ('
                    '  SELECT pg_catalog.pg_terminate_backend(pid) '
                    '  FROM pg_catalog.pg_stat_activity '
                    "  WHERE pid <> pg_backend_pid() AND backend_type = 'client backend' "
                    '    AND backend_xid IS NOT NULL'
                    ') t'
                ).fetchone()[0])
            if not rec['source_in_recovery']:
                sconn.execute('CHECKPOINT')
            fenced_ro = sconn.execute("SHOW default_transaction_read_only").fetchone()[0]

        # 2. Promote target if in recovery, then run independent R/W verification
        promoted = False
        with psycopg.connect(rec['target_dsn'], autocommit=True, connect_timeout=10) as tconn:
            in_rec = tconn.execute('SELECT pg_catalog.pg_is_in_recovery()').fetchone()[0]
            if in_rec:
                if not rec['promote_if_standby']:
                    raise ContinuityError('Target service is in standby recovery and promote_if_standby is False')
                ok = tconn.execute('SELECT pg_catalog.pg_promote(true, 30)').fetchone()[0]
                if not ok:
                    raise ContinuityError('Target PostgreSQL promotion did not complete within 30s')
                promoted = True

        acceptance = verify_restored_service_dsn(
            rec['target_dsn'], expected_system_identifier=rec['system_identifier']
        )
        result_fields = {
            'state': 'completed',
            'source_fenced_read_only': fenced_ro == 'on',
            'terminated_source_writers': terminated,
            'target_promoted': promoted,
            'target_acceptance': acceptance,
            'finished_at': time.time(),
        }
    except Exception as exc:
        def _err(store):
            store.change(lambda s: s['cutovers'][cutover_id].update(
                state='failed', error=str(exc), finished_at=time.time()
            ))
        _with_orch_store(jobs, owner, endpoint, _err)
        raise

    def _done(store):
        store.change(lambda s: s['cutovers'][cutover_id].update(result_fields))
        return deepcopy(store.read()['cutovers'][cutover_id])

    return _with_orch_store(jobs, owner, endpoint, _done)


def cutover_rollback(jobs, owner: int, endpoint: str, source_dsn: str, request: dict) -> dict:
    """Unfence the original primary (reset default_transaction_read_only) on explicit rollback confirmation."""
    if (
        not isinstance(request, dict)
        or set(request) != {'cutover_id', 'confirmed'}
        or request.get('confirmed') is not True
    ):
        raise ContinuityError('Confirm cutover rollback with cutover_id and confirmed=True')
    cutover_id = request['cutover_id']

    def _load(store):
        rec = store.read().get('cutovers', {}).get(cutover_id)
        if not rec:
            raise ContinuityError('Cutover receipt is unavailable')
        return deepcopy(rec)

    rec = _with_orch_store(jobs, owner, endpoint, _load)
    with psycopg.connect(source_dsn, autocommit=True, connect_timeout=10) as sconn:
        sys_id = sconn.execute('SELECT system_identifier::text FROM pg_catalog.pg_control_system()').fetchone()[0]
        if str(sys_id) != rec['system_identifier']:
            raise ContinuityError('Source cluster identity does not match cutover receipt')
        sconn.execute('SET transaction_read_only = off')
        if rec['source_initial_read_only'] == 'off':
            sconn.execute('ALTER SYSTEM RESET default_transaction_read_only')
        else:
            sconn.execute("ALTER SYSTEM SET default_transaction_read_only = 'on'")
        sconn.execute('SELECT pg_catalog.pg_reload_conf()')
    expected_ro = rec['source_initial_read_only']
    restored_ro = None
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        with psycopg.connect(source_dsn, autocommit=True, connect_timeout=5) as check_conn:
            restored_ro = check_conn.execute('SHOW default_transaction_read_only').fetchone()[0]
            if restored_ro == expected_ro:
                break
        time.sleep(0.05)

    def _finish(store):
        def _mut(s):
            s['cutovers'][cutover_id].update(
                state='rolled_back',
                rolled_back_at=time.time(),
                source_restored_read_only=restored_ro,
            )
        store.change(_mut)
        return deepcopy(store.read()['cutovers'][cutover_id])

    return _with_orch_store(jobs, owner, endpoint, _finish)


def orchestration_status(jobs, owner: int, endpoint: str, request: dict) -> dict:
    if not isinstance(request, dict) or set(request) - {'restore_id', 'cutover_id', 'review_id'}:
        raise ContinuityError('Select restore_id, cutover_id, or review_id')

    def _read(store):
        data = store.read()
        if 'restore_id' in request:
            rec = data.get('production_restores', {}).get(request['restore_id'])
        elif 'cutover_id' in request:
            rec = data.get('cutovers', {}).get(request['cutover_id'])
        else:
            rec = data.get('retention_reviews', {}).get(request.get('review_id'))
        if not rec:
            raise ContinuityError('Requested orchestration receipt does not exist')
        return deepcopy(rec)

    return _with_orch_store(jobs, owner, endpoint, _read)

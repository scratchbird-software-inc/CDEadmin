"""Native Firebird 5.0.4 replication setup, seeding, journal shipping and promotion.

Models Firebird's actual journal-segment / synchronous-attachment replication
without inventing automatic HA failover, quorum or PostgreSQL WAL byte-LSN lag.
"""
from collections.abc import Mapping
import os
from pathlib import Path
import re
import shutil
import subprocess

from .host_configuration import render_replication_conf
from .host_runtime_grant import file_sha256, verify_same_host

REPLICA_MODES = {0: 'NONE', 1: 'READ_ONLY', 2: 'READ_WRITE'}
_SEGMENT_RE = re.compile(r'^(?P<prefix>.+)\.journal-(?P<seq>\d{9})$')


def descriptor():
    return {
        'schema': 'scratchrobin.firebird.replication-workflow-api@1',
        'engine_version': '5.0.4',
        'supported_platforms': ['linux'],
        'requires_permissions': ['administer', 'maintenance_admin'],
        'actions': ['describe', 'inspect', 'review', 'apply', 'get', 'list'],
        'operations': [
            'configure_primary',
            'seed_replica',
            'distribute_segments',
            'promote_replica',
        ],
        'automatic_failover_supported': False,
        'automatic_cluster_consensus_supported': False,
        'postgresql_wal_lsn_semantics': False,
        'lag_authority': (
            'Unapplied journal segment count/sequence numbers in journal directories '
            'and bounded replication.log diagnostics; Firebird 5.0.4 does not expose '
            'PostgreSQL-style SQL WAL byte-lag views.'
        ),
    }


def _scan_journal_directory(directory):
    root = Path(directory)
    if not root.is_dir():
        return {
            'directory': str(root),
            'exists': False,
            'segment_count': 0,
            'total_bytes': 0,
            'min_sequence': None,
            'max_sequence': None,
            'segments': [],
        }
    segments = []
    # Firebird places archived segments either directly or under {DB_GUID}/ subdirectories.
    candidates = list(root.iterdir())
    for entry in list(candidates):
        if entry.is_dir() and not entry.is_symlink():
            candidates.extend(entry.iterdir())
    for entry in sorted(candidates, key=lambda p: str(p)):
        if not entry.is_file() or entry.is_symlink():
            continue
        match = _SEGMENT_RE.match(entry.name)
        if not match:
            continue
        seq = int(match.group('seq'))
        st = entry.stat()
        rel = entry.relative_to(root).as_posix()
        segments.append({
            'relative_path': rel,
            'filename': entry.name,
            'sequence': seq,
            'size_bytes': st.st_size,
            'sha256': file_sha256(entry),
        })
    segments.sort(key=lambda item: (item['sequence'], item['relative_path']))
    seqs = [s['sequence'] for s in segments]
    return {
        'directory': str(root),
        'exists': True,
        'segment_count': len(segments),
        'total_bytes': sum(s['size_bytes'] for s in segments),
        'min_sequence': min(seqs) if seqs else None,
        'max_sequence': max(seqs) if seqs else None,
        'segments': segments,
    }


def _read_replication_log_tail(runtime_root, max_lines=60):
    log_path = Path(runtime_root) / 'replication.log'
    if not log_path.is_file() or log_path.is_symlink():
        return {'present': False, 'error_count': 0, 'last_replicated_segment': None, 'lines': []}
    raw = log_path.read_bytes()[-65536:].decode('utf-8', errors='replace')
    lines = [ln.rstrip('\r') for ln in raw.splitlines() if ln.strip()][-max_lines:]
    errors = sum(1 for ln in lines if 'ERROR:' in ln)
    last_rep = None
    for ln in lines:
        m = re.search(r'Segment\s+(\d+)\s+.*is replicated', ln)
        if m:
            last_rep = int(m.group(1))
    return {
        'present': True,
        'error_count': errors,
        'last_replicated_segment': last_rep,
        'lines': lines,
    }


def inspect_replication_state(host_scope, client=None, route=None):
    db_state = None
    if client is not None and route is not None and route.get('database'):
        import firebird.driver as native
        conn = client._connect({'route': route})
        try:
            guid = conn.info.get_info(native.DbInfoCode.DB_GUID)
            cur = conn.cursor()
            try:
                cur.execute('SELECT MON$REPLICA_MODE, MON$READ_ONLY, MON$DATABASE_NAME FROM MON$DATABASE')
                rep_mode, read_only, db_name = cur.fetchone()
                cur.execute(
                    'SELECT TRIM(TRAILING FROM RDB$PUBLICATION_NAME), RDB$ACTIVE_FLAG, RDB$AUTO_ENABLE '
                    'FROM RDB$PUBLICATIONS ORDER BY 1'
                )
                pubs = [
                    {
                        'name': r[0],
                        'active': bool(r[1]),
                        'auto_enable': bool(r[2]),
                    }
                    for r in cur.fetchall()
                ]
                cur.execute(
                    'SELECT TRIM(TRAILING FROM RDB$PUBLICATION_NAME), TRIM(TRAILING FROM RDB$TABLE_NAME) '
                    'FROM RDB$PUBLICATION_TABLES ORDER BY 1, 2'
                )
                pub_tables = [{'publication': r[0], 'table': r[1]} for r in cur.fetchall()]
            finally:
                cur.close()
            conn.rollback()
            mode_code = int(rep_mode or 0)
            db_state = {
                'database_name': db_name,
                'database_guid': guid,
                'replica_mode_code': mode_code,
                'replica_mode': REPLICA_MODES.get(mode_code, 'UNKNOWN'),
                'read_only': bool(read_only),
                'publications': pubs,
                'published_tables': pub_tables,
            }
        finally:
            client._forget_and_close(conn)

    journals = [
        _scan_journal_directory(jdir)
        for jdir in (host_scope.get('journal_directories') or ())
    ]
    return {
        'schema': 'scratchrobin.firebird.replication-status@1',
        'runtime_root': host_scope['firebird_runtime_root'],
        'automatic_failover_supported': False,
        'database': db_state,
        'journal_directories': journals,
        'replication_log': _read_replication_log_tail(host_scope['firebird_runtime_root']),
    }


def _check_admitted_journal_dir(raw_dir, host_scope, label):
    if not isinstance(raw_dir, str) or not raw_dir:
        raise ValueError(f'{label} is required')
    p = Path(raw_dir)
    if not p.is_absolute() or '..' in p.parts:
        raise ValueError(f'{label} must be a canonical absolute directory')
    allowed = [Path(d) for d in (host_scope.get('journal_directories') or ())]
    if not allowed:
        raise ValueError('No admitted journal_directories configured in host grant')
    parent_resolved = p.parent.resolve(strict=True) if p.parent.exists() else p.parent
    candidate = parent_resolved / p.name
    if not any(candidate == a or a in candidate.parents for a in allowed):
        raise ValueError(f'{label} is outside admitted journal_directories')
    return str(candidate)


def prepare_replication_review(host_scope, request, client=None, route=None):
    if not isinstance(request, Mapping):
        raise ValueError('Replication review request must be an object')
    op = request.get('operation')
    if op not in {'configure_primary', 'seed_replica', 'distribute_segments', 'promote_replica'}:
        raise ValueError('Unknown replication workflow operation')

    if op == 'configure_primary':
        db_path = request.get('primary_database_path') or (route or {}).get('database')
        if not isinstance(db_path, str) or not Path(db_path).is_absolute():
            raise ValueError('primary_database_path must be an absolute path')
        j_active = _check_admitted_journal_dir(request.get('journal_directory'), host_scope, 'journal_directory')
        j_arch = _check_admitted_journal_dir(request.get('journal_archive_directory'), host_scope, 'journal_archive_directory')
        timeout_s = request.get('journal_archive_timeout', 5)
        if type(timeout_s) is not int or not 0 <= timeout_s <= 86400:
            raise ValueError('journal_archive_timeout must be 0..86400')
        include_all = request.get('include_all_tables', True)
        enable_pub = request.get('enable_publication', True)
        if type(include_all) is not bool or type(enable_pub) is not bool:
            raise ValueError('include_all_tables and enable_publication must be boolean')
        repl_text = render_replication_conf({
            'databases': {
                db_path: {
                    'journal_directory': j_active,
                    'journal_archive_directory': j_arch,
                    'journal_archive_command': 'test ! -f $(archivepathname) && cp $(pathname) $(archivepathname)',
                    'journal_archive_timeout': timeout_s,
                    'log_errors': True,
                }
            }
        }, host_scope)
        return {
            'scope': host_scope,
            'operation': op,
            'primary_database_path': db_path,
            'journal_directory': j_active,
            'journal_archive_directory': j_arch,
            'replication_conf_text': repl_text,
            'include_all_tables': include_all,
            'enable_publication': enable_pub,
            'route_database': (route or {}).get('database'),
        }

    if op == 'seed_replica':
        pri_path = request.get('primary_database_path') or (route or {}).get('database')
        rep_path = request.get('replica_database_path', '')
        rep_rt = request.get('replica_runtime_root') or host_scope['firebird_runtime_root']
        j_source = _check_admitted_journal_dir(request.get('journal_source_directory'), host_scope, 'journal_source_directory')
        rep_mode = request.get('replica_mode', 'READ_ONLY')
        if rep_mode not in {'READ_ONLY', 'READ_WRITE'}:
            raise ValueError('replica_mode must be READ_ONLY or READ_WRITE')
        if not isinstance(pri_path, str) or not Path(pri_path).is_file():
            raise ValueError('primary_database_path must be an existing regular file')
        rep_file = Path(rep_path)
        if not rep_file.is_absolute() or '..' in rep_file.parts or rep_file.exists() or rep_file.is_symlink():
            raise ValueError('replica_database_path must be a non-existing canonical path')
        staging_root = host_scope.get('staging_directory')
        if staging_root:
            sroot = Path(staging_root).resolve(strict=True)
            rparent = rep_file.parent.resolve(strict=True)
            if rparent != sroot and sroot not in rparent.parents:
                raise ValueError('replica_database_path must reside inside the admitted staging/replica root')
        if request.get('confirmation') != rep_file.name:
            raise ValueError('Confirm the exact replica database filename')

        rep_rt_path = Path(rep_rt).resolve(strict=True)
        if not (rep_rt_path / 'bin/nbackup').is_file():
            raise ValueError('replica_runtime_root must provide Firebird 5.0.4 bin/nbackup')

        repl_text = render_replication_conf({
            'databases': {
                str(rep_file): {
                    'journal_source_directory': j_source,
                    'apply_idle_timeout': int(request.get('apply_idle_timeout', 1)),
                    'apply_error_timeout': int(request.get('apply_error_timeout', 5)),
                    'verbose_logging': True,
                }
            }
        }, {**host_scope, 'firebird_runtime_root': str(rep_rt_path)})
        return {
            'scope': host_scope,
            'operation': op,
            'primary_database_path': str(pri_path),
            'replica_database_path': str(rep_file),
            'replica_runtime_root': str(rep_rt_path),
            'journal_source_directory': j_source,
            'replica_mode': rep_mode,
            'replica_replication_conf_text': repl_text,
        }

    if op == 'distribute_segments':
        src_dir = _check_admitted_journal_dir(request.get('source_archive_directory'), host_scope, 'source_archive_directory')
        dst_dir = _check_admitted_journal_dir(request.get('target_source_directory'), host_scope, 'target_source_directory')
        if src_dir == dst_dir:
            raise ValueError('source_archive_directory and target_source_directory must be distinct')
        scan = _scan_journal_directory(src_dir)
        if not scan['segments']:
            raise ValueError('No archived journal segments found to distribute')
        # Check contiguous sequence order
        seqs = [s['sequence'] for s in scan['segments']]
        expected_contiguous = list(range(seqs[0], seqs[0] + len(seqs)))
        if seqs != expected_contiguous:
            raise ValueError(f'Journal segments have sequence gaps or duplicates: observed {seqs}')
        return {
            'scope': host_scope,
            'operation': op,
            'source_archive_directory': src_dir,
            'target_source_directory': dst_dir,
            'segments': scan['segments'],
        }

    # promote_replica
    rep_path = request.get('replica_database_path') or (route or {}).get('database')
    if not isinstance(rep_path, str) or not Path(rep_path).is_file():
        raise ValueError('replica_database_path must be an existing replica database file')
    if request.get('promotion_confirmed') is not True or request.get('confirmation') != Path(rep_path).name:
        raise ValueError('Confirm manual replica promotion with promotion_confirmed=true and exact filename')
    j_source = request.get('journal_source_directory')
    unapplied = 0
    if j_source:
        checked_src = _check_admitted_journal_dir(j_source, host_scope, 'journal_source_directory')
        unapplied = _scan_journal_directory(checked_src)['segment_count']
        if unapplied > 0 and request.get('discard_unapplied_segments_confirmed') is not True:
            raise ValueError(
                f'{unapplied} unapplied journal segment(s) remain in {checked_src}; '
                'wait for replica catch-up or set discard_unapplied_segments_confirmed=true'
            )
    return {
        'scope': host_scope,
        'operation': op,
        'replica_database_path': str(rep_path),
        'unapplied_segments_at_review': unapplied,
        'discard_unapplied_segments_confirmed': bool(request.get('discard_unapplied_segments_confirmed')),
        'journal_source_directory': j_source,
    }


def apply_replication_operation(record, client=None, route=None, replica_service_connect=None):
    import firebird.driver as native

    payload = record['payload']
    host_scope = payload['scope']
    verify_same_host(host_scope)
    op = payload['operation']

    if op == 'configure_primary':
        Path(payload['journal_directory']).mkdir(parents=True, exist_ok=True)
        Path(payload['journal_archive_directory']).mkdir(parents=True, exist_ok=True)
        rconf = Path(host_scope['firebird_runtime_root']) / 'replication.conf'
        tmp_c = rconf.with_suffix('.conf.tmp')
        tmp_c.write_text(payload['replication_conf_text'], encoding='utf-8')
        os.replace(tmp_c, rconf)

        if client is not None and route is not None:
            conn = client._connect({'route': route})
            try:
                if payload['include_all_tables']:
                    conn.execute_immediate('ALTER DATABASE INCLUDE ALL TO PUBLICATION')
                if payload['enable_publication']:
                    conn.execute_immediate('ALTER DATABASE ENABLE PUBLICATION')
                conn.commit()
            finally:
                client._forget_and_close(conn)

        return {
            'state': 'configured',
            'native_dispatched': True,
            'operation': op,
            'journal_directory': payload['journal_directory'],
            'journal_archive_directory': payload['journal_archive_directory'],
            'publication_enabled': payload['enable_publication'],
        }

    if op == 'seed_replica':
        rep_file = Path(payload['replica_database_path'])
        if rep_file.exists() or rep_file.is_symlink():
            return {'state': 'rejected', 'native_dispatched': False, 'reason': 'Replica target file already exists'}
        Path(payload['journal_source_directory']).mkdir(parents=True, exist_ok=True)
        if client is None or route is None:
            raise ValueError('Primary database connection is required for online backup-state seeding')

        conn = client._connect({'route': route})
        try:
            primary_guid = conn.info.get_info(native.DbInfoCode.DB_GUID)
            conn.execute_immediate('ALTER DATABASE BEGIN BACKUP')
            conn.commit()
            try:
                shutil.copy2(payload['primary_database_path'], rep_file)
                os.chmod(rep_file, 0o600)
            finally:
                conn.execute_immediate('ALTER DATABASE END BACKUP')
                conn.commit()
        finally:
            client._forget_and_close(conn)

        rep_rt = Path(payload['replica_runtime_root'])
        rep_lock = rep_rt / 'lock'
        rep_lock.mkdir(parents=True, exist_ok=True)
        env = {
            k: v for k, v in os.environ.items()
            if k not in {'ISC_PASSWORD', 'ISC_USER', 'ISC_DATABASE', 'ISC_ROLE'}
        }
        env.update(FIREBIRD=str(rep_rt), FIREBIRD_LOCK=str(rep_lock), LD_LIBRARY_PATH=str(rep_rt / 'lib'))
        fix_proc = subprocess.run(
            [str(rep_rt / 'bin/nbackup'), '-F', str(rep_file), '-SEQ'],
            env=env, capture_output=True, text=True, timeout=30, check=False,
        )
        if fix_proc.returncode != 0:
            raise RuntimeError('Replica nbackup -F -SEQ failed: ' + (fix_proc.stderr or fix_proc.stdout))

        rconf = rep_rt / 'replication.conf'
        if rconf.is_symlink():
            rconf.unlink()
        tmp_rc = rconf.with_suffix('.conf.tmp')
        tmp_rc.write_text(payload['replica_replication_conf_text'], encoding='utf-8')
        os.replace(tmp_rc, rconf)

        mode_enum = (
            native.ReplicaMode.READ_ONLY
            if payload['replica_mode'] == 'READ_ONLY'
            else native.ReplicaMode.READ_WRITE
        )
        if replica_service_connect is not None:
            srv = replica_service_connect()
            try:
                srv.database.set_replica_mode(database=str(rep_file), mode=mode_enum)
            finally:
                srv.close()
        else:
            # Local Engine13 service fallback when replica runs on local runtime
            mode_flag = 'read_only' if payload['replica_mode'] == 'READ_ONLY' else 'read_write'
            gfix_proc = subprocess.run(
                [str(rep_rt / 'bin/gfix'), '-user', 'SYSDBA', '-replica', mode_flag, str(rep_file)],
                env=env, capture_output=True, text=True, timeout=30, check=False,
            )
            if gfix_proc.returncode != 0:
                raise RuntimeError('Replica gfix -replica failed: ' + (gfix_proc.stderr or gfix_proc.stdout))

        return {
            'state': 'seeded',
            'native_dispatched': True,
            'operation': op,
            'primary_guid_preserved': primary_guid,
            'replica_database_path': str(rep_file),
            'replica_mode': payload['replica_mode'],
            'journal_source_directory': payload['journal_source_directory'],
        }

    if op == 'distribute_segments':
        src_root = Path(payload['source_archive_directory'])
        dst_root = Path(payload['target_source_directory'])
        shipped = []
        for seg in payload['segments']:
            src_seg = src_root / seg['relative_path']
            dst_seg = dst_root / seg['relative_path']
            if not src_seg.is_file() or file_sha256(src_seg) != seg['sha256']:
                return {
                    'state': 'rejected',
                    'native_dispatched': bool(shipped),
                    'shipped_segments': shipped,
                    'reason': f"Source segment {seg['relative_path']} changed or disappeared before copy",
                }
            if dst_seg.exists():
                return {
                    'state': 'rejected',
                    'native_dispatched': bool(shipped),
                    'shipped_segments': shipped,
                    'reason': f"Duplicate segment refused at destination: {seg['relative_path']}",
                }
            dst_seg.parent.mkdir(parents=True, exist_ok=True)
            tmp_seg = dst_seg.with_suffix('.shipping.tmp')
            tmp_seg.write_bytes(src_seg.read_bytes())
            os.chmod(tmp_seg, 0o600)
            os.replace(tmp_seg, dst_seg)
            shipped.append(seg['relative_path'])
        return {
            'state': 'distributed',
            'native_dispatched': True,
            'operation': op,
            'shipped_count': len(shipped),
            'shipped_segments': shipped,
        }

    # promote_replica
    if payload.get('journal_source_directory') and not payload.get('discard_unapplied_segments_confirmed'):
        remaining = _scan_journal_directory(payload['journal_source_directory'])['segment_count']
        if remaining > 0:
            return {
                'state': 'rejected',
                'native_dispatched': False,
                'reason': f'{remaining} unapplied journal segment(s) arrived since review; promotion refused',
            }

    rep_path = payload['replica_database_path']
    if replica_service_connect is not None:
        srv = replica_service_connect()
        try:
            srv.database.set_replica_mode(database=rep_path, mode=native.ReplicaMode.NONE)
            srv.database.set_access_mode(database=rep_path, mode=native.DbAccessMode.READ_WRITE)
        finally:
            srv.close()
    elif client is not None and route is not None:
        srv = client._connect_server({'route': route})
        try:
            srv.database.set_replica_mode(database=rep_path, mode=native.ReplicaMode.NONE)
            srv.database.set_access_mode(database=rep_path, mode=native.DbAccessMode.READ_WRITE)
        finally:
            client._release_server(srv)
    else:
        rt = Path(host_scope['firebird_runtime_root'])
        env = {k: v for k, v in os.environ.items() if k not in {'ISC_PASSWORD', 'ISC_USER', 'ISC_DATABASE', 'ISC_ROLE'}}
        env.update(FIREBIRD=str(rt), FIREBIRD_LOCK=str(host_scope['firebird_lock_directory']), LD_LIBRARY_PATH=str(rt / 'lib'))
        subprocess.run([str(rt / 'bin/gfix'), '-user', 'SYSDBA', '-replica', 'none', rep_path], env=env, check=True, timeout=30)
        subprocess.run([str(rt / 'bin/gfix'), '-user', 'SYSDBA', '-mode', 'read_write', rep_path], env=env, check=True, timeout=30)

    return {
        'state': 'promoted',
        'native_dispatched': True,
        'operation': op,
        'promoted_database_path': rep_path,
        'replica_mode': 'NONE',
        'access_mode': 'READ_WRITE',
        'automatic_failover_used': False,
    }

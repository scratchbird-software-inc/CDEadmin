"""Extended PostgreSQL 18 native host utilities (Batch 2):
- host_initdb (PG-AUDIT-UTILITY-INITDB)
- host_pg_amcheck (PG-AUDIT-UTILITY-PG_AMCHECK)
- host_pg_createsubscriber (PG-AUDIT-UTILITY-PG_CREATESUBSCRIBER)
- host_pg_resetwal (PG-AUDIT-UTILITY-PG_RESETWAL)
- host_pg_rewind (PG-AUDIT-UTILITY-PG_REWIND)
- host_pg_archivecleanup (PG-AUDIT-UTILITY-PGARCHIVECLEANUP)
- host_pgbench (PG-AUDIT-UTILITY-PGBENCH)
- host_pg_upgrade (PG-AUDIT-UTILITY-PGUPGRADE)
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import socket
import stat

from .continuity import ContinuityError

EXTENDED_OPERATIONS = {
    'host_initdb': 'initdb',
    'host_pg_amcheck': 'pg_amcheck',
    'host_pg_createsubscriber': 'pg_createsubscriber',
    'host_pg_resetwal': 'pg_resetwal',
    'host_pg_rewind': 'pg_rewind',
    'host_pg_archivecleanup': 'pg_archivecleanup',
    'host_pgbench': 'pgbench',
    'host_pg_upgrade': 'pg_upgrade',
}

_IDENT_RE = re.compile(r'[A-Za-z0-9_.-]{1,64}')
_SUBDIR_RE = re.compile(r'[A-Za-z0-9_-]{1,64}')
_WAL_FILE_RE = re.compile(r'[0-9A-Fa-f]{24}(?:\.[0-9A-Fa-f]{8}\.backup)?')
_PGBENCH_DB_RE = re.compile(r'cdeadmin_pgbench_[a-z0-9_]{1,45}')
_XID_RE = re.compile(r'[1-9][0-9]{0,9}')


def _bool(draft: dict, key: str, default: bool = False) -> bool:
    val = draft.setdefault(key, default)
    if type(val) is not bool:
        raise ContinuityError(f'Native utility option {key} requires a Boolean choice')
    return val


def _int_range(draft: dict, key: str, lo: int, hi: int, default: int | None = None) -> int | None:
    if default is not None:
        val = draft.setdefault(key, default)
    else:
        val = draft.get(key)
        if val in (None, ''):
            return None
    if type(val) is not int or not lo <= val <= hi:
        raise ContinuityError(f'Native utility option {key} must be an integer from {lo} through {hi}')
    return val


def _str_opt(draft: dict, key: str, default: str = '', pattern: re.Pattern | None = None) -> str:
    val = draft.setdefault(key, default)
    if not isinstance(val, str) or '\x00' in val:
        raise ContinuityError(f'Native utility option {key} must be text')
    val = val.strip()
    draft[key] = val
    if val and pattern is not None and not pattern.fullmatch(val):
        raise ContinuityError(f'Native utility option {key} has an invalid format')
    return val


def validate_extended_options(operation: str, draft: dict) -> dict:
    result = deepcopy(draft)
    timeout = result.setdefault('timeout_seconds', 120)
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise ContinuityError('Select a bounded native utility timeout of 1 through 3600 seconds')

    if operation == 'host_initdb':
        allowed = {
            'init_root_id', 'subdir', 'encoding', 'locale_provider', 'locale', 'icu_locale',
            'builtin_locale', 'data_checksums', 'wal_segsize_mb', 'username', 'auth_host',
            'auth_local', 'confirmation', 'timeout_seconds',
        }
        if set(result) - allowed:
            raise ContinuityError('Native initdb draft contains unrelated fields')
        root_id = _str_opt(result, 'init_root_id', pattern=_IDENT_RE)
        subdir = _str_opt(result, 'subdir', pattern=_SUBDIR_RE)
        if not root_id or not subdir:
            raise ContinuityError('Select an operator-granted init_root_id and new cluster subdir')
        enc = _str_opt(result, 'encoding', 'UTF8', re.compile(r'[A-Za-z0-9_]{2,32}')).upper()
        result['encoding'] = enc
        prov = _str_opt(result, 'locale_provider', 'libc')
        if prov not in {'libc', 'icu', 'builtin'}:
            raise ContinuityError('locale_provider must be libc, icu or builtin')
        _str_opt(result, 'locale', 'C', re.compile(r'[A-Za-z0-9_.@-]{1,64}'))
        _str_opt(result, 'icu_locale', '', re.compile(r'[A-Za-z0-9_.@-]{1,64}'))
        _str_opt(result, 'builtin_locale', '', re.compile(r'[A-Za-z0-9_.@-]{1,64}'))
        _bool(result, 'data_checksums', True)
        seg = _int_range(result, 'wal_segsize_mb', 1, 1024, 16)
        if seg & (seg - 1) != 0:
            raise ContinuityError('wal_segsize_mb must be a power of two from 1 through 1024')
        _str_opt(result, 'username', 'postgres', _IDENT_RE)
        ah = _str_opt(result, 'auth_host', 'scram-sha-256')
        al = _str_opt(result, 'auth_local', 'peer')
        if ah not in {'scram-sha-256', 'md5', 'reject', 'trust'} or al not in {'peer', 'scram-sha-256', 'reject', 'trust'}:
            raise ContinuityError('Select an admitted initdb authentication method')
        if result.get('confirmation') != f'{root_id}/{subdir}':
            raise ContinuityError('Confirm init_root_id/subdir before initializing a new cluster')
        return result

    if operation == 'host_pg_amcheck':
        allowed = {
            'host', 'port', 'username', 'database', 'all_databases', 'schema_pattern',
            'table_pattern', 'index_pattern', 'heapallindexed', 'parent_check',
            'rootdescend', 'no_dependent_indexes', 'no_dependent_toast', 'jobs',
            'confirmation', 'timeout_seconds',
        }
        if set(result) - allowed:
            raise ContinuityError('Native pg_amcheck draft contains unrelated fields')
        host = _str_opt(result, 'host', '127.0.0.1', re.compile(r'[A-Za-z0-9_.:-]{1,255}'))
        if host not in {'127.0.0.1', 'localhost', '::1'}:
            raise ContinuityError('Host pg_amcheck targets loopback PostgreSQL endpoints on the application host')
        _int_range(result, 'port', 1, 65535, 5432)
        _str_opt(result, 'username', 'postgres', _IDENT_RE)
        all_dbs = _bool(result, 'all_databases', False)
        db = _str_opt(result, 'database', '' if all_dbs else 'postgres', _IDENT_RE)
        if not all_dbs and not db:
            raise ContinuityError('Select a target database or enable all_databases')
        for pat in ('schema_pattern', 'table_pattern', 'index_pattern'):
            _str_opt(result, pat, '', re.compile(r'[A-Za-z0-9_.*?|-]{1,128}'))
        for flag in ('heapallindexed', 'parent_check', 'rootdescend', 'no_dependent_indexes', 'no_dependent_toast'):
            _bool(result, flag, False)
        _int_range(result, 'jobs', 1, 64, 1)
        expected_conf = 'ALL' if all_dbs else db
        if result.get('confirmation') != expected_conf:
            raise ContinuityError(f'Confirm {expected_conf!r} before running pg_amcheck')
        return result

    if operation == 'host_pg_createsubscriber':
        allowed = {
            'cluster_id', 'publisher_host', 'publisher_port', 'publisher_user',
            'databases', 'dry_run', 'subscriber_port', 'subscriber_username',
            'recovery_timeout', 'enable_two_phase', 'publication_name',
            'subscription_name', 'replication_slot_name',
            'offline_quiescence_confirmed', 'confirmation', 'timeout_seconds',
        }
        if set(result) - allowed:
            raise ContinuityError('Native pg_createsubscriber draft contains unrelated fields')
        cid = _str_opt(result, 'cluster_id', pattern=_IDENT_RE)
        if not cid:
            raise ContinuityError('Select an operator-granted standby cluster_id')
        _str_opt(result, 'publisher_host', '127.0.0.1', re.compile(r'[A-Za-z0-9_.:-]{1,255}'))
        _int_range(result, 'publisher_port', 1, 65535, 5432)
        _str_opt(result, 'publisher_user', 'postgres', _IDENT_RE)
        dbs = result.get('databases')
        if isinstance(dbs, str):
            dbs = [d.strip() for d in dbs.split(',') if d.strip()]
            result['databases'] = dbs
        if not isinstance(dbs, list) or not 1 <= len(dbs) <= 32 or any(not isinstance(d, str) or not _IDENT_RE.fullmatch(d) for d in dbs):
            raise ContinuityError('Select 1 through 32 database names for pg_createsubscriber')
        _bool(result, 'dry_run', True)
        _int_range(result, 'subscriber_port', 1024, 65535, 50432)
        _str_opt(result, 'subscriber_username', 'postgres', _IDENT_RE)
        _int_range(result, 'recovery_timeout', 5, 600, 60)
        _bool(result, 'enable_two_phase', False)
        for opt_k in ('publication_name', 'subscription_name', 'replication_slot_name'):
            val = _str_opt(result, opt_k, '', _IDENT_RE)
            if val and len(dbs) != 1:
                raise ContinuityError(f'{opt_k} applies when converting a single database')
        if not _bool(result, 'offline_quiescence_confirmed', False):
            raise ContinuityError('Confirm stopped standby quiescence before pg_createsubscriber')
        if result.get('confirmation') != cid:
            raise ContinuityError('Confirm the exact standby cluster_id')
        return result

    if operation == 'host_pg_resetwal':
        allowed = {
            'cluster_id', 'dry_run', 'force', 'next_xid', 'next_oid',
            'next_multixact_ids', 'next_wal_file', 'wal_segsize_mb',
            'offline_quiescence_confirmed', 'destructive_reset_confirmed',
            'confirmation', 'timeout_seconds',
        }
        if set(result) - allowed:
            raise ContinuityError('Native pg_resetwal draft contains unrelated fields')
        cid = _str_opt(result, 'cluster_id', pattern=_IDENT_RE)
        dry_run = _bool(result, 'dry_run', True)
        _bool(result, 'force', False)
        _str_opt(result, 'next_xid', '', _XID_RE)
        _str_opt(result, 'next_oid', '', _XID_RE)
        _str_opt(result, 'next_multixact_ids', '', re.compile(r'[1-9][0-9]{0,9},[1-9][0-9]{0,9}'))
        _str_opt(result, 'next_wal_file', '', re.compile(r'[0-9A-Fa-f]{24}'))
        seg = _int_range(result, 'wal_segsize_mb', 1, 1024)
        if seg is not None and (seg & (seg - 1) != 0):
            raise ContinuityError('wal_segsize_mb must be a power of two')
        if not _bool(result, 'offline_quiescence_confirmed', False):
            raise ContinuityError('Confirm stopped cluster quiescence before pg_resetwal')
        dest_ok = _bool(result, 'destructive_reset_confirmed', False)
        if not dry_run and not dest_ok:
            raise ContinuityError('Confirm destructive_reset_confirmed before non-dry-run pg_resetwal')
        if not cid or result.get('confirmation') != cid:
            raise ContinuityError('Confirm the exact cluster_id for pg_resetwal')
        return result

    if operation == 'host_pg_rewind':
        allowed = {
            'cluster_id', 'source_mode', 'source_cluster_id', 'source_host', 'source_port',
            'source_user', 'source_dbname', 'dry_run', 'restore_target_wal',
            'write_recovery_conf', 'no_sync', 'offline_quiescence_confirmed',
            'confirmation', 'timeout_seconds',
        }
        if set(result) - allowed:
            raise ContinuityError('Native pg_rewind draft contains unrelated fields')
        cid = _str_opt(result, 'cluster_id', pattern=_IDENT_RE)
        smode = _str_opt(result, 'source_mode', 'cluster')
        if smode not in {'cluster', 'server'}:
            raise ContinuityError('source_mode must be cluster or server')
        if smode == 'cluster':
            scid = _str_opt(result, 'source_cluster_id', pattern=_IDENT_RE)
            if not scid or scid == cid:
                raise ContinuityError('Select a distinct operator-granted source_cluster_id')
            if _bool(result, 'write_recovery_conf', False):
                raise ContinuityError('--write-recovery-conf requires source_mode=server')
        else:
            _str_opt(result, 'source_host', '127.0.0.1', re.compile(r'[A-Za-z0-9_.:-]{1,255}'))
            _int_range(result, 'source_port', 1, 65535, 5432)
            _str_opt(result, 'source_user', 'postgres', _IDENT_RE)
            _str_opt(result, 'source_dbname', 'postgres', _IDENT_RE)
            _bool(result, 'write_recovery_conf', False)
        _bool(result, 'dry_run', True)
        _bool(result, 'restore_target_wal', False)
        _bool(result, 'no_sync', False)
        if not _bool(result, 'offline_quiescence_confirmed', False):
            raise ContinuityError('Confirm stopped target cluster quiescence before pg_rewind')
        if not cid or result.get('confirmation') != cid:
            raise ContinuityError('Confirm the exact target cluster_id for pg_rewind')
        return result

    if operation == 'host_pg_archivecleanup':
        allowed = {
            'archive_id', 'oldest_kept_wal_file', 'dry_run', 'debug',
            'clean_backup_history', 'strip_extension', 'confirmation', 'timeout_seconds',
        }
        if set(result) - allowed:
            raise ContinuityError('Native pg_archivecleanup draft contains unrelated fields')
        aid = _str_opt(result, 'archive_id', pattern=_IDENT_RE)
        oldest = _str_opt(result, 'oldest_kept_wal_file', pattern=_WAL_FILE_RE)
        if not aid or not oldest:
            raise ContinuityError('Select an operator-granted archive_id and oldest_kept_wal_file')
        _bool(result, 'dry_run', True)
        _bool(result, 'debug', False)
        _bool(result, 'clean_backup_history', False)
        _str_opt(result, 'strip_extension', '', re.compile(r'\.[A-Za-z0-9]{1,16}'))
        if result.get('confirmation') != aid:
            raise ContinuityError('Confirm the exact archive_id before WAL archive cleanup')
        return result

    if operation == 'host_pgbench':
        allowed = {
            'mode', 'host', 'port', 'username', 'database', 'scale', 'clients', 'jobs',
            'transactions', 'time_seconds', 'builtin_script', 'protocol', 'no_vacuum',
            'confirmation', 'timeout_seconds',
        }
        if set(result) - allowed:
            raise ContinuityError('Native pgbench draft contains unrelated fields')
        mode = _str_opt(result, 'mode', 'RUN').upper()
        result['mode'] = mode
        if mode not in {'INIT', 'RUN'}:
            raise ContinuityError('pgbench mode must be INIT or RUN')
        host = _str_opt(result, 'host', '127.0.0.1', re.compile(r'[A-Za-z0-9_.:-]{1,255}'))
        if host not in {'127.0.0.1', 'localhost', '::1'}:
            raise ContinuityError('Managed pgbench targets loopback dedicated benchmark databases')
        _int_range(result, 'port', 1, 65535, 5432)
        _str_opt(result, 'username', 'postgres', _IDENT_RE)
        db = _str_opt(result, 'database')
        if not db or not _PGBENCH_DB_RE.fullmatch(db):
            raise ContinuityError('pgbench requires a dedicated cdeadmin_pgbench_* database name')
        _int_range(result, 'scale', 1, 100, 1)
        _int_range(result, 'clients', 1, 64, 2)
        _int_range(result, 'jobs', 1, 16, 1)
        tx = _int_range(result, 'transactions', 1, 100000)
        dur = _int_range(result, 'time_seconds', 1, 600)
        if mode == 'RUN':
            if tx is not None and dur is not None:
                raise ContinuityError('Specify either transactions or time_seconds for pgbench, not both')
            if tx is None and dur is None:
                result['transactions'] = 10
        script = _str_opt(result, 'builtin_script', 'tpcb-like')
        if script not in {'tpcb-like', 'simple-update', 'select-only'}:
            raise ContinuityError('builtin_script must be tpcb-like, simple-update or select-only')
        proto = _str_opt(result, 'protocol', 'simple')
        if proto not in {'simple', 'extended', 'prepared'}:
            raise ContinuityError('protocol must be simple, extended or prepared')
        _bool(result, 'no_vacuum', False)
        if result.get('confirmation') != db:
            raise ContinuityError('Confirm the dedicated cdeadmin_pgbench_* database name')
        return result

    if operation == 'host_pg_upgrade':
        allowed = {
            'pair_id', 'check_only', 'transfer_mode', 'jobs', 'retain', 'no_sync',
            'username', 'offline_quiescence_confirmed', 'upgrade_mutation_confirmed',
            'confirmation', 'timeout_seconds',
        }
        if set(result) - allowed:
            raise ContinuityError('Native pg_upgrade draft contains unrelated fields')
        pid = _str_opt(result, 'pair_id', pattern=_IDENT_RE)
        check_only = _bool(result, 'check_only', True)
        tmode = _str_opt(result, 'transfer_mode', 'copy')
        if tmode not in {'copy', 'clone', 'link', 'swap'}:
            raise ContinuityError('transfer_mode must be copy, clone, link or swap')
        _int_range(result, 'jobs', 1, 64, 1)
        _bool(result, 'retain', False)
        _bool(result, 'no_sync', False)
        _str_opt(result, 'username', '', _IDENT_RE)
        if not _bool(result, 'offline_quiescence_confirmed', False):
            raise ContinuityError('Confirm both old and new clusters are shut down before pg_upgrade')
        mut_ok = _bool(result, 'upgrade_mutation_confirmed', False)
        if not check_only and not mut_ok:
            raise ContinuityError('Confirm upgrade_mutation_confirmed before running live pg_upgrade')
        if not pid or result.get('confirmation') != pid:
            raise ContinuityError('Confirm the exact upgrade pair_id')
        return result

    raise ContinuityError(f'Unsupported extended PostgreSQL utility: {operation}')


def observe_extended(host_tools, operation: str, selected: dict, grant: dict, workspace, exact_path, identity_fn, parse_control) -> dict:
    if operation == 'host_initdb':
        entry = next((r for r in grant.get('init_roots', []) if r['id'] == selected['init_root_id']), None)
        if entry is None:
            raise ContinuityError('Selected init_root_id is not granted to this endpoint')
        root = exact_path(entry['path'], True)
        target = root / selected['subdir']
        if target.exists() or target.is_symlink():
            if target.is_symlink() or not target.is_dir() or any(target.iterdir()):
                raise ContinuityError('Target initdb directory already exists and is non-empty or a symlink')
        return {
            'hostname': socket.gethostname(),
            'init_root_id': entry['id'],
            'init_root': str(root),
            'init_root_identity': identity_fn(root),
            'target_pgdata': str(target),
        }

    if operation in {'host_pg_amcheck', 'host_pgbench'}:
        return {
            'hostname': socket.gethostname(),
            'target_host': selected['host'],
            'target_port': selected['port'],
            'target_database': 'ALL' if selected.get('all_databases') else selected.get('database'),
            'sql_session_borrowed': False,
        }

    if operation == 'host_pg_archivecleanup':
        entry = next((r for r in grant.get('archive_dirs', []) if r['id'] == selected['archive_id']), None)
        if entry is None:
            raise ContinuityError('Selected archive_id is not granted to this endpoint')
        arch = exact_path(entry['path'], True)
        holds_file = arch / '.scratchrobin-archive-holds.json'
        if holds_file.is_file():
            try:
                holds = json.loads(holds_file.read_text(encoding='utf-8')).get('protected_wal_files', [])
            except Exception as exc:
                raise ContinuityError('Archive hold manifest could not be parsed safely') from exc
            oldest_base = selected['oldest_kept_wal_file'][:24].upper()
            for held in holds:
                if isinstance(held, str) and len(held) >= 24 and held[:24].upper() < oldest_base:
                    raise ContinuityError(
                        f'WAL segment {held} is protected by an active recovery/consumer hold and precedes {selected["oldest_kept_wal_file"]}'
                    )
        wal_files = sorted(
            p.name for p in arch.iterdir()
            if p.is_file() and not p.is_symlink() and len(p.name) >= 24
        )
        return {
            'archive_id': entry['id'],
            'archive_path': str(arch),
            'archive_identity': identity_fn(arch),
            'wal_count_before': len(wal_files),
        }

    if operation == 'host_pg_upgrade':
        pair = next((r for r in grant.get('upgrade_pairs', []) if r['id'] == selected['pair_id']), None)
        if pair is None:
            raise ContinuityError('Selected upgrade pair_id is not granted to this endpoint')
        old_bin = exact_path(pair['old_bindir'], True)
        new_bin = exact_path(pair['new_bindir'], True)
        old_data = exact_path(pair['old_datadir'], True)
        new_data = exact_path(pair['new_datadir'], True)
        if old_data == new_data:
            raise ContinuityError('old_datadir and new_datadir must be distinct clusters')
        for label, ddir in (('old_datadir', old_data), ('new_datadir', new_data)):
            if (ddir / 'postmaster.pid').exists() or (ddir / 'postmaster.pid').is_symlink():
                raise ContinuityError(f'pg_upgrade requires stopped cluster ({label} has postmaster.pid)')
            if not (ddir / 'PG_VERSION').is_file():
                raise ContinuityError(f'{label} is missing PG_VERSION')
        old_ver = int((old_data / 'PG_VERSION').read_text().strip())
        new_ver = int((new_data / 'PG_VERSION').read_text().strip())
        if new_ver != 18 or old_ver > new_ver or old_ver < 15:
            raise ContinuityError('Supported pg_upgrade pairs require old major 15..18 and target major 18')
        obs_new = host_tools.invoke('pg_controldata', workspace, [str(new_data)], 15)
        fields_new = parse_control(obs_new['stdout'])
        if obs_new['return_code'] or fields_new.get('Database cluster state') not in {'shut down', 'shut down in recovery'}:
            raise ContinuityError('New target cluster must be cleanly shut down before pg_upgrade')
        return {
            'pair_id': pair['id'],
            'old_bindir': str(old_bin),
            'new_bindir': str(new_bin),
            'old_datadir': str(old_data),
            'new_datadir': str(new_data),
            'old_pg_version': str(old_ver),
            'new_pg_version': str(new_ver),
            'new_control_before': fields_new,
        }

    # Stopped PG 18 cluster operations: host_pg_createsubscriber, host_pg_resetwal, host_pg_rewind
    cluster = next((r for r in grant.get('clusters', []) if r['id'] == selected['cluster_id']), None)
    if cluster is None:
        raise ContinuityError('Selected cluster is not granted to this endpoint')
    path = exact_path(cluster['path'], True)
    if (path / 'postmaster.pid').exists() or (path / 'postmaster.pid').is_symlink():
        raise ContinuityError(f'{operation} requires an absent postmaster.pid and a stopped cluster')
    ver = exact_path(str(path / 'PG_VERSION')).read_text().strip()
    if ver != '18':
        raise ContinuityError('Granted cluster and native utility major versions differ')
    obs = host_tools.invoke('pg_controldata', workspace, [str(path)], 15)
    fields = parse_control(obs['stdout'])
    if obs['return_code'] or fields.get('Database cluster state') not in {'shut down', 'shut down in recovery'}:
        raise ContinuityError(f'{operation} requires a cleanly shut down cluster')
    source = {
        'cluster_id': selected['cluster_id'],
        'cluster_path': str(path),
        'directory_identity': identity_fn(path),
        'pg_version': ver,
        'control_fields_before': fields,
    }
    if operation == 'host_pg_rewind' and selected['source_mode'] == 'cluster':
        src_cluster = next((r for r in grant.get('clusters', []) if r['id'] == selected['source_cluster_id']), None)
        if src_cluster is None:
            raise ContinuityError('Selected source_cluster_id is not granted to this endpoint')
        src_path = exact_path(src_cluster['path'], True)
        source['source_cluster_path'] = str(src_path)
    return source


def execute_extended(host_tools, operation: str, selected: dict, source: dict, workspace, cancel, progress, before_dispatch, parse_control) -> dict:
    import shutil
    import tempfile

    extra_summary: dict = {}
    exec_cwd = workspace
    short_sock_dir: Path | None = None

    if operation == 'host_initdb':
        target_dir = source['target_pgdata']
        args = [
            f'--pgdata={target_dir}',
            f'--encoding={selected["encoding"]}',
            f'--locale-provider={selected["locale_provider"]}',
            f'--username={selected["username"]}',
            f'--auth-host={selected["auth_host"]}',
            f'--auth-local={selected["auth_local"]}',
            f'--wal-segsize={selected["wal_segsize_mb"]}',
            '--no-instructions',
        ]
        if selected['locale_provider'] == 'libc':
            args.append(f'--locale={selected["locale"]}')
        elif selected['locale_provider'] == 'icu':
            args.append(f'--locale={selected["locale"]}')
            if selected['icu_locale']:
                args.append(f'--icu-locale={selected["icu_locale"]}')
        else:
            args.append(f'--builtin-locale={selected["builtin_locale"] or "C"}')
        args.append('--data-checksums' if selected['data_checksums'] else '--no-data-checksums')

    elif operation == 'host_pg_amcheck':
        args = [
            f'--host={selected["host"]}',
            f'--port={selected["port"]}',
            f'--username={selected["username"]}',
            f'--jobs={selected["jobs"]}',
        ]
        if selected['all_databases']:
            args.append('--all')
        else:
            args.append(f'--database={selected["database"]}')
        if selected['schema_pattern']:
            args.append(f'--schema={selected["schema_pattern"]}')
        if selected['table_pattern']:
            args.append(f'--table={selected["table_pattern"]}')
        if selected['index_pattern']:
            args.append(f'--index={selected["index_pattern"]}')
        if selected['heapallindexed']:
            args.append('--heapallindexed')
        if selected['parent_check']:
            args.append('--parent-check')
        if selected['rootdescend']:
            args.append('--rootdescend')
        if selected['no_dependent_indexes']:
            args.append('--no-dependent-indexes')
        if selected['no_dependent_toast']:
            args.append('--no-dependent-toast')

    elif operation == 'host_pg_createsubscriber':
        short_sock_dir = Path(tempfile.mkdtemp(prefix='sr-pgcs-'))
        os.chmod(short_sock_dir, 0o700)
        pub_conn = f"host={selected['publisher_host']} port={selected['publisher_port']} user={selected['publisher_user']}"
        args = [
            f'--pgdata={source["cluster_path"]}',
            f'--publisher-server={pub_conn}',
            f'--subscriber-port={selected["subscriber_port"]}',
            f'--subscriber-username={selected["subscriber_username"]}',
            f'--socketdir={short_sock_dir}',
            f'--recovery-timeout={selected["recovery_timeout"]}',
        ]
        for db in selected['databases']:
            args.append(f'--database={db}')
        if selected['dry_run']:
            args.append('--dry-run')
        if selected['enable_two_phase']:
            args.append('--enable-two-phase')
        if selected['publication_name']:
            args.append(f'--publication={selected["publication_name"]}')
        if selected['subscription_name']:
            args.append(f'--subscription={selected["subscription_name"]}')
        if selected['replication_slot_name']:
            args.append(f'--replication-slot={selected["replication_slot_name"]}')

    elif operation == 'host_pg_resetwal':
        args = []
        if selected['dry_run']:
            args.append('--dry-run')
        if selected['force']:
            args.append('--force')
        if selected['next_xid']:
            args.append(f'--next-transaction-id={selected["next_xid"]}')
        if selected['next_oid']:
            args.append(f'--next-oid={selected["next_oid"]}')
        if selected['next_multixact_ids']:
            args.append(f'--multixact-ids={selected["next_multixact_ids"]}')
        if selected['next_wal_file']:
            args.append(f'--next-wal-file={selected["next_wal_file"]}')
        if selected.get('wal_segsize_mb'):
            args.append(f'--wal-segsize={selected["wal_segsize_mb"]}')
        args.append(f'--pgdata={source["cluster_path"]}')

    elif operation == 'host_pg_rewind':
        args = [f'--target-pgdata={source["cluster_path"]}']
        if selected['source_mode'] == 'cluster':
            args.append(f'--source-pgdata={source["source_cluster_path"]}')
        else:
            connstr = (
                f"host={selected['source_host']} port={selected['source_port']} "
                f"user={selected['source_user']} dbname={selected['source_dbname']}"
            )
            args.append(f'--source-server={connstr}')
            if selected['write_recovery_conf']:
                args.append('--write-recovery-conf')
        if selected['dry_run']:
            args.append('--dry-run')
        if selected['restore_target_wal']:
            args.append('--restore-target-wal')
        if selected['no_sync']:
            args.append('--no-sync')

    elif operation == 'host_pg_archivecleanup':
        args = []
        if selected['dry_run']:
            args.append('--dry-run')
        if selected['debug']:
            args.append('--debug')
        if selected['clean_backup_history']:
            args.append('--clean-backup-history')
        if selected['strip_extension']:
            args.append(f'--strip-extension={selected["strip_extension"]}')
        args.extend([source['archive_path'], selected['oldest_kept_wal_file']])

    elif operation == 'host_pgbench':
        args = [
            f'--host={selected["host"]}',
            f'--port={selected["port"]}',
            f'--username={selected["username"]}',
        ]
        if selected['mode'] == 'INIT':
            args.extend(['--initialize', f'--scale={selected["scale"]}'])
            if selected['no_vacuum']:
                args.append('--no-vacuum')
        else:
            args.extend([
                f'--client={selected["clients"]}',
                f'--jobs={selected["jobs"]}',
                f'--builtin={selected["builtin_script"]}',
                f'--protocol={selected["protocol"]}',
            ])
            if selected['no_vacuum']:
                args.append('--no-vacuum')
            if selected.get('time_seconds'):
                args.append(f'--time={selected["time_seconds"]}')
            else:
                args.append(f'--transactions={selected["transactions"]}')
        args.append(selected['database'])

    else:  # host_pg_upgrade
        work_sub = Path(workspace) / 'pg_upgrade_work'
        work_sub.mkdir(parents=True, exist_ok=True, mode=0o700)
        short_sock_dir = Path(tempfile.mkdtemp(prefix='sr-pgup-'))
        os.chmod(short_sock_dir, 0o700)
        exec_cwd = work_sub
        args = [
            f'--old-bindir={source["old_bindir"]}',
            f'--new-bindir={source["new_bindir"]}',
            f'--old-datadir={source["old_datadir"]}',
            f'--new-datadir={source["new_datadir"]}',
            f'--jobs={selected["jobs"]}',
            f'--socketdir={short_sock_dir}',
        ]
        if selected['check_only']:
            args.append('--check')
        else:
            tmode = selected['transfer_mode']
            args.append('--link' if tmode == 'link' else f'--{tmode}')
        if selected['retain']:
            args.append('--retain')
        if selected['no_sync']:
            args.append('--no-sync')
        if selected['username']:
            args.append(f'--username={selected["username"]}')

    if before_dispatch is not None:
        before_dispatch()

    try:
        result = host_tools.invoke(
            EXTENDED_OPERATIONS[operation],
            exec_cwd,
            args,
            selected['timeout_seconds'],
            cancel,
            progress,
            True,
        )
    finally:
        if short_sock_dir is not None:
            shutil.rmtree(short_sock_dir, ignore_errors=True)

    verification = result['return_code'] == 0
    if operation == 'host_initdb' and result['return_code'] == 0:
        rb = host_tools.invoke('pg_controldata', workspace, [source['target_pgdata']], 15)
        cfields = parse_control(rb['stdout'])
        verification = rb['return_code'] == 0 and cfields.get('Database cluster state') == 'shut down'
        extra_summary['initialized_control_fields'] = cfields

    elif operation == 'host_pg_amcheck':
        findings = [ln.strip() for ln in result['stdout'].splitlines() if ln.strip()]
        extra_summary['corruption_detected'] = result['return_code'] == 2
        extra_summary['corruption_findings'] = findings[:200]
        verification = result['return_code'] == 0

    elif operation in {'host_pg_createsubscriber', 'host_pg_resetwal', 'host_pg_rewind'} and result['return_code'] == 0:
        rb = host_tools.invoke('pg_controldata', workspace, [source['cluster_path']], 15)
        cfields = parse_control(rb['stdout'])
        extra_summary['control_fields_after'] = cfields
        verification = rb['return_code'] == 0
        if operation == 'host_pg_createsubscriber' and not selected['dry_run']:
            verification = verification and (
                cfields.get('Database system identifier') != source['control_fields_before'].get('Database system identifier')
            )

    elif operation == 'host_pg_archivecleanup' and result['return_code'] == 0:
        arch = Path(source['archive_path'])
        after_count = sum(1 for p in arch.iterdir() if p.is_file() and not p.is_symlink() and len(p.name) >= 24)
        extra_summary['wal_count_after'] = after_count
        extra_summary['candidate_or_removed_lines'] = [ln.strip() for ln in (result['stdout'] + '\n' + result['stderr']).splitlines() if ln.strip()][:200]

    elif operation == 'host_pgbench':
        out_text = result['stdout'] + '\n' + result['stderr']
        tps_match = re.search(r'tps\s*=\s*([0-9.]+)', out_text)
        lat_match = re.search(r'latency average\s*=\s*([0-9.]+)\s*ms', out_text)
        tx_match = re.search(r'number of transactions actually processed:\s*([0-9]+)', out_text)
        extra_summary['benchmark_metrics'] = {
            'mode': selected['mode'],
            'tps': float(tps_match.group(1)) if tps_match else None,
            'latency_avg_ms': float(lat_match.group(1)) if lat_match else None,
            'transactions_processed': int(tx_match.group(1)) if tx_match else None,
        }

    elif operation == 'host_pg_upgrade' and result['return_code'] == 0:
        rb = host_tools.invoke('pg_controldata', workspace, [source['new_datadir']], 15)
        extra_summary['new_control_after'] = parse_control(rb['stdout'])
        verification = rb['return_code'] == 0

    return {
        'verification_complete': verification,
        'native': result,
        'control_fields': None,
        'summary_input_count': 0,
        'summary_quiet_requested': False,
        'native_stdout_empty': not bool(result['stdout']),
        'sql_session_borrowed': False,
        'commit_requested': False,
        'rollback_requested': False,
        'native_success': result['return_code'] == 0,
        'report_complete': not result['stdout_truncated'] and not result['stderr_truncated'],
        'cluster_mutation_requested': operation in {'host_initdb', 'host_pg_createsubscriber', 'host_pg_resetwal', 'host_pg_rewind', 'host_pg_archivecleanup', 'host_pg_upgrade'} and not selected.get('dry_run', False) and not selected.get('check_only', False),
        'native_effect_rollback_available': False,
        'atomic_live_snapshot_claimed': False,
        **extra_summary,
    }

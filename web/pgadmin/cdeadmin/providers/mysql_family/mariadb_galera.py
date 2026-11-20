"""Native MariaDB wsrep / Galera cluster inspection & lifecycle management.

Implements MA-AUDIT-GALERA:
- Explicit `wsrep_provider` (`libgalera_smm.so`) runtime dependency verification
  (reports unavailable cleanly when absent; NEVER substitutes async replication or Group Replication!)
- Structured inspection of `wsrep_cluster_state_uuid`, `wsrep_cluster_size`,
  `wsrep_cluster_status` (`Primary` vs `Non-Primary`), `wsrep_local_state_comment`
  (`Synced`/`Donor/Desynced`/`Joining`/`Joined`), flow control, SST/IST & `grastate.dat`
- Safe-to-bootstrap `grastate.dat` enforcement (`safe_to_bootstrap == 1` check, peer `seqno` comparison,
  and atomic backed-up rewrite only on reviewed `force_safe_to_bootstrap=True`)
- Reviewed cluster bootstrap (`--wsrep-new-cluster` / `pc.bootstrap=YES`), node join,
  maintenance `wsrep_desync` toggle, node stop & IST/SST rejoin verification, and quorum recovery.
"""
from copy import deepcopy
import os
from pathlib import Path
import re
import time

from ...operations.fileio import durable_replace, private_file
from .mariadb_host_services import control_managed_service
from .mariadb_physical import (
    MariaDBPhysicalError,
    canonical_digest,
    execution_host_identity,
    file_sha256,
    mariadb_bool,
    rows,
    safe_absolute_path,
)


class MariaDBGaleraError(MariaDBPhysicalError):
    """Refusal or failure in native MariaDB wsrep / Galera cluster operations."""


SECRET_PROVIDER_OPTION_KEYS = frozenset({
    'socket.ssl_password', 'evs.debug_log_mask',
})


def parse_wsrep_provider_options(raw_options):
    """Parse semicolon-delimited `wsrep_provider_options` into structured dict."""
    result = {}
    if not isinstance(raw_options, str) or not raw_options.strip():
        return result
    for part in raw_options.split(';'):
        item = part.strip()
        if not item or '=' not in item:
            continue
        k, _, v = item.partition('=')
        key = k.strip()
        val = v.strip()
        if key.lower() in SECRET_PROVIDER_OPTION_KEYS or 'password' in key.lower():
            val = '<redacted>'
        result[key] = val
    return result


def inspect_provider_library(library_path):
    """Verify external Galera provider shared library (`libgalera_smm.so`) on disk."""
    if not library_path or str(library_path).strip().lower() == 'none':
        return {'available_on_host': False, 'reason': 'no_provider_path_configured'}
    p = Path(str(library_path))
    if not p.is_absolute():
        return {'available_on_host': False, 'path': str(p), 'reason': 'relative_provider_path'}
    if not p.exists():
        return {'available_on_host': False, 'path': str(p), 'reason': 'provider_library_missing'}
    resolved = p.resolve(strict=False)
    if not resolved.is_file():
        return {'available_on_host': False, 'path': str(p), 'reason': 'not_regular_file'}
    with resolved.open('rb') as stream:
        magic = stream.read(4)
    if magic != b'\x7fELF':
        return {'available_on_host': False, 'path': str(resolved), 'reason': 'not_elf_shared_library'}
    return {
        'available_on_host': True,
        'path': str(p),
        'resolved_path': str(resolved),
        'sha256': file_sha256(resolved),
        'bytes': resolved.stat().st_size,
    }


def inspect_grastate(datadir):
    """Read and parse `<datadir>/grastate.dat` and `gvwstate.dat`."""
    ddir = safe_absolute_path(str(datadir), 'Galera datadir')
    gra_path = ddir / 'grastate.dat'
    gvw_path = ddir / 'gvwstate.dat'
    if not gra_path.is_file():
        return {
            'exists': False,
            'datadir': str(ddir),
            'gvwstate_exists': gvw_path.is_file(),
            'safe_for_initial_bootstrap': not (ddir / 'galera.cache').exists(),
        }
    text = gra_path.read_text(encoding='utf-8', errors='replace')
    parsed = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if ':' in line:
            k, _, v = line.partition(':')
            parsed[k.strip()] = v.strip()
    seqno = int(parsed['seqno']) if re.fullmatch(r'-?[0-9]+', parsed.get('seqno', '')) else None
    safe = int(parsed['safe_to_bootstrap']) if parsed.get('safe_to_bootstrap') in {'0', '1'} else 0
    return {
        'exists': True,
        'path': str(gra_path),
        'sha256': file_sha256(gra_path),
        'version': parsed.get('version'),
        'uuid': parsed.get('uuid'),
        'seqno': seqno,
        'safe_to_bootstrap': safe == 1,
        'safe_to_bootstrap_raw': safe,
        'gvwstate_exists': gvw_path.is_file(),
    }


def validate_and_prepare_grastate_bootstrap(
    datadir, *, allow_initial=True, force_safe_to_bootstrap=False,
    peer_seqnos=(), backup_dir=None,
):
    """Enforce `grastate.dat` `safe_to_bootstrap == 1` before `--wsrep-new-cluster`!"""
    gra = inspect_grastate(datadir)
    if not gra['exists']:
        if not allow_initial:
            raise MariaDBGaleraError(
                'grastate.dat is absent and allow_initial is False; refusing unverified cluster bootstrap'
            )
        return {
            'bootstrap_admitted': True,
            'mode': 'initial_cluster_no_grastate',
            'grastate_before': gra,
            'grastate_modified': False,
        }

    local_seqno = gra['seqno'] if gra['seqno'] is not None else -1
    higher_peers = [p for p in peer_seqnos if p is not None and int(p) > local_seqno]
    if higher_peers:
        raise MariaDBGaleraError(
            f'Refusing Galera bootstrap on stale node (seqno={local_seqno} < peer seqno={max(higher_peers)})'
        )

    if gra['safe_to_bootstrap']:
        return {
            'bootstrap_admitted': True,
            'mode': 'native_safe_to_bootstrap',
            'grastate_before': gra,
            'grastate_modified': False,
        }

    if not force_safe_to_bootstrap:
        raise MariaDBGaleraError(
            f"Refusing Galera bootstrap: grastate.dat has safe_to_bootstrap=0 (uuid={gra['uuid']}, seqno={gra['seqno']}). "
            'Inspect all cluster members to find safe_to_bootstrap=1 or explicitly review force_safe_to_bootstrap=True on the highest-seqno survivor.'
        )

    # Atomically back up grastate.dat and promote safe_to_bootstrap: 1
    gra_path = Path(gra['path'])
    original_text = gra_path.read_text(encoding='utf-8')
    backup_target = (
        Path(backup_dir) / 'grastate.dat.backup'
        if backup_dir else gra_path.with_name('grastate.dat.sr-backup')
    )
    backup_target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with backup_target.open('w', encoding='utf-8') as bf:
        private_file(backup_target)
        bf.write(original_text)
        bf.flush()
        os.fsync(bf.fileno())

    updated_text = re.sub(
        r'(?m)^(\s*safe_to_bootstrap\s*:\s*)0\s*$',
        r'\g<1>1',
        original_text,
    )
    if 'safe_to_bootstrap: 1' not in updated_text and 'safe_to_bootstrap:1' not in updated_text.replace(' ', ''):
        raise MariaDBGaleraError('Failed to rewrite safe_to_bootstrap: 1 in grastate.dat')

    tmp_path = gra_path.with_name(f'.grastate.dat.sr-{os.getpid()}.tmp')
    st = gra_path.stat()
    with tmp_path.open('w', encoding='utf-8') as tf:
        tf.write(updated_text)
        tf.flush()
        os.fsync(tf.fileno())
        if os.geteuid() == 0:
            os.fchown(tf.fileno(), st.st_uid, st.st_gid)
        os.fchmod(tf.fileno(), st.st_mode & 0o777)
    durable_replace(tmp_path, gra_path)

    after_gra = inspect_grastate(datadir)
    if not after_gra['safe_to_bootstrap']:
        raise MariaDBGaleraError('Post-write verification of safe_to_bootstrap=1 in grastate.dat failed')
    return {
        'bootstrap_admitted': True,
        'mode': 'forced_safe_to_bootstrap_on_highest_seqno',
        'grastate_before': gra,
        'grastate_after': after_gra,
        'grastate_modified': True,
        'backup_path': str(backup_target),
    }


def inspect_galera_node(conn, *, host_datadir=None, host_provider_path=None):
    """Inspect MariaDB wsrep/Galera variables, status, flow control, SST/IST & provider availability."""
    conn.autocommit = True
    sysvars = rows(
        conn,
        'SELECT VERSION() AS version, @@server_uid AS server_uid, @@server_id AS server_id, '
        '@@hostname AS hostname, @@port AS port, @@datadir AS datadir, @@read_only AS read_only, '
        '@@global.wsrep_on AS wsrep_on, @@global.wsrep_provider AS wsrep_provider, '
        '@@global.wsrep_cluster_name AS wsrep_cluster_name, '
        '@@global.wsrep_cluster_address AS wsrep_cluster_address, '
        '@@global.wsrep_node_name AS wsrep_node_name, '
        '@@global.wsrep_node_address AS wsrep_node_address, '
        '@@global.wsrep_node_incoming_address AS wsrep_node_incoming_address, '
        '@@global.wsrep_sst_method AS wsrep_sst_method, '
        '@@global.wsrep_sst_receive_address AS wsrep_sst_receive_address, '
        '@@global.wsrep_sst_donor AS wsrep_sst_donor, '
        '@@global.wsrep_desync AS wsrep_desync, '
        '@@global.wsrep_provider_options AS wsrep_provider_options',
    )[0]
    if 'MariaDB' not in str(sysvars['version']):
        raise MariaDBGaleraError('Target server is not a native MariaDB instance')

    cur = conn.cursor()
    try:
        cur.execute("SHOW GLOBAL STATUS LIKE 'wsrep_%'")
        status_map = {str(k): str(v) for k, v in cur.fetchall()}
    finally:
        cur.close()

    provider_val = str(sysvars['wsrep_provider'] or '').strip()
    provider_loaded = (
        provider_val.lower() not in {'', 'none'}
        and bool(status_map.get('wsrep_provider_name'))
    )
    host_lib = inspect_provider_library(host_provider_path) if host_provider_path else None
    grastate = inspect_grastate(host_datadir) if host_datadir else None

    if not provider_loaded:
        return {
            'galera_available': False,
            'availability_reason': (
                host_lib['reason'] if (host_lib and not host_lib['available_on_host'])
                else 'wsrep_provider_not_loaded'
            ),
            'async_replication_substituted': False,
            'identity': {
                'version': sysvars['version'],
                'server_uid': sysvars['server_uid'],
                'server_id': int(sysvars['server_id']),
                'hostname': sysvars['hostname'],
                'port': int(sysvars['port']),
                'datadir': sysvars['datadir'],
            },
            'wsrep_on': mariadb_bool(sysvars['wsrep_on']),
            'wsrep_provider': provider_val,
            'host_provider_library': host_lib,
            'grastate': grastate,
        }

    provider_opts = parse_wsrep_provider_options(sysvars['wsrep_provider_options'])

    def _int_or_none(key):
        v = status_map.get(key)
        return int(v) if (v is not None and re.fullmatch(r'-?[0-9]+', v)) else None

    def _float_or_none(key):
        v = status_map.get(key)
        try:
            return float(v) if v is not None else None
        except ValueError:
            return None

    return {
        'galera_available': True,
        'availability_reason': 'wsrep_provider_loaded',
        'async_replication_substituted': False,
        'identity': {
            'version': sysvars['version'],
            'server_uid': sysvars['server_uid'],
            'server_id': int(sysvars['server_id']),
            'hostname': sysvars['hostname'],
            'port': int(sysvars['port']),
            'datadir': sysvars['datadir'],
            'read_only': mariadb_bool(sysvars['read_only']),
        },
        'wsrep_on': mariadb_bool(sysvars['wsrep_on']),
        'wsrep_provider': provider_val,
        'wsrep_provider_name': status_map.get('wsrep_provider_name'),
        'wsrep_provider_version': status_map.get('wsrep_provider_version'),
        'wsrep_provider_vendor': status_map.get('wsrep_provider_vendor'),
        'host_provider_library': host_lib,
        'cluster': {
            'wsrep_cluster_name': sysvars['wsrep_cluster_name'],
            'wsrep_cluster_address': sysvars['wsrep_cluster_address'],
            'wsrep_cluster_state_uuid': status_map.get('wsrep_cluster_state_uuid'),
            'wsrep_cluster_conf_id': _int_or_none('wsrep_cluster_conf_id'),
            'wsrep_cluster_size': _int_or_none('wsrep_cluster_size'),
            'wsrep_cluster_status': status_map.get('wsrep_cluster_status'),
            'wsrep_ready': status_map.get('wsrep_ready') == 'ON',
            'wsrep_connected': status_map.get('wsrep_connected') == 'ON',
            'wsrep_incoming_addresses': status_map.get('wsrep_incoming_addresses'),
        },
        'local_member': {
            'wsrep_node_name': sysvars['wsrep_node_name'],
            'wsrep_node_address': sysvars['wsrep_node_address'],
            'wsrep_node_incoming_address': sysvars['wsrep_node_incoming_address'],
            'wsrep_local_state': _int_or_none('wsrep_local_state'),
            'wsrep_local_state_comment': status_map.get('wsrep_local_state_comment'),
            'wsrep_local_state_uuid': status_map.get('wsrep_local_state_uuid'),
            'wsrep_last_committed': _int_or_none('wsrep_last_committed'),
            'wsrep_desync': mariadb_bool(sysvars['wsrep_desync']),
            'wsrep_local_cert_failures': _int_or_none('wsrep_local_cert_failures'),
            'wsrep_local_bf_aborts': _int_or_none('wsrep_local_bf_aborts'),
        },
        'flow_control': {
            'wsrep_flow_control_paused': _float_or_none('wsrep_flow_control_paused'),
            'wsrep_flow_control_paused_ns': _int_or_none('wsrep_flow_control_paused_ns'),
            'wsrep_flow_control_sent': _int_or_none('wsrep_flow_control_sent'),
            'wsrep_flow_control_recv': _int_or_none('wsrep_flow_control_recv'),
            'wsrep_flow_control_active': status_map.get('wsrep_flow_control_active'),
            'wsrep_local_recv_queue': _int_or_none('wsrep_local_recv_queue'),
            'wsrep_local_recv_queue_avg': _float_or_none('wsrep_local_recv_queue_avg'),
            'wsrep_local_send_queue': _int_or_none('wsrep_local_send_queue'),
        },
        'sst_ist': {
            'wsrep_sst_method': sysvars['wsrep_sst_method'],
            'wsrep_sst_receive_address': sysvars['wsrep_sst_receive_address'],
            'wsrep_sst_donor': sysvars['wsrep_sst_donor'],
            'ist_recv_addr': provider_opts.get('ist.recv_addr'),
            'gcache_size': provider_opts.get('gcache.size'),
            'pc_weight': provider_opts.get('pc.weight'),
            'provider_options': provider_opts,
        },
        'grastate': grastate,
    }


def set_node_desync(conn, *, enabled, expected_server_uid=None):
    """Toggle `SET GLOBAL wsrep_desync = ON|OFF` on an active Galera member."""
    if type(enabled) is not bool:
        raise MariaDBGaleraError('Supply boolean enabled for wsrep_desync')
    before = inspect_galera_node(conn)
    if not before['galera_available']:
        raise MariaDBGaleraError(
            f"Galera wsrep_provider is not available ({before['availability_reason']}); wsrep_desync refused"
        )
    if expected_server_uid and before['identity']['server_uid'] != expected_server_uid:
        raise MariaDBGaleraError('Target server_uid mismatch before setting wsrep_desync')
    if before['cluster']['wsrep_cluster_status'] != 'Primary':
        raise MariaDBGaleraError('Cannot change wsrep_desync while member is not in a Primary cluster component')

    cur = conn.cursor()
    try:
        cur.execute('SET GLOBAL wsrep_desync = ' + ('ON' if enabled else 'OFF'))
    finally:
        cur.close()

    after = inspect_galera_node(conn)
    if after['local_member']['wsrep_desync'] is not enabled:
        raise MariaDBGaleraError('Independent read-back did not confirm wsrep_desync state change')
    return {
        'enabled': enabled,
        'before_state_comment': before['local_member']['wsrep_local_state_comment'],
        'after_state_comment': after['local_member']['wsrep_local_state_comment'],
        'wsrep_desync': after['local_member']['wsrep_desync'],
        'server_uid': after['identity']['server_uid'],
    }


def promote_non_primary_quorum(conn, *, expected_server_uid=None, peer_committed_seqnos=()):
    """Recover quorum on the most-advanced surviving Non-Primary partition via `pc.bootstrap=YES`."""
    before = inspect_galera_node(conn)
    if not before['galera_available']:
        raise MariaDBGaleraError(
            f"Galera wsrep_provider is unavailable ({before['availability_reason']}); quorum recovery refused"
        )
    if expected_server_uid and before['identity']['server_uid'] != expected_server_uid:
        raise MariaDBGaleraError('Target server_uid mismatch before quorum promotion')
    if before['cluster']['wsrep_cluster_status'] == 'Primary':
        raise MariaDBGaleraError('Cluster component is already Primary; pc.bootstrap=YES is refused')

    local_seq = before['local_member']['wsrep_last_committed'] or -1
    higher = [s for s in peer_committed_seqnos if s is not None and int(s) > local_seq]
    if higher:
        raise MariaDBGaleraError(
            f'Refusing pc.bootstrap=YES on stale node: wsrep_last_committed={local_seq} < peer={max(higher)}'
        )

    cur = conn.cursor()
    try:
        cur.execute("SET GLOBAL wsrep_provider_options='pc.bootstrap=YES'")
    finally:
        cur.close()

    deadline = time.monotonic() + 20.0
    after = None
    while time.monotonic() < deadline:
        after = inspect_galera_node(conn)
        if (after['cluster']['wsrep_cluster_status'] == 'Primary'
                and after['cluster']['wsrep_ready']
                and after['local_member']['wsrep_local_state_comment'] == 'Synced'):
            break
        time.sleep(0.2)
    if not after or after['cluster']['wsrep_cluster_status'] != 'Primary':
        raise MariaDBGaleraError('Quorum bootstrap did not reach Primary/Synced state within deadline')
    return {
        'promoted': True,
        'before': before['cluster'],
        'after': after['cluster'],
        'local_member': after['local_member'],
    }


def stop_galera_member(conn, *, expected_server_uid=None, host_datadir=None, timeout_seconds=30):
    """Gracefully shut down a Galera member (`SHUTDOWN`) and optionally capture post-stop `grastate.dat`."""
    before = inspect_galera_node(conn)
    if not before['galera_available']:
        raise MariaDBGaleraError('Target server does not have Galera wsrep_provider loaded')
    if expected_server_uid and before['identity']['server_uid'] != expected_server_uid:
        raise MariaDBGaleraError('Target server_uid mismatch before Galera member stop')

    cur = conn.cursor()
    try:
        cur.execute('SHUTDOWN')
    finally:
        cur.close()

    if host_datadir:
        # Wait briefly for mariadbd to flush grastate.dat on clean exit
        gra_file = Path(host_datadir) / 'grastate.dat'
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if gra_file.is_file():
                gra = inspect_grastate(host_datadir)
                if gra['seqno'] is not None and gra['seqno'] >= 0:
                    break
            time.sleep(0.2)
        post_gra = inspect_grastate(host_datadir)
    else:
        post_gra = None

    return {
        'shutdown_acknowledged': True,
        'server_uid': before['identity']['server_uid'],
        'last_committed_before_stop': before['local_member']['wsrep_last_committed'],
        'grastate_after_stop': post_gra,
    }


def wait_for_galera_synced(
    *, host='127.0.0.1', port=3306, db_user='root', db_password='',
    expected_cluster_uuid=None, minimum_cluster_size=1,
    minimum_last_committed=None, timeout_seconds=90,
):
    """Wait for a bootstrapped or joining/rejoining Galera node to reach Primary + Synced."""
    import mariadb

    deadline = time.monotonic() + timeout_seconds
    last_obs = None
    last_err = None
    while time.monotonic() < deadline:
        try:
            conn = mariadb.connect(
                host=host, port=int(port),
                user=db_user, password=db_password or '',
                connect_timeout=3, autocommit=True,
            )
            try:
                obs = inspect_galera_node(conn)
                last_obs = obs
                if (obs['galera_available']
                        and obs['cluster']['wsrep_cluster_status'] == 'Primary'
                        and obs['cluster']['wsrep_ready'] is True
                        and obs['local_member']['wsrep_local_state_comment'] == 'Synced'
                        and (obs['cluster']['wsrep_cluster_size'] or 0) >= int(minimum_cluster_size)
                        and (expected_cluster_uuid is None
                             or obs['cluster']['wsrep_cluster_state_uuid'] == expected_cluster_uuid)
                        and (minimum_last_committed is None
                             or (obs['local_member']['wsrep_last_committed'] or -1) >= int(minimum_last_committed))):
                    return obs
            finally:
                conn.close()
        except Exception as exc:
            last_err = exc
        time.sleep(0.3)

    raise MariaDBGaleraError(
        f'Galera node at {host}:{port} did not reach Primary/Synced (size>={minimum_cluster_size}) '
        f'within {timeout_seconds}s; last_obs={last_obs}, last_err={last_err}'
    )

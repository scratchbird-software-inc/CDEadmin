"""Unit tests for MariaDB Batch 6: Physical Backup, Incremental Prepare, Recovery/Cutover,
Archive Retention, Host Config/Service, Host Upgrade, Galera & UI Descriptors.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import zlib

import pytest

from pgadmin.cdeadmin.providers.mysql_family import (
    mariadb_archive_checkpoint,
    mariadb_galera,
    mariadb_host_services,
    mariadb_host_upgrade,
    mariadb_physical,
)
from pgadmin.cdeadmin.ui_descriptors import UIDescriptorService
from pgadmin.cdeadmin.workspace import mariadb_archive_retention, mariadb_physical_service


def _make_fake_backup_dir(path: Path, *, backup_type='full-backuped', from_lsn=0, to_lsn=47765, last_lsn=47976,
                          server_version='12.2.2-MariaDB-ubu2404-log', binlog='sr-owned.000002\t794\t0-173-4',
                          modern_names=True):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    cp_name = 'mariadb_backup_checkpoints' if modern_names else 'xtrabackup_checkpoints'
    info_name = 'mariadb_backup_info' if modern_names else 'xtrabackup_info'
    bl_name = 'mariadb_backup_binlog_info' if modern_names else 'xtrabackup_binlog_info'
    (path / cp_name).write_text(
        f'backup_type = {backup_type}\nfrom_lsn = {from_lsn}\nto_lsn = {to_lsn}\n'
        f'last_lsn = {last_lsn}\nrecover_binlog_info = 0\n',
        encoding='utf-8',
    )
    inc_flag = 'Y' if backup_type == 'incremental' else 'N'
    (path / info_name).write_text(
        'uuid = 4a471edf-e47c-11f1-9e33-566c39ff35ba\n'
        'tool_name = mariadb-backup\n'
        'tool_version = 12.2.2-MariaDB\n'
        f'server_version = {server_version}\n'
        f'innodb_from_lsn = {from_lsn}\n'
        f'innodb_to_lsn = {to_lsn}\n'
        'partial = N\n'
        f'incremental = {inc_flag}\n'
        'compressed = N\n',
        encoding='utf-8',
    )
    (path / bl_name).write_text(binlog + '\n', encoding='utf-8')
    (path / 'ibdata1').write_bytes(b'INNODB_DATA_' + str(to_lsn).encode('ascii'))
    return path


def test_private_defaults_file_and_supervised_redaction(tmp_path):
    secret_pw = 'S3cr3t"Quote\\Line\nPass!'
    cnf = mariadb_physical.write_private_defaults_file(
        tmp_path / 'job', user='sr_backup', password=secret_pw, host='127.0.0.1', port=3306
    )
    assert stat.S_IMODE(cnf.lstat().st_mode) == 0o600
    text = cnf.read_text(encoding='utf-8')
    assert 'user="sr_backup"' in text
    assert 'skip-ssl' in text

    obs = mariadb_physical.run_supervised_process(
        '/bin/echo', [f'pw={secret_pw}', f'file={cnf}'], tmp_path / 'job',
        timeout_seconds=10, defaults_file=cnf, redact_values=(secret_pw,),
    )
    assert obs['credential_cleanup_confirmed'] is True
    assert not cnf.exists()
    assert secret_pw not in obs['stdout']
    assert '<redacted>' in obs['stdout']
    assert obs['process_termination_confirmed'] is True


def test_inspect_backup_artifact_modern_and_legacy(tmp_path):
    modern = _make_fake_backup_dir(tmp_path / 'modern', modern_names=True)
    art_m = mariadb_physical.inspect_backup_artifact(modern, expected_type='full-backuped')
    assert art_m['checkpoints_filename'] == 'mariadb_backup_checkpoints'
    assert art_m['from_lsn'] == '0'
    assert art_m['to_lsn'] == '47765'
    assert art_m['binlog_info']['binlog_file'] == 'sr-owned.000002'
    assert art_m['binlog_info']['gtid_pos'] == '0-173-4'
    assert art_m['xtrabackup_checkpoints']['backup_type'] == 'full-backuped'

    legacy = _make_fake_backup_dir(tmp_path / 'legacy', modern_names=False)
    art_l = mariadb_physical.inspect_backup_artifact(legacy, expected_type='full-backuped')
    assert art_l['checkpoints_filename'] == 'xtrabackup_checkpoints'
    assert art_l['manifest_sha256']

    # Reject non-zero from_lsn on full backup
    bad = _make_fake_backup_dir(tmp_path / 'bad', backup_type='full-backuped', from_lsn=100)
    with pytest.raises(mariadb_physical.MariaDBPhysicalError, match='from_lsn=0'):
        mariadb_physical.inspect_backup_artifact(bad)


def test_validate_backup_chain_and_interrupted_prepare_reconciliation(tmp_path):
    base_dir = _make_fake_backup_dir(tmp_path / 'base', backup_type='full-backuped', from_lsn=0, to_lsn=47765, last_lsn=47976)
    inc1_dir = _make_fake_backup_dir(tmp_path / 'inc1', backup_type='incremental', from_lsn=47765, to_lsn=47976, last_lsn=49682)
    bad_inc_dir = _make_fake_backup_dir(tmp_path / 'bad_inc', backup_type='incremental', from_lsn=99999, to_lsn=100100, last_lsn=100200)

    base_art = mariadb_physical.inspect_backup_artifact(base_dir)
    inc1_art = mariadb_physical.inspect_backup_artifact(inc1_dir)
    bad_art = mariadb_physical.inspect_backup_artifact(bad_inc_dir)

    base_rec = {
        'job_id': '00000000-0000-0000-0000-000000000001',
        'source': {'server_uid': 'S59OGp2dvoHvJ14+VWirMF8hTO4='},
        'artifact_adoption_state': 'artifact_adopted',
        'artifact_dir': str(base_dir),
        'result': {'artifact': base_art},
    }
    inc1_rec = {
        'job_id': '00000000-0000-0000-0000-000000000002',
        'source': {'server_uid': 'S59OGp2dvoHvJ14+VWirMF8hTO4='},
        'artifact_adoption_state': 'artifact_adopted',
        'artifact_dir': str(inc1_dir),
        'result': {'artifact': inc1_art},
    }
    bad_rec = {
        'job_id': '00000000-0000-0000-0000-000000000003',
        'source': {'server_uid': 'S59OGp2dvoHvJ14+VWirMF8hTO4='},
        'artifact_adoption_state': 'artifact_adopted',
        'artifact_dir': str(bad_inc_dir),
        'result': {'artifact': bad_art},
    }

    chain = mariadb_physical.validate_backup_chain(base_rec, [inc1_rec])
    assert chain['expected_final_to_lsn'] == '47976'
    assert chain['expected_final_last_lsn'] == '49682'

    with pytest.raises(mariadb_physical.MariaDBPhysicalError, match='Broken LSN chain'):
        mariadb_physical.validate_backup_chain(base_rec, [bad_rec])

    # Simulate interrupted prepare with leftover working_copy and reconcile
    prep_job_dir = tmp_path / 'prep_job'
    (prep_job_dir / 'working_copy').mkdir(parents=True)
    (prep_job_dir / 'working_copy' / 'dirty.tmp').write_text('partial')
    (prep_job_dir / 'prepare-state.json').write_text(json.dumps({
        'stage': 'interrupted_after_preparing_base',
        'steps_completed': ['staging_base', 'preparing_base'],
    }))
    recon = mariadb_physical.reconcile_interrupted_prepare(
        job_dir=prep_job_dir, base_record=base_rec, incremental_records=[inc1_rec]
    )
    assert recon['immutable_inputs_intact'] is True
    assert recon['partial_working_copy_removed'] is True
    assert recon['usable_for_recovery'] is False
    assert recon['automatic_retry'] is False
    assert not (prep_job_dir / 'working_copy').exists()


def test_archive_retention_physical_chain_and_uncertain_holds(tmp_path):
    reg = mariadb_archive_retention.MariaDBBackupProtectionRegistry(tmp_path / 'prot')
    owner = 1
    ep = '11111111-1111-1111-1111-111111111111'
    base_id = '22222222-2222-2222-2222-222222222221'
    inc_id = '22222222-2222-2222-2222-222222222222'
    uid = 'S59OGp2dvoHvJ14+VWirMF8hTO4='

    reg.register_physical_backup_hold(
        owner, ep, backup_job_id=base_id, source_uid=uid, backup_type='full-backuped',
        chain_root_job_id=base_id, binlog_file='sr-owned.000003', gtid_pos='0-173-10',
        from_lsn=0, to_lsn=50000, last_lsn=50100, state='active', native_acknowledged=True,
    )
    reg.register_physical_backup_hold(
        owner, ep, backup_job_id=inc_id, source_uid=uid, backup_type='incremental',
        chain_root_job_id=base_id, parent_job_id=base_id, binlog_file='sr-owned.000004',
        gtid_pos='0-173-15', from_lsn=50000, to_lsn=52000, last_lsn=52100,
        state='active', native_acknowledged=True,
    )

    refs = reg.protections(owner, ep)
    older_archive = {
        'job_id': '33333333-3333-3333-3333-333333333331',
        'endpoint_id': ep,
        'source': {'server_uid': uid},
        'result': {'artifact': {'start_from': {'file': 'sr-owned.000001'}, 'end_at': {'file': 'sr-owned.000002'}}},
    }
    needed_archive = {
        'job_id': '33333333-3333-3333-3333-333333333332',
        'endpoint_id': ep,
        'source': {'server_uid': uid},
        'result': {'artifact': {'start_from': {'file': 'sr-owned.000003'}, 'end_at': {'file': 'sr-owned.000004'}}},
    }

    # Archive strictly before sr-owned.000003 is NOT needed by base_id or inc_id
    assert reg.protected(older_archive, refs) is False
    # Archive overlapping sr-owned.000003..000004 IS protected!
    assert reg.protected(needed_archive, refs) is True
    with pytest.raises(mariadb_archive_retention.BinlogArchiveError, match='dependency-aware retention protects'):
        with reg.guard(owner, ep, needed_archive):
            pass

    # Cannot retire base_id while child inc_id depends on it!
    with pytest.raises(mariadb_archive_retention.BinlogArchiveError, match='dependent incremental backups'):
        reg.review_retire_hold(owner, ep, base_id)

    # Uncertain hold blocks ALL archives for source_uid, even older_archive!
    uncertain = reg.record_uncertain_hold(
        owner, ep,
        origin_operation='mariadb_continuous_receiver',
        origin_job_id='44444444-4444-4444-4444-444444444444',
        source_uid=uid,
        uncertainty_reason='Receiver process exit unconfirmed',
        native_acknowledged=False,
    )
    refs_with_uncertain = reg.protections(owner, ep)
    assert reg.protected(older_archive, refs_with_uncertain) is True

    # Retiring uncertain hold requires reconciliation_acknowledged=True
    rev = reg.review_retire_hold(owner, ep, uncertain['hold_id'])
    with pytest.raises(mariadb_archive_retention.BinlogArchiveError, match='reconciliation_acknowledged'):
        reg.retire_hold(owner, ep, {
            'review_id': rev['review_id'], 'review_digest': rev['review_digest'], 'confirmed': True
        })
    retired = reg.retire_hold(owner, ep, {
        'review_id': rev['review_id'],
        'review_digest': rev['review_digest'],
        'confirmed': True,
        'reconciliation_acknowledged': True,
    })
    assert retired['state'] == 'retired'
    assert retired['original_native_acknowledgement_preserved'] is True


def test_mariadb_archive_checkpoint_rotation_parser(tmp_path):
    arch_dir = tmp_path / 'archive'
    arch_dir.mkdir(mode=0o700)
    next_name = b'sr-owned.000002'
    body = struct.pack('<Q', 4) + next_name
    total_len = 19 + len(body) + 4
    header = struct.pack('<IBIIIH', 1700000000, 4, 173, total_len, 100, 0)
    crc = zlib.crc32(header + body)
    rotate_event = header + body + struct.pack('<I', crc)
    binlog_bytes = b'\xfebin' + rotate_event
    binlog_path = arch_dir / 'sr-owned.000001'
    binlog_path.write_bytes(binlog_bytes)

    source = {'version': '12.2.2-MariaDB', 'server_uid': 'abc='}
    meta = {
        'format': 'mariadb-binlog@12.2.2',
        'source': source,
        'logs': [{'name': 'sr-owned.000001', 'last_event_type': 4}],
        'source_successor': {
            'file': 'sr-owned.000002',
            'position': '4',
            'scope': mariadb_archive_checkpoint.SUCCESSOR_SCOPE,
        },
    }
    meta_bytes = json.dumps(meta, sort_keys=True).encode('utf-8')
    (arch_dir / 'archive.json').write_bytes(meta_bytes)
    artifact = {
        'end_at': {'file': 'sr-owned.000001', 'position': str(len(binlog_bytes))},
        'files': [
            {'path': 'archive.json', 'size': len(meta_bytes), 'sha256': hashlib.sha256(meta_bytes).hexdigest()},
            {'path': 'sr-owned.000001', 'size': len(binlog_bytes), 'sha256': hashlib.sha256(binlog_bytes).hexdigest()},
        ],
        'event_integrity': [{'binlog': 'sr-owned.000001', 'checksum_algorithm': 'crc32'}],
    }
    succ = mariadb_archive_checkpoint.successor(arch_dir, artifact, source)
    assert succ['next_file'] == 'sr-owned.000002'
    assert succ['successor_authority'] == 'native-terminal-rotation'


def test_host_option_file_graph_and_boot_policy(tmp_path):
    etc = tmp_path / 'etc_mysql'
    confd = etc / 'mariadb.conf.d'
    confd.mkdir(parents=True)
    my_cnf = etc / 'my.cnf'
    srv_cnf = confd / '50-server.cnf'
    my_cnf.write_text(f'[client-server]\nport = 3306\n!includedir {confd}\n', encoding='utf-8')
    srv_cnf.write_text(
        '[mysqld]\ndatadir = /var/lib/mysql\nmax_connections = 250\nwsrep_sst_auth = sst_user:SuperSecret123\n',
        encoding='utf-8',
    )

    graph = mariadb_host_services.inspect_option_file_graph(my_cnf)
    assert graph['file_count'] == 2
    assert graph['effective_server_options']['max_connections'] == '250'
    assert graph['effective_server_options']['wsrep_sst_auth'] == '<redacted>'
    assert 'SuperSecret123' not in json.dumps(graph)

    boot_res = mariadb_host_services.control_managed_service(
        action='set_boot_policy',
        service_mode='managed_daemon',
        state_dir=tmp_path / 'svc_state',
        boot_enabled=True,
    )
    assert boot_res['boot_policy'] == 'enabled'
    assert boot_res['sql_readiness_verified'] is False


def test_upgrade_guards_and_rollback(tmp_path):
    # Verify backup prerequisite rejects missing backup
    with pytest.raises(mariadb_host_upgrade.MariaDBUpgradeError, match='verified backup prerequisite'):
        mariadb_host_upgrade.verify_backup_prerequisite()

    # Verify rollback restores exact 11.8 snapshot and releases claim
    ddir = tmp_path / 'data118'
    ddir.mkdir()
    (ddir / 'mariadb_upgrade_info').write_text('11.8.9-MariaDB\n', encoding='utf-8')
    (ddir / 'ibdata1').write_bytes(b'ORIGINAL_11_8_BYTES')

    job_dir = tmp_path / 'upg_job'
    snap_dir = job_dir / 'pre-upgrade-snapshot'
    import shutil
    shutil.copytree(ddir, snap_dir)
    snap_sha = mariadb_physical.canonical_digest(mariadb_physical.directory_manifest(snap_dir))

    # Mutate datadir as if partial upgrade occurred & create claim
    (ddir / 'mariadb_upgrade_info').write_text('PARTIAL\n', encoding='utf-8')
    (ddir / 'partial.tmp').write_bytes(b'dirty')
    claim = mariadb_host_upgrade.claim_path_for_datadir(ddir)
    claim.write_text('{"job_id":"test"}')
    (job_dir / 'upgrade-phase.json').write_text(json.dumps({
        'stage': 'interrupted_before_mariadb_upgrade_tool',
        'steps_completed': ['verified_datadir_quiescent', 'pre_upgrade_snapshot_captured'],
        'target_state_dir': str(job_dir / 'target-daemon'),
        'rollback_snapshot': {'path': str(snap_dir), 'manifest_sha256': snap_sha},
    }))

    recon = mariadb_host_upgrade.reconcile_interrupted_upgrade(job_dir=job_dir, datadir=ddir)
    assert recon['claim_present'] is True
    assert recon['rollback_snapshot_available'] is True
    assert recon['automatic_retry'] is False

    rb = mariadb_host_upgrade.rollback_interrupted_upgrade(job_dir=job_dir, datadir=ddir)
    assert rb['rolled_back'] is True
    assert rb['claim_released'] is True
    assert not claim.exists()
    assert not (ddir / 'partial.tmp').exists()
    assert (ddir / 'mariadb_upgrade_info').read_text().strip() == '11.8.9-MariaDB'


def test_galera_unavailable_and_grastate_safe_to_bootstrap(tmp_path):
    class _FakeCursor:
        def execute(self, sql):
            self.sql = sql
        def fetchall(self):
            if 'SHOW GLOBAL STATUS' in self.sql:
                return []
            return [(
                '12.2.2-MariaDB', 'uid1=', 1, 'node1', 3306, '/var/lib/mysql', 0,
                0, 'none', '', '', 'node1', '', 'AUTO', 'rsync', 'AUTO', '', 0, '',
            )]
        @property
        def description(self):
            return [
                ('version',), ('server_uid',), ('server_id',), ('hostname',), ('port',),
                ('datadir',), ('read_only',), ('wsrep_on',), ('wsrep_provider',),
                ('wsrep_cluster_name',), ('wsrep_cluster_address',), ('wsrep_node_name',),
                ('wsrep_node_address',), ('wsrep_node_incoming_address',), ('wsrep_sst_method',),
                ('wsrep_sst_receive_address',), ('wsrep_sst_donor',), ('wsrep_desync',),
                ('wsrep_provider_options',),
            ]
        def close(self):
            pass

    class _FakeConn:
        autocommit = True
        def cursor(self):
            return _FakeCursor()

    obs = mariadb_galera.inspect_galera_node(_FakeConn())
    assert obs['galera_available'] is False
    assert obs['availability_reason'] == 'wsrep_provider_not_loaded'
    assert obs['async_replication_substituted'] is False

    # Test grastate.dat safe_to_bootstrap=0 refusal, stale peer refusal, and forced recovery
    gdir = tmp_path / 'galera_data'
    gdir.mkdir()
    (gdir / 'grastate.dat').write_text(
        '# GALERA saved state\nversion: 2.1\nuuid:    12345678-1234-1234-1234-123456789abc\n'
        'seqno:   42\nsafe_to_bootstrap: 0\n',
        encoding='utf-8',
    )
    gra = mariadb_galera.inspect_grastate(gdir)
    assert gra['safe_to_bootstrap'] is False
    assert gra['seqno'] == 42

    with pytest.raises(mariadb_galera.MariaDBGaleraError, match='safe_to_bootstrap=0'):
        mariadb_galera.validate_and_prepare_grastate_bootstrap(gdir, force_safe_to_bootstrap=False)

    with pytest.raises(mariadb_galera.MariaDBGaleraError, match='stale node'):
        mariadb_galera.validate_and_prepare_grastate_bootstrap(
            gdir, force_safe_to_bootstrap=True, peer_seqnos=[50]
        )

    promoted = mariadb_galera.validate_and_prepare_grastate_bootstrap(
        gdir, force_safe_to_bootstrap=True, peer_seqnos=[40], backup_dir=tmp_path / 'bk'
    )
    assert promoted['bootstrap_admitted'] is True
    assert promoted['grastate_modified'] is True
    assert Path(promoted['backup_path']).is_file()
    assert mariadb_galera.inspect_grastate(gdir)['safe_to_bootstrap'] is True


def test_mariadb_ui_descriptors_for_batch6():
    bundle = UIDescriptorService().engine('mariadb')
    op_ids = {op['operation_id'] for op in bundle['operations'] if op['resource_kind'] == 'server'}
    expected_ops = {
        'physical_backup',
        'prepare_physical_chain',
        'recover_physical_instance',
        'evaluate_archive_retention',
        'manage_host_service',
        'upgrade_server_instance',
        'manage_galera_cluster',
    }
    assert expected_ops.issubset(op_ids)
    tool_cmds = {t['command_id'] for t in bundle['tools']}
    for suffix in ('physical', 'archive_retention', 'host', 'upgrade', 'galera'):
        assert f'endpoint.{{engine_id}}.{suffix}' in tool_cmds or f'endpoint.mariadb.{suffix}' in tool_cmds

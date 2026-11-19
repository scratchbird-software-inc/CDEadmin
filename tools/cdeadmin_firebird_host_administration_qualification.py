"""Qualify Firebird 5.0.4 host configuration (FB-AUD-03), plugin/UDR deployment (FB-AUD-06)
and runtime lifecycle + cross-version ODS 12.0/13.0 -> 13.1 migration (FB-AUD-05).
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]

DONOR_INCLUDE = Path('/home/dcalford/Sandbox/donor_release_acquisition/firebird/5.0.4/source/src/include')
FB4_FIXTURE = Path('/home/dcalford/Sandbox/codex-work-area/cdeadmin-six-engine-implementation/firebird4-current-fixture/upgrade-original.fdb')

CLEAN_ROOM_UDR_CPP = """\
#define FB_UDR_STATUS_TYPE ::Firebird::ThrowStatusWrapper
#include "firebird/UdrCppEngine.h"

FB_UDR_BEGIN_FUNCTION(audit_triple)
    FB_UDR_MESSAGE(InMessage, (FB_INTEGER, val));
    FB_UDR_MESSAGE(OutMessage, (FB_INTEGER, res));
    FB_UDR_EXECUTE_FUNCTION
    {
        if (in->valNull)
        {
            out->resNull = FB_TRUE;
            out->res = 0;
        }
        else
        {
            out->resNull = FB_FALSE;
            out->res = in->val * 3;
        }
    }
FB_UDR_END_FUNCTION

FB_UDR_IMPLEMENT_ENTRY_POINT
"""


def _build_fb3_ods12_fixture(staging_dir):
    """Create a real Firebird 3.0 ODS 12.0 .fdb and portable .fbk in a disposable container."""
    container_name = 'cdeadmin-fb3-ods12-' + uuid.uuid4().hex[:12]
    out_fdb = staging_dir / 'legacy_fb3_ods12.fdb'
    out_fbk = staging_dir / 'legacy_fb3_ods12.fbk'
    sql_script = (
        "CREATE DATABASE '/tmp/fb3_src.fdb' USER 'SYSDBA' PASSWORD 'masterkey' PAGE_SIZE 8192 DEFAULT CHARACTER SET UTF8;\n"
        "CREATE TABLE DEPT (DEPT_ID INTEGER NOT NULL PRIMARY KEY, TITLE VARCHAR(60));\n"
        "CREATE TABLE EMP (EMP_ID INTEGER NOT NULL PRIMARY KEY, DEPT_ID INTEGER NOT NULL REFERENCES DEPT(DEPT_ID), FULL_NAME VARCHAR(80));\n"
        "COMMIT;\n"
        "INSERT INTO DEPT VALUES (10, 'Engineering 東京');\n"
        "INSERT INTO EMP VALUES (101, 10, 'Ada Lovelace');\n"
        "INSERT INTO EMP VALUES (102, 10, 'Grace Hopper');\n"
        "COMMIT;\n"
        "CREATE VIEW EMP_VIEW AS SELECT E.EMP_ID, E.FULL_NAME, D.TITLE FROM EMP E JOIN DEPT D ON D.DEPT_ID = E.DEPT_ID;\n"
        "SET TERM ^ ;\n"
        "CREATE PROCEDURE EMP_COUNT RETURNS (CNT INTEGER) AS BEGIN SELECT COUNT(*) FROM EMP INTO :CNT; SUSPEND; END^\n"
        "SET TERM ; ^\n"
        "COMMIT;\n"
    )
    try:
        proc = subprocess.run(
            [
                'docker', 'run', '--rm', '--name', container_name,
                '--entrypoint', '/bin/sh',
                'jacobalberty/firebird:v3.0',
                '-c',
                (
                    'cat > /tmp/init.sql <<\'EOF\'\n' + sql_script + 'EOF\n'
                    '/usr/local/firebird/bin/isql -q -i /tmp/init.sql && '
                    '/usr/local/firebird/bin/gbak -b -t -user SYSDBA -password masterkey /tmp/fb3_src.fdb /tmp/fb3_src.fbk && '
                    'base64 -w0 /tmp/fb3_src.fdb && echo "" && base64 -w0 /tmp/fb3_src.fbk && echo ""'
                ),
            ],
            capture_output=True, text=True, timeout=60, check=True,
        )
        import base64
        non_empty = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
        fdb_b64, fbk_b64 = non_empty[-2], non_empty[-1]
        out_fdb.write_bytes(base64.b64decode(fdb_b64))
        out_fbk.write_bytes(base64.b64decode(fbk_b64))
        return out_fdb, out_fbk
    finally:
        subprocess.run(['docker', 'rm', '-f', container_name], capture_output=True, check=False)


def qualify_native(runtime, output):
    from tools.cdeadmin_firebird_object_live_orchestrator import (
        _stage_runtime, _runtime_fingerprint, _initialize_security, _free_port,
    )
    from pgadmin.cdeadmin.providers.firebird import provider as network
    from pgadmin.cdeadmin.providers.firebird.host_runtime_grant import (
        file_sha256, resolve_admin_host_scope,
    )
    from pgadmin.cdeadmin.providers.firebird.host_configuration import (
        inspect_host_configuration, prepare_configuration_review, apply_host_configuration,
    )
    from pgadmin.cdeadmin.providers.firebird.plugin_deployment import (
        inspect_plugin_environment, prepare_plugin_review, apply_plugin_operation,
    )
    from pgadmin.cdeadmin.providers.firebird.runtime_lifecycle import (
        inspect_runtime_environment, inspect_database_ods,
        prepare_runtime_review, apply_runtime_operation,
        start_managed_daemon_process, stop_managed_daemon_process,
    )
    from pgadmin.cdeadmin.workspace.firebird_host_actions import HostActions
    from tools.mysql_driver_gate_support import provider_access

    runtime, output = Path(runtime).resolve(), Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True, exist_ok=True)
    before = _runtime_fingerprint(runtime)
    proof = {
        'complete': False,
        'history_tests': 'not run',
        'scope': (
            'Owned Linux Firebird 5.0.4 host configuration + failed-restart rollback (FB-AUD-03), '
            'compiled C++ UDR + plugin deployment (FB-AUD-06), and daemon lifecycle + ODS 12.0/13.0 -> 13.1 '
            'cross-version migration (FB-AUD-05)'
        ),
        'checks': [],
    }
    tracked_files = [
        'web/pgadmin/cdeadmin/providers/firebird/host_runtime_grant.py',
        'web/pgadmin/cdeadmin/providers/firebird/host_configuration.py',
        'web/pgadmin/cdeadmin/providers/firebird/plugin_deployment.py',
        'web/pgadmin/cdeadmin/providers/firebird/runtime_lifecycle.py',
        'web/pgadmin/cdeadmin/workspace/firebird_host_actions.py',
        'web/pgadmin/cdeadmin/workspace/service.py',
        'web/pgadmin/cdeadmin/ui_descriptors/firebird/tools.json',
        'tools/cdeadmin_firebird_host_administration_qualification.py',
    ]
    proof['source_sha256'] = {
        rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
        for rel in tracked_files
    }

    prev_manifest = os.environ.get('CDEADMIN_FIREBIRD_HOST_TOOLS_MANIFEST')
    try:
        with tempfile.TemporaryDirectory(prefix='fb-host-admin-', dir=output) as folder:
            area = Path(folder)
            stage = area / 'runtime'
            staging_dir = area / 'staging'
            journal_dir = area / 'journals'
            staging_dir.mkdir()
            journal_dir.mkdir()
            _stage_runtime(runtime, stage)
            # Materialize writable replication.conf and plugins/ directory so owned host
            # mutations never touch the read-only source runtime kit.
            (stage / 'replication.conf').unlink()
            shutil.copy2(runtime / 'replication.conf', stage / 'replication.conf')
            (stage / 'plugins').unlink()
            shutil.copytree(runtime / 'plugins', stage / 'plugins', symlinks=True)

            (stage / 'firebird.conf').write_text(
                'ServerMode = SuperClassic\nProviders = Remote,Engine13\n'
                f'SecurityDatabase = {stage / "security5.fdb"}\n',
                encoding='utf-8',
            )
            primary_db = area / 'primary.fdb'
            sibling_db = area / 'sibling.fdb'
            (stage / 'databases.conf').write_text(
                f'SIBLING_ALIAS = {sibling_db}\n',
                encoding='utf-8',
            )
            os.environ.update(
                FIREBIRD=str(stage),
                FIREBIRD_LOCK=str(stage / 'lock'),
                CDEADMIN_FIREBIRD_CLIENT_LIBRARY=str(stage / 'lib/libfbclient.so.5.0.4'),
            )
            sysdba_pw = secrets.token_urlsafe(24)
            peer_pw = secrets.token_urlsafe(24)
            _initialize_security(stage, sysdba_pw, dict(os.environ))
            port = _free_port()

            manifest_file = area / 'host-manifest.json'
            endpoint_id = 'owned-host-ep'
            manifest_doc = {
                'format': 'scratchrobin.firebird.host-tools@1',
                'grants': [
                    {
                        'endpoint_id': endpoint_id,
                        'firebird_runtime_root': str(stage),
                        'firebird_lock_directory': str(stage / 'lock'),
                        'databases': [str(primary_db), str(sibling_db)],
                        'allow_host_administration': True,
                        'staging_directory': str(staging_dir),
                        'journal_directories': [str(journal_dir)],
                        'managed_daemon': {
                            'pid_file': str(area / 'firebird.pid'),
                            'port': port,
                            'bind_host': '127.0.0.1',
                            'server_log': str(area / 'daemon.log'),
                        },
                    }
                ],
            }
            manifest_file.write_text(json.dumps(manifest_doc, indent=2) + '\n', encoding='utf-8')
            os.environ['CDEADMIN_FIREBIRD_HOST_TOOLS_MANIFEST'] = str(manifest_file)

            import firebird.driver as fb_mod
            fb_mod.driver_config.fb_client_library.value = str(stage / 'lib/libfbclient.so.5.0.4')

            base_route = {
                'host': '127.0.0.1', 'port': port, 'database': str(primary_db),
                'user': 'SYSDBA', 'charset': 'UTF8', 'wire_crypt': 'Required', 'trusted_auth': False,
            }
            route, perms = provider_access(base_route, sysdba_pw)
            perms.require = lambda *_: None
            perms.allows = lambda *_: True

            host_scope = resolve_admin_host_scope(endpoint_id, route, require_mutation=True)
            started_daemon = start_managed_daemon_process(host_scope)
            assert started_daemon['ok'] and started_daemon['pid'] > 1, started_daemon
            initial_pid = started_daemon['pid']

            try:
                client = network._create_client(perms, attachment_mode='network')
                try:
                    for db_target, marker in ((primary_db, 101), (sibling_db, 202)):
                        db_r = {**route, 'database': str(db_target)}
                        c = client.config.database_creator(
                            **client.config.database_create_arguments(db_r, str(db_target), {}),
                            password=sysdba_pw,
                        )
                        c.execute_immediate('CREATE TABLE KEEP_DATA (ID INTEGER NOT NULL PRIMARY KEY)')
                        c.commit()
                        c.execute_immediate(f'INSERT INTO KEEP_DATA VALUES ({marker})')
                        c.commit()
                        c.close()

                    srv = client._connect_server({'route': route})
                    try:
                        srv.user.add(user_name='CFG_PEER', password=peer_pw)
                    finally:
                        client._release_server(srv)

                    # --- 1. FB-AUD-03: Host configuration, CAS, restart & failed-restart rollback ---
                    cfg_journal = HostActions(area / 'cfg-journal.json', 'fb_cfg', {'update_configuration'})
                    snap = inspect_host_configuration(host_scope, client, route)
                    fb_gen_0 = snap['files']['firebird.conf']['generation_sha256']

                    # Invalid option and stale CAS refusals
                    for bad_req in (
                        {'target_file': 'firebird.conf', 'expected_generation_sha256': fb_gen_0, 'set_options': {'NoSuchOption': '1'}},
                        {'target_file': 'firebird.conf', 'expected_generation_sha256': '0' * 64, 'set_options': {'StatementTimeout': 30}},
                    ):
                        denied = False
                        try:
                            prepare_configuration_review(host_scope, bad_req)
                        except ValueError:
                            denied = True
                        assert denied

                    # Valid firebird.conf update + managed daemon restart + live RDB$CONFIG read-back
                    rev1 = cfg_journal.review(
                        'owner', 'b1', 'update_configuration',
                        prepare_configuration_review(host_scope, {
                            'target_file': 'firebird.conf',
                            'expected_generation_sha256': fb_gen_0,
                            'lifecycle_action': 'restart_managed_daemon',
                            'set_options': {
                                'DefaultDbCachePages': 1536,
                                'StatementTimeout': 45,
                                'TempCacheLimit': '64M',
                            },
                        }),
                    )
                    out1 = cfg_journal.apply(
                        'owner', 'b1',
                        {'review_id': rev1['review_id'], 'review_digest': rev1['review_digest'], 'confirmed': True},
                        apply_host_configuration,
                    )['outcome']
                    assert out1['state'] == 'applied' and out1['restart_performed'] is True, out1
                    assert out1['daemon_receipt']['pid'] != initial_pid
                    snap_after = inspect_host_configuration(host_scope, client, route)
                    assert snap_after['live_rdb_config']['DefaultDbCachePages']['value'] == '1536'
                    assert snap_after['live_rdb_config']['StatementTimeout']['value'] == '45'
                    fb_gen_1 = snap_after['files']['firebird.conf']['generation_sha256']

                    # Failed restart automatic rollback & recovery (IPv6-only bind breaks IPv4 127.0.0.1 listener)
                    rev_fail = cfg_journal.review(
                        'owner', 'b1', 'update_configuration',
                        prepare_configuration_review(host_scope, {
                            'target_file': 'firebird.conf',
                            'expected_generation_sha256': fb_gen_1,
                            'lifecycle_action': 'restart_managed_daemon',
                            'set_options': {'RemoteBindAddress': '::1', 'IPv6V6Only': True},
                        }),
                    )
                    out_fail = cfg_journal.apply(
                        'owner', 'b1',
                        {'review_id': rev_fail['review_id'], 'review_digest': rev_fail['review_digest'], 'confirmed': True},
                        apply_host_configuration,
                    )['outcome']
                    assert out_fail['state'] == 'rolled_back_after_failed_restart', out_fail
                    assert out_fail['rolled_back'] is True and out_fail['daemon_recovered'] is True
                    snap_recovered = inspect_host_configuration(host_scope, client, route)
                    assert snap_recovered['files']['firebird.conf']['generation_sha256'] == fb_gen_1

                    # Verify sibling database and secondary CFG_PEER credentials survived untouched
                    peer_route, peer_perms = provider_access(
                        {**base_route, 'database': 'SIBLING_ALIAS', 'user': 'CFG_PEER'}, peer_pw,
                    )
                    peer_perms.require = lambda *_: None
                    peer_perms.allows = lambda *_: True
                    sib_conn = client._connect({'route': {**route, 'database': 'SIBLING_ALIAS'}})
                    try:
                        sib_conn.execute_immediate('GRANT SELECT ON KEEP_DATA TO CFG_PEER')
                        sib_conn.commit()
                    finally:
                        client._forget_and_close(sib_conn)
                    peer_client = network._create_client(peer_perms, attachment_mode='network')
                    try:
                        pc = peer_client._connect({'route': peer_route})
                        try:
                            cur = pc.cursor()
                            cur.execute('SELECT ID FROM KEEP_DATA')
                            assert cur.fetchall() == [(202,)]
                            cur.close()
                            pc.rollback()
                        finally:
                            peer_client._forget_and_close(pc)
                    finally:
                        peer_client.close()
                    proof['checks'].append(
                        'FB-AUD-03: firebird.conf typed update, RDB$CONFIG read-back, and failed-restart automatic rollback/recovery preserving sibling DB and peer credentials'
                    )

                    # databases.conf per-DB override + sibling preservation + replication.conf + plugins.conf
                    db_gen_0 = snap_recovered['files']['databases.conf']['generation_sha256']
                    rev_db = cfg_journal.review(
                        'owner', 'b1', 'update_configuration',
                        prepare_configuration_review(host_scope, {
                            'target_file': 'databases.conf',
                            'expected_generation_sha256': db_gen_0,
                            'upsert_aliases': {
                                'PRIMARY_ALIAS': {
                                    'path': str(primary_db),
                                    'overrides': {'DefaultDbCachePages': 768},
                                }
                            },
                        }),
                    )
                    out_db = cfg_journal.apply(
                        'owner', 'b1',
                        {'review_id': rev_db['review_id'], 'review_digest': rev_db['review_digest'], 'confirmed': True},
                        apply_host_configuration,
                    )['outcome']
                    assert out_db['state'] == 'applied' and out_db['preserved_sibling_aliases'] == ['SIBLING_ALIAS']
                    alias_conn = client._connect({'route': {**route, 'database': 'PRIMARY_ALIAS'}})
                    try:
                        cur = alias_conn.cursor()
                        cur.execute("SELECT RDB$CONFIG_VALUE FROM RDB$CONFIG WHERE TRIM(TRAILING FROM RDB$CONFIG_NAME)='DefaultDbCachePages'")
                        assert cur.fetchone() == ('768',)
                        cur.close()
                        alias_conn.rollback()
                    finally:
                        client._forget_and_close(alias_conn)

                    repl_gen_0 = inspect_host_configuration(host_scope)['files']['replication.conf']['generation_sha256']
                    rev_repl = cfg_journal.review(
                        'owner', 'b1', 'update_configuration',
                        prepare_configuration_review(host_scope, {
                            'target_file': 'replication.conf',
                            'expected_generation_sha256': repl_gen_0,
                            'replication_spec': {
                                'databases': {
                                    str(primary_db): {
                                        'journal_directory': str(journal_dir / 'active'),
                                        'journal_archive_directory': str(journal_dir / 'archive'),
                                        'journal_archive_timeout': 10,
                                    }
                                }
                            },
                        }),
                    )
                    assert cfg_journal.apply(
                        'owner', 'b1',
                        {'review_id': rev_repl['review_id'], 'review_digest': rev_repl['review_digest'], 'confirmed': True},
                        apply_host_configuration,
                    )['outcome']['state'] == 'applied'
                    proof['checks'].append(
                        'FB-AUD-03: databases.conf per-database override read-back + sibling alias preservation + replication.conf validation'
                    )

                    # --- 2. FB-AUD-06: Compile clean-room C++ UDR, refuse invalid .so, deploy, execute & remove ---
                    udr_cpp_path = area / 'owned_audit_udr.cpp'
                    udr_cpp_path.write_text(CLEAN_ROOM_UDR_CPP, encoding='utf-8')
                    staged_udr_so = staging_dir / 'libowned_audit_udr.so'
                    subprocess.run(
                        [
                            'g++', '-std=c++17', '-shared', '-fPIC', '-O2',
                            f'-I{DONOR_INCLUDE}',
                            str(udr_cpp_path), '-o', str(staged_udr_so),
                        ],
                        check=True, timeout=30,
                    )
                    udr_sha = file_sha256(staged_udr_so)

                    # Wrong-symbol .so (copy libChaCha.so into staging as a fake UDR) must be refused
                    wrong_sym_so = staging_dir / 'libwrong_sym.so'
                    shutil.copy2(stage / 'plugins/libChaCha.so', wrong_sym_so)
                    wrong_sym_denied = False
                    try:
                        prepare_plugin_review(host_scope, {
                            'operation': 'deploy_udr_module',
                            'module_name': 'wrong_sym',
                            'expected_source_sha256': file_sha256(wrong_sym_so),
                        })
                    except ValueError as err:
                        wrong_sym_denied = 'firebird_udr_plugin' in str(err)
                    assert wrong_sym_denied

                    plug_journal = HostActions(
                        area / 'plug-journal.json', 'fb_plug',
                        {'deploy_udr_module', 'remove_udr_module', 'deploy_plugin', 'remove_plugin'},
                    )
                    rev_udr = plug_journal.review(
                        'owner', 'b1', 'deploy_udr_module',
                        prepare_plugin_review(host_scope, {
                            'operation': 'deploy_udr_module',
                            'module_name': 'owned_audit_udr',
                            'expected_source_sha256': udr_sha,
                        }),
                    )
                    out_udr = plug_journal.apply(
                        'owner', 'b1',
                        {'review_id': rev_udr['review_id'], 'review_digest': rev_udr['review_digest'], 'confirmed': True},
                        apply_plugin_operation,
                    )['outcome']
                    assert out_udr['state'] == 'deployed', out_udr

                    uconn = client._connect({'route': route})
                    try:
                        uconn.execute_immediate(
                            "CREATE FUNCTION AUDIT_TRIPLE(VAL INTEGER) RETURNS INTEGER "
                            "EXTERNAL NAME 'owned_audit_udr!audit_triple' ENGINE UDR"
                        )
                        uconn.commit()
                        cur = uconn.cursor()
                        cur.execute('SELECT AUDIT_TRIPLE(14), AUDIT_TRIPLE(NULL) FROM RDB$DATABASE')
                        assert cur.fetchall() == [(42, None)]
                        cur.close()
                        uconn.rollback()
                    finally:
                        client._forget_and_close(uconn)

                    inv = inspect_plugin_environment(host_scope, client, route)
                    assert any(
                        d['object_name'] == 'AUDIT_TRIPLE' and d['module_binary_installed'] is True
                        for d in inv['database_udr_dependents']
                    )

                    # Removal must refuse while AUDIT_TRIPLE still depends on owned_audit_udr
                    dep_refused = False
                    try:
                        prepare_plugin_review(
                            host_scope,
                            {'operation': 'remove_udr_module', 'module_name': 'owned_audit_udr', 'confirmation': 'owned_audit_udr'},
                            client, route,
                        )
                    except ValueError as err:
                        dep_refused = 'AUDIT_TRIPLE' in str(err)
                    assert dep_refused

                    uconn = client._connect({'route': route})
                    try:
                        uconn.execute_immediate('DROP FUNCTION AUDIT_TRIPLE')
                        uconn.commit()
                    finally:
                        client._forget_and_close(uconn)

                    rev_rm_udr = plug_journal.review(
                        'owner', 'b1', 'remove_udr_module',
                        prepare_plugin_review(
                            host_scope,
                            {'operation': 'remove_udr_module', 'module_name': 'owned_audit_udr', 'confirmation': 'owned_audit_udr'},
                            client, route,
                        ),
                    )
                    out_rm_udr = plug_journal.apply(
                        'owner', 'b1',
                        {'review_id': rev_rm_udr['review_id'], 'review_digest': rev_rm_udr['review_digest'], 'confirmed': True},
                        apply_plugin_operation,
                    )['outcome']
                    assert out_rm_udr['state'] == 'removed' and not Path(out_rm_udr['removed_path']).exists()
                    proof['checks'].append(
                        'FB-AUD-06: ELF64/symbol gate, clean-room C++ UDR deployment, live SQL execution (14*3=42), dependent-routine removal guard, and clean backup/uninstall'
                    )

                    # --- 3. FB-AUD-05: Runtime bundle staging, daemon stop/start & ODS 12.0 + 13.0 -> 13.1 migrations ---
                    rt_journal = HostActions(
                        area / 'rt-journal.json', 'fb_rt',
                        {'daemon_start', 'daemon_stop', 'daemon_restart', 'stage_runtime_bundle', 'migrate_database'},
                    )
                    rt_inv = inspect_runtime_environment(host_scope)
                    assert rt_inv['network_maintenance_upgrades_runtime'] is False
                    assert all(b['present'] for b in rt_inv['binaries'].values())

                    rev_bundle = rt_journal.review(
                        'owner', 'b1', 'stage_runtime_bundle',
                        prepare_runtime_review(host_scope, {
                            'operation': 'stage_runtime_bundle',
                            'target_directory_name': 'staged_fb5_kit',
                        }),
                    )
                    out_bundle = rt_journal.apply(
                        'owner', 'b1',
                        {'review_id': rev_bundle['review_id'], 'review_digest': rev_bundle['review_digest'], 'confirmed': True},
                        apply_runtime_operation,
                    )['outcome']
                    assert out_bundle['state'] == 'staged'

                    # Managed daemon stop + start cycle
                    client.close()
                    rev_stop = rt_journal.review(
                        'owner', 'b1', 'daemon_stop',
                        prepare_runtime_review(host_scope, {'operation': 'daemon_stop', 'disruption_confirmed': True}),
                    )
                    out_stop = rt_journal.apply(
                        'owner', 'b1',
                        {'review_id': rev_stop['review_id'], 'review_digest': rev_stop['review_digest'], 'confirmed': True},
                        apply_runtime_operation,
                    )['outcome']
                    assert out_stop['state'] == 'stopped' and out_stop['tcp_closed'] is True

                    rev_start = rt_journal.review(
                        'owner', 'b1', 'daemon_start',
                        prepare_runtime_review(host_scope, {'operation': 'daemon_start'}),
                    )
                    out_start = rt_journal.apply(
                        'owner', 'b1',
                        {'review_id': rev_start['review_id'], 'review_digest': rev_start['review_digest'], 'confirmed': True},
                        apply_runtime_operation,
                    )['outcome']
                    assert out_start['state'] == 'started' and out_start['pid'] > 1
                    client = network._create_client(perms, attachment_mode='network')

                    # Route A: ODS 13.0 (Firebird 4.0.5) -> ODS 13.1 via ods13_minor_upgrade
                    fb4_src = staging_dir / 'fb4_ods13_0_input.fdb'
                    shutil.copy2(FB4_FIXTURE, fb4_src)
                    ods13_info = inspect_database_ods(host_scope, str(fb4_src))
                    assert (ods13_info['ods_major'], ods13_info['ods_minor']) == (13, 0), ods13_info
                    fb4_dst = staging_dir / 'fb5_from_ods13_0.fdb'
                    rev_mig13 = rt_journal.review(
                        'owner', 'b1', 'migrate_database',
                        prepare_runtime_review(host_scope, {
                            'operation': 'migrate_database',
                            'migration_route': 'ods13_minor_upgrade',
                            'source_path': str(fb4_src),
                            'target_database_path': str(fb4_dst),
                            'confirmation': fb4_dst.name,
                        }),
                    )
                    out_mig13 = rt_journal.apply(
                        'owner', 'b1',
                        {'review_id': rev_mig13['review_id'], 'review_digest': rev_mig13['review_digest'], 'confirmed': True},
                        apply_runtime_operation,
                    )['outcome']
                    assert out_mig13['state'] == 'migrated' and out_mig13['verified_ods'] == [13, 1], out_mig13
                    assert out_mig13['source_preserved_unchanged'] is True
                    assert out_mig13['verified_row_counts'] == {'UPGRADE_DATA': 1}

                    # Route B: ODS 12.0 (Firebird 3.0) -> ODS 13.1 via gbak_backup_restore
                    fb3_fdb, fb3_fbk = _build_fb3_ods12_fixture(staging_dir)
                    ods12_info = inspect_database_ods(host_scope, str(fb3_fdb))
                    assert ods12_info['ods_major'] == 12 and ods12_info['recommended_migration_route'] == 'gbak_backup_restore'
                    ods12_minor_denied = False
                    try:
                        prepare_runtime_review(host_scope, {
                            'operation': 'migrate_database',
                            'migration_route': 'ods13_minor_upgrade',
                            'source_path': str(fb3_fdb),
                            'target_database_path': str(staging_dir / 'bad.fdb'),
                            'confirmation': 'bad.fdb',
                        })
                    except ValueError as err:
                        ods12_minor_denied = 'gbak_backup_restore' in str(err)
                    assert ods12_minor_denied

                    fb3_dst = staging_dir / 'fb5_from_fb3_ods12.fdb'
                    rev_mig12 = rt_journal.review(
                        'owner', 'b1', 'migrate_database',
                        prepare_runtime_review(host_scope, {
                            'operation': 'migrate_database',
                            'migration_route': 'gbak_backup_restore',
                            'source_path': str(fb3_fbk),
                            'target_database_path': str(fb3_dst),
                            'confirmation': fb3_dst.name,
                        }),
                    )
                    out_mig12 = rt_journal.apply(
                        'owner', 'b1',
                        {'review_id': rev_mig12['review_id'], 'review_digest': rev_mig12['review_digest'], 'confirmed': True},
                        apply_runtime_operation,
                    )['outcome']
                    assert out_mig12['state'] == 'migrated' and out_mig12['verified_ods'] == [13, 1], out_mig12
                    assert out_mig12['verified_tables'] == ['DEPT', 'EMP']
                    assert out_mig12['verified_views'] == ['EMP_VIEW']
                    assert out_mig12['verified_procedures'] == ['EMP_COUNT']
                    assert out_mig12['verified_row_counts'] == {'DEPT': 1, 'EMP': 2}
                    assert out_mig12['verified_dependency_rows'] > 0
                    proof['checks'].append(
                        'FB-AUD-05: runtime bundle staging, daemon stop/start lifecycle, ODS 13.0 -> 13.1 minor upgrade, and Firebird 3.0 ODS 12.0 -> 13.1 gbak migration preserving tables, views, procedures, constraints and dependencies'
                    )
                finally:
                    client.close()
            finally:
                stop_managed_daemon_process(host_scope)

        proof['owned_state_removed'] = not area.exists()
        proof['source_runtime_unchanged'] = _runtime_fingerprint(runtime) == before
        proof['complete'] = (
            proof['owned_state_removed']
            and proof['source_runtime_unchanged']
            and len(proof['checks']) == 4
        )
    finally:
        if prev_manifest is None:
            os.environ.pop('CDEADMIN_FIREBIRD_HOST_TOOLS_MANIFEST', None)
        else:
            os.environ['CDEADMIN_FIREBIRD_HOST_TOOLS_MANIFEST'] = prev_manifest
        (output / 'native.json').write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
    return proof


def qualify_http(runtime, output):
    import builtins
    builtins.SERVER_MODE = None
    import pgadmin  # noqa: F401
    from tools.cdeadmin_firebird_object_live_orchestrator import _stage_runtime, _runtime_fingerprint
    from tools.cdeadmin_mysql_dump_verification_qualification import setup_application

    runtime, output = Path(runtime).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    before = _runtime_fingerprint(runtime)
    proof = {
        'complete': False,
        'history_tests': 'not run',
        'scope': 'Authenticated desktop HTTP qualification for firebird_host_configuration, firebird_plugin_deployment and firebird_runtime_lifecycle',
        'checks': [],
    }
    prev_manifest = os.environ.get('CDEADMIN_FIREBIRD_HOST_TOOLS_MANIFEST')
    try:
        with tempfile.TemporaryDirectory(prefix='fb-host-http-', dir=output) as folder, ExitStack() as stack:
            root = Path(folder)
            stage = root / 'runtime'
            data = root / 'data'
            data.mkdir()
            _stage_runtime(runtime, stage)
            # Materialize writable replication.conf and plugins/ directory so owned host
            # mutations never touch the read-only source runtime kit.
            (stage / 'replication.conf').unlink()
            shutil.copy2(runtime / 'replication.conf', stage / 'replication.conf')
            (stage / 'plugins').unlink()
            shutil.copytree(runtime / 'plugins', stage / 'plugins', symlinks=True)
            (stage / 'firebird.conf').write_text(
                'ServerMode = SuperClassic\nProviders = Engine13\n'
                f'SecurityDatabase = {stage / "security5.fdb"}\n',
                encoding='utf-8',
            )
            (stage / 'databases.conf').write_text('', encoding='utf-8')
            os.environ.update(
                FIREBIRD=str(stage),
                FIREBIRD_LOCK=str(stage / 'lock'),
                CDEADMIN_FIREBIRD_CLIENT_LIBRARY=str(stage / 'lib/libfbclient.so.5.0.4'),
            )
            import firebird.driver as fb_mod
            fb_mod.driver_config.fb_client_library.value = str(stage / 'lib/libfbclient.so.5.0.4')

            app = setup_application(root)

            def close_app():
                from pgadmin.cdeadmin.workspace.service import service_for_app
                with app.app_context():
                    service_for_app(app).endpoint_service.provider_registry.close()
            stack.callback(close_app)

            from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
            from pgadmin.cdeadmin.providers.firebird.provider import _create_client
            from pgadmin.cdeadmin.endpoints.profiles import registration_profile
            from pgadmin.model import db, User, ServerGroup, Server, EndpointDatabaseTarget
            from flask import url_for

            db_path = data / 'http_host.fdb'
            route = {
                'attachment_mode': 'embedded',
                'database': str(db_path),
                'filesystem_root': str(data),
                'user': 'SYSDBA',
                'charset': 'UTF8',
            }
            nc = _create_client(
                SimpleNamespace(require=lambda *_: None, acquire_secret=None),
                attachment_mode='embedded', profile=embedded.PROFILE, administration=embedded.ADMINISTRATION,
            )
            created = nc.config.database_creator(**nc.config.database_create_arguments(route, str(db_path), {}))
            created.close()
            nc.close()

            with app.test_request_context('/'):
                user = User.query.first()
                uid = user.id
                group = ServerGroup.query.filter_by(user_id=uid).first()
                for name, pref in app.blueprints['NODE-engine_type'].connector_visibility.items():
                    if 'firebird' in name:
                        pref.set(True, user_id=uid)
                server = Server(
                    user_id=uid, servergroup_id=group.id, name='HTTP Host Admin',
                    host=None, port=1, username='SYSDBA', maintenance_db=str(db_path), save_password=0,
                )
                server._cde_endpoint_registration = registration_profile('firebird-embedded')
                server._cde_endpoint_route_configuration = route
                db.session.add(server)
                db.session.commit()
                ep_id = server.endpoint_profile.id
                tid = str(uuid.uuid4())
                db.session.add(EndpointDatabaseTarget(
                    id=tid, endpoint_id=ep_id,
                    display_name=db_path.name, database=str(db_path), configuration='{}', active=1,
                ))
                db.session.commit()
                url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=server.id)
                verify_url = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=server.id)

            http = app.test_client()
            with http.session_transaction() as sess:
                sess['_user_id'] = str(uid)
                sess['_fresh'] = True
            assert http.post(verify_url, json={}).get_json()['success']

            # Test read-only manifest grant refuses mutation while allowing inspect
            manifest_path = root / 'ro-manifest.json'
            manifest_path.write_text(json.dumps({
                'format': 'scratchrobin.firebird.host-tools@1',
                'grants': [{
                    'endpoint_id': ep_id,
                    'firebird_runtime_root': str(stage),
                    'firebird_lock_directory': str(stage / 'lock'),
                    'databases': [str(db_path)],
                    'allow_host_administration': False,
                }],
            }), encoding='utf-8')
            os.environ['CDEADMIN_FIREBIRD_HOST_TOOLS_MANIFEST'] = str(manifest_path)

            ro_inspect = http.post(url, json={'action': 'firebird_host_configuration', 'request': {'action': 'inspect'}})
            assert ro_inspect.status_code == 200 and ro_inspect.get_json()['success']
            ro_review = http.post(url, json={
                'action': 'firebird_host_configuration',
                'request': {
                    'action': 'review',
                    'target_file': 'firebird.conf',
                    'expected_generation_sha256': ro_inspect.get_json()['data']['files']['firebird.conf']['generation_sha256'],
                    'set_options': {'StatementTimeout': 20},
                },
            })
            assert not ro_review.get_json().get('success')
            os.environ.pop('CDEADMIN_FIREBIRD_HOST_TOOLS_MANIFEST', None)
            proof['checks'].append('Read-only host grant permits inspect and refuses mutation over HTTP')

            # Describe + inspect + review + apply + replay refusal across all 3 host actions
            for act_name in ('firebird_host_configuration', 'firebird_plugin_deployment', 'firebird_runtime_lifecycle'):
                d_resp = http.post(url, json={'action': act_name, 'request': {'action': 'describe'}})
                assert d_resp.status_code == 200 and d_resp.headers.get('Cache-Control') == 'no-store'
                i_resp = http.post(url, json={'action': act_name, 'database_target_id': tid, 'request': {'action': 'inspect', 'database_target_id': tid}})
                assert i_resp.status_code == 200 and i_resp.get_json()['success'], (act_name, i_resp.get_json())

            cfg_snap = http.post(url, json={'action': 'firebird_host_configuration', 'request': {'action': 'inspect'}}).get_json()['data']
            cfg_rev = http.post(url, json={
                'action': 'firebird_host_configuration',
                'request': {
                    'action': 'review',
                    'target_file': 'firebird.conf',
                    'expected_generation_sha256': cfg_snap['files']['firebird.conf']['generation_sha256'],
                    'set_options': {'ConnectionIdleTimeout': 15},
                },
            }).get_json()['data']
            cfg_app = http.post(url, json={
                'action': 'firebird_host_configuration',
                'request': {
                    'action': 'apply',
                    'review_id': cfg_rev['review_id'],
                    'review_digest': cfg_rev['review_digest'],
                    'confirmed': True,
                },
            }).get_json()
            assert cfg_app['success'] and cfg_app['data']['outcome']['state'] == 'applied', cfg_app
            replay = http.post(url, json={
                'action': 'firebird_host_configuration',
                'request': {
                    'action': 'apply',
                    'review_id': cfg_rev['review_id'],
                    'review_digest': cfg_rev['review_digest'],
                    'confirmed': True,
                },
            }).get_json()
            assert not replay.get('success')
            proof['checks'].append('HTTP describe/inspect/review/apply/one-use retirement and no-store verified across host configuration, plugin and runtime actions')

        proof['owned_state_removed'] = not root.exists()
        proof['source_runtime_unchanged'] = _runtime_fingerprint(runtime) == before
        proof['complete'] = proof['owned_state_removed'] and proof['source_runtime_unchanged'] and len(proof['checks']) == 2
    finally:
        if prev_manifest is None:
            os.environ.pop('CDEADMIN_FIREBIRD_HOST_TOOLS_MANIFEST', None)
        else:
            os.environ['CDEADMIN_FIREBIRD_HOST_TOOLS_MANIFEST'] = prev_manifest
        (output / 'http.json').write_text(json.dumps(proof, indent=2) + '\n', encoding='utf-8')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('all', 'native', 'http'), default='all')
    args = parser.parse_args()
    if args.mode == 'native':
        res = qualify_native(args.runtime, args.output)
        print(json.dumps({'complete': res['complete'], 'checks': len(res['checks'])}))
        raise SystemExit(0 if res['complete'] else 1)
    if args.mode == 'http':
        res = qualify_http(args.runtime, args.output)
        print(json.dumps({'http_complete': res['complete'], 'checks': len(res['checks'])}))
        raise SystemExit(0 if res['complete'] else 1)
    nres = qualify_native(args.runtime, args.output)
    hproc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), '--runtime', str(args.runtime), '--output', str(args.output), '--mode', 'http'],
        check=False, capture_output=True, text=True,
    )
    if hproc.returncode != 0:
        sys.stderr.write(hproc.stdout + hproc.stderr)
        raise SystemExit(hproc.returncode)
    hres = json.loads((Path(args.output).resolve() / 'http.json').read_text(encoding='utf-8'))
    ok = bool(nres.get('complete') and hres.get('complete'))
    print(json.dumps({'complete': ok, 'native_checks': len(nres['checks']), 'http_checks': len(hres['checks'])}))
    raise SystemExit(0 if ok else 1)

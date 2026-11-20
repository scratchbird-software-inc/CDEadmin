#!/usr/bin/env python3
"""End-to-end live native + authenticated HTTP qualification for MariaDB Batch 6 (all 7 items):
1. MA-AUDIT-PHYSICAL-BACKUP
2. MA-AUDIT-INCREMENTAL-PREPARE
3. MA-AUDIT-RECOVERY-CUTOVER
4. MA-AUDIT-ARCHIVE-RECOVERY-RETENTION
5. MA-AUDIT-HOST-CONFIG-SERVICE
6. MA-AUDIT-HOST-UPGRADE (mariadb:11.8 -> mariadb:12.2.2)
7. MA-AUDIT-GALERA (2-node mariadb:12.2.2 Galera cluster on owned Docker bridge network)
"""
import argparse
import builtins
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _docker(args, *, check=True, timeout=180):
    env = {**os.environ, 'DOCKER_CONTEXT': os.environ.get('DOCKER_CONTEXT', 'desktop-linux')}
    res = subprocess.run(['docker', *args], capture_output=True, text=True, timeout=timeout, env=env, check=False)
    if check and res.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args)} failed (rc={res.returncode}): {res.stderr.strip()}")
    return res


def _stage_mariadb_runtime(image: str, dest: Path):
    """Extract MariaDB server & client binaries, share scripts, plugins & Galera provider from image."""
    dest.mkdir(parents=True, exist_ok=True)
    script = (
        'set -e\n'
        'mkdir -p /out/usr/bin /out/usr/sbin /out/usr/share /out/usr/lib/mysql /out/usr/lib/galera\n'
        'for f in /usr/bin/mariad* /usr/bin/mysql* /usr/bin/my_print_defaults /usr/bin/my_* /usr/bin/resolveip /usr/bin/wsrep_sst_*; do\n'
        '  [ -e "$f" ] && cp -L "$f" /out/usr/bin/ || true\n'
        'done\n'
        'cp -L /usr/sbin/mariadbd /out/usr/sbin/mariadbd\n'
        '[ -d /usr/share/mariadb ] && cp -r /usr/share/mariadb /out/usr/share/mariadb || true\n'
        '[ -d /usr/share/mysql ] && cp -r /usr/share/mysql /out/usr/share/mysql || true\n'
        'if [ -d /out/usr/share/mariadb ] && [ ! -e /out/usr/share/mysql ]; then\n'
        '  ln -s mariadb /out/usr/share/mysql\n'
        'fi\n'
        '[ -d /usr/lib/mysql/plugin ] && cp -r /usr/lib/mysql/plugin /out/usr/lib/mysql/plugin || true\n'
        '[ -e /usr/lib/galera/libgalera_smm.so ] && cp -L /usr/lib/galera/libgalera_smm.so /out/usr/lib/galera/libgalera_smm.so || true\n'
    )
    _docker(['run', '--rm', '-v', f'{dest}:/out', image, 'bash', '-c', script], timeout=180)
    share_dir = dest / 'usr/share/mariadb' if (dest / 'usr/share/mariadb').is_dir() else dest / 'usr/share/mysql'
    return {
        'basedir': str(dest / 'usr'),
        'mariadbd': str(dest / 'usr/sbin/mariadbd'),
        'mariadb': str(dest / 'usr/bin/mariadb'),
        'mariadb_binlog': str(dest / 'usr/bin/mariadb-binlog'),
        'mariadb_backup': str(dest / 'usr/bin/mariadb-backup'),
        'mariadb_upgrade': str(dest / 'usr/bin/mariadb-upgrade'),
        'mariadb_install_db': str(dest / 'usr/bin/mariadb-install-db'),
        'lc_messages_dir': str(share_dir),
        'plugin_dir': str(dest / 'usr/lib/mysql/plugin'),
        'galera_provider': str(dest / 'usr/lib/galera/libgalera_smm.so'),
    }


def _setup_flask_app(app_root: Path, bins_1222: dict):
    app_root.mkdir(parents=True, exist_ok=True)
    os.environ['CDEADMIN_MARIADB_BINLOG_BINARY'] = bins_1222['mariadb_binlog']
    os.environ['CDEADMIN_MARIADB_BACKUP_BINARY'] = bins_1222['mariadb_backup']
    os.environ['CDEADMIN_MARIADB_CLIENT_BINARY'] = bins_1222['mariadb']
    os.environ['CDEADMIN_MARIADB_UPGRADE_BINARY'] = bins_1222['mariadb_upgrade']
    os.environ['CDEADMIN_MARIADBD_BINARY'] = bins_1222['mariadbd']
    os.environ['CDEADMIN_MARIADB_INSTALL_DB_BINARY'] = bins_1222['mariadb_install_db']

    builtins.SERVER_MODE = None
    import config
    config.SERVER_MODE = False
    config.TESTING = True
    config.WTF_CSRF_ENABLED = False
    config.MASTER_PASSWORD_REQUIRED = False
    config.USE_OS_SECRET_STORAGE = False
    config.DATA_DIR = str(app_root / 'data')
    config.SQLITE_PATH = str(app_root / 'data/app.db')
    config.SESSION_DB_PATH = str(app_root / 'data/sessions')
    config.STORAGE_DIR = str(app_root / 'data/storage')
    config.LOG_FILE = str(app_root / 'data/app.log')
    config.AZURE_CREDENTIAL_CACHE_DIR = str(app_root / 'data/azure')
    config.KERBEROS_CCACHE_DIR = str(app_root / 'data/kerberos')
    config.CDEADMIN_OPERATION_STORE_PATH = str(app_root / 'data/operations.json')
    config.CDEADMIN_MARIADB_BINLOG_ROOT = str(app_root / 'binlog-archives')
    config.CDEADMIN_MARIADB_CONTINUOUS_BINLOG_ROOT = str(app_root / 'binlog-receivers')
    config.CDEADMIN_MARIADB_BINLOG_REPLAY_ROOT = str(app_root / 'binlog-replays')
    config.CDEADMIN_MARIADB_PHYSICAL_ROOT = str(app_root / 'physical-jobs')
    config.CDEADMIN_MARIADB_BACKUP_PROTECTION_ROOT = str(app_root / 'backup-protection')
    config.CDEADMIN_MARIADB_HOST_ROOT = str(app_root / 'host-jobs')
    config.CDEADMIN_MARIADB_UPGRADE_ROOT = str(app_root / 'upgrade-jobs')
    config.CDEADMIN_MARIADB_GALERA_ROOT = str(app_root / 'galera-jobs')

    from pgadmin import create_app
    app = create_app('ScratchRobin-MariaDB-Batch6-Qualification')
    app.PGADMIN_RUNTIME = False
    app.PGADMIN_INT_KEY = ''
    app.run_before_app_start()
    return app


def _register_mariadb_endpoint(app, client, *, name, host, port, user, password, tool_workspace=None):
    from flask import url_for
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.model import Server, ServerGroup, User, db

    with app.test_request_context('/'):
        u = User.query.first()
        uid = u.id
        group = ServerGroup.query.filter_by(user_id=uid).order_by(ServerGroup.id).first()
        app.blueprints['NODE-engine_type'].connector_visibility['mariadb'].set(True, user_id=uid)
        srv = Server(
            user_id=uid, servergroup_id=group.id, name=name,
            host=host, port=int(port), username=user,
            maintenance_db=None, save_password=0,
        )
        srv._cde_endpoint_registration = registration_profile('mariadb-native')
        rcfg = {
            'host': host, 'port': int(port), 'user': user,
            'ssl': False, 'ssl_verify_cert': False,
            'credential_kinds': ['database_password'],
        }
        if tool_workspace:
            rcfg['tool_workspace'] = str(tool_workspace)
        srv._cde_endpoint_route_configuration = rcfg
        db.session.add(srv)
        db.session.commit()
        sid = srv.id
        verify_url = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=sid)
        ws_url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=sid)

    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)
        sess['_fresh'] = True
    vresp = client.post(verify_url, json={'password': password}).get_json()
    assert vresp and vresp.get('success'), f'Endpoint verification failed for {name}: {vresp}'
    return sid, verify_url, ws_url


def _post_ws(client, ws_url, action, req_body, *, expect_refusal=False):
    resp = client.post(ws_url, json={'action': action, 'request': req_body})
    payload = resp.get_json()
    if expect_refusal:
        assert resp.status_code == 400 and not payload.get('success'), (
            f'Expected 400 refusal for {action}, got status={resp.status_code} payload={payload}'
        )
        return payload
    assert resp.status_code == 200 and payload.get('success'), (
        f'HTTP workspace {action} failed (status={resp.status_code}): {payload}'
    )
    assert resp.headers.get('Cache-Control') == 'no-store'
    return payload['data']


def qualify_continuity_and_host(app, client, scratch: Path, output: Path, bins: dict):
    """Qualify Items 1, 2, 3, 4, and 5 against real local MariaDB 12.2.2 daemons & tools."""
    import mariadb

    host_dir = scratch / 'primary-host'
    etc_dir = host_dir / 'etc'
    confd_dir = etc_dir / 'mariadb.conf.d'
    confd_dir.mkdir(parents=True, mode=0o700)
    primary_datadir = host_dir / 'datadir'
    daemon_state = host_dir / 'daemon-state'
    primary_port = _free_port()
    admin_pw = 'SrBatch6#' + secrets.token_urlsafe(18)

    my_cnf = etc_dir / 'my.cnf'
    srv_cnf = confd_dir / '50-server.cnf'
    my_cnf.write_text(f'[client-server]\nport = {primary_port}\n!includedir {confd_dir}\n', encoding='utf-8')
    srv_cnf.write_text(
        '[mysqld]\n'
        'max_connections = 150\n'
        'server_id = 173\n'
        'log_bin = sr-owned\n'
        'gtid_strict_mode = ON\n'
        'binlog_format = ROW\n',
        encoding='utf-8',
    )

    # Bootstrap initial datadir & start primary via mariadb_host_services so we can register it
    from pgadmin.cdeadmin.providers.mysql_family import mariadb_host_services
    init_res = mariadb_host_services.initialize_datadir(
        install_db_binary=bins['mariadb_install_db'],
        mariadbd_binary=bins['mariadbd'],
        datadir=primary_datadir,
        job_dir=host_dir / 'init-job',
        auth_root_method='normal',
        basedir=bins['basedir'],
        version_prefix='12.2.2',
    )
    started_primary = mariadb_host_services.control_managed_service(
        action='start',
        service_mode='managed_daemon',
        state_dir=daemon_state,
        mariadbd_binary=bins['mariadbd'],
        defaults_file=my_cnf,
        datadir=primary_datadir,
        port=primary_port,
        basedir=bins['basedir'],
        plugin_dir=bins['plugin_dir'],
        lc_messages_dir=bins['lc_messages_dir'],
        version_prefix='12.2.2',
    )
    recovery_ports_to_stop = []
    try:
        mariadb_host_services.verify_sql_readiness(
            host='127.0.0.1', port=primary_port, db_user='root', db_password='', expected_datadir=primary_datadir
        )
        root_conn = mariadb.connect(host='127.0.0.1', port=primary_port, user='root', autocommit=True)
        try:
            cur = root_conn.cursor()
            cur.execute("CREATE USER 'sr_admin'@'127.0.0.1' IDENTIFIED BY ?", (admin_pw,))
            cur.execute("GRANT ALL PRIVILEGES ON *.* TO 'sr_admin'@'127.0.0.1' WITH GRANT OPTION")
            cur.execute("CREATE USER 'sr_app_reader'@'127.0.0.1' IDENTIFIED BY ?", ('ReaderPw!' + secrets.token_hex(6),))
            cur.execute('CREATE DATABASE sr_continuity CHARACTER SET utf8mb4')
            cur.execute("GRANT SELECT ON sr_continuity.* TO 'sr_app_reader'@'127.0.0.1'")
            cur.execute(
                'CREATE TABLE sr_continuity.orders ('
                'id BIGINT PRIMARY KEY, customer VARCHAR(80) NOT NULL, payload LONGBLOB'
                ') ENGINE=InnoDB'
            )
            cur.execute(
                'CREATE TABLE sr_continuity.audit_notes ('
                'note_id INT PRIMARY KEY, body VARCHAR(120)'
                ') ENGINE=Aria'
            )
            cur.execute('CREATE VIEW sr_continuity.v_orders AS SELECT id, customer FROM sr_continuity.orders')
            cur.execute(
                'CREATE PROCEDURE sr_continuity.sp_order_total(OUT cnt INT) '
                'BEGIN SELECT COUNT(*) INTO cnt FROM sr_continuity.orders; END'
            )
            cur.execute("INSERT INTO sr_continuity.orders VALUES (1, 'Ada 東京', ?), (2, 'Grace 🚀', ?)", (b'\x00\x01', b'\xfe\xff'))
            cur.execute("INSERT INTO sr_continuity.audit_notes VALUES (10, 'initial seed')")
            cur.execute('FLUSH BINARY LOGS')
            cur.close()
        finally:
            root_conn.close()

        sid, verify_url, ws_url = _register_mariadb_endpoint(
            app, client,
            name='Owned MariaDB 12.2.2 Primary',
            host='127.0.0.1', port=primary_port,
            user='sr_admin', password=admin_pw,
            tool_workspace=scratch / 'tool-ws',
        )

        # Archive closed log #1 (strictly older than physical backup we are about to take!)
        cat1 = _post_ws(client, ws_url, 'mariadb_binlog_catalog', {})
        closed1 = [r['Log_name'] for r in cat1['logs'] if r['closed']]
        assert closed1, cat1
        arch1_rev = _post_ws(client, ws_url, 'mariadb_binlog_review', {'options': {'log_names': [closed1[0]]}})
        arch1 = _post_ws(client, ws_url, 'mariadb_binlog_start', {
            'job_id': arch1_rev['job_id'], 'review_digest': arch1_rev['review_digest'], 'confirmed': True,
        })
        deadline = time.monotonic() + 30
        while arch1['state'] in {'dispatching', 'active'}:
            assert time.monotonic() < deadline
            time.sleep(0.1)
            arch1 = _post_ws(client, ws_url, 'mariadb_binlog_status', {'job_id': arch1['job_id']})
        assert arch1['state'] == 'completed'

        # =====================================================================
        # ITEM 5: MA-AUDIT-HOST-CONFIG-SERVICE (via authenticated HTTP!)
        # =====================================================================
        cfg_graph = _post_ws(client, ws_url, 'mariadb_host_inspect_config', {'configuration_file': str(my_cnf)})
        assert cfg_graph['file_count'] == 2

        invalid_cnf = host_dir / 'invalid-candidate.cnf'
        invalid_cnf.write_text('[mysqld]\nnonexistent_mariadb_bogus_setting = 999\n', encoding='utf-8')
        invalid_val = _post_ws(client, ws_url, 'mariadb_host_validate_config', {
            'configuration_file': str(invalid_cnf),
            'basedir': bins['basedir'],
            'lc_messages_dir': bins['lc_messages_dir'],
        })
        assert invalid_val['valid'] is False and invalid_val['server_started'] is False

        # Refusal of invalid config during review
        _post_ws(client, ws_url, 'mariadb_host_review', {
            'options': {
                'operation': 'deploy_config',
                'configuration_file': str(srv_cnf),
                'replacement_text': '[mysqld]\nnonexistent_mariadb_bogus_setting = 999\n',
                'basedir': bins['basedir'],
                'lc_messages_dir': bins['lc_messages_dir'],
            }
        }, expect_refusal=True)

        # Atomic deployment of valid 50-server.cnf (max_connections = 321)
        new_srv_cnf_text = (
            '[mysqld]\n'
            'max_connections = 321\n'
            'server_id = 173\n'
            'log_bin = sr-owned\n'
            'gtid_strict_mode = ON\n'
            'binlog_format = ROW\n'
        )
        dep_rev = _post_ws(client, ws_url, 'mariadb_host_review', {
            'options': {
                'operation': 'deploy_config',
                'configuration_file': str(srv_cnf),
                'replacement_text': new_srv_cnf_text,
                'basedir': bins['basedir'],
                'lc_messages_dir': bins['lc_messages_dir'],
            }
        })
        dep_done = _post_ws(client, ws_url, 'mariadb_host_start', {
            'job_id': dep_rev['job_id'], 'review_digest': dep_rev['review_digest'], 'confirmed': True,
        })
        assert dep_done['state'] == 'completed'
        assert dep_done['result']['restart_issued'] is False
        assert Path(dep_done['result']['backup_path']).is_file()

        # Restart managed daemon via HTTP & independently verify SQL readiness + max_connections=321
        rst_rev = _post_ws(client, ws_url, 'mariadb_host_review', {
            'options': {
                'operation': 'service_restart',
                'service_mode': 'managed_daemon',
                'state_dir': str(daemon_state),
                'configuration_file': str(my_cnf),
                'datadir': str(primary_datadir),
                'port': primary_port,
                'basedir': bins['basedir'],
                'plugin_dir': bins['plugin_dir'],
                'lc_messages_dir': bins['lc_messages_dir'],
                'disconnect_all_clients': True,
            }
        })
        rst_done = _post_ws(client, ws_url, 'mariadb_host_start', {
            'job_id': rst_rev['job_id'], 'review_digest': rst_rev['review_digest'], 'confirmed': True,
        })
        assert rst_done['result']['sql_readiness_verified'] is True

        # Boot policy toggle + initialize_data check via HTTP
        bp_rev = _post_ws(client, ws_url, 'mariadb_host_review', {
            'options': {
                'operation': 'service_boot_policy',
                'service_mode': 'managed_daemon',
                'state_dir': str(daemon_state),
                'boot_enabled': True,
            }
        })
        bp_done = _post_ws(client, ws_url, 'mariadb_host_start', {
            'job_id': bp_rev['job_id'], 'review_digest': bp_rev['review_digest'], 'confirmed': True,
        })
        assert bp_done['result']['boot_policy'] == 'enabled'

        fresh_ddir = scratch / 'host-init-fresh-datadir'
        init_http_rev = _post_ws(client, ws_url, 'mariadb_host_review', {
            'options': {
                'operation': 'initialize_data',
                'datadir': str(fresh_ddir),
                'basedir': bins['basedir'],
                'auth_root_method': 'normal',
            }
        })
        init_http_done = _post_ws(client, ws_url, 'mariadb_host_start', {
            'job_id': init_http_rev['job_id'], 'review_digest': init_http_rev['review_digest'], 'confirmed': True,
        })
        assert init_http_done['result']['initialized'] is True and (fresh_ddir / 'mysql').is_dir()

        chk_conn = mariadb.connect(host='127.0.0.1', port=primary_port, user='sr_admin', password=admin_pw, autocommit=True)
        try:
            c = chk_conn.cursor()
            c.execute('SELECT @@global.max_connections')
            observed_max_conn = int(c.fetchone()[0])
            c.close()
        finally:
            chk_conn.close()
        assert observed_max_conn == 321

        # Rollback option file via HTTP & verify original restored
        rb_cfg = _post_ws(client, ws_url, 'mariadb_host_rollback_config', {
            'job_id': dep_rev['job_id'], 'confirmed': True,
        })
        assert rb_cfg['rollback_result']['rolled_back'] is True

        (output / 'host-config-service.json').write_text(json.dumps({
            'item': 'MA-AUDIT-HOST-CONFIG-SERVICE',
            'complete': True,
            'config_graph_file_count': cfg_graph['file_count'],
            'invalid_config_rejected_without_server_start': invalid_val,
            'atomic_config_deploy_job': dep_done['job_id'],
            'observed_max_connections_after_restart': observed_max_conn,
            'boot_policy': bp_done['result']['boot_policy'],
            'datadir_initialization': init_http_done['result']['initialized'],
            'atomic_config_rollback': rb_cfg['rollback_result'],
        }, indent=2) + '\n')

        # =====================================================================
        # ITEM 1: MA-AUDIT-PHYSICAL-BACKUP (via authenticated HTTP!)
        # =====================================================================
        # Flush InnoDB pages so LSN boundaries advance deterministically across full -> inc1 -> inc2
        w_conn = mariadb.connect(host='127.0.0.1', port=primary_port, user='sr_admin', password=admin_pw, autocommit=True)
        try:
            cur = w_conn.cursor()
            cur.execute('SET GLOBAL innodb_max_dirty_pages_pct_lwm=0')
            cur.execute('SET GLOBAL innodb_max_dirty_pages_pct=0')
            time.sleep(0.5)

            src_inspect = _post_ws(client, ws_url, 'mariadb_physical_inspect', {})
            full_rev = _post_ws(client, ws_url, 'mariadb_physical_review', {
                'options': {'phase': 'backup', 'parallel': 2, 'timeout_seconds': 300}
            })
            assert full_rev['dispatch_state'] == 'not_dispatched'
            assert full_rev['acknowledgement_state'] == 'unacknowledged'
            assert full_rev['artifact_adoption_state'] == 'unverified'

            full_job = _post_ws(client, ws_url, 'mariadb_physical_start', {
                'job_id': full_rev['job_id'], 'review_digest': full_rev['review_digest'], 'confirmed': True,
            })
            assert full_job['state'] == 'completed'
            assert full_job['dispatch_state'] == 'dispatched'
            assert full_job['acknowledgement_state'] == 'native_acknowledged'
            assert full_job['artifact_adoption_state'] == 'artifact_adopted'
            full_art = full_job['result']['artifact']
            assert full_art['from_lsn'] == '0'
            assert int(full_art['to_lsn']) > 0

            (output / 'physical-backup.json').write_text(json.dumps({
                'item': 'MA-AUDIT-PHYSICAL-BACKUP',
                'complete': True,
                'source_identity': src_inspect['identity'],
                'full_backup_job_id': full_job['job_id'],
                'dispatch_state': full_job['dispatch_state'],
                'acknowledgement_state': full_job['acknowledgement_state'],
                'artifact_adoption_state': full_job['artifact_adoption_state'],
                'checkpoints': full_art['checkpoints'],
                'binlog_info': full_art['binlog_info'],
                'manifest_sha256': full_art['manifest_sha256'],
                'credential_cleanup_confirmed': full_job['result']['process_observation']['credential_cleanup_confirmed'],
            }, indent=2) + '\n')

            # =================================================================
            # ITEM 2: MA-AUDIT-INCREMENTAL-PREPARE (via authenticated HTTP!)
            # =================================================================
            cur.execute("INSERT INTO sr_continuity.orders VALUES (3, 'Linus Torvalds', ?), (4, 'Monty Widenius', ?)", (b'inc1a', b'inc1b'))
            time.sleep(0.6)

            inc1_rev = _post_ws(client, ws_url, 'mariadb_physical_review', {
                'options': {
                    'phase': 'incremental',
                    'parent_job_id': full_job['job_id'],
                    'incremental_mode': 'basedir',
                }
            })
            inc1_job = _post_ws(client, ws_url, 'mariadb_physical_start', {
                'job_id': inc1_rev['job_id'], 'review_digest': inc1_rev['review_digest'], 'confirmed': True,
            })
            assert inc1_job['state'] == 'completed'
            inc1_art = inc1_job['result']['artifact']
            assert inc1_art['from_lsn'] == full_art['to_lsn']

            cur.execute("INSERT INTO sr_continuity.orders VALUES (5, 'Barbara Liskov', ?)", (b'inc2',))
            time.sleep(0.6)

            inc2_rev = _post_ws(client, ws_url, 'mariadb_physical_review', {
                'options': {
                    'phase': 'incremental',
                    'parent_job_id': inc1_job['job_id'],
                    'incremental_mode': 'lsn',
                }
            })
            inc2_job = _post_ws(client, ws_url, 'mariadb_physical_start', {
                'job_id': inc2_rev['job_id'], 'review_digest': inc2_rev['review_digest'], 'confirmed': True,
            })
            assert inc2_job['state'] == 'completed'
            inc2_art = inc2_job['result']['artifact']
            assert inc2_art['from_lsn'] == inc1_art['to_lsn']

            # Test interrupted prepare + reconciliation (verifying immutable base + inc1 + inc2 stay untouched!)
            int_prep_rev = _post_ws(client, ws_url, 'mariadb_physical_review', {
                'options': {
                    'phase': 'prepare',
                    'base_job_id': full_job['job_id'],
                    'incremental_job_ids': [inc1_job['job_id'], inc2_job['job_id']],
                    '_simulate_interrupt_after_step': 'preparing_base',
                }
            })
            int_prep_job = _post_ws(client, ws_url, 'mariadb_physical_start', {
                'job_id': int_prep_rev['job_id'], 'review_digest': int_prep_rev['review_digest'], 'confirmed': True,
            })
            assert int_prep_job['state'] == 'cancelled'
            int_recon = _post_ws(client, ws_url, 'mariadb_physical_reconcile', {
                'job_id': int_prep_job['job_id'], 'confirmed': True,
            })
            assert int_recon['reconciliation']['immutable_inputs_intact'] is True
            assert int_recon['reconciliation']['usable_for_recovery'] is False

            # Now run complete staged prepare!
            prep_rev = _post_ws(client, ws_url, 'mariadb_physical_review', {
                'options': {
                    'phase': 'prepare',
                    'base_job_id': full_job['job_id'],
                    'incremental_job_ids': [inc1_job['job_id'], inc2_job['job_id']],
                }
            })
            prep_job = _post_ws(client, ws_url, 'mariadb_physical_start', {
                'job_id': prep_rev['job_id'], 'review_digest': prep_rev['review_digest'], 'confirmed': True,
            })
            assert prep_job['state'] == 'completed'
            assert prep_job['result']['immutable_inputs_verified_unchanged'] is True
            assert prep_job['result']['lsn_advancement']['advanced'] is True
            prep_art = prep_job['result']['artifact']
            assert prep_art['prepared'] is True

            (output / 'incremental-prepare.json').write_text(json.dumps({
                'item': 'MA-AUDIT-INCREMENTAL-PREPARE',
                'complete': True,
                'full_to_lsn': full_art['to_lsn'],
                'inc1_lsn': {'from_lsn': inc1_art['from_lsn'], 'to_lsn': inc1_art['to_lsn'], 'last_lsn': inc1_art['last_lsn']},
                'inc2_lsn': {'from_lsn': inc2_art['from_lsn'], 'to_lsn': inc2_art['to_lsn'], 'last_lsn': inc2_art['last_lsn']},
                'interrupted_prepare_reconciliation': int_recon['reconciliation'],
                'prepared_job_id': prep_job['job_id'],
                'lsn_advancement': prep_job['result']['lsn_advancement'],
                'immutable_inputs_verified_unchanged': prep_job['result']['immutable_inputs_verified_unchanged'],
            }, indent=2) + '\n')

            # =================================================================
            # ITEM 4: MA-AUDIT-ARCHIVE-RECOVERY-RETENTION (via HTTP!)
            # =================================================================
            # Write PITR row id=6 (wanted) and row id=7 (unwanted post-target), then rotate logs!
            cur.execute("INSERT INTO sr_continuity.orders VALUES (6, 'PITR Target Row', ?)", (b'pitr_keep',))
            cur.execute('SELECT @@global.gtid_binlog_pos')
            good_gtid = cur.fetchone()[0]
            cur.execute("INSERT INTO sr_continuity.orders VALUES (7, 'Accidental Post-PITR Row', ?)", (b'pitr_omit',))
            cur.execute('FLUSH BINARY LOGS')

            # Archive closed logs covering full..inc2..PITR
            cat2 = _post_ws(client, ws_url, 'mariadb_binlog_catalog', {})
            post_backup_logs = [r['Log_name'] for r in cat2['logs'] if r['closed'] and r['Log_name'] > closed1[0]]
            arch2_rev = _post_ws(client, ws_url, 'mariadb_binlog_review', {'options': {'log_names': post_backup_logs}})
            arch2 = _post_ws(client, ws_url, 'mariadb_binlog_start', {
                'job_id': arch2_rev['job_id'], 'review_digest': arch2_rev['review_digest'], 'confirmed': True,
            })
            while arch2['state'] in {'dispatching', 'active'}:
                time.sleep(0.1)
                arch2 = _post_ws(client, ws_url, 'mariadb_binlog_status', {'job_id': arch2['job_id']})
            assert arch2['state'] == 'completed'

            # Start continuous MariaDB binlog receiver, rotate log so it seals a snapshot with source_successor,
            # cancel receiver, and test checkpoint_catalog + checkpoint_inspect + recover_job_id!
            cap_cat = _post_ws(client, ws_url, 'mariadb_binlog_capture_catalog', {})
            open_log = cap_cat['current']['File']
            cap_rev = _post_ws(client, ws_url, 'mariadb_binlog_capture_review', {
                'options': {'start_file': open_log, 'receiver_server_id': 91731, 'timeout_seconds': 60}
            })
            cap_job = _post_ws(client, ws_url, 'mariadb_binlog_capture_start', {
                'job_id': cap_rev['job_id'], 'review_digest': cap_rev['review_digest'], 'confirmed': True,
            })
            time.sleep(0.5)
            cur.execute("INSERT INTO sr_continuity.audit_notes VALUES (11, 'receiver event')")
            cur.execute('FLUSH BINARY LOGS')
            deadline_cap = time.monotonic() + 20
            while time.monotonic() < deadline_cap:
                cap_st = _post_ws(client, ws_url, 'mariadb_binlog_capture_status', {'job_id': cap_job['job_id']})
                if (cap_st.get('progress') or {}).get('published_batches', 0) >= 1:
                    break
                time.sleep(0.3)
            _post_ws(client, ws_url, 'mariadb_binlog_capture_cancel', {'job_id': cap_job['job_id']})
            while True:
                cap_st = _post_ws(client, ws_url, 'mariadb_binlog_capture_status', {'job_id': cap_job['job_id']})
                if cap_st['state'] in {'cancelled', 'captured', 'failed'}:
                    break
                time.sleep(0.1)
            _post_ws(client, ws_url, 'mariadb_binlog_capture_reconcile_writer', {
                'job_id': cap_job['job_id'], 'confirmed': True,
            })
            cp_cat = _post_ws(client, ws_url, 'mariadb_binlog_capture_checkpoint_catalog', {'job_id': cap_job['job_id']})
            assert cp_cat['archives'], cp_cat
            cp_arch_id = cp_cat['archives'][0]['job_id']
            cp_insp = _post_ws(client, ws_url, 'mariadb_binlog_capture_checkpoint_inspect', {
                'job_id': cap_job['job_id'], 'archive_job_id': cp_arch_id,
            })
            rec_cap_rev = _post_ws(client, ws_url, 'mariadb_binlog_capture_review', {
                'options': {
                    'start_file': cp_insp['checkpoint']['next_file'],
                    'receiver_server_id': 91732,
                    'timeout_seconds': 30,
                },
                'recover_job_id': cap_job['job_id'],
                'archive_job_id': cp_arch_id,
                'acknowledge_archive_checkpoint': True,
            })
            _post_ws(client, ws_url, 'mariadb_binlog_capture_cancel', {'job_id': rec_cap_rev['job_id']})

            # Evaluate dependency-aware retention!
            # arch2 MUST be protected by unretired physical backup chain; attempting remove_artifact MUST fail (400)!
            _post_ws(client, ws_url, 'mariadb_binlog_remove_artifact', {
                'job_id': arch2['job_id'], 'confirmation': arch2['job_id'],
            }, expect_refusal=True)

            # Record an uncertain hold -> arch1 MUST ALSO be protected while uncertain hold is active!
            uncertain_hold = _post_ws(client, ws_url, 'mariadb_binlog_hold_record_uncertain', {
                'origin_operation': 'mariadb_binlog_replay',
                'origin_job_id': str(uuid.uuid4()),
                'source_uid': src_inspect['identity']['server_uid'],
                'uncertainty_reason': 'Simulated unconfirmed replay client exit',
            })
            eval_with_uncertain = _post_ws(client, ws_url, 'mariadb_binlog_retention_evaluate', {
                'policy': {'retention_days': 0, 'keep_latest': 1}
            })
            assert eval_with_uncertain['summary']['protected_by_uncertain_hold'] >= 2
            _post_ws(client, ws_url, 'mariadb_binlog_remove_artifact', {
                'job_id': arch1['job_id'], 'confirmation': arch1['job_id'],
            }, expect_refusal=True)

            # Retire uncertain hold -> arch1 (older than full physical backup) becomes eligible & removable, while arch2 stays protected!
            ret_uh_rev = _post_ws(client, ws_url, 'mariadb_binlog_hold_review_retire', {'hold_id': uncertain_hold['hold_id']})
            _post_ws(client, ws_url, 'mariadb_binlog_hold_retire', {
                'review_id': ret_uh_rev['review_id'],
                'review_digest': ret_uh_rev['review_digest'],
                'confirmed': True,
                'reconciliation_acknowledged': True,
            })
            eval_after_retire = _post_ws(client, ws_url, 'mariadb_binlog_retention_evaluate', {
                'policy': {'retention_days': 0, 'keep_latest': 1}
            })
            assert eval_after_retire['summary']['protected_by_physical_chain'] >= 1
            removed_arch1 = _post_ws(client, ws_url, 'mariadb_binlog_remove_artifact', {
                'job_id': arch1['job_id'], 'confirmation': arch1['job_id'],
            })
            assert removed_arch1['artifact_removed'] is True

            # Activate & retire explicit recovery chain hold binding inc2 + arch2
            rc_rev = _post_ws(client, ws_url, 'mariadb_binlog_recovery_chain_review', {
                'backup_job_id': inc2_job['job_id'],
                'archive_job_ids': [arch2['job_id']],
                'stop_gtid': good_gtid,
            })
            rc_act = _post_ws(client, ws_url, 'mariadb_binlog_recovery_chain_activate', {
                'review_id': rc_rev['review_id'], 'review_digest': rc_rev['review_digest'], 'confirmed': True,
            })
            assert rc_act['state'] == 'active'
            rc_ret_rev = _post_ws(client, ws_url, 'mariadb_binlog_recovery_chain_review_retire', {'chain_id': rc_act['chain_id']})
            rc_ret = _post_ws(client, ws_url, 'mariadb_binlog_recovery_chain_retire', {
                'review_id': rc_ret_rev['review_id'], 'review_digest': rc_ret_rev['review_digest'], 'confirmed': True,
            })
            assert rc_ret['state'] == 'retired'

            (output / 'archive-recovery-retention.json').write_text(json.dumps({
                'item': 'MA-AUDIT-ARCHIVE-RECOVERY-RETENTION',
                'complete': True,
                'receiver_checkpoint_recovery_next_file': cp_insp['checkpoint']['next_file'],
                'evaluation_with_uncertain_hold': eval_with_uncertain['summary'],
                'evaluation_after_uncertain_retired': eval_after_retire['summary'],
                'older_archive_removed_cleanly': removed_arch1['job_id'],
                'active_chain_archive_protected': arch2['job_id'],
                'recovery_chain_lifecycle': rc_ret['chain_id'],
            }, indent=2) + '\n')
        finally:
            w_conn.close()

        # =====================================================================
        # ITEM 3: MA-AUDIT-RECOVERY-CUTOVER (via authenticated HTTP!)
        # =====================================================================
        copy_back_dir = scratch / 'isolated-copy-back-datadir'
        move_back_dir = scratch / 'isolated-move-back-datadir'

        cb_rev = _post_ws(client, ws_url, 'mariadb_physical_review', {
            'options': {
                'phase': 'copy_back',
                'prepared_job_id': prep_job['job_id'],
                'target_datadir': str(copy_back_dir),
            }
        })
        cb_job = _post_ws(client, ws_url, 'mariadb_physical_start', {
            'job_id': cb_rev['job_id'], 'review_digest': cb_rev['review_digest'], 'confirmed': True,
        })
        assert cb_job['state'] == 'completed'

        mb_rev = _post_ws(client, ws_url, 'mariadb_physical_review', {
            'options': {
                'phase': 'move_back',
                'prepared_job_id': prep_job['job_id'],
                'target_datadir': str(move_back_dir),
            }
        })
        mb_job = _post_ws(client, ws_url, 'mariadb_physical_start', {
            'job_id': mb_rev['job_id'], 'review_digest': mb_rev['review_digest'], 'confirmed': True,
        })
        assert mb_job['state'] == 'completed'

        # Start isolated recovery mariadbd on copy_back_dir with PITR stopping AFTER good_gtid (rows 1..6, NOT row 7!)
        rec_port = _free_port()
        recovery_ports_to_stop.append((None, rec_port))
        rec_rev = _post_ws(client, ws_url, 'mariadb_physical_review', {
            'options': {
                'phase': 'recover',
                'restore_job_id': cb_job['job_id'],
                'recovery_port': rec_port,
                'basedir': bins['basedir'],
                'plugin_dir': bins['plugin_dir'],
                'lc_messages_dir': bins['lc_messages_dir'],
                'pitr': {
                    'archive_job_ids': [arch2['job_id']],
                    'stop_gtid': good_gtid,
                    'stop_mode': 'after',
                },
                'expected_checks': {
                    'databases': ['sr_continuity'],
                    'table_row_counts': {
                        'sr_continuity.orders': 6,
                        'sr_continuity.audit_notes': 1,
                    },
                    'accounts': ['sr_app_reader@127.0.0.1'],
                },
            }
        })
        rec_job = _post_ws(client, ws_url, 'mariadb_physical_start', {
            'job_id': rec_rev['job_id'], 'review_digest': rec_rev['review_digest'], 'confirmed': True,
        })
        assert rec_job['state'] == 'completed', rec_job
        assert rec_job['database_recovery_verified'] is True

        # Separately reviewed ONE-USE production cutover!
        cut_rev = _post_ws(client, ws_url, 'mariadb_physical_cutover_review', {
            'recovery_job_id': rec_job['job_id'],
            'target_confirmation': str(rec_port),
            'fence_old_primary': True,
            'update_target_registration': True,
            'promote_writable': True,
        })
        cut_done = _post_ws(client, ws_url, 'mariadb_physical_cutover_start', {
            'cutover_id': cut_rev['cutover_id'],
            'review_digest': cut_rev['review_digest'],
            'confirmed': True,
        })
        assert cut_done['state'] == 'completed'
        assert cut_done['old_primary_fenced'] is True
        assert cut_done['registration_updated'] is True

        # Replay of one-use cutover MUST be refused (400)!
        _post_ws(client, ws_url, 'mariadb_physical_cutover_start', {
            'cutover_id': cut_rev['cutover_id'],
            'review_digest': cut_rev['review_digest'],
            'confirmed': True,
        }, expect_refusal=True)

        # Rollback cutover & stop isolated recovery instance cleanly
        cut_rb = _post_ws(client, ws_url, 'mariadb_physical_cutover_rollback', {
            'cutover_id': cut_rev['cutover_id'],
            'confirmed': True,
        })
        assert cut_rb['state'] == 'rolled_back'

        stopped_rec = _post_ws(client, ws_url, 'mariadb_physical_stop_recovery', {
            'job_id': rec_job['job_id'], 'confirmed': True,
        })
        assert stopped_rec['recovery_running'] is False

        (output / 'recovery-cutover.json').write_text(json.dumps({
            'item': 'MA-AUDIT-RECOVERY-CUTOVER',
            'complete': True,
            'copy_back_job_id': cb_job['job_id'],
            'move_back_job_id': mb_job['job_id'],
            'recovery_job_id': rec_job['job_id'],
            'pitr_stop_gtid': good_gtid,
            'independent_verification': rec_job['result']['independent_verification'],
            'cutover_id': cut_done['cutover_id'],
            'old_primary_fenced': cut_done['old_primary_fenced'],
            'rollback_metadata': cut_done['rollback_metadata'],
            'one_use_replay_refused': True,
            'cutover_rollback_verified': cut_rb['state'] == 'rolled_back',
        }, indent=2) + '\n')

    finally:
        mariadb_host_services.control_managed_service(
            action='stop', service_mode='managed_daemon', state_dir=daemon_state,
            db_user='sr_admin', db_password=admin_pw,
        )


def qualify_upgrade_11_8_to_12_2_2(app, client, scratch: Path, output: Path, bins_1222: dict):
    """Qualify Item 6: Real mariadb:11.8 datadir -> stop -> managed 12.2.2 upgrade & container verification."""
    import mariadb

    upg_root = scratch / 'upgrade-118-to-1222'
    data_118 = upg_root / 'data118'
    data_118.mkdir(parents=True, mode=0o777)
    dump_path = upg_root / 'pre-upgrade-118.sql'
    upg_pw = 'UpgPass#' + secrets.token_urlsafe(16)
    c118 = 'sr-m118-upg-' + secrets.token_hex(6)
    c122 = 'sr-m122-verify-' + secrets.token_hex(6)
    helper_port = _free_port()
    helper_state = upg_root / 'helper-1222-state'
    helper_data = upg_root / 'helper-1222-data'

    from pgadmin.cdeadmin.providers.mysql_family import mariadb_host_services, mariadb_host_upgrade

    try:
        # 1. Start real mariadb:11.8 container mounting data_118 and populate schema, routines, views, grants
        _docker([
            'run', '-d', '--name', c118,
            '-p', '127.0.0.1::3306',
            '-e', 'MARIADB_ALLOW_EMPTY_ROOT_PASSWORD=1',
            '-v', f'{data_118}:/var/lib/mysql',
            'mariadb:11.8',
        ])
        insp = json.loads(_docker(['inspect', c118]).stdout)[0]
        port_118 = int(insp['NetworkSettings']['Ports']['3306/tcp'][0]['HostPort'])

        deadline = time.monotonic() + 90
        conn118 = None
        while time.monotonic() < deadline:
            try:
                conn118 = mariadb.connect(host='127.0.0.1', port=port_118, user='root', connect_timeout=2, autocommit=True)
                cur = conn118.cursor()
                cur.execute('SELECT VERSION()')
                ver_118 = cur.fetchone()[0]
                cur.close()
                if ver_118.startswith('11.8.'):
                    break
            except Exception:
                if conn118:
                    conn118.close()
                    conn118 = None
                time.sleep(0.4)
        assert conn118 is not None, 'mariadb:11.8 container did not become ready'

        try:
            cur = conn118.cursor()
            cur.execute('SELECT VERSION(), @@server_uid')
            ver_118, uid_118 = cur.fetchone()
            cur.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY ?", (upg_pw,))
            cur.execute("ALTER USER 'root'@'%' IDENTIFIED BY ?", (upg_pw,))
            cur.execute("CREATE USER IF NOT EXISTS 'root'@'127.0.0.1' IDENTIFIED BY ?", (upg_pw,))
            cur.execute("GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION")
            cur.execute("CREATE USER 'sr_upg_reader'@'%' IDENTIFIED BY ?", ('UpgReader!' + secrets.token_hex(6),))
            cur.execute('CREATE DATABASE sr_legacy_118 CHARACTER SET utf8mb4')
            cur.execute("GRANT SELECT, EXECUTE ON sr_legacy_118.* TO 'sr_upg_reader'@'%'")
            cur.execute(
                'CREATE TABLE sr_legacy_118.customers ('
                'id BIGINT PRIMARY KEY, name VARCHAR(100) NOT NULL, balance DECIMAL(14,2) NOT NULL'
                ') ENGINE=InnoDB'
            )
            cur.execute(
                "INSERT INTO sr_legacy_118.customers VALUES "
                "(101, 'Katherine Johnson 星', 12345.67), (102, 'Margaret Hamilton', 98765.43)"
            )
            cur.execute(
                'CREATE VIEW sr_legacy_118.v_vip AS '
                'SELECT id, name, balance FROM sr_legacy_118.customers WHERE balance > 50000'
            )
            cur.execute(
                'CREATE FUNCTION sr_legacy_118.fn_double_cents(v DECIMAL(14,2)) RETURNS DECIMAL(14,2) '
                'DETERMINISTIC RETURN v * 2'
            )
            cur.execute(
                'CREATE PROCEDURE sr_legacy_118.sp_customer_count(OUT total INT) '
                'BEGIN SELECT COUNT(*) INTO total FROM sr_legacy_118.customers; END'
            )
            cur.close()
        finally:
            conn118.close()

        # Take pre-upgrade logical dump prerequisite & perform clean innodb_fast_shutdown=0 SHUTDOWN!
        from pgadmin.cdeadmin.providers.mysql_family.mariadb_physical import write_private_defaults_file
        dump_cnf = write_private_defaults_file(
            upg_root / 'dump-auth', user='root', password=upg_pw, host='127.0.0.1', port=port_118, ssl=False,
        )
        try:
            dump_proc = subprocess.run(
                [
                    bins_1222['basedir'] + '/bin/mariadb-dump',
                    f'--defaults-file={dump_cnf}',
                    '--all-databases', '--routines', '--events',
                    f'--result-file={dump_path}',
                ],
                capture_output=True, text=True, timeout=60, check=False,
            )
            assert dump_proc.returncode == 0, f'mariadb-dump failed: {dump_proc.stderr}'
        finally:
            dump_cnf.unlink(missing_ok=True)
        assert dump_path.is_file() and dump_path.stat().st_size > 100

        clean_stop = mariadb_host_upgrade.clean_stop_source_daemon(
            host='127.0.0.1', port=port_118, db_user='root', db_password=upg_pw,
        )
        _docker(['wait', c118], timeout=30)
        _docker(['rm', '-f', '-v', c118])

        # Copy 11.8 datadir to test interrupted-upgrade reconciliation + rollback first!
        rollback_test_data = upg_root / 'data118-rollback-copy'
        shutil.copytree(data_118, rollback_test_data)

        # Start a helper 12.2.2 registration so we drive mariadb_upgrade_* through authenticated HTTP!
        mariadb_host_services.initialize_datadir(
            install_db_binary=bins_1222['mariadb_install_db'],
            mariadbd_binary=bins_1222['mariadbd'],
            datadir=helper_data,
            job_dir=upg_root / 'helper-init',
            auth_root_method='normal',
            basedir=bins_1222['basedir'],
            version_prefix='12.2.2',
        )
        mariadb_host_services.control_managed_service(
            action='start', service_mode='managed_daemon', state_dir=helper_state,
            mariadbd_binary=bins_1222['mariadbd'], datadir=helper_data, port=helper_port,
            basedir=bins_1222['basedir'], plugin_dir=bins_1222['plugin_dir'],
            lc_messages_dir=bins_1222['lc_messages_dir'], version_prefix='12.2.2',
        )
        mariadb_host_services.verify_sql_readiness(host='127.0.0.1', port=helper_port, db_user='root', db_password='')
        hconn = mariadb.connect(host='127.0.0.1', port=helper_port, user='root', autocommit=True)
        try:
            hcur = hconn.cursor()
            hcur.execute("CREATE USER IF NOT EXISTS 'root'@'127.0.0.1' IDENTIFIED BY ?", (upg_pw,))
            hcur.execute("GRANT ALL PRIVILEGES ON *.* TO 'root'@'127.0.0.1' WITH GRANT OPTION")
            hcur.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY ?", (upg_pw,))
            hcur.close()
        finally:
            hconn.close()
        _sid, _vurl, upg_ws_url = _register_mariadb_endpoint(
            app, client, name='Upgrade Controller Endpoint',
            host='127.0.0.1', port=helper_port, user='root', password=upg_pw,
        )

        # Refusal check: missing backup prerequisite MUST return 400!
        _post_ws(client, upg_ws_url, 'mariadb_upgrade_preflight', {
            'datadir': str(rollback_test_data),
            'source_version': ver_118,
        }, expect_refusal=True)

        # Interrupted upgrade + reconcile + rollback test via HTTP!
        rb_port = _free_port()
        int_rev = _post_ws(client, upg_ws_url, 'mariadb_upgrade_review', {
            'options': {
                'datadir': str(rollback_test_data),
                'source_version': ver_118,
                'target_port': rb_port,
                'target_basedir': bins_1222['basedir'],
                'target_plugin_dir': bins_1222['plugin_dir'],
                'target_lc_messages_dir': bins_1222['lc_messages_dir'],
                'verified_logical_dump_path': str(dump_path),
                'create_rollback_snapshot': True,
                '_simulate_interrupt_before_upgrade_tool': True,
            }
        })
        _post_ws(client, upg_ws_url, 'mariadb_upgrade_start', {
            'job_id': int_rev['job_id'],
            'review_digest': int_rev['review_digest'],
            'confirmed': True,
            'db_password': upg_pw,
        }, expect_refusal=True)
        int_recon = _post_ws(client, upg_ws_url, 'mariadb_upgrade_reconcile', {
            'job_id': int_rev['job_id'], 'confirmed': True,
        })
        assert int_recon['reconciliation']['rollback_snapshot_available'] is True
        int_rb = _post_ws(client, upg_ws_url, 'mariadb_upgrade_rollback', {
            'job_id': int_rev['job_id'], 'confirmed': True,
        })
        assert int_rb['rollback_result']['rolled_back'] is True
        assert int_rb['rollback_result']['claim_released'] is True

        # Full end-to-end 11.8 -> 12.2.2 managed upgrade via HTTP!
        upg_target_port = _free_port()
        upg_rev = _post_ws(client, upg_ws_url, 'mariadb_upgrade_review', {
            'options': {
                'datadir': str(data_118),
                'source_version': ver_118,
                'target_port': upg_target_port,
                'target_basedir': bins_1222['basedir'],
                'target_plugin_dir': bins_1222['plugin_dir'],
                'target_lc_messages_dir': bins_1222['lc_messages_dir'],
                'verified_logical_dump_path': str(dump_path),
                'create_rollback_snapshot': True,
            }
        })
        upg_done = _post_ws(client, upg_ws_url, 'mariadb_upgrade_start', {
            'job_id': upg_rev['job_id'],
            'review_digest': upg_rev['review_digest'],
            'confirmed': True,
            'db_password': upg_pw,
        })
        assert upg_done['state'] == 'completed', upg_done
        assert '12.2.2-MariaDB' in upg_done['result']['mariadb_upgrade_info']['raw']
        assert upg_done['result']['upgrade_still_needed'] is False

        # Stop local target daemon cleanly, then mount upgraded datadir into real `mariadb:12.2.2` container
        # and verify 12.2.2 container boots cleanly and preserves all 11.8 tables, views, routines & grants!
        _post_ws(client, upg_ws_url, 'mariadb_upgrade_stop_target', {
            'job_id': upg_rev['job_id'], 'confirmed': True,
        })

        _docker([
            'run', '-d', '--name', c122,
            '-p', '127.0.0.1::3306',
            '-v', f'{data_118}:/var/lib/mysql',
            'mariadb:12.2.2',
        ])
        insp122 = json.loads(_docker(['inspect', c122]).stdout)[0]
        port_122 = int(insp122['NetworkSettings']['Ports']['3306/tcp'][0]['HostPort'])

        deadline122 = time.monotonic() + 90
        conn122 = None
        while time.monotonic() < deadline122:
            try:
                conn122 = mariadb.connect(host='127.0.0.1', port=port_122, user='root', password=upg_pw, connect_timeout=2, autocommit=True)
                break
            except Exception:
                time.sleep(0.4)
        assert conn122 is not None, 'mariadb:12.2.2 container on upgraded datadir did not become ready'

        try:
            cur = conn122.cursor()
            cur.execute('SELECT VERSION()')
            ver_after = cur.fetchone()[0]
            assert ver_after.startswith('12.2.2-MariaDB'), ver_after
            cur.execute('SELECT id, name, CAST(balance AS CHAR) FROM sr_legacy_118.v_vip')
            vip_rows = cur.fetchall()
            assert vip_rows == [(102, 'Margaret Hamilton', '98765.43')], vip_rows
            cur.execute('SELECT CAST(sr_legacy_118.fn_double_cents(12.34) AS CHAR)')
            assert cur.fetchone()[0] == '24.68'
            cur.execute('CALL sr_legacy_118.sp_customer_count(@cnt)')
            cur.execute('SELECT @cnt')
            assert int(cur.fetchone()[0]) == 2
            cur.execute("SHOW GRANTS FOR 'sr_upg_reader'@'%'")
            grants_after = [r[0] for r in cur.fetchall()]
            assert any('sr_legacy_118' in g for g in grants_after), grants_after
            cur.close()
        finally:
            conn122.close()

        (output / 'host-upgrade.json').write_text(json.dumps({
            'item': 'MA-AUDIT-HOST-UPGRADE',
            'complete': True,
            'source_11_8_version': ver_118,
            'source_11_8_clean_stop': clean_stop,
            'interrupted_upgrade_rollback_verified': int_rb['rollback_result'],
            'upgrade_job_id': upg_done['job_id'],
            'mariadb_upgrade_info': upg_done['result']['mariadb_upgrade_info'],
            'upgrade_still_needed_after_upgrade': upg_done['result']['upgrade_still_needed'],
            'container_12_2_2_mounted_version': ver_after,
            'preserved_vip_view_rows': vip_rows,
            'preserved_grants': grants_after,
        }, indent=2) + '\n')

    finally:
        mariadb_host_services.control_managed_service(
            action='stop', service_mode='managed_daemon', state_dir=helper_state,
            db_user='root', db_password=upg_pw,
        )
        _docker(['rm', '-f', '-v', c118], check=False)
        _docker(['rm', '-f', '-v', c122], check=False)


def qualify_galera_2node_cluster(app, client, scratch: Path, output: Path, bins_1222: dict):
    """Qualify Item 7: Real 2-node MariaDB 12.2.2 Galera cluster on an owned Docker bridge network."""
    import mariadb

    gal_root = scratch / 'galera-2node'
    n1_data = gal_root / 'node1-data'
    n2_data = gal_root / 'node2-data'
    n1_data.mkdir(parents=True, mode=0o777)
    n2_data.mkdir(parents=True, mode=0o777)

    net_name = 'sr-galera-net-' + secrets.token_hex(6)
    n1_name = 'sr-galera-n1-' + secrets.token_hex(5)
    n2_name = 'sr-galera-n2-' + secrets.token_hex(5)
    standalone_name = 'sr-nongalera-' + secrets.token_hex(5)
    gal_pw = 'GaleraAdm#' + secrets.token_urlsafe(16)

    try:
        # 1. Verify non-Galera MariaDB reports galera_available=False (never substituting async replication!)
        _docker([
            'run', '-d', '--name', standalone_name,
            '-p', '127.0.0.1::3306',
            '-e', f'MARIADB_ROOT_PASSWORD={gal_pw}',
            'mariadb:12.2.2',
        ])
        st_port = int(json.loads(_docker(['inspect', standalone_name]).stdout)[0]['NetworkSettings']['Ports']['3306/tcp'][0]['HostPort'])
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                c = mariadb.connect(host='127.0.0.1', port=st_port, user='root', password=gal_pw, connect_timeout=2)
                c.close()
                break
            except Exception:
                time.sleep(0.3)

        _st_id, _st_v, st_ws_url = _register_mariadb_endpoint(
            app, client, name='Standalone Non-Galera MariaDB',
            host='127.0.0.1', port=st_port, user='root', password=gal_pw,
        )
        non_gal_obs = _post_ws(client, st_ws_url, 'mariadb_galera_inspect', {})
        assert non_gal_obs['galera_available'] is False
        assert non_gal_obs['availability_reason'] == 'wsrep_provider_not_loaded'
        assert non_gal_obs['async_replication_substituted'] is False
        _post_ws(client, st_ws_url, 'mariadb_galera_review', {
            'options': {'operation': 'set_desync', 'enabled': True}
        }, expect_refusal=True)
        _docker(['rm', '-f', '-v', standalone_name])

        # 2. Create owned Docker bridge network & bootstrap Galera Node 1 (`--wsrep-new-cluster`)
        _docker(['network', 'create', net_name])
        common_galera_args = [
            '--wsrep-on=ON',
            '--wsrep-provider=/usr/lib/galera/libgalera_smm.so',
            '--wsrep-cluster-name=sr_batch6_galera',
            f'--wsrep-cluster-address=gcomm://{n1_name},{n2_name}',
            '--wsrep-sst-method=rsync',
            '--binlog-format=ROW',
            '--default-storage-engine=InnoDB',
            '--innodb-autoinc-lock-mode=2',
        ]
        _docker([
            'run', '-d', '--name', n1_name, '--hostname', n1_name,
            '--network', net_name,
            '-p', '127.0.0.1::3306',
            '-e', f'MARIADB_ROOT_PASSWORD={gal_pw}',
            '-e', 'MARIADB_ROOT_HOST=%',
            '-v', f'{n1_data}:/var/lib/mysql',
            'mariadb:12.2.2',
            *common_galera_args,
            '--wsrep-new-cluster',
            '--wsrep-node-name=node1',
            f'--wsrep-node-address={n1_name}',
        ])
        n1_port = int(json.loads(_docker(['inspect', n1_name]).stdout)[0]['NetworkSettings']['Ports']['3306/tcp'][0]['HostPort'])

        deadline_n1 = time.monotonic() + 90
        while time.monotonic() < deadline_n1:
            try:
                cn1 = mariadb.connect(host='127.0.0.1', port=n1_port, user='root', password=gal_pw, connect_timeout=2, autocommit=True)
                cur = cn1.cursor()
                cur.execute("SHOW GLOBAL STATUS LIKE 'wsrep_local_state_comment'")
                row = cur.fetchone()
                cur.close()
                cn1.close()
                if row and row[1] == 'Synced':
                    break
            except Exception:
                pass
            time.sleep(0.5)

        n1_sid, _n1_v, n1_ws_url = _register_mariadb_endpoint(
            app, client, name='Galera Node 1',
            host='127.0.0.1', port=n1_port, user='root', password=gal_pw,
        )
        boot_rev = _post_ws(client, n1_ws_url, 'mariadb_galera_review', {
            'options': {
                'operation': 'bootstrap_cluster',
                'bootstrap_mode': 'grastate_and_verify',
                'host_provider_path': bins_1222['galera_provider'],
            }
        })
        boot_done = _post_ws(client, n1_ws_url, 'mariadb_galera_start', {
            'job_id': boot_rev['job_id'], 'review_digest': boot_rev['review_digest'], 'confirmed': True,
        })
        n1_obs = boot_done['result']['synced_observation']
        assert n1_obs['galera_available'] is True
        assert n1_obs['cluster']['wsrep_cluster_status'] == 'Primary'
        assert n1_obs['cluster']['wsrep_cluster_size'] == 1
        assert n1_obs['local_member']['wsrep_local_state_comment'] == 'Synced'
        cluster_uuid = n1_obs['cluster']['wsrep_cluster_state_uuid']

        # Seed initial database & table on Node 1 BEFORE Node 2 joins so SST copies it!
        cn1 = mariadb.connect(host='127.0.0.1', port=n1_port, user='root', password=gal_pw, autocommit=True)
        try:
            cur = cn1.cursor()
            cur.execute('CREATE DATABASE sr_galera_db CHARACTER SET utf8mb4')
            cur.execute('CREATE TABLE sr_galera_db.ledger (id INT PRIMARY KEY, origin VARCHAR(32), note VARCHAR(80)) ENGINE=InnoDB')
            cur.execute("INSERT INTO sr_galera_db.ledger VALUES (1, 'node1_pre_sst', 'bootstrapped row')")
            cur.close()
        finally:
            cn1.close()

        # 3. Join Node 2 via SST onto the owned Docker bridge network!
        n2_port = _free_port()
        _docker([
            'run', '-d', '--name', n2_name, '--hostname', n2_name,
            '--network', net_name,
            '-p', f'127.0.0.1:{n2_port}:3306',
            '-e', 'MARIADB_ALLOW_EMPTY_ROOT_PASSWORD=1',
            '-v', f'{n2_data}:/var/lib/mysql',
            'mariadb:12.2.2',
            *common_galera_args,
            '--wsrep-node-name=node2',
            f'--wsrep-node-address={n2_name}',
        ])

        deadline_n2 = time.monotonic() + 90
        while time.monotonic() < deadline_n2:
            try:
                cn2 = mariadb.connect(host='127.0.0.1', port=n2_port, user='root', password=gal_pw, connect_timeout=2, autocommit=True)
                cn2.close()
                break
            except Exception:
                time.sleep(0.5)

        n2_sid, _n2_v, n2_ws_url = _register_mariadb_endpoint(
            app, client, name='Galera Node 2',
            host='127.0.0.1', port=n2_port, user='root', password=gal_pw,
        )
        join_rev = _post_ws(client, n2_ws_url, 'mariadb_galera_review', {
            'options': {
                'operation': 'join_node',
                'seed_server_id': n1_sid,
                'expected_cluster_size': 2,
            }
        })
        join_done = _post_ws(client, n2_ws_url, 'mariadb_galera_start', {
            'job_id': join_rev['job_id'], 'review_digest': join_rev['review_digest'], 'confirmed': True,
        })
        n2_joined_obs = join_done['result']['member_observation']
        assert n2_joined_obs['cluster']['wsrep_cluster_state_uuid'] == cluster_uuid
        assert n2_joined_obs['cluster']['wsrep_cluster_size'] == 2
        assert n2_joined_obs['cluster']['wsrep_cluster_status'] == 'Primary'
        assert n2_joined_obs['local_member']['wsrep_local_state_comment'] == 'Synced'

        cluster_view = _post_ws(client, n1_ws_url, 'mariadb_galera_inspect_cluster', {
            'peer_server_ids': [n2_sid]
        })
        assert cluster_view['uniform_cluster_uuid'] is True

        # 4. Verify bi-directional synchronous replication across Node 1 <-> Node 2!
        cn1 = mariadb.connect(host='127.0.0.1', port=n1_port, user='root', password=gal_pw, autocommit=True)
        cn2 = mariadb.connect(host='127.0.0.1', port=n2_port, user='root', password=gal_pw, autocommit=True)
        try:
            c1, c2 = cn1.cursor(), cn2.cursor()
            c1.execute("INSERT INTO sr_galera_db.ledger VALUES (2, 'node1_live', 'replicated to node2')")
            c2.execute('SELECT COUNT(*) FROM sr_galera_db.ledger WHERE id IN (1, 2)')
            assert int(c2.fetchone()[0]) == 2
            c2.execute("INSERT INTO sr_galera_db.ledger VALUES (3, 'node2_live', 'replicated to node1')")
            c1.execute('SELECT id, origin FROM sr_galera_db.ledger ORDER BY id')
            sync_rows = c1.fetchall()
            assert sync_rows == [(1, 'node1_pre_sst'), (2, 'node1_live'), (3, 'node2_live')]
            c1.close()
            c2.close()
        finally:
            cn1.close()
            cn2.close()

        # 5. Toggle maintenance `wsrep_desync` ON and OFF on Node 2 via HTTP!
        desync_on_rev = _post_ws(client, n2_ws_url, 'mariadb_galera_review', {
            'options': {'operation': 'set_desync', 'enabled': True}
        })
        desync_on = _post_ws(client, n2_ws_url, 'mariadb_galera_start', {
            'job_id': desync_on_rev['job_id'], 'review_digest': desync_on_rev['review_digest'], 'confirmed': True,
        })
        assert desync_on['result']['wsrep_desync'] is True
        assert 'Desynced' in (desync_on['result']['after_state_comment'] or '')

        desync_off_rev = _post_ws(client, n2_ws_url, 'mariadb_galera_review', {
            'options': {'operation': 'set_desync', 'enabled': False}
        })
        desync_off = _post_ws(client, n2_ws_url, 'mariadb_galera_start', {
            'job_id': desync_off_rev['job_id'], 'review_digest': desync_off_rev['review_digest'], 'confirmed': True,
        })
        assert desync_off['result']['wsrep_desync'] is False
        assert desync_off['result']['after_state_comment'] == 'Synced'

        # 6. Stop Node 2 cleanly via HTTP, verify `grastate.dat` safe_to_bootstrap=0 refusal,
        #    write on Node 1 while Node 2 is stopped, then rejoin Node 2 via IST/SST catch-up!
        stop_n2_rev = _post_ws(client, n2_ws_url, 'mariadb_galera_review', {
            'options': {'operation': 'stop_node', 'datadir': str(n2_data)}
        })
        stop_n2 = _post_ws(client, n2_ws_url, 'mariadb_galera_start', {
            'job_id': stop_n2_rev['job_id'], 'review_digest': stop_n2_rev['review_digest'], 'confirmed': True,
        })
        _docker(['wait', n2_name], timeout=30)

        gra_n2_stopped = _post_ws(client, n1_ws_url, 'mariadb_galera_inspect_grastate', {'datadir': str(n2_data)})
        assert gra_n2_stopped['exists'] is True
        assert gra_n2_stopped['safe_to_bootstrap'] is False

        # Attempting to bootstrap from stopped Node 2 (safe_to_bootstrap=0) MUST be refused (400)!
        _post_ws(client, n1_ws_url, 'mariadb_galera_review', {
            'options': {
                'operation': 'bootstrap_cluster',
                'datadir': str(n2_data),
                'force_safe_to_bootstrap': False,
            }
        }, expect_refusal=True)

        # Write rows 4 & 5 on Node 1 while Node 2 is offline!
        cn1 = mariadb.connect(host='127.0.0.1', port=n1_port, user='root', password=gal_pw, autocommit=True)
        try:
            c1 = cn1.cursor()
            c1.execute("INSERT INTO sr_galera_db.ledger VALUES (4, 'while_n2_down', 'ist_catchup_1'), (5, 'while_n2_down', 'ist_catchup_2')")
            c1.close()
        finally:
            cn1.close()

        # Start Node 2 container again (rejoining without --wsrep-new-cluster!) & verify IST/SST catch-up via HTTP!
        _docker(['start', n2_name])
        n2_port_rejoin = n2_port
        deadline_rejoin = time.monotonic() + 90
        while time.monotonic() < deadline_rejoin:
            try:
                cn2_chk = mariadb.connect(host='127.0.0.1', port=n2_port, user='root', password=gal_pw, connect_timeout=2, autocommit=True)
                cn2_chk.close()
                break
            except Exception:
                time.sleep(0.5)

        rejoin_rev = _post_ws(client, n2_ws_url, 'mariadb_galera_review', {
            'options': {'operation': 'rejoin_node', 'seed_server_id': n1_sid, 'expected_cluster_size': 2}
        })
        rejoin_done = _post_ws(client, n2_ws_url, 'mariadb_galera_start', {
            'job_id': rejoin_rev['job_id'], 'review_digest': rejoin_rev['review_digest'], 'confirmed': True,
        })
        assert rejoin_done['result']['member_observation']['cluster']['wsrep_cluster_size'] == 2
        assert rejoin_done['result']['member_observation']['local_member']['wsrep_local_state_comment'] == 'Synced'

        cn2 = mariadb.connect(host='127.0.0.1', port=n2_port_rejoin, user='root', password=gal_pw, autocommit=True)
        try:
            c2 = cn2.cursor()
            c2.execute('SELECT COUNT(*) FROM sr_galera_db.ledger')
            rejoined_count = int(c2.fetchone()[0])
            c2.close()
        finally:
            cn2.close()
        assert rejoined_count == 5

        # Stop Node 2 first, then stop Node 1 last -> verify Node 1's grastate.dat has safe_to_bootstrap=1!
        _docker(['stop', n2_name], timeout=30)
        _docker(['stop', n1_name], timeout=30)
        gra_n1_final = _post_ws(client, n1_ws_url, 'mariadb_galera_inspect_grastate', {'datadir': str(n1_data)})
        assert gra_n1_final['safe_to_bootstrap'] is True

        (output / 'galera-cluster.json').write_text(json.dumps({
            'item': 'MA-AUDIT-GALERA',
            'complete': True,
            'non_galera_unavailable_cleanly': non_gal_obs,
            'cluster_state_uuid': cluster_uuid,
            'node1_bootstrap': n1_obs['cluster'],
            'node2_sst_join': n2_joined_obs['cluster'],
            'bidirectional_sync_rows': sync_rows,
            'desync_toggle': {
                'on': desync_on['result'],
                'off': desync_off['result'],
            },
            'stopped_node2_grastate': gra_n2_stopped,
            'unsafe_bootstrap_refused': True,
            'rejoin_ist_sst_row_count': rejoined_count,
            'last_standing_node1_grastate': gra_n1_final,
        }, indent=2) + '\n')

    finally:
        _docker(['rm', '-f', '-v', standalone_name], check=False)
        _docker(['rm', '-f', '-v', n2_name], check=False)
        _docker(['rm', '-f', '-v', n1_name], check=False)
        _docker(['network', 'rm', net_name], check=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    tmp_base = Path(os.environ.get(
        'TMPDIR',
        '/home/dcalford/Sandbox/codex-work-area/cdeadmin-six-engine-implementation/tmp-work/batch6',
    ))
    tmp_base.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix='mariadb-batch6-live-', dir=str(tmp_base)))

    tracked_sources = [
        'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_physical.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_archive_checkpoint.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_host_services.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_host_upgrade.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_galera.py',
        'web/pgadmin/cdeadmin/workspace/mariadb_physical_service.py',
        'web/pgadmin/cdeadmin/workspace/mariadb_receiver_checkpoints.py',
        'web/pgadmin/cdeadmin/workspace/mariadb_archive_retention.py',
        'web/pgadmin/cdeadmin/workspace/mariadb_host_service.py',
        'web/pgadmin/cdeadmin/workspace/mariadb_upgrade_service.py',
        'web/pgadmin/cdeadmin/workspace/mariadb_galera_service.py',
        'web/pgadmin/cdeadmin/ui_descriptors/mariadb/capabilities.json',
        'web/pgadmin/cdeadmin/ui_descriptors/mariadb/operations.json',
        'web/pgadmin/cdeadmin/ui_descriptors/mariadb/tools.json',
        'tools/cdeadmin_mariadb_batch6_continuity_qualification.py',
    ]

    try:
        bins_1222 = _stage_mariadb_runtime('mariadb:12.2.2', scratch / 'runtime-12.2.2')
        app = _setup_flask_app(scratch / 'flask-app', bins_1222)
        client = app.test_client()

        qualify_continuity_and_host(app, client, scratch, output, bins_1222)
        qualify_upgrade_11_8_to_12_2_2(app, client, scratch, output, bins_1222)
        qualify_galera_2node_cluster(app, client, scratch, output, bins_1222)

        from tools.validate_ui_descriptors import lint_counts, validate_descriptors
        desc_errors, desc_summary = validate_descriptors(strict_pending=False)
        assert not desc_errors, desc_errors
        counts = lint_counts()
        (output / 'ui-descriptors.json').write_text(json.dumps({
            'errors': desc_errors,
            'mariadb_summary': desc_summary['engines']['mariadb'],
            'lint_counts': counts,
        }, indent=2) + '\n')

    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    # Verify zero leftover disposable batch6 containers or networks
    ps_out = _docker(['ps', '-a', '--format', '{{.Names}}']).stdout.splitlines()
    net_out = _docker(['network', 'ls', '--format', '{{.Name}}']).stdout.splitlines()
    leftover_containers = [n for n in ps_out if n.startswith(('sr-m118-upg-', 'sr-m122-verify-', 'sr-galera-n1-', 'sr-galera-n2-', 'sr-nongalera-'))]
    leftover_nets = [n for n in net_out if n.startswith('sr-galera-net-')]
    assert not leftover_containers and not leftover_nets, (leftover_containers, leftover_nets)

    receipt_files = [
        'physical-backup.json',
        'incremental-prepare.json',
        'recovery-cutover.json',
        'archive-recovery-retention.json',
        'host-config-service.json',
        'host-upgrade.json',
        'galera-cluster.json',
        'ui-descriptors.json',
    ]
    for rf in receipt_files:
        assert (output / rf).is_file(), f'Missing receipt {rf}'

    summary = {
        'complete': True,
        'batch': 'mariadb-batch6-continuity',
        'history_testing': 'not run',
        'items_qualified': [
            'MA-AUDIT-PHYSICAL-BACKUP',
            'MA-AUDIT-INCREMENTAL-PREPARE',
            'MA-AUDIT-RECOVERY-CUTOVER',
            'MA-AUDIT-ARCHIVE-RECOVERY-RETENTION',
            'MA-AUDIT-HOST-CONFIG-SERVICE',
            'MA-AUDIT-HOST-UPGRADE',
            'MA-AUDIT-GALERA',
        ],
        'receipts': receipt_files,
        'cleanup_verified': {
            'scratch_removed': not scratch.exists(),
            'leftover_containers': leftover_containers,
            'leftover_networks': leftover_nets,
        },
        'source_sha256': {
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
            for p in tracked_sources
        },
    }
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('MariaDB Batch 6 qualification COMPLETE:', output / 'summary.json')


if __name__ == '__main__':
    main()

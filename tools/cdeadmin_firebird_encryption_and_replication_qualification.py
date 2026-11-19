"""Qualify Firebird 5.0.4 database-at-rest encryption/decryption & KeyHolder lifecycle (FB-AUD-07)
and two-process native journal replication, lag observation, recovery & promotion (FB-AUD-04).
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
import time
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]

DONOR_SOURCE = Path('/home/dcalford/Sandbox/donor_release_acquisition/firebird/5.0.4/source')
DBCRYPT_EXAMPLE_DIR = DONOR_SOURCE / 'examples/dbcrypt'


def _materialize_writable_runtime(stage):
    """Ensure plugins/ and config files in a staged runtime are real writable files/dirs, not symlinks."""
    for cfg in ('firebird.conf', 'databases.conf', 'replication.conf', 'plugins.conf'):
        p = stage / cfg
        if p.is_symlink():
            txt = p.read_text(encoding='utf-8') if p.exists() else ''
            p.unlink()
            p.write_text(txt, encoding='utf-8')
        elif not p.exists():
            p.write_text('', encoding='utf-8')

    plug_link = stage / 'plugins'
    if plug_link.is_symlink():
        src_plug = plug_link.resolve(strict=True)
        plug_link.unlink()
        shutil.copytree(src_plug, plug_link)


def _compile_sample_crypt_plugins(staging_dir):
    """Compile official Firebird 5.0.4 SDK sample DbCrypt and CryptKeyHolder plugins into staging_dir."""
    dbcrypt_so = staging_dir / 'libfbSampleDbCrypt.so'
    keyholder_so = staging_dir / 'libfbSampleKeyHolder.so'
    include_flags = [
        f'-I{DONOR_SOURCE / "src/include"}',
        f'-I{DONOR_SOURCE / "examples/interfaces"}',
    ]
    for src_file, out_so in (
        (DBCRYPT_EXAMPLE_DIR / 'DbCrypt.cpp', dbcrypt_so),
        (DBCRYPT_EXAMPLE_DIR / 'CryptKeyHolder.cpp', keyholder_so),
    ):
        subprocess.run(
            ['g++', '-std=gnu++14', '-shared', '-fPIC', '-O2', *include_flags, str(src_file), '-o', str(out_so)],
            check=True, capture_output=True, text=True, timeout=60,
        )
    return dbcrypt_so, keyholder_so


def qualify_native(runtime, output):
    import firebird.driver as fb_driver
    from tools.cdeadmin_firebird_object_live_orchestrator import (
        _stage_runtime, _runtime_fingerprint, _initialize_security, _free_port,
    )
    from pgadmin.cdeadmin.providers.firebird import provider as network
    from pgadmin.cdeadmin.providers.firebird.host_runtime_grant import file_sha256
    from pgadmin.cdeadmin.providers.firebird.host_configuration import (
        inspect_host_configuration, prepare_configuration_review, apply_host_configuration,
    )
    from pgadmin.cdeadmin.providers.firebird.plugin_deployment import (
        prepare_plugin_review, apply_plugin_operation,
    )
    from pgadmin.cdeadmin.providers.firebird.runtime_lifecycle import (
        start_managed_daemon_process, stop_managed_daemon_process,
    )
    from pgadmin.cdeadmin.providers.firebird.database_encryption import (
        inspect_encryption_status, wait_for_encryption_settle,
    )
    from pgadmin.cdeadmin.providers.firebird.replication_workflow import (
        inspect_replication_state, prepare_replication_review, apply_replication_operation,
    )
    from pgadmin.cdeadmin.workspace.firebird_host_actions import HostActions
    from pgadmin.cdeadmin.visual_admin import ProviderVisualAdministration
    from tools.mysql_driver_gate_support import provider_access

    runtime, output = Path(runtime).resolve(), Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True, exist_ok=True)
    before = _runtime_fingerprint(runtime)

    enc_proof = {
        'format': 'cdeadmin.firebird-database-encryption.v1',
        'engine_version': '5.0.4',
        'complete': False,
        'history_tests': 'not run',
        'application_implements_cryptography': False,
        'unavailable_closed_dependencies_recorded': [
            {
                'dependency': 'Production third-party DbCrypt / HSM KeyHolder plugin',
                'installed': False,
                'reason': 'Core Firebird 5.0.4 provides plugin hooks only; qualified with official IDPL SDK sample fbSampleDbCrypt + fbSampleKeyHolder (explicitly flagged non-secure).',
            }
        ],
        'parser_statements': [],
        'live_statements': [],
        'checks': [],
    }
    repl_proof = {
        'format': 'cdeadmin.firebird-replication.v1',
        'engine_version': '5.0.4',
        'complete': False,
        'history_tests': 'not run',
        'automatic_failover_certified': False,
        'postgresql_wal_lsn_semantics': False,
        'checks': [],
    }

    with tempfile.TemporaryDirectory(prefix='cdeadmin-fb-enc-repl-') as temp:
        area = Path(temp).resolve()

        # =====================================================================
        # PART 1: FB-AUD-07 — Database encryption, decryption & KeyHolder loss
        # =====================================================================
        enc_stage = area / 'enc_runtime'
        enc_data = area / 'enc_data'
        enc_staging = area / 'enc_staging'
        enc_data.mkdir()
        enc_staging.mkdir()
        _stage_runtime(runtime, enc_stage)
        _materialize_writable_runtime(enc_stage)

        enc_pw = 'Enc' + secrets.token_hex(8) + '!9'
        enc_port = _free_port()
        enc_pid = area / 'enc_daemon.pid'
        enc_log = area / 'enc_daemon.log'
        (enc_stage / 'firebird.conf').write_text(
            (enc_stage / 'firebird.conf').read_text(encoding='utf-8').rstrip()
            + '\nServerMode = SuperClassic\nAuthServer = Srp256, Srp\nUserManager = Srp\nWireCrypt = Enabled\n',
            encoding='utf-8',
        )
        os.environ.update(
            FIREBIRD=str(enc_stage),
            FIREBIRD_LOCK=str(enc_stage / 'lock'),
            CDEADMIN_FIREBIRD_CLIENT_LIBRARY=str(enc_stage / 'lib/libfbclient.so.5.0.4'),
        )
        fb_driver.driver_config.fb_client_library.value = str(enc_stage / 'lib/libfbclient.so.5.0.4')
        _initialize_security(enc_stage, enc_pw, {
            **os.environ,
            'FIREBIRD': str(enc_stage),
            'FIREBIRD_LOCK': str(enc_stage / 'lock'),
            'LD_LIBRARY_PATH': str(enc_stage / 'lib'),
        })

        enc_scope = {
            'attachment_mode': 'same_host_granted_network',
            'platform': 'linux',
            'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text(encoding='utf-8').strip(),
            'hostname': 'localhost',
            'engine_version': '5.0.4',
            'firebird_runtime_root': str(enc_stage),
            'firebird_lock_directory': str(enc_stage / 'lock'),
            'staging_directory': str(enc_staging),
            'journal_directories': [],
            'allowed_databases': [str(enc_data / 'vault.fdb')],
            'allow_host_administration': True,
            'managed_daemon': {
                'pid_file': str(enc_pid),
                'port': enc_port,
                'bind_host': '127.0.0.1',
                'server_log': str(enc_log),
            },
        }

        start_managed_daemon_process(enc_scope)
        try:
            with ExitStack() as stack:
                vault_db = enc_data / 'vault.fdb'
                base_enc_route = {
                    'host': '127.0.0.1', 'port': enc_port,
                    'database': str(vault_db),
                    'user': 'SYSDBA', 'charset': 'UTF8', 'wire_crypt': 'Enabled', 'trusted_auth': False,
                }
                enc_route, perms = provider_access(base_enc_route, enc_pw)
                perms.require = lambda *_: None
                perms.allows = lambda *_: True
                ctx = SimpleNamespace(
                    endpoint_id='ep-fb-enc',
                    mode='provider_native', runtime_verification_state='verified',
                    profile_id=network.PROFILE.profile_id, provider_id=network.PROFILE.provider_id,
                    declared_runtime_family='firebird', verified_runtime_family='firebird',
                )
                client = network._create_client(perms, attachment_mode='network')
                stack.callback(client.close)
                visual = ProviderVisualAdministration(ctx, perms, 'firebird', '5.0.4', client)
                created = client.config.database_creator(
                    **client.config.database_create_arguments(enc_route, str(vault_db), {}),
                    password=enc_pw,
                )
                created.close()

                conn = client._connect({'route': enc_route})
                try:
                    conn.execute_immediate(
                        'CREATE TABLE SECRET_LEDGER (ID INTEGER NOT NULL PRIMARY KEY, PAYLOAD VARCHAR(80))'
                    )
                    conn.commit()
                    conn.execute_immediate("INSERT INTO SECRET_LEDGER VALUES (1, ' Confidential-東京-Alpha')")
                    conn.execute_immediate("INSERT INTO SECRET_LEDGER VALUES (2, ' Confidential-Beta-42')")
                    conn.commit()
                finally:
                    client._forget_and_close(conn)

                # 1a. Stock runtime WITHOUT DbCrypt plugin must natively refuse encrypt_database
                db_res = next(
                    item for item in client.list_resources({'route': enc_route})
                    if item['resource_kind'] == 'database'
                )
                enc_draft = {
                    'confirmation': str(vault_db),
                    'crypt_plugin': 'fbSampleDbCrypt',
                    'key_name': 'OWNED',
                    'confirm_key_recovery_responsibility': True,
                }
                val_res = visual.validate({
                    '_provider_route': enc_route,
                    'resource_kind': 'database',
                    'operation_id': 'encrypt_database',
                    'target_resource': db_res,
                    'draft': enc_draft,
                })
                assert val_res['valid'] is True and val_res['errors'] == [], val_res
                plan_missing = visual.plan({
                    '_provider_route': enc_route,
                    'resource_kind': 'database',
                    'operation_id': 'encrypt_database',
                    'target_resource': db_res,
                    'draft': enc_draft,
                })
                enc_sql = plan_missing['command_preview']['statements'][0]['source']
                assert enc_sql == 'ALTER DATABASE ENCRYPT WITH "fbSampleDbCrypt" KEY "OWNED"'
                enc_proof['parser_statements'].append(enc_sql)

                missing_plugin_refused = False
                try:
                    visual.apply({
                        'plan_id': plan_missing['plan_id'],
                        'plan_digest': plan_missing['plan_digest'],
                        'confirmed': True,
                    })
                except Exception as err:
                    err_text = str(err) + json.dumps(getattr(err, 'operation', {}))
                    missing_plugin_refused = (
                        '335545039' in err_text or '336397313' in err_text
                        or 'fbSampleDbCrypt' in err_text or 'plugin' in err_text.lower()
                    )
                assert missing_plugin_refused
                st0 = inspect_encryption_status(client, enc_route, host_scope=enc_scope)
                assert st0['crypt_state_code'] == 0 and st0['crypt_state'] == 'not_encrypted'
                enc_proof['checks'].append(
                    'Stock runtime without DbCrypt plugin natively refuses encrypt_database and leaves MON$CRYPT_STATE=0'
                )

                # 1b. Compile & deploy official non-secure sample fbSampleDbCrypt + fbSampleKeyHolder
                dbcrypt_so, keyholder_so = _compile_sample_crypt_plugins(enc_staging)
                dbcrypt_cfg = enc_staging / 'fbSampleDbCrypt.conf'
                dbcrypt_cfg.write_text('Auto = false\n', encoding='utf-8')
                keyholder_cfg = enc_staging / 'fbSampleKeyHolder.conf'
                keyholder_cfg.write_text('Auto = true\nKeyOWNED = 90\nOnlyOwnKey = false\n', encoding='utf-8')

                plug_journal = HostActions(
                    area / 'enc-plug.json', 'fb_plug',
                    {'deploy_udr_module', 'remove_udr_module', 'deploy_plugin', 'remove_plugin'},
                )
                for mod_name, so_p, cfg_p in (
                    ('fbSampleDbCrypt', dbcrypt_so, dbcrypt_cfg),
                    ('fbSampleKeyHolder', keyholder_so, keyholder_cfg),
                ):
                    rev = plug_journal.review(
                        'owner', 'b1', 'deploy_plugin',
                        prepare_plugin_review(enc_scope, {
                            'operation': 'deploy_plugin',
                            'module_name': mod_name,
                            'plugin_alias': mod_name,
                            'staged_filename': so_p.name,
                            'expected_source_sha256': file_sha256(so_p),
                            'staged_config_filename': cfg_p.name,
                            'expected_config_sha256': file_sha256(cfg_p),
                        }),
                    )
                    out = plug_journal.apply(
                        'owner', 'b1',
                        {'review_id': rev['review_id'], 'review_digest': rev['review_digest'], 'confirmed': True},
                        apply_plugin_operation,
                    )['outcome']
                    assert out['state'] == 'deployed', out

                # Configure KeyHolderPlugin = fbSampleKeyHolder and restart managed daemon
                client.close()
                cfg_journal = HostActions(area / 'enc-cfg.json', 'fb_cfg', {'update_configuration'})
                cfg_snap = inspect_host_configuration(enc_scope)
                rev_kh = cfg_journal.review(
                    'owner', 'b1', 'update_configuration',
                    prepare_configuration_review(enc_scope, {
                        'target_file': 'firebird.conf',
                        'expected_generation_sha256': cfg_snap['files']['firebird.conf']['generation_sha256'],
                        'set_options': {'KeyHolderPlugin': 'fbSampleKeyHolder'},
                        'lifecycle_action': 'restart_managed_daemon',
                    }),
                )
                out_kh = cfg_journal.apply(
                    'owner', 'b1',
                    {'review_id': rev_kh['review_id'], 'review_digest': rev_kh['review_digest'], 'confirmed': True},
                    apply_host_configuration,
                )['outcome']
                assert out_kh['state'] == 'applied' and out_kh['restart_performed'] is True, out_kh

                # Re-open client & encrypt database at rest
                client2 = network._create_client(perms, attachment_mode='network')
                stack.callback(client2.close)
                visual2 = ProviderVisualAdministration(ctx, perms, 'firebird', '5.0.4', client2)
                db_res2 = next(
                    item for item in client2.list_resources({'route': enc_route})
                    if item['resource_kind'] == 'database'
                )
                plan_enc = visual2.plan({
                    '_provider_route': enc_route,
                    'resource_kind': 'database',
                    'operation_id': 'encrypt_database',
                    'target_resource': db_res2,
                    'draft': enc_draft,
                })
                app_enc = visual2.apply({
                    'plan_id': plan_enc['plan_id'],
                    'plan_digest': plan_enc['plan_digest'],
                    'confirmed': True,
                })
                assert app_enc['provider_result']['commit_requested'] is True, app_enc
                enc_proof['live_statements'].append(enc_sql)

                settled_enc = wait_for_encryption_settle(client2, enc_route, 1, timeout_seconds=20, host_scope=enc_scope)
                assert settled_enc['settled'] is True and settled_enc['crypt_state_code'] == 1, settled_enc
                assert settled_enc['encryption_plugin'] == 'fbSampleDbCrypt'
                assert settled_enc['encryption_key_name'] == 'OWNED'
                assert settled_enc['sample_non_secure_plugin_active'] is True

                # Independent reopen & row read-back
                client2.close()
                client3 = network._create_client(perms, attachment_mode='network')
                stack.callback(client3.close)
                rconn = client3._connect({'route': enc_route})
                try:
                    cur = rconn.cursor()
                    cur.execute('SELECT ID, PAYLOAD FROM SECRET_LEDGER ORDER BY ID')
                    rows_enc = cur.fetchall()
                    assert len(rows_enc) == 2 and '東京' in rows_enc[0][1]
                    cur.close()
                    rconn.rollback()
                finally:
                    client3._forget_and_close(rconn)
                enc_proof['checks'].append(
                    'encrypt_database settled at MON$CRYPT_STATE=1 with fbSampleDbCrypt/OWNED and verified independent reopen + UTF-8 row read-back'
                )

                # 1c. Simulate KeyHolder key loss -> verify native open failure -> restore key -> verify recovery
                client3.close()
                stop_managed_daemon_process(enc_scope)
                (enc_stage / 'plugins/fbSampleKeyHolder.conf').write_text('Auto = true\nOnlyOwnKey = false\n', encoding='utf-8')
                start_managed_daemon_process(enc_scope)

                key_loss_blocked = False
                try:
                    bad_conn = fb_driver.connect(
                        f'127.0.0.1/{enc_port}:{vault_db}',
                        user='SYSDBA', password=enc_pw, charset='UTF8',
                    )
                    cur = bad_conn.cursor()
                    cur.execute('SELECT COUNT(*) FROM SECRET_LEDGER')
                    cur.fetchall()
                    bad_conn.close()
                except Exception as err:
                    key_loss_blocked = 'Crypt key' in str(err) or 'encrypted' in str(err).lower() or 'OWNED' in str(err)
                assert key_loss_blocked

                # Restore key in KeyHolder and restart daemon
                stop_managed_daemon_process(enc_scope)
                (enc_stage / 'plugins/fbSampleKeyHolder.conf').write_text('Auto = true\nKeyOWNED = 90\nOnlyOwnKey = false\n', encoding='utf-8')
                start_managed_daemon_process(enc_scope)

                client4 = network._create_client(perms, attachment_mode='network')
                stack.callback(client4.close)
                visual4 = ProviderVisualAdministration(ctx, perms, 'firebird', '5.0.4', client4)
                db_res4 = next(
                    item for item in client4.list_resources({'route': enc_route})
                    if item['resource_kind'] == 'database'
                )
                dec_draft = {
                    'confirmation': str(vault_db),
                    'confirm_plaintext_storage': True,
                }
                plan_dec = visual4.plan({
                    '_provider_route': enc_route,
                    'resource_kind': 'database',
                    'operation_id': 'decrypt_database',
                    'target_resource': db_res4,
                    'draft': dec_draft,
                })
                dec_sql = plan_dec['command_preview']['statements'][0]['source']
                assert dec_sql == 'ALTER DATABASE DECRYPT'
                enc_proof['parser_statements'].append(dec_sql)

                app_dec = visual4.apply({
                    'plan_id': plan_dec['plan_id'],
                    'plan_digest': plan_dec['plan_digest'],
                    'confirmed': True,
                })
                assert app_dec['provider_result']['commit_requested'] is True, app_dec
                enc_proof['live_statements'].append(dec_sql)

                settled_dec = wait_for_encryption_settle(client4, enc_route, 0, timeout_seconds=20, host_scope=enc_scope)
                assert settled_dec['settled'] is True and settled_dec['crypt_state_code'] == 0, settled_dec

                pconn = client4._connect({'route': enc_route})
                try:
                    cur = pconn.cursor()
                    cur.execute('SELECT COUNT(*) FROM SECRET_LEDGER')
                    assert cur.fetchone()[0] == 2
                    cur.close()
                    pconn.rollback()
                finally:
                    client4._forget_and_close(pconn)
                client4.close()
                enc_proof['checks'].append(
                    'Simulated KeyHolder key loss refused encrypted access; key restoration + decrypt_database settled at MON$CRYPT_STATE=0 with full row preservation'
                )
        finally:
            try:
                stop_managed_daemon_process(enc_scope)
            except Exception:
                pass

        # =====================================================================
        # PART 2: FB-AUD-04 — Two-process native journal replication & promotion
        # =====================================================================
        pri_stage = area / 'pri_runtime'
        rep_stage = area / 'rep_runtime'
        pri_data = area / 'pri_data'
        rep_data = area / 'rep_data'
        journals_root = area / 'journals'
        j_active = journals_root / 'pri_active'
        j_archive = journals_root / 'pri_archive'
        j_rep_src = journals_root / 'rep_source'
        pri_data.mkdir()
        rep_data.mkdir()
        journals_root.mkdir()

        for stg in (pri_stage, rep_stage):
            _stage_runtime(runtime, stg)
            _materialize_writable_runtime(stg)
            (stg / 'firebird.conf').write_text(
                (stg / 'firebird.conf').read_text(encoding='utf-8').rstrip()
                + '\nServerMode = SuperClassic\nAuthServer = Srp256, Srp\nUserManager = Srp\nWireCrypt = Enabled\n',
                encoding='utf-8',
            )

        pri_pw = 'Pri' + secrets.token_hex(8) + '!9'
        rep_pw = 'Rep' + secrets.token_hex(8) + '!9'
        _initialize_security(pri_stage, pri_pw, {
            **os.environ,
            'FIREBIRD': str(pri_stage),
            'FIREBIRD_LOCK': str(pri_stage / 'lock'),
            'LD_LIBRARY_PATH': str(pri_stage / 'lib'),
        })
        _initialize_security(rep_stage, rep_pw, {
            **os.environ,
            'FIREBIRD': str(rep_stage),
            'FIREBIRD_LOCK': str(rep_stage / 'lock'),
            'LD_LIBRARY_PATH': str(rep_stage / 'lib'),
        })
        os.environ.update(
            FIREBIRD=str(pri_stage),
            FIREBIRD_LOCK=str(pri_stage / 'lock'),
            CDEADMIN_FIREBIRD_CLIENT_LIBRARY=str(pri_stage / 'lib/libfbclient.so.5.0.4'),
        )
        fb_driver.driver_config.fb_client_library.value = str(pri_stage / 'lib/libfbclient.so.5.0.4')

        pri_port = _free_port()
        rep_port = _free_port()
        pri_db = pri_data / 'primary_orders.fdb'
        rep_db = rep_data / 'replica_orders.fdb'

        pri_scope = {
            'attachment_mode': 'same_host_granted_network',
            'platform': 'linux',
            'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text(encoding='utf-8').strip(),
            'hostname': 'localhost',
            'engine_version': '5.0.4',
            'firebird_runtime_root': str(pri_stage),
            'firebird_lock_directory': str(pri_stage / 'lock'),
            'staging_directory': str(rep_data),
            'journal_directories': [str(journals_root)],
            'allowed_databases': [str(pri_db), str(rep_db)],
            'allow_host_administration': True,
            'managed_daemon': {
                'pid_file': str(area / 'pri.pid'),
                'port': pri_port,
                'bind_host': '127.0.0.1',
                'server_log': str(area / 'pri.log'),
            },
        }
        rep_scope = {
            **pri_scope,
            'firebird_runtime_root': str(rep_stage),
            'firebird_lock_directory': str(rep_stage / 'lock'),
            'managed_daemon': {
                'pid_file': str(area / 'rep.pid'),
                'port': rep_port,
                'bind_host': '127.0.0.1',
                'server_log': str(area / 'rep.log'),
            },
        }

        start_managed_daemon_process(pri_scope)
        start_managed_daemon_process(rep_scope)
        try:
            with ExitStack() as stack:
                def _client_holder(perms_obj):
                    cl = network._create_client(perms_obj, attachment_mode='network')
                    return SimpleNamespace(client=cl, close=cl.close)

                pri_route, p_perms = provider_access({
                    'host': '127.0.0.1', 'port': pri_port, 'database': str(pri_db),
                    'user': 'SYSDBA', 'charset': 'UTF8', 'wire_crypt': 'Enabled', 'trusted_auth': False,
                }, pri_pw)
                rep_route, r_perms = provider_access({
                    'host': '127.0.0.1', 'port': rep_port, 'database': str(rep_db),
                    'user': 'SYSDBA', 'charset': 'UTF8', 'wire_crypt': 'Enabled', 'trusted_auth': False,
                }, rep_pw)
                p_perms.require = lambda *_: None
                p_perms.allows = lambda *_: True
                r_perms.require = lambda *_: None
                r_perms.allows = lambda *_: True

                pri_prov = _client_holder(p_perms)
                rep_prov = _client_holder(r_perms)
                stack.callback(pri_prov.close)
                stack.callback(rep_prov.close)

                c_pri = pri_prov.client.config.database_creator(
                    **pri_prov.client.config.database_create_arguments(pri_route, str(pri_db), {}),
                    password=pri_pw,
                )
                c_pri.close()
                conn = pri_prov.client._connect({'route': pri_route})
                try:
                    conn.execute_immediate(
                        'CREATE TABLE ORDERS (ORDER_ID INTEGER NOT NULL PRIMARY KEY, CUSTOMER VARCHAR(60), AMOUNT NUMERIC(12,2))'
                    )
                    conn.commit()
                    conn.execute_immediate("INSERT INTO ORDERS VALUES (1, 'Seeded-Customer', 100.50)")
                    conn.commit()
                finally:
                    pri_prov.client._forget_and_close(conn)

                repl_journal = HostActions(
                    area / 'repl-journal.json', 'fb_repl',
                    {'configure_primary', 'seed_replica', 'distribute_segments', 'promote_replica'},
                )

                # 2a. Configure primary & restart primary daemon so replication.conf takes effect
                rev_cfg = repl_journal.review(
                    'owner', 'b_pri', 'configure_primary',
                    prepare_replication_review(pri_scope, {
                        'operation': 'configure_primary',
                        'primary_database_path': str(pri_db),
                        'journal_directory': str(j_active),
                        'journal_archive_directory': str(j_archive),
                        'journal_archive_timeout': 1,
                        'include_all_tables': True,
                        'enable_publication': True,
                    }, pri_prov.client, pri_route),
                )
                out_cfg = repl_journal.apply(
                    'owner', 'b_pri',
                    {'review_id': rev_cfg['review_id'], 'review_digest': rev_cfg['review_digest'], 'confirmed': True},
                    lambda rec: apply_replication_operation(rec, pri_prov.client, pri_route),
                )['outcome']
                assert out_cfg['state'] == 'configured', out_cfg

                pri_prov.close()
                stop_managed_daemon_process(pri_scope)
                start_managed_daemon_process(pri_scope)
                pri_prov = _client_holder(p_perms)
                stack.callback(pri_prov.close)

                # 2b. Seed replica preserving GUID & internal sequence
                def _rep_srv():
                    return fb_driver.connect_server(f'127.0.0.1/{rep_port}', user='SYSDBA', password=rep_pw)

                rev_seed = repl_journal.review(
                    'owner', 'b_pri', 'seed_replica',
                    prepare_replication_review(pri_scope, {
                        'operation': 'seed_replica',
                        'primary_database_path': str(pri_db),
                        'replica_database_path': str(rep_db),
                        'replica_runtime_root': str(rep_stage),
                        'journal_source_directory': str(j_rep_src),
                        'replica_mode': 'READ_ONLY',
                        'apply_idle_timeout': 1,
                        'apply_error_timeout': 2,
                        'confirmation': rep_db.name,
                    }, pri_prov.client, pri_route),
                )
                out_seed = repl_journal.apply(
                    'owner', 'b_pri',
                    {'review_id': rev_seed['review_id'], 'review_digest': rev_seed['review_digest'], 'confirmed': True},
                    lambda rec: apply_replication_operation(
                        rec, pri_prov.client, pri_route, replica_service_connect=_rep_srv,
                    ),
                )['outcome']
                assert out_seed['state'] == 'seeded', out_seed

                # Restart replica daemon so its replication.conf applier attaches cleanly
                rep_prov.close()
                stop_managed_daemon_process(rep_scope)
                start_managed_daemon_process(rep_scope)
                rep_prov = _client_holder(r_perms)
                stack.callback(rep_prov.close)

                pri_state = inspect_replication_state(
                    {**pri_scope, 'journal_directories': [str(j_archive)]}, pri_prov.client, pri_route
                )
                rep_state = inspect_replication_state(
                    {**rep_scope, 'journal_directories': [str(j_rep_src)]}, rep_prov.client, rep_route
                )
                assert pri_state['database']['database_guid'] == rep_state['database']['database_guid']
                assert rep_state['database']['replica_mode'] == 'READ_ONLY'
                assert rep_state['automatic_failover_supported'] is False

                # Direct SQL writes to READ_ONLY replica must be natively rejected by Firebird
                ro_write_rejected = False
                rc_ro = rep_prov.client._connect({'route': rep_route})
                try:
                    try:
                        rc_ro.execute_immediate("INSERT INTO ORDERS VALUES (999, 'Forbidden-Replica-Write', 1.00)")
                        rc_ro.commit()
                    except Exception:
                        ro_write_rejected = True
                        rc_ro.rollback()
                finally:
                    rep_prov.client._forget_and_close(rc_ro)
                assert ro_write_rejected

                # Write rows on primary to generate journal segments
                conn = pri_prov.client._connect({'route': pri_route})
                try:
                    conn.execute_immediate("INSERT INTO ORDERS VALUES (2, 'Replicated-Tokyo-東京', 250.75)")
                    conn.execute_immediate("UPDATE ORDERS SET AMOUNT = 125.00 WHERE ORDER_ID = 1")
                    conn.commit()
                finally:
                    pri_prov.client._forget_and_close(conn)

                # Wait up to 8s for primary journal archive timeout (1s) to flush segment(s) into j_archive
                deadline = time.monotonic() + 8.0
                arch_scan = None
                while time.monotonic() < deadline:
                    arch_scan = inspect_replication_state(
                        {**pri_scope, 'journal_directories': [str(j_archive)]}
                    )['journal_directories'][0]
                    if arch_scan['segment_count'] >= 1:
                        break
                    time.sleep(0.25)
                assert arch_scan and arch_scan['segment_count'] >= 1, arch_scan
                repl_proof['checks'].append(
                    'Primary publication + online backup-state seeding preserved DB_GUID and archived native journal segments'
                )

                # 2c. Verify duplicate-segment refusal & sequence-gap refusal before clean distribution
                first_seg = arch_scan['segments'][0]
                gap_dir = journals_root / 'gap_test'
                gap_dir.mkdir()
                (gap_dir / 'pri.journal-000000001').write_bytes(b's1')
                (gap_dir / 'pri.journal-000000003').write_bytes(b's3')
                gap_refused = False
                try:
                    prepare_replication_review(pri_scope, {
                        'operation': 'distribute_segments',
                        'source_archive_directory': str(gap_dir),
                        'target_source_directory': str(j_rep_src),
                    })
                except ValueError as err:
                    gap_refused = 'sequence gaps' in str(err)
                assert gap_refused
                shutil.rmtree(gap_dir)

                # Ship segments to replica and wait for replica applier to apply & delete consumed segments
                rev_dist = repl_journal.review(
                    'owner', 'b_pri', 'distribute_segments',
                    prepare_replication_review(pri_scope, {
                        'operation': 'distribute_segments',
                        'source_archive_directory': str(j_archive),
                        'target_source_directory': str(j_rep_src),
                    }),
                )
                # Pre-create duplicate file at destination to prove duplicate-segment refusal, then remove it and apply cleanly
                dup_target = j_rep_src / first_seg['relative_path']
                dup_target.parent.mkdir(parents=True, exist_ok=True)
                dup_target.write_bytes(b'existing-duplicate')
                dup_out = apply_replication_operation(
                    {'payload': prepare_replication_review(pri_scope, {
                        'operation': 'distribute_segments',
                        'source_archive_directory': str(j_archive),
                        'target_source_directory': str(j_rep_src),
                    })}
                )
                assert dup_out['state'] == 'rejected' and 'Duplicate segment refused' in dup_out['reason']
                dup_target.unlink()

                out_dist = repl_journal.apply(
                    'owner', 'b_pri',
                    {'review_id': rev_dist['review_id'], 'review_digest': rev_dist['review_digest'], 'confirmed': True},
                    apply_replication_operation,
                )['outcome']
                assert out_dist['state'] == 'distributed' and out_dist['shipped_count'] >= 1, out_dist

                # Wait for replica daemon to replicate rows & clear j_rep_src
                replicated_rows = []
                deadline = time.monotonic() + 12.0
                while time.monotonic() < deadline:
                    rc = rep_prov.client._connect({'route': rep_route})
                    try:
                        cur = rc.cursor()
                        cur.execute('SELECT ORDER_ID, CUSTOMER, CAST(AMOUNT AS VARCHAR(20)) FROM ORDERS ORDER BY ORDER_ID')
                        replicated_rows = cur.fetchall()
                        cur.close()
                        rc.rollback()
                    finally:
                        rep_prov.client._forget_and_close(rc)
                    if len(replicated_rows) == 2 and float(replicated_rows[0][2]) == 125.0:
                        break
                    time.sleep(0.25)
                assert len(replicated_rows) == 2 and '東京' in replicated_rows[1][1], replicated_rows
                repl_proof['checks'].append(
                    'Journal distribution applied on live replica daemon with sequence-gap & duplicate-segment refusals verified'
                )

                # 2d. Replica stop/lag/promotion guard & restart catch-up recovery
                rep_prov.close()
                stop_managed_daemon_process(rep_scope)

                # Clear previously shipped archive files so next distribution ships only new segment(s)
                for seg_item in arch_scan['segments']:
                    (j_archive / seg_item['relative_path']).unlink(missing_ok=True)

                conn = pri_prov.client._connect({'route': pri_route})
                try:
                    conn.execute_immediate("INSERT INTO ORDERS VALUES (3, 'Offline-Catchup-Row', 999.00)")
                    conn.commit()
                finally:
                    pri_prov.client._forget_and_close(conn)

                deadline = time.monotonic() + 8.0
                arch_scan2 = None
                while time.monotonic() < deadline:
                    arch_scan2 = inspect_replication_state(
                        {**pri_scope, 'journal_directories': [str(j_archive)]}
                    )['journal_directories'][0]
                    if arch_scan2['segment_count'] >= 1:
                        break
                    time.sleep(0.25)
                assert arch_scan2 and arch_scan2['segment_count'] >= 1

                rev_dist2 = repl_journal.review(
                    'owner', 'b_pri', 'distribute_segments',
                    prepare_replication_review(pri_scope, {
                        'operation': 'distribute_segments',
                        'source_archive_directory': str(j_archive),
                        'target_source_directory': str(j_rep_src),
                    }),
                )
                out_dist2 = repl_journal.apply(
                    'owner', 'b_pri',
                    {'review_id': rev_dist2['review_id'], 'review_digest': rev_dist2['review_digest'], 'confirmed': True},
                    apply_replication_operation,
                )['outcome']
                assert out_dist2['state'] == 'distributed'

                # Promotion MUST refuse while unapplied segments sit in j_rep_src!
                unapplied_promo_refused = False
                try:
                    prepare_replication_review(rep_scope, {
                        'operation': 'promote_replica',
                        'replica_database_path': str(rep_db),
                        'journal_source_directory': str(j_rep_src),
                        'promotion_confirmed': True,
                        'confirmation': rep_db.name,
                    })
                except ValueError as err:
                    unapplied_promo_refused = 'unapplied journal segment' in str(err)
                assert unapplied_promo_refused

                # Restart replica daemon and verify catch-up of ORDER_ID=3 and queue drain -> 0
                start_managed_daemon_process(rep_scope)
                rep_prov2 = _client_holder(r_perms)
                stack.callback(rep_prov2.close)

                caught_up = False
                deadline = time.monotonic() + 12.0
                while time.monotonic() < deadline:
                    st_rep = inspect_replication_state(
                        {**rep_scope, 'journal_directories': [str(j_rep_src)]}, rep_prov2.client, rep_route
                    )
                    rc = rep_prov2.client._connect({'route': rep_route})
                    try:
                        cur = rc.cursor()
                        cur.execute('SELECT COUNT(*) FROM ORDERS')
                        cnt = cur.fetchone()[0]
                        cur.close()
                        rc.rollback()
                    finally:
                        rep_prov2.client._forget_and_close(rc)
                    if cnt == 3 and st_rep['journal_directories'][0]['segment_count'] == 0:
                        caught_up = True
                        break
                    time.sleep(0.25)
                assert caught_up
                repl_proof['checks'].append(
                    'Stopped-replica lag queue blocked unconfirmed promotion and cleanly caught up on daemon restart'
                )

                # 2e. Manual reviewed promotion to standalone READ_WRITE and independent write verification
                rev_promo = repl_journal.review(
                    'owner', 'b_rep', 'promote_replica',
                    prepare_replication_review(rep_scope, {
                        'operation': 'promote_replica',
                        'replica_database_path': str(rep_db),
                        'journal_source_directory': str(j_rep_src),
                        'promotion_confirmed': True,
                        'confirmation': rep_db.name,
                    }),
                )
                out_promo = repl_journal.apply(
                    'owner', 'b_rep',
                    {'review_id': rev_promo['review_id'], 'review_digest': rev_promo['review_digest'], 'confirmed': True},
                    lambda rec: apply_replication_operation(rec, rep_prov2.client, rep_route, replica_service_connect=_rep_srv),
                )['outcome']
                assert out_promo['state'] == 'promoted' and out_promo['automatic_failover_used'] is False

                post_promo = inspect_replication_state(
                    {**rep_scope, 'journal_directories': [str(j_rep_src)]}, rep_prov2.client, rep_route
                )
                assert post_promo['database']['replica_mode'] == 'NONE'
                assert post_promo['database']['read_only'] is False

                wconn = rep_prov2.client._connect({'route': rep_route})
                try:
                    wconn.execute_immediate("INSERT INTO ORDERS VALUES (4, 'Standalone-Promoted-Write', 500.00)")
                    wconn.commit()
                    cur = wconn.cursor()
                    cur.execute('SELECT COUNT(*) FROM ORDERS')
                    assert cur.fetchone()[0] == 4
                    cur.close()
                    wconn.rollback()
                finally:
                    rep_prov2.client._forget_and_close(wconn)
                rep_prov2.close()
                pri_prov.close()
                repl_proof['checks'].append(
                    'Manual reviewed promote_replica switched replica_mode=NONE + READ_WRITE and verified standalone writes'
                )
        finally:
            for sc in (pri_scope, rep_scope):
                try:
                    stop_managed_daemon_process(sc)
                except Exception:
                    pass

    unchanged = _runtime_fingerprint(runtime) == before
    removed = not area.exists()
    enc_proof['owned_state_removed'] = removed
    enc_proof['source_runtime_unchanged'] = unchanged
    enc_proof['complete'] = unchanged and removed and len(enc_proof['checks']) == 3

    repl_proof['owned_state_removed'] = removed
    repl_proof['source_runtime_unchanged'] = unchanged
    repl_proof['complete'] = unchanged and removed and len(repl_proof['checks']) == 4

    (output / 'database-encryption-native.json').write_text(
        json.dumps(enc_proof, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    (output / 'replication-native.json').write_text(
        json.dumps(repl_proof, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    return {'encryption': enc_proof, 'replication': repl_proof}


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
        'format': 'cdeadmin.firebird-encryption-replication-http.v1',
        'complete': False,
        'history_tests': 'not run',
        'checks': [],
    }
    prev_manifest = os.environ.get('CDEADMIN_FIREBIRD_HOST_TOOLS_MANIFEST')
    try:
        with tempfile.TemporaryDirectory(prefix='cdeadmin-fb-enc-repl-http-') as temp, ExitStack() as stack:
            root = Path(temp).resolve()
            stage = root / 'runtime'
            data = root / 'data'
            journals = root / 'journals'
            data.mkdir()
            journals.mkdir()
            _stage_runtime(runtime, stage)
            _materialize_writable_runtime(stage)
            (stage / 'firebird.conf').write_text(
                'ServerMode = SuperClassic\nProviders = Engine13\n'
                f'SecurityDatabase = {stage / "security5.fdb"}\n',
                encoding='utf-8',
            )
            os.environ['FIREBIRD'] = str(stage)
            os.environ['FIREBIRD_LOCK'] = str(stage / 'lock')
            os.environ['LD_LIBRARY_PATH'] = str(stage / 'lib')
            os.environ['CDEADMIN_FIREBIRD_CLIENT_LIBRARY'] = str(stage / 'lib/libfbclient.so.5.0.4')
            import firebird.driver as fb_mod
            fb_mod.driver_config.fb_client_library.value = str(stage / 'lib/libfbclient.so.5.0.4')

            app = setup_application(root)

            def close_app():
                from pgadmin.cdeadmin.workspace.service import service_for_app
                with app.app_context():
                    service_for_app(app).endpoint_service.provider_registry.close()
            stack.callback(close_app)

            from flask import url_for
            from pgadmin.model import EndpointDatabaseTarget, Server, ServerGroup, User, db
            from pgadmin.cdeadmin.endpoints.profiles import registration_profile
            from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
            from pgadmin.cdeadmin.providers.firebird.provider import _create_client

            db_path = data / 'http_enc_repl.fdb'
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
                    user_id=uid, servergroup_id=group.id, name='HTTP Enc & Repl',
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

            # 1. firebird_database_encryption describe + inspect + visual_admin_plan over HTTP
            enc_desc = http.post(url, json={'action': 'firebird_database_encryption', 'request': {'action': 'describe'}})
            assert enc_desc.status_code == 200 and enc_desc.headers.get('Cache-Control') == 'no-store'
            assert enc_desc.get_json()['data']['application_implements_cryptography'] is False

            enc_insp = http.post(url, json={
                'action': 'firebird_database_encryption',
                'database_target_id': tid,
                'request': {'action': 'inspect', 'database_target_id': tid},
            }).get_json()
            assert enc_insp['success'] and enc_insp['data']['crypt_state_code'] == 0

            initial = http.get(url, query_string={'database_target_id': tid}).get_json()
            assert initial['success'], initial
            gen = initial['data']['resource_page']['generation']
            res_list = http.post(url, json={
                'action': 'resource_refresh',
                'database_target_id': tid,
                'request': {'database_target_id': tid, 'generation': gen},
            }).get_json()['data']['items']
            db_target_res = next(r for r in res_list if r.get('kind') == 'database' or r.get('resource_kind') == 'database')

            plan_enc_http = http.post(url, json={
                'action': 'visual_admin_plan',
                'database_target_id': tid,
                'request': {
                    'database_target_id': tid,
                    'resource_kind': 'database',
                    'operation_id': 'encrypt_database',
                    'target_resource': db_target_res,
                    'draft': {
                        'confirmation': str(db_path),
                        'crypt_plugin': 'fbSampleDbCrypt',
                        'key_name': 'OWNED',
                        'confirm_key_recovery_responsibility': True,
                    },
                },
            }).get_json()
            assert plan_enc_http['success'], plan_enc_http
            assert plan_enc_http['data']['command_preview']['statements'][0]['source'] == 'ALTER DATABASE ENCRYPT WITH "fbSampleDbCrypt" KEY "OWNED"'
            proof['checks'].append('HTTP firebird_database_encryption describe/inspect and encrypt_database visual_admin_plan verified')

            # 2. firebird_replication read-only refusal + full configure_primary review/apply/one-use retirement
            ro_manifest = root / 'ro-repl.json'
            ro_manifest.write_text(json.dumps({
                'format': 'scratchrobin.firebird.host-tools@1',
                'grants': [{
                    'endpoint_id': ep_id,
                    'firebird_runtime_root': str(stage),
                    'firebird_lock_directory': str(stage / 'lock'),
                    'databases': [str(db_path)],
                    'journal_directories': [str(journals)],
                    'allow_host_administration': False,
                }],
            }), encoding='utf-8')
            os.environ['CDEADMIN_FIREBIRD_HOST_TOOLS_MANIFEST'] = str(ro_manifest)
            ro_insp = http.post(url, json={'action': 'firebird_replication', 'database_target_id': tid, 'request': {'action': 'inspect', 'database_target_id': tid}})
            assert ro_insp.status_code == 200 and ro_insp.get_json()['success']
            ro_rev = http.post(url, json={
                'action': 'firebird_replication',
                'database_target_id': tid,
                'request': {
                    'action': 'review',
                    'database_target_id': tid,
                    'operation': 'configure_primary',
                    'journal_directory': str(journals / 'active'),
                    'journal_archive_directory': str(journals / 'archive'),
                },
            }).get_json()
            assert not ro_rev.get('success')

            rw_manifest = root / 'rw-repl.json'
            rw_manifest.write_text(json.dumps({
                'format': 'scratchrobin.firebird.host-tools@1',
                'grants': [{
                    'endpoint_id': ep_id,
                    'firebird_runtime_root': str(stage),
                    'firebird_lock_directory': str(stage / 'lock'),
                    'databases': [str(db_path)],
                    'journal_directories': [str(journals)],
                    'allow_host_administration': True,
                }],
            }), encoding='utf-8')
            os.environ['CDEADMIN_FIREBIRD_HOST_TOOLS_MANIFEST'] = str(rw_manifest)

            rw_rev = http.post(url, json={
                'action': 'firebird_replication',
                'database_target_id': tid,
                'request': {
                    'action': 'review',
                    'database_target_id': tid,
                    'operation': 'configure_primary',
                    'journal_directory': str(journals / 'active'),
                    'journal_archive_directory': str(journals / 'archive'),
                },
            }).get_json()
            assert rw_rev['success'], rw_rev
            rw_app = http.post(url, json={
                'action': 'firebird_replication',
                'database_target_id': tid,
                'request': {
                    'action': 'apply',
                    'database_target_id': tid,
                    'review_id': rw_rev['data']['review_id'],
                    'review_digest': rw_rev['data']['review_digest'],
                    'confirmed': True,
                },
            }).get_json()
            assert rw_app['success'] and rw_app['data']['outcome']['state'] == 'configured', rw_app

            replay = http.post(url, json={
                'action': 'firebird_replication',
                'database_target_id': tid,
                'request': {
                    'action': 'apply',
                    'database_target_id': tid,
                    'review_id': rw_rev['data']['review_id'],
                    'review_digest': rw_rev['data']['review_digest'],
                    'confirmed': True,
                },
            }).get_json()
            assert not replay.get('success')
            proof['checks'].append('HTTP firebird_replication read-only refusal, configure_primary review/apply and one-use retirement verified')

        proof['owned_state_removed'] = not root.exists()
        proof['source_runtime_unchanged'] = _runtime_fingerprint(runtime) == before
        proof['complete'] = proof['owned_state_removed'] and proof['source_runtime_unchanged'] and len(proof['checks']) == 2
    finally:
        if prev_manifest is None:
            os.environ.pop('CDEADMIN_FIREBIRD_HOST_TOOLS_MANIFEST', None)
        else:
            os.environ['CDEADMIN_FIREBIRD_HOST_TOOLS_MANIFEST'] = prev_manifest
        (output / 'http.json').write_text(json.dumps(proof, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('all', 'native', 'http'), default='all')
    args = parser.parse_args()
    if args.mode == 'native':
        res = qualify_native(args.runtime, args.output)
        ok = res['encryption']['complete'] and res['replication']['complete']
        print(json.dumps({'complete': ok}))
        raise SystemExit(0 if ok else 1)
    if args.mode == 'http':
        res = qualify_http(args.runtime, args.output)
        print(json.dumps({'http_complete': res['complete']}))
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
    ok = bool(nres['encryption']['complete'] and nres['replication']['complete'] and hres.get('complete'))
    print(json.dumps({'complete': ok}))
    raise SystemExit(0 if ok else 1)

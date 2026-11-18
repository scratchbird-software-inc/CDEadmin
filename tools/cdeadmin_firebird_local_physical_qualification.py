"""Qualify owned Engine13 physical backup and physical restore (native + authenticated HTTP).

Exercises backup_physical (nbackup) and restore_physical (nrestore) on disposable
Engine13 5.0.4 fixtures without starting a network listener or modifying the
read-only runtime kit.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]

SOURCE_PATHS = [
    'web/pgadmin/cdeadmin/providers/firebird/local_services.py',
    'web/pgadmin/cdeadmin/providers/firebird/local_physical_backup.py',
    'web/pgadmin/cdeadmin/providers/firebird/local_physical_restore.py',
    'web/pgadmin/cdeadmin/providers/firebird/embedded_provider.py',
    'web/pgadmin/cdeadmin/providers/firebird/query_client.py',
    'web/pgadmin/cdeadmin/providers/firebird/provider.py',
    'web/pgadmin/cdeadmin/providers/firebird/restore_policy.py',
    'web/pgadmin/cdeadmin/providers/firebird/physical_io.py',
    'web/pgadmin/cdeadmin/providers/firebird/backup_guid.py',
    'web/pgadmin/cdeadmin/providers/firebird/embedded_provider_manifest.json',
    'web/pgadmin/cdeadmin/providers/firebird/firebird_embedded_dialect_5_0_4.json',
    'web/pgadmin/cdeadmin/providers/firebird/firebird_embedded_metrics_5_0_4.json',
    'web/pgadmin/cdeadmin/providers/relational_admin.py',
    'web/pgadmin/cdeadmin/visual_admin/provider.py',
    'web/pgadmin/cdeadmin/ui_descriptors/firebird/capabilities.json',
    'web/pgadmin/cdeadmin/ui_descriptors/firebird/operations.json',
    'tools/cdeadmin_firebird_local_physical_qualification.py',
]


def _source_hashes():
    return {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in SOURCE_PATHS
    }


def _readback_db(client, base_route, db_path):
    connection = client._connect({'route': {**base_route, 'database': str(db_path)}})
    try:
        cursor = connection.cursor()
        try:
            cursor.execute('SELECT ID, PAYLOAD FROM OWNED ORDER BY ID')
            rows = []
            for identifier, value in cursor.fetchall():
                if hasattr(value, 'read'):
                    blob = value.read()
                    value.close()
                else:
                    blob = value
                rows.append((identifier, blob))
            cursor.execute('SELECT ID FROM "雪DATA" ORDER BY ID')
            unicode_rows = [r[0] for r in cursor.fetchall()]
            cursor.execute(
                'SELECT MON$DATABASE_NAME, MON$READ_ONLY, MON$GUID FROM MON$DATABASE'
            )
            db_name, read_only, mon_guid = cursor.fetchone()
            cursor.execute(
                'SELECT RDB$BACKUP_LEVEL, RDB$FILE_NAME, RDB$GUID '
                'FROM RDB$BACKUP_HISTORY ORDER BY RDB$BACKUP_ID'
            )
            history = [
                (lvl, fname.strip() if isinstance(fname, str) else fname,
                 guid.strip() if isinstance(guid, str) else guid)
                for lvl, fname, guid in cursor.fetchall()
            ]
            return {
                'rows': rows,
                'unicode_rows': unicode_rows,
                'db_name': db_name.strip() if isinstance(db_name, str) else db_name,
                'read_only': read_only,
                'guid': mon_guid.strip() if isinstance(mon_guid, str) else mon_guid,
                'history': history,
            }
        finally:
            cursor.close()
            connection.rollback()
    finally:
        client._forget_and_close(connection)


def qualify_native(runtime, output):
    from tools.cdeadmin_firebird_object_live_orchestrator import (
        _stage_runtime, _runtime_fingerprint,
    )
    runtime, output = Path(runtime).resolve(), Path(output).resolve()
    if sys.platform != 'linux' or output == ROOT or ROOT in output.parents:
        raise ValueError('Use Linux and keep qualification evidence outside source')
    output.mkdir(parents=True, exist_ok=True)
    proof = {
        'complete': False,
        'checks': [],
        'history_tests': 'not run',
        'scope': (
            'Owned Linux Firebird 5.0.4 Engine13 backup_physical and '
            'restore_physical; no network/platform/UI acceptance'
        ),
        'source_sha256': _source_hashes(),
    }
    before = _runtime_fingerprint(runtime)
    env_keys = ('FIREBIRD', 'FIREBIRD_LOCK', 'CDEADMIN_FIREBIRD_CLIENT_LIBRARY')
    previous_env = {k: os.environ.get(k) for k in env_keys}
    area = None
    try:
        with tempfile.TemporaryDirectory(prefix='firebird-local-phys-', dir=output) as folder:
            area = Path(folder)
            stage = area / 'runtime'
            _stage_runtime(runtime, stage)
            (stage / 'firebird.conf').write_text(
                'Providers = Engine13\nSecurityDatabase = ' + str(stage / 'security5.fdb') + '\n'
            )
            (stage / 'databases.conf').write_text('')
            os.environ.update(
                FIREBIRD=str(stage),
                FIREBIRD_LOCK=str(stage / 'lock'),
                CDEADMIN_FIREBIRD_CLIENT_LIBRARY=str(stage / 'lib/libfbclient.so.5.0.4'),
            )
            import firebird.driver as module
            module.driver_config.fb_client_library.value = str(stage / 'lib/libfbclient.so.5.0.4')
            from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
            from pgadmin.cdeadmin.providers.firebird.provider import _create_client
            from pgadmin.cdeadmin.visual_admin import (
                ProviderVisualAdministration, VisualAdminAccessError, VisualAdminExecutionError,
            )

            permitted = {
                'embedded_runtime', 'filesystem', 'data_read', 'administer',
                'execute', 'maintenance_admin', 'backup_admin', 'restore_admin',
            }

            def require(name, *_):
                if name not in permitted:
                    raise PermissionError(name)

            def secret(*_):
                raise AssertionError('Local physical backup/restore acquired a network credential')

            permissions = SimpleNamespace(
                require=require,
                allows=lambda name, *_: name in permitted,
                acquire_secret=secret,
            )
            client = _create_client(
                permissions, attachment_mode='embedded',
                profile=embedded.PROFILE, administration=embedded.ADMINISTRATION,
            )
            native_runner = client.config.server_operation_runner

            def observed_runner(server, operation, database, options):
                try:
                    return native_runner(server, operation, database, options)
                except Exception as error:
                    proof['last_owned_native_error'] = {
                        'operation': operation,
                        'message': str(error)[:8192],
                        'status_codes': list(getattr(error, 'gds_codes', ()))[:32],
                    }
                    raise

            client.config = replace(client.config, server_operation_runner=observed_runner)
            context = SimpleNamespace(
                endpoint_id='owned-physical', mode='provider_native',
                provider_id=embedded.PROFILE.provider_id,
                profile_id=embedded.PROFILE.profile_id,
                runtime_verification_state='verified',
                declared_runtime_family='firebird', verified_runtime_family='firebird',
            )
            visual = ProviderVisualAdministration(context, permissions, 'firebird', '5.0.4', client)
            data = area / 'data'
            data.mkdir()
            route = {
                'attachment_mode': 'embedded',
                'database': str(data / "primary 雪's.fdb"),
                'filesystem_root': str(data),
                'user': 'SYSDBA',
                'charset': 'UTF8',
            }

            def make_payload(idx):
                return (idx, hashlib.shake_256(f'phys-{idx}'.encode()).digest(2500))

            base_payloads = [make_payload(i) for i in range(1, 21)]
            creator = client.config.database_creator(
                **client.config.database_create_arguments(route, route['database'], {})
            )
            try:
                creator.execute_immediate(
                    'CREATE TABLE OWNED(ID INTEGER NOT NULL PRIMARY KEY, PAYLOAD BLOB SUB_TYPE BINARY)'
                )
                creator.execute_immediate('CREATE TABLE "雪DATA"(ID INTEGER)')
                creator.commit()
                q = creator.cursor()
                try:
                    for identifier, blob in base_payloads:
                        q.execute('INSERT INTO OWNED VALUES(?, ?)', (identifier, blob))
                    q.execute('INSERT INTO "雪DATA" VALUES(23)')
                    creator.commit()
                finally:
                    q.close()
            finally:
                creator.close()

            source_initial = _readback_db(client, route, route['database'])
            source_db_guid = source_initial['guid']

            def review(operation, options, origin=None):
                active_route = origin or route
                request = {
                    'resource_kind': 'database',
                    'operation_id': operation,
                    '_provider_route': active_route,
                    'draft': options,
                }
                if operation not in {'restore_logical', 'restore_physical'}:
                    request['target_resource'] = {
                        'resource_kind': 'database',
                        'resource_id': 'owned-source',
                        'display_name': Path(active_route['database']).name,
                    }
                validation = visual.validate(request)
                assert validation['valid'], validation
                plan = visual.plan(request)
                return {
                    'plan_id': plan['plan_id'],
                    'plan_digest': plan['plan_digest'],
                    'confirmed': True,
                    '_plan': plan,
                }

            def replay_refused(apply_req):
                try:
                    visual.apply({
                        'plan_id': apply_req['plan_id'],
                        'plan_digest': apply_req['plan_digest'],
                        'confirmed': True,
                    })
                except VisualAdminAccessError:
                    return
                raise AssertionError('Consumed one-use review replayed')

            def run_op(operation, options, origin=None, forbid_sql=False):
                connect_orig = client._connect
                if forbid_sql:
                    def forbidden(*_a, **_kw):
                        raise AssertionError('Operation attempted SQL before native service execution')
                    client._connect = forbidden
                try:
                    reviewed = review(operation, options, origin)
                    apply_req = {
                        'plan_id': reviewed['plan_id'],
                        'plan_digest': reviewed['plan_digest'],
                        'confirmed': True,
                    }
                    try:
                        applied = visual.apply(apply_req)['provider_result']
                    finally:
                        replay_refused(reviewed)
                finally:
                    client._connect = connect_orig
                obs = applied['driver_observation']
                assert obs['server_completed'] and obs['native_provider'] == 'Engine13'
                assert not obs['network_authentication']
                if operation in {'backup_physical', 'restore_physical'}:
                    assert not obs['file_identity_race_fenced']
                assert obs['service_release']['connection_released']
                assert obs['service_release']['service_handle_released']
                return applied

            pending = client._connect({'route': route})
            pending.execute_immediate('INSERT INTO "雪DATA" VALUES(999)')
            try:
                # 1. Online physical backup admits concurrent managed SQL without touching pending tx.
                dispatch_orig = client.run_server_operation

                def online_dispatch(*args, **kwargs):
                    def concurrent_read():
                        conn = client._connect({'route': route})
                        try:
                            cur = conn.cursor()
                            cur.execute('SELECT COUNT(*) FROM OWNED')
                            cnt = cur.fetchone()[0]
                            cur.close()
                            conn.rollback()
                            return cnt
                        finally:
                            client._forget_and_close(conn)

                    pool = ThreadPoolExecutor(max_workers=1)
                    try:
                        fut = pool.submit(concurrent_read)
                        assert fut.result(timeout=10) == 20
                    finally:
                        pool.shutdown(wait=False, cancel_futures=True)
                    return dispatch_orig(*args, **kwargs)

                b0 = data / "level0 雪's.nbk"
                client.run_server_operation = online_dispatch
                try:
                    res0 = run_op('backup_physical', {
                        'backup_file': str(b0),
                        'backup_level': 0,
                        'direct_io_mode': 'OFF',
                        'backup_flags': ['NO_TRIGGERS'],
                    })['driver_observation']
                finally:
                    client.run_server_operation = dispatch_orig
                assert res0['outputs_at_reviewed_paths'] is True
                assert res0['restore_verified'] is False
                assert res0['local_physical_backup_outputs'][0]['bytes_observed'] > 0
                assert res0['local_physical_backup_outputs'][0]['native_exclusive_create'] is True
                proof['checks'].append({
                    'case': 'online-level0-backup',
                    'concurrent_sql_admitted': True,
                    'canonical_output_created': True,
                })

                # 2. Backup permission check refuses before output creation.
                denied_nbk = data / 'denied.nbk'
                permitted.remove('backup_admin')
                try:
                    try:
                        review('backup_physical', {'backup_file': str(denied_nbk), 'backup_level': 0})
                    except PermissionError:
                        pass
                    else:
                        raise AssertionError('backup_physical admitted without backup_admin')
                finally:
                    permitted.add('backup_admin')
                assert not denied_nbk.exists()
                proof['checks'].append({'case': 'backup-permission', 'no_output_created': True})

                # 3. Incremental Level 1 + GUID-based incremental + clean_history.
                hist0 = _readback_db(client, route, route['database'])['history']
                assert len(hist0) == 1 and hist0[0][0] == 0 and hist0[0][1] == str(b0)
                b0_backup_guid = hist0[0][2]

                writer = client._connect({'route': route})
                try:
                    cur = writer.cursor()
                    p21 = make_payload(21)
                    cur.execute('INSERT INTO OWNED VALUES(?, ?)', p21)
                    cur.execute('INSERT INTO "雪DATA" VALUES(24)')
                    cur.close()
                    writer.commit()
                finally:
                    client._forget_and_close(writer)

                b1 = data / 'level1 雪.nbk'
                res1 = run_op('backup_physical', {
                    'backup_file': str(b1),
                    'backup_level': 1,
                    'direct_io_mode': 'NATIVE',
                })['driver_observation']
                assert res1['outputs_at_reviewed_paths'] is True

                writer = client._connect({'route': route})
                try:
                    cur = writer.cursor()
                    p22 = make_payload(22)
                    cur.execute('INSERT INTO OWNED VALUES(?, ?)', p22)
                    cur.execute('INSERT INTO "雪DATA" VALUES(25)')
                    cur.close()
                    writer.commit()
                finally:
                    client._forget_and_close(writer)

                b_guid = data / 'guid_delta.nbk'
                res_guid = run_op('backup_physical', {
                    'backup_file': str(b_guid),
                    'backup_level': None,
                    'database_guid': b0_backup_guid,
                    'clean_history': True,
                    'history_keep_unit': 'ROWS',
                    'history_keep_value': 2,
                })['driver_observation']
                assert res_guid['outputs_at_reviewed_paths'] is True
                hist_cleaned = _readback_db(client, route, route['database'])['history']
                assert len(hist_cleaned) == 2
                proof['checks'].append({
                    'case': 'incremental-level1-guid-and-clean-history',
                    'history_rows_kept': len(hist_cleaned),
                })

                # 4. Existing file created after backup review refuses pre-dispatch.
                stale_nbk = data / 'stale.nbk'
                stale_req = review('backup_physical', {'backup_file': str(stale_nbk), 'backup_level': 0})
                stale_nbk.write_bytes(b'foreign nbk bytes')
                try:
                    visual.apply({
                        'plan_id': stale_req['plan_id'],
                        'plan_digest': stale_req['plan_digest'],
                        'confirmed': True,
                    })
                except VisualAdminExecutionError as error:
                    assert error.operation['unknown_outcome'] is False
                else:
                    raise AssertionError('backup_physical overwrote file created after review')
                replay_refused(stale_req)
                assert stale_nbk.read_bytes() == b'foreign nbk bytes'
                proof['checks'].append({
                    'case': 'backup-stale-output',
                    'known_pre_dispatch_refusal': True,
                    'foreign_bytes_preserved': True,
                })

                # 5. Missing base level after clean_history refuses natively (337117235), and lost level-0 response stays unknown/no-replay.
                purged_lvl1 = data / 'purged_base_level1.nbk'
                purged_req = review('backup_physical', {'backup_file': str(purged_lvl1), 'backup_level': 1})
                try:
                    visual.apply({
                        'plan_id': purged_req['plan_id'],
                        'plan_digest': purged_req['plan_digest'],
                        'confirmed': True,
                    })
                except VisualAdminExecutionError as error:
                    assert error.operation['unknown_outcome'] is True
                    assert 337117235 in proof.get('last_owned_native_error', {}).get('status_codes', [])
                else:
                    raise AssertionError('Level 1 backup succeeded after clean_history purged level 0')
                replay_refused(purged_req)

                lost_nbk = data / 'lost_response.nbk'
                lost_req = review('backup_physical', {'backup_file': str(lost_nbk), 'backup_level': 0})
                completed_bkp = []

                def lose_bkp(*args, **kwargs):
                    completed_bkp.append(dispatch_orig(*args, **kwargs))
                    from pgadmin.cdeadmin.sdk import RelationalClientError
                    raise RelationalClientError('Owned qualifier lost completed backup_physical response')

                client.run_server_operation = lose_bkp
                try:
                    try:
                        visual.apply({
                            'plan_id': lost_req['plan_id'],
                            'plan_digest': lost_req['plan_digest'],
                            'confirmed': True,
                        })
                    except VisualAdminExecutionError as error:
                        assert error.operation['unknown_outcome'] is True
                        assert error.operation['impact']['backup_output_files'][0]['filename'] == str(lost_nbk)
                    else:
                        raise AssertionError('Lost backup_physical response reported known success')
                finally:
                    client.run_server_operation = dispatch_orig
                replay_refused(lost_req)
                assert len(completed_bkp) == 1 and lost_nbk.exists() and lost_nbk.stat().st_size > 0
                proof['checks'].append({
                    'case': 'backup-missing-base-337117235-and-lost-response',
                    'clean_history_purged_level0_verified': True,
                    'unknown_no_replay': True,
                    'impact_retains_output_path': True,
                })

                # 6. Restore permission refusal with unavailable original database.
                absent_origin = {
                    **route,
                    'database': str(data / 'absent-parent' / 'unavailable-original.fdb'),
                }
                denied_fdb = data / 'denied_restore.fdb'
                permitted.remove('restore_admin')
                try:
                    try:
                        review('restore_physical', {
                            'backup_files': [str(b0)],
                            'restore_database': str(denied_fdb),
                        }, absent_origin)
                    except PermissionError:
                        pass
                    else:
                        raise AssertionError('restore_physical admitted without restore_admin')
                finally:
                    permitted.add('restore_admin')
                assert not denied_fdb.exists()
                proof['checks'].append({'case': 'restore-permission', 'no_destination_created': True})

                # 7. NEW_DATABASE restore of [b0, b1] without SEQUENCE resets database GUID; direct_io_mode is refused on restore_physical.
                restored_new = data / "restored new 雪's.fdb"
                bad_dio = visual.validate({
                    'resource_kind': 'database',
                    'operation_id': 'restore_physical',
                    '_provider_route': absent_origin,
                    'draft': {
                        'backup_files': [str(b0), str(b1)],
                        'restore_database': str(restored_new),
                        'direct_io_mode': 'OFF',
                    },
                })
                assert not bad_dio['valid']
                applied_new = run_op('restore_physical', {
                    'backup_files': [str(b0), str(b1)],
                    'restore_database': str(restored_new),
                }, absent_origin, forbid_sql=True)
                assert applied_new['driver_observation']['local_restore_files']['inputs_unchanged'] is True
                assert applied_new['driver_observation']['local_restore_files']['data_readback_verified'] is False
                assert applied_new['restored_database_target'] == {
                    'database': str(restored_new),
                    'display_name': restored_new.name,
                    'registration_changed': False,
                }
                rb_new = _readback_db(client, route, restored_new)
                assert rb_new['rows'] == base_payloads + [p21]
                assert rb_new['unicode_rows'] == [23, 24]
                assert rb_new['read_only'] == 0
                assert rb_new['guid'] != source_db_guid
                proof['checks'].append({
                    'case': 'restore-new-database-default-guid-reset',
                    'no_pre_restore_sql': True,
                    'rows_and_blobs_verified': True,
                    'guid_reset_verified': True,
                })

                # 8. Read-only database physical backup refusal (native 335544765).
                ro_route = {**route, 'database': str(restored_new)}
                run_op('set_access_mode', {'mode': 'READ_ONLY'}, ro_route)
                ro_nbk = data / 'readonly_fail.nbk'
                ro_req = review('backup_physical', {'backup_file': str(ro_nbk), 'backup_level': 0}, ro_route)
                try:
                    visual.apply({
                        'plan_id': ro_req['plan_id'],
                        'plan_digest': ro_req['plan_digest'],
                        'confirmed': True,
                    })
                except VisualAdminExecutionError as error:
                    assert error.operation['unknown_outcome'] is True
                    assert 335544765 in proof.get('last_owned_native_error', {}).get('status_codes', [])
                else:
                    raise AssertionError('Read-only source admitted backup_physical')
                replay_refused(ro_req)
                proof['checks'].append({
                    'case': 'backup-readonly-source-native-refusal',
                    'native_status_335544765': True,
                    'unknown_no_replay': True,
                })

                # 9. NEW_DATABASE restore of [b0, b_guid] with SEQUENCE preserves GUID and restores GUID-based delta!
                restored_seq = data / 'restored_sequence.fdb'
                run_op('restore_physical', {
                    'backup_files': [str(b0), str(b_guid)],
                    'restore_database': str(restored_seq),
                    'restore_flags': ['SEQUENCE'],
                }, absent_origin, forbid_sql=True)
                rb_seq = _readback_db(client, route, restored_seq)
                assert rb_seq['rows'] == base_payloads + [p21, p22]
                assert rb_seq['unicode_rows'] == [23, 24, 25]
                assert rb_seq['guid'] == source_db_guid
                proof['checks'].append({
                    'case': 'restore-sequence-guid-delta',
                    'guid_preserved': True,
                    'guid_incremental_rows_verified': True,
                })

                # 10. IN_PLACE incremental restore + read-only result + repeat increment native denial (337117247).
                inplace_db = data / 'inplace_standby.fdb'
                run_op('restore_physical', {
                    'backup_files': [str(b0)],
                    'restore_database': str(inplace_db),
                    'restore_flags': ['SEQUENCE'],
                }, absent_origin, forbid_sql=True)
                # Open an idle catalog observation first to prove apply releases idle catalog handles cleanly.
                _ = client.list_resources({'route': {**route, 'database': str(inplace_db)}})
                run_op('restore_physical', {
                    'backup_files': [str(b1)],
                    'restore_database': str(inplace_db),
                    'restore_flags': ['IN_PLACE', 'SEQUENCE'],
                    'confirmation': str(inplace_db),
                }, absent_origin)
                rb_inplace = _readback_db(client, route, inplace_db)
                assert rb_inplace['rows'] == base_payloads + [p21]
                assert rb_inplace['unicode_rows'] == [23, 24]
                assert rb_inplace['read_only'] == 1
                assert rb_inplace['guid'] == source_db_guid

                dup_req = review('restore_physical', {
                    'backup_files': [str(b1)],
                    'restore_database': str(inplace_db),
                    'restore_flags': ['IN_PLACE'],
                    'confirmation': str(inplace_db),
                }, absent_origin)
                try:
                    visual.apply({
                        'plan_id': dup_req['plan_id'],
                        'plan_digest': dup_req['plan_digest'],
                        'confirmed': True,
                    })
                except VisualAdminExecutionError as error:
                    assert error.operation['unknown_outcome'] is True
                    assert 337117247 in proof.get('last_owned_native_error', {}).get('status_codes', [])
                else:
                    raise AssertionError('Repeated IN_PLACE increment admitted natively')
                replay_refused(dup_req)
                proof['checks'].append({
                    'case': 'restore-in-place-and-duplicate-denial',
                    'read_only_after_in_place': True,
                    'duplicate_increment_337117247_refused': True,
                })

                # 11. Pinned backup input replaced during dispatch restores pinned bytes without touching replacement.
                copied_b0 = data / 'raced_b0.nbk'
                copied_b0.write_bytes(b0.read_bytes())
                raced_target = data / 'raced_restored.fdb'

                def swap_input(*args, **kwargs):
                    copied_b0.rename(data / 'retained_b0.nbk')
                    copied_b0.write_bytes(b'foreign replacement nbk')
                    return dispatch_orig(*args, **kwargs)

                client.run_server_operation = swap_input
                try:
                    raced_res = run_op('restore_physical', {
                        'backup_files': [str(copied_b0), str(b1)],
                        'restore_database': str(raced_target),
                    }, absent_origin)['driver_observation']
                finally:
                    client.run_server_operation = dispatch_orig
                assert not raced_res['local_restore_files']['backup_inputs'][0]['requested_path_still_names_input']
                assert copied_b0.read_bytes() == b'foreign replacement nbk'
                assert _readback_db(client, route, raced_target)['rows'] == base_payloads + [p21]
                proof['checks'].append({
                    'case': 'restore-input-replaced-during-dispatch',
                    'pinned_backup_restored': True,
                    'replacement_untouched': True,
                })

                # 12. Corrupt backup input yields unknown outcome + durable destination lookup + no replay.
                corrupt_nbk = data / 'corrupt.nbk'
                corrupt_nbk.write_bytes(b'owned corrupt physical backup bytes')
                corrupt_target = data / 'corrupt_target.fdb'
                corrupt_req = review('restore_physical', {
                    'backup_files': [str(corrupt_nbk)],
                    'restore_database': str(corrupt_target),
                }, absent_origin)
                try:
                    visual.apply({
                        'plan_id': corrupt_req['plan_id'],
                        'plan_digest': corrupt_req['plan_digest'],
                        'confirmed': True,
                    })
                except VisualAdminExecutionError as error:
                    assert error.operation['unknown_outcome'] is True
                    assert error.operation['impact']['restore_files']['outputs'][0]['filename'] == str(corrupt_target)
                else:
                    raise AssertionError('Corrupt physical backup reported success')
                replay_refused(corrupt_req)
                proof['checks'].append({
                    'case': 'restore-corrupt-input',
                    'unknown_no_replay': True,
                    'impact_retains_destination': True,
                })

                # 13. Caller's pending uncommitted row on primary survived the entire suite!
                assert pending.main_transaction.is_active()
                cur = pending.cursor()
                cur.execute('SELECT ID FROM "雪DATA" ORDER BY ID')
                assert cur.fetchall() == [(23,), (999,)]
                cur.close()
                pending.rollback()
                proof['checks'].append({
                    'case': 'caller-transaction-preserved',
                    'pending_row_preserved_until_rollback': True,
                })
            finally:
                client._forget_and_close(pending)
                client.close()

        proof['owned_state_removed'] = area is not None and not area.exists()
        proof['source_runtime_unchanged'] = _runtime_fingerprint(runtime) == before
        proof['complete'] = (
            len(proof['checks']) == 13 and
            proof['owned_state_removed'] and
            proof['source_runtime_unchanged']
        )
    finally:
        for k, v in previous_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        (output / 'native.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


def qualify_http(runtime, output):
    import builtins
    builtins.SERVER_MODE = None
    import pgadmin  # noqa: F401
    from tools.cdeadmin_firebird_object_live_orchestrator import (
        _stage_runtime, _runtime_fingerprint,
    )
    from tools.cdeadmin_mysql_dump_verification_qualification import setup_application
    runtime, output = Path(runtime).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    before = _runtime_fingerprint(runtime)
    proof = {
        'complete': False,
        'scope': (
            'Owned Engine13 Firebird 5.0.4 authenticated local physical backup '
            'and physical restore (NEW_DATABASE + IN_PLACE), readback, stale '
            'refusal and unknown-outcome lookup. No browser/platform acceptance.'
        ),
        'checks': [],
        'source_sha256': _source_hashes(),
    }
    env_keys = ('FIREBIRD', 'FIREBIRD_LOCK', 'CDEADMIN_FIREBIRD_CLIENT_LIBRARY')
    previous_env = {k: os.environ.get(k) for k in env_keys}
    root = None
    try:
        with tempfile.TemporaryDirectory(prefix='firebird-phys-http-', dir=output) as folder, ExitStack() as owners:
            root = Path(folder)
            stage = root / 'runtime'
            _stage_runtime(runtime, stage)
            (stage / 'firebird.conf').write_text(
                'Providers = Engine13\nSecurityDatabase = ' + str(stage / 'security5.fdb') + '\n'
            )
            (stage / 'databases.conf').write_text('')
            os.environ.update(
                FIREBIRD=str(stage),
                FIREBIRD_LOCK=str(stage / 'lock'),
                CDEADMIN_FIREBIRD_CLIENT_LIBRARY=str(stage / 'lib/libfbclient.so.5.0.4'),
            )
            import firebird.driver as module
            module.driver_config.fb_client_library.value = str(stage / 'lib/libfbclient.so.5.0.4')
            app = setup_application(root)

            def close_app():
                from pgadmin.cdeadmin.workspace.service import service_for_app
                with app.app_context():
                    svc = service_for_app(app)
                    svc.endpoint_service.provider_registry.close()

            owners.callback(close_app)
            from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
            from pgadmin.cdeadmin.providers.firebird.provider import _create_client
            from pgadmin.cdeadmin.endpoints.profiles import registration_profile
            from pgadmin.model import db, User, ServerGroup, Server, EndpointDatabaseTarget
            from flask import url_for

            data = root / 'data'
            data.mkdir()
            source_path = data / 'http_source 雪.fdb'
            route = {
                'attachment_mode': 'embedded',
                'database': str(source_path),
                'filesystem_root': str(data),
                'user': 'SYSDBA',
                'charset': 'UTF8',
            }
            helper_client = _create_client(
                SimpleNamespace(
                    require=lambda *_: None,
                    acquire_secret=lambda *_: (_ for _ in ()).throw(AssertionError('Network secret')),
                ),
                attachment_mode='embedded',
                profile=embedded.PROFILE,
                administration=embedded.ADMINISTRATION,
            )
            owners.callback(helper_client.close)
            c = helper_client.config.database_creator(
                **helper_client.config.database_create_arguments(route, str(source_path), {})
            )
            try:
                c.execute_immediate(
                    'CREATE TABLE OWNED(ID INTEGER NOT NULL PRIMARY KEY, PAYLOAD BLOB SUB_TYPE BINARY)'
                )
                c.execute_immediate('CREATE TABLE "雪DATA"(ID INTEGER)')
                c.commit()
                q = c.cursor()
                q.execute('INSERT INTO OWNED VALUES(17, ?)', (b'http-blob-17',))
                q.execute('INSERT INTO "雪DATA" VALUES(23)')
                q.close()
                c.commit()
            finally:
                c.close()

            with app.test_request_context('/'):
                user = User.query.first()
                uid = user.id
                group = ServerGroup.query.filter_by(user_id=uid).first()
                for name, pref in app.blueprints['NODE-engine_type'].connector_visibility.items():
                    if 'firebird' in name:
                        pref.set(True, user_id=uid)
                server = Server(
                    user_id=uid, servergroup_id=group.id,
                    name='Owned local physical backup/restore',
                    host=None, port=1, username='SYSDBA',
                    maintenance_db=str(source_path), save_password=0,
                )
                server._cde_endpoint_registration = registration_profile('firebird-embedded')
                server._cde_endpoint_route_configuration = route
                db.session.add(server)
                db.session.commit()
                tid = str(uuid.uuid4())
                db.session.add(EndpointDatabaseTarget(
                    id=tid, endpoint_id=server.endpoint_profile.id,
                    display_name=source_path.name, database=str(source_path),
                    configuration='{}', active=1,
                ))
                db.session.commit()
                url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=server.id)
                verify_url = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=server.id)

            http = app.test_client()
            with http.session_transaction() as sess:
                sess['_user_id'] = str(uid)
                sess['_fresh'] = True
            verified = http.post(verify_url, json={}).get_json()
            assert verified['success'], verified

            def focused_target(op_id):
                resp = http.get(url, query_string={
                    'database_target_id': tid,
                    'focused_operation_id': op_id,
                })
                body = resp.get_json()
                assert resp.status_code == 200 and body['success'], body
                assert resp.headers['Cache-Control'] == 'no-store'
                assert body['data']['engine_contracts']['state'] == 'passed', body['data']['engine_contracts']
                items = body['data']['resource_page']['items']
                assert len(items) == 1 and items[0]['extensions']['cdeadmin']['focused_operation_id'] == op_id
                return items[0]

            def post_action(action, req_payload, expect_success=True):
                resp = http.post(url, json={
                    'action': action,
                    'database_target_id': tid,
                    'request': {'database_target_id': tid, **req_payload},
                })
                body = resp.get_json()
                assert resp.headers.get('Cache-Control') == 'no-store'
                if expect_success:
                    assert resp.status_code == 200 and body.get('success'), (action, resp.status_code, body)
                    return body['data']
                assert not body.get('success'), (action, body)
                return body

            # 1. Authenticated HTTP backup_physical Level 0 + Level 1 + restore_physical NEW_DATABASE & IN_PLACE.
            bkp_target = focused_target('backup_physical')
            b0 = data / 'http_b0.nbk'
            val0 = post_action('visual_admin_validate', {
                'resource_kind': 'database',
                'operation_id': 'backup_physical',
                'target_resource': bkp_target,
                'draft': {'backup_file': str(b0), 'backup_level': 0, 'direct_io_mode': 'OFF'},
            })
            assert val0['valid'], val0
            plan0 = post_action('visual_admin_plan', {
                'resource_kind': 'database',
                'operation_id': 'backup_physical',
                'target_resource': bkp_target,
                'draft': {'backup_file': str(b0), 'backup_level': 0, 'direct_io_mode': 'OFF'},
            })
            apply0 = post_action('visual_admin_apply', {
                'plan_id': plan0['plan_id'],
                'plan_digest': plan0['plan_digest'],
                'confirmed': True,
            })
            assert apply0['provider_result']['driver_observation']['outputs_at_reviewed_paths'] is True
            # One-use replay must be denied.
            post_action('visual_admin_apply', {
                'plan_id': plan0['plan_id'],
                'plan_digest': plan0['plan_digest'],
                'confirmed': True,
            }, expect_success=False)

            w = helper_client._connect({'route': route})
            try:
                cur = w.cursor()
                cur.execute('INSERT INTO OWNED VALUES(18, ?)', (b'http-blob-18',))
                cur.close()
                w.commit()
            finally:
                helper_client._forget_and_close(w)

            b1 = data / 'http_b1.nbk'
            plan1 = post_action('visual_admin_plan', {
                'resource_kind': 'database',
                'operation_id': 'backup_physical',
                'target_resource': bkp_target,
                'draft': {'backup_file': str(b1), 'backup_level': 1},
            })
            post_action('visual_admin_apply', {
                'plan_id': plan1['plan_id'],
                'plan_digest': plan1['plan_digest'],
                'confirmed': True,
            })

            rst_target = focused_target('restore_physical')
            standby = data / 'http_standby.fdb'
            plan_r0 = post_action('visual_admin_plan', {
                'resource_kind': 'database',
                'operation_id': 'restore_physical',
                'target_resource': rst_target,
                'draft': {
                    'backup_files': [str(b0)],
                    'restore_database': str(standby),
                    'restore_flags': ['SEQUENCE'],
                },
            })
            post_action('visual_admin_apply', {
                'plan_id': plan_r0['plan_id'],
                'plan_digest': plan_r0['plan_digest'],
                'confirmed': True,
            })
            post_action('visual_admin_apply', {
                'plan_id': plan_r0['plan_id'],
                'plan_digest': plan_r0['plan_digest'],
                'confirmed': True,
            }, expect_success=False)

            plan_inp = post_action('visual_admin_plan', {
                'resource_kind': 'database',
                'operation_id': 'restore_physical',
                'target_resource': rst_target,
                'draft': {
                    'backup_files': [str(b1)],
                    'restore_database': str(standby),
                    'restore_flags': ['IN_PLACE'],
                    'confirmation': str(standby),
                },
            })
            apply_inp = post_action('visual_admin_apply', {
                'plan_id': plan_inp['plan_id'],
                'plan_digest': plan_inp['plan_digest'],
                'confirmed': True,
            })
            assert apply_inp['provider_result']['restored_database_target']['database'] == str(standby)
            rb = _readback_db(helper_client, route, standby)
            assert rb['rows'] == [(17, b'http-blob-17'), (18, b'http-blob-18')]
            assert rb['read_only'] == 1
            proof['checks'].append(
                'Authenticated HTTP backup_physical (L0+L1) and restore_physical '
                '(NEW_DATABASE+SEQUENCE and IN_PLACE), row17+row18 BLOB readback, '
                'read-only property, one-use and no-store'
            )

            # 2. Destination created after review refused before native dispatch without overwriting foreign bytes.
            stale_dest = data / 'http_stale_dest.fdb'
            plan_stale = post_action('visual_admin_plan', {
                'resource_kind': 'database',
                'operation_id': 'restore_physical',
                'target_resource': rst_target,
                'draft': {
                    'backup_files': [str(b0)],
                    'restore_database': str(stale_dest),
                },
            })
            stale_dest.write_bytes(b'foreign http destination')
            post_action('visual_admin_apply', {
                'plan_id': plan_stale['plan_id'],
                'plan_digest': plan_stale['plan_digest'],
                'confirmed': True,
            }, expect_success=False)
            assert stale_dest.read_bytes() == b'foreign http destination'
            proof['checks'].append(
                'Destination created after review is refused before native physical restore without overwriting foreign bytes'
            )

            # 3. Corrupt physical backup keeps unknown/no-replay and destination identity in authenticated operation lookup.
            corrupt = data / 'http_corrupt.nbk'
            corrupt.write_bytes(b'corrupt nbk bytes')
            bad_dest = data / 'http_bad_dest.fdb'
            plan_bad = post_action('visual_admin_plan', {
                'resource_kind': 'database',
                'operation_id': 'restore_physical',
                'target_resource': rst_target,
                'draft': {
                    'backup_files': [str(corrupt)],
                    'restore_database': str(bad_dest),
                },
            })
            post_action('visual_admin_apply', {
                'plan_id': plan_bad['plan_id'],
                'plan_digest': plan_bad['plan_digest'],
                'confirmed': True,
            }, expect_success=False)
            ops = post_action('visual_admin_operation_list', {})['items']
            latest = next(item for item in ops if item['plan_id'] == plan_bad['plan_id'])
            assert latest['unknown_outcome'] is True
            assert latest['impact']['restore_files']['outputs'][0]['filename'] == str(bad_dest)
            proof['checks'].append(
                'Native physical restore error keeps unknown/no-replay and destination identity in authenticated operation lookup'
            )

        proof['owned_state_removed'] = root is not None and not root.exists()
        proof['source_runtime_unchanged'] = _runtime_fingerprint(runtime) == before
        proof['complete'] = (
            len(proof['checks']) == 3 and
            proof['owned_state_removed'] and
            proof['source_runtime_unchanged']
        )
    finally:
        for k, v in previous_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        (output / 'http.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


def qualify(runtime, output, mode='both'):
    import subprocess
    output = Path(output).resolve()
    if mode == 'native':
        native_res = qualify_native(runtime, output)
        return {'complete': bool(native_res['complete']), 'native_checks': len(native_res['checks'])}
    if mode == 'http':
        http_res = qualify_http(runtime, output)
        return {'complete': bool(http_res['complete']), 'http_checks': len(http_res['checks'])}
    native_res = qualify_native(runtime, output)
    subprocess.run(
        [sys.executable, str(Path(__file__).resolve()),
         '--runtime', str(Path(runtime).resolve()),
         '--output', str(output), '--mode', 'http'],
        check=True,
    )
    http_res = json.loads((output / 'http.json').read_text())
    # Refresh source_sha256 in native.json so both receipts match exact runner bytes.
    native_res['source_sha256'] = _source_hashes()
    (output / 'native.json').write_text(json.dumps(native_res, indent=2) + '\n')
    return {
        'complete': bool(native_res['complete'] and http_res['complete']),
        'native_checks': len(native_res['checks']),
        'http_checks': len(http_res['checks']),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('both', 'native', 'http'), default='both')
    args = parser.parse_args()
    summary = qualify(args.runtime, args.output, mode=args.mode)
    print(json.dumps(summary))
    raise SystemExit(0 if summary['complete'] else 1)

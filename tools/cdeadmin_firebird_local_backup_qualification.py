"""Qualify owned Engine13 logical backups with owned native restore controls."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def qualify(runtime, output):
    from tools.cdeadmin_firebird_object_live_orchestrator import _stage_runtime, _runtime_fingerprint
    runtime, output = Path(runtime).resolve(), Path(output).resolve()
    if sys.platform != 'linux' or output == ROOT or ROOT in output.parents:
        raise ValueError('Use Linux and evidence outside source')
    output.mkdir(parents=True, exist_ok=True)
    proof = {'complete': False, 'checks': [], 'history_tests': 'not run',
             'scope': 'Owned Linux Firebird5.0.4 Engine13 logical backup and qualification-only restore controls; no network/platform/UI acceptance'}
    paths = ['web/pgadmin/cdeadmin/providers/firebird/' + name for name in (
        'local_services.py', 'embedded_provider.py', 'query_client.py', 'provider.py', 'local_backup.py')]
    paths += ['web/pgadmin/cdeadmin/providers/relational_admin.py',
              'web/pgadmin/cdeadmin/visual_admin/provider.py',
              'web/pgadmin/cdeadmin/providers/firebird/embedded_provider_manifest.json',
              'web/pgadmin/cdeadmin/ui_descriptors/firebird/capabilities.json',
              'web/pgadmin/cdeadmin/ui_descriptors/firebird/operations.json',
              'tools/cdeadmin_firebird_local_backup_qualification.py']
    proof['source_sha256'] = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}
    before = _runtime_fingerprint(runtime)
    try:
        with tempfile.TemporaryDirectory(prefix='firebird-local-backup-', dir=output) as folder:
            area = Path(folder); stage = area/'runtime'; _stage_runtime(runtime, stage)
            (stage/'firebird.conf').write_text('Providers = Engine13\nSecurityDatabase = ' + str(stage/'security5.fdb') + '\n')
            (stage/'databases.conf').write_text('')
            os.environ.update(FIREBIRD=str(stage), FIREBIRD_LOCK=str(stage/'lock'),
                CDEADMIN_FIREBIRD_CLIENT_LIBRARY=str(stage/'lib/libfbclient.so.5.0.4'))
            import firebird.driver as module
            module.driver_config.fb_client_library.value = str(stage/'lib/libfbclient.so.5.0.4')
            from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
            from pgadmin.cdeadmin.providers.firebird.provider import _create_client, _firebird_service_operation
            from pgadmin.cdeadmin.visual_admin import ProviderVisualAdministration, VisualAdminAccessError, VisualAdminExecutionError
            permitted = {'embedded_runtime', 'filesystem', 'data_read', 'administer', 'execute', 'maintenance_admin', 'backup_admin'}
            def require(name, *_):
                if name not in permitted: raise PermissionError(name)
            def secret(*_): raise AssertionError('Recovery acquired a network credential')
            permissions = SimpleNamespace(require=require, allows=lambda name, *_: name in permitted, acquire_secret=secret)
            client = _create_client(permissions, attachment_mode='embedded', profile=embedded.PROFILE, administration=embedded.ADMINISTRATION)
            context = SimpleNamespace(endpoint_id='owned-backup', mode='provider_native', provider_id=embedded.PROFILE.provider_id,
                profile_id=embedded.PROFILE.profile_id, runtime_verification_state='verified', declared_runtime_family='firebird', verified_runtime_family='firebird')
            visual = ProviderVisualAdministration(context, permissions, 'firebird', '5.0.4', client)
            data = area/'data'; data.mkdir()
            route = {'attachment_mode': 'embedded', 'database': str(data/"source 雪's.fdb"),
                     'filesystem_root': str(data), 'user': 'SYSDBA', 'charset': 'UTF8'}
            c = client.config.database_creator(**client.config.database_create_arguments(route, route['database'], {}))
            payloads = [(i, hashlib.shake_256(str(i).encode()).digest(2500)) for i in range(1,21)]
            try:
                c.execute_immediate('CREATE TABLE OWNED(ID INTEGER NOT NULL PRIMARY KEY, PAYLOAD BLOB SUB_TYPE BINARY)')
                c.execute_immediate('CREATE TABLE "雪DATA"(ID INTEGER)'); c.commit()
                q = c.cursor()
                try:
                    for identifier, payload in payloads: q.execute('INSERT INTO OWNED VALUES(?,?)', (identifier,payload))
                    q.execute('INSERT INTO "雪DATA" VALUES(23)'); c.commit()
                finally: q.close()
            finally: c.close()
            def review(options):
                request = {'resource_kind': 'database', 'operation_id': 'backup_logical',
                    '_provider_route': route, 'draft': options,
                    'target_resource': {'resource_kind': 'database', 'resource_id': 'owned-database',
                                        'display_name': Path(route['database']).name}}
                validation = visual.validate(request); assert validation['valid'], validation
                plan = visual.plan(request)
                assert plan['command_preview']['local_backup_outputs']
                return {'plan_id': plan['plan_id'], 'plan_digest': plan['plan_digest'], 'confirmed': True}
            def replay_refused(request):
                try: visual.apply(request)
                except VisualAdminAccessError: return
                raise AssertionError('Consumed backup review replayed')
            def apply(options):
                request = review(options)
                try: result = visual.apply(request)['provider_result']['driver_observation']
                finally: replay_refused(request)
                assert result['server_completed'] and result['native_provider'] == 'Engine13'
                assert not result['network_authentication'] and not result['file_identity_race_fenced']
                assert result['service_release']['connection_released'] and result['service_release']['service_handle_released']
                return result
            def restore(files, name, rows=True, unicode_rows=True):
                # Qualification-only native control: this does not expose the
                # as-yet unimplemented embedded restore product workflow.
                target = data/(name+' restored.fdb')
                server = client._connect_server({'route': route})
                try:
                    result = _firebird_service_operation(server, 'restore_logical', str(target), {
                        'backup_file': str(files[0]), 'additional_backup_files': [str(p) for p in files[1:]],
                        'restore_database': str(target), 'verbose': False}, module)
                    assert result['server_completed']
                finally: client._release_server(server)
                connection = client._connect({'route': {**route,'database':str(target)}})
                try:
                    cursor = connection.cursor()
                    try:
                        cursor.execute('SELECT ID,PAYLOAD FROM OWNED ORDER BY ID')
                        observed = []
                        for identifier, value in cursor.fetchall():
                            if hasattr(value,'read'):
                                blob = value.read(); value.close()
                            else: blob = value
                            observed.append((identifier,blob))
                        assert observed == (payloads if rows else []), len(observed)
                        cursor.execute('SELECT ID FROM "雪DATA"')
                        assert cursor.fetchall() == ([(23,)] if unicode_rows else [])
                    finally: cursor.close(); connection.rollback()
                finally: client._forget_and_close(connection)
            pending = client._connect({'route':route})
            pending.execute_immediate('INSERT INTO "雪DATA" VALUES(999)')
            try:
                # A new managed connection must remain possible while the
                # backup's canonical-filename and output reservations are held.
                from concurrent.futures import ThreadPoolExecutor
                dispatch = client.run_server_operation
                def online(*args, **kwargs):
                    def read():
                        connection = client._connect({'route':route})
                        try:
                            cursor = connection.cursor(); cursor.execute('SELECT COUNT(*) FROM OWNED')
                            count = cursor.fetchone()[0]; cursor.close(); connection.rollback()
                            return count
                        finally: client._forget_and_close(connection)
                    pool = ThreadPoolExecutor(max_workers=1)
                    try:
                        future = pool.submit(read)
                        assert future.result(timeout=10) == 20
                    finally: pool.shutdown(wait=False, cancel_futures=True)
                    return dispatch(*args, **kwargs)
                client.run_server_operation = online
                try: apply({'backup_file':str(data/'online connection.fbk')})
                finally: client.run_server_operation = dispatch
                proof['checks'].append({'case':'online-new-connection', 'new_managed_sql_admitted_during_backup_scope':True})
                denied_output = data/'denied.fbk'
                permitted.remove('backup_admin')
                try:
                    try: review({'backup_file':str(denied_output)})
                    except PermissionError: pass
                    else: raise AssertionError('Backup without its native-operation permission admitted')
                finally: permitted.add('backup_admin')
                assert not denied_output.exists()
                proof['checks'].append({'case':'backup-permission', 'refused_before_any_output_creation':True})
                cases = [
                    ('full', {'backup_flags':['NO_GARBAGE_COLLECT','NO_TRIGGERS'], 'parallel_workers':2}, True, True),
                    ('metadata', {'backup_flags':['METADATA_ONLY']}, False, False),
                    ('compressed', {'backup_flags':['ZIP']}, True, True),
                    ('unicode-skip', {'skip_data':'雪DATA'}, True, False),
                ]
                for name, extra, rows, unicode_rows in cases:
                    backup_path = data/(name+" 雪's.fbk")
                    result = apply({'backup_file':str(backup_path), 'verbose':True, 'statistics':'TDWR', **extra})
                    assert result['local_backup_outputs'][0]['requested_path_still_names_output']
                    assert result['local_backup_outputs'][0]['bytes_observed'] > 0
                    restore([backup_path], name, rows, unicode_rows)
                    proof['checks'].append({'case':name, 'native_backup_and_independent_restore':True,
                        'blob_and_schema_readback':True, 'selection_applied_natively':True})
                files = [data/'split first 雪.fbk', data/'split last 雪.fbk']
                result = apply({'split_backup':True,'backup_volumes':[
                    {'filename':str(files[0]),'size_bytes':8192},{'filename':str(files[1])}], 'verbose':False})
                assert all(row['bytes_observed'] > 0 for row in result['local_backup_outputs'])
                restore(files,'split')
                proof['checks'].append({'case':'ordered-split', 'capacities_and_order_native_restore_verified':True})
                backup_path = data/'stale output.fbk'; options = {'backup_file':str(backup_path)}
                request = review(options); backup_path.write_bytes(b'foreign file')
                try: visual.apply(request)
                except VisualAdminExecutionError as error: assert error.operation['unknown_outcome'] is False
                else: raise AssertionError('Existing backup_path overwritten')
                replay_refused(request); assert backup_path.read_bytes() == b'foreign file'
                proof['checks'].append({'case':'output-created-after-review', 'known_pre_dispatch_refusal':True})
                backup_path = data/'replaced output.fbk'; retained = data/'retained native backup.fbk'
                dispatch = client.run_server_operation
                def replace(*args, **kwargs):
                    backup_path.rename(retained); backup_path.write_bytes(b'foreign replacement')
                    return dispatch(*args, **kwargs)
                client.run_server_operation = replace
                try: result = apply({'backup_file':str(backup_path)})
                finally: client.run_server_operation = dispatch
                assert not result['local_backup_outputs'][0]['requested_path_still_names_output']
                assert backup_path.read_bytes() == b'foreign replacement'
                restore([retained],'retained-native-output')
                proof['checks'].append({'case':'output-replaced-during-native-dispatch',
                    'replacement_untouched':True,'pinned_backup_restored':True,'path_mismatch_reported':True})
                backup_path = data/'missing plugin partial.fbk'; options = {'backup_file':str(backup_path), 'key_holder':'OwnedAbsentKeyHolder'}
                request = review(options)
                try: visual.apply(request)
                except VisualAdminExecutionError as error:
                    assert error.operation['unknown_outcome']
                    assert error.operation['impact']['backup_output_files'][0]['filename'] == str(backup_path)
                else: raise AssertionError('Missing native key-holder plugin accepted')
                replay_refused(request); assert backup_path.exists()
                proof['checks'].append({'case':'native-plugin-failure', 'partial_output_retained':True,'unknown_no_replay':True})
                backup_path = data/'lost response.fbk'; request = review({'backup_file':str(backup_path)})
                dispatch = client.run_server_operation
                completed = []
                def lose(*args, **kwargs):
                    completed.append(dispatch(*args, **kwargs))
                    from pgadmin.cdeadmin.sdk import RelationalClientError
                    raise RelationalClientError('Owned qualification lost the completed native backup response')
                client.run_server_operation = lose
                try:
                    try: visual.apply(request)
                    except VisualAdminExecutionError as error: assert error.operation['unknown_outcome']
                    else: raise AssertionError('Lost native response reported known success')
                finally: client.run_server_operation = dispatch
                replay_refused(request)
                assert len(completed) == 1 and completed[0]['server_completed']
                restore([backup_path],'lost-response')
                proof['checks'].append({'case':'lost-response', 'unknown_no_replay':True,
                                        'native_backup_independently_restored':True})
                assert pending.main_transaction.is_active()
                q = pending.cursor(); q.execute('SELECT ID FROM "雪DATA" ORDER BY ID')
                assert q.fetchall() == [(23,),(999,)]; q.close()
                pending.rollback()
                proof['checks'].append({'case':'caller-transaction', 'pending_row_preserved_until_explicit_rollback':True})
            finally:
                client._forget_and_close(pending); client.close()
        proof['owned_state_removed'] = not area.exists()
        proof['source_runtime_unchanged'] = _runtime_fingerprint(runtime) == before
        proof['complete'] = len(proof['checks']) == 12 and proof['owned_state_removed'] and proof['source_runtime_unchanged']
    finally: (output/'native.json').write_text(json.dumps(proof, indent=2)+'\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); result = qualify(args.runtime, args.output)
    print(json.dumps({'complete': result['complete'], 'checks': len(result['checks'])}))
    raise SystemExit(0 if result['complete'] else 1)

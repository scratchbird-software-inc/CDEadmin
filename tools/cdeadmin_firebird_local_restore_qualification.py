"""Qualify owned Engine13 logical restore of reviewed local backup files."""
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
             'scope': 'Owned Linux Firebird5.0.4 Engine13 logical restore; no network/platform/UI acceptance'}
    paths = ['web/pgadmin/cdeadmin/providers/firebird/' + name for name in (
        'local_services.py', 'embedded_provider.py', 'query_client.py', 'provider.py', 'local_backup.py','local_restore.py')]
    paths += ['web/pgadmin/cdeadmin/providers/relational_admin.py',
              'web/pgadmin/cdeadmin/visual_admin/provider.py',
              'web/pgadmin/cdeadmin/providers/firebird/embedded_provider_manifest.json',
              'web/pgadmin/cdeadmin/ui_descriptors/firebird/capabilities.json',
              'web/pgadmin/cdeadmin/ui_descriptors/firebird/operations.json',
              'tools/cdeadmin_firebird_local_restore_qualification.py']
    proof['source_sha256'] = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}
    before = _runtime_fingerprint(runtime)
    try:
        with tempfile.TemporaryDirectory(prefix='firebird-local-restore-', dir=output) as folder:
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
            permitted = {'embedded_runtime', 'filesystem', 'data_read', 'administer', 'execute', 'maintenance_admin', 'backup_admin','restore_admin'}
            def require(name, *_):
                if name not in permitted: raise PermissionError(name)
            def secret(*_): raise AssertionError('Recovery acquired a network credential')
            permissions = SimpleNamespace(require=require, allows=lambda name, *_: name in permitted, acquire_secret=secret)
            client = _create_client(permissions, attachment_mode='embedded', profile=embedded.PROFILE, administration=embedded.ADMINISTRATION)
            # Diagnostic evidence is restricted to this owned, credential-free
            # fixture; production exceptions remain normalized by the client.
            from dataclasses import replace
            native_runner = client.config.server_operation_runner
            def observed_runner(server, operation, database, options):
                try:return native_runner(server, operation, database, options)
                except Exception as error:
                    proof['last_owned_native_error'] = {'operation':operation,
                        'message':str(error)[:8192],'status_codes':list(getattr(error,'gds_codes',()))[:32]}
                    raise
            client.config = replace(client.config, server_operation_runner=observed_runner)
            context = SimpleNamespace(endpoint_id='owned-restore', mode='provider_native', provider_id=embedded.PROFILE.provider_id,
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
            def review(operation, options, origin=None):
                request = {'resource_kind':'database','operation_id':operation,
                    '_provider_route':origin or route,'draft':options}
                if operation == 'backup_logical':
                    request['target_resource'] = {'resource_kind':'database','resource_id':'owned-source','display_name':Path(route['database']).name}
                validation = visual.validate(request); assert validation['valid'],validation
                plan = visual.plan(request)
                return {'plan_id':plan['plan_id'],'plan_digest':plan['plan_digest'],'confirmed':True}
            def replay_refused(request):
                try: visual.apply(request)
                except VisualAdminAccessError: return
                raise AssertionError('Consumed native restore review replayed')
            def apply(options, origin=None, operation='restore_logical'):
                connect = client._connect
                if operation == 'restore_logical':
                    def forbidden(*_args,**_kwargs): raise AssertionError('Restore attempted SQL before native execution')
                    client._connect = forbidden
                try:
                    request = review(operation,options,origin)
                    try: result = visual.apply(request)['provider_result']['driver_observation']
                    finally: replay_refused(request)
                finally: client._connect = connect
                assert result['server_completed'] and result['native_provider']=='Engine13'
                assert not result['network_authentication'] and not result['file_identity_race_fenced']
                assert result['service_release']['connection_released'] and result['service_release']['service_handle_released']
                return result
            def readback(path, rows=True, unicode_rows=True, properties=None):
                connection = client._connect({'route':{**route,'database':str(path)}})
                try:
                    cursor = connection.cursor()
                    try:
                        cursor.execute('SELECT ID,PAYLOAD FROM OWNED ORDER BY ID'); observed=[]
                        for identifier,value in cursor.fetchall():
                            if hasattr(value,'read'):
                                blob=value.read(); value.close()
                            else: blob=value
                            observed.append((identifier,blob))
                        assert observed==(payloads if rows else []),len(observed)
                        cursor.execute('SELECT ID FROM "雪DATA"');assert cursor.fetchall()==([(23,)] if unicode_rows else [])
                        cursor.execute('SELECT MON$DATABASE_NAME,MON$PAGE_SIZE,MON$PAGE_BUFFERS,MON$READ_ONLY,MON$REPLICA_MODE FROM MON$DATABASE')
                        values=cursor.fetchone();assert values[0]==str(path),values
                        if properties:
                            for index,value in properties.items(): assert values[index]==value,values
                    finally:cursor.close();connection.rollback()
                finally:client._forget_and_close(connection)
            pending = client._connect({'route':route})
            pending.execute_immediate('INSERT INTO "雪DATA" VALUES(999)')
            try:
                backup = data/"complete 雪's.fbk"
                apply({'backup_file':str(backup),'verbose':False},operation='backup_logical')
                split = [data/'first volume.fbk',data/'last volume.fbk']
                apply({'split_backup':True,'backup_volumes':[
                    {'filename':str(split[0]),'size_bytes':8192},{'filename':str(split[1])}], 'verbose':False},operation='backup_logical')
                origin = {**route,'database':str(data/'absent-parent'/'unavailable-original.fdb')}
                denied = data/'denied restore.fdb';permitted.remove('restore_admin')
                try:
                    try: review('restore_logical',{'backup_file':str(backup),'restore_database':str(denied)},origin)
                    except PermissionError:pass
                    else:raise AssertionError('Restore without its operation permission admitted')
                finally:permitted.add('restore_admin')
                assert not denied.exists();proof['checks'].append({'case':'restore-permission','no_destination_created':True})
                for name,extra,rows,unicode_rows,properties in (
                    ('full',{'page_size':'16384','page_buffers':321,'parallel_workers':2},True,True,{1:16384,2:321}),
                    ('metadata',{'restore_flags':['METADATA_ONLY']},False,False,None),
                    ('filtered',{'skip_data':'雪DATA'},True,False,None),
                    ('read-only',{'access_mode':'READ_ONLY','replica_mode':'READ_ONLY'},True,True,{3:1,4:1}),
                ):
                    target = data/(name+" restored 雪's.fdb")
                    result=apply({'backup_file':str(backup),'restore_database':str(target),'verbose':True,'statistics':'TDWR',**extra},origin)
                    assert result['local_restore_files']['inputs_unchanged']
                    assert result['local_restore_files']['data_readback_verified'] is False
                    readback(target,rows,unicode_rows,properties)
                    proof['checks'].append({'case':name,'no_pre_restore_sql':True,'blob_and_row_readback':True,'native_properties_read_back':True})
                target = data/'split restored.fdb'
                apply({'backup_file':str(split[0]),'additional_backup_files':[str(split[1])],'restore_database':str(target)},origin)
                readback(target);proof['checks'].append({'case':'split-input-order','all_native_rows_and_blobs_verified':True})
                target = data/'multiple files restored.fdb';secondary = data/'secondary native.fdb'
                result=apply({'backup_file':str(backup),'restore_database':str(target),
                    'multiple_database_files':True,'primary_file_pages':512,
                    'database_file_volumes':[{'filename':str(secondary)}]},origin)
                readback(target)
                assert len(result['local_restore_files']['database_files'])==2
                assert target.exists() and secondary.exists()
                proof['checks'].append({'case':'multiple-database-files','canonical_native_files_exist':True,'all_rows_and_blobs_verified':True})
                target = data/'replace owned.fdb'
                apply({'backup_file':str(backup),'restore_database':str(target)},origin)
                connection=client._connect({'route':{**route,'database':str(target)}})
                try:connection.execute_immediate('CREATE TABLE REPLACED_MARKER(ID INTEGER)');connection.commit()
                finally:client._forget_and_close(connection)
                apply({'backup_file':str(backup),'restore_database':str(target),'replace_existing':True,'confirmation':str(target)},origin)
                readback(target)
                connection=client._connect({'route':{**route,'database':str(target)}})
                try:
                    q=connection.cursor();q.execute("SELECT COUNT(*) FROM RDB$RELATIONS WHERE RDB$RELATION_NAME='REPLACED_MARKER'");assert q.fetchone()==(0,);q.close();connection.rollback()
                finally:client._forget_and_close(connection)
                proof['checks'].append({'case':'explicit-replacement','old_marker_removed_and_restored_data_verified':True})
                target=data/'stale destination.fdb';request=review('restore_logical',{'backup_file':str(backup),'restore_database':str(target)},origin)
                target.write_bytes(b'foreign destination')
                try:visual.apply(request)
                except VisualAdminExecutionError as error:assert error.operation['unknown_outcome'] is False
                else:raise AssertionError('Restore overwrote a destination created after review')
                replay_refused(request);assert target.read_bytes()==b'foreign destination'
                proof['checks'].append({'case':'stale-destination','known_pre_dispatch_refusal':True,'foreign_file_preserved':True})
                copied=data/'raced input.fbk';copied.write_bytes(backup.read_bytes());target=data/'raced input restored.fdb'
                dispatch=client.run_server_operation
                def replace(*args,**kwargs):
                    copied.rename(data/'retained backup input.fbk');copied.write_bytes(b'foreign replacement input')
                    return dispatch(*args,**kwargs)
                client.run_server_operation=replace
                try:result=apply({'backup_file':str(copied),'restore_database':str(target)},origin)
                finally:client.run_server_operation=dispatch
                readback(target)
                assert not result['local_restore_files']['backup_inputs'][0]['requested_path_still_names_input']
                assert copied.read_bytes()==b'foreign replacement input'
                proof['checks'].append({'case':'input-replaced-during-dispatch','pinned_backup_restored':True,'replacement_untouched':True,'path_change_reported':True})
                corrupt=data/'invalid backup.fbk';corrupt.write_bytes(b'owned invalid backup bytes');target=data/'native failure.fdb'
                request=review('restore_logical',{'backup_file':str(corrupt),'restore_database':str(target)},origin)
                try:visual.apply(request)
                except VisualAdminExecutionError as error:
                    assert error.operation['unknown_outcome']
                    assert error.operation['impact']['restore_files']['outputs'][0]['filename']==str(target)
                else:raise AssertionError('Invalid native backup reported successful restore')
                replay_refused(request);proof['checks'].append({'case':'invalid-backup','native_failure_unknown_no_replay':True,'requested_destination_retained_in_receipt':True})
                target=data/'lost response restored.fdb';request=review('restore_logical',{'backup_file':str(backup),'restore_database':str(target)},origin)
                completed=[]
                def lose(*args,**kwargs):
                    completed.append(dispatch(*args,**kwargs))
                    from pgadmin.cdeadmin.sdk import RelationalClientError
                    raise RelationalClientError('Owned qualifier lost an actual completed restore response')
                client.run_server_operation=lose
                try:
                    try:visual.apply(request)
                    except VisualAdminExecutionError as error:assert error.operation['unknown_outcome']
                    else:raise AssertionError('Lost restore response reported known success')
                finally:client.run_server_operation=dispatch
                replay_refused(request);assert len(completed)==1 and completed[0]['server_completed'];readback(target)
                proof['checks'].append({'case':'lost-response','actual_restore_read_back_but_operation_remains_unknown':True})
                assert pending.main_transaction.is_active()
                q=pending.cursor();q.execute('SELECT ID FROM "雪DATA" ORDER BY ID');assert q.fetchall()==[(23,),(999,)];q.close();pending.rollback()
                proof['checks'].append({'case':'caller-transaction','pending_native_row_preserved_until_explicit_rollback':True})
            finally:client._forget_and_close(pending);client.close()
        proof['owned_state_removed']=not area.exists()
        proof['source_runtime_unchanged']=_runtime_fingerprint(runtime)==before
        proof['complete']=len(proof['checks'])==13 and proof['owned_state_removed'] and proof['source_runtime_unchanged']
    finally:(output/'native.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();value=qualify(args.runtime,args.output)
    print(json.dumps({'complete':value['complete'],'checks':len(value['checks'])}))
    raise SystemExit(0 if value['complete'] else 1)

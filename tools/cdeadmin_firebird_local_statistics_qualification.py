"""Qualify local statistics on an owned Engine13-only runtime and database."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output,runtime):
    from tools.cdeadmin_firebird_object_live_orchestrator import _stage_runtime,_runtime_fingerprint
    output=Path(output).resolve();runtime=Path(runtime).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Qualification artifacts belong outside source')
    output.mkdir(parents=True,exist_ok=True,mode=0o700)
    names=['web/pgadmin/cdeadmin/providers/firebird/'+name for name in (
        'local_services.py','embedded_provider.py','provider.py','query_client.py','service_connection.py')]
    names+=['web/pgadmin/cdeadmin/ui_descriptors/firebird/capabilities.json',
            'tools/cdeadmin_firebird_local_statistics_qualification.py']
    proof={'complete':False,'scope':'Owned Engine13-only local native Firebird5.0.4 client validate/plan/apply and statistics; no network server or credentials. Linux private-hardlink inode qualification; not HTTP or other-platform acceptance.',
        'checks':[],'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()for name in names}}
    before=_runtime_fingerprint(runtime);area=None
    try:
        with tempfile.TemporaryDirectory(prefix='firebird-local-statistics-',dir=output)as folder:
            area=Path(folder);stage=area/'runtime';_stage_runtime(runtime,stage)
            (stage/'firebird.conf').write_text('Providers = Engine13\nSecurityDatabase = '+str(stage/'security5.fdb')+'\n')
            (stage/'databases.conf').write_text('')
            os.environ.update(FIREBIRD=str(stage),FIREBIRD_LOCK=str(stage/'lock'),
                CDEADMIN_FIREBIRD_CLIENT_LIBRARY=str(stage/'lib/libfbclient.so.5.0.4'))
            import firebird.driver as module
            module.driver_config.fb_client_library.value=str(stage/'lib/libfbclient.so.5.0.4')
            from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
            from pgadmin.cdeadmin.providers.firebird.provider import _create_client
            from pgadmin.cdeadmin.sdk import RelationalClientError
            permitted={'embedded_runtime','filesystem','data_read','administer','execute'};requested=[]
            def require(name,*_):
                requested.append(name)
                if name not in permitted:raise AssertionError('Unexpected nonlocal permission')
            def secret(*_):raise AssertionError('Embedded statistics acquired a network secret')
            client=_create_client(SimpleNamespace(require=require,acquire_secret=secret),
                attachment_mode='embedded',profile=embedded.PROFILE,administration=embedded.ADMINISTRATION)
            data=area/'data';data.mkdir();route={'attachment_mode':'embedded','database':str(data/'Owned 雪.fdb'),'filesystem_root':str(data),'user':'SYSDBA','charset':'UTF8'}
            def create(selected):
                c=client.config.database_creator(**client.config.database_create_arguments(selected,selected['database'],{}))
                q=c.cursor()
                try:
                    q.execute('CREATE TABLE "Stats 雪"(ID INTEGER)');c.commit();q.execute('INSERT INTO "Stats 雪" VALUES(1)');c.commit()
                    q.execute("SELECT RDB$GET_CONTEXT('SYSTEM','ENGINE_VERSION'),RDB$GET_CONTEXT('SYSTEM','NETWORK_PROTOCOL') FROM RDB$DATABASE");identity=q.fetchone();c.rollback()
                    assert identity==('5.0.4',None),identity
                    q.execute('SELECT MON$DATABASE_NAME FROM MON$DATABASE');actual=q.fetchone()[0];c.rollback()
                    return actual
                finally:q.close();c.close()
            try:
                create(route)
                base={'resource_kind':'database','operation_id':'database_statistics','_provider_route':route,
                    'draft':{'statistics_flags':['HDR_PAGES']}}
                assert not client.validate_admin_operation(base)['errors']
                planned=client.plan_admin_operation(base);response=client.apply_admin_operation(planned);result=response['driver_observation']
                assert result['server_completed']and result['native_provider']=='Engine13'and not result['network_authentication']
                assert result['native_utility_exit_code_observed']is False and result['native_utility_exit_code']is None
                assert result['service_release']['connection_released']and result['service_release']['service_handle_released']
                assert any('Database header page information'in line for line in result['output']),result['output']
                proof['checks'].append({'scope':'native-header-statistics-unicode-path','line_count':len(result['output']),'output_sha256':hashlib.sha256(json.dumps(result['output'],ensure_ascii=False).encode()).hexdigest()})
                selected={**base,'draft':{'statistics_flags':['DATA_PAGES','IDX_PAGES'],'tables':[{'value':'Stats 雪'}]}}
                response=client.apply_admin_operation(client.plan_admin_operation(selected));result=response['driver_observation'];assert result['server_completed'];assert any('Stats 雪'in line for line in result['output']),result['output']
                proof['checks'].append({'scope':'native-typed-table-filter','line_count':len(result['output']),'output_sha256':hashlib.sha256(json.dumps(result['output'],ensure_ascii=False).encode()).hexdigest()})
                # Unlink the original after review/pinning and replace its path
                # during actual native dispatch. A symlink descriptor that is merely
                # canonicalized back to the original pathname cannot pass this.
                original=Path(route['database']);original_bytes=original.read_bytes()
                native_path=client._server_operation_database;swapped=[False]
                def swap_during_native_dispatch(database):
                    if not swapped[0]:
                        swapped[0]=True
                        assert '/.scratchrobin-statistics-' in database
                        original.unlink();create(route)
                        c=client._connect({'route':route});q=c.cursor()
                        try:
                            q.execute('DROP TABLE "Stats 雪"');q.execute('CREATE TABLE REPLACEMENT(ID INTEGER)');c.commit()
                        finally:q.close();client._forget_and_close(c)
                    return native_path(database)
                client._server_operation_database=swap_during_native_dispatch
                try:
                    response=client.apply_admin_operation(client.plan_admin_operation(selected))
                    result=response['driver_observation']
                    assert result['file_identity_race_fenced'] and result['server_completed']
                    assert any('Stats 雪' in line for line in result['output']),result['output']
                    assert swapped[0] and result['service_release']['service_handle_released']
                    proof['checks'].append('Native statistics read the pinned original after unlink and same-path replacement during dispatch')
                finally:
                    client._server_operation_database=native_path
                    original.unlink(missing_ok=True);original.write_bytes(original_bytes)
                for flag in ('DATA_PAGES','HDR_PAGES','IDX_PAGES','SYS_RELATIONS','RECORD_VERSIONS','NOCREATION','ENCRYPTION'):
                    item={**base,'draft':{'statistics_flags':[flag]}}
                    result=client.apply_admin_operation(client.plan_admin_operation(item))['driver_observation']
                    assert result['server_completed'] and result['file_identity_race_fenced']
                    proof['checks'].append({'scope':'native-statistics-flag','flag':flag,'lines':len(result['output'])})
                obsolete={**base,'draft':{'statistics_flags':['DB_LOG']}}
                assert client.validate_admin_operation(obsolete)['errors']
                try:client.plan_admin_operation(obsolete)
                except RelationalClientError:pass
                else:raise AssertionError('Obsolete native DB_LOG option admitted')
                proof['checks'].append('Native5 obsolete DB_LOG is refused by typed validation and before service attachment')
                for changed in [{'host':'127.0.0.1'},{'credential_reference_id':'not-local'}]:
                    try:client.plan_admin_operation({**base,'_provider_route':{**route,**changed}})
                    except RelationalClientError:pass
                    else:raise AssertionError('Network authority admitted')
                proof['checks'].append('Network host/credential reference refused before action')
                planned=client.plan_admin_operation(base);original=Path(route['database']);retained=data/'Retained original.fdb';original.rename(retained);create(route)
                try:client.apply_admin_operation(planned)
                except RelationalClientError as error:
                    assert 'changed since review'in str(error)
                    assert error.rejected and error.nothing_changed and not error.native_dispatched
                else:raise AssertionError('Replaced file admitted')
                proof['checks'].append('Same-path file replacement refused before dispatch')
                c=client._connect({'route':{**route,'database':str(retained)}});q=c.cursor()
                try:q.execute('SELECT COUNT(*) FROM "Stats 雪"');assert q.fetchone()==(1,);c.rollback()
                finally:q.close();client._forget_and_close(c)
                proof['checks'].append('Independent original-file row read-back preserved')
                trial={**route,'database':str(data/'Trailing.fdb ')}
                actual=create(trial)
                proof['filename_creation_probe']={'requested':trial['database'],'native_reported':actual,'requested_file_present':Path(trial['database']).is_file()}
                if not Path(trial['database']).is_file():
                    try:client.plan_admin_operation({**base,'_provider_route':trial})
                    except RelationalClientError:proof['checks'].append('Missing requested filename refused even when native creation reports another spelling')
                    else:raise AssertionError('Unqualified filename normalization was admitted')

            finally:client.close()
            proof['permissions_requested']=sorted(set(requested))
        proof['owned_state_removed']=not area.exists();proof['source_runtime_unchanged']=_runtime_fingerprint(runtime)==before
        proof['complete']=proof['owned_state_removed']and proof['source_runtime_unchanged']
    finally:(output/'firebird-local-statistics-native.json').write_text(json.dumps(proof,indent=2)+'\n')
    if not proof['complete']:raise RuntimeError('Local Firebird statistics qualification incomplete')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--runtime',type=Path,required=True)
    args=parser.parse_args();result=qualify(args.output,args.runtime);print(json.dumps({'complete':result['complete'],'checks':len(result['checks'])}))

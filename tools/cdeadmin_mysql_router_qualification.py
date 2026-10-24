"""Native Router application bootstrap on an explicitly owned peer network."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output,fixture,use_c=False):
    output=Path(output).resolve();fixture=Path(fixture).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep owned qualification state outside source')
    output.mkdir(parents=True,exist_ok=False);owned=json.loads(fixture.read_text())
    if not owned.get('complete') or not owned['network'].startswith('sr-router240-'):raise ValueError('Select the explicitly owned native Router fixture')
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    app=setup_application(output)
    from flask import url_for
    from pgadmin.model import db,User,ServerGroup,Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.workspace import service_for_app
    from pgadmin.cdeadmin.providers.mysql_family import mysql_router_transport as native
    client=app.test_client();service=service_for_app(app)
    proof={'complete':False,'history_testing':'not run','interface':'c' if use_c else 'pure','checks':[]}
    names=['tools/cdeadmin_mysql_router_qualification.py','web/pgadmin/cdeadmin/providers/mysql_family/mysql_router_transport.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_router_worker.py','web/pgadmin/cdeadmin/workspace/mysql_router_service.py',
        'web/pgadmin/cdeadmin/workspace/service.py','web/pgadmin/browser/server_groups/servers/__init__.py']
    proof['source_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in names}
    try:
        seed=owned['peers'][0]
        with app.test_request_context('/'):
            uid=User.query.first().id;group=ServerGroup.query.filter_by(user_id=uid).first()
            app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
            server=Server(user_id=uid,servergroup_id=group.id,name='Owned native Router seed',host=seed['host'],port=3306,username='root',maintenance_db=None,save_password=0)
            server._cde_endpoint_registration=registration_profile('mysql-native')
            server._cde_endpoint_route_configuration={'host':seed['host'],'port':3306,'user':'root','use_pure':not use_c,'credential_kinds':['database_password']}
            db.session.add(server);db.session.commit()
            verify=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=server.id)
            url=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=server.id)
        with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
        assert client.post(verify,json={'password':'true'}).get_json()['success']
        def post(action,request,refused=False):
            response=client.post(url,json={'action':'mysql_router_'+action,'request':request});value=response.get_json()
            if refused:
                assert response.status_code==400,value
                return value
            if response.status_code!=200 or not value.get('success'):
                (output/'http-failure.json').write_text(json.dumps(value,indent=2)+'\n')
                raise AssertionError('Native Router application request failed: '+action)
            return value['data']
        catalog=post('catalog',{});assert catalog['identity']['server_uuid']==seed['server_uuid']
        key=Path(owned['private_key']).read_text();credentials={'private_key':key}
        chosen={'connection':{'host':owned['router_address'],'port':22,'username':'root','host_key':owned['host_key'],
            'authentication':'private_key','platform':'posix','python':'python3'},'executable':'/usr/bin/mysqlrouter',
            'directory':'/opt/sr-router-'+secrets.token_hex(8),'workspace':'/tmp/sr-router-jobs','user':'mysqlrouter','base_port':16446,
            'bind_address':'0.0.0.0','seed':catalog['suggested_seed'],'extra_arguments':['--name=sr-native-router-'+secrets.token_hex(8),'--conf-skip-x-protocol'],'timeout_seconds':120}
        reviewed=post('review',{'options':chosen,'credentials':credentials})
        assert reviewed['execution_host']['hostname']=='sr-router-native-host'
        assert reviewed['remote_observation']['seed']['server_uuid']==seed['server_uuid']
        assert 'server_uuid' not in reviewed['remote_observation']['host']
        assert reviewed['source_connection_class']==('CharsetCMySQLConnection' if use_c else 'CharsetMySQLConnection')
        proof['checks'].append('authenticated-application-source-and-independent-native-Router-host-seed-binding-with-actual-selected-driver')
        admitted={**{key:reviewed[key] for key in ('job_id','review_digest')},'confirmed':True,'credentials':credentials}
        post('start',{**admitted,'confirmed':False},refused=True)
        current=post('start',admitted);deadline=time.monotonic()+150
        while current['state'] in {'dispatching','active','cancel_requested'}:
            if time.monotonic()>deadline:raise TimeoutError('Native Router bootstrap qualification deadline')
            time.sleep(.1);current=post('status',{'job_id':current['job_id']})
        (output/'bootstrap-receipt.json').write_text(json.dumps(current,indent=2)+'\n')
        assert current['state']=='native_process_returned',current.get('error_message') or current.get('error_type')
        remote=current['remote_receipt'];assert remote['result']['return_code']==0
        assert remote['result']['cleanup_confirmed'] and remote['result']['credential_file_cleanup_confirmed'] and remote['result']['input_file_cleanup_confirmed']
        deployment=remote['deployment_observation'];assert deployment['observed'] and len(deployment['native_router_ids'])==1
        assert deployment['sensitive_file_contents_omitted'] and not remote['sql_readiness_observed']
        assert post('start',{**admitted,'credentials':{}})['remote_receipt']==remote
        original=native.Transport.request
        def no_sql(self,request,*args,**kwargs):
            assert request['action'] in {'status','cancel','acknowledge'} and 'database_password' not in request
            return original(self,request,*args,**kwargs)
        from unittest.mock import patch
        with patch.object(native.Transport,'request',no_sql):
            later=post('reconcile',{'job_id':current['job_id'],'credentials':credentials})
        facts=later['reconciliation']['remote_receipt']['utility_observation']
        assert facts['cleanup_confirmed'] and later['reconciliation']['original_ssh_acknowledgement_unchanged']
        proof['checks'].append('actual-native-Router-bootstrap-private-input-cleanup-generated-native-ID-manifest-no-replay-and-SQL-independent-original-observation')
        post('review',{'options':chosen,'credentials':credentials},refused=True)
        assert key not in json.dumps(current)
        def operate(operation,binding,lose_reply=False):
            options={**chosen,'operation':operation,'binding_job_id':binding['job_id'],
                'service':{'manager':'systemd','name':'sr-router-'+secrets.token_hex(4)+'.service'} if operation=='install_service' else binding['options']['service'],
                'disconnect_all_clients':operation in {'service_stop','service_restart'}}
            planned=post('review',{'options':options,'credentials':credentials})
            assert planned['source_identity_scope']=='original_native_router_deployment_and_current_ssh_host_authority'
            command={**{name:planned[name] for name in ('job_id','review_digest')},'confirmed':True,'credentials':credentials}
            def lost(self,request,*args,**kwargs):
                answer=original(self,request,*args,**kwargs)
                if request['action']==operation:raise native.HostError('Owned test lost the original native service acknowledgement')
                return answer
            with patch.object(native.Transport,'request',lost if lose_reply else original):
                result=post('start',command);deadline=time.monotonic()+150
                while result['state'] in {'dispatching','active','cancel_requested'}:
                    if time.monotonic()>deadline:raise TimeoutError('Native Router service deadline')
                    time.sleep(.1);result=post('status',{'job_id':result['job_id']})
            (output/(operation+'-receipt.json')).write_text(json.dumps(result,indent=2)+'\n')
            assert result['state']==('unknown' if lose_reply else 'native_process_returned'),result.get('error_message') or result.get('error_type')
            if not lose_reply:assert result['remote_receipt']['result']['return_code']==0,result['remote_receipt']
            reconciled=post('reconcile',{'job_id':result['job_id'],'credentials':credentials})
            assert reconciled['state']==result['state']
            observations=reconciled['reconciliation']['remote_receipt']['native_command_observations']
            assert observations and all(item['cleanup_confirmed'] for item in observations)
            return reconciled
        installed=operate('install_service',current)
        install=installed['remote_receipt']['service_installation_result']
        assert install['installed'] and not install['restart_issued'] and not install['enable_issued']
        assert install['configuration_validation'] is None
        enabled=operate('service_enable',installed)
        assert enabled['remote_receipt']['service_after']['unit']['UnitFileState']=='enabled'
        disabled=operate('service_disable',enabled)
        assert disabled['remote_receipt']['service_after']['unit']['UnitFileState']=='disabled'
        started=operate('service_start',disabled)
        import mysql.connector
        database='sr_router_'+secrets.token_hex(6)
        def routed(port=16446):
            return mysql.connector.connect(host=owned['router_address'],port=port,user='root',password='true',use_pure=not use_c,
                ssl_disabled=False,connection_timeout=5,read_timeout=5,write_timeout=5)
        deadline=time.monotonic()+30
        while True:
            try:
                connection=routed();break
            except mysql.connector.Error:
                if time.monotonic()>deadline:raise
                time.sleep(.2)
        try:
            cursor=connection.cursor();cursor.execute('SELECT @@server_uuid,@@read_only');identity=cursor.fetchone()
            assert identity[0] in {peer['server_uuid'] for peer in owned['peers']} and identity[1]==0,identity
            cursor.execute('CREATE DATABASE '+database)
            cursor.execute('CREATE TABLE '+database+'.committed (id BIGINT PRIMARY KEY,value VARCHAR(120))')
            cursor.execute('INSERT INTO '+database+'.committed VALUES (9007199254740993,%s)',('native Router 雪',));connection.commit()
        finally:connection.close()
        restarted=operate('service_restart',started)
        connection=routed()
        try:
            cursor=connection.cursor();cursor.execute('SELECT * FROM '+database+'.committed')
            assert cursor.fetchall()==[(9007199254740993,'native Router 雪')]
        finally:connection.close()
        stopped=operate('service_stop',restarted)
        assert stopped['remote_receipt']['service_after']['unit']['ActiveState']=='inactive'
        started_again=operate('service_start',stopped)
        controls=fixture.parent/'controls';controls.mkdir(exist_ok=True)
        def control(operation,peer):
            identity=secrets.token_hex(10);request=controls/(identity+'.request.json');answer=controls/(identity+'.answer.json')
            request.write_text(json.dumps({'operation':operation,'container':peer['container']})+'\n')
            deadline=time.monotonic()+45
            while not answer.exists():
                if time.monotonic()>deadline:raise TimeoutError('Owned native fixture controller deadline')
                time.sleep(.1)
            result=json.loads(answer.read_text());assert result['return_code']==0,result
        connection=routed();cursor=connection.cursor();cursor.execute('SELECT @@server_uuid');primary=cursor.fetchone()[0]
        failed=next(peer for peer in owned['peers'] if peer['server_uuid']==primary)
        try:
            cursor.execute('INSERT INTO '+database+'.committed VALUES (9007199254740994,%s)',('pending must roll back',))
            control('crash',failed)
            try:cursor.execute('SELECT 1')
            except mysql.connector.Error:pass
            else:raise AssertionError('The original routed session survived loss of its native primary')
            deadline=time.monotonic()+90
            while True:
                routed_connection=None
                try:
                    routed_connection=routed();routed_cursor=routed_connection.cursor();routed_cursor.execute('SELECT @@server_uuid,@@read_only');new_primary=routed_cursor.fetchone()
                    if new_primary[0]!=primary and new_primary[1]==0:break
                except mysql.connector.Error:pass
                if routed_connection is not None:routed_connection.close()
                if time.monotonic()>deadline:raise TimeoutError('Native Router failover deadline')
                time.sleep(.5)
            try:
                routed_cursor.execute('SELECT * FROM '+database+'.committed ORDER BY id')
                assert routed_cursor.fetchall()==[(9007199254740993,'native Router 雪')]
                routed_cursor.execute('INSERT INTO '+database+'.committed VALUES (9007199254740995,%s)',('committed after failover',));routed_connection.commit()
            finally:routed_connection.close()
            # Native Router controls must remain available while the originally
            # registered SQL seed is gone. No source SQL preflight is permitted.
            from pgadmin.cdeadmin.workspace import mysql_router_service
            with patch.object(mysql_router_service,'source',side_effect=AssertionError('Router service control attempted source SQL')):
                offline_stopped=operate('service_stop',started_again)
                started_again=operate('service_start',offline_stopped)
            readonly=routed(16447)
            try:
                readonly_cursor=readonly.cursor();readonly_cursor.execute('SELECT @@read_only');assert readonly_cursor.fetchone()==(1,)
            finally:readonly.close()
            proof['checks'].append('actual-native-primary-crash-group-election-new-routed-writer-pending-rollback-committed-data-and-readonly-route-with-SQL-independent-Router-controls')
        finally:
            connection.close();control('start',failed)
        deadline=time.monotonic()+90
        while True:
            connection=routed()
            try:
                cursor=connection.cursor();cursor.execute("SELECT COUNT(*) FROM performance_schema.replication_group_members WHERE MEMBER_STATE='ONLINE'")
                if cursor.fetchone()==(3,):break
            finally:connection.close()
            if time.monotonic()>deadline:raise TimeoutError('Native crashed member rejoin deadline')
            time.sleep(.5)
        uncertain=operate('service_disable',started_again,lose_reply=True)
        assert uncertain['state']=='unknown' and not uncertain.get('ssh_reply_observed')
        operate('service_stop',uncertain)
        proof['checks'].append('native-systemd-exclusive-install-enable-disable-start-restart-stop-routed-TLS-exact-bigint-and-text-original-unknown-no-replay')
        proof.update(complete=True,native_router_id=deployment['native_router_ids'][0],job_id=current['job_id'],deployment=chosen['directory'],server_id=server.id)
    finally:
        jobs=getattr(service,'mysql_router_jobs',None);proof['owned_jobs_stopped']=jobs.close() if jobs is not None else True
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--fixture',required=True);parser.add_argument('--use-c',action='store_true')
    parser.add_argument('--browser-only-application');parser.add_argument('--server-id',type=int);parser.add_argument('--browser-binary');parser.add_argument('--driver-binary');args=parser.parse_args()
    if args.browser_only_application:
        if not all((args.server_id,args.browser_binary,args.driver_binary)):parser.error('Select the native application server and desktop binaries')
        from mysql_router_ui_qualification import qualify as desktop
        result=desktop(args.output,args.fixture,args.browser_only_application,args.server_id,args.browser_binary,args.driver_binary)
    else:result=qualify(args.output,args.fixture,args.use_c)
    print(json.dumps({'complete':result['complete'],'checks':len(result['checks'])}))

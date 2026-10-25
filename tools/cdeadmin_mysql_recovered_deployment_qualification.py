"""Native cold recovery staging, data/log preservation and permanent restart."""
import argparse
from copy import deepcopy
import json
import hashlib
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output,fixture,use_c=False,mysql_shell=None,browser_binary=None,driver_binary=None,interrupt=False):
    import mysql.connector
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    from cdeadmin_mysql_online_ddl_qualification import registration
    from cdeadmin_mysql_recovery_connection_qualification import endpoint,query_post,execute
    from pgadmin.model import User
    from pgadmin.cdeadmin.workspace import service_for_app
    from cdeadmin_mysql_physical_replay_qualification import wait_job,start_request
    from pgadmin.cdeadmin.providers.mysql_family import mysql_system_state
    os.environ['CDEADMIN_MYSQLSH_BINARY']=str(Path(mysql_shell).resolve(strict=True))
    output=Path(output).resolve();output.mkdir(exist_ok=False)
    owned=json.loads(Path(fixture).read_text());assert owned['complete'] and owned['container'].startswith('sr-deployment248-')
    app=setup_application(output);client=app.test_client()
    proof={'complete':False,'use_c':use_c,'checks':[],'history_testing':'ScratchBird history not run',
        'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [
            Path(__file__),ROOT/'tools/mysql_recovery_cutover_ui_qualification.py',
            *[ROOT/'web/pgadmin/cdeadmin/providers/mysql_family'/name for name in ('mysql_recovery_deployment.py','mysql_recovery_worker.py','mysql_physical_worker.py','mysql_physical_transport.py','mysql_host_worker.py')],
            *[ROOT/'web/pgadmin/cdeadmin/workspace'/name for name in ('mysql_recovery_cutover.py','mysql_physical_service.py','mysql_instance_acceptance_jobs.py')]]}}
    def connect(port):return mysql.connector.connect(host='127.0.0.1',port=port,user='sr_physical',
        password='owned-deployment-private',use_pure=not use_c,autocommit=True,connection_timeout=3,read_timeout=5)
    def sql(port,source,parameters=()):
        connection=connect(port);cursor=connection.cursor(dictionary=True)
        try:cursor.execute(source,parameters);return cursor.fetchall() if cursor.with_rows else []
        finally:cursor.close();connection.close()
    sql(owned['sql_port'],'CREATE DATABASE IF NOT EXISTS sr_osc CHARACTER SET utf8mb4')
    sql(owned['sql_port'],'CREATE TABLE IF NOT EXISTS sr_osc.t(id BIGINT PRIMARY KEY,body TEXT,payload LONGBLOB)')
    if owned.get('encrypted_external'):
        sql(owned['sql_port'],"ALTER TABLE sr_osc.t ENCRYPTION='Y'")
        sql(owned['sql_port'],"CREATE TABLESPACE sr_recovery_external ADD DATAFILE '/opt/sr-external-deployment/external.ibd' ENCRYPTION='Y' ENGINE=InnoDB")
        sql(owned['sql_port'],"CREATE TABLE sr_osc.external_t(id BIGINT PRIMARY KEY,note TEXT) TABLESPACE sr_recovery_external ENCRYPTION='Y'")
        sql(owned['sql_port'],"INSERT INTO sr_osc.external_t VALUES(1,'native encrypted external 雪')")
    sql(owned['sql_port'],'DELETE FROM sr_osc.t')
    sql(owned['sql_port'],'INSERT INTO sr_osc.t VALUES(%s,%s,%s)',(9007199254740993,'native cold stage 雪',b'\x00\xff'))
    sid,target,_=registration(app,{'host':'127.0.0.1','port':owned['sql_port']},'owned-deployment-private',use_c,username='sr_physical')
    with app.test_request_context('/'):uid=User.query.first().id
    with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
    source_url=endpoint(app,sid)
    def post(action,request,*,url=None,prefix='mysql_physical_',refused=False):
        response=client.post(url or source_url,json={'action':prefix+action,'request':request});value=response.get_json()
        if refused:assert response.status_code==400,value;return value
        if response.status_code!=200 or not value.get('success'):
            (output/'http-failure.json').write_text(json.dumps(value,indent=2)+'\n');raise AssertionError('Native deployment action failed: '+action)
        return value['data']
    credentials={'private_key':Path(owned['private_key']).read_text()}
    base={'connection':{'host':'127.0.0.1','port':owned['ssh_port'],'username':'root','host_key':owned['host_key'],
        'authentication':'private_key','platform':'posix','python':'python3'},'workspace':'/tmp/sr-deployment-jobs',
        'executable':'/opt/sr-xtrabackup/bin/xtrabackup','mysql':'/opt/sr-mysql-client/mysql',
        'phase':'backup','sql_host':'127.0.0.1','sql_port':3306,'input_job_id':None,'parallel':2,
        'memory_bytes':67108864,'timeout_seconds':120,'accept_release_candidate':True}
    if owned.get('encrypted_external'):base.update(keyring={'xtrabackup_plugin_dir':'/opt/sr-xtrabackup-keyring'},isolate_external_paths=True)
    runtimes=[];attached=None
    def wait(job,mode='files'):
        deadline=time.monotonic()+240
        while time.monotonic()<deadline:
            value=post('reconcile',{'job_id':job['job_id'],'credentials':credentials});remote=value.get('remote_observation') or {}
            if mode=='files' and value['file_verification_confirmed']:return value
            if mode=='running' and value['recovery_running']:return value
            if mode=='ended' and remote.get('runtime_process_live') is False and remote.get('supervisor_process_live') is False:return value
            if mode=='deployed' and remote.get('supervisor_finished') and remote.get('return_code')==0:return value
            if remote.get('error_type') or remote.get('supervisor_finished') and remote.get('return_code') not in {0,None}:
                (output/'native-failure.json').write_text(json.dumps(value,indent=2)+'\n')
                (output/'native-output.json').write_text(json.dumps(post('output',{'job_id':value['job_id'],'credentials':credentials}),indent=2)+'\n')
                raise AssertionError('Native recovered deployment operation failed')
            time.sleep(.2)
        raise TimeoutError('Native recovered deployment observation deadline')
    def phase(name,parent=None,mode='files',**changes):
        selected={**deepcopy(base),'phase':name,'input_job_id':parent,**changes}
        review=post('review',{'options':selected,'credentials':credentials})
        value=post('start',{**{k:review[k] for k in ('job_id','review_digest')},'confirmed':True,
            'delegate_database_credentials':name in {'backup','recover'},'credentials':credentials})
        result=wait(value,mode);(output/(name+'-receipt.json')).write_text(json.dumps(result,indent=2)+'\n');return result
    try:
        backed=phase('backup');prepared=phase('prepare',backed['job_id']);copied=phase('copy_back',prepared['job_id'])
        runtime=phase('recover',copied['job_id'],mode='running',mysqld='/opt/mysql97/usr/sbin/mysqld',
            recovery_gtid_mode='ON',recovery_mode='replay',recovery_port=3348,recovery_server_id=33048,recovery_local_infile=True,timeout_seconds=600)
        runtimes.append(runtime)
        review=post('connection_review',{'job_id':runtime['job_id'],'name':'Owned cold-stage recovery','credentials':credentials})
        attached=post('connection_connect',{**{k:review[k] for k in ('job_id','review_digest') if k!='job_id'},'review_id':review['job_id'],
            'confirmed':True,'delegate_database_credentials':True,'credentials':credentials})['result']
        url=endpoint(app,attached['server_id']);query=lambda action,**body:query_post(client,url,attached['database_target_id'],action,**body)
        session=query('open_session',language_profile='mysql-sql')['session_id']
        try:
            execute(query,session,"INSERT INTO t VALUES(2,'recovered update 雪',X'0100FF')")
            expected=execute(query,session,'SELECT CAST(id AS CHAR),body,HEX(payload) FROM t ORDER BY id')['rows']
            uuid=execute(query,session,'SELECT @@server_uuid')['rows'][0][0]
        finally:query('close_session',session_id=session)
        post('connection_detach',{'server_id':attached['server_id']});attached=None
        staging={'directory':'/var/lib/sr-native-recovered-'+secrets.token_hex(5),'service':'sr-recovered-'+secrets.token_hex(5)+'.service',
            'bind_address':'0.0.0.0','port':3349,'server_id':33049}
        post('review',{'options':{**base,'phase':'deploy','input_job_id':runtime['job_id'],'deployment':staging},'credentials':credentials},refused=True)
        post('cancel',{'job_id':runtime['job_id'],'credentials':credentials});ended=wait(runtime,'ended')
        assert ended['remote_observation']['runtime_process_live'] is False
        staged=phase('deploy',runtime['job_id'],mode='deployed',deployment=staging)
        proof['checks'].append('new-review-refuses-live-recovery-and-copies-only-after-original-runtime-and-supervisor-births-end')
        def target_ready():
            deadline=time.monotonic()+60
            while True:
                try:
                    value=sql(owned['deployment_port'],'SELECT @@server_uuid AS uuid,VERSION() AS version,@@super_read_only AS ro,@@read_only AS read_only,@@log_bin AS logging,@@server_id AS server_id,@@event_scheduler AS scheduler')[0]
                    if value['uuid']==uuid and value['version']=='9.7.0':return value
                except mysql.connector.Error:
                    if time.monotonic()>deadline:raise
                if time.monotonic()>deadline:raise TimeoutError('Permanent native recovered listener readiness deadline')
                time.sleep(.2)
        observed=target_ready();assert observed['ro']==observed['read_only']==observed['logging']==1 and observed['server_id']==33049 and observed['scheduler']=='OFF',observed
        if owned.get('encrypted_external'):
            assert sql(owned['deployment_port'],'SELECT * FROM sr_osc.external_t')==[{'id':1,'note':'native encrypted external 雪'}]
            encryption=sql(owned['deployment_port'],'SELECT @@innodb_redo_log_encrypt AS redo_encrypted,@@innodb_undo_log_encrypt AS undo_encrypted,@@binlog_encryption AS binlog_encrypted')[0]
            assert encryption=={'redo_encrypted':1,'undo_encrypted':1,'binlog_encrypted':1},encryption
        assert [list(row.values()) for row in sql(owned['deployment_port'],'SELECT CAST(id AS CHAR),body,HEX(payload) FROM sr_osc.t ORDER BY id')]==expected
        assert len(sql(owned['sql_port'],'SELECT * FROM sr_osc.t'))==1
        try:sql(owned['deployment_port'],"INSERT INTO sr_osc.t VALUES(3,'must refuse',NULL)")
        except mysql.connector.Error as error:assert error.errno==1290,error
        else:raise AssertionError('Permanent staging admitted a write before activation')
        proof['checks'].append('permanent-native-service-preserves-original-recovered-UUID-post-base-data-and-logs-with-independent-read-only-listener-observations')
        target_sid,_,_=registration(app,{'host':'127.0.0.1','port':owned['deployment_port']},'owned-deployment-private',use_c,username='sr_physical')
        target_url=endpoint(app,target_sid)
        service_options={'connection':base['connection'],'executable':'/opt/mysql97/usr/sbin/mysqld','configuration_file':None,
            'workspace':'/tmp/sr-deployment-host','timeout_seconds':120,'operation':'service_restart',
            'service':{'manager':'systemd','name':staging['service']},'binding_job_id':None,'disconnect_all_clients':True}
        reviewed=post('review',{'options':service_options,'credentials':credentials},url=target_url,prefix='mysql_host_')
        value=post('start',{**{k:reviewed[k] for k in ('job_id','review_digest')},'confirmed':True,'credentials':credentials},url=target_url,prefix='mysql_host_')
        deadline=time.monotonic()+150
        while value['state'] in {'dispatching','active','cancel_requested'}:
            if time.monotonic()>deadline:raise TimeoutError('Permanent recovered native service restart deadline')
            time.sleep(.2);value=post('status',{'job_id':value['job_id']},url=target_url,prefix='mysql_host_')
        (output/'service-restart.json').write_text(json.dumps(value,indent=2)+'\n')
        assert value['state']=='native_process_returned' and value['remote_receipt']['result']['return_code']==0
        assert target_ready()['uuid']==uuid
        assert [list(row.values()) for row in sql(owned['deployment_port'],'SELECT CAST(id AS CHAR),body,HEX(payload) FROM sr_osc.t ORDER BY id')]==expected
        proof['checks'].append('new-normal-native-registration-and-reviewed-systemd-restart-preserve-permanent-recovered-data-and-read-only-role')
        staged=wait(staged,'deployed')
        assert staged['permanent_deployment']['observation']['permanent_native_process_verified'],staged
        sql(owned['sql_port'],"INSERT INTO sr_osc.t VALUES(2,'recovered update 雪',X'0100FF')")
        backups=lambda action,request:post(action,request,prefix='mysql_instance_backup_')
        expected_dump=wait_job(backups('start',start_request(backups('review',{'options':{
            'users':True,'checksum':True,'threads':1,'timeout_seconds':120,
            'system_state_tables':sorted(mysql_system_state.TABLES),'system_state_write_pause_confirmed':True}}))),backups,'completed')
        accept=lambda action,request:post(action,request,url=target_url,prefix='mysql_instance_acceptance_')
        acceptance=wait_job(accept('start',start_request(accept('review',{'source_server_id':sid,'backup_job_id':expected_dump['job_id'],
            'options':{'target_confirmation':uuid,'server_wide_write_pause_confirmed':True,'threads':1,'timeout_seconds':120}}))),accept,'verification_observed')
        assert acceptance['acceptance_outcome']=='matched',acceptance
        assert acceptance['result']['accounts']['matched'] and acceptance['result']['system_state']['matched']
        host_options={'connection':base['connection'],'executable':'/opt/mysql97/usr/sbin/mysqld',
            'configuration_file':owned['configuration'],'workspace':'/tmp/sr-deployment-source-controls','timeout_seconds':120,
            'operation':'service_stop','service':{'manager':'systemd','name':owned['service']},'binding_job_id':None,'disconnect_all_clients':True}
        controls=lambda action,request:post(action,request,prefix='mysql_host_')
        stopped=wait_job(controls('start',{**start_request(controls('review',{'options':host_options,'credentials':credentials})),
            'credentials':credentials}),controls,'native_process_returned')
        disabled=wait_job(controls('start',{**start_request(controls('review',{'options':{**host_options,'operation':'service_disable',
            'binding_job_id':stopped['job_id']},'credentials':credentials})),'credentials':credentials}),controls,'native_process_returned')
        selection={'deployment_job_id':staged['job_id'],'target_server_id':target_sid,'acceptance_job_id':acceptance['job_id'],
            'source_fence_job_id':disabled['job_id'],'target_confirmation':uuid,'event_scheduler':'OFF','acceptance_scope_acknowledged':True,
            'credentials':credentials}
        # A disabled/inactive unit can coexist with a manual native server.
        # Prove the dictionary-inode check refuses that real original writer.
        subprocess.run(['docker','exec','-d',owned['container'],owned['candidate'],'--defaults-file='+owned['configuration'],
            '--basedir=/opt/mysql97/usr','--user=mysql','--daemonize=OFF'],check=True)
        deadline=time.monotonic()+45
        while True:
            try:sql(owned['sql_port'],'SELECT @@server_uuid');break
            except mysql.connector.Error:
                if time.monotonic()>deadline:raise
                time.sleep(.2)
        post('cutover_review',selection,refused=True)
        try:sql(owned['sql_port'],'SHUTDOWN')
        except mysql.connector.Error as error:
            if error.errno not in {2006,2013}:raise
        while subprocess.check_output(['docker','exec',owned['container'],'python3','-c',
                "from pathlib import Path;print(Path('/opt/sr-deployment248/data/mysql.pid').exists())"],text=True).strip()=='True':
            if time.monotonic()>deadline:raise TimeoutError('Owned manual original shutdown deadline')
            time.sleep(.1)
        proof['checks'].append('inactive-disabled-unit-does-not-hide-an-actual-manually-started-original-native-dictionary-writer')
        cutovers=lambda action,request:post('cutover_'+action,request)
        if browser_binary:
            from mysql_recovery_cutover_ui_qualification import qualify as desktop
            activated=desktop(app,output/'desktop',sid,staged,selection,browser_binary,driver_binary)
            reviewed=activated
        else:
            reviewed=post('cutover_review',selection)
            if interrupt:
                from unittest.mock import patch
                from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_transport as transport
                original=transport.Transport.request
                def lost(peer,request):
                    reply=original(peer,request)
                    if request.get('action')=='activate_policy':raise transport.HostError('Owned loss after original startup commit')
                    return reply
                with patch.object(transport.Transport,'request',lost):
                    activated=wait_job(post('cutover_start',{**start_request(reviewed),'credentials':credentials}),cutovers,'unknown')
                assert activated['state']=='unknown' and activated['production_cutover_verified'] is False
                assert target_ready()['ro']==1
            else:activated=wait_job(post('cutover_start',{**start_request(reviewed),'credentials':credentials}),cutovers,'native_returned')
        (output/'activation.json').write_text(json.dumps(activated,indent=2)+'\n')
        if not interrupt:assert activated['production_cutover_verified'] and activated['result']['selected_dump_surfaces_verified'],activated
        again=post('cutover_start',{**start_request(reviewed),'credentials':credentials})
        assert again['job_id']==activated['job_id'] and again['finished_at']==activated['finished_at']
        observed=target_ready();assert observed['ro']==observed['read_only']==int(interrupt),observed
        if not interrupt:sql(owned['deployment_port'],"INSERT INTO sr_osc.t VALUES(3,'activated native write',X'00')")
        observed_activation=post('cutover_reconcile',{'job_id':activated['job_id'],'credentials':credentials})
        assert observed_activation['current_observation']['startup_activation']['job_id']==activated['job_id']
        if interrupt:assert observed_activation['state']=='unknown' and observed_activation['production_cutover_verified'] is False
        proof['checks'].append('matched-independent-expected-checkpoint-and-fresh-locked-native-acceptance-gate-stopped-disabled-source-and-once-only-writable-activation')
        reviewed=post('review',{'options':service_options,'credentials':credentials},url=target_url,prefix='mysql_host_')
        restarted=wait_job(post('start',{**start_request(reviewed),'credentials':credentials},url=target_url,prefix='mysql_host_'),
            lambda action,request:post(action,request,url=target_url,prefix='mysql_host_'),'native_process_returned')
        assert restarted['remote_receipt']['result']['return_code']==0 and target_ready()['ro']==0
        if interrupt:sql(owned['deployment_port'],"INSERT INTO sr_osc.t VALUES(3,'activated native write',X'00')")
        assert len(sql(owned['deployment_port'],'SELECT * FROM sr_osc.t'))==3
        if interrupt:
            observed_activation=post('cutover_reconcile',{'job_id':activated['job_id'],'credentials':credentials})
            assert observed_activation['state']=='unknown' and observed_activation['production_cutover_verified'] is False
            assert observed_activation['current_observation']['policy']['read_only']==0
            proof['checks'].append('lost-startup-commit-reply-retains-unknown-live-outcome-no-duplicate-dispatch-and-separately-observed-explicit-restart-policy')
        if owned.get('encrypted_external'):
            assert sql(owned['deployment_port'],'SELECT * FROM sr_osc.external_t')==[{'id':1,'note':'native encrypted external 雪'}]
            proof['checks'].append('permanent-encrypted-data-keyring-redo-undo-binary-logs-and-native-external-tablespace-namespace-survive-normal-host-controls-and-activation')
        proof['checks'].append('reviewed-native-restart-retains-activated-writable-startup-and-post-cutover-committed-data')
        proof.update(complete=True,service=staging['service'],deployment=staging['directory'],recovered_uuid=uuid)
    finally:
        if attached is not None:
            try:post('connection_detach',{'server_id':attached['server_id']})
            except Exception:pass
        for runtime in runtimes:
            try:post('cancel',{'job_id':runtime['job_id'],'credentials':credentials})
            except Exception:pass
        service=service_for_app(app);closed={key:getattr(service,key).close() for key in ('mysql_recovery_cutover_jobs','mysql_host_jobs','mysql_topology_jobs','mysql_binlog_replay_jobs') if getattr(service,key,None) is not None};proof['owned_jobs_stopped']=all(closed.values())
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--fixture',required=True);parser.add_argument('--use-c',action='store_true');parser.add_argument('--mysql-shell',required=True);parser.add_argument('--browser-binary');parser.add_argument('--driver-binary');parser.add_argument('--interrupt',action='store_true');args=parser.parse_args()
    result=qualify(args.output,args.fixture,args.use_c,args.mysql_shell,args.browser_binary,args.driver_binary,args.interrupt);print(json.dumps({'complete':result['complete'],'checks':len(result['checks'])}))

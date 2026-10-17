"""Native raw replay through authenticated HTTP and the browser workspace."""
import argparse
import builtins
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'web'),str(ROOT/'tools'),str(ROOT)]


def qualify(output,executable,decoder,client_binary,*,browser_binary=None,driver_binary=None,use_c=False,gtid_mode='OFF'):
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    proof={'complete':False,'checks':[],'history_testing':'not run','source_sha256':{},
        'base_qualification':'equivalent empty user schema and explicit native GTID seed on independent servers; not base recovery or production cutover'}
    for path in [*list((ROOT/'web/pgadmin/cdeadmin').rglob('*binlog*.py')),ROOT/'web/pgadmin/static/js/Dialogs/MySQLBinlogReplay.jsx',
                 ROOT/'web/pgadmin/browser/server_groups/servers/__init__.py',Path(__file__)]:
        proof['source_sha256'][str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    os.environ['CDEADMIN_MYSQLSH_BINARY']=str(Path(executable).resolve(strict=True));os.environ['CDEADMIN_MYSQL_BINLOG_BINARY']=str(Path(decoder).resolve(strict=True));os.environ['CDEADMIN_MYSQL_CLIENT_BINARY']=str(Path(client_binary).resolve(strict=True));builtins.SERVER_MODE=None
    import config
    config.SERVER_MODE=False;config.TESTING=True;config.WTF_CSRF_ENABLED=False
    config.MASTER_PASSWORD_REQUIRED=False;config.USE_OS_SECRET_STORAGE=False
    config.DATA_DIR=str(output/'app');config.SQLITE_PATH=str(output/'app/application.db')
    config.SESSION_DB_PATH=str(output/'app/sessions');config.STORAGE_DIR=str(output/'app/storage')
    config.LOG_FILE=str(output/'app/application.log');config.AZURE_CREDENTIAL_CACHE_DIR=str(output/'app/azure')
    config.CDEADMIN_OPERATION_STORE_PATH=str(output/'app/operations.json')
    config.CDEADMIN_MYSQL_BINLOG_ROOT=str(output/'shell-archives');config.CDEADMIN_MYSQL_RAW_BINLOG_ROOT=str(output/'raw-archives');config.CDEADMIN_MYSQL_BINLOG_REPLAY_ROOT=str(output/'replays')
    from pgadmin import create_app
    from pgadmin.model import db,User,ServerGroup,Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.workspace import service_for_app
    from pgadmin.cdeadmin.providers.mysql_family import mysql_raw_binlog_replay as native
    from flask import url_for
    from mysql_qualification_support import server,_root_connection
    app=create_app('ScratchRobin-native-mysql-raw-replay');app.PGADMIN_RUNTIME=False;app.PGADMIN_INT_KEY='';app.run_before_app_start()
    client=app.test_client();service=service_for_app(app);jobs=None
    password='native LF\nquote"slash\\雪-'+secrets.token_urlsafe(24)
    ddl=['CREATE DATABASE sr_replay CHARACTER SET utf8mb4','CREATE TABLE sr_replay.t(id BIGINT PRIMARY KEY,body TEXT,payload LONGBLOB)']
    from pgadmin.cdeadmin.sdk.tooling import ProviderToolRunner
    original_run=ProviderToolRunner.run;native_failures=[]
    def recording_run(self,grant,*args,**kwargs):
        result=original_run(self,grant,*args,**kwargs)
        if result['return_code']!=0:
            path=output/('native-tool-failure-'+str(len(native_failures))+'.log')
            with path.open('x',encoding='utf8') as stream:
                os.chmod(path,0o600);stream.write(result.get('stderr','').replace(password,'<redacted>'))
            native_failures.append(path.name)
        return result
    ProviderToolRunner.run=recording_run
    try:
        with ExitStack() as cleanup,server(output/'target-fixture',server_id=102,gtid_mode=gtid_mode) as (target_route,_target,owned_target):
            target_root=_root_connection('mysql',target_route['port']);cleanup.callback(target_root.close);target_root.autocommit=True
            target_query=target_root.cursor();cleanup.callback(target_query.close)
            for statement in ddl:target_query.execute(statement)
            target_query.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
            with server(output/'source-fixture',gtid_mode=gtid_mode) as (source_route,_source,owned_source):
                source_root=_root_connection('mysql',source_route['port']);source_root.autocommit=True;query=source_root.cursor()
                try:
                    query.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                    for statement in ddl:query.execute(statement)
                    query.execute('SELECT @@global.gtid_executed');baseline=query.fetchone()[0]
                    query.execute('FLUSH BINARY LOGS');query.execute('SHOW BINARY LOG STATUS');start=query.fetchone()[0];query.fetchall()
                    gtids=[];previous=baseline
                    for index in range(3):
                        query.execute('INSERT INTO sr_replay.t VALUES(%s,%s,%s)',(9007199254740993+index,'Unicode 😀 '+str(index),b'\x00\xff'+bytes([index])))
                        query.execute('SELECT GTID_SUBTRACT(@@global.gtid_executed,%s)',(previous,));gtids.append(query.fetchone()[0])
                        query.execute('SELECT @@global.gtid_executed');previous=query.fetchone()[0]
                    query.execute('FLUSH BINARY LOGS')
                    with app.test_request_context('/'):
                        user=User.query.first();uid=user.id;group=ServerGroup.query.filter_by(user_id=uid).order_by(ServerGroup.id).first()
                        app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
                        def register(label,route,username='root'):
                            item=Server(user_id=uid,servergroup_id=group.id,name=label,host=route['host'],port=route['port'],username=username,maintenance_db=None,save_password=0)
                            item._cde_endpoint_registration=registration_profile('mysql-native')
                            item._cde_endpoint_route_configuration={**route,'use_pure':not use_c,'user':username,'credential_kinds':['database_password']}
                            db.session.add(item);db.session.commit()
                            return item.id,url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=item.id),url_for('NODE-server.cde_workspace_id',gid=group.id,sid=item.id)
                        source_id,source_verify,source_url=register('Owned replay archive source',source_route)
                        target_id,target_verify,target_url=register('Owned independent replay target',target_route)
                        _other_id,other_verify,other_url=register('Another registration of replay target',target_route)
                    with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
                    for url in (source_verify,target_verify,other_verify):assert client.post(url,json={'password':password}).get_json()['success']
                    def http(url,prefix,action,request,*,refused=False):
                        response=client.post(url,json={'action':prefix+action,'request':request});value=response.get_json()
                        if refused:
                            assert response.status_code==400,value;return value
                        if response.status_code!=200 or not value.get('success'):
                            (output/'http-failure.json').write_text(json.dumps(value,indent=2)+'\n');raise RuntimeError('Native HTTP '+action+' failed')
                        return value['data']
                    def replay(action,request,**kwargs):
                        if action in {'inspect','review','archives','boundaries'}:request={**request,'archive_family':'raw'}
                        return http(target_url,'mysql_binlog_replay_',action,request,**kwargs)
                    def archive(action,request):return http(source_url,'mysql_raw_binlog_',action,request)
                    def wait(value,status,expected):
                        deadline=time.monotonic()+90
                        while value['state'] in {'dispatching','active','cancel_requested'}:
                            if time.monotonic()>deadline:raise TimeoutError('Native HTTP replay deadline')
                            time.sleep(.1);value=status('status',{'job_id':value['job_id']})
                        assert value['state']==expected,value;return value
                    def start_request(value):return {**{key:value[key] for key in ('job_id','review_digest')},'confirmed':True}
                    sealed=archive('review',{'options':{'log_names':[start]}})
                    sealed=wait(archive('start',start_request(sealed)),archive,'completed')
                    shell_archive=None
                    if gtid_mode=='ON':
                        def shell_archive_action(action,request,**kwargs):return http(source_url,'mysql_binlog_',action,request,**kwargs)
                        shell_archive=shell_archive_action('review',{'options':{'start_file':start,'start_position':'4','compression':'zstd','threads':1}})
                        shell_archive=wait(shell_archive_action('start',start_request(shell_archive)),shell_archive_action,'completed')
                    observed=replay('inspect',{});target_uuid=observed['identity']['server_uuid']
                    assert target_uuid!=sealed['source']['server_uuid']
                    groups=replay('boundaries',{'source_server_id':source_id,'archive_job_id':sealed['job_id']})['groups'];assert len(groups)==3
                    selected={'archive_family':'raw','source_server_id':source_id,'archive_job_id':sealed['job_id'],'options':{'target_confirmation':target_uuid,'stop_mode':'before','stop_file':groups[1]['file'],'stop_position':groups[1]['position']}}
                    if gtid_mode=='ON':
                        missing=replay('review',selected,refused=True);assert 'starting GTIDs' in missing['errormsg']
                        target_query.execute('SET GLOBAL gtid_purged=%s',('+'+baseline,))
                    wrong=deepcopy_request(selected);wrong['options']['target_confirmation']=sealed['source']['server_uuid']
                    assert 'confirmed' in replay('review',wrong,refused=True)['errormsg']
                    self_target=deepcopy_request(selected);self_target['options']['target_confirmation']=sealed['source']['server_uuid']
                    assert 'separate' in http(source_url,'mysql_binlog_replay_','review',self_target,refused=True)['errormsg']
                    proof['checks'].append('native-base-gap-exact-target-and-source-self-replay-admission-refused')
                    # Freeze a review, then change native target GTIDs before dispatch.
                    stale=replay('review',selected);target_query.execute('CREATE DATABASE sr_replay_concurrent')
                    refused=wait(replay('start',start_request(stale)),replay,'not_dispatched')
                    assert refused['native_load_outcome']=='not_dispatched'
                    proof['checks'].append('native-target-gtid-change-after-review-prevents-loader-dispatch')
                    reviewed=replay('review',selected)
                    original=native.run_load
                    def lost_reply(*args,**kwargs):
                        result=original(*args,**kwargs);assert result['control']['native_load_returned']
                        error=ConnectionError('Owned injected loss after actual native load return');error.observation=result['tool'];raise error
                    native.run_load=lost_reply
                    try:unknown=wait(replay('start',start_request(reviewed)),replay,'unknown')
                    finally:native.run_load=original
                    jobs=service.mysql_binlog_replay_jobs
                    assert unknown['native_process_termination_confirmed'] is True and unknown['native_load_outcome']=='unknown'
                    target_query.execute('SELECT CAST(id AS CHAR),body,HEX(payload) FROM sr_replay.t ORDER BY id')
                    assert target_query.fetchall()==[('9007199254740993','Unicode 😀 0','00FF00')]
                    assert replay('start',start_request(reviewed))['started_at']==unknown['started_at']
                    peer=http(other_url,'mysql_binlog_replay_','review',selected)
                    assert 'unresolved' in http(other_url,'mysql_binlog_replay_','start',start_request(peer),refused=True)['errormsg']
                    if shell_archive is not None:
                        shell_peer=http(other_url,'mysql_binlog_replay_','review',{'source_server_id':source_id,'archive_job_id':shell_archive['job_id'],'options':{'target_confirmation':target_uuid}})
                        assert 'unresolved' in http(other_url,'mysql_binlog_replay_','start',start_request(shell_peer),refused=True)['errormsg']
                        proof['checks'].append('native-raw-unknown-fence-also-blocks-shell-replay-on-another-registration')
                    assert http(other_url,'mysql_binlog_replay_','status',{'job_id':unknown['job_id']},refused=True)
                    facts=replay('reconcile',{'job_id':unknown['job_id']})
                    assert facts['native_load_outcome']=='unknown' and facts['reconciliation']['native_lock_free'] is True
                    acknowledgement={'job_id':unknown['job_id'],'target_confirmation':target_uuid,'observation_digest':facts['observation_digest']}
                    assert 'exact' in replay('acknowledge',{**acknowledgement,'observation_digest':'stale'},refused=True)['errormsg']
                    acknowledged=replay('acknowledge',acknowledgement);assert acknowledged['target_state_acknowledged_at'] and acknowledged['native_load_outcome']=='unknown'
                    proof['checks'].append('actual-native-partial-replay-lost-ack-preserves-unknown-fences-all-registrations-and-requires-exact-reconciliation')
                    all_selected={**selected,'options':{'target_confirmation':target_uuid,'stop_mode':'all',**({'start_file':groups[1]['file'],'start_position':groups[1]['position']} if gtid_mode=='OFF' else {})}}
                    full=replay('review',all_selected);completed=wait(replay('start',start_request(full)),replay,'native_load_returned')
                    assert completed['result']['native_coverage']['baseline_preserved']==1 and completed['data_recovery_verified'] is False
                    target_query.execute('SELECT CAST(id AS CHAR),body,HEX(payload) FROM sr_replay.t ORDER BY id')
                    assert target_query.fetchall()==[(str(9007199254740993+i),'Unicode 😀 '+str(i),'00FF'+f'{i:02X}') for i in range(3)]
                    proof['checks'].append('fresh-reviewed-native-resume-skips-present-gtids-and-preserves-wide-int-unicode-binary-rows')
                    app.config['CDEADMIN_MYSQL_BINLOG_REPLAY_MAX_RUNTIME_SECONDS']=1
                    assert 'policy' in replay('review',{**all_selected,'options':{**all_selected['options'],'timeout_seconds':None}},refused=True)['errormsg']
                    app.config['CDEADMIN_MYSQL_BINLOG_REPLAY_MAX_RUNTIME_SECONDS']=None
                    proof['checks'].append('application-runtime-ceiling-enforced-without-dispatch')
                    # Prepare another native archive for browser execution while its source is offline.
                    query.execute('FLUSH BINARY LOGS');query.execute('SHOW BINARY LOG STATUS');browser_start=query.fetchone()[0];query.fetchall()
                    query.execute('INSERT INTO sr_replay.t VALUES(%s,%s,%s)',(9007199254740996,'Unicode 😀 3',b'\x00\xff\x03'));query.execute('FLUSH BINARY LOGS')
                    browser_archive=archive('review',{'options':{'log_names':[browser_start]}})
                    browser_archive=wait(archive('start',start_request(browser_archive)),archive,'completed')
                    target_query.execute("CREATE USER 'sr_denied_replay'@'%' IDENTIFIED BY %s",(password,))
                    target_query.execute("GRANT BACKUP_ADMIN ON *.* TO 'sr_denied_replay'@'%'")
                    target_query.execute("GRANT SELECT ON performance_schema.log_status TO 'sr_denied_replay'@'%'")
                    with app.test_request_context('/'):
                        _denied_id,denied_verify,denied_url=register('Restricted replay principal',target_route,'sr_denied_replay')
                    assert client.post(denied_verify,json={'password':password}).get_json()['success']
                    def denied(action,request,**kwargs):return http(denied_url,'mysql_binlog_replay_',action,{**request,**({'archive_family':'raw'} if action in {'inspect','review'} else {})},**kwargs)
                    assert denied('inspect',{})['identity']['authenticated_principal'].startswith('sr_denied_replay@')
                    denied_review=denied('review',{'source_server_id':source_id,'archive_job_id':browser_archive['job_id'],'options':{'target_confirmation':target_uuid}})
                    denied_result=wait(denied('start',start_request(denied_review)),denied,'unknown')
                    assert denied_result['result']['control']['native_load_invoked'] is True and denied_result['result']['tool']['return_code']!=0
                    target_query.execute('SELECT COUNT(*) FROM sr_replay.t');assert target_query.fetchone()[0]==3
                    denied_facts=denied('reconcile',{'job_id':denied_review['job_id']})
                    assert denied_facts['reconciliation']['baseline_preserved']==1
                    denied('acknowledge',{'job_id':denied_review['job_id'],'target_confirmation':target_uuid,'observation_digest':denied_facts['observation_digest']})
                    proof['checks'].append('restricted-principal-inspects-without-show-binlogs-but-native-loader-denies-ungranted-replay-and-no-rows-apply')
                finally:query.close();source_root.close()
            assert owned_source['owned_server_stopped'];proof['owned_source_stopped']=True
            assert replay('archives',{'source_server_id':source_id})['jobs'][0]['job_id']==browser_archive['job_id']
            if browser_binary:
                proof['browser']=browser(app,output,target_id,source_id,browser_archive['job_id'],target_uuid,browser_binary,driver_binary,raw=True)
                target_query.execute('SELECT COUNT(*) FROM sr_replay.t');assert target_query.fetchone()[0]==4
                proof['checks'].append('native-browser-context-menu-confirmed-replay-from-offline-source-with-independent-native-rows')
            else:
                final=replay('review',{'source_server_id':source_id,'archive_job_id':browser_archive['job_id'],'options':{'target_confirmation':target_uuid}})
                wait(replay('start',start_request(final)),replay,'native_load_returned')
                target_query.execute('SELECT COUNT(*) FROM sr_replay.t');assert target_query.fetchone()[0]==4
                proof['checks'].append('native-replay-from-offline-source-sealed-archive')
        assert owned_target['owned_server_stopped'];proof['owned_target_stopped']=True
        assert replay('list',{})['jobs'] and replay('status',{'job_id':unknown['job_id']})['native_load_outcome']=='unknown'
        proof['checks'].append('durable-receipts-remain-readable-with-both-native-servers-offline')
        proof.update(complete=True,interface='c' if use_c else 'pure',gtid_mode=gtid_mode)
    finally:
        ProviderToolRunner.run=original_run;proof['private_native_failure_logs']=native_failures
        if jobs is not None:jobs.close()
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof



from cdeadmin_mysql_binlog_replay_workspace_qualification import browser,deepcopy_request

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--mysql-shell',type=Path,required=True);parser.add_argument('--mysql-binlog',type=Path,required=True);parser.add_argument('--mysql-client',type=Path,required=True)
    parser.add_argument('--browser-binary');parser.add_argument('--driver-binary');parser.add_argument('--use-c',action='store_true');parser.add_argument('--gtid-mode',choices=('ON','OFF'),default='OFF');args=parser.parse_args()
    qualify(args.evidence,args.mysql_shell,args.mysql_binlog,args.mysql_client,browser_binary=args.browser_binary,driver_binary=args.driver_binary,use_c=args.use_c,gtid_mode=args.gtid_mode)

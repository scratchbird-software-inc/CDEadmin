"""Native Shell replay over the original managed physical recovery route."""
import json
from pathlib import Path
import threading
from unittest.mock import patch


def reconnect_probe(client,route,credentials,directory,target):
    from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_archives import CREDENTIAL_FILE,connection_options
    from pgadmin.cdeadmin.providers.mysql_family.mysql_recovery_bridge import UTILITY_KEY
    from pgadmin.cdeadmin.sdk.tooling import ProviderToolGrant
    from pgadmin.cdeadmin.operations.fileio import private_file
    path=Path(directory)/'owned-reconnect.js'
    source=('const target='+json.dumps(connection_options(client,route))+';\n'
        'Object.assign(target,JSON.parse(os.loadTextFile(os.getenv('+json.dumps(CREDENTIAL_FILE)+'))));\n'
        'shell.connect(target);const before=shell.getSession().runSql("SELECT @@server_uuid").fetchOne()[0];\n'
        'if(!shell.reconnect())throw new Error("Native reconnect refused");\n'
        'const after=shell.getSession().runSql("SELECT @@server_uuid").fetchOne()[0];\n'
        'if(before!=='+json.dumps(target['server_uuid'])+' || after!==before)throw new Error("Original native peer changed");\n'
        'print("CDEADMIN_NATIVE_RECONNECT:"+after);shell.getSession().close();\n')
    with path.open('x',encoding='utf8') as stream:private_file(path);stream.write(source)
    grant=ProviderToolGrant('mysql-shell',str(directory),route['host'],route['port'],timeout_seconds=30,
        durable_name='shell-reconnect-probe',secret_environment_names=(CREDENTIAL_FILE,))
    result=credentials.use(lambda view:client._tool_runner.run(grant,['--no-defaults','--js','--log-level=none','--file='+str(path)],
        secret_config=bytes(view),secret_argument=None,secret_environment_name=CREDENTIAL_FILE,secret_suffix='.json',
        reservation_socket=route[UTILITY_KEY].bridge.listener))
    assert result['return_code']==0 and result['process_observation']['cleanup_confirmed'],result
    assert result['process_observation']['endpoint_reservation_inherited']
    assert 'CDEADMIN_NATIVE_RECONNECT:'+target['server_uuid'] in result['stdout']


def shell_replay(app,client,sid,root,archive,replay,physical,target,url,output,browser_binary=None,driver_binary=None):
    from cdeadmin_mysql_physical_replay_qualification import wait_job,start_request,cancel_independent_replay
    from cdeadmin_mysql_recovery_connection_qualification import query_post,execute
    from pgadmin.cdeadmin.providers.mysql_family import mysql_binlog_replay as native,mysql_recovery_bridge as bridge
    cursor=root.cursor();checks=[];uuid=target['binding']['server_uuid']
    original_bridge=bridge.bridges.get(target['binding']);opened=[];open_stream=original_bridge.transport.open_stream
    def traced(request):
        channel=open_stream(request);opened.append(True);return channel
    try:
        cursor.execute('FLUSH BINARY LOGS');cursor.execute('SHOW BINARY LOG STATUS');filename=cursor.fetchone()[0];cursor.fetchall()
        cursor.execute('SELECT @@global.gtid_executed');previous=cursor.fetchone()[0];gtids=[]
        for index in range(11,14):
            cursor.execute('INSERT INTO sr_osc.t VALUES(%s,%s,%s)',(index,'physical Shell 雪 '+str(index),b'\x00\xff'+bytes([index])))
            cursor.execute('SELECT GTID_SUBTRACT(@@global.gtid_executed,%s)',(previous,));gtids.append(cursor.fetchone()[0])
            cursor.execute('SELECT @@global.gtid_executed');previous=cursor.fetchone()[0]
        cursor.execute('FLUSH BINARY LOGS')
        sealed=archive('review',{'options':{'start_file':filename,'start_position':'4','compression':'zstd','threads':1}})
        sealed=wait_job(archive('start',start_request(sealed)),archive,'completed')
        selected={'source_server_id':sid,'archive_job_id':sealed['job_id'],
            'options':{'target_confirmation':uuid,'stop_mode':'before','stop_gtid':gtids[1]}}
        ticket=replay('review',selected);original=native.run_load;entered=threading.Event();release=threading.Event()
        def lost_reply(*args,**kwargs):
            entered.set();assert release.wait(30)
            with patch.object(original_bridge.transport,'open_stream',side_effect=traced):
                before=len(opened);result=original(*args,**kwargs)
                assert result['control']['native_load_returned'] and len(opened)-before>=2,result
                assert result['tool']['process_observation']['endpoint_reservation_inherited']
                before=len(opened);reconnect_probe(args[0],args[1],args[2],args[7],args[4])
                assert len(opened)-before>=2
            raise ConnectionError('Owned original Shell reply loss after real native replay')
        with patch.object(native,'run_load',lost_reply):
            try:
                value=replay('start',start_request(ticket));assert entered.wait(30)
                physical('connection_detach',{'server_id':target['server_id']},refused=True)
            finally:release.set()
            unknown=wait_job(value,replay,'unknown')
        assert unknown['native_load_outcome']=='unknown' and unknown.get('native_process_termination_confirmed') is not True
        assert set(unknown['durable_tools'])=={'shell-replay-client'}
        import time
        limit=time.monotonic()+30
        while app.extensions['cdeadmin_provider_workspace'].mysql_binlog_replay_jobs.workers.get(ticket['job_id']):
            if time.monotonic()>limit:raise TimeoutError('Original Shell observer remained active')
            time.sleep(.02)
        physical('connection_detach',{'server_id':target['server_id']},refused=True)
        assert replay('start',start_request(ticket))['started_at']==unknown['started_at']
        facts=replay('reconcile',{'job_id':ticket['job_id']})
        assert facts['native_load_outcome']=='unknown' and facts['native_process_termination_confirmed'] and facts['reconciliation']['native_lock_free']
        tool=facts['interrupted_utility_observation']['tools']['shell-replay-client']
        assert tool['credential_file_cleanup_confirmed'] and tool['endpoint_reservation_inherited'] and facts['staged_input_cleanup']['complete']
        replay('acknowledge',{'job_id':ticket['job_id'],'target_confirmation':uuid,'observation_digest':facts['observation_digest']})
        post=lambda action,**body:query_post(client,url,target['database_target_id'],action,**body)
        for mode,count in [('before',1),('after',2),('all',3)]:
            if mode!='before':
                selected['options']={'target_confirmation':uuid,'stop_mode':mode,**({'stop_gtid':gtids[1]} if mode=='after' else {})}
                item=replay('review',selected);wait_job(replay('start',start_request(item)),replay,'native_load_returned')
            session=post('open_session',language_profile='mysql-sql')['session_id']
            try:
                rows=execute(post,session,'SELECT CAST(id AS CHAR),note,HEX(b) FROM t WHERE id BETWEEN 11 AND 13 ORDER BY id')['rows']
                assert rows==[[str(i),'physical Shell 雪 '+str(i),'00FF'+format(i,'02X')] for i in range(11,11+count)]
            finally:post('close_session',session_id=session)
        cancelled=cancel_independent_replay(app,client,sid,root,archive,replay,physical,target,url,output,browser_binary,driver_binary,family='shell')
        checks.extend(cancelled['checks'])
        # A new review, after explicit acknowledgement, completes any remaining
        # transaction; cancellation itself never proves rollback or completion.
        selected={'source_server_id':sid,'archive_job_id':cancelled['archive_job_id'],'options':{'target_confirmation':uuid}}
        item=replay('review',selected);wait_job(replay('start',start_request(item)),replay,'native_load_returned')
        checks.extend(['native-Shell-additional-replay-connection-and-explicit-reconnect-use-original-process-bound-route',
            'native-Shell-physical-base-before-after-all-exact-Unicode-BLOB-and-lost-reply-fence-reconciliation',
            'native-Shell-retains-original-listener-descriptor-after-observer-loss'])
        return checks
    finally:cursor.close()

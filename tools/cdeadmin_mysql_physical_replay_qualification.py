"""Native raw-log replay into a reviewed physical recovery instance."""
import argparse
import json
import os
from pathlib import Path
import threading
import time
from unittest.mock import patch


def wait_job(value,post,expected):
    deadline=time.monotonic()+120
    while value['state'] in {'dispatching','active','cancel_requested'}:
        if time.monotonic()>deadline:raise TimeoutError('Native physical raw replay deadline')
        time.sleep(.05);value=post('status',{'job_id':value['job_id']})
    assert value['state']==expected,value
    return value


def start_request(value):return {key:value[key] for key in ('job_id','review_digest')}|{'confirmed':True}


def native_replay(app,client,sid,root,physical,credentials,review,start,copied,output,use_c):
    from cdeadmin_mysql_recovery_connection_qualification import endpoint,query_post,execute
    from pgadmin.cdeadmin.providers.mysql_family import mysql_raw_binlog_replay as raw
    source_url=endpoint(app,sid)
    def http(url,prefix,action,request,refused=False):
        response=client.post(url,json={'action':prefix+action,'request':request});value=response.get_json()
        if refused:assert not value.get('success'),value;return value
        assert response.status_code==200 and value.get('success'),value
        return value['data']
    archive=lambda action,request:http(source_url,'mysql_raw_binlog_',action,request)
    runtime=target=None;cursor=root.cursor();checks=[]
    try:
        runtime=start(review('recover',copied['job_id'],lifetime=600,startup='replay'))
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            runtime=physical('reconcile',{'job_id':runtime['job_id'],'credentials':credentials})
            if runtime['recovery_running']:break
            if runtime.get('remote_observation',{}).get('supervisor_finished'):raise AssertionError(runtime)
            time.sleep(.1)
        else:raise TimeoutError('Writable physical recovery startup')
        identity=runtime['remote_observation']['sql_identity']
        assert identity['log_bin']==1 and identity['super_read_only']==0 and identity['read_only']==0
        assert identity['server_id']==10001+int(use_c) and identity['binlog_format']=='ROW' and identity['log_replica_updates']==1
        ticket=physical('connection_review',{'job_id':runtime['job_id'],'name':'Physical raw replay '+str(use_c),'credentials':credentials})
        attached=physical('connection_connect',{'review_id':ticket['job_id'],'review_digest':ticket['review_digest'],'confirmed':True,
            'delegate_database_credentials':True,'credentials':credentials})
        target=attached['result'];url=endpoint(app,target['server_id'])
        def replay(action,request,refused=False):
            if action in {'inspect','review','archives','boundaries'}:request={**request,'archive_family':'raw'}
            return http(url,'mysql_binlog_replay_',action,request,refused)
        assert replay('inspect',{})['identity']['server_uuid']==identity['server_uuid']
        cursor.execute('FLUSH BINARY LOGS');cursor.execute('SHOW BINARY LOG STATUS');filename=cursor.fetchone()[0];cursor.fetchall()
        for index in range(1,4):
            cursor.execute('INSERT INTO sr_osc.t VALUES(%s,%s,%s)',(index,'physical raw 雪 '+str(index),b'\x00\xff'+bytes([index])))
        cursor.execute('FLUSH BINARY LOGS')
        sealed=archive('review',{'options':{'log_names':[filename]}})
        sealed=wait_job(archive('start',start_request(sealed)),archive,'completed')
        groups=replay('boundaries',{'source_server_id':sid,'archive_job_id':sealed['job_id']})['groups'];assert len(groups)==3
        selected={'source_server_id':sid,'archive_job_id':sealed['job_id'],'options':{'target_confirmation':identity['server_uuid'],
            'stop_mode':'before','stop_file':groups[1]['file'],'stop_position':groups[1]['position']}}
        ticket=replay('review',selected)
        reached=threading.Event();release=threading.Event();original=raw.run_load
        def lost_reply(*args,**kwargs):
            reached.set();assert release.wait(30)
            result=original(*args,**kwargs);assert result['control']['native_load_returned']
            error=ConnectionError('Owned reply loss after actual native raw replay');error.observation=result['tool'];raise error
        with patch.object(raw,'run_load',lost_reply):
            try:
                value=replay('start',start_request(ticket));assert reached.wait(30)
                physical('connection_detach',{'server_id':target['server_id']},refused=True)
            finally:release.set()
            unknown=wait_job(value,replay,'unknown')
        assert unknown['native_process_termination_confirmed'] and unknown['native_load_outcome']=='unknown'
        assert replay('start',start_request(ticket))['started_at']==unknown['started_at']
        facts=replay('reconcile',{'job_id':ticket['job_id']});assert facts['reconciliation']['native_lock_free']
        replay('acknowledge',{'job_id':ticket['job_id'],'target_confirmation':identity['server_uuid'],'observation_digest':facts['observation_digest']})
        post=lambda action,**body:query_post(client,url,target['database_target_id'],action,**body)
        session=post('open_session',language_profile='mysql-sql')['session_id']
        try:
            assert execute(post,session,'SELECT CAST(id AS CHAR),note,HEX(b) FROM t WHERE id<10 ORDER BY id')['rows']==[['1','physical raw 雪 1','00FF01']]
        finally:post('close_session',session_id=session)
        for mode,count in [('after',2),('all',3)]:
            selected['options']={'target_confirmation':identity['server_uuid'],'stop_mode':mode,
                **({'stop_file':groups[1]['file'],'stop_position':groups[1]['position']} if mode=='after' else {})}
            ticket=replay('review',selected)
            value=wait_job(replay('start',start_request(ticket)),replay,'native_load_returned')
            assert value['result']['native_coverage']['baseline_preserved']==1
            session=post('open_session',language_profile='mysql-sql')['session_id']
            try:
                rows=execute(post,session,'SELECT CAST(id AS CHAR),note,HEX(b) FROM t WHERE id<10 ORDER BY id')['rows']
                assert rows==[[str(i),'physical raw 雪 '+str(i),'00FF0'+str(i)] for i in range(1,count+1)]
            finally:post('close_session',session_id=session)
        physical('connection_detach',{'server_id':target['server_id']})
        checks.extend(['physical-base-writable-startup-native-GTID-ROW-binlogs-and-separate-leased-raw-replay-registration',
            'native-mysqlbinlog-mysql-before-after-all-replay-exact-selected-Unicode-BLOB-data',
            'active-native-raw-utility-refuses-detach-and-original-lost-reply-remains-unknown-after-independent-observation'])
        return checks
    finally:
        if runtime:
            physical('cancel',{'job_id':runtime['job_id'],'credentials':credentials})
            deadline=time.monotonic()+60
            while time.monotonic()<deadline:
                value=physical('reconcile',{'job_id':runtime['job_id'],'credentials':credentials})
                if value.get('remote_observation',{}).get('supervisor_finished'):break
                time.sleep(.1)
            else:raise TimeoutError('Writable physical recovery did not stop')
        cursor.execute('DELETE FROM sr_osc.t WHERE id<10');cursor.close()


def browser_replay(app,output,sid,password,target,root,binary,driver_binary):
    from pgadmin.model import db,Server
    from cdeadmin_mysql_online_ddl_qualification import registration
    from cdeadmin_mysql_recovery_connection_qualification import endpoint,query_post,execute
    from cdeadmin_mysql_binlog_replay_workspace_qualification import browser
    with app.test_request_context('/'):
        source=Server.query.get(sid);route={'host':source.host,'port':source.port};username=source.username;owner=source.user_id
    alias,_selected,_post=registration(app,route,password,True,username=username)
    with app.test_request_context('/'):
        source=Server.query.get(alias);source.name='Owned replay archive source';db.session.commit()
    client=app.test_client()
    with client.session_transaction() as session:session['_user_id'],session['_fresh']=str(owner),True
    source_url=endpoint(app,alias);url=endpoint(app,target['server_id'])
    def archive(action,request):
        response=client.post(source_url,json={'action':'mysql_raw_binlog_'+action,'request':request});value=response.get_json()
        assert response.status_code==200 and value.get('success'),value
        return value['data']
    cursor=root.cursor()
    try:
        cursor.execute('FLUSH BINARY LOGS');cursor.execute('SHOW BINARY LOG STATUS');filename=cursor.fetchone()[0];cursor.fetchall()
        cursor.execute('INSERT INTO sr_osc.t VALUES(1001001,%s,%s)',('desktop raw replay 雪',b'\x00\xff\x7f'))
        cursor.execute('FLUSH BINARY LOGS')
        sealed=archive('review',{'options':{'log_names':[filename]}})
        sealed=wait_job(archive('start',start_request(sealed)),archive,'completed')
        evidence=output/'raw-replay-desktop';evidence.mkdir(mode=0o700)
        value=browser(app,evidence,target['server_id'],alias,sealed['job_id'],target['binding']['server_uuid'],binary,driver_binary,raw=True)
        value['source_offline']=False
        (evidence/'summary.json').write_text(json.dumps(value,indent=2)+'\n')
        post=lambda action,**body:query_post(client,url,target['database_target_id'],action,**body)
        session=post('open_session',language_profile='mysql-sql')['session_id']
        try:
            assert execute(post,session,'SELECT CAST(id AS CHAR),note,HEX(b) FROM t WHERE id=1001001')['rows']==[['1001001','desktop raw replay 雪','00FF7F']]
        finally:post('close_session',session_id=session)
        return ['built-recovery-target-menu-reviewed-native-raw-replay-and-independent-exact-data']
    finally:
        cursor.execute('DELETE FROM sr_osc.t WHERE id=1001001');cursor.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--fixture-image',default='sr-mysql-physical:phase210')
    parser.add_argument('--private-key');parser.add_argument('--prepare-fixture',action='store_true');parser.add_argument('--decoder',required=True);parser.add_argument('--client',required=True)
    parser.add_argument('--browser-binary');parser.add_argument('--driver-binary');args=parser.parse_args()
    os.environ['CDEADMIN_MYSQL_BINLOG_BINARY']=str(Path(args.decoder).resolve(strict=True));os.environ['CDEADMIN_MYSQL_CLIENT_BINARY']=str(Path(args.client).resolve(strict=True))
    from cdeadmin_mysql_physical_qualification import qualify
    qualify(args.output,args.fixture_image,args.private_key,args.prepare_fixture,args.browser_binary,args.driver_binary,connections=True,replay=True)

"""Native in-place upgrade against an explicitly prepared disposable SSH host."""
import argparse
import json
import secrets
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output,fixture,use_c=False,browser_binary=None,driver_binary=None,interrupt=False):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    import mysql.connector
    from flask import url_for
    from pgadmin.model import db,User,ServerGroup,Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    output=Path(output).resolve();output.mkdir(exist_ok=False)
    owned=json.loads(Path(fixture).read_text())
    if not owned.get('complete') or not owned['container'].startswith('sr-upgrade245-'):
        raise ValueError('Select the explicitly owned native upgrade fixture')
    app=setup_application(output);client=app.test_client()
    proof={'complete':False,'use_c':use_c,'checks':[],'history_testing':'not run'}
    def connect():return mysql.connector.connect(host='127.0.0.1',port=owned['sql_port'],user='sr_upgrade',
        password='owned-upgrade-private',use_pure=not use_c,autocommit=True,connection_timeout=3,read_timeout=5)
    def sql(source,parameters=()):
        connection=connect();cursor=connection.cursor(dictionary=True)
        try:
            cursor.execute(source,parameters)
            return cursor.fetchall() if cursor.with_rows else []
        finally:cursor.close();connection.close()
    before=sql('SELECT @@server_uuid AS uuid,VERSION() AS version')[0]
    assert before['version'].split('-')[0]=='8.4.8'
    schema='sr_native_upgrade_'+secrets.token_hex(5)
    sql('CREATE DATABASE '+schema+' CHARACTER SET utf8mb4')
    sql('CREATE TABLE '+schema+'.t(id BIGINT PRIMARY KEY,body TEXT,payload LONGBLOB)')
    sql('INSERT INTO '+schema+'.t VALUES(%s,%s,%s)',(9007199254740993,'native upgrade 雪',b'\x00\xff'))
    with app.test_request_context('/'):
        uid=User.query.first().id;group=ServerGroup.query.filter_by(user_id=uid).first()
        app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
        item=Server(user_id=uid,servergroup_id=group.id,name='Owned native upgrade',host='127.0.0.1',port=owned['sql_port'],username='sr_upgrade',maintenance_db=None,save_password=0)
        item._cde_endpoint_registration=registration_profile('mysql-native')
        item._cde_endpoint_route_configuration={'host':'127.0.0.1','port':owned['sql_port'],'user':'sr_upgrade',
            'use_pure':not use_c,'credential_kinds':['database_password']}
        db.session.add(item);db.session.commit()
        verify=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=item.id)
        url=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=item.id)
    with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
    def post(action,request,refused=False):
        response=client.post(url,json={'action':'mysql_host_'+action,'request':request});value=response.get_json()
        if refused:
            assert response.status_code==400,value
            return value
        if response.status_code!=200 or not value.get('success'):
            (output/'http-failure.json').write_text(json.dumps(value,indent=2)+'\n')
            raise AssertionError('Native upgrade application action failed: '+action)
        return value['data']
    credentials={'private_key':Path(owned['private_key']).read_text()}
    selected={'connection':{'host':'127.0.0.1','port':owned['ssh_port'],'username':'root','host_key':owned['host_key'],
        'authentication':'private_key','platform':'posix','python':'python3'},'executable':owned['legacy'],
        'configuration_file':owned['configuration'],'workspace':'/tmp/sr-native-upgrade-jobs','timeout_seconds':120,
        'operation':'upgrade_service','service':{'manager':'systemd','name':owned['service']},
        'binding_job_id':None,'disconnect_all_clients':True,'upgrade':{'executable':owned['candidate'],
            'configuration_file':owned['configuration'],'basedir':'/opt/mysql97/usr','user':'mysql',
            'source_datadir':'/opt/sr-upgrade245/data','source_pid_file':'/opt/sr-upgrade245/data/mysql.pid',
            'shell_executable':'/opt/scratchrobin-native/mysql/bin/mysqlsh',
            'check_connection':{'scheme':'mysql','host':'127.0.0.1','port':3306,'user':'sr_upgrade','ssl-mode':'REQUIRED'}}}
    check_secret={'password':'owned-upgrade-private'}
    try:
        if interrupt:
            from mysql_upgrade_interruption_qualification import qualify as interruption
            proof['checks'].extend(interruption(post,selected,credentials,check_secret,owned,output,sql))
        review=post('review',{'options':selected,'credentials':credentials,'upgrade_check_secret':check_secret})
        assert check_secret['password'] not in json.dumps(review)
        assert review['remote_observation']['upgrade_plan']['preflight']['report']['errorCount']==0
        proof['checks'].append('authenticated-original-native-8.4-source-and-independent-SSH-service-candidate-9.7-binding')
        request={**{key:review[key] for key in ('job_id','review_digest')},'confirmed':True,'credentials':credentials,'upgrade_check_secret':check_secret}
        if browser_binary:
            post('cancel',{'job_id':review['job_id']})
            from mysql_upgrade_ui_qualification import qualify as desktop
            result=desktop(app,output,item.id,selected,Path(owned['private_key']),browser_binary,driver_binary)
            proof['browser']={key:value for key,value in result.items() if key not in {'original','acknowledged'}}
            value=result['original'];review={key:value[key] for key in ('job_id','review_digest')}
            request={**review,'confirmed':True,'credentials':credentials,'upgrade_check_secret':check_secret}
        else:
            value=post('start',request);deadline=time.monotonic()+150
            while value['state'] in {'dispatching','active','cancel_requested'}:
                if time.monotonic()>deadline:raise TimeoutError('Native service upgrade application deadline')
                time.sleep(.1);value=post('status',{'job_id':value['job_id']})
        (output/'original-upgrade.json').write_text(json.dumps(value,indent=2)+'\n')
        assert value['state']=='native_process_returned',value.get('error_message') or value.get('error_type')
        remote=value['remote_receipt'];assert remote['result']['return_code']==0
        assert remote['upgrade_result']['dispatcher_steps_ended']
        deadline=time.monotonic()+60
        while True:
            try:
                after=sql('SELECT @@server_uuid AS uuid,VERSION() AS version')[0]
                if after=={'uuid':before['uuid'],'version':'9.7.0'}:break
            except mysql.connector.Error:
                if time.monotonic()>deadline:raise
            if time.monotonic()>deadline:raise TimeoutError('Independent native upgraded SQL readiness deadline')
            time.sleep(.2)
        assert sql('SELECT CAST(id AS CHAR) AS id,body,HEX(payload) AS payload FROM '+schema+'.t')==[
            {'id':'9007199254740993','body':'native upgrade 雪','payload':'00FF'}]
        verification=client.post(verify,json={'password':'owned-upgrade-private'}).get_json()
        (output/'endpoint-verification.json').write_text(json.dumps(verification,indent=2)+'\n')
        assert verification['success'],verification
        proof['checks'].append('actual-native-data-dictionary-service-upgrade-preserves-original-UUID-exact-bigint-Unicode-and-binary-data')
        observed=post('reconcile',{'job_id':review['job_id'],'credentials':credentials})
        later=observed['reconciliation']['remote_receipt']['upgrade_reconciliation'];assert later['observed'] and later['original_native_process_termination_confirmed']
        assert later['native_upgrade_history']['upgrade_history'][-1]['version']=='9.7.0'
        acknowledged=post('acknowledge_upgrade',{'job_id':review['job_id'],'credentials':credentials})
        assert acknowledged['reconciliation']['remote_receipt']['upgrade_reconciliation']['data_directory_claim_released']
        assert post('start',request)['remote_receipt']==value['remote_receipt']
        proof['checks'].append('separate-original-manager-result-current-native-process-and-native-upgrade-history-observations-explicit-claim-release-and-no-replay')
        proof.update(complete=True,job_id=review['job_id'],server_id=item.id)
    finally:
        from pgadmin.cdeadmin.workspace import service_for_app
        jobs=getattr(service_for_app(app),'mysql_host_jobs',None)
        proof['owned_jobs_stopped']=jobs.close() if jobs is not None else True
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--fixture',required=True);parser.add_argument('--use-c',action='store_true');parser.add_argument('--browser-binary');parser.add_argument('--driver-binary');parser.add_argument('--interrupt',action='store_true');args=parser.parse_args()
    result=qualify(args.output,args.fixture,args.use_c,args.browser_binary,args.driver_binary,args.interrupt);print(json.dumps({'complete':result['complete'],'checks':len(result['checks'])}))

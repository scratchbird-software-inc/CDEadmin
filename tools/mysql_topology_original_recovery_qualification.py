"""Actual native topology guardian loss and surviving server-work clearance."""
import json
from pathlib import Path
import secrets
import time


def qualify(app,client,service,post,server_id,owned,output,use_c):
    import mysql.connector,psutil
    from flask import url_for
    from pgadmin.model import db,Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.providers.mysql_family import mysql_topology_quiescence as native
    output=Path(output);proof={'complete':False,'checks':[],'history_testing':'not run'};oracles=[];locked=[];job=None
    with app.test_request_context('/'):
        seed=db.session.get(Server,server_id);uid=seed.user_id;group=seed.servergroup_id;endpoint=seed.endpoint_profile.id;ids=[];verify=[]
        for peer in owned['peers'][1:]:
            server=Server(user_id=uid,servergroup_id=group,name='Owned topology original '+peer['server_uuid'],host=peer['host'],port=3306,username='root',maintenance_db=None,save_password=0)
            server._cde_endpoint_registration=registration_profile('mysql-native');server._cde_endpoint_route_configuration={'host':peer['host'],'port':3306,'user':'root','use_pure':not use_c,'credential_kinds':['database_password']}
            db.session.add(server);db.session.commit();ids.append(server.id);verify.append(url_for('NODE-server.verify_endpoint_id',gid=group,sid=server.id))
    for url in verify:assert client.post(url,json={'password':'true'}).get_json()['success']
    lock_name='sr-topology-original-'+secrets.token_hex(10)
    def sql(connection,source,parameters=()):
        cursor=connection.cursor(dictionary=True)
        try:cursor.execute(source,parameters);return cursor.fetchall()
        finally:cursor.close()
    def topology(action,request,refused=False):return post(action,request,refused=refused,prefix='mysql_topology_')
    try:
        for peer in owned['peers']:
            connection=mysql.connector.connect(host=peer['host'],port=3306,user='root',password='true',use_pure=not use_c,autocommit=True)
            assert sql(connection,'SELECT @@server_uuid AS uuid')==[{'uuid':peer['server_uuid']}]
            oracles.append(connection);assert sql(connection,'SELECT GET_LOCK(%s,0) AS acquired',(lock_name,))==[{'acquired':1}];locked.append(connection)
        selected={'operation':'cluster.execute','arguments_json':json.dumps(["SELECT GET_LOCK('"+lock_name+"',30)",'all']),
            'context_name':'','context_options_json':'{}','use_advertised_endpoint':True,'witness_server_ids':ids,
            'target_confirmation':owned['peers'][0]['server_uuid'],'timeout_seconds':120}
        reviewed=topology('review',{'options':selected});job=reviewed['job_id'];request={'job_id':job,'review_digest':reviewed['review_digest'],'confirmed':True}
        active=topology('start',request);jobs=service.mysql_topology_jobs;record=jobs.load(job,uid,endpoint);directory=jobs.directory(record)
        deadline=time.monotonic()+30;witness=None
        while time.monotonic()<deadline:
            path=directory/native.OWNER_FILE;progress=directory/'.cdeadmin-tool-mysql-topology/progress.json'
            if path.exists() and progress.exists():
                witness=json.loads(path.read_text());current=json.loads(progress.read_text())['observation']
                if current.get('pid')==witness['pid']:
                    waiting=[sql(connection,"SELECT t.PROCESSLIST_ID AS id FROM performance_schema.threads t JOIN performance_schema.session_connect_attrs a ON a.PROCESSLIST_ID=t.PROCESSLIST_ID WHERE a.ATTR_NAME='_pid' AND a.ATTR_VALUE=%s AND t.PROCESSLIST_INFO LIKE 'SELECT GET_LOCK%%'",(str(witness['pid']),)) for connection in oracles]
                    if all(waiting):break
            time.sleep(.05)
        else:raise TimeoutError('Owned native topology fanout was not positively observed on every member')
        root=directory/'.cdeadmin-tool-mysql-topology';started=json.loads((root/'started.json').read_text());intent=json.loads((root/'request.json').read_text())
        assert intent['kernel_policy']=='linux-parent-death-kill-v1'
        native_process=psutil.Process(witness['pid']);assert native_process.create_time()==current['process_create_time'] and native_process.ppid()==started['guardian_pid']
        psutil.Process(started['guardian_pid']).kill()
        deadline=time.monotonic()+15
        while active['state'] in {'active','dispatching','cancel_requested'}:
            if time.monotonic()>deadline:raise TimeoutError('Original native topology observer did not return unknown')
            time.sleep(.05);active=topology('status',{'job_id':job})
        assert active['native_operation_outcome']=='unknown' and not active.get('native_process_termination_confirmed')
        observed=topology('reconcile',{'job_id':job});(output/'original-before-server-completion.json').write_text(json.dumps(observed,indent=2)+'\n')
        assert observed['native_process_termination_confirmed'] is True
        clearance=observed['reconciliation']['server_recovery_quiescence']
        assert clearance['qualified'] is True and clearance['idle'] is False,clearance
        topology('acknowledge',{'job_id':job,'target_confirmation':owned['peers'][0]['server_uuid'],'observation_digest':observed['observation_digest']},refused=True)
        proof['checks'].append('actual-native-topology-guardian-loss-client-termination-and-private-cleanup-do-not-clear-positive-surviving-server-fanout')
        for connection in locked:sql(connection,'SELECT RELEASE_LOCK(%s)',(lock_name,))
        locked.clear();deadline=time.monotonic()+15
        while True:
            ended=topology('reconcile',{'job_id':job});clearance=ended['reconciliation']['server_recovery_quiescence']
            if clearance.get('qualified') is True and clearance.get('idle') is True:break
            if time.monotonic()>deadline:raise TimeoutError('Original owned native server work did not become independently idle')
            time.sleep(.1)
        acknowledged=topology('acknowledge',{'job_id':job,'target_confirmation':owned['peers'][0]['server_uuid'],'observation_digest':ended['observation_digest']})
        assert acknowledged['native_operation_outcome']=='unknown' and acknowledged.get('target_state_acknowledged_at')
        assert topology('start',request)['native_operation_outcome']=='unknown'
        (output/'original-after-server-completion.json').write_text(json.dumps(acknowledged,indent=2)+'\n')
        proof['checks'].append('independent-original-member-session-absence-clone-idleness-explicit-target-acknowledgement-and-no-replay-preserve-unknown')
        proof.update(complete=True,job_id=job,native_pid=witness['pid'],original_guardian=started['guardian_pid'])
    finally:
        for connection in locked:
            try:sql(connection,'SELECT RELEASE_LOCK(%s)',(lock_name,))
            except mysql.connector.Error:pass
        for connection in oracles:connection.close()
        (output/'topology-original-summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof

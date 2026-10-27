"""Native certificate accounts and owned primary execution from secondary seeds."""
import argparse
import json
from pathlib import Path
import secrets
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output,fixture,certificates,use_c=False):
    import mysql.connector
    from flask import url_for
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    from pgadmin.model import db,User,ServerGroup,Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.workspace import service_for_app
    output=Path(output).resolve();output.mkdir(exist_ok=False)
    owned=json.loads(Path(fixture).read_text());assert owned['complete'] and owned['network'].startswith('sr-upgrade246-')
    peers=owned['peers'];cert=json.loads(Path(certificates).read_text())
    app=setup_application(output);client=app.test_client()
    proof={'complete':False,'use_c':use_c,'checks':[],'operations':[],'history_testing':'ScratchBird history not run'}
    def connect(peer=0,**changes):
        return mysql.connector.connect(host=peers[peer]['address'],port=3306,user='sr_upgrade',
            password='owned-upgrade-private',use_pure=not use_c,autocommit=True,connection_timeout=5,read_timeout=10,**changes)
    def sql(peer,source,parameters=()):
        connection=connect(peer);cursor=connection.cursor(dictionary=True)
        try:
            cursor.execute(source,parameters)
            return cursor.fetchall() if cursor.with_rows else []
        finally:cursor.close();connection.close()
    def until(read,expected=True):
        deadline=time.monotonic()+90
        while True:
            value=read()
            if value==expected:return value
            if time.monotonic()>deadline:raise TimeoutError('Owned native security fixture observation: '+repr(value))
            time.sleep(.2)
    identities=[sql(i,'SELECT @@server_uuid AS uuid,VERSION() AS version')[0] for i in range(3)]
    assert all(v['version']=='9.7.0' for v in identities)
    registrations=[]
    with app.test_request_context('/'):
        uid=User.query.first().id;group=ServerGroup.query.filter_by(user_id=uid).first()
        app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
        for i,peer in enumerate(peers):
            item=Server(user_id=uid,servergroup_id=group.id,name='Owned security member '+str(i),host=peer['address'],port=3306,username='sr_upgrade',maintenance_db=None,save_password=0)
            item._cde_endpoint_registration=registration_profile('mysql-native')
            item._cde_endpoint_route_configuration={'host':peer['address'],'port':3306,'user':'sr_upgrade','use_pure':not use_c,'credential_kinds':['database_password']}
            db.session.add(item);db.session.commit()
            registrations.append({'server_id':item.id,'verify':url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=item.id),
                'url':url_for('NODE-server.cde_workspace_id',gid=group.id,sid=item.id)})
    with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
    for item in registrations:assert client.post(item['verify'],json={'password':'owned-upgrade-private'}).get_json()['success']
    def post(action,request,origin=0,execution=None,refused=False):
        body={**request,**({'execution_server_id':registrations[execution]['server_id']} if execution is not None else {})}
        response=client.post(registrations[origin]['url'],json={'action':'mysql_topology_'+action,'request':body});value=response.get_json()
        if refused:assert response.status_code==400,value;return value
        if response.status_code!=200 or not value.get('success'):
            (output/'http-failure.json').write_text(json.dumps(value,indent=2)+'\n');raise AssertionError('Native security request failed: '+action)
        return value['data']
    def execute(operation,arguments=(),peer=0,origin=None,password=None):
        origin=peer if origin is None else origin
        witnesses=[]
        if operation in {'cluster.add_instance','replica_set.add_instance'}:
            current=post('inspect',{},origin=peer)
            allowed={current['identity']['server_uuid'],*current['metadata']['instance_uuids']}
            allowed.update(identities[i]['uuid'] for i,item in enumerate(registrations) if arguments[0].get('server_id')==item['server_id'])
            witnesses=[item['server_id'] for i,item in enumerate(registrations) if identities[i]['uuid'] in allowed]
        selected={'operation':operation,'arguments_json':json.dumps(list(arguments)),'context_name':'','context_options_json':'{}',
            'use_advertised_endpoint':True,'witness_server_ids':witnesses,
            'target_confirmation':identities[peer]['uuid'],'timeout_seconds':180,
            **({'account_password_mode':'set'} if password is not None else {})}
        review=post('review',{'options':selected},origin=origin,execution=peer if origin!=peer else None)
        if password is not None:assert password not in json.dumps(review)
        value=post('start',{**{k:review[k] for k in ('job_id','review_digest')},'confirmed':True,
            **({'account_secret':{'password':password}} if password is not None else {})},origin=origin,execution=peer if origin!=peer else None)
        deadline=time.monotonic()+200
        while value['state'] in {'dispatching','active','cancel_requested'}:
            if time.monotonic()>deadline:raise TimeoutError('Native security operation deadline')
            time.sleep(.15);value=post('status',{'job_id':value['job_id']},origin=origin,execution=peer if origin!=peer else None)
        (output/(str(len(proof['operations']))+'-'+operation.replace('.','-')+'.json')).write_text(json.dumps(value,indent=2)+'\n')
        assert value['native_operation_outcome']=='returned' and value['native_process_termination_confirmed'],value.get('native_error') or value.get('error_type')
        if origin!=peer:assert value['execution_registration']['server_id']==registrations[peer]['server_id']
        proof['operations'].append({'method':operation,'origin':origin,'execution':peer,'job_id':value['job_id']})
        return value
    def accounts(family):
        created=[]
        try:
            for purpose in ('admin','router'):
                user='sr_cert_'+purpose+'_'+secrets.token_hex(5);password='private-cert-'+secrets.token_urlsafe(20)
                created.append(user)
                value=execute(family+'.setup_'+purpose+'_account',[{'user':user,'host':'%'},{'requireCertIssuer':cert['issuer'],'requireCertSubject':cert['subject']}],origin=1,password=password)
                assert value['result']['account_observation']['exists']
                tls={'ssl_ca':cert['ca'],'ssl_cert':cert['certificate'],'ssl_key':cert['key'],'ssl_verify_cert':True}
                connection=mysql.connector.connect(host=peers[0]['address'],port=3306,user=user,password=password,
                    use_pure=not use_c,autocommit=True,connection_timeout=5,read_timeout=5,**tls)
                try:
                    cursor=connection.cursor();cursor.execute('SELECT CURRENT_USER()');assert cursor.fetchone()[0]==user+'@%'
                    cursor.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'");assert cursor.fetchone()[1];cursor.close()
                finally:connection.close()
                try:
                    connection=mysql.connector.connect(host=peers[0]['address'],port=3306,user=user,password=password,
                        use_pure=not use_c,connection_timeout=5,read_timeout=5,ssl_disabled=True)
                except mysql.connector.Error as error:assert error.errno in {1045,3159},error
                else:connection.close();raise AssertionError('Native certificate account accepted a non-TLS password-only login')
                assert password not in json.dumps(value)
                proof['checks'].append(family+'-'+purpose+'-secondary-origin-owned-primary-review-private-password-native-certificate-account-and-real-TLS-login-refusal-without-certificate')
        finally:
            for user in created:sql(0,'DROP USER IF EXISTS %s@%s',(user,'%'))
    def standalone(peer):
        return not sql(peer,"SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA='mysql_innodb_cluster_metadata'") and not sql(peer,"SELECT CHANNEL_NAME FROM performance_schema.replication_connection_configuration WHERE CHANNEL_NAME NOT IN ('group_replication_applier','group_replication_recovery')") and not sql(peer,'SHOW REPLICAS')
    def reset_owned_generation():
        for peer in range(3):
            until(lambda peer=peer:standalone(peer))
            sql(peer,'SET GLOBAL super_read_only=OFF')
            sql(peer,'RESET BINARY LOGS AND GTIDS')
    try:
        assert sql(0,"SELECT MEMBER_ROLE AS role FROM performance_schema.replication_group_members WHERE MEMBER_ID=@@server_uuid")==[{'role':'PRIMARY'}]
        accounts('cluster')
        execute('cluster.create_cluster_set',['sr_security_'+secrets.token_hex(5)])
        accounts('cluster_set')
        execute('cluster_set.dissolve',[{'force':True}])
        reset_owned_generation()
        for peer in range(3):execute('instance.configure_replica_set',[{'restart':True}],peer=peer)
        execute('instance.create_replica_set',['sr_security_rs_'+secrets.token_hex(5),{'gtidSetIsComplete':True}])
        execute('replica_set.add_instance',[{'server_id':registrations[1]['server_id']},{'recoveryMethod':'incremental'}])
        post('inspect',{},origin=1,execution=2,refused=True)
        accounts('replica_set')
        proof['checks'].append('owned-execution-registration-outside-current-native-topology-refused-before-dispatch')
        execute('replica_set.dissolve',[{'force':True}])
        reset_owned_generation()
        for peer in range(3):execute('instance.configure_cluster',[{'restart':True}],peer=peer)
        execute('instance.create_cluster',['sr_security_restored_'+secrets.token_hex(5),{'gtidSetIsComplete':True,'communicationStack':'MYSQL'}])
        for peer in (1,2):execute('cluster.add_instance',[{'server_id':registrations[peer]['server_id']},{'recoveryMethod':'incremental'}])
        proof.update(complete=True,owned_fixture_restored=True)
    finally:
        jobs=getattr(service_for_app(app),'mysql_topology_jobs',None);proof['owned_jobs_stopped']=jobs.close() if jobs else True
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--fixture',required=True);parser.add_argument('--certificates',required=True);parser.add_argument('--use-c',action='store_true');args=parser.parse_args()
    result=qualify(args.output,args.fixture,args.certificates,args.use_c);print(json.dumps({'complete':result['complete'],'checks':len(result['checks'])}))

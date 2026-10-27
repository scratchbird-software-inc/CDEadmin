"""Owned Community ALTER INSTANCE, independent pure/C and reviewed API evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output,application=False):
    import config  # noqa: F401
    from mysql_qualification_support import server,_root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE,MYSQL_ADMINISTRATION,_create_client
    from pgadmin.cdeadmin.providers.mysql_family import mysql_instance as adapter
    from pgadmin.cdeadmin.sdk import RelationalClientError
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep native evidence outside source')
    output.mkdir(parents=True,exist_ok=False)
    paths=['web/pgadmin/cdeadmin/providers/mysql_family/'+name for name in ('mysql_instance.py','administration.py','provider.py')]
    paths+=['tools/cdeadmin_mysql_instance_qualification.py']
    proof={'complete':False,'interfaces':[],'history_testing':'not run','full_mysql_product_complete':False,
        'source_sha256':{path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in paths}}
    try:
        with server(output/'fixture',keyring=True) as (route,_name,owned):
            oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;query=oracle.cursor()
            try:
                query.execute('CREATE DATABASE sr_instance')
                query.execute("CREATE TABLE sr_instance.t(id INT PRIMARY KEY) ENCRYPTION='Y'")
                query.execute('INSERT INTO sr_instance.t VALUES(1)')
                query.execute('CREATE TABLE sr_instance.pending(id INT PRIMARY KEY)')
                query.execute('SET GLOBAL binlog_encryption=ON')
                query.execute('SELECT @@server_uuid');uuid=query.fetchone()[0]
                target={'resource_id':'server:MySQL','resource_kind':'server','display_name':'MySQL','display_path':['MySQL'],'native':{'server_uuid':uuid}}
                def keys():
                    query.execute('SELECT KEY_ID FROM performance_schema.keyring_keys ORDER BY KEY_ID')
                    return {row[0] for row in query.fetchall()}
                for pure in (True,False):
                    selected={**route,'database':'sr_instance','use_pure':pure}
                    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace())
                    connect=client._connect;classes=[]
                    def tracked(request):
                        value=connect(request);classes.append(type(value).__name__);return value
                    def plan(operation,**draft):
                        return client.plan_admin_operation({'resource_kind':'server','operation_id':operation,
                            'draft':{'confirmation':'MySQL',**draft},'target_resource':target,'_provider_route':selected})
                    def apply(operation,**draft):return MYSQL_ADMINISTRATION.apply(client,plan(operation,**draft))
                    checks=[];templates={};key_changes=[]
                    try:
                        with patch.object(client,'_connect',tracked):
                            for operation in adapter.OPERATIONS:
                                if adapter.OPERATIONS[operation][1] is None:continue
                                draft={'initial_load_only':True} if operation=='disable_innodb_redo' else {}
                                before=keys();planned=plan(operation,**draft)
                                templates[operation]=planned['provider_payload']['compiled']['statements'][0]['source']
                                value=MYSQL_ADMINISTRATION.apply(client,planned)
                                assert value['accepted'] and value['instance_observation']['native_acknowledged'] and not value['automatic_retry']
                                after=keys()
                                if operation.startswith('rotate_'):
                                    prefix='INNODBKey-' if operation=='rotate_innodb_master_key' else 'MySQLReplicationKey_'
                                    added=sorted(key for key in after-before if key.startswith(prefix));assert added
                                    key_changes.append({'operation':operation,'added_native_key_ids':added})
                                if operation.endswith('innodb_redo'):assert value['instance_observation']['redo_state_verified']
                            # Restore native redo before any further ordinary work.
                            assert apply('enable_innodb_redo')['instance_observation']['redo_state_verified']
                            checks.append('all-six-native-instance-commands-acknowledged-with-real-key-id-rotation-and-redo-OFF-ON-postconditions')
                            for channel,rollback in (('mysql_admin',True),('mysql_main',False)):
                                assert apply('reload_tls',channel=channel,rollback_on_error=rollback)['accepted']
                            checks.append('native-main-admin-TLS-channels-and-explicit-NO-ROLLBACK-behavior-accepted')
                            changed_tls=plan('reload_tls')
                            query.execute('SELECT @@GLOBAL.ssl_cert');certificate=query.fetchone()[0]
                            query.execute('SET GLOBAL ssl_cert=%s',('sr_owned_absent_certificate.pem',))
                            try:
                                try:MYSQL_ADMINISTRATION.apply(client,changed_tls)
                                except RelationalClientError as error:assert not error.native_dispatched
                                else:raise AssertionError('Changed configured TLS path was dispatched')
                            finally:query.execute('SET GLOBAL ssl_cert=%s',(certificate,))
                            checks.append('changed-configured-TLS-path-refused-before-native-context-reload')
                            changed=plan('enable_innodb_redo');query.execute('ALTER INSTANCE DISABLE INNODB REDO_LOG')
                            try:
                                try:MYSQL_ADMINISTRATION.apply(client,changed)
                                except RelationalClientError as error:assert not error.native_dispatched and not error.native_acknowledged
                                else:raise AssertionError('Stale native redo state was dispatched')
                            finally:query.execute('ALTER INSTANCE ENABLE INNODB REDO_LOG')
                            checks.append('changed-native-redo-state-refused-before-maintenance-dispatch')
                            query.execute('SET GLOBAL binlog_encryption=OFF')
                            try:
                                try:apply('rotate_binlog_master_key')
                                except RelationalClientError as error:assert error.native_dispatched and not error.native_acknowledged and type(error.errno) is int
                                else:raise AssertionError('Disabled binlog encryption was reported as rotated')
                            finally:query.execute('SET GLOBAL binlog_encryption=ON')
                            checks.append('actual-native-binlog-encryption-disabled-refusal-keeps-error-code-and-no-ACK')
                            observed=adapter.observe;calls=0;before=keys();review=plan('rotate_innodb_master_key')
                            def lost(*args):
                                nonlocal calls
                                calls+=1
                                if calls==2:raise OSError('Owned post-ACK observation loss')
                                return observed(*args)
                            with patch.object(adapter,'observe',lost):
                                try:MYSQL_ADMINISTRATION.apply(client,review)
                                except RelationalClientError as error:assert error.native_dispatched and error.native_acknowledged and not error.automatic_retry
                                else:raise AssertionError('Post-ACK observation loss was hidden')
                            assert any(key.startswith('INNODBKey-') for key in keys()-before)
                            checks.append('real-key-rotation-ACK-survives-later-observation-loss-without-replay')
                            query.execute('SELECT * FROM sr_instance.t');assert query.fetchall()==[(1,)]
                            checks.append('encrypted-table-remains-readable-after-rotations-keyring-reload-TLS-and-redo-transitions')
                            query.execute("CREATE USER IF NOT EXISTS 'sr_instance_denied'@'%'")
                            query.execute("GRANT SELECT ON performance_schema.* TO 'sr_instance_denied'@'%'")
                            denied={**selected,'user':'sr_instance_denied','database':None}
                            request={'resource_kind':'server','operation_id':'reload_keyring','draft':{'confirmation':'MySQL'},'target_resource':target,'_provider_route':denied}
                            denied_plan=client.plan_admin_operation(request)
                            try:MYSQL_ADMINISTRATION.apply(client,denied_plan)
                            except RelationalClientError as error:assert error.errno==1227 and error.native_dispatched and not error.native_acknowledged
                            else:raise AssertionError('A principal without native encryption privilege reloaded keyring')
                            checks.append('native-1227-privilege-refusal-preserved-through-owned-reviewed-maintenance')
                            expected='CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection'
                            assert classes and set(classes)=={expected}
                            proof['interfaces'].append({'use_pure':pure,'native_connection_class':expected,'checks':checks,'templates':templates,'key_changes':key_changes})
                    finally:client.close()
                if application:
                    password='instance-'+secrets.token_urlsafe(24)
                    query.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                    proof['application']=workspace(output,route,password,query,target)
                proof['complete']=True
            finally:query.close();oracle.close()
        proof['owned_server_stopped']=owned['owned_server_stopped']
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def workspace(output,route,password,oracle,resource):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    app=setup_application(output)
    from flask import url_for
    from pgadmin.model import db,User,ServerGroup,Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    client=app.test_client();receipts=[]
    for pure in (True,False):
        with app.test_request_context('/'):
            uid=User.query.first().id;group=ServerGroup.query.filter_by(user_id=uid).first()
            app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
            item=Server(user_id=uid,servergroup_id=group.id,name='Owned instance '+str(pure),host=route['host'],port=route['port'],username='root',maintenance_db='sr_instance',save_password=0)
            item._cde_endpoint_registration=registration_profile('mysql-native')
            item._cde_endpoint_route_configuration={**route,'user':'root','use_pure':pure,'credential_kinds':['database_password']}
            db.session.add(item);db.session.commit()
            url=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=item.id);verify=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=item.id)
        with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
        assert client.post(verify,json={'password':password}).get_json()['success']
        def post(action,request):
            response=client.post(url,json={'action':action,'request':request});value=response.get_json()
            if response.status_code!=200 or not value.get('success'):
                (output/'application-failure.json').write_text(json.dumps(value,indent=2).replace(password,'<redacted>')+'\n')
                raise AssertionError('Native instance application request failed: '+action)
            return value['data']
        for operation in ('reload_tls','reload_keyring','rotate_innodb_master_key','rotate_binlog_master_key','disable_innodb_redo','enable_innodb_redo'):
            request={'resource_kind':'server','operation_id':operation,'target_resource':resource,
                'draft':{'confirmation':'MySQL',**({'initial_load_only':True} if operation=='disable_innodb_redo' else {})}}
            plan=post('visual_admin_plan',request);assert plan['state']=='ready' and plan['execution_available']
            apply={key:plan[key] for key in ('plan_id','plan_digest')}|{'confirmed':True}
            result=post('visual_admin_apply',apply);assert result['provider_result']['instance_observation']['native_acknowledged']
            replay=client.post(url,json={'action':'visual_admin_apply','request':apply})
            assert replay.status_code!=200 or not replay.get_json().get('success')
            receipts.append({'use_pure':pure,'operation':operation,'reviewed_native_acknowledged':True,'replay_refused':True})
        oracle.execute('SET autocommit=0');oracle.execute('INSERT INTO sr_instance.pending VALUES(9)');oracle.execute('SAVEPOINT instance_guard')
        plan=post('visual_admin_plan',{'resource_kind':'server','operation_id':'reload_keyring','target_resource':resource,'draft':{'confirmation':'MySQL'}})
        post('visual_admin_apply',{key:plan[key] for key in ('plan_id','plan_digest')}|{'confirmed':True})
        oracle.execute('ROLLBACK TO SAVEPOINT instance_guard');oracle.execute('ROLLBACK');oracle.execute('SET autocommit=1')
    return {'complete':True,'operations':receipts,'independent_pending_transaction_savepoint_preserved':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--application',action='store_true')
    args=parser.parse_args();value=qualify(args.output,args.application)
    print(json.dumps({'complete':value['complete'],'interfaces':len(value['interfaces'])}))

"""Owned MySQL pure/C registration lifecycle and retained native SQL proof."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output):
    import config  # noqa: F401
    from mysql_qualification_support import server,_root_connection
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True,exist_ok=False)
    paths=['tools/cdeadmin_mysql_registration_lifecycle_qualification.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/provider.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_recovery_bridge.py',
        'web/pgadmin/cdeadmin/endpoints/service.py',
        'web/pgadmin/cdeadmin/core/registry.py',
        'web/pgadmin/browser/server_groups/servers/__init__.py']
    proof={'complete':False,'interfaces':[],'history_testing':'not run','full_product_complete':False,
        'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    try:
        with server(output/'fixture') as (route,_name,owned):
            root=_root_connection('mysql',route['port']);root.autocommit=True
            password='owned-lifecycle-'+secrets.token_urlsafe(24)
            with root.cursor() as cursor:
                cursor.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                cursor.execute('CREATE DATABASE sr_lifecycle')
                cursor.execute('CREATE TABLE sr_lifecycle.pending(id INT PRIMARY KEY) ENGINE=InnoDB')
            root.close()
            app=setup_application(output)
            from flask import url_for
            from pgadmin.model import db,User,ServerGroup,Server,EndpointDatabaseTarget
            from pgadmin.cdeadmin.endpoints.profiles import registration_profile
            from pgadmin.cdeadmin.workspace.service import service_for_app
            for pure in (True,False):
                client=app.test_client();checks=[]
                with app.test_request_context('/'):
                    uid=User.query.first().id;group=ServerGroup.query.filter_by(user_id=uid).first()
                    app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
                    item=Server(user_id=uid,servergroup_id=group.id,name='Owned lifecycle '+str(pure),
                        host=route['host'],port=route['port'],username='root',maintenance_db='sr_lifecycle',save_password=0)
                    item._cde_endpoint_registration=registration_profile('mysql-native')
                    item._cde_endpoint_route_configuration={**route,'database':'sr_lifecycle','autocommit':False,
                        'use_pure':pure,'credential_kinds':['database_password']}
                    db.session.add(item);db.session.commit();sid=item.id;target=str(uuid.uuid4())
                    db.session.add(EndpointDatabaseTarget(id=target,endpoint_id=item.endpoint_profile.id,
                        display_name='sr_lifecycle',database='sr_lifecycle',configuration='{}',active=1));db.session.commit()
                    url=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=sid)
                    verify=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=sid)
                    disconnect=url_for('NODE-server.connect_id',gid=group.id,sid=sid)
                    legacy=url_for('NODE-server.obj_id',gid=group.id,sid=sid)
                with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
                assert client.post(verify,json={'password':password}).get_json()['success']
                for method in ('put','delete'):
                    response=getattr(client,method)(legacy,json={'name':'must not change'})
                    assert response.status_code==409 and 'connection profile form' in response.get_json()['errormsg'],response.get_json()
                    checks.append('legacy-'+method+'-requires-provider-form')
                def post(action,**data):
                    response=client.post(url,json={'action':action,'database_target_id':target,**data})
                    value=response.get_json()
                    assert response.status_code==200 and value.get('success'),(action,value)
                    return value['data']
                session=post('open_session',language_profile='mysql-sql')['session_id']
                def sql(source):
                    occurrence=post('execute',session_id=session,source=source,parameters=[],history_sensitive=True)
                    deadline=time.monotonic()+30
                    while time.monotonic()<deadline:
                        row=post('poll',occurrence_id=occurrence['occurrence_id'])['occurrence']
                        if row['operation']['terminal']:break
                    else:raise TimeoutError('Native lifecycle SQL did not finish')
                    payload=row['result']['extensions']['mysql']['payload']
                    assert not payload.get('error'),payload
                    return payload.get('rows',[])
                sql('CREATE TEMPORARY TABLE retained_temp(value INT)')
                sql('INSERT INTO retained_temp VALUES(73)')
                sql("PREPARE retained_statement FROM 'SELECT value FROM retained_temp'")
                sql('INSERT INTO pending VALUES('+('1' if pure else '2')+')')
                sql('SAVEPOINT retained_work')
                for action,request in [('endpoint_profile_update',{'name':'must not change'}),
                        ('endpoint_profile_remove',{'confirmation':'Owned lifecycle '+str(pure)}),
                        ('database_target_delete',{'target_id':target})]:
                    response=client.post(url,json={'action':action,'request':request})
                    assert response.status_code==409 and 'close this connection' in response.get_json()['errormsg'],(action,response.get_json())
                    checks.append(action+'-refused-with-native-work')
                response=client.delete(disconnect)
                assert response.status_code==409 and 'close this connection' in response.get_json()['errormsg'],response.get_json()
                checks.append('actual-server-disconnect-refused-without-PostgreSQL-fallback')
                sql('ROLLBACK TO SAVEPOINT retained_work')
                assert sql('EXECUTE retained_statement')==[[73]]
                assert sql('SELECT COUNT(*) FROM pending')[0][0]==1
                checks.append('transaction-savepoint-temporary-table-and-prepared-statement-preserved')
                post('transaction_action',session_id=session,transaction_action='rollback')
                assert sql('SELECT COUNT(*) FROM pending')==[[0]]
                assert sql('SELECT COUNT(*) FROM retained_temp')==[[0]]
                assert sql('EXECUTE retained_statement')==[]
                checks.append('explicit-native-rollback-preserves-session-objects')
                # Capture the original binding to prove successful release
                # invalidates an already acquired facade/client as well.
                with app.test_request_context('/'):
                    service=service_for_app(app)
                    registry=service.endpoint_service.provider_registry
                    providers=[b.instance for r in registry._registrations.values() for b in r.bindings.values()
                        if b.context.endpoint_id==db.session.get(Server,sid).endpoint_profile.id]
                    retained=next(p for p in providers if session in p._sessions)
                post('close_session',session_id=session)
                response=client.delete(disconnect);assert response.status_code==200 and response.get_json()['success'],response.get_json()
                assert retained.client._executions.closing and not retained._sessions
                from pgadmin.cdeadmin.sdk import RelationalClientError
                try:retained.client._connect({'route':{**route,'use_pure':pure}})
                except RelationalClientError:pass
                else:raise AssertionError('released client opened a new native connection')
                checks.append('explicit-session-close-admits-disconnect-and-invalidates-original-client')
                assert client.post(verify,json={'password':password}).get_json()['success']
                session=post('open_session',language_profile='mysql-sql')['session_id']
                assert sql('SELECT COUNT(*) FROM pending')==[[0]]
                post('close_session',session_id=session)
                checks.append('fresh-verification-and-session-use-new-provider')
                value=post('endpoint_profile_remove',request={'confirmation':'Owned lifecycle '+str(pure)})
                assert value['removed'];checks.append('explicit-idle-registration-removal')
                proof['interfaces'].append({'use_pure':pure,'checks':checks,'complete':True})
        proof.update(complete=True,owned_server_stopped=owned['owned_server_stopped'])
        return proof
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    print(json.dumps(qualify(parser.parse_args().output),indent=2))

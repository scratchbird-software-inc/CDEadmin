"""Owned native named-cache configure, inspect and release in pure/C and API."""
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
    from pgadmin.cdeadmin.providers.mysql_family import mysql_key_cache_lifecycle as adapter
    from pgadmin.cdeadmin.sdk import RelationalClientError
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep evidence outside source')
    output.mkdir(parents=True,exist_ok=False)
    paths=['web/pgadmin/cdeadmin/providers/mysql_family/'+name for name in ('mysql_key_cache_lifecycle.py','administration.py','provider.py','mysql_charsets.py','mysql_warnings.py')]
    paths+=['tools/cdeadmin_mysql_key_cache_lifecycle_qualification.py']
    proof={'complete':False,'interfaces':[],'history_testing':'not run','full_mysql_product_complete':False,
        'source_sha256':{path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in paths}}
    try:
        with server(output/'fixture') as (route,_name,owned):
            oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;query=oracle.cursor()
            try:
                query.execute('CREATE DATABASE sr_cache_lifecycle')
                query.execute('CREATE TABLE sr_cache_lifecycle.t(id INT PRIMARY KEY,value INT,KEY(value)) ENGINE=MyISAM')
                query.executemany('INSERT INTO sr_cache_lifecycle.t VALUES(%s,%s)',[(i,i*10) for i in range(100)])
                query.execute('CREATE TABLE sr_cache_lifecycle.pending(id INT PRIMARY KEY) ENGINE=InnoDB')
                query.execute('SELECT @@server_uuid');uuid=query.fetchone()[0]
                target={'resource_id':'server:MySQL','resource_kind':'server','display_name':'MySQL','display_path':['MySQL'],'native':{'server_uuid':uuid}}
                name='cache . ` é'
                for pure in (True,False):
                    selected={**route,'database':'sr_cache_lifecycle','use_pure':pure}
                    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace());classes=[];connect=client._connect
                    def tracked(request):
                        value=connect(request);classes.append(type(value).__name__);return value
                    def plan(operation,cache_name=name,**draft):
                        return client.plan_admin_operation({'resource_kind':'server','operation_id':operation,'draft':{'cache_name':cache_name,'confirmation':'MySQL',**draft},'target_resource':target,'_provider_route':selected})
                    def apply(operation,**draft):return MYSQL_ADMINISTRATION.apply(client,plan(operation,**draft))
                    templates={};checks=[];native_warnings=[]
                    try:
                        with patch.object(client,'_connect',tracked):
                            empty=apply('inspect_key_cache')['key_cache_observation']['after']
                            assert not empty['native_cache_existence_asserted']
                            request=plan('configure_key_cache',value='4194305')
                            templates['configure_key_cache']=request['provider_payload']['compiled']['statements'][0]['source']
                            changed=MYSQL_ADMINISTRATION.apply(client,request)
                            assert changed['key_cache_observation']['after']['native_values']['key_buffer_size']=='4194304'
                            for field,value,expected in [('key_cache_block_size','1537','1536'),('key_cache_division_limit','65','65'),('key_cache_age_threshold','1234','1200')]:
                                result=apply('configure_key_cache',variable=field,value=value)
                                assert result['key_cache_observation']['after']['native_values'][field]==expected
                                native_warnings.extend(result['native_warnings'])
                            result=apply('configure_key_cache',variable='key_cache_block_size',value_mode='DEFAULT')
                            assert result['key_cache_observation']['after']['native_values']['key_cache_block_size']=='1024'
                            result=apply('configure_key_cache',variable='key_cache_age_threshold',value='9007199254740993')
                            assert result['key_cache_observation']['after']['native_values']['key_cache_age_threshold']=='9007199254740900'
                            apply('configure_key_cache',variable='key_cache_age_threshold',value='300')
                            checks.append('all-four-native-cache-variables-and-DEFAULT-with-real-server-rounding-and-exact-values-above-JavaScript-safe-integer')
                            query.execute('CACHE INDEX sr_cache_lifecycle.t IN '+adapter.identifier(name));assert any(row[2:] == ('status','OK') for row in query.fetchall())
                            query.execute('LOAD INDEX INTO CACHE sr_cache_lifecycle.t');assert any(row[2:] == ('status','OK') for row in query.fetchall())
                            inspected=plan('inspect_key_cache');templates['inspect_key_cache']=inspected['provider_payload']['compiled']['statements'][0]['source']
                            query.execute('SET GLOBAL '+adapter.identifier(name)+'.key_cache_age_threshold=600')
                            result=MYSQL_ADMINISTRATION.apply(client,inspected)
                            assert result['key_cache_observation']['after']['native_values']['key_cache_age_threshold']=='600'
                            checks.append('configured-quoted-Unicode-cache-accepts-native-table-assignment-preload-and-read-only-inspection-reports-current-values')
                            stale=plan('configure_key_cache',variable='key_cache_division_limit',value='75')
                            query.execute('SET GLOBAL '+adapter.identifier(name)+'.key_cache_age_threshold=700')
                            try:MYSQL_ADMINISTRATION.apply(client,stale)
                            except RelationalClientError as error:assert not error.native_dispatched
                            else:raise AssertionError('Changed native cache state was mutated')
                            checks.append('changed-cache-configuration-refused-before-native-setting-dispatch')
                            release=plan('release_key_cache');templates['release_key_cache']=release['provider_payload']['compiled']['statements'][0]['source']
                            result=MYSQL_ADMINISTRATION.apply(client,release)
                            assert result['key_cache_observation']['after']['native_values']['key_buffer_size']=='0' and not result['key_cache_observation']['native_prefix_deleted']
                            query.execute('LOAD INDEX INTO CACHE sr_cache_lifecycle.t');assert any(row[2:] == ('status','OK') for row in query.fetchall())
                            checks.append('native-release-zeroes-buffer-retains-prefix-options-and-table-index-preload-remains-available')
                            try:apply('release_key_cache',cache_name='default')
                            except RelationalClientError as error:assert error.errno==1438 and error.native_dispatched and not error.native_acknowledged
                            else:raise AssertionError('Native default cache protection was bypassed')
                            checks.append('actual-native-1438-default-cache-release-refusal-preserved')
                            apply('configure_key_cache',value='4194304')
                            review=plan('configure_key_cache',variable='key_cache_division_limit',value='99');observed=adapter.observe;calls=0
                            def lost(*args):
                                nonlocal calls
                                calls+=1
                                if calls==2:raise OSError('Owned post-ACK cache read loss')
                                return observed(*args)
                            with patch.object(adapter,'observe',lost):
                                try:MYSQL_ADMINISTRATION.apply(client,review)
                                except RelationalClientError as error:assert error.native_dispatched and error.native_acknowledged and not error.automatic_retry
                                else:raise AssertionError('Post-ACK read failure was hidden')
                            query.execute('SELECT @@GLOBAL.'+adapter.identifier(name)+'.key_cache_division_limit');assert query.fetchone()==(99,)
                            checks.append('real-native-setting-ACK-survives-later-observation-loss-without-replay')
                            query.execute('SELECT COUNT(*),SUM(value) FROM sr_cache_lifecycle.t');assert query.fetchone()==(100,49500)
                            checks.append('native-cache-lifecycle-does-not-change-table-data')
                            expected='CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection';assert classes and set(classes)=={expected}
                            proof['interfaces'].append({'use_pure':pure,'native_connection_class':expected,'checks':checks,'templates':templates,'native_warnings':native_warnings})
                    finally:client.close()
                if application:
                    password='cache-lifecycle-'+secrets.token_urlsafe(24)
                    query.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                    proof['application']=workspace(output,route,password,query,target,name)
                proof['complete']=True
            finally:query.close();oracle.close()
        proof['owned_server_stopped']=owned['owned_server_stopped']
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def workspace(output,route,password,oracle,resource,name):
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
            item=Server(user_id=uid,servergroup_id=group.id,name='Owned cache lifecycle '+str(pure),host=route['host'],port=route['port'],username='root',maintenance_db='mysql',save_password=0)
            item._cde_endpoint_registration=registration_profile('mysql-native');item._cde_endpoint_route_configuration={**route,'user':'root','use_pure':pure,'credential_kinds':['database_password']}
            db.session.add(item);db.session.commit();url=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=item.id);verify=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=item.id)
        with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
        assert client.post(verify,json={'password':password}).get_json()['success']
        def post(action,request):
            response=client.post(url,json={'action':action,'request':request});value=response.get_json()
            if response.status_code!=200 or not value.get('success'):
                (output/'application-failure.json').write_text(json.dumps(value,indent=2).replace(password,'<redacted>')+'\n');raise AssertionError('Native cache lifecycle application failed: '+action)
            return value['data']
        for operation in ('configure_key_cache','inspect_key_cache','release_key_cache'):
            draft={'cache_name':name}
            if operation!='inspect_key_cache':draft['confirmation']='MySQL'
            if operation=='configure_key_cache':draft.update(variable='key_buffer_size',value_mode='VALUE',value='4194304')
            request={'resource_kind':'server','operation_id':operation,'target_resource':resource,'draft':draft}
            checked=post('visual_admin_validate',request);assert checked['valid'],(operation,checked['errors'])
            plan=post('visual_admin_plan',request);assert plan['state']=='ready' and plan['execution_available']
            result=post('visual_admin_apply',{key:plan[key] for key in ('plan_id','plan_digest')}|{'confirmed':True})
            assert result['provider_result']['key_cache_observation']['native_acknowledged']
            receipts.append({'use_pure':pure,'operation':operation,'reviewed_native_acknowledged':True})
        oracle.execute('SET autocommit=0');oracle.execute('INSERT INTO sr_cache_lifecycle.pending VALUES(9)');oracle.execute('SAVEPOINT cache_lifecycle_guard')
        request={'resource_kind':'server','operation_id':'configure_key_cache','target_resource':resource,'draft':{'confirmation':'MySQL','cache_name':name,'variable':'key_buffer_size','value_mode':'VALUE','value':'4194304'}}
        plan=post('visual_admin_plan',request);post('visual_admin_apply',{key:plan[key] for key in ('plan_id','plan_digest')}|{'confirmed':True})
        oracle.execute('ROLLBACK TO SAVEPOINT cache_lifecycle_guard');oracle.execute('ROLLBACK');oracle.execute('SET autocommit=1')
    return {'complete':True,'operations':receipts,'independent_pending_transaction_savepoint_preserved':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--application',action='store_true')
    args=parser.parse_args();value=qualify(args.output,args.application)
    print(json.dumps({'complete':value['complete'],'interfaces':len(value['interfaces'])}))

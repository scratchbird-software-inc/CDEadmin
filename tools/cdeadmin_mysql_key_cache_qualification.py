"""Owned native MySQL9.7 MyISAM cache operations; no application emulation."""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import secrets
import uuid
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output, application=False):
    import config  # noqa: F401
    from mysql_qualification_support import server,_root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION as adapter,MYSQL_PROFILE,_create_client
    from pgadmin.cdeadmin.providers.mysql_family import mysql_key_cache as cache
    from pgadmin.cdeadmin.sdk import RelationalClientError
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep native evidence outside source')
    output.mkdir(parents=True,exist_ok=False)
    paths=['tools/cdeadmin_mysql_key_cache_qualification.py','web/pgadmin/cdeadmin/providers/mysql_family/mysql_key_cache.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/administration.py','web/pgadmin/cdeadmin/providers/mysql_family/provider.py']
    proof={'complete':False,'history_testing':'not run','full_product_complete':False,'interfaces':[],
        'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    try:
        with server(output/'fixture') as (route,_name,owned):
            oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;query=oracle.cursor()
            try:
                query.execute('CREATE DATABASE sr_cache CHARACTER SET utf8mb4')
                query.execute('CREATE TABLE sr_cache.`t . `` é` (id INT PRIMARY KEY,value INT,KEY `index . `` é`(value)) ENGINE=MyISAM')
                query.executemany('INSERT INTO sr_cache.`t . `` é` VALUES(%s,%s)',[(i,i*10) for i in range(200)])
                query.execute('CREATE TABLE sr_cache.mixed_blocks(id INT PRIMARY KEY,value VARCHAR(80),KEY(value)) ENGINE=MyISAM')
                query.execute("INSERT INTO sr_cache.mixed_blocks VALUES(1,'owned mixed index sizes')")
                query.execute('CREATE TABLE sr_cache.not_myisam(id INT) ENGINE=InnoDB')
                query.execute('SET GLOBAL sr_named_cache.key_buffer_size=1048576')
                query.execute('SELECT id,value FROM sr_cache.`t . `` é` ORDER BY id');original=query.fetchall()
                def target(table='t . ` é'):
                    path=['sr_cache',table]
                    return {'resource_kind':'table','resource_id':cache.address(path),'display_path':path,'display_name':table}
                for pure in (True,False):
                    selected={**route,'database':'sr_cache','use_pure':pure}
                    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace())
                    checks=[];templates={}
                    native=client._connect({'route':selected})
                    try:
                        native_class=type(native).__name__
                        assert native_class==('CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection'),native_class
                    finally:client._forget_and_close(native)
                    def planned(operation,**draft):
                        request={'resource_kind':'table','operation_id':operation,
                            'draft':{'confirmation':target()['display_name'],**draft},'target_resource':target(),'_provider_route':selected}
                        assert not adapter.validate(request)['errors']
                        value=client.plan_admin_operation(request)
                        templates.setdefault(operation,value['command_preview']['statements'][0]['source'])
                        return value
                    try:
                        for name in ('default','sr_named_cache'):
                            for indexes in ([],['PRIMARY'],['index . ` é']):
                                value=adapter.apply(client,planned('assign_index_cache',cache_name=name,indexes=indexes))
                                assert value['accepted'] and value['index_cache_observation']['native_effect_acknowledged'],value
                                assert value['index_cache_observation']['definition_unchanged']
                        for leaves in (False,True):
                            value=adapter.apply(client,planned('preload_index_cache',ignore_leaves=leaves,indexes=['index . ` é']))
                            assert value['accepted'] and value['index_cache_observation']['native_effect_acknowledged'],value
                        checks.append('native-default-and-configured-named-cache-assignment-all-and-selected-exact-indexes-and-preload-with-or-without-ignore-leaves')
                        try:adapter.apply(client,planned('assign_index_cache',cache_name='sr_unconfigured_cache'))
                        except RelationalClientError as error:
                            assert error.errno==1284 and error.native_dispatched and not error.native_acknowledged and not error.automatic_retry
                        else:raise AssertionError('An unconfigured native key cache was accepted')
                        request={'resource_kind':'table','operation_id':'preload_index_cache','draft':{'confirmation':'mixed_blocks','ignore_leaves':True},
                            'target_resource':target('mixed_blocks'),'_provider_route':selected}
                        mixed=adapter.apply(client,client.plan_admin_operation(request))
                        assert not mixed['accepted'] and mixed['index_cache_observation']['native_acknowledged'] and not mixed['index_cache_observation']['native_effect_acknowledged'],mixed
                        assert any(row['msg_type']=='error' for row in mixed['index_cache_observation']['native_results'])
                        checks.append('native-error-result-rows-are-not-positive-cache-effect-acknowledgements')
                        stale=planned('preload_index_cache')
                        query.execute('ALTER TABLE sr_cache.`t . `` é` ADD COLUMN changed INT')
                        try:adapter.apply(client,stale)
                        except RelationalClientError as error:assert not error.native_dispatched and not error.native_acknowledged
                        else:raise AssertionError('Changed MyISAM definition was dispatched')
                        query.execute('ALTER TABLE sr_cache.`t . `` é` DROP COLUMN changed')
                        checks.append('changed-table-definition-refused-before-dispatch')
                        for table,indexes in (('not_myisam',[]),('t . ` é',['absent_index'])):
                            request={'resource_kind':'table','operation_id':'preload_index_cache','draft':{'confirmation':table,'indexes':indexes},
                                'target_resource':target(table),'_provider_route':selected}
                            try:client.plan_admin_operation(request)
                            except RelationalClientError:pass
                            else:raise AssertionError('Unsupported engine or missing exact index was admitted')
                        checks.append('innodb-and-missing-native-index-refused-during-review-without-emulation')
                        saved=cache.observe;counter=0
                        def loss(*args):
                            nonlocal counter
                            counter+=1
                            if counter==2:raise OSError('Owned post-ack independent observation loss')
                            return saved(*args)
                        review=planned('preload_index_cache')
                        with patch.object(cache,'observe',loss):
                            try:adapter.apply(client,review)
                            except RelationalClientError as error:assert error.native_dispatched and error.native_acknowledged and not error.automatic_retry
                            else:raise AssertionError('Post-ack observation loss was reported successful')
                        checks.append('actual-native-sql-acknowledgement-survives-later-observation-loss-without-retry')
                        query.execute('SELECT id,value FROM sr_cache.`t . `` é` ORDER BY id');assert query.fetchall()==original
                        proof['interfaces'].append({'use_pure':pure,'native_connection_class':native_class,'checks':checks,'templates':templates,'native_results':value['index_cache_observation']['native_results']})
                    finally:client.close()
                # The source and native parser both admit this syntax. Record
                # actual Community execution separately from storage/runtime use.
                materialized={}
                try:
                    query.execute('CREATE MATERIALIZED VIEW sr_cache.materialized_probe AS SELECT id FROM sr_cache.`t . `` é`')
                    query.execute('SHOW CREATE VIEW sr_cache.materialized_probe');materialized['declaration']=query.fetchone()[1]
                    try:
                        query.execute('SELECT COUNT(*) FROM sr_cache.materialized_probe');materialized['count']=query.fetchone()[0]
                    except Exception as error:materialized['read_error']=getattr(error,'errno',None)
                    query.execute('DROP VIEW sr_cache.materialized_probe')
                    materialized['create_acknowledged']=True
                except Exception as error:materialized.update(create_acknowledged=False,native_error=getattr(error,'errno',None))
                proof['materialized_view_observation']=materialized
                if application:
                    password='cache-'+secrets.token_urlsafe(24)
                    query.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                    proof['application']=workspace(output,route,password,query,target())
                proof['complete']=True
            finally:query.close();oracle.close()
        proof['owned_server_stopped']=owned['owned_server_stopped']
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def workspace(output, route, password, oracle, resource):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    from flask import url_for
    from pgadmin.model import db,User,ServerGroup,Server,EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    app=setup_application(output);client=app.test_client();receipts=[]
    for pure in (True,False):
        with app.test_request_context('/'):
            uid=User.query.first().id;group=ServerGroup.query.filter_by(user_id=uid).first()
            app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
            item=Server(user_id=uid,servergroup_id=group.id,name='Owned MyISAM cache '+str(pure),host=route['host'],
                port=route['port'],username='root',maintenance_db='sr_cache',save_password=0)
            item._cde_endpoint_registration=registration_profile('mysql-native')
            item._cde_endpoint_route_configuration={**route,'database':'sr_cache','user':'root','use_pure':pure,'credential_kinds':['database_password']}
            db.session.add(item);db.session.commit();target=str(uuid.uuid4())
            db.session.add(EndpointDatabaseTarget(id=target,endpoint_id=item.endpoint_profile.id,display_name='sr_cache',database='sr_cache',configuration='{}',active=1));db.session.commit()
            url=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=item.id)
            verify=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=item.id)
        with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
        assert client.post(verify,json={'password':password}).get_json()['success']
        def post(action,request):
            response=client.post(url,json={'action':action,'request':{'database_target_id':target,**request}});value=response.get_json()
            if response.status_code!=200 or not value.get('success'):
                (output/'application-failure.json').write_text(json.dumps(value,indent=2).replace(password,'<redacted>')+'\n')
                raise AssertionError('Native cache application request failed: '+action)
            return value['data']
        for operation in ('assign_index_cache','preload_index_cache'):
            request={'resource_kind':'table','operation_id':operation,'target_resource':resource,
                'draft':{'confirmation':resource['display_name'],'indexes':['PRIMARY']}}
            checked=post('visual_admin_validate',request);assert not checked.get('errors'),checked
            plan=post('visual_admin_plan',request)
            assert plan['state']=='ready' and plan['execution_available'],plan
            result=post('visual_admin_apply',{key:plan[key] for key in ('plan_id','plan_digest')}|{'confirmed':True})
            assert result['provider_result']['index_cache_observation']['native_effect_acknowledged'],result
            replay=client.post(url,json={'action':'visual_admin_apply','request':{'database_target_id':target,
                **{key:plan[key] for key in ('plan_id','plan_digest')},'confirmed':True}})
            assert replay.status_code!=200 or not replay.get_json().get('success')
            receipts.append({'use_pure':pure,'operation':operation,'state':result.get('state'),'reviewed_native_effect_acknowledged':True,'replay_refused':True})
        oracle.execute('SET autocommit=0');oracle.execute('INSERT INTO sr_cache.not_myisam VALUES(9)');oracle.execute('SAVEPOINT native_cache_guard')
        request={'resource_kind':'table','operation_id':'preload_index_cache','target_resource':resource,'draft':{'confirmation':resource['display_name']}}
        plan=post('visual_admin_plan',request)
        post('visual_admin_apply',{key:plan[key] for key in ('plan_id','plan_digest')}|{'confirmed':True})
        oracle.execute('ROLLBACK TO SAVEPOINT native_cache_guard');oracle.execute('ROLLBACK');oracle.execute('SET autocommit=1')
    return {'complete':True,'operations':receipts,'independent_pending_transaction_savepoint_preserved':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--application',action='store_true')
    args=parser.parse_args();value=qualify(args.output,args.application)
    print(json.dumps({'complete':value['complete'],'interfaces':len(value['interfaces'])}))

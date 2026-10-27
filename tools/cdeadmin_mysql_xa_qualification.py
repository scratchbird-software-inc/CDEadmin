"""Owned native binary XA branches, pure/C resolution and authenticated API."""
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


def seed(cursor,adapter,xid,key):
    source=adapter.xid_source(xid)
    cursor.execute('XA START '+source)
    cursor.execute('INSERT INTO sr_xa.t VALUES(%s)',(key,))
    cursor.execute('XA END '+source)
    cursor.execute('XA PREPARE '+source)


def qualify(output,application=False):
    import config  # noqa: F401
    from mysql_qualification_support import server,_root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE,MYSQL_ADMINISTRATION,_create_client
    from pgadmin.cdeadmin.providers.mysql_family import mysql_xa as adapter
    from pgadmin.cdeadmin.providers.mysql_family.mysql_server_catalog import capture
    from pgadmin.cdeadmin.sdk import RelationalClientError
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep evidence outside source')
    output.mkdir(parents=True,exist_ok=False)
    paths=['web/pgadmin/cdeadmin/providers/mysql_family/'+name for name in ('mysql_xa.py','mysql_server_catalog.py','administration.py','provider.py')]
    paths+=['tools/cdeadmin_mysql_xa_qualification.py']
    proof={'complete':False,'interfaces':[],'history_testing':'not run','full_mysql_product_complete':False,
        'source_sha256':{path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in paths}}
    try:
        with server(output/'fixture') as (route,_name,owned):
            oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;query=oracle.cursor()
            try:
                query.execute('CREATE DATABASE sr_xa');query.execute('CREATE TABLE sr_xa.t(id INT PRIMARY KEY) ENGINE=InnoDB')
                query.execute('CREATE TABLE sr_xa.pending(id INT PRIMARY KEY) ENGINE=InnoDB')
                query.execute('CREATE USER xa_denied');query.execute('SELECT @@server_uuid');uuid=query.fetchone()[0]
                target={'resource_id':'server:MySQL','resource_kind':'server','display_name':'MySQL','display_path':['MySQL'],'native':{'server_uuid':uuid}}
                for pure in (True,False):
                    selected={**route,'database':'sr_xa','use_pure':pure}
                    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace());classes=[];connect=client._connect
                    def tracked(request):
                        value=connect(request);classes.append(type(value).__name__);return value
                    def xid(key):return adapter.identity({'gtrid_hex':(b'\0\xff\x27\\'+bytes([key])+b'X'*(59)).hex(),'bqual_hex':(b'\x80\0'+bytes([key])).hex(),'format_id':'9007199254740993'})
                    def plan(operation,selected_xid=None):
                        draft={} if operation=='inspect_prepared_xa' else {key:selected_xid[key] for key in ('gtrid_hex','bqual_hex','format_id')}|{'confirmation':'MySQL','decision_reference':'Owned coordinator test decision','lock_wait_seconds':1}
                        return client.plan_admin_operation({'resource_kind':'server','operation_id':operation,'draft':draft,'target_resource':target,'_provider_route':selected})
                    checks=[];templates={};codes=[];base=0 if pure else 10
                    pending=client.open_session({'route':selected});work=pending.cursor()
                    try:
                        client.control_transaction(pending,'autocommit_off');work.execute('INSERT INTO pending VALUES(%s)',(base+1,));work.execute('SAVEPOINT xa_guard')
                        with patch.object(client,'_connect',tracked):
                            for operation,offset in [('commit_prepared_xa',1),('rollback_prepared_xa',2)]:
                                value=xid(base+offset);seed(query,adapter,value,base+offset)
                                request=plan(operation,value);templates[operation]=request['provider_payload']['compiled']['statements'][0]['source']
                                result=MYSQL_ADMINISTRATION.apply(client,request);assert result['xa_observation']['native_acknowledged']
                                assert value not in result['xa_observation']['prepared_after'] and not result['xa_observation']['global_transaction_decision_inferred']
                                query.execute('SELECT COUNT(*) FROM sr_xa.t WHERE id=%s',(base+offset,));assert query.fetchone()==((1 if offset==1 else 0),)
                            request=plan('inspect_prepared_xa');templates['inspect_prepared_xa']=request['provider_payload']['compiled']['statements'][0]['source']
                            assert MYSQL_ADMINISTRATION.apply(client,request)['xa_observation']['prepared_after']==[]
                            checks.append('binary-max64-global-ID-nonASCII-NUL-quote-backslash-empty-safe-literals-and-exact-formatID-above-JavaScript-safe-integer-resolved-with-real-commit-and-rollback-row-observations')
                            value=xid(base+3);seed(query,adapter,value,base+3);request=plan('rollback_prepared_xa',value)
                            query.execute('XA ROLLBACK '+adapter.xid_source(value))
                            try:MYSQL_ADMINISTRATION.apply(client,request)
                            except RelationalClientError as error:assert not error.native_dispatched and not error.automatic_retry
                            else:raise AssertionError('Missing prepared branch was replayed')
                            checks.append('resolved-since-review-XID-refused-before-dispatch')
                            value=xid(base+4);seed(query,adapter,value,base+4);request=plan('commit_prepared_xa',value);observed=adapter.observe;calls=0
                            def lost(*args):
                                nonlocal calls
                                calls+=1
                                if calls==2:raise OSError('Owned post-ACK XA recovery-list loss')
                                return observed(*args)
                            with patch.object(adapter,'observe',lost):
                                try:MYSQL_ADMINISTRATION.apply(client,request)
                                except RelationalClientError as error:assert error.native_dispatched and error.native_acknowledged and not error.automatic_retry
                                else:raise AssertionError('Post-ACK observation loss was hidden')
                            query.execute('SELECT COUNT(*) FROM sr_xa.t WHERE id=%s',(base+4,));assert query.fetchone()==(1,)
                            checks.append('actual-native-commit-ACK-remains-distinct-from-post-ACK-inventory-loss-without-replay')
                            value=xid(base+5);seed(query,adapter,value,base+5);request=plan('commit_prepared_xa',value)
                            def concurrent(*args):
                                result=observed(*args);query.execute('XA ROLLBACK '+adapter.xid_source(value));return result
                            with patch.object(adapter,'observe',concurrent):
                                try:MYSQL_ADMINISTRATION.apply(client,request)
                                except RelationalClientError as error:
                                    assert error.errno==1397 and error.sqlstate=='XAE04' and error.native_dispatched and not error.native_acknowledged and not error.automatic_retry;codes.append({'errno':error.errno,'sqlstate':error.sqlstate})
                                else:raise AssertionError('Concurrent native resolution refusal was lost')
                            checks.append('actual-native-1397-XAE04-concurrent-resolution-preserved-with-no-automatic-replay')
                            query.execute('SET SESSION xa_detach_on_prepare=OFF')
                            value=xid(base+7);seed(query,adapter,value,base+7)
                            try:
                                try:MYSQL_ADMINISTRATION.apply(client,plan('rollback_prepared_xa',value))
                                except RelationalClientError as error:
                                    assert error.errno==1397 and error.native_dispatched and not error.native_acknowledged;codes.append({'errno':error.errno,'sqlstate':error.sqlstate})
                                else:raise AssertionError('Attached prepared branch was resolved by another attachment')
                            finally:
                                query.execute('XA ROLLBACK '+adapter.xid_source(value));query.execute('SET SESSION xa_detach_on_prepare=ON')
                            checks.append('native-attached-prepared-branch-remains-owned-by-originating-attachment-and-native-refusal-is-preserved')
                            value=xid(base+6);seed(query,adapter,value,base+6)
                            handle=client._connect({'route':selected})
                            try:
                                catalog=capture(handle);rows=[item['native']['catalog_row'] for item in catalog['resources'] if item['resource_kind']=='prepared-transaction'];assert value in rows
                            finally:client._forget_and_close(handle)
                            MYSQL_ADMINISTRATION.apply(client,plan('rollback_prepared_xa',value))
                            checks.append('native-server-catalog-captures-exact-prepared-binary-XID-with-no-generation-or-global-finality-claim')
                        denied=client._connect({'route':{**route,'user':'xa_denied','use_pure':pure}});denied_cursor=denied.cursor()
                        try:
                            try:adapter.observe(denied_cursor)
                            except Exception as error:
                                assert error.errno==1401 and any(item['code']==1227 for item in error.native_conditions)
                                codes.append({'errno':error.errno,'sqlstate':error.sqlstate,'native_conditions':error.native_conditions})
                            else:raise AssertionError('Unprivileged XA recovery unexpectedly succeeded')
                            denied_catalog=capture(denied)
                            unavailable=next(row for row in denied_catalog['observations'] if row['section']=='prepared-transactions');assert not unavailable['available'] and unavailable['error_code']==1401 and any(item['code']==1227 for item in unavailable['native_conditions'])
                        finally:denied_cursor.close();client._forget_and_close(denied)
                        checks.append('native-XA_RECOVER_ADMIN-denial-is-preserved-and-catalog-section-is-explicitly-unavailable')
                        work.execute('ROLLBACK TO SAVEPOINT xa_guard');work.execute('ROLLBACK')
                        checks.append('independent-pending-transaction-and-savepoint-preserved')
                        expected='CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection';assert classes and set(classes)=={expected}
                        proof['interfaces'].append({'use_pure':pure,'native_connection_class':expected,'checks':checks,'templates':templates,'native_status_codes':codes})
                    finally:work.close();client._forget_and_close(pending);client.close()
                if application:
                    password='native-xa-'+secrets.token_urlsafe(24);query.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                    proof['application']=workspace(output,route,password,query,target)
                proof['complete']=True
            finally:query.close();oracle.close()
        proof['owned_server_stopped']=owned['owned_server_stopped']
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def workspace(output,route,password,oracle,resource):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    from pgadmin.cdeadmin.providers.mysql_family import mysql_xa as adapter
    app=setup_application(output)
    from flask import url_for
    from pgadmin.model import db,User,ServerGroup,Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    client=app.test_client();receipts=[]
    for pure in (True,False):
        with app.test_request_context('/'):
            uid=User.query.first().id;group=ServerGroup.query.filter_by(user_id=uid).first()
            app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
            item=Server(user_id=uid,servergroup_id=group.id,name='Owned native XA '+str(pure),host=route['host'],port=route['port'],username='root',maintenance_db='mysql',save_password=0)
            item._cde_endpoint_registration=registration_profile('mysql-native');item._cde_endpoint_route_configuration={**route,'user':'root','use_pure':pure,'credential_kinds':['database_password']}
            db.session.add(item);db.session.commit();url=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=item.id);verify=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=item.id)
        with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
        assert client.post(verify,json={'password':password}).get_json()['success']
        def post(action,request):
            response=client.post(url,json={'action':action,'request':request});value=response.get_json()
            if response.status_code!=200 or not value.get('success'):
                (output/'application-failure.json').write_text(json.dumps(value,indent=2).replace(password,'<redacted>')+'\n');raise AssertionError('Native XA application failed: '+action)
            return value['data']
        for index,operation in enumerate(adapter.OPERATIONS):
            key=100+(0 if pure else 10)+index;value=adapter.identity({'gtrid_hex':(b'\0\xffAPI'+bytes([key])).hex(),'bqual_hex':'','format_id':'1'})
            draft={}
            if operation!='inspect_prepared_xa':
                seed(oracle,adapter,value,key);draft={key:value[key] for key in ('gtrid_hex','bqual_hex','format_id')}|{'confirmation':'MySQL','decision_reference':'Owned API coordinator decision','lock_wait_seconds':1}
            request={'resource_kind':'server','operation_id':operation,'target_resource':resource,'draft':draft}
            checked=post('visual_admin_validate',request);assert checked['valid'],checked['errors']
            plan=post('visual_admin_plan',request);assert plan['state']=='ready' and plan['execution_available']
            result=post('visual_admin_apply',{key:plan[key] for key in ('plan_id','plan_digest')}|{'confirmed':True})
            assert result['provider_result']['xa_observation']['native_acknowledged']
            receipts.append({'use_pure':pure,'operation':operation,'reviewed_native_acknowledged':True})
    return {'complete':True,'operations':receipts}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--application',action='store_true')
    args=parser.parse_args();value=qualify(args.output,args.application)
    print(json.dumps({'complete':value['complete'],'interfaces':len(value['interfaces'])}))

"""Actual native Community keyring UDF ownership and reviewed key operations."""
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


def qualify(output,application=True):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    app=setup_application(output)
    from mysql_qualification_support import server,_root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE,MYSQL_ADMINISTRATION,_create_client
    from pgadmin.cdeadmin.providers.mysql_family import mysql_user_keys as native
    from pgadmin.cdeadmin.sdk import RelationalClientError
    paths=['web/pgadmin/cdeadmin/providers/mysql_family/'+name for name in ['mysql_user_keys.py','administration.py','provider.py']]
    paths+=['web/pgadmin/cdeadmin/ui_descriptors/mysql/'+name for name in ['operations.json','capabilities.json','forms/table.form.json']]
    paths+=[str(Path(__file__).relative_to(ROOT))]
    proof={'complete':False,'history_testing':'ScratchBird history not run','interfaces':[],
        'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    try:
        with server(output/'fixture',keyring=True) as (route,_container,owned):
            oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;q=oracle.cursor()
            try:
                q.execute('CREATE DATABASE sr_osc');q.execute('CREATE TABLE sr_osc.pending(id INT PRIMARY KEY)')
                q.execute('SELECT @@server_uuid');identity=q.fetchone()[0]
                target={'resource_kind':'server','resource_id':'server:MySQL','display_name':'MySQL','display_path':['MySQL'],'native':{'server_uuid':identity}}
                def read(key):
                    q.execute('SELECT keyring_key_type_fetch(%s),keyring_key_length_fetch(%s),HEX(keyring_key_fetch(%s))',(key,key,key));return q.fetchone()
                for pure in (True,False):
                    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace());classes=[];connect=client._connect
                    def tracked(request):
                        handle=connect(request);classes.append(type(handle).__name__);return handle
                    client._connect=tracked
                    def plan(operation,**draft):return client.plan_admin_operation({'resource_kind':'server','operation_id':operation,'target_resource':target,
                        'draft':{'confirmation':'MySQL',**draft},'_provider_route':{**route,'database':'sr_osc','use_pure':pure}})
                    def apply(operation,**draft):return MYSQL_ADMINISTRATION.apply(client,plan(operation,**draft))
                    prefix='native-key-'+str(int(pure))+'-雪-';material="private quote' slash\\ 雪"
                    try:
                        setup=apply('install_user_key_functions',library='keyring_udf.so',trusted_library=True)
                        assert setup['accepted']
                        q.execute("SELECT PLUGIN_STATUS FROM information_schema.PLUGINS WHERE PLUGIN_NAME='keyring_udf'");assert q.fetchone()==('ACTIVE',)
                        q.execute("SELECT COUNT(*) FROM mysql.func WHERE dl='keyring_udf.so'");assert q.fetchone()==(6,)
                        assert not plan('install_user_key_functions',library='keyring_udf.so',trusted_library=True)['provider_payload']['compiled']['statements']
                        oracle.autocommit=False;q.execute('SAVEPOINT key_guard');q.execute('INSERT INTO sr_osc.pending VALUES(%s)',(int(pure)+1,))
                        reviewed=plan('store_user_key',key_id=prefix+'stored',key_type='SECRET',password=material)
                        assert material not in json.dumps(reviewed['command_preview'])
                        result=MYSQL_ADMINISTRATION.apply(client,reviewed)
                        assert result['accepted'] and result['keyring_observation']['native_key_effect_acknowledged']
                        assert material not in json.dumps(result) and 'private_fingerprint' not in json.dumps(result)
                        q.execute('SELECT ROW_COUNT()');assert q.fetchone()==(1,)
                        assert read(prefix+'stored')==('SECRET',len(material.encode()),material.encode().hex().upper())
                        inspected=apply('inspect_user_key',key_id=prefix+'stored')
                        assert inspected['keyring_observation']['after']=={'key_type':'SECRET','key_length':len(material.encode())}
                        q.execute('ROLLBACK TO SAVEPOINT key_guard');oracle.rollback();oracle.autocommit=True
                        assert read(prefix+'stored')[2]==material.encode().hex().upper()
                        generated=apply('generate_user_key',key_id=prefix+'generated',key_type='AES',key_length=32)
                        assert generated['accepted'] and read(prefix+'generated')[:2]==('AES',32)
                        stale=plan('remove_user_key',key_id=prefix+'stored')
                        q.execute('SELECT keyring_key_remove(%s)',(prefix+'stored',));assert q.fetchone()==(1,)
                        q.execute('SELECT keyring_key_store(%s,%s,%s)',(prefix+'stored','SECRET','externally replaced'));assert q.fetchone()==(1,)
                        try:MYSQL_ADMINISTRATION.apply(client,stale)
                        except RelationalClientError as error:assert error.native_dispatched is False
                        else:raise AssertionError('A changed key was removed using a stale review')
                        assert read(prefix+'stored')[2]==b'externally replaced'.hex().upper()
                        reviewed=plan('store_user_key',key_id=prefix+'lost-observation',key_type='SECRET',password=material)
                        observe=native.observe;calls=0
                        def lost(*args):
                            nonlocal calls
                            calls+=1
                            if calls==2:raise OSError('Owned post-ack observation loss')
                            return observe(*args)
                        with patch.object(native,'observe',lost):
                            try:MYSQL_ADMINISTRATION.apply(client,reviewed)
                            except RelationalClientError as error:assert error.native_dispatched and error.native_acknowledged and error.automatic_retry is False
                            else:raise AssertionError('Post-ack loss was hidden')
                        assert read(prefix+'lost-observation')[2]==material.encode().hex().upper()
                        for suffix in ('stored','generated','lost-observation'):
                            assert apply('remove_user_key',key_id=prefix+suffix)['accepted']
                            assert read(prefix+suffix)==(None,None,None)
                        expected='CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection';assert set(classes)=={expected}
                        proof['interfaces'].append({'native_connection_class':expected,'complete':True,'native_functions_verified':6,
                            'checks':['reviewed-native-plugin-and-six-UDF-registration-with-existing-definitions-preserved','exact-UTF8-store-native-generation-inspection-and-removal',
                                'independent-pending-transaction-savepoint-and-row-count-preserved','native-key-effects-survive-original-query-rollback',
                                'stale-key-fingerprint-refused-before-dispatch','post-native-ack-observation-loss-keeps-ACK-and-never-replays','no-key-material-in-preview-or-receipt']})
                    finally:client.close()
                import mysql.connector
                other_password=secrets.token_urlsafe(24)
                q.execute("CREATE USER 'other_key_owner'@'%' IDENTIFIED BY %s",(other_password,));q.execute("GRANT EXECUTE ON *.* TO 'other_key_owner'@'%'")
                q.execute("SELECT keyring_key_store('same-id','SECRET','first owner')");assert q.fetchone()==(1,)
                other=mysql.connector.connect(host=route['host'],port=route['port'],user='other_key_owner',password=other_password,autocommit=True)
                other_query=other.cursor()
                try:
                    other_query.execute("SELECT keyring_key_fetch('same-id')");assert other_query.fetchone()==(None,)
                    other_query.execute("SELECT keyring_key_store('same-id','SECRET','second owner')");assert other_query.fetchone()==(1,)
                    assert read('same-id')[2]==b'first owner'.hex().upper()
                    other_query.execute("SELECT keyring_key_remove('same-id')");assert other_query.fetchone()==(1,)
                    assert read('same-id')[2]==b'first owner'.hex().upper()
                finally:other_query.close();other.close()
                q.execute("SELECT keyring_key_remove('same-id')");assert q.fetchone()==(1,)
                proof['native_principal_ownership_verified']=True
                if application:
                    password=secrets.token_urlsafe(24);q.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                    proof['application']=workspace(app,route,password,target,q)
                proof['complete']=True
            finally:q.close();oracle.close()
        proof['owned_server_stopped']=owned['owned_server_stopped']
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def workspace(app,route,password,target,oracle):
    from cdeadmin_mysql_online_ddl_qualification import registration
    records=[]
    for pure in (True,False):
        _sid,_target,post=registration(app,route,password,not pure)
        key='api-key-'+str(int(pure));material='private-api-'+secrets.token_urlsafe(12)
        def apply(operation,**draft):
            plan=post('visual_admin_plan',{'resource_kind':'server','operation_id':operation,'target_resource':target,'draft':{'confirmation':'MySQL',**draft}})
            assert plan['state']=='ready' and plan['execution_available'],plan
            assert material not in json.dumps(plan)
            request={key:plan[key] for key in ('plan_id','plan_digest')}|{'confirmed':True}
            result=post('visual_admin_apply',request)
            replay=post.raw('visual_admin_apply',request)
            assert replay.status_code!=200 or not replay.get_json().get('success')
            assert material not in json.dumps(result)
            return result['provider_result']
        configured=apply('install_user_key_functions',library='keyring_udf.so',trusted_library=True)
        assert configured['accepted'] and configured['keyring_observation']['already_configured']
        assert apply('generate_user_key',key_id=key+'-generated',key_type='AES',key_length=32)['accepted']
        oracle.execute('SELECT keyring_key_length_fetch(%s)',(key+'-generated',));assert oracle.fetchone()==(32,)
        assert apply('remove_user_key',key_id=key+'-generated')['accepted']
        assert apply('store_user_key',key_id=key,key_type='SECRET',password=material)['accepted']
        oracle.execute('SELECT HEX(keyring_key_fetch(%s))',(key,));assert oracle.fetchone()==(material.encode().hex().upper(),)
        assert apply('inspect_user_key',key_id=key)['keyring_observation']['after']['key_length']==len(material)
        assert apply('remove_user_key',key_id=key)['accepted']
        records.append({'use_pure':pure,'complete':True,'operations_verified':5,'typed_plan_apply_and_no_replay':True,'secret_not_in_public_plan_or_receipt':True})
    return {'complete':True,'interfaces':records}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    parser.add_argument('--core-only',action='store_true')
    args=parser.parse_args();value=qualify(args.output,not args.core_only);print(json.dumps({'complete':value['complete'],'interfaces':len(value['interfaces'])}))

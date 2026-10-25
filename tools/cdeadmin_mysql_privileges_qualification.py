"""Owned native MySQL9.7 privilege effects, failures and authenticated dispatch."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False);app=setup_application(output)
    from mysql_qualification_support import server,_root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE,MYSQL_ADMINISTRATION,_create_client
    from pgadmin.cdeadmin.providers.mysql_family import mysql_privileges as privileges
    from pgadmin.cdeadmin.providers.mysql_roles import account
    from pgadmin.cdeadmin.sdk import RelationalClientError
    import mysql.connector
    paths=['web/pgadmin/cdeadmin/providers/mysql_family/'+name for name in ('mysql_privileges.py','mysql_accounts.py','mysql_indexes.py','administration.py','provider.py','descriptor_contracts.py')]
    paths+=['web/pgadmin/cdeadmin/providers/mysql_roles.py']
    paths+=['web/pgadmin/cdeadmin/ui_descriptors/mysql/'+name for name in ('forms/role-privilege.form.json','operations.json','capabilities.json')]
    paths+=[str(Path(__file__).relative_to(ROOT))]
    proof={'complete':False,'interfaces':[],'history_testing':'ScratchBird history not run',
        'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}}
    try:
        with server(output/'fixture') as (route,_container,owned):
            oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;q=oracle.cursor()
            try:
                q.execute('CREATE DATABASE sr_osc');q.execute('CREATE TABLE sr_osc.t(id INT, secret INT)');q.execute('INSERT INTO sr_osc.t VALUES(1,9)')
                q.execute('CREATE TABLE sr_osc.pending(id INT PRIMARY KEY)');q.execute('CREATE PROCEDURE sr_osc.p() SELECT 1')
                q.execute('SELECT CURRENT_USER()');grantor_user,grantor_host=q.fetchone()[0].rsplit('@',1)
                q.execute('SELECT @@GLOBAL.sql_mode');original_mode=q.fetchone()[0]
                for pure in (True,False):
                    q.execute('SET GLOBAL sql_mode=%s',(original_mode if pure else 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES',))
                    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace());classes=[];connect=client._connect
                    def tracked(request):
                        handle=connect(request);classes.append(type(handle).__name__);return handle
                    client._connect=tracked;name="priv`'\\@雪"+str(int(pure));pw=secrets.token_urlsafe(20)
                    q.execute('CREATE USER '+account(name,'%')+' IDENTIFIED BY %s',(pw,))
                    recipient={'grantees':[{'user':name,'host':'%'}]};selected={**route,'database':'sr_osc','use_pure':pure}
                    def review(op,draft):return client.plan_admin_operation({'resource_kind':'privilege','operation_id':op,'draft':{**recipient,**draft},'_provider_route':selected})
                    def run(op,draft):
                        try:return MYSQL_ADMINISTRATION.apply(client,review(op,draft))
                        except RelationalClientError as error:
                            raise AssertionError('Native privilege operation failed: '+op+' scope='+draft.get('object_type','?')+' errno='+str(getattr(error,'errno',None))) from error
                    def permitted(sql,expected=None):
                        handle=mysql.connector.connect(host=route['host'],port=route['port'],user=name,password=pw,use_pure=pure,autocommit=True)
                        try:
                            cursor=handle.cursor()
                            try:cursor.execute(sql);result=cursor.fetchall() if cursor.description else None
                            except mysql.connector.Error as error:
                                if expected is None:raise
                                assert error.errno in expected,error.errno
                            else:
                                if expected is not None:raise AssertionError('Native privilege unexpectedly allowed SQL')
                                return result
                            finally:cursor.close()
                        finally:handle.close()
                    try:
                        column={'object_type':'TABLE','database':'sr_osc','object':'t','privileges':[{'name':'SELECT','columns':['id']}]}
                        planned=review('grant',column)
                        oracle.autocommit=False;q.execute('SAVEPOINT privilege_guard');q.execute('INSERT INTO sr_osc.pending VALUES(%s)',(int(pure)+1,))
                        result=MYSQL_ADMINISTRATION.apply(client,planned);assert result['accepted'] and result['privilege_observation']['native_acknowledged']
                        q.execute('SELECT ROW_COUNT()');assert q.fetchone()==(1,);q.execute('ROLLBACK TO SAVEPOINT privilege_guard');oracle.rollback();oracle.autocommit=True
                        assert permitted('SELECT id FROM sr_osc.t')==[(1,)];permitted('SELECT secret FROM sr_osc.t',expected={1142,1143})
                        dynamic={'object_type':'GLOBAL','privileges':[{'name':'BACKUP_ADMIN'}]};run('grant',dynamic)
                        q.execute('SELECT PRIV FROM mysql.global_grants WHERE USER=%s AND HOST=%s',(name,'%'));assert ('BACKUP_ADMIN',) in q.fetchall()
                        routine={'object_type':'PROCEDURE','database':'sr_osc','object':'p','privileges':[{'name':'EXECUTE'}]};run('grant',routine);run('revoke',routine)
                        proxy={'object_type':'PROXY','proxy_user':grantor_user,'proxy_host':grantor_host,'grant_option':True};run('grant',proxy)
                        q.execute('SELECT With_grant FROM mysql.proxies_priv WHERE User=%s AND Host=%s AND Proxied_user=%s AND Proxied_host=%s',(name,'%',grantor_user,grantor_host));assert q.fetchone()==(1,)
                        run('revoke',{k:v for k,v in proxy.items() if k!='grant_option'})
                        role='owned_grantor_role_'+str(int(pure));q.execute('CREATE ROLE '+account(role,'%'))
                        q.execute('GRANT '+account(role,'%')+' TO '+account(grantor_user,grantor_host))
                        for mode in ('NONE','DEFAULT','ALL','SELECTED','ALL_EXCEPT'):
                            run('grant',{'object_type':'GLOBAL','privileges':[{'name':'UPDATE'}],
                                'grant_as_user':grantor_user,'grant_as_host':grantor_host,'grant_as_roles_mode':mode,
                                **({'grant_as_roles':[{'user':role,'host':'%'}]} if mode in {'SELECTED','ALL_EXCEPT'} else {})})
                        second=role+'_second';q.execute('CREATE ROLE '+account(second,'%'))
                        q.execute('GRANT '+account(role,'%')+','+account(second,'%')+' TO '+account(name,'%'))
                        target={'display_name':role+'@%','native':{'user':role,'host':'%'}}
                        for mode in ('SELECTED','ALL','NONE'):
                            draft={'member_user':name,'member_host':'%','mode':mode}
                            if mode=='SELECTED':draft['roles']=[{'user':role,'host':'%'},{'user':second,'host':'%'}]
                            planned=client.plan_admin_operation({'resource_kind':'role','operation_id':'set_default','draft':draft,'target_resource':target,'_provider_route':selected})
                            assert MYSQL_ADMINISTRATION.apply(client,planned)['accepted']
                            q.execute('SELECT COUNT(*) FROM mysql.default_roles WHERE USER=%s AND HOST=%s',(name,'%'));assert q.fetchone()==(0 if mode=='NONE' else 2,)
                        stale=review('revoke',column);q.execute('GRANT INSERT ON sr_osc.t TO '+account(name,'%'))
                        try:MYSQL_ADMINISTRATION.apply(client,stale)
                        except RelationalClientError as error:assert error.native_dispatched is False
                        else:raise AssertionError('Stale grant review dispatched')
                        # A successful DCL followed by observation loss must not replay.
                        fault=review('revoke',column);observe=privileges.observe;calls=0
                        def lost(cursor,intent):
                            nonlocal calls
                            calls+=1
                            if calls==2:raise OSError('owned post-ack observation fault')
                            return observe(cursor,intent)
                        privileges.observe=lost
                        try:
                            try:MYSQL_ADMINISTRATION.apply(client,fault)
                            except RelationalClientError as error:assert error.native_acknowledged and not error.automatic_retry
                            else:raise AssertionError('Observation fault was swallowed')
                        finally:privileges.observe=observe
                        permitted('SELECT id FROM sr_osc.t',expected={1142,1143})
                        invalid=review('grant',{'object_type':'GLOBAL','privileges':[{'name':'OWNED_UNREGISTERED_PRIVILEGE'}]})
                        try:MYSQL_ADMINISTRATION.apply(client,invalid)
                        except RelationalClientError as error:assert type(error.errno) is int and error.sqlstate and error.native_dispatched and not error.native_acknowledged and not error.automatic_retry
                        else:raise AssertionError('Unknown dynamic privilege was accepted')
                        policy_stale=review('grant',{'object_type':'GLOBAL','privileges':[{'name':'SELECT'}]})
                        q.execute('SET GLOBAL partial_revokes=ON')
                        # The second connector starts with partial revokes on;
                        # change it for this refusal rather than asserting drift
                        # from an identical value.
                        q.execute('SET GLOBAL partial_revokes=OFF')
                        q.execute('SELECT @@GLOBAL.partial_revokes');current=bool(q.fetchone()[0])
                        previous=policy_stale['provider_payload']['compiled']['mysql_privilege_change']['review']['identity']['partial_revokes']
                        if current==previous:q.execute('SET GLOBAL partial_revokes=ON')
                        try:MYSQL_ADMINISTRATION.apply(client,policy_stale)
                        except RelationalClientError as error:assert error.native_dispatched is False
                        else:raise AssertionError('Changed partial-revoke interpretation dispatched')
                        q.execute('SET GLOBAL partial_revokes=ON')
                        run('grant',{'object_type':'GLOBAL','privileges':[{'name':'SELECT'}]})
                        run('revoke',{'object_type':'DATABASE','database':'sr_osc','privileges':[{'name':'SELECT'}]})
                        permitted('SELECT id FROM sr_osc.t',expected={1142,1143})
                        q.execute("SELECT JSON_EXTRACT(User_attributes,'$.Restrictions') FROM mysql.user WHERE User=%s AND Host=%s",(name,'%'));assert q.fetchone()[0] is not None
                        run('revoke',{'object_type':'ACCOUNT'})
                        result=run('revoke',{'grantees':[{'user':'owned_absent','host':'%'}],'object_type':'GLOBAL','privileges':[{'name':'SELECT'}],'if_exists':True,'ignore_unknown_user':True})
                        assert result['accepted'] and result['native_warnings']
                        expected='CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection';assert set(classes)=={expected}
                        proof['interfaces'].append({'native_connection_class':expected,'complete':True,'column_scope_real_allow_and_denial':True,
                            'dynamic_routine_proxy_and_grant_as':True,'multiple_selected_all_and_no_default_roles':True,'native_partial_revoke_restrictions':True,'changed_partial_revoke_policy_refused':True,'native_unregistered_dynamic_privilege_error_retained':True,'all_privileges_and_missing_user_warnings':True,
                            'stale_review_refused':True,'post_ack_observation_loss_not_replayed':True,'source_diagnostics_and_savepoint_preserved':True})
                    finally:client.close()
                q.execute('SET GLOBAL sql_mode=%s',(original_mode,));password=secrets.token_urlsafe(24);q.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                proof['application']=workspace(app,route,password,q);proof['complete']=True
            finally:q.close();oracle.close()
        proof['owned_server_stopped']=owned['owned_server_stopped']
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def workspace(app,route,password,q):
    from cdeadmin_mysql_online_ddl_qualification import registration
    from pgadmin.cdeadmin.providers.mysql_roles import account
    results=[]
    for pure in (True,False):
        _sid,_target,post=registration(app,route,password,not pure);name='api_privilege_'+str(int(pure))
        q.execute('CREATE USER '+account(name,'%'))
        target={'resource_kind':'privilege','resource_id':'owned-grant','display_name':name+'@%'}
        for op in ('grant','revoke'):
            draft={'grantees':[{'user':name,'host':'%'}],'object_type':'TABLE','database':'sr_osc','object':'t',
                'privileges':[{'name':'SELECT','columns':['id']}],'confirmation':target['display_name']}
            planned=post('visual_admin_plan',{'resource_kind':'privilege','operation_id':op,'draft':draft,'target_resource':target})
            assert planned['state']=='ready' and planned['execution_available'],planned
            request={key:planned[key] for key in ('plan_id','plan_digest')}|{'confirmed':True}
            result=post('visual_admin_apply',request);assert result['provider_result']['accepted']
            q.execute('SELECT Column_priv FROM mysql.columns_priv WHERE User=%s AND Host=%s AND Db=%s AND Table_name=%s AND Column_name=%s',(name,'%','sr_osc','t','id'))
            row=q.fetchone();assert (row is not None)==(op=='grant')
            replay=post.raw('visual_admin_apply',request);assert replay.status_code!=200 or not replay.get_json().get('success')
        results.append({'use_pure':pure,'typed_authenticated_column_grant_revoke_and_effect':True,'consumed_plan_refused':True})
    return {'complete':True,'interfaces':results}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    result=qualify(parser.parse_args().output);print(json.dumps({'complete':result['complete'],'interfaces':len(result['interfaces'])}))

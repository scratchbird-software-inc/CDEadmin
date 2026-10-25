"""Native MySQL account policy, plugin authentication, TLS and API evidence."""
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


def qualify(output):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False);app=setup_application(output)
    from mysql_qualification_support import server,_root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE,MYSQL_ADMINISTRATION,_create_client,_resources
    from pgadmin.cdeadmin.providers.mysql_family import mysql_accounts as accounts
    from pgadmin.cdeadmin.sdk import RelationalClientError
    from cdeadmin_mysql_physical_tls_qualification import certificates
    import mysql.connector
    paths=['web/pgadmin/cdeadmin/providers/mysql_family/'+name for name in ('mysql_accounts.py','administration.py','provider.py','descriptor_contracts.py')]
    paths+=['web/pgadmin/cdeadmin/ui_descriptors/mysql/'+name for name in ('forms/role-user.form.json','capabilities.json')]
    paths+=['web/pgadmin/cdeadmin/visual_admin/provider.py',str(Path(__file__).relative_to(ROOT))]
    proof={'complete':False,'interfaces':[],'history_testing':'ScratchBird history not run',
           'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}}
    try:
        with server(output/'fixture') as (route,container,owned):
            oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;q=oracle.cursor()
            try:
                q.execute('CREATE DATABASE sr_osc');q.execute('CREATE TABLE sr_osc.pending(id INT PRIMARY KEY)')
                q.execute("CREATE USER 'sr_physical'@'%' IDENTIFIED BY 'owned-temporary-setup'")
                client_tls,_paths=certificates(output,container,oracle)
                q.execute('SELECT @@GLOBAL.sql_mode');original_mode=q.fetchone()[0]
                q.execute("SELECT PLUGIN_STATUS FROM information_schema.PLUGINS WHERE PLUGIN_NAME='auth_socket'")
                if q.fetchone() is None:q.execute("INSTALL PLUGIN auth_socket SONAME 'auth_socket.so'")
                for pure in (True,False):
                    q.execute('SET GLOBAL sql_mode=%s',(original_mode if pure else 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES',))
                    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace())
                    selected={**route,'database':'sr_osc','use_pure':pure};name='native_雪@'+str(int(pure));host='%';pw=secrets.token_urlsafe(20)+'雪'
                    target={'resource_kind':'user','resource_id':'owned-account','display_name':name+'@'+host,'display_path':[name+'@'+host],'native':{'user':name,'host':host}}
                    connect=client._connect;classes=[]
                    def tracked(request):
                        handle=connect(request);classes.append(type(handle).__name__);return handle
                    client._connect=tracked
                    def review(operation,draft):return client.plan_admin_operation({'resource_kind':'user','operation_id':operation,'draft':draft,'target_resource':target,'_provider_route':selected})
                    def execute(operation,draft):return MYSQL_ADMINISTRATION.apply(client,review(operation,draft))
                    def login(password,*,tls=None,expect=None,user=name):
                        arguments={'host':route['host'],'port':route['port'],'user':user,'password':password,'use_pure':pure,'autocommit':True}
                        if tls is not None:arguments.update(tls)
                        try:handle=mysql.connector.connect(**arguments)
                        except mysql.connector.Error as error:
                            if expect is None:raise
                            assert error.errno in expect,(type(error).__name__,error.errno);return error.errno
                        else:
                            try:
                                if expect is not None:raise AssertionError('Native login unexpectedly succeeded')
                                cursor=handle.cursor();cursor.execute('SELECT CURRENT_USER()');identity=cursor.fetchone()[0];cursor.close();assert identity==user+'@%'
                            finally:handle.close()
                    try:
                        draft={'name':name,'host':host,'password':pw,'plugin':'caching_sha2_password','tls_mode':'NONE',
                            'max_queries_per_hour':4294967295,'max_updates_per_hour':0,'max_connections_per_hour':0,'max_user_connections':0,
                            'password_expire':'NEVER','password_history':2,'password_reuse_days':3,'password_require_current':'OPTIONAL',
                            'failed_login_attempts':2,'password_lock_time':0,'comment':"native quote' 雪"}
                        planned=review('create',draft)
                        assert pw not in str(planned['command_preview']) and 'private_fingerprint' not in str(planned['command_preview'])
                        oracle.autocommit=False;q.execute('SAVEPOINT account_guard');q.execute('INSERT INTO sr_osc.pending VALUES(%s)',(int(pure)+1,))
                        result=MYSQL_ADMINISTRATION.apply(client,planned);assert result['accepted'] and result['account_observation']['native_acknowledged']
                        q.execute('SELECT ROW_COUNT()');assert q.fetchone()==(1,)
                        q.execute('ROLLBACK TO SAVEPOINT account_guard');oracle.rollback();oracle.autocommit=True
                        login(pw)
                        q.execute('SELECT plugin,max_questions,password_lifetime,password_reuse_history,password_reuse_time,password_require_current FROM mysql.user WHERE User=%s AND Host=%s',(name,host))
                        assert q.fetchone()==('caching_sha2_password',4294967295,0,2,3,'N')
                        execute('alter',{'attributes':{'literal':"quote' 雪",'exact':9007199254740993}})
                        q.execute("SELECT JSON_EXTRACT(User_attributes,'$.metadata.exact') FROM mysql.user WHERE User=%s AND Host=%s",(name,host));assert str(q.fetchone()[0])=='9007199254740993'
                        handle=client._connect({'route':selected})
                        try:
                            rows=_resources(handle,{'route':selected},MYSQL_PROFILE);node=next(row for row in rows if row['resource_kind']=='user' and row['native'].get('user')==name)
                            facts=node['native'];assert facts['authentication_plugin']=='caching_sha2_password' and facts['max_queries_per_hour']==4294967295
                            assert facts['metadata_attributes']['exact']==9007199254740993 and facts['authentication_secrets_returned'] is False
                            assert not {'authentication_string','additional_password','multi_factor_authentication'}&facts.keys()
                        finally:client._forget_and_close(handle)
                        new_pw=secrets.token_urlsafe(20)+'雪';execute('alter',{'password':new_pw,'retain_current_password':True});login(pw);login(new_pw)
                        execute('alter',{'discard_old_password':True});login(pw,expect={1045});login(new_pw)
                        execute('alter',{'account_lock':'LOCK'});login(new_pw,expect={3118,1045})
                        execute('alter',{'account_lock':'UNLOCK','tls_mode':'SSL'});login(new_pw);login(new_pw,tls={'ssl_disabled':True},expect={1045})
                        execute('alter',{'tls_mode':'X509'});login(new_pw,expect={1045});login(new_pw,tls=client_tls)
                        exact_tls={**client_tls,'tls_versions':['TLSv1.2'],'ssl_cipher':'ECDHE-RSA-AES128-GCM-SHA256'}
                        execute('alter',{'tls_mode':'SPECIFIED','tls_cipher':'ECDHE-RSA-AES128-GCM-SHA256','tls_issuer':'/CN=Owned native physical CA','tls_subject':'/CN=Owned physical client'})
                        login(new_pw,tls=exact_tls)
                        execute('alter',{'tls_mode':'NONE','password_expire':'IMMEDIATE'});login(new_pw,expect={1820,1862})
                        final_pw=secrets.token_urlsafe(20);execute('alter',{'password':final_pw,'password_expire':'DEFAULT','password_history':'DEFAULT','password_reuse_days':'DEFAULT','password_require_current':'DEFAULT'});login(final_pw)
                        q.execute('SELECT password_expired,password_lifetime,password_reuse_history,password_reuse_time,password_require_current FROM mysql.user WHERE User=%s AND Host=%s',(name,host));assert q.fetchone()==('N',None,None,None,None)
                        # Hash/string and plugin-only authentication are native,
                        # distinct from the ordinary default password path.
                        q.execute('SELECT authentication_string FROM mysql.user WHERE User=%s AND Host=%s',(name,host));native_hash=q.fetchone()[0]
                        clone=name+'_hash';execute('create',{'name':clone,'host':'%','authentication_mode':'AUTHENTICATION_STRING','plugin':'caching_sha2_password','authentication_string':native_hash});login(final_pw,user=clone)
                        renamed="renamed`'\\@雪"+str(int(pure))
                        rename_target={'display_name':clone+'@%','native':{'user':clone,'host':'%'}}
                        planned=client.plan_admin_operation({'resource_kind':'user','operation_id':'rename','draft':{'new_name':renamed},'target_resource':rename_target,'_provider_route':selected})
                        assert MYSQL_ADMINISTRATION.apply(client,planned)['accepted'];login(final_pw,user=renamed)
                        drop_target={'display_name':renamed+'@%','native':{'user':renamed,'host':'%'}}
                        planned=client.plan_admin_operation({'resource_kind':'user','operation_id':'drop','draft':{},'target_resource':drop_target,'_provider_route':selected})
                        assert MYSQL_ADMINISTRATION.apply(client,planned)['accepted'];login(final_pw,user=renamed,expect={1045})
                        socket_name=name+'_socket';execute('create',{'name':socket_name,'host':'%','authentication_mode':'AUTHENTICATION_STRING','plugin':'auth_socket','authentication_string':'root'})
                        q.execute('SELECT plugin,authentication_string FROM mysql.user WHERE User=%s AND Host=%s',(socket_name,'%'));assert q.fetchone()==('auth_socket','root')
                        login('',user=socket_name,expect={1698,1045});socket_login(output,container,socket_name,None)
                        mfa_name=name+'_mfa';mfa_password=secrets.token_urlsafe(20)
                        execute('create',{'name':mfa_name,'password':mfa_password,'authentication_factors':[{'mode':'AUTHENTICATION_STRING','plugin':'auth_socket','authentication_string':'root'}]})
                        socket_login(output,container,mfa_name,mfa_password);login(mfa_password,user=mfa_name,expect={1045,1698})
                        mfa_target={'native':{'user':mfa_name,'host':'%'},'display_name':mfa_name+'@%'}
                        def mfa_change(rows):
                            planned=client.plan_admin_operation({'resource_kind':'user','operation_id':'alter','draft':{'factor_actions':rows},'target_resource':mfa_target,'_provider_route':selected})
                            return MYSQL_ADMINISTRATION.apply(client,planned)
                        mfa_change([{'action':'MODIFY','factor':2,'mode':'AUTHENTICATION_STRING','plugin':'auth_socket','authentication_string':'owned_missing_os_user'}])
                        socket_login(output,container,mfa_name,mfa_password,expect_failure=True)
                        mfa_change([{'action':'MODIFY','factor':2,'mode':'AUTHENTICATION_STRING','plugin':'auth_socket','authentication_string':'root'}]);socket_login(output,container,mfa_name,mfa_password)
                        mfa_change([{'action':'ADD','factor':3,'mode':'AUTHENTICATION_STRING','plugin':'auth_socket','authentication_string':'root'}]);socket_login(output,container,mfa_name,mfa_password)
                        handle=client._connect({'route':selected})
                        try:
                            rows=_resources(handle,{'route':selected},MYSQL_PROFILE);facts=next(row['native'] for row in rows if row['resource_kind']=='user' and row['native'].get('user')==mfa_name)
                            assert facts['factor_catalog_state']=='observed' and [row['factor'] for row in facts['authentication_factors']]==[2,3]
                            assert all(row['plugin']=='auth_socket' and 'authentication_string' not in row for row in facts['authentication_factors'])
                        finally:client._forget_and_close(handle)
                        mfa_change([{'action':'DROP','factor':2},{'action':'DROP','factor':3}]);login(mfa_password,user=mfa_name)
                        # Confirm native role accounts remain visible as users.
                        role='native_role_'+str(int(pure))
                        def role_create(role_name,members=None):
                            planned=client.plan_admin_operation({'resource_kind':'role','operation_id':'create','draft':{'name':role_name,'host':'%','members':members or []},'_provider_route':selected})
                            return MYSQL_ADMINISTRATION.apply(client,planned)
                        role_create(role,[{'user':name,'host':host}])
                        empty_role=role+'_empty';role_create(empty_role)
                        partial_role=role+'_partial'
                        try:role_create(partial_role,[{'user':'owned_missing_role_member','host':'%'}])
                        except RelationalClientError as error:
                            assert error.native_dispatched and error.native_acknowledged and len(error.native_acknowledgements)==1 and error.automatic_retry is False
                            q.execute('SELECT COUNT(*) FROM mysql.user WHERE User=%s AND Host=%s',(partial_role,'%'));assert q.fetchone()==(1,)
                        else:raise AssertionError('Missing initial member did not retain partial native outcome')
                        execute('create',{'name':name+'_roles','password':secrets.token_urlsafe(20),'default_roles':[{'user':role,'host':'%'}]})
                        q.execute('SELECT COUNT(*) FROM mysql.default_roles WHERE USER=%s AND HOST=%s AND DEFAULT_ROLE_USER=%s AND DEFAULT_ROLE_HOST=%s',(name+'_roles','%',role,'%'));assert q.fetchone()==(1,)
                        q.execute('SELECT COUNT(*) FROM mysql.role_edges WHERE TO_USER=%s AND TO_HOST=%s AND FROM_USER=%s AND FROM_HOST=%s',(name+'_roles','%',role,'%'));assert q.fetchone()==(1,)
                        handle=client._connect({'route':selected})
                        try:
                            rows=_resources(handle,{'route':selected},MYSQL_PROFILE)
                            assert any(row['resource_kind']=='role' and row['native'].get('user')==role for row in rows)
                            assert any(row['resource_kind']=='role' and row['native'].get('user')==empty_role and not row['native']['role_usage_observed'] for row in rows)
                            assert any(row['resource_kind']=='user' and row['native'].get('user')==role and row['native']['role_usage_observed'] for row in rows)
                        finally:client._forget_and_close(handle)
                        stale=review('alter',{'comment':'stale'});q.execute('ALTER USER '+accounts.account(name,host)+' ACCOUNT LOCK')
                        try:MYSQL_ADMINISTRATION.apply(client,stale)
                        except RelationalClientError as error:assert not error.native_dispatched
                        else:raise AssertionError('Stale account state admitted')
                        q.execute('ALTER USER '+accounts.account(name,host)+' ACCOUNT UNLOCK')
                        try:execute('alter',{'authentication_mode':'PLUGIN','plugin':'owned_missing_authentication'})
                        except RelationalClientError as error:assert error.native_dispatched and not error.native_acknowledged and error.errno==1524
                        else:raise AssertionError('Missing native authentication plugin accepted')
                        planned=review('alter',{'comment':'observed after ACK'});original=accounts.observe;calls=0
                        def lost(*args):
                            nonlocal calls
                            calls+=1
                            if calls==2:raise OSError('Owned post-ack observation loss')
                            return original(*args)
                        with patch.object(accounts,'observe',lost):
                            try:MYSQL_ADMINISTRATION.apply(client,planned)
                            except RelationalClientError as error:assert error.native_dispatched and error.native_acknowledged and error.automatic_retry is False
                            else:raise AssertionError('Lost observation hid account ACK')
                        q.execute("SELECT JSON_UNQUOTE(JSON_EXTRACT(User_attributes,'$.metadata.comment')) FROM mysql.user WHERE User=%s AND Host=%s",(name,host));assert q.fetchone()==('observed after ACK',)
                        global_plan=client.plan_admin_operation({'resource_kind':'user','operation_id':'alter','draft':{'comment':'global maintenance context'},'target_resource':target,'_provider_route':{**selected,'database':'owned_missing_default_database'}})
                        assert MYSQL_ADMINISTRATION.apply(client,global_plan)['accepted']
                        expected='CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection';assert set(classes)=={expected}
                        proof['interfaces'].append({'native_connection_class':expected,'complete':True,'unicode_native_login':True,'explicit_plugin_and_hash_authentication':True,
                            'auth_socket_metadata_and_native_tcp_refusal':True,'native_unix_socket_login':True,'available_gpl_second_third_factor_create_modify_add_drop_and_enforcement':True,'native_initial_role_grants_and_partial_failure':True,'native_quote_backslash_unicode_rename_and_drop':True,'dual_password_retain_and_discard':True,'ssl_x509_and_exact_certificate_cipher_policies':True,
                            'lock_expiry_and_default_policy_restoration':True,'uint32_limits_and_exact_json_attributes':True,'full_nonsecret_catalog_and_role_account_discovery':True,
                            'source_row_count_transaction_and_savepoint_preserved':True,'stale_review_refused':True,'missing_plugin_native_error_preserved':True,'post_ack_loss_never_replayed':True})
                    finally:client.close()
                q.execute('SET GLOBAL sql_mode=%s',(original_mode,));password=secrets.token_urlsafe(24);q.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                proof['application']=workspace(app,route,password,q);proof['complete']=True
            finally:q.close();oracle.close()
        proof['owned_server_stopped']=owned['owned_server_stopped']
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def socket_login(output,container,user,password,expect_failure=False):
    import os,subprocess
    token=secrets.token_hex(6);local=output/('private-client-'+token+'.cnf');remote='/tmp/owned-client-'+token+'.cnf'
    def quote(value):return '"'+value.replace('\\','\\\\').replace('"','\\"')+'"'
    data='[client]\nuser='+quote(user)+'\nprotocol=SOCKET\nssl-mode=DISABLED\ndefault-character-set=utf8mb4\n'
    if password is not None:data+='password='+quote(password)+'\n'
    descriptor=os.open(local,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'w') as handle:handle.write(data)
    try:
        subprocess.run(['docker','cp',str(local),container+':'+remote],check=True,capture_output=True)
        subprocess.run(['docker','exec',container,'chmod','600',remote],check=True,capture_output=True)
        result=subprocess.run(['docker','exec','--user','0',container,'mysql','--defaults-file='+remote,'--batch','--skip-column-names','--execute','SELECT CURRENT_USER()'],capture_output=True,text=True)
        if expect_failure:assert result.returncode!=0
        else:assert result.returncode==0 and result.stdout.strip()==user+'@%',(result.returncode,result.stderr)
    finally:
        local.unlink(missing_ok=True)
        subprocess.run(['docker','exec',container,'rm','-f',remote],check=True,capture_output=True)


def workspace(app,route,password,q):
    from cdeadmin_mysql_online_ddl_qualification import registration
    results=[]
    for pure in (True,False):
        _sid,_target,post=registration(app,route,password,not pure);name='api_account_'+str(int(pure));pw=secrets.token_urlsafe(20)
        target={'resource_kind':'user','resource_id':'user:'+name+'@%','display_name':name+'@%','display_path':[name+'@%'],'native':{'user':name,'host':'%'}}
        def run(operation,draft,kind='user',selected_target=None):
            planned=post('visual_admin_plan',{'resource_kind':kind,'operation_id':operation,'draft':draft,'target_resource':selected_target or target})
            assert planned['state']=='ready' and planned['execution_available'] and pw not in str(planned)
            request={key:planned[key] for key in ('plan_id','plan_digest')}|{'confirmed':True}
            value=post('visual_admin_apply',request);assert value['provider_result']['accepted']
            replay=post.raw('visual_admin_apply',request);assert replay.status_code!=200 or not replay.get_json().get('success')
        run('create',{'name':name,'password':pw,'plugin':'caching_sha2_password','max_user_connections':3})
        run('alter',{'comment':'only comment','confirmation':target['display_name']})
        q.execute('SELECT plugin,account_locked,max_user_connections FROM mysql.user WHERE User=%s AND Host=%s',(name,'%'));assert q.fetchone()==('caching_sha2_password','N',3)
        role='api_role_'+str(int(pure));role_target={'resource_kind':'role','resource_id':'role:'+role+'@%','display_name':role+'@%','native':{'user':role,'host':'%'}}
        run('create',{'name':role,'host':'%'},kind='role',selected_target=role_target)
        run('grant',{'member_user':name,'member_host':'%','admin_option':True,'confirmation':role+'@%'},kind='role',selected_target=role_target)
        q.execute('SELECT WITH_ADMIN_OPTION FROM mysql.role_edges WHERE FROM_USER=%s AND FROM_HOST=%s AND TO_USER=%s AND TO_HOST=%s',(role,'%',name,'%'));assert q.fetchone()==('Y',)
        run('set_default',{'member_user':name,'member_host':'%','mode':'SELECTED','confirmation':role+'@%'},kind='role',selected_target=role_target)
        renamed=name+'_renamed';run('rename',{'new_name':renamed,'confirmation':name+'@%'})
        new_target={'resource_kind':'user','resource_id':'user:'+renamed+'@%','display_name':renamed+'@%','native':{'user':renamed,'host':'%'}}
        q.execute('SELECT COUNT(*) FROM mysql.role_edges WHERE FROM_USER=%s AND TO_USER=%s',(role,renamed));assert q.fetchone()==(1,)
        q.execute('SELECT COUNT(*) FROM mysql.default_roles WHERE USER=%s AND DEFAULT_ROLE_USER=%s',(renamed,role));assert q.fetchone()==(1,)
        run('set_default',{'member_user':renamed,'member_host':'%','mode':'NONE','confirmation':role+'@%'},kind='role',selected_target=role_target)
        run('revoke',{'member_user':renamed,'member_host':'%','confirmation':role+'@%'},kind='role',selected_target=role_target)
        run('drop',{'confirmation':renamed+'@%'},selected_target=new_target)
        run('drop',{'confirmation':role+'@%'},kind='role',selected_target=role_target)
        q.execute('SELECT COUNT(*) FROM mysql.user WHERE User IN (%s,%s)',(renamed,role));assert q.fetchone()==(0,)
        results.append({'role_create_grant_defaults_revoke_and_drop':True,'rename_preserves_membership_defaults':True,'typed_plan_apply_and_effect':True,'use_pure':pure,'password_never_in_preview':True,'comment_only_preserves_policies':True,'replay_refused':True})
    return {'complete':True,'interfaces':results}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    args=parser.parse_args();result=qualify(args.output);print(json.dumps({'complete':result['complete'],'interfaces':len(result['interfaces'])}))

"""Native private recovery driver/editor connection acceptance."""
import argparse
import json
from pathlib import Path
import time


def endpoint(app,sid):
    from flask import url_for
    from pgadmin.model import Server
    with app.test_request_context('/'):
        item=Server.query.get(sid)
        return url_for('NODE-server.cde_workspace_id',gid=item.servergroup_id,sid=sid)


def query_post(client,url,target,action,**body):
    reply=client.post(url,json={'action':action,'database_target_id':target,**body});data=reply.get_json()
    assert reply.status_code==200 and data.get('success'),data
    return data['data']


def execute(post,session,source):
    value=post('execute',session_id=session,source=source,parameters=[],history_sensitive=True)
    limit=time.monotonic()+45;rows=[]
    while time.monotonic()<limit:
        result=post('poll',occurrence_id=value['occurrence_id'])
        payload=result['occurrence'].get('result',{}).get('extensions',{}).get('mysql',{}).get('payload',{})
        if payload.get('has_page'):rows.extend(payload.get('rows',[]))
        if result['occurrence']['operation']['terminal']:
            error=payload.get('error')
            assert not error,error
            rendered=result.get('rendered_result') or {}
            return {'rows':rows,'rendered':rendered}
        time.sleep(.03)
    raise TimeoutError('Private recovery editor statement did not finish')


def native_connection(app,client,sid,target,runtime,physical,credentials,output,use_c):
    from pgadmin.model import Server
    source_url=endpoint(app,sid)
    source_post=lambda action,**body:query_post(client,source_url,target,action,**body)
    session=source_post('open_session',language_profile='mysql-sql')['session_id'];checks=[]
    try:
        execute(source_post,session,'START TRANSACTION')
        execute(source_post,session,'INSERT INTO pending VALUES(700)')
        execute(source_post,session,'SAVEPOINT recovery_source_guard')
        review=physical('connection_review',{'job_id':runtime['job_id'],'name':'Recovered native '+str(use_c),'credentials':credentials})
        request={'review_id':review['job_id'],'review_digest':review['review_digest'],'confirmed':True,'delegate_database_credentials':True,'credentials':credentials}
        physical('connection_connect',{**request,'confirmed':False},refused=True)
        physical('connection_connect',{**request,'delegate_database_credentials':False},refused=True)
        # Registration metadata commits before the original connection receipt.
        # Losing that receipt must leave one observable registration, followed
        # by an explicit fresh attachment rather than a second creation.
        from unittest.mock import patch
        from pgadmin.cdeadmin.workspace import mysql_recovery_connections as registrations
        with patch.object(registrations,'registration',side_effect=RuntimeError('owned lost reply')):
            physical('connection_connect',request,refused=True)
        lost=physical('connection_status',{'review_id':review['job_id']})
        assert lost['state']=='unknown' and len(lost['registration_observation'])==1
        original_id=lost['registration_observation'][0]['server_id']
        assert physical('connection_connect',request)['state']=='unknown'
        review=physical('connection_review',{'job_id':runtime['job_id'],'name':'Reattach original recovery','credentials':credentials})
        request={**request,'review_id':review['job_id'],'review_digest':review['review_digest']}
        value=physical('connection_connect',request)
        if not value.get('result'):
            (output/'connection-failure.json').write_text(json.dumps(value,indent=2)+'\n');raise RuntimeError('Native recovery registration did not return')
        attached=value['result'];assert attached['transport_attached'] and attached['verification_state']=='verified' and attached['server_id']==original_id
        assert physical('connection_connect',request)['result']['server_id']==attached['server_id']
        observed=physical('connection_status',{'review_id':review['job_id']})
        assert len(observed['registration_observation'])==1
        target_url=endpoint(app,attached['server_id']);target_id=attached['database_target_id']
        post=lambda action,**body:query_post(client,target_url,target_id,action,**body)
        recovered=post('open_session',language_profile='mysql-sql')['session_id']
        try:
            rows=execute(post,recovered,'SELECT CAST(id AS CHAR),note,HEX(b),@@server_uuid FROM t')['rows']
            assert rows[0][:3]==['18446744073709551615','native 雪','00FF'] and rows[0][3]==runtime['remote_observation']['sql_identity']['server_uuid']
            completion=post('source_complete',session_id=recovered,source='SELECT t.',source_before_cursor='SELECT t.')
            assert completion.get('editor_context')
            execute(post,recovered,'START TRANSACTION')
            execute(post,recovered,'SELECT COUNT(*) FROM t')
            physical('connection_detach',{'server_id':attached['server_id']},refused=True)
            execute(post,recovered,'ROLLBACK')
        finally:post('close_session',session_id=recovered)
        # Native connector type, exact binary values and explicit reconnect keep
        # the original driver implementation and its protocol semantics.
        with app.test_request_context('/'):
            from flask_login import login_user
            from pgadmin.model import User
            service=app.extensions['cdeadmin_provider_workspace']
            registered=Server.query.get(attached['server_id'])
            login_user(User.query.get(registered.user_id))
            context,payload,_=service.endpoint_service.workspace(registered,database_target_id=target_id)
            provider=service.endpoint_service.provider_registry.resolve(context).instance
            from pgadmin.cdeadmin.providers.mysql_family.mysql_recovery_bridge import native_connection as native_connect
            try:
                refused=native_connect(provider.client.module.connect,(),{
                    'host':'managed-recovery.invalid','user':payload['route']['user'],
                    'password':'owned-wrong-recovery-password','use_pure':not use_c,
                    'mysql_recovery_binding':payload['route']['mysql_recovery_binding']})
            except Exception as error:assert getattr(error,'errno',None)==1045,error
            else:refused.close();raise AssertionError('Recovery must retain native TCP account authentication')
            connection=provider.client._connect({'route':payload['route']})
            try:
                assert type(connection).__name__==('CharsetCMySQLConnection' if use_c else 'CharsetMySQLConnection')
                cursor=connection.cursor();cursor.execute('SELECT id,note,b FROM t');assert cursor.fetchall()==[(18446744073709551615,'native 雪',b'\x00\xff')];cursor.close()
                cursor=connection.cursor();cursor.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'");assert cursor.fetchone()[1];cursor.close()
                cursor=connection.cursor();cursor.execute("SET SESSION character_set_results='latin1'");cursor.close()
                connection.reconnect(attempts=1,delay=0)
                cursor=connection.cursor();cursor.execute('SELECT @@server_uuid');assert cursor.fetchone()[0]==rows[0][3];cursor.close()
                cursor=connection.cursor();cursor.execute('SELECT note AS `雪列` FROM t');assert cursor.description[0][0]=='雪列' and cursor.fetchall()==[('native 雪',)];cursor.close()
            finally:provider.client._discard_failed_session(connection)
        execute(source_post,session,'ROLLBACK TO SAVEPOINT recovery_source_guard')
        assert execute(source_post,session,'SELECT COUNT(*) FROM pending')['rows']==[[1]]
        execute(source_post,session,'ROLLBACK')
        # A fresh attachment replaces only the target transport. Source pending
        # work is protected by a different endpoint namespace.
        physical('connection_detach',{'server_id':attached['server_id']})
        failed=client.post(target_url,json={'action':'open_session','language_profile':'mysql-sql','database_target_id':target_id}).get_json()
        assert not failed.get('success')
        again=physical('connection_review',{'job_id':runtime['job_id'],'name':'Ignored existing name','credentials':credentials})
        reattached=physical('connection_connect',{'review_id':again['job_id'],'review_digest':again['review_digest'],'confirmed':True,'delegate_database_credentials':True,'credentials':credentials})
        assert reattached['result']['server_id']==attached['server_id']
        checks.extend(['native-driver-SSH-editor-exact-unsigned64-Unicode-BLOB-completion-TLS-native-auth-refusal-and-reconnect',
            'separate-registration-preserves-source-pending-savepoint-and-once-only-connection-claim',
            'lost-connection-reply-preserves-one-durable-registration-and-target-pending-work-refuses-detach',
            'detached-transport-refuses-network-fallback-and-fresh-SSH-reattaches-same-registration'])
        return {'checks':checks,'server_id':attached['server_id'],'database_target_id':target_id,'url':target_url}
    finally:
        source_post('close_session',session_id=session)


def stopped_connection(app,client,connection,physical):
    value=client.post(connection['url'],json={'action':'open_session','language_profile':'mysql-sql','database_target_id':connection['database_target_id']}).get_json()
    assert not value.get('success')
    physical('connection_detach',{'server_id':connection['server_id']})


def browser_connection(driver,wait,click,fill,check,password,output):
    from selenium.webdriver.common.by import By
    from cdeadmin_ui_evidence import expand,wait_for_tree_item,invoke_context_action,complete_endpoint_prompt
    from cdeadmin_sqlite_query_ui_gate import _run_query
    fill('Recovery registration name','Recovered editor desktop')
    click('Review recovery connection')
    wait.until(lambda b:b.find_element(By.CSS_SELECTOR,'[aria-label="Native recovery connection review"]'))
    check('I confirm this separate recovery connection registration.')
    check('Use the registered database credential for this recovery registration.')
    click('Attach reviewed recovery connection')
    def receipt(b):return json.loads(b.find_element(By.CSS_SELECTOR,'[aria-label="Native recovery connection receipt"]').text)
    value=wait.until(lambda b:(r if (r:=receipt(b)).get('result',{}).get('transport_attached') else None))
    sid=value['result']['server_id']
    def owned(b):
        return next((node for node in b.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and b.execute_script(
            'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,sid)),None)
    label=wait.until(owned).text;expand(wait,label,('Connectors','MySQL'))
    database=wait_for_tree_item(wait,'sr_osc',('Connectors','MySQL',label))
    invoke_context_action(wait,driver,database,('Database workspace','Open MySQL SQL editor...'),handle_endpoint_prompt=False)
    complete_endpoint_prompt(driver,password,timeout=5)
    def tab(label):
        node=wait.until(lambda b:next((e for e in b.find_elements(By.CSS_SELECTOR,'[role="tab"]') if e.is_displayed() and e.text==label),None));node.click()
    tab('Engine options')
    label=wait.until(lambda b:b.find_element(By.XPATH,'//label[contains(.,"Omit this sensitive source from SQL history")]'))
    if not label.find_element(By.CSS_SELECTOR,'input').is_selected():label.click()
    tab('Data Output')
    _run_query(driver,wait,'SELECT CAST(id AS CHAR) AS native_id,note,HEX(b) AS binary_value FROM t','native 雪','MySQL',output)
    assert '18446744073709551615' in driver.find_element(By.TAG_NAME,'body').text
    driver.save_screenshot(str(output/'native-recovery-editor.png'))
    close=wait.until(lambda b:next((e for e in b.find_elements(By.CSS_SELECTOR,'button[aria-label="Close query session"]') if e.is_displayed() and e.is_enabled()),None));close.click()
    physical=wait.until(lambda b:next((e for e in b.find_elements(By.XPATH,'//*[normalize-space(text())="MySQL physical backups"]') if e.is_displayed()),None));physical.click()
    click('Detach recovery transport')
    return ['built-separate-recovery-registration-native-SQL-editor-result-and-explicit-detach']


if __name__=='__main__':
    from cdeadmin_mysql_physical_qualification import qualify
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--fixture-image',default='sr-mysql-physical:phase209')
    parser.add_argument('--private-key');parser.add_argument('--prepare-fixture',action='store_true');parser.add_argument('--browser-binary');parser.add_argument('--driver-binary')
    args=parser.parse_args();qualify(args.output,args.fixture_image,args.private_key,args.prepare_fixture,args.browser_binary,args.driver_binary,connections=True)

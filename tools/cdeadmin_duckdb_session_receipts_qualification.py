"""Owned native DuckDB receipt retention, authenticated APIs and browser evidence."""
from pathlib import Path
import argparse,builtins,hashlib,json,subprocess,sys,threading,time,uuid
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',required=True,type=Path);parser.add_argument('--browser-binary');parser.add_argument('--driver-binary')
parser.add_argument('--inspect-existing',action='store_true');args=parser.parse_args();out=args.output.resolve()
if out==ROOT or ROOT in out.parents:raise ValueError('Evidence belongs outside source')
out.mkdir(parents=True,exist_ok=args.inspect_existing,mode=0o700)
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')];builtins.SERVER_MODE=None
import config
config.SERVER_MODE=False;config.TESTING=True;config.WTF_CSRF_ENABLED=False;config.MASTER_PASSWORD_REQUIRED=False;config.USE_OS_SECRET_STORAGE=False
for name,value in {'DATA_DIR':'app','SQLITE_PATH':'app/application.db','SESSION_DB_PATH':'app/sessions','STORAGE_DIR':'app/storage','LOG_FILE':'app/application.log','AZURE_CREDENTIAL_CACHE_DIR':'app/azure','CDEADMIN_OPERATION_STORE_PATH':'app/operations.json'}.items():setattr(config,name,str(out/value))
import duckdb
from pgadmin import create_app
from pgadmin.model import db,User,ServerGroup,Server,EndpointDatabaseTarget
from pgadmin.cdeadmin.endpoints.profiles import registration_profile
from flask import url_for
if duckdb.__version__!='1.5.2':raise ValueError('Select native DuckDB 1.5.2')
if args.inspect_existing:
 app=create_app('ScratchRobin-native-duckdb-receipt-restart');app.PGADMIN_RUNTIME=False;app.PGADMIN_INT_KEY='';app.run_before_app_start();client=app.test_client()
 fixture=json.loads((out/'receipt-fixture.json').read_text())
 with client.session_transaction() as session:session['_user_id']=str(fixture['owner']);session['_fresh']=True
 def forbidden(*_args,**_kwargs):raise AssertionError('Archive reconnected to a native engine')
 with patch.object(duckdb,'connect',side_effect=forbidden):
  for key in fixture['receipts']:
   response=client.post(fixture['url'],json={'action':'duckdb_session_receipts','database_target_id':fixture['target'],'request':{'operation':'get','review_id':key}})
   value=response.get_json();assert response.status_code==200 and value.get('success'),value
   assert value['data']['receipt']['native_acknowledged'] and value['data']['original_session']['state']=='released'
   assert value['data']['archived_read_only'] and not value['data']['transaction_finality_inferred']
 (out/'restart-proof.json').write_text(json.dumps({'complete':True,'new_application_process':True,'native_connect_forbidden':True,'native_source_file_unavailable':not (out/'primary.duckdb').exists(),'receipts':len(fixture['receipts'])},indent=2)+'\n')
 raise SystemExit(0)
path=out/'primary.duckdb';observer=duckdb.connect(str(path));observer.execute('CREATE TABLE pending(id INT)');other=out/'other . é.duckdb';secondary=duckdb.connect(str(other));secondary.execute('CREATE TABLE data(id INT)');secondary.execute('INSERT INTO data VALUES (7)');secondary.close()
app=create_app('ScratchRobin-native-duckdb-session-receipts');app.PGADMIN_RUNTIME=False;app.PGADMIN_INT_KEY='';app.run_before_app_start();client=app.test_client()
proof={'complete':False,'platform':sys.platform,'native_version':duckdb.__version__,'history_testing':'not run','full_product_complete':False,'source_sha256':{}}
for rel in ['web/pgadmin/cdeadmin/providers/duckdb/administration.py','web/pgadmin/cdeadmin/providers/duckdb/attachments.py','web/pgadmin/cdeadmin/providers/duckdb/driver.py','web/pgadmin/cdeadmin/data_studio/studio.py','web/pgadmin/cdeadmin/workspace/service.py','web/pgadmin/browser/server_groups/servers/__init__.py','web/pgadmin/static/js/Dialogs/DuckDBAttachment.jsx','web/pgadmin/cdeadmin/providers/duckdb/provider.py','web/pgadmin/cdeadmin/providers/duckdb/duckdb_dialect_1_5_2.json','web/pgadmin/static/js/Dialogs/ProviderWorkspaceContent.jsx']:
 proof['source_sha256'][rel]=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()
for rel in ['web/pgadmin/cdeadmin/providers/duckdb/database_copy.py','web/pgadmin/static/js/Dialogs/DuckDBDatabaseCopy.jsx']:
 proof['source_sha256'][rel]=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()
for rel in ['tools/cdeadmin_duckdb_session_receipts_qualification.py','web/pgadmin/cdeadmin/workspace/duckdb_session_receipts.py','web/pgadmin/cdeadmin/providers/duckdb/extension_actions.py','web/pgadmin/cdeadmin/context_menu.py','web/pgadmin/static/js/helpers/ModalCloseGuard.jsx','web/pgadmin/static/js/helpers/Layout/index.jsx','web/pgadmin/static/js/Dialogs/index.jsx','web/pgadmin/static/js/Dialogs/DuckDBOperationReceipts.jsx']:
 proof['source_sha256'][rel]=hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()
try:
 with app.test_request_context('/'):
  user=User.query.first();uid=user.id;group=ServerGroup.query.filter_by(user_id=uid).first();app.blueprints['NODE-engine_type'].connector_visibility['duckdb'].set(True,user_id=uid)
  server=Server(user_id=uid,servergroup_id=group.id,name='Owned DuckDB metadata',host=None,port=1,username='',maintenance_db=str(path),save_password=0)
  server._cde_endpoint_registration=registration_profile('duckdb-native');server._cde_endpoint_route_configuration={'database':str(path),'filesystem_root':str(out),'database_create_root':str(out)}
  db.session.add(server);db.session.commit();sid=server.id;target=str(uuid.uuid4());db.session.add(EndpointDatabaseTarget(id=target,endpoint_id=server.endpoint_profile.id,display_name=path.name,database=str(path),configuration='{}',active=1));db.session.commit()
  verify=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=sid);url=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=sid)
 with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
 response=client.post(verify,json={});value=response.get_json();assert value.get('success'),value
 def post(action,request=None,refused=False,**fields):
  payload={'action':action,'database_target_id':target,**fields}
  if request is not None:payload['request']=request
  response=client.post(url,json=payload);value=response.get_json()
  if refused:assert response.status_code==400,value;return value
  assert response.status_code==200 and value.get('success'),value;return value['data']
 opened=post('open_session',language_profile='duckdb-sql');session_id=opened['session_id']
 from flask_login import login_user
 with app.test_request_context('/'):
  login_user(User.query.filter_by(id=uid).first());registered=Server.query.filter_by(id=sid).first();endpoint_service=app.extensions['cdeadmin_endpoint_service'];context,endpoint,_=endpoint_service.workspace(registered,database_target_id=target);provider=endpoint_service.provider_registry.resolve(context).instance;handle=provider._sessions[app.extensions['cdeadmin_data_studio']._sessions[session_id].provider_session['session_id']].handle

 destination_file=out/'destination.duckdb';duckdb.connect(str(destination_file)).close()
 source_alias='HTTP source . " é';destination_alias='HTTP destination . " é'
 for alias,file,readonly in [(source_alias,other,True),(destination_alias,destination_file,False)]:
  reviewed=post('duckdb_attachments',{'operation':'review','draft':{'action':'attach','alias':alias,'path':str(file),'read_only':readonly,'create_if_missing':False,'conflict':'ERROR'}},session_id=session_id)
  result=post('duckdb_attachments',{'operation':'apply','review_id':reviewed['review_id'],'review_digest':reviewed['review_digest'],'confirmation':alias,'confirmed':True},session_id=session_id)
  assert result['rediscovery_verified'],result
 post('transaction_action',session_id=session_id,transaction_action='commit')
 def finish(record):
  deadline=time.monotonic()+30
  while record['phase']!='finished':
   assert time.monotonic()<deadline,record
   time.sleep(.03)
   record=post('duckdb_database_copy',{'operation':'receipt','review_id':record['review_id']},session_id=session_id)
  return record
 handle.execute('CREATE TEMP TABLE private_copy AS SELECT 42 id')
 reviewed=finish(post('duckdb_database_copy',{'operation':'review','draft':{'source_catalog':source_alias,'destination_catalog':destination_alias,'mode':'ALL'}},session_id=session_id))
 assert reviewed['state']=='reviewed',reviewed
 applying={'operation':'apply','review_id':reviewed['review_id'],'review_digest':reviewed['review_digest'],'confirmation':destination_alias,'confirmed':True}
 applied=finish(post('duckdb_database_copy',applying,session_id=session_id));assert applied['state']=='acknowledged' and applied['rediscovery_verified'],applied
 assert post('duckdb_database_copy',applying,session_id=session_id)==applied
 assert handle.execute('SELECT id FROM "HTTP destination . "" é".main.data').fetchall()==[(7,)]
 assert handle.execute('SELECT id FROM private_copy').fetchall()==[(42,)]
 assert observer.execute('SELECT count(*) FROM duckdb_tables() WHERE database_name=?',[destination_alias]).fetchone()==(0,)
 post('duckdb_database_copy',{'operation':'apply',**applying,'source':'DROP TABLE main.pending'},session_id=session_id,refused=True)
 response=client.post(url+'?database_target_id='+target,json={'action':'duckdb_database_copy','database_target_id':'another-target','session_id':session_id,'request':{'operation':'inventory'}});assert response.status_code==400
 post('transaction_action',session_id=session_id,transaction_action='rollback')
 assert observer.execute('SELECT count(*) FROM duckdb_tables() WHERE database_name=?',[destination_alias]).fetchone()==(0,)
 encryption_canary='owned confidential '+uuid.uuid4().hex
 reviewed_attachment=post('duckdb_attachments',{'operation':'review','draft':{'action':'attach','alias':'owned private file','path':str(out/'encrypted.duckdb'),'read_only':False,'create_if_missing':True,'conflict':'ERROR','encryption_key':encryption_canary,'encryption_cipher':'GCM'}},session_id=session_id)
 attached=post('duckdb_attachments',{'operation':'apply','review_id':reviewed_attachment['review_id'],'review_digest':reviewed_attachment['review_digest'],'confirmation':'owned private file','confirmed':True},session_id=session_id)
 assert attached['native_acknowledged'] and attached['rediscovery_verified'],attached
 reviewed_extension=post('duckdb_extensions',{'operation':'review','draft':{'action':'load','extension_name':'json'}},session_id=session_id)
 loaded=post('duckdb_extensions',{'operation':'apply','review_id':reviewed_extension['review_id'],'review_digest':reviewed_extension['review_digest'],'confirmation':reviewed_extension['extension_name'],'confirmed':True},session_id=session_id)
 assert loaded['native_acknowledged'] and loaded['rediscovery_verified'],loaded
 post('close_session',session_id=session_id)
 receipt_ids=[applied['review_id'],attached['review_id'],loaded['review_id']]
 for key in receipt_ids:
  retained=post('duckdb_session_receipts',{'operation':'get','review_id':key})
  assert retained['receipt']['native_acknowledged'] and retained['original_session']['state']=='released'
  assert retained['archived_read_only'] and retained['transaction_finality_inferred'] is False
 post('duckdb_session_receipts',{'operation':'apply','review_id':receipt_ids[0]},refused=True)
 assert not app.extensions['cdeadmin_data_studio']._sessions
 proof['authenticated_all_three_families_after_original_release']=True
 proof['native_copy_rollback_does_not_erase_acknowledgement']=True
 (out/'receipt-fixture.json').write_text(json.dumps({'owner':uid,'url':url,'target':target,'receipts':receipt_ids},indent=2)+'\n')
 if args.browser_binary:
  from werkzeug.serving import make_server
  from selenium import webdriver
  from selenium.webdriver.chrome.service import Service
  from selenium.webdriver.common.by import By
  from selenium.webdriver.common.keys import Keys
  from selenium.webdriver.support.ui import WebDriverWait
  from selenium.common.exceptions import StaleElementReferenceException
  from cdeadmin_ui_evidence import ensure_data_explorer,expand,named_tree_item,invoke_context_action
  http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
  try:
   options=webdriver.ChromeOptions();options.binary_location=args.browser_binary
   for flag in ['--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1800,1200']:options.add_argument(flag)
   options.add_argument('--user-data-dir='+str(out/'browser-profile'));options.set_capability('goog:loggingPrefs',{'browser':'ALL'});driver=webdriver.Chrome(options=options,service=Service(args.driver_binary));driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/');wait=WebDriverWait(driver,90,ignored_exceptions=(StaleElementReferenceException,))
   ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'DuckDB')
   def owned_server(browser):
    return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and browser.execute_script('const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,sid)),None)
   label=wait.until(owned_server).text;expand(wait,label,('Connectors','DuckDB'));base=('Connectors','DuckDB',label)
   database=wait.until(lambda browser:named_tree_item(browser,path.name,base));invoke_context_action(wait,driver,database,('Database workspace','Plan native DuckDB attachment...'),handle_endpoint_prompt=False)
   def field(label):
    node=wait.until(lambda browser:next((node for node in browser.find_elements(By.TAG_NAME,'label') if node.is_displayed() and node.text.strip().rstrip('*').strip()==label),None));return driver.find_element(By.ID,node.get_attribute('for'))
   for label,value in [('Copy source catalog',source_alias),('Copy destination catalog',destination_alias)]:
    control=field(label);control.send_keys(Keys.CONTROL,'a');control.send_keys(value)
   def click(label):
    def attempt(browser):
     node=next((row for row in browser.find_elements(By.TAG_NAME,'button') if row.is_displayed() and row.is_enabled() and row.text.strip()==label),None)
     if node is None:return False
     browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});',node);node.click();return True
    wait.until(attempt)
   click('Review native database copy');field('Exact copy destination confirmation').send_keys(destination_alias)
   confirmation=wait.until(lambda browser:next((row for row in browser.find_elements(By.TAG_NAME,'label') if row.is_displayed() and row.text.strip()=='I reviewed the native database copy and its transaction effects'),None));driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',confirmation);confirmation.click();click('Apply reviewed database copy once')
   def acknowledged(browser):
    node=next((row for row in browser.find_elements(By.CSS_SELECTOR,'[aria-label="DuckDB database copy receipt"]') if row.is_displayed()),None)
    if node is None:return False
    value=json.loads(node.text);return value['phase']=='finished' and value['state']=='acknowledged' and value['rediscovery_verified']
   wait.until(acknowledged)
   browser_session=next(iter(app.extensions['cdeadmin_data_studio']._sessions))
   assert observer.execute('SELECT count(*) FROM duckdb_tables() WHERE database_name=?',[destination_alias]).fetchone()==(0,)
   post('transaction_action',session_id=browser_session,transaction_action='commit')
   assert observer.execute('SELECT id FROM "HTTP destination . "" é".main.data').fetchall()==[(7,)]
   click('Read database copy receipt');wait.until(acknowledged)
   tab=wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[data-cdeadmin-tab-id^="id-provider-workspace-"]') if node.is_displayed() and 'Plan native DuckDB attachment' in node.text),None))
   tab.find_element(By.TAG_NAME,'button').click()
   wait.until(lambda _browser:not app.extensions['cdeadmin_data_studio']._sessions)
   database=wait.until(lambda browser:named_tree_item(browser,path.name,base))
   invoke_context_action(wait,driver,database,('Database workspace','Saved DuckDB operation receipts...'),handle_endpoint_prompt=False)
   click('Load saved DuckDB receipts')
   wait.until(lambda browser:any(node.is_displayed() for node in browser.find_elements(By.CSS_SELECTOR,'[aria-label="Saved DuckDB operation receipts"]')))
   inspection=wait.until(lambda browser:next((node for node in browser.find_elements(By.TAG_NAME,'button') if node.is_displayed() and node.is_enabled() and node.get_attribute('aria-label')=='Inspect saved DuckDB receipt '+receipt_ids[0]),None))
   driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',inspection);inspection.click()
   saved=wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[aria-label="Saved DuckDB receipt details"]') if node.is_displayed()),None))
   retained=json.loads(saved.text);assert retained['receipt']['native_acknowledged'] and retained['original_session']['state']=='released'
   assert not app.extensions['cdeadmin_data_studio']._sessions

   driver.save_screenshot(str(out/'browser-database-copy.png'));errors=[row for row in driver.get_log('browser') if row['level']=='SEVERE'];assert not errors,errors
   proof['browser']={'complete':True,'console_errors':0,'original_session_review_apply_and_receipt_verified':True,'independent_pending_and_explicit_api_commit_observed':True,'archive_context_menu_read_after_actual_workspace_close_without_native_session':True}
  finally:
   if driver is not None:
    if not proof.get('browser',{}).get('complete'):
     driver.save_screenshot(str(out/'browser-failure.png'));(out/'browser-failure.html').write_text(driver.page_source)
    driver.quit()
   http.shutdown();thread.join(timeout=10)
 archive_files=list(Path(str(app.extensions['cdeadmin_operation_bus'].store.path)+'.duckdb-session-receipts').rglob('*.json'))
 assert len(archive_files)>=len(receipt_ids)+1
 for file in archive_files:
  assert encryption_canary.encode() not in file.read_bytes()
 hidden=out/'offline-primary.duckdb';path.rename(hidden)
 try:
  with (out/'restart.log').open('w') as log:
   subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--output',str(out),'--inspect-existing'],check=True,stdout=log,stderr=subprocess.STDOUT,timeout=90)
 finally:hidden.rename(path)
 restarted=json.loads((out/'restart-proof.json').read_text())
 assert restarted['complete'] and restarted['native_source_file_unavailable']
 proof['restart']=restarted;proof['private_encryption_key_absent_from_durable_archive']=True
 proof['complete']=True
finally:
 if 'app' in locals():
  for live_session in list(app.extensions['cdeadmin_data_studio']._sessions):
   response=client.post(url,json={'action':'close_session','database_target_id':target,'session_id':live_session})
   if response.status_code!=200:proof['session_cleanup_failed']=True
 observer.close();(out/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')

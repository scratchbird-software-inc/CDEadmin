"""Owned HTTPS repository, original-session credentials, API and UI evidence."""
import argparse
import datetime
import gzip
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import ssl
import sys
import threading
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def qualify(args):
    import builtins
    builtins.SERVER_MODE = None
    import config
    import duckdb
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    out = args.output.resolve()
    if out == ROOT or ROOT in out.parents:raise ValueError('Evidence belongs outside source')
    if duckdb.__version__ != '1.5.2':raise ValueError('Select native DuckDB 1.5.2')
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    binary = args.signed_extension.resolve().read_bytes()
    signed = out / 'httpfs.duckdb_extension';signed.write_bytes(binary)
    payload = gzip.compress(binary, compresslevel=1)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'owned-native-repository')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=1))
        .not_valid_after(now+datetime.timedelta(hours=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]), False)
        .sign(key, hashes.SHA256()))
    private = out / 'tls.key';certificate = out / 'tls.pem'
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    os.chmod(private, 0o600);certificate.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    token, broad_token, error_canary = ['owned-private-'+uuid.uuid4().hex for _ in range(3)]
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):pass
        def do_HEAD(self):self.reply(True)
        def do_GET(self):self.reply(False)
        def reply(self, head):
            authorized = self.headers.get('Authorization') == 'Bearer '+token and (
                not args.typed_secret_properties or self.headers.get('X-CDE-Native-Property')=='native typed map')
            requests.append({'method': self.command, 'path': self.path, 'authorized': authorized,
                'tls': isinstance(self.connection, ssl.SSLSocket)})
            if not authorized:self.send_error(401, error_canary);return
            start, end = 0, len(payload)-1
            selected = self.headers.get('Range')
            if selected:
                first, last = selected.removeprefix('bytes=').split('-')
                start = int(first);end = min(int(last) if last else end, end)
            self.send_response(206 if selected else 200)
            self.send_header('Content-Length', str(end-start+1));self.send_header('Accept-Ranges', 'bytes')
            self.send_header('ETag', '"owned-stable-signed-extension"')
            if selected:self.send_header('Content-Range', f'bytes {start}-{end}/{len(payload)}')
            self.end_headers()
            if not head:self.wfile.write(payload[start:end+1])
    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(certificate, private)
    http.socket = tls.wrap_socket(http.socket, server_side=True)
    thread = threading.Thread(target=http.serve_forever, daemon=True);thread.start()
    repository = 'http://127.0.0.1:'+str(http.server_port)+'/native'
    native_config = {'extension_directory': str(out/'cache'), 'home_directory': str(out),
        'secret_directory': str(out/'secrets'), 'autoload_known_extensions': False, 'autoinstall_known_extensions': False}
    primary = out/'primary.duckdb';observer = duckdb.connect(str(primary), config=native_config)
    observer.execute('CREATE TABLE pending(id INT)')
    config.SERVER_MODE=False;config.TESTING=True;config.WTF_CSRF_ENABLED=False
    config.MASTER_PASSWORD_REQUIRED=False;config.USE_OS_SECRET_STORAGE=False
    for option, value in {'DATA_DIR':'app','SQLITE_PATH':'app/application.db','SESSION_DB_PATH':'app/sessions',
            'STORAGE_DIR':'app/storage','LOG_FILE':'app/application.log','AZURE_CREDENTIAL_CACHE_DIR':'app/azure',
            'CDEADMIN_OPERATION_STORE_PATH':'app/operations.json'}.items():setattr(config, option, str(out/value))
    from pgadmin import create_app
    from pgadmin.model import db, User, ServerGroup, Server, EndpointDatabaseTarget
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from flask import url_for
    from flask_login import login_user
    app=create_app('ScratchRobin-owned-native-HTTP-authentication');app.PGADMIN_RUNTIME=False;app.PGADMIN_INT_KEY=''
    app.run_before_app_start();client=app.test_client()
    proof={'complete':False,'native_version':duckdb.__version__,'history_testing':'not run','full_product_complete':False,
        'httpfs_binary_sha256':hashlib.sha256(binary).hexdigest(),'httpfs_source_commit':'13e18b3c9f3810334f5972b76a3acc247b28e537',
        'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in [
            'tools/cdeadmin_duckdb_authenticated_extensions_qualification.py','web/pgadmin/cdeadmin/providers/duckdb/extension_actions.py',
            'web/pgadmin/cdeadmin/providers/duckdb/provider.py','web/pgadmin/cdeadmin/providers/duckdb/provider_manifest.json','web/pgadmin/cdeadmin/providers/duckdb/driver.py',
            'web/pgadmin/cdeadmin/endpoints/service.py',
            'web/pgadmin/cdeadmin/providers/duckdb/administration.py',
            'web/pgadmin/cdeadmin/providers/duckdb/secret_values.py',
            'web/pgadmin/cdeadmin/providers/relational_admin.py',
            'web/pgadmin/cdeadmin/data_studio/studio.py','web/pgadmin/cdeadmin/workspace/service.py',
            'web/pgadmin/cdeadmin/context_menu.py','web/pgadmin/static/js/Dialogs/DuckDBExtensions.jsx',
            'web/pgadmin/static/js/Dialogs/ProviderWorkspaceContent.jsx']}}
    try:
        with app.test_request_context('/'):
            user=User.query.first();owner=user.id;group=ServerGroup.query.filter_by(user_id=owner).first()
            app.blueprints['NODE-engine_type'].connector_visibility['duckdb'].set(True,user_id=owner)
            server=Server(user_id=owner,servergroup_id=group.id,name='Owned authenticated DuckDB',host=None,port=1,username='',maintenance_db=str(primary),save_password=0)
            server._cde_endpoint_registration=registration_profile('duckdb-native')
            server._cde_endpoint_route_configuration={'database':str(primary),'filesystem_root':str(out),'config':native_config}
            db.session.add(server);db.session.commit();sid=server.id;target=str(uuid.uuid4())
            db.session.add(EndpointDatabaseTarget(id=target,endpoint_id=server.endpoint_profile.id,display_name=primary.name,database=str(primary),configuration='{}',active=1));db.session.commit()
            verify=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=sid)
            url=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=sid)
        with client.session_transaction() as session:session['_user_id']=str(owner);session['_fresh']=True
        checked=client.post(verify,json={});assert checked.get_json().get('success'),checked.get_json()
        def post(action, request=None, *, refused=False, **fields):
            response=client.post(url,json={'action':action,'database_target_id':target,**fields,
                **({'request':request} if request is not None else {})});value=response.get_json()
            if refused:assert response.status_code in {400,403},value;return value
            assert response.status_code==200 and value.get('success'),value
            return value['data']
        session_id=post('open_session',language_profile='duckdb-sql')['session_id']
        with app.test_request_context('/'):
            login_user(User.query.filter_by(id=owner).first());registered=Server.query.filter_by(id=sid).first()
            endpoints=app.extensions['cdeadmin_endpoint_service'];context,_endpoint,_=endpoints.workspace(registered,database_target_id=target)
            provider=endpoints.provider_registry.resolve(context).instance
            handle=provider._sessions[app.extensions['cdeadmin_data_studio']._sessions[session_id].provider_session['session_id']].handle
        def review(draft):return post('duckdb_extensions',{'operation':'review','draft':draft},session_id=session_id)
        def apply(record):
            request={'operation':'apply','review_id':record['review_id'],'review_digest':record['review_digest'],
                'confirmation':record['extension_name'],'confirmed':True}
            value=post('duckdb_extensions',request,session_id=session_id);count=len(requests)
            assert post('duckdb_extensions',request,session_id=session_id)==value and len(requests)==count
            return value
        handle.execute('INSERT INTO pending VALUES (42)');handle.execute('CREATE TEMP TABLE private_rows AS SELECT 19 id')
        transaction=handle.execute('SELECT current_transaction_id()').fetchone()[0]
        installed=apply(review({'action':'install','extension_name':'httpfs','source_kind':'FILE','source':str(signed)}))
        assert installed['native_acknowledged'] and installed['rediscovery_verified'],installed
        loaded=apply(review({'action':'load','extension_name':'httpfs'}))
        assert loaded['native_acknowledged'] and loaded['rediscovery_verified'],loaded
        assert next(row for row in loaded['native_extensions'] if row['extension_name']=='httpfs')['extension_version']=='13e18b3'
        handle.execute('SET GLOBAL ca_cert_file=?',[str(certificate)]);handle.execute('SET GLOBAL http_retries=0')
        platform=handle.execute('PRAGMA platform').fetchone()[0]
        effective='https://127.0.0.1:'+str(http.server_port)+'/native/v1.5.2/'+platform+'/httpfs.duckdb_extension.gz'
        handle.execute('CREATE SECRET broad (TYPE HTTP,BEARER_TOKEN ?,SCOPE ?)',[broad_token,effective.rsplit('/',1)[0]+'/'])
        selected='owned exact . " é'
        def seed(value):
            if not args.typed_secret_properties:
                handle.execute('CREATE OR REPLACE SECRET "owned exact . "" é" (TYPE HTTP,BEARER_TOKEN ?,SCOPE ?,VERIFY_SSL true)',[value,effective])
                return
            handle.execute('DROP SECRET IF EXISTS "owned exact . "" é"')
            request={'resource_kind':'secret','operation_id':'create','session_id':session_id,'database_target_id':target,
                'draft':{'name':selected,'secret_type':'HTTP','properties':{'scope':[effective,'https://unused.example.test/'],
                    'verify_ssl':True,'extra_http_headers':{'Authorization':'Bearer '+value,'X-CDE-Native-Property':'native typed map'}}}}
            validated=post('visual_admin_validate',request);assert validated['valid'],validated
            planned=post('visual_admin_plan',request)
            assert value not in json.dumps(planned) and effective not in json.dumps(planned['command_preview'])
            applied=post('visual_admin_apply',{'plan_id':planned['plan_id'],'plan_digest':planned['plan_digest'],
                'confirmed':True,'session_id':session_id,'database_target_id':target})
            assert applied['provider_result']['accepted'] and not applied['provider_result']['commit_requested'] and not applied['provider_result']['rollback_requested'],applied
            proof['typed_secret_properties_api']={'native_header_map_and_boolean_and_scope_list':True,
                'original_session_explicitly_bound':True,'private_properties_absent_from_public_plan':True,
                'native_transaction_decision_not_requested':True}
        seed(token)
        count=len(requests)
        try:observer.execute("FORCE INSTALL '"+effective+"'")
        except duckdb.Error as error:
            assert len(requests)==count
            proof['native_direct_https_refused_before_request']={'error_type':type(error).__name__,
                'independent_native_interface':True,'application_downloader_used':False}
        else:raise AssertionError('The pinned direct-HTTPS limitation changed; reconcile its source and documented scope')
        proof['native_build']=dict(zip(('library_version','source_id','codename'),observer.execute('PRAGMA version').fetchone()))
        draft={'action':'install','extension_name':'httpfs','source_kind':'NAME','repository_kind':'URL',
            'repository':repository,'force':True,'expected_http_secret':selected}
        reviewed=review(draft);access=reviewed['source_access']
        assert access['lookup_url']==effective and access['selected_http_identity']['name']==selected
        assert access['httpfs_loaded'] and not access['credential_values_observed'] and not access['credential_value_changes_fenced']
        assert access['native_transport_settings']['ca_cert_file']==str(certificate)
        result=apply(reviewed);assert result['native_acknowledged'] and result['rediscovery_verified'],result
        assert requests and all(row['authorized'] and row['tls'] for row in requests)
        assert handle.execute('SELECT current_transaction_id()').fetchone()[0]==transaction
        assert handle.execute('SELECT id FROM pending').fetchall()==[(42,)]
        assert handle.execute('SELECT id FROM private_rows').fetchall()==[(19,)]
        assert observer.execute('SELECT id FROM pending').fetchall()==[]
        original_allows=provider.permissions.allows
        def denied(action,*values):
            return False if action=='secret_read' else original_allows(action,*values)
        count=len(requests)
        with patch.object(provider.permissions,'allows',side_effect=denied):
            post('duckdb_extensions',{'operation':'review','draft':draft},session_id=session_id,refused=True)
            assert post('duckdb_extensions',{'operation':'receipt','review_id':result['review_id']},session_id=session_id)==result
        assert len(requests)==count
        stale=review(draft);handle.execute('DROP SECRET "owned exact . "" é"')
        refused=apply(stale);assert refused['native_dispatched'] is False and refused['state']=='refused'
        assert len(requests)==count;seed(token)
        post('transaction_action',session_id=session_id,transaction_action='rollback')
        assert observer.execute('SELECT id FROM pending').fetchall()==[]
        seed('owned incorrect native bearer')
        failed=apply(review(draft));assert not failed['native_acknowledged'] and failed['state'] in {'refused','unknown_outcome'},failed
        assert any(not row['authorized'] for row in requests)
        assert error_canary not in json.dumps(failed) and token not in json.dumps(failed)
        post('close_session',session_id=session_id)
        if args.typed_secret_properties:
            from pgadmin.cdeadmin.providers.duckdb.provider import ADMINISTRATION
            source,_preview=ADMINISTRATION._duckdb_secret('"owned exact . "" é"',{'secret_type':'HTTP',
                'scope':[effective,'https://unused.example.test/'],'verify_ssl':True,
                'extra_http_headers':{'Authorization':'Bearer '+token,'X-CDE-Native-Property':'native typed map'}})
            observer.execute('DROP SECRET IF EXISTS "owned exact . "" é"');observer.execute(source)
        else:observer.execute('CREATE OR REPLACE SECRET "owned exact . "" é" (TYPE HTTP,BEARER_TOKEN ?,SCOPE ?,VERIFY_SSL true)',[token,effective])
        proof.update(native_api_complete=True,native_longest_scope_selected=True,secret_read_denial_before_request=True,
            native_secret_reselection_refused_without_dispatch=True,native_pending_temp_and_caller_rollback_preserved=True,
            native_https_repository_install_verified=True,native_wrong_credential_refusal_and_no_replay=True,
            opaque_error_and_credential_values_absent_from_receipts=True,successful_review_id=result['review_id'])
        if args.browser_binary:
            browser_qualify(args,out,app,sid,primary,repository,selected,post,proof)
        archives=list(Path(str(app.extensions['cdeadmin_operation_bus'].store.path)+'.duckdb-session-receipts').rglob('*.json'))
        assert archives
        for archive in archives:
            for value in (token,broad_token,error_canary,'owned incorrect native bearer'):assert value.encode() not in archive.read_bytes()
        if args.typed_secret_properties:
            for path in (out/'app').rglob('*.json'):
                for value in (token,broad_token,error_canary,'owned incorrect native bearer'):assert value.encode() not in path.read_bytes()
            proof['typed_private_values_absent_from_application_json']=True
        proof['private_values_absent_from_durable_archives']=True
        proof['complete']=True
    finally:
        for identity in list(app.extensions['cdeadmin_data_studio']._sessions):
            response=client.post(url,json={'action':'close_session','database_target_id':target,'session_id':identity})
            if response.status_code!=200:
                proof['session_cleanup_failed']=True
                if 'provider' in locals():
                    try:provider.client.close();proof['owned_fixture_fallback_client_released']=True
                    except Exception as error:proof['owned_fixture_fallback_error_type']=type(error).__name__
        observer.close();http.shutdown();http.server_close();thread.join(timeout=10)
        proof['owned_https_server_stopped']=not thread.is_alive();proof['native_requests']=requests
        (out/'proof.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False)+'\n')
    return proof


def browser_qualify(args,out,app,sid,primary,repository,selected,post,proof):
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import StaleElementReferenceException
    from cdeadmin_ui_evidence import ensure_data_explorer, expand, named_tree_item, invoke_context_action
    server=make_server('127.0.0.1',0,app,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();driver=None
    try:
        options=webdriver.ChromeOptions();options.binary_location=args.browser_binary
        for flag in ['--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1800,1200']:options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(out/'browser-profile'));options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(args.driver_binary))
        driver.get('http://127.0.0.1:'+str(server.server_port)+'/browser/')
        wait=WebDriverWait(driver,90,ignored_exceptions=(StaleElementReferenceException,))
        ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'DuckDB')
        def owned_server(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and
                browser.execute_script('const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,sid)),None)
        label=wait.until(owned_server).text;expand(wait,label,('Connectors','DuckDB'));base=('Connectors','DuckDB',label)
        database=wait.until(lambda browser:named_tree_item(browser,primary.name,base))
        invoke_context_action(wait,driver,database,('Database workspace','Install or load DuckDB extensions...'),handle_endpoint_prompt=False)
        def label_node(label):
            node=wait.until(lambda browser:browser.execute_script('return Array.from(document.querySelectorAll("label")).find(e => e.getClientRects().length && e.textContent.trim().replace(/\\*$/, "").trim()===arguments[0]) || null;',label))
            driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',node)
            return node
        def field(label):return driver.find_element(By.ID,label_node(label).get_attribute('for'))
        def rendered(selector):
            node=wait.until(lambda browser:browser.execute_script('return Array.from(document.querySelectorAll(arguments[0])).find(e => e.getClientRects().length) || null;',selector))
            driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',node)
            return node
        def click(label):
            def attempt(browser):
                node=next((row for row in browser.find_elements(By.TAG_NAME,'button') if row.is_displayed() and row.is_enabled() and row.text.strip()==label),None)
                if node is None:return False
                browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});',node);node.click();return True
            wait.until(attempt)
        field('Exact native extension name').send_keys('httpfs')
        field('Repository kind').click()
        wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="option"]') if node.is_displayed() and node.text.strip()=='HTTP(S) URL'),None)).click()
        field('Native extension repository').send_keys(repository)
        field('Expected native HTTP secret (optional)').send_keys(selected)
        label_node('FORCE replacement of extension file').click();click('Review native extension')
        field('Exact reviewed extension name').send_keys('httpfs')
        access=json.loads(rendered('[aria-label="DuckDB extension source access"]').get_attribute('textContent'))
        assert access['selected_http_identity']['name']==selected and access['lookup_url'].startswith('https://127.0.0.1:')
        assert not access['credential_values_observed'] and not access['native_authentication_success_inferred']
        label_node('I reviewed the native extension code and file effects').click();click('Apply reviewed extension once')
        def acknowledged(browser):
            node=next((row for row in browser.find_elements(By.CSS_SELECTOR,'[aria-label="DuckDB extension receipt"]') if row.get_attribute('textContent').strip()),None)
            if node is None:return False
            value=json.loads(node.get_attribute('textContent'))
            return value if value['state']=='acknowledged' and value['native_acknowledged'] and value['rediscovery_verified'] else False
        result=wait.until(acknowledged);click('Read extension receipt');assert wait.until(acknowledged)==result
        tab=wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[data-cdeadmin-tab-id^="id-provider-workspace-"]') if node.is_displayed() and 'Install or load DuckDB extensions' in node.text),None))
        tab.find_element(By.TAG_NAME,'button').click()
        wait.until(lambda _browser:not app.extensions['cdeadmin_data_studio']._sessions)
        retained=post('duckdb_session_receipts',{'operation':'get','review_id':result['review_id']})
        assert retained['receipt']['native_acknowledged'] and retained['original_session']['state']=='released'
        assert retained['receipt']['source_access']==access and retained['archived_read_only']
        driver.save_screenshot(str(out/'browser-native-authentication.png'))
        errors=[row for row in driver.get_log('browser') if row['level']=='SEVERE'];assert not errors,errors
        proof['browser']={'complete':True,'console_errors':0,'context_menu_original_session_install':True,
            'expected_secret_name_and_https_transport_visible':True,'actual_native_acknowledgement':True,
            'real_dock_close_releases_session':True,'archived_access_observations_survive_release':True,
            'review_id':result['review_id']}
    finally:
        if driver is not None:
            if not proof.get('browser',{}).get('complete'):
                driver.save_screenshot(str(out/'browser-failure.png'));(out/'browser-failure.html').write_text(driver.page_source)
            driver.quit()
        server.shutdown();server.server_close();thread.join(timeout=10)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path);parser.add_argument('--signed-extension',required=True,type=Path)
    parser.add_argument('--browser-binary');parser.add_argument('--driver-binary')
    parser.add_argument('--typed-secret-properties',action='store_true')
    value=qualify(parser.parse_args());print(json.dumps({'complete':value['complete'],'native_requests':len(value['native_requests'])}))

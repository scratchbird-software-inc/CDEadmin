"""Native topology qualification against three explicitly disposable MySQL peers.

The application and mysqlsh must reach the peers' advertised addresses. Docker
Desktop fixtures therefore run this controller inside their private network;
the production runner still launches native mysqlsh directly on its own host.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'web'), str(ROOT/'tools')]

from cdeadmin_mysql_dump_verification_qualification import setup_application

UI_ACCOUNT_USER = 'sr_gui_雪'
UI_ACCOUNT_PASSWORD = 'Native-UI-private:\'\\雪'


def qualify(output, routes, password, *, use_c=False, browser_exchange=False, routing_only=False, desktop_only=False, accounts_only=False, account_contexts=None):
    from flask import url_for
    from pgadmin.model import db, User, ServerGroup, Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_archives import rows
    from pgadmin.cdeadmin.workspace.mysql_topology_service import context
    from pgadmin.cdeadmin.workspace import service_for_app
    app = setup_application(output)
    service = service_for_app(app)
    client = app.test_client()
    proof = {'complete': False, 'full_mysql_product_complete': False, 'use_c': use_c,
             'execution_host': 'native application host on isolated fixture network',
             'checks': [], 'connector_classes': [], 'operations': []}
    paths = ['tools/cdeadmin_mysql_topology_qualification.py',
        'tools/mysql_topology_lingering_qualification.py',
        'tools/mysql_routing_qualification.py',
        'tools/mysql_accounts_qualification.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_topology.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_topology_accounts.py',
        'web/pgadmin/cdeadmin/workspace/mysql_topology_jobs.py',
        'web/pgadmin/cdeadmin/workspace/mysql_topology_service.py',
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_topology_quiescence.py',
        'web/pgadmin/cdeadmin/sdk/durable_tool.py',
        'web/pgadmin/cdeadmin/sdk/tool_guardian.py',
        'web/pgadmin/cdeadmin/sdk/tool_process.py',
        'web/pgadmin/static/js/Dialogs/MySQLTopologies.jsx']
    proof['source_sha256'] = {path: hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in paths}
    http_server = None
    try:
        registrations = []
        with app.test_request_context('/'):
            uid = User.query.first().id
            group = ServerGroup.query.filter_by(user_id=uid).first()
            app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True, user_id=uid)
            for index, route in enumerate(routes):
                item = Server(user_id=uid, servergroup_id=group.id, name='Owned MySQL topology '+str(index),
                    host=route['host'], port=route['port'], username='root', maintenance_db=None, save_password=0)
                item._cde_endpoint_registration = registration_profile('mysql-native')
                item._cde_endpoint_route_configuration = {**route, 'user': 'root', 'use_pure': not use_c,
                    'credential_kinds': ['database_password']}
                db.session.add(item); db.session.commit()
                registrations.append({'server_id': item.id,
                    'verify': url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=item.id),
                    'url': url_for('NODE-server.cde_workspace_id', gid=group.id, sid=item.id)})
        with client.session_transaction() as session:
            session['_user_id'] = str(uid); session['_fresh'] = True
        for item in registrations:
            assert client.post(item['verify'], json={'password': password}).get_json()['success']

        def http(action, request=None, *, peer=0, refused=False):
            response = client.post(registrations[peer]['url'], json={
                'action': 'mysql_topology_'+action, 'request': request or {}})
            value = response.get_json()
            if refused:
                assert response.status_code == 400, value
                return value
            if response.status_code != 200 or not value.get('success'):
                (output/'http-failure.json').write_text(json.dumps(value, indent=2)+'\n')
                raise AssertionError('Native topology application request failed: '+action)
            return value['data']

        with app.test_request_context('/'):
            instrumented = set()
            for item in registrations:
                native_client, route = context(service, db.session.get(Server, item['server_id']))
                if id(native_client) in instrumented: continue
                instrumented.add(id(native_client)); connect = native_client._connect
                def recorded(*args, _connect=connect, **kwargs):
                    connection = _connect(*args, **kwargs)
                    from mysql.connector.connection import MySQLConnection
                    from mysql.connector.connection_cext import CMySQLConnection
                    assert isinstance(connection, CMySQLConnection if use_c else MySQLConnection)
                    proof['connector_classes'].append(type(connection).__name__)
                    return connection
                native_client._connect = recorded
        seeds = [http('inspect', peer=index) for index in range(3)]
        assert len({value['identity']['server_uuid'] for value in seeds}) == 3
        assert len(proof['connector_classes']) >= 3
        catalog = http('catalog')
        assert len(catalog['operations']) > 40
        assert http('members', {'offset': 0, 'limit': 2})['total'] == 3
        proof['checks'].append('authenticated-native-9.7-seed-catalog-and-owned-paged-member-inspection-with-actual-selected-driver')

        def options(operation, arguments, peer=0, *, guideline='', setting_password=False):
            witnesses = []
            if operation in {'cluster.add_instance','replica_set.add_instance'}:
                current = http('inspect', peer=peer)
                allowed = {current['identity']['server_uuid'], *current['metadata']['instance_uuids']}
                allowed.update(seeds[index]['identity']['server_uuid'] for index,item in enumerate(registrations)
                    if arguments[0].get('server_id') == item['server_id'])
                witnesses = [item['server_id'] for index,item in enumerate(registrations)
                    if seeds[index]['identity']['server_uuid'] in allowed]
            return {'operation': operation, 'arguments_json': json.dumps(arguments),
                **({'guideline_name': guideline} if '.guideline.' in operation else {}),
                **({'account_password_mode':'set' if setting_password else 'preserve'} if '.setup_' in operation else {}),
                'context_name': '', 'context_options_json': '{}', 'use_advertised_endpoint': True,
                'witness_server_ids': witnesses,
                'target_confirmation': seeds[peer]['identity']['server_uuid'], 'timeout_seconds': 240}

        def wait(value, peer=0):
            deadline = time.monotonic()+260
            while value['state'] in {'dispatching', 'active', 'cancel_requested'}:
                if time.monotonic() > deadline: raise TimeoutError('Native topology job deadline')
                time.sleep(.1); value = http('status', {'job_id': value['job_id']}, peer=peer)
            (output/'last-job.json').write_text(json.dumps(value, indent=2)+'\n')
            return value

        def execute(operation, arguments, peer=0, *, inspection=False, expect_returned=True, guideline='', account_password=None):
            selected = options(operation, arguments, peer, guideline=guideline, setting_password=account_password is not None)
            if inspection:
                value = wait(http('inspect_native', {'options': selected}, peer=peer), peer)
            else:
                review = http('review', {'options': selected}, peer=peer)
                request = {key: review[key] for key in ('job_id', 'review_digest')} | {'confirmed': True}
                if account_password is not None:
                    assert account_password not in json.dumps(review), 'A private account password entered a review'
                    request['account_secret']={'password':account_password}
                value = wait(http('start', request, peer=peer), peer)
                assert http('start', request, peer=peer)['native_operation_outcome'] == value['native_operation_outcome']
            proof['operations'].append({'method': operation, 'peer': peer, 'job_id': value['job_id'],
                'state': value['state'], 'outcome': value['native_operation_outcome']})
            (output/'progress.json').write_text(json.dumps(proof, indent=2)+'\n')
            if expect_returned:
                assert value['native_operation_outcome'] == 'returned', value
                assert value['native_process_termination_confirmed'] is True, value
            assert value['workload_readiness_verified'] is False
            return value

        def sql(peer, source, parameters=()):
            with app.test_request_context('/'):
                native_client, route = context(service, db.session.get(Server, registrations[peer]['server_id']))
                connection = native_client._connector(host=routes[peer]['host'], port=routes[peer]['port'],
                    user='root', password=password, use_pure=not use_c, autocommit=True)
                try: return rows(connection, source, parameters)
                finally: native_client._discard_failed_session(connection)

        def wait_data(peers):
            deadline = time.monotonic()+30
            for peer in peers:
                while True:
                    try:
                        result = sql(peer, 'SELECT CAST(id AS CHAR) AS id,body,HEX(payload) AS payload FROM sr_topology.t')
                        if result == [{'id': '9007199254740993', 'body': 'native topology 雪', 'payload': '00FF'}]: break
                    except Exception:
                        if time.monotonic() > deadline: raise
                    if time.monotonic() > deadline: raise TimeoutError('Independent replicated data deadline')
                    time.sleep(.1)

        def desktop(uncertain_job_id=None):
            nonlocal http_server
            from werkzeug.serving import make_server
            http_server=make_server('0.0.0.0',5000,app,threaded=True)
            threading.Thread(target=http_server.serve_forever,daemon=True).start()
            request={'server_id':registrations[0]['server_id'],'target_uuid':seeds[0]['identity']['server_uuid'],
                'recovery_member_indexes':[0] if desktop_only or accounts_only else [0,1,2]}
            if accounts_only:request['account_setup']=True
            if uncertain_job_id:request['uncertain_job_id']=uncertain_job_id
            (output/'browser-request.json').write_text(json.dumps(request)+'\n')
            deadline=time.monotonic()+300
            while not (output/'browser-response.json').exists():
                if time.monotonic()>deadline:raise TimeoutError('External native desktop qualification deadline')
                time.sleep(.25)
            proof['browser']=json.loads((output/'browser-response.json').read_text())
            assert proof['browser']['complete'],proof['browser']
        if accounts_only:
            from mysql_accounts_qualification import qualify as qualify_accounts
            def login(peer,user,secret):
                with app.test_request_context('/'):
                    native_client,route=context(service,db.session.get(Server,registrations[peer]['server_id']))
                    connection=native_client._connector(host=routes[peer]['host'],port=routes[peer]['port'],user=user,
                        password=secret,use_pure=not use_c,autocommit=True)
                    try:
                        from mysql.connector.connection import MySQLConnection
                        from mysql.connector.connection_cext import CMySQLConnection
                        assert isinstance(connection,CMySQLConnection if use_c else MySQLConnection)
                        return rows(connection,'SELECT CURRENT_USER() AS identity,VERSION() AS version')[0]
                    finally:native_client._discard_failed_session(connection)
            if desktop_only:
                if not browser_exchange:raise ValueError('Account desktop qualification requires a browser exchange')
                execute('instance.configure_cluster',[{'restart':True}],peer=0)
                execute('instance.create_cluster',['sr_account_desktop'],peer=0)
                desktop()
                proof['account_desktop_login']=login(0,UI_ACCOUNT_USER,UI_ACCOUNT_PASSWORD)
                assert proof['account_desktop_login']['identity']==UI_ACCOUNT_USER+'@%'
                assert sql(0,'SELECT password_lifetime AS days FROM mysql.user WHERE User=%s AND Host=%s',
                    (UI_ACCOUNT_USER,'%'))==[{'days':14}]
                proof['complete']=True
                return proof
            contexts=set(account_contexts or ('cluster','cluster_set','replica_set'))
            if not contexts <= {'cluster','cluster_set','replica_set'}:raise ValueError('Select native account qualification contexts')
            if browser_exchange and 'cluster' not in contexts:raise ValueError('The account desktop requires its Cluster fixture')
            for peer,name in ((0,'cluster'),(1,'cluster_set')):
                if name in contexts:execute('instance.configure_cluster',[{'restart':True}],peer)
            proof['accounts']={}
            if 'cluster' in contexts:
                execute('instance.create_cluster',['sr_account_cluster'],peer=0)
                proof['accounts']['cluster']=qualify_accounts('cluster',0,execute,http,options,sql,login,output)
            if 'cluster_set' in contexts:
                execute('instance.create_cluster',['sr_account_domain_cluster'],peer=1)
                execute('cluster.create_cluster_set',['sr_account_domain'],peer=1)
                proof['accounts']['cluster_set']=qualify_accounts('cluster_set',1,execute,http,options,sql,login,output)
            if 'replica_set' in contexts:
                execute('instance.configure_replica_set',[{'restart':True}],peer=2)
                execute('instance.create_replica_set',['sr_account_replicas'],peer=2)
                proof['accounts']['replica_set']=qualify_accounts('replica_set',2,execute,http,options,sql,login,output)
            if browser_exchange:
                desktop()
                proof['account_desktop_login']=login(0,UI_ACCOUNT_USER,UI_ACCOUNT_PASSWORD)
                assert proof['account_desktop_login']['identity']==UI_ACCOUNT_USER+'@%'
                assert sql(0,'SELECT password_lifetime AS days FROM mysql.user WHERE User=%s AND Host=%s',
                    (UI_ACCOUNT_USER,'%'))==[{'days':14}]
            proof['complete']=True
            return proof
        if desktop_only:
            if not browser_exchange:raise ValueError('Desktop-only qualification requires a browser exchange')
            execute('instance.configure_cluster',[{'restart':True}])
            execute('instance.create_cluster',['sr_desktop_cluster'])
            execute('cluster.set_option',['tag:wide',2**63])
            desktop()
            proof['complete']=True
            return proof
        if routing_only:
            from mysql_routing_qualification import qualify as qualify_routing
            for peer in (0,1):execute('instance.configure_cluster', [{'restart': True}], peer)
            execute('instance.create_cluster',['sr_routing_cluster'],peer=0)
            proof['routing']={'cluster':qualify_routing('cluster',0,execute,http,options,sql)}
            execute('instance.create_cluster',['sr_routing_domain_cluster'],peer=1)
            execute('cluster.create_cluster_set',['sr_routing_domain'],peer=1)
            proof['routing']['cluster_set']=qualify_routing('cluster_set',1,execute,http,options,sql)
            execute('instance.configure_replica_set',[{'restart':True}],peer=2)
            execute('instance.create_replica_set',['sr_routing_replicas'],peer=2)
            proof['routing']['replica_set']=qualify_routing('replica_set',2,execute,http,options,sql)
            proof['complete']=True
            return proof
        execute('instance.check_configuration', [{}], inspection=True)
        for peer in range(3): execute('instance.configure_cluster', [{'restart': True}], peer)
        execute('instance.create_cluster', ['sr_application_cluster', {'gtidSetIsComplete': True}])
        first = execute('cluster.add_instance', [
            {'server_id': registrations[1]['server_id']}, {'recoveryMethod': 'clone', 'recoveryProgress': 0}])
        first_observed = http('reconcile', {'job_id': first['job_id']})
        assert first_observed['reconciliation']['server_recovery_quiescence']['idle'] is True, first_observed
        from pgadmin.cdeadmin.workspace.mysql_topology_jobs import TopologyTransport
        original_execute = TopologyTransport.execute
        def missing_reply(self, *args, **kwargs):
            result = original_execute(self, *args, **kwargs)
            result['control'] = None
            return result
        TopologyTransport.execute = missing_reply
        try:
            uncertain = execute('cluster.add_instance', [
                {'server_id': registrations[2]['server_id']}, {'recoveryMethod': 'clone', 'recoveryProgress': 0}], expect_returned=False)
        finally: TopologyTransport.execute = original_execute
        assert uncertain['state'] == 'unknown' and uncertain['server_recovery_clearance_required'] is True
        blocked = http('review', {'options': options('cluster.set_option', ['tag:afterRecovery', True], 2)}, peer=2)
        blocked_request = {key: blocked[key] for key in ('job_id','review_digest')} | {'confirmed': True}
        http('start', blocked_request, peer=2, refused=True)
        reconciled = http('reconcile', {'job_id': uncertain['job_id']})
        assert reconciled['reconciliation']['server_recovery_quiescence']['idle'] is True, reconciled
        acknowledged = http('acknowledge', {'job_id': uncertain['job_id'],
            'target_confirmation': seeds[0]['identity']['server_uuid'], 'observation_digest': reconciled['observation_digest']})
        assert acknowledged['native_operation_outcome'] == 'unknown' and acknowledged['target_state_acknowledged_at']
        assert not acknowledged['server_recovery_clearance_required']
        assert wait(http('start', blocked_request, peer=2), 2)['native_operation_outcome'] == 'returned'
        proof['checks'].append('actual-native-clone-with-injected-reply-loss-keeps-all-known-targets-fenced-until-original-process-and-server-quiescence-observation-and-explicit-acknowledgement')
        sql(0, 'CREATE DATABASE sr_topology CHARACTER SET utf8mb4')
        sql(0, 'CREATE TABLE sr_topology.t(id BIGINT PRIMARY KEY,body TEXT,payload LONGBLOB)')
        sql(0, 'INSERT INTO sr_topology.t VALUES(%s,%s,%s)', (9007199254740993, 'native topology 雪', b'\x00\xff'))
        wait_data((0, 1, 2))
        proof['checks'].append('reviewed-native-cluster-create-two-actual-clone-joins-and-independent-wide-unicode-binary-data-on-three-peers')
        response=client.post(registrations[0]['url'],json={'action':'mysql_binlog_backup_protection_list',
            'request':{'all_registrations':True,'limit':100}})
        holds=response.get_json();assert response.status_code==200 and holds['success'],holds
        holds=[row for row in holds['data']['backups'] if row.get('backup_kind')=='mysql_native_topology_recovery']
        assert {row['source']['server_uuid'] for row in holds}=={row['identity']['server_uuid'] for row in seeds}
        assert all(row['state']=='native_topology_reply_observed' and row['native_topology_returned'] is True and
            row['native_protocol_source_uuid_attested'] is False for row in holds)
        proof['checks'].append('actual-native-clone-joins-retain-conservative-archive-holds-reachable-through-authenticated-cross-registration-inspection')
        execute('cluster.set_primary', [{'server_id': registrations[1]['server_id']}])
        assert sql(1, 'SELECT @@super_read_only AS read_only') == [{'read_only': 0}]
        execute('cluster.set_option', ['tag:wide', 2**63], peer=1)
        proof['independent_native_tag'] = sql(1, "SELECT CAST(JSON_EXTRACT(attributes,'$.tags.wide') AS CHAR) AS value FROM mysql_innodb_cluster_metadata.clusters")
        (output/'wide-tag-observation.json').write_text(json.dumps(proof['independent_native_tag'], indent=2)+'\n')
        status = execute('cluster.options', [{}], peer=1, inspection=True)
        assert proof['independent_native_tag'] == [{'value': str(2**63)}], proof['independent_native_tag']
        assert status['result']['native_json_observation']['native_shell_json_signed_limit'] is True
        assert str(2**63) in json.dumps(status['result']['native_json_observation']['tags'])
        # Preserve the source-confirmed native Shell JSON decoder limitation.
        assert str(2**63-1) in status['result']['control']['result_json']
        observed = http('reconcile', {'job_id': status['job_id']}, peer=1)
        assert observed['native_operation_outcome'] == 'returned' and not observed['workload_readiness_verified']
        proof['checks'].append('native-primary-switch-exact-uint64-tag-storage-and-separate-native-Shell-signed-decoder-limitation-observation')
        stale = http('review', {'options': options('cluster.set_option', ['tag:stale', True], 1)}, peer=1)
        execute('cluster.set_option', ['clusterName', 'sr_application_cluster_renamed'], peer=1)
        http('start', {key: stale[key] for key in ('job_id', 'review_digest')} | {'confirmed': True}, peer=1, refused=True)
        proof['checks'].append('native-metadata-identity-change-refuses-stale-reviewed-mutation-before-dispatch')

        if browser_exchange:
            execute('cluster.remove_instance', [{'server_id': registrations[2]['server_id']}], peer=1)
            TopologyTransport.execute = missing_reply
            try:
                browser_unknown = execute('cluster.add_instance', [{'server_id': registrations[2]['server_id']},
                    {'recoveryMethod':'clone','recoveryProgress':0}], expect_returned=False)
            finally: TopologyTransport.execute = original_execute
            assert browser_unknown['native_operation_outcome']=='unknown'
            wait_data((0,1,2))
            desktop(browser_unknown['job_id'])
            browser_acknowledged=http('status',{'job_id':browser_unknown['job_id']})
            assert browser_acknowledged['native_operation_outcome']=='unknown' and browser_acknowledged['target_state_acknowledged_at']
        from mysql_routing_qualification import qualify as qualify_routing
        proof['routing'] = {'cluster': qualify_routing('cluster', 1, execute, http, options, sql)}
        execute('cluster.create_cluster_set', ['sr_application_domain'])
        proof['routing']['cluster_set'] = qualify_routing('cluster_set', 1, execute, http, options, sql)
        execute('cluster_set.dissolve', [{'force': True}], peer=1)
        # Dissolution leaves the data in place and stops native replication.
        for peer in range(3):
            sql(peer, 'SET GLOBAL super_read_only=OFF')
            execute('instance.configure_replica_set', [{'restart': True}], peer)
        execute('instance.create_replica_set', ['sr_application_replicas', {'gtidSetIsComplete': True}], peer=1)
        execute('replica_set.add_instance', [{'server_id': registrations[2]['server_id']},
            {'recoveryMethod': 'clone', 'recoveryProgress': 0}], peer=1)
        execute('replica_set.set_primary', [{'server_id': registrations[2]['server_id']}], peer=1)
        assert sql(2, 'SELECT @@super_read_only AS read_only') == [{'read_only': 0}]
        wait_data((1, 2))
        execute('replica_set.status', [{'extended': 1}], peer=2, inspection=True)
        proof['routing']['replica_set'] = qualify_routing('replica_set', 2, execute, http, options, sql)
        execute('replica_set.dissolve', [{'force': True}], peer=2)
        proof['checks'].append('native-replicaset-create-uri-typed-clone-join-primary-switch-data-observation-and-dissolution')
        from mysql_topology_lingering_qualification import qualify as lingering, qualify_privileges
        with app.test_request_context('/'):
            native_client, route = context(service, db.session.get(Server, registrations[0]['server_id']))
            oracle = native_client._connector(host=routes[0]['host'],port=routes[0]['port'],
                user='root',password=password,use_pure=not use_c,autocommit=True)
            try:
                proof['privilege_profiles']=qualify_privileges(native_client,oracle,routes[0],password,use_c=use_c)
                proof['lingering_server_worker']=lingering(native_client,oracle,routes[0],password,output/'native-lingering-worker')
            finally:native_client._discard_failed_session(oracle)
        proof['complete'] = True
    finally:
        if http_server: http_server.shutdown(); http_server.server_close()
        for name in ('mysql_topology_jobs', 'mysql_binlog_replay_jobs'):
            jobs = getattr(service, name, None)
            if jobs: jobs.close()
        (output/'summary.json').write_text(json.dumps(proof, indent=2)+'\n')
    return proof


def browser(base_url, output, request, binary, driver_binary):
    from selenium import webdriver
    from selenium.webdriver import ActionChains
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
    from cdeadmin_ui_evidence import ensure_data_explorer, expand
    driver = None
    try:
        options = webdriver.ChromeOptions(); options.binary_location = binary
        for flag in ('--headless=new', '--no-sandbox', '--disable-dev-shm-usage', '--window-size=1800,1200'):
            options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'))
        options.add_experimental_option('prefs', {'download.default_directory': str(output/'browser-downloads'),
            'download.prompt_for_download': False})
        options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
        driver = webdriver.Chrome(options=options, service=Service(driver_binary))
        driver.get(base_url+'/browser/'); wait = WebDriverWait(driver, 120,
            ignored_exceptions=(StaleElementReferenceException,))
        diagnostics='''window.srTopologyApi=[];
const send=XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.send=function(body){
  let request;try{request=JSON.parse(body);}catch(e){}
  if(request?.action?.startsWith('mysql_topology_'))this.addEventListener('load',()=>{
    let response;try{response=JSON.parse(this.responseText);}catch(e){}
    window.srTopologyApi.push({action:request.action,status:this.status,error:response?.errormsg || null});
    if(window.srTopologyApi.length>20)window.srTopologyApi.shift();
  });
  return send.apply(this,arguments);
};'''
        def target(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR, '.file-name') if node.is_displayed() and
                browser.execute_script('const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);', node, request['server_id'])), None)
        for attempt in range(2):
            if attempt:driver.get(base_url+'/browser/')
            ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
            try:
                selected=WebDriverWait(driver,30,ignored_exceptions=(StaleElementReferenceException,)).until(target)
                break
            except TimeoutException:
                driver.save_screenshot(str(output/('native-tree-navigation-'+str(attempt)+'.png')))
                if attempt:raise
        # No provider action has occurred before the optional navigation retry.
        driver.execute_script(diagnostics)
        ActionChains(driver).context_click(selected).perform()
        for label in ('Availability', 'MySQL native topologies...'):
            wait.until(lambda b: next((node for node in b.find_elements(By.CSS_SELECTOR, '[role="menuitem"]') if
                node.is_displayed() and node.text.strip() == label), None)).click()
        def click(label):
            def attempt(browser):
                for node in browser.find_elements(By.TAG_NAME, 'button'):
                    if node.is_enabled() and node.get_attribute('textContent').strip() == label:
                        browser.execute_script('arguments[0].scrollIntoView({block:"center"});', node)
                        if node.is_displayed(): node.click(); return True
                return False
            wait.until(attempt)
        def reviewed(browser):
            errors=[node.get_attribute('textContent') for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]')
                if node.get_attribute('class') and 'MuiAlert-colorError' in node.get_attribute('class')]
            if errors:raise AssertionError('Desktop review refused: '+'; '.join(errors))
            return next(iter(browser.find_elements(By.CSS_SELECTOR,'[aria-label="Native topology review"]')),None)
        def control(label,textarea=False):
            tag='textarea' if textarea else 'input'
            def find(browser):
                for item in browser.find_elements(By.TAG_NAME,'label'):
                    if not item.get_attribute('textContent').startswith(label):continue
                    identifier=item.get_attribute('for')
                    if not identifier:continue
                    for node in browser.find_elements(By.ID,identifier):
                        if node.tag_name!=tag or node.get_property('readOnly') or node.get_attribute('aria-hidden')=='true':continue
                        browser.execute_script('arguments[0].scrollIntoView({block:"center"});',node)
                        if node.is_displayed() and node.is_enabled():return node
                return None
            return wait.until(find)
        def field(label, value, textarea=False):
            node=control(label,textarea)
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});', node)
            node.send_keys(Keys.CONTROL, 'a'); node.send_keys(Keys.BACKSPACE); node.send_keys(value)
            wait.until(lambda _browser: control(label,textarea).get_attribute('value') == value)
        click('Load native topology methods')
        if request.get('uncertain_job_id'):
            click('Load native topology jobs');click('Inspect topology job '+request['uncertain_job_id'])
            click('Observe current topology target')
            wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,'[aria-label="Native recovery member observations"]'))
            field('Confirm uncertain topology target UUID',request['target_uuid'])
            click('Acknowledge observed topology target')
            wait.until(lambda b:any('Observed target state acknowledged.' in node.get_attribute('textContent') for node in b.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        click('Inspect topology seed')
        wait.until(lambda b: b.find_elements(By.CSS_SELECTOR, '[aria-label="Native topology seed"]'))
        click('Run native topology inspection')
        wait.until(lambda b: any('outcome: returned.' in node.get_attribute('textContent') for node in b.find_elements(By.CSS_SELECTOR, '[role="alert"]')))
        click('Load registered topology instances')
        for index in request.get('recovery_member_indexes',[0,1,2]):
            checkbox = wait.until(lambda b: b.find_element(By.CSS_SELECTOR, '[aria-label="Observe recovery member Owned MySQL topology '+str(index)+'"]'))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});', checkbox)
            checkbox.click()
        # The native selector is a MUI listbox; choose its actual operation label.
        selector = driver.find_element(By.XPATH, '//label[contains(text(),"Native topology method")]/following::*[@role="combobox"][1]')
        selector.click()
        wait.until(lambda b: next((node for node in b.find_elements(By.CSS_SELECTOR, '[role="option"]') if node.text == 'cluster.set_option'), None)).click()
        field('Native topology arguments', '["tag:browserWide",9223372036854775808]', True)
        field('Confirm topology seed UUID', request['target_uuid'])
        click('Review native topology change')
        review = wait.until(reviewed)
        assert '9223372036854775808' in review.get_attribute('textContent')
        click('Confirm and start native topology change')
        wait.until(lambda b: any('outcome: returned.' in node.get_attribute('textContent') for node in b.find_elements(By.CSS_SELECTOR, '[role="alert"]')))
        tags = wait.until(lambda b: b.find_element(By.CSS_SELECTOR, '[aria-label="Native topology stored tag JSON"]'))
        assert '9223372036854775808' in tags.get_attribute('textContent')
        assert any('options decoding can clamp' in node.get_attribute('textContent') for node in driver.find_elements(By.CSS_SELECTOR, '[role="alert"]'))
        click('Observe current topology target')
        wait.until(lambda b: any('native_lock_free' in node.get_attribute('textContent') for node in b.find_elements(By.TAG_NAME, 'pre')))
        def select_method(identifier):
            selector=driver.find_element(By.XPATH, '//label[contains(text(),"Native topology method")]/following::*[@role="combobox"][1]')
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',selector)
            selector.click()
            option=wait.until(lambda b: next((node for node in b.find_elements(By.CSS_SELECTOR, '[role="option"]') if node.text == identifier), None))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',option)
            option.click()
        def change(identifier, arguments, guideline=None):
            select_method(identifier)
            if guideline is not None:field('Native routing guideline name', guideline)
            if arguments is not None:field('Native topology arguments', json.dumps(arguments), True)
            click('Review native topology change')
            wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,'[aria-label="Native topology review"]'))
            click('Confirm and start native topology change')
            wait.until(lambda b: any('outcome: returned.' in node.get_attribute('textContent') for node in b.find_elements(By.CSS_SELECTOR, '[role="alert"]')))
        if request.get('account_setup'):
            select_method('cluster.setup_admin_account')
            field('Native topology arguments',json.dumps([{'user':UI_ACCOUNT_USER,'host':'%'},{'passwordExpiration':30}]),True)
            checkbox=driver.find_element(By.XPATH,'//label[contains(.,"Set account password at dispatch")]//input[@type="checkbox"]')
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',checkbox);checkbox.click()
            field('Native account password',UI_ACCOUNT_PASSWORD)
            click('Review native topology change');review=wait.until(reviewed)
            assert UI_ACCOUNT_PASSWORD not in review.get_attribute('textContent')
            click('Confirm and start native topology change')
            wait.until(lambda b:any('outcome: returned.' in node.get_attribute('textContent') for node in b.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
            assert control('Native account password').get_attribute('value')==''
            wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,'[aria-label="Native account state observation"]'))
            checkbox=driver.find_element(By.XPATH,'//label[contains(.,"Set account password at dispatch")]//input[@type="checkbox"]')
            if checkbox.is_selected():
                driver.execute_script('arguments[0].scrollIntoView({block:"center"});',checkbox);checkbox.click()
            change('cluster.setup_admin_account',[{'user':UI_ACCOUNT_USER,'host':'%'},{'update':True,'passwordExpiration':14}])
            severe=[entry for entry in driver.get_log('browser') if entry['level']=='SEVERE']
            (output/'browser-console.json').write_text(json.dumps(severe,indent=2)+'\n')
            driver.save_screenshot(str(output/'native-account-setup.png'));assert not severe,severe
            return {'complete':True,'checks':['native-context-menu','native-read-only-inspection',
                'exact-uint64-review','native-account-review-excludes-password','explicit-private-password-dispatch',
                'password-field-cleared-after-dispatch','native-account-update-preserves-password'], 'severe_errors':0}
        guideline='sr_desktop_routes'
        change('cluster.create_routing_guideline',[guideline])
        change('cluster.guideline.add_destination',['desktop_primary','$.server.memberRole = PRIMARY'],guideline)
        change('cluster.guideline.add_route',['desktop_route','$.session.targetPort = $.router.port.ro',
            ['round-robin(desktop_primary)'],{'enabled':False}],guideline)
        # Execute the displayed native templates unchanged, including optional
        # dictionary omission, ROLE/session expressions and real class names.
        change('cluster.create_routing_guideline',None)
        change('cluster.guideline.add_destination',None,guideline)
        change('cluster.guideline.add_route',None,guideline)
        change('cluster.guideline.set_destination_option',None,guideline)
        change('cluster.guideline.set_route_option',None,guideline)
        select_method('cluster.guideline.export');click('Run native topology inspection')
        click('Download native routing guideline JSON')
        downloaded=output/'browser-downloads/mysql-routing-guideline.json'
        wait.until(lambda _b: downloaded.is_file())
        document=json.loads(downloaded.read_text())
        assert document['name']==guideline
        assert any(row['name']=='desktop_route' and row['enabled'] is False for row in document['routes']),document
        select_method('cluster.import_routing_guideline')
        invalid=output/'invalid-utf8-guideline.json';invalid.write_bytes(b'{"name":"\xff"}')
        before=control('Native topology arguments',True).get_attribute('value')
        driver.find_element(By.CSS_SELECTOR,'input[aria-label="Routing guideline JSON file"]').send_keys(str(invalid))
        wait.until(lambda b:any('must contain valid UTF-8' in node.get_attribute('textContent') for node in b.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        assert control('Native topology arguments',True).get_attribute('value')==before
        driver.find_element(By.CSS_SELECTOR,'input[aria-label="Routing guideline JSON file"]').send_keys(str(downloaded))
        wait.until(lambda _b: guideline in control('Native topology arguments',True).get_attribute('value'))
        # Explicit replacement is reviewed with the native force option.
        field('Native topology arguments', '['+downloaded.read_text()+',{"force":true}]',True)
        click('Review native topology change');wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,'[aria-label="Native topology review"]'))
        click('Confirm and start native topology change')
        wait.until(lambda b: any('outcome: returned.' in node.get_attribute('textContent') for node in b.find_elements(By.CSS_SELECTOR, '[role="alert"]')))
        severe = [entry for entry in driver.get_log('browser') if entry['level'] == 'SEVERE']
        (output/'browser-console.json').write_text(json.dumps(severe, indent=2)+'\n')
        driver.save_screenshot(str(output/'native-topology.png'))
        assert not severe, severe
        return {'complete': True, 'checks': ['native-context-menu', 'read-only-native-inspection',
            'exact-uint64-argument-review', 'explicit-native-mutation', 'separate-target-observation',
            *(['native-uncertain-clone-recovery-observation-and-explicit-target-acknowledgement'] if request.get('uncertain_job_id') else []),
            'native-guideline-create-destination-route-edit-download-and-upload-reviewed-force-import',
            'invalid-UTF8-file-is-refused-without-replacement-or-import'], 'severe_errors': 0}
    except Exception:
        if driver:
            driver.save_screenshot(str(output/'native-topology-failure.png'))
            (output/'browser-failure-alerts.json').write_text(json.dumps([node.get_attribute('textContent') for node in driver.find_elements(By.CSS_SELECTOR,'[role="alert"]')],indent=2)+'\n')
            (output/'browser-failure-console.json').write_text(json.dumps(driver.get_log('browser'),indent=2)+'\n')
            (output/'browser-failure-api.json').write_text(json.dumps(driver.execute_script('return window.srTopologyApi || []'),indent=2)+'\n')
        raise
    finally:
        if driver: driver.quit()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True); parser.add_argument('--routes', required=True)
    parser.add_argument('--password-env', required=True); parser.add_argument('--mysql-shell', required=True)
    parser.add_argument('--use-c', action='store_true'); parser.add_argument('--browser-exchange', action='store_true')
    parser.add_argument('--routing-only', action='store_true')
    parser.add_argument('--desktop-only', action='store_true')
    parser.add_argument('--accounts-only', action='store_true')
    parser.add_argument('--account-contexts', nargs='+', choices=['cluster','cluster_set','replica_set'])
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if output == ROOT or ROOT in output.parents: raise ValueError('Keep native evidence outside source')
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.environ['CDEADMIN_MYSQLSH_BINARY'] = args.mysql_shell
    selected = json.loads(Path(args.routes).read_text())
    if not isinstance(selected, list) or len(selected) != 3: raise ValueError('Select three disposable native peers')
    qualify(output, selected, os.environ[args.password_env], use_c=args.use_c,
        browser_exchange=args.browser_exchange, routing_only=args.routing_only, desktop_only=args.desktop_only, accounts_only=args.accounts_only,
        account_contexts=args.account_contexts)

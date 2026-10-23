"""Owned native full physical backup/prepare/copy-back and desktop acceptance."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'web'), str(ROOT/'tools')]
BACKEND = 'percona/percona-xtrabackup@sha256:580747a61714d1884040794fc8a144179f5e3fe6ae839701d8958fe73a4e5e2b'


def prepare_fixture(output, image):
    build = output/'fixture-build'; build.mkdir()
    key = build/'private-key'
    subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(key)],check=True)
    context = build/'context'; context.mkdir()
    (context/'authorized_keys').write_bytes(key.with_suffix('.pub').read_bytes())
    (context/'start.sh').write_text('#!/bin/bash\nset -e\n/usr/sbin/sshd -D >/tmp/physical-sshd.log 2>&1 &\nexec /usr/local/bin/docker-entrypoint.sh "$@"\n')
    (context/'Dockerfile').write_text('FROM '+BACKEND+' AS pxb\nFROM mysql:9.7.0\nUSER root\n'
        'RUN microdnf install -y python3 openssh-server procps-ng && microdnf clean all && ssh-keygen -A && mkdir -p /run/sshd /root/.ssh && chmod 700 /root/.ssh\n'
        'COPY --from=pxb /usr/bin/xtrabackup /usr/bin/xtrabackup\nCOPY --from=pxb /usr/lib/private /usr/lib/private\n'
        'COPY authorized_keys /root/.ssh/authorized_keys\n'
        'RUN chmod 600 /root/.ssh/authorized_keys && printf "%s\\n" "PermitRootLogin prohibit-password" "PasswordAuthentication no" "UsePAM no" "PrintMotd no" > /etc/ssh/sshd_config.d/physical-fixture.conf && xtrabackup --version\n'
        'COPY start.sh /opt/physical-start.sh\nENTRYPOINT ["/bin/bash","/opt/physical-start.sh"]\nCMD ["mysqld"]\n')
    with (output/'fixture-build.log').open('w') as log:
        subprocess.run(['docker','build','-t',image,str(context)],stdout=log,stderr=subprocess.STDOUT,check=True)
    return key


def qualify(output, image, key=None, prepare=False, browser_binary=None, driver_binary=None):
    import config  # noqa: F401
    from flask import url_for
    from unittest.mock import patch
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    from cdeadmin_mysql_online_ddl_qualification import registration
    from cdeadmin_mysql_family_object_live_orchestrator import _run, _wait_until_ready, _root_connection, _published_port, _image_identity
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents: raise ValueError('Keep private qualification outside source')
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    proof = {'complete':False,'interfaces':[],'history_testing':'not run','source_sha256':{},'owned_servers_stopped':False,'owned_physical_volume_removed':False}
    paths = ['web/pgadmin/cdeadmin/providers/mysql_family/mysql_physical_worker.py','web/pgadmin/cdeadmin/providers/mysql_family/mysql_physical_transport.py',
        'web/pgadmin/cdeadmin/workspace/mysql_physical_service.py','web/pgadmin/cdeadmin/workspace/service.py','web/pgadmin/static/js/Dialogs/MySQLPhysical.jsx',
        'web/pgadmin/static/js/Dialogs/index.jsx','web/pgadmin/cdeadmin/context_menu.py','web/pgadmin/browser/server_groups/servers/__init__.py',
        'web/pgadmin/static/vendor/ddn/current/resource-manifest.json',str(Path(__file__).relative_to(ROOT))]
    proof['source_sha256'] = {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
    names = []; volume = 'sr-physical-'+secrets.token_hex(8); root = None
    data_volumes = []
    try:
        key = prepare_fixture(output,image) if prepare else Path(key).resolve(strict=True)
        proof['fixture_image'] = _image_identity(image)
        _run(['docker','volume','create',volume])
        name = volume+'-source'; names.append(name)
        _run(['docker','run','--rm','-d','--name',name,'--hostname',name,'-v',volume+':/var/backups/scratchrobin',
            '-e','MYSQL_ALLOW_EMPTY_PASSWORD=yes','-p','127.0.0.1::3306','-p','127.0.0.1::22',image,
            'mysqld','--server-id=101','--gtid-mode=ON','--enforce-gtid-consistency=ON','--log-bin=physical'])
        mounts=json.loads(_run(['docker','inspect','--format','{{json .Mounts}}',name]).stdout)
        data_volumes=[m['Name'] for m in mounts if m['Type']=='volume' and m['Destination']=='/var/lib/mysql']
        proof['owned_source_data_volumes']=data_volumes
        port = _wait_until_ready('mysql',name,300); ssh = _published_port(_run(['docker','port',name,'22/tcp']).stdout)
        host_key = _run(['docker','exec',name,'cat','/etc/ssh/ssh_host_ed25519_key.pub']).stdout.strip()
        root = _root_connection('mysql',port); root.autocommit=True
        password = 'physical LF\nquote"slash\\雪-'+secrets.token_urlsafe(16)
        with root.cursor() as cursor:
            cursor.execute('CREATE DATABASE sr_osc'); cursor.execute('USE sr_osc')
            cursor.execute('CREATE TABLE t(id BIGINT UNSIGNED PRIMARY KEY,note VARCHAR(80),b LONGBLOB) ENGINE=InnoDB')
            cursor.execute('INSERT INTO t VALUES(%s,%s,%s)',(18446744073709551615,'native 雪',b'\x00\xff'))
            cursor.execute('CREATE TABLE m(id INT PRIMARY KEY,note VARCHAR(80)) ENGINE=MyISAM');cursor.execute("INSERT INTO m VALUES(1,'native MyISAM')")
            cursor.execute('CREATE TABLE c(note VARCHAR(80) NOT NULL) ENGINE=CSV');cursor.execute("INSERT INTO c VALUES('native CSV')")
            cursor.execute('CREATE VIEW v AS SELECT id,note FROM t');cursor.execute('CREATE PROCEDURE p() SELECT * FROM t')
            cursor.execute("CREATE USER 'sr_physical'@'%' IDENTIFIED BY %s",(password,));cursor.execute("GRANT ALL PRIVILEGES ON *.* TO 'sr_physical'@'%' WITH GRANT OPTION")
            cursor.execute('CREATE ROLE `physical role 雪`')
            cursor.execute("GRANT `physical role 雪` TO 'sr_physical'@'%'")
            cursor.execute("SET DEFAULT ROLE `physical role 雪` TO 'sr_physical'@'%'")
            cursor.execute('CREATE TABLE pending(id INT PRIMARY KEY)')
        app = setup_application(output)
        for use_c in (False,True):
            sid,target,_post = registration(app,{'host':'127.0.0.1','port':port},password,use_c,username='sr_physical')
            from pgadmin.model import User,Server
            with app.test_request_context('/'):
                registered = Server.query.get(sid); uid = User.query.first().id
                endpoint = url_for('NODE-server.cde_workspace_id',gid=registered.servergroup_id,sid=sid)
            client = app.test_client()
            with client.session_transaction() as session: session['_user_id'],session['_fresh']=str(uid),True
            def post(operation,request,refused=False):
                reply = client.post(endpoint,json={'action':'mysql_physical_'+operation,'request':request})
                data = reply.get_json()
                if refused: assert not data.get('success'),data;return data
                assert reply.status_code==200 and data.get('success'),data
                assert reply.headers['Cache-Control']=='no-store'
                return data['data']
            credentials = {'private_key':key.read_text()}
            selected = {'connection':{'host':'127.0.0.1','port':ssh,'username':'root','host_key':host_key,'authentication':'private_key','platform':'posix','python':'/usr/bin/python3'},
                'workspace':'/var/backups/scratchrobin/jobs','executable':'/usr/bin/xtrabackup','mysql':'/usr/bin/mysql',
                'phase':'backup','sql_host':'127.0.0.1','sql_port':3306,'input_job_id':None,'parallel':2,'memory_bytes':268435456,'timeout_seconds':120,'accept_release_candidate':True}
            def review(phase,input_job=None):
                return post('review',{'options':{**selected,'phase':phase,'input_job_id':input_job},'credentials':credentials})
            def start(value):
                return post('start',{'job_id':value['job_id'],'review_digest':value['review_digest'],'confirmed':True,'delegate_database_credentials':True,'credentials':credentials})
            def terminal(value):
                limit=time.monotonic()+180
                while time.monotonic()<limit:
                    value=post('reconcile',{'job_id':value['job_id'],'credentials':credentials})
                    observed=value.get('remote_observation') or {}
                    if observed.get('supervisor_finished'):
                        if observed.get('return_code')!=0 or not value['file_verification_confirmed']:
                            (output/'native-failure.json').write_text(json.dumps(value,indent=2)+'\n')
                            raise RuntimeError('Native physical operation did not qualify; inspect owned native-failure.json')
                        return value
                    time.sleep(.15)
                raise TimeoutError('Owned native physical process did not finish')
            checks=[]
            root.autocommit=False
            with root.cursor() as pending:
                pending.execute('INSERT INTO sr_osc.pending VALUES(%s)',(100+int(use_c),))
                pending.execute('SAVEPOINT physical_guard')
                pending.execute("SELECT CAST('original native warning' AS UNSIGNED)");pending.fetchall()
                pending.execute('SHOW COUNT(*) WARNINGS'); warning_count=pending.fetchone()[0];assert warning_count
            backup_review=review('backup');before=post('status',{'job_id':backup_review['job_id']})
            assert before['state']=='reviewed' and before['source_connection_class']==('CharsetCMySQLConnection' if use_c else 'CharsetMySQLConnection')
            post('start',{'job_id':before['job_id'],'review_digest':before['review_digest'],'confirmed':False,'delegate_database_credentials':True,'credentials':credentials},refused=True)
            from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_transport as transport
            original=transport.Transport.request
            def lost(instance,request,*args,**kwargs):
                result=original(instance,request,*args,**kwargs)
                if request['action']=='start':raise transport.HostError('Injected lost reply after actual remote supervisor admission')
                return result
            with patch.object(transport.Transport,'request',lost):
                post('start',{'job_id':before['job_id'],'review_digest':before['review_digest'],'confirmed':True,'delegate_database_credentials':True,'credentials':credentials},refused=True)
            backup=terminal(before);assert backup['state']=='unknown' and backup['original_dispatch_reply_unchanged']
            assert start(before)['state']=='unknown'
            assert root.in_transaction
            with root.cursor() as pending:
                pending.execute('SHOW COUNT(*) WARNINGS');assert pending.fetchone()[0]==warning_count
                pending.execute('ROLLBACK TO SAVEPOINT physical_guard')
                pending.execute('SELECT COUNT(*) FROM sr_osc.pending');assert pending.fetchone()[0]==1
            root.rollback();root.autocommit=True
            checks.append('independent-pending-user-transaction-savepoint-and-original-warning-area-preserved')
            checks.append('explicit-delegation-native-source-identity-and-unknown-original-dispatch-with-independent-supervisor-completion-no-replay')
            prepared=terminal(start(review('prepare',backup['job_id'])))
            assert prepared['remote_observation']['artifact']['prepared']
            copied=terminal(start(review('copy_back',prepared['job_id'])))
            assert copied['remote_observation']['restored_files']['database_started'] is False
            checks.append('native-full-backup-immutable-prepare-and-isolated-copy-back-with-exact-byte-manifests')
            target_name=volume+'-target-'+str(use_c);names.append(target_name)
            _run(['docker','run','--rm','--user','0','-v',volume+':/physical','--entrypoint','chown','mysql:9.7.0','-R','mysql:mysql','/physical/jobs/'+copied['job_id']+'/artifact'])
            _run(['docker','run','--rm','-d','--name',target_name,'--mount','type=volume,source='+volume+',target=/var/lib/mysql,volume-subpath=jobs/'+copied['job_id']+'/artifact',
                '-p','127.0.0.1::3306','mysql:9.7.0','--server-id=202','--gtid-mode=ON','--enforce-gtid-consistency=ON','--log-bin=recovered'])
            recovered=_root_connection('mysql',_wait_until_ready('mysql',target_name,120));recovered.autocommit=True
            try:
                with recovered.cursor() as cursor:
                    cursor.execute('SELECT id,note,b FROM sr_osc.t');assert cursor.fetchall()==[(18446744073709551615,'native 雪',b'\x00\xff')]
                    cursor.execute('SELECT * FROM sr_osc.m');assert cursor.fetchall()==[(1,'native MyISAM')]
                    cursor.execute('SELECT * FROM sr_osc.c');assert cursor.fetchall()==[('native CSV',)]
                    cursor.execute('SELECT COUNT(*) FROM sr_osc.pending');assert cursor.fetchone()[0]==0
                    for what in ('VIEW sr_osc.v','PROCEDURE sr_osc.p'):cursor.execute('SHOW CREATE '+what);assert cursor.fetchone()
            finally:recovered.close();_run(['docker','rm','-fv',target_name]);names.remove(target_name)
            checks.append('independent-native-MySQL9.7-boot-and-InnoDB-MyISAM-CSV-unsigned64-Unicode-BLOB-view-routine-recovery')
            output_value=post('output',{'job_id':backup['job_id'],'credentials':credentials})
            assert 'completed OK!' in output_value['outputs']['stderr'] and password not in json.dumps(output_value)
            assert 'BEGIN OPENSSH PRIVATE KEY' not in json.dumps(backup)
            raw=_run(['docker','exec',name,'cat','/var/backups/scratchrobin/jobs/'+backup['job_id']+'/request.json']).stdout
            assert json.loads(raw)['database_credentials'] is None and password not in raw
            checks.append('bounded-native-output-and-private-password-LF-quotes-backslash-Unicode-with-confirmed-credential-cleanup')
            proof['interfaces'].append({'use_c':use_c,'native_interface':before['source_connection_class'],'complete':True,'checks':checks,
                'jobs':[backup['job_id'],prepared['job_id'],copied['job_id']]})
        if browser_binary:
            ui_password=secrets.token_urlsafe(24)
            with root.cursor() as cursor:
                cursor.execute("CREATE USER 'sr_physical_ui'@'%' IDENTIFIED BY %s",(ui_password,))
                cursor.execute("GRANT ALL PRIVILEGES ON *.* TO 'sr_physical_ui'@'%' WITH GRANT OPTION")
            sid,_target,_post=registration(app,{'host':'127.0.0.1','port':port},ui_password,True,username='sr_physical_ui')
            proof['browser']=browser(app,output,sid,ui_password,selected,credentials,browser_binary,driver_binary)
        proof['complete']=True
    finally:
        if root is not None:root.close()
        for name in reversed(names):_run(['docker','rm','-fv',name],check=False)
        remaining=_run(['docker','ps','-aq','--filter','name='+volume],check=False)
        proof['owned_servers_stopped']=remaining.returncode==0 and not remaining.stdout.strip()
        _run(['docker','volume','rm',volume],check=False)
        volumes=_run(['docker','volume','ls','-q','--filter','name='+volume],check=False)
        proof['owned_physical_volume_removed']=volumes.returncode==0 and volume not in volumes.stdout.splitlines()
        known=_run(['docker','volume','ls','-q'],check=False)
        proof['owned_source_data_volumes_removed']=known.returncode==0 and not set(data_volumes).intersection(known.stdout.splitlines())
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
        if proof['complete'] and not (proof['owned_servers_stopped'] and proof['owned_physical_volume_removed'] and proof['owned_source_data_volumes_removed']):
            raise RuntimeError('Owned native physical qualification resources remain; inspect summary.json')
    return proof


def browser(app,output,sid,password,selected,credentials,binary,driver_binary):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.common.exceptions import StaleElementReferenceException
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer,expand,invoke_context_action,complete_endpoint_prompt
    http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
    try:
        chrome=webdriver.ChromeOptions();chrome.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1900,1600'):chrome.add_argument(flag)
        chrome.add_argument('--user-data-dir='+str(output/'browser-profile'));chrome.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=chrome,service=Service(driver_binary));driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/')
        wait=WebDriverWait(driver,120,ignored_exceptions=(StaleElementReferenceException,));ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
        def owned(b):
            return next((n for n in b.find_elements(By.CSS_SELECTOR,'.file-name') if n.is_displayed() and b.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',n,sid)),None)
        node=wait.until(owned)
        invoke_context_action(wait,driver,node,('Backup','MySQL physical backups...'),handle_endpoint_prompt=False)
        complete_endpoint_prompt(driver,password,timeout=5)
        def click(text):
            node=wait.until(lambda b:next((e for e in b.find_elements(By.TAG_NAME,'button') if e.is_displayed() and e.is_enabled() and e.text==text),None))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',node);node.click()
        def field(text):
            label=wait.until(lambda b:next((e for e in b.find_elements(By.TAG_NAME,'label') if e.is_displayed() and e.text==text),None))
            return driver.find_element(By.ID,label.get_attribute('for'))
        def fill(text,value):
            node=field(text);driver.execute_script('arguments[0].scrollIntoView({block:"center"});',node)
            node.send_keys(Keys.CONTROL,'a');node.send_keys(Keys.BACKSPACE);node.send_keys(str(value))
        def check(text):
            label=wait.until(lambda b:b.find_element(By.XPATH,'//label[normalize-space()="'+text+'"]'))
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',label)
            if not label.find_element(By.CSS_SELECTOR,'input').is_selected():label.click()
        for label,value in [('Physical SSH host',selected['connection']['host']),('Physical SSH port',selected['connection']['port']),
            ('Physical SSH user','root'),('Pinned physical SSH public key',selected['connection']['host_key']),
            ('Physical SSH private key',credentials['private_key']),('Private physical workspace',selected['workspace']),('Physical native timeout seconds',120)]:fill(label,value)
        assert driver.execute_script('const e=arguments[0],r=e.getBoundingClientRect(),p=e.parentElement.getBoundingClientRect();return r.top>=p.top-1 && r.bottom<=p.bottom+1 && r.right<=p.right+1;',field('Physical SSH private key'))
        check('I accept this pinned XtraBackup release candidate for this physical operation.')
        checks=[]
        for index in range(3):
            click('Review native physical job');wait.until(lambda b:b.find_element(By.CSS_SELECTOR,'[aria-label="Native physical review"]'))
            check('I confirm this exact reviewed physical operation.')
            if index==0:check('Delegate the registered database password privately to the pinned SSH host.')
            click('Start reviewed physical job')
            def receipt(b):
                node=b.find_element(By.CSS_SELECTOR,'[aria-label="Native physical receipt"]')
                return json.loads(node.text)
            final=wait.until(lambda b:(value if (value:=receipt(b)).get('file_verification_confirmed') else None))
            assert final['state']=='native_returned' and final['remote_observation']['credential_cleanup_confirmed']
            if index==0:click('Use backup for separate prepare');checks.append('built-reviewed-native-full-backup-and-private-credential-delegation')
            elif index==1:click('Use prepared artifact for isolated copy-back');checks.append('built-immutable-prepare-from-selected-native-artifact')
            else:checks.append('built-isolated-copy-back-with-independent-file-verification-and-no-database-start')
        click('Inspect native physical output');wait.until(lambda b:b.find_element(By.CSS_SELECTOR,'[aria-label="Native physical output"]'))
        fill('Physical SSH private key','')
        driver.save_screenshot(str(output/'native-physical.png'))
        errors=[row for row in driver.get_log('browser') if row['level']=='SEVERE'];assert not errors,errors
        return {'complete':True,'version':driver.capabilities['browserVersion'],'checks':checks,'console_errors':errors}
    except Exception:
        if driver:
            driver.save_screenshot(str(output/'browser-failure.png'));(output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text)
        raise
    finally:
        if driver:driver.quit()
        http.shutdown();thread.join(timeout=10)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--fixture-image',default='sr-mysql-physical:phase207')
    parser.add_argument('--private-key');parser.add_argument('--prepare-fixture',action='store_true');parser.add_argument('--browser-binary');parser.add_argument('--driver-binary')
    args=parser.parse_args();qualify(args.output,args.fixture_image,args.private_key,args.prepare_fixture,args.browser_binary,args.driver_binary)

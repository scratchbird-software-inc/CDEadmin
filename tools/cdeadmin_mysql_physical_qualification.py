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


def qualify(output, image, key=None, prepare=False, browser_binary=None, driver_binary=None, connections=False,replay=False):
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
        'web/pgadmin/cdeadmin/providers/mysql_family/mysql_recovery_worker.py',
        'web/pgadmin/cdeadmin/workspace/mysql_physical_service.py','web/pgadmin/cdeadmin/workspace/service.py','web/pgadmin/static/js/Dialogs/MySQLPhysical.jsx',
        'web/pgadmin/static/js/Dialogs/index.jsx','web/pgadmin/cdeadmin/context_menu.py','web/pgadmin/browser/server_groups/servers/__init__.py',
        'web/pgadmin/static/vendor/ddn/current/resource-manifest.json',str(Path(__file__).relative_to(ROOT))]
    proof['source_sha256'] = {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
    if connections:
        extras=['web/pgadmin/cdeadmin/providers/mysql_family/mysql_recovery_bridge.py','web/pgadmin/cdeadmin/providers/mysql_family/mysql_recovery_stream.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/mysql_charsets.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/mysql_connections.py','web/pgadmin/cdeadmin/providers/mysql_family/provider.py',
            'web/pgadmin/cdeadmin/endpoints/service.py','web/pgadmin/cdeadmin/workspace/mysql_recovery_connections.py','web/pgadmin/static/js/Dialogs/index.jsx',
            'tools/cdeadmin_mysql_recovery_connection_qualification.py']
        proof['source_sha256'].update({p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in extras})
    if replay:
        for p in ('tools/cdeadmin_mysql_physical_replay_qualification.py','web/pgadmin/cdeadmin/workspace/mysql_binlog_replay_service.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/mysql_raw_binlog_replay.py',
            'web/pgadmin/cdeadmin/workspace/mysql_binlog_replay_jobs.py','web/pgadmin/static/js/Dialogs/MySQLBinlogReplay.jsx',
            'web/pgadmin/cdeadmin/sdk/durable_tool.py','web/pgadmin/cdeadmin/sdk/tool_guardian.py','web/pgadmin/cdeadmin/sdk/tooling.py',
            'tools/cdeadmin_mysql_binlog_replay_workspace_qualification.py'):
            proof['source_sha256'][p]=hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
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
            cursor.execute("INSTALL PLUGIN group_replication SONAME 'group_replication.so'")
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
            def review(phase,input_job=None,gtid_mode='ON',lifetime=None,startup='read_only'):
                extra={'mysqld':'/usr/sbin/mysqld','recovery_gtid_mode':gtid_mode} if phase=='recover' else {}
                if connections and phase=='recover':extra['recovery_port']=33447
                if startup=='replay':extra.update(recovery_mode='replay',recovery_server_id=10001+int(use_c))
                if lifetime is not None:extra['timeout_seconds']=lifetime
                return post('review',{'options':{**selected,'phase':phase,'input_job_id':input_job,**extra},'credentials':credentials})
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
            (output/'native-backup-configuration.txt').write_text(_run(['docker','exec',name,'cat',selected['workspace']+'/'+prepared['job_id']+'/artifact/backup-my.cnf']).stdout)
            runtime_review=review('recover',copied['job_id'])
            post('start',{'job_id':runtime_review['job_id'],'review_digest':runtime_review['review_digest'],'confirmed':True,'delegate_database_credentials':False,'credentials':credentials},refused=True)
            with patch.object(transport.Transport,'request',lost):
                post('start',{'job_id':runtime_review['job_id'],'review_digest':runtime_review['review_digest'],'confirmed':True,'delegate_database_credentials':True,'credentials':credentials},refused=True)
            limit=time.monotonic()+150
            while time.monotonic()<limit:
                runtime=post('reconcile',{'job_id':runtime_review['job_id'],'credentials':credentials})
                if runtime['recovery_running']:break
                if runtime.get('remote_observation',{}).get('supervisor_finished'):
                    (output/'native-failure.json').write_text(json.dumps(runtime,indent=2)+'\n')
                    (output/'native-failure-output.json').write_text(json.dumps(post('output',{'job_id':runtime['job_id'],'credentials':credentials}),indent=2)+'\n')
                    raise RuntimeError('Managed native recovery did not qualify; inspect native-failure.json')
                time.sleep(.2)
            else:raise TimeoutError('Managed native recovery startup was not observed')
            assert runtime['state']=='unknown' and runtime['recovery_sql_startup_observed']
            assert runtime['remote_observation']['sql_identity']['group_replication_autostart']=='OFF'
            native_output=post('output',{'job_id':runtime['job_id'],'credentials':credentials})['outputs']
            assert 'ready for connections' in native_output['native-error.log'].lower()
            assert all(password not in value and 'BEGIN OPENSSH PRIVATE KEY' not in value for value in native_output.values())
            assert start(runtime_review)['state']=='unknown'
            socket=runtime['remote_observation']['socket']
            def recovered_sql(query,check=True):
                return _run(['docker','exec',name,'mysql','--no-defaults','--protocol=socket','--socket='+socket,'--user=root',
                    '--batch','--raw','--skip-column-names','--default-character-set=utf8mb4','--execute='+query],check=check)
            value=json.loads(recovered_sql("SELECT JSON_OBJECT('id',CAST(id AS CHAR),'note',note,'bytes',HEX(b)) FROM sr_osc.t").stdout)
            assert value=={'id':'18446744073709551615','note':'native 雪','bytes':'00FF'}
            assert json.loads(recovered_sql("SELECT JSON_ARRAY((SELECT COUNT(*) FROM sr_osc.m),(SELECT COUNT(*) FROM sr_osc.c),(SELECT COUNT(*) FROM sr_osc.pending))").stdout)==[1,1,0]
            for what in ('VIEW sr_osc.v','PROCEDURE sr_osc.p'):assert recovered_sql('SHOW CREATE '+what).stdout
            assert recovered_sql('INSERT INTO sr_osc.pending VALUES(999)',False).returncode!=0
            connection_proof=None
            if connections:
                from cdeadmin_mysql_recovery_connection_qualification import native_connection
                connection_proof=native_connection(app,client,sid,target,runtime,post,credentials,output,use_c)
                checks.extend(connection_proof['checks'])
            if use_c:
                # Loss of the original supervisor must not require a third-party
                # process tool or authorize a signal to a reused numeric PID.
                pid=runtime['remote_observation']['supervisor_process']['pid']
                _run(['docker','exec',name,'kill','-9',str(pid)])
            stopped=post('cancel',{'job_id':runtime['job_id'],'credentials':credentials})
            limit=time.monotonic()+60
            while time.monotonic()<limit:
                stopped=post('reconcile',{'job_id':runtime['job_id'],'credentials':credentials})
                remote=stopped.get('remote_observation',{})
                if remote.get('process_termination_confirmed') and (use_c or remote.get('supervisor_finished')):break
                time.sleep(.2)
            else:raise TimeoutError('Original native recovery process did not stop')
            assert not stopped['recovery_running'] and stopped['state']=='unknown'
            if use_c:assert stopped['remote_observation']['supervisor_control_unavailable'] and stopped['remote_observation']['native_exit_reply_unknown']
            else:assert stopped['remote_observation']['return_code']==0
            if connection_proof:
                from cdeadmin_mysql_recovery_connection_qualification import stopped_connection
                stopped_connection(app,client,connection_proof,post)
            checks.append('managed-native-recovery-new-UUID-private-socket-read-only-SQL-data-and-definitions-explicit-stop-with-unknown-original-reply')
            if use_c:checks.append('owned-process-descriptor-stop-after-original-supervisor-loss-without-invented-native-exit-reply')
            if replay:
                from cdeadmin_mysql_physical_replay_qualification import native_replay
                checks.extend(native_replay(app,client,sid,root,post,credentials,review,start,copied,output,use_c,
                    browser_binary=browser_binary if use_c else None,driver_binary=driver_binary if use_c else None))
            if not use_c:
                for mode in ('OFF','OFF_PERMISSIVE','ON_PERMISSIVE'):
                    alternate=start(review('recover',copied['job_id'],mode))
                    limit=time.monotonic()+120
                    while time.monotonic()<limit:
                        alternate=post('reconcile',{'job_id':alternate['job_id'],'credentials':credentials})
                        if alternate['recovery_running']:break
                        if alternate.get('remote_observation',{}).get('supervisor_finished'):
                            (output/'native-failure.json').write_text(json.dumps(alternate,indent=2)+'\n');raise RuntimeError('Native GTID recovery mode failed: '+mode)
                        time.sleep(.2)
                    else:raise TimeoutError('Native GTID recovery startup not observed: '+mode)
                    assert alternate['remote_observation']['sql_identity']['gtid_mode']==mode
                    post('cancel',{'job_id':alternate['job_id'],'credentials':credentials})
                    limit=time.monotonic()+60
                    while time.monotonic()<limit:
                        alternate=post('reconcile',{'job_id':alternate['job_id'],'credentials':credentials})
                        if alternate.get('remote_observation',{}).get('supervisor_finished'):break
                        time.sleep(.2)
                    else:raise TimeoutError('Native GTID recovery stop not observed: '+mode)
                    assert alternate['remote_observation']['return_code']==0 and not alternate['recovery_running']
                expiring=start(review('recover',copied['job_id'],lifetime=2));limit=time.monotonic()+60
                while time.monotonic()<limit:
                    expiring=post('reconcile',{'job_id':expiring['job_id'],'credentials':credentials})
                    if expiring.get('remote_observation',{}).get('supervisor_finished'):break
                    time.sleep(.2)
                else:raise TimeoutError('Native recovery lifetime did not stop the original process')
                assert expiring['remote_observation']['lifetime_expired'] and expiring['remote_observation']['process_termination_confirmed']
                checks.append('all-four-native-GTID-modes-and-reviewed-lifetime-shutdown')
            target_name=volume+'-target-'+str(use_c);names.append(target_name)
            _run(['docker','run','--rm','--user','0','-v',volume+':/physical','--entrypoint','chown','mysql:9.7.0','-R','mysql:mysql','/physical/jobs/'+copied['job_id']+'/artifact'])
            _run(['docker','run','--rm','-d','--name',target_name,'--mount','type=volume,source='+volume+',target=/var/lib/mysql,volume-subpath=jobs/'+copied['job_id']+'/artifact',
                '-p','127.0.0.1::3306','mysql:9.7.0','--server-id=202','--gtid-mode=ON','--enforce-gtid-consistency=ON','--log-bin=recovered','--loose-group-replication-start-on-boot=OFF'])
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
                'jobs':[backup['job_id'],prepared['job_id'],copied['job_id'],runtime['job_id']]})
        if browser_binary:
            ui_password=secrets.token_urlsafe(24)
            with root.cursor() as cursor:
                cursor.execute("CREATE USER 'sr_physical_ui'@'%' IDENTIFIED BY %s",(ui_password,))
                cursor.execute("GRANT ALL PRIVILEGES ON *.* TO 'sr_physical_ui'@'%' WITH GRANT OPTION")
            sid,_target,_post=registration(app,{'host':'127.0.0.1','port':port},ui_password,True,username='sr_physical_ui')
            proof['browser']=browser(app,output,sid,ui_password,selected,credentials,browser_binary,driver_binary,connections=connections,replay=replay,replay_source=root)
        proof['complete']=True
    finally:
        if connections:
            from pgadmin.cdeadmin.providers.mysql_family.mysql_recovery_bridge import bridges
            bridges.close()
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


def browser(app,output,sid,password,selected,credentials,binary,driver_binary,connections=False,replay=False,replay_source=None):
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
        for index in range(4):
            if replay and index==3:
                field('Recovery startup mode').click()
                wait.until(lambda b:next(e for e in b.find_elements(By.CSS_SELECTOR,'[role="option"]') if e.text=='Replay (writable, binary logging)')).click()
                fill('Recovery native server ID',10003)
                fill('Physical native timeout seconds',600)
            click('Review native physical job');wait.until(lambda b:b.find_element(By.CSS_SELECTOR,'[aria-label="Native physical review"]'))
            check('I confirm this exact reviewed physical operation.')
            if index in (0,3):check('Delegate the registered database password privately to the pinned SSH host.')
            click('Start reviewed physical job')
            def receipt(b):
                node=b.find_element(By.CSS_SELECTOR,'[aria-label="Native physical receipt"]')
                return json.loads(node.text)
            final=wait.until(lambda b:(value if (value:=receipt(b)).get('recovery_running' if index==3 else 'file_verification_confirmed') else None))
            assert final['remote_observation']['credential_cleanup_confirmed']
            if index==0:click('Use backup for separate prepare');checks.append('built-reviewed-native-full-backup-and-private-credential-delegation')
            elif index==1:click('Use prepared artifact for isolated copy-back');checks.append('built-immutable-prepare-from-selected-native-artifact')
            elif index==2:click('Use copy-back for managed recovery');checks.append('built-isolated-copy-back-with-independent-file-verification-and-no-database-start')
            else:
                assert final['recovery_sql_startup_observed'] and not final['database_recovery_verified']
                if replay:
                    identity=final['remote_observation']['sql_identity']
                    assert identity['log_bin']==1 and identity['super_read_only']==0 and identity['server_id']==10003
                    checks.append('built-separate-writable-replay-startup-and-private-native-binary-logging')
                if connections:
                    from cdeadmin_mysql_recovery_connection_qualification import browser_connection
                    callback=None
                    if replay:
                        from cdeadmin_mysql_physical_replay_qualification import browser_replay
                        callback=lambda target:browser_replay(app,output,sid,password,target,replay_source,binary,driver_binary)
                    checks.extend(browser_connection(driver,wait,click,fill,check,password,output,before_detach=callback))
                click('Stop managed recovery instance')
                wait.until(lambda b:(value if (value:=receipt(b)).get('remote_observation',{}).get('supervisor_finished') else None))
                checks.append('built-explicit-native-recovery-start-SQL-readiness-owned-process-and-stop')
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

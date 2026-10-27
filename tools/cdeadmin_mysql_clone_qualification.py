#!/usr/bin/env python3
"""Owned MySQL 9.7 HTTP local cloning and independent native recovery proof."""
import argparse
import builtins
from contextlib import contextmanager,ExitStack
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'web'),str(ROOT/'tools'),str(ROOT)]


@contextmanager
def fixture_pair(output,remote):
    from mysql_qualification_support import server as owned_server
    network='sr-clone-net-'+secrets.token_hex(8) if remote else None
    if network:subprocess.run(['docker','network','create',network],check=True,stdout=subprocess.DEVNULL,timeout=15)
    try:
        with ExitStack() as stack:
            recipient=stack.enter_context(owned_server(output/'fixture',network=network))
            donor=stack.enter_context(owned_server(output/'donor-fixture',network=network,server_id=102)) if remote else None
            yield recipient,donor
    finally:
        if network:
            result=subprocess.run(['docker','network','rm',network],check=False,stdout=subprocess.DEVNULL,timeout=15)
            (output/'network-cleanup.json').write_text(json.dumps({'owned_network_removed':result.returncode==0})+'\n')
            if result.returncode:raise RuntimeError('Owned clone qualification network cleanup failed')


def qualify(output,*,browser_binary=None,driver_binary=None,remote=False,browser_only=False,use_c=False,mysql_binlog=None):
    import mysql.connector
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence must be outside the source checkout')
    output.mkdir(parents=True,exist_ok=False)
    proof={'complete':False,'checks':[],'history_testing':'not run','source_sha256':{},'mysql_interface':'c' if use_c else 'pure'}
    if mysql_binlog:os.environ['CDEADMIN_MYSQL_BINLOG_BINARY']=str(Path(mysql_binlog).resolve(strict=True))
    for directory in ('web/pgadmin/cdeadmin/workspace','web/pgadmin/cdeadmin/providers/mysql_family'):
        for path in (ROOT/directory).glob('*.py'):
            proof['source_sha256'][str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ('tools/cdeadmin_mysql_clone_qualification.py','web/pgadmin/static/js/Dialogs/MySQLBackupProtection.jsx'):
        proof['source_sha256'][name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    builtins.SERVER_MODE=None
    import config
    config.SERVER_MODE=False;config.TESTING=True;config.WTF_CSRF_ENABLED=False
    config.MASTER_PASSWORD_REQUIRED=False;config.USE_OS_SECRET_STORAGE=False
    config.DATA_DIR=str(output/'app');config.SQLITE_PATH=str(output/'app/application.db')
    config.SESSION_DB_PATH=str(output/'app/sessions');config.STORAGE_DIR=str(output/'app/storage')
    config.LOG_FILE=str(output/'app/application.log');config.AZURE_CREDENTIAL_CACHE_DIR=str(output/'app/azure')
    config.CDEADMIN_OPERATION_STORE_PATH=str(output/'app/operations.json')
    config.CDEADMIN_MYSQL_CLONE_RECEIPT_ROOT=str(output/'clone-receipts')
    from pgadmin import create_app
    from pgadmin.model import db,User,ServerGroup,Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.workspace import service_for_app
    from flask import url_for
    app=create_app('ScratchRobin-native-mysql-clone-qualification');app.PGADMIN_RUNTIME=False;app.PGADMIN_INT_KEY=''
    app.run_before_app_start();client=app.test_client();jobs=None
    restored_name='sr-mysql-clone-restore-'+secrets.token_hex(8);restored_started=False
    restored=output/'restored-clone'
    password=secrets.token_urlsafe(32);donor_password="clone'ü\\-"+secrets.token_urlsafe(24)
    parent='/var/lib/sr-owned-clones'
    try:
        with fixture_pair(output,remote) as (recipient,donor_fixture):
            route,name,fixture=recipient
            route['use_pure']=not use_c
            native=mysql.connector.connect(**route,autocommit=True)
            cursor=native.cursor()
            try:
                cursor.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                route['password']=password
                cursor.execute("SELECT COUNT(*) FROM information_schema.PLUGINS WHERE PLUGIN_NAME='clone' AND PLUGIN_STATUS='ACTIVE'")
                if cursor.fetchone()[0]==0:cursor.execute("INSTALL PLUGIN clone SONAME 'mysql_clone.so'")
                for command in (['mkdir','-p',parent],['chown','mysql:mysql',parent]):
                    subprocess.run(['docker','exec','--user','root',name,*command],check=True,timeout=15,stdout=subprocess.DEVNULL)
                cursor.execute('CREATE DATABASE sr_clone_data CHARACTER SET utf8mb4')
                cursor.execute('CREATE TABLE sr_clone_data.sample(id BIGINT PRIMARY KEY,body TEXT,payload LONGBLOB) ENGINE=InnoDB')
                cursor.execute('INSERT INTO sr_clone_data.sample VALUES(%s,%s,%s)',(9007199254740993,'Unicode 😀',bytes.fromhex('0080ff')))
                with app.test_request_context('/'):
                    user=User.query.first();group=ServerGroup.query.filter_by(user_id=user.id).order_by(ServerGroup.id).first()
                    app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=user.id)
                    registered=Server(user_id=user.id,servergroup_id=group.id,name='Owned MySQL clone',
                        host=route['host'],port=route['port'],username='root',maintenance_db=None,save_password=0)
                    registered._cde_endpoint_registration=registration_profile('mysql-native')
                    registered._cde_endpoint_route_configuration={key:value for key,value in route.items() if key!='password'}
                    registered._cde_endpoint_route_configuration['credential_kinds']=['database_password']
                    db.session.add(registered);db.session.commit()
                    uid,sid,gid=user.id,registered.id,group.id
                    endpoint=registered.endpoint_profile.id
                    connect_url=url_for('NODE-server.verify_endpoint_id',gid=gid,sid=sid)
                    workspace_url=url_for('NODE-server.cde_workspace_id',gid=gid,sid=sid)
                with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
                connected=client.post(connect_url,json={'password':password}).get_json()
                if not connected.get('success'):
                    (output/'connect-failure.json').write_text(json.dumps(connected,indent=2).replace(password,'<redacted>')+'\n')
                    raise RuntimeError('Owned native MySQL application connection failed')
                donor_options=None
                if remote:
                    donor_route,donor_name,donor_proof=donor_fixture
                    donor_route['use_pure']=not use_c
                    donor_native=mysql.connector.connect(**donor_route,autocommit=True)
                    try:
                        with donor_native.cursor() as donor_cursor:
                            donor_cursor.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                            donor_cursor.execute("INSTALL PLUGIN clone SONAME 'mysql_clone.so'")
                            donor_cursor.execute("CREATE USER 'sr_clone_donor'@'%' IDENTIFIED BY %s",(donor_password,))
                            donor_cursor.execute("GRANT BACKUP_ADMIN ON *.* TO 'sr_clone_donor'@'%'")
                            donor_cursor.execute('CREATE DATABASE sr_clone_data CHARACTER SET utf8mb4')
                            donor_cursor.execute('CREATE TABLE sr_clone_data.sample(id BIGINT PRIMARY KEY,body TEXT,payload LONGBLOB) ENGINE=InnoDB')
                            donor_cursor.execute('INSERT INTO sr_clone_data.sample VALUES(%s,%s,%s)',(9007199254740993,'Unicode 😀',bytes.fromhex('0080ff')))
                        cursor.execute("UPDATE sr_clone_data.sample SET body='recipient original',payload=X'CAFE'")
                        cursor.execute('SET GLOBAL clone_valid_donor_list=%s',(donor_name+':3306',))
                        with app.test_request_context('/'):
                            item=Server(user_id=uid,servergroup_id=gid,name='Owned remote clone donor',host=donor_route['host'],port=donor_route['port'],username='sr_clone_donor',maintenance_db=None,save_password=0)
                            item._cde_endpoint_registration=registration_profile('mysql-native')
                            item._cde_endpoint_route_configuration={**donor_route,'user':'sr_clone_donor','credential_kinds':['database_password']}
                            db.session.add(item);db.session.commit()
                            donor_sid=item.id;donor_endpoint=item.endpoint_profile.id
                            donor_url=url_for('NODE-server.cde_workspace_id',gid=gid,sid=donor_sid)
                            verify=url_for('NODE-server.verify_endpoint_id',gid=gid,sid=donor_sid)
                        response=client.post(verify,json={'password':donor_password}).get_json()
                        if not response.get('success'):raise RuntimeError('Owned donor verification failed')
                        donor_options={'server_id':donor_sid,'host':donor_name,'port':3306,'require_ssl':True,'delegate_credentials':True}
                    finally:donor_native.close()
                def http(operation,request):
                    response=client.post(workspace_url,json={'action':'mysql_clone_'+operation,'request':request})
                    value=response.get_json()
                    if response.status_code!=200 or not value.get('success'):
                        (output/'http-failure.json').write_text(json.dumps(value,indent=2).replace(password,'<redacted>').replace(donor_password,'<redacted>')+'\n')
                        raise RuntimeError('Native clone HTTP '+operation+' failed')
                    return value['data']
                def backup_http(action,request,*,target=None,refused=False):
                    response=client.post(target or workspace_url,json={'action':action,'request':request});value=response.get_json()
                    if refused:
                        assert response.status_code==400,value
                        return value
                    assert response.status_code==200 and value.get('success'),value
                    return value['data']
                archive=None;archive_bytes=None
                if mysql_binlog and not browser_only:
                    cursor.execute('FLUSH BINARY LOGS')
                    catalog=backup_http('mysql_raw_binlog_catalog',{})
                    selected=backup_http('mysql_raw_binlog_review',{'options':{'log_names':[catalog['logs'][0]['Log_name']]}})
                    archive=backup_http('mysql_raw_binlog_start',{key:selected[key] for key in ('job_id','review_digest')}|{'confirmed':True})
                    deadline=time.monotonic()+60
                    while archive['state'] in {'dispatching','active','cancel_requested'}:
                        if time.monotonic()>deadline:raise TimeoutError('Owned clone dependency archive deadline')
                        time.sleep(.05);archive=backup_http('mysql_raw_binlog_status',{'job_id':archive['job_id']})
                    assert archive['state']=='completed',archive
                    archives=service_for_app(app).mysql_raw_binlog_jobs
                    archive_record=archives.load(archive['job_id'],uid,endpoint)
                    archive_bytes=archives.native_verify(archives.directory(archive_record)/'archive',archive_record['source'])
                last_review=[]
                def start(path):
                    selected={'destination':path,'confirmation':path,'timeout_seconds':120}
                    if donor_options is not None:selected['donor']=donor_options
                    review=http('review',{'options':selected})
                    last_review[:]=[review]
                    assert review['source']['version'].split('-')[0]=='9.7.0'
                    if remote:
                        assert review['operation']=='remote_clone' and review['donor']['native_identity']['server_uuid']==donor_proof['server_uuid']
                        assert review['donor']['native_protocol_uuid_attested'] is False
                    request={'job_id':review['job_id'],'review_digest':review['review_digest'],'confirmed':True}
                    result=http('start',request);repeated=http('start',request)
                    assert repeated['job_id']==result['job_id']
                    return result,request
                def finish(result,expected):
                    deadline=time.monotonic()+150
                    while result['state'] in {'dispatching','active','cancel_requested'}:
                        if time.monotonic()>deadline:
                            http('cancel',{'job_id':result['job_id']});raise TimeoutError('Native local clone deadline')
                        time.sleep(.1);result=http('status',{'job_id':result['job_id']})
                    if result['state']!=expected:
                        (output/'clone-failure.json').write_text(json.dumps(result,indent=2)+'\n')
                        raise RuntimeError('Native local clone returned '+result['state'])
                    return result
                if browser_only:
                    if not browser_binary:raise ValueError('Browser-only qualification requires a browser binary')
                    proof['browser']=browser(app,output,parent,sid,browser_binary,driver_binary,donor_options=donor_options)
                    jobs=service_for_app(app).mysql_clone_jobs
                    managed=jobs.list(uid,endpoint)['jobs']
                    completed_job=next(row for row in managed if row['state']=='native_completed')
                    assert completed_job['source']['client_interface']==('CharsetCMySQLConnection' if use_c else 'CharsetMySQLConnection')
                    from cdeadmin_mysql_backup_protection_qualification import browser as protection_browser
                    ui_output=output/'protection-browser';ui_output.mkdir()
                    proof['protection_browser']=protection_browser(app,ui_output,sid,password,browser_binary,driver_binary,completed_job['job_id'])
                    proof.update(complete=True,mode='remote' if remote else 'local',qualification_scope='native-browser-clone-only')
                    proof['checks'].append('native-browser-reviewed-clone-with-correlated-completion-and-explicit-physical-protection-retirement')
                else:
                    import pgadmin.cdeadmin.workspace.mysql_clone_jobs as clone_module
                    import pgadmin.cdeadmin.providers.mysql_family.mysql_clone as native_clone_module
                    from pgadmin.cdeadmin.workspace.mysql_backup_protection import Registry
                    registry=service_for_app(app).mysql_backup_protection
                    original_rows=clone_module.rows;native_original_rows=native_clone_module.rows;intents=[]
                    def before_native(connection,statement,parameters=()):
                        if statement.startswith('CLONE '):
                            scopes=[endpoint,donor_endpoint] if remote else [endpoint]
                            for scope in scopes:
                                rows=registry.list(uid,scope)['backups']
                                assert any(row['backup_id']==last_review[0]['job_id'] and row['state']=='pending_native_reply' for row in rows)
                            intents.append('durable-intent-before-native-clone')
                        return original_rows(connection,statement,parameters)
                    clone_module.rows=before_native
                    if remote:native_clone_module.rows=before_native
                    path=parent+'/Clone "ü" '+secrets.token_hex(8)
                    try:completed,request=start(path);completed=finish(completed,'native_completed')
                    finally:clone_module.rows=original_rows;native_clone_module.rows=native_original_rows
                    assert len(intents)==1
                    assert completed['source']['client_interface']==('CharsetCMySQLConnection' if use_c else 'CharsetMySQLConnection')
                    assert completed['sql_observation']['acknowledged'] and completed['native_observation']['job_correlated']
                    holds=completed['archive_backup_protections']
                    assert len(holds)==(2 if remote else 1)
                    assert all(row['native_clone_completion_acknowledged'] for row in holds)
                    assert all(row['state']==('native_clone_returned_unattested_source' if remote else 'native_clone_returned') for row in holds)
                    assert Registry(registry.root).list(uid,endpoint)['backups'][0]['backup_id']==completed['job_id']
                    if remote:
                        donated=backup_http('mysql_binlog_backup_protection_list',{},target=donor_url)['backups']
                        assert donated[0]['clone_role']=='registered_donor' and donated[0]['source']['server_uuid']==donor_proof['server_uuid']
                    if archive:
                        backup_http('mysql_raw_binlog_remove_artifact',{'job_id':archive['job_id'],'confirmation':archive['job_id']},refused=True)
                        assert archives.native_verify(archives.directory(archive_record)/'archive',archive_record['source'])==archive_bytes
                    proof['checks'].append('durable-clone-holds-before-native-SQL-with-exact-registered-source-and-conservative-remote-donor-recipient-scope')
                    assert completed['files_verified'] is False and completed['recovery_drill_complete'] is False
                    proof['checks'].append('authenticated-http-native-innodb-'+('remote' if remote else 'local')+'-clone-to-exact-quoted-unicode-server-directory-and-correlated-pfs-completion')
                    if remote:
                        assert completed['native_observation']['status']['source']==donor_name+':3306'
                        cursor.execute('SELECT body,HEX(payload) FROM sr_clone_data.sample')
                        assert cursor.fetchall()==[('recipient original','CAFE')]
                        assert any(item['server_id']==donor_sid for item in http('donors',{})['donors'])
                        proof['checks'].append('remote-native-tls-donor-delegation-preserves-recipient-original-data-and-records-native-tcp-source')
                    print('native local clone completed through application HTTP',flush=True)
                    cursor.execute("INSERT INTO sr_clone_data.sample VALUES(9007199254740994,'after clone',X'AABB')")
                    restored.mkdir()
                    subprocess.run(['docker','cp',name+':'+path+'/.',str(restored)],check=True,timeout=60,stdout=subprocess.DEVNULL)
                    subprocess.run(['docker','run','--rm','-d','--name',restored_name,'--publish','127.0.0.1::3306',
                        '--mount','type=bind,source='+str(restored)+',target=/var/lib/mysql','mysql:9.7.0','--server-id=202','--skip-log-bin'],
                        check=True,timeout=30,stdout=subprocess.DEVNULL)
                    restored_started=True
                    port=int(subprocess.check_output(['docker','port',restored_name,'3306/tcp'],text=True,timeout=15).strip().rsplit(':',1)[1])
                    deadline=time.monotonic()+90
                    while True:
                        try:
                            recovered=mysql.connector.connect(host='127.0.0.1',port=port,user='root',password=password,
                                use_pure=True,connection_timeout=2,autocommit=True);break
                        except mysql.connector.Error:
                            if time.monotonic()>deadline:raise
                            time.sleep(.2)
                    with recovered.cursor() as observed:
                        observed.execute('SELECT CAST(id AS CHAR),body,HEX(payload) FROM sr_clone_data.sample ORDER BY id')
                        assert observed.fetchall()==[('9007199254740993','Unicode 😀','0080FF')]
                        observed.execute('SELECT VERSION()');assert observed.fetchone()[0].split('-')[0]=='9.7.0'
                    recovered.close()
                    proof['checks'].append('independent-native-mysql9.7-recovery-of-cloned-files-preserves-exact-int64-unicode-binary-and-excludes-later-source-data')
                    print('independent native MySQL clone recovery passed',flush=True)
                    cursor.execute('SET GLOBAL clone_max_data_bandwidth=1')
                    cancelled,_request=start(parent+'/cancel-'+secrets.token_hex(8))
                    deadline=time.monotonic()+30
                    while not cancelled.get('native_observation',{}).get('status'):
                        if time.monotonic()>deadline:raise TimeoutError('Native clone never exposed correlated live progress')
                        time.sleep(.1);cancelled=http('status',{'job_id':cancelled['job_id']})
                        if cancelled['state'] not in {'dispatching','active'}:raise RuntimeError('Clone finished before cancellation fixture became active')
                    http('cancel',{'job_id':cancelled['job_id']});cancelled=finish(cancelled,'cancelled')
                    assert cancelled['cancel_delivery']['acknowledged'] and cancelled['native_completion_observed']
                    cursor.execute('SET GLOBAL clone_max_data_bandwidth=0')
                    proof['checks'].append('native-pfs-progress-and-identity-bound-kill-query-cancellation-with-confirmed-native-failed-state')
                    print('native MySQL clone cancellation passed',flush=True)
                    # A repeated terminal start reads its receipt without replaying.
                    assert http('start',request)['state']=='native_completed'
                    reconciled=http('reconcile',{'job_id':completed['job_id']})
                    assert reconciled['state']=='native_completed'
                    proof['checks'].append('durable-no-replay-and-native-status-reconciliation')
                    import pgadmin.cdeadmin.workspace.mysql_clone_jobs as clone_module
                    original_rows=clone_module.rows
                    def lose_reply(connection,statement,parameters=()):
                        result=original_rows(connection,statement,parameters)
                        if statement.startswith('CLONE '):raise OSError('fixture loses successful clone acknowledgement')
                        return result
                    clone_module.rows=lose_reply
                    import pgadmin.cdeadmin.providers.mysql_family.mysql_clone as native_clone_module
                    native_original_rows=native_clone_module.rows
                    if remote:native_clone_module.rows=lose_reply
                    try:
                        lost,lost_request=start(parent+'/lost-reply-'+secrets.token_hex(8))
                        lost=finish(lost,'native_completed')
                        assert lost['sql_observation']['acknowledged'] is False and lost['native_completion_observed']
                        assert http('start',lost_request)['state']=='native_completed'
                        assert all(row['state']=='unconfirmed_native_reply' and not row['native_clone_completion_acknowledged'] for row in lost['archive_backup_protections'])
                    finally:clone_module.rows=original_rows;native_clone_module.rows=native_original_rows
                    proof['checks'].append('lost-success-reply-reconciles-only-from-frozen-native-operation-identity-without-replay')
                    original_observation=clone_module.observation;observations=[]
                    def broken_after_reply(connection):
                        observations.append(1)
                        item=service_for_app(app).mysql_clone_jobs.load(last_review[0]['job_id'],uid,endpoint)
                        if len(observations)>1 and item.get('sql_observation',{}).get('acknowledged'):
                            raise OSError('Owned native clone post-ack observer failure')
                        return original_observation(connection)
                    clone_module.observation=broken_after_reply
                    try:
                        uncertain,uncertain_request=start(parent+'/observer-fault-'+secrets.token_hex(8))
                        uncertain=finish(uncertain,'unknown')
                    finally:clone_module.observation=original_observation
                    assert uncertain['sql_observation']['acknowledged'] and not uncertain.get('recovery_drill_complete')
                    assert all(row['native_clone_completion_acknowledged'] for row in uncertain['archive_backup_protections'])
                    assert http('start',uncertain_request)['state']=='unknown'
                    proof['checks'].append('actual-native-clone-ACK-survives-later-observer-failure-with-protection-and-no-replay')
                    refused,_request=start(path);refused=finish(refused,'refused')
                    assert refused['sql_observation']['native_refusal'] and refused['native_completion_observed'] is False
                    proof['checks'].append('native-existing-directory-refusal-does-not-reuse-a-prior-completed-status')
                    cursor.execute("CREATE USER 'sr_no_backup'@'%' IDENTIFIED BY %s",(password,))
                    def register(label,username,use_pure,sql_mode=None):
                        with app.test_request_context('/'):
                            item=Server(user_id=uid,servergroup_id=gid,name=label,host=route['host'],port=route['port'],username=username,maintenance_db=None,save_password=0)
                            item._cde_endpoint_registration=registration_profile('mysql-native')
                            item._cde_endpoint_route_configuration={'host':route['host'],'port':route['port'],'user':username,'use_pure':use_pure,'credential_kinds':['database_password']}
                            if sql_mode is not None:item._cde_endpoint_route_configuration['sql_mode']=sql_mode
                            db.session.add(item);db.session.commit()
                            verify=url_for('NODE-server.verify_endpoint_id',gid=gid,sid=item.id)
                            workspace=url_for('NODE-server.cde_workspace_id',gid=gid,sid=item.id)
                        response=client.post(verify,json={'password':password}).get_json()
                        if not response.get('success'):
                            (output/'secondary-connect-failure.json').write_text(json.dumps(response,indent=2).replace(password,'<redacted>')+'\n')
                            raise RuntimeError('Secondary native MySQL endpoint verification failed')
                        return workspace
                    original_workspace=workspace_url
                    try:
                        workspace_url=register('Owned MySQL denied clone','sr_no_backup',True)
                        denied,_request=start(parent+'/denied-'+secrets.token_hex(8));denied=finish(denied,'refused')
                        assert denied['sql_observation']['error_number']==1227
                        proof['checks'].append('native-backup-admin-denial-is-refused-without-application-privilege-escalation')
                        workspace_url=register('Owned MySQL C clone','root',False,'NO_BACKSLASH_ESCAPES,ANSI_QUOTES')
                        alternate,_request=start(parent+'/C exact \\ quoted "ü" '+secrets.token_hex(8))
                        alternate=finish(alternate,'native_completed')
                        assert alternate['source']['client_interface']=='CharsetCMySQLConnection'
                        proof['checks'].append('native-c-extension-worker-and-observer-under-ansi-quotes-no-backslash-escapes-preserve-exact-server-path')
                    finally:workspace_url=original_workspace
                    jobs=service_for_app(app).mysql_clone_jobs
                    for file in Path(str(jobs.path)+'.jobs').glob('*.json'):
                        assert password not in file.read_text() and donor_password not in file.read_text()
                    if browser_binary:
                        proof['browser']=browser(app,output,parent,sid,browser_binary,driver_binary,donor_options=donor_options)
                        proof['checks'].append('native-browser-server-menu-reviews-confirms-and-observes-'+('remote' if remote else 'local')+'-physical-clone')
                        from cdeadmin_mysql_backup_protection_qualification import browser as protection_browser
                        ui_output=output/'protection-browser';ui_output.mkdir()
                        proof['protection_browser']=protection_browser(app,ui_output,sid,password,browser_binary,driver_binary,lost['job_id'])
                    if archive:
                        for target in ([workspace_url,donor_url] if remote else [workspace_url]):
                            for hold in backup_http('mysql_binlog_backup_protection_list',{},target=target)['backups']:
                                if hold['state']=='retired':continue
                                retirement=backup_http('mysql_binlog_backup_protection_review_retire',{'backup_id':hold['backup_id']},target=target)
                                backup_http('mysql_binlog_backup_protection_retire',{key:retirement[key] for key in ('review_id','review_digest')}|{'confirmed':True},target=target)
                        removed=backup_http('mysql_raw_binlog_remove_artifact',{'job_id':archive['job_id'],'confirmation':archive['job_id']})
                        assert removed['artifact_removed']
                        subprocess.run(['docker','exec',name,'test','-d',path],check=True,timeout=15)
                        proof['checks'].append('actual-archive-bytes-retained-until-reviewed-clone-hold-retirement-with-native-clone-files-preserved')
                    proof.update(complete=True,mode='remote' if remote else 'local',source=completed['source'],job_ids=[completed['job_id'],cancelled['job_id']])
            finally:cursor.close();native.close()
        assert fixture['owned_server_stopped']
        assert http('list',{})['total']>=(1 if browser_only else 2)
        proof['checks'].append('offline-authenticated-http-owner-bound-clone-receipts-after-source-stopped')
    finally:
        if jobs is not None:
            jobs.close();proof['owned_workers_stopped']=not jobs.workers
        if restored_started:
            with (output/'restore-server.log').open('wb') as stream:
                subprocess.run(['docker','logs',restored_name],stdout=stream,stderr=subprocess.STDOUT,timeout=15)
            stopped=subprocess.run(['docker','stop',restored_name],stdout=subprocess.DEVNULL,timeout=45)
            proof['owned_restored_server_stopped']=stopped.returncode==0
            ownership=subprocess.run(['docker','run','--rm','--user','0:0','--entrypoint','find','--mount',
                'type=bind,source='+str(restored)+',target=/owned','mysql:9.7.0','/owned','!','-type','l','-exec','chown',
                str(os.getuid())+':'+str(os.getgid()),'{}','+'],check=False,timeout=30,stdout=subprocess.DEVNULL)
            proof['owned_clone_ownership_restored']=ownership.returncode==0
            if ownership.returncode!=0:proof['complete']=False
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    assert proof['complete'] and (browser_only or proof['owned_restored_server_stopped'])
    return proof


def browser(app,output,parent,server_id,binary,driver_binary,*,donor_options=None):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver import ActionChains
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer,expand
    http=make_server('127.0.0.1',0,app,threaded=True)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
    try:
        opts=webdriver.ChromeOptions();opts.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1600,1000'):opts.add_argument(flag)
        opts.add_argument('--user-data-dir='+str(output/'browser-profile'));opts.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=opts,service=Service(driver_binary) if driver_binary else Service())
        driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/')
        wait=WebDriverWait(driver,60)
        ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
        def target(browser):
            for node in browser.find_elements(By.CSS_SELECTOR,'.file-name'):
                if node.is_displayed() and browser.execute_script('''
                    const tree=window.pgAdmin.Browser.tree;
                    const data=tree.itemData(tree.itemFrom(arguments[0].closest('.file-entry')));
                    return data?._type==='server' && String(data._id ?? data.id)===String(arguments[1]);
                ''',node,server_id):return node
            return None
        item=wait.until(target)
        ActionChains(driver).context_click(item).perform()
        wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="menuitem"]')
            if node.is_displayed() and node.text.strip()=='Backup'),None)).click()
        menu=wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="menuitem"]')
            if node.is_displayed() and 'MySQL physical clone' in node.text),None));menu.click()
        def click(text):
            def attempt(browser):
                for node in browser.find_elements(By.TAG_NAME,'button'):
                    if node.is_enabled() and node.get_attribute('textContent').strip()==text:
                        browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});',node)
                        if node.is_displayed():node.click();return True
                return False
            wait.until(attempt)
        path=parent+'/browser-'+secrets.token_hex(8)
        if donor_options:
            click('Load registered donors')
            def source_control(browser):
                for label in browser.find_elements(By.TAG_NAME,'label'):
                    if label.is_displayed() and label.text=='Clone source':
                        control=browser.find_element(By.ID,label.get_attribute('for'))
                        if control.is_displayed() and control.get_attribute('aria-disabled')!='true':return control
                return False
            select=wait.until(source_control)
            driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});',select);select.click()
            wait.until(lambda browser:next((node for node in browser.find_elements(By.CSS_SELECTOR,'[role="option"]')
                if node.text=='Owned remote clone donor'),None)).click()
            for label,value in (('Donor host reachable from recipient',donor_options['host']),('Donor TCP port','3306')):
                field_label=driver.find_element(By.XPATH,'//label[normalize-space()="'+label+'"]')
                field=driver.find_element(By.ID,field_label.get_attribute('for'));field.send_keys(Keys.CONTROL,'a');field.send_keys(value)
            driver.find_element(By.XPATH,'//label[contains(.,"Delegate registered donor credentials to recipient")]//input').click()
        for label in ('Destination on database-server host','Confirm exact destination'):
            field_label=wait.until(lambda browser:browser.find_element(By.XPATH,'//label[normalize-space()="'+label+'"]'))
            field=driver.find_element(By.ID,field_label.get_attribute('for'));driver.execute_script('arguments[0].scrollIntoView();',field);field.send_keys(path)
        mode='remote' if donor_options else 'local'
        click('Review '+mode+' clone');click('Confirm and start '+mode+' clone')
        def completed(browser):
            for node in browser.find_elements(By.CSS_SELECTOR,'[role="alert"]'):
                if 'Native clone completion observed' in node.get_attribute('textContent'):
                    browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});',node)
                    return 'Native clone completion observed' in node.text
            return False
        wait.until(completed);driver.save_screenshot(str(output/'native-mysql-clone.png'))
        errors=[value for value in driver.get_log('browser') if value.get('level')=='SEVERE']
        (output/'browser-console.json').write_text(json.dumps(errors,indent=2)+'\n');assert not errors
        return {'complete':True,'console_errors':0,'server_context_menu':True,'reviewed_native_clone':True,'mode':mode}
    except Exception:
        if driver is not None:
            driver.save_screenshot(str(output/'browser-failure.png'))
            (output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text)
        raise
    finally:
        if driver is not None:driver.quit()
        http.shutdown();http.server_close();thread.join(timeout=5)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--browser-binary');parser.add_argument('--driver-binary');parser.add_argument('--remote',action='store_true');parser.add_argument('--browser-only',action='store_true')
    parser.add_argument('--use-c',action='store_true');parser.add_argument('--mysql-binlog');args=parser.parse_args()
    qualify(args.evidence,browser_binary=args.browser_binary,driver_binary=args.driver_binary,remote=args.remote,browser_only=args.browser_only,use_c=args.use_c,mysql_binlog=args.mysql_binlog)

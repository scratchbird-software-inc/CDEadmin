"""Owned two-instance native restore, log continuation and uncertain outcomes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output,shell,use_c=False,binary=None,driver_binary=None,acceptance=False,system_state=False):
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep native evidence outside source')
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    os.environ['CDEADMIN_MYSQLSH_BINARY']=str(Path(shell).resolve(strict=True))
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    app=setup_application(output)
    from flask import url_for
    from pgadmin.model import db,User,ServerGroup,Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.workspace import service_for_app
    from pgadmin.cdeadmin.workspace.mysql_instance_restore_jobs import InstanceRestoreTransport
    from mysql_qualification_support import server,_root_connection
    client=app.test_client();service=service_for_app(app);fixtures=[]
    paths=['web/pgadmin/cdeadmin/providers/mysql_family/'+name for name in ('mysql_instance_restores.py','mysql_instance_dumps.py','mysql_binlog_archives.py')]
    paths+=['web/pgadmin/cdeadmin/workspace/'+name for name in ('mysql_instance_restore_jobs.py','mysql_instance_restore_service.py','mysql_binlog_replay_jobs.py','service.py')]
    paths+=['web/pgadmin/browser/server_groups/servers/__init__.py','web/pgadmin/cdeadmin/context_menu.py',
        'web/pgadmin/static/js/Dialogs/MySQLInstanceRestores.jsx','tools/cdeadmin_mysql_instance_restore_qualification.py']
    paths+=['web/pgadmin/cdeadmin/sdk/'+name for name in ('tooling.py','durable_tool.py','tool_guardian.py','tool_process.py','tool_reconcile.py')]
    paths+=['web/pgadmin/cdeadmin/workspace/mysql_binlog_jobs.py','tools/mysql_interruption_qualification.py']
    if system_state:
        paths+=['web/pgadmin/cdeadmin/providers/mysql_family/mysql_system_state.py','web/pgadmin/cdeadmin/workspace/mysql_instance_backup_jobs.py','web/pgadmin/cdeadmin/workspace/mysql_instance_backup_service.py']
    if acceptance:
        paths+=['web/pgadmin/cdeadmin/providers/mysql_family/mysql_instance_acceptance.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/mysql_acceptance_lock_owner.py',
            'web/pgadmin/cdeadmin/workspace/mysql_instance_acceptance_jobs.py','web/pgadmin/cdeadmin/workspace/mysql_instance_acceptance_service.py',
            'web/pgadmin/static/js/Dialogs/MySQLInstanceAcceptance.jsx']
    proof={'complete':False,'full_mysql_product_complete':False,'history_testing':'not run','use_c':use_c,'checks':[],
        'independent_acceptance':acceptance,
        'source_sha256':{path:hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in paths}}
    password='true';recovered_acceptance_id=None;interrupted_restore_id=None
    try:
        with server(output/'source-fixture') as (source,_source_name,sfixture),server(output/'target-fixture',server_id=102) as (target,_target_name,tfixture):
            fixtures.extend([sfixture,tfixture]);handles=[];cursors=[]
            try:
                for route in (source,target):
                    handle=_root_connection('mysql',route['port']);handle.autocommit=True;handles.append(handle);q=handle.cursor();cursors.append(q)
                    q.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                qs,qt=cursors
                if system_state:
                    for q in cursors:q.execute("CREATE SERVER sr_system_checkpoint FOREIGN DATA WRAPPER mysql OPTIONS(HOST 'native-original.example',DATABASE 'native',USER 'fixture',PASSWORD 'private-system-state-fixture')")
                for schema in ('sr_restored_a','sr_restored_b'):
                    qs.execute('CREATE DATABASE '+schema+' CHARACTER SET utf8mb4')
                    qs.execute('CREATE TABLE '+schema+'.t(id BIGINT PRIMARY KEY,body TEXT,payload LONGBLOB)')
                    qs.execute('INSERT INTO '+schema+'.t VALUES(%s,%s,%s)',(9007199254740993,'native 雪',b'\x00\xff'))
                qs.execute('CREATE VIEW sr_restored_a.v AS SELECT id FROM sr_restored_b.t')
                qs.execute('CREATE PROCEDURE sr_restored_a.p() SELECT 1')
                qs.execute("CREATE ROLE 'sr_restored_role'@'%'");qs.execute("CREATE USER 'sr_restored_user'@'%' IDENTIFIED BY %s",(password,))
                qs.execute("GRANT SELECT ON sr_restored_a.* TO 'sr_restored_role'@'%'");qs.execute("GRANT 'sr_restored_role'@'%' TO 'sr_restored_user'@'%'")
                qt.execute('SET GLOBAL local_infile=ON')
                qt.execute("CREATE USER 'sr_restore_denied'@'%' IDENTIFIED BY %s",(password,));qt.execute("GRANT SELECT ON performance_schema.* TO 'sr_restore_denied'@'%'")
                with app.test_request_context('/'):
                    uid=User.query.first().id;group=ServerGroup.query.filter_by(user_id=uid).first()
                    app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
                    def register(label,route,user='root'):
                        item=Server(user_id=uid,servergroup_id=group.id,name=label,host=route['host'],port=route['port'],username=user,maintenance_db=None,save_password=0)
                        item._cde_endpoint_registration=registration_profile('mysql-native')
                        item._cde_endpoint_route_configuration={**route,'user':user,'use_pure':not use_c,'credential_kinds':['database_password']}
                        db.session.add(item);db.session.commit()
                        return item.id,url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=item.id),url_for('NODE-server.cde_workspace_id',gid=group.id,sid=item.id)
                    sid,sv,surl=register('Owned instance recovery source',source)
                    tid,tv,turl=register('Owned instance recovery target',target)
                    _did,dv,durl=register('Owned denied recovery actor',target,'sr_restore_denied')
                with client.session_transaction() as session:session['_user_id']=str(uid);session['_fresh']=True
                for endpoint in (sv,tv,dv):assert client.post(endpoint,json={'password':password}).get_json()['success']
                with app.app_context():
                    context,_payload,_root=service.endpoint_service.workspace(db.session.get(Server,tid),database_target_id=None)
                    db_client=service.endpoint_service.provider_registry.resolve(context).instance.client
                connect=db_client._connect;classes=[]
                def recorded(*args,**kwargs):
                    handle=connect(*args,**kwargs);classes.append(type(handle).__name__);return handle
                db_client._connect=recorded
                def http(action,request,*,url=turl,prefix='mysql_instance_restore_',refused=False):
                    response=client.post(url,json={'action':prefix+action,'request':request});value=response.get_json()
                    if refused:assert response.status_code==400,value;return value
                    if response.status_code!=200 or not value.get('success'):
                        (output/'http-failure.json').write_text(json.dumps(value,indent=2)+'\n');raise AssertionError('Native instance recovery API failed: '+action)
                    return value['data']
                def start(planned,**kwargs):return http('start',{key:planned[key] for key in ('job_id','review_digest')}|{'confirmed':True},**kwargs)
                def wait(value,**kwargs):
                    deadline=time.monotonic()+180
                    while value['state'] in {'dispatching','active','cancel_requested'}:
                        if time.monotonic()>deadline:raise TimeoutError('Owned native instance recovery deadline')
                        time.sleep(.05);value=http('status',{'job_id':value['job_id']},**kwargs)
                    return value
                backup=wait(start(http('review',{'options':{'users':True,'checksum':True,'threads':1,**({'system_state_tables':['servers','plugin','component','func','time_zone','time_zone_name','time_zone_transition','time_zone_transition_type','time_zone_leap_second'],'system_state_write_pause_confirmed':True} if system_state else {}),**({'exclude_users':['root']} if acceptance else {})}},url=surl,prefix='mysql_instance_backup_'),url=surl,prefix='mysql_instance_backup_'),url=surl,prefix='mysql_instance_backup_')
                assert backup['state']=='completed',backup
                if system_state:
                    assert backup['result']['system_source_locks_released'] and backup['server_lock_owner']['admitted']
                    observed=http('observe_source_locks',{'job_id':backup['job_id']},url=surl,prefix='mysql_instance_backup_')
                    assert observed['source_lock_cleanup_observation']['released']
                    from pgadmin.cdeadmin.workspace.mysql_instance_backup_jobs import InstanceBackupTransport
                    original_system_dump=InstanceBackupTransport.system_dump
                    def lost_source_unlock(self,*args,**kwargs):
                        connection=self.system_connection;cursor=connection.cursor
                        class LostReply:
                            def __init__(self,owned):self.owned=owned
                            def __getattr__(self,key):return getattr(self.owned,key)
                            def execute(self,statement,*parameters,**options):
                                value=self.owned.execute(statement,*parameters,**options)
                                if statement=='UNLOCK TABLES':raise OSError('Owned lost source unlock reply')
                                return value
                        connection.cursor=lambda *a,**kw:LostReply(cursor(*a,**kw))
                        try:return original_system_dump(self,*args,**kwargs)
                        finally:connection.cursor=cursor
                    InstanceBackupTransport.system_dump=lost_source_unlock
                    try:
                        options={'users':False,'threads':1,'system_state_tables':['servers'],'system_state_write_pause_confirmed':True}
                        lost=wait(start(http('review',{'options':options},url=surl,prefix='mysql_instance_backup_'),url=surl,prefix='mysql_instance_backup_'),url=surl,prefix='mysql_instance_backup_')
                    finally:InstanceBackupTransport.system_dump=original_system_dump
                    assert lost['state']=='native_returned_unverified' and lost['native_dump_acknowledged'],lost
                    observed=http('observe_source_locks',{'job_id':lost['job_id']},url=surl,prefix='mysql_instance_backup_')
                    assert observed['source_lock_cleanup_observation']['released'] and observed['state']=='native_returned_unverified'
                    verified=http('reconcile',{'job_id':lost['job_id']},url=surl,prefix='mysql_instance_backup_')
                    assert verified['state']=='artifact_verified' and verified['native_dump_acknowledged']
                    assert verified['result']['artifact']['system_state_checkpoint']['tables']==['servers']
                    proof['checks'].append('lost-source-unlock-reply-keeps-native-dump-acknowledgement-with-independent-original-lock-cleanup-and-separate-required-system-checkpoint-file-acceptance')

                target_uuid=http('inspect',{})['identity']['server_uuid']
                selected={'target_confirmation':target_uuid,'load_users':True,'exclude_users':['root'],
                    'checksum':True,'threads':1,'skip_binlog':True,'update_gtid_set':'append','timeout_seconds':120}
                def review(options=None,**kwargs):return http('review',{'source_server_id':sid,'backup_job_id':backup['job_id'],'options':options or selected},**kwargs)
                http('review',{'source_server_id':sid,'backup_job_id':backup['job_id'],
                    'options':{**selected,'target_confirmation':backup['source']['server_uuid']}},url=surl,refused=True)
                restored=wait(start(review()))
                assert restored['state']=='native_load_returned' and restored['native_load_outcome']=='returned',restored
                assert not restored['data_recovery_verified'] and restored['native_process_termination_confirmed']
                qt.execute('SELECT CAST(id AS CHAR),body,HEX(payload) FROM sr_restored_a.t');assert qt.fetchall()==[('9007199254740993','native 雪','00FF')]
                qt.execute('SELECT CAST(id AS CHAR) FROM sr_restored_a.v');assert qt.fetchall()==[('9007199254740993',)]
                qt.execute("SELECT User FROM mysql.user WHERE User IN ('sr_restored_user','sr_restored_role') ORDER BY User");assert qt.fetchall()==[('sr_restored_role',),('sr_restored_user',)]
                qt.execute("SHOW GRANTS FOR 'sr_restored_user'@'%'");assert any('sr_restored_role' in row[0] for row in qt.fetchall())
                for q in (qs,qt):q.execute('SHOW CREATE PROCEDURE sr_restored_a.p')
                source_procedure=qs.fetchone()[2]
                assert source_procedure==qt.fetchone()[2]
                boundary=backup['result']['artifact']['native_boundary']
                qt.execute('SELECT GTID_SUBSET(%s,@@GLOBAL.gtid_executed)',(boundary['gtidExecuted'],));assert qt.fetchone()==(1,)
                assert start({'job_id':restored['job_id'],'review_digest':restored['review_digest']})['native_load_outcome']=='returned'
                proof['checks'].append('native-instance-load-restores-two-schemas-wide-unicode-blob-cross-schema-view-procedure-accounts-and-roles-with-reviewed-native-GTID-base-installation')
                if acceptance:
                    def acceptance_review():
                        return http('review',{'source_server_id':sid,'backup_job_id':backup['job_id'],
                            'options':{'target_confirmation':target_uuid,'server_wide_write_pause_confirmed':True,'threads':1,'timeout_seconds':120}},prefix='mysql_instance_acceptance_')
                    def accept(expect_unlock=True):
                        planned=acceptance_review()
                        value=wait(start(planned,prefix='mysql_instance_acceptance_'),prefix='mysql_instance_acceptance_')
                        if value['state']!='verification_observed':
                            (output/'acceptance-failure.json').write_text(json.dumps(value,indent=2)+'\n')
                            raise AssertionError('Native independent acceptance did not finish its observations')
                        assert value['result']['server_locks_released'] is expect_unlock and not value['restore_issued']
                        assert value['server_lock_owner']['admitted'],value['server_lock_owner']
                        return value
                    http('review',{'source_server_id':sid,'backup_job_id':backup['job_id'],
                        'options':{'target_confirmation':target_uuid,'server_wide_write_pause_confirmed':False}},prefix='mysql_instance_acceptance_',refused=True)
                    accepted=accept()
                    assert accepted['acceptance_outcome']=='matched',accepted
                    assert all(accepted['result'][key]['matched'] is True for key in ('data','definitions','accounts'))
                    proof['checks'].append('independent-native-full-dump-count-checksum-schema-and-exported-account-definition-acceptance-under-explicit-server-read-and-instance-backup-locks')
                    if system_state:
                        assert accepted['result']['system_state']['matched'] is True
                        assert 'private-system-state-fixture' not in json.dumps(accepted)
                        qt.execute("ALTER SERVER sr_system_checkpoint OPTIONS(HOST 'native-changed.example')")
                        changed=accept()
                        assert changed['acceptance_outcome']=='not_matched' and changed['result']['system_state']['matched'] is False
                        assert all(changed['result'][key]['matched'] for key in ('data','definitions','accounts'))
                        assert [row['table'] for row in changed['result']['system_state']['differences']]==['servers']
                        assert not changed['result']['selected_dump_surfaces_verified']
                        qt.execute("ALTER SERVER sr_system_checkpoint OPTIONS(HOST 'native-original.example')")
                        assert accept()['acceptance_outcome']=='matched'
                        proof['checks'].append('native-system-checkpoint-with-held-source-locks-sealed-digests-and-independent-detection-of-unexported-foreign-server-change-without-import')
                    qt.execute('UPDATE sr_restored_a.t SET body="same count changed value"')
                    changed=accept();assert changed['acceptance_outcome']=='not_matched' and changed['result']['data']['matched'] is False
                    assert changed['result']['row_counts']['matched'] and changed['result']['definitions']['matched'] and changed['result']['accounts']['matched']
                    assert any(error['code']==53031 for error in changed['result']['control']['errors'])
                    qt.execute('UPDATE sr_restored_a.t SET body=%s',('native 雪',))
                    proof['checks'].append('actual-native-checksum-mismatch-53031-is-separate-from-row-count-and-definition-acceptance-without-restore-replay')
                    qt.execute('INSERT INTO sr_restored_a.t VALUES(9007199254740994,"outside original chunk boundary",NULL)')
                    changed=accept();assert changed['acceptance_outcome']=='not_matched' and not changed['result']['row_counts']['matched']
                    assert changed['result']['control']['checksum_returned'] and changed['result']['data']['matched'] is False
                    qt.execute('DELETE FROM sr_restored_a.t WHERE id=9007199254740994')
                    proof['checks'].append('full-instance-counts-detect-extra-rows-beyond-native-checksum-chunk-boundaries')
                    qt.execute("ALTER PROCEDURE sr_restored_a.p COMMENT 'changed native definition'")
                    changed=accept();assert changed['acceptance_outcome']=='not_matched' and changed['result']['definitions']['matched'] is False
                    assert changed['result']['data']['matched'] and changed['result']['accounts']['matched']
                    qt.execute('DROP PROCEDURE sr_restored_a.p')
                    qt.execute('USE sr_restored_a')
                    qt.execute(source_procedure)
                    qt.execute('SHOW CREATE PROCEDURE sr_restored_a.p');assert qt.fetchone()[2]==source_procedure
                    proof['checks'].append('native-routine-definition-change-fails-exact-definition-acceptance-despite-matching-row-data')
                    qt.execute("GRANT UPDATE ON sr_restored_b.* TO 'sr_restored_role'@'%'")
                    changed=accept();assert changed['acceptance_outcome']=='not_matched' and changed['result']['accounts']['matched'] is False
                    assert changed['result']['data']['matched'] and changed['result']['definitions']['matched']
                    qt.execute("REVOKE UPDATE ON sr_restored_b.* FROM 'sr_restored_role'@'%'")
                    proof['checks'].append('native-role-grant-change-fails-exported-account-acceptance-without-disclosing-native-sql-or-authentication-material')
                    assert accept()['acceptance_outcome']=='matched'
                    original=http('status',{'job_id':restored['job_id']});assert original['native_load_outcome']=='returned' and not original['data_recovery_verified']
                    proof['checks'].append('new-acceptance-after-fixture-reversion-is-separate-from-the-original-restore-acknowledgement-and-prior-failed-observations')
                    from pgadmin.cdeadmin.workspace.mysql_instance_acceptance_jobs import InstanceAcceptanceTransport
                    from pgadmin.cdeadmin.providers.mysql_family import mysql_acceptance_lock_owner as lock_owner
                    execute_acceptance=InstanceAcceptanceTransport.execute
                    def lost_unlock(self,*args,**kwargs):
                        connection=self.connection;cursor=connection.cursor
                        class Cursor:
                            def __init__(self,wrapped):self.wrapped=wrapped
                            def __getattr__(self,name):return getattr(self.wrapped,name)
                            def execute(self,source,*args,**kwargs):
                                if source in {'UNLOCK TABLES','UNLOCK INSTANCE'}:raise OSError('Owned missing unlock reply')
                                return self.wrapped.execute(source,*args,**kwargs)
                        connection.cursor=lambda *args,**kwargs:Cursor(cursor(*args,**kwargs))
                        try:return execute_acceptance(self,*args,**kwargs)
                        finally:connection.cursor=cursor
                    InstanceAcceptanceTransport.execute=lost_unlock
                    try:lost=accept(expect_unlock=False)
                    finally:InstanceAcceptanceTransport.execute=execute_acceptance
                    assert lost['acceptance_outcome']=='matched' and not lost['recovery_fence_release_confirmed']
                    jobs=service.mysql_instance_acceptance_jobs
                    deadline=time.monotonic()+10
                    while jobs.workers.get(lost['job_id']):
                        if time.monotonic()>deadline:raise TimeoutError('Owned native acceptance cleanup worker')
                        time.sleep(.05)
                    observed=http('reconcile',{'job_id':lost['job_id']},prefix='mysql_instance_acceptance_')
                    assert observed['recovery_fence_release_confirmed'] and observed['result']==lost['result']
                    assert observed['acceptance_outcome']=='matched' and observed['reconciliation']['private_server_lock_cleanup']['released']
                    recovered_acceptance_id=lost['job_id']
                    proof['checks'].append('lost-native-unlock-replies-retain-matched-check-facts-and-protection-until-independent-original-session-cleanup-observation')
                    planned=acceptance_review();record=jobs.load(planned['job_id'],uid,planned['endpoint_id']);jobs.claim_fence(record)
                    private=db_client._connector(host=target['host'],port=target['port'],user='root',
                        password=password,use_pure=not use_c,autocommit=True)
                    classes.append(type(private).__name__)
                    try:
                        witness=lock_owner.acquire(private,record['job_id'],target_uuid);assert witness['admitted'],witness
                        cursor=private.cursor();cursor.execute('LOCK INSTANCE FOR BACKUP');cursor.execute('FLUSH TABLES WITH READ LOCK');cursor.close()
                        # This fixture has no launched utility. It models only an
                        # abandoned private SQL owner, with utility absence known.
                        jobs.update(record,state='unknown',server_lock_owner=witness,native_load_outcome='not_dispatched',
                            native_process_termination_confirmed=True,recovery_fence_release_confirmed=False)
                        observed=http('reconcile',{'job_id':record['job_id']},prefix='mysql_instance_acceptance_')
                        assert not observed['reconciliation']['private_server_lock_cleanup']['released']
                        http('acknowledge',{'job_id':record['job_id'],'target_confirmation':target_uuid,'observation_digest':observed['observation_digest']},prefix='mysql_instance_acceptance_',refused=True)
                    finally:db_client._discard_failed_session(private)
                    deadline=time.monotonic()+10
                    while True:
                        observed=http('reconcile',{'job_id':record['job_id']},prefix='mysql_instance_acceptance_')
                        if observed.get('recovery_fence_release_confirmed'):break
                        if time.monotonic()>deadline:raise TimeoutError('Native private-session teardown not observed')
                        time.sleep(.05)
                    # Even observed SQL cleanup cannot replace unknown utility
                    # termination or rewrite the original outcome.
                    jobs.update(record,native_process_termination_confirmed=False)
                    http('acknowledge',{'job_id':record['job_id'],'target_confirmation':target_uuid,'observation_digest':observed['observation_digest']},prefix='mysql_instance_acceptance_',refused=True)
                    jobs.update(record,native_process_termination_confirmed=True)
                    acknowledged=http('acknowledge',{'job_id':record['job_id'],'target_confirmation':target_uuid,'observation_digest':observed['observation_digest']},prefix='mysql_instance_acceptance_')
                    assert acknowledged['state']=='unknown' and acknowledged['native_load_outcome']=='not_dispatched'
                    proof['checks'].append('live-native-private-lock-owner-blocks-release-and-observed-session-teardown-still-requires-separate-known-utility-termination-and-explicit-unknown-target-acknowledgement')
                qs.execute('INSERT INTO sr_restored_b.t VALUES(2,"after backup",NULL)');qs.execute('FLUSH BINARY LOGS')
                archived=wait(start(http('review',{'options':{'start_file':boundary['file'],'start_position':boundary['position'],'threads':1,'timeout_seconds':120}},url=surl,prefix='mysql_binlog_'),url=surl,prefix='mysql_binlog_'),url=surl,prefix='mysql_binlog_')
                assert archived['state']=='completed'
                replay=wait(start(http('review',{'source_server_id':sid,'archive_job_id':archived['job_id'],
                    'options':{'target_confirmation':target_uuid}},prefix='mysql_binlog_replay_'),prefix='mysql_binlog_replay_'),prefix='mysql_binlog_replay_')
                assert replay['state']=='native_load_returned',replay
                qt.execute('SELECT COUNT(*) FROM sr_restored_b.t');assert qt.fetchone()==(2,)
                proof['checks'].append('actual-application-instance-base-to-native-log-continuation-restores-later-source-row-on-separate-target')
                cancelled=review({**selected,'load_users':False,'exclude_users':[],'update_gtid_set':'off','drop_existing_objects':True})
                assert http('cancel',{'job_id':cancelled['job_id']})['state']=='cancelled' and start(cancelled)['state']=='cancelled'
                proof['checks'].append('cancelled-review-and-repeated-dispatch-never-reissue-a-native-load')
                plain={**selected,'load_users':False,'update_gtid_set':'off','drop_existing_objects':True};plain.pop('exclude_users')
                original=InstanceRestoreTransport.execute
                def post_ack(*args,**kwargs):
                    result=original(*args,**kwargs);failure=OSError('Owned suppressed post-ack wrapper reply');failure.control=result['control'];failure.observation=result['tool'];raise failure
                InstanceRestoreTransport.execute=post_ack
                try:failed=wait(start(review(plain)))
                finally:InstanceRestoreTransport.execute=original
                assert failed['state']=='native_returned_unverified' and failed['native_load_outcome']=='returned',failed
                assert http('reconcile',{'job_id':failed['job_id']})['native_load_outcome']=='returned'
                qt.execute('SELECT COUNT(*) FROM sr_restored_b.t');assert qt.fetchone()==(1,)
                proof['checks'].append('real-native-load-ack-survives-later-wrapper-failure-and-observer-reconciliation-never-reissues-the-restore')
                def lost(*args,**kwargs):
                    result=original(*args,**kwargs);failure=OSError('Owned lost native reply');failure.observation=result['tool'];raise failure
                InstanceRestoreTransport.execute=lost
                try:uncertain=wait(start(review(plain)))
                finally:InstanceRestoreTransport.execute=original
                assert uncertain['state']=='unknown' and uncertain['native_load_outcome']=='unknown',uncertain
                observed=http('reconcile',{'job_id':uncertain['job_id']});assert observed['reconciliation']['native_lock_free']
                acknowledged=http('acknowledge',{'job_id':uncertain['job_id'],'target_confirmation':target_uuid,'observation_digest':observed['observation_digest']})
                assert acknowledged['native_load_outcome']=='unknown' and start(uncertain)['state']=='unknown'
                proof['checks'].append('lost-native-reply-keeps-unknown-outcome-and-target-fence-until-explicit-current-state-acknowledgement-without-replay')
                denied=wait(start(review(plain,url=durl),url=durl),url=durl)
                assert denied['state']=='unknown' and denied['native_error']['message'] and denied['native_load_outcome']=='unknown',denied
                assert password not in denied['native_error']['message']
                observed=http('reconcile',{'job_id':denied['job_id']},url=durl)
                http('acknowledge',{'job_id':denied['job_id'],'target_confirmation':target_uuid,'observation_digest':observed['observation_digest']},url=durl)
                proof['checks'].append('actual-native-privilege-refusal-exposes-redacted-error-and-retains-partial-effect-uncertainty-until-reviewed-target-acknowledgement')
                planned=review(plain);qt.execute('LOCK TABLES sr_restored_b.t WRITE')
                try:
                    blocked=start(planned);deadline=time.monotonic()+30
                    while blocked.get('phase')!='native_dispatch' or (blocked.get('progress') or {}).get('elapsed_seconds',0)<.5:
                        if blocked['state'] not in {'dispatching','active'} or time.monotonic()>deadline:
                            raise AssertionError('Owned native instance load did not enter its blocked utility')
                        time.sleep(.05);blocked=http('status',{'job_id':blocked['job_id']})
                    cancelled=wait(http('cancel',{'job_id':blocked['job_id']}))
                    assert cancelled['state']=='unknown' and cancelled['native_load_outcome']=='unknown' and cancelled['native_process_termination_confirmed'],cancelled
                finally:qt.execute('UNLOCK TABLES')
                deadline=time.monotonic()+30
                observed=http('reconcile',{'job_id':cancelled['job_id']})
                while not observed['reconciliation']['native_lock_free']:
                    if time.monotonic()>deadline:raise TimeoutError('Owned cancelled native restore still holds its target lock')
                    time.sleep(.1);observed=http('reconcile',{'job_id':cancelled['job_id']})
                accepted=http('acknowledge',{'job_id':cancelled['job_id'],'target_confirmation':target_uuid,'observation_digest':observed['observation_digest']})
                assert accepted['native_load_outcome']=='unknown'
                proof['checks'].append('active-native-load-cancellation-confirms-local-process-cleanup-and-requires-released-native-lock-and-explicit-target-acknowledgement-without-inferred-rollback')
                if acceptance:
                    from mysql_interruption_qualification import qualify as qualify_interruption
                    # Cancellation can leave dropped objects. Re-establish the
                    # owned fixture through a new reviewed native load.
                    reset=wait(start(review(plain)))
                    assert reset['state']=='native_load_returned' and reset['native_load_outcome']=='returned'
                    interruption_checks,interrupted_restore_id=qualify_interruption(service,db_client,backup,uid,
                        target,target_uuid,review,http,qt,shell,output,password)
                    proof['checks'].extend(interruption_checks)
                if binary:proof['browser']=browser(app,output,tid,backup['job_id'],target_uuid,binary,driver_binary,acceptance,recovered_acceptance_id,interrupted_restore_id,system_state)
                proof['native_connection_classes']=sorted(set(classes));assert proof['native_connection_classes']==[('CharsetCMySQLConnection' if use_c else 'CharsetMySQLConnection')]
                proof['complete']=True
            finally:
                for q in cursors:q.close()
                for handle in handles:handle.close()
    finally:
        proof['owned_servers_stopped']=[fixture['owned_server_stopped'] for fixture in fixtures]
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def browser(app,output,tid,backup_id,target_uuid,binary,driver_binary,acceptance=False,recovered_acceptance_id=None,interrupted_restore_id=None,system_state=False):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver import ActionChains
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer,expand
    http=make_server('127.0.0.1',0,app,threaded=True);thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start();driver=None
    try:
        options=webdriver.ChromeOptions();options.binary_location=binary
        for flag in ('--headless=new','--no-sandbox','--disable-dev-shm-usage','--window-size=1800,1200'):options.add_argument(flag)
        options.add_argument('--user-data-dir='+str(output/'browser-profile'));options.set_capability('goog:loggingPrefs',{'browser':'ALL'})
        driver=webdriver.Chrome(options=options,service=Service(driver_binary));driver.get('http://127.0.0.1:'+str(http.server_port)+'/browser/')
        wait=WebDriverWait(driver,120);ensure_data_explorer(wait);expand(wait,'Connectors');expand(wait,'MySQL')
        def target(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR,'.file-name') if node.is_displayed() and browser.execute_script('const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);',node,tid)),None)
        ActionChains(driver).context_click(wait.until(target)).perform()
        wait.until(lambda b:next((node for node in b.find_elements(By.CSS_SELECTOR,'[role="menuitem"]') if node.is_displayed() and node.text.strip()=='Restore'),None)).click()
        wait.until(lambda b:next((node for node in b.find_elements(By.CSS_SELECTOR,'[role="menuitem"]') if node.is_displayed() and 'MySQL full-instance restores' in node.text),None)).click()
        def click(label,tag='button'):
            def attempt(browser):
                for node in browser.find_elements(By.TAG_NAME,tag):
                    if node.is_enabled() and node.get_attribute('textContent').strip()==label:
                        browser.execute_script('arguments[0].scrollIntoView({block:"center"});',node)
                        if node.is_displayed():node.click();return True
                return False
            wait.until(attempt)
        click('Inspect instance restore target');wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,'[aria-label="Native instance restore target"]'))
        click('Load instance backup sources');click('Use backup source Owned instance recovery source');click('Load source instance backups');click('Use instance backup '+backup_id)
        confirmation=driver.find_element(By.XPATH,'//label[contains(text(),"Confirm native restore target UUID")]/following::input[1]')
        confirmation.send_keys(target_uuid)
        editor=driver.find_element(By.XPATH,'//label[contains(text(),"Native instance restore options")]/following::textarea[1]')
        selected=json.dumps({'load_users':False,'checksum':True,'threads':1,'drop_existing_objects':True,'skip_binlog':True,'update_gtid_set':'off','timeout_seconds':120})
        editor.send_keys(Keys.CONTROL,'a');editor.send_keys(Keys.BACKSPACE);editor.send_keys(selected)
        wait.until(lambda _browser:editor.get_attribute('value')==selected)
        click('Review full-instance restore');wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,'[aria-label="Instance restore review"]'))
        click('Confirm and start instance restore')
        wait.until(lambda b:any(': native_load_returned.' in node.get_attribute('textContent') and 'outcome: returned.' in node.get_attribute('textContent') for node in b.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
        click('Observe instance restore target')
        wait.until(lambda b:any('native_lock_free' in node.get_attribute('textContent') for node in b.find_elements(By.TAG_NAME,'pre')))
        checks=['native-target-context-action','owned-source-and-backup-selection-with-exact-target-confirmation','review-and-explicit-native-instance-load','separate-target-observation-preserves-original-native-outcome']
        if acceptance:
            click('Independent dump acceptance','summary')
            consent=driver.find_element(By.XPATH,'//label[contains(.,"Confirm server-wide write pause for independent acceptance")]')
            driver.execute_script('arguments[0].scrollIntoView({block:"center"});',consent);consent.click()
            click('Review independent dump acceptance');wait.until(lambda b:b.find_elements(By.CSS_SELECTOR,'[aria-label="Independent dump acceptance review"]'))
            click('Confirm and start independent acceptance')
            wait.until(lambda b:any('Recorded outcome: matched.' in node.get_attribute('textContent') for node in b.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
            table=driver.find_element(By.CSS_SELECTOR,'[aria-label="Recorded dump acceptance surfaces"]')
            assert table.get_attribute('textContent').count('Matched')==(4 if system_state else 3)
            if system_state:
                assert 'system_stateMatched' in table.get_attribute('textContent')
                checks.append('separate-native-system-table-checkpoint-result-in-built-desktop')
            checks+=['independent-read-lock-confirmation-and-reviewed-acceptance','separate-exported-data-definition-account-results']
            if recovered_acceptance_id:
                click('Load independent acceptance jobs');click('Inspect acceptance '+recovered_acceptance_id)
                wait.until(lambda b:any('A later native observation confirmed' in node.get_attribute('textContent') for node in b.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
                assert any('Recorded outcome: matched.' in node.get_attribute('textContent') for node in driver.find_elements(By.CSS_SELECTOR,'[role="alert"]'))
                checks+=['retained-unlock-reply-loss-receipt-reachable-after-later-native-session-cleanup','native-session-cleanup-keeps-original-comparison-outcome-visible']
        if interrupted_restore_id:
            click('Load instance restore jobs');click('Inspect instance restore '+interrupted_restore_id)
            click('Observe original restore utility without SQL connection')
            wait.until(lambda b:any('Interrupted utility cleanup: confirmed.' in node.get_attribute('textContent') for node in b.find_elements(By.CSS_SELECTOR,'[role="alert"]')))
            assert any('Original native load outcome: unknown' in node.get_attribute('textContent') for node in driver.find_elements(By.CSS_SELECTOR,'[role="alert"]'))
            checks+=['interrupted-native-utility-receipt-reachable-in-built-desktop','independent-cleanup-observation-without-SQL-keeps-original-load-outcome-unknown']
        driver.save_screenshot(str(output/'native-instance-restore.png'))
        errors=[entry for entry in driver.get_log('browser') if entry['level']=='SEVERE'];assert not errors,errors
        return {'complete':True,'version':driver.capabilities['browserVersion'],'console_errors':errors,
            'checks':checks}
    except Exception:
        if driver:
            driver.save_screenshot(str(output/'browser-failure.png'));(output/'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME,'body').text)
        raise
    finally:
        if driver:driver.quit()
        http.shutdown();http.server_close();thread.join(timeout=10)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);parser.add_argument('--mysql-shell',required=True);parser.add_argument('--use-c',action='store_true')
    parser.add_argument('--browser-binary');parser.add_argument('--driver-binary');parser.add_argument('--acceptance',action='store_true');parser.add_argument('--system-state',action='store_true')
    args=parser.parse_args();proof=qualify(args.output,args.mysql_shell,args.use_c,args.browser_binary,args.driver_binary,args.acceptance,args.system_state);print(json.dumps({'complete':proof['complete'],'checks':len(proof['checks'])}))

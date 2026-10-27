"""Owned native PXB policies with real SSH, encrypted delegation and closed UI."""
from copy import deepcopy
import base64
import hashlib
import json
from pathlib import Path
import secrets
import threading
import time
from unittest.mock import patch


def qualify_schedule(app,output,oracle,container,port,password,selected,credentials,binary=None,driver_binary=None):
    from flask import url_for
    from cdeadmin_mysql_online_ddl_qualification import registration
    from cdeadmin_mysql_family_object_live_orchestrator import _run
    from cdeadmin_mysql_physical_retention_qualification import browser
    from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_transport as transport
    from pgadmin.cdeadmin.workspace import mysql_physical_batch_retention as batch
    from pgadmin.cdeadmin.workspace.mysql_physical_retention_schedule import ScheduleHost
    from pgadmin.cdeadmin.report_scheduler.crypto import WorkerKeyRing
    from mysql_qualification_support import _root_connection
    root=Path(__file__).resolve().parents[1];output=Path(output);service=app.extensions['cdeadmin_provider_workspace']
    paths=[Path(__file__),root/'web/pgadmin/cdeadmin/workspace/mysql_physical_retention_schedule.py',
        root/'web/pgadmin/cdeadmin/workspace/mysql_physical_batch_retention.py',root/'web/pgadmin/cdeadmin/workspace/mysql_physical_retention.py',
        root/'web/pgadmin/static/js/Dialogs/MySQLPhysicalBatchRetention.jsx',root/'tools/cdeadmin_mysql_physical_retention_qualification.py']
    proof={'complete':False,'interfaces':[],'history_testing':'not run','source_sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    for use_c in (False,True):
        sid,_target,_post=registration(app,{'host':'127.0.0.1','port':port},password,use_c,username='sr_physical')
        with app.test_request_context('/'):
            item=__import__('pgadmin.model',fromlist=['Server']).Server.query.get(sid)
            endpoint=url_for('NODE-server.cde_workspace_id',gid=item.servergroup_id,sid=sid);owner=item.user_id
        client=app.test_client()
        with client.session_transaction() as session:session['_user_id'],session['_fresh']=str(owner),True
        checks=[]
        def post(operation,request,refused=False):
            response=client.post(endpoint,json={'action':'mysql_physical_'+operation,'request':request});value=response.get_json()
            if refused:assert not value.get('success'),value;return value
            assert response.status_code==200 and value.get('success'),value
            return value['data']
        def create(phase='backup',parent=None):
            ticket=post('review',{'options':{**deepcopy(selected),'phase':phase,'input_job_id':parent},'credentials':credentials})
            value=post('start',{'job_id':ticket['job_id'],'review_digest':ticket['review_digest'],'confirmed':True,'delegate_database_credentials':True,'credentials':credentials})
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                value=post('reconcile',{'job_id':value['job_id'],'credentials':credentials})
                if value.get('remote_observation',{}).get('supervisor_finished'):
                    assert value['file_verification_confirmed'],value;return value
                time.sleep(.15)
            raise TimeoutError('Native physical schedule fixture did not finish')
        def review(anchor):return post('retention_schedule_review',{'scope_job_id':anchor['job_id'],
            'options':{'policy':{'retention_days':0,'keep_latest':1},'interval_seconds':60,'expires_after_days':1},'credentials':credentials})
        def confirmation(value):return {'job_id':value['job_id'],'confirmed':True,'schedule_confirmation':value['job_id']}
        def enable(value):return post('retention_schedule_enable',{**confirmation(value),'review_digest':value['review_digest'],'delegate_ssh_credentials':True,'credentials':credentials})
        def wait_grant(value,predicate):
            deadline=time.monotonic()+90
            while time.monotonic()<deadline:
                current=post('retention_schedule_status',{'job_id':value['job_id']})
                if predicate(current):return current
                time.sleep(.1)
            raise TimeoutError('Scheduled native occurrence did not reach its expected state')
        def cancel_occurrence(value):
            ticket=post('retention_batch_status',{'job_id':value['last_occurrence_id']})
            return post('retention_batch_cancel',{'job_id':ticket['job_id'],'review_digest':ticket['review_digest'],
                'confirmed':True,'batch_confirmation':ticket['job_id'],'credentials':credentials})
        def exists(value):return _run(['docker','exec',container,'test','-d',selected['workspace']+'/'+value['job_id']+'/artifact'],check=False).returncode==0
        backup=create();child=create('prepare',backup['job_id']);newest=create();grant=review(backup)
        assert not grant['ssh_delegation_present'] and 'ssh_envelope' not in grant
        host=service.mysql_physical_scheduler
        raw=host.jobs.load(grant['job_id'],owner,grant['endpoint_id']);assert not raw.get('ssh_envelope')
        checks.append('review-uses-transient-SSH-and-stores-no-delegated-credential-before-explicit-enablement')
        original=transport.Transport.request
        def lost(channel,payload,*args,**kwargs):
            value=original(channel,payload,*args,**kwargs)
            if payload['action']=='retention_remove':raise transport.HostError('Owned scheduled native completion reply loss')
            return value
        oracle.autocommit=False
        with oracle.cursor() as cursor:cursor.execute('INSERT INTO sr_osc.pending VALUES(%s)',(9001+int(use_c),));cursor.execute('SAVEPOINT physical_schedule_guard')
        control=_root_connection('mysql',port);control.autocommit=True;locked=False
        try:
            with control.cursor() as cursor:cursor.execute("ALTER USER 'sr_physical'@'%' ACCOUNT LOCK")
            locked=True
            with patch.object(transport.Transport,'request',lost):
                enable(grant);observed=wait_grant(grant,lambda value:value['state']=='attention_required')
            assert not observed['ssh_delegation_present'] and not exists(child) and exists(backup) and exists(newest)
        finally:
            if locked:
                with control.cursor() as cursor:cursor.execute("ALTER USER 'sr_physical'@'%' ACCOUNT UNLOCK")
            control.close()
            with oracle.cursor() as cursor:
                cursor.execute('ROLLBACK TO SAVEPOINT physical_schedule_guard');cursor.execute('SELECT COUNT(*) FROM sr_osc.pending');assert cursor.fetchone()[0]==1
            oracle.rollback();oracle.autocommit=True
        ticket=post('retention_batch_status',{'job_id':observed['last_occurrence_id']});assert ticket['state']=='interrupted'
        reconciled=post('retention_batch_reconcile',{'job_id':ticket['job_id'],'credentials':credentials});assert reconciled['state']=='paused'
        assert post('retention_schedule_status',{'job_id':grant['job_id']})['state']=='attention_required'
        post('retention_schedule_scan',confirmation(grant),refused=True)
        assert cancel_occurrence(observed)['state']=='cancelled' and exists(backup)
        checks.append('unattended-native-removal-with-source-SQL-account-locked-preserves-pending-transaction-and-savepoint')
        checks.append('lost-completion-reply-suspends-future-occurrences-clears-delegation-and-reconciliation-never-reenables')
        latest=create();grant=review(backup);action=batch.action
        def revoke(*args,**kwargs):
            value=action(*args,**kwargs)
            if args[5]=='retention_batch_advance' and value['state']=='paused':post('retention_schedule_disable',confirmation(grant))
            return value
        with patch.object(batch,'action',revoke):
            enable(grant);observed=wait_grant(grant,lambda value:value['state']=='disabled')
        assert not exists(backup) and exists(newest) and exists(latest)
        assert not observed['ssh_delegation_present']
        assert cancel_occurrence(observed)['state']=='cancelled'
        checks.append('revocation-between-real-host-deletions-preserves-unattempted-files-and-removes-encrypted-delegation')
        if use_c and binary and driver_binary:
            closed=threading.Event();entered=threading.Event()
            def hold(*args,**kwargs):
                if args[5]=='retention_batch_advance':
                    entered.set();assert closed.wait(90),'Owned viewer-close gate timed out'
                return action(*args,**kwargs)
            with patch.object(batch,'action',hold):
                proof['browser']=browser(app,output/'physical-schedule-desktop',sid,newest['job_id'],password,credentials,binary,driver_binary,scheduled=True,closed=closed)
                assert entered.wait(10) and closed.is_set()
                ui=wait_grant({'job_id':proof['browser']['schedule_job_id']},lambda value:bool(value.get('last_scan_at')) and not value.get('scan_state'))
            assert ui['state']=='enabled' and not exists(newest) and exists(latest)
            post('retention_schedule_disable',confirmation(ui))
            checks.append('built-desktop-policy-continues-native-cleanup-after-viewer-closes-and-retains-newest-full-backup')
        else:
            grant=review(newest);enable(grant)
            observed=wait_grant(grant,lambda value:bool(value.get('last_scan_at')) and not value.get('scan_state'))
            assert observed['state']=='enabled' and not exists(newest) and exists(latest)
            post('retention_schedule_disable',confirmation(observed))
            checks.append('later-native-backup-jobs-enter-only-a-fresh-due-occurrence-with-the-retained-floor-preserved')
        grant=review(latest);enable(grant)
        observed=wait_grant(grant,lambda value:bool(value.get('last_scan_at')) and not value.get('scan_state'))
        key_id='rotated-fixture-c' if use_c else 'rotated-fixture-pure'
        keys={**app.config['CDEADMIN_MYSQL_PHYSICAL_WORKER_KEYS'],key_id:base64.b64encode(secrets.token_bytes(32)).decode('ascii')}
        app.config.update(CDEADMIN_MYSQL_PHYSICAL_WORKER_KEYS=keys,CDEADMIN_MYSQL_PHYSICAL_WORKER_ACTIVE_KEY_ID=key_id)
        host.keys=WorkerKeyRing(keys,key_id)
        rotated=post('retention_schedule_rotate',confirmation(grant));assert rotated['ssh_delegation_present'] and 'ssh_envelope' not in rotated
        raw=host.jobs.load(grant['job_id'],owner,grant['endpoint_id'])
        assert json.loads(raw['ssh_envelope'])['key_id']==key_id and 'BEGIN OPENSSH PRIVATE KEY' not in json.dumps(raw)
        assert host.close()
        host=service.mysql_physical_scheduler=ScheduleHost(app,service);host.start()
        with app.app_context():assert host.tick(grant['job_id'],force=True)['state']=='enabled'
        host.jobs.update(raw,valid_until=0,next_scan_at=0)
        observed=wait_grant(grant,lambda value:value['state']=='expired')
        assert not observed['ssh_delegation_present'] and exists(latest)
        checks.append('native-policy-encrypted-key-rotation-idle-worker-restart-and-expiry-preserve-retained-files')
        proof['interfaces'].append({'use_c':use_c,'checks':checks,'complete':True})
    proof['complete']=True
    (output/'physical-schedule-summary.json').write_text(json.dumps(proof,indent=2)+'\n');return proof

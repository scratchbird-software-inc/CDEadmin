"""Real native recurring backups, encrypted SQL delegation and startup drills."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import threading
import time
from unittest.mock import patch


def qualify_backups(app,output,oracle,container,port,password,selected,credentials,binary=None,driver_binary=None):
    from flask import url_for
    from cdeadmin_mysql_online_ddl_qualification import registration
    from cdeadmin_mysql_family_object_live_orchestrator import _run
    from cdeadmin_mysql_physical_retention_qualification import browser
    from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_transport as transport
    from pgadmin.cdeadmin.workspace.mysql_physical_backup_schedule import ScheduleHost
    from pgadmin.cdeadmin.workspace.mysql_physical_service import manager
    from pgadmin.model import Server,db
    output=Path(output);root=Path(__file__).resolve().parents[1];service=app.extensions['cdeadmin_provider_workspace']
    paths=[Path(__file__),root/'web/pgadmin/cdeadmin/workspace/mysql_physical_backup_schedule.py',
        root/'web/pgadmin/cdeadmin/workspace/mysql_physical_service.py',root/'web/pgadmin/cdeadmin/workspace/mysql_host_service.py',
        root/'web/pgadmin/cdeadmin/workspace/mysql_physical_retention_schedule.py',root/'web/pgadmin/static/js/Dialogs/MySQLPhysicalBackupSchedule.jsx',
        root/'tools/cdeadmin_mysql_physical_retention_qualification.py']
    proof={'complete':False,'interfaces':[],'history_testing':'not run','source_sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    for use_c in (False,True):
        sid,_target,_post=registration(app,{'host':'127.0.0.1','port':port},password,use_c,username='sr_physical')
        with app.test_request_context('/'):
            server=db.session.get(Server,sid);owner=server.user_id;name=server.name
            endpoint=url_for('NODE-server.cde_workspace_id',gid=server.servergroup_id,sid=sid)
            verification=url_for('NODE-server.verify_endpoint_id',gid=server.servergroup_id,sid=sid)
        client=app.test_client()
        with client.session_transaction() as session:session['_user_id'],session['_fresh']=str(owner),True
        checks=[]
        def post(action,request,refused=False):
            response=client.post(endpoint,json={'action':action,'request':request});value=response.get_json()
            if refused:assert not value.get('success'),value;return value
            assert response.status_code==200 and value.get('success'),value
            return value['data']
        def physical(action,request,refused=False):return post('mysql_physical_'+action,request,refused)
        def schedule(action,request,refused=False):return physical('backup_schedule_'+action,request,refused)
        def confirmation(value):return {'job_id':value['job_id'],'confirmed':True,'schedule_confirmation':value['job_id']}
        def review(drill=False):return schedule('review',{'options':{'physical':deepcopy(selected),
            'drill':{'mysqld':'/usr/sbin/mysqld','gtid_mode':'ON','timeout_seconds':60} if drill else None,'interval_seconds':60,'expires_after_days':1},'credentials':credentials})
        def enable(value):return schedule('enable',{**confirmation(value),'review_digest':value['review_digest'],'delegate_ssh_credentials':True,'delegate_database_credentials':True,'credentials':credentials})
        def wait(value,predicate):
            deadline=time.monotonic()+360
            while time.monotonic()<deadline:
                current=schedule('status',{'job_id':value['job_id']})
                if predicate(current):return current
                if current['state']=='attention_required' and not predicate(current):raise AssertionError(current)
                time.sleep(.1)
            raise TimeoutError('Native backup policy did not reach its expected state')
        def occurrence(value):return schedule('occurrence',{'job_id':value['job_id'],'occurrence_id':value['last_occurrence_id']})
        host=service.mysql_backup_scheduler;grant=review()
        assert not grant['ssh_delegation_present'] and 'ssh_envelope' not in grant
        assert not host.read(grant['job_id']).get('ssh_envelope')
        checks.append('native-policy-review-does-not-persist-SSH-or-SQL-credentials-before-explicit-delegation')
        oracle.autocommit=False
        with oracle.cursor() as cursor:cursor.execute('INSERT INTO sr_osc.pending VALUES(%s)',(10001+int(use_c),));cursor.execute('SAVEPOINT recurring_backup_guard')
        try:
            enable(grant);first=wait(grant,lambda value:bool(value.get('last_scan_at')) and not value.get('scan_state'))
            result=occurrence(first)
            assert result['state']=='completed' and result['protection_released'] and result['startup_drill_outcome']=='not_requested'
            seed=result['backup_job_id'];assert physical('status',{'job_id':seed})['file_verification_confirmed']
            post('endpoint_profile_remove',{'confirmation':name},refused=True)
            with app.app_context():
                server=db.session.get(Server,sid);service.endpoint_service.forget_server_credentials(server)
            raw=host.read(grant['job_id']);assert 'BEGIN OPENSSH PRIVATE KEY' not in json.dumps(raw) and password not in json.dumps(raw)
            assert host.close();host=service.mysql_backup_scheduler=ScheduleHost(app,service)
            host.jobs.update(raw,next_scan_at=0);host.start()
            second=wait(grant,lambda value:bool(value.get('last_scan_at')) and value.get('last_occurrence_id')!=first['last_occurrence_id'] and not value.get('scan_state'))
            next_result=occurrence(second)
            assert next_result['state']=='completed' and next_result['backup_job_id']!=seed
            checks.append('real-background-native-full-backup-completes-without-viewer-and-preserves-archive-and-file-receipts')
            checks.append('idle-worker-restart-uses-encrypted-SQL-and-SSH-delegation-after-interactive-password-erasure')
            schedule('disable',confirmation(second));assert not schedule('status',{'job_id':grant['job_id']})['ssh_delegation_present']
            with oracle.cursor() as cursor:
                cursor.execute('ROLLBACK TO SAVEPOINT recurring_backup_guard');cursor.execute('SELECT COUNT(*) FROM sr_osc.pending');assert cursor.fetchone()[0]==1
        finally:oracle.rollback();oracle.autocommit=True
        assert client.post(verification,json={'password':password}).get_json()['success']
        uncertain=review();request=transport.Transport.request
        def lost(channel,payload,*args,**kwargs):
            value=request(channel,payload,*args,**kwargs)
            if payload['action']=='start':raise transport.HostError('Owned loss of original scheduled physical backup dispatch reply')
            return value
        with patch.object(transport.Transport,'request',lost):
            enable(uncertain);observed=wait(uncertain,lambda value:value['state']=='attention_required')
        result=occurrence(observed);assert result['state']=='interrupted' and len(result['native_jobs'])==1
        source=result['native_jobs'][0]['job_id'];deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            current=physical('reconcile',{'job_id':source,'credentials':credentials})
            if current['native_process_termination_confirmed'] and current.get('remote_observation',{}).get('supervisor_finished'):break
            time.sleep(.1)
        else:raise TimeoutError('Original native backup did not end after lost dispatch reply')
        assert current['state']=='unknown' and current['backup_workflow_protected']
        physical('retention_review',{'job_id':source,'credentials':credentials},refused=True)
        post('endpoint_profile_remove',{'confirmation':name},refused=True)
        released=schedule('release',{**confirmation(observed),'occurrence_id':result['job_id'],'credentials':credentials})
        assert released['state']=='interrupted' and released['protection_released']
        assert physical('status',{'job_id':source})['state']=='unknown'
        checks.append('lost-real-native-dispatch-reply-never-replays-and-explicit-release-preserves-original-unknown-outcome')
        checks.append('enabled-policy-and-unresolved-native-work-refuse-registration-removal-and-physical-retention')
        if use_c and binary and driver_binary:
            closed=threading.Event();entered=threading.Event()
            def hold(channel,payload,*args,**kwargs):
                if payload['action']=='start' and payload['phase']=='backup':entered.set();assert closed.wait(90)
                return request(channel,payload,*args,**kwargs)
            with patch.object(transport.Transport,'request',hold):
                proof['browser']=browser(app,output/'recurring-backup-desktop',sid,seed,password,credentials,binary,driver_binary,recurring=True,closed=closed)
                assert entered.wait(10) and closed.is_set()
                drilled=wait({'job_id':proof['browser']['schedule_job_id']},lambda value:bool(value.get('last_scan_at')) and not value.get('scan_state'))
        else:
            drilled=review(True);enable(drilled);drilled=wait(drilled,lambda value:bool(value.get('last_scan_at')) and not value.get('scan_state'))
        result=occurrence(drilled)
        assert result['state']=='completed' and result['startup_drill_outcome']=='passed' and result['protection_released']
        assert result['database_recovery_verified'] is False and result['production_cutover_verified'] is False
        assert [item['phase'] for item in result['native_jobs']]==['backup','prepare','copy_back','recover']
        for item in result['native_jobs']:
            value=physical('status',{'job_id':item['job_id']})
            assert value['native_process_termination_confirmed'] and value['remote_observation']['credential_cleanup_confirmed'] and not value['backup_workflow_protected']
            if item['phase']=='recover':
                identity=value['remote_observation']['sql_identity']
                assert identity['super_read_only']==1 and identity['read_only']==1 and identity['skip_networking']==1 and identity['event_scheduler']=='DISABLED'
                assert identity['skip_replica_start']==1 and not value['recovery_running'] and identity['server_uuid']!=value['source']['server_uuid']
        schedule('disable',confirmation(drilled))
        checks.append('native-prepare-copy-back-private-read-only-startup-and-confirmed-shutdown-remain-distinct-from-full-recovery-acceptance')
        proof['interfaces'].append({'use_c':use_c,'checks':checks,'complete':True})
    proof['complete']=True
    (output/'physical-backup-schedule-summary.json').write_text(json.dumps(proof,indent=2)+'\n');return proof

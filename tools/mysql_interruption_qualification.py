"""Owned native instance-load worker loss; fixtures remain with the controller."""
import json
from pathlib import Path
import subprocess
import sys
import time


def worker():
    import os
    import types
    import psutil
    root=Path(__file__).resolve().parents[1]
    package=types.ModuleType('pgadmin');package.__path__=[str(root/'web/pgadmin')];sys.modules['pgadmin']=package
    sys.path.insert(0,str(root/'web'))
    from pgadmin.cdeadmin.sdk.tooling import ProviderToolRunner,ProviderToolGrant
    from pgadmin.cdeadmin.workspace.mysql_instance_restore_jobs import InstanceRestoreJobs
    payload=json.load(sys.stdin)
    jobs=InstanceRestoreJobs(payload['store'],payload['root'])
    record=jobs.load(payload['job_id'],payload['owner'],payload['endpoint_id'])
    jobs.update(record,state='active',native_load_outcome='unknown',native_load_may_have_dispatched=True,
        worker_identity=[os.getpid(),psutil.Process().create_time()])
    from pgadmin.cdeadmin.sdk import durable_tool
    def progress(value):
        if payload.get('legacy') and value.get('durable_tool'):
            reference=value['durable_tool'];host=reference['host']
            host.pop('linux_boot_id',None);host.pop('pid_namespace',None)
            native_root=durable_tool.directory(payload['workspace'],reference['name'])
            intent=json.loads((native_root/'request.json').read_text());intent['host']=host
            intent.pop('kernel_policy',None);intent.pop('credential_file_identity',None)
            durable_tool.write(native_root/'request.json',intent)
            reference['request_sha256']=durable_tool.sha(native_root/'request.json')
        jobs.progress(record,value)
    ProviderToolRunner({'mysql-shell':payload['shell']}).run(
        ProviderToolGrant('mysql-shell',payload['workspace'],'127.0.0.1',payload['port'],timeout_seconds=120,
            secret_environment_names=('CDEADMIN_MYSQL_INSTANCE_RESTORE_CREDENTIAL_FILE',),durable_name='mysql-instance-restore',guard_parent_death=not payload.get('legacy',False)),
        ['--no-defaults','--js','--log-level=none','--quiet-start=2','--file='+payload['script']],
        secret_config=json.dumps({'password':payload['password']}).encode('utf8'),secret_argument=None,
        secret_environment_name='CDEADMIN_MYSQL_INSTANCE_RESTORE_CREDENTIAL_FILE',secret_suffix='.json',
        progress=progress)


def qualify(service,db_client,backup,uid,target,target_uuid,review,http,query,shell,output,password):
    from pgadmin.cdeadmin.providers.mysql_family import mysql_instance_restores as native
    from pgadmin.cdeadmin.providers.mysql_family import mysql_instance_dumps as dumps
    from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_archives import stage_continuation
    from pgadmin.cdeadmin.operations.fileio import private_file
    from pgadmin.cdeadmin.sdk import durable_tool
    jobs=service.mysql_instance_restore_jobs;backups=service.mysql_instance_backup_jobs
    source=backups.load(backup['job_id'],uid,backup['endpoint_id'])
    source_directory=backups.directory(source)/'archive'
    artifact=dumps.verify(source_directory,source['source'])
    checks=[];receipt_id=None
    options={'target_confirmation':target_uuid,'load_users':False,'checksum':True,'threads':1,
        'drop_existing_objects':True,'skip_binlog':True,'update_gtid_set':'off','timeout_seconds':120}
    for mode in ('worker-completion','worker-cancellation','guardian-loss','completion-receipt-lost','legacy-guardian-loss'):
        cancel=mode=='worker-cancellation';guardian_loss=mode in {'guardian-loss','legacy-guardian-loss'};legacy=mode=='legacy-guardian-loss';receipt_lost=mode=='completion-receipt-lost'
        if guardian_loss or receipt_lost:
            # A new reviewed load resets only this disposable target; it never
            # reuses the interrupted invocation or its review digest.
            reset=review(options);reset=http('start',{'job_id':reset['job_id'],'review_digest':reset['review_digest'],'confirmed':True})
            deadline=time.monotonic()+120
            while reset['state'] in {'dispatching','active','cancel_requested'}:
                if time.monotonic()>deadline:raise TimeoutError('Owned guardian fixture reset')
                time.sleep(.05);reset=http('status',{'job_id':reset['job_id']})
            assert reset['native_load_outcome']=='returned'

        planned=review(options);record=jobs.load(planned['job_id'],uid,planned['endpoint_id'])
        jobs.claim_fence(record);directory=jobs.directory(record)
        stage_continuation(source_directory,directory/'input',artifact,source['source'],verify_artifact=dumps.verify)
        path=directory/'native-instance-restore.js'
        path.write_text(native.script(db_client,target,directory/'input',record['source'],
            record['source_state']['target']['state'],record['options'],directory,'OWNED_INTERRUPTED_LOAD:'),encoding='utf8');private_file(path)
        payload={'store':str(jobs.path),'root':str(jobs.root),'job_id':record['job_id'],'owner':uid,
            'endpoint_id':record['endpoint_id'],'workspace':str(directory),'shell':str(shell),
            'port':target['port'],'script':str(path),'password':password,'legacy':legacy}
        owner=None
        log_path=Path(output)/('interrupted-utility-'+mode+'.log')
        with log_path.open('wb') as log:
            private_file(log_path)
            query.execute('LOCK TABLES sr_restored_b.t WRITE');failed=True
            try:
                owner=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--worker'],
                    stdin=subprocess.PIPE,stdout=log,stderr=subprocess.STDOUT)
                owner.stdin.write(json.dumps(payload).encode('utf8'));owner.stdin.close()
                deadline=time.monotonic()+30
                while True:
                    current=jobs.load(record['job_id'],uid,record['endpoint_id'])
                    if current.get('durable_tool') and current.get('progress',{}).get('elapsed_seconds',0)>=.5:break
                    if owner.poll() is not None or time.monotonic()>deadline:
                        raise AssertionError('Owned interrupted worker did not enter its native utility')
                    time.sleep(.05)
                if guardian_loss:
                    import psutil
                    reference=current['durable_tool'];native_root=durable_tool.directory(directory,reference['name'])
                    intent=json.loads((native_root/'request.json').read_text());assert (intent.get('kernel_policy') is None) if legacy else intent['kernel_policy']=='linux-parent-death-kill-v1'
                    started=json.loads((native_root/'started.json').read_text());guardian=psutil.Process(started['guardian_pid'])
                    assert guardian.cmdline()[-2:]==[str(native_root),reference['request_sha256']]
                    guardian.kill();owner.wait(timeout=10)
                else:owner.kill();owner.wait(timeout=5)
                lost=http('status',{'job_id':record['job_id']})
                assert lost['state']=='unknown' and lost['native_load_outcome']=='unknown' and not lost['native_process_termination_confirmed']
                if mode=='worker-completion':
                    import psutil
                    reference=current['durable_tool'];connect=db_client._connect
                    def no_sql(*_args,**_kwargs):raise AssertionError('Missing-reference observation must not contact SQL')
                    jobs.update(record,durable_tool=None);db_client._connect=no_sql
                    try:
                        unavailable=http('observe_utilities',{'job_id':record['job_id']})
                        assert unavailable['state']=='unknown' and unavailable['native_load_outcome']=='unknown'
                        assert not unavailable['native_process_termination_confirmed']
                        assert unavailable['utility_observation_unavailable']['reason']=='original_durable_reference_unavailable'
                        assert not unavailable['utility_observation_unavailable']['cancellation_requested']
                        assert psutil.Process(current['progress']['pid']).is_running()
                        with jobs.fence_store(target_uuid) as store:assert store.read()['replay_fence']['job_id']==record['job_id']
                        (Path(output)/'missing-original-reference.json').write_text(json.dumps({
                            'state':unavailable['state'],'native_load_outcome':unavailable['native_load_outcome'],
                            'native_process_termination_confirmed':False,'original_native_client_still_present':True,
                            'target_fence_retained':True,'diagnostic':unavailable['utility_observation_unavailable'],
                            'history_testing':'not run'},indent=2)+'\n')
                        checks.append('missing-original-utility-reference-is-explicitly-unavailable-while-native-client-remains-alive-without-SQL-or-guessed-cleanup')
                    finally:
                        jobs.update(record,durable_tool=reference);db_client._connect=connect
                if cancel:http('cancel',{'job_id':record['job_id']})
                if guardian_loss:
                    deadline=time.monotonic()+15;connect=db_client._connect
                    def no_sql(*_args,**_kwargs):raise AssertionError('Original utility observation must not contact SQL')
                    db_client._connect=no_sql
                    try:
                        while True:
                            if legacy:http('cancel',{'job_id':record['job_id']})
                            observed=http('observe_utilities',{'job_id':record['job_id']})
                            if observed['native_process_termination_confirmed']:break
                            if time.monotonic()>deadline:raise TimeoutError('Native guardian-loss cleanup was not independently observed')
                            time.sleep(.05)
                    finally:db_client._connect=connect
                    assert observed['native_load_outcome']=='unknown' and observed['state']=='unknown'
                    assert not observed['interrupted_utility_observation']['complete'] and not (native_root/'result.json').exists()
                    assert not jobs.load(record['job_id'],uid,record['endpoint_id']).get('target_state_acknowledged_at')

                failed=False
            finally:
                query.execute('UNLOCK TABLES')
                if owner is not None and owner.poll() is None:owner.kill();owner.wait(timeout=5)
                if failed:
                    current=jobs.load(record['job_id'],uid,record['endpoint_id'])
                    if current.get('durable_tool'):
                        durable_tool.cancel(directory,current['durable_tool'],record['program']['executable_sha256'])
                        deadline=time.monotonic()+10
                        while not durable_tool.terminated(durable_tool.observe(directory,current['durable_tool'],record['program']['executable_sha256'])):
                            if time.monotonic()>deadline:raise TimeoutError('Owned failed interruption fixture utility cleanup')
                            time.sleep(.05)
        deadline=time.monotonic()+30
        while True:
            current=jobs.load(record['job_id'],uid,record['endpoint_id'])
            observed=durable_tool.observe(directory,current['durable_tool'],record['program']['executable_sha256'])
            if durable_tool.terminated(observed):break
            if time.monotonic()>deadline:raise TimeoutError('Owned detached native utility did not finish')
            time.sleep(.05)
        assert observed['cleanup_confirmed'] and observed['credential_file_cleanup_confirmed']
        if receipt_lost:
            assert observed['complete'] and observed['return_code']==0
            native_root=durable_tool.directory(directory,current['durable_tool']['name'])
            (native_root/'result.json').unlink()
            deadline=time.monotonic()+15
            while True:
                observed=durable_tool.observe(directory,current['durable_tool'],record['program']['executable_sha256'])
                if durable_tool.terminated(observed):break
                if time.monotonic()>deadline:raise TimeoutError('Original completion guardian did not end')
                time.sleep(.05)
        if guardian_loss or receipt_lost:
            assert not observed['complete'] and 'return_code' not in observed and durable_tool.terminated(observed)
            assert observed['native_outcome_inferred'] is False
            (Path(output)/(mode+'.json')).write_text(json.dumps({'job_id':record['job_id'],'original_request_sha256':current['durable_tool']['request_sha256'],'observation':observed,'history_testing':'not run'},indent=2)+'\n')
        else:assert (observed['return_code']==0) is (not cancel)
        deadline=time.monotonic()+10
        while True:
            reconciled=http('reconcile',{'job_id':record['job_id']})
            if reconciled['reconciliation']['native_lock_free']:break
            if time.monotonic()>deadline:raise TimeoutError('Owned interrupted native utility still holds its SQL lock')
            time.sleep(.05)
        assert reconciled['native_process_termination_confirmed'] and reconciled['native_load_outcome']=='unknown'
        assert reconciled['interrupted_utility_observation']['complete'] is (not (guardian_loss or receipt_lost))
        acknowledged=http('acknowledge',{'job_id':record['job_id'],'target_confirmation':target_uuid,
            'observation_digest':reconciled['observation_digest']})
        assert acknowledged['native_load_outcome']=='unknown' and acknowledged['state']=='unknown'
        assert http('start',{'job_id':record['job_id'],'review_digest':record['review_digest'],'confirmed':True})['state']=='unknown'
        receipt_id=record['job_id']
        checks.append('actual-native-load-'+mode+'-with-independent-utility-cleanup-and-explicit-unknown-target-acknowledgement-without-replay')
    return checks,receipt_id


if __name__=='__main__' and sys.argv[1:]==['--worker']:worker()

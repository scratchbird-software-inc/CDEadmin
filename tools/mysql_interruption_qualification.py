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
    ProviderToolRunner({'mysql-shell':payload['shell']}).run(
        ProviderToolGrant('mysql-shell',payload['workspace'],'127.0.0.1',payload['port'],timeout_seconds=120,
            secret_environment_names=('CDEADMIN_MYSQL_INSTANCE_RESTORE_CREDENTIAL_FILE',),durable_name='mysql-instance-restore'),
        ['--no-defaults','--js','--log-level=none','--quiet-start=2','--file='+payload['script']],
        secret_config=json.dumps({'password':payload['password']}).encode('utf8'),secret_argument=None,
        secret_environment_name='CDEADMIN_MYSQL_INSTANCE_RESTORE_CREDENTIAL_FILE',secret_suffix='.json',
        progress=lambda value:jobs.progress(record,value))


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
    for cancel in (False,True):
        planned=review(options);record=jobs.load(planned['job_id'],uid,planned['endpoint_id'])
        jobs.claim_fence(record);directory=jobs.directory(record)
        stage_continuation(source_directory,directory/'input',artifact,source['source'],verify_artifact=dumps.verify)
        path=directory/'native-instance-restore.js'
        path.write_text(native.script(db_client,target,directory/'input',record['source'],
            record['source_state']['target']['state'],record['options'],directory,'OWNED_INTERRUPTED_LOAD:'),encoding='utf8');private_file(path)
        payload={'store':str(jobs.path),'root':str(jobs.root),'job_id':record['job_id'],'owner':uid,
            'endpoint_id':record['endpoint_id'],'workspace':str(directory),'shell':str(shell),
            'port':target['port'],'script':str(path),'password':password}
        owner=None
        log_path=Path(output)/('interrupted-utility-'+str(cancel)+'.log')
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
                owner.kill();owner.wait(timeout=5)
                lost=http('status',{'job_id':record['job_id']})
                assert lost['state']=='unknown' and lost['native_load_outcome']=='unknown' and not lost['native_process_termination_confirmed']
                if cancel:http('cancel',{'job_id':record['job_id']})
                failed=False
            finally:
                query.execute('UNLOCK TABLES')
                if owner is not None and owner.poll() is None:owner.kill();owner.wait(timeout=5)
                if failed:
                    current=jobs.load(record['job_id'],uid,record['endpoint_id'])
                    if current.get('durable_tool'):
                        durable_tool.cancel(directory,current['durable_tool'],record['program']['executable_sha256'])
                        deadline=time.monotonic()+10
                        while not durable_tool.observe(directory,current['durable_tool'],record['program']['executable_sha256'])['complete']:
                            if time.monotonic()>deadline:raise TimeoutError('Owned failed interruption fixture utility cleanup')
                            time.sleep(.05)
        deadline=time.monotonic()+30
        while True:
            current=jobs.load(record['job_id'],uid,record['endpoint_id'])
            observed=durable_tool.observe(directory,current['durable_tool'],record['program']['executable_sha256'])
            if observed['complete']:break
            if time.monotonic()>deadline:raise TimeoutError('Owned detached native utility did not finish')
            time.sleep(.05)
        assert observed['cleanup_confirmed'] and observed['credential_file_cleanup_confirmed']
        assert (observed['return_code']==0) is (not cancel)
        deadline=time.monotonic()+10
        while True:
            reconciled=http('reconcile',{'job_id':record['job_id']})
            if reconciled['reconciliation']['native_lock_free']:break
            if time.monotonic()>deadline:raise TimeoutError('Owned interrupted native utility still holds its SQL lock')
            time.sleep(.05)
        assert reconciled['native_process_termination_confirmed'] and reconciled['native_load_outcome']=='unknown'
        assert reconciled['interrupted_utility_observation']['complete']
        acknowledged=http('acknowledge',{'job_id':record['job_id'],'target_confirmation':target_uuid,
            'observation_digest':reconciled['observation_digest']})
        assert acknowledged['native_load_outcome']=='unknown' and acknowledged['state']=='unknown'
        assert http('start',{'job_id':record['job_id'],'review_digest':record['review_digest'],'confirmed':True})['state']=='unknown'
        receipt_id=record['job_id']
        checks.append('actual-native-load-'+('cancellation' if cancel else 'completion')+'-after-abrupt-application-worker-loss-with-durable-utility-cleanup-and-explicit-target-acknowledgement-without-replay')
    return checks,receipt_id


if __name__=='__main__' and sys.argv[1:]==['--worker']:worker()

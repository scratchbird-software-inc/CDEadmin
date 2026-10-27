"""Real native bootstrap dispatcher/guardian loss on an owned Router fixture."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import secrets
import shlex
import time
from unittest.mock import patch


def qualify(post,selected,credentials,owned,output,use_c,legacy_helper=None):
    import mysql.connector
    from pgadmin.cdeadmin.providers.mysql_family import mysql_router_transport as native
    output=Path(output);control=native.ssh.Transport(selected['connection'],credentials);control.connect()
    checks=[];result={'complete':False,'checks':checks,'faults':[],'history_testing':'not run'}
    def remote(code):
        channel=control.transport.open_session(timeout=5);channel.settimeout(15)
        try:
            channel.exec_command('python3 -u -c '+shlex.quote(code));out=channel.makefile('rb').read(65537);error=channel.makefile_stderr('rb').read(65537)
            assert channel.recv_exit_status()==0,error.decode('utf8','replace')
            return json.loads(out)
        finally:channel.close()
    def wait(value):
        deadline=time.monotonic()+150
        while value['state'] in {'dispatching','active','cancel_requested'}:
            if time.monotonic()>deadline:raise TimeoutError('Owned Router original invocation deadline')
            time.sleep(.05);value=post('status',{'job_id':value['job_id']})
        return value
    def admitted(value):return {**{name:value[name] for name in ('job_id','review_digest')},'confirmed':True,'credentials':credentials}
    def invoke(operation,reference):
        options={**reference['options'],'operation':operation,'binding_job_id':reference['job_id'],
            'service':{'manager':'systemd','name':'sr-reconciled-router-'+secrets.token_hex(5)+'.service'} if operation=='install_service' else reference['options']['service'],
            'disconnect_all_clients':operation in {'service_stop','service_restart'}}
        reviewed=post('review',{'options':options,'credentials':credentials});value=wait(post('start',admitted(reviewed)))
        assert value['state']=='native_process_returned' and value['remote_receipt']['result']['return_code']==0,value.get('error_message') or value.get('error_type')
        return value
    lock=None
    try:
        for peer in owned['peers']:
            connection=mysql.connector.connect(host=peer['host'],port=3306,user='root',password='true',use_pure=not use_c,autocommit=True)
            cursor=connection.cursor();cursor.execute('SELECT @@server_uuid,@@read_only');uuid,readonly=cursor.fetchone()
            assert uuid==peer['server_uuid']
            if not readonly:lock=connection;break
            connection.close()
        assert lock is not None
        legacy=None
        if legacy_helper is not None:
            legacy=Path(legacy_helper).read_text();assert 'SESSION_CLIENTS' not in legacy
            result['previous_reader_sha256']=hashlib.sha256(legacy.encode()).hexdigest()
        for fault in ('dispatcher','dispatcher-and-guardian'):
            options=deepcopy(selected);options['directory']='/opt/sr-router-original-'+secrets.token_hex(8)
            options['extra_arguments']=['--name=sr-original-'+secrets.token_hex(6),'--conf-skip-x-protocol']
            original_sources=native.sources();old_sources={**original_sources,**({'tool_reconcile':legacy} if legacy is not None else {})}
            held=None;locked=False
            try:
                with patch.object(native,'sources',lambda:old_sources):
                    reviewed=post('review',{'options':options,'credentials':credentials})
                    assert reviewed['source_connection_class']==('CharsetCMySQLConnection' if use_c else 'CharsetMySQLConnection')
                    cursor=lock.cursor();cursor.execute('LOCK TABLES mysql_innodb_cluster_metadata.routers WRITE');locked=True
                    active=post('start',admitted(reviewed));directory=options['workspace']+'/'+active['job_id']
                    held=remote('''import json,os,signal,time,psutil,hashlib
from pathlib import Path
directory=Path(DIRECTORY)
for attempt in range(1000):
 try:
  value=json.loads((directory/'result.json').read_text());root=directory/'.cdeadmin-tool-router-bootstrap'
  started=json.loads((root/'started.json').read_text());progress=json.loads((root/'progress.json').read_text())
  assert progress['nonce']==started['nonce'];observed=progress['observation'];pid=observed['pid'];process=psutil.Process(pid)
  assert process.create_time()==observed['process_create_time'] and os.getsid(pid)==started['guardian_pid']
  assert hashlib.sha256((Path('/proc')/str(pid)/'exe').read_bytes()).hexdigest()==value['observation']['program']['sha256']
  descriptor=os.pidfd_open(pid)
  try:signal.pidfd_send_signal(descriptor,signal.SIGSTOP)
  finally:os.close(descriptor)
  print(json.dumps({'pid':pid,'create_time':process.create_time(),'uid':process.uids().effective,
   'guardian_pid':started['guardian_pid'],'guardian_ticks':(Path('/proc')/str(started['guardian_pid'])/'stat').read_text().rpartition(')')[2].split()[19],
   'dispatcher':value['dispatcher_identity'],'sdk_sha256':value['sdk_sha256']}));break
 except FileNotFoundError:time.sleep(.01)
else:raise TimeoutError('Original owned Router did not reach its native metadata wait')
'''.replace('DIRECTORY',repr(directory)))
                    result['faults'].append({'fault':fault,'original_process':held})
                    cursor.execute('UNLOCK TABLES');locked=False
                    kill=[held['dispatcher']]
                    if fault=='dispatcher-and-guardian':kill.append({'pid':held['guardian_pid'],'start_ticks':held['guardian_ticks']})
                    remote('''import json,os,signal
from pathlib import Path
for value in VALUES:
 descriptor=os.pidfd_open(value['pid'])
 try:
  assert (Path('/proc')/str(value['pid'])/'stat').read_text().rpartition(')')[2].split()[19]==value['start_ticks']
  signal.pidfd_send_signal(descriptor,signal.SIGKILL)
 finally:os.close(descriptor)
print(json.dumps({'original_observers_ended':True}))
'''.replace('VALUES',repr(kill)))
                    unknown=wait(active)
                assert unknown['state']=='unknown' and not unknown.get('ssh_reply_observed')
                observed=post('reconcile',{'job_id':unknown['job_id'],'credentials':credentials})
                receipt=observed['reconciliation']['remote_receipt'];facts=receipt['utility_observation']
                assert facts.get('cleanup_confirmed') is not True
                if legacy is not None:assert facts['reader_scope']=='current_reader_over_unchanged_original_request'
                post('acknowledge',{'job_id':unknown['job_id'],'credentials':credentials},refused=True)
                if fault=='dispatcher':
                    remote('''import os,signal,json,psutil
process=psutil.Process(PID);assert process.create_time()==BIRTH
descriptor=os.pidfd_open(process.pid)
try:signal.pidfd_send_signal(descriptor,signal.SIGCONT)
finally:os.close(descriptor)
print(json.dumps({'original_native_resumed':True}))
'''.replace('PID',str(held['pid'])).replace('BIRTH',repr(held['create_time'])))
                else:
                    assert any(value['pid']==held['pid'] for value in facts['independent_reconciliation']['original_session_live_processes'])
                    cancelled=post('cancel_original',{'job_id':unknown['job_id'],'credentials':credentials})
                    facts=cancelled['reconciliation']['remote_receipt']['utility_observation']
                    assert facts['independent_reconciliation']['original_native_cancellation_requested']
                deadline=time.monotonic()+30
                while True:
                    ended=post('reconcile',{'job_id':unknown['job_id'],'credentials':credentials})
                    receipt=ended['reconciliation']['remote_receipt'];facts=receipt['utility_observation']
                    if facts.get('cleanup_confirmed') is True:break
                    if time.monotonic()>deadline:raise TimeoutError('Original native Router cleanup deadline')
                    time.sleep(.1)
                assert ended['state']=='unknown' and not ended.get('ssh_reply_observed') and receipt['state']=='native_dispatch' and 'result' not in receipt
                assert facts['credential_file_cleanup_confirmed'] and facts['input_file_cleanup_confirmed']
                acknowledged=post('acknowledge',{'job_id':unknown['job_id'],'credentials':credentials})
                assert acknowledged['state']=='unknown' and acknowledged['reconciliation']['remote_receipt']['deployment_claim_released']
                if fault=='dispatcher':
                    assert facts['complete'] and facts['return_code']==0 and receipt['current_deployment_observation']['observed']
                    installed=invoke('install_service',acknowledged);started=invoke('service_start',installed);invoke('service_stop',started)
                    result['unknown_completed_bootstrap_job']=unknown['job_id']
                    checks.append('actual-SSH-dispatcher-loss-independent-native-success-files-and-reviewed-service-install-start-stop-with-original-unknown-unchanged')
                else:
                    assert facts['complete'] is False and facts['native_outcome_inferred'] is False and not receipt['current_deployment_observation']['observed']
                    checks.append('actual-dispatcher-and-guardian-loss-live-writer-ack-refusal-exact-original-PIDFD-cancel-input-cleanup-and-separate-claim-acknowledgement')
                (output/('original-'+fault+'.json')).write_text(json.dumps(acknowledged,indent=2)+'\n')
            finally:
                if locked:lock.cursor().execute('UNLOCK TABLES')
                if held is not None:
                    # Owned process identity only, including on qualification failure.
                    remote('''import json,psutil
try:
 process=psutil.Process(PID)
 if process.create_time()==BIRTH:process.kill()
except psutil.NoSuchProcess:pass
print(json.dumps({'owned_native_cleanup':True}))
'''.replace('PID',str(held['pid'])).replace('BIRTH',repr(held['create_time'])))
        result['complete']=True
    finally:
        if lock is not None:lock.close()
        control.close();(output/'original-recovery-summary.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

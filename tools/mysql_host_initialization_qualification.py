"""Initialize actual native MySQL datadirs through an unverified registration."""
import base64
from copy import deepcopy
import json
from pathlib import Path
import re
import time
from unittest.mock import patch


def qualify(http,admitted,remote,output,selected,credential,url):
    from pgadmin.cdeadmin.workspace import mysql_host_service
    proof={'complete':False,'history_testing':'not run','checks':[],'initializations':[]}
    def call(action,request,**kwargs):return http(action,request,target=url,**kwargs)
    def review(options):return call('review',{'options':options,'credentials':credential})
    def wait(value):
        deadline=time.monotonic()+120
        while value['state'] in {'dispatching','active','cancel_requested'}:
            if time.monotonic()>deadline:raise TimeoutError('Owned initializer did not finish')
            time.sleep(.05);value=call('status',{'job_id':value['job_id']})
        return value
    def options(label,secure):
        return {**deepcopy(selected),'operation':'initialize_data','configuration_file':None,'timeout_seconds':90,
            'initialization':{'datadir':'/tmp/sr-initialization-'+label,'user':'mysql','secure':secure}}
    def hold(value):
        directory=selected['workspace']+'/'+value['job_id']
        script='''import json,os,signal,time
from pathlib import Path
directory=Path(DIRECTORY)
for attempt in range(400):
 try:
  process=json.loads((directory/'initializer-process.json').read_text());marker=json.loads((directory/'initializer-started.json').read_text())
  pid=process['pid'];ticks=(Path('/proc')/str(pid)/'stat').read_text().rpartition(')')[2].split()[19]
  if ticks!=process['start_ticks']:raise AssertionError('Owned initializer PID identity changed')
  os.kill(pid,signal.SIGSTOP);print(json.dumps({'process':process,'guardian':marker}));break
 except FileNotFoundError:time.sleep(.01)
else:raise TimeoutError('Owned initializer did not become observable')
'''.replace('DIRECTORY',repr(directory))
        return json.loads(remote(script).stdout)
    # The route cannot resolve and has never passed endpoint verification.
    # Fail the gate if any initialization action attempts a SQL binding.
    with patch.object(mysql_host_service,'source',side_effect=AssertionError('Initialization must not request SQL authority')):
        stale_options=options('stale',False);stale=review(stale_options)
        assert stale['source_identity_scope']=='authenticated_ssh_host_before_native_initialization'
        assert 'server_uuid' not in stale['remote_observation']['host']
        remote("from pathlib import Path;p=Path('/tmp/sr-initialization-stale');p.mkdir();(p/'existing-data').write_bytes(b'preserved')")
        call('start',admitted(stale),refused=True);call('cancel',{'job_id':stale['job_id']})
        assert remote("from pathlib import Path;assert Path('/tmp/sr-initialization-stale/existing-data').read_bytes()==b'preserved'").returncode==0
        proof['checks'].append('unverified-registration-authenticated-SSH-no-SQL-identity-and-stale-nonempty-directory-refusal')
        for secure in (False,True):
            chosen=options('secure' if secure else 'insecure',secure)
            planned=review(chosen)
            value=wait(call('start',admitted(planned)))
            (Path(output)/('initialization-'+('secure' if secure else 'insecure')+'.json')).write_text(json.dumps(value,indent=2)+'\n')
            assert value['state']=='native_process_returned',value['state']
            receipt=value['remote_receipt'];result=receipt['initialization_result']
            assert result['native_initialization_returned'],receipt.get('error_type')
            assert receipt['result']['return_code']==0 and result['process_termination_confirmed']
            assert result['secure']==secure and not result['sql_readiness_observed'] and not result['automatic_retry']
            assert call('start',admitted(value,{}))['remote_receipt']==receipt
            observed=call('reconcile',{'job_id':value['job_id'],'credentials':credential})
            assert observed['reconciliation']['remote_receipt']['initialization_reconciliation']['process_termination_confirmed']
            call('review',{'options':chosen,'credentials':credential},refused=True)
            stderr=base64.b64decode(receipt['result']['outputs']['stderr']['base64']).decode('utf8')
            match=re.search(r'A temporary password is generated for root@localhost: (\S+)',stderr)
            assert bool(match)==secure
            password=match.group(1) if match else ''
            # Independent native acceptance starts/stops this disposable target;
            # the product receipt intentionally does not infer SQL readiness.
            script='''import json,subprocess,time,os
from pathlib import Path
target=Path(TARGET);socket=str(target)+'.sock';pid=str(target)+'.pid';log=str(target)+'.log'
arguments=['/usr/sbin/mysqld','--no-defaults','--datadir='+str(target),'--user=mysql','--socket='+socket,'--pid-file='+pid,'--log-error='+log,'--mysqlx=OFF','--skip-networking','--skip-log-bin','--innodb-buffer-pool-size=64M','--daemonize']
subprocess.run(arguments,check=True,capture_output=True)
client=Path(str(target)+'.client.cnf');client.write_text('[client]\\nuser=root\\nprotocol=SOCKET\\nsocket='+socket+'\\npassword='+json.dumps(PASSWORD)+'\\n');client.chmod(0o600)
command=['mysql','--defaults-file='+str(client),'--connect-expired-password','--batch','--skip-column-names']
try:
 for attempt in range(200):
  result=subprocess.run(command+['--execute','SELECT 1'],capture_output=True,text=True)
  if result.returncode==0 or 'expired' in result.stderr:break
  time.sleep(.05)
 if PASSWORD:
  subprocess.run(command+['--execute',"ALTER USER CURRENT_USER() IDENTIFIED BY 'Owned-initialization-acceptance-9!'"],check=True,capture_output=True)
  client.write_text('[client]\\nuser=root\\nprotocol=SOCKET\\nsocket='+socket+'\\npassword=Owned-initialization-acceptance-9!\\n')
 result=subprocess.run(command+['--execute','SELECT @@server_uuid,(SELECT COUNT(*) FROM mysql.user)'],check=True,capture_output=True,text=True)
 print(json.dumps({'server_uuid':result.stdout.strip().split('\\t')[0],'native_system_accounts':int(result.stdout.strip().split('\\t')[1]),'sql_acceptance':True}))
finally:
 subprocess.run(['mysqladmin','--defaults-file='+str(client),'shutdown'],check=True,capture_output=True)
 client.unlink()
'''.replace('TARGET',repr(chosen['initialization']['datadir'])).replace('PASSWORD',repr(password))
            accepted=json.loads(remote(script).stdout)
            assert accepted['server_uuid']==result['native_identity']['server_uuid'] and accepted['native_system_accounts']>=4
            proof['initializations'].append({'secure':secure,'native_identity':result['native_identity'],'independent_acceptance':accepted})
        proof['checks'].append('actual-secure-and-insecure-native-initialization-new-UUID-private-temporary-password-independent-start-query-stop-and-no-replay')
        cancelled=call('start',admitted(review(options('cancelled',False))))
        held=hold(cancelled)
        call('cancel_initialization',{'job_id':cancelled['job_id'],'credentials':credential})
        cancelled=wait(cancelled)
        assert cancelled['state']=='native_process_returned'
        assert cancelled['remote_receipt']['result']['cancelled'] and cancelled['remote_receipt']['result']['return_code']!=0
        assert not cancelled['remote_receipt']['initialization_result']['native_initialization_returned']
        proof['checks'].append('actual-native-initializer-cancellation-survives-stopped-child-and-preserves-unsuccessful-native-result')
        original=mysql_host_service.native.Transport.request
        def early_timeout(self,request,timeout=90):
            return original(self,request,timeout=1 if request['action']=='initialize_data' else timeout)
        with patch.object(mysql_host_service.native.Transport,'request',early_timeout):
            lost=call('start',admitted(review(options('lost-guardian',False))))
            held=hold(lost)
            lost=wait(lost)
        assert lost['state']=='unknown' and not lost.get('ssh_reply_observed')
        marker=held['guardian']
        remote("from pathlib import Path;import os,signal;pid="+str(marker['guardian_pid'])+";assert (Path('/proc')/str(pid)/'stat').read_text().rpartition(')')[2].split()[19]=="+repr(marker['guardian_start_ticks'])+";os.kill(pid,signal.SIGKILL)")
        time.sleep(.1)
        observed=call('reconcile',{'job_id':lost['job_id'],'credentials':credential})
        facts=observed['reconciliation']['remote_receipt']['initialization_reconciliation']
        assert not facts['process_termination_confirmed'] and held['process']['pid'] in facts['original_session_live_processes']
        call('acknowledge_initialization',{'job_id':lost['job_id'],'credentials':credential},refused=True)
        cancelled=call('cancel_initialization',{'job_id':lost['job_id'],'credentials':credential})
        assert cancelled['reconciliation']['remote_receipt']['initialization_reconciliation']['original_native_cancellation_requested']
        deadline=time.monotonic()+10
        while True:
            observed=call('reconcile',{'job_id':lost['job_id'],'credentials':credential})
            if observed['reconciliation']['remote_receipt']['initialization_reconciliation']['process_termination_confirmed']:break
            if time.monotonic()>deadline:raise TimeoutError('Original owned writer did not end')
            time.sleep(.05)
        acknowledged=call('acknowledge_initialization',{'job_id':lost['job_id'],'credentials':credential})
        later=acknowledged['reconciliation']['remote_receipt']
        assert later['initialization_reconciliation']['target_claim_released'] and later['state']=='native_dispatch'
        assert acknowledged['state']=='unknown' and not later.get('result') and not later.get('initialization_result')
        proof['checks'].append('lost-SSH-and-guardian-preserve-unknown-outcome-live-writer-fence-exact-PIDFD-cancellation-and-separate-ended-writer-acknowledgement')
    proof['complete']=True
    (Path(output)/'initialization.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof['checks']

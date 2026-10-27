"""Kill the actual original SSH dispatcher while native systemd stop waits."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import time


def qualify(post,selected,credentials,secret,owned,output,sql):
    output=Path(output);container=owned['container'];checks=[]
    assert container.startswith('sr-upgrade245-')
    def remote(source,*arguments):
        result=subprocess.run(['docker','exec',container,'python3','-c',source,*map(str,arguments)],capture_output=True,text=True)
        assert result.returncode==0,result.stderr
        return json.loads(result.stdout) if result.stdout.strip() else None
    delay='/etc/systemd/system/'+selected['service']['name']+'.d/10-owned-stop-delay.conf'
    remote('from pathlib import Path;import sys;p=Path(sys.argv[1]);p.parent.mkdir(exist_ok=True);p.open("x").write(sys.argv[2])',delay,'[Service]\nExecStop=/usr/bin/sleep 15\n')
    subprocess.run(['docker','exec',container,'systemctl','daemon-reload'],check=True,capture_output=True)
    try:
        reviewed=post('review',{'options':selected,'credentials':credentials,'upgrade_check_secret':secret})
        request={**{key:reviewed[key] for key in ('job_id','review_digest')},'confirmed':True,'credentials':credentials,'upgrade_check_secret':secret}
        current=post('start',request);root=selected['workspace']+'/'+reviewed['job_id']
        manager=reviewed['remote_observation']['service']['manager_programs']['systemctl']
        source='''import hashlib,json,os,signal,sys
from pathlib import Path
r=Path(sys.argv[1]);phase=r/'upgrade-phase.json';started=r/'upgrade-dispatcher.json'
if not phase.exists() or not started.exists():print('{}');raise SystemExit(0)
p=json.loads(phase.read_text());s=json.loads(started.read_text())
if p.get('stage')!='original_service_stop_admitted':print('{}');raise SystemExit(0)
assert s['job_id']==sys.argv[2] and s['input_digest']==sys.argv[3]
assert s['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
pid=s['pid'];fields=(Path('/proc')/str(pid)/'stat').read_text().rpartition(')')[2].split();assert fields[19]==s['start_ticks']
for child in (Path('/proc')/str(pid)/'task'/str(pid)/'children').read_text().split():
 d=Path('/proc')/child
 try:command=(d/'cmdline').read_bytes().decode().split('\\0')[:-1]
 except FileNotFoundError:continue
 if command!=[sys.argv[4],'--no-ask-password','--no-pager','--job-mode=fail','stop','--',sys.argv[6]]:continue
 assert hashlib.sha256((d/'exe').read_bytes()).hexdigest()==sys.argv[5]
 stat=(d/'stat').read_text().rpartition(')')[2].split();assert int(stat[1])==pid
 os.kill(int(child),signal.SIGSTOP);os.kill(pid,signal.SIGKILL)
 print(json.dumps({'dispatcher':s,'native_client_pid':int(child),'native_client_start_ticks':stat[19]}));break
else:print('{}')
'''
        deadline=time.monotonic()+30;original=None
        while time.monotonic()<deadline:
            original=remote(source,root,reviewed['job_id'],reviewed['review_digest'],manager['path'],manager['sha256'],selected['service']['name'])
            if original:break
            time.sleep(.05)
        assert original,'Original native stop client was not positively observed'
        (output/'killed-original-upgrade-dispatcher.json').write_text(json.dumps(original,indent=2)+'\n')
        deadline=time.monotonic()+15
        while current['state'] in {'dispatching','active','cancel_requested'}:
            if time.monotonic()>deadline:raise TimeoutError('Killed original upgrade dispatcher did not return unknown')
            time.sleep(.05);current=post('status',{'job_id':reviewed['job_id']})
        assert current['state']=='unknown' and not current.get('ssh_reply_observed')
        process=remote('''import json,sys
from pathlib import Path
p=Path('/proc')/sys.argv[1]/'stat'
try:f=p.read_text().rpartition(')')[2].split();ended=f[19]!=sys.argv[2] or f[0] in {'Z','X'}
except FileNotFoundError:ended=True
print(json.dumps({'ended':ended}))''',original['native_client_pid'],original['native_client_start_ticks'])
        assert process['ended'],'Kernel guardian-death policy did not end the original stopped native manager client'
        before=post('reconcile',{'job_id':reviewed['job_id'],'credentials':credentials})
        later=before['reconciliation']['remote_receipt']['upgrade_reconciliation']
        assert later['original_dispatcher_end_confirmed']
        if later.get('native_service',{}).get('unit',{}).get('ActiveState')=='deactivating':
            post('acknowledge_upgrade',{'job_id':reviewed['job_id'],'credentials':credentials},refused=True)
            checks.append('actual-original-dispatcher-and-stopped-native-client-loss-keeps-pending-native-manager-stop-protected')
        else:raise AssertionError('The independently delayed original stop must still be pending')
        deadline=time.monotonic()+30
        while True:
            observed=post('reconcile',{'job_id':reviewed['job_id'],'credentials':credentials})
            later=observed['reconciliation']['remote_receipt']['upgrade_reconciliation']
            if later.get('observed') and later['native_service']['unit']['ActiveState']=='inactive':break
            if time.monotonic()>deadline:raise TimeoutError('Original native stop did not independently finish')
            time.sleep(.1)
        assert later['original_native_process_termination_confirmed'] and later['native_upgrade_write_not_dispatched']
        acknowledged=post('acknowledge_upgrade',{'job_id':reviewed['job_id'],'credentials':credentials})
        assert acknowledged['state']=='unknown' and not acknowledged.get('ssh_reply_observed')
        assert acknowledged['reconciliation']['remote_receipt']['upgrade_reconciliation']['data_directory_claim_released']
        assert post('start',request)['state']=='unknown'
        (output/'interrupted-upgrade-acknowledged.json').write_text(json.dumps(acknowledged,indent=2)+'\n')
        restart=deepcopy(selected);restart.pop('upgrade');restart.update(operation='service_start',binding_job_id=reviewed['job_id'],disconnect_all_clients=False)
        review=post('review',{'options':restart,'credentials':credentials})
        active=post('start',{**{key:review[key] for key in ('job_id','review_digest')},'confirmed':True,'credentials':credentials})
        deadline=time.monotonic()+60
        while active['state'] in {'active','dispatching','cancel_requested'}:
            if time.monotonic()>deadline:raise TimeoutError('Separately reviewed original native service restart deadline')
            time.sleep(.1);active=post('status',{'job_id':active['job_id']})
        assert active['state']=='native_process_returned' and active['remote_receipt']['result']['return_code']==0
        import mysql.connector
        deadline=time.monotonic()+30
        while True:
            try:
                assert sql('SELECT VERSION() AS version')[0]['version'].split('-')[0]=='8.4.8'
                break
            except mysql.connector.Error as error:
                if getattr(error,'errno',None) not in {2002,2003,2006,2013,2055} or time.monotonic()>deadline:raise
            time.sleep(.1)
        checks.append('independent-ended-original-upgrade-acknowledgement-and-separately-reviewed-original-8.4-service-start-preserve-unknown-without-replay')
        return checks
    finally:
        remote('from pathlib import Path;import sys;Path(sys.argv[1]).unlink(missing_ok=True)',delay)
        subprocess.run(['docker','exec',container,'systemctl','daemon-reload'],check=True,capture_output=True)

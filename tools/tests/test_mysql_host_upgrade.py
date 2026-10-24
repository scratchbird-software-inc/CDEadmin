"""Upgrade validation and original-claim ownership boundaries."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_host_upgrade as native
from pgadmin.cdeadmin.providers.mysql_family import mysql_host_worker as host


def test_private_native_input_is_drained_without_appearing_in_process_receipts(tmp_path):
    secret=b'owned-upgrade-private-input-\x00-\xff'
    result=host.process(Path(sys.executable),['-c','import sys;assert sys.stdin.buffer.read()==bytes.fromhex(sys.argv[1])',secret.hex()],
        tmp_path,10,input_bytes=secret)
    assert result['return_code']==0 and result['private_input_closed'] and not result['private_input_error_type']
    assert secret.hex() not in json.dumps(result) and 'owned-upgrade-private-input' not in json.dumps(result)


@pytest.mark.skipif(not sys.platform.startswith('linux'),reason='Linux native manager-client parent-death policy')
def test_original_host_dispatcher_death_ends_its_guarded_native_client(tmp_path):
    import psutil
    web=Path(__file__).resolve().parents[2]/'web'
    code='''import sys,types
from pathlib import Path
p=types.ModuleType('pgadmin');p.__path__=[sys.argv[2]+'/pgadmin'];sys.modules['pgadmin']=p
sys.path.insert(0,sys.argv[2])
from pgadmin.cdeadmin.providers.mysql_family import mysql_host_worker as host
host.process(Path(sys.executable),['-c',"import os,time;from pathlib import Path;Path('owned-pid').write_text(str(os.getpid()));time.sleep(45)"],Path(sys.argv[1]),60,guard_parent_death=True)
'''
    owner=subprocess.Popen([sys.executable,'-c',code,str(tmp_path),str(web)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    native=None
    try:
        deadline=time.monotonic()+10;path=tmp_path/'owned-pid'
        while not path.exists():
            if owner.poll() is not None or time.monotonic()>deadline:raise AssertionError('Original native client did not start')
            time.sleep(.03)
        native=psutil.Process(int(path.read_text()));assert native.ppid()==owner.pid
        owner.kill();owner.wait(timeout=5)
        while native.is_running() and native.status()!=psutil.STATUS_ZOMBIE:
            if time.monotonic()>deadline:raise AssertionError('Guarded native client survived its original dispatcher')
            time.sleep(.03)
    finally:
        if owner.poll() is None:owner.kill();owner.wait(timeout=5)
        if native is not None:
            try:
                if native.is_running() and native.status()!=psutil.STATUS_ZOMBIE:native.kill()
            except psutil.NoSuchProcess:pass


def test_candidate_configuration_refusal_never_stops_the_original_service_or_claims_its_data(tmp_path):
    directory=tmp_path/'job';directory.mkdir();data=tmp_path/'data';data.mkdir()
    calls=[]
    def refused(executable,arguments,*args,**kwargs):
        calls.append((str(executable),arguments))
        return {'return_code':1,'timed_out':False,'native_process_termination_observed':True}
    plan={'candidate':{'program':{'path':'/candidate/mysqld'},'configuration':{'context':{}}},
        'native_arguments':['/candidate/mysqld','--upgrade=AUTO'],'preflight':{'report':{'errorCount':0}}}
    observed={'upgrade_plan':plan,'host':{'datadir':str(data)}}
    value=native.execute({'job_id':'owned','input_digest':'owned-review'},observed,directory,60,{**host.__dict__,'process':refused})
    assert value['configuration_validation']['return_code']==1 and value['dispatcher_steps_ended']
    assert len(calls)==1 and '--validate-config' in calls[0][1]
    assert not native.claim_path(data).exists() and not value['service_start_requested']


@pytest.mark.parametrize('changed',['job','digest'])
def test_original_native_claim_cannot_be_adopted_by_another_host_request(tmp_path,changed):
    data=tmp_path/'data';data.mkdir()
    request={'binding':{'datadir':str(data)},'job_id':'original-job','input_digest':'original-input'}
    value={'job_id':'original-job','input_digest':'original-input'}
    value['job_id' if changed=='job' else 'input_digest']='foreign'
    path=native.claim_path(data);path.write_text(json.dumps(value))
    with pytest.raises(host.Refused,match='original native upgrade'):native.admitted(request,host.__dict__)
    assert json.loads(path.read_text())==value


@pytest.mark.parametrize('ended,version',[(False,'9.7.0'),(True,'8.4.8'),(True,'9.7.0')])
def test_target_observation_never_releases_a_claim_while_original_dispatch_steps_or_native_upgrade_are_unconfirmed(tmp_path,monkeypatch,ended,version):
    directory=tmp_path/'job';directory.mkdir();(directory/'upgrade.lock').touch()
    data=tmp_path/'data';data.mkdir()
    reference={'job_id':'original-job','input_digest':'original-input','binding':{'datadir':str(data)}}
    path=native.claim_path(data);path.write_text(json.dumps({key:reference[key] for key in ('job_id','input_digest')}))
    dropin=tmp_path/'owned.conf';dropin.write_bytes(b'candidate')
    import hashlib
    plan={'candidate':{'program':{'path':'/candidate/mysqld'}},'native_arguments':['/candidate/mysqld'],
        'dropin_path':str(dropin),'dropin_sha256':hashlib.sha256(b'candidate').hexdigest(),
        'original_native_process':{'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()}}
    phase={'stage':'native_manager_requests_returned','dispatcher_steps_ended':ended}
    (directory/'upgrade-phase.json').write_text(json.dumps(phase))
    value={'state':'native_dispatch','upgrade_request':reference,'observation':{'upgrade_plan':plan,'host':{'datadir':str(data)},
        'service':{'definition_files':{},'command_sha256':{}}}}
    monkeypatch.setattr(native,'process_ended',lambda _original:True)
    monkeypatch.setattr(native,'history',lambda *_args:{'file_format':'1','upgrade_history':[{'version':version}]})
    adapted={**host.__dict__,'native_services':SimpleNamespace(inspect=lambda *_args:{'native_process':{'pid':123},'unit':{'ActiveState':'active'}})}
    if not ended:
        with pytest.raises(host.Refused,match='has not independently ended'):native.observe(directory,value,adapted,acknowledge=True)
        assert path.exists()
    elif version!='9.7.0':
        with pytest.raises(host.Refused,match='native upgrade completion is unconfirmed'):native.observe(directory,value,adapted,acknowledge=True)
        assert path.exists()
    else:
        result=native.observe(directory,value,adapted,acknowledge=True)
        assert result['upgrade_reconciliation']['data_directory_claim_released'] and not path.exists()
        assert value['state']==result['state']=='native_dispatch' and 'result' not in result

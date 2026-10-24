"""Native process supervision survives an abruptly lost application owner."""
import json
import base64
import os
from pathlib import Path
import subprocess
import sys
import time
import hashlib
import socket

import pytest

from pgadmin.cdeadmin.sdk import durable_tool
from pgadmin.cdeadmin.sdk.tooling import ProviderToolGrant, ProviderToolRunner


@pytest.mark.parametrize('publishes_receipt',[True,False])
def test_guardian_exit_rechecks_a_receipt_published_between_existence_check_and_poll(tmp_path,monkeypatch,publishes_receipt):
    class Guardian:
        def poll(self):
            root=durable_tool.directory(tmp_path,'owned-race')
            intent=json.loads((root/'request.json').read_text())
            if publishes_receipt:
                durable_tool.write(root/'result.json',{'nonce':intent['nonce'],
                    'request_sha256':durable_tool.sha(root/'request.json'),'credential_file_cleanup_confirmed':True,
                    'observation':{'cleanup_confirmed':True,'return_code':0,
                        'stdout':base64.b64encode(b'native returned\n').decode(),
                        'stderr':base64.b64encode(b'').decode()}})
            return 0
        def wait(self,timeout=None):return 0
    monkeypatch.setattr(durable_tool.subprocess,'Popen',lambda *_args,**_kwargs:Guardian())
    def run():
        return durable_tool.run([sys.executable,'-c','pass'],workspace=tmp_path,environment={},
            timeout=10,capture_limit=1024,name='owned-race')
    if publishes_receipt:
        result=run()
        assert result['return_code']==0 and result['stdout']==b'native returned\n' and result['cleanup_confirmed']
    else:
        with pytest.raises(RuntimeError,match='without a final receipt'):run()


def wait_until(callback, seconds=15):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        value=callback()
        if value:return value
        time.sleep(.05)
    raise TimeoutError('Owned durable utility fixture deadline')


@pytest.mark.skipif(not sys.platform.startswith('linux'),reason='Linux original session and PIDFD qualification')
def test_non_daemon_router_session_survives_guardian_loss_and_cancels_only_its_original_client(tmp_path):
    import psutil,pwd
    web=Path(__file__).resolve().parents[2]/'web';root=durable_tool.directory(tmp_path,'router-bootstrap')
    secret=tmp_path/'private-input';secret.write_bytes(b'owned-router-input\n')
    code='''import json,os,sys,types
from pathlib import Path
package=types.ModuleType('pgadmin');package.__path__=[sys.argv[2]+'/pgadmin'];sys.modules['pgadmin']=package
sys.path.insert(0,sys.argv[2])
from pgadmin.cdeadmin.sdk import durable_tool
root=Path(sys.argv[1])
def progress(value):
 if value.get('durable_tool'):(root/'reference.json').write_text(json.dumps(value['durable_tool']))
durable_tool.run([sys.executable,'-c',"import os,time,json;from pathlib import Path;(Path.cwd()/'native-started.json').write_text(json.dumps({'pid':os.getpid()}));time.sleep(45)",
 '--bootstrap=mysql://owned-fixture','--user='+sys.argv[3]],workspace=root,environment=dict(os.environ),timeout=60,capture_limit=1024,
 name='router-bootstrap',input_path=root/'private-input',credential_file=root/'private-input',progress=progress,guard_parent_death=False)
'''
    owner=subprocess.Popen([sys.executable,'-c',code,str(tmp_path),str(web),pwd.getpwuid(os.geteuid()).pw_name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    native=guardian=None
    try:
        wait_until(lambda:(tmp_path/'native-started.json').exists() and (root/'progress.json').exists())
        native=psutil.Process(json.loads((tmp_path/'native-started.json').read_text())['pid'])
        reference=json.loads((tmp_path/'reference.json').read_text());guardian=psutil.Process(json.loads((root/'started.json').read_text())['guardian_pid'])
        assert json.loads((root/'request.json').read_text())['kernel_policy'] is None
        guardian.kill();owner.wait(timeout=10)
        observed=durable_tool.observe(tmp_path,reference,durable_tool.sha(sys.executable))
        assert native.is_running() and not durable_tool.terminated(observed)
        assert observed['independent_reconciliation']['reason']=='original_native_session_still_present'
        cancelled=durable_tool.cancel(tmp_path,reference,durable_tool.sha(sys.executable))
        assert cancelled['independent_reconciliation']['original_native_cancellation_requested']
        wait_until(lambda:not native.is_running() or native.status()==psutil.STATUS_ZOMBIE)
        ended=durable_tool.observe(tmp_path,reference,durable_tool.sha(sys.executable))
        assert durable_tool.terminated(ended) and ended['credential_file_cleanup_confirmed'] and ended['input_file_cleanup_confirmed']
        assert ended['complete'] is False and ended['native_outcome_inferred'] is False
        assert not (root/'result.json').exists() and not secret.exists() and not (root/'stdin.bin').exists()
    finally:
        if owner.poll() is None:owner.kill();owner.wait(timeout=5)
        for process in (native,guardian):
            if process is not None:
                try:process.kill()
                except psutil.NoSuchProcess:pass


def test_durable_receipt_keeps_private_output_separate_and_scrubs_credentials(tmp_path):
    events=[]
    result=ProviderToolRunner({'python':sys.executable}).run(
        ProviderToolGrant('python',str(tmp_path),'127.0.0.1',3306,durable_name='owned-native',
            secret_environment_names=('OWNED_CREDENTIAL_FILE',)),
        ['-c','import os,pathlib;print(pathlib.Path(os.environ["OWNED_CREDENTIAL_FILE"]).read_text())'],
        secret_config=b'private-owned-canary',secret_argument=None,secret_environment_name='OWNED_CREDENTIAL_FILE',
        redact_values=('private-owned-canary',),progress=events.append)
    assert result['return_code']==0 and result['stdout']=='[redacted]\n'
    reference=next(event['durable_tool'] for event in events if 'durable_tool' in event)
    observed=durable_tool.observe(tmp_path,reference,result['executable_sha256'])
    assert observed['complete'] and observed['cleanup_confirmed'] and observed['credential_file_cleanup_confirmed']
    assert 'private-owned-canary' not in json.dumps(observed)
    assert not list(tmp_path.glob('.cdeadmin-tool-*.json'))
    with pytest.raises(FileExistsError):
        ProviderToolRunner({'python':sys.executable}).run(
            ProviderToolGrant('python',str(tmp_path),'127.0.0.1',3306,durable_name='owned-native'),['-c','raise RuntimeError("must never replay")'])


@pytest.mark.parametrize('guarded',[False,True])
@pytest.mark.parametrize('cancel',[False,True])
@pytest.mark.parametrize('with_input',[False,True])
@pytest.mark.parametrize('with_reservation',[False,True])
def test_lost_application_process_never_loses_guardian_outcome_or_replays(tmp_path,cancel,with_input,with_reservation,guarded):
    if with_reservation and os.name!='posix':pytest.skip('POSIX endpoint descriptor inheritance')
    web=Path(__file__).resolve().parents[2]/'web'
    fixture=tmp_path/'native_fixture.py'
    fixture.write_text('''import os,time
from pathlib import Path
root=Path.cwd()
if (root/'listener.json').exists():
 import json,socket
 expected=tuple(json.loads((root/'listener.json').read_text()))
 fd=json.loads((root/'.cdeadmin-tool-owned-native'/'request.json').read_text())['endpoint_reservation']['fd']
 with socket.socket(fileno=os.dup(fd)) as reserved:assert reserved.getsockname()==expected
with (root/'started').open('a') as stream:stream.write('one\\n')
assert Path(os.environ['OWNED_CREDENTIAL_FILE']).read_text()=='owned-private'
while not (root/'release').exists():time.sleep(.05)
if (root/'stdin.data').exists():
 import sys
 assert sys.stdin.buffer.read()==(root/'stdin.data').read_bytes()
print('native completed')
''')
    if with_input:(tmp_path/'stdin.data').write_bytes('native LF\nquote"slash\\雪'.encode()+b'\x00\xff')
    owner_code='''import json,sys,types
from pathlib import Path
package=types.ModuleType('pgadmin');package.__path__=[sys.argv[2]+'/pgadmin'];sys.modules['pgadmin']=package
sys.path.insert(0,sys.argv[2])
from pgadmin.cdeadmin.sdk.tooling import ProviderToolGrant,ProviderToolRunner
root=Path(sys.argv[1])
listener=None
if sys.argv[5]=='1':
 import socket
 listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen()
 (root/'listener.json').write_text(json.dumps(listener.getsockname()))
def progress(event):
 if 'durable_tool' in event:(root/'reference.json').write_text(json.dumps(event['durable_tool']))
ProviderToolRunner({'python':sys.executable}).run(ProviderToolGrant('python',str(root),'127.0.0.1',listener.getsockname()[1] if listener else 3306,timeout_seconds=12,durable_name='owned-native',guard_parent_death=sys.argv[6]=='1',secret_environment_names=('OWNED_CREDENTIAL_FILE',)),
 [sys.argv[3]],input_path=root/'stdin.data' if sys.argv[4]=='1' else None,
 secret_config=b'owned-private',secret_argument=None,secret_environment_name='OWNED_CREDENTIAL_FILE',progress=progress,reservation_socket=listener)
'''
    owner=subprocess.Popen([sys.executable,'-c',owner_code,str(tmp_path),str(web),str(fixture),'1' if with_input else '0','1' if with_reservation else '0','1' if guarded else '0'],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    reference=None
    try:
        wait_until(lambda:(tmp_path/'started').exists())
        reference=json.loads((tmp_path/'reference.json').read_text())
        owner.kill();owner.wait(timeout=5)
        if with_reservation:
            with socket.socket() as other:
                with pytest.raises(OSError):other.bind(tuple(json.loads((tmp_path/'listener.json').read_text())))
        expected=durable_tool.sha(sys.executable)
        assert not durable_tool.observe(tmp_path,reference,expected)['complete']
        if cancel:
            assert durable_tool.cancel(tmp_path,reference,expected)['cancellation_requested']
        else:(tmp_path/'release').write_text('release the owned native fixture')
        observed=wait_until(lambda:(value if (value:=durable_tool.observe(tmp_path,reference,expected))['complete'] else None))
        assert observed['cleanup_confirmed'] and observed['credential_file_cleanup_confirmed']
        assert observed['input_file_cleanup_confirmed'] and not (durable_tool.directory(tmp_path,'owned-native')/'stdin.bin').exists()
        assert (observed['return_code']==0) is (not cancel)
        assert (tmp_path/'started').read_text()=='one\n'
        assert not list(tmp_path.glob('.cdeadmin-tool-*.json'))
        if with_reservation:
            with socket.socket() as other:other.bind(tuple(json.loads((tmp_path/'listener.json').read_text())))
    finally:
        if owner.poll() is None:owner.kill();owner.wait(timeout=5)
        if reference:
            expected=durable_tool.sha(sys.executable)
            durable_tool.cancel(tmp_path,reference,expected)
            wait_until(lambda:durable_tool.observe(tmp_path,reference,expected)['complete'])


def test_durable_stdin_owns_exact_bytes_after_the_original_path_changes(tmp_path):
    source=tmp_path/'input.sql';data=('native LF\nquote"slash\\雪'.encode()+b'\x00\xff')*4096;source.write_bytes(data)
    events=[]
    def progress(value):
        events.append(value)
        if value.get('durable_tool'):source.write_bytes(b'changed after handoff')
    result=ProviderToolRunner({'python':sys.executable}).run(
        ProviderToolGrant('python',str(tmp_path),'127.0.0.1',3306,durable_name='owned-input'),
        ['-c','import hashlib,sys;print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())'],input_path=source,progress=progress)
    assert result['stdout'].strip()==hashlib.sha256(data).hexdigest()
    reference=next(value['durable_tool'] for value in events if value.get('durable_tool'))
    observed=durable_tool.observe(tmp_path,reference,result['executable_sha256'])
    assert observed['cleanup_confirmed'] and observed['input_file_cleanup_confirmed']
    assert not (durable_tool.directory(tmp_path,'owned-input')/'stdin.bin').exists()


def test_guardian_refuses_changed_stdin_before_native_dispatch(tmp_path):
    source=tmp_path/'input.sql';source.write_bytes(b'owned input');references=[]
    def progress(value):
        if value.get('durable_tool'):
            reference=value['durable_tool'];references.append(reference)
            (durable_tool.directory(tmp_path,reference['name'])/'stdin.bin').write_bytes(b'tampered input')
    with pytest.raises(RuntimeError,match='supervision failed'):
        ProviderToolRunner({'python':sys.executable}).run(
            ProviderToolGrant('python',str(tmp_path),'127.0.0.1',3306,durable_name='owned-input'),
            ['-c','from pathlib import Path;Path("must-not-run").write_text("unsafe")'],input_path=source,progress=progress)
    assert not (tmp_path/'must-not-run').exists()
    observed=durable_tool.observe(tmp_path,references[0],durable_tool.sha(sys.executable))
    assert observed['native_may_have_dispatched'] is False and observed['cleanup_confirmed']
    assert observed['input_file_cleanup_confirmed'] and observed['credential_file_cleanup_confirmed']


@pytest.mark.skipif(not sys.platform.startswith('linux'),reason='Linux native parent-death and kernel session qualification')
@pytest.mark.parametrize('fault',[None,'credential-link','input-changed','namespace'])
def test_original_guardian_loss_stops_its_native_client_and_retains_unknown_reply(tmp_path,monkeypatch,fault):
    import psutil
    web=Path(__file__).resolve().parents[2]/'web';root=durable_tool.directory(tmp_path,'owned-guardian-loss')
    original=b'private native input\x00\xff';(tmp_path/'input.sql').write_bytes(original)
    code='''import json,os,sys,types
from pathlib import Path
package=types.ModuleType('pgadmin');package.__path__=[sys.argv[2]+'/pgadmin'];sys.modules['pgadmin']=package
sys.path.insert(0,sys.argv[2])
from pgadmin.cdeadmin.sdk.tooling import ProviderToolGrant,ProviderToolRunner
root=Path(sys.argv[1])
def progress(value):
 if value.get('durable_tool'):(root/'reference.json').write_text(json.dumps(value['durable_tool']))
ProviderToolRunner({'python':sys.executable}).run(ProviderToolGrant('python',str(root),'127.0.0.1',3306,
 timeout_seconds=60,durable_name='owned-guardian-loss',guard_parent_death=True,secret_environment_names=('OWNED_CREDENTIAL_FILE',)),
 ['-c',"import os,time,json;from pathlib import Path;p=Path.cwd()/'native-started.json';p.write_text(json.dumps({'pid':os.getpid()}));assert Path(os.environ['OWNED_CREDENTIAL_FILE']).read_text()=='owned-private-secret';time.sleep(45)"],
 input_path=root/'input.sql',secret_config=b'owned-private-secret',secret_argument=None,secret_environment_name='OWNED_CREDENTIAL_FILE',progress=progress)
'''
    owner=subprocess.Popen([sys.executable,'-c',code,str(tmp_path),str(web)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    native=None;guardian=None;reference=None
    try:
        wait_until(lambda:(tmp_path/'native-started.json').exists())
        native=psutil.Process(json.loads((tmp_path/'native-started.json').read_text())['pid'])
        reference=json.loads((tmp_path/'reference.json').read_text());intent=json.loads((root/'request.json').read_text())
        guardian=psutil.Process(json.loads((root/'started.json').read_text())['guardian_pid'])
        assert native.ppid()==guardian.pid and intent['kernel_policy']=='linux-parent-death-kill-v1'
        credential=Path(intent['credential_file']);canary=tmp_path/'foreign-credential';canary.write_bytes(b'foreign must remain')
        guardian.kill();owner.wait(timeout=10)
        wait_until(lambda:not native.is_running() or native.status()==psutil.STATUS_ZOMBIE)
        if fault=='credential-link':credential.unlink(missing_ok=True);credential.symlink_to(canary)
        elif fault=='input-changed':(root/'stdin.bin').write_bytes(b'changed private input')
        elif fault=='namespace':
            previous=durable_tool.host
            monkeypatch.setattr(durable_tool,'host',lambda:{**previous(),'pid_namespace':'pid:[another]'})
        observed=durable_tool.observe(tmp_path,reference,durable_tool.sha(sys.executable))
        assert observed['complete'] is False and observed['native_outcome_inferred'] is False
        assert 'return_code' not in observed and not (root/'result.json').exists()
        assert 'owned-private-secret' not in json.dumps(observed) and canary.read_bytes()==b'foreign must remain'
        if fault=='namespace':
            assert not durable_tool.terminated(observed)
            assert observed['independent_reconciliation']['reason']=='original_process_namespace_unavailable'
        else:
            assert durable_tool.terminated(observed)
            assert observed['credential_file_cleanup_confirmed'] is (fault!='credential-link')
            assert observed['input_file_cleanup_confirmed'] is (fault!='input-changed')
            assert observed['independent_reconciliation']['guardian_lock_independently_free']
        with pytest.raises(FileExistsError):
            ProviderToolRunner({'python':sys.executable}).run(ProviderToolGrant('python',str(tmp_path),'127.0.0.1',3306,
                durable_name='owned-guardian-loss',guard_parent_death=True),['-c','raise RuntimeError("never replay")'])
    finally:
        if owner.poll() is None:owner.kill();owner.wait(timeout=5)
        for process in (native,guardian):
            if process is not None:
                try:
                    if process.is_running() and process.status()!=psutil.STATUS_ZOMBIE:process.kill()
                except psutil.NoSuchProcess:pass


@pytest.mark.skipif(not sys.platform.startswith('linux'),reason='Linux native guardian admission qualification')
@pytest.mark.parametrize('cancel',[False,True])
def test_observation_cannot_revoke_a_delayed_launch_but_explicit_cancellation_can(tmp_path,cancel):
    events=[];observations=[]
    def progress(value):
        events.append(value)
        if value.get('durable_tool'):
            operation=durable_tool.cancel if cancel else durable_tool.observe
            observations.append(operation(tmp_path,value['durable_tool'],durable_tool.sha(sys.executable)))
            if not cancel:assert not (durable_tool.directory(tmp_path,value['durable_tool']['name'])/'guardian.lock').exists()
    def run():
        return ProviderToolRunner({'python':sys.executable}).run(ProviderToolGrant('python',str(tmp_path),'127.0.0.1',3306,
            durable_name='owned-delayed-launch',guard_parent_death=True),
            ['-c','from pathlib import Path;Path("native-executed").write_text("once")'],progress=progress)
    if cancel:
        with pytest.raises(RuntimeError,match='without a final receipt'):run()
        assert not (tmp_path/'native-executed').exists() and durable_tool.terminated(observations[0])
        assert observations[0]['independent_reconciliation']['native_start_revoked']
    else:
        assert run()['return_code']==0 and (tmp_path/'native-executed').read_text()=='once'
        assert not durable_tool.terminated(observations[0])
        assert observations[0]['independent_reconciliation']['reason']=='original_guardian_admission_unconfirmed'


@pytest.mark.skipif(not sys.platform.startswith('linux'),reason='Linux original legacy-client kernel handle qualification')
@pytest.mark.parametrize('changed_birth',[False,True])
def test_legacy_managed_orphan_requires_its_original_live_identity_before_stop(tmp_path,changed_birth):
    import psutil
    web=Path(__file__).resolve().parents[2]/'web';root=durable_tool.directory(tmp_path,'mysql-instance-restore')
    code='''import json,sys,types
from pathlib import Path
package=types.ModuleType('pgadmin');package.__path__=[sys.argv[2]+'/pgadmin'];sys.modules['pgadmin']=package
sys.path.insert(0,sys.argv[2])
from pgadmin.cdeadmin.sdk.tooling import ProviderToolGrant,ProviderToolRunner
from pgadmin.cdeadmin.sdk import durable_tool
root=Path(sys.argv[1])
def progress(value):
 if value.get('durable_tool'):
  reference=value['durable_tool'];reference['host'].pop('linux_boot_id',None);reference['host'].pop('pid_namespace',None)
  directory=durable_tool.directory(root,reference['name']);intent=json.loads((directory/'request.json').read_text())
  intent['host']=reference['host'];intent.pop('kernel_policy',None);intent.pop('credential_file_identity',None)
  durable_tool.write(directory/'request.json',intent);reference['request_sha256']=durable_tool.sha(directory/'request.json')
  (root/'reference.json').write_text(json.dumps(reference))
ProviderToolRunner({'python':sys.executable}).run(ProviderToolGrant('python',str(root),'127.0.0.1',3306,
 timeout_seconds=60,durable_name='mysql-instance-restore',secret_environment_names=('OWNED_CREDENTIAL_FILE',)),
 ['-c',"import os,time,json;from pathlib import Path;assert Path(os.environ['OWNED_CREDENTIAL_FILE']).read_text()=='legacy-private';Path('native-started.json').write_text(json.dumps({'pid':os.getpid()}));time.sleep(45)"],
 secret_config=b'legacy-private',secret_argument=None,secret_environment_name='OWNED_CREDENTIAL_FILE',progress=progress)
'''
    owner=subprocess.Popen([sys.executable,'-c',code,str(tmp_path),str(web)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    native=guardian=None
    try:
        wait_until(lambda:(tmp_path/'native-started.json').exists() and (root/'progress.json').exists())
        native=psutil.Process(json.loads((tmp_path/'native-started.json').read_text())['pid'])
        reference=json.loads((tmp_path/'reference.json').read_text());intent=json.loads((root/'request.json').read_text())
        assert 'kernel_policy' not in intent and 'linux_boot_id' not in intent['host']
        guardian=psutil.Process(json.loads((root/'started.json').read_text())['guardian_pid'])
        guardian.kill();owner.wait(timeout=10)
        assert native.is_running() and native.status()!=psutil.STATUS_ZOMBIE
        if changed_birth:
            progress=json.loads((root/'progress.json').read_text());progress['observation']['process_create_time']+=1
            durable_tool.write(root/'progress.json',progress)
            observed=durable_tool.cancel(tmp_path,reference,durable_tool.sha(sys.executable))
            assert not durable_tool.terminated(observed) and native.status()!=psutil.STATUS_ZOMBIE
            assert observed['independent_reconciliation']['reason']=='original_legacy_native_identity_unavailable'
        else:
            observed=durable_tool.observe(tmp_path,reference,durable_tool.sha(sys.executable))
            assert observed['independent_reconciliation']['legacy_session_independently_anchored']
            durable_tool.cancel(tmp_path,reference,durable_tool.sha(sys.executable))
            observed=wait_until(lambda:(value if durable_tool.terminated(value:=durable_tool.observe(tmp_path,reference,durable_tool.sha(sys.executable))) else None))
            assert not observed['complete'] and 'return_code' not in observed and not observed['native_outcome_inferred']
            assert observed['credential_file_cleanup_confirmed'] and observed['input_file_cleanup_confirmed']
            assert not Path(intent['credential_file']).exists() and not (root/'result.json').exists()
            assert 'legacy-private' not in json.dumps(observed)
    finally:
        if owner.poll() is None:owner.kill();owner.wait(timeout=5)
        for process in (native,guardian):
            if process is not None:
                try:
                    if process.is_running() and process.status()!=psutil.STATUS_ZOMBIE:process.kill()
                except psutil.NoSuchProcess:pass

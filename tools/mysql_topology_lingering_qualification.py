"""Owned native client death while its server-side lock waiter still exists."""
import json
from pathlib import Path
import threading
import time
import uuid

import psutil

from pgadmin.cdeadmin.sdk import durable_tool
from pgadmin.cdeadmin.sdk.tooling import ProviderToolGrant
from pgadmin.cdeadmin.providers.mysql_family import mysql_topology_quiescence as native
from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_archives import rows


def qualify_privileges(client, connection, route, password, *, use_c):
    suffix=uuid.uuid4().hex[:8];role_name='sr_q_role`雪_'+suffix;user_name='sr_q_actor_'+suffix
    role="'"+role_name+"'@'%'";user="'"+user_name+"'@'%'";observer=None
    try:
        rows(connection,'CREATE ROLE '+role)
        rows(connection,'GRANT PROCESS ON *.* TO '+role)
        rows(connection,'CREATE USER '+user+' IDENTIFIED BY %s',(password,))
        rows(connection,'GRANT SELECT ON performance_schema.* TO '+user)
        rows(connection,'CREATE TABLE sr_topology.sr_q_privilege_probe(`x, PROCESS ON *.* TO y` INT)')
        rows(connection,'GRANT SELECT (`x, PROCESS ON *.* TO y`) ON sr_topology.sr_q_privilege_probe TO '+user)
        rows(connection,'GRANT '+role+' TO '+user)
        rows(connection,'SET DEFAULT ROLE '+role+' TO '+user)
        observer=client._connector(host=route['host'],port=route['port'],user=user_name,
            password=password,use_pure=not use_c,autocommit=True)
        def query(source,parameters=()):return [list(row.values()) for row in rows(observer,source,parameters)]
        profile=native.native_profile(query,observer._cdeadmin_observer_attribute)
        assert profile['identity']['active_role']!='NONE' and '雪' in profile['identity']['active_role']
        rows(observer,'SET ROLE NONE')
        try:native.native_profile(query,observer._cdeadmin_observer_attribute)
        except ValueError as error:assert 'process visibility' in str(error)
        else:raise AssertionError('Missing effective PROCESS privilege was not refused')
        return {'complete':True,'native_active_role':profile['identity']['active_role'],
            'checks':['native-quoted-Unicode-role-inherited-PROCESS-visibility',
                'native-denied-PROCESS-with-current-handshake-visible-is-unqualified',
                'native-quoted-column-grant-text-cannot-spoof-global-PROCESS-visibility']}
    finally:
        if observer is not None:client._discard_failed_session(observer)
        rows(connection,'DROP USER IF EXISTS '+user)
        rows(connection,'DROP ROLE IF EXISTS '+role)
        rows(connection,'DROP TABLE IF EXISTS sr_topology.sr_q_privilege_probe')


def qualify(client, connection, route, password, output):
    output = Path(output); output.mkdir(mode=0o700, exist_ok=False)
    nonce = str(uuid.uuid4()); lock = 'sr:topology-linger:'+nonce
    witness_path = output/'native-owner.json'; source = output/'native-waiter.py'
    source.write_text('import json,os\n'+native.profile_source()+'''
with open(os.environ["OWNED_LINGER_CREDENTIAL_FILE"],encoding="utf8") as stream:definition=json.load(stream)
shell.connect(definition)
def query(source,parameters=()):
    return [list(row) for row in (shell.get_session().run_sql(source,list(parameters)) if parameters else shell.get_session().run_sql(source)).fetch_all()]
profile=native_profile(query,{"name":'''+repr(native.ATTRIBUTE)+''',"value":'''+repr(nonce)+'''},os.getpid())
with open('''+repr(str(witness_path))+''',"x",encoding="utf8") as stream:
    json.dump({"pid":os.getpid(),"profile":profile},stream);stream.flush();os.fsync(stream.fileno())
shell.get_session().run_sql("SELECT GET_LOCK(?,30)",['''+repr(lock)+'''])
''')
    definition = {'scheme':'mysql','host':route['host'],'port':route['port'],'user':'root',
        'password':password,'ssl-mode':'REQUIRED','connection-attributes':{native.ATTRIBUTE:nonce}}
    grant = ProviderToolGrant('mysql-shell',str(output),route['host'],route['port'],timeout_seconds=35,
        durable_name='owned-linger',secret_environment_names=('OWNED_LINGER_CREDENTIAL_FILE',))
    events=[];outcome={};cancel=threading.Event();worker=None;locked=False
    def run():
        try:
            outcome['result']=client._tool_runner.run(grant,
                ['--no-defaults','--py','--quiet-start=2','--log-level=none','--file='+str(source)],
                secret_config=json.dumps(definition).encode(),secret_argument=None,
                secret_environment_name='OWNED_LINGER_CREDENTIAL_FILE',secret_suffix='.json',
                redact_values=(password,),cancel_signal=cancel,progress=events.append)
        except BaseException as error:outcome['error_type']=type(error).__name__
    proof={'complete':False,'original_native_outcome_inferred':False}
    try:
        assert rows(connection,'SELECT GET_LOCK(%s,0) AS acquired',(lock,))[0]['acquired']==1
        locked=True;worker=threading.Thread(target=run,daemon=True);worker.start()
        deadline=time.monotonic()+15;witness=None;process_identity=None
        while time.monotonic()<deadline:
            if witness_path.exists():
                try:witness=json.loads(witness_path.read_text())
                except ValueError:pass
            if witness:
                process_identity=next((event for event in events if event.get('pid')==witness['pid'] and event.get('process_create_time')),None)
                waiting=rows(connection,'SELECT PROCESSLIST_INFO AS statement FROM performance_schema.threads WHERE THREAD_ID=%s',
                    (witness['profile']['thread_id'],))
                if process_identity and waiting and (waiting[0]['statement'] or '').startswith('SELECT GET_LOCK'):break
            if 'error_type' in outcome:raise AssertionError('Owned native waiter failed: '+outcome['error_type'])
            time.sleep(.05)
        else:raise TimeoutError('Owned native lock waiter was not positively observed')
        process=psutil.Process(witness['pid'])
        assert process.create_time()==process_identity['process_create_time']
        process.kill();worker.join(timeout=10)
        assert not worker.is_alive() and 'result' in outcome,outcome.get('error_type')
        result=outcome['result']
        assert result['return_code']!=0 and result['process_observation']['cleanup_confirmed'] is True
        reference=next(event['durable_tool'] for event in events if 'durable_tool' in event)
        utility=durable_tool.observe(output,reference,result['executable_sha256'])
        assert utility['cleanup_confirmed'] and utility['credential_file_cleanup_confirmed']
        original={'admitted':True,'profile':witness['profile']}
        blocked=native.observe(connection,original,witness['pid'])
        assert blocked['qualified'] is True and blocked['idle'] is False,blocked
        assert blocked['remaining_native_session_ids'] or not blocked['original_thread_absent'],blocked
        proof['after_native_client_death']=blocked
        rows(connection,'SELECT RELEASE_LOCK(%s)',(lock,));locked=False
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            idle=native.observe(connection,original,witness['pid'])
            if idle.get('qualified') is True and idle.get('idle') is True:break
            time.sleep(.05)
        else:raise TimeoutError('Original native server worker did not finish after fixture lock release')
        proof.update(complete=True,after_server_worker_completion=idle,
            checks=['actual-owned-mysqlsh-process-killed-after-positive-native-thread-and-handshake-observation',
                'supervised-native-client-cleanup-and-credential-wipe-do-not-clear-a-surviving-server-worker',
                'independent-native-session-absence-and-clone-idleness-observed-after-server-worker-completion'])
    finally:
        if locked:rows(connection,'SELECT RELEASE_LOCK(%s)',(lock,))
        cancel.set()
        if worker is not None:worker.join(timeout=40)
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof

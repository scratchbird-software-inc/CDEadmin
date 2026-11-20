"""Owned MariaDB12.2.2 GTID/binlog fixture with retained cleanup evidence."""
from contextlib import contextmanager
import json
from pathlib import Path
import secrets
import subprocess
import time

from tools.cdeadmin_mysql_family_object_live_orchestrator import _run,_wait_until_ready,_root_connection,_image_identity


@contextmanager
def server(output,*,image='mariadb:12.2.2',server_id=173,native_shutdown=False):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    name='sr-mariadb-'+secrets.token_hex(8);started=False
    proof={'image':_image_identity(image),'owned_server_stopped':False}
    try:
        opened=_run(['docker','run',*([] if native_shutdown else ['--rm']),'-d','--name',name,'-p','127.0.0.1::3306','-e','MARIADB_ALLOW_EMPTY_ROOT_PASSWORD=1',
            image,'--server-id='+str(server_id),'--log-bin=sr-owned','--gtid-strict-mode=ON','--binlog-format=ROW'])
        started=True
        proof.update(container_name=name,container_id=opened.stdout.strip())
        inspected=json.loads(_run(['docker','inspect',name]).stdout)[0]
        proof['owned_volume_names']=[mount['Name']for mount in inspected.get('Mounts',[])if mount.get('Type')=='volume']
        port=_wait_until_ready('mariadb',name,180)
        connection=_root_connection('mariadb',port)
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT VERSION(),@@server_uid');version,identity=cursor.fetchone()
                clean_version=version.split('-')[0];expected_prefix=image.split(':',1)[1]
                if clean_version!=expected_prefix and not clean_version.startswith(expected_prefix+'.'):raise RuntimeError('Native MariaDB fixture version differs')
                proof.update(engine_version=version,server_uid=identity)
        finally:connection.close()
        yield {'host':'127.0.0.1','port':port,'user':'root','ssl':False,'ssl_verify_cert':False},name,proof
    finally:
        if started:
            logs=_run(['docker','logs',name],check=False);(output/'server.log').write_text(logs.stdout+logs.stderr)
            if native_shutdown:
                proof['native_process_exit_observed'] = False
                if proof.get('native_shutdown_acknowledged') is True:
                    try:
                        subprocess.run(['docker','wait',name],capture_output=True,text=True,timeout=30,check=True)
                    except (subprocess.SubprocessError, OSError):
                        pass
                    state = json.loads(_run(['docker','inspect',name]).stdout)[0]['State']
                    proof['native_process_state'] = state
                    proof['native_process_exit_observed'] = (state['Status']=='exited' and state['ExitCode']==0 and not state['OOMKilled'])
                proof['owned_server_stopped'] = (proof['native_process_exit_observed'] or
                    _run(['docker','stop',name],check=False).returncode==0)
                logs=_run(['docker','logs',name],check=False);(output/'server.log').write_text(logs.stdout+logs.stderr)
                proof['owned_container_removed'] = _run(['docker','rm','-f','-v',name],check=False).returncode==0
                proof['owned_server_stopped'] &= proof['owned_container_removed']
            else:
                proof['owned_server_stopped']=_run(['docker','stop',name],check=False).returncode==0
        if started:
            remaining=list(proof.get('owned_volume_names',[]))
            for attempt in range(10):
                pending=[]
                for volume in remaining:
                    inspected=_run(['docker','volume','inspect',volume],check=False)
                    if inspected.returncode==0 or 'no such volume' not in inspected.stderr.lower():
                        pending.append(volume)
                remaining=pending
                if not remaining:break
                time.sleep(0.1)
            proof['owned_fixture_volumes_removed']=not remaining
        (output/'fixture.json').write_text(json.dumps(proof,indent=2)+'\n')
        if started and (not proof['owned_server_stopped'] or not proof.get('owned_fixture_volumes_removed')):raise RuntimeError('Owned MariaDB fixture cleanup failed')

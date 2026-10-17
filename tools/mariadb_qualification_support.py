"""Owned MariaDB12.2.2 GTID/binlog fixture with retained cleanup evidence."""
from contextlib import contextmanager
import json
from pathlib import Path
import secrets

from tools.cdeadmin_mysql_family_object_live_orchestrator import _run,_wait_until_ready,_root_connection,_image_identity


@contextmanager
def server(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    name='sr-mariadb-'+secrets.token_hex(8);started=False
    proof={'image':_image_identity('mariadb:12.2.2'),'owned_server_stopped':False}
    try:
        _run(['docker','run','--rm','-d','--name',name,'-p','127.0.0.1::3306','-e','MARIADB_ALLOW_EMPTY_ROOT_PASSWORD=1',
            'mariadb:12.2.2','--server-id=173','--log-bin=sr-owned','--gtid-strict-mode=ON','--binlog-format=ROW'])
        started=True;port=_wait_until_ready('mariadb',name,180)
        connection=_root_connection('mariadb',port)
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT VERSION(),@@server_uid');version,identity=cursor.fetchone()
                if version.split('-')[0]!='12.2.2':raise RuntimeError('Native MariaDB fixture version differs')
                proof.update(engine_version=version,server_uid=identity)
        finally:connection.close()
        yield {'host':'127.0.0.1','port':port,'user':'root','ssl':False,'ssl_verify_cert':False},name,proof
    finally:
        if started:
            logs=_run(['docker','logs',name],check=False);(output/'server.log').write_text(logs.stdout+logs.stderr)
            proof['owned_server_stopped']=_run(['docker','stop',name],check=False).returncode==0
        (output/'fixture.json').write_text(json.dumps(proof,indent=2)+'\n')
        if started and not proof['owned_server_stopped']:raise RuntimeError('Owned MariaDB fixture cleanup failed')

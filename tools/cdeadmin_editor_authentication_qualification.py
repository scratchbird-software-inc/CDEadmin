"""Owned MySQL/MariaDB editor authentication and role-context qualification."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import secrets
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web')]
from tools.cdeadmin_native_editor_gate import provider
from tools.cdeadmin_mysql_family_object_live_orchestrator import _run,_image_identity,_wait_until_ready,_root_connection,IMAGES


@contextmanager
def fixture(engine,output):
    name='sr-editor-auth-'+secrets.token_hex(8);started=False
    receipt={'image':_image_identity(IMAGES[engine]),'owned_server_stopped':False}
    try:
        _run(['docker','run','--rm','-d','--name',name,'-p','127.0.0.1::3306','-e',
            'MYSQL_ALLOW_EMPTY_PASSWORD=yes' if engine=='mysql' else 'MARIADB_ALLOW_EMPTY_ROOT_PASSWORD=1',IMAGES[engine]])
        started=True;port=_wait_until_ready(engine,name,180)
        yield port,receipt
    finally:
        if started:
            logs=_run(['docker','logs',name],check=False);(output/'server.log').write_text(logs.stdout+logs.stderr)
            receipt['owned_server_stopped']=_run(['docker','stop',name],check=False).returncode==0
        (output/'fixture.json').write_text(json.dumps(receipt,indent=2)+'\n')
        if started and not receipt['owned_server_stopped']:raise RuntimeError('Owned authentication fixture cleanup failed')


def qualify(engine,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    proof={'complete':False,'engine':engine,'history_tests_executed':False,'interfaces':[],
        'source_sha256':{str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (Path(__file__),ROOT/'web/pgadmin/cdeadmin/providers/native_editor.py')}}
    try:
        with fixture(engine,output) as (port,owned):
            root=_root_connection(engine,port);root.autocommit=True
            database='sr_editor_auth_'+secrets.token_hex(6);role='sr_editor_'+secrets.token_hex(6)+' ü'
            role_sql="'"+role+"'@'%'" if engine=='mysql' else '`'+role+'`'
            cursor=root.cursor()
            try:
                cursor.execute('SELECT VERSION(),CURRENT_USER()');version,actor=cursor.fetchone()
                assert version.split('-')[0]==('9.7.0' if engine=='mysql' else '12.2.2') and actor=='root@%'
                cursor.execute('CREATE DATABASE `'+database+'`')
                cursor.execute('CREATE TABLE `'+database+'`.owned(value INTEGER)');cursor.execute('INSERT INTO `'+database+'`.owned VALUES(1)')
                cursor.execute('CREATE ROLE '+role_sql);cursor.execute('GRANT '+role_sql+" TO 'root'@'%'")
                for setting in ([True,False] if engine=='mysql' else ['', 'ORACLE']):
                    route={'host':'127.0.0.1','port':port,'user':'root','database':database}
                    if engine=='mysql':route.update(use_pure=setting,sql_mode='ANSI_QUOTES,NO_BACKSLASH_ESCAPES')
                    instance,native_route=provider(engine,route)
                    try:
                        session=instance.open_session({'route':native_route});handle=instance._sessions[session['session_id']].handle
                        if engine=='mysql':assert (type(handle).__name__=='CMySQLConnection') is (setting is False)
                        work=handle.cursor()
                        try:
                            if engine=='mariadb':work.execute("SET SESSION sql_mode='"+setting+"'")
                            request={'session_id':session['session_id']}
                            first=instance.complete(request)['editor_context']
                            work.execute('SELECT CURRENT_USER(),CURRENT_ROLE()');principal,initial=work.fetchone()
                            assert first['context']['authenticated_principal']==principal and first['context']['active_role']==initial
                            work.execute('SET ROLE '+role_sql)
                            selected=instance.complete(request)['editor_context']
                            work.execute('SELECT CURRENT_USER(),CURRENT_ROLE()');principal,active=work.fetchone()
                            assert selected['context']['authenticated_principal']==principal and selected['context']['active_role']==active and active!=initial
                            assert selected['resources']==first['resources'] and selected['context']['context_revision']!=first['context']['context_revision']
                            instance.client.control_transaction(handle,'autocommit_off')
                            work.execute('INSERT INTO owned VALUES(2)')
                            pending=instance.complete(request)['editor_context']
                            assert pending['context']['context_revision']==selected['context']['context_revision']
                            cursor.execute('SELECT count(*) FROM `'+database+'`.owned');assert cursor.fetchone()[0]==1
                            work.execute('SELECT count(*) FROM owned');assert work.fetchone()[0]==2
                            instance.client.control_transaction(handle,'rollback')
                            work.execute('SET ROLE NONE')
                            restored=instance.complete(request)['editor_context']
                            assert restored['context']['context_revision']==first['context']['context_revision']
                            proof['interfaces'].append({'client':type(handle).__name__,'sql_mode':selected['context']['sql_mode'],
                                'native_version':version,'principal':principal,'initial_role':initial,'selected_role':active,
                                'native_role_change_invalidates_context':True,'visible_symbols_unchanged':True,'pending_work_preserved':True})
                        finally:work.close()
                    finally:instance.client.close()
            finally:cursor.close();root.close()
        proof['owned_server_stopped']=owned['owned_server_stopped']
        proof['complete']=proof['owned_server_stopped']
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False)+'\n')
    assert proof['complete'] and proof['owned_server_stopped']
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--engine',choices=('mysql','mariadb'),required=True)
    parser.add_argument('--evidence',type=Path,required=True);args=parser.parse_args()
    qualify(args.engine,args.evidence)

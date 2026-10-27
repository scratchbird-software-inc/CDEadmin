"""Owned Firebird network/embedded editor principal and role observations."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web')]
from tools.cdeadmin_native_editor_gate import provider
from tools.cdeadmin_firebird_local_fixture import run_local
from tools.cdeadmin_firebird_password_gate import _route_arguments


def qualify(runtime,output):
    output=Path(output)
    proof={'complete':False,'history_tests_executed':False,'interfaces':[],
        'source_sha256':{str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (Path(__file__),ROOT/'web/pgadmin/cdeadmin/providers/native_editor.py')}}
    def check(native,network_admin,network_route,accounts,_evidence,root):
        def session(admin,route,username,password,embedded):
            role='Role ü '+secrets.token_hex(6);quoted='"'+role+'"'
            admin.execute_immediate('CREATE ROLE '+quoted)
            admin.execute_immediate('GRANT '+quoted+' TO USER '+username)
            admin.execute_immediate('CREATE TABLE EDITOR_AUTH_KEEP(ID INTEGER)')
            admin.execute_immediate('GRANT SELECT,INSERT ON EDITOR_AUTH_KEEP TO USER '+username)
            admin.commit()
            instance,native_route=provider('firebird',{**route,'user':username},password,embedded=embedded)
            observer=native.connect(password=password,**_route_arguments({**route,'user':username},native))
            try:
                opened=instance.open_session({'route':native_route});handle=instance._sessions[opened['session_id']].handle
                request={'session_id':opened['session_id']}
                first=instance.complete(request)['editor_context']
                assert not handle.main_transaction.is_active()
                with handle.cursor() as cursor:
                    cursor.execute('SELECT CURRENT_USER,CURRENT_ROLE FROM RDB$DATABASE');principal,initial=cursor.fetchone()
                handle.rollback()
                assert first['context']['authenticated_principal']==principal and first['context']['active_role']==initial
                with handle.cursor() as cursor:cursor.execute('SET ROLE '+quoted)
                handle.commit()
                selected=instance.complete(request)['editor_context']
                assert not handle.main_transaction.is_active()
                with handle.cursor() as cursor:
                    cursor.execute('SELECT CURRENT_USER,CURRENT_ROLE FROM RDB$DATABASE');principal,active=cursor.fetchone()
                handle.rollback()
                assert selected['context']['active_role']==active==role and active!=initial
                assert selected['resources']==first['resources'] and selected['context']['context_revision']!=first['context']['context_revision']
                with handle.cursor() as cursor:cursor.execute('INSERT INTO EDITOR_AUTH_KEEP VALUES(1)')
                transaction=handle.main_transaction.info.id
                pending=instance.complete(request)['editor_context']
                assert handle.main_transaction.info.id==transaction and pending['context']['context_revision']==selected['context']['context_revision']
                with observer.cursor() as cursor:
                    cursor.execute('SELECT count(*) FROM EDITOR_AUTH_KEEP');assert cursor.fetchone()[0]==0
                observer.rollback();handle.rollback()
                with handle.cursor() as cursor:cursor.execute('SET ROLE NONE')
                handle.commit()
                assert instance.complete(request)['editor_context']['context']['context_revision']==first['context']['context_revision']
                proof['interfaces'].append({'embedded':embedded,'principal':principal,'initial_role':initial,'selected_role':active,
                    'native_role_change_invalidates_context':True,'visible_symbols_unchanged':True,
                    'pending_transaction_id_preserved':True,'idle_metadata_transaction_released':True})
            finally:observer.close();instance.client.close()
        user,password=accounts['Srp'][0]
        session(network_admin,network_route,user,password,False)
        path=root/'embedded-auth.fdb'
        with native.create_database(database=str(path),user='SYSDBA',charset='UTF8') as embedded_admin:
            route={'database':str(path),'filesystem_root':str(root),'user':'SYSDBA','attachment_mode':'embedded','charset':'UTF8'}
            session(embedded_admin,route,'SYSDBA',None,True)
    try:
        fixture=run_local(runtime,output,check)
        proof.update(complete=fixture['complete'],owned_process_stopped=fixture['owned_process_stopped'],owned_state_removed=fixture['owned_state_removed'])
    finally:
        output.mkdir(parents=True,exist_ok=True)
        (output/'editor-authentication.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False)+'\n')
    assert proof['complete'] and proof['owned_process_stopped'] and proof['owned_state_removed']
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--evidence',type=Path,required=True);args=parser.parse_args();qualify(args.runtime,args.evidence)

"""Owned native MySQL/MariaDB keyword-qualified editor completion fixtures."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(engine,output):
    from tools.cdeadmin_editor_authentication_qualification import fixture,provider,_root_connection
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside application source')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    paths=['web/pgadmin/cdeadmin/providers/native_editor.py','web/pgadmin/static/js/cdeadmin_ui/editors/nativeLexing.js',
        'web/pgadmin/static/js/cdeadmin_ui/editors/nativeScopes.js','web/pgadmin/static/js/cdeadmin_ui/editors/nativeCompletion.js']
    paths.append(str(Path(__file__).relative_to(ROOT)))
    proof={'complete':False,'engine':engine,'interfaces':[],'failures':[],'history_testing':'not run',
        'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}}
    captured={'engine':engine,'interfaces':[]}
    try:
        with fixture(engine,output) as (port,owned):
            root=_root_connection(engine,port);root.autocommit=True;cursor=root.cursor()
            database='sr_ident_'+secrets.token_hex(6)
            try:
                cursor.execute('SELECT VERSION()');version=cursor.fetchone()[0]
                assert version.split('-')[0]==('9.7.0' if engine=='mysql' else '12.2.2')
                cursor.execute('CREATE DATABASE `'+database+'`')
                cursor.execute('CREATE TABLE `'+database+'`.`select`(id INTEGER,`select` INTEGER)')
                cursor.execute('INSERT INTO `'+database+'`.`select` VALUES(1,17)')
                cursor.execute('CREATE TABLE `'+database+'`.pending(v INTEGER)');cursor.execute('INSERT INTO `'+database+'`.pending VALUES(1)')
                for setting in ([True,False] if engine=='mysql' else ['', 'ORACLE']):
                    label=('pure' if setting else 'c') if engine=='mysql' else setting or 'normal'
                    instance=None
                    try:
                        route={'host':'127.0.0.1','port':port,'user':'root','database':database}
                        if engine=='mysql':route.update(use_pure=setting,sql_mode='ANSI_QUOTES,NO_BACKSLASH_ESCAPES')
                        instance,native_route=provider(engine,route)
                        session=instance.open_session({'route':native_route});handle=instance._sessions[session['session_id']].handle
                        work=handle.cursor()
                        try:
                            if engine=='mariadb':work.execute("SET SESSION sql_mode='"+setting+"'")
                            instance.client.control_transaction(handle,'autocommit_off');work.execute('INSERT INTO pending VALUES(2)')
                            observed=instance.complete({'session_id':session['session_id']})['editor_context']
                            quote_char='"' if 'ANSI_QUOTES' in observed['context']['sql_mode'].split(',') else '`'
                            quote=lambda name:quote_char+name.replace(quote_char,quote_char*2)+quote_char
                            cases=[]
                            for marked in [
                                'SELECT t.| FROM '+database+'.select t',
                                'SELECT t.| FROM `'+database+'`.`select` t',
                                'WITH q AS (SELECT t.* FROM '+database+'.select t) SELECT q.| FROM q',
                                'WITH q AS (SELECT t.select AS selected FROM '+database+'.select t) SELECT q.| FROM q',
                                'SELECT q.| FROM (SELECT t.id FROM '+database+'.select t) q',
                            ]:
                                work.execute(marked.replace('|','*'));names=[column[0] for column in work.description];rows=work.fetchall()
                                assert names and rows and len(rows)==1
                                expected=[{'label':name,'apply':quote(name),'type':'property'} for name in names]
                                inserted=[]
                                for option in expected:
                                    sql=marked.replace('|',option['apply']);work.execute(sql)
                                    assert len(work.description)==1 and work.description[0][0]==option['label']
                                    assert work.fetchall()[0][0] in {1,17}
                                    inserted.append(sql)
                                cases.append({'marked':marked,'expected':expected,'native_inserted_sql':inserted})
                            cursor.execute('SELECT count(*) FROM `'+database+'`.pending');assert cursor.fetchone()[0]==1
                            work.execute('SELECT count(*) FROM pending');assert work.fetchone()[0]==2
                            instance.client.control_transaction(handle,'rollback')
                            work.execute('SELECT count(*) FROM pending');assert work.fetchone()[0]==1
                            captured['interfaces'].append({'label':label,'metadata':observed,'cases':cases})
                            proof['interfaces'].append({'label':label,'client':type(handle).__name__,'native_version':version,
                                'sql_mode':observed['context']['sql_mode'],'native_cases':len(cases),'pending_work_preserved':True})
                        finally:work.close()
                    except Exception as error:
                        proof['failures'].append({'interface':label,'error_type':type(error).__name__})
                        (output/('failure-'+label+'.log')).write_text(traceback.format_exc())
                    finally:
                        if instance is not None:instance.client.close()
            finally:cursor.close();root.close()
        proof.update(owned_server_stopped=owned['owned_server_stopped'],complete=not proof['failures'] and owned['owned_server_stopped'])
        (output/'native-editor-fixtures.json').write_text(json.dumps(captured,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    if not proof['complete']:raise RuntimeError('Native identifier qualification failed; retained all interface failures')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--engine',choices=('mysql','mariadb'),required=True)
    parser.add_argument('--evidence',type=Path,required=True);args=parser.parse_args();qualify(args.engine,args.evidence)

"""Actual local CLI deployments, independent environments and durable exits."""
import argparse
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output,interface='both'):
    import config  # noqa: F401
    from mysql_qualification_support import server,_root_connection
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    from cdeadmin_mysql_online_ddl_qualification import registration
    from pgadmin.model import User
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    from pgadmin.cdeadmin.workspace.mysql_deployment import encode
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    files=['tools/cdeadmin_mysql_deploy.py','tools/cdeadmin_mysql_deployment_qualification.py',
        'web/pgadmin/cdeadmin/workspace/mysql_deployment.py','web/pgadmin/static/vendor/ddn/current/resource-manifest.json']
    flags={'both':(False,True),'pure':(False,),'c':(True,)}[interface]
    proof={'complete':False,'requested_interfaces':list(flags),'interfaces':[],'history_testing':'not run','source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files}}
    owned=[];connections=[]
    try:
        with ExitStack() as stack:
            routes=[];passwords=[]
            for name in ('stage','production'):
                route,_,fixture=stack.enter_context(server(output/('fixture-'+name)));owned.append(fixture);routes.append(route)
                connection=_root_connection('mysql',route['port']);connections.append(connection);connection.autocommit=True
                password=secrets.token_urlsafe(28);passwords.append(password)
                with connection.cursor() as cursor:
                    cursor.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                    cursor.execute('CREATE DATABASE sr_osc');cursor.execute('USE sr_osc')
                    cursor.execute('CREATE TABLE t(id INT PRIMARY KEY,note VARCHAR(80))');cursor.execute("INSERT INTO t VALUES(1,'preserved')")
                    cursor.execute('CREATE TABLE pending(id INT)')
            app=setup_application(output)
            with app.app_context():owner=User.query.first().email
            settings={'SERVER_MODE':False,'TESTING':True,'MASTER_PASSWORD_REQUIRED':False,'USE_OS_SECRET_STORAGE':False,'WTF_CSRF_ENABLED':False,'CONFIG_DATABASE_URI':''}
            for name in ('DATA_DIR','SQLITE_PATH','SESSION_DB_PATH','STORAGE_DIR','LOG_FILE','AZURE_CREDENTIAL_CACHE_DIR','CDEADMIN_OPERATION_STORE_PATH'):
                settings[name]=getattr(config,name)
            configuration=output/'application-config.py';configuration.write_text('\n'.join(k+' = '+repr(v) for k,v in settings.items())+'\n')
            sequence=0;commands=[]
            def cli(arguments,password,*,expected=0,target=None):
                nonlocal sequence
                sequence+=1;report=target or output/f'cli-{sequence}.json'
                args=[str(sys.executable),'-B',str(ROOT/'tools/cdeadmin_mysql_deploy.py'),*arguments,'--output',str(report)]
                env={**os.environ,'CONFIG_DISTRO_FILE_PATH':str(configuration),'OWNED_DEPLOY_PASSWORD':password,'PYTHONDONTWRITEBYTECODE':'1'}
                result=subprocess.run(args,cwd=ROOT,env=env,text=True,capture_output=True,timeout=100)
                (output/f'cli-{sequence}.log').write_text(result.stdout+'\n'+result.stderr)
                assert all(p not in result.stdout+result.stderr for p in passwords),'Native credentials escaped to console'
                lines=result.stdout.strip().splitlines();assert len(lines)==1,result.stdout
                summary=json.loads(lines[0]);assert result.returncode==summary['exit_code']==expected,(summary,result.stderr)
                commands.append({'operation':arguments[0],'exit_code':result.returncode,'summary':summary})
                return json.loads(report.read_text()),summary,report
            def change_capture(capture,label,width,extra=None):
                model=read_catalog(encode(capture['snapshot']),engine='mysql')
                for row in model['rows'].values():
                    if row['kind']=='table' and row['name']=='t':
                        row['native']['definition']=row['native']['definition'].replace('varchar(80)','text' if width=='text' else f'varchar({width})')
                        if extra:row['native']['definition']=row['native']['definition'].replace('PRIMARY KEY (','`'+extra+'` int DEFAULT NULL, PRIMARY KEY (')
                resources=[{'resource_id':row['resource_id'],'resource_kind':row['kind'],'display_name':row['name'],'display_path':row['path'],'native':row['native']} for row in model['rows'].values()]
                snapshot=build_export(resources,engine='mysql',endpoint_id=capture['binding']['endpoint_id'],
                    target_id=capture['binding']['database_target_id'],generation='deployment-qualification')['snapshot']
                path=output/(label+'-desired.json');path.write_text(encode(snapshot)+'\n');return path
            for use_c in flags:
                checks=[];captures={};bindings={};inputs={}
                for index,environment in enumerate(('stage','production')):
                    with connections[index].cursor() as cursor:cursor.execute('ALTER TABLE t MODIFY note VARCHAR(80)')
                    sid,target,_=registration(app,routes[index],passwords[index],use_c)
                    args=['--user',owner,'--server-id',str(sid),'--target-id',target,'--environment',environment,'--password-env','OWNED_DEPLOY_PASSWORD']
                    binding={'args':args,'password':passwords[index]};bindings[environment]=binding
                    capture,_,path=cli(['capture',*args],passwords[index])
                    desired=change_capture(capture,environment+'-'+str(use_c),120)
                    inputs[environment]={'capture':str(path),'desired':str(desired),'execution':None};captures[environment]=capture
                assert captures['stage']['binding']['server_uuid']!=captures['production']['binding']['server_uuid']
                manifest=output/('manifest-'+str(use_c)+'.json');manifest.write_text(json.dumps({'version':'release-'+str(use_c),'environments':inputs}))
                artifact,_,artifact_path=cli(['pack','--manifest',str(manifest)],passwords[0])
                checks.append('actual-subprocess-capture-and-reproducible-versioned-artifact-with-independent-native-environment-identities')
                first_ticket=None;first_ticket_summary=None
                for index,environment in enumerate(('stage','production')):
                    b=bindings[environment];args=[*b['args'],'--artifact',str(artifact_path)]
                    plan,summary,_=cli(['plan',*args],b['password']);assert plan['plan']['ready_for_review'] and plan['plan']['native_grammar_validated']
                    with connections[index].cursor() as cursor:
                        cursor.execute("SELECT COLUMN_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA='sr_osc' AND TABLE_NAME='t' AND COLUMN_NAME='note'")
                        assert cursor.fetchone()[0]=='varchar(80)'
                    ticket_path=output/('ticket-'+str(use_c)+'-'+environment+'.json')
                    review,summary,_=cli(['review',*args,'--expect-plan',summary['execution_sha256'],'--ticket-output',str(ticket_path)],b['password'])
                    if environment=='stage':first_ticket,first_ticket_summary=ticket_path,summary
                    if environment=='production':
                        cli(['apply',*args,'--ticket',str(first_ticket),'--approve',first_ticket_summary['ticket_sha256']],b['password'],expected=2)
                    connections[index].autocommit=False
                    try:
                        with connections[index].cursor() as cursor:
                            cursor.execute('INSERT INTO pending VALUES(99)');cursor.execute('SAVEPOINT deployment_guard')
                            cursor.execute("SELECT CAST('preserved warning' AS UNSIGNED)");cursor.fetchall()
                            cursor.execute('SHOW COUNT(*) WARNINGS');warnings=cursor.fetchone()[0];assert warnings
                            applied,applied_summary,_=cli(['apply',*args,'--ticket',str(ticket_path),'--approve',summary['ticket_sha256']],b['password'])
                            assert applied['review']['state']=='committed' and applied_summary['rediscovery_verified']
                            cursor.execute('SHOW COUNT(*) WARNINGS');assert cursor.fetchone()[0]==warnings and connections[index].in_transaction
                            cursor.execute('ROLLBACK TO SAVEPOINT deployment_guard');cursor.execute('SELECT COUNT(*) FROM pending');assert cursor.fetchone()[0]==1
                    finally:connections[index].rollback();connections[index].autocommit=True
                    again,_,_=cli(['apply',*args,'--ticket',str(ticket_path),'--approve',summary['ticket_sha256']],b['password'])
                    assert again['review']==applied['review'] and not again['automatic_retry']
                    observed,_,_=cli(['receipt',*args,'--ticket',str(ticket_path)],b['password']);assert observed['review']==applied['review']
                    with connections[index].cursor() as cursor:
                        cursor.execute('SHOW CREATE TABLE t');assert '`note` varchar(120)' in cursor.fetchone()[1]
                        cursor.execute('SELECT id,note FROM t');assert cursor.fetchall()==[(1,'preserved')]
                checks.append('actual-plan-review-apply-and-receipt-in-separate-processes-with-native-rediscovery-and-once-only-replay-refusal')
                checks.append('wrong-environment-ticket-refusal-and-independent-interactive-savepoint-warning-and-data-preservation')
                # The same artifact now reports drift, without a new dispatch.
                b=bindings['stage'];args=[*b['args'],'--artifact',str(artifact_path)]
                drift,_,_=cli(['plan',*args],b['password'],expected=3);assert drift['plan']['conflicts']
                altered=deepcopy(artifact);altered['version']='tampered';bad=output/('tampered-'+str(use_c)+'.json');bad.write_text(json.dumps(altered))
                cli(['plan',*b['args'],'--artifact',str(bad)],b['password'],expected=2)
                checks.append('native-three-way-drift-exit-and-modified-artifact-fingerprint-refusal-without-new-review-or-DDL')
                # A deliberately paused provider call proves the real CLI has
                # durably spent its review before any native DDL can be sent.
                with connections[0].cursor() as cursor:cursor.execute('ALTER TABLE t MODIFY note VARCHAR(80)')
                fresh,_,capture_path=cli(['capture',*b['args']],b['password']);desired=change_capture(fresh,'crash-'+str(use_c),130)
                manifest=output/('crash-manifest-'+str(use_c)+'.json');manifest.write_text(json.dumps({'version':'crash-'+str(use_c),'environments':{'stage':{'capture':str(capture_path),'desired':str(desired),'execution':None}}}))
                _,_,crash_artifact=cli(['pack','--manifest',str(manifest)],b['password'])
                args=[*b['args'],'--artifact',str(crash_artifact)]
                _,planned,_=cli(['plan',*args],b['password']);ticket_path=output/('crash-ticket-'+str(use_c)+'.json')
                _,reviewed,_=cli(['review',*args,'--expect-plan',planned['execution_sha256'],'--ticket-output',str(ticket_path)],b['password'])
                marker=output/('claimed-'+str(use_c)+'.json');report=output/('crash-report-'+str(use_c)+'.json')
                arguments=['apply',*args,'--ticket',str(ticket_path),'--approve',reviewed['ticket_sha256'],'--output',str(report)]
                script='''import config,json,sys,time
from pathlib import Path
from tools import cdeadmin_mysql_deploy as cli
from pgadmin.cdeadmin.providers import mysql_schema_application as native
original=native.apply_review
def paused(connection,record,runtime=None):
 Path(sys.argv[2]).write_text(json.dumps({'native_interface':type(connection).__name__,'review_id':record['review_id']}))
 time.sleep(60)
 return original(connection,record,runtime)
native.apply_review=paused
raise SystemExit(cli.main(json.loads(sys.argv[1])))
'''
                env={**os.environ,'CONFIG_DISTRO_FILE_PATH':str(configuration),'OWNED_DEPLOY_PASSWORD':b['password'],'PYTHONDONTWRITEBYTECODE':'1'}
                with (output/('crash-'+str(use_c)+'.log')).open('w') as log:
                    process=subprocess.Popen([sys.executable,'-B','-c',script,json.dumps(arguments),str(marker)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
                    try:
                        deadline=time.monotonic()+55
                        while not marker.exists() and process.poll() is None and time.monotonic()<deadline:time.sleep(.02)
                        assert marker.exists(),('CLI did not reach its native dispatch boundary',process.poll())
                        interface=json.loads(marker.read_text())['native_interface']
                        assert interface==('CharsetCMySQLConnection' if use_c else 'CharsetMySQLConnection'),interface
                        process.kill();process.wait(timeout=10)
                    finally:
                        if process.poll() is None:process.kill();process.wait(timeout=10)
                interrupted,_,_=cli(['receipt',*args,'--ticket',str(ticket_path)],b['password'],expected=5)
                assert interrupted['review']['state']=='unknown_outcome' and not interrupted['automatic_retry']
                retried,_,_=cli(['apply',*args,'--ticket',str(ticket_path),'--approve',reviewed['ticket_sha256']],b['password'],expected=5)
                assert retried['review']==interrupted['review']
                with connections[0].cursor() as cursor:
                    cursor.execute('SHOW CREATE TABLE t');assert '`note` varchar(80)' in cursor.fetchone()[1]
                checks.append('actual-native-interface-and-abrupt-CLI-loss-after-durable-claim-with-restart-receipt-and-no-automatic-redispatch')
                # Exercise the owned asynchronous native ALTER contract through
                # the same public CLI, including a real native algorithm refusal.
                for mode in ('instant','refused','copy'):
                    refused=mode=='refused';copy=mode=='copy'
                    fresh,_,capture_path=cli(['capture',*b['args']],b['password'])
                    desired=change_capture(fresh,'controlled-'+str(use_c)+'-'+mode,'text' if refused or copy else 80,
                        None if refused or copy else 'headless_'+str(use_c))
                    execution={'method':'pt-online-schema-change' if copy else 'native','algorithm':'COPY' if copy else 'INPLACE' if refused else 'INSTANT',
                        'lock':'NONE' if refused or copy else 'DEFAULT','lock_wait_seconds':2,'timeout_seconds':40}
                    manifest=output/('controlled-manifest-'+str(use_c)+'-'+mode+'.json')
                    manifest.write_text(json.dumps({'version':'controlled-'+str(use_c)+'-'+mode,'environments':{
                        'stage':{'capture':str(capture_path),'desired':str(desired),'execution':execution}}}))
                    _,_,controlled=cli(['pack','--manifest',str(manifest)],b['password'])
                    args=[*b['args'],'--artifact',str(controlled)]
                    _,planned,_=cli(['plan',*args],b['password'])
                    ticket_path=output/('controlled-ticket-'+str(use_c)+'-'+mode+'.json')
                    _,reviewed,_=cli(['review',*args,'--expect-plan',planned['execution_sha256'],'--ticket-output',str(ticket_path)],b['password'])
                    value,_,_=cli(['apply',*args,'--ticket',str(ticket_path),'--approve',reviewed['ticket_sha256'],*(['--cutover'] if copy else [])],b['password'],expected=5 if refused else 0)
                    assert value['review']['controlled_terminal']
                    if refused:assert value['review']['outcome']['error_code'] in {1845,1846},value
                    else:assert value['review']['outcome']['rediscovery_verified']
                checks.append('actual-owned-asynchronous-native-INSTANT-INPLACE-refusal-and-pinned-online-copy-with-explicit-cutover-approval')
                proof['interfaces'].append({'use_c':use_c,'native_interface':interface,'complete':True,'checks':checks})
            proof['commands']=commands;proof['complete']=True
    finally:
        for connection in connections:
            try:connection.close()
            except Exception:pass
        proof['owned_servers_stopped']=bool(owned) and all(v.get('owned_server_stopped') for v in owned)
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--interface',choices=['both','pure','c'],default='both')
    args=parser.parse_args();qualify(args.output,args.interface)

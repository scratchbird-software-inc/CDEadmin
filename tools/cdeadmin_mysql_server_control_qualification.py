"""Owned native SQL server-control requests, refusals and external observations."""
import argparse
import hashlib
import json
import secrets
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def wait_state(name,predicate):
    from mysql_qualification_support import _run
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        result=json.loads(_run(['docker','inspect',name]).stdout)[0]
        if predicate(result):return result
        time.sleep(.1)
    raise TimeoutError('Owned native server-control fixture did not reach the required process state')


def workspace(app,route,name,uuid,target):
    """Restart and shut down through the authenticated API, observed outside the product."""
    from cdeadmin_mysql_online_ddl_qualification import registration
    from mysql_qualification_support import _root_connection,_run,_wait_until_ready
    # The fixture's readiness probe logs in as password-less root, so the
    # application signs in as a separate administrator instead.
    password=secrets.token_urlsafe(24);oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;q=oracle.cursor()
    try:
        q.execute('CREATE DATABASE IF NOT EXISTS sr_osc');q.execute("CREATE USER sr_api IDENTIFIED BY %s",(password,))
        q.execute('GRANT ALL PRIVILEGES ON *.* TO sr_api WITH GRANT OPTION')
    finally:q.close();oracle.close()
    operations=[]
    for pure in (True,False):
        _sid,_target,post=registration(app,route,password,not pure,username='sr_api')
        for operation in ('restart_server','shutdown_server'):
            before=wait_state(name,lambda row:row['State']['Running'])
            request={'resource_kind':'server','operation_id':operation,'target_resource':target,
                     'draft':{'confirmation':'MySQL','disconnect_all_clients':True}}
            checked=post('visual_admin_validate',request);assert checked['valid'],checked['errors']
            plan=post('visual_admin_plan',request);assert plan['state']=='ready' and plan['execution_available'],plan
            body={key:plan[key] for key in ('plan_id','plan_digest')}|{'confirmed':True}
            observed=post('visual_admin_apply',body)['provider_result']['server_control_observation']
            assert observed['native_acknowledged'] and observed['acknowledgement_scope']=='request_only'
            replay=post.raw('visual_admin_apply',body);assert replay.status_code!=200 or not replay.get_json().get('success')
            # The receipt is written only after the process change is observed outside the product.
            if operation=='restart_server':
                wait_state(name,lambda row:row['RestartCount']>before['RestartCount'] and row['State']['Running'] and not row['State']['Restarting'] and row['State']['StartedAt']!=before['State']['StartedAt'])
            else:
                assert wait_state(name,lambda row:not row['State']['Running'])['State']['ExitCode']==0
                _run(['docker','start',name])  # Fixture recovery only, not product host-start qualification.
            _wait_until_ready('mysql',name,90)
            observer=_root_connection('mysql',route['port']);query=observer.cursor()
            try:query.execute('SELECT @@server_uuid');assert query.fetchone()==(uuid,)
            finally:query.close();observer.close()
            operations.append({'use_pure':pure,'resource_kind':'server','operation':operation,'native_acknowledged':True,'replay_refused':True})
    return {'complete':True,'operations':operations}


def qualify(output,application=False):
    import config  # noqa: F401
    from mysql_qualification_support import server,_root_connection,_run,_wait_until_ready
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE,MYSQL_ADMINISTRATION,_create_client
    from pgadmin.cdeadmin.sdk import RelationalClientError
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep native evidence outside source')
    output.mkdir(parents=True,exist_ok=False)
    if application:
        from cdeadmin_mysql_dump_verification_qualification import setup_application
        app=setup_application(output)
    paths=['web/pgadmin/cdeadmin/providers/mysql_family/'+name for name in ('mysql_server_control.py','administration.py','provider.py')]
    paths+=['tools/cdeadmin_mysql_server_control_qualification.py','tools/mysql_qualification_support.py']
    proof={'complete':False,'interfaces':[],'history_testing':'not run','full_mysql_product_complete':False,
        'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    try:
        with server(output/'unmanaged') as (route,_name,unmanaged):
            oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;q=oracle.cursor()
            q.execute('CREATE USER control_denied');q.execute('SELECT @@server_uuid');uuid=q.fetchone()[0]
            target={'resource_id':'server:MySQL','resource_kind':'server','display_name':'MySQL','display_path':['MySQL'],'native':{'server_uuid':uuid}}
            refusals=[]
            for pure in (True,False):
                client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace())
                try:
                    for operation,user,expected in [('shutdown_server','control_denied',1227),('restart_server','root',3707)]:
                        request=client.plan_admin_operation({'resource_kind':'server','operation_id':operation,
                            'draft':{'confirmation':'MySQL','disconnect_all_clients':True},'target_resource':target,
                            '_provider_route':{**route,'use_pure':pure,'user':user}})
                        try:MYSQL_ADMINISTRATION.apply(client,request)
                        except RelationalClientError as error:
                            assert error.errno==expected and error.native_dispatched and not error.native_acknowledged and not error.automatic_retry
                            refusals.append({'use_pure':pure,'operation':operation,'native_errno':error.errno,'sqlstate':error.sqlstate})
                        else:raise AssertionError('Native privilege or supervision refusal was not preserved')
                finally:client.close()
            q.execute('SELECT 1');assert q.fetchone()==(1,);q.close();oracle.close()
        assert unmanaged['owned_server_stopped'];proof['native_refusals']=refusals
        with server(output/'supervised',restartable=True,supervised_restart=True) as (route,name,owned):
            oracle=_root_connection('mysql',route['port']);oracle.autocommit=True;q=oracle.cursor()
            q.execute('CREATE DATABASE sr_control');q.execute('CREATE TABLE sr_control.committed(id INT PRIMARY KEY) ENGINE=InnoDB');q.execute('INSERT INTO sr_control.committed VALUES(1)')
            q.execute('CREATE TABLE sr_control.pending(id INT PRIMARY KEY) ENGINE=InnoDB');q.execute('SELECT @@server_uuid');uuid=q.fetchone()[0];q.close();oracle.close()
            target={'resource_id':'server:MySQL','resource_kind':'server','display_name':'MySQL','display_path':['MySQL'],'native':{'server_uuid':uuid}}
            for pure in (True,False):
                client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),SimpleNamespace());connect=client._connect;classes=[]
                def tracked(request):
                    handle=connect(request);classes.append(type(handle).__name__);return handle
                templates={};checks=[]
                try:
                    with patch.object(client,'_connect',tracked):
                        for operation in ('restart_server','shutdown_server'):
                            source=client.open_session({'route':{**route,'database':'sr_control','use_pure':pure}});cursor=source.cursor()
                            try:
                                client.control_transaction(source,'autocommit_off');cursor.execute('INSERT INTO pending VALUES(9)');cursor.execute('SAVEPOINT control_guard')
                                before=wait_state(name,lambda row:row['State']['Running'])
                                request=client.plan_admin_operation({'resource_kind':'server','operation_id':operation,
                                    'draft':{'confirmation':'MySQL','disconnect_all_clients':True},'target_resource':target,'_provider_route':{**route,'use_pure':pure}})
                                templates[operation]=request['provider_payload']['compiled']['statements'][0]['source']
                                result=MYSQL_ADMINISTRATION.apply(client,request)
                                observed=result['server_control_observation'];assert observed['native_acknowledged'] and observed['acknowledgement_scope']=='request_only'
                                assert not any(observed[key] for key in ('server_termination_observed','new_process_generation_observed','server_readiness_observed'))
                                if operation=='restart_server':
                                    process=wait_state(name,lambda row:row['RestartCount']>before['RestartCount'] and row['State']['Running'] and not row['State']['Restarting'] and row['State']['StartedAt']!=before['State']['StartedAt'])
                                    assert process['State']['StartedAt']!=before['State']['StartedAt']
                                else:
                                    process=wait_state(name,lambda row:not row['State']['Running']);assert process['State']['ExitCode']==0
                                    _run(['docker','start',name])  # Fixture recovery only, not product host-start qualification.
                                _wait_until_ready('mysql',name,90)
                                observer=_root_connection('mysql',route['port']);observer.autocommit=True;query=observer.cursor()
                                try:
                                    query.execute('SELECT @@server_uuid');assert query.fetchone()==(uuid,)
                                    query.execute('SELECT COUNT(*),SUM(id) FROM sr_control.committed');assert query.fetchone()==(1,1)
                                    query.execute('SELECT COUNT(*) FROM sr_control.pending');assert query.fetchone()==(0,)
                                finally:query.close();observer.close()
                                checks.append({'operation':operation,'native_request_acknowledged':True,
                                    'separate_owned_process_observation':'new-supervised-process' if operation=='restart_server' else 'native-exit0',
                                    'native_uuid_and_committed_rows_preserved':True,'native_pending_transaction_rolled_back_on_server_stop':True})
                            finally:client._safe_close(cursor);client._forget_and_close(source)
                    expected='CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection';assert classes and set(classes)=={expected}
                    proof['interfaces'].append({'use_pure':pure,'native_connection_class':expected,'templates':templates,'checks':checks})
                finally:client.close()
            if application:proof['application']=workspace(app,route,name,uuid,target)
        proof['owned_server_stopped']=owned['owned_server_stopped'];proof['owned_container_removed']=owned['owned_container_removed'];proof['complete']=True
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    parser.add_argument('--application',action='store_true')
    args=parser.parse_args();value=qualify(args.output,args.application);print(json.dumps({'complete':value['complete'],'interfaces':len(value['interfaces'])}))

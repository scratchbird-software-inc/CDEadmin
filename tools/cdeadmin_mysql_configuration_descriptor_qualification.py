"""Owned native/API qualification of typed configuration and replication inputs."""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import secrets
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output,application_only=False):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep native evidence outside source')
    output.mkdir(parents=True,exist_ok=False);app=setup_application(output)
    from mysql_qualification_support import server,_root_connection
    from cdeadmin_mysql_family_object_live_orchestrator import _run
    from cdeadmin_mysql_server_operations_qualification import qualify as variables
    from cdeadmin_mysql_resource_group_qualification import qualify as groups
    from cdeadmin_mysql_replication_qualification import qualify as replication
    from cdeadmin_mysql_online_ddl_qualification import registration
    from pgadmin.cdeadmin.providers.mysql_family.provider import _resources,MYSQL_PROFILE
    from pgadmin.cdeadmin.providers import mysql_replication
    from pgadmin.cdeadmin.providers.mysql_tablespaces import identifier
    from ui_descriptor_roundtrip import backend_draft,engine_operations,operation_draft
    import mysql.connector
    paths=['web/pgadmin/cdeadmin/ui_descriptors/mysql/operations.json',
           'web/pgadmin/cdeadmin/providers/mysql_descriptor_contract.py',
           'web/pgadmin/cdeadmin/providers/mysql_family/provider.py',
           'web/pgadmin/cdeadmin/visual_admin/provider.py',str(Path(__file__).relative_to(ROOT))]
    proof={'complete':False,'native_interfaces':[],'application':[],
           'application_only':application_only,
           'actual_operation_dialog_qualified':False,'history_testing':'ScratchBird history not run',
           'source_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}}
    network='sr-config-'+secrets.token_hex(8);network_created=False;owned=[]
    declarations=engine_operations('mysql')
    try:
        _run(['docker','network','create',network]);network_created=True
        with ExitStack() as stack:
            origin,origin_name,origin_proof=stack.enter_context(server(output/'source',network=network,server_id=301));owned.append(origin_proof)
            replica,_,replica_proof=stack.enter_context(server(output/'replica',network=network,server_id=302));owned.append(replica_proof)
            for pure in (() if application_only else (True,False)):
                options=lambda route:{'host':route['host'],'port':route['port'],'user':'root','use_pure':pure}
                probe=mysql.connector.connect(**options(replica));native_class=type(probe).__name__;probe.close()
                assert native_class==('MySQLConnection' if pure else 'CMySQLConnection')
                variables(options(replica),output/('variables-'+str(pure)),descriptor_inputs=True)
                groups(options(replica),output/('groups-'+str(pure)),descriptor_inputs=True)
                replication(options(origin),options(replica),origin_name,output/('replication-'+str(pure)),descriptor_inputs=True)
                proof['native_interfaces'].append({'use_pure':pure,'native_connection_class':native_class,'variables_sessions_resource_groups_and_native_replication':True})
            oracle=_root_connection('mysql',replica['port']);oracle.autocommit=True;q=oracle.cursor()
            source=_root_connection('mysql',origin['port']);source.autocommit=True;s=source.cursor()
            try:
                q.execute('CREATE DATABASE sr_osc');q.execute('CREATE TABLE sr_osc.pending(id INT PRIMARY KEY)')
                password=secrets.token_urlsafe(24);q.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s',(password,))
                q.execute('SELECT @@GLOBAL.init_connect,@@GLOBAL.local_infile,@@GLOBAL.max_execution_time,@@GLOBAL.long_query_time');original=q.fetchone()
                q.execute("INSTALL COMPONENT 'file://component_mysqlbackup'")
                q.execute('SELECT @@GLOBAL.`mysqlbackup.backupid`');default_backup_id=q.fetchone()[0]
                for pure in (True,False):
                    _,_,post=registration(app,replica,password,not pure);checks=[]
                    def target(kind,name):
                        rows=_resources(oracle,{'route':{**replica,'database':'sr_osc'}},MYSQL_PROFILE)
                        matches=[row for row in rows if row['resource_kind']==kind and
                            (row['native'].get('processlist_id')==name if kind=='session' else row['native'].get('channel_name')==name if kind=='replication-channel' else row['display_name']==name)]
                        assert len(matches)==1,(kind,name,[row.get('native',{}).get('channel_name',row['display_name']) for row in rows if row['resource_kind']==kind])
                        return matches[0]
                    def run(kind,operation,values=None,resource=None):
                        declaration=declarations[operation+'@'+kind]
                        draft=backend_draft({'tabs':[{'fields':declaration['fields']}]},operation_draft(declaration,values,resource['display_name']))
                        payload={'resource_kind':kind,'operation_id':operation,'target_resource':resource,'draft':draft}
                        oracle.autocommit=False;q.execute('SAVEPOINT descriptor_guard');q.execute('INSERT INTO sr_osc.pending VALUES(1)')
                        checked=post('visual_admin_validate',payload);assert checked['valid'],checked['errors']
                        planned=post('visual_admin_plan',payload);assert planned['state']=='ready' and planned['execution_available']
                        apply={key:planned[key] for key in ('plan_id','plan_digest')}|{'confirmed':True}
                        result=post('visual_admin_apply',apply);assert result['provider_result']['accepted']
                        replay=post.raw('visual_admin_apply',apply);assert replay.status_code!=200 or not replay.get_json().get('success')
                        q.execute('SELECT ROW_COUNT()');assert q.fetchone()==(1,)
                        q.execute('ROLLBACK TO SAVEPOINT descriptor_guard');oracle.rollback();oracle.autocommit=True
                        checks.append(kind+'.'+operation)
                        print('API',kind,operation,'use_pure='+str(pure),flush=True)
                        return result
                    text="SET @owned_typed='quote 雪'"
                    run('system-variable','set_global',{'value_type':'TEXT','value_text':text},target('system-variable','init_connect'))
                    q.execute('SELECT @@GLOBAL.init_connect');assert q.fetchone()==(text,)
                    for value in (True,False):
                        run('system-variable','set_global',{'value_type':'BOOLEAN','value_boolean':value},target('system-variable','local_infile'))
                        q.execute('SELECT @@GLOBAL.local_infile');assert q.fetchone()[0]==int(value)
                    run('system-variable','set_global',{'value_type':'SAFE_INTEGER','value_integer':123},target('system-variable','max_execution_time'))
                    q.execute('SELECT @@GLOBAL.max_execution_time');assert q.fetchone()==(123,)
                    for operation,value in [('set_persist_only','234'),('set_persist','345')]:
                        run('system-variable',operation,{'value_type':'INTEGER','value_text':value},target('system-variable','max_execution_time'))
                        q.execute('SELECT @@GLOBAL.max_execution_time');assert q.fetchone()[0]==(123 if operation=='set_persist_only' else 345)
                        q.execute("SELECT VARIABLE_VALUE FROM performance_schema.persisted_variables WHERE VARIABLE_NAME='max_execution_time'");assert q.fetchone()==(value,)
                    run('system-variable','reset_persist',resource=target('system-variable','max_execution_time'))
                    q.execute("SELECT COUNT(*) FROM performance_schema.persisted_variables WHERE VARIABLE_NAME='max_execution_time'");assert q.fetchone()==(0,)
                    for representation,value in [('DECIMAL','0.125'),('DOUBLE','2.5e-1')]:
                        run('system-variable','set_global',{'value_type':representation,'value_text':value},target('system-variable','long_query_time'))
                        q.execute('SELECT @@GLOBAL.long_query_time');assert q.fetchone()[0]==(0.125 if representation=='DECIMAL' else 0.25)
                    run('system-variable','set_global',{'value_type':'TEXT','value_text':'12345'},target('system-variable','mysqlbackup.backupid'))
                    q.execute('SELECT @@GLOBAL.`mysqlbackup.backupid`');assert q.fetchone()==('12345',)
                    run('system-variable','set_global',{'value_mode':'NULL','value_type':'BOOLEAN'},target('system-variable','mysqlbackup.backupid'))
                    q.execute('SELECT @@GLOBAL.`mysqlbackup.backupid`');assert q.fetchone()==(None,)
                    run('system-variable','set_global',{'value_mode':'DEFAULT'},target('system-variable','mysqlbackup.backupid'))
                    q.execute('SELECT @@GLOBAL.`mysqlbackup.backupid`');assert q.fetchone()==(default_backup_id,)
                    worker=mysql.connector.connect(host=replica['host'],port=replica['port'],user='root',password=password,use_pure=pure,autocommit=True)
                    cursor=worker.cursor();cursor.execute('SELECT CONNECTION_ID()');process=str(cursor.fetchone()[0]);cursor.execute('SELECT THREAD_ID FROM performance_schema.threads WHERE PROCESSLIST_ID=CONNECTION_ID()');thread=str(cursor.fetchone()[0])
                    group='sr_typed_group_'+str(pure);q.execute('CREATE RESOURCE GROUP '+identifier(group)+' TYPE=USER ENABLE')
                    job=None
                    try:
                        run('resource-group','assign',{'thread_ids':[{'value':thread}]},target('resource-group',group))
                        q.execute('SELECT RESOURCE_GROUP FROM performance_schema.threads WHERE THREAD_ID=%s',(thread,));assert q.fetchone()==(group,)
                        errors=[]
                        def sleep():
                            try:cursor.execute('SELECT 1+SLEEP(20)');cursor.fetchall()
                            except mysql.connector.Error as error:errors.append(error.errno)
                        job=threading.Thread(target=sleep);job.start()
                        until(lambda:query_state(q,process)=='User sleep')
                        run('session','terminate_query',resource=target('session',process));job.join(5);assert not job.is_alive()
                        assert not errors or errors==[1317]
                        cursor.execute('SELECT CONNECTION_ID()');assert str(cursor.fetchone()[0])==process
                        run('session','terminate_connection',resource=target('session',process))
                        try:cursor.execute('SELECT 1')
                        except mysql.connector.Error:pass
                        else:raise AssertionError('Killed owned attachment remained usable')
                    finally:
                        worker.close()
                        if job is not None:job.join(5)
                        q.execute('DROP RESOURCE GROUP '+identifier(group)+' FORCE')
                    database='sr_typed_rx_'+str(pure);channel='typed . 雪 '+str(pure);user='sr_typed_reader_'+str(pure);secret=secrets.token_urlsafe(18)
                    s.execute('CREATE USER '+identifier(user)+"@'%' IDENTIFIED BY %s",(secret,));s.execute('GRANT REPLICATION SLAVE ON *.* TO '+identifier(user)+"@'%'")
                    s.execute('CREATE DATABASE '+identifier(database))
                    for table in ('t','ignored'):s.execute('CREATE TABLE '+identifier(database)+'.'+table+'(id INT PRIMARY KEY)');s.execute('INSERT INTO '+identifier(database)+'.'+table+' VALUES(1)')
                    setup=mysql_replication.compile_operation('create',{'name':channel,'source_options':{'SOURCE_HOST':origin_name,'SOURCE_PORT':3306,'SOURCE_USER':user,'SOURCE_AUTO_POSITION':True,'SOURCE_SSL':True},'source_password':secret},None)
                    q.execute(setup['source'],setup['parameters'])
                    q.execute('SELECT CHANNEL_NAME FROM performance_schema.replication_connection_configuration WHERE CHANNEL_NAME=%s',(channel,))
                    observed=q.fetchone();assert observed is not None
                    channel=observed[0]
                    run('replication-channel','start',resource=target('replication-channel',channel))
                    until(lambda:count(q,database,'t')==1)
                    run('replication-channel','stop',{'thread':'SQL_THREAD'},target('replication-channel',channel))
                    values={}
                    for key,rows in {'REPLICATE_DO_DB':[{'value':database}],'REPLICATE_IGNORE_DB':[],
                                     'REPLICATE_DO_TABLE':[{'database':database,'table':'t'}],
                                     'REPLICATE_IGNORE_TABLE':[{'database':database,'table':'ignored'}],
                                     'REPLICATE_WILD_DO_TABLE':[],'REPLICATE_WILD_IGNORE_TABLE':[{'value':database+'.ignored'}],
                                     'REPLICATE_REWRITE_DB':[{'source':'sr_unused_source','target':'sr_unused_target'}]}.items():
                        values['edit_'+key.lower()]=True;values[key.lower()]=rows
                    run('replication-channel','filter',values,target('replication-channel',channel))
                    for table in ('t','ignored'):s.execute('INSERT INTO '+identifier(database)+'.'+table+' VALUES(2)')
                    run('replication-channel','start',{'thread':'SQL_THREAD'},target('replication-channel',channel))
                    until(lambda:count(q,database,'t')==2);assert count(q,database,'ignored')==1
                    run('replication-channel','stop',resource=target('replication-channel',channel))
                    s.execute('INSERT INTO '+identifier(database)+'.t VALUES(3)');s.execute('SELECT @@GLOBAL.gtid_executed');position=s.fetchone()[0]
                    run('replication-channel','start',{'thread':'SQL_THREAD','until_kind':'SQL_AFTER_GTIDS','sql_after_gtids':position},target('replication-channel',channel))
                    run('replication-channel','start',{'thread':'IO_THREAD'},target('replication-channel',channel))
                    until(lambda:count(q,database,'t')==3)
                    run('replication-channel','stop',resource=target('replication-channel',channel))
                    run('replication-channel','reset',resource=target('replication-channel',channel))
                    q.execute('SELECT HOST FROM performance_schema.replication_connection_configuration WHERE CHANNEL_NAME=%s',(channel,));assert q.fetchone()==(origin_name,)
                    run('replication-channel','start',resource=target('replication-channel',channel))
                    s.execute('INSERT INTO '+identifier(database)+'.t VALUES(4)');until(lambda:count(q,database,'t')==4)
                    run('replication-channel','stop',resource=target('replication-channel',channel))
                    run('replication-channel','reset',{'delete_connection':True},target('replication-channel',channel))
                    q.execute('SELECT COUNT(*) FROM performance_schema.replication_connection_configuration WHERE CHANNEL_NAME=%s',(channel,));assert q.fetchone()==(0,)
                    assert count(q,database,'t')==4
                    proof['application'].append({'use_pure':pure,'operations':checks,'all_six_scalar_inputs_observed':True,
                        'native_persist_only_and_reset_semantics':True,'native_thread_assignment_and_owned_kill_effects':True,
                        'typed_filter_delivery_and_gtid_until':True,'reset_retains_source_and_data':True,
                        'diagnostics_and_savepoint_preserved':True,'consumed_plans_refused':True})
                    s.execute('DROP DATABASE IF EXISTS '+identifier(database));s.execute('DROP USER IF EXISTS '+identifier(user)+"@'%'")
                    q.execute('DROP DATABASE IF EXISTS '+identifier(database));q.execute('DROP USER IF EXISTS '+identifier(user)+"@'%'")
                for name,value in zip(['init_connect','local_infile','max_execution_time','long_query_time'],original):q.execute('SET GLOBAL '+name+'=%s',(value,))
                proof['complete']=True
            finally:q.close();s.close();oracle.close();source.close()
    finally:
        proof['owned_servers_stopped']=len(owned)==2 and all(row['owned_server_stopped'] for row in owned)
        proof['owned_network_removed']=not network_created or _run(['docker','network','rm',network],check=False).returncode==0
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


def until(predicate):
    deadline=time.monotonic()+45
    while time.monotonic()<deadline:
        if predicate():return
        time.sleep(.05)
    raise AssertionError('Owned native state did not converge')


def count(cursor,database,table):
    try:cursor.execute('SELECT COUNT(*) FROM `'+database+'`.'+table);return cursor.fetchone()[0]
    except Exception as error:
        if getattr(error,'errno',None) in {1049,1146}:return None
        raise


def query_state(cursor,process):
    cursor.execute('SELECT PROCESSLIST_STATE FROM performance_schema.threads WHERE PROCESSLIST_ID=%s',(process,));row=cursor.fetchone();return row[0] if row else None


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    parser.add_argument('--application-only',action='store_true');args=parser.parse_args()
    result=qualify(args.output,args.application_only);print(json.dumps({'complete':result['complete'],'interfaces':len(result['native_interfaces'])}))

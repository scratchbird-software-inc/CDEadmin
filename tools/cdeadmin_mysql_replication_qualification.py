"""Qualify native channel plans with two separately owned MySQL instances."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'web'))
import config  # noqa: F401
import mysql.connector
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION,MYSQL_PROFILE,_resources
from pgadmin.cdeadmin.providers.mysql_tablespaces import identifier


def qualify(source_options,replica_options,source_host,output,descriptor_inputs=False):
    output.mkdir(parents=True,exist_ok=True)
    source=mysql.connector.connect(**{**source_options,'autocommit':True});replica=mysql.connector.connect(**{**replica_options,'autocommit':True})
    sc=source.cursor();rc=replica.cursor();token=secrets.token_hex(6);database='sr_repl_'+token;user='sr_repl_'+token;password=secrets.token_urlsafe(18);channel='sr_channel_'+token+'é'
    proof={'passed':False,'statements':{},'checks':[]};created=False;default_created=False
    root=Path(__file__).resolve().parents[1]
    proof.update(descriptor_inputs=descriptor_inputs,actual_operation_dialog_qualified=False,
        source_sha256={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in (
            'web/pgadmin/cdeadmin/providers/mysql_replication.py',
            'web/pgadmin/cdeadmin/ui_descriptors/mysql/operations.json',
            str(Path(__file__).relative_to(root)))})
    if descriptor_inputs:
        from ui_descriptor_roundtrip import backend_draft,engine_operations,operation_draft
        declarations=engine_operations('mysql')
    def execute(operation,draft=None,selected=channel):
        target={'display_name':selected or 'Default channel','native':{'channel_name':selected}}
        if descriptor_inputs and operation not in {'create','alter'}:
            declaration=declarations[operation+'@replication-channel'];values=dict(draft or {})
            if operation=='start' and values.get('until'):
                until=values.pop('until');key=next(iter(until));family=key.split('_LOG_')[0] if '_LOG_' in key else key
                values['until_kind']=family
                for name,value in until.items():
                    name='after_mts_gaps' if name=='SQL_AFTER_MTS_GAPS' else name.lower().replace('_log_','_')
                    values[name]=str(value) if name.endswith('_pos') else value
            if operation=='filter':
                for key,rows in values.pop('filters').items():
                    values['edit_'+key.lower()]=True
                    names=('source','target') if key=='REPLICATE_REWRITE_DB' else ('database','table') if key in {'REPLICATE_DO_TABLE','REPLICATE_IGNORE_TABLE'} else None
                    values[key.lower()]=[dict(zip(names,row)) if names else {'value':row} for row in rows]
            draft=backend_draft({'tabs':[{'fields':declaration['fields']}]},operation_draft(declaration,values,target['display_name']))
        request={'resource_kind':'replication-channel','operation_id':operation,'draft':draft or {},'target_resource':target,'_provider_route':{'host':replica_options.get('host','localhost')}}
        assert not MYSQL_ADMINISTRATION.validate(request)['errors']
        statement=MYSQL_ADMINISTRATION._compile(request)['statements'][0]
        rc.execute(statement['source'],statement['parameters'] or None)
        from tools.mysql_task_evidence import record
        record(proof, request)
        if rc.description:rc.fetchall()
        proof['statements'].setdefault(operation,statement['source'])
    def count():
        try:rc.execute('SELECT COUNT(*) FROM '+identifier(database)+'.t');return rc.fetchone()[0]
        except mysql.connector.Error as error:
            if error.errno in {1049,1146}:return None
            raise
    def wait_count(expected):
        for attempt in range(300):
            if count()==expected:return
            time.sleep(0.05)
        rc.execute('SELECT LAST_ERROR_NUMBER FROM performance_schema.replication_connection_status WHERE CHANNEL_NAME=%s',(channel,));receiver=rc.fetchall()
        rc.execute('SELECT LAST_ERROR_NUMBER FROM performance_schema.replication_applier_status_by_worker WHERE CHANNEL_NAME=%s',(channel,));workers=rc.fetchall()
        raise AssertionError('Native replication delivery timed out; receiver/worker codes '+str((receiver,workers)))
    def state(thread):
        table='replication_connection_status' if thread=='IO_THREAD' else 'replication_applier_status'
        rc.execute('SELECT SERVICE_STATE FROM performance_schema.'+table+' WHERE CHANNEL_NAME=%s',(channel,));return rc.fetchone()[0]
    try:
        for cursor in (sc,rc):
            cursor.execute('SELECT VERSION(),@@server_uuid,@@gtid_mode');row=cursor.fetchone();assert str(row[0]).split('-')[0]=='9.7.0' and row[2]=='ON'
        sc.execute('CREATE USER '+identifier(user)+"@'%' IDENTIFIED BY %s",(password,));sc.execute('GRANT REPLICATION SLAVE ON *.* TO '+identifier(user)+"@'%'")
        sc.execute('CREATE DATABASE '+identifier(database));sc.execute('CREATE TABLE '+identifier(database)+'.t(id int PRIMARY KEY) ENGINE=InnoDB');sc.execute('INSERT INTO '+identifier(database)+'.t VALUES (1)')
        execute('create',{'name':channel,'source_options':{'SOURCE_HOST':source_host,'SOURCE_PORT':3306,'SOURCE_USER':user,'SOURCE_AUTO_POSITION':True,'SOURCE_SSL':True,'SOURCE_CONNECT_RETRY':1},'source_password':password});created=True
        execute('start');wait_count(1);assert state('IO_THREAD')=='ON' and state('SQL_THREAD')=='ON'
        sc.execute("SELECT s.VARIABLE_VALUE FROM performance_schema.status_by_thread s JOIN performance_schema.threads t ON t.THREAD_ID=s.THREAD_ID WHERE t.PROCESSLIST_USER=%s AND s.VARIABLE_NAME='Ssl_cipher'",(user,))
        ciphers=[row[0] for row in sc.fetchall()];assert ciphers and all(ciphers)
        proof['native_replication_tls_ciphers']=ciphers
        discovered=_resources(replica,{'route':{}},MYSQL_PROFILE)
        observed=next(row['native'] for row in discovered if row['resource_kind']=='replication-channel' and row['native'].get('channel_name')==channel)
        assert observed['channel_name']==channel and observed['receiver']['service_state']=='ON' and observed['applier']['service_state']=='ON'
        assert password not in json.dumps(discovered,default=str)
        execute('stop',{'thread':'SQL_THREAD'});assert state('SQL_THREAD')=='OFF' and state('IO_THREAD')=='ON'
        execute('filter',{'filters':{'REPLICATE_DO_DB':[database],'REPLICATE_IGNORE_DB':[], 'REPLICATE_DO_TABLE':[], 'REPLICATE_IGNORE_TABLE':[], 'REPLICATE_WILD_DO_TABLE':[], 'REPLICATE_WILD_IGNORE_TABLE':['sr_excluded.%'], 'REPLICATE_REWRITE_DB':[['sr_unused_source','sr_unused_target']]}})
        sc.execute('INSERT INTO '+identifier(database)+'.t VALUES (2)');time.sleep(0.1);assert count()==1
        execute('start',{'thread':'SQL_THREAD'});wait_count(2)
        execute('stop');assert state('IO_THREAD')=='OFF' and state('SQL_THREAD')=='OFF'
        execute('alter',{'source_options':{'SOURCE_CONNECT_RETRY':3,'SOURCE_HEARTBEAT_PERIOD':0.5}})
        replica.sql_mode='NO_BACKSLASH_ESCAPES,ANSI_QUOTES'
        execute('reset',{'delete_connection':False})
        rc.execute('SELECT HOST FROM performance_schema.replication_connection_configuration WHERE CHANNEL_NAME=%s',(channel,));assert rc.fetchone()==(source_host,)
        execute('start');sc.execute('INSERT INTO '+identifier(database)+'.t VALUES (3)');wait_count(3)
        execute('stop')
        sc.execute('INSERT INTO '+identifier(database)+'.t VALUES (4)');sc.execute('SELECT @@global.gtid_executed');position=sc.fetchone()[0]
        execute('start',{'thread':'SQL_THREAD','until':{'SQL_AFTER_GTIDS':position}});execute('start',{'thread':'IO_THREAD'});wait_count(4)
        for attempt in range(200):
            if state('SQL_THREAD')=='OFF':break
            time.sleep(0.05)
        assert state('SQL_THREAD')=='OFF'
        execute('stop');execute('reset',{'delete_connection':True});created=False
        rc.execute('SELECT COUNT(*) FROM performance_schema.replication_connection_configuration WHERE CHANNEL_NAME=%s',(channel,));assert rc.fetchone()[0]==0
        execute('create',{'name':'','source_options':{'SOURCE_HOST':source_host,'SOURCE_PORT':3306,'SOURCE_AUTO_POSITION':True}},selected='');default_created=True
        defaults=[row for row in _resources(replica,{'route':{}},MYSQL_PROFILE) if row['resource_kind']=='replication-channel' and row['native'].get('channel_name')=='']
        assert len(defaults)==1 and defaults[0]['display_name']=='Default channel' and all(defaults[0]['display_path'])
        execute('reset',{'delete_connection':True},selected='');default_created=False
        proof.update(passed=True,checks=['native generated channel create/alter/start/stop/reset/filter plans','two independent MySQL 9.7 instances and GTID delivery','bound Unicode channel identity and redacted credentials','TLS-enabled native source connection','separate receiver/applier state and dedicated catalog rediscovery','SQL-thread pause retains received changes and resumes application','native per-channel database filter','RESET preserves configured source and resumes without duplicate primary-key effects','native SQL_AFTER_GTIDS stops the applier at delivered position','RESET ALL removes only the owned channel','native default channel has a visible nonempty presentation and exact empty channel binding','default and ANSI_QUOTES/NO_BACKSLASH_ESCAPES'])
    finally:
        if default_created:
            execute('stop',selected='');execute('reset',{'delete_connection':True},selected='')
        if created:
            execute('stop');execute('reset',{'delete_connection':True})
        sc.execute('DROP DATABASE IF EXISTS '+identifier(database));sc.execute('DROP USER IF EXISTS '+identifier(user)+"@'%'")
        rc.execute('DROP DATABASE IF EXISTS '+identifier(database));rc.execute('DROP USER IF EXISTS '+identifier(user)+"@'%'")
        sc.close();rc.close();source.close();replica.close();proof['owned_channel_and_databases_removed']=True
        (output/'summary.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source-connection-json',type=Path,required=True);parser.add_argument('--replica-connection-json',type=Path,required=True);parser.add_argument('--source-host',required=True);parser.add_argument('--output-root',type=Path,required=True)
    parser.add_argument('--descriptor-inputs',action='store_true')
    args=parser.parse_args();qualify(json.loads(args.source_connection_json.read_text()),json.loads(args.replica_connection_json.read_text()),args.source_host,args.output_root,args.descriptor_inputs)

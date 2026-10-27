"""Native raw replay admission, transaction groups and independently read data."""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import sys
import threading
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]
import config  # noqa: E402,F401


def qualify(output,decoder,client_binary,*,gtid_mode='OFF',use_c=False):
    from mysql_qualification_support import server,_root_connection
    from cdeadmin_native_editor_gate import provider
    from pgadmin.cdeadmin.sdk.tooling import ProviderToolRunner
    from pgadmin.cdeadmin.providers.mysql_family import mysql_raw_binlog_archives as archive
    from pgadmin.cdeadmin.providers.mysql_family import mysql_raw_binlog_replay as native
    output=Path(output).resolve()
    if ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    proof={'complete':False,'checks':[],'failures':[],'gtid_mode':gtid_mode,'interface':'c' if use_c else 'pure','history_testing':'not run',
        'scope':'equivalent empty schema and explicit native GTID seed; not physical base recovery or production cutover',
        'source_sha256':{str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in [Path(__file__),
            ROOT/'web/pgadmin/cdeadmin/providers/mysql_family/mysql_raw_binlog_replay.py',ROOT/'web/pgadmin/cdeadmin/providers/mysql_family/mysql_raw_binlog_archives.py',
            ROOT/'web/pgadmin/cdeadmin/providers/mysql_family/provider.py']}}
    runner=ProviderToolRunner({'mysql-binlog':str(Path(decoder).resolve(strict=True)),'mysql-client':str(Path(client_binary).resolve(strict=True))})
    ddl=['CREATE DATABASE sr_raw_replay CHARACTER SET utf8mb4','CREATE TABLE sr_raw_replay.t(id BIGINT PRIMARY KEY,body TEXT,payload LONGBLOB)']
    password='native LF\nquote"slash\\雪-'+secrets.token_urlsafe(24)
    try:
        with ExitStack() as cleanup,server(output/'source-fixture',gtid_mode=gtid_mode) as (source_route,_source,source_proof):
            root=_root_connection('mysql',source_route['port']);cleanup.callback(root.close);root.autocommit=True;cursor=root.cursor();cleanup.callback(cursor.close)
            for sql in ddl:cursor.execute(sql)
            cursor.execute('SELECT @@global.gtid_executed');baseline=cursor.fetchone()[0]
            cursor.execute('FLUSH BINARY LOGS');cursor.execute('SHOW BINARY LOG STATUS');filename=cursor.fetchone()[0];cursor.fetchall();filenames=[filename]
            cursor.execute('SET SESSION binlog_transaction_compression=ON')
            for index in range(3):
                cursor.execute('INSERT INTO sr_raw_replay.t VALUES(%s,%s,%s)',(9007199254740993+index,'Unicode 雪😀 '+str(index),b'\x00\xff'+bytes([index])))
                if index==1:
                    cursor.execute('FLUSH BINARY LOGS');cursor.execute('SHOW BINARY LOG STATUS');filenames.append(cursor.fetchone()[0]);cursor.fetchall()
            cursor.execute('FLUSH BINARY LOGS')
            instance,route=provider('mysql',{**source_route,'use_pure':not use_c});cleanup.callback(instance.client.close);instance.client._tool_runner=runner
            connection=instance.client._connect({'route':route});captured=archive.capture(connection);selected=archive.options({'log_names':filenames})
            captured['state']['selected_logs']=archive.selected_logs(captured,selected)
            archive_dir=output/'archive-job';archive_dir.mkdir(mode=0o700)
            transport=archive.ArchiveTransport(instance.client,route,archive.delegate_credentials(instance.client,route),connection);cleanup.callback(transport.close)
            dumped=transport.execute({'program':archive.program_identity(instance.client,route,archive_dir),'source':captured['identity'],
                'source_state':captured['state'],'options':selected},archive_dir,threading.Event(),lambda _value:None)
            artifact=dumped['artifact'];archive_path=archive_dir/'archive';all_groups=native.inventory(archive_path)
            assert all_groups['total']==3 and all_groups['anonymous_groups_present'] is (gtid_mode=='OFF')
            assert all_groups['groups'][1]['file']!=all_groups['groups'][2]['file']
            proof['input_scope']={'closed_log_count':2,'transaction_compression':True,'group_count':3}
            group=all_groups['groups'][1]
            for mode,count in [('all',3),('before',1),('after',2)]:
                try:
                    with ExitStack() as target_cleanup,server(output/(mode+'-fixture'),gtid_mode=gtid_mode,server_id=102) as (target_route,_target,target_proof):
                        owner=_root_connection('mysql',target_route['port']);target_cleanup.callback(owner.close);owner.autocommit=True;query=owner.cursor();target_cleanup.callback(query.close)
                        query.execute('SET SESSION sql_log_bin=0')
                        for sql in ddl:query.execute(sql)
                        query.execute("CREATE USER 'sr_raw_replay'@'%' IDENTIFIED BY %s",(password,));query.execute("GRANT ALL PRIVILEGES ON *.* TO 'sr_raw_replay'@'%' WITH GRANT OPTION")
                        if baseline:query.execute('SET GLOBAL gtid_purged=%s',('+'+baseline,))
                        target_instance,target_native_route=provider('mysql',{**target_route,'user':'sr_raw_replay','use_pure':not use_c},password=password)
                        target_cleanup.callback(target_instance.client.close);client=target_instance.client;client._tool_runner=runner
                        target_connection=client._connect({'route':target_native_route});target_cleanup.callback(target_connection.close)
                        observed_target=native.capture_target(target_connection)
                        selected=native.options({'target_confirmation':observed_target['identity']['server_uuid'],'stop_mode':mode,
                            **({'stop_file':group['file'],'stop_position':group['position']} if mode!='all' else {})})
                        observed=native.inventory(archive_path,selected=selected)
                        work=output/('job-'+mode);work.mkdir(mode=0o700);shutil.copytree(archive_path,work/'input')
                        program=native.program_identity(client,target_native_route,work)
                        previous=native.previous_gtids(client,target_native_route,work/'input',observed,work,program)
                        assert previous==baseline,(previous,baseline)
                        admitted=native.admission(target_connection,artifact,observed,previous,selected)
                        if mode=='all':
                            for probe in ('held-lock','changed-position'):
                                probe_dir=output/probe;probe_dir.mkdir(mode=0o700);shutil.copytree(archive_path,probe_dir/'input')
                                if probe=='held-lock':
                                    query.execute('SELECT GET_LOCK(%s,0)',(native.lock_name(admitted['identity']),));assert query.fetchone()[0]==1
                                else:
                                    query.execute('SET SESSION sql_log_bin=1');query.execute('CREATE DATABASE sr_raw_changed');query.execute('SET SESSION sql_log_bin=0')
                                credentials=native.delegate_credentials(client,target_native_route)
                                try:refused=native.run_load(client,target_native_route,credentials,probe_dir/'input',admitted['identity'],admitted['state'],selected,observed,probe_dir,program)
                                finally:
                                    credentials.close()
                                    if probe=='held-lock':query.execute('SELECT RELEASE_LOCK(%s)',(native.lock_name(admitted['identity']),));query.fetchall()
                                assert refused['control'] and refused['control']['native_load_invoked'] is False and refused['tool']['return_code']!=0,refused
                                query.execute('SELECT COUNT(*) FROM sr_raw_replay.t');assert query.fetchone()[0]==0
                                proof['checks'].append({'mode':gtid_mode,'name':probe+'-refuses-before-native-replay','native_diagnostics':refused['native_diagnostics']})
                            admitted=native.admission(target_connection,artifact,observed,previous,selected)
                        credentials=native.delegate_credentials(client,target_native_route)
                        try:loaded=native.run_load(client,target_native_route,credentials,work/'input',admitted['identity'],admitted['state'],selected,observed,work,program)
                        finally:credentials.close()
                        (output/(mode+'-tool.json')).write_text(json.dumps(loaded,indent=2)+'\n')
                        assert loaded['control'] and loaded['control']['native_load_returned'] and loaded['tool']['return_code']==0,loaded
                        query.execute('SELECT CAST(id AS CHAR),body,HEX(payload) FROM sr_raw_replay.t ORDER BY id')
                        assert query.fetchall()==[(str(9007199254740993+i),'Unicode 雪😀 '+str(i),'00FF'+f'{i:02X}') for i in range(count)]
                        proof['checks'].append({'mode':mode,'rows':count,'native_coverage':native.coverage(target_connection,admitted['identity'],admitted)})
                        if mode=='after':
                            resumed=native.options({'target_confirmation':admitted['identity']['server_uuid'],
                                **({'start_file':all_groups['groups'][2]['file'],'start_position':all_groups['groups'][2]['position']} if gtid_mode=='OFF' else {})});now=native.capture_target(target_connection)
                            resume=output/'resume';resume.mkdir(mode=0o700);shutil.copytree(archive_path,resume/'input');credentials=native.delegate_credentials(client,target_native_route)
                            try:result=native.run_load(client,target_native_route,credentials,resume/'input',now['identity'],now['state'],resumed,native.inventory(resume/'input',selected=resumed),resume,program)
                            finally:credentials.close()
                            assert result['control'] and result['control']['native_load_returned'] and result['tool']['return_code']==0,result
                            query.execute('SELECT COUNT(*) FROM sr_raw_replay.t');assert query.fetchone()[0]==3
                            proof['checks'].append({'name':'native-gtid-resume-skips-already-applied-transactions' if gtid_mode=='ON' else 'native-anonymous-resume-at-reviewed-group-boundary'})
                    assert target_proof['owned_server_stopped']
                except Exception as error:
                    proof['failures'].append({'mode':mode,'error_type':type(error).__name__});(output/(mode+'-failure.log')).write_text(traceback.format_exc())
        proof['owned_source_stopped']=source_proof['owned_server_stopped'];proof['complete']=not proof['failures'] and source_proof['owned_server_stopped']
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    if not proof['complete']:raise RuntimeError('Native raw replay failed; retained all mode failures')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--mysql-binlog',type=Path,required=True);parser.add_argument('--mysql-client',type=Path,required=True)
    parser.add_argument('--gtid-mode',choices=('ON','OFF'),default='OFF');parser.add_argument('--use-c',action='store_true');args=parser.parse_args()
    qualify(args.evidence,args.mysql_binlog,args.mysql_client,gtid_mode=args.gtid_mode,use_c=args.use_c)

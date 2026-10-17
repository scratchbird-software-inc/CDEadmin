"""Native9.7 archive replay controls; base provisioning/cutover are separate."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import threading
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]
import config  # noqa: E402,F401


def qualify(output,executable):
    from tools.mysql_qualification_support import server,_root_connection
    from tools.cdeadmin_native_editor_gate import provider
    from pgadmin.cdeadmin.sdk.tooling import ProviderToolRunner
    from pgadmin.cdeadmin.providers.mysql_family import mysql_binlog_archives as archive
    from pgadmin.cdeadmin.providers.mysql_family import mysql_binlog_replay as replay
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside application source')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    proof={'complete':False,'checks':[],'failures':[],'history_testing':'not run',
        'base_qualification':'equivalent empty user schema on independently initialized native servers, with explicit GTID seed; not a base recovery proof',
        'source_sha256':{str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in [ROOT/'web/pgadmin/cdeadmin/providers/mysql_family/mysql_binlog_replay.py',
                ROOT/'web/pgadmin/cdeadmin/providers/mysql_family/mysql_binlog_archives.py',Path(__file__)]}}
    runner=ProviderToolRunner({'mysql-shell':str(Path(executable).resolve(strict=True))})
    try:
        with server(output/'source-fixture') as (source_route,_name,owned_source):
            source_root=_root_connection('mysql',source_route['port']);source_root.autocommit=True;cursor=source_root.cursor()
            source_instance=None;source_connection=None
            ddl=['CREATE DATABASE sr_replay CHARACTER SET utf8mb4',
                'CREATE TABLE sr_replay.t(id BIGINT PRIMARY KEY,body TEXT,payload LONGBLOB)']
            try:
                for statement in ddl:cursor.execute(statement)
                cursor.execute('SELECT @@global.gtid_executed');baseline=cursor.fetchone()[0]
                cursor.execute('FLUSH BINARY LOGS');cursor.execute('SHOW BINARY LOG STATUS');start=cursor.fetchone();cursor.fetchall()
                gtids=[]
                for index in range(3):
                    cursor.execute('INSERT INTO sr_replay.t VALUES(%s,%s,%s)',(9007199254740993+index,'Unicode 😀 '+str(index),b'\x00\xff'+bytes([index])))
                    cursor.execute('SELECT GTID_SUBTRACT(@@global.gtid_executed,%s)',(baseline if not gtids else previous,));gtids.append(cursor.fetchone()[0])
                    cursor.execute('SELECT @@global.gtid_executed');previous=cursor.fetchone()[0]
                cursor.execute('FLUSH BINARY LOGS')
                source_instance,route=provider('mysql',source_route);source_instance.client._tool_runner=runner
                source_connection=source_instance.client._connect({'route':route});captured=archive.capture(source_connection)
                credentials=archive.delegate_credentials(source_instance.client,route)
                try:
                    dumped=archive.run_dump(source_instance.client,route,credentials,captured['identity'],archive.options({
                        'start_file':start[0],'start_position':str(start[1]),'compression':'zstd','threads':1}),output/'archive',output)
                finally:credentials.close()
                artifact=dumped['artifact'];proof['archive_source_uuid']=captured['identity']['server_uuid']
                for mode,count in [('all',3),('before',1),('after',2)]:
                    target_instance=target_connection=None
                    try:
                        with server(output/(mode+'-fixture'),server_id=102) as (target_route,_target,owned_target):
                            target_root=_root_connection('mysql',target_route['port']);target_root.autocommit=True;query=target_root.cursor()
                            try:
                                for statement in ddl:query.execute(statement)
                                query.execute('SET GLOBAL gtid_purged=%s',('+'+baseline,))
                                target_instance,target_native_route=provider('mysql',target_route);client=target_instance.client;client._tool_runner=runner
                                target_connection=client._connect({'route':target_native_route});target=replay.capture_target(target_connection)
                                selected=replay.options({'stop_mode':mode,'stop_gtid':None if mode=='all' else gtids[1],
                                    'target_confirmation':target['identity']['server_uuid']})
                                admitted=replay.admission(target_connection,artifact,selected)
                                if mode=='all':
                                    for probe in ('held-native-lock','changed-native-gtids'):
                                        probe_work=output/probe;probe_work.mkdir(mode=0o700)
                                        archive.stage_continuation(output/'archive',probe_work/'input',artifact,captured['identity'])
                                        probe_program=archive.program_identity(client,target_native_route,probe_work)
                                        if probe=='held-native-lock':
                                            query.execute('SELECT GET_LOCK(%s,0)',('cdeadmin:binlog-load:'+target['identity']['server_uuid'],));assert query.fetchone()[0]==1
                                        else:query.execute('CREATE DATABASE sr_replay_changed')
                                        credentials=archive.delegate_credentials(client,target_native_route)
                                        try:refused=replay.run_load(client,target_native_route,credentials,probe_work/'input',admitted['identity'],
                                            admitted['state']['gtid_executed'],selected,probe_work,probe_program,cancel=threading.Event())
                                        finally:
                                            credentials.close()
                                            if probe=='held-native-lock':
                                                query.execute('SELECT RELEASE_LOCK(%s)',('cdeadmin:binlog-load:'+target['identity']['server_uuid'],));assert query.fetchone()[0]==1
                                        assert refused['control']['native_load_invoked'] is False and refused['tool']['return_code']!=0,refused
                                        assert refused['tool']['process_observation']['cleanup_confirmed'] is True
                                        query.execute('SELECT COUNT(*) FROM sr_replay.t');assert query.fetchone()[0]==0
                                        proof['checks'].append({'name':probe+'-refuses-before-native-loader-dispatch','native_control':refused['control']})
                                    admitted=replay.admission(target_connection,artifact,selected)
                                work=output/('job-'+mode);work.mkdir(mode=0o700)
                                archive.stage_continuation(output/'archive',work/'input',artifact,captured['identity'])
                                program=archive.program_identity(client,target_native_route,work)
                                credentials=archive.delegate_credentials(client,target_native_route)
                                try:result=replay.run_load(client,target_native_route,credentials,work/'input',admitted['identity'],
                                    admitted['state']['gtid_executed'],selected,work,program,cancel=threading.Event())
                                finally:credentials.close()
                                (output/(mode+'-tool.json')).write_text(json.dumps(result,indent=2)+'\n')
                                assert result['control']['native_load_returned'] and result['tool']['return_code']==0,result
                                observed=replay.coverage(target_connection,artifact,selected,admitted)
                                assert observed['baseline_preserved']==1 and observed['only_archived_gtids_added'] and observed['target_identity_unchanged']
                                if mode=='all':assert observed['all_archive_gtids_present']==1
                                else:assert observed['stop_gtid_present'] is (mode=='after')
                                query.execute('SELECT CAST(id AS CHAR),body,HEX(payload) FROM sr_replay.t ORDER BY id');rows=query.fetchall()
                                assert rows==[(str(9007199254740993+index),'Unicode 😀 '+str(index),'00FF'+f'{index:02X}') for index in range(count)],rows
                                proof['checks'].append({'name':'native-'+mode+'-gtid-archive-replay','rows':count,'native_coverage':observed})
                            finally:
                                if target_connection is not None:target_connection.close();target_connection=None
                                if target_instance is not None:target_instance.client.close();target_instance=None
                                query.close();target_root.close()
                        assert owned_target['owned_server_stopped']
                    except Exception as error:
                        proof['failures'].append({'mode':mode,'error_type':type(error).__name__});(output/('failure-'+mode+'.log')).write_text(traceback.format_exc())
            finally:
                if source_connection is not None:source_connection.close()
                if source_instance is not None:source_instance.client.close()
                cursor.close();source_root.close()
        proof.update(owned_source_stopped=owned_source['owned_server_stopped'],complete=not proof['failures'] and owned_source['owned_server_stopped'])
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    if not proof['complete']:raise RuntimeError('Native replay qualification failed; retained every mode failure')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--mysql-shell',type=Path,required=True);args=parser.parse_args();qualify(args.evidence,args.mysql_shell)

"""Owned native12.2 MariaDB raw archive replay; no history or base-recovery claim."""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import sys
import threading
import traceback

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]
import config  # noqa: E402,F401


def qualify(output,decoder,client_binary):
    from mariadb_qualification_support import server
    from mysql_qualification_support import _root_connection
    from cdeadmin_native_editor_gate import provider
    from pgadmin.cdeadmin.sdk.tooling import ProviderToolRunner
    from pgadmin.cdeadmin.providers.mysql_family import mariadb_binlog_archives as archive
    from pgadmin.cdeadmin.providers.mysql_family import mariadb_binlog_replay as native
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False,mode=0o700)
    if ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    proof={'complete':False,'checks':[],'failures':[],'history_testing':'not run',
        'scope':'equivalent empty user schema and native GTID seed; not physical base recovery or production cutover',
        'source_sha256':{str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in [
            Path(__file__),ROOT/'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_binlog_replay.py',
            ROOT/'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_binlog_archives.py']}}
    runner=ProviderToolRunner({'mariadb-binlog':str(Path(decoder).resolve(strict=True)), 'mariadb-client':str(Path(client_binary).resolve(strict=True))})
    ddl=['CREATE DATABASE sr_replay CHARACTER SET utf8mb4','CREATE TABLE sr_replay.t(id BIGINT PRIMARY KEY,body TEXT,payload LONGBLOB)']
    try:
        with ExitStack() as cleanup,server(output/'source-fixture') as (source_route,_name,source_proof):
            root=_root_connection('mariadb',source_route['port']);cleanup.callback(root.close);root.autocommit=True
            cursor=root.cursor();cleanup.callback(cursor.close)
            for statement in ddl:cursor.execute(statement)
            cursor.execute('SELECT @@global.gtid_binlog_pos');baseline=cursor.fetchone()[0]
            cursor.execute('FLUSH BINARY LOGS');cursor.execute('SHOW MASTER STATUS');name=cursor.fetchone()[0];cursor.fetchall()
            gtids=[]
            for index in range(3):
                cursor.execute('INSERT INTO sr_replay.t VALUES(%s,%s,%s)',(9007199254740993+index,'Unicode 😀 '+str(index),b'\x00\xff'+bytes([index])))
                cursor.execute('SELECT @@global.gtid_binlog_pos');gtids.append(cursor.fetchone()[0])
            cursor.execute('FLUSH BINARY LOGS')
            instance,route=provider('mariadb',source_route);cleanup.callback(instance.client.close);instance.client._tool_runner=runner
            connection=instance.client._connect({'route':route});cleanup.callback(connection.close)
            captured=archive.capture(connection);selected=archive.options({'log_names':[name]})
            captured['state']['selected_logs']=archive.selected_logs(captured,selected)
            archive_directory=output/'archive-job';archive_directory.mkdir(mode=0o700)
            program=archive.program_identity(instance.client,route,archive_directory)
            transport=archive.ArchiveTransport(instance.client,route,archive.delegate_credentials(instance.client,route),connection)
            result=transport.execute({'program':program,'source':captured['identity'],'source_state':captured['state'],'options':selected},archive_directory,threading.Event(),lambda _value:None)
            artifact=result['artifact'];archive_path=archive_directory/'archive'
            for mode,expected in [('all',3),('before',1),('after',2)]:
                try:
                    with ExitStack() as target_cleanup,server(output/(mode+'-fixture'),server_id=174) as (target_route,_target,target_proof):
                        target_root=_root_connection('mariadb',target_route['port']);target_cleanup.callback(target_root.close);target_root.autocommit=True
                        query=target_root.cursor();target_cleanup.callback(query.close)
                        query.execute('SET SESSION sql_log_bin=0')
                        for statement in ddl:query.execute(statement)
                        query.execute('SET GLOBAL gtid_slave_pos=%s',(baseline,))
                        target_instance,target_native_route=provider('mariadb',target_route);target_cleanup.callback(target_instance.client.close)
                        target_client=target_instance.client;target_client._tool_runner=runner
                        target_connection=target_client._connect({'route':target_native_route});target_cleanup.callback(target_connection.close)
                        target=native.capture_target(target_connection)
                        selected=native.options({'stop_mode':mode,'stop_gtid':None if mode=='all' else gtids[1],'target_confirmation':target['identity']['server_uid']})
                        observed=native.inventory(archive_path,artifact,wanted=target['state']['replay_gtid_pos'].split(','),stop=selected['stop_gtid'])
                        admitted=native.admission(target_connection,artifact,selected,observed)
                        if mode=='before':
                            zero_selected=native.options({'stop_mode':'before','stop_gtid':gtids[0],'target_confirmation':target['identity']['server_uid']})
                            zero_observed=native.inventory(archive_path,artifact,wanted=target['state']['replay_gtid_pos'].split(','),stop=gtids[0])
                            native.admission(target_connection,artifact,zero_selected,zero_observed)
                            work=output/'before-first';work.mkdir(mode=0o700);shutil_copy(archive_path,work/'input')
                            credentials=archive.delegate_credentials(target_client,target_native_route)
                            try:zero=native.run_load(target_client,target_native_route,credentials,work/'input',target['identity'],target['state'],zero_selected,zero_observed,work,native.program_identity(target_client,target_native_route,work))
                            finally:credentials.close()
                            assert zero['control']['native_load_returned'] and zero['tool']['return_code']==0,zero
                            query.execute('SELECT COUNT(*) FROM sr_replay.t');assert query.fetchone()[0]==0
                            assert native.capture_target(target_connection)==target
                            proof['checks'].append('native-stop-before-first-transaction-preserves-empty-target-and-all-gtid-stores')
                        if mode=='all':
                            query.execute('SELECT GET_LOCK(%s,0)',(native.lock_name(target['identity']),));assert query.fetchone()[0]==1
                            work=output/'held-lock';work.mkdir(mode=0o700);shutil_copy(archive_path,work/'input')
                            credentials=archive.delegate_credentials(target_client,target_native_route)
                            try:
                                refused=native.run_load(target_client,target_native_route,credentials,work/'input',target['identity'],target['state'],selected,observed,work,native.program_identity(target_client,target_native_route,work))
                                assert refused['control']['native_load_invoked'] is False and refused['tool']['return_code']!=0,refused
                            finally:
                                credentials.close();query.execute('SELECT RELEASE_LOCK(%s)',(native.lock_name(target['identity']),));query.fetchall()
                            query.execute('SELECT COUNT(*) FROM sr_replay.t');assert query.fetchone()[0]==0
                            proof['checks'].append('native-held-lock-refuses-before-archive-execution')
                        work=output/('job-'+mode);work.mkdir(mode=0o700);shutil_copy(archive_path,work/'input')
                        credentials=archive.delegate_credentials(target_client,target_native_route)
                        try:loaded=native.run_load(target_client,target_native_route,credentials,work/'input',target['identity'],target['state'],selected,observed,work,native.program_identity(target_client,target_native_route,work))
                        finally:credentials.close()
                        (output/(mode+'-tool.json')).write_text(json.dumps(loaded,indent=2)+'\n')
                        assert loaded['control']['native_load_returned'] and loaded['tool']['return_code']==0,loaded
                        query.execute('SELECT CAST(id AS CHAR),body,HEX(payload) FROM sr_replay.t ORDER BY id')
                        actual=query.fetchall();assert actual==[(str(9007199254740993+i),'Unicode 😀 '+str(i),'00FF'+f'{i:02X}') for i in range(expected)],actual
                        after=native.capture_target(target_connection)
                        assert after['state']['replay_gtid_pos']==gtids[expected-1],after
                        proof['checks'].append('native-'+mode+'-preserves-exact-wide-int-unicode-binary-and-gtid')
                        if mode=='all':
                            cursor.execute('SET GLOBAL log_bin_compress=1');cursor.execute('SET GLOBAL binlog_checksum=\'NONE\'')
                            cursor.execute('FLUSH BINARY LOGS');cursor.execute('SHOW MASTER STATUS');extra_name=cursor.fetchone()[0];cursor.fetchall()
                            cursor.execute('SET SESSION gtid_domain_id=7')
                            cursor.execute('INSERT INTO sr_replay.t VALUES(%s,%s,%s)',(9007199254740996,'Compressed Unicode 😀',b'\x00\xff'*65536))
                            cursor.execute('SET SESSION binlog_format=\'STATEMENT\'')
                            cursor.execute("SELECT '9007199254740997', 'Native LOAD 😀', 'load-bytes' INTO OUTFILE '/tmp/sr-owned-replay-load.csv'")
                            cursor.execute("LOAD DATA INFILE '/tmp/sr-owned-replay-load.csv' INTO TABLE sr_replay.t CHARACTER SET utf8mb4")
                            cursor.execute('FLUSH BINARY LOGS')
                            extra_capture=archive.capture(connection);extra_options=archive.options({'log_names':[extra_name]})
                            extra_capture['state']['selected_logs']=archive.selected_logs(extra_capture,extra_options)
                            extra_dir=output/'extra-archive-job';extra_dir.mkdir(mode=0o700)
                            extra_program=archive.program_identity(instance.client,route,extra_dir)
                            extra_result=transport.execute({'program':extra_program,'source':extra_capture['identity'],'source_state':extra_capture['state'],'options':extra_options},extra_dir,threading.Event(),lambda _value:None)
                            extra_artifact=extra_result['artifact'];extra_archive=extra_dir/'archive'
                            now=native.capture_target(target_connection);extra_selected=native.options({'target_confirmation':now['identity']['server_uid']})
                            extra_observed=native.inventory(extra_archive,extra_artifact,wanted=now['state']['replay_gtid_pos'].split(','))
                            native.admission(target_connection,extra_artifact,extra_selected,extra_observed)
                            work=output/'multi-domain-load';work.mkdir(mode=0o700);shutil_copy(extra_archive,work/'input')
                            credentials=archive.delegate_credentials(target_client,target_native_route)
                            try:extra_loaded=native.run_load(target_client,target_native_route,credentials,work/'input',now['identity'],now['state'],extra_selected,extra_observed,work,native.program_identity(target_client,target_native_route,work))
                            finally:credentials.close()
                            (output/'multi-domain-tool.json').write_text(json.dumps(extra_loaded,indent=2)+'\n')
                            assert extra_loaded['control']['native_load_returned'] and extra_loaded['tool']['return_code']==0,extra_loaded
                            query.execute('SELECT CAST(id AS CHAR),body,payload FROM sr_replay.t WHERE id>=9007199254740996 ORDER BY id')
                            assert query.fetchall()==[('9007199254740996','Compressed Unicode 😀',b'\x00\xff'*65536),('9007199254740997','Native LOAD 😀',b'load-bytes')]
                            assert native.capture_target(target_connection)['state']['replay_gtid_pos']==extra_observed['end_gtid_pos']
                            proof['checks'].append('native-multi-domain-compressed-checksum-disabled-and-statement-load-data-replay')
                            cursor.execute('SET SESSION gtid_domain_id=0');cursor.execute('SET SESSION binlog_format=\'ROW\'')
                            cursor.execute('SET GLOBAL log_bin_compress=0');cursor.execute('SET GLOBAL binlog_checksum=\'CRC32\'')
                        if mode=='after':
                            resume=native.options({'target_confirmation':target['identity']['server_uid']})
                            observed=native.inventory(archive_path,artifact,wanted=after['state']['replay_gtid_pos'].split(','));native.admission(target_connection,artifact,resume,observed)
                            work=output/'resume';work.mkdir(mode=0o700);shutil_copy(archive_path,work/'input')
                            credentials=archive.delegate_credentials(target_client,target_native_route)
                            try:loaded=native.run_load(target_client,target_native_route,credentials,work/'input',after['identity'],after['state'],resume,observed,work,native.program_identity(target_client,target_native_route,work))
                            finally:credentials.close()
                            assert loaded['control']['native_load_returned'] and loaded['tool']['return_code']==0,loaded
                            query.execute('SELECT COUNT(*) FROM sr_replay.t');assert query.fetchone()[0]==3
                            proof['checks'].append('native-fresh-resume-skips-already-present-transactions')
                    assert target_proof['owned_server_stopped']
                except Exception as error:
                    proof['failures'].append({'mode':mode,'error_type':type(error).__name__});(output/('failure-'+mode+'.log')).write_text(traceback.format_exc())
        proof.update(complete=not proof['failures'] and source_proof['owned_server_stopped'],owned_source_stopped=source_proof['owned_server_stopped'])
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    if not proof['complete']:raise RuntimeError('Native MariaDB replay failed; retained all mode failures')
    return proof


def shutil_copy(source,target):
    import shutil
    shutil.copytree(source,target)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--mariadb-binlog',type=Path,required=True);parser.add_argument('--mariadb-client',type=Path,required=True)
    args=parser.parse_args();qualify(args.evidence,args.mariadb_binlog,args.mariadb_client)

"""Owned MySQL9.7 Shell archive and continuation qualification; no history."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import sys
import time
import traceback
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]
import config  # noqa: F401,E402


def qualify(output,executable):
    from tools.mysql_qualification_support import server,_root_connection
    from tools.cdeadmin_native_editor_gate import provider
    from pgadmin.cdeadmin.sdk.tooling import ProviderToolRunner
    from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_archives import (
        capture,delegate_credentials,options,program_identity,verify)
    from pgadmin.cdeadmin.workspace.mysql_binlog_jobs import MySQLBinlogJobs
    from pgadmin.cdeadmin.workspace.mysql_binlog_service import ArchiveTransport
    output=Path(output).resolve();executable=Path(executable).resolve(strict=True)
    if output==ROOT or ROOT in output.parents:raise ValueError('Keep evidence outside source')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    paths=[path for path in (ROOT/'web/pgadmin/cdeadmin').rglob('*binlog*.py')]+[Path(__file__)]
    proof={'complete':False,'checks':[],'failures':[],'history_testing':'not run',
        'source_sha256':{str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}}
    jobs=MySQLBinlogJobs(output/'jobs.json',output/'archives');endpoint=str(uuid.uuid4());instance=None
    def check(name,callback):
        try:
            callback();proof['checks'].append({'name':name,'passed':True})
        except Exception as error:
            proof['failures'].append({'name':name,'error_type':type(error).__name__})
            (output/('failure-'+name+'.log')).write_text(traceback.format_exc())
    try:
        with server(output/'native-server') as (root_route,_name,owned):
            root=_root_connection('mysql',root_route['port']);root.autocommit=True
            cursor=root.cursor();connection=None
            try:
                database='sr_archive_'+secrets.token_hex(6)
                password='archive LF\n quote\" slash\\ '+secrets.token_hex(8)+' é雪'
                cursor.execute("CREATE USER 'sr_archive'@'%' IDENTIFIED BY %s",(password,))
                cursor.execute("GRANT ALL PRIVILEGES ON *.* TO 'sr_archive'@'%' WITH GRANT OPTION")
                cursor.execute('CREATE DATABASE `'+database+'`')
                cursor.execute('CREATE TABLE `'+database+'`.t(id INTEGER PRIMARY KEY,v TEXT)')
                cursor.execute('FLUSH BINARY LOGS')
                cursor.execute('SHOW BINARY LOG STATUS');start_row=cursor.fetchone();cursor.fetchall();start=start_row[0];partial_position=str(start_row[1])
                cursor.execute('INSERT INTO `'+database+'`.t VALUES(1,%s)',('native archive data é雪',))
                cursor.execute('FLUSH BINARY LOGS')
                instance,route=provider('mysql',{**root_route,'user':'sr_archive','ssl_mode':'REQUIRED'},password)
                client=instance.client;client._tool_runner=ProviderToolRunner({'mysql-shell':str(executable)})
                connection=client._connect({'route':route});captured=capture(connection)
                scope=jobs.prepare_scope(1,endpoint);program=program_identity(client,route,scope)
                current={'source':captured['identity'],'program':program,'configuration':'owned-native-fixture'}
                saved={}
                def archive(label,selected,since=None):
                    before=capture(connection)
                    continuation=None if since is None else {'job_id':since['job_id'],'artifact_digest':__import__('pgadmin.cdeadmin.workspace.mysql_binlog_jobs',fromlist=['digest']).digest(since['result']['artifact'])}
                    review=jobs.review(1,endpoint,options(selected),before,current['configuration'],program,continuation)
                    request={'job_id':review['job_id'],'review_digest':review['review_digest'],'confirmed':True}
                    previous=None if since is None else jobs.directory(since)/'archive'
                    transport=ArchiveTransport(client,route,delegate_credentials(client,route),scope,previous,continuation)
                    receipt=jobs.start(request,1,endpoint,current,transport)
                    deadline=time.monotonic()+90
                    while receipt['state'] in {'active','dispatching','cancel_requested'} and time.monotonic()<deadline:
                        time.sleep(.1);receipt=jobs.get(review['job_id'],1,endpoint)
                    (output/(label+'-receipt.json')).write_text(json.dumps(receipt,indent=2)+'\n')
                    assert receipt['state'] in {'completed','no_new_snapshot'},receipt
                    repeated=jobs.start(request,1,endpoint,{},None)
                    assert repeated['state']==receipt['state'] and repeated['started_at']==receipt['started_at']
                    saved[label]=jobs.load(review['job_id'],1,endpoint)
                    return saved[label]
                for compression in ('none','gzip','zstd'):
                    def run(compression=compression):
                        result=archive(compression,{'start_file':start,'compression':compression,'threads':1})
                        assert result['state']=='completed'
                        assert result['result']['artifact']['native_event_checksums_verified_where_present']
                        assert verify(jobs.directory(result)/'archive',captured['identity'])==result['result']['artifact']
                    check(compression+'-native-dump',run)
                check('native-midfile-position',lambda:archive('partial',{'start_file':start,'start_position':partial_position,'compression':'none','threads':1}))
                def continuation():
                    cursor.execute('INSERT INTO `'+database+'`.t VALUES(2,%s)',('continuation',));cursor.execute('FLUSH BINARY LOGS')
                    result=archive('continuation',{'since_job_id':saved['none']['job_id'],'compression':'zstd'},saved['none'])
                    assert result['state']=='completed'
                    assert result['result']['artifact']['start_from']==saved['none']['result']['artifact']['end_at']
                if 'none' in saved:check('native-continuation',continuation)
                if 'continuation' in saved:
                    check('empty-continuation',lambda:archive('empty',{'since_job_id':saved['continuation']['job_id'],'compression':'none'},saved['continuation']))
                def checksum_off():
                    cursor.execute("SET GLOBAL binlog_checksum='NONE'");cursor.execute('FLUSH BINARY LOGS')
                    cursor.execute('SHOW BINARY LOG STATUS');filename=cursor.fetchone()[0];cursor.fetchall()
                    cursor.execute('INSERT INTO `'+database+'`.t VALUES(3,%s)',('checksum off',));cursor.execute('FLUSH BINARY LOGS')
                    result=archive('checksum-off',{'start_file':filename,'compression':'none','threads':1})
                    assert all(item['checksum_algorithm']=='native_none' for item in result['result']['artifact']['event_integrity'])
                check('native-checksum-disabled',checksum_off)
                def corrupt():
                    original=jobs.directory(saved['none'])/'archive';copied=output/'corrupt';shutil.copytree(original,copied)
                    artifact=saved['none']['result']['artifact'];relative=next(row['path'] for row in artifact['files'] if not row['path'].endswith('.json'))
                    target=copied/relative;data=bytearray(target.read_bytes());data[-8]^=1;target.write_bytes(data)
                    from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_integrity import BinlogIntegrityError
                    try:verify(copied,captured['identity'])
                    except BinlogIntegrityError:pass
                    else:raise AssertionError('Corrupt native event was admitted')
                    target.write_bytes(data[:-3])
                    try:verify(copied,captured['identity'])
                    except ValueError:pass
                    else:raise AssertionError('Truncated native event was admitted')
                if 'none' in saved:check('corruption-and-truncation-refused',corrupt)
                def cancellation():
                    before=capture(connection)
                    review=jobs.review(1,endpoint,options({'start_file':start,'compression':'none'}),before,current['configuration'],program)
                    transport=ArchiveTransport(client,route,delegate_credentials(client,route),scope)
                    request={'job_id':review['job_id'],'review_digest':review['review_digest'],'confirmed':True}
                    jobs.start(request,1,endpoint,current,transport)
                    # Let version observation finish, then cancel the actual
                    # dump process while it is owned by the native runner.
                    pids=set();deadline=time.monotonic()+30
                    while time.monotonic()<deadline:
                        observed=jobs.get(review['job_id'],1,endpoint)
                        if observed.get('progress',{}).get('pid'):pids.add(observed['progress']['pid'])
                        if len(pids)>=2:break
                        time.sleep(.01)
                    assert len(pids)>=2
                    jobs.cancel(review['job_id'],1,endpoint);assert jobs.close()
                    cancelled=jobs.get(review['job_id'],1,endpoint)
                    (output/'cancelled-receipt.json').write_text(json.dumps(cancelled,indent=2)+'\n')
                    assert cancelled['state']=='cancelled' and cancelled['native_process_termination_confirmed'] is True
                    assert transport.credentials is None
                check('owned-native-process-cancellation-and-private-credential-cleanup',cancellation)
                proof['credential_delivery']='private JSON file; password includes newline, quote, backslash and Unicode'
            finally:
                if connection is not None:connection.close()
                if instance is not None:instance.client.close()
                cursor.close();root.close();jobs.close()
        proof.update(owned_server_stopped=owned['owned_server_stopped'],complete=not proof['failures'] and owned['owned_server_stopped'])
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    if not proof['complete']:raise RuntimeError('Native archive qualification failed; retained every case failure')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('--mysql-shell',type=Path,required=True);args=parser.parse_args();qualify(args.evidence,args.mysql_shell)

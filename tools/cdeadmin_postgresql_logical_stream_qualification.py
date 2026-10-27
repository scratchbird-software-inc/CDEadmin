#!/usr/bin/env python3
"""Compare owned PG18.3 native logical receivers with independent SQL slots."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',required=True,type=Path);parser.add_argument('--binary-path',default='/usr/lib/postgresql/18/bin')
args=parser.parse_args();out=args.evidence.resolve()
if out==ROOT or ROOT in out.parents:raise ValueError('Evidence belongs outside source')
out.mkdir(parents=True,exist_ok=False,mode=0o700)
import config
import psycopg
from psycopg import sql
from postgresql_qualification_support import server
from pgadmin.cdeadmin.providers.postgresql import large_object_files as private_sql
from pgadmin.cdeadmin.providers.postgresql.continuity import binary_paths
from pgadmin.cdeadmin.providers.postgresql.continuity_transport import ContinuityTransport
from pgadmin.cdeadmin.workspace.postgresql_continuity_jobs import PostgreSQLContinuityJobs
from pgadmin.cdeadmin.workspace import postgresql_logical_stream as stream
from pgadmin.cdeadmin.workspace import postgresql_continuity_slot_sql as slots
proof={'complete':False,'history_testing':'not run','full_product_complete':False,
       'source_sha256':{str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in [Path(__file__),ROOT/'web/pgadmin/cdeadmin/workspace/postgresql_logical_stream.py',ROOT/'web/pgadmin/cdeadmin/workspace/postgresql_continuity_jobs.py',ROOT/'web/pgadmin/cdeadmin/providers/postgresql/continuity.py']}}
jobs=PostgreSQLContinuityJobs(out/'jobs.json',out/'jobs');endpoint=str(uuid.uuid4());paths=binary_paths(args.binary_path)
try:
 with server(out/'fixture',server_options=('-c','wal_level=logical','-c','wal_sender_timeout=5s')) as (route,password,fixture):
  parameters={'host':route['host'],'port':route['port'],'user':route['user'],'dbname':route['database']}
  database="Native database = ü ' \\"
  with psycopg.connect(**parameters,password=password,autocommit=True) as bootstrap:
   bootstrap.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
  parameters['dbname']=database
  with psycopg.connect(**parameters,password=password,autocommit=True) as observer:
   observer.execute('CREATE TABLE sr_stream_data(id bigint PRIMARY KEY,body text,payload bytea)')
   pub="Native publication ü ' \\"
   observer.execute(sql.SQL('CREATE PUBLICATION {} FOR TABLE sr_stream_data').format(sql.Identifier(pub)))
   target='postgresql-database:'+str(observer.execute('SELECT oid FROM pg_database WHERE datname=current_database()').fetchone()[0])
   def wait(job,predicate):
    deadline=time.monotonic()+40
    while True:
     result=jobs.get(job['job_id'],1,endpoint)
     if predicate(result):return result
     assert time.monotonic()<deadline,result;time.sleep(.03)
   def prepare(name,pairs,*,end='',timeout=30):
    selected={'slot':name,'plugin_options':pairs,'status_interval_seconds':1,'fsync_interval_seconds':1,'end_lsn':end,'timeout_seconds':timeout}
    source=stream.bind_source(slots.enrich(private_sql.identity(observer),observer,selected))
    reviewed=jobs.review({'operation':stream.OPERATION,'database_target_id':target,'options':selected},1,endpoint,source,'owned',paths)
    return reviewed,source
   def start(job,source):
    request={'job_id':job['job_id'],'review_digest':job['review_digest'],'confirmed':True}
    return jobs.start(request,1,endpoint,source,'owned',ContinuityTransport(parameters,secrets={'database_password':password}))
   evidence={}
   for mode,plugin,pairs in [('text','test_decoding',[{'name':'include-xids','value':'1'},{'name':'include-xids','value':'0'},{'name':'skip-empty-xacts','value':'1'}]),('binary','pgoutput',[{'name':'proto_version','value':'4'},{'name':'publication_names','value':sql.Identifier(pub).as_string(observer)},{'name':'binary','value':'true'}])]:
    reference='sr_stream_reference_'+mode;managed='sr_stream_'+mode
    observer.execute('SELECT * FROM pg_create_logical_replication_slot(%s,%s)',(reference,plugin))
    observer.execute('SELECT * FROM pg_create_logical_replication_slot(%s,%s)',(managed,plugin))
    observer.execute('INSERT INTO sr_stream_data VALUES(%s,%s,%s)',(9007199254740993 if mode=='text' else 2,"native 😀 quote' slash\\ newline\n",b'\x00\x80\xff\n'))
    end=observer.execute('SELECT pg_current_wal_insert_lsn()::text').fetchone()[0]
    rows=observer.execute('SELECT data FROM pg_logical_slot_peek_binary_changes(%s,NULL,NULL,VARIADIC %s::text[])',(reference,[part for pair in pairs for part in (pair['name'],pair['value'])])).fetchall()
    expected=b''.join(bytes(row[0])+b'\n' for row in rows);assert expected
    reviewed,source=prepare(managed,pairs,end=end)
    start(reviewed,source);done=wait(reviewed,lambda result:result['state'] not in {'dispatching','active','cancel_requested'} and (result.get('logical_stream_artifact') or {}).get('state') in {'sealed','unavailable'})
    assert done['state']=='captured' and done['native_receiver_returned'],done
    saved=jobs.load(done['job_id'],1,endpoint)
    with stream.payload(jobs,saved) as file:actual=file.read()
    assert actual==expected,(mode,len(actual),len(expected))
    assert done['logical_stream_artifact']['sha256']==hashlib.sha256(expected).hexdigest()
    assert start(reviewed,source)['state']=='captured'
    page=stream.preview(jobs,saved,{'limit':17});assert page['bytes']==min(17,len(expected))
    deadline=time.monotonic()+10
    while observer.execute('SELECT active FROM pg_replication_slots WHERE slot_name=%s',(managed,)).fetchone()[0]:assert time.monotonic()<deadline;time.sleep(.03)
    confirmed=observer.execute('SELECT confirmed_flush_lsn::text FROM pg_replication_slots WHERE slot_name=%s',(managed,)).fetchone()[0]
    assert observer.execute('SELECT %s::pg_lsn>%s::pg_lsn',(confirmed,source['logical_stream_confirmed_lsn'])).fetchone()[0]
    evidence[mode]={'bytes':len(actual),'sha256':hashlib.sha256(actual).hexdigest(),'native_confirmed_flush_lsn':confirmed,'tool':done['tool_identities']['pg_recvlogical']}
    observer.execute('SELECT pg_drop_replication_slot(%s)',(reference,));observer.execute('SELECT pg_drop_replication_slot(%s)',(managed,))
   observer.execute("SELECT * FROM pg_create_logical_replication_slot('sr_stream_cancel','test_decoding')")
   reviewed,source=prepare('sr_stream_cancel',[{'name':'include-xids','value':'0'}],timeout=None)
   start(reviewed,source)
   deadline=time.monotonic()+15
   while not observer.execute("SELECT active FROM pg_replication_slots WHERE slot_name='sr_stream_cancel'").fetchone()[0]:assert time.monotonic()<deadline;time.sleep(.03)
   observer.execute("INSERT INTO sr_stream_data VALUES(3,'cancelled native stream',NULL)")
   wait(reviewed,lambda result:int((result.get('progress') or {}).get('captured_bytes','0'))>0)
   jobs.cancel(reviewed['job_id'],1,endpoint)
   stopped=wait(reviewed,lambda result:result['state'] in {'cancelled','unknown'} and result.get('worker_io_closed') is True and (result.get('logical_stream_artifact') or {}).get('state')=='sealed')
   assert stopped['state']=='cancelled' and stopped['logical_stream_artifact']['state']=='sealed',stopped
   assert start(reviewed,source)['state']=='cancelled'
   deadline=time.monotonic()+10
   while observer.execute("SELECT active FROM pg_replication_slots WHERE slot_name='sr_stream_cancel'").fetchone()[0]:assert time.monotonic()<deadline;time.sleep(.03)
   observer.execute("SELECT pg_drop_replication_slot('sr_stream_cancel')")
   observer.execute("SELECT * FROM pg_create_logical_replication_slot('sr_stream_publication_lost','test_decoding')")
   observer.execute("INSERT INTO sr_stream_data VALUES(4,'native return before failed file seal',NULL)")
   end=observer.execute('SELECT pg_current_wal_insert_lsn()::text').fetchone()[0]
   reviewed,source=prepare('sr_stream_publication_lost',[{'name':'include-xids','value':'0'}],end=end)
   original=stream.reconcile
   def unavailable(*_args):raise OSError('owned file sealing failure')
   stream.reconcile=unavailable
   try:
    start(reviewed,source)
    retained=wait(reviewed,lambda result:result['state']=='captured' and (result.get('logical_stream_artifact') or {}).get('state')=='unavailable')
   finally:stream.reconcile=original
   assert retained['native_receiver_returned'] and start(reviewed,source)['state']=='captured'
   recovered=stream.reconcile(jobs,jobs.load(reviewed['job_id'],1,endpoint))
   assert recovered['state']=='captured' and recovered['native_receiver_returned'] and recovered['logical_stream_artifact']['state']=='sealed'
   observer.execute("SELECT pg_drop_replication_slot('sr_stream_publication_lost')")
   observer.execute("SELECT * FROM pg_create_logical_replication_slot('sr_stream_stale','test_decoding')")
   observer.execute("INSERT INTO sr_stream_data VALUES(5,'another native consumer',NULL)")
   reviewed,source=prepare('sr_stream_stale',[{'name':'include-xids','value':'0'}])
   observer.execute("SELECT * FROM pg_logical_slot_get_changes('sr_stream_stale',NULL,NULL)").fetchall()
   selected={'slot':'sr_stream_stale'}
   fresh=stream.bind_source(slots.enrich(private_sql.identity(observer),observer,selected))
   from pgadmin.cdeadmin.providers.postgresql.continuity import ContinuityError
   try:start(reviewed,fresh)
   except ContinuityError:pass
   else:raise AssertionError('A changed native consumer position was admitted')
   assert jobs.get(reviewed['job_id'],1,endpoint)['state']=='reviewed'
   start(reviewed,source)
   refused=wait(reviewed,lambda result:result['state']=='failed')
   assert not refused.get('native_receiver_dispatch_admitted') and not (jobs.directory(jobs.load(refused['job_id'],1,endpoint))/stream.FILENAME).exists()
   observer.execute("SELECT pg_drop_replication_slot('sr_stream_stale')")
   proof.update(complete=True,text_binary_native_files_match_independent_SQL_slots=True,ordered_and_quoted_plugin_options_preserved=True,
                native_feedback_independently_observed=True,lost_seal_recovers_bytes_without_native_replay=True,changed_native_checkpoint_refused_at_admission_and_worker=True,duplicate_admission_does_not_replay=True,cancelled_stream_preserves_output_and_slot=True,captured=evidence)
finally:
 jobs.close();(out/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps({'complete':proof['complete'],'history_testing':'not run','full_product_complete':False}))

#!/usr/bin/env python3
"""Independently compare retained temporary text/binary decoding on owned PG18.3."""
from pathlib import Path
import argparse,hashlib,json,socket,sys,time,uuid
root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path,required=True)
out=parser.parse_args().evidence.resolve()
if out==root or root in out.parents:raise ValueError('Evidence belongs outside source')
out.mkdir(mode=0o700,parents=True,exist_ok=False)
sys.path[:0]=[str(root),str(root/'web'),str(root/'tools')]
import config
import psycopg
from psycopg import sql
from postgresql_qualification_support import server
from pgadmin.cdeadmin.providers.postgresql import large_object_files as private_sql
from pgadmin.cdeadmin.providers.postgresql.continuity_transport import ContinuityTransport
from pgadmin.cdeadmin.workspace.postgresql_temporary_slot_jobs import TemporarySlotResources
from pgadmin.cdeadmin.workspace.postgresql_temporary_slot_jobs import TemporarySlotTransport
from pgadmin.cdeadmin.workspace import postgresql_slot_changes as changes
proof={'complete':False,'history_testing':'not run','full_product_complete':False,'source_sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),root/'web/pgadmin/cdeadmin/providers/postgresql/temporary_slots.py',root/'web/pgadmin/cdeadmin/workspace/postgresql_temporary_slot_jobs.py',root/'web/pgadmin/cdeadmin/workspace/postgresql_slot_changes.py']}};jobs=None
try:
 with server(out/'fixture',server_options=('-c','wal_level=logical')) as (route,password,fixture):
  args={'host':route['host'],'port':route['port'],'user':route['user'],'dbname':route['database'],'autocommit':True}
  with psycopg.connect(**args,password=password) as observer:
   observer.execute('CREATE TABLE sr_temp_data(id bigint PRIMARY KEY,body text,payload bytea)')
   observer.execute('CREATE PUBLICATION "Temporary publication ü" FOR TABLE sr_temp_data')
   observer.execute("SELECT * FROM pg_create_logical_replication_slot('sr_ref_text','test_decoding')")
   observer.execute("SELECT * FROM pg_create_logical_replication_slot('sr_ref_binary','pgoutput')")
   source={'sql_identity':private_sql.identity(observer)};endpoint=str(uuid.uuid4());jobs=TemporarySlotResources(out/'resources.json',out/'resources')
   program={'execution_host':{'kind':'application-host','hostname':socket.gethostname(),'platform':sys.platform},'adapter_sha256':hashlib.sha256((root/'web/pgadmin/cdeadmin/providers/postgresql/temporary_slots.py').read_bytes()).hexdigest(),'logical_output_sha256':hashlib.sha256((root/'web/pgadmin/cdeadmin/workspace/postgresql_slot_changes.py').read_bytes()).hexdigest(),'channel_sha256':hashlib.sha256((root/'web/pgadmin/cdeadmin/workspace/postgresql_temporary_slot_jobs.py').read_bytes()).hexdigest()}
   opened=jobs.review(1,endpoint,{'max_lifetime_seconds':120},{'identity':source,'state':{}},'owned',program);rid=opened['job_id'];record=jobs.load(rid,1,endpoint)
   jobs.start({'job_id':rid,'review_digest':opened['review_digest'],'confirmed':True},1,endpoint,{k:record[k] for k in ('source','configuration','program')},TemporarySlotTransport(ContinuityTransport({k:v for k,v in args.items() if k!='autocommit'},secrets={'database_password':password})))
   deadline=time.monotonic()+15
   while not jobs.get(rid,1,endpoint).get('ready'):assert time.monotonic()<deadline;time.sleep(.02)
   commands=jobs.commands(record)
   def wait(child,states):
    deadline=time.monotonic()+20
    while True:
     value=commands.get(child['job_id'],1,endpoint)
     if value['state'] in states and not jobs.get(rid,1,endpoint).get('pending_command'):return value
     assert time.monotonic()<deadline,value;time.sleep(.02)
   def run(operation,expected='completed',**options):
    child=wait(jobs.queue_review(rid,1,endpoint,operation,options),{'reviewed'})
    request={'job_id':child['job_id'],'review_digest':child['review_digest'],'confirmed':True}
    jobs.queue_execute(rid,1,endpoint,request);child=wait(child,{expected})
    assert jobs.queue_execute(rid,1,endpoint,request)['state']==expected
    return child
   run('logical_create',slot='sr_temp_text',plugin='test_decoding')
   run('logical_create',slot='sr_temp_binary',plugin='pgoutput')
   observer.execute('INSERT INTO sr_temp_data VALUES(%s,%s,%s)',(9007199254740993,'native 😀 雪',b'\x00\x80\xff'))
   options_text=[{'name':'include-xids','value':'0'},{'name':'skip-empty-xacts','value':'1'}]
   options_binary=[{'name':'proto_version','value':'4'},{'name':'publication_names','value':'"Temporary publication ü"'},{'name':'binary','value':'true'}]
   captured={}
   for mode,slot,reference,pairs in [('text','sr_temp_text','sr_ref_text',options_text),('binary','sr_temp_binary','sr_ref_binary',options_binary)]:
    flattened=[part for pair in pairs for part in (pair['name'],pair['value'])]
    data='encode(data,\'base64\')' if mode=='binary' else 'data'
    function='pg_logical_slot_peek_binary_changes' if mode=='binary' else 'pg_logical_slot_peek_changes'
    expected=observer.execute('SELECT lsn::text,xid::text,'+data+' FROM '+function+'(%s,NULL,NULL,VARIADIC %s::text[])',(reference,flattened)).fetchall()
    assert expected
    def captured_rows(child):
     assert child['native_sql_acknowledged'] and child['change_artifact']['state']=='verified',child
     with changes.payload(commands,commands.load(child['job_id'],1,endpoint)) as stream:
      content=stream.read();assert hashlib.sha256(content).hexdigest()==child['change_artifact']['sha256']
     return [(row['lsn'],row['xid'],row['data']) for row in map(json.loads,content.splitlines())]
    peek=run('peek_'+mode,slot=slot,plugin_options=pairs)
    assert captured_rows(peek)==expected,(mode,captured_rows(peek),expected)
    got=run('get_'+mode,slot=slot,plugin_options=pairs)
    assert captured_rows(got)==expected
    empty=run('get_'+mode,slot=slot,plugin_options=pairs)
    assert captured_rows(empty)==[]
    captured[mode]={'peek':peek['job_id'],'get':got['job_id'],'rows':len(expected)}
   observer.execute('INSERT INTO sr_temp_data VALUES(2,\'lost publication\',NULL)')
   replace=changes.durable_replace
   def broken(*_args):raise OSError('owned logical publication failure')
   changes.durable_replace=broken
   try:unknown=run('get_text',expected='unknown',slot='sr_temp_text',plugin_options=options_text)
   finally:changes.durable_replace=replace
   assert unknown['native_sql_acknowledged'] and not unknown.get('change_artifact')
   reconciled=changes.reconcile(commands,commands.load(unknown['job_id'],1,endpoint))
   assert reconciled['state']=='unknown' and reconciled['change_artifact']['state']=='verified'
   jobs.cancel(rid,1,endpoint);deadline=time.monotonic()+15
   while not jobs.get(rid,1,endpoint).get('worker_io_closed'):assert time.monotonic()<deadline;time.sleep(.02)
   with changes.payload(commands,commands.load(unknown['job_id'],1,endpoint)) as stream:assert stream.read()
   observer.execute("SELECT pg_drop_replication_slot('sr_ref_text')");observer.execute("SELECT pg_drop_replication_slot('sr_ref_binary')")
   proof.update(complete=True,native_text_and_binary_match_independent_permanent_slots=True,peek_does_not_consume=True,get_consumes_without_repeat=True,lost_publication_recovers_acked_bytes_without_changing_unknown_outcome=True,offline_artifact_after_resource_release=True,captured=captured)
finally:
 if jobs:jobs.close()
 (out/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))

#!/usr/bin/env python3
"""Independently compare retained temporary text/binary decoding on owned PG18.3."""
from pathlib import Path
import argparse,base64,hashlib,json,socket,sys,time,uuid
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
proof={'complete':False,'history_testing':'not run','full_product_complete':False,'source_sha256':{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),root/'web/pgadmin/cdeadmin/providers/postgresql/temporary_slots.py',root/'web/pgadmin/cdeadmin/workspace/postgresql_temporary_slot_jobs.py',root/'web/pgadmin/cdeadmin/workspace/postgresql_slot_changes.py',root/'web/pgadmin/cdeadmin/providers/postgresql/large_object_files.py']}};jobs=None
try:
 with server(out/'fixture',server_options=('-c','wal_level=logical')) as (route,password,fixture):
  args={'host':route['host'],'port':route['port'],'user':route['user'],'dbname':route['database'],'autocommit':True}
  with psycopg.connect(**args,password=password) as observer:
   observer.execute('CREATE TABLE sr_temp_data(id bigint PRIMARY KEY,body text,payload bytea)')
   observer.execute('CREATE PUBLICATION "Temporary publication ü" FOR TABLE sr_temp_data')
   observer.execute("SELECT * FROM pg_create_logical_replication_slot('sr_ref_text','test_decoding')")
   observer.execute("SELECT * FROM pg_create_logical_replication_slot('sr_ref_binary','pgoutput')")
   source={'sql_identity':private_sql.identity(observer)};endpoint=str(uuid.uuid4());jobs=TemporarySlotResources(out/'resources.json',out/'resources')
   program={'execution_host':{'kind':'application-host','hostname':socket.gethostname(),'platform':sys.platform},'adapter_sha256':hashlib.sha256((root/'web/pgadmin/cdeadmin/providers/postgresql/temporary_slots.py').read_bytes()).hexdigest(),'logical_output_sha256':hashlib.sha256((root/'web/pgadmin/cdeadmin/workspace/postgresql_slot_changes.py').read_bytes()).hexdigest(),'private_transport_sha256':hashlib.sha256(Path(private_sql.__file__).read_bytes()).hexdigest(),'channel_sha256':hashlib.sha256((root/'web/pgadmin/cdeadmin/workspace/postgresql_temporary_slot_jobs.py').read_bytes()).hexdigest()}
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
   def wire_case(parameters,label,native_encoding):
    with psycopg.connect(**parameters,password=password,autocommit=True) as independent:
     independent.execute('CREATE TABLE '+label+'(id bigint PRIMARY KEY,body text,payload bytea)')
     publication=label+'_pub';independent.execute('CREATE PUBLICATION '+publication+' FOR TABLE '+label)
     identity=private_sql.identity(independent);endpoint=str(uuid.uuid4())
     reviewed=jobs.review(1,endpoint,{'max_lifetime_seconds':120},{'identity':{'sql_identity':identity},'state':{}},'owned',program)
     resource=jobs.load(reviewed['job_id'],1,endpoint);rid=resource['job_id']
     jobs.start({'job_id':rid,'review_digest':reviewed['review_digest'],'confirmed':True},1,endpoint,{k:resource[k] for k in ('source','configuration','program')},TemporarySlotTransport(ContinuityTransport(parameters,secrets={'database_password':password})))
     deadline=time.monotonic()+15
     while not jobs.get(rid,1,endpoint).get('ready'):assert time.monotonic()<deadline;time.sleep(.02)
     commands=jobs.commands(resource)
     def wait(child,states):
      deadline=time.monotonic()+20
      while True:
       current=commands.get(child['job_id'],1,endpoint)
       if current['state'] in states and not jobs.get(rid,1,endpoint).get('pending_command'):return current
       assert time.monotonic()<deadline,current;time.sleep(.02)
     def run(operation,expected_state='completed',**selected):
      child=wait(jobs.queue_review(rid,1,endpoint,operation,selected),{'reviewed'})
      request={'job_id':child['job_id'],'review_digest':child['review_digest'],'confirmed':True}
      jobs.queue_execute(rid,1,endpoint,request);child=wait(child,{expected_state})
      assert jobs.queue_execute(rid,1,endpoint,request)['state']==expected_state
      return child
     for mode,plugin in [('text','test_decoding'),('binary','pgoutput')]:
      independent.execute('SELECT * FROM pg_create_logical_replication_slot(%s,%s)',(label+'_ref_'+mode,plugin))
      run('logical_create',slot=label+'_'+mode,plugin=plugin)
     native_bytes=b'raw\x80\xff\r\n' if native_encoding=='SQL_ASCII' else b'legacy\x80\xe9\xff' if native_encoding=='LATIN1' else 'native 😀 雪'.encode()
     independent.execute('INSERT INTO '+label+" VALUES(9007199254740993,convert_from(decode('"+native_bytes.hex()+"','hex'),'"+native_encoding+"'),decode('0080ff','hex'))")
     counts={}
     for mode,pairs in [('text',[{'name':'include-xids','value':'0'},{'name':'skip-empty-xacts','value':'1'}]),('binary',[{'name':'proto_version','value':'4'},{'name':'publication_names','value':publication},{'name':'binary','value':'true'}])]:
      function='pg_logical_slot_peek_binary_changes' if mode=='binary' else 'pg_logical_slot_peek_changes'
      data="encode(data,'base64')" if mode=='binary' else "encode(convert_to(data,current_setting('server_encoding')::name),'base64')"
      try:
       expected=[tuple(map(private_sql.native_text,row)) for row in independent.execute('SELECT lsn::text,xid::text,'+data+' FROM '+function+'(%s,NULL,NULL,VARIADIC %s::text[])',(label+'_ref_'+mode,[part for pair in pairs for part in (pair['name'],pair['value'])])).fetchall()]
      except psycopg.errors.CharacterNotInRepertoire as error:
       assert mode=='binary' and native_encoding=='SQL_ASCII' and parameters['client_encoding']=='UTF8' and error.sqlstate=='22021'
       child=run('peek_binary',expected_state='failed',slot=label+'_binary',upto_nchanges=None,plugin_options=pairs)
       assert child['native_error_sqlstate']=='22021' and not child.get('native_sql_acknowledged')
       assert not child.get('change_artifact')
       inventory=wait(jobs.queue_catalog(rid,1,endpoint),{'completed'})
       assert inventory['result']['total']==0
       counts[mode]={'native_refusal_sqlstate':'22021','native_error_removed_owned_temporary_slots':True}
       independent.execute('SELECT pg_drop_replication_slot(%s)',(label+'_ref_'+mode,))
       continue
      assert expected
      if mode=='text':assert any(native_bytes in base64.b64decode(row[2]) for row in expected)
      counts[mode]=len(expected)
      for operation in ('peek_'+mode,'get_'+mode,'get_'+mode):
       child=run(operation,slot=label+'_'+mode,upto_nchanges=None,plugin_options=pairs)
       assert child['change_artifact']['data_encoding']==('base64' if mode=='binary' else 'base64-native-text')
       assert child['change_artifact']['native_server_encoding']==native_encoding
       assert child['change_artifact']['native_client_encoding']==parameters['client_encoding']
       with changes.payload(commands,commands.load(child['job_id'],1,endpoint)) as source:rows=list(map(json.loads,source.read().splitlines()))
       assert [(row['lsn'],row['xid'],row['data']) for row in rows]==expected
       if operation.startswith('get_'):expected=[]
      independent.execute('SELECT pg_drop_replication_slot(%s)',(label+'_ref_'+mode,))
     jobs.cancel(rid,1,endpoint);deadline=time.monotonic()+15
     while not jobs.get(rid,1,endpoint).get('worker_io_closed'):assert time.monotonic()<deadline;time.sleep(.02)
     return {'server_encoding':native_encoding,'client_encoding':parameters['client_encoding'],'text_binary_rows':counts,'native_raw_text_bytes_preserved':True}
   observer.execute("CREATE DATABASE sr_ascii ENCODING 'SQL_ASCII' LC_COLLATE 'C' LC_CTYPE 'C' TEMPLATE template0")
   observer.execute("CREATE DATABASE sr_latin1 ENCODING 'LATIN1' LC_COLLATE 'C' LC_CTYPE 'C' TEMPLATE template0")
   raw_parameters={k:v for k,v in args.items() if k!='autocommit'}
   proof['sql_ascii_cases']=[wire_case({**raw_parameters,'dbname':'sr_ascii','client_encoding':'UTF8'},'sr_ascii_utf8','SQL_ASCII'),wire_case({**raw_parameters,'dbname':'sr_ascii','client_encoding':'SQL_ASCII'},'sr_ascii_wire','SQL_ASCII'),wire_case({**raw_parameters,'client_encoding':'SQL_ASCII'},'sr_utf8_wire','UTF8'),wire_case({**raw_parameters,'dbname':'sr_latin1','client_encoding':'SQL_ASCII'},'sr_latin1_wire','LATIN1')]
   proof.update(complete=True,native_text_and_binary_match_independent_permanent_slots=True,peek_does_not_consume=True,get_consumes_without_repeat=True,lost_publication_recovers_acked_bytes_without_changing_unknown_outcome=True,offline_artifact_after_resource_release=True,captured=captured)
finally:
 if jobs:jobs.close()
 (out/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof))

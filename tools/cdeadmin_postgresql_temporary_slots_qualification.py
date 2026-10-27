#!/usr/bin/env python3
"""Owned PostgreSQL18.3 native temporary-slot adapter and independent lifetime proof."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output):
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    import config  # noqa: F401
    import psycopg
    from postgresql_qualification_support import server
    from pgadmin.cdeadmin.providers.postgresql.temporary_slots import TemporarySlots,TemporarySlotError
    proof={'complete':False,'history_testing':'not run','full_product_complete':False,'scope':'native independently owned temporary-slot adapter; managed API/UI qualification remains separate','commands':[],
     'source_sha256':{str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in (Path(__file__),ROOT/'web/pgadmin/cdeadmin/providers/postgresql/temporary_slots.py',ROOT/'web/pgadmin/cdeadmin/providers/postgresql/large_object_files.py',ROOT/'tools/postgresql_qualification_support.py')}}
    try:
     with server(output/'fixture',server_options=('-c','wal_level=logical')) as (route,password,fixture):
      args={'host':route['host'],'port':route['port'],'user':route['user'],'dbname':route['database'],'password':password,'autocommit':True}
      with psycopg.connect(**args) as observer:
       owner=psycopg.connect(**args)
       try:
        resource=TemporarySlots(owner)
        observer.execute("SELECT * FROM pg_create_physical_replication_slot('sr_perm_physical',true,false)")
        observer.execute("SELECT * FROM pg_create_logical_replication_slot('sr_perm_logical','test_decoding',false)")
        def command(operation,**options):
         review=resource.review(operation,options);ack=[];events=[]
         def acknowledged(value):ack.append(value);events.append('acknowledged')
         result=resource.command(review,acknowledged,dispatching=lambda:events.append('dispatch_admitted'),finished=lambda:events.append('dispatch_finished'))
         assert len(ack)==1 and ack[0]['native_command_returned'] and ack[0]['temporary']
         assert events==['dispatch_admitted','acknowledged','dispatch_finished'],events
         proof['commands'].append({'operation':operation,'slot':options['slot'],'acknowledged':True})
         return result
        command('physical_create',slot='sr_temp_physical')
        command('logical_create',slot='sr_temp_logical',plugin='test_decoding')
        command('physical_copy',slot='sr_temp_physical_copy',source_slot='sr_perm_physical')
        command('logical_copy',slot='sr_temp_logical_copy',source_slot='sr_perm_logical',plugin='test_decoding')
        command('logical_copy',slot='sr_temp_logical_auto',source_slot='sr_temp_logical')
        page=resource.inventory(0,2);assert page['total']==5 and page['more'] and len(page['slots'])==2
        assert len(resource.inventory(2,2)['slots'])==2
        rows=observer.execute('SELECT slot_name,temporary,active_pid::text FROM pg_replication_slots WHERE temporary ORDER BY slot_name').fetchall()
        assert len(rows)==5 and all(row[1] and row[2]==resource.backend_pid for row in rows),rows
        try:resource.review('logical_create',{'slot':'sr_utf8_truncation','plugin':'é'*63})
        except TemporarySlotError:pass
        else:raise AssertionError('Native UTF-8 plugin name would have been truncated')
        assert resource.inventory()['total']==5
        observer.execute("CREATE DATABASE sr_native_latin1 TEMPLATE template0 ENCODING 'LATIN1' LC_COLLATE 'C' LC_CTYPE 'C' LOCALE_PROVIDER libc")
        with psycopg.connect(**{**args,'dbname':'sr_native_latin1'}) as latin:
         latin_resource=TemporarySlots(latin)
         reviewed=latin_resource.review('logical_create',{'slot':'sr_latin1_exact','plugin':'é'*63})
         assert reviewed['options']['plugin']=='é'*63
        proof['database_encoding_plugin_width_preserved']=True
        lsn=observer.execute('SELECT pg_current_wal_lsn()::text').fetchone()[0]
        command('advance',slot='sr_temp_physical',upto_lsn=lsn)
        try:resource.review('drop',{'slot':'sr_perm_physical'})
        except TemporarySlotError:pass
        else:raise AssertionError('Permanent slot escaped resource ownership check')
        command('drop',slot='sr_temp_logical_copy')
        assert observer.execute("SELECT count(*) FROM pg_replication_slots WHERE slot_name='sr_temp_logical_copy'").fetchone()[0]==0
        lost=resource.review('physical_create',{'slot':'sr_temp_lost_ack'})
        def unavailable(_value):raise OSError('durable native acknowledgement unavailable')
        try:resource.command(lost,unavailable)
        except OSError:pass
        else:raise AssertionError('Injected acknowledgement failure was concealed')
        assert observer.execute("SELECT temporary FROM pg_replication_slots WHERE slot_name='sr_temp_lost_ack'").fetchone()==(True,)
        try:resource.review('physical_create',{'slot':'sr_temp_lost_ack'})
        except TemporarySlotError:pass
        else:raise AssertionError('An uncertain acknowledged effect was implicitly repeated')
        proof['lost_ack_slot_exists_without_replay']=True
        try:command('logical_create',slot='sr_temp_error',plugin='sr_missing_plugin')
        except psycopg.Error as error:proof['native_error_sqlstate']=error.sqlstate
        else:raise AssertionError('Native missing plugin was accepted')
        assert resource.inventory()['slots']==[],resource.inventory()
        assert observer.execute('SELECT count(*) FROM pg_replication_slots WHERE temporary').fetchone()[0]==0
        assert observer.execute('SELECT count(*) FROM pg_replication_slots WHERE NOT temporary').fetchone()[0]==2
        command('physical_create',slot='sr_temp_until_close')
        pid=resource.backend_pid;owner.close()
        closed_at=time.monotonic();deadline=closed_at+10
        while observer.execute("SELECT count(*) FROM pg_replication_slots WHERE slot_name='sr_temp_until_close'").fetchone()[0]!=0:
         assert time.monotonic()<deadline;time.sleep(.02)
        proof['native_absence_observed_after_local_close_seconds']=time.monotonic()-closed_at
        proof.update(complete=True,backend_pid=pid,independent_temporary_lifetime_verified=True,native_error_dropped_all_owned_temporary_slots=True,permanent_slots_preserved=True,connection_close_dropped_temporary_slots=True)
       finally:owner.close()
       observer.execute("SELECT pg_drop_replication_slot('sr_perm_physical')");observer.execute("SELECT pg_drop_replication_slot('sr_perm_logical')")
    finally:
     (output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path,required=True)
    result=qualify(parser.parse_args().evidence)
    print(json.dumps({'complete':result['complete'],'native_commands':len(result['commands']),'history_testing':'not run','full_product_complete':False}))

"""Execute generated MySQL partition plans against disposable native data."""
import argparse
import json
from pathlib import Path
import secrets
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'web'))
import config  # noqa: F401
import mysql.connector
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION,MYSQL_PROFILE,_resources
from pgadmin.cdeadmin.providers.mysql_tablespaces import identifier


def qualify(options,output):
    output.mkdir(parents=True,exist_ok=True);connection=mysql.connector.connect(**{**options,'autocommit':True})
    cursor=connection.cursor();database='sr_partition_'+secrets.token_hex(6);table='t`é';exchange='x`é'
    address=identifier(database)+'.'+identifier(table);other=identifier(database)+'.'+identifier(exchange)
    proof={'passed':False,'statements':{},'native_results':[]}
    def execute(kind,operation,draft=None,partition='p0'):
        target={'display_name':partition if kind=='partition' else table,'display_path':[database,table]+([partition] if kind=='partition' else [])}
        request={'resource_kind':kind,'operation_id':operation,'draft':draft or {},'target_resource':target,'_provider_route':{'host':options.get('host','localhost')}}
        assert not MYSQL_ADMINISTRATION.validate(request)['errors']
        statement=MYSQL_ADMINISTRATION._compile(request)['statements'][0]
        cursor.execute(statement['source'])
        if cursor.description:proof['native_results'].append({'operation':operation,'rows':cursor.fetchall()})
        proof['statements'].setdefault(kind+'.'+operation,statement['source'])
    def rows(name=address):
        cursor.execute('SELECT id FROM '+name+' ORDER BY id');return cursor.fetchall()
    try:
        cursor.execute('SELECT VERSION()');assert str(cursor.fetchone()[0]).split('-')[0]=='9.7.0'
        cursor.execute('CREATE DATABASE '+identifier(database))
        for mode in ('','NO_BACKSLASH_ESCAPES,ANSI_QUOTES'):
            connection.sql_mode=mode
            cursor.execute('CREATE TABLE '+address+' (id int PRIMARY KEY) ENGINE=InnoDB PARTITION BY RANGE(id) (PARTITION p0 VALUES LESS THAN (10), PARTITION p1 VALUES LESS THAN (20))')
            cursor.execute('INSERT INTO '+address+' VALUES (1),(11)')
            for operation in ('analyze','check','optimize','rebuild'):execute('partition',operation)
            assert rows()==[(1,),(11,)]
            cursor.execute('CREATE TABLE '+other+' (id int PRIMARY KEY) ENGINE=InnoDB')
            cursor.execute('INSERT INTO '+other+' VALUES (5)')
            draft={'exchange_database':database,'exchange_table':exchange}
            execute('partition','exchange',draft);assert rows()==[(5,),(11,)] and rows(other)==[(1,)]
            cursor.execute('INSERT INTO '+other+' VALUES (55)')
            try:execute('partition','exchange',draft)
            except mysql.connector.Error as error:proof['row_placement_refusal_code']=error.errno
            else:raise AssertionError('WITH VALIDATION admitted an out-of-range row')
            assert rows()==[(5,),(11,)] and rows(other)==[(1,),(55,)]
            cursor.execute('DELETE FROM '+other+' WHERE id=55')
            execute('partition','exchange',{**draft,'validation':'WITHOUT VALIDATION'});assert rows()==[(1,),(11,)]
            execute('partition','reorganize',{'definitions':'PARTITION pa VALUES LESS THAN (15), PARTITION pb VALUES LESS THAN (20)'},'p1')
            execute('table','add_partitions',{'definitions':'PARTITION p2 VALUES LESS THAN (30)'})
            cursor.execute('INSERT INTO '+address+' VALUES (25)')
            discovered=_resources(connection,{'route':{}},MYSQL_PROFILE)
            observed=next(row for row in discovered if row['resource_kind']=='partition' and row['display_path']==[database,table,'pa'])
            assert observed['native']['partition_method']=='RANGE' and observed['native']['partition_description']=='15'
            assert {'drop','reorganize','exchange'} <= set(observed['native']['administration']['allowed_operations'])
            execute('partition','drop',partition='p2');assert rows()==[(1,),(11,)]
            execute('partition','truncate');assert rows()==[(11,)]
            execute('table','remove_partitioning')
            execute('table','partition_by',{'partition_clause':'PARTITION BY HASH(id) PARTITIONS 4'})
            execute('table','coalesce_partitions',{'count':2})
            execute('table','add_partitions',{'mode':'COUNT','count':2})
            assert rows()==[(11,)]
            cursor.execute('SELECT COUNT(*) FROM information_schema.PARTITIONS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s',(database,table));assert cursor.fetchone()[0]==4
            discovered=_resources(connection,{'route':{}},MYSQL_PROFILE)
            hash_parts=[row for row in discovered if row['resource_kind']=='partition' and row['display_path'][:2]==[database,table]]
            assert len(hash_parts)==4 and all(not {'drop','reorganize'} & set(row['native']['administration']['allowed_operations']) for row in hash_parts)
            cursor.execute('DROP TABLE '+address);cursor.execute('DROP TABLE '+other)
        proof.update(passed=True,checks=['native generated partition lifecycle','default and ANSI_QUOTES/NO_BACKSLASH_ESCAPES','Unicode and quoted owning table identities','native InnoDB maintenance result messages','WITH/WITHOUT VALIDATION exchanges and rejected out-of-range rows','RANGE reorganize/add/drop/truncate data effects','native partition catalog bounds','remove/repartition/HASH coalesce/add with retained data'])
    finally:
        cursor.execute('DROP DATABASE IF EXISTS '+identifier(database));cursor.close();connection.close()
        proof['owned_native_database_removed']=True
        (output/'summary.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False,default=str)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--connection-json',type=Path,required=True);parser.add_argument('--output-root',type=Path,required=True)
    args=parser.parse_args();qualify(json.loads(args.connection_json.read_text()),args.output_root)

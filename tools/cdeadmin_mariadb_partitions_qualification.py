"""Execute native MariaDB partition lifecycle and independently inspect effects."""
import argparse
import json
from pathlib import Path
import secrets
from tools.cdeadmin_mariadb_driver_gate import run
from pgadmin.cdeadmin.providers.mysql_family.provider import MARIADB_ADMINISTRATION


def qualify(route,evidence,*,password=None):
    import mariadb
    evidence.mkdir(parents=True,exist_ok=False)
    proof={'complete':False,'engine':'mariadb','version':'12.2.2','checks':[],'task_sources':{}}
    schema='owned_partitions_'+secrets.token_hex(8)
    credentials={'password':password} if password is not None else {}
    owner=mariadb.connect(**route,autocommit=True,**credentials);cursor=owner.cursor();observer=None
    try:
        cursor.execute('CREATE DATABASE `'+schema+'`');owner.database=schema
        cursor.execute('CREATE TABLE ranged(id INT PRIMARY KEY) PARTITION BY RANGE(id) (PARTITION p0 VALUES LESS THAN (10),PARTITION p1 VALUES LESS THAN (20))')
        cursor.execute('INSERT INTO ranged VALUES (1),(11)')
        observer=mariadb.connect(**{**route,'database':schema},autocommit=True,**credentials)
        def execute(kind,operation,table,partition=None,**draft):
            target={'resource_kind':kind,'display_name':partition or table,'display_path':[schema,table]+([partition] if partition else [])}
            request={'resource_kind':kind,'operation_id':operation,'target_resource':target,'draft':draft}
            validation=MARIADB_ADMINISTRATION.validate(request)
            assert not validation['errors'],validation
            plan=MARIADB_ADMINISTRATION._compile(request)
            proof['task_sources']['visual_admin.'+kind+'.'+operation]=[statement['source'] for statement in plan['statements']]
            for statement in plan['statements']:
                cursor.execute(statement['source'],statement.get('parameters',()))
                if cursor.description:cursor.fetchall()
                while cursor.nextset():
                    if cursor.description:cursor.fetchall()
        def count(table):
            c=observer.cursor();c.execute('SELECT COUNT(*) FROM `'+table+'`');value=c.fetchone()[0];c.close();return value
        for operation in ('analyze','check','optimize','repair','rebuild'):
            execute('partition',operation,'ranged','p0')
        assert count('ranged')==2
        proof['checks'].append('native_partition_maintenance_keeps_independently_observed_rows')
        execute('partition','convert_to_table','ranged','p1',exchange_database=schema,exchange_table='detached')
        assert count('detached')==1 and count('ranged')==1
        execute('table','convert_from_table','ranged',exchange_database=schema,exchange_table='detached',definitions='PARTITION p1 VALUES LESS THAN (20)')
        assert count('ranged')==2
        proof['checks'].append('native_convert_out_and_in_preserve_data_and_consume_standalone_table')
        cursor.execute('CREATE TABLE exchange_table(id INT PRIMARY KEY)');cursor.execute('INSERT INTO exchange_table VALUES(2)')
        execute('partition','exchange','ranged','p0',exchange_database=schema,exchange_table='exchange_table',validation='WITH VALIDATION')
        c=observer.cursor();c.execute('SELECT id FROM ranged ORDER BY id');assert c.fetchall()==[(2,),(11,)];c.close()
        proof['checks'].append('native_exchange_changes_partition_rows_with_explicit_validation')
        execute('partition','reorganize','ranged','p1',definitions='PARTITION p1a VALUES LESS THAN (15),PARTITION p1b VALUES LESS THAN (20)')
        execute('table','add_partitions','ranged',mode='DEFINITIONS',definitions='PARTITION p2 VALUES LESS THAN (30)')
        execute('partition','truncate','ranged','p0');assert count('ranged')==1
        execute('partition','drop','ranged','p2')
        execute('table','remove_partitioning','ranged');assert count('ranged')==1
        proof['checks'].append('native_reorganize_add_truncate_drop_remove_partitioning_rediscover_visible_effects')
        cursor.execute('CREATE TABLE hashed(id INT PRIMARY KEY)')
        execute('table','partition_by','hashed',partition_clause='PARTITION BY HASH(id) PARTITIONS 2')
        execute('table','add_partitions','hashed',mode='COUNT',count=2)
        execute('table','coalesce_partitions','hashed',count=1)
        c=observer.cursor();c.execute('SELECT COUNT(*) FROM information_schema.PARTITIONS WHERE TABLE_SCHEMA=? AND TABLE_NAME=?',(schema,'hashed'));assert c.fetchone()[0]==3;c.close()
        proof['checks'].append('native_hash_partition_creation_count_addition_and_coalesce')
        from pgadmin.cdeadmin.providers.mysql_family.provider import _resources, MARIADB_PROFILE
        def package(operation, draft):
            target=next((row for row in _resources(owner,{'route':{'database':schema}},MARIADB_PROFILE)
                         if row['resource_kind']=='package' and row['display_name']=='qualified_pkg'),None)
            compiled=MARIADB_ADMINISTRATION._compile({'resource_kind':'package','operation_id':operation,'draft':draft,'target_resource':target})
            proof['task_sources']['visual_admin.package.'+operation]=[statement['source'] for statement in compiled['statements']]
            for statement in compiled['statements']:cursor.execute(statement['source'],statement.get('parameters',()))
        package('create_specification',{'database':schema,'name':'qualified_pkg','sql_mode':'oracle','definition':'AS FUNCTION answer RETURN INT; END'})
        package('create_body',{'definition':'AS FUNCTION answer RETURN INT AS BEGIN RETURN 42; END; END'})
        package('replace_body',{'definition':'AS FUNCTION answer RETURN INT AS BEGIN RETURN 43; END; END'})
        cursor.execute('SELECT qualified_pkg.answer()');assert cursor.fetchone()[0]==43
        package('drop_body',{})
        package('replace_specification',{'definition':'AS FUNCTION replacement RETURN INT; END'})
        proof['checks'].append('independent_oracle_package_declaration_body_lifecycle_compiles_and_executes_native_tasks')
        proof['complete']=True
    finally:
        if observer is not None:observer.close()
        cursor.execute('DROP DATABASE IF EXISTS `'+schema+'`');cursor.close();owner.close()
        (evidence/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--image',default='mariadb:12.2.2');parser.add_argument('--evidence',type=Path,required=True)
    options=parser.parse_args();raise SystemExit(0 if run(options.image,options.evidence,qualify)['complete'] else 1)

"""Native reviewed database defaults preserve existing table data and receipts."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import secrets
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'web'))
import config  # noqa: F401
import mysql.connector
from pgadmin.cdeadmin.providers.mysql_family.mysql_catalog import capture,identifier
from pgadmin.cdeadmin.providers.mysql_schema_validation import validate
from pgadmin.cdeadmin.providers.mysql_schema_application import apply_review
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
from pgadmin.cdeadmin.workspace.mysql_schema_plan import plan
from pgadmin.cdeadmin.workspace.mysql_schema_apply import MySQLSchemaApplications


def qualify(options,output):
    output.mkdir(parents=True,exist_ok=True)
    connection=mysql.connector.connect(**{**options,'autocommit':True});cursor=connection.cursor();reader=None
    database='sr_database_'+secrets.token_hex(5);proof={'passed':False,'checks':[]}
    try:
        cursor.execute('CREATE DATABASE '+identifier(database)+' CHARACTER SET utf8mb4');connection.database=database
        cursor.execute('CREATE TABLE t (value VARCHAR(30)) CHARACTER SET utf8mb4')
        cursor.execute('INSERT INTO t VALUES (%s)',('Unicode 🌳',))
        reader=mysql.connector.connect(**{**options,'database':database,'autocommit':True})
        applications=MySQLSchemaApplications(output/'receipts.json')
        for mode,charset,collation in [('', 'latin1','latin1_bin'),('NO_BACKSLASH_ESCAPES','utf8mb4','utf8mb4_bin')]:
            connection.sql_mode=mode
            current=capture(connection,database)
            before=read_catalog(json.dumps(build_export(current['resources'],engine='mysql',endpoint_id='ep',target_id='target',generation=current['generation'])['snapshot']),engine='mysql')
            desired=deepcopy(before);row=next(row for row in desired['rows'].values() if row['kind']=='database')
            row['native']['mysql_change']={'action':'alter-options','character_set':charset,'collation':collation,'encryption':'N'}
            preview=plan(before,desired,before);assert preview['ready_for_review'],preview
            preview.update(validate(reader,preview));assert preview['native_grammar_validated'],preview
            assert preview['native_validation'][0]['validation_stage']=='parse-only'
            invalid=deepcopy(preview);invalid['operations'][0]['source']+=' DEFAULT CHARACTER SET'
            assert not validate(reader,invalid)['native_grammar_validated']
            receipt=applications.review(preview,before,desired,'owner','binding','target')
            request={'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True}
            result=applications.apply(request,'owner','binding',lambda record:apply_review(reader,record))
            assert result['state']=='committed' and result['outcome']['rediscovery_verified'],result
            assert MySQLSchemaApplications(output/'receipts.json').apply(request,'owner','binding',lambda _:(_ for _ in ()).throw(AssertionError('replay')))==result
            cursor.execute('SELECT DEFAULT_CHARACTER_SET_NAME,DEFAULT_COLLATION_NAME,DEFAULT_ENCRYPTION FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s',(database,))
            assert cursor.fetchone()==(charset,collation,'NO')
            cursor.execute('SELECT * FROM t');assert cursor.fetchall()==[('Unicode 🌳',)]
            proof['checks'].append({'sql_mode':mode,'native_defaults_rediscovered':True,'existing_unicode_data_preserved':True,'restart_no_replay':True})
        proof['passed']=True
    finally:
        if reader is not None:reader.close()
        cursor.execute('DROP DATABASE IF EXISTS '+identifier(database));cursor.close();connection.close()
        proof['owned_database_removed']=True
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--connection-json',type=Path,required=True);parser.add_argument('--output-root',type=Path,required=True)
    args=parser.parse_args();qualify(json.loads(args.connection_json.read_text()),args.output_root)

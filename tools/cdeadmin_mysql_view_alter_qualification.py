"""Qualify native ALTER VIEW parsing and durable reviewed deployment without replacement."""
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
    database='sr_view_alter_'+secrets.token_hex(5);proof={'passed':False,'checks':[]}
    try:
        cursor.execute('CREATE DATABASE '+identifier(database)+' CHARACTER SET utf8mb4');connection.database=database
        reader=mysql.connector.connect(**{**options,'database':database,'autocommit':True})
        applications=MySQLSchemaApplications(output/'receipts.json')
        for mode in ('','NO_BACKSLASH_ESCAPES'):
            connection.sql_mode=mode
            cursor.execute('CREATE SQL SECURITY INVOKER VIEW v AS SELECT 42 AS id')
            captured=capture(connection,database)
            exported=build_export(captured['resources'],engine='mysql',endpoint_id='ep',target_id='target',generation=captured['generation'])['snapshot']
            baseline=read_catalog(json.dumps(exported),engine='mysql');desired=deepcopy(baseline)
            row=next(row for row in desired['rows'].values() if row['kind']=='view')
            original=row['native']['definition']
            assert '42' in original
            row['native']['definition']=original.replace('42','43',1)
            preview=plan(baseline,desired,baseline);assert preview['ready_for_review'],preview
            assert preview['operations'][0]['source'].startswith('ALTER ') and 'OR REPLACE' not in preview['operations'][0]['source']
            preview.update(validate(reader,preview))
            assert preview['native_grammar_validated'],preview
            assert preview['native_validation'][0]['validation_stage']=='parse-only'
            assert not preview['native_validation'][0]['preparation_supported']
            invalid=deepcopy(preview);invalid['operations'][0]['source']='ALTER VIEW '+identifier(database)+'.`v` AS SELECT FROM'
            rejected=validate(reader,invalid)
            assert not rejected['native_grammar_validated'] and rejected['native_validation'][0]['error_code']==1064
            cursor.execute('SELECT * FROM v');assert cursor.fetchall()==[(42,)]
            cursor.execute('SHOW CREATE VIEW v');assert cursor.fetchone()[1]==original
            receipt=applications.review(preview,baseline,desired,'owner','binding','target')
            request={'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True}
            result=applications.apply(request,'owner','binding',lambda record:apply_review(reader,record))
            assert result['state']=='committed' and result['outcome']['rediscovery_verified'],result
            assert MySQLSchemaApplications(output/'receipts.json').apply(request,'owner','binding',lambda _:(_ for _ in ()).throw(AssertionError('replay')))==result
            cursor.execute('SELECT * FROM v');assert cursor.fetchall()==[(43,)]
            proof['checks'].append({'sql_mode':mode,'native_grammar_accepted':True,'preparation_supported':False,
                'malformed_query_rejected':True,'validation_without_effects':True,'native_alter_without_replacement':True,'restart_no_replay':True})
            cursor.execute('DROP VIEW v')
        proof['passed']=True
    finally:
        if reader is not None:reader.close()
        cursor.execute('DROP DATABASE IF EXISTS '+identifier(database));cursor.close();connection.close()
        proof['owned_database_removed']=True
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--connection-json',type=Path,required=True);parser.add_argument('--output-root',type=Path,required=True)
    args=parser.parse_args();qualify(json.loads(args.connection_json.read_text()),args.output_root)

"""Native trigger reviewed deployment and metadata replay preserve execution order."""
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
from pgadmin.cdeadmin.workspace.mysql_sql_export import build_metadata


def qualify(options,output):
    output.mkdir(parents=True,exist_ok=True)
    connection=mysql.connector.connect(**{**options,'autocommit':True});cursor=connection.cursor();reader=None
    database='sr_trigger_'+secrets.token_hex(5);proof={'passed':False,'checks':[]}
    def document():
        current=capture(connection,database)
        return read_catalog(json.dumps(build_export(current['resources'],engine='mysql',endpoint_id='ep',target_id='target',generation=current['generation'])['snapshot']),engine='mysql')
    try:
        cursor.execute('CREATE DATABASE '+identifier(database)+' CHARACTER SET utf8mb4');connection.database=database
        reader=mysql.connector.connect(**{**options,'database':database,'autocommit':True})
        applications=MySQLSchemaApplications(output/'receipts.json')
        for mode in ('','NO_BACKSLASH_ESCAPES','ANSI_QUOTES,NO_BACKSLASH_ESCAPES'):
            connection.sql_mode=mode
            cursor.execute('CREATE TABLE t (id INT)')
            cursor.execute('CREATE TRIGGER z_first BEFORE INSERT ON t FOR EACH ROW SET NEW.id=NEW.id+1')
            cursor.execute('CREATE TRIGGER a_second BEFORE INSERT ON t FOR EACH ROW SET NEW.id=NEW.id*10')
            captured=document();metadata=build_metadata(captured)
            assert not metadata['blockers'],metadata
            triggers=[row for row in metadata['statements'] if row['kind']=='trigger']
            assert [row['name'] for row in triggers]==['z_first','a_second']
            cursor.execute('DROP TRIGGER a_second');cursor.execute('DROP TRIGGER z_first')
            # Replay exported native statements in their supplied order, proving
            # actual effects rather than only comparing order metadata.
            for row in triggers:cursor.execute(row['statement'])
            cursor.execute('INSERT INTO t VALUES (1)');cursor.execute('SELECT id FROM t');assert cursor.fetchall()==[(20,)]
            cursor.execute('TRUNCATE t')
            baseline=document();desired=deepcopy(baseline)
            key=next(key for key,row in desired['rows'].items() if row['kind']=='trigger' and row['name']=='a_second')
            desired['rows'][key]['native']['mysql_change']={'action':'drop','confirmation':'a_second'}
            for action in ('drop','create'):
                if action=='create':
                    baseline=document();desired=deepcopy(baseline);desired['rows'][key]=deepcopy(captured['rows'][key])
                preview=plan(baseline,desired,baseline);assert preview['ready_for_review'],preview
                preview.update(validate(reader,preview));assert preview['native_grammar_validated'],preview
                if action in {'create','drop'}:
                    invalid=deepcopy(preview);invalid['operations'][0]['source']+=' +'
                    rejected=validate(reader,invalid);assert not rejected['native_grammar_validated'],rejected
                receipt=applications.review(preview,baseline,desired,'owner','binding','target')
                request={'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True}
                result=applications.apply(request,'owner','binding',lambda record:apply_review(reader,record))
                assert result['state']=='committed' and result['outcome']['rediscovery_verified'],result
                assert MySQLSchemaApplications(output/'receipts.json').apply(request,'owner','binding',lambda _:(_ for _ in ()).throw(AssertionError('replay')))==result
                cursor.execute('INSERT INTO t VALUES (1)');cursor.execute('SELECT id FROM t');assert cursor.fetchall()==[(2 if action=='drop' else 20,)]
                cursor.execute('TRUNCATE t')
                proof['checks'].append({'sql_mode':mode,'operation':action,'native_order_replayed':True,'native_body_effect_verified':True,'restart_no_replay':True})
            cursor.execute('DROP TABLE t')
        proof['passed']=True
    finally:
        if reader is not None:reader.close()
        cursor.execute('DROP DATABASE IF EXISTS '+identifier(database));cursor.close();connection.close()
        proof['owned_database_removed']=True
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--connection-json',type=Path,required=True);parser.add_argument('--output-root',type=Path,required=True)
    args=parser.parse_args();qualify(json.loads(args.connection_json.read_text()),args.output_root)

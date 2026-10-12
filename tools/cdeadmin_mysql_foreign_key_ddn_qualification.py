"""Qualify native DDN foreign-key add/change/drop under exact parent locks."""
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
from pgadmin.cdeadmin.workspace.mysql_schema_plan import plan
from pgadmin.cdeadmin.workspace.mysql_schema_apply import MySQLSchemaApplications


def qualify(options,output):
    output.mkdir(parents=True,exist_ok=True)
    connection=mysql.connector.connect(**{**options,'autocommit':True});cursor=connection.cursor();reader=None
    database='sr_fk_ddn_'+secrets.token_hex(5);proof={'passed':False,'checks':[]}
    try:
        cursor.execute('CREATE DATABASE '+identifier(database)+' CHARACTER SET utf8mb4');connection.database=database
        reader=mysql.connector.connect(**{**options,'database':database,'autocommit':True})
        applications=MySQLSchemaApplications(output/'receipts.json')
        def model():
            captured=capture(connection,database)
            return build_export(captured['resources'],engine='mysql',endpoint_id='ep',target_id='target',generation=captured['generation'],native_model=True)
        for mode in ('','NO_BACKSLASH_ESCAPES'):
            connection.sql_mode=mode
            for table in ('p','q'):cursor.execute('CREATE TABLE '+table+' (id INT PRIMARY KEY)');cursor.execute('INSERT INTO '+table+' VALUES (42)')
            cursor.execute('CREATE TABLE child (id INT PRIMARY KEY, parent_id INT, KEY parent_key(parent_id))');cursor.execute('INSERT INTO child VALUES (1,42)')
            for action in ('create','alter','rename_column','drop'):
                before=model();desired=deepcopy(before);row=next(row for row in desired['rows'].values() if row['kind']=='table' and row['name']=='child')
                if action=='create':
                    source=row['native']['definition'];at=source.rfind(') ENGINE=');assert at>=0
                    row['native']['definition']=source[:at]+', CONSTRAINT `parent_fk` FOREIGN KEY (`parent_id`) REFERENCES `p` (`id`) ON DELETE RESTRICT ON UPDATE CASCADE'+source[at:]
                elif action=='alter':
                    from pgadmin.cdeadmin.workspace.mysql_schema_plan import parts
                    _layout,clauses,_order=parts(row,mode)
                    row['native']['definition']=row['native']['definition'].replace(clauses[('foreign-key','parent_fk')],
                        'CONSTRAINT `parent_fk_changed` FOREIGN KEY (`parent_id`) REFERENCES `q` (`id`) ON DELETE CASCADE ON UPDATE CASCADE')
                elif action=='rename_column':
                    row['native']['definition']=row['native']['definition'].replace('`parent_id`','`parent_ref`')
                    row['native']['mysql_change']={'rename_columns':{'parent_id':'parent_ref'}}
                else:
                    from pgadmin.cdeadmin.workspace.mysql_schema_plan import parts
                    layout,clauses,_order=parts(row,mode)
                    row['native']['definition']=layout['prefix']+'('+','.join(value for key,value in clauses.items() if key!=('foreign-key','parent_fk_changed'))+')'+layout['suffix']
                preview=plan(before,desired,before);assert preview['ready_for_review'],preview
                preview.update(validate(reader,preview));assert preview['native_grammar_validated'],preview
                receipt=applications.review(preview,before,desired,'owner','binding','target')
                request={'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True}
                result=applications.apply(request,'owner','binding',lambda record:apply_review(reader,record))
                assert result['state']=='committed' and result['outcome']['rediscovery_verified'],result
                assert MySQLSchemaApplications(output/'receipts.json').apply(request,'owner','binding',lambda _:(_ for _ in ()).throw(AssertionError('replay')))==result
                cursor.execute("SELECT REFERENCED_TABLE_NAME,DELETE_RULE FROM information_schema.REFERENTIAL_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=%s AND CONSTRAINT_NAME=%s",(database,'parent_fk' if action=='create' else 'parent_fk_changed'))
                observed=cursor.fetchall()
                assert observed==([('p','RESTRICT')] if action=='create' else [('q','CASCADE')] if action in {'alter','rename_column'} else []),observed
                cursor.execute('SELECT * FROM child');assert cursor.fetchall()==[(1,42)]
                cursor.execute("SELECT COLUMN_NAME FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND TABLE_NAME='child' AND INDEX_NAME='parent_key'",(database,))
                assert cursor.fetchall()==[('parent_ref' if action in {'rename_column','drop'} else 'parent_id',)]
                proof['checks'].append({'sql_mode':mode,'foreign_key_operation':action,'native_parent_locking':True,'data_preserved':True,'restart_no_replay':True})
            for table in ('child','p','q'):cursor.execute('DROP TABLE '+table)
        proof['passed']=True
    finally:
        if reader is not None:reader.close()
        cursor.execute('DROP DATABASE IF EXISTS '+identifier(database));cursor.close();connection.close()
        proof['owned_database_removed']=True
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--connection-json',type=Path,required=True);parser.add_argument('--output-root',type=Path,required=True)
    args=parser.parse_args();qualify(json.loads(args.connection_json.read_text()),args.output_root)

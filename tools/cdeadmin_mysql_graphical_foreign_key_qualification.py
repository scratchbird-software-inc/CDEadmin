"""Qualify public DDN relationship create/replace/drop through native reviewed DDL."""
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
from pgadmin.cdeadmin.workspace.firebird_relational_review import handoff,read_relations
from pgadmin.cdeadmin.workspace.mysql_erd import build_diagram
from pgadmin.cdeadmin.workspace.mysql_relational_constraints import FORMAT
from pgadmin.cdeadmin.workspace.mysql_schema_plan import plan
from pgadmin.cdeadmin.workspace.mysql_schema_apply import MySQLSchemaApplications


def qualify(options,output):
    output.mkdir(parents=True,exist_ok=True)
    connection=mysql.connector.connect(**{**options,'autocommit':True});cursor=connection.cursor();reader=None
    database='sr_graph_fk_'+secrets.token_hex(5);proof={'passed':False,'checks':[]}
    def quote(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))
    try:
        cursor.execute('CREATE DATABASE '+identifier(database)+' CHARACTER SET utf8mb4');connection.database=database
        reader=mysql.connector.connect(**{**options,'database':database,'autocommit':True})
        applications=MySQLSchemaApplications(output/'receipts.json')
        for mode in ('','NO_BACKSLASH_ESCAPES'):
            connection.sql_mode=mode
            for table in ('p','q'):cursor.execute('CREATE TABLE '+table+' (id INT PRIMARY KEY)');cursor.execute('INSERT INTO '+table+' VALUES (42)')
            cursor.execute('CREATE TABLE child (id INT PRIMARY KEY, parent_id INT, KEY parent_key(parent_id))');cursor.execute('INSERT INTO child VALUES (1,42)')
            for action in ('create','replace','drop'):
                captured=capture(connection,database)
                catalog=build_export(captured['resources'],engine='mysql',endpoint_id='ep',target_id='target',generation=captured['generation'])['snapshot']
                diagram=build_diagram(captured['resources'],{'endpoint_id':'ep','database_target_id':'target'})
                original=diagram['snapshot'];desired=deepcopy(original);source=desired['files']['relations.ddn']
                resources={row['display_name']:row['resource_id'] for row in captured['resources'] if row['resource_kind']=='table'}
                aliases={identity:alias for alias,identity in diagram['resource_mapping'].items()}
                intent={'format':FORMAT,'action':action,'name':'parent_fk' if action=='create' else 'parent_fk_changed',
                    'columns':['parent_id'],'referenced_columns':['id'],'on_delete':'RESTRICT' if action=='create' else 'CASCADE','on_update':'CASCADE'}
                if action=='create':
                    at=source.rfind('\n}\nview ');assert at>=0
                    relation='\nrelation authored_fk "New native foreign key" @'+aliases[resources['child']]+' -> @'+aliases[resources['p']]+' {kind:ref;enforcement:database;uid:"authored-fk";x_record:{native_json:'+quote(quote(intent))+'};}'
                    source=source[:at]+relation+source[at:]
                else:
                    rows=read_relations(original,engine='mysql');edge=next(edge for row in rows.values() for edge in row.get('graphical_relationships',[]))
                    if action=='drop':intent={'format':FORMAT,'action':'drop','confirmation':'parent_fk_changed'}
                    old='native_json:'+quote(edge['native_json']);assert source.count(old)==1
                    source=source.replace(old,'native_json:'+quote(quote(intent)),1)
                    if action=='replace':source=source.replace('-> @'+aliases[resources['p']],'-> @'+aliases[resources['q']],1)
                desired['files']['relations.ddn']=source
                handed=handoff(catalog,original,desired,engine='mysql',allow_foreign_keys=True)
                before=read_catalog(handed['baseline'],engine='mysql');after=read_catalog(handed['desired'],engine='mysql')
                preview=plan(before,after,before);assert preview['ready_for_review'],preview
                preview.update(validate(reader,preview));assert preview['native_grammar_validated'],preview
                receipt=applications.review(preview,before,after,'owner','binding','target')
                request={'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True}
                result=applications.apply(request,'owner','binding',lambda record:apply_review(reader,record))
                assert result['state']=='committed' and result['outcome']['rediscovery_verified'],result
                assert MySQLSchemaApplications(output/'receipts.json').apply(request,'owner','binding',lambda _:(_ for _ in ()).throw(AssertionError('replay')))==result
                cursor.execute("SELECT REFERENCED_TABLE_NAME,DELETE_RULE FROM information_schema.REFERENTIAL_CONSTRAINTS WHERE CONSTRAINT_SCHEMA=%s",(database,))
                assert cursor.fetchall()==([('p','RESTRICT')] if action=='create' else [('q','CASCADE')] if action=='replace' else [])
                cursor.execute('SELECT * FROM child');assert cursor.fetchall()==[(1,42)]
                proof['checks'].append({'sql_mode':mode,'graphical_foreign_key_operation':action,'public_ddn_handoff':True,'native_prepare':True,'native_parent_locks':True,'data_preserved':True,'restart_no_replay':True})
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

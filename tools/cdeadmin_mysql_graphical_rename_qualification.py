"""Qualify graphical DDN column renames through native durable reviewed application."""
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
from pgadmin.cdeadmin.workspace.mysql_erd import build_diagram
from pgadmin.cdeadmin.workspace.firebird_relational_review import handoff
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
from pgadmin.cdeadmin.workspace.mysql_schema_apply import MySQLSchemaApplications


def qualify(options,output):
    output.mkdir(parents=True,exist_ok=True)
    connection=mysql.connector.connect(**{**options,'autocommit':True})
    cursor=connection.cursor();reader=None;database='sr_graph_rename_'+secrets.token_hex(5)
    proof={'passed':False,'checks':[]}
    try:
        cursor.execute('CREATE DATABASE '+identifier(database)+' CHARACTER SET utf8mb4')
        connection.database=database
        reader=mysql.connector.connect(**{**options,'database':database,'autocommit':True})
        applications=MySQLSchemaApplications(output/'receipts.json')
        for mode in ('','NO_BACKSLASH_ESCAPES'):
            connection.sql_mode=mode
            cursor.execute("CREATE TABLE t (id INT PRIMARY KEY, note VARCHAR(80) NOT NULL DEFAULT 'a;b', calculated INT GENERATED ALWAYS AS (length(note)) STORED, KEY by_note(note(10)), CONSTRAINT valid_note CHECK (length(note) > 0))")
            cursor.execute("INSERT INTO t(id,note) VALUES (42,'native retained')")
            captured=capture(connection,database)
            catalog=build_export(captured['resources'],endpoint_id='ep',target_id='target',generation=captured['generation'],engine='mysql')['snapshot']
            original=build_diagram(captured['resources'],{'endpoint_id':'ep','database_target_id':'target'})['snapshot']
            edited=deepcopy(original)
            source=edited['files']['relations.ddn'];assert source.count('"note" {')==1
            edited['files']['relations.ddn']=source.replace('"note" {','"memo`é" {')
            handed=handoff(catalog,original,edited,engine='mysql',allow_column_renames=True)
            before=read_catalog(handed['baseline'],engine='mysql');desired=read_catalog(handed['desired'],engine='mysql')
            row=next(row for row in desired['rows'].values() if row['kind']=='table')
            assert row['native']['mysql_change']=={'rename_columns':{'note':'memo`é'}}
            preview=plan(before,desired,before)
            assert preview['ready_for_review'] and len(preview['operations'])==1,preview
            preview.update(validate(reader,preview));assert preview['native_grammar_validated'],preview
            receipt=applications.review(preview,before,desired,'owner','binding','target')
            request={'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True}
            result=applications.apply(request,'owner','binding',lambda record:apply_review(reader,record))
            assert result['state']=='committed' and result['outcome']['rediscovery_verified'],result
            cursor.execute('SELECT id,`memo``é`,calculated FROM t');assert cursor.fetchall()==[(42,'native retained',15)]
            cursor.execute('INSERT INTO t(id) VALUES (43)')
            cursor.execute('SELECT `memo``é`,calculated FROM t WHERE id=43');assert cursor.fetchone()==('a;b',3)
            cursor.execute('SHOW CREATE TABLE t');definition=cursor.fetchone()[1]
            assert '`by_note` (`memo``é`(10))' in definition and '`note`' not in definition
            assert MySQLSchemaApplications(output/'receipts.json').apply(request,'owner','binding',lambda _:(_ for _ in ()).throw(AssertionError('replay')))==result
            cursor.execute('DROP TABLE t')
            proof['checks'].append({'sql_mode':mode,'native_rename_verified':True,'graphical_handoff':True,'data_defaults_generated_expression_and_index_preserved':True,'no_replay':True})
        proof['passed']=True
    finally:
        if reader is not None:reader.close()
        cursor.execute('DROP DATABASE IF EXISTS '+identifier(database));cursor.close();connection.close()
        proof['owned_database_removed']=True
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--connection-json',type=Path,required=True)
    parser.add_argument('--output-root',type=Path,required=True)
    args=parser.parse_args();qualify(json.loads(args.connection_json.read_text()),args.output_root)

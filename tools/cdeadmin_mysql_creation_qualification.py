"""Qualify reviewed native CREATE TABLE and uncertain outcomes without replay."""
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
    output.mkdir(parents=True,exist_ok=True);connection=mysql.connector.connect(**{**options,'autocommit':True});cursor=connection.cursor()
    database='sr_create_'+secrets.token_hex(6);reader=None;proof={'passed':False};applications=MySQLSchemaApplications(output/'receipts.json')
    def native():
        captured=capture(connection,database)
        return build_export(captured['resources'],endpoint_id='ep',target_id='db',generation=captured['generation'],engine='mysql',native_model=True)
    def table(model):return next(row for row in model['rows'].values() if row['kind']=='table')
    def review(template):
        before=native();desired=deepcopy(before);row=deepcopy(table(template));desired['rows'][row['resource_id']]=row
        preview=plan(before,desired,before);preview.update(validate(reader,preview));assert preview['native_grammar_validated'] and preview['operations'][0]['operation']=='create'
        cursor.execute('SHOW TABLES');assert not cursor.fetchall()
        return applications.review(preview,before,desired,'owner','binding','target')
    def apply(receipt,callback=None):
        return applications.apply({'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True},'owner','binding',callback or (lambda record:apply_review(reader,record)))
    try:
        cursor.execute('CREATE DATABASE '+identifier(database)+' CHARACTER SET utf8mb4');connection.database=database
        reader=mysql.connector.connect(**{**options,'database':database,'autocommit':True})
        for mode in ('','NO_BACKSLASH_ESCAPES,ANSI_QUOTES'):
            connection.sql_mode=mode
            cursor.execute("CREATE TABLE `t` (`id` int PRIMARY KEY, `note` varchar(80) DEFAULT 'semi;comma,)' COMMENT 'native', `computed` int GENERATED ALWAYS AS ((`id` + 1)) STORED) ENGINE=InnoDB")
            template=native();cursor.execute('DROP TABLE t')
            receipt=review(template);result=apply(receipt)
            assert result['state']=='committed' and result['outcome']['rediscovery_verified']
            assert apply(receipt)==result
            cursor.execute('INSERT INTO t(id) VALUES (42)');cursor.execute('SELECT note,computed FROM t');assert cursor.fetchone()==('semi;comma,)',43)
            cursor.execute('DROP TABLE t');receipt=review(template)
            cursor.execute('CREATE TABLE t(competing int)');stale=apply(receipt);assert stale['state']=='not_dispatched'
            cursor.execute('SHOW COLUMNS FROM t');assert [row[0] for row in cursor.fetchall()]==['competing']
            cursor.execute('DROP TABLE t');receipt=review(template)
            class CursorProxy:
                def __init__(self,cursor):self.cursor=cursor
                def execute(self,source,*args,**kwargs):
                    result=self.cursor.execute(source,*args,**kwargs)
                    prefix=b'CREATE TABLE' if isinstance(source,bytes) else 'CREATE TABLE'
                    if source.startswith(prefix):raise OSError('fixture drops successful CREATE acknowledgement')
                    return result
                def __getattr__(self,key):return getattr(self.cursor,key)
            class ConnectionProxy:
                def __init__(self,connection):object.__setattr__(self,'connection',connection)
                def cursor(self):return CursorProxy(self.connection.cursor())
                def __getattr__(self,key):return getattr(self.connection,key)
                def __setattr__(self,key,value):setattr(self.connection,key,value)
            unknown=apply(receipt,lambda record:apply_review(ConnectionProxy(reader),record));assert unknown['state']=='unknown_outcome'
            cursor.execute('SHOW TABLES');assert cursor.fetchall()==[('t',)]
            assert apply(receipt)==unknown
            cursor.execute('DROP TABLE t')
        proof.update(passed=True,checks=['native PREPARE before CREATE leaves target absent','reviewed ordinary CREATE and SHOW CREATE rediscovery','default and ANSI_QUOTES/NO_BACKSLASH_ESCAPES','exact defaults/generated expressions and data behavior','receipt repeat does not dispatch again','competing native table refuses pre-dispatch without modifying its schema','lost CREATE success acknowledgement remains unknown','unknown receipt is never replayed'])
    finally:
        if reader is not None:reader.close()
        cursor.execute('DROP DATABASE IF EXISTS '+identifier(database));cursor.close();connection.close();proof['owned_database_removed']=True
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--connection-json',type=Path,required=True);parser.add_argument('--output-root',type=Path,required=True)
    args=parser.parse_args();qualify(json.loads(args.connection_json.read_text()),args.output_root)

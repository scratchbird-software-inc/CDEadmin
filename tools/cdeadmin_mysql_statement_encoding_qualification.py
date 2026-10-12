"""Native non-UTF-8 PREPARE/application proof with Unicode control queries."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import secrets
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'web'))
import config  # noqa: F401
import mysql.connector
from pgadmin.cdeadmin.providers.mysql_family.mysql_catalog import capture, identifier
from pgadmin.cdeadmin.providers.mysql_schema_validation import validate
from pgadmin.cdeadmin.providers.mysql_schema_application import apply_review
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_schema_plan import digest
from pgadmin.cdeadmin.workspace.mysql_schema_plan import plan
from pgadmin.cdeadmin.workspace.mysql_schema_apply import MySQLSchemaApplications


def qualify(options, output):
    output.mkdir(parents=True, exist_ok=True)
    connection=mysql.connector.connect(**{**options,'autocommit':True})
    cursor=connection.cursor();database='sr_encoding_é_'+secrets.token_hex(5)
    reader=None;proof={'passed':False,'checks':[]}
    try:
        cursor.execute('CREATE DATABASE '+identifier(database)+' CHARACTER SET utf8mb4')
        connection.database=database
        cursor.execute("CREATE TABLE t (id INT PRIMARY KEY, note VARCHAR(80) DEFAULT 'native') ENGINE=InnoDB")
        cursor.execute('INSERT INTO t(id) VALUES (42)')
        reader=mysql.connector.connect(**{**options,'database':database,'autocommit':True})
        applications=MySQLSchemaApplications(output/'receipts.json')
        for mode in ('','NO_BACKSLASH_ESCAPES'):
            for text,expected in [('é€',True),('漢',False)]:
                connection.sql_mode=mode
                captured=capture(connection,database)
                before=build_export(captured['resources'],endpoint_id='ep',target_id='target',generation=captured['generation'],engine='mysql',native_model=True)
                desired=deepcopy(before)
                row=next(row for row in desired['rows'].values() if row['kind']=='table')
                # Replace the previous comment as well as adding the first one.
                source=row['native']['definition']
                import re
                source=re.sub(r" COMMENT='[^']*'$",'',source)
                row['native']['definition']=source+" COMMENT='"+text+"'"
                preview=plan(before,desired,before)
                assert preview['ready_for_review'] and len(preview['operations'])==1
                preview['operations'][0]['context'].update(character_set_client='latin1',collation_connection='utf8mb4_bin')
                preview['execution_sha256']=digest(preview['operations'])
                if not expected:
                    try: validate(reader,preview)
                    except ValueError as error: assert 'lose' in str(error)
                    else: raise AssertionError('Lossy native encoding accepted')
                    cursor.execute("SELECT TABLE_COMMENT FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME='t'",(database,))
                    assert cursor.fetchone()[0]==''
                else:
                    # Ensure each mode has an actual change to apply.
                    preview.update(validate(reader,preview));assert preview['native_grammar_validated']
                    receipt=applications.review(preview,before,desired,'owner','binding','target')
                    request={'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True}
                    result=applications.apply(request,'owner','binding',lambda record:apply_review(reader,record))
                    assert result['state']=='committed' and result['outcome']['rediscovery_verified'], result
                    cursor.execute("SELECT TABLE_COMMENT FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_NAME='t'",(database,))
                    assert cursor.fetchone()[0]=='é€'
                    cursor.execute("ALTER TABLE t COMMENT=''" )
                cursor.execute('SELECT id,note FROM t');assert cursor.fetchall()==[(42,'native')]
                proof['checks'].append({'sql_mode':mode,'representable':expected,'native_conversion_and_outcome_verified':True})
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
    args=parser.parse_args()
    qualify(json.loads(args.connection_json.read_text()),args.output_root)

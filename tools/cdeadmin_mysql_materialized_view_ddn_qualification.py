"""Qualify native ordinary/materialized-view DDN create, native alter and confirmed drop."""
import argparse
from copy import deepcopy
import json
import hashlib
from pathlib import Path
import secrets
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'web'))
import config  # noqa: F401
import mysql.connector
from pgadmin.cdeadmin.providers.mysql_family.mysql_catalog import capture, identifier
from pgadmin.cdeadmin.providers.mysql_schema_validation import validate
from pgadmin.cdeadmin.providers.mysql_schema_application import apply_review
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.mysql_schema_plan import plan
from pgadmin.cdeadmin.workspace.mysql_schema_apply import MySQLSchemaApplications


def qualify(options,output):
    output.mkdir(parents=True,exist_ok=True)
    connection=mysql.connector.connect(**{**options,'autocommit':True})
    cursor=connection.cursor();reader=None;database='sr_view_kinds_'+secrets.token_hex(5)
    proof={'passed':False,'checks':[]}
    try:
        cursor.execute('CREATE DATABASE '+identifier(database)+' CHARACTER SET utf8mb4')
        connection.database=database
        cursor.execute('CREATE TABLE t (id INT PRIMARY KEY, note VARCHAR(80))')
        cursor.execute("INSERT INTO t VALUES (42,'retained')")
        reader=mysql.connector.connect(**{**options,'database':database,'autocommit':True})
        applications=MySQLSchemaApplications(output/'receipts.json')
        def model():
            captured=capture(connection,database)
            return build_export(captured['resources'],endpoint_id='ep',target_id='target',generation=captured['generation'],engine='mysql',native_model=True)
        for mode,kind in [(mode,kind) for mode in ('','NO_BACKSLASH_ESCAPES','ANSI_QUOTES,NO_BACKSLASH_ESCAPES') for kind in ('view','materialized-view')]:
            connection.sql_mode=mode
            cursor.execute('CREATE ALGORITHM=UNDEFINED '+('MATERIALIZED ' if kind=='materialized-view' else '')+'SQL SECURITY INVOKER VIEW v AS SELECT id,note FROM t WHERE id > 0'+(' WITH CASCADED CHECK OPTION' if kind=='view' else ''))
            template=model();view=next(row for row in template['rows'].values() if row['kind']==kind);key=view['resource_id']
            cursor.execute('DROP VIEW v')
            before=model();desired=deepcopy(before);desired['rows'][key]=deepcopy(view)
            for operation in ('create','alter','drop'):
                if operation!='create':
                    before=model();desired=deepcopy(before)
                    if operation=='alter':
                        desired['rows'][key]['native']['definition']=desired['rows'][key]['native']['definition'].replace('> 0','> 1')
                    else:desired['rows'][key]['native']['mysql_change']={'action':'drop','confirmation':'v'}
                preview=plan(before,desired,before)
                assert preview['ready_for_review'] and len(preview['operations'])==1, preview
                preview.update(validate(reader,preview));assert preview['native_grammar_validated'],preview
                receipt=applications.review(preview,before,desired,'owner','binding','target')
                request={'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True}
                if operation=='alter':
                    # Another cooperating application must not pass the advisory fence.
                    lock=('sr-ddn-'+kind+':'+hashlib.sha256((identifier(database)+'.`v`').encode('utf8')).hexdigest()[:48])[:64]
                    cursor.execute('SELECT GET_LOCK(%s,0)',(lock,));assert cursor.fetchone()[0]==1
                    blocked=applications.review(preview,before,desired,'owner','binding','target')
                    blocked_request={'review_id':blocked['review_id'],'review_digest':blocked['review_digest'],'confirmed':True}
                    result=applications.apply(blocked_request,'owner','binding',lambda record:apply_review(reader,record))
                    assert result['state']=='not_dispatched',result
                    cursor.execute('SELECT RELEASE_LOCK(%s)',(lock,));assert cursor.fetchone()[0]==1
                result=applications.apply(request,'owner','binding',lambda record:apply_review(reader,record))
                assert result['state']=='committed' and result['outcome']['rediscovery_verified'],result
                assert MySQLSchemaApplications(output/'receipts.json').apply(request,'owner','binding',lambda _:(_ for _ in ()).throw(AssertionError('replay')))==result
                if operation!='drop':
                    cursor.execute('SHOW CREATE VIEW v');native=cursor.fetchone()[1]
                    assert 'ALGORITHM=UNDEFINED' in native and 'SQL SECURITY INVOKER' in native and (kind!='view' or 'WITH CASCADED CHECK OPTION' in native)
                    cursor.execute('SELECT * FROM v');assert cursor.fetchall()==[(42,'retained')]
                cursor.execute('SELECT * FROM t');assert cursor.fetchall()==[(42,'retained')]
                proof['checks'].append({'kind':kind,'sql_mode':mode,'operation':operation,'native_outcome_verified':True,'no_replay':True,'existing_data_preserved':True})
        cursor.execute('CREATE SQL SECURITY INVOKER VIEW v AS SELECT id,note FROM t')
        before=model();desired=deepcopy(before)
        row=next(row for row in desired['rows'].values() if row['kind']=='view')
        row['native']['definition']=row['native']['definition'].replace('SQL SECURITY INVOKER','SQL SECURITY DEFINER')
        preview=plan(before,desired,before);preview.update(validate(reader,preview))
        receipt=applications.review(preview,before,desired,'owner','binding','target')
        cursor.execute('ALTER VIEW v AS SELECT id FROM t')
        result=applications.apply({'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True},'owner','binding',lambda record:apply_review(reader,record))
        assert result['state']=='not_dispatched' and 'changed' in result['outcome']['rejection_reason'],result
        cursor.execute('SELECT * FROM v');assert cursor.fetchall()==[(42,)]
        proof['concurrent_native_drift_refused_without_overwrite']=True
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

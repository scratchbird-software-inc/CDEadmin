"""Native PREPARE, durable library DDN apply, drift refusal and restart non-replay."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import secrets
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'web'))
import config  # noqa: F401
from tools.cdeadmin_mysql_family_object_live_orchestrator import _run,_wait_until_ready,_root_connection,_image_identity
from pgadmin.cdeadmin.providers.mysql_family.mysql_catalog import capture
from pgadmin.cdeadmin.providers.mysql_schema_validation import validate
from pgadmin.cdeadmin.providers.mysql_schema_application import apply_review
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.mysql_schema_plan import plan
from pgadmin.cdeadmin.workspace.mysql_schema_apply import MySQLSchemaApplications


def qualify(output):
    output.mkdir(parents=True,exist_ok=True)
    container='sr-lib-ddn-'+secrets.token_hex(6);connection=cursor=None;started=False
    proof={'passed':False,'checks':[],'image':_image_identity('mysql:9.7.0')}
    try:
        _run(['docker','run','-d','--rm','--name',container,'-e','MYSQL_ALLOW_EMPTY_PASSWORD=yes','-p','127.0.0.1::3306','mysql:9.7.0']);started=True
        port=_wait_until_ready('mysql',container,300)
        connection=_root_connection('mysql',port);connection.autocommit=True;cursor=connection.cursor()
        cursor.execute('CREATE DATABASE sr_library_ddn CHARACTER SET utf8mb4');connection.database='sr_library_ddn'
        cursor.execute('CREATE TABLE `library` (id INT PRIMARY KEY)');cursor.execute('INSERT INTO `library` VALUES (42)')
        applications=MySQLSchemaApplications(output/'receipts.json')
        def model():
            captured=capture(connection,'sr_library_ddn')
            return build_export(captured['resources'],engine='mysql',endpoint_id='ep',target_id='target',generation=captured['generation'],native_model=True)
        def review(before,desired):
            preview=plan(before,desired,before);assert preview['ready_for_review'],preview
            preview.update(validate(connection,preview));assert preview['native_grammar_validated'],preview
            receipt=applications.review(preview,before,desired,'owner','binding','target')
            return {'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True}
        for mode in ('','NO_BACKSLASH_ESCAPES'):
            connection.sql_mode=mode
            cursor.execute("CREATE LIBRARY `library` LANGUAGE JAVASCRIPT COMMENT 'initial' AS %s",("export function value() { return 'é €'; }",))
            template=model();library=next(row for row in template['rows'].values() if row['kind']=='library');key=library['resource_id']
            cursor.execute('DROP LIBRARY `library`')
            for operation in ('create','alter','drop'):
                before=model();desired=deepcopy(before)
                if operation=='create':desired['rows'][key]=deepcopy(library)
                elif operation=='alter':desired['rows'][key]['native']['definition']=desired['rows'][key]['native']['definition'].replace("COMMENT 'initial'","COMMENT 'updated é'")
                else:desired['rows'][key]['native']['mysql_change']={'action':'drop','confirmation':'library'}
                request=review(before,desired)
                result=applications.apply(request,'owner','binding',lambda record:apply_review(connection,record))
                assert result['state']=='committed' and result['outcome']['rediscovery_verified'],result
                assert MySQLSchemaApplications(output/'receipts.json').apply(request,'owner','binding',lambda _:(_ for _ in ()).throw(AssertionError('replay')))==result
                cursor.execute('SELECT * FROM `library`');assert cursor.fetchall()==[(42,)]
                proof['checks'].append({'sql_mode':mode,'operation':operation,'native_prepare':True,'rediscovery':True,'restart_no_replay':True,'same_name_table_preserved':True})
        cursor.execute("CREATE LIBRARY `library` LANGUAGE JAVASCRIPT COMMENT 'initial' AS 'export const value=1'")
        before=model();desired=deepcopy(before);key=next(row['resource_id'] for row in desired['rows'].values() if row['kind']=='library')
        desired['rows'][key]['native']['definition']=desired['rows'][key]['native']['definition'].replace("COMMENT 'initial'","COMMENT 'requested'")
        request=review(before,desired)
        cursor.execute("ALTER LIBRARY `library` COMMENT 'external'")
        refused=applications.apply(request,'owner','binding',lambda record:apply_review(connection,record))
        assert refused['state']=='not_dispatched' and not refused['outcome']['rediscovery_verified'],refused
        cursor.execute("SELECT LIBRARY_COMMENT FROM information_schema.LIBRARIES WHERE LIBRARY_SCHEMA='sr_library_ddn' AND LIBRARY_NAME='library'");assert cursor.fetchone()[0]=='external'
        desired['rows'][key]['native']['definition']=desired['rows'][key]['native']['definition'].replace('value=1','value=2')
        blocked=plan(before,desired,before);assert not blocked['ready_for_review'] and 'only COMMENT' in blocked['blockers'][0]['reason']
        cursor.execute('DROP DATABASE sr_library_ddn')
        proof.update(passed=True,external_drift_refused=True,body_replacement_refused=True,external_ddl_fenced=False)
    finally:
        if cursor is not None:cursor.close()
        if connection is not None:connection.close()
        if started:
            (output/'server.log').write_text(_run(['docker','logs',container],check=False).stdout)
            proof['owned_server_stopped']=_run(['docker','stop',container],check=False).returncode==0
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-root',type=Path,required=True)
    qualify(parser.parse_args().output_root)

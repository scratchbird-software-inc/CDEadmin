"""Qualify DDN events with native time zones, durable receipts and drift refusal."""
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
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
from pgadmin.cdeadmin.workspace.mysql_sql_export import build_metadata
from pgadmin.cdeadmin.workspace.mysql_schema_plan import plan
from pgadmin.cdeadmin.workspace.mysql_schema_apply import MySQLSchemaApplications


def qualify(output):
    output.mkdir(parents=True,exist_ok=True)
    container='sr-event-ddn-'+secrets.token_hex(6);connection=cursor=None;started=False
    proof={'passed':False,'checks':[],'image':_image_identity('mysql:9.7.0')}
    try:
        _run(['docker','run','-d','--rm','--name',container,'-e','MYSQL_ALLOW_EMPTY_PASSWORD=yes','-p','127.0.0.1::3306','mysql:9.7.0']);started=True
        port=_wait_until_ready('mysql',container,300)
        connection=_root_connection('mysql',port);connection.autocommit=True;cursor=connection.cursor()
        cursor.execute('CREATE DATABASE sr_event_ddn CHARACTER SET utf8mb4');connection.database='sr_event_ddn'
        cursor.execute('CREATE TABLE events_observed (id INT PRIMARY KEY)')
        applications=MySQLSchemaApplications(output/'receipts.json')
        def model():
            captured=capture(connection,'sr_event_ddn')
            return build_export(captured['resources'],engine='mysql',endpoint_id='ep',target_id='target',generation=captured['generation'],native_model=True)
        def review(before,desired):
            preview=plan(before,desired,before);assert preview['ready_for_review'],preview
            preview.update(validate(connection,preview));assert preview['native_grammar_validated'],preview
            receipt=applications.review(preview,before,desired,'owner','binding','target')
            return {'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True}
        for mode in ('','NO_BACKSLASH_ESCAPES'):
            for zone in ('+05:30','-07:00'):
                connection.sql_mode=mode;connection.time_zone=zone
                cursor.execute("CREATE EVENT `e``é` ON SCHEDULE AT '2037-01-01 12:00:00' ON COMPLETION PRESERVE DISABLE COMMENT 'initial' DO BEGIN INSERT INTO events_observed VALUES(1); SELECT 'é €'; END")
                template=model();event=next(row for row in template['rows'].values() if row['kind']=='event');key=event['resource_id']
                assert event['native']['definition_context']['time_zone']==zone
                document=read_catalog(json.dumps(template['snapshot']),engine='mysql') if 'snapshot' in template else None
                captured=capture(connection,'sr_event_ddn')
                export=build_export(captured['resources'],engine='mysql',endpoint_id='ep',target_id='target',generation=captured['generation'])
                metadata=build_metadata(read_catalog(json.dumps(export['snapshot']),engine='mysql'))
                assert metadata['script_available'] and next(row for row in metadata['statements'] if row['kind']=='event')['context']['time_zone']==zone
                cursor.execute('DROP EVENT `e``é`')
                for operation in ('create','alter','drop'):
                    before=model();desired=deepcopy(before)
                    if operation=='create':desired['rows'][key]=deepcopy(event)
                    elif operation=='alter':desired['rows'][key]['native']['definition']=desired['rows'][key]['native']['definition'].replace("COMMENT 'initial'","COMMENT 'updated é'")
                    else:desired['rows'][key]['native']['mysql_change']={'action':'drop','confirmation':'e`é'}
                    request=review(before,desired)
                    # Intentionally use an unrelated ambient zone before apply.
                    connection.time_zone='+00:00'
                    result=applications.apply(request,'owner','binding',lambda record:apply_review(connection,record))
                    assert result['state']=='committed' and result['outcome']['rediscovery_verified'],result
                    assert MySQLSchemaApplications(output/'receipts.json').apply(request,'owner','binding',lambda _:(_ for _ in ()).throw(AssertionError('replay')))==result
                    if operation!='drop':
                        cursor.execute("SELECT TIME_ZONE,EXECUTE_AT,STATUS FROM information_schema.EVENTS WHERE EVENT_SCHEMA='sr_event_ddn' AND EVENT_NAME='e`é'")
                        observed=cursor.fetchone();assert observed[0]==zone and str(observed[1])=='2037-01-01 12:00:00' and observed[2]=='DISABLED',observed
                    cursor.execute('SELECT COUNT(*) FROM events_observed');assert cursor.fetchone()[0]==0
                    proof['checks'].append({'sql_mode':mode,'time_zone':zone,'operation':operation,'native_prepare':True,'rediscovery':True,'restart_no_replay':True,'event_not_executed':True})
        connection.time_zone='+05:30'
        cursor.execute("CREATE EVENT e ON SCHEDULE AT '2037-01-01 12:00:00' ON COMPLETION PRESERVE DISABLE COMMENT 'initial' DO SELECT 1")
        before=model();desired=deepcopy(before);key=next(row['resource_id'] for row in desired['rows'].values() if row['kind']=='event')
        desired['rows'][key]['native']['definition']=desired['rows'][key]['native']['definition'].replace("COMMENT 'initial'","COMMENT 'requested'")
        request=review(before,desired);cursor.execute("ALTER EVENT e COMMENT 'external'")
        refused=applications.apply(request,'owner','binding',lambda record:apply_review(connection,record))
        assert refused['state']=='not_dispatched',refused
        cursor.execute("SELECT EVENT_COMMENT FROM information_schema.EVENTS WHERE EVENT_SCHEMA='sr_event_ddn' AND EVENT_NAME='e'");assert cursor.fetchone()[0]=='external'
        cursor.execute('DROP DATABASE sr_event_ddn')
        proof.update(passed=True,external_drift_refused=True,external_ddl_fenced=False)
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

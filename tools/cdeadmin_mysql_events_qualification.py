"""Native complete event forms, preservation, context and cross-database rename."""
import argparse
import json
from pathlib import Path
import secrets
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'web'))
import config  # noqa: F401
import mysql.connector
from tools.cdeadmin_mysql_family_object_live_orchestrator import _run,_wait_until_ready,_root_connection,_image_identity
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION,MYSQL_PROFILE,_resources


def qualify(output):
    output.mkdir(parents=True,exist_ok=True)
    container='sr-events-'+secrets.token_hex(6);connection=cursor=None;started=False
    proof={'passed':False,'checks':[],'image':_image_identity('mysql:9.7.0')}
    try:
        _run(['docker','run','-d','--rm','--name',container,'-e','MYSQL_ALLOW_EMPTY_PASSWORD=yes','-p','127.0.0.1::3306','mysql:9.7.0']);started=True
        port=_wait_until_ready('mysql',container,300)
        connection=_root_connection('mysql',port);connection.autocommit=True;cursor=connection.cursor()
        for db in ('sr_events','sr_events_destination'):cursor.execute('CREATE DATABASE '+db+' CHARACTER SET utf8mb4')
        route={'host':'127.0.0.1','port':port,'user':'root','database':'sr_events','autocommit':True,'charset':'utf8mb4','time_zone':'+00:00'}
        class Client:
            config=type('Config',(),{'execute_on_connection':False})()
            def _connect(self,request):return mysql.connector.connect(**request['route'])
            def _safe_close(self,item):item.close()
            def _forget_and_close(self,item):item.close()
        client=Client()
        def execute(operation,draft,target=None):
            request={'resource_kind':'event','operation_id':operation,'draft':draft,'target_resource':target,'_provider_route':route}
            assert not MYSQL_ADMINISTRATION.validate(request)['errors'],MYSQL_ADMINISTRATION.validate(request)
            return MYSQL_ADMINISTRATION.apply(client,MYSQL_ADMINISTRATION.plan(request))
        for mode in ('','NO_BACKSLASH_ESCAPES'):
            route['sql_mode']=mode
            execute('create',{'database':'sr_events','name':'e`é','schedule':"AT '2037-01-01 12:00:00'",'body':'BEGIN SELECT 1; SELECT 2; END',
                'completion':'PRESERVE','status':'DISABLE','time_zone':'+05:30','comment':"initial'\\é",'if_not_exists':True,'definer_user':'root','definer_host':'%'})
            target=next(row for row in _resources(connection,{'route':{}},MYSQL_PROFILE) if row['resource_kind']=='event' and row['display_name']=='e`é')
            assert target['native']['time_zone']=='+05:30' and target['native']['show_create']
            execute('alter',{'comment':'updated é'},target)
            cursor.execute("SELECT STATUS,ON_COMPLETION,TIME_ZONE,EXECUTE_AT,EVENT_DEFINITION,EVENT_COMMENT FROM information_schema.EVENTS WHERE EVENT_SCHEMA='sr_events' AND EVENT_NAME='e`é'")
            observed=cursor.fetchone()
            # MySQL retains the schedule's stored zone when no new schedule is supplied.
            assert observed[0]=='DISABLED' and observed[1]=='PRESERVE' and observed[2]=='+05:30' and str(observed[3])=='2037-01-01 12:00:00' and observed[4]=='BEGIN SELECT 1; SELECT 2; END' and observed[5]=='updated é',observed
            execute('alter',{'clear_comment':True,'status':'DISABLE ON REPLICA'},target)
            cursor.execute("SELECT EVENT_COMMENT,STATUS FROM information_schema.EVENTS WHERE EVENT_SCHEMA='sr_events' AND EVENT_NAME='e`é'");assert cursor.fetchone()==('','REPLICA_SIDE_DISABLED')
            execute('rename',{'new_database':'sr_events_destination','new_name':'renamed`é'},target)
            renamed=next(row for row in _resources(connection,{'route':{}},MYSQL_PROFILE) if row['resource_kind']=='event' and row['display_name']=='renamed`é')
            assert renamed['display_path']==['sr_events_destination','renamed`é']
            execute('drop',{'confirmation':'renamed`é'},renamed)
            assert not any(row['resource_kind']=='event' for row in _resources(connection,{'route':{}},MYSQL_PROFILE))
            proof['checks'].append({'sql_mode':mode,'create_alter_rename_drop':True,'omitted_alter_properties_preserved':True,'native_time_zone':True,'explicit_comment_clear':True,'replica_side_disable':True})
        for db in ('sr_events','sr_events_destination'):cursor.execute('DROP DATABASE '+db)
        proof['passed']=True
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

"""Qualify native components in an owned isolated MySQL server, including restart."""
import argparse
import json
from pathlib import Path
import secrets
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'web'))
import config  # noqa: F401
from tools.cdeadmin_mysql_family_object_live_orchestrator import _run,_wait_until_ready,_root_connection,_image_identity
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION,MYSQL_PROFILE,_resources


def qualify(output):
    output.mkdir(parents=True,exist_ok=True)
    container='sr-components-'+secrets.token_hex(6);connection=cursor=None;started=False
    proof={'passed':False,'checks':[],'image':_image_identity('mysql:9.7.0')}
    component='file://component_validate_password'
    try:
        _run(['docker','run','-d','--rm','--name',container,'-e','MYSQL_ALLOW_EMPTY_PASSWORD=yes','-p','127.0.0.1::3306','mysql:9.7.0']);started=True
        port=_wait_until_ready('mysql',container,300)
        connection=_root_connection('mysql',port);connection.autocommit=True;cursor=connection.cursor()
        def execute(operation,draft,target=None):
            request={'resource_kind':'component','operation_id':operation,'draft':draft,'target_resource':target}
            assert not MYSQL_ADMINISTRATION.validate(request)['errors']
            statement=MYSQL_ADMINISTRATION._compile(request)['statements'][0]
            cursor.execute(statement['source'],statement['parameters'])
        execute('create',{'urns':[component],'settings':[
            {'scope':'GLOBAL','name':'validate_password.length','value':10},
            {'scope':'PERSIST','name':'validate_password.mixed_case_count','value':1}]})
        cursor.execute('SELECT @@GLOBAL.validate_password.length');assert cursor.fetchone()[0]==10
        cursor.execute("SELECT VARIABLE_VALUE FROM performance_schema.persisted_variables WHERE VARIABLE_NAME='validate_password.mixed_case_count'")
        assert cursor.fetchone()[0]=='1'
        resources=_resources(connection,{'route':{}},MYSQL_PROFILE)
        target=next(row for row in resources if row['resource_kind']=='component' and row['display_name']==component)
        assert target['native']['component_id'] is not None and target['display_path']==[component]
        cursor.close();cursor=None;connection.close();connection=None
        _run(['docker','restart',container]);port=_wait_until_ready('mysql',container,300)
        connection=_root_connection('mysql',port);connection.autocommit=True;cursor=connection.cursor()
        cursor.execute('SELECT component_urn FROM mysql.component');assert (component,) in cursor.fetchall()
        cursor.execute('SELECT @@GLOBAL.validate_password.mixed_case_count');assert cursor.fetchone()[0]==1
        execute('drop',{'confirmation':component},target)
        cursor.execute('SELECT component_urn FROM mysql.component');assert (component,) not in cursor.fetchall()
        # Persisted settings are explicit independent state, not silently erased by uninstall.
        cursor.execute('RESET PERSIST IF EXISTS validate_password.mixed_case_count')
        proof.update(passed=True,checks=['install with native GLOBAL/PERSIST options','native component inventory and exact URN','component and persistent setting survive native process restart','uninstall and rediscovery','explicit persisted-setting cleanup'])
    finally:
        if cursor is not None:cursor.close()
        if connection is not None:connection.close()
        if started:
            (output/'server.log').write_text(_run(['docker','logs',container],check=False).stdout)
            stopped=_run(['docker','stop',container],check=False)
            proof['owned_server_stopped']=stopped.returncode==0
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root',type=Path,required=True)
    qualify(parser.parse_args().output_root)

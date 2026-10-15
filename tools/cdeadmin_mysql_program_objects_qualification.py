"""Qualify stored libraries, DDN export and isolated global UDF lifecycle."""
import argparse
import base64
import json
from pathlib import Path
import secrets
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'web'))
import config  # noqa: F401
import mysql.connector
from tools.cdeadmin_mysql_family_object_live_orchestrator import _run,_wait_until_ready,_root_connection,_image_identity
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION,MYSQL_PROFILE,_resources
from pgadmin.cdeadmin.providers.mysql_family.mysql_catalog import capture
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
from pgadmin.cdeadmin.workspace.mysql_sql_export import build_metadata


def qualify(output):
    output.mkdir(parents=True,exist_ok=True)
    container='sr-programs-'+secrets.token_hex(6);connection=cursor=None;started=False
    proof={'passed':False,'checks':[],'image':_image_identity('mysql:9.7.0')}
    try:
        _run(['docker','run','-d','--rm','--name',container,'-e','MYSQL_ALLOW_EMPTY_PASSWORD=yes','-p','127.0.0.1::3306','mysql:9.7.0']);started=True
        port=_wait_until_ready('mysql',container,300)
        connection=_root_connection('mysql',port);connection.autocommit=True;cursor=connection.cursor()
        cursor.execute('CREATE DATABASE sr_programs CHARACTER SET utf8mb4');connection.database='sr_programs'
        route={'host':'127.0.0.1','port':port,'user':'root','database':'sr_programs','autocommit':True,'charset':'utf8mb4'}
        class Client:
            config=type('Config',(),{'execute_on_connection':False})()
            def _connect(self,request):return mysql.connector.connect(**request['route'])
            def _safe_close(self,item):item.close()
            def _forget_and_close(self,item):item.close()
        client=Client()
        def execute(kind,operation,draft,target=None):
            request={'resource_kind':kind,'operation_id':operation,'draft':draft,'target_resource':target,'_provider_route':route}
            assert not MYSQL_ADMINISTRATION.validate(request)['errors'],MYSQL_ADMINISTRATION.validate(request)
            return MYSQL_ADMINISTRATION.apply(client,MYSQL_ADMINISTRATION.plan(request))
        for mode in ('','NO_BACKSLASH_ESCAPES'):
            route['sql_mode']=mode;connection.sql_mode=mode
            source="export function value() { return 'é €'; }"
            execute('library','create',{'database':'sr_programs','name':'text`é','body':source,'comment':"initial'\\é"})
            target={'display_path':['sr_programs','text`é']}
            execute('library','alter',{'comment':'updated é','confirmation':'text`é'},target)
            cursor.execute('SELECT LIBRARY_DEFINITION,LIBRARY_COMMENT FROM information_schema.LIBRARIES WHERE LIBRARY_SCHEMA=%s AND LIBRARY_NAME=%s',('sr_programs','text`é'))
            assert cursor.fetchone()==(source,'updated é')
            execute('library','create',{'database':'sr_programs','name':'binary','body':base64.b64encode(b'\x00\xff\x80wasm').decode(),'source_format':'binary_base64'})
            cursor.execute('SHOW CREATE LIBRARY `binary`');binary=cursor.fetchone()[2];assert '00ff807761736d' in binary.lower()
            captured=capture(connection,'sr_programs')
            document=read_catalog(json.dumps(build_export(captured['resources'],engine='mysql',endpoint_id='ep',target_id='target',generation=captured['generation'])['snapshot']),engine='mysql')
            exported=build_metadata(document);assert exported['script_available'],exported['blockers']
            libs=[row for row in exported['statements'] if row['kind']=='library'];assert len(libs)==2
            resources=_resources(connection,{'route':{'database':'sr_programs'}},MYSQL_PROFILE)
            assert {row['display_name'] for row in resources if row['resource_kind']=='library'}=={'text`é','binary'}
            for name in ('text`é','binary'):execute('library','drop',{'confirmation':name},{'display_path':['sr_programs',name]})
            for block in libs:
                for key,value in block['context'].items():cursor.execute('SET SESSION '+key+'=%s',(value,))
                cursor.execute(block['statement'])
            cursor.execute('SELECT LIBRARY_DEFINITION FROM information_schema.LIBRARIES WHERE LIBRARY_SCHEMA=%s AND LIBRARY_NAME=%s',('sr_programs','text`é'));assert cursor.fetchone()[0]==source
            cursor.execute('SHOW CREATE LIBRARY `binary`');assert cursor.fetchone()[2]==binary
            for name in ('text`é','binary'):execute('library','drop',{'confirmation':name},{'display_path':['sr_programs',name]})
            proof['checks'].append({'sql_mode':mode,'library_create_alter_drop':True,'binary_bytes_preserved':True,'ddn_native_roundtrip':True})
        # Register a shipped native UDF; services may remain unconfigured.
        execute('loadable-function','create',{'name':'keyring_key_type_fetch','return_type':'STRING','library':'keyring_udf.so'})
        target=next(row for row in _resources(connection,{'route':{}},MYSQL_PROFILE) if row['resource_kind']=='loadable-function' and row['display_name']=='keyring_key_type_fetch')
        assert target['native']['registration_origin']=='mysql.func'
        # A stored routine may coexist with the same global UDF name.
        cursor.execute('CREATE FUNCTION keyring_key_type_fetch() RETURNS INTEGER DETERMINISTIC RETURN 42')
        execute('loadable-function','drop',{'confirmation':'keyring_key_type_fetch'},target)
        try:execute('loadable-function','drop',{'confirmation':'keyring_key_type_fetch'},target)
        except RelationalClientError:pass
        else:raise AssertionError('Stale global UDF removal unexpectedly succeeded')
        cursor.execute('SELECT sr_programs.keyring_key_type_fetch()');assert cursor.fetchone()[0]==42
        cursor.execute('SELECT COUNT(*) FROM mysql.func WHERE name=%s',('keyring_key_type_fetch',));assert cursor.fetchone()[0]==0
        proof['checks'].append({'udf_native_create_drop':True,'stale_global_drop_preserves_stored_routine':True,'runtime_service_configuration_claimed':False})
        cursor.execute('DROP DATABASE sr_programs')
        proof['passed']=True
    finally:
        if cursor is not None:cursor.close()
        if connection is not None:connection.close()
        if started:
            (output/'server.log').write_text(_run(['docker','logs',container],check=False).stdout)
            stopped=_run(['docker','stop',container],check=False);proof['owned_server_stopped']=stopped.returncode==0
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output-root',type=Path,required=True)
    qualify(parser.parse_args().output_root)

"""Native installed-component variable controls with both MySQL connectors."""
import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]


def qualify(output):
    import config  # noqa: F401
    from mysql_qualification_support import server,_root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE,MYSQL_ADMINISTRATION as adapter,_create_client,_resources
    from pgadmin.cdeadmin.providers.mysql_family.mysql_server_catalog import capture
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    proof={'complete':False,'full_product_complete':False,'history_testing':'not run','checks':[],
        'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in [
            'tools/cdeadmin_mysql_component_variables_qualification.py',
            'web/pgadmin/cdeadmin/providers/mysql_server_operations.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/provider.py']}}
    try:
        with server(output/'fixture') as (route,_name,owned):
            observer=_root_connection('mysql',route['port']);observer.autocommit=True;cursor=observer.cursor()
            try:
                cursor.execute("INSTALL COMPONENT 'file://component_validate_password'")
                name='validate_password.length'
                def value():
                    cursor.execute('SELECT @@GLOBAL.validate_password.length');runtime=cursor.fetchone()[0]
                    cursor.execute('SELECT VARIABLE_VALUE FROM performance_schema.persisted_variables WHERE VARIABLE_NAME=%s',(name,));row=cursor.fetchone()
                    return runtime,row[0] if row else None
                for pure in (True,False):
                    for mode in ('','NO_BACKSLASH_ESCAPES,ANSI_QUOTES'):
                        client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),None)
                        selected={**route,'use_pure':pure,'sql_mode':mode}
                        def apply(operation,new_value=None):
                            resource=next(row for row in _resources(observer,{'route':{}},MYSQL_PROFILE) if row['resource_kind']=='system-variable' and row['display_name']==name)
                            draft={'confirmation':name}
                            if operation!='reset_persist':draft['value']=new_value
                            request={'resource_kind':'system-variable','operation_id':operation,'target_resource':resource,'draft':draft,'_provider_route':selected}
                            assert not adapter.validate(request)['errors']
                            planned=client.plan_admin_operation(request)
                            if operation!='reset_persist':
                                assert planned['command_preview']['statements'][0]['parameters_redacted']
                            result=adapter.apply(client,planned);assert result['accepted'] and client._connections==[]
                        try:
                            apply('set_global',10);assert value()[0]==10
                            apply('set_persist_only',12);assert value()==(10,'12')
                            apply('set_persist',14);assert value()==(14,'14')
                            resource=next(row for row in capture(observer)['resources'] if row['resource_kind']=='system-variable' and row['display_name']==name)
                            assert resource['native']['catalog_row']['global_value']=='14' and resource['native']['catalog_row']['persisted_value']=='14'
                            apply('reset_persist');assert value()==(14,None)
                            proof['checks'].append({'use_pure':pure,'sql_mode':mode,'native_component_catalog_verified':True,
                                'typed_global_persist_only_persist_and_reset_verified':True,'runtime_and_persistence_distinct':True,
                                'preview_values_redacted':True,'owned_connections_released':True})
                        finally:client.close()
                cursor.execute("UNINSTALL COMPONENT 'file://component_validate_password'")
                proof['native_engine']=owned;proof['complete']=True
            finally:cursor.close();observer.close()
    finally:(output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',required=True,type=Path)
    qualify(parser.parse_args().evidence)

"""Native MySQL column-policy references and component-unavailable evidence."""
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
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION as adapter,MYSQL_PROFILE,_create_client,_resources
    from pgadmin.cdeadmin.providers.mysql_family import column_masking as masking
    from pgadmin.cdeadmin.sdk import RelationalClientError
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    proof={'complete':False,'history_testing':'not run','full_product_complete':False,'checks':[],'source_sha256':{}}
    for name in ['tools/cdeadmin_mysql_column_masking_qualification.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/column_masking.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/administration.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/provider.py']:
        proof['source_sha256'][name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    try:
        with server(output/'fixture') as (route,_name,owned):
            observer=_root_connection('mysql',route['port']);observer.autocommit=True;cursor=observer.cursor()
            schema='owned_mask';table='table . ` é';column='value : . ` é';policy='policy . ` é'
            from pgadmin.cdeadmin.providers.mysql_family.mysql_catalog import identifier
            qualified=identifier(schema)+'.'+identifier(table);column_sql=identifier(column)
            try:
                cursor.execute('CREATE DATABASE '+identifier(schema))
                cursor.execute('CREATE TABLE '+qualified+' (id BIGINT AUTO_INCREMENT PRIMARY KEY,'+column_sql+
                    " VARCHAR(80) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL DEFAULT 'catalog default' COMMENT 'MASKING POLICY literal')")
                cursor.execute('INSERT INTO '+qualified+' ('+column_sql+') VALUES (%s)',('native value',))
                def target():
                    return next(row for row in _resources(observer,{'route':{'database':schema}},MYSQL_PROFILE)
                        if row['resource_kind']=='column' and row['display_name']==column)
                def observed():
                    cursor.execute('SHOW CREATE TABLE '+qualified);ddl=cursor.fetchone()[1]
                    assert ('MASKING POLICY '+identifier(policy) in ddl) or 'MASKING POLICY `external`' in ddl or 'MASKING POLICY `' not in ddl
                    cursor.execute('SELECT * FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s',(schema,table,column))
                    names=[str(row[0]).lower() for row in cursor.description];facts=dict(zip(names,cursor.fetchone()))
                    return ddl,facts
                for pure in (True,False):
                    for mode in ('','NO_BACKSLASH_ESCAPES,ANSI_QUOTES'):
                        client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),None)
                        selected={**route,'use_pure':pure,'sql_mode':mode}
                        def planned(operation,resource=None):
                            resource=resource or target();draft={'confirmation':column}
                            if operation=='set_masking_policy':draft['policy_name']=policy
                            request={'resource_kind':'column','operation_id':operation,'draft':draft,
                                'target_resource':resource,'_provider_route':selected}
                            assert not adapter.validate(request)['errors'];return client.plan_admin_operation(request)
                        try:
                            _,before=observed();resource=target()
                            assert resource['native']['catalog_metadata']==before
                            create=planned('set_masking_policy',resource)
                            assert create['command_preview']['masking_policy_definition']['state']=='component_unavailable'
                            result=adapter.apply(client,create)['column_masking_observation']
                            assert result['rediscovery_verified'] and result['after']['masking_policy']==policy
                            ddl,after=observed();assert 'MASKING POLICY '+identifier(policy) in ddl and after['extra']=='MASKING POLICY'
                            assert {key:value for key,value in before.items() if key!='extra'}=={key:value for key,value in after.items() if key!='extra'}
                            resource=target();assert resource['native']['masking_policy']=={'name':policy,'available':True}
                            try:cursor.execute('SELECT '+column_sql+' FROM '+qualified);cursor.fetchall()
                            except Exception as error:
                                assert error.errno==6561;component_error=error.errno
                            else:raise AssertionError('Missing policy component silently returned a masked value')
                            stale=planned('drop_masking_policy',resource)
                            cursor.execute('ALTER TABLE '+qualified+' ALTER COLUMN '+column_sql+' SET MASKING POLICY `external`')
                            try:adapter.apply(client,stale)
                            except RelationalClientError as error:assert not error.native_dispatched
                            else:raise AssertionError('A changed masking policy was removed without review')
                            removal=planned('drop_masking_policy');removed=adapter.apply(client,removal)['column_masking_observation']
                            assert removed['rediscovery_verified'] and removed['after']['masking_policy'] is None
                            cursor.execute('SELECT '+column_sql+',id FROM '+qualified);assert cursor.fetchall()==[('native value',1)]
                            assert target()['native']['catalog_metadata']==before and client._connections==[]
                            proof['checks'].append({'use_pure':pure,'sql_mode':mode,'all_native_column_facts_verified':len(before),
                                'typed_policy_reference_and_removal_verified':True,'other_column_attributes_preserved':True,
                                'changed_policy_refused_before_dispatch':True,'native_data_preserved':True,
                                'component_unavailable_error':component_error,
                                'task_sources':{'set_masking_policy':create['command_preview']['statements'][0]['source'],
                                    'drop_masking_policy':removal['command_preview']['statements'][0]['source']}})
                        finally:client.close()
                for user,privileges in [('column_editor','SELECT, ALTER'),('column_reader','SELECT')]:
                    cursor.execute('CREATE USER '+identifier(user)+"@'%'")
                    cursor.execute('GRANT '+privileges+' ON '+identifier(schema)+'.* TO '+identifier(user)+"@'%'")
                    client=_create_client(MYSQL_PROFILE,SimpleNamespace(acquire_secret=None),None)
                    try:
                        resource=target()
                        request={'resource_kind':'column','operation_id':'set_masking_policy',
                            'draft':{'confirmation':column,'policy_name':policy},'target_resource':resource,
                            '_provider_route':{**route,'database':schema,'user':user,'use_pure':True}}
                        reviewed=client.plan_admin_operation(request)
                        if user=='column_editor':
                            result=adapter.apply(client,reviewed)['column_masking_observation']
                            assert result['rediscovery_verified']
                            cursor.execute('ALTER TABLE '+qualified+' ALTER COLUMN '+column_sql+' DROP MASKING POLICY')
                        else:
                            try:adapter.apply(client,reviewed)
                            except RelationalClientError as error:
                                assert error.native_dispatched and not error.native_acknowledged and error.errno==1142
                            else:raise AssertionError('Column DDL ignored native ALTER privilege')
                        assert client._connections==[]
                    finally:client.close()
                proof['native_alter_privilege_and_restricted_principal_verified']=True
                proof['native_engine']=owned;proof['complete']=True
            finally:cursor.close();observer.close()
    finally:(output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',required=True,type=Path)
    qualify(parser.parse_args().evidence)

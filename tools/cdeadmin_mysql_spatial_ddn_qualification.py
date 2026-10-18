"""Bounded native MySQL spatial-reference DDN exchange and durable application."""
import argparse
from copy import deepcopy
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
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE,MySQLPilotProvider,_create_client
    from pgadmin.cdeadmin.providers.mysql_family import spatial_reference_systems as srs
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
    from pgadmin.cdeadmin.workspace.mysql_server_plan import plan
    from pgadmin.cdeadmin.workspace.mysql_server_apply import MySQLServerApplications
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    proof={'complete':False,'history_testing':'not run','full_product_complete':False,'checks':[],'source_sha256':{}}
    for name in ['tools/cdeadmin_mysql_spatial_ddn_qualification.py',
            'web/pgadmin/cdeadmin/workspace/mysql_server_plan.py',
            'web/pgadmin/cdeadmin/providers/mysql_server_application.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/mysql_server_catalog.py',
            'web/pgadmin/cdeadmin/providers/mysql_family/provider.py']:
        proof['source_sha256'][name]=hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
    try:
        with server(output/'fixture') as (route,_name,owned):
            observer=_root_connection('mysql',route['port']);observer.autocommit=True;cursor=observer.cursor()
            try:
                cursor.execute(srs.SELECT+' WHERE SRS_ID=4326');built_in=dict(zip(srs.FIELDS,cursor.fetchone()))
                srid=4294967001
                cursor.execute('CREATE DATABASE owned_spatial_ddn')
                permissions=SimpleNamespace(acquire_secret=None,require=lambda *_:None)
                for pure in (True,False):
                    for mode in ('','NO_BACKSLASH_ESCAPES,ANSI_QUOTES'):
                        selected={**route,'use_pure':pure,'sql_mode':mode};client=_create_client(MYSQL_PROFILE,permissions,None)
                        provider=MySQLPilotProvider(SimpleNamespace(endpoint_id='owned-native'),permissions,client)
                        directory=output/('pure' if pure else 'cext')/('strict' if mode else 'default');directory.mkdir(parents=True)
                        store=directory/'reviews.json';applications=MySQLServerApplications(store);calls=[]
                        def model():
                            capture=provider.capture_server_catalog(selected,spatial_reference_ids=[4326,srid])
                            exported=build_export(capture['resources'],endpoint_id='owned-native',target_id='server:'+capture['server_uuid'],
                                generation=capture['generation'],include_system=True,refreshed=True,engine='mysql')
                            encoded=json.dumps(exported['snapshot'],ensure_ascii=False)
                            assert len(encoded.encode())<8*1024*1024
                            result=read_catalog(encoded,engine='mysql')
                            actual=next(row['native']['catalog_row'] for row in result['rows'].values() if row['kind']==srs.KIND and row['native']['catalog_row']['srs_id']==4326)
                            assert actual==built_in
                            return result
                        def prepare(action,draft):
                            baseline=model();desired=deepcopy(baseline)
                            uuid=next(row['native']['server_uuid'] for row in baseline['rows'].values() if row['kind']=='server')
                            key='mysql-server:'+json.dumps([uuid,'spatial-reference-systems',[srid]],separators=(',',':'))
                            if key not in desired['rows']:
                                desired['rows'][key]={'resource_id':key,'kind':srs.KIND,'name':str(srid),'system':'false',
                                    'native':{'section':'spatial-reference-systems','server_uuid':uuid,'system_object':False,'catalog_row':{'srs_id':srid}}}
                            desired['rows'][key]['native']['mysql_change']={'action':action,'draft':draft,'confirmation':str(srid)}
                            preview=plan(baseline,desired,model());preview['endpoint_id']='owned-native'
                            assert preview['ready_for_review'],preview
                            return applications.review(preview,baseline,desired,1,'owned-server')
                        def execute(record,operation):
                            calls.append(operation['resource_id']);return provider.apply_server_operation(selected,record,operation)
                        def apply(receipt):
                            request={'review_id':receipt['review_id'],'review_digest':receipt['review_digest'],'confirmed':True}
                            result=applications.apply(request,1,'owned-server',execute);count=len(calls)
                            assert MySQLServerApplications(store).apply(request,1,'owned-server',execute)['state']==result['state'] and len(calls)==count
                            return result
                        def observed():
                            cursor.execute(srs.SELECT+' WHERE SRS_ID=%s',(srid,));row=cursor.fetchone()
                            return dict(zip(srs.FIELDS,row)) if row else None
                        try:
                            draft={'srs_id':str(srid),'name':"DDN ' ü \\",'definition':built_in['definition'],
                                'include_organization':True,'organization':"org ' é \\",'organization_id':'4294967295',
                                'include_description':True,'description':"description ' é \\"}
                            result=apply(prepare('create',draft));assert result['state']=='acknowledged' and result['outcome']['rediscovery_verified'],result
                            expected={'srs_name':draft['name'],'srs_id':srid,'organization':draft['organization'],
                                'organization_coordsys_id':4294967295,'definition':draft['definition'],'description':draft['description']}
                            assert observed()==expected
                            stale=prepare('alter',{**draft,'name':'must not overwrite'})
                            cursor.execute('CREATE OR REPLACE SPATIAL REFERENCE SYSTEM '+str(srid)+' NAME %s DEFINITION %s',('external',built_in['definition']))
                            refusal=apply(stale);assert refusal['state']=='not_applied' and refusal['statement_outcomes'][0]['outcome']['state']=='not_dispatched'
                            replacement={'name':'reviewed replacement','definition':built_in['definition']}
                            result=apply(prepare('alter',replacement));assert result['state']=='acknowledged' and result['outcome']['rediscovery_verified'],result
                            assert observed()=={'srs_name':replacement['name'],'srs_id':srid,'organization':None,
                                'organization_coordsys_id':None,'definition':built_in['definition'],'description':None}
                            cursor.execute('CREATE TABLE owned_spatial_ddn.used_srs (p POINT SRID '+str(srid)+')')
                            cursor.execute('INSERT INTO owned_spatial_ddn.used_srs VALUES (ST_GeomFromText(%s,%s))',('POINT(10 20)',srid))
                            refused=apply(prepare('drop',{}))
                            assert refused['state']=='not_applied' and refused['statement_outcomes'][0]['state']=='refused' and not refused['outcome']['rediscovery_verified'],refused
                            cursor.execute('SELECT ST_SRID(p),ST_AsText(p) FROM owned_spatial_ddn.used_srs')
                            assert cursor.fetchall()==[(srid,'POINT(10 20)')]
                            cursor.execute('DROP TABLE owned_spatial_ddn.used_srs')
                            result=apply(prepare('drop',{}));assert result['state']=='acknowledged' and result['outcome']['rediscovery_verified'] and observed() is None,result
                            assert client._connections==[]
                            proof['checks'].append({'use_pure':pure,'sql_mode':mode,'bounded_selected_srid_exchange_verified':True,
                                'all_six_native_fields_roundtrip_verified':True,'native_create_replace_drop_verified':True,
                                'changed_baseline_refused_before_dispatch':True,'omitted_replacement_fields_clear_natively':True,
                                'native_in_use_refusal_preserves_data_without_replay':True,
                                'durable_receipt_restart_does_not_redispatch':True})
                        finally:client.close()
                cursor.execute("CREATE USER 'spatial_ddn_reader'@'%'")
                selected={**route,'user':'spatial_ddn_reader'}
                client=_create_client(MYSQL_PROFILE,permissions,None)
                provider=MySQLPilotProvider(SimpleNamespace(endpoint_id='owned-native'),permissions,client)
                store=output/'restricted-reviews.json';applications=MySQLServerApplications(store);calls=[]
                try:
                    result=apply(prepare('create',{'srs_id':str(srid),'name':'native denial','definition':built_in['definition']}))
                    assert result['state']=='not_applied' and result['statement_outcomes'][0]['state']=='refused' and not result['outcome']['rediscovery_verified'],result
                    assert observed() is None and client._connections==[]
                    proof['restricted_principal_native_refusal_without_replay']=True
                finally:client.close()
                proof['native_engine']=owned;proof['complete']=True
            finally:cursor.close();observer.close()
    finally:(output/'proof.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',required=True,type=Path)
    qualify(parser.parse_args().evidence)

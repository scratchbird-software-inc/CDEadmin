"""Owned native MySQL engine diagnostic qualification; no monitoring history tests.

Run core, supplement_mysql_engine_diagnostics_contract.py, refresh the immutable
snapshot, then HTTP. All outputs must be outside the source checkout.
"""
import argparse
from pathlib import Path
from types import SimpleNamespace
import sys
import json
import hashlib
import secrets

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'web'), str(ROOT/'tools')]


def output_area(output):
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Native qualification output belongs outside source')
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    return output


def core(output):
    W = output_area(output); R = ROOT
    import config  # noqa: F401
    from tools.mysql_qualification_support import server, _root_connection
    from tools.mysql_driver_gate_support import provider_access
    from pgadmin.cdeadmin.providers.mysql_family.provider import _create_client, MYSQL_PROFILE, _resources
    from pgadmin.cdeadmin.sdk import RelationalClientError
    proof={'complete':False,'scope':'Owned MySQL9.7.0 fixture; production native catalog and both client implementations validate/plan/apply. Successful execution establishes native parser acceptance for these exact statements; no nonexecuting PREPARE claim. No HTTP/full-product claim. Private text is only hashed.','interfaces':[],'source_sha256':{p:hashlib.sha256((R/p).read_bytes()).hexdigest()for p in ['web/pgadmin/cdeadmin/providers/mysql_family/mysql_engine_diagnostics.py','web/pgadmin/cdeadmin/providers/mysql_family/administration.py','web/pgadmin/cdeadmin/providers/mysql_family/provider.py','web/pgadmin/cdeadmin/ui_descriptors/mysql/operations.json','web/pgadmin/cdeadmin/ui_descriptors/mysql/capabilities.json','tools/cdeadmin_mysql_engine_diagnostics_qualification.py']}}
    try:
     with server(W/'mysql-engine-diagnostics-fixture')as(base_route,name,fixture):
      native=_root_connection('mysql',base_route['port']);native.autocommit=True
      try:
       target=next(x for x in _resources(native,{},MYSQL_PROFILE)if x['resource_kind']=='server');password=secrets.token_urlsafe(24)
       with native.cursor()as c:c.execute("CREATE USER 'owned_diag'@'%' IDENTIFIED BY %s",(password,))
       for pure in [True,False]:
        route,permissions=provider_access({**base_route,'use_pure':pure});client=_create_client(MYSQL_PROFILE,permissions,SimpleNamespace(pool_namespace='owned-engine-diagnostics-'+str(pure)));interface={'use_pure':pure,'templates':{},'checks':[]};proof['interfaces'].append(interface)
        def request(op,engine='InnoDB'):return {'resource_kind':'server','operation_id':op,'target_resource':target,'draft':{'engine':engine,'private_data_confirmed':True,'confirmation':target['display_name']},'_provider_route':route}
        try:
         probe=client._connect({'route':route});interface['native_connection_class']=type(probe).__name__;client._forget_and_close(probe)
         for suffix in ['status','logs','mutex']:
          operation='show_engine_'+suffix;req=request(operation);assert not client.validate_admin_operation(req)['errors'];planned=client.plan_admin_operation(req);interface['templates'][operation]=planned['provider_payload']['compiled']['statements'][0]['source'];response=client.apply_admin_operation(planned);result=response['engine_diagnostic'];assert result['native_acknowledged']and result['complete']and not result['truncated'];assert response['connection_release']['connection_released'];assert result['columns']==['Type','Name','Status'];assert result['execution_identity']['server_uuid']==fixture['server_uuid']
          if suffix=='status':assert result['rows']and result['rows'][0][0]=='InnoDB'
          interface['checks'].append({'operation':operation,'native_parser_accepted_by_execution':True,'row_count':len(result['rows']),'complete':result['complete'],'text_sha256':hashlib.sha256(json.dumps(result['rows']).encode()).hexdigest(),'connection_released':True})
         interface['all_templates']={};interface['all_checks']=[]
         for suffix in ['status','logs','mutex']:
          operation='show_engine_'+suffix;req=request(operation);req['draft'].pop('engine');req['draft']['engine_scope']='ALL';assert not client.validate_admin_operation(req)['errors'];planned=client.plan_admin_operation(req);interface['all_templates'][operation]=planned['provider_payload']['compiled']['statements'][0]['source'];response=client.apply_admin_operation(planned);result=response['engine_diagnostic']
          assert result['native_acknowledged']and result['complete']and not result['truncated'];assert response['connection_release']['connection_released'];assert result['engine']['scope']=='ALL'
          interface['all_checks'].append({'operation':operation,'native_parser_accepted_by_execution':True,'row_count':len(result['rows']),'complete':True,'connection_released':True,'text_sha256':hashlib.sha256(json.dumps(result['rows']).encode()).hexdigest()})
         try:client.plan_admin_operation(request('show_engine_status','not_installed_owned'))
         except RelationalClientError:interface['missing_engine_refused']=True
         else:raise AssertionError('missing engine')
         restricted_route,restricted_permissions=provider_access({**base_route,'use_pure':pure,'user':'owned_diag'},password);restricted=_create_client(MYSQL_PROFILE,restricted_permissions,SimpleNamespace(pool_namespace='owned-engine-diagnostics-restricted-'+str(pure)))
         try:
          for suffix in ['status','logs','mutex']:
           req={**request('show_engine_'+suffix),'_provider_route':restricted_route};plan=restricted.plan_admin_operation(req)
           try:restricted.apply_admin_operation(plan)
           except RelationalClientError as error:
            assert error.native_dispatched and not error.native_acknowledged;assert error.errno in {1044,1045,1142,1227},error.errno;assert error.connection_release['connection_released'];interface['checks'].append({'native_denied':'show_engine_'+suffix,'native_error_code':error.errno,'automatic_retry':error.automatic_retry,'connection_released':True})
           else:raise AssertionError('restricted native access')
          for suffix in ['status','logs','mutex']:
           req={**request('show_engine_'+suffix),'_provider_route':restricted_route};req['draft'].pop('engine');req['draft']['engine_scope']='ALL';plan=restricted.plan_admin_operation(req)
           try:restricted.apply_admin_operation(plan)
           except RelationalClientError as error:
            assert error.native_dispatched and not error.native_acknowledged and error.errno in {1044,1045,1142,1227};assert error.connection_release['connection_released'];interface['all_checks'].append({'native_denied':'show_engine_'+suffix,'native_error_code':error.errno,'automatic_retry':error.automatic_retry,'connection_released':True})
           else:raise AssertionError('Restricted ALL-engine diagnostic admitted')
         finally:restricted.close()
        finally:client.close()
      finally:native.close()
     proof['owned_server_stopped']=fixture['owned_server_stopped'];proof['fixture_image']=fixture['image'];proof['native_version']='9.7.0';proof['complete']=True
    finally:(W/'mysql-engine-diagnostics-native.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof

def http(output):
    W = output_area(output); R = ROOT; O = W/'mysql-engine-http'
    O.mkdir(exist_ok=False)
    from tools.cdeadmin_mysql_dump_verification_qualification import setup_application
    app=setup_application(O)
    from tools.mysql_qualification_support import server,_root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import _resources,MYSQL_PROFILE
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.model import db,User,ServerGroup,Server
    from flask import url_for
    proof={'complete':False,'scope':'Authenticated desktop HTTP server registration/verify, actual descriptor fields and visual validation/review/apply; owned native MySQL9.7.0. No UI/browser claim. Private returned text is only hashed in receipt.','checks':[],'source_sha256':{p:hashlib.sha256((R/p).read_bytes()).hexdigest()for p in ['web/pgadmin/cdeadmin/providers/mysql_family/mysql_engine_diagnostics.py','web/pgadmin/cdeadmin/providers/mysql_family/administration.py','web/pgadmin/cdeadmin/providers/mysql_family/provider.py','web/pgadmin/cdeadmin/ui_descriptors/mysql/operations.json','web/pgadmin/cdeadmin/ui_descriptors/mysql/capabilities.json','tools/cdeadmin_mysql_engine_diagnostics_qualification.py']}}
    try:
     with server(W/'mysql-engine-http-fixture')as(route,name,fixture):
      native=_root_connection('mysql',route['port'])
      try:
       target=next(x for x in _resources(native,{},MYSQL_PROFILE)if x['resource_kind']=='server');password=secrets.token_urlsafe(24)
       with native.cursor()as cursor:
        cursor.execute("CREATE USER 'owned_http'@'%' IDENTIFIED BY %s",(password,));cursor.execute("GRANT ALL PRIVILEGES ON *.* TO 'owned_http'@'%'")
       native.commit();route={**route,'user':'owned_http'}
      finally:native.close()
      with app.test_request_context('/'):
       user=User.query.first();uid=user.id;group=ServerGroup.query.filter_by(user_id=uid).first();app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True,user_id=uid)
       item=Server(user_id=uid,servergroup_id=group.id,name='Owned MySQL engine diagnostics',host=route['host'],port=route['port'],username='owned_http',maintenance_db=None,save_password=0);item._cde_endpoint_registration=registration_profile('mysql-native');item._cde_endpoint_route_configuration={**route,'credential_kinds':['database_password']};db.session.add(item);db.session.commit();url=url_for('NODE-server.cde_workspace_id',gid=group.id,sid=item.id);verify=url_for('NODE-server.verify_endpoint_id',gid=group.id,sid=item.id)
      client=app.test_client()
      with client.session_transaction()as session:session['_user_id']=str(uid);session['_fresh']=True
      verified=client.post(verify,json={'password':password}).get_json();assert verified['success'],verified
      def post(action,request,denied=False):
       response=client.post(url,json={'action':action,'request':request});value=response.get_json()
       if denied:assert not value.get('success');return value
       assert response.status_code==200 and value.get('success'),(action,value);assert response.headers['Cache-Control']=='no-store';return value['data']
      declared=json.loads((R/'web/pgadmin/cdeadmin/ui_descriptors/mysql/operations.json').read_text())['operations']
      for scope in ['ENGINE','ALL']:
       for suffix in ['status','logs','mutex']:
        operation='show_engine_'+suffix;fields=next(x['fields']for x in declared if x['resource_kind']=='server'and x['operation_id']==operation);draft={x['field_id']:x.get('default')for x in fields};draft.update(private_data_confirmed=True,confirmation=target['display_name']);draft['engine_scope']=scope;draft.pop('engine',None)if scope=='ALL'else None;request={'resource_kind':'server','operation_id':operation,'target_resource':target,'draft':draft};assert post('visual_admin_validate',request)['valid'];plan=post('visual_admin_plan',request);assert plan['state']=='ready';result=post('visual_admin_apply',{'plan_id':plan['plan_id'],'plan_digest':plan['plan_digest'],'confirmed':True})['provider_result']['engine_diagnostic'];assert result['native_acknowledged'];assert result['execution_identity']['server_uuid']==fixture['server_uuid'];proof['checks'].append({'operation':operation,'engine_scope':scope,'row_count':len(result['rows']),'complete':result['complete'],'private_text_sha256':hashlib.sha256(json.dumps(result['rows']).encode()).hexdigest()})
        post('visual_admin_apply',{'plan_id':plan['plan_id'],'plan_digest':plan['plan_digest'],'confirmed':True},denied=True)
      invalid={**request,'draft':{**draft,'private_data_confirmed':False}};assert not post('visual_admin_validate',invalid)['valid'];proof['checks'].append('Private access refused; one-use reviewed plan cannot be replayed; no-store responses')
     proof['complete']=True
    finally:(W/'mysql-engine-http.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--stage', choices=('core', 'http'), required=True)
    args = parser.parse_args()
    result = (core if args.stage == 'core' else http)(args.output)
    print(json.dumps({'complete': result['complete'], 'stage': args.stage}))

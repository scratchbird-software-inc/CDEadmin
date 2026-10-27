"""Exact release/environment binding, native review authority and CLI exits."""
from copy import deepcopy
import json
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from tools.tests.test_mysql_schema_plan import captured,table
from pgadmin.cdeadmin.workspace import mysql_deployment as native
from pgadmin.cdeadmin.workspace.mysql_schema_apply import MySQLSchemaApplications
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
from pgadmin.cdeadmin.workspace.mysql_schema_plan import plan
from tools import cdeadmin_mysql_deploy as cli


def text(model):
    resources=[{'resource_id':row['resource_id'],'resource_kind':row['kind'],'display_name':row['name'],
        'display_path':row['path'],'native':row['native']} for row in model['rows'].values()]
    return native.encode(build_export(resources,endpoint_id='endpoint',target_id='target',generation='test',engine='mysql')['snapshot'])


def selected(width=120):
    baseline=captured();desired=deepcopy(baseline)
    table(desired)['native']['definition']=table(desired)['native']['definition'].replace('varchar(80)',f'varchar({width})')
    binding={'owner_id':1,'server_id':7,'endpoint_id':'endpoint','database_target_id':'target','database':'demo`db',
        'server_uuid':'server','runtime_version':'9.7.0','registration_sha256':'configuration'}
    return {'binding':binding,'baseline':text(baseline),'desired':text(desired),'execution':None}


def fixture(tmp_path):
    item=selected();artifact=native.artifact('release.1',{'stage':item})
    store=MySQLSchemaApplications(tmp_path/'native.json');execute=Mock(return_value={'state':'committed','rediscovery_verified':True})
    def preview(_server,request,**_):
        base=read_catalog(request['baseline'],engine='mysql');desired=read_catalog(request['source'],engine='mysql')
        return {**plan(base,desired,base),'native_grammar_validated':True}
    def application(server,action,request):
        if action=='mysql_schema_review':
            return store.review(preview(server,request),read_catalog(request['baseline'],engine='mysql'),
                read_catalog(request['source'],engine='mysql'),1,'native-binding','target')
        if action=='mysql_schema_receipt':return store.get(request['review_id'],1,'native-binding')
        return store.apply({k:v for k,v in request.items() if k!='database_target_id'},1,'native-binding',execute)
    service=NS(mysql_schema_plan=Mock(side_effect=preview),mysql_schema_application=Mock(side_effect=application))
    deployment=native.Deployment(service,NS(id=7),'target');deployment.current_binding=Mock(return_value=deepcopy(item['binding']))
    expected=preview(None,{'baseline':item['baseline'],'source':item['desired']})['execution_sha256']
    return deployment,artifact,execute,expected


def test_capture_uses_the_existing_native_administration_and_execution_permissions(monkeypatch):
    calls=[]
    def require(permission,kind=None):
        assert (permission,kind) in {('administer','resource'),('execute',None)}
        calls.append((permission,kind))
    provider=NS(_require=require,capture_catalog=lambda _: {'resources':[{'resource_kind':'database','native':{
        'catalog_row':{'database_name':'demo','server_uuid':'native','version':'9.7.0'}}}]})
    service=NS(_mysql_catalog_context=lambda *_:(NS(endpoint_id='endpoint'),{'route':{}},provider))
    monkeypatch.setattr(native.MySQLMonitoringHost,'_configuration',lambda _:'configuration')
    result=native.Deployment(service,NS(user_id=1,id=7),'target').current_binding()
    assert result['server_uuid']=='native' and calls==[('administer','resource'),('execute',None)]


def test_artifact_digest_is_reproducible_and_modified_content_cannot_reuse_it():
    item=selected();a=native.artifact('v1',{'stage':item})
    assert a==native.artifact('v1',{'stage':deepcopy(item)})
    assert native.select(a,'stage')==item
    a['version']='v2'
    with pytest.raises(native.DeploymentError,match='fingerprint'):native.select(a,'stage')


@pytest.mark.parametrize('change',[{'database':'other'},{'server_uuid':'other'},{'endpoint_id':'other'},
    {'database_target_id':'other'},{'owner_id':True},{'password':'forbidden'},{'runtime_version':'8.0'}])
def test_exact_native_scope_and_supported_fields_are_required(change):
    item=selected();item['binding'].update(change)
    with pytest.raises(ValueError):native.artifact('v1',{'stage':item})


def test_selection_and_version_never_supply_new_environment_or_deletion_authority():
    item=selected();base=read_catalog(item['baseline'],engine='mysql');desired=deepcopy(base)
    del desired['rows'][table(desired)['resource_id']];item['desired']=text(desired)
    a=native.artifact('v1',{'stage':item});value=native.select(a,'stage')
    result=plan(base,read_catalog(value['desired'],engine='mysql'),base)
    assert not result['operations'] and result['ignored']
    with pytest.raises(native.DeploymentError):native.select(a,'production')
    with pytest.raises(native.DeploymentError):native.artifact('../version',{'stage':item})


def test_unseen_plan_cannot_be_prepared_and_exact_review_is_applied_only_once(tmp_path):
    deployment,a,execute,expected=fixture(tmp_path)
    with pytest.raises(native.DeploymentError,match='displayed plan'):deployment.review(a,'stage','wrong')
    assert not deployment.service.mysql_schema_application.called
    ticket,_=deployment.review(a,'stage',expected)
    with pytest.raises(native.DeploymentError,match='approval'):deployment.apply(a,'stage',ticket,'wrong')
    result=deployment.apply(a,'stage',ticket,ticket['sha256'])
    assert result['state']=='committed' and native.outcome(result)==0
    assert deployment.apply(a,'stage',ticket,ticket['sha256'])==result
    execute.assert_called_once()


def test_registration_change_blocks_private_native_review_and_dispatch(tmp_path):
    deployment,a,execute,expected=fixture(tmp_path);ticket,_=deployment.review(a,'stage',expected)
    deployment.current_binding.return_value['registration_sha256']='replaced'
    with pytest.raises(native.DeploymentError,match='binding'):deployment.apply(a,'stage',ticket,ticket['sha256'])
    execute.assert_not_called()


def test_native_drift_is_preserved_without_attempting_prepare_on_a_blocked_plan(tmp_path):
    deployment,a,execute,_=fixture(tmp_path)
    conflict={'ready_for_review':False,'operations':[],'blockers':[],'conflicts':[{'reason':'native drift'}]}
    deployment.service.mysql_schema_plan=Mock(return_value=conflict)
    ticket,observed=deployment.review(a,'stage','irrelevant')
    assert ticket is None and observed==conflict
    assert deployment.service.mysql_schema_plan.call_args.kwargs=={'validate':False}
    deployment.service.mysql_schema_application.assert_not_called();execute.assert_not_called()


def test_relabelled_old_native_review_cannot_authorize_a_different_artifact(tmp_path):
    deployment,a,execute,expected=fixture(tmp_path);ticket,_=deployment.review(a,'stage',expected)
    other=native.artifact('release.2',{'stage':selected(140)})
    forged=native.sealed({k:v for k,v in {**ticket,'version':'release.2','artifact_sha256':other['sha256']}.items() if k!='sha256'})
    with pytest.raises(native.DeploymentError,match='does not implement'):deployment.apply(other,'stage',forged,forged['sha256'])
    execute.assert_not_called()


def test_modified_ticket_plan_does_not_replace_durable_native_authority(tmp_path):
    deployment,a,execute,expected=fixture(tmp_path);ticket,_=deployment.review(a,'stage',expected)
    ticket['review']['plan']['operations'][0]['source']='DROP DATABASE private'
    ticket=native.sealed({k:v for k,v in ticket.items() if k!='sha256'})
    with pytest.raises(native.DeploymentError,match='durable native review'):deployment.apply(a,'stage',ticket,ticket['sha256'])
    execute.assert_not_called()


@pytest.mark.parametrize('record,code',[({'state':'committed','outcome':{'rediscovery_verified':True}},0),
    ({'state':'committed','outcome':{'rediscovery_verified':False}},5),({'state':'partially_committed'},5),
    ({'state':'unknown_outcome'},5),({'state':'not_dispatched'},4),({'state':'reviewed'},5)])
def test_ci_exit_never_equates_acknowledgement_or_partial_work_with_verified_success(record,code):
    assert native.outcome(record)==code


@pytest.mark.parametrize('source',['{"duplicate":1,"duplicate":2}','{"value":NaN}','{"value":Infinity}'])
def test_ambiguous_or_nonfinite_release_json_is_refused(source):
    with pytest.raises(ValueError):cli.decode(source)


def arguments(path):
    return ['plan','--user','owner','--server-id','7','--target-id','target','--environment','stage',
        '--password-env','NATIVE_PASSWORD','--artifact','artifact','--output',str(path)]


def test_existing_or_symlink_output_is_preserved_before_any_native_access(tmp_path,monkeypatch,capsys):
    target=tmp_path/'report.json';target.write_text('preserved')
    run=Mock();monkeypatch.setattr(cli,'run',run)
    assert cli.main(arguments(target))==2
    assert target.read_text()=='preserved';run.assert_not_called()
    assert json.loads(capsys.readouterr().out)['exit_code']==2
    link=tmp_path/'link';link.symlink_to(target)
    assert cli.main(arguments(link))==2;run.assert_not_called()


def test_report_encoding_failure_cannot_exit_success_or_leak_private_exception(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(cli,'run',lambda *_:(0,{'not-json':object()},{'private':'never printed'}))
    assert cli.main(arguments(tmp_path/'report.json'))==2
    reply=json.loads(capsys.readouterr().out)
    assert reply['exit_code']==2 and reply['error_type']=='TypeError' and 'private' not in reply

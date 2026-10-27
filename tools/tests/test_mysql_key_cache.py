"""Exact cache/index targets, native statuses and independently owned effects."""
from copy import deepcopy
from unittest.mock import Mock
import hashlib

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_key_cache as cache
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MARIADB_ADMINISTRATION
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine
from pgadmin.cdeadmin.sdk import RelationalClientError


def target():
    path=['schema : é','table . ` é']
    return {'resource_kind':'table','resource_id':cache.address(path),'display_path':path,'display_name':path[-1]}


def test_cache_operations_quote_exact_native_names_and_keep_default_distinct_from_a_named_cache():
    resource=target();draft={'indexes':['PRIMARY','index . ` é'],'confirmation':resource['display_name'],'cache_name':'cache . ` é'}
    value=cache.compile_operation('assign_index_cache',draft,resource)
    assert value['statements'][0]['source']=='CACHE INDEX `schema : é`.`table . `` é` INDEX (`PRIMARY`,`index . `` é`) IN `cache . `` é`'
    assert cache.compile_operation('assign_index_cache',{'confirmation':resource['display_name']},resource)['statements'][0]['source'].endswith(' IN DEFAULT')
    assert cache.compile_operation('preload_index_cache',{'confirmation':resource['display_name'],'ignore_leaves':True},resource)['statements'][0]['source']=='LOAD INDEX INTO CACHE `schema : é`.`table . `` é` IGNORE LEAVES'


@pytest.mark.parametrize('change',[{'indexes':['a','a']},{'indexes':'a'},{'indexes':['a\x00b']},{'ignore_leaves':1},{'source':'DROP TABLE t'},{'confirmation':'another'}])
def test_invalid_or_redirected_native_cache_input_cannot_compile(change):
    with pytest.raises(RelationalClientError):cache.compile_operation('preload_index_cache',{'confirmation':target()['display_name'],**change},target())


def test_cache_forms_are_mysql_only_and_admitted_tasks_are_visible():
    objects=MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))['objects']
    table=next(row for row in objects if row['resource_kind']=='table')
    for operation in cache.OPERATIONS:
        assert MYSQL_ADMINISTRATION.supports('table',operation) and not MARIADB_ADMINISTRATION.supports('table',operation)
        item=next(row for row in table['operations'] if row['operation_id']==operation)
        assert item['confirmation_required'] and item['form']['form_id']=='mysql.table.'+operation


def test_existing_interactive_connection_is_rejected_before_any_native_access():
    client=Mock()
    with pytest.raises(RelationalClientError,match='independently owned'):cache.apply(client,{},object())
    client._connect.assert_not_called()


def planned():
    compiled=cache.compile_operation('preload_index_cache',{'confirmation':target()['display_name']},target())
    compiled['mysql_key_cache']['review']={'execution_identity':{'server_uuid':'owned'},'baseline':{'definition_sha256':'exact'}}
    return {'provider_payload':{'route':{'host':'owned'},'compiled':compiled}}


@pytest.mark.parametrize('kind',['ok','native-result-error','before-sql','after-ack','changed-review'])
def test_native_reply_acknowledgement_is_separate_from_status_rows_and_later_failures(monkeypatch,kind):
    client=Mock();query=client._connect.return_value.cursor.return_value
    query.description=[(name,) for name in ('Table','Op','Msg_type','Msg_text')];query.warnings=[]
    query.fetchall.return_value=[('t','preload_keys','status','OK')] if kind=='ok' else [('t','preload_keys','error','native refusal')]
    monkeypatch.setattr(cache,'environment',lambda _:{'server_uuid':'owned'})
    monkeypatch.setattr(cache,'observe',lambda *_:{'definition_sha256':'changed' if kind=='changed-review' else 'exact'})
    if kind=='before-sql':query.execute.side_effect=OSError('owned missing native reply')
    if kind=='after-ack':query.fetchall.side_effect=OSError('owned result stream loss')
    if kind in {'before-sql','after-ack','changed-review'}:
        with pytest.raises(RelationalClientError) as failure:cache.apply(client,planned())
        assert failure.value.native_dispatched==(kind!='changed-review')
        assert failure.value.native_acknowledged==(kind=='after-ack')
        assert failure.value.automatic_retry is False
        if kind=='changed-review':query.execute.assert_not_called()
    else:
        result=cache.apply(client,planned())
        assert result['accepted']==(kind=='ok') and result['index_cache_observation']['native_acknowledged']
        assert result['index_cache_observation']['native_effect_acknowledged']==(kind=='ok')
        assert not result['index_cache_observation']['cache_contents_observed'] and not result['automatic_retry']
    client._forget_and_close.assert_called_once()


def test_mutated_compiled_plan_is_refused_without_connection():
    request=deepcopy(planned());request['provider_payload']['compiled']['statements'][0]['source']='DROP DATABASE mysql'
    client=Mock()
    with pytest.raises(RelationalClientError):cache.apply(client,request)
    client._connect.assert_not_called()


@pytest.mark.parametrize('invalid',['source','interface','incomplete'])
def test_contract_supplement_rejects_changed_production_source_missing_interfaces_and_incomplete_native_receipts(tmp_path,invalid):
    from reference_engine_demos.supplement_mysql_key_cache_contract import supplement
    paths=['mysql_key_cache.py','administration.py','provider.py'];fingerprints={}
    for name in paths:
        relative='web/pgadmin/cdeadmin/providers/mysql_family/'+name
        path=tmp_path/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('owned source')
        fingerprints[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
    interfaces=[{'use_pure':pure,'native_connection_class':'CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection',
        'checks':['qualified native case']*5,'templates':{'assign_index_cache':'CACHE INDEX `d`.`t` IN DEFAULT',
            'preload_index_cache':'LOAD INDEX INTO CACHE `d`.`t`'}} for pure in (True,False)]
    evidence={'complete':invalid!='incomplete','owned_server_stopped':True,'source_sha256':fingerprints,
        'interfaces':interfaces[:1] if invalid=='interface' else interfaces}
    if invalid=='source':next(iter((tmp_path/'web/pgadmin/cdeadmin/providers/mysql_family').iterdir())).write_text('changed source')
    with pytest.raises(ValueError):supplement({},evidence,'owned-summary.json','0'*64,tmp_path)

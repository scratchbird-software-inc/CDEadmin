"""Native named cache values and explicit reviewed runtime effects."""
from copy import deepcopy
from unittest.mock import Mock
import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_key_cache_lifecycle as cache
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION,MARIADB_ADMINISTRATION
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine
from test_mysql_instance import target,UUID


@pytest.mark.parametrize('variable',cache.VARIABLES)
def test_native_prefix_and_variable_are_separately_quoted_and_numbers_stay_exact(variable):
    name='odd . ` cache é'
    value=cache.compile_operation('configure_key_cache',{'cache_name':name,'variable':variable,'value':'18446744073709551615','confirmation':'MySQL'},target())
    statement=value['statements'][0]
    assert statement['source']=='SET GLOBAL `odd . `` cache é`.`'+variable+'` = %s'
    assert statement['parameters']==(2**64-1,)
    default=cache.compile_operation('configure_key_cache',{'cache_name':name,'variable':variable,'value_mode':'DEFAULT','confirmation':'MySQL'},target())
    assert default['statements'][0]['source'].endswith(' = DEFAULT') and not default['statements'][0]['parameters']


@pytest.mark.parametrize('value',['-1','1.5','01',str(2**64),True,2**53,{'sql':'0;SHUTDOWN'}])
def test_invalid_exact_native_numbers_cannot_enter_a_statement(value):
    with pytest.raises(RelationalClientError):cache.compile_operation('configure_key_cache',{'cache_name':'a','value':value,'confirmation':'MySQL'},target())


def test_engine_catalog_has_read_only_inspection_and_confirmed_native_changes():
    catalog=MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))
    server=next(row for row in catalog['objects'] if row['resource_kind']=='server')
    operations={row['operation_id']:row for row in server['operations']}
    for operation in cache.OPERATIONS:
        assert MYSQL_ADMINISTRATION.supports('server',operation) and not MARIADB_ADMINISTRATION.supports('server',operation)
        assert operations[operation]['confirmation_required']==(operation!='inspect_key_cache')
        assert operations[operation]['form']['form_id']=='mysql.server.'+operation
    assert operations['inspect_key_cache']['mutation_class']=='read'


def planned(operation='configure_key_cache'):
    draft={'cache_name':'owned','confirmation':'MySQL'}
    if operation=='configure_key_cache':draft['value']='4194304'
    compiled=cache.compile_operation(operation,draft,target())
    compiled['mysql_key_cache_lifecycle']['review']={'execution_identity':{'server_uuid':UUID},'before':{'native_values':{'key_buffer_size':'0'}}}
    return {'provider_payload':{'route':{'host':'owned'},'compiled':compiled}}


@pytest.mark.parametrize('outcome',['ack-rounded','changed-cache','post-ack-loss','no-reply','inspection-new-values'])
def test_native_actual_values_ack_and_read_only_refresh_have_distinct_meaning(monkeypatch,outcome):
    client=Mock();cursor=client._connect.return_value.cursor.return_value;cursor.warnings=[]
    monkeypatch.setattr(cache,'environment',lambda _:{'server_uuid':UUID})
    calls=0
    def observe(*_):
        nonlocal calls
        calls+=1
        if outcome=='post-ack-loss' and calls==2:raise OSError('owned later read loss')
        return {'native_values':{'key_buffer_size':'4096' if calls==2 or outcome in {'changed-cache','inspection-new-values'} else '0'}}
    monkeypatch.setattr(cache,'observe',observe)
    if outcome=='no-reply':cursor.execute.side_effect=OSError('owned missing reply')
    if outcome in {'changed-cache','post-ack-loss','no-reply'}:
        with pytest.raises(RelationalClientError) as failure:cache.apply(client,planned())
        assert failure.value.native_dispatched==(outcome!='changed-cache') and failure.value.native_acknowledged==(outcome=='post-ack-loss')
        assert not failure.value.automatic_retry
    else:
        result=cache.apply(client,planned('inspect_key_cache' if outcome=='inspection-new-values' else 'configure_key_cache'))
        assert result['key_cache_observation']['native_acknowledged'] and result['key_cache_observation']['after']['native_values']['key_buffer_size']=='4096'
        assert not result['native_implicit_commit'] and not result['key_cache_observation']['server_configuration_persisted']
        if outcome=='inspection-new-values':cursor.execute.assert_not_called()
    client._forget_and_close.assert_called_once()


def test_forged_statement_and_borrowed_session_never_reach_a_native_connection():
    client=Mock();request=deepcopy(planned());request['provider_payload']['compiled']['statements'][0]['source']='SHUTDOWN'
    with pytest.raises(RelationalClientError):cache.apply(client,request)
    with pytest.raises(RelationalClientError):cache.apply(client,planned(),object())
    client._connect.assert_not_called()

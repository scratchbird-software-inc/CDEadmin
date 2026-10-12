"""Scope-bound MySQL generators preserve native identities and execution ownership."""
from copy import deepcopy
import json
import pytest
from pgadmin.cdeadmin.workspace.mysql_test_data import generate,template,literal,FORMAT

def model():
    root={'mapping':'scratchrobin.mysql.catalog@1','endpoint_id':'ep','database_target_id':'db'}
    rows={}
    for name in ('parent','child'):
        columns=[{'column_name':'id','column_type':'bigint unsigned','extra':'auto_increment' if name=='parent' else '',
                    'ordinal_position':1,'is_nullable':'NO'},
            {'column_name':'value','column_type':'varchar(100)','extra':'','ordinal_position':2,'is_nullable':'YES'},
            {'column_name':'calc','column_type':'int','extra':'VIRTUAL GENERATED','generation_expression':'id+1','ordinal_position':3}]
        rows[name]={'resource_id':name,'kind':'table','name':name+'`@','system':'false','native':{
            'database':'demo`db','children':{'COLUMNS':columns,'STATISTICS':[{'index_name':'PRIMARY','non_unique':0,
            'column_name':'id','seq_in_index':1,'sub_part':None}]}}}
    return {'provenance':root,'rows':rows}

def recipe(entries):return {'format':FORMAT,'scope':{'endpoint_id':'ep','database_target_id':'db'},'seed':1,'tables':entries}

def test_parent_defaults_returned_keys_and_exact_values_compile_without_transaction_control():
    value=recipe([{'table':'child','count':2,'columns':{'id':{'kind':'returned','table':'parent','column':'id'},
        'value':{'kind':'constant','value':{'type':'decimal','value':'12345678901234567890.12345678901234567890'}}}},
        {'table':'parent','count':2,'columns':{'id':{'kind':'default'},'value':{'kind':'file','values':["a';\\漢",'second']}}}])
    result=generate(model(),value);source=result['source']
    assert result['rows']==4 and not result['executed']
    assert source.index('INSERT INTO `demo``db`.`parent``@`')<source.index('INSERT INTO `demo``db`.`child``@`')
    assert 'DO LAST_INSERT_ID(0)' in source and 'NULLIF(LAST_INSERT_ID(),0)' in source
    assert '12345678901234567890.12345678901234567890' in source
    assert 'COMMIT;' not in source and 'FOREIGN_KEY_CHECKS' not in source and 'RETURNING' not in source
    assert source==generate(model(),value)['source']
    assert not template(model())['tables'][0]['columns'][2]['insertable']


def test_foreign_scope_cycles_generated_columns_and_unbounded_values_are_refused():
    value=recipe([{'table':'parent','count':1,'columns':{'value':{'kind':'sequential','start':'1','step':'1'}}}])
    changed=deepcopy(value);changed['scope']['database_target_id']='other'
    with pytest.raises(ValueError):generate(model(),changed)
    changed=deepcopy(value);changed['tables'][0]['columns']['calc']={'kind':'constant','value':1}
    with pytest.raises(ValueError,match='Generated'):generate(model(),changed)
    changed=deepcopy(value);changed['tables'][0]['columns']['value']={'kind':'generated','table':'parent','column':'value'}
    with pytest.raises(ValueError,match='cycle'):generate(model(),changed)
    for value in [2**64,1.2,{'type':'binary','value':'invalid?'},{'type':'vector','value':'[NaN]'}]:
        with pytest.raises(ValueError):literal(value)
    assert literal({'type':'binary','value':'AP8='})=="X'00ff'"
    assert 'AS JSON)' in literal({'type':'json','value':'{"n":18446744073709551615}'})


def test_existing_references_require_complete_nonnullable_native_unique_keys():
    value=recipe([{'table':'child','count':1,'columns':{'id':{'kind':'existing','table':'parent','column':'id','order_by':['id']}}}])
    result=generate(model(),value)
    assert 'ORDER BY `id` LIMIT 1 OFFSET 0' in result['source']
    changed=model();changed['rows']['parent']['native']['children']['STATISTICS'].append({
        'index_name':'PRIMARY','non_unique':0,'column_name':None,'expression':'(id + 1)'})
    with pytest.raises(ValueError,match='unique key'):generate(changed,value)


def test_host_captures_owned_native_metadata_without_dispatching_user_sql(monkeypatch):
    import config
    from types import SimpleNamespace
    from unittest.mock import Mock
    from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService,ProviderWorkspaceError
    from pgadmin.cdeadmin.workspace import firebird_catalog_export
    service=object.__new__(ProviderWorkspaceService)
    provider=Mock();provider.capture_catalog.return_value={'resources':[],'generation':'native'}
    service._mysql_catalog_context=Mock(return_value=(SimpleNamespace(endpoint_id='ep'),{'route':{'database':'demo'}},provider))
    monkeypatch.setattr(firebird_catalog_export,'build_export',lambda *args,**kwargs:model())
    server=object();result=service.mysql_test_data(server,{'database_target_id':'db'})
    assert result['format']==FORMAT and not result['executed']
    service._mysql_catalog_context.assert_called_once_with(server,'db')
    assert [call[0] for call in provider.mock_calls]==['capture_catalog']
    service._mysql_catalog_context.side_effect=ProviderWorkspaceError('Foreign owner')
    with pytest.raises(ProviderWorkspaceError,match='Foreign owner'):service.mysql_test_data(server,{'database_target_id':'db'})

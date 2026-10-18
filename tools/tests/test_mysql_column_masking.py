"""Exact native column declarations, policy references and owned DDL admission."""
from copy import deepcopy
from unittest.mock import Mock, patch
import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.mysql_family import column_masking as masking
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MARIADB_ADMINISTRATION
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.visual_admin import catalog_for_engine


def target():
    path = ['schema : é', 'table . ` é', 'value : . ` é']
    return {'resource_id':masking.address(path),'resource_kind':'column',
        'display_path':path,'display_name':path[-1]}


def draft():
    return {'policy_name':'policy . ` é','confirmation':target()['display_name']}


def test_native_column_reference_uses_exact_quoted_identifiers():
    result = masking.compile_operation('set_masking_policy',draft(),target())
    assert result['statements'][0]['source'] == 'ALTER TABLE `schema : é`.`table . `` é` ALTER COLUMN `value : . `` é` SET MASKING POLICY `policy . `` é`'
    removed = masking.compile_operation('drop_masking_policy',{'confirmation':target()['display_name']},target())
    assert removed['statements'][0]['source'].endswith(' DROP MASKING POLICY')


@pytest.mark.parametrize('change',[{'policy_name':''},{'policy_name':'x'*65},
    {'policy_name':'nul\x00name'},{'confirmation':'another'},{'source':'DROP TABLE existing'}])
def test_invalid_native_reference_never_dispatches(change):
    with pytest.raises(RelationalClientError):
        masking.compile_operation('set_masking_policy',{**draft(),**change},target())


@pytest.mark.parametrize('key,value',[('resource_id','column:other'),
    ('display_name','another'),('display_path',['schema : é','another','value : . ` é'])])
def test_native_address_metadata_cannot_redirect_an_operation(key,value):
    resource=target();resource[key]=value
    with pytest.raises(RelationalClientError):
        masking.compile_operation('set_masking_policy',draft(),resource)


@pytest.mark.parametrize('mode',['','NO_BACKSLASH_ESCAPES,ANSI_QUOTES'])
def test_policy_parser_preserves_literal_and_expression_tokens(mode):
    declaration="CREATE TABLE `t` (`c` varchar(80) MASKING POLICY `p`` ; é` DEFAULT 'MASKING POLICY fake' COMMENT 'literal, (value)', `d` int DEFAULT (length('MASKING POLICY')) ) ENGINE=InnoDB"
    policies=masking.policy_clauses(declaration,mode)
    assert policies['c']['name']=='p` ; é' and policies['d']['name'] is None
    without=declaration.replace(' MASKING POLICY `p`` ; é`','')
    assert policies['c']['column_tokens_without_policy']==masking.policy_clause(without,'c',mode)['column_tokens_without_policy']


def test_only_mysql_exposes_policy_reference_controls():
    catalog=MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))
    column=next(row for row in catalog['objects'] if row['resource_kind']=='column')
    assert masking.OPERATIONS <= {row['operation_id'] for row in column['operations']}
    assert all(not MARIADB_ADMINISTRATION.supports('column',operation) for operation in masking.OPERATIONS)


def test_recompiled_review_and_independent_attachment_are_required():
    client=Mock();compiled=masking.compile_operation('set_masking_policy',draft(),target())
    with pytest.raises(RelationalClientError,match='independently owned'):
        masking.apply(client,{},object())
    with pytest.raises(RelationalClientError,match='principal before dispatch'):
        masking.apply(client,{'provider_payload':{'compiled':compiled}})
    modified=deepcopy(compiled);modified['statements'][0]['source']='DROP DATABASE existing'
    with pytest.raises(RelationalClientError,match='operation changed'):
        masking.apply(client,{'provider_payload':{'compiled':modified}})
    client._connect.assert_not_called()


def test_component_absence_is_distinct_from_a_lost_connection():
    cursor=Mock()
    class NativeError(Exception):
        def __init__(self,code):self.errno=code;self.sqlstate='HY000'
    cursor.execute.side_effect=NativeError(6561)
    assert masking.lookup(cursor,'p')['state']=='component_unavailable'
    cursor.execute.side_effect=NativeError(2013)
    with pytest.raises(NativeError):masking.lookup(cursor,'p')


def test_post_acknowledgement_observation_failure_is_not_replayed():
    client=Mock();handle=client._connect.return_value;cursor=handle.cursor.return_value;cursor.warnings=None
    compiled=masking.compile_operation('set_masking_policy',draft(),target())
    identity={'server_uuid':'owned','sql_mode':''};before={'column':{'extra':''}}
    compiled['mysql_column_masking']['review']={'execution_identity':identity,'baseline':before}
    with patch.object(masking,'environment',return_value=identity),patch.object(masking,'observe',side_effect=[before,OSError('read failed')]):
        with pytest.raises(RelationalClientError) as failure:
            masking.apply(client,{'provider_payload':{'compiled':compiled,'route':{'host':'owned'}}})
    assert failure.value.native_dispatched and failure.value.native_acknowledged and failure.value.automatic_retry is False
    cursor.execute.assert_called_once_with(compiled['statements'][0]['source'])
    client._forget_and_close.assert_called_once_with(handle)

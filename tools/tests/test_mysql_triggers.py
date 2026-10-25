"""Native trigger fields never acquire another engine's event/active model."""
import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from test_cdeadmin_visual_admin import context, Permissions
from test_visual_admin_field_contracts import IndexAdapter
from pgadmin.cdeadmin.providers.mysql_family import mysql_triggers as triggers
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MySQLDBAPIClient
from pgadmin.cdeadmin.visual_admin import ProviderVisualAdministration
from pgadmin.cdeadmin.sdk import RelationalClientError

BASE={'name':'trigger`雪','table':['db`雪','table`雪'],'body':'BEGIN SET NEW.id=NEW.id+1; END'}


def test_native_timing_event_order_definer_and_schema_are_separate_slots():
    result=triggers.compile_create({**BASE,'timing':'AFTER','event':'DELETE','order':'FOLLOWS','other_trigger':'anchor`雪',
        'definer_user':'owner`雪','definer_host':'%','if_not_exists':True})
    source=result['statements'][0]['source']
    assert source.startswith('CREATE DEFINER=`owner``雪`@`%` TRIGGER IF NOT EXISTS `db``雪`.`trigger``雪` AFTER DELETE ON `db``雪`.`table``雪` FOR EACH ROW FOLLOWS `anchor``雪`')
    assert 'ACTIVE' not in source and 'POSITION' not in source
    assert triggers.compile_create({**BASE,'events':['INSERT'],'active':True,'position':0})['statements'][0]['source']==triggers.compile_create(BASE)['statements'][0]['source']


@pytest.mark.parametrize('change',[
    {'parent':'different'}, {'event':'TRUNCATE'}, {'events':['INSERT','UPDATE']},
    {'event':'INSERT','events':['INSERT']}, {'timing':'INSTEAD OF'}, {'order':'BEFORE'},
    {'order':'PRECEDES'}, {'other_trigger':'anchor'}, {'active':False}, {'position':1},
    {'position':True}, {'invented':1}, {'body':None}, {'if_not_exists':1},
])
def test_incompatible_or_invented_fields_are_refused(change):
    with pytest.raises(RelationalClientError):triggers.compile_create({**BASE,**change})


class TriggerAdapter(IndexAdapter):
    admin_operation_field_contract=MySQLDBAPIClient.admin_operation_field_contract


def test_typed_and_existing_event_list_inputs_both_reach_native_compiler():
    provider=ProviderVisualAdministration(context(),Permissions(),'mysql','9.7.0',TriggerAdapter(MYSQL_ADMINISTRATION))
    for values in ({'event':'UPDATE'},{'events':['UPDATE'],'active':True,'position':0}):
        request={'resource_kind':'trigger','operation_id':'create','draft':{**BASE,**values},
            '_provider_route':{'host':'owned','user':'operator'}}
        validation=provider.validate(request);assert validation['valid'],validation['errors']
        planned=provider.plan(request);assert ' BEFORE UPDATE ON ' in planned['command_preview']['statements'][0]['source']
    assert not MYSQL_ADMINISTRATION.supports('trigger','alter')

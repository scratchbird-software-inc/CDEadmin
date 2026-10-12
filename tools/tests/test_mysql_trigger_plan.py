"""Native trigger ownership and order are never guessed from generic SQL objects."""
from copy import deepcopy
import json
import pytest
from tools.tests.test_mysql_sql_export import model
from pgadmin.cdeadmin.workspace.mysql_schema_plan import plan
from pgadmin.cdeadmin.workspace.mysql_trigger_plan import compile_trigger
from pgadmin.cdeadmin.workspace.mysql_sql_export import build_metadata


def captured():
    document=model([('table','t','CREATE TABLE `t` (`id` int)',{}),('trigger','tr','CREATE DEFINER=`owner`@`%` TRIGGER `tr` BEFORE INSERT ON `t` FOR EACH ROW SET NEW.id=42',{
        'trigger_identity':{'database':'demo`db','table':'t','timing':'BEFORE','event':'INSERT','action_order':1},
        'definition_context':{'sql_mode':'','character_set_client':'utf8mb4','collation_connection':'utf8mb4_bin'}})])
    row=next(row for row in document['rows'].values() if row['kind']=='trigger');old=row['resource_id']
    parent=next(row['resource_id'] for row in document['rows'].values() if row['kind']=='table')
    row['native']['navigator_parent_resource_id']=parent
    row['resource_id']='mysql:'+json.dumps(['demo`db','trigger',parent,'tr'],separators=(',',':'))
    del document['rows'][old];document['rows'][row['resource_id']]=row
    return document


def trigger(document):return next(row for row in document['rows'].values() if row['kind']=='trigger')


def test_native_trigger_create_drop_bind_exact_table_parent_and_filter_never_deletes():
    desired=captured();before=deepcopy(desired);del before['rows'][trigger(desired)['resource_id']]
    preview=plan(before,desired,before)
    assert preview['ready_for_review'] and '`demo``db`.`tr` BEFORE INSERT ON `t`' in preview['operations'][0]['source']
    assert not plan(desired,before,desired)['operations']
    row=trigger(desired);row['native']['mysql_change']={'action':'drop','confirmation':'tr'}
    assert plan(captured(),desired,captured())['operations'][0]['source']=='DROP TRIGGER `demo``db`.`tr`'


@pytest.mark.parametrize('field,value',[('table','other'),('database','other'),('event','DELETE'),('timing','AFTER')])
def test_trigger_header_cannot_redirect_owner_or_event(field,value):
    row=trigger(captured());row['native']['trigger_identity'][field]=value
    with pytest.raises(ValueError):compile_trigger(row,'create','demo`db')


def test_trigger_edits_and_changed_order_block_native_application():
    before=captured();desired=deepcopy(before);trigger(desired)['native']['definition']+=' '
    assert plan(before,desired,before)['blockers']
    trigger(desired)['native']['mysql_change']={'action':'drop','confirmation':'tr'}
    live=deepcopy(before);trigger(live)['native']['trigger_identity']['action_order']=2
    assert plan(before,desired,live)['conflicts']


@pytest.mark.parametrize('orders,blocked', [([2,1],False),([1,1],True),([None,2],True)])
def test_metadata_export_preserves_native_multi_trigger_order(orders,blocked):
    document=model([('table','t','CREATE TABLE `t` (`id` int)',{}), *[
        ('trigger',name,'CREATE TRIGGER `'+name+'` BEFORE INSERT ON `t` FOR EACH ROW SET NEW.id=42',{
            'catalog_row':{'event_object_schema':'demo`db','event_object_table':'t','action_timing':'BEFORE','event_manipulation':'INSERT','action_order':order},
            'definition_context':{'sql_mode':'','character_set_client':'utf8mb4','collation_connection':'utf8mb4_bin'}})
        for name,order in zip(('a','z'),orders)]])
    result=build_metadata(document)
    assert bool(result['blockers'])==blocked
    if not blocked:assert [row['name'] for row in result['statements'] if row['kind']=='trigger']==['z','a']

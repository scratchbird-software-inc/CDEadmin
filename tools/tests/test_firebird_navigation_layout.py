"""Firebird virtual folders retain native identities and child ownership."""
import test_cdeadmin_provider_navigator as fixtures
from pgadmin.cdeadmin.navigator import resource_children, encode_navigator_state, decode_navigator_state

CATALOG = {'engine_id': 'firebird', 'objects': []}
STATE = {'scope': 'database', 'parent_path': []}

def item(kind, name, path=None, owner=None):
    value = fixtures.resource(kind+':'+name, kind, name, path or [name])
    value['native'] = {'navigator_parent_resource_id': owner} if owner else {}
    return value

def test_roots_and_catalog_relations_are_disjoint():
    data=[item('table','ORDERS'),item('view','OPEN_ORDERS'),item('table','RDB$RELATIONS'),item('metric','MON$DATABASE'),item('table','SEC$USERS'),item('procedure','P'),item('domain','MON$IDLE_TIMEOUT'),item('domain','SEC$USER_NAME')]
    root=resource_children(data,STATE,CATALOG)
    assert [n['label'] for n in root] == ['monitoring','programming','security','system','OPEN_ORDERS','ORDERS']
    for branch, name in [('system','RDB$RELATIONS'),('monitoring','MON$DATABASE'),('security','SEC$USERS')]:
        children=resource_children(data,{**STATE,'scope':'kind','resource_kind':'firebird-folder','virtual_branch':branch},CATALOG)
        actual=[n['label'] for n in children if n['node_type']=='resource']
        assert actual == [name]

def test_database_and_relation_triggers_have_different_parents():
    table=item('table','T')
    data=[table,item('trigger','ON_CONNECT'),item('trigger','T_INSERT',['T','T_INSERT'],table['resource_id'])]
    db=resource_children(data,{**STATE,'scope':'kind','resource_kind':'trigger','virtual_branch':'system'},CATALOG)
    child=resource_children(data,{**STATE,'scope':'kind','resource_kind':'trigger','resource_id':table['resource_id'],'parent_path':['T']},CATALOG)
    assert [n['label'] for n in db]==['ON_CONNECT']
    assert [n['label'] for n in child]==['T_INSERT']

def test_table_and_column_sections_refer_to_real_owner():
    table=item('table','T');column=item('column','C',['T','C'],table['resource_id']);data=[table,column]
    for resource,expected in [(table,['columns','comments','constraints','dependencies','grants','indexes','triggers']),(column,['calculations','comments','constraints','grants'])]:
        nodes=resource_children(data,{**STATE,'scope':'resource','resource_id':resource['resource_id'],'parent_path':resource['display_path']},CATALOG)
        assert [n['label'] for n in nodes]==expected
        for n in nodes:
            if n.get('section'):
                assert n['resource_id']==resource['resource_id']
                assert n['resource'] is resource
                assert not n['has_children']

def test_virtual_state_round_trip_and_other_engines_remain_unchanged():
    state={**STATE,'scope':'kind','resource_kind':'firebird-folder','virtual_branch':'system'}
    assert decode_navigator_state(encode_navigator_state(state))==state
    assert [n['label'] for n in resource_children([item('table','T')],STATE,{'engine_id':'mysql'})]==['Tables']


def test_prefixed_domains_stay_inside_programming_domains():
    data=[item('domain','MON$TIMEOUT'),item('domain','SEC$USER_NAME')]
    state={**STATE,'scope':'kind','resource_kind':'firebird-folder','virtual_branch':'programming'}
    assert all(n['node_type']=='group' for n in resource_children(data,state,CATALOG))
    domains=resource_children(data,{**state,'resource_kind':'domain'},CATALOG)
    assert [n['label'] for n in domains]==['MON$TIMEOUT','SEC$USER_NAME']

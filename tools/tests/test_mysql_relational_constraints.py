"""Native relationship intent keeps exact owner/constraint identities."""
from copy import deepcopy
import json
import pytest
from pgadmin.cdeadmin.workspace.mysql_relational_constraints import relationship_changes,merge_constraints,FORMAT

CURRENT={name:{'resource_id':name,'uid':'mysql:ep:target:'+name,'kind':'table','name':name,'path':['d`é',name]} for name in ('child','parent','other')}
INTENT={'format':FORMAT,'action':'create','name':'fk`é','columns':['pid'],'referenced_columns':['id'],'on_delete':'CASCADE'}
EDGE={'uid':'authored','source':'child','target':'parent','kind':'ref','enforcement':'database','native_json':INTENT}


def original():
    return {**EDGE,'uid':CURRENT['child']['uid']+':foreign-key:'+json.dumps('fk`é',ensure_ascii=False,separators=(',',':')),
        'native_json':[{'constraint_name':'fk`é','column_name':'pid','referenced_column_name':'id'}]}


def test_new_relationship_becomes_exact_native_clause_and_existing_name_collision_refuses():
    changes=relationship_changes([], [EDGE], CURRENT)
    before={'name':'child','native':{'database':'d`é','definition':'CREATE TABLE `child` (`id` int,`pid` int)'}}
    result=merge_constraints(before,deepcopy(before['native']),changes['child'],'')
    assert 'CONSTRAINT `fk``é` FOREIGN KEY (`pid`) REFERENCES `d``é`.`parent` (`id`) ON DELETE CASCADE ON UPDATE RESTRICT' in result['definition']
    with pytest.raises(ValueError,match='already exists'):merge_constraints({'name':'child','native':result},deepcopy(result),changes['child'],'')


def test_existing_relationship_replacement_binds_original_uid_and_drop_requires_exact_name():
    old=original();after={**old,'target':'other','native_json':{**INTENT,'action':'replace','name':'new_fk'}}
    changes=relationship_changes([old],[after],CURRENT)
    assert changes['child'][0]['old_name']=='fk`é' and changes['child'][0]['name']=='new_fk'
    dropped={**old,'native_json':{'format':FORMAT,'action':'drop','confirmation':'fk`é'}}
    assert relationship_changes([old],[dropped],CURRENT)['child'][0]['clause'] is None
    assert relationship_changes([old],[],CURRENT)=={}
    dropped['native_json']['confirmation']='other'
    with pytest.raises(ValueError,match='confirmation'):relationship_changes([old],[dropped],CURRENT)
    old['uid']='forged';after['uid']='forged'
    with pytest.raises(ValueError,match='UID'):relationship_changes([old],[after],CURRENT)


@pytest.mark.parametrize('change',[
    {'enforcement':'application'}, {'target':'missing'}, {'uid':None},
    {'native_json':{**INTENT,'columns':['pid','pid']}},
    {'native_json':{**INTENT,'on_delete':'anything'}},
    {'native_json':{**INTENT,'columns':['pid; DROP']}},
    {'native_json':{**INTENT,'action':'replace'}},
])
def test_unadmitted_or_ambiguous_relationship_intent_refuses(change):
    # A semicolon inside an identifier is safely quoted, not a SQL statement.
    if change.get('native_json',{}).get('columns')==['pid; DROP']:
        result=relationship_changes([],[{**EDGE,**change}],CURRENT)
        assert '`pid; DROP`' in result['child'][0]['clause']
    else:
        with pytest.raises(ValueError):relationship_changes([],[{**EDGE,**change}],CURRENT)

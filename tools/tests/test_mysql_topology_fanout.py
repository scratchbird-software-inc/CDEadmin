"""Native SQL fanout preserves selectors, credentials and unknown targets."""
import json
from types import SimpleNamespace
import uuid

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_topology as native
from pgadmin.cdeadmin.providers.mysql_family import mysql_topology_fanout as fanout
from pgadmin.cdeadmin.workspace.mysql_topology_jobs import TopologyJobs


def selected(context='cluster', instances='all', options=None):
    arguments=['SELECT 9223372036854775808 AS wide, \'雪\' AS body',instances]
    if options is not None:arguments.append(options)
    return native.options({'operation':context+'.execute','arguments_json':json.dumps(arguments),
        'target_confirmation':str(uuid.uuid4())})


@pytest.mark.parametrize('context',['cluster','cluster_set','replica_set'])
def test_native_fanout_is_reviewed_and_requires_independent_server_work_clearance(context):
    value=selected(context)
    assert native.parse(value['arguments_json'])[0]=="SELECT 9223372036854775808 AS wide, '雪' AS body"
    assert native.CALLS[value['operation']]['method']=='execute'
    assert native.CALLS[value['operation']]['read_only'] is False
    assert value['operation'] in native.SERVER_WORK_CALLS
    assert value['operation'] not in native.RECOVERY_CALLS
    with pytest.raises(native.BinlogArchiveError,match='server'):
        TopologyJobs.acknowledge(object(),{'options':value,'server_recovery_quiescence':None},{},{})


@pytest.mark.parametrize('instances',[
    'host:3306','root:private@host:3306',[],None,True,[1],
    [{'server_id':True}],[{'server_id':0}],[{'server_id':1,'password':'private'}],
    [{'server_id':1}]*129,
])
def test_fanout_addresses_and_credentials_cannot_bypass_registered_selection(instances):
    with pytest.raises(native.BinlogArchiveError):selected(instances=instances)


def test_explicit_selection_and_exclusion_bind_every_registered_identity():
    value=selected(instances=[{'server_id':5},{'server_id':2},{'server_id':5}],
        options={'exclude':[{'server_id':3}],'dryRun':True,'timeout':17})
    assert native.member_ids(value)==[2,3,5]
    assert native.parse(value['arguments_json'])[1]==[{'server_id':5},{'server_id':2},{'server_id':5}]
    with pytest.raises(native.BinlogArchiveError):selected(options={'exclude':['arbitrary:3306']})


def test_native_context_keywords_remain_native_and_case_is_preserved():
    for name in fanout.KEYWORDS:
        assert native.parse(selected(instances=name.upper())['arguments_json'])[1]==name.upper()


def test_private_uri_conversion_preserves_selector_order_and_native_sql_text():
    converted=[]
    def uri(definition):
        converted.append(definition)
        return 'private-uri:'+definition['password']
    namespace={'shell':SimpleNamespace(unparse_uri=uri)}
    exec(fanout.native_source(),namespace)
    arguments=['SELECT 9223372036854775808',[{'server_id':2},{'server_id':1},{'server_id':2}],
        {'exclude':[{'server_id':1}],'dryRun':False,'timeout':0}]
    prepared={1:{'password':'one'},2:{'password':'two'}}
    result=namespace['native_fanout'](arguments,prepared)
    assert result==['SELECT 9223372036854775808',['private-uri:two','private-uri:one','private-uri:two'],
        {'exclude':['private-uri:one'],'dryRun':False,'timeout':0}]
    assert converted==[prepared[2],prepared[1],prepared[2],prepared[1]]


def test_cluster_set_options_follow_its_native_context_instead_of_cluster_tags():
    common={'operation':'cluster_set.set_option','target_confirmation':str(uuid.uuid4())}
    value=native.options({**common,'arguments_json':'["replicationAllowedHost","%"]'})
    assert native.parse(value['arguments_json'])==['replicationAllowedHost','%']
    with pytest.raises(native.BinlogArchiveError,match='routing options'):
        native.options({**common,'arguments_json':'["tag:not_a_clusterset_option",true]'})

"""Account secrets, exact identities and native state admission boundaries."""
import json
import uuid

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_topology as native
from pgadmin.cdeadmin.providers.mysql_family import mysql_topology_accounts as accounts


def selected(**changes):
    return native.options({'operation':'cluster.setup_admin_account',
        'arguments_json':json.dumps([{'user':'quoted`雪', 'host':'%'}]),
        'target_confirmation':str(uuid.uuid4()), **changes})


@pytest.mark.parametrize('context',['cluster','replica_set','cluster_set'])
@pytest.mark.parametrize('method',['setup_admin_account','setup_router_account'])
def test_native_account_modes_are_retained_without_inline_credentials(context,method):
    value=selected(operation=context+'.'+method,account_password_mode='set')
    assert value['account_password_mode']=='set'
    assert native.parse(value['arguments_json'])==[{'user':'quoted`雪','host':'%'}]
    assert native.CALLS[value['operation']]['account'] is True
    assert selected(operation=value['operation'])['account_password_mode']=='preserve'


@pytest.mark.parametrize('changes',[
    {'account_password_mode':[]}, {'account_password_mode':'unknown'},
    {'arguments_json':'[{"user":"name","host":"%","password":"must-not-be-retained"}]'},
    {'arguments_json':'["name@%"]'}, {'arguments_json':'[{"user":"name"}]'},
    {'arguments_json':'[{"user":"name","host":false}]'},
    {'arguments_json':'[{"user":"name","host":"%"},{"password":"must-not-be-retained"}]'},
    {'operation':'cluster.set_option','arguments_json':'["tag:name",1]','account_password_mode':'set'},
])
def test_untyped_account_identities_and_retained_password_fields_are_refused(changes):
    with pytest.raises(native.BinlogArchiveError):selected(**changes)


def fixture(monkeypatch, *, writable=True, member_role='PRIMARY', cs_role=None):
    calls=[]
    def query(_connection,source,parameters=()):
        calls.append((source,parameters))
        if 'v2_this_instance' in source:return [{'cluster_id':'native-cluster','cluster_type':'gr'}]
        if '@@global.read_only' in source:return [{'read_only':'0' if writable else '1','super_read_only':'0'}]
        if 'replication_group_members' in source:return [{'role':member_role,'state':'ONLINE'}]
        if 'v2_cs_members' in source:return [] if cs_role is None else [{'role':cs_role,'invalidated':'0'}]
        if 'information_schema.COLUMNS' in source:return [
            {'name':'authentication_string','datatype':'text'},
            {'name':'password_last_changed','datatype':'timestamp'}]
        if 'FROM mysql.user WHERE' in source:return [{'user':'quoted`雪','host':'%','fingerprint':'a'*64}]
        if source.startswith('SHOW GRANTS'):return [{'grant':'GRANT SELECT ON *.* TO `quoted``雪`@`%`'}]
        raise AssertionError('Unexpected account query')
    monkeypatch.setattr(accounts,'rows',query)
    return calls


def test_account_state_uses_bound_values_and_server_hashes_with_timezone_independent_timestamps(monkeypatch):
    calls=fixture(monkeypatch)
    result=accounts.capture(object(),{'user':'quoted`雪','host':'%'},'cluster')
    assert result['exists'] is True and result['native_grants']
    digest=next(source for source,_ in calls if 'FROM mysql.user WHERE' in source)
    assert 'SHA2(CONCAT_WS' in digest and 'UNIX_TIMESTAMP(`password_last_changed`)' in digest
    assert 'quoted`雪' not in digest
    assert calls[-1][1]==('quoted`雪','%')
    assert 'a'*64 in json.dumps(result)
    assert all(query['parameters']==['quoted`雪','%'] for query in result['queries'][-2:])


@pytest.mark.parametrize('changes',[{'writable':False},{'member_role':'SECONDARY'},{'cs_role':'REPLICA'}])
def test_nonprimary_or_nonwritable_registrations_do_not_admit_account_writes(monkeypatch,changes):
    calls=fixture(monkeypatch,**changes)
    with pytest.raises(native.BinlogArchiveError):accounts.capture(object(),{'user':'name','host':'%'},'cluster')
    assert not any('FROM mysql.user WHERE' in source for source,_ in calls)

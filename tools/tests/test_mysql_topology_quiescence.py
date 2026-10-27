"""Positive native visibility, original process binding and recovery clearance."""
import hashlib
import json
from types import SimpleNamespace

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_topology_quiescence as native


class Queries:
    def __init__(self):
        self.pid='812';self.marker={'name':'owned_nonce','value':'owned-value'}
        self.identity=['owned-uuid','9.7.0','root@%','NONE']
        self.enabled=1;self.size=512;self.thread='21';self.connection='31';self.process=True
        self.attributes=[['owned_nonce','owned-value'],['_pid',self.pid],['_client_name','libmysql'],['program_name','mysqlsh']]
        self.counters=[['Performance_schema_session_connect_attrs_lost','0'],['Performance_schema_thread_instances_lost','0']]
        self.original_present=False;self.reused_thread=False;self.sessions=[];self.clone=[['1','Completed','native-start','native-end','55']]
        self.calls=[];self.fail=None;self.extra_grants=[]
    def __call__(self,source,parameters=()):
        self.calls.append((source,parameters))
        if self.fail and self.fail in source:raise PermissionError('Native observer denied')
        if source.startswith('SELECT @@server_uuid'):return [self.identity+[self.enabled,self.thread,self.connection,self.size]]
        if source.startswith('SELECT ATTR_NAME'):return self.attributes
        if source.startswith('SHOW GRANTS'):return [['GRANT '+('SELECT, PROCESS' if self.process else 'SELECT')+' ON *.* TO `root`@`%`']]+[[value] for value in self.extra_grants]
        if 'global_status' in source:return self.counters
        if 'performance_schema.threads' in source:
            return [['11']] if self.original_present and not ('JOIN performance_schema.session_connect_attrs' in source and self.reused_thread) else []
        if "ATTR_NAME='_pid'" in source:return self.sessions
        if 'information_schema.PLUGINS' in source:return [['ACTIVE']]
        if 'performance_schema.clone_status' in source:return self.clone
        raise AssertionError(source)


def original(query):
    return {'admitted':True,'profile':native.native_profile(query,query.marker,int(query.pid))}


def connection(query,monkeypatch):
    monkeypatch.setattr(native,'rows',lambda _connection,source,parameters=():[
        {str(index):value for index,value in enumerate(row)} for row in query(source,parameters)])
    return SimpleNamespace(_cdeadmin_observer_attribute=query.marker)


@pytest.mark.parametrize('change',[
    {'enabled':0},{'size':0},{'thread':'0'},{'connection':'0'},{'attributes':[]},
    {'attributes':[['owned_nonce','owned-value'],['_pid','different']]},{'process':False},
    {'counters':[]}, {'counters':[['Performance_schema_session_connect_attrs_lost','-1']]},
])
def test_missing_native_visibility_is_never_treated_as_an_empty_server(change):
    query=Queries()
    for key,value in change.items():setattr(query,key,value)
    with pytest.raises(ValueError):native.native_profile(query,query.marker,int(query.pid))


def test_effective_native_role_grants_are_requested_without_replacing_source_role_state():
    query=Queries();query.identity[3]='`observer_role`@`%`'
    assert native.native_profile(query,query.marker,int(query.pid))['identity']['active_role']==query.identity[3]
    assert any(source=='SHOW GRANTS FOR CURRENT_USER() USING `observer_role`@`%`' for source,_ in query.calls)
    assert not any(source.startswith('SET ') for source,_ in query.calls)


@pytest.mark.parametrize('grant',[
    'GRANT SELECT (`x, PROCESS ON *.* TO y`) ON `db`.`t` TO `root`@`%`',
    'GRANT `x, PROCESS ON *.* TO y`@`%` TO `root`@`%`',
])
def test_quoted_catalog_identities_cannot_invent_native_process_visibility(grant):
    query=Queries();query.process=False;query.extra_grants=[grant]
    with pytest.raises(ValueError,match='process visibility'):native.native_profile(query,query.marker,int(query.pid))


@pytest.mark.parametrize('blocker',['original_thread','session','clone','loss','denied','identity'])
def test_server_work_or_unqualified_evidence_keeps_original_recovery_protected(monkeypatch,blocker):
    query=Queries();witness=original(query)
    if blocker=='original_thread':query.original_present=True
    if blocker=='session':query.sessions=[['55']]
    if blocker=='clone':query.clone[0][1]='In Progress'
    if blocker=='loss':query.counters[0][1]='1'
    if blocker=='denied':query.fail='clone_status'
    if blocker=='identity':query.identity[0]='another-server'
    observed=native.observe(connection(query,monkeypatch),witness,int(query.pid))
    assert observed['idle'] is not True
    if blocker in {'loss','denied','identity'}:assert observed['qualified'] is False


def test_original_thread_and_process_sessions_must_be_absent_with_native_clone_idle(monkeypatch):
    query=Queries();witness=original(query)
    observed=native.observe(connection(query,monkeypatch),witness,int(query.pid))
    assert observed['qualified'] and observed['idle'] and observed['original_thread_absent']
    assert not observed['remaining_native_session_ids'] and observed['clone_status'][0][1]=='Completed'
    assert not any(source.startswith(('KILL ','SET ','CLONE ','UPDATE ')) for source,_ in query.calls)


def test_clone_restart_thread_id_reuse_is_not_attributed_to_the_original_native_client(monkeypatch):
    query=Queries();witness=original(query);query.original_present=True;query.reused_thread=True
    observed=native.observe(connection(query,monkeypatch),witness,int(query.pid))
    assert observed['qualified'] and observed['idle'] and observed['original_thread_absent']
    assert any('JOIN performance_schema.session_connect_attrs' in source and parameters==(witness['profile']['thread_id'],query.pid)
        for source,parameters in query.calls)


@pytest.mark.parametrize('changed',['pid','cleanup','credential_cleanup','script','nonce'])
def test_owner_witness_cannot_be_adopted_from_another_or_unconfirmed_native_invocation(tmp_path,changed):
    script=tmp_path/'native-topology.py';script.write_text('native owned script')
    reference={'policy':native.POLICY,'nonce':'owned-nonce','script_sha256':hashlib.sha256(script.read_bytes()).hexdigest()}
    witness={'policy':native.POLICY,'nonce':'owned-nonce','pid':812,'targets':{}}
    record={'native_topology_owner':reference,'interrupted_utility_observation':{
        'cleanup_confirmed':True,'credential_file_cleanup_confirmed':True,'native_process_identity':{'pid':812}}}
    if changed=='pid':record['interrupted_utility_observation']['native_process_identity']['pid']=813
    if changed=='cleanup':record['interrupted_utility_observation']['cleanup_confirmed']=False
    if changed=='credential_cleanup':record['interrupted_utility_observation']['credential_file_cleanup_confirmed']=False
    if changed=='script':script.write_text('changed native script')
    if changed=='nonce':witness['nonce']='another-owner'
    (tmp_path/native.OWNER_FILE).write_text(json.dumps(witness))
    with pytest.raises(native.BinlogArchiveError):native.load(tmp_path,record)

"""Native slot commands, acknowledgement durability and catalog boundaries."""
import json
import threading
import time
import uuid

import pytest

from pgadmin.cdeadmin.providers.postgresql.continuity import ContinuityError
from pgadmin.cdeadmin.providers.postgresql.continuity_transport import ContinuityTransport
from pgadmin.cdeadmin.workspace.postgresql_continuity_jobs import PostgreSQLContinuityJobs
from pgadmin.cdeadmin.workspace import postgresql_continuity_slots as slots


@pytest.mark.parametrize('operation,value',[
    ('wal_slot_create',{'slot':'UPPER'}),('wal_slot_create',{'slot':'ü'}),
    ('wal_slot_create',{'slot':'a'*64}),('wal_slot_create',{'slot':'a; DROP'}),
    ('wal_slot_drop',{'slot':'owned','if_not_exists':True}),('wal_slot_create',{'slot':'owned','if_not_exists':'true'}),
    ('wal_slot_create',{'slot':'owned','timeout_seconds':True}),('wal_slot_create',{'slot':'owned','timeout_seconds':0}),
    ('wal_slot_unknown',{'slot':'owned'}),('wal_slot_create',[]),
])
def test_inadmissible_native_slot_options_never_become_commands(operation,value):
    with pytest.raises(ContinuityError):slots.options(operation,value)


@pytest.fixture
def fixture(tmp_path,monkeypatch):
    class Tools:
        calls=[]
        def __init__(self,_paths):pass
        def identify(self,*_args):return {'available':True,'version':'(PostgreSQL) 18.6','executable_sha256':'a'*64}
        def execute(self,name,_directory,arguments,**kwargs):
            self.calls.append((name,arguments));kwargs['progress']({'pid':999999999,'process_create_time':0})
            return {'return_code':0,'process_observation':{'return_code':0,'cleanup_confirmed':True}}
    monkeypatch.setattr(slots,'PhysicalTools',Tools)
    from pgadmin.cdeadmin.workspace import postgresql_continuity_jobs as module
    monkeypatch.setattr(module,'PhysicalTools',Tools)
    monkeypatch.setattr(slots,'observe',lambda *_args:{'slot_name':'owned_slot','slot_type':'physical','active':False})
    jobs=PostgreSQLContinuityJobs(tmp_path/'jobs.json',tmp_path/'artifacts')
    source={'system_identifier':'18446744073709551615','server_version':180003,'timeline':1,'lsn':'0/100',
            'tablespaces':[],'slot_snapshot':None,'slot_identity':None}
    endpoint=str(uuid.uuid4())
    try:yield jobs,source,endpoint,Tools
    finally:jobs.close()


def review(fixture,operation='wal_slot_create',**options):
    jobs,source,endpoint,_tools=fixture
    return jobs.review({'operation':operation,'options':{'slot':'owned_slot',**options}},1,endpoint,source,'configuration',{})


def request(record):
    return {'job_id':record['job_id'],'review_digest':record['review_digest'],'confirmed':True}


def wait(fixture,record):
    jobs,_source,endpoint,_tools=fixture;deadline=time.monotonic()+5
    while True:
        result=jobs.get(record['job_id'],1,endpoint)
        if result['state'] not in {'active','dispatching','cancel_requested'} and result.get('slot_observation_state')!='pending':return result
        if time.monotonic()>deadline:raise AssertionError('Owned slot worker failed to stop')
        time.sleep(.01)


@pytest.mark.parametrize('operation',['wal_slot_create','wal_slot_drop'])
def test_native_slot_arguments_and_repeated_start_preserve_one_dispatch(fixture,operation):
    jobs,source,endpoint,tools=fixture
    selected=review(fixture,operation,if_not_exists=operation=='wal_slot_create')
    assert selected['execution_host']['kind']=='application-host'
    assert 'archive' not in selected['options'] and selected['inputs']==[]
    jobs.start(request(selected),1,endpoint,source,'configuration',ContinuityTransport({}))
    result=wait(fixture,selected)
    assert result['state']=='completed' and result['native_utility_acknowledged']
    assert result['slot_observation_state']=='observed' and result['slot_observation']['slot_type']=='physical'
    assert result['remote_finality_inferred'] is False
    expected=['--no-password','--verbose','--slot=owned_slot','--create-slot' if operation=='wal_slot_create' else '--drop-slot']
    if operation=='wal_slot_create':expected.append('--if-not-exists')
    assert tools.calls==[('pg_receivewal',expected)]
    lease=ContinuityTransport({});jobs.start(request(selected),1,endpoint,source,'configuration',lease)
    assert lease.closed and len(tools.calls)==1


def test_slot_replacement_is_a_new_review_but_live_counters_do_not_change_identity(fixture):
    jobs,source,endpoint,_tools=fixture
    selected=review(fixture)
    changed={**source,'slot_identity':{'slot_name':'owned_slot','slot_type':'logical'}}
    lease=ContinuityTransport({})
    with pytest.raises(ContinuityError,match='target or registration changed'):
        jobs.start(request(selected),1,endpoint,changed,'configuration',lease)
    assert lease.closed
    changed={**source,'slot_snapshot':{'slot_name':'owned_slot','restart_lsn':'0/200'},'lsn':'0/200'}
    jobs.start(request(selected),1,endpoint,changed,'configuration',ContinuityTransport({}))
    assert wait(fixture,selected)['state']=='completed'


def test_a_current_slot_does_not_establish_an_interrupted_command_outcome(fixture,monkeypatch):
    jobs,source,endpoint,tools=fixture
    def interrupted(*_args,**_kwargs):return {'return_code':-15,'process_observation':{'cleanup_confirmed':False,'cancel_requested':True}}
    monkeypatch.setattr(tools,'execute',interrupted)
    selected=review(fixture)
    jobs.start(request(selected),1,endpoint,source,'configuration',ContinuityTransport({}))
    result=wait(fixture,selected)
    assert result['state']=='unknown' and not result['native_utility_acknowledged']
    assert result['slot_observation']['slot_name']=='owned_slot' and result['automatic_retry'] is False


def test_catalog_failure_does_not_rewrite_the_durable_native_acknowledgement(fixture,monkeypatch):
    jobs,source,endpoint,_tools=fixture
    def unavailable(*_args):raise RuntimeError('private-password-canary')
    monkeypatch.setattr(slots,'observe',unavailable)
    selected=review(fixture)
    jobs.start(request(selected),1,endpoint,source,'configuration',ContinuityTransport({}))
    result=wait(fixture,selected)
    assert result['state']=='completed' and result['native_utility_acknowledged']
    assert result['slot_observation_state']=='unavailable' and 'private-password-canary' not in json.dumps(result)


def test_a_late_cancel_request_does_not_erase_a_successful_native_utility_acknowledgement(fixture,monkeypatch):
    jobs,source,endpoint,tools=fixture
    def acknowledged(*_args,**kwargs):
        kwargs['cancel_signal'].set()
        return {'return_code':0,'process_observation':{'return_code':0,'cleanup_confirmed':True,'cancel_requested':True}}
    monkeypatch.setattr(tools,'execute',acknowledged)
    selected=review(fixture)
    jobs.start(request(selected),1,endpoint,source,'configuration',ContinuityTransport({}))
    result=wait(fixture,selected)
    assert result['state']=='completed' and result['native_utility_acknowledged']


def test_acknowledgement_is_saved_before_a_later_catalog_read_and_survives_a_lost_observer(fixture,monkeypatch):
    jobs,source,endpoint,_tools=fixture;entered=threading.Event();release=threading.Event()
    def delayed(*_args):entered.set();assert release.wait(5);return None
    monkeypatch.setattr(slots,'observe',delayed)
    selected=review(fixture)
    try:
        jobs.start(request(selected),1,endpoint,source,'configuration',ContinuityTransport({}))
        assert entered.wait(2)
        saved=jobs.load(selected['job_id'],1,endpoint)
        assert saved['state']=='completed' and saved['native_utility_acknowledged'] and saved['slot_observation_state']=='pending'
        public=jobs.observed({**saved,'worker_identity':[999999999,0]})
        assert public['state']=='completed' and public['native_utility_acknowledged'] and public['slot_observation_state']=='unavailable'
    finally:release.set()
    assert wait(fixture,selected)['slot_observation_state']=='observed'


def test_slot_catalog_preserves_native_fields_and_bounded_page_parameters(monkeypatch):
    from types import SimpleNamespace
    import psycopg
    calls=[];connections=[]
    native={'slot_name':'owned_slot','slot_type':'physical','safe_wal_size':'9223372036854775807','active':False,'database':None}
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*_args):pass
        def execute(self,query,parameters=None):
            calls.append((query,parameters))
            row=('1',json.dumps([native])) if query.startswith('WITH') else (json.dumps(native),)
            return SimpleNamespace(fetchone=lambda:row)
    def connect(**parameters):connections.append(parameters);return Connection()
    monkeypatch.setattr(psycopg,'connect',connect)
    transport=ContinuityTransport({'connect_timeout':'99'})
    try:
        result=slots.catalog({'system_identifier':'1'},transport,{'offset':25,'limit':25})
        assert result['slots']==[native] and result['total']==1 and result['offset']==25
        assert calls[-1][1]==(25,25) and 'MATERIALIZED' in calls[-1][0]
        assert slots.observe(transport,'owned_slot')==native and calls[-1][1]==('owned_slot',)
        assert all(item['connect_timeout']==5 for item in connections)
    finally:transport.close()

"""Native clone admission, durable claims and correlated cancellation identity."""
import threading
import uuid
import pytest

from pgadmin.cdeadmin.providers.mysql_family.mysql_clone import CloneError, correlated, options
from pgadmin.cdeadmin.workspace.mysql_clone_jobs import MySQLCloneJobs


@pytest.mark.parametrize('value',[{}, {'destination':'a','confirmation':'b'},
    {'destination':'x\x00y','confirmation':'x\x00y'}, {'destination':'x'*511,'confirmation':'x'*511},
    {'destination':'/clone','confirmation':'/clone','timeout_seconds':False},
    {'destination':'/clone','confirmation':'/clone','sql':'arbitrary'}])
def test_clone_options_refuse_ambiguous_native_requests(value):
    with pytest.raises(CloneError):options(value)


@pytest.fixture
def manager(tmp_path,monkeypatch):
    import pgadmin.cdeadmin.workspace.mysql_clone_jobs as module
    monkeypatch.setattr(module,'destination',lambda _connection,path,_source:len(path.encode('utf8')))
    jobs=MySQLCloneJobs(tmp_path/'jobs.json',tmp_path/'receipts')
    source={'server_uuid':str(uuid.uuid4()),'version':'9.7.0','operating_system':'Linux','authenticated_principal':'root@localhost'}
    yield jobs,source,str(uuid.uuid4())
    jobs.close()


def review(manager):
    jobs,source,endpoint=manager
    path='/server/Clone "ü" \\ exact'
    return jobs.review({'options':{'destination':path,'confirmation':path}},1,endpoint,source,'configuration',None)


class Transport:
    worker=None
    def __init__(self):self.closed=False
    def close(self):self.closed=True


def test_clone_receipts_are_owner_bound_persistent_and_do_not_contain_transports(manager):
    jobs,source,endpoint=manager;item=review(manager)
    restarted=MySQLCloneJobs(jobs.path,jobs.root)
    assert restarted.get(item['job_id'],1,endpoint)['source']==source
    assert restarted.list(1,endpoint)['total']==1
    for owner,scope in ((2,endpoint),(True,endpoint),(1,str(uuid.uuid4()))):
        with pytest.raises(CloneError):restarted.get(item['job_id'],owner,scope)
    assert item['execution_host']['kind']=='database-server' and item['files_verified'] is False


def test_changed_clone_source_and_review_cannot_dispatch(manager):
    jobs,source,endpoint=manager;item=review(manager)
    request={key:item[key] for key in ('job_id','review_digest')};request['confirmed']=True
    transport=Transport()
    with pytest.raises(CloneError,match='target or registration'):
        jobs.start(request,1,endpoint,{**source,'server_uuid':str(uuid.uuid4())},'configuration',transport)
    assert transport.closed
    record=jobs.load(item['job_id'],1,endpoint)
    jobs.update(record,options={**record['options'],'destination':'/different'})
    with pytest.raises(CloneError,match='fingerprint'):
        jobs.start(request,1,endpoint,source,'configuration',Transport())


def test_duplicate_clone_start_is_offline_and_cross_instance_cancellation_reaches_worker(manager):
    jobs,source,endpoint=manager;item=review(manager)
    request={key:item[key] for key in ('job_id','review_digest')};request['confirmed']=True
    calls=[];started=threading.Event();stopped=threading.Event()
    def run(record,transport,signal):
        calls.append(record['job_id']);started.set()
        try:signal.wait(3);jobs.update(record,state='cancelled')
        finally:transport.close();jobs.workers.pop(record['job_id'],None);stopped.set()
    jobs.run=run
    jobs.start(request,1,endpoint,source,'configuration',Transport());assert started.wait(2)
    assert jobs.start(request,1,endpoint,source,'configuration',None)['job_id']==item['job_id']
    assert len(calls)==1
    restarted=MySQLCloneJobs(jobs.path,jobs.root);restarted.cancel(item['job_id'],1,endpoint)
    assert stopped.wait(2) and restarted.get(item['job_id'],1,endpoint)['state']=='cancelled'


def test_dead_clone_worker_is_unknown_and_cannot_replay(manager):
    jobs,source,endpoint=manager;item=review(manager);record=jobs.load(item['job_id'],1,endpoint)
    jobs.update(record,state='active',worker_identity=[999999999,0])
    assert jobs.get(item['job_id'],1,endpoint)['state']=='unknown'
    request={key:item[key] for key in ('job_id','review_digest')};request['confirmed']=True
    assert jobs.start(request,1,endpoint,source,'configuration',None)['state']=='unknown'


def test_native_status_cannot_be_attributed_by_destination_alone():
    record={'source':{'operating_system':'Linux'},'options':{'destination':'/server/clone'},
            'native_thread':{'connection_id':'9007199254740993','thread_id':'9007199254740995'},
            'native_operation_key':{'id':'1','pid':'9007199254740993','begin_time':'2026-10-16 12:00:00.001'}}
    observed={'available':True,'status':{'id':'1','pid':'9007199254740993','begin_time':'2026-10-16 12:00:00.001','source':'LOCAL INSTANCE','destination':'/server/clone/'}}
    assert correlated(observed,record)
    for changed in ({'id':'2'},{'pid':'9007199254740994'},{'begin_time':'2026-10-16 12:00:00.002'},{'source':'remote.example'},{'destination':'/server/another'}):
        assert not correlated({**observed,'status':{**observed['status'],**changed}},record)
    assert not correlated({'available':False},record)
    unbound={**record,'native_operation_key':None,'baseline_operation_key':{'id':'1','pid':'previous','begin_time':'old'}}
    assert not correlated(observed,unbound)
    assert correlated(observed,unbound,allow_new=True)


def test_runtime_policy_refuses_an_unbounded_native_client_when_required(manager):
    jobs,source,endpoint=manager
    with pytest.raises(CloneError,match='Application policy'):
        jobs.review({'options':{'destination':'/clone','confirmation':'/clone','timeout_seconds':None}},1,endpoint,source,'configuration',None,runtime_limit=3600)

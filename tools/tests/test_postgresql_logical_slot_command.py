"""Native logical slot options, protocol quoting and acknowledgement ownership."""
from contextlib import contextmanager
import time
import uuid

import pytest

from pgadmin.cdeadmin.providers.postgresql.continuity import ContinuityError
from pgadmin.cdeadmin.providers.postgresql.continuity_transport import ContinuityTransport
from pgadmin.cdeadmin.workspace import postgresql_logical_slot_command as command
from pgadmin.cdeadmin.workspace.postgresql_continuity_jobs import PostgreSQLContinuityJobs


@pytest.mark.parametrize('value',[{},[],{'slot':'UPPER'},{'slot':'owned','plugin':''},
    {'slot':'owned','plugin':'\x00'},{'slot':'owned','plugin':'\ud800'},{'slot':'owned','plugin':'ü'*32},
    {'slot':'owned','two_phase':1},{'slot':'owned','failover':'true'},
    {'slot':'owned','if_not_exists':None},{'slot':'owned','timeout_seconds':True},
    {'slot':'owned','unsafe_arguments':['--start']}])
def test_inadmissible_options_do_not_become_native_commands(value):
    with pytest.raises(ContinuityError):command.options(value)


@pytest.mark.parametrize('version,expected',[('18.3','Native "" ü'),('18.4','Native "" ü'),('18.6','Native " ü')])
def test_native_plugin_identifier_quoting_is_bound_to_tool_revision(version,expected):
    selected=command.options({'slot':'owned','plugin':'Native " ü','two_phase':True,'failover':True,'if_not_exists':True})
    assert command.arguments(selected,{'version':'(PostgreSQL) '+version})==[
        '--no-password','--verbose','--create-slot','--slot=owned','--plugin='+expected,
        '--enable-two-phase','--enable-failover','--if-not-exists']
    with pytest.raises(ContinuityError):command.arguments(selected,{'version':'(PostgreSQL) 18.5'})


@pytest.fixture
def fixture(tmp_path,monkeypatch):
    source={'system_identifier':'9007199254740993','server_version':180003,'timeline':1,'lsn':'0/A',
        'admission_interface':'logical-replication','database':'native','database_target_id':'postgresql-replication-database:'+b'native'.hex(),
        'authenticated_principal':'native owner','sql_admission_performed':False,'slot_catalog_observed':False,
        'sql_identity':None,'slot_snapshot':None,'slot_identity':None}
    class Tools:
        calls=[]
        def __init__(self,_paths):pass
        def identify(self,*_args):return {'available':True,'version':'(PostgreSQL) 18.6','executable_sha256':'a'*64}
        def execute(self,name,_directory,args,**kwargs):
            self.calls.append((name,args));assert kwargs['parameters']['client_encoding']=='UTF8'
            return {'return_code':0,'process_observation':{'cleanup_confirmed':True,'return_code':0}}
    from pgadmin.cdeadmin.workspace import postgresql_continuity_jobs
    from pgadmin.cdeadmin.providers.postgresql import replication_admission
    monkeypatch.setattr(command,'PhysicalTools',Tools);monkeypatch.setattr(postgresql_continuity_jobs,'PhysicalTools',Tools)
    def capture(_parameters,*,logical):
        assert logical;return dict(source),ContinuityTransport({})
    monkeypatch.setattr(replication_admission,'capture',capture)
    jobs=PostgreSQLContinuityJobs(tmp_path/'jobs.json',tmp_path/'artifacts');endpoint=str(uuid.uuid4())
    try:yield jobs,source,endpoint,Tools
    finally:jobs.close()


def review(fixture):
    jobs,source,endpoint,_tools=fixture
    return jobs.review({'operation':command.OPERATION,'options':{'slot':'owned','two_phase':True,'failover':True}},1,endpoint,source,'configuration',{})


def request(record):return {'job_id':record['job_id'],'review_digest':record['review_digest'],'confirmed':True}


def wait(fixture,record):
    jobs,_source,endpoint,_tools=fixture;deadline=time.monotonic()+5
    while True:
        result=jobs.get(record['job_id'],1,endpoint)
        if result['state'] not in {'active','dispatching','cancel_requested'}:return result
        assert time.monotonic()<deadline;time.sleep(.01)


def test_native_acknowledgement_and_duplicate_start_do_not_invent_a_catalog(fixture):
    jobs,source,endpoint,tools=fixture;record=review(fixture)
    jobs.start(request(record),1,endpoint,source,'configuration',ContinuityTransport({}))
    result=wait(fixture,record)
    assert result['state']=='completed' and result['native_utility_acknowledged']
    assert result['slot_existed_before'] is None and result['slot_observation'] is None
    assert result['slot_observation_state']=='unavailable' and result['remote_finality_inferred'] is False
    assert len(tools.calls)==1 and tools.calls[0][0]=='pg_recvlogical'
    lease=ContinuityTransport({});jobs.start(request(record),1,endpoint,source,'configuration',lease)
    assert lease.closed and len(tools.calls)==1


def test_pinned_replication_parser_limitation_is_not_emulated_or_misrepresented(fixture):
    jobs,source,endpoint,tools=fixture
    with pytest.raises(ContinuityError,match='replication parser cannot represent'):
        jobs.review({'operation':command.OPERATION,'options':{'slot':'owned','plugin':'Native " ü'}},1,endpoint,source,'configuration',{})
    assert not tools.calls


def test_worker_checks_native_database_before_dispatch_even_after_start_admission(fixture):
    jobs,source,endpoint,tools=fixture;record=review(fixture)
    admitted=dict(source);source['database']='changed'
    jobs.start(request(record),1,endpoint,admitted,'configuration',ContinuityTransport({}))
    assert wait(fixture,record)['state']=='failed' and not tools.calls


def test_returned_acknowledgement_survives_later_tunnel_release_failure(fixture):
    jobs,source,endpoint,_tools=fixture;record=review(fixture)
    class Transport:
        @contextmanager
        def parameters(self):
            yield {}
            raise ContinuityError('Owned tunnel release failure')
        def close(self):pass
    jobs.start(request(record),1,endpoint,source,'configuration',Transport())
    deadline=time.monotonic()+5
    while True:
        result=jobs.get(record['job_id'],1,endpoint)
        if result['state']=='failed':break
        assert time.monotonic()<deadline;time.sleep(.01)
    assert result['native_utility_acknowledged'] and result['tool_observation']['return_code']==0


def test_unknown_native_command_outcome_never_grants_retry(fixture,monkeypatch):
    jobs,source,endpoint,tools=fixture;record=review(fixture)
    def failed(*_args,**_kwargs):
        tools.calls.append('dispatched');return {'return_code':1,'process_observation':{'cleanup_confirmed':True,'return_code':1}}
    monkeypatch.setattr(tools,'execute',failed)
    jobs.start(request(record),1,endpoint,source,'configuration',ContinuityTransport({}))
    result=wait(fixture,record)
    assert result['state']=='unknown' and result['native_utility_acknowledged'] is False
    jobs.start(request(record),1,endpoint,source,'configuration',ContinuityTransport({}))
    assert len(tools.calls)==1

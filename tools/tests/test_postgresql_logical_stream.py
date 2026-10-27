"""Native receiver admission and exact retained bytes do not imply replication finality."""
import base64
import threading
import uuid
from contextlib import contextmanager
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.postgresql.continuity import ContinuityError
from pgadmin.cdeadmin.workspace import postgresql_logical_stream as stream
from pgadmin.cdeadmin.workspace.postgresql_continuity_jobs import PostgreSQLContinuityJobs


@pytest.mark.parametrize('change',[
    {'slot':'UPPER'},{'slot':'../escape'},{'start_lsn':'0/1;SELECT 1'},{'end_lsn':'100000000/0'},
    {'status_interval_seconds':True},{'fsync_interval_seconds':-1},{'fsync_interval_seconds':2147484},
    {'timeout_seconds':0},{'timeout_seconds':True},{'plugin_options':[{'name':'x=y','value':'z'}]},
    {'plugin_options':[{'name':'x','value':'\ud800'}]},{'unsafe_arguments':['--create-slot']},
])
def test_native_receiver_refuses_ambiguous_options_before_dispatch(change):
    with pytest.raises(ContinuityError):stream.options({'slot':'owned',**change})


def source():
    return {'sql_identity':{'database':'native','authenticated_principal':'owner','effective_principal':'owner'},
            'slot_snapshot':{'slot_name':'owned','slot_type':'logical','temporary':False,'active':False,'database':'native'}}


@pytest.mark.parametrize('change',[
    {'temporary':True},{'slot_type':'physical'},{'database':'other'},{'active':True},{'slot_name':'other'},
])
def test_only_existing_idle_permanent_logical_slots_are_admitted(change):
    native=source();native['slot_snapshot'].update(change)
    with pytest.raises(ContinuityError):stream.require_source(native,{'slot':'owned'})


def test_receiver_does_not_silently_change_effective_principal():
    native=source();native['sql_identity']['effective_principal']='selected_role'
    with pytest.raises(ContinuityError,match='authenticates directly'):stream.require_source(native,{'slot':'owned'})


def replication_source():
    return {'admission_interface':'logical-replication','sql_admission_performed':False,'database':'native',
        'database_target_id':'postgresql-replication-database:'+b'native'.hex(),
        'authenticated_principal':'native user','sql_identity':None,'slot_catalog_observed':False,
        'slot_snapshot':None,'slot_identity':None}


@pytest.mark.parametrize('change',[
    {'slot_catalog_observed':True},{'slot_snapshot':{}},{'sql_identity':{}},
    {'slot_identity':{}},{'sql_admission_performed':True},{'database_target_id':'other'},
])
def test_replication_only_stream_never_invents_sql_slot_facts(change):
    source={**replication_source(),**change}
    with pytest.raises(ContinuityError,match='unobserved SQL'):stream.require_source(source,{'slot':'owned'})


def test_known_slot_name_can_be_admitted_with_unobserved_catalog():
    stream.require_source(replication_source(),{'slot':'owned'})


@pytest.mark.parametrize('version,expected',[('(PostgreSQL) 18.3','adapter'),('(PostgreSQL) 18.4','adapter'),('(PostgreSQL) 18.6','utility')])
def test_native_client_quoting_revision_is_explicit(version,expected):
    assert stream.option_quoting({'version':version})==expected


def test_unqualified_native_quoting_revision_is_not_guessed():
    with pytest.raises(ContinuityError,match='requires qualification'):stream.option_quoting({'version':'(PostgreSQL) 18.5'})


@pytest.fixture
def captured(tmp_path):
    jobs=PostgreSQLContinuityJobs(tmp_path/'jobs.json',tmp_path/'output');endpoint=str(uuid.uuid4())
    record={'job_id':str(uuid.uuid4()),'owner':1,'endpoint_id':endpoint,'operation':stream.OPERATION,
            'state':'unknown','options':{},'source':{},'created_at':1,'cancel_requested':False,
            'tool_observation':{'process_observation':{'cleanup_confirmed':True,'return_code':-15}}}
    jobs.save_review(record);directory=jobs.directory(record);directory.mkdir(parents=True)
    data=b"\x00\x80\xff\r\n"+'native 😀'.encode();(directory/stream.FILENAME).write_bytes(data)
    try:yield jobs,record,data
    finally:jobs.close()


def test_sealing_interrupted_bytes_preserves_unknown_outcome_and_exact_ranges(captured):
    jobs,record,data=captured
    result=stream.reconcile(jobs,record)
    assert result['state']=='unknown' and result['logical_stream_artifact']['state']=='sealed'
    assert not result['logical_stream_artifact']['native_receiver_returned']
    assert not result['logical_stream_artifact']['transaction_completeness_inferred']
    assert 'file_identity' not in result['logical_stream_artifact']
    saved=jobs.load(record['job_id'],1,record['endpoint_id'])
    preview=stream.preview(jobs,saved,{'job_id':record['job_id'],'limit':3})
    assert base64.b64decode(preview['data_base64'])==data[:3] and preview['utf8_preview'] is None
    next_page=stream.preview(jobs,saved,{'offset':preview['next_offset'],'limit':65536})
    assert base64.b64decode(next_page['data_base64'])==data[3:] and next_page['next_offset'] is None
    with stream.payload(jobs,saved) as native:assert native.read()==data
    assert jobs.get(record['job_id'],1,record['endpoint_id'])['state']=='unknown'


def test_active_or_changed_native_files_are_never_offered_as_sealed_output(captured):
    jobs,record,_data=captured;jobs.update(record,state='active',worker_identity=jobs.worker_identity)
    jobs.workers[record['job_id']]=(threading.current_thread(),threading.Event())
    try:
        with pytest.raises(ContinuityError,match='active worker'):stream.reconcile(jobs,record)
    finally:jobs.workers.pop(record['job_id'])
    jobs.update(record,state='failed');stream.reconcile(jobs,record)
    saved=jobs.load(record['job_id'],1,record['endpoint_id'])
    with (jobs.directory(record)/stream.FILENAME).open('ab') as output:output.write(b'changed')
    with pytest.raises(ContinuityError,match='changed'):
        with stream.payload(jobs,saved):pass
    with pytest.raises(ContinuityError,match='Previously sealed'):stream.reconcile(jobs,saved)


@pytest.mark.parametrize('selected',[{'offset':1},{'offset':'01'},{'offset':'-1'},{'limit':True},{'limit':65537},{'offset':'99999999999999999999'}])
def test_byte_preview_bounds_do_not_coerce_native_positions(captured,selected):
    jobs,record,_data=captured;stream.reconcile(jobs,record)
    with pytest.raises(ContinuityError):stream.preview(jobs,jobs.load(record['job_id'],1,record['endpoint_id']),selected)


def test_dead_sealing_worker_preserves_native_utility_outcome_for_offline_recovery(captured):
    jobs,record,_data=captured
    jobs.update(record,state='captured',worker_io_closed=True,native_receiver_returned=True,
                logical_stream_artifact={'state':'sealing','writer_closed':True})
    value=jobs.get(record['job_id'],1,record['endpoint_id'])
    assert value['state']=='captured' and value['native_receiver_returned']
    assert value['logical_stream_artifact']['state']=='unavailable'
    recovered=stream.reconcile(jobs,jobs.load(record['job_id'],1,record['endpoint_id']))
    assert recovered['state']=='captured' and recovered['logical_stream_artifact']['state']=='sealed'


def test_logical_native_return_precedes_failed_tunnel_release_and_bytes_recover_offline(captured,monkeypatch):
    jobs,record,data=captured;directory=jobs.directory(record);path=directory/stream.FILENAME
    path.unlink()
    admitted={**source(),'slot_identity':{'slot_name':'owned'},'logical_stream_confirmed_lsn':None}
    fields={'client_identity':stream.client_identity(),'options':stream.options({'slot':'owned'}),'source':admitted,
        'tool_identities':{'pg_recvlogical':{'version':'(PostgreSQL) 18.6'}}}
    record.update(fields);jobs.update(record,**fields)
    monkeypatch.setattr(stream.private_sql,'attach',lambda *_args:Mock())
    @contextmanager
    def query(_connection):yield Mock()
    monkeypatch.setattr(stream.private_sql,'cursor',query)
    monkeypatch.setattr(stream.slots,'enrich',lambda *_args:admitted)
    class Tools:
        def execute(self,*_args,**_kwargs):
            path.write_bytes(data)
            return {'return_code':0,'process_observation':{'cleanup_confirmed':True,'return_code':0}}
    class Transport:
        @contextmanager
        def parameters(self):
            yield {}
            raise ContinuityError('Owned native tunnel release failed')
    with pytest.raises(ContinuityError,match='tunnel release failed'):
        stream.run(jobs,record,Tools(),directory,Transport(),lambda _event:None,threading.Event())
    saved=jobs.load(record['job_id'],1,record['endpoint_id'])
    assert saved['native_receiver_returned'] is True and saved['worker_io_closed'] is True
    assert saved['tool_observation']['return_code']==0
    recovered=stream.reconcile(jobs,saved)
    assert recovered['logical_stream_artifact']['native_receiver_returned'] is True
    with stream.payload(jobs,jobs.load(record['job_id'],1,record['endpoint_id'])) as incoming:assert incoming.read()==data

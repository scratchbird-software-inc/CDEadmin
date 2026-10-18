"""Native inspection artifacts, acknowledgements, cancellation and file ownership."""
from contextlib import contextmanager
import json
import os
import time
import uuid

import pytest
from test_sqlite_changeset_inspection import native,prepare
from pgadmin.cdeadmin.providers.sqlite.changeset_inspection import options,inspect
from pgadmin.cdeadmin.providers.sqlite.session_api import SessionAPIError
from pgadmin.cdeadmin.workspace.sqlite_capture_jobs import checked_archive_reads
from pgadmin.cdeadmin.workspace.sqlite_inspection_jobs import SQLiteInspectionJobs,InspectionTransport


@pytest.fixture
def setup(native,tmp_path):
    connection,api,key,path,payload=prepare(native)
    jobs=SQLiteInspectionJobs(tmp_path/'jobs.json',tmp_path/'jobs');endpoint=str(uuid.uuid4())
    def review(selected=None,cancel_on_open=False):
        selected=options(selected or {'mode':'page','preview_bytes':4});source={'input':{'reference':{'job_id':'original'},'file':{'path':path.name}}}
        receipt=jobs.review(1,endpoint,selected,{'identity':source,'state':{}},'native-owned',api.program);record=jobs.load(receipt['job_id'],1,endpoint)
        @contextmanager
        def input_file():
            if cancel_on_open:jobs.cancel(record['job_id'],1,endpoint)
            with path.open('rb') as stream:yield stream,{'path':path.name}
        transport=InspectionTransport(jobs,os.environ['CDEADMIN_SQLITE_SESSION_LIBRARY'],input_file)
        request={'job_id':record['job_id'],'review_digest':record['review_digest'],'confirmed':True}
        return record,request,transport
    try:yield jobs,endpoint,connection,api,key,path,payload,review
    finally:jobs.close()


def start(jobs,endpoint,record,request,transport):
    jobs.start(request,1,endpoint,{key:record[key] for key in ('source','configuration','program')},transport)
    deadline=time.monotonic()+10
    while True:
        value=jobs.get(record['job_id'],1,endpoint)
        with jobs._maps_lock:known=jobs.workers.get(record['job_id'])
        if value['state'] not in {'dispatching','active','publishing','cancel_requested'} and not known:return value
        assert time.monotonic()<deadline;time.sleep(.01)


def test_native_page_result_is_sealed_owner_scoped_and_never_an_apply_input(setup):
    jobs,endpoint,connection,_api,_key,_path,_payload,review=setup;record,request,transport=review()
    value=start(jobs,endpoint,record,request,transport);assert value['state']=='completed' and value['native_returned']
    result=jobs.result(record['job_id'],1,endpoint);assert result['inspection']['rows_returned']==3 and not result['apply_input']
    assert result['inspection']['column_name_scope'] and result['inspection']['rows'][0]['table']=='t'
    assert value['result']['artifact'].get('native_kind') is None and not value['result']['artifact']['apply_input']
    assert connection.in_transaction and connection.execute('SELECT count(*) FROM t').fetchone()==(2,)
    with pytest.raises(ValueError):jobs.result(record['job_id'],2,endpoint)
    assert jobs.start(request,1,endpoint,{},None)['state']=='completed'


def test_full_blob_and_text_extraction_agree_with_native_ranges_and_preserve_pending_sql(setup):
    jobs,endpoint,connection,api,_key,path,payload,review=setup
    with path.open('rb') as stream:page=inspect(api,stream.fileno(),{'mode':'page','preview_bytes':4})
    row=next(row for row in page['rows'] if row['operation']=='insert');assert row['new_values'][1]['preview_text']=='雪'
    assert row['new_values'][1]['data']['byte_length']==4
    for column,expected in ((2,payload),(1,'雪😀\x00'.encode('utf8'))):
        record,request,transport=review({'mode':'extract','record_number':row['record_number'],'column_index':column,'side':'new'})
        value=start(jobs,endpoint,record,request,transport);assert value['state']=='completed',value
        result=jobs.result(record['job_id'],1,endpoint);assert result['inspection']['native_written_bytes']==str(len(expected))
        with jobs.download(record['job_id'],1,endpoint,'value.bin') as (stream,metadata):assert stream.read()==expected and metadata['size']==len(expected)
    assert connection.in_transaction


def test_cancel_before_native_dispatch_is_confirmed_and_not_replayed(setup):
    jobs,endpoint,_connection,_api,_key,_path,_payload,review=setup;record,request,transport=review(cancel_on_open=True)
    value=start(jobs,endpoint,record,request,transport);assert value['state']=='cancelled' and not value.get('native_dispatch_admitted')
    assert not value.get('result') and jobs.start(request,1,endpoint,{},None)['state']=='cancelled'


def test_lost_publication_reconciles_only_sealed_output_without_repeating_native_work(setup,monkeypatch):
    jobs,endpoint,_connection,_api,_key,_path,_payload,review=setup;record,request,transport=review()
    import pgadmin.cdeadmin.workspace.sqlite_inspection_jobs as module
    monkeypatch.setattr(module,'durable_replace',lambda *_args:(_ for _ in ()).throw(OSError('lost publication')))
    value=start(jobs,endpoint,record,request,transport);assert value['state']=='unknown' and value['native_returned'] and value['sealed_candidate']
    result=jobs.reconcile(record['job_id'],1,endpoint);assert result['state']=='artifact_verified'
    assert jobs.result(record['job_id'],1,endpoint)['inspection']['rows_returned']==3
    assert jobs.start(request,1,endpoint,{},None)['state']=='artifact_verified'


def test_unsealed_json_is_diagnostic_even_when_its_current_json_parses(setup,monkeypatch):
    jobs,endpoint,_connection,_api,_key,_path,_payload,review=setup;record,request,transport=review();original=jobs.update
    def fail_seal(value,**fields):
        if fields.get('state')=='publishing':raise OSError('lost seal')
        return original(value,**fields)
    monkeypatch.setattr(jobs,'update',fail_seal);value=start(jobs,endpoint,record,request,transport)
    assert value['state']=='unknown' and value['native_returned'] and not value.get('sealed_candidate')
    result=jobs.reconcile(record['job_id'],1,endpoint,lambda _fd,_program:{'json_complete':True})
    assert result['state']=='unknown' and result['partial_output']['diagnostic_only'] and not result['partial_output']['complete_export_verified']
    with pytest.raises(ValueError):jobs.result(record['job_id'],1,endpoint)
    with jobs.diagnostic_download(record['job_id'],1,endpoint,'partial/inspection.json') as (stream,_row):assert json.load(stream)['inspection']['rows_returned']==3


def test_native_artifact_hash_read_has_cancellation_checkpoints_and_restores_scope(setup):
    jobs,endpoint,_connection,_api,_key,_path,_payload,review=setup;record,request,transport=review();assert start(jobs,endpoint,record,request,transport)['state']=='completed'
    calls=[]
    def stop_after_first_block():
        calls.append(True)
        if len(calls)==2:raise SessionAPIError('cancel hash')
    with pytest.raises(SessionAPIError,match='cancel hash'):
        with checked_archive_reads(stop_after_first_block):
            with jobs.download(record['job_id'],1,endpoint,'inspection.json'):raise AssertionError('Verification was not complete')
    with jobs.download(record['job_id'],1,endpoint,'inspection.json') as (stream,_row):assert json.load(stream)['format']=='sqlite-native-inspection@1'

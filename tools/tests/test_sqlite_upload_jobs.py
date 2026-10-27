"""Native external file intake, bounded chunks and durable retry postimages."""
import base64
import hashlib
import os
import time
import uuid

import pytest

from test_sqlite_changeset_apply import native  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.session_api import SessionAPIError
from pgadmin.cdeadmin.workspace.sqlite_upload_jobs import SQLiteUploadJobs,CHUNK_BYTES


def chunk(data,offset=0):return {'offset':str(offset),'data_base64':base64.b64encode(data).decode('ascii'),'sha256':hashlib.sha256(data).hexdigest()}


@pytest.fixture
def setup(native,tmp_path):
    connection,api,create,_route=native
    schema='CREATE TABLE t(id INTEGER PRIMARY KEY,body TEXT)'
    source=create(schema,'',"INSERT INTO t VALUES(9007199254740993,'😀')")
    jobs=SQLiteUploadJobs(tmp_path/'uploads.json',tmp_path/'uploads');endpoint=str(uuid.uuid4())
    def opened(data=None,**selected):
        if data is None:data=source.read_bytes()
        reviewed=jobs.create(1,endpoint,{'filename':'external\n雪.changeset','length':str(len(data)),**selected},'owned',api.program)
        return jobs.load(reviewed['job_id'],1,endpoint),data
    def seal(record):return jobs.seal(record['job_id'],1,endpoint,'owned',api.program,os.environ['CDEADMIN_SQLITE_SESSION_LIBRARY'])
    try:yield jobs,endpoint,opened,seal,connection
    finally:jobs.close()


def wait(jobs,record,endpoint):
    deadline=time.monotonic()+10
    while True:
        result=jobs.get(record['job_id'],1,endpoint)
        with jobs._maps_lock:known=jobs.workers.get(record['job_id'])
        if result['state'] not in {'active','dispatching','publishing','cancel_requested'} and not known:return result
        assert time.monotonic()<deadline;time.sleep(.01)


def test_real_native_upload_seals_after_checksum_and_native_parse_without_database_changes(setup):
    jobs,endpoint,opened,seal,connection=setup;record,data=opened()
    received=jobs.upload(record['job_id'],1,endpoint,chunk(data))
    assert received['uploaded_bytes']==str(len(data))
    assert jobs.upload(record['job_id'],1,endpoint,chunk(data))==received
    seal(record);result=wait(jobs,record,endpoint)
    assert result['state']=='completed' and result['native_returned']
    artifact=result['result']['artifact'];assert artifact['native_kind']=='changeset' and artifact['native_record_count']=='1'
    with jobs.download(record['job_id'],1,endpoint,'uploaded.native') as (stream,row):assert stream.read()==data and row['sha256']==hashlib.sha256(data).hexdigest()
    assert not connection.in_transaction and not connection.execute("SELECT name FROM sqlite_schema WHERE name='t'").fetchall()
    assert seal(record)['state']=='completed'


def test_exact_unacknowledged_chunk_is_recovered_and_overlapping_changed_retries_refuse(setup):
    jobs,endpoint,opened,_seal,_connection=setup;record,data=opened();path=jobs.directory(record)/'archive.incoming/uploaded.native'
    path.write_bytes(data)
    assert jobs.upload(record['job_id'],1,endpoint,chunk(data))['uploaded_bytes']==str(len(data))
    with pytest.raises(SessionAPIError,match='differs from acknowledged'):jobs.upload(record['job_id'],1,endpoint,chunk(bytes([data[0]^1])+data[1:]))
    with pytest.raises(SessionAPIError,match='declared bounds'):jobs.upload(record['job_id'],1,endpoint,chunk(b'extra',len(data)))
    with pytest.raises(ValueError):jobs.upload(record['job_id'],2,endpoint,chunk(data))


@pytest.mark.parametrize('data,selected',[(b'Tinvalid native stream',{}),(b'invalid magic',{}),(None,{'expected_sha256':'0'*64}),(None,{'kind':'patchset'})])
def test_checksum_native_structure_and_expected_kind_refuse_eligibility(setup,data,selected):
    jobs,endpoint,opened,seal,_connection=setup;record,data=opened(data,**selected)
    jobs.upload(record['job_id'],1,endpoint,chunk(data));seal(record);result=wait(jobs,record,endpoint)
    assert result['state']=='failed' and not (result.get('result') or {}).get('artifact')
    with pytest.raises(ValueError):
        with jobs.download(record['job_id'],1,endpoint,'uploaded.native'):pass


def test_missing_chunks_cancelled_upload_and_changed_policy_do_not_start_validation(setup):
    jobs,endpoint,opened,seal,_connection=setup;record,data=opened()
    with pytest.raises(SessionAPIError,match='all declared bytes'):seal(record)
    jobs.upload(record['job_id'],1,endpoint,chunk(data))
    with pytest.raises(SessionAPIError,match='policy changed'):jobs.seal(record['job_id'],1,endpoint,'changed',record['program'],'')
    assert jobs.cancel(record['job_id'],1,endpoint)['state']=='cancelled'
    assert seal(record)['state']=='cancelled' and not jobs.get(record['job_id'],1,endpoint).get('native_returned')


def test_upload_size_and_canonical_chunk_bounds_are_enforced(setup):
    jobs,endpoint,opened,_seal,_connection=setup;record,_data=opened(b'x'*(CHUNK_BYTES+1))
    with pytest.raises(SessionAPIError):jobs.upload(record['job_id'],1,endpoint,chunk(b'x'*(CHUNK_BYTES+1)))
    malformed=chunk(b'x');malformed['data_base64']+='='
    with pytest.raises(SessionAPIError):jobs.upload(record['job_id'],1,endpoint,malformed)


def test_native_empty_stream_and_lost_publication_reconciliation(setup,monkeypatch):
    from pgadmin.cdeadmin.workspace import sqlite_upload_jobs as module
    jobs,endpoint,opened,seal,_connection=setup;empty,_data=opened(b'')
    seal(empty);result=wait(jobs,empty,endpoint)
    assert result['state']=='completed' and result['result']['artifact']['native_record_count']=='0'
    record,data=opened();jobs.upload(record['job_id'],1,endpoint,chunk(data));replace=module.durable_replace
    def broken(_source,_target):raise OSError('owned native intake publication fault')
    monkeypatch.setattr(module,'durable_replace',broken);seal(record);result=wait(jobs,record,endpoint)
    assert result['state']=='unknown' and result['native_returned'] and result['sealed_candidate']
    monkeypatch.setattr(module,'durable_replace',replace)
    assert jobs.reconcile(record['job_id'],1,endpoint)['state']=='artifact_verified'
    with jobs.download(record['job_id'],1,endpoint,'uploaded.native') as (stream,_row):assert stream.read()==data

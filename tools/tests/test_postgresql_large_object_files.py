"""Whole-file staging, ownership, recovery and native dispatch invariants."""
import base64
import hashlib
import time
import uuid

import pytest

from pgadmin.cdeadmin.providers.postgresql.large_object_files import LargeObjectFileError as Error,options
from pgadmin.cdeadmin.workspace.postgresql_large_object_jobs import PostgreSQLLargeObjectJobs


@pytest.fixture
def jobs(tmp_path):
    manager=PostgreSQLLargeObjectJobs(tmp_path/'jobs',tmp_path/'files')
    yield manager
    manager.close()


def create(jobs,data=b'\x00\xffnative',**overrides):
    endpoint=str(uuid.uuid4())
    return jobs.create(1,endpoint,'postgresql-database:5',{'operation':'import','oid':'0','filename':'exact ü.bin','length':str(len(data)),**overrides},
        {'database_oid':'5'},'configuration')


def scope(record):return record['job_id'],1,record['endpoint_id'],record['database_target_id']


def chunk(data,offset='0'):
    return {'offset':offset,'data_base64':base64.b64encode(data).decode('ascii'),'sha256':hashlib.sha256(data).hexdigest()}


def sealed(jobs,data=b'\x00\xffnative'):
    record=create(jobs,data)
    if data:jobs.upload(*scope(record),chunk(data))
    jobs.seal(*scope(record),record['source'],'configuration')
    deadline=time.monotonic()+3
    while True:
        result=jobs.get(*scope(record))
        if result['state']!='reviewing':break
        assert time.monotonic()<deadline;time.sleep(.01)
    assert result['state']=='reviewed'
    return result


@pytest.mark.parametrize('change',[{'operation':'arbitrary'},{'oid':True},{'length':'-1'},{'length':'01'},
    {'filename':'../file'},{'filename':'/file'},{'filename':'x\x00y'},{'filename':'x\ud800y'}])
def test_file_options_refuse_ambiguous_native_identities(change):
    with pytest.raises(Error):options({'operation':'import','oid':'0','filename':'file.bin','length':'0',**change})


def test_staging_is_owner_endpoint_and_database_bound_and_has_offline_receipts(jobs):
    record=create(jobs);job_id,owner,endpoint,target=scope(record)
    restarted=PostgreSQLLargeObjectJobs(jobs.path,jobs.root)
    assert restarted.list(owner,endpoint,target)['total']==1
    for changed in ((job_id,2,endpoint,target),(job_id,True,endpoint,target),(job_id,owner,str(uuid.uuid4()),target),(job_id,owner,endpoint,'other')):
        with pytest.raises(Error):restarted.get(*changed)
    assert restarted.get(*scope(record))['state']=='uploading'


def test_chunk_retries_are_idempotent_and_different_prefixes_or_out_of_order_data_are_refused(jobs):
    data=b'\x00\xffnative';record=create(jobs,data);request=chunk(data)
    first=jobs.upload(*scope(record),request);assert jobs.upload(*scope(record),request)==first
    with pytest.raises(Error,match='differs'):jobs.upload(*scope(record),chunk(b'\x01\xffnative'))
    with pytest.raises(Error):jobs.upload(*scope(record),chunk(b'X',str(len(data)+1)))
    bad={**request,'sha256':'0'*64}
    with pytest.raises(Error,match='checksum'):jobs.upload(*scope(record),bad)
    assert jobs.load(*scope(record))['uploaded_bytes']==str(len(data))


def test_fsynced_but_unacknowledged_upload_recovers_only_matching_bytes(jobs):
    data=b'\x00\xffnative';record=create(jobs,data)
    with jobs.payload(jobs.load(*scope(record)),'r+b') as stream:stream.write(data);stream.flush()
    assert jobs.upload(*scope(record),chunk(data))['uploaded_bytes']==str(len(data))
    partial=create(jobs,data)
    with jobs.payload(jobs.load(*scope(partial)),'r+b') as stream:stream.write(data[:2]);stream.flush()
    with pytest.raises(Error,match='partial write'):jobs.upload(*scope(partial),chunk(data))


@pytest.mark.parametrize('data',[b'',b'\x00\xffnative'])
def test_whole_file_review_hashes_exact_bytes_and_private_file_identity(jobs,data):
    record=sealed(jobs,data)
    assert record['sha256']==hashlib.sha256(data).hexdigest() and record['length']==str(len(data))
    assert 'artifact_identity' not in record and 'configuration' not in record
    assert jobs.load(*scope(record))['artifact_identity'][2]==len(data)


def test_cancelled_upload_cannot_be_sealed_or_dispatched(jobs):
    record=create(jobs);cancelled=jobs.cancel(*scope(record));assert cancelled['state']=='cancelled'
    assert jobs.seal(*scope(record),record['source'],'configuration')['state']=='cancelled'
    with pytest.raises(Error):jobs.upload(*scope(record),chunk(b'\x00\xffnative'))


def test_dead_native_worker_remains_unknown_and_cannot_be_replayed(jobs):
    record=sealed(jobs);private=jobs.load(*scope(record));jobs.update(private,state='active',worker_identity=[999999999,0])
    request={'job_id':record['job_id'],'review_digest':record['review_digest'],'confirmed':True}
    result=jobs.start(request,1,record['endpoint_id'],record['database_target_id'],record['source'],'configuration',None)
    assert result['state']=='unknown' and result['automatic_retry'] is False


def test_application_artifact_removal_requires_confirmation_and_retains_the_receipt(jobs):
    record=sealed(jobs)
    with pytest.raises(Error,match='Confirm'):jobs.remove_artifact(*scope(record),'other-job')
    result=jobs.remove_artifact(*scope(record),record['job_id'])
    assert result['artifact_available'] is False and result['state']=='cancelled'
    assert jobs.list(1,record['endpoint_id'],record['database_target_id'])['total']==1
    assert not (jobs.directory(jobs.load(*scope(record)))/'payload').exists()

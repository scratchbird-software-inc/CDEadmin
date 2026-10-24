"""Native incremental metadata, exact lineage and immutable multi-input admission."""
from copy import deepcopy
import socket
from pathlib import Path
import uuid
from unittest.mock import Mock
import pytest

from test_mysql_physical import artifact as full_artifact
from test_mysql_physical_batch_retention import setup  # noqa: F401
from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_worker as worker
from pgadmin.cdeadmin.workspace import mysql_physical_service as physical
from pgadmin.cdeadmin.workspace import mysql_physical_batch_retention as batch


def make(path,kind='full-backuped',low=0,high=123,last=124):
    if not path.exists():full_artifact(path)
    (path/'xtrabackup_checkpoints').write_text(f'backup_type = {kind}\nfrom_lsn = {low}\nto_lsn = {high}\nlast_lsn = {last}\n')
    if kind=='incremental':
        p=path/'xtrabackup_info';p.write_text(p.read_text().replace('incremental = N','incremental = Y'))
    return worker.artifact(path)


def test_raw_incremental_and_redo_only_artifacts_never_claim_final_preparation(tmp_path):
    inc=make(tmp_path/'inc','incremental',123,224,225)
    redo=make(tmp_path/'redo','log-applied',0,224,225)
    assert inc['format']=='xtrabackup-9.7-incremental' and not inc['prepared']
    assert redo['redo_only'] and not redo['prepared']
    for path in ('inc','redo'):
        with pytest.raises(worker.Refused,match='preparation state'):worker.artifact(tmp_path/path,prepared=True)


@pytest.mark.parametrize('low,high,last',[(10,9,11),(0,11,10),(-1,11,12),(0,11,18446744073709551616)])
def test_native_checkpoint_ranges_cannot_wrap_or_lose_order(tmp_path,low,high,last):
    with pytest.raises(worker.Refused):make(tmp_path/'bad','incremental',low,high,last)


@pytest.fixture
def chain(tmp_path,monkeypatch):
    root=tmp_path/'private';root.mkdir(mode=0o700)
    binding={'server_uuid':str(uuid.uuid4()),'hostname':socket.gethostname(),'datadir':str(tmp_path/'live')}
    request={'schema':'cdeadmin.mysql-physical.v1','binding':binding,'workspace':str(root),'executable':'/bin/xtrabackup',
        'parallel':1,'memory_bytes':67108864,'timeout_seconds':60,'phase':'prepare_redo'}
    monkeypatch.setattr(worker,'executable',lambda path,kind:{'path':path,'kind':kind})
    def create(kind,lineage=None,parent=None):
        job=str(uuid.uuid4());directory=root/job;directory.mkdir(mode=0o700)
        value=make(directory/'artifact',kind,123 if kind=='incremental' else 0,224 if kind=='incremental' else 123,225 if kind=='incremental' else 124)
        phase={'full-backuped':'backup','incremental':'incremental','log-applied':'prepare_redo'}[kind]
        original={**request,'job_id':job,'phase':phase,'input_job_id':parent,'input_digest':job}
        receipt={'state':'native_returned','input_digest':job,'return_code':0,'process_termination_confirmed':True,'credential_cleanup_confirmed':True,'artifact':value}
        if lineage is not None:receipt['lineage']=lineage(job)
        worker.host.save(directory/'request.json',original);worker.host.save(directory/'result.json',receipt)
        return job
    base=create('full-backuped');prefix={'base_job_id':base,'incremental_job_ids':[]}
    redo=create('log-applied',lambda _id:prefix,base)
    inc=create('incremental',lambda job:{'base_job_id':base,'incremental_job_ids':[job]},base)
    return root,request,base,redo,inc,create


def test_prepare_admits_only_the_exact_next_native_delta_and_both_sealed_inputs(chain):
    root,request,base,redo,inc,_create=chain
    value=worker.inspection({**request,'input_job_id':redo,'incremental_job_id':inc})
    assert value['input']['lineage']=={'base_job_id':base,'incremental_job_ids':[]}
    assert value['incremental_input']['lineage']['incremental_job_ids']==[inc]
    (root/inc/'artifact'/'ibdata1').write_bytes(b'changed after publication')
    with pytest.raises(worker.Refused,match='bytes changed'):worker.inspection({**request,'input_job_id':redo,'incremental_job_id':inc})


@pytest.mark.parametrize('fault',['foreign-base','gap','repeated','missing-delta','raw-base','copy-redo','prepare-delta','foreign-source'])
def test_invalid_incremental_lineage_and_native_operation_are_refused(chain,fault):
    root,request,base,redo,inc,_create=chain
    request={**request,'input_job_id':redo,'incremental_job_id':inc}
    path=root/inc/'result.json';value=worker.read_json(path)
    if fault=='foreign-base':value['lineage']['base_job_id']=str(uuid.uuid4())
    if fault=='gap':
        value['artifact']=make(root/inc/'artifact','incremental',122,224,225)
    if fault=='repeated':value['lineage']['incremental_job_ids']=[inc,inc]
    worker.host.save(path,value)
    if fault=='missing-delta':request['incremental_job_id']=None
    if fault=='raw-base':request['input_job_id']=base
    if fault=='copy-redo':request.update(phase='copy_back',incremental_job_id=None)
    if fault=='prepare-delta':request.update(phase='prepare',input_job_id=inc,incremental_job_id=None)
    if fault=='foreign-source':
        original=worker.read_json(root/inc/'request.json');original['binding']['server_uuid']=str(uuid.uuid4());worker.host.save(root/inc/'request.json',original)
    with pytest.raises(worker.Refused):worker.inspection(request)


def test_retention_preserves_both_inputs_and_their_ancestors_for_a_retained_apply(setup):
    s=setup;base=s.create();delta=s.create('incremental',base['job_id']);redo=s.create('prepare_redo',base['job_id'])
    merged=s.create('prepare_redo',redo['job_id'],retention_pinned=True)
    record=s.jobs.load(merged['job_id'],1,s.endpoint.id)
    s.jobs.update(record,options={**record['options'],'incremental_job_id':delta['job_id']})
    s.create()
    assert not batch.plan(s.records(),base,{'retention_days':0,'keep_latest':1},200)['job_ids']
    record=s.jobs.load(merged['job_id'],1,s.endpoint.id);s.jobs.update(record,retention_pinned=False)
    order=batch.plan(s.records(),base,{'retention_days':0,'keep_latest':1},200)['job_ids']
    assert order.index(merged['job_id'])<order.index(delta['job_id'])<order.index(base['job_id'])
    assert order.index(merged['job_id'])<order.index(redo['job_id'])<order.index(base['job_id'])


@pytest.mark.parametrize('kind',['log-applied','full-prepared'])
def test_native_merged_target_keeps_the_last_incremental_info_without_relabelling_its_stage(tmp_path,kind):
    path=tmp_path/'merged';make(path,kind)
    info=path/'xtrabackup_info';info.write_text(info.read_text().replace('incremental = N','incremental = Y'))
    value=worker.artifact(path)
    assert value['format']=='xtrabackup-9.7-full' and value['native_incremental_info']
    assert value['prepared'] is (kind=='full-prepared')
    assert 'incremental = Y' in info.read_text()


def test_host_retention_finds_a_delta_used_only_as_the_second_input(chain):
    from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_retention_worker as retention
    root,request,_base,redo,inc,_create=chain
    child=str(uuid.uuid4());directory=root/child;directory.mkdir(mode=0o700)
    worker.host.save(directory/'request.json',{**request,'job_id':child,'input_job_id':redo,'incremental_job_id':inc})
    assert retention.dependencies(root,inc)==[child]
    assert child in retention.dependencies(root,redo)
    worker.host.save(directory/'retention-intent.json',{'state':'removed'})
    assert retention.dependencies(root,inc)==[]

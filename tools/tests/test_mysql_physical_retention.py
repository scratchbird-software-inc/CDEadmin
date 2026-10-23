"""Real private filesystem claims, dependency refusal and interrupted removal."""
import json
from pathlib import Path
import socket
import uuid
from types import SimpleNamespace

import pytest
from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_worker as physical
from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_retention_worker as native


def fixture(tmp_path,*,parent=None):
    root=tmp_path/'private';root.mkdir(exist_ok=True,mode=0o700)
    selected=str(uuid.uuid4());directory=root/selected;directory.mkdir(mode=0o700)
    source=tmp_path/'source';source.mkdir(exist_ok=True)
    request={'schema':'cdeadmin.mysql-physical.v1','workspace':str(root),'job_id':selected,'input_digest':'original-review',
        'phase':'backup','input_job_id':parent,'database_credentials':None,
        'binding':{'server_uuid':str(uuid.uuid4()),'hostname':socket.gethostname(),'datadir':str(source)}}
    physical.host.save(directory/'request.json',request)
    physical.host.save(directory/'result.json',{'state':'native_returned','input_digest':request['input_digest'],
        'process_termination_confirmed':True,'credential_cleanup_confirmed':True,'supervisor_finished':True})
    artifact=directory/'artifact';artifact.mkdir();(artifact/'data.ibd').write_bytes(b'original native bytes\0\xff')
    (artifact/'nested').mkdir();(artifact/'nested'/'other').write_bytes(b'separate data')
    return directory,{**request,'action':'retention_inspect','retention_id':str(uuid.uuid4())}


def inspect(request):return physical.dispatch(request)


def remove(request,review):return physical.dispatch({**request,'action':'retention_remove','confirmed':True,'retention_review':review})


def test_review_removes_only_exact_private_files_and_preserves_original_outcome(tmp_path):
    directory,request=fixture(tmp_path);original=(directory/'result.json').read_bytes()
    unrelated=tmp_path/'source'/'not-a-backup';unrelated.write_bytes(b'keep')
    review=inspect(request);assert review['artifact']['files']==2
    result=remove(request,review)
    assert result['removal_confirmed'] and not (directory/'artifact').exists()
    assert (directory/'result.json').read_bytes()==original and unrelated.read_bytes()==b'keep'
    assert inspect({**request,'action':'retention_status'})['removal_confirmed']
    assert remove(request,review)['removal_confirmed']
    assert 'manifest' not in physical.read_json(directory/'retention-intent.json')


@pytest.mark.parametrize('field',['process_termination_confirmed','credential_cleanup_confirmed','supervisor_finished'])
def test_unknown_original_native_ownership_never_permits_removal(tmp_path,field):
    directory,request=fixture(tmp_path);record=physical.read_json(directory/'result.json');record[field]=False
    physical.host.save(directory/'result.json',record)
    with pytest.raises(native.Refused,match='termination'):inspect(request)
    assert (directory/'artifact'/'data.ibd').is_file() and not (directory/'retention-intent.json').exists()


def test_dependent_remote_receipts_protect_the_parent_until_child_retention(tmp_path):
    directory,request=fixture(tmp_path);child,child_request=fixture(tmp_path,parent=request['job_id'])
    with pytest.raises(native.Refused,match='dependent'):inspect(request)
    remove(child_request,inspect(child_request))
    assert remove(request,inspect(request))['removal_confirmed']


def test_changed_bytes_or_unreviewed_entries_are_retained(tmp_path):
    directory,request=fixture(tmp_path);review=inspect(request)
    path=directory/'artifact'/'data.ibd';before=path.stat();path.write_bytes(b'changed native bytes\0\xff!')
    __import__('os').utime(path,ns=(before.st_atime_ns,before.st_mtime_ns))
    with pytest.raises(native.Refused,match='bytes changed'):remove(request,review)
    assert path.exists() and not (directory/'retention-intent.json').exists()


def test_interrupted_removal_resumes_only_original_detached_inode(tmp_path,monkeypatch):
    directory,request=fixture(tmp_path);review=inspect(request);original=native.shutil.rmtree
    def interrupted(path):
        (path/'data.ibd').unlink();raise OSError('owned interrupted cleanup')
    interrupted.avoids_symlink_attacks=True
    with monkeypatch.context() as patch:
        patch.setattr(native.shutil,'rmtree',interrupted)
        with pytest.raises(OSError):remove(request,review)
    detached=directory/('.removing-'+request['retention_id']+'-artifact')
    assert not (directory/'artifact').exists() and detached.is_dir()
    assert not inspect({**request,'action':'retention_status'})['removal_confirmed']
    assert remove(request,review)['removal_confirmed'] and not detached.exists()
    assert native.shutil.rmtree is original


def test_unreviewed_file_after_interruption_blocks_resume(tmp_path,monkeypatch):
    directory,request=fixture(tmp_path);review=inspect(request)
    def interrupted(_path):raise OSError('owned interruption')
    interrupted.avoids_symlink_attacks=True
    with monkeypatch.context() as patch:
        patch.setattr(native.shutil,'rmtree',interrupted)
        with pytest.raises(OSError):remove(request,review)
    detached=directory/('.removing-'+request['retention_id']+'-artifact');(detached/'new-file').write_text('retain me')
    with pytest.raises(native.Refused,match='Unreviewed'):remove(request,review)
    assert (detached/'new-file').read_text()=='retain me'


def test_symlinks_and_bind_mounts_are_refused(tmp_path,monkeypatch):
    directory,request=fixture(tmp_path);(directory/'artifact'/'outside').symlink_to(tmp_path/'source',target_is_directory=True)
    with pytest.raises(native.Refused,match='regular'):inspect(request)
    (directory/'artifact'/'outside').unlink()
    original=Path.read_text
    def mounts(path,*args,**kwargs):
        if str(path)=='/proc/self/mountinfo':return '1 2 0:1 / '+str(directory/'artifact')+' rw - none none rw\n'
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',mounts)
    with pytest.raises(native.Refused,match='bind mount'):inspect(request)


def test_abandon_invalidates_even_a_late_original_dispatch(tmp_path):
    directory,request=fixture(tmp_path);review=inspect(request)
    value=inspect({**request,'action':'retention_abandon'})
    assert value['late_dispatch_refused'] and (directory/'artifact').is_dir()
    with pytest.raises(native.Refused,match='expired'):remove(request,review)
    updated={**request,'retention_id':str(uuid.uuid4())}
    assert remove(updated,inspect(updated))['removal_confirmed']


def test_recovery_private_binlogs_and_data_are_in_the_review(tmp_path):
    directory,request=fixture(tmp_path);(directory/'artifact').rename(directory/'runtime-data')
    (directory/'recovery-bin.000001').write_bytes(b'native recovery binlog')
    (directory/'recovery-bin.index').write_text(str(directory/'recovery-bin.000001'))
    (directory/'native-error.log').write_text('preserved native output')
    review=inspect(request)
    assert set(review['artifact']['paths'])=={'runtime-data','recovery-bin.000001','recovery-bin.index'}
    assert remove(request,review)['removal_confirmed']
    assert (directory/'native-error.log').read_text()=='preserved native output'


def test_confirmed_guardian_and_runtime_end_permit_cleanup_without_inventing_native_reply(tmp_path,monkeypatch):
    directory,request=fixture(tmp_path)
    original=physical.read_json(directory/'request.json');original['phase']='recover';physical.host.save(directory/'request.json',original)
    result=physical.read_json(directory/'result.json');result.update(state='unknown',supervisor_finished=False,native_exit_reply_unknown=True)
    physical.host.save(directory/'result.json',result);before=(directory/'result.json').read_bytes()
    monkeypatch.setattr(physical,'recovery_module',lambda:SimpleNamespace(observe=lambda _directory,value,_action:{**value,
        'supervisor_process_live':False,'runtime_process_live':False,'supervisor_control_unavailable':True}))
    assert remove(request,inspect(request))['removal_confirmed']
    assert (directory/'result.json').read_bytes()==before


def test_application_dependency_graph_preserves_reviewed_children_and_pins(tmp_path):
    from pgadmin.cdeadmin.workspace.mysql_physical_service import PhysicalJobs
    from pgadmin.cdeadmin.workspace.mysql_physical_retention import dependencies
    from pgadmin.cdeadmin.providers.mysql_family.mysql_physical_transport import HostError
    jobs=PhysicalJobs(tmp_path/'jobs',tmp_path/'artifacts');endpoint=str(uuid.uuid4())
    def review(phase,parent=None):
        return jobs.review(1,endpoint,{'phase':phase,'input_job_id':parent},{'identity':{'server_uuid':str(uuid.uuid4())},
            'state':{'remote_review':{},'host_binding':{}}},'configuration',{'execution_host':{}})
    parent=review('backup');child=review('prepare',parent['job_id']);parent=jobs.load(parent['job_id'],1,endpoint)
    with pytest.raises(HostError,match='dependent'):
        dependencies(jobs,parent,1,endpoint)
    child=jobs.load(child['job_id'],1,endpoint);jobs.update(child,state='cancelled',native_may_have_dispatched=False)
    assert not dependencies(jobs,parent,1,endpoint)['physical_dependencies']
    jobs.update(parent,retention_pinned=True)
    parent=jobs.load(parent['job_id'],1,endpoint)
    with pytest.raises(HostError,match='Unpin'):dependencies(jobs,parent,1,endpoint)


def test_completed_removal_reconciles_interrupted_preview_compaction(tmp_path,monkeypatch):
    directory,request=fixture(tmp_path);review=inspect(request);unlink=Path.unlink
    def interrupted(path,*args,**kwargs):
        if path==directory/'retention-review.json':raise OSError('owned preview cleanup interruption')
        return unlink(path,*args,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(Path,'unlink',interrupted)
        with pytest.raises(OSError):remove(request,review)
    assert not (directory/'artifact').exists() and (directory/'retention-review.json').exists()
    assert inspect({**request,'action':'retention_status'})['removal_confirmed']
    assert not (directory/'retention-review.json').exists()


def test_public_original_process_status_uses_observed_termination_without_changing_unknown_outcome(tmp_path):
    from pgadmin.cdeadmin.workspace.mysql_physical_service import PhysicalJobs
    jobs=PhysicalJobs(tmp_path/'jobs',tmp_path/'artifacts');endpoint=str(uuid.uuid4())
    ticket=jobs.review(1,endpoint,{'phase':'backup'},{'identity':{'server_uuid':str(uuid.uuid4())},
        'state':{'remote_review':{},'host_binding':{}}},'configuration',{'execution_host':{}})
    record=jobs.load(ticket['job_id'],1,endpoint)
    jobs.update(record,state='unknown',remote_observation={'process_termination_confirmed':True,'return_code':None})
    observed=jobs.get(record['job_id'],1,endpoint)
    assert observed['native_process_termination_confirmed'] is True and observed['state']=='unknown'
    jobs.update(record,remote_observation={'return_code':0})
    assert jobs.get(record['job_id'],1,endpoint)['native_process_termination_confirmed'] is False

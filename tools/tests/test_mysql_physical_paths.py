"""Private native path plans, immutable input transformation and OS admission."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_paths as paths
from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_worker as worker
from test_mysql_physical import artifact


def entries():
    return [{'file_name':'/outside/general.ibd','tablespace_name':'general','tablespace_type':'TABLESPACE'},
        {'file_name':'/outside/schema/table.ibd','tablespace_name':'schema/table','tablespace_type':'TABLESPACE'}]


def test_native_copy_back_mapping_changes_only_its_private_verified_input(tmp_path):
    original=tmp_path/'prepared';artifact(original,prepared=True)
    worker.host.save(original/'xtrabackup_tablespaces',{'version':3,'external_tablespaces':entries()})
    expected=worker.public(worker.artifact(original));before=worker.manifest(original)
    job=tmp_path/'job';job.mkdir();target=job/'artifact'
    staged,plan=paths.stage_copy_back(job,original,target,expected)
    assert worker.manifest(original)==before
    assert len(plan)==1 and plan[0]['source_root']=='/outside'
    mapped=paths.tablespaces(staged)['external_tablespaces']
    assert mapped[0]['file_name']==str(target/'external-data/0/general.ibd')
    assert mapped[1]['file_name']==str(target/'external-data/0/schema/table.ibd')
    assert [row['tablespace_name'] for row in mapped]==['general','schema/table']
    assert (staged/'ibdata1').read_bytes()==(original/'ibdata1').read_bytes()


def test_native_directory_separator_in_a_literal_child_path_preserves_its_exact_name():
    row={'file_name':'/outside/literal; child 雪/schema/table.ibd','tablespace_name':'schema/table','tablespace_type':'TABLESPACE'}
    selected=paths.plan([row])
    assert selected[0]['source_root']=='/outside'
    assert selected[0]['files'][0]['relative_file']=='literal; child 雪/schema/table.ibd'


@pytest.mark.parametrize('fault',['missing-kind','relative-source','parent-source','parent-name','duplicate'])
def test_ambiguous_native_external_metadata_is_not_used_for_copy_back(tmp_path,fault):
    rows=entries()
    if fault=='missing-kind':rows[0].pop('tablespace_type')
    elif fault=='relative-source':rows[0]['file_name']='relative.ibd'
    elif fault=='parent-source':rows[0]['file_name']='/outside/../different.ibd'
    elif fault=='parent-name':rows[0]['tablespace_name']='../different'
    else:rows.append(dict(rows[0]))
    worker.host.save(tmp_path/'xtrabackup_tablespaces',{'version':3,'external_tablespaces':rows})
    with pytest.raises(worker.Refused):paths.tablespaces(tmp_path)


def test_external_material_requires_explicit_admission(tmp_path):
    request={'phase':'copy_back','binding':{'datadir':'/original'},'workspace':str(tmp_path)}
    with pytest.raises(worker.Refused,match='explicitly'):paths.admission(request,entries())
    accepted=paths.admission({**request,'isolate_external_paths':True},entries())
    assert accepted['native_datadir_uses_private_alias'] and accepted['host_root_readonly']
    assert paths.admission(request,[]) is None


def test_external_undo_is_not_relabelled_as_supported_table_geometry(tmp_path):
    request={'phase':'prepare','binding':{'datadir':'/original'},'workspace':str(tmp_path),'isolate_external_paths':True}
    with pytest.raises(worker.Refused,match='system/undo geometry'):
        paths.admission(request,[{'file_name':'/outside/undo.ibu','tablespace_name':'undo','tablespace_type':'UNDO_LOG'}])


def test_namespace_plan_never_hides_its_private_workspace_or_required_runtime(tmp_path):
    workspace=tmp_path/'private';workspace.mkdir();data=workspace/'data';data.mkdir()
    source=tmp_path/'source';source.mkdir()
    assert paths.validate_roots(workspace,[{'source_root':str(source),'private_root':str(data)}])
    for source_root in (tmp_path,workspace,Path('/proc'),Path('/')):
        with pytest.raises(worker.Refused):paths.validate_roots(workspace,[{'source_root':str(source_root),'private_root':str(data)}])


def test_missing_native_namespace_privilege_does_not_start_recovery(monkeypatch):
    observed=[]
    def run(command,**_kwargs):observed.append(command);return SimpleNamespace(returncode=1,stdout=b'',stderr=b'Operation not permitted')
    monkeypatch.setattr(paths.subprocess,'run',run)
    with pytest.raises(worker.Refused,match='privileges'):paths.capability()
    assert len(observed)==1 and all('mysqld' not in part for part in observed[0])


def test_missing_alias_review_selects_private_projection_without_creating_original_paths(tmp_path,monkeypatch):
    workspace=tmp_path/'private';workspace.mkdir();source=tmp_path/'lost-data';external=tmp_path/'lost-external'
    probes=[]
    monkeypatch.setattr(paths,'capability',lambda **options:probes.append(options) or {'backend':'native-probe'})
    request={'phase':'recover','workspace':str(workspace),'binding':{'datadir':str(source)},'isolate_external_paths':True}
    entry={'file_name':str(external/'schema/table.ibd'),'tablespace_name':'schema/table','tablespace_type':'TABLESPACE'}
    value=paths.admission(request,[entry])
    assert set(value['missing_alias_directories'])=={str(source),str(external)}
    assert probes==[{'projection':True,'root_projection':False}]
    assert not source.exists() and not external.exists()


def test_missing_top_level_alias_review_checks_private_root_switch_capability(tmp_path,monkeypatch):
    import uuid
    source='/native-missing-'+str(uuid.uuid4());external='/external-missing-'+str(uuid.uuid4());probes=[]
    monkeypatch.setattr(paths,'capability',lambda **options:probes.append(options) or {'backend':'native-probe'})
    request={'phase':'recover','workspace':str(tmp_path),'binding':{'datadir':source},'isolate_external_paths':True}
    value=paths.admission(request,[{'file_name':external+'/schema/table.ibd','tablespace_name':'schema/table','tablespace_type':'TABLESPACE'}])
    assert probes==[{'projection':True,'root_projection':True}]
    assert set(value['missing_alias_directories'])=={source,external}
    assert not Path(source).exists() and not Path(external).exists()


def test_cancelled_projection_creates_no_placeholders_or_mounts(tmp_path):
    from unittest.mock import Mock
    job=tmp_path/'job';job.mkdir();cancel=job/'cancel';cancel.write_text('requested')
    native=Mock()
    with pytest.raises(InterruptedError):paths.project_parent(native,tmp_path,tmp_path,0,cancel,directory=job)
    native.mount.assert_not_called();native.syscall.assert_not_called()
    assert not (job/'namespace-projections').exists()


def test_independent_observer_requires_private_namespace_exact_directory_and_readonly_host(tmp_path,monkeypatch):
    proc=tmp_path/'proc-root'/'123';ns=proc/'ns';ns.mkdir(parents=True);(ns/'mnt').symlink_to('mnt:[private]')
    root=proc/'root';root.mkdir();private=tmp_path/'private';private.mkdir();(root/'alias').symlink_to(private,target_is_directory=True)
    (proc/'mountinfo').write_text('1 0 0:1 / / ro - ext4 native ro\n2 1 0:1 / /private rw - ext4 native rw\n')
    real_path=Path
    monkeypatch.setattr(paths,'Path',lambda value:proc.parent if str(value)=='/proc' else real_path(value))
    expected={'private_namespace':'mnt:[private]','workspace':'/private','roots':[{'source_root':'/alias','private_root':str(private)}]}
    assert paths.observe(123,expected)['native_filesystem_isolation_observed']
    (proc/'mountinfo').write_text('1 0 0:1 / / rw - ext4 native rw\n2 1 0:1 / /private rw - ext4 native rw\n')
    with pytest.raises(worker.Refused,match='permissions changed'):paths.observe(123,expected)


def test_uncertain_filesystem_view_blocks_connections_but_preserves_original_process_stop(tmp_path,monkeypatch):
    from pgadmin.cdeadmin.providers.mysql_family import mysql_recovery_worker as recovery
    native={'pid':123};stopped=[]
    monkeypatch.setattr(recovery,'present',lambda value:True)
    monkeypatch.setattr(recovery,'stop',lambda value:stopped.append(value) or True)
    def refused(*_args):raise worker.Refused('changed native filesystem view')
    monkeypatch.setattr(paths,'observe',refused)
    value=recovery.observe(tmp_path,{'state':'unknown','input_digest':'reviewed','runtime_process':native,
        'filesystem_isolation':{'private_namespace':'original'},'sql_ready_observed':True,'credential_cleanup_confirmed':True},'cancel')
    assert stopped==[native] and value['runtime_process_live'] is True
    assert value['state']=='unknown'
    assert not value['recovery_running_verified']
    assert not value['filesystem_isolation_observation']['native_filesystem_isolation_observed']


@pytest.mark.parametrize('phase,checkpoint',[('prepare','full-backuped'),('prepare_redo','full-backuped'),('copy_back','full-prepared')])
@pytest.mark.parametrize('geometry',['innodb_data_file_path=/original/system.ibd:12M:autoextend','innodb_undo_directory=/external-undo'])
def test_external_system_or_undo_geometry_refuses_before_any_native_preparation_or_copy_back(tmp_path,monkeypatch,phase,checkpoint,geometry):
    import uuid
    from unittest.mock import Mock
    root=tmp_path/'private';root.mkdir();identity=str(uuid.uuid4());directory=root/identity/'artifact';directory.mkdir(parents=True)
    (directory/'backup-my.cnf').write_text('[mysqld]\n'+geometry+'\n')
    monkeypatch.setattr(worker,'host_scope',lambda *_args,**_kwargs:{'datadir':'/original'})
    monkeypatch.setattr(worker,'root_directory',lambda *_args:root)
    monkeypatch.setattr(worker,'executable',lambda *_args:{'path':'/native/xtrabackup'})
    monkeypatch.setattr(worker,'input_artifact',lambda *_args:{'artifact':{'checkpoint':{'backup_type':checkpoint}}})
    spawn=Mock();monkeypatch.setattr(worker.subprocess,'Popen',spawn)
    with pytest.raises(worker.Refused):
        worker.inspection({'phase':phase,'workspace':str(root),'executable':'/native/xtrabackup','input_job_id':identity,
            'parallel':2,'memory_bytes':268435456,'timeout_seconds':120,'binding':{'datadir':'/original'}})
    spawn.assert_not_called()

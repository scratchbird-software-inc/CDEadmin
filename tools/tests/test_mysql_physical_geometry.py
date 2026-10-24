"""Reviewed storage metadata and private native utility destinations."""
from copy import deepcopy
from pathlib import Path

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_geometry as geometry
from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_paths as paths
from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_worker as worker
from pgadmin.cdeadmin.providers.mysql_family import mysql_recovery_worker as recovery


def source():
    values={'innodb_data_home_dir':'','innodb_data_file_path':'/system/first:12M;/system/second:12M:autoextend',
        'innodb_undo_directory':'/undo','innodb_directories':'/tables;/undo;/empty'}
    files=[{'file_name':name,'tablespace_name':'innodb_system','file_type':'TABLESPACE'} for name in ('/system/first','/system/second')]
    files.extend({'file_name':name,'tablespace_name':table,'file_type':'UNDO LOG'} for name,table in
        [('/undo/undo_001','innodb_undo_001'),('/undo/undo_002','innodb_undo_002'),('/undo/extra.ibu','user_undo')])
    return {'binding':{'datadir':'/original/data'},'source_storage':{'variables':values,'files':files},'isolate_external_paths':True}


def captured(tmp_path):
    request=source();directory=tmp_path/'artifact';directory.mkdir()
    values=request['source_storage']['variables']
    (directory/'backup-my.cnf').write_text('[mysqld]\ninnodb_data_file_path='+values['innodb_data_file_path']+'\ninnodb_undo_directory=/undo\n')
    for name in ('first','second','undo_001','undo_002','extra.ibu'):(directory/name).write_bytes(('owned native page '+name).encode())
    return request,directory,geometry.capture(request,directory)


def test_capture_preserves_exact_original_geometry_empty_scan_roots_and_page_bytes(tmp_path):
    _request,directory,value=captured(tmp_path)
    assert geometry.audit(directory)==value
    assert value['scan_directories']==['/tables','/undo','/empty']
    assert value['system_files'][1]=={'native_name':'/system/second','backup_name':'second','suffix':'12M:autoextend','source_file':'/system/second'}
    assert (directory/'first').read_bytes()==b'owned native page first'
    assert (directory/geometry.FILE).stat().st_mode&0o077==0


@pytest.mark.parametrize('fault',['no-consent','catalog-mismatch','undo-name-collision','relative-home','raw-device'])
def test_unadmitted_source_storage_is_refused_before_sealing_or_native_dispatch(fault):
    request=source()
    if fault=='no-consent':request['isolate_external_paths']=False
    elif fault=='catalog-mismatch':request['source_storage']['files'][0]['file_name']='/different/file'
    elif fault=='undo-name-collision':request['source_storage']['files'].append({'file_name':'/other/extra.ibu','tablespace_name':'different_undo','file_type':'UNDO LOG'})
    elif fault=='relative-home':request['source_storage']['variables']['innodb_data_home_dir']='relative'
    else:request['source_storage']['variables']['innodb_data_file_path']='/system/first:12Mraw'
    with pytest.raises(worker.Refused):geometry.from_source(request)


def test_native_checkpoint_geometry_must_match_reviewed_source(tmp_path):
    request,directory,_value=captured(tmp_path)
    (directory/geometry.FILE).unlink()
    (directory/'backup-my.cnf').write_text('[mysqld]\ninnodb_data_file_path=/different/file:12M\n')
    with pytest.raises(worker.Refused,match='changed after'):geometry.capture(request,directory)
    assert not (directory/geometry.FILE).exists()


def test_private_prepare_flattens_native_filenames_and_retains_original_metadata_outside_cleanup(tmp_path):
    _request,original,value=captured(tmp_path)
    before=worker.manifest(original);target=tmp_path/'working'
    import shutil
    shutil.copytree(original,target);job=tmp_path/'job';job.mkdir()
    assert geometry.stage_prepare(job,target)==value
    assert not (target/geometry.FILE).exists()
    args=geometry.prepare_arguments(target,value)
    assert '--innodb-data-file-path=first:12M;second:12M:autoextend' in args
    assert '--innodb-undo-directory='+str(target) in args
    geometry.restore_prepare(job,target)
    assert geometry.audit(target)==value and worker.manifest(original)==before


def test_recovery_does_not_relax_absolute_path_refusal_without_retained_matching_metadata(tmp_path):
    _request,directory,value=captured(tmp_path)
    with pytest.raises(worker.Refused):recovery.configuration(directory/'backup-my.cnf',original_datadir='/original/data')
    accepted=recovery.configuration(directory/'backup-my.cnf',original_datadir='/original/data',mapped_storage=value)
    assert accepted['innodb_data_file_path']==value['variables']['innodb_data_file_path']
    changed=deepcopy(value);changed['variables']['innodb_data_file_path']='different:12M'
    with pytest.raises(worker.Refused,match='differs'):recovery.configuration(directory/'backup-my.cnf',mapped_storage=changed)


def test_native_copy_back_uses_private_system_destinations_and_a_separate_undo_pool(tmp_path):
    request,original,value=captured(tmp_path);job=tmp_path/'job';job.mkdir();target=job/'artifact';target.mkdir()
    context=paths.admission({**request,'phase':'copy_back'},[],storage=value)
    assert {row['source_root'] for row in context['plan']}=={'/system','/undo','/tables','/empty'}
    args=geometry.copy_back_arguments(job,target,value,context)
    assert not any(option.startswith('--innodb-data-file-path=/system/') for option in args)
    assert '--innodb-undo-directory='+str(job/'undo-copy-back') in args
    assert not list(target.iterdir())  # Native copy-back requires an empty datadir.
    pool=job/'undo-copy-back';pool.mkdir()
    for row in value['undo_files']:(pool/row['backup_name']).write_bytes(('owned undo '+row['backup_name']).encode())
    geometry.finish_copy_back(job,original,target,value,context)
    assert not pool.exists()
    for row in value['undo_files']:
        assert geometry.destination(row['source_file'],target,context).read_bytes()==('owned undo '+row['backup_name']).encode()
    assert geometry.destination('/empty',target,context).is_dir()
    assert worker.read_json(target/geometry.FILE)==value


def test_unexpected_native_undo_output_is_not_given_a_guessed_original_path(tmp_path):
    request,original,value=captured(tmp_path);job=tmp_path/'job';job.mkdir();target=job/'artifact';target.mkdir()
    context=paths.admission({**request,'phase':'copy_back'},[],storage=value)
    pool=job/'undo-copy-back';pool.mkdir();(pool/'unknown.ibu').write_bytes(b'native but unmapped')
    with pytest.raises(worker.Refused,match='inventory'):geometry.finish_copy_back(job,original,target,value,context)
    assert (pool/'unknown.ibu').read_bytes()==b'native but unmapped'


def test_new_unobserved_undo_file_cannot_be_sealed_using_an_earlier_source_inventory(tmp_path):
    _request,directory,_value=captured(tmp_path)
    (directory/'created_during_backup.ibu').write_bytes(b'owned new native file')
    with pytest.raises(worker.Refused,match='publication withheld'):geometry.audit(directory)


def test_literal_system_filename_is_preserved_in_private_argument_vectors(tmp_path):
    request=source();literal='/system/first one 雪'
    request['source_storage']['variables']['innodb_data_file_path']=literal+':12M;/system/second:12M:autoextend'
    request['source_storage']['files'][0]['file_name']=literal
    value=geometry.from_source(request)
    assert geometry.prepare_arguments(tmp_path,value)[0]=='--innodb-data-file-path=first one 雪:12M;second:12M:autoextend'


def test_native_relative_system_catalog_names_use_the_observed_data_home():
    request=source()
    request['source_storage']['variables']['innodb_data_home_dir']='/system'
    request['source_storage']['variables']['innodb_data_file_path']='first:12M;second:12M:autoextend'
    for row in request['source_storage']['files']:
        if row['tablespace_name']=='innodb_system':row['file_name']='./'+Path(row['file_name']).name
    value=geometry.from_source(request)
    assert [row['source_file'] for row in value['system_files']]==['/system/first','/system/second']
    assert value['original_datadir']=='/original/data' and value['data_home']=='/system'


@pytest.mark.parametrize('fault',[None,'receipt','prepared-bytes','copy-back','symlink'])
def test_runtime_metadata_is_bound_to_prepared_receipt_and_copy_back_bytes(tmp_path,fault):
    import shutil
    _request,original,value=captured(tmp_path);copied=tmp_path/'copied';copied.mkdir()
    shutil.copyfile(original/geometry.FILE,copied/geometry.FILE)
    artifact={'storage_geometry':deepcopy(value),'files':worker.manifest(original)}
    if fault=='receipt':artifact['storage_geometry']['scan_directories'].append('/unreviewed')
    elif fault=='prepared-bytes':(original/geometry.FILE).write_text((original/geometry.FILE).read_text()+'\n')
    elif fault=='copy-back':worker.host.save(copied/geometry.FILE,{'unreviewed':'different'})
    elif fault=='symlink':
        (original/geometry.FILE).unlink();(original/geometry.FILE).symlink_to(copied/geometry.FILE)
    if fault:
        with pytest.raises(worker.Refused):geometry.retained(original,artifact,copied)
    else:assert geometry.retained(original,artifact,copied)==value

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


@pytest.mark.parametrize('fault',['no-consent','catalog-mismatch','undo-name-collision','circular-home'])
def test_unadmitted_source_storage_is_refused_before_sealing_or_native_dispatch(fault):
    request=source()
    if fault=='no-consent':request['isolate_external_paths']=False
    elif fault=='catalog-mismatch':request['source_storage']['files'][0]['file_name']='/different/file'
    elif fault=='undo-name-collision':request['source_storage']['files'].append({'file_name':'/other/extra.ibu','tablespace_name':'different_undo','file_type':'UNDO LOG'})
    elif fault=='circular-home':request['source_storage']['variables']['innodb_data_home_dir']='/system/link/../different'
    with pytest.raises(worker.Refused):geometry.from_source(request)


@pytest.mark.parametrize('mode',['raw','newraw'])
def test_raw_system_geometry_retains_native_mode_and_uses_only_private_regular_files(tmp_path,mode):
    request=source();variables=request['source_storage']['variables']
    variables['innodb_data_file_path']='/dev/source-system:32M'+mode
    request['source_storage']['files']=[row for row in request['source_storage']['files'] if row['file_type']=='UNDO LOG']+[
        {'file_name':'/dev/source-system','tablespace_name':'innodb_system','file_type':'TABLESPACE'}]
    value=geometry.from_source(request)
    raw=value['system_files'][0]
    assert raw['raw_mode']==mode and raw['suffix']=='32M'+mode and raw['regular_suffix']=='32M'
    assert geometry.prepare_arguments(tmp_path,value)[0]=='--innodb-data-file-path=source-system:32M'
    context=paths.admission({**request,'phase':'copy_back'},[],storage=value)
    selected=next(row for row in context['plan'] if row.get('kind')=='file')
    assert selected['source_root']=='/dev/source-system'
    private=geometry.destination('/dev/source-system',tmp_path,context)
    assert geometry.copy_back_arguments(tmp_path,tmp_path,value,context)[0]=='--innodb-data-file-path='+str(private)+':32M'
    data=tmp_path/'data';(data/'external-data').mkdir(parents=True)
    _aliases,arguments=paths.runtime(tmp_path,data,context)
    assert '--innodb-data-file-path=/dev/source-system:32M' in arguments
    assert all('newraw' not in arg and not arg.endswith('32Mraw') for arg in arguments)


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


def test_relative_homes_scan_roots_and_prefixed_undo_catalog_use_native_datadir():
    request=source();request['binding']['datadir']='/server/data'
    variables=request['source_storage']['variables']
    variables.update(innodb_data_home_dir='../system/deep',innodb_data_file_path='first:12M;second:12M:autoextend',
        innodb_undo_directory='../undo/deep',innodb_directories='../tables/deep;../undo/deep;../empty/deep')
    for row in request['source_storage']['files']:
        name=Path(row['file_name']).name
        row['file_name']='./'+name if row['file_type']=='TABLESPACE' else '../undo/deep/'+name
    value=geometry.from_source(request)
    assert value['data_home']=='/server/system/deep' and value['undo_home']=='/server/undo/deep'
    assert value['scan_directories']==['/server/tables/deep','/server/undo/deep','/server/empty/deep']
    assert [row['source_file'] for row in value['undo_files']]==[
        '/server/undo/deep/undo_001','/server/undo/deep/undo_002','/server/undo/deep/extra.ibu']
    assert value['variables']==variables


def test_leading_parent_system_specs_keep_source_names_and_resolved_file_identity():
    request=source();request['binding']['datadir']='/server/data'
    request['source_storage']['variables'].update(innodb_data_home_dir='',
        innodb_data_file_path='../system/first:12M;../system/second:12M:autoextend',innodb_undo_directory='../undo',innodb_directories='')
    for row in request['source_storage']['files']:
        row['file_name']=('../system/' if row['file_type']=='TABLESPACE' else '../undo/')+Path(row['file_name']).name
    value=geometry.from_source(request)
    assert [row['source_file'] for row in value['system_files']]==['/server/system/first','/server/system/second']
    assert value['system_files'][0]['native_name']=='../system/first'


def test_internal_nondefault_homes_are_retained_even_without_external_files():
    request=source();request['binding']['datadir']='/server/data'
    request['source_storage']['variables'].update(innodb_data_home_dir='system',innodb_data_file_path='first:12M;second:12M:autoextend',
        innodb_undo_directory='undo',innodb_directories='')
    for row in request['source_storage']['files']:
        row['file_name']='./'+Path(row['file_name']).name if row['file_type']=='TABLESPACE' else 'undo/'+Path(row['file_name']).name
    value=geometry.from_source(request)
    assert value and value['data_home']=='/server/data/system' and value['undo_home']=='/server/data/undo'


def circular_source(tmp_path):
    request=source();data=tmp_path/'data';data.mkdir()
    request['binding']['datadir']=str(data)
    for name in ('system','undo','empty'):
        root=tmp_path/name;(root/'deep/nested').mkdir(parents=True)
        (root/'deep/leaf').mkdir();(root/'link').symlink_to(root/'deep/nested',target_is_directory=True)
    values=request['source_storage']['variables']
    values.update(innodb_data_home_dir='../system/link/../leaf',
        innodb_data_file_path='first:12M;second:12M:autoextend',innodb_undo_directory='../undo/link/../leaf',
        innodb_directories='../empty/link/../leaf')
    for row in request['source_storage']['files']:
        name=Path(row['file_name']).name
        row['file_name']=name if row['file_type']=='TABLESPACE' else '../undo/link/../leaf/'+name
        ((tmp_path/('system' if row['file_type']=='TABLESPACE' else 'undo')/'deep/leaf')/name).write_bytes(b'owned native file')
    return request


def test_native_filesystem_resolution_preserves_symlink_parent_semantics_and_offline_audit(tmp_path):
    request=circular_source(tmp_path)
    with pytest.raises(geometry.ResolutionRequired):geometry.from_source(request)
    value=geometry.from_source(request,filesystem=True)
    assert value['data_home']==str(tmp_path/'system/deep/leaf')
    assert value['undo_home']==str(tmp_path/'undo/deep/leaf')
    assert value['scan_directories']==[str(tmp_path/'empty/deep/leaf')]
    assert value['catalog_files']==request['source_storage']['files']
    artifact=tmp_path/'artifact';artifact.mkdir()
    (artifact/'backup-my.cnf').write_text('[mysqld]\ninnodb_data_file_path='+value['variables']['innodb_data_file_path']+
        '\ninnodb_undo_directory='+value['variables']['innodb_undo_directory']+'\n')
    assert geometry.capture(request,artifact,reviewed=value)==value
    import shutil
    for name in ('system','undo','empty'):shutil.rmtree(tmp_path/name)
    assert geometry.audit(artifact)==value
    assert recovery.configuration(artifact/'backup-my.cnf',mapped_storage=value)['innodb_data_file_path']==value['variables']['innodb_data_file_path']


def test_source_filesystem_resolution_must_still_match_original_review(tmp_path):
    request=circular_source(tmp_path);value=geometry.from_source(request,filesystem=True)
    root=tmp_path/'empty';(root/'other/leaf').mkdir(parents=True);(root/'other/nested').mkdir()
    (root/'link').unlink();(root/'link').symlink_to(root/'other/nested',target_is_directory=True)
    with pytest.raises(worker.Refused,match='changed after'):geometry.capture(request,tmp_path/'unused',reviewed=value)


@pytest.mark.parametrize('fault',['missing','extra','relative','circular','catalog'])
def test_retained_resolution_cannot_omit_or_invent_original_filesystem_paths(tmp_path,fault):
    request=circular_source(tmp_path);value=geometry.from_source(request,filesystem=True);observed=deepcopy(value['resolved_paths'])
    key=next(iter(observed))
    if fault=='missing':del observed[key]
    elif fault=='extra':observed['/unobserved/link/../file']='/unobserved/file'
    elif fault=='relative':observed[key]='relative'
    elif fault=='circular':observed[key]='/again/link/../file'
    else:request['source_storage']['files'][0]['file_name']='unobserved-system-file'
    with pytest.raises(worker.Refused):geometry.from_source(request,observed_paths=observed)


def test_missing_circular_source_directory_is_not_lexically_guessed(tmp_path):
    request=circular_source(tmp_path);(tmp_path/'system/link').unlink()
    with pytest.raises(worker.Refused,match='unavailable'):geometry.from_source(request,filesystem=True)


def test_runtime_uses_retained_system_identities_after_original_traversal_dirs_disappear(tmp_path):
    request=circular_source(tmp_path);value=geometry.from_source(request,filesystem=True)
    context=paths.admission({**request,'phase':'copy_back'},[],storage=value)
    directory=tmp_path/'runtime';data=directory/'data';(data/'external-data').mkdir(parents=True)
    aliases,args=paths.runtime(directory,data,context)
    assert '--innodb-data-home-dir='+value['data_home'] in args
    assert '--innodb-undo-directory='+value['undo_home'] in args
    assert '--innodb-data-file-path='+str(tmp_path/'system/deep/leaf/first')+':12M;'+str(tmp_path/'system/deep/leaf/second')+':12M:autoextend' in args
    assert all('..' not in Path(row['source_root']).parts for row in aliases)


def test_native_null_default_homes_and_scan_roots_do_not_require_a_synthetic_mapping():
    request=source();request['source_storage']['variables'].update(innodb_data_home_dir=None,
        innodb_data_file_path='ibdata1:12M:autoextend',innodb_undo_directory=None,innodb_directories=None)
    request['source_storage']['files']=[{'file_name':'./ibdata1','tablespace_name':'innodb_system','file_type':'TABLESPACE'},
        {'file_name':'./undo_001','tablespace_name':'innodb_undo_001','file_type':'UNDO LOG'},
        {'file_name':'./undo_002','tablespace_name':'innodb_undo_002','file_type':'UNDO LOG'}]
    assert geometry.from_source(request) is None
    assert request['source_storage']['variables']['innodb_directories'] is None


def test_retained_external_storage_preserves_null_defaults_and_native_effective_undo_home(tmp_path):
    request=source();request['source_storage']['variables'].update(innodb_data_home_dir=None,
        innodb_undo_directory=None,innodb_directories=None)
    directory=tmp_path/'artifact';directory.mkdir()
    (directory/'backup-my.cnf').write_text('[mysqld]\ninnodb_data_file_path=/system/first:12M;/system/second:12M:autoextend\ninnodb_undo_directory=./\n')
    value=geometry.capture(request,directory)
    assert value['variables']['innodb_data_home_dir'] is None and value['variables']['innodb_undo_directory'] is None
    assert value['undo_home']=='/original/data' and value['scan_directories']==[]
    assert geometry.audit(directory)==value
    assert recovery.configuration(directory/'backup-my.cnf',mapped_storage=value)['innodb_data_file_path']==value['variables']['innodb_data_file_path']


@pytest.mark.parametrize('number',[1,2,3,4,127])
def test_native_undo_number_survives_truncation_space_id_rotation(number):
    for generation in (0,1,399999):
        space_id=0xFFFFFFEF-(number-1)-127*generation
        assert geometry.undo_number(space_id)==number


@pytest.mark.parametrize('space_id',[None,True,'4294967277',0,0xFFFFFFF0,0xFFFFFFF0-127*400000-1])
def test_unobserved_or_non_native_undo_space_ids_are_refused(space_id):
    with pytest.raises(worker.Refused):geometry.undo_number(space_id)


def numbered_source():
    request=source();undo=[row for row in request['source_storage']['files'] if row['file_type']=='UNDO LOG']
    undo.append({'file_name':'/other/same.ibu','tablespace_name':'second_named_undo','file_type':'UNDO LOG'})
    request['source_storage']['files']=[row for row in request['source_storage']['files'] if row['file_type']!='UNDO LOG']+undo
    for number,row in enumerate(undo,1):row['undo_number']=number
    undo[2]['file_name']='/undo/same.ibu'
    return request


def test_duplicate_native_undo_paths_need_qualified_naming_and_keep_original_identities(tmp_path):
    request=numbered_source()
    with pytest.raises(geometry.ResolutionRequired,match='qualified numbered'):geometry.from_source(request)
    value=geometry.from_source(request,undo_naming=geometry.UNDO_NAMING)
    assert [row['backup_name'] for row in value['undo_files']]==['undo_001','undo_002','sr-undo-3.ibu','sr-undo-4.ibu']
    assert [row['source_file'] for row in value['undo_files']][-2:]==['/undo/same.ibu','/other/same.ibu']
    original=tmp_path/'original';original.mkdir()
    (original/'backup-my.cnf').write_text('[mysqld]\ninnodb_data_file_path=/system/first:12M;/system/second:12M:autoextend\ninnodb_undo_directory=/undo\n')
    assert geometry.capture(request,original,reviewed=value)==value
    assert geometry.audit(original)==value
    job=tmp_path/'job';job.mkdir();target=job/'artifact';target.mkdir();pool=job/'undo-copy-back';pool.mkdir()
    for row in value['undo_files']:(pool/row['backup_name']).write_bytes(('native '+str(row['undo_number'])).encode())
    context=paths.admission({**request,'phase':'copy_back'},[],storage=value)
    geometry.finish_copy_back(job,original,target,value,context)
    assert geometry.destination('/undo/same.ibu',target,context).read_bytes()==b'native 3'
    assert geometry.destination('/other/same.ibu',target,context).read_bytes()==b'native 4'


@pytest.mark.parametrize('fault',['missing-number','duplicate-number','bool','range','unknown-naming','no-consent'])
def test_numbered_undo_does_not_guess_identity_or_downgrade_review(fault):
    request=numbered_source();naming=geometry.UNDO_NAMING;row=request['source_storage']['files'][-1]
    if fault=='missing-number':row.pop('undo_number')
    elif fault=='duplicate-number':row['undo_number']=3
    elif fault=='bool':row['undo_number']=True
    elif fault=='range':row['undo_number']=128
    elif fault=='unknown-naming':naming='guessed'
    else:request['isolate_external_paths']=False
    with pytest.raises(worker.Refused):geometry.from_source(request,undo_naming=naming)


@pytest.mark.parametrize('kind',['numbered','filesystem','unqualified-numbered','both'])
def test_application_review_requires_the_specific_pending_host_observation(kind):
    from pgadmin.cdeadmin.workspace import mysql_physical_service as service
    value=geometry.from_source(numbered_source(),undo_naming=geometry.UNDO_NAMING)
    captured={'state':{'native_undo_naming_pending':True}}
    if kind in {'filesystem','both'}:captured['state']['native_storage_resolution_pending']=True
    if kind=='both':value['resolved_paths']={'/retained/link/../file':'/retained/effective/file'}
    if kind=='unqualified-numbered':value.pop('undo_naming')
    observed={'external_paths':{'storage':value}}
    if kind in {'filesystem','unqualified-numbered'}:
        with pytest.raises(service.native.HostError):service.resolve_storage(captured,observed)
    else:
        service.resolve_storage(captured,observed)
        assert {'file_name':'/undo/same.ibu'} in captured['state']['native_external_files']
        assert {'file_name':'/other/same.ibu'} in captured['state']['native_external_files']


def system_collision_source():
    request=source()
    request['source_storage']['variables']['innodb_data_file_path']='/system-b/same:12M;/system-a/same:12M:autoextend'
    system=[row for row in request['source_storage']['files'] if row['file_type']=='TABLESPACE']
    for row,name in zip(system,('/system-a/same','/system-b/same')):row['file_name']=name
    return request


def test_duplicate_system_names_keep_native_file_order_independent_of_catalog_order(tmp_path):
    request=system_collision_source()
    with pytest.raises(geometry.SystemNamingRequired):geometry.from_source(request)
    value=geometry.from_source(request,system_naming=geometry.SYSTEM_NAMING)
    assert [row['source_file'] for row in value['system_files']]==['/system-b/same','/system-a/same']
    assert [row['backup_name'] for row in value['system_files']]==['sr-system-0.ibdata','sr-system-1.ibdata']
    assert geometry.backup_arguments(value)==['--scratchrobin-system-file-numbers']
    assert geometry.prepare_arguments(tmp_path,value)[0]=='--innodb-data-file-path=sr-system-0.ibdata:12M;sr-system-1.ibdata:12M:autoextend'
    context=paths.admission({**request,'phase':'copy_back'},[],storage=value)
    args=geometry.copy_back_arguments(tmp_path,tmp_path,value,context)
    assert args[-1]=='--scratchrobin-system-file-numbers'
    assert '/system-b/same' not in args[0] and '/system-a/same' not in args[0]
    artifact=tmp_path/'artifact';artifact.mkdir();(artifact/'backup-my.cnf').write_text('[mysqld]\ninnodb_data_file_path='+request['source_storage']['variables']['innodb_data_file_path']+'\ninnodb_undo_directory=/undo\n')
    assert geometry.capture(request,artifact,reviewed=value)==geometry.audit(artifact)==value


def test_system_file_can_share_a_basename_with_native_default_undo_without_overwriting_it():
    request=source();request['source_storage']['variables']['innodb_data_file_path']='/system/undo_001:12M;/system/second:12M:autoextend'
    request['source_storage']['files'][0]['file_name']='/system/undo_001'
    with pytest.raises(geometry.SystemNamingRequired):geometry.from_source(request)
    value=geometry.from_source(request,system_naming=geometry.SYSTEM_NAMING)
    assert value['system_files'][0]['backup_name']=='sr-system-0.ibdata'
    assert value['undo_files'][0]['backup_name']=='undo_001'
    assert len({row['backup_name'] for row in [*value['system_files'],*value['undo_files']]})==5


@pytest.mark.parametrize('fault',['no-consent','unknown-profile','unqualified-host','different-original-path'])
def test_system_numbering_never_guesses_or_weakens_the_original_storage_review(tmp_path,fault):
    from pgadmin.cdeadmin.workspace import mysql_physical_service as service
    request=system_collision_source();value=geometry.from_source(request,system_naming=geometry.SYSTEM_NAMING)
    if fault=='no-consent':
        request['isolate_external_paths']=False
        with pytest.raises(worker.Refused):geometry.from_source(request,system_naming=geometry.SYSTEM_NAMING)
    elif fault=='unknown-profile':
        with pytest.raises(worker.Refused):geometry.from_source(request,system_naming='guessed-index')
    elif fault=='unqualified-host':
        value.pop('system_naming')
        with pytest.raises(service.native.HostError):service.resolve_storage({'state':{'native_system_naming_pending':True}},{'external_paths':{'storage':value}})
    else:
        request['source_storage']['files'][0]['file_name']='/changed/same'
        with pytest.raises(worker.Refused):geometry.capture(request,tmp_path,reviewed=value)


def test_ordinal_capability_does_not_rename_unambiguous_existing_native_layouts():
    request=source();old=geometry.from_source(request)
    assert geometry.from_source(request,system_naming=geometry.SYSTEM_NAMING)==old
    assert geometry.backup_arguments(old)==[]

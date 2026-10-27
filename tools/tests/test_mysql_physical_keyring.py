"""Opaque native keys, exact chain secrets and private recovery provisioning."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_keyring as keyring
from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_worker as worker


def source(tmp_path):
    native=tmp_path/'native';native.mkdir()
    plugins=native/'plugin';plugins.mkdir()
    (plugins/'component_keyring_file.so').write_bytes(b'owned native component bytes')
    (plugins/'component_keyring_file.cnf').write_text('{"path":"/original/keys","read_only":false}')
    private=native/'private';private.mkdir();(private/'libprotobuf.so.1').write_bytes(b'owned native dependency')
    (private/'libprotobuf.so').symlink_to('libprotobuf.so.1')
    xtra=tmp_path/'xtra';xtra.mkdir();(xtra/'component_keyring_file.so').write_bytes(b'owned native utility component')
    material=tmp_path/'live-keys';material.write_bytes(b'opaque native bytes\x00\xff')
    data=tmp_path/'live-data';data.mkdir()
    (data/'mysqld.my').write_text('{"components":"file://component_keyring_file;file://another_native_component"}')
    request={'phase':'backup','keyring':{'xtrabackup_plugin_dir':str(xtra)},'binding':{'datadir':str(data)},
        'source_keyring':{'component':'component_keyring_file','data_file':str(material),'server_plugin_directory':str(plugins),
            'encryption':{'redo':True,'undo':True,'binlog':False}}}
    return request,keyring.inspect(request),material


def captured(tmp_path):
    request,context,original=source(tmp_path)
    job=tmp_path/'job';job.mkdir();artifact=job/'artifact';artifact.mkdir()
    secret=keyring.backup_key(job)
    value=keyring.capture(job,artifact,context)
    return request,context,original,job,artifact,secret,value


def test_native_material_is_opaque_private_and_not_part_of_public_facts(tmp_path):
    request,context,original,job,artifact,secret,value=captured(tmp_path)
    root=artifact/keyring.DIRECTORY
    assert (root/'keyring').read_bytes()==original.read_bytes()
    assert (root/'keyring').stat().st_mode&0o077==0
    assert not (job/keyring.TRANSITION).exists()
    assert value['keyring_sha256']==hashlib.sha256(original.read_bytes()).hexdigest()
    assert secret not in json.dumps(value) and 'opaque native bytes' not in json.dumps(value)
    assert value['private_key_material_retained'] and context['retains_private_key_material']
    assert (root/'mysqld.my').read_bytes()==(Path(request['binding']['datadir'])/'mysqld.my').read_bytes()


def test_transition_key_uses_native_option_file_without_changing_SQL_options(tmp_path):
    directory=tmp_path/'job';directory.mkdir();secret=keyring.backup_key(directory)
    request={'database_credentials':{'user':'native','password':'private password'},'sql_host':'127.0.0.1','sql_port':3306}
    option=worker.client_options(request,directory,transition_key=secret)
    import configparser
    parser=configparser.ConfigParser(interpolation=None);parser.read_string(option.read_text())
    assert 'transition-key' not in parser['client']
    assert parser['xtrabackup']['transition-key']=='"'+secret+'"'
    assert option.stat().st_mode&0o077==0
    worker.clean_client_options(directory);keyring.cleanup(directory,material_retained=True)
    assert (directory/keyring.TRANSITION).read_text()==secret
    keyring.cleanup(directory,material_retained=False);assert not list(directory.iterdir())


def test_incremental_reuses_exact_chain_key_and_replaces_only_the_private_keyring_snapshot(tmp_path):
    _request,context,original,_job,base,secret,value=captured(tmp_path)
    delta_job=tmp_path/'delta-job';delta_job.mkdir();delta=delta_job/'artifact';delta.mkdir()
    assert keyring.backup_key(delta_job,base)==secret
    original.write_bytes(b'new native master-key snapshot')
    newest=keyring.capture(delta_job,delta,context)
    target=tmp_path/'working';target.mkdir();keyring.copied_snapshot(base,target)
    assert keyring.apply_snapshot(target,delta)==newest
    assert keyring.audit(base)==value and keyring.audit(delta)==newest
    assert keyring.read_key(target/keyring.DIRECTORY)==secret


def test_other_chain_key_is_refused_without_replacing_working_material(tmp_path):
    _request,context,_original,_job,base,_secret,value=captured(tmp_path)
    other_job=tmp_path/'other-job';other_job.mkdir();other=other_job/'artifact';other.mkdir()
    keyring.backup_key(other_job);keyring.capture(other_job,other,context)
    target=tmp_path/'working';target.mkdir();keyring.copied_snapshot(base,target)
    with pytest.raises(worker.Refused,match='original chain'):keyring.apply_snapshot(target,other)
    assert keyring.audit(target)==value


def test_private_runtime_library_and_keyring_configuration_never_change_original_paths(tmp_path):
    request,_context,original,_job,artifact,_secret,value=captured(tmp_path)
    selected=keyring.inspect({**request,'phase':'recover'},value)
    runtime=tmp_path/'runtime';runtime.mkdir();data=runtime/'runtime-data';data.mkdir();keyring.copied_snapshot(artifact,data)
    before=original.read_bytes();plugins=Path(request['source_keyring']['server_plugin_directory'])
    source_config=(plugins/'component_keyring_file.cnf').read_bytes()
    args=keyring.runtime(runtime,data,selected)
    config=json.loads((runtime/'runtime-plugins/component_keyring_file.cnf').read_text())
    assert config=={'path':str(data/keyring.DIRECTORY/'keyring'),'read_only':False}
    assert '--plugin-dir='+str(runtime/'runtime-plugins') in args
    assert '--innodb-redo-log-encrypt=ON' in args and '--innodb-undo-log-encrypt=ON' in args
    assert (runtime/'private/libprotobuf.so').read_bytes()==b'owned native dependency'
    assert not (runtime/'private/libprotobuf.so').is_symlink()
    assert original.read_bytes()==before and (plugins/'component_keyring_file.cnf').read_bytes()==source_config
    assert (data/'mysqld.my').read_bytes()==(Path(request['binding']['datadir'])/'mysqld.my').read_bytes()


def test_changed_native_libraries_refuse_before_staging_them(tmp_path):
    request,context,_original=source(tmp_path)
    plugins=Path(request['source_keyring']['server_plugin_directory'])
    (plugins/'component_keyring_file.so').write_bytes(b'changed native library')
    with pytest.raises(worker.Refused,match='changed after review'):keyring.stage_libraries(context['server_plugins'],tmp_path/'staged')
    assert not (tmp_path/'staged').exists()


def test_missing_consent_never_silently_drops_encryption_keys(tmp_path):
    _request,_context,_original,_job,_artifact,_secret,value=captured(tmp_path)
    with pytest.raises(worker.Refused,match='explicitly'):keyring.inspect({'phase':'prepare'},value)


@pytest.mark.parametrize('fault',['symlink','bad-key','missing-metadata','unknown-component'])
def test_changed_key_material_is_not_admitted_as_a_native_snapshot(tmp_path,fault):
    _request,_context,original,_job,artifact,_secret,_value=captured(tmp_path);root=artifact/keyring.DIRECTORY
    if fault=='symlink':(root/'keyring').unlink();(root/'keyring').symlink_to(original)
    elif fault=='bad-key':(root/'transition.key').write_text('not a native transition key')
    elif fault=='missing-metadata':(root/'metadata.json').unlink()
    else:
        value=json.loads((root/'metadata.json').read_text());value['component']='unsupported-keyring';(root/'metadata.json').write_text(json.dumps(value))
    with pytest.raises((worker.Refused,OSError)):keyring.audit(artifact)


def test_empty_native_file_keyring_is_preserved_without_inventing_key_data(tmp_path):
    _request,context,original=source(tmp_path);original.write_bytes(b'')
    job=tmp_path/'job';job.mkdir();artifact=job/'artifact';artifact.mkdir();keyring.backup_key(job)
    value=keyring.capture(job,artifact,context)
    assert value['keyring_bytes']=='0' and (artifact/keyring.DIRECTORY/'keyring').read_bytes()==b''


def test_prepare_temporarily_includes_secret_options_only_from_its_private_config(tmp_path):
    target=tmp_path/'private-prepare';target.mkdir();config=target/'backup-my.cnf'
    original=b'[mysqld]\ninnodb_page_size=16384\n';config.write_bytes(original)
    option=keyring.native_options(tmp_path,'a'*64)
    saved=keyring.prepare_options(target,option)
    assert saved==original and b'!include '+str(option).encode() in config.read_bytes()
    assert b'a'*64 not in config.read_bytes()
    keyring.restore_prepare_options(target,saved);keyring.cleanup(tmp_path,material_retained=True)
    assert config.read_bytes()==original and not option.exists()


def test_native_incremental_cleanup_cannot_remove_staged_opaque_material(tmp_path):
    _request,_context,_original,job,artifact,_secret,value=captured(tmp_path)
    keyring.stage_prepare_material(job,artifact)
    assert not (artifact/keyring.DIRECTORY).exists()
    assert (job/keyring.STAGED/'keyring').is_file()
    keyring.restore_prepare_material(job,artifact)
    assert keyring.audit(artifact)==value and not (job/keyring.STAGED).exists()


def test_native_copied_keyring_is_verified_and_its_permissions_are_private(tmp_path):
    _request,_context,_original,_job,artifact,_secret,value=captured(tmp_path)
    import shutil
    target=tmp_path/'copied';target.mkdir();root=target/keyring.DIRECTORY
    shutil.copytree(artifact/keyring.DIRECTORY,root)
    (root/'keyring').chmod(0o644)
    keyring.copied_snapshot(artifact,target)
    assert keyring.audit(target)==value and (root/'keyring').stat().st_mode&0o077==0
    (root/'unexpected').write_text('native unexpected additional material')
    with pytest.raises(worker.Refused,match='differs'):keyring.copied_snapshot(artifact,target)

"""Raw recovery must not accept the stock utility's zero-page device copy."""
import hashlib
import json

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_physical_worker as worker


def package(tmp_path,monkeypatch):
    (tmp_path/'bin').mkdir();(tmp_path/'lib').mkdir()
    for name,data in [('bin/xtrabackup',b'owned utility'),('lib/libnative.so.1',b'owned dependency'),('native-raw.patch',b'owned source patch')]:
        (tmp_path/name).write_bytes(data)
    files={name:hashlib.sha256((tmp_path/name).read_bytes()).hexdigest() for name in
        ('bin/xtrabackup','lib/libnative.so.1','native-raw.patch')}
    monkeypatch.setattr(worker,'RAW_READER_PATCH',files['native-raw.patch'])
    value={'schema':'scratchrobin.native-backup-build.v1','upstream_revision':worker.REVISION,
        'patch_sha256':files['native-raw.patch'],'binary_sha256':files['bin/xtrabackup'],
        'research_candidate_only':False,'capabilities':['raw-system-files-v1'],
        'qualification':{'binary_sha256':files['bin/xtrabackup'],'qualified_extents':['fixed','autoextended'],'multiple_system_files':True},
        'libraries':{'libnative.so.1':files['lib/libnative.so.1']},'package_files':files}
    executable={'path':str(tmp_path/'bin/xtrabackup'),'sha256':files['bin/xtrabackup']}
    return value,executable


@pytest.mark.parametrize('fault',[None,'unqualified','patch','binary','library','missing','escape','manifest-link','shape','fixed-only','stale-qualification','missing-multiple'])
def test_raw_reader_requires_qualified_source_exact_package_bytes_and_private_dependencies(tmp_path,monkeypatch,fault):
    value,executable=package(tmp_path,monkeypatch)
    if fault=='unqualified':value['research_candidate_only']=True
    elif fault=='patch':value['patch_sha256']='0'*64
    elif fault=='binary':(tmp_path/'bin/xtrabackup').write_bytes(b'different utility with same reported version')
    elif fault=='library':(tmp_path/'lib/libnative.so.1').write_bytes(b'different native dependency')
    elif fault=='escape':value['package_files']['../outside']='0'*64
    elif fault=='shape':value=[]
    elif fault=='fixed-only':value['qualification']['qualified_extents']=['fixed']
    elif fault=='stale-qualification':value['qualification']['binary_sha256']='0'*64
    elif fault=='missing-multiple':value['qualification'].pop('multiple_system_files')
    manifest=tmp_path/'PROVENANCE.json'
    manifest.write_text(json.dumps(value))
    if fault=='missing':manifest.unlink()
    elif fault=='manifest-link':manifest.rename(tmp_path/'different.json');manifest.symlink_to(tmp_path/'different.json')
    if fault:
        with pytest.raises(worker.Refused):worker.raw_storage_backend(executable)
    else:
        admitted=worker.raw_storage_backend(executable)
        assert admitted['binary_sha256']==executable['sha256']
        assert admitted['libraries']==value['libraries']


@pytest.mark.parametrize('fault',[None,'missing-proof','old-capabilities','candidate','altered-dependency'])
def test_numbered_native_undo_profile_requires_its_own_qualified_source(tmp_path,monkeypatch,fault):
    value,executable=package(tmp_path,monkeypatch)
    monkeypatch.setattr(worker,'UNDO_READER_PATCH',value['patch_sha256'])
    value['capabilities'].append('undo-numbers-v1');value['qualification']['duplicate_undo_paths']=True
    if fault=='missing-proof':value['qualification'].pop('duplicate_undo_paths')
    elif fault=='old-capabilities':value['capabilities'].pop()
    elif fault=='candidate':value['research_candidate_only']=True
    elif fault=='altered-dependency':(tmp_path/'lib/libnative.so.1').write_bytes(b'other native library')
    (tmp_path/'PROVENANCE.json').write_text(json.dumps(value))
    if fault:
        with pytest.raises(worker.Refused):worker.raw_storage_backend(executable,optional=True)
    else:
        assert worker.raw_storage_backend(executable)['undo_naming']=='native-number-v1'


def test_stock_native_backup_utility_remains_usable_for_unambiguous_legacy_undo(tmp_path):
    executable={'path':str(tmp_path/'bin/xtrabackup'),'sha256':'0'*64}
    assert worker.raw_storage_backend(executable,optional=True) is None
    with pytest.raises(worker.Refused):worker.raw_storage_backend(executable)

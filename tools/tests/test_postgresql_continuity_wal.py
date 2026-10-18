"""WAL archive ownership, immutable review and independent staging contracts."""
from pathlib import Path
import threading
import uuid

import pytest

from pgadmin.cdeadmin.providers.postgresql.continuity import ContinuityError
from pgadmin.cdeadmin.providers.postgresql.continuity_recovery import recovery_options, recovery_command
from pgadmin.cdeadmin.providers.postgresql.continuity_wal import freeze, stage
from pgadmin.cdeadmin.workspace.postgresql_continuity_jobs import PostgreSQLContinuityJobs


SEGMENT = '000000010000000000000002'


@pytest.mark.parametrize('target', [
    {'kind':'xid','value':'4294967296'}, {'kind':'xid','value':'1; SELECT 1'},
    {'kind':'lsn','value':'0/123456789'}, {'kind':'name','value':'ü'*32},
    {'kind':'immediate','value':'ignored'}, {'kind':'time','value':'now','inclusive':1},
    {'kind':'lsn','value':'0/100','timeline':'0'}, {'kind':'name','value':'a','command':'arbitrary'},
])
def test_invalid_native_targets_never_enter_a_recovery_configuration(target):
    with pytest.raises(ContinuityError):recovery_options({'target':target,'wal_archive':'owned'})


def test_wal_selection_requires_a_target_and_owner_endpoint_directory(tmp_path):
    with pytest.raises(ContinuityError):recovery_options({'wal_archive':'owned'})
    with pytest.raises(ContinuityError):recovery_options({'target':{'kind':'name','value':'a'}})
    jobs=PostgreSQLContinuityJobs(tmp_path/'jobs.json',tmp_path/'backups')
    endpoint=str(uuid.uuid4());bucket=jobs.archive_directory(1,endpoint)
    assert bucket==tmp_path/'backups/wal-archives/1'/endpoint
    bucket.parent.mkdir(parents=True)
    bucket.symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(ContinuityError):jobs.archive_directory(1,endpoint)


def test_staged_wal_matches_review_without_changing_archive_or_original_backup(tmp_path):
    archive=tmp_path/'archives/owned';archive.mkdir(parents=True)
    source=archive/SEGMENT;source.write_bytes(b'completed native shaped WAL')
    reviewed=freeze(archive.parent,'owned')
    clone=tmp_path/'clone';(clone/'pg_wal').mkdir(parents=True)
    (clone/'pg_wal'/SEGMENT).write_bytes(b'older backup segment')
    result=stage(archive.parent,reviewed,clone,progress=lambda _event:None,cancel_signal=threading.Event())
    assert result['reviewed_content_matched'] and result['files']==1
    assert (clone/'pg_wal'/SEGMENT).read_bytes()==source.read_bytes()==b'completed native shaped WAL'
    source.write_bytes(b'changed after review')
    with pytest.raises(ContinuityError,match='changed after review'):
        stage(archive.parent,reviewed,clone,progress=lambda _event:None,cancel_signal=threading.Event())
    assert (clone/'pg_wal'/SEGMENT).read_bytes()==b'completed native shaped WAL'
    assert not list((clone/'pg_wal').glob('.scratchrobin-*'))


@pytest.mark.parametrize('kind',['partial','symlink','inventory','cancel'])
def test_unsafe_or_changed_wal_inputs_cannot_be_reported_staged(tmp_path,kind):
    archive=tmp_path/'archives/owned';archive.mkdir(parents=True)
    source=archive/SEGMENT;source.write_bytes(b'owned')
    if kind=='partial':source.rename(str(source)+'.partial')
    if kind=='symlink':source.unlink();source.symlink_to(Path(__file__))
    if kind in {'partial','symlink'}:
        with pytest.raises(ContinuityError):freeze(archive.parent,'owned')
        return
    reviewed=freeze(archive.parent,'owned');clone=tmp_path/'clone';(clone/'pg_wal').mkdir(parents=True)
    signal=threading.Event()
    if kind=='inventory':source.unlink()
    else:signal.set()
    with pytest.raises(ContinuityError):stage(archive.parent,reviewed,clone,progress=lambda _event:None,cancel_signal=signal)
    assert not list((clone/'pg_wal').iterdir())


def test_append_only_archive_growth_does_not_expand_a_reviewed_recovery(tmp_path):
    archive=tmp_path/'archives/owned';archive.mkdir(parents=True)
    (archive/SEGMENT).write_bytes(b'owned reviewed bytes')
    reviewed=freeze(archive.parent,'owned')
    extra=archive/(SEGMENT[:-1]+'3');extra.write_bytes(b'later completed native bytes')
    clone=tmp_path/'clone';(clone/'pg_wal').mkdir(parents=True)
    result=stage(archive.parent,reviewed,clone,progress=lambda _event:None,cancel_signal=threading.Event())
    assert {p.name for p in (clone/'pg_wal').iterdir()}=={SEGMENT}
    assert result['reviewed_content_matched'] and result['unreviewed_files_at_start']==1
    assert result['unreviewed_files_staged'] is False
    assert extra.read_bytes()==b'later completed native bytes'


@pytest.mark.parametrize('kind',['partial','symlink','directory','changed_reviewed'])
def test_archive_growth_never_admits_unsafe_entries_or_changed_pinned_bytes(tmp_path,kind):
    archive=tmp_path/'archives/owned';archive.mkdir(parents=True)
    (archive/SEGMENT).write_bytes(b'owned reviewed bytes')
    reviewed=freeze(archive.parent,'owned')
    extra=archive/(SEGMENT[:-1]+'3')
    if kind=='partial':extra.with_suffix('.partial').write_bytes(b'not complete')
    elif kind=='symlink':extra.symlink_to(Path(__file__))
    elif kind=='directory':extra.mkdir()
    else:
        extra.write_bytes(b'later completed file')
        (archive/SEGMENT).write_bytes(b'changed pinned bytes')
    clone=tmp_path/'clone';(clone/'pg_wal').mkdir(parents=True)
    with pytest.raises(ContinuityError):
        stage(archive.parent,reviewed,clone,progress=lambda _event:None,cancel_signal=threading.Event())
    assert not list((clone/'pg_wal').iterdir())


def test_pitr_configuration_contains_one_native_target_without_caller_commands(tmp_path):
    clone=tmp_path/'recovered-clone';clone.mkdir()
    options=recovery_options({'target':{'kind':'name','value':"Restore ü ' quoted"},'wal_archive':'owned'})
    _args,_sql,_output=recovery_command(tmp_path,options,'job-token')
    configuration=(tmp_path/'recovery.conf').read_text()
    assert "recovery_target_name = 'Restore ü '' quoted'" in configuration
    assert "recovery_target_action = 'promote'" in configuration and (clone/'recovery.signal').exists()
    assert 'primary_conninfo = \'\'' in configuration and "listen_addresses = ''" in configuration

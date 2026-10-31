"""Retention authority, byte changes, crash boundaries and offline reconciliation."""
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace
import uuid

import pytest

from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
from pgadmin.cdeadmin.workspace.mysql_binlog_jobs import MySQLBinlogJobs
from pgadmin.cdeadmin.workspace import mysql_archive_retention as retention


def wait(jobs, job_id, endpoint):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        result = jobs.get(job_id, 1, endpoint)
        if result['state'] not in {'active', 'dispatching', 'cancel_requested'}:
            return result
        time.sleep(.01)
    raise AssertionError('Owned retention worker did not finish')


@pytest.fixture
def fixture(tmp_path):
    jobs = MySQLBinlogJobs(tmp_path / 'jobs', tmp_path / 'archives')
    endpoint = str(uuid.uuid4())
    source = {'server_uuid': str(uuid.uuid4()), 'authenticated_principal': 'archive@%', 'active_role': 'NONE'}
    program = {'execution_host': {'kind': 'application-host'}, 'executable_sha256': 'owned'}
    records = []

    def verify(path, _source):
        data = (path / 'owned.bin').read_bytes()
        return {'files': [{'path': 'owned.bin', 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}],
                'total_bytes': len(data)}
    jobs.native_verify = verify

    def archive(*, days=100, native=None, state='completed', stopped=True):
        review = jobs.review(1, endpoint, {}, {'identity': native or source, 'state': {}}, 'config', program)
        record = jobs.load(review['job_id'], 1, endpoint)
        directory = jobs.directory(record) / 'archive'
        directory.mkdir()
        (directory / 'owned.bin').write_bytes(b'private native archive bytes ' + os.urandom(8))
        jobs.update(record, state=state, created_at=time.time() - days * 86400,
                    result={'artifact': verify(directory, source)}, native_process_termination_confirmed=stopped)
        record = jobs.load(review['job_id'], 1, endpoint)
        records.append(record)
        return record

    service = SimpleNamespace(_semantic_lock=threading.RLock())
    def action(operation, request):
        return retention.action(service, jobs, 1, endpoint, operation, request)
    yield SimpleNamespace(jobs=jobs, endpoint=endpoint, source=source, archive=archive, action=action, service=service)
    jobs.close()
    for value in vars(service).values():
        if isinstance(value, retention.RetentionJobs):
            value.close()


def test_policy_keeps_newest_for_each_identity_pins_and_unknown_processes(fixture):
    f = fixture
    old = f.archive()
    newest = f.archive(days=1)
    pinned = f.archive(days=101)
    unknown = f.archive(days=200, state='unknown', stopped=False)
    other = f.archive(native={**f.source, 'server_uuid': str(uuid.uuid4())})
    f.action('pin', {'job_id': pinned['job_id'], 'pinned': True})
    plan = f.action('retention_review', {'policy': {'retention_days': 30, 'keep_latest': 1}})
    assert [row['job_id'] for row in plan['continuation']['archives']] == [old['job_id']]
    assert plan['continuation']['excluded']['pinned'] == 1
    assert plan['continuation']['excluded']['minimum_count'] == 2
    for record in (newest, pinned, unknown, other):
        assert (f.jobs.directory(record) / 'archive' / 'owned.bin').is_file()


def test_manual_removal_requires_separate_unprotect_and_preserves_receipt(fixture):
    f = fixture; record = f.archive(); job_id = record['job_id']
    f.action('pin', {'job_id': job_id, 'pinned': True})
    with pytest.raises(BinlogArchiveError, match='Unprotect'):
        f.action('remove_artifact', {'job_id': job_id, 'confirmation': job_id})
    f.action('pin', {'job_id': job_id, 'pinned': False})
    result = f.action('remove_artifact', {'job_id': job_id, 'confirmation': job_id})
    assert result['artifact_removed'] and result['artifact_removal']['state'] == 'completed'
    assert not (f.jobs.directory(record) / 'archive').exists()
    assert f.jobs.load(job_id, 1, f.endpoint)['result'] == record['result']
    assert f.jobs.list(1, f.endpoint)['total'] == 1


@pytest.mark.parametrize('boundary', ['before_detach', 'during_delete', 'before_ack'])
def test_restart_reconciles_only_the_durable_removal_intent(fixture, monkeypatch, boundary):
    f = fixture; record = f.archive(); job_id = record['job_id']
    original_replace, original_rmtree = retention.durable_replace, retention.shutil.rmtree
    if boundary == 'before_detach':
        monkeypatch.setattr(retention, 'durable_replace', lambda *_args: (_ for _ in ()).throw(OSError('owned rename fault')))
    else:
        def fault(path):
            receipt = json.loads((f.jobs.path.with_name(f.jobs.path.name + '.jobs') / (job_id + '.json')).read_text())
            assert receipt['mysql_binlog_jobs'][job_id]['artifact_removal']['state'] == 'pending'
            if boundary == 'before_ack':
                original_rmtree(path)
            else:
                (path / 'owned.bin').unlink()
            raise OSError('owned cleanup fault')
        monkeypatch.setattr(retention.shutil, 'rmtree', fault)
    with pytest.raises(OSError):
        f.action('remove_artifact', {'job_id': job_id, 'confirmation': job_id})
    assert not f.jobs.load(job_id, 1, f.endpoint).get('artifact_removed')
    with pytest.raises(BinlogArchiveError, match='Reconcile'):
        f.action('remove_artifact', {'job_id': job_id, 'confirmation': job_id})
    monkeypatch.setattr(retention, 'durable_replace', original_replace)
    monkeypatch.setattr(retention.shutil, 'rmtree', original_rmtree)
    restarted = MySQLBinlogJobs(f.jobs.path, f.jobs.root)
    result = retention.remove(restarted, job_id, 1, f.endpoint, job_id, reconcile=True)
    assert result['artifact_removed']
    assert not list(f.jobs.directory(record).glob('.removing-*'))
    assert retention.remove(restarted, job_id, 1, f.endpoint, job_id, reconcile=True)['artifact_removed']


def test_retention_does_not_delete_new_or_newly_pinned_archives(fixture):
    f = fixture; old = f.archive(); newest = f.archive(days=1)
    reviewed = f.action('retention_review', {'policy': {'retention_days': 30, 'keep_latest': 1}})
    later = f.archive(days=200)
    f.action('pin', {'job_id': old['job_id'], 'pinned': True})
    request = {key: reviewed[key] for key in ('job_id', 'review_digest')}; request['confirmed'] = True
    f.action('retention_start', request)
    jobs = retention.manager(f.service, f.jobs)
    result = wait(jobs, reviewed['job_id'], f.endpoint)
    assert result['state'] == 'interrupted'
    for record in (old, newest, later):
        assert (f.jobs.directory(record) / 'archive' / 'owned.bin').is_file()
    result = f.action('retention_reconcile', {'job_id': reviewed['job_id'], 'confirmed': True})
    assert result['result']['unattempted_job_ids'] == [old['job_id']]
    assert f.action('retention_start', request)['state'] == 'reconciled'


def test_changed_bytes_refuse_removal_before_any_intent(fixture):
    f = fixture; old = f.archive(); f.archive(days=1)
    reviewed = f.action('retention_review', {'policy': {'retention_days': 30, 'keep_latest': 1}})
    path = f.jobs.directory(old) / 'archive' / 'owned.bin'
    path.write_bytes(b'changed after review')
    request = {key: reviewed[key] for key in ('job_id', 'review_digest')}; request['confirmed'] = True
    f.action('retention_start', request); jobs = retention.manager(f.service, f.jobs)
    assert wait(jobs, reviewed['job_id'], f.endpoint)['state'] == 'interrupted'
    assert not f.jobs.load(old['job_id'], 1, f.endpoint).get('artifact_removal')
    assert path.is_file()


def test_reconciliation_cannot_resume_another_removal_authority(fixture, monkeypatch):
    f = fixture; old = f.archive(); f.archive(days=1)
    reviewed = f.action('retention_review', {'policy': {'retention_days': 30, 'keep_latest': 1}})
    f.action('retention_cancel', {'job_id': reviewed['job_id']})
    original = retention.shutil.rmtree
    monkeypatch.setattr(retention.shutil, 'rmtree', lambda *_args: (_ for _ in ()).throw(OSError('owned manual fault')))
    with pytest.raises(OSError):
        f.action('remove_artifact', {'job_id': old['job_id'], 'confirmation': old['job_id']})
    monkeypatch.setattr(retention.shutil, 'rmtree', original)
    result = f.action('retention_reconcile', {'job_id': reviewed['job_id'], 'confirmed': True})
    assert result['result']['other_removal_job_ids'] == [old['job_id']]
    assert f.jobs.load(old['job_id'], 1, f.endpoint)['artifact_removal']['state'] == 'pending'
    assert next(f.jobs.directory(old).glob('.removing-*')).is_dir()


def test_large_inventory_selects_oldest_hundred_without_losing_latest_guards(fixture):
    f = fixture
    records = [f.archive(days=300-index) for index in range(103)]
    other = f.archive(native={**f.source, 'server_uuid': str(uuid.uuid4())})
    plan = f.action('retention_review', {'policy': {'retention_days': 30, 'keep_latest': 1}})
    selected = plan['continuation']['archives']
    assert plan['continuation']['eligible_count'] == 102 and len(selected) == 100
    assert [item['job_id'] for item in selected] == [row['job_id'] for row in records[:100]]
    assert plan['continuation']['excluded']['minimum_count'] == 2
    assert (f.jobs.directory(other) / 'archive').is_dir()


def test_successful_plan_is_bounded_and_duplicate_start_cannot_extend_it(fixture):
    f = fixture; old = f.archive(); f.archive(days=1)
    reviewed = f.action('retention_review', {'policy': {'retention_days': 30, 'keep_latest': 1}})
    request = {key: reviewed[key] for key in ('job_id', 'review_digest')}; request['confirmed'] = True
    f.action('retention_start', request); jobs = retention.manager(f.service, f.jobs)
    result = wait(jobs, reviewed['job_id'], f.endpoint)
    assert result['state'] == 'completed' and result['result']['removed_job_ids'] == [old['job_id']]
    assert result['native_process_dispatched'] is False and result['automatic_retry'] is False
    later = f.archive(days=200)
    assert f.action('retention_start', request)['state'] == 'completed'
    assert (f.jobs.directory(later) / 'archive').is_dir()


@pytest.mark.parametrize('owner,other_endpoint', [(2, False), (True, False), (1, True)])
def test_wrong_owner_or_endpoint_cannot_pin_remove_or_read(fixture, owner, other_endpoint):
    f = fixture; record = f.archive(); endpoint = str(uuid.uuid4()) if other_endpoint else f.endpoint
    with pytest.raises(BinlogArchiveError):
        retention.pin(f.jobs, record['job_id'], owner, endpoint, True)
    with pytest.raises(BinlogArchiveError):
        retention.remove(f.jobs, record['job_id'], owner, endpoint, record['job_id'])
    assert (f.jobs.directory(record) / 'archive').is_dir()


@pytest.mark.parametrize('value', [True, -1, 1.2, '30', None])
def test_invalid_policy_is_refused(fixture, value):
    with pytest.raises(BinlogArchiveError):
        fixture.action('retention_review', {'policy': {'retention_days': value, 'keep_latest': 1}})


def test_unreadable_receipt_fails_closed_instead_of_lowering_keep_count(fixture):
    f = fixture; old = f.archive(); f.archive(days=1)
    with f.jobs.store(old['job_id']) as store:
        store.path.write_text('not json', encoding='utf8')
    with pytest.raises(Exception, match='cannot be loaded'):
        f.action('retention_review', {'policy': {'retention_days': 30, 'keep_latest': 1}})


@pytest.mark.parametrize('state', ['active', 'unknown', 'cancelled'])
def test_unconfirmed_native_process_is_never_removed(fixture, state):
    f = fixture; record = f.archive(state=state, stopped=False)
    f.jobs.update(record, started_at=time.time(), worker_identity=[999999999, 0])
    with pytest.raises(BinlogArchiveError, match='termination'):
        f.action('remove_artifact', {'job_id': record['job_id'], 'confirmation': record['job_id']})
    assert not f.jobs.load(record['job_id'], 1, f.endpoint).get('artifact_removal')


def test_directory_replacement_during_interruption_is_refused(fixture, monkeypatch):
    f = fixture; record = f.archive(); original = retention.durable_replace
    monkeypatch.setattr(retention, 'durable_replace', lambda *_args: (_ for _ in ()).throw(OSError('owned fault')))
    with pytest.raises(OSError):
        f.action('remove_artifact', {'job_id': record['job_id'], 'confirmation': record['job_id']})
    path = f.jobs.directory(record) / 'archive'
    path.rename(path.with_name('operator-preserved-original'))
    path.mkdir(); (path / 'unreviewed.txt').write_text('must survive')
    monkeypatch.setattr(retention, 'durable_replace', original)
    with pytest.raises(BinlogArchiveError, match='changed'):
        f.action('removal_reconcile', {'job_id': record['job_id'], 'confirmation': record['job_id']})
    assert (path / 'unreviewed.txt').read_text() == 'must survive'


@pytest.mark.parametrize('change', ['new_file', 'changed_file'])
def test_new_or_changed_entries_survive_interrupted_cleanup(fixture, monkeypatch, change):
    f = fixture; record = f.archive(); original = retention.shutil.rmtree
    monkeypatch.setattr(retention.shutil, 'rmtree', lambda *_args: (_ for _ in ()).throw(OSError('owned fault')))
    with pytest.raises(OSError):
        f.action('remove_artifact', {'job_id': record['job_id'], 'confirmation': record['job_id']})
    monkeypatch.setattr(retention.shutil, 'rmtree', original)
    detached = next(f.jobs.directory(record).glob('.removing-*'))
    selected = detached / ('unreviewed.txt' if change == 'new_file' else 'owned.bin')
    selected.write_bytes(b'unreviewed private data must survive')
    with pytest.raises(BinlogArchiveError, match='entries changed'):
        f.action('removal_reconcile', {'job_id': record['job_id'], 'confirmation': record['job_id']})
    assert selected.read_bytes() == b'unreviewed private data must survive'


def test_symlink_in_archive_index_or_root_is_refused(fixture, tmp_path):
    f = fixture; record = f.archive(); path = f.jobs.directory(record) / 'archive'
    target = tmp_path / 'operator'; target.mkdir(); (target / 'keep').write_text('private')
    retention.shutil.rmtree(path); path.symlink_to(target, target_is_directory=True)
    with pytest.raises(BinlogArchiveError, match='identity'):
        f.action('remove_artifact', {'job_id': record['job_id'], 'confirmation': record['job_id']})
    assert (target / 'keep').read_text() == 'private'


def test_pending_intent_survives_an_independent_process(fixture, monkeypatch, tmp_path):
    import subprocess
    import sys
    f = fixture; record = f.archive(); original = retention.shutil.rmtree
    monkeypatch.setattr(retention.shutil, 'rmtree', lambda *_args: (_ for _ in ()).throw(OSError('owned fault')))
    with pytest.raises(OSError):
        f.action('remove_artifact', {'job_id': record['job_id'], 'confirmation': record['job_id']})
    monkeypatch.setattr(retention.shutil, 'rmtree', original)
    payload = {'path': str(f.jobs.path), 'root': str(f.jobs.root), 'job_id': record['job_id'], 'endpoint': f.endpoint}
    code = ('import config,json,sys; from pgadmin.cdeadmin.workspace.mysql_binlog_jobs import MySQLBinlogJobs; '
            'from pgadmin.cdeadmin.workspace.mysql_archive_retention import remove; '
            'v=json.loads(sys.argv[1]); j=MySQLBinlogJobs(v["path"],v["root"]); '
            'r=remove(j,v["job_id"],1,v["endpoint"],v["job_id"],reconcile=True); '
            'assert r["artifact_removed"] and r["artifact_removal"]["state"]=="completed"')
    # Independent of the caller's working directory and sys.path.
    web = Path(retention.__file__).resolve().parents[3]
    subprocess.run([sys.executable, '-B', '-c', code, json.dumps(payload)], check=True, timeout=30, cwd=web)
    assert f.jobs.get(record['job_id'], 1, f.endpoint)['artifact_removed']


def test_recurring_recovery_baseline_hold_blocks_manual_and_planned_removal_until_released(fixture):
    f=fixture;old=f.archive();f.archive(days=1)
    f.jobs.update(old,recovery_check_holds={'reviewed-policy':True})
    with pytest.raises(BinlogArchiveError,match='recovery-check policies'):
        retention.remove(f.jobs,old['job_id'],1,f.endpoint,old['job_id'])
    with pytest.raises(BinlogArchiveError,match='No retained archives'):
        f.action('retention_review',{'policy':{'retention_days':0,'keep_latest':1}})
    assert (f.jobs.directory(old)/'archive'/'owned.bin').exists()
    f.jobs.update(old,recovery_check_holds={})
    assert retention.remove(f.jobs,old['job_id'],1,f.endpoint,old['job_id'])['artifact_removed']

"""Unattended retention authority, restart, concurrency and no-replay boundaries."""
from types import SimpleNamespace
import threading
import time
import uuid

from flask import Flask
import pytest

from test_mysql_archive_retention import fixture, wait  # noqa: F401
from pgadmin.cdeadmin.operations.store import JsonOperationStore
from pgadmin.cdeadmin.providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
from pgadmin.cdeadmin.workspace import mysql_archive_retention as retention
from pgadmin.cdeadmin.workspace import mysql_retention_schedule as schedule


@pytest.fixture
def scheduled(fixture, tmp_path, monkeypatch):
    f = fixture
    app = Flask(__name__)
    app.config['CDEADMIN_MYSQL_RETENTION_POLL_SECONDS'] = .1
    f.service.operation_bus = SimpleNamespace(store=JsonOperationStore(tmp_path / 'operations.json'))
    from pgadmin.cdeadmin.workspace.mysql_monitoring_host import MySQLMonitoringHost
    monkeypatch.setattr(MySQLMonitoringHost, '_configuration', lambda _server: 'owned-registration')
    hosts = []
    def host():
        result = schedule.ScheduleHost(app, f.service)
        def authority(grant):
            if grant['configuration'] != 'owned-registration' or grant['program'] != schedule.program(f.jobs):
                raise BinlogArchiveError('Owned authority changed')
            return f.jobs
        monkeypatch.setattr(result, 'authority', authority)
        monkeypatch.setattr(result, 'start', lambda: None)
        hosts.append(result)
        return result
    f.host_factory = host; f.host = host(); f.app = app
    def action(operation, request, *, owner=1, endpoint=None):
        return f.host.action(SimpleNamespace(id=9), f.jobs, owner, endpoint or f.endpoint, 'retention_schedule_' + operation, request)
    f.schedule = action
    def grant(anchor):
        review = action('review', {'anchor_job_id': anchor['job_id'],
            'options': {'policy': {'retention_days': 30, 'keep_latest': 1}, 'interval_seconds': 60, 'expires_after_days': 1}})
        value = action('enable', {'job_id': review['job_id'], 'review_digest': review['review_digest'], 'confirmed': True})
        return f.host.jobs.load(value['job_id'], 1, f.endpoint)
    f.grant = grant
    yield f
    for item in hosts: item.close()


def occurrence(f, grant):
    current = f.host.jobs.load(grant['job_id'], 1, f.endpoint)
    return wait(retention.manager(f.service, f.jobs), current['last_occurrence_id'], f.endpoint)


def test_independent_occurrences_include_later_archives_only_for_the_frozen_native_identity(scheduled):
    f = scheduled; old = f.archive(); latest = f.archive(days=1); pin = f.archive(days=101)
    other = f.archive(days=200, native={**f.source, 'active_role': '`different-role`'})
    f.action('pin', {'job_id': pin['job_id'], 'pinned': True})
    grant = f.grant(latest)
    f.host.tick(grant['job_id']); first = occurrence(f, grant)
    assert first['state'] == 'completed' and first['result']['removed_job_ids'] == [old['job_id']]
    later = f.archive(days=150)
    assert f.host.tick(grant['job_id']).get('last_occurrence_id') == first['job_id']
    f.host.close(); f.host = f.host_factory()
    f.host.jobs.update(grant, next_scan_at=0)
    f.host.tick(grant['job_id']); second = occurrence(f, grant)
    assert second['state'] == 'completed' and second['job_id'] != first['job_id']
    assert second['result']['removed_job_ids'] == [later['job_id']]
    for record in (latest, pin, other): assert (f.jobs.directory(record) / 'archive').exists()
    assert retention.manager(f.service, f.jobs).get(first['job_id'], 1, f.endpoint) == first


def test_lost_native_removal_ack_suspends_future_scans_even_after_explicit_reconciliation(scheduled, monkeypatch):
    f = scheduled; old = f.archive(); latest = f.archive(days=1); grant = f.grant(latest)
    original = retention.shutil.rmtree
    def fault(path):
        original(path)
        raise OSError('Owned removal acknowledgement loss')
    with monkeypatch.context() as context:
        context.setattr(retention.shutil, 'rmtree', fault)
        f.host.tick(grant['job_id']); receipt = occurrence(f, grant)
    assert receipt['state'] == 'interrupted'
    assert f.host.tick(grant['job_id'], force=True)['state'] == 'attention_required'
    later = f.archive(days=200)
    reconciled = f.action('retention_reconcile', {'job_id': receipt['job_id'], 'confirmed': True})
    assert reconciled['state'] == 'reconciled' and reconciled['result']['removed_job_ids'] == [old['job_id']]
    assert f.host.tick(grant['job_id'], force=True)['state'] == 'attention_required'
    assert (f.jobs.directory(later) / 'archive').exists()
    fresh = f.grant(latest); f.host.tick(fresh['job_id'])
    assert occurrence(f, fresh)['result']['removed_job_ids'] == [later['job_id']]


def test_revocation_after_first_removal_preserves_unattempted_files(scheduled, monkeypatch):
    f = scheduled; oldest = f.archive(days=200); other = f.archive(days=100); latest = f.archive(days=1)
    grant = f.grant(latest); jobs = retention.manager(f.service, f.jobs); update = jobs.update
    def revoke(record, **values):
        result = update(record, **values)
        progress = values.get('progress', {})
        if progress.get('removed_job_ids') and progress.get('current_job_id') is None:
            f.schedule('disable', {'job_id': grant['job_id'], 'confirmed': True})
        return result
    monkeypatch.setattr(jobs, 'update', revoke)
    f.host.tick(grant['job_id']); receipt = occurrence(f, grant)
    assert receipt['state'] == 'interrupted' and not (f.jobs.directory(oldest) / 'archive').exists()
    assert (f.jobs.directory(other) / 'archive').exists() and (f.jobs.directory(latest) / 'archive').exists()
    assert f.host.tick(grant['job_id'], force=True)['state'] == 'disabled'


def test_concurrent_manual_removal_cannot_lower_the_scheduled_retained_floor(scheduled, monkeypatch):
    f = scheduled; oldest = f.archive(days=200); middle = f.archive(days=100); latest = f.archive(days=1); grant = f.grant(latest)
    require = f.host.require; removed = False
    def concurrent(grant, occurrence=None):
        nonlocal removed
        value = require(grant, occurrence)
        if occurrence and not removed:
            removed = True
            f.action('remove_artifact', {'job_id': latest['job_id'], 'confirmation': latest['job_id']})
        return value
    monkeypatch.setattr(f.host, 'require', concurrent)
    f.host.tick(grant['job_id']); receipt = occurrence(f, grant)
    assert receipt['state'] == 'interrupted'
    assert not (f.jobs.directory(oldest) / 'archive').exists() and (f.jobs.directory(middle) / 'archive').exists()


@pytest.mark.parametrize('fault', ['expired', 'registration', 'program', 'review', 'preparing', 'unresolved'])
def test_changed_or_interrupted_authority_never_starts_a_new_occurrence(scheduled, fault):
    f = scheduled; old = f.archive(); latest = f.archive(days=1); grant = f.grant(latest)
    if fault == 'expired': f.host.jobs.update(grant, valid_until=0)
    elif fault == 'registration': f.host.jobs.update(grant, configuration='changed')
    elif fault == 'program': f.host.jobs.update(grant, program={**grant['program'], 'scheduler_sha256': 'changed'})
    elif fault == 'review': f.host.jobs.update(grant, review_digest='changed')
    elif fault == 'preparing': f.host.jobs.update(grant, state='preparing')
    else:
        jobs = retention.manager(f.service, f.jobs)
        plan = retention.prepare(jobs, f.jobs, 1, f.endpoint, grant['options']['policy'], native_source=grant['source'], scheduled_policy_id=grant['job_id'])
        jobs.update(jobs.load(plan['job_id'], 1, f.endpoint), state='active', worker_identity=[999999999, 0])
        f.host.jobs.update(grant, last_occurrence_id=plan['job_id'])
    assert f.host.tick(grant['job_id'], force=True)['state'] == 'attention_required'
    assert (f.jobs.directory(old) / 'archive').exists()
    count = retention.manager(f.service, f.jobs).list(1, f.endpoint)['total']
    f.host.tick(grant['job_id'], force=True)
    assert retention.manager(f.service, f.jobs).list(1, f.endpoint)['total'] == count


def test_two_hosts_cannot_prepare_the_same_due_policy_concurrently(scheduled, monkeypatch):
    f = scheduled; f.archive(); latest = f.archive(days=1); grant = f.grant(latest); other = f.host_factory()
    original = retention.prepare; entered = threading.Event(); release = threading.Event(); errors = []
    def pause(*args, **kwargs):
        entered.set(); assert release.wait(5)
        return original(*args, **kwargs)
    monkeypatch.setattr(retention, 'prepare', pause)
    def first():
        try: f.host.tick(grant['job_id'])
        except BaseException as error: errors.append(error)
    thread = threading.Thread(target=first); thread.start(); assert entered.wait(5)
    try: assert other.tick(grant['job_id'], force=True)['state'] == 'preparing'
    finally: release.set(); thread.join(timeout=5)
    assert not thread.is_alive() and not errors
    assert occurrence(f, grant)['state'] == 'completed'
    assert retention.manager(f.service, f.jobs).list(1, f.endpoint)['total'] == 1


@pytest.mark.parametrize('fault', ['owner', 'endpoint', 'confirmation', 'digest', 'extra'])
def test_policy_enable_and_observation_require_the_exact_owner_endpoint_and_review(scheduled, fault):
    f = scheduled; anchor = f.archive()
    plan = f.schedule('review', {'anchor_job_id': anchor['job_id'], 'options': {
        'policy': {'retention_days': 30, 'keep_latest': 1}, 'interval_seconds': 60, 'expires_after_days': 1}})
    request = {'job_id': plan['job_id'], 'review_digest': plan['review_digest'], 'confirmed': True}
    if fault == 'confirmation': request['confirmed'] = False
    if fault == 'digest': request['review_digest'] = 'changed'
    if fault == 'extra': request['unreviewed_option'] = True
    with pytest.raises(BinlogArchiveError):
        f.schedule('enable', request, owner=2 if fault == 'owner' else 1, endpoint=str(uuid.uuid4()) if fault == 'endpoint' else f.endpoint)
    assert f.host.jobs.get(plan['job_id'], 1, f.endpoint)['state'] == 'reviewed'
    assert (f.jobs.directory(anchor) / 'archive').exists()


def test_orphan_scheduled_reviews_cannot_bypass_delegation_with_manual_start(scheduled):
    f = scheduled; f.archive(); latest = f.archive(days=1); grant = f.grant(latest)
    plan = retention.prepare(retention.manager(f.service, f.jobs), f.jobs, 1, f.endpoint, grant['options']['policy'], scheduled_policy_id=grant['job_id'])
    with pytest.raises(BinlogArchiveError, match='delegated policy'):
        f.action('retention_start', {'job_id': plan['job_id'], 'review_digest': plan['review_digest'], 'confirmed': True})


@pytest.mark.parametrize('field,value', [('interval_seconds', True), ('interval_seconds', 0), ('interval_seconds', 1.5), ('expires_after_days', 0), ('expires_after_days', 366)])
def test_invalid_delegation_limits_are_refused(field, value):
    options = {'policy': {'retention_days': 30, 'keep_latest': 1}, 'interval_seconds': 60, 'expires_after_days': 1}
    options[field] = value
    with pytest.raises(BinlogArchiveError): schedule.selected(options)

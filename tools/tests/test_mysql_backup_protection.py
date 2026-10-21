"""Managed backup holds, restart, concurrent removal and native reply boundaries."""
from copy import deepcopy
import hashlib
import threading
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_backup_events as events
from pgadmin.cdeadmin.workspace.mysql_backup_protection import Registry
from pgadmin.cdeadmin.workspace import mysql_archive_retention as retention
from test_mysql_archive_retention import fixture, wait


def completed(ticket, source, database='native'):
    return ticket.completed({'origin': 'dumpSchemas', 'schemas': [database], 'serverVersion': source.get('version'),
        'consistent': True, 'source': {'sysvars': {'server_uuid': source['server_uuid']},
            'binlog': {'file': 'native.000001', 'position': 9007199254740993, 'gtidExecuted': 'native:1-9'}}},
        {'end': 'native completion'}, {'artifact_manifest': [], 'artifact_total_bytes': 0})


def test_a_new_pending_backup_blocks_an_already_reviewed_retention_and_survives_restart(fixture, tmp_path):
    f = fixture; old = f.archive(); f.archive(days=1)
    review = f.action('retention_review', {'policy': {'retention_days': 30, 'keep_latest': 1}})
    registry = f.jobs.backup_protection = Registry(tmp_path / 'backup-protection')
    ticket = registry.scoped(1, f.endpoint).begin(f.source, 'native', '/owned/dump', {})
    result = f.action('retention_start', {key: review[key] for key in ('job_id', 'review_digest')} | {'confirmed': True})
    jobs = retention.manager(f.service, f.jobs)
    result = wait(jobs, result['job_id'], f.endpoint)
    assert result['state'] == 'interrupted' and not f.jobs.load(old['job_id'], 1, f.endpoint).get('artifact_removal')
    assert (f.jobs.directory(old) / 'archive/owned.bin').is_file()
    registry = f.jobs.backup_protection = Registry(registry.root)
    assert registry.list(1, f.endpoint)['backups'][0]['backup_id'] == ticket.backup_id
    with pytest.raises(retention.BinlogArchiveError, match='Managed backup protection'):
        f.action('remove_artifact', {'job_id': old['job_id'], 'confirmation': old['job_id']})
    rows, excluded, _cutoff, total = retention.candidates(f.jobs, 1, f.endpoint, {'retention_days': 0, 'keep_latest': 1})
    assert not rows and total == 0 and excluded['managed_backup_protected'] == 2


def test_confirmed_source_holds_and_unknown_holds_have_separate_scope(tmp_path):
    registry = Registry(tmp_path); endpoint = str(uuid.uuid4()); source = {'server_uuid': str(uuid.uuid4()), 'version': '9.7.0'}
    ticket = registry.scoped(1, endpoint).begin(source, 'native', '/owned/dump', {})
    other = {'source': {'server_uuid': str(uuid.uuid4())}}
    assert registry.protected(other, registry.protections(1, endpoint))
    result = completed(ticket, source)
    assert result['native_boundary']['position'] == '9007199254740993'
    assert not registry.protected(other, registry.protections(1, endpoint))
    assert registry.protected({'source': source}, registry.protections(1, endpoint))
    assert registry.list(2, endpoint)['backups'] == []
    assert registry.list(1, str(uuid.uuid4()))['backups'] == []


def test_retirement_is_reviewed_scoped_stale_checked_and_does_not_resurrect_on_late_native_reply(tmp_path):
    registry = Registry(tmp_path); endpoint = str(uuid.uuid4()); source = {'server_uuid': str(uuid.uuid4()), 'version': '9.7.0'}
    ticket = registry.scoped(1, endpoint).begin(source, 'native', '/owned/dump', {})
    review = registry.review_retire(1, endpoint, ticket.backup_id)
    request = {key: review[key] for key in ('review_id', 'review_digest')} | {'confirmed': True}
    for owner, scope in ((2, endpoint), (1, str(uuid.uuid4()))):
        with pytest.raises(retention.BinlogArchiveError): registry.retire(owner, scope, request)
    completed(ticket, source)
    with pytest.raises(retention.BinlogArchiveError, match='changed'): registry.retire(1, endpoint, request)
    review = registry.review_retire(1, endpoint, ticket.backup_id)
    request = {key: review[key] for key in ('review_id', 'review_digest')} | {'confirmed': True}
    with pytest.raises(retention.BinlogArchiveError): registry.retire(1, endpoint, {**request, 'confirmed': False})
    result = registry.retire(1, endpoint, request)
    assert result['state'] == 'retired' and result['backup_files_removed'] is False
    assert registry.retire(1, endpoint, request) == result
    assert completed(ticket, source)['native_dump_acknowledged_after_retirement']
    assert registry.protections(1, endpoint) == []


def test_native_backup_intent_cannot_enter_during_an_accepted_file_removal(tmp_path):
    registry = Registry(tmp_path); other = Registry(tmp_path); endpoint = str(uuid.uuid4())
    source = {'server_uuid': str(uuid.uuid4())}; requested = threading.Event(); admitted = threading.Event(); errors = []
    def begin():
        requested.set()
        try: other.scoped(1, endpoint).begin(source, 'native', '/owned/dump', {}); admitted.set()
        except BaseException as error: errors.append(error)
    with registry.guard(1, endpoint, {'source': source}):
        worker = threading.Thread(target=begin); worker.start()
        assert requested.wait(5) and not admitted.wait(.05)
    worker.join(5)
    assert not worker.is_alive() and admitted.is_set() and errors == []


def test_missing_tool_reply_keeps_the_original_error_and_a_durable_hold_without_source_session_io(tmp_path, monkeypatch):
    registry = Registry(tmp_path); endpoint = str(uuid.uuid4()); source = {'server_uuid': str(uuid.uuid4()), 'version': '9.7.0'}
    handle = object(); client = SimpleNamespace(_connect=Mock(return_value=handle), _forget_and_close=Mock())
    monkeypatch.setattr(events, 'rows', lambda connection, _sql: [deepcopy(source)] if connection is handle else [])
    with events.observe(registry.scoped(1, endpoint)):
        with pytest.raises(OSError, match='Owned missing tool reply'):
            with events.track(client, {'database': 'native'}, tmp_path / 'dump', {}) as ticket:
                assert registry.list(1, endpoint)['backups'][0]['backup_id'] == ticket.backup_id
                raise OSError('Owned missing tool reply')
    assert registry.list(1, endpoint)['backups'][0]['state'] == 'unconfirmed_native_reply'
    client._forget_and_close.assert_called_once_with(handle)
    client._connect.reset_mock()
    with events.track(client, {}, tmp_path / 'unmanaged', {}) as ticket: assert ticket is None
    client._connect.assert_not_called()


def test_native_dump_acknowledgement_survives_changed_metadata_and_still_protects_archives(tmp_path):
    registry = Registry(tmp_path / 'registry'); endpoint = str(uuid.uuid4()); source = {'server_uuid': str(uuid.uuid4()), 'version': '9.7.0'}
    ticket = registry.scoped(1, endpoint).begin(source, 'native', str(tmp_path), {})
    files = []
    for name in ('@.json', '@.done.json'):
        path = tmp_path / name; path.write_text('{}')
        files.append({'path': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    (tmp_path / '@.json').write_text('{"changed":"after native manifest"}')
    native = {'artifact_path': str(tmp_path), 'artifact_manifest': files, 'mysql_shell_completed': True}
    result = events.completed(ticket, native)
    assert result['mysql_shell_completed'] and result['archive_backup_protection']['native_backup_acknowledgement_unchanged']
    record = registry.list(1, endpoint)['backups'][0]
    assert record['state'] == 'protection_unconfirmed' and record['native_dump_completion_acknowledged']
    assert registry.protected({'source': source}, registry.protections(1, endpoint))

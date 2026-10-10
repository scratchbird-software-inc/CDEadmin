"""Local native qualification must clean up failed startup and checks."""

from unittest.mock import Mock

import firebird.driver as native
import pytest

from tools import cdeadmin_firebird_local_fixture as fixture


@pytest.mark.parametrize('failure_stage', ['startup', 'callback', None])
def test_owned_fixture_cleanup_and_environment_restore(
        tmp_path, monkeypatch, failure_stage):
    source = tmp_path / 'source'
    for name in ('bin/firebird', 'bin/isql', 'security5.fdb',
                 'lib/libfbclient.so.5.0.4'):
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('owned test runtime')
    monkeypatch.setenv('FIREBIRD', 'previous-runtime')
    monkeypatch.setenv('FIREBIRD_LOCK', 'previous-lock')
    monkeypatch.setenv('CDEADMIN_FIREBIRD_CLIENT_LIBRARY', 'previous-library')
    monkeypatch.setattr(fixture, '_configure_client_library', Mock())
    monkeypatch.setattr(fixture.platform, 'platform', lambda: 'owned-linux')
    staged = []

    def stage(_source, target):
        target.mkdir()
        staged.append(target)

    monkeypatch.setattr(fixture, '_stage_runtime', stage)
    initialize = Mock()
    if failure_stage == 'startup':
        initialize.side_effect = RuntimeError('private credential marker')
    monkeypatch.setattr(fixture, '_initialize_security', initialize)
    monkeypatch.setattr(fixture, '_free_port', lambda: 12345)
    monkeypatch.setattr(fixture, '_wait_for_server', Mock())
    process = Mock()
    process.poll.return_value = 0
    launch = Mock(return_value=process)
    monkeypatch.setattr(fixture.subprocess, 'Popen', launch)
    monkeypatch.setattr(fixture, '_route_arguments', lambda *_: {})
    admin = Mock()
    admin.__enter__ = Mock(return_value=admin)
    admin.__exit__ = Mock(return_value=False)
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.fetchone.return_value = ('5.0.4',)
    admin.cursor.return_value = cursor
    monkeypatch.setattr(native, 'create_database', Mock(return_value=admin))
    authentication = Mock()
    monkeypatch.setattr(fixture, 'authenticate', authentication)
    monkeypatch.setattr(fixture, 'reject_password', Mock())
    callback = Mock()
    if failure_stage == 'callback':
        callback.side_effect = RuntimeError('private credential marker')
    evidence = tmp_path / 'evidence'
    result = fixture.run_local(source, evidence, callback)
    assert result['complete'] == (failure_stage is None)
    assert result['owned_state_removed']
    assert result['owned_process_stopped']
    assert result['source_runtime_unchanged']
    assert staged and not staged[0].exists()
    assert fixture.os.environ['FIREBIRD'] == 'previous-runtime'
    assert fixture.os.environ['FIREBIRD_LOCK'] == 'previous-lock'
    assert fixture.os.environ['CDEADMIN_FIREBIRD_CLIENT_LIBRARY'] == (
        'previous-library')
    summary = (evidence / 'summary.json').read_text()
    assert 'private credential marker' not in summary
    if failure_stage == 'startup':
        launch.assert_not_called()
        callback.assert_not_called()
    else:
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=10)
        callback.assert_called_once()
    if failure_stage:
        authentication.assert_not_called()
    else:
        authentication.assert_called_once()


def test_incomplete_runtime_is_rejected_before_evidence_or_process(
        tmp_path, monkeypatch):
    launch = Mock()
    monkeypatch.setattr(fixture.subprocess, 'Popen', launch)
    with pytest.raises(ValueError, match='complete local Firebird'):
        fixture.run_local(tmp_path / 'missing', tmp_path / 'evidence', Mock())
    launch.assert_not_called()
    assert not (tmp_path / 'evidence').exists()

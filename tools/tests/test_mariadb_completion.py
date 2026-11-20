"""Automatic completion must not send a command to the user's session."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.mysql_family import mariadb_completion as subject
from pgadmin.cdeadmin.providers import native_editor
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def harness(monkeypatch):
    source = Mock(connection_id=7)
    peer = Mock(connection_id=8)
    client = SimpleNamespace(_executions=SimpleNamespace(sessions=Mock()),
        _completion_identities={id(source): (source, ('server', 'owner', '12.2.2', 7))},
        _session_requests={id(source): {'route': {'host': 'owned', 'pool_size': 1}}},
        _connect=Mock(return_value=peer),
        _close_idle_session=Mock(return_value={'connection_released': True}))
    peer.cursor.return_value.fetchone.return_value = ('server', 'owner', '12.2.2', 8)
    data = {'context': {'version': '12.2.2', 'default_schema': 'initial',
        'sql_mode': 'ANSI_QUOTES', 'character_set_client': 'utf8mb4', 'active_role': 'peer'},
        'resources': [], 'observations': [], 'visible_resource_count': 0,
        'complete': True, 'truncated': False}
    metadata = Mock(side_effect=lambda *args: deepcopy(data))
    monkeypatch.setattr(native_editor, 'metadata', metadata)
    return client, source, peer, metadata


def test_private_catalog_has_no_source_commands_or_false_source_context(monkeypatch):
    client, source, peer, metadata = harness(monkeypatch)
    result = subject.complete(client, source)
    source.cursor.assert_not_called()
    source.ping.assert_not_called()
    source.rollback.assert_not_called()
    source.commit.assert_not_called()
    metadata.assert_called_once_with(peer, 'mariadb')
    assert not result['complete'] and result['original_diagnostics_preserved']
    assert result['original_session_commands_sent'] == 0
    assert not result['original_session_catalog_binding_validated']
    assert 'sql_mode' not in result['context'] and 'default_schema' not in result['context']
    assert result['context']['metadata_peer_context']['sql_mode'] == 'ANSI_QUOTES'
    assert 'pool_size' not in client._connect.call_args.args[0]['route']
    client._close_idle_session.assert_called_once_with(peer)


@pytest.mark.parametrize('failure', ['identity', 'principal', 'version', 'metadata', 'release', 'connect', 'source'])
def test_failures_preserve_source_diagnostics_and_never_substitute_source_queries(monkeypatch, failure):
    client, source, peer, metadata = harness(monkeypatch)
    if failure in {'identity', 'principal', 'version'}:
        row = ['server', 'owner', '12.2.2', 8]
        row[{'identity': 0, 'principal': 1, 'version': 2}[failure]] = 'changed'
        peer.cursor.return_value.fetchone.return_value = tuple(row)
    elif failure == 'metadata':
        metadata.side_effect = RuntimeError('private source-bearing failure')
    elif failure == 'release':
        client._close_idle_session.return_value = {'connection_released': False}
    elif failure == 'connect':
        client._connect.side_effect = RuntimeError('private password')
    else:
        source.connection_id = 9
    with pytest.raises(RelationalClientError) as error:
        subject.complete(client, source)
    assert error.value.original_diagnostics_preserved
    assert error.value.original_session_commands_sent == 0
    assert 'password' not in str(error.value) and 'source-bearing' not in str(error.value)
    source.cursor.assert_not_called()
    source.rollback.assert_not_called()
    if failure == 'source':
        client._connect.assert_not_called()
    elif failure != 'connect':
        client._close_idle_session.assert_called_once_with(peer)


def test_aliased_source_handle_is_never_queried_or_closed(monkeypatch):
    client, source, peer, metadata = harness(monkeypatch)
    client._connect.return_value = source
    with pytest.raises(RelationalClientError):
        subject.complete(client, source)
    source.cursor.assert_not_called()
    client._close_idle_session.assert_not_called()
    metadata.assert_not_called()


def test_killed_peer_marks_peer_uncertain_before_release_and_tracks_snapshot_invalidation(monkeypatch):
    client, source, peer, metadata = harness(monkeypatch)
    client._uncertain_sessions = set()
    client._source_revisions = {id(source): 3}
    client._editor_context_snapshots = {id(source): 3}
    ok = subject.complete(client, source)
    assert ok['context']['source_work_revision'] == 3
    assert ok['context']['explicit_context_snapshot_valid'] is True

    client._source_revisions[id(source)] = 4
    client._editor_context_snapshots.pop(id(source), None)
    stale = subject.complete(client, source)
    assert stale['context']['source_work_revision'] == 4
    assert stale['context']['explicit_context_snapshot_valid'] is False

    metadata.side_effect = RuntimeError('peer killed')
    with pytest.raises(RelationalClientError):
        subject.complete(client, source)
    assert id(peer) in client._uncertain_sessions
    assert id(source) not in client._uncertain_sessions
    source.cursor.assert_not_called()

"""The native gate collects all case failures and releases only its fixture."""

from unittest.mock import Mock

import pytest

from tools import cdeadmin_firebird_native_opening_gate as gate


@pytest.mark.parametrize('failure', [
    None, 'native_failover', 'identity_admission', 'concurrent_open',
    'process_loss', 'wait_ready', 'address_identity', 'failed_detach'])
def test_failure_collection_and_owned_cleanup(monkeypatch, failure):
    container = 'a' * 64
    monkeypatch.setattr(gate, '_configure_client_library', Mock())
    monkeypatch.setattr(gate, 'docker', Mock(return_value=container.encode()))
    monkeypatch.setattr(gate, 'published_port', Mock(return_value=53050))
    cleanup = Mock()
    monkeypatch.setattr(gate, 'remove_owned', cleanup)
    stages = {}
    for name in ('native_failover', 'identity_admission', 'concurrent_open',
                 'process_loss', 'wait_ready', 'address_identity',
                 'failed_detach'):
        error = (RuntimeError('owned-fixture-failure')
                 if failure == name else None)
        stages[name] = Mock(side_effect=error,
                            return_value={'observed': True})
        monkeypatch.setattr(gate, name, stages[name])
    if failure == 'wait_ready':
        with pytest.raises(RuntimeError, match='owned-fixture-failure'):
            gate.run('owned-image')
    else:
        result = gate.run('owned-image')
        assert result['complete'] is (failure is None)
        assert len(result['failures']) == (0 if failure is None else 1)
        for name, stage in stages.items():
            stage.assert_called_once()
        assert result['owned_container_removed']
    cleanup.assert_called_once_with(container)


@pytest.mark.parametrize('selected', [
    [], ['unknown'], ['concurrent-open', 'concurrent-open'],
])
def test_invalid_selection_never_starts_container(monkeypatch, selected):
    docker = Mock()
    monkeypatch.setattr(gate, 'docker', docker)
    with pytest.raises(ValueError, match='unique known'):
        gate.run('owned-image', selected)
    docker.assert_not_called()


def test_selected_feature_reports_only_executed_cases(monkeypatch):
    monkeypatch.setattr(gate, '_configure_client_library', Mock())
    monkeypatch.setattr(gate, 'docker', Mock(return_value=b'a' * 64))
    monkeypatch.setattr(gate, 'published_port', Mock(return_value=53050))
    monkeypatch.setattr(gate, 'wait_ready', Mock())
    cleanup = Mock()
    monkeypatch.setattr(gate, 'remove_owned', cleanup)
    stages = {}
    for name in gate.CASES:
        stages[name] = Mock(return_value={'observed': True})
        monkeypatch.setattr(gate, name.replace('-', '_'), stages[name])
    selected = ('identity-admission', 'concurrent-open', 'process-loss')
    result = gate.run('owned-image', selected)
    assert result['complete']
    assert result['selected_cases'] == list(selected)
    assert set(result['cases']) == set(selected)
    for name, stage in stages.items():
        assert stage.call_count == (1 if name in selected else 0)
    cleanup.assert_called_once_with('a' * 64)


def test_native_fixture_uses_registry_declared_adapter(monkeypatch):
    monkeypatch.setattr(
        'pgadmin.cdeadmin.providers.firebird.provider.'
        '_configure_client_library', Mock())
    provider, client = gate.provider_for('owned-test-secret')
    try:
        assert provider.context.target_adapter_id == 'firebird-wire-client'
        assert type(provider.permissions).__name__ == 'PermissionGuard'
        provider.permissions.require('network')
        with pytest.raises(AssertionError):
            provider.permissions.acquire_secret('foreign', 'foreign')
    finally:
        client.close()

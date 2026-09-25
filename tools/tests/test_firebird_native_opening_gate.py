"""The native gate collects all case failures and releases only its fixture."""

from unittest.mock import Mock

import pytest

from tools import cdeadmin_firebird_native_opening_gate as gate


@pytest.mark.parametrize('failure', [
    None, 'native_failover', 'identity_admission', 'concurrent_open',
    'process_loss', 'wait_ready', 'address_identity'])
def test_failure_collection_and_owned_cleanup(monkeypatch, failure):
    container = 'a' * 64
    monkeypatch.setattr(gate, '_configure_client_library', Mock())
    monkeypatch.setattr(gate, 'docker', Mock(return_value=container.encode()))
    monkeypatch.setattr(gate, 'published_port', Mock(return_value=53050))
    cleanup = Mock()
    monkeypatch.setattr(gate, 'remove_owned', cleanup)
    stages = {}
    for name in ('native_failover', 'identity_admission', 'concurrent_open',
                 'process_loss', 'wait_ready', 'address_identity'):
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

"""Password principal changes must not reuse another identity's credential."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.endpoints.service import (
    EndpointService, EndpointRegistrationError,
)


@pytest.mark.parametrize('alternate,previous', [
    ('other', None), (None, 'other'), ('other', 'other'),
])
def test_firebird_principal_change_requires_explicit_password(
        alternate, previous):
    registry = SimpleNamespace(resolve=Mock())
    service = EndpointService(registry, SimpleNamespace(
        secrets=SimpleNamespace(register_resolver=Mock())))
    endpoint = SimpleNamespace(id='owned', provider_version='0.1.0',
                               profile_id='firebird-native')
    if previous:
        service._principal_overrides[endpoint.id] = previous
    server = SimpleNamespace(endpoint_profile=endpoint)
    with pytest.raises(EndpointRegistrationError, match='password explicitly'):
        service.verify_server(server, connect_as=alternate)
    registry.resolve.assert_not_called()
    assert service._principal_overrides.get(endpoint.id) == previous


@pytest.mark.parametrize('busy', [False, True])
def test_disconnect_erases_transient_identity_only_after_release(busy):
    from contextlib import contextmanager
    from pgadmin.cdeadmin.core.registry import ProviderReleaseError

    class Registry:
        @contextmanager
        def endpoint_configuration_change(self, endpoint_id):
            assert endpoint_id == 'owned'
            if busy:
                raise ProviderReleaseError('active owned session')
            yield

    service = EndpointService(Registry(), SimpleNamespace(
        secrets=SimpleNamespace(register_resolver=Mock())))
    endpoint = SimpleNamespace(id='owned', secret_references=[
        SimpleNamespace(secret_reference='server:1:password')])
    server = SimpleNamespace(endpoint_profile=endpoint,
                             username='default', password='encrypted')
    service._record_verification = Mock()
    service._principal_overrides['owned'] = 'alternate'
    service.resolver.remember('server:1:password', 'owned-ephemeral')
    buffer = service.resolver._session['server:1:password']
    if busy:
        with pytest.raises(EndpointRegistrationError, match='active owned'):
            service.disconnect_server(server)
        assert bytes(buffer) == b'owned-ephemeral'
        assert service._principal_overrides['owned'] == 'alternate'
        service._record_verification.assert_not_called()
    else:
        service.disconnect_server(server)
        assert not service.resolver._session
        assert not service._principal_overrides
        assert not any(buffer)
        service._record_verification.assert_called_once_with(
            endpoint, 'unverified')
    assert server.username == 'default' and server.password == 'encrypted'


def test_password_gate_collects_plugin_failures_and_removes_owned_fixture(
        monkeypatch, tmp_path):
    from unittest.mock import MagicMock
    from tools import cdeadmin_firebird_password_gate as gate

    monkeypatch.setattr(gate, '_configure_client_library', Mock())
    monkeypatch.setattr(gate, 'docker', Mock(return_value=b'a' * 64))
    monkeypatch.setattr(gate, 'published_port', Mock(return_value=53050))
    monkeypatch.setattr(gate, 'wait_ready', Mock())
    monkeypatch.setattr(gate, '_route_arguments', Mock(return_value={}))
    monkeypatch.setattr('firebird.driver.connect', MagicMock())
    cleanup = Mock()
    monkeypatch.setattr(gate, 'remove_owned', cleanup)
    checked = []

    def authenticate(_native, _route, _user, _password, plugin):
        checked.append(plugin)
        if plugin == 'Srp':
            raise RuntimeError('must not export private exception text')

    monkeypatch.setattr(gate, 'authenticate', authenticate)
    monkeypatch.setattr(gate, 'reject_password', Mock())
    result = gate.run(tmp_path / 'evidence')
    assert not result['complete'] and len(result['cases']) == 5
    assert result['failures'][0]['plugin'] == 'Srp'
    assert set(checked) == set(gate.PLUGINS)
    assert 'private exception text' not in str(result)
    cleanup.assert_called_once_with('a' * 64)


@pytest.mark.parametrize('selected', [[], ['Win_Sspi'], ['Srp', 'Srp']])
def test_password_gate_rejects_invalid_selection_before_start(
        monkeypatch, tmp_path, selected):
    from tools import cdeadmin_firebird_password_gate as gate
    docker = Mock()
    monkeypatch.setattr(gate, 'docker', docker)
    with pytest.raises(ValueError, match='unique supported'):
        gate.run(tmp_path / 'invalid', selected_plugins=selected)
    docker.assert_not_called()
    assert not (tmp_path / 'invalid').exists()


@pytest.mark.parametrize('ready,owner', [
    (False, False), (False, True), (True, False), (True, True),
])
def test_disconnect_menu_matches_endpoint_owner_and_verification(ready, owner):
    from tools.tests.test_cdeadmin_context_menu import profile
    from pgadmin.cdeadmin.context_menu import endpoint_context_actions

    actions = endpoint_context_actions(
        profile('firebird'), 'verified' if ready else 'unverified',
        can_manage=owner)
    action = next(item for item in actions
                  if item['handler'] == 'disconnect_endpoint')
    assert action['enabled'] is (ready and owner)

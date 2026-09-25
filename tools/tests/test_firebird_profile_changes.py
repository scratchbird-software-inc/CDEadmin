"""Firebird connection edits cannot invalidate owned database sessions."""

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from contextlib import nullcontext
import threading

import pytest

from tools.tests.test_firebird_async_queries import rig  # noqa: F401
from tools.tests.test_firebird_async_queries import service_handle
from pgadmin.cdeadmin.providers.firebird.query_client import (
    FirebirdQueryClient,
)
from tools.tests.test_cdeadmin_actual_engine_pilots import context
from pgadmin.cdeadmin.core import ProviderRegistry, ProviderReleaseError
from pgadmin.cdeadmin.endpoints import (
    EndpointService, EndpointRegistrationError,
)
from pgadmin.cdeadmin.providers.firebird.provider import (
    FirebirdProvider, PROFILE,
)
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.endpoints.service import _credential_change


def registered(client):
    registry = ProviderRegistry()
    path = (Path(__file__).resolve().parents[2] / 'web/pgadmin/cdeadmin/'
            'providers/firebird/provider_manifest.json')
    with patch('pgadmin.cdeadmin.providers.firebird.provider.create_provider',
               side_effect=lambda context, permissions: FirebirdProvider(
                   context, permissions, client)):
        registration = registry.register_package(
            json.loads(path.read_text()),
            'pgadmin.cdeadmin.providers.firebird.provider')
        binding = registry.resolve(replace(
            context(PROFILE),
            effective_permissions=frozenset(registration.permission_grants),
            target_adapter_id=registration.manifest[
                'composition']['target_adapter_ids'][0]))
    return registry, registration, binding


@pytest.mark.parametrize('method,args', [
    ('attach_database', ({},)),
    ('update_database_target', ('target', {})),
    ('activate_database', ('target', {})),
    ('disconnect_database', ()),
    ('delete_database_target', ('target', {})),
    ('retain_created_database', ({},)),
    ('retain_registered_database', ({},)),
    ('create_route', ({},)),
    ('update_route', ('route', {})),
    ('update_endpoint_profile', ({},)),
    ('validate_endpoint_removal', ({},)),
    ('delete_route', ('route',)),
    ('verify_server', ('new-password',)),
    ('verify_server', (None, 'alternate-user')),
    ('forget_server_credentials', ()),
])
def test_connection_mutations_reject_before_changing_state(rig, method, args):
    registry, registration, binding = registered(rig.client)
    service = EndpointService(registry, Mock())
    endpoint = SimpleNamespace(
        id=binding.context.endpoint_id, profile_id=PROFILE.profile_id,
        provider_version='0.1.0', profile_generation='original')
    server = SimpleNamespace(endpoint_profile=endpoint)
    before = list(rig.handle.mock_calls)
    with pytest.raises(EndpointRegistrationError, match='open sessions'):
        getattr(service, method)(server, *args)
    assert endpoint.profile_generation == 'original'
    assert rig.handle.mock_calls == before
    assert registry.resolve(binding.context) is binding
    assert len(registration.bindings) == 1


def test_confirmed_profile_release_invalidates_previously_acquired_client(rig):
    registry, registration, binding = registered(rig.client)
    rig.client.close_session(rig.handle)
    with registry.endpoint_configuration_change(binding.context.endpoint_id):
        assert not registration.bindings
        with pytest.raises(RelationalClientError, match='closed'):
            rig.client.open_session({'route': {}})


def test_profile_change_does_not_touch_another_endpoint(rig):
    registry, registration, binding = registered(rig.client)
    other_id = context(PROFILE, 'other').endpoint_id
    with registry.endpoint_configuration_change(other_id):
        assert list(registration.bindings.values()) == [binding]
        assert rig.handle in rig.client._connections


def test_opening_attachment_prevents_profile_release(rig):
    registry, registration, binding = registered(rig.client)
    rig.client.close_session(rig.handle)
    with rig.client._connecting():
        with pytest.raises(ProviderReleaseError):
            with registry.endpoint_configuration_change(
                    binding.context.endpoint_id):
                pytest.fail('Configuration change was admitted')
    assert registry.resolve(binding.context) is binding
    assert not rig.client._closed


def test_ordinary_discovery_does_not_replace_a_query_session(rig):
    registry, registration, binding = registered(rig.client)
    service = EndpointService(registry, Mock())
    server = SimpleNamespace(endpoint_profile=SimpleNamespace(
        id=binding.context.endpoint_id))

    @_credential_change
    def discover(self, server, password, connect_as, database_target_id):
        return 'read-only discovery'

    assert discover(service, server) == 'read-only discovery'
    assert registry.resolve(binding.context) is binding
    assert len(registration.bindings) == 1
    service._principal_overrides[binding.context.endpoint_id] = 'alternate'
    with pytest.raises(EndpointRegistrationError, match='open sessions'):
        discover(service, server)
    assert service._principal_overrides[binding.context.endpoint_id] == (
        'alternate')


def test_local_persistence_failure_does_not_resurrect_released_client(rig):
    registry, registration, binding = registered(rig.client)
    rig.client.close_session(rig.handle)
    with pytest.raises(ValueError, match='owned persistence failure'):
        with registry.endpoint_configuration_change(
                binding.context.endpoint_id):
            raise ValueError('owned persistence failure')
    assert not registration.bindings
    assert rig.client._closed


@pytest.mark.parametrize('state', [
    'idle', 'failed-initialization', 'uncertain-transaction', 'service',
    'opening', 'temporary', 'recovery',
])
def test_all_owned_states_refuse_then_recover_without_profile_write(
        rig, state):
    registry, registration, binding = registered(rig.client)
    scope = nullcontext()
    if state in {'opening', 'temporary', 'recovery', 'service'}:
        rig.client.close_session(rig.handle)
    if state == 'failed-initialization':
        rig.client._failed_initializations.add(id(rig.handle))
    if state == 'uncertain-transaction':
        rig.client._state(rig.handle).visual_task_state_unknown = True
    if state == 'service':
        service = service_handle(rig)
    if state == 'opening':
        scope = rig.client._connecting()
    if state == 'temporary':
        scope = rig.client._temporary_operation()
    if state == 'recovery':
        rig.client._recoveries.append(object())
    try:
        with scope, pytest.raises(ProviderReleaseError):
            with registry.endpoint_configuration_change(
                    binding.context.endpoint_id):
                pytest.fail('Profile write was admitted')
        assert not rig.client._closed
        assert registration.release_failure_count == 0
        assert registry.resolve(binding.context) is binding
    finally:
        if state == 'recovery':
            rig.client._recoveries.clear()
    if state == 'service':
        rig.client.close_session(service)
    elif rig.handle in rig.client._connections:
        if state == 'failed-initialization':
            # The mock must report confirmed native detachment, just as the
            # real failed-initialization releaser is required to do.
            rig.handle._att = None
        rig.client.close_session(rig.handle)
    with registry.endpoint_configuration_change(binding.context.endpoint_id):
        assert rig.client._closed
        assert not registration.bindings


def test_busy_binding_does_not_release_an_idle_sibling(rig):
    registry, registration, binding = registered(rig.client)
    idle = FirebirdQueryClient(rig.client.config, module=rig.module)
    sibling = replace(binding, instance=FirebirdProvider(
        binding.context, registration.permission_grants, idle))
    original = dict(registration.bindings)
    registration.bindings.clear()
    registration.bindings['idle-sibling'] = sibling
    registration.bindings.update(original)
    try:
        with pytest.raises(ProviderReleaseError):
            with registry.endpoint_configuration_change(
                    binding.context.endpoint_id):
                pytest.fail('Busy endpoint accepted')
        assert not idle._closed
        assert len(registration.bindings) == 2
    finally:
        idle.close()


def test_admission_is_held_through_profile_persistence(rig):
    registry, _registration, binding = registered(rig.client)
    rig.client.close_session(rig.handle)
    entered = threading.Event()
    done = threading.Event()
    errors = []

    def opening():
        entered.set()
        try:
            with rig.client._connecting():
                errors.append('unexpected admission')
        except RelationalClientError as error:
            errors.append(str(error))
        finally:
            done.set()

    with registry.endpoint_configuration_change(binding.context.endpoint_id):
        worker = threading.Thread(target=opening)
        worker.start()
        assert entered.wait(2)
        assert not done.wait(0.05)
    worker.join(2)
    assert not worker.is_alive()
    assert errors == ['Firebird client is closed']


def test_new_generation_cannot_implicitly_rollback_existing_attachment(rig):
    registry, registration, binding = registered(rig.client)
    before = list(rig.handle.mock_calls)
    with pytest.raises(ProviderReleaseError, match='previous connection'):
        registry.resolve(replace(binding.context,
                                 runtime_identity_generation='new-profile'))
    assert rig.handle.mock_calls == before
    assert not rig.client._closed
    assert len(registration.bindings) == 1
    assert registry.resolve(binding.context) is binding


def test_generation_preflight_preserves_idle_sibling_and_allows_retry(rig):
    registry, registration, binding = registered(rig.client)
    idle = FirebirdQueryClient(rig.client.config, module=rig.module)
    sibling = replace(binding, instance=FirebirdProvider(
        binding.context, registration.permission_grants, idle))
    original = dict(registration.bindings)
    registration.bindings.clear()
    registration.bindings['idle-sibling'] = sibling
    registration.bindings.update(original)
    replacement = replace(binding.context,
                          runtime_identity_generation='replacement')
    try:
        with pytest.raises(ProviderReleaseError):
            registry.resolve(replacement)
        assert not idle._closed
        assert len(registration.bindings) == 2
        rig.client.close_session(rig.handle)
        registry._retire_superseded_generation(registration, replacement)
        assert idle._closed and rig.client._closed
        assert not registration.bindings
        assert registration.release_failure_count == 0
    finally:
        idle.close()

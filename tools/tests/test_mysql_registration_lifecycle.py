"""Configuration admission preserves native owners and retires stale clients."""
import threading
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from tools.tests.test_cdeadmin_relational_providers import context, MYSQL_PROFILE
from pgadmin.cdeadmin.sdk import RelationalClientConfig, RelationalClientError
from pgadmin.cdeadmin.providers.mysql_family.provider import MySQLDBAPIClient, MySQLPilotProvider
from pgadmin.cdeadmin.providers.mysql_family.mysql_recovery_bridge import Bridges


def provider(connect=None):
    client = MySQLDBAPIClient(RelationalClientConfig(
        profile=MYSQL_PROFILE, module_name='owned-test', version_query='SELECT VERSION()',
        version_parser=lambda value: value, connect_arguments=lambda route: route,
        metadata_reader=lambda *_args: []),
        SimpleNamespace(connect=connect or Mock(return_value=Mock())))
    return MySQLPilotProvider(context(MYSQL_PROFILE), Mock(), client)


@pytest.mark.parametrize('owner', ['session', 'connection', 'uncertain', 'request', 'worker', 'utility'])
def test_configuration_refuses_every_retained_native_owner(owner):
    value = provider()
    if owner == 'session':value._sessions['retained'] = object()
    elif owner == 'connection':value.client._connections.append(object())
    elif owner == 'uncertain':value.client._uncertain_sessions.add(1)
    elif owner == 'request':value.client._session_requests[1] = {}
    elif owner == 'worker':value.client._executions.tokens.append(SimpleNamespace(finished=threading.Event()))
    else:value.client._native_operations=1
    with pytest.raises(RelationalClientError, match='Close MySQL'):
        with value.profile_change_guard():pytest.fail('native owner was abandoned')
    assert not value.client._executions.closing


def test_connection_opening_cannot_cross_configuration_release():
    entered, resume, changed = threading.Event(), threading.Event(), threading.Event()
    connection = Mock();failures=[]
    def connect(**_options):
        entered.set();assert resume.wait(5);return connection
    value=provider(connect)
    def change():
        try:
            with value.profile_change_guard():
                value.release_for_profile_change();changed.set()
        except RelationalClientError:failures.append('retained native connection')
    with patch('pgadmin.cdeadmin.providers.mysql_family.mysql_connections.live_sql_mode_conversion'), patch('pgadmin.cdeadmin.providers.mysql_family.mysql_charsets.install'):
        opening=threading.Thread(target=lambda:value.client._connect({'route':{'host':'owned'}}))
        opening.start();assert entered.wait(5)
        changing=threading.Thread(target=change);changing.start()
        assert not changed.wait(.05)
        resume.set();opening.join(5);changing.join(5)
    assert not opening.is_alive() and not changing.is_alive()
    assert failures == ['retained native connection'] and not changed.is_set()
    connection.close.assert_not_called()
    value.client._discard_failed_session(connection)
    with value.profile_change_guard():value.release_for_profile_change()
    with pytest.raises(RelationalClientError, match='closing'):
        value.client._connect({'route':{'host':'owned'}})
    with pytest.raises(RelationalClientError, match='closing'):
        value.client.open_session({'route':{'host':'owned'}})


def test_release_failure_keeps_admission_retryable_without_claiming_success():
    value=provider()
    with patch.object(value.client, 'close', side_effect=[RuntimeError('release failed'), None]):
        with pytest.raises(RuntimeError):value.release_for_profile_change()
        with value.profile_change_guard():value.release_for_profile_change()


def test_native_utility_callback_is_owned_and_cannot_run_after_release():
    value=provider();called=[]
    def native(_secrets):
        with pytest.raises(RelationalClientError):value.release_for_profile_change()
        with pytest.raises(RelationalClientError, match='native utility work'):value.client.close()
        called.append(True)
    value.client._tool_secrets({},native)
    assert called==[True] and value.client._native_operations==0
    value.release_for_profile_change()
    with pytest.raises(RelationalClientError, match='closing'):
        value.client._tool_secrets({},native)
    assert called==[True]


def test_independent_recovery_utility_blocks_mutation_without_provider_bindings():
    bridges=Bridges();bridge=SimpleNamespace(binding={'endpoint_id':'owned','id':'original'},
        lock=threading.RLock(),users=1,close=Mock())
    bridges.entries['original']=bridge
    with pytest.raises(RelationalClientError, match='original utility leases'):
        with bridges.registration_change_guard('owned'):pytest.fail('leased transport changed')
    with bridges.registration_change_guard('different'):pass
    assert bridges.entries['original'] is bridge
    bridge.close.assert_not_called()
    bridge.users=0;bridges.detach_endpoint('owned')
    assert not bridges.entries;bridge.close.assert_called_once()


def test_independent_owner_refusal_precedes_any_registry_binding_release():
    from pgadmin.cdeadmin.core import ProviderRegistry
    value=provider();registry=ProviderRegistry();bridges=Bridges()
    bridge=SimpleNamespace(binding={'endpoint_id':value.context.endpoint_id,'id':'original'},
        lock=threading.RLock(),users=1)
    bridges.entries['original']=bridge
    registration=SimpleNamespace(bindings={'owned':SimpleNamespace(context=value.context,instance=value)})
    registry._registrations[('owned','test')]=registration
    with pytest.raises(RelationalClientError):
        with registry.endpoint_configuration_change(value.context.endpoint_id,
                ownership=bridges.registration_change_guard(value.context.endpoint_id)):
            pytest.fail('retained independent native owner admitted')
    assert not value.client._executions.closing
    assert registration.bindings['owned'].instance is value
    bridge.users=0
    with registry.endpoint_configuration_change(value.context.endpoint_id,
            ownership=bridges.registration_change_guard(value.context.endpoint_id)):pass
    assert not registration.bindings and value.client._executions.closing


def test_configuration_admission_does_not_block_native_relay_threads():
    bridges=Bridges();bridge=SimpleNamespace(binding={'endpoint_id':'owned','id':'original'},
        lock=threading.RLock(),users=0)
    bridges.entries['original']=bridge;relayed=threading.Event()
    def relay():
        with bridge.lock:relayed.set()
    with bridges.registration_change_guard('owned'):
        worker=threading.Thread(target=relay);worker.start()
        assert relayed.wait(2),'native authentication relay blocked by registration admission'
    worker.join(2);assert not worker.is_alive()

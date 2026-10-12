"""MariaDB leases cannot cross provider/configuration or failure boundaries."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from tools.tests.test_cdeadmin_relational_providers import MARIADB_PROFILE
from pgadmin.cdeadmin.providers.mysql_family.mariadb_connections import (
    Connector, discard,
)
from pgadmin.cdeadmin.providers.mysql_family.provider import MariaDBDBAPIClient
from pgadmin.cdeadmin.sdk import RelationalClientConfig, RelationalClientError


def factory():
    return SimpleNamespace(connect=Mock(side_effect=lambda **kw: Mock()))


def test_reset_preference_does_not_enable_global_pool():
    module = factory()
    owner = Connector(module)
    a = owner(host='one', pool_reset_connection=True)
    b = owner(host='two', pool_reset_connection=False)
    assert a is not b
    assert module.connect.call_args_list[0].kwargs == {'host': 'one'}
    assert module.connect.call_args_list[1].kwargs == {'host': 'two'}


def test_private_generation_rotation_and_outstanding_old_lease():
    module = factory()
    owner = Connector(module)
    a = owner(host='one', password='first', pool_size=2)
    native_a = a._native
    b = owner(host='one', password='first', pool_size=2)
    native_b = b._native
    b.close()
    changed = owner(host='two', password='second', pool_size=2)
    native_b.close.assert_called_once()
    native_a.close.assert_not_called()
    a.close()
    native_a.close.assert_called_once()
    changed.close()
    owner.close()


def test_same_name_other_provider_is_independent():
    module = factory()
    a, b = Connector(module), Connector(module)
    first = a(pool_name='shared', pool_validation_interval=0, pool_size=1)
    second = b(pool_name='shared', pool_validation_interval=0, pool_size=1)
    assert first._native is not second._native
    first.close()
    with pytest.raises(RelationalClientError, match='closed'):
        first.cursor()
    second.close()
    a.close()
    b.close()


def test_pool_exhaustion_reset_reuse_and_final_teardown():
    module = factory()
    owner = Connector(module)
    a = owner(pool_validation_interval=0, pool_size=1)
    native = a._native
    with pytest.raises(RelationalClientError, match='exhausted'):
        owner(pool_validation_interval=0, pool_size=1)
    a.close()
    native.rollback.assert_called_once()
    native.reset.assert_called_once()
    b = owner(pool_validation_interval=0, pool_size=1)
    assert b._native is native
    native.ping.assert_called_once_with()
    owner.close()
    native.close.assert_not_called()
    b.close()
    native.close.assert_called_once()
    with pytest.raises(RelationalClientError, match='closed'):
        owner()


@pytest.mark.parametrize('operation', ['rollback', 'reset'])
def test_failed_return_discards_native(operation):
    module = factory()
    owner = Connector(module)
    a = owner(pool_validation_interval=0, pool_size=1)
    native = a._native
    getattr(native, operation).side_effect = RuntimeError('native failure')
    with pytest.raises(RuntimeError):
        a.close()
    native.close.assert_called_once()
    replacement = owner(pool_validation_interval=0, pool_size=1)
    assert replacement._native is not native
    discard(replacement)
    owner.close()


def test_failed_idle_ping_replaces_only_idle_connection():
    module = factory()
    owner = Connector(module)
    a = owner(
        pool_validation_interval=0,
        pool_size=1,
        pool_reset_connection=False)
    native = a._native
    a.close()
    native.reset.assert_not_called()
    native.ping.side_effect = RuntimeError('dead')
    b = owner(
        pool_validation_interval=0,
        pool_size=1,
        pool_reset_connection=False)
    assert b._native is not native
    native.close.assert_called_once()
    b.close()
    owner.close()


@pytest.mark.parametrize('size', [0, -1, 65, True, '2', 1.5])
def test_invalid_size_never_connects(size):
    module = factory()
    with pytest.raises(RelationalClientError):
        Connector(module)(pool_size=size)
    module.connect.assert_not_called()


def test_client_close_failure_discards_and_forgets_handle():
    config = RelationalClientConfig(
        profile=MARIADB_PROFILE, module_name='test.mariadb',
        version_query='SELECT VERSION()',
        connect_arguments=lambda route: route,
        metadata_reader=lambda *_: [],
    )
    client = MariaDBDBAPIClient(config, 'tests', module=factory())
    handle = client.open_session({'route': {'host': 'one', 'pool_size': 1}})
    native = handle._native
    native.rollback.side_effect = RuntimeError('dead')
    with pytest.raises(RuntimeError):
        client.close_session(handle)
    assert not client._connections
    native.close.assert_called_once()
    client.close()


def make_client():
    return MariaDBDBAPIClient(RelationalClientConfig(
        profile=MARIADB_PROFILE, module_name='test.mariadb',
        version_query='SELECT VERSION()',
        connect_arguments=lambda route: route,
        metadata_reader=lambda *_: []), 'tests', module=factory())


@pytest.mark.parametrize('action', ['commit', 'rollback'])
def test_failed_finality_is_unknown_even_when_cached_flags_are_idle(action):
    client = make_client()
    handle = client.open_session({'route': {'host': 'one', 'pool_size': 1}})
    native = handle._native
    native.autocommit, native.server_status = False, 0
    getattr(native, action).side_effect = RuntimeError('lost reply')
    with pytest.raises(RelationalClientError):
        client.control_transaction(handle, action)
    assert client.describe_transaction(handle)['state'] == 'unknown'
    with pytest.raises(RelationalClientError, match='unknown'):
        client.execute(handle, {'source': 'SELECT 1'})
    with pytest.raises(RelationalClientError, match='unknown'):
        client.control_transaction(handle, 'rollback')
    native.rollback.reset_mock()
    receipt = client.close_session(handle)
    assert receipt['state'] == 'unknown'
    assert receipt['rollback_requested'] is False
    native.rollback.assert_not_called()
    native.close.assert_called_once()
    client.close()


def test_dead_native_session_does_not_publish_cached_transaction_flags():
    client = make_client()
    handle = client.open_session({'route': {'host': 'one'}})
    handle.autocommit, handle.server_status = False, 0
    handle.ping.side_effect = RuntimeError('dead')
    result = client.describe_transaction(handle)
    assert result['state'] == 'unknown'
    assert result['connection_usable'] is False
    assert 'in_transaction' not in result
    client.close()


def test_reset_checkout_does_not_trust_cached_autocommit_setter():
    native = Mock(database='schema', autocommit=False)
    owner = Connector(SimpleNamespace(connect=lambda **kw: native))
    first = owner(pool_size=1)
    first.close()
    second = owner(pool_size=1)
    native.cursor().execute.assert_called_once_with('SET autocommit = 0')
    second.close()
    owner.close()


def test_automatic_reconnect_is_refused_before_connect():
    module = factory()
    with pytest.raises(RelationalClientError, match='automatic reconnect'):
        Connector(module)(reconnect=True)
    module.connect.assert_not_called()

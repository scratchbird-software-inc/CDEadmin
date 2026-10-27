"""MySQL leases cannot cross provider/configuration or failure boundaries."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from tools.tests.test_cdeadmin_relational_providers import MYSQL_PROFILE
from pgadmin.cdeadmin.providers.mysql_family.mysql_connections import (
    Connector, discard,
)
from pgadmin.cdeadmin.providers.mysql_family.provider import MySQLDBAPIClient
from pgadmin.cdeadmin.providers.mysql_family.provider import (
    _initialize_mysql_connection,
)
from pgadmin.cdeadmin.sdk import RelationalClientConfig, RelationalClientError


class Native(Mock):
    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name in {'autocommit', 'in_transaction'} and type(value) is bool:
            status = self.__dict__.get('server_status', 0)
            if type(status) is int:
                bit = 2 if name == 'autocommit' else 1
                status = (status | bit) if value else (status & ~bit)
                super().__setattr__('server_status', status)
                super().__setattr__('_cdeadmin_server_status',
                    None if self.__dict__.get('lose_status_on_policy') else status)


def factory():
    def connection(**options):
        native = Native(connection_id=7, server_status=0, _cmysql=None)
        native.cursor.return_value.fetchone.return_value = ('server-one', 7)
        return native
    return SimpleNamespace(connect=Mock(side_effect=connection))


def test_reset_preference_does_not_enable_global_pool():
    module = factory()
    owner = Connector(module)
    a = owner(host='one', pool_reset_session=True)
    b = owner(host='two', pool_reset_session=False)
    assert a is not b
    assert module.connect.call_args_list[0].kwargs == {'host': 'one'}
    assert module.connect.call_args_list[1].kwargs == {'host': 'two'}


def test_real_driver_identity_attribute_fits_native_limits_and_preserves_operator_attributes():
    module = SimpleNamespace(__name__='mysql.connector', connect=Mock(side_effect=lambda **_options: Mock(_cmysql=None)))
    owner = Connector(module)
    attributes = {'application': 'operator supplied'}
    first = owner(use_pure=True, conn_attrs=attributes)
    second = owner(use_pure=True, conn_attrs=attributes)
    assert attributes == {'application': 'operator supplied'}
    values = []
    for native, call in zip((first, second), module.connect.call_args_list):
        supplied = call.kwargs['conn_attrs']
        assert supplied['application'] == 'operator supplied'
        added = set(supplied) - set(attributes)
        assert len(added) == 1
        key = added.pop(); value = supplied[key]
        assert len(key) <= 32 and not key.startswith('_')
        assert len(value) == 48 and bytes.fromhex(value).hex() == value
        assert native._cdeadmin_observer_attribute == {'name': key, 'value': value}
        values.append(value)
    assert values[0] != values[1]


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
    first = a(pool_name='shared', pool_size=1)
    second = b(pool_name='shared', pool_size=1)
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
    a = owner(pool_size=1)
    native = a._native
    with pytest.raises(RelationalClientError, match='exhausted'):
        owner(pool_size=1)
    a.close()
    native.rollback.assert_called_once()
    native.reset_session.assert_called_once()
    b = owner(pool_size=1)
    assert b._native is native
    native.ping.assert_called_once_with(reconnect=False)
    owner.close()
    native.close.assert_not_called()
    b.close()
    native.close.assert_called_once()
    with pytest.raises(RelationalClientError, match='closed'):
        owner()


@pytest.mark.parametrize('operation', ['rollback', 'reset_session'])
def test_failed_return_discards_native(operation):
    module = factory()
    owner = Connector(module)
    a = owner(pool_size=1)
    native = a._native
    getattr(native, operation).side_effect = RuntimeError('native failure')
    with pytest.raises(RuntimeError):
        a.close()
    native.close.assert_called_once()
    replacement = owner(pool_size=1)
    assert replacement._native is not native
    discard(replacement)
    owner.close()


def test_failed_idle_ping_replaces_only_idle_connection():
    module = factory()
    owner = Connector(module)
    a = owner(pool_size=1, pool_reset_session=False)
    native = a._native
    a.close()
    native.reset_session.assert_not_called()
    native.ping.side_effect = RuntimeError('dead')
    b = owner(pool_size=1, pool_reset_session=False)
    assert b._native is not native
    native.close.assert_called_once()
    b.close()
    owner.close()


@pytest.mark.parametrize('size', [0, -1, 33, True, '2', 1.5])
def test_invalid_size_never_connects(size):
    module = factory()
    with pytest.raises(RelationalClientError):
        Connector(module)(pool_size=size)
    module.connect.assert_not_called()


def test_client_close_failure_discards_and_forgets_handle():
    config = RelationalClientConfig(
        profile=MYSQL_PROFILE, module_name='test.mysql',
        version_query='SELECT VERSION()',
        connect_arguments=lambda route: route,
        metadata_reader=lambda *_: [],
    )
    client = MySQLDBAPIClient(config, module=factory())
    handle = client.open_session({'route': {'host': 'one', 'pool_size': 1}})
    native = handle._native
    native.rollback.side_effect = RuntimeError('dead')
    with pytest.raises(RuntimeError):
        client.close_session(handle)
    assert not client._connections
    native.close.assert_called_once()
    client.close()


def test_explicit_empty_mode_is_distinct_from_omitted_mode():
    handle = SimpleNamespace(sql_mode='STRICT_TRANS_TABLES')
    _initialize_mysql_connection(handle, {})
    assert handle.sql_mode == 'STRICT_TRANS_TABLES'
    _initialize_mysql_connection(handle, {'sql_mode': ''})
    assert handle.sql_mode == ''


def make_client():
    return MySQLDBAPIClient(RelationalClientConfig(
        profile=MYSQL_PROFILE, module_name='test.mysql',
        version_query='SELECT VERSION()',
        connect_arguments=lambda route: route,
        metadata_reader=lambda *_: []), module=factory())


@pytest.mark.parametrize('action', ['commit', 'rollback'])
def test_failed_finality_is_unknown_even_when_cached_flags_are_idle(action):
    client = make_client()
    handle = client.open_session({'route': {'host': 'one', 'pool_size': 1}})
    native = handle._native
    native.autocommit, native.in_transaction = False, False
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


def test_locally_closed_native_session_does_not_publish_cached_transaction_flags():
    client = make_client()
    handle = client.open_session({'route': {'host': 'one'}})
    handle.autocommit, handle.in_transaction = False, False
    handle.connection_id = None
    result = client.describe_transaction(handle)
    assert result['state'] == 'unknown'
    assert result['connection_usable'] is False
    assert 'in_transaction' not in result
    client.close()


def test_autocommit_requires_explicit_resolution_and_native_acknowledgement():
    client = make_client()
    handle = client.open_session({'route': {'host': 'one'}})
    handle.autocommit, handle.in_transaction = False, True
    with pytest.raises(RelationalClientError, match='Commit or roll back'):
        client.control_transaction(handle, 'autocommit_on')
    assert handle.autocommit is False
    handle.commit.assert_not_called()
    handle.rollback.assert_not_called()
    assert client.control_transaction(handle, 'autocommit_off')['autocommit'] is False
    handle.in_transaction = False
    assert client.control_transaction(handle, 'autocommit_on')['autocommit'] is True
    assert client.control_transaction(handle, 'autocommit_off')['autocommit'] is False
    client.close()


def test_lost_autocommit_acknowledgement_quarantines_without_reconnect():
    client = make_client()
    handle = client.open_session({'route': {'host': 'one'}})
    handle.autocommit, handle.in_transaction = False, False
    handle.lose_status_on_policy = True
    with pytest.raises(RelationalClientError, match='acknowledgement'):
        client.control_transaction(handle, 'autocommit_on')
    assert client.describe_transaction(handle)['state'] == 'unknown'
    with pytest.raises(RelationalClientError, match='unknown'):
        client.control_transaction(handle, 'autocommit_on')
    handle.ping.assert_not_called()
    client.close()

"""Preserved PostgreSQL workspaces must not silently select maintenance DB."""
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import pytest
import uuid

from tools.tests.test_cdeadmin_endpoint_registration import EndpointService
from pgadmin.cdeadmin.endpoints.service import EndpointRegistrationError


@pytest.fixture
def workspace():
    service = object.__new__(EndpointService)
    service.provider_registry = Mock()
    service.provider_registry.admitted_permissions.return_value = set()
    service.provider_registry.resolve.return_value.manifest = {'identity': {}}
    endpoint = NS(id=str(uuid.uuid4()), provider_version=None,
        provider_id='org.pgadmin.postgresql', profile_id='postgresql-native',
        pool_namespace=str(uuid.uuid4()), session_namespace=str(uuid.uuid4()),
        cache_namespace=str(uuid.uuid4()), diagnostic_namespace=str(uuid.uuid4()))
    server = NS(id=7, user_id=1, name='PostgreSQL', endpoint_profile=endpoint,
                host='localhost', port=5432, username='qa')
    connection = Mock(db='selected_database')
    connection.connected.return_value = True
    manager = Mock(ver='PostgreSQL 18.3 full server banner', version=180003)
    manager.connection.return_value = connection
    with patch('pgadmin.utils.driver.registry.DriverRegistry.get') as driver:
        driver.return_value.connection_manager.return_value = manager
        yield service, server, manager, connection


def test_explicit_database_binding(workspace):
    service, server, manager, _ = workspace
    context, endpoint, _ = service.workspace(server, database_target_id='postgresql-database:42')
    manager.connection.assert_called_once_with(did=42)
    assert endpoint['route']['database_id'] == 42
    assert context.cache_namespace == str(uuid.uuid5(uuid.UUID(server.endpoint_profile.cache_namespace), 'postgresql-database:42'))
    assert context.session_namespace == str(uuid.uuid5(uuid.UUID(server.endpoint_profile.session_namespace), 'postgresql-database:42'))
    assert context.cache_namespace != server.endpoint_profile.cache_namespace


def test_server_scope_is_explicit(workspace):
    service, server, manager, _ = workspace
    _, endpoint, _ = service.workspace(server)
    manager.connection.assert_called_once_with()
    assert 'database_id' not in endpoint['route']


def test_disconnected_target_is_not_reconnected_or_replaced(workspace):
    service, server, manager, connection = workspace
    connection.connected.return_value = False
    with pytest.raises(EndpointRegistrationError, match='must be connected'):
        service.workspace(server, database_target_id='postgresql-database:42')
    manager.connection.assert_called_once_with(did=42)
    connection.connect.assert_not_called()


def test_invalid_target_does_not_touch_manager(workspace):
    service, server, manager, _ = workspace
    with pytest.raises(EndpointRegistrationError, match='Invalid'):
        service.workspace(server, database_target_id='42; SELECT 1')
    manager.connection.assert_not_called()


def test_native_descriptors_do_not_offer_generic_registration_mutation(workspace):
    service, server, _, connection = workspace
    connection.execute_dict.return_value = (True, {'rows': [
        {'did': 42, 'datname': 'selected_database', 'datallowconn': True}]})
    route = service.route_catalog(server)
    assert route['server_forms']['forms'] == {}
    assert set(route['routes'][0]['configuration']) == {'host', 'port', 'user'}
    catalog = service.database_catalog(server)
    assert catalog['target_management'] is False
    assert catalog['active_target_id'] == 'postgresql-database:42'
    assert catalog['targets'][0]['database'] == 'selected_database'

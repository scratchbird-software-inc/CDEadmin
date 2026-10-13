"""Native workspace target and document boundaries for MariaDB catalog capture."""
from types import SimpleNamespace
from unittest.mock import Mock
import json
import pytest

from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService, ProviderWorkspaceError
from pgadmin.cdeadmin.providers.mysql_family.provider import MariaDBPilotProvider
from tools.tests.test_mariadb_catalog import Connection, capture
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export


def fixture():
    provider = object.__new__(MariaDBPilotProvider)
    provider.capture_catalog = Mock(return_value=capture(Connection(), 'demo'))
    server = SimpleNamespace(user_id=7, endpoint_profile=SimpleNamespace(profile_id='mariadb-native'))
    context = SimpleNamespace(profile_id='mariadb-native', endpoint_id='owned-endpoint')
    endpoint = {'route': {'database': 'demo'}}
    service = object.__new__(ProviderWorkspaceService)
    service.endpoint_service = SimpleNamespace(workspace=Mock(return_value=(context, endpoint, None)),
        database_catalog=Mock(return_value={'targets': [{'target_id': 'owned-target', 'database': 'demo'}]}),
        provider_registry=SimpleNamespace(resolve=Mock(return_value=SimpleNamespace(instance=provider))))
    return service, server, provider, context, endpoint


def test_exact_native_engine_and_registered_route_required_before_capture():
    for profile in ('mysql-native', 'postgresql-native', 'firebird-native'):
        service, server, provider, _, _ = fixture()
        server.endpoint_profile.profile_id = profile
        with pytest.raises(ProviderWorkspaceError):
            service.mariadb_catalog(server, {'database_target_id': 'owned-target'})
        provider.capture_catalog.assert_not_called()
    for target, database in (('foreign-target', 'demo'), ('owned-target', 'another-database')):
        service, server, provider, _, endpoint = fixture()
        endpoint['route']['database'] = database
        with pytest.raises(ProviderWorkspaceError):
            service.mariadb_catalog(server, {'database_target_id': target})
        provider.capture_catalog.assert_not_called()


def test_native_uid_and_documentary_comparison_preserve_ownership():
    service, server, provider, _, _ = fixture()
    result = service.mariadb_catalog(server, {'database_target_id': 'owned-target'})
    assert result['server_uid'] == 'native-server'
    assert result['provenance']['mapping'] == 'scratchrobin.mariadb.catalog@1'
    source = json.dumps(result['snapshot'])
    comparison = service.mariadb_catalog(server, {'database_target_id': 'owned-target', 'source': source}, compare=True)
    assert not comparison['changes']
    for key, value in (('endpoint_id', 'foreign-endpoint'), ('target_id', 'foreign-target')):
        options = {'endpoint_id': 'owned-endpoint', 'target_id': 'owned-target', 'generation': 'capture', 'engine': 'mariadb'}
        options[key] = value
        other = build_export(provider.capture_catalog.return_value['resources'], **options)
        provider.capture_catalog.reset_mock()
        with pytest.raises(ProviderWorkspaceError, match='another endpoint or database'):
            service.mariadb_catalog(server, {'database_target_id': 'owned-target', 'source': json.dumps(other['snapshot'])}, compare=True)
        provider.capture_catalog.assert_not_called()


def test_explicit_data_capture_forwards_native_identity_and_rejects_unknown_fields():
    service, server, provider, _, _ = fixture()
    provider.capture_data = Mock(return_value={'acquisition': {'engine_id': 'mariadb'}})
    request = {'database_target_id': 'owned-target', 'resource_id': 'native-table',
        'expected_server_uid': 'native-server', 'mode': 'full', 'row_limit': 42}
    assert service.mariadb_data_capture(server, request)['acquisition']['engine_id'] == 'mariadb'
    provider.capture_data.assert_called_once_with({'database': 'demo'}, 'native-table',
        endpoint_id='owned-endpoint', target_id='owned-target', expected_server_uid='native-server', mode='full', row_limit=42)
    provider.capture_data.reset_mock()
    for invalid in ({**request, 'source': 'SELECT * FROM another_database.secret'},
                    {**request, 'database_target_id': 'foreign-target'}):
        with pytest.raises(ProviderWorkspaceError):
            service.mariadb_data_capture(server, invalid)
        provider.capture_data.assert_not_called()

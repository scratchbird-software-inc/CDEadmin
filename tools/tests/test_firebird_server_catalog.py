"""Server capture uses registered, independently authorized database scopes."""
import config  # Initialize application configuration before ORM imports.
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService, ProviderWorkspaceError


def fixture():
    service = object.__new__(ProviderWorkspaceService)
    service.endpoint_service = SimpleNamespace(database_catalog=Mock(return_value={
        'targets': [{'target_id': 'one'}, {'target_id': 'two'}]}))
    service.navigator_snapshot = Mock(return_value={'generation': 'observed'})
    service.export_firebird_catalog = Mock(return_value={'snapshot': {}, 'provenance': {}})
    return service, SimpleNamespace(endpoint_profile=SimpleNamespace(profile_id='firebird-native'))


def test_each_capture_uses_exact_registration_and_generation_without_activation():
    service, server = fixture()
    for target in ('one', 'two'):
        result = service.capture_firebird_registered_catalog(server, {
            'target_id': target, 'refresh': True, 'include_system': False})
        assert result['target_id'] == target
        service.navigator_snapshot.assert_called_with(server, database_target_id=target)
        service.export_firebird_catalog.assert_called_with(server, {
            'generation': 'observed', 'database_target_id': target,
            'refresh': True, 'include_system': False})


@pytest.mark.parametrize('body', [None, {}, {'target_id': 'foreign'},
    {'target_id': 'one', 'refresh': 1}, {'target_id': 'one', 'include_system': 'true'},
    {'target_id': 'one', 'route': '/other/database.fdb'}, {'target_id': 'x' * 1025}])
def test_rejects_unregistered_or_ambiguous_scope_before_catalog_access(body):
    service, server = fixture()
    with pytest.raises(ProviderWorkspaceError):
        service.capture_firebird_registered_catalog(server, body)
    service.navigator_snapshot.assert_not_called()
    service.export_firebird_catalog.assert_not_called()


def test_other_engines_and_registration_authorization_failure_never_capture():
    service, server = fixture()
    server.endpoint_profile.profile_id = 'mysql-native'
    with pytest.raises(ProviderWorkspaceError):
        service.capture_firebird_registered_catalog(server, {'target_id': 'one'})
    service.endpoint_service.database_catalog.assert_not_called()
    server.endpoint_profile.profile_id = 'firebird-native'
    service.endpoint_service.database_catalog.side_effect = ProviderWorkspaceError('unavailable')
    with pytest.raises(ProviderWorkspaceError):
        service.capture_firebird_registered_catalog(server, {'target_id': 'one'})
    service.export_firebird_catalog.assert_not_called()

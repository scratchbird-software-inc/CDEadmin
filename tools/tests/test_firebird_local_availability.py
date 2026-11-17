"""Local availability keeps native choices and an attachment-free opener."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
from pgadmin.cdeadmin.providers.firebird import local_services as local
from pgadmin.cdeadmin.providers.firebird.provider import _create_client
from pgadmin.cdeadmin.visual_admin import ProviderVisualAdministration
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService
from pgadmin.cdeadmin.sdk import RelationalClientError


@pytest.mark.parametrize('operation', ['shutdown_database', 'bring_online', 'fixup_database', 'repair_database', 'upgrade_database', 'backup_logical', 'restore_logical'])
def test_local_availability_opener_uses_registered_target_without_sql(operation):
    service = object.__new__(ProviderWorkspaceService)
    service.endpoint_service = Mock()
    service.endpoint_service.database_catalog.return_value = {
        'targets': [{'target_id': 'owned', 'display_name': 'Owned local DB'}]}
    root = {'identity': {'engine_id': 'firebird'}, 'model_family': 'relational',
            'resource_id': 'root', 'display_name': 'Local runtime', 'generation': 'g'}
    catalog = embedded.ADMINISTRATION.catalog(catalog_for_engine('firebird'))
    result = service._service_workspace_targets(SimpleNamespace(endpoint_id='endpoint'),
        root, catalog, 'owner', 'owned', operation)
    target, = result
    assert target['extensions']['cdeadmin'] == {
        'database_target_id': 'owned', 'service_scope_only': True,
        'focused_operation_id': operation}
    service.endpoint_service.database_catalog.assert_called_once_with('owner')
    service.endpoint_service.workspace.assert_not_called()


def test_shared_shutdown_descriptor_attention_field_is_admitted(tmp_path):
    file = tmp_path / 'owned.fdb'; file.touch()
    route = {'attachment_mode': 'embedded', 'database': str(file),
             'filesystem_root': str(tmp_path), 'user': 'SYSDBA'}
    client = _create_client(Mock(), attachment_mode='embedded',
        profile=embedded.PROFILE, administration=embedded.ADMINISTRATION)
    visual = ProviderVisualAdministration(SimpleNamespace(endpoint_id='owned',
        runtime_verification_state='verified', mode='provider_native',
        declared_runtime_family='firebird', verified_runtime_family='firebird'),
        SimpleNamespace(require=Mock(), allows=lambda *_: True), 'firebird', '5.0.4', client)
    try:
        request = {'resource_kind': 'database', 'operation_id': 'shutdown_database',
            'target_resource': {'resource_kind': 'database', 'display_name': file.name},
            '_provider_route': route, 'draft': {'mode': 'FULL', 'method': 'FORCED',
                'shutdown_timeout': 0, 'confirmation': file.name}}
        assert visual.validate(request)['valid']
        request['draft']['confirmation'] = True
        assert not visual.validate(request)['valid']
    finally:
        client.close()


@pytest.mark.parametrize('operation,options', [
    ('shutdown_database', {'mode': 'NORMAL', 'method': 'FORCED', 'shutdown_timeout': 0}),
    ('shutdown_database', {'mode': 'FULL', 'method': 'other', 'shutdown_timeout': 0}),
    ('shutdown_database', {'mode': 'FULL', 'method': 'FORCED', 'shutdown_timeout': 32768}),
    ('shutdown_database', {'mode': 'FULL', 'method': 'FORCED', 'shutdown_timeout': True}),
    ('shutdown_database', {'mode': 'FULL', 'method': 'FORCED', 'confirmation': {}}),
    ('bring_online', {'mode': 'FULL'}), ('bring_online', {'mode': 'NORMAL', 'host': 'remote'}),
    ('fixup_database', {'fixup_flags': ['IN_PLACE']}),
    ('fixup_database', {'fixup_flags': 'SEQUENCE'}),
])
def test_invalid_local_availability_choices_fail_before_service_attachment(tmp_path, operation, options):
    file = tmp_path / 'owned.fdb'; file.touch()
    route = {'attachment_mode': 'embedded', 'database': str(file),
             'filesystem_root': str(tmp_path)}
    with pytest.raises(RelationalClientError):
        local.validate_operation(route, operation, str(file), options)

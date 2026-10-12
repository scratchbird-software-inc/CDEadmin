"""Every declared Firebird operation uses the same authoritative target scope.

This is a dispatch-boundary test, not native execution qualification.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION
from pgadmin.cdeadmin.workspace.service import (
    ProviderWorkspaceService, ProviderWorkspaceError,
)


OPERATIONS = [(kind, operation)
              for kind, operations in ADMINISTRATION.dialect.supported.items()
              for operation in sorted(operations)]


@pytest.mark.parametrize('kind,operation', OPERATIONS)
@pytest.mark.parametrize('method', [
    'validate_visual_admin', 'plan_visual_admin', 'apply_visual_admin'])
@pytest.mark.parametrize('scope_source', ['explicit', 'resource', 'conflict'])
def test_every_operation_preserves_selected_target(
        kind, operation, method, scope_source):
    callback = Mock()
    endpoint_service = Mock()
    route = {'database': '/owned/selected.fdb', 'route_id': 'route-selected'}
    endpoint_service.workspace.return_value = (
        'selected-context', {'route': route}, {})
    endpoint_service.provider_registry.resolve.return_value = SimpleNamespace(
        instance=SimpleNamespace(**{method: callback}))
    service = object.__new__(ProviderWorkspaceService)
    service.endpoint_service = endpoint_service
    target = {'resource_kind': kind, 'resource_id': 'owned-resource',
              'extensions': {'cdeadmin': {}}}
    request = {'resource_kind': kind, 'operation_id': operation,
               'target_resource': target, 'draft': {},
               '_provider_route': {'database': '/forged/other.fdb'}}
    if scope_source != 'resource':
        request['database_target_id'] = 'selected'
    if scope_source != 'explicit':
        target['extensions']['cdeadmin']['database_target_id'] = (
            'other' if scope_source == 'conflict' else 'selected')
    if scope_source == 'conflict':
        with pytest.raises(ProviderWorkspaceError, match='conflicts'):
            service._prepare_visual_admin_call('owner', method, request)
        callback.assert_not_called()
    else:
        context, resolved, payload = service._prepare_visual_admin_call(
            'owner', method, request)
        assert context == 'selected-context' and resolved is callback
        assert payload['_provider_route'] == route
        assert payload['_provider_route'] is not route
        assert payload['target_resource']['extensions']['cdeadmin'][
            'database_target_id'] == 'selected'
        assert request['_provider_route']['database'] == '/forged/other.fdb'
    endpoint_service.workspace.assert_called_once_with(
        'owner', database_target_id='selected')

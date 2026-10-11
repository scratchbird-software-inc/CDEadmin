"""Restores name a destination without selecting or attaching to a database."""
import pytest
from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine


@pytest.mark.parametrize('operation', ['restore_logical', 'restore_physical'])
def test_restore_descriptor_is_targetless_server_service(operation):
    catalog = ADMINISTRATION.catalog(catalog_for_engine('firebird'))
    database = next(item for item in catalog['objects']
                    if item['resource_kind'] == 'database')
    descriptor = next(item for item in database['operations']
                      if item['operation_id'] == operation)
    assert descriptor['target_required'] is False
    assert descriptor['workspace_scope'] == 'server_service'


@pytest.mark.parametrize('operation', ['restore_logical', 'restore_physical'])
@pytest.mark.parametrize('route', [{'host': 'localhost'},
                                 {'database': '/existing/untouched.fdb'}])
def test_restore_plan_uses_explicit_destination(operation, route):
    draft = {'restore_database': '/new/restored.fdb'}
    draft.update({'backup_file': '/backups/base.fbk'}
                 if operation == 'restore_logical' else
                 {'backup_files': ['/backups/base.nbk']})
    request = {'resource_kind': 'database', 'operation_id': operation,
               '_provider_route': route, 'draft': draft}
    assert not ADMINISTRATION.validate(request)['errors']
    plan = ADMINISTRATION.plan(request)
    assert plan['command_preview']['driver_operation'] == 'firebird-service'
    compiled = ADMINISTRATION._compile(request)
    assert compiled['database'] == '/new/restored.fdb'
    assert compiled['options']['restore_database'] == '/new/restored.fdb'

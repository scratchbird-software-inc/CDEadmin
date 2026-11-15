"""An embedded service never acquires a network or arbitrary-file authority."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import firebird.driver as native
from firebird.driver.config import DriverConfig

from pgadmin.cdeadmin.providers.firebird import local_services as local
from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
from pgadmin.cdeadmin.providers.firebird.provider import _create_client
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine


@pytest.fixture
def route(tmp_path):
    path = tmp_path/'owned.fdb'; path.touch()
    return {'attachment_mode':'embedded','database':str(path),'filesystem_root':str(tmp_path),'user':'SYSDBA'}


@pytest.mark.parametrize('field,value', [('host','127.0.0.1'),('port',3050),('password','secret'),
    ('wire_config','Providers=Remote'),('trusted_auth',True),('credential_reference_id','other'),
    ('credential_references',{'database_password':'other'}),('credential_kinds',['database_password'])])
def test_network_and_secret_inputs_are_refused_before_local_attachment(route, field, value):
    with pytest.raises(RelationalClientError): local.route_for_service({**route,field:value})


def test_local_arguments_force_engine13_and_both_permissions_without_mutating_network_defaults(route, monkeypatch):
    from pgadmin.cdeadmin.providers.firebird import provider
    monkeypatch.setattr(native,'driver_config',DriverConfig('local-only-service-test'))
    monkeypatch.setattr(provider,'_configure_client_library',Mock())
    monkeypatch.setattr(provider,'_client_library_identity',Mock(return_value='Firebird5.0.4'))
    permissions=Mock(); result=local.arguments(route,permissions,native)
    assert [c.args for c in permissions.require.call_args_list] == [('embedded_runtime',),('filesystem',)]
    config=native.driver_config.get_server(result['server'])
    assert config.host.value=='service_mgr' and config.config.value=='Providers=Engine13'
    assert config.password.value is None and config.user.value is None
    assert result=={'server':'cde_embedded_services_engine13','user':'SYSDBA'}


def test_only_implemented_local_action_and_exact_approved_database_are_admitted(route,tmp_path):
    assert local.validate_operation(route,'database_statistics',route['database'],{'statistics_flags':['HDR_PAGES']})
    another=tmp_path/'another.fdb';another.touch()
    for operation,database,options in [('backup_logical',route['database'],{}),
            ('database_statistics',str(another),{}),('database_statistics',route['database'],{'restore_database':'other'})]:
        with pytest.raises(RelationalClientError):local.validate_operation(route,operation,database,options)
    with pytest.raises(RelationalClientError):local.route_for_service({**route,'filesystem_root':'/'})


def test_local_catalog_keeps_shared_typed_form_and_database_target_scope():
    catalog=embedded.ADMINISTRATION.catalog(catalog_for_engine('firebird'))
    task=next(x for row in catalog['objects']if row['resource_kind']=='database'
              for x in row['operations']if x['operation_id']=='database_statistics')
    assert task.get('workspace_scope')!='server_service'
    assert {x['field_id']for x in task['form']['fields']}=={'statistics_flags','tables','role'}
    assert embedded.ADMINISTRATION.supports('database','database_statistics')
    assert not embedded.ADMINISTRATION.supports('database','backup_logical')


def test_replaced_file_is_refused_before_service_dispatch(route,tmp_path):
    request={'resource_kind':'database','operation_id':'database_statistics','draft':{'statistics_flags':['HDR_PAGES']},'_provider_route':route}
    permissions=Mock()
    client=_create_client(permissions,attachment_mode='embedded',profile=embedded.PROFILE,administration=embedded.ADMINISTRATION)
    client._connect_server=Mock(return_value=object());client._release_server=Mock()
    plan=client.plan_admin_operation(request)
    old=tmp_path/'original.fdb'; (tmp_path/'owned.fdb').rename(old); (tmp_path/'owned.fdb').touch()
    client.run_server_operation=Mock()
    try:
        with pytest.raises(RelationalClientError,match='changed since review') as failure:
            client.apply_admin_operation(plan)
        assert failure.value.rejected and failure.value.nothing_changed
        assert not failure.value.native_dispatched
        client.run_server_operation.assert_not_called()
    finally:client.close()


def test_secret_reference_is_rejected_before_native_connector_or_lease(route):
    permissions=Mock()
    client=_create_client(permissions,attachment_mode='embedded',profile=embedded.PROFILE,administration=embedded.ADMINISTRATION)
    try:
        with pytest.raises(RelationalClientError,match='network credentials'):
            client._connect_server({'route':{**route,'credential_reference_id':'other'}})
        permissions.acquire_secret.assert_not_called()
    finally:client.close()

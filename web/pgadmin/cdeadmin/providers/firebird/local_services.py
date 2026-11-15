"""Explicit Engine13 local services under the embedded filesystem authority."""
from collections.abc import Mapping
from pathlib import Path

from ...sdk import RelationalClientError
from .embedded import embedded_route

OPERATIONS = frozenset({'database_statistics'})


def route_for_service(route, permissions=None):
    if not isinstance(route, Mapping) or route.get('attachment_mode') != 'embedded':
        raise RelationalClientError('Local Firebird services require the embedded profile')
    if any(route.get(key) for key in ('credential_reference_id', 'credential_references', 'credential_kinds')):
        raise RelationalClientError('Local Firebird services do not acquire network credentials')
    value = embedded_route(route, permissions)
    if not Path(value['database']).is_file():
        raise RelationalClientError('Local database statistics require an existing approved file')
    return value


def validate_operation(route, operation, database, options):
    selected = route_for_service(route)
    if operation not in OPERATIONS:
        raise RelationalClientError('This embedded local service operation is not implemented')
    if not isinstance(options, Mapping) or set(options) - {'statistics_flags', 'tables', 'role'}:
        raise RelationalClientError('Select typed local database statistics options')
    actual = embedded_route({**route, 'database': database})['database']
    if actual != selected['database']:
        raise RelationalClientError('Local service target differs from the approved database')
    return selected


def file_identity(route):
    value = route_for_service(route)
    state = Path(value['database']).stat()
    return {'path': value['database'], 'device': str(state.st_dev), 'inode': str(state.st_ino)}


def arguments(route, permissions, module):
    selected = route_for_service(route, permissions)
    from .provider import _CONFIG_LOCK, _configure_client_library, _client_library_identity
    _configure_client_library(module)
    _client_library_identity(module)
    name = 'cde_embedded_services_engine13'
    with _CONFIG_LOCK:
        config = module.driver_config.get_server(name)
        if config is None:
            config = module.driver_config.register_server(name)
        # All requests share immutable transport settings. Principal and role
        # are explicit attachment arguments, never mutable global defaults.
        config.host.value = 'service_mgr'
        config.port.value = None
        config.user.value = None
        config.password.value = None
        config.trusted_auth.value = False
        config.auth_plugin_list.value = None
        config.config.value = 'Providers=Engine13'
    result = {'server': name, 'user': selected.get('user') or 'SYSDBA'}
    if selected.get('role'):
        result['role'] = selected['role']
    return result

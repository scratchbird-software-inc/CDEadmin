"""Local attachment boundary: embedded is not network authentication."""

import os
from pathlib import Path

from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from ..embedded_route import contained_database


def require_attachment_mode(route, expected):
    """An admitted provider instance never changes transport per request."""
    selected = route.get('attachment_mode', 'network')
    if selected not in ('network', 'embedded'):
        raise RelationalClientError('Firebird attachment mode is invalid')
    if expected is not None and selected != expected:
        raise RelationalClientError(
            'Firebird attachment mode does not match the admitted endpoint')
    return route


def embedded_route(route, permissions=None, *, database=None):
    """Validate an opted-in local route before consulting the native driver.

    Engine13 authenticates by filesystem access, not the supplied password.
    The caller must separately grant embedded execution and filesystem access.
    No client-library switching is performed in this process.
    """
    mode = route.get('attachment_mode', 'network')
    if mode not in ('network', 'embedded'):
        raise RelationalClientError('Firebird attachment mode is invalid')
    if mode != 'embedded':
        if permissions is not None and not route.get('host') and (
                route.get('protocol') not in {'INET', 'INET4', 'INET6',
                                              'XNET'}):
            raise RelationalClientError(
                'Firebird local attachments require explicit embedded mode '
                'and filesystem authorization')
        return route
    if permissions is not None:
        permissions.require('embedded_runtime')
        permissions.require('filesystem')
    forbidden = (
        'host', 'port', 'protocol', 'wire_config', 'wire_crypt',
        'wire_compression', 'auth_plugin_list', 'trusted_auth',
        'service_expected_database', 'password', 'timeout',
        'dummy_packet_interval',
    )
    if any(route.get(key) not in (None, '') for key in forbidden):
        raise RelationalClientError(
            'Firebird embedded attachment cannot use network, service or '
            'authentication options')
    selected = dict(route)
    if database is not None:
        selected['database'] = database
    if selected.get('database') == ':memory:':
        raise RelationalClientError(
            'Firebird embedded attachment requires a database file')
    path = contained_database(selected)
    root = Path(selected['filesystem_root']).resolve()
    if root == Path(root.anchor) or not root.is_dir():
        raise RelationalClientError(
            'Firebird embedded filesystem root must be an existing '
            'dedicated directory')
    target = Path(path)
    if target.exists() and not target.is_file():
        raise RelationalClientError(
            'Firebird embedded database target must be a regular file')
    if not target.parent.is_dir():
        raise RelationalClientError(
            'Firebird embedded database parent directory does not exist')
    if not os.access(root, os.X_OK):
        raise RelationalClientError(
            'Firebird embedded filesystem root is inaccessible')
    selected['database'] = path
    return selected


def reject_embedded_service(route):
    if route.get('attachment_mode') == 'embedded':
        raise RelationalClientError(
            'Firebird embedded profiles cannot open server Services API '
            'operations; select an authenticated network server profile')

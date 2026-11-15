"""Explicit Engine13 local services under the embedded filesystem authority."""
from collections.abc import Mapping
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar
import os
import stat
import sys
import tempfile

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
    from .statistics import validate_options
    validate_options(options)
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



_SERVICE_TARGET = ContextVar('firebird_local_service_target', default=None)


@contextmanager
def pinned_target(route, reviewed):
    """Pin the reviewed inode through native service completion and release.

    Private inode aliases never come from a request. The
    route retains its approved filename for authorization and recompilation.
    Native qualification currently covers Linux; other platform teams own
    qualification of their file-pinning adapter.
    """
    selected = route_for_service(route)
    original = selected['database']
    descriptor = None
    alias_area = None
    token = None
    entered = False
    try:
        if sys.platform != 'linux':
            # Preserve existing platform service behaviour and its explicitly
            # unfenced receipt until that platform supplies a qualified pin.
            if file_identity(route) != reviewed:
                raise RelationalClientError('Local database file changed since review')
            token = _SERVICE_TARGET.set((original, original))
            entered = True
            yield original
            return
        descriptor = os.open(original, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        info = os.fstat(descriptor)
        actual = {'path': original, 'device': str(info.st_dev), 'inode': str(info.st_ino)}
        if not stat.S_ISREG(info.st_mode) or actual != reviewed:
            raise RelationalClientError('Local database file changed since review; native service not dispatched')
        # Native gstat canonicalizes descriptor symlinks. A private hardlink
        # instead gives it a stable native filename for this exact inode.
        # Verify after link creation: linking a raced same-name replacement
        # must never authorize that replacement. Only read-only statistics
        # use this alias; it is never a database attachment/lock alias.
        alias_area = tempfile.TemporaryDirectory(prefix='.scratchrobin-statistics-',dir=str(Path(original).parent))
        native = str(Path(alias_area.name) / 'database.fdb')
        os.link(original,native,follow_symlinks=False)
        resolved = os.stat(native,follow_symlinks=False)
        if (resolved.st_dev, resolved.st_ino) != (info.st_dev, info.st_ino):
            raise RelationalClientError('Native statistics alias does not pin the reviewed file')
        token = _SERVICE_TARGET.set((original, native))
        entered = True
        yield native
    except OSError as error:
        if entered:
            raise
        failure = RelationalClientError('Cannot pin the approved local database file')
        failure.rejected = failure.nothing_changed = True
        failure.native_dispatched = failure.automatic_retry = False
        raise failure from error
    except RelationalClientError as error:
        if not entered:
            error.rejected = error.nothing_changed = True
            error.native_dispatched = error.automatic_retry = False
        raise
    finally:
        if token is not None:
            _SERVICE_TARGET.reset(token)
        if descriptor is not None:
            os.close(descriptor)
        if alias_area is not None:
            alias_area.cleanup()


def dispatch_target(database):
    target = _SERVICE_TARGET.get()
    if target is None or database != target[0]:
        raise RelationalClientError('Local native service requires the pinned reviewed target')
    return target[1]

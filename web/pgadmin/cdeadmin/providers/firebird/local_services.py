"""Explicit Engine13 local services under the embedded filesystem authority."""
from collections.abc import Mapping
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar
import os
import stat
import sys
import tempfile
from threading import RLock
from weakref import WeakValueDictionary

from ...sdk import RelationalClientError
from .embedded import embedded_route

LOCAL_OPTIONS = {
    'set_access_mode': {'mode'},
    'set_page_cache_size': {'page_buffers'},
    'set_sweep_interval': {'sweep_interval'},
    'set_space_reservation': {'mode'},
    'set_write_mode': {'mode'},
    'set_sql_dialect': {'sql_dialect'},
    'set_replica_mode': {'mode'},
    'remove_linger': set(),
    'sweep_database': {'parallel_workers'},
    'validate_database': {'include_table', 'exclude_table', 'include_index',
                          'exclude_index', 'lock_timeout'},
    'database_statistics': {'statistics_flags', 'tables'},
    'shutdown_database': {'mode', 'method', 'shutdown_timeout', 'confirmation'},
    'bring_online': {'mode'},
    'fixup_database': {'fixup_flags', 'confirmation'},
    'activate_shadow': {'shadow_filename', 'confirmation', 'original_isolated'},
}
OPERATIONS = frozenset(LOCAL_OPTIONS)


def route_for_service(route, permissions=None):
    if not isinstance(route, Mapping) or route.get('attachment_mode') != 'embedded':
        raise RelationalClientError('Local Firebird services require the embedded profile')
    if any(route.get(key) for key in ('credential_reference_id', 'credential_references', 'credential_kinds')):
        raise RelationalClientError('Local Firebird services do not acquire network credentials')
    value = embedded_route(route, permissions)
    if not Path(value['database']).is_file():
        raise RelationalClientError('Local database services require an existing approved file')
    return value


def validate_operation(route, operation, database, options):
    if operation not in OPERATIONS:
        raise RelationalClientError('This embedded local service operation is not implemented')
    if not isinstance(options, Mapping) or set(options) - (LOCAL_OPTIONS[operation] | {'role'}):
        raise RelationalClientError('Select typed local database service options')
    if 'confirmation' in options and not isinstance(options['confirmation'], str):
        raise RelationalClientError('Confirmation must be text')
    if operation == 'activate_shadow':
        from ..embedded_route import contained_database
        from .shadow_activation import validate
        if not isinstance(route, Mapping):
            raise RelationalClientError('Local recovery requires an approved embedded route')
        # The primary can be absent or its old parent removed. Authorize its
        # stored path lexically, then admit only the existing recovery target.
        original = contained_database(route)
        values = validate(options, original)
        selected = route_for_service({**route, 'database': values['shadow_filename']})
        if selected['database'] != values['shadow_filename']:
            raise RelationalClientError('Select the canonical absolute shadow filename')
        if Path(original).exists() and os.path.samefile(original, selected['database']):
            raise RelationalClientError('The shadow target must not be the original database inode')
    else:
        selected = route_for_service(route)
    if operation == 'database_statistics':
        from .statistics import validate_options
        validate_options(options)
    else:
        from ..relational_admin import RelationalAdministration
        errors = RelationalAdministration._validate_firebird_service(operation, options)
        for field in LOCAL_OPTIONS[operation] & {'page_buffers', 'sweep_interval'}:
            if options.get(field) is None:
                raise RelationalClientError('A local service requires ' + field)
        if errors:
            raise RelationalClientError(errors[0]['message'])
        if sys.platform != 'linux':
            raise RelationalClientError('Local administration file pinning is qualified on Linux only')
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
_MAINTENANCE_PROBE = ContextVar('firebird_local_maintenance_probe', default=False)
_ADMISSION_LOCK = RLock()
_ADMISSIONS = WeakValueDictionary()


def maintenance_probe_active():
    return _MAINTENANCE_PROBE.get()


@contextmanager
def attachment_admission(route):
    """Do not let a new managed SQL attachment adopt a private service alias."""
    if route.get('attachment_mode') != 'embedded':
        yield
        return
    identity = file_identity(route)
    key = (identity['device'], identity['inode'])
    with _ADMISSION_LOCK:
        lock = _ADMISSIONS.get(key)
        if lock is None:
            lock = RLock()
            _ADMISSIONS[key] = lock
    with lock:
        yield


@contextmanager
def service_filename(client, route, reviewed, operation, options):
    """Keep native filename semantics for caches and auxiliary files.

    Private aliases are restricted to short header operations on a database
    with no linger or auxiliary files. Canonical operations retain/recheck
    the reviewed descriptor but do not claim an OS rename race fence.
    """
    if operation == 'activate_shadow':
        # An SQL probe could itself activate/open a recovery file. Activation
        # must keep the canonical native filename, including persistent LINGER
        # and any auxiliary-file references inherited from the primary.
        with attachment_admission(route), pinned_target(route, reviewed, operation, private_alias=False):
            yield False
        return
    if operation == 'fixup_database':
        # NFIX writes raw header pages. Never attach the copied database as
        # a preflight: that could create a delta file before fixup. Hold new
        # managed SQL admission, without claiming external file exclusivity.
        with attachment_admission(route), pinned_target(route, reviewed, operation):
            yield True
        return
    if operation == 'database_statistics':
        with pinned_target(route, reviewed, operation):
            yield sys.platform == 'linux'
        return
    private = False
    with attachment_admission(route):
        if operation not in {'sweep_database', 'validate_database'}:
            scoped, _ = client._service_role_scope({'route': route}, options)
            token = _MAINTENANCE_PROBE.set(True)
            connection = None
            failure = None
            try:
                probe = dict(scoped['route'], transaction_access='READ',
                             transaction_isolation='SNAPSHOT',
                             transaction_auto_commit=False,
                             transaction_no_auto_undo=False,
                             transaction_ignore_limbo=False)
                connection = client._connect({'route': probe})
                import firebird.driver as native
                actual = connection.info.get_info(native.DbInfoCode.DB_FILE_ID)
                expected = (int(reviewed['device']).to_bytes(8, sys.byteorder) +
                            int(reviewed['inode']).to_bytes(8, sys.byteorder)).hex()
                if actual.lower() != expected:
                    error = RelationalClientError('Native maintenance file differs from reviewed file')
                    error.rejected = error.nothing_changed = True
                    error.native_dispatched = error.automatic_retry = False
                    raise error
                cursor = connection.cursor()
                try:
                    cursor.execute('SELECT COALESCE(RDB$LINGER,0) FROM RDB$DATABASE')
                    linger = cursor.fetchone()[0]
                    cursor.execute('SELECT MON$BACKUP_STATE FROM MON$DATABASE')
                    backup = cursor.fetchone()[0]
                    cursor.execute('SELECT COUNT(*) FROM RDB$FILES')
                    auxiliary = cursor.fetchone()[0]
                    private = linger == 0 and backup == 0 and auxiliary == 0
                finally:
                    cursor.close()
            except RelationalClientError as error:
                failure = error
                # FULL/SINGLE shutdown must not strand attachment-free recovery.
                # An observed identity mismatch is never a fallback condition.
                if str(error).startswith('Native maintenance file differs'):
                    raise
            finally:
                _MAINTENANCE_PROBE.reset(token)
                if connection is not None:
                    client._finish_temporary_attachment(connection, failure)
        if private:
            with pinned_target(route, reviewed, operation):
                yield True
            return
    # Long online work must not hold SQL admission for its whole duration.
    with pinned_target(route, reviewed, operation, private_alias=False):
        yield False


@contextmanager
def pinned_target(route, reviewed, operation='database_statistics', *, private_alias=True):
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
        if not private_alias:
            if file_identity(route) != reviewed:
                raise RelationalClientError('Local database file changed before native service dispatch')
            token = _SERVICE_TARGET.set((original, original))
            entered = True
            yield original
            return
        # Native gstat canonicalizes descriptor symlinks. A private hardlink
        # instead gives it a stable native filename for this exact inode.
        # Verify after link creation: linking a raced same-name replacement
        # must never authorize that replacement. Engine13 identifies database
        # locks by native file identity, including hardlinks. Mutation adapters
        # are separately qualified with an active original-path attachment.
        prefix = ('.scratchrobin-statistics-' if operation == 'database_statistics'
                  else '.scratchrobin-local-service-')
        alias_area = tempfile.TemporaryDirectory(prefix=prefix,dir=str(Path(original).parent))
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

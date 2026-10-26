"""Provider-owned MySQL leases, without Connector/Python's global pools."""
import hashlib
import hmac
import json
import secrets
import threading
import weakref
from contextlib import nullcontext

from pgadmin.cdeadmin.sdk import RelationalClientError


POOL_ARGUMENTS = frozenset({
    'pool_name', 'pool_size', 'pool_reset_session',
})


class PoolUnavailable(RelationalClientError):
    """A target's provider-owned pool has no available lease."""


def _close(connection):
    try:
        connection.close()
    except Exception:
        pass


def live_sql_mode_conversion(native):
    """Use native OK/EOF status for escaping after SQL changes session mode.

    The pure client caches sql_mode while arbitrary SET SQL updates protocol
    status without refreshing that cache. Preserve the native converter's
    types/charset and choose escaping from live status. C clients already do
    this. Only a fixed initial metadata read is sent; no session setting changes.
    """
    converter=getattr(native,'converter',None)
    handler=getattr(type(native),'_handle_server_status',None)
    if converter is None or getattr(native,'_cmysql',None) is not None or not callable(handler):return
    from mysql.connector.constants import ServerFlag
    reference=weakref.ref(native)
    def observe_status(flags):
        connection=reference()
        if connection is None:raise RelationalClientError('MySQL protocol connection is unavailable')
        connection._cdeadmin_server_status=flags
        return handler(connection,flags)
    # The pure driver keeps only selected flags itself. Observe the complete
    # decoded status while preserving its native transaction/result handling.
    native._handle_server_status=observe_status
    cursor=native.cursor()
    try:
        cursor.execute('SELECT @@SESSION.sql_mode');cursor.fetchall()
    finally:cursor.close()
    if not isinstance(getattr(native,'_cdeadmin_server_status',None),int):
        raise RelationalClientError('Native MySQL SQL-mode status is unavailable')
    class LiveSQLModeConverter(type(converter)):
        def escape(self,value,sql_mode=None):
            connection=reference()
            if connection is None:raise RelationalClientError('MySQL parameter connection is unavailable')
            selected = getattr(connection, '_cdeadmin_parameter_sql_mode', None)
            sql_mode = selected if isinstance(selected, str) else ('NO_BACKSLASH_ESCAPES' if connection._cdeadmin_server_status & ServerFlag.STATUS_NO_BACKSLASH_ESCAPES else '')
            escaped=super().escape(value,sql_mode)
            # Connector/Python26.7 leaves raw NUL in this text-protocol path.
            # Native routine definitions cannot retain that source byte.
            if not sql_mode:
                if isinstance(escaped,(bytes,bytearray)) and b'\x00' in escaped:return escaped.replace(b'\x00',b'\\0')
                if isinstance(escaped,str) and '\x00' in escaped:return escaped.replace('\x00','\\0')
            return escaped
    native.set_converter_class(LiveSQLModeConverter)


class Lease:
    """A closed lease cannot reach a connection that has been lent again."""

    def __init__(self, pool, native):
        object.__setattr__(self, '_pool', pool)
        object.__setattr__(self, '_native', native)

    def __getattr__(self, name):
        native = self._native
        if native is None:
            raise RelationalClientError('MySQL connection lease is closed')
        return getattr(native, name)

    def __setattr__(self, name, value):
        if self._native is None:
            raise RelationalClientError('MySQL connection lease is closed')
        setattr(self._native, name, value)

    def close(self):
        native = self._native
        if native is not None:
            object.__setattr__(self, '_native', None)
            if getattr(native, '_cdeadmin_temporary_management_used', False) is True:
                self._pool.discard(native)
            else:
                self._pool.release(native)

    def discard(self):
        native = self._native
        if native is not None:
            object.__setattr__(self, '_native', None)
            self._pool.discard(native)


class _Pool:
    def __init__(self, connect, size, reset):
        self.connect = connect
        self.size = size
        self.reset = reset
        self.idle = []
        self.count = 0
        self.retired = False
        self.lock = threading.RLock()

    def checkout(self, options):
        with self.lock:
            if self.retired:
                raise RelationalClientError('MySQL pool has been retired')
            while self.idle:
                native = self.idle.pop()
                try:
                    native.ping(reconnect=False)
                except Exception:
                    self.discard(native)
                    continue
                return Lease(self, native)
            if self.count >= self.size:
                raise PoolUnavailable('MySQL connection pool exhausted')
            native = self.connect(**options)
            self.count += 1
            return Lease(self, native)

    def discard(self, native):
        with self.lock:
            try:
                _close(native)
            finally:
                self.count -= 1

    def release(self, native):
        with self.lock:
            if self.retired:
                self.discard(native)
                return
            try:
                native.rollback()
                if self.reset:
                    native.reset_session()
            except BaseException:
                self.discard(native)
                raise
            self.idle.append(native)

    def close(self):
        with self.lock:
            self.retired = True
            while self.idle:
                self.discard(self.idle.pop())


class Connector:
    """Configuration generations are private to this provider instance."""

    def __init__(self, module, secret_acquirer=None):
        self.module = module
        self.secret_acquirer = secret_acquirer
        self._key = secrets.token_bytes(32)
        self._pools = {}
        self._lock = threading.RLock()
        self._closed = False

    def __call__(self, *args, **kwargs):
        return self.connect(None, *args, **kwargs)

    def connect(self, principal, *args, **kwargs):
        if 'failover' not in kwargs:
            return self._checkout(None, args, kwargs)
        options = dict(kwargs)
        targets = options.pop('failover')
        if args or not isinstance(targets, (tuple, list)) or not targets or len(targets) > 128:
            raise RelationalClientError('Select a bounded native failover target list')
        allowed = {'host', 'port', 'unix_socket', 'user', 'database', 'priority',
                   'pool_name', 'pool_size', 'pool_reset_session', 'credential_reference_id', 'credential_kind'}
        validated = []
        for index, target in enumerate(targets):
            if not isinstance(target, dict) or set(target) - allowed:
                raise RelationalClientError('Unknown failover option; use protected credential references')
            selected = dict(target)
            priority = selected.pop('priority', 100)
            if type(priority) is not int or not 0 <= priority <= 100:
                raise RelationalClientError('Failover priority must be 0 through 100')
            reference = selected.pop('credential_reference_id', None)
            kind = selected.pop('credential_kind', 'database_password')
            if kind not in {'database_password', 'password'} or reference is not None and (
                    not isinstance(reference, str) or not reference or not principal or not callable(self.secret_acquirer)):
                raise RelationalClientError('Protected failover credentials are unavailable')
            validated.append((priority, index, selected, reference, kind))
        # Native priority order, with randomized selection without replacement
        # among equals. Configuration/secret failures never become fallback.
        validated.sort(key=lambda row: (-row[0], secrets.randbits(128)))
        for _priority, index, target, reference, kind in validated:
            selected = {**options, **target}
            lease = self.secret_acquirer(reference, principal, 'connect', kind) if reference is not None else nullcontext()
            with lease as password:
                try:
                    if reference is None:
                        connection = self._checkout((principal, index), (), selected)
                    else:
                        connection = password.use(lambda value: self._checkout((principal, index), (), {
                            **selected, 'password': bytes(value).decode('utf8')}))
                    # A retained session's observer/cancellation peers must use
                    # this target's principal and reference, not the root login.
                    connection._cdeadmin_failover_target = {**target,
                        **({'credential_reference_id': reference, 'credential_kind': kind} if reference is not None else {})}
                    return connection
                except (self.module.Error, PoolUnavailable):
                    continue
        raise self.module.InterfaceError('Unable to connect to any selected failover target')

    def _checkout(self, scope, args, kwargs):
        options = dict(kwargs)
        size = options.pop('pool_size', None)
        name = options.pop('pool_name', 'default')
        reset = options.pop('pool_reset_session', True)
        if size is not None and (type(size) is not int or not 1 <= size <= 32):
            raise RelationalClientError('MySQL pool size must be 1 through 32')
        if type(reset) is not bool:
            raise RelationalClientError('MySQL pool reset must be Boolean')
        if not isinstance(name, str) or not name:
            raise RelationalClientError('MySQL pool name is invalid')
        name = (scope, name)
        with self._lock:
            if self._closed:
                raise RelationalClientError('MySQL connector is closed')
            if size is None:
                return self._native_connect(*args, **options)
            if args:
                raise RelationalClientError(
                    'MySQL pooled connections require named arguments')
            # Only the keyed digest survives checkout. Current native options
            # (including acquired secrets) are not stored by this pool owner.
            signature = hmac.new(self._key, json.dumps(
                [size, reset, options], sort_keys=True,
                ensure_ascii=True).encode('ascii'), hashlib.sha256).digest()
            previous = self._pools.get(name)
            if previous is None or previous[0] != signature:
                if previous is not None:
                    previous[1].close()
                pool = _Pool(self._native_connect, size, reset)
                self._pools[name] = (signature, pool)
            else:
                pool = previous[1]
            return pool.checkout(options)

    def _native_connect(self,*args,**options):
        attribute = None
        if getattr(self.module, '__name__', '').startswith('mysql.connector'):
            attributes = dict(options.get('conn_attrs') or {})
            key = 'scratchrobin_' + secrets.token_hex(8)
            while key in attributes:
                key = 'scratchrobin_' + secrets.token_hex(8)
            attribute = {'name': key, 'value': secrets.token_hex(24)}
            options['conn_attrs'] = {**attributes, key: attribute['value']}
        if options.get('use_pure') is True and getattr(self.module,'__name__','').startswith('mysql.connector'):
            from mysql.connector.constants import ClientFlag
            flags=options.get('client_flags')
            options['client_flags']=[*flags,ClientFlag.SESSION_TRACK] if isinstance(flags,(tuple,list)) else (ClientFlag.get_default() if flags is None else flags)|ClientFlag.SESSION_TRACK
        from .mysql_recovery_bridge import native_connection
        native=native_connection(self.module.connect,args,options)
        try:
            if attribute is not None:
                native._cdeadmin_observer_attribute = attribute
            live_sql_mode_conversion(native)
            from .mysql_charsets import install
            install(native)
        except BaseException:
            _close(native)
            raise
        return native

    def close(self):
        with self._lock:
            self._closed = True
            for _signature, pool in self._pools.values():
                pool.close()
            self._pools.clear()


def discard(connection):
    """Failed initialization must never return partially configured state."""
    if isinstance(connection, Lease):
        connection.discard()
    else:
        _close(connection)

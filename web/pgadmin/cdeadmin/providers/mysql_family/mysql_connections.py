"""Provider-owned MySQL leases, without Connector/Python's global pools."""
import hashlib
import hmac
import json
import secrets
import threading
import weakref

from pgadmin.cdeadmin.sdk import RelationalClientError


POOL_ARGUMENTS = frozenset({
    'pool_name', 'pool_size', 'pool_reset_session',
})


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
            sql_mode='NO_BACKSLASH_ESCAPES' if connection._cdeadmin_server_status & ServerFlag.STATUS_NO_BACKSLASH_ESCAPES else ''
            return super().escape(value,sql_mode)
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
                raise RelationalClientError('MySQL connection pool exhausted')
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

    def __init__(self, module):
        self.module = module
        self._key = secrets.token_bytes(32)
        self._pools = {}
        self._lock = threading.RLock()
        self._closed = False

    def __call__(self, *args, **kwargs):
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
        if options.get('use_pure') is True and getattr(self.module,'__name__','').startswith('mysql.connector'):
            from mysql.connector.constants import ClientFlag
            flags=options.get('client_flags')
            options['client_flags']=[*flags,ClientFlag.SESSION_TRACK] if isinstance(flags,(tuple,list)) else (ClientFlag.get_default() if flags is None else flags)|ClientFlag.SESSION_TRACK
        native=self.module.connect(*args,**options)
        try:
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

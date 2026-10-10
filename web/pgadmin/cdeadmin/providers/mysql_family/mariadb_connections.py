"""Provider-owned MariaDB leases, without Connector/Python's global pools."""
import hashlib
import hmac
import json
import secrets
import threading
import time

from pgadmin.cdeadmin.sdk import RelationalClientError


POOL_ARGUMENTS = frozenset({
    'pool_name', 'pool_size', 'pool_reset_connection',
    'pool_validation_interval',
})


def _close(connection):
    try:
        connection.close()
    except Exception:
        pass


class Lease:
    """A closed lease cannot reach a connection that has been lent again."""

    def __init__(self, pool, native):
        object.__setattr__(self, '_pool', pool)
        object.__setattr__(self, '_native', native)

    def __getattr__(self, name):
        native = self._native
        if native is None:
            raise RelationalClientError('MariaDB connection lease is closed')
        return getattr(native, name)

    def __setattr__(self, name, value):
        if self._native is None:
            raise RelationalClientError('MariaDB connection lease is closed')
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
    def __init__(self, connect, size, reset, interval):
        self.connect = connect
        self.size = size
        self.reset = reset
        self.interval = interval / 1000
        self.idle = []
        self.defaults = {}
        self.count = 0
        self.retired = False
        self.lock = threading.RLock()

    def checkout(self, options):
        with self.lock:
            if self.retired:
                raise RelationalClientError('MariaDB pool has been retired')
            while self.idle:
                native, returned = self.idle.pop()
                try:
                    if time.monotonic() - returned >= self.interval:
                        native.ping()
                    if self.reset:
                        database, autocommit = self.defaults[id(native)]
                        if database != native.database:
                            if not database:
                                self.discard(native)
                                continue
                            native.database = database
                        if type(autocommit) is bool:
                            # COM_RESET_CONNECTION can leave cached status
                            # stale; the property setter may skip the command.
                            cursor = native.cursor()
                            try:
                                cursor.execute('SET autocommit = ' +
                                               ('1' if autocommit else '0'))
                            finally:
                                cursor.close()
                        if options.get('init_command'):
                            cursor = native.cursor()
                            try:
                                cursor.execute(options['init_command'])
                            finally:
                                cursor.close()
                except Exception:
                    self.discard(native)
                    continue
                return Lease(self, native)
            if self.count >= self.size:
                raise RelationalClientError(
                    'MariaDB connection pool exhausted')
            native = self.connect(**options)
            try:
                self.defaults[id(native)] = (
                    native.database, native.autocommit)
            except BaseException:
                _close(native)
                raise
            self.count += 1
            return Lease(self, native)

    def discard(self, native):
        with self.lock:
            try:
                _close(native)
            finally:
                self.defaults.pop(id(native), None)
                self.count -= 1

    def release(self, native):
        with self.lock:
            if self.retired:
                self.discard(native)
                return
            try:
                native.rollback()
                if self.reset:
                    native.reset()
            except BaseException:
                self.discard(native)
                raise
            self.idle.append((native, time.monotonic()))

    def close(self):
        with self.lock:
            self.retired = True
            while self.idle:
                self.discard(self.idle.pop()[0])


class Connector:
    """Configuration generations are private to this provider instance."""

    _POOL_ARGUMENTS = POOL_ARGUMENTS

    def __init__(self, module, pool_namespace=None):
        self.module = module
        self._key = secrets.token_bytes(32)
        self._pools = {}
        self._lock = threading.RLock()
        self._closed = False

    def __call__(self, *args, **kwargs):
        options = dict(kwargs)
        if options.get('reconnect'):
            raise RelationalClientError(
                'MariaDB automatic reconnect is not admitted '
                'for retained work')
        interval = options.pop('pool_validation_interval', 500)
        if type(interval) is not int or interval < 0:
            raise RelationalClientError(
                'MariaDB pool validation interval must be nonnegative')
        size = options.pop('pool_size', None)
        name = options.pop('pool_name', 'default')
        reset = options.pop('pool_reset_connection', True)
        if size is not None and (type(size) is not int or not 1 <= size <= 64):
            raise RelationalClientError(
                'MariaDB pool size must be 1 through 64')
        if type(reset) is not bool:
            raise RelationalClientError('MariaDB pool reset must be Boolean')
        if not isinstance(name, str) or not name:
            raise RelationalClientError('MariaDB pool name is invalid')
        with self._lock:
            if self._closed:
                raise RelationalClientError('MariaDB connector is closed')
            if size is None:
                return self.module.connect(*args, **options)
            if args:
                raise RelationalClientError(
                    'MariaDB pooled connections require named arguments')
            # Only the keyed digest survives checkout. Current native options
            # (including acquired secrets) are not stored by this pool owner.
            signature = hmac.new(self._key, json.dumps(
                [size, reset, interval, options], sort_keys=True,
                ensure_ascii=True).encode('ascii'), hashlib.sha256).digest()
            previous = self._pools.get(name)
            if previous is None or previous[0] != signature:
                if previous is not None:
                    previous[1].close()
                pool = _Pool(self.module.connect, size, reset, interval)
                self._pools[name] = (signature, pool)
            else:
                pool = previous[1]
            return pool.checkout(options)

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

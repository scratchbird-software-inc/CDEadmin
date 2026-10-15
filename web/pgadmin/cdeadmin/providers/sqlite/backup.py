"""SQLite online backup with validated, atomic artifact publication."""
import math
import os
import sqlite3
import stat
import tempfile
import time
from urllib.parse import quote

from pgadmin.cdeadmin.sdk import RelationalClientError
from ..embedded_route import contained_database


def database_operation(connection, route, operation, options):
    try:
        return _database_operation(connection, route, operation, options)
    except sqlite3.Error as exc:
        code = getattr(exc, 'sqlite_errorcode', None)
        name = getattr(exc, 'sqlite_errorname', type(exc).__name__)
        raise RelationalClientError(
            f'SQLite {operation} failed ({name}, code={code})') from None


def _database_operation(connection, route, operation, options):
    if operation not in {'backup', 'restore'}:
        raise RelationalClientError('SQLite database operation is unknown')
    if connection.in_transaction:
        raise RelationalClientError(
            'commit or roll back the SQLite transaction before this operation')
    timeout = options.get('backup_timeout', 30)
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or
            not math.isfinite(timeout) or not 0 < timeout <= 3600):
        raise RelationalClientError(
            'SQLite backup timeout must be 0 to 3600 seconds')
    active = contained_database(route)
    target_route = dict(route, database=options.get('backup_path'))
    target = contained_database(target_route)
    if target == ':memory:' or target == active or (
            active != ':memory:' and os.path.exists(target) and
            os.path.samefile(active, target)):
        raise RelationalClientError(
            'SQLite backup and active files must differ')
    if os.path.islink(options['backup_path']):
        raise RelationalClientError(
            'SQLite backup path cannot be a symbolic link')
    if os.path.lexists(target) and not stat.S_ISREG(os.lstat(target).st_mode):
        raise RelationalClientError(
            'SQLite backup path must be a regular file')
    deadline = time.monotonic() + timeout

    def progress(status, _remaining, _total):
        if status != sqlite3.SQLITE_DONE and time.monotonic() >= deadline:
            raise TimeoutError('SQLite backup deadline expired')

    def transfer(source, destination):
        try:
            source.backup(destination, pages=128, progress=progress, sleep=.01)
        except sqlite3.Error as exc:
            code = getattr(exc, 'sqlite_errorcode', 0) & 255
            if operation == 'restore' and code in {
                    sqlite3.SQLITE_IOERR, sqlite3.SQLITE_CORRUPT,
                    sqlite3.SQLITE_NOTADB, sqlite3.SQLITE_PROTOCOL}:
                error = RelationalClientError(
                    'SQLite restore state is unknown; close the session')
                error.session_reuse_blocked = True
                raise error from None
            raise

    if operation == 'restore':
        if (route.get('read_only') or route.get('uri_mode') == 'ro' or
                route.get('uri_immutable')):
            raise RelationalClientError(
                'SQLite read-only routes cannot restore')
        if not os.path.isfile(target):
            raise RelationalClientError('SQLite restore source does not exist')
        with open(target, 'rb') as stream:
            if stream.read(16) != b'SQLite format 3\x00':
                raise RelationalClientError(
                    'SQLite restore source has no SQLite header')
        uri = 'file:' + quote(target, safe='/') + '?mode=ro'
        source = sqlite3.connect(uri, uri=True)
        try:
            if source.execute('PRAGMA quick_check(1)').fetchone() != ('ok',):
                raise RelationalClientError(
                    'SQLite restore source failed quick_check')
            transfer(source, connection)
        finally:
            source.close()
        observed = connection.execute('PRAGMA quick_check(1)').fetchone()
        if observed != ('ok',):
            raise RelationalClientError(
                'SQLite restored database failed quick_check')
        return {'operation': 'sqlite-online-restore', 'backup_path': target,
                'quick_check': 'ok', 'driver_returned': True}

    overwrite = options.get('overwrite', False)
    if type(overwrite) is not bool:
        raise RelationalClientError('SQLite overwrite must be true or false')
    if os.path.lexists(target) and not overwrite:
        raise RelationalClientError(
            'SQLite backup exists and overwrite is disabled')
    if any(os.path.lexists(target + suffix)
           for suffix in ('-journal', '-wal', '-shm')):
        raise RelationalClientError(
            'SQLite backup destination has journal sidecars')
    before = os.stat(target) if os.path.exists(target) else None
    descriptor, staging = tempfile.mkstemp(prefix='.cdeadmin-backup-',
                                           dir=os.path.dirname(target))
    os.close(descriptor)
    destination = None
    try:
        destination = sqlite3.connect(staging)
        transfer(connection, destination)
        if destination.execute('PRAGMA quick_check(1)').fetchone() != ('ok',):
            raise RelationalClientError(
                'SQLite backup did not pass quick_check')
        destination.close()
        destination = None
        # Windows _commit (used by fsync) requires a writable handle.
        # This is our closed, validated staging file, before publication.
        with open(staging, 'r+b') as stream:
            os.fsync(stream.fileno())
        if overwrite:
            current = os.lstat(target) if os.path.lexists(target) else None

            def identity(item):
                return (item.st_dev, item.st_ino) if item else None
            if identity(before) != identity(current):
                raise RelationalClientError(
                    'SQLite backup destination changed')
            os.replace(staging, target)
        else:
            # Atomic exclusive publication. Unlike replace(), this cannot
            # overwrite a file created after the earlier existence check.
            if os.name == 'nt':
                # Windows rename refuses an existing destination atomically.
                os.rename(staging, target)
            else:
                os.link(staging, target)
        return {'operation': 'sqlite-online-backup', 'backup_path': target,
                'bytes': os.path.getsize(target), 'quick_check': 'ok',
                'driver_returned': True, 'atomic_publication': True}
    finally:
        if destination is not None:
            destination.close()
        for suffix in ('', '-journal', '-wal', '-shm'):
            try:
                os.unlink(staging + suffix)
            except FileNotFoundError:
                pass

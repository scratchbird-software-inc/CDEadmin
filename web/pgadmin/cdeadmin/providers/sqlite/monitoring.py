"""Dedicated SQLite file probes using short independent read transactions."""

from datetime import datetime, timezone
import os
import uuid

from ..embedded_route import contained_database
from .provider import PROFILE, _create_client
from pgadmin.cdeadmin.sdk import RelationalClientError


class SQLiteMonitor:
    def __init__(self, route, *, target_id, metadata_interval_seconds=60):
        path = contained_database(route)
        if path == ':memory:':
            raise RelationalClientError(
                'Independent :memory: monitoring observes a different SQLite database')
        if not os.path.isfile(path):
            raise RelationalClientError('Registered SQLite monitoring file does not exist')
        self.route = dict(route)
        self.path = path
        self.target_id = target_id
        self.metadata_interval_seconds = metadata_interval_seconds
        self._client = _create_client()
        self._connection = None
        self._epoch = str(uuid.uuid4())

    def _open(self):
        if self._connection is None:
            self._connection = self._client._connect({'route': self.route})
        return self._connection

    def sample(self):
        connection = self._open()
        active = False
        try:
            connection.execute('BEGIN')
            active = True
            database = next((row for row in connection.execute(
                'PRAGMA database_list') if row[1] == 'main'), None)
            if database is None or os.path.realpath(database[2]) != self.path:
                raise ValueError('SQLite monitoring connection changed file identity')
            version = connection.execute('SELECT sqlite_version()').fetchone()[0]
            if not PROFILE.accepts_runtime_version(version):
                raise ValueError(
                    'SQLite monitoring runtime is outside the supported '
                    f'{PROFILE.version_requirement} range')
            def scalar(name):
                row = connection.execute('PRAGMA main.' + name).fetchone()
                if row is None:
                    raise ValueError('SQLite monitoring PRAGMA is unavailable')
                return row[0]
            page_size = int(scalar('page_size'))
            page_count = int(scalar('page_count'))
            free_pages = int(scalar('freelist_count'))
            journal_mode = str(scalar('journal_mode'))
            schema_version = int(scalar('schema_version'))
            user_version = int(scalar('user_version'))
            connection.execute('ROLLBACK')
            active = False
            return {
                'status': 'available', 'scope': 'database',
                'sample_id': str(uuid.uuid4()), 'source_epoch': self._epoch,
                'ended_at': datetime.now(timezone.utc).isoformat(),
                'identity': {'database_name': os.path.basename(self.path),
                             'version': version, 'target_id': self.target_id,
                             'engine_id': 'sqlite'},
                'groups': {
                    'storage': {'status': 'available', 'rows': [{
                        'page_size_bytes': page_size,
                        'page_count': page_count,
                        'freelist_pages': free_pages,
                        'logical_size_bytes': page_size * page_count,
                        'free_space_bytes': page_size * free_pages,
                        'file_size_bytes': os.path.getsize(self.path)}]},
                    'database': {'status': 'available', 'rows': [{
                        'journal_mode': journal_mode,
                        'schema_version': schema_version,
                        'user_version': user_version,
                        'read_only_route': self.route.get('read_only') is True}]},
                },
                'transaction_refresh': {'status': 'completed',
                    'action': 'read-only-native-transaction-rolled-back'},
                'limitations': [
                    'No remote server load or global user-session metrics are exposed.',
                    'Connection-local temporary objects and settings are not visible.'],
            }
        except BaseException:
            if active:
                try:
                    connection.execute('ROLLBACK')
                except Exception:
                    pass
            self._retire()
            raise

    def _retire(self):
        connection, self._connection = self._connection, None
        if connection is not None:
            self._client._discard_failed_session(connection)
        self._client.close()
        self._client = _create_client()
        self._epoch = str(uuid.uuid4())

    def close(self):
        connection, self._connection = self._connection, None
        if connection is not None:
            self._client._discard_failed_session(connection)
        self._client.close()

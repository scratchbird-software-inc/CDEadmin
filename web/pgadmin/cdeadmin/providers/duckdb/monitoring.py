"""Dedicated DuckDB file probes; each refresh owns a short native transaction."""

from datetime import datetime, timezone
import os
import uuid

from ..embedded_route import contained_database
from .provider import _create_client
from pgadmin.cdeadmin.sdk import RelationalClientError


class DuckDBMonitor:
    def __init__(self, route, *, target_id, metadata_interval_seconds=60):
        path = contained_database(route)
        if path == ':memory:':
            raise RelationalClientError('Independent :memory: monitoring observes a different database')
        if not os.path.isfile(path):
            raise RelationalClientError('Registered DuckDB monitoring file does not exist')
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
            connection.execute('BEGIN TRANSACTION')
            active = True
            connection.execute('SELECT current_database(), version()')
            catalog, version = connection.fetchone()
            connection.execute('SELECT database_name, database_size, block_size, '
                'total_blocks, used_blocks, free_blocks, memory_usage, memory_limit '
                'FROM pragma_database_size() WHERE database_name=?', [catalog])
            size = connection.fetchone()
            if size is None:
                raise ValueError('DuckDB native database size is unavailable')
            connection.execute('SELECT readonly, encrypted, cipher FROM duckdb_databases() '
                'WHERE database_name=? AND NOT internal', [catalog])
            state = connection.fetchone()
            if state is None:
                raise ValueError('DuckDB native database identity is unavailable')
            connection.execute('SELECT COUNT(*), SUM(CASE WHEN installed THEN 1 ELSE 0 END), '
                'SUM(CASE WHEN loaded THEN 1 ELSE 0 END) FROM duckdb_extensions()')
            extensions = connection.fetchone()
            connection.execute('ROLLBACK'); active = False
            return {
                'status': 'available', 'scope': 'database',
                'sample_id': str(uuid.uuid4()), 'source_epoch': self._epoch,
                'ended_at': datetime.now(timezone.utc).isoformat(),
                'identity': {'database_name': catalog, 'version': version,
                             'target_id': self.target_id, 'engine_id': 'duckdb'},
                'groups': {
                    'storage': {'status': 'available', 'rows': [{
                        'database_name': size[0], 'database_size': size[1],
                        'block_size': size[2], 'total_blocks': size[3],
                        'used_blocks': size[4], 'free_blocks': size[5],
                        'memory_usage': size[6], 'memory_limit': size[7]}]},
                    'database': {'status': 'available', 'rows': [{
                        'read_only': bool(state[0]), 'encrypted': bool(state[1]),
                        'cipher': state[2]}]},
                    'extensions': {'status': 'available', 'rows': [{
                        'available': extensions[0], 'installed': extensions[1] or 0,
                        'loaded': extensions[2] or 0}]},
                },
                'transaction_refresh': {'status': 'completed',
                    'action': 'read-only-native-transaction-rolled-back'},
                'limitations': ['No remote server load or global user-session metrics are exposed.',
                    'Temporary objects and settings on other connections are not visible.'],
            }
        except BaseException:
            # A failed refresh cannot become an availability heartbeat.
            if active:
                try: connection.execute('ROLLBACK')
                except Exception: pass
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

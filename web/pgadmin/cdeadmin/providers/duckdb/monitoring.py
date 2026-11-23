"""Dedicated DuckDB file probes; each refresh owns a short native transaction (DU-AUD-40)."""

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

            connection.execute(
                'SELECT database_name, database_size, block_size, total_blocks, '
                'used_blocks, free_blocks, wal_size, memory_usage, memory_limit '
                'FROM pragma_database_size() WHERE database_name=?',
                [catalog],
            )
            size = connection.fetchone()
            if size is None:
                raise ValueError('DuckDB native database size is unavailable')

            connection.execute(
                'SELECT database_name, database_oid, path, comment, tags, internal, '
                'type, readonly, encrypted, cipher, options '
                'FROM "system"."main".duckdb_databases() '
                'WHERE NOT internal ORDER BY database_name LIMIT 256'
            )
            db_rows = connection.fetchall()
            primary_db = next((r for r in db_rows if r[0] == catalog), None)
            if primary_db is None:
                raise ValueError('DuckDB native database identity is unavailable')

            connection.execute(
                'SELECT COUNT(*), '
                'SUM(CASE WHEN installed THEN 1 ELSE 0 END), '
                'SUM(CASE WHEN loaded THEN 1 ELSE 0 END) '
                'FROM "system"."main".duckdb_extensions()'
            )
            extensions = connection.fetchone()

            approx_db_count = int(connection.execute(
                'SELECT COALESCE(SUM(approx_count), 0) FROM "system"."main".duckdb_approx_database_count()'
            ).fetchone()[0])

            connection_count = int(connection.execute(
                'SELECT COALESCE(SUM(count), 0) FROM "system"."main".duckdb_connection_count()'
            ).fetchone()[0])

            memory_rows = connection.execute(
                'SELECT tag, memory_usage_bytes, temporary_storage_bytes '
                'FROM "system"."main".duckdb_memory() ORDER BY tag LIMIT 256'
            ).fetchall()
            memory_usage_total = sum(int(r[1] or 0) for r in memory_rows)
            temp_storage_total = sum(int(r[2] or 0) for r in memory_rows)

            temp_file_rows = connection.execute(
                'SELECT path, size FROM "system"."main".duckdb_temporary_files() '
                'ORDER BY path LIMIT 256'
            ).fetchall()
            temp_files_total = int(connection.execute(
                'SELECT COALESCE(SUM(size), 0) FROM "system"."main".duckdb_temporary_files()'
            ).fetchone()[0])

            cache_rows = connection.execute(
                'SELECT path, nr_bytes, location, loaded '
                'FROM "system"."main".duckdb_external_file_cache() ORDER BY path LIMIT 256'
            ).fetchall()
            cache_bytes_total = int(connection.execute(
                'SELECT COALESCE(SUM(nr_bytes), 0) FROM "system"."main".duckdb_external_file_cache()'
            ).fetchone()[0])

            meta_totals = connection.execute(
                'SELECT COALESCE(SUM(total_blocks), 0), COALESCE(SUM(free_blocks), 0) '
                'FROM pragma_metadata_info()'
            ).fetchone()
            meta_rows = connection.execute(
                'SELECT block_id, total_blocks, free_blocks, list_count(free_list) '
                'FROM pragma_metadata_info() LIMIT 256'
            ).fetchall()

            platform = connection.execute('PRAGMA platform').fetchone()[0]
            user_agent = connection.execute('PRAGMA user_agent').fetchone()[0]
            ver_row = connection.execute('SELECT library_version, source_id, codename FROM pragma_version()').fetchone()

            prep_rows = connection.execute(
                'SELECT name, parameter_types, result_types '
                'FROM "system"."main".duckdb_prepared_statements() ORDER BY name LIMIT 64'
            ).fetchall()
            var_rows = connection.execute(
                'SELECT name, type FROM "system"."main".duckdb_variables() ORDER BY name LIMIT 64'
            ).fetchall()
            log_ctx_count = int(connection.execute(
                'SELECT COUNT(*) FROM "system"."main".duckdb_log_contexts()'
            ).fetchone()[0])
            log_count = int(connection.execute(
                'SELECT COUNT(*) FROM "system"."main".duckdb_logs()'
            ).fetchone()[0])

            connection.execute('ROLLBACK')
            active = False

            ended_at = datetime.now(timezone.utc).isoformat()
            metrics = {
                'duckdb.approx_database_count.approx_count': approx_db_count,
                'duckdb.connection_count.count': connection_count,
                'duckdb.external_file_cache.nr_bytes': cache_bytes_total,
                'duckdb.memory.memory_usage_bytes': memory_usage_total,
                'duckdb.memory.temporary_storage_bytes': temp_storage_total,
                'duckdb.temporary_files.size': temp_files_total,
                'duckdb.database_size.block_size': int(size[2] or 0),
                'duckdb.database_size.total_blocks': int(size[3] or 0),
                'duckdb.database_size.used_blocks': int(size[4] or 0),
                'duckdb.database_size.free_blocks': int(size[5] or 0),
                'duckdb.metadata_info.total_blocks': int(meta_totals[0] or 0),
                'duckdb.metadata_info.free_blocks': int(meta_totals[1] or 0),
            }

            return {
                'status': 'available',
                'scope': 'database',
                'contract_id': 'duckdb.metrics.1.5.2.v1',
                'sample_id': str(uuid.uuid4()),
                'source_epoch': self._epoch,
                'ended_at': ended_at,
                'identity': {
                    'database_name': catalog,
                    'version': version,
                    'library_version': ver_row[0],
                    'source_id': ver_row[1],
                    'codename': ver_row[2],
                    'platform': platform,
                    'user_agent': user_agent,
                    'target_id': self.target_id,
                    'engine_id': 'duckdb',
                    'collector_scope': 'dedicated-policy-connection',
                },
                'metrics': metrics,
                'groups': {
                    'storage': {
                        'status': 'available',
                        'scope': 'database',
                        'rows': [{
                            'database_name': size[0],
                            'database_size': size[1],
                            'block_size': size[2],
                            'total_blocks': size[3],
                            'used_blocks': size[4],
                            'free_blocks': size[5],
                            'wal_size': size[6],
                            'memory_usage': size[7],
                            'memory_limit': size[8],
                        }],
                    },
                    'database': {
                        'status': 'available',
                        'scope': 'database',
                        'rows': [{
                            'read_only': bool(primary_db[7]),
                            'encrypted': bool(primary_db[8]),
                            'cipher': primary_db[9],
                            'database_oid': int(primary_db[1]),
                            'type': str(primary_db[6]),
                        }],
                    },
                    'databases': {
                        'status': 'available',
                        'scope': 'instance',
                        'rows': [
                            {
                                'database_name': r[0],
                                'database_oid': int(r[1]),
                                'path_basename': os.path.basename(r[2]) if r[2] else None,
                                'comment': r[3],
                                'tags': dict(r[4]) if r[4] else {},
                                'internal': bool(r[5]),
                                'type': r[6],
                                'readonly': bool(r[7]),
                                'encrypted': bool(r[8]),
                                'cipher': r[9],
                            }
                            for r in db_rows
                        ],
                    },
                    'extensions': {
                        'status': 'available',
                        'scope': 'instance',
                        'rows': [{
                            'available': extensions[0],
                            'installed': extensions[1] or 0,
                            'loaded': extensions[2] or 0,
                        }],
                    },
                    'instance_counts': {
                        'status': 'available',
                        'scope': 'instance',
                        'rows': [{
                            'approx_database_count': approx_db_count,
                            'connection_count': connection_count,
                        }],
                    },
                    'memory': {
                        'status': 'available',
                        'scope': 'instance',
                        'rows': [
                            {
                                'tag': r[0],
                                'memory_usage_bytes': int(r[1] or 0),
                                'temporary_storage_bytes': int(r[2] or 0),
                            }
                            for r in memory_rows
                        ],
                    },
                    'temporary_files': {
                        'status': 'available',
                        'scope': 'instance',
                        'rows': [
                            {'filename': os.path.basename(r[0]) if r[0] else '', 'size': int(r[1] or 0)}
                            for r in temp_file_rows
                        ],
                    },
                    'external_file_cache': {
                        'status': 'available',
                        'scope': 'instance',
                        'rows': [
                            {
                                'entry': os.path.basename(r[0]) if r[0] else '',
                                'nr_bytes': int(r[1] or 0),
                                'location': int(r[2] or 0),
                                'loaded': bool(r[3]),
                            }
                            for r in cache_rows
                        ],
                    },
                    'metadata_info': {
                        'status': 'available',
                        'scope': 'database',
                        'rows': [
                            {
                                'block_id': int(r[0]),
                                'total_blocks': int(r[1]),
                                'free_blocks': int(r[2]),
                                'free_list_count': int(r[3] or 0),
                            }
                            for r in meta_rows
                        ],
                    },
                    'collector_session': {
                        'status': 'available',
                        'scope': 'collector-connection-only',
                        'rows': [{
                            'prepared_statement_count': len(prep_rows),
                            'variable_count': len(var_rows),
                            'log_context_count': log_ctx_count,
                            'log_event_count': log_count,
                        }],
                    },
                },
                'transaction_refresh': {
                    'status': 'completed',
                    'action': 'read-only-native-transaction-rolled-back',
                },
                'limitations': [
                    'No remote server load or global user-session metrics are exposed.',
                    'Temporary objects, variables, and prepared statements on other connections are not visible.',
                ],
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

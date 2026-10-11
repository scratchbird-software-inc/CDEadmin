"""Independent PostgreSQL monitoring; no user connection or SQL text capture."""
import copy
from datetime import date, datetime, timezone
from decimal import Decimal
import threading
import time
import uuid


class PostgreSQLMonitoringError(RuntimeError):
    pass


COUNTERS = ('xact_commit', 'xact_rollback', 'blks_read', 'blks_hit',
            'tup_returned', 'tup_fetched', 'tup_inserted', 'tup_updated',
            'tup_deleted', 'temp_files', 'temp_bytes', 'deadlocks')
DATABASE_SQL = '''SELECT datid, datname, numbackends, xact_commit, xact_rollback,
 blks_read, blks_hit, tup_returned, tup_fetched, tup_inserted, tup_updated,
 tup_deleted, temp_files, temp_bytes, deadlocks, stats_reset
 FROM pg_catalog.pg_stat_database WHERE datid <> 0'''
ACTIVITY_SQL = '''SELECT count(*) AS visible_backends,
 count(*) FILTER (WHERE state='active') AS active,
 count(*) FILTER (WHERE state='idle in transaction') AS idle_in_transaction,
 count(*) FILTER (WHERE state='idle in transaction (aborted)') AS aborted,
 count(*) FILTER (WHERE wait_event_type='Lock') AS lock_waiters,
 count(*) FILTER (WHERE state IS NULL) AS restricted_or_unavailable,
 max(EXTRACT(epoch FROM clock_timestamp()-xact_start)) AS oldest_transaction_seconds
 FROM pg_catalog.pg_stat_activity WHERE pid <> pg_backend_pid()'''
TABLE_SQL = '''SELECT relid, schemaname, relname, n_live_tup, n_dead_tup,
 n_mod_since_analyze, last_vacuum, last_autovacuum, last_analyze, last_autoanalyze,
 vacuum_count, autovacuum_count, analyze_count, autoanalyze_count
 FROM pg_catalog.pg_stat_user_tables ORDER BY n_dead_tup DESC, relid LIMIT 101'''
LOCK_SQL = '''SELECT locktype, mode, granted, count(*) AS count
 FROM pg_catalog.pg_locks WHERE pid IS DISTINCT FROM pg_backend_pid()'''
REPLICATION_SQL = '''SELECT pid, application_name, state, sync_state,
 sent_lsn, write_lsn, flush_lsn, replay_lsn, write_lag, flush_lag, replay_lag
 FROM pg_catalog.pg_stat_replication ORDER BY pid LIMIT 101'''
IO_SQL = '''SELECT backend_type, object, context, reads, read_bytes,
 writes, write_bytes, hits, evictions, fsyncs, stats_reset
 FROM pg_catalog.pg_stat_io ORDER BY backend_type, object, context LIMIT 101'''
SETTINGS_SQL = '''SELECT name, setting, unit FROM pg_catalog.pg_settings
 WHERE name IN ('max_connections','shared_buffers','track_counts','track_activities',
 'track_io_timing','stats_fetch_consistency','autovacuum','max_worker_processes')
 ORDER BY name'''


def wire(value):
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, Decimal)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: wire(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [wire(item) for item in value]
    if isinstance(value, float):
        return str(value)
    # Native intervals and LSNs are display values, not numeric counters.
    return value if isinstance(value, str) else str(value)


class PostgreSQLMonitor:
    """One dedicated attachment. The host owns scheduling and authorization."""
    def __init__(self, permissions, route, *, scope='database',
                 connect=None, monotonic_ns=time.monotonic_ns,
                 metadata_interval_seconds=60):
        if scope not in ('database', 'server') or not route.get('database'):
            raise ValueError('PostgreSQL monitoring requires an explicit connection database')
        if type(metadata_interval_seconds) is not int or not 60 <= metadata_interval_seconds <= 3600:
            raise ValueError('Invalid metadata interval')
        if any(name in route for name in ('password', 'passwd', 'secret', 'token')):
            raise ValueError('Monitoring requires a secret reference')
        if 'database_oid' in route and (type(route['database_oid']) is not int or
                                       not 1 <= route['database_oid'] <= 4294967295):
            raise ValueError('Invalid monitoring database identity')
        self.scope = scope
        self.route = copy.deepcopy(route)
        self.permissions = permissions
        self._connect = connect
        self._clock = monotonic_ns
        self._lock = threading.Lock()
        self._connection = None
        self._closed = False
        self._needs_release = False
        self._epoch = None
        self._previous = {}
        self._last_success = None
        self._metadata_interval_ns = metadata_interval_seconds * 10**9
        self._settings = None
        self._settings_at = None

    def _open(self):
        import psycopg
        route = self.route
        options = dict(route.get('connection_params') or {})
        timeout = options.pop('connect_timeout', 5)
        if isinstance(timeout, str) and timeout.isascii() and timeout.isdigit():
            timeout = int(timeout)
        if type(timeout) is not int or not 1 <= timeout <= 30:
            raise PostgreSQLMonitoringError('Monitoring connection timeout must be 1 to 30 seconds')
        allowed = {'sslmode', 'sslrootcert', 'sslcert', 'sslkey', 'sslcrl',
                   'sslcrldir', 'ssl_min_protocol_version', 'ssl_max_protocol_version',
                   'channel_binding', 'gssencmode', 'krbsrvname', 'target_session_attrs'}
        if set(options) - allowed:
            raise PostgreSQLMonitoringError('Unsupported monitoring connection options')
        reference = route.get('credential_reference_id')
        if not reference or not route.get('principal_reference'):
            raise PostgreSQLMonitoringError('Monitoring credential reference is unavailable')
        with self.permissions.acquire_secret(reference, route['principal_reference'],
                                             'connect', 'database_password') as lease:
            def attach(value):
                return (self._connect or psycopg.connect)(
                    host=route['host'], port=route['port'], user=route['user'],
                    dbname=route['database'], password=bytes(value).decode('utf8'),
                    application_name='ScratchRobin monitoring', connect_timeout=timeout,
                    autocommit=True, **options)
            connection = lease.use(attach)
        self._connection = connection
        if connection.info.server_version != 180003:
            raise PostgreSQLMonitoringError('Monitoring requires qualified PostgreSQL 18.3')
        if route.get('role'):
            from psycopg import sql
            connection.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(route['role'])))
        self._epoch = str(uuid.uuid4())
        self._previous = {}
        self._settings = None
        self._settings_at = None

    def _release(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        self._needs_release = False
        self._previous = {}
        self._settings = None
        self._settings_at = None

    def close(self):
        with self._lock:
            self._needs_release = True
            self._release()
            self._closed = True

    def _group(self, result, name, sql, params=(), *, scope=None, limited=False):
        try:
            with self._connection.transaction():
                with self._connection.cursor() as cursor:
                    cursor.execute(sql, params)
                    columns = [col.name for col in cursor.description]
                    values = cursor.fetchmany(101)
            result['groups'][name] = {
                'status': 'available', 'scope': scope or self.scope,
                'rows': [dict(zip(columns, row)) for row in values[:100]],
                'truncated': len(values) > 100, 'limit': 100,
                'visibility': 'permission-limited' if limited else 'native',
            }
        except Exception as error:
            # Connection errors abort the sample, rather than becoming zeros.
            code = getattr(error, 'sqlstate', None)
            if not code or code.startswith('08') or self._connection.closed:
                raise
            result['groups'][name] = {'status': 'unavailable', 'sqlstate': code,
                                      'scope': scope or self.scope}

    def _rates(self, result, started, postmaster):
        group = result['groups'].get('database', {})
        current = {}
        for row in group.get('rows', []):
            identity = (row['datid'], postmaster, row['stats_reset'])
            old = self._previous.get(identity)
            values = {key: row[key] for key in COUNTERS}
            valid = (old is not None and started > old[0] and
                     all(type(value) is int and type(old[1].get(key)) is int
                         and value >= old[1][key] for key, value in values.items()))
            row['rates_per_second'] = ({key: Decimal(value-old[1][key]) * Decimal(10**9) /
                                        Decimal(started-old[0]) for key, value in values.items()}
                                       if valid else None)
            row['rate_state'] = 'available' if valid else 'baseline-required'
            current[identity] = started, values
        self._previous = current

    def sample(self):
        with self._lock:
            if self._closed:
                raise PostgreSQLMonitoringError('Monitoring source is closed')
            start = self._clock()
            result = {'schema': 'postgresql-monitoring-sample@1', 'sample_id': str(uuid.uuid4()),
                      'scope': self.scope, 'status': 'available', 'history': 'volatile',
                      'started_at': datetime.now(timezone.utc).isoformat(), 'groups': {},
                      'last_success_at': self._last_success}
            try:
                if self._needs_release:
                    self._release()
                if self._connection is None:
                    self._open()
                with self._connection.transaction():
                    self._connection.execute('SET TRANSACTION READ ONLY')
                    self._connection.execute("SET LOCAL statement_timeout='3000ms'")
                    self._connection.execute("SET LOCAL lock_timeout='1000ms'")
                    identity = self._connection.execute('''SELECT current_database(),
                        pg_postmaster_start_time(), pg_backend_pid(), current_user,
                        pg_is_in_recovery(), (SELECT rolsuper FROM pg_roles WHERE rolname=current_user)
                        OR pg_has_role(current_user, 'pg_read_all_stats', 'USAGE'),
                        (SELECT oid FROM pg_database WHERE datname=current_database())''').fetchone()
                    database, postmaster, pid, user, recovery, all_stats, database_oid = identity
                    if (self.route.get('database_oid') is not None and
                            database_oid != self.route['database_oid']):
                        raise PostgreSQLMonitoringError('Monitoring database identity changed')
                    result.update(source_epoch=self._epoch, identity={
                        'database': database, 'database_oid': database_oid,
                        'postmaster_started_at': postmaster,
                        'collector_pid': pid, 'user': user, 'in_recovery': recovery,
                        'statistics_visibility': 'all' if all_stats else 'permission-limited'})
                    condition = ' AND datname=current_database()' if self.scope == 'database' else ''
                    self._group(result, 'database', DATABASE_SQL + condition + ' ORDER BY datid')
                    self._group(result, 'activity', ACTIVITY_SQL + condition, limited=not all_stats)
                    lock_scope = ' AND database=(SELECT oid FROM pg_database WHERE datname=current_database())' if self.scope == 'database' else ''
                    self._group(result, 'locks', LOCK_SQL + lock_scope + ' GROUP BY locktype, mode, granted ORDER BY locktype, mode, granted')
                    if self.scope == 'database':
                        self._group(result, 'tables', TABLE_SQL)
                    self._group(result, 'replication', REPLICATION_SQL, scope='server', limited=not all_stats)
                    self._group(result, 'io', IO_SQL, scope='server')
                    if (self._settings is None or self._settings_at is None or
                            start - self._settings_at >= self._metadata_interval_ns):
                        self._group(result, 'settings', SETTINGS_SQL, scope='connection')
                        result['groups']['settings']['observed_at'] = datetime.now(timezone.utc).isoformat()
                    else:
                        result['groups']['settings'] = copy.deepcopy(self._settings)
                settings = result['groups']['settings']
                if settings['status'] == 'available' and settings != self._settings:
                    self._settings = copy.deepcopy(settings)
                    self._settings_at = start
                self._rates(result, start, postmaster)
                if any(g['status'] != 'available' or g.get('truncated') or
                       g.get('visibility') == 'permission-limited' for g in result['groups'].values()):
                    result['status'] = 'partial'
                self._last_success = datetime.now(timezone.utc).isoformat()
                result['last_success_at'] = self._last_success
                result['transaction_completed'] = True
            except Exception as error:
                result.update(status='unavailable', error_type=type(error).__name__, transaction_completed=False)
                self._previous = {}
                self._needs_release = True
                try:
                    self._release()
                except Exception as cleanup:
                    result['release'] = {'status': 'unconfirmed', 'error_type': type(cleanup).__name__}
            except BaseException:
                self._previous = {}
                self._needs_release = True
                try:
                    self._release()
                except Exception:
                    pass  # Retain ownership and retry before any next attachment.
                raise
            result['ended_at'] = datetime.now(timezone.utc).isoformat()
            result['duration_seconds'] = Decimal(self._clock()-start) / Decimal(10**9)
            return wire(result)

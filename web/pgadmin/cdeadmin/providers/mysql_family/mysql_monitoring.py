"""Independent bounded MySQL monitoring source; no user transaction ownership."""
import copy
from datetime import datetime, timezone
import threading
import time
import uuid
from decimal import Decimal, localcontext

from .mysql_catalog import DENIED, identifier, _value

STATUS_NAMES = ('Uptime', 'Uptime_since_flush_status', 'Threads_connected', 'Threads_running', 'Connections',
    'Aborted_connects', 'Aborted_clients', 'Questions', 'Com_select', 'Com_insert',
    'Com_update', 'Com_delete', 'Com_commit', 'Com_rollback', 'Bytes_received',
    'Bytes_sent', 'Slow_queries', 'Created_tmp_tables', 'Created_tmp_disk_tables',
    'Innodb_buffer_pool_read_requests', 'Innodb_buffer_pool_reads',
    'Innodb_buffer_pool_pages_data', 'Innodb_buffer_pool_pages_dirty',
    'Innodb_data_reads', 'Innodb_data_writes', 'Innodb_row_lock_waits',
    'Innodb_row_lock_time', 'Innodb_rows_read', 'Innodb_rows_inserted',
    'Innodb_rows_updated', 'Innodb_rows_deleted')
GAUGES = {'Uptime', 'Uptime_since_flush_status', 'Threads_connected', 'Threads_running',
          'Innodb_buffer_pool_pages_data', 'Innodb_buffer_pool_pages_dirty'}


def counter_rates(previous, current, elapsed, *, identity_key='server_uuid'):
    """Exact native global counter differences; missing fields remain gaps."""
    unavailable = {'status': 'unavailable', 'reason': 'baseline-unavailable', 'per_second': {}}
    def counters(sample):
        group = sample.get('groups', {}).get('status', {})
        if not sample.get('transaction_completed') or group.get('status') != 'available':
            return None
        values = {}
        for row in group.get('rows', []):
            name, value = row.get('variable_name'), row.get('variable_value')
            if name in STATUS_NAMES and isinstance(value, str) and value.isascii() and value.isdigit():
                values[name] = int(value)
        return values
    before, after = counters(previous or {}), counters(current)
    if (before is None or after is None or previous.get('source_epoch') != current.get('source_epoch') or
            previous.get('identity', {}).get(identity_key) != current.get('identity', {}).get(identity_key) or
            not isinstance(elapsed, (int, float)) or not 0 < elapsed <= 3600):
        return unavailable
    if any(name not in before or name not in after for name in ('Uptime', 'Uptime_since_flush_status')):
        return {**unavailable, 'reason': 'reset-observation-unavailable'}
    if (after['Uptime'] < before['Uptime'] or after['Uptime_since_flush_status'] < before['Uptime_since_flush_status'] or
            abs((after['Uptime'] - after['Uptime_since_flush_status']) -
                (before['Uptime'] - before['Uptime_since_flush_status'])) > 1):
        return {**unavailable, 'reason': 'server-or-status-reset'}
    rates, gaps = {}, {}
    with localcontext() as context:
        context.prec = 64
        for name in STATUS_NAMES:
            if name in GAUGES:
                continue
            if name not in before or name not in after:
                gaps[name] = 'counter-unavailable'
            elif after[name] < before[name]:
                gaps[name] = 'counter-reset'
            else:
                rates[name] = format(Decimal(after[name] - before[name]) / Decimal(str(elapsed)), 'f')
    return {'status': 'available', 'scope': 'server', 'elapsed_seconds': elapsed,
            'epoch': current['source_epoch'], 'per_second': rates, 'gaps': gaps}


class MySQLMonitor:
    engine = 'mysql'
    native_version = '9.7.0'
    identity_key = 'server_uuid'
    identity_source = ('SELECT DATABASE() AS database_name, VERSION() AS version, '
        '@@server_uuid AS server_uuid, CONNECTION_ID() AS collector_id, CURRENT_USER() AS account')
    status_table = 'performance_schema.global_status'
    settings_source = ('SELECT @@max_connections AS max_connections, @@innodb_page_size AS innodb_page_size, '
        '@@innodb_buffer_pool_size AS innodb_buffer_pool_size, @@read_only AS read_only, '
        '@@super_read_only AS super_read_only, @@event_scheduler AS event_scheduler')
    replication_source = ('SELECT CHANNEL_NAME, SERVICE_STATE, LAST_ERROR_NUMBER '
        'FROM performance_schema.replication_connection_status ORDER BY CHANNEL_NAME LIMIT 101')

    def _activity_source(self):
        condition = ' AND PROCESSLIST_DB=DATABASE()' if self.scope == 'database' else ''
        return ('SELECT PROCESSLIST_ID, PROCESSLIST_USER, PROCESSLIST_DB, PROCESSLIST_COMMAND, '
            'PROCESSLIST_TIME, PROCESSLIST_STATE FROM performance_schema.threads '
            "WHERE TYPE='FOREGROUND'" + condition + ' ORDER BY PROCESSLIST_ID LIMIT 101')

    def _transaction_active(self):
        return self._connection.in_transaction

    def __init__(self, permissions, route, *, scope='database', metadata_interval_seconds=60):
        if scope not in {'database', 'server'} or (scope == 'database' and not route.get('database')):
            raise ValueError(f'{self.engine} monitoring requires an explicit native scope')
        if type(metadata_interval_seconds) is not int or not 60 <= metadata_interval_seconds <= 3600:
            raise ValueError('Invalid monitoring metadata interval')
        self.permissions, self.route, self.scope = permissions, copy.deepcopy(route), scope
        self._connection = self._client = None
        self._closed = False
        self._epoch = None
        self._lock = threading.RLock()
        self._last_success = None
        self._previous = None
        self._previous_clock = None
        self._metadata_interval = metadata_interval_seconds
        self._metadata_clock = None
        self._metadata_cache = {}

    def _open(self):
        from .provider import MYSQL_PROFILE, _create_client
        route = {**self.route, 'autocommit': True, 'connection_timeout': 5,
                 'read_timeout': 5, 'write_timeout': 5}
        # A monitor must never compete for an interactive pool lease.
        for name in ('pool_name', 'pool_size', 'pool_reset_session'):
            route.pop(name, None)
        self._client = _create_client(MYSQL_PROFILE, self.permissions, None)
        self._connection = self._client._connect({'route': {**route, 'database': None} if route.get('role') else route})
        if route.get('role'):
            with self._connection.cursor() as cursor:
                cursor.execute('SET ROLE ' + identifier(route['role']))
            if route.get('database'):
                self._connection.database = route['database']
        self._epoch = str(uuid.uuid4())

    def _release(self):
        client, connection = self._client, self._connection
        self._client = self._connection = None
        self._metadata_clock = None
        self._metadata_cache = {}
        try:
            if client is not None and connection is not None:
                client._discard_failed_session(connection)
        finally:
            if client is not None:
                client.close()

    def _read(self, source, parameters=None):
        with self._connection.cursor() as cursor:
            cursor.execute(source, parameters)
            names = [str(item[0]).lower() for item in cursor.description]
            rows = cursor.fetchmany(101)
            # Every probe includes a SQL LIMIT or a fixed cardinality bound;
            # consume its remainder before issuing another protocol command.
            remainder = cursor.fetchone()
            if remainder is not None:
                raise ValueError('Monitoring probe exceeded its native row bound')
            return [{key: str(value) if type(value) is int else _value(value)
                     for key, value in zip(names, row)} for row in rows]

    def _group(self, result, name, source, parameters=None, *, scope=None):
        try:
            rows = self._read(source, parameters)
            result['groups'][name] = {'status': 'available', 'scope': scope or self.scope,
                'rows': rows[:100], 'truncated': len(rows) > 100, 'limit': 100,
                'visibility': 'permission-filtered'}
        except Exception as error:
            if getattr(error, 'errno', None) not in DENIED:
                raise
            result['groups'][name] = {'status': 'unavailable', 'scope': scope or self.scope,
                'error_code': error.errno, 'sqlstate': getattr(error, 'sqlstate', None)}
        result['groups'][name].update(observed_at=datetime.now(timezone.utc).isoformat(),
                                     observation_age_seconds=0)

    def sample(self):
        with self._lock:
            if self._closed:
                raise ValueError(f'{self.engine} monitoring source is closed')
            start = time.monotonic()
            probe = 'transaction_refresh' if self.scope == 'database' else 'service_probe'
            result = {'schema': self.engine + '-monitoring-sample@1', 'sample_id': str(uuid.uuid4()),
                'scope': self.scope, 'status': 'available', 'history': 'volatile', 'groups': {},
                'started_at': datetime.now(timezone.utc).isoformat(),
                'transaction_completed': False, probe: {'status': 'not-completed'}}
            try:
                if self._connection is None:
                    self._open()
                identity = self._read(self.identity_source)[0]
                if identity['version'].split('-')[0] != self.native_version or identity['database_name'] != self.route.get('database'):
                    raise ValueError('Monitoring native identity changed')
                result.update(identity=identity, source_epoch=self._epoch)
                markers = ','.join(['%s'] * len(STATUS_NAMES))
                self._group(result, 'status', 'SELECT VARIABLE_NAME, VARIABLE_VALUE FROM ' + self.status_table + ' '
                    'WHERE VARIABLE_NAME IN (' + markers + ') ORDER BY VARIABLE_NAME LIMIT 101', STATUS_NAMES, scope='server')
                if self._metadata_clock is None or start - self._metadata_clock >= self._metadata_interval:
                    self._group(result, 'settings', self.settings_source, scope='server')
                    if self.scope == 'database':
                        self._group(result, 'storage', 'SELECT ENGINE, COUNT(*) AS tables_count, '
                            'SUM(TABLE_ROWS) AS estimated_rows, SUM(DATA_LENGTH) AS data_bytes, SUM(INDEX_LENGTH) AS index_bytes '
                            'FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() GROUP BY ENGINE LIMIT 101')
                    if self.engine == 'mysql':
                        from .mysql_workload import observe
                        result['groups'].update(observe(self, self.route.get('database') if self.scope == 'database' else None)['groups'])
                    self._metadata_cache = {name: copy.deepcopy(group) for name, group in result['groups'].items()
                        if name in {'settings', 'storage'} or name.startswith('workload_')}
                    self._metadata_clock = start
                else:
                    for name, group in self._metadata_cache.items():
                        result['groups'][name] = {**copy.deepcopy(group),
                            'observation_age_seconds': round(start - self._metadata_clock, 3)}
                self._group(result, 'activity', self._activity_source())
                self._group(result, 'replication', self.replication_source, scope='server')
                if self._transaction_active():
                    raise ValueError('Monitoring probe retained a transaction')
                result.update(status='partial', transaction_completed=True)
                # Visible empty groups do not establish complete server coverage.
                result[probe] = {'status': 'completed', 'evidence': 'owned-autocommit-read-probes'}
                result['rates'] = counter_rates(self._previous, result,
                    None if self._previous_clock is None else start - self._previous_clock, identity_key=self.identity_key)
                if self.engine == 'mysql':
                    from .mysql_workload import reset_evidence
                    result['workload_reset'] = reset_evidence(self._previous, result)
                self._previous, self._previous_clock = copy.deepcopy(result), start
                self._last_success = datetime.now(timezone.utc).isoformat()
            except Exception as error:
                result.update(status='unavailable', error_type=type(error).__name__)
                if isinstance(getattr(error, 'errno', None), int):
                    result.update(error_code=error.errno, sqlstate=getattr(error, 'sqlstate', None))
                self._previous = self._previous_clock = None
                self._release()
            result.update(last_success_at=self._last_success, ended_at=datetime.now(timezone.utc).isoformat(),
                          elapsed_ms=round((time.monotonic() - start) * 1000, 3))
            return result

    def close(self):
        with self._lock:
            self._closed = True
            self._release()

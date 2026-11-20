"""Dedicated MariaDB native probes, independent of interactive transactions."""
from datetime import datetime, timezone
import uuid
from types import SimpleNamespace

from .mariadb_catalog import DENIED
from .mysql_catalog import identifier
from .mysql_monitoring import GAUGES, MySQLMonitor, STATUS_NAMES

ARIA_STATUS_NAMES = (
    'Aria_pagecache_blocks_not_flushed',
    'Aria_pagecache_blocks_unused',
    'Aria_pagecache_blocks_used',
    'Aria_pagecache_read_requests',
    'Aria_pagecache_reads',
    'Aria_pagecache_write_requests',
    'Aria_pagecache_writes',
    'Aria_transaction_log_syncs',
)
KEY_STATUS_NAMES = (
    'Key_blocks_not_flushed',
    'Key_blocks_unused',
    'Key_blocks_used',
    'Key_read_requests',
    'Key_reads',
    'Key_write_requests',
    'Key_writes',
)
MARIADB_STATUS_NAMES = STATUS_NAMES + ARIA_STATUS_NAMES + KEY_STATUS_NAMES
MARIADB_GAUGES = GAUGES | {
    'Aria_pagecache_blocks_not_flushed',
    'Aria_pagecache_blocks_unused',
    'Aria_pagecache_blocks_used',
    'Key_blocks_not_flushed',
    'Key_blocks_unused',
    'Key_blocks_used',
}
MARIADB_STATUS_UNITS = {
    'Uptime': 'seconds',
    'Uptime_since_flush_status': 'seconds',
    'Threads_connected': 'connections',
    'Threads_running': 'connections',
    'Connections': 'connections',
    'Aborted_connects': 'connections',
    'Aborted_clients': 'connections',
    'Questions': 'queries',
    'Com_select': 'statements',
    'Com_insert': 'statements',
    'Com_update': 'statements',
    'Com_delete': 'statements',
    'Com_commit': 'transactions',
    'Com_rollback': 'transactions',
    'Bytes_received': 'bytes',
    'Bytes_sent': 'bytes',
    'Slow_queries': 'queries',
    'Created_tmp_tables': 'tables',
    'Created_tmp_disk_tables': 'tables',
    'Innodb_buffer_pool_read_requests': 'requests',
    'Innodb_buffer_pool_reads': 'pages',
    'Innodb_buffer_pool_pages_data': 'pages',
    'Innodb_buffer_pool_pages_dirty': 'pages',
    'Innodb_data_reads': 'operations',
    'Innodb_data_writes': 'operations',
    'Innodb_row_lock_waits': 'waits',
    'Innodb_row_lock_time': 'milliseconds',
    'Innodb_rows_read': 'rows',
    'Innodb_rows_inserted': 'rows',
    'Innodb_rows_updated': 'rows',
    'Innodb_rows_deleted': 'rows',
    'Aria_pagecache_blocks_not_flushed': 'blocks',
    'Aria_pagecache_blocks_unused': 'blocks',
    'Aria_pagecache_blocks_used': 'blocks',
    'Aria_pagecache_read_requests': 'requests',
    'Aria_pagecache_reads': 'blocks',
    'Aria_pagecache_write_requests': 'requests',
    'Aria_pagecache_writes': 'blocks',
    'Aria_transaction_log_syncs': 'syncs',
    'Key_blocks_not_flushed': 'blocks',
    'Key_blocks_unused': 'blocks',
    'Key_blocks_used': 'blocks',
    'Key_read_requests': 'requests',
    'Key_reads': 'blocks',
    'Key_write_requests': 'requests',
    'Key_writes': 'blocks',
}
WSREP_VARIABLE_NAMES = ('WSREP_ON', 'WSREP_PROVIDER', 'WSREP_CLUSTER_NAME', 'WSREP_NODE_NAME')
WSREP_STATUS_NAMES = (
    'WSREP_READY',
    'WSREP_CONNECTED',
    'WSREP_CLUSTER_SIZE',
    'WSREP_CLUSTER_STATUS',
    'WSREP_LOCAL_STATE_COMMENT',
    'WSREP_LOCAL_RECV_QUEUE_AVG',
    'WSREP_FLOW_CONTROL_PAUSED',
)


class MariaDBMonitor(MySQLMonitor):
    engine = 'mariadb'
    native_version = '12.2.2'
    identity_key = 'server_uid'
    status_names = MARIADB_STATUS_NAMES
    gauges = MARIADB_GAUGES
    identity_source = ('SELECT DATABASE() AS database_name, VERSION() AS version, '
        '@@server_uid AS server_uid, CONNECTION_ID() AS collector_id, CURRENT_USER() AS account')
    status_table = 'information_schema.GLOBAL_STATUS'
    settings_source = ('SELECT @@max_connections AS max_connections, @@innodb_page_size AS innodb_page_size, '
        '@@innodb_buffer_pool_size AS innodb_buffer_pool_size, @@aria_pagecache_buffer_size AS aria_pagecache_buffer_size, '
        '@@key_buffer_size AS key_buffer_size, @@wsrep_on AS wsrep_on, '
        '@@read_only AS read_only, @@event_scheduler AS event_scheduler')
    replication_source = ('SELECT CONNECTION_NAME AS channel_name, SLAVE_IO_RUNNING, SLAVE_SQL_RUNNING, '
        'LAST_IO_ERRNO, LAST_SQL_ERRNO, SECONDS_BEHIND_MASTER, GTID_IO_POS '
        'FROM information_schema.SLAVE_STATUS ORDER BY CONNECTION_NAME LIMIT 101')

    def _activity_source(self):
        condition = ' WHERE DB=DATABASE()' if self.scope == 'database' else ''
        return ('SELECT ID AS processlist_id, USER AS processlist_user, DB AS processlist_db, '
            'COMMAND AS processlist_command, TIME AS processlist_time, STATE AS processlist_state '
            'FROM information_schema.PROCESSLIST' + condition + ' ORDER BY ID LIMIT 101')

    def _group(self, result, name, source, parameters=None, *, scope=None):
        super()._group(result, name, source, parameters, scope=scope)
        if name == 'status' and result['groups'][name]['status'] == 'available':
            canonical = {key.casefold(): key for key in self.status_names}
            units = {}
            metric_kinds = {}
            for row in result['groups'][name]['rows']:
                native = row.get('variable_name')
                if isinstance(native, str) and native.casefold() in canonical:
                    canon_name = canonical[native.casefold()]
                    row['native_variable_name'] = native
                    row['variable_name'] = canon_name
                    units[canon_name] = MARIADB_STATUS_UNITS.get(canon_name, 'count')
                    metric_kinds[canon_name] = 'gauge' if canon_name in self.gauges else 'counter'
            if units:
                result['groups'][name]['units'] = units
                result['groups'][name]['metric_kinds'] = metric_kinds

    def _collect_engine_metadata_groups(self, result):
        if self.scope == 'server':
            self._group(
                result,
                'storage',
                'SELECT ENGINE, COUNT(*) AS tables_count, SUM(TABLE_ROWS) AS estimated_rows, '
                'SUM(DATA_LENGTH) AS data_bytes, SUM(INDEX_LENGTH) AS index_bytes '
                "FROM information_schema.TABLES WHERE TABLE_TYPE='BASE TABLE' "
                "AND TABLE_SCHEMA NOT IN ('information_schema','performance_schema','sys') "
                'GROUP BY ENGINE ORDER BY ENGINE LIMIT 101',
                scope='server',
            )
        scope_filter = (
            "WHERE TABLE_TYPE='BASE TABLE' AND TABLE_SCHEMA=DATABASE()"
            if self.scope == 'database'
            else "WHERE TABLE_TYPE='BASE TABLE' AND TABLE_SCHEMA NOT IN ('information_schema','performance_schema','sys')"
        )
        self._group(
            result,
            'engines',
            'SELECT e.ENGINE, e.SUPPORT, e.TRANSACTIONS, e.XA, e.SAVEPOINTS, '
            'COALESCE(t.tables_count, 0) AS tables_count, '
            'COALESCE(t.data_bytes, 0) AS data_bytes, '
            'COALESCE(t.index_bytes, 0) AS index_bytes '
            'FROM information_schema.ENGINES e '
            'LEFT JOIN (SELECT ENGINE, COUNT(*) AS tables_count, SUM(DATA_LENGTH) AS data_bytes, '
            f'SUM(INDEX_LENGTH) AS index_bytes FROM information_schema.TABLES {scope_filter} GROUP BY ENGINE) t '
            'ON t.ENGINE = e.ENGINE '
            "WHERE e.SUPPORT IN ('YES', 'DEFAULT') ORDER BY e.ENGINE LIMIT 101",
            scope=self.scope,
        )

    def _collect_engine_live_groups(self, result):
        now_iso = datetime.now(timezone.utc).isoformat()
        v_markers = ','.join(['%s'] * len(WSREP_VARIABLE_NAMES))
        s_markers = ','.join(['%s'] * len(WSREP_STATUS_NAMES))
        try:
            var_rows = self._read(
                'SELECT VARIABLE_NAME, VARIABLE_VALUE FROM information_schema.GLOBAL_VARIABLES '
                f'WHERE VARIABLE_NAME IN ({v_markers}) ORDER BY VARIABLE_NAME LIMIT 101',
                WSREP_VARIABLE_NAMES,
            )
            stat_rows = self._read(
                'SELECT VARIABLE_NAME, VARIABLE_VALUE FROM information_schema.GLOBAL_STATUS '
                f'WHERE VARIABLE_NAME IN ({s_markers}) ORDER BY VARIABLE_NAME LIMIT 101',
                WSREP_STATUS_NAMES,
            )
        except Exception as error:
            if getattr(error, 'errno', None) not in DENIED:
                raise
            result['groups']['wsrep'] = {
                'status': 'unavailable',
                'scope': 'server',
                'error_code': error.errno,
                'sqlstate': getattr(error, 'sqlstate', None),
                'observed_at': now_iso,
                'observation_age_seconds': 0,
            }
            return

        vars_map = {
            str(r.get('variable_name') or '').upper(): str(r.get('variable_value') or '')
            for r in var_rows
        }
        wsrep_on_raw = vars_map.get('WSREP_ON', 'OFF').upper()
        wsrep_on = wsrep_on_raw in {'ON', '1', 'TRUE'}
        provider_val = vars_map.get('WSREP_PROVIDER', 'none')
        provider_loaded = bool(provider_val and provider_val.strip().lower() not in {'none', 'off', ''})
        active_cluster = wsrep_on and provider_loaded

        if not active_cluster:
            # Explicitly distinguish unconfigured/disabled Galera wsrep from active cluster metrics;
            # never fabricate zero cluster metrics when wsrep_on=OFF or wsrep_provider=none.
            result['groups']['wsrep'] = {
                'status': 'disabled',
                'scope': 'server',
                'wsrep_on': wsrep_on,
                'wsrep_on_native': wsrep_on_raw,
                'wsrep_provider': provider_val,
                'provider_loaded': provider_loaded,
                'cluster_metrics_available': False,
                'cluster_state': 'wsrep-provider-not-loaded' if not provider_loaded else 'wsrep-disabled',
                'reason': 'wsrep-disabled-or-provider-not-loaded;no-zero-metrics-fabricated',
                'rows': [],
                'truncated': False,
                'limit': 100,
                'visibility': 'permission-filtered',
                'observed_at': now_iso,
                'observation_age_seconds': 0,
            }
        else:
            normalized_rows = []
            for r in stat_rows:
                vname = str(r.get('variable_name') or '')
                normalized_rows.append({
                    'variable_name': vname.lower(),
                    'native_variable_name': vname,
                    'variable_value': r.get('variable_value'),
                })
            result['groups']['wsrep'] = {
                'status': 'available',
                'scope': 'server',
                'wsrep_on': True,
                'wsrep_on_native': wsrep_on_raw,
                'wsrep_provider': provider_val,
                'provider_loaded': True,
                'cluster_metrics_available': True,
                'cluster_state': 'active',
                'cluster_name': vars_map.get('WSREP_CLUSTER_NAME'),
                'node_name': vars_map.get('WSREP_NODE_NAME'),
                'rows': normalized_rows,
                'truncated': False,
                'limit': 100,
                'visibility': 'permission-filtered',
                'observed_at': now_iso,
                'observation_age_seconds': 0,
            }

    def _transaction_active(self):
        status = self._connection.server_status
        if type(status) is not int or self._connection.autocommit is not True:
            raise ValueError('MariaDB monitoring transaction policy is unavailable')
        return bool(status & 1)

    def _open(self):
        from .provider import MARIADB_PROFILE, _create_client
        route = {**self.route, 'autocommit': True, 'reconnect': False,
                 'connect_timeout': 5, 'read_timeout': 5, 'write_timeout': 5}
        for name in ('pool_name', 'pool_size', 'pool_reset_connection', 'pool_validation_interval'):
            route.pop(name, None)
        self._client = _create_client(MARIADB_PROFILE, self.permissions,
            SimpleNamespace(pool_namespace='mariadb-monitor:' + str(uuid.uuid4())))
        self._connection = self._client._connect({'route': {**route, 'database': None} if route.get('role') else route})
        if route.get('role'):
            with self._connection.cursor() as cursor:
                cursor.execute('SET ROLE ' + identifier(route['role']))
            if route.get('database'):
                self._connection.database = route['database']
        self._epoch = str(uuid.uuid4())

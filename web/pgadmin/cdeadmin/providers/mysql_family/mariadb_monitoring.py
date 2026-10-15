"""Dedicated MariaDB native probes, independent of interactive transactions."""
import uuid
from types import SimpleNamespace

from .mysql_catalog import identifier
from .mysql_monitoring import MySQLMonitor, STATUS_NAMES


class MariaDBMonitor(MySQLMonitor):
    engine = 'mariadb'
    native_version = '12.2.2'
    identity_key = 'server_uid'
    identity_source = ('SELECT DATABASE() AS database_name, VERSION() AS version, '
        '@@server_uid AS server_uid, CONNECTION_ID() AS collector_id, CURRENT_USER() AS account')
    status_table = 'information_schema.GLOBAL_STATUS'
    settings_source = ('SELECT @@max_connections AS max_connections, @@innodb_page_size AS innodb_page_size, '
        '@@innodb_buffer_pool_size AS innodb_buffer_pool_size, @@read_only AS read_only, '
        '@@event_scheduler AS event_scheduler')
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
            canonical = {key.casefold(): key for key in STATUS_NAMES}
            for row in result['groups'][name]['rows']:
                native = row.get('variable_name')
                if isinstance(native, str) and native.casefold() in canonical:
                    row['native_variable_name'] = native
                    row['variable_name'] = canonical[native.casefold()]

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

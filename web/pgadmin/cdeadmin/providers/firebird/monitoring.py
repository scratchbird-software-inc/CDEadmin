"""Dedicated, read-only Firebird monitoring snapshots (not user sessions).

This is a trusted provider-side source adapter. Its route must come from the
endpoint service; dashboard definitions and browser payloads are not routes.
"""

import copy
import threading
import time
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from .monitoring_inventory import (
    ACTIVITY, METADATA, TABLE_COUNTERS, rows as inventory_rows,
)


DATABASE_FIELDS = (
    'DATABASE_NAME', 'GUID', 'FILE_ID', 'OWNER', 'CREATION_DATE',
    'PAGE_SIZE', 'ODS_MAJOR', 'ODS_MINOR', 'SQL_DIALECT', 'SHUTDOWN_MODE',
    'READ_ONLY', 'FORCED_WRITES', 'OLDEST_TRANSACTION', 'OLDEST_ACTIVE',
    'OLDEST_SNAPSHOT', 'NEXT_TRANSACTION', 'PAGE_BUFFERS', 'PAGES',
    'BACKUP_STATE', 'CRYPT_STATE', 'REPLICA_MODE', 'STAT_ID',
)
IO_FIELDS = ('PAGE_READS', 'PAGE_WRITES', 'PAGE_FETCHES', 'PAGE_MARKS')
RECORD_FIELDS = (
    'RECORD_SEQ_READS', 'RECORD_IDX_READS', 'RECORD_INSERTS', 'RECORD_UPDATES',
    'RECORD_DELETES', 'RECORD_BACKOUTS', 'RECORD_PURGES', 'RECORD_EXPUNGES',
    'RECORD_LOCKS', 'RECORD_WAITS', 'RECORD_CONFLICTS', 'BACKVERSION_READS',
    'FRAGMENT_READS', 'RECORD_RPT_READS', 'RECORD_IMGC',
)
MEMORY_FIELDS = ('MEMORY_USED', 'MEMORY_ALLOCATED', 'MAX_MEMORY_USED',
                 'MAX_MEMORY_ALLOCATED')

DETAIL_FIELDS = {
    'attachment_details': ('ATTACHMENTS', ('ATTACHMENT_ID', 'USER', 'ROLE',
        'REMOTE_PROTOCOL', 'REMOTE_ADDRESS', 'TIMESTAMP', 'STATE', 'SYSTEM_FLAG')),
    'transaction_details': ('TRANSACTIONS', ('TRANSACTION_ID', 'ATTACHMENT_ID',
        'TIMESTAMP', 'STATE', 'ISOLATION_MODE', 'READ_ONLY', 'LOCK_TIMEOUT',
        'AUTO_COMMIT', 'AUTO_UNDO')),
    'statement_details': ('STATEMENTS', ('STATEMENT_ID', 'ATTACHMENT_ID',
        'TRANSACTION_ID', 'TIMESTAMP', 'STATE', 'STATEMENT_TIMEOUT',
        'COMPILED_STATEMENT_ID')),
}


def _details(cursor, table, fields):
    cursor.execute('SELECT FIRST 101 ' + ', '.join('MON$' + f for f in fields) +
                   ' FROM MON$' + table +
                   ' WHERE MON$ATTACHMENT_ID <> CURRENT_CONNECTION'
                   ' ORDER BY MON$TIMESTAMP, MON$' + fields[0])
    rows = cursor.fetchmany(101)
    if any(len(row) != len(fields) for row in rows):
        raise RelationalClientError('Invalid monitoring detail row')
    return {'rows': [dict(zip((f.lower() for f in fields), row)) for row in rows[:100]],
            'truncated': len(rows) > 100, 'limit': 100, 'collector_excluded': True}


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _wire(value):
    """Do not silently round Firebird BIGINTs in a JavaScript consumer."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, Decimal)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {key: _wire(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_wire(item) for item in value]
    return value


def _one(cursor, sql, fields):
    cursor.execute(sql)
    row = cursor.fetchone()
    if row is None or len(row) != len(fields):
        raise RelationalClientError('Monitoring source returned no valid row')
    return dict(zip((field.lower() for field in fields), row))


def _stats(cursor, table, fields):
    return _one(cursor, 'SELECT ' + ', '.join('S.MON$' + f for f in fields) +
                ' FROM MON$' + table + ' S JOIN MON$DATABASE D'
                ' ON S.MON$STAT_ID = D.MON$STAT_ID'
                ' WHERE S.MON$STAT_GROUP = 0', fields)


class CounterEpoch:
    """One source's exact counters; an interrupted series never bridges a gap."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.epoch = str(uuid.uuid4())
        self.previous = None

    def observe(self, identity, counters, observed_ns):
        previous = self.previous
        reason = 'first-observation'
        if previous is not None:
            old_identity, old_values, old_ns = previous
            if identity != old_identity:
                reason = 'identity-changed'
            elif counters.keys() != old_values.keys():
                reason = 'counter-coverage-changed'
            elif observed_ns <= old_ns:
                reason = 'invalid-interval'
            elif any(value < old_values[key]
                     for key, value in counters.items()):
                reason = 'counter-decreased'
            else:
                seconds = Decimal(observed_ns - old_ns) / Decimal(10**9)
                result = {
                    'epoch': self.epoch, 'status': 'available',
                    'elapsed_seconds': str(seconds),
                    'delta': {key: str(value - old_values[key])
                              for key, value in counters.items()},
                    'per_second': {
                        key: str(Decimal(value - old_values[key]) / seconds)
                        for key, value in counters.items()},
                }
                self.previous = (identity, dict(counters), observed_ns)
                return result
            self.reset()
        self.previous = (identity, dict(counters), observed_ns)
        return {'epoch': self.epoch, 'status': 'gap', 'reason': reason,
                'delta': {}, 'per_second': {}}


class FirebirdMonitor:
    """Own one isolated client, with serialized sampling and explicit release.

    Callers own scheduling and reauthorization. No shared provider client can be
    supplied: even tests supply a factory, never a user's open session handle.
    Failed release remains owned here until close succeeds.
    """

    def __init__(self, permissions, route, *, scope='database',
                 client_factory=None, monotonic_ns=time.monotonic_ns,
                 metadata_interval_seconds=60):
        if type(metadata_interval_seconds) is not int or not 60 <= metadata_interval_seconds <= 3600:
            raise ValueError('Invalid metadata sampling interval')
        self._metadata_interval_seconds = metadata_interval_seconds
        if scope not in ('database', 'server'):
            raise ValueError('Monitoring scope must be database or server')
        if scope == 'database' and not route.get('database'):
            raise ValueError('Database monitoring requires a registered target')
        embedded = route.get('attachment_mode') == 'embedded'
        if embedded and scope != 'database':
            raise ValueError('Embedded Firebird has no server Services API collector')
        if client_factory is None:
            from .provider import _create_client
            if embedded:
                from .embedded_provider import PROFILE, ADMINISTRATION
                client_factory = lambda permissions, **options: _create_client(
                    permissions, profile=PROFILE, administration=ADMINISTRATION, **options)
            else:
                client_factory = _create_client
        self._route = copy.deepcopy(route)
        self._route.update({
            'transaction_isolation': 'SNAPSHOT', 'transaction_access': 'READ',
            'transaction_lock_timeout': 0, 'transaction_auto_commit': False,
            'transaction_ignore_limbo': False, 'transaction_no_auto_undo': False,
            'statement_timeout_ms': 3000, 'session_idle_timeout_seconds': 0,
            'timeout': 5,
        })
        if embedded:
            self._route.pop('timeout', None)
        self._client = client_factory(
            permissions, attachment_mode=route.get('attachment_mode', 'network'))
        self.scope = scope
        self._clock = monotonic_ns
        self._lock = threading.Lock()
        self._connection = None
        self._needs_release = False
        self._closed = False
        self._counters = CounterEpoch()
        self._last_success = None
        self._source_epoch = None
        self._metadata_cache = None
        self._metadata_observed_ns = None
        self._table_counters = {}

    def close(self):
        with self._lock:
            self._client.close()
            self._connection = None
            self._closed = True
            self._counters.reset()

    def sample(self):
        with self._lock:
            if self._closed:
                raise RelationalClientError('Monitoring collector is closed')
            start = self._clock()
            result = {
                'schema': 'firebird-monitoring-sample@1',
                'sample_id': str(uuid.uuid4()), 'scope': self.scope,
                'attachment_mode': self._route.get('attachment_mode', 'network'),
                'started_at': _utc(), 'status': 'available',
                'last_success_at': self._last_success,
                'history': 'volatile', 'groups': {},
            }
            try:
                if self._needs_release:
                    self._release()
                if self._connection is None:
                    connector = (self._client._connect if
                                 self.scope == 'database' else
                                 self._client._connect_server)
                    self._connection = connector({'route': self._route})
                    self._source_epoch = str(uuid.uuid4())
                    self._counters.reset()
                    self._metadata_cache = None
                    self._metadata_observed_ns = None
                    self._table_counters = {}
                result['source_epoch'] = self._source_epoch
                if self.scope == 'database':
                    self._database(result)
                else:
                    self._server(result)
                if any(group['status'] != 'available'
                       for group in result['groups'].values()):
                    result['status'] = 'partial'
                self._last_success = _utc()
                result['last_success_at'] = self._last_success
            except Exception as error:
                result.update(status='unavailable', error_type=type(error).__name__)
                self._counters.reset()
                self._table_counters = {}
                self._metadata_cache = None
                self._needs_release = True
                try:
                    self._release()
                except Exception as cleanup:
                    result['release'] = {'status': 'unconfirmed',
                                         'error_type': type(cleanup).__name__}
            except BaseException:
                self._needs_release = True
                self._counters.reset()
                self._table_counters = {}
                self._metadata_cache = None
                try:
                    self._release()
                except Exception:
                    pass  # Ownership remains; do not replace interruption.
                raise
            result['ended_at'] = _utc()
            result['duration_seconds'] = str(
                Decimal(self._clock() - start) / Decimal(10**9))
            return _wire(result)

    def inspect_statement(self, reference):
        """Read one previously sampled identity; caller owns current authorization."""
        with self._lock:
            if (self._closed or self.scope != 'database' or self._connection is None or
                    self._needs_release or reference.get('source_epoch') != self._source_epoch):
                return {'status': 'unavailable', 'reason': 'collector-epoch-unavailable'}
            connection = self._connection
            cursor = connection.cursor()
            fields = ('statement_id', 'attachment_id', 'compiled_statement_id', 'timestamp')
            try:
                if reference.get('kind') == 'compiled':
                    fields = ('compiled_statement_id', 'object_name', 'object_type', 'package_name', 'stat_id')
                    table = 'MON$COMPILED_STATEMENTS'
                    where = 'MON$COMPILED_STATEMENT_ID = ?'
                    parameters = (int(reference['compiled_statement_id']),)
                else:
                    table = 'MON$STATEMENTS'
                    where = ('MON$STATEMENT_ID = ? AND MON$ATTACHMENT_ID = ? '
                             'AND MON$ATTACHMENT_ID <> CURRENT_CONNECTION')
                    parameters = (int(reference['statement_id']), int(reference['attachment_id']))
                cursor.execute('SELECT ' + ', '.join('MON$' + field.upper() for field in fields) + ', '
                    'CAST(SUBSTRING(MON$SQL_TEXT FROM 1 FOR 4097) AS VARCHAR(4097) CHARACTER SET UTF8), '
                    'CAST(SUBSTRING(MON$EXPLAINED_PLAN FROM 1 FOR 4097) AS VARCHAR(4097) CHARACTER SET UTF8) '
                    'FROM ' + table + ' WHERE ' + where, parameters)
                if connection.main_transaction.info.is_read_only() is not True:
                    raise RelationalClientError('Statement inspection must use a read-only transaction')
                row = cursor.fetchone()
                if row is None:
                    return {'status': 'gone', 'observed_at': _utc()}
                if len(row) != len(fields) + 2:
                    raise RelationalClientError('Invalid native statement detail')
                identity = _wire(dict(zip(fields, row[:len(fields)])))
                checked_fields = tuple(key for key in fields if key != 'stat_id')
                if any(identity[key] != reference.get(key) for key in checked_fields):
                    return {'status': 'changed', 'observed_at': _utc()}
                result = {'status': 'available', 'observed_at': _utc(), 'identity': identity,
                          'source_epoch': self._source_epoch, 'history': 'not-retained', 'limit_characters': 4096}
                for key, value in zip(('sql_text', 'explained_plan'), row[len(fields):]):
                    if value is not None and not isinstance(value, str):
                        raise RelationalClientError('Expected bounded native statement text')
                    result[key] = {'value': None if value is None else value[:4096],
                                   'truncated': value is not None and len(value) > 4096}
                if reference.get('kind') != 'compiled':
                    stack_fields = ('call_id', 'statement_id', 'caller_id', 'object_name',
                                    'object_type', 'timestamp', 'source_line', 'source_column',
                                    'package_name', 'compiled_statement_id')
                    try:
                        stack = inventory_rows(cursor, 'SELECT FIRST 101 ' +
                            ', '.join('MON$' + field.upper() for field in stack_fields) +
                            ' FROM MON$CALL_STACK WHERE MON$STATEMENT_ID = ? ORDER BY MON$CALL_ID',
                            stack_fields, (int(reference['statement_id']),))
                        result['call_stack'] = {'status': 'available', **_wire(stack)}
                    except Exception as error:
                        result['call_stack'] = {'status': 'unavailable', 'error_type': type(error).__name__}
                return result
            except Exception:
                self._needs_release = True
                raise
            finally:
                try:
                    cursor.close()
                except BaseException:
                    self._needs_release = True
                    raise
                finally:
                    try:
                        connection.rollback()
                    except Exception:
                        self._needs_release = True
                        raise

    def _release(self):
        if self._connection is not None:
            self._client._forget_and_close(self._connection)
            self._connection = None
        # Also retries handles retained by failed connection initialization.
        # Do not close the client itself: a future policy tick may reconnect.
        for connection in tuple(self._client._connections):
            self._client._forget_and_close(connection)
        self._needs_release = False

    def inspect_details(self, operation, source_epoch):
        with self._lock:
            if (self._closed or self._needs_release or self._connection is None or
                    source_epoch != self._source_epoch):
                return {'status': 'unavailable', 'reason': 'collector-epoch-unavailable'}
            result = {'status': 'available', 'operation': operation,
                      'observed_at': _utc(), 'history': 'not-retained'}
            if operation == 'accounts' and self.scope == 'database':
                cursor = self._connection.cursor()
                try:
                    fields = ('user_name', 'plugin', 'active', 'admin',
                              'first_name', 'middle_name', 'last_name')
                    result.update(inventory_rows(cursor,
                        'SELECT FIRST 101 ' + ', '.join('SEC$' + f.upper() for f in fields) +
                        ' FROM SEC$USERS ORDER BY SEC$PLUGIN, SEC$USER_NAME', fields))
                    if self._connection.main_transaction.info.is_read_only() is not True:
                        raise RelationalClientError('Account inspection must be read-only')
                    return _wire(result)
                finally:
                    try:
                        cursor.close()
                    except BaseException:
                        self._needs_release = True
                        raise
                    finally:
                        try:
                            self._connection.rollback()
                        except BaseException:
                            self._needs_release = True
                            raise
            if operation not in ('server-log', 'server-paths') or self.scope != 'server':
                raise ValueError('Unsupported monitoring detail scope')
            handle = None
            try:
                handle = self._client._connect_server({'route': self._route})
                if operation == 'server-paths':
                    result['rows'] = [{'name': name, 'value': getattr(handle.info, name)}
                                      for name in ('home_directory', 'lock_directory',
                                                   'message_directory', 'security_database')]
                else:
                    handle.info.get_log()
                    started = self._clock()
                    output, count, ended, attempts = [], 0, False, 0
                    while attempts < 1000 and count < 65536 and self._clock() - started < 5 * 10**9:
                        attempts += 1
                        line = handle.readline_timed(1)
                        if line is None:
                            ended = True
                            break
                        if not isinstance(line, str):
                            continue  # Driver TIMEOUT sentinel; bounded by observation clock.
                        encoded = line.encode('utf-8')
                        remaining = 65536 - count
                        output.append(encoded[:remaining].decode('utf-8', errors='ignore'))
                        count += min(len(encoded), remaining)
                        if len(encoded) > remaining:
                            break
                    result.update(text=''.join(output), truncated=not ended,
                                  limit_bytes=65536, limit_lines=1000, position='prefix')
                return _wire(result)
            except BaseException:
                self._needs_release = True
                raise
            finally:
                if handle is not None:
                    try:
                        self._client._forget_and_close(handle)
                    except BaseException:
                        self._needs_release = True
                        raise

    @staticmethod
    def _group(result, name, source, callback):
        try:
            value = callback()
        except Exception as error:
            result['groups'][name] = {
                'status': 'unavailable', 'source': source,
                'error_type': type(error).__name__,
            }
            return None
        result['groups'][name] = {'status': 'available', 'source': source,
                                  'values': value}
        return value

    def _database(self, result):
        connection = self._connection
        cursor = connection.cursor()
        try:
            identity = _one(cursor,
                'SELECT CURRENT_CONNECTION, CURRENT_TRANSACTION, CURRENT_USER,'
                " RDB$GET_CONTEXT('SYSTEM', 'ENGINE_VERSION') FROM RDB$DATABASE",
                ('attachment_id', 'transaction_id', 'user', 'engine_version'))
            if connection.main_transaction.info.is_read_only() is not True:
                raise RelationalClientError(
                    'Monitoring transaction is not confirmed read-only')
            result['collector'] = identity
            database = _one(cursor, 'SELECT ' + ', '.join(
                'MON$' + field for field in DATABASE_FIELDS) +
                ' FROM MON$DATABASE', DATABASE_FIELDS)
            result['groups']['database'] = {
                'status': 'available', 'source': 'MON$DATABASE',
                'values': database}
            # Timestamp the actual snapshot before the remaining queries.
            observed = self._clock()
            privilege = self._group(result, 'visibility',
                'CURRENT_USER / MON$OWNER / RDB$SYSTEM_PRIVILEGE',
                lambda: _one(cursor,
                    "SELECT CURRENT_USER = 'SYSDBA' OR "
                    'CURRENT_USER = MON$OWNER OR '
                    'RDB$SYSTEM_PRIVILEGE(MONITOR_ANY_ATTACHMENT) '
                    'FROM MON$DATABASE', ('all_attachments',)))
            result['coverage'] = ('database' if privilege and
                privilege['all_attachments'] else 'visible-to-collector')
            self._group(result, 'attachments', 'MON$ATTACHMENTS',
                lambda: _one(cursor,
                    'SELECT COUNT(*), COUNT(CASE WHEN MON$ATTACHMENT_ID = '
                    'CURRENT_CONNECTION THEN 1 END), '
                    'COUNT(CASE WHEN MON$ATTACHMENT_ID <> CURRENT_CONNECTION '
                    'AND MON$SYSTEM_FLAG = 0 THEN 1 END), '
                    'COUNT(CASE WHEN MON$SYSTEM_FLAG = 1 THEN 1 END), '
                    'COUNT(CASE WHEN MON$ATTACHMENT_ID <> CURRENT_CONNECTION '
                    'AND MON$SYSTEM_FLAG = 0 AND MON$STATE = 1 THEN 1 END), '
                    'COUNT(CASE WHEN MON$ATTACHMENT_ID <> CURRENT_CONNECTION '
                    'AND MON$SYSTEM_FLAG = 0 AND MON$STATE = 0 THEN 1 END) '
                    'FROM MON$ATTACHMENTS',
                    ('visible_total', 'collector', 'user', 'system',
                     'active_user', 'idle_user')))
            self._group(result, 'transactions', 'MON$TRANSACTIONS',
                lambda: _one(cursor,
                    'SELECT COUNT(*), COUNT(CASE WHEN MON$STATE = 1 '
                    'THEN 1 END), COUNT(CASE WHEN MON$READ_ONLY = 1 THEN 1 END), '
                    'MAX(DATEDIFF(SECOND FROM MON$TIMESTAMP TO LOCALTIMESTAMP)) '
                    'FROM MON$TRANSACTIONS WHERE MON$ATTACHMENT_ID <> '
                    'CURRENT_CONNECTION',
                    ('visible_total', 'active', 'read_only', 'oldest_age_seconds')))
            for name, (table, fields) in DETAIL_FIELDS.items():
                self._group(result, name, 'MON$' + table,
                            lambda t=table, f=fields: _details(cursor, t, f))
            counters = {}
            complete = True
            for name, table, fields in (
                    ('io', 'IO_STATS', IO_FIELDS),
                    ('records', 'RECORD_STATS', RECORD_FIELDS),
                    ('memory', 'MEMORY_USAGE', MEMORY_FIELDS)):
                values = self._group(result, name, 'MON$' + table + ' group 0',
                                     lambda t=table, f=fields: _stats(cursor, t, f))
                if name != 'memory':
                    if values is None or any(type(v) is not int or v < 0
                                             for v in values.values()):
                        complete = False
                    else:
                        counters.update({name + '.' + k: v
                                         for k, v in values.items()})
            result['derived'] = {
                'allocated_bytes': database['pages'] * database['page_size'],
                'configured_cache_bytes': database['page_buffers'] *
                    database['page_size'],
                'next_minus_oit': database['next_transaction'] -
                    database['oldest_transaction'],
                'next_minus_oat': database['next_transaction'] -
                    database['oldest_active'],
                'next_minus_ost': database['next_transaction'] -
                    database['oldest_snapshot'],
            }
            if complete:
                result['rates'] = self._counters.observe(
                    (database['guid'], database['file_id'], self._source_epoch,
                     identity['engine_version'], result['coverage']),
                    counters, observed)
            else:
                self._counters.reset()
                result['rates'] = {'epoch': self._counters.epoch,
                                   'status': 'gap', 'reason': 'missing-counters',
                                   'delta': {}, 'per_second': {}}
            self._inventory(cursor, result, observed)
        finally:
            try:
                cursor.close()
            finally:
                # Never retain the MON$ snapshot, including on query failure.
                connection.rollback()
        result['transaction_refresh'] = {
            'status': 'completed', 'read_only': True, 'retaining': False,
        }

    def _inventory(self, cursor, result, observed):
        for name, (source, fields, sql) in ACTIVITY.items():
            self._group(result, name, source,
                        lambda s=sql, f=fields: inventory_rows(cursor, s, f))
            result['groups'][name]['observed_at'] = result['started_at']
        table_group = result['groups']['table_details']
        retained = {}
        if table_group['status'] == 'available':
            for row in table_group['values']['rows']:
                key = (row['table_name'], row['relation_id'])
                counters = {field: row[field] for field in TABLE_COUNTERS}
                if any(type(value) is not int or value < 0 for value in counters.values()):
                    row['rate_status'] = 'unavailable'
                    continue
                epoch = self._table_counters.get(key, CounterEpoch())
                rates = epoch.observe((self._source_epoch, result.get('coverage'), key),
                                      counters, observed)
                row['rate_status'] = rates['status']
                row['rate_epoch'] = rates['epoch']
                row['rate_gap_reason'] = rates.get('reason')
                for field in TABLE_COUNTERS:
                    row[field + '_per_second'] = rates['per_second'].get(field)
                retained[key] = epoch
        self._table_counters = retained
        if (self._metadata_cache is None or self._metadata_observed_ns is None or
                observed - self._metadata_observed_ns >= self._metadata_interval_seconds * 10**9):
            collected = {'groups': {}}
            for name, (source, fields, sql) in METADATA.items():
                self._group(collected, name, source,
                            lambda s=sql, f=fields: inventory_rows(cursor, s, f))
                collected['groups'][name]['observed_at'] = result['started_at']
            self._group(collected, 'page_inventory', 'native attachment database information',
                        self._page_inventory)
            collected['groups']['page_inventory']['observed_at'] = result['started_at']
            self._group(collected, 'crypt_identity', 'native crypt plugin/key names (not key material)',
                        self._crypt_identity)
            collected['groups']['crypt_identity']['observed_at'] = result['started_at']
            self._metadata_cache = collected['groups']
            self._metadata_observed_ns = observed
        for name, group in self._metadata_cache.items():
            result['groups'][name] = copy.deepcopy(group)
            result['groups'][name]['age_seconds'] = str(
                Decimal(observed - self._metadata_observed_ns) / Decimal(10**9))
            result['groups'][name]['refresh_interval_seconds'] = self._metadata_interval_seconds

    def _page_inventory(self):
        values = {}
        for name in ('pages_used', 'pages_free'):
            value = getattr(self._connection.info, name)
            if type(value) is not int or value < 0:
                raise RelationalClientError('Invalid native page inventory')
            values[name] = value
        return {'rows': [values], 'limit': 1, 'truncated': False,
                'scope': 'native allocation information; independent of MON$ snapshot'}

    def _crypt_identity(self):
        from firebird.driver import DbInfoCode
        values = {}
        for name, code in (('plugin_name', DbInfoCode.CRYPT_PLUGIN), ('key_name', DbInfoCode.CRYPT_KEY)):
            value = self._connection.info.get_info(code)
            if value is not None and not isinstance(value, str):
                raise RelationalClientError('Invalid native encryption identity')
            values[name] = value
        return {'rows': [values], 'limit': 1, 'truncated': False}

    def _server(self, result):
        info = self._connection.info
        for name in ('version', 'engine_version', 'architecture',
                     'manager_version', 'capabilities', 'connection_count',
                     'attached_databases'):
            self._group(result, name, 'firebird.driver.ServerInfoProvider.' + name,
                        lambda n=name: getattr(info, n))
        if not any(group['status'] == 'available'
                   for group in result['groups'].values()):
            raise RelationalClientError('Service monitoring is unavailable')
        result['service_probe'] = {
            'status': 'completed' if any(
                result['groups'][name]['status'] == 'available'
                for name in ('connection_count', 'attached_databases'))
            else 'unavailable',
        }
        if result['service_probe']['status'] != 'completed':
            raise RelationalClientError('Fresh service observation is unavailable')
        result['coverage'] = 'service-visible-attached-databases'

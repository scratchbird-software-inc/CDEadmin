"""Native MySQL-dialect administration shared by MySQL-wire providers.

An engine declares only the features it executes and reads back (each was
probed live before it was declared). Every operation compiles to native
statements, and its inspector and confirmation read the result back from
the engine's own catalog; nothing is inferred from acceptance alone.
"""

import re

from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.visual_admin import (
    ControlPlaneOperation,
    control_plane_field as cp_field,
)


IDENTIFIER = r'[^`\x00\r\n]{1,64}'
COLLATION = r'[A-Za-z0-9_]+'
ACCOUNT_PART = r'[^\x00\r\n]*'
VARIABLE = r'[A-Za-z_][A-Za-z0-9_]{0,127}'
TTL_UNITS = ('SECOND', 'MINUTE', 'HOUR', 'DAY', 'WEEK', 'MONTH', 'YEAR')
_JOB_INTERVAL = r'[1-9][0-9]{0,5}[smhd]'
_DIGEST = r'[0-9a-f]{64}'
_BINDABLE = re.compile(r'\s*(SELECT|INSERT|UPDATE|DELETE|REPLACE|WITH)\b',
                       re.IGNORECASE)

_TABLE_OPTIONS = {
    'comment': lambda: cp_field(
        'comment', 'Comment', 'text', False, max_length=2048),
    'auto_increment': lambda: cp_field(
        'auto_increment', 'Next AUTO_INCREMENT value', 'number', False,
        minimum=1, maximum=2 ** 63 - 1,
        help='Only for a table with an AUTO_INCREMENT column.'),
    'collation': lambda: cp_field(
        'collation', 'Default collation', 'text', False, max_length=64,
        pattern=COLLATION),
    'shard_row_id_bits': lambda: cp_field(
        'shard_row_id_bits', 'Row ID shard bits', 'number', False,
        minimum=0, maximum=15,
        help='Only for a table without a clustered primary key.'),
}


def _member_fields(admin_option):
    fields = [
        cp_field('member_user', 'Recipient user', 'text', True,
                 max_length=32, pattern=ACCOUNT_PART),
        cp_field('member_host', 'Recipient host', 'text', True,
                 max_length=255, pattern=ACCOUNT_PART, default='%'),
    ]
    if admin_option:
        fields.append(cp_field('admin_option', 'Allow delegation', 'boolean',
                               False, default=False))
    return tuple(fields)


class MySQLWireAdministration:
    """The native administration one engine declares.

    ``features`` maps an operation key to its options:

    - ``('table', 'set_options')``: the admitted option names;
    - ``('table', 'analyze')``: ``'dolt_statistics'`` or ``'analyze_jobs'``;
    - ``('role', 'grant')``: whether ``WITH ADMIN OPTION`` is admitted;
    - ``('session', ...)``: the process-list table to read back from;
    - other keys: ``True``.
    """

    def __init__(self, engine_name, features):
        self.engine_name = engine_name
        self.features = dict(features)

    def supports(self, kind, operation):
        return (kind, operation) in self.features

    def _error(self, message):
        return RelationalClientError(f'{self.engine_name} {message}')

    # Declarations -----------------------------------------------------

    def operations(self):
        values = []
        for (kind, operation), option in self.features.items():
            values.append(self._operation(kind, operation, option))
        return tuple(values)

    def _operation(self, kind, operation, option):
        if (kind, operation) == ('table', 'set_options'):
            return ControlPlaneOperation(
                'table', 'set_options', 'Set table options', 'admin',
                'administer', tuple(_TABLE_OPTIONS[name]() for name in option),
                impact_scope='resource')
        if (kind, operation) == ('table', 'analyze'):
            return ControlPlaneOperation(
                'table', 'analyze', 'Analyze table', 'admin',
                'maintenance_admin', confirmation_required=False,
                impact_scope='resource')
        if (kind, operation) == ('table', 'set_cache'):
            return ControlPlaneOperation(
                'table', 'set_cache', 'Set table caching', 'admin',
                'administer', (cp_field(
                    'cached', 'Cache the table in memory', 'select', True,
                    options=[{'value': 'ON', 'label': 'Cached'},
                             {'value': 'OFF', 'label': 'Not cached'}]),),
                impact_scope='resource')
        if (kind, operation) in {('table', 'lock_stats'),
                                 ('table', 'unlock_stats')}:
            title = ('Lock statistics' if operation == 'lock_stats'
                     else 'Unlock statistics')
            return ControlPlaneOperation(
                'table', operation, title, 'admin', 'maintenance_admin',
                impact_scope='resource')
        if (kind, operation) == ('index', 'rename'):
            return ControlPlaneOperation(
                'index', 'rename', 'Rename index', 'admin', 'administer', (
                    cp_field('new_name', 'New name', 'text', True,
                             max_length=64, pattern=IDENTIFIER),
                ), impact_scope='resource')
        if (kind, operation) == ('index', 'visibility'):
            return ControlPlaneOperation(
                'index', 'visibility', 'Set index visibility', 'admin',
                'administer', (cp_field(
                    'visibility', 'Visibility', 'select', True,
                    options=[{'value': 'VISIBLE', 'label': 'Visible'},
                             {'value': 'INVISIBLE', 'label': 'Invisible'}]),),
                impact_scope='resource')
        if (kind, operation) == ('role', 'grant'):
            return ControlPlaneOperation(
                'role', 'grant', 'Grant role membership', 'admin',
                'security_admin', _member_fields(bool(option)),
                impact_scope='resource')
        if (kind, operation) == ('role', 'revoke'):
            return ControlPlaneOperation(
                'role', 'revoke', 'Revoke role membership', 'admin',
                'security_admin', _member_fields(False),
                impact_scope='resource')
        if (kind, operation) == ('role', 'set_default'):
            return ControlPlaneOperation(
                'role', 'set_default', 'Make default role of member', 'admin',
                'security_admin', _member_fields(False),
                impact_scope='resource')
        if (kind, operation) == ('user', 'rename'):
            return ControlPlaneOperation(
                'user', 'rename', 'Rename account', 'admin', 'security_admin',
                (
                    cp_field('new_user', 'New user name', 'text', True,
                             max_length=32, pattern=ACCOUNT_PART),
                    cp_field('new_host', 'New host', 'text', True,
                             max_length=255, pattern=ACCOUNT_PART),
                ), impact_scope='resource')
        if (kind, operation) == ('table', 'set_ttl'):
            return ControlPlaneOperation(
                'table', 'set_ttl', 'Set row expiry (TTL)', 'admin',
                'administer', (
                    cp_field('column', 'Time column', 'text', True,
                             max_length=64, pattern=IDENTIFIER,
                             help='A DATE, DATETIME or TIMESTAMP column.'),
                    cp_field('interval', 'Expire after', 'number', True,
                             minimum=1, maximum=1000000),
                    cp_field('unit', 'Unit', 'select', True, default='DAY',
                             options=[{'value': unit, 'label': unit.title()}
                                      for unit in TTL_UNITS]),
                    cp_field('enabled', 'Delete expired rows', 'boolean',
                             False, default=True),
                    cp_field('job_interval', 'Job interval', 'text', False,
                             max_length=8, pattern=_JOB_INTERVAL,
                             help='How often the TTL job runs, e.g. 1h.'),
                ), impact_scope='resource')
        if (kind, operation) == ('table', 'remove_ttl'):
            return ControlPlaneOperation(
                'table', 'remove_ttl', 'Remove row expiry (TTL)', 'admin',
                'administer', impact_scope='resource')
        if (kind, operation) == ('binding', 'create'):
            return ControlPlaneOperation(
                'binding', 'create', 'Create SQL plan binding', 'admin',
                'administer', (
                    cp_field('original_sql', 'Statement', 'multiline', True,
                             max_length=65536,
                             help='The statement to bind, as the '
                             'application sends it.'),
                    cp_field('bind_sql', 'Statement with hints',
                             'multiline', True, max_length=65536,
                             help='The same statement with optimizer hints, '
                             'e.g. /*+ USE_INDEX(t, k) */.'),
                ), target_required=False, impact_scope='database')
        if (kind, operation) == ('binding', 'set_status'):
            return ControlPlaneOperation(
                'binding', 'set_status', 'Enable or disable binding',
                'admin', 'administer', (cp_field(
                    'status', 'Status', 'select', True, options=[
                        {'value': 'ENABLED', 'label': 'Enabled'},
                        {'value': 'DISABLED', 'label': 'Disabled'}]),),
                impact_scope='database')
        if (kind, operation) == ('binding', 'drop'):
            return ControlPlaneOperation(
                'binding', 'drop', 'Drop binding', 'destructive',
                'administer', impact_scope='database')
        if (kind, operation) == ('database', 'flashback_table'):
            return ControlPlaneOperation(
                'database', 'flashback_table', 'Recover dropped table',
                'admin', 'administer', (
                    cp_field('table', 'Dropped table', 'text', True,
                             max_length=64, pattern=IDENTIFIER),
                    cp_field('new_name', 'Recover as', 'text', False,
                             max_length=64, pattern=IDENTIFIER,
                             help='Empty: the original name.'),
                ), impact_scope='database')
        if (kind, operation) == ('session', 'terminate_query'):
            return ControlPlaneOperation(
                'session', 'terminate_query', 'Terminate running statement',
                'admin', 'administer', impact_scope='resource')
        if (kind, operation) == ('session', 'terminate_connection'):
            return ControlPlaneOperation(
                'session', 'terminate_connection', 'Terminate connection',
                'destructive', 'administer', impact_scope='resource')
        if (kind, operation) == ('system-variable', 'set_global'):
            return ControlPlaneOperation(
                'system-variable', 'set_global', 'Set global value', 'admin',
                'administer', (
                    cp_field('value', 'Value', 'text', True, max_length=4096,
                             help='Applies until the server restarts.'),
                ), impact_scope='cluster')
        raise ValueError(f'undeclared MySQL-wire operation {kind}.{operation}')

    # Targets ----------------------------------------------------------

    def _path(self, request, length):
        target = request.get('target_resource')
        path = target.get('display_path') if isinstance(target, dict) else None
        if not isinstance(path, list) or len(path) != length or not all(
                isinstance(item, str) and item for item in path):
            raise self._error('control target is invalid')
        return path

    def _name(self, request):
        target = request.get('target_resource')
        name = target.get('display_name') if isinstance(target, dict) else None
        if not isinstance(name, str) or not name:
            raise self._error('control target is required')
        return name

    def _account(self, request):
        target = request.get('target_resource') or {}
        native = target.get('native') if isinstance(target, dict) else None
        if not isinstance(native, dict) or not all(
                isinstance(native.get(key), str) for key in ('user', 'host')):
            raise self._error('account identity is unavailable')
        return native['user'], native['host']

    def _member(self, draft):
        member = (draft.get('member_user'), draft.get('member_host'))
        if not all(isinstance(item, str) and re.fullmatch(
                ACCOUNT_PART, item) for item in member):
            raise self._error('role member is invalid')
        return member

    def _session(self, request):
        value = self._name(request)
        if not re.fullmatch(r'[1-9][0-9]{0,19}', value):
            raise self._error('session identity is invalid')
        return int(value)

    def _variable(self, request):
        name = self._name(request)
        if not re.fullmatch(VARIABLE, name):
            raise self._error('variable name is invalid')
        return name

    # Compilation ------------------------------------------------------

    def statements(self, request):
        kind = request['resource_kind']
        operation = request['operation_id']
        if not self.supports(kind, operation):
            raise self._error('control-plane operation is unavailable')
        draft = request.get('draft') or {}
        option = self.features[(kind, operation)]
        if kind == 'binding':
            if operation == 'create':
                return [_statement(
                    'CREATE GLOBAL BINDING FOR ' +
                    self._bindable(draft.get('original_sql')) + ' USING ' +
                    self._bindable(draft.get('bind_sql')))]
            digest = self._digest(request)
            if operation == 'drop':
                return [_statement('DROP GLOBAL BINDING FOR SQL DIGEST ' +
                                   _literal(digest))]
            if draft.get('status') not in {'ENABLED', 'DISABLED'}:
                raise self._error('binding status is invalid')
            return [_statement('SET BINDING ' + draft['status'] +
                               ' FOR SQL DIGEST ' + _literal(digest))]
        if kind == 'database' and operation == 'flashback_table':
            database = self._name(request)
            table = draft.get('table')
            if not isinstance(table, str) or not re.fullmatch(
                    IDENTIFIER, table):
                raise self._error('dropped table name is invalid')
            source = ('FLASHBACK TABLE ' + quote(database) + '.' +
                      quote(table))
            if draft.get('new_name') not in (None, ''):
                if not re.fullmatch(IDENTIFIER, draft['new_name']):
                    raise self._error('recovered table name is invalid')
                source += ' TO ' + quote(draft['new_name'])
            return [_statement(source)]
        if kind == 'table':
            database, table = self._path(request, 2)
            qualified = quote(database) + '.' + quote(table)
            if operation == 'set_ttl':
                return [_statement('ALTER TABLE ' + qualified + ' ' +
                                   ' '.join(self._ttl_clauses(draft)))]
            if operation == 'remove_ttl':
                return [_statement('ALTER TABLE ' + qualified +
                                   ' REMOVE TTL')]
            if operation == 'set_options':
                return self._table_options(qualified, draft, option)
            if operation == 'analyze':
                if option == 'dolt_statistics':
                    # Live, Dolt 1.86.6: only tables of the session database
                    # are analyzed; a qualified name elsewhere returns an
                    # error row instead of an error.
                    route = request.get('_provider_route') or {}
                    current = route.get('database')
                    if not isinstance(current, str) or (
                            current.split('/', 1)[0] != database):
                        raise self._error(
                            'analyzes tables of the connection database only')
                    return [_statement('ANALYZE TABLE ' + quote(table))]
                return [_statement('ANALYZE TABLE ' + qualified)]
            if operation == 'set_cache':
                if draft.get('cached') not in {'ON', 'OFF'}:
                    raise self._error('table caching choice is invalid')
                return [_statement('ALTER TABLE ' + qualified + (
                    ' CACHE' if draft['cached'] == 'ON' else ' NOCACHE'))]
            keyword = 'LOCK' if operation == 'lock_stats' else 'UNLOCK'
            return [_statement(keyword + ' STATS ' + qualified)]
        if kind == 'index':
            database, table, index = self._path(request, 3)
            prefix = ('ALTER TABLE ' + quote(database) + '.' + quote(table))
            if operation == 'rename':
                new_name = draft.get('new_name')
                if not isinstance(new_name, str) or not re.fullmatch(
                        IDENTIFIER, new_name) or new_name == index:
                    raise self._error('index name is invalid')
                return [_statement(prefix + ' RENAME INDEX ' + quote(index) +
                                   ' TO ' + quote(new_name))]
            if draft.get('visibility') not in {'VISIBLE', 'INVISIBLE'}:
                raise self._error('index visibility is invalid')
            return [_statement(prefix + ' ALTER INDEX ' + quote(index) + ' ' +
                               draft['visibility'])]
        if kind == 'role':
            role = self._account(request)
            member = self._member(draft)
            if operation == 'grant':
                source = 'GRANT %s@%s TO %s@%s'
                if draft.get('admin_option'):
                    if not option:
                        raise self._error('has no delegated role membership')
                    source += ' WITH ADMIN OPTION'
            elif operation == 'revoke':
                source = 'REVOKE %s@%s FROM %s@%s'
            else:
                source = 'SET DEFAULT ROLE %s@%s TO %s@%s'
            return [{'source': source, 'parameters': (*role, *member)}]
        if kind == 'user':
            account = self._account(request)
            renamed = (draft.get('new_user'), draft.get('new_host'))
            if not all(isinstance(item, str) and re.fullmatch(
                    ACCOUNT_PART, item) for item in renamed) or (
                    renamed == account):
                raise self._error('new account name is invalid')
            return [{'source': 'RENAME USER %s@%s TO %s@%s',
                     'parameters': (*account, *renamed)}]
        if kind == 'session':
            prefix = ('KILL QUERY ' if operation == 'terminate_query'
                      else 'KILL ')
            return [_statement(prefix + str(self._session(request)))]
        name = self._variable(request)
        if not isinstance(draft.get('value'), str):
            raise self._error('variable value is required')
        return [{'source': 'SET @@GLOBAL.' + name + ' = %s',
                 'parameters': (draft['value'],)}]

    def _bindable(self, value):
        if not isinstance(value, str):
            raise self._error('binding statement is required')
        text = value.strip().rstrip(';').strip()
        # One statement only; EXPLAIN of it is the read-back.
        if not text or ';' in text or not _BINDABLE.match(text) or (
                '\x00' in text):
            raise self._error(
                'a binding is one SELECT, INSERT, UPDATE, DELETE or REPLACE')
        return text

    def _digest(self, request):
        value = self._name(request)
        if not re.fullmatch(_DIGEST, value):
            raise self._error('binding digest is invalid')
        return value

    @staticmethod
    def _ttl_clauses(draft):
        column, interval = draft.get('column'), draft.get('interval')
        unit = draft.get('unit') or 'DAY'
        if not isinstance(column, str) or not re.fullmatch(IDENTIFIER, column):
            raise RelationalClientError('TTL column is invalid')
        if isinstance(interval, bool) or not isinstance(interval, int) or (
                interval < 1) or unit not in TTL_UNITS:
            raise RelationalClientError('TTL interval is invalid')
        clauses = [f'TTL = {quote(column)} + INTERVAL {interval} {unit}',
                   "TTL_ENABLE = '" + ('OFF' if draft.get('enabled') is False
                                       else 'ON') + "'"]
        if draft.get('job_interval') not in (None, ''):
            if not re.fullmatch(_JOB_INTERVAL, str(draft['job_interval'])):
                raise RelationalClientError('TTL job interval is invalid')
            clauses.append(f"TTL_JOB_INTERVAL = '{draft['job_interval']}'")
        return clauses

    def _table_options(self, qualified, draft, admitted):
        clauses, parameters, separate = [], [], []
        for name in draft:
            if name in _TABLE_OPTIONS and name not in admitted and (
                    draft[name] not in (None, '')):
                raise self._error(f'does not offer table option {name}')
        if draft.get('comment') not in (None, ''):
            clauses.append('COMMENT = %s')
            parameters.append(draft['comment'])
        for name, keyword, minimum in (
                ('auto_increment', 'AUTO_INCREMENT', 1),
                ('shard_row_id_bits', 'SHARD_ROW_ID_BITS', 0)):
            value = draft.get(name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int) or (
                    value < minimum):
                raise self._error(f'{keyword} value is invalid')
            if name == 'shard_row_id_bits':
                # TiDB 8.5.6: "Unsupported multi schema change for shard
                # row ID" when combined with any other change.
                separate.append(_statement(
                    'ALTER TABLE ' + qualified + ' ' + keyword + ' = ' +
                    str(value)))
            else:
                clauses.append(keyword + ' = ' + str(value))
        if draft.get('collation') not in (None, ''):
            if not re.fullmatch(COLLATION, draft['collation']):
                raise self._error('collation is invalid')
            clauses.append('DEFAULT COLLATE ' + quote(draft['collation']))
        if not clauses and not separate:
            raise self._error('needs at least one table option')
        combined = [{'source': ('ALTER TABLE ' + qualified + ' ' +
                                ', '.join(clauses)),
                     'parameters': tuple(parameters)}] if clauses else []
        return combined + separate

    # Read-back --------------------------------------------------------

    def inspect(self, plan, query, sequence=None):
        kind = plan['resource_kind']
        operation = plan['operation_id']
        draft = plan.get('draft') or {}
        option = self.features[(kind, operation)]
        if kind == 'binding' and operation == 'create':
            # EXPLAIN plans without executing, DML included; the session
            # flag says whether a binding chose the plan (live, TiDB 8.5.6).
            if not callable(sequence):
                raise self._error('binding read-back needs one session')
            return sequence([
                ('EXPLAIN ' + self._bindable(draft.get('original_sql')), ()),
                ('SELECT @@last_plan_from_binding', ())])
        if kind == 'binding':
            return query('SHOW GLOBAL BINDINGS WHERE Sql_digest = %s',
                         (self._digest(plan),))
        if kind == 'database' and operation == 'flashback_table':
            return query(
                'SELECT TABLE_NAME FROM information_schema.TABLES '
                'WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s',
                (self._name(plan), draft.get('new_name') or draft.get(
                    'table')))
        if kind == 'table' and operation in {'set_ttl', 'remove_ttl'}:
            database, table = self._path(plan, 2)
            return query('SHOW CREATE TABLE ' + quote(database) + '.' +
                         quote(table))
        if kind == 'table':
            database, table = self._path(plan, 2)
            if operation == 'analyze' and option == 'dolt_statistics':
                return query(
                    'SELECT index_name, row_count FROM ' + quote(database) +
                    '.dolt_statistics WHERE table_name = %s', (table,))
            if operation == 'analyze':
                # The newest job for this table, finished within ten minutes
                # by the server's own clock.
                return query(
                    'SELECT state, end_time >= NOW() - INTERVAL 10 MINUTE '
                    'FROM mysql.analyze_jobs WHERE table_schema = %s AND '
                    'table_name = %s ORDER BY id DESC LIMIT 1',
                    (database, table))
            if operation in {'lock_stats', 'unlock_stats'}:
                return query(
                    'SHOW STATS_LOCKED WHERE Db_name = %s AND Table_name = %s',
                    (database, table))
            return query(
                'SELECT TABLE_COMMENT, AUTO_INCREMENT, TABLE_COLLATION, ' + (
                    'TIDB_ROW_ID_SHARDING_INFO, CREATE_OPTIONS'
                    if 'shard_row_id_bits' in self._table_option_names()
                    or self.supports('table', 'set_cache')
                    else 'NULL, NULL') +
                ' FROM information_schema.TABLES '
                'WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s',
                (database, table))
        if kind == 'index':
            database, table, index = self._path(plan, 3)
            if operation == 'visibility':
                return query(
                    'SELECT DISTINCT IS_VISIBLE FROM '
                    'information_schema.STATISTICS WHERE TABLE_SCHEMA = %s '
                    'AND TABLE_NAME = %s AND INDEX_NAME = %s',
                    (database, table, index))
            return query(
                'SELECT DISTINCT INDEX_NAME FROM '
                'information_schema.STATISTICS '
                'WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s '
                'AND INDEX_NAME IN (%s, %s)',
                (database, table, index, draft.get('new_name')))
        if kind == 'role':
            member = (draft.get('member_user'), draft.get('member_host'))
            if operation == 'set_default':
                return query(
                    'SELECT DEFAULT_ROLE_USER, DEFAULT_ROLE_HOST '
                    'FROM mysql.default_roles WHERE USER = %s AND HOST = %s',
                    member)
            return query(
                'SELECT WITH_ADMIN_OPTION FROM mysql.role_edges '
                'WHERE FROM_USER = %s AND FROM_HOST = %s '
                'AND TO_USER = %s AND TO_HOST = %s',
                (*self._account(plan), *member))
        if kind == 'user':
            return query(
                'SELECT User, Host FROM mysql.user WHERE (User = %s AND '
                'Host = %s) OR (User = %s AND Host = %s)',
                (*self._account(plan), draft.get('new_user'),
                 draft.get('new_host')))
        if kind == 'session':
            return query(
                'SELECT ID, COMMAND, INFO FROM information_schema.' + option +
                ' WHERE ID = %s', (self._session(plan),))
        return query('SELECT @@GLOBAL.' + self._variable(plan))

    def _table_option_names(self):
        return self.features.get(('table', 'set_options'), ())

    def confirmed(self, plan, rows):
        kind = plan['resource_kind']
        operation = plan['operation_id']
        draft = plan.get('draft') or {}
        option = self.features[(kind, operation)]
        if kind == 'binding':
            if operation == 'create':
                return len(rows) == 1 and str(rows[0][0]) == '1'
            if operation == 'drop':
                return not rows
            return len(rows) == 1 and str(rows[0][3]).upper() == draft.get(
                'status')
        if kind == 'database' and operation == 'flashback_table':
            return len(rows) == 1
        if kind == 'table' and operation in {'set_ttl', 'remove_ttl'}:
            source = str(rows[0][1]) if len(rows) == 1 else ''
            if operation == 'remove_ttl':
                return bool(source) and '/*T![ttl]' not in source
            # SHOW CREATE TABLE renders each clause as /*T![ttl] K=V */.
            expected = [clause.replace(' = ', '=', 1)
                        for clause in self._ttl_clauses(draft)]
            return all(f'/*T![ttl] {clause} */' in source
                       for clause in expected)
        if kind == 'table':
            if operation == 'analyze':
                if option == 'dolt_statistics':
                    return bool(rows)
                return len(rows) == 1 and str(rows[0][0]) == 'finished' and (
                    bool(rows[0][1]))
            if operation == 'lock_stats':
                return len(rows) == 1 and str(rows[0][-1]) == 'locked'
            if operation == 'unlock_stats':
                return not rows
            if len(rows) != 1:
                return False
            comment, auto_increment, collation, sharding, created = rows[0]
            if operation == 'set_cache':
                cached = 'cached=on' in str(created or '').split()
                return cached == (draft.get('cached') == 'ON')
            return all((
                draft.get('comment') in (None, '') or
                str(comment) == draft['comment'],
                draft.get('auto_increment') is None or (
                    auto_increment is not None and
                    int(auto_increment) == draft['auto_increment']),
                draft.get('collation') in (None, '') or
                str(collation).lower() == draft['collation'].lower(),
                draft.get('shard_row_id_bits') is None or
                str(sharding) == f'SHARD_BITS={draft["shard_row_id_bits"]}'
                or (draft['shard_row_id_bits'] == 0 and
                    str(sharding) == 'NOT_SHARDED'),
            ))
        if kind == 'index':
            if operation == 'visibility':
                return [str(row[0]) for row in rows] == [
                    'YES' if draft.get('visibility') == 'VISIBLE' else 'NO']
            return {str(row[0]) for row in rows} == {draft.get('new_name')}
        if kind == 'role':
            if operation == 'revoke':
                return not rows
            if operation == 'set_default':
                return (self._account(plan)[0], self._account(plan)[1]) in {
                    (str(user), str(host)) for user, host in rows}
            return len(rows) == 1 and (
                str(rows[0][0]).upper() == 'Y') == bool(
                    draft.get('admin_option'))
        if kind == 'user':
            return [(str(user), str(host)) for user, host in rows] == [
                (draft.get('new_user'), draft.get('new_host'))]
        if kind == 'session':
            if operation == 'terminate_connection':
                return not rows
            return not rows or str(rows[0][1]) != 'Query'
        if len(rows) != 1:
            return False
        observed, requested = rows[0][0], draft.get('value')
        if str(observed) == requested:
            return True
        # Boolean variables read back as 0/1.
        flags = {'ON': '1', 'TRUE': '1', 'OFF': '0', 'FALSE': '0'}
        return str(observed) == flags.get(str(requested).upper())


def quote(value):
    return '`' + str(value).replace('`', '``') + '`'


def _literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def _statement(source):
    return {'source': source, 'parameters': ()}


def session_resources(cursor, generation, resource, optional_rows,
                      source='PROCESSLIST'):
    """List sessions with the fields the session operations read back."""
    values = []
    for session_id, user, host, database, command, seconds, state, info in \
            optional_rows(
                cursor,
                'SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, INFO '
                f'FROM information_schema.{source} ORDER BY ID'):
        values.append(resource('session', [], session_id, generation, {
            'user': str(user), 'host': str(host),
            'database': None if database is None else str(database),
            'command': str(command), 'seconds': int(seconds or 0),
            'state': str(state or ''),
            'statement': None if info is None else str(info),
        }))
    return values


def variable_resources(cursor, generation, resource, optional_rows):
    """List global system variables with their current values."""
    return [
        resource('system-variable', [], name, generation, {
            'value': None if value is None else str(value),
            'scope': 'global',
        })
        for name, value in optional_rows(cursor, 'SHOW GLOBAL VARIABLES')
    ]

"""Native PostgreSQL-dialect administration shared by PG-wire providers.

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


NAME = r'[^\x00-\x1f\x7f]{1,63}'
CLUSTER_SETTING = r'[a-z0-9_]+(\.[a-z0-9_]+)+'

# CockroachDB 26.1.3 table storage parameters that read back from
# pg_class.reloptions (live, 2026-11-01); fillfactor and autovacuum_enabled
# are accepted and discarded, so they are not offered.
STORAGE_PARAMETERS = {
    'exclude_data_from_backup': 'boolean',
    'schema_locked': 'boolean',
    'sql_stats_automatic_collection_enabled': 'boolean',
    'sql_stats_automatic_partial_collection_enabled': 'boolean',
    'sql_stats_forecasts_enabled': 'boolean',
    'sql_stats_automatic_collection_min_stale_rows': 'integer',
    'sql_stats_automatic_collection_fraction_stale_rows': 'number',
    'sql_stats_histogram_samples_count': 'integer',
    'sql_stats_histogram_buckets_count': 'integer',
}
ABSENT_VALUES = {'schema_locked': 'false'}
SETTING = r'[a-z_][a-z0-9_.]{0,127}'
VALUE = r'[^\x00-\x1f\x7f]{0,4096}'

_GRANT_TITLES = {'database': 'database', 'schema': 'schema', 'type': 'type'}


def quote(value):
    return '"' + str(value).replace('"', '""') + '"'


def literal(value):
    """A standard-conforming SQL string literal (no backslash escapes)."""
    return "'" + str(value).replace("'", "''") + "'"


def _choice(field_id, label, values, **options):
    return cp_field(field_id, label, 'select', options=[
        {'value': value, 'label': title} for value, title in values],
        **options)


def _bound_fields():
    range_bound = {'field_id': 'bound', 'equals': 'RANGE'}
    ends = []
    for side, label, open_end in (('from', 'From', 'MINVALUE'),
                                  ('to', 'To', 'MAXVALUE')):
        ends += [
            _choice(f'{side}_mode', f'{label} end', (
                ('VALUE', 'Value'), (open_end, open_end.title())),
                default='VALUE', visible_when=range_bound),
            cp_field(f'{side}_value', f'{label} value', 'text', False,
                     max_length=4096, pattern=VALUE,
                     visible_when=range_bound),
        ]
    return (
        _choice('bound', 'Bound', (
            ('RANGE', 'Range'), ('LIST', 'List'), ('HASH', 'Hash'),
            ('DEFAULT', 'Default (rows matching no other partition)'),
        ), required=True,
            help='Must match how the table is partitioned; the key is one '
            'column.'),
        *ends,
        cp_field('in_values', 'Values', 'grid', True, columns=[{'field_id': 'value', 'label': 'Value', 'control': 'text'}],
                 visible_when={'field_id': 'bound', 'equals': 'LIST'}),
        cp_field('modulus', 'Modulus', 'number', True, minimum=1,
                 maximum=1024, visible_when={'field_id': 'bound',
                                             'equals': 'HASH'}),
        cp_field('remainder', 'Remainder', 'number', True, minimum=0,
                 maximum=1023, visible_when={'field_id': 'bound',
                                             'equals': 'HASH'}),
    )


class PGWireAdministration:
    """The native administration one PG-wire engine declares.

    ``features`` maps an operation key to its options:

    - ``('table', 'analyze')``: ``'show_statistics'`` or ``'pg_stat'``;
    - ``(kind, 'grant'|'revoke')``: the privilege names read back;
    - ``('session', ...)``: ``'cluster_sessions'`` or ``'pg_stat_activity'``;
    - ``('grants', None)``: ``'show_grants'`` or ``'aclexplode'``;
    - other keys: ``True``.
    """

    def __init__(self, engine_name, features, grant_reader):
        self.engine_name = engine_name
        self.features = dict(features)
        self.grant_reader = grant_reader

    def supports(self, kind, operation):
        return (kind, operation) in self.features

    @staticmethod
    def outside_transaction(kind, _operation):
        """CockroachDB refuses SET CLUSTER SETTING in a transaction."""
        return kind == 'cluster-setting'

    def _error(self, message):
        return RelationalClientError(f'{self.engine_name} {message}')

    # Declarations -----------------------------------------------------

    def operations(self):
        return tuple(self._operation(kind, operation, option)
                     for (kind, operation), option in self.features.items())

    def _operation(self, kind, operation, option):
        if (kind, operation) == ('table', 'truncate'):
            return ControlPlaneOperation(
                'table', 'truncate', 'Truncate table', 'destructive',
                'data_write', (
                    cp_field('cascade', 'Also truncate referencing tables',
                             'boolean', False, default=False),
                ), impact_scope='resource')
        if (kind, operation) == ('table', 'analyze'):
            return ControlPlaneOperation(
                'table', 'analyze', 'Analyze table', 'admin',
                'maintenance_admin', confirmation_required=False,
                impact_scope='resource')
        if (kind, operation) == ('table', 'set_schema'):
            return ControlPlaneOperation(
                'table', 'set_schema', 'Move to schema', 'admin',
                'administer', (
                    cp_field('schema', 'Schema', 'text', True, max_length=63,
                             pattern=NAME),
                ), impact_scope='resource')
        if (kind, operation) == ('table', 'set_owner'):
            return ControlPlaneOperation(
                'table', 'set_owner', 'Change owner', 'admin',
                'security_admin', (
                    cp_field('owner', 'Owner', 'text', True, max_length=63,
                             pattern=NAME),
                ), impact_scope='resource')
        if (kind, operation) == ('constraint', 'validate'):
            return ControlPlaneOperation(
                'constraint', 'validate', 'Validate constraint', 'admin',
                'maintenance_admin', impact_scope='resource')
        if operation in {'set_setting', 'reset_setting'}:
            fields = [cp_field('setting', 'Setting', 'text', True,
                               max_length=128, pattern=SETTING)]
            if operation == 'set_setting':
                fields.append(cp_field('value', 'Value', 'text', True,
                                       max_length=4096, pattern=VALUE))
            if kind in {'role', 'user'}:
                fields.append(cp_field(
                    'database', 'Only in database', 'text', False,
                    max_length=63, pattern=NAME,
                    help='Leave empty for every database.'))
            title = ('Set default setting' if operation == 'set_setting'
                     else 'Reset default setting')
            return ControlPlaneOperation(
                kind, operation, title, 'admin', 'administer', tuple(fields),
                impact_scope='resource')
        if operation in {'grant', 'revoke'}:
            fields = [
                cp_field('principal', 'Role', 'text', True, max_length=63,
                         pattern=NAME),
                cp_field('privileges', 'Privileges', 'multiselect', True,
                         options=[{'value': name, 'label': name}
                                  for name in option]),
            ]
            if operation == 'grant':
                fields.append(cp_field('grant_option', 'With grant option',
                                       'boolean', False, default=False))
            title = (f'Grant {_GRANT_TITLES[kind]} privileges'
                     if operation == 'grant'
                     else f'Revoke {_GRANT_TITLES[kind]} privileges')
            return ControlPlaneOperation(
                kind, operation, title, 'admin', 'security_admin',
                tuple(fields), impact_scope='resource')
        if (kind, operation) in {('table', 'create_partition'),
                                 ('table', 'attach_partition')}:
            first = (cp_field('name', 'Partition name', 'text', True,
                              max_length=63, pattern=NAME)
                     if operation == 'create_partition' else
                     cp_field('table', 'Table to attach', 'text', True,
                              max_length=63, pattern=NAME,
                              help='An existing table in the same schema.'))
            title = ('Create partition' if operation == 'create_partition'
                     else 'Attach partition')
            return ControlPlaneOperation(
                'table', operation, title, 'admin', 'administer',
                (first, *_bound_fields()), impact_scope='resource')
        if (kind, operation) == ('partition', 'detach'):
            return ControlPlaneOperation(
                'partition', 'detach', 'Detach partition', 'admin',
                'administer', impact_scope='resource')
        if (kind, operation) == ('table', 'repartition'):
            return ControlPlaneOperation(
                'table', 'repartition', 'Repartition', 'admin',
                'administer', (
                    _choice('strategy', 'Partition by', (
                        ('LIST', 'List'), ('RANGE', 'Range'),
                        ('NOTHING', 'Nothing (remove partitioning)'),
                    ), required=True),
                    cp_field('column', 'Partition column', 'text', False,
                             max_length=63, pattern=NAME,
                             visible_when={'field_id': 'strategy',
                                           'in': ['LIST', 'RANGE']},
                             help='The first primary key column; required '
                             'unless removing partitioning.'),
                    cp_field('list_partitions', 'List partitions', 'grid',
                             True, columns=[{'field_id': 'partition', 'label': 'Partition', 'control': 'text'}, {'field_id': 'value', 'label': 'Value', 'control': 'text'}, {'field_id': 'default', 'label': 'Default', 'control': 'boolean'}],
                             visible_when={'field_id': 'strategy',
                                           'equals': 'LIST'},
                             help='One row per value: partition, value, '
                             'or Default for rows matching no other.'),
                    cp_field('range_partitions', 'Range partitions', 'grid',
                             True, columns=[{'field_id': 'partition', 'label': 'Partition', 'control': 'text'}, {'field_id': 'from_mode', 'label': 'From end', 'control': 'select'}, {'field_id': 'from_value', 'label': 'From value', 'control': 'text'}, {'field_id': 'to_mode', 'label': 'To end', 'control': 'select'}, {'field_id': 'to_value', 'label': 'To value', 'control': 'text'}],
                             visible_when={'field_id': 'strategy',
                                           'equals': 'RANGE'},
                             help='One row per partition: from and to, '
                             'each a value or the open end.'),
                ), impact_scope='resource')
        if (kind, operation) == ('cluster-setting', 'set_value'):
            return ControlPlaneOperation(
                'cluster-setting', 'set_value', 'Set cluster setting',
                'admin', 'administer', (
                    cp_field('value', 'Value', 'text', True, max_length=4096,
                             pattern=VALUE,
                             help='Cluster-wide and persistent.'),
                ), impact_scope='cluster')
        if (kind, operation) == ('cluster-setting', 'reset'):
            return ControlPlaneOperation(
                'cluster-setting', 'reset', 'Reset to default', 'admin',
                'administer', impact_scope='cluster')
        if operation in {'grant_system', 'revoke_system'}:
            fields = [cp_field('privileges', 'System privileges',
                               'multiselect', True, options=[
                                   {'value': name, 'label': name}
                                   for name in option])]
            if operation == 'grant_system':
                fields.append(cp_field('grant_option', 'With grant option',
                                       'boolean', False, default=False))
            title = ('Grant system privileges' if operation == 'grant_system'
                     else 'Revoke system privileges')
            return ControlPlaneOperation(
                kind, operation, title, 'admin', 'security_admin',
                tuple(fields), impact_scope='cluster')
        if (kind, operation) == ('table', 'split_at'):
            return ControlPlaneOperation(
                'table', 'split_at', 'Split ranges at', 'admin',
                'topology_admin', (
                    cp_field('split_values', 'Split points', 'grid', True,
                             columns=[{'field_id': 'value', 'label': 'Value', 'control': 'text'}],
                             help='One primary key value per split; the '
                             'key is one column.'),
                ), impact_scope='resource')
        if operation in {'set_storage_parameter', 'reset_storage_parameter'}:
            fields = [_choice('parameter', 'Parameter', tuple(
                (name, name) for name in STORAGE_PARAMETERS), required=True,
                help='schema_locked is changed on its own.')]
            if operation == 'set_storage_parameter':
                fields.append(cp_field('value', 'Value', 'text', True,
                                       max_length=64, pattern=VALUE,
                                       help='true/false, or a number.'))
            title = ('Set storage parameter'
                     if operation == 'set_storage_parameter'
                     else 'Reset storage parameter')
            return ControlPlaneOperation(
                'table', operation, title, 'admin', 'administer',
                tuple(fields), impact_scope='resource')
        if (kind, operation) == ('session', 'terminate_query'):
            return ControlPlaneOperation(
                'session', 'terminate_query', 'Cancel running statement',
                'admin', 'administer', impact_scope='resource')
        if (kind, operation) == ('session', 'terminate_connection'):
            return ControlPlaneOperation(
                'session', 'terminate_connection', 'Terminate session',
                'destructive', 'administer', impact_scope='resource')
        raise ValueError(f'undeclared PG-wire operation {kind}.{operation}')

    # Targets ----------------------------------------------------------

    def _path(self, request, length):
        target = request.get('target_resource')
        path = target.get('display_path') if isinstance(target, dict) else None
        if not isinstance(path, list) or len(path) != length or not all(
                isinstance(item, str) and item for item in path):
            raise self._error('control target is invalid')
        return path

    def _text(self, draft, field_id, pattern, label, required=True):
        value = draft.get(field_id)
        if value in (None, '') and not required:
            return None
        if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
            raise self._error(f'{label} is invalid')
        return value

    def _session(self, request):
        value = self._path(request, 1)[0]
        option = self.features[('session', request['operation_id'])]
        pattern = (r'[0-9a-f]{32}' if option == 'cluster_sessions'
                   else r'[1-9][0-9]{0,9}')
        if re.fullmatch(pattern, value) is None:
            raise self._error('session identity is invalid')
        return value

    def _grant_object(self, kind, request):
        if kind == 'type':
            schema, name = self._path(request, 2)
            return 'TYPE ' + quote(schema) + '.' + quote(name)
        return kind.upper() + ' ' + quote(self._path(request, 1)[0])

    def _privileges(self, kind, operation, draft):
        admitted = self.features[(kind, operation)]
        values = draft.get('privileges')
        if not isinstance(values, list) or not values or len(values) != len(
                set(values)) or any(value not in admitted for value in values):
            raise self._error('privilege selection is invalid')
        return [value for value in admitted if value in values]

    # Compilation ------------------------------------------------------

    def statements(self, request):
        kind = request['resource_kind']
        operation = request['operation_id']
        if not self.supports(kind, operation):
            raise self._error('control-plane operation is unavailable')
        draft = request.get('draft') or {}
        if kind == 'cluster-setting':
            name = self._path(request, 1)[0]
            if re.fullmatch(CLUSTER_SETTING, name) is None:
                raise self._error('cluster setting name is invalid')
            if operation == 'reset':
                return [_statement('RESET CLUSTER SETTING ' + name)]
            value = self._text(draft, 'value', VALUE, 'setting value')
            return [_statement('SET CLUSTER SETTING ' + name + ' = ' +
                               literal(value))]
        if operation in {'grant_system', 'revoke_system'}:
            principal = quote(self._path(request, 1)[0])
            privileges = ', '.join(self._privileges(kind, operation, draft))
            if operation == 'grant_system':
                return [_statement(
                    'GRANT SYSTEM ' + privileges + ' TO ' + principal + (
                        ' WITH GRANT OPTION' if draft.get('grant_option')
                        else ''))]
            return [_statement('REVOKE SYSTEM ' + privileges + ' FROM ' +
                               principal)]
        if operation == 'split_at':
            schema, table = self._path(request, 2)
            values = self._values(draft.get('split_values'))
            return [_statement(
                'ALTER TABLE ' + quote(schema) + '.' + quote(table) +
                ' SPLIT AT VALUES ' + ', '.join(
                    '(' + literal(value) + ')' for value in values))]
        if operation in {'set_storage_parameter', 'reset_storage_parameter'}:
            schema, table = self._path(request, 2)
            parameter = draft.get('parameter')
            if parameter not in STORAGE_PARAMETERS:
                raise self._error('storage parameter is invalid')
            prefix = 'ALTER TABLE ' + quote(schema) + '.' + quote(table)
            if operation == 'reset_storage_parameter':
                return [_statement(prefix + ' RESET (' + parameter + ')')]
            return [_statement(prefix + ' SET (' + parameter + ' = ' +
                               _storage_value(parameter, draft.get('value'),
                                              self._error) + ')')]
        if kind == 'partition':
            schema, parent, child = self._path(request, 3)
            return [_statement('ALTER TABLE ' + quote(schema) + '.' +
                               quote(parent) + ' DETACH PARTITION ' +
                               quote(schema) + '.' + quote(child))]
        if kind == 'table' and operation in {'create_partition',
                                             'attach_partition',
                                             'repartition'}:
            schema, table = self._path(request, 2)
            qualified = quote(schema) + '.' + quote(table)
            if operation == 'repartition':
                return [_statement('ALTER TABLE ' + qualified + ' ' +
                                   self._repartition(draft))]
            bound = self._bound(draft)
            if operation == 'create_partition':
                name = self._text(draft, 'name', NAME, 'partition name')
                return [_statement(
                    'CREATE TABLE ' + quote(schema) + '.' + quote(name) +
                    ' PARTITION OF ' + qualified + ' ' + bound)]
            child = self._text(draft, 'table', NAME, 'table to attach')
            return [_statement('ALTER TABLE ' + qualified +
                               ' ATTACH PARTITION ' + quote(schema) + '.' +
                               quote(child) + ' ' + bound)]
        if kind == 'table':
            schema, table = self._path(request, 2)
            qualified = quote(schema) + '.' + quote(table)
            if operation == 'truncate':
                return [_statement('TRUNCATE TABLE ' + qualified + (
                    ' CASCADE' if draft.get('cascade') else ''))]
            if operation == 'analyze':
                return [_statement('ANALYZE ' + qualified)]
            if operation == 'set_schema':
                target = self._text(draft, 'schema', NAME, 'schema')
                if target == schema:
                    raise self._error('table is already in that schema')
                return [_statement('ALTER TABLE ' + qualified +
                                   ' SET SCHEMA ' + quote(target))]
            owner = self._text(draft, 'owner', NAME, 'owner')
            return [_statement('ALTER TABLE ' + qualified + ' OWNER TO ' +
                               quote(owner))]
        if kind == 'constraint':
            schema, table = self._path(request, 3)[:2]
            name = self._path(request, 3)[2]
            return [_statement('ALTER TABLE ' + quote(schema) + '.' +
                               quote(table) + ' VALIDATE CONSTRAINT ' +
                               quote(name))]
        if operation in {'set_setting', 'reset_setting'}:
            name = self._path(request, 1)[0]
            setting = self._text(draft, 'setting', SETTING, 'setting name')
            if kind == 'database':
                prefix = 'ALTER DATABASE ' + quote(name)
            else:
                prefix = 'ALTER ROLE ' + quote(name)
                database = self._text(draft, 'database', NAME, 'database',
                                      required=False)
                if database:
                    prefix += ' IN DATABASE ' + quote(database)
            if operation == 'reset_setting':
                return [_statement(prefix + ' RESET ' + setting)]
            value = draft.get('value')
            if not isinstance(value, str) or re.fullmatch(
                    VALUE, value) is None:
                raise self._error('setting value is invalid')
            return [_statement(prefix + ' SET ' + setting + ' = ' +
                               literal(value))]
        if operation in {'grant', 'revoke'}:
            principal = self._text(draft, 'principal', NAME, 'role')
            privileges = ', '.join(self._privileges(kind, operation, draft))
            target = self._grant_object(kind, request)
            if operation == 'grant':
                return [_statement(
                    'GRANT ' + privileges + ' ON ' + target + ' TO ' +
                    quote(principal) + (' WITH GRANT OPTION'
                                        if draft.get('grant_option') else ''))]
            return [_statement('REVOKE ' + privileges + ' ON ' + target +
                               ' FROM ' + quote(principal))]
        session = self._session(request)
        if self.features[(kind, operation)] == 'cluster_sessions':
            if operation == 'terminate_query':
                return [_statement(
                    'CANCEL QUERIES (SELECT query_id FROM '
                    '[SHOW CLUSTER STATEMENTS] WHERE session_id = ' +
                    literal(session) + ')')]
            return [_statement('CANCEL SESSION ' + literal(session))]
        function = ('pg_cancel_backend' if operation == 'terminate_query'
                    else 'pg_terminate_backend')
        return [_statement(f'SELECT {function}({int(session)})')]

    def _bound_value(self, draft, side):
        mode = draft.get(f'{side}_mode') or 'VALUE'
        if mode in {'MINVALUE', 'MAXVALUE'}:
            return mode
        if mode != 'VALUE':
            raise self._error(f'{side} bound is invalid')
        value = draft.get(f'{side}_value')
        if not isinstance(value, str) or re.fullmatch(VALUE, value) is None:
            raise self._error(f'{side} value is invalid')
        return literal(value)

    def _bound(self, draft):
        kind = draft.get('bound')
        if kind == 'RANGE':
            return ('FOR VALUES FROM (' + self._bound_value(draft, 'from') +
                    ') TO (' + self._bound_value(draft, 'to') + ')')
        if kind == 'LIST':
            return 'FOR VALUES IN (' + ', '.join(
                literal(value) for value in self._values(
                    draft.get('in_values'))) + ')'
        if kind == 'HASH':
            modulus, remainder = draft.get('modulus'), draft.get('remainder')
            if not all(isinstance(value, int) and not isinstance(value, bool)
                       for value in (modulus, remainder)) or not (
                    0 <= remainder < modulus):
                raise self._error('hash modulus and remainder are invalid')
            return (f'FOR VALUES WITH (MODULUS {modulus}, '
                    f'REMAINDER {remainder})')
        if kind == 'DEFAULT':
            return 'DEFAULT'
        raise self._error('partition bound is invalid')

    def _values(self, values):
        if not isinstance(values, list) or not values or len(values) > 1024:
            raise self._error('partition values are invalid')
        result = []
        for item in values:
            value = item.get('value') if isinstance(item, dict) else item
            if not isinstance(value, str) or re.fullmatch(
                    VALUE, value) is None:
                raise self._error('partition value is invalid')
            result.append(value)
        if len(set(result)) != len(result):
            raise self._error('partition values repeat')
        return result

    def _repartition(self, draft):
        strategy = draft.get('strategy')
        if strategy == 'NOTHING':
            return 'PARTITION BY NOTHING'
        column = self._text(draft, 'column', NAME, 'partition column')
        rows = draft.get('list_partitions' if strategy == 'LIST'
                         else 'range_partitions')
        if strategy not in {'LIST', 'RANGE'} or not isinstance(
                rows, list) or not rows:
            raise self._error('partitions are invalid')
        partitions = {}
        for row in rows:
            if not isinstance(row, dict):
                raise self._error('partition row is invalid')
            name = self._text(row, 'partition', NAME, 'partition name')
            if strategy == 'RANGE':
                if name in partitions:
                    raise self._error(f'partition {name} repeats')
                partitions[name] = (
                    'VALUES FROM (' + self._bound_value(row, 'from') +
                    ') TO (' + self._bound_value(row, 'to') + ')')
                continue
            value = ('DEFAULT' if row.get('default') else
                     literal(self._values([row.get('value')])[0]))
            values = partitions.setdefault(name, [])
            if value in values:
                raise self._error(f'partition {name} repeats a value')
            values.append(value)
        clauses = [
            'PARTITION ' + quote(name) + ' ' + (
                definition if strategy == 'RANGE'
                else 'VALUES IN (' + ', '.join(definition) + ')')
            for name, definition in partitions.items()]
        return ('PARTITION BY ' + strategy + ' (' + quote(column) + ') (' +
                ', '.join(clauses) + ')')

    # Read-back --------------------------------------------------------

    def inspect(self, plan, query):
        kind = plan['resource_kind']
        operation = plan['operation_id']
        draft = plan.get('draft') or {}
        option = self.features[(kind, operation)]
        if kind == 'cluster-setting':
            return query('SELECT value, origin FROM [SHOW CLUSTER SETTINGS] '
                         'WHERE variable = %s', (self._path(plan, 1)[0],))
        if operation in {'grant_system', 'revoke_system'}:
            return query('SELECT privilege_type, is_grantable FROM '
                         '[SHOW SYSTEM GRANTS FOR ' +
                         quote(self._path(plan, 1)[0]) + ']')
        if operation == 'split_at':
            schema, table = self._path(plan, 2)
            return query('SELECT start_key FROM [SHOW RANGES FROM TABLE ' +
                         quote(schema) + '.' + quote(table) + ']')
        if operation in {'set_storage_parameter', 'reset_storage_parameter'}:
            schema, table = self._path(plan, 2)
            return query(
                'SELECT c.reloptions FROM pg_catalog.pg_class c '
                'JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace '
                'WHERE n.nspname = %s AND c.relname = %s', (schema, table))
        if kind == 'partition' or operation in {'create_partition',
                                                'attach_partition'}:
            if kind == 'partition':
                schema, _parent, child = self._path(plan, 3)
            else:
                schema = self._path(plan, 2)[0]
                child = draft.get('name' if operation == 'create_partition'
                                  else 'table')
            return query(
                'SELECT pc.relname, pg_catalog.pg_get_expr(cc.relpartbound, '
                'cc.oid) FROM pg_catalog.pg_class cc '
                'JOIN pg_catalog.pg_namespace cn ON cn.oid = cc.relnamespace '
                'LEFT JOIN pg_catalog.pg_inherits i ON i.inhrelid = cc.oid '
                'LEFT JOIN pg_catalog.pg_class pc ON pc.oid = i.inhparent '
                'WHERE cn.nspname = %s AND cc.relname = %s', (schema, child))
        if operation == 'repartition':
            schema, table = self._path(plan, 2)
            # The primary index's partitions only; secondary indexes keep
            # their own.
            return query(
                'SELECT partition_name, column_names, partition_value FROM '
                '[SHOW PARTITIONS FROM TABLE ' + quote(schema) + '.' +
                quote(table) + "] WHERE index_name = %s || '@' || "
                '(SELECT constraint_name FROM [SHOW CONSTRAINTS FROM ' +
                quote(schema) + '.' + quote(table) + "] WHERE "
                "constraint_type = 'PRIMARY KEY')", (table,))
        if kind == 'table':
            schema, table = self._path(plan, 2)
            if operation == 'truncate':
                return query('SELECT NOT EXISTS (SELECT 1 FROM ' +
                             quote(schema) + '.' + quote(table) + ')')
            if operation == 'analyze' and option == 'show_statistics':
                # A fresh table has no statistics row at all, so require
                # one created within ten minutes by the server clock.
                return query(
                    "SELECT count(*) FILTER (WHERE created >= now() - "
                    "INTERVAL '10 minutes') > 0 FROM "
                    '[SHOW STATISTICS FOR TABLE ' + quote(schema) + '.' +
                    quote(table) + ']')
            if operation == 'analyze':
                return query(
                    "SELECT last_analyze >= now() - INTERVAL '10 minutes' "
                    'FROM pg_catalog.pg_stat_user_tables '
                    'WHERE schemaname = %s AND relname = %s', (schema, table))
            if operation == 'set_schema':
                return query(
                    'SELECT table_schema FROM information_schema.tables '
                    'WHERE table_name = %s AND table_schema IN (%s, %s)',
                    (table, schema, draft.get('schema')))
            return query(
                'SELECT tableowner FROM pg_catalog.pg_tables '
                'WHERE schemaname = %s AND tablename = %s', (schema, table))
        if kind == 'constraint':
            schema, table, name = self._path(plan, 3)
            return query(
                'SELECT c.convalidated FROM pg_catalog.pg_constraint c '
                'JOIN pg_catalog.pg_class t ON t.oid = c.conrelid '
                'JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace '
                'WHERE n.nspname = %s AND t.relname = %s AND c.conname = %s',
                (schema, table, name))
        if operation in {'set_setting', 'reset_setting'}:
            name = self._path(plan, 1)[0]
            role, database = (('', name) if kind == 'database' else
                              (name, draft.get('database') or ''))
            return query(
                'SELECT s.setconfig FROM pg_catalog.pg_db_role_setting s '
                'LEFT JOIN pg_catalog.pg_roles r ON r.oid = s.setrole '
                'LEFT JOIN pg_catalog.pg_database d ON d.oid = s.setdatabase '
                "WHERE coalesce(r.rolname, '') = %s "
                "AND coalesce(d.datname, '') = %s", (role, database))
        if operation in {'grant', 'revoke'}:
            return self._inspect_grants(kind, plan, query)
        session = self._session(plan)
        if option == 'cluster_sessions':
            return query(
                'SELECT session_id, active_queries FROM '
                '[SHOW CLUSTER SESSIONS] WHERE session_id = %s', (session,))
        return query(
            'SELECT pid, state FROM pg_catalog.pg_stat_activity '
            'WHERE pid = %s', (int(session),))

    def _inspect_grants(self, kind, plan, query):
        principal = (plan.get('draft') or {}).get('principal')
        if self.grant_reader == 'show_grants':
            return query(
                'SELECT privilege_type, is_grantable FROM [SHOW GRANTS ON ' +
                self._grant_object(kind, plan) + '] WHERE grantee = %s',
                (principal,))
        if kind == 'type':
            schema, name = self._path(plan, 2)
            source, condition, parameters = (
                'pg_catalog.pg_type o JOIN pg_catalog.pg_namespace n '
                'ON n.oid = o.typnamespace', 'n.nspname = %s AND '
                'o.typname = %s', (schema, name))
            acl = 'o.typacl'
        else:
            catalog, column, acl = {
                'database': ('pg_database', 'datname', 'o.datacl'),
                'schema': ('pg_namespace', 'nspname', 'o.nspacl'),
            }[kind]
            source = 'pg_catalog.' + catalog + ' o'
            condition = 'o.' + column + ' = %s'
            parameters = (self._path(plan, 1)[0],)
        return query(
            'SELECT a.privilege_type, a.is_grantable FROM ' + source +
            ' CROSS JOIN LATERAL aclexplode(' + acl + ') a '
            'JOIN pg_catalog.pg_roles r ON r.oid = a.grantee '
            'WHERE ' + condition + ' AND r.rolname = %s',
            (*parameters, principal))

    def confirmed(self, plan, rows):
        kind = plan['resource_kind']
        operation = plan['operation_id']
        draft = plan.get('draft') or {}
        if kind == 'cluster-setting':
            if len(rows) != 1:
                return False
            value, origin = (str(item) for item in rows[0])
            if operation == 'reset':
                return origin == 'default'
            # CockroachDB normalizes some values (40MiB reads back 40 MiB);
            # anything beyond spacing and case is reported unconfirmed.
            return origin == 'override' and _plain(value) == _plain(
                draft.get('value'))
        if operation in {'grant_system', 'revoke_system'}:
            operation = operation.split('_', 1)[0]
        if operation == 'split_at':
            starts = [str(row[0]) for row in rows]
            return all(any(start.endswith(suffix) for start in starts
                           for suffix in _split_suffixes(value))
                       for value in self._values(draft.get('split_values')))
        if operation in {'set_storage_parameter', 'reset_storage_parameter'}:
            if len(rows) != 1:
                return False
            entries = [str(entry) for entry in rows[0][0] or []]
            prefix = f'{draft.get("parameter")}='
            absent = not any(entry.startswith(prefix) for entry in entries)
            if operation == 'reset_storage_parameter':
                return absent
            value = _storage_value(draft.get('parameter'), draft.get('value'),
                                   RelationalClientError)
            # CockroachDB records schema_locked = false by removing it.
            if absent and ABSENT_VALUES.get(draft.get('parameter')) == value:
                return True
            return prefix + _storage_value(
                draft.get('parameter'), draft.get('value'),
                RelationalClientError) in entries
        if kind == 'partition':
            # Still a table, no longer anyone's partition.
            return len(rows) == 1 and rows[0][0] is None
        if operation in {'create_partition', 'attach_partition'}:
            parent = self._path(plan, 2)[1]
            return len(rows) == 1 and str(rows[0][0]) == parent and (
                bound_tokens(str(rows[0][1] or '')) ==
                _expected_bound(draft))
        if operation == 'repartition':
            if draft.get('strategy') == 'NOTHING':
                return not rows
            observed = {str(name): bound_tokens(str(value))
                        for name, _columns, value in rows}
            columns = {str(columns) for _name, columns, _value in rows}
            return columns == {draft.get('column')} and (
                observed == _expected_partitions(draft))
        if kind == 'table':
            if operation in {'truncate', 'analyze'}:
                return len(rows) == 1 and rows[0][0] is True
            if operation == 'set_schema':
                return [str(row[0]) for row in rows] == [draft.get('schema')]
            return len(rows) == 1 and str(rows[0][0]) == draft.get('owner')
        if kind == 'constraint':
            return len(rows) == 1 and rows[0][0] is True
        if operation in {'set_setting', 'reset_setting'}:
            entries = [str(entry) for row in rows for entry in row[0] or []]
            prefix = f'{draft.get("setting")}='
            if operation == 'reset_setting':
                return not any(entry.startswith(prefix) for entry in entries)
            return prefix + str(draft.get('value')) in entries
        if operation in {'grant', 'revoke'}:
            granted = {}
            for privilege, grantable in rows:
                held = str(grantable).upper() in {'TRUE', 'YES', 'T'}
                granted[str(privilege)] = granted.get(str(privilege)) or held
            wanted = draft.get('privileges') or []
            if operation == 'revoke':
                return not any(name in granted for name in wanted)
            return all(name in granted and (
                granted[name] or not draft.get('grant_option'))
                for name in wanted)
        if operation == 'terminate_connection':
            return not rows
        if self.features[(kind, operation)] == 'cluster_sessions':
            return not rows or not str(rows[0][1] or '')
        return not rows or str(rows[0][1]) != 'active'


def _plain(value):
    return ''.join(str(value).split()).lower()


def _split_suffixes(value):
    """How SHOW RANGES renders a split at ``value``: bare, or quoted."""
    quoted = value.replace('\\', '\\\\').replace('"', '\\"')
    return ('/' + value, '/"' + quoted + '"')


def _storage_value(parameter, value, error):
    kind = STORAGE_PARAMETERS.get(parameter)
    text = str(value or '').strip().lower()
    if kind == 'boolean' and text in {'true', 'false'}:
        return text
    if kind == 'integer' and re.fullmatch(r'[0-9]{1,18}', text):
        return text
    if kind == 'number' and re.fullmatch(r'[0-9]{1,18}(\.[0-9]{1,18})?',
                                         text):
        return text
    raise error(f'{parameter} value is invalid')


def _expected_side(row, side):
    mode = row.get(f'{side}_mode') or 'VALUE'
    if mode in {'MINVALUE', 'MAXVALUE'}:
        return ('k', mode)
    return ('v', row.get(f'{side}_value'))


def _expected_values(values):
    return sorted(('v', item.get('value') if isinstance(item, dict)
                   else item) for item in values)


def _expected_bound(draft):
    kind = draft.get('bound')
    if kind == 'RANGE':
        return [_expected_side(draft, 'from'), ('k', 'TO'),
                _expected_side(draft, 'to')]
    if kind == 'LIST':
        return _expected_values(draft.get('in_values') or [])
    if kind == 'HASH':
        return [('k', 'MODULUS'), ('v', str(draft.get('modulus'))),
                ('k', 'REMAINDER'), ('v', str(draft.get('remainder')))]
    return [('k', 'DEFAULT')]


def _expected_partitions(draft):
    expected = {}
    if draft.get('strategy') == 'RANGE':
        for row in draft.get('range_partitions') or []:
            expected[row['partition']] = [
                _expected_side(row, 'from'), ('k', 'TO'),
                _expected_side(row, 'to')]
        return expected
    for row in draft.get('list_partitions') or []:
        expected.setdefault(row['partition'], []).append(
            ('k', 'DEFAULT') if row.get('default')
            else ('v', row.get('value')))
    return {name: sorted(values) for name, values in expected.items()}


_KEYWORDS = {'TO', 'MINVALUE', 'MAXVALUE', 'DEFAULT', 'MODULUS', 'REMAINDER'}
_SKIPPED = {'FOR', 'VALUES', 'IN', 'FROM', 'WITH'}


def bound_tokens(text):
    """Values and keywords of a partition bound as the engine renders it.

    Handles PostgreSQL ``pg_get_expr`` (``FOR VALUES IN ('a', 1)``,
    ``FOR VALUES WITH (modulus 4, remainder 0)``, casts) and CockroachDB
    ``SHOW PARTITIONS`` (``(1), (2)``, ``(MINVALUE) TO (10)``,
    ``e'x\\'y'``). List values are returned sorted, since an engine may
    reorder them; ranges keep their order.
    """
    tokens, position = [], 0
    while position < len(text):
        char = text[position]
        if char in " \t\n(),":
            position += 1
            continue
        if text.startswith('::', position):
            position += 2
            while position < len(text) and (
                    text[position].isalnum() or text[position] in '_ "[]'):
                if text[position] == ' ' and not text[position + 1:
                                                      position + 2].isalpha():
                    break
                position += 1
            continue
        escaped = char in 'eE' and text[position + 1:position + 2] == "'"
        if char == "'" or escaped:
            position += 2 if escaped else 1
            value = []
            while position < len(text):
                if escaped and text[position] == '\\':
                    value.append(text[position + 1:position + 2])
                    position += 2
                    continue
                if text[position] == "'":
                    if text[position + 1:position + 2] == "'":
                        value.append("'")
                        position += 2
                        continue
                    position += 1
                    break
                value.append(text[position])
                position += 1
            tokens.append(('v', ''.join(value)))
            continue
        end = position
        while end < len(text) and text[end] not in " \t\n(),:":
            end += 1
        word = text[position:end]
        position = end
        if word.upper() in _SKIPPED:
            continue
        tokens.append(('k', word.upper()) if word.upper() in _KEYWORDS
                      else ('v', word))
    if tokens and all(kind == 'v' or value == 'DEFAULT'
                      for kind, value in tokens) and ('k', 'TO') not in tokens:
        return sorted(tokens)
    return tokens


def _statement(source):
    return {'source': source, 'parameters': ()}


def session_resources(cursor, generation, resource, optional_rows, source):
    """List client sessions with the fields their operations read back."""
    values = []
    if source == 'cluster_sessions':
        for session_id, user, client, application, active, started in \
                optional_rows(
                    cursor,
                    'SELECT session_id, user_name, client_address, '
                    'application_name, active_queries, session_start '
                    'FROM [SHOW CLUSTER SESSIONS] ORDER BY session_start'):
            values.append(resource('session', [], session_id, generation, {
                'user': str(user), 'client': str(client or ''),
                'application': str(application or ''),
                'statement': str(active or ''),
                'started': None if started is None else str(started),
            }))
        return values
    for pid, user, database, state, statement, started, client in \
            optional_rows(
                cursor,
                'SELECT pid, usename, datname, state, query, backend_start, '
                'client_addr FROM pg_catalog.pg_stat_activity '
                "WHERE backend_type = 'client backend' ORDER BY pid"):
        values.append(resource('session', [], pid, generation, {
            'user': None if user is None else str(user),
            'database': None if database is None else str(database),
            'state': str(state or ''), 'statement': str(statement or ''),
            'started': None if started is None else str(started),
            'client': None if client is None else str(client),
        }))
    return values

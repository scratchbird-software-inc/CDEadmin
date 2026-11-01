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
SETTING = r'[a-z_][a-z0-9_.]{0,127}'
VALUE = r'[^\x00-\x1f\x7f]{0,4096}'

_GRANT_TITLES = {'database': 'database', 'schema': 'schema', 'type': 'type'}


def quote(value):
    return '"' + str(value).replace('"', '""') + '"'


def literal(value):
    """A standard-conforming SQL string literal (no backslash escapes)."""
    return "'" + str(value).replace("'", "''") + "'"


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

    # Read-back --------------------------------------------------------

    def inspect(self, plan, query):
        kind = plan['resource_kind']
        operation = plan['operation_id']
        draft = plan.get('draft') or {}
        option = self.features[(kind, operation)]
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

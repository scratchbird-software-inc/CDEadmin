"""PostgreSQL publications and subscriptions on the provider tree (M5,
2026-11-11).

Publications: CREATE PUBLICATION FOR ALL TABLES | FOR TABLE [ONLY] t
(columns) WHERE (filter), ... | TABLES IN SCHEMA s WITH (publish,
publish_via_partition_root), owner, comment; ALTER PUBLICATION RENAME TO /
OWNER TO / SET (publish ...) / ADD | DROP TABLE / ADD | DROP TABLES IN
SCHEMA, COMMENT; DROP. Column lists, row filters and schema publications
(PostgreSQL 15) and the published-operation subset, which YugabyteDB
refuses, are offered. Subscriptions: CREATE SUBSCRIPTION with a connection
built from the dialog's non-secret fields (host, port, database, user,
passfile, SSL settings; never a password), publications and options;
ALTER SUBSCRIPTION RENAME TO / OWNER TO / ENABLE | DISABLE / SET (options)
/ SET PUBLICATION, COMMENT; REFRESH PUBLICATION runs alone, as do CREATE
and DROP, which PostgreSQL refuses inside a transaction block. The
connection string carries credentials: the capture redacts it and a
change to it stays with the inherited dialog, so a plan never shows a
secret. Field ids follow the inherited dialogs.
"""
import re

from .native_admin import (
    PostgreSQLNativeAdminError, _flag, _identifier, _literal, _name,
    _qualified,
)
from .policies import expression

EVENTS = (('evnt_insert', 'insert'), ('evnt_update', 'update'),
          ('evnt_delete', 'delete'), ('evnt_truncate', 'truncate'))
_CONNECTION_VALUE = re.compile(r'[A-Za-z0-9_.:/@%+=~-]{1,256}')
_SLOT = re.compile(r'[a-z0-9_]{1,63}')
SYNC_COMMIT = ('off', 'local', 'remote_write', 'remote_apply', 'on')
STREAMING = {'f': 'off', 't': 'on', 'p': 'parallel'}
ORIGINS = ('any', 'none')
_CONNECTION_FIELDS = (('host', 'host'), ('port', 'port'), ('db', 'dbname'),
                      ('username', 'user'),
                      ('connect_timeout', 'connect_timeout'),
                      ('passfile', 'passfile'), ('sslmode', 'sslmode'),
                      ('sslcert', 'sslcert'), ('sslkey', 'sslkey'),
                      ('sslrootcert', 'sslrootcert'), ('sslcrl', 'sslcrl'))
_BOOL_OPTIONS = ('binary', 'two_phase', 'disable_on_error', 'run_as_owner',
                 'password_required', 'failover')


def _blank(value):
    return value is None or value == '' or value == []


def _rows(draft, key, label):
    value = draft.get(key)
    if value in (None, ''):
        return []
    if not isinstance(value, list) or any(
            not isinstance(item, dict) for item in value):
        raise PostgreSQLNativeAdminError(f'{label} must be a list of rows')
    return value


def _comment(keyword, name, value):
    text = 'NULL' if _blank(value) else _literal(str(value), 'comment')
    return f'COMMENT ON {keyword} {name} IS {text}'


# -- facts --------------------------------------------------------------------

def publication_facts(native, relations=None, attributes=None,
                      schema_names=None):
    row = native.get('catalog_row') or {}
    children = native.get('children') or {}
    tables = []
    for item in children.get('pg_publication_rel') or []:
        try:
            relation = int(item.get('prrelid') or 0)
        except (TypeError, ValueError):
            relation = 0
        schema, name = (relations or {}).get(relation, (None, None))
        columns = []
        for number in item.get('prattrs') or []:
            for attribute in (attributes or {}).get(relation, []):
                if attribute.get('attnum') == number:
                    columns.append(attribute.get('attname'))
        tables.append({'table_name': f'{schema}.{name}' if schema else name,
                       'columns': ', '.join(columns),
                       'where': item.get('row_filter_sql')})
    schemas = []
    for item in children.get('pg_publication_namespace') or []:
        try:
            schema = (schema_names or {}).get(int(item.get('pnnspid') or 0))
        except (TypeError, ValueError):
            schema = None
        if schema:
            schemas.append({'schema': schema})
    return {'name': native.get('name') or row.get('pubname'),
            'all_table': bool(row.get('puballtables', False)),
            'evnt_insert': bool(row.get('pubinsert', True)),
            'evnt_update': bool(row.get('pubupdate', True)),
            'evnt_delete': bool(row.get('pubdelete', True)),
            'evnt_truncate': bool(row.get('pubtruncate', True)),
            'publish_via_partition_root': bool(row.get('pubviaroot', False)),
            'pubtable': tables, 'pubschema': schemas,
            'description': native.get('comment')}


def subscription_facts(native):
    row = native.get('catalog_row') or {}
    return {'name': native.get('name') or row.get('subname'),
            'pub': list(row.get('subpublications') or []),
            'enabled': bool(row.get('subenabled', False)),
            'slot_name': row.get('subslotname'),
            'sync': row.get('subsynccommit'),
            'binary': bool(row.get('subbinary', False)),
            'streaming': STREAMING.get(row.get('substream'), 'off'),
            'two_phase': row.get('subtwophasestate', 'd') != 'd',
            'disable_on_error': bool(row.get('subdisableonerr', False)),
            'run_as_owner': bool(row.get('subrunasowner', False)),
            'password_required': bool(row.get('subpasswordrequired', True)),
            'origin': row.get('suborigin', 'any'),
            'failover': bool(row.get('subfailover', False)),
            'description': native.get('comment')}


# -- publications -------------------------------------------------------------

def _table_spec(row):
    full = _name(row.get('table_name'), 'table')
    schema, _, table = full.rpartition('.')
    if not schema:
        raise PostgreSQLNativeAdminError('a table is written schema.table')
    text = _qualified(schema.strip('"'), table.strip('"'))
    columns = row.get('columns')
    if isinstance(columns, str):
        columns = [item.strip() for item in columns.split(',')
                   if item.strip()]
    if columns:
        text += ' (' + ', '.join(_identifier(item, 'column')
                                 for item in columns) + ')'
    if not _blank(row.get('where')):
        text += ' WHERE (' + expression(row['where'], 'row filter') + ')'
    return text


def _publish_options(draft, current=None):
    options = []
    events = []
    for key, keyword in EVENTS:
        value = draft.get(key)
        if value is None and current is not None:
            value = current[key]
        if value is None:
            value = True
        if _flag({key: value}, key):
            events.append(keyword)
    if not events:
        raise PostgreSQLNativeAdminError(
            'a publication publishes at least one operation')
    options.append("publish = '" + ', '.join(events) + "'")
    root = draft.get('publish_via_partition_root')
    if root is None and current is not None:
        root = current['publish_via_partition_root']
    if root is not None:
        options.append('publish_via_partition_root = '
                       + ('true' if _flag(
                           {'r': root}, 'r') else 'false'))
    return options


def _publication_create(draft):
    name = _identifier(draft.get('name'), 'name')
    text = f'CREATE PUBLICATION {name}'
    tables = _rows(draft, 'pubtable', 'tables')
    schemas = _rows(draft, 'pubschema', 'schemas')
    if _flag(draft, 'all_table'):
        if tables or schemas:
            raise PostgreSQLNativeAdminError(
                'FOR ALL TABLES takes no table or schema list')
        text += ' FOR ALL TABLES'
    elif tables or schemas:
        parts = []
        if tables:
            only = 'ONLY ' if _flag(draft, 'only_table') else ''
            parts.append('TABLE ' + only + ', '.join(
                _table_spec(row) for row in tables))
        if schemas:
            parts.append('TABLES IN SCHEMA ' + ', '.join(
                _identifier(row.get('schema'), 'schema') for row in schemas))
        text += ' FOR ' + ', '.join(parts)
    text += ' WITH (' + ', '.join(_publish_options(draft)) + ')'
    statements = [text]
    if not _blank(draft.get('pubowner')):
        statements.append(f'ALTER PUBLICATION {name} OWNER TO '
                          + _identifier(draft['pubowner'], 'owner'))
    if not _blank(draft.get('description')):
        statements.append(_comment('PUBLICATION', name,
                                   draft['description']))
    return statements


def _publication_alter(native, draft):
    current = native.get('publication_facts') or publication_facts(native)
    name = _name(current['name'], 'name')
    quoted = _identifier(name, 'name')
    if draft.get('all_table') is not None and _flag(draft, 'all_table') != \
            current['all_table']:
        raise PostgreSQLNativeAdminError(
            'FOR ALL TABLES is fixed once created; drop and create the '
            'publication to change it')
    statements = []
    new_name = draft.get('name')
    if not _blank(new_name) and new_name != name:
        statements.append(f'ALTER PUBLICATION {quoted} RENAME TO '
                          + _identifier(new_name, 'name'))
        quoted = _identifier(new_name, 'name')
    if not _blank(draft.get('pubowner')):
        statements.append(f'ALTER PUBLICATION {quoted} OWNER TO '
                          + _identifier(draft['pubowner'], 'owner'))
    changed = any(draft.get(key) is not None and _flag(draft, key) != current[
        key] for key, _ in EVENTS + (('publish_via_partition_root', ''),))
    if changed:
        statements.append(f'ALTER PUBLICATION {quoted} SET ('
                          + ', '.join(_publish_options(draft, current)) + ')')
    only = 'ONLY ' if _flag(draft, 'only_table') else ''
    drop = _rows(draft, 'drop_tables', 'dropped tables')
    if drop:
        dropped = ', '.join(_table_spec({'table_name': row.get('table_name')})
                            for row in drop)
        statements.append(f'ALTER PUBLICATION {quoted} DROP TABLE {dropped}')
    add = _rows(draft, 'add_tables', 'added tables')
    if add:
        statements.append(f'ALTER PUBLICATION {quoted} ADD TABLE {only}'
                          + ', '.join(_table_spec(row) for row in add))
    for key, keyword in (('drop_schemas', 'DROP'), ('add_schemas', 'ADD')):
        rows = _rows(draft, key, key.replace('_', ' '))
        if rows:
            statements.append(
                f'ALTER PUBLICATION {quoted} {keyword} TABLES IN SCHEMA '
                + ', '.join(_identifier(row.get('schema'), 'schema')
                            for row in rows))
    if 'description' in draft and (draft['description'] or None) != (
            current['description'] or None):
        statements.append(_comment('PUBLICATION', quoted,
                                   draft['description']))
    if not statements:
        raise PostgreSQLNativeAdminError('nothing to change')
    return {'statement': ';\n'.join(statements), 'read_only': False}


def _publication_drop(native, draft):
    current = native.get('publication_facts') or publication_facts(native)
    name = _name(current['name'], 'name')
    if _name(draft.get('confirmation'), 'confirmation') != name:
        raise PostgreSQLNativeAdminError(
            'drop confirmation does not match object name')
    cascade = ' CASCADE' if _flag(draft, 'cascade') else ' RESTRICT'
    return {'statement': f'DROP PUBLICATION {_identifier(name, "name")}'
                         f'{cascade}', 'read_only': False}


# -- subscriptions ------------------------------------------------------------

def _connection(draft):
    parts = []
    for key, keyword in _CONNECTION_FIELDS:
        value = draft.get(key)
        if _blank(value):
            continue
        value = str(value)
        if not _CONNECTION_VALUE.fullmatch(value):
            raise PostgreSQLNativeAdminError(
                f'{key} holds a plain connection value')
        parts.append(f'{keyword}={value}')
    if draft.get('sslcompression') is not None:
        parts.append('sslcompression=' + (
            '1' if _flag(draft, 'sslcompression') else '0'))
    if not parts:
        raise PostgreSQLNativeAdminError(
            'a subscription needs connection settings (host, database, '
            'user, ...); the password stays with the inherited dialog or a '
            'passfile')
    return _literal(' '.join(parts), 'connection')


def _publications(value):
    if isinstance(value, str):
        value = [item.strip() for item in value.split(',') if item.strip()]
    if not isinstance(value, list) or not value:
        raise PostgreSQLNativeAdminError(
            'a subscription needs at least one publication')
    return ', '.join(_identifier(item, 'publication') for item in value)


def _option_values(draft, current=None, *, creating=False):
    """``key = value`` pairs for WITH (...) or SET (...)."""
    pairs = []

    def wanted(key):
        value = draft.get(key)
        if value is None:
            return None
        if current is not None and current.get(key) == value:
            return None
        return value
    for key in ('connect', 'enabled', 'copy_data', 'create_slot'):
        if not creating:
            continue
        value = draft.get(key)
        if value is not None:
            pairs.append(f'{key} = {"true" if _flag(draft, key) else "false"}')
    slot = wanted('slot_name')
    if slot is not None:
        if slot == '' or str(slot).upper() == 'NONE':
            pairs.append('slot_name = NONE')
        elif not _SLOT.fullmatch(str(slot)):
            raise PostgreSQLNativeAdminError(
                'slot name is lower-case letters, digits and underscores')
        else:
            pairs.append(f'slot_name = {slot}')
    sync = wanted('sync')
    if sync is not None:
        if sync not in SYNC_COMMIT:
            raise PostgreSQLNativeAdminError(
                'synchronous commit is ' + ', '.join(SYNC_COMMIT))
        pairs.append(f"synchronous_commit = '{sync}'")
    streaming = wanted('streaming')
    if streaming is not None:
        if streaming not in STREAMING.values():
            raise PostgreSQLNativeAdminError(
                'streaming is off, on or parallel')
        pairs.append(f"streaming = '{streaming}'")
    for key in _BOOL_OPTIONS:
        value = wanted(key)
        if value is not None:
            pairs.append(f'{key} = {"true" if _flag(draft, key) else "false"}')
    origin = wanted('origin')
    if origin is not None:
        if origin not in ORIGINS:
            raise PostgreSQLNativeAdminError('origin is any or none')
        pairs.append(f"origin = '{origin}'")
    return pairs


def _subscription_create(draft):
    name = _identifier(draft.get('name'), 'name')
    text = (f'CREATE SUBSCRIPTION {name} CONNECTION {_connection(draft)} '
            f'PUBLICATION {_publications(draft.get("pub"))}')
    if draft.get('connect') is False and (draft.get('create_slot') is None
                                         or _flag(draft, 'create_slot')):
        raise PostgreSQLNativeAdminError(
            'connect = false needs create_slot = false (and copy_data = '
            'false): the server refuses them together')
    pairs = _option_values(draft, creating=True)
    if pairs:
        text += ' WITH (' + ', '.join(pairs) + ')'
    if not _blank(draft.get('description')) or not _blank(
            draft.get('subowner')):
        raise PostgreSQLNativeAdminError(
            'CREATE SUBSCRIPTION runs alone outside a transaction; set the '
            'owner and comment with Alter afterwards')
    # One statement outside a transaction block (create_slot), by
    # PostgreSQL's rule.
    return {'statement': text, 'read_only': False, 'autocommit': True}


def _subscription_alter(native, draft):
    current = native.get('subscription_facts') or subscription_facts(native)
    name = _name(current['name'], 'name')
    quoted = _identifier(name, 'name')
    if any(not _blank(draft.get(key)) for key, _ in _CONNECTION_FIELDS):
        raise PostgreSQLNativeAdminError(
            'the connection string carries credentials; change it from the '
            'inherited dialog')
    if _flag(draft, 'refresh_pub'):
        others = {key for key, value in draft.items()
                  if value not in (None, '', False, [])} - {
            'refresh_pub', 'copy_data_after_refresh', 'name'}
        if others or (not _blank(draft.get('name')) and draft['name'] != name):
            raise PostgreSQLNativeAdminError(
                'REFRESH PUBLICATION runs alone, outside a transaction; '
                'apply the other changes first')
        copy = draft.get('copy_data_after_refresh')
        suffix = '' if copy is None else ' WITH (copy_data = ' + (
            'true' if _flag(draft, 'copy_data_after_refresh') else 'false') \
            + ')'
        return {'statement': f'ALTER SUBSCRIPTION {quoted} REFRESH '
                             f'PUBLICATION{suffix}',
                'read_only': False, 'autocommit': True}
    statements = []
    new_name = draft.get('name')
    if not _blank(new_name) and new_name != name:
        statements.append(f'ALTER SUBSCRIPTION {quoted} RENAME TO '
                          + _identifier(new_name, 'name'))
        quoted = _identifier(new_name, 'name')
    if not _blank(draft.get('subowner')):
        statements.append(f'ALTER SUBSCRIPTION {quoted} OWNER TO '
                          + _identifier(draft['subowner'], 'owner'))
    enabled = draft.get('enabled')
    if enabled is not None and _flag(draft, 'enabled') != current['enabled'] \
            and not enabled:
        statements.append(f'ALTER SUBSCRIPTION {quoted} DISABLE')
    pairs = _option_values(draft, current)
    if pairs:
        statements.append(f'ALTER SUBSCRIPTION {quoted} SET ('
                          + ', '.join(pairs) + ')')
    publications = draft.get('pub')
    if not _blank(publications):
        if isinstance(publications, str):
            publications = [item.strip() for item in publications.split(',')
                            if item.strip()]
        if sorted(publications) != sorted(current['pub']):
            refresh = '' if current['enabled'] or (
                enabled is not None and _flag(draft, 'enabled')) else \
                ' WITH (refresh = false)'
            statements.append(f'ALTER SUBSCRIPTION {quoted} SET PUBLICATION '
                              + _publications(publications) + refresh)
    if enabled is not None and _flag(draft, 'enabled') != current['enabled'] \
            and enabled:
        statements.append(f'ALTER SUBSCRIPTION {quoted} ENABLE')
    if 'description' in draft and (draft['description'] or None) != (
            current['description'] or None):
        statements.append(_comment('SUBSCRIPTION', quoted,
                                   draft['description']))
    if not statements:
        raise PostgreSQLNativeAdminError('nothing to change')
    return {'statement': ';\n'.join(statements), 'read_only': False}


def _subscription_drop(native, draft):
    current = native.get('subscription_facts') or subscription_facts(native)
    name = _name(current['name'], 'name')
    if _name(draft.get('confirmation'), 'confirmation') != name:
        raise PostgreSQLNativeAdminError(
            'drop confirmation does not match object name')
    cascade = ' CASCADE' if _flag(draft, 'cascade') else ' RESTRICT'
    # Outside a transaction block, as PostgreSQL requires when a slot is
    # attached.
    return {'statement': f'DROP SUBSCRIPTION {_identifier(name, "name")}'
                         f'{cascade}', 'read_only': False, 'autocommit': True}


# -- dispatch -----------------------------------------------------------------

FACTS = {'publication': ('publication_facts', publication_facts),
         'subscription': ('subscription_facts', subscription_facts)}


def compile_operation(kind, operation, native, draft):
    """One exact native text for a publication or subscription."""
    if kind == 'publication':
        if operation == 'create':
            return {'statement': ';\n'.join(_publication_create(draft)),
                    'read_only': False}
        if operation == 'alter':
            return _publication_alter(native, draft)
        if operation == 'drop':
            return _publication_drop(native, draft)
    else:
        if operation == 'create':
            return _subscription_create(draft)
        if operation == 'alter':
            return _subscription_alter(native, draft)
        if operation == 'drop':
            return _subscription_drop(native, draft)
    raise PostgreSQLNativeAdminError(
        f'{kind} inspection stays with the provider tree')


# -- forms --------------------------------------------------------------------

def _column(field_id, label, control='text', required=False, **extra):
    return {'field_id': field_id, 'label': label, 'control': control,
            'required': required, **extra}


def form(kind, operation, field):
    """Dialog fields; ids follow the inherited dialogs."""
    facts_key = FACTS[kind][0]
    alter = operation == 'alter'

    def initial(key):
        return {'initial_value_path': [facts_key, key]} if alter else {}
    table_columns = [_column('table_name', 'Table (schema.table)',
                             required=True),
                     _column('columns', 'Columns (comma-separated)'),
                     _column('where', 'Row filter')]
    schema_columns = [_column('schema', 'Schema', required=True)]
    if operation == 'drop':
        fields = [field('cascade', 'Drop dependent objects', 'boolean'),
                  field('confirmation', f'Type the {kind} name to confirm',
                        required=True)]
    elif kind == 'publication':
        fields = [field('name', 'Name', required=not alter, **initial('name')),
                  field('pubowner', 'Owner', help=(
                      'Empty keeps the owner.' if alter else 'OWNER TO')),
                  field('all_table', 'All tables', 'boolean', **(
                      {'help': 'Fixed once created.'} if alter else {}),
                      **initial('all_table')),
                  field('only_table', 'Only the listed tables (not their '
                        'partitions or children)', 'boolean')]
        if alter:
            fields += [field('pubtable', 'Tables', 'grid',
                             columns=table_columns, help='Current members.',
                             **initial('pubtable')),
                       field('add_tables', 'Add tables', 'grid',
                             columns=table_columns),
                       field('drop_tables', 'Drop tables', 'grid',
                             columns=[table_columns[0]]),
                       field('pubschema', 'Tables in schemas', 'grid',
                             columns=schema_columns, help='Current members.',
                             **initial('pubschema')),
                       field('add_schemas', 'Add tables in schemas', 'grid',
                             columns=schema_columns),
                       field('drop_schemas', 'Drop tables in schemas',
                             'grid', columns=schema_columns)]
        else:
            fields += [field('pubtable', 'Tables', 'grid',
                             columns=table_columns, help=(
                                 'Column lists and row filters need '
                                 'PostgreSQL 15.')),
                       field('pubschema', 'Tables in schemas', 'grid',
                             columns=schema_columns,
                             help='PostgreSQL 15 and later.')]
        for key, keyword in EVENTS:
            fields.append(field(key, keyword.upper(), 'boolean',
                                **({} if alter else {'default': True}),
                                **initial(key)))
        fields += [field('publish_via_partition_root', 'Publish via root',
                         'boolean', **initial('publish_via_partition_root')),
                   field('description', 'Comment', 'multiline',
                         **initial('description'))]
    else:
        fields = [field('name', 'Name', required=not alter, **initial('name'))]
        if alter:
            fields.append(field('subowner', 'Owner',
                                help='Empty keeps the owner.'))
        else:
            fields += [field(key, label, help=note) for key, label, note in (
                ('host', 'Host name/address', ''),)]
            fields.append(field('port', 'Port', 'number'))
            fields += [field(key, label, help=note) for key, label, note in (
                ('db', 'Database', ''),
                ('username', 'Username', ''),
                ('passfile', 'Passfile', 'A password file on the server '
                 'host; the password itself stays with the inherited '
                 'dialog.'),
                ('connect_timeout', 'Connection timeout', ''),
                ('sslmode', 'SSL mode', ''),
                ('sslcert', 'Client certificate', ''),
                ('sslkey', 'Client certificate key', ''),
                ('sslrootcert', 'Root certificate', ''),
                ('sslcrl', 'Certificate revocation list', ''))]
            fields.append(field('sslcompression', 'SSL compression',
                                'boolean'))
        fields.append(field('pub', 'Publications', help=(
            'Comma-separated publication names.'), required=not alter,
            **initial('pub')))
        if not alter:
            fields += [field('connect', 'Connect', 'boolean', default=True),
                       field('copy_data', 'Copy data', 'boolean',
                             default=True),
                       field('create_slot', 'Create slot', 'boolean',
                             default=True)]
        fields += [
            field('enabled', 'Enabled', 'boolean',
                  **({} if alter else {'default': True}),
                  **initial('enabled')),
            field('slot_name', 'Slot name', help='NONE for no slot.',
                  **initial('slot_name')),
            field('sync', 'Synchronous commit', 'select', options=[
                {'value': item, 'label': item} for item in SYNC_COMMIT],
                **initial('sync')),
            field('streaming', 'Streaming', 'select', options=[
                {'value': item, 'label': item}
                for item in STREAMING.values()],
                help='PostgreSQL 14; parallel needs 16.',
                **initial('streaming')),
            field('binary', 'Binary', 'boolean', **initial('binary')),
            field('two_phase', 'Two-phase commit', 'boolean',
                  help='PostgreSQL 15.', **initial('two_phase')),
            field('disable_on_error', 'Disable on error', 'boolean',
                  help='PostgreSQL 15.', **initial('disable_on_error')),
            field('run_as_owner', 'Run as owner', 'boolean',
                  help='PostgreSQL 16.', **initial('run_as_owner')),
            field('password_required', 'Password required', 'boolean',
                  help='PostgreSQL 16.', **initial('password_required')),
            field('origin', 'Origin', 'select', options=[
                {'value': item, 'label': item} for item in ORIGINS],
                help='PostgreSQL 16.', **initial('origin')),
            field('failover', 'Failover', 'boolean', help='PostgreSQL 17.',
                  **initial('failover'))]
        if alter:
            fields += [field('refresh_pub', 'Refresh publication (runs '
                             'alone, outside a transaction)', 'boolean'),
                       field('copy_data_after_refresh', 'Copy data on '
                             'refresh', 'boolean'),
                       field('description', 'Comment', 'multiline',
                             **initial('description'))]
    return {'form_id': f'postgresql-{kind}-{operation}',
            'form_key': f'native:postgresql:database:{kind}',
            'title': f'{operation.title()} {kind}', 'fields': fields,
            'notes': 'A subscription\'s connection string carries '
                     'credentials: it is never shown, and changing it or '
                     'its password stays with the inherited dialog.'}

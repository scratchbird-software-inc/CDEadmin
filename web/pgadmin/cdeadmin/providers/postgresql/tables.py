"""PostgreSQL table editor on the provider tree (M7, 2026-11-11).

The dialog is the table family form (``forms/table.form.json``), whose
field ids are the inherited table dialog's. Create compiles the one
``CREATE TABLE`` the inherited template rendered, with its columns,
constraints, LIKE source, OF type, PARTITION BY, INHERITS, access method,
storage options and tablespace, followed by owner, row security, labels,
grants and comments; alter emits one statement per changed table-level
fact; drop is ``DROP TABLE`` with optional CASCADE and a typed name.

Columns and constraints of an existing table are edited on their own
nodes (the column and constraint editors), so alter ignores those grids.
Column clauses and constraint bodies come from those editors' compilers,
so one table create and a later column or constraint create render the
same text. Every value is a literal, a validated identifier, or a type or
expression admitted by PostgreSQL's own parser.
"""
from __future__ import annotations

from . import columns as column_editor
from . import constraints as constraint_editor
from .native_admin import (
    PostgreSQLNativeAdminError, _flag, _identifier, _literal, _name,
    _qualified, _reference, _type_reference,
)
from .policies import expression
from .views import _options

PRIVILEGE_CODES = {'a': 'INSERT', 'r': 'SELECT', 'w': 'UPDATE',
                   'd': 'DELETE', 'D': 'TRUNCATE', 'x': 'REFERENCES',
                   't': 'TRIGGER'}
REPLICA_IDENTITY = {'d': 'DEFAULT', 'f': 'FULL', 'n': 'NOTHING',
                    'i': 'USING INDEX'}
PARTITION_TYPES = ('range', 'list', 'hash')
LIKE_OPTIONS = (('like_default_value', 'DEFAULTS'),
                ('like_constraints', 'CONSTRAINTS'),
                ('like_indexes', 'INDEXES'), ('like_storage', 'STORAGE'),
                ('like_comments', 'COMMENTS'),
                ('like_compression', 'COMPRESSION'),
                ('like_generated', 'GENERATED'),
                ('like_identity', 'IDENTITY'),
                ('like_statistics', 'STATISTICS'))
AUTOVACUUM = ('autovacuum_enabled', 'autovacuum_analyze_scale_factor',
              'autovacuum_analyze_threshold', 'autovacuum_freeze_max_age',
              'autovacuum_vacuum_cost_delay', 'autovacuum_vacuum_cost_limit',
              'autovacuum_vacuum_scale_factor',
              'autovacuum_vacuum_threshold', 'autovacuum_freeze_min_age',
              'autovacuum_freeze_table_age',
              'autovacuum_vacuum_insert_threshold',
              'autovacuum_vacuum_insert_scale_factor')
_NUMBER_RANGES = {'fillfactor': (10, 100), 'parallel_workers': (0, 1024),
                  'toast_tuple_target': (128, 8160)}


def _refuse(message):
    raise PostgreSQLNativeAdminError(message)


def _blank(value):
    return value is None or value == ''


def facts(native):
    """Table-level facts from the captured pg_class row. Owner, tablespace
    and access method are OIDs in the row, so their names are not known
    here; the editor treats a value the dialog supplies as a change."""
    row = native.get('catalog_row') or {}
    options = _options(row.get('reloptions'))
    autovacuum = {key: value for key, value in options.items()
                  if key in AUTOVACUUM}

    def number(key):
        value = options.get(key)
        return int(value) if isinstance(value, str) and value.isdigit() \
            else None
    return {
        'schema': native.get('schema'),
        'name': native.get('name') or row.get('relname'),
        'relowner': native.get('owner'),
        'relpersistence': row.get('relpersistence') == 'u',
        'description': native.get('comment') or '',
        'spcname': native.get('tablespace'),
        'fillfactor': number('fillfactor'),
        'parallel_workers': number('parallel_workers'),
        'toast_tuple_target': number('toast_tuple_target'),
        'autovacuum_enabled': {'true': 't', 'false': 'f'}.get(
            str(options.get('autovacuum_enabled', '')).lower(), 'x'),
        'autovacuum_custom': bool(autovacuum),
        'vacuum_settings': autovacuum,
        'rlspolicy': bool(row.get('relrowsecurity')),
        'forcerlspolicy': bool(row.get('relforcerowsecurity')),
        'replica_identity': REPLICA_IDENTITY.get(row.get('relreplident'),
                                                 None),
        'is_partitioned': row.get('relkind') == 'p',
        'relkind': row.get('relkind'),
        'amname': native.get('access_method'),
    }


# -- values -----------------------------------------------------------------

def _number(value, key):
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    low, high = _NUMBER_RANGES[key]
    if type(value) is not int or not low <= value <= high:
        _refuse(f'{key} runs from {low} to {high}')
    return value


def _rows(draft, key):
    value = draft.get(key)
    if _blank(value):
        return []
    if not isinstance(value, list) or any(
            not isinstance(item, dict) for item in value):
        _refuse(f'{key} must be a list of rows')
    return value


def _names(value, label):
    if isinstance(value, str):
        value = [part.strip() for part in value.split(',') if part.strip()]
    if not isinstance(value, list) or not value:
        _refuse(f'{label} needs at least one entry')
    return [item.get('column') if isinstance(item, dict) else item
            for item in value]


def _grantee(value):
    value = _name(value, 'grantee')
    return 'PUBLIC' if value.upper() == 'PUBLIC' else _identifier(
        value, 'grantee')


def _grant(qualified, row):
    codes = row.get('privileges')
    if isinstance(codes, str):
        codes = list(codes.replace(',', '').replace(' ', ''))
    if not isinstance(codes, list) or not codes or any(
            code not in PRIVILEGE_CODES for code in codes):
        _refuse('table privileges are codes among '
                + ', '.join(PRIVILEGE_CODES))
    words = [PRIVILEGE_CODES[code] for code in PRIVILEGE_CODES
             if code in codes]
    privileges = 'ALL' if len(words) == len(PRIVILEGE_CODES) else \
        ', '.join(words)
    option = ' WITH GRANT OPTION' if _flag(row, 'with_grant') else ''
    return (f'GRANT {privileges} ON TABLE {qualified} TO '
            f'{_grantee(row.get("grantee"))}{option}')


def _label(qualified, row):
    provider = _name(row.get('provider'), 'provider')
    label = row.get('label')
    if not isinstance(label, str) or not label:
        _refuse('a security label needs text')
    return (f'SECURITY LABEL FOR {_identifier(provider, "provider")} ON TABLE '
            f'{qualified} IS {_literal(label, "label")}')


def _autovacuum_rows(draft, key):
    """Storage parameters from the inherited grid: one row per parameter,
    ``name`` (or ``label`` when the dialog carries only that), ``value``."""
    result = []
    for row in _rows(draft, key):
        name = row.get('name') or row.get('label')
        if not isinstance(name, str) or name not in AUTOVACUUM:
            _refuse(f'{key} rows name an autovacuum storage parameter')
        value = row.get('value')
        if _blank(value):
            continue
        text = str(value).strip()
        if not all(ch.isdigit() or ch == '.' for ch in text) or \
                text.count('.') > 1:
            _refuse(f'{name} must be a number')
        result.append((name, text))
    return result


# -- create -----------------------------------------------------------------

def _column_clause(row):
    name = _identifier(_name(row.get('name'), 'name'), 'name')
    clause = name + ' ' + _type_reference(row.get('cltype'), 'cltype')
    if not _blank(row.get('attcompression')):
        clause += ' COMPRESSION ' + column_editor._compression(
            row['attcompression'])
    if not _blank(row.get('collspcname')):
        clause += ' COLLATE ' + _reference(row['collspcname'], 'collation')
    if _flag(row, 'attnotnull') if 'attnotnull' in row else False:
        clause += ' NOT NULL'
    constype = row.get('colconstype') or 'n'
    if constype not in ('n', 'i', 'g'):
        _refuse('colconstype must be n, i or g')
    if constype != 'g' and not _blank(row.get('defval')):
        clause += ' DEFAULT ' + expression(row['defval'], 'default')
    if constype == 'i':
        clause += ' ' + column_editor._identity_clause(row)
    elif constype == 'g':
        if _blank(row.get('genexpr')):
            _refuse('a generated column needs genexpr')
        clause += (' GENERATED ALWAYS AS ('
                   + expression(row['genexpr'], 'genexpr') + ') STORED')
    return clause


def _constraint_row(contype, row):
    """Map an inherited constraint grid row onto the constraint editor's
    draft and render its body."""
    draft = dict(row)
    if contype in ('p', 'u'):
        if not _blank(row.get('columns')):
            draft['columns'] = _names(row['columns'], 'columns')
        if not _blank(row.get('include')):
            draft['include'] = _names(row['include'], 'include')
    elif contype == 'f':
        pairs = []
        for pair in _rows(row, 'columns'):
            pairs.append({'local_column': pair.get('local_column'),
                          'referenced': pair.get('referenced')})
        draft['fk_columns'] = pairs
        if _blank(row.get('remote_table')):
            reference = str(row.get('references_table_name') or '')
            schema, dot, table = reference.rpartition('.')
            if not dot:
                _refuse('a foreign key names its referenced table as '
                        'schema.table')
            draft['remote_schema'], draft['remote_table'] = schema, table
        if 'convalidated' in row:
            draft['not_valid'] = not _flag(row, 'convalidated')
    elif contype == 'c':
        if 'convalidated' in row:
            draft['not_valid'] = not _flag(row, 'convalidated')
    else:
        draft['elements'] = _rows(row, 'columns')
        if not _blank(row.get('include')):
            draft['include'] = _names(row['include'], 'include')
    body = constraint_editor._body(contype, draft)
    if not _blank(row.get('name')):
        body = ('CONSTRAINT ' + _identifier(_name(row['name'], 'name'), 'name')
                + ' ' + body)
    return body


def _partition_by(draft):
    kind = str(draft.get('partition_type') or '').lower()
    if kind not in PARTITION_TYPES:
        _refuse('partition_type must be range, list or hash')
    keys = []
    for row in _rows(draft, 'partition_keys'):
        if row.get('key_type') == 'expression' or (
                _blank(row.get('pt_column')) and
                not _blank(row.get('expression'))):
            key = '(' + expression(row.get('expression'), 'expression') + ')'
        else:
            key = _identifier(_name(row.get('pt_column'), 'pt_column'),
                              'pt_column')
        if not _blank(row.get('collationame')):
            key += ' COLLATE ' + _reference(row['collationame'], 'collation')
        if not _blank(row.get('op_class')):
            key += ' ' + _reference(row['op_class'], 'op_class')
        keys.append(key)
    if not keys:
        _refuse('a partitioned table needs at least one partition key')
    return f' PARTITION BY {kind.upper()} (' + ', '.join(keys) + ')'


def _with_options(draft):
    items = []
    for key in ('fillfactor', 'parallel_workers', 'toast_tuple_target'):
        if not _blank(draft.get(key)):
            items.append(f'{key}={_number(draft[key], key)}')
    enabled = draft.get('autovacuum_enabled')
    if enabled in ('t', 'f'):
        items.append('autovacuum_enabled=' + ('true' if enabled == 't'
                                              else 'false'))
    if _flag(draft, 'autovacuum_custom') if 'autovacuum_custom' in draft \
            else False:
        for name, value in _autovacuum_rows(draft, 'vacuum_table'):
            items.append(f'{name}={value}')
    toast = draft.get('toast_autovacuum_enabled')
    if toast in ('t', 'f'):
        items.append('toast.autovacuum_enabled=' + ('true' if toast == 't'
                                                    else 'false'))
    if _flag(draft, 'toast_autovacuum') if 'toast_autovacuum' in draft \
            else False:
        for name, value in _autovacuum_rows(draft, 'vacuum_toast'):
            items.append(f'toast.{name}={value}')
    return ' WITH (' + ', '.join(items) + ')' if items else ''


def _create(draft):
    schema = _name(draft.get('schema'), 'schema')
    name = _name(draft.get('name'), 'name')
    qualified = _qualified(schema, name)
    statement = 'CREATE '
    if _flag(draft, 'relpersistence') if 'relpersistence' in draft else False:
        statement += 'UNLOGGED '
    statement += f'TABLE {qualified}'
    if not _blank(draft.get('typname')):
        statement += ' OF ' + _type_reference(draft['typname'], 'typname')
    elements = []
    if not _blank(draft.get('like_relation')):
        like = 'LIKE ' + _reference(draft['like_relation'], 'like_relation')
        for key, word in LIKE_OPTIONS:
            if _flag(draft, key) if key in draft else False:
                like += ' INCLUDING ' + word
        elements.append(like)
    for row in _rows(draft, 'columns'):
        if _blank(row.get('name')):
            continue
        elements.append(_column_clause(row))
    for key, contype in (('primary_key', 'p'), ('unique_constraint', 'u'),
                         ('foreign_key', 'f'), ('check_constraint', 'c'),
                         ('exclude_constraint', 'x')):
        rows = _rows(draft, key)
        if key == 'primary_key' and len(rows) > 1:
            _refuse('a table has at most one primary key')
        for row in rows:
            elements.append(_constraint_row(contype, row))
    if elements or _blank(draft.get('typname')):
        statement += ' (' + ', '.join(elements) + ')'
    if _flag(draft, 'is_partitioned') if 'is_partitioned' in draft else False:
        statement += _partition_by(draft)
    parents = draft.get('coll_inherits')
    if not _blank(parents):
        if isinstance(parents, str):
            parents = [part.strip() for part in parents.split(',')
                       if part.strip()]
        statement += ' INHERITS (' + ', '.join(
            _reference(parent, 'coll_inherits') for parent in parents) + ')'
    if not _blank(draft.get('amname')):
        statement += ' USING ' + _identifier(_name(draft['amname'], 'amname'),
                                             'amname')
    statement += _with_options(draft)
    if not _blank(draft.get('spcname')):
        statement += ' TABLESPACE ' + _identifier(
            _name(draft['spcname'], 'spcname'), 'spcname')
    statements = [statement]
    if not _blank(draft.get('relowner')):
        statements.append(f'ALTER TABLE {qualified} OWNER TO '
                          + _identifier(_name(draft['relowner'], 'relowner'),
                                        'relowner'))
    if _flag(draft, 'rlspolicy') if 'rlspolicy' in draft else False:
        statements.append(f'ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY')
    if _flag(draft, 'forcerlspolicy') if 'forcerlspolicy' in draft else False:
        statements.append(f'ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY')
    for row in _rows(draft, 'seclabels'):
        statements.append(_label(qualified, row))
    for row in _rows(draft, 'relacl'):
        statements.append(_grant(qualified, row))
    if not _blank(draft.get('description')):
        statements.append(f'COMMENT ON TABLE {qualified} IS '
                          + _literal(str(draft['description']), 'comment'))
    for row in _rows(draft, 'columns'):
        if not _blank(row.get('name')) and not _blank(row.get('description')):
            statements.append(
                f'COMMENT ON COLUMN {qualified}.'
                f'{_identifier(_name(row["name"], "name"), "name")} IS '
                + _literal(str(row['description']), 'comment'))
    for key in ('primary_key', 'unique_constraint', 'foreign_key',
                'check_constraint', 'exclude_constraint'):
        for row in _rows(draft, key):
            if not _blank(row.get('name')) and not _blank(row.get('comment')):
                statements.append(
                    'COMMENT ON CONSTRAINT '
                    f'{_identifier(_name(row["name"], "name"), "name")} ON '
                    f'{qualified} IS '
                    + _literal(str(row['comment']), 'comment'))
    return statements


# -- alter ------------------------------------------------------------------

def _alter(native, draft):
    current = facts(native)
    schema = _name(current['schema'], 'schema')
    name = _name(current['name'], 'name')
    qualified = _qualified(schema, name)
    statements = []
    if not _blank(draft.get('name')) and draft['name'] != current['name']:
        name = _name(draft['name'], 'name')
        statements.append(f'ALTER TABLE {qualified} RENAME TO '
                          + _identifier(name, 'name'))
        qualified = _qualified(schema, name)
    if not _blank(draft.get('schema')) and \
            draft['schema'] != current['schema']:
        schema = _name(draft['schema'], 'schema')
        statements.append(f'ALTER TABLE {qualified} SET SCHEMA '
                          + _identifier(schema, 'schema'))
        qualified = _qualified(schema, name)
    alter = f'ALTER TABLE {qualified}'
    if not _blank(draft.get('relowner')) and \
            draft['relowner'] != current['relowner']:
        statements.append(f'{alter} OWNER TO '
                          + _identifier(_name(draft['relowner'], 'relowner'),
                                        'relowner'))
    if 'relpersistence' in draft and \
            _flag(draft, 'relpersistence') != current['relpersistence']:
        statements.append(f'{alter} SET '
                          + ('UNLOGGED' if draft['relpersistence']
                             else 'LOGGED'))
    if not _blank(draft.get('spcname')) and \
            draft['spcname'] != current['spcname']:
        statements.append(f'{alter} SET TABLESPACE '
                          + _identifier(_name(draft['spcname'], 'spcname'),
                                        'spcname'))
    if 'rlspolicy' in draft and _flag(draft, 'rlspolicy') != \
            current['rlspolicy']:
        statements.append(f'{alter} '
                          + ('ENABLE' if draft['rlspolicy'] else 'DISABLE')
                          + ' ROW LEVEL SECURITY')
    if 'forcerlspolicy' in draft and _flag(draft, 'forcerlspolicy') != \
            current['forcerlspolicy']:
        statements.append(f'{alter} '
                          + ('FORCE' if draft['forcerlspolicy']
                             else 'NO FORCE')
                          + ' ROW LEVEL SECURITY')
    sets, resets = [], []
    for key in ('fillfactor', 'parallel_workers', 'toast_tuple_target'):
        if _flag(draft, f'reset_{key}') if f'reset_{key}' in draft else False:
            resets.append(key)
        elif not _blank(draft.get(key)) and \
                _number(draft[key], key) != current[key]:
            sets.append(f'{key}={_number(draft[key], key)}')
    enabled = draft.get('autovacuum_enabled')
    if enabled in ('t', 'f') and enabled != current['autovacuum_enabled']:
        sets.append('autovacuum_enabled=' + ('true' if enabled == 't'
                                             else 'false'))
    elif enabled == 'x' and current['autovacuum_enabled'] != 'x':
        resets.append('autovacuum_enabled')
    if 'autovacuum_custom' in draft:
        if _flag(draft, 'autovacuum_custom'):
            for param, value in _autovacuum_rows(draft, 'vacuum_table'):
                if current['vacuum_settings'].get(param) != value:
                    sets.append(f'{param}={value}')
        elif current['autovacuum_custom']:
            resets.extend(param for param in current['vacuum_settings']
                          if param != 'autovacuum_enabled')
    if sets:
        statements.append(f'{alter} SET (' + ', '.join(sets) + ')')
    if resets:
        statements.append(f'{alter} RESET (' + ', '.join(resets) + ')')
    identity = draft.get('replica_identity')
    if not _blank(identity) and identity != current['replica_identity']:
        statements.append(f'{alter} REPLICA IDENTITY '
                          + _replica_identity(identity))
    for row in _rows(draft, 'seclabels'):
        statements.append(_label(qualified, row))
    for row in _rows(draft, 'relacl'):
        statements.append(_grant(qualified, row))
    for row in _rows(draft, 'revoke'):
        statements.append(f'REVOKE ALL ON TABLE {qualified} FROM '
                          + _grantee(row.get('grantee')))
    if 'description' in draft and (draft.get('description') or '') != \
            current['description']:
        value = draft.get('description') or ''
        statements.append(f'COMMENT ON TABLE {qualified} IS '
                          + ('NULL' if value == '' else
                             _literal(str(value), 'comment')))
    if not statements:
        _refuse('nothing to change')
    return statements


def _replica_identity(value):
    text = str(value).strip()
    upper = text.upper()
    if upper in ('DEFAULT', 'FULL', 'NOTHING'):
        return upper
    if upper.startswith('USING INDEX '):
        return 'USING INDEX ' + _identifier(
            _name(text[len('USING INDEX '):].strip(), 'index'), 'index')
    _refuse('replica_identity is DEFAULT, FULL, NOTHING or USING INDEX name')


def _drop(native, draft):
    current = facts(native)
    if _name(draft.get('confirmation'), 'confirmation') != current['name']:
        _refuse('drop confirmation does not match object name')
    cascade = ' CASCADE' if _flag(draft, 'cascade') else ''
    qualified = _qualified(_name(current['schema'], 'schema'),
                           _name(current['name'], 'name'))
    return [f'DROP TABLE {qualified}{cascade}']


def compile_operation(operation, native, draft):
    """One exact native text for the table lifecycle."""
    if operation == 'create':
        statements = _create(draft)
    elif operation == 'alter':
        statements = _alter(native, draft)
    elif operation == 'drop':
        statements = _drop(native, draft)
    else:
        _refuse('table inspection stays with the provider tree')
    return {'statement': ';\n'.join(statements), 'read_only': False}


# -- form -------------------------------------------------------------------

# Every top-level field the table family form sends, per mode, so the
# validator admits the dialog's draft; the compiler uses the subset above.
_FAMILY_FIELDS = {
    'create': ('name', 'relowner', 'schema', 'relpersistence', 'description',
               'columns', 'primary_key', 'foreign_key', 'check_constraint',
               'unique_constraint', 'exclude_constraint', 'is_partitioned',
               'partition_type', 'partition_keys', 'partitions', 'spcname',
               'fillfactor', 'coll_inherits', 'typname', 'rlspolicy',
               'forcerlspolicy', 'amname', 'toast_tuple_target',
               'parallel_workers', 'relhasoids', 'like_relation',
               'like_default_value', 'like_constraints', 'like_indexes',
               'like_storage', 'like_comments', 'like_compression',
               'like_generated', 'like_identity', 'like_statistics',
               'autovacuum_custom', 'autovacuum_enabled', 'vacuum_table',
               'toast_autovacuum', 'toast_autovacuum_enabled', 'vacuum_toast',
               'relacl', 'seclabels'),
    'alter': ('name', 'oid', 'relowner', 'schema', 'is_sys_table',
              'relpersistence', 'description', 'columns', 'primary_key',
              'foreign_key', 'check_constraint', 'unique_constraint',
              'exclude_constraint', 'is_partitioned', 'partition_scheme',
              'partitions', 'spcname', 'fillfactor', 'reset_fillfactor',
              'coll_inherits', 'inherited_tables_cnt', 'relhassubclass',
              'typname', 'rlspolicy', 'forcerlspolicy', 'replica_identity',
              'amname', 'toast_tuple_target', 'reset_toast_tuple_target',
              'parallel_workers', 'reset_parallel_workers', 'relhasoids',
              'conname', 'vacuum_settings_str', 'autovacuum_custom',
              'autovacuum_enabled', 'vacuum_table', 'toast_autovacuum',
              'toast_autovacuum_enabled', 'vacuum_toast', 'relacl_str',
              'relacl', 'seclabels', 'revoke', 'reltuples', 'rows_cnt'),
}
_GRIDS = ('columns', 'primary_key', 'foreign_key', 'check_constraint',
          'unique_constraint', 'exclude_constraint', 'partition_keys',
          'partitions', 'vacuum_table', 'vacuum_toast', 'relacl',
          'seclabels', 'revoke')
_BOOLEANS = ('relpersistence', 'is_partitioned', 'rlspolicy', 'forcerlspolicy',
             'relhasoids', 'like_default_value', 'like_constraints',
             'like_indexes', 'like_storage', 'like_comments',
             'like_compression', 'like_generated', 'like_identity',
             'like_statistics', 'autovacuum_custom', 'toast_autovacuum',
             'is_sys_table', 'relhassubclass', 'reset_fillfactor',
             'reset_toast_tuple_target', 'reset_parallel_workers')


def form(operation, field):
    """The validator's view of the table family form: every field id the
    dialog sends, typed loosely; the family form file carries the labels,
    tabs and grid columns the dialog shows."""
    if operation == 'drop':
        return {'form_id': 'postgresql-table-drop',
                'form_key': 'native:postgresql:schema:table',
                'title': 'Drop table', 'fields': [
                    field('cascade', 'Drop dependent objects (CASCADE)',
                          'boolean'),
                    field('confirmation', 'Type the table name to confirm',
                          required=True)]}
    alter = operation == 'alter'
    fields = []
    for field_id in _FAMILY_FIELDS[operation]:
        label = field_id.replace('_', ' ').capitalize()
        if field_id in _GRIDS:
            fields.append(field(field_id, label, 'grid', columns=[]))
        elif field_id in _BOOLEANS:
            fields.append(field(field_id, label, 'boolean'))
        elif field_id in ('autovacuum_enabled', 'toast_autovacuum_enabled'):
            fields.append(field(field_id, label, 'select', options=[
                {'value': 'x', 'label': 'Not set'},
                {'value': 't', 'label': 'True'},
                {'value': 'f', 'label': 'False'}]))
        elif field_id in ('fillfactor', 'parallel_workers',
                          'toast_tuple_target'):
            fields.append(field(field_id, label, 'number'))
        else:
            fields.append(field(field_id, label,
                                required=field_id in ('name', 'schema')
                                and not alter))
    return {'form_id': f'postgresql-table-{operation}',
            'form_key': 'native:postgresql:schema:table',
            'title': ('Edit' if alter else 'Create') + ' table',
            'fields': fields,
            'notes': ('Columns and constraints of an existing table are '
                      'edited on their own nodes; the Columns and '
                      'Constraints grids act at creation only. Owner, '
                      'tablespace and access method are applied when the '
                      'dialog supplies them.')}

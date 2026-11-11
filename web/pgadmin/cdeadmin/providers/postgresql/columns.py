"""PostgreSQL column editor on the provider tree (M7, 2026-11-11).

Create, alter and drop compile to the statements the inherited column
dialog rendered (``columns/sql/default/create.sql`` and ``update.sql``):
ADD COLUMN with its type, collation, NOT NULL, default, identity or
generated clause, then comment, statistics, storage and compression; on
alter one statement per changed fact, compared against the captured
``pg_attribute`` row. Field ids follow the inherited dialog
(``column.ui.js``). Every value is a literal, a validated identifier or
a type or expression admitted by PostgreSQL's own parser; the engine
never receives free text as an identifier. Column privileges, security
labels and attribute options stay with the inherited dialog for now.
"""
from __future__ import annotations

from .native_admin import (
    PostgreSQLNativeAdminError, _flag, _identifier, _literal, _name,
    _qualified, _reference, _type_reference,
)
from .policies import expression

STORAGE = {'p': 'PLAIN', 'm': 'MAIN', 'e': 'EXTERNAL', 'x': 'EXTENDED'}
COMPRESSION = ('pglz', 'lz4')
IDENTITY = {'a': 'ALWAYS', 'd': 'BY DEFAULT'}
_SEQUENCE = (('seqincrement', 'INCREMENT'), ('seqstart', 'START'),
             ('seqmin', 'MINVALUE'), ('seqmax', 'MAXVALUE'),
             ('seqcache', 'CACHE'))


def _refuse(message):
    raise PostgreSQLNativeAdminError(message)


def _blank(value):
    return value is None or value == ''


def facts(native):
    """The column's current values from the captured attribute row."""
    row = native.get('catalog_row') or {}
    identity = row.get('attidentity') or ''
    generated = row.get('attgenerated') or ''
    storage = row.get('attstorage') or ''
    return {
        'schema': native.get('schema'),
        'table': native.get('table'),
        'name': native.get('name') or row.get('attname'),
        'attnum': native.get('attnum', row.get('attnum')),
        'cltype': native.get('data_type') or row.get('formatted_type'),
        'attnotnull': bool(native.get('not_null', row.get('attnotnull'))),
        'defval': native.get('default_expression') or '',
        'description': native.get('comment') or '',
        'colconstype': 'i' if identity else 'g' if generated else 'n',
        'attidentity': identity,
        # PostgreSQL 17+ stores the default target as NULL; the dialog's -1.
        'attstattarget': (-1 if row.get('attstattarget') is None
                          else row.get('attstattarget')),
        'attstorage': storage if storage in STORAGE else '',
        'attcompression': row.get('attcompression') or '',
    }


# -- values -----------------------------------------------------------------

def _int(value, label, minimum=None):
    if isinstance(value, bool) or _blank(value):
        _refuse(f'{label} must be a whole number')
    if isinstance(value, str) and value.strip().lstrip('-').isdigit():
        value = int(value.strip())
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if type(value) is not int:
        _refuse(f'{label} must be a whole number')
    if minimum is not None and value < minimum:
        _refuse(f'{label} is at least {minimum}')
    return value


def _storage(value):
    if value not in STORAGE:
        _refuse('attstorage must be one of p, m, e, x')
    return STORAGE[value]


def _compression(value):
    if value not in COMPRESSION:
        _refuse('attcompression must be pglz or lz4')
    return value


def _identity_options(draft):
    parts = []
    if _flag(draft, 'seqcycle'):
        parts.append('CYCLE')
    for key, word in _SEQUENCE:
        if not _blank(draft.get(key)):
            parts.append(f'{word} {_int(draft.get(key), key)}')
    return ' (' + ' '.join(parts) + ')' if parts else ''


def _identity_clause(draft, verb='GENERATED'):
    kind = draft.get('attidentity')
    if kind not in IDENTITY:
        _refuse('attidentity must be a (always) or d (by default)')
    return f'{verb} {IDENTITY[kind]} AS IDENTITY' + _identity_options(draft)


def _table(current):
    return _qualified(_name(current['schema'], 'schema'),
                      _name(current['table'], 'table'))


def _column_ref(current, name=None):
    return _identifier(_name(name or current['name'], 'name'), 'name')


# -- statements -------------------------------------------------------------

def _create(native, draft):
    current = facts(native)
    table = _table(current)
    name = _name(draft.get('name'), 'name')
    column = _identifier(name, 'name')
    constype = draft.get('colconstype', 'n')
    if constype not in ('n', 'i', 'g'):
        _refuse('colconstype must be n (none), i (identity) or g (generated)')
    clause = (f'ALTER TABLE {table} ADD COLUMN {column} '
              + _type_reference(draft.get('cltype'), 'cltype'))
    if not _blank(draft.get('collspcname')):
        clause += ' COLLATE ' + _reference(draft['collspcname'], 'collation')
    if _flag(draft, 'attnotnull'):
        clause += ' NOT NULL'
    if constype != 'g' and not _blank(draft.get('defval')):
        clause += ' DEFAULT ' + expression(draft['defval'], 'default')
    if constype == 'i':
        clause += ' ' + _identity_clause(draft)
    elif constype == 'g':
        if _blank(draft.get('genexpr')):
            _refuse('a generated column needs genexpr')
        clause += (' GENERATED ALWAYS AS ('
                   + expression(draft['genexpr'], 'genexpr') + ') STORED')
    statements = [clause]
    target = f'{table}.{column}'
    if not _blank(draft.get('description')):
        statements.append(f'COMMENT ON COLUMN {target} IS '
                          + _literal(str(draft['description']), 'comment'))
    if not _blank(draft.get('attstattarget')):
        target = _int(draft['attstattarget'], 'attstattarget', -1)
        statements.append(f'ALTER TABLE {table} ALTER COLUMN {column} '
                          f'SET STATISTICS {target}')
    if not _blank(draft.get('attstorage')):
        statements.append(f'ALTER TABLE {table} ALTER COLUMN {column} '
                          f'SET STORAGE {_storage(draft["attstorage"])}')
    if not _blank(draft.get('attcompression')):
        statements.append(f'ALTER TABLE {table} ALTER COLUMN {column} '
                          f'SET COMPRESSION '
                          f'{_compression(draft["attcompression"])}')
    return statements


def _alter(native, draft):
    current = facts(native)
    table = _table(current)
    old = _column_ref(current)
    statements = []
    name = current['name']
    if not _blank(draft.get('name')) and draft['name'] != current['name']:
        name = _name(draft['name'], 'name')
        statements.append(f'ALTER TABLE {table} RENAME {old} TO '
                          + _identifier(name, 'name'))
    column = _identifier(name, 'name')
    alter = f'ALTER TABLE {table} ALTER COLUMN {column}'
    type_changed = (not _blank(draft.get('cltype')) and
                    draft['cltype'] != current['cltype'])
    if type_changed or not _blank(draft.get('collspcname')):
        clause = (f'{alter} TYPE '
                  + _type_reference(draft.get('cltype') or current['cltype'],
                                    'cltype'))
        if not _blank(draft.get('collspcname')):
            clause += ' COLLATE ' + _reference(draft['collspcname'],
                                               'collation')
        statements.append(clause)
    if 'defval' in draft and current['colconstype'] != 'g':
        if _blank(draft.get('defval')):
            if current['defval']:
                statements.append(f'{alter} DROP DEFAULT')
        elif draft['defval'] != current['defval']:
            statements.append(f'{alter} SET DEFAULT '
                              + expression(draft['defval'], 'default'))
    if 'attnotnull' in draft and _flag(draft, 'attnotnull') != \
            current['attnotnull']:
        statements.append(f'{alter} '
                          + ('SET' if draft['attnotnull'] else 'DROP')
                          + ' NOT NULL')
    constype = draft.get('colconstype')
    if constype == 'i':
        if current['colconstype'] == 'g':
            _refuse('a generated column cannot become an identity column')
        if current['colconstype'] != 'i':
            statements.append(f'{alter} ADD ' + _identity_clause(draft))
        else:
            if (not _blank(draft.get('attidentity')) and
                    draft['attidentity'] != current['attidentity']):
                kind = draft['attidentity']
                if kind not in IDENTITY:
                    _refuse('attidentity must be a (always) or d (by default)')
                statements.append(f'{alter} SET GENERATED {IDENTITY[kind]}')
            options = [f'SET {word} {_int(draft[key], key)}'
                       for key, word in _SEQUENCE
                       if not _blank(draft.get(key))]
            if 'seqcycle' in draft:
                options.append('SET CYCLE' if _flag(draft, 'seqcycle')
                               else 'SET NO CYCLE')
            if options:
                statements.append(f'{alter} ' + ' '.join(options))
    elif constype == 'n' and current['colconstype'] == 'i':
        statements.append(f'{alter} DROP IDENTITY')
    elif constype == 'g' and current['colconstype'] != 'g':
        _refuse('an existing column cannot become a generated column; '
                'add a new one')
    if (not _blank(draft.get('attstattarget')) and
            _int(draft['attstattarget'], 'attstattarget', -1)
            != current['attstattarget']):
        target = _int(draft['attstattarget'], 'attstattarget', -1)
        statements.append(f'{alter} SET STATISTICS {target}')
    if (not _blank(draft.get('attstorage')) and
            draft['attstorage'] != current['attstorage']):
        statements.append(f'{alter} SET STORAGE '
                          f'{_storage(draft["attstorage"])}')
    if (not _blank(draft.get('attcompression')) and
            draft['attcompression'] != current['attcompression']):
        statements.append(f'{alter} SET COMPRESSION '
                          f'{_compression(draft["attcompression"])}')
    if 'description' in draft and (draft.get('description') or '') != \
            current['description']:
        value = draft.get('description') or ''
        statements.append(f'COMMENT ON COLUMN {table}.{column} IS '
                          + ('NULL' if value == '' else
                             _literal(str(value), 'comment')))
    if not statements:
        _refuse('nothing to change')
    return statements


def _drop(native, draft):
    current = facts(native)
    if _name(draft.get('confirmation'), 'confirmation') != current['name']:
        _refuse('drop confirmation does not match object name')
    cascade = ' CASCADE' if _flag(draft, 'cascade') else ''
    return [f'ALTER TABLE {_table(current)} DROP COLUMN '
            f'{_column_ref(current)}{cascade}']


def compile_operation(operation, native, draft):
    """One exact native text for the column lifecycle."""
    if operation == 'create':
        statements = _create(native, draft)
    elif operation == 'alter':
        statements = _alter(native, draft)
    elif operation == 'drop':
        statements = _drop(native, draft)
    else:
        _refuse('column inspection stays with the provider tree')
    return {'statement': ';\n'.join(statements), 'read_only': False}


# -- form -------------------------------------------------------------------

def _when(controller, value):
    # The client reads ``field``; the server validator reads ``field_id``.
    return {'field': controller, 'field_id': controller, 'equals': value}


def form(operation, field):
    """Dialog fields; ids follow the inherited column dialog."""
    if operation == 'drop':
        return {'form_id': 'postgresql-column-drop',
                'form_key': 'native:postgresql:schema:column',
                'title': 'Drop column', 'fields': [
                    field('cascade', 'Drop dependent objects (CASCADE)',
                          'boolean'),
                    field('confirmation', 'Type the column name to confirm',
                          required=True)]}
    alter = operation == 'alter'
    initial = (lambda key: {'initial_value_path': ['column_facts', key]}) \
        if alter else (lambda key: {})
    fields = [
        field('name', 'Name', required=not alter, **initial('name')),
        field('cltype', 'Data type', required=not alter, help=(
            'A native type with its modifiers, such as numeric(10,2) or '
            'text[].'), **initial('cltype')),
        field('collspcname', 'Collation', help=(
            'Empty keeps the type default; on alter it is applied with the '
            'type.')),
        field('attnotnull', 'Not NULL', 'boolean', **initial('attnotnull')),
        field('defval', 'Default', help=(
            'An expression; empty drops the default on alter.'),
            **initial('defval')),
        field('colconstype', 'Constraint', 'select', options=[
            {'value': 'n', 'label': 'None'},
            {'value': 'i', 'label': 'Identity'},
            {'value': 'g', 'label': 'Generated'}],
            default='n', **initial('colconstype')),
        field('attidentity', 'Identity', 'select', options=[
            {'value': 'a', 'label': 'Always'},
            {'value': 'd', 'label': 'By default'}],
            visible_when=_when('colconstype', 'i'),
            **initial('attidentity')),
        field('seqincrement', 'Increment', 'number',
              visible_when=_when('colconstype', 'i')),
        field('seqstart', 'Start', 'number',
              visible_when=_when('colconstype', 'i')),
        field('seqmin', 'Minimum', 'number',
              visible_when=_when('colconstype', 'i')),
        field('seqmax', 'Maximum', 'number',
              visible_when=_when('colconstype', 'i')),
        field('seqcache', 'Cache', 'number',
              visible_when=_when('colconstype', 'i')),
        field('seqcycle', 'Cycled', 'boolean',
              visible_when=_when('colconstype', 'i')),
        field('genexpr', 'Expression', help=(
            'GENERATED ALWAYS AS (expression) STORED; set at creation only.'),
            visible_when=_when('colconstype', 'g')),
        field('attstattarget', 'Statistics', 'number', help=(
            '-1 uses the default statistics target.'),
            **initial('attstattarget')),
        field('attstorage', 'Storage', 'select', options=[
            {'value': code, 'label': word.title()}
            for code, word in STORAGE.items()], **initial('attstorage')),
        field('attcompression', 'Compression', 'select', options=[
            {'value': code, 'label': code} for code in COMPRESSION],
            **initial('attcompression')),
        field('description', 'Comment', 'multiline',
              **initial('description')),
    ]
    return {'form_id': f'postgresql-column-{operation}',
            'form_key': 'native:postgresql:schema:column',
            'title': ('Edit' if alter else 'Create') + ' column',
            'fields': fields,
            'notes': ('Privileges, security labels and attribute options '
                      'stay with the inherited dialog for now. A type '
                      'change carries no USING clause: PostgreSQL must be '
                      'able to cast the existing values.')}

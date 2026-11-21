"""PostgreSQL table constraints on the provider tree (M7, 2026-11-11).

One capture kind, five inherited node types (``pg_constraint.contype``):
primary key and unique (``index_constraint``), foreign key, check and
exclusion. Create compiles the ``ALTER TABLE ... ADD CONSTRAINT`` the
inherited templates rendered for each kind; alter emits one statement per
changed fact (rename, validate, comment, index fill factor and tablespace,
a foreign key's deferrability); drop is ``DROP CONSTRAINT`` with optional
CASCADE and a typed name. Field ids follow the inherited dialogs. Names
and columns are identifiers, expressions and predicates are admitted by
PostgreSQL's own parser, and everything else is a literal.
"""
from __future__ import annotations

from .native_admin import (
    PostgreSQLNativeAdminError, _flag, _identifier, _literal, _name,
    _qualified, _reference,
)
from .policies import expression

CONTYPES = {'p': 'PRIMARY KEY', 'u': 'UNIQUE', 'f': 'FOREIGN KEY',
            'c': 'CHECK', 'x': 'EXCLUDE', 'n': 'NOT NULL'}
ACTIONS = {'a': 'NO ACTION', 'r': 'RESTRICT', 'c': 'CASCADE',
           'n': 'SET NULL', 'd': 'SET DEFAULT'}
INDEX_BACKED = ('p', 'u', 'x')
ENFORCEABLE_CREATE_KINDS = ('f', 'c')


def _refuse(message):
    raise PostgreSQLNativeAdminError(message)


def _blank(value):
    return value is None or value == ''


def facts(native, relations=None):
    """The constraint's current values from the captured pg_constraint
    row; ``relations`` maps relation OID to (schema, name)."""
    row = native.get('catalog_row') or {}
    relations = relations or {}
    table = native.get('table')
    referenced = native.get('referenced_table')
    if table is None:
        table = relations.get(_oid(row.get('conrelid')), (None, None))[1]
    if referenced is None and _oid(row.get('confrelid')):
        schema, name = relations.get(_oid(row.get('confrelid')),
                                     (None, None))
        referenced = {'schema': schema, 'name': name}
    return {
        'schema': native.get('schema'),
        'table': table,
        'name': native.get('name') or row.get('conname'),
        'contype': row.get('contype'),
        'definition': native.get('definition'),
        'condeferrable': bool(row.get('condeferrable')),
        'condeferred': bool(row.get('condeferred')),
        'convalidated': row.get('convalidated') is not False,
        'conenforced': row.get('conenforced') is not False,
        'conperiod': bool(row.get('conperiod')),
        'connoinherit': bool(row.get('connoinherit')),
        'confupdtype': row.get('confupdtype') or '',
        'confdeltype': row.get('confdeltype') or '',
        'confmatchtype': row.get('confmatchtype') or '',
        'referenced_table': referenced,
        'comment': native.get('comment') or '',
    }


def _oid(value):
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return value if type(value) is int else None


# -- values -----------------------------------------------------------------

def _names(value, label):
    """A column list: a list of names or a comma-separated string."""
    if isinstance(value, str):
        value = [part.strip() for part in value.split(',') if part.strip()]
    if not isinstance(value, list) or not value:
        _refuse(f'{label} needs at least one column')
    return [_identifier(_name(item, label), label) for item in value]


def _rows(draft, key):
    value = draft.get(key)
    if _blank(value):
        return []
    if not isinstance(value, list) or any(
            not isinstance(item, dict) for item in value):
        _refuse(f'{key} must be a list of rows')
    return value


def _fillfactor(value):
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if type(value) is not int or not 10 <= value <= 100:
        _refuse('fillfactor runs from 10 to 100')
    return value


def _index_options(draft):
    text = ''
    include = draft.get('include')
    if not _blank(include):
        text += ' INCLUDE (' + ', '.join(_names(include, 'include')) + ')'
    if not _blank(draft.get('fillfactor')):
        text += f' WITH (FILLFACTOR={_fillfactor(draft["fillfactor"])})'
    if not _blank(draft.get('spcname')) and draft['spcname'] != 'pg_default':
        text += ' USING INDEX TABLESPACE ' + _identifier(
            _name(draft['spcname'], 'spcname'), 'spcname')
    return text


def _deferrable(draft):
    if not _flag(draft, 'condeferrable'):
        return ''
    return ' DEFERRABLE' + (' INITIALLY DEFERRED'
                            if _flag(draft, 'condeferred') else '')


def _action(draft, key):
    value = draft.get(key)
    if _blank(value):
        return ''
    if value not in ACTIONS:
        _refuse(f'{key} must be one of a, r, c, n, d')
    word = 'ON UPDATE' if key == 'confupdtype' else 'ON DELETE'
    return f' {word} {ACTIONS[value]}'


# -- statements -------------------------------------------------------------

def _table(current):
    return _qualified(_name(current['schema'], 'schema'),
                      _name(current['table'], 'table'))


def _enforcement_clause(contype, draft):
    mode = draft.get('enforcement')
    not_enforced_flag = _flag(draft, 'not_enforced') if 'not_enforced' in draft else False
    if _blank(mode) and not not_enforced_flag:
        return '', False
    if not _blank(mode):
        norm = str(mode).strip().upper()
        if norm not in ('ENFORCED', 'NOT ENFORCED'):
            _refuse('enforcement must be ENFORCED or NOT ENFORCED')
        if not_enforced_flag and norm == 'ENFORCED':
            _refuse('conflicting enforcement settings')
    else:
        norm = 'NOT ENFORCED'
    if contype not in ENFORCEABLE_CREATE_KINDS:
        _refuse('only CHECK and FOREIGN KEY constraints support ENFORCED / NOT ENFORCED')
    if norm == 'NOT ENFORCED' and _flag(draft, 'not_valid'):
        _refuse('NOT ENFORCED cannot be combined with NOT VALID')
    return f' {norm}', True


def _body(contype, draft):
    min_ver = None
    if contype == 'n':
        col = _identifier(_name(draft.get('not_null_column') or draft.get('column'), 'not_null_column'), 'not_null_column')
        if not _blank(draft.get('enforcement')) or _flag(draft, 'not_enforced'):
            _refuse('only CHECK and FOREIGN KEY constraints support ENFORCED / NOT ENFORCED')
        text = f'NOT NULL {col}'
        if _flag(draft, 'connoinherit'):
            text += ' NO INHERIT'
        return text, 180000
    if contype in ('p', 'u'):
        if not _blank(draft.get('enforcement')) or _flag(draft, 'not_enforced'):
            _refuse('only CHECK and FOREIGN KEY constraints support ENFORCED / NOT ENFORCED')
        without_overlaps = draft.get('without_overlaps_column')
        if not _blank(draft.get('index')):
            if not _blank(without_overlaps):
                _refuse('WITHOUT OVERLAPS cannot be combined with USING INDEX')
            return (f'{CONTYPES[contype]} USING INDEX '
                    + _identifier(_name(draft['index'], 'index'), 'index')), None
        cols = _names(draft.get('columns'), 'columns') if not _blank(draft.get('columns')) else []
        if not _blank(without_overlaps):
            wo_col = _identifier(_name(without_overlaps, 'without_overlaps_column'), 'without_overlaps_column')
            cols.append(f'{wo_col} WITHOUT OVERLAPS')
            min_ver = 180000
        if not cols:
            _refuse('columns needs at least one column')
        return (f'{CONTYPES[contype]} ('
                + ', '.join(cols) + ')'
                + _index_options(draft) + _deferrable(draft)), min_ver
    if contype == 'f':
        rows = _rows(draft, 'fk_columns')
        local_period = draft.get('local_period_column')
        remote_period = draft.get('referenced_period_column')
        if bool(_blank(local_period)) != bool(_blank(remote_period)):
            _refuse('PERIOD foreign keys require both local_period_column and referenced_period_column')
        if not rows and _blank(local_period):
            _refuse('a foreign key needs column pairs')
        local = [_identifier(_name(row.get('local_column'), 'local_column'),
                             'local_column') for row in rows]
        remote = [_identifier(_name(row.get('referenced'), 'referenced'),
                              'referenced') for row in rows]
        if not _blank(local_period):
            local.append('PERIOD ' + _identifier(_name(local_period, 'local_period_column'), 'local_period_column'))
            remote.append('PERIOD ' + _identifier(_name(remote_period, 'referenced_period_column'), 'referenced_period_column'))
            min_ver = 180000
        text = ('FOREIGN KEY (' + ', '.join(local) + ') REFERENCES '
                + _qualified(
                    _name(draft.get('remote_schema'), 'remote_schema'),
                    _name(draft.get('remote_table'), 'remote_table'))
                + ' (' + ', '.join(remote) + ')')
        if 'confmatchtype' in draft:
            text += ' MATCH FULL' if _flag(draft, 'confmatchtype') \
                else ' MATCH SIMPLE'
        text += _action(draft, 'confupdtype') + _action(draft, 'confdeltype')
        text += _deferrable(draft)
        enf_clause, enf_v18 = _enforcement_clause(contype, draft)
        if enf_v18:
            min_ver = 180000
        text += enf_clause
        if _flag(draft, 'not_valid'):
            text += ' NOT VALID'
        return text, min_ver
    if contype == 'c':
        text = 'CHECK (' + expression(draft.get('consrc'), 'consrc') + ')'
        if _flag(draft, 'connoinherit'):
            text += ' NO INHERIT'
        enf_clause, enf_v18 = _enforcement_clause(contype, draft)
        if enf_v18:
            min_ver = 180000
        text += enf_clause
        if _flag(draft, 'not_valid'):
            text += ' NOT VALID'
        return text, min_ver
    if not _blank(draft.get('enforcement')) or _flag(draft, 'not_enforced'):
        _refuse('only CHECK and FOREIGN KEY constraints support ENFORCED / NOT ENFORCED')
    rows = _rows(draft, 'elements')
    if not rows:
        _refuse('an exclusion constraint needs at least one element')
    elements = []
    for row in rows:
        if _flag(row, 'is_exp'):
            element = '(' + expression(row.get('column'), 'column') + ')'
        else:
            element = _identifier(_name(row.get('column'), 'column'),
                                  'column')
        if not _blank(row.get('oper_class')):
            element += ' ' + _reference(row['oper_class'], 'oper_class')
        if 'order' in row:
            element += ' ASC' if _flag(row, 'order') else ' DESC'
        if 'nulls_order' in row:
            element += ' NULLS FIRST' if _flag(row, 'nulls_order') \
                else ' NULLS LAST'
        element += ' WITH ' + _reference(row.get('operator'), 'operator',
                                         operator=True)
        elements.append(element)
    text = 'EXCLUDE'
    if not _blank(draft.get('amname')):
        text += ' USING ' + _identifier(_name(draft['amname'], 'amname'),
                                        'amname')
    text += ' (' + ', '.join(elements) + ')' + _index_options(draft)
    if not _blank(draft.get('indconstraint')):
        text += ' WHERE (' + expression(draft['indconstraint'],
                                        'indconstraint') + ')'
    return text + _deferrable(draft), None


def _create(native, draft):
    current = facts(native)
    table = _table(current)
    contype = draft.get('contype')
    if contype not in CONTYPES:
        _refuse('contype must be one of p, u, f, c, x, n')
    statement = f'ALTER TABLE {table} ADD'
    name = draft.get('name')
    if not _blank(name):
        statement += ' CONSTRAINT ' + _identifier(_name(name, 'name'), 'name')
    body_sql, min_ver = _body(contype, draft)
    statements = [statement + ' ' + body_sql]
    if not _blank(draft.get('comment')):
        if _blank(name):
            _refuse('a comment needs a constraint name')
        statements.append(
            f'COMMENT ON CONSTRAINT {_identifier(_name(name, "name"), "name")}'
            f' ON {table} IS ' + _literal(str(draft['comment']), 'comment'))
    return statements, min_ver


def _alter(native, draft):
    current = facts(native)
    table = _table(current)
    contype = current['contype']
    old = _identifier(_name(current['name'], 'name'), 'name')
    name = current['name']
    statements = []
    if not _blank(draft.get('name')) and draft['name'] != current['name']:
        name = _name(draft['name'], 'name')
        statements.append(f'ALTER TABLE {table} RENAME CONSTRAINT {old} TO '
                          + _identifier(name, 'name'))
    constraint = _identifier(name, 'name')
    min_ver = None
    if not _blank(draft.get('enforcement')) or 'not_enforced' in draft:
        enf_clause, _ = _enforcement_clause('f' if contype == 'f' else contype, draft)
        if contype != 'f':
            _refuse('PostgreSQL ALTER CONSTRAINT ENFORCED / NOT ENFORCED applies only to FOREIGN KEY constraints')
        target_enforced = enf_clause.strip() == 'ENFORCED'
        if target_enforced != current['conenforced']:
            statements.append(f'ALTER TABLE {table} ALTER CONSTRAINT {constraint}{enf_clause}')
            min_ver = 180000
    if contype in ('f', 'c') and _flag(draft, 'validate') and \
            not current['convalidated']:
        if not current['conenforced'] and not any('ENFORCED' in s and 'NOT ENFORCED' not in s for s in statements):
            _refuse('cannot VALIDATE a NOT ENFORCED constraint without enforcing it')
        statements.append(f'ALTER TABLE {table} VALIDATE CONSTRAINT '
                          f'{constraint}')
    if contype == 'f' and 'condeferrable' in draft and (
            _flag(draft, 'condeferrable') != current['condeferrable'] or
            (_flag(draft, 'condeferrable') and 'condeferred' in draft and
             _flag(draft, 'condeferred') != current['condeferred'])):
        clause = 'DEFERRABLE' if draft['condeferrable'] else 'NOT DEFERRABLE'
        if draft['condeferrable']:
            clause += (' INITIALLY DEFERRED' if _flag(draft, 'condeferred')
                       else ' INITIALLY IMMEDIATE')
        statements.append(f'ALTER TABLE {table} ALTER CONSTRAINT '
                          f'{constraint} {clause}')
    if contype in INDEX_BACKED:
        index = _qualified(_name(current['schema'], 'schema'), name)
        # The validator drops empty values, so a reset is its own flag.
        if _flag(draft, 'reset_fillfactor'):
            statements.append(f'ALTER INDEX {index} RESET (FILLFACTOR)')
        elif not _blank(draft.get('fillfactor')):
            statements.append(f'ALTER INDEX {index} SET (FILLFACTOR='
                              f'{_fillfactor(draft["fillfactor"])})')
        if not _blank(draft.get('spcname')):
            statements.append(f'ALTER INDEX {index} SET TABLESPACE '
                              + _identifier(_name(draft['spcname'], 'spcname'),
                                            'spcname'))
    if 'comment' in draft and (draft.get('comment') or '') != \
            current['comment']:
        value = draft.get('comment') or ''
        statements.append(
            f'COMMENT ON CONSTRAINT {constraint} ON {table} IS '
            + ('NULL' if value == '' else _literal(str(value), 'comment')))
    if not statements:
        _refuse('nothing to change')
    return statements, min_ver


def _drop(native, draft):
    current = facts(native)
    if _name(draft.get('confirmation'), 'confirmation') != current['name']:
        _refuse('drop confirmation does not match object name')
    cascade = ' CASCADE' if _flag(draft, 'cascade') else ''
    return [f'ALTER TABLE {_table(current)} DROP CONSTRAINT '
            f'{_identifier(_name(current["name"], "name"), "name")}{cascade}'], None


def compile_operation(operation, native, draft):
    """One exact native text for the constraint lifecycle."""
    if operation == 'create':
        statements, min_ver = _create(native, draft)
    elif operation == 'alter':
        statements, min_ver = _alter(native, draft)
    elif operation == 'drop':
        statements, min_ver = _drop(native, draft)
    else:
        _refuse('constraint inspection stays with the provider tree')
    result = {'statement': ';\n'.join(statements), 'read_only': False}
    if min_ver is not None:
        result['minimum_server_version'] = min_ver
    return result


# -- form -------------------------------------------------------------------

def _when(value):
    # The client reads ``field``; the server validator reads ``field_id``.
    return {'field': 'contype', 'field_id': 'contype',
            'in' if isinstance(value, list) else 'equals': value}


def form(operation, field):
    """Dialog fields; ids follow the inherited constraint dialogs."""
    def column(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    if operation == 'drop':
        return {'form_id': 'postgresql-constraint-drop',
                'form_key': 'native:postgresql:schema:constraint',
                'title': 'Drop constraint', 'fields': [
                    field('cascade', 'Drop dependent objects (CASCADE)',
                          'boolean'),
                    field('confirmation',
                          'Type the constraint name to confirm',
                          required=True)]}
    kinds = [{'value': code, 'label': word.title()}
             for code, word in CONTYPES.items()]
    if operation == 'alter':
        fields = [
            field('name', 'Name',
                  initial_value_path=['constraint_facts', 'name']),
            field('contype', 'Kind', 'select', options=kinds,
                  initial_value_path=['constraint_facts', 'contype'],
                  help='Fixed once created.'),
            field('validate', 'Validate now', 'boolean', visible_when=_when(
                ['f', 'c']), help='VALIDATE CONSTRAINT for one created '
                                  'NOT VALID.'),
            field('condeferrable', 'Deferrable', 'boolean',
                  visible_when=_when('f'),
                  initial_value_path=['constraint_facts', 'condeferrable']),
            field('condeferred', 'Initially deferred', 'boolean',
                  visible_when=_when('f'),
                  initial_value_path=['constraint_facts', 'condeferred']),
            field('enforcement', 'Enforcement (PostgreSQL 18+)', 'select',
                  options=[{'value': 'ENFORCED', 'label': 'Enforced'},
                           {'value': 'NOT ENFORCED', 'label': 'Not enforced'}],
                  visible_when=_when('f'),
                  help='ALTER CONSTRAINT ENFORCED / NOT ENFORCED for foreign keys.'),
            field('fillfactor', 'Fill factor', 'number',
                  visible_when=_when(['p', 'u', 'x']), help='10 to 100.'),
            field('reset_fillfactor', 'Reset fill factor to the default',
                  'boolean', visible_when=_when(['p', 'u', 'x'])),
            field('spcname', 'Tablespace', visible_when=_when(['p', 'u', 'x']),
                  help='Moves the backing index.'),
            field('comment', 'Comment', 'multiline',
                  initial_value_path=['constraint_facts', 'comment']),
        ]
        return {'form_id': 'postgresql-constraint-alter',
                'form_key': 'native:postgresql:schema:constraint',
                'title': 'Edit constraint', 'fields': fields,
                'notes': ('Columns, references and expressions cannot be '
                          'changed in place; drop and create instead.')}
    fields = [
        field('name', 'Name', help='Empty lets PostgreSQL name it.'),
        field('contype', 'Kind', 'select', options=kinds, required=True,
              default='p'),
        field('columns', 'Columns', help='Comma separated.',
              visible_when=_when(['p', 'u'])),
        field('without_overlaps_column', 'Temporal range column (WITHOUT OVERLAPS, PostgreSQL 18+)',
              help='Optional range/multirange column for temporal PRIMARY KEY / UNIQUE.',
              visible_when=_when(['p', 'u'])),
        field('index', 'Existing unique index', help=(
            'USING INDEX; replaces the column list.'),
            visible_when=_when(['p', 'u'])),
        field('not_null_column', 'Column (named NOT NULL, PostgreSQL 18+)',
              visible_when=_when('n')),
        field('fk_columns', 'Column pairs', 'grid', columns=[
            column('local_column', 'Local column', required=True),
            column('referenced', 'Referenced column', required=True)],
            visible_when=_when('f')),
        field('local_period_column', 'Local PERIOD range column (PostgreSQL 18+)',
              visible_when=_when('f')),
        field('referenced_period_column', 'Referenced PERIOD range column (PostgreSQL 18+)',
              visible_when=_when('f')),
        field('remote_schema', 'Referenced schema', visible_when=_when('f')),
        field('remote_table', 'Referenced table', visible_when=_when('f')),
        field('confmatchtype', 'Match full', 'boolean',
              visible_when=_when('f')),
        field('confupdtype', 'On update', 'select', options=[
            {'value': code, 'label': word.title()}
            for code, word in ACTIONS.items()], visible_when=_when('f')),
        field('confdeltype', 'On delete', 'select', options=[
            {'value': code, 'label': word.title()}
            for code, word in ACTIONS.items()], visible_when=_when('f')),
        field('consrc', 'Check expression', 'multiline',
              visible_when=_when('c')),
        field('connoinherit', 'No inherit', 'boolean',
              visible_when=_when(['c', 'n'])),
        field('enforcement', 'Enforcement (PostgreSQL 18+)', 'select',
              options=[{'value': 'ENFORCED', 'label': 'Enforced'},
                       {'value': 'NOT ENFORCED', 'label': 'Not enforced'}],
              visible_when=_when(['f', 'c'])),
        field('not_enforced', 'Do not enforce constraint (NOT ENFORCED, PostgreSQL 18+)',
              'boolean', visible_when=_when(['f', 'c'])),
        field('not_valid', "Don't validate existing rows (NOT VALID)",
              'boolean', visible_when=_when(['f', 'c'])),
        field('amname', 'Access method', visible_when=_when('x'),
              help='Empty uses the default (gist is usual).'),
        field('elements', 'Elements', 'grid', columns=[
            column('column', 'Column or expression', required=True),
            column('is_exp', 'Is expression', 'boolean'),
            column('oper_class', 'Operator class'),
            column('order', 'Ascending', 'boolean'),
            column('nulls_order', 'Nulls first', 'boolean'),
            column('operator', 'Operator', required=True)],
            visible_when=_when('x')),
        field('indconstraint', 'Predicate (WHERE)', visible_when=_when('x')),
        field('include', 'Include columns', help='Comma separated.',
              visible_when=_when(['p', 'u', 'x'])),
        field('fillfactor', 'Fill factor', 'number',
              visible_when=_when(['p', 'u', 'x'])),
        field('spcname', 'Index tablespace',
              visible_when=_when(['p', 'u', 'x'])),
        field('condeferrable', 'Deferrable', 'boolean',
              visible_when=_when(['p', 'u', 'f', 'x'])),
        field('condeferred', 'Initially deferred', 'boolean',
              visible_when=_when(['p', 'u', 'f', 'x'])),
        field('comment', 'Comment', 'multiline'),
    ]
    return {'form_id': 'postgresql-constraint-create',
            'form_key': 'native:postgresql:schema:constraint',
            'title': 'Create constraint', 'fields': fields}

"""PostgreSQL foreign tables on the provider tree (M7, 2026-11-11).

The table family form is the dialog (it gained the foreign server and the
option grids). Create compiles the ``CREATE FOREIGN TABLE`` the inherited
template rendered: columns, INHERITS, SERVER and OPTIONS, then owner,
check constraints, comment, column comments, grants and labels. Alter
emits one statement per changed fact: rename, schema, owner, options
added, set or dropped (the capture strips a foreign table's options, so
changes are stated through the three grids as for foreign servers),
comment, grants and revocations, labels. Drop is ``DROP FOREIGN TABLE``
with optional CASCADE and a typed name. Option names and values are
identifiers and literals; a credential-bearing option is refused as on
foreign servers.
"""
from __future__ import annotations

from . import tables as table_editor
from .foreign_objects import _option_changes, _option_pairs
from .native_admin import (
    PostgreSQLNativeAdminError, _flag, _identifier, _literal, _name,
    _qualified, _reference,
)
from .policies import expression


def _refuse(message):
    raise PostgreSQLNativeAdminError(message)


def _blank(value):
    return value is None or value == ''


def facts(native, servers=None):
    """Table facts plus the foreign server, named through the captured
    foreign servers (``servers`` maps OID to name)."""
    current = table_editor.facts(native)
    child = ((native.get('children') or {}).get('pg_foreign_table') or
             [{}])[0]
    server_oid = child.get('ftserver')
    if isinstance(server_oid, str) and server_oid.isdigit():
        server_oid = int(server_oid)
    current['ftsrvname'] = (servers or {}).get(server_oid)
    return current


def _qualified_table(current):
    return _qualified(_name(current['schema'], 'schema'),
                      _name(current['name'], 'name'))


def _create(draft):
    schema = _name(draft.get('schema') or draft.get('basensp'), 'schema')
    name = _name(draft.get('name'), 'name')
    qualified = _qualified(schema, name)
    if _blank(draft.get('ftsrvname')):
        _refuse('a foreign table needs a foreign server')
    columns = []
    for row in table_editor._rows(draft, 'columns'):
        if _blank(row.get('name')):
            continue
        if row.get('colconstype') == 'i':
            _refuse('a foreign table column cannot be an identity column')
        clause = table_editor._column_clause(row)
        options = table_editor._rows(row, 'coloptions')
        if options:
            clause += ' OPTIONS (' + ', '.join(_option_pairs(options)) + ')'
        columns.append(clause)
    statement = (f'CREATE FOREIGN TABLE {qualified} ('
                 + ', '.join(columns) + ')')
    parents = draft.get('inherits') or draft.get('coll_inherits')
    if not _blank(parents):
        if isinstance(parents, str):
            parents = [part.strip() for part in parents.split(',')
                       if part.strip()]
        statement += ' INHERITS (' + ', '.join(
            _reference(parent, 'inherits') for parent in parents) + ')'
    statement += ' SERVER ' + _identifier(_name(draft['ftsrvname'],
                                                'ftsrvname'), 'ftsrvname')
    options = table_editor._rows(draft, 'ftoptions')
    if options:
        statement += ' OPTIONS (' + ', '.join(_option_pairs(options)) + ')'
    statements = [statement]
    owner = draft.get('relowner') or draft.get('owner')
    if not _blank(owner):
        statements.append(f'ALTER FOREIGN TABLE {qualified} OWNER TO '
                          + _identifier(_name(owner, 'owner'), 'owner'))
    for row in table_editor._rows(draft, 'check_constraint'):
        clause = (f'ALTER FOREIGN TABLE {qualified} ADD')
        if not _blank(row.get('name')):
            clause += ' CONSTRAINT ' + _identifier(_name(row['name'], 'name'),
                                                   'name')
        clause += ' CHECK (' + expression(row.get('consrc'), 'consrc') + ')'
        if 'convalidated' in row and not _flag(row, 'convalidated'):
            clause += ' NOT VALID'
        if _flag(row, 'connoinherit') if 'connoinherit' in row else False:
            clause += ' NO INHERIT'
        statements.append(clause)
    if not _blank(draft.get('description')):
        statements.append(f'COMMENT ON FOREIGN TABLE {qualified} IS '
                          + _literal(str(draft['description']), 'comment'))
    for row in table_editor._rows(draft, 'columns'):
        if not _blank(row.get('name')) and not _blank(row.get('description')):
            statements.append(
                f'COMMENT ON COLUMN {qualified}.'
                f'{_identifier(_name(row["name"], "name"), "name")} IS '
                + _literal(str(row['description']), 'comment'))
    for row in table_editor._rows(draft, 'relacl'):
        statements.append(table_editor._grant(qualified, row))
    for row in table_editor._rows(draft, 'seclabels'):
        statements.append(table_editor._label(qualified, row).replace(
            ' ON TABLE ', ' ON FOREIGN TABLE ', 1))
    return statements


def _alter(native, draft):
    current = facts(native)
    schema = _name(current['schema'], 'schema')
    name = _name(current['name'], 'name')
    qualified = _qualified(schema, name)
    statements = []
    if not _blank(draft.get('name')) and draft['name'] != current['name']:
        name = _name(draft['name'], 'name')
        statements.append(f'ALTER FOREIGN TABLE {qualified} RENAME TO '
                          + _identifier(name, 'name'))
        qualified = _qualified(schema, name)
    if not _blank(draft.get('schema')) and \
            draft['schema'] != current['schema']:
        schema = _name(draft['schema'], 'schema')
        statements.append(f'ALTER FOREIGN TABLE {qualified} SET SCHEMA '
                          + _identifier(schema, 'schema'))
        qualified = _qualified(schema, name)
    owner = draft.get('relowner') or draft.get('owner')
    if not _blank(owner) and owner != current['relowner']:
        statements.append(f'ALTER FOREIGN TABLE {qualified} OWNER TO '
                          + _identifier(_name(owner, 'owner'), 'owner'))
    options = _option_changes(draft)
    if options:
        statements.append(f'ALTER FOREIGN TABLE {qualified}{options}')
    for row in table_editor._rows(draft, 'seclabels'):
        statements.append(table_editor._label(qualified, row).replace(
            ' ON TABLE ', ' ON FOREIGN TABLE ', 1))
    for row in table_editor._rows(draft, 'relacl'):
        statements.append(table_editor._grant(qualified, row))
    for row in table_editor._rows(draft, 'revoke'):
        statements.append(f'REVOKE ALL ON TABLE {qualified} FROM '
                          + table_editor._grantee(row.get('grantee')))
    if 'description' in draft and (draft.get('description') or '') != \
            current['description']:
        value = draft.get('description') or ''
        statements.append(f'COMMENT ON FOREIGN TABLE {qualified} IS '
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
    return [f'DROP FOREIGN TABLE {_qualified_table(current)}{cascade}']


def compile_operation(operation, native, draft):
    """One exact native text for the foreign table lifecycle."""
    if operation == 'create':
        statements = _create(draft)
    elif operation == 'alter':
        statements = _alter(native, draft)
    elif operation == 'drop':
        statements = _drop(native, draft)
    else:
        _refuse('foreign table inspection stays with the provider tree')
    return {'statement': ';\n'.join(statements), 'read_only': False}


def form(operation, field):
    """The validator's view: the table family form's fields (which carry
    the foreign server and option grids) typed loosely."""
    base = table_editor.form(operation, field)
    if operation == 'drop':
        base['form_id'] = 'postgresql-foreign-table-drop'
        base['title'] = 'Drop foreign table'
        base['form_key'] = 'native:postgresql:schema:foreign-table'
        return base
    present = {item['field_id'] for item in base['fields']}
    for field_id, label, control in (
            ('ftsrvname', 'Foreign server', 'text'),
            ('ftoptions', 'Foreign table options', 'grid'),
            ('add_options', 'Add options', 'grid'),
            ('set_options', 'Set options', 'grid'),
            ('drop_options', 'Drop options', 'grid'),
            ('inherits', 'Inherits', 'text'), ('basensp', 'Schema', 'text'),
            ('owner', 'Owner', 'text')):
        if field_id not in present:
            base['fields'].append(field(field_id, label, control,
                                        **({'columns': []}
                                           if control == 'grid' else {})))
    base['form_id'] = f'postgresql-foreign-table-{operation}'
    base['form_key'] = 'native:postgresql:schema:foreign-table'
    base['title'] = ('Edit' if operation == 'alter' else 'Create') + \
        ' foreign table'
    base['notes'] = ('Foreign table options are not read back by the '
                     'capture; state changes through the add, set and drop '
                     'grids. Check constraints on an existing foreign table '
                     'are edited on their own nodes.')
    return base

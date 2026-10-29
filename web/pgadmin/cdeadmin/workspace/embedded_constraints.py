"""Opt-in, rebuild-backed constraint additions for SQLite and DuckDB tables from the diagram.

SQLite and DuckDB cannot add UNIQUE, CHECK or FOREIGN KEY constraints to an existing table
in place. Their native plans do it by rebuilding the table (new table, copy every row, swap),
which rewrites data. The diagram therefore only requests it when the reviewer opts in
(``allow_rebuilds``); without the opt-in these drafts are refused with that reason.

The desired facts are never hand-built. The new CREATE TABLE text is derived from the native
one by inserting the drafted clauses, executed on a throwaway in-memory database (DuckDB with
external access disabled), and the facts the plan checks are read back from that copy:

* SQLite: the table record keeps its baseline facts with the new ``ddl``; the new constraint
  records come from the copy. The review returns ``rebuilds`` (the table identity) for the
  existing rebuild plan.
* DuckDB: the table record gets the new ``ddl`` and ``constraints`` list plus the reviewed
  ``duckdb_change`` rebuild action (one constraint kind per review); the new constraint
  records come from the copy.

Only additions are carried. Dropping or replacing a constraint, adding to a table whose
existing constraints would be renumbered (which would defeat post-apply rediscovery), and
mixed kinds in one review are refused with a reason. Nothing executes against the database.
See docs/en_US/ddn_physical_schema_vocabulary.rst.
"""
from copy import deepcopy
import re

from . import physical_schema as vocab

KINDS = ('unique', 'check', 'foreign-key')
_DUCKDB_ACTIONS = {'unique': 'rebuild-unique-constraints', 'check': 'rebuild-check-constraints',
                   'foreign-key': 'rebuild-foreign-keys'}
_DUCKDB_TYPES = {'unique': 'UNIQUE', 'check': 'CHECK', 'foreign-key': 'FOREIGN KEY'}
_ALLOWED = {'physical_kind', 'physical_name', 'columns_json', 'columns', 'expression',
            'referenced_columns_json', 'referenced_columns', 'on_delete', 'on_update'}


def _quote(name):
    if not isinstance(name, str) or not name or '\x00' in name:
        raise ValueError('Invalid schema identifier')
    return '"' + name.replace('"', '""') + '"'


def is_constraint_draft(draft):
    return (draft.get('physical') or {}).get('physical_kind') in KINDS


def _closing_paren(ddl):
    """Index of the ')' that closes the first '(' of a CREATE TABLE statement."""
    depth, index, length = 0, 0, len(ddl)
    while index < length:
        char = ddl[index]
        if char in '\'"`':
            end = index + 1
            while end < length:
                if ddl[end] == char:
                    if end + 1 < length and ddl[end + 1] == char:
                        end += 2
                        continue
                    break
                end += 1
            index = end
        elif char == '[':
            index = ddl.find(']', index)
            if index < 0:
                break
        elif ddl.startswith('--', index):
            index = ddl.find('\n', index)
            if index < 0:
                break
        elif ddl.startswith('/*', index):
            index = ddl.find('*/', index)
            if index < 0:
                break
            index += 1
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise ValueError('The native table definition could not be read to add a constraint')


def _clause(engine, draft, table, current):
    values = vocab.normalize(draft['physical'], 'physical draft')
    if {'drop', 'rename_from', 'drop_confirmation'} & values.keys():
        raise ValueError('A new physical object cannot carry drop or rename intent')
    if set(values) - _ALLOWED:
        raise ValueError('A constraint draft carries only its kind, name, columns and definition')
    kind = values['physical_kind']
    names = [column['name'] for column in table['native'].get('columns', [])]
    name = values.get('physical_name')
    prefix = 'CONSTRAINT ' + _quote(name) + ' ' if name and engine == 'sqlite' else ''
    if kind == 'check':
        expression = values.get('expression')
        if not isinstance(expression, str) or not expression.strip() or len(expression) > 4096:
            raise ValueError('A check constraint needs its expression')
        if ';' in expression or '--' in expression or '/*' in expression:
            raise ValueError('A check expression must be one native expression')
        return kind, prefix + 'CHECK (' + expression.strip() + ')', None
    columns = values.get('columns')
    if not columns or any(column not in names for column in columns):
        raise ValueError('Constraint columns must be existing columns of the table')
    cols = ', '.join(_quote(column) for column in columns)
    if kind == 'unique':
        return kind, prefix + 'UNIQUE (' + cols + ')', None
    reference = values.get('referenced_columns')
    target = current['rows'].get((draft.get('endpoints') or {}).get('target') or '')
    if (not reference or len(reference) != len(columns) or target is None or target['kind'] != 'table' or
            target.get('system') != 'false' or target['path'][:-1] != table['path'][:-1]):
        raise ValueError('A foreign key needs matching referenced columns and a user table in the same schema as its target')
    clause = prefix + 'FOREIGN KEY (' + cols + ') REFERENCES ' + _quote(target['name']) + ' (' + \
        ', '.join(_quote(column) for column in reference) + ')'
    for key, word in (('on_delete', 'ON DELETE'), ('on_update', 'ON UPDATE')):
        if key in values and values[key] != 'NO ACTION':
            clause += ' ' + word + ' ' + values[key]
    return kind, clause, target


def _qualify(ddl, path):
    """DuckDB plans need the exact fully qualified CREATE target."""
    match = re.match(r'\s*CREATE\s+TABLE\s+', ddl, re.I)
    if match is None:
        raise ValueError('The native table definition is not a plain CREATE TABLE; edit it natively')
    start = match.end()
    quote, end = None, start
    while end < len(ddl) and (quote or ddl[end] != '('):
        if ddl[end] in '"\'':
            quote = None if quote == ddl[end] else (quote or ddl[end])
        end += 1
    if end >= len(ddl) or quote:
        raise ValueError('The native table definition could not be read to add a constraint')
    return 'CREATE TABLE ' + '.'.join(_quote(part) for part in path) + ' ' + ddl[end:]


def _new_ddl(ddl, clauses):
    text = ddl.rstrip()
    suffix = ';' if text.endswith(';') else ''
    text = text[:-1].rstrip() if suffix else text
    close = _closing_paren(text)
    return text[:close].rstrip() + ', ' + ', '.join(clauses) + text[close:] + suffix


def _children(rows, table_id, kind='constraint'):
    return {identity: row for identity, row in rows.items() if row['kind'] == kind and
            row['native'].get('navigator_parent_resource_id') == table_id}


def _item(row, owner):
    return {'resource_id': row['resource_id'], 'kind': 'constraint', 'name': row['name'], 'path': row['path'],
            'system': 'false', 'native': row['native'], 'owner': owner}


def _sqlite(table, ddl, old_rows, wanted):
    import sqlite3
    from ..providers.sqlite.provider import _resources
    from .firebird_catalog_export import build_export
    if not sqlite3.complete_statement(ddl if ddl.rstrip().endswith(';') else ddl + ';'):
        raise ValueError('The drafted table must be one native statement')
    scratch = sqlite3.connect(':memory:')
    try:
        scratch.execute(ddl)
        resources = _resources(scratch, {})
    except sqlite3.Error as error:
        raise ValueError('SQLite rejected the drafted constraint: ' + str(error)[:200]) from None
    finally:
        scratch.close()
    model = build_export(resources, endpoint_id='scratch', target_id='scratch', generation='scratch',
                         engine='sqlite', native_model=True, include_system=False)
    fresh = model['rows'].get(table['resource_id'])
    if fresh is None or fresh['native'].get('columns') != table['native'].get('columns'):
        raise ValueError('Adding the constraint would change the table columns; edit it natively')
    after = _children(model['rows'], table['resource_id'])
    before = _children(old_rows, table['resource_id'])
    if set(before) - set(after) or any(after[key]['native'] != row['native'] for key, row in before.items()):
        raise ValueError('Adding the constraint would renumber an existing constraint; edit the table natively')
    created = [row for key, row in after.items() if key not in before]
    if len(created) != wanted:
        raise ValueError('SQLite reported an unexpected set of new constraints')
    return created


def _duckdb(table, ddl, kind, old_rows, current, extra_tables, wanted):
    import duckdb
    from ..providers.duckdb.catalog import capture
    from .firebird_catalog_export import build_export
    root, schema = table['path'][0], table['path'][1]
    resources = None
    # The first pass runs with external access off, so a drafted expression cannot touch files or the network; the
    # second pass (same statements) is read back, because catalog capture needs the extension directory.
    for hardened in (True, False):
        scratch = duckdb.connect(':memory:', config={'enable_external_access': False} if hardened else {})
        try:
            scratch.execute('ATTACH \':memory:\' AS ' + _quote(root))
            scratch.execute('USE ' + _quote(root))
            if schema != 'main':
                scratch.execute('CREATE SCHEMA ' + _quote(schema))
            scratch.execute('USE ' + _quote(root) + '.' + _quote(schema))
            for other in extra_tables:
                if any(item.get('constraint_type') == 'FOREIGN KEY' for item in other['native'].get('constraints', [])):
                    raise ValueError('A referenced table with its own foreign keys is not carried; edit natively')
                scratch.execute(other['native']['ddl'])
            scratch.execute(ddl)
            if not hardened:
                resources = capture(scratch)['resources']
        except duckdb.Error as error:
            raise ValueError('DuckDB rejected the drafted constraint: ' + str(error)[:200]) from None
        finally:
            scratch.close()
    model = build_export(resources, endpoint_id='scratch', target_id='scratch', generation='scratch',
                         engine='duckdb', native_model=True)
    fresh = model['rows'].get(table['resource_id'])
    if fresh is None:
        raise ValueError('DuckDB reported no drafted table')
    strip = lambda columns: [{key: value for key, value in column.items() if key != 'owner_oid'} for column in columns]
    if strip(fresh['native'].get('columns', [])) != strip(table['native'].get('columns', [])):
        raise ValueError('Adding the constraint would change the table columns; edit it natively')
    changing = _DUCKDB_TYPES[kind]
    retained = lambda items: [item for item in items if item.get('constraint_type') != changing]
    if retained(fresh['native'].get('constraints', [])) != retained(table['native'].get('constraints', [])):
        raise ValueError('Adding the constraint would renumber the existing constraints, so the change could not be '
                         'verified after the rebuild; edit the table natively')
    existing = {item['resource_id'] for item in table['native'].get('constraints', [])}
    created = [row for key, row in _children(model['rows'], table['resource_id']).items() if key not in existing]
    if len(created) != wanted:
        raise ValueError('DuckDB reported an unexpected set of new constraints')
    return fresh['native'].get('constraints', []), created


def add(engine, old, table, current, drafts, native, allow_rebuilds):
    """(desired table native, new constraint items, rebuild identity) for constraint drafts."""
    if not allow_rebuilds:
        raise ValueError('Adding a constraint rebuilds the table and rewrites its rows; enable rebuild-backed constraint '
                         'additions to review it')
    if table['native'].get('catalog_metadata', {}).get('table_list_type', 'table') not in ('table', None):
        raise ValueError('Constraint additions are carried for ordinary tables only')
    ddl = old['native'].get('ddl')
    if not isinstance(ddl, str) or not ddl or len(ddl.encode('utf8')) > 1024 * 1024:
        raise ValueError('The table has no bounded native definition to extend')
    built = [_clause(engine, draft, table, current) for draft in drafts]
    kinds = {kind for kind, _, _ in built}
    if engine == 'duckdb' and len(kinds) != 1:
        raise ValueError('DuckDB rebuilds add one constraint kind per review')
    for draft in drafts:
        vocab.draft_identity(engine, old['uid'], draft['uid'])
    new_ddl = _new_ddl(_qualify(ddl, table['path']) if engine == 'duckdb' else ddl, [clause for _, clause, _ in built])
    wanted = sum(1 for kind, _, _ in built if kind != 'check') if engine == 'sqlite' else len(built)
    result = deepcopy(native)
    if engine == 'sqlite':
        created = _sqlite(table, new_ddl, current['rows'], wanted)
        result['ddl'] = new_ddl
        return result, [_item(row, table['resource_id']) for row in created], table['resource_id']
    kind = next(iter(kinds))
    references = {item[2]['resource_id']: item[2] for item in built if item[2] is not None}
    for item in table['native'].get('constraints', []):
        if item.get('constraint_type') == 'FOREIGN KEY':
            other = next((row for row in current['rows'].values() if row['kind'] == 'table' and
                          row['name'] == item.get('referenced_table') and row['path'][:-1] == table['path'][:-1]), None)
            if other is None:
                raise ValueError('An existing foreign key target is unavailable')
            references[other['resource_id']] = other
    references.pop(table['resource_id'], None)
    constraints, created = _duckdb(table, new_ddl, kind, current['rows'], current, list(references.values()), wanted)
    result['ddl'] = new_ddl
    result['constraints'] = constraints
    result['duckdb_change'] = {'action': _DUCKDB_ACTIONS[kind], 'complete_definition_confirmed': True,
                               'preserve_rows_confirmed': True}
    return result, [_item(row, table['resource_id']) for row in created], None

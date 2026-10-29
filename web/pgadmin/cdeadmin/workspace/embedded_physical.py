"""SQLite and DuckDB physical edits from the diagram (physical-schema vocabulary).

Carried: indexes (below), explicit table and column renames (physical_name + rename_from on the
table record or the field record; the baseline name is read from the live catalog) and, for
DuckDB, adding a primary key to a table that has none. SQLite renames leave the desired model
equal to the baseline and are returned as native ``renames`` arguments for the existing rename
design/plan flow; DuckDB renames become the reviewed ``duckdb_change`` rename intent.

Not carried: other constraint kinds (SQLite and DuckDB change them only through table
rebuilds that rewrite data), index renames, SQLite drops and table/column drops; each fails
with a reason (see docs/en_US/ddn_physical_schema_vocabulary.rst).

SQLite: an existing index may be replaced (same name, new columns/uniqueness/predicate) and
new indexes may be drafted. DuckDB: an existing index may be dropped with its exact name and
new indexes may be drafted; DuckDB has no replace plan, so a replacement is a drop plus a
new index under a new name. Nothing executes here.
"""
from copy import deepcopy
import json
import re
from . import physical_schema as vocab

IDENT = re.compile(r'[A-Za-z_][A-Za-z0-9_$]*')


def _quote(name):
    if not isinstance(name, str) or not name or '\x00' in name:
        raise ValueError('Invalid schema identifier')
    return '"' + name.replace('"', '""') + '"'


def _native(row, engine):
    from .firebird_catalog_export import native_metadata
    return native_metadata(row, engine)


def _sqlite_values(row):
    native = _native(row, 'sqlite')
    meta = native.get('catalog_metadata', {})
    if native.get('system_object') is not False or meta.get('origin') != 'c' or not native.get('ddl'):
        return None
    values = {'physical_kind': 'index', 'physical_name': row['display_name'], 'unique': bool(meta.get('unique'))}
    keys = [key for key in meta.get('keys', []) if key.get('is_key')]
    simple = bool(keys) and all(key.get('name') and not key.get('descending') and key.get('collation') == 'BINARY'
                                for key in keys)
    if simple:
        values['columns_json'] = vocab.encode([key['name'] for key in keys])
    if meta.get('partial'):
        match = re.search(r'\sWHERE\s(.*?);?\s*$', native['ddl'], re.I | re.S)
        if match:
            values['predicate'] = match.group(1)
        else:
            simple = False
    return {'values': values, 'replaceable': simple}


def _duckdb_values(row):
    native = _native(row, 'duckdb')
    meta = native.get('catalog_metadata', {})
    if native.get('system_object') is not False or meta.get('primary') or not native.get('ddl'):
        return None
    values = {'physical_kind': 'index', 'physical_name': row['display_name'], 'unique': bool(meta.get('unique'))}
    expressions = meta.get('expressions')
    match = re.fullmatch(r'\[(.*)\]', expressions or '', re.S)
    names = [part.strip() for part in match.group(1).split(',')] if match and match.group(1) else []
    if names and all(IDENT.fullmatch(name) for name in names):
        values['columns_json'] = vocab.encode(names)
    return {'values': values, 'replaceable': False}


def forward(engine, resources):
    """{table resource id: [{'row', 'values', 'role'}]} for user indexes."""
    extract = _sqlite_values if engine == 'sqlite' else _duckdb_values
    grouped = {}
    for row in resources:
        if row['resource_kind'] != 'index':
            continue
        found = extract(row)
        parent = _native(row, engine).get('navigator_parent_resource_id')
        if found is not None and parent:
            grouped.setdefault(parent, []).append({'row': row, 'values': found['values'], 'role': 'index'})
    return grouped


# --------------------------------------------------------------------------- merge

def _scratch_sqlite(table, name, columns, unique, predicate):
    """The exact catalog row SQLite reports for the drafted index, built on a throwaway copy."""
    import sqlite3
    from ..providers.sqlite.provider import _resources
    statement = ('CREATE ' + ('UNIQUE ' if unique else '') + 'INDEX ' + _quote(name) + ' ON ' + _quote(table['name']) +
                 ' (' + ', '.join(_quote(column) for column in columns) + ')' +
                 (' WHERE ' + predicate if predicate else ''))
    if not sqlite3.complete_statement(statement + ';') or ';' in statement:
        raise ValueError('The drafted index must be one native statement')
    scratch = sqlite3.connect(':memory:')
    try:
        scratch.execute(table['native']['ddl'])
        scratch.execute(statement)
        rows = [row for row in _resources(scratch, {}) if row['resource_kind'] == 'index' and row['display_name'] == name]
    except sqlite3.Error as error:
        raise ValueError('SQLite rejected the drafted index: ' + str(error)[:200]) from None
    finally:
        scratch.close()
    if len(rows) != 1:
        raise ValueError('SQLite reported no unique drafted index')
    native = _native(rows[0], 'sqlite')
    if native.get('catalog_metadata', {}).get('without_rowid'):
        raise ValueError('Indexes on WITHOUT ROWID tables are not admitted from the diagram')
    return native


def _table_columns(table):
    return [column['name'] for column in table['native'].get('columns', [])]


def _definition(values, old=None):
    merged = {**(old or {}), **values}
    return {'columns': merged.get('columns'), 'unique': bool(merged.get('unique', False)),
            'predicate': merged.get('predicate')}


def _primary_key(engine, table, drafts, old):
    """DuckDB: ADD PRIMARY KEY from one primary-key draft on a table without a key."""
    wanted = [draft for draft in drafts if (draft.get('physical') or {}).get('physical_kind') == 'primary-key']
    if not wanted:
        return None
    if engine != 'duckdb':
        raise ValueError('Primary-key drafts are admitted for DuckDB only; SQLite changes keys through a table rebuild')
    if len(wanted) != 1:
        raise ValueError('Add one primary key at a time')
    draft = wanted[0]
    values = vocab.normalize(draft['physical'], 'physical draft')
    if {'drop', 'rename_from', 'drop_confirmation'} & values.keys():
        raise ValueError('A new physical object cannot carry drop or rename intent')
    if set(values) - {'physical_kind', 'physical_name', 'columns_json', 'columns'}:
        raise ValueError('A primary-key draft carries only its columns')
    vocab.draft_identity(engine, old['uid'], draft['uid'])
    if table['native'].get('catalog_metadata', {}).get('has_primary_key') is not False:
        raise ValueError('Primary-key addition requires a table without a key')
    columns = values.get('columns')
    if not columns or any(column not in _table_columns(table) for column in columns):
        raise ValueError('Primary-key columns must be existing columns of the table')
    return wanted[0], columns


def _name_change(before_name, values, label):
    """(old, new) for an explicit rename; vocabulary other than a rename is refused."""
    after = vocab.normalize(values or {}, label + ' physical vocabulary')
    if {'drop', 'drop_confirmation'} & after.keys():
        raise ValueError(label.capitalize() + ' drops are not carried for this engine')
    if set(after) - {'physical_name', 'rename_from'}:
        raise ValueError('Only an explicit rename is carried for a ' + label + ' on this engine')
    return vocab.rename({'physical_name': before_name}, after, label)


def _draft_row(engine, table, draft, uid_parent):
    from .firebird_catalog_import import _equal  # noqa: F401
    values = vocab.normalize(draft['physical'], 'physical draft')
    if values.get('physical_kind') != 'index' or 'physical_name' not in values:
        raise ValueError('Only index drafts are admitted for this engine')
    if {'drop', 'rename_from', 'drop_confirmation'} & values.keys():
        raise ValueError('A new physical object cannot carry drop or rename intent')
    vocab.draft_identity(engine, uid_parent, draft['uid'])
    name, columns = values['physical_name'], values.get('columns')
    if not columns or any(column not in _table_columns(table) for column in columns):
        raise ValueError('Index columns must be existing columns of the table')
    path = [*table['path'], name]
    if engine == 'sqlite':
        if path[0] != 'main':
            raise ValueError('Indexes are admitted on the main registered file only')
        from ..providers.sqlite.provider import _resource_id
        native = _scratch_sqlite(table, name, columns, bool(values.get('unique')), values.get('predicate'))
    else:
        if values.get('predicate'):
            raise ValueError('DuckDB has no partial indexes')
        from ..providers.duckdb.provider import _resource_id
        ddl = ('CREATE ' + ('UNIQUE ' if values.get('unique') else '') + 'INDEX ' + _quote(name) + ' ON ' +
               '.'.join(_quote(part) for part in table['path']) + ' (' + ', '.join(_quote(column) for column in columns) + ');')
        native = {'catalog_metadata': {'comment': None, 'tags': {}, 'unique': bool(values.get('unique')),
                                       'primary': False, 'expressions': '[' + ', '.join(columns) + ']'},
                  'ddl': ddl, 'navigator_parent_resource_id': table['resource_id'], 'system_object': False}
    identity = _resource_id('index', path[:-1], name)
    return {'resource_id': identity, 'kind': 'index', 'name': name, 'path': path, 'system': 'false',
            'native': native, 'owner': table['resource_id']}


def _resource_id(engine, kind, parent_path, name):
    if engine == 'sqlite':
        from ..providers.sqlite.provider import _resource_id
    else:
        from ..providers.duckdb.provider import _resource_id
    return _resource_id(kind, parent_path, name)


def _renames(engine, old, row, live, current):
    """Explicit table/column renames on this relation: [{'identity', 'kind', 'old', 'new', 'native'}]."""
    found = []
    if live['kind'] == 'table' or (engine == 'duckdb' and live['kind'] == 'view'):
        change = _name_change(live['name'], row.get('physical') or {}, 'table' if live['kind'] == 'table' else 'view')
        if change:
            found.append({'identity': live['resource_id'], 'kind': live['kind'], 'old': change[0], 'new': change[1],
                          'table': live['name']})
    prefix = old['uid'][:-len(old['resource_id'])]
    for uid, field in row.get('fields', {}).items():
        values = field.get('_physical') or {}
        if not values:
            continue
        if live['kind'] != 'table':
            raise ValueError('Column renames are carried for tables only')
        column = current['rows'].get(uid[len(prefix):]) if uid.startswith(prefix) else None
        if column is None or column['kind'] != 'column' or column['path'][:-1] != live['path']:
            raise ValueError('The field does not name a native column of this table')
        change = _name_change(column['name'], values, 'column')
        if change:
            found.append({'identity': column['resource_id'], 'kind': 'column', 'old': change[0], 'new': change[1],
                          'table': live['name']})
    if len({(item['kind'], item['new']) for item in found}) != len(found):
        raise ValueError('Rename targets must be distinct')
    return found


def merge(engine, old, row, live, current, drafts, allow_rebuilds=False):
    """Returns (desired native facts, new catalog rows, renames, rebuilds) for one relational row.

    renames: explicit table/column renames (see _renames). For DuckDB the caller rewrites the
    renamed catalog records; for SQLite they are returned as native rename arguments.
    rebuilds: SQLite table identities whose reviewed desired DDL needs the native rebuild plan
    (opt-in constraint additions, see embedded_constraints)."""
    native, created = deepcopy(row['native']), []
    before, after = old.get('physical') or {}, row.get('physical') or {}
    renames = []
    if live['kind'] in {'table', 'view'}:
        renames = _renames(engine, old, row, live, current)
        if engine == 'sqlite' and any(item['kind'] == 'view' for item in renames):
            raise ValueError('SQLite view renames are not carried')
        if renames and drafts:
            raise ValueError('Review renames separately from new physical objects')
    elif any((item.get('_physical') for item in row.get('fields', {}).values())):
        raise ValueError('Column renames and drops are not carried from the diagram for this engine')
    if live['kind'] == 'table':
        from . import embedded_constraints
        constraints = [draft for draft in drafts if embedded_constraints.is_constraint_draft(draft)]
        if constraints:
            drafts = [draft for draft in drafts if draft not in constraints]
            if renames or drafts:
                raise ValueError('Review constraint additions separately from other edits to the table')
            native, created, rebuild = embedded_constraints.add(engine, old, live, current, constraints, native, allow_rebuilds)
            return native, created, renames, [rebuild] if rebuild else []
        key = _primary_key(engine, live, drafts, old)
        if key is not None:
            native['duckdb_change'] = {'action': 'add-primary-key', 'columns': key[1]}
            drafts = [draft for draft in drafts if draft is not key[0]]
        if drafts and renames:
            raise ValueError('Review renames separately from new physical objects')
        for draft in drafts:
            created.append(_draft_row(engine, live, draft, old['uid']))
        if key is not None and (created or renames):
            raise ValueError('Review a primary-key addition separately from other edits to the table')
        return native, created, renames, []
    if live['kind'] == 'view' and engine == 'duckdb' and renames:
        return native, created, renames, []
    if drafts:
        raise ValueError('Drafts must belong to a table')
    if live['kind'] != 'index' or not after:
        return native, created, renames, []
    if not before:
        raise ValueError('The baseline diagram carries no physical-schema vocabulary for this index; regenerate it')
    name = live['name']
    changed = vocab.changes(before, after)
    if vocab.rename(before, after, 'index'):
        raise ValueError('Renaming an index is not carried for this engine; drop it and add a new one')
    if engine == 'duckdb':
        if vocab.drop(before, after, name, 'index'):
            native['duckdb_change'] = {'action': 'drop', 'confirmation': name}
            return native, created, renames, []
        if changed:
            raise ValueError('DuckDB has no index replacement plan; drop it (with drop_confirmation) and add a new index under a new name')
        return native, created, renames, []
    if 'drop' in after and after['drop']:
        raise ValueError('SQLite index deletion needs row absence plus a deletion argument; it is not carried from the diagram')
    if not changed:
        return native, created, renames, []
    found = _sqlite_values({'resource_kind': 'index', 'display_name': name, 'native': old['native']})
    if found is None or not found['replaceable']:
        raise ValueError('This index has native properties (expressions, ordering, collations) outside the vocabulary; edit it natively')
    wanted = _definition(vocab.normalize({**before, **after}), None)
    tables = [item for item in current['rows'].values() if item['kind'] == 'table' and item['path'] == live['path'][:2]]
    if len(tables) != 1:
        raise ValueError('The owning table is unavailable')
    columns = wanted['columns']
    if not columns or any(column not in _table_columns(tables[0]) for column in columns):
        raise ValueError('Index columns must be existing columns of the table')
    scratch = _scratch_sqlite(tables[0], name, columns, wanted['unique'], wanted['predicate'])
    scratch['navigator_parent_resource_id'] = native.get('navigator_parent_resource_id')
    return {**native, 'ddl': scratch['ddl'], 'catalog_metadata': scratch['catalog_metadata']}, created, renames, []

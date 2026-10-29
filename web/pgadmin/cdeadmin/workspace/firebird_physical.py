"""Firebird physical-schema edits from the diagram: indexes, PRIMARY KEY / UNIQUE /
CHECK / FOREIGN KEY constraints (with ON DELETE / ON UPDATE actions), the index
ACTIVE/INACTIVE state, explicit drops and the one rename the engine has.

Stages, mirroring postgresql_physical.py but expressed through the existing Firebird
planner instead of a second one:

  * extract() / forward(): native catalog facts -> vocabulary (forward ERD, tests)
  * merge_row() / new_objects(): edited vocabulary -> explicit native intents in the
    desired catalog document (ordinary native properties, the ``lifecycle`` instruction
    for drop, rename and index replacement, and new catalog rows for drafts)
  * the reviewed plan itself is built by firebird_schema_plan / firebird_lifecycle_plan

Nothing here executes SQL. Missing diagram objects are never deletion intent, a changed
name is only a rename with an explicit rename_from mapping, and drops need the exact name.

Firebird 5.0 (ODS 13.x) has ALTER TABLE ... ALTER COLUMN ... TO (and ALTER DOMAIN ... TO)
but no rename for tables, views, indexes or constraints. Those requests are refused with
NotCarried and the reason, never emulated by drop and re-create (which would lose data
or silently change dependent objects).
"""
from copy import deepcopy
import re

from . import physical_schema as vocab
from .firebird_catalog_import import _equal
from ..providers.firebird.character_metadata import identifier
from ..providers.firebird.identity import catalog_resource_id

KEY_KINDS = {'PRIMARY KEY': 'primary-key', 'UNIQUE': 'unique', 'CHECK': 'check', 'FOREIGN KEY': 'foreign-key'}
NATIVE_TYPES = {value: key for key, value in KEY_KINDS.items()}
RULES = {'NO ACTION': 'RESTRICT'}  # Firebird records NO ACTION as RESTRICT.
INDEX_CONTENT = ('unique', 'descending', 'columns', 'expression', 'predicate')
NOT_CARRIED = {
    'table': 'Firebird 5.0 has no ALTER TABLE ... RENAME TO. A copy-and-drop would lose dependent objects, '
             'grants and triggers, so a table is not renamed from the diagram',
    'view': 'Firebird 5.0 has no ALTER VIEW ... RENAME TO; recreate the view natively',
    'index': 'Firebird 5.0 has no ALTER INDEX ... RENAME TO; drop the index with drop and drop_confirmation '
             'and add a new one under the wanted name in two reviewed changes',
    'constraint': 'Firebird 5.0 has no ALTER TABLE ... RENAME CONSTRAINT; replace the constraint under a new name '
                  'natively in two reviewed changes',
}


class NotCarried(ValueError):
    """A diagram edit the engine cannot express; always carries the reason."""

    def __init__(self, reason):
        super().__init__('Not carried to Firebird: ' + reason)


def _is(value):
    return value is True or str(value) == '1'


def _names(segments):
    if not isinstance(segments, list):
        return []
    return [item['field_name'] for item in sorted(segments, key=lambda item: int(item['position']))]


def resource_map(resources):
    from .firebird_catalog_export import native_metadata
    return {row['resource_id']: {'kind': row['resource_kind'], 'native': native_metadata(row),
                                 'path': list(row.get('display_path') or [row['display_name']])}
            for row in resources}


def constraint_backed(row, rows):
    """True for an index that merely implements a PRIMARY KEY, UNIQUE or FOREIGN KEY."""
    name, table = row['path'][-1], row['path'][0]
    return any(other['kind'] == 'constraint' and other['path'][0] == table and
               other['native'].get('index_name') == name for other in rows.values())


def _key_index(native, rows, table):
    """Columns of the index behind a PRIMARY KEY/UNIQUE constraint of table."""
    backing = native.get('backing_index')
    if isinstance(backing, dict) and backing.get('segments'):
        return _names(backing['segments'])
    index = rows.get(catalog_resource_id('index', [table], native.get('index_name')))
    return _names(index['native'].get('segments')) if index else []


def extract(row, rows):
    """Vocabulary for one native index/constraint row and whether the vocabulary is
    complete enough that replacing the object cannot silently lose native properties.

    row and rows are resource-map shaped: {'kind', 'native', 'path'}."""
    native, path, kind = row['native'], row['path'], row['kind']
    if len(path) != 2:
        return None
    table, name = path
    if kind == 'index':
        columns = _names(native.get('segments'))
        values = {'physical_kind': 'index', 'physical_name': name, 'unique': _is(native.get('unique')),
                  'descending': _is(native.get('index_type')), 'inactive': _is(native.get('inactive'))}
        replaceable = True
        if native.get('expression_source'):
            values['expression'] = native['expression_source']
        elif columns:
            values['columns_json'] = vocab.encode(columns)
        else:
            return None
        if native.get('condition_source'):
            match = re.fullmatch(r'\s*WHERE\s+(.+)', native['condition_source'], re.I | re.S)
            if match:
                values['predicate'] = match.group(1)
            else:
                replaceable = False
        return {'values': values, 'replaceable': replaceable}
    if kind != 'constraint':
        return None
    kind_name = KEY_KINDS.get(native.get('constraint_type'))
    if kind_name is None:
        return None
    values = {'physical_kind': kind_name, 'physical_name': name}
    if kind_name == 'check':
        match = re.fullmatch(r'\s*CHECK\s*(\(.*\))\s*', native.get('check_source') or '', re.I | re.S)
        if match is None:
            return {'values': values, 'replaceable': False}
        values['expression'] = match.group(1)
        return {'values': values, 'replaceable': True}
    backing = native.get('backing_index')
    columns = _key_index(native, rows, table)
    replaceable = (isinstance(backing, dict) and bool(columns) and backing.get('name') == native.get('index_name') and
                   not backing.get('expression_source') and not backing.get('condition_source') and
                   not _is(backing.get('inactive')))
    if columns:
        values['columns_json'] = vocab.encode(columns)
    values['descending'] = _is(backing.get('index_type')) if isinstance(backing, dict) else False
    if kind_name == 'foreign-key':
        referenced = _key_index({'index_name': native.get('referenced_index')}, rows, native.get('referenced_relation'))
        if referenced:
            values['referenced_columns_json'] = vocab.encode(referenced)
        else:
            replaceable = False
        for key, rule in (('on_delete', 'delete_rule'), ('on_update', 'update_rule')):
            values[key] = native.get(rule) if native.get(rule) in vocab.ACTIONS else 'RESTRICT'
    return {'values': values, 'replaceable': replaceable}


def forward(resources):
    """Vocabulary elements grouped by owning table name for firebird_erd.

    Returns {table: [{'row', 'values', 'role'}...]}. Constraint-backing indexes and
    foreign keys (drawn as edges) are excluded; NOT NULL has no vocabulary (the column
    ``nullable`` edit is its path)."""
    rows = resource_map(resources)
    grouped = {}
    for row in resources:
        item = rows[row['resource_id']]
        if item['kind'] not in {'index', 'constraint'} or item['native'].get('system_object') is True:
            continue
        if item['kind'] == 'index' and constraint_backed(item, rows):
            continue
        found = extract(item, rows)
        if found is None or found['values']['physical_kind'] == 'foreign-key':
            continue
        grouped.setdefault(item['path'][0], []).append({
            'row': row, 'values': found['values'], 'role': vocab.ROLE[found['values']['physical_kind']]})
    return grouped


def edge_values(row, rows):
    found = extract(rows[row['resource_id']], rows)
    return dict(found['values']) if found else {}


def table_values(name):
    return {'physical_name': name}


def column_values(name):
    return {'physical_name': name}


# --------------------------------------------------------------------------- merge

def _lifecycle(native, operation, name, **extra):
    native['lifecycle'] = {'operation': operation, 'confirmation': name, **extra}
    return native


def _vocabulary(old, row, label):
    before, after = old.get('physical') or {}, row.get('physical') or {}
    if after and not before:
        raise ValueError('The baseline diagram carries no physical-schema vocabulary for this ' + label + '; regenerate it')
    return before, after


def merge_table(old, row, live, native):
    before, after = _vocabulary(old, row, 'table')
    if not after:
        return native
    name = live['name']
    renamed = vocab.rename(before, after, 'table')
    if renamed:
        if renamed[0] != name:
            raise ValueError('rename_from does not name the baseline table')
        raise NotCarried(NOT_CARRIED['table'])
    if vocab.drop(before, after, name, 'table'):
        _lifecycle(native, 'drop', name)
    return native


def merge_column(old, row, live, native):
    """Column rename (ALTER COLUMN ... TO) and drop from the field annotation."""
    before = (old.get('fields') or {}).get('_physical') or {}
    after = (row.get('fields') or {}).get('_physical') or {}
    if after and not before:
        raise ValueError('The baseline diagram carries no physical-schema vocabulary for this column; regenerate it')
    if not after:
        return native
    name = live['name']
    renamed = vocab.rename(before, after, 'column')
    if renamed:
        if renamed[0] != name:
            raise ValueError('rename_from does not name the baseline column')
        _lifecycle(native, 'rename', name, new_name=renamed[1])
    if vocab.drop(before, after, name, 'column'):
        if renamed:
            raise ValueError('Review a drop separately from other edits to the same object')
        _lifecycle(native, 'drop', name)
    return native


def _flag(value):
    return '1' if value else '0'


def _segments(columns):
    return [{'field_name': name, 'position': position} for position, name in enumerate(columns)]


def _guard_physical_kind(changed, label):
    if 'physical_kind' in changed:
        raise ValueError('The physical kind of an existing ' + label + ' cannot change')


def merge_index(old, row, live, current, native):
    before, after = _vocabulary(old, row, 'object')
    if not after:
        return native
    name = live['name']
    found = extract({'kind': 'index', 'native': old['native'], 'path': live['path']}, current['rows'])
    if found is None:
        raise ValueError('Physical vocabulary is unavailable for this native index')
    wanted = vocab.normalize(after)
    if (vocab.drop(before, after, name, 'index') or vocab.rename(before, after, 'index') or
            vocab.changes(before, after)):
        if constraint_backed(live, current['rows']):
            raise ValueError('This index implements a constraint; edit the constraint instead')
    if vocab.drop(before, after, name, 'index'):
        return _lifecycle(native, 'drop', name)
    if vocab.rename(before, after, 'index'):
        raise NotCarried(NOT_CARRIED['index'])
    changed = vocab.changes(before, after)
    _guard_physical_kind(changed, 'object')
    content = {key: changed[key] for key in INDEX_CONTENT + ('inactive',) if key in changed}
    if not content:
        return native
    merged = {**vocab.normalize(before), **wanted}
    if 'columns' in content and 'expression' not in content:
        merged.pop('expression', None)
    if 'expression' in content and 'columns' not in content:
        merged.pop('columns', None)
    if bool(merged.get('expression')) == bool(merged.get('columns')):
        raise ValueError('An index is defined by either key columns or one COMPUTED BY expression, not both')
    if 'unique' in content:
        native['unique'] = _flag(content['unique'])
    if 'descending' in content:
        native['index_type'] = _flag(content['descending'])
    if 'inactive' in content:
        native['inactive'] = _flag(content['inactive'])
    if 'columns' in content or 'expression' in content:
        if merged.get('columns'):
            native['segments'], native['expression_source'] = _segments(merged['columns']), None
        else:
            native.pop('segments', None)
            native['expression_source'] = merged['expression']
    if 'predicate' in content:
        native['condition_source'] = 'WHERE ' + content['predicate'] if content['predicate'].strip() else None
    if set(content) & set(INDEX_CONTENT):
        _lifecycle(native, 'replace', name)
    return native


def _table_columns(table, current):
    return {item['path'][1] for item in current['rows'].values()
            if item['kind'] == 'column' and len(item['path']) == 2 and item['path'][0] == table}


def _require_not_null(table, columns, current):
    """Firebird refuses a PRIMARY KEY over a nullable column (it does not add NOT NULL)."""
    nullable = []
    for name in columns:
        column = current['rows'].get(catalog_resource_id('column', [table], name))
        native = column['native'] if column else {}
        declared = any(item['kind'] == 'constraint' and item['path'][0] == table and
                       item['native'].get('not_null_column') == name for item in current['rows'].values())
        if not (str(native.get('not_null')) == '1' or str(native.get('domain_not_null')) == '1' or declared):
            nullable.append(name)
    if nullable:
        raise ValueError('PRIMARY KEY columns must be NOT NULL in Firebird; make these columns non-nullable in a '
                         'separate reviewed change first: ' + ', '.join(nullable))


def _keys(table, current, extra=()):
    """PRIMARY KEY / UNIQUE constraints of table: [(index name, ordered columns)]."""
    result = []
    for item in [*current['rows'].values(), *extra]:
        if item['kind'] == 'constraint' and item['path'][0] == table and item['native'].get('constraint_type') in {'PRIMARY KEY', 'UNIQUE'}:
            result.append((item['native'].get('index_name'), _key_index(item['native'], current['rows'], table), item['resource_id']))
    return result


def _reference(target, columns, current, pending=()):
    """The PRIMARY KEY/UNIQUE index of table target covering exactly these ordered columns."""
    tables = [item for item in current['rows'].values() if item['kind'] == 'table' and item['name'] == target and
              item['system'] == 'false']
    if len(tables) != 1:
        raise ValueError('Foreign-key target is not a visible ordinary user table')
    for index, names, owner in _keys(target, current, pending):
        if names == list(columns):
            return index, owner
    raise ValueError('Foreign-key referenced columns need a PRIMARY KEY or UNIQUE constraint on the target table with the same ordered columns')


def _dependents(live, current):
    return [item['name'] for item in current['rows'].values() if item['kind'] == 'constraint' and
            item['native'].get('constraint_type') == 'FOREIGN KEY' and
            item['native'].get('referenced_relation') == live['path'][0] and
            item['native'].get('referenced_index') == live['native'].get('index_name')]


def _table_named(rid, current):
    table = current['rows'].get(rid) if rid else None
    if table is None or table['kind'] != 'table' or table['system'] != 'false':
        raise ValueError('Foreign-key target is not a visible ordinary user table')
    return table['name']


def merge_constraint(old, row, live, current, native, mirror):
    before, after = _vocabulary(old, row, 'object')
    if not after:
        return native
    name = live['name']
    ctype = old['native'].get('constraint_type')
    found = extract({'kind': 'constraint', 'native': old['native'], 'path': live['path']}, current['rows'])
    if found is None:
        raise ValueError('Physical vocabulary is unavailable for this native constraint')
    if vocab.drop(before, after, name, 'constraint'):
        return _lifecycle(native, 'drop', name)
    if vocab.rename(before, after, 'constraint'):
        raise NotCarried(NOT_CARRIED['constraint'])
    changed = vocab.changes(before, after)
    _guard_physical_kind(changed, 'object')
    edges = {}
    previous, wanted = old.get('endpoints') or {}, row.get('endpoints') or {}
    if ctype == 'FOREIGN KEY' and wanted and previous:
        if wanted.get('target') != previous.get('target'):
            edges['target'] = wanted.get('target')
        if wanted.get('source') != previous.get('source'):
            raise ValueError('Moving a foreign key to another owning table needs a new constraint')
    content = {key: value for key, value in changed.items() if key != 'physical_name'}
    if not content and not edges:
        return native
    applicable = {'CHECK': {'expression'}, 'PRIMARY KEY': {'columns', 'descending'},
                  'UNIQUE': {'columns', 'descending'},
                  'FOREIGN KEY': {'columns', 'descending', 'referenced_columns', 'on_delete', 'on_update'}}[ctype]
    if set(content) - applicable:
        raise ValueError('Not applicable to a Firebird ' + ctype + ': ' + ', '.join(sorted(set(content) - applicable)))
    if not found['replaceable']:
        raise ValueError('This constraint has native properties outside the vocabulary (for example an inactive or '
                         'differently named backing index); edit it natively')
    if ctype in {'PRIMARY KEY', 'UNIQUE'} and _dependents(live, current):
        raise ValueError('Foreign keys depend on this key; change them in a separate reviewed change first')
    merged = {**vocab.normalize(before), **vocab.normalize(after)}
    if ctype == 'CHECK':
        native['check_source'] = 'CHECK ' + content['expression'].strip()
        return native
    backing = native.get('backing_index')
    if not isinstance(backing, dict):
        raise ValueError('The constraint carries no backing index definition')
    if 'columns' in content:
        columns = content['columns']
        if ctype == 'PRIMARY KEY':
            _require_not_null(live['path'][0], columns, current)
        missing = [item for item in columns if item not in _table_columns(live['path'][0], current)]
        if missing:
            raise ValueError('Constraint columns are not columns of the table: ' + ', '.join(missing))
        backing['segments'] = _segments(columns)
    if 'descending' in content:
        backing['index_type'] = _flag(content['descending'])
    if ctype == 'FOREIGN KEY':
        if 'on_delete' in content:
            native['delete_rule'] = RULES.get(content['on_delete'], content['on_delete'])
        if 'on_update' in content:
            native['update_rule'] = RULES.get(content['on_update'], content['on_update'])
        if 'referenced_columns' in content or 'target' in edges:
            target = _table_named(edges['target'], current) if 'target' in edges else native.get('referenced_relation')
            index, _ = _reference(target, merged.get('referenced_columns') or [], current)
            native['referenced_relation'], native['referenced_index'] = target, index
    mirrored = current['rows'].get(catalog_resource_id('index', [live['path'][0]], backing.get('name')))
    if mirrored is not None:
        projection = deepcopy(mirrored['native'])
        for key in ('segments', 'index_type'):
            if key in backing:
                projection[key] = deepcopy(backing[key])
        mirror[mirrored['resource_id']] = projection
    return native


# --------------------------------------------------------------------------- drafts

ALLOWED = {
    'index': {'unique', 'descending', 'inactive', 'columns', 'expression', 'predicate'},
    'primary-key': {'descending', 'columns'},
    'unique': {'descending', 'columns'},
    'check': {'expression'},
    'foreign-key': {'descending', 'columns', 'referenced_columns', 'on_delete', 'on_update'},
}
BASE = {'physical_kind', 'physical_name', 'columns_json', 'referenced_columns_json'}
KEY_NATIVE = {'primary-key': 'PRIMARY KEY', 'unique': 'UNIQUE', 'foreign-key': 'FOREIGN KEY'}


def _index_native(values):
    native = {'unique': _flag(values.get('unique')), 'inactive': _flag(values.get('inactive')),
              'index_type': _flag(values.get('descending')), 'description': None,
              'condition_source': 'WHERE ' + values['predicate'] if values.get('predicate', '').strip() else None,
              'system_object': False}
    if values.get('expression'):
        native['expression_source'] = values['expression']
    else:
        native['expression_source'], native['segments'] = None, _segments(values['columns'])
    return native


def new_objects(drafts, tables, current):
    """New catalog rows for physical drafts.

    drafts maps a table resource id to its draft items; tables maps a table resource id
    to its baseline reader row. Returns insertable rows for the desired document only.
    Non-foreign-key drafts are created first so a foreign key may reference a key added
    in the same review."""
    from .firebird_domain_plan import clause
    taken = {item['path'][-1] for item in current['rows'].values() if item['kind'] in {'index', 'constraint'}}
    seen, parsed = set(), []
    for parent, items in sorted(drafts.items()):
        owner = current['rows'].get(parent)
        if owner is None or owner['kind'] != 'table' or owner['system'] != 'false':
            raise ValueError('Physical drafts need an exact ordinary user table')
        if str(owner['native'].get('relation_type')) not in {'0', '4', '5'}:
            raise ValueError('Physical drafts need a native persistent or temporary table')
        if len(items) > 64:
            raise ValueError('Physical additions allow at most 64 drafts per table')
        for draft in items:
            values = vocab.normalize(draft['physical'], 'physical draft')
            kind = values.get('physical_kind')
            vocab.draft_identity('firebird', tables[parent]['uid'], draft['uid'])
            if kind is None or 'physical_name' not in values:
                raise ValueError('A physical draft needs physical_kind and physical_name')
            if 'drop' in values or 'rename_from' in values:
                raise ValueError('A new physical object cannot carry drop or rename intent')
            name = values['physical_name']
            identifier(name)
            if name in taken or name in seen:
                raise ValueError('A Firebird index or constraint named ' + name + ' already exists; names are database-wide')
            seen.add(name)
            excess = set(values) - ALLOWED[kind] - BASE - {'drop_confirmation'}
            if excess:
                raise ValueError('Not applicable to a Firebird ' + kind + ': ' + ', '.join(sorted(excess)))
            columns = values.get('columns')
            keyless = kind == 'check' or (kind == 'index' and values.get('expression') and not columns)
            if not keyless and (not columns or any(item not in _table_columns(owner['name'], current) for item in columns)):
                raise ValueError('Draft columns must be existing columns of the table')
            if kind == 'index' and bool(values.get('expression')) == bool(columns):
                raise ValueError('An index is defined by either key columns or one COMPUTED BY expression')
            if kind == 'primary-key':
                _require_not_null(owner['name'], columns, current)
            if kind == 'primary-key' and any(item['kind'] == 'constraint' and item['path'][0] == owner['name'] and
                                              item['native'].get('constraint_type') == 'PRIMARY KEY'
                                              for item in current['rows'].values()):
                raise ValueError('The table already has a PRIMARY KEY')
            parsed.append((parent, owner, draft, kind, name, values))
    if sum(1 for item in parsed if item[3] == 'primary-key') != len({item[0] for item in parsed if item[3] == 'primary-key'}):
        raise ValueError('A table has only one PRIMARY KEY')
    rows, created = [], []
    for phase in (0, 1):
        for parent, owner, draft, kind, name, values in parsed:
            if (kind == 'foreign-key') != bool(phase):
                continue
            table = owner['name']

            def row(row_kind, native):
                return {'owner': parent, 'resource_id': catalog_resource_id(row_kind, [table], name), 'kind': row_kind,
                        'path': [table, name], 'system': 'false', 'native': native, 'name': name}
            if kind == 'index':
                rows.append(row('index', _index_native(values)))
                continue
            if kind == 'check':
                source = 'CHECK ' + values.get('expression', '').strip()
                clause(source, 'CHECK')
                rows.append(row('constraint', {'constraint_type': 'CHECK', 'check_source': source, 'system_object': False}))
                continue
            backing = _index_native({'columns': values['columns'], 'unique': kind != 'foreign-key',
                                     'descending': values.get('descending')})
            native = {'constraint_type': KEY_NATIVE[kind], 'index_name': name, 'system_object': False,
                      'backing_index': {'name': name, **deepcopy(backing)}}
            if kind == 'foreign-key':
                target = _table_named((draft.get('endpoints') or {}).get('target'), current)
                index, key_owner = _reference(target, values.get('referenced_columns') or [], current, created)
                wanted = {key: RULES.get(values.get(key, 'RESTRICT'), values.get(key, 'RESTRICT')) for key in ('on_update', 'on_delete')}
                native.update(referenced_relation=target, referenced_index=index,
                              update_rule=wanted['on_update'], delete_rule=wanted['on_delete'])
                if key_owner in {item['resource_id'] for item in created}:
                    native['creation_dependencies'] = [key_owner]
            constraint = row('constraint', native)
            created.append(constraint)
            rows.extend([row('index', backing), constraint])
    return rows

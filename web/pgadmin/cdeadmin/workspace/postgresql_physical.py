"""PostgreSQL physical-schema edits from the diagram: indexes, UNIQUE/CHECK/PRIMARY
KEY/FOREIGN KEY constraints (with ON DELETE/UPDATE actions) and explicit renames.

Three stages share this module:
  * extract(): native catalog facts -> vocabulary (forward ERD, convergence tests)
  * merge_physical(): edited vocabulary -> explicit native intents in the desired model
  * plan_row()/table_additions(): intents -> reviewed plan operations (build_plan hooks)

Nothing here executes SQL. Missing diagram objects are never deletion intent, a changed
name is only a rename with an explicit rename_from mapping, and drops need the exact name.
"""
from copy import deepcopy
import re
from . import physical_schema as vocab
from .firebird_catalog_import import _equal
from .firebird_schema_plan import digest

TABLE_KINDS = {'table'}
KEY_KINDS = {'primary-key': 'PRIMARY KEY', 'unique': 'UNIQUE', 'check': 'CHECK',
             'foreign-key': 'FOREIGN KEY'}
CONTYPES = {'p': 'primary-key', 'u': 'unique', 'c': 'check', 'f': 'foreign-key'}


def _columns(native):
    return {int(item['attnum']): item['attname']
            for item in native.get('children', {}).get('pg_attribute', [])}


def _unquote(token):
    token = token.strip()
    return token[1:-1].replace('""', '"') if len(token) > 1 and token[0] == token[-1] == '"' else token


def _owner_oid(row):
    native = row['native']
    if row['kind'] == 'index':
        indexes = native.get('children', {}).get('pg_index', [])
        return str(indexes[0]['indrelid']) if len(indexes) == 1 else None
    return str(native.get('catalog_row', {}).get('conrelid')) if row['kind'] == 'constraint' else None


def constraint_backed_index(row, rows):
    """True for an index that merely implements a PRIMARY KEY/UNIQUE/EXCLUDE constraint."""
    oid = str(row['native'].get('oid'))
    return any(other['kind'] == 'constraint' and other['native'].get('catalog') == 'pg_constraint' and
               str(other['native'].get('catalog_row', {}).get('conindid')) == oid
               and other['native']['catalog_row'].get('contype') in {'p', 'u', 'x'}
               for other in rows.values())


def extract(row, rows):
    """Vocabulary for one native index/constraint row, plus whether the vocabulary is
    complete enough that replacing the object cannot silently lose native properties.

    rows is a mapping resource_id -> row (a catalog model's rows or a resource map)."""
    native = row['native']
    owner = rows.get('postgresql:pg_class:' + str(_owner_oid(row)))
    names = _columns(owner['native']) if owner else {}
    if row['kind'] == 'index':
        indexes = native.get('children', {}).get('pg_index', [])
        if len(indexes) != 1:
            return None
        info = indexes[0]
        definition = native.get('definition') or ''
        if not isinstance(native.get('catalog_row', {}).get('relname'), str):
            return None
        values = {'physical_kind': 'index', 'physical_name': native['catalog_row']['relname'],
                  'unique': bool(info.get('indisunique'))}
        using = re.search(r' USING (\w+) \(', definition)
        if using:
            values['method'] = using.group(1)
        if info.get('indpred') is not None and ' WHERE ' in definition:
            values['predicate'] = definition.rsplit(' WHERE ', 1)[1]
        keys = [int(number) for number in info.get('indkey', [])]
        simple = (using is not None and all(number > 0 and number in names for number in keys) and
                  int(info.get('indnatts', len(keys))) == int(info.get('indnkeyatts', len(keys))) and
                  all(int(option) == 0 for option in info.get('indoption', [])) and
                  info.get('indexprs') is None and not native['catalog_row'].get('reloptions') and
                  str(native['catalog_row'].get('reltablespace', '0')) == '0')
        if simple:
            tail = definition[using.end():]
            end = tail.find(')')
            tokens = [_unquote(token) for token in tail[:end].split(', ')] if end > 0 else []
            names_in_order = [names[number] for number in keys]
            if tokens != names_in_order:
                simple = False  # explicit opclass, collation or ordering text
        if simple:
            values['columns_json'] = vocab.encode(names_in_order)
        return {'values': values, 'replaceable': simple}
    contype = native.get('catalog_row', {}).get('contype')
    kind = CONTYPES.get(contype)
    if kind is None:
        return None
    facts = native['catalog_row']
    if not isinstance(facts.get('conname'), str):
        return None
    values = {'physical_kind': kind, 'physical_name': facts['conname']}
    replaceable = (not facts.get('condeferrable') and facts.get('convalidated') is True and
                   str(facts.get('contypid')) in {'0'} and str(facts.get('conparentid', '0')) == '0' and
                   int(facts.get('coninhcount', 0)) == 0)
    if kind == 'check':
        expression = vocab.split_check(native.get('definition'))
        if expression is None:
            replaceable = False
        else:
            values['expression'] = expression
        return {'values': values, 'replaceable': replaceable}
    keys = [names.get(int(number)) for number in facts.get('conkey') or []]
    if None in keys or not keys:
        replaceable = False
    else:
        values['columns_json'] = vocab.encode(keys)
    if kind == 'foreign-key':
        target = rows.get('postgresql:pg_class:' + str(facts.get('confrelid')))
        referenced = ([_columns(target['native']).get(int(number)) for number in facts.get('confkey') or []]
                      if target else [None])
        if None in referenced or not referenced:
            replaceable = False
        else:
            values['referenced_columns_json'] = vocab.encode(referenced)
        values['on_delete'] = vocab.ACTION_CODES.get(str(facts.get('confdeltype')).strip(), 'NO ACTION')
        values['on_update'] = vocab.ACTION_CODES.get(str(facts.get('confupdtype')).strip(), 'NO ACTION')
        replaceable = replaceable and facts.get('confmatchtype') == 's' and not facts.get('condeferred')
    return {'values': values, 'replaceable': replaceable}


def forward(resources):
    """Group vocabulary elements by owning table OID for postgresql_erd.

    Returns {table_oid: [{'row', 'values', 'role'}...]}; constraint-backed indexes and
    foreign keys (drawn as edges) are excluded."""
    rows = resource_map(resources)
    grouped = {}
    for row in resources:
        item = rows[row['resource_id']]
        if item['kind'] not in {'index', 'constraint'} or item['native'].get('system_object') is True:
            continue
        if item['kind'] == 'index' and constraint_backed_index(item, rows):
            continue
        found = extract(item, rows)
        if found is None or found['values']['physical_kind'] == 'foreign-key':
            continue
        oid = _owner_oid(item)
        if oid in {None, '0'}:
            continue
        grouped.setdefault(int(oid), []).append({
            'row': row, 'values': found['values'], 'role': vocab.ROLE[found['values']['physical_kind']]})
    return grouped


def resource_map(resources):
    from .firebird_catalog_export import native_metadata
    return {row['resource_id']: {'kind': row['resource_kind'], 'native': native_metadata(row, 'postgresql')}
            for row in resources}


def edge_values(row, rows):
    found = extract(rows[row['resource_id']], rows)
    return dict(found['values']) if found else {}


def column_values(name):
    return {'physical_name': name}


def table_values(name):
    return {'physical_name': name}


# --------------------------------------------------------------------------- merge

def _definition(kind, values, live_rows):
    """Complete desired definition from normalized vocabulary values."""
    if kind == 'index':
        return {'physical_kind': 'index', 'columns': values.get('columns'), 'unique': values.get('unique', False),
                'method': values.get('method', 'btree'), 'predicate': values.get('predicate')}
    result = {'physical_kind': kind}
    for key in ('columns', 'expression', 'on_delete', 'on_update'):
        if key in values:
            result[key] = values[key]
    if kind == 'foreign-key':
        result['referenced'] = values.get('referenced')
    return result


def _referenced(target_id, columns, current):
    table = current['rows'].get(target_id) if target_id else None
    if (table is None or table['kind'] != 'table' or table.get('system') != 'false' or
            table['native'].get('catalog') != 'pg_class'):
        raise ValueError('Foreign-key target is not a visible ordinary user table')
    return {'schema': table['native']['schema'], 'table': table['native']['catalog_row']['relname'],
            'columns': columns}


def merge_physical(old, row, live, current, drafts):
    """Translate vocabulary edits on one relational row into explicit native intents.

    old/row are the baseline and edited reader rows; the returned dict replaces the
    desired native facts already produced by merge_fields."""
    native = deepcopy(row['native'])
    before, after = old.get('physical') or {}, row.get('physical') or {}
    kind = live['kind']
    if kind in TABLE_KINDS:
        name = old['native'].get('catalog_row', {}).get('relname')
        if after and not before:
            raise ValueError('The baseline diagram carries no physical-schema vocabulary for this table; regenerate it')
        renamed = vocab.rename(before, after, 'table') if after else None
        if renamed:
            if renamed[0] != name:
                raise ValueError('rename_from does not name the baseline table')
            native.setdefault('catalog_row', {})['relname'] = renamed[1]
        if after and vocab.drop(before, after, name, 'table'):
            native['drop'] = True
        _merge_columns(old, row, native)
        _merge_drafts(old, row, native, drafts, current)
        return native
    if kind not in {'index', 'constraint'} or not after:
        return native
    if not before:
        raise ValueError('The baseline diagram carries no physical-schema vocabulary for this object; regenerate it')
    old_values = vocab.normalize(before)
    new_values = vocab.normalize(after)
    found = extract({'kind': kind, 'native': old['native']}, current['rows'])
    name = found['values']['physical_name'] if found else None
    if name is None:
        raise ValueError('Physical vocabulary is unavailable for this native object')
    if vocab.drop(before, after, name, kind):
        native['physical_change'] = {'action': 'drop', 'name': name, 'confirmation': name}
        return native
    changed = vocab.changes(before, after)
    renamed = vocab.rename(before, after, kind)
    if 'physical_kind' in changed:
        raise ValueError('The physical kind of an existing object cannot change')
    edges = {}
    if kind == 'constraint':
        previous = old.get('endpoints') or {}
        wanted = row.get('endpoints') or {}
        if wanted and previous and wanted.get('target') != previous.get('target'):
            edges['target'] = wanted.get('target')
        if wanted and previous and wanted.get('source') != previous.get('source'):
            raise ValueError('Moving a foreign key to another owning table needs a new constraint')
    content = {key: value for key, value in changed.items() if key != 'physical_name'}
    if not content and not edges:
        if renamed:
            native['physical_change'] = {'action': 'rename', 'from': renamed[0], 'name': renamed[1]}
        return native
    merged = {**old_values, **new_values}
    merged_kind = old_values.get('physical_kind') or found['values']['physical_kind']
    if kind == 'constraint' and merged_kind == 'foreign-key':
        target = edges.get('target') or (old.get('endpoints') or {}).get('target')
        merged['referenced'] = _referenced(target, merged.get('referenced_columns') or old_values.get('referenced_columns'), current)
    desired = _definition(merged_kind if kind == 'constraint' else 'index', merged, current['rows'])
    native['physical_change'] = {'action': 'replace', 'from': renamed[0] if renamed else name,
                                 'name': renamed[1] if renamed else name, 'definition': desired}
    return native


def _merge_columns(old, row, native):
    attributes = {str(item['attnum']): item for item in native.get('children', {}).get('pg_attribute', [])}
    baseline = {str(item['attnum']): item['attname'] for item in old['native'].get('children', {}).get('pg_attribute', [])}
    prefix = old['uid'] + ':'
    for uid, fields in row.get('fields', {}).items():
        after = fields.get('_physical') or {}
        before = (old.get('fields', {}).get(uid) or {}).get('_physical') or {}
        number = uid[len(prefix):] if uid.startswith(prefix) else None
        if not after or number not in attributes or number not in baseline:
            continue
        if not before:
            raise ValueError('The baseline diagram carries no physical-schema vocabulary for this column; regenerate it')
        attribute = attributes[number]
        renamed = vocab.rename(before, after, 'column')
        if renamed:
            if renamed[0] != baseline[number]:
                raise ValueError('rename_from does not name the baseline column')
            attribute['attname'] = renamed[1]
        if vocab.drop(before, after, baseline[number], 'column'):
            attribute['drop'] = True


def _merge_drafts(old, row, native, drafts, current):
    indexes, constraints = [], []
    for draft in drafts:
        values = vocab.normalize(draft['physical'], 'physical draft')
        kind = values.get('physical_kind')
        identity = vocab.draft_identity('postgresql', old['uid'], draft['uid'])
        if kind is None or 'physical_name' not in values:
            raise ValueError('A physical draft needs physical_kind and physical_name')
        if 'drop' in values or 'rename_from' in values:
            raise ValueError('A new physical object cannot carry drop or rename intent')
        item = {'resource_id': identity, 'name': values['physical_name']}
        if kind == 'foreign-key':
            target = (draft.get('endpoints') or {}).get('target')
            values['referenced'] = _referenced(target, values.get('referenced_columns'), current)
        item['definition'] = _definition(kind, values, current['rows'])
        (indexes if kind == 'index' else constraints).append(item)
    if indexes:
        native['add_indexes'] = indexes
    if constraints:
        native['add_constraints'] = constraints


# --------------------------------------------------------------------------- plan

def _checked(statement, expected):
    from ..providers.postgresql.language import analyze
    from pglast import parse_sql
    parsed = parse_sql(statement)
    if (analyze(statement, standard_strings='on')['grammar_valid'] is not True or
            len(parsed) != 1 or not isinstance(parsed[0].stmt, expected)):
        raise ValueError('Generated physical-schema statement failed native grammar validation')
    return statement


def _owner(row, current):
    return _owner_table(current['rows'].get('postgresql:pg_class:' + str(_owner_oid(row))))


def _owner_table(owner):
    from .postgresql_schema_plan import _lock_target
    if (owner is None or owner['kind'] != 'table' or owner.get('system') != 'false' or
            not _lock_target(owner)):
        raise ValueError('Physical object requires its exact ordinary user table')
    facts = owner['native'].get('catalog_row', {})
    if (facts.get('relhassubclass') or facts.get('relispartition') or
            owner['native'].get('children', {}).get('pg_inherits')):
        raise ValueError('Physical changes on partitioned, inherited or inheriting tables need a separate adapter')
    return owner


def _key(kind, name, definition, names, owner_columns):
    key = {'kind': KEY_KINDS[kind], 'name': name}
    if kind == 'check':
        key['expression'] = definition.get('expression')
        return key
    key['columns'] = definition.get('columns')
    if kind == 'foreign-key':
        reference = definition.get('referenced')
        if not reference or not reference.get('columns'):
            raise ValueError('Foreign key needs referenced columns and a target table')
        key['references'] = reference
        key['on_delete'] = definition.get('on_delete', 'NO ACTION')
        key['on_update'] = definition.get('on_update', 'NO ACTION')
    return key


def _add_statement(owner, kind, name, definition, extra_columns=()):
    from ..providers.postgresql.native_admin import _identifier
    from .postgresql_creation import index_definition, key_definition
    from pglast import ast
    native = owner['native']
    names = set(_columns(native).values()) | set(extra_columns)
    if kind == 'index':
        columns = definition.get('columns')
        if not columns or any(column not in names for column in columns):
            raise ValueError('Index columns must be existing or newly added columns of the table')
        draft = {'table': native['catalog_row']['relname'], 'keys': [{'column': column} for column in columns],
                 'method': definition.get('method') or 'btree', 'unique': bool(definition.get('unique'))}
        if definition.get('predicate'):
            draft['predicate'] = definition['predicate']
        return _checked(index_definition(name, native['schema'], draft), ast.IndexStmt)
    if kind in {'primary-key', 'unique', 'foreign-key'}:
        columns = definition.get('columns')
        if not columns or any(column not in names for column in columns):
            raise ValueError('Constraint columns must be existing or newly added columns of the table')
    key = _key(kind, name, definition, names, names)
    return _checked('ALTER TABLE ONLY ' + native['sql_identity'] + ' ADD ' + key_definition(key, names), ast.AlterTableStmt)


def _check_foreign_target(definition, current):
    reference = definition.get('referenced')
    if not reference:
        return
    targets = [row for row in current['rows'].values() if row['kind'] == 'table' and
               row['native'].get('schema') == reference['schema'] and
               row['native'].get('catalog_row', {}).get('relname') == reference['table']]
    if len(targets) != 1:
        raise ValueError('Foreign-key target table is unavailable or ambiguous')
    names = _columns(targets[0]['native'])
    if any(column not in names.values() for column in reference['columns']):
        raise ValueError('Foreign-key referenced columns are not columns of the target table')
    oid = str(targets[0]['native']['oid'])
    wanted = sorted(reference['columns'])
    for row in current['rows'].values():
        facts = row['native'].get('catalog_row', {}) if row['kind'] == 'constraint' else {}
        if facts.get('contype') in {'p', 'u'} and str(facts.get('conrelid')) == oid and \
                sorted(names.get(int(number)) for number in facts['conkey']) == wanted:
            return
    raise ValueError('Foreign-key referenced columns need a PRIMARY KEY or UNIQUE constraint on the target table')


def _dependents(row, current):
    """Foreign keys that depend on the index behind a PRIMARY KEY/UNIQUE constraint."""
    index = str(row['native'].get('catalog_row', {}).get('conindid'))
    return [other for other in current['rows'].values() if other['kind'] == 'constraint' and
            other['native'].get('catalog_row', {}).get('contype') == 'f' and
            str(other['native']['catalog_row'].get('conindid')) == index and index not in {'0', 'None'}]


def _live_by_name(owner, kind, name, current):
    """A live object of the owner table with this name, if any."""
    oid = str(owner['native']['oid'])
    for row in current['rows'].values():
        if row['kind'] == 'index' and kind == 'index' and _owner_oid(row) == oid and \
                row['native']['catalog_row'].get('relname') == name:
            return row
        if row['kind'] == 'constraint' and kind != 'index' and _owner_oid(row) == oid and \
                row['native']['catalog_row'].get('conname') == name:
            return row
    return None


def _relation_named(owner, name, current):
    return any(row['native'].get('catalog') == 'pg_class' and row['native'].get('schema') == owner['native']['schema'] and
               row['native'].get('catalog_row', {}).get('relname') == name for row in current['rows'].values())


def _same(row, definition, current):
    found = extract(row, current['rows'])
    if not found:
        return False
    values = found['values']
    kind = values['physical_kind']
    normalized = vocab.normalize({key: value for key, value in values.items()})
    comparable = _definition(kind, normalized, current['rows'])
    if kind == 'foreign-key':
        facts = row['native']['catalog_row']
        target = current['rows'].get('postgresql:pg_class:' + str(facts['confrelid']))
        if target:
            comparable['referenced'] = {'schema': target['native']['schema'],
                                        'table': target['native']['catalog_row']['relname'],
                                        'columns': normalized.get('referenced_columns')}
    return _equal(_normalized(comparable), _normalized(definition))


def _json_safe(value):
    import json
    return json.loads(json.dumps(value))


def _canonical_expression(text):
    """Parsed expression text with the redundant string-literal casts PostgreSQL adds
    (''::text) removed, so a stored CHECK or index predicate compares with what was drafted."""
    from pglast import parse_sql, ast
    from pglast.visitors import Visitor
    from pglast.stream import RawStream

    class Strip(Visitor):
        def visit_TypeCast(self, ancestors, node):
            if isinstance(node.arg, ast.A_Const) and isinstance(node.arg.val, ast.String):
                return node.arg

    from .postgresql_creation import expression
    tree = parse_sql('SELECT (' + expression(text) + ')')
    return RawStream()(Strip()(tree)[0].stmt.targetList[0].val)


def _normalized(definition):
    result = _json_safe(definition)
    for key in ('expression', 'predicate'):
        if result.get(key):
            result[key] = _canonical_expression(result[key])
    return result


def _operation(owner, row, operation, statement, name, **extra):
    from .postgresql_schema_plan import _lock_target
    return {'resource_id': row['resource_id'] if row else extra.pop('resource_id'),
            'parent_resource_id': 'postgresql:pg_class:' + str(owner['native']['oid']),
            'kind': extra.pop('kind', row['kind'] if row else 'constraint'), 'name': name,
            'operation': operation, 'lock_target': _lock_target(owner),
            'live_guard': digest(row['native'] if row else owner['native']), 'statement': statement, **extra}


def plan_row(identity, before, after, live, current):
    """Operations for an index/constraint row carrying physical_change, else None."""
    change = after['native'].get('physical_change')
    if change is None or after['kind'] not in {'index', 'constraint'}:
        return None
    wanted = deepcopy(after['native'])
    wanted.pop('physical_change')
    if ('physical_change' in before['native'] or not _equal(before['native'], wanted) or
            any(not _equal(before.get(key), after.get(key)) for key in ('kind', 'path', 'name', 'system'))):
        raise ValueError('Review a physical-schema change separately from other native edits')
    if before.get('system') != 'false':
        raise ValueError('System-managed or unclassified objects cannot be changed')
    action = change.get('action')
    if live is None:
        if action == 'drop':
            return [], 1
        # A replacement gets a new OID: converged when the owner already has the
        # wanted object under the wanted name with the wanted definition.
        baseline_found = extract(before, current['rows'])
        if action in {'replace', 'rename'} and baseline_found is not None:
            owner = _owner(before, current)
            existing = _live_by_name(owner, baseline_found['values']['physical_kind'], change.get('name'), current)
            if existing is not None and (action == 'rename' or _same(existing, change.get('definition'), current)):
                return [], 1
        raise ValueError('Native object no longer exists')
    if live['kind'] != before['kind'] or live.get('system') != 'false':
        raise ValueError('Native object identity changed since baseline')
    owner = _owner(live, current)
    if before['kind'] == 'index' and constraint_backed_index(live, current['rows']):
        raise ValueError('This index implements a constraint; edit the constraint instead')
    from ..providers.postgresql.native_admin import _identifier
    from pglast import ast
    found = extract(live, current['rows'])
    baseline_found = extract(before, current['rows'])
    if found is None or baseline_found is None:
        raise ValueError('Native object has no physical-schema vocabulary')
    name = found['values']['physical_name']
    kind = found['values']['physical_kind']
    desired_definition = change.get('definition')
    wanted_name = change.get('name', name)
    converged = False
    if action == 'rename':
        if not isinstance(wanted_name, str) or change.get('from') != baseline_found['values']['physical_name']:
            raise ValueError('Rename needs the exact baseline name mapping')
        converged = name == wanted_name
    elif action == 'replace':
        converged = name == wanted_name and _same(live, desired_definition, current)
    if action == 'drop':
        if change.get('confirmation') != baseline_found['values']['physical_name']:
            raise ValueError('Drop confirmation must equal the exact baseline name')
    if converged:
        return [], 1
    if not _equal(found['values'], baseline_found['values']):
        raise ValueError('Native object changed independently since baseline')
    table = owner['native']['sql_identity']
    if action in {'drop', 'replace'} and kind in {'primary-key', 'unique'} and _dependents(live, current):
        raise ValueError('Foreign keys depend on this key; change them in the same reviewed change set')
    operations = []
    if action == 'rename':
        if _live_by_name(owner, kind, wanted_name, current) or (kind in {'index', 'primary-key', 'unique'} and
                                                              _relation_named(owner, wanted_name, current)):
            raise ValueError('Rename destination is already a live object')
        if before['kind'] == 'index':
            statement = _checked('ALTER INDEX ' + _identifier(owner['native']['schema'], 'schema') + '.' +
                                 _identifier(name, 'index') + ' RENAME TO ' + _identifier(wanted_name, 'index'), ast.RenameStmt)
        else:
            statement = _checked('ALTER TABLE ONLY ' + table + ' RENAME CONSTRAINT ' + _identifier(name, 'constraint') +
                                 ' TO ' + _identifier(wanted_name, 'constraint'), ast.RenameStmt)
        return [_operation(owner, live, 'rename_' + before['kind'], statement, wanted_name,
                           before_name=name, after_name=wanted_name)], 0
    drop_statement = _checked(
        'DROP INDEX ' + _identifier(owner['native']['schema'], 'schema') + '.' + _identifier(name, 'index') + ' RESTRICT'
        if before['kind'] == 'index' else
        'ALTER TABLE ONLY ' + table + ' DROP CONSTRAINT ' + _identifier(name, 'constraint') + ' RESTRICT',
        ast.DropStmt if before['kind'] == 'index' else ast.AlterTableStmt)
    if action == 'drop':
        return [_operation(owner, live, 'drop_' + before['kind'], drop_statement, name,
                           destructive=True, confirmation=change['confirmation'])], 0
    if action != 'replace':
        raise ValueError('Unsupported physical-schema action')
    if not baseline_found['replaceable'] or not found['replaceable']:
        raise ValueError('This object has native properties (ordering, operator classes, expressions, deferrability, '
                         'partial validation or inherited state) outside the vocabulary; edit it natively')
    if desired_definition.get('physical_kind') != kind:
        raise ValueError('The physical kind of an existing object cannot change')
    if desired_definition.get('referenced'):
        _check_foreign_target(desired_definition, current)
    if wanted_name != name and (_live_by_name(owner, kind, wanted_name, current) or _relation_named(owner, wanted_name, current)):
        raise ValueError('Replacement name is already a live object')
    add_statement = _add_statement(owner, kind, wanted_name, desired_definition)
    operations.append(_operation(owner, live, 'drop_' + before['kind'], drop_statement, name, replacement=True))
    operations.append(_operation(owner, live, 'add_' + before['kind'], add_statement, wanted_name,
                                 resource_id=identity + ':replacement'))
    return operations, 0


def table_additions(identity, before, after, live, current, desired):
    """Reviewed operations for add_indexes/add_constraints drafts on a table.

    Returns (operations, converged, after_without_drafts) or None when there are none."""
    native = after['native']
    if 'add_indexes' not in native and 'add_constraints' not in native:
        return None
    stripped = deepcopy(after)
    drafts = [('index', item) for item in stripped['native'].pop('add_indexes', [])] + \
             [(item['definition']['physical_kind'], item) for item in stripped['native'].pop('add_constraints', [])]
    if ('add_indexes' in before['native'] or 'add_constraints' in before['native'] or
            before['kind'] != 'table' or live is None or live['kind'] != 'table' or
            before.get('system') != 'false' or live.get('system') != 'false' or not drafts or len(drafts) > 64):
        raise ValueError('Physical additions require a bounded draft list on an unchanged ordinary user table')
    owner = _owner_table(live)
    if (live['native']['catalog_row']['relname'] != before['native']['catalog_row']['relname'] or
            after['native']['catalog_row']['relname'] != before['native']['catalog_row']['relname']):
        raise ValueError('Review a table rename separately from physical additions')
    added = [item['definition']['name'] for item in native.get('add_columns', []) if isinstance(item, dict) and
             isinstance(item.get('definition'), dict)]
    operations, converged, seen, ids = [], 0, set(), set()
    for kind, item in drafts:
        if set(item) != {'resource_id', 'name', 'definition'}:
            raise ValueError('Physical addition requires a draft identity, name and definition')
        reference, name, definition = item['resource_id'], item['name'], item['definition']
        if (not isinstance(reference, str) or not reference.startswith('postgresql:new:') or reference in ids or
                reference in desired['rows'] or (kind, name) in seen):
            raise ValueError('Physical addition requires a distinct canonical draft UUID and unique name')
        ids.add(reference)
        seen.add((kind, name))
        existing = _live_by_name(owner, kind, name, current)
        if existing is not None:
            if _same(existing, definition, current):
                converged += 1
                continue
            raise ValueError('A different native object already has this name on the table: ' + name)
        if _relation_named(owner, name, current) and kind in {'index', 'primary-key', 'unique'}:
            raise ValueError('A native relation already occupies the index name: ' + name)
        if kind == 'primary-key' and any(row['kind'] == 'constraint' and _owner_oid(row) == str(owner['native']['oid']) and
                                         row['native']['catalog_row'].get('contype') == 'p' for row in current['rows'].values()):
            raise ValueError('The table already has a PRIMARY KEY')
        if definition.get('referenced'):
            _check_foreign_target(definition, current)
        statement = _add_statement(owner, kind, name, definition, added)
        operations.append(_operation(owner, None, 'add_' + ('index' if kind == 'index' else 'constraint'), statement, name,
                                     resource_id=reference, kind='index' if kind == 'index' else 'constraint',
                                     parent_resource_id=identity))
    return operations, converged, stripped

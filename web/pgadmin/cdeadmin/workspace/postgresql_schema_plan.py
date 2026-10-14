"""Three-way PostgreSQL metadata previews. No database writes or SQL imports."""
from copy import deepcopy
from .firebird_catalog_import import _equal
from .firebird_schema_plan import digest

COMMENT_TYPES = {
    'schema': 'SCHEMA', 'table': 'TABLE', 'partitioned-table': 'TABLE',
    'foreign-table': 'FOREIGN TABLE', 'view': 'VIEW', 'materialized-view': 'MATERIALIZED VIEW',
    'index': 'INDEX', 'partitioned-index': 'INDEX', 'sequence': 'SEQUENCE',
    'type': 'TYPE', 'domain': 'DOMAIN', 'function': 'FUNCTION', 'procedure': 'PROCEDURE',
    'window-function': 'FUNCTION',
    'aggregate': 'AGGREGATE', 'constraint': 'CONSTRAINT', 'trigger': 'TRIGGER',
    'rule': 'RULE', 'policy': 'POLICY', 'extension': 'EXTENSION', 'collation': 'COLLATION',
    'conversion': 'CONVERSION', 'operator': 'OPERATOR', 'operator-class': 'OPERATOR CLASS',
    'operator-family': 'OPERATOR FAMILY', 'text-search-configuration': 'TEXT SEARCH CONFIGURATION',
    'text-search-dictionary': 'TEXT SEARCH DICTIONARY', 'text-search-parser': 'TEXT SEARCH PARSER',
    'text-search-template': 'TEXT SEARCH TEMPLATE', 'extended-statistics': 'STATISTICS',
    'language': 'LANGUAGE', 'event-trigger': 'EVENT TRIGGER', 'publication': 'PUBLICATION',
    'subscription': 'SUBSCRIPTION', 'foreign-data-wrapper': 'FOREIGN DATA WRAPPER',
    'foreign-server': 'SERVER', 'access-method': 'ACCESS METHOD',
}


def _application_supported(operations, blockers):
    if blockers or not operations:
        return False
    creations = [operation for operation in operations if operation.get('operation') == 'create']
    alterations = [operation for operation in operations if operation.get('operation') != 'create']
    if any(not operation.get('lock_target') for operation in alterations):
        return False
    schemas = {operation['name'] for operation in creations if operation['kind'] == 'schema'}
    ids = {operation['resource_id'] for operation in creations}
    return all((operation['kind'] == 'schema' or operation['schema'] in schemas or operation.get('schema_guard')) and
        set(operation['dependencies']) <= ids | ({operation['parent_guard']['resource_id']}
            if operation.get('parent_guard') else set()) | ({operation['owner_guard']['resource_id']}
            if operation.get('owner_guard') else set()) for operation in creations)



TABLE_OWNED = {
    'trigger': ('pg_trigger', 'tgrelid', 'tgname', 'TRIGGER'),
    'rule': ('pg_rewrite', 'ev_class', 'rulename', 'RULE'),
    'policy': ('pg_policy', 'polrelid', 'polname', 'POLICY'),
}


def _owned_table(row, model):
    definition = TABLE_OWNED.get(row['kind'])
    if not definition or row['native'].get('catalog') != definition[0] or model is None:
        raise ValueError('Table-owned object requires its exact native catalog')
    facts = row['native'].get('catalog_row', {})
    oid = facts.get(definition[1])
    owner = model['rows'].get('postgresql:pg_class:' + str(oid))
    if (not owner or owner['kind'] != 'table' or owner.get('system') != 'false' or
            owner['native'].get('catalog') != 'pg_class' or str(owner['native'].get('oid')) != str(oid) or
            owner['native'].get('schema') != row['native'].get('schema') or not _lock_target(owner)):
        raise ValueError('Table-owned change requires an exact captured ordinary user table')
    parent = owner['native']
    if (parent.get('catalog_row', {}).get('relhassubclass') or
            parent.get('catalog_row', {}).get('relispartition') or
            parent.get('children', {}).get('pg_inherits') or
            facts.get('tgisinternal') or facts.get('tgconstraint') not in (None, 0, '0') or
            (row['kind'] == 'rule' and facts.get('rulename') == '_RETURN')):
        raise ValueError('System, constraint-owned, inherited or partitioned objects require a separate adapter')
    return owner


def _lock_target(row, model=None):
    if row['kind'] in TABLE_OWNED:
        try:
            return _lock_target(_owned_table(row, model))
        except ValueError:
            # Existing documentary previews can include native objects whose
            # mutations have not been admitted. Keep them preview-only.
            return None
    native = row['native']
    if row['kind'] not in {'table', 'partitioned-table', 'view'} or native.get('catalog') != 'pg_class':
        return None
    schema, name = native.get('schema'), native.get('catalog_row', {}).get('relname')
    if not all(isinstance(value, str) and value and '\x00' not in value for value in (schema, name)):
        return None
    return {'schema': schema, 'name': name, 'oid': native['oid']}


def _literal(value):
    if value is None or value == '':
        return 'NULL'  # PostgreSQL normalizes an empty comment to NULL.
    if not isinstance(value, str) or '\x00' in value or len(value.encode('utf8')) > 1024 * 1024:
        raise ValueError('Comment must be text or null within 1 MiB')
    return "E'" + value.replace('\\', '\\\\').replace("'", "''") + "'"


def _validate_comment(statement):
    from ..providers.postgresql.language import analyze
    if analyze(statement, standard_strings='on')['grammar_valid'] is not True:
        raise ValueError('Qualified PostgreSQL grammar checking is unavailable or rejected this identity')
    from pglast import parse_sql, ast
    parsed = parse_sql(statement)
    if len(parsed) != 1 or not isinstance(parsed[0].stmt, ast.CommentStmt):
        raise ValueError('Native comment statement did not pass grammar validation')


def _rename_relation(identity, before, after, live, current):
    """Only explicit native relname edits carry rename intent."""
    from ..providers.postgresql.native_admin import _identifier
    from ..providers.postgresql.language import analyze
    from pglast import parse_sql, ast
    original, wanted = before['native'], after['native']
    old_name = original.get('catalog_row', {}).get('relname')
    new_name = wanted.get('catalog_row', {}).get('relname')
    if old_name == new_name:
        return None
    if (live is None or before['kind'] not in {'table', 'view'} or
            any(row['kind'] != before['kind'] or row['system'] != 'false'
                for row in (before, after, live))):
        raise ValueError('Rename requires a visible user table or view')
    for name in (old_name, new_name):
        if not isinstance(name, str) or not name or '\x00' in name or len(name.encode()) > 63:
            raise ValueError('Relation name must fit the native 63-byte identifier limit')
    unchanged = deepcopy(wanted)
    unchanged['catalog_row']['relname'] = old_name
    if not _equal(original, unchanged):
        raise ValueError('Review relation rename separately from other native edits')
    native = live['native']
    if (native.get('catalog') != 'pg_class' or original.get('catalog') != 'pg_class' or
            identity != f'postgresql:pg_class:{native.get("oid")}' or
            original.get('oid') != native.get('oid') or
            original.get('schema') != native.get('schema') or not _lock_target(live)):
        raise ValueError('Native relation identity changed since baseline')
    facts = native.get('catalog_row', {})
    if (facts.get('relhassubclass') or facts.get('relispartition') or
            native.get('children', {}).get('pg_inherits')):
        raise ValueError('Rename requires a relation without inheritance or partitions')
    if (after['path'] not in (before['path'], before['path'][:-1] + [new_name]) or
            after['name'] not in (before['name'], new_name) or
            live['path'] != before['path'][:-1] + [facts.get('relname')]):
        raise ValueError('Rename cannot change schema or database scope')
    if facts.get('relname') == new_name:
        return [], 1
    if facts.get('relname') != old_name:
        raise ValueError('Relation was renamed independently since baseline')
    if any(other_id != identity and row['native'].get('catalog') == 'pg_class' and
           row['native'].get('schema') == native['schema'] and
           row['native'].get('catalog_row', {}).get('relname') == new_name
           for other_id, row in current['rows'].items()):
        raise ValueError('Rename destination is already a live relation')
    statement = ('ALTER ' + ('VIEW' if live['kind'] == 'view' else 'TABLE') + ' ' +
                 _identifier(native['schema'], 'schema') + '.' + _identifier(old_name, 'relation') +
                 ' RENAME TO ' + _identifier(new_name, 'relation'))
    if analyze(statement, standard_strings='on')['grammar_valid'] is not True:
        raise ValueError('Generated relation rename failed native grammar validation')
    parsed = parse_sql(statement)
    if len(parsed) != 1 or not isinstance(parsed[0].stmt, ast.RenameStmt):
        raise ValueError('Invalid native relation rename')
    return [{'resource_id': identity, 'kind': live['kind'], 'name': new_name,
             'operation': 'rename_relation', 'lock_target': _lock_target(live),
             'live_guard': digest(native), 'statement': statement}], 0


def _drop_relation(identity, before, after, live, baseline, current):
    if 'drop' not in after.get('native', {}):
        return None
    wanted = deepcopy(after['native'])
    if wanted.pop('drop') is not True or 'drop' in before['native']:
        raise ValueError('Deletion intent must be explicit true on a captured relation')
    owned = before['kind'] in TABLE_OWNED
    if (before['kind'] not in {'table', 'view'} | TABLE_OWNED.keys() or before.get('system') != 'false' or
            any(not _equal(before.get(key), after.get(key)) for key in ('kind', 'path', 'name', 'system')) or
            not _equal(before['native'], wanted)):
        raise ValueError('Review relation deletion separately from other native edits')
    native = before['native']
    catalog = TABLE_OWNED[before['kind']][0] if owned else 'pg_class'
    if identity != f'postgresql:{catalog}:{native.get("oid")}' or native.get('catalog') != catalog or not _lock_target(before, baseline):
        raise ValueError('Deletion requires an exact captured relation identity')
    facts = native.get('catalog_row', {})
    if facts.get('relhassubclass') or facts.get('relispartition') or native.get('children', {}).get('pg_inherits'):
        raise ValueError('Relation deletion requires an ordinary relation without inheritance')
    if live is None:
        return [], 1
    if live.get('system') != 'false' or live['kind'] != before['kind'] or not _equal(live['native'], native):
        raise ValueError('Relation changed independently since the deletion baseline')
    from ..providers.postgresql.native_admin import _identifier
    from ..providers.postgresql.language import analyze
    from pglast import parse_sql, ast
    if owned:
        owner = _owned_table(live, current)
        definition = TABLE_OWNED[before['kind']]
        statement = ('DROP ' + definition[3] + ' ' + _identifier(facts[definition[2]], 'object') +
            ' ON ' + _identifier(owner['native']['schema'], 'schema') + '.' +
            _identifier(owner['native']['catalog_row']['relname'], 'table') + ' RESTRICT')
    else:
        statement = ('DROP ' + ('VIEW' if before['kind'] == 'view' else 'TABLE') + ' ' +
            _identifier(native['schema'], 'schema') + '.' + _identifier(facts['relname'], 'relation') + ' RESTRICT')
    parsed = parse_sql(statement)
    if (analyze(statement, standard_strings='on')['grammar_valid'] is not True or
            len(parsed) != 1 or not isinstance(parsed[0].stmt, ast.DropStmt)):
        raise ValueError('Generated relation deletion failed native grammar validation')
    return [{'resource_id': identity, 'kind': before['kind'], 'name': before['name'],
        'operation': 'drop_table_owned' if owned else 'drop_relation', 'lock_target': _lock_target(live, current),
        'live_guard': digest(native), 'statement': statement}], 0


def _rename_table_owned(identity, before, after, live, current):
    definition = TABLE_OWNED.get(before['kind'])
    if not definition:
        return None
    catalog, owner_field, name_field, keyword = definition
    original, wanted = before['native'], after['native']
    old_name = original.get('catalog_row', {}).get(name_field)
    new_name = wanted.get('catalog_row', {}).get(name_field)
    if old_name == new_name:
        return None
    from ..providers.postgresql.native_admin import _identifier
    from ..providers.postgresql.language import analyze
    from pglast import parse_sql, ast
    for name in (old_name, new_name):
        if not isinstance(name, str) or not name or '\x00' in name or len(name.encode('utf8')) > 63:
            raise ValueError('Table-owned name must fit the native 63-byte identifier limit')
    unchanged = deepcopy(wanted)
    unchanged['catalog_row'][name_field] = old_name
    if (not _equal(original, unchanged) or live is None or
            any(row['kind'] != before['kind'] or row.get('system') != 'false' for row in (before, after, live))):
        raise ValueError('Review table-owned rename separately from other native edits')
    native = live['native']
    facts = native.get('catalog_row', {})
    if (original.get('catalog') != catalog or native.get('catalog') != catalog or
            identity != f'postgresql:{catalog}:{native.get("oid")}' or original.get('oid') != native.get('oid') or
            original.get('schema') != native.get('schema') or
            str(original['catalog_row'].get(owner_field)) != str(facts.get(owner_field))):
        raise ValueError('Table-owned identity or ownership changed since baseline')
    owner = _owned_table(live, current)
    if (after['name'] not in (before['name'], new_name) or
            after['path'] not in (before['path'], before['path'][:-1] + [new_name])):
        raise ValueError('Table-owned rename cannot change schema or database scope')
    if facts.get(name_field) == new_name:
        return [], 1
    if facts.get(name_field) != old_name:
        raise ValueError('Table-owned object was independently renamed')
    if any(other_id != identity and row['native'].get('catalog') == catalog and
           str(row['native'].get('catalog_row', {}).get(owner_field)) == str(facts[owner_field]) and
           row['native'].get('catalog_row', {}).get(name_field) == new_name
           for other_id, row in current['rows'].items()):
        raise ValueError('Rename destination already exists on the owning table')
    statement = ('ALTER ' + keyword + ' ' + _identifier(old_name, 'object') + ' ON ' +
        _identifier(owner['native']['schema'], 'schema') + '.' +
        _identifier(owner['native']['catalog_row']['relname'], 'table') +
        ' RENAME TO ' + _identifier(new_name, 'object'))
    parsed = parse_sql(statement)
    if (analyze(statement, standard_strings='on')['grammar_valid'] is not True or
            len(parsed) != 1 or not isinstance(parsed[0].stmt, ast.RenameStmt)):
        raise ValueError('Generated table-owned rename failed native grammar validation')
    return [{'resource_id': identity, 'kind': before['kind'], 'name': new_name,
        'operation': 'rename_table_owned', 'lock_target': _lock_target(owner),
        'live_guard': digest(native), 'statement': statement}], 0


def _table_owned_enabled(identity, before, after, live, current):
    field = {'trigger': 'tgenabled', 'rule': 'ev_enabled'}.get(before['kind'])
    if field is None:
        return None
    original, wanted = before['native'], after['native']
    old = original.get('catalog_row', {}).get(field)
    new = wanted.get('catalog_row', {}).get(field)
    if old == new:
        return None
    clauses = {'O': 'ENABLE', 'D': 'DISABLE', 'R': 'ENABLE REPLICA', 'A': 'ENABLE ALWAYS'}
    if not isinstance(old, str) or not isinstance(new, str) or old not in clauses or new not in clauses:
        raise ValueError('Native activation state must be O, D, R or A')
    unchanged = deepcopy(wanted)
    unchanged['catalog_row'][field] = old
    if (not _equal(original, unchanged) or live is None or
            any(not _equal(before.get(key), after.get(key))
                for key in ('kind', 'name', 'path', 'system', 'resource_id')) or
            any(row.get('system') != 'false' or row['kind'] != before['kind']
                for row in (before, after, live))):
        raise ValueError('Review activation separately from other native edits')
    catalog, _, name_field, keyword = TABLE_OWNED[before['kind']]
    native = live['native']
    if (original.get('catalog') != catalog or native.get('catalog') != catalog or
            identity != f'postgresql:{catalog}:{native.get("oid")}' or
            original.get('oid') != native.get('oid')):
        raise ValueError('Activation requires the original native object identity')
    live_state = native.get('catalog_row', {}).get(field)
    unchanged_live = deepcopy(native)
    unchanged_live.setdefault('catalog_row', {})[field] = old
    if not _equal(original, unchanged_live):
        raise ValueError('Native definition changed since activation baseline')
    owner = _owned_table(live, current)
    if live_state == new:
        return [], 1
    if live_state != old:
        raise ValueError('Native activation state was independently changed')
    from ..providers.postgresql.native_admin import _identifier
    from ..providers.postgresql.language import analyze
    from pglast import parse_sql, ast
    statement = ('ALTER TABLE ONLY ' + _identifier(owner['native']['schema'], 'schema') + '.' +
        _identifier(owner['native']['catalog_row']['relname'], 'table') + ' ' +
        clauses[new] + ' ' + keyword + ' ' +
        _identifier(native['catalog_row'][name_field], 'object'))
    parsed = parse_sql(statement)
    if (analyze(statement, standard_strings='on')['grammar_valid'] is not True or
            len(parsed) != 1 or not isinstance(parsed[0].stmt, ast.AlterTableStmt)):
        raise ValueError('Generated activation change failed native grammar validation')
    return [{'resource_id': identity, 'kind': before['kind'], 'name': live['name'],
        'operation': 'set_table_owned_enabled', 'lock_target': _lock_target(owner),
        'live_guard': digest(native), 'statement': statement}], 0


def _row_security(identity, before, after, live):
    flags = ('relrowsecurity', 'relforcerowsecurity')
    original, wanted = before['native'], after['native']
    old_facts, desired_facts = original.get('catalog_row', {}), wanted.get('catalog_row', {})
    changed = [flag for flag in flags if not _equal(old_facts.get(flag), desired_facts.get(flag))]
    if not changed:
        return None
    if (live is None or any(row['kind'] != 'table' or row.get('system') != 'false'
            for row in (before, after, live)) or
            any(not _equal(before.get(key), after.get(key))
                for key in ('kind', 'name', 'path', 'system', 'resource_id'))):
        raise ValueError('Row-security switches require the original ordinary user table')
    unchanged = deepcopy(wanted)
    for flag in flags:
        if type(old_facts.get(flag)) is not bool or type(desired_facts.get(flag)) is not bool:
            raise ValueError('Native row-security switches must be boolean')
        unchanged['catalog_row'][flag] = old_facts[flag]
    if not _equal(original, unchanged):
        raise ValueError('Review row-security switches separately from other native edits')
    native = live['native']
    if (original.get('catalog') != 'pg_class' or native.get('catalog') != 'pg_class' or
            identity != f'postgresql:pg_class:{native.get("oid")}' or original.get('oid') != native.get('oid') or
            not _lock_target(live)):
        raise ValueError('Row-security switches require the original native table identity')
    facts = native.get('catalog_row', {})
    if facts.get('relhassubclass') or facts.get('relispartition') or native.get('children', {}).get('pg_inherits'):
        raise ValueError('Inherited or partitioned row security requires a separate adapter')
    unchanged_live = deepcopy(native)
    for flag in changed:
        if type(facts.get(flag)) is not bool:
            raise ValueError('Live row-security switch is unavailable')
        unchanged_live['catalog_row'][flag] = old_facts[flag]
    if not _equal(original, unchanged_live):
        raise ValueError('Native table changed since row-security baseline')
    from ..providers.postgresql.native_admin import _identifier
    from ..providers.postgresql.language import analyze
    from pglast import parse_sql, ast
    prefix = 'ALTER TABLE ONLY ' + _identifier(native['schema'], 'schema') + '.' + _identifier(facts['relname'], 'table')
    operations, converged = [], 0
    for flag in changed:
        if facts[flag] == desired_facts[flag]:
            converged += 1
            continue
        if flag == 'relrowsecurity':
            clause = 'ENABLE' if desired_facts[flag] else 'DISABLE'
        else:
            clause = 'FORCE' if desired_facts[flag] else 'NO FORCE'
        statement = prefix + ' ' + clause + ' ROW LEVEL SECURITY'
        parsed = parse_sql(statement)
        if (analyze(statement, standard_strings='on')['grammar_valid'] is not True or
                len(parsed) != 1 or not isinstance(parsed[0].stmt, ast.AlterTableStmt)):
            raise ValueError('Generated row-security switch failed native grammar validation')
        operations.append({'resource_id': identity, 'kind': 'table', 'name': live['name'],
            'operation': 'set_row_security', 'field': flag, 'lock_target': _lock_target(live),
            'live_guard': digest(native), 'statement': statement})
    return operations, converged


def _add_columns(identity, before, after, live, desired):
    import uuid
    from .postgresql_creation import column_definition
    if 'add_columns' not in after.get('native', {}):
        return None
    wanted = deepcopy(after['native'])
    drafts = wanted.pop('add_columns')
    if ('add_columns' in before['native'] or not _equal(wanted, before['native']) or
            any(not _equal(before.get(key), after.get(key)) for key in ('name', 'kind', 'path', 'system'))):
        raise ValueError('Review column additions separately from other table edits')
    if (live is None or before['kind'] != 'table' or live['kind'] != 'table' or
            before.get('system') != 'false' or live.get('system') != 'false' or
            not _equal(before['native'], live['native']) or not _lock_target(live)):
        raise ValueError('Column addition requires unchanged ordinary user-table metadata')
    native = live['native']
    facts = native.get('catalog_row', {})
    if (identity != f'postgresql:pg_class:{native.get("oid")}' or
            facts.get('relhassubclass') or facts.get('relispartition') or
            native.get('children', {}).get('pg_inherits')):
        raise ValueError('Column addition requires an exact non-inherited table identity')
    if not isinstance(drafts, list) or not 1 <= len(drafts) <= 1600:
        raise ValueError('Column additions must be a bounded nonempty ordered list')
    names = {item['attname'] for item in native.get('children', {}).get('pg_attribute', [])}
    identifiers, operations = set(), []
    for draft in drafts:
        if not isinstance(draft, dict) or set(draft) != {'resource_id', 'definition'}:
            raise ValueError('Column addition requires a draft identity and native definition')
        reference = draft['resource_id']
        if (not isinstance(reference, str) or not reference.startswith('postgresql:new:') or
                str(uuid.UUID(reference[15:])) != reference[15:] or reference in identifiers or
                reference in desired['rows']):
            raise ValueError('Column addition requires a distinct canonical draft UUID')
        definition = draft['definition']
        rendered = column_definition(definition)
        name = definition['name']
        if name in names:
            raise ValueError('Column addition name already exists or is repeated')
        names.add(name)
        identifiers.add(reference)
        statement = 'ALTER TABLE ONLY ' + native['sql_identity'] + ' ADD COLUMN ' + rendered
        from ..providers.postgresql.language import analyze
        if analyze(statement, standard_strings='on')['grammar_valid'] is not True:
            raise ValueError('Generated column addition failed native grammar validation')
        operations.append({'resource_id': reference, 'parent_resource_id': identity,
            'kind': 'column', 'name': name, 'operation': 'add_column',
            'lock_target': _lock_target(live), 'live_guard': digest(native), 'statement': statement})
    return operations


def _drop_column(identity, before, live, old, wanted, current, attributes):
    from ..providers.postgresql.native_admin import _identifier
    native = live['native']
    facts = native.get('catalog_row', {})
    unchanged = deepcopy(wanted)
    if unchanged.pop('drop', None) is not True or 'drop' in old or not _equal(unchanged, old):
        raise ValueError('Review explicit column removal separately from other attribute edits')
    if (before['kind'] != 'table' or live['kind'] != 'table' or
            not _lock_target(live) or before['native'].get('oid') != native.get('oid') or
            facts.get('relhassubclass') or facts.get('relispartition') or
            native.get('children', {}).get('pg_inherits') or old.get('attinhcount', 0) != 0 or
            str(old.get('attrelid')) != str(native['oid'])):
        raise ValueError('Column removal requires an exact ordinary non-inherited table attribute')
    name = old.get('attname')
    quoted = _identifier(name, 'column')
    if current is None:
        if any(item.get('attname') == name for item in attributes.values()):
            raise ValueError('A replacement column occupies the removed attribute name')
        return [], 1
    if not _equal(old, current):
        raise ValueError('Column changed independently since the removal baseline')
    statement = 'ALTER TABLE ONLY ' + native['sql_identity'] + ' DROP COLUMN ' + quoted + ' RESTRICT'
    from ..providers.postgresql.language import analyze
    from pglast import parse_sql, ast
    parsed = parse_sql(statement)
    if (analyze(statement, standard_strings='on')['grammar_valid'] is not True or
            len(parsed) != 1 or not isinstance(parsed[0].stmt, ast.AlterTableStmt)):
        raise ValueError('Generated column removal failed native grammar validation')
    return [{'resource_id': f'postgresql:pg_attribute:{native["oid"]}:{old["attnum"]}',
        'parent_resource_id': identity, 'kind': 'column', 'name': name,
        'operation': 'drop_column', 'lock_target': _lock_target(live),
        'live_guard': digest({'relation_oid': native['oid'], 'attribute': current}),
        'statement': statement}], 0


def _column_comments(identity, before, after, live):
    if live['kind'] not in {'table', 'partitioned-table', 'view', 'materialized-view', 'foreign-table'}:
        raise ValueError('This relation does not admit column comments')
    children = []
    for row in (before, after, live):
        value = deepcopy(row['native'].get('children', {}))
        if not isinstance(value, dict):
            raise ValueError('Native child metadata must be an object')
        attributes = value.pop('pg_attribute', [])
        if not isinstance(attributes, list):
            raise ValueError('Native attributes must be an array')
        mapped = {}
        for attribute in attributes:
            number = attribute.get('attnum') if isinstance(attribute, dict) else None
            if type(number) is not int or number <= 0 or number in mapped:
                raise ValueError('Native attribute identity is invalid or repeated')
            mapped[number] = attribute
        children.append((value, mapped))
    if not _equal(children[0][0], children[1][0]) or list(children[0][1]) != list(children[1][1]):
        raise ValueError('Only comments on existing columns can change in this adapter')
    native = live['native']
    parent = native.get('sql_identity')
    if not isinstance(parent, str) or not parent or native.get('catalog') != 'pg_class':
        raise ValueError('Live relation identity is unavailable')
    operations, converged = [], 0
    for number, old in children[0][1].items():
        wanted = children[1][1][number]
        changes = [key for key in old.keys() | wanted.keys()
                   if (key in old) != (key in wanted) or not _equal(old.get(key), wanted.get(key))]
        if not changes:
            continue
        if 'drop' in wanted:
            dropped, count = _drop_column(identity, before, live, old, wanted,
                children[2][1].get(number), children[2][1])
            operations.extend(dropped)
            converged += count
            continue
        if set(changes) - {'comment', 'attnotnull', 'attname', 'default_expression', 'formatted_type'} or any(key not in wanted for key in changes):
            raise ValueError('Column metadata changes require an additional native adapter')
        current = children[2][1].get(number)
        if (current is None or ('attname' not in changes and current.get('attname') != old.get('attname')) or
                str(current.get('attrelid')) != str(native['oid']) or
                str(old.get('attrelid')) != str(native['oid'])):
            raise ValueError('Native column identity changed since baseline')
        effective_name = current.get('attname')
        if 'attname' in changes:
            if (live['kind'] != 'table' or current.get('attinhcount', 0) != 0 or
                    native.get('catalog_row', {}).get('relhassubclass', False)):
                raise ValueError('Rename requires an ordinary table column without inheritance')
            old_name, new_name, live_name = old.get('attname'), wanted['attname'], current.get('attname')
            for name in (old_name, new_name, live_name):
                if not isinstance(name, str) or not name or '\x00' in name or len(name.encode('utf8')) > 63:
                    raise ValueError('Column name must fit the native 63-byte identifier limit')
            if live_name == new_name:
                converged += 1
            elif live_name != old_name:
                raise ValueError('Column name changed independently since baseline')
            else:
                if any(other_number != number and other.get('attname') == new_name
                       for other_number, other in children[2][1].items()):
                    raise ValueError('Rename destination is already a live column')
                from ..providers.postgresql.native_admin import _identifier
                from ..providers.postgresql.language import analyze
                from pglast import parse_sql, ast
                statement = ('ALTER TABLE ONLY ' + parent + ' RENAME COLUMN ' +
                             _identifier(live_name, 'column') + ' TO ' + _identifier(new_name, 'column'))
                if analyze(statement, standard_strings='on')['grammar_valid'] is not True:
                    raise ValueError('Generated column rename failed native grammar validation')
                parsed = parse_sql(statement)
                if len(parsed) != 1 or not isinstance(parsed[0].stmt, ast.RenameStmt):
                    raise ValueError('Invalid native column rename')
                operations.append({'resource_id': f'postgresql:pg_attribute:{native["oid"]}:{number}',
                    'parent_resource_id': identity, 'kind': 'column', 'name': new_name,
                    'operation': 'rename_column', 'lock_target': _lock_target(live),
                    'before_name': live_name, 'after_name': new_name,
                    'live_guard': digest({'relation_oid': native['oid'], 'attribute': current}),
                    'statement': statement})
            effective_name = new_name
        if 'formatted_type' in changes:
            if (live['kind'] != 'table' or current.get('attinhcount', 0) != 0 or
                    current.get('attgenerated') or current.get('attidentity') or
                    native.get('catalog_row', {}).get('relhassubclass', False) or
                    native.get('catalog_row', {}).get('relispartition', False)):
                raise ValueError('Type changes require an ordinary non-inherited, non-generated table column')
            from ..providers.postgresql.native_admin import _identifier, _type_reference
            values = tuple(item.get('formatted_type') for item in (old, wanted, current))
            for value in values:
                _type_reference(value, 'column type')
            if values[1] == values[2]:
                converged += 1
            elif values[0] != values[2] or any(old.get(key) != current.get(key) for key in ('atttypid', 'atttypmod', 'attcollation')):
                raise ValueError('Column type changed independently since baseline')
            else:
                statement = ('ALTER TABLE ONLY ' + parent + ' ALTER COLUMN ' +
                    _identifier(effective_name, 'column') + ' TYPE ' + _type_reference(values[1], 'column type'))
                from ..providers.postgresql.language import analyze
                from pglast import parse_sql, ast
                if analyze(statement, standard_strings='on')['grammar_valid'] is not True:
                    raise ValueError('Generated column type statement failed native grammar validation')
                parsed = parse_sql(statement)
                if len(parsed) != 1 or not isinstance(parsed[0].stmt, ast.AlterTableStmt):
                    raise ValueError('Invalid native column type statement')
                operations.append({'resource_id': f'postgresql:pg_attribute:{native["oid"]}:{number}',
                    'parent_resource_id': identity, 'kind': 'column', 'name': effective_name,
                    'operation': 'set_type', 'lock_target': _lock_target(live),
                    'before_type': values[2], 'after_type': values[1],
                    'live_guard': digest({'relation_oid': native['oid'], 'attribute': current}), 'statement': statement})
        if 'attnotnull' in changes:
            if live['kind'] != 'table' or current.get('attinhcount', 0) != 0:
                raise ValueError('Nullability changes require an ordinary, non-inherited table column')
            values = tuple(item.get('attnotnull') for item in (old, wanted, current))
            if any(type(value) is not bool for value in values):
                raise ValueError('Native nullability values must be explicit booleans')
            if values[1] == values[2]:
                converged += 1
            elif values[0] != values[2]:
                raise ValueError('Column nullability changed independently since baseline')
            else:
                from ..providers.postgresql.native_admin import _identifier
                name = effective_name
                statement = 'ALTER TABLE ONLY ' + parent + ' ALTER COLUMN ' + _identifier(name, 'column')
                statement += ' SET NOT NULL' if values[1] else ' DROP NOT NULL'
                from ..providers.postgresql.language import analyze
                from pglast import parse_sql, ast
                if analyze(statement, standard_strings='on')['grammar_valid'] is not True:
                    raise ValueError('Generated nullability statement failed native grammar validation')
                parsed = parse_sql(statement)
                if len(parsed) != 1 or not isinstance(parsed[0].stmt, ast.AlterTableStmt):
                    raise ValueError('Invalid native nullability statement')
                operations.append({'resource_id': f'postgresql:pg_attribute:{native["oid"]}:{number}',
                    'parent_resource_id': identity, 'kind': 'column', 'name': name,
                    'operation': 'set_nullability', 'lock_target': _lock_target(live),
                    'before_not_null': values[2], 'after_not_null': values[1],
                    'live_guard': digest({'relation_oid': native['oid'], 'attribute': current}), 'statement': statement})
        if 'default_expression' in changes:
            if (live['kind'] != 'table' or current.get('attinhcount', 0) != 0 or
                    current.get('attgenerated') or current.get('attidentity') or
                    native.get('catalog_row', {}).get('relhassubclass', False) or
                    any('default_expression' not in item for item in (old, wanted, current))):
                raise ValueError('Defaults require a freshly captured ordinary non-generated table column')
            from .postgresql_creation import expression
            values = tuple(item['default_expression'] for item in (old, wanted, current))
            for value in values:
                if value is not None:
                    expression(value)
            if values[1] == values[2]:
                converged += 1
            elif values[0] != values[2]:
                raise ValueError('Column default changed independently since baseline')
            else:
                from ..providers.postgresql.native_admin import _identifier
                from ..providers.postgresql.language import analyze
                from pglast import parse_sql, ast
                statement = 'ALTER TABLE ONLY ' + parent + ' ALTER COLUMN ' + _identifier(effective_name, 'column')
                statement += ' DROP DEFAULT' if values[1] is None else ' SET DEFAULT ' + expression(values[1])
                if analyze(statement, standard_strings='on')['grammar_valid'] is not True:
                    raise ValueError('Generated default statement failed native grammar validation')
                parsed = parse_sql(statement)
                if len(parsed) != 1 or not isinstance(parsed[0].stmt, ast.AlterTableStmt):
                    raise ValueError('Invalid native default statement')
                operations.append({'resource_id': f'postgresql:pg_attribute:{native["oid"]}:{number}',
                    'parent_resource_id': identity, 'kind': 'column', 'name': effective_name,
                    'operation': 'set_default', 'lock_target': _lock_target(live),
                    'before_default': values[2], 'after_default': values[1],
                    'live_guard': digest({'relation_oid': native['oid'], 'attribute': current}), 'statement': statement})
        if 'comment' not in changes:
            continue
        for value in (old.get('comment'), wanted['comment'], current.get('comment')):
            _literal(value)
        values = tuple(value or None for value in (old.get('comment'), wanted['comment'], current.get('comment')))
        if _equal(values[1], values[2]):
            converged += 1
            continue
        if not _equal(values[0], values[2]):
            raise ValueError('Column comment changed independently since baseline')
        name = effective_name
        if not isinstance(name, str) or not name or '\x00' in name:
            raise ValueError('Live column name is unavailable')
        quoted = '"' + name.replace('"', '""') + '"'
        statement = f'COMMENT ON COLUMN {parent}.{quoted} IS ' + _literal(wanted['comment'])
        _validate_comment(statement)
        operations.append({'resource_id': f'postgresql:pg_attribute:{native["oid"]}:{number}',
            'parent_resource_id': identity, 'kind': 'column', 'name': name, 'lock_target': _lock_target(live),
            'before_comment': deepcopy(values[2]), 'after_comment': deepcopy(values[1]),
            'live_guard': digest({'relation_oid': native['oid'], 'attribute': current}), 'statement': statement})
    return operations, converged


def build_plan(baseline, desired, current):
    for document in (baseline, desired, current):
        if document['provenance'].get('mapping') != 'scratchrobin.postgresql.catalog@1':
            raise ValueError('PostgreSQL native mapping is required')
        for field in ('endpoint_id', 'database_target_id'):
            if not document['provenance'].get(field) or document['provenance'][field] != current['provenance'][field]:
                raise ValueError('Plan documents belong to a different endpoint or database')
    operations, blockers = [], []
    from .postgresql_creation import creation, order_creations
    from ..providers.postgresql.native_admin import PostgreSQLNativeAdminError
    counts = {'unchanged': 0, 'converged': 0, 'preserved_live_changes': 0, 'proposed_creations': 0}
    for identity in sorted(baseline['rows'].keys() | desired['rows'].keys()):
        before, after, live = (document['rows'].get(identity) for document in (baseline, desired, current))
        try:
            if after is None:
                raise ValueError('Missing desired object is not deletion intent')
            if before is None:
                operations.append(creation(identity, after))
                counts['proposed_creations'] += 1
                continue
            additions = _add_columns(identity, before, after, live, desired)
            if additions is not None:
                operations.extend(additions)
                counts['proposed_creations'] += len(additions)
                continue
            dropped = _drop_relation(identity, before, after, live, baseline, current)
            if dropped is not None:
                operations.extend(dropped[0])
                counts['converged'] += dropped[1]
                continue
            renamed = _rename_table_owned(identity, before, after, live, current)
            if renamed is not None:
                operations.extend(renamed[0])
                counts['converged'] += renamed[1]
                continue
            renamed = _rename_relation(identity, before, after, live, current)
            if renamed is not None:
                operations.extend(renamed[0])
                counts['converged'] += renamed[1]
                continue
            activation = _table_owned_enabled(identity, before, after, live, current)
            if activation is not None:
                operations.extend(activation[0])
                counts['converged'] += activation[1]
                continue
            security = _row_security(identity, before, after, live)
            if security is not None:
                operations.extend(security[0])
                counts['converged'] += security[1]
                continue
            if any(not _equal(before.get(key), after.get(key)) for key in ('kind', 'path', 'system')):
                raise ValueError('Object kind, path or system identity changed')
            changes = [key for key in before['native'].keys() | after['native'].keys()
                       if not _equal(before['native'].get(key), after['native'].get(key)) or
                       (key in before['native']) != (key in after['native'])]
            if not changes:
                counts['unchanged'] += 1
                if live and not _equal(before['native'], live['native']):
                    counts['preserved_live_changes'] += 1
                continue
            if set(changes) - {'comment', 'children'}:
                raise ValueError('Native fields require an additional generation adapter: ' + ', '.join(sorted(changes)))
            if 'comment' in changes and 'comment' not in after['native']:
                raise ValueError('Removing a field is not a comment deletion; use explicit null')
            if live is None:
                raise ValueError('Native object no longer exists')
            if after['system'] != 'false' or live['system'] != 'false':
                raise ValueError('System-managed or unclassified objects cannot be changed')
            for field in ('kind', 'path'):
                if not _equal(before[field], live[field]):
                    raise ValueError('Native object identity changed since baseline')
            native = live['native']
            if identity != f"postgresql:{native.get('catalog')}:{native.get('oid')}":
                raise ValueError('Live catalog address is inconsistent')
            column_operations, column_converged = (_column_comments(identity, before, after, live)
                if 'children' in changes else ([], 0))
            if 'comment' not in changes:
                operations.extend(column_operations)
                counts['converged'] += column_converged
                continue
            for item in (before, after, live):
                _literal(item['native'].get('comment'))
            old_value, new_value, live_value = (item['native'].get('comment') or None for item in (before, after, live))
            literal = _literal(after['native']['comment'])
            if _equal(new_value, live_value):
                counts['converged'] += 1 + column_converged
                operations.extend(column_operations)
                continue
            if not _equal(old_value, live_value):
                raise ValueError('Comment changed independently since baseline')
            keyword = COMMENT_TYPES.get(live['kind'])
            native_identity = native.get('sql_identity')
            if live['kind'] == 'constraint' and native.get('catalog_row', {}).get('contypid') not in (None, 0, '0'):
                facts = native['catalog_row']
                domain = current['rows'].get('postgresql:pg_type:' + str(facts['contypid']))
                if not domain or not domain['native'].get('sql_identity'):
                    raise ValueError('Domain constraint requires the live domain identity')
                constraint_name = facts.get('conname')
                if not isinstance(constraint_name, str) or not constraint_name or '\x00' in constraint_name:
                    raise ValueError('Domain constraint name is unavailable')
                native_identity = ('"' + constraint_name.replace('"', '""') + '" ON DOMAIN ' +
                                   domain['native']['sql_identity'])
            if not keyword or not isinstance(native_identity, str) or not native_identity:
                raise ValueError('Native comment identity is unavailable for this object')
            statement = f'COMMENT ON {keyword} {native_identity} IS {literal}'
            _validate_comment(statement)
            operations.extend(column_operations)
            counts['converged'] += column_converged
            operations.append({'resource_id': identity, 'kind': live['kind'], 'name': live['name'],
                'before_comment': deepcopy(live_value), 'after_comment': deepcopy(new_value), 'lock_target': _lock_target(live, current),
                'live_guard': digest(native), 'statement': statement})
        except (ValueError, TypeError, PostgreSQLNativeAdminError) as error:
            blockers.append({'resource_id': identity, 'reason': str(error)})
    try:
        draft_ids = [item['resource_id'] for item in operations if item.get('operation') in {'create', 'add_column'}]
        if len(draft_ids) != len(set(draft_ids)):
            raise ValueError('Creation draft identities must be unique across the whole plan')
        operations = order_creations(operations, current)
    except ValueError as error:
        blockers.append({'resource_id': None, 'reason': str(error)})
    return {'format': 'scratchrobin.postgresql.schema-preview@1',
        'endpoint_id': current['provenance']['endpoint_id'],
        'database_target_id': current['provenance']['database_target_id'],
        'generation': current['provenance']['generation'], 'counts': counts,
        'operations': operations, 'blockers': blockers,
        'ready_for_review': not blockers,
        'execution_sha256': digest(operations),
        'application_supported': _application_supported(operations, blockers),
        'warnings': ['Preview only; no commands have been executed.',
                     'Unmodified live fields are preserved. Missing objects never imply DROP.']}

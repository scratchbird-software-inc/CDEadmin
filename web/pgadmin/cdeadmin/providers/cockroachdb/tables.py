"""CockroachDB tables: create and alter as 26.1.3 accepts them.

Every clause was checked live (docs/en_US/postgresql_wire_parity.rst).
Alter works from the table record (``table_native``): a constraint grid
that changed is diffed against the constraints the record holds, and a
changed column cell becomes the matching ALTER COLUMN clause. What
CockroachDB refuses, or this editor cannot do safely, is refused by name.
"""
import re

from ...sdk.relational import RelationalClientError

GENERATED = ('STORED', 'VIRTUAL')
IDENTITY = ('ALWAYS', 'BY DEFAULT')
FK_ACTIONS = ('NO ACTION', 'RESTRICT', 'CASCADE', 'SET NULL', 'SET DEFAULT')
CONSTRAINT_LISTS = {
    'primary_key': 'PRIMARY KEY', 'unique_constraints': 'UNIQUE',
    'foreign_keys': 'FOREIGN KEY', 'check_constraints': 'CHECK',
}
TTL_KEYS = ('ttl_expire_after', 'ttl_expiration_expression', 'ttl_job_cron')
COLUMN_KEYS = {
    'name', 'type', 'nullable', 'default', 'unique', 'primary_key',
    'generated_kind', 'generated_expression', 'identity', 'not_visible',
    'on_update', 'family', 'comment',
}
CONSTRAINT_KEYS = {
    'name', 'kind', 'columns', 'references_table', 'references_columns',
    'on_delete', 'on_update', 'expression',
}
CREATE_KEYS = {'name', 'parent', 'columns', 'constraints', 'comment',
               *CONSTRAINT_LISTS, *TTL_KEYS}
ALTER_KEYS = {'add_columns', 'drop_columns', 'rename_columns',
              'alter_columns', 'comment', 'confirmation',
              *CONSTRAINT_LISTS, *TTL_KEYS}
# Column cells an existing column cannot take here: key membership is the
# Constraints tab's, and a column cannot move between families.
_LOCKED = {'unique': 'use the Unique grid', 'primary_key':
           'use the Primary key grid', 'family':
           'a column cannot move to another family',
           'generated_expression': 'drop and re-add the column'}


def _blank(value):
    return value is None or value == ''


def _choice(value, allowed, label):
    if _blank(value):
        return ''
    if value not in allowed:
        raise RelationalClientError(
            f'{label} must be one of: ' + ', '.join(allowed))
    return value


def _boolean(item, key, default):
    value = item.get(key, default)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise RelationalClientError(f'{key} must be true or false')
    return value


def column_definition(admin, item, adding=False):
    """One column clause; comments are separate statements."""
    if not isinstance(item, dict):
        raise RelationalClientError('column definition must be an object')
    unknown = set(item) - COLUMN_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown column option: ' + ', '.join(sorted(unknown)))
    parts = [admin._quote(item.get('name')),
             admin._safe_fragment(item.get('type'), 'column type')]
    generated = _choice(item.get('generated_kind'), GENERATED,
                        'generated column')
    identity = _choice(item.get('identity'), IDENTITY, 'identity')
    has_default = not _blank(item.get('default'))
    if generated and (identity or has_default or not _blank(
            item.get('on_update'))):
        raise RelationalClientError(
            'a computed column takes no default, identity or ON UPDATE')
    if identity and has_default:
        raise RelationalClientError(
            'an identity column takes no default expression')
    if generated == 'VIRTUAL' and not _blank(item.get('family')):
        # Live: "virtual computed column cannot be part of a family".
        raise RelationalClientError(
            'a virtual computed column cannot belong to a family')
    if not _boolean(item, 'nullable', True):
        parts.append('NOT NULL')
    if _boolean(item, 'not_visible', False):
        parts.append('NOT VISIBLE')
    if has_default:
        parts += ['DEFAULT', admin._safe_fragment(item['default'],
                                                  'default')]
    if identity:
        parts.append(f'GENERATED {identity} AS IDENTITY')
    if generated:
        parts.append('AS (' + admin._safe_fragment(
            item.get('generated_expression'), 'computed expression') +
            f') {generated}')
    if not _blank(item.get('on_update')):
        parts += ['ON UPDATE', admin._safe_fragment(item['on_update'],
                                                    'ON UPDATE')]
    if _boolean(item, 'unique', False):
        parts.append('UNIQUE')
    if _boolean(item, 'primary_key', False):
        parts.append('PRIMARY KEY')
    if adding and not _blank(item.get('family')):
        parts.append('CREATE IF NOT EXISTS FAMILY ' + admin._quote(
            item['family']))
    return ' '.join(parts)


def _constraint_row(admin, kind, item):
    """Normalize one constraint row for SQL and for comparison."""
    if not isinstance(item, dict):
        raise RelationalClientError('constraint must be an object')
    unknown = set(item) - CONSTRAINT_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown constraint option: ' + ', '.join(sorted(unknown)))
    row = {'kind': kind, 'name': item.get('name') or None}
    if kind in {'PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY'}:
        columns = item.get('columns')
        if not isinstance(columns, list) or not columns:
            raise RelationalClientError(f'{kind} needs columns')
        row['columns'] = [admin._identifier(value) for value in columns]
    if kind == 'FOREIGN KEY':
        row['references_table'] = list(admin._option_path(
            item, 'references_table'))
        references = item.get('references_columns')
        if not isinstance(references, list) or len(references) != len(
                row['columns']):
            raise RelationalClientError(
                'a foreign key needs one referenced column per column')
        row['references_columns'] = [admin._identifier(value)
                                     for value in references]
        for key in ('on_delete', 'on_update'):
            row[key] = _choice(item.get(key), FK_ACTIONS,
                               key.replace('_', ' ')) or 'NO ACTION'
    if kind == 'CHECK':
        row['expression'] = _unwrap(admin._safe_fragment(
            item.get('expression'), 'check expression'))
    return row


def _constraint_sql(admin, row):
    prefix = (f'CONSTRAINT {admin._quote(row["name"])} '
              if row.get('name') else '')
    kind = row['kind']
    if kind in {'PRIMARY KEY', 'UNIQUE'}:
        return prefix + kind + ' (' + admin._identifier_list(
            row['columns']) + ')'
    if kind == 'FOREIGN KEY':
        source = (prefix + 'FOREIGN KEY (' + admin._identifier_list(
            row['columns']) + ') REFERENCES ' + admin._qualified(
                row['references_table']) + ' (' + admin._identifier_list(
                    row['references_columns']) + ')')
        for key, phrase in (('on_delete', ' ON DELETE '),
                            ('on_update', ' ON UPDATE ')):
            if row[key] != 'NO ACTION':
                source += phrase + row[key]
        return source
    return f'{prefix}CHECK ({row["expression"]})'


def _constraint_rows(admin, draft):
    rows = []
    for item in draft.get('constraints') or []:
        if not isinstance(item, dict):
            raise RelationalClientError('constraint must be an object')
        kind = str(item.get('kind', '')).upper()
        if kind not in CONSTRAINT_LISTS.values():
            raise RelationalClientError('constraint kind is unsupported')
        rows.append(_constraint_row(
            admin, kind, {k: v for k, v in item.items() if k != 'kind'}))
    for key, kind in CONSTRAINT_LISTS.items():
        for item in draft.get(key) or []:
            rows.append(_constraint_row(admin, kind, item))
    return rows


def _ttl_clauses(admin, values):
    clauses = []
    for key in TTL_KEYS:
        value = values.get(key)
        if not _blank(value):
            if not isinstance(value, str):
                raise RelationalClientError(f'{key} must be text')
            clauses.append(f'{key} = {admin._literal(value)}')
    return clauses


def _comment(admin, target_sql, value, column=False):
    keyword = 'COLUMN' if column else 'TABLE'
    text = 'NULL' if _blank(value) else admin._literal(str(value))
    return {'source': f'COMMENT ON {keyword} {target_sql} IS {text}',
            'parameters': ()}


def create(admin, draft):
    unknown = set(draft) - CREATE_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown table option: ' + ', '.join(sorted(unknown)))
    name = admin._identifier(draft.get('name'))
    table = admin._new_object_name(name, draft)
    columns = draft.get('columns')
    if not isinstance(columns, list) or not columns:
        raise RelationalClientError(
            'table creation requires at least one structured column')
    definitions = [column_definition(admin, item) for item in columns]
    definitions += [_constraint_sql(admin, row)
                    for row in _constraint_rows(admin, draft)]
    families = {}
    for item in columns:
        if not _blank(item.get('family')):
            families.setdefault(item['family'], []).append(item['name'])
    definitions += [f'FAMILY {admin._quote(family)} (' +
                    admin._identifier_list(members) + ')'
                    for family, members in families.items()]
    source = f'CREATE TABLE {table} ({", ".join(definitions)})'
    ttl = _ttl_clauses(admin, draft)
    if ttl:
        source += ' WITH (' + ', '.join(ttl) + ')'
    statements = [{'source': source, 'parameters': ()}]
    if not _blank(draft.get('comment')):
        statements.append(_comment(admin, table, draft['comment']))
    for item in columns:
        if not _blank(item.get('comment')):
            statements.append(_comment(
                admin, f'{table}.{admin._quote(item["name"])}',
                item['comment'], column=True))
    return statements


def _alter_column(admin, table, name, changes):
    """ALTER COLUMN clauses for one column's changed cells, in order."""
    if not isinstance(changes, dict) or not changes:
        raise RelationalClientError('column change is empty')
    for key in changes:
        if key in _LOCKED:
            raise RelationalClientError(
                f'column {name}: {key} cannot change here; {_LOCKED[key]}')
        if key not in COLUMN_KEYS - {'name'}:
            raise RelationalClientError(f'unknown column change: {key}')
    column = admin._quote(name)
    head = f'ALTER TABLE {table} ALTER COLUMN {column} '
    out, unlock = [], False
    if 'generated_kind' in changes:
        if not _blank(changes['generated_kind']):
            raise RelationalClientError(
                f'column {name}: a column becomes computed only when added')
        # Live: STORED becomes a regular column; VIRTUAL is refused.
        out.append(head + 'DROP STORED')
    if 'identity' in changes:
        identity = _choice(changes['identity'], IDENTITY, 'identity')
        if identity:
            out.append(head + f'SET GENERATED {identity}')
        else:
            # Live: refused while schema_locked, which it cannot unlock.
            out.append(head + 'DROP IDENTITY')
            unlock = True
    if not _blank(changes.get('type')):
        out.append(head + 'TYPE ' + admin._safe_fragment(
            changes['type'], 'column type'))
    if 'default' in changes:
        out.append(head + ('DROP DEFAULT' if _blank(changes['default'])
                           else 'SET DEFAULT ' + admin._safe_fragment(
                               changes['default'], 'default')))
    if 'nullable' in changes:
        out.append(head + ('DROP NOT NULL' if _boolean(
            changes, 'nullable', True) else 'SET NOT NULL'))
    if 'on_update' in changes:
        out.append(head + ('DROP ON UPDATE' if _blank(changes['on_update'])
                           else 'SET ON UPDATE ' + admin._safe_fragment(
                               changes['on_update'], 'ON UPDATE')))
    if 'not_visible' in changes:
        out.append(head + ('SET NOT VISIBLE' if _boolean(
            changes, 'not_visible', False) else 'SET VISIBLE'))
    statements = [{'source': source, 'parameters': ()} for source in out]
    if 'comment' in changes:
        statements.append(_comment(admin, f'{table}.{column}',
                                   changes['comment'], column=True))
    return statements, unlock


def _comparable(row):
    return {key: value for key, value in row.items() if key != 'name'}


def _constraint_changes(admin, table, schema_table, draft, native):
    """Drop, add and primary-key statements for the grids that changed."""
    held = [row for row in native.get('constraints') or []]
    drops, adds, warnings = [], [], []
    for key, kind in CONSTRAINT_LISTS.items():
        if key not in draft:
            continue
        # Rows reopened from the record also carry its catalog facts.
        wanted = [_constraint_row(admin, kind, {
            name: value for name, value in item.items()
            if name in CONSTRAINT_KEYS - {'kind'}})
            for item in draft[key] or [] if isinstance(item, dict)]
        current = [row for row in held if row.get('kind') == kind]
        if kind == 'PRIMARY KEY':
            if len(wanted) != 1:
                raise RelationalClientError(
                    'a CockroachDB table keeps exactly one primary key')
            new = wanted[0]
            old = current[0] if current else None
            if old is None or old['columns'] != new['columns']:
                adds.append(f'ALTER TABLE {table} ALTER PRIMARY KEY USING '
                            'COLUMNS (' + admin._identifier_list(
                                new['columns']) + ')')
                warnings.append(
                    'CockroachDB keeps the old primary key columns as a '
                    'UNIQUE index after ALTER PRIMARY KEY.')
            if old and new.get('name') and new['name'] != old['name']:
                adds.append(f'ALTER TABLE {table} RENAME CONSTRAINT '
                            f'{admin._quote(old["name"])} TO '
                            f'{admin._quote(new["name"])}')
            continue
        by_name = {row['name']: row for row in current}
        kept = set()
        for row in wanted:
            old = by_name.get(row['name'])
            if old is not None and _comparable(old) == _comparable(row):
                kept.add(row['name'])
                continue
            adds.append(f'ALTER TABLE {table} ADD ' +
                        _constraint_sql(admin, row))
        for row in current:
            if row['name'] in kept:
                continue
            if kind == 'UNIQUE':
                # Live: DROP CONSTRAINT is refused for UNIQUE.
                drops.append('DROP INDEX ' + admin._qualified(
                    schema_table) + '@' + admin._quote(row['name']) +
                    ' CASCADE')
            else:
                drops.append(f'ALTER TABLE {table} DROP CONSTRAINT '
                             f'{admin._quote(row["name"])}')
    return drops, adds, warnings


def alter(admin, draft, target):
    unknown = set(draft) - ALTER_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown table change: ' + ', '.join(sorted(unknown)))
    native = (target or {}).get('native') or {}
    schema_table = admin._target_path(target)
    table = admin._qualified(schema_table)
    drops, adds, warnings = _constraint_changes(
        admin, table, schema_table, draft, native)
    statements = [{'source': source, 'parameters': ()} for source in drops]
    for name in draft.get('drop_columns') or []:
        statements.append({'source': f'ALTER TABLE {table} DROP COLUMN '
                                     f'{admin._quote(name)}',
                           'parameters': ()})
    for item in draft.get('rename_columns') or []:
        statements.append({'source': (
            f'ALTER TABLE {table} RENAME COLUMN {admin._quote(item["from"])}'
            f' TO {admin._quote(item["to"])}'), 'parameters': ()})
    unlock = False
    for item in draft.get('alter_columns') or []:
        if not isinstance(item, dict):
            raise RelationalClientError('column change must be an object')
        changed, needs = _alter_column(admin, table, item.get('name'),
                                       item.get('changes'))
        statements += changed
        unlock = unlock or needs
    for item in draft.get('add_columns') or []:
        statements.append({'source': (
            f'ALTER TABLE {table} ADD COLUMN '
            f'{column_definition(admin, item, adding=True)}'),
            'parameters': ()})
        if not _blank(item.get('comment')):
            statements.append(_comment(
                admin, f'{table}.{admin._quote(item["name"])}',
                item['comment'], column=True))
    statements += [{'source': source, 'parameters': ()} for source in adds]
    statements += _ttl_changes(admin, table, draft, native)
    if 'comment' in draft and (draft['comment'] or None) != (
            native.get('comment') or None):
        statements.append(_comment(admin, table, draft['comment']))
    if not statements:
        raise RelationalClientError('nothing to change')
    if unlock and native.get('schema_locked'):
        statements = ([{'source': f'ALTER TABLE {table} SET '
                                  '(schema_locked = false)',
                        'parameters': ()}] + statements +
                      [{'source': f'ALTER TABLE {table} SET '
                                  '(schema_locked = true)',
                        'parameters': ()}])
    return statements, warnings


def _ttl_changes(admin, table, draft, native):
    if not any(key in draft for key in TTL_KEYS):
        return []
    wanted = {key: (draft[key] if key in draft else native.get(key))
              for key in TTL_KEYS}
    had = any(not _blank(native.get(key)) for key in TTL_KEYS[:2])
    if _blank(wanted['ttl_expire_after']) and _blank(
            wanted['ttl_expiration_expression']):
        if not _blank(wanted['ttl_job_cron']):
            raise RelationalClientError(
                'a TTL schedule needs an expiry interval or expression')
        return [{'source': f'ALTER TABLE {table} RESET (ttl)',
                 'parameters': ()}] if had else []
    changed = {key: wanted[key] for key in TTL_KEYS
               if key in draft and (draft[key] or None) != (
                   native.get(key) or None)}
    statements = []
    clauses = _ttl_clauses(admin, changed)
    if clauses:
        statements.append({'source': f'ALTER TABLE {table} SET (' +
                                     ', '.join(clauses) + ')',
                           'parameters': ()})
    for key in TTL_KEYS:
        if key in changed and _blank(changed[key]):
            statements.append({'source': f'ALTER TABLE {table} RESET '
                                         f'({key})', 'parameters': ()})
    return statements


def _unwrap(text):
    """Strip outer parentheses pg_constraint and pg_trigger add."""
    text = text.strip()
    while text.startswith('(') and text.endswith(')'):
        depth = 0
        for index, char in enumerate(text):
            depth += char == '('
            depth -= char == ')'
            if depth == 0 and index < len(text) - 1:
                return text
        text = text[1:-1].strip()
    return text


# --- reading SHOW CREATE ALL TABLES -------------------------------------

def _identifier(text, at):
    """(name, next index) for a bare or double-quoted identifier."""
    if text.startswith('"', at):
        out, index = [], at + 1
        while index < len(text):
            if text[index] == '"':
                if text.startswith('""', index):
                    out.append('"')
                    index += 2
                    continue
                return ''.join(out), index + 1
            out.append(text[index])
            index += 1
        raise ValueError('unterminated identifier')
    match = re.compile(r'[^\s.,()"]+').match(text, at)
    if not match:
        raise ValueError('identifier expected')
    return match.group(0), match.end()


def _identifiers(text):
    names, index = [], 0
    while index < len(text):
        if text[index] in ' ,':
            index += 1
            continue
        name, index = _identifier(text, index)
        names.append(name)
    return names


def parse_create(statement):
    """((schema, table), {column: on_update}, [{name, columns}]) or None.

    The statement is CockroachDB's own rendering: one item per line, each
    line tab-indented. ON UPDATE is rendered last on its column line.
    """
    match = re.match(r'CREATE TABLE ', statement)
    if not match:
        return None
    try:
        schema, index = _identifier(statement, match.end())
        table, index = _identifier(statement, index + 1)
    except ValueError:
        return None
    on_update, families = {}, []
    for line in statement.split('\n')[1:]:
        if not line.startswith('\t'):
            continue
        line = line[1:].rstrip(',')
        if line.startswith(('CONSTRAINT ', 'INDEX ', 'UNIQUE INDEX ',
                            'INVERTED INDEX ', 'VECTOR INDEX ')):
            continue
        try:
            if line.startswith('FAMILY '):
                name, at = _identifier(line, len('FAMILY '))
                members = line[at:].strip()
                if members.startswith('(') and members.endswith(')'):
                    families.append({'name': name, 'columns': _identifiers(
                        members[1:-1])})
                continue
            name, at = _identifier(line, 0)
        except ValueError:
            continue
        if ' ON UPDATE ' in line[at:]:
            on_update[name] = _strip_casts(line[at:].rsplit(
                ' ON UPDATE ', 1)[1])
    return (schema, table), on_update, families


def _strip_casts(text):
    """Drop the :::TYPE annotations CockroachDB adds to constants."""
    return re.sub(r":::[A-Z][A-Z0-9_]*(?:\[\])?", '', text).strip()


def parse_reloptions(options):
    """pg_class.reloptions entries ("k='v':::TYPE") as a dict of text."""
    found = {}
    for entry in options or ():
        key, _, value = str(entry).partition('=')
        value = re.sub(r':::[A-Z][A-Z0-9_ ]*$', '', value)
        if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
            value = value[1:-1].replace("''", "'")
        found[key] = value
    return found


def extend_form(form, field, operation):
    """Add CockroachDB's column, foreign-key, TTL and comment fields to the
    shared table form (whose column and constraint editors are typed)."""
    for item in form['fields']:
        editor = item.get('array_editor') or {}
        if item['field_id'] in {'columns', 'add_columns'} and editor:
            editor['fields'] = editor.get('fields', []) + [
                field('generated_kind', 'Computed', 'select', False,
                      'AS (expression) STORED or VIRTUAL.',
                      options=GENERATED),
                field('generated_expression', 'Computed expression', 'text'),
                field('identity', 'Identity', 'select', False,
                      'GENERATED ... AS IDENTITY', options=IDENTITY),
                field('not_visible', 'Not visible', 'boolean', False,
                      'NOT VISIBLE: left out of SELECT *.', False),
                field('on_update', 'On update', 'text', False,
                      'ON UPDATE expression'),
                field('family', 'Column family', 'text', False,
                      'FAMILY; new on an existing table: CREATE IF NOT '
                      'EXISTS FAMILY.'),
                field('comment', 'Comment', 'text'),
            ]
        if item['field_id'] == 'constraints' and 'fields' in editor:
            for key, label in (('on_delete', 'On delete'),
                               ('on_update', 'On update')):
                editor['fields'].append({
                    **field(key, label, 'select', False,
                            default='NO ACTION', options=FK_ACTIONS),
                    'visible_when': {'field_id': 'kind',
                                     'equals': 'FOREIGN KEY'}})
    form['fields'] += [
        field('ttl_expire_after', 'Row TTL: expire after', 'text', False,
              "Row-level TTL interval, for example '30 days'."),
        field('ttl_expiration_expression', 'Row TTL: expiry expression',
              'text', False, 'A TIMESTAMPTZ expression per row.'),
        field('ttl_job_cron', 'Row TTL: deletion schedule', 'text', False,
              "Cron expression, for example '@daily'."),
        field('comment', 'Comment', 'text'),
    ]
    if operation == 'alter':
        form['notes'] = ('Changes to existing columns (alter_columns) and '
                         'the per-kind constraint lists come from the '
                         'table editor; this form adds, drops and renames.')
    return form

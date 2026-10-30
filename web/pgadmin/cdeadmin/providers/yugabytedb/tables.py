"""YugabyteDB YSQL tables: PostgreSQL 15's table surface plus YSQL's own.

Checked live on 2025.2.2.2 (docs/en_US/postgresql_wire_parity.rst):
identity and stored generated columns, collations, deferrable and NOT
VALID constraints, foreign-key actions, partitioning, primary keys with
HASH and ASC/DESC columns, SPLIT INTO / SPLIT AT, tablespaces with replica
placement, colocation. Refused: virtual generated columns, EXCLUDE
constraints. Primary-key and type changes rewrite the table (YSQL warns).

Field ids match the CockroachDB table form where the concept is the same
(providers/cockroachdb/tables.py).
"""
import re

from ...sdk.relational import RelationalClientError

IDENTITY = ('ALWAYS', 'BY DEFAULT')
FK_ACTIONS = ('NO ACTION', 'RESTRICT', 'CASCADE', 'SET NULL', 'SET DEFAULT')
ORDERS = ('ASC', 'DESC')
PARTITIONING = ('RANGE', 'LIST', 'HASH')
CONSTRAINT_LISTS = {
    'primary_key': 'PRIMARY KEY', 'unique_constraints': 'UNIQUE',
    'foreign_keys': 'FOREIGN KEY', 'check_constraints': 'CHECK',
}
COLUMN_KEYS = {'name', 'type', 'nullable', 'default', 'identity',
               'generated_expression', 'collation', 'comment', 'unique',
               'primary_key'}
CONSTRAINT_KEYS = {'name', 'columns', 'hash_columns', 'order',
                   'references_table', 'references_columns', 'on_delete',
                   'on_update', 'deferrable', 'initially_deferred',
                   'expression'}
TABLE_KEYS = {'comment', 'tablespace', 'row_level_security',
              'force_row_level_security'}
CREATE_KEYS = {'name', 'parent', 'columns', 'constraints', 'split_into',
               'split_at', 'colocation', 'partition_by', 'partition_key',
               *CONSTRAINT_LISTS, *TABLE_KEYS}
ALTER_KEYS = {'add_columns', 'drop_columns', 'rename_columns',
              'alter_columns', 'confirmation', *CONSTRAINT_LISTS,
              *TABLE_KEYS}
_LOCKED = {'unique': 'use the Unique grid',
           'primary_key': 'use the Primary key grid'}


def _blank(value):
    return value is None or value == ''


def _choice(value, allowed, label):
    if _blank(value):
        return ''
    if value not in allowed:
        raise RelationalClientError(
            f'{label} must be one of: ' + ', '.join(allowed))
    return value


def _comment(admin, keyword, target, value):
    text = 'NULL' if _blank(value) else admin._literal(str(value))
    return {'source': f'COMMENT ON {keyword} {target} IS {text}',
            'parameters': ()}


def column_definition(admin, item):
    if not isinstance(item, dict):
        raise RelationalClientError('column definition must be an object')
    unknown = set(item) - COLUMN_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown column option: ' + ', '.join(sorted(unknown)))
    parts = [admin._quote(item.get('name')),
             admin._safe_fragment(item.get('type'), 'column type')]
    if not _blank(item.get('collation')):
        parts.append('COLLATE ' + admin._quote(item['collation']))
    identity = _choice(item.get('identity'), IDENTITY, 'identity')
    generated = item.get('generated_expression')
    if not _blank(generated) and (identity or not _blank(
            item.get('default'))):
        raise RelationalClientError(
            'a generated column takes no default or identity')
    if identity and not _blank(item.get('default')):
        raise RelationalClientError(
            'an identity column takes no default expression')
    if item.get('nullable') is False:
        parts.append('NOT NULL')
    if not _blank(item.get('default')):
        parts += ['DEFAULT', admin._safe_fragment(item['default'],
                                                  'default')]
    if identity:
        parts.append(f'GENERATED {identity} AS IDENTITY')
    if not _blank(generated):
        # Live: YSQL (PostgreSQL 15) has STORED generated columns only.
        parts.append('GENERATED ALWAYS AS (' + admin._safe_fragment(
            generated, 'generated expression') + ') STORED')
    if item.get('unique'):
        parts.append('UNIQUE')
    if item.get('primary_key'):
        parts.append('PRIMARY KEY')
    return ' '.join(parts)


def _constraint_row(admin, kind, item):
    if not isinstance(item, dict):
        raise RelationalClientError('constraint must be an object')
    row = {'kind': kind, 'name': item.get('name') or None}
    if kind in {'PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY'}:
        columns = item.get('columns')
        if not isinstance(columns, list) or not columns:
            raise RelationalClientError(f'{kind} needs columns')
        row['columns'] = [admin._identifier(value) for value in columns]
    if kind == 'PRIMARY KEY':
        hashed = [admin._identifier(value)
                  for value in item.get('hash_columns') or []]
        if hashed != row['columns'][:len(hashed)]:
            raise RelationalClientError(
                'HASH columns must be the leading primary key columns')
        row['hash_columns'] = hashed
        row['order'] = _choice(item.get('order'), ORDERS, 'order') or 'ASC'
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
    if kind == 'UNIQUE' and item.get('deferrable'):
        # Live, 2025.2.2.2: "DEFERRABLE unique constraints are not
        # supported yet" (deferrable foreign keys are).
        raise RelationalClientError(
            'YugabyteDB does not support deferrable unique constraints')
    if kind == 'FOREIGN KEY':
        row['deferrable'] = bool(item.get('deferrable'))
        row['initially_deferred'] = bool(item.get('initially_deferred'))
        if row['initially_deferred'] and not row['deferrable']:
            raise RelationalClientError(
                'only a deferrable constraint can start deferred')
    if kind == 'CHECK':
        row['expression'] = _unwrap(admin._safe_fragment(
            item.get('expression'), 'check expression'))
    return row


def _key_list(admin, row):
    hashed = row.get('hash_columns') or []
    parts = []
    if hashed:
        parts.append(('(' + admin._identifier_list(hashed) + ') HASH')
                     if len(hashed) > 1 else
                     f'{admin._quote(hashed[0])} HASH')
    parts += [f'{admin._quote(column)} {row.get("order") or "ASC"}'
              for column in row['columns'][len(hashed):]]
    return ', '.join(parts)


def _constraint_sql(admin, row):
    prefix = (f'CONSTRAINT {admin._quote(row["name"])} '
              if row.get('name') else '')
    kind = row['kind']
    if kind == 'PRIMARY KEY':
        return f'{prefix}PRIMARY KEY ({_key_list(admin, row)})'
    if kind == 'UNIQUE':
        source = prefix + 'UNIQUE (' + admin._identifier_list(
            row['columns']) + ')'
    elif kind == 'FOREIGN KEY':
        source = (prefix + 'FOREIGN KEY (' + admin._identifier_list(
            row['columns']) + ') REFERENCES ' + admin._qualified(
                row['references_table']) + ' (' + admin._identifier_list(
                    row['references_columns']) + ')')
        for key, phrase in (('on_delete', ' ON DELETE '),
                            ('on_update', ' ON UPDATE ')):
            if row[key] != 'NO ACTION':
                source += phrase + row[key]
    else:
        return f'{prefix}CHECK ({row["expression"]})'
    if row.get('deferrable'):
        source += ' DEFERRABLE'
        if row.get('initially_deferred'):
            source += ' INITIALLY DEFERRED'
    return source


def _constraint_rows(admin, draft):
    rows = []
    for item in draft.get('constraints') or []:
        kind = str((item or {}).get('kind', '')).upper()
        if kind not in CONSTRAINT_LISTS.values():
            raise RelationalClientError('constraint kind is unsupported')
        rows.append(_constraint_row(
            admin, kind, {k: v for k, v in item.items() if k != 'kind'}))
    for key, kind in CONSTRAINT_LISTS.items():
        for item in draft.get(key) or []:
            rows.append(_constraint_row(admin, kind, {
                name: value for name, value in item.items()
                if name in CONSTRAINT_KEYS}))
    return rows


def _split(admin, draft):
    into, at = draft.get('split_into'), draft.get('split_at')
    if not _blank(into) and not _blank(at):
        raise RelationalClientError('choose SPLIT INTO or SPLIT AT')
    if not _blank(into):
        if isinstance(into, bool) or not isinstance(into, int) or into < 1:
            raise RelationalClientError('split into a whole number of '
                                        'tablets')
        return f' SPLIT INTO {into} TABLETS'
    if not _blank(at):
        if not isinstance(at, list) or not at:
            raise RelationalClientError('split points are a list')
        points = ', '.join('(' + admin._safe_fragment(
            str(point), 'split point') + ')' for point in at)
        return f' SPLIT AT VALUES ({points})'
    return ''


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
    source = f'CREATE TABLE {table} ({", ".join(definitions)})'
    strategy = _choice(draft.get('partition_by'), PARTITIONING,
                       'partitioning')
    if strategy:
        source += f' PARTITION BY {strategy} (' + admin._safe_fragment(
            draft.get('partition_key'), 'partition key') + ')'
    elif not _blank(draft.get('partition_key')):
        raise RelationalClientError('a partition key needs a strategy')
    if draft.get('colocation') is not None:
        source += (' WITH (COLOCATION = '
                   f'{"true" if draft["colocation"] else "false"})')
    if not _blank(draft.get('tablespace')):
        source += f' TABLESPACE {admin._quote(draft["tablespace"])}'
    source += _split(admin, draft)
    statements = [{'source': source, 'parameters': ()}]
    statements += _rls(admin, table, draft, {})
    if not _blank(draft.get('comment')):
        statements.append(_comment(admin, 'TABLE', table, draft['comment']))
    for item in columns:
        if not _blank(item.get('comment')):
            statements.append(_comment(
                admin, 'COLUMN', f'{table}.{admin._quote(item["name"])}',
                item['comment']))
    return statements


def _rls(admin, table, draft, native):
    statements = []
    for key, on, off in (
            ('row_level_security', 'ENABLE', 'DISABLE'),
            ('force_row_level_security', 'FORCE', 'NO FORCE')):
        if draft.get(key) is None:
            continue
        if bool(draft[key]) != bool(native.get(key, False)):
            statements.append({'source': (
                f'ALTER TABLE {table} {on if draft[key] else off} ROW '
                'LEVEL SECURITY'), 'parameters': ()})
    return statements


def _alter_column(admin, table, name, changes, types=None):
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
    out = []
    if 'generated_expression' in changes:
        if not _blank(changes['generated_expression']):
            raise RelationalClientError(
                f'column {name}: a column becomes generated only when added')
        out.append(head + 'DROP EXPRESSION')
    if 'identity' in changes:
        identity = _choice(changes['identity'], IDENTITY, 'identity')
        out.append(head + (f'SET GENERATED {identity}' if identity
                           else 'DROP IDENTITY'))
    if not _blank(changes.get('type')) or 'collation' in changes:
        # PostgreSQL changes a collation only by restating the type.
        kind = changes.get('type') or (types or {}).get(name)
        if _blank(kind):
            raise RelationalClientError(
                f'column {name}: changing the collation re-states the type')
        source = head + 'TYPE ' + admin._safe_fragment(kind, 'column type')
        if not _blank(changes.get('collation')):
            source += ' COLLATE ' + admin._quote(changes['collation'])
        out.append(source)
    if 'default' in changes:
        out.append(head + ('DROP DEFAULT' if _blank(changes['default'])
                           else 'SET DEFAULT ' + admin._safe_fragment(
                               changes['default'], 'default')))
    if 'nullable' in changes:
        out.append(head + ('DROP NOT NULL' if changes['nullable'] is not
                           False else 'SET NOT NULL'))
    statements = [{'source': source, 'parameters': ()} for source in out]
    if 'comment' in changes:
        statements.append(_comment(admin, 'COLUMN', f'{table}.{column}',
                                   changes['comment']))
    return statements


def _comparable(row):
    return {key: value for key, value in row.items() if key != 'name'}


def _constraint_changes(admin, table, draft, native):
    held = list(native.get('constraints') or [])
    drops, adds, warnings = [], [], []
    for key, kind in CONSTRAINT_LISTS.items():
        if key not in draft:
            continue
        wanted = [_constraint_row(admin, kind, {
            name: value for name, value in item.items()
            if name in CONSTRAINT_KEYS})
            for item in draft[key] or [] if isinstance(item, dict)]
        current = [row for row in held if row.get('kind') == kind]
        by_name = {row['name']: row for row in current}
        kept = set()
        for row in wanted:
            old = by_name.get(row['name'])
            if old is not None and _comparable(old) == _comparable(row):
                kept.add(row['name'])
                continue
            adds.append(f'ALTER TABLE {table} ADD ' +
                        _constraint_sql(admin, row))
            if kind == 'PRIMARY KEY':
                warnings.append('YugabyteDB rewrites the table to change '
                                'its primary key.')
        for row in current:
            if row['name'] not in kept:
                drops.append(f'ALTER TABLE {table} DROP CONSTRAINT '
                             f'{admin._quote(row["name"])}')
    return drops, adds, warnings


def alter(admin, draft, target):
    unknown = set(draft) - ALTER_KEYS
    if unknown:
        raise RelationalClientError(
            ', '.join(sorted(unknown)) + ' cannot change in place')
    native = (target or {}).get('native') or {}
    table = admin._qualified(admin._target_path(target))
    drops, adds, warnings = _constraint_changes(admin, table, draft, native)
    statements = [{'source': source, 'parameters': ()} for source in drops]
    statements += [{'source': f'ALTER TABLE {table} DROP COLUMN '
                              f'{admin._quote(name)}', 'parameters': ()}
                   for name in draft.get('drop_columns') or []]
    statements += [{'source': (
        f'ALTER TABLE {table} RENAME COLUMN {admin._quote(item["from"])} '
        f'TO {admin._quote(item["to"])}'), 'parameters': ()}
        for item in draft.get('rename_columns') or []]
    for item in draft.get('alter_columns') or []:
        statements += _alter_column(admin, table, item.get('name'),
                                    item.get('changes'),
                                    native.get('column_types'))
    for item in draft.get('add_columns') or []:
        statements.append({'source': (
            f'ALTER TABLE {table} ADD COLUMN '
            f'{column_definition(admin, item)}'), 'parameters': ()})
        if not _blank(item.get('comment')):
            statements.append(_comment(
                admin, 'COLUMN', f'{table}.{admin._quote(item["name"])}',
                item['comment']))
    statements += [{'source': source, 'parameters': ()} for source in adds]
    if 'tablespace' in draft and (draft['tablespace'] or None) != (
            native.get('tablespace') or None):
        statements.append({'source': (
            f'ALTER TABLE {table} SET TABLESPACE ' + admin._quote(
                draft['tablespace'] or 'pg_default')), 'parameters': ()})
    statements += _rls(admin, table, draft, native)
    if 'comment' in draft and (draft['comment'] or None) != (
            native.get('comment') or None):
        statements.append(_comment(admin, 'TABLE', table, draft['comment']))
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements, warnings


def _unwrap(text):
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


def primary_key_shape(definition):
    """(hash_columns, order) from a primary key's pg_indexes definition:
    '... USING lsm ((a, b) HASH, c ASC)' or '... USING lsm (a HASH)'."""
    match = re.search(r' USING \w+ \((.*)\)$', definition or '')
    if not match:
        return [], 'ASC'
    body = match.group(1)
    grouped = re.match(r'\(([^)]*)\) HASH', body)
    if grouped:
        hashed = [part.strip().strip('"')
                  for part in grouped.group(1).split(',')]
    else:
        single = re.match(r'"?([^\s"]+)"? HASH', body)
        hashed = [single.group(1)] if single else []
    order = 'DESC' if re.search(r' DESC(,|$)', body) else 'ASC'
    return hashed, order


def extend_form(form, field, operation):
    """YSQL's table options on the shared table form (whose column and
    constraint editors are typed); the per-kind constraint grids and
    alter_columns come from the descriptor form."""
    for item in form['fields']:
        editor = item.get('array_editor') or {}
        if item['field_id'] in {'columns', 'add_columns'} and editor:
            editor['fields'] = editor.get('fields', []) + [
                field('identity', 'Identity', 'select', False,
                      options=IDENTITY),
                field('generated_expression', 'Generated (stored)', 'text'),
                field('collation', 'Collation', 'text'),
                field('comment', 'Comment', 'text'),
            ]
    form['fields'] += [
        field('tablespace', 'Tablespace', 'text'),
        field('comment', 'Comment', 'text'),
        field('row_level_security', 'Row-level security', 'boolean',
              False, default=False),
    ]
    if operation == 'create':
        form['fields'] += [
            field('split_into', 'Split into tablets', 'number'),
            field('colocation', 'Colocated', 'boolean', False,
                  'In a colocated database; off gives the table its own '
                  'tablets.'),
            field('partition_by', 'Partition by', 'select', False,
                  options=PARTITIONING),
            field('partition_key', 'Partition key', 'text'),
        ]
    return form

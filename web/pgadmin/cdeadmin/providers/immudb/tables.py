"""immudb SQL tables, sent through the native /db/sqlexec endpoint.

Checked on 1.11.0 (source and live, 2026-10-31):
- Columns: INTEGER, BOOLEAN, VARCHAR[n], UUID, BLOB[n], TIMESTAMP, FLOAT,
  JSON, with NOT NULL, DEFAULT and AUTO_INCREMENT. The PRIMARY KEY is a
  column list. Named and unnamed CHECK constraints are enforced; an
  unnamed one is named <table>_check<n>. Unlike standard SQL, a check
  fails on NULL (CHECK (p >= 0) refused an omitted p); p IS NULL OR
  p >= 0 allows it.
- After create: ADD COLUMN, RENAME COLUMN, DROP COLUMN, DROP CONSTRAINT
  and RENAME TO.
- Not offered:
  - ALTER COLUMN (SET/DROP NOT NULL, TYPE) is accepted and not kept: it
    changes only the loaded catalog (embedded/sql/stmt.go:1179);
  - there is no ADD CONSTRAINT;
  - FOREIGN KEY is accepted and neither stored nor enforced.
- The PostgreSQL-wire layer turns ALTER TABLE ... ADD into a reported
  success that does nothing (pkg/pgsql/server/stmts_handler.go:190) and
  drops a CHECK's name, so these statements are sent natively; a batch
  there is one transaction.
- Defaults and checks are read back from the catalog log
  (catalog_log.py); everything else from COLUMNS() and INDEXES().
"""
import re

from ...sdk.relational import RelationalClientError

TYPES = ('INTEGER', 'BOOLEAN', 'VARCHAR', 'UUID', 'BLOB', 'TIMESTAMP',
         'FLOAT', 'JSON')
SIZED = ('VARCHAR', 'BLOB')
COLUMN_KEYS = {'name', 'type', 'max_length', 'nullable', 'default',
               'auto_increment'}
CHECK_KEYS = {'name', 'expression'}
CREATE_KEYS = {'name', 'parent', 'columns', 'primary_key',
               'check_constraints'}
ALTER_KEYS = {'name', 'add_columns', 'drop_columns', 'rename_columns',
              'alter_columns', 'primary_key', 'check_constraints',
              'confirmation'}
_NAME = re.compile(r'[a-z_][a-z0-9_]{0,127}')
_WORD = re.compile(r"'(?:[^']|'')*'|([A-Za-z_][A-Za-z0-9_]*)")
_KEPT_NOT = (
    'immudb 1.11.0 accepts a column change but does not keep it; add a new '
    'column instead')


def _blank(value):
    return value is None or value == ''


def name(value, label='name'):
    """A validated name, double-quoted so reserved words (key) work.

    The lexer folds every identifier to lowercase, quoted or not
    (embedded/sql/parser.go:432), so an uppercase name would come back
    different; it is refused.
    """
    if isinstance(value, str) and _NAME.fullmatch(value.lower()) and \
            value != value.lower():
        raise RelationalClientError(
            f'{label}: immudb folds names to lowercase; use {value.lower()}')
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise RelationalClientError(
            f'{label} is a letter or underscore, then letters, digits or '
            'underscores')
    return f'"{value}"'


def _target_name(target):
    target = target or {}
    return target.get('display_name') or (
        target.get('display_path') or [None])[-1]


def column(admin, item, adding=False):
    if not isinstance(item, dict):
        raise RelationalClientError('a column is a row of the column grid')
    unknown = set(item) - COLUMN_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown column option: ' + ', '.join(sorted(unknown)))
    kind = str(item.get('type') or '').upper()
    if kind not in TYPES:
        raise RelationalClientError(
            'column type is one of: ' + ', '.join(TYPES))
    parts = [name(item.get('name'), 'column name'), kind]
    if not _blank(item.get('max_length')):
        size = item['max_length']
        if kind not in SIZED:
            raise RelationalClientError(
                'a maximum length applies to VARCHAR and BLOB only')
        if isinstance(size, bool) or not isinstance(size, int) or size < 1:
            raise RelationalClientError(
                'maximum length is a whole number from 1')
        parts[-1] += f'[{size}]'
    if item.get('nullable') is False:
        parts.append('NOT NULL')
    if not _blank(item.get('default')):
        parts += ['DEFAULT', admin._safe_fragment(
            item['default'], 'column default')]
    if item.get('auto_increment'):
        if adding:
            raise RelationalClientError(
                'AUTO_INCREMENT belongs to the primary key, set at create')
        parts.append('AUTO_INCREMENT')
    return ' '.join(parts)


def _check(admin, item):
    if not isinstance(item, dict) or set(item) - CHECK_KEYS:
        raise RelationalClientError('a check has a name and an expression')
    text = 'CHECK (' + admin._safe_fragment(
        item.get('expression'), 'check expression') + ')'
    if _blank(item.get('name')):
        return text
    return f'CONSTRAINT {name(item["name"], "check name")} {text}'


def create(admin, draft):
    unknown = set(draft) - CREATE_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown table option: ' + ', '.join(sorted(unknown)))
    if draft.get('parent') not in (None, '', 'public'):
        raise RelationalClientError(
            'immudb has one namespace per database (public)')
    table = name(draft.get('name'), 'table name')
    columns = draft.get('columns')
    if not isinstance(columns, list) or not columns:
        raise RelationalClientError('a table needs columns')
    elements = [column(admin, item) for item in columns]
    names = [item['name'] for item in columns]
    if len(set(names)) != len(names):
        raise RelationalClientError('column names repeat')
    key = draft.get('primary_key')
    if not isinstance(key, list) or not key:
        raise RelationalClientError('immudb tables need a primary key')
    for item in key:
        if item not in names:
            raise RelationalClientError(
                f'primary key column {item!r} is not a column')
    elements += [_check(admin, item)
                 for item in draft.get('check_constraints') or []]
    elements.append('PRIMARY KEY (' + ', '.join(
        name(item, 'key column') for item in key) + ')')
    return [f'CREATE TABLE {table} (' + ', '.join(elements) + ')']


def _check_changes(admin, table, wanted, native):
    held = native.get('check_constraints')
    if held is None:
        raise RelationalClientError(
            'this table\'s checks could not be read ('
            f'{native.get("catalog_log_unread") or "unread"}), so they '
            'cannot be changed here')
    wanted = wanted or []
    held_by_name = {item['name']: item for item in held}
    statements = []
    for item in wanted:
        previous = held_by_name.get((item or {}).get('name'))
        if previous is None or previous.get('expression') != item.get(
                'expression'):
            raise RelationalClientError(
                'immudb has no ADD CONSTRAINT: a check is set when the '
                'table is created, and can only be dropped afterwards')
    kept = {(item or {}).get('name') for item in wanted}
    for item in held:
        if item['name'] not in kept:
            statements.append(
                f'ALTER TABLE {table} DROP CONSTRAINT '
                f'{name(item["name"], "check name")}')
    return statements


def _words(expression):
    """The identifiers in an expression, string literals skipped."""
    return {match.group(1) for match in _WORD.finditer(expression or '')
            if match.group(1)}


def _guard_check_columns(draft, native):
    """Refuse renaming or dropping a column a check reads.

    Live, 1.11.0: a check keeps its expression text, so after RENAME
    COLUMN qty TO quantity every insert failed ("check constraint
    violation: column does not exist (qty)").
    """
    moved = {item.get('from') for item in draft.get('rename_columns') or []
             if isinstance(item, dict)} | set(draft.get('drop_columns') or [])
    if not moved:
        return
    held = native.get('check_constraints')
    if held is None:
        raise RelationalClientError(
            'this table\'s checks could not be read, so a column cannot be '
            'renamed or dropped here: a check using it would stop every '
            'insert')
    remaining = draft.get('check_constraints', held) or []
    for item in remaining:
        used = moved & _words(item.get('expression'))
        if used:
            raise RelationalClientError(
                f'check {item.get("name")} uses {", ".join(sorted(used))}; '
                'immudb keeps the check\'s text, so renaming or dropping the '
                'column would stop every insert. Drop the check first')


def alter(admin, draft, target):
    unknown = set(draft) - ALTER_KEYS
    if unknown:
        raise RelationalClientError(
            ', '.join(sorted(unknown)) + ' cannot change in place')
    native = (target or {}).get('native') or {}
    table = name(_target_name(target), 'table name')
    if draft.get('alter_columns'):
        raise RelationalClientError(_KEPT_NOT)
    if 'primary_key' in draft and list(draft['primary_key'] or []) != list(
            native.get('primary_key') or []):
        raise RelationalClientError(
            'immudb cannot change a primary key; create a new table')
    _guard_check_columns(draft, native)
    statements = []
    if 'check_constraints' in draft:
        statements += _check_changes(admin, table,
                                     draft['check_constraints'], native)
    for item in draft.get('rename_columns') or []:
        statements.append(
            f'ALTER TABLE {table} RENAME COLUMN '
            f'{name(item.get("from"), "column name")} TO '
            f'{name(item.get("to"), "new column name")}')
    for item in draft.get('add_columns') or []:
        statements.append(f'ALTER TABLE {table} ADD COLUMN '
                          f'{column(admin, item, adding=True)}')
    for item in draft.get('drop_columns') or []:
        statements.append(f'ALTER TABLE {table} DROP COLUMN '
                          f'{name(item, "column name")}')
    if draft.get('name') not in (None, '', _target_name(target)):
        statements.append(
            f'ALTER TABLE {table} RENAME TO '
            f'{name(draft["name"], "table name")}')
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


def drop(target):
    """DROP TABLE, after the table's checks.

    Live, 1.11.0: DROP TABLE failed ("tbtree: key not found") for every
    table that still had a check, with or without rows, and succeeded once
    the checks were dropped first; one batch does both. Unread checks
    leave the plain DROP TABLE, which the engine refuses if checks remain.
    """
    table = name(_target_name(target), 'table name')
    held = ((target or {}).get('native') or {}).get('check_constraints')
    return [f'ALTER TABLE {table} DROP CONSTRAINT '
            f'{name(item["name"], "check name")}'
            for item in held or []] + [f'DROP TABLE {table}']


def unwrap(expression):
    """The engine stores a check as (expr); the editor shows expr."""
    text = (expression or '').strip()
    if not (text.startswith('(') and text.endswith(')')):
        return text
    depth = 0
    for index, character in enumerate(text):
        depth += {'(': 1, ')': -1}.get(character, 0)
        if depth == 0 and index < len(text) - 1:
            return text
    return text[1:-1].strip()


def _primary(indexes):
    for row in indexes:
        if row.get('primary'):
            match = re.fullmatch(r'[^(]*\((.*)\)', str(row.get('name')))
            if match:
                return [item.strip() for item in match.group(1).split(',')]
    return []


def record(columns, indexes):
    """The table's native record from COLUMNS() and INDEXES() rows.

    Defaults and checks are left unread until with_facts adds them.
    """
    key = _primary(indexes)
    out = []
    for row in columns:
        kind = str(row['type']).upper()
        size = row.get('max_length')
        out.append({
            'name': row['name'], 'type': kind,
            'max_length': size if kind in SIZED and size else None,
            # A primary key column is NOT NULL whatever COLUMNS() says.
            'nullable': bool(row['nullable']) and row['name'] not in key,
            'default': None,
            'auto_increment': bool(row['auto_increment']),
        })
    return {'columns': out, 'primary_key': key, 'check_constraints': None,
            'catalog_log_unread': 'not read'}


def with_facts(native, facts):
    """Add catalog_log facts for the table, or the reason they are unread.

    Unread is kept distinct from empty: the record then has no checks
    list, and the editor refuses check changes.
    """
    if isinstance(facts, str):
        native['catalog_log_unread'] = facts
        return native
    facts = facts or {'defaults': {}, 'checks': []}
    for item in native.get('columns') or []:
        item['default'] = facts['defaults'].get(item['name'])
    native['check_constraints'] = [
        {'name': item['name'], 'expression': unwrap(item['expression'])}
        for item in facts['checks']]
    native.pop('catalog_log_unread', None)
    return native

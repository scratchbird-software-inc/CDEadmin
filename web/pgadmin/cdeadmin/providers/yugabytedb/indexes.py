"""YugabyteDB YSQL indexes.

Checked live on 2025.2.2.2: key columns or expressions with HASH / ASC /
DESC (leading HASH keys are hashed together), UNIQUE [NULLS NOT DISTINCT],
INCLUDE, a partial predicate, USING gin (read back as ybgin), TABLESPACE,
SPLIT INTO / SPLIT AT (between TABLESPACE and WHERE), NONCONCURRENTLY,
COMMENT ON INDEX; in place ALTER INDEX ... RENAME TO and SET TABLESPACE.
Refused: fillfactor and other storage parameters. A hash index (USING hash)
becomes lsm HASH, so the method is lsm or gin.

Field ids match the CockroachDB index form where the concept is the same
(keys, storing for INCLUDE, predicate, unique, comment).
"""
import re

from ...sdk.relational import RelationalClientError

METHODS = ('lsm', 'gin')
DIRECTIONS = ('HASH', 'ASC', 'DESC')
CREATE_KEYS = {'name', 'parent', 'table', 'keys', 'columns', 'unique',
               'nulls_not_distinct', 'method', 'storing', 'predicate',
               'tablespace', 'split_into', 'split_at', 'nonconcurrently',
               'comment'}
ALTER_KEYS = {'name', 'tablespace', 'comment', 'confirmation'}
_PLAIN = re.compile(r'[A-Za-z_][A-Za-z0-9_$]*')


def _blank(value):
    return value is None or value == ''


def _key_text(admin, expression):
    return (admin._quote(expression) if _PLAIN.fullmatch(expression)
            else f'({expression})')


def _keys(admin, draft):
    keys = draft.get('keys')
    if keys is None:
        keys = [{'expression': column}
                for column in draft.get('columns') or []]
    if not isinstance(keys, list) or not keys:
        raise RelationalClientError('an index needs at least one key')
    rows = []
    for item in keys:
        if not isinstance(item, dict):
            raise RelationalClientError('an index key must be an object')
        expression = admin._safe_fragment(item.get('expression'),
                                          'index key')
        direction = item.get('direction') or ''
        if direction and direction not in DIRECTIONS:
            raise RelationalClientError('direction is HASH, ASC or DESC')
        rows.append((expression, direction))
    hashed = 0
    while hashed < len(rows) and rows[hashed][1] == 'HASH':
        hashed += 1
    if any(direction == 'HASH' for _, direction in rows[hashed:]):
        raise RelationalClientError('HASH keys must lead the index')
    parts = []
    if hashed > 1:
        parts.append('(' + ', '.join(_key_text(admin, expression)
                                     for expression, _ in rows[:hashed]) +
                     ') HASH')
    elif hashed == 1:
        parts.append(f'{_key_text(admin, rows[0][0])} HASH')
    parts += [f'{_key_text(admin, expression)} {direction}'.strip()
              for expression, direction in rows[hashed:]]
    return ', '.join(parts)


def _split(admin, draft):
    into, at = draft.get('split_into'), draft.get('split_at')
    if not _blank(into) and not _blank(at):
        raise RelationalClientError('choose SPLIT INTO or SPLIT AT')
    if not _blank(into):
        if isinstance(into, bool) or not isinstance(into, int) or into < 1:
            raise RelationalClientError(
                'split into a whole number of tablets')
        return f' SPLIT INTO {into} TABLETS'
    if not _blank(at):
        if not isinstance(at, list) or not at:
            raise RelationalClientError('split points are a list')
        return ' SPLIT AT VALUES (' + ', '.join(
            '(' + admin._safe_fragment(str(point), 'split point') + ')'
            for point in at) + ')'
    return ''


def _comment(admin, name, value):
    text = 'NULL' if _blank(value) else admin._literal(str(value))
    return {'source': f'COMMENT ON INDEX {name} IS {text}', 'parameters': ()}


def create(admin, draft):
    unknown = set(draft) - CREATE_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown index option: ' + ', '.join(sorted(unknown)))
    name = admin._identifier(draft.get('name'))
    table = admin._option_path(draft, 'table')
    if len(table) == 1 and draft.get('parent'):
        table = admin._path_value(draft['parent']) + table
    method = draft.get('method') or 'lsm'
    if method not in METHODS:
        raise RelationalClientError('index method is lsm or gin')
    unique = bool(draft.get('unique'))
    if method == 'gin' and (unique or draft.get('storing')):
        raise RelationalClientError(
            'a gin index takes no UNIQUE or INCLUDE')
    if draft.get('nulls_not_distinct') and not unique:
        raise RelationalClientError('NULLS NOT DISTINCT is for UNIQUE')
    source = (f'CREATE {"UNIQUE " if unique else ""}INDEX '
              f'{"NONCONCURRENTLY " if draft.get("nonconcurrently") else ""}'
              f'{admin._quote(name)} ON {admin._qualified(table)}'
              f'{" USING gin" if method == "gin" else ""} '
              f'({_keys(admin, draft)})')
    if draft.get('storing'):
        source += ' INCLUDE (' + admin._identifier_list(
            draft['storing']) + ')'
    if draft.get('nulls_not_distinct'):
        source += ' NULLS NOT DISTINCT'
    if not _blank(draft.get('tablespace')):
        source += f' TABLESPACE {admin._quote(draft["tablespace"])}'
    # Live: SPLIT goes between TABLESPACE and WHERE.
    source += _split(admin, draft)
    if not _blank(draft.get('predicate')):
        source += ' WHERE ' + admin._safe_fragment(draft['predicate'],
                                                   'predicate')
    statements = [{'source': source, 'parameters': ()}]
    if not _blank(draft.get('comment')):
        qualified = admin._qualified((*table[:-1], name))
        statements.append(_comment(admin, qualified, draft['comment']))
    return statements


def alter(admin, draft, target):
    unknown = set(draft) - ALTER_KEYS
    if unknown:
        raise RelationalClientError(
            'only the name, tablespace and comment of an index change in '
            'place; ' + ', '.join(sorted(unknown)) + ' needs a new index')
    native = (target or {}).get('native') or {}
    path = admin._target_path(target)
    # An index lives in its table's schema.
    name = admin._qualified((path[0], path[-1]))
    statements = []
    if 'tablespace' in draft and (draft['tablespace'] or None) != (
            native.get('tablespace') or None):
        statements.append({'source': (
            f'ALTER INDEX {name} SET TABLESPACE ' + admin._quote(
                draft['tablespace'] or 'pg_default')), 'parameters': ()})
    if 'comment' in draft and (draft['comment'] or None) != (
            native.get('comment') or None):
        statements.append(_comment(admin, name, draft['comment']))
    if draft.get('name') not in (None, '', path[-1]):
        statements.append({'source': (
            f'ALTER INDEX {name} RENAME TO '
            f'{admin._quote(admin._identifier(draft["name"]))}'),
            'parameters': ()})
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


def _split_top(text):
    items, depth, start, quote = [], 0, 0, None
    for index, char in enumerate(text):
        if quote:
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
        elif char == ',' and depth == 0:
            items.append(text[start:index].strip())
            start = index + 1
    if text[start:].strip():
        items.append(text[start:].strip())
    return items


def _closing(text, start):
    """Index just past the parenthesis group opening at ``start``."""
    depth = 0
    for index in range(start, len(text)):
        depth += text[index] == '('
        depth -= text[index] == ')'
        if depth == 0:
            return index + 1
    return len(text)


def parse_definition(definition):
    """The index form's fields from a pg_indexes definition."""
    match = re.search(r' USING (\w+) \(', definition or '')
    if not match:
        return {}
    start = match.end() - 1
    end = _closing(definition, start)
    keys = []
    for item in _split_top(definition[start + 1:end - 1]):
        grouped = re.fullmatch(r'\((.*)\) HASH', item)
        if grouped:
            keys += [{'expression': part.strip(), 'direction': 'HASH'}
                     for part in _split_top(grouped.group(1))]
            continue
        direction = ''
        found = re.search(r' (HASH|ASC|DESC)$', item)
        if found:
            item, direction = item[:found.start()], found.group(1)
        keys.append({'expression': item.strip(), 'direction': direction})
    rest = definition[end:]
    include = re.match(r' INCLUDE \(', rest)
    storing = []
    if include:
        close = _closing(rest, include.end() - 1)
        storing = [part.strip().strip('"') for part in _split_top(
            rest[include.end():close - 1])]
        rest = rest[close:]
    predicate = re.search(r' WHERE \((.*)\)$', rest)
    return {
        'method': 'gin' if match.group(1) == 'ybgin' else 'lsm',
        'keys': keys, 'storing': storing,
        'nulls_not_distinct': ' NULLS NOT DISTINCT' in rest,
        'predicate': predicate.group(1) if predicate else None,
    }


def form(base, field, operation):
    if operation == 'alter':
        return {'form_id': 'yugabytedb.index.alter',
                'title': 'Alter YSQL index', 'fields': [
                    {**field('name', 'Name', 'text', True),
                     'initial_value_path': ['name']},
                    {**field('tablespace', 'Tablespace', 'text'),
                     'initial_value_path': ['tablespace']},
                    {**field('comment', 'Comment', 'text'),
                     'initial_value_path': ['comment']},
                ]}
    base['fields'] += [
        field('method', 'Method', 'select', False, default='lsm',
              options=METHODS),
        field('nulls_not_distinct', 'NULLS NOT DISTINCT', 'boolean', False,
              default=False),
        field('predicate', 'Partial index predicate', 'text'),
        field('tablespace', 'Tablespace', 'text'),
        field('split_into', 'Split into tablets', 'number'),
        field('nonconcurrently', 'Build without the online process',
              'boolean', False, 'NONCONCURRENTLY', False),
        field('comment', 'Comment', 'text'),
    ]
    return base

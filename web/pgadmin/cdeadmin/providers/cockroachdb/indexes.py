"""CockroachDB indexes: create, and alter what changes in place.

Checked live on 26.1.3: key columns or expressions with a direction,
UNIQUE, inverted (USING GIN), hash-sharded with a bucket count, STORING,
a partial predicate, and visibility (NOT VISIBLE, or a fraction). In place
an index can be renamed, have its visibility changed and be commented on;
any other change needs a new index, so the editor fixes those fields.
"""
import re

from ...sdk.relational import RelationalClientError

METHODS = ('btree', 'inverted')
DIRECTIONS = ('ASC', 'DESC')
CREATE_KEYS = {'name', 'parent', 'table', 'columns', 'keys', 'unique',
               'method', 'hash_sharded', 'bucket_count', 'storing',
               'predicate', 'visibility', 'comment'}
ALTER_KEYS = {'name', 'visibility', 'comment', 'confirmation'}
_PLAIN = re.compile(r'[A-Za-z_][A-Za-z0-9_$]*')


def _blank(value):
    return value is None or value == ''


def _visibility(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or \
            not 0 <= value <= 1:
        raise RelationalClientError('visibility is a number from 0 to 1')
    return float(value)


def _visibility_clause(value):
    value = _visibility(value)
    if value == 1:
        return 'VISIBLE'
    if value == 0:
        return 'NOT VISIBLE'
    return f'VISIBILITY {value:g}'


def _keys(admin, draft):
    keys = draft.get('keys')
    if keys is None:
        keys = [{'expression': column}
                for column in draft.get('columns') or []]
    if not isinstance(keys, list) or not keys:
        raise RelationalClientError('an index needs at least one key')
    out = []
    for item in keys:
        if not isinstance(item, dict):
            raise RelationalClientError('an index key must be an object')
        expression = admin._safe_fragment(item.get('expression'),
                                          'index key')
        direction = item.get('direction') or ''
        if direction and direction not in DIRECTIONS:
            raise RelationalClientError('direction is ASC or DESC')
        # A plain column is quoted; anything else is an expression.
        key = (admin._quote(expression) if _PLAIN.fullmatch(expression)
               else f'({expression})')
        out.append(f'{key} {direction}'.strip())
    return out


def create(admin, draft):
    unknown = set(draft) - CREATE_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown index option: ' + ', '.join(sorted(unknown)))
    name = admin._quote(admin._identifier(draft.get('name')))
    table = admin._option_path(draft, 'table')
    if len(table) == 1 and draft.get('parent'):
        table = admin._path_value(draft['parent']) + table
    table = admin._qualified(table)
    method = draft.get('method') or 'btree'
    if method not in METHODS:
        raise RelationalClientError('index method is btree or inverted')
    unique = bool(draft.get('unique'))
    hashed = bool(draft.get('hash_sharded'))
    storing = draft.get('storing') or []
    if method == 'inverted' and (unique or hashed or storing):
        raise RelationalClientError(
            'an inverted index takes no UNIQUE, hash sharding or STORING')
    source = (f'CREATE {"UNIQUE " if unique else ""}INDEX {name} ON '
              f'{table}{" USING GIN" if method == "inverted" else ""} (' +
              ', '.join(_keys(admin, draft)) + ')')
    if hashed:
        source += ' USING HASH'
        if not _blank(draft.get('bucket_count')):
            count = draft['bucket_count']
            if isinstance(count, bool) or not isinstance(count, int) or \
                    not 2 <= count <= 2048:
                raise RelationalClientError(
                    'bucket count is a whole number from 2 to 2048')
            source += f' WITH (bucket_count = {count})'
    elif not _blank(draft.get('bucket_count')):
        raise RelationalClientError('a bucket count needs hash sharding')
    if storing:
        source += ' STORING (' + admin._identifier_list(storing) + ')'
    if not _blank(draft.get('predicate')):
        source += ' WHERE ' + admin._safe_fragment(draft['predicate'],
                                                   'predicate')
    if not _blank(draft.get('visibility')) and _visibility(
            draft['visibility']) != 1:
        source += ' ' + _visibility_clause(draft['visibility'])
    statements = [{'source': source, 'parameters': ()}]
    if not _blank(draft.get('comment')):
        statements.append(_comment(admin, table, name, draft['comment']))
    return statements


def _comment(admin, table, name, value):
    text = 'NULL' if _blank(value) else admin._literal(str(value))
    return {'source': f'COMMENT ON INDEX {table}@{name} IS {text}',
            'parameters': ()}


def alter(admin, draft, target):
    unknown = set(draft) - ALTER_KEYS
    if unknown:
        raise RelationalClientError(
            'only the name, visibility and comment of an index change in '
            'place; ' + ', '.join(sorted(unknown)) + ' needs a new index')
    path = admin._target_path(target)
    table = admin._qualified(path[:-1])
    name = admin._quote(path[-1])
    native = (target or {}).get('native') or {}
    statements = []
    if not _blank(draft.get('visibility')) and _visibility(
            draft['visibility']) != _visibility(
                native.get('visibility', 1.0)):
        clause = _visibility_clause(draft['visibility'])
        statements.append({'source': f'ALTER INDEX {table}@{name} {clause}',
                           'parameters': ()})
    if 'comment' in draft and (draft['comment'] or None) != (
            native.get('comment') or None):
        statements.append(_comment(admin, table, name, draft['comment']))
    if not _blank(draft.get('name')) and draft['name'] != path[-1]:
        statements.append({'source': (
            f'ALTER INDEX {table}@{name} RENAME TO '
            f'{admin._quote(admin._identifier(draft["name"]))}'),
            'parameters': ()})
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


def key_list(definition):
    """[{expression, direction}] from a pg_indexes definition."""
    match = re.search(r' USING \w+ \(', definition)
    if not match:
        return []
    depth, start, items, index = 1, match.end(), [], match.end()
    while index < len(definition) and depth:
        char = definition[index]
        if char == "'":
            index = definition.find("'", index + 1)
            if index < 0:
                break
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth == 0:
                items.append(definition[start:index])
        elif char == ',' and depth == 1:
            items.append(definition[start:index])
            start = index + 1
        index += 1
    keys = []
    for item in items:
        item = item.strip()
        direction = ''
        found = re.search(r' (ASC|DESC)$', item)
        if found:
            item, direction = item[:found.start()], found.group(1)
        keys.append({'expression': item.strip(), 'direction': direction})
    return keys


def form(base, field, operation):
    """The shared index create form plus CockroachDB's options, or the
    in-place alter form. Keys with directions and STORING columns are
    descriptor grids (ui_descriptors/cockroachdb/forms/index.form.json)."""
    if operation == 'alter':
        return {'form_id': 'cockroachdb.index.alter',
                'title': 'Alter CockroachDB index', 'fields': [
                    {**field('name', 'Name', 'text', True),
                     'initial_value_path': ['name']},
                    {**field('visibility', 'Visibility', 'number', False,
                             '1 visible, 0 NOT VISIBLE, between: the '
                             'share of queries that may use it.'),
                     'initial_value_path': ['visibility']},
                    {**field('comment', 'Comment', 'text'),
                     'initial_value_path': ['comment']},
                ]}
    base['fields'] += [
        field('method', 'Method', 'select', False, 'inverted: USING GIN',
              default='btree', options=METHODS),
        field('hash_sharded', 'Hash sharded', 'boolean', False,
              'USING HASH', False),
        field('bucket_count', 'Bucket count', 'number'),
        field('predicate', 'Partial index predicate', 'text', False,
              'WHERE expression'),
        field('visibility', 'Visibility', 'number', False,
              '1 visible, 0 NOT VISIBLE.', 1),
        field('comment', 'Comment', 'text'),
    ]
    return base

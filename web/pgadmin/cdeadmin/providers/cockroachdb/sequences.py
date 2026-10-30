"""CockroachDB sequences.

Checked live on 26.1.3: AS INT2/INT4/INT8, START, INCREMENT, MINVALUE /
MAXVALUE (or NO ...), CACHE with an optional PER NODE / PER SESSION scope,
OWNED BY table.column (or NONE), RESTART [WITH], RENAME TO. Refused:
CYCLE (unimplemented), COMMENT ON SEQUENCE. pg_sequences reports bigint
for every sequence, so the record reads SHOW CREATE ALL TABLES.
"""
import re

from ...sdk.relational import RelationalClientError

TYPES = ('INT2', 'INT4', 'INT8')
SCOPES = ('PER NODE', 'PER SESSION')
_NUMBERS = (('start', 'START'), ('increment', 'INCREMENT'),
            ('minimum', 'MINVALUE'), ('maximum', 'MAXVALUE'))
CREATE_KEYS = {'name', 'parent', 'data_type', 'cache', 'cache_scope',
               'owned_by', *(key for key, _ in _NUMBERS)}
ALTER_KEYS = CREATE_KEYS - {'parent'} | {'restart', 'confirmation'}


def _blank(value):
    return value is None or value == ''


def _integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int):
        raise RelationalClientError(f'{label} must be a whole number')
    return value


def _clauses(admin, draft, native):
    """Option clauses for the keys present (alter: those that changed)."""
    if draft.get('cycle'):
        raise RelationalClientError('CockroachDB does not support CYCLE')
    clauses = []
    if not _blank(draft.get('data_type')) and draft['data_type'] != \
            native.get('data_type'):
        if draft['data_type'] not in TYPES:
            raise RelationalClientError('type is INT2, INT4 or INT8')
        clauses.append(f'AS {draft["data_type"]}')
    for key, keyword in _NUMBERS:
        if key not in draft or draft[key] == native.get(key):
            continue
        if _blank(draft[key]):
            if key in {'minimum', 'maximum'}:
                clauses.append(f'NO {keyword}')
            continue
        clauses.append(f'{keyword} {_integer(draft[key], key)}')
    if 'owned_by' in draft and (draft['owned_by'] or None) != (
            native.get('owned_by') or None):
        if _blank(draft['owned_by']):
            clauses.append('OWNED BY NONE')
        else:
            path = admin._path_value(draft['owned_by'])
            if len(path) < 2:
                raise RelationalClientError('owned by needs table.column')
            clauses.append('OWNED BY ' + admin._qualified(path))
    return clauses


def _cache_steps(draft, native):
    """ALTER clauses, in order, that move the cache to the wanted state.

    Live, 26.1.3: a cache above 1 has a scope (PER NODE by default); a
    scope-less CACHE n is ignored on a PER SESSION sequence; node becomes
    session directly, but session becomes node only after a reset to
    PER SESSION CACHE 1. So every step names its scope.
    """
    old_size = native.get('cache') or 1
    old_scope = native.get('cache_scope') or ''
    size = draft.get('cache', old_size)
    size = 1 if _blank(size) else _integer(size, 'cache')
    if size < 1:
        raise RelationalClientError('cache is at least 1')
    scope = draft.get('cache_scope', old_scope) or ''
    if scope and scope not in SCOPES:
        raise RelationalClientError('cache scope is PER NODE or PER SESSION')
    if size == 1:
        scope = ''
    elif not scope:
        scope = 'PER NODE'
    if (size, scope) == (old_size, old_scope):
        return []
    steps = []
    if old_scope == 'PER SESSION' and scope != 'PER SESSION':
        steps.append('PER SESSION CACHE 1')
        old_scope = ''
    if size == 1:
        if old_scope:
            steps.append(f'{old_scope} CACHE 1')
    else:
        steps.append(f'{scope} CACHE {size}')
    return steps


def create(admin, draft):
    unknown = set(draft) - CREATE_KEYS - {'cycle'}
    if unknown:
        raise RelationalClientError(
            'unknown sequence option: ' + ', '.join(sorted(unknown)))
    name = admin._new_object_name(admin._identifier(draft.get('name')),
                                  draft)
    source = ' '.join([f'CREATE SEQUENCE {name}',
                       *_clauses(admin, draft, {}),
                       *_cache_steps(draft, {})])
    return [{'source': source, 'parameters': ()}]


def alter(admin, draft, target):
    unknown = set(draft) - ALTER_KEYS - {'cycle'}
    if unknown:
        raise RelationalClientError(
            'unknown sequence change: ' + ', '.join(sorted(unknown)))
    native = (target or {}).get('native') or {}
    path = admin._target_path(target)
    name = admin._qualified(path)
    clauses = _clauses(admin, draft, native)
    if not _blank(draft.get('restart')):
        clauses.append(f'RESTART WITH {_integer(draft["restart"], "restart")}')
    statements = [{'source': f'ALTER SEQUENCE {name} {step}',
                   'parameters': ()} for step in _cache_steps(draft, native)]
    if clauses:
        statements.append({'source': f'ALTER SEQUENCE {name} ' +
                                     ' '.join(clauses), 'parameters': ()})
    if draft.get('name') not in (None, '', path[-1]):
        statements.append({'source': (
            f'ALTER SEQUENCE {name} RENAME TO '
            f'{admin._quote(admin._identifier(draft["name"]))}'),
            'parameters': ()})
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


_SEQUENCE = re.compile(r'CREATE SEQUENCE (?P<path>.+?)(?: AS (?P<type>\w+))?'
                       r' MINVALUE (?P<minimum>-?\d+)'
                       r' MAXVALUE (?P<maximum>-?\d+)'
                       r' INCREMENT (?P<increment>-?\d+)'
                       r' START (?P<start>-?\d+)'
                       r'(?: (?P<scope>PER NODE|PER SESSION))?'
                       r'(?: CACHE (?P<cache>\d+))?;?$')


def parse_create(statement):
    """{schema, name, fields} from CockroachDB's own rendering, or None."""
    match = _SEQUENCE.match(statement.strip())
    if not match:
        return None
    from .tables import _identifier
    try:
        schema, index = _identifier(match.group('path'), 0)
        name, _ = _identifier(match.group('path'), index + 1)
    except ValueError:
        return None
    return (schema, name), {
        'data_type': match.group('type') or 'INT8',
        **{key: int(match.group(key)) for key in (
            'start', 'increment', 'minimum', 'maximum')},
        'cache': int(match.group('cache') or 1),
        'cache_scope': match.group('scope') or '',
    }


def form(field, operation):
    fields = [field('name', 'Name', 'text', True)]
    if operation == 'create':
        fields.append(field('parent', 'Schema', 'text'))
    fields += [
        field('data_type', 'Type', 'select', False, default='INT8',
              options=TYPES),
        field('start', 'Start', 'number'),
        field('increment', 'Increment', 'number'),
        field('minimum', 'Minimum', 'number'),
        field('maximum', 'Maximum', 'number'),
        field('cache', 'Cache', 'number'),
        field('cache_scope', 'Cache scope', 'select', False,
              'Default: per node. PER SESSION caches per connection.',
              options=SCOPES),
        field('owned_by', 'Owned by column', 'text', False,
              'schema.table.column; dropping it drops the sequence.'),
    ]
    if operation == 'alter':
        for item in fields:
            item['initial_value_path'] = [item['field_id']]
        fields.append(field('restart', 'Restart with', 'number', False,
                            'RESTART WITH: the next value nextval returns.'))
    return {'form_id': f'cockroachdb.sequence.{operation}',
            'title': f'{operation.title()} CockroachDB sequence',
            'fields': fields}

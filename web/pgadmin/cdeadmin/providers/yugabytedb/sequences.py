"""YugabyteDB YSQL sequences.

Checked live on 2025.2.2.2: AS smallint / integer / bigint, INCREMENT,
MINVALUE / MAXVALUE (or NO ...), START, CACHE, CYCLE / NO CYCLE, OWNED BY
(or NONE), RESTART [WITH], RENAME TO, COMMENT ON SEQUENCE. A cache below
the server's minimum is raised to it (CACHE 10 read back as 100 on the
demo), so the record shows the cache in force.

Field ids match the CockroachDB sequence form (providers/cockroachdb/
sequences.py); YSQL adds cycle and comment, CockroachDB's cache scope is
not offered.
"""
from ...sdk.relational import RelationalClientError

TYPES = ('smallint', 'integer', 'bigint')
_NUMBERS = (('start', 'START'), ('increment', 'INCREMENT'),
            ('minimum', 'MINVALUE'), ('maximum', 'MAXVALUE'),
            ('cache', 'CACHE'))
CREATE_KEYS = {'name', 'parent', 'data_type', 'cycle', 'owned_by',
               'comment', *(key for key, _ in _NUMBERS)}
ALTER_KEYS = CREATE_KEYS - {'parent'} | {'restart', 'confirmation'}


def _blank(value):
    return value is None or value == ''


def _integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int):
        raise RelationalClientError(f'{label} must be a whole number')
    return value


def _clauses(admin, draft, native):
    clauses = []
    if not _blank(draft.get('data_type')) and draft['data_type'] != \
            native.get('data_type'):
        if draft['data_type'] not in TYPES:
            raise RelationalClientError(
                'type is ' + ', '.join(TYPES))
        clauses.append(f'AS {draft["data_type"]}')
    for key, keyword in _NUMBERS:
        if key not in draft or draft[key] == native.get(key):
            continue
        if _blank(draft[key]):
            if key in {'minimum', 'maximum'}:
                clauses.append(f'NO {keyword}')
            continue
        value = _integer(draft[key], key)
        if key == 'cache' and value < 1:
            raise RelationalClientError('cache is at least 1')
        clauses.append(f'{keyword} {value}')
    if draft.get('cycle') is not None and bool(draft['cycle']) != bool(
            native.get('cycle', False)):
        clauses.append('CYCLE' if draft['cycle'] else 'NO CYCLE')
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


def _comment(admin, name, value):
    text = 'NULL' if _blank(value) else admin._literal(str(value))
    return {'source': f'COMMENT ON SEQUENCE {name} IS {text}',
            'parameters': ()}


def create(admin, draft):
    unknown = set(draft) - CREATE_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown sequence option: ' + ', '.join(sorted(unknown)))
    name = admin._new_object_name(admin._identifier(draft.get('name')),
                                  draft)
    statements = [{'source': ' '.join(
        [f'CREATE SEQUENCE {name}', *_clauses(admin, draft, {})]),
        'parameters': ()}]
    if not _blank(draft.get('comment')):
        statements.append(_comment(admin, name, draft['comment']))
    return statements


def alter(admin, draft, target):
    unknown = set(draft) - ALTER_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown sequence change: ' + ', '.join(sorted(unknown)))
    native = (target or {}).get('native') or {}
    path = admin._target_path(target)
    name = admin._qualified(path)
    clauses = _clauses(admin, draft, native)
    if not _blank(draft.get('restart')):
        clauses.append('RESTART WITH ' + str(
            _integer(draft['restart'], 'restart')))
    statements = []
    if clauses:
        statements.append({'source': f'ALTER SEQUENCE {name} ' +
                                     ' '.join(clauses), 'parameters': ()})
    if 'comment' in draft and (draft['comment'] or None) != (
            native.get('comment') or None):
        statements.append(_comment(admin, name, draft['comment']))
    if draft.get('name') not in (None, '', path[-1]):
        statements.append({'source': (
            f'ALTER SEQUENCE {name} RENAME TO '
            f'{admin._quote(admin._identifier(draft["name"]))}'),
            'parameters': ()})
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


def form(field, operation):
    fields = [field('name', 'Name', 'text', True)]
    if operation == 'create':
        fields.append(field('parent', 'Schema', 'text'))
    fields += [
        field('data_type', 'Type', 'select', False, default='bigint',
              options=TYPES),
        field('start', 'Start', 'number'),
        field('increment', 'Increment', 'number'),
        field('minimum', 'Minimum', 'number'),
        field('maximum', 'Maximum', 'number'),
        field('cache', 'Cache', 'number', False,
              'Raised to the server minimum when smaller.'),
        field('cycle', 'Cycle', 'boolean', False, default=False),
        field('owned_by', 'Owned by column', 'text', False,
              'schema.table.column'),
        field('comment', 'Comment', 'text'),
    ]
    if operation == 'alter':
        for item in fields:
            item['initial_value_path'] = [item['field_id']]
        fields.append(field('restart', 'Restart with', 'number'))
    return {'form_id': f'yugabytedb.sequence.{operation}',
            'title': f'{operation.title()} YSQL sequence', 'fields': fields}

"""YugabyteDB YSQL placement tablespaces.

Checked live on 2025.2.2.2: CREATE TABLESPACE name [OWNER role] WITH
(replica_placement = '{"num_replicas": n, "placement_blocks": [{"cloud",
"region", "zone" (or "*"), "min_num_replicas", "leader_preference"}]}');
ALTER TABLESPACE ... OWNER TO; COMMENT ON TABLESPACE; DROP TABLESPACE.
Refused ("ALTER TABLESPACE not supported yet"): SET / RESET
replica_placement and RENAME TO, so the placement is fixed once created.

The engine refuses minimums summing past num_replicas ("Sum of
min_num_replicas fields (2) exceeds the total replication factor"), a
leader_preference of 0, and preferences that are not contiguous from 1
("leader preferences must be contiguous from 1..N"); the editor says so
first. It accepts unknown keys and LOCATION without effect, so neither is
sent.
"""
import json

from ...sdk.relational import RelationalClientError

CREATE_KEYS = {'name', 'owner', 'num_replicas', 'placement_blocks',
               'comment'}
ALTER_KEYS = {'owner', 'comment', 'confirmation'}
_BLOCK_KEYS = ('cloud', 'region', 'zone')


def _blank(value):
    return value is None or value == ''


def _count(value, label, minimum=1):
    if isinstance(value, bool) or not isinstance(value, int) or \
            value < minimum:
        raise RelationalClientError(f'{label} is a whole number from '
                                    f'{minimum}')
    return value


def placement(draft):
    """The replica_placement object, in the engine's key order."""
    replicas = _count(draft.get('num_replicas'), 'replicas')
    blocks = draft.get('placement_blocks')
    if not isinstance(blocks, list) or not blocks:
        raise RelationalClientError('a placement needs at least one block')
    out, preferences, seen = [], [], set()
    for block in blocks:
        if not isinstance(block, dict) or not all(
                isinstance(block.get(key), str) and block[key].strip()
                for key in _BLOCK_KEYS):
            raise RelationalClientError(
                'a placement block needs a cloud, region and zone '
                '(zone * for any)')
        where = tuple(block[key].strip() for key in _BLOCK_KEYS)
        if where in seen:
            raise RelationalClientError(
                'placement block ' + '.'.join(where) + ' is listed twice')
        seen.add(where)
        item = dict(zip(_BLOCK_KEYS, where))
        item['min_num_replicas'] = _count(
            block.get('min_num_replicas'), 'minimum replicas')
        if not _blank(block.get('leader_preference')):
            item['leader_preference'] = _count(
                block['leader_preference'], 'leader preference')
            preferences.append(item['leader_preference'])
        out.append(item)
    total = sum(item['min_num_replicas'] for item in out)
    if total > replicas:
        raise RelationalClientError(
            f'the blocks\' minimum replicas ({total}) exceed the replicas '
            f'({replicas})')
    if preferences and sorted(set(preferences)) != list(
            range(1, max(preferences) + 1)):
        raise RelationalClientError(
            'leader preferences must run from 1 without gaps')
    return {'num_replicas': replicas, 'placement_blocks': out}


def from_options(options):
    """num_replicas and placement_blocks from pg_tablespace.spcoptions."""
    for entry in options or ():
        key, _, value = str(entry).partition('=')
        if key == 'replica_placement':
            try:
                parsed = json.loads(value)
            except ValueError:
                return None, []
            blocks = [{
                'cloud': block.get('cloud'), 'region': block.get('region'),
                'zone': block.get('zone'),
                'min_num_replicas': block.get('min_num_replicas'),
                'leader_preference': block.get('leader_preference'),
            } for block in parsed.get('placement_blocks') or []]
            return parsed.get('num_replicas'), blocks
    return None, []


def _comment(admin, name, value):
    text = 'NULL' if _blank(value) else admin._literal(str(value))
    return {'source': f'COMMENT ON TABLESPACE {name} IS {text}',
            'parameters': ()}


def create(admin, draft):
    unknown = set(draft) - CREATE_KEYS
    if unknown:
        raise RelationalClientError(
            'unknown tablespace option: ' + ', '.join(sorted(unknown)))
    name = admin._quote(admin._identifier(draft.get('name')))
    source = f'CREATE TABLESPACE {name}'
    if not _blank(draft.get('owner')):
        source += f' OWNER {admin._quote(draft["owner"])}'
    serialized = json.dumps(placement(draft), separators=(',', ':'))
    source += f' WITH (replica_placement={admin._literal(serialized)})'
    statements = [{'source': source, 'parameters': ()}]
    if not _blank(draft.get('comment')):
        statements.append(_comment(admin, name, draft['comment']))
    return statements


def alter(admin, draft, target):
    unknown = set(draft) - ALTER_KEYS
    if unknown:
        raise RelationalClientError(
            ', '.join(sorted(unknown)) + ' cannot change: YugabyteDB '
            'does not alter a tablespace\'s placement or name yet; create '
            'a new tablespace and move tables to it')
    native = (target or {}).get('native') or {}
    name = admin._quote((target or {}).get('display_name'))
    statements = []
    if draft.get('owner') not in (None, '', native.get('owner')):
        statements.append({'source': (
            f'ALTER TABLESPACE {name} OWNER TO '
            f'{admin._quote(draft["owner"])}'), 'parameters': ()})
    if 'comment' in draft and (draft['comment'] or None) != (
            native.get('comment') or None):
        statements.append(_comment(admin, name, draft['comment']))
    if not statements:
        raise RelationalClientError('nothing to change')
    return statements


def form(field, operation):
    fields = [field('name', 'Name', 'text', True),
              field('owner', 'Owner', 'text'),
              field('comment', 'Comment', 'text')]
    if operation == 'create':
        fields.append(field('num_replicas', 'Replicas', 'number', True))
    else:
        for item in fields:
            item['initial_value_path'] = [item['field_id']]
    return {'form_id': f'yugabytedb.tablespace.{operation}',
            'title': f'{operation.title()} YSQL placement tablespace',
            'fields': fields,
            'notes': 'Placement blocks are a descriptor grid '
                     '(tablespace.form.json).'}

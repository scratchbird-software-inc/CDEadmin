"""Native standalone index models and dependency checks for DDN previews."""
import re

from ..providers.firebird_expressions import index_expression
from ..providers.firebird.character_metadata import identifier, text

FIELDS = {'unique', 'inactive', 'index_type', 'segments', 'expression_source',
          'condition_source', 'description'}
DEFINITION = {'unique', 'index_type', 'segments', 'expression_source', 'condition_source'}


def flag(value):
    if value is None:
        return '0'  # Native nullable catalog flags use zero as the default.
    if type(value) not in (str, int) or str(value) not in ('0', '1'):
        raise ValueError('Index flags must be native zero/one values')
    return str(value)


def model(row):
    native = row['native']
    for key in ('unique', 'inactive', 'index_type'):
        if key not in native:
            raise ValueError('Exact index metadata is missing: ' + key)
    result = {key: flag(native[key]) for key in ('unique', 'inactive', 'index_type')}
    result['table'] = row['path'][0]
    identifier(result['table'])
    # The native reader omits the segment group for computed indexes because
    # RDB$INDEX_SEGMENTS has no rows. This is known-empty only with an expression.
    if 'segments' not in native and not native.get('expression_source'):
        raise ValueError('Exact index metadata is missing: segments')
    segments = native.get('segments', [])
    if not isinstance(segments, list) or len(segments) > 16:
        raise ValueError('Invalid Firebird index segment list')
    ordered, names = {}, set()
    for segment in segments:
        if not isinstance(segment, dict) or set(segment) != {'field_name', 'position'}:
            raise ValueError('Index segments require exact field name and position')
        position = segment['position']
        if type(position) not in (str, int) or not str(position).isdigit():
            raise ValueError('Invalid index segment position')
        position = int(position)
        name = segment['field_name']
        identifier(name)
        if position in ordered or name in names:
            raise ValueError('Duplicate index segment position or column')
        ordered[position] = name
        names.add(name)
    if set(ordered) != set(range(len(segments))):
        raise ValueError('Index segment positions must be contiguous from zero')
    result['segments'] = [{'field_name': ordered[i], 'position': i} for i in range(len(segments))]
    for key in ('expression_source', 'condition_source'):
        value = native.get(key)
        result[key] = None if value is None else text(value, 'Index expression source')
    if not result['segments'] and not result['expression_source']:
        raise ValueError('Index needs columns or a native computed expression')
    if result['segments'] and result['expression_source']:
        raise ValueError('Index columns and computed expression are mutually exclusive')
    return result


def context(row, current, segments):
    table, name = row['path']
    databases = [r for r in current['rows'].values() if r['kind'] == 'database']
    observations = databases[0]['native'].get('catalog_observations', []) if len(databases) == 1 else []
    for section in ('index objects', 'system index objects', 'constraint objects', 'column objects'):
        evidence = [item for item in observations if item.get('section') == section]
        if len(evidence) != 1 or evidence[0].get('available') is not True:
            raise ValueError('Index planning requires available catalog observation: ' + section)
    parents = [r for r in current['rows'].values() if r['kind'] == 'table' and r['path'] == [table]]
    if len(parents) != 1 or parents[0]['system'] == 'true':
        raise ValueError('Index owner must be an observed user table')
    for item in current['rows'].values():
        if item['kind'] == 'index' and item['path'][-1] == name and item['resource_id'] != row['resource_id']:
            raise ValueError('Index name already exists elsewhere in the database')
        if item['kind'] == 'constraint' and item['native'].get('index_name') == name:
            raise ValueError('Constraint backing indexes require the constraint lifecycle')
    # Parent summaries also retain backing-index identity when a filtered child
    # catalog omits a constraint record.
    if any(c.get('index_name') == name for c in parents[0]['native'].get('constraints', [])):
        raise ValueError('Constraint backing indexes require the constraint lifecycle')
    available = {r['path'][-1] for r in current['rows'].values()
                 if r['kind'] == 'column' and len(r['path']) == 2 and r['path'][0] == table}
    if any(part['field_name'] not in available for part in segments):
        raise ValueError('Index refers to a column absent from the current table catalog')
    return parents[0]['resource_id']


def statements(before, after):
    name = identifier(after['name'])
    result = []
    if before is None:
        expression, condition = after['expression_source'], after['condition_source']
        if expression is not None:
            expression = index_expression(expression, 'Computed index expression', require_outer=True)
            definition = 'COMPUTED BY ' + expression + '\n'
        else:
            definition = '(' + ', '.join(identifier(s['field_name']) for s in after['segments']) + ')'
        if condition is not None:
            match = re.fullmatch(r'WHERE\s+(.+)', condition.strip(), re.IGNORECASE | re.DOTALL)
            if not match:
                raise ValueError('Native partial index source must contain WHERE and a predicate')
            index_expression(match.group(1), 'Partial index predicate')
            definition += ' ' + condition.strip() + '\n'
        result.append('CREATE ' + ('UNIQUE ' if after['unique'] == '1' else '') +
                      ('DESCENDING ' if after['index_type'] == '1' else 'ASCENDING ') +
                      'INDEX ' + name + ' ON ' + identifier(after['table']) + ' ' + definition)
    elif any(before[key] != after[key] for key in DEFINITION):
        raise ValueError('Index definition changes require an explicit rebuild plan')
    if (before is None and after['inactive'] == '1') or (before is not None and before['inactive'] != after['inactive']):
        result.append('ALTER INDEX ' + name + (' INACTIVE' if after['inactive'] == '1' else ' ACTIVE'))
    return result

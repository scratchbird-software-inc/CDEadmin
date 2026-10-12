"""Explicit creation ordering, separate from broad native drift guards."""
from ..providers.firebird.identity import catalog_resource_id
from .firebird_routine_stages import break_cycle

INSTRUCTION = 'creation_dependencies'


def projected_catalog(baseline, desired, current):
    rows = dict(current['rows'])
    for identity, row in desired['rows'].items():
        if identity not in baseline['rows'] and identity not in rows:
            rows[identity] = row
            if row['kind'] == 'table':
                columns = row['native'].get('columns')
                for column in columns if isinstance(columns, list) else []:
                    if not isinstance(column, dict) or not isinstance(column.get('name'), str):
                        continue
                    child = catalog_resource_id('column', row['path'], column['name'])
                    rows.setdefault(child, {'resource_id': child, 'kind': 'column',
                        'name': column['name'], 'path': [*row['path'], column['name']],
                        'system': row['system'], 'native': column})
    return {**current, 'rows': rows}


def dependencies(identity, row, baseline, desired, current):
    native = row['native']
    declared = native.get(INSTRUCTION, [])
    if not isinstance(declared, list) or len(declared) > 1024 or any(not isinstance(value, str) or not value for value in declared):
        raise ValueError('Creation dependencies must be a bounded array of exact resource identities')
    if len(set(declared)) != len(declared) or identity in declared:
        raise ValueError('Creation dependencies contain duplicate or self references')
    old = baseline['rows'].get(identity)
    if old is not None:
        if declared != old['native'].get(INSTRUCTION, []):
            raise ValueError('Creation ordering cannot be changed on an existing object')
        return []
    required = set(declared)
    if row['kind'] == 'table':
        for field in ('columns', 'constraints'):
            if native.get(field) is not None and not isinstance(native[field], list):
                raise ValueError('Table ' + field + ' must be an array')
        for column in native.get('columns') or []:
            if isinstance(column, dict) and isinstance(column.get('domain'), str) and column['domain'] and not column['domain'].startswith('RDB$'):
                required.add(catalog_resource_id('domain', [], column['domain']))
        for constraint in native.get('constraints') or []:
            if isinstance(constraint, dict) and constraint.get('constraint_type') == 'FOREIGN KEY' and isinstance(constraint.get('referenced_relation'), str) and constraint['referenced_relation'] != row['name']:
                parent = catalog_resource_id('table', [], constraint['referenced_relation'])
                if parent not in desired['rows'] or parent in baseline['rows'] or parent in current['rows']:
                    required.add(parent)
    elif row['kind'] in {'index', 'column', 'constraint'} and row['path']:
        required.add(catalog_resource_id('table', [], row['path'][0]))
    elif row['kind'] == 'trigger' and native.get('relation'):
        matches = [key for key, candidate in {**current['rows'], **desired['rows']}.items()
                   if candidate['kind'] in {'table', 'view'} and candidate['name'] == native['relation']]
        if len(matches) != 1:
            raise ValueError('Trigger relation must resolve to one exact native identity')
        required.add(matches[0])
    elif row['kind'] in {'procedure', 'function'}:
        for parameter in native.get('parameters') or []:
            if not isinstance(parameter, dict):
                raise ValueError('Routine parameter must be an object')
            domain = parameter.get('domain')
            if isinstance(domain, str) and domain and not domain.startswith('RDB$'):
                required.add(catalog_resource_id('domain', [], domain))
            if parameter.get('relation_name') and parameter.get('field_name'):
                parent = parameter['relation_name']
                # A new table owns its projected column; a separately added
                # column has its own operation and exact ordering identity.
                column = catalog_resource_id('column', [parent], parameter['field_name'])
                required.add(column if column in desired['rows'] or column in current['rows'] else catalog_resource_id('table', [], parent))
    available = current['rows'].keys() | desired['rows'].keys()
    absent = required - available
    if absent:
        raise ValueError('Creation dependencies are unavailable: ' + ', '.join(sorted(absent)))
    return sorted(required)


def order(operations):
    by_id = {item['resource_id']: item for item in operations}
    edges = {identity: set(item.get('order_dependencies', [])) & by_id.keys() for identity, item in by_id.items()}
    for identity, item in by_id.items():
        if item['kind'] == 'table' and item['operation'] == 'create':
            for dependency in edges[identity]:
                if by_id[dependency]['kind'] == 'domain' and by_id[dependency]['operation'] == 'alter':
                    raise ValueError('Referenced domain alteration needs effective column reconciliation: ' + dependency)
    rank = {'domain': 0, 'sequence': 0, 'exception': 0, 'role': 0, 'blob-filter': 0,
            'table': 1, 'index': 2, 'view': 3}
    result = []
    while edges:
        ready = sorted((identity for identity, prerequisites in edges.items() if not prerequisites),
                       key=lambda identity: (rank.get(by_id[identity]['kind'], 4), identity))
        if not ready and break_cycle(edges, by_id):
            continue
        if not ready:
            raise ValueError('Creation dependency cycle: ' + ', '.join(sorted(edges)))
        for identity in ready:
            result.append(by_id[identity]); del edges[identity]
        for prerequisites in edges.values():
            prerequisites.difference_update(ready)
    return result

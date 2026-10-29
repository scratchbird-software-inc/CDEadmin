"""DuckDB catalog-qualified relations and native keys in the public DDN graph."""
import hashlib
import json
from . import ddn_source as ddn
from .firebird_catalog_export import MAX_BYTES, MAX_DDN_UNITS, native_metadata
from . import embedded_physical


def build_diagram(resources, provenance):
    module = 'scratchrobin.duckdb.relations'
    def quote(value):
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    def key(value): return 'n_' + hashlib.sha256(value.encode('utf8')).hexdigest()
    relations = sorted((row for row in resources if row['resource_kind'] in {'table', 'view'}),
                       key=lambda row: (row['display_path'], row['resource_id']))
    if not relations: return None
    by_path = {tuple(row['display_path']): row for row in relations}
    if len(by_path) != len(relations): raise ValueError('Ambiguous native DuckDB relation paths')
    prefix = 'duckdb:' + provenance['endpoint_id'] + ':' + provenance['database_target_id'] + ':'
    declarations, edges, warnings, mapping = [], [], [], {}
    indexes = embedded_physical.forward('duckdb', resources)
    def fk_values(table, constraint_id):
        # A droppable foreign key is its edge: the edge record carries the constraint identity and vocabulary.
        for item in indexes.get(table, []):
            if item['role'] == 'ref' and item['row']['resource_id'] == constraint_id:
                return {'resource_id': constraint_id, 'native_kind': 'constraint', 'native_json': quote(native_metadata(item['row'], 'duckdb')),
                        **item['values']}
        return {}
    for row in relations:
        identity = row['resource_id']; native = native_metadata(row, 'duckdb')
        fields = []
        for column in sorted(native.get('columns', []), key=lambda item: item['ordinal_position']):
            cid = column['resource_id']
            properties = {'datatype': column['data_type'], 'nullable': bool(column['nullable'])}
            if column.get('comment'): properties['description'] = column['comment']
            fields.append(ddn.native_field(key(cid), column['name'], prefix + cid, properties))
            mapping[key(cid)] = cid
        label = '.'.join(row['display_path'])
        children = []
        for item in [item for item in indexes.get(identity, []) if item['role'] != 'ref'] if row['resource_kind'] == 'table' else []:
            child = item['row']['resource_id']
            children.append({'identity': key(child), 'title': item['row']['display_name'], 'role': item['role'],
                'uid': prefix + child, 'values': {'resource_id': child, 'native_kind': item['role'],
                    'native_json': quote(native_metadata(item['row'], 'duckdb')), **item['values']}})
            mapping[key(child)] = child
        declarations.append(ddn.relation_object(key(identity), label, row['resource_kind'], prefix + identity,
            {'resource_id': identity, 'native_kind': row['resource_kind'], 'native_json': quote(native)}, fields, module,
            children))
        mapping[key(identity)] = identity
        for constraint in native.get('constraints', []):
            if constraint['constraint_type'] != 'FOREIGN KEY': continue
            # DuckDB 1.5.2 admits native FKs only inside one schema/catalog.
            target = by_path.get(tuple(row['display_path'][:-1] + [constraint['referenced_table']]))
            if target is None:
                warnings.append('Native foreign-key target outside visible selection: ' + constraint['name'])
                continue
            cid = constraint['resource_id']
            label = constraint['name'] + ' (' + ', '.join(constraint['column_names']) + ') -> (' + ', '.join(constraint['referenced_column_names']) + ')'
            declarations.append(ddn.relation_edge(key(cid), label, key(identity), key(target['resource_id']),
                prefix + cid, {'native_json': quote(constraint), **fk_values(identity, cid)}, module))
            edges.append((key(cid), identity, target['resource_id'])); mapping[key(cid)] = cid
    views, blocks = [], []
    for start in range(0, len(relations), 25):
        selected = {row['resource_id'] for row in relations[start:start + 25]}
        sources = set(selected)
        selected.update(target for _, source, target in edges if source in sources)
        if len(selected) > 100 or len(views) >= 64: raise ValueError('DuckDB diagram exceeds view bounds')
        view = 'relations_' + str(len(views) + 1); label = 'DuckDB relations — page ' + str(len(views) + 1)
        blocks.append(ddn.graph_view(view, label, [key(identity) for identity in sorted(selected)],
            [(edge, key(source), key(target)) for edge, source, target in edges]))
        views.append({'id': view, 'label': label, 'entry': 'relations.ddn'})
    source = ddn.header(module) + '\n'.join(declarations + blocks)
    if len(source.encode('utf8')) > MAX_BYTES or len(source.encode('utf-16-le')) // 2 > MAX_DDN_UNITS:
        raise ValueError('DuckDB diagram exceeds the paired DDN document bound')
    return {'snapshot': {'format': 'ddn-source-workspace@1', 'entry': 'relations.ddn', 'view': views[0]['id'], 'files': {'relations.ddn': source}},
            'views': views, 'warnings': warnings, 'resource_mapping': mapping,
            'deployment': 'diagram-only', 'foreign_keys': len(edges)}

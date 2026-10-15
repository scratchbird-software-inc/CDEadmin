"""DuckDB catalog-qualified relations and native keys in the public DDN graph."""
import hashlib
import json
from .firebird_catalog_export import MAX_BYTES, MAX_DDN_UNITS, native_metadata


def build_diagram(resources, provenance):
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
    for row in relations:
        identity = row['resource_id']; native = native_metadata(row, 'duckdb')
        fields = []
        for column in sorted(native.get('columns', []), key=lambda item: item['ordinal_position']):
            cid = column['resource_id']
            properties = ['uid:' + quote(prefix + cid), 'datatype:' + quote(column['data_type']),
                          'nullable:' + ('true' if column['nullable'] else 'false')]
            if column.get('comment'): properties.append('description:' + quote(column['comment']))
            fields.append('field ' + key(cid) + ' ' + quote(column['name']) + ' {' + ';'.join(properties) + ';}')
            mapping[key(cid)] = cid
        label = '.'.join(row['display_path'])
        declarations.append('object ' + key(identity) + ' ' + quote(label) + ' {kind:' + row['resource_kind'] +
            ';uid:' + quote(prefix + identity) + ';x_record:{resource_id:' + quote(identity) +
            ',native_kind:' + quote(row['resource_kind']) + ',native_json:' + quote(quote(native)) +
            '};fields {' + '\n'.join(fields) + '}}')
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
            declarations.append('relation ' + key(cid) + ' ' + quote(label) + ' @' + key(identity) + ' -> @' +
                key(target['resource_id']) + ' {kind:ref;enforcement:database;uid:' + quote(prefix + cid) +
                ';x_record:{native_json:' + quote(quote(constraint)) + '};}')
            edges.append((identity, target['resource_id'])); mapping[key(cid)] = cid
    views, blocks = [], []
    for start in range(0, len(relations), 25):
        selected = {row['resource_id'] for row in relations[start:start + 25]}
        sources = set(selected)
        selected.update(target for source, target in edges if source in sources)
        if len(selected) > 100 or len(views) >= 64: raise ValueError('DuckDB diagram exceeds view bounds')
        view = 'relations_' + str(len(views) + 1); label = 'DuckDB relations — page ' + str(len(views) + 1)
        blocks.append('view ' + view + ' ' + quote(label) + ' {data:[@relations];select:[' +
            ','.join('@relations.' + key(identity) for identity in sorted(selected)) +
            '];projection {kind:graph;profile:"ddn@1";}layout {algorithm:layered;gap:240px;row_gap:160px;}' +
            'publication {size:content;fit:none;}}')
        views.append({'id': view, 'label': label, 'entry': 'relations.ddn'})
    source = 'ddn "0.6";module "scratchrobin.duckdb.relations";\ndata relations {\n' + '\n'.join(declarations) + '\n}\n' + '\n'.join(blocks)
    if len(source.encode('utf8')) > MAX_BYTES or len(source.encode('utf-16-le')) // 2 > MAX_DDN_UNITS:
        raise ValueError('DuckDB diagram exceeds the paired DDN document bound')
    return {'snapshot': {'format': 'ddn-workspace@1', 'entry': 'relations.ddn', 'view': views[0]['id'], 'files': {'relations.ddn': source}},
            'views': views, 'warnings': warnings, 'resource_mapping': mapping,
            'deployment': 'diagram-only', 'foreign_keys': len(edges)}

"""SQLite file relations and native foreign keys in public DDN views."""

import hashlib
import json

from .firebird_catalog_export import MAX_BYTES, MAX_DDN_UNITS, native_metadata


def build_diagram(resources, provenance):
    def quote(value):
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'),
                          allow_nan=False)

    def key(value):
        return 'n_' + hashlib.sha256(value.encode('utf8')).hexdigest()

    relations = sorted((row for row in resources if row['resource_kind'] in {
        'table', 'view', 'virtual-table', 'fts-table'}),
        key=lambda row: (row['display_path'], row['resource_id']))
    if not relations:
        return None
    by_path = {tuple(row['display_path']): row for row in relations}
    if len(by_path) != len(relations):
        raise ValueError('Ambiguous native SQLite relation paths')
    prefix = ('sqlite:' + provenance['endpoint_id'] + ':' +
              provenance['database_target_id'] + ':')
    declarations, edges, warnings, mapping = [], [], [], {}
    for row in relations:
        identity = row['resource_id']
        native = native_metadata(row, 'sqlite')
        fields = []
        for column in sorted(native.get('columns', []),
                             key=lambda item: item['ordinal_position']):
            column_id = column['resource_id']
            properties = [
                'uid:' + quote(prefix + column_id),
                'nullable:' + ('true' if column['nullable'] else 'false'),
            ]
            if column['data_type']:
                properties.append('datatype:' + quote(column['data_type']))
            fields.append('field ' + key(column_id) + ' ' + quote(column['name']) +
                          ' {' + ';'.join(properties) + ';}')
            mapping[key(column_id)] = column_id
        label = '.'.join(row['display_path'])
        kind = 'view' if row['resource_kind'] == 'view' else 'table'
        declarations.append('object ' + key(identity) + ' ' + quote(label) +
            ' {kind:' + kind + ';uid:' + quote(prefix + identity) +
            ';x_record:{resource_id:' + quote(identity) +
            ',native_kind:' + quote(row['resource_kind']) +
            ',native_json:' + quote(quote(native)) +
            '};fields {' + '\n'.join(fields) + '}}')
        mapping[key(identity)] = identity
        for constraint in native.get('constraints', []):
            if constraint.get('constraint_type') != 'FOREIGN KEY':
                continue
            target = by_path.get((row['display_path'][0],
                                  constraint['referenced_table']))
            if target is None:
                warnings.append('Foreign-key target outside visible selection: ' +
                                constraint['name'])
                continue
            cid = constraint['resource_id']
            label = (constraint['name'] + ' (' +
                     ', '.join(constraint['columns']) + ') -> (' +
                     ', '.join(constraint['referenced_columns']) + ')')
            declarations.append('relation ' + key(cid) + ' ' + quote(label) +
                ' @' + key(identity) + ' -> @' + key(target['resource_id']) +
                ' {kind:ref;enforcement:database;uid:' + quote(prefix + cid) +
                ';x_record:{native_json:' + quote(quote(constraint)) + '};}')
            edges.append((identity, target['resource_id']))
            mapping[key(cid)] = cid
    views, pages = [], []
    for start in range(0, len(relations), 25):
        selected = {row['resource_id'] for row in relations[start:start + 25]}
        selected.update(target for source, target in edges if source in selected)
        if len(selected) > 100 or len(views) >= 64:
            raise ValueError('SQLite diagram exceeds view bounds')
        view = 'relations_' + str(len(views) + 1)
        label = 'SQLite relations — page ' + str(len(views) + 1)
        views.append({'id': view, 'label': label,
                      'entry': 'relations.ddn'})
        pages.append(selected)
    blocks = [
        'view ' + item['id'] + ' ' + quote(item['label']) +
        ' {data:[@relations];select:[' + ','.join(
            '@relations.' + key(identity)
            for identity in sorted(pages[index])) +
        '];projection {kind:graph;profile:"ddn@1";}' +
        'layout {algorithm:layered;gap:240px;row_gap:160px;}' +
        'publication {size:content;fit:none;}}'
        for index, item in enumerate(views)
    ]
    source = ('ddn "0.6";module "scratchrobin.sqlite.relations";\n'
              'data relations {\n' + '\n'.join(declarations) + '\n}\n' +
              '\n'.join(blocks))
    if (len(source.encode('utf8')) > MAX_BYTES or
            len(source.encode('utf-16-le')) // 2 > MAX_DDN_UNITS):
        raise ValueError('SQLite diagram exceeds the paired DDN document bound')
    return {'snapshot': {
        'format': 'ddn-workspace@1', 'entry': 'relations.ddn',
        'view': views[0]['id'], 'files': {'relations.ddn': source}},
        'views': views, 'warnings': warnings,
        'resource_mapping': mapping, 'deployment': 'diagram-only',
        'foreign_keys': len(edges)}

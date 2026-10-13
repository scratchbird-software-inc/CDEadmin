"""Map native MySQL relations/foreign keys into public DDN graph input."""
import hashlib
import json

from .firebird_catalog_export import MAX_BYTES, MAX_DDN_UNITS, native_metadata


def build_diagram(resources, provenance, *, engine='mysql'):
    if engine not in {'mysql', 'mariadb'}:
        raise ValueError('Unsupported relational diagram engine')
    engine_name = 'MariaDB' if engine == 'mariadb' else 'MySQL'
    def quote(value):
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)

    def key(value):
        return 'n_' + hashlib.sha256(value.encode('utf8')).hexdigest()

    relations = sorted((row for row in resources if row['resource_kind'] in {'table', 'view', 'materialized-view'}),
                       key=lambda row: (row['display_path'], row['resource_id']))
    if not relations:
        return None
    by_name = {(native_metadata(row, engine)['database'], row['display_name']): row for row in relations}
    if len(by_name) != len(relations):
        raise ValueError('Ambiguous native ' + engine_name + ' relation identities')
    prefix = engine + ':' + provenance['endpoint_id'] + ':' + provenance['database_target_id'] + ':'
    declarations, edges, warnings, mapping = [], [], [], {}
    for row in relations:
        identity, native = row['resource_id'], native_metadata(row, engine)
        fields = []
        for column in sorted(native.get('children', {}).get('COLUMNS', []), key=lambda item: int(item.get('ordinal_position', 0))):
            cid = identity + ':' + quote(column['column_name'])
            properties = ['uid:' + quote(prefix + cid), 'datatype:' + quote(column['column_type']),
                          'nullable:' + ('false' if column.get('is_nullable') == 'NO' else 'true')]
            if column.get('column_comment'):
                properties.append('description:' + quote(column['column_comment']))
            fields.append('field ' + key(cid) + ' ' + quote(column['column_name']) + ' {' + ';'.join(properties) + ';}')
            mapping[key(cid)] = cid
        shape = 'table' if row['resource_kind'] == 'table' else 'view'
        declarations.append('object ' + key(identity) + ' ' + quote(row['display_name']) +
            ' {kind:' + shape + '; uid:' + quote(prefix + identity) + '; x_record:{resource_id:' + quote(identity) +
            ',native_kind:' + quote(row['resource_kind']) + ',native_json:' + quote(quote(native)) +
            '}; fields {' + '\n'.join(fields) + '}}')
        mapping[key(identity)] = identity
        foreign_keys = {}
        for column in native.get('children', {}).get('KEY_COLUMN_USAGE', []):
            if column.get('referenced_table_name') is not None:
                foreign_keys.setdefault(column['constraint_name'], []).append(column)
        for name, columns in sorted(foreign_keys.items()):
            columns.sort(key=lambda item: int(item['ordinal_position']))
            target = by_name.get((columns[0]['referenced_table_schema'], columns[0]['referenced_table_name']))
            if target is None:
                warnings.append('Referenced relation outside visible selection: ' + name)
                continue
            fk_id = identity + ':foreign-key:' + quote(name)
            label = name + ' (' + ', '.join(item['column_name'] for item in columns) + ') -> (' + ', '.join(item['referenced_column_name'] for item in columns) + ')'
            declarations.append('relation ' + key(fk_id) + ' ' + quote(label) + ' @' + key(identity) + ' -> @' + key(target['resource_id']) +
                ' {kind:ref; enforcement:database; uid:' + quote(prefix + fk_id) + '; x_record:{native_json:' + quote(quote(columns)) + '};}')
            edges.append((identity, target['resource_id']))
            mapping[key(fk_id)] = fk_id
    views, blocks = [], []
    for start in range(0, len(relations), 25):
        selected = {row['resource_id'] for row in relations[start:start + 25]}
        sources = set(selected)
        selected.update(target for source, target in edges if source in sources)
        if len(selected) > 100 or len(views) >= 64:
            raise ValueError('Relational diagram exceeds view bounds; select a smaller native branch')
        view, label = 'relations_' + str(len(views) + 1), engine_name + ' relations — page ' + str(len(views) + 1)
        blocks.append('view ' + view + ' ' + quote(label) + ' {data:[@relations]; select:[' +
            ','.join('@relations.' + key(identity) for identity in sorted(selected)) +
            ']; projection {kind:graph; profile:"ddn@1";} layout {algorithm:layered; gap:240px; row_gap:160px;} publication {size:content; fit:none;} }')
        views.append({'id': view, 'label': label, 'entry': 'relations.ddn'})
    source = 'ddn "0.6"; module "scratchrobin.' + engine + '.relations";\ndata relations {\n' + '\n'.join(declarations) + '\n}\n' + '\n'.join(blocks)
    if len(source.encode('utf8')) > MAX_BYTES or len(source.encode('utf-16-le')) // 2 > MAX_DDN_UNITS:
        raise ValueError('Relational diagram exceeds the paired DDN document bound')
    return {'snapshot': {'format': 'ddn-workspace@1', 'entry': 'relations.ddn', 'view': views[0]['id'], 'files': {'relations.ddn': source}},
            'views': views, 'warnings': warnings, 'resource_mapping': mapping, 'deployment': 'diagram-only', 'foreign_keys': len(edges)}

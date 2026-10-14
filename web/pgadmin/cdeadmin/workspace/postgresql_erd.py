"""Project PostgreSQL catalog facts through the paired DDN graph renderer."""
import hashlib
import json

from .firebird_catalog_export import MAX_DDN_UNITS, MAX_BYTES, native_metadata

RELATIONS = {'table', 'partitioned-table', 'foreign-table', 'view', 'materialized-view'}


def build_diagram(resources, provenance):
    def quoted(value):
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)

    def key(identity):
        return 'n_' + hashlib.sha256(identity.encode('utf8')).hexdigest()

    relations = sorted((row for row in resources if row['resource_kind'] in RELATIONS),
                       key=lambda row: (row['display_path'], row['resource_id']))
    if not relations:
        return None
    by_oid = {int(native_metadata(row, 'postgresql')['oid']): row for row in relations}
    if len(by_oid) != len(relations):
        raise ValueError('Ambiguous native relation identities')
    prefix = 'postgresql:' + provenance['endpoint_id'] + ':' + provenance['database_target_id'] + ':'
    declarations, warnings, edges, mapping, column_names = [], [], [], {}, {}
    for row in relations:
        identity = row['resource_id']
        native = native_metadata(row, 'postgresql')
        fields = []
        columns = sorted(native.get('children', {}).get('pg_attribute', []), key=lambda item: int(item['attnum']))
        if not columns:
            warnings.append('Column metadata unavailable: ' + '.'.join(row['display_path'][1:]))
        for column in columns:
            number = int(column['attnum'])
            column_id = identity + ':' + str(number)
            column_names[(int(native['oid']), number)] = column['attname']
            props = ['uid: ' + quoted(prefix + column_id) + ';']
            if column.get('formatted_type'):
                props.append('datatype: ' + quoted(column['formatted_type']) + ';')
            if column.get('attnotnull') is True:
                props.append('nullable: false;')
            if int(column.get('attndims', 0)) > 0:
                props.append('shape: array;')
            if column.get('comment'):
                props.append('description: ' + quoted(column['comment']) + ';')
            fields.append('field ' + key(column_id) + ' ' + quoted(column['attname']) + ' {' + ' '.join(props) + '}')
            mapping[key(column_id)] = column_id
        shape = 'view' if row['resource_kind'] in {'view', 'materialized-view'} else 'table'
        label = '.'.join(row['display_path'][1:]) + ' [' + row['resource_kind'] + ']'
        declarations.append('object ' + key(identity) + ' ' + quoted(label) + ' {kind: ' + shape +
            '; uid: ' + quoted(prefix + identity) + '; x_record: {resource_id:' + quoted(identity) +
            ', native_kind:' + quoted(row['resource_kind']) + ', native_json:' + quoted(quoted(native)) +
            '}; fields {' + '\n'.join(fields) + '} }')
        mapping[key(identity)] = identity
    for row in resources:
        native = native_metadata(row, 'postgresql')
        facts = native.get('catalog_row', {})
        if native.get('catalog') != 'pg_constraint' or facts.get('contype') != 'f':
            continue
        source_oid, target_oid = int(facts['conrelid']), int(facts['confrelid'])
        if source_oid not in by_oid:
            continue
        if target_oid not in by_oid:
            warnings.append('Referenced relation outside visible selection: ' + row['display_name'] + ' -> OID ' + str(target_oid))
            continue
        source_columns = [column_names.get((source_oid, int(number))) for number in facts.get('conkey', [])]
        target_columns = [column_names.get((target_oid, int(number))) for number in facts.get('confkey', [])]
        if not source_columns or len(source_columns) != len(target_columns) or None in source_columns + target_columns:
            warnings.append('Foreign-key column tuple unavailable: ' + row['display_name'])
            continue
        source, target = by_oid[source_oid]['resource_id'], by_oid[target_oid]['resource_id']
        identity = row['resource_id']
        label = row['display_name'] + ' (' + ', '.join(source_columns) + ') -> (' + ', '.join(target_columns) + ')'
        declarations.append('relation ' + key(identity) + ' ' + quoted(label) + ' @' + key(source) + ' -> @' + key(target) +
            ' {kind: ref; enforcement: database; uid:' + quoted(prefix + identity) +
            '; x_record: {resource_id:' + quoted(identity) + ', native_json:' + quoted(quoted(native)) + '}; }')
        edges.append((source, target))
        mapping[key(identity)] = identity
    views, blocks = [], []
    for start in range(0, len(relations), 25):
        selected = {row['resource_id'] for row in relations[start:start + 25]}
        page_sources = set(selected)
        selected.update(target for source, target in edges if source in page_sources)
        if len(selected) > 100 or len(views) >= 64:
            raise ValueError('Relational diagram exceeds its view bounds; select a smaller native branch')
        view = 'relations_' + str(len(views) + 1)
        label = 'PostgreSQL relations — page ' + str(len(views) + 1)
        blocks.append('view ' + view + ' ' + quoted(label) + ' {data: [@relations]; select: [' +
            ','.join('@relations.' + key(identity) for identity in sorted(selected)) +
            ']; projection {kind: graph; profile: "ddn@1";} layout {algorithm: layered; gap: 240px; row_gap: 160px;} publication {size: content; fit: none;} }')
        views.append({'id': view, 'label': label, 'entry': 'relations.ddn'})
    source = 'ddn "0.6"; module "scratchrobin.postgresql.relations";\ndata relations {\n' + '\n'.join(declarations) + '\n}\n' + '\n'.join(blocks)
    if len(source.encode('utf-16-le')) // 2 > MAX_DDN_UNITS or len(source.encode('utf8')) > MAX_BYTES:
        raise ValueError('Relational diagram exceeds the paired DDN document bound')
    return {'snapshot': {'format': 'ddn-workspace@1', 'entry': 'relations.ddn', 'view': views[0]['id'], 'files': {'relations.ddn': source}},
            'views': views, 'resource_mapping': mapping, 'warnings': warnings,
            'filename': 'postgresql-relations.ddn', 'deployment': 'diagram-only', 'foreign_keys': len(edges)}

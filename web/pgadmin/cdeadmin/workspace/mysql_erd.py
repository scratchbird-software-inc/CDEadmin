"""Map native MySQL relations/foreign keys into public DDN graph input."""
import hashlib
import json
from . import ddn_source as ddn

from .firebird_catalog_export import MAX_BYTES, MAX_DDN_UNITS, native_metadata
from . import mysql_physical as physical


def build_diagram(resources, provenance, *, engine='mysql'):
    module = f'scratchrobin.{engine}.relations'
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
    root = next((native_metadata(item, engine) for item in resources if item['resource_kind'] == 'database'), {})
    mode = root.get('definition_context', {}).get('sql_mode', root.get('catalog_row', {}).get('sql_mode', ''))
    mode = mode if isinstance(mode, str) else ''
    for row in relations:
        identity, native = row['resource_id'], native_metadata(row, engine)
        fields = []
        for column in sorted(native.get('children', {}).get('COLUMNS', []), key=lambda item: int(item.get('ordinal_position', 0))):
            cid = identity + ':' + quote(column['column_name'])
            properties = {'datatype': column['column_type'], 'nullable': column.get('is_nullable') != 'NO'}
            if column.get('column_comment'):
                properties['description'] = column['column_comment']
            fields.append(ddn.native_field(key(cid), column['column_name'], prefix + cid, properties,
                physical.column_values(column['column_name']) if row['resource_kind'] == 'table' else None))
            mapping[key(cid)] = cid
        shape = 'table' if row['resource_kind'] == 'table' else 'view'
        kids, vocabulary, notes = physical.forward(row['display_name'], native, mode, engine) if shape == 'table' else ([], {}, [])
        warnings.extend(notes)
        children = []
        for kid in kids:
            kid_id = identity + ':' + kid['kind'] + ':' + quote(kid['name'])
            children.append({'identity': key(kid_id), 'title': kid['name'], 'role': kid['role'], 'uid': prefix + kid_id,
                'values': {'resource_id': kid_id, 'native_kind': kid['kind'], 'native_json': quote({'clause': kid['clause']}), **kid['values']}})
            mapping[key(kid_id)] = kid_id
        declarations.append(ddn.relation_object(key(identity), row['display_name'], shape, prefix + identity,
            {'resource_id': identity, 'native_kind': row['resource_kind'], 'native_json': quote(native)}, fields, module,
            children, physical.table_values(row['display_name']) if shape == 'table' else None))
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
            declarations.append(ddn.relation_edge(key(fk_id), label, key(identity), key(target['resource_id']),
                prefix + fk_id, {'native_json': quote(columns)}, module,
                vocabulary.get(name, {}).get('values') if shape == 'table' else None))
            edges.append((key(fk_id), identity, target['resource_id']))
            mapping[key(fk_id)] = fk_id
    views, blocks = [], []
    for start in range(0, len(relations), 25):
        selected = {row['resource_id'] for row in relations[start:start + 25]}
        sources = set(selected)
        selected.update(target for _, source, target in edges if source in sources)
        if len(selected) > 100 or len(views) >= 64:
            raise ValueError('Relational diagram exceeds view bounds; select a smaller native branch')
        view, label = 'relations_' + str(len(views) + 1), engine_name + ' relations — page ' + str(len(views) + 1)
        blocks.append(ddn.graph_view(view, label, [key(identity) for identity in sorted(selected)],
            [(edge, key(source), key(target)) for edge, source, target in edges]))
        views.append({'id': view, 'label': label, 'entry': 'relations.ddn'})
    source = ddn.header(module) + '\n'.join(declarations + blocks)
    if len(source.encode('utf8')) > MAX_BYTES or len(source.encode('utf-16-le')) // 2 > MAX_DDN_UNITS:
        raise ValueError('Relational diagram exceeds the paired DDN document bound')
    return {'snapshot': {'format': 'ddn-source-workspace@1', 'entry': 'relations.ddn', 'view': views[0]['id'], 'files': {'relations.ddn': source}},
            'views': views, 'warnings': warnings, 'resource_mapping': mapping, 'deployment': 'diagram-only', 'foreign_keys': len(edges)}

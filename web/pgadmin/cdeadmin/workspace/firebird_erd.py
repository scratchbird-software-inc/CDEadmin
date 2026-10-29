"""Native relational facts projected through the paired DDN graph renderer."""
import hashlib
import json
from . import ddn_source as ddn
from .firebird_catalog_export import native_metadata, MAX_DDN_UNITS, MAX_BYTES
from . import firebird_physical as physical
from ..providers.firebird.column_type_metadata import type_editor_values
from ..providers.firebird.columns import data_type
from ..sdk.relational import RelationalClientError


def build_diagram(resources, provenance):
    module = 'scratchrobin.firebird.relations'
    def quoted(value):
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    def key(identity):
        return 'n_' + hashlib.sha256(identity.encode()).hexdigest()
    relations = [row for row in resources if row['resource_kind'] in {'table', 'view'}]
    if not relations:
        return None
    relations.sort(key=lambda row: (row['display_name'], row['resource_id']))
    by_name = {row['display_name']: row for row in relations}
    if len(by_name) != len(relations):
        raise ValueError('Ambiguous native relation names in diagram scope')
    domains = {row['display_name']: native_metadata(row) for row in resources if row['resource_kind'] == 'domain'}
    indexes = {row['display_name']: native_metadata(row) for row in resources if row['resource_kind'] == 'index'}
    warnings, declarations, edges, mapping = [], [], [], {}
    groups, catalog = physical.forward(resources), physical.resource_map(resources)
    children = {}
    for item in resources:
        if item['resource_kind'] == 'column':
            children.setdefault(tuple(item.get('display_path', [])[:-1]), []).append(item)
    prefix = 'firebird:' + provenance['endpoint_id'] + ':' + str(provenance['database_target_id']) + ':'
    for row in relations:
        identity, name = row['resource_id'], row['display_name']
        native = native_metadata(row)
        columns = sorted(children.get(tuple(row.get('display_path', [])), []),
                         key=lambda item: (int(native_metadata(item).get('position') or 0), item['display_name']))
        fields = []
        if not columns:
            warnings.append('Column metadata unavailable: ' + name)
        for column in columns:
            facts = native_metadata(column)
            typed = type_editor_values(facts)
            try:
                label = data_type(typed) if typed else None
            except RelationalClientError:
                label = None
            dimensions = facts.get('array_dimensions') or domains.get(facts.get('domain'), {}).get('array_dimensions')
            array = (bool(dimensions) or facts.get('alteration', {}).get('array') is True or
                     str(facts.get('dimensions') or '0') != '0')
            if dimensions:
                label = (label or 'Unknown native type') + '[' + ','.join(
                    str(part['lower_bound']) + ':' + str(part['upper_bound']) for part in dimensions) + ']'
            elif array:
                label = (label or 'Unknown native type') + ' [array bounds unavailable]'
                warnings.append('Array bounds unavailable: ' + name + '.' + column['display_name'])
            if label is None:
                warnings.append('Native type unavailable: ' + name + '.' + column['display_name'])
            props = {}
            if array: props['shape'] = 'array'
            if label is not None: props['datatype'] = label
            if str(facts.get('not_null')) == '1' or str(facts.get('domain_not_null')) == '1': props['nullable'] = False
            if facts.get('description'): props['description'] = facts['description']
            fields.append(ddn.native_field(key(column['resource_id']), column['display_name'],
                prefix + column['resource_id'], props, physical.column_values(column['display_name'])))
            mapping[key(column['resource_id'])] = column['resource_id']
        captured = {**native, 'diagram_columns': [{'resource_id': col['resource_id'], 'native': native_metadata(col)} for col in columns]}
        owned = []
        for item in groups.get(name, []) if row['resource_kind'] == 'table' else []:
            child = item['row']['resource_id']
            owned.append({'identity': key(child), 'title': item['row']['display_name'], 'role': item['role'],
                'uid': prefix + child, 'values': {'resource_id': child, 'native_kind': item['row']['resource_kind'],
                    'native_json': quoted(native_metadata(item['row'])), **item['values']}})
            mapping[key(child)] = child
        declarations.append(ddn.relation_object(key(identity), name, row['resource_kind'], prefix + identity,
            {'resource_id': identity, 'native_json': quoted(captured)}, fields, module, owned,
            physical.table_values(name) if row['resource_kind'] == 'table' else None))
        mapping[key(identity)] = identity
    for row in resources:
        facts = native_metadata(row)
        if row['resource_kind'] != 'constraint' or facts.get('constraint_type') != 'FOREIGN KEY':
            continue
        source_name = row['display_path'][-2]
        target_name = facts.get('referenced_relation')
        if source_name not in by_name:
            continue
        if target_name not in by_name:
            warnings.append('Referenced relation outside visible selection: ' + row['display_name'] + ' -> ' + str(target_name))
            continue
        def segments(index):
            return [item['field_name'] for item in sorted(indexes.get(index, {}).get('segments', []), key=lambda item: int(item['position']))]
        source_columns, target_columns = segments(facts.get('index_name')), segments(facts.get('referenced_index'))
        if not source_columns or len(source_columns) != len(target_columns):
            warnings.append('Foreign-key column tuple unavailable: ' + row['display_name'])
        source_id, target_id = by_name[source_name]['resource_id'], by_name[target_name]['resource_id']
        identity = row['resource_id']
        label = row['display_name'] + ' (' + ', '.join(source_columns) + ') -> (' + ', '.join(target_columns) + ')'
        declarations.append(ddn.relation_edge(key(identity), label, key(source_id), key(target_id),
            prefix + identity, {'resource_id': identity, 'native_json': quoted({**facts,
                'source_columns': source_columns, 'target_columns': target_columns})}, module,
            physical.edge_values(row, catalog)))
        edges.append((key(identity), source_id, target_id)); mapping[key(identity)] = identity
    views, blocks = [], []
    for start in range(0, len(relations), 25):
        selected = {row['resource_id'] for row in relations[start:start + 25]}
        selected.update(target for _, source, target in edges if source in selected)
        if len(selected) > 100:
            raise ValueError('Relational diagram view exceeds 100 objects; select a smaller branch')
        if len(views) >= 64:
            raise ValueError('Relational diagram exceeds 64 views; select a smaller branch')
        view_id = 'relations_' + str(len(views) + 1)
        label = 'Firebird relations — page ' + str(len(views) + 1)
        blocks.append(ddn.graph_view(view_id, label, [key(identity) for identity in sorted(selected)],
            [(edge, key(source), key(target)) for edge, source, target in edges]))
        views.append({'id': view_id, 'label': label, 'entry': 'relations.ddn'})
    source = ddn.header(module) + '\n'.join(declarations + blocks)
    if len(source.encode('utf-16-le')) // 2 > MAX_DDN_UNITS or len(source.encode()) > MAX_BYTES:
        raise ValueError('Relational diagram exceeds the paired DDN document limit; select a smaller branch')
    return {'snapshot': {'format': 'ddn-source-workspace@1', 'entry': 'relations.ddn', 'view': views[0]['id'], 'files': {'relations.ddn': source}},
            'views': views, 'resource_mapping': mapping, 'warnings': warnings,
            'filename': 'firebird-relations.ddn', 'deployment': 'diagram-only', 'foreign_keys': len(edges)}

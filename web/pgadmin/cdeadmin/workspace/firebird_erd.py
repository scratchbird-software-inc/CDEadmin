"""Native relational facts projected through the paired DDN graph renderer."""
import hashlib
import json
from .firebird_catalog_export import native_metadata, MAX_DDN_UNITS, MAX_BYTES
from ..providers.firebird.column_type_metadata import type_editor_values
from ..providers.firebird.columns import data_type
from ..sdk.relational import RelationalClientError


def build_diagram(resources, provenance):
    def quoted(value):
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    def key(identity):
        return 'n_' + hashlib.sha256(identity.encode()).hexdigest()
    def metadata(identity, native=None):
        values = {'resource_id': identity}
        if native is not None:
            values['native_json'] = quoted(native)
        return 'x_record: {' + ','.join(name + ':' + quoted(value) for name, value in values.items()) + '};'
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
            props = ['uid: ' + quoted(prefix + column['resource_id']) + ';']
            if array:
                props.append('shape: array;')
            if label is not None:
                props.append('datatype: ' + quoted(label) + ';')
            # Domain nullability can add restrictions to the column flag. Do
            # not assert nullable=true from an absent relation-field flag.
            if str(facts.get('not_null')) == '1' or str(facts.get('domain_not_null')) == '1':
                props.append('nullable: false;')
            if facts.get('description'):
                props.append('description: ' + quoted(facts['description']) + ';')
            fields.append('field ' + key(column['resource_id']) + ' ' + quoted(column['display_name']) +
                          ' {' + ' '.join(props) + '}')
            mapping[key(column['resource_id'])] = column['resource_id']
        declarations.append('object ' + key(identity) + ' ' + quoted(name) + ' {kind: ' + row['resource_kind'] +
                            '; uid: ' + quoted(prefix + identity) + '; ' + metadata(identity, {**native, 'diagram_columns': [{'resource_id': col['resource_id'], 'native': native_metadata(col)} for col in columns]}) +
                            ' fields {' + '\n'.join(fields) + '} }')
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
        declarations.append('relation ' + key(identity) + ' ' + quoted(label) + ' @' + key(source_id) + ' -> @' + key(target_id) +
                            ' {kind: ref; enforcement: database; uid: ' + quoted(prefix + identity) + '; ' +
                            metadata(identity, {**facts, 'source_columns': source_columns, 'target_columns': target_columns}) + '}')
        edges.append((source_id, target_id)); mapping[key(identity)] = identity
    callouts = {key(row['resource_id']): number for number, row in enumerate(
        [row for row in resources if row['resource_kind'] == 'constraint' and key(row['resource_id']) in mapping], 1)}
    views, blocks = [], []
    for start in range(0, len(relations), 25):
        selected = {row['resource_id'] for row in relations[start:start + 25]}
        selected.update(target for source, target in edges if source in selected)
        if len(selected) > 100:
            raise ValueError('Relational diagram view exceeds 100 objects; select a smaller branch')
        if len(views) >= 64:
            raise ValueError('Relational diagram exceeds 64 views; select a smaller branch')
        view_id = 'relations_' + str(len(views) + 1)
        label = 'Firebird relations — page ' + str(len(views) + 1)
        blocks.append('view ' + view_id + ' ' + quoted(label) + ' {data: [@relations]; select: [' +
                      ','.join('@relations.' + key(identity) for identity in sorted(selected)) +
                      ']; projection {kind: graph; profile: "ddn@1";} layout {algorithm: layered; gap: 240px; row_gap: 160px;} legend {mode: numbers; placement: right; keys: ' + quoted(callouts) + ';} publication {size: content; fit: none;} }')
        views.append({'id': view_id, 'label': label, 'entry': 'relations.ddn'})
    source = 'ddn "0.6"; module "scratchrobin.firebird.relations";\ndata relations {\n' + '\n'.join(declarations) + '\n}\n' + '\n'.join(blocks)
    if len(source.encode('utf-16-le')) // 2 > MAX_DDN_UNITS or len(source.encode()) > MAX_BYTES:
        raise ValueError('Relational diagram exceeds the paired DDN document limit; select a smaller branch')
    return {'snapshot': {'format': 'ddn-workspace@1', 'entry': 'relations.ddn', 'view': views[0]['id'], 'files': {'relations.ddn': source}},
            'views': views, 'resource_mapping': mapping, 'warnings': warnings,
            'filename': 'firebird-relations.ddn', 'deployment': 'diagram-only', 'foreign_keys': len(edges)}

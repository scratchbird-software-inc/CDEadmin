"""Emit the adopted DDN source notation; native metadata stays namespaced data.

This is an encoder, never an alternative parser or renderer. Consumers admit
the result through the standalone DDN language/runtime/verifier APIs.
"""
import json
import math

CONTRACT = 'ddn-next-1'
FORMAT = 'ddn-source-workspace@1'
# The adopted verifier's source/model records require a larger bounded worker
# heap than the former parser. The web process and input limits are unchanged.
NODE_HEAP_OPTION = '--max-old-space-size=384'


def quoted(value):
    value = str(value)
    if '\n' in value or '\r' in value or '\0' in value:
        raise ValueError('DDN structural identifiers cannot contain line breaks or NUL')
    return '"' + value.replace('"', '""') + '"'


def _scalar(value):
    if isinstance(value, str):
        return quoted(value)
    if value is None or isinstance(value, bool) or type(value) in (int, float):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('DDN numbers must be finite')
        return json.dumps(value, allow_nan=False)
    raise ValueError('Unsupported DDN scalar')


def _value(key, value, indent):
    lead = ' ' * indent + key
    if isinstance(value, dict):
        return (lead + '\n' + properties(value, indent + 4)) if value else lead + ' empty record\n'
    if isinstance(value, (tuple, list)):
        return (lead + '\n' + ''.join(_value('item', item, indent + 4) for item in value)) if value else lead + ' empty list\n'
    if isinstance(value, str) and ('\n' in value or '\r' in value):
        # Literal property bodies preserve text; structural names use opaque ids.
        return lead + '\n' + '\n'.join(' ' * (indent + 4) + line for line in value.split('\n')) + '\n'
    return lead + ' ' + _scalar(value) + '\n'


def properties(values, indent=8):
    return ''.join(_value(quoted(key) if key == 'item' or any(c.isspace() or c in '\"\'' for c in key) else key,
                          value, indent) for key, value in values.items())


def declaration(kind, identity, role, values):
    return (kind + ' ' + quoted(identity) + (' as ' + quoted(role) if role else '') +
            '\n    with\n' + properties({'id': identity, **values}) + '\n')


def header(module):
    return 'version ' + CONTRACT + '\n// ScratchRobin mapping: ' + module + '\n\n'


def validate_workspace(value, label='DDN source'):
    if (not isinstance(value, dict) or set(value) != {'format', 'entry', 'view', 'files'} or
            value['format'] != FORMAT or not isinstance(value['files'], dict) or
            not 1 <= len(value['files']) <= 64 or not isinstance(value['entry'], str) or
            value['entry'] not in value['files'] or not isinstance(value['view'], str) or not value['view']):
        raise ValueError('Invalid ' + label + ' workspace')
    for name, source in value['files'].items():
        if (not isinstance(name, str) or len(name) > 1024 or not name.endswith('.ddn') or
                any(part in {'', '.', '..'} for part in name.split('/')) or
                any(char in name for char in '\\:\0') or not isinstance(source, str) or
                len(source.encode('utf-16-le')) // 2 > 2000000):
            raise ValueError('Invalid ' + label + ' file')
    encoded = json.dumps(value, ensure_ascii=False)
    if len(encoded.encode('utf-8')) > 8 * 1024 * 1024:
        raise ValueError('DDN design exceeds 8 MiB')
    return encoded


def record_definition(identity, title, fields, *, module, block, uid=None):
    facts = {'module': module, 'block': block, 'record': fields, 'name_json': json.dumps(title, ensure_ascii=False)}
    if uid is not None:
        facts['uid'] = uid
    exact = {}
    def text_values(value, path=()):
        if isinstance(value, dict):
            return {key: text_values(child, (*path, key)) for key, child in value.items()}
        if isinstance(value, list):
            return [text_values(child, (*path, index)) for index, child in enumerate(value)]
        if isinstance(value, str) and any(char in value for char in '\r\n\0'):
            exact[json.dumps(path, separators=(',', ':'))] = value
            return _display(value)
        return value
    facts = text_values(facts)
    if exact:
        facts['exact_text_json'] = json.dumps(exact, ensure_ascii=False, separators=(',', ':'))
    return declaration('element', block + '.' + identity, 'record',
                       {'title': _label(title), 'metadata': {'x_record': facts}})


def ref(identity, filename=None):
    return {'id': identity, **({'file': filename} if filename else {})}


def column_path(key):
    return ('title' if key == 'name' else
            'metadata.x_record.record.' + key[9:] if key.startswith('x_record.') else key)


def table_view(identity, title, records, columns):
    refs = [ref(item) if isinstance(item, str) else item for item in records]
    options = {'records': refs, 'columns': [
        {'id': 'c_' + str(index), 'path': column_path(column['key']), 'label': column['label']}
        for index, column in enumerate(columns)]}
    return declaration('view', identity, 'table.records@1', {
        'title': title, 'selection': {'include': refs}, 'projection': {'options': options}})


def connect_files(files):
    if len(files) > 1:
        root = next(iter(files))
        for name in files:
            targets = list(files) if name == root else [root]
            files[name] += ''.join('\ninclude ' + quoted(target) + '\n' for target in targets if target != name)
            if len(files[name].encode('utf-16-le')) // 2 > 2000000:
                raise ValueError('DDN linked source exceeds its per-file limit')
    return files


def workspace(files, entry, view):
    return {'format': FORMAT, 'entry': entry,
            'view': view, 'files': files}


def _display(value):
    return json.dumps(value, ensure_ascii=False)[1:-1] if isinstance(value, str) and any(char in value for char in "\r\n\0") else value


def _label(value):
    text = str(_display(value))
    if len(text.encode('utf-16-le')) <= 2048:
        return text
    prefix = text[:1023]
    while len(prefix.encode('utf-16-le')) > 2046:
        prefix = prefix[:-1]
    return prefix + '…'


def native_field(identity, title, uid, values):
    content = {key: value for key, value in values.items() if key in {'datatype', 'nullable'}}
    return {'identity': identity, 'title': title, 'uid': uid, 'values': values,
            'source': declaration('element', identity, 'field', {
                'title': _label(title), **({'content': content} if content else {}),
                **({'description': _display(values['description'])} if 'description' in values else {})})}


def annotation(identity, title, uid, values, module):
    # The public record role admits typed x_record data. Other roles have
    # restricted metadata schemas; never invent fields on those roles.
    return record_definition('mapping_' + identity, title,
                             {'subject_id': identity, **values}, module=module,
                             block='relations', uid=uid)


def relation_object(identity, title, role, uid, native, fields, module):
    source = ''.join(field['source'] + annotation(field['identity'], field['title'],
        field['uid'], {'subject_kind': 'field', 'parent_id': identity,
                       'field_title_json': json.dumps(field['title'], ensure_ascii=False),
                       'field_properties_json': json.dumps(field['values'], ensure_ascii=False)}, module) for field in fields)
    return source + declaration('element', identity, role, {
        'title': _label(title), 'members': [ref(field['identity']) for field in fields]}) + annotation(
            identity, title, uid, {'subject_kind': role, **native}, module)


def relation_edge(identity, title, source, target, uid, native, module):
    return declaration('relation', identity, 'ref', {'title': title,
        'properties': {'enforcement': 'database'},
        'endpoints': [{'definition': ref(source)}, {'definition': ref(target)}]}) + annotation(
            identity, title, uid, {'subject_kind': 'ref', **native}, module)


def graph_view(identity, title, selected, edges=()):
    edge_ids = sorted(edge for edge, source, target in edges
                      if source in selected and target in selected)
    included = list(selected) + edge_ids
    result = declaration('view', identity, 'ddn@1', {'title': title,
        'selection': {'include': [ref(item) for item in included]},
        'layout': {'algorithm': 'layered', 'gap': 240},
        'legend': {'mode': 'numbers', 'placement': 'bottom',
                   'keys': {edge: str(index + 1) for index, edge in enumerate(edge_ids)}}})
    for item in included:
        result += '    use ' + quoted(item) + ' named ' + quoted('appearance:' + identity + ':' + item) + '\n'
    return result + '\n'

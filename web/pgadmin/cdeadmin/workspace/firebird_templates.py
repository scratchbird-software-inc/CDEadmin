"""Native object-context source templates; rendering never executes SQL."""
import re
from .firebird_catalog_export import native_metadata
from ..providers.firebird.character_metadata import identifier

TOKENS = {'object', 'columns', 'insert_columns', 'values', 'assignments',
          'key_predicate', 'definition', 'new_object'}
DEFAULTS = {
    'select': 'SELECT {{columns}} FROM {{object}};',
    'insert': 'INSERT INTO {{object}} ({{insert_columns}}) VALUES ({{values}});',
    'update': 'UPDATE {{object}} SET {{assignments}} WHERE {{key_predicate}};',
    'delete': 'DELETE FROM {{object}} WHERE {{key_predicate}};',
    'trigger': 'CREATE TRIGGER {{new_object}} FOR {{object}} ACTIVE BEFORE INSERT POSITION 0\nAS\nBEGIN\n  /* Add the trigger body here. */\nEND;',
    'procedure': 'CREATE PROCEDURE {{new_object}}\nAS\nBEGIN\n  /* Add parameters, declarations and body here. */\nEND;',
    'execute-block': 'EXECUTE BLOCK\nAS\nBEGIN\n  /* Add declarations and body here. */\nEND;',
    'definition': '{{definition}}',
}


def context(snapshot, resource_id):
    objects = {row['resource_id']: row for row in snapshot['resources']}
    selected = objects.get(resource_id)
    if selected is None:
        raise ValueError('Selected native object is unavailable')
    kind = selected['resource_kind']
    columns = []
    if kind in {'table', 'view'}:
        columns = [row for row in objects.values() if row['resource_kind'] == 'column' and
                   row.get('display_path', [])[:-1] == selected.get('display_path', [])]
        columns.sort(key=lambda row: (int(native_metadata(row).get('position') or 0), row['display_name']))
    writable = [row for row in columns if native_metadata(row).get('computed_source') is None and
                str(native_metadata(row).get('identity_type')) != '0']
    definitions = native_metadata(selected).get('ddl')
    substitutions = {'object': identifier(selected['display_name']),
        'columns': ', '.join(identifier(row['display_name']) for row in columns),
        'insert_columns': ', '.join(identifier(row['display_name']) for row in writable),
        'values': ', '.join('?' for _row in writable),
        'assignments': ', '.join(identifier(row['display_name']) + ' = ?' for row in writable),
        'key_predicate': 'FALSE /* replace with the intended row key predicate */',
        'definition': definitions}
    templates = {'execute-block': DEFAULTS['execute-block'], 'procedure': DEFAULTS['procedure']}
    if definitions:
        templates['definition'] = DEFAULTS['definition']
    if columns:
        templates['select'] = DEFAULTS['select']
        native = native_metadata(selected)
        if kind == 'table' and native.get('system_object') is not True and str(native.get('relation_type')) in {'0', '2', '4', '5'}:
            if writable:
                templates['insert'] = DEFAULTS['insert']
            if str(native.get('relation_type')) != '2':
                if writable:
                    templates['update'] = DEFAULTS['update']
                templates['delete'] = DEFAULTS['delete']
    if kind == 'table' and native_metadata(selected).get('system_object') is not True and str(native_metadata(selected).get('relation_type')) in {'0', '2', '4', '5'}:
        templates['trigger'] = DEFAULTS['trigger']
    return {'resource_id': resource_id, 'resource_kind': kind, 'name': selected['display_name'],
            'generation': snapshot['generation'], 'templates': templates, 'substitutions': substitutions,
            'parameter_columns': [row['display_name'] for row in writable],
            'definition_unavailable': native_metadata(selected).get('ddl_unavailable_reason') if not definitions else None,
            'authority': 'source template only; native preparation and permissions remain authoritative'}


def render(context, template, new_name=None):
    if not isinstance(template, str) or not template.strip() or len(template.encode('utf-8')) > 65536 or '\0' in template:
        raise ValueError('Template must contain 1–65536 UTF-8 bytes without NUL')
    values = dict(context['substitutions'])
    if new_name:
        values['new_object'] = identifier(new_name)
    def replace(match):
        token = match.group(1).strip()
        if token not in TOKENS or not isinstance(values.get(token), str) or not values[token]:
            raise ValueError('Template substitution is unavailable: ' + token)
        return values[token]
    source = re.sub(r'\{\{([^{}]*)\}\}', replace, template)
    if '{{' in source or '}}' in source:
        # Detect malformed template syntax before substituting native text:
        # native definitions can legitimately contain these characters.
        stripped = re.sub(r'\{\{[^{}]*\}\}', '', template)
        if '{{' in stripped or '}}' in stripped:
            raise ValueError('Malformed template substitution')
    if len(source.encode('utf-8')) > 1024 * 1024:
        raise ValueError('Rendered source exceeds 1 MiB')
    return {'source': source, 'executed': False,
            'parameters': [None] * len(context['parameter_columns']) if template in (DEFAULTS['insert'], DEFAULTS['update']) else [],
            'parameter_policy': 'Replace NULL placeholders; custom templates require explicit ordered parameters',
            'generation': context['generation'],
            'resource_id': context['resource_id']}

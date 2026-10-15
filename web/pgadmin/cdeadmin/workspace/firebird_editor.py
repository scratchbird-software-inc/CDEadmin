"""Display hints from the admitted lexical inventory, not grammar approval."""
import json
from pathlib import Path
import re


def languages(values):
    result = [dict(value) for value in values]
    selected = [value for value in result if value.get('language_profile') == 'firebird-sql']
    if selected:
        path = Path(__file__).parents[1] / 'providers/firebird/firebird_dialect_5_0_4.json'
        contract = json.loads(path.read_text())
        words = sorted({item['native_name'] for item in contract['inventories']['lexical_rules']
                        if re.fullmatch(r'[A-Z][A-Z0-9_$]*', item['native_name'])})
        for value in selected:
            value['editor'] = {'keywords': ' '.join(words), 'reference_version': contract['reference_version'],
                               'reserved_words': [item['native_name'] for item in contract['inventories']['lexical_rules']
                                                  if not item.get('non_reserved') and item['native_name'] in words],
                               'authority': 'lexical display only; native engine validates SQL'}
    return result


COMPLETION_KINDS = frozenset({'table', 'view', 'column', 'procedure', 'function',
    'external-function', 'package', 'sequence', 'domain', 'exception',
    'collation', 'character-set'})


def metadata(snapshot):
    from .firebird_catalog_export import native_metadata
    resources, total, size = [], 0, 0
    for item in snapshot['resources']:
        kind = item['resource_kind']
        if kind not in COMPLETION_KINDS:
            continue
        native = native_metadata(item)
        if native.get('package') and (str(native.get('private_flag')) != '0'):
            continue  # Private/unknown package members are not public names.
        total += 1
        if len(resources) >= 25000:
            continue
        entry = {key:item.get(key) for key in ('resource_id','resource_kind','display_name','display_path')}
        if kind in {'procedure','function','external-function'}:
            entry['package_name'] = native.get('package')
            parameters = native.get('parameters', [])
            entry['parameters'] = [{key:parameter.get(key) for key in ('name','mode','position')}
                for parameter in parameters[:256] if isinstance(parameter,dict)]
            entry['parameters_truncated'] = len(parameters)>256
        count = len(json.dumps(entry, ensure_ascii=False).encode('utf-8'))
        if size + count > 8 * 1024 * 1024:
            continue
        size += count
        resources.append(entry)
    return {'resources':resources, 'generation':snapshot['generation'],
        'truncated':total>len(resources), 'visible_resource_count':total,
        'coverage':'Native visible relations, columns, public routines/packages, sequences, types and exceptions; inaccessible metadata is not inferred'}

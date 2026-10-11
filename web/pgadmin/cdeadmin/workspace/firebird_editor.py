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

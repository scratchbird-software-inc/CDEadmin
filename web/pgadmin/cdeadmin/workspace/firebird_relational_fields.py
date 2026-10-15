"""Translate explicit DDN field edits into exact Firebird catalog facts.

Native JSON remains authoritative for defaults, arrays, identities, computed
expressions and lifecycle intent. The ordinary native planner owns admission,
conversion, permissions, dependency checks and execution.
"""
from copy import deepcopy
import re

from .firebird_catalog_import import _equal
from ..providers.firebird.columns import data_type

_IDENTIFIER = r'(?:"(?:[^"]|"")+"|[A-Za-z_][A-Za-z_0-9$]*)'
_SCALAR = {name: (code, length) for name, code, length in (
    ('SMALLINT', 7, 2), ('INTEGER', 8, 4), ('BIGINT', 16, 8), ('INT128', 26, 16),
    ('FLOAT', 10, 4), ('DOUBLE PRECISION', 27, 8), ('BOOLEAN', 23, 1),
    ('DATE', 12, 4), ('TIME', 13, 4), ('TIMESTAMP', 35, 8),
    ('TIME WITH TIME ZONE', 28, 8), ('TIMESTAMP WITH TIME ZONE', 29, 12),
    ('TIME WITHOUT TIME ZONE', 13, 4), ('TIMESTAMP WITHOUT TIME ZONE', 35, 8))}


def identifier(value):
    return value[1:-1].replace('""', '"') if value.startswith('"') else value.upper()


def descriptor(source, current):
    if not isinstance(source, str) or not source.strip() or len(source) > 512:
        raise ValueError('Graphical datatype requires bounded native type text')
    text = source.strip()
    upper = re.sub(r'\s+', ' ', text.upper())
    facts = dict(field_type=None, field_sub_type=0, field_scale=0,
                 field_precision=None, character_length=None, segment_length=None,
                 character_set=None, collation=None, dimensions=0, array_dimensions=[])
    if upper in _SCALAR:
        facts['field_type'], facts['field_length'] = _SCALAR[upper]
        return facts
    numeric = re.fullmatch(r'(NUMERIC|DECIMAL)\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)', upper)
    if numeric:
        name, precision, scale = numeric.group(1), int(numeric.group(2)), int(numeric.group(3))
        data_type({'data_type': name, 'precision': precision, 'scale': scale})
        code = 7 if name == 'NUMERIC' and precision <= 4 else 8 if precision <= 9 else 16 if precision <= 18 else 26
        facts.update(field_type=code, field_length={7: 2, 8: 4, 16: 8, 26: 16}[code],
                     field_sub_type=1 if name == 'NUMERIC' else 2, field_precision=precision, field_scale=-scale)
        return facts
    decimal = re.fullmatch(r'DECFLOAT\s*\(\s*(16|34)\s*\)', upper)
    if decimal:
        precision = int(decimal.group(1))
        facts.update(field_type=24 if precision == 16 else 25,
                     field_length=8 if precision == 16 else 16, field_precision=precision)
        return facts
    character = re.fullmatch(r'(CHAR|VARCHAR|BINARY|VARBINARY)\s*\(\s*(\d+)\s*\)'
        r'(?:\s+CHARACTER\s+SET\s+(' + _IDENTIFIER + r'))?'
        r'(?:\s+COLLATE\s+(' + _IDENTIFIER + r'))?', text, re.IGNORECASE)
    if character:
        name, length, charset, collation = character.groups()
        name, length = name.upper(), int(length)
        binary = name in {'BINARY', 'VARBINARY'}
        if binary and (charset or collation):
            raise ValueError('Binary graphical types do not accept character set or collation clauses')
        if not binary and not charset:
            raise ValueError('Character graphical types require explicit CHARACTER SET')
        charset = 'OCTETS' if binary else identifier(charset)
        sets = [row for row in current['rows'].values() if row['kind'] == 'character-set' and row['name'] == charset]
        if len(sets) != 1:
            raise ValueError('Graphical character set must be observed in the target catalog')
        collation = identifier(collation) if collation else sets[0]['native'].get('default_collation')
        matches = [row for row in current['rows'].values() if row['kind'] == 'collation' and row['name'] == collation
                   and row['native'].get('character_set') == charset]
        if len(matches) != 1:
            raise ValueError('Graphical collation must be observed for the selected character set')
        width = sets[0]['native'].get('bytes_per_character')
        if not str(width).isdigit() or not 1 <= int(width) <= 4:
            raise ValueError('Character width is not observed')
        data_type({'data_type': name, 'length': length, **({} if binary else {'character_set': charset})})
        facts.update(field_type=14 if name in {'CHAR', 'BINARY'} else 37,
                     field_sub_type=1 if binary else 0, field_length=length*int(width),
                     character_length=length, character_set=charset, collation=collation)
        return facts
    raise ValueError('Graphical datatype cannot be represented losslessly; edit the explicit native definition for domains, arrays or specialized types')


def merge_fields(before, desired, current):
    original, edited = before.get('fields', {}), desired.get('fields', {})
    result = deepcopy(desired['native'])
    for property_name in ('datatype', 'nullable', 'description'):
        if property_name not in edited or _equal(edited[property_name], original.get(property_name)):
            continue  # Field/property omissions never mean removal.
        value = edited[property_name]
        if property_name == 'datatype':
            if (str(before['native'].get('dimensions') or '0') != '0' or
                    before['native'].get('array_dimensions')):
                raise ValueError('Array changes require exact native layout and lifecycle review')
            if before['native'].get('domain') and not before['native']['domain'].startswith('RDB$'):
                raise ValueError('Named-domain rebinding requires explicit native lifecycle intent')
            changes = descriptor(value, current)
            # A scalar edit does not alter its native array-layout markers.
            changes.pop('dimensions', None)
            changes.pop('array_dimensions', None)
        elif property_name == 'nullable':
            if type(value) is not bool:
                raise ValueError('Graphical nullable must be boolean')
            if value and str(before['native'].get('domain_not_null') or '0') == '1':
                raise ValueError('An inherited NOT NULL domain requires explicit domain review')
            changes = {'not_null': None if value else 1}
        else:
            if not isinstance(value, str) or '\0' in value:
                raise ValueError('Graphical description must be text; empty text clears it')
            changes = {'description': value or None}
        for key, fact in changes.items():
            prior, authored = before['native'].get(key), result.get(key)
            # Native catalog numbers are often decimal strings. Compare their
            # scalar spellings without treating Boolean true as integer one.
            same = lambda a, b: _equal(a, b) or (type(a) in (int, str) and type(b) in (int, str) and str(a) == str(b))
            if not same(prior, authored) and not same(authored, fact):
                raise ValueError('Graphical and native column edits disagree: ' + key)
            result[key] = fact
    return result

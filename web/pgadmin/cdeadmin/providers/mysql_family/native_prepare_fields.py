"""Translate result-column packets exposed by the retained C connectors."""

from .mysql_charsets import codec


def native_fields(rows, charset, type_name):
    return [
        {
            'position': index, 'name': name.decode(codec(charset)),
            'native_type': type_name(code) or str(code), 'type_code': code,
            'flags': flags, 'charset_id': charset_id, 'length': length, 'decimals': decimals,
        }
        for index, (name, code, flags, charset_id, length, decimals) in enumerate(rows, start=1)
    ]


def parameter_slots(count):
    return [{'position': index, 'name': '?'} for index in range(1, count + 1)]

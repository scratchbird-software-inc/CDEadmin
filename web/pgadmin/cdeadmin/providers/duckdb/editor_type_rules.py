"""Pinned aggregate result shapes, admitted by complete native function facts.

These rules describe completion types; they do not accept SQL grammar, bind an
arbitrary function, evaluate arguments or infer a replacement for native values.
Any visible non-core homonym disables the corresponding rule conservatively.
"""


def aggregate_type_rules(version, functions, truncated):
    if str(version).removeprefix('v') != '1.5.2' or truncated:
        return {}
    result = {}
    for name in ('min', 'max', 'first', 'last', 'any_value', 'arbitrary', 'list', 'array_agg'):
        rows = [row for row in functions if str(row[2]).lower() == name]
        if not rows or any(row[0:2] != ('system', 'main') or row[3] != 'aggregate' or row[7] is not True for row in rows):
            continue
        listed = name in {'list', 'array_agg'}
        if not any(list(row[5]) == (['T'] if listed else ['ANY']) and
                   row[6] == ('T[]' if listed else 'ANY') for row in rows):
            continue
        result[name] = {'argument': 'list' if listed else 'same',
                        'positive_literal_count': name in {'min', 'max'} and
                        any(list(row[5]) == ['ANY', 'BIGINT'] and row[6] == 'ANY[]' for row in rows)}
    return result

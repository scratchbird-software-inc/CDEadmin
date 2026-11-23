"""Pinned aggregate and computed result shapes admitted by native function facts.

These rules describe completion types; they do not accept SQL grammar, bind an
arbitrary function, evaluate arguments or infer a replacement for native values.
Any visible non-core homonym or truncated symbol section disables affected rules
conservatively (DU-AUD-02).
"""


def _core_rows(functions, name, allowed_kinds):
    rows = [row for row in functions if str(row[2]).lower() == name]
    if not rows:
        return None
    if any(
        row[0:2] != ('system', 'main')
        or row[3] not in allowed_kinds
        or row[7] is not True
        for row in rows
    ):
        return None
    return rows


def _unshadowed_special(functions, name):
    return not any(
        str(row[2]).lower() == name
        and (row[0:2] != ('system', 'main') or row[7] is not True)
        for row in functions
    )


def aggregate_type_rules(version, functions, truncated):
    if str(version).removeprefix('v') != '1.5.2' or truncated:
        return {}
    result = {}
    for name in (
        'min', 'max', 'first', 'last', 'any_value', 'arbitrary',
        'list', 'array_agg',
    ):
        rows = _core_rows(functions, name, {'aggregate'})
        if not rows:
            continue
        listed = name in {'list', 'array_agg'}
        if not any(
            list(row[5]) == (['T'] if listed else ['ANY'])
            and row[6] == ('T[]' if listed else 'ANY')
            for row in rows
        ):
            continue
        result[name] = {
            'argument': 'list' if listed else 'same',
            'positive_literal_count': (
                name in {'min', 'max'}
                and any(
                    list(row[5]) == ['ANY', 'BIGINT'] and row[6] == 'ANY[]'
                    for row in rows
                )
            ),
        }
    return result


def computed_type_rules(
    version,
    functions,
    truncated,
    *,
    types_truncated=False,
    columns_truncated=False,
):
    """Admit non-executing computed completion rules from verified 1.5.2 catalog facts."""
    if (
        str(version).removeprefix('v') != '1.5.2'
        or truncated
        or types_truncated
        or columns_truncated
    ):
        return {}

    keyed_aggregates = {}
    for name in ('arg_min', 'arg_max', 'min_by', 'max_by'):
        rows = _core_rows(functions, name, {'aggregate'})
        if not rows:
            continue
        if not any(list(row[5]) == ['ANY', 'ANY'] and row[6] == 'ANY' for row in rows):
            continue
        keyed_aggregates[name] = {
            'positive_literal_count': any(
                list(row[5]) == ['ANY', 'ANY', 'BIGINT'] and row[6] == 'ANY[]'
                for row in rows
            ),
        }

    scalar_functions = {}
    scalar_specs = (
        ('list_extract', {'scalar'}, lambda rows: any(
            list(r[5]) == ['T[]', 'BIGINT'] and r[6] == 'T' for r in rows
        ), {'shape': 'list_element', 'min_args': 2, 'max_args': 2}),
        ('list_element', {'scalar'}, lambda rows: any(
            list(r[5]) == ['T[]', 'BIGINT'] and r[6] == 'T' for r in rows
        ), {'shape': 'list_element', 'min_args': 2, 'max_args': 2}),
        ('array_extract', {'scalar'}, lambda rows: (
            any(list(r[5]) == ['T[]', 'BIGINT'] and r[6] == 'T' for r in rows)
            and any(list(r[5]) == ['STRUCT', 'VARCHAR'] and r[6] == 'ANY' for r in rows)
        ), {'shape': 'array_or_struct_extract', 'min_args': 2, 'max_args': 2}),
        ('list_slice', {'scalar'}, lambda rows: any(
            list(r[5]) == ['ANY', 'ANY', 'ANY'] and r[6] == 'ANY' for r in rows
        ), {'shape': 'list_slice', 'min_args': 3, 'max_args': 4}),
        ('array_slice', {'scalar'}, lambda rows: any(
            list(r[5]) == ['ANY', 'ANY', 'ANY'] and r[6] == 'ANY' for r in rows
        ), {'shape': 'list_slice', 'min_args': 3, 'max_args': 4}),
        ('list_distinct', {'scalar'}, lambda rows: any(
            list(r[5]) == ['T[]'] and r[6] == 'T[]' for r in rows
        ), {'shape': 'list_preserve', 'min_args': 1, 'max_args': 1}),
        ('list_reverse', {'macro', 'scalar'}, lambda rows: len(rows) >= 1,
         {'shape': 'list_preserve', 'min_args': 1, 'max_args': 1}),
        ('list_sort', {'scalar'}, lambda rows: any(
            list(r[5]) == ['ANY[]'] and r[6] == 'ANY[]' for r in rows
        ), {'shape': 'list_preserve', 'min_args': 1, 'max_args': 3}),
        ('list_reverse_sort', {'scalar'}, lambda rows: any(
            list(r[5]) == ['ANY[]'] and r[6] == 'ANY[]' for r in rows
        ), {'shape': 'list_preserve', 'min_args': 1, 'max_args': 2}),
        ('flatten', {'scalar'}, lambda rows: any(
            list(r[5]) == ['T[][]'] and r[6] == 'T[]' for r in rows
        ), {'shape': 'list_flatten', 'min_args': 1, 'max_args': 1}),
        ('map_extract', {'scalar'}, lambda rows: any(
            list(r[5]) == ['MAP(K, V)', 'K'] and r[6] == 'V[]' for r in rows
        ), {'shape': 'map_extract_list', 'min_args': 2, 'max_args': 2}),
        ('map_extract_value', {'scalar'}, lambda rows: any(
            list(r[5]) == ['MAP(K, V)', 'K'] and r[6] == 'V' for r in rows
        ), {'shape': 'map_extract_value', 'min_args': 2, 'max_args': 2}),
        ('map_keys', {'scalar'}, lambda rows: any(
            list(r[5]) == ['MAP(K, V)'] and r[6] == 'K[]' for r in rows
        ), {'shape': 'map_keys', 'min_args': 1, 'max_args': 1}),
        ('map_values', {'scalar'}, lambda rows: any(
            list(r[5]) == ['MAP(K, V)'] and r[6] == 'V[]' for r in rows
        ), {'shape': 'map_values', 'min_args': 1, 'max_args': 1}),
        ('map_entries', {'scalar'}, lambda rows: any(
            list(r[5]) == ['MAP(K, V)'] and 'STRUCT' in str(r[6]) for r in rows
        ), {'shape': 'map_entries', 'min_args': 1, 'max_args': 1}),
        ('struct_extract', {'scalar'}, lambda rows: any(
            list(r[5]) == ['STRUCT', 'VARCHAR'] and r[6] == 'ANY' for r in rows
        ), {'shape': 'struct_extract', 'min_args': 2, 'max_args': 2}),
        ('union_extract', {'scalar'}, lambda rows: any(
            list(r[5]) == ['UNION', 'VARCHAR'] and r[6] == 'ANY' for r in rows
        ), {'shape': 'union_extract', 'min_args': 2, 'max_args': 2}),
        ('struct_pack', {'scalar'}, lambda rows: any(
            list(r[5]) == [] and r[6] == 'STRUCT' for r in rows
        ), {'shape': 'struct_pack', 'min_args': 1, 'max_args': 64}),
        ('row', {'scalar'}, lambda rows: any(
            list(r[5]) == [] and r[6] == 'STRUCT' for r in rows
        ), {'shape': 'row_tuple', 'min_args': 1, 'max_args': 64}),
        ('nullif', {'macro', 'scalar'}, lambda rows: len(rows) == 1 and len(rows[0][4] or ()) == 2,
         {'shape': 'first_arg', 'min_args': 2, 'max_args': 2}),
    )
    for name, allowed_kinds, predicate, rule in scalar_specs:
        rows = _core_rows(functions, name, allowed_kinds)
        if rows and predicate(rows):
            scalar_functions[name] = dict(rule)

    special_forms = {
        'coalesce': _unshadowed_special(functions, 'coalesce'),
        'ifnull': _unshadowed_special(functions, 'ifnull'),
        'casts': _unshadowed_special(functions, 'cast') and _unshadowed_special(functions, 'try_cast'),
        'scalar_subquery': True,
    }
    return {
        'ordered_aggregates': True,
        'keyed_aggregates': keyed_aggregates,
        'scalar_functions': scalar_functions,
        'special_forms': special_forms,
    }

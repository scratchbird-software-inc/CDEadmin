##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Provider-invoked SQL compilation for semantic logical queries."""

from __future__ import annotations

import copy
import re
import uuid
from decimal import Decimal
from typing import Mapping

from .models import (
    SEMI_ADDITIVE_AGGREGATIONS,
    SemanticModelError,
    filter_model_for_role,
    validate_model,
    validate_query,
)


def compile_sql(
    model_value, query_value, dialect, *, role: str | None = None
):
    """Compile a validated model only when invoked by an owning provider."""
    if not isinstance(dialect, Mapping) or dialect.get(
            'contract_complete') is not True:
        raise SemanticModelError(
            'provider semantic SQL dialect contract is incomplete'
        )
    required = {
        'language_profile', 'quote_open', 'quote_close',
        'supports_rollup', 'limit_style', 'true_literal', 'false_literal',
        'time_operations', 'window_operations',
    }
    missing = sorted(required.difference(dialect))
    if missing:
        raise SemanticModelError(
            'provider semantic SQL dialect contract is missing: ' +
            ', '.join(missing)
        )
    if dialect['limit_style'] not in {'limit', 'rows'}:
        raise SemanticModelError(
            'provider semantic SQL limit style is unsupported'
        )
    rollup_style = dialect.get('rollup_style', 'function')
    if rollup_style not in {'function', 'with_rollup'}:
        raise SemanticModelError(
            'provider semantic SQL rollup style is unsupported'
        )
    rollup_allows_order_by = dialect.get(
        'rollup_allows_order_by', True
    )
    if not isinstance(rollup_allows_order_by, bool):
        raise SemanticModelError(
            'provider semantic SQL rollup ordering flag is invalid'
        )
    window_input_cast = dialect.get('window_input_cast')
    if window_input_cast is not None and (
        not isinstance(window_input_cast, str) or
        re.fullmatch(
            r'[A-Za-z][A-Za-z0-9_]*(?:\(\d+(?:,\s*\d+)?\))?',
            window_input_cast,
        ) is None
    ):
        raise SemanticModelError(
            'provider semantic SQL window input cast is invalid'
        )
    percent_change_result_cast = dialect.get(
        'percent_change_result_cast'
    )
    if percent_change_result_cast is not None and (
        not isinstance(percent_change_result_cast, str) or
        re.fullmatch(
            r'[A-Za-z][A-Za-z0-9_]*(?:\(\d+(?:,\s*\d+)?\))?',
            percent_change_result_cast,
        ) is None
    ):
        raise SemanticModelError(
            'provider semantic SQL percent-change result cast is invalid'
        )
    percent_change_numerator_cast = dialect.get(
        'percent_change_numerator_cast'
    )
    if percent_change_numerator_cast is not None and (
        not isinstance(percent_change_numerator_cast, str) or
        re.fullmatch(
            r'[A-Za-z][A-Za-z0-9_]*(?:\(\d+(?:,\s*\d+)?\))?',
            percent_change_numerator_cast,
        ) is None
    ):
        raise SemanticModelError(
            'provider semantic SQL percent-change numerator cast is invalid'
        )
    model = validate_model(model_value)
    if role is not None and isinstance(query_value, Mapping):
        merged_query = dict(query_value)
        merged_query.setdefault('role', role)
        query = validate_query(model, merged_query)
    else:
        query = validate_query(model, query_value)
    binder = _Binder(query.get('bind'))
    time_operations = frozenset(dialect['time_operations'])
    window_operations = frozenset(dialect['window_operations'])
    if query['time_intelligence'] and query['time_intelligence'][
            'operation'] not in time_operations:
        raise SemanticModelError(
            'provider does not admit the requested time-intelligence operation'
        )
    unavailable_windows = {
        item['operation'] for item in query['windows']
    }.difference(window_operations)
    if unavailable_windows:
        raise SemanticModelError(
            'provider does not admit requested analytical window operations: '
            + ', '.join(sorted(unavailable_windows))
        )
    quote_open = dialect['quote_open']
    quote_close = dialect['quote_close']

    def quote(value):
        return quote_open + str(value).replace(
            quote_close, quote_close + quote_close
        ) + quote_close

    sources = {item['id']: item for item in model['sources']}
    source_sql = {
        item['id']: '.'.join(quote(part) for part in item['relation']) +
        ' AS ' + quote(item['alias'])
        for item in model['sources']
    }

    def field(reference):
        source = sources[reference['source_id']]
        return f"{quote(source['alias'])}.{quote(reference['field'])}"

    levels = {}
    owner_dimension_by_item = {}
    parent_child_hierarchies = {}
    dimensions_by_id = {item['id']: item for item in model['dimensions']}
    for dimension in model['dimensions']:
        owner_dimension_by_item[dimension['id']] = dimension
        levels[dimension['id']] = {
            'id': dimension['id'], 'name': dimension['name'],
            'field': dimension['field'],
        }
        for attr in dimension.get('attributes', []):
            owner_dimension_by_item[attr['id']] = dimension
            levels[attr['id']] = attr
        for hierarchy in dimension.get('hierarchies', []):
            owner_dimension_by_item[hierarchy['id']] = dimension
            if hierarchy.get('hierarchy_kind') == 'parent_child':
                parent_child_hierarchies[hierarchy['id']] = (
                    dimension, hierarchy, True
                )
                parent_child_hierarchies.setdefault(
                    dimension['id'], (dimension, hierarchy, False)
                )
                levels[hierarchy['id']] = {
                    'id': hierarchy['id'],
                    'name': hierarchy['name'],
                    'field': (
                        hierarchy.get('name_field')
                        or hierarchy['child_field']
                    ),
                    'parent_child': True,
                }
            else:
                for level in hierarchy.get('levels', []):
                    owner_dimension_by_item[level['id']] = dimension
                    levels[level['id']] = level
    measures = {item['id']: item for item in model['measures']}
    parameter_values = {
        item['id']: item.get('default') for item in model['parameters']
        if 'default' in item
    }
    parameter_values.update(query['parameters'])
    axis_ids = []
    for axis in ('pages', 'rows', 'columns'):
        for item in query['axes'][axis]:
            if item not in axis_ids:
                axis_ids.append(item)
    drill = query['drill']
    if drill['mode'] == 'down' and drill.get('target_level') not in axis_ids:
        axis_ids.append(drill['target_level'])

    active_pc = [
        item for item in axis_ids
        if item in parent_child_hierarchies and drill['mode'] != 'through'
    ]
    recursive_ctes = []
    pc_joins = []
    pc_exprs = {}
    seen_pc_hiers = set()
    for hid in active_pc:
        _pc_dim, pc_hier, use_name_col = parent_child_hierarchies[hid]
        hier_id = pc_hier['id']
        cte_alias = quote(f'__pc_{hier_id}')
        anc_id = quote('ancestor_id')
        anc_name = quote('ancestor_name')
        desc_id = quote('descendant_id')
        depth_col = quote('pc_depth')
        if hier_id not in seen_pc_hiers:
            seen_pc_hiers.add(hier_id)
            d_alias = quote(f'__pcd_{hier_id}')
            c_alias = quote(f'__pcc_{hier_id}')
            ch_alias = quote(f'__pcch_{hier_id}')
            pc_src = sources[pc_hier['child_field']['source_id']]
            pc_rel = '.'.join(quote(part) for part in pc_src['relation'])
            child_col = quote(pc_hier['child_field']['field'])
            parent_col = quote(pc_hier['parent_field']['field'])
            name_ref = pc_hier.get('name_field') or pc_hier['child_field']
            name_col = quote(name_ref['field'])
            max_depth = int(pc_hier.get('max_depth', 16))
            cte_sql = (
                f'{cte_alias} ({anc_id}, {anc_name}, {desc_id}, '
                f'{depth_col}) AS ('
                f'SELECT {d_alias}.{child_col}, {d_alias}.{name_col}, '
                f'{d_alias}.{child_col}, 0 FROM {pc_rel} AS {d_alias} '
                f'UNION ALL '
                f'SELECT {c_alias}.{anc_id}, {c_alias}.{anc_name}, '
                f'{ch_alias}.{child_col}, {c_alias}.{depth_col} + 1 '
                f'FROM {cte_alias} AS {c_alias} '
                f'INNER JOIN {pc_rel} AS {ch_alias} '
                f'ON {ch_alias}.{parent_col} = {c_alias}.{desc_id} '
                f'WHERE {c_alias}.{depth_col} < {max_depth})'
            )
            recursive_ctes.append(cte_sql)
            pc_joins.append(
                f' INNER JOIN {cte_alias} ON {cte_alias}.{desc_id} = '
                f"{field(pc_hier['child_field'])}"
            )
        pc_exprs[hid] = (
            f'{cte_alias}.{anc_name}'
            if (use_name_col and pc_hier.get('name_field'))
            else f'{cte_alias}.{anc_id}'
        )

    first = model['sources'][0]['id']
    from_clause = source_sql[first]
    joined = {first}
    nullable_sources = set()
    active_dims = [
        d for d in model['dimensions']
        if d.get('active', True) is not False
    ]

    def _effective_join_type(join_obj):
        jid = join_obj['id']
        right_src = join_obj['right_source']
        linked_dims = [
            d for d in active_dims
            if d.get('join_id') == jid
            or (
                d.get('join_id') is None
                and d['field']['source_id'] == right_src
            )
        ]
        if any(
            d.get('unknown_member_policy', 'unknown') == 'hide'
            for d in linked_dims
        ):
            return 'INNER'
        return join_obj.get('join_type', 'inner').upper()

    remaining = [
        item for item in model['joins']
        if item.get('active', True) is not False
    ]
    while remaining:
        progress = False
        for join in list(remaining):
            left = join['left_source']
            right = join['right_source']
            if left not in joined or right in joined:
                continue
            join_type = _effective_join_type(join)
            if join_type in {'LEFT', 'FULL'} or left in nullable_sources:
                nullable_sources.add(right)
            from_clause += f' {join_type} JOIN {source_sql[right]}'
            if join_type != 'CROSS':
                join_preds = [
                    f"{field(item['left'])} = {field(item['right'])}"
                    for item in join['predicates']
                ]
                from_clause += ' ON ' + ' AND '.join(join_preds)
            joined.add(right)
            remaining.remove(join)
            progress = True
        if not progress:
            raise SemanticModelError(
                'joins must form an ordered graph from the first source'
            )

    def axis_sql_expr(item_id):
        raw_expr = (
            pc_exprs[item_id]
            if item_id in pc_exprs
            else field(levels[item_id]['field'])
        )
        owner_dim = owner_dimension_by_item.get(item_id)
        if owner_dim is not None:
            policy = owner_dim.get('unknown_member_policy', 'unknown')
            src_id = levels[item_id]['field']['source_id']
            if policy == 'unknown' and src_id in nullable_sources:
                caption = owner_dim.get('unknown_member_caption') or 'Unknown'
                return f'COALESCE({raw_expr}, {_literal(caption, dialect)})'
        return raw_expr

    selections = [
        f'{axis_sql_expr(item)} AS {quote(item)}'
        for item in axis_ids
    ]
    aggregate_names = {
        'sum': 'SUM', 'count': 'COUNT', 'count_distinct': 'COUNT',
        'min': 'MIN', 'max': 'MAX', 'avg': 'AVG', 'none': '',
    }

    axis_field_pairs = {
        (levels[item]['field']['source_id'], levels[item]['field']['field'])
        for item in axis_ids
        if item not in pc_exprs
    }

    def _semi_additive_time_ref(measure):
        sa_dim_id = measure['semi_additive_dimension']
        sa_dim = dimensions_by_id[sa_dim_id]
        return (
            sa_dim.get('sort_field')
            or sa_dim.get('key_field')
            or sa_dim['field']
        )

    def _is_rolled_up_semi_additive(measure):
        if drill['mode'] == 'through':
            return False
        if measure['aggregation'] not in SEMI_ADDITIVE_AGGREGATIONS:
            return False
        t_ref = _semi_additive_time_ref(measure)
        return (t_ref['source_id'], t_ref['field']) not in axis_field_pairs

    def _collect_leaf_measures(measure_id, stack=frozenset()):
        if measure_id in stack:
            raise SemanticModelError('calculated measure cycle is unsupported')
        m_obj = measures[measure_id]
        if m_obj.get('expression') is None:
            return [measure_id]
        found = []

        def _walk(node):
            if 'measure' in node:
                for leaf in _collect_leaf_measures(
                    node['measure'], stack | frozenset({measure_id})
                ):
                    if leaf not in found:
                        found.append(leaf)
            elif 'operator' in node:
                _walk(node['left'])
                _walk(node['right'])

        _walk(m_obj['expression'])
        return found

    all_leaf_ids = []
    for q_mid in query['measures']:
        for leaf_id in _collect_leaf_measures(q_mid):
            if leaf_id not in all_leaf_ids:
                all_leaf_ids.append(leaf_id)

    rolled_semi_ids = [
        mid for mid in all_leaf_ids
        if _is_rolled_up_semi_additive(measures[mid])
    ]

    def _within_agg_sql(measure):
        within_agg = measure.get('within_group_aggregation', 'sum')
        m_filters = measure.get('filters') or []
        m_cond = ' AND '.join(
            _compile_filter(item, field, dialect, parameter_values, binder)
            for item in m_filters
        )
        if within_agg == 'count' and measure.get('field') is None:
            if m_cond:
                return f'COUNT(CASE WHEN {m_cond} THEN 1 END)'
            return 'COUNT(*)'
        operand = field(measure['field'])
        if m_cond:
            operand = f'CASE WHEN {m_cond} THEN {operand} END'
        return f'{aggregate_names[within_agg]}({operand})'

    def measure_expression(measure_id, stack=frozenset(), leaf_lookup=None):
        if measure_id in stack:
            raise SemanticModelError('calculated measure cycle is unsupported')
        if leaf_lookup and measure_id in leaf_lookup:
            return leaf_lookup[measure_id]
        measure = measures[measure_id]
        if measure.get('expression') is not None:
            return calculation(
                measure['expression'],
                stack | frozenset({measure_id}),
                leaf_lookup=leaf_lookup,
            )
        aggregation = measure['aggregation']
        if aggregation in SEMI_ADDITIVE_AGGREGATIONS:
            return _within_agg_sql(measure)
        m_filters = measure.get('filters') or []
        m_cond = ' AND '.join(
            _compile_filter(item, field, dialect, parameter_values, binder)
            for item in m_filters
        )
        if aggregation == 'count' and measure.get('field') is None:
            if m_cond:
                return f'COUNT(CASE WHEN {m_cond} THEN 1 END)'
            return 'COUNT(*)'
        operand = field(measure['field'])
        if m_cond:
            operand = f'CASE WHEN {m_cond} THEN {operand} END'
        if aggregation == 'count_distinct':
            return f'COUNT(DISTINCT {operand})'
        if aggregation == 'none':
            return operand
        return f'{aggregate_names[aggregation]}({operand})'

    def calculation(node, stack, leaf_lookup=None):
        if 'measure' in node:
            return measure_expression(
                node['measure'], stack, leaf_lookup=leaf_lookup
            )
        if 'literal' in node:
            return str(node['literal'])
        operators = {
            'add': '+', 'subtract': '-', 'multiply': '*', 'divide': '/',
        }
        left = calculation(node['left'], stack, leaf_lookup=leaf_lookup)
        right = calculation(node['right'], stack, leaf_lookup=leaf_lookup)
        if node['operator'] == 'divide':
            right = f'NULLIF({right}, 0)'
        return f'({left} {operators[node["operator"]]} {right})'

    for measure_id in query['measures']:
        measure = measures[measure_id]
        if drill['mode'] == 'through':
            if measure.get('expression') is not None or not measure.get(
                    'field'):
                raise SemanticModelError(
                    'drill-through requires field-backed measures'
                )
            expression = field(measure['field'])
        else:
            expression = measure_expression(measure_id)
            if query['windows'] and window_input_cast and any(
                item['measure_id'] == measure_id
                for item in query['windows']
            ):
                expression = (
                    f'CAST({expression} AS {window_input_cast})'
                )
        selections.append(f'{expression} AS {quote(measure_id)}')
    detail_aliases = []
    for index, reference in enumerate(drill['detail_fields']):
        alias = f'detail_{index + 1}_{reference["field"]}'
        detail_aliases.append(alias)
        selections.append(f'{field(reference)} AS {quote(alias)}')
    if not selections:
        raise SemanticModelError('semantic query has no projection')

    if joined != set(sources):
        raise SemanticModelError('every source must be connected by a join')
    if pc_joins:
        from_clause += ''.join(pc_joins)

    filters = (
        model['default_filters'] + model['security']['row_filters'] +
        query['filters'] + query['cross_filters']
    )
    predicates = [
        _compile_filter(item, field, dialect, parameter_values, binder)
        for item in filters
    ]
    for item_id in axis_ids:
        owner_dim = owner_dimension_by_item.get(item_id)
        if (
            owner_dim is not None
            and owner_dim.get('unknown_member_policy') == 'hide'
            and levels[item_id]['field']['source_id'] == first
        ):
            predicates.append(f"{field(levels[item_id]['field'])} IS NOT NULL")
    time_intelligence = query['time_intelligence']
    comparison_expression = None
    if time_intelligence:
        dimension = next(
            item for item in model['dimensions']
            if item['id'] == time_intelligence['dimension_id']
        )
        time_field = field(dimension['field'])
        start = binder.literal(time_intelligence['start'], dialect)
        operation = time_intelligence['operation']
        if operation == 'as_of':
            predicates.append(f'{time_field} <= {start}')
        elif operation == 'period_comparison':
            end = binder.literal(time_intelligence['end'], dialect)
            previous_start = binder.literal(
                time_intelligence['comparison_start'], dialect
            )
            previous_end = binder.literal(
                time_intelligence['comparison_end'], dialect
            )
            current = f'{time_field} BETWEEN {start} AND {end}'
            previous = (
                f'{time_field} BETWEEN {previous_start} AND {previous_end}'
            )
            predicates.append(f'(({current}) OR ({previous}))')
            comparison_expression = (
                f"CASE WHEN {current} THEN 'current' "
                f"WHEN {previous} THEN 'comparison' END"
            )
            selections.append(
                f'{comparison_expression} AS {quote("__semantic_period")}'
            )
        else:
            end = binder.literal(time_intelligence['end'], dialect)
            predicates.append(f'{time_field} BETWEEN {start} AND {end}')

    if rolled_semi_ids:
        part_items = list(axis_ids) + (
            ['__semantic_period'] if comparison_expression is not None else []
        )
        part_exprs = [axis_sql_expr(item) for item in axis_ids] + (
            [comparison_expression]
            if comparison_expression is not None else []
        )
        part_selects = [
            f'{axis_sql_expr(item)} AS {quote(item)}' for item in axis_ids
        ]
        if comparison_expression is not None:
            part_selects.append(
                f'{comparison_expression} AS {quote("__semantic_period")}'
            )
        regular_leaf_ids = [
            mid for mid in all_leaf_ids if mid not in rolled_semi_ids
        ]
        base_alias = quote('__sem_base')
        leaf_lookup = {
            mid: f'{base_alias}.{quote("__m_" + mid)}'
            for mid in regular_leaf_ids
        }
        base_selects = list(part_selects) + [
            f'{measure_expression(mid)} AS {quote("__m_" + mid)}'
            for mid in regular_leaf_ids
        ]
        if not base_selects:
            base_selects.append('1 AS ' + quote('__sem_anchor'))
        base_sql = (
            'SELECT ' + ', '.join(base_selects) + ' FROM ' + from_clause
        )
        if predicates:
            base_sql += ' WHERE ' + ' AND '.join(predicates)
        if part_exprs:
            base_sql += ' GROUP BY ' + ', '.join(part_exprs)

        sa_joins = []
        time_col = quote('__sa_time')
        val_col = quote('__sa_val')
        rn_col = quote('__sa_rn')
        for idx, sa_mid in enumerate(rolled_semi_ids):
            sa_m = measures[sa_mid]
            sa_agg = sa_m['aggregation']
            t_expr = field(_semi_additive_time_ref(sa_m))
            w_expr = _within_agg_sql(sa_m)
            p_alias = quote(f'__sap_{idx}')
            g_alias = quote(f'__sag_{idx}')
            j_alias = quote(f'__sa_{idx}')
            period_sql = (
                'SELECT '
                + ', '.join(
                    part_selects + [
                        f'{t_expr} AS {time_col}',
                        f'{w_expr} AS {val_col}',
                    ]
                )
                + ' FROM ' + from_clause
            )
            if predicates:
                period_sql += ' WHERE ' + ' AND '.join(predicates)
            period_sql += ' GROUP BY ' + ', '.join(part_exprs + [t_expr])
            if sa_agg in {'last_non_empty', 'first_non_empty'}:
                period_sql += f' HAVING {w_expr} IS NOT NULL'

            part_refs_p = [
                f'{p_alias}.{quote(col)}' for col in part_items
            ]
            if sa_agg == 'avg_over_time':
                sa_sub_sql = (
                    'SELECT '
                    + ', '.join(
                        part_refs_p + [
                            f'AVG({p_alias}.{val_col}) AS {val_col}',
                        ]
                    )
                    + f' FROM ({period_sql}) AS {p_alias}'
                )
                if part_refs_p:
                    sa_sub_sql += ' GROUP BY ' + ', '.join(part_refs_p)
            else:
                direction = (
                    'DESC'
                    if sa_agg in {'last_value', 'last_non_empty'}
                    else 'ASC'
                )
                part_clause = (
                    ('PARTITION BY ' + ', '.join(part_refs_p) + ' ')
                    if part_refs_p else ''
                )
                order_clause = f'ORDER BY {p_alias}.{time_col} {direction}'
                ranked_sql = (
                    'SELECT '
                    + ', '.join(
                        part_refs_p + [
                            f'{p_alias}.{val_col}',
                            f'ROW_NUMBER() OVER ({part_clause}{order_clause})'
                            f' AS {rn_col}',
                        ]
                    )
                    + f' FROM ({period_sql}) AS {p_alias}'
                )
                part_refs_g = [
                    f'{g_alias}.{quote(col)}' for col in part_items
                ]
                sa_sub_sql = (
                    'SELECT '
                    + ', '.join(part_refs_g + [f'{g_alias}.{val_col}'])
                    + f' FROM ({ranked_sql}) AS {g_alias}'
                    + f' WHERE {g_alias}.{rn_col} = 1'
                )

            if part_items:
                join_cond = ' AND '.join(
                    f'(({base_alias}.{quote(col)} = {j_alias}.{quote(col)}) '
                    f'OR ({base_alias}.{quote(col)} IS NULL '
                    f'AND {j_alias}.{quote(col)} IS NULL))'
                    for col in part_items
                )
            else:
                join_cond = '1 = 1'
            sa_joins.append(
                f' LEFT JOIN ({sa_sub_sql}) AS {j_alias} ON {join_cond}'
            )
            leaf_lookup[sa_mid] = f'{j_alias}.{val_col}'

        outer_selects = [
            f'{base_alias}.{quote(item)} AS {quote(item)}'
            for item in axis_ids
        ]
        for measure_id in query['measures']:
            expr = measure_expression(measure_id, leaf_lookup=leaf_lookup)
            if query['windows'] and window_input_cast and any(
                item['measure_id'] == measure_id
                for item in query['windows']
            ):
                expr = f'CAST({expr} AS {window_input_cast})'
            outer_selects.append(f'{expr} AS {quote(measure_id)}')
        if comparison_expression is not None:
            outer_selects.append(
                f'{base_alias}.{quote("__semantic_period")} '
                f'AS {quote("__semantic_period")}'
            )
        source = (
            'SELECT ' + ', '.join(outer_selects) +
            f' FROM ({base_sql}) AS {base_alias}' +
            ''.join(sa_joins)
        )
    else:
        source = 'SELECT ' + ', '.join(selections) + ' FROM ' + from_clause
        if predicates:
            source += ' WHERE ' + ' AND '.join(predicates)
        group_fields = [axis_sql_expr(item) for item in axis_ids]
        if comparison_expression is not None:
            group_fields.append(comparison_expression)
        if drill['mode'] != 'through' and group_fields and any(
            measures[item]['aggregation'] != 'none' or
            measures[item].get('expression') is not None
            for item in query['measures']
        ):
            group_keyword = 'GROUP BY'
            if query['totals'] and dialect['supports_rollup']:
                if rollup_style == 'with_rollup':
                    source += (
                        ' GROUP BY ' + ', '.join(group_fields) + ' WITH ROLLUP'
                    )
                else:
                    source += (
                        ' GROUP BY ROLLUP (' + ', '.join(group_fields) + ')'
                    )
            else:
                source += ' ' + group_keyword + ' ' + ', '.join(group_fields)
    output_order = [quote(item) for item in axis_ids]
    if comparison_expression is not None:
        output_order.append(quote('__semantic_period'))
    if query['windows']:
        source = _compile_sql_windows(
            source, query['windows'], axis_ids, quote,
            percent_change_result_cast=percent_change_result_cast,
            percent_change_numerator_cast=percent_change_numerator_cast,
        )
    if recursive_ctes:
        source = 'WITH RECURSIVE ' + ', '.join(recursive_ctes) + ' ' + source
    native_rollup_without_order = bool(
        query['totals'] and dialect['supports_rollup'] and
        not rollup_allows_order_by
    )
    if query.get('order_by'):
        output_order = [
            quote(item['id']) + ' ' + item['direction'].upper()
            for item in query['order_by']
        ]
    if output_order and not native_rollup_without_order:
        source += ' ORDER BY ' + ', '.join(output_order)
    if dialect['limit_style'] == 'rows':
        source += f" ROWS 1 TO {query['limit']}"
    else:
        source += f" LIMIT {query['limit']}"
    source, bound = binder.finish(source)
    return {
        'contract_version': '1.0.0',
        'language_profile': dialect['language_profile'],
        'source': source,
        'parameters': bound if binder.active else {},
        'projection': {
            'axes': query['axes'], 'levels': axis_ids,
            'measures': query['measures'], 'totals': query['totals'],
            'drill': copy.deepcopy(drill),
            'detail_fields': detail_aliases,
            'time_intelligence': copy.deepcopy(time_intelligence),
            'windows': copy.deepcopy(query['windows']),
        },
        'warnings': (
            [
                'Provider does not declare native rollup; totals are omitted.'
            ] if query['totals'] and not dialect['supports_rollup'] else
            [
                'Provider native rollup does not admit ORDER BY; rollup '
                'order is provider-defined.'
            ] if native_rollup_without_order and output_order else []
        ),
    }


def _compile_sql_windows(
        source, windows, axis_ids, quote,
        percent_change_result_cast=None,
        percent_change_numerator_cast=None):
    """Wrap an aggregate query with provider-admitted native windows."""
    admitted = set(axis_ids)
    for window in windows:
        required = set(window['partition_by']) | {
            window['order_by']['level_id']
        }
        if not required.issubset(admitted):
            raise SemanticModelError(
                'window partition and order levels must be query axes'
            )
    alias = quote('semantic_base')

    def column(name):
        return f'{alias}.{quote(name)}'

    expressions = []
    for window in windows:
        measure = column(window['measure_id'])
        partitions = ', '.join(
            column(item) for item in window['partition_by']
        )
        order = column(window['order_by']['level_id']) + ' ' + window[
            'order_by']['direction'].upper()
        clause = (
            ('PARTITION BY ' + partitions + ' ') if partitions else ''
        ) + 'ORDER BY ' + order
        operation = window['operation']
        size = window['frame_size']
        if operation == 'running_sum':
            value = (
                f'SUM({measure}) OVER ({clause} ROWS BETWEEN UNBOUNDED '
                'PRECEDING AND CURRENT ROW)'
            )
        elif operation in {'moving_sum', 'moving_average'}:
            function = 'SUM' if operation == 'moving_sum' else 'AVG'
            value = (
                f'{function}({measure}) OVER ({clause} ROWS BETWEEN '
                f'{size - 1} PRECEDING AND CURRENT ROW)'
            )
        elif operation == 'lag':
            value = f'LAG({measure}, {size}) OVER ({clause})'
        elif operation in {'delta', 'percent_change'}:
            previous = f'LAG({measure}, {size}) OVER ({clause})'
            if operation == 'delta':
                value = f'({measure} - {previous})'
            else:
                numerator = f'({measure} - {previous})'
                if percent_change_numerator_cast:
                    numerator = (
                        f'CAST({numerator} AS '
                        f'{percent_change_numerator_cast})'
                    )
                value = (
                    f'(CASE WHEN {previous} IS NULL OR {previous} = 0 '
                    f'THEN NULL ELSE {numerator} / '
                    f'{previous} END)'
                )
                if percent_change_result_cast:
                    value = (
                        f'CAST({value} AS {percent_change_result_cast})'
                    )
        else:
            function = 'RANK' if operation == 'rank' else 'DENSE_RANK'
            rank_clause = (
                ('PARTITION BY ' + partitions + ' ') if partitions else ''
            ) + f'ORDER BY {measure} DESC'
            value = f'{function}() OVER ({rank_clause})'
        expressions.append(f'{value} AS {quote(window["id"])}')
    return (
        f'SELECT {alias}.*, ' + ', '.join(expressions) +
        f' FROM ({source}) AS {alias}'
    )


def _literal(value, dialect):
    if value is None:
        return 'NULL'
    if isinstance(value, bool):
        return dialect['true_literal'] if value else dialect['false_literal']
    if (
        isinstance(value, (int, float, Decimal)) and
        not isinstance(value, bool)
    ):
        return str(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    raise SemanticModelError('filter value type is not portable')


class _Binder:
    """Render filter values as inline literals or as bound parameters.

    With a ``bind`` style the SQL text never contains a caller value: each
    value becomes a private token that ``finish`` replaces, in textual order,
    by the engine marker (``?`` for ``qmark``, ``%s`` for ``format``) while the
    values are returned as the positional parameter array.
    """

    STYLES = {'qmark': '?', 'format': '%s'}

    def __init__(self, style):
        if style is not None and style not in self.STYLES:
            raise SemanticModelError('query.bind style is unsupported')
        self.style = style
        self.active = style is not None
        self._values = []
        self._prefix = '\x00' + uuid.uuid4().hex + ':'

    def literal(self, value, dialect):
        if not self.active or value is None:
            return _literal(value, dialect)
        if isinstance(value, bool):
            pass
        elif not isinstance(value, (int, float, Decimal, str)):
            raise SemanticModelError('filter value type is not portable')
        if isinstance(value, str) and '\x00' in value:
            raise SemanticModelError('filter value cannot contain NUL')
        self._values.append(value)
        return f'{self._prefix}{len(self._values) - 1}\x00'

    def finish(self, source):
        if not self.active:
            return source, {}
        marker = self.STYLES[self.style]
        pattern = re.compile(re.escape(self._prefix) + r'(\d+)\x00')
        ordered, parts, position = [], [], 0
        for match in pattern.finditer(source):
            parts.append(source[position:match.start()])
            ordered.append(self._values[int(match.group(1))])
            position = match.end()
        parts.append(source[position:])
        if ordered and self.style == 'format':
            parts = [part.replace('%', '%%') for part in parts]
        return marker.join(parts), ordered


def _compile_filter(item, field, dialect, parameters=None, binder=None):
    binder = binder or _Binder(None)
    left = field(item['field'])
    operator = item.get('operator', 'eq')
    if item.get('parameter_id') is not None:
        parameter_id = item['parameter_id']
        if parameter_id not in (parameters or {}):
            raise SemanticModelError(
                f'query parameter {parameter_id!r} has no value'
            )
        item = dict(item)
        item['value'] = parameters[parameter_id]
    unary = {'is_null': 'IS NULL', 'is_not_null': 'IS NOT NULL'}
    if operator in unary:
        return f'{left} {unary[operator]}'
    if operator in {'in', 'not_in'}:
        values = item.get('value')
        if not isinstance(values, list) or not values:
            raise SemanticModelError(
                'set filter value must be a non-empty array'
            )
        keyword = 'IN' if operator == 'in' else 'NOT IN'
        literals = ', '.join(
            binder.literal(value, dialect) for value in values)
        return f'{left} {keyword} ({literals})'
    if operator == 'between':
        values = item.get('value')
        if not isinstance(values, list) or len(values) != 2:
            raise SemanticModelError('between filter requires two values')
        return (
            f'{left} BETWEEN {binder.literal(values[0], dialect)} '
            f'AND {binder.literal(values[1], dialect)}'
        )
    operators = {
        'eq': '=', 'ne': '<>', 'lt': '<', 'lte': '<=',
        'gt': '>', 'gte': '>=',
    }
    literal = binder.literal(item.get('value'), dialect)
    return f'{left} {operators[operator]} {literal}'

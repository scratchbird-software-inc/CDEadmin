##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Translate saved-question builder state into the semantic contract.

No SQL is generated here.  Builder state becomes a synthetic one-source
semantic model plus a semantic query, which the provider compiles through
``semantic_models.compiler.compile_sql`` and its own dialect contract.
"""

from __future__ import annotations

import copy

from .models import BIError, output_id

SOURCE_ID = 'src'


def _unique(name, used):
    base, index = name, 2
    while name in used:
        name = f'{base}_{index}'
        index += 1
    used.add(name)
    return name


def builder_to_semantic(builder, parameters, family='relational'):
    """Return ``(model, query, columns)`` for an ad hoc builder question."""
    used = set()

    def ref(column):
        return {'source_id': SOURCE_ID, 'field': column}

    dimensions, measures, columns = [], [], []
    by_column = {}
    by_alias = {}

    for entry in builder['group_by']:
        alias = _unique(entry.get('alias') or output_id(entry['column']), used)
        dimensions.append({
            'id': alias, 'name': entry['column'],
            'field': ref(entry['column']),
        })
        columns.append({'id': alias, 'kind': 'dimension',
                        'label': entry['column']})
        by_column.setdefault(entry['column'], alias)
        by_alias[alias] = alias
    for entry in builder['aggregations']:
        column = entry.get('column')
        default = entry['function'] + (
            f'_{output_id(column)}' if column else '')
        alias = _unique(entry.get('alias') or default, used)
        measure = {'id': alias, 'name': alias,
                   'aggregation': entry['function']}
        if column is not None:
            measure['field'] = ref(column)
        measures.append(measure)
        columns.append({'id': alias, 'kind': 'measure', 'label': alias})
        by_alias[alias] = alias
    if not builder['aggregations']:
        for entry in builder['columns']:
            alias = _unique(entry.get('alias') or output_id(entry['column']),
                            used)
            measures.append({'id': alias, 'name': entry['column'],
                             'aggregation': 'none',
                             'field': ref(entry['column'])})
            columns.append({'id': alias, 'kind': 'column',
                            'label': entry['column']})
            by_column.setdefault(entry['column'], alias)
            by_alias[alias] = alias
    model = {
        'name': 'builder', 'semantic_family': family,
        'sources': [{
            'id': SOURCE_ID,
            'resource_id': 'builder:' + '.'.join(
                builder['source']['relation']),
            'relation': list(builder['source']['relation']),
            'alias': SOURCE_ID,
        }],
        'joins': [], 'dimensions': dimensions, 'measures': measures,
        'parameters': copy.deepcopy(parameters),
    }
    filters = []
    for entry in builder['filters']:
        item = {key: value for key, value in entry.items()
                if key != 'column'}
        item['field'] = ref(entry['column'])
        filters.append(item)
    order_by = []
    for entry in builder['order_by']:
        key = entry['column']
        target = by_alias.get(key) or by_column.get(key)
        if target is None:
            raise BIError(f'order_by {key!r} is not a selected output')
        order_by.append({'id': target, 'direction': entry['direction']})
    query = {
        'axes': {'rows': [d['id'] for d in dimensions], 'columns': [],
                 'pages': []},
        'measures': [m['id'] for m in measures],
        'filters': filters, 'order_by': order_by,
        'limit': builder['limit'],
    }
    return model, query, columns


def semantic_to_query(builder):
    """Translate a model-bound builder into a semantic query."""
    return {
        'axes': {'rows': list(builder['group_by']), 'columns': [],
                 'pages': []},
        'measures': [m['measure_id'] for m in builder['aggregations']],
        'filters': copy.deepcopy(builder['filters']),
        'order_by': copy.deepcopy(builder['order_by']),
        'limit': builder['limit'],
    }

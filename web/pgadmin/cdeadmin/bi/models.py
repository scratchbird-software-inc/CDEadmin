##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Validation of provider-neutral saved questions and collections."""

from __future__ import annotations

import copy
import re
from typing import Any, Mapping

from pgadmin.cdeadmin.semantic_models.models import (
    CHART_TYPES, EXPORT_FORMATS, FILTER_OPERATORS, PARAMETER_TYPES,
    SemanticModelError,
    _validate_parameter_value, identifier, required_text,
)


CONTRACT_VERSION = '1.0.0'
QUESTION_STATUSES = frozenset({'active', 'archived'})
QUERY_KINDS = frozenset({'builder', 'semantic', 'sql'})
BUILDER_AGGREGATIONS = frozenset({
    'sum', 'count', 'count_distinct', 'min', 'max', 'avg',
})
MAX_SQL_LENGTH = 200000


class BIError(SemanticModelError):
    """A saved question or collection request cannot be admitted."""


class BIConflict(BIError):
    """An optimistic revision check failed."""


def _text(value, label, maximum=512):
    try:
        return required_text(value, label, maximum)
    except SemanticModelError as exc:
        raise BIError(str(exc)) from exc


def _ident(value, label):
    try:
        return identifier(value, label)
    except SemanticModelError as exc:
        raise BIError(str(exc)) from exc


def _map(value, label):
    if not isinstance(value, Mapping):
        raise BIError(f'{label} must be an object')
    return copy.deepcopy(dict(value))


def _list(value, label, maximum=128):
    if not isinstance(value, list) or len(value) > maximum:
        raise BIError(f'{label} must be an array of at most {maximum} items')
    return copy.deepcopy(value)


def validate_collection(value: Mapping[str, Any]) -> dict[str, Any]:
    item = _map(value, 'collection')
    parent = item.get('parent_id')
    if parent is not None and not isinstance(parent, str):
        raise BIError('collection.parent_id must be a string or null')
    return {
        'name': _text(item.get('name'), 'collection.name', 256),
        'description': str(item.get('description') or '')[:4096],
        'parent_id': parent,
    }


def validate_parameters(value):
    parameters = []
    seen = set()
    for raw in _list(value or [], 'question.parameters'):
        item = _map(raw, 'parameter')
        pid = _ident(item.get('id'), 'parameter.id')
        if pid in seen:
            raise BIError('parameter identifiers must be unique')
        seen.add(pid)
        ptype = item.get('type', 'string')
        if ptype not in PARAMETER_TYPES:
            raise BIError('parameter.type is unsupported')
        allowed = _list(item.get('allowed_values', []),
                        'parameter.allowed_values', 500)
        normalized = {
            'id': pid,
            'name': _text(item.get('name', pid), 'parameter.name', 256),
            'type': ptype, 'required': bool(item.get('required', False)),
            'allowed_values': allowed,
        }
        try:
            for entry in allowed:
                _validate_parameter_value(entry, ptype)
            if 'default' in item:
                _validate_parameter_value(item['default'], ptype)
                if allowed and item['default'] not in allowed:
                    raise SemanticModelError(
                        'parameter default must be an allowed value')
        except SemanticModelError as exc:
            raise BIError(str(exc)) from exc
        if 'default' in item:
            normalized['default'] = item['default']
        parameters.append(normalized)
    return parameters


def validate_visualization(value):
    item = _map(value or {'type': 'table'}, 'visualization')
    kind = item.get('type', 'table')
    if kind not in CHART_TYPES:
        raise BIError('visualization.type is unsupported')
    return {'type': kind,
            'settings': _map(item.get('settings', {}),
                             'visualization.settings')}


DEFAULT_CACHE_TTL = 300
MAX_CACHE_TTL = 86400
DEFAULT_PAGE_SIZE = 100


def validate_result_policy(value):
    """Normalize how a question's result may be cached, shown and exported.

    Export is off unless a question opts in, and only for the listed
    formats; redacted columns are masked in every page and export.
    """
    item = _map(value if value is not None else {}, 'result_policy')
    redact = []
    for column in _list(item.get('redact_columns', []),
                        'result_policy.redact_columns', 64):
        redact.append(_text(column, 'result_policy.redact_columns', 128))
    export = _map(item.get('export', {}), 'result_policy.export')
    formats = _list(export.get('formats', []), 'result_policy.export.formats',
                    len(EXPORT_FORMATS))
    if any(f not in EXPORT_FORMATS for f in formats):
        raise BIError('result_policy.export.formats has an unsupported format')
    if export.get('enabled', False) and not formats:
        raise BIError('enabled export needs at least one format')
    ttl = item.get('cache_ttl_seconds', DEFAULT_CACHE_TTL)
    if isinstance(ttl, bool) or not isinstance(ttl, int) or not (
            0 <= ttl <= MAX_CACHE_TTL):
        raise BIError('result_policy.cache_ttl_seconds must be 0 to 86400')
    page = item.get('page_size', DEFAULT_PAGE_SIZE)
    if isinstance(page, bool) or not isinstance(page, int) or not (
            1 <= page <= 500):
        raise BIError('result_policy.page_size must be 1 to 500')
    return {
        'redact_columns': list(dict.fromkeys(redact)),
        'export': {'enabled': bool(export.get('enabled', False)),
                   'formats': list(dict.fromkeys(formats))},
        'cache_ttl_seconds': ttl, 'page_size': page,
    }


def _filters(value, parameter_ids, field_key):
    result = []
    for raw in _list(value or [], 'builder.filters'):
        item = _map(raw, 'filter')
        operator = item.get('operator', 'eq')
        if operator not in FILTER_OPERATORS:
            raise BIError('filter.operator is unsupported')
        entry = {'operator': operator}
        if field_key == 'column':
            entry['column'] = _text(item.get('column'), 'filter.column')
        else:
            ref = _map(item.get('field'), 'filter.field')
            entry['field'] = {
                'source_id': _ident(ref.get('source_id'), 'filter.source_id'),
                'field': _text(ref.get('field'), 'filter.field.field'),
            }
        if item.get('parameter_id') is not None:
            if item['parameter_id'] not in parameter_ids:
                raise BIError('filter references an unknown parameter')
            if 'value' in item:
                raise BIError('filter cannot have both value and parameter')
            entry['parameter_id'] = item['parameter_id']
        elif 'value' in item:
            entry['value'] = item['value']
        result.append(entry)
    return result


def _limit(value):
    value = 500 if value is None else value
    if isinstance(value, bool) or not isinstance(value, int) or not (
            1 <= value <= 10000):
        raise BIError('limit must be an integer between 1 and 10000')
    return value


def _orders(value, key):
    result = []
    for raw in _list(value or [], 'builder.order_by', 32):
        item = _map(raw, 'order_by entry')
        direction = item.get('direction', 'asc')
        if direction not in {'asc', 'desc'}:
            raise BIError('order_by direction must be asc or desc')
        result.append({key: _text(item.get(key), f'order_by.{key}'),
                       'direction': direction})
    return result


def _named(value, label):
    """Accept ``"col"`` or ``{"column": "col", "alias": "a"}``."""
    if isinstance(value, str):
        return {'column': _text(value, label)}
    item = _map(value, label)
    entry = {'column': _text(item.get('column'), label + '.column')}
    if item.get('alias') is not None:
        entry['alias'] = _ident(item['alias'], label + '.alias')
    return entry


def validate_query_spec(value, parameter_ids):
    spec = _map(value, 'question.query')
    kind = spec.get('kind')
    if kind not in QUERY_KINDS:
        raise BIError('question.query.kind must be builder, semantic or sql')
    if kind == 'sql':
        sql = spec.get('sql')
        if not isinstance(sql, str) or not sql.strip() or (
                len(sql) > MAX_SQL_LENGTH) or '\x00' in sql:
            raise BIError('question.query.sql must be non-empty text')
        return {'kind': 'sql', 'sql': sql}
    raw = _map(spec.get('builder'), 'question.query.builder')
    if kind == 'builder':
        source = _map(raw.get('source'), 'builder.source')
        relation = _list(source.get('relation'), 'builder.source.relation', 8)
        if not relation or not all(
                isinstance(p, str) and p.strip() for p in relation):
            raise BIError('builder.source.relation needs identifier parts')
        columns = [_named(c, 'builder.columns')
                   for c in _list(raw.get('columns', []), 'builder.columns')]
        group_by = [_named(c, 'builder.group_by')
                    for c in _list(raw.get('group_by', []),
                                   'builder.group_by', 32)]
        aggregations = []
        for entry in _list(raw.get('aggregations', []),
                           'builder.aggregations', 64):
            item = _map(entry, 'aggregation')
            function = item.get('function')
            if function not in BUILDER_AGGREGATIONS:
                raise BIError('aggregation.function is unsupported')
            normalized = {'function': function}
            if item.get('column') is not None:
                normalized['column'] = _text(item['column'],
                                             'aggregation.column')
            elif function != 'count':
                raise BIError('aggregation requires a column')
            if item.get('alias') is not None:
                normalized['alias'] = _ident(item['alias'],
                                             'aggregation.alias')
            aggregations.append(normalized)
        if aggregations:
            grouped = {c['column'] for c in group_by}
            if any(c['column'] not in grouped for c in columns):
                raise BIError(
                    'with aggregations, columns must also be grouped')
        else:
            if group_by:
                raise BIError('group_by requires at least one aggregation')
            if not columns:
                raise BIError('builder needs columns or aggregations')
        return {'kind': 'builder', 'builder': {
            'source': {'relation': [p.strip() for p in relation]},
            'columns': columns, 'group_by': group_by,
            'aggregations': aggregations,
            'filters': _filters(raw.get('filters'), parameter_ids, 'column'),
            'order_by': _orders(raw.get('order_by'), 'column'),
            'limit': _limit(raw.get('limit')),
        }}
    group_by = [_text(i, 'builder.group_by', 128) for i in _list(
        raw.get('group_by', []), 'builder.group_by', 32)]
    measures = [
        _text(_map(entry, 'aggregation').get('measure_id'),
              'aggregation.measure_id', 128)
        for entry in _list(raw.get('aggregations', []),
                           'builder.aggregations', 64)
    ]
    if not measures:
        raise BIError('semantic builder needs at least one measure')
    return {'kind': 'semantic', 'builder': {
        'group_by': group_by,
        'aggregations': [{'measure_id': m} for m in measures],
        'filters': _filters(raw.get('filters'), parameter_ids, 'field'),
        'order_by': _orders(raw.get('order_by'), 'id'),
        'limit': _limit(raw.get('limit')),
    }}


def validate_question(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize a saved-question document."""
    item = _map(value, 'question')
    parameters = validate_parameters(item.get('parameters'))
    parameter_ids = {p['id'] for p in parameters}
    model = item.get('semantic_model')
    reference = None
    if model is not None:
        model = _map(model, 'question.semantic_model')
        revision = model.get('revision')
        if revision is not None and (
                isinstance(revision, bool) or not isinstance(revision, int)
                or revision < 1):
            raise BIError('semantic_model.revision must be a positive integer')
        reference = {'id': _text(model.get('id'), 'semantic_model.id', 36),
                     'revision': revision}
    query = validate_query_spec(item.get('query'), parameter_ids)
    if query['kind'] == 'semantic' and reference is None:
        raise BIError('semantic questions require a semantic_model')
    collection_id = item.get('collection_id')
    if collection_id is not None and not isinstance(collection_id, str):
        raise BIError('question.collection_id must be a string or null')
    return {
        'contract_version': CONTRACT_VERSION,
        'name': _text(item.get('name'), 'question.name', 256),
        'description': str(item.get('description') or '')[:4096],
        'collection_id': collection_id,
        'semantic_model': reference,
        'query': query,
        'visualization': validate_visualization(item.get('visualization')),
        'parameters': parameters,
        'result_policy': validate_result_policy(item.get('result_policy')),
    }


_SAFE = re.compile(r'[^A-Za-z0-9_]+')


def output_id(name):
    """Derive a semantic-model identifier from a native column name."""
    text = _SAFE.sub('_', str(name)).strip('_') or 'col'
    if not text[0].isalpha():
        text = 'c_' + text
    return text[:100]

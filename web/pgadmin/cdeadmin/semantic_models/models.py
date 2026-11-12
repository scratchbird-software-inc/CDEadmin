##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Provider-neutral semantic-model contracts and validation."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field as dc_field
import json
import re
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .profiles import analytical_profile


CONTRACT_VERSION = '1.0.0'
MODEL_STATUSES = frozenset({'draft', 'published', 'archived'})
SEMI_ADDITIVE_AGGREGATIONS = frozenset({
    'last_value', 'first_value', 'last_non_empty', 'first_non_empty',
    'avg_over_time',
})
WITHIN_GROUP_AGGREGATIONS = frozenset({'sum', 'min', 'max', 'avg', 'count'})
AGGREGATIONS = frozenset({
    'sum', 'count', 'count_distinct', 'min', 'max', 'avg', 'none',
}) | SEMI_ADDITIVE_AGGREGATIONS
HIERARCHY_KINDS = frozenset({'level', 'parent_child'})
TRANSLATION_TARGET_KINDS = frozenset({
    'model', 'dimension', 'attribute', 'hierarchy', 'level', 'measure',
    'measure_group', 'perspective',
})
_LOCALE_RE = re.compile(r'^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$')
CALCULATION_OPERATORS = frozenset({
    'add', 'subtract', 'multiply', 'divide',
})
JOIN_TYPES = frozenset({'inner', 'left', 'right', 'full', 'cross'})
SOURCE_CLASSIFICATIONS = frozenset({
    'fact', 'dimension', 'bridge', 'lookup', 'node-set',
    'relationship-set', 'path-set', 'projection', 'document-set',
    'embedded-array', 'event', 'indexed-document-set', 'data-stream',
    'search-view', 'vector-set', 'partition', 'metadata-set', 'measurement',
    'event-series', 'metric-series', 'dictionary', 'partitioned-table',
    'materialized-view', 'keyspace', 'data-structure', 'stream',
    'ordered-range', 'entity-history', 'transaction-set',
})
PARAMETER_TYPES = frozenset({
    'string', 'integer', 'number', 'boolean', 'date', 'datetime', 'array',
})
CARDINALITIES = frozenset({
    'one-to-one', 'one-to-many', 'many-to-one', 'many-to-many',
})
TIME_ROLES = frozenset({
    'event-time', 'processing-time', 'valid-time', 'system-time',
    'calendar-time', 'fiscal-time',
})
CERTIFICATION_STATUSES = frozenset({
    'uncertified', 'candidate', 'certified', 'deprecated',
})
CHART_TYPES = frozenset({
    'table', 'pivot', 'bar', 'line', 'area', 'scatter', 'pie', 'metric',
    'histogram', 'timeline', 'graph', 'vector-neighbors',
})
EXPORT_FORMATS = frozenset({
    'csv', 'json', 'jsonl', 'xlsx', 'svg', 'pdf',
})
FILTER_OPERATORS = frozenset({
    'eq', 'ne', 'lt', 'lte', 'gt', 'gte', 'in', 'not_in', 'between',
    'is_null', 'is_not_null',
})
TIME_OPERATIONS = frozenset({
    'as_of', 'range', 'period_to_date', 'period_comparison',
})
TIME_PERIODS = frozenset({
    'day', 'week', 'month', 'quarter', 'year',
    'fiscal_quarter', 'fiscal_year',
})
WINDOW_OPERATIONS = frozenset({
    'running_sum', 'moving_sum', 'moving_average', 'lag', 'delta',
    'percent_change', 'rank', 'dense_rank',
})
DIMENSION_USAGE_KINDS = frozenset({
    'regular', 'referenced', 'fact', 'many_to_many',
})
ATTRIBUTE_RELATIONSHIP_TYPES = frozenset({'changing', 'fixed'})
UNKNOWN_MEMBER_POLICIES = frozenset({'unknown', 'hide', 'error'})
PARTITION_GRAINS = frozenset({'none', 'day', 'month', 'year'})
REFRESH_POLICIES = frozenset({
    'manual', 'incremental', 'full_rebuild', 'on_accept_review', 'scheduled',
})
_ID = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,127}$')


@dataclass(frozen=True)
class CubeAttribute:
    """Typed dimensional attribute / hierarchy level metadata."""

    id: str
    name: str
    field: dict[str, str]
    sort_field: dict[str, str] | None = None
    relationship_type: str = 'changing'

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            'id': self.id,
            'name': self.name,
            'field': copy.deepcopy(self.field),
            'relationship_type': self.relationship_type,
        }
        if self.sort_field is not None:
            out['sort_field'] = copy.deepcopy(self.sort_field)
        return out


@dataclass(frozen=True)
class CubeDimension:
    """Typed cube dimension specification with unknown-member & role policy."""

    id: str
    name: str
    field: dict[str, str]
    is_time: bool = False
    time_role: str | None = None
    key_field: dict[str, str] | None = None
    name_field: dict[str, str] | None = None
    sort_field: dict[str, str] | None = None
    attributes: tuple[dict[str, Any], ...] = ()
    hierarchies: tuple[dict[str, Any], ...] = ()
    role_of: str | None = None
    active: bool = True
    join_id: str | None = None
    unknown_member_policy: str = 'unknown'
    unknown_member_caption: str = 'Unknown'
    visible_roles: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            'id': self.id,
            'name': self.name,
            'field': copy.deepcopy(self.field),
            'is_time': self.is_time,
            'time_role': self.time_role,
            'hierarchies': [copy.deepcopy(h) for h in self.hierarchies],
            'unknown_member_policy': self.unknown_member_policy,
            'unknown_member_caption': self.unknown_member_caption,
            'visible_roles': list(self.visible_roles),
        }
        if self.key_field is not None:
            out['key_field'] = copy.deepcopy(self.key_field)
        if self.name_field is not None:
            out['name_field'] = copy.deepcopy(self.name_field)
        if self.sort_field is not None:
            out['sort_field'] = copy.deepcopy(self.sort_field)
        if self.attributes:
            out['attributes'] = [copy.deepcopy(a) for a in self.attributes]
        if self.role_of is not None:
            out['role_of'] = self.role_of
            out['active'] = self.active
        if self.join_id is not None:
            out['join_id'] = self.join_id
        return out


@dataclass(frozen=True)
class CubeMeasure:
    """Typed cube measure specification with role visibility."""

    id: str
    name: str
    aggregation: str = 'sum'
    field: dict[str, str] | None = None
    expression: dict[str, Any] | None = None
    format: str = ''
    description: str = ''
    display_folder: str = ''
    measure_group_id: str | None = None
    filters: tuple[dict[str, Any], ...] = ()
    semi_additive_dimension: str | None = None
    within_group_aggregation: str = 'sum'
    visible_roles: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            'id': self.id,
            'name': self.name,
            'aggregation': self.aggregation,
            'field': copy.deepcopy(self.field),
            'format': self.format,
            'visible_roles': list(self.visible_roles),
        }
        if self.expression is not None:
            out['expression'] = copy.deepcopy(self.expression)
        if self.description:
            out['description'] = self.description
        if self.display_folder:
            out['display_folder'] = self.display_folder
        if self.measure_group_id is not None:
            out['measure_group_id'] = self.measure_group_id
        if self.filters:
            out['filters'] = [copy.deepcopy(f) for f in self.filters]
        if self.semi_additive_dimension is not None:
            out['semi_additive_dimension'] = self.semi_additive_dimension
            out['within_group_aggregation'] = self.within_group_aggregation
        return out


@dataclass(frozen=True)
class CubePerspective:
    """Typed cube perspective specification with role visibility."""

    id: str
    name: str
    description: str = ''
    dimensions: tuple[str, ...] = ()
    measures: tuple[str, ...] = ()
    measure_groups: tuple[str, ...] = ()
    hierarchies: tuple[str, ...] = ()
    default_measure: str | None = None
    visible_roles: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'dimensions': list(self.dimensions),
            'measures': list(self.measures),
            'measure_groups': list(self.measure_groups),
            'hierarchies': list(self.hierarchies),
            'visible_roles': list(self.visible_roles),
        }
        if self.default_measure is not None:
            out['default_measure'] = self.default_measure
        return out


@dataclass(frozen=True)
class CubeAggregationPlan:
    """Typed cube aggregation / materialization plan specification."""

    id: str
    name: str
    strategy: str = 'aggregate_table'
    enabled: bool = True
    measure_group_id: str | None = None
    grain_dimensions: tuple[str, ...] = ()
    measures: tuple[str, ...] = ()
    target_relation: tuple[str, ...] = ()
    partition_field: dict[str, str] | str | None = None
    partition_grain: str = 'none'
    refresh_policy: str = 'manual'
    rule_group: dict[str, Any] | None = dc_field(default=None)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            'id': self.id,
            'name': self.name,
            'strategy': self.strategy,
            'enabled': self.enabled,
            'grain_dimensions': list(self.grain_dimensions),
            'measures': list(self.measures),
            'target_relation': list(self.target_relation),
            'partition_grain': self.partition_grain,
            'refresh_policy': self.refresh_policy,
        }
        if self.measure_group_id is not None:
            out['measure_group_id'] = self.measure_group_id
        if self.partition_field is not None:
            out['partition_field'] = copy.deepcopy(self.partition_field)
        if self.rule_group is not None:
            out['rule_group'] = copy.deepcopy(self.rule_group)
        return out


class SemanticModelError(RuntimeError):
    """A semantic-model request cannot be admitted safely."""


class SemanticModelConflict(SemanticModelError):
    """A model revision changed before a requested mutation."""


class SemanticCompilationUnavailable(SemanticModelError):
    """The endpoint provider has no semantic-query compiler."""


def required_text(value, label, maximum=512):
    if not isinstance(value, str) or not value.strip():
        raise SemanticModelError(f'{label} must not be empty')
    value = value.strip()
    if len(value) > maximum:
        raise SemanticModelError(f'{label} exceeds its length limit')
    return value


def identifier(value, label):
    value = required_text(value, label, 128)
    if not _ID.fullmatch(value):
        raise SemanticModelError(f'{label} is not a portable identifier')
    return value


def mapping(value, label):
    if hasattr(value, 'to_dict') and callable(value.to_dict):
        value = value.to_dict()
    if not isinstance(value, Mapping):
        raise SemanticModelError(f'{label} must be an object')
    return copy.deepcopy(dict(value))


def array(value, label, maximum=500):
    if isinstance(value, tuple):
        value = list(value)
    if not isinstance(value, list):
        raise SemanticModelError(f'{label} must be an array')
    if len(value) > maximum:
        raise SemanticModelError(f'{label} exceeds its item limit')
    return [
        copy.deepcopy(
            item.to_dict()
            if hasattr(item, 'to_dict') and callable(item.to_dict)
            else item
        )
        for item in value
    ]


def _validate_visible_roles(value, label) -> list[str]:
    raw_items = array(value, label, 128)
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        role_id = identifier(raw, f'{label}.role')
        if role_id not in seen:
            seen.add(role_id)
            normalized.append(role_id)
    return normalized


def _unique(items, label):
    seen = set()
    for item in items:
        if not isinstance(item, Mapping):
            raise SemanticModelError(f'{label} items must be objects')
        item_id = identifier(item.get('id'), f'{label}.id')
        if item_id in seen:
            raise SemanticModelError(f'{label} identifiers must be unique')
        seen.add(item_id)
    return seen


def validate_model(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize a complete semantic model document."""
    model = mapping(value, 'model')
    model['contract_version'] = CONTRACT_VERSION
    model['name'] = required_text(model.get('name'), 'model.name', 256)
    model['description'] = str(model.get('description') or '')[:4096]
    model['semantic_family'] = identifier(
        model.get('semantic_family', 'relational'), 'model.semantic_family'
    )
    profile = analytical_profile(model['semantic_family'])
    if not profile['recognized_model_family']:
        raise SemanticModelError('model.semantic_family is unsupported')
    sources = array(model.get('sources', []), 'model.sources', 64)
    if not sources:
        raise SemanticModelError('model.sources must contain a data source')
    source_ids = _unique(sources, 'model.sources')
    normalized_sources = []
    for source in sources:
        source = mapping(source, 'source')
        source['id'] = identifier(source['id'], 'source.id')
        source['resource_id'] = required_text(
            source.get('resource_id'), 'source.resource_id', 1024
        )
        source['relation'] = array(
            source.get('relation', []), 'source.relation', 8
        )
        if not source['relation'] or not all(
            isinstance(part, str) and part.strip()
            for part in source['relation']
        ):
            raise SemanticModelError(
                'source.relation must contain native identifier parts'
            )
        source['relation'] = [part.strip() for part in source['relation']]
        source['alias'] = identifier(
            source.get('alias', source['id']), 'source.alias'
        )
        source['source_kind'] = identifier(
            source.get('source_kind', profile['source_kinds'][0]),
            'source.source_kind'
        )
        if source['source_kind'] not in profile['source_kinds']:
            raise SemanticModelError('source.source_kind is unsupported')
        classification = source.get(
            'classification', profile['source_classifications'][0]
        )
        if classification not in SOURCE_CLASSIFICATIONS or (
                classification not in profile['source_classifications']):
            raise SemanticModelError(
                'source.classification is unsupported'
            )
        source['classification'] = classification
        grain = array(source.get('grain', []), 'source.grain', 32)
        for reference in grain:
            _validate_field_reference(reference, source_ids)
        source['grain'] = grain
        source['provider_config'] = mapping(
            source.get('provider_config', {}), 'source.provider_config'
        )
        normalized_sources.append(source)
    model['sources'] = normalized_sources

    joins = array(model.get('joins', []), 'model.joins', 128)
    join_ids = _unique(joins, 'model.joins')
    for join in joins:
        identifier(join.get('id'), 'join.id')
        if join.get('left_source') not in source_ids or (
            join.get('right_source') not in source_ids
        ):
            raise SemanticModelError('join references an unknown source')
        if join.get('join_type', 'inner') not in JOIN_TYPES:
            raise SemanticModelError('join.join_type is unsupported')
        cardinality = join.get('cardinality', 'many-to-one')
        if cardinality not in CARDINALITIES:
            raise SemanticModelError('join.cardinality is unsupported')
        join['cardinality'] = cardinality
        if 'active' in join:
            join['active'] = bool(join['active'])
        predicates = array(join.get('predicates', []), 'join.predicates', 32)
        if join.get('join_type', 'inner') != 'cross' and not predicates:
            raise SemanticModelError('non-cross joins require predicates')
        for predicate in predicates:
            _validate_field_reference(predicate.get('left'), source_ids)
            _validate_field_reference(predicate.get('right'), source_ids)
            if predicate.get('operator', 'eq') != 'eq':
                raise SemanticModelError(
                    'join predicate operator is unsupported'
                )
    model['joins'] = joins

    relationships = array(
        model.get('relationships', []), 'model.relationships', 256
    )
    _unique(relationships, 'model.relationships')
    for relationship in relationships:
        relationship['name'] = required_text(
            relationship.get('name'), 'relationship.name', 256
        )
        if relationship.get('from_source') not in source_ids or (
                relationship.get('to_source') not in source_ids):
            raise SemanticModelError(
                'relationship references an unknown source'
            )
        relationship['relationship_kind'] = identifier(
            relationship.get(
                'relationship_kind', profile['relationship_kinds'][0]
            ),
            'relationship.relationship_kind',
        )
        if relationship['relationship_kind'] not in profile[
                'relationship_kinds']:
            raise SemanticModelError(
                'relationship.relationship_kind is unsupported'
            )
        relationship['provider_config'] = mapping(
            relationship.get('provider_config', {}),
            'relationship.provider_config',
        )
    model['relationships'] = relationships

    dimensions = array(model.get('dimensions', []), 'model.dimensions')
    dimension_ids = _unique(dimensions, 'model.dimensions')
    level_ids = set()
    hierarchy_ids = set()
    parent_child_ids = set()
    attribute_ids = set()
    time_dimension_ids = []
    for dimension in dimensions:
        identifier(dimension.get('id'), 'dimension.id')
        dimension['name'] = required_text(
            dimension.get('name'), 'dimension.name', 256
        )
        if 'description' in dimension:
            dimension['description'] = str(
                dimension.get('description') or ''
            )[:2048]
        if 'display_folder' in dimension:
            dimension['display_folder'] = str(
                dimension.get('display_folder') or ''
            )[:256]
        dimension['dimension_kind'] = identifier(
            dimension.get('dimension_kind', profile['dimension_kinds'][0]),
            'dimension.dimension_kind',
        )
        if dimension['dimension_kind'] not in profile['dimension_kinds']:
            raise SemanticModelError('dimension.dimension_kind is unsupported')
        _validate_field_reference(dimension.get('field'), source_ids)
        time = dimension.get('time_intelligence')
        if time is not None:
            time = mapping(time, 'dimension.time_intelligence')
            if time.get('role', 'calendar-time') not in TIME_ROLES:
                raise SemanticModelError(
                    'dimension time-intelligence role is unsupported'
                )
            time['role'] = time.get('role', 'calendar-time')
            time['calendar'] = identifier(
                time.get('calendar', 'gregorian'),
                'dimension.time_intelligence.calendar',
            )
            time['timezone'] = required_text(
                time.get('timezone', 'UTC'),
                'dimension.time_intelligence.timezone', 128,
            )
            try:
                ZoneInfo(time['timezone'])
            except (ValueError, ZoneInfoNotFoundError) as exc:
                raise SemanticModelError(
                    'dimension time-intelligence timezone is invalid'
                ) from exc
            value_type = time.get('value_type', 'string')
            if value_type not in {'string', 'date', 'datetime'}:
                raise SemanticModelError(
                    'dimension time-intelligence value type is unsupported'
                )
            time['value_type'] = value_type
            fiscal_month = time.get('fiscal_year_start_month', 1)
            if isinstance(fiscal_month, bool) or not isinstance(
                    fiscal_month, int) or not 1 <= fiscal_month <= 12:
                raise SemanticModelError(
                    'fiscal year start month must be between 1 and 12'
                )
            time['fiscal_year_start_month'] = fiscal_month
            time_dimension_ids.append(dimension['id'])
        dimension['time_intelligence'] = time
        dimension['provider_config'] = mapping(
            dimension.get('provider_config', {}),
            'dimension.provider_config',
        )
        hierarchies = array(
            dimension.get('hierarchies', []), 'dimension.hierarchies', 64
        )
        dim_hier_ids = _unique(hierarchies, 'dimension.hierarchies')
        if dim_hier_ids & hierarchy_ids:
            raise SemanticModelError('hierarchy identifiers must be unique')
        hierarchy_ids.update(dim_hier_ids)
        for hierarchy in hierarchies:
            hierarchy['name'] = required_text(
                hierarchy.get('name'), 'hierarchy.name', 256
            )
            h_kind = hierarchy.get('hierarchy_kind', 'level')
            if h_kind not in HIERARCHY_KINDS:
                raise SemanticModelError(
                    'hierarchy.hierarchy_kind is unsupported'
                )
            if 'hierarchy_kind' in hierarchy or h_kind != 'level':
                hierarchy['hierarchy_kind'] = h_kind
            if 'ragged' in hierarchy or h_kind == 'parent_child':
                hierarchy['ragged'] = bool(
                    hierarchy.get('ragged', h_kind == 'parent_child')
                )
            if h_kind == 'parent_child':
                _validate_field_reference(
                    hierarchy.get('child_field'), source_ids
                )
                _validate_field_reference(
                    hierarchy.get('parent_field'), source_ids
                )
                child_src = hierarchy['child_field']['source_id']
                parent_src = hierarchy['parent_field']['source_id']
                if child_src != parent_src:
                    raise SemanticModelError(
                        'parent-child hierarchy fields must share a source'
                    )
                if hierarchy.get('name_field') is not None:
                    _validate_field_reference(
                        hierarchy['name_field'], source_ids
                    )
                root_val = hierarchy.get('root_parent_value')
                if root_val is not None and (
                    isinstance(root_val, bool)
                    or not isinstance(root_val, (int, str))
                ):
                    raise SemanticModelError(
                        'parent-child root_parent_value must be int, str '
                        'or null'
                    )
                max_depth = hierarchy.get('max_depth', 16)
                if (
                    isinstance(max_depth, bool)
                    or not isinstance(max_depth, int)
                    or not 1 <= max_depth <= 64
                ):
                    raise SemanticModelError(
                        'parent-child max_depth must be between 1 and 64'
                    )
                hierarchy['max_depth'] = max_depth
                raw_levels = hierarchy.get('levels')
                if raw_levels:
                    levels = array(raw_levels, 'hierarchy.levels', 64)
                else:
                    levels = [{
                        'id': f"{hierarchy['id']}_member",
                        'name': hierarchy['name'],
                        'field': copy.deepcopy(hierarchy['child_field']),
                    }]
                hierarchy['levels'] = levels
                if hierarchy['id'] in level_ids or (
                    hierarchy['id'] in dimension_ids
                ):
                    raise SemanticModelError(
                        'parent-child hierarchy id collides with level or '
                        'dimension'
                    )
                level_ids.add(hierarchy['id'])
                parent_child_ids.add(hierarchy['id'])
            else:
                levels = array(
                    hierarchy.get('levels', []), 'hierarchy.levels', 64
                )
                if not levels:
                    raise SemanticModelError(
                        'hierarchy.levels must not be empty'
                    )
            for level in levels:
                level_id = identifier(level.get('id'), 'level.id')
                if level_id in level_ids:
                    raise SemanticModelError(
                        'level identifiers must be unique'
                    )
                level_ids.add(level_id)
                level['name'] = required_text(level.get('name'), 'level.name')
                _validate_field_reference(level.get('field'), source_ids)
                if 'relationship_type' in level:
                    rel_type = str(
                        level.get('relationship_type') or 'changing'
                    ).strip()
                    if rel_type not in ATTRIBUTE_RELATIONSHIP_TYPES:
                        raise SemanticModelError(
                            'level.relationship_type must be changing or fixed'
                        )
                    level['relationship_type'] = rel_type
        for ref_key in ('key_field', 'name_field', 'sort_field'):
            if dimension.get(ref_key) is not None:
                _validate_field_reference(dimension[ref_key], source_ids)
        if 'attributes' in dimension:
            attrs = array(
                dimension.get('attributes', []), 'dimension.attributes', 128
            )
            _unique(attrs, 'dimension.attributes')
            for attr in attrs:
                attr_id = identifier(attr.get('id'), 'attribute.id')
                if attr_id in level_ids or attr_id in dimension_ids:
                    raise SemanticModelError(
                        'attribute identifiers must be unique'
                    )
                level_ids.add(attr_id)
                attribute_ids.add(attr_id)
                attr['name'] = required_text(
                    attr.get('name'), 'attribute.name', 256
                )
                _validate_field_reference(attr.get('field'), source_ids)
                if attr.get('sort_field') is not None:
                    _validate_field_reference(attr['sort_field'], source_ids)
                if 'relationship_type' in attr:
                    rel_type = str(
                        attr.get('relationship_type') or 'changing'
                    ).strip()
                    if rel_type not in ATTRIBUTE_RELATIONSHIP_TYPES:
                        raise SemanticModelError(
                            'attribute.relationship_type must be changing or '
                            'fixed'
                        )
                    attr['relationship_type'] = rel_type
            dimension['attributes'] = attrs
        if 'unknown_member_policy' in dimension:
            um_policy = str(
                dimension.get('unknown_member_policy') or 'unknown'
            ).strip()
            if um_policy not in UNKNOWN_MEMBER_POLICIES:
                raise SemanticModelError(
                    'dimension.unknown_member_policy must be unknown, hide '
                    'or error'
                )
            dimension['unknown_member_policy'] = um_policy
        if 'unknown_member_caption' in dimension:
            dimension['unknown_member_caption'] = (
                str(dimension.get('unknown_member_caption') or '').strip()[:256]
                or 'Unknown'
            )
        if 'visible_roles' in dimension:
            dimension['visible_roles'] = _validate_visible_roles(
                dimension.get('visible_roles', []), 'dimension.visible_roles'
            )
        if dimension.get('role_of') is not None:
            role_of = identifier(dimension['role_of'], 'dimension.role_of')
            if role_of not in dimension_ids or role_of == dimension['id']:
                raise SemanticModelError(
                    'role-playing dimension must reference another dimension'
                )
            dimension['role_of'] = role_of
            dimension['active'] = bool(dimension.get('active', True))
        elif 'active' in dimension:
            dimension['active'] = bool(dimension['active'])
        if dimension.get('join_id') is not None:
            join_id = identifier(dimension['join_id'], 'dimension.join_id')
            if join_id not in join_ids:
                raise SemanticModelError(
                    'dimension.join_id references an unknown join'
                )
            dimension['join_id'] = join_id
    model['dimensions'] = dimensions

    measures = array(model.get('measures', []), 'model.measures')
    measure_ids = _unique(measures, 'model.measures')
    for measure in measures:
        identifier(measure.get('id'), 'measure.id')
        measure['name'] = required_text(measure.get('name'), 'measure.name')
        if 'description' in measure:
            measure['description'] = str(
                measure.get('description') or ''
            )[:2048]
        if 'display_folder' in measure:
            measure['display_folder'] = str(
                measure.get('display_folder') or ''
            )[:256]
        aggregation = measure.get('aggregation', 'sum')
        if aggregation not in AGGREGATIONS:
            raise SemanticModelError('measure.aggregation is unsupported')
        measure['aggregation'] = aggregation
        expression = measure.get('expression')
        if expression is not None:
            if aggregation in SEMI_ADDITIVE_AGGREGATIONS:
                raise SemanticModelError(
                    'semi-additive measure cannot use calculated expression'
                )
            measure['aggregation'] = 'none'
            measure['field'] = None
            _validate_expression(expression, measure_ids, measure['id'])
        elif aggregation == 'count' and measure.get('field') is None:
            measure['field'] = None
        else:
            _validate_field_reference(measure.get('field'), source_ids)
        if measure['aggregation'] in SEMI_ADDITIVE_AGGREGATIONS:
            sa_dim = measure.get('semi_additive_dimension')
            if sa_dim is None and time_dimension_ids:
                sa_dim = time_dimension_ids[0]
            if sa_dim is None:
                raise SemanticModelError(
                    'semi-additive measure requires semi_additive_dimension '
                    'or a declared time dimension'
                )
            sa_dim = identifier(sa_dim, 'measure.semi_additive_dimension')
            if sa_dim not in dimension_ids:
                raise SemanticModelError(
                    'measure.semi_additive_dimension references an unknown '
                    'dimension'
                )
            measure['semi_additive_dimension'] = sa_dim
            within_agg = measure.get('within_group_aggregation', 'sum')
            if within_agg not in WITHIN_GROUP_AGGREGATIONS:
                raise SemanticModelError(
                    'measure.within_group_aggregation is unsupported'
                )
            measure['within_group_aggregation'] = within_agg
        measure['format'] = str(measure.get('format') or '')[:128]
        measure['measure_kind'] = identifier(
            measure.get('measure_kind', (
                'calculated' if expression is not None else
                profile['measure_kinds'][0]
            )), 'measure.measure_kind'
        )
        if measure['measure_kind'] not in profile['measure_kinds'] and not (
                expression is not None and
                measure['measure_kind'] == 'calculated'):
            raise SemanticModelError('measure.measure_kind is unsupported')
        certification = mapping(
            measure.get('certification', {}), 'measure.certification'
        )
        status = certification.get('status', 'uncertified')
        if status not in CERTIFICATION_STATUSES:
            raise SemanticModelError(
                'measure certification status is unsupported'
            )
        certification['status'] = status
        certification['owner'] = str(
            certification.get('owner') or ''
        )[:256]
        certification['definition'] = str(
            certification.get('definition') or ''
        )[:4096]
        measure['certification'] = certification
        if 'visible_roles' in measure:
            measure['visible_roles'] = _validate_visible_roles(
                measure.get('visible_roles', []), 'measure.visible_roles'
            )
    dependencies = {
        item['id']: _expression_references(item.get('expression'))
        for item in measures
    }
    visited = set()
    visiting = set()

    def visit_measure(measure_id):
        if measure_id in visiting:
            raise SemanticModelError('calculated measure cycle is unsupported')
        if measure_id in visited:
            return
        visiting.add(measure_id)
        for dependency in dependencies[measure_id]:
            visit_measure(dependency)
        visiting.remove(measure_id)
        visited.add(measure_id)

    for measure_id in measure_ids:
        visit_measure(measure_id)
    model['measures'] = measures

    parameters = array(model.get('parameters', []), 'model.parameters', 128)
    parameter_ids = _unique(parameters, 'model.parameters')
    for parameter in parameters:
        parameter['name'] = required_text(
            parameter.get('name'), 'parameter.name', 256
        )
        parameter_type = parameter.get('type', 'string')
        if parameter_type not in PARAMETER_TYPES:
            raise SemanticModelError('parameter.type is unsupported')
        parameter['type'] = parameter_type
        parameter['required'] = bool(parameter.get('required', False))
        parameter['allowed_values'] = array(
            parameter.get('allowed_values', []),
            'parameter.allowed_values', 500,
        )
        for allowed in parameter['allowed_values']:
            _validate_parameter_value(allowed, parameter_type)
        if 'default' in parameter:
            _validate_parameter_value(parameter['default'], parameter_type)
            if parameter['allowed_values'] and parameter['default'] not in (
                    parameter['allowed_values']):
                raise SemanticModelError(
                    'parameter.default is not an allowed value'
                )
    model['parameters'] = parameters

    parameter_definitions = {item['id']: item for item in parameters}
    for measure in measures:
        if 'filters' in measure:
            if measure.get('expression') is not None and measure['filters']:
                raise SemanticModelError(
                    'calculated measures cannot carry row filters directly'
                )
            measure['filters'] = _validate_filters(
                measure.get('filters', []), source_ids, parameter_definitions
            )
        if measure.get('measure_group_id') is not None:
            measure['measure_group_id'] = identifier(
                measure['measure_group_id'], 'measure.measure_group_id'
            )
    model['default_filters'] = _validate_filters(
        model.get('default_filters', []), source_ids, parameter_definitions
    )
    measure_group_ids = set()
    if 'measure_groups' in model:
        groups = array(
            model.get('measure_groups', []), 'model.measure_groups', 64
        )
        measure_group_ids = _unique(groups, 'model.measure_groups')
        for group in groups:
            group['name'] = required_text(
                group.get('name'), 'measure_group.name', 256
            )
            fact_source = identifier(
                group.get('fact_source'), 'measure_group.fact_source'
            )
            if fact_source not in source_ids:
                raise SemanticModelError(
                    'measure_group.fact_source references an unknown source'
                )
            group['fact_source'] = fact_source
            grp_measures = array(
                group.get('measures', []), 'measure_group.measures', 256
            )
            for mid in grp_measures:
                if mid not in measure_ids:
                    raise SemanticModelError(
                        'measure_group references an unknown measure'
                    )
            group['measures'] = list(grp_measures)
            usages = array(
                group.get('dimension_usage', []),
                'measure_group.dimension_usage', 128,
            )
            seen_dims = set()
            norm_usages = []
            for usage in usages:
                usage = mapping(usage, 'dimension_usage')
                dim_id = identifier(
                    usage.get('dimension_id'), 'dimension_usage.dimension_id'
                )
                if dim_id not in dimension_ids:
                    raise SemanticModelError(
                        'dimension_usage references an unknown dimension'
                    )
                if dim_id in seen_dims:
                    raise SemanticModelError(
                        'dimension_usage entries must be unique per dimension'
                    )
                seen_dims.add(dim_id)
                rel_kind = usage.get('relationship_kind', 'regular')
                if rel_kind not in DIMENSION_USAGE_KINDS:
                    raise SemanticModelError(
                        'dimension_usage.relationship_kind is unsupported'
                    )
                usage['dimension_id'] = dim_id
                usage['relationship_kind'] = rel_kind
                usage['active'] = bool(usage.get('active', True))
                if usage.get('granularity_field') is not None:
                    _validate_field_reference(
                        usage['granularity_field'], source_ids
                    )
                if usage.get('join_id') is not None:
                    jid = identifier(
                        usage['join_id'], 'dimension_usage.join_id'
                    )
                    if jid not in join_ids:
                        raise SemanticModelError(
                            'dimension_usage.join_id is unknown'
                        )
                    usage['join_id'] = jid
                norm_usages.append(usage)
            group['dimension_usage'] = norm_usages
        model['measure_groups'] = groups
        for measure in measures:
            mg_id = measure.get('measure_group_id')
            if mg_id is not None and mg_id not in measure_group_ids:
                raise SemanticModelError(
                    'measure.measure_group_id references an unknown group'
                )
    admitted_grain = dimension_ids | level_ids
    materializations = array(
        model.get('materializations', []), 'model.materializations', 64
    )
    _unique(materializations, 'model.materializations')
    for materialization in materializations:
        materialization['name'] = required_text(
            materialization.get('name'), 'materialization.name'
        )
        materialization['strategy'] = identifier(
            materialization.get('strategy', 'provider_managed'),
            'materialization.strategy',
        )
        materialization['enabled'] = bool(
            materialization.get('enabled', False)
        )
        if materialization.get('measure_group_id') is not None:
            mg_id = identifier(
                materialization['measure_group_id'],
                'materialization.measure_group_id',
            )
            if measure_group_ids and mg_id not in measure_group_ids:
                raise SemanticModelError(
                    'materialization.measure_group_id is unknown'
                )
            materialization['measure_group_id'] = mg_id
        if 'grain_dimensions' in materialization:
            grain_dims = array(
                materialization.get('grain_dimensions', []),
                'materialization.grain_dimensions', 64,
            )
            if any(item not in admitted_grain for item in grain_dims):
                raise SemanticModelError(
                    'materialization.grain_dimensions has an unknown level'
                )
            materialization['grain_dimensions'] = list(grain_dims)
        if 'measures' in materialization:
            mat_measures = array(
                materialization.get('measures', []),
                'materialization.measures', 128,
            )
            if any(item not in measure_ids for item in mat_measures):
                raise SemanticModelError(
                    'materialization.measures has an unknown measure'
                )
            materialization['measures'] = list(mat_measures)
        if 'target_relation' in materialization:
            t_rel = array(
                materialization.get('target_relation', []),
                'materialization.target_relation', 8,
            )
            if t_rel and not all(
                isinstance(p, str) and p.strip() for p in t_rel
            ):
                raise SemanticModelError(
                    'materialization.target_relation requires identifier parts'
                )
            materialization['target_relation'] = [p.strip() for p in t_rel]
        if 'partition_field' in materialization:
            p_field = materialization.get('partition_field')
            if p_field is not None:
                if isinstance(p_field, Mapping):
                    _validate_field_reference(p_field, source_ids)
                    materialization['partition_field'] = copy.deepcopy(
                        dict(p_field)
                    )
                else:
                    materialization['partition_field'] = identifier(
                        p_field, 'materialization.partition_field'
                    )
            else:
                materialization['partition_field'] = None
        if 'partition_grain' in materialization:
            p_grain = str(
                materialization.get('partition_grain') or 'none'
            ).strip()
            if p_grain not in PARTITION_GRAINS:
                raise SemanticModelError(
                    'materialization.partition_grain must be none, day, '
                    'month or year'
                )
            materialization['partition_grain'] = p_grain
        if 'refresh_policy' in materialization:
            r_policy = str(
                materialization.get('refresh_policy') or 'manual'
            ).strip()[:128]
            if r_policy not in REFRESH_POLICIES:
                raise SemanticModelError(
                    'materialization.refresh_policy is unsupported'
                )
            materialization['refresh_policy'] = r_policy
        if 'rule_group' in materialization:
            rg = materialization.get('rule_group')
            if rg is not None:
                rg_map = mapping(rg, 'materialization.rule_group')
                norm_rg: dict[str, Any] = {}
                if 'name' in rg_map and rg_map['name']:
                    norm_rg['name'] = str(rg_map['name']).strip()[:128]
                if 'mandatory_dimensions' in rg_map:
                    norm_rg['mandatory_dimensions'] = [
                        identifier(
                            d, 'rule_group.mandatory_dimensions'
                        )
                        for d in array(
                            rg_map['mandatory_dimensions'],
                            'rule_group.mandatory_dimensions', 64,
                        )
                    ]
                if 'hierarchy_sets' in rg_map:
                    norm_rg['hierarchy_sets'] = [
                        [
                            identifier(d, 'rule_group.hierarchy_sets.item')
                            for d in array(
                                chain, 'rule_group.hierarchy_sets.chain', 32
                            )
                        ]
                        for chain in array(
                            rg_map['hierarchy_sets'],
                            'rule_group.hierarchy_sets', 32,
                        )
                    ]
                if 'joint_sets' in rg_map:
                    norm_rg['joint_sets'] = [
                        [
                            identifier(d, 'rule_group.joint_sets.item')
                            for d in array(
                                grp, 'rule_group.joint_sets.group', 32
                            )
                        ]
                        for grp in array(
                            rg_map['joint_sets'], 'rule_group.joint_sets', 32
                        )
                    ]
                if (
                    'max_dimension_combinations' in rg_map
                    and rg_map['max_dimension_combinations'] is not None
                ):
                    cap = rg_map['max_dimension_combinations']
                    if (
                        isinstance(cap, bool)
                        or not isinstance(cap, int)
                        or cap < 0
                    ):
                        raise SemanticModelError(
                            'rule_group.max_dimension_combinations must be '
                            'a non-negative integer'
                        )
                    norm_rg['max_dimension_combinations'] = cap
                materialization['rule_group'] = norm_rg
            else:
                materialization['rule_group'] = None
    model['materializations'] = materializations
    security = mapping(model.get('security', {}), 'model.security')
    security['row_filters'] = _validate_filters(
        security.get('row_filters', []), source_ids, parameter_definitions
    )
    tenant = security.get('tenant_filter')
    if tenant is not None:
        tenant = mapping(tenant, 'security.tenant_filter')
        _validate_field_reference(tenant.get('field'), source_ids)
        tenant['principal_claim'] = identifier(
            tenant.get('principal_claim', 'tenant_id'),
            'security.tenant_filter.principal_claim',
        )
        tenant['required'] = bool(tenant.get('required', True))
    security['tenant_filter'] = tenant
    roles = array(security.get('roles', []), 'security.roles', 128)
    _unique(roles, 'security.roles')
    for role in roles:
        role['name'] = required_text(role.get('name'), 'security.role.name')
        role['principal_claim'] = identifier(
            role.get('principal_claim', 'role'),
            'security.role.principal_claim',
        )
        role['filters'] = _validate_filters(
            role.get('filters', []), source_ids, parameter_definitions
        )
    security['roles'] = roles
    model['security'] = security

    visualizations = array(
        model.get('visualizations', []), 'model.visualizations', 256
    )
    visualization_ids = _unique(visualizations, 'model.visualizations')
    for chart in visualizations:
        if not isinstance(chart, Mapping):
            raise SemanticModelError('visualization must be an object')
        chart['name'] = required_text(chart.get('name'), 'visualization.name')
        if chart.get('chart_type', 'table') not in CHART_TYPES:
            raise SemanticModelError('visualization.chart_type is unsupported')
        chart['chart_type'] = chart.get('chart_type', 'table')
        chart['query'] = mapping(chart.get('query', {}), 'visualization.query')
        chart['encodings'] = mapping(
            chart.get('encodings', {}), 'visualization.encodings'
        )
    model['visualizations'] = visualizations

    dashboards = array(model.get('dashboards', []), 'model.dashboards', 64)
    dashboard_ids = _unique(dashboards, 'model.dashboards')
    for dashboard in dashboards:
        dashboard['name'] = required_text(
            dashboard.get('name'), 'dashboard.name'
        )
        tiles = array(dashboard.get('tiles', []), 'dashboard.tiles', 256)
        normalized_tiles = []
        for tile in tiles:
            tile = mapping(tile, 'dashboard.tile')
            if tile.get('visualization_id') not in visualization_ids:
                raise SemanticModelError(
                    'dashboard tile references an unknown visualization'
                )
            tile['layout'] = mapping(
                tile.get('layout', {}), 'dashboard.tile.layout'
            )
            normalized_tiles.append(tile)
        dashboard['tiles'] = normalized_tiles
        dashboard['cross_filtering'] = bool(
            dashboard.get('cross_filtering', True)
        )
    model['dashboards'] = dashboards

    schedules = array(model.get('schedules', []), 'model.schedules', 64)
    schedule_ids = _unique(schedules, 'model.schedules')
    for schedule in schedules:
        schedule['name'] = required_text(
            schedule.get('name'), 'schedule.name'
        )
        schedule['expression'] = required_text(
            schedule.get('expression'), 'schedule.expression', 256
        )
        schedule['timezone'] = required_text(
            schedule.get('timezone', 'UTC'), 'schedule.timezone', 128
        )
        schedule['enabled'] = bool(schedule.get('enabled', False))
        delivery = mapping(
            schedule.get('delivery', {}), 'schedule.delivery'
        )
        unsupported = set(delivery).difference({
            'profile_id', 'format', 'target',
        })
        if unsupported:
            raise SemanticModelError(
                'schedule delivery contains unsupported fields'
            )
        if delivery:
            delivery['profile_id'] = required_text(
                delivery.get('profile_id'),
                'schedule.delivery.profile_id', 128,
            )
            delivery['format'] = required_text(
                delivery.get('format'), 'schedule.delivery.format', 16
            )
            if delivery['format'] not in EXPORT_FORMATS:
                raise SemanticModelError(
                    'schedule delivery export format is unsupported'
                )
            target = mapping(
                delivery.get('target'), 'schedule.delivery.target'
            )
            target_fields = set(target)
            if target_fields == {'recipients'}:
                recipients = array(
                    target['recipients'],
                    'schedule.delivery.target.recipients', 50,
                )
                if not recipients:
                    raise SemanticModelError(
                        'schedule delivery recipients must not be empty'
                    )
                target['recipients'] = [required_text(
                    item, 'schedule.delivery.target.recipient', 320
                ) for item in recipients]
            elif target_fields == {'object_name'}:
                target['object_name'] = required_text(
                    target['object_name'],
                    'schedule.delivery.target.object_name', 255,
                )
            else:
                raise SemanticModelError(
                    'schedule delivery target shape is unsupported'
                )
            delivery['target'] = target
        schedule['delivery'] = delivery
    model['schedules'] = schedules

    reports = array(model.get('reports', []), 'model.reports', 128)
    _unique(reports, 'model.reports')
    for report in reports:
        report['name'] = required_text(report.get('name'), 'report.name')
        dashboard_id = report.get('dashboard_id')
        if dashboard_id is not None and dashboard_id not in dashboard_ids:
            raise SemanticModelError(
                'report references an unknown dashboard'
            )
        schedule_id = report.get('schedule_id')
        if schedule_id is not None and schedule_id not in schedule_ids:
            raise SemanticModelError(
                'report references an unknown schedule'
            )
        formats = array(
            report.get('export_formats', ['json']),
            'report.export_formats', 8,
        )
        if not formats or any(item not in EXPORT_FORMATS for item in formats):
            raise SemanticModelError('report export format is unsupported')
        report['export_formats'] = formats
        report['parameters'] = mapping(
            report.get('parameters', {}), 'report.parameters'
        )
    model['reports'] = reports
    perspective_ids = set()
    if 'perspectives' in model:
        perspectives = array(
            model.get('perspectives', []), 'model.perspectives', 64
        )
        perspective_ids = _unique(perspectives, 'model.perspectives')
        for persp in perspectives:
            persp['name'] = required_text(
                persp.get('name'), 'perspective.name', 256
            )
            persp['description'] = str(persp.get('description') or '')[:2048]
            p_dims = array(
                persp.get('dimensions', []), 'perspective.dimensions', 128
            )
            if any(item not in dimension_ids for item in p_dims):
                raise SemanticModelError(
                    'perspective.dimensions references an unknown dimension'
                )
            persp['dimensions'] = list(p_dims)
            p_measures = array(
                persp.get('measures', []), 'perspective.measures', 256
            )
            if any(item not in measure_ids for item in p_measures):
                raise SemanticModelError(
                    'perspective.measures references an unknown measure'
                )
            persp['measures'] = list(p_measures)
            p_groups = array(
                persp.get('measure_groups', []),
                'perspective.measure_groups', 64,
            )
            if any(item not in measure_group_ids for item in p_groups):
                raise SemanticModelError(
                    'perspective.measure_groups has an unknown measure group'
                )
            persp['measure_groups'] = list(p_groups)
            p_hiers = array(
                persp.get('hierarchies', []), 'perspective.hierarchies', 128
            )
            if any(item not in hierarchy_ids for item in p_hiers):
                raise SemanticModelError(
                    'perspective.hierarchies references an unknown hierarchy'
                )
            persp['hierarchies'] = list(p_hiers)
            if not persp['measures'] and not persp['measure_groups']:
                raise SemanticModelError(
                    'perspective must include at least one measure or group'
                )
            default_measure = persp.get('default_measure')
            if default_measure is not None:
                default_measure = identifier(
                    default_measure, 'perspective.default_measure'
                )
                exposed_measures = set(persp['measures'])
                if model.get('measure_groups'):
                    for grp in model['measure_groups']:
                        if grp['id'] in persp['measure_groups']:
                            exposed_measures.update(grp['measures'])
                if default_measure not in exposed_measures:
                    raise SemanticModelError(
                        'perspective.default_measure must be in perspective'
                    )
                persp['default_measure'] = default_measure
            if 'visible_roles' in persp:
                persp['visible_roles'] = _validate_visible_roles(
                    persp.get('visible_roles', []),
                    'perspective.visible_roles',
                )
        model['perspectives'] = perspectives

    if 'translations' in model:
        translations = array(
            model.get('translations', []), 'model.translations', 64
        )
        valid_targets = {
            'model': {model['name'], 'model'},
            'dimension': set(dimension_ids),
            'attribute': set(attribute_ids),
            'hierarchy': set(hierarchy_ids),
            'level': set(level_ids) - set(attribute_ids),
            'measure': set(measure_ids),
            'measure_group': set(measure_group_ids),
            'perspective': set(perspective_ids),
        }
        seen_locales = set()
        normalized_translations = []
        for raw_tr in translations:
            tr = mapping(raw_tr, 'translation')
            locale = required_text(tr.get('locale'), 'translation.locale', 32)
            if not _LOCALE_RE.fullmatch(locale):
                raise SemanticModelError(
                    'translation.locale must be a valid BCP-47 locale tag'
                )
            locale_key = locale.lower()
            if locale_key in seen_locales:
                raise SemanticModelError(
                    'translation locales must be unique'
                )
            seen_locales.add(locale_key)
            tr_id = identifier(
                tr.get('id') or f"loc_{locale.replace('-', '_')}",
                'translation.id',
            )
            raw_entries = tr.get('entries', [])
            norm_entries = []
            if isinstance(raw_entries, Mapping):
                for composite_key, entry_val in sorted(raw_entries.items()):
                    entry_map = mapping(entry_val, 'translation.entry')
                    if ':' in str(composite_key):
                        t_kind, t_id = str(composite_key).split(':', 1)
                    else:
                        t_kind = entry_map.get('target_kind', 'model')
                        t_id = str(composite_key)
                    norm_entries.append({
                        'target_kind': t_kind,
                        'target_id': t_id,
                        **entry_map,
                    })
            else:
                norm_entries = [
                    mapping(item, 'translation.entry')
                    for item in array(raw_entries, 'translation.entries', 1024)
                ]
            checked_entries = []
            seen_targets = set()
            for entry in norm_entries:
                t_kind = entry.get('target_kind') or entry.get('kind')
                if t_kind not in TRANSLATION_TARGET_KINDS:
                    raise SemanticModelError(
                        'translation.entry.target_kind is unsupported'
                    )
                t_id = required_text(
                    entry.get('target_id'),
                    'translation.entry.target_id', 128,
                )
                if t_kind != 'model' and t_id not in valid_targets[t_kind]:
                    raise SemanticModelError(
                        f'translation references unknown {t_kind}: {t_id}'
                    )
                pair = (t_kind, t_id)
                if pair in seen_targets:
                    raise SemanticModelError(
                        'duplicate translation entry for the same object'
                    )
                seen_targets.add(pair)
                checked_entries.append({
                    'target_kind': t_kind,
                    'target_id': t_id,
                    'caption': str(entry.get('caption') or '')[:256],
                    'description': str(entry.get('description') or '')[:2048],
                    'display_folder': str(
                        entry.get('display_folder') or ''
                    )[:256],
                })
            checked_entries.sort(
                key=lambda item: (item['target_kind'], item['target_id'])
            )
            normalized_translations.append({
                'id': tr_id,
                'locale': locale,
                'caption': str(tr.get('caption') or '')[:256],
                'description': str(tr.get('description') or '')[:2048],
                'entries': checked_entries,
            })
        model['translations'] = normalized_translations

    model['annotations'] = mapping(
        model.get('annotations', {}), 'model.annotations'
    )
    model['_symbols'] = {
        'source_ids': sorted(source_ids),
        'dimension_ids': sorted(dimension_ids),
        'level_ids': sorted(level_ids),
        'hierarchy_ids': sorted(hierarchy_ids),
        'parent_child_ids': sorted(parent_child_ids),
        'measure_ids': sorted(measure_ids),
        'perspective_ids': sorted(perspective_ids),
        'parameter_ids': sorted(parameter_ids),
        'visualization_ids': sorted(visualization_ids),
        'dashboard_ids': sorted(dashboard_ids),
        'schedule_ids': sorted(schedule_ids),
    }
    for chart in model['visualizations']:
        chart['query'] = validate_query(model, chart['query'])
    for report in model['reports']:
        for parameter_id, parameter_value in report['parameters'].items():
            if parameter_id not in parameter_ids:
                raise SemanticModelError(
                    'report contains an unknown parameter'
                )
            parameter = next(
                item for item in model['parameters']
                if item['id'] == parameter_id
            )
            _validate_parameter_value(parameter_value, parameter['type'])
    encoded = json.dumps(
        model, ensure_ascii=False, separators=(',', ':'), default=repr
    ).encode('utf-8')
    if len(encoded) > 1024 * 1024:
        raise SemanticModelError('semantic model exceeds its byte limit')
    return model


def _validate_expression(value, measure_ids, current_id, depth=0):
    if depth > 16:
        raise SemanticModelError('calculated measure expression is too deep')
    value = mapping(value, 'calculated measure expression')
    if set(value) == {'measure'}:
        measure_id = identifier(value['measure'], 'expression.measure')
        if measure_id not in measure_ids or measure_id == current_id:
            raise SemanticModelError(
                'calculated measure references an unavailable measure'
            )
        return
    if set(value) == {'literal'}:
        if isinstance(value['literal'], bool) or not isinstance(
            value['literal'], (int, float)
        ):
            raise SemanticModelError(
                'calculated measure literal must be numeric'
            )
        return
    if set(value) != {'operator', 'left', 'right'} or (
        value['operator'] not in CALCULATION_OPERATORS
    ):
        raise SemanticModelError(
            'calculated measure expression node is unsupported'
        )
    _validate_expression(value['left'], measure_ids, current_id, depth + 1)
    _validate_expression(value['right'], measure_ids, current_id, depth + 1)


def _expression_references(value):
    if value is None or 'literal' in value:
        return set()
    if 'measure' in value:
        return {value['measure']}
    return (
        _expression_references(value['left']) |
        _expression_references(value['right'])
    )


def _validate_parameter_value(value, parameter_type):
    """Enforce declared parameter types without coercing caller input."""
    valid = {
        'string': lambda item: isinstance(item, str),
        'date': lambda item: isinstance(item, str) and bool(item.strip()),
        'datetime': lambda item: isinstance(item, str) and bool(item.strip()),
        'integer': lambda item: isinstance(item, int) and not isinstance(
            item, bool
        ),
        'number': lambda item: (
            isinstance(item, (int, float)) and not isinstance(item, bool)
        ),
        'boolean': lambda item: isinstance(item, bool),
        'array': lambda item: isinstance(item, list),
    }[parameter_type]
    if not valid(value):
        raise SemanticModelError(
            f'parameter value does not match type {parameter_type}'
        )


def _validate_field_reference(value, source_ids):
    value = mapping(value, 'field reference')
    if value.get('source_id') not in source_ids:
        raise SemanticModelError('field reference uses an unknown source')
    field = required_text(value.get('field'), 'field reference.field', 512)
    if '\x00' in field:
        raise SemanticModelError('field reference contains a null character')


def _validate_filters(value, source_ids, parameters=None):
    parameters = parameters or {}
    parameter_ids = set(parameters)
    filters = array(value, 'filters', 128)
    normalized = []
    for raw in filters:
        item = mapping(raw, 'filter')
        _validate_field_reference(item.get('field'), source_ids)
        operator = item.get('operator', 'eq')
        if operator not in FILTER_OPERATORS:
            raise SemanticModelError('filter.operator is unsupported')
        item['operator'] = operator
        parameter_id = item.get('parameter_id')
        if parameter_id is not None:
            if operator in {'is_null', 'is_not_null'}:
                raise SemanticModelError(
                    f'{operator} filter must not use a parameter'
                )
            if parameter_id not in parameter_ids:
                raise SemanticModelError(
                    'filter references an unknown parameter'
                )
            if 'value' in item:
                raise SemanticModelError(
                    'filter cannot contain both value and parameter_id'
                )
            if operator in {'in', 'not_in', 'between'} and parameters[
                    parameter_id]['type'] != 'array':
                raise SemanticModelError(
                    f'{operator} filter parameter must have array type'
                )
        elif operator in {'is_null', 'is_not_null'}:
            if 'value' in item:
                raise SemanticModelError(
                    f'{operator} filter must not contain a value'
                )
        elif 'value' not in item:
            raise SemanticModelError('filter requires a value or parameter')
        elif operator in {'in', 'not_in'} and not isinstance(
                item['value'], list):
            raise SemanticModelError(f'{operator} filter requires an array')
        elif operator == 'between' and (
                not isinstance(item['value'], list) or
                len(item['value']) != 2):
            raise SemanticModelError(
                'between filter requires an array of two values'
            )
        normalized.append(item)
    return normalized


def _temporal_value(value, label, timezone_name):
    value = required_text(value, label, 128)
    try:
        parsed = (
            datetime.fromisoformat(value.replace('Z', '+00:00'))
            if 'T' in value else datetime.combine(
                date.fromisoformat(value), datetime.min.time()
            )
        )
    except ValueError as exc:
        raise SemanticModelError(f'{label} must be an ISO date or datetime') \
            from exc
    if 'T' in value:
        timezone = ZoneInfo(timezone_name)
        parsed = (
            parsed.replace(tzinfo=timezone)
            if parsed.tzinfo is None else parsed.astimezone(timezone)
        )
    return value, parsed, 'T' in value


def _format_temporal(value, has_time):
    if not has_time:
        return value.date().isoformat()
    formatted = value.isoformat()
    return formatted[:-6] + 'Z' if formatted.endswith('+00:00') else formatted


def _shift_months(value, months):
    target = value.month - 1 + months
    year = value.year + target // 12
    month = target % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _period_start(anchor, period, fiscal_month):
    start = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == 'day':
        return start
    if period == 'week':
        return start - timedelta(days=start.weekday())
    if period == 'month':
        return start.replace(day=1)
    if period == 'quarter':
        return start.replace(month=((start.month - 1) // 3) * 3 + 1, day=1)
    if period == 'year':
        return start.replace(month=1, day=1)
    offset = (start.month - fiscal_month) % 12
    if period == 'fiscal_quarter':
        return _shift_months(start.replace(day=1), -(offset % 3))
    fiscal_year = start.year if start.month >= fiscal_month else start.year - 1
    return start.replace(year=fiscal_year, month=fiscal_month, day=1)


def _previous_period_start(current_start, period):
    if period == 'day':
        return current_start - timedelta(days=1)
    if period == 'week':
        return current_start - timedelta(days=7)
    months = {
        'month': -1, 'quarter': -3, 'fiscal_quarter': -3,
        'year': -12, 'fiscal_year': -12,
    }
    return _shift_months(current_start, months[period])


def _validate_time_intelligence(model, value):
    time = mapping(value, 'query.time_intelligence')
    if not time:
        return time
    dimension_id = time.get('dimension_id')
    dimensions = {item['id']: item for item in model['dimensions']}
    dimension = dimensions.get(dimension_id)
    if dimension is None or not dimension.get('time_intelligence'):
        raise SemanticModelError(
            'query time intelligence requires a declared time dimension'
        )
    operation = time.get('operation')
    if operation not in TIME_OPERATIONS:
        raise SemanticModelError(
            'query time-intelligence operation is unsupported'
        )
    value_type = dimension['time_intelligence'].get('value_type', 'string')
    timezone_name = dimension['time_intelligence']['timezone']

    def check_type(has_time):
        if value_type == 'date' and has_time:
            raise SemanticModelError(
                'time-intelligence value must match date dimension type'
            )
        if value_type == 'datetime' and not has_time:
            raise SemanticModelError(
                'time-intelligence value must match datetime dimension type'
            )

    if operation in {'as_of', 'range'}:
        time['start'], start, start_time = _temporal_value(
            time.get('start'), 'query.time_intelligence.start', timezone_name
        )
        check_type(start_time)
        if operation == 'range':
            time['end'], end, end_time = _temporal_value(
                time.get('end'), 'query.time_intelligence.end', timezone_name
            )
            check_type(end_time)
            if start_time != end_time or end < start:
                raise SemanticModelError(
                    'time-intelligence range must use ordered matching types'
                )
        else:
            time.pop('end', None)
        return time
    period = time.get('period')
    if period not in TIME_PERIODS:
        raise SemanticModelError(
            'query time-intelligence period is unsupported'
        )
    if dimension['time_intelligence']['calendar'] != 'gregorian':
        raise SemanticModelError(
            'computed periods require the Gregorian calendar'
        )
    anchor_text, anchor, has_time = _temporal_value(
        time.get('anchor'), 'query.time_intelligence.anchor', timezone_name
    )
    check_type(has_time)
    fiscal_month = dimension['time_intelligence'][
        'fiscal_year_start_month'
    ]
    current_start = _period_start(anchor, period, fiscal_month)
    time['anchor'] = anchor_text
    time['start'] = _format_temporal(current_start, has_time)
    time['end'] = _format_temporal(anchor, has_time)
    if operation == 'period_comparison':
        prior_start = _previous_period_start(current_start, period)
        boundary_step = timedelta(microseconds=1) if has_time else timedelta(
            days=1
        )
        prior_end = min(
            prior_start + (anchor - current_start),
            current_start - boundary_step,
        )
        time['comparison_start'] = _format_temporal(prior_start, has_time)
        time['comparison_end'] = _format_temporal(prior_end, has_time)
    return time


def _validate_windows(value, symbols, selected_measures):
    windows = array(value, 'query.windows', 32)
    window_ids = _unique(windows, 'query.windows')
    admitted_levels = set(symbols['level_ids']) | set(
        symbols['dimension_ids']
    )
    if window_ids & (
        admitted_levels | set(symbols['measure_ids']) |
        {'__semantic_period'}
    ):
        raise SemanticModelError(
            'window output identifiers must not collide with model symbols'
        )
    for window in windows:
        if window.get('measure_id') not in symbols['measure_ids']:
            raise SemanticModelError('window references an unknown measure')
        if window['measure_id'] not in selected_measures:
            raise SemanticModelError(
                'window measure must be selected by the query'
            )
        operation = window.get('operation')
        if operation not in WINDOW_OPERATIONS:
            raise SemanticModelError('window.operation is unsupported')
        partition = array(
            window.get('partition_by', []), 'window.partition_by', 16
        )
        if any(item not in admitted_levels for item in partition):
            raise SemanticModelError('window partition has an unknown level')
        order = mapping(window.get('order_by', {}), 'window.order_by')
        if order.get('level_id') not in admitted_levels:
            raise SemanticModelError('window order has an unknown level')
        direction = order.get('direction', 'asc')
        if direction not in {'asc', 'desc'}:
            raise SemanticModelError('window order direction is unsupported')
        size = window.get('frame_size', 1)
        if isinstance(size, bool) or not isinstance(size, int) or not (
                1 <= size <= 10000):
            raise SemanticModelError('window frame size is outside limits')
        window['partition_by'] = partition
        window['order_by'] = {
            'level_id': order['level_id'], 'direction': direction,
        }
        window['frame_size'] = size
    return windows


def validate_query(model, value):
    query = mapping(value, 'query')
    if '_symbols' not in model:
        model = validate_model(model)
    symbols = model['_symbols']
    axes = mapping(query.get('axes', {}), 'query.axes')
    for axis in ('rows', 'columns', 'pages'):
        if axis not in axes and axis in query:
            axes[axis] = query[axis]
    admitted_levels = set(symbols['level_ids']) | set(symbols['dimension_ids'])
    for axis in ('rows', 'columns', 'pages'):
        items = array(axes.get(axis, []), f'query.axes.{axis}', 32)
        if any(item not in admitted_levels for item in items):
            raise SemanticModelError(f'query.axes.{axis} has an unknown level')
        axes[axis] = items
    selected_measures = array(query.get('measures', []), 'query.measures', 64)
    if not selected_measures:
        raise SemanticModelError('query.measures must not be empty')
    if any(item not in symbols['measure_ids'] for item in selected_measures):
        raise SemanticModelError('query.measures has an unknown measure')
    query['axes'] = axes
    query['measures'] = selected_measures
    perspective_id = query.get('perspective')
    if perspective_id is not None:
        perspective_id = identifier(perspective_id, 'query.perspective')
        perspectives_by_id = {
            item['id']: item for item in model.get('perspectives', [])
        }
        persp = perspectives_by_id.get(perspective_id)
        if persp is None:
            raise SemanticModelError('query.perspective is unknown')
        exposed_measures = set(persp['measures'])
        for grp in model.get('measure_groups', []):
            if grp['id'] in persp.get('measure_groups', []):
                exposed_measures.update(grp['measures'])
        if any(item not in exposed_measures for item in selected_measures):
            raise SemanticModelError(
                'query measure is not exposed by the selected perspective'
            )
        exposed_axes = set(persp['dimensions'])
        allowed_hiers = set(persp.get('hierarchies', []))
        for dim in model['dimensions']:
            if dim['id'] not in persp['dimensions']:
                continue
            for attr in dim.get('attributes', []):
                exposed_axes.add(attr['id'])
            for hier in dim.get('hierarchies', []):
                if allowed_hiers and hier['id'] not in allowed_hiers:
                    continue
                exposed_axes.add(hier['id'])
                for lvl in hier.get('levels', []):
                    exposed_axes.add(lvl['id'])
        for axis in ('rows', 'columns', 'pages'):
            if any(item not in exposed_axes for item in axes[axis]):
                raise SemanticModelError(
                    'query axis item is not exposed by perspective'
                )
        query['perspective'] = perspective_id
    query['filters'] = _validate_filters(
        query.get('filters', []), set(symbols['source_ids']),
        {item['id']: item for item in model['parameters']}
    )
    query['cross_filters'] = _validate_filters(
        query.get('cross_filters', []), set(symbols['source_ids']),
        {item['id']: item for item in model['parameters']}
    )
    parameters = mapping(query.get('parameters', {}), 'query.parameters')
    if set(parameters).difference(symbols['parameter_ids']):
        raise SemanticModelError('query contains an unknown parameter')
    definitions = {item['id']: item for item in model['parameters']}
    for parameter_id, parameter_value in parameters.items():
        definition = definitions[parameter_id]
        _validate_parameter_value(parameter_value, definition['type'])
        if definition['allowed_values'] and parameter_value not in (
                definition['allowed_values']):
            raise SemanticModelError('query parameter value is not allowed')
    required_parameters = {
        item['id'] for item in model['parameters']
        if item['required'] and 'default' not in item
    }
    if required_parameters.difference(parameters):
        raise SemanticModelError('query omits a required parameter')
    query['parameters'] = parameters
    drill = mapping(query.get('drill', {}), 'query.drill')
    mode = drill.get('mode', 'summary')
    if mode not in {'summary', 'down', 'through'}:
        raise SemanticModelError('query drill mode is unsupported')
    target = drill.get('target_level')
    if mode == 'down' and target is None:
        raise SemanticModelError(
            'drill-down requires a target level'
        )
    if target is not None and target not in admitted_levels:
        raise SemanticModelError('query drill target is unknown')
    if target is not None and query.get('perspective') is not None:
        if target not in exposed_axes:
            raise SemanticModelError(
                'query drill target is not exposed by perspective'
            )
    detail_fields = array(
        drill.get('detail_fields', []), 'query.drill.detail_fields', 64
    )
    for reference in detail_fields:
        _validate_field_reference(reference, set(symbols['source_ids']))
    drill['mode'] = mode
    drill['target_level'] = target
    drill['detail_fields'] = detail_fields
    query['drill'] = drill
    query['time_intelligence'] = _validate_time_intelligence(
        model, query.get('time_intelligence', {})
    )
    query['windows'] = _validate_windows(
        query.get('windows', []), symbols, set(selected_measures)
    )
    query['totals'] = bool(query.get('totals', False))
    order_symbols = (
        admitted_levels | set(symbols['measure_ids']) |
        {item['id'] for item in query['windows']}
    )
    requested_order = array(query.get('order_by', []), 'query.order_by', 32)
    query['order_by'] = []
    for entry in requested_order:
        entry = mapping(entry, 'query.order_by entry')
        direction = entry.get('direction', 'asc')
        if entry.get('id') not in order_symbols or direction not in {
                'asc', 'desc'}:
            raise SemanticModelError(
                'query.order_by must name an output column and asc or desc'
            )
        query['order_by'].append({'id': entry['id'], 'direction': direction})
    bind = query.get('bind')
    if bind is not None and bind not in {'qmark', 'format'}:
        raise SemanticModelError('query.bind must be qmark, format or null')
    query['bind'] = bind
    query['limit'] = query.get('limit', 500)
    if isinstance(query['limit'], bool) or not isinstance(query['limit'], int):
        raise SemanticModelError('query.limit must be an integer')
    if not 1 <= query['limit'] <= 10000:
        raise SemanticModelError('query.limit is outside platform limits')
    raw_role = query.get('role')
    if raw_role is not None and str(raw_role).strip():
        active_role = identifier(raw_role, 'query.role')
        query['role'] = active_role
        if query.get('perspective') is not None:
            persp_map = {
                item['id']: item for item in model.get('perspectives', [])
            }
            p_obj = persp_map.get(query['perspective'])
            if (
                p_obj
                and p_obj.get('visible_roles')
                and active_role not in p_obj['visible_roles']
            ):
                raise SemanticModelError(
                    'selected perspective is not visible to role'
                )
        measures_map = {item['id']: item for item in model['measures']}

        def _check_measure_role(mid: str, seen: frozenset[str] = frozenset()):
            if mid in seen:
                return
            m_obj = measures_map.get(mid)
            if not m_obj:
                return
            if (
                m_obj.get('visible_roles')
                and active_role not in m_obj['visible_roles']
            ):
                raise SemanticModelError(
                    f"measure '{mid}' is not visible to role '{active_role}'"
                )
            for dep in _expression_references(m_obj.get('expression')):
                _check_measure_role(dep, seen | frozenset({mid}))

        for mid in selected_measures:
            _check_measure_role(mid)

        owner_dim_by_item: dict[str, dict[str, Any]] = {}
        for dim in model['dimensions']:
            owner_dim_by_item[dim['id']] = dim
            for attr in dim.get('attributes', []):
                owner_dim_by_item[attr['id']] = dim
            for hier in dim.get('hierarchies', []):
                owner_dim_by_item[hier['id']] = dim
                for lvl in hier.get('levels', []):
                    owner_dim_by_item[lvl['id']] = dim

        checked_items = [
            item
            for axis in ('rows', 'columns', 'pages')
            for item in axes[axis]
        ]
        if query['drill'].get('target_level'):
            checked_items.append(query['drill']['target_level'])
        for item_id in checked_items:
            d_obj = owner_dim_by_item.get(item_id)
            if (
                d_obj
                and d_obj.get('visible_roles')
                and active_role not in d_obj['visible_roles']
            ):
                raise SemanticModelError(
                    f"dimension '{d_obj['id']}' is not visible to role "
                    f"'{active_role}'"
                )
    return query


def filter_model_for_role(model_value, role: str | None) -> dict[str, Any]:
    """Return a public copy of ``model_value`` filtered for ``role``."""
    validated = public_model(validate_model(model_value))
    if role is None or not str(role).strip():
        return validated
    active_role = identifier(role, 'role')
    filtered = copy.deepcopy(validated)
    visible_dims = [
        d for d in filtered.get('dimensions', [])
        if not d.get('visible_roles') or active_role in d['visible_roles']
    ]
    visible_dim_ids = {d['id'] for d in visible_dims}
    visible_hier_ids = {
        h['id']
        for d in visible_dims
        for h in d.get('hierarchies', [])
    }
    filtered['dimensions'] = visible_dims

    raw_measures = {m['id']: m for m in filtered.get('measures', [])}

    def _measure_visible(mid: str, stack: frozenset[str] = frozenset()) -> bool:
        if mid in stack or mid not in raw_measures:
            return False
        m_obj = raw_measures[mid]
        if (
            m_obj.get('visible_roles')
            and active_role not in m_obj['visible_roles']
        ):
            return False
        return all(
            _measure_visible(dep, stack | frozenset({mid}))
            for dep in _expression_references(m_obj.get('expression'))
        )

    visible_measures = [
        m for m in filtered.get('measures', [])
        if _measure_visible(m['id'])
    ]
    visible_measure_ids = {m['id'] for m in visible_measures}
    filtered['measures'] = visible_measures

    if 'measure_groups' in filtered:
        for grp in filtered['measure_groups']:
            grp['measures'] = [
                mid for mid in grp.get('measures', [])
                if mid in visible_measure_ids
            ]
            grp['dimension_usage'] = [
                u for u in grp.get('dimension_usage', [])
                if u.get('dimension_id') in visible_dim_ids
            ]

    if 'perspectives' in filtered:
        kept_perspectives = []
        for persp in filtered['perspectives']:
            if (
                persp.get('visible_roles')
                and active_role not in persp['visible_roles']
            ):
                continue
            persp['dimensions'] = [
                did for did in persp.get('dimensions', [])
                if did in visible_dim_ids
            ]
            persp['measures'] = [
                mid for mid in persp.get('measures', [])
                if mid in visible_measure_ids
            ]
            persp['hierarchies'] = [
                hid for hid in persp.get('hierarchies', [])
                if hid in visible_hier_ids
            ]
            if (
                persp.get('default_measure')
                and persp['default_measure'] not in visible_measure_ids
            ):
                persp.pop('default_measure', None)
            if persp['measures'] or persp.get('measure_groups'):
                kept_perspectives.append(persp)
        filtered['perspectives'] = kept_perspectives
    return filtered


def public_model(model):
    value = copy.deepcopy(model)
    value.pop('_symbols', None)
    return value


def localize_model(model_value, locale: str):
    """Return a public copy of ``model_value`` overlaid with ``locale``."""
    validated = public_model(validate_model(model_value))
    requested = str(locale or '').strip().lower()
    if not requested:
        return validated
    translations = validated.get('translations', [])
    if not translations:
        return validated

    matched = next(
        (t for t in translations if t['locale'].lower() == requested),
        None,
    )
    if matched is None and '-' in requested:
        lang_prefix = requested.split('-', 1)[0]
        matched = next(
            (
                t for t in translations
                if t['locale'].lower() == lang_prefix
                or t['locale'].lower().startswith(lang_prefix + '-')
            ),
            None,
        )
    if matched is None:
        return validated

    localized = copy.deepcopy(validated)
    if matched.get('caption'):
        localized['name'] = matched['caption']
    if matched.get('description'):
        localized['description'] = matched['description']

    entry_map = {
        (e['target_kind'], e['target_id']): e
        for e in matched.get('entries', [])
    }
    model_entry = entry_map.get(('model', 'model')) or entry_map.get(
        ('model', validated['name'])
    )
    if model_entry:
        if model_entry.get('caption'):
            localized['name'] = model_entry['caption']
        if model_entry.get('description'):
            localized['description'] = model_entry['description']

    def _apply(obj, kind):
        hit = entry_map.get((kind, obj['id']))
        if not hit:
            return
        if hit.get('caption'):
            obj['name'] = hit['caption']
        if hit.get('description'):
            obj['description'] = hit['description']
        if hit.get('display_folder'):
            obj['display_folder'] = hit['display_folder']

    for dim in localized.get('dimensions', []):
        _apply(dim, 'dimension')
        for attr in dim.get('attributes', []):
            _apply(attr, 'attribute')
        for hier in dim.get('hierarchies', []):
            _apply(hier, 'hierarchy')
            for lvl in hier.get('levels', []):
                _apply(lvl, 'level')
    for meas in localized.get('measures', []):
        _apply(meas, 'measure')
    for grp in localized.get('measure_groups', []):
        _apply(grp, 'measure_group')
    for persp in localized.get('perspectives', []):
        _apply(persp, 'perspective')
    return localized

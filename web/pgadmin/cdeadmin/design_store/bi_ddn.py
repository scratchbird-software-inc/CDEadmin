##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""BI Questions & Dashboards Store <-> DDN bridge, SBsql model & importers.

Implements the 2026-11-08 and 2026-11-10 owner decisions (E1-E10):
- E1: Render BI charts and composed dashboards through the shared DDN
  libraries and viewer (``chart.*@1``, ``timeline.basic@1``,
  ``table.records@1``, ``panels.composed@1`` and ``bi.analytics@1``).
- E2: Unified SBsql-shaped structured query model shared by BI questions and
  the visual SQL builder, with multi-table joins, fan-out warnings,
  ``sql_to_question`` fidelity reporting and bound-parameter SQL generation.
- E3: Both ``question`` and ``dashboard`` designs live in ``designs.db`` and
  Git; dashboards reference questions by design ID; users, grants, recipients
  and secrets never enter DDN text; saved filter values are flagged for review.
- E4: Accepting a question or dashboard version makes it active without
  switching on subscriptions/alerts, embeds or dashboard-server publication.
- E5: Default card click cross-filters (per-card override), auto-apply filters,
  personal filter state unless author-pinned, drill-through carries context.
- E6: No BI write-back or action buttons in the first release.
- E7: Imported monitoring ``metric_panel`` cards hold static snapshots in BI.
- E8: Optional BYOK AI drafting searches existing questions first and produces
  only an ordinary draft or diff; agents never accept, merge or publish.
- E9: Display-only remote dashboard server mode under an explicit publishing
  identity with narrowing-only HMAC device tokens.
- E10: Clean-room Superset YAML ZIP and Metabase bundle importers into Draft
  DDN with explicit loss reports.
"""

from __future__ import annotations

import base64
import copy
from datetime import datetime, timezone
import hashlib
import hmac
import io
import json
import re
import tarfile
from typing import Any, Callable, Mapping
import zipfile

from pgadmin.cdeadmin.bi.convert import sql_to_question
from pgadmin.cdeadmin.sdk import sql_builder as sdk_sql_builder
from pgadmin.cdeadmin.semantic_models.models import (
    CHART_TYPES,
    PARAMETER_TYPES,
)

from .ddn_elements import (
    DEFAULT_DIALECT,
    _extract_x_record,
    _parse_blocks,
)
from .identifiers import is_uuid7, uuid7
from .service import (
    DesignStore,
    DesignStoreConflict,
    DesignStoreError,
    DesignStoreForbidden,
    DesignStoreNotFound,
)
from .shared_ddn import StoreDDNProcess

try:
    import yaml as _yaml
except Exception:  # pragma: no cover
    _yaml = None

BI_QUESTION_MODULE = 'scratchrobin.bi.question@1'
BI_DASHBOARD_MODULE = 'scratchrobin.bi.dashboard@1'
BI_ANALYTICS_PROFILE = 'bi.analytics@1'
COMPOSED_PANELS_PROFILE = 'panels.composed@1'

# Owner decision E1: every supported BI chart type maps to a shared DDN profile
# and optional chart mark.
CHART_PROFILE_MAP: dict[str, tuple[str, str | None]] = {
    'table': ('table.records@1', None),
    'pivot': ('table.records@1', None),
    'bar': ('chart.basic@1', 'bar'),
    'line': ('chart.basic@1', 'line'),
    'area': ('chart.basic@1', 'area'),
    'scatter': ('chart.basic@1', 'point'),
    'pie': ('chart.basic@1', 'pie'),
    'metric': ('chart.gauge@1', 'gauge'),
    'histogram': ('chart.histogram@1', 'histogram'),
    'timeline': ('timeline.basic@1', None),
    'graph': ('chart.force@1', 'force'),
    'vector-neighbors': ('chart.dotplot@1', 'dotplot'),
}

CLICK_BEHAVIORS = frozenset({'inherit', 'cross_filter', 'highlight', 'none'})
VERIFICATION_TIERS = frozenset({'draft', 'verified', 'endorsed'})
JOIN_CARDINALITIES = frozenset({
    'many_to_one',
    'one_to_one',
    'one_to_many',
    'many_to_many',
    'undeclared',
})
OUTWARD_EFFECT_KINDS = frozenset({
    'subscription',
    'embed',
    'dashboard_server',
})

# Owner decision E3: sensitive principals, grants, recipients and credentials
# must never be written into DDN text or Git.
FORBIDDEN_DDN_KEYS = frozenset({
    'users',
    'grants',
    'permissions',
    'recipients',
    'webhooks',
    'secrets',
    'secret',
    'api_key',
    'password',
    'token',
    'connection_string',
    'sqlalchemy_uri',
    'dsn',
})

# Owner decision E6: no BI write-back in the first release.
FORBIDDEN_WRITEBACK_KEYS = frozenset({
    'write_back',
    'writeback',
    'action_buttons',
    'mutation_sql',
})

_NON_SELECT_RE = re.compile(
    r'^\s*(insert|update|delete|merge|drop|alter|create|truncate|grant|'
    r'revoke|call|exec|execute)\b',
    re.IGNORECASE,
)

_JINJA_PARAM_RE = re.compile(
    r"\{\{\s*(?:url_param|filter_values)\(\s*"
    r"['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]"
    r"(?:\s*,\s*['\"]([^'\"]*)['\"])?\s*\)\s*\}\}"
)
_JINJA_BLOCK_RE = re.compile(r'\{%.*?%\}|\{\{.*?\}\}', re.DOTALL)
_MB_TAG_RE = re.compile(r'\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}')

_SUPERSET_VIZ_MAP: dict[str, str] = {
    'table': 'table',
    'pivot_table_v2': 'pivot',
    'pivot_table': 'pivot',
    'echarts_timeseries_bar': 'bar',
    'dist_bar': 'bar',
    'bar': 'bar',
    'echarts_timeseries_line': 'line',
    'line': 'line',
    'echarts_area': 'area',
    'area': 'area',
    'scatter': 'scatter',
    'bubble': 'scatter',
    'pie': 'pie',
    'big_number_total': 'metric',
    'big_number': 'metric',
    'gauge_chart': 'metric',
    'histogram': 'histogram',
    'gantt': 'timeline',
    'graph_chart': 'graph',
}

_METABASE_DISPLAY_MAP: dict[str, str] = {
    'table': 'table',
    'pivot': 'pivot',
    'bar': 'bar',
    'row': 'bar',
    'line': 'line',
    'area': 'area',
    'scatter': 'scatter',
    'pie': 'pie',
    'scalar': 'metric',
    'gauge': 'metric',
    'progress': 'metric',
}

_OPERATOR_SQL: dict[str, str] = {
    'eq': '=',
    'ne': '<>',
    'lt': '<',
    'lte': '<=',
    'gt': '>',
    'gte': '>=',
    'like': 'LIKE',
    'not_like': 'NOT LIKE',
    '=': '=',
    '<>': '<>',
    '<': '<',
    '<=': '<=',
    '>': '>',
    '>=': '>=',
    'LIKE': 'LIKE',
    'NOT LIKE': 'NOT LIKE',
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _q(value: Any) -> str:
    text = str(value if value is not None else '')
    text = text.replace('\r\n', ' ').replace('\n', ' ').replace('\x00', '')
    return '"' + text.replace('"', '""') + '"'


def _json_str(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _alloc_id(element_ids: dict[str, str], logical_key: str) -> str:
    existing = element_ids.get(logical_key)
    if existing and is_uuid7(existing):
        return existing
    fresh = uuid7()
    element_ids[logical_key] = fresh
    return fresh


def _safe_ident(raw: Any, fallback: str = 'item') -> str:
    cleaned = re.sub(r'[^A-Za-z0-9_]+', '_', str(raw or '').strip()).strip('_')
    if not cleaned:
        return fallback
    if cleaned[0].isdigit():
        return f'{fallback}_{cleaned}'
    return cleaned[:96]


def _quote_sql_ident(name: str, dialect: str) -> str:
    text = str(name or '').strip()
    if not text or '\x00' in text:
        raise DesignStoreError('SQL identifier must be non-empty')
    if dialect in ('mysql', 'mariadb'):
        return '`' + text.replace('`', '``') + '`'
    return '"' + text.replace('"', '""') + '"'


def _all_builder_options_enabled() -> dict[str, dict[str, Any]]:
    return {
        opt: {'label': label, 'available': True, 'reason': ''}
        for opt, label in sdk_sql_builder.OPTIONS
    }


def _ensure_no_writeback(payload: Any) -> None:
    """Enforce E6: reject write-back definitions or mutation SQL."""
    if isinstance(payload, Mapping):
        for key, val in payload.items():
            key_s = str(key).lower()
            if key_s in FORBIDDEN_WRITEBACK_KEYS and val:
                raise DesignStoreError(
                    'BI write-back and action buttons are not supported in '
                    'this release'
                )
            _ensure_no_writeback(val)
    elif isinstance(payload, list):
        for item in payload:
            _ensure_no_writeback(item)


def _ensure_no_sensitive_fields(payload: Any, path: str = 'root') -> None:
    """Enforce E3: reject users, grants, recipients and secrets in DDN."""
    if isinstance(payload, Mapping):
        for key, val in payload.items():
            key_s = str(key).lower()
            if key_s in FORBIDDEN_DDN_KEYS and val not in (None, '', [], {}):
                raise DesignStoreError(
                    f'Field {path}.{key} cannot be stored in BI DDN text '
                    f'(exclude users, grants, recipients and secrets)'
                )
            _ensure_no_sensitive_fields(val, f'{path}.{key}')
    elif isinstance(payload, list):
        for idx, item in enumerate(payload):
            _ensure_no_sensitive_fields(item, f'{path}[{idx}]')


def _strip_sensitive_fields(payload: Any) -> tuple[Any, list[str]]:
    """Strip sensitive fields during external imports and report removals."""
    removed: list[str] = []

    def _walk(node: Any, path: str) -> Any:
        if isinstance(node, Mapping):
            out: dict[str, Any] = {}
            for k, v in node.items():
                ks = str(k).lower()
                if ks in FORBIDDEN_DDN_KEYS:
                    if v not in (None, '', [], {}):
                        removed.append(f'{path}.{k}')
                    continue
                out[str(k)] = _walk(v, f'{path}.{k}')
            return out
        if isinstance(node, list):
            return [_walk(item, f'{path}[{i}]') for i, item in enumerate(node)]
        return copy.deepcopy(node)

    return _walk(payload, 'import'), removed


def collect_saved_filter_value_flags(
    payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Enforce E3: flag saved parameter/filter literal defaults for review."""
    flags: list[dict[str, Any]] = []
    for param in payload.get('parameters') or []:
        if isinstance(param, Mapping) and param.get('default') not in (
            None, '', [],
        ):
            flags.append({
                'scope': 'parameter',
                'id': str(param.get('id') or ''),
                'value_preview': str(param.get('default'))[:64],
                'reason': (
                    'Saved parameter default value will appear in DDN/Git; '
                    'confirm it contains no sensitive data.'
                ),
            })
    query = payload.get('query')
    if isinstance(query, Mapping):
        sbsql = query.get('sbsql') or {}
        for idx, flt in enumerate(sbsql.get('filters') or []):
            if (
                isinstance(flt, Mapping)
                and not flt.get('parameter')
                and flt.get('value') not in (None, '', [])
            ):
                flags.append({
                    'scope': 'query_filter',
                    'id': f'filter_{idx}',
                    'value_preview': str(flt.get('value'))[:64],
                    'reason': (
                        'Saved literal filter value in query; consider a '
                        'parameter or confirm before Git export.'
                    ),
                })
    for flt in payload.get('filters') or []:
        if isinstance(flt, Mapping) and flt.get('default') not in (
            None, '', [],
        ):
            flags.append({
                'scope': (
                    'pinned_dashboard_filter'
                    if flt.get('pinned_by_author')
                    else 'dashboard_filter'
                ),
                'id': str(flt.get('id') or ''),
                'value_preview': str(flt.get('default'))[:64],
                'reason': (
                    'Saved dashboard filter default will appear in DDN/Git; '
                    'confirm it contains no sensitive data.'
                ),
            })
    return flags


# ---------------------------------------------------------------------------
# Unified SBsql-shaped Query Model & Visual SQL Builder Bridge (E2)
# ---------------------------------------------------------------------------


def _col_parts(raw: Any) -> list[str]:
    if isinstance(raw, list):
        parts = [str(p).strip() for p in raw if str(p).strip()]
        if not parts or len(parts) > 2:
            raise DesignStoreError('Column reference needs 1 or 2 name parts')
        return parts
    if isinstance(raw, str) and raw.strip():
        parts = [p.strip() for p in raw.strip().split('.') if p.strip()]
        if 1 <= len(parts) <= 2:
            return parts
    raise DesignStoreError(f'Invalid column reference: {raw!r}')


def _rel_parts(raw: Any) -> list[str]:
    if isinstance(raw, list):
        parts = [str(p).strip() for p in raw if str(p).strip()]
        if 1 <= len(parts) <= 4:
            return parts
    if isinstance(raw, str) and raw.strip():
        parts = [p.strip() for p in raw.strip().split('.') if p.strip()]
        if 1 <= len(parts) <= 4:
            return parts
    raise DesignStoreError(f'Invalid relation reference: {raw!r}')


def normalize_sbsql_query(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize the unified SBsql-shaped structured query."""
    if not isinstance(raw, Mapping):
        raise DesignStoreError('SBsql query must be an object')
    from_raw = raw.get('from')
    if isinstance(from_raw, Mapping):
        base_rel = _rel_parts(from_raw.get('relation'))
        base_alias = (
            str(from_raw['alias']).strip()
            if from_raw.get('alias')
            else base_rel[-1]
        )
    else:
        base_rel = _rel_parts(raw.get('relation') or ['main', 'items'])
        base_alias = str(raw.get('alias') or base_rel[-1]).strip()

    joins: list[dict[str, Any]] = []
    for idx, jraw in enumerate(raw.get('joins') or []):
        if not isinstance(jraw, Mapping):
            raise DesignStoreError('Each join must be an object')
        jtype = str(jraw.get('type') or 'inner').lower()
        if jtype not in sdk_sql_builder.JOINS:
            raise DesignStoreError(f'Unsupported join type: {jtype!r}')
        jrel = _rel_parts(jraw.get('relation') or jraw.get('source'))
        jalias = str(jraw.get('alias') or f'{jrel[-1]}_{idx + 1}').strip()
        cardinality = str(jraw.get('cardinality') or 'undeclared').lower()
        if cardinality not in JOIN_CARDINALITIES:
            raise DesignStoreError(
                f'Unsupported join cardinality: {cardinality!r}'
            )
        on_clauses: list[dict[str, Any]] = []
        for cond in jraw.get('on') or []:
            if not isinstance(cond, Mapping):
                raise DesignStoreError('Join ON clause must be an object')
            op = str(cond.get('op') or '=')
            if op not in _OPERATOR_SQL:
                raise DesignStoreError(f'Unsupported join operator: {op!r}')
            on_clauses.append({
                'left': _col_parts(cond.get('left')),
                'op': _OPERATOR_SQL[op],
                'right': _col_parts(cond.get('right')),
            })
        using_cols = [
            str(c).strip() for c in (jraw.get('using') or [])
            if str(c).strip()
        ]
        if jtype not in ('cross', 'natural') and not on_clauses and not (
            using_cols
        ):
            raise DesignStoreError(
                f'Join to {".".join(jrel)} requires ON keys or USING columns'
            )
        joins.append({
            'type': jtype,
            'relation': jrel,
            'alias': jalias,
            'on': on_clauses,
            'using': using_cols,
            'cardinality': cardinality,
        })

    columns: list[dict[str, Any]] = []
    for craw in raw.get('columns') or []:
        if isinstance(craw, str):
            parts = _col_parts(craw)
            columns.append({'column': parts, 'alias': parts[-1]})
        elif isinstance(craw, Mapping):
            parts = _col_parts(craw.get('column'))
            alias = str(craw.get('alias') or parts[-1]).strip()
            columns.append({'column': parts, 'alias': alias})
        else:
            raise DesignStoreError('Invalid SBsql column entry')

    measures: list[dict[str, Any]] = []
    for mraw in raw.get('measures') or []:
        if not isinstance(mraw, Mapping):
            raise DesignStoreError('Each measure must be an object')
        fn = str(mraw.get('function') or 'count').lower()
        if fn not in ('sum', 'count', 'count_distinct', 'min', 'max', 'avg'):
            raise DesignStoreError(f'Unsupported measure function: {fn!r}')
        col_val = mraw.get('column')
        col = (
            None
            if col_val in (None, '', '*')
            else _col_parts(col_val)
        )
        if col is None and fn != 'count':
            raise DesignStoreError(f'{fn.upper()} requires a target column')
        default_alias = (
            f'{fn}_{col[-1]}' if col is not None else 'count_rows'
        )
        measures.append({
            'function': fn,
            'column': col,
            'alias': str(mraw.get('alias') or default_alias).strip(),
        })

    if not columns and not measures:
        raise DesignStoreError(
            'SBsql query requires at least one column or measure'
        )

    filters: list[dict[str, Any]] = []
    for fraw in raw.get('filters') or []:
        if not isinstance(fraw, Mapping):
            raise DesignStoreError('Each filter must be an object')
        col = _col_parts(fraw.get('column') or fraw.get('field'))
        op = str(fraw.get('operator') or 'eq').lower()
        allowed_ops = (
            set(_OPERATOR_SQL)
            | {'in', 'not_in', 'between', 'is_null', 'is_not_null'}
        )
        if op not in allowed_ops:
            raise DesignStoreError(f'Unsupported filter operator: {op!r}')
        entry: dict[str, Any] = {'column': col, 'operator': op}
        if fraw.get('parameter'):
            entry['parameter'] = _safe_ident(fraw['parameter'], 'param')
        elif op not in ('is_null', 'is_not_null'):
            entry['value'] = copy.deepcopy(fraw.get('value'))
        filters.append(entry)

    group_raw = raw.get('group_by')
    if isinstance(group_raw, Mapping):
        gkind = str(group_raw.get('kind') or 'columns').lower()
        if gkind not in ('columns', 'rollup', 'cube', 'all'):
            raise DesignStoreError(f'Unsupported group_by kind: {gkind!r}')
        gcols = [
            _col_parts(c)
            for c in (group_raw.get('columns') or [])
        ]
    elif isinstance(group_raw, list) and group_raw:
        gkind = 'columns'
        gcols = [_col_parts(c) for c in group_raw]
    elif measures and columns:
        gkind = 'columns'
        gcols = [list(c['column']) for c in columns]
    else:
        gkind = 'columns'
        gcols = []

    order_by: list[dict[str, Any]] = []
    for oraw in raw.get('order_by') or []:
        if not isinstance(oraw, Mapping):
            raise DesignStoreError('Each order_by item must be an object')
        direction = str(oraw.get('direction') or 'asc').lower()
        if direction not in ('asc', 'desc'):
            raise DesignStoreError('order_by direction must be asc or desc')
        target = oraw.get('expr') or oraw.get('field') or oraw.get('column')
        if isinstance(target, list):
            expr: Any = _col_parts(target)
        else:
            expr = str(target or '').strip()
            if not expr:
                raise DesignStoreError('order_by requires expr or column')
        order_by.append({'expr': expr, 'direction': direction})

    limit_val = raw.get('limit', 1000)
    if limit_val is not None:
        if (
            isinstance(limit_val, bool)
            or not isinstance(limit_val, int)
            or not (1 <= limit_val <= 100000)
        ):
            raise DesignStoreError('SBsql limit must be 1..100000')

    return {
        'dialect': 'sbsql@1',
        'distinct': bool(raw.get('distinct', False)),
        'from': {'relation': base_rel, 'alias': base_alias},
        'joins': joins,
        'columns': columns,
        'measures': measures,
        'filters': filters,
        'group_by': {'kind': gkind, 'columns': gcols},
        'order_by': order_by,
        'limit': limit_val,
    }


def analyze_sbsql_fanout(
    sbsql_query: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Detect potential aggregate fan-out risks across joins (E2)."""
    normalized = normalize_sbsql_query(sbsql_query)
    joins = normalized['joins']
    measures = normalized['measures']
    if not joins or not measures:
        return []
    fanout_sensitive = [
        m for m in measures
        if m['function'] in ('sum', 'avg', 'count')
    ]
    if not fanout_sensitive:
        return []
    m_names = ', '.join(m['alias'] for m in fanout_sensitive)
    warnings: list[dict[str, Any]] = []
    for join in joins:
        jrel = '.'.join(join['relation'])
        card = join.get('cardinality', 'undeclared')
        if join['type'] == 'cross':
            warnings.append({
                'code': 'cross_join_fanout',
                'severity': 'warning',
                'relation': jrel,
                'detail': (
                    f'CROSS JOIN to {jrel} multiplies rows before '
                    f'aggregating {m_names}.'
                ),
            })
        elif card in ('one_to_many', 'many_to_many'):
            warnings.append({
                'code': 'one_to_many_fanout',
                'severity': 'warning',
                'relation': jrel,
                'detail': (
                    f'Join to {jrel} has {card} cardinality and may '
                    f'duplicate rows in {m_names}.'
                ),
            })
        elif card == 'undeclared':
            warnings.append({
                'code': 'undeclared_join_cardinality',
                'severity': 'info',
                'relation': jrel,
                'detail': (
                    f'Join to {jrel} has undeclared cardinality; verify the '
                    f'join key is unique on the joined side to prevent '
                    f'metric fan-out.'
                ),
            })
    return warnings


def sbsql_to_sql_builder_model(
    sbsql_query: Mapping[str, Any],
) -> dict[str, Any]:
    """Project unified SBsql onto ``cdeadmin/sdk/sql_builder.py``."""
    q = normalize_sbsql_query(sbsql_query)
    select_cols: list[dict[str, Any]] = []
    for col in q['columns']:
        entry: dict[str, Any] = {'expr': {'column': list(col['column'])}}
        if col.get('alias'):
            entry['alias'] = col['alias']
        select_cols.append(entry)
    for meas in q['measures']:
        fn = 'count' if meas['function'] == 'count_distinct' else (
            meas['function']
        )
        distinct = meas['function'] == 'count_distinct'
        arg: Any = (
            '*'
            if meas['column'] is None
            else {'column': list(meas['column'])}
        )
        select_cols.append({
            'expr': {
                'aggregate': {
                    'function': fn,
                    'distinct': distinct,
                    'argument': arg,
                },
            },
            'alias': meas['alias'],
        })

    builder_joins: list[dict[str, Any]] = []
    for join in q['joins']:
        bjoin: dict[str, Any] = {
            'type': join['type'],
            'source': {'relation': list(join['relation'])},
            'alias': join['alias'],
        }
        if join.get('using'):
            bjoin['using'] = list(join['using'])
        elif join.get('on'):
            comparisons = [
                {
                    'compare': {
                        'left': {'column': list(c['left'])},
                        'op': c['op'],
                        'right': {'column': list(c['right'])},
                    }
                }
                for c in join['on']
            ]
            bjoin['on'] = (
                comparisons[0]
                if len(comparisons) == 1
                else {'all': comparisons}
            )
        builder_joins.append(bjoin)

    where_terms: list[dict[str, Any]] = []
    for flt in q['filters']:
        col_expr = {'column': list(flt['column'])}
        op = flt['operator']
        if op in ('is_null', 'is_not_null'):
            where_terms.append({op: col_expr})
        elif flt.get('parameter'):
            where_terms.append({
                'compare': {
                    'left': col_expr,
                    'op': _OPERATOR_SQL.get(op, '='),
                    'right': {'value': f":param:{flt['parameter']}"},
                }
            })
        elif op == 'in' and isinstance(flt.get('value'), list):
            where_terms.append({
                'in': {'expr': col_expr, 'values': flt['value']},
            })
        elif op == 'between' and (
            isinstance(flt.get('value'), list) and len(flt['value']) == 2
        ):
            where_terms.extend([
                {
                    'compare': {
                        'left': col_expr,
                        'op': '>=',
                        'right': {'value': flt['value'][0]},
                    }
                },
                {
                    'compare': {
                        'left': col_expr,
                        'op': '<=',
                        'right': {'value': flt['value'][1]},
                    }
                },
            ])
        else:
            where_terms.append({
                'compare': {
                    'left': col_expr,
                    'op': _OPERATOR_SQL.get(op, '='),
                    'right': {'value': flt.get('value')},
                }
            })

    select_obj: dict[str, Any] = {
        'distinct': q['distinct'],
        'columns': select_cols,
        'from': {
            'source': {'relation': list(q['from']['relation'])},
            'alias': q['from']['alias'],
        },
        'joins': builder_joins,
    }
    if where_terms:
        select_obj['where'] = (
            where_terms[0]
            if len(where_terms) == 1
            else {'all': where_terms}
        )
    if q['group_by']['columns'] or q['group_by']['kind'] == 'all':
        gb_kind = q['group_by']['kind']
        if gb_kind == 'all':
            select_obj['group_by'] = {'kind': 'all'}
        else:
            select_obj['group_by'] = {
                'kind': gb_kind,
                'items': [
                    {'column': list(c)} for c in q['group_by']['columns']
                ],
            }

    alias_lookup: dict[str, list[str]] = {
        c['alias']: list(c['column']) for c in q['columns']
    }
    order_items: list[dict[str, Any]] = []
    for ord_item in q['order_by']:
        expr_val = ord_item['expr']
        if isinstance(expr_val, list):
            col_ref = list(expr_val)
        elif expr_val in alias_lookup:
            col_ref = alias_lookup[expr_val]
        else:
            col_ref = [str(expr_val)]
        order_items.append({
            'expr': {'column': col_ref},
            'direction': ord_item['direction'],
        })

    compound: dict[str, Any] = {'selects': [select_obj]}
    if order_items:
        compound['order_by'] = order_items
    if q['limit'] is not None:
        compound['limit'] = q['limit']
    return {'query': compound}


def sql_builder_model_to_sbsql(
    builder_model: Mapping[str, Any],
) -> dict[str, Any]:
    """Convert a ``sdk.sql_builder`` statement model into unified SBsql."""
    query = (builder_model or {}).get('query') or {}
    selects = query.get('selects') or []
    if len(selects) != 1 or builder_model.get('with'):
        raise DesignStoreError(
            'Compound UNION/CTE SQL builder models map as SQL questions; '
            'single-SELECT models map directly onto structured SBsql'
        )
    sel = selects[0]
    from_spec = sel.get('from') or {}
    src = (from_spec.get('source') or {}).get('relation')
    if not src:
        raise DesignStoreError('SQL builder SELECT requires a base relation')
    columns: list[dict[str, Any]] = []
    measures: list[dict[str, Any]] = []
    for item in sel.get('columns') or []:
        expr = item.get('expr') or {}
        if 'column' in expr:
            cparts = list(expr['column'])
            columns.append({
                'column': cparts,
                'alias': item.get('alias') or cparts[-1],
            })
        elif 'aggregate' in expr:
            agg = expr['aggregate']
            fn = agg['function']
            if fn == 'count' and agg.get('distinct'):
                fn = 'count_distinct'
            arg = agg.get('argument')
            col = None if arg == '*' else list(arg.get('column') or [])
            measures.append({
                'function': fn,
                'column': col,
                'alias': item.get('alias') or f'{fn}_val',
            })

    joins: list[dict[str, Any]] = []
    for jitem in sel.get('joins') or []:
        jrel = (jitem.get('source') or {}).get('relation')
        on_list: list[dict[str, Any]] = []
        raw_on = jitem.get('on')
        conds = (
            raw_on['all']
            if isinstance(raw_on, Mapping) and 'all' in raw_on
            else ([raw_on] if isinstance(raw_on, Mapping) else [])
        )
        for cond in conds:
            cmp_body = (
                cond.get('compare') if isinstance(cond, Mapping) else None
            )
            if cmp_body:
                on_list.append({
                    'left': list(cmp_body['left']['column']),
                    'op': cmp_body['op'],
                    'right': list(cmp_body['right']['column']),
                })
        joins.append({
            'type': jitem.get('type', 'inner'),
            'relation': list(jrel),
            'alias': jitem.get('alias') or jrel[-1],
            'on': on_list,
            'using': list(jitem.get('using') or []),
            'cardinality': 'undeclared',
        })

    filters: list[dict[str, Any]] = []
    raw_where = sel.get('where')
    w_items = (
        raw_where['all']
        if isinstance(raw_where, Mapping) and 'all' in raw_where
        else ([raw_where] if isinstance(raw_where, Mapping) else [])
    )
    for w_item in w_items:
        if 'is_null' in w_item:
            filters.append({
                'column': list(w_item['is_null']['column']),
                'operator': 'is_null',
            })
        elif 'is_not_null' in w_item:
            filters.append({
                'column': list(w_item['is_not_null']['column']),
                'operator': 'is_not_null',
            })
        elif 'in' in w_item:
            filters.append({
                'column': list(w_item['in']['expr']['column']),
                'operator': 'in',
                'value': list(w_item['in']['values']),
            })
        elif 'compare' in w_item:
            cmp_b = w_item['compare']
            rhs = cmp_b['right'].get('value')
            if isinstance(rhs, str) and rhs.startswith(':param:'):
                filters.append({
                    'column': list(cmp_b['left']['column']),
                    'operator': cmp_b['op'],
                    'parameter': rhs.split(':param:', 1)[1],
                })
            else:
                filters.append({
                    'column': list(cmp_b['left']['column']),
                    'operator': cmp_b['op'],
                    'value': rhs,
                })

    gb_raw = sel.get('group_by') or {}
    gb_kind = gb_raw.get('kind', 'columns') if gb_raw else 'columns'
    gb_cols = [
        list(it['column'])
        for it in (gb_raw.get('items') or [])
        if isinstance(it, Mapping) and 'column' in it
    ]
    order_by = [
        {
            'expr': list(o['expr']['column']),
            'direction': o.get('direction', 'asc'),
        }
        for o in (query.get('order_by') or [])
        if isinstance(o, Mapping) and 'column' in (o.get('expr') or {})
    ]
    return normalize_sbsql_query({
        'distinct': bool(sel.get('distinct', False)),
        'from': {
            'relation': list(src),
            'alias': from_spec.get('alias') or src[-1],
        },
        'joins': joins,
        'columns': columns,
        'measures': measures,
        'filters': filters,
        'group_by': {'kind': gb_kind, 'columns': gb_cols},
        'order_by': order_by,
        'limit': query.get('limit', 1000),
    })


def compile_bi_question_sql(
    question: Mapping[str, Any],
    *,
    dialect: str = 'sqlite',
    parameter_values: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile a BI question to dialect SQL with bound parameters (E2).

    Filter values and parameter values are NEVER spliced into the SQL string;
    they are emitted as ``:p_<name>`` placeholders with a separate
    ``bound_params`` dictionary.
    """
    eng = dialect.lower()
    if eng not in (
        'postgresql', 'duckdb', 'sqlite', 'firebird', 'mysql', 'mariadb',
    ):
        raise DesignStoreError(f'Unsupported SQL dialect: {dialect!r}')

    qspec = question.get('query') or {}
    qkind = qspec.get('kind', 'sbsql')
    param_defs = {
        p['id']: p
        for p in (question.get('parameters') or [])
        if isinstance(p, Mapping) and p.get('id')
    }
    provided = dict(parameter_values or {})
    bound_params: dict[str, Any] = {}

    if qkind == 'sql':
        raw_sql = str(qspec.get('sql') or '').strip()
        if not raw_sql or _NON_SELECT_RE.match(raw_sql):
            raise DesignStoreError(
                'BI SQL questions only admit read-only SELECT/WITH statements'
            )

        def _sub_param(match: re.Match[str]) -> str:
            pname = match.group(1)
            if pname in provided:
                bound_params[pname] = provided[pname]
            elif pname in param_defs and 'default' in param_defs[pname]:
                bound_params[pname] = param_defs[pname]['default']
            else:
                bound_params[pname] = None
            return f':{pname}'

        compiled_sql = re.sub(
            r'\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}',
            _sub_param,
            raw_sql,
        )
        return {
            'dialect': eng,
            'sql': compiled_sql,
            'bound_params': bound_params,
            'fanout_warnings': [],
        }

    sbsql = normalize_sbsql_query(qspec.get('sbsql') or qspec)
    fanout_warnings = analyze_sbsql_fanout(sbsql)

    def qident(name: str) -> str:
        return _quote_sql_ident(name, eng)

    def qcol(parts: list[str]) -> str:
        return '.'.join(qident(p) for p in parts)

    def qrel(parts: list[str]) -> str:
        if eng == 'firebird':
            return qident(parts[-1])
        return '.'.join(qident(p) for p in parts)

    select_exprs: list[str] = []
    for col in sbsql['columns']:
        select_exprs.append(f"{qcol(col['column'])} AS {qident(col['alias'])}")
    for meas in sbsql['measures']:
        fn = meas['function']
        if fn == 'count_distinct':
            inner = f"COUNT(DISTINCT {qcol(meas['column'])})"
        elif meas['column'] is None:
            inner = 'COUNT(*)'
        else:
            inner = f"{fn.upper()}({qcol(meas['column'])})"
        select_exprs.append(f"{inner} AS {qident(meas['alias'])}")

    head = 'SELECT DISTINCT' if sbsql['distinct'] else 'SELECT'
    lines = [
        head,
        '  ' + ',\n  '.join(select_exprs),
        f"FROM {qrel(sbsql['from']['relation'])} AS "
        f"{qident(sbsql['from']['alias'])}",
    ]

    for join in sbsql['joins']:
        jkw = sdk_sql_builder.JOINS[join['type']]
        jtarget = (
            f"{qrel(join['relation'])} AS {qident(join['alias'])}"
        )
        if join['type'] in ('cross', 'natural'):
            lines.append(f'  {jkw} {jtarget}')
        elif join.get('using'):
            ucols = ', '.join(qident(u) for u in join['using'])
            lines.append(f'  {jkw} {jtarget} USING ({ucols})')
        else:
            on_sql = ' AND '.join(
                f"{qcol(c['left'])} {c['op']} {qcol(c['right'])}"
                for c in join['on']
            )
            lines.append(f'  {jkw} {jtarget} ON {on_sql}')

    where_clauses: list[str] = []
    p_counter = 0

    def bind_val(hint: str, val: Any) -> str:
        nonlocal p_counter
        p_counter += 1
        key = f'{_safe_ident(hint, "p")}_{p_counter}'
        bound_params[key] = val
        return f':{key}'

    for flt in sbsql['filters']:
        lhs = qcol(flt['column'])
        op = flt['operator']
        if op == 'is_null':
            where_clauses.append(f'{lhs} IS NULL')
            continue
        if op == 'is_not_null':
            where_clauses.append(f'{lhs} IS NOT NULL')
            continue

        if flt.get('parameter'):
            pname = flt['parameter']
            val = (
                provided[pname]
                if pname in provided
                else param_defs.get(pname, {}).get('default')
            )
            if val is None and not param_defs.get(pname, {}).get('required'):
                continue
        else:
            pname = flt['column'][-1]
            val = flt.get('value')

        if op in ('in', 'not_in'):
            items = val if isinstance(val, list) else [val]
            if not items:
                continue
            phs = ', '.join(bind_val(pname, item) for item in items)
            kw = 'NOT IN' if op == 'not_in' else 'IN'
            where_clauses.append(f'{lhs} {kw} ({phs})')
        elif op == 'between':
            if not isinstance(val, list) or len(val) != 2:
                raise DesignStoreError('BETWEEN filter requires 2 values')
            ph_lo = bind_val(f'{pname}_lo', val[0])
            ph_hi = bind_val(f'{pname}_hi', val[1])
            where_clauses.append(f'{lhs} BETWEEN {ph_lo} AND {ph_hi}')
        else:
            sql_op = _OPERATOR_SQL[op]
            ph = bind_val(pname, val)
            where_clauses.append(f'{lhs} {sql_op} {ph}')

    if where_clauses:
        lines.append('WHERE ' + ' AND '.join(where_clauses))

    gb = sbsql['group_by']
    if gb['kind'] == 'all' and eng == 'duckdb':
        lines.append('GROUP BY ALL')
    elif gb['columns']:
        gb_items = ', '.join(qcol(c) for c in gb['columns'])
        if gb['kind'] == 'rollup':
            if eng in ('mysql', 'mariadb'):
                lines.append(f'GROUP BY {gb_items} WITH ROLLUP')
            elif eng in ('postgresql', 'duckdb'):
                lines.append(f'GROUP BY ROLLUP ({gb_items})')
            else:
                lines.append(f'GROUP BY {gb_items}')
        elif gb['kind'] == 'cube' and eng in ('postgresql', 'duckdb'):
            lines.append(f'GROUP BY CUBE ({gb_items})')
        else:
            lines.append(f'GROUP BY {gb_items}')

    if sbsql['order_by']:
        ord_parts = []
        for o in sbsql['order_by']:
            target = (
                qcol(o['expr'])
                if isinstance(o['expr'], list)
                else qident(o['expr'])
            )
            ord_parts.append(f"{target} {o['direction'].upper()}")
        lines.append('ORDER BY ' + ', '.join(ord_parts))

    if sbsql['limit'] is not None:
        if eng == 'firebird':
            lines.append(f"ROWS 1 TO {sbsql['limit']}")
        else:
            lines.append(f"LIMIT {sbsql['limit']}")

    # Validate single-table/multi-join structure against sdk.sql_builder too
    # when operators are standard builder operators, confirming model parity.
    builder_projection = sbsql_to_sql_builder_model(sbsql)
    sdk_sql_builder.build(
        builder_projection,
        lambda ident: qident(ident),
        _all_builder_options_enabled(),
        dialect=(
            {'rollup': 'with_rollup', 'text': 'mysql'}
            if eng in ('mysql', 'mariadb')
            else None
        ),
    )

    return {
        'dialect': eng,
        'sql': '\n'.join(lines),
        'bound_params': bound_params,
        'builder_model': builder_projection,
        'fanout_warnings': fanout_warnings,
    }


def execute_bi_question_connection(
    conn: Any,
    question: Mapping[str, Any],
    *,
    dialect: str = 'sqlite',
    parameter_values: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a compiled BI question over a live DB-API connection."""
    compiled = compile_bi_question_sql(
        question,
        dialect=dialect,
        parameter_values=parameter_values,
    )
    sql = compiled['sql']
    params = compiled['bound_params']
    eng = compiled['dialect']
    if eng in ('duckdb', 'firebird'):
        ordered_vals: list[Any] = []

        def _qmark_ph(match: re.Match[str]) -> str:
            ordered_vals.append(params[match.group(1)])
            return '?'

        exec_sql = re.sub(r':([A-Za-z_][A-Za-z0-9_]*)', _qmark_ph, sql)
        if eng == 'duckdb' and hasattr(conn, 'execute'):
            cur = conn.execute(exec_sql, ordered_vals)
        else:
            cur = conn.cursor()
            cur.execute(exec_sql, ordered_vals)
    elif eng in ('mysql', 'mariadb', 'postgresql'):
        ordered_vals = []

        def _fmt_ph(match: re.Match[str]) -> str:
            ordered_vals.append(params[match.group(1)])
            return '%s'

        exec_sql = re.sub(r':([A-Za-z_][A-Za-z0-9_]*)', _fmt_ph, sql)
        cur = conn.cursor() if hasattr(conn, 'cursor') else conn
        cur.execute(exec_sql, tuple(ordered_vals))
    elif hasattr(conn, 'execute'):
        cur = conn.execute(sql, params)
    else:
        cur = conn.cursor()
        cur.execute(sql, params)
    cols = [desc[0] for desc in (cur.description or ())]
    rows = [list(r) for r in cur.fetchall()]
    return {
        'columns': cols,
        'rows': rows,
        'sql': sql,
        'bound_params': params,
        'fanout_warnings': compiled['fanout_warnings'],
    }


def sql_to_bi_question_model(
    sql: str,
    *,
    name: str = 'Question from SQL',
    endpoint_id: str = 'default-endpoint',
    parameter_types: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Map raw SQL onto unified SBsql question state with fidelity report."""
    converted = sql_to_question(
        sql,
        name=name,
        parameter_types=parameter_types,
    )
    raw_q = converted['question']
    qspec = raw_q['query']
    if qspec['kind'] == 'builder':
        b = qspec['builder']
        rel = list(b['source']['relation'])
        alias = rel[-1]
        plain_cols = list(b.get('group_by') or []) + list(
            b.get('columns') or []
        )
        sbsql = normalize_sbsql_query({
            'from': {'relation': rel, 'alias': alias},
            'columns': [
                {
                    'column': [alias, g['column']],
                    'alias': g.get('alias') or g['column'],
                }
                for g in plain_cols
            ],
            'measures': [
                {
                    'function': m['function'],
                    'column': (
                        [alias, m['column']] if m.get('column') else None
                    ),
                    'alias': m.get('alias') or (
                        f"{m['function']}_{m.get('column') or 'rows'}"
                    ),
                }
                for m in b.get('aggregations', [])
            ],
            'filters': [
                {
                    'column': [alias, f['column']],
                    'operator': f['operator'],
                    **(
                        {'parameter': f['parameter']}
                        if f.get('parameter')
                        else {'value': f.get('value')}
                    ),
                }
                for f in b.get('filters', [])
            ],
            'order_by': [
                {
                    'expr': o['column'],
                    'direction': o.get('direction', 'asc'),
                }
                for o in b.get('order_by', [])
            ],
            'limit': b.get('limit', 1000),
        })
        model = default_question_model(
            name=name,
            endpoint_id=endpoint_id,
            sbsql=sbsql,
            parameters=raw_q.get('parameters', []),
            visualization=raw_q.get('visualization'),
        )
    else:
        model = default_question_model(
            name=name,
            endpoint_id=endpoint_id,
            raw_sql=qspec['sql'],
            parameters=raw_q.get('parameters', []),
            visualization=raw_q.get('visualization'),
        )
    return {
        'question': model,
        'fidelity': converted['fidelity'],
        'loss': converted['loss'],
    }


# ---------------------------------------------------------------------------
# Question & Dashboard Validation + Lossless DDN Serialization (E1, E3, E5-E7)
# ---------------------------------------------------------------------------


def default_question_model(
    name: str = 'New Question',
    *,
    endpoint_id: str = 'default-endpoint',
    sbsql: Mapping[str, Any] | None = None,
    raw_sql: str | None = None,
    parameters: list[dict[str, Any]] | None = None,
    visualization: Mapping[str, Any] | None = None,
    result_policy: Mapping[str, Any] | None = None,
    preview_rows: list[list[Any]] | None = None,
    verification_tier: str = 'draft',
) -> dict[str, Any]:
    """Build and validate a canonical BI Question model."""
    title = str(name or 'New Question').strip() or 'New Question'
    vis_type = str((visualization or {}).get('type') or 'bar')
    if vis_type not in CHART_PROFILE_MAP:
        raise DesignStoreError(
            f'Unsupported BI chart visualization type: {vis_type!r}'
        )
    if verification_tier not in VERIFICATION_TIERS:
        raise DesignStoreError(
            f'Unsupported verification_tier: {verification_tier!r}'
        )

    if raw_sql is not None:
        sql_clean = str(raw_sql).strip()
        if not sql_clean or _NON_SELECT_RE.match(sql_clean):
            raise DesignStoreError(
                'BI SQL questions only admit read-only SELECT/WITH statements'
            )
        query_block: dict[str, Any] = {'kind': 'sql', 'sql': sql_clean}
    else:
        normalized_sbsql = normalize_sbsql_query(sbsql or {
            'from': {'relation': ['main', 'orders'], 'alias': 'orders'},
            'columns': [{'column': ['orders', 'region'], 'alias': 'region'}],
            'measures': [{
                'function': 'sum',
                'column': ['orders', 'amount'],
                'alias': 'total_amount',
            }],
            'limit': 100,
        })
        query_block = {'kind': 'sbsql', 'sbsql': normalized_sbsql}

    norm_params: list[dict[str, Any]] = []
    for praw in parameters or []:
        ptype = str(praw.get('type') or 'string')
        if ptype not in PARAMETER_TYPES:
            ptype = 'string'
        entry: dict[str, Any] = {
            'id': _safe_ident(praw.get('id'), 'param'),
            'name': str(praw.get('name') or praw.get('id') or 'Parameter'),
            'type': ptype,
            'required': bool(praw.get('required', False)),
        }
        if 'default' in praw and praw['default'] is not None:
            entry['default'] = copy.deepcopy(praw['default'])
        if praw.get('allowed_values'):
            entry['allowed_values'] = list(praw['allowed_values'])
        norm_params.append(entry)

    rpol = dict(result_policy or {})
    question = {
        'contract_version': '1.0.0',
        'name': title,
        'description': str(rpol.pop('description', '') or ''),
        'endpoint_id': str(endpoint_id or 'default-endpoint'),
        'verification_tier': verification_tier,
        'query': query_block,
        'parameters': norm_params,
        'visualization': {
            'type': vis_type,
            'settings': copy.deepcopy(
                dict((visualization or {}).get('settings') or {})
            ),
        },
        'result_policy': {
            'redact_columns': list(rpol.get('redact_columns') or []),
            'cache_ttl_seconds': int(rpol.get('cache_ttl_seconds', 300)),
            'page_size': int(rpol.get('page_size', 100)),
            'export': copy.deepcopy(
                rpol.get('export') or {'enabled': False, 'formats': []}
            ),
        },
        'preview_rows': copy.deepcopy(preview_rows or []),
    }
    _ensure_no_writeback(question)
    _ensure_no_sensitive_fields(question)
    question['review_flags'] = {
        'saved_filter_values': collect_saved_filter_value_flags(question),
        'fanout_warnings': (
            analyze_sbsql_fanout(query_block['sbsql'])
            if query_block['kind'] == 'sbsql'
            else []
        ),
    }
    return question


def validate_bi_question(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an incoming BI question dictionary."""
    _ensure_no_writeback(raw)
    _ensure_no_sensitive_fields(raw)
    qblock = raw.get('query') or {}
    qkind = qblock.get('kind', 'sbsql')
    question = default_question_model(
        name=str(raw.get('name') or 'New Question'),
        endpoint_id=str(raw.get('endpoint_id') or 'default-endpoint'),
        sbsql=qblock.get('sbsql') if qkind != 'sql' else None,
        raw_sql=qblock.get('sql') if qkind == 'sql' else None,
        parameters=list(raw.get('parameters') or []),
        visualization=raw.get('visualization'),
        result_policy=raw.get('result_policy'),
        preview_rows=list(raw.get('preview_rows') or []),
        verification_tier=str(raw.get('verification_tier') or 'draft'),
    )
    question['description'] = str(raw.get('description') or '')
    return question


def _preview_columns_and_rows(
    question: Mapping[str, Any],
) -> tuple[list[dict[str, str]], list[list[Any]]]:
    """Build deterministic DDN data columns & rows for chart rendering."""
    qblock = question['query']
    cols: list[dict[str, str]] = []
    if qblock['kind'] == 'sbsql':
        sbsql = qblock['sbsql']
        for c in sbsql['columns']:
            cols.append({'id': c['alias'], 'type': 'text'})
        for m in sbsql['measures']:
            cols.append({'id': m['alias'], 'type': 'number'})
    if not cols:
        cols = [
            {'id': 'label', 'type': 'text'},
            {'id': 'value', 'type': 'number'},
        ]
    raw_rows = question.get('preview_rows') or []
    rows: list[list[Any]] = []
    for idx, r in enumerate(raw_rows[:200]):
        if isinstance(r, list):
            padded = list(r[:len(cols)])
            while len(padded) < len(cols):
                padded.append('' if cols[len(padded)]['type'] == 'text' else 0)
            rows.append([f'r_{idx + 1}', *padded])
    if not rows:
        sample = [
            'Sample A' if c['type'] == 'text' else 10
            for c in cols
        ]
        rows = [['r_1', *sample]]
    return [{'id': 'row_id', 'type': 'text'}, *cols], rows


def _chart_projection_options(
    vis_type: str,
    columns: list[dict[str, str]],
    settings: Mapping[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return ``(ddn_profile, projection_options)`` for any BI chart type."""
    if vis_type not in CHART_PROFILE_MAP:
        raise DesignStoreError(f'Unsupported BI chart type: {vis_type!r}')
    profile, mark = CHART_PROFILE_MAP[vis_type]
    non_key = [c for c in columns if c['id'] != 'row_id']
    x_col = (
        str((settings or {}).get('x') or '')
        or (non_key[0]['id'] if non_key else 'row_id')
    )
    num_cols = [c['id'] for c in non_key if c['type'] == 'number']
    y_col = (
        str((settings or {}).get('y') or '')
        or (
            num_cols[0]
            if num_cols
            else (non_key[-1]['id'] if non_key else 'row_id')
        )
    )
    if profile == 'table.records@1':
        return profile, {
            'columns': [
                {'id': c['id'], 'label': c['id']}
                for c in non_key
            ],
        }
    if profile == 'timeline.basic@1':
        end_col = non_key[1]['id'] if len(non_key) > 1 else x_col
        return profile, {
            'start': x_col,
            'end': end_col,
            'label': x_col,
        }
    opts: dict[str, Any] = {'x': x_col, 'y': y_col}
    if mark:
        opts['mark'] = mark
    return profile, opts


def _emit_data_block(
    data_id: str,
    columns: list[dict[str, str]],
    rows: list[list[Any]],
) -> list[str]:
    lines = [
        f'data {_q(data_id)}',
        '    with',
        f'        id {_q(data_id)}',
        '        key "row_id"',
        '        columns',
    ]
    for col in columns:
        lines.extend([
            '            item',
            f'                id {_q(col["id"])}',
            f'                type {_q(col["type"])}',
        ])
    if not rows:
        lines.append('        rows empty list')
    else:
        lines.append('        rows')
        for row in rows:
            lines.append('            item')
            for cell in row:
                if isinstance(cell, (int, float)) and not isinstance(
                    cell, bool
                ):
                    lines.append(f'                item {json.dumps(cell)}')
                else:
                    lines.append(f'                item {_q(str(cell))}')
    lines.append('')
    return lines


def _emit_bi_companion_record(
    lines: list[str],
    record_id: str,
    *,
    module_name: str,
    block_kind: str,
    subject_id: str,
    logical_name: str,
    fields: Mapping[str, str],
    resource_id: str | None = None,
    position: Mapping[str, float] | None = None,
) -> None:
    lines.extend([
        f'element {_q(record_id)} as "record"',
        '    with',
        f'        id {_q(record_id)}',
        f'        title {_q(f"{block_kind}:{logical_name}")}',
        '        metadata',
        '            x_record',
        f'                module {_q(module_name)}',
        f'                block {_q(block_kind)}',
        f'                name_json {_q(json.dumps(logical_name))}',
        '                record',
        f'                    subject_id {_q(subject_id)}',
    ])
    if resource_id:
        lines.append(f'                    resource_id {_q(resource_id)}')
    if position and 'x' in position and 'y' in position:
        lines.append(
            f'                    pos_x {_q(str(float(position["x"])))}'
        )
        lines.append(
            f'                    pos_y {_q(str(float(position["y"])))}'
        )
    for key, val in sorted(fields.items()):
        lines.append(f'                    {key} {_q(val)}')
    lines.append('')


def _emit_chart_view(
    view_id: str,
    title: str,
    profile: str,
    data_id: str,
    options: Mapping[str, Any],
) -> list[str]:
    lines = [
        f'view {_q(view_id)} as {_q(profile)}',
        '    with',
        f'        id {_q(view_id)}',
        f'        title {_q(title)}',
        '        selection',
        '            include empty list',
        '        projection',
        '            options',
        '                records',
        '                    item',
        f'                        id {_q(data_id)}',
    ]
    for key, val in options.items():
        if key == 'columns' and isinstance(val, list):
            lines.append('                columns')
            for col in val:
                lines.extend([
                    '                    item',
                    f'                        id {_q(col["id"])}',
                    f'                        label {_q(col["label"])}',
                ])
        elif isinstance(val, str):
            lines.append(f'                {key} {_q(val)}')
        elif isinstance(val, (int, float, bool)):
            lines.append(f'                {key} {json.dumps(val)}')
    lines.append('')
    return lines


def question_to_ddn(
    question_raw: Mapping[str, Any],
    *,
    element_ids: Mapping[str, str] | None = None,
    layout_positions: Mapping[str, Mapping[str, float]] | None = None,
    question_notes: str = '',
) -> tuple[str, dict[str, str]]:
    """Serialize a BI Question losslessly into ``ddn-next-1`` text."""
    question = validate_bi_question(question_raw)
    id_map: dict[str, str] = dict(element_ids or {})
    pos_map = dict(layout_positions or {})
    root_id = _alloc_id(id_map, 'question:root')
    op_id = _alloc_id(id_map, 'question:query_op')

    elements: list[tuple[str, str, str, dict[str, Any]]] = []
    relations: list[tuple[str, str, str, str, str]] = []

    qblock = question['query']
    if qblock['kind'] == 'sbsql':
        sbsql = qblock['sbsql']
        base_rel = sbsql['from']['relation']
        base_res = 'table:' + ':'.join(base_rel)
        base_el = _alloc_id(id_map, f"source:{sbsql['from']['alias']}")
        elements.append((
            base_el,
            'table',
            '.'.join(base_rel),
            {
                'resource_id': base_res,
                'alias': sbsql['from']['alias'],
                'columns': [c['alias'] for c in sbsql['columns']],
            },
        ))
        relations.append((
            _alloc_id(id_map, f'rel:op_uses:{base_el}'),
            'uses',
            op_id,
            base_el,
            'FROM',
        ))
        for join in sbsql['joins']:
            j_res = 'table:' + ':'.join(join['relation'])
            j_el = _alloc_id(id_map, f"source:{join['alias']}")
            elements.append((
                j_el,
                'table',
                '.'.join(join['relation']),
                {
                    'resource_id': j_res,
                    'alias': join['alias'],
                    'cardinality': join['cardinality'],
                },
            ))
            relations.append((
                _alloc_id(id_map, f'rel:join:{j_el}'),
                'joins',
                base_el,
                j_el,
                f"{join['type'].upper()} ({join['cardinality']})",
            ))
            relations.append((
                _alloc_id(id_map, f'rel:op_uses:{j_el}'),
                'uses',
                op_id,
                j_el,
                join['type'].upper(),
            ))
        for meas in sbsql['measures']:
            m_el = _alloc_id(id_map, f"measure:{meas['alias']}")
            elements.append((
                m_el,
                'metric',
                meas['alias'],
                {
                    'function': meas['function'],
                    'column': meas['column'],
                },
            ))
            relations.append((
                _alloc_id(id_map, f'rel:agg:{m_el}'),
                'aggregates',
                op_id,
                m_el,
                meas['function'].upper(),
            ))
    else:
        sql_ds_el = _alloc_id(id_map, 'source:sql_dataset')
        elements.append((
            sql_ds_el,
            'dataset',
            f"{question['name']} SQL",
            {'endpoint_id': question['endpoint_id'], 'kind': 'sql'},
        ))
        relations.append((
            _alloc_id(id_map, f'rel:op_uses:{sql_ds_el}'),
            'uses',
            op_id,
            sql_ds_el,
            'SQL',
        ))

    for param in question['parameters']:
        p_el = _alloc_id(id_map, f"param:{param['id']}")
        elements.append((
            p_el,
            'binding',
            param['name'],
            {
                'parameter_id': param['id'],
                'type': param['type'],
                'required': param['required'],
            },
        ))
        relations.append((
            _alloc_id(id_map, f'rel:param_filters:{p_el}'),
            'filters',
            p_el,
            op_id,
            f":{param['id']}",
        ))

    elements.append((
        op_id,
        'query_operation',
        f"{question['name']} Query",
        {'query_kind': qblock['kind']},
    ))
    relations.append((
        _alloc_id(id_map, 'rel:root_derives_op'),
        'derives',
        root_id,
        op_id,
        question['visualization']['type'],
    ))

    root_rec_id = _alloc_id(id_map, 'record:question:root')
    element_rec_ids = {
        el_id: _alloc_id(id_map, f'record:el:{el_id}')
        for el_id, *_ in elements
    }

    envelope = {
        'bi_kind': 'question',
        'question': question,
        'question_notes': str(question_notes or ''),
        'element_ids': dict(id_map),
    }

    lines = [
        f'version {DEFAULT_DIALECT}',
        f'// ScratchRobin module: {BI_QUESTION_MODULE}',
        '',
    ]
    data_cols, data_rows = _preview_columns_and_rows(question)
    lines.extend(_emit_data_block('question_preview', data_cols, data_rows))

    # Root saved_view element
    lines.extend([
        f'element {_q(root_id)} as "saved_view"',
        '    with',
        f'        id {_q(root_id)}',
        f'        title {_q(question["name"])}',
        '',
    ])
    _emit_bi_companion_record(
        lines,
        root_rec_id,
        module_name=BI_QUESTION_MODULE,
        block_kind='question_root',
        subject_id=root_id,
        logical_name=question['name'],
        fields={'envelope_json': _json_str(envelope)},
        position=pos_map.get(root_id),
    )

    for el_id, role, el_name, meta in elements:
        lines.extend([
            f'element {_q(el_id)} as {_q(role)}',
            '    with',
            f'        id {_q(el_id)}',
            f'        title {_q(el_name)}',
            '',
        ])
        _emit_bi_companion_record(
            lines,
            element_rec_ids[el_id],
            module_name=BI_QUESTION_MODULE,
            block_kind='question_element',
            subject_id=el_id,
            logical_name=el_name,
            fields={'meta_json': _json_str(meta)},
            resource_id=meta.get('resource_id'),
            position=pos_map.get(el_id),
        )

    for rel_id, rel_role, src_id, dst_id, label in relations:
        lines.extend([
            f'relation {_q(rel_id)} as {_q(rel_role)}',
            f'    endpoint {_q(src_id)}',
            f'    endpoint {_q(dst_id)}',
            '    with',
            f'        id {_q(rel_id)}',
            f'        title {_q(label)}',
            '',
        ])

    vis_type = question['visualization']['type']
    chart_profile, chart_opts = _chart_projection_options(
        vis_type,
        data_cols,
        question['visualization']['settings'],
    )
    lines.extend(_emit_chart_view(
        'question_chart',
        question['name'],
        chart_profile,
        'question_preview',
        chart_opts,
    ))

    include_ids = [
        root_id,
        *[e[0] for e in elements],
        *[r[0] for r in relations],
    ]
    lines.extend([
        f'view "question_lineage" as {_q(BI_ANALYTICS_PROFILE)}',
        '    with',
        '        id "question_lineage"',
        f'        title {_q(question["name"] + " — Query Lineage")}',
        '        selection',
        '            include',
    ])
    for inc_id in include_ids:
        lines.extend([
            '                item',
            f'                    id {_q(inc_id)}',
        ])
    lines.append('')

    return '\n'.join(lines).rstrip() + '\n', id_map


def ddn_to_question(ddn_text: str) -> dict[str, Any]:
    """Parse a BI Question DDN document back to its canonical model."""
    blocks = _parse_blocks(ddn_text)
    positions: dict[str, dict[str, float]] = {}
    envelope: dict[str, Any] | None = None
    for blk in blocks:
        xrec = _extract_x_record(blk)
        if xrec is None or xrec.get('module') != BI_QUESTION_MODULE:
            continue
        rec = xrec.get('record') or {}
        subj = rec.get('subject_id')
        if subj and 'pos_x' in rec and 'pos_y' in rec:
            try:
                positions[subj] = {
                    'x': float(rec['pos_x']),
                    'y': float(rec['pos_y']),
                }
            except (TypeError, ValueError):
                pass
        if xrec.get('block') == 'question_root' and rec.get('envelope_json'):
            envelope = json.loads(str(rec['envelope_json']))
    if envelope is None:
        raise DesignStoreError(
            'DDN document does not contain a scratchrobin.bi.question@1 '
            'saved_view envelope'
        )
    question = validate_bi_question(envelope['question'])
    return {
        'question': question,
        'question_notes': str(envelope.get('question_notes') or ''),
        'element_ids': dict(envelope.get('element_ids') or {}),
        'layout_positions': positions,
    }


def default_dashboard_model(
    name: str = 'New Dashboard',
    *,
    tabs: list[dict[str, Any]] | None = None,
    cards: list[dict[str, Any]] | None = None,
    filters: list[dict[str, Any]] | None = None,
    links: list[dict[str, Any]] | None = None,
    interaction: Mapping[str, Any] | None = None,
    description: str = '',
) -> dict[str, Any]:
    """Build and validate a canonical BI Dashboard model (E1, E3, E5-E7)."""
    title = str(name or 'New Dashboard').strip() or 'New Dashboard'
    norm_tabs: list[dict[str, Any]] = []
    for traw in tabs or [{'id': 'main', 'name': 'Overview'}]:
        tid = _safe_ident(traw.get('id'), 'tab')
        norm_tabs.append({
            'id': tid,
            'name': str(traw.get('name') or tid)[:256],
        })
    tab_ids = {t['id'] for t in norm_tabs}

    inter_raw = dict(interaction or {})
    _ensure_no_writeback(inter_raw)
    _ensure_no_sensitive_fields(inter_raw, 'interaction')
    default_click = str(
        inter_raw.get('default_click_behavior') or 'cross_filter'
    )
    if default_click not in ('cross_filter', 'highlight', 'none'):
        raise DesignStoreError(
            f'Unsupported default_click_behavior: {default_click!r}'
        )
    filter_scope = str(inter_raw.get('filter_state_scope') or 'personal')
    if filter_scope not in ('personal', 'author_pinned'):
        raise DesignStoreError(
            f'Unsupported filter_state_scope: {filter_scope!r}'
        )
    norm_interaction = {
        'default_click_behavior': default_click,
        'auto_apply_filters': bool(inter_raw.get('auto_apply_filters', True)),
        'filter_state_scope': filter_scope,
        'drill_carries_filter_context': bool(
            inter_raw.get('drill_carries_filter_context', True)
        ),
    }

    norm_cards: list[dict[str, Any]] = []
    for idx, craw in enumerate(cards or []):
        cid = _safe_ident(craw.get('id') or f'card_{idx + 1}', 'card')
        tab_id = str(craw.get('tab_id') or norm_tabs[0]['id'])
        if tab_id not in tab_ids:
            raise DesignStoreError(f'Card {cid!r} references unknown tab')
        ctype = str(craw.get('type') or 'question')
        if ctype not in ('question', 'text', 'metric_panel'):
            raise DesignStoreError(f'Unsupported card type: {ctype!r}')
        click_override = str(craw.get('click_behavior') or 'inherit')
        if click_override not in CLICK_BEHAVIORS:
            raise DesignStoreError(
                f'Unsupported card click_behavior: {click_override!r}'
            )
        lay = craw.get('layout') or {'x': 0, 'y': idx * 8, 'w': 12, 'h': 8}
        card: dict[str, Any] = {
            'id': cid,
            'tab_id': tab_id,
            'type': ctype,
            'title': str(craw.get('title') or cid)[:256],
            'click_behavior': click_override,
            'layout': {
                'x': max(0, min(23, int(lay.get('x', 0)))),
                'y': max(0, int(lay.get('y', 0))),
                'w': max(1, min(24, int(lay.get('w', 12)))),
                'h': max(1, min(100, int(lay.get('h', 8)))),
            },
        }
        if ctype == 'question':
            qref = craw.get('question') or {}
            q_design_id = str(
                qref.get('question_design_id')
                or qref.get('question_id')
                or ''
            ).strip()
            if not q_design_id:
                raise DesignStoreError(
                    f'Question card {cid!r} requires question_design_id'
                )
            vis_override = craw.get('visualization') or {'type': 'bar'}
            vtype = str(vis_override.get('type') or 'bar')
            if vtype not in CHART_PROFILE_MAP:
                raise DesignStoreError(
                    f'Unsupported card visualization type: {vtype!r}'
                )
            card['question'] = {
                'question_design_id': q_design_id,
                'pinned_version': (
                    int(qref['pinned_version'])
                    if qref.get('pinned_version') is not None
                    else None
                ),
                'follow_latest_accepted': bool(
                    qref.get('follow_latest_accepted', False)
                ),
            }
            card['visualization'] = {
                'type': vtype,
                'settings': copy.deepcopy(
                    dict(vis_override.get('settings') or {})
                ),
            }
            card['preview_rows'] = copy.deepcopy(
                list(craw.get('preview_rows') or [])
            )
        elif ctype == 'text':
            t_obj = craw.get('text') or {}
            card['text'] = {'markdown': str(t_obj.get('markdown') or '')}
        else:
            mp = craw.get('metric_panel') or {}
            # Owner decision E7: imported metric_panel cards in BI hold static
            # snapshots only (never live collector feeds or BI questions).
            card['metric_panel'] = {
                'panel_id': str(mp.get('panel_id') or cid),
                'snapshot_mode': 'static',
                'columns': copy.deepcopy(list(mp.get('columns') or [
                    {'id': 'measure', 'label': 'Measure'},
                    {'id': 'value', 'label': 'Snapshot Value'},
                ])),
                'rows': copy.deepcopy(list(mp.get('rows') or [])),
            }
        norm_cards.append(card)

    norm_filters: list[dict[str, Any]] = []
    for fraw in filters or []:
        fid = _safe_ident(fraw.get('id'), 'filter')
        ftype = str(fraw.get('type') or 'string')
        if ftype not in PARAMETER_TYPES:
            ftype = 'string'
        fentry: dict[str, Any] = {
            'id': fid,
            'name': str(fraw.get('name') or fid)[:256],
            'type': ftype,
            'widget': str(fraw.get('widget') or 'text'),
            'operator': str(fraw.get('operator') or 'eq'),
            'required': bool(fraw.get('required', False)),
            'pinned_by_author': bool(fraw.get('pinned_by_author', False)),
            'targets': copy.deepcopy(list(fraw.get('targets') or [])),
        }
        if 'default' in fraw and fraw['default'] is not None:
            fentry['default'] = copy.deepcopy(fraw['default'])
        norm_filters.append(fentry)

    norm_links: list[dict[str, Any]] = []
    for idx, lraw in enumerate(links or []):
        norm_links.append({
            'id': _safe_ident(lraw.get('id') or f'link_{idx + 1}', 'link'),
            'card_id': str(lraw.get('card_id') or ''),
            'kind': str(lraw.get('kind') or 'drill_through'),
            'target_design_id': str(lraw.get('target_design_id') or ''),
            'carry_filter_context': bool(
                lraw.get('carry_filter_context', True)
            ),
            'field_map': copy.deepcopy(dict(lraw.get('field_map') or {})),
        })

    dashboard = {
        'contract_version': '1.0.0',
        'name': title,
        'description': str(description or ''),
        'tabs': norm_tabs,
        'cards': norm_cards,
        'filters': norm_filters,
        'links': norm_links,
        'interaction': norm_interaction,
    }
    _ensure_no_writeback(dashboard)
    _ensure_no_sensitive_fields(dashboard)
    dashboard['review_flags'] = {
        'saved_filter_values': collect_saved_filter_value_flags(dashboard),
    }
    return dashboard


def validate_bi_dashboard(raw: Mapping[str, Any]) -> dict[str, Any]:
    _ensure_no_writeback(raw)
    _ensure_no_sensitive_fields(raw)
    return default_dashboard_model(
        name=str(raw.get('name') or 'New Dashboard'),
        tabs=list(raw.get('tabs') or [{'id': 'main', 'name': 'Overview'}]),
        cards=list(raw.get('cards') or []),
        filters=list(raw.get('filters') or []),
        links=list(raw.get('links') or []),
        interaction=raw.get('interaction'),
        description=str(raw.get('description') or ''),
    )


def carry_drill_filter_context(
    dashboard_raw: Mapping[str, Any],
    *,
    card_id: str,
    active_filters: Mapping[str, Any] | None = None,
    cross_filters: Mapping[str, Any] | None = None,
    clicked_row: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute effective interaction & drill-through filter context (E5)."""
    dashboard = validate_bi_dashboard(dashboard_raw)
    card = next(
        (c for c in dashboard['cards'] if c['id'] == card_id),
        None,
    )
    if card is None:
        raise DesignStoreNotFound(f'Dashboard card {card_id!r} was not found')
    effective_click = (
        dashboard['interaction']['default_click_behavior']
        if card['click_behavior'] == 'inherit'
        else card['click_behavior']
    )
    merged: dict[str, Any] = {}
    for flt in dashboard['filters']:
        if flt.get('pinned_by_author') and 'default' in flt:
            merged[flt['id']] = copy.deepcopy(flt['default'])
    for k, v in (active_filters or {}).items():
        merged[str(k)] = copy.deepcopy(v)
    if effective_click == 'cross_filter':
        for k, v in (cross_filters or {}).items():
            merged[str(k)] = copy.deepcopy(v)
    link = next(
        (lnk for lnk in dashboard['links'] if lnk['card_id'] == card_id),
        None,
    )
    if clicked_row and effective_click == 'cross_filter':
        for k, v in clicked_row.items():
            merged.setdefault(str(k), copy.deepcopy(v))
    if link and clicked_row:
        for src_col, dst_param in (link.get('field_map') or {}).items():
            if src_col in clicked_row:
                merged[str(dst_param)] = copy.deepcopy(clicked_row[src_col])
    return {
        'card_id': card_id,
        'effective_click_behavior': effective_click,
        'auto_apply_filters': dashboard['interaction']['auto_apply_filters'],
        'filter_state_scope': dashboard['interaction']['filter_state_scope'],
        'carried_filters': merged,
        'target_design_id': link['target_design_id'] if link else None,
    }


def dashboard_to_ddn(
    dashboard_raw: Mapping[str, Any],
    *,
    element_ids: Mapping[str, str] | None = None,
    layout_positions: Mapping[str, Mapping[str, float]] | None = None,
    dashboard_notes: str = '',
) -> tuple[str, dict[str, str]]:
    """Serialize a BI Dashboard losslessly into ``ddn-next-1`` text."""
    dashboard = validate_bi_dashboard(dashboard_raw)
    id_map: dict[str, str] = dict(element_ids or {})
    pos_map = dict(layout_positions or {})
    root_id = _alloc_id(id_map, 'dashboard:root')

    elements: list[tuple[str, str, str, dict[str, Any]]] = []
    relations: list[tuple[str, str, str, str, str]] = []
    data_blocks: list[str] = []
    card_views: list[str] = []
    card_view_ids: dict[str, str] = {}
    q_el_by_design: dict[str, str] = {}

    for card in dashboard['cards']:
        cid = card['id']
        c_el = _alloc_id(id_map, f'card:{cid}')
        data_id = f'card_data_{cid}'
        view_id = f'card_view_{cid}'
        card_view_ids[cid] = view_id

        if card['type'] == 'question':
            q_did = card['question']['question_design_id']
            vtype = card['visualization']['type']
            cols = [
                {'id': 'row_id', 'type': 'text'},
                {'id': 'label', 'type': 'text'},
                {'id': 'value', 'type': 'number'},
            ]
            raw_rows = card.get('preview_rows') or [['Category A', 42]]
            rows = [
                [
                    'r_' + str(i + 1),
                    str(r[0]),
                    float(r[1]) if len(r) > 1 else 0,
                ]
                for i, r in enumerate(raw_rows[:100])
                if isinstance(r, list) and r
            ] or [['r_1', 'Category A', 42]]
            data_blocks.extend(_emit_data_block(data_id, cols, rows))
            c_prof, c_opts = _chart_projection_options(
                vtype, cols, card['visualization']['settings']
            )
            card_views.extend(_emit_chart_view(
                view_id, card['title'], c_prof, data_id, c_opts,
            ))
            elements.append((
                c_el,
                'report',
                card['title'],
                {'card_id': cid, 'type': 'question', 'chart': vtype},
            ))
            q_el = q_el_by_design.get(q_did)
            if q_el is None:
                q_el = _alloc_id(id_map, f'question_ref:{q_did}')
                q_el_by_design[q_did] = q_el
                elements.append((
                    q_el,
                    'saved_view',
                    f'Question {q_did[:8]}',
                    {'question_design_id': q_did},
                ))
            relations.append((
                _alloc_id(id_map, f'rel:card_uses:{cid}'),
                'uses',
                c_el,
                q_el,
                vtype,
            ))
        elif card['type'] == 'text':
            cols = [
                {'id': 'row_id', 'type': 'text'},
                {'id': 'markdown', 'type': 'text'},
            ]
            rows = [['r_1', card['text']['markdown'] or card['title']]]
            data_blocks.extend(_emit_data_block(data_id, cols, rows))
            card_views.extend(_emit_chart_view(
                view_id,
                card['title'],
                'table.records@1',
                data_id,
                {'columns': [{'id': 'markdown', 'label': card['title']}]},
            ))
            elements.append((
                c_el,
                'record',
                card['title'],
                {'card_id': cid, 'type': 'text'},
            ))
        else:
            mp = card['metric_panel']
            cols = [
                {'id': 'row_id', 'type': 'text'},
                *[
                    {'id': col['id'], 'type': 'text'}
                    for col in mp['columns']
                ],
            ]
            rows = [
                [
                    str(r.get('id') or f'r_{i + 1}'),
                    *[str(r.get(col['id'], '')) for col in mp['columns']],
                ]
                for i, r in enumerate(mp['rows'])
                if isinstance(r, Mapping)
            ] or [['r_1', *['Static snapshot' for _ in mp['columns']]]]
            data_blocks.extend(_emit_data_block(data_id, cols, rows))
            card_views.extend(_emit_chart_view(
                view_id,
                card['title'],
                'table.records@1',
                data_id,
                {
                    'columns': [
                        {'id': col['id'], 'label': col['label']}
                        for col in mp['columns']
                    ],
                },
            ))
            elements.append((
                c_el,
                'metric',
                card['title'],
                {
                    'card_id': cid,
                    'type': 'metric_panel',
                    'snapshot_mode': 'static',
                },
            ))

        relations.append((
            _alloc_id(id_map, f'rel:dash_part:{cid}'),
            'part',
            root_id,
            c_el,
            card['tab_id'],
        ))

    for flt in dashboard['filters']:
        f_el = _alloc_id(id_map, f"filter:{flt['id']}")
        elements.append((
            f_el,
            'binding',
            flt['name'],
            {'filter_id': flt['id'], 'widget': flt['widget']},
        ))
        relations.append((
            _alloc_id(id_map, f"rel:dash_owns_filter:{flt['id']}"),
            'owns',
            root_id,
            f_el,
            flt['operator'],
        ))
        for tgt in flt.get('targets') or []:
            tcid = tgt.get('card_id')
            target_el = id_map.get(f'card:{tcid}')
            if target_el:
                relations.append((
                    _alloc_id(
                        id_map, f"rel:filter_card:{flt['id']}:{tcid}"
                    ),
                    'filters',
                    f_el,
                    target_el,
                    str(tgt.get('parameter') or tgt.get('field') or flt['id']),
                ))

    root_rec_id = _alloc_id(id_map, 'record:dashboard:root')
    element_rec_ids = {
        el_id: _alloc_id(id_map, f'record:el:{el_id}')
        for el_id, *_ in elements
    }

    envelope = {
        'bi_kind': 'dashboard',
        'dashboard': dashboard,
        'dashboard_notes': str(dashboard_notes or ''),
        'element_ids': dict(id_map),
    }

    lines = [
        f'version {DEFAULT_DIALECT}',
        f'// ScratchRobin module: {BI_DASHBOARD_MODULE}',
        '',
    ]
    lines.extend(data_blocks)

    lines.extend([
        f'element {_q(root_id)} as "dashboard"',
        '    with',
        f'        id {_q(root_id)}',
        f'        title {_q(dashboard["name"])}',
        '',
    ])
    _emit_bi_companion_record(
        lines,
        root_rec_id,
        module_name=BI_DASHBOARD_MODULE,
        block_kind='dashboard_root',
        subject_id=root_id,
        logical_name=dashboard['name'],
        fields={'envelope_json': _json_str(envelope)},
        position=pos_map.get(root_id),
    )

    for el_id, role, el_name, meta in elements:
        lines.extend([
            f'element {_q(el_id)} as {_q(role)}',
            '    with',
            f'        id {_q(el_id)}',
            f'        title {_q(el_name)}',
            '',
        ])
        _emit_bi_companion_record(
            lines,
            element_rec_ids[el_id],
            module_name=BI_DASHBOARD_MODULE,
            block_kind='dashboard_element',
            subject_id=el_id,
            logical_name=el_name,
            fields={'meta_json': _json_str(meta)},
            position=pos_map.get(el_id),
        )

    for rel_id, rel_role, src_id, dst_id, label in relations:
        lines.extend([
            f'relation {_q(rel_id)} as {_q(rel_role)}',
            f'    endpoint {_q(src_id)}',
            f'    endpoint {_q(dst_id)}',
            '    with',
            f'        id {_q(rel_id)}',
            f'        title {_q(label)}',
            '',
        ])

    lines.extend(card_views)

    for idx, tab in enumerate(dashboard['tabs']):
        tab_cards = [
            c for c in dashboard['cards'] if c['tab_id'] == tab['id']
        ]
        tab_view_id = (
            'dashboard_composed'
            if idx == 0
            else f"dashboard_tab_{tab['id']}"
        )
        lines.extend([
            f'view {_q(tab_view_id)} as {_q(COMPOSED_PANELS_PROFILE)}',
            '    with',
            f'        id {_q(tab_view_id)}',
            f'        title {_q(dashboard["name"] + " — " + tab["name"])}',
            '        selection',
            '            include empty list',
            '        projection',
            '            options',
            '                columns 2',
        ])
        if not tab_cards:
            lines.append('                panels empty list')
        else:
            lines.append('                panels')
            for c_idx, card in enumerate(tab_cards):
                c_view_ref = _q(card_view_ids[card['id']])
                lines.extend([
                    '                    item',
                    '                        target',
                    f'                            id {c_view_ref}',
                    '                        kind "view"',
                    f'                        title {_q(card["title"])}',
                    '                        layout',
                    f'                            row {c_idx // 2}',
                    f'                            column {c_idx % 2}',
                ])
        lines.append('')

    include_ids = [
        root_id,
        *[e[0] for e in elements],
        *[r[0] for r in relations],
    ]
    lines.extend([
        f'view "dashboard_wiring" as {_q(BI_ANALYTICS_PROFILE)}',
        '    with',
        '        id "dashboard_wiring"',
        f'        title {_q(dashboard["name"] + " — Wiring & Lineage")}',
        '        selection',
        '            include',
    ])
    for inc_id in include_ids:
        lines.extend([
            '                item',
            f'                    id {_q(inc_id)}',
        ])
    lines.append('')

    return '\n'.join(lines).rstrip() + '\n', id_map


def ddn_to_dashboard(ddn_text: str) -> dict[str, Any]:
    """Parse a BI Dashboard DDN document back to its canonical model."""
    blocks = _parse_blocks(ddn_text)
    positions: dict[str, dict[str, float]] = {}
    envelope: dict[str, Any] | None = None
    for blk in blocks:
        xrec = _extract_x_record(blk)
        if xrec is None or xrec.get('module') != BI_DASHBOARD_MODULE:
            continue
        rec = xrec.get('record') or {}
        subj = rec.get('subject_id')
        if subj and 'pos_x' in rec and 'pos_y' in rec:
            try:
                positions[subj] = {
                    'x': float(rec['pos_x']),
                    'y': float(rec['pos_y']),
                }
            except (TypeError, ValueError):
                pass
        if xrec.get('block') == 'dashboard_root' and rec.get('envelope_json'):
            envelope = json.loads(str(rec['envelope_json']))
    if envelope is None:
        raise DesignStoreError(
            'DDN document does not contain a scratchrobin.bi.dashboard@1 '
            'dashboard envelope'
        )
    dashboard = validate_bi_dashboard(envelope['dashboard'])
    return {
        'dashboard': dashboard,
        'dashboard_notes': str(envelope.get('dashboard_notes') or ''),
        'element_ids': dict(envelope.get('element_ids') or {}),
        'layout_positions': positions,
    }


# ---------------------------------------------------------------------------
# Clean-Room Superset ZIP & Metabase Bundle Importers (E10)
# ---------------------------------------------------------------------------


def _load_structured_doc(raw_bytes: bytes, filename: str) -> Any:
    text = raw_bytes.decode('utf-8')
    if filename.endswith('.json'):
        return json.loads(text)
    if _yaml is not None:
        return _yaml.safe_load(text)
    return json.loads(text)


def _parse_superset_zip_entries(
    bundle: bytes | Mapping[str, Any],
) -> dict[str, Any]:
    if isinstance(bundle, Mapping):
        return copy.deepcopy(dict(bundle))
    if not isinstance(bundle, (bytes, bytearray)):
        raise DesignStoreError('Superset bundle must be ZIP bytes or a dict')
    datasets: dict[str, dict[str, Any]] = {}
    charts: dict[str, dict[str, Any]] = {}
    dashboards: dict[str, dict[str, Any]] = {}
    with zipfile.ZipFile(io.BytesIO(bundle), 'r') as zf:
        for info in zf.infolist():
            if info.is_dir() or '..' in info.filename:
                continue
            if not info.filename.endswith(('.yaml', '.yml', '.json')):
                continue
            doc = _load_structured_doc(zf.read(info.filename), info.filename)
            if not isinstance(doc, Mapping):
                continue
            parts = info.filename.strip('/').split('/')
            section = parts[1] if len(parts) >= 3 else parts[0]
            uid = str(doc.get('uuid') or info.filename)
            if section == 'datasets' or 'table_name' in doc:
                datasets[uid] = dict(doc)
            elif section == 'charts' or 'viz_type' in doc:
                charts[uid] = dict(doc)
            elif section == 'dashboards' or 'position' in doc:
                dashboards[uid] = dict(doc)
    return {
        'datasets': list(datasets.values()),
        'charts': list(charts.values()),
        'dashboards': list(dashboards.values()),
    }


def _parse_metabase_entries(
    bundle: bytes | Mapping[str, Any],
) -> dict[str, Any]:
    if isinstance(bundle, Mapping):
        return copy.deepcopy(dict(bundle))
    if not isinstance(bundle, (bytes, bytearray)):
        raise DesignStoreError('Metabase bundle must be archive/JSON/YAML')
    raw = bytes(bundle)
    if zipfile.is_zipfile(io.BytesIO(raw)):
        cards, dashboards, tables = [], [], {}
        with zipfile.ZipFile(io.BytesIO(raw), 'r') as zf:
            for info in zf.infolist():
                if info.is_dir() or '..' in info.filename:
                    continue
                if not info.filename.endswith(('.yaml', '.yml', '.json')):
                    continue
                doc = _load_structured_doc(
                    zf.read(info.filename), info.filename
                )
                if not isinstance(doc, Mapping):
                    continue
                if 'dataset_query' in doc:
                    cards.append(dict(doc))
                elif 'dashcards' in doc or 'ordered_cards' in doc:
                    dashboards.append(dict(doc))
                elif doc.get('cards') or doc.get('dashboards'):
                    cards.extend(doc.get('cards') or [])
                    dashboards.extend(doc.get('dashboards') or [])
                    tables.update(doc.get('tables') or {})
        return {'cards': cards, 'dashboards': dashboards, 'tables': tables}
    if raw[:2] == b'\x1f\x8b':
        cards, dashboards = [], []
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as tf:
            for member in tf.getmembers():
                if not member.isfile() or '..' in member.name:
                    continue
                if not member.name.endswith(('.yaml', '.yml', '.json')):
                    continue
                extracted = tf.extractfile(member)
                if extracted is None:
                    continue
                doc = _load_structured_doc(extracted.read(), member.name)
                if isinstance(doc, Mapping):
                    if 'dataset_query' in doc:
                        cards.append(dict(doc))
                    elif 'dashcards' in doc or 'ordered_cards' in doc:
                        dashboards.append(dict(doc))
        return {'cards': cards, 'dashboards': dashboards, 'tables': {}}
    doc = _load_structured_doc(raw, 'bundle.yaml')
    if not isinstance(doc, Mapping):
        raise DesignStoreError('Unsupported Metabase bundle structure')
    return dict(doc)


# ---------------------------------------------------------------------------
# Runtime Outward Effects & Remote Dashboard Server Store Helpers (E4, E9)
# ---------------------------------------------------------------------------

_RUNTIME_BI_DDL = """
CREATE TABLE IF NOT EXISTS bi_outward_effect (
    id TEXT PRIMARY KEY,
    design_id TEXT NOT NULL REFERENCES design(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    effect_kind TEXT NOT NULL
        CHECK (effect_kind IN ('subscription', 'embed', 'dashboard_server')),
    enabled INTEGER NOT NULL DEFAULT 0,
    publisher_user_id INTEGER,
    reviewed_by INTEGER NOT NULL,
    reviewed_at TEXT NOT NULL,
    config_json TEXT NOT NULL,
    exposure_diff_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_bi_outward_effect_design
    ON bi_outward_effect (design_id, effect_kind);
"""


def _ensure_bi_runtime_tables(store: DesignStore) -> None:
    conn = store._connect()
    try:
        conn.executescript(_RUNTIME_BI_DDL)
        conn.commit()
    finally:
        conn.close()


def _compute_outward_exposure_diff(
    effect_kind: str,
    previous_config: Mapping[str, Any] | None,
    proposed_config: Mapping[str, Any],
    *,
    previous_redact: list[str] | None = None,
    current_redact: list[str] | None = None,
) -> dict[str, Any]:
    prev = dict(previous_config or {})
    prop = dict(proposed_config or {})
    warnings: list[dict[str, Any]] = []

    prev_recips = set(prev.get('recipients') or [])
    prop_recips = set(prop.get('recipients') or [])
    added_recips = sorted(prop_recips - prev_recips)
    if added_recips:
        warnings.append({
            'code': 'added_recipients',
            'severity': 'warning',
            'detail': f'New outward recipients: {", ".join(added_recips)}',
        })

    prev_hooks = set(prev.get('webhooks') or [])
    prop_hooks = set(prop.get('webhooks') or [])
    added_hooks = sorted(prop_hooks - prev_hooks)
    if added_hooks:
        warnings.append({
            'code': 'added_webhooks',
            'severity': 'warning',
            'detail': f'New webhook destinations: {", ".join(added_hooks)}',
        })

    if (
        effect_kind in ('embed', 'dashboard_server')
        and not prev.get('enabled')
    ):
        warnings.append({
            'code': f'{effect_kind}_enabled',
            'severity': 'warning',
            'detail': (
                f'Outward {effect_kind} exposure is being switched on '
                f'explicitly.'
            ),
        })

    if previous_redact is not None and current_redact is not None:
        removed_redact = sorted(set(previous_redact) - set(current_redact))
        if removed_redact:
            warnings.append({
                'code': 'loosened_redaction',
                'severity': 'warning',
                'detail': (
                    'Columns no longer redacted: ' + ', '.join(removed_redact)
                ),
            })

    return {
        'effect_kind': effect_kind,
        'added_recipients': added_recips,
        'added_webhooks': added_hooks,
        'warnings': warnings,
    }


def _b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


def _b64u_decode(token_part: str) -> bytes:
    pad = '=' * (-len(token_part) % 4)
    return base64.urlsafe_b64decode(token_part + pad)


def _narrow_filter_value(locked_val: Any, requested_val: Any, key: str) -> Any:
    """Enforce E9: device tokens can only narrow filters, never widen them."""
    if requested_val is None:
        return copy.deepcopy(locked_val)
    if isinstance(locked_val, list):
        allowed = list(locked_val)
        req_items = (
            requested_val
            if isinstance(requested_val, list)
            else [requested_val]
        )
        narrowed = [item for item in req_items if item in allowed]
        if not narrowed:
            raise DesignStoreForbidden(
                f'Requested filter {key!r} widens beyond device token scope'
            )
        return narrowed
    if isinstance(requested_val, list):
        if len(requested_val) == 1 and requested_val[0] == locked_val:
            return copy.deepcopy(locked_val)
        raise DesignStoreForbidden(
            f'Requested filter {key!r} widens locked value'
        )
    if requested_val != locked_val:
        raise DesignStoreForbidden(
            f'Requested filter {key!r} conflicts with locked device filter'
        )
    return copy.deepcopy(locked_val)


class BIDesignSync:
    """Coordinate BI Question & Dashboard designs, outward review & imports."""

    def __init__(
        self,
        store: DesignStore,
        process: StoreDDNProcess | None = None,
        *,
        token_secret: str = 'scratchrobin-bi-device-secret',
    ):
        self.store = store
        self.process = process or StoreDDNProcess(store)
        self.token_secret = token_secret
        _ensure_bi_runtime_tables(self.store)

    @staticmethod
    def _require_human(actor_kind: str, action_label: str) -> None:
        """Enforce E8: agents/AI principals never accept, merge or publish."""
        if str(actor_kind or 'human').lower() != 'human':
            raise DesignStoreForbidden(
                f'AI or automated agents cannot {action_label}; a human '
                f'reviewer must perform this step'
            )

    def create_question(
        self,
        *,
        project_id: str,
        key: str,
        title: str,
        actor_id: int,
        question: Mapping[str, Any] | None = None,
        endpoint_id: str = 'default-endpoint',
        note: str = '',
    ) -> dict[str, Any]:
        q_model = validate_bi_question(
            question or default_question_model(
                name=title, endpoint_id=endpoint_id
            )
        )
        q_model['name'] = title.strip() or q_model['name']
        ddn_text, id_map = question_to_ddn(q_model)
        design = self.store.create_design(
            project_id=project_id,
            key=key,
            kind='question',
            title=q_model['name'],
            ddn_text=ddn_text,
            actor_id=actor_id,
            status='draft',
            note=note or 'Created BI question design',
            origin='local',
            observe_resources=True,
        )
        return {'design': design, 'question': q_model, 'element_ids': id_map}

    def save_question(
        self,
        design_id: str,
        *,
        expected_head_version: int,
        actor_id: int,
        question: Mapping[str, Any] | None = None,
        ddn_text: str | None = None,
        question_notes: str = '',
        pinned_positions: Mapping[str, Mapping[str, float]] | None = None,
        status: str = 'draft',
        note: str = '',
    ) -> dict[str, Any]:
        current = self.store.get_design(design_id)
        if current['kind'] != 'question':
            raise DesignStoreError(f'Design {design_id!r} is not a question')
        prev_parsed = ddn_to_question(current['version']['ddn_text'])
        merged_pos = {
            **prev_parsed['layout_positions'],
            **dict(pinned_positions or {}),
        }
        if ddn_text is not None and question is None:
            parsed = ddn_to_question(ddn_text)
            q_model = parsed['question']
            final_ddn = ddn_text
        else:
            q_model = validate_bi_question(
                question or prev_parsed['question']
            )
            # Verification tier drops back to draft when query logic changes.
            if q_model['query'] != prev_parsed['question']['query']:
                q_model['verification_tier'] = 'draft'
            final_ddn, _ = question_to_ddn(
                q_model,
                element_ids=prev_parsed['element_ids'],
                layout_positions=merged_pos,
                question_notes=(
                    question_notes or prev_parsed['question_notes']
                ),
            )
        eff_base = (
            current['version']['base_version']
            if current['version']['status'] != 'accepted'
            else current.get('active_version')
        )
        saved = self.process.save_from_ddn(
            design_id,
            expected_head_version=expected_head_version,
            ddn_or_workspace=final_ddn,
            actor_id=actor_id,
            base_version=eff_base,
            pinned_positions=dict(pinned_positions or {}),
            status=status,
            note=note or 'Saved BI question design',
            observe_resources=True,
        )
        return {'saved': saved, 'question': q_model}

    def create_dashboard(
        self,
        *,
        project_id: str,
        key: str,
        title: str,
        actor_id: int,
        dashboard: Mapping[str, Any] | None = None,
        note: str = '',
    ) -> dict[str, Any]:
        d_model = validate_bi_dashboard(
            dashboard or default_dashboard_model(name=title)
        )
        d_model['name'] = title.strip() or d_model['name']
        ddn_text, id_map = dashboard_to_ddn(d_model)
        design = self.store.create_design(
            project_id=project_id,
            key=key,
            kind='dashboard',
            title=d_model['name'],
            ddn_text=ddn_text,
            actor_id=actor_id,
            status='draft',
            note=note or 'Created BI dashboard design',
            origin='local',
        )
        self._sync_dashboard_dependencies(
            design['id'], design['head_version'], d_model
        )
        return {
            'design': design,
            'dashboard': d_model,
            'element_ids': id_map,
        }

    def save_dashboard(
        self,
        design_id: str,
        *,
        expected_head_version: int,
        actor_id: int,
        dashboard: Mapping[str, Any] | None = None,
        ddn_text: str | None = None,
        dashboard_notes: str = '',
        pinned_positions: Mapping[str, Mapping[str, float]] | None = None,
        status: str = 'draft',
        note: str = '',
    ) -> dict[str, Any]:
        current = self.store.get_design(design_id)
        if current['kind'] != 'dashboard':
            raise DesignStoreError(f'Design {design_id!r} is not a dashboard')
        prev_parsed = ddn_to_dashboard(current['version']['ddn_text'])
        merged_pos = {
            **prev_parsed['layout_positions'],
            **dict(pinned_positions or {}),
        }
        if ddn_text is not None and dashboard is None:
            parsed = ddn_to_dashboard(ddn_text)
            d_model = parsed['dashboard']
            final_ddn = ddn_text
        else:
            d_model = validate_bi_dashboard(
                dashboard or prev_parsed['dashboard']
            )
            final_ddn, _ = dashboard_to_ddn(
                d_model,
                element_ids=prev_parsed['element_ids'],
                layout_positions=merged_pos,
                dashboard_notes=(
                    dashboard_notes or prev_parsed['dashboard_notes']
                ),
            )
        eff_base = (
            current['version']['base_version']
            if current['version']['status'] != 'accepted'
            else current.get('active_version')
        )
        saved = self.process.save_from_ddn(
            design_id,
            expected_head_version=expected_head_version,
            ddn_or_workspace=final_ddn,
            actor_id=actor_id,
            base_version=eff_base,
            pinned_positions=dict(pinned_positions or {}),
            status=status,
            note=note or 'Saved BI dashboard design',
        )
        new_ver = saved['design']['head_version']
        self._sync_dashboard_dependencies(design_id, new_ver, d_model)
        return {'saved': saved, 'dashboard': d_model}

    def _sync_dashboard_dependencies(
        self,
        dashboard_design_id: str,
        version: int,
        dashboard_model: Mapping[str, Any],
    ) -> None:
        deps: dict[str, dict[str, Any]] = {}
        for card in dashboard_model.get('cards') or []:
            if card.get('type') != 'question':
                continue
            q_info = card['question']
            q_did = q_info['question_design_id']
            if q_did == dashboard_design_id:
                continue
            try:
                q_rec = self.store.get_design(q_did)
            except DesignStoreNotFound:
                continue
            pinned = (
                None
                if q_info.get('follow_latest_accepted')
                else (
                    q_info.get('pinned_version')
                    or q_rec.get('active_version')
                    or q_rec.get('head_version')
                )
            )
            deps[q_did] = {
                'depends_on_design_id': q_did,
                'depends_on_version': pinned,
            }
        if deps:
            self.store.set_dependencies(
                dashboard_design_id, version, list(deps.values())
            )

    def accept_bi_design(
        self,
        design_id: str,
        version: int,
        actor_id: int,
        *,
        approval_ref: str | None = None,
        authorized: bool = True,
        actor_kind: str = 'human',
    ) -> dict[str, Any]:
        """Accept a BI question or dashboard without switching outward effects.

        Enforces E4 and E8.
        """
        self._require_human(actor_kind, 'accept BI design versions')
        record = self.store.get_design(design_id, version=version)
        if record['kind'] not in ('question', 'dashboard'):
            raise DesignStoreError(
                f'Design {design_id!r} is kind {record["kind"]!r}, not BI'
            )
        if record['kind'] == 'dashboard':
            parsed = ddn_to_dashboard(record['version']['ddn_text'])
            for card in parsed['dashboard']['cards']:
                if card['type'] != 'question':
                    continue
                q_did = card['question']['question_design_id']
                try:
                    q_doc = self.store.get_design(q_did)
                except DesignStoreNotFound as exc:
                    raise DesignStoreConflict(
                        f'Dashboard references missing question design '
                        f'{q_did!r}'
                    ) from exc
                if q_doc.get('active_version') is None:
                    raise DesignStoreConflict(
                        f'Referenced question {q_doc["title"]!r} ({q_did}) '
                        f'must be accepted before accepting this dashboard'
                    )
        accepted = self.store.accept_version(
            design_id,
            version,
            actor_id,
            approval_ref=approval_ref,
            authorized=authorized,
        )
        return {
            'design': accepted,
            'outward_effects_activated': False,
            'active_outward_effects': self.list_outward_effects(
                design_id, only_enabled=True
            ),
        }

    # ------------------------------------------------------------------
    # Outward Effect Review & Remote Dashboard Server (E4, E9)
    # ------------------------------------------------------------------

    def list_outward_effects(
        self,
        design_id: str,
        *,
        only_enabled: bool = False,
    ) -> list[dict[str, Any]]:
        conn = self.store._connect()
        try:
            sql = 'SELECT * FROM bi_outward_effect WHERE design_id = ?'
            params: list[Any] = [design_id]
            if only_enabled:
                sql += ' AND enabled = 1'
            sql += ' ORDER BY reviewed_at DESC, id ASC'
            rows = conn.execute(sql, params).fetchall()
            out = []
            for row in rows:
                item = dict(row)
                item['enabled'] = bool(item['enabled'])
                item['config'] = json.loads(item.pop('config_json'))
                item['exposure_diff'] = json.loads(
                    item.pop('exposure_diff_json')
                )
                out.append(item)
            return out
        finally:
            conn.close()

    def review_outward_effect(
        self,
        design_id: str,
        *,
        effect_kind: str,
        enabled: bool,
        config: Mapping[str, Any] | None,
        reviewer_id: int,
        publisher_user_id: int | None = None,
        authorized: bool = True,
        actor_kind: str = 'human',
    ) -> dict[str, Any]:
        """Separate reviewed switch for subscriptions, embeds & server (E4)."""
        self._require_human(actor_kind, 'approve outward BI effects')
        if not authorized:
            raise DesignStoreForbidden(
                'Caller is not authorized to review outward BI exposure'
            )
        if effect_kind not in OUTWARD_EFFECT_KINDS:
            raise DesignStoreError(
                f'Unsupported outward effect_kind: {effect_kind!r}'
            )
        design = self.store.get_design(design_id)
        active_ver = design.get('active_version')
        if active_ver is None:
            raise DesignStoreConflict(
                'Design must have an accepted active version before '
                'configuring outward effects'
            )
        if effect_kind == 'dashboard_server':
            if design['kind'] != 'dashboard':
                raise DesignStoreError(
                    'Only dashboard designs can publish to the remote '
                    'dashboard server'
                )
            if enabled and (
                isinstance(publisher_user_id, bool)
                or not isinstance(publisher_user_id, int)
            ):
                raise DesignStoreError(
                    'Remote dashboard server publication requires an explicit '
                    'publisher_user_id'
                )

        existing = [
            e for e in self.list_outward_effects(design_id)
            if e['effect_kind'] == effect_kind
        ]
        prev_cfg = existing[0]['config'] if existing else None
        cfg_dict = copy.deepcopy(dict(config or {}))
        cfg_dict['enabled'] = bool(enabled)
        exposure_diff = _compute_outward_exposure_diff(
            effect_kind, prev_cfg, cfg_dict
        )
        effect_id = existing[0]['id'] if existing else uuid7()
        now = _utc_now()

        conn = self.store._connect()
        try:
            conn.execute(
                """
                INSERT INTO bi_outward_effect (
                    id, design_id, version, effect_kind, enabled,
                    publisher_user_id, reviewed_by, reviewed_at,
                    config_json, exposure_diff_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    version = excluded.version,
                    enabled = excluded.enabled,
                    publisher_user_id = excluded.publisher_user_id,
                    reviewed_by = excluded.reviewed_by,
                    reviewed_at = excluded.reviewed_at,
                    config_json = excluded.config_json,
                    exposure_diff_json = excluded.exposure_diff_json
                """,
                (
                    effect_id,
                    design_id,
                    int(active_ver),
                    effect_kind,
                    1 if enabled else 0,
                    publisher_user_id,
                    reviewer_id,
                    now,
                    _json_str(cfg_dict),
                    _json_str(exposure_diff),
                ),
            )
            conn.commit()
        finally:
            conn.close()

        return {
            'id': effect_id,
            'design_id': design_id,
            'version': int(active_ver),
            'effect_kind': effect_kind,
            'enabled': bool(enabled),
            'publisher_user_id': publisher_user_id,
            'reviewed_by': reviewer_id,
            'reviewed_at': now,
            'config': cfg_dict,
            'exposure_diff': exposure_diff,
        }

    def publish_to_dashboard_server(
        self,
        dashboard_design_id: str,
        *,
        publisher_user_id: int,
        reviewer_id: int,
        locked_filters: Mapping[str, Any] | None = None,
        authorized: bool = True,
        actor_kind: str = 'human',
    ) -> dict[str, Any]:
        """Publish an accepted dashboard under an explicit identity (E9)."""
        return self.review_outward_effect(
            dashboard_design_id,
            effect_kind='dashboard_server',
            enabled=True,
            config={
                'display_only': True,
                'locked_filters': copy.deepcopy(dict(locked_filters or {})),
            },
            reviewer_id=reviewer_id,
            publisher_user_id=publisher_user_id,
            authorized=authorized,
            actor_kind=actor_kind,
        )

    def mint_device_token(
        self,
        publication_id: str,
        *,
        device_label: str = 'kiosk',
        locked_filters: Mapping[str, Any] | None = None,
        expires_at: str | None = None,
    ) -> str:
        """Mint an HMAC-SHA256 display-only remote device token (E9)."""
        conn = self.store._connect()
        try:
            row = conn.execute(
                'SELECT * FROM bi_outward_effect WHERE id = ? '
                "AND effect_kind = 'dashboard_server' AND enabled = 1",
                (publication_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            raise DesignStoreNotFound(
                f'Active dashboard-server publication {publication_id!r} '
                f'was not found'
            )
        pub_cfg = json.loads(row['config_json'])
        base_locked = dict(pub_cfg.get('locked_filters') or {})
        merged_locked = dict(base_locked)
        for k, v in (locked_filters or {}).items():
            if k in base_locked:
                merged_locked[k] = _narrow_filter_value(base_locked[k], v, k)
            else:
                merged_locked[k] = copy.deepcopy(v)

        claims = {
            'pub': publication_id,
            'did': row['design_id'],
            'ver': int(row['version']),
            'uid': int(row['publisher_user_id']),
            'dev': str(device_label or 'kiosk')[:64],
            'ro': True,
            'flt': merged_locked,
            'exp': expires_at,
        }
        payload_b64 = _b64u_encode(_json_str(claims).encode('utf-8'))
        sig = hmac.new(
            self.token_secret.encode('utf-8'),
            payload_b64.encode('ascii'),
            hashlib.sha256,
        ).digest()
        return f'{payload_b64}.{_b64u_encode(sig)}'

    def verify_device_token(self, token: str) -> dict[str, Any]:
        """Verify an HMAC device token and check active publication status."""
        if not isinstance(token, str) or '.' not in token:
            raise DesignStoreForbidden('Invalid device token format')
        payload_b64, sig_b64 = token.split('.', 1)
        expected_sig = hmac.new(
            self.token_secret.encode('utf-8'),
            payload_b64.encode('ascii'),
            hashlib.sha256,
        ).digest()
        try:
            actual_sig = _b64u_decode(sig_b64)
        except Exception as exc:
            raise DesignStoreForbidden('Malformed device token') from exc
        if not hmac.compare_digest(expected_sig, actual_sig):
            raise DesignStoreForbidden('Device token signature is invalid')
        claims = json.loads(_b64u_decode(payload_b64).decode('utf-8'))
        if claims.get('ro') is not True:
            raise DesignStoreForbidden('Device token must be display-only')
        if claims.get('exp'):
            if str(claims['exp']) < _utc_now():
                raise DesignStoreForbidden('Device token has expired')
        conn = self.store._connect()
        try:
            row = conn.execute(
                'SELECT * FROM bi_outward_effect WHERE id = ? '
                "AND effect_kind = 'dashboard_server' AND enabled = 1",
                (claims['pub'],),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            raise DesignStoreForbidden(
                'Dashboard server publication has been disabled or revoked'
            )
        return claims

    def render_dashboard_server_view(
        self,
        publication_id: str,
        *,
        device_token: str,
        requested_filters: Mapping[str, Any] | None = None,
        view_id: str | None = None,
    ) -> dict[str, Any]:
        """Serve a display-only dashboard view with narrowing-only filters."""
        claims = self.verify_device_token(device_token)
        if claims['pub'] != publication_id:
            raise DesignStoreForbidden(
                'Device token does not match the requested publication'
            )
        locked = dict(claims.get('flt') or {})
        effective_filters: dict[str, Any] = dict(locked)
        for key, val in (requested_filters or {}).items():
            if key in locked:
                effective_filters[key] = _narrow_filter_value(
                    locked[key], val, key
                )
            else:
                effective_filters[key] = copy.deepcopy(val)
        session = self.process.open_session(
            claims['did'],
            version=claims['ver'],
            active_only=True,
            view_id=view_id or 'dashboard_composed',
        )
        return {
            'publication_id': publication_id,
            'display_only': True,
            'publisher_user_id': claims['uid'],
            'device_label': claims['dev'],
            'effective_filters': effective_filters,
            'capabilities': {
                'can_edit': False,
                'can_export': False,
                'can_open_sql': False,
                'can_accept': False,
            },
            'session': session,
        }

    # ------------------------------------------------------------------
    # Optional BYOK AI Drafting (E8)
    # ------------------------------------------------------------------

    def propose_ai_draft(
        self,
        *,
        project_id: str,
        prompt: str,
        actor_id: int,
        endpoint_id: str = 'default-endpoint',
        schema_hint: Mapping[str, Any] | None = None,
        target_design_id: str | None = None,
        byok_api_key: str | None = None,
        byok_completer: (
            Callable[[str, Mapping[str, Any]], dict[str, Any]] | None
        ) = None,
    ) -> dict[str, Any]:
        """Search existing questions first, then draft a question or diff (E8).

        Never stores ``byok_api_key`` and never accepts, merges or publishes.
        """
        prompt_clean = str(prompt or '').strip()
        if not prompt_clean:
            raise DesignStoreError('AI draft prompt is required')
        if byok_completer is None and not (byok_api_key or '').strip():
            raise DesignStoreError(
                'Bring-your-own-key (byok_api_key) is required when optional '
                'AI drafting is invoked'
            )

        existing_matches = self.store.search(
            prompt_clean, project_id=project_id, kind='question'
        )
        context = {
            'existing_questions': [
                {'id': m['id'], 'key': m['key'], 'title': m['title']}
                for m in existing_matches[:10]
            ],
            'schema_hint': copy.deepcopy(dict(schema_hint or {})),
        }

        if byok_completer is not None:
            proposed_raw = byok_completer(prompt_clean, context)
        else:
            tables = list((schema_hint or {}).get('tables') or [])
            first_tbl = tables[0] if tables else {
                'relation': ['main', 'orders'],
                'columns': ['region', 'amount'],
            }
            rel = _rel_parts(first_tbl.get('relation') or ['main', 'orders'])
            tcols = list(first_tbl.get('columns') or ['id'])
            dim_col = str(tcols[0])
            num_col = str(tcols[1]) if len(tcols) > 1 else None
            proposed_raw = default_question_model(
                name=prompt_clean[:80],
                endpoint_id=endpoint_id,
                sbsql={
                    'from': {'relation': rel, 'alias': rel[-1]},
                    'columns': [
                        {'column': [rel[-1], dim_col], 'alias': dim_col}
                    ],
                    'measures': [
                        {
                            'function': 'sum' if num_col else 'count',
                            'column': (
                                [rel[-1], num_col] if num_col else None
                            ),
                            'alias': (
                                f'sum_{num_col}' if num_col else 'row_count'
                            ),
                        }
                    ],
                    'limit': 100,
                },
            )

        q_model = validate_bi_question(proposed_raw)
        q_model['verification_tier'] = 'draft'

        if target_design_id is not None:
            current = self.store.get_design(target_design_id)
            prev_parsed = ddn_to_question(current['version']['ddn_text'])
            draft_ddn, _ = question_to_ddn(
                q_model,
                element_ids=prev_parsed['element_ids'],
                layout_positions=prev_parsed['layout_positions'],
                question_notes=f'AI draft from prompt: {prompt_clean}',
            )
            saved = self.process.save_from_ddn(
                target_design_id,
                expected_head_version=current['head_version'],
                ddn_or_workspace=draft_ddn,
                actor_id=actor_id,
                status='draft',
                origin='ai:draft',
                note=(
                    f'AI draft proposal for human review: '
                    f'{prompt_clean[:80]}'
                ),
            )
            return {
                'mode': 'draft_diff',
                'existing_matches': existing_matches,
                'design': saved['design'],
                'diff': saved.get('diff'),
                'question': q_model,
                'requires_human_review': True,
            }

        slug = _safe_ident(prompt_clean[:32], 'question')
        draft_key = f'ai_draft_{slug}_{uuid7()[:8]}'
        ddn_text, _ = question_to_ddn(
            q_model,
            question_notes=f'AI draft from prompt: {prompt_clean}',
        )
        created = self.store.create_design(
            project_id=project_id,
            key=draft_key,
            kind='question',
            title=q_model['name'],
            ddn_text=ddn_text,
            actor_id=actor_id,
            status='draft',
            origin='ai:draft',
            note=(
                f'AI draft proposal for human review: '
                f'{prompt_clean[:80]}'
            ),
            observe_resources=True,
        )
        return {
            'mode': 'new_draft',
            'existing_matches': existing_matches,
            'design': created,
            'question': q_model,
            'requires_human_review': True,
        }

    # ------------------------------------------------------------------
    # Superset & Metabase Importers -> Draft DDN + Loss Report (E10)
    # ------------------------------------------------------------------

    def import_superset_zip(
        self,
        bundle: bytes | Mapping[str, Any],
        *,
        project_id: str,
        actor_id: int,
        endpoint_id: str = 'default-endpoint',
        key_prefix: str = 'superset',
    ) -> dict[str, Any]:
        """Import an Apache Superset UUID-keyed YAML ZIP into Draft DDN."""
        cleaned, stripped_fields = _strip_sensitive_fields(
            _parse_superset_zip_entries(bundle)
        )
        losses: list[dict[str, Any]] = [
            {
                'code': 'credential_excluded',
                'severity': 'info',
                'detail': f'Excluded sensitive field {path} from DDN import',
            }
            for path in stripped_fields
        ]
        datasets_by_uuid = {
            str(ds.get('uuid') or ds.get('table_name')): ds
            for ds in (cleaned.get('datasets') or [])
            if isinstance(ds, Mapping)
        }
        chart_design_map: dict[str, dict[str, Any]] = {}
        imported_questions: list[dict[str, Any]] = []

        for idx, chart in enumerate(cleaned.get('charts') or []):
            if not isinstance(chart, Mapping):
                continue
            c_uuid = str(chart.get('uuid') or f'chart_{idx + 1}')
            c_title = str(
                chart.get('slice_name') or chart.get('name') or c_uuid
            )
            raw_viz = str(chart.get('viz_type') or 'table')
            mapped_viz = _SUPERSET_VIZ_MAP.get(raw_viz)
            chart_losses: list[dict[str, Any]] = []
            if mapped_viz is None:
                mapped_viz = 'table'
                chart_losses.append({
                    'code': 'unsupported_viz_type',
                    'severity': 'warning',
                    'detail': (
                        f'Superset viz_type {raw_viz!r} mapped to table'
                    ),
                })

            params_obj = chart.get('params') or {}
            if isinstance(params_obj, str):
                try:
                    params_obj = json.loads(params_obj)
                except Exception:
                    params_obj = {}
            ds_uuid = str(chart.get('dataset_uuid') or '')
            ds = datasets_by_uuid.get(ds_uuid) or {}
            schema_name = str(ds.get('schema') or 'main')
            table_name = str(ds.get('table_name') or 'imported_dataset')
            custom_sql = str(ds.get('sql') or '').strip()

            q_params: list[dict[str, Any]] = []
            if custom_sql:
                def _replace_jinja(match: re.Match[str]) -> str:
                    pname = _safe_ident(match.group(1), 'param')
                    default_v = match.group(2)
                    pdef: dict[str, Any] = {
                        'id': pname,
                        'name': pname,
                        'type': 'string',
                        'required': False,
                    }
                    if default_v is not None:
                        pdef['default'] = default_v
                    if not any(p['id'] == pname for p in q_params):
                        q_params.append(pdef)
                    return '{{' + pname + '}}'

                converted_sql = _JINJA_PARAM_RE.sub(_replace_jinja, custom_sql)
                if _JINJA_BLOCK_RE.search(converted_sql):
                    chart_losses.append({
                        'code': 'jinja_template_untranslated',
                        'severity': 'warning',
                        'detail': (
                            'Complex Superset Jinja macros could not be '
                            'translated automatically; review SQL draft.'
                        ),
                    })
                    converted_sql = _JINJA_BLOCK_RE.sub('NULL', converted_sql)
                q_model = default_question_model(
                    name=c_title,
                    endpoint_id=endpoint_id,
                    raw_sql=converted_sql,
                    parameters=q_params,
                    visualization={'type': mapped_viz},
                )
            else:
                groupby = [
                    str(g) for g in (params_obj.get('groupby') or [])
                    if isinstance(g, str) and g.strip()
                ]
                metrics_raw = params_obj.get('metrics') or []
                measures: list[dict[str, Any]] = []
                for m_i, m in enumerate(metrics_raw):
                    if isinstance(m, Mapping):
                        agg = str(
                            m.get('aggregate') or 'count'
                        ).lower()
                        col_d = m.get('column') or {}
                        cname = (
                            col_d.get('column_name')
                            if isinstance(col_d, Mapping)
                            else None
                        )
                        if agg not in (
                            'sum', 'count', 'count_distinct',
                            'min', 'max', 'avg',
                        ):
                            chart_losses.append({
                                'code': 'unsupported_metric_aggregate',
                                'severity': 'warning',
                                'detail': (
                                    f'Aggregate {agg!r} mapped to count'
                                ),
                            })
                            agg = 'count'
                            cname = None
                        measures.append({
                            'function': agg,
                            'column': (
                                [table_name, str(cname)] if cname else None
                            ),
                            'alias': _safe_ident(
                                m.get('label') or f'm_{m_i + 1}', 'metric'
                            ),
                        })
                    elif isinstance(m, str):
                        measures.append({
                            'function': 'count',
                            'column': None,
                            'alias': _safe_ident(m, 'metric'),
                        })
                if not groupby and not measures:
                    measures = [{
                        'function': 'count',
                        'column': None,
                        'alias': 'row_count',
                    }]
                sbsql_filters: list[dict[str, Any]] = []
                for flt in params_obj.get('adhoc_filters') or []:
                    if not isinstance(flt, Mapping):
                        continue
                    subj = flt.get('subject')
                    op_raw = str(flt.get('operator') or '==').upper()
                    op_map = {
                        '==': 'eq', '=': 'eq', '!=': 'ne', '<>': 'ne',
                        '<': 'lt', '<=': 'lte', '>': 'gt', '>=': 'gte',
                        'IN': 'in', 'NOT IN': 'not_in',
                    }
                    if subj and op_raw in op_map:
                        sbsql_filters.append({
                            'column': [table_name, str(subj)],
                            'operator': op_map[op_raw],
                            'value': flt.get('comparator'),
                        })
                    else:
                        chart_losses.append({
                            'code': 'unsupported_adhoc_filter',
                            'severity': 'warning',
                            'detail': f'Skipped adhoc filter {op_raw!r}',
                        })
                q_model = default_question_model(
                    name=c_title,
                    endpoint_id=endpoint_id,
                    sbsql={
                        'from': {
                            'relation': [schema_name, table_name],
                            'alias': table_name,
                        },
                        'columns': [
                            {'column': [table_name, g], 'alias': g}
                            for g in groupby
                        ],
                        'measures': measures,
                        'filters': sbsql_filters,
                        'limit': int(params_obj.get('row_limit') or 1000),
                    },
                    visualization={'type': mapped_viz},
                )

            losses.extend(chart_losses)
            q_key = f"{key_prefix}_q_{_safe_ident(c_uuid, 'chart')}"
            q_loss_report = {
                'source_format': 'superset_zip',
                'source_uuid': c_uuid,
                'items': chart_losses,
            }
            ddn_text, _ = question_to_ddn(q_model)
            q_design = self.store.import_ddn(
                project_id=project_id,
                key=q_key,
                kind='question',
                title=c_title,
                ddn_or_workspace=ddn_text,
                actor_id=actor_id,
                origin='import:superset',
                loss_report=q_loss_report,
                observe_resources=True,
                note=f'Imported Superset chart {c_title} as Draft',
            )
            chart_design_map[c_uuid] = {
                'design': q_design,
                'viz': mapped_viz,
                'title': c_title,
            }
            imported_questions.append(q_design)

        imported_dashboards: list[dict[str, Any]] = []
        for d_idx, dash in enumerate(cleaned.get('dashboards') or []):
            if not isinstance(dash, Mapping):
                continue
            d_uuid = str(dash.get('uuid') or f'dash_{d_idx + 1}')
            d_title = str(
                dash.get('dashboard_title') or dash.get('title') or d_uuid
            )
            dash_losses: list[dict[str, Any]] = []
            cards: list[dict[str, Any]] = []
            pos_dict = dash.get('position') or {}
            chart_refs: list[tuple[str, str]] = []
            if isinstance(pos_dict, Mapping):
                for node_id, node in pos_dict.items():
                    if not isinstance(node, Mapping):
                        continue
                    if node.get('type') == 'CHART':
                        meta = node.get('meta') or {}
                        cuuid = str(meta.get('uuid') or '')
                        if cuuid:
                            chart_refs.append((str(node_id), cuuid))
                    elif node.get('type') == 'MARKDOWN':
                        meta = node.get('meta') or {}
                        cards.append({
                            'id': _safe_ident(node_id, 'md'),
                            'tab_id': 'main',
                            'type': 'text',
                            'title': 'Note',
                            'text': {'markdown': str(meta.get('code') or '')},
                            'layout': {
                                'x': 0,
                                'y': len(cards) * 8,
                                'w': 12,
                                'h': 6,
                            },
                        })
            for c_ref in dash.get('charts') or []:
                cuuid = str(
                    c_ref.get('uuid') if isinstance(c_ref, Mapping) else c_ref
                )
                if cuuid and all(
                    cuuid != existing[1] for existing in chart_refs
                ):
                    chart_refs.append((f'card_{len(chart_refs) + 1}', cuuid))

            for c_i, (node_id, cuuid) in enumerate(chart_refs):
                mapped_q = chart_design_map.get(cuuid)
                if mapped_q is None:
                    dash_losses.append({
                        'code': 'missing_chart_uuid',
                        'severity': 'warning',
                        'detail': f'Chart UUID {cuuid} not present in bundle',
                    })
                    continue
                cards.append({
                    'id': _safe_ident(node_id, f'card_{c_i + 1}'),
                    'tab_id': 'main',
                    'type': 'question',
                    'title': mapped_q['title'],
                    'question': {
                        'question_design_id': mapped_q['design']['id'],
                        'pinned_version': 1,
                        'follow_latest_accepted': False,
                    },
                    'visualization': {'type': mapped_q['viz']},
                    'layout': {
                        'x': (c_i % 2) * 12,
                        'y': (c_i // 2) * 8,
                        'w': 12,
                        'h': 8,
                    },
                })

            dash_filters: list[dict[str, Any]] = []
            meta_obj = dash.get('metadata') or {}
            for nf in meta_obj.get('native_filter_configuration') or []:
                if not isinstance(nf, Mapping):
                    continue
                dash_filters.append({
                    'id': _safe_ident(nf.get('id') or nf.get('name'), 'flt'),
                    'name': str(nf.get('name') or 'Filter'),
                    'type': 'string',
                    'widget': 'select',
                    'operator': 'eq',
                })

            losses.extend(dash_losses)
            d_model = default_dashboard_model(
                name=d_title,
                tabs=[{'id': 'main', 'name': 'Overview'}],
                cards=cards,
                filters=dash_filters,
            )
            d_ddn, _ = dashboard_to_ddn(d_model)
            d_key = f"{key_prefix}_d_{_safe_ident(d_uuid, 'dash')}"
            d_design = self.store.import_ddn(
                project_id=project_id,
                key=d_key,
                kind='dashboard',
                title=d_title,
                ddn_or_workspace=d_ddn,
                actor_id=actor_id,
                origin='import:superset',
                loss_report={
                    'source_format': 'superset_zip',
                    'source_uuid': d_uuid,
                    'items': dash_losses,
                },
                note=f'Imported Superset dashboard {d_title} as Draft',
            )
            self._sync_dashboard_dependencies(
                d_design['id'], d_design['head_version'], d_model
            )
            imported_dashboards.append(d_design)

        return {
            'source_format': 'superset_zip',
            'status': 'draft',
            'questions': imported_questions,
            'dashboards': imported_dashboards,
            'loss_report': {
                'source_format': 'superset_zip',
                'loss_count': len(losses),
                'items': losses,
            },
        }

    def import_metabase_bundle(
        self,
        bundle: bytes | Mapping[str, Any],
        *,
        project_id: str,
        actor_id: int,
        endpoint_id: str = 'default-endpoint',
        key_prefix: str = 'metabase',
    ) -> dict[str, Any]:
        """Import a Metabase serialization export into Draft DDN (E10)."""
        cleaned, stripped_fields = _strip_sensitive_fields(
            _parse_metabase_entries(bundle)
        )
        losses: list[dict[str, Any]] = [
            {
                'code': 'credential_excluded',
                'severity': 'info',
                'detail': f'Excluded sensitive field {path} from DDN import',
            }
            for path in stripped_fields
        ]
        if cleaned.get('pulses') or cleaned.get('alerts'):
            losses.append({
                'code': 'pulses_alerts_excluded',
                'severity': 'warning',
                'detail': (
                    'Metabase pulses/alerts are not auto-activated on import '
                    '(configure ScratchRobin outward subscriptions after '
                    'review).'
                ),
            })

        tables_lookup = dict(cleaned.get('tables') or {})
        card_map: dict[str, dict[str, Any]] = {}
        imported_questions: list[dict[str, Any]] = []

        for idx, card in enumerate(
            cleaned.get('cards') or cleaned.get('questions') or []
        ):
            if not isinstance(card, Mapping):
                continue
            cid = str(
                card.get('entity_id') or card.get('id') or f'card_{idx + 1}'
            )
            ctitle = str(card.get('name') or cid)
            display = str(card.get('display') or 'table')
            mapped_viz = _METABASE_DISPLAY_MAP.get(display)
            card_losses: list[dict[str, Any]] = []
            if mapped_viz is None:
                mapped_viz = 'table'
                card_losses.append({
                    'code': 'unsupported_display',
                    'severity': 'warning',
                    'detail': f'Metabase display {display!r} mapped to table',
                })

            ds_query = card.get('dataset_query') or {}
            qtype = str(ds_query.get('type') or 'query')
            if qtype == 'native':
                native_obj = ds_query.get('native') or {}
                raw_sql = str(native_obj.get('query') or 'SELECT 1 AS val')
                tags = native_obj.get('template-tags') or {}
                q_params: list[dict[str, Any]] = []
                for tname, tspec in (
                    tags.items() if isinstance(tags, Mapping) else ()
                ):
                    tspec_d = tspec if isinstance(tspec, Mapping) else {}
                    if tspec_d.get('type') == 'dimension':
                        card_losses.append({
                            'code': 'field_filter_tag_simplified',
                            'severity': 'warning',
                            'detail': (
                                f'Metabase dimension field-filter '
                                f'{{{{{tname}}}}} converted to scalar '
                                f'parameter; review WHERE clause.'
                            ),
                        })
                    q_params.append({
                        'id': _safe_ident(tname, 'param'),
                        'name': str(tspec_d.get('display-name') or tname),
                        'type': 'string',
                        'required': bool(tspec_d.get('required', False)),
                    })
                for match in _MB_TAG_RE.finditer(raw_sql):
                    mname = _safe_ident(match.group(1), 'param')
                    if not any(p['id'] == mname for p in q_params):
                        q_params.append({
                            'id': mname,
                            'name': mname,
                            'type': 'string',
                            'required': False,
                        })
                q_model = default_question_model(
                    name=ctitle,
                    endpoint_id=endpoint_id,
                    raw_sql=raw_sql,
                    parameters=q_params,
                    visualization={'type': mapped_viz},
                )
            else:
                mbql = ds_query.get('query') or {}
                src_tbl = mbql.get('source-table')
                if isinstance(src_tbl, str) and src_tbl in tables_lookup:
                    rel = _rel_parts(tables_lookup[src_tbl])
                elif isinstance(src_tbl, list):
                    rel = _rel_parts(src_tbl)
                elif isinstance(src_tbl, str) and '.' in src_tbl:
                    rel = _rel_parts(src_tbl)
                else:
                    rel = ['main', _safe_ident(src_tbl or 'table_1', 'tbl')]
                alias = rel[-1]
                cols: list[dict[str, Any]] = []
                for b_i, brk in enumerate(mbql.get('breakout') or []):
                    cname = (
                        str(brk[1])
                        if isinstance(brk, list) and len(brk) >= 2
                        else str(brk)
                    )
                    cname = _safe_ident(cname, f'col_{b_i + 1}')
                    cols.append({'column': [alias, cname], 'alias': cname})
                measures: list[dict[str, Any]] = []
                for a_i, agg in enumerate(mbql.get('aggregation') or []):
                    if isinstance(agg, list) and agg:
                        fn_raw = str(agg[0]).lower().replace('-', '_')
                        if fn_raw == 'distinct':
                            fn_raw = 'count_distinct'
                        if fn_raw not in (
                            'sum', 'count', 'count_distinct',
                            'min', 'max', 'avg',
                        ):
                            card_losses.append({
                                'code': 'unsupported_mbql_aggregation',
                                'severity': 'warning',
                                'detail': (
                                    f'MBQL aggregation {fn_raw!r} mapped to '
                                    f'count'
                                ),
                            })
                            fn_raw = 'count'
                        target_col = None
                        if len(agg) >= 2 and fn_raw != 'count':
                            raw_f = agg[1]
                            cname = (
                                str(raw_f[1])
                                if isinstance(raw_f, list) and len(raw_f) >= 2
                                else str(raw_f)
                            )
                            target_col = [alias, _safe_ident(cname, 'val')]
                        measures.append({
                            'function': fn_raw,
                            'column': target_col,
                            'alias': f'{fn_raw}_{a_i + 1}',
                        })
                if not cols and not measures:
                    measures = [{
                        'function': 'count',
                        'column': None,
                        'alias': 'row_count',
                    }]
                q_model = default_question_model(
                    name=ctitle,
                    endpoint_id=endpoint_id,
                    sbsql={
                        'from': {'relation': rel, 'alias': alias},
                        'columns': cols,
                        'measures': measures,
                        'limit': int(mbql.get('limit') or 1000),
                    },
                    visualization={'type': mapped_viz},
                )

            losses.extend(card_losses)
            q_key = f"{key_prefix}_q_{_safe_ident(cid, 'card')}"
            ddn_text, _ = question_to_ddn(q_model)
            q_design = self.store.import_ddn(
                project_id=project_id,
                key=q_key,
                kind='question',
                title=ctitle,
                ddn_or_workspace=ddn_text,
                actor_id=actor_id,
                origin='import:metabase',
                loss_report={
                    'source_format': 'metabase_bundle',
                    'source_id': cid,
                    'items': card_losses,
                },
                observe_resources=True,
                note=f'Imported Metabase question {ctitle} as Draft',
            )
            card_map[cid] = {
                'design': q_design,
                'viz': mapped_viz,
                'title': ctitle,
            }
            imported_questions.append(q_design)

        imported_dashboards: list[dict[str, Any]] = []
        for d_idx, dash in enumerate(cleaned.get('dashboards') or []):
            if not isinstance(dash, Mapping):
                continue
            did = str(
                dash.get('entity_id') or dash.get('id') or f'dash_{d_idx + 1}'
            )
            dtitle = str(dash.get('name') or did)
            dash_losses: list[dict[str, Any]] = []
            cards: list[dict[str, Any]] = []
            raw_dcards = (
                dash.get('dashcards') or dash.get('ordered_cards') or []
            )
            for c_i, dc in enumerate(raw_dcards):
                if not isinstance(dc, Mapping):
                    continue
                ref_id = str(
                    dc.get('card_entity_id') or dc.get('card_id') or ''
                )
                viz_settings = dc.get('visualization_settings') or {}
                if not ref_id and viz_settings.get('text'):
                    cards.append({
                        'id': f'text_{c_i + 1}',
                        'tab_id': 'main',
                        'type': 'text',
                        'title': 'Note',
                        'text': {'markdown': str(viz_settings['text'])},
                        'layout': {
                            'x': int(dc.get('col') or 0),
                            'y': int(dc.get('row') or c_i * 6),
                            'w': max(1, min(24, int(dc.get('size_x') or 12))),
                            'h': max(1, min(100, int(dc.get('size_y') or 6))),
                        },
                    })
                    continue
                mapped_q = card_map.get(ref_id)
                if mapped_q is None:
                    dash_losses.append({
                        'code': 'missing_card_reference',
                        'severity': 'warning',
                        'detail': (
                            f'Metabase card {ref_id!r} missing in bundle'
                        ),
                    })
                    continue
                cards.append({
                    'id': f'card_{c_i + 1}',
                    'tab_id': 'main',
                    'type': 'question',
                    'title': mapped_q['title'],
                    'question': {
                        'question_design_id': mapped_q['design']['id'],
                        'pinned_version': 1,
                        'follow_latest_accepted': False,
                    },
                    'visualization': {'type': mapped_q['viz']},
                    'layout': {
                        'x': max(0, min(23, int(dc.get('col') or 0))),
                        'y': max(0, int(dc.get('row') or c_i * 8)),
                        'w': max(1, min(24, int(dc.get('size_x') or 12))),
                        'h': max(1, min(100, int(dc.get('size_y') or 8))),
                    },
                })

            dash_filters: list[dict[str, Any]] = []
            for p in dash.get('parameters') or []:
                if isinstance(p, Mapping):
                    dash_filters.append({
                        'id': _safe_ident(
                            p.get('slug') or p.get('id') or 'filter', 'flt'
                        ),
                        'name': str(p.get('name') or 'Filter'),
                        'type': 'string',
                        'widget': 'text',
                        'operator': 'eq',
                    })

            losses.extend(dash_losses)
            d_model = default_dashboard_model(
                name=dtitle,
                tabs=[{'id': 'main', 'name': 'Overview'}],
                cards=cards,
                filters=dash_filters,
            )
            d_ddn, _ = dashboard_to_ddn(d_model)
            d_key = f"{key_prefix}_d_{_safe_ident(did, 'dash')}"
            d_design = self.store.import_ddn(
                project_id=project_id,
                key=d_key,
                kind='dashboard',
                title=dtitle,
                ddn_or_workspace=d_ddn,
                actor_id=actor_id,
                origin='import:metabase',
                loss_report={
                    'source_format': 'metabase_bundle',
                    'source_id': did,
                    'items': dash_losses,
                },
                note=f'Imported Metabase dashboard {dtitle} as Draft',
            )
            self._sync_dashboard_dependencies(
                d_design['id'], d_design['head_version'], d_model
            )
            imported_dashboards.append(d_design)

        return {
            'source_format': 'metabase_bundle',
            'status': 'draft',
            'questions': imported_questions,
            'dashboards': imported_dashboards,
            'loss_report': {
                'source_format': 'metabase_bundle',
                'loss_count': len(losses),
                'items': losses,
            },
        }

    def import_legacy_bi_store(
        self,
        bundle: Mapping[str, Any] | None = None,
        *,
        project_id: str,
        actor_id: int,
        endpoint_id: str = 'default-endpoint',
        key_prefix: str = 'legacy_bi',
        bi_service: Any = None,
        dashboard_service: Any = None,
        semantic_service: Any = None,
    ) -> dict[str, Any]:
        """Migrate legacy ScratchRobin JSON BI items to Draft DDN.

        Reads either an explicit JSON export ``bundle`` or live rows from
        ``bi_service`` / ``dashboard_service`` in ``cdeadmin.db`` without
        mutating or deleting legacy configuration-database rows. Every item is
        written to ``designs.db`` as ``Draft`` with an explicit loss report.
        """
        raw_payload: dict[str, Any]
        if bundle and isinstance(bundle, Mapping) and (
            bundle.get('questions')
            or bundle.get('dashboards')
            or bundle.get('alerts')
            or bundle.get('embeds')
            or bundle.get('grants')
        ):
            raw_payload = dict(bundle)
        elif bi_service is not None:
            q_summaries = bi_service.list_questions(actor_id, endpoint_id)
            q_records = [
                bi_service.get_question(
                    actor_id, endpoint_id, item['question_id']
                )
                for item in q_summaries
            ]
            d_svc = dashboard_service or getattr(
                bi_service, 'dashboards', None
            )
            d_records = []
            if d_svc is not None:
                d_summaries = d_svc.list(actor_id, endpoint_id)
                d_records = [
                    d_svc.get(actor_id, endpoint_id, item['dashboard_id'])
                    for item in d_summaries
                ]
            raw_payload = {
                'questions': q_records,
                'dashboards': d_records,
            }
        else:
            raw_payload = dict(bundle or {})

        cleaned, stripped_fields = _strip_sensitive_fields(raw_payload)
        losses: list[dict[str, Any]] = [
            {
                'code': 'credential_or_grant_excluded',
                'severity': 'info',
                'detail': f'Excluded sensitive field {path} from DDN import',
            }
            for path in stripped_fields
        ]
        for runtime_key, code_name in (
            ('alerts', 'legacy_alerts_not_auto_enabled'),
            ('subscriptions', 'legacy_subscriptions_not_auto_enabled'),
            ('embeds', 'legacy_embeds_not_auto_enabled'),
            ('shares', 'legacy_shares_excluded_from_ddn'),
        ):
            if cleaned.get(runtime_key):
                losses.append({
                    'code': code_name,
                    'severity': 'warning',
                    'detail': (
                        f'Legacy {runtime_key} remain runtime switches '
                        f'outside DDN text and are not auto-activated.'
                    ),
                })

        semantic_lookup: dict[str, Mapping[str, Any]] = {}
        for sm in cleaned.get('semantic_models') or []:
            if isinstance(sm, Mapping) and sm.get('id'):
                semantic_lookup[str(sm['id'])] = sm

        question_design_map: dict[str, dict[str, Any]] = {}
        imported_questions: list[dict[str, Any]] = []

        for idx, q_entry in enumerate(cleaned.get('questions') or []):
            if not isinstance(q_entry, Mapping):
                continue
            q_id = str(
                q_entry.get('question_id')
                or q_entry.get('id')
                or f'q_{idx + 1}'
            )
            defn = (
                q_entry.get('definition')
                if isinstance(q_entry.get('definition'), Mapping)
                else q_entry
            )
            converted = convert_legacy_bi_question(
                defn,
                endpoint_id=endpoint_id,
                semantic_models=semantic_lookup,
                semantic_service=semantic_service,
                actor_id=actor_id,
            )
            q_model = converted['question']
            q_losses = list(converted['losses'])
            if q_entry.get('status') == 'archived':
                q_losses.append({
                    'code': 'archived_status_imported_as_draft',
                    'severity': 'info',
                    'detail': (
                        f'Archived legacy question {q_id!r} imported as Draft.'
                    ),
                })
            losses.extend(q_losses)
            q_key = f"{key_prefix}_q_{_safe_ident(q_id, f'q_{idx + 1}')}"
            ddn_text, _ = question_to_ddn(q_model)
            q_design = self.store.import_ddn(
                project_id=project_id,
                key=q_key,
                kind='question',
                title=q_model['name'],
                ddn_or_workspace=ddn_text,
                actor_id=actor_id,
                origin='import:legacy_bi',
                loss_report={
                    'source_format': 'legacy_scratchrobin_bi',
                    'source_question_id': q_id,
                    'items': q_losses,
                },
                observe_resources=True,
                note=(
                    f"Migrated legacy ScratchRobin BI question "
                    f"{q_model['name']} ({q_id}) as Draft"
                ),
            )
            question_design_map[q_id] = {
                'design': q_design,
                'question': q_model,
            }
            imported_questions.append(q_design)

        imported_dashboards: list[dict[str, Any]] = []
        for idx, d_entry in enumerate(cleaned.get('dashboards') or []):
            if not isinstance(d_entry, Mapping):
                continue
            d_id = str(
                d_entry.get('dashboard_id')
                or d_entry.get('id')
                or f'd_{idx + 1}'
            )
            defn = (
                d_entry.get('definition')
                if isinstance(d_entry.get('definition'), Mapping)
                else d_entry
            )
            converted_d = convert_legacy_bi_dashboard(
                defn,
                question_design_map=question_design_map,
            )
            d_model = converted_d['dashboard']
            d_losses = list(converted_d['losses'])
            if d_entry.get('status') == 'archived':
                d_losses.append({
                    'code': 'archived_status_imported_as_draft',
                    'severity': 'info',
                    'detail': (
                        f'Archived legacy dashboard {d_id!r} imported '
                        f'as Draft.'
                    ),
                })
            losses.extend(d_losses)
            d_key = f"{key_prefix}_d_{_safe_ident(d_id, f'd_{idx + 1}')}"
            d_ddn, _ = dashboard_to_ddn(d_model)
            d_design = self.store.import_ddn(
                project_id=project_id,
                key=d_key,
                kind='dashboard',
                title=d_model['name'],
                ddn_or_workspace=d_ddn,
                actor_id=actor_id,
                origin='import:legacy_bi',
                loss_report={
                    'source_format': 'legacy_scratchrobin_bi',
                    'source_dashboard_id': d_id,
                    'items': d_losses,
                },
                note=(
                    f"Migrated legacy ScratchRobin BI dashboard "
                    f"{d_model['name']} ({d_id}) as Draft"
                ),
            )
            self._sync_dashboard_dependencies(
                d_design['id'], d_design['head_version'], d_model
            )
            imported_dashboards.append(d_design)

        return {
            'source_format': 'legacy_scratchrobin_bi',
            'status': 'draft',
            'questions': imported_questions,
            'dashboards': imported_dashboards,
            'loss_report': {
                'source_format': 'legacy_scratchrobin_bi',
                'loss_count': len(losses),
                'items': losses,
            },
        }


def convert_legacy_bi_question(
    raw_question: Mapping[str, Any],
    *,
    endpoint_id: str = 'default-endpoint',
    semantic_models: Mapping[str, Mapping[str, Any]] | None = None,
    semantic_service: Any = None,
    actor_id: int = 1,
) -> dict[str, Any]:
    """Convert a legacy JSON ``BIQuestion`` definition to unified Draft DDN."""
    losses: list[dict[str, Any]] = []
    name = str(raw_question.get('name') or 'Migrated Question')
    description = str(raw_question.get('description') or '')
    if raw_question.get('collection_id'):
        losses.append({
            'code': 'collection_mapped_to_project',
            'severity': 'info',
            'detail': (
                f"Legacy collection_id {raw_question['collection_id']!r} "
                f"replaced by project scope in designs.db."
            ),
        })

    viz_raw = raw_question.get('visualization') or {'type': 'table'}
    vis_type = str(viz_raw.get('type') or 'table')
    if vis_type not in CHART_PROFILE_MAP:
        losses.append({
            'code': 'unsupported_visualization_type',
            'severity': 'warning',
            'detail': (
                f'Legacy visualization type {vis_type!r} mapped to table.'
            ),
        })
        vis_type = 'table'
    viz = {
        'type': vis_type,
        'settings': copy.deepcopy(dict(viz_raw.get('settings') or {})),
    }
    params = list(raw_question.get('parameters') or [])
    rpol = dict(raw_question.get('result_policy') or {})

    qspec = raw_question.get('query') or {}
    qkind = str(qspec.get('kind') or 'builder')
    if qkind == 'sql':
        sql_text = str(qspec.get('sql') or 'SELECT 1 AS value')
        model = default_question_model(
            name=name,
            endpoint_id=endpoint_id,
            raw_sql=sql_text,
            parameters=params,
            visualization=viz,
            result_policy=rpol,
        )
    elif qkind == 'semantic':
        sm_ref = raw_question.get('semantic_model') or {}
        sm_id = str(sm_ref.get('id') or 'semantic_model')
        sm_def: Mapping[str, Any] | None = (semantic_models or {}).get(sm_id)
        if sm_def is None and semantic_service is not None:
            try:
                loaded_sm = semantic_service.get_model(
                    actor_id, endpoint_id, sm_id
                )
                sm_def = loaded_sm.get('definition') or loaded_sm
            except Exception:
                sm_def = None
        b = qspec.get('builder') or {}
        rel = ['main', _safe_ident(f'cube_{sm_id[:8]}', 'cube')]
        if isinstance(sm_def, Mapping):
            sources = sm_def.get('sources') or []
            if sources and isinstance(sources[0], Mapping):
                src_rel = sources[0].get('relation')
                if isinstance(src_rel, list) and src_rel:
                    rel = _rel_parts(src_rel)
        losses.append({
            'code': 'legacy_semantic_query_converted',
            'severity': 'warning',
            'detail': (
                f'Legacy semantic builder query on semantic_model {sm_id!r} '
                f'converted to Draft SBsql; review cube field bindings.'
            ),
        })
        alias = rel[-1]
        cols = [
            {
                'column': [alias, _safe_ident(g, f'dim_{i + 1}')],
                'alias': _safe_ident(g, f'dim_{i + 1}'),
            }
            for i, g in enumerate(b.get('group_by') or [])
        ]
        measures = [
            {
                'function': 'sum',
                'column': [
                    alias,
                    _safe_ident(
                        (m.get('measure_id') if isinstance(m, Mapping) else m),
                        f'm_{i + 1}',
                    ),
                ],
                'alias': _safe_ident(
                    (m.get('measure_id') if isinstance(m, Mapping) else m),
                    f'm_{i + 1}',
                ),
            }
            for i, m in enumerate(b.get('aggregations') or [])
        ] or [{'function': 'count', 'column': None, 'alias': 'row_count'}]
        model = default_question_model(
            name=name,
            endpoint_id=endpoint_id,
            sbsql={
                'from': {'relation': rel, 'alias': alias},
                'columns': cols,
                'measures': measures,
                'limit': int(b.get('limit') or 500),
            },
            parameters=params,
            visualization=viz,
            result_policy=rpol,
        )
    else:
        b = qspec.get('builder') or {}
        src = b.get('source') or {}
        rel = _rel_parts(src.get('relation') or ['main', 'items'])
        alias = rel[-1]
        seen_cols: set[str] = set()
        cols = []
        for entry in list(b.get('group_by') or []) + list(
            b.get('columns') or []
        ):
            c_obj = (
                {'column': entry}
                if isinstance(entry, str)
                else dict(entry or {})
            )
            cname = _safe_ident(c_obj.get('column'), 'col')
            calias = _safe_ident(c_obj.get('alias') or cname, cname)
            if calias not in seen_cols:
                seen_cols.add(calias)
                cols.append({'column': [alias, cname], 'alias': calias})
        measures = []
        for idx, agg in enumerate(b.get('aggregations') or []):
            if not isinstance(agg, Mapping):
                continue
            fn = str(agg.get('function') or 'count')
            col_raw = agg.get('column')
            m_alias = _safe_ident(
                agg.get('alias') or f'{fn}_{col_raw or (idx + 1)}',
                f'm_{idx + 1}',
            )
            measures.append({
                'function': fn,
                'column': (
                    [alias, _safe_ident(col_raw, 'val')] if col_raw else None
                ),
                'alias': m_alias,
            })
        sbsql_filters = []
        for flt in b.get('filters') or []:
            if not isinstance(flt, Mapping):
                continue
            fcol = _safe_ident(flt.get('column'), 'col')
            fentry: dict[str, Any] = {
                'column': [alias, fcol],
                'operator': str(flt.get('operator') or 'eq'),
            }
            if flt.get('parameter_id') is not None:
                fentry['parameter'] = _safe_ident(
                    flt['parameter_id'], 'param'
                )
            else:
                fentry['value'] = copy.deepcopy(flt.get('value'))
            sbsql_filters.append(fentry)
        order_by = [
            {
                'expr': _safe_ident(o.get('column'), 'col'),
                'direction': str(o.get('direction') or 'asc'),
            }
            for o in (b.get('order_by') or [])
            if isinstance(o, Mapping) and o.get('column')
        ]
        model = default_question_model(
            name=name,
            endpoint_id=endpoint_id,
            sbsql={
                'from': {'relation': rel, 'alias': alias},
                'columns': cols,
                'measures': measures,
                'filters': sbsql_filters,
                'order_by': order_by,
                'limit': int(b.get('limit') or 500),
            },
            parameters=params,
            visualization=viz,
            result_policy=rpol,
        )
    model['description'] = description
    return {'question': model, 'losses': losses}


def convert_legacy_bi_dashboard(
    raw_dashboard: Mapping[str, Any],
    *,
    question_design_map: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Convert a legacy JSON ``BIDashboard`` definition to Draft DDN."""
    losses: list[dict[str, Any]] = []
    name = str(raw_dashboard.get('name') or 'Migrated Dashboard')
    description = str(raw_dashboard.get('description') or '')
    if raw_dashboard.get('collection_id'):
        losses.append({
            'code': 'collection_mapped_to_project',
            'severity': 'info',
            'detail': (
                f"Legacy collection_id {raw_dashboard['collection_id']!r} "
                f"replaced by project scope in designs.db."
            ),
        })

    tabs = [
        {
            'id': _safe_ident(t.get('id'), 'main'),
            'name': str(t.get('name') or 'Main'),
        }
        for t in (
            raw_dashboard.get('tabs') or [{'id': 'main', 'name': 'Main'}]
        )
        if isinstance(t, Mapping)
    ] or [{'id': 'main', 'name': 'Main'}]
    valid_tab_ids = {t['id'] for t in tabs}

    cards: list[dict[str, Any]] = []
    for idx, craw in enumerate(raw_dashboard.get('cards') or []):
        if not isinstance(craw, Mapping):
            continue
        cid = _safe_ident(craw.get('id') or f'card_{idx + 1}', 'card')
        tab_id = _safe_ident(
            craw.get('tab_id') or tabs[0]['id'], tabs[0]['id']
        )
        if tab_id not in valid_tab_ids:
            tab_id = tabs[0]['id']
        ctype = str(craw.get('type') or 'text')
        lay = craw.get('layout') or {}
        layout_box = {
            'x': max(0, min(23, int(lay.get('x') or 0))),
            'y': max(0, int(lay.get('y') or idx * 8)),
            'w': max(1, min(24, int(lay.get('w') or 12))),
            'h': max(1, min(100, int(lay.get('h') or 8))),
        }
        title = str(craw.get('title') or cid)
        if ctype == 'question':
            qref = craw.get('question') or {}
            legacy_qid = str(qref.get('question_id') or '')
            mapped = question_design_map.get(legacy_qid)
            if mapped is None:
                losses.append({
                    'code': 'missing_legacy_question',
                    'severity': 'warning',
                    'detail': (
                        f'Card {cid!r} references legacy question '
                        f'{legacy_qid!r} which was not in the migrated set.'
                    ),
                })
                continue
            vis_ov = craw.get('visualization') or (
                mapped['question'].get('visualization') or {'type': 'bar'}
            )
            vtype = str(vis_ov.get('type') or 'bar')
            if vtype not in CHART_PROFILE_MAP:
                vtype = 'table'
            cards.append({
                'id': cid,
                'tab_id': tab_id,
                'type': 'question',
                'title': title or mapped['question']['name'],
                'layout': layout_box,
                'question': {
                    'question_design_id': mapped['design']['id'],
                    'pinned_version': 1,
                    'follow_latest_accepted': False,
                },
                'visualization': {
                    'type': vtype,
                    'settings': copy.deepcopy(
                        dict(vis_ov.get('settings') or {})
                    ),
                },
            })
        elif ctype == 'text':
            t_obj = craw.get('text') or {}
            cards.append({
                'id': cid,
                'tab_id': tab_id,
                'type': 'text',
                'title': title,
                'layout': layout_box,
                'text': {'markdown': str(t_obj.get('markdown') or '')},
            })
        elif ctype == 'metric_panel':
            mp = craw.get('metric_panel') or {}
            losses.append({
                'code': 'metric_panel_static_snapshot',
                'severity': 'info',
                'detail': (
                    f'Legacy monitoring metric_panel {cid!r} imported as a '
                    f'static snapshot card (live collector feeds stay in '
                    f'monitoring).'
                ),
            })
            cards.append({
                'id': cid,
                'tab_id': tab_id,
                'type': 'metric_panel',
                'title': title,
                'layout': layout_box,
                'metric_panel': {
                    'panel_id': str(mp.get('panel_id') or cid),
                    'snapshot_mode': 'static',
                    'columns': copy.deepcopy(list(mp.get('columns') or [
                        {'id': 'measure', 'label': 'Measure'},
                        {'id': 'value', 'label': 'Snapshot Value'},
                    ])),
                    'rows': copy.deepcopy(list(mp.get('rows') or [])),
                },
            })

    kept_card_ids = {c['id'] for c in cards}
    filters: list[dict[str, Any]] = []
    for fraw in raw_dashboard.get('filters') or []:
        if not isinstance(fraw, Mapping):
            continue
        fid = _safe_ident(fraw.get('id'), 'flt')
        targets = []
        for tgt in fraw.get('targets') or []:
            if not isinstance(tgt, Mapping):
                continue
            tcid = _safe_ident(tgt.get('card_id'), 'card')
            if tcid not in kept_card_ids:
                continue
            if tgt.get('parameter_id'):
                targets.append({
                    'card_id': tcid,
                    'parameter': _safe_ident(tgt['parameter_id'], 'param'),
                })
            elif isinstance(tgt.get('field'), Mapping):
                fld = tgt['field']
                targets.append({
                    'card_id': tcid,
                    'field': str(fld.get('column') or fld.get('field') or ''),
                })
        fentry: dict[str, Any] = {
            'id': fid,
            'name': str(fraw.get('name') or fid),
            'type': str(fraw.get('type') or 'string'),
            'widget': str(fraw.get('widget') or 'text'),
            'operator': str(fraw.get('operator') or 'eq'),
            'required': bool(fraw.get('required', False)),
            'targets': targets,
        }
        if 'default' in fraw and fraw['default'] is not None:
            fentry['default'] = copy.deepcopy(fraw['default'])
        filters.append(fentry)

    links: list[dict[str, Any]] = []
    for dt in raw_dashboard.get('drill_throughs') or []:
        if not isinstance(dt, Mapping):
            continue
        src_cid = _safe_ident(dt.get('source_card_id'), 'card')
        if src_cid not in kept_card_ids:
            continue
        tgt = dt.get('target') or {}
        if tgt.get('kind') == 'question':
            mapped_q = question_design_map.get(
                str(tgt.get('question_id') or '')
            )
            if mapped_q is None:
                losses.append({
                    'code': 'unresolved_drill_target',
                    'severity': 'warning',
                    'detail': (
                        f"Drill-through {dt.get('id')!r} targets unmigrated "
                        f"question {tgt.get('question_id')!r}."
                    ),
                })
                continue
            fmap: dict[str, str] = {}
            for param_id, src_spec in (tgt.get('parameters') or {}).items():
                if isinstance(src_spec, Mapping) and src_spec.get('column'):
                    fmap[str(src_spec['column'])] = str(param_id)
            links.append({
                'id': _safe_ident(dt.get('id') or 'drill', 'drill'),
                'card_id': src_cid,
                'kind': 'drill_through',
                'target_design_id': mapped_q['design']['id'],
                'carry_filter_context': True,
                'field_map': fmap,
            })
        else:
            losses.append({
                'code': 'external_drill_target_deferred',
                'severity': 'info',
                'detail': (
                    f"Drill-through {dt.get('id')!r} to dashboard target "
                    f"{tgt.get('dashboard_id')!r} recorded in loss report; "
                    f"re-link to target dashboard design ID if needed."
                ),
            })

    d_model = default_dashboard_model(
        name=name,
        tabs=tabs,
        cards=cards,
        filters=filters,
        links=links,
        description=description,
    )
    return {'dashboard': d_model, 'losses': losses}

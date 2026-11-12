##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Cube Designer Phase 1 server extensions.

Implements the four Cube Designer capability endpoints wired in ``routes.py``:
- ``check_cube_against_connection`` (``SR-F-030002``): PK uniqueness, join
  fan-out ratio, and orphan foreign-key probes against a SQLite connection or
  sample verification harness.
- ``reduce_cube_aggregations`` (``SR-F-030005``): Kylin-style combinatorial
  rule-group cuboid reducer (mandatory dimensions, hierarchy prefix sets,
  all-or-nothing joint sets, and max dimension combination cap).
- ``execute_cube_try_query``: Interactive slice-and-dice query compiler,
  aggregate routing hit detector, role/locale preview, and optional SQLite
  execution.
- ``propose_cube_ai_draft`` (``SR-F-030004``): BYOK Draft-only cube assistant
  that searches existing cubes first and proposes measures, dimensions, and
  aggregations for human review without auto-accepting or publishing.
"""

from __future__ import annotations

import copy
from itertools import combinations
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping

from pgadmin.cdeadmin.semantic_models.compiler import compile_sql
from pgadmin.cdeadmin.semantic_models.models import (
    SemanticModelError,
    filter_model_for_role,
    identifier,
    localize_model,
    public_model,
    validate_model,
)

from .cube_ddn import (
    CubeDesignSync,
    ddn_to_semantic_model,
    default_cube_model,
    semantic_model_to_ddn,
)
from .service import DesignStore, DesignStoreError
from .shared_ddn import StoreDDNProcess


_DIALECT_CONTRACTS: dict[str, dict[str, Any]] = {
    'sqlite': {
        'contract_complete': True,
        'language_profile': 'sqlite',
        'quote_open': '"',
        'quote_close': '"',
        'supports_rollup': False,
        'limit_style': 'limit',
        'true_literal': '1',
        'false_literal': '0',
        'time_operations': ['as_of', 'range', 'period_comparison'],
        'window_operations': [
            'running_sum', 'moving_sum', 'moving_average', 'lag',
            'delta', 'percent_change', 'rank', 'dense_rank',
        ],
    },
    'duckdb': {
        'contract_complete': True,
        'language_profile': 'duckdb',
        'quote_open': '"',
        'quote_close': '"',
        'supports_rollup': True,
        'limit_style': 'limit',
        'true_literal': 'TRUE',
        'false_literal': 'FALSE',
        'time_operations': [
            'as_of', 'range', 'period_to_date', 'period_comparison',
        ],
        'window_operations': [
            'running_sum', 'moving_sum', 'moving_average', 'lag',
            'delta', 'percent_change', 'rank', 'dense_rank',
        ],
    },
    'postgresql': {
        'contract_complete': True,
        'language_profile': 'postgresql',
        'quote_open': '"',
        'quote_close': '"',
        'supports_rollup': True,
        'limit_style': 'limit',
        'true_literal': 'TRUE',
        'false_literal': 'FALSE',
        'time_operations': [
            'as_of', 'range', 'period_to_date', 'period_comparison',
        ],
        'window_operations': [
            'running_sum', 'moving_sum', 'moving_average', 'lag',
            'delta', 'percent_change', 'rank', 'dense_rank',
        ],
    },
    'mysql': {
        'contract_complete': True,
        'language_profile': 'mysql',
        'quote_open': '`',
        'quote_close': '`',
        'supports_rollup': True,
        'rollup_style': 'with_rollup',
        'rollup_allows_order_by': False,
        'limit_style': 'limit',
        'true_literal': 'TRUE',
        'false_literal': 'FALSE',
        'time_operations': ['as_of', 'range', 'period_comparison'],
        'window_operations': [
            'running_sum', 'moving_sum', 'moving_average', 'lag',
            'delta', 'percent_change', 'rank', 'dense_rank',
        ],
    },
    'firebird': {
        'contract_complete': True,
        'language_profile': 'firebird',
        'quote_open': '"',
        'quote_close': '"',
        'supports_rollup': False,
        'limit_style': 'rows',
        'true_literal': 'TRUE',
        'false_literal': 'FALSE',
        'time_operations': ['as_of', 'range', 'period_comparison'],
        'window_operations': [
            'running_sum', 'moving_sum', 'moving_average', 'lag',
            'delta', 'percent_change', 'rank', 'dense_rank',
        ],
    },
}


def _quote_ident(name: str, quote_open: str = '"', quote_close: str = '"'):
    escaped = str(name).replace(quote_close, quote_close + quote_close)
    return f'{quote_open}{escaped}{quote_close}'


def _relation_sql(relation: list[str], *, sqlite_mode: bool = False) -> str:
    parts = [p for p in (relation or []) if str(p).strip()]
    if not parts:
        return '"fact_table"'
    if sqlite_mode and len(parts) > 1 and parts[0].lower() in {
        'public', 'dbo', 'default',
    }:
        parts = parts[-1:]
    return '.'.join(_quote_ident(p) for p in parts)


def _load_cube_model_for_design(
    store: DesignStore, design_id: str, payload: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    design = store.get_design(design_id)
    if design.get('kind') != 'cube':
        raise DesignStoreError(f'Design {design_id} is not a cube design')
    parsed = ddn_to_semantic_model(design['version']['ddn_text'])
    if isinstance(payload.get('model'), Mapping):
        try:
            model = public_model(validate_model(payload['model']))
        except SemanticModelError as exc:
            raise DesignStoreError(str(exc)) from exc
    else:
        model = parsed['model']
    return design, parsed, model


def _resolve_sqlite_connection(
    model: Mapping[str, Any],
    payload: Mapping[str, Any],
    app=None,
) -> tuple[sqlite3.Connection | None, str]:
    """Open an isolated read/harness SQLite connection when available."""
    sample_rows = payload.get('sample_rows')
    if isinstance(sample_rows, Mapping) and sample_rows:
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        sources_by_id = {s['id']: s for s in model.get('sources', [])}
        known_cols: dict[str, set[str]] = {}
        for src in model.get('sources', []):
            tname = (src.get('relation') or [src['id']])[-1]
            cols = known_cols.setdefault(tname, set())
            for g in src.get('grain', []):
                if g.get('field'):
                    cols.add(g['field'])
        for dim in model.get('dimensions', []):
            for key_name in ('field', 'key_field', 'name_field', 'sort_field'):
                ref = dim.get(key_name)
                if isinstance(ref, Mapping) and ref.get('source_id') in (
                    sources_by_id
                ):
                    tname = (
                        sources_by_id[ref['source_id']].get('relation')
                        or [ref['source_id']]
                    )[-1]
                    known_cols.setdefault(tname, set()).add(ref['field'])
            for attr in dim.get('attributes', []):
                ref = attr.get('field')
                if isinstance(ref, Mapping) and ref.get('source_id') in (
                    sources_by_id
                ):
                    tname = (
                        sources_by_id[ref['source_id']].get('relation')
                        or [ref['source_id']]
                    )[-1]
                    known_cols.setdefault(tname, set()).add(ref['field'])
            for hier in dim.get('hierarchies', []):
                for lvl in hier.get('levels', []):
                    ref = lvl.get('field')
                    if isinstance(ref, Mapping) and ref.get('source_id') in (
                        sources_by_id
                    ):
                        tname = (
                            sources_by_id[ref['source_id']].get('relation')
                            or [ref['source_id']]
                        )[-1]
                        known_cols.setdefault(tname, set()).add(ref['field'])
        for join in model.get('joins', []):
            for pred in join.get('predicates', []):
                for side in ('left', 'right'):
                    ref = pred.get(side)
                    if isinstance(ref, Mapping) and ref.get('source_id') in (
                        sources_by_id
                    ):
                        tname = (
                            sources_by_id[ref['source_id']].get('relation')
                            or [ref['source_id']]
                        )[-1]
                        known_cols.setdefault(tname, set()).add(ref['field'])
        for meas in model.get('measures', []):
            ref = meas.get('field')
            if isinstance(ref, Mapping) and ref.get('source_id') in (
                sources_by_id
            ):
                tname = (
                    sources_by_id[ref['source_id']].get('relation')
                    or [ref['source_id']]
                )[-1]
                known_cols.setdefault(tname, set()).add(ref['field'])

        for raw_key, rows in sample_rows.items():
            if not isinstance(rows, list):
                continue
            src_obj = sources_by_id.get(str(raw_key))
            tname = (
                (src_obj.get('relation') or [src_obj['id']])[-1]
                if src_obj
                else str(raw_key)
            )
            col_set = set(known_cols.get(tname, set()))
            for row in rows:
                if isinstance(row, Mapping):
                    col_set.update(str(k) for k in row.keys())
            ordered_cols = sorted(col_set) or ['id']
            col_defs = ', '.join(_quote_ident(c) for c in ordered_cols)
            conn.execute(
                f'CREATE TABLE IF NOT EXISTS {_quote_ident(tname)} '
                f'({col_defs})'
            )
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                placeholders = ', '.join('?' for _ in ordered_cols)
                vals = [row.get(c) for c in ordered_cols]
                conn.execute(
                    f'INSERT INTO {_quote_ident(tname)} '
                    f'({", ".join(_quote_ident(c) for c in ordered_cols)}) '
                    f'VALUES ({placeholders})',
                    vals,
                )
        for tname, cols in known_cols.items():
            ordered_cols = sorted(cols) or ['id']
            col_defs = ', '.join(_quote_ident(c) for c in ordered_cols)
            conn.execute(
                f'CREATE TABLE IF NOT EXISTS {_quote_ident(tname)} '
                f'({col_defs})'
            )
        return conn, 'sample_harness'

    sqlite_path = str(payload.get('sqlite_path') or '').strip()
    if sqlite_path:
        path_obj = Path(sqlite_path)
        if not path_obj.is_file():
            raise DesignStoreError(
                f'SQLite database file does not exist: {sqlite_path}'
            )
        uri = f'file:{path_obj.resolve()}?mode=ro'
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn, 'sqlite_connection'

    endpoint_id = str(
        payload.get('endpoint_id')
        or model.get('annotations', {}).get('semantic_endpoint_id')
        or ''
    ).strip()
    if endpoint_id and app is not None:
        ext = getattr(app, 'extensions', {}) or {}
        ep_svc = ext.get('cdeadmin_endpoint_service')
        if ep_svc is not None and hasattr(ep_svc, 'resolve_sqlite_path'):
            try:
                resolved = ep_svc.resolve_sqlite_path(endpoint_id)
                if resolved and Path(resolved).is_file():
                    uri = f'file:{Path(resolved).resolve()}?mode=ro'
                    conn = sqlite3.connect(uri, uri=True)
                    conn.row_factory = sqlite3.Row
                    return conn, 'sqlite_connection'
            except Exception:
                pass

    return None, 'probe_sql_only'


def check_cube_against_connection(
    store: DesignStore,
    *,
    design_id: str,
    actor_id: int,
    payload: dict[str, Any],
    app=None,
) -> dict[str, Any]:
    """Run PK uniqueness, join fan-out, and orphan FK checks for a cube."""
    _ = actor_id
    body = payload if isinstance(payload, Mapping) else {}
    _design, _parsed, model = _load_cube_model_for_design(
        store, design_id, body
    )
    sources_by_id = {s['id']: s for s in model.get('sources', [])}
    fact_sources = [
        s for s in model.get('sources', [])
        if s.get('classification') == 'fact'
    ] or model.get('sources', [])[:1]
    if not fact_sources:
        raise DesignStoreError('Cube model has no fact source to verify')
    primary_fact = fact_sources[0]
    joins_by_id = {j['id']: j for j in model.get('joins', [])}

    conn, checked_mode = _resolve_sqlite_connection(model, body, app=app)
    sqlite_mode = conn is not None
    fact_rel_sql = _relation_sql(
        primary_fact.get('relation', [primary_fact['id']]),
        sqlite_mode=sqlite_mode,
    )

    fact_row_count: int | None = None
    dimension_results: list[dict[str, Any]] = []
    probe_queries: list[dict[str, str]] = []

    try:
        if conn is not None:
            try:
                row = conn.execute(
                    f'SELECT COUNT(*) AS cnt FROM {fact_rel_sql}'
                ).fetchone()
                fact_row_count = int(row['cnt']) if row is not None else 0
            except sqlite3.Error:
                fact_row_count = None

        for dim in model.get('dimensions', []):
            dim_id = dim['id']
            key_ref = dim.get('key_field') or dim['field']
            dim_src_id = key_ref['source_id']
            key_col = key_ref['field']
            dim_src = sources_by_id.get(dim_src_id, {'relation': [dim_src_id]})
            dim_rel_sql = _relation_sql(
                dim_src.get('relation', [dim_src_id]),
                sqlite_mode=sqlite_mode,
            )
            q_key = _quote_ident(key_col)

            join_obj = None
            if dim.get('join_id') and dim['join_id'] in joins_by_id:
                join_obj = joins_by_id[dim['join_id']]
            elif dim_src_id != primary_fact['id']:
                join_obj = next(
                    (
                        j for j in model.get('joins', [])
                        if j.get('right_source') == dim_src_id
                        and j.get('left_source') == primary_fact['id']
                    ),
                    None,
                )

            pk_sql = (
                f'SELECT COUNT(*) AS total_rows, '
                f'COUNT(DISTINCT {q_key}) AS distinct_keys '
                f'FROM {dim_rel_sql}'
            )

            fanout_sql = ''
            orphan_sql = ''
            if join_obj and join_obj.get('predicates'):
                on_clauses: list[str] = []
                orphan_checks: list[str] = []
                for pred in join_obj['predicates']:
                    l_ref = pred['left']
                    r_ref = pred['right']
                    if l_ref['source_id'] == primary_fact['id']:
                        f_col = _quote_ident(l_ref['field'])
                        d_col = _quote_ident(r_ref['field'])
                    else:
                        f_col = _quote_ident(r_ref['field'])
                        d_col = _quote_ident(l_ref['field'])
                    on_clauses.append(f'f.{f_col} = d.{d_col}')
                    orphan_checks.append(
                        f'(f.{f_col} IS NOT NULL AND d.{d_col} IS NULL)'
                    )
                on_expr = ' AND '.join(on_clauses)
                orphan_expr = ' OR '.join(orphan_checks)
                fanout_sql = (
                    f'SELECT '
                    f'(SELECT COUNT(*) FROM {fact_rel_sql}) AS base_rows, '
                    f'(SELECT COUNT(*) FROM {fact_rel_sql} AS f '
                    f'LEFT JOIN {dim_rel_sql} AS d ON {on_expr}) '
                    f'AS joined_rows'
                )
                orphan_sql = (
                    f'SELECT COUNT(*) AS orphan_fact_rows '
                    f'FROM {fact_rel_sql} AS f '
                    f'LEFT JOIN {dim_rel_sql} AS d ON {on_expr} '
                    f'WHERE {orphan_expr}'
                )

            combined_probe = ';\n'.join(
                s for s in (pk_sql, fanout_sql, orphan_sql) if s
            ) + ';'
            probe_queries.append({
                'dimension_id': dim_id,
                'pk_probe_sql': pk_sql,
                'fanout_probe_sql': fanout_sql,
                'orphan_probe_sql': orphan_sql,
                'probe_sql': combined_probe,
            })

            um_policy = dim.get('unknown_member_policy', 'unknown')
            duplicate_keys = 0
            orphan_fact_rows = 0
            fanout_ratio = 1.0

            if conn is None:
                dimension_results.append({
                    'dimension_id': dim_id,
                    'dimension_name': dim['name'],
                    'key_field': f'{dim_src_id}.{key_col}',
                    'unknown_member_policy': um_policy,
                    'status': 'unverified_connection',
                    'duplicate_keys': 0,
                    'orphan_fact_rows': 0,
                    'fanout_ratio': 1.0,
                    'probe_sql': combined_probe,
                    'message': (
                        'Generated PK uniqueness, join fan-out, and orphan FK '
                        'probe SQL; supply a live SQLite connection or sample '
                        'rows to execute.'
                    ),
                })
                continue

            try:
                pk_row = conn.execute(pk_sql).fetchone()
                total_dim_rows = int(pk_row['total_rows']) if pk_row else 0
                distinct_keys = int(pk_row['distinct_keys']) if pk_row else 0
                if dim_src_id != primary_fact['id']:
                    duplicate_keys = max(0, total_dim_rows - distinct_keys)

                if fanout_sql:
                    fo_row = conn.execute(fanout_sql).fetchone()
                    base_r = int(fo_row['base_rows']) if fo_row else 0
                    joined_r = int(fo_row['joined_rows']) if fo_row else 0
                    if base_r > 0:
                        fanout_ratio = round(joined_r / base_r, 4)
                if orphan_sql:
                    or_row = conn.execute(orphan_sql).fetchone()
                    orphan_fact_rows = (
                        int(or_row['orphan_fact_rows']) if or_row else 0
                    )

                issues: list[str] = []
                status = 'valid'
                if duplicate_keys > 0 or fanout_ratio > 1.0:
                    status = 'fanout_risk'
                    issues.append(
                        f'{duplicate_keys} duplicate dimension key(s), '
                        f'join fan-out ratio {fanout_ratio:.2f}x'
                    )
                if orphan_fact_rows > 0:
                    if um_policy == 'error':
                        status = 'fanout_risk'
                        issues.append(
                            f'{orphan_fact_rows} orphan fact row(s) violate '
                            "unknown_member_policy='error'"
                        )
                    else:
                        issues.append(
                            f'{orphan_fact_rows} orphan fact row(s) handled '
                            f"by unknown_member_policy='{um_policy}'"
                        )
                msg = (
                    '; '.join(issues)
                    if issues
                    else (
                        f'Dimension key {dim_src_id}.{key_col} is unique '
                        'with 1.00x join ratio and 0 orphan fact rows.'
                    )
                )
                dimension_results.append({
                    'dimension_id': dim_id,
                    'dimension_name': dim['name'],
                    'key_field': f'{dim_src_id}.{key_col}',
                    'unknown_member_policy': um_policy,
                    'status': status,
                    'duplicate_keys': duplicate_keys,
                    'orphan_fact_rows': orphan_fact_rows,
                    'fanout_ratio': fanout_ratio,
                    'probe_sql': combined_probe,
                    'message': msg,
                })
            except sqlite3.Error as exc:
                dimension_results.append({
                    'dimension_id': dim_id,
                    'dimension_name': dim['name'],
                    'key_field': f'{dim_src_id}.{key_col}',
                    'unknown_member_policy': um_policy,
                    'status': 'unverified_connection',
                    'duplicate_keys': 0,
                    'orphan_fact_rows': 0,
                    'fanout_ratio': 1.0,
                    'probe_sql': combined_probe,
                    'message': f'Probe query could not run on connection: {exc}',
                })
    finally:
        if conn is not None:
            conn.close()

    statuses = {d['status'] for d in dimension_results}
    if 'fanout_risk' in statuses:
        overall_status = 'fanout_risk'
    elif 'unverified_connection' in statuses or not dimension_results:
        overall_status = 'unverified_connection'
    else:
        overall_status = 'valid'

    return {
        'design_id': design_id,
        'checked_against': checked_mode,
        'overall_status': overall_status,
        'fact_table': '.'.join(
            primary_fact.get('relation', [primary_fact['id']])
        ),
        'fact_row_count': fact_row_count,
        'dimensions': dimension_results,
        'probe_queries': probe_queries,
    }


def _slug_id(raw: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9_]+', '_', str(raw or '').strip()).strip('_')
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f'agg_{cleaned}' if cleaned else 'agg_plan'
    return cleaned[:120]


def reduce_cube_aggregations(
    store: DesignStore,
    proc: StoreDDNProcess,
    *,
    design_id: str,
    actor_id: int,
    payload: dict[str, Any],
    semantic_service=None,
) -> dict[str, Any]:
    """Prune naive 2^D cuboid combinations using Kylin-style rule groups."""
    body = payload if isinstance(payload, Mapping) else {}
    design, parsed, model = _load_cube_model_for_design(store, design_id, body)

    admitted_grain: list[str] = []
    for dim in model.get('dimensions', []):
        if dim.get('active', True) is not False:
            admitted_grain.append(dim['id'])
        for attr in dim.get('attributes', []):
            admitted_grain.append(attr['id'])
        for hier in dim.get('hierarchies', []):
            if hier.get('hierarchy_kind') == 'parent_child':
                admitted_grain.append(hier['id'])
            for lvl in hier.get('levels', []):
                admitted_grain.append(lvl['id'])
    admitted_set = set(admitted_grain)

    raw_candidates = body.get('candidate_dimensions')
    if isinstance(raw_candidates, list) and raw_candidates:
        candidates: list[str] = []
        for item in raw_candidates:
            cid = identifier(item, 'candidate_dimensions.item')
            if cid not in candidates:
                candidates.append(cid)
    else:
        candidates = [
            d['id']
            for d in model.get('dimensions', [])
            if d.get('active', True) is not False
        ]

    if len(candidates) > 16:
        raise DesignStoreError(
            'Combinatorial rule reducer supports at most 16 candidate '
            'dimensions per rule group'
        )

    mandatory = [
        identifier(item, 'mandatory_dimensions.item')
        for item in (body.get('mandatory_dimensions') or [])
    ]
    hierarchy_sets = [
        [identifier(d, 'hierarchy_sets.item') for d in chain]
        for chain in (body.get('hierarchy_sets') or [])
        if isinstance(chain, list) and chain
    ]
    joint_sets = [
        [identifier(d, 'joint_sets.item') for d in grp]
        for grp in (body.get('joint_sets') or [])
        if isinstance(grp, list) and grp
    ]

    for extra_id in (
        mandatory
        + [d for chain in hierarchy_sets for d in chain]
        + [d for grp in joint_sets for d in grp]
    ):
        if extra_id not in candidates:
            candidates.append(extra_id)

    raw_max = body.get('max_dimension_combinations')
    max_cap: int | None = None
    if raw_max is not None and raw_max != '':
        if isinstance(raw_max, bool) or not isinstance(raw_max, int):
            try:
                max_cap = int(raw_max)
            except (TypeError, ValueError) as exc:
                raise DesignStoreError(
                    'max_dimension_combinations must be an integer'
                ) from exc
        else:
            max_cap = raw_max
        if max_cap < 0:
            raise DesignStoreError(
                'max_dimension_combinations must be non-negative'
            )

    include_apex = bool(body.get('include_apex', False))

    all_subsets: list[tuple[str, ...]] = []
    for r_len in range(len(candidates) + 1):
        all_subsets.extend(combinations(candidates, r_len))
    naive_count = len(all_subsets)  # 2 ** len(candidates)

    mandatory_set = set(mandatory)
    after_mj: list[tuple[str, ...]] = []
    for sub in all_subsets:
        sub_set = set(sub)
        if not mandatory_set.issubset(sub_set):
            continue
        joint_ok = True
        for j_grp in joint_sets:
            present = [item in sub_set for item in j_grp]
            if any(present) and not all(present):
                joint_ok = False
                break
        if joint_ok:
            after_mj.append(sub)
    after_mj_count = len(after_mj)

    final_cuboids: list[list[str]] = []
    for sub in after_mj:
        if not sub and not include_apex:
            continue
        sub_set = set(sub)
        hier_ok = True
        for chain in hierarchy_sets:
            in_chain = [item for item in chain if item in sub_set]
            if in_chain != chain[:len(in_chain)]:
                hier_ok = False
                break
        if not hier_ok:
            continue
        if max_cap is not None and len(sub) > max_cap:
            continue
        final_cuboids.append(list(sub))
    final_count = len(final_cuboids)

    requested_measures = [
        identifier(m, 'measures.item')
        for m in (body.get('measures') or [])
    ] or [m['id'] for m in model.get('measures', [])]

    partition_field = body.get('partition_field') or None
    partition_grain = str(body.get('partition_grain') or 'none').strip()
    refresh_policy = str(body.get('refresh_policy') or 'manual').strip()
    strategy = str(body.get('strategy') or 'aggregate_table').strip()
    enabled = bool(body.get('enabled', True))
    mg_id = body.get('measure_group_id') or (
        model['measure_groups'][0]['id']
        if model.get('measure_groups')
        else None
    )

    rule_group_meta: dict[str, Any] = {
        'mandatory_dimensions': mandatory,
        'hierarchy_sets': hierarchy_sets,
        'joint_sets': joint_sets,
    }
    if max_cap is not None:
        rule_group_meta['max_dimension_combinations'] = max_cap

    generated_plans: list[dict[str, Any]] = []
    for idx, cuboid in enumerate(final_cuboids, start=1):
        valid_grain = [g for g in cuboid if g in admitted_set]
        if bool(body.get('save_version')) and len(valid_grain) != len(cuboid):
            unknown = sorted(set(cuboid) - admitted_set)
            raise DesignStoreError(
                'Cannot save aggregation rule referencing unknown cube '
                f"dimension/level: {', '.join(unknown)}"
            )
        grain_for_plan = valid_grain if body.get('save_version') else cuboid
        suffix = '_'.join(cuboid) if cuboid else 'grand_total'
        plan_id = _slug_id(f'agg_{suffix}')
        existing_ids = {p['id'] for p in generated_plans}
        if plan_id in existing_ids:
            plan_id = _slug_id(f'{plan_id}_{idx}')
        label = ' × '.join(cuboid) if cuboid else 'Grand Total'
        plan_entry: dict[str, Any] = {
            'id': plan_id,
            'name': f'Cuboid: {label}',
            'strategy': strategy,
            'enabled': enabled,
            'grain_dimensions': grain_for_plan,
            'measures': list(requested_measures),
            'target_relation': [plan_id],
            'partition_grain': partition_grain,
            'refresh_policy': refresh_policy,
            'rule_group': copy.deepcopy(rule_group_meta),
        }
        if mg_id:
            plan_entry['measure_group_id'] = mg_id
        if partition_field:
            plan_entry['partition_field'] = partition_field
        generated_plans.append(plan_entry)

    saved_design = design
    saved_cube = parsed
    if bool(body.get('save_version')):
        next_model = copy.deepcopy(model)
        if bool(body.get('replace_existing', True)):
            next_model['materializations'] = generated_plans
        else:
            existing_by_id = {
                m['id']: m for m in next_model.get('materializations', [])
            }
            for gp in generated_plans:
                existing_by_id[gp['id']] = gp
            next_model['materializations'] = list(existing_by_id.values())
        sync = CubeDesignSync(store, proc, semantic_service=semantic_service)
        expected_ver = int(
            body.get('expected_head_version') or design['head_version']
        )
        saved_res = sync.save_cube_model(
            design_id,
            expected_head_version=expected_ver,
            actor_id=actor_id,
            model=next_model,
            cube_notes=parsed.get('notes'),
            note=str(
                body.get('note')
                or (
                    f'Applied combinatorial aggregation reducer '
                    f'({naive_count} -> {after_mj_count} -> {final_count})'
                )
            ),
        )
        saved_design = saved_res['design']
        saved_cube = saved_res['cube']

    return {
        'design_id': design_id,
        'candidate_dimensions': candidates,
        'naive_cuboid_count': naive_count,
        'after_mandatory_and_joint_count': after_mj_count,
        'final_cuboid_count': final_count,
        'reduction_summary': (
            f'{naive_count} -> {after_mj_count} -> {final_count}'
        ),
        'cuboids': final_cuboids,
        'generated_plans': generated_plans,
        'saved_version': bool(body.get('save_version')),
        'design': saved_design,
        'cube': saved_cube,
    }


def _match_aggregate_plan(
    model: Mapping[str, Any],
    requested_dims: list[str],
    requested_measures: list[str],
) -> dict[str, Any]:
    req_dim_set = set(requested_dims)
    req_meas_set = set(requested_measures)
    candidates: list[dict[str, Any]] = []
    for mat in model.get('materializations', []):
        if not mat.get('enabled'):
            continue
        grain_set = set(mat.get('grain_dimensions') or [])
        mat_meas = set(mat.get('measures') or [])
        if req_dim_set.issubset(grain_set) and (
            not mat_meas or req_meas_set.issubset(mat_meas)
        ):
            candidates.append(mat)
    if not candidates:
        return {
            'matched': False,
            'materialization_id': None,
            'name': None,
            'target_relation': None,
        }
    best = min(candidates, key=lambda m: len(m.get('grain_dimensions') or []))
    return {
        'matched': True,
        'materialization_id': best['id'],
        'name': best['name'],
        'target_relation': best.get('target_relation') or [best['id']],
        'grain_dimensions': best.get('grain_dimensions') or [],
    }


def execute_cube_try_query(
    store: DesignStore,
    *,
    design_id: str,
    actor_id: int,
    payload: dict[str, Any],
    app=None,
) -> dict[str, Any]:
    """Compile and optionally execute an interactive slice-and-dice query."""
    _ = actor_id
    body = payload if isinstance(payload, Mapping) else {}
    _design, _parsed, model = _load_cube_model_for_design(
        store, design_id, body
    )

    dialect_key = str(body.get('dialect') or 'sqlite').strip().lower()
    if dialect_key == 'mariadb':
        dialect_key = 'mysql'
    dialect_contract = _DIALECT_CONTRACTS.get(dialect_key)
    if dialect_contract is None:
        raise DesignStoreError(f'Unsupported SQL dialect: {dialect_key}')

    role = str(body.get('role') or '').strip() or None
    locale = str(body.get('locale') or '').strip()

    rows_axis = list(
        body.get('rows')
        if isinstance(body.get('rows'), list)
        else (body.get('dimensions') or [])
    )
    cols_axis = list(
        body.get('columns') if isinstance(body.get('columns'), list) else []
    )
    pages_axis = list(
        body.get('pages') if isinstance(body.get('pages'), list) else []
    )
    measures_req = list(
        body.get('measures')
        if isinstance(body.get('measures'), list) and body.get('measures')
        else [m['id'] for m in model.get('measures', [])[:1]]
    )

    query_spec: dict[str, Any] = {
        'axes': {
            'rows': rows_axis,
            'columns': cols_axis,
            'pages': pages_axis,
        },
        'measures': measures_req,
        'filters': list(body.get('filters') or []),
        'totals': bool(body.get('totals', False)),
        'limit': int(body.get('limit') or 100),
    }
    if body.get('perspective'):
        query_spec['perspective'] = str(body['perspective']).strip()
    if body.get('bind') in {'qmark', 'format'}:
        query_spec['bind'] = body['bind']
    if isinstance(body.get('parameters'), Mapping):
        query_spec['parameters'] = dict(body['parameters'])

    try:
        compiled = compile_sql(model, query_spec, dialect_contract, role=role)
        display_model = (
            localize_model(filter_model_for_role(model, role), locale)
            if locale
            else filter_model_for_role(model, role)
        )
    except SemanticModelError as exc:
        raise DesignStoreError(str(exc)) from exc

    label_lookup: dict[str, str] = {}
    for dim in display_model.get('dimensions', []):
        label_lookup[dim['id']] = dim['name']
        for attr in dim.get('attributes', []):
            label_lookup[attr['id']] = attr['name']
        for hier in dim.get('hierarchies', []):
            label_lookup[hier['id']] = hier['name']
            for lvl in hier.get('levels', []):
                label_lookup[lvl['id']] = lvl['name']
    for meas in display_model.get('measures', []):
        label_lookup[meas['id']] = meas['name']

    all_axes = []
    for item in pages_axis + rows_axis + cols_axis:
        if item not in all_axes:
            all_axes.append(item)
    columns_meta = [
        {
            'id': item,
            'label': label_lookup.get(item, item),
            'kind': 'dimension',
        }
        for item in all_axes
    ] + [
        {
            'id': mid,
            'label': label_lookup.get(mid, mid),
            'kind': 'measure',
        }
        for mid in measures_req
    ]

    routing_hit = _match_aggregate_plan(model, all_axes, measures_req)

    preview_rows: list[dict[str, Any]] = []
    executed = False
    conn, _mode = _resolve_sqlite_connection(model, body, app=app)
    if conn is not None:
        try:
            exec_sql = compiled['source']
            exec_params = compiled.get('parameters') or []
            if dialect_key != 'sqlite':
                sq_compiled = compile_sql(
                    model,
                    {**query_spec, 'bind': 'qmark'},
                    _DIALECT_CONTRACTS['sqlite'],
                    role=role,
                )
                exec_sql = sq_compiled['source']
                exec_params = sq_compiled.get('parameters') or []
            cur = conn.execute(
                exec_sql,
                exec_params if isinstance(exec_params, list) else (),
            )
            col_names = [desc[0] for desc in (cur.description or [])]
            for raw_row in cur.fetchall():
                preview_rows.append({
                    col_names[idx]: raw_row[idx]
                    for idx in range(len(col_names))
                })
            executed = True
        except sqlite3.Error as exc:
            raise DesignStoreError(
                f'SQLite Try-a-Query execution failed: {exc}'
            ) from exc
        finally:
            conn.close()

    return {
        'design_id': design_id,
        'dialect': dialect_key,
        'role': role,
        'locale': locale or None,
        'compiled_sql': compiled['source'],
        'parameters': compiled.get('parameters', {}),
        'columns': columns_meta,
        'preview_rows': preview_rows,
        'executed': executed,
        'aggregate_routing_hit': routing_hit,
    }


def _tokenize_keywords(text: str) -> set[str]:
    return {
        tok
        for tok in re.findall(r'[a-z0-9_]{3,}', str(text or '').lower())
        if tok not in {
            'the', 'and', 'for', 'with', 'from', 'cube', 'table', 'by', 'per',
        }
    }


def propose_cube_ai_draft(
    store: DesignStore,
    *,
    project_id: str,
    actor_id: int,
    payload: dict[str, Any],
    app=None,
) -> dict[str, Any]:
    """Search existing cubes first and draft a BYOK Cube proposal for review.

    Honors AGENTS.md:
    - Searches existing cubes in ``store.list_designs(project_id=..., kind='cube')``
      first so authors reuse existing semantic models before creating new ones.
    - Never persists API keys/secrets or writes grants/secrets into DDN.
    - Produces ONLY a Draft proposal / diff (``requires_human_review=True``);
      never accepts, merges, or publishes.
    """
    _ = (actor_id, app)
    body = payload if isinstance(payload, Mapping) else {}
    prompt_text = str(
        body.get('prompt') or body.get('business_question') or ''
    ).strip()
    fact_table_raw = str(body.get('fact_table') or 'orders').strip()
    raw_columns = body.get('columns') or []

    col_specs: list[dict[str, str]] = []
    if isinstance(raw_columns, list):
        for item in raw_columns:
            if isinstance(item, Mapping) and item.get('name'):
                col_specs.append({
                    'name': str(item['name']).strip(),
                    'type': str(item.get('type') or 'text').strip().lower(),
                })
            elif isinstance(item, str) and item.strip():
                parts = item.strip().split(':', 1)
                col_specs.append({
                    'name': parts[0].strip(),
                    'type': (
                        parts[1].strip().lower() if len(parts) > 1 else 'text'
                    ),
                })

    search_tokens = _tokenize_keywords(
        ' '.join([
            prompt_text,
            fact_table_raw,
            ' '.join(c['name'] for c in col_specs),
        ])
    )

    existing_cubes = store.list_designs(project_id=project_id, kind='cube')
    matched_existing: list[dict[str, Any]] = []
    for item in existing_cubes:
        item_id = item.get('id') or item.get('design_id')
        if not item_id:
            continue
        cand_tokens = _tokenize_keywords(
            f"{item.get('title', '')} {item.get('key', '')}"
        )
        try:
            full_doc = store.get_design(item_id)
            c_model = ddn_to_semantic_model(
                full_doc['version']['ddn_text']
            )['model']
            for m_obj in c_model.get('measures', []):
                cand_tokens |= _tokenize_keywords(
                    f"{m_obj['id']} {m_obj['name']}"
                )
            for d_obj in c_model.get('dimensions', []):
                cand_tokens |= _tokenize_keywords(
                    f"{d_obj['id']} {d_obj['name']}"
                )
            for s_obj in c_model.get('sources', []):
                cand_tokens |= _tokenize_keywords(
                    ' '.join(s_obj.get('relation') or [s_obj['id']])
                )
        except Exception:
            pass
        overlap = sorted(search_tokens & cand_tokens)
        if overlap or not search_tokens:
            matched_existing.append({
                'design_id': item_id,
                'key': item['key'],
                'title': item['title'],
                'head_version': item.get('head_version'),
                'active_version': item.get('active_version'),
                'matched_terms': overlap,
                'score': len(overlap),
            })
    matched_existing.sort(
        key=lambda entry: (-entry['score'], entry['title'])
    )

    rel_parts = [
        p.strip() for p in fact_table_raw.split('.') if p.strip()
    ] or ['main', 'orders']
    fact_short = _slug_id(rel_parts[-1])
    fact_src_id = (
        fact_short if not fact_short.startswith('agg_') else 'fact_main'
    )

    if not col_specs:
        col_specs = [
            {'name': f'{fact_src_id}_id', 'type': 'integer'},
            {'name': 'order_date', 'type': 'date'},
            {'name': 'region', 'type': 'text'},
            {'name': 'amount', 'type': 'numeric'},
        ]

    proposed_measures: list[dict[str, Any]] = [
        {
            'id': 'row_count',
            'name': 'Row Count',
            'aggregation': 'count',
            'field': None,
            'format': '#,##0',
            'measure_group_id': f'mg_{fact_src_id}',
        }
    ]
    proposed_dimensions: list[dict[str, Any]] = []
    grain_fields: list[dict[str, str]] = []

    numeric_hints = (
        'amount', 'total', 'revenue', 'sales', 'price', 'cost', 'qty',
        'quantity', 'balance', 'score', 'value', 'margin',
    )
    numeric_types = (
        'int', 'integer', 'bigint', 'numeric', 'decimal', 'real', 'float',
        'double', 'money',
    )
    time_hints = ('date', 'time', '_at', 'month', 'year', 'day', 'period')

    for spec in col_specs:
        cname = spec['name']
        ctype = spec['type']
        cid = _slug_id(cname)
        lower_c = cname.lower()
        title_c = cname.replace('_', ' ').strip().title()

        if lower_c in {'id', f'{fact_src_id}_id'} or lower_c.endswith('_pk'):
            grain_fields.append({'source_id': fact_src_id, 'field': cname})
            continue

        if any(h in lower_c for h in time_hints) or ctype in {
            'date', 'datetime', 'timestamp', 'timestamptz',
        }:
            proposed_dimensions.append({
                'id': cid,
                'name': title_c,
                'field': {'source_id': fact_src_id, 'field': cname},
                'is_time': True,
                'time_role': 'event-time',
                'unknown_member_policy': 'unknown',
                'unknown_member_caption': 'Unknown Date',
                'hierarchies': [{
                    'id': f'{cid}_calendar',
                    'name': f'{title_c} Hierarchy',
                    'hierarchy_kind': 'level',
                    'levels': [{
                        'id': f'{cid}_day',
                        'name': title_c,
                        'field': {'source_id': fact_src_id, 'field': cname},
                        'relationship_type': 'fixed',
                    }],
                }],
            })
        elif lower_c.endswith('_id'):
            stem = _slug_id(lower_c[:-3] or cid)
            proposed_measures.append({
                'id': f'distinct_{stem}',
                'name': f'Distinct {stem.replace("_", " ").title()}',
                'aggregation': 'count_distinct',
                'field': {'source_id': fact_src_id, 'field': cname},
                'format': '#,##0',
                'measure_group_id': f'mg_{fact_src_id}',
            })
            proposed_dimensions.append({
                'id': stem,
                'name': stem.replace('_', ' ').title(),
                'field': {'source_id': fact_src_id, 'field': cname},
                'is_time': False,
                'time_role': None,
                'unknown_member_policy': 'unknown',
                'unknown_member_caption': 'Unknown',
                'hierarchies': [{
                    'id': f'{stem}_default',
                    'name': stem.replace('_', ' ').title(),
                    'levels': [{
                        'id': f'{stem}_key',
                        'name': stem.replace('_', ' ').title(),
                        'field': {'source_id': fact_src_id, 'field': cname},
                        'relationship_type': 'changing',
                    }],
                }],
            })
        elif any(h in lower_c for h in numeric_hints) or any(
            ctype.startswith(nt) for nt in numeric_types
        ):
            proposed_measures.append({
                'id': f'sum_{cid}',
                'name': f'Total {title_c}',
                'aggregation': 'sum',
                'field': {'source_id': fact_src_id, 'field': cname},
                'format': '#,##0.00',
                'measure_group_id': f'mg_{fact_src_id}',
            })
            proposed_measures.append({
                'id': f'avg_{cid}',
                'name': f'Average {title_c}',
                'aggregation': 'avg',
                'field': {'source_id': fact_src_id, 'field': cname},
                'format': '#,##0.00',
                'measure_group_id': f'mg_{fact_src_id}',
            })
        else:
            proposed_dimensions.append({
                'id': cid,
                'name': title_c,
                'field': {'source_id': fact_src_id, 'field': cname},
                'is_time': False,
                'time_role': None,
                'unknown_member_policy': 'unknown',
                'unknown_member_caption': 'Unknown',
                'hierarchies': [{
                    'id': f'{cid}_default',
                    'name': title_c,
                    'levels': [{
                        'id': f'{cid}_level',
                        'name': title_c,
                        'field': {'source_id': fact_src_id, 'field': cname},
                        'relationship_type': 'changing',
                    }],
                }],
            })

    seen_d: set[str] = set()
    dedup_dims = []
    for d in proposed_dimensions:
        if d['id'] not in seen_d:
            seen_d.add(d['id'])
            dedup_dims.append(d)
    proposed_dimensions = dedup_dims

    seen_m: set[str] = set()
    dedup_meas = []
    for m in proposed_measures:
        if m['id'] not in seen_m:
            seen_m.add(m['id'])
            dedup_meas.append(m)
    proposed_measures = dedup_meas

    proposed_aggregations: list[dict[str, Any]] = []
    if proposed_dimensions:
        top_dims = [d['id'] for d in proposed_dimensions[:2]]
        time_dim = next(
            (d for d in proposed_dimensions if d.get('is_time')), None
        )
        agg_plan: dict[str, Any] = {
            'id': _slug_id(f'agg_{"_".join(top_dims)}'),
            'name': f"Summary by {', '.join(top_dims)}",
            'strategy': 'aggregate_table',
            'enabled': False,
            'measure_group_id': f'mg_{fact_src_id}',
            'grain_dimensions': top_dims,
            'measures': [m['id'] for m in proposed_measures[:3]],
            'target_relation': [_slug_id(f'agg_{"_".join(top_dims)}')],
            'partition_grain': 'month' if time_dim else 'none',
            'refresh_policy': 'incremental' if time_dim else 'manual',
        }
        if time_dim:
            agg_plan['partition_field'] = copy.deepcopy(time_dim['field'])
        proposed_aggregations.append(agg_plan)

    cube_title = str(
        body.get('title')
        or f"{rel_parts[-1].replace('_', ' ').title()} Analytical Cube"
    ).strip()

    draft_model = default_cube_model(cube_title)
    draft_model['description'] = (
        prompt_text
        or f'Draft cube proposed from {fact_table_raw} for human review.'
    )[:512]
    draft_model['sources'] = [{
        'id': fact_src_id,
        'resource_id': f"table:{':'.join(rel_parts)}",
        'relation': rel_parts,
        'alias': fact_src_id,
        'source_kind': 'table',
        'classification': 'fact',
        'grain': grain_fields,
    }]
    draft_model['dimensions'] = proposed_dimensions
    draft_model['measures'] = proposed_measures
    draft_model['measure_groups'] = [{
        'id': f'mg_{fact_src_id}',
        'name': f'{cube_title} Measures',
        'fact_source': fact_src_id,
        'measures': [m['id'] for m in proposed_measures],
        'dimension_usage': [
            {
                'dimension_id': d['id'],
                'relationship_kind': 'regular',
                'active': True,
            }
            for d in proposed_dimensions
        ],
    }]
    draft_model['materializations'] = proposed_aggregations
    draft_model['annotations'] = {
        'cube_version_label': '1.0',
        'ai_draft_mode': (
            'byok_configured'
            if str(body.get('api_key') or '').strip()
            else 'local_schema_heuristic'
        ),
    }

    validated_draft = public_model(validate_model(draft_model))
    draft_ddn_text, _ = semantic_model_to_ddn(validated_draft)

    return {
        'status': 'draft',
        'requires_human_review': True,
        'auto_accepted': False,
        'published': False,
        'matched_existing_cubes': matched_existing,
        'proposed_title': cube_title,
        'proposed_measures': proposed_measures,
        'proposed_dimensions': proposed_dimensions,
        'proposed_aggregations': proposed_aggregations,
        'proposed_model': validated_draft,
        'proposed_ddn_text': draft_ddn_text,
        'diff_summary': {
            'existing_matches_found': len(matched_existing),
            'measures_added': len(proposed_measures),
            'dimensions_added': len(proposed_dimensions),
            'aggregations_added': len(proposed_aggregations),
        },
    }

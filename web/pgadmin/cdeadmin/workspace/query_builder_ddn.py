##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Server-computed DDN dataflow workspace for the Visual SQL Builder and BI.

Builds a verified ``ddn-source-workspace@1`` graph (``ddn@1``) using
ScratchRobin's shared DDN encoder (``ddn_source``) and server-side Sugiyama
layout engine (``design_store.shared_ddn.compute_server_layout``) so the
client renders query/CTE dataflow, joins, set operations and fan-out warnings
through the shared ``DDNViewerSurface``.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from pgadmin.cdeadmin.design_store.shared_ddn import compute_server_layout
from pgadmin.cdeadmin.sdk import sql_builder as sdk_sql_builder

from . import ddn_source

MODULE = 'scratchrobin.sql_builder.flow'
ENTRY_FILE = 'query-flow.ddn'
VIEW_ID = 'query_flow'

_IDENT_CLEAN = re.compile(r'[^A-Za-z0-9_]+')


def _slug(raw: Any, fallback: str = 'item') -> str:
    cleaned = _IDENT_CLEAN.sub('_', str(raw or '').strip()).strip('_')
    if not cleaned:
        return fallback
    if cleaned[0].isdigit():
        return f'{fallback}_{cleaned}'
    return cleaned[:64]


def _expr_summary(expr: Any) -> str:
    if not isinstance(expr, Mapping):
        return '?'
    if 'column' in expr:
        cols = expr['column']
        if isinstance(cols, list) and cols:
            return '.'.join(str(part) for part in cols)
        return str(cols)
    if 'value' in expr:
        val = expr['value']
        return 'NULL' if val is None else repr(val)
    if 'aggregate' in expr and isinstance(expr['aggregate'], Mapping):
        agg = expr['aggregate']
        fn = str(agg.get('function') or 'count').upper()
        arg = agg.get('argument')
        arg_txt = '*' if arg == '*' else _expr_summary(arg)
        dist = 'DISTINCT ' if agg.get('distinct') else ''
        return f'{fn}({dist}{arg_txt})'
    if 'window' in expr and isinstance(expr['window'], Mapping):
        win = expr['window']
        fn = str(win.get('function') or 'row_number').upper()
        if fn.lower() in sdk_sql_builder.RANKING_WINDOWS:
            call = f'{fn}()'
        else:
            arg = win.get('argument')
            arg_txt = (
                '*' if (arg is None or arg == '*') else _expr_summary(arg)
            )
            dist = 'DISTINCT ' if win.get('distinct') else ''
            call = f'{fn}({dist}{arg_txt})'
        over_bits: list[str] = []
        pby = win.get('partition_by') or []
        if isinstance(pby, list) and pby:
            over_bits.append(
                'PARTITION BY ' + ', '.join(_expr_summary(p) for p in pby)
            )
        oby = win.get('order_by') or []
        if isinstance(oby, list) and oby:
            over_bits.append(
                'ORDER BY ' + ', '.join(
                    f"{_expr_summary(o.get('expr'))} "
                    f"{str(o.get('direction') or 'asc').upper()}"
                    for o in oby if isinstance(o, Mapping)
                )
            )
        return f"{call} OVER ({' '.join(over_bits)})"
    return '?'


def _select_fanout_metrics(select_obj: Mapping[str, Any]) -> list[str]:
    metrics: list[str] = []
    for idx, col in enumerate(select_obj.get('columns') or []):
        if not isinstance(col, Mapping):
            continue
        expr = col.get('expr')
        if not isinstance(expr, Mapping):
            continue
        alias = str(col.get('alias') or '').strip()
        if 'aggregate' in expr and isinstance(expr['aggregate'], Mapping):
            agg = expr['aggregate']
            fn = str(agg.get('function') or '').lower()
            if fn in ('sum', 'avg') or (
                fn == 'count' and not agg.get('distinct')
            ):
                metrics.append(
                    alias or _expr_summary(expr) or f'col_{idx + 1}'
                )
        elif 'window' in expr and isinstance(expr['window'], Mapping):
            win = expr['window']
            fn = str(win.get('function') or '').lower()
            if fn in ('sum', 'avg') or (
                fn == 'count' and not win.get('distinct')
            ):
                metrics.append(
                    alias or _expr_summary(expr) or f'col_{idx + 1}'
                )
    return metrics


def analyze_builder_fanout(
    model: Mapping[str, Any],
    *,
    join_cardinalities: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Detect aggregate/window fan-out risks across joined relations."""
    if not isinstance(model, Mapping):
        return []
    card_map = dict(join_cardinalities or {})
    warnings: list[dict[str, Any]] = []

    scopes: list[tuple[str, Mapping[str, Any]]] = []
    for cte in model.get('with') or []:
        if isinstance(cte, Mapping):
            cname = str(cte.get('name') or 'cte').strip() or 'cte'
            cquery = cte.get('query')
            if isinstance(cquery, Mapping):
                for s_idx, sel in enumerate(cquery.get('selects') or []):
                    if isinstance(sel, Mapping):
                        scopes.append((f'CTE {cname}#{s_idx + 1}', sel))
    main_q = model.get('query')
    if isinstance(main_q, Mapping):
        for s_idx, sel in enumerate(main_q.get('selects') or []):
            if isinstance(sel, Mapping):
                label = (
                    'Final SELECT'
                    if len(main_q.get('selects') or []) == 1
                    else f'SELECT branch #{s_idx + 1}'
                )
                scopes.append((label, sel))

    for scope_label, sel in scopes:
        joins = [
            j for j in (sel.get('joins') or []) if isinstance(j, Mapping)
        ]
        if not joins:
            continue
        metrics = _select_fanout_metrics(sel)
        if not metrics:
            continue
        metric_list = ', '.join(metrics)
        non_safe_count = 0
        for join in joins:
            jtype = str(join.get('type') or 'inner').lower()
            src = join.get('source') or {}
            if isinstance(src, Mapping) and 'relation' in src:
                rel_parts = src.get('relation') or []
                target_name = (
                    '.'.join(str(p) for p in rel_parts)
                    if isinstance(rel_parts, list) and rel_parts
                    else str(rel_parts or 'relation')
                )
            elif isinstance(src, Mapping) and 'cte' in src:
                target_name = f"CTE {src.get('cte')}"
            else:
                target_name = 'joined source'
            alias = str(join.get('alias') or '').strip()
            card = str(
                join.get('cardinality') or
                card_map.get(alias) or
                card_map.get(target_name) or
                'undeclared'
            ).lower()
            if card not in ('many_to_one', 'one_to_one'):
                non_safe_count += 1
            if jtype == 'cross':
                warnings.append({
                    'code': 'cross_join_fanout',
                    'severity': 'warning',
                    'scope': scope_label,
                    'relation': target_name,
                    'detail': (
                        f'{scope_label}: CROSS JOIN to {target_name} '
                        f'multiplies rows before computing {metric_list}.'
                    ),
                })
            elif card in ('one_to_many', 'many_to_many'):
                warnings.append({
                    'code': 'one_to_many_fanout',
                    'severity': 'warning',
                    'scope': scope_label,
                    'relation': target_name,
                    'detail': (
                        f'{scope_label}: join to {target_name} ({card}) '
                        f'can duplicate rows in {metric_list}.'
                    ),
                })
            elif len(joins) == 1 and card == 'undeclared':
                warnings.append({
                    'code': 'undeclared_join_cardinality',
                    'severity': 'info',
                    'scope': scope_label,
                    'relation': target_name,
                    'detail': (
                        f'{scope_label}: join to {target_name} aggregates '
                        f'{metric_list}; verify the joined key is unique to '
                        f'avoid metric fan-out.'
                    ),
                })
        if len(joins) >= 2 and non_safe_count >= 2:
            warnings.append({
                'code': 'multi_join_fanout',
                'severity': 'warning',
                'scope': scope_label,
                'relation': f'{len(joins)} joins',
                'detail': (
                    f'{scope_label}: {len(joins)} joins are combined with '
                    f'{metric_list}; multi-branch joins can cause chasm/fan '
                    f'traps unless pre-aggregated in a WITH CTE.'
                ),
            })
    return warnings


def build_query_builder_ddn(
    model: Mapping[str, Any],
    *,
    join_cardinalities: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Generate a DDN dataflow workspace, server layout and warnings."""
    if not isinstance(model, Mapping):
        raise ValueError('Query model must be an object.')

    recursive_flag = bool(model.get('recursive', False))
    ctes_raw = [
        c for c in (model.get('with') or []) if isinstance(c, Mapping)
    ]
    raw_q = model.get('query')
    query_raw = raw_q if isinstance(raw_q, Mapping) else {}
    selects_raw = [
        s for s in (query_raw.get('selects') or []) if isinstance(s, Mapping)
    ]

    fanout_warnings = analyze_builder_fanout(
        model, join_cardinalities=join_cardinalities
    )
    warning_relations = {
        w['relation']
        for w in fanout_warnings
        if w.get('severity') == 'warning'
    }

    node_sources: list[str] = []
    node_ids: list[str] = []
    edge_sources: list[str] = []
    edge_triples: list[tuple[str, str, str]] = []
    field_seq = 0
    edge_seq = 0

    base_nodes: dict[str, str] = {}
    cte_nodes: dict[str, str] = {}
    stages: list[dict[str, Any]] = []

    def alloc_field(
        parent_id: str, title: str, datatype: str = 'clause'
    ) -> dict[str, Any]:
        nonlocal field_seq
        field_seq += 1
        fid = f'qfield_{field_seq}_{_slug(parent_id, "n")}'
        return ddn_source.native_field(
            fid,
            title,
            f'uid:{fid}',
            {'datatype': datatype},
        )

    def ensure_source_node(source_spec: Any) -> tuple[str, str, bool]:
        """Return ``(node_id, display_name, is_cte_ref)`` for FROM/JOIN."""
        if isinstance(source_spec, Mapping) and 'cte' in source_spec:
            cname = str(source_spec.get('cte') or '').strip()
            if cname and cname in cte_nodes:
                return cte_nodes[cname], cname, True
            label = cname or '(unselected CTE)'
            key = f'cte_unresolved:{label}'
        elif isinstance(source_spec, Mapping) and 'relation' in source_spec:
            rparts = source_spec.get('relation')
            if isinstance(rparts, list) and rparts:
                label = '.'.join(str(p) for p in rparts if str(p).strip())
            else:
                label = str(rparts or '').strip()
            label = label or '(unselected relation)'
            key = f'rel:{label}'
        else:
            label = '(unselected relation)'
            key = 'rel:__empty__'

        if key not in base_nodes:
            nid = f'qsrc_{len(base_nodes) + 1}_{_slug(label, "rel")}'
            base_nodes[key] = nid
            f_kind = alloc_field(nid, f'source: {label}', 'relation')
            node_sources.append(
                ddn_source.relation_object(
                    nid,
                    label,
                    'table',
                    f'uid:{nid}',
                    {'node_kind': 'relation', 'relation_name': label},
                    [f_kind],
                    MODULE,
                )
            )
            node_ids.append(nid)
        return base_nodes[key], label, False

    def add_edge(src_id: str, tgt_id: str, label: str, edge_kind: str) -> None:
        nonlocal edge_seq
        edge_seq += 1
        eid = f'qedge_{edge_seq}'
        edge_sources.append(
            ddn_source.relation_edge(
                eid,
                label,
                src_id,
                tgt_id,
                f'uid:{eid}',
                {'edge_kind': edge_kind},
                MODULE,
            )
        )
        edge_triples.append((eid, src_id, tgt_id))

    def select_fields(
        node_id: str,
        sel: Mapping[str, Any],
        extra: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        fields: list[dict[str, Any]] = []
        if sel.get('distinct'):
            fields.append(alloc_field(node_id, 'DISTINCT', 'modifier'))
        if sel.get('distinct_on'):
            fields.append(
                alloc_field(node_id, 'DISTINCT ON (...)', 'modifier')
            )
        cols = sel.get('columns') or []
        if not cols:
            fields.append(
                alloc_field(node_id, '* (all columns)', 'projection')
            )
        else:
            for c_item in cols[:8]:
                if not isinstance(c_item, Mapping):
                    continue
                if 'all' in c_item:
                    q = c_item.get('all')
                    fields.append(
                        alloc_field(
                            node_id,
                            f'{q}.*' if q else '*',
                            'projection',
                        )
                    )
                else:
                    summary = _expr_summary(c_item.get('expr'))
                    alias = c_item.get('alias')
                    lbl = f'{summary} AS {alias}' if alias else summary
                    expr_map = c_item.get('expr')
                    if isinstance(expr_map, Mapping) and 'window' in expr_map:
                        dtype = 'window'
                    elif (
                        isinstance(expr_map, Mapping) and
                        'aggregate' in expr_map
                    ):
                        dtype = 'aggregate'
                    else:
                        dtype = 'projection'
                    fields.append(alloc_field(node_id, lbl, dtype))
            if len(cols) > 8:
                fields.append(
                    alloc_field(
                        node_id,
                        f'+{len(cols) - 8} more columns',
                        'projection',
                    )
                )
        if sel.get('where') is not None:
            fields.append(alloc_field(node_id, 'WHERE predicate', 'filter'))
        gb = sel.get('group_by')
        if isinstance(gb, Mapping) and gb.get('kind'):
            fields.append(
                alloc_field(node_id, f"GROUP BY ({gb['kind']})", 'grouping')
            )
        if sel.get('having') is not None:
            fields.append(alloc_field(node_id, 'HAVING filter', 'filter'))
        for note in extra or []:
            fields.append(alloc_field(node_id, note, 'clause'))
        return fields

    def wire_select_inputs(
        sel: Mapping[str, Any],
        target_node_id: str,
        self_cte_name: str | None = None,
    ) -> bool:
        """Connect FROM and JOIN sources of ``sel`` into ``target_node_id``."""
        self_ref = False
        raw_from = sel.get('from')
        from_obj = raw_from if isinstance(raw_from, Mapping) else {}
        src_id, src_label, _ = ensure_source_node(from_obj.get('source'))
        alias = str(from_obj.get('alias') or '').strip()
        if self_cte_name and src_id == target_node_id:
            self_ref = True
            edge_lbl = (
                f'RECURSIVE FROM ({alias})' if alias else 'RECURSIVE FROM'
            )
        else:
            edge_lbl = f'FROM AS {alias}' if alias else 'FROM'
        add_edge(src_id, target_node_id, edge_lbl, 'from')

        for j_item in sel.get('joins') or []:
            if not isinstance(j_item, Mapping):
                continue
            jtype = str(j_item.get('type') or 'inner').lower()
            jkw = sdk_sql_builder.JOINS.get(jtype, 'JOIN')
            jsrc_id, jsrc_label, _ = ensure_source_node(j_item.get('source'))
            jalias = str(j_item.get('alias') or '').strip()
            if self_cte_name and jsrc_id == target_node_id:
                self_ref = True
            warn_tag = (
                ' [fan-out!]'
                if jsrc_label in warning_relations or jtype == 'cross'
                else ''
            )
            jlbl = (
                f'{jkw} AS {jalias}{warn_tag}'
                if jalias
                else f'{jkw}{warn_tag}'
            )
            add_edge(jsrc_id, target_node_id, jlbl, f'join.{jtype}')
        return self_ref

    # 1. CTE stages
    for idx, cte in enumerate(ctes_raw):
        raw_name = str(cte.get('name') or '').strip()
        display_name = raw_name or f'cte_{idx + 1}'
        cte_nid = f'qcte_{idx + 1}_{_slug(display_name, "cte")}'
        if raw_name:
            cte_nodes[raw_name] = cte_nid

        cte_badges: list[str] = []
        if recursive_flag:
            cte_badges.append('RECURSIVE')
        if cte.get('materialized') is True:
            cte_badges.append('MATERIALIZED')
        elif cte.get('materialized') is False:
            cte_badges.append('NOT MATERIALIZED')
        cycle_cfg = cte.get('cycle')
        if isinstance(cycle_cfg, Mapping):
            ccols = ', '.join(str(c) for c in (cycle_cfg.get('columns') or []))
            cte_badges.append(f'CYCLE ({ccols})' if ccols else 'CYCLE')

        title = f'WITH {display_name}' + (
            f" [{' · '.join(cte_badges)}]" if cte_badges else ''
        )
        raw_cq = cte.get('query')
        cquery = raw_cq if isinstance(raw_cq, Mapping) else {}
        cselects = [
            s for s in (cquery.get('selects') or []) if isinstance(s, Mapping)
        ]
        cops = [str(op) for op in (cquery.get('operators') or [])]

        extra_notes: list[str] = []
        if cte.get('columns'):
            extra_notes.append(
                'columns: ' + ', '.join(str(c) for c in cte['columns'])
            )
        if len(cselects) > 1 and cops:
            extra_notes.append(
                'set ops: ' + ', '.join(
                    sdk_sql_builder.SET_OPERATORS.get(op, op.upper())
                    for op in cops
                )
            )
        if isinstance(cycle_cfg, Mapping):
            extra_notes.append(
                f"CYCLE SET {cycle_cfg.get('set_column', 'is_cycle')} "
                f"USING {cycle_cfg.get('using_column', 'path')}"
            )

        first_sel = cselects[0] if cselects else {'columns': []}
        fields = select_fields(cte_nid, first_sel, extra=extra_notes)
        node_sources.append(
            ddn_source.relation_object(
                cte_nid,
                title,
                'view',
                f'uid:{cte_nid}',
                {'node_kind': 'cte', 'cte_name': display_name},
                fields,
                MODULE,
            )
        )
        node_ids.append(cte_nid)

        self_referenced = False
        for csel in cselects:
            if wire_select_inputs(
                csel, cte_nid, self_cte_name=raw_name or None
            ):
                self_referenced = True

        stages.append({
            'id': f'cte:{idx}:{display_name}',
            'node_id': cte_nid,
            'kind': 'cte',
            'index': idx,
            'name': raw_name or None,
            'label': f'WITH {display_name}',
            'recursive': recursive_flag and self_referenced,
            'materialized': cte.get('materialized'),
            'has_cycle': isinstance(cycle_cfg, Mapping),
            'previewable': bool(raw_name),
        })

    # 2. Main query SELECT branches & final output
    operators = [str(op) for op in (query_raw.get('operators') or [])]
    tail_notes: list[str] = []
    if query_raw.get('order_by'):
        tail_notes.append(f"ORDER BY ({len(query_raw['order_by'])})")
    if query_raw.get('limit') is not None:
        lim_txt = f"LIMIT {query_raw['limit']}"
        if query_raw.get('offset') is not None:
            lim_txt += f" OFFSET {query_raw['offset']}"
        tail_notes.append(lim_txt)

    if len(selects_raw) <= 1:
        final_nid = 'qfinal_select'
        sel0 = selects_raw[0] if selects_raw else {'columns': []}
        final_title = 'Final SELECT' + (
            f" ({tail_notes[-1]})" if tail_notes else ''
        )
        fields = select_fields(final_nid, sel0, extra=tail_notes)
        node_sources.append(
            ddn_source.relation_object(
                final_nid,
                final_title,
                'view',
                f'uid:{final_nid}',
                {'node_kind': 'final_select'},
                fields,
                MODULE,
            )
        )
        node_ids.append(final_nid)
        wire_select_inputs(sel0, final_nid)
    else:
        branch_ids: list[str] = []
        for b_idx, b_sel in enumerate(selects_raw):
            bnid = f'qbranch_{b_idx + 1}'
            btitle = f'SELECT Branch #{b_idx + 1}'
            bfields = select_fields(bnid, b_sel)
            node_sources.append(
                ddn_source.relation_object(
                    bnid,
                    btitle,
                    'view',
                    f'uid:{bnid}',
                    {'node_kind': 'select_branch', 'branch_index': b_idx},
                    bfields,
                    MODULE,
                )
            )
            node_ids.append(bnid)
            wire_select_inputs(b_sel, bnid)
            branch_ids.append(bnid)

        final_nid = 'qfinal_select'
        op_labels = [
            sdk_sql_builder.SET_OPERATORS.get(op, op.upper())
            for op in operators
        ]
        final_title = (
            'Compound Result (' + ' / '.join(op_labels or ['SET']) + ')'
        )
        final_fields = [
            alloc_field(
                final_nid, f'{len(branch_ids)} SELECT branches', 'clause'
            ),
            *[alloc_field(final_nid, note, 'clause') for note in tail_notes],
        ]
        node_sources.append(
            ddn_source.relation_object(
                final_nid,
                final_title,
                'view',
                f'uid:{final_nid}',
                {'node_kind': 'final_select'},
                final_fields,
                MODULE,
            )
        )
        node_ids.append(final_nid)
        for b_idx, bnid in enumerate(branch_ids):
            raw_op = (
                operators[b_idx - 1]
                if b_idx - 1 < len(operators)
                else 'union_all'
            )
            edge_op = (
                'First SELECT'
                if b_idx == 0
                else sdk_sql_builder.SET_OPERATORS.get(raw_op, 'UNION ALL')
            )
            add_edge(bnid, final_nid, edge_op, 'set_op')

    stages.append({
        'id': 'final',
        'node_id': final_nid,
        'kind': 'final',
        'index': None,
        'name': None,
        'label': 'Final Query',
        'recursive': False,
        'materialized': None,
        'has_cycle': False,
        'previewable': True,
    })

    view_source = ddn_source.graph_view(
        VIEW_ID,
        'Query & CTE Dataflow',
        node_ids,
        edge_triples,
    )
    ddn_text = (
        ddn_source.header(MODULE) +
        ''.join(node_sources) +
        ''.join(edge_sources) +
        view_source
    )
    ws = ddn_source.workspace({ENTRY_FILE: ddn_text}, ENTRY_FILE, VIEW_ID)
    ddn_source.validate_workspace(ws, label='SQL builder DDN')
    layout = compute_server_layout(ddn_text, view_id=VIEW_ID)

    return {
        **ws,
        'layout': layout,
        'stages': stages,
        'fanout_warnings': fanout_warnings,
    }

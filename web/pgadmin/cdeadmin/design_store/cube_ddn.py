##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Cube (semantic model) Store <-> DDN bridge, 3-way diff and review plans.

Implements the 2026-11-08 and 2026-11-10 owner decisions (C1-C4):
- C1: Full dimensional DDN profile (``cube.dimensional@1``) in DDN text while
  the ScratchRobin semantic-model store holds the active implementation.
- C2: Dimension usage matrix rendered as ``matrix.relations@1`` and
  aggregation plan grid rendered as ``table.records@1`` in the shared viewer.
- C3: Dimension entities (key/name/sort/attributes), level & parent-child
  hierarchies, role-playing dimensions with ``active`` flag, measure groups +
  dimension usage, filtered & semi-additive measures, perspectives,
  translations, and aggregation/materialization plans.
- C4: External SML (v1.8) and Apache Ossie (v0.2.0) export with explicit loss
  reporting.
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Mapping

from pgadmin.cdeadmin.semantic_models import (
    SEMI_ADDITIVE_AGGREGATIONS,
    SemanticModelError,
    public_model,
    validate_model,
)
from pgadmin.cdeadmin.semantic_models.compiler import compile_sql

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
)
from .shared_ddn import StoreDDNProcess

CUBE_MODULE = 'scratchrobin.cube.dimensional@1'
CUBE_PROFILE = 'cube.dimensional@1'
USAGE_MATRIX_PROFILE = 'matrix.relations@1'
AGGREGATION_GRID_PROFILE = 'table.records@1'

CUBE_VIEWS = (
    ('cube_star', CUBE_PROFILE, 'Dimensional Star Diagram'),
    ('cube_usage_matrix', USAGE_MATRIX_PROFILE, 'Dimension Usage Matrix'),
    ('cube_aggregation_grid', AGGREGATION_GRID_PROFILE, 'Aggregation Grid'),
)

_PORTABLE_DIALECTS: dict[str, dict[str, Any]] = {
    'postgresql': {
        'contract_complete': True,
        'language_profile': 'postgresql',
        'quote_open': '"',
        'quote_close': '"',
        'supports_rollup': True,
        'rollup_style': 'function',
        'limit_style': 'limit',
        'true_literal': 'TRUE',
        'false_literal': 'FALSE',
        'time_operations': [
            'as_of', 'range', 'period_to_date', 'period_comparison',
        ],
        'window_operations': [
            'running_sum', 'moving_sum', 'moving_average', 'lag', 'delta',
            'percent_change', 'rank', 'dense_rank',
        ],
    },
    'duckdb': {
        'contract_complete': True,
        'language_profile': 'duckdb',
        'quote_open': '"',
        'quote_close': '"',
        'supports_rollup': True,
        'rollup_style': 'function',
        'limit_style': 'limit',
        'true_literal': 'TRUE',
        'false_literal': 'FALSE',
        'time_operations': [
            'as_of', 'range', 'period_to_date', 'period_comparison',
        ],
        'window_operations': [
            'running_sum', 'moving_sum', 'moving_average', 'lag', 'delta',
            'percent_change', 'rank', 'dense_rank',
        ],
    },
    'sqlite': {
        'contract_complete': True,
        'language_profile': 'sqlite',
        'quote_open': '"',
        'quote_close': '"',
        'supports_rollup': False,
        'rollup_style': 'function',
        'limit_style': 'limit',
        'true_literal': '1',
        'false_literal': '0',
        'time_operations': [
            'as_of', 'range', 'period_to_date', 'period_comparison',
        ],
        'window_operations': [
            'running_sum', 'moving_sum', 'moving_average', 'lag', 'delta',
            'percent_change', 'rank', 'dense_rank',
        ],
    },
    'firebird': {
        'contract_complete': True,
        'language_profile': 'firebird',
        'quote_open': '"',
        'quote_close': '"',
        'supports_rollup': False,
        'rollup_style': 'function',
        'limit_style': 'rows',
        'true_literal': 'TRUE',
        'false_literal': 'FALSE',
        'time_operations': [
            'as_of', 'range', 'period_to_date', 'period_comparison',
        ],
        'window_operations': [
            'running_sum', 'moving_sum', 'moving_average', 'lag', 'delta',
            'percent_change', 'rank', 'dense_rank',
        ],
    },
    'mysql': {
        'contract_complete': True,
        'language_profile': 'mysql',
        'quote_open': '`',
        'quote_close': '`',
        'supports_rollup': True,
        'rollup_style': 'with_rollup',
        'limit_style': 'limit',
        'true_literal': 'TRUE',
        'false_literal': 'FALSE',
        'time_operations': [
            'as_of', 'range', 'period_to_date', 'period_comparison',
        ],
        'window_operations': [
            'running_sum', 'moving_sum', 'moving_average', 'lag', 'delta',
            'percent_change', 'rank', 'dense_rank',
        ],
    },
    'mariadb': {
        'contract_complete': True,
        'language_profile': 'mariadb',
        'quote_open': '`',
        'quote_close': '`',
        'supports_rollup': True,
        'rollup_style': 'with_rollup',
        'limit_style': 'limit',
        'true_literal': 'TRUE',
        'false_literal': 'FALSE',
        'time_operations': [
            'as_of', 'range', 'period_to_date', 'period_comparison',
        ],
        'window_operations': [
            'running_sum', 'moving_sum', 'moving_average', 'lag', 'delta',
            'percent_change', 'rank', 'dense_rank',
        ],
    },
}


def _q(value: Any) -> str:
    text = str(value if value is not None else '')
    text = text.replace('\r\n', ' ').replace('\n', ' ')
    return '"' + text.replace('"', '""') + '"'


def _json_str(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


def _field_label(ref: dict[str, Any] | None) -> str:
    if not isinstance(ref, dict):
        return ''
    src = ref.get('source_id') or ''
    col = ref.get('field') or ''
    return f'{src}.{col}' if src and col else col


def _alloc_id(
    element_ids: dict[str, str],
    logical_key: str,
) -> str:
    existing = element_ids.get(logical_key)
    if existing and is_uuid7(existing):
        return existing
    fresh = uuid7()
    element_ids[logical_key] = fresh
    return fresh


def default_cube_model(
    name: str = 'New Cube',
    *,
    fact_relation: list[str] | None = None,
    resource_id: str = 'table:main:fact_table',
) -> dict[str, Any]:
    """Build a valid starter semantic model for a new Cube design."""
    rel = fact_relation or ['main', 'fact_table']
    fact_id = 'fact_main'
    model = {
        'contract_version': '1.0.0',
        'name': name.strip() or 'New Cube',
        'description': '',
        'semantic_family': 'relational',
        'sources': [{
            'id': fact_id,
            'resource_id': resource_id,
            'relation': list(rel),
            'alias': fact_id,
            'source_kind': 'table',
            'classification': 'fact',
            'grain': [],
            'provider_config': {},
        }],
        'joins': [],
        'relationships': [],
        'dimensions': [],
        'measures': [{
            'id': 'row_count',
            'name': 'Row count',
            'aggregation': 'count',
            'field': None,
            'format': '0',
        }],
        'measure_groups': [{
            'id': 'default_measures',
            'name': 'Default Measure Group',
            'fact_source': fact_id,
            'measures': ['row_count'],
            'dimension_usage': [],
        }],
        'parameters': [],
        'default_filters': [],
        'materializations': [],
        'security': {'row_filters': [], 'tenant_filter': None, 'roles': []},
        'visualizations': [],
        'dashboards': [],
        'schedules': [],
        'reports': [],
        'annotations': {},
    }
    return public_model(validate_model(model))


def _effective_measure_groups(model: dict[str, Any]) -> list[dict[str, Any]]:
    """Return declared measure_groups or synthesize from fact sources."""
    if model.get('measure_groups'):
        return copy.deepcopy(model['measure_groups'])
    fact_sources = [
        s for s in model['sources'] if s.get('classification') == 'fact'
    ] or model['sources'][:1]
    primary = fact_sources[0]
    usages = [
        {
            'dimension_id': dim['id'],
            'relationship_kind': 'regular',
            'active': bool(dim.get('active', True)),
            **(
                {'join_id': dim['join_id']}
                if dim.get('join_id') else {}
            ),
        }
        for dim in model['dimensions']
    ]
    return [{
        'id': f"mg_{primary['id']}",
        'name': f"{model['name']} Measures",
        'fact_source': primary['id'],
        'measures': [m['id'] for m in model['measures']],
        'dimension_usage': usages,
    }]


def _emit_inline_table(
    lines: list[str],
    columns: list[tuple[str, str]],
    rows: list[list[str]],
) -> None:
    if not rows:
        return
    lines.append('        data')
    lines.append('            columns')
    for col_id, col_label in columns:
        lines.append('                item')
        lines.append(f'                    id {_q(col_id)}')
        lines.append(f'                    label {_q(col_label)}')
    lines.append('            rows')
    for row in rows:
        lines.append('                item')
        for cell in row:
            lines.append(f'                    item {_q(cell)}')


def _emit_companion_record(
    lines: list[str],
    record_id: str,
    *,
    block_kind: str,
    subject_id: str,
    logical_name: str,
    fields: dict[str, str],
    resource_id: str | None = None,
) -> None:
    lines.extend([
        f'element {_q(record_id)} as "record"',
        '    with',
        f'        id {_q(record_id)}',
        f'        title {_q(f"{block_kind}:{logical_name}")}',
        '        metadata',
        '            x_record',
        f'                module {_q(CUBE_MODULE)}',
        f'                block {_q(block_kind)}',
        f'                name_json {_q(json.dumps(logical_name))}',
        '                record',
        f'                    subject_id {_q(subject_id)}',
    ])
    if resource_id:
        lines.append(f'                    resource_id {_q(resource_id)}')
    for key, val in sorted(fields.items()):
        lines.append(f'                    {key} {_q(val)}')
    lines.append('')


def semantic_model_to_ddn(
    model_value: dict[str, Any],
    *,
    element_ids: dict[str, str] | None = None,
    cube_notes: list[str] | None = None,
    highlighted_changes: dict[str, str] | None = None,
) -> tuple[str, dict[str, str]]:
    """Serialize a validated semantic model into multi-view Cube DDN text.

    Returns ``(ddn_text, element_ids_map)`` where ``element_ids_map`` maps
    logical cube symbol keys (e.g. ``cube``, ``dimension:customer``) to their
    stable UUIDv7 DDN element IDs.
    """
    try:
        normalized = public_model(validate_model(model_value))
    except SemanticModelError as exc:
        raise DesignStoreError(str(exc)) from exc

    id_map: dict[str, str] = dict(element_ids or {})
    highlights = dict(highlighted_changes or {})
    notes_list = [
        str(n) for n in (
            cube_notes
            if cube_notes is not None
            else normalized.get('annotations', {}).get('ddn_notes', [])
        )
        if str(n).strip()
    ]

    lines: list[str] = [f'version {DEFAULT_DIALECT}', '']

    cube_el_id = _alloc_id(id_map, 'cube')
    cube_rec_id = _alloc_id(id_map, 'record:cube')
    minor_version = str(
        normalized.get('annotations', {}).get('cube_version_label') or '1.0'
    )
    cube_rows = [
        ['Family', normalized['semantic_family']],
        ['Version', minor_version],
        ['Sources', str(len(normalized['sources']))],
        ['Dimensions', str(len(normalized['dimensions']))],
        ['Measures', str(len(normalized['measures']))],
        ['Aggregations', str(len(normalized['materializations']))],
    ]
    if normalized.get('description'):
        cube_rows.insert(0, ['Description', normalized['description']])
    if normalized.get('perspectives'):
        cube_rows.append([
            'Perspectives', str(len(normalized['perspectives'])),
        ])
    if normalized.get('translations'):
        locales_lbl = ', '.join(
            t['locale'] for t in normalized['translations']
        )
        cube_rows.append(['Translations', locales_lbl])
    if normalized.get('description'):
        lines.append(
            '// @cube.description: '
            + json.dumps(normalized['description'], ensure_ascii=False)
        )
    lines.extend([
        f'element {_q(cube_el_id)} as "cube"',
        '    with',
        f'        id {_q(cube_el_id)}',
        f'        title {_q(normalized["name"])}',
    ])
    _emit_inline_table(
        lines,
        [('property', 'Property'), ('value', 'Value')],
        cube_rows,
    )
    if notes_list:
        lines.append('        notes')
        for note_item in notes_list:
            lines.append(f'            item {_q(note_item)}')
    lines.append('')

    preserved_envelope = {
        'contract_version': normalized['contract_version'],
        'description': normalized['description'],
        'semantic_family': normalized['semantic_family'],
        'sources': normalized['sources'],
        'joins': normalized['joins'],
        'relationships': normalized['relationships'],
        'has_explicit_measure_groups': 'measure_groups' in normalized,
        'has_explicit_perspectives': 'perspectives' in normalized,
        'has_explicit_translations': 'translations' in normalized,
        'parameters': normalized['parameters'],
        'default_filters': normalized['default_filters'],
        'security': normalized['security'],
        'visualizations': normalized['visualizations'],
        'dashboards': normalized['dashboards'],
        'schedules': normalized['schedules'],
        'reports': normalized['reports'],
        'annotations': normalized['annotations'],
    }

    sources_by_id = {s['id']: s for s in normalized['sources']}
    groups = _effective_measure_groups(normalized)
    group_el_ids: dict[str, str] = {}
    star_items: list[str] = [cube_el_id]
    matrix_items: list[str] = []
    agg_record_ids: list[str] = []

    for group in groups:
        gid = group['id']
        gel_id = _alloc_id(id_map, f'measure_group:{gid}')
        grec_id = _alloc_id(id_map, f'record:measure_group:{gid}')
        group_el_ids[gid] = gel_id
        star_items.append(gel_id)
        matrix_items.append(gel_id)
        fsrc = sources_by_id.get(group['fact_source'], {})
        rel_path = '.'.join(fsrc.get('relation', []))
        grain_cols = ', '.join(
            g.get('field', '') for g in fsrc.get('grain', [])
        ) or '(row)'
        g_rows = [
            ['Fact source', rel_path or group['fact_source']],
            ['Grain', grain_cols],
            ['Measures', ', '.join(group.get('measures', [])) or '(none)'],
        ]
        lines.extend([
            f'element {_q(gel_id)} as "fact"',
            '    with',
            f'        id {_q(gel_id)}',
            f'        title {_q(group["name"])}',
        ])
        _emit_inline_table(
            lines,
            [('attribute', 'Attribute'), ('detail', 'Detail')],
            g_rows,
        )
        lines.append('')
        _emit_companion_record(
            lines,
            grec_id,
            block_kind='measure_group',
            subject_id=gel_id,
            logical_name=gid,
            fields={'group_json': _json_str(group)},
            resource_id=fsrc.get('resource_id'),
        )
        own_rel = _alloc_id(id_map, f'rel:cube_owns_mg:{gid}')
        star_items.append(own_rel)
        if not normalized['dimensions']:
            if cube_el_id not in matrix_items:
                matrix_items.append(cube_el_id)
            matrix_items.append(own_rel)
        lines.extend([
            f'relation {_q(own_rel)} as "uses"',
            f'    endpoint {_q(cube_el_id)}',
            f'    endpoint {_q(gel_id)}',
            '    with',
            f'        id {_q(own_rel)}',
            '        title "measure group"',
            '',
        ])

    dim_el_ids: dict[str, str] = {}
    for dim in normalized['dimensions']:
        did = dim['id']
        del_id = _alloc_id(id_map, f'dimension:{did}')
        drec_id = _alloc_id(id_map, f'record:dimension:{did}')
        dim_el_ids[did] = del_id
        star_items.append(del_id)
        matrix_items.append(del_id)
        dim_src = sources_by_id.get(dim['field']['source_id'], {})
        key_ref = dim.get('key_field') or dim['field']
        d_rows = [['Key', _field_label(key_ref)]]
        if dim.get('name_field'):
            d_rows.append(['Name', _field_label(dim['name_field'])])
        if dim.get('sort_field'):
            d_rows.append(['Sort', _field_label(dim['sort_field'])])
        if dim.get('role_of'):
            state_lbl = (
                'active' if dim.get('active', True) else 'inactive'
            )
            d_rows.append(['Role of', f"{dim['role_of']} ({state_lbl})"])
        if (
            dim.get('unknown_member_policy')
            or dim.get('unknown_member_caption')
        ):
            um_pol = dim.get('unknown_member_policy', 'unknown')
            um_cap = dim.get('unknown_member_caption', 'Unknown')
            d_rows.append([
                'Unknown member',
                f'{um_pol} ({um_cap})' if um_pol == 'unknown' else um_pol,
            ])
        if dim.get('visible_roles'):
            d_rows.append([
                'Visible roles', ', '.join(dim['visible_roles']),
            ])
        for attr in dim.get('attributes', []):
            rel_tag = (
                ' (fixed)'
                if attr.get('relationship_type') == 'fixed'
                else ''
            )
            d_rows.append([
                f"Attr{rel_tag}: {attr['name']}",
                _field_label(attr.get('field')),
            ])
        for hier in dim.get('hierarchies', []):
            if hier.get('hierarchy_kind') == 'parent_child':
                c_lbl = _field_label(hier.get('child_field'))
                p_lbl = _field_label(hier.get('parent_field'))
                d_max = hier.get('max_depth', 16)
                d_rows.append([
                    f"Hierarchy (P-C): {hier['name']}",
                    f'{c_lbl} -> {p_lbl} (max {d_max})',
                ])
            else:
                lvl_names = ' > '.join(
                    lvl['name'] for lvl in hier.get('levels', [])
                )
                tag = ' (ragged)' if hier.get('ragged') else ''
                d_rows.append([f"Hierarchy{tag}: {hier['name']}", lvl_names])

        lines.extend([
            f'element {_q(del_id)} as "dimension"',
            '    with',
            f'        id {_q(del_id)}',
            f'        title {_q(dim["name"])}',
        ])
        _emit_inline_table(
            lines,
            [('role', 'Role'), ('binding', 'Binding')],
            d_rows,
        )
        lines.append('')
        _emit_companion_record(
            lines,
            drec_id,
            block_kind='dimension',
            subject_id=del_id,
            logical_name=did,
            fields={'dimension_json': _json_str(dim)},
            resource_id=dim_src.get('resource_id'),
        )

    for dim in normalized['dimensions']:
        role_of = dim.get('role_of')
        if role_of and role_of in dim_el_ids:
            rel_id = _alloc_id(
                id_map, f"rel:role_of:{dim['id']}->{role_of}"
            )
            star_items.append(rel_id)
            active_tag = 'active' if dim.get('active', True) else 'inactive'
            lines.extend([
                f'relation {_q(rel_id)} as "derives"',
                f'    endpoint {_q(dim_el_ids[dim["id"]])}',
                f'    endpoint {_q(dim_el_ids[role_of])}',
                '    with',
                f'        id {_q(rel_id)}',
                f'        title {_q(f"role ({active_tag})")}',
                '',
            ])

    for group in groups:
        gid = group['id']
        gel_id = group_el_ids[gid]
        for usage in group.get('dimension_usage', []):
            did = usage['dimension_id']
            if did not in dim_el_ids:
                continue
            urel_id = _alloc_id(id_map, f'rel:usage:{gid}:{did}')
            star_items.append(urel_id)
            matrix_items.append(urel_id)
            kind_lbl = usage.get('relationship_kind', 'regular')
            active_lbl = (
                'active' if usage.get('active', True) else 'inactive'
            )
            gran = _field_label(usage.get('granularity_field'))
            label = f'{kind_lbl} ({active_lbl})'
            if gran:
                label = f'{gran} [{label}]'
            lines.extend([
                f'relation {_q(urel_id)} as "uses"',
                f'    endpoint {_q(gel_id)}',
                f'    endpoint {_q(dim_el_ids[did])}',
                '    with',
                f'        id {_q(urel_id)}',
                f'        title {_q(label)}',
                '        properties',
                '            source_mark "many"',
                '            target_mark "one"',
                '',
            ])

    measure_el_ids: dict[str, str] = {}
    default_mg_el = next(iter(group_el_ids.values()), cube_el_id)
    for measure in normalized['measures']:
        mid = measure['id']
        mel_id = _alloc_id(id_map, f'measure:{mid}')
        mrec_id = _alloc_id(id_map, f'record:measure:{mid}')
        measure_el_ids[mid] = mel_id
        star_items.append(mel_id)
        m_rows = [['Aggregation', measure['aggregation'].upper()]]
        if measure['aggregation'] in SEMI_ADDITIVE_AGGREGATIONS:
            sa_dim = measure.get('semi_additive_dimension') or ''
            w_agg = measure.get('within_group_aggregation', 'sum')
            m_rows.append([
                'Semi-additive',
                f"{measure['aggregation']} over {sa_dim} ({w_agg})",
            ])
        if measure.get('field'):
            m_rows.append(['Field', _field_label(measure['field'])])
        elif measure.get('expression'):
            m_rows.append(['Expression', _json_str(measure['expression'])])
        if measure.get('display_folder'):
            m_rows.append(['Folder', measure['display_folder']])
        if measure.get('format'):
            m_rows.append(['Format', measure['format']])
        if measure.get('visible_roles'):
            m_rows.append([
                'Visible roles', ', '.join(measure['visible_roles']),
            ])
        m_filters = measure.get('filters') or []
        if m_filters:
            summary = '; '.join(
                f"{_field_label(f.get('field'))} {f.get('operator')} "
                f"{f.get('value', f.get('parameter_id', ''))}"
                for f in m_filters
            )
            m_rows.append(['Filter', summary])
        cert = measure.get('certification', {}).get('status')
        if cert and cert != 'uncertified':
            m_rows.append(['Certification', cert])

        lines.extend([
            f'element {_q(mel_id)} as "metric"',
            '    with',
            f'        id {_q(mel_id)}',
            f'        title {_q(measure["name"])}',
        ])
        _emit_inline_table(
            lines,
            [('property', 'Property'), ('definition', 'Definition')],
            m_rows,
        )
        lines.append('')
        _emit_companion_record(
            lines,
            mrec_id,
            block_kind='measure',
            subject_id=mel_id,
            logical_name=mid,
            fields={'measure_json': _json_str(measure)},
        )
        owner_mg = group_el_ids.get(
            measure.get('measure_group_id') or '', default_mg_el
        )
        mrel_id = _alloc_id(id_map, f'rel:aggregates:{mid}')
        star_items.append(mrel_id)
        lines.extend([
            f'relation {_q(mrel_id)} as "aggregates"',
            f'    endpoint {_q(owner_mg)}',
            f'    endpoint {_q(mel_id)}',
            '    with',
            f'        id {_q(mrel_id)}',
            f'        title {_q(measure["aggregation"])}',
            '',
        ])

    for mat in normalized['materializations']:
        mat_id = mat['id']
        ael_id = _alloc_id(id_map, f'materialization:{mat_id}')
        arec_id = _alloc_id(id_map, f'record:materialization:{mat_id}')
        star_items.append(ael_id)
        agg_record_ids.append(arec_id)

        grain_str = ', '.join(mat.get('grain_dimensions') or []) or '(all)'
        meas_str = ', '.join(mat.get('measures') or []) or '(all)'
        target_str = '.'.join(mat.get('target_relation') or []) or mat_id
        enabled_str = 'enabled' if mat.get('enabled') else 'disabled'
        db_change = highlights.get(mat_id, 'unchanged') or 'unchanged'
        p_field = mat.get('partition_field')
        if isinstance(p_field, Mapping):
            p_field_str = _field_label(p_field)
        else:
            p_field_str = str(p_field or '').strip()
        p_grain = str(mat.get('partition_grain') or 'none').strip()
        if p_field_str and p_grain and p_grain != 'none':
            partition_str = f'{p_field_str} ({p_grain})'
        elif p_field_str:
            partition_str = p_field_str
        elif p_grain and p_grain != 'none':
            partition_str = p_grain
        else:
            partition_str = '—'
        refresh_str = str(mat.get('refresh_policy') or 'manual').strip() or '—'

        a_rows = [
            ['Strategy', mat['strategy']],
            ['Grain', grain_str],
            ['Measures', meas_str],
            ['Target', target_str],
            ['State', enabled_str],
        ]
        if partition_str != '—':
            a_rows.append(['Partition', partition_str])
        if mat.get('refresh_policy'):
            a_rows.append(['Refresh', refresh_str])
        if db_change != 'unchanged':
            a_rows.append(['DB review', f'HIGHLIGHT: {db_change}'])

        lines.extend([
            f'element {_q(ael_id)} as "aggregate"',
            '    with',
            f'        id {_q(ael_id)}',
            f'        title {_q(mat["name"])}',
        ])
        _emit_inline_table(
            lines,
            [('setting', 'Setting'), ('value', 'Value')],
            a_rows,
        )
        lines.append('')
        _emit_companion_record(
            lines,
            arec_id,
            block_kind='materialization',
            subject_id=ael_id,
            logical_name=mat_id,
            fields={
                'materialization_json': _json_str(mat),
                'rule_name': mat['name'] or '—',
                'measure_group': mat.get('measure_group_id') or '(default)',
                'grain_dimensions': grain_str or '—',
                'measures': meas_str or '—',
                'strategy': mat.get('strategy') or '—',
                'target_relation': target_str or '—',
                'partition': partition_str or '—',
                'refresh_policy': refresh_str or '—',
                'enabled': enabled_str or '—',
                'db_review': db_change or 'unchanged',
            },
        )
        for m_ref in (mat.get('measures') or list(measure_el_ids)[:1]):
            if m_ref in measure_el_ids:
                arel_id = _alloc_id(
                    id_map, f'rel:mat_measure:{mat_id}:{m_ref}'
                )
                star_items.append(arel_id)
                lines.extend([
                    f'relation {_q(arel_id)} as "uses"',
                    f'    endpoint {_q(measure_el_ids[m_ref])}',
                    f'    endpoint {_q(ael_id)}',
                    '    with',
                    f'        id {_q(arel_id)}',
                    '        title "materializes"',
                    '',
                ])

    for persp in normalized.get('perspectives', []):
        pid = persp['id']
        pel_id = _alloc_id(id_map, f'perspective:{pid}')
        prec_id = _alloc_id(id_map, f'record:perspective:{pid}')
        star_items.append(pel_id)
        p_rows = [
            [
                'Dimensions',
                ', '.join(persp.get('dimensions') or []) or '(none)',
            ],
            ['Measures', ', '.join(persp.get('measures') or []) or '(groups)'],
        ]
        if persp.get('description'):
            p_rows.insert(0, ['Description', persp['description']])
        if persp.get('measure_groups'):
            p_rows.append([
                'Measure groups', ', '.join(persp['measure_groups']),
            ])
        if persp.get('default_measure'):
            p_rows.append(['Default measure', persp['default_measure']])
        if persp.get('visible_roles'):
            p_rows.append([
                'Visible roles', ', '.join(persp['visible_roles']),
            ])
        if persp.get('description'):
            lines.append(
                f'// @cube.perspective_description {pid}: '
                + json.dumps(persp['description'], ensure_ascii=False)
            )
        lines.extend([
            f'element {_q(pel_id)} as "semantic_model"',
            '    with',
            f'        id {_q(pel_id)}',
            f'        title {_q(persp["name"])}',
        ])
        _emit_inline_table(
            lines,
            [('scope', 'Scope'), ('included', 'Included')],
            p_rows,
        )
        lines.append('')
        _emit_companion_record(
            lines,
            prec_id,
            block_kind='perspective',
            subject_id=pel_id,
            logical_name=pid,
            fields={'perspective_json': _json_str(persp)},
        )
        prel_id = _alloc_id(id_map, f'rel:perspective_of:{pid}')
        star_items.append(prel_id)
        lines.extend([
            f'relation {_q(prel_id)} as "derives"',
            f'    endpoint {_q(pel_id)}',
            f'    endpoint {_q(cube_el_id)}',
            '    with',
            f'        id {_q(prel_id)}',
            '        title "perspective"',
            '',
        ])
        for p_dim in persp.get('dimensions', []):
            if p_dim in dim_el_ids:
                ud_id = _alloc_id(id_map, f'rel:persp_dim:{pid}:{p_dim}')
                star_items.append(ud_id)
                lines.extend([
                    f'relation {_q(ud_id)} as "uses"',
                    f'    endpoint {_q(pel_id)}',
                    f'    endpoint {_q(dim_el_ids[p_dim])}',
                    '    with',
                    f'        id {_q(ud_id)}',
                    '        title "exposes"',
                    '',
                ])
        for p_meas in persp.get('measures', []):
            if p_meas in measure_el_ids:
                um_id = _alloc_id(id_map, f'rel:persp_meas:{pid}:{p_meas}')
                star_items.append(um_id)
                lines.extend([
                    f'relation {_q(um_id)} as "uses"',
                    f'    endpoint {_q(pel_id)}',
                    f'    endpoint {_q(measure_el_ids[p_meas])}',
                    '    with',
                    f'        id {_q(um_id)}',
                    '        title "exposes"',
                    '',
                ])

    for tr in normalized.get('translations', []):
        tid = tr['id']
        trec_id = _alloc_id(id_map, f'record:translation:{tid}')
        _emit_companion_record(
            lines,
            trec_id,
            block_kind='translation',
            subject_id=cube_el_id,
            logical_name=tr['locale'],
            fields={'translation_json': _json_str(tr)},
        )

    if not agg_record_ids:
        empty_agg_rec_id = _alloc_id(
            id_map, 'record:materialization:__empty__'
        )
        agg_record_ids.append(empty_agg_rec_id)
        _emit_companion_record(
            lines,
            empty_agg_rec_id,
            block_kind='materialization_empty',
            subject_id=cube_el_id,
            logical_name='(none)',
            fields={
                'rule_name': '(no aggregation rules defined)',
                'measure_group': '—',
                'grain_dimensions': '—',
                'measures': '—',
                'strategy': '—',
                'target_relation': '—',
                'partition': '—',
                'refresh_policy': '—',
                'enabled': '—',
                'db_review': '—',
            },
        )

    preserved_envelope['element_ids'] = dict(id_map)
    _emit_companion_record(
        lines,
        cube_rec_id,
        block_kind='cube_root',
        subject_id=cube_el_id,
        logical_name=normalized['name'],
        fields={'envelope_json': _json_str(preserved_envelope)},
    )

    cube_title = normalized['name']
    # 1. Dimensional star view (cube.dimensional@1)
    lines.extend([
        f'view "cube_star" as {_q(CUBE_PROFILE)}',
        '    with',
        '        id "cube_star"',
        f'        title {_q(f"{cube_title} — Dimensional Star")}',
        '        selection',
    ])
    if star_items:
        lines.append('            include')
        for item_id in star_items:
            lines.append('                item')
            lines.append(f'                    id {_q(item_id)}')
    else:
        lines.append('            include empty list')
    lines.append('')

    # 2. Dimension usage matrix view (matrix.relations@1)
    matrix_rel_role = 'uses'
    matrix_rows = (
        list(group_el_ids.values()) if dim_el_ids else [cube_el_id]
    )
    matrix_cols = (
        list(dim_el_ids.values())
        if dim_el_ids
        else list(group_el_ids.values()) or [cube_el_id]
    )
    lines.extend([
        f'view "cube_usage_matrix" as {_q(USAGE_MATRIX_PROFILE)}',
        '    with',
        '        id "cube_usage_matrix"',
        f'        title {_q(f"{cube_title} — Usage Matrix")}',
        '        selection',
    ])
    if matrix_items:
        lines.append('            include')
        for item_id in matrix_items:
            lines.append('                item')
            lines.append(f'                    id {_q(item_id)}')
    else:
        lines.append('            include empty list')
    lines.extend([
        '        projection',
        '            options',
        f'                relation {_q(matrix_rel_role)}',
        '                rows',
    ])
    for r_id in matrix_rows:
        lines.extend([
            '                    item',
            f'                        id {_q(r_id)}',
        ])
    lines.append('                columns')
    for c_id in matrix_cols:
        lines.extend([
            '                    item',
            f'                        id {_q(c_id)}',
        ])
    lines.append('')

    # 3. Aggregation plan grid view (table.records@1)
    lines.extend([
        f'view "cube_aggregation_grid" as {_q(AGGREGATION_GRID_PROFILE)}',
        '    with',
        '        id "cube_aggregation_grid"',
        f'        title {_q(f"{cube_title} — Aggregation Grid")}',
        '        selection',
    ])
    if agg_record_ids:
        lines.append('            include')
        for rec_el_id in agg_record_ids:
            lines.append('                item')
            lines.append(f'                    id {_q(rec_el_id)}')
    else:
        lines.append('            include empty list')
    lines.extend([
        '        projection',
        '            options',
    ])
    if agg_record_ids:
        lines.append('                records')
        for rec_el_id in agg_record_ids:
            lines.append('                    item')
            lines.append(f'                        id {_q(rec_el_id)}')
    else:
        lines.append('                records empty list')
    lines.append('                columns')
    grid_cols = [
        ('rule_name', 'Rule'),
        ('measure_group', 'Measure Group'),
        ('grain_dimensions', 'Grain Dimensions'),
        ('measures', 'Measures'),
        ('strategy', 'Strategy'),
        ('target_relation', 'Target Relation'),
        ('partition', 'Partition'),
        ('refresh_policy', 'Refresh Policy'),
        ('enabled', 'State'),
        ('db_review', 'DB Review'),
    ]
    for col_key, col_label in grid_cols:
        lines.extend([
            '                    item',
            f'                        id {_q(f"x_record.{col_key}")}',
            f'                        path '
            f'{_q(f"metadata.x_record.record.{col_key}")}',
            f'                        label {_q(col_label)}',
        ])
    lines.append('')

    return '\n'.join(lines), id_map


def _extract_notes(block_body: str) -> list[str]:
    notes: list[str] = []
    in_notes = False
    notes_indent = 0
    item_re = re.compile(r'^\s+item\s+"((?:[^"]|"")*)"\s*$')
    for line in block_body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip(' '))
        if stripped == 'notes':
            in_notes = True
            notes_indent = indent
            continue
        if in_notes:
            if indent <= notes_indent:
                in_notes = False
                continue
            match = item_re.match(line)
            if match:
                notes.append(match.group(1).replace('""', '"'))
    return notes


def _decode_comment_text(raw: str) -> str:
    val = raw.strip()
    if not val:
        return ''
    try:
        parsed = json.loads(val)
        if isinstance(parsed, str):
            return parsed
    except ValueError:
        pass
    return val


def ddn_to_semantic_model(ddn_text: str) -> dict[str, Any]:
    """Parse a Cube DDN document back into a normalized semantic model dict.

    Returns ``{'model': ..., 'element_ids': ..., 'notes': [...]}``.
    """
    if not isinstance(ddn_text, str) or not ddn_text.strip():
        raise DesignStoreError('Cube DDN text must be a non-empty string')

    cube_desc_comment: str | None = None
    persp_desc_comments: dict[str, str] = {}
    cube_desc_re = re.compile(r'^\s*//\s*@cube\.description:\s*(.*)$')
    persp_desc_re = re.compile(
        r'^\s*//\s*@cube\.perspective_description\s+'
        r'([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$'
    )
    for line in ddn_text.splitlines():
        m_cube = cube_desc_re.match(line)
        if m_cube:
            cube_desc_comment = _decode_comment_text(m_cube.group(1))
            continue
        m_persp = persp_desc_re.match(line)
        if m_persp:
            persp_desc_comments[m_persp.group(1)] = _decode_comment_text(
                m_persp.group(2)
            )

    blocks = _parse_blocks(ddn_text)
    titles_by_id: dict[str, str] = {}
    subtitles_by_id: dict[str, str] = {}
    cube_notes: list[str] = []
    element_ids: dict[str, str] = {}

    for block in blocks:
        if block['kind'] == 'element' and _extract_x_record(block) is None:
            titles_by_id[block['id']] = block['title']
            if 'subtitle' in block['props']:
                subtitles_by_id[block['id']] = block['props']['subtitle']
            if block['role'] == 'cube':
                element_ids['cube'] = block['id']
                cube_notes.extend(_extract_notes(block['body']))

    envelope: dict[str, Any] = {}
    cube_name: str | None = None
    cube_subject_id: str | None = None
    dimensions: list[dict[str, Any]] = []
    measures: list[dict[str, Any]] = []
    measure_groups: list[dict[str, Any]] = []
    materializations: list[dict[str, Any]] = []
    perspectives: list[dict[str, Any]] = []
    translations: list[dict[str, Any]] = []

    for block in blocks:
        x_rec = _extract_x_record(block)
        if x_rec is None or x_rec.get('module') != CUBE_MODULE:
            continue
        bkind = x_rec.get('block')
        rec = x_rec.get('record', {})
        subj_id = rec.get('subject_id') or ''
        try:
            logical_name = (
                json.loads(x_rec['name_json'])
                if x_rec.get('name_json') else ''
            )
        except ValueError:
            logical_name = ''

        if bkind == 'cube_root':
            cube_subject_id = subj_id
            cube_name = titles_by_id.get(subj_id) or logical_name
            if rec.get('envelope_json'):
                envelope = json.loads(rec['envelope_json'])
                saved_ids = envelope.get('element_ids')
                if isinstance(saved_ids, dict):
                    for k, v in saved_ids.items():
                        if isinstance(k, str) and is_uuid7(v):
                            element_ids.setdefault(k, v)
            element_ids['cube'] = subj_id
            element_ids['record:cube'] = block['id']
        elif bkind == 'dimension' and rec.get('dimension_json'):
            dim = json.loads(rec['dimension_json'])
            if subj_id in titles_by_id:
                dim['name'] = titles_by_id[subj_id]
            dimensions.append(dim)
            element_ids[f"dimension:{dim['id']}"] = subj_id
            element_ids[f"record:dimension:{dim['id']}"] = block['id']
        elif bkind == 'measure' and rec.get('measure_json'):
            meas = json.loads(rec['measure_json'])
            if subj_id in titles_by_id:
                meas['name'] = titles_by_id[subj_id]
            measures.append(meas)
            element_ids[f"measure:{meas['id']}"] = subj_id
            element_ids[f"record:measure:{meas['id']}"] = block['id']
        elif bkind == 'measure_group' and rec.get('group_json'):
            grp = json.loads(rec['group_json'])
            if subj_id in titles_by_id:
                grp['name'] = titles_by_id[subj_id]
            measure_groups.append(grp)
            element_ids[f"measure_group:{grp['id']}"] = subj_id
            element_ids[f"record:measure_group:{grp['id']}"] = block['id']
        elif bkind == 'materialization' and rec.get('materialization_json'):
            mat = json.loads(rec['materialization_json'])
            if subj_id in titles_by_id:
                mat['name'] = titles_by_id[subj_id]
            materializations.append(mat)
            element_ids[f"materialization:{mat['id']}"] = subj_id
            element_ids[f"record:materialization:{mat['id']}"] = block['id']
        elif bkind == 'perspective' and rec.get('perspective_json'):
            persp = json.loads(rec['perspective_json'])
            if subj_id in titles_by_id:
                persp['name'] = titles_by_id[subj_id]
            if persp.get('id') in persp_desc_comments:
                persp['description'] = persp_desc_comments[persp['id']]
            elif subj_id in subtitles_by_id:
                persp['description'] = subtitles_by_id[subj_id]
            perspectives.append(persp)
            element_ids[f"perspective:{persp['id']}"] = subj_id
            element_ids[f"record:perspective:{persp['id']}"] = block['id']
        elif bkind == 'translation' and rec.get('translation_json'):
            tr = json.loads(rec['translation_json'])
            translations.append(tr)
            element_ids[f"record:translation:{tr['id']}"] = block['id']

    if not envelope and not cube_name:
        raise DesignStoreError(
            'DDN document does not contain a ScratchRobin dimensional cube'
        )

    annotations = copy.deepcopy(envelope.get('annotations') or {})
    if cube_notes:
        annotations['ddn_notes'] = cube_notes
    else:
        annotations.pop('ddn_notes', None)

    description = envelope.get('description', '')
    if cube_desc_comment is not None:
        description = cube_desc_comment
    elif cube_subject_id and cube_subject_id in subtitles_by_id:
        description = subtitles_by_id[cube_subject_id]

    raw_model: dict[str, Any] = {
        'contract_version': envelope.get('contract_version', '1.0.0'),
        'name': cube_name or 'Cube',
        'description': description,
        'semantic_family': envelope.get('semantic_family', 'relational'),
        'sources': envelope.get('sources', []),
        'joins': envelope.get('joins', []),
        'relationships': envelope.get('relationships', []),
        'dimensions': dimensions,
        'measures': measures,
        'parameters': envelope.get('parameters', []),
        'default_filters': envelope.get('default_filters', []),
        'materializations': materializations,
        'security': envelope.get(
            'security',
            {'row_filters': [], 'tenant_filter': None, 'roles': []},
        ),
        'visualizations': envelope.get('visualizations', []),
        'dashboards': envelope.get('dashboards', []),
        'schedules': envelope.get('schedules', []),
        'reports': envelope.get('reports', []),
        'annotations': annotations,
    }
    if envelope.get('has_explicit_measure_groups') or measure_groups:
        if envelope.get('has_explicit_measure_groups', True):
            raw_model['measure_groups'] = measure_groups
    if envelope.get('has_explicit_perspectives') or perspectives:
        raw_model['perspectives'] = perspectives
    if envelope.get('has_explicit_translations') or translations:
        raw_model['translations'] = translations

    try:
        validated = public_model(validate_model(raw_model))
    except SemanticModelError as exc:
        raise DesignStoreError(f'Invalid Cube DDN model: {exc}') from exc

    return {
        'model': validated,
        'element_ids': element_ids,
        'notes': cube_notes,
    }


def _index_by_id(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in items:
        key = item.get('id') or item.get('locale')
        if key:
            out[str(key)] = item
    return out


def diff_cube_ddn(
    base_ddn_text: str,
    active_ddn_text: str,
    draft_ddn_text: str | None = None,
) -> dict[str, Any]:
    """Compare base vs active Cube DDN and optionally merge into a draft.

    Detects changes accepted by someone else while a draft was edited and
    computes a 3-way merge when ``draft_ddn_text`` is provided.
    """
    base_parsed = ddn_to_semantic_model(base_ddn_text)
    active_parsed = ddn_to_semantic_model(active_ddn_text)
    base_m = base_parsed['model']
    active_m = active_parsed['model']

    sections = (
        'sources',
        'joins',
        'relationships',
        'dimensions',
        'measures',
        'measure_groups',
        'perspectives',
        'translations',
        'parameters',
        'materializations',
    )
    active_changes: list[dict[str, Any]] = []
    for sec in sections:
        b_map = _index_by_id(base_m.get(sec, []))
        a_map = _index_by_id(active_m.get(sec, []))
        for item_id in sorted(set(b_map) | set(a_map)):
            if item_id not in b_map:
                active_changes.append({
                    'section': sec,
                    'item_id': item_id,
                    'change': 'added',
                    'after': a_map[item_id],
                })
            elif item_id not in a_map:
                active_changes.append({
                    'section': sec,
                    'item_id': item_id,
                    'change': 'removed',
                    'before': b_map[item_id],
                })
            elif b_map[item_id] != a_map[item_id]:
                active_changes.append({
                    'section': sec,
                    'item_id': item_id,
                    'change': 'modified',
                    'before': b_map[item_id],
                    'after': a_map[item_id],
                })
    for scalar_key in ('name', 'description', 'default_filters', 'security'):
        if base_m.get(scalar_key) != active_m.get(scalar_key):
            active_changes.append({
                'section': scalar_key,
                'item_id': scalar_key,
                'change': 'modified',
                'before': base_m.get(scalar_key),
                'after': active_m.get(scalar_key),
            })

    if draft_ddn_text is None:
        return {
            'has_active_changes': bool(active_changes),
            'active_changes': active_changes,
            'conflicts': [],
            'merged_ddn_text': None,
        }

    draft_parsed = ddn_to_semantic_model(draft_ddn_text)
    draft_m = copy.deepcopy(draft_parsed['model'])
    merged_ids = {
        **base_parsed['element_ids'],
        **active_parsed['element_ids'],
        **draft_parsed['element_ids'],
    }
    conflicts: list[dict[str, Any]] = []

    for sec in sections:
        if (
            sec in {'measure_groups', 'perspectives', 'translations'}
            and sec not in base_m
            and sec not in active_m
            and sec not in draft_m
        ):
            continue
        b_map = _index_by_id(base_m.get(sec, []))
        a_map = _index_by_id(active_m.get(sec, []))
        d_map = _index_by_id(draft_m.get(sec, []))
        ordered_ids: list[str] = []
        for candidate_id in (
            list(d_map) + [k for k in a_map if k not in d_map]
        ):
            if candidate_id not in ordered_ids:
                ordered_ids.append(candidate_id)

        merged_list: list[dict[str, Any]] = []
        for item_id in ordered_ids:
            b_val = b_map.get(item_id)
            a_val = a_map.get(item_id)
            d_val = d_map.get(item_id)
            if a_val == b_val:
                if d_val is not None:
                    merged_list.append(d_val)
                continue
            if d_val == b_val:
                if a_val is not None:
                    merged_list.append(a_val)
                continue
            if a_val == d_val:
                if d_val is not None:
                    merged_list.append(d_val)
                continue
            conflicts.append({
                'section': sec,
                'item_id': item_id,
                'base': b_val,
                'active': a_val,
                'draft': d_val,
            })
            if d_val is not None:
                merged_list.append(d_val)
        draft_m[sec] = merged_list

    for scalar_key in ('name', 'description', 'default_filters', 'security'):
        b_val = base_m.get(scalar_key)
        a_val = active_m.get(scalar_key)
        d_val = draft_m.get(scalar_key)
        if a_val != b_val:
            if d_val == b_val:
                draft_m[scalar_key] = copy.deepcopy(a_val)
            elif d_val != a_val:
                conflicts.append({
                    'section': scalar_key,
                    'item_id': scalar_key,
                    'base': b_val,
                    'active': a_val,
                    'draft': d_val,
                })

    merged_notes = list(draft_parsed['notes'])
    for conflict in conflicts:
        note_line = (
            f"CONFLICT [{conflict['section']}:{conflict['item_id']}]: "
            'both active cube and draft modified this item.'
        )
        if note_line not in merged_notes:
            merged_notes.append(note_line)

    merged_ddn, _ = semantic_model_to_ddn(
        draft_m,
        element_ids=merged_ids,
        cube_notes=merged_notes,
    )
    return {
        'has_active_changes': bool(active_changes),
        'active_changes': active_changes,
        'conflicts': conflicts,
        'can_auto_merge': len(conflicts) == 0,
        'merged_ddn_text': merged_ddn,
    }


def _quote_ident(part: str, engine: str) -> str:
    dialect = _PORTABLE_DIALECTS.get(engine, _PORTABLE_DIALECTS['postgresql'])
    q_open = dialect['quote_open']
    q_close = dialect['quote_close']
    return q_open + part.replace(q_close, q_close + q_close) + q_close


def _compile_materialization_select(
    model: dict[str, Any],
    mat: dict[str, Any],
    engine: str,
) -> str:
    dialect = _PORTABLE_DIALECTS.get(engine, _PORTABLE_DIALECTS['postgresql'])
    grain = list(mat.get('grain_dimensions') or [
        d['id'] for d in model.get('dimensions', [])[:2]
    ])
    measures = list(mat.get('measures') or [
        m['id'] for m in model.get('measures', [])
    ])
    if not measures:
        return '-- No measures declared for materialization'
    query = {
        'axes': {'rows': grain, 'columns': [], 'pages': []},
        'measures': measures,
        'filters': [],
        'totals': False,
        'limit': 10000,
    }
    compiled = compile_sql(model, query, dialect)
    sql = compiled.get('source') or compiled.get('sql') or ''
    sql = re.sub(r'\s+(?:LIMIT\s+\d+|ROWS\s+1\s+TO\s+\d+)\s*$', '', sql)
    return sql


def preview_cube_materialization_plan(
    active_model: dict[str, Any] | None,
    candidate_model: dict[str, Any],
    *,
    target_engine: str = 'postgresql',
    element_ids: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Highlight materialized-aggregate DB changes and build native review SQL.

    Never executes database DDL directly; all database-affecting aggregate
    changes require ScratchRobin's native-operation review.
    """
    engine = (target_engine or 'postgresql').lower()
    before_map = _index_by_id(
        (active_model or {}).get('materializations', [])
    )
    after_map = _index_by_id(candidate_model.get('materializations', []))

    highlights: dict[str, str] = {}
    differences: list[dict[str, Any]] = []
    statements: list[str] = []
    grain_warnings: list[str] = []
    measures_by_id = _index_by_id(candidate_model.get('measures', []))
    dims_by_id = _index_by_id(candidate_model.get('dimensions', []))

    def _check_mat_grain(mat_obj: dict[str, Any]) -> list[str]:
        warnings_local: list[str] = []
        grain_set = set(mat_obj.get('grain_dimensions') or [])
        mat_meas = list(
            mat_obj.get('measures')
            or [m['id'] for m in measures_by_id.values()]
        )
        for mid in mat_meas:
            m_obj = measures_by_id.get(mid)
            if not m_obj:
                continue
            if m_obj.get('aggregation') not in SEMI_ADDITIVE_AGGREGATIONS:
                continue
            sa_dim_id = m_obj.get('semi_additive_dimension')
            sa_dim = dims_by_id.get(sa_dim_id or '')
            admitted_time_keys = {sa_dim_id} if sa_dim_id else set()
            if sa_dim:
                for h_obj in sa_dim.get('hierarchies', []):
                    for lvl in h_obj.get('levels', []):
                        if lvl.get('field') == sa_dim.get('field'):
                            admitted_time_keys.add(lvl['id'])
            if not (grain_set & admitted_time_keys):
                msg = (
                    f"Aggregate '{mat_obj['name']}' materializes "
                    f"semi-additive measure '{m_obj['name']}' "
                    f"({m_obj['aggregation']}) without its time dimension "
                    f"'{sa_dim_id}' in grain_dimensions; rolled-up snapshot "
                    'values cannot be re-aggregated safely across finer '
                    'time periods.'
                )
                warnings_local.append(msg)
        return warnings_local

    supports_mat_view = engine in ('postgresql', 'duckdb')
    create_kw = (
        'CREATE MATERIALIZED VIEW' if supports_mat_view else 'CREATE TABLE'
    )
    drop_kw = (
        'DROP MATERIALIZED VIEW IF EXISTS'
        if supports_mat_view
        else 'DROP TABLE IF EXISTS'
    )

    def _partition_ddl_annotations(mat_obj: dict[str, Any]) -> tuple[str, str]:
        p_field = mat_obj.get('partition_field')
        if isinstance(p_field, Mapping):
            col_name = str(p_field.get('field') or '').strip()
        else:
            col_name = str(p_field or '').strip()
        p_grain = str(mat_obj.get('partition_grain') or 'none').strip()
        r_pol = str(mat_obj.get('refresh_policy') or '').strip()
        rg = mat_obj.get('rule_group')
        header_lines: list[str] = []
        if r_pol:
            header_lines.append(f'-- Refresh policy: {r_pol}')
        if rg and isinstance(rg, Mapping):
            rg_parts = []
            if rg.get('mandatory_dimensions'):
                rg_parts.append(
                    f"mandatory={','.join(rg['mandatory_dimensions'])}"
                )
            if rg.get('max_dimension_combinations') is not None:
                rg_parts.append(
                    f"max_dims={rg['max_dimension_combinations']}"
                )
            if rg_parts:
                header_lines.append(f"-- Rule group: {'; '.join(rg_parts)}")
        suffix = ''
        if col_name and p_grain and p_grain != 'none':
            q_col = _quote_ident(col_name, engine)
            grain_expr = {
                'day': f"DATE_TRUNC('day', {q_col})",
                'month': f"DATE_TRUNC('month', {q_col})",
                'year': f"DATE_TRUNC('year', {q_col})",
            }.get(p_grain, q_col)
            header_lines.append(
                f'-- Partition clause ({p_grain}): PARTITION BY RANGE '
                f'({grain_expr})'
            )
            if not supports_mat_view and engine in ('postgresql', 'mysql'):
                suffix = f'\n/* PARTITION BY RANGE ({q_col}) -- {p_grain} */'
        elif p_grain and p_grain != 'none':
            header_lines.append(f'-- Partition grain: {p_grain}')
        header = ('\n'.join(header_lines) + '\n') if header_lines else ''
        return header, suffix

    destructive_items: list[str] = []

    for mat_id in sorted(set(before_map) | set(after_map)):
        before = before_map.get(mat_id)
        after = after_map.get(mat_id)
        if before is None and after is not None:
            kind = 'added_enabled' if after.get('enabled') else 'added_draft'
            highlights[mat_id] = kind
            rel_parts = after.get('target_relation') or [after['id']]
            rel_sql = '.'.join(_quote_ident(p, engine) for p in rel_parts)
            select_sql = _compile_materialization_select(
                candidate_model, after, engine
            )
            p_header, p_suffix = _partition_ddl_annotations(after)
            ddl = (
                f'{p_header}{create_kw} {rel_sql} AS\n{select_sql}{p_suffix};'
                if after.get('enabled')
                else (
                    f'{p_header}-- Disabled aggregate {rel_sql} '
                    '(no DB object created)'
                )
            )
            if after.get('enabled'):
                statements.append(ddl)
            mat_warns = _check_mat_grain(after)
            grain_warnings.extend(mat_warns)
            differences.append({
                'materialization_id': mat_id,
                'name': after['name'],
                'change_kind': kind,
                'target_relation': rel_parts,
                'partition_grain': after.get('partition_grain', 'none'),
                'refresh_policy': after.get('refresh_policy', 'manual'),
                'sql': ddl,
                'warnings': mat_warns,
            })
        elif before is not None and after is None:
            highlights[mat_id] = 'dropped'
            rel_parts = before.get('target_relation') or [before['id']]
            rel_sql = '.'.join(_quote_ident(p, engine) for p in rel_parts)
            ddl = f'{drop_kw} {rel_sql};'
            if before.get('enabled'):
                statements.append(ddl)
                destructive_items.append(rel_sql)
            differences.append({
                'materialization_id': mat_id,
                'name': before['name'],
                'change_kind': 'dropped',
                'target_relation': rel_parts,
                'sql': ddl,
            })
        elif before != after and after is not None and before is not None:
            if not before.get('enabled') and after.get('enabled'):
                kind = 'enabled'
            elif before.get('enabled') and not after.get('enabled'):
                kind = 'disabled'
            else:
                kind = 'modified'
            highlights[mat_id] = kind
            rel_parts = after.get('target_relation') or [after['id']]
            rel_sql = '.'.join(_quote_ident(p, engine) for p in rel_parts)
            p_header, p_suffix = _partition_ddl_annotations(after)
            if after.get('enabled'):
                select_sql = _compile_materialization_select(
                    candidate_model, after, engine
                )
                ddl = (
                    f'{p_header}{drop_kw} {rel_sql};\n'
                    f'{create_kw} {rel_sql} AS\n{select_sql}{p_suffix};'
                )
                statements.append(ddl)
                if before.get('enabled'):
                    destructive_items.append(rel_sql)
            else:
                ddl = f'{p_header}{drop_kw} {rel_sql};'
                if before.get('enabled'):
                    statements.append(ddl)
                    destructive_items.append(rel_sql)
            mat_warns = _check_mat_grain(after)
            grain_warnings.extend(mat_warns)
            differences.append({
                'materialization_id': mat_id,
                'name': after['name'],
                'change_kind': kind,
                'target_relation': rel_parts,
                'partition_grain': after.get('partition_grain', 'none'),
                'refresh_policy': after.get('refresh_policy', 'manual'),
                'sql': ddl,
                'warnings': mat_warns,
            })

    for mat_id, after in sorted(after_map.items()):
        if before_map.get(mat_id) == after:
            for warn in _check_mat_grain(after):
                if warn not in grain_warnings:
                    grain_warnings.append(warn)

    destructive_warning = (
        f'Dropping or rebuilding materialized objects '
        f'({", ".join(destructive_items)}) removes existing materialized data '
        'and requires native operation review.'
        if destructive_items
        else ''
    )

    highlighted_ddn, _ = semantic_model_to_ddn(
        candidate_model,
        element_ids=element_ids,
        highlighted_changes=highlights,
    )
    return {
        'target_engine': engine,
        'has_database_changes': bool(statements),
        'differences': differences,
        'statements': statements,
        'grain_warnings': grain_warnings,
        'destructive_warning': destructive_warning,
        'sql_preview': '\n\n'.join(statements),
        'highlighted_ddn_text': highlighted_ddn,
        'requires_native_review': True,
        'applied_immediately': False,
    }


def _bump_minor_version(label: str) -> str:
    match = re.fullmatch(r'(\d+)\.(\d+)', str(label or '').strip())
    if not match:
        return '1.1'
    return f'{int(match.group(1))}.{int(match.group(2)) + 1}'


class CubeDesignSync:
    """Coordinate Cube designs in ``DesignStore`` and ``SemanticModelService``.

    - Saving drafts/save points updates ``DesignStore`` only; the active cube
      in ``SemanticModelService`` is untouched until a version is ``accepted``.
    - Accepting a version applies the Cube DDN into ``SemanticModelService``
      (creating or updating the published semantic model) and returns any
      materialized-aggregate database plan for native-operation review.
    """

    def __init__(
        self,
        store: DesignStore,
        process: StoreDDNProcess | None = None,
        semantic_service=None,
    ):
        self.store = store
        self.process = process or StoreDDNProcess(store)
        self.semantic_service = semantic_service

    def create_cube(
        self,
        *,
        project_id: str,
        key: str,
        title: str,
        actor_id: int,
        model: dict[str, Any] | None = None,
        endpoint_id: str | None = None,
        note: str = '',
    ) -> dict[str, Any]:
        cube_model = copy.deepcopy(
            model or default_cube_model(title or key or 'New Cube')
        )
        cube_model['name'] = (title or cube_model.get('name') or key).strip()
        if endpoint_id:
            cube_model.setdefault('annotations', {})[
                'semantic_endpoint_id'
            ] = endpoint_id
        cube_model.setdefault('annotations', {})['cube_version_label'] = '1.0'
        ddn_text, _ = semantic_model_to_ddn(cube_model)
        created = self.store.create_design(
            project_id=project_id,
            key=key,
            kind='cube',
            title=cube_model['name'],
            ddn_text=ddn_text,
            actor_id=actor_id,
            status='draft',
            note=note or 'Created cube design',
            origin='local',
        )
        return {
            'design': created,
            'cube': ddn_to_semantic_model(created['version']['ddn_text']),
        }

    def import_from_semantic_store(
        self,
        *,
        project_id: str,
        key: str,
        actor_id: int,
        endpoint_id: str,
        model_id: str,
        semantic_service=None,
        note: str = '',
    ) -> dict[str, Any]:
        svc = semantic_service or self.semantic_service
        if svc is None:
            raise DesignStoreError(
                'SemanticModelService is required to load from semantic store'
            )
        record = svc.get(actor_id, endpoint_id, model_id)
        definition = copy.deepcopy(record['definition'])
        definition.setdefault('annotations', {}).update({
            'semantic_model_id': record['model_id'],
            'semantic_endpoint_id': endpoint_id,
            'semantic_store_revision': record['revision'],
            'cube_version_label': f"1.{max(0, int(record['revision']) - 1)}",
        })
        ddn_text, _ = semantic_model_to_ddn(definition)
        created = self.store.create_design(
            project_id=project_id,
            key=key,
            kind='cube',
            title=definition['name'],
            ddn_text=ddn_text,
            actor_id=actor_id,
            status='draft',
            note=note or f'Loaded from semantic store ({model_id})',
            origin=f'semantic_store:{model_id}@{record["revision"]}',
        )
        return {
            'design': created,
            'cube': ddn_to_semantic_model(created['version']['ddn_text']),
            'source_semantic_model': record,
        }

    def save_cube_model(
        self,
        design_id: str,
        *,
        expected_head_version: int,
        actor_id: int,
        model: dict[str, Any] | None = None,
        ddn_text: str | None = None,
        cube_notes: list[str] | None = None,
        pinned_positions: dict[str, dict[str, float]] | None = None,
        status: str = 'draft',
        note: str = '',
    ) -> dict[str, Any]:
        current = self.store.get_design(design_id)
        current_parsed = ddn_to_semantic_model(current['version']['ddn_text'])
        if ddn_text is not None:
            parsed = ddn_to_semantic_model(ddn_text)
            next_ddn = ddn_text
        elif model is not None:
            next_ddn, _ = semantic_model_to_ddn(
                model,
                element_ids=current_parsed['element_ids'],
                cube_notes=cube_notes,
            )
            parsed = ddn_to_semantic_model(next_ddn)
        else:
            raise DesignStoreError('Supply either model or ddn_text')

        active_drift = None
        base_ver = current['version'].get('base_version')
        active_ver = current.get('active_version')
        if (
            active_ver is not None
            and base_ver is not None
            and active_ver != base_ver
            and active_ver != current['version']['version']
        ):
            base_doc = self.store.get_design(design_id, version=base_ver)
            active_doc = self.store.get_design(design_id, version=active_ver)
            active_drift = diff_cube_ddn(
                base_doc['version']['ddn_text'],
                active_doc['version']['ddn_text'],
                next_ddn,
            )

        inherited_base = (
            current['version']['version']
            if current['version'].get('status') == 'accepted'
            else current['version'].get('base_version')
        )
        saved = self.process.save_from_ddn(
            design_id,
            expected_head_version=expected_head_version,
            ddn_or_workspace=next_ddn,
            actor_id=actor_id,
            base_version=inherited_base,
            pinned_positions=pinned_positions,
            status=status,
            note=note or 'Saved cube draft',
            allow_conflict_note=True,
        )
        return {
            **saved,
            'cube': parsed,
            'active_drift': active_drift,
            'applied_to_semantic_store': False,
        }

    def sync_draft_with_active(
        self,
        design_id: str,
        *,
        actor_id: int,
        note: str = '',
    ) -> dict[str, Any]:
        """Merge accepted active cube changes into the current head draft."""
        current = self.store.get_design(design_id)
        active_ver = current.get('active_version')
        if active_ver is None:
            raise DesignStoreError('Cube has no accepted active version yet')
        base_ver = current['version'].get('base_version') or 1
        base_doc = self.store.get_design(design_id, version=base_ver)
        active_doc = self.store.get_design(design_id, version=active_ver)
        merge_result = diff_cube_ddn(
            base_doc['version']['ddn_text'],
            active_doc['version']['ddn_text'],
            current['version']['ddn_text'],
        )
        if merge_result['conflicts']:
            return {
                'merged': False,
                'merge': merge_result,
            }
        saved = self.store.save_version(
            design_id,
            expected_head_version=current['head_version'],
            ddn_text=merge_result['merged_ddn_text'],
            actor_id=actor_id,
            base_version=active_ver,
            status='draft',
            note=note or f'Merged active v{active_ver} changes into draft',
            allow_conflict_note=True,
        )
        return {
            'merged': True,
            'merge': merge_result,
            'design': saved,
            'cube': ddn_to_semantic_model(saved['version']['ddn_text']),
        }

    def _apply_to_semantic_store(
        self,
        cube_model: dict[str, Any],
        *,
        actor_id: int,
        endpoint_id: str | None = None,
        semantic_service=None,
    ) -> dict[str, Any] | None:
        svc = semantic_service or self.semantic_service
        if svc is None:
            return None
        annotations = cube_model.get('annotations', {})
        ep_id = (
            endpoint_id
            or annotations.get('semantic_endpoint_id')
            or 'default'
        )
        model_id = annotations.get('semantic_model_id')
        if model_id:
            try:
                existing = svc.get(actor_id, ep_id, model_id)
            except SemanticModelError:
                existing = None
            if existing is not None:
                rev = existing['revision']
                if existing['status'] == 'published':
                    drafted = svc.set_status(
                        actor_id, ep_id, model_id, rev, 'draft'
                    )
                    rev = drafted['revision']
                updated = svc.update(
                    actor_id, ep_id, model_id, rev, cube_model
                )
                published = svc.set_status(
                    actor_id, ep_id, model_id, updated['revision'], 'published'
                )
                return published

        created = svc.create(actor_id, ep_id, cube_model)
        published = svc.set_status(
            actor_id,
            ep_id,
            created['model_id'],
            created['revision'],
            'published',
        )
        return published

    def accept_cube(
        self,
        design_id: str,
        version: int,
        *,
        actor_id: int,
        has_scratchrobin_permission: bool = True,
        require_git_review: bool = False,
        git_review_ref: str | None = None,
        endpoint_id: str | None = None,
        target_engine: str = 'postgresql',
        semantic_service=None,
        comment: str = '',
    ) -> dict[str, Any]:
        target_doc = self.store.get_design(design_id, version=version)
        prev_active_ver = target_doc.get('active_version')
        prev_active_model = None
        if prev_active_ver is not None and prev_active_ver != version:
            prev_active_doc = self.store.get_design(
                design_id, version=prev_active_ver
            )
            prev_active_model = ddn_to_semantic_model(
                prev_active_doc['version']['ddn_text']
            )['model']
            base_ver = target_doc['version'].get('base_version')
            if base_ver is not None and base_ver != prev_active_ver:
                base_doc = self.store.get_design(design_id, version=base_ver)
                drift = diff_cube_ddn(
                    base_doc['version']['ddn_text'],
                    prev_active_doc['version']['ddn_text'],
                    target_doc['version']['ddn_text'],
                )
                if drift['has_active_changes']:
                    raise DesignStoreConflict(
                        'Active cube changed since this draft branched; '
                        'merge active DDN changes into the draft before '
                        'accepting.'
                    )

        candidate_parsed = ddn_to_semantic_model(
            target_doc['version']['ddn_text']
        )
        candidate_model = candidate_parsed['model']

        accepted = self.process.accept_with_policy(
            design_id,
            version,
            actor_id=actor_id,
            has_scratchrobin_permission=has_scratchrobin_permission,
            require_git_review=require_git_review,
            git_review_ref=git_review_ref,
            comment=comment or 'Accepted and applied cube version',
        )
        applied = self._apply_to_semantic_store(
            candidate_model,
            actor_id=actor_id,
            endpoint_id=endpoint_id,
            semantic_service=semantic_service,
        )
        mat_plan = preview_cube_materialization_plan(
            prev_active_model,
            candidate_model,
            target_engine=target_engine,
            element_ids=candidate_parsed['element_ids'],
        )
        return {
            'design': accepted,
            'cube': candidate_parsed,
            'applied_semantic_model': applied,
            'materialization_review_plan': mat_plan,
        }

    def leave_accepted(
        self,
        design_id: str,
        *,
        mode: str,
        actor_id: int,
        target_version: int | None = None,
        endpoint_id: str | None = None,
        target_engine: str = 'postgresql',
        semantic_service=None,
        note: str = '',
    ) -> dict[str, Any]:
        """Leave an accepted cube via rollback or branch_minor_draft."""
        current = self.store.get_design(design_id)
        active_ver = current.get('active_version')
        if active_ver is None:
            raise DesignStoreError('Cube has no accepted version to leave')
        active_doc = self.store.get_design(design_id, version=active_ver)
        active_parsed = ddn_to_semantic_model(
            active_doc['version']['ddn_text']
        )

        if mode == 'rollback':
            if target_version is None:
                raise DesignStoreError(
                    'target_version is required for rollback'
                )
            rolled = self.store.rollback_to_version(
                design_id,
                int(target_version),
                actor_id=actor_id,
                comment=note or f'Rolled back cube to v{target_version}',
            )
            rolled_parsed = ddn_to_semantic_model(
                rolled['version']['ddn_text']
            )
            applied = self._apply_to_semantic_store(
                rolled_parsed['model'],
                actor_id=actor_id,
                endpoint_id=endpoint_id,
                semantic_service=semantic_service,
            )
            mat_plan = preview_cube_materialization_plan(
                active_parsed['model'],
                rolled_parsed['model'],
                target_engine=target_engine,
                element_ids=rolled_parsed['element_ids'],
            )
            return {
                'mode': 'rollback',
                'design': rolled,
                'cube': rolled_parsed,
                'applied_semantic_model': applied,
                'materialization_review_plan': mat_plan,
            }

        if mode == 'branch_minor_draft':
            bumped_model = copy.deepcopy(active_parsed['model'])
            old_label = bumped_model.get('annotations', {}).get(
                'cube_version_label', '1.0'
            )
            new_label = _bump_minor_version(old_label)
            bumped_model.setdefault('annotations', {})[
                'cube_version_label'
            ] = new_label
            ddn_text, _ = semantic_model_to_ddn(
                bumped_model,
                element_ids=active_parsed['element_ids'],
                cube_notes=active_parsed['notes'],
            )
            saved = self.store.save_version(
                design_id,
                expected_head_version=current['head_version'],
                ddn_text=ddn_text,
                actor_id=actor_id,
                base_version=active_ver,
                status='draft',
                note=note or f'Minor version bump draft ({new_label})',
            )
            return {
                'mode': 'branch_minor_draft',
                'cube_version_label': new_label,
                'design': saved,
                'cube': ddn_to_semantic_model(saved['version']['ddn_text']),
            }

        raise DesignStoreError(
            f'Unsupported leave_accepted mode: {mode!r}'
        )

    def export_interchange(
        self,
        design_id: str,
        *,
        fmt: str,
        version: int | None = None,
        include_custom_extensions: bool = True,
    ) -> dict[str, Any]:
        """Export a Cube design to SML (v1.8) or Apache Ossie (v0.2.0)."""
        from .cube_interchange import export_cube_to_ossie, export_cube_to_sml

        doc = self.store.get_design(design_id, version=version)
        parsed = ddn_to_semantic_model(doc['version']['ddn_text'])
        target_fmt = str(fmt or '').strip().lower()
        if target_fmt in {'sml', 'sml@1.8'}:
            exported = export_cube_to_sml(parsed['model'])
        elif target_fmt in {'ossie', 'apache-ossie', 'apache-ossie@0.2.0'}:
            exported = export_cube_to_ossie(
                parsed['model'],
                include_custom_extensions=include_custom_extensions,
            )
        else:
            raise DesignStoreError(
                f'Unsupported cube interchange export format: {fmt!r}'
            )
        return {
            'design_id': design_id,
            'version': doc['version']['version'],
            'status': doc['version']['status'],
            **exported,
        }

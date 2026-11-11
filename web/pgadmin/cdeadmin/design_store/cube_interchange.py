##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Clean-room SML (v1.8) and Apache Ossie (v0.2.0) cube interchange exporters.

Implements owner decision C4 (2026-11-10):
- SML first (``sml@1.8``): multi-file YAML bundle + manifest preserving
  datasets, level & parent-child hierarchies, role-playing relationships with
  ``active`` flag, additive/semi-additive/filtered/calculated metrics,
  perspectives, translations and materialization aggregates while excluding
  runtime principals, secrets and delivery recipients.
- Apache Ossie second (``apache-ossie@0.2.0``): lossy YAML + JSON export with a
  mandatory itemized ``loss_report`` detailing every dropped or degraded
  dimensional construct, plus optional ``custom_extensions`` JSON metadata
  excluding security and secrets.
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

from .cube_ddn import _effective_measure_groups, ddn_to_semantic_model
from .service import DesignStoreError

SML_FORMAT = 'sml@1.8'
OSSIE_FORMAT = 'apache-ossie@0.2.0'

_YAML_BARE_KEY = re.compile(r'^[A-Za-z_][A-Za-z0-9_.-]*$')
_YAML_SAFE_STR = re.compile(r'^[A-Za-z0-9_./:@$%+-][A-Za-z0-9_./:@$%+ -]*$')
_YAML_RESERVED = frozenset({
    'true', 'false', 'null', 'yes', 'no', 'on', 'off', '~',
})


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if (
        text
        and _YAML_SAFE_STR.fullmatch(text)
        and text.lower() not in _YAML_RESERVED
        and not text[0].isdigit()
        and not text.endswith(' ')
    ):
        return text
    return json.dumps(text, ensure_ascii=False)


def _yaml_key(key: Any) -> str:
    text = str(key)
    if _YAML_BARE_KEY.fullmatch(text) and text.lower() not in _YAML_RESERVED:
        return text
    return json.dumps(text, ensure_ascii=False)


def _emit_yaml_lines(value: Any, indent: int = 0) -> list[str]:
    pad = ' ' * indent
    if isinstance(value, Mapping):
        if not value:
            return [f'{pad}{{}}']
        out: list[str] = []
        for raw_k, raw_v in value.items():
            k_txt = _yaml_key(raw_k)
            if isinstance(raw_v, Mapping):
                if not raw_v:
                    out.append(f'{pad}{k_txt}: {{}}')
                else:
                    out.append(f'{pad}{k_txt}:')
                    out.extend(_emit_yaml_lines(raw_v, indent + 2))
            elif isinstance(raw_v, list):
                if not raw_v:
                    out.append(f'{pad}{k_txt}: []')
                else:
                    out.append(f'{pad}{k_txt}:')
                    out.extend(_emit_yaml_lines(raw_v, indent + 2))
            else:
                out.append(f'{pad}{k_txt}: {_yaml_scalar(raw_v)}')
        return out
    if isinstance(value, list):
        if not value:
            return [f'{pad}[]']
        out = []
        for item in value:
            if isinstance(item, Mapping) and item:
                items_iter = list(item.items())
                first_k, first_v = items_iter[0]
                fk_txt = _yaml_key(first_k)
                if not isinstance(first_v, (Mapping, list)) or not first_v:
                    val_txt = (
                        '{}' if isinstance(first_v, Mapping)
                        else '[]' if isinstance(first_v, list)
                        else _yaml_scalar(first_v)
                    )
                    out.append(f'{pad}- {fk_txt}: {val_txt}')
                else:
                    out.append(f'{pad}- {fk_txt}:')
                    out.extend(_emit_yaml_lines(first_v, indent + 4))
                for rest_k, rest_v in items_iter[1:]:
                    out.extend(_emit_yaml_lines({rest_k: rest_v}, indent + 2))
            elif isinstance(item, (Mapping, list)):
                out.append(f'{pad}-')
                out.extend(_emit_yaml_lines(item, indent + 2))
            else:
                out.append(f'{pad}- {_yaml_scalar(item)}')
        return out
    return [f'{pad}{_yaml_scalar(value)}']


def dump_deterministic_yaml(document: Any) -> str:
    """Serialize nested mappings/lists into deterministic block YAML 1.2."""
    return '\n'.join(_emit_yaml_lines(document, 0)) + '\n'


def _slug(value: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9_-]+', '_', str(value or '').strip()).strip(
        '_'
    )
    return cleaned.lower() or 'cube'


def _normalize_cube_input(
    model_or_ddn: Mapping[str, Any] | str,
) -> dict[str, Any]:
    if isinstance(model_or_ddn, str):
        return ddn_to_semantic_model(model_or_ddn)['model']
    try:
        return public_model(validate_model(model_or_ddn))
    except SemanticModelError as exc:
        raise DesignStoreError(str(exc)) from exc


def _expression_to_sql_formula(
    node: Mapping[str, Any],
    measures_by_id: Mapping[str, Mapping[str, Any]],
) -> str:
    if 'measure' in node:
        return str(node['measure'])
    if 'literal' in node:
        return str(node['literal'])
    op_map = {
        'add': '+',
        'subtract': '-',
        'multiply': '*',
        'divide': '/',
    }
    left = _expression_to_sql_formula(node['left'], measures_by_id)
    right = _expression_to_sql_formula(node['right'], measures_by_id)
    symbol = op_map.get(str(node.get('operator')), '+')
    if node.get('operator') == 'divide':
        return f'({left} / NULLIF({right}, 0))'
    return f'({left} {symbol} {right})'


def _filter_to_dict(flt: Mapping[str, Any]) -> dict[str, Any]:
    field = flt.get('field') or {}
    entry: dict[str, Any] = {
        'dataset': field.get('source_id', ''),
        'column': field.get('field', ''),
        'operator': flt.get('operator', 'eq'),
    }
    if flt.get('parameter_id') is not None:
        entry['parameter_id'] = flt['parameter_id']
    elif 'value' in flt:
        entry['value'] = copy.deepcopy(flt['value'])
    return entry


def _translations_index(
    translations: list[dict[str, Any]],
) -> dict[tuple[str, str], dict[str, dict[str, str]]]:
    by_target: dict[tuple[str, str], dict[str, dict[str, str]]] = {}
    for tr in translations:
        loc = tr['locale']
        for entry in tr.get('entries', []):
            t_kind = entry.get('target_kind') or entry.get('kind')
            key = (t_kind, entry['target_id'])
            payload: dict[str, str] = {}
            if entry.get('caption'):
                payload['caption'] = entry['caption']
            if entry.get('description'):
                payload['description'] = entry['description']
            if entry.get('display_folder'):
                payload['display_folder'] = entry['display_folder']
            if payload:
                by_target.setdefault(key, {})[loc] = payload
    return by_target


def export_cube_to_sml(
    model_or_ddn: Mapping[str, Any] | str,
) -> dict[str, Any]:
    """Export a Cube design or semantic model to SML v1.8 YAML bundle."""
    model = _normalize_cube_input(model_or_ddn)
    model_slug = _slug(model['name'])
    translations = model.get('translations', [])
    tr_index = _translations_index(translations)
    joins_by_id = {j['id']: j for j in model.get('joins', [])}
    measures_by_id = {m['id']: m for m in model.get('measures', [])}
    groups = _effective_measure_groups(model)

    files: dict[str, str] = {}
    loss_items: list[dict[str, Any]] = []

    security = model.get('security') or {}
    if (
        security.get('row_filters')
        or security.get('tenant_filter')
        or security.get('roles')
    ):
        loss_items.append({
            'category': 'security_policy_excluded',
            'item_id': 'security',
            'item_name': 'Row-level & tenant security policies',
            'reason': (
                'ScratchRobin omits runtime principals, tenant claims and '
                'row-level security policies from portable SML bundles.'
            ),
            'mitigation': (
                'Configure target platform row-level security separately '
                'after SML import.'
            ),
        })
    if model.get('schedules') or model.get('reports'):
        loss_items.append({
            'category': 'delivery_schedules_excluded',
            'item_id': 'schedules',
            'item_name': 'Report delivery schedules & recipients',
            'reason': (
                'Delivery schedules and recipient lists are operational '
                'settings outside SML semantic definitions.'
            ),
            'mitigation': 'Recreate delivery schedules in the target host.',
        })

    # Collect referenced columns per dataset for complete SML dataset files
    dataset_cols: dict[str, set[str]] = {
        src['id']: {g['field'] for g in src.get('grain', []) if g.get('field')}
        for src in model['sources']
    }

    def _note_ref(ref: dict[str, Any] | None) -> None:
        if isinstance(ref, Mapping):
            sid = ref.get('source_id')
            col = ref.get('field')
            if sid in dataset_cols and col:
                dataset_cols[sid].add(str(col))

    for j_obj in model.get('joins', []):
        for pred in j_obj.get('predicates', []):
            _note_ref(pred.get('left'))
            _note_ref(pred.get('right'))
    for dim in model['dimensions']:
        for r_k in ('field', 'key_field', 'name_field', 'sort_field'):
            _note_ref(dim.get(r_k))
        for attr in dim.get('attributes', []):
            _note_ref(attr.get('field'))
            _note_ref(attr.get('sort_field'))
        for hier in dim.get('hierarchies', []):
            _note_ref(hier.get('child_field'))
            _note_ref(hier.get('parent_field'))
            _note_ref(hier.get('name_field'))
            for lvl in hier.get('levels', []):
                _note_ref(lvl.get('field'))
    for meas in model['measures']:
        _note_ref(meas.get('field'))
        for flt in meas.get('filters') or []:
            _note_ref(flt.get('field'))

    dataset_docs: list[dict[str, Any]] = []
    for src in model['sources']:
        sid = src['id']
        rel = src.get('relation') or [sid]
        schema_name = rel[-2] if len(rel) >= 2 else ''
        table_name = rel[-1] if rel else sid
        ds_doc: dict[str, Any] = {
            'unique_name': sid,
            'object_type': 'dataset',
            'label': sid,
            'classification': src.get('classification', 'fact'),
            'schema': schema_name,
            'table': table_name,
            'columns': [
                {'name': col_name, 'data_type': 'auto'}
                for col_name in sorted(dataset_cols.get(sid, set()))
            ],
        }
        dataset_docs.append(ds_doc)
        files[f'datasets/{sid}.yml'] = dump_deterministic_yaml(ds_doc)

    dimension_docs: list[dict[str, Any]] = []
    for dim in model['dimensions']:
        did = dim['id']
        key_ref = dim.get('key_field') or dim['field']
        name_ref = dim.get('name_field') or key_ref
        dim_type = (
            'time' if dim.get('time_intelligence') else 'standard'
        )
        sml_hiers: list[dict[str, Any]] = []
        for hier in dim.get('hierarchies', []):
            h_kind = hier.get('hierarchy_kind', 'level')
            h_doc: dict[str, Any] = {
                'unique_name': hier['id'],
                'label': hier['name'],
                'hierarchy_kind': h_kind,
                'ragged': bool(hier.get('ragged', h_kind == 'parent_child')),
            }
            if h_kind == 'parent_child':
                h_doc['parent_child'] = {
                    'dataset': hier['child_field']['source_id'],
                    'child_column': hier['child_field']['field'],
                    'parent_column': hier['parent_field']['field'],
                    'name_column': (
                        (hier.get('name_field') or hier['child_field'])[
                            'field'
                        ]
                    ),
                    'root_parent_value': hier.get('root_parent_value'),
                    'max_depth': int(hier.get('max_depth', 16)),
                }
            h_doc['levels'] = [
                {
                    'unique_name': lvl['id'],
                    'label': lvl['name'],
                    'dataset': lvl['field']['source_id'],
                    'key_column': lvl['field']['field'],
                    **(
                        {
                            'locales': tr_index[('level', lvl['id'])],
                        }
                        if ('level', lvl['id']) in tr_index else {}
                    ),
                }
                for lvl in hier.get('levels', [])
            ]
            if ('hierarchy', hier['id']) in tr_index:
                h_doc['locales'] = tr_index[('hierarchy', hier['id'])]
            sml_hiers.append(h_doc)

        sml_attrs: list[dict[str, Any]] = [
            {
                'unique_name': attr['id'],
                'label': attr['name'],
                'dataset': attr['field']['source_id'],
                'key_column': attr['field']['field'],
                **(
                    {'sort_column': attr['sort_field']['field']}
                    if attr.get('sort_field') else {}
                ),
                **(
                    {'locales': tr_index[('attribute', attr['id'])]}
                    if ('attribute', attr['id']) in tr_index else {}
                ),
            }
            for attr in dim.get('attributes', [])
        ]

        dim_doc: dict[str, Any] = {
            'unique_name': did,
            'object_type': 'dimension',
            'label': dim['name'],
            'type': dim_type,
            'dataset': key_ref['source_id'],
            'key_column': key_ref['field'],
            'name_column': name_ref['field'],
        }
        if dim.get('description'):
            dim_doc['description'] = dim['description']
        if dim.get('display_folder'):
            dim_doc['folder'] = dim['display_folder']
        if dim.get('sort_field'):
            dim_doc['sort_column'] = dim['sort_field']['field']
        if dim.get('role_of'):
            dim_doc['role_of'] = dim['role_of']
            dim_doc['active'] = bool(dim.get('active', True))
        if dim.get('time_intelligence'):
            dim_doc['time_intelligence'] = copy.deepcopy(
                dim['time_intelligence']
            )
        if sml_attrs:
            dim_doc['level_attributes'] = sml_attrs
        if sml_hiers:
            dim_doc['hierarchies'] = sml_hiers
        if ('dimension', did) in tr_index:
            dim_doc['locales'] = tr_index[('dimension', did)]
        dimension_docs.append(dim_doc)
        files[f'dimensions/{did}.yml'] = dump_deterministic_yaml(dim_doc)

    metric_docs: list[dict[str, Any]] = []
    for meas in model['measures']:
        mid = meas['id']
        is_calc = meas.get('expression') is not None
        agg = meas['aggregation']
        m_doc: dict[str, Any] = {
            'unique_name': mid,
            'object_type': 'metric_calc' if is_calc else 'metric',
            'label': meas['name'],
        }
        if meas.get('description'):
            m_doc['description'] = meas['description']
        if meas.get('display_folder'):
            m_doc['folder'] = meas['display_folder']
        if meas.get('format'):
            m_doc['format'] = meas['format']
        if meas.get('measure_group_id'):
            m_doc['measure_group'] = meas['measure_group_id']
        if is_calc:
            m_doc['expression'] = _expression_to_sql_formula(
                meas['expression'], measures_by_id
            )
            m_doc['expression_ast'] = copy.deepcopy(meas['expression'])
        else:
            if meas.get('field'):
                m_doc['dataset'] = meas['field']['source_id']
                m_doc['column'] = meas['field']['field']
            if agg in SEMI_ADDITIVE_AGGREGATIONS:
                m_doc['calculation_method'] = agg
                m_doc['semi_additive'] = {
                    'mode': agg,
                    'dimension': meas['semi_additive_dimension'],
                    'within_group_aggregation': meas.get(
                        'within_group_aggregation', 'sum'
                    ),
                }
            else:
                m_doc['calculation_method'] = agg
            if meas.get('filters'):
                m_doc['filters'] = [
                    _filter_to_dict(f) for f in meas['filters']
                ]
        if ('measure', mid) in tr_index:
            m_doc['locales'] = tr_index[('measure', mid)]
        metric_docs.append(m_doc)
        files[f'metrics/{mid}.yml'] = dump_deterministic_yaml(m_doc)

    perspective_docs: list[dict[str, Any]] = []
    for persp in model.get('perspectives', []):
        pid = persp['id']
        p_doc: dict[str, Any] = {
            'unique_name': pid,
            'object_type': 'perspective',
            'label': persp['name'],
            'description': persp.get('description', ''),
            'dimensions': list(persp.get('dimensions', [])),
            'metrics': list(persp.get('measures', [])),
            'measure_groups': list(persp.get('measure_groups', [])),
            'hierarchies': list(persp.get('hierarchies', [])),
        }
        if persp.get('default_measure'):
            p_doc['default_metric'] = persp['default_measure']
        if ('perspective', pid) in tr_index:
            p_doc['locales'] = tr_index[('perspective', pid)]
        perspective_docs.append(p_doc)
        files[f'perspectives/{pid}.yml'] = dump_deterministic_yaml(p_doc)

    aggregate_docs: list[dict[str, Any]] = []
    for mat in model.get('materializations', []):
        mat_id = mat['id']
        a_doc: dict[str, Any] = {
            'unique_name': mat_id,
            'object_type': 'aggregate',
            'label': mat['name'],
            'strategy': mat.get('strategy', 'provider_managed'),
            'enabled': bool(mat.get('enabled', False)),
            'grain_dimensions': list(mat.get('grain_dimensions') or []),
            'metrics': list(mat.get('measures') or []),
            'target_relation': list(mat.get('target_relation') or []),
        }
        if mat.get('measure_group_id'):
            a_doc['measure_group'] = mat['measure_group_id']
        aggregate_docs.append(a_doc)
        files[f'aggregates/{mat_id}.yml'] = dump_deterministic_yaml(a_doc)

    sml_relationships: list[dict[str, Any]] = []
    dims_by_id = {d['id']: d for d in model['dimensions']}
    for grp in groups:
        for usage in grp.get('dimension_usage', []):
            did = usage['dimension_id']
            dim_obj = dims_by_id.get(did, {})
            join_obj = joins_by_id.get(
                usage.get('join_id') or dim_obj.get('join_id') or ''
            )
            rel_entry: dict[str, Any] = {
                'unique_name': f"{grp['id']}_to_{did}",
                'from_dataset': grp['fact_source'],
                'to_dimension': dim_obj.get('role_of') or did,
                'relationship_kind': usage.get('relationship_kind', 'regular'),
                'active': bool(usage.get('active', True)),
            }
            if dim_obj.get('role_of'):
                rel_entry['role_play'] = did
            if join_obj and join_obj.get('predicates'):
                first_pred = join_obj['predicates'][0]
                rel_entry['from_columns'] = [
                    p['left']['field'] for p in join_obj['predicates']
                ]
                rel_entry['to_columns'] = [
                    p['right']['field'] for p in join_obj['predicates']
                ]
                rel_entry['join_type'] = join_obj.get('join_type', 'left')
                rel_entry.setdefault(
                    'to_dataset', first_pred['right']['source_id']
                )
            elif usage.get('granularity_field'):
                rel_entry['from_columns'] = [
                    usage['granularity_field']['field']
                ]
                key_f = dim_obj.get('key_field') or dim_obj.get('field') or {}
                if key_f.get('field'):
                    rel_entry['to_columns'] = [key_f['field']]
            sml_relationships.append(rel_entry)

    model_locales: dict[str, dict[str, str]] = {}
    for tr in translations:
        loc_meta: dict[str, str] = {}
        if tr.get('caption'):
            loc_meta['caption'] = tr['caption']
        if tr.get('description'):
            loc_meta['description'] = tr['description']
        if loc_meta:
            model_locales[tr['locale']] = loc_meta
    for loc, payload in tr_index.get(('model', 'model'), {}).items():
        model_locales.setdefault(loc, {}).update(payload)

    sml_model_doc: dict[str, Any] = {
        'unique_name': model_slug,
        'object_type': 'model',
        'sml_version': '1.8',
        'label': model['name'],
        'description': model.get('description', ''),
        'datasets': [d['unique_name'] for d in dataset_docs],
        'dimensions': [d['unique_name'] for d in dimension_docs],
        'metrics': [m['unique_name'] for m in metric_docs],
        'measure_groups': [
            {
                'unique_name': g['id'],
                'label': g['name'],
                'fact_dataset': g['fact_source'],
                'metrics': list(g.get('measures', [])),
                **(
                    {'locales': tr_index[('measure_group', g['id'])]}
                    if ('measure_group', g['id']) in tr_index else {}
                ),
            }
            for g in groups
        ],
        'relationships': sml_relationships,
    }
    if perspective_docs:
        sml_model_doc['perspectives'] = [
            p['unique_name'] for p in perspective_docs
        ]
    if aggregate_docs:
        sml_model_doc['aggregates'] = [
            a['unique_name'] for a in aggregate_docs
        ]
    if model_locales:
        sml_model_doc['locales'] = model_locales
    for tr in translations:
        loc_doc = {
            'object_type': 'locale',
            'locale': tr['locale'],
            'caption': tr.get('caption', ''),
            'description': tr.get('description', ''),
            'entries': copy.deepcopy(tr.get('entries', [])),
        }
        files[f"locales/{tr['locale']}.yml"] = dump_deterministic_yaml(loc_doc)

    files[f'models/{model_slug}.yml'] = dump_deterministic_yaml(sml_model_doc)

    manifest_doc = {
        'sml_version': '1.8',
        'exporter': 'ScratchRobin',
        'model': model_slug,
        'files': sorted(files),
        'locales': [t['locale'] for t in translations],
    }
    manifest_yaml = dump_deterministic_yaml(manifest_doc)
    files['sml_manifest.yml'] = manifest_yaml

    bundle = {
        'manifest': manifest_doc,
        'model': sml_model_doc,
        'datasets': dataset_docs,
        'dimensions': dimension_docs,
        'metrics': metric_docs,
        'perspectives': perspective_docs,
        'aggregates': aggregate_docs,
    }
    combined_yaml = dump_deterministic_yaml(bundle)
    loss_report = {
        'format': SML_FORMAT,
        'fidelity': 'lossy' if loss_items else 'exact',
        'loss_count': len(loss_items),
        'dropped_or_degraded_count': len(loss_items),
        'items': loss_items,
    }
    return {
        'format': SML_FORMAT,
        'bundle': bundle,
        'files': files,
        'manifest_yaml': manifest_yaml,
        'yaml': combined_yaml,
        'yaml_text': combined_yaml,
        'loss_report': loss_report,
    }


def export_cube_to_ossie(
    model_or_ddn: Mapping[str, Any] | str,
    *,
    include_custom_extensions: bool = True,
) -> dict[str, Any]:
    """Export a Cube design to Apache Ossie v0.2.0 with explicit loss report.

    Apache Ossie v0.2.0 represents flat ``datasets``, pairwise
    ``relationships`` and SQL-expression ``metrics``. Dimensional constructs
    outside Ossie's schema are itemized in ``loss_report`` so users never
    mistake Ossie output for a lossless cube backup.
    """
    model = _normalize_cube_input(model_or_ddn)
    measures_by_id = {m['id']: m for m in model.get('measures', [])}
    loss_items: list[dict[str, Any]] = []

    datasets_by_id: dict[str, dict[str, Any]] = {}
    for src in model['sources']:
        sid = src['id']
        rel = src.get('relation') or [sid]
        pk = [g['field'] for g in src.get('grain', []) if g.get('field')]
        datasets_by_id[sid] = {
            'name': sid,
            'source': '.'.join(rel),
            'primary_key': pk,
            'dimensions': [],
            'time_dimensions': [],
            'fields': [
                {'name': col_name, 'expression': col_name}
                for col_name in pk
            ],
        }

    def _ensure_dataset_field(sid: str, col_name: str) -> None:
        ds = datasets_by_id.get(sid)
        if ds is None or not col_name:
            return
        if not any(f['name'] == col_name for f in ds['fields']):
            ds['fields'].append({'name': col_name, 'expression': col_name})

    for dim in model['dimensions']:
        did = dim['id']
        key_ref = dim.get('key_field') or dim['field']
        sid = key_ref['source_id']
        col = key_ref['field']
        _ensure_dataset_field(sid, col)
        ds = datasets_by_id.get(sid)
        if ds is not None:
            if dim.get('time_intelligence'):
                ds['time_dimensions'].append({
                    'name': did,
                    'label': dim['name'],
                    'expression': col,
                })
                ti = dim['time_intelligence']
                if ti.get('fiscal_year_start_month', 1) != 1 or (
                    ti.get('calendar', 'gregorian') != 'gregorian'
                ):
                    loss_items.append({
                        'category': 'time_intelligence_calendar',
                        'item_id': did,
                        'item_name': dim['name'],
                        'reason': (
                            'Apache Ossie 0.2.0 does not represent fiscal '
                            'year start months or non-Gregorian calendars.'
                        ),
                        'mitigation': (
                            'Retain DDN or SML for fiscal/calendar semantics.'
                        ),
                    })
            else:
                ds['dimensions'].append({
                    'name': did,
                    'label': dim['name'],
                    'expression': col,
                })
            for attr in dim.get('attributes', []):
                a_sid = attr['field']['source_id']
                a_col = attr['field']['field']
                _ensure_dataset_field(a_sid, a_col)
                target_ds = datasets_by_id.get(a_sid, ds)
                target_ds['dimensions'].append({
                    'name': attr['id'],
                    'label': attr['name'],
                    'expression': a_col,
                })

        if dim.get('role_of'):
            loss_items.append({
                'category': 'role_playing_dimension',
                'item_id': did,
                'item_name': dim['name'],
                'reason': (
                    f"Role-playing dimension '{did}' (role of "
                    f"'{dim['role_of']}', active={dim.get('active', True)}) "
                    'is flattened because Apache Ossie 0.2.0 has no '
                    'role-playing alias or active-relationship flag.'
                ),
                'mitigation': (
                    'Duplicate dataset aliases manually in Ossie consumers '
                    'or export SML v1.8.'
                ),
            })
        elif dim.get('active') is False:
            loss_items.append({
                'category': 'inactive_relationship',
                'item_id': did,
                'item_name': dim['name'],
                'reason': (
                    'Apache Ossie 0.2.0 relationships cannot be marked '
                    'inactive.'
                ),
                'mitigation': 'Use SML v1.8 or DDN to retain inactive joins.',
            })

        for hier in dim.get('hierarchies', []):
            h_kind = hier.get('hierarchy_kind', 'level')
            if h_kind == 'parent_child':
                _ensure_dataset_field(
                    hier['child_field']['source_id'],
                    hier['child_field']['field'],
                )
                _ensure_dataset_field(
                    hier['parent_field']['source_id'],
                    hier['parent_field']['field'],
                )
                loss_items.append({
                    'category': 'parent_child_hierarchy',
                    'item_id': hier['id'],
                    'item_name': hier['name'],
                    'reason': (
                        'Parent-child recursive hierarchy closure and max '
                        'depth are unsupported in Apache Ossie 0.2.0.'
                    ),
                    'mitigation': (
                        'Pre-flatten hierarchy levels or use SML v1.8 / DDN.'
                    ),
                })
            else:
                for lvl in hier.get('levels', []):
                    _ensure_dataset_field(
                        lvl['field']['source_id'], lvl['field']['field']
                    )
                loss_items.append({
                    'category': 'level_hierarchy',
                    'item_id': hier['id'],
                    'item_name': hier['name'],
                    'reason': (
                        'Ordered drill hierarchies are flattened to '
                        'unstructured dataset dimensions in Apache Ossie '
                        '0.2.0.'
                    ),
                    'mitigation': 'Use SML v1.8 or DDN for drill paths.',
                })

    ossie_relationships: list[dict[str, Any]] = []
    for join in model.get('joins', []):
        if join.get('active') is False:
            loss_items.append({
                'category': 'inactive_join',
                'item_id': join['id'],
                'item_name': join['id'],
                'reason': (
                    f"Inactive join '{join['id']}' is omitted from active "
                    'Apache Ossie relationships.'
                ),
                'mitigation': (
                    'Use SML v1.8 or DDN to preserve inactive joins.'
                ),
            })
            continue
        ossie_relationships.append({
            'name': join['id'],
            'left_dataset': join['left_source'],
            'right_dataset': join['right_source'],
            'join_type': join.get('join_type', 'left'),
            'on': [
                {
                    'left_field': p['left']['field'],
                    'right_field': p['right']['field'],
                }
                for p in join.get('predicates', [])
            ],
        })

    if len(model.get('measure_groups', [])) > 1:
        loss_items.append({
            'category': 'measure_group_scoping',
            'item_id': 'measure_groups',
            'item_name': 'Multi-fact measure groups & dimension usage matrix',
            'reason': (
                'Apache Ossie 0.2.0 merges metrics into one flat model '
                'namespace without explicit measure-group granularity scoping.'
            ),
            'mitigation': 'Use SML v1.8 or DDN for constellation cubes.',
        })

    ossie_metrics: list[dict[str, Any]] = []
    for meas in model['measures']:
        mid = meas['id']
        agg = meas['aggregation']
        if meas.get('expression') is not None:
            expr_sql = _expression_to_sql_formula(
                meas['expression'], measures_by_id
            )
            loss_items.append({
                'category': 'calculated_measure_ast',
                'item_id': mid,
                'item_name': meas['name'],
                'reason': (
                    'Typed calculated-measure AST is serialized to a flat '
                    'SQL expression string in Apache Ossie 0.2.0.'
                ),
                'mitigation': 'Retain SML v1.8 or DDN for typed AST.',
            })
        else:
            f_ref = meas.get('field')
            col_expr = (
                f"{f_ref['source_id']}.{f_ref['field']}" if f_ref else '*'
            )
            if f_ref:
                _ensure_dataset_field(f_ref['source_id'], f_ref['field'])
            if meas.get('filters'):
                conds = []
                for flt in meas['filters']:
                    fl = flt['field']
                    _ensure_dataset_field(fl['source_id'], fl['field'])
                    val_txt = json.dumps(
                        flt.get('value', flt.get('parameter_id'))
                    )
                    conds.append(
                        f"{fl['source_id']}.{fl['field']} "
                        f"{flt.get('operator', 'eq')} {val_txt}"
                    )
                col_expr = (
                    f"CASE WHEN {' AND '.join(conds)} THEN {col_expr} END"
                )
                loss_items.append({
                    'category': 'filtered_measure',
                    'item_id': mid,
                    'item_name': meas['name'],
                    'reason': (
                        'Structured measure filter predicates are inlined '
                        'into a SQL CASE expression in Apache Ossie 0.2.0.'
                    ),
                    'mitigation': (
                        'Use SML v1.8 or DDN for structured filters.'
                    ),
                })
            if agg in SEMI_ADDITIVE_AGGREGATIONS:
                w_agg = meas.get('within_group_aggregation', 'sum').upper()
                expr_sql = f'{w_agg}({col_expr})'
                loss_items.append({
                    'category': 'semi_additive_measure',
                    'item_id': mid,
                    'item_name': meas['name'],
                    'reason': (
                        f"Semi-additive aggregation '{agg}' over "
                        f"'{meas.get('semi_additive_dimension')}' has no "
                        'native representation in Apache Ossie 0.2.0 and '
                        f'degrades to {w_agg}({col_expr}).'
                    ),
                    'mitigation': (
                        'Export SML v1.8 or keep ScratchRobin DDN to preserve '
                        'semi-additive time-snapshot semantics.'
                    ),
                })
            elif agg == 'count_distinct':
                expr_sql = f'COUNT(DISTINCT {col_expr})'
            elif agg == 'count' and not f_ref:
                expr_sql = (
                    'COUNT(*)' if col_expr == '*' else f'COUNT({col_expr})'
                )
            elif agg == 'none':
                expr_sql = col_expr
            else:
                expr_sql = f'{agg.upper()}({col_expr})'

        m_entry: dict[str, Any] = {
            'name': mid,
            'label': meas['name'],
            'expression': expr_sql,
        }
        if meas.get('description'):
            m_entry['description'] = meas['description']
        ossie_metrics.append(m_entry)

    for mat in model.get('materializations', []):
        loss_items.append({
            'category': 'materialization_plan',
            'item_id': mat['id'],
            'item_name': mat['name'],
            'reason': (
                'Materialized aggregate rules and native DDL targets are not '
                'part of Apache Ossie 0.2.0.'
            ),
            'mitigation': 'Use SML v1.8 aggregates or ScratchRobin DDN.',
        })

    for persp in model.get('perspectives', []):
        loss_items.append({
            'category': 'perspective',
            'item_id': persp['id'],
            'item_name': persp['name'],
            'reason': (
                'Named audience perspectives are unsupported in Apache Ossie '
                '0.2.0.'
            ),
            'mitigation': 'Use SML v1.8 perspectives or ScratchRobin DDN.',
        })

    for tr in model.get('translations', []):
        loss_items.append({
            'category': 'translation',
            'item_id': tr['id'],
            'item_name': tr['locale'],
            'reason': (
                f"Locale '{tr['locale']}' metadata translations are "
                'unsupported in Apache Ossie 0.2.0.'
            ),
            'mitigation': 'Use SML v1.8 locales or ScratchRobin DDN.',
        })

    security = model.get('security') or {}
    if (
        security.get('row_filters')
        or security.get('tenant_filter')
        or security.get('roles')
    ):
        loss_items.append({
            'category': 'security_policy_excluded',
            'item_id': 'security',
            'item_name': 'Row-level & tenant security policies',
            'reason': (
                'Security principals and row filters are excluded from '
                'Apache Ossie exports and custom_extensions.'
            ),
            'mitigation': 'Configure target access policies independently.',
        })

    semantic_model_entry: dict[str, Any] = {
        'name': _slug(model['name']),
        'label': model['name'],
        'description': model.get('description', ''),
        'datasets': list(datasets_by_id.values()),
        'relationships': ossie_relationships,
        'metrics': ossie_metrics,
    }
    if include_custom_extensions:
        safe_ext = {
            'exporter': 'ScratchRobin',
            'contract_version': model['contract_version'],
            'measure_groups': _effective_measure_groups(model),
            'perspectives': model.get('perspectives', []),
            'locales': [t['locale'] for t in model.get('translations', [])],
        }
        semantic_model_entry['custom_extensions'] = json.dumps(
            safe_ext, sort_keys=True, separators=(',', ':')
        )

    ossie_doc = {
        'version': '0.2.0',
        'semantic_models': [semantic_model_entry],
    }
    loss_report = {
        'format': OSSIE_FORMAT,
        'fidelity': 'lossy' if loss_items else 'exact',
        'loss_count': len(loss_items),
        'dropped_or_degraded_count': len(loss_items),
        'items': loss_items,
    }
    ossie_yaml = dump_deterministic_yaml(ossie_doc)
    return {
        'format': OSSIE_FORMAT,
        'document': ossie_doc,
        'yaml': ossie_yaml,
        'yaml_text': ossie_yaml,
        'json_text': json.dumps(ossie_doc, indent=2, ensure_ascii=False),
        'loss_report': loss_report,
    }

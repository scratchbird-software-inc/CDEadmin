##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Host-computed Project Navigator hierarchy, virtual folders, and filtering.

Performs DAG cycle-safe project hierarchy assembly, database resource-binding
extraction, 11-section virtual folder grouping, subgroup rollups, and search
filtering on the Python host so browser clients render pre-computed CDETree
nodes with minimal client-side computation.
"""

from __future__ import annotations

import json
from typing import Any


SCREEN_TYPES = frozenset({
    'cdeadmin.design.screen',
    'cdeadmin.design.screen_flow',
    'cdeadmin.design.screen_mesh',
})

GRAPH_TYPES = frozenset({
    'cdeadmin.design.question',
    'cdeadmin.design.dashboard',
    'cdeadmin.design.monitoring_dashboard',
    'cdeadmin.design.cube',
    'cube',
    'semantic-model',
})

DIAGRAM_TYPES = frozenset({
    'cdeadmin.design.erd',
    'ddn-workspace',
    'cdeadmin.lineage.v1',
    'cdeadmin.schema_compare.v1',
    'cdeadmin.etl.v1',
    'cdeadmin.cdc.v1',
    'cdeadmin.replication.v1',
    'cdeadmin.migration.v1',
    'cdeadmin.tracing.v1',
})

PROJECT_LOCAL_ASSET_TYPES = frozenset({
    'cdeadmin.project.report.print.v1',
    'cdeadmin.project.report.pdf.v1',
    'cdeadmin.project.task.v1',
    'cdeadmin.project.calendar.v1',
    'cdeadmin.project.channel.v1',
    'cdeadmin.project.document.v1',
})

DISCOVERY_TYPES = frozenset({
    'BusinessTerm',
    'Domain',
    'MetricDefinition',
    'DataProduct',
    'SavedSearch',
    'DiscoveryCollection',
    'RankingProfile',
    'CertificationProfile',
    'IndexSourceConfig',
})


def asset_icon(asset_type: str | None) -> str:
    at = str(asset_type or '')
    if at in ('ddn-workspace', 'cdeadmin.design.erd'):
        return 'tool.erd'
    if at == 'cdeadmin.lineage.v1':
        return 'tool.lineage'
    if at == 'cdeadmin.schema_compare.v1':
        return 'tool.schema-compare'
    if at == 'cdeadmin.quality.v1':
        return 'tool.quality'
    if at == 'cdeadmin.contract.v1':
        return 'tool.contract'
    if at == 'cdeadmin.etl.v1':
        return 'tool.etl'
    if at == 'cdeadmin.cdc.v1':
        return 'tool.cdc'
    if at == 'cdeadmin.replication.v1':
        return 'tool.replication'
    if at == 'cdeadmin.tracing.v1':
        return 'tool.tracing'
    if at == 'cdeadmin.migration.v1':
        return 'tool.migration'
    if at == 'cdeadmin.api.v1':
        return 'tool.api'
    if at == 'cdeadmin.ml_vector.v1':
        return 'tool.ml-vector'
    if at == 'cdeadmin.ai.v1' or at.startswith('cdeadmin.ai_interface.'):
        return 'tool.ai'
    if at in DISCOVERY_TYPES or at.startswith('cdeadmin.discovery.'):
        return 'tool.search'
    if at in SCREEN_TYPES:
        return 'ui.screen_frame'
    if at in (
        'cdeadmin.design.question',
        'cdeadmin.design.dashboard',
        'cdeadmin.design.monitoring_dashboard',
    ):
        return 'tool.bi'
    if at in ('cube', 'cdeadmin.design.cube'):
        return 'object.cube'
    if at == 'semantic-model':
        return 'object.semantic_model'
    if at in ('query', 'script', 'cdeadmin.sql-notebook.v1'):
        return 'tool.query'
    if at == 'cdeadmin.project.task.v1':
        return 'action.check'
    if at == 'cdeadmin.project.calendar.v1':
        return 'action.schedule'
    if at == 'cdeadmin.project.channel.v1':
        return 'action.section_comments'
    if at in (
        'cdeadmin.project.report.print.v1',
        'cdeadmin.project.report.pdf.v1',
    ):
        return 'action.export'
    return 'object.notebook'


def db_object_icon(kind: str | None) -> str:
    normalized = str(kind or 'table').lower()
    if normalized in ('table', 'view', 'procedure', 'package', 'function', 'sequence'):
        return f'object.{normalized}'
    return 'object.table'


def build_project_hierarchy(
    projects: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    by_id = {p['project_id']: p for p in (projects or []) if p.get('project_id')}
    children_map: dict[str, list[dict[str, Any]]] = {}
    roots: list[dict[str, Any]] = []

    def introduces_cycle(project: dict[str, Any]) -> bool:
        seen = {project['project_id']}
        parent_id = project.get('parent_project_id')
        cur = by_id.get(parent_id) if parent_id else None
        while cur is not None:
            cid = cur['project_id']
            if cid in seen:
                return True
            seen.add(cid)
            next_pid = cur.get('parent_project_id')
            cur = by_id.get(next_pid) if next_pid else None
        return False

    for project in projects or []:
        parent_id = project.get('parent_project_id')
        if parent_id and parent_id in by_id and not introduces_cycle(project):
            children_map.setdefault(parent_id, []).append(project)
        else:
            roots.append(project)

    roots.sort(key=lambda item: (str(item.get('name') or '').lower(), item['project_id']))
    for child_list in children_map.values():
        child_list.sort(
            key=lambda item: (str(item.get('name') or '').lower(), item['project_id'])
        )
    return roots, children_map, by_id


def extract_project_database_objects(
    assets: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    buckets: dict[str, dict[str, dict[str, Any]]] = {
        'table': {},
        'view': {},
        'procedure': {},
        'package': {},
        'function': {},
        'sequence': {},
    }
    for asset in assets or []:
        for raw in asset.get('resource_bindings') or []:
            if not isinstance(raw, dict):
                continue
            ref_id = str(raw.get('resource_id') or '')
            if ':' in ref_id:
                inferred_kind, inferred_name = ref_id.split(':', 1)
            else:
                inferred_kind, inferred_name = 'table', ref_id
            kind = str(raw.get('kind') or inferred_kind or 'table').lower()
            name = str(raw.get('nativeIdentity') or inferred_name or '').strip()
            if not name or kind not in buckets:
                continue
            role = str(raw.get('bindingRole') or 'linked')
            existing = buckets[kind].get(name)
            if existing is None or (existing.get('bindingRole') != 'owned' and role == 'owned'):
                buckets[kind][name] = {
                    **raw,
                    'kind': kind,
                    'nativeIdentity': name,
                    'resource_id': f'{kind}:{name}',
                    'bindingRole': role,
                }
    return {
        kind: sorted(bucket.values(), key=lambda item: item['nativeIdentity'].lower())
        for kind, bucket in buckets.items()
    }


def build_project_virtual_tree(
    project: dict[str, Any],
    state: dict[str, Any] | None,
    child_projects: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    pid = project['project_id']
    assets = list((state or {}).get('assets') or [])
    child_list = list(child_projects or [])
    db_objects = extract_project_database_objects(assets)

    screens: list[dict[str, Any]] = []
    reports_print: list[dict[str, Any]] = []
    reports_graphs: list[dict[str, Any]] = []
    reports_diagrams: list[dict[str, Any]] = []
    reports_pdf: list[dict[str, Any]] = []
    tasks_pending: list[dict[str, Any]] = []
    tasks_in_process: list[dict[str, Any]] = []
    tasks_completed: list[dict[str, Any]] = []
    cal_shared_personal: list[dict[str, Any]] = []
    cal_gantt: list[dict[str, Any]] = []
    channels: list[dict[str, Any]] = []
    documents: list[dict[str, Any]] = []

    for asset in assets:
        at = str(asset.get('asset_type') or '')
        meta = asset.get('metadata') if isinstance(asset.get('metadata'), dict) else {}
        if at in SCREEN_TYPES:
            screens.append(asset)
        elif at == 'cdeadmin.project.report.print.v1' or meta.get('report_category') == 'print':
            reports_print.append(asset)
        elif at == 'cdeadmin.project.report.pdf.v1' or meta.get('report_category') == 'pdf':
            reports_pdf.append(asset)
        elif at in GRAPH_TYPES:
            reports_graphs.append(asset)
        elif at in DIAGRAM_TYPES:
            reports_diagrams.append(asset)
        elif at == 'cdeadmin.project.task.v1':
            st = str(meta.get('task_status') or 'pending').lower()
            if st == 'completed':
                tasks_completed.append(asset)
            elif st in ('in_process', 'in-process'):
                tasks_in_process.append(asset)
            else:
                tasks_pending.append(asset)
        elif at == 'cdeadmin.project.calendar.v1':
            if str(meta.get('calendar_kind') or '').lower() == 'gantt':
                cal_gantt.append(asset)
            else:
                cal_shared_personal.append(asset)
        elif at == 'cdeadmin.project.channel.v1':
            channels.append(asset)
        else:
            documents.append(asset)

    raw_members = list((state or {}).get('members') or [])
    meta_groups = list((state or {}).get('metadata_groups') or [])
    member_groups: list[dict[str, Any]] = [
        {
            'id': f"role-{m.get('principal_id')}",
            'label': m.get('label') or f"Role #{m.get('principal_id')}",
            'access_level': m.get('access_level'),
            'principal_type': 'role',
            'principal_id': m.get('principal_id'),
        }
        for m in raw_members
        if m.get('principal_type') == 'role'
    ] + meta_groups

    team_doc = next(
        (
            d for d in documents
            if isinstance(d.get('metadata'), dict)
            and d['metadata'].get('document_kind') == 'team_roster'
        ),
        None,
    )
    team_meta = team_doc.get('metadata') if isinstance(team_doc, dict) else {}
    if isinstance(team_meta, dict) and isinstance(team_meta.get('groups'), list):
        for grp in team_meta['groups']:
            if isinstance(grp, dict) and grp.get('name'):
                if not any(x.get('label') == grp['name'] for x in member_groups):
                    member_groups.append({
                        'id': f"grp-{grp['name']}",
                        'label': grp['name'],
                        'access_level': grp.get('access') or 'editor',
                        'principal_type': 'role',
                    })

    lead_name = (
        team_meta.get('lead')
        if isinstance(team_meta, dict) and team_meta.get('lead')
        else 'Project Owner (cdeadmin@localhost)'
    )
    member_individuals: list[dict[str, Any]] = [
        {
            'id': f'owner-{pid}',
            'label': lead_name,
            'access_level': project.get('access') or 'owner',
            'principal_type': 'user',
        },
        *[
            {
                'id': f"user-{m.get('principal_id')}",
                'label': m.get('label') or f"User #{m.get('principal_id')}",
                'access_level': m.get('access_level'),
                'principal_type': 'user',
                'principal_id': m.get('principal_id'),
            }
            for m in raw_members
            if m.get('principal_type') == 'user'
        ],
    ]
    if isinstance(team_meta, dict) and isinstance(team_meta.get('individuals'), list):
        for ind in team_meta['individuals']:
            if isinstance(ind, dict) and ind.get('name'):
                label = f"{ind['name']} ({ind.get('role') or 'Contributor'})"
                if not any(x.get('label') in (ind['name'], label) for x in member_individuals):
                    member_individuals.append({
                        'id': f"ind-{ind['name']}",
                        'label': label,
                        'access_level': ind.get('access') or 'editor',
                        'principal_type': 'user',
                    })

    def to_db_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                'itemKind': 'db-object',
                'id': f"{pid}:db:{obj['kind']}:{obj['nativeIdentity']}",
                'label': obj['nativeIdentity'],
                'iconKey': db_object_icon(obj['kind']),
                'badge': 'owned' if obj.get('bindingRole') == 'owned' else 'linked',
                'dbObject': obj,
                'project': project,
            }
            for obj in items
        ]

    def to_asset_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sorted_items = sorted(
            items,
            key=lambda a: (str(a.get('name') or '').lower(), str(a.get('asset_id') or '')),
        )
        return [
            {
                'itemKind': 'asset',
                'id': f"{pid}:asset:{asset['asset_id']}",
                'label': asset['name'],
                'iconKey': asset_icon(asset.get('asset_type')),
                'badge': f"v{asset.get('version') or 1}",
                'warning': (
                    'Validation failed'
                    if asset.get('validation_state') == 'invalid'
                    else ''
                ),
                'asset': asset,
                'project': project,
            }
            for asset in sorted_items
        ]

    def to_member_items(items: list[dict[str, Any]], icon_key: str) -> list[dict[str, Any]]:
        return [
            {
                'itemKind': 'member',
                'id': f"{pid}:member:{m['id']}",
                'label': m['label'],
                'iconKey': icon_key,
                'badge': m.get('access_level') or 'viewer',
                'member': m,
                'project': project,
            }
            for m in items
        ]

    coding_subgroups = [
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:coding:procedures',
            'key': 'procedures',
            'label': 'Procedures',
            'iconKey': 'object.procedure',
            'project': project,
            'items': to_db_items(db_objects['procedure']),
            'subgroups': [],
        },
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:coding:packages',
            'key': 'packages',
            'label': 'Packages',
            'iconKey': 'object.package',
            'project': project,
            'items': to_db_items(db_objects['package']),
            'subgroups': [],
        },
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:coding:functions',
            'key': 'functions',
            'label': 'Functions',
            'iconKey': 'object.function',
            'project': project,
            'items': to_db_items(db_objects['function']),
            'subgroups': [],
        },
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:coding:sequences',
            'key': 'sequences',
            'label': 'Sequences',
            'iconKey': 'object.sequence',
            'project': project,
            'items': to_db_items(db_objects['sequence']),
            'subgroups': [],
        },
    ]

    reports_subgroups = [
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:reports:print',
            'key': 'print',
            'label': 'Print',
            'iconKey': 'action.export',
            'project': project,
            'items': to_asset_items(reports_print),
            'subgroups': [],
        },
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:reports:graphs',
            'key': 'graphs',
            'label': 'Graphs',
            'iconKey': 'tool.bi',
            'project': project,
            'items': to_asset_items(reports_graphs),
            'subgroups': [],
        },
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:reports:diagrams',
            'key': 'diagrams',
            'label': 'Diagrams',
            'iconKey': 'tool.erd',
            'project': project,
            'items': to_asset_items(reports_diagrams),
            'subgroups': [],
        },
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:reports:pdf',
            'key': 'pdf',
            'label': 'PDF',
            'iconKey': 'action.export',
            'project': project,
            'items': to_asset_items(reports_pdf),
            'subgroups': [],
        },
    ]

    tasks_subgroups = [
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:tasks:pending',
            'key': 'pending',
            'label': 'Pending',
            'iconKey': 'action.check',
            'project': project,
            'items': to_asset_items(tasks_pending),
            'subgroups': [],
        },
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:tasks:in_process',
            'key': 'in_process',
            'label': 'In Process',
            'iconKey': 'action.execute',
            'project': project,
            'items': to_asset_items(tasks_in_process),
            'subgroups': [],
        },
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:tasks:completed',
            'key': 'completed',
            'label': 'Completed',
            'iconKey': 'action.check',
            'project': project,
            'items': to_asset_items(tasks_completed),
            'subgroups': [],
        },
    ]

    calendars_subgroups = [
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:calendars:shared_personal',
            'key': 'shared_personal',
            'label': 'Shared & Personal Calendars',
            'iconKey': 'action.schedule',
            'project': project,
            'items': to_asset_items(cal_shared_personal),
            'subgroups': [],
        },
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:calendars:gantt',
            'key': 'gantt',
            'label': 'Gantt Charts',
            'iconKey': 'tool.bi',
            'project': project,
            'items': to_asset_items(cal_gantt),
            'subgroups': [],
        },
    ]

    members_subgroups = [
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:members:groups',
            'key': 'groups',
            'label': 'Groups',
            'iconKey': 'folder.security',
            'project': project,
            'items': to_member_items(member_groups, 'folder.security'),
            'subgroups': [],
        },
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:members:individuals',
            'key': 'individuals',
            'label': 'Individuals',
            'iconKey': 'object.role',
            'project': project,
            'items': to_member_items(member_individuals, 'object.role'),
            'subgroups': [],
        },
    ]

    top_virtuals = [
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:projects',
            'key': 'projects',
            'label': 'Projects',
            'iconKey': 'folder.system',
            'project': project,
            'childProjects': child_list,
            'items': [],
            'subgroups': [],
        },
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:tables',
            'key': 'tables',
            'label': 'Tables',
            'iconKey': 'object.table',
            'project': project,
            'items': to_db_items(db_objects['table']),
            'subgroups': [],
        },
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:views',
            'key': 'views',
            'label': 'Views',
            'iconKey': 'object.view',
            'project': project,
            'items': to_db_items(db_objects['view']),
            'subgroups': [],
        },
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:coding',
            'key': 'coding',
            'label': 'Coding',
            'iconKey': 'folder.programming',
            'project': project,
            'items': [],
            'subgroups': coding_subgroups,
        },
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:screens',
            'key': 'screens',
            'label': 'Screens',
            'iconKey': 'ui.screen_frame',
            'project': project,
            'items': to_asset_items(screens),
            'subgroups': [],
        },
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:reports',
            'key': 'reports',
            'label': 'Reports',
            'iconKey': 'tool.bi',
            'project': project,
            'items': [],
            'subgroups': reports_subgroups,
        },
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:tasks',
            'key': 'tasks',
            'label': 'Tasks',
            'iconKey': 'action.check',
            'project': project,
            'items': [],
            'subgroups': tasks_subgroups,
        },
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:calendars',
            'key': 'calendars',
            'label': 'Calendars',
            'iconKey': 'action.schedule',
            'project': project,
            'items': [],
            'subgroups': calendars_subgroups,
        },
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:channels',
            'key': 'channels',
            'label': 'Channels',
            'iconKey': 'action.section_comments',
            'project': project,
            'items': to_asset_items(channels),
            'subgroups': [],
        },
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:members',
            'key': 'members',
            'label': 'Members',
            'iconKey': 'folder.security',
            'project': project,
            'items': [],
            'subgroups': members_subgroups,
        },
        {
            'nodeKind': 'virtual',
            'id': f'virt:{pid}:documents',
            'key': 'documents',
            'label': 'Notes, Documents, Transcripts',
            'iconKey': 'object.notebook',
            'project': project,
            'items': to_asset_items(documents),
            'subgroups': [],
        },
    ]

    def stamp_counts(vnode: dict[str, Any]) -> dict[str, Any]:
        sub_total = 0
        for sg in vnode.get('subgroups') or []:
            stamp_counts(sg)
            sub_total += sg['totalCount']
        vnode['totalCount'] = (
            len(vnode.get('items') or [])
            + len(vnode.get('childProjects') or [])
            + sub_total
        )
        return vnode

    return [stamp_counts(v) for v in top_virtuals]


def _safe_token(value: str) -> str:
    return (
        str(value or '')
        .replace('/', '_')
        .replace(':', '~')
        .replace(' ', '_')
    )


def _project_tree_node(
    project: dict[str, Any],
    child_count: int,
    *,
    auto_expand: bool = False,
) -> dict[str, Any]:
    pid = project['project_id']
    access = project.get('access') or 'owner'
    access_label = 'Owner' if access == 'owner' else str(access)
    info = f' ({child_count} sub)' if child_count > 0 else f' ({access_label})'
    icon_key = 'folder.system' if child_count > 0 else 'object.schema'
    return {
        'id': f'proj~{_safe_token(pid)}',
        'label': project['name'],
        'info_label': info,
        'icon': icon_key,
        'icon_key': icon_key,
        '_type': 'cde_project',
        'object_type': 'project',
        'inode': True,
        'has_children': True,
        'expandable': True,
        'auto_expand': auto_expand,
        'project_id': pid,
        'project': project,
        'nav_payload': {
            'kind': 'project',
            'projectId': pid,
            'virtualId': None,
            'item': None,
        },
    }


def _virtual_tree_node(
    project: dict[str, Any],
    vnode: dict[str, Any],
    *,
    force_expand: bool = False,
) -> dict[str, Any]:
    pid = project['project_id']
    total = int(vnode.get('totalCount') or 0)
    subgroups = vnode.get('subgroups') or []
    has_children = total > 0 or len(subgroups) > 0
    is_projects_group = vnode.get('key') == 'projects'
    auto_expand = force_expand or (
        (is_projects_group and 0 < total <= 12)
        or (not is_projects_group and 0 < total <= 8)
    )
    return {
        'id': _safe_token(vnode['id']),
        'label': vnode['label'],
        'info_label': f' ({total})',
        'icon': vnode['iconKey'],
        'icon_key': vnode['iconKey'],
        '_type': 'cde_project_virtual',
        'object_type': 'folder',
        'inode': True,
        'has_children': has_children,
        'expandable': has_children,
        'auto_expand': auto_expand,
        'project_id': pid,
        'virtual_id': vnode['id'],
        'project': project,
        'nav_payload': {
            'kind': 'virtual',
            'projectId': pid,
            'virtualId': vnode['id'],
            'item': None,
        },
    }


def _leaf_tree_node(leaf: dict[str, Any]) -> dict[str, Any]:
    badge = leaf.get('badge') or ''
    return {
        'id': f"item~{_safe_token(leaf['id'])}",
        'label': leaf['label'],
        'info_label': f' · {badge}' if badge else '',
        'icon': leaf['iconKey'],
        'icon_key': leaf['iconKey'],
        '_type': 'cde_project_leaf',
        'object_type': leaf.get('itemKind') or 'asset',
        'inode': False,
        'has_children': False,
        'expandable': False,
        'auto_expand': False,
        'project_id': leaf['project']['project_id'],
        'leaf': leaf,
    }


def _item_matches_filter(item: dict[str, Any], q: str) -> bool:
    if not q:
        return True
    asset = item.get('asset') or {}
    haystack = ' '.join([
        str(item.get('label') or ''),
        str(asset.get('path') or ''),
        str(asset.get('asset_type') or ''),
    ]).lower()
    return q in haystack


def _collect_matching_project_ids(
    service: Any,
    user_id: int,
    role_ids: tuple[int, ...],
    roots: list[dict[str, Any]],
    children_map: dict[str, list[dict[str, Any]]],
    q: str,
) -> set[str]:
    if not q:
        all_ids: set[str] = set()
        stack = list(roots)
        while stack:
            cur = stack.pop()
            cid = cur['project_id']
            if cid not in all_ids:
                all_ids.add(cid)
                stack.extend(children_map.get(cid) or [])
        return all_ids

    # Build lightweight per-project search text on the host from repository rows
    search_blobs: dict[str, str] = {}
    if hasattr(service, 'repository') and hasattr(service.repository, 'projects'):
        for row, _access in service.repository.projects(user_id, role_ids):
            parts = [str(row.name or ''), str(row.project_key or '')]
            for asset in getattr(row, 'assets', None) or []:
                parts.append(str(getattr(asset, 'name', '') or ''))
                parts.append(str(getattr(asset, 'path', '') or ''))
                parts.append(str(getattr(asset, 'asset_type', '') or ''))
                raw_rb = getattr(asset, 'resource_bindings', None)
                if raw_rb:
                    try:
                        rbs = json.loads(raw_rb) if isinstance(raw_rb, str) else raw_rb
                    except Exception:
                        rbs = []
                    for rb in rbs or []:
                        if isinstance(rb, dict):
                            parts.append(
                                str(rb.get('nativeIdentity') or rb.get('resource_id') or '')
                            )
            search_blobs[row.project_key] = ' '.join(parts).lower()

    matched: set[str] = set()

    def check_subtree(proj: dict[str, Any], visited: set[str]) -> bool:
        pid = proj['project_id']
        if pid in visited:
            return False
        visited.add(pid)
        blob = search_blobs.get(pid)
        if blob is None:
            blob = f"{proj.get('name') or ''} {pid}".lower()
        self_matches = q in blob
        child_matches = False
        for child in children_map.get(pid) or []:
            if check_subtree(child, visited):
                child_matches = True
        if self_matches or child_matches:
            matched.add(pid)
            return True
        return False

    for root in roots:
        check_subtree(root, set())
    return matched


def list_project_navigator_nodes(
    service: Any,
    user_id: int,
    role_ids: tuple[int, ...] = (),
    *,
    parent: str = '',
    query: str = '',
) -> dict[str, Any]:
    q = str(query or '').strip().lower()
    projects = service.list_projects(user_id, role_ids)
    roots, children_map, by_id = build_project_hierarchy(projects)
    matching_ids = _collect_matching_project_ids(
        service, user_id, role_ids, roots, children_map, q
    )

    clean_parent = str(parent or '').strip().strip('/')
    if clean_parent in ('', 'project-navigator'):
        visible_roots = [p for p in roots if p['project_id'] in matching_ids]
        return {
            'parent': '',
            'matching_project_count': len(matching_ids),
            'total_project_count': len(projects),
            'nodes': [
                _project_tree_node(
                    p,
                    len([
                        ch for ch in (children_map.get(p['project_id']) or [])
                        if ch['project_id'] in matching_ids
                    ]),
                    auto_expand=bool(q),
                )
                for p in visible_roots
            ],
        }

    last_seg = clean_parent.split('/')[-1]

    # Case 1: Expanding a project node -> return its 11 virtual folders
    if last_seg.startswith('proj~'):
        pid_token = last_seg[len('proj~'):]
        target_proj = next(
            (p for p in projects if _safe_token(p['project_id']) == pid_token or p['project_id'] == pid_token),
            None,
        )
        if target_proj is None:
            return {'parent': clean_parent, 'matching_project_count': len(matching_ids), 'nodes': []}
        pid = target_proj['project_id']
        state = service.project_state(user_id, role_ids, pid)
        child_projects = [
            ch for ch in (children_map.get(pid) or [])
            if ch['project_id'] in matching_ids
        ]
        vnodes = build_project_virtual_tree(target_proj, state, child_projects)
        project_self_matches = (not q) or (
            q in f"{target_proj.get('name') or ''} {pid}".lower()
        )
        out_nodes: list[dict[str, Any]] = []
        for vnode in vnodes:
            if q and not project_self_matches:
                has_cp = any(
                    cp['project_id'] in matching_ids
                    for cp in (vnode.get('childProjects') or [])
                )
                has_items = any(
                    _item_matches_filter(it, q) for it in (vnode.get('items') or [])
                )
                has_sg = any(
                    any(_item_matches_filter(it, q) for it in (sg.get('items') or []))
                    for sg in (vnode.get('subgroups') or [])
                )
                if not (has_cp or has_items or has_sg):
                    continue
            out_nodes.append(
                _virtual_tree_node(target_proj, vnode, force_expand=bool(q))
            )
        return {
            'parent': clean_parent,
            'matching_project_count': len(matching_ids),
            'nodes': out_nodes,
        }

    # Case 2: Expanding a virtual folder or subgroup -> return child projects, subgroups, or leaf items
    if last_seg.startswith('virt~'):
        parts = last_seg.split('~')
        # Format: virt~<pid>~<vkey> or virt~<pid>~<vkey>~<subkey>
        if len(parts) >= 3:
            pid_token = parts[1]
            vkey = parts[2]
            subkey = parts[3] if len(parts) >= 4 else None
            target_proj = next(
                (p for p in projects if _safe_token(p['project_id']) == pid_token or p['project_id'] == pid_token),
                None,
            )
            if target_proj is None:
                return {'parent': clean_parent, 'matching_project_count': len(matching_ids), 'nodes': []}
            pid = target_proj['project_id']
            state = service.project_state(user_id, role_ids, pid)
            child_projects = [
                ch for ch in (children_map.get(pid) or [])
                if ch['project_id'] in matching_ids
            ]
            vnodes = build_project_virtual_tree(target_proj, state, child_projects)
            vnode = next((v for v in vnodes if v['key'] == vkey), None)
            if vnode is not None and subkey:
                vnode = next(
                    (sg for sg in (vnode.get('subgroups') or []) if sg['key'] == subkey),
                    None,
                )
            if vnode is None:
                return {'parent': clean_parent, 'matching_project_count': len(matching_ids), 'nodes': []}

            project_self_matches = (not q) or (
                q in f"{target_proj.get('name') or ''} {pid}".lower()
            )
            out_children: list[dict[str, Any]] = []
            for cp in vnode.get('childProjects') or []:
                if cp['project_id'] in matching_ids:
                    out_children.append(
                        _project_tree_node(
                            cp,
                            len([
                                ch for ch in (children_map.get(cp['project_id']) or [])
                                if ch['project_id'] in matching_ids
                            ]),
                            auto_expand=bool(q),
                        )
                    )
            for sg in vnode.get('subgroups') or []:
                if q and not project_self_matches:
                    if not any(_item_matches_filter(it, q) for it in (sg.get('items') or [])):
                        continue
                out_children.append(
                    _virtual_tree_node(target_proj, sg, force_expand=bool(q))
                )
            for item in vnode.get('items') or []:
                if not q or project_self_matches or _item_matches_filter(item, q):
                    out_children.append(_leaf_tree_node(item))

            return {
                'parent': clean_parent,
                'matching_project_count': len(matching_ids),
                'nodes': out_children,
            }

    return {'parent': clean_parent, 'matching_project_count': len(matching_ids), 'nodes': []}


def get_project_virtual_tree_payload(
    service: Any,
    user_id: int,
    role_ids: tuple[int, ...] = (),
    *,
    project_id: str,
) -> dict[str, Any]:
    projects = service.list_projects(user_id, role_ids)
    _roots, children_map, by_id = build_project_hierarchy(projects)
    state = service.project_state(user_id, role_ids, project_id)
    project = by_id.get(project_id) or {
        'project_id': state['project_id'],
        'parent_project_id': state.get('parent_project_id'),
        'name': state['name'],
        'description': state.get('description') or '',
        'revision': state.get('revision', 0),
        'access': state.get('access', 'viewer'),
    }
    parent_proj = (
        by_id.get(project['parent_project_id'])
        if project.get('parent_project_id')
        else None
    )
    child_projects = children_map.get(project_id) or []
    virtual_tree = build_project_virtual_tree(project, state, child_projects)
    return {
        'project': project,
        'parent_project': parent_proj,
        'child_projects': child_projects,
        'state': state,
        'virtual_tree': virtual_tree,
    }

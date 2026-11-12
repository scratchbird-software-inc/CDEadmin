##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Cross-design 'Where Used' impact explorer and checkpoint DDN diff."""

from __future__ import annotations

import difflib
import re
from typing import Any

from .service import DesignStore, DesignStoreError

_ELEMENT_DECL_RE = re.compile(
    r'^\s*(?:(?P<kw>element|view)\s+"(?P<qid>[^"]+)"\s+as\s+"(?P<qrole>[^"]+)"|'
    r'(?P<role>entity|table|dimension|measure|card|control|region|frame|node|cube|question|dashboard)\s+'
    r'(?P<ident>[A-Za-z0-9_.\-]+)(?:\s+"(?P<label>[^"]*)")?)',
    re.MULTILINE,
)
_TITLE_RE = re.compile(r'^\s*title\s+"([^"]*)"')


def _matches_needle(needle: str, *candidates: Any) -> bool:
    if not needle:
        return True
    norm_needle = needle.replace(':', '.').lower()
    for item in candidates:
        raw = str(item or '').lower()
        if needle in raw or norm_needle in raw.replace(':', '.'):
            return True
    return False


def _extract_ddn_elements(ddn_text: str) -> dict[str, dict[str, str]]:
    """Extract lightweight element descriptors from DDN text for version diffing."""
    found: dict[str, dict[str, str]] = {}
    lines = (ddn_text or '').splitlines()
    for idx, line in enumerate(lines):
        match = _ELEMENT_DECL_RE.match(line)
        if not match:
            continue
        base_indent = len(line) - len(line.lstrip(' '))
        if match.group('kw'):
            role = match.group('qrole')
            ident = match.group('qid')
            label = ''
        else:
            role = match.group('role')
            ident = match.group('ident')
            label = match.group('label') or ''

        block_lines = [line.strip()]
        j = idx + 1
        while j < len(lines):
            nxt = lines[j]
            stripped = nxt.strip()
            if stripped == '':
                j += 1
                continue
            indent = len(nxt) - len(nxt.lstrip(' '))
            if indent <= base_indent:
                break
            block_lines.append(stripped)
            if not label:
                tm = _TITLE_RE.match(nxt)
                if tm:
                    label = tm.group(1)
            j += 1

        found[f'{role}:{ident}'] = {
            'key': f'{role}:{ident}',
            'role': role,
            'id': ident,
            'label': label or ident,
            'signature': '\n'.join(block_lines),
        }
    return found


def diff_design_versions(
    store: DesignStore,
    design_id: str,
    base_version: int,
    target_version: int,
) -> dict[str, Any]:
    """Compute a structured and unified DDN diff between two design checkpoints."""
    if int(base_version) < 1 or int(target_version) < 1:
        raise DesignStoreError('Checkpoint versions must be >= 1.')
    base_doc = store.get_design(design_id, version=int(base_version))
    target_doc = store.get_design(design_id, version=int(target_version))
    base_ddn = str(base_doc['version']['ddn_text'] or '')
    target_ddn = str(target_doc['version']['ddn_text'] or '')

    diff_lines = list(
        difflib.unified_diff(
            base_ddn.splitlines(),
            target_ddn.splitlines(),
            fromfile=f"{base_doc['key']}@v{base_version} ({base_doc['version']['status']})",
            tofile=f"{target_doc['key']}@v{target_version} ({target_doc['version']['status']})",
            lineterm='',
        )
    )
    base_elems = _extract_ddn_elements(base_ddn)
    target_elems = _extract_ddn_elements(target_ddn)

    added: list[dict[str, str]] = []
    removed: list[dict[str, str]] = []
    modified: list[dict[str, str]] = []

    for key, elem in sorted(target_elems.items()):
        if key not in base_elems:
            added.append(
                {'key': key, 'role': elem['role'], 'id': elem['id'], 'label': elem['label']}
            )
        elif base_elems[key]['signature'] != elem['signature']:
            modified.append(
                {'key': key, 'role': elem['role'], 'id': elem['id'], 'label': elem['label']}
            )
    for key, elem in sorted(base_elems.items()):
        if key not in target_elems:
            removed.append(
                {'key': key, 'role': elem['role'], 'id': elem['id'], 'label': elem['label']}
            )

    return {
        'design_id': design_id,
        'base_version': int(base_version),
        'base_status': base_doc['version']['status'],
        'target_version': int(target_version),
        'target_status': target_doc['version']['status'],
        'identical': base_ddn == target_ddn,
        'unified_diff': '\n'.join(diff_lines) if diff_lines else '-- Identical DDN checkpoint text.',
        'added_elements': added,
        'modified_elements': modified,
        'removed_elements': removed,
    }


def query_cross_design_usage(
    store: DesignStore,
    project_id: str,
    *,
    target_ref: str | None = None,
    target_kind: str | None = None,
    design_id: str | None = None,
    include_suspect: bool = True,
) -> dict[str, Any]:
    """Return cross-design bindings, includes, and DDN references across all 4 designers."""
    needle = (target_ref or '').strip().lower()
    kind_filter = (target_kind or '').strip().lower()
    usages: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str, str]] = set()

    with store._lock:
        conn = store._connect()
        try:
            sql = """
                SELECT
                    b.id AS binding_id,
                    b.design_id AS design_id,
                    d.kind AS design_kind,
                    d.key AS design_key,
                    d.title AS design_title,
                    d.head_version AS head_version,
                    d.active_version AS active_version,
                    b.element_id AS element_id,
                    e.role AS element_role,
                    e.name AS element_label,
                    b.target_kind AS target_kind,
                    b.target_ref AS target_ref,
                    b.target_engine AS target_engine,
                    b.target_endpoint_id AS target_endpoint_id,
                    b.target_database_target_id AS target_database_target_id,
                    b.state AS validity,
                    b.state_reason AS state_reason
                FROM binding b
                JOIN design d ON d.id = b.design_id
                LEFT JOIN element e ON e.id = b.element_id AND e.design_id = b.design_id
                WHERE d.project_id = ?
            """
            params: list[Any] = [project_id]
            if not include_suspect:
                sql += " AND b.state = 'valid'"
            if kind_filter:
                sql += ' AND LOWER(b.target_kind) = ?'
                params.append(kind_filter)
            sql += ' ORDER BY d.kind, d.title, e.name'

            for row in conn.execute(sql, params).fetchall():
                t_ref = str(row['target_ref'] or '')
                elem_lbl = str(row['element_label'] or row['element_id'] or '')
                if not _matches_needle(
                    needle,
                    t_ref,
                    row['design_title'],
                    row['design_key'],
                    elem_lbl,
                ):
                    continue
                dedup = (str(row['design_id']), str(row['element_id']), t_ref)
                seen_keys.add(dedup)
                usages.append(
                    {
                        'binding_id': row['binding_id'],
                        'design_id': row['design_id'],
                        'design_kind': row['design_kind'],
                        'design_key': row['design_key'],
                        'design_title': row['design_title'],
                        'head_version': row['head_version'],
                        'active_version': row['active_version'],
                        'element_id': row['element_id'],
                        'element_role': row['element_role'] or 'element',
                        'element_label': elem_lbl,
                        'target_kind': row['target_kind'],
                        'target_ref': t_ref,
                        'target_engine': row['target_engine'],
                        'validity': row['validity'],
                        'state_reason': row['state_reason'],
                    }
                )

            dep_rows = conn.execute(
                """
                SELECT
                    dep.design_id AS consumer_id,
                    cd.kind AS consumer_kind,
                    cd.key AS consumer_key,
                    cd.title AS consumer_title,
                    dep.version AS consumer_version,
                    dep.depends_on_design_id AS target_design_id,
                    td.kind AS target_design_kind,
                    td.key AS target_design_key,
                    td.title AS target_design_title,
                    dep.depends_on_version AS pinned_version
                FROM design_dependency dep
                JOIN design cd ON cd.id = dep.design_id
                JOIN design td ON td.id = dep.depends_on_design_id
                WHERE cd.project_id = ?
                ORDER BY cd.kind, cd.title
                """,
                (project_id,),
            ).fetchall()
            for row in dep_rows:
                ref_label = (
                    f"{row['target_design_kind']}:{row['target_design_key']}"
                    f" ({row['target_design_id']})"
                )
                if design_id and row['target_design_id'] != design_id and row['consumer_id'] != design_id:
                    if needle and needle not in ref_label.lower():
                        continue
                elif needle and (
                    needle not in ref_label.lower()
                    and needle not in str(row['consumer_title'] or '').lower()
                    and needle not in str(row['target_design_title'] or '').lower()
                ):
                    continue
                dedup = (str(row['consumer_id']), f"include:v{row['consumer_version']}", ref_label)
                if dedup in seen_keys:
                    continue
                seen_keys.add(dedup)
                usages.append(
                    {
                        'binding_id': f"dep:{row['consumer_id']}:{row['target_design_id']}",
                        'design_id': row['consumer_id'],
                        'design_kind': row['consumer_kind'],
                        'design_key': row['consumer_key'],
                        'design_title': row['consumer_title'],
                        'element_id': f"v{row['consumer_version']}",
                        'element_role': 'include',
                        'element_label': (
                            f"v{row['consumer_version']} -> "
                            f"{'pinned v' + str(row['pinned_version']) if row['pinned_version'] else 'latest accepted'}"
                        ),
                        'target_kind': row['target_design_kind'],
                        'target_ref': ref_label,
                        'validity': 'valid',
                        'state_reason': None,
                    }
                )

            # Scan head DDN documents for cross-references (dashboard -> question_design_id,
            # question -> cube/table, screen -> table/column, erd -> table) not yet in binding rows
            doc_rows = conn.execute(
                """
                SELECT d.id, d.kind, d.key, d.title, d.head_version, d.active_version, v.ddn_text
                FROM design d
                JOIN design_version v ON v.design_id = d.id AND v.version = d.head_version
                WHERE d.project_id = ?
                ORDER BY d.kind, d.title
                """,
                (project_id,),
            ).fetchall()
            design_lookup = {str(r['id']): dict(r) for r in doc_rows}
            design_key_lookup = {str(r['key']): dict(r) for r in doc_rows}

            ref_patterns = (
                ('question', re.compile(r'question_design_id\s*[=:]?\s*"([^"]+)"')),
                ('cube', re.compile(r'cube(?:_id|_key|_ref)?\s*[=:]?\s*"([^"]+)"')),
                ('resource', re.compile(r'(?:source_table|fact_table|table_ref|resource_id|bind|target_ref)\s*[=:]?\s*"([^"]+)"')),
            )
            for row in doc_rows:
                ddn_text = str(row['ddn_text'] or '')
                for ref_kind, pattern in ref_patterns:
                    if kind_filter and kind_filter != ref_kind:
                        continue
                    for match in pattern.finditer(ddn_text):
                        raw_target = match.group(1).strip()
                        if not raw_target:
                            continue
                        resolved_target = raw_target
                        if raw_target in design_lookup:
                            td = design_lookup[raw_target]
                            resolved_target = f"{td['kind']}:{td['key']} ({raw_target})"
                        elif raw_target in design_key_lookup:
                            td = design_key_lookup[raw_target]
                            resolved_target = f"{td['kind']}:{td['key']} ({td['id']})"
                        if not _matches_needle(
                            needle,
                            resolved_target,
                            raw_target,
                            row['title'],
                        ):
                            continue
                        dedup = (str(row['id']), f'ddn:{ref_kind}', raw_target)
                        if dedup in seen_keys:
                            continue
                        seen_keys.add(dedup)
                        usages.append(
                            {
                                'binding_id': f"ddn:{row['id']}:{ref_kind}:{raw_target}",
                                'design_id': row['id'],
                                'design_kind': row['kind'],
                                'design_key': row['key'],
                                'design_title': row['title'],
                                'head_version': row['head_version'],
                                'active_version': row['active_version'],
                                'element_id': ref_kind,
                                'element_role': 'ddn_reference',
                                'element_label': f'DDN {ref_kind} reference',
                                'target_kind': ref_kind,
                                'target_ref': resolved_target,
                                'validity': 'valid',
                                'state_reason': None,
                            }
                        )
        finally:
            conn.close()

    by_kind: dict[str, int] = {}
    suspect_count = 0
    for item in usages:
        dk = str(item.get('design_kind') or 'design')
        by_kind[dk] = by_kind.get(dk, 0) + 1
        if item.get('validity') == 'suspect':
            suspect_count += 1

    return {
        'project_id': project_id,
        'filter_target_ref': target_ref or '',
        'total': len(usages),
        'suspect_count': suspect_count,
        'by_design_kind': by_kind,
        'usages': usages,
    }

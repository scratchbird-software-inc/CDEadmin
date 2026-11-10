##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""DDN text element/binding extraction, UUIDv7 identity assignment and
workspace bridging for the ScratchRobin design store.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from pgadmin.cdeadmin.workspace import ddn_source as ddn
from .identifiers import is_uuid7, uuid7

DEFAULT_DIALECT = ddn.CONTRACT
WORKSPACE_FORMAT = ddn.FORMAT

_VERSION_RE = re.compile(r'^\s*version\s+(\S+)\s*$', re.MULTILINE)
_HEADER_DECL_RE = re.compile(
    r'^(element|relation|view)\s+"((?:[^"\\]|"")*)"'
    r'(?:\s+as\s+"((?:[^"\\]|"")*)")?\s*$',
    re.MULTILINE,
)
_PROP_STR_RE = re.compile(r'^\s+(\w+)\s+"((?:[^"\\]|"")*)"\s*$')


def _unquote(raw: str) -> str:
    return raw.replace('""', '"')


def _quote_inner(value: str) -> str:
    return value.replace('"', '""')


def sha256_text(text: str) -> str:
    """Return hex SHA-256 of canonical UTF-8 DDN text."""
    if not isinstance(text, str):
        raise ValueError('DDN text must be a string')
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def parse_uid_scope(
    uid: str | None,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Extract (engine, endpoint_id, database_target_id, resource_id) from uid.

    Catalog and physical-schema uids use the format:
    ``<engine>:<endpoint_id>:<database_target_id>:<resource_id>``.
    """
    if not isinstance(uid, str) or uid.count(':') < 3:
        return None, None, None, None
    parts = uid.split(':', 3)
    if not all(parts):
        return None, None, None, None
    return parts[0], parts[1], parts[2], parts[3]


def _parse_blocks(ddn_text: str) -> list[dict[str, Any]]:
    """Parse top-level element, relation and view declarations from DDN."""
    matches = list(_HEADER_DECL_RE.finditer(ddn_text))
    blocks: list[dict[str, Any]] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = (
            matches[idx + 1].start()
            if idx + 1 < len(matches)
            else len(ddn_text)
        )
        body = ddn_text[match.end():end]
        kind = match.group(1)
        decl_id = _unquote(match.group(2))
        role = _unquote(match.group(3) or '') or kind
        props: dict[str, str] = {}
        for line in body.splitlines():
            prop_match = _PROP_STR_RE.match(line)
            if prop_match:
                key, val = prop_match.group(1), _unquote(prop_match.group(2))
                if key not in props:
                    props[key] = val
        blocks.append({
            'kind': kind,
            'id': decl_id,
            'role': role,
            'title': props.get('title') or decl_id,
            'props': props,
            'body': body,
            'span': (start, end),
        })
    return blocks


def _extract_x_record(block: dict[str, Any]) -> dict[str, Any] | None:
    """Extract metadata.x_record facts from a companion record element."""
    if block['kind'] != 'element' or block['role'] != 'record':
        return None
    body = block['body']
    if 'x_record' not in body:
        return None
    props: dict[str, str] = {}
    in_x_record = False
    x_record_indent = 0
    in_record = False
    record_indent = 0
    record_fields: dict[str, str] = {}
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        indent = len(line) - len(line.lstrip(' '))
        if stripped == 'x_record':
            in_x_record = True
            x_record_indent = indent
            in_record = False
            continue
        if not in_x_record:
            continue
        if indent <= x_record_indent:
            in_x_record = False
            in_record = False
            continue
        if in_record and indent <= record_indent:
            in_record = False
        if stripped == 'record':
            in_record = True
            record_indent = indent
            continue
        prop_match = _PROP_STR_RE.match(line)
        if prop_match:
            key = prop_match.group(1)
            val = _unquote(prop_match.group(2))
            if in_record:
                record_fields[key] = val
            else:
                props[key] = val
    if not props and not record_fields:
        return None
    return {
        'module': props.get('module'),
        'block': props.get('block'),
        'uid': props.get('uid'),
        'name_json': props.get('name_json'),
        'record': record_fields,
    }


def inspect_ddn_text(ddn_text: str) -> dict[str, Any]:
    """Inspect a DDN document and return dialect, views, elements, bindings."""
    if not isinstance(ddn_text, str) or not ddn_text.strip():
        raise ValueError('DDN text must be a non-empty string')
    ver_match = _VERSION_RE.search(ddn_text)
    dialect_version = ver_match.group(1) if ver_match else DEFAULT_DIALECT
    blocks = _parse_blocks(ddn_text)

    annotations_by_subject: dict[str, dict[str, Any]] = {}
    for block in blocks:
        x_rec = _extract_x_record(block)
        if x_rec is not None:
            subject_id = x_rec['record'].get('subject_id')
            if subject_id:
                annotations_by_subject[subject_id] = x_rec

    elements: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []
    views: list[dict[str, str]] = []

    for block in blocks:
        if block['kind'] == 'view':
            views.append({
                'id': block['id'],
                'profile': block['role'],
                'title': block['title'],
            })
            continue
        if _extract_x_record(block) is not None:
            continue

        decl_id = block['id']
        role = block['role']
        name = block['title']
        resource_id: str | None = None
        x_rec = annotations_by_subject.get(decl_id)
        if x_rec is not None:
            rec = x_rec['record']
            if x_rec.get('name_json'):
                try:
                    parsed_name = json.loads(x_rec['name_json'])
                    if isinstance(parsed_name, str) and parsed_name:
                        name = parsed_name
                except ValueError:
                    pass
            elif rec.get('field_title_json'):
                try:
                    parsed_title = json.loads(rec['field_title_json'])
                    if isinstance(parsed_title, str) and parsed_title:
                        name = parsed_title
                except ValueError:
                    pass
            elif rec.get('physical_name'):
                name = rec['physical_name']

            resource_id = rec.get('resource_id')
            uid = x_rec.get('uid')
            engine, endpoint_id, db_target_id, uid_res = parse_uid_scope(uid)
            if (
                not resource_id
                and uid_res
                and ':new:' not in uid_res
                and not uid_res.startswith('ddn-new-')
            ):
                resource_id = uid_res
            if resource_id:
                bindings.append({
                    'element_id': decl_id,
                    'target_kind': 'resource',
                    'target_ref': resource_id,
                    'target_engine': engine,
                    'target_endpoint_id': endpoint_id,
                    'target_database_target_id': db_target_id,
                    'resource_kind': rec.get('native_kind') or role,
                    'uid': uid,
                })
            elif rec.get('target_ref') and rec.get('target_kind'):
                bindings.append({
                    'element_id': decl_id,
                    'target_kind': rec['target_kind'],
                    'target_ref': rec['target_ref'],
                    'target_engine': rec.get('target_engine') or engine,
                    'target_endpoint_id': (
                        rec.get('target_endpoint_id') or endpoint_id
                    ),
                    'target_database_target_id': (
                        rec.get('target_database_target_id') or db_target_id
                    ),
                    'resource_kind': role,
                    'uid': uid,
                })

        props = block['props']
        if 'target_ref' in props and 'target_kind' in props:
            bindings.append({
                'element_id': decl_id,
                'target_kind': props['target_kind'],
                'target_ref': props['target_ref'],
                'target_engine': props.get('target_engine'),
                'target_endpoint_id': props.get('target_endpoint_id'),
                'target_database_target_id': props.get(
                    'target_database_target_id'
                ),
                'resource_kind': role,
                'uid': None,
            })

        elements.append({
            'id': decl_id,
            'kind': block['kind'],
            'role': role,
            'name': name,
            'has_annotation': x_rec is not None,
            'resource_id': resource_id,
            'uid': x_rec.get('uid') if x_rec else None,
        })

    return {
        'dialect_version': dialect_version,
        'views': views,
        'elements': elements,
        'bindings': bindings,
    }


def assign_uuid7_element_ids(
    ddn_text: str,
    *,
    existing_by_id: dict[str, dict[str, Any]] | None = None,
    existing_by_resource: dict[str, str] | None = None,
    name_mapping: dict[str, str] | None = None,
) -> tuple[str, dict[str, str], dict[str, Any]]:
    """Ensure every design element in ``ddn_text`` has a UUIDv7 ``id``.

    Matching order (DESIGN-STORE-PROPOSAL.md section 2 & 5):
    1. If the element already has a valid UUIDv7 ``id``, keep it.
    2. If ``name_mapping`` maps the legacy id or ``(role, name)``/``name``
       to a UUIDv7, use that UUIDv7.
    3. If ``existing_by_resource`` maps the element's ``resource_id`` or
       ``uid`` to an existing element UUIDv7 in this design, use it.
    4. Otherwise allocate a fresh UUIDv7 and rewrite references in the
       DDN text so exported DDN always carries the portable UUIDv7 ``id``.
    """
    existing_by_id = existing_by_id or {}
    existing_by_resource = existing_by_resource or {}
    name_mapping = name_mapping or {}

    info = inspect_ddn_text(ddn_text)
    id_map: dict[str, str] = {}
    used_ids: set[str] = set()

    for elem in info['elements']:
        old_id = elem['id']
        role = elem['role']
        name = elem['name']
        res_id = elem.get('resource_id')
        uid = elem.get('uid')

        chosen: str | None = None
        if is_uuid7(old_id) and old_id not in used_ids:
            chosen = old_id
        elif old_id in name_mapping and is_uuid7(name_mapping[old_id]):
            chosen = name_mapping[old_id]
        elif (
            f'{role}:{name}' in name_mapping
            and is_uuid7(name_mapping[f'{role}:{name}'])
        ):
            chosen = name_mapping[f'{role}:{name}']
        elif name in name_mapping and is_uuid7(name_mapping[name]):
            chosen = name_mapping[name]
        elif res_id and res_id in existing_by_resource:
            candidate = existing_by_resource[res_id]
            if is_uuid7(candidate) and candidate not in used_ids:
                chosen = candidate
        elif uid and uid in existing_by_resource:
            candidate = existing_by_resource[uid]
            if is_uuid7(candidate) and candidate not in used_ids:
                chosen = candidate
        elif old_id in existing_by_id and is_uuid7(old_id):
            chosen = old_id

        if chosen is None or chosen in used_ids:
            chosen = uuid7()
        used_ids.add(chosen)
        if chosen != old_id:
            id_map[old_id] = chosen

    rewritten = _rewrite_ddn_ids(ddn_text, id_map) if id_map else ddn_text
    updated_info = inspect_ddn_text(rewritten)
    return rewritten, id_map, updated_info


def _rewrite_ddn_ids(ddn_text: str, id_map: dict[str, str]) -> str:
    """Rewrite non-UUIDv7 declaration IDs and internal references in DDN."""
    result = ddn_text
    for old_id, new_id in sorted(
        id_map.items(), key=lambda item: len(item[0]), reverse=True
    ):
        q_old = _quote_inner(old_id)
        q_new = _quote_inner(new_id)
        result = re.sub(
            rf'^(element|relation)\s+"{re.escape(q_old)}"',
            rf'\g<1> "{q_new}"',
            result,
            flags=re.MULTILINE,
        )
        result = re.sub(
            rf'^element\s+"relations\.mapping_{re.escape(q_old)}"',
            f'element "relations.mapping_{q_new}"',
            result,
            flags=re.MULTILINE,
        )
        result = re.sub(
            rf'^(\s+id\s+)"relations\.mapping_{re.escape(q_old)}"\s*$',
            rf'\g<1>"relations.mapping_{q_new}"',
            result,
            flags=re.MULTILINE,
        )
        result = re.sub(
            rf'^(\s+(?:id|subject_id|parent_id)\s+)"{re.escape(q_old)}"\s*$',
            rf'\g<1>"{q_new}"',
            result,
            flags=re.MULTILINE,
        )
        result = re.sub(
            rf'^(\s+"?{re.escape(old_id)}"?\s+)("[0-9]+")\s*$',
            rf'                "{q_new}" \g<2>',
            result,
            flags=re.MULTILINE,
        )
        result = re.sub(
            rf'^(\s+use\s+)"{re.escape(q_old)}"'
            rf'(\s+named\s+"appearance:[^":]+:){re.escape(q_old)}"\s*$',
            rf'\g<1>"{q_new}"\g<2>{q_new}"',
            result,
            flags=re.MULTILINE,
        )
    return result


def ddn_text_to_workspace(
    ddn_text: str,
    *,
    entry: str = 'design.ddn',
    view: str | None = None,
) -> dict[str, Any]:
    """Wrap a single-file DDN text document in ``ddn-source-workspace@1``."""
    info = inspect_ddn_text(ddn_text)
    selected_view = view
    if not selected_view:
        selected_view = (
            info['views'][0]['id'] if info['views'] else 'main'
        )
    if not info['views']:
        elem_refs = [ddn.ref(item['id']) for item in info['elements']]
        ddn_text = (
            ddn_text.rstrip()
            + '\n\n'
            + ddn.declaration(
                'view',
                selected_view,
                'ddn@1',
                {
                    'title': 'Design',
                    'selection': {'include': elem_refs},
                },
            )
        )
    ws = ddn.workspace({entry: ddn_text}, entry, selected_view)
    ddn.validate_workspace(ws)
    return ws


def workspace_to_ddn_text(
    ddn_or_workspace: str | dict[str, Any],
) -> tuple[str, str, str]:
    """Extract (ddn_text, entry_file, view_id) from text or workspace dict."""
    if isinstance(ddn_or_workspace, str):
        info = inspect_ddn_text(ddn_or_workspace)
        view_id = info['views'][0]['id'] if info['views'] else 'main'
        return ddn_or_workspace, 'design.ddn', view_id
    if isinstance(ddn_or_workspace, dict):
        ddn.validate_workspace(ddn_or_workspace)
        entry = ddn_or_workspace['entry']
        view_id = ddn_or_workspace['view']
        files = ddn_or_workspace['files']
        if len(files) == 1:
            return files[entry], entry, view_id
        parts = [files[entry]]
        for name, content in sorted(files.items()):
            if name == entry:
                continue
            parts.append(
                f'// --- included file: {name} ---\n' + content
            )
        combined = '\n'.join(parts)
        return combined, entry, view_id
    raise ValueError('Expected DDN source string or ddn-source-workspace@1')

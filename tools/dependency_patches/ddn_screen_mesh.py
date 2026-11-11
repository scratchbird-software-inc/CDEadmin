"""Reviewed consumer patch, applied only to an isolated standalone DDN capture.

Expands `wireframe.ui@1` in ScratchRobin's consumed DDN capture so the Screen
Mesh designer can express wireframe controls beyond the baseline seven-control
stencil (`ui.grid` with named columns, `ui.dropdown`, `ui.radio`, `ui.tabs`),
first-class rectangular image hotspot regions (`ui.region`), data/resource
bindings (`binds` / `bindfield` to context `table`, `field`, `record`,
`saved_view`, `dashboard`, `binding`), and bounded non-executable
screen-to-screen `navigation` relations (`control` or `ui.region` ->
`ui.frame`). Working form builders and executable UI scripts remain outside
scope. See ddn-screen-mesh.md; the public DDN checkout is never modified.
"""
import copy
import json
from pathlib import Path

CONTRACTS = 'standard/codex'
PROFILE_ID = 'wireframe.ui@1'

NEW_UI_ROLES = {
    'ui.dropdown': {
        'code': 'UI_DROPDOWN',
        'label': 'Wireframe dropdown',
    },
    'ui.grid': {
        'code': 'UI_GRID',
        'label': 'Wireframe grid',
    },
    'ui.radio': {
        'code': 'UI_RADIO',
        'label': 'Wireframe radio',
    },
    'ui.region': {
        'code': 'UI_REGION',
        'label': 'Wireframe image region',
    },
    'ui.tabs': {
        'code': 'UI_TABS',
        'label': 'Wireframe tabs',
    },
}

ALL_UI_ROLES = sorted([
    'ui.button',
    'ui.checkbox',
    'ui.dropdown',
    'ui.frame',
    'ui.grid',
    'ui.image',
    'ui.input',
    'ui.label',
    'ui.list',
    'ui.radio',
    'ui.region',
    'ui.tabs',
])

CONTEXT_ROLES = [
    'binding',
    'dashboard',
    'field',
    'record',
    'saved_view',
    'table',
]

RELATION_ROLES = [
    'assoc',
    'bindfield',
    'binds',
    'navigation',
]


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(
            f'DDN screen mesh consumer patch anchor changed ({label}): '
            f'{old[:72]}'
        )
    return text.replace(old, new)


def _extra_x_ui_object_props() -> dict:
    return {
        'checked': {'$ref': '#/$defs/bool'},
        'placeholder': {'$ref': '#/$defs/text'},
        'asset_sha256': {'$ref': '#/$defs/text'},
        'form_reference': {'$ref': '#/$defs/text'},
        'access_mode': {
            'type': 'string',
            'enum': ['read', 'write', 'read_write'],
        },
        'bounds': {'$ref': '#/$defs/rect'},
        'options': {
            'type': 'array',
            'items': {'$ref': '#/$defs/text'},
            'minItems': 0,
            'maxItems': 256,
        },
        'columns': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'id': {'$ref': '#/$defs/id'},
                    'name': {'$ref': '#/$defs/text'},
                    'width': {'$ref': '#/$defs/number'},
                    'datatype': {'$ref': '#/$defs/text'},
                    'binding_id': {'$ref': '#/$defs/text'},
                },
                'additionalProperties': False,
            },
            'minItems': 0,
            'maxItems': 256,
        },
    }


def _extra_x_ui_relation_props() -> dict:
    return {
        'trigger': {
            'type': 'string',
            'enum': ['click', 'hover', 'delay'],
        },
        'action': {
            'type': 'string',
            'enum': ['navigate', 'back', 'overlay', 'url'],
        },
        'delay_ms': {'$ref': '#/$defs/nonnegative'},
        'url': {'$ref': '#/$defs/text'},
    }


def apply(root):
    root = Path(root)
    codex = root / CONTRACTS

    # 1. Core element & relation contracts
    core_path = codex / 'core-contracts.json'
    core = json.loads(core_path.read_text())
    el16_roles = core['EL16']['retained_roles']
    for role_name in NEW_UI_ROLES:
        if role_name not in el16_roles:
            el16_roles.append(role_name)
    core_path.write_text(
        json.dumps(core, indent=2, ensure_ascii=False) + '\n'
    )

    rel_core_path = codex / 'relation-contracts.json'
    rel_core = json.loads(rel_core_path.read_text())
    rl25_roles = rel_core['RL25']['retained_roles']
    if 'navigation' not in rl25_roles:
        rl25_roles.append('navigation')
    rel_core_path.write_text(
        json.dumps(rel_core, indent=2, ensure_ascii=False) + '\n'
    )

    # 2. Role contracts
    roles_path = codex / 'role-contracts.json'
    roles = json.loads(roles_path.read_text())
    if 'ui.grid' in roles or 'relation::navigation' in roles:
        raise RuntimeError(
            'Screen mesh roles already exist in DDN role-contracts.json'
        )
    base_ui = roles['ui.input']
    for role_name, meta in NEW_UI_ROLES.items():
        entry = copy.deepcopy(base_ui)
        entry['role'] = role_name
        entry['schema'] = f'kind_{role_name}'
        entry['data_properties'] = f'data_properties_kind_{role_name}'
        entry['contract']['id'] = f'profile-kind.{role_name}'
        entry['contract']['code'] = meta['code']
        entry['contract']['name'] = meta['label']
        entry['contract']['text_label'] = meta['label']
        entry['contract']['keyword'] = role_name
        entry['standard']['text_label'] = meta['label']
        entry['profiles'] = ['ddn@1', PROFILE_ID]
        roles[role_name] = entry

    nav_entry = copy.deepcopy(roles['relation::flow.next'])
    nav_entry['role'] = 'navigation'
    nav_entry['schema'] = 'relation_navigation'
    nav_entry['data_properties'] = 'data_properties_relation_navigation'
    nav_entry['contract']['id'] = 'profile-relation.navigation'
    nav_entry['contract']['code'] = 'REL_NAVIGATION'
    nav_entry['contract']['name'] = 'Screen navigation'
    nav_entry['contract']['text_label'] = 'navigates'
    nav_entry['contract']['keyword'] = 'navigation'
    nav_entry['contract']['colour'] = '#0284C7'
    nav_entry['standard']['text_label'] = 'navigates'
    nav_entry['standard']['colour'] = '#0284C7'
    nav_entry['profiles'] = ['ddn@1', PROFILE_ID]
    roles['relation::navigation'] = nav_entry

    for ctx_role in CONTEXT_ROLES:
        entry = roles.get(ctx_role)
        if entry and PROFILE_ID not in entry.get('profiles', []):
            entry['profiles'].append(PROFILE_ID)
    for rel_key in ('relation::binds', 'relation::bindfield'):
        entry = roles.get(rel_key)
        if entry and PROFILE_ID not in entry.get('profiles', []):
            entry['profiles'].append(PROFILE_ID)
    roles_path.write_text(
        json.dumps(roles, indent=2, ensure_ascii=False) + '\n'
    )

    # 3. Property codex render entries for new roles
    prop_path = codex / 'property-codex.json'
    prop_codex = json.loads(prop_path.read_text())
    prop_list = prop_codex['properties']
    ui_template_props = [
        p for p in prop_list if p.get('owner') == 'role:ui.input'
    ]
    nav_template_props = [
        p for p in prop_list if p.get('owner') == 'role:relation::flow.next'
    ]
    if not ui_template_props or not nav_template_props:
        raise RuntimeError('Missing role template properties in codex')

    for role_name, meta in NEW_UI_ROLES.items():
        tag = meta['code']
        for idx, tmpl in enumerate(ui_template_props, start=1):
            cloned = copy.deepcopy(tmpl)
            cloned['id'] = f'PSR_{tag}_{idx:02d}'
            cloned['owner'] = f'role:{role_name}'
            cloned['provenance'] = [
                f'consumer_patch:role-registry/{role_name}'
            ]
            if cloned['path'] == 'render.text_label':
                cloned['default']['value'] = meta['label']
            prop_list.append(cloned)

    for idx, tmpl in enumerate(nav_template_props, start=1):
        cloned = copy.deepcopy(tmpl)
        cloned['id'] = f'PSR_REL_NAV_{idx:02d}'
        cloned['owner'] = 'role:relation::navigation'
        cloned['provenance'] = ['consumer_patch:role-registry/navigation']
        if cloned['path'] == 'render.text_label':
            cloned['default']['value'] = 'navigates'
        elif cloned['path'] == 'render.colour':
            cloned['default']['value'] = '#0284C7'
        prop_list.append(cloned)

    prop_path.write_text(
        json.dumps(prop_codex, indent=2, ensure_ascii=False) + '\n'
    )

    # 4. Schema updates
    schema_path = codex / 'ddn.schema.json'
    schema = json.loads(schema_path.read_text())
    defs = schema['$defs']

    for def_key in ('meta_x_ui_object', 'partial_meta_x_ui_object'):
        defs[def_key]['properties'].update(_extra_x_ui_object_props())
    for def_key in ('meta_x_ui_relation', 'partial_meta_x_ui_relation'):
        defs[def_key]['properties'].update(_extra_x_ui_relation_props())

    defn = defs['definition']
    role_enum = defn['properties']['role']['enum']
    el_data_enum = defs['data_property_4']['enum']
    rel_data_enum = defs['data_property_35']['enum']
    tail_branch = defn['allOf'][-1]
    tail_el_enum = tail_branch['else']['properties']['role']['enum']
    tail_rel_enum = tail_branch['then']['properties']['role']['enum']

    new_branches = []
    for role_name in NEW_UI_ROLES:
        for prefix in (
            'metadata_kind_',
            'metadata_partial_kind_',
            'data_properties_kind_',
            'kind_',
        ):
            defs[f'{prefix}{role_name}'] = copy.deepcopy(
                defs[f'{prefix}ui.input']
            )
        for target_enum in (role_enum, el_data_enum, tail_el_enum):
            if role_name not in target_enum:
                target_enum.append(role_name)
        new_branches.append({
            'if': {
                'properties': {
                    'role': {'const': role_name},
                    'category': {'const': 'element'},
                },
                'required': ['role'],
            },
            'then': {
                'properties': {
                    'content': {'$ref': '#/$defs/content_EL16'},
                    'metadata': {
                        '$ref': f'#/$defs/metadata_partial_kind_{role_name}',
                    },
                    'properties': {
                        '$ref': f'#/$defs/data_properties_kind_{role_name}',
                    },
                    'qualifiers': {
                        'type': 'object',
                        'properties': {},
                        'required': [],
                        'additionalProperties': False,
                    },
                },
            },
        })

    for prefix, src_key in (
        ('metadata_relation_navigation', 'metadata_relation_flow.next'),
        (
            'metadata_partial_relation_navigation',
            'metadata_partial_relation_flow.next',
        ),
        (
            'data_properties_relation_navigation',
            'data_properties_relation_flow.next',
        ),
        ('relation_navigation', 'relation_flow.next'),
    ):
        defs[prefix] = copy.deepcopy(defs[src_key])
    for target_enum in (role_enum, rel_data_enum, tail_rel_enum):
        if 'navigation' not in target_enum:
            target_enum.append('navigation')
    new_branches.append({
        'if': {
            'properties': {
                'role': {'const': 'navigation'},
                'category': {'const': 'relation'},
            },
            'required': ['role', 'category'],
        },
        'then': {
            'properties': {
                'content': {
                    'type': 'object',
                    'properties': {},
                    'required': [],
                    'additionalProperties': False,
                },
                'metadata': {
                    '$ref': '#/$defs/metadata_partial_relation_navigation',
                },
                'properties': {
                    '$ref': '#/$defs/data_properties_relation_navigation',
                },
                'qualifiers': {'$ref': '#/$defs/qualifiers_RL25'},
            },
        },
    })
    defn['allOf'] = [*defn['allOf'][:-1], *new_branches, tail_branch]
    schema_path.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + '\n'
    )

    # 5. Profile contracts (wireframe.ui@1 and ddn@1 superset)
    profiles_path = codex / 'profile-contracts.json'
    profiles = json.loads(profiles_path.read_text())
    wf = profiles[PROFILE_ID]
    ddn1 = profiles['ddn@1']

    all_wf_elements = sorted(set(ALL_UI_ROLES) | set(CONTEXT_ROLES))
    wf['scope'] = (
        'Screen mesh wireframes, screenshot hotspot regions, data/resource '
        'bindings and bounded non-executable screen-to-screen navigation.'
    )
    wf['primary_palette'] = list(ALL_UI_ROLES)
    wf['context_roles'] = list(CONTEXT_ROLES)
    wf['relation_roles'] = list(RELATION_ROLES)
    wf['relation_endpoint_contracts'] = [
        {
            'profile': PROFILE_ID,
            'role': 'assoc',
            'source_roles': list(ALL_UI_ROLES),
            'target_roles': list(ALL_UI_ROLES),
            'source_selectors': ['*'],
            'target_selectors': ['*'],
            'member_endpoints': True,
            'self_allowed': True,
            'canonical_pattern': 'RL17',
            'canonical_direction': 'same',
            'further_restrictions': (
                'Profile semantic rules and member/metadata-owner checks '
                'apply after registry checks.'
            ),
        },
        {
            'profile': PROFILE_ID,
            'role': 'bindfield',
            'source_roles': sorted(set(ALL_UI_ROLES) | {'binding', 'field'}),
            'target_roles': list(CONTEXT_ROLES),
            'source_selectors': ['*'],
            'target_selectors': ['*'],
            'member_endpoints': True,
            'self_allowed': False,
            'canonical_pattern': 'RL83',
            'canonical_direction': 'same',
            'further_restrictions': (
                'Control, grid column or hotspot region field binding.'
            ),
        },
        {
            'profile': PROFILE_ID,
            'role': 'binds',
            'source_roles': sorted(set(ALL_UI_ROLES) | {'binding'}),
            'target_roles': list(CONTEXT_ROLES),
            'source_selectors': ['*'],
            'target_selectors': ['*'],
            'member_endpoints': True,
            'self_allowed': False,
            'canonical_pattern': 'RL75',
            'canonical_direction': 'reverse',
            'further_restrictions': (
                'Control or hotspot region resource binding.'
            ),
        },
        {
            'profile': PROFILE_ID,
            'role': 'navigation',
            'source_roles': list(ALL_UI_ROLES),
            'target_roles': ['ui.frame'],
            'source_selectors': ['*'],
            'target_selectors': ['*'],
            'member_endpoints': True,
            'self_allowed': True,
            'canonical_pattern': 'RL25',
            'canonical_direction': 'same',
            'further_restrictions': (
                'Bounded non-executable screen-to-screen navigation link.'
            ),
        },
    ]
    wf['element_bindings'] = {
        r: roles[r]['core'] for r in all_wf_elements
    }
    wf['relation_bindings'] = {
        'assoc': {'pattern': 'RL17', 'direction': 'same'},
        'bindfield': {'pattern': 'RL83', 'direction': 'same'},
        'binds': {'pattern': 'RL75', 'direction': 'reverse'},
        'navigation': {'pattern': 'RL25', 'direction': 'same'},
    }
    wf['element_footprint'] = sorted({
        roles[r]['core'] for r in all_wf_elements
    })
    wf['relation_footprint'] = ['RL17', 'RL25', 'RL75', 'RL83']
    wf['element_contracts'] = {r: f'kind_{r}' for r in all_wf_elements}
    wf['relation_contracts'] = {
        r: f'relation_{r}' for r in RELATION_ROLES
    }
    wf['profile_rules'] = [
        'Use the twelve bounded UI roles plus optional bound catalog/BI '
        'context nodes; UI controls outside any ui.frame produce a warning.',
        'Support rectangular screenshot regions (ui.region), data bindings '
        '(binds/bindfield) and bounded non-executable screen-to-screen '
        'navigation; working form execution remains out of scope.',
    ]

    for role_name in NEW_UI_ROLES:
        if role_name not in ddn1['context_roles']:
            ddn1['context_roles'].append(role_name)
        ddn1['element_bindings'][role_name] = 'EL16'
        ddn1['element_contracts'][role_name] = f'kind_{role_name}'
    ddn1['context_roles'].sort()
    if 'navigation' not in ddn1['relation_roles']:
        ddn1['relation_roles'].append('navigation')
        ddn1['relation_roles'].sort()
    ddn1['relation_bindings']['navigation'] = {
        'pattern': 'RL25',
        'direction': 'same',
    }
    ddn1['relation_contracts']['navigation'] = 'relation_navigation'
    ddn1['relation_endpoint_contracts'].append({
        'profile': 'ddn@1',
        'role': 'navigation',
        'source_roles': list(ALL_UI_ROLES),
        'target_roles': ['ui.frame'],
        'source_selectors': ['*'],
        'target_selectors': ['*'],
        'member_endpoints': True,
        'self_allowed': True,
        'canonical_pattern': 'RL25',
        'canonical_direction': 'same',
        'further_restrictions': (
            'Bounded non-executable screen-to-screen navigation link.'
        ),
    })

    profiles_path.write_text(
        json.dumps(profiles, indent=2, ensure_ascii=False) + '\n'
    )

    # 6. Semantic rule update so context nodes do not trigger DDN-UI-FRAME
    sem_path = root / 'project/ddn/packages/profiles/src/semantic.ts'
    sem_text = sem_path.read_text()
    sem_text = _replace_once(
        sem_text,
        "if (profileId === 'wireframe.ui@1') "
        "for (const n of nodes.filter(n => role(n) !== 'ui.frame'))",
        "if (profileId === 'wireframe.ui@1') "
        "for (const n of nodes.filter("
        "n => role(n).startsWith('ui.') && role(n) !== 'ui.frame'))",
        'semantic.ts wireframe frame check',
    )
    sem_path.write_text(sem_text)

    # 7. Crisp vector glyphs for ui.radio, ui.dropdown, ui.tabs, ui.grid,
    #    and ui.region in shared presentation library
    glyphs_path = (
        root / 'project/ddn/packages/presentation/src/graph-glyphs.ts'
    )
    glyphs_text = glyphs_path.read_text()
    glyphs_text = _replace_once(
        glyphs_text,
        "    else if (role === 'ui.image') {\n"
        "        ps.push(box(b, '#f1f5f9', '#64748b'), "
        "line([x, y], [x + w, y + h], '#94a3b8'), "
        "line([x + w, y], [x, y + h], '#94a3b8'));\n"
        "    }",
        "    else if (role === 'ui.image') {\n"
        "        ps.push(box(b, '#f1f5f9', '#64748b'), "
        "line([x, y], [x + w, y + h], '#94a3b8'), "
        "line([x + w, y], [x, y + h], '#94a3b8'));\n"
        "    }\n"
        "    else if (role === 'ui.radio') {\n"
        "        ps.push(oval({ x, y: cy - 10, width: 20, height: 20 }, "
        "'#fff', '#64748b'));\n"
        "        if (m('x_ui').checked)\n"
        "            ps.push(oval({ x: x + 5, y: cy - 5, width: 10, "
        "height: 10 }, '#334155', '#334155'));\n"
        "        ps.push(label(options.title, x + 28, cy + 5));\n"
        "        title = false;\n"
        "    }\n"
        "    else if (role === 'ui.dropdown') {\n"
        "        ps.push(box(b, '#fff', '#64748b'), "
        "path(`M${x + w - 22},${cy - 4}L${x + w - 16},${cy + 3}"
        "L${x + w - 10},${cy - 4}`, 'none', '#475569', 2), "
        "label(options.title, x + 10, cy + 5));\n"
        "        title = false;\n"
        "    }\n"
        "    else if (role === 'ui.tabs') {\n"
        "        const opts = array(m('x_ui').options).map(String);\n"
        "        const tabs = opts.length ? opts.slice(0, 5) : "
        "[options.title || 'Tab 1', 'Tab 2'];\n"
        "        const tw = Math.min(\n"
        "            110, Math.max(48, (w - 8) / tabs.length)\n"
        "        );\n"
        "        ps.push(box({ x, y: y + 22, width: w, "
        "height: Math.max(18, h - 22) }, '#fff', '#64748b'));\n"
        "        tabs.forEach((t, i) => ps.push("
        "box({ x: x + i * tw, y, width: tw - 2, height: 22 }, "
        "i === 0 ? '#fff' : '#e2e8f0', '#64748b'), "
        "label(t, x + i * tw + 8, y + 15, 11, '#334155')));\n"
        "        title = false;\n"
        "    }\n"
        "    else if (role === 'ui.grid') {\n"
        "        const cols = array(m('x_ui').columns);\n"
        "        const nCols = Math.max(2, Math.min(6, cols.length || 3));\n"
        "        ps.push(box(b, '#fff', '#64748b'), "
        "box({ x, y, width: w, height: 24 }, '#f1f5f9', '#64748b'));\n"
        "        for (let i = 1; i < nCols; i++)\n"
        "            ps.push(line([x + (w * i) / nCols, y], "
        "[x + (w * i) / nCols, y + h], '#cbd5e1', 1));\n"
        "        for (let r = 1; r <= 2; r++)\n"
        "            ps.push(line([x, y + 24 + r * 20], "
        "[x + w, y + 24 + r * 20], '#e2e8f0', 1));\n"
        "    }\n"
        "    else if (role === 'ui.region') {\n"
        "        ps.push(box(b, 'none', '#0284c7', 2, '6 3'));\n"
        "    }",
        'graph-glyphs.ts wireframe controls',
    )
    glyphs_path.write_text(glyphs_text)

    # 8. Adjust native standalone HTML viewer budget in isolated capture to
    #    accommodate expanded role/schema tables from consumer dialect patches
    dist_path = root / 'tooling/workspace/ddn-distribution.mjs'
    dist_text = _replace_once(
        dist_path.read_text(),
        "['ddn-viewer', 'viewer-entry', 'viewer', "
        "2 * 1024 * 1024, 250 * 1024],",
        "['ddn-viewer', 'viewer-entry', 'viewer', "
        "2 * 1024 * 1024, 264 * 1024],",
        'ddn-distribution.mjs native viewer gzip budget',
    )
    dist_path.write_text(dist_text)

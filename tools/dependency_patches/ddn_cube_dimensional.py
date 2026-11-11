"""Reviewed consumer patch, applied only to an isolated standalone DDN capture.

Adds the `cube.dimensional@1` dimensional/semantic-model profile to
ScratchRobin's consumed DDN capture so cube star/constellation diagrams use the
full dimensional element and relation vocabulary alongside `matrix.relations@1`
and `table.records@1`. See ddn-cube-dimensional.md; the public DDN checkout is
never modified.
"""
import copy
import json
from pathlib import Path

CONTRACTS = 'standard/codex'
PROFILE_ID = 'cube.dimensional@1'
PRIMARY_PALETTE = [
    'aggregate',
    'binding',
    'bridge',
    'cube',
    'dimension',
    'fact',
    'field',
    'materialized_view',
    'metric',
    'semantic_model',
]
RELATION_ROLES = [
    'aggregates',
    'assoc',
    'bindfield',
    'binds',
    'derives',
    'filters',
    'joins',
    'lookup',
    'owns',
    'part',
    'ref',
    'uses',
]


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(
            f'DDN dimensional consumer patch anchor changed ({label}): '
            f'{old[:72]}'
        )
    return text.replace(old, new)


def apply(root):
    root = Path(root)
    codex = root / CONTRACTS

    profiles_path = codex / 'profile-contracts.json'
    profiles = json.loads(profiles_path.read_text())
    if PROFILE_ID in profiles:
        raise RuntimeError(f'{PROFILE_ID} already exists in DDN contracts')
    erd = copy.deepcopy(profiles['erd.crowfoot@1'])
    ddn1 = profiles['ddn@1']
    all_roles = sorted(
        set(erd['primary_palette']) | set(erd['context_roles'])
    )
    context_roles = [r for r in all_roles if r not in PRIMARY_PALETTE]
    endpoint_contracts = []
    for rel_role in RELATION_ROLES:
        found = next(
            (
                copy.deepcopy(item)
                for item in ddn1['relation_endpoint_contracts']
                if item['role'] == rel_role
            ),
            None,
        )
        if found is None:
            raise RuntimeError(
                f'Missing relation endpoint contract in ddn@1: {rel_role}'
            )
        found['profile'] = PROFILE_ID
        endpoint_contracts.append(found)

    cube_profile = copy.deepcopy(erd)
    cube_profile.update({
        'id': PROFILE_ID,
        'scope': (
            'Dimensional cube and semantic-model star/constellation graph '
            'with measure groups, dimension entities, role-playing '
            'dimensions, filtered measures and aggregation rules.'
        ),
        'diagram_families': ['Dimensional cube'],
        'primary_palette': PRIMARY_PALETTE,
        'context_roles': context_roles,
        'relation_roles': RELATION_ROLES,
        'relation_endpoint_contracts': endpoint_contracts,
        'standard_overrides': {
            **copy.deepcopy(erd.get('standard_overrides', {})),
            'projection.profile': PROFILE_ID,
        },
        'projection_schema': f'profile_{PROFILE_ID}',
        'profile_rules': [
            'ScratchRobin reviewed dimensional-cube profile extension: '
            'renders cube, fact/measure-group, dimension, bridge, metric '
            'and aggregate elements with inline column/attribute '
            'compartments and explicit join/usage/aggregation relations.',
            'Works alongside matrix.relations@1 (dimension usage matrix) '
            'and table.records@1 (aggregation grid) over shared element IDs.',
        ],
        'element_contracts': {
            role: f'kind_{role}' for role in sorted(
                set(PRIMARY_PALETTE) | set(context_roles)
            )
        },
        'relation_contracts': {
            role: f'relation_{role}' for role in RELATION_ROLES
        },
    })
    profiles[PROFILE_ID] = cube_profile
    profiles_path.write_text(
        json.dumps(profiles, indent=2, ensure_ascii=False) + '\n'
    )

    schema_path = codex / 'ddn.schema.json'
    schema = json.loads(schema_path.read_text())
    defs = schema['$defs']
    defs[f'profile_{PROFILE_ID}'] = copy.deepcopy(
        defs['profile_erd.crowfoot@1']
    )
    for def_name in ('default_selector', 'view_definition'):
        enum_list = defs[def_name]['properties']['profile']['enum']
        if PROFILE_ID not in enum_list:
            enum_list.append(PROFILE_ID)
    defs['view_definition']['allOf'].append({
        'if': {
            'properties': {'profile': {'const': PROFILE_ID}},
            'required': ['profile'],
        },
        'then': {
            'properties': {
                'projection': {
                    'type': 'object',
                    'properties': {
                        'options': {'$ref': f'#/$defs/profile_{PROFILE_ID}'},
                        'defaults': {
                            'type': 'object',
                            'properties': {
                                'iso': {'$ref': '#/$defs/bool'},
                                'depth': {'$ref': '#/$defs/nonnegative'},
                            },
                            'required': [],
                            'additionalProperties': False,
                        },
                    },
                    'required': [],
                    'additionalProperties': False,
                },
            },
        },
    })
    schema_path.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False) + '\n'
    )

    prop_path = codex / 'property-codex.json'
    prop_codex = json.loads(prop_path.read_text())
    updated_enum = 0
    for item in prop_codex.get('structured_properties', []):
        choices = item.get('type', {}).get('enum')
        if isinstance(choices, list) and 'erd.crowfoot@1' in choices:
            if PROFILE_ID not in choices:
                choices.append(PROFILE_ID)
            updated_enum += 1
    for prop in prop_codex.get('properties', []):
        choices = prop.get('schema', {}).get('enum')
        if isinstance(choices, list) and 'erd.crowfoot@1' in choices:
            if PROFILE_ID not in choices:
                choices.append(PROFILE_ID)
            updated_enum += 1
    if not updated_enum:
        raise RuntimeError(
            'DDN property-codex profile enum changed; review cube patch'
        )
    prop_path.write_text(
        json.dumps(prop_codex, indent=2, ensure_ascii=False) + '\n'
    )

    roles_path = codex / 'role-contracts.json'
    roles = json.loads(roles_path.read_text())
    for role_name in set(PRIMARY_PALETTE) | set(context_roles):
        entry = roles.get(role_name)
        if entry and isinstance(entry.get('profiles'), list):
            if PROFILE_ID not in entry['profiles']:
                entry['profiles'].append(PROFILE_ID)
    roles_path.write_text(
        json.dumps(roles, indent=2, ensure_ascii=False) + '\n'
    )

    gen_path = root / 'project/ddn/packages/profiles/tools/generate.py'
    gen_text = gen_path.read_text()
    gen_text = _replace_once(
        gen_text,
        'assert len({key for family in families.values() '
        'for key in family})==153',
        'assert len({key for family in families.values() '
        'for key in family})==154',
        'generate.py family count',
    )
    gen_text = _replace_once(
        gen_text,
        "elif name.startswith(('chen.','chebotko.','erd.','orm.')):part='erd'",
        "elif name.startswith(('chen.','chebotko.','erd.','orm.','cube.')):"
        "part='erd'",
        'generate.py shard routing',
    )
    gen_text = _replace_once(
        gen_text,
        'assert sum(map(len,shards.values()))==149',
        'assert sum(map(len,shards.values()))==150',
        'generate.py shard count',
    )
    gen_path.write_text(gen_text)

    cat_path = (
        root / 'project/ddn/packages/presentation/src/graph-catalogue.ts'
    )
    cat_path.write_text(_replace_once(
        cat_path.read_text(),
        '"erd.crowfoot@1": { "projection": "graph" }',
        '"erd.crowfoot@1": { "projection": "graph" }, '
        f'"{PROFILE_ID}": {{ "projection": "graph" }}',
        'graph-catalogue.ts',
    ))

    common_path = (
        root / 'project/ddn/packages/presentation/src/graph-common.ts'
    )
    common_text = common_path.read_text()
    common_text = _replace_once(
        common_text,
        "if (profile === 'erd.crowfoot@1' && ['columns', 'draft', 'notes']",
        f"if ((profile === 'erd.crowfoot@1' || profile === '{PROFILE_ID}') "
        "&& ['columns', 'draft', 'notes']",
        'graph-common.ts body check',
    )
    common_text = _replace_once(
        common_text,
        "if (profile === 'erd.crowfoot@1') {",
        f"if (profile === 'erd.crowfoot@1' || profile === '{PROFILE_ID}') {{",
        'graph-common.ts cardinality marks',
    )
    common_path.write_text(common_text)

    prof_path = (
        root / 'project/ddn/packages/presentation/src/graph-profiles.ts'
    )
    prof_text = prof_path.read_text()
    prof_text = _replace_once(
        prof_text,
        "if (profile === 'erd.crowfoot@1' && !members.length",
        f"if ((profile === 'erd.crowfoot@1' || profile === '{PROFILE_ID}') "
        "&& !members.length",
        'graph-profiles.ts inline data rows',
    )
    prof_text = _replace_once(
        prof_text,
        "if (profile === 'erd.crowfoot@1' && entry.item.primitives.length",
        f"if ((profile === 'erd.crowfoot@1' || profile === '{PROFILE_ID}') "
        "&& entry.item.primitives.length",
        'graph-profiles.ts progressive body',
    )
    prof_path.write_text(prof_text)

    labels_path = root / 'project/ddn/packages/designer/src/view-labels.ts'
    labels_path.write_text(_replace_once(
        labels_path.read_text(),
        '"erd.crowfoot@1": "Crow’s-foot ERD",',
        '"erd.crowfoot@1": "Crow’s-foot ERD",\n'
        f'    "{PROFILE_ID}": "Dimensional cube",',
        'view-labels.ts',
    ))

    previews_path = root / 'project/ddn/packages/designer/src/view-previews.ts'
    previews_path.write_text(_replace_once(
        previews_path.read_text(),
        "'erd.crowfoot@1': ['erd', 1],",
        "'erd.crowfoot@1': ['erd', 1],\n"
        f"    '{PROFILE_ID}': ['erd', 1],",
        'view-previews.ts',
    ))

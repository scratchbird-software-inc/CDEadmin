##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Automated audit guardrails for SR-F form references, semantic icon registry,
and 15-locale i18n catalog completeness (Phase 5)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
JS_ROOT = REPO_ROOT / 'web' / 'pgadmin' / 'static' / 'js'
DESCRIPTORS_ROOT = REPO_ROOT / 'web' / 'pgadmin' / 'cdeadmin' / 'ui_descriptors'
FORM_REFS_PATH = JS_ROOT / 'cdeadmin_ui' / 'navigation' / 'formReferences.json'
ICON_REGISTRY_PATH = JS_ROOT / 'cdeadmin_ui' / 'icons' / 'registry.js'
TIB_CATALOG_PATH = JS_ROOT / 'cdeadmin_ui' / 'icons' / 'tibThreeToneCatalog.jsx'
UI_CATALOGS_PATH = JS_ROOT / 'cdeadmin_ui' / 'i18n' / 'ui_catalogs.json'
VALIDATE_SCRIPT = REPO_ROOT / 'tools' / 'validate_ui_descriptors.py'
LINT_MAXIMUMS = REPO_ROOT / 'tools' / 'ui_lint_maximums.json'

EXPECTED_NON_ENGLISH_LOCALES = (
    'zh_Hans_CN',
    'zh_Hant_TW',
    'cs',
    'fr',
    'de',
    'id',
    'it',
    'ja',
    'ko',
    'pl',
    'pt_BR',
    'ru',
    'es',
    'sv',
)

SRF_PATTERN = re.compile(r'^SR-F-\d{6}$')


def _parse_registered_icon_keys() -> tuple[set[str], list[str]]:
    """Extract all built-in semantic icon keys and taxonomy prefixes from registry.js."""
    src = ICON_REGISTRY_PATH.read_text(encoding='utf-8')
    keys: set[str] = set()

    engine_block = re.search(
        r'ENGINE_IDS\s*=\s*Object\.freeze\(\[(.*?)\]\)', src, re.S
    )
    assert engine_block, 'ENGINE_IDS block not found in registry.js'
    for eng in re.findall(r"'([a-z0-9_]+)'", engine_block.group(1)):
        keys.add(f'engine.{eng}')

    for map_name, prefix in (
        ('OBJECT_CLASSES', 'object'),
        ('ACTION_COMPONENTS', 'action'),
        ('STATUS_CLASSES', 'status'),
        ('TOOL_CLASSES', 'tool'),
    ):
        block = re.search(
            rf'const\s+{map_name}\s*=\s*Object\.freeze\(\{{(.*?)\}}\);',
            src,
            re.S,
        )
        assert block, f'{map_name} block not found in registry.js'
        for entry in re.findall(r'^\s*([a-z0-9_-]+)\s*:', block.group(1), re.M):
            keys.add(f'{prefix}.{entry}')

    for explicit in re.findall(
        r"(?:componentDefinition|definition)\(\s*'([a-z0-9._-]+)'", src
    ):
        keys.add(explicit)

    # registry.js registers every TiB three-tone icon from the catalog at
    # runtime as ``tib.<slug>``; the slugs are the TIB_ICON_SPECS keys.
    if TIB_CATALOG_PATH.exists():
        tib_src = TIB_CATALOG_PATH.read_text(encoding='utf-8')
        specs = re.search(
            r'const\s+TIB_ICON_SPECS\s*=\s*Object\.freeze\(\{(.*?)\}\);\s*$',
            tib_src,
            re.S | re.M,
        )
        body = specs.group(1) if specs else ''
        for slug in re.findall(r"(?:^|[,{])\s*'([a-z0-9_]+)'\s*:\s*\{'label'", body):
            keys.add(f'tib.{slug}')

    tax_block = re.search(
        r'const\s+TAXONOMY_FALLBACKS\s*=\s*Object\.freeze\(\[(.*?)\]\);',
        src,
        re.S,
    )
    taxonomy_prefixes: list[str] = []
    if tax_block:
        taxonomy_prefixes = re.findall(r"\[\s*'([a-z0-9._-]+)'", tax_block.group(1))

    return keys, taxonomy_prefixes


def _icon_key_resolves(
    raw_key: str, registered_keys: set[str], taxonomy_prefixes: list[str]
) -> bool:
    key = raw_key.strip().lower()
    if not key:
        return True
    if key in registered_keys:
        return True
    if key.startswith('object.'):
        normalized = f"object.{key[7:].replace('-', '_')}"
        if normalized in registered_keys:
            return True
    if key.startswith(('icon-', 'fa ')):
        return True
    if '.' not in key and f"object.{key.replace('-', '_')}" in registered_keys:
        return True
    if key.startswith('engine.'):
        return True
    if any(key.startswith(prefix) for prefix in taxonomy_prefixes):
        return True
    return False


def test_srf_form_references_and_ui_descriptors_completeness():
    data = json.loads(FORM_REFS_PATH.read_text(encoding='utf-8'))
    assert data.get('schema') == 'scratchrobin.form-references.v1'
    forms = data.get('forms', {})
    assert len(forms) >= 1640

    seen_refs: dict[str, str] = {}
    for form_key, meta in forms.items():
        ref = meta.get('reference', '')
        assert SRF_PATTERN.match(ref), f'Invalid SR-F code on {form_key}: {ref!r}'
        assert ref not in seen_refs, (
            f'Duplicate SR-F reference {ref} shared by {seen_refs[ref]} and {form_key}'
        )
        seen_refs[ref] = form_key
        assert str(meta.get('title', '')).strip(), f'Empty title on {form_key}'

    valid_refs = set(seen_refs.keys())

    # Every ui_descriptors/*.form.json must carry a registered form_reference.
    form_files = sorted(DESCRIPTORS_ROOT.glob('**/forms/*.form.json'))
    assert len(form_files) >= 140
    missing_descriptor_refs: list[str] = []
    for form_file in form_files:
        doc = json.loads(form_file.read_text(encoding='utf-8'))
        ref = doc.get('form_reference')
        if not ref or ref not in valid_refs:
            missing_descriptor_refs.append(
                f'{form_file.relative_to(REPO_ROOT)} -> {ref!r}'
            )
    assert not missing_descriptor_refs, (
        f'Descriptor forms with missing/unregistered form_reference: {missing_descriptor_refs}'
    )

    # Every static formKey="..." / resolveFormReference('...') in JS/JSX must exist in formReferences.json.
    static_form_key_re = re.compile(
        r"""(?:\bformKey\s*=\s*['"]([a-z0-9][a-z0-9._-]*)['"]|\bresolveFormReference\(\s*['"]([a-z0-9][a-z0-9._-]*)['"]\s*\))"""
    )
    unresolved_js_keys: list[str] = []
    for js_file in sorted(JS_ROOT.rglob('*')):
        if js_file.suffix not in {'.js', '.jsx', '.ts', '.tsx'}:
            continue
        text = js_file.read_text(encoding='utf-8')
        for match in static_form_key_re.finditer(text):
            candidate = match.group(1) or match.group(2)
            if candidate and candidate not in forms:
                unresolved_js_keys.append(
                    f'{js_file.relative_to(REPO_ROOT)}: {candidate}'
                )
    assert not unresolved_js_keys, (
        f'Unregistered static formKey / resolveFormReference calls: {unresolved_js_keys}'
    )

    # Enforce validate_ui_descriptors.py + ui_lint_maximums.json gate.
    proc = subprocess.run(
        [
            sys.executable,
            str(VALIDATE_SCRIPT),
            '--counts',
            '--enforce-counts',
            str(LINT_MAXIMUMS),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f'validate_ui_descriptors.py failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}'
    )
    assert 'ui descriptors: OK' in proc.stdout


def test_icon_registry_resolves_all_referenced_semantic_keys():
    registered_keys, taxonomy_prefixes = _parse_registered_icon_keys()
    assert len(registered_keys) >= 240

    target_files = [
        JS_ROOT / 'BrowserComponent.jsx',
        JS_ROOT / 'cdeadmin_ui' / 'actions' / 't_actions.js',
        JS_ROOT / 'cdeadmin_ui' / 'shell' / 'ProjectShell.jsx',
        JS_ROOT / 'cdeadmin_ui' / 'shell' / 'NotebookBar.jsx',
        JS_ROOT / 'cdeadmin_ui' / 'projects' / 'ProjectExplorer.jsx',
        JS_ROOT / 'cdeadmin_ui' / 'workspace' / 'SurfaceHost.js',
        JS_ROOT / 'cdeadmin_ui' / 'integrations' / 'ddn' / 'DesignerChrome.jsx',
        JS_ROOT / 'cdeadmin_ui' / 'integrations' / 'ddn' / 'ERDDesignerSurface.jsx',
        JS_ROOT / 'cdeadmin_ui' / 'integrations' / 'ddn' / 'CubeDesignerSurface.jsx',
        JS_ROOT / 'cdeadmin_ui' / 'integrations' / 'ddn' / 'BIDesignerSurface.jsx',
        JS_ROOT / 'cdeadmin_ui' / 'integrations' / 'ddn' / 'ScreenMeshDesignerSurface.jsx',
        REPO_ROOT / 'web' / 'pgadmin' / 'cdeadmin' / 'workspace' / 'shell_authority.py',
    ]
    target_files.extend(sorted((JS_ROOT / 'cdeadmin_ui' / 'modules').rglob('*.js')))
    target_files.extend(sorted((JS_ROOT / 'cdeadmin_ui' / 'modules').rglob('*.jsx')))

    icon_prop_re = re.compile(
        r"""\b(?:iconKey|icon)\s*:\s*['"]([a-z][a-z0-9]*\.[a-z0-9._-]+)['"]"""
    )
    unresolved_icons: list[str] = []
    for path in target_files:
        if not path.exists():
            continue
        text = path.read_text(encoding='utf-8')
        for match in icon_prop_re.finditer(text):
            icon_key = match.group(1)
            if not _icon_key_resolves(icon_key, registered_keys, taxonomy_prefixes):
                unresolved_icons.append(f'{path.relative_to(REPO_ROOT)}: {icon_key}')

    for desc_json in sorted(DESCRIPTORS_ROOT.rglob('*.json')):
        if 'schemas' in desc_json.parts:
            continue
        doc_text = desc_json.read_text(encoding='utf-8')
        for match in re.finditer(
            r'"(?:icon|icon_key)"\s*:\s*"([a-z][a-z0-9]*\.[a-z0-9._-]+)"', doc_text
        ):
            icon_key = match.group(1)
            if not _icon_key_resolves(icon_key, registered_keys, taxonomy_prefixes):
                unresolved_icons.append(
                    f'{desc_json.relative_to(REPO_ROOT)}: {icon_key}'
                )

    assert not unresolved_icons, (
        f'Referenced semantic icon keys missing from registry.js: {unresolved_icons}'
    )


def test_surface_action_hints_have_translations_in_every_locale():
    catalog_text = UI_CATALOGS_PATH.read_text(encoding='utf-8')
    catalogs = json.loads(catalog_text)['gettext']
    runtime_catalog = UI_CATALOGS_PATH.with_suffix('.js').read_text(encoding='utf-8')
    assert catalog_text.rstrip() in runtime_catalog
    hint_source = (JS_ROOT / 'cdeadmin_ui' / 'surfaces' / 'surfaceActionHints.js').read_text(encoding='utf-8')
    hints = set(re.findall(r"gettext\('([^']+)'\)", hint_source))
    for filename in ('DataEditSurface.jsx', 'SqlEditorSurface.jsx'):
        source = (JS_ROOT / 'cdeadmin_ui' / 'surfaces' / filename).read_text(encoding='utf-8')
        hints.update(re.findall(r"tooltip:\s*gettext\('([^']+)'\)", source))
    assert hints
    for locale, catalog in catalogs.items():
        untranslated = {hint for hint in hints if not catalog.get(hint) or catalog[hint] == hint}
        assert not untranslated, f'{locale}: {sorted(untranslated)}'


def test_i18n_catalogs_15_locale_parity_and_non_empty_strings():
    catalogs = json.loads(UI_CATALOGS_PATH.read_text(encoding='utf-8'))
    assert 'shell' in catalogs and 'gettext' in catalogs

    shell = catalogs['shell']
    assert 'en' in shell
    en_keys = set(shell['en'].keys())
    assert len(en_keys) >= 80

    for key, val in shell['en'].items():
        assert isinstance(val, str) and val.strip(), f'Empty English shell string: {key}'

    for locale in EXPECTED_NON_ENGLISH_LOCALES:
        assert locale in shell, f'Missing locale {locale} in shell catalog'
        loc_map = shell[locale]
        missing = sorted(en_keys - set(loc_map.keys()))
        extra = sorted(set(loc_map.keys()) - en_keys)
        assert not missing, f'Locale {locale} missing shell keys: {missing[:10]}'
        assert not extra, f'Locale {locale} has unexpected shell keys: {extra[:10]}'
        empty = [k for k, v in loc_map.items() if not isinstance(v, str) or not v.strip()]
        assert not empty, f'Locale {locale} has empty shell translations: {empty[:10]}'

    gt = catalogs['gettext']
    reference_gt_keys = set(gt[EXPECTED_NON_ENGLISH_LOCALES[0]].keys())
    assert len(reference_gt_keys) >= 200
    for locale in EXPECTED_NON_ENGLISH_LOCALES:
        assert locale in gt, f'Missing locale {locale} in gettext catalog'
        loc_gt = gt[locale]
        missing = sorted(reference_gt_keys - set(loc_gt.keys()))
        extra = sorted(set(loc_gt.keys()) - reference_gt_keys)
        assert not missing, f'Locale {locale} missing gettext keys: {missing[:10]}'
        assert not extra, f'Locale {locale} has unexpected gettext keys: {extra[:10]}'
        empty = [k for k, v in loc_gt.items() if not isinstance(v, str) or not v.strip()]
        assert not empty, f'Locale {locale} has empty gettext translations: {empty[:10]}'

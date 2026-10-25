"""Serve the declarative UI descriptors to the browser.

The descriptor folder (schemas, family skeletons and one folder per engine)
is the single source for what the shell renders; see
``docs/en_US/ui_unified_design.rst`` section 8 and ``README.md`` beside this
file. This module loads the folder once, resolves each engine form against
its family skeleton (tab order, grid column defaults, required tabs) and
exposes the result over ``/cdeadmin/api/ui/descriptors/<engine>``.

Nothing here knows about any engine; the engine folder does.
"""
from __future__ import annotations

import copy
import json
import re
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_EXTENSION_KEY = 'cdeadmin_ui_descriptors'
_VERSION_PART = re.compile(r'\d+')


class UIDescriptorError(RuntimeError):
    """A descriptor file is missing or malformed."""


def _load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        raise UIDescriptorError(f'{path.relative_to(ROOT)}: {exc}') from exc


def _version_tuple(text):
    if not text:
        return ()
    return tuple(int(part) for part in _VERSION_PART.findall(str(text))[:4])


def version_gate_state(gate, observed_version):
    """Return (available, reason) for a field/operation version gate."""
    if not gate:
        return True, None
    observed = _version_tuple(observed_version)
    if not observed:
        return True, None
    minimum = _version_tuple(gate.get('minimum'))
    maximum = _version_tuple(gate.get('maximum_exclusive'))
    if minimum and observed < minimum:
        return False, gate.get('reason') or f"Requires version {gate['minimum']} or later"
    if maximum and observed >= maximum:
        return False, gate.get('reason') or f"Removed in version {gate['maximum_exclusive']}"
    return True, None


class UIDescriptorService:
    """Loads and resolves the descriptor folder; safe to share per app."""

    def __init__(self, root: Path = ROOT):
        self.root = root
        self._lock = threading.RLock()
        self._families = None
        self._engines: dict[str, dict] = {}

    # -- loading -----------------------------------------------------------
    def families(self) -> dict:
        with self._lock:
            if self._families is None:
                families = {}
                for path in sorted((self.root / 'families').glob('*.family.json')):
                    doc = _load_json(path)
                    families[doc['family']] = doc
                self._families = families
            return self._families

    def engine_ids(self) -> list[str]:
        return sorted(
            p.name for p in self.root.iterdir()
            if p.is_dir() and p.name not in ('schema', 'families', '__pycache__')
            and (p / 'capabilities.json').exists()
        )

    def engine(self, engine_id: str) -> dict:
        """Return the resolved bundle for one engine (cached)."""
        with self._lock:
            cached = self._engines.get(engine_id)
            if cached is not None:
                return cached
            folder = self.root / engine_id
            if not (folder / 'capabilities.json').exists():
                raise UIDescriptorError(f'no UI descriptors for engine {engine_id!r}')
            bundle = {
                'schema': 'cdeadmin.ui-bundle.v1',
                'engine': engine_id,
                'capabilities': _load_json(folder / 'capabilities.json'),
                'operations': (_load_json(folder / 'operations.json') or {}).get('operations', []),
                'navigator': _load_json(folder / 'navigator.json') or {},
                'omitted_families': (_load_json(folder / 'omitted_families.json') or {}).get('omitted', []),
                'options': _load_json(folder / 'options.json') or {'dialect': {}, 'catalog': {}},
                'forms': {},
            }
            for path in sorted((folder / 'forms').glob('*.form.json')):
                form = _load_json(path)
                bundle['forms'][form['family']] = self._resolve_form(form)
            bundle['kinds'] = self._kind_index(bundle)
            self._engines[engine_id] = bundle
            return bundle

    def invalidate(self):
        with self._lock:
            self._families = None
            self._engines.clear()

    # -- resolution --------------------------------------------------------
    def _resolve_form(self, form: dict) -> dict:
        """Merge a family skeleton with an engine form into render order."""
        family = self.families().get(form['family'])
        if family is None:
            raise UIDescriptorError(f"{form['engine']}/{form['family']}: unknown family")
        omitted = {row['tab']: row['reason'] for row in form.get('omitted_tabs', [])}
        skeleton_by_tab = {tab['tab']: tab for tab in family['tabs']}
        fields_by_tab: dict[str, list] = {}
        for field in form.get('fields', []):
            fields_by_tab.setdefault(field.get('tab') or family['tabs'][0]['tab'], []).append(field)
        tabs = []
        for tab in family['tabs']:
            name = tab['tab']
            fields = fields_by_tab.get(name, [])
            shell_tab = tab['primitive'] in ('sql_preview', 'data_grid', 'readonly_grid', 'readonly_groups')
            if not fields and not shell_tab:
                continue  # engine has nothing for it (an omitted or empty tab)
            if name in omitted:
                continue
            title = form.get('engine_tab_title') if name == 'Engine' else name
            tabs.append({
                'tab': name,
                'title': title or name,
                'primitive': tab['primitive'],
                'required': bool(tab.get('required')),
                'fields': fields,
                'grid_columns': tab.get('grid_columns', []),
                'nested': tab.get('nested', []),
                'notes': tab.get('notes'),
            })
        resolved = copy.deepcopy(form)
        resolved['tabs'] = tabs
        resolved['family_title'] = family.get('title', form['family'].capitalize())
        resolved['family_tabs'] = [tab['tab'] for tab in family['tabs']]
        resolved['missing_required_tabs'] = [
            tab['tab'] for tab in family['tabs']
            if tab.get('required') and tab['tab'] not in {t['tab'] for t in tabs}
            and tab['tab'] not in omitted and tab['primitive'] != 'sql_preview'
        ]
        return resolved

    @staticmethod
    def _kind_index(bundle: dict) -> dict:
        kinds = {}
        ops_by_kind: dict[str, list] = {}
        for op in bundle['operations']:
            ops_by_kind.setdefault(op['resource_kind'], []).append(op)
        for kind in bundle['capabilities'].get('kinds', []):
            family = kind['family']
            form = bundle['forms'].get(family) if family != 'engine_object' else None
            kinds[kind['resource_kind']] = {
                'resource_kind': kind['resource_kind'],
                'family': family,
                'variant': kind.get('variant'),
                'title': kind.get('title'),
                'form_status': form.get('status') if form else None,
                'tier1': [op['operation_id'] for op in kind.get('operations', [])],
                'operations': ops_by_kind.get(kind['resource_kind'], []),
            }
        return kinds

    # -- per-connection view -------------------------------------------------
    def resolve_for_version(self, engine_id: str, observed_version: str | None) -> dict:
        """Copy of the bundle with version gates evaluated for a connection.

        Gated fields and operations are kept, with ``available`` and
        ``unavailable_reason`` set, so the shell disables rather than hides.
        """
        bundle = copy.deepcopy(self.engine(engine_id))

        def mark(item):
            available, reason = version_gate_state(item.get('version'), observed_version)
            item['available'] = available
            if reason:
                item['unavailable_reason'] = reason
            for column in item.get('columns', []) or []:
                mark(column)

        for form in bundle['forms'].values():
            for tab in form['tabs']:
                for field in tab['fields']:
                    mark(field)
        for op in bundle['operations']:
            mark(op)
            for field in op.get('fields', []):
                mark(field)
        bundle['observed_version'] = observed_version
        return bundle


def init_app(app) -> UIDescriptorService:
    existing = app.extensions.get(APP_EXTENSION_KEY)
    if existing is not None:
        return existing
    service = UIDescriptorService()
    app.extensions[APP_EXTENSION_KEY] = service

    from flask import Blueprint, jsonify, request
    from pgadmin.user_login_check import pga_login_required

    api = Blueprint('cdeadmin_ui_descriptors', __name__)

    @api.route('/cdeadmin/api/ui/descriptors', methods=['GET'])
    @pga_login_required
    def list_engines():
        return jsonify(success=1, data={
            'engines': service.engine_ids(),
            'families': list(service.families()),
        })

    @api.route('/cdeadmin/api/ui/descriptors/<engine_id>', methods=['GET'])
    @pga_login_required
    def engine_bundle(engine_id):
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,40}', engine_id):
            return jsonify(success=0, errormsg='Invalid engine'), 400
        try:
            if request.args.get('version'):
                data = service.resolve_for_version(engine_id, request.args.get('version'))
            else:
                data = service.engine(engine_id)
        except UIDescriptorError as exc:
            return jsonify(success=0, errormsg=str(exc)), 404
        response = jsonify(success=1, data=data)
        response.headers['Cache-Control'] = 'no-store' if app.debug else 'private, max-age=300'
        return response

    app.register_blueprint(api)
    return service


def service_for_app(app) -> UIDescriptorService:
    try:
        return app.extensions[APP_EXTENSION_KEY]
    except (AttributeError, KeyError) as exc:
        raise UIDescriptorError('UI descriptor service is not initialized') from exc


__all__ = ('UIDescriptorService', 'UIDescriptorError', 'init_app',
           'service_for_app', 'version_gate_state')

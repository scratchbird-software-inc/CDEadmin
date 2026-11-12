##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Regression tests for Screen Mesh DDN Phase 1 & Phase 2 extensions.

Covers:
1. ``look_handdrawn`` ("Sketch look") DDN round-trip & 0-diagnostic validation
   in ``ddn-next-1`` (both companion envelope and hand-written DDN fallback).
2. ``trace_screenshot_regions_to_mesh`` ("Trace as mesh", SR-F-030021):
   control role inference (checkbox, dropdown, grid with inferred columns,
   button, tabs, input, explicit kind_hint), exact ``(x, y, width, height)``
   geometry preservation, binding copying, and HTTP route.
3. ``build_screen_mesh_field_spec`` ("Field table" specification & exporter,
   SR-F-030022): joining screens, controls, ``ui.grid`` columns, ``ui.region``
   hotspots, and ``navigation`` links against authoritative ``binding`` rows,
   project physical ERD tables/columns in ``designs.db``, and ``catalog_metadata``
   with Markdown, CSV, HTML, and JSON exports + HTTP routes.
4. ``compare_screen_mesh_screenshots`` ("Compare with newer screenshot",
   SR-F-030021): Pillow + pure-Python PNG diffing, dimension change detection,
   affected ``ui.region`` hotspot overlap flagging, checkpoint replacement
   (``replace_screenshot=True``), and HTTP route.
"""

from __future__ import annotations

import base64
import csv
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib

from flask import Flask

from pgadmin.cdeadmin.design_store import (
    DesignStore,
    ScreenMeshSync,
    StoreDDNProcess,
    build_four_level_erd_ddn,
    build_solid_png,
    ddn_to_screen_mesh,
    init_routes_app,
    screen_mesh_to_ddn,
    uuid7,
)
from pgadmin.cdeadmin.design_store.screen_mesh_extensions import (
    build_screen_mesh_field_spec,
    compare_screen_mesh_screenshots,
    trace_screenshot_regions_to_mesh,
)


def _verify_ddn_with_runtime(documents: dict[str, str]) -> dict[str, dict]:
    """Open and semantically verify DDN documents with bundled DDN runtime."""
    repo_root = Path(__file__).resolve().parents[2]
    viewer_bundle = (
        repo_root
        / 'web/pgadmin/static/vendor/ddn/current/complete/ddn-viewer.js'
    )
    script = (
        "import { pathToFileURL } from 'node:url';\n"
        "const mod = await import(pathToFileURL(process.argv[1]).href);\n"
        "const runtime = mod.createRuntime(\n"
        "  mod.createCompleteRuntimeOptions()\n"
        ");\n"
        "const docs = JSON.parse(process.argv[2]);\n"
        "const out = {};\n"
        "for (const [k, text] of Object.entries(docs)) {\n"
        "  const src = {\n"
        "    entry: 'design.ddn',\n"
        "    files: [{\n"
        "      id: 'design.ddn',\n"
        "      text,\n"
        "      revision: 'v1',\n"
        "      encoding: 'utf-8',\n"
        "      writable: true,\n"
        "    }],\n"
        "  };\n"
        "  const opened = await runtime.open(src);\n"
        "  const diags = opened.diagnostics || [];\n"
        "  out[k] = {\n"
        "    ok: diags.length === 0,\n"
        "    diagnostics: diags,\n"
        "    fileCount: (opened.snapshot?.normalized?.files || []).length,\n"
        "  };\n"
        "}\n"
        "runtime.destroy();\n"
        "process.stdout.write(JSON.stringify(out));\n"
    )
    proc = subprocess.run(
        [
            'node',
            '--input-type=module',
            '-e',
            script,
            str(viewer_bundle),
            json.dumps(documents),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(proc.stdout)


def _make_test_app(db_path: Path) -> Flask:
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['LOGIN_DISABLED'] = True
    app.config['SECRET_KEY'] = 'test-screen-mesh-ddn-secret'
    app.config['CDEADMIN_DESIGN_STORE_PATH'] = str(db_path)
    init_routes_app(app)
    return app


def _build_patched_png(
    width: int,
    height: int,
    *,
    bg_rgb: tuple[int, int, int] = (240, 244, 248),
    patch_box: tuple[int, int, int, int] | None = None,
    patch_rgb: tuple[int, int, int] = (220, 38, 38),
) -> bytes:
    """Build a valid RGB PNG with an optional colored rectangular patch."""
    raw = bytearray()
    px0, py0, pw, ph = patch_box or (0, 0, 0, 0)
    for y in range(height):
        raw.append(0)  # Filter type 0 (None)
        for x in range(width):
            if px0 <= x < px0 + pw and py0 <= y < py0 + ph:
                raw.extend(patch_rgb)
            else:
                raw.extend(bg_rgb)

    def _chunk(ctype: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(ctype)
        crc = zlib.crc32(data, crc) & 0xFFFFFFFF
        return struct.pack('>I', len(data)) + ctype + data + struct.pack('>I', crc)

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(bytes(raw), level=6)
    return (
        b'\x89PNG\r\n\x1a\n'
        + _chunk(b'IHDR', ihdr)
        + _chunk(b'IDAT', idat)
        + _chunk(b'IEND', b'')
    )


class ScreenMeshDDNAndExtensionsTests(unittest.TestCase):
    def test_look_handdrawn_roundtrip_and_zero_ddn_diagnostics(self):
        """Sketch look (look_handdrawn) round-trips cleanly with 0 diagnostics."""
        scr1 = uuid7()
        scr2 = uuid7()
        ctrl_id = uuid7()
        nav_id = uuid7()

        sketch_mesh = {
            'name': 'Work Orders Sketch',
            'look_handdrawn': True,
            'screens': [
                {
                    'id': scr1,
                    'name': 'Dispatch Board',
                    'width': 1024,
                    'height': 720,
                    'form_reference': 'SR-F-030020',
                },
                {
                    'id': scr2,
                    'name': 'Inspector Overlay',
                    'width': 640,
                    'height': 480,
                },
            ],
            'controls': [
                {
                    'id': ctrl_id,
                    'screen_id': scr1,
                    'role': 'ui.input',
                    'name': 'Technician Filter',
                    'placeholder': 'Filter technician…',
                    'bounds': {'x': 32, 'y': 48, 'width': 260, 'height': 36},
                }
            ],
            'regions': [],
            'bindings': [],
            'navigations': [
                {
                    'id': nav_id,
                    'from_id': ctrl_id,
                    'to_screen_id': scr2,
                    'trigger': 'click',
                    'action': 'overlay',
                    'label': 'Inspect Technician',
                }
            ],
        }
        ddn_sketch, _ = screen_mesh_to_ddn(sketch_mesh)
        self.assertIn('look "handdrawn"', ddn_sketch)

        parsed_sketch = ddn_to_screen_mesh(ddn_sketch)['mesh']
        self.assertTrue(parsed_sketch['look_handdrawn'])
        self.assertEqual(
            parsed_sketch['controls'][0]['bounds'],
            {'x': 32, 'y': 48, 'width': 260, 'height': 36},
        )

        # Crisp mode (look_handdrawn=False) omits look "handdrawn"
        crisp_mesh = {**sketch_mesh, 'look_handdrawn': False}
        ddn_crisp, _ = screen_mesh_to_ddn(crisp_mesh)
        self.assertNotIn('look "handdrawn"', ddn_crisp)
        parsed_crisp = ddn_to_screen_mesh(ddn_crisp)['mesh']
        self.assertFalse(parsed_crisp['look_handdrawn'])

        # Strip companion envelope to verify hand-written DDN fallback parser
        handwritten_lines = [
            line
            for line in ddn_sketch.splitlines()
            if 'envelope_b64' not in line and 'envelope_json' not in line
        ]
        handwritten_ddn = '\n'.join(handwritten_lines)
        parsed_handwritten = ddn_to_screen_mesh(handwritten_ddn)['mesh']
        self.assertTrue(parsed_handwritten['look_handdrawn'])
        self.assertEqual(
            parsed_handwritten['controls'][0]['bounds'],
            {'x': 32, 'y': 48, 'width': 260, 'height': 36},
        )

        # Validate both documents with the real bundled ddn-next-1 runtime
        verified = _verify_ddn_with_runtime(
            {'sketch': ddn_sketch, 'crisp': ddn_crisp}
        )
        self.assertTrue(verified['sketch']['ok'], verified['sketch'])
        self.assertEqual(verified['sketch']['diagnostics'], [])
        self.assertTrue(verified['crisp']['ok'], verified['crisp'])
        self.assertEqual(verified['crisp']['diagnostics'], [])

    def test_trace_screenshot_regions_to_mesh_inference_and_bindings(self):
        """SR-F-030021: Trace as mesh infers roles, bounds, grid cols & bindings."""
        with tempfile.TemporaryDirectory() as tmp:
            store = DesignStore(Path(tmp) / 'designs.db')
            proc = StoreDDNProcess(store)

            # Seed a physical ERD in the same project so ui.grid column inference
            # discovers exact columns from sales.order_lines and FK/boolean types.
            erd_ddn = build_four_level_erd_ddn(
                title='Sales Physical Schema',
                physical_tables=[
                    {
                        'name': 'sales.orders',
                        'fields': [
                            {'name': 'id', 'datatype': 'INTEGER', 'nullable': False},
                            {'name': 'customer_name', 'datatype': 'VARCHAR(120)', 'nullable': False},
                            {'name': 'order_status', 'datatype': 'VARCHAR(32)', 'nullable': False},
                            {'name': 'is_priority', 'datatype': 'BOOLEAN', 'nullable': False},
                        ],
                    },
                    {
                        'name': 'sales.order_lines',
                        'fields': [
                            {'name': 'line_id', 'datatype': 'INTEGER', 'nullable': False},
                            {'name': 'sku', 'datatype': 'VARCHAR(40)', 'nullable': False},
                            {'name': 'qty', 'datatype': 'INTEGER', 'nullable': False},
                            {'name': 'unit_price', 'datatype': 'NUMERIC(12,2)', 'nullable': False},
                        ],
                    },
                ],
            )
            store.create_design(
                project_id='proj-trace',
                key='sales-erd',
                kind='erd',
                title='Sales Physical Schema',
                ddn_text=erd_ddn,
                actor_id=1,
            )

            scr_shot = uuid7()
            scr_detail = uuid7()
            reg_input = uuid7()
            reg_chk = uuid7()
            reg_drop = uuid7()
            reg_grid = uuid7()
            reg_btn = uuid7()
            reg_tabs = uuid7()

            sync = ScreenMeshSync(store, proc)
            created = sync.create_screen_mesh(
                project_id='proj-trace',
                key='orders-capture',
                title='Orders Screenshot Capture',
                actor_id=1,
                mesh={
                    'name': 'Orders Screenshot Capture',
                    'look_handdrawn': True,
                    'screens': [
                        {
                            'id': scr_shot,
                            'name': 'Orders Capture',
                            'width': 1200,
                            'height': 800,
                        },
                        {
                            'id': scr_detail,
                            'name': 'Confirmation Modal',
                            'width': 480,
                            'height': 320,
                        },
                    ],
                    'controls': [],
                    'regions': [
                        {
                            'id': reg_input,
                            'screen_id': scr_shot,
                            'name': 'Customer Name',
                            'bounds': {'x': 40, 'y': 60, 'width': 280, 'height': 36},
                        },
                        {
                            'id': reg_chk,
                            'screen_id': scr_shot,
                            'name': 'Priority Flag',
                            'bounds': {'x': 350, 'y': 64, 'width': 140, 'height': 28},
                        },
                        {
                            'id': reg_drop,
                            'screen_id': scr_shot,
                            'name': 'Order Status Selector',
                            'bounds': {'x': 520, 'y': 60, 'width': 220, 'height': 36},
                        },
                        {
                            'id': reg_grid,
                            'screen_id': scr_shot,
                            'name': 'Order Lines Table',
                            'bounds': {'x': 40, 'y': 140, 'width': 920, 'height': 360},
                        },
                        {
                            'id': reg_btn,
                            'screen_id': scr_shot,
                            'name': 'Submit Order',
                            'bounds': {'x': 800, 'y': 540, 'width': 160, 'height': 42},
                        },
                        {
                            'id': reg_tabs,
                            'screen_id': scr_shot,
                            'name': 'Order Section Tabs',
                            'bounds': {'x': 40, 'y': 16, 'width': 520, 'height': 32},
                        },
                    ],
                    'bindings': [
                        {
                            'id': uuid7(),
                            'source_id': reg_input,
                            'target_kind': 'column',
                            'target_ref': 'sales.orders.customer_name',
                            'access_mode': 'read_write',
                        },
                        {
                            'id': uuid7(),
                            'source_id': reg_chk,
                            'target_kind': 'column',
                            'target_ref': 'sales.orders.is_priority',
                            'access_mode': 'read_write',
                        },
                        {
                            'id': uuid7(),
                            'source_id': reg_drop,
                            'target_kind': 'column',
                            'target_ref': 'sales.orders.order_status',
                            'access_mode': 'read_write',
                        },
                        {
                            'id': uuid7(),
                            'source_id': reg_grid,
                            'target_kind': 'table',
                            'target_ref': 'sales.order_lines',
                            'access_mode': 'read',
                        },
                    ],
                    'navigations': [
                        {
                            'id': uuid7(),
                            'from_id': reg_btn,
                            'to_screen_id': scr_detail,
                            'trigger': 'click',
                            'action': 'overlay',
                            'label': 'Submit -> Confirmation',
                        }
                    ],
                },
            )
            design_id = created['design']['id']

            traced = trace_screenshot_regions_to_mesh(
                store,
                proc,
                design_id=design_id,
                actor_id=1,
                payload={
                    'source_screen_id': scr_shot,
                    'link_navigation': True,
                },
            )

            self.assertEqual(traced['controls_created'], 6)
            self.assertEqual(traced['bindings_preserved'], 4)
            traced_screen_id = traced['traced_screen_id']
            mesh = traced['mesh']
            self.assertTrue(mesh['look_handdrawn'])

            screens_by_id = {s['id']: s for s in mesh['screens']}
            self.assertIn(scr_shot, screens_by_id)
            self.assertIn(traced_screen_id, screens_by_id)
            self.assertEqual(
                screens_by_id[traced_screen_id]['name'],
                'Orders Capture (Traced Mesh)',
            )

            traced_controls = [
                c for c in mesh['controls'] if c['screen_id'] == traced_screen_id
            ]
            roles_by_name = {c['name']: c['role'] for c in traced_controls}
            self.assertEqual(roles_by_name['Customer Name'], 'ui.input')
            self.assertEqual(roles_by_name['Priority Flag'], 'ui.checkbox')
            self.assertEqual(roles_by_name['Order Status Selector'], 'ui.dropdown')
            self.assertEqual(roles_by_name['Order Lines Table'], 'ui.grid')
            self.assertEqual(roles_by_name['Submit Order'], 'ui.button')
            self.assertEqual(roles_by_name['Order Section Tabs'], 'ui.tabs')

            # Exact (x, y, width, height) geometry preserved on every control
            bounds_by_name = {c['name']: c['bounds'] for c in traced_controls}
            self.assertEqual(
                bounds_by_name['Customer Name'],
                {'x': 40, 'y': 60, 'width': 280, 'height': 36},
            )
            self.assertEqual(
                bounds_by_name['Order Lines Table'],
                {'x': 40, 'y': 140, 'width': 920, 'height': 360},
            )

            # ui.grid columns inferred from project physical ERD sales.order_lines
            grid_ctrl = next(
                c for c in traced_controls if c['name'] == 'Order Lines Table'
            )
            col_ids = [col['id'] for col in grid_ctrl['columns']]
            self.assertEqual(col_ids, ['line_id', 'sku', 'qty', 'unit_price'])

            # Every binding copied onto the traced controls
            traced_ctrl_ids = {c['id'] for c in traced_controls}
            copied_bindings = [
                b for b in mesh['bindings'] if b['source_id'] in traced_ctrl_ids
            ]
            self.assertEqual(len(copied_bindings), 4)
            self.assertEqual(
                {b['target_ref'] for b in copied_bindings},
                {
                    'sales.orders.customer_name',
                    'sales.orders.is_priority',
                    'sales.orders.order_status',
                    'sales.order_lines',
                },
            )

            # Saved DDN validates with 0 diagnostics in real ddn-next-1 runtime
            saved_ddn = traced['design']['version']['ddn_text']
            verified = _verify_ddn_with_runtime({'traced': saved_ddn})
            self.assertTrue(verified['traced']['ok'], verified['traced'])
            self.assertEqual(verified['traced']['diagnostics'], [])

    def test_build_screen_mesh_field_spec_joins_bindings_erd_and_exports(self):
        """SR-F-030022: Field specification table joins bindings + ERD + exports."""
        with tempfile.TemporaryDirectory() as tmp:
            store = DesignStore(Path(tmp) / 'designs.db')
            proc = StoreDDNProcess(store)

            erd_ddn = build_four_level_erd_ddn(
                title='Billing Physical Schema',
                physical_tables=[
                    {
                        'name': 'billing.invoices',
                        'fields': [
                            {'name': 'invoice_id', 'datatype': 'BIGINT', 'nullable': False},
                            {'name': 'customer_code', 'datatype': 'VARCHAR(32)', 'nullable': False},
                            {'name': 'notes_text', 'datatype': 'TEXT', 'nullable': True},
                        ],
                    }
                ],
            )
            store.create_design(
                project_id='proj-spec',
                key='billing-erd',
                kind='erd',
                title='Billing Physical Schema',
                ddn_text=erd_ddn,
                actor_id=1,
            )

            s1 = uuid7()
            s2 = uuid7()
            inp_cust = uuid7()
            grid_inv = uuid7()
            btn_open = uuid7()
            reg_legacy = uuid7()

            sync = ScreenMeshSync(store, proc)
            created = sync.create_screen_mesh(
                project_id='proj-spec',
                key='invoice-workbench',
                title='Invoice Workbench',
                actor_id=1,
                mesh={
                    'name': 'Invoice Workbench',
                    'screens': [
                        {'id': s1, 'name': 'Invoice List', 'width': 1000, 'height': 700},
                        {'id': s2, 'name': 'Invoice Drawer', 'width': 560, 'height': 700},
                    ],
                    'controls': [
                        {
                            'id': inp_cust,
                            'screen_id': s1,
                            'role': 'ui.input',
                            'name': 'Customer Code Filter',
                        },
                        {
                            'id': grid_inv,
                            'screen_id': s1,
                            'role': 'ui.grid',
                            'name': 'Invoices Grid',
                            'columns': [
                                {
                                    'id': 'invoice_id',
                                    'name': 'Invoice #',
                                    'width': 120,
                                    'datatype': 'bigint',
                                },
                                {
                                    'id': 'legacy_amt',
                                    'name': 'Invoice Total',
                                    'width': 140,
                                    'datatype': 'numeric(12,2)',
                                },
                            ],
                        },
                        {
                            'id': btn_open,
                            'screen_id': s1,
                            'role': 'ui.button',
                            'name': 'Open Drawer',
                        },
                    ],
                    'regions': [
                        {
                            'id': reg_legacy,
                            'screen_id': s1,
                            'name': 'Notes Hotspot',
                            'bounds': {'x': 24, 'y': 500, 'width': 400, 'height': 80},
                        }
                    ],
                    'bindings': [
                        {
                            'id': uuid7(),
                            'source_id': inp_cust,
                            'target_kind': 'column',
                            'target_ref': 'billing.invoices.customer_code',
                            'access_mode': 'read_write',
                        },
                        {
                            'id': uuid7(),
                            'source_id': grid_inv,
                            'column_id': 'invoice_id',
                            'target_kind': 'column',
                            'target_ref': 'billing.invoices.invoice_id',
                            'access_mode': 'read',
                        },
                        {
                            'id': uuid7(),
                            'source_id': grid_inv,
                            'column_id': 'legacy_amt',
                            'target_kind': 'column',
                            'target_ref': 'billing.invoices.total_amount',
                            'access_mode': 'read',
                            'target_engine': 'sqlite',
                            'target_endpoint_id': 'ep-1',
                            'target_database_target_id': 'db-1',
                        },
                        {
                            'id': uuid7(),
                            'source_id': reg_legacy,
                            'target_kind': 'column',
                            'target_ref': 'billing.invoices.notes_text',
                            'access_mode': 'read',
                        },
                    ],
                    'navigations': [
                        {
                            'id': uuid7(),
                            'from_id': btn_open,
                            'to_screen_id': s2,
                            'trigger': 'click',
                            'action': 'overlay',
                            'label': 'Inspect Invoice',
                        }
                    ],
                },
            )
            design_id = created['design']['id']

            # Confirm valid bindings and mark renamed/dropped column as suspect
            for b in store.list_bindings(design_id=design_id):
                if b['target_ref'] != 'billing.invoices.total_amount':
                    store.confirm_binding(b['id'], actor_id=1)
            store.record_resource_rename(
                engine='sqlite',
                endpoint_id='ep-1',
                database_target_id='db-1',
                old_resource_id='billing.invoices.total_amount',
                new_resource_id='billing.invoices.invoice_total_cents',
            )

            spec = build_screen_mesh_field_spec(
                store,
                proc,
                design_id=design_id,
                payload={
                    'format': 'markdown',
                    'catalog_metadata': {
                        'billing.invoices.customer_code': {
                            'catalog_type': 'VARCHAR(32)',
                            'nullable': False,
                            'default_value': "'CUST-000'",
                        }
                    },
                },
            )

            self.assertEqual(spec['design_id'], design_id)
            self.assertEqual(spec['title'], 'Invoice Workbench')
            self.assertEqual(spec['summary']['bound_fields'], 5)
            self.assertEqual(spec['summary']['suspect_fields'], 1)
            self.assertGreaterEqual(spec['summary']['total_fields'], 8)

            rows_by_label = {r['label']: r for r in spec['rows']}
            cust_row = rows_by_label['Customer Code Filter']
            self.assertEqual(cust_row['access_mode'], 'read_write')
            self.assertEqual(cust_row['catalog_type'], 'VARCHAR(32)')
            self.assertFalse(cust_row['nullable'])
            self.assertEqual(cust_row['default_value'], "'CUST-000'")
            self.assertEqual(cust_row['binding_state'], 'valid')

            inv_col_row = rows_by_label['Invoices Grid.Invoice #']
            self.assertEqual(inv_col_row['element_kind'], 'ui.grid.column')
            self.assertEqual(inv_col_row['access_mode'], 'read_only')
            self.assertEqual(inv_col_row['catalog_type'], 'BIGINT')
            self.assertFalse(inv_col_row['nullable'])
            self.assertEqual(inv_col_row['binding_state'], 'valid')

            suspect_row = rows_by_label['Invoices Grid.Invoice Total']
            self.assertEqual(suspect_row['binding_state'], 'suspect')
            self.assertTrue(suspect_row['notes'])

            notes_row = rows_by_label['Notes Hotspot']
            self.assertEqual(notes_row['element_kind'], 'ui.region')
            self.assertEqual(notes_row['catalog_type'], 'TEXT')
            self.assertTrue(notes_row['nullable'])

            nav_row = rows_by_label['Open Drawer -> Inspect Invoice']
            self.assertEqual(nav_row['element_kind'], 'navigation')
            self.assertEqual(nav_row['access_mode'], 'trigger')
            self.assertEqual(nav_row['target_ref'], 'screen:Invoice Drawer')

            # Markdown, CSV, and HTML exports are populated and well-formed
            self.assertIn('Invoice Workbench', spec['markdown'])
            self.assertIn('| Invoice List |', spec['markdown'])
            self.assertIn('billing.invoices.customer_code', spec['markdown'])

            parsed_csv = list(csv.DictReader(io.StringIO(spec['csv'])))
            self.assertEqual(len(parsed_csv), len(spec['rows']))
            self.assertIn('target_ref', parsed_csv[0])

            self.assertIn('<!doctype html>', spec['html'].lower())
            self.assertIn('<table>', spec['html'])
            self.assertIn('billing.invoices.customer_code', spec['html'])

    def test_compare_screen_mesh_screenshots_pillow_pure_python_and_replace(self):
        """SR-F-030021: Compare newer screenshot flags affected regions & replaces."""
        with tempfile.TemporaryDirectory() as tmp:
            store = DesignStore(Path(tmp) / 'designs.db')
            proc = StoreDDNProcess(store)
            sync = ScreenMeshSync(store, proc)

            scr_id = uuid7()
            reg_hit = uuid7()
            reg_safe = uuid7()

            created = sync.create_screen_mesh(
                project_id='proj-diff',
                key='capture-diff',
                title='Capture Diff Mesh',
                actor_id=1,
                mesh={
                    'name': 'Capture Diff Mesh',
                    'screens': [
                        {
                            'id': scr_id,
                            'name': 'Order Header Capture',
                            'width': 120,
                            'height': 90,
                        }
                    ],
                    'controls': [],
                    'regions': [
                        {
                            'id': reg_hit,
                            'screen_id': scr_id,
                            'name': 'Header Banner Hotspot',
                            'bounds': {'x': 10, 'y': 10, 'width': 40, 'height': 30},
                        },
                        {
                            'id': reg_safe,
                            'screen_id': scr_id,
                            'name': 'Footer Hotspot',
                            'bounds': {'x': 70, 'y': 60, 'width': 40, 'height': 20},
                        },
                    ],
                    'bindings': [],
                    'navigations': [],
                },
            )
            design_id = created['design']['id']

            base_png = _build_patched_png(120, 90, bg_rgb=(240, 244, 248))
            sync.attach_screenshot(
                design_id,
                actor_id=1,
                data=base_png,
                media_type='image/png',
                screen_id=scr_id,
            )

            # Newer screenshot modifies pixels inside Header Banner Hotspot (15..45, 12..36)
            newer_png = _build_patched_png(
                120,
                90,
                bg_rgb=(240, 244, 248),
                patch_box=(15, 12, 30, 24),
                patch_rgb=(20, 90, 220),
            )
            newer_b64 = base64.b64encode(newer_png).decode('ascii')

            # 1. Default comparison (Pillow when available)
            report_pil = compare_screen_mesh_screenshots(
                store,
                proc,
                design_id=design_id,
                actor_id=1,
                payload={
                    'screen_id': scr_id,
                    'new_image_base64': f'data:image/png;base64,{newer_b64}',
                    'replace_screenshot': False,
                },
            )
            self.assertEqual(report_pil['old_dimensions'], {'width': 120, 'height': 90})
            self.assertEqual(report_pil['new_dimensions'], {'width': 120, 'height': 90})
            self.assertFalse(report_pil['dimension_changed'])
            self.assertGreater(report_pil['changed_pixel_ratio'], 0.05)
            self.assertGreaterEqual(len(report_pil['diff_bounding_boxes']), 1)

            by_reg = {r['region_id']: r for r in report_pil['affected_regions']}
            self.assertEqual(by_reg[reg_hit]['recommendation'], 'review_bounds')
            self.assertGreater(by_reg[reg_hit]['overlap_ratio'], 0.4)
            self.assertFalse(by_reg[reg_hit]['out_of_bounds'])
            self.assertEqual(by_reg[reg_safe]['recommendation'], 'unchanged')
            self.assertEqual(by_reg[reg_safe]['overlap_ratio'], 0.0)
            self.assertFalse(report_pil['replaced'])

            # 2. Pure-Python PNG fallback produces matching region recommendations
            report_pure = compare_screen_mesh_screenshots(
                store,
                proc,
                design_id=design_id,
                actor_id=1,
                payload={
                    'screen_id': scr_id,
                    'new_image_base64': newer_b64,
                    '_force_pure_python': True,
                },
            )
            self.assertAlmostEqual(
                report_pure['changed_pixel_ratio'],
                report_pil['changed_pixel_ratio'],
                places=4,
            )
            by_reg_pure = {
                r['region_id']: r for r in report_pure['affected_regions']
            }
            self.assertEqual(by_reg_pure[reg_hit]['recommendation'], 'review_bounds')
            self.assertEqual(by_reg_pure[reg_safe]['recommendation'], 'unchanged')

            # 3. Smaller screenshot triggers out_of_bounds + replace_screenshot=True saves checkpoint
            shrunk_png = build_solid_png(80, 50, rgb=(240, 244, 248))
            shrunk_b64 = base64.b64encode(shrunk_png).decode('ascii')
            replaced = compare_screen_mesh_screenshots(
                store,
                proc,
                design_id=design_id,
                actor_id=1,
                payload={
                    'screen_id': scr_id,
                    'new_image_base64': shrunk_b64,
                    'media_type': 'image/png',
                    'replace_screenshot': True,
                },
            )
            self.assertTrue(replaced['dimension_changed'])
            self.assertTrue(replaced['replaced'])
            self.assertGreaterEqual(replaced['design']['head_version'], 3)
            by_reg_shrunk = {
                r['region_id']: r for r in replaced['affected_regions']
            }
            self.assertTrue(by_reg_shrunk[reg_safe]['out_of_bounds'])
            self.assertEqual(
                by_reg_shrunk[reg_safe]['recommendation'], 'review_bounds'
            )

    def test_http_routes_for_trace_field_spec_and_compare_screenshot(self):
        """End-to-end Flask API verification for the 3 Screen Mesh extension routes."""
        with tempfile.TemporaryDirectory() as tmp:
            app = _make_test_app(Path(tmp) / 'routes_designs.db')
            client = app.test_client()

            scr_id = uuid7()
            reg_id = uuid7()
            create_resp = client.post(
                '/cdeadmin/api/projects/ui-ext/designs',
                json={
                    'mode': 'create_screen_mesh',
                    'key': 'customer-portal',
                    'title': 'Customer Portal',
                    'mesh': {
                        'name': 'Customer Portal',
                        'look_handdrawn': True,
                        'screens': [
                            {
                                'id': scr_id,
                                'name': 'Portal Home',
                                'width': 80,
                                'height': 60,
                            }
                        ],
                        'controls': [],
                        'regions': [
                            {
                                'id': reg_id,
                                'screen_id': scr_id,
                                'name': 'Active Subscription Flag',
                                'bounds': {'x': 8, 'y': 8, 'width': 32, 'height': 20},
                            }
                        ],
                        'bindings': [
                            {
                                'id': uuid7(),
                                'source_id': reg_id,
                                'target_kind': 'column',
                                'target_ref': 'crm.accounts.is_active',
                                'access_mode': 'read_write',
                            }
                        ],
                        'navigations': [],
                    },
                },
            )
            self.assertEqual(
                create_resp.status_code, 200, create_resp.get_data(as_text=True)
            )
            created_data = create_resp.get_json()['data']
            design_id = (created_data.get('design') or created_data)['id']

            # Attach initial screenshot
            png1 = _build_patched_png(80, 60, bg_rgb=(250, 250, 252))
            up_resp = client.post(
                f'/cdeadmin/api/projects/ui-ext/designs/{design_id}/screen-mesh/screenshot',
                json={
                    'screen_id': scr_id,
                    'media_type': 'image/png',
                    'image_base64': base64.b64encode(png1).decode('ascii'),
                },
            )
            self.assertEqual(up_resp.status_code, 200)

            # 1. POST /screen-mesh/compare-screenshot
            png2 = _build_patched_png(
                80,
                60,
                bg_rgb=(250, 250, 252),
                patch_box=(10, 10, 24, 16),
                patch_rgb=(180, 20, 40),
            )
            cmp_resp = client.post(
                f'/cdeadmin/api/projects/ui-ext/designs/{design_id}/screen-mesh/compare-screenshot',
                json={
                    'screen_id': scr_id,
                    'new_image_base64': base64.b64encode(png2).decode('ascii'),
                },
            )
            self.assertEqual(
                cmp_resp.status_code, 200, cmp_resp.get_data(as_text=True)
            )
            cmp_json = cmp_resp.get_json()['data']
            self.assertEqual(
                cmp_json['affected_regions'][0]['recommendation'],
                'review_bounds',
            )

            # 2. POST /screen-mesh/trace
            trace_resp = client.post(
                f'/cdeadmin/api/projects/ui-ext/designs/{design_id}/screen-mesh/trace',
                json={'source_screen_id': scr_id},
            )
            self.assertEqual(
                trace_resp.status_code, 200, trace_resp.get_data(as_text=True)
            )
            trace_json = trace_resp.get_json()['data']
            self.assertEqual(trace_json['controls_created'], 1)
            self.assertEqual(trace_json['bindings_preserved'], 1)
            self.assertEqual(
                trace_json['traced_controls'][0]['role'], 'ui.checkbox'
            )

            # 3. GET & POST /screen-mesh/field-spec
            spec_get = client.get(
                f'/cdeadmin/api/projects/ui-ext/designs/{design_id}/screen-mesh/field-spec?format=csv'
            )
            self.assertEqual(spec_get.status_code, 200)
            spec_json = spec_get.get_json()['data']
            self.assertIn('crm.accounts.is_active', spec_json['csv'])
            self.assertGreaterEqual(spec_json['summary']['bound_fields'], 2)

            spec_post = client.post(
                f'/cdeadmin/api/projects/ui-ext/designs/{design_id}/screen-mesh/field-spec',
                json={
                    'format': 'html',
                    'catalog_metadata': {
                        'crm.accounts.is_active': {
                            'catalog_type': 'BOOLEAN',
                            'nullable': False,
                            'default_value': 'true',
                        }
                    },
                },
            )
            self.assertEqual(spec_post.status_code, 200)
            post_data = spec_post.get_json()['data']
            self.assertIn('BOOLEAN', post_data['html'])


if __name__ == '__main__':
    unittest.main()

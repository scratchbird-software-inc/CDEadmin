##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Regression tests for the DDN Screen Mesh Designer (F1-F4)."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

from flask import Flask

from pgadmin.cdeadmin.design_store import (
    ALL_WIREFRAME_ROLES,
    WIREFRAME_PROFILE,
    DesignStore,
    DesignStoreConflict,
    DesignStoreError,
    ScreenMeshSync,
    StoreDDNProcess,
    build_solid_png,
    ddn_to_screen_mesh,
    init_routes_app,
    is_uuid7,
    list_available_descriptor_forms,
    read_png_pixel_rgb,
    screen_mesh_to_ddn,
    uuid7,
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
    app.config['SECRET_KEY'] = 'test-screen-mesh-secret'
    app.config['CDEADMIN_DESIGN_STORE_PATH'] = str(db_path)
    init_routes_app(app)
    return app


class ScreenMeshDesignerBackendTests(unittest.TestCase):
    def test_all_twelve_wireframe_roles_navigation_and_ddn_runtime(self):
        """F1 & F2: all 12 wireframe.ui@1 roles, bindings & screen_flow."""
        s1 = uuid7()
        s2 = uuid7()
        grid_id = uuid7()
        btn_id = uuid7()
        reg_id = uuid7()

        controls = [
            {
                'id': grid_id,
                'screen_id': s1,
                'role': 'ui.grid',
                'name': 'Customer Orders Grid',
                'columns': [
                    {
                        'id': 'order_id',
                        'name': 'Order ID',
                        'width': 110,
                        'datatype': 'integer',
                    },
                    {
                        'id': 'total_amt',
                        'name': 'Total Amount',
                        'width': 140,
                        'datatype': 'numeric',
                    },
                ],
            },
            {
                'id': uuid7(),
                'screen_id': s1,
                'role': 'ui.dropdown',
                'name': 'Order Status',
                'options': ['Draft', 'Submitted', 'Shipped'],
            },
            {
                'id': uuid7(),
                'screen_id': s1,
                'role': 'ui.radio',
                'name': 'Expedited Shipping',
                'checked': True,
                'options': ['Standard', 'Expedited'],
            },
            {
                'id': uuid7(),
                'screen_id': s1,
                'role': 'ui.tabs',
                'name': 'Order Sections',
                'options': ['Summary', 'Line Items', 'Audit'],
            },
            {
                'id': btn_id,
                'screen_id': s1,
                'role': 'ui.button',
                'name': 'Inspect Customer',
            },
            {
                'id': uuid7(),
                'screen_id': s1,
                'role': 'ui.checkbox',
                'name': 'Tax Exempt',
                'checked': False,
            },
            {
                'id': uuid7(),
                'screen_id': s1,
                'role': 'ui.input',
                'name': 'Customer Search',
                'placeholder': 'Type customer name…',
            },
            {
                'id': uuid7(),
                'screen_id': s1,
                'role': 'ui.label',
                'name': 'Header Title',
            },
            {
                'id': uuid7(),
                'screen_id': s1,
                'role': 'ui.list',
                'name': 'Recent Filters',
                'options': ['Today', 'This Quarter'],
            },
            {
                'id': uuid7(),
                'screen_id': s2,
                'role': 'ui.image',
                'name': 'Customer Avatar Placeholder',
            },
        ]
        used_roles = {c['role'] for c in controls} | {'ui.frame', 'ui.region'}
        self.assertEqual(used_roles, set(ALL_WIREFRAME_ROLES))

        mesh = {
            'name': 'Order Workbench Mesh',
            'screens': [
                {
                    'id': s1,
                    'name': 'Orders List Screen',
                    'width': 1024,
                    'height': 720,
                    'form_reference': 'SR-F-010027',
                },
                {
                    'id': s2,
                    'name': 'Customer Detail Modal',
                    'width': 640,
                    'height': 480,
                },
            ],
            'controls': controls,
            'regions': [
                {
                    'id': reg_id,
                    'screen_id': s1,
                    'name': 'KPI Banner Region',
                    'bounds': {
                        'x': 24,
                        'y': 16,
                        'width': 320,
                        'height': 72,
                    },
                },
            ],
            'bindings': [
                {
                    'id': uuid7(),
                    'source_id': grid_id,
                    'target_kind': 'table',
                    'target_ref': 'sales.orders',
                    'access_mode': 'read',
                },
                {
                    'id': uuid7(),
                    'source_id': grid_id,
                    'column_id': 'total_amt',
                    'target_kind': 'column',
                    'target_ref': 'sales.orders.total_amt',
                    'access_mode': 'read_write',
                },
                {
                    'id': uuid7(),
                    'source_id': reg_id,
                    'target_kind': 'question',
                    'target_ref': 'question:daily_revenue',
                    'access_mode': 'read',
                },
            ],
            'navigations': [
                {
                    'id': uuid7(),
                    'from_id': btn_id,
                    'to_screen_id': s2,
                    'trigger': 'click',
                    'action': 'overlay',
                    'label': 'Open Customer Detail',
                },
                {
                    'id': uuid7(),
                    'from_id': reg_id,
                    'to_screen_id': s2,
                    'trigger': 'hover',
                    'action': 'navigate',
                },
            ],
        }

        ddn_text, id_map = screen_mesh_to_ddn(mesh)
        self.assertIn(
            f'view "screen_mesh_main" as "{WIREFRAME_PROFILE}"', ddn_text
        )
        self.assertIn(f'view "screen_1" as "{WIREFRAME_PROFILE}"', ddn_text)
        self.assertIn(
            f'view "screen_flow" as "{WIREFRAME_PROFILE}"', ddn_text
        )
        self.assertTrue(all(is_uuid7(v) for v in id_map.values()))

        verified = _verify_ddn_with_runtime({'workbench': ddn_text})
        self.assertTrue(
            verified['workbench']['ok'],
            msg=f"DDN diagnostics: {verified['workbench']['diagnostics']}",
        )

        roundtrip = ddn_to_screen_mesh(ddn_text)['mesh']
        self.assertEqual(roundtrip['name'], 'Order Workbench Mesh')
        self.assertEqual(len(roundtrip['screens']), 2)
        self.assertEqual(len(roundtrip['controls']), 10)
        self.assertEqual(len(roundtrip['regions']), 1)
        self.assertEqual(len(roundtrip['bindings']), 3)
        self.assertEqual(len(roundtrip['navigations']), 2)

    def test_scope_guard_rejects_working_form_and_secret_keys(self):
        """Working form builders and credentials in DDN are rejected."""
        s1 = uuid7()
        for bad_key, bad_val in (
            ('event_handler', 'onClickSave()'),
            ('submit_sql', 'INSERT INTO orders VALUES (1)'),
            ('working_form', True),
            ('password', 'hunter2'),
            ('recipients', ['ops@example.com']),
        ):
            with self.subTest(bad_key=bad_key):
                with self.assertRaises(DesignStoreError):
                    screen_mesh_to_ddn({
                        'name': 'Invalid Mesh',
                        'screens': [{'id': s1, 'name': 'Main'}],
                        'controls': [{
                            'id': uuid7(),
                            'screen_id': s1,
                            'role': 'ui.button',
                            'name': 'Submit',
                            bad_key: bad_val,
                        }],
                    })

    def test_suspect_bindings_on_catalog_rename_and_usage_queries(self):
        """A5/A6: catalog rename marks control/region bindings suspect."""
        with tempfile.TemporaryDirectory() as tmp:
            store = DesignStore(Path(tmp) / 'designs.db')
            proc = StoreDDNProcess(store)
            sync = ScreenMeshSync(store, proc)

            store.register_resource_identity(
                engine='sqlite',
                endpoint_id='ep-1',
                database_target_id='db-1',
                resource_kind='column',
                resource_id='main.customers.email',
            )
            s1 = uuid7()
            inp_id = uuid7()
            created = sync.create_screen_mesh(
                project_id='proj-1',
                key='customer_screen',
                title='Customer Profile Screen',
                actor_id=1,
                mesh={
                    'name': 'Customer Profile Screen',
                    'screens': [{'id': s1, 'name': 'Profile'}],
                    'controls': [{
                        'id': inp_id,
                        'screen_id': s1,
                        'role': 'ui.input',
                        'name': 'Email Address',
                    }],
                    'bindings': [{
                        'id': uuid7(),
                        'source_id': inp_id,
                        'target_kind': 'column',
                        'target_ref': 'main.customers.email',
                        'access_mode': 'read_write',
                        'target_engine': 'sqlite',
                        'target_endpoint_id': 'ep-1',
                        'target_database_target_id': 'db-1',
                    }],
                },
            )
            design_id = created['design']['id']
            self.assertEqual(created['suspect_binding_count'], 0)

            usage = sync.query_usage(
                project_id='proj-1', target_ref='customers.email'
            )
            self.assertEqual(len(usage), 1)
            self.assertEqual(usage[0]['element_name'], 'Email Address')
            self.assertEqual(usage[0]['state'], 'valid')

            # Rename catalog column -> binding becomes suspect and blocks
            # acceptance until confirmed
            renamed = store.record_resource_rename(
                engine='sqlite',
                endpoint_id='ep-1',
                database_target_id='db-1',
                old_resource_id='main.customers.email',
                new_resource_id='main.customers.contact_email',
            )
            self.assertEqual(renamed['suspect_bindings_marked'], 1)

            after_rename = sync.get_screen_mesh(design_id)
            self.assertEqual(after_rename['suspect_binding_count'], 1)
            bnd_row = after_rename['mesh']['bindings'][0]
            self.assertEqual(bnd_row['state'], 'suspect')

            store.advance_status(design_id, 1, 'in_progress', actor_id=1)
            store.advance_status(design_id, 1, 'in_review', actor_id=1)
            with self.assertRaises(DesignStoreConflict):
                proc.accept_with_policy(
                    design_id,
                    1,
                    actor_id=1,
                    has_scratchrobin_permission=True,
                )

            store.confirm_binding(
                bnd_row['store_binding_id'],
                actor_id=1,
                new_target_ref='main.customers.contact_email',
            )
            accepted = proc.accept_with_policy(
                design_id,
                1,
                actor_id=1,
                has_scratchrobin_permission=True,
            )
            self.assertEqual(accepted['version']['status'], 'accepted')

    def test_f3_descriptor_form_import_and_qa_screenshot_manifest(self):
        """F3: discover 122 SR-F forms and import with QA manifest into DDN."""
        forms = list_available_descriptor_forms()
        self.assertEqual(len(forms), 122)
        self.assertTrue(
            all(f['form_reference'].startswith('SR-F-') for f in forms)
        )

        with tempfile.TemporaryDirectory() as tmp:
            store = DesignStore(Path(tmp) / 'designs.db')
            sync = ScreenMeshSync(store)

            qa_png = build_solid_png(width=400, height=260)
            qa_manifest = [{
                'form_reference': 'SR-F-020073',
                'media_type': 'image/png',
                'image_base64': base64.b64encode(qa_png).decode('ascii'),
                'regions': [{
                    'name': 'SQLite Columns Grid Area',
                    'bounds': {
                        'x': 20,
                        'y': 80,
                        'width': 340,
                        'height': 120,
                    },
                }],
            }]

            imported = sync.import_descriptor_form(
                project_id='proj-f3',
                actor_id=1,
                form_reference='SR-F-020073',
                qa_manifest=qa_manifest,
            )
            self.assertEqual(imported['design']['kind'], 'screen')
            self.assertEqual(
                imported['design']['version']['status'], 'draft'
            )
            self.assertEqual(
                imported['mesh']['screens'][0]['form_reference'],
                'SR-F-020073',
            )
            self.assertEqual(len(imported['mesh']['regions']), 1)
            self.assertTrue(
                any(
                    c['role'] == 'ui.tabs'
                    for c in imported['mesh']['controls']
                )
            )
            self.assertTrue(
                any(
                    c['role'] == 'ui.grid' and len(c['columns']) >= 2
                    for c in imported['mesh']['controls']
                )
            )
            self.assertGreater(len(imported['mesh']['bindings']), 3)
            self.assertGreater(
                len(imported['loss_report']['omitted_dynamic_rules']), 0
            )

            ddn_text = imported['design']['version']['ddn_text']
            verified = _verify_ddn_with_runtime({'f3_import': ddn_text})
            self.assertTrue(
                verified['f3_import']['ok'],
                msg=f"DDN diagnostics: {verified['f3_import']['diagnostics']}",
            )

    def test_f4_destructive_screenshot_redaction_purges_unredacted_bytes(self):
        """F4: redacting a screenshot replaces & purges original blob bytes."""
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / 'designs.db'
            store = DesignStore(db_path)
            sync = ScreenMeshSync(store)

            created = sync.create_screen_mesh(
                project_id='proj-f4',
                key='acct_screenshot',
                title='Account Screenshot',
                actor_id=1,
            )
            design_id = created['design']['id']

            # Create PNG with a bright red sensitive stripe at (40, 30, 80, 40)
            sensitive_png = build_solid_png(
                width=200,
                height=120,
                rgb=(240, 244, 248),
                stripe_box={'x': 40, 'y': 30, 'width': 80, 'height': 40},
                stripe_rgb=(222, 17, 34),
            )
            self.assertEqual(
                read_png_pixel_rgb(sensitive_png, 50, 40), (222, 17, 34)
            )

            attached = sync.attach_screenshot(
                design_id,
                actor_id=1,
                data=sensitive_png,
                media_type='image/png',
            )
            old_sha = attached['mesh']['screens'][0]['screenshot_sha256']
            self.assertTrue(old_sha)

            redacted = sync.redact_screenshot(
                design_id,
                actor_id=1,
                regions=[{'x': 35, 'y': 25, 'width': 90, 'height': 50}],
            )
            new_sha = redacted['redaction']['new_sha256']
            self.assertNotEqual(old_sha, new_sha)
            self.assertTrue(redacted['redaction']['purged_original'])

            # New blob has redacted fill inside box and untouched pixel outside
            new_blob = store.get_blob(new_sha)
            self.assertEqual(
                read_png_pixel_rgb(new_blob['bytes'], 50, 40), (15, 23, 42)
            )
            self.assertEqual(
                read_png_pixel_rgb(new_blob['bytes'], 10, 10), (240, 244, 248)
            )

            # Prove old_sha256 row AND raw sensitive_png bytes are absent from
            # designs.db
            conn = sqlite3.connect(str(db_path))
            try:
                old_count = conn.execute(
                    'SELECT COUNT(*) FROM asset_blob WHERE sha256 = ?',
                    (old_sha,),
                ).fetchone()[0]
                self.assertEqual(old_count, 0)
                all_blobs = conn.execute(
                    'SELECT bytes FROM asset_blob'
                ).fetchall()
                for (bval,) in all_blobs:
                    self.assertNotEqual(bytes(bval), sensitive_png)
            finally:
                conn.close()

    def test_http_routes_create_import_save_screenshot_redact_and_usage(self):
        """HTTP routes cover Screen Mesh create, import, redact and usage."""
        with tempfile.TemporaryDirectory() as tmp:
            app = _make_test_app(Path(tmp) / 'designs.db')
            client = app.test_client()

            # 1. List SR-F descriptor forms filtered by engine
            res_forms = client.get(
                '/cdeadmin/api/ui/descriptor-forms?engine=sqlite'
            )
            self.assertEqual(res_forms.status_code, 200)
            sqlite_forms = res_forms.get_json()['data']
            self.assertGreaterEqual(len(sqlite_forms), 5)

            # 2. Import SQLite table descriptor form via HTTP
            res_imp = client.post(
                '/cdeadmin/api/projects/p1/designs',
                json={
                    'mode': 'import_descriptor_mesh',
                    'engine': 'sqlite',
                    'form_key': 'table',
                },
            )
            self.assertEqual(res_imp.status_code, 200)
            imp_data = res_imp.get_json()['data']
            design_id = imp_data['design']['id']

            # 3. Upload screenshot via base64 JSON
            png_bytes = build_solid_png(
                width=160,
                height=100,
                stripe_box={'x': 10, 'y': 10, 'width': 60, 'height': 30},
            )
            res_up = client.post(
                f'/cdeadmin/api/projects/p1/designs/{design_id}'
                f'/screen-mesh/screenshot',
                json={
                    'image_base64': base64.b64encode(png_bytes).decode(
                        'ascii'
                    ),
                    'media_type': 'image/png',
                },
            )
            self.assertEqual(res_up.status_code, 200)
            old_sha = (
                res_up.get_json()['data']['mesh']['screens'][0][
                    'screenshot_sha256'
                ]
            )

            res_blob1 = client.get(
                f'/cdeadmin/api/projects/p1/designs/{design_id}'
                f'/blobs/{old_sha}'
            )
            self.assertEqual(res_blob1.status_code, 200)
            self.assertEqual(res_blob1.data, png_bytes)

            # 4. Redact screenshot via HTTP -> old blob returns 404, new 200
            res_red = client.post(
                f'/cdeadmin/api/projects/p1/designs/{design_id}'
                f'/screen-mesh/redact',
                json={
                    'regions': [{'x': 10, 'y': 10, 'width': 60, 'height': 30}]
                },
            )
            self.assertEqual(res_red.status_code, 200)
            new_sha = res_red.get_json()['data']['redaction']['new_sha256']

            res_old_gone = client.get(
                f'/cdeadmin/api/projects/p1/designs/{design_id}'
                f'/blobs/{old_sha}'
            )
            self.assertEqual(res_old_gone.status_code, 404)

            res_new_ok = client.get(
                f'/cdeadmin/api/projects/p1/designs/{design_id}'
                f'/blobs/{new_sha}'
            )
            self.assertEqual(res_new_ok.status_code, 200)
            self.assertEqual(
                read_png_pixel_rgb(res_new_ok.data, 20, 20), (15, 23, 42)
            )

            # 5. Query usage across project meshes
            res_usage = client.get(
                '/cdeadmin/api/projects/p1/screen-mesh/usage'
                '?target_ref=sqlite.table'
            )
            self.assertEqual(res_usage.status_code, 200)
            self.assertGreater(len(res_usage.get_json()['data']), 0)


if __name__ == '__main__':
    unittest.main()

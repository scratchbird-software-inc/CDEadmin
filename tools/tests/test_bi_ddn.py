##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Regression tests for BI Phase 1 & Phase 2 DDN formatters, device fleet & kiosk."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

from flask import Flask

from pgadmin.cdeadmin.design_store import (
    BIDesignSync,
    DesignStore,
    DesignStoreError,
    DesignStoreForbidden,
    ddn_to_question,
    default_dashboard_model,
    default_question_model,
    init_routes_app,
    question_to_ddn,
)
from pgadmin.cdeadmin.design_store.bi_ddn import normalize_visualization_format
from pgadmin.cdeadmin.design_store.bi_extensions import (
    manage_bi_device_tokens,
    render_bi_kiosk_html_response,
)


def _verify_ddn_zero_diagnostics(documents: dict[str, str]) -> dict[str, list]:
    """Run bundled ddn-verifier.js via stdin and return ALL diagnostics."""
    repo_root = Path(__file__).resolve().parents[2]
    verifier = (
        repo_root
        / 'web/pgadmin/static/vendor/ddn/current/complete/ddn-verifier.js'
    )
    script = (
        "import { pathToFileURL } from 'node:url';\n"
        "import fs from 'node:fs';\n"
        "const mod = await import(pathToFileURL(process.argv[1]).href);\n"
        "const verifier = mod.createVerifier(\n"
        "  mod.createCompleteRuntimeOptions()\n"
        ");\n"
        "const docs = JSON.parse(fs.readFileSync(0, 'utf8'));\n"
        "const out = {};\n"
        "for (const [k, text] of Object.entries(docs)) {\n"
        "  const res = verifier.verifySources({ 'design.ddn': text });\n"
        "  out[k] = res.diagnostics || [];\n"
        "}\n"
        "verifier.destroy();\n"
        "process.stdout.write(JSON.stringify(out));\n"
    )
    proc = subprocess.run(
        ['node', '--input-type=module', '-e', script, str(verifier)],
        input=json.dumps(documents),
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(proc.stdout)


class BIDDNPhase1And2Tests(unittest.TestCase):
    def test_visualization_format_roundtrip_zero_ddn_diagnostics(self):
        docs: dict[str, str] = {}
        cases = [
            (
                'currency_eur',
                'bar',
                {
                    'number_format': 'currency',
                    'currency_code': 'EUR',
                    'decimals': 2,
                    'date_grain': 'month',
                    'x_axis_label': 'Order Month',
                    'y_axis_label': 'Net Revenue (€)',
                    'show_accessible_table_default': True,
                },
            ),
            (
                'percent_zero',
                'kpi',
                {
                    'number_format': 'percent',
                    'currency_code': 'USD',
                    'decimals': 1,
                    'date_grain': 'quarter',
                    'x_axis_label': 'Quarter',
                    'y_axis_label': 'Conversion Rate',
                    'show_accessible_table_default': False,
                },
            ),
            (
                'compact_cad',
                'funnel',
                {
                    'number_format': 'compact',
                    'currency_code': 'CAD',
                    'decimals': 0,
                    'date_grain': 'year',
                    'x_axis_label': 'Stage',
                    'y_axis_label': 'Accounts',
                    'show_accessible_table_default': True,
                },
            ),
            (
                'standard_gbp',
                'scatter',
                {
                    'number_format': 'standard',
                    'currency_code': 'GBP',
                    'decimals': 4,
                    'date_grain': 'day',
                    'x_axis_label': 'Day',
                    'y_axis_label': 'Latency',
                    'show_accessible_table_default': False,
                },
            ),
        ]
        for key, viz_type, fmt in cases:
            q = default_question_model(
                name=f'Formatted {key}',
                visualization={'type': viz_type},
                visualization_format=fmt,
                preview_rows=[['2026-10', 12500.75], ['2026-11', 18400.25]],
            )
            self.assertEqual(q['visualization_format'], fmt)
            ddn_text, id_map = question_to_ddn(q)
            parsed = ddn_to_question(ddn_text)
            self.assertEqual(parsed['question']['visualization_format'], fmt)
            self.assertEqual(parsed['question'], q)
            self.assertTrue(id_map)
            docs[key] = ddn_text

        diagnostics = _verify_ddn_zero_diagnostics(docs)
        for key, diags in diagnostics.items():
            self.assertEqual(
                diags,
                [],
                f'Expected 0 DDN diagnostics for {key}, got {diags}',
            )

        with self.assertRaises(DesignStoreError):
            normalize_visualization_format({'number_format': 'scientific'})
        with self.assertRaises(DesignStoreError):
            normalize_visualization_format({'currency_code': 'JPY'})
        with self.assertRaises(DesignStoreError):
            normalize_visualization_format({'decimals': 5})
        with self.assertRaises(DesignStoreError):
            normalize_visualization_format({'decimals': True})
        with self.assertRaises(DesignStoreError):
            normalize_visualization_format({'date_grain': 'decade'})

    def test_device_token_fleet_persistence_and_kiosk_viewer_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = f'{tmp}/designs.db'
            app = Flask(__name__)
            app.secret_key = 'test-bi-kiosk-fleet-secret'
            app.config['TESTING'] = True
            app.config['LOGIN_DISABLED'] = True
            app.config['CDEADMIN_DESIGN_STORE_PATH'] = db_path
            store: DesignStore = init_routes_app(app)
            sync = BIDesignSync(store, token_secret=app.secret_key)

            q_created = sync.create_question(
                project_id='p1',
                key='regional-sales',
                title='Regional Sales',
                actor_id=1,
                question=default_question_model(
                    name='Regional Sales',
                    visualization={'type': 'bar'},
                    visualization_format={
                        'number_format': 'currency',
                        'currency_code': 'USD',
                        'decimals': 2,
                        'date_grain': 'month',
                        'x_axis_label': 'Region',
                        'y_axis_label': 'Sales ($)',
                        'show_accessible_table_default': True,
                    },
                    preview_rows=[['North', 4200.5], ['West', 3150.0]],
                ),
            )
            q_id = q_created['design']['id']
            store.advance_status(q_id, 1, 'in_review', actor_id=1)
            sync.accept_bi_design(q_id, 1, actor_id=1, authorized=True)

            d_created = sync.create_dashboard(
                project_id='p1',
                key='wallboard-sales',
                title='Sales Wallboard',
                actor_id=1,
                dashboard=default_dashboard_model(
                    name='Sales Wallboard',
                    cards=[
                        {
                            'id': 'sales_card',
                            'tab_id': 'main',
                            'type': 'question',
                            'title': 'Sales by Region',
                            'question': {
                                'question_design_id': q_id,
                                'pinned_version': 1,
                            },
                            'visualization': {'type': 'bar'},
                        },
                    ],
                    action_buttons=[
                        {
                            'id': 'approve_order',
                            'label': 'Approve Order',
                            'operation_kind': 'update_row',
                            'capability_id': 'table.update_row',
                            'risk_class': 'write',
                            'target_endpoint_id': 'ep-pg',
                            'target_relation': ['public', 'orders'],
                            'key_columns': ['order_id'],
                            'parameter_bindings': [
                                {
                                    'name': 'order_id',
                                    'column': 'order_id',
                                    'source': 'prompt',
                                    'type': 'integer',
                                    'required': True,
                                },
                                {
                                    'name': 'status',
                                    'column': 'status',
                                    'source': 'literal',
                                    'default': 'approved',
                                },
                            ],
                        },
                    ],
                ),
            )
            d_id = d_created['design']['id']
            store.advance_status(d_id, 1, 'in_review', actor_id=1)
            sync.accept_bi_design(d_id, 1, actor_id=1, authorized=True)
            pub = sync.publish_to_dashboard_server(
                d_id,
                publisher_user_id=1,
                reviewer_id=1,
                locked_filters={'region': ['North', 'West']},
            )
            pub_id = pub['id']

            # Unauthorized mint must raise DesignStoreForbidden
            with self.assertRaises(DesignStoreForbidden):
                manage_bi_device_tokens(
                    store,
                    None,
                    design_id=d_id,
                    actor_id=1,
                    method='POST',
                    payload={'action': 'mint', 'device_label': 'unauth-tv'},
                    authorized=False,
                    app=app,
                )

            client = app.test_client()

            # 1. Initial fleet list is empty
            list_res = client.get(
                f'/cdeadmin/api/projects/p1/designs/{d_id}/bi/devices'
            )
            self.assertEqual(list_res.status_code, 200)
            self.assertEqual(list_res.get_json()['data']['tokens'], [])

            # 2. Mint device token via API
            mint_res = client.post(
                f'/cdeadmin/api/projects/p1/designs/{d_id}/bi/devices',
                json={
                    'action': 'mint',
                    'publication_id': pub_id,
                    'device_label': 'lobby-wallboard-1',
                    'locked_filters': {'region': ['North', 'West']},
                },
            )
            self.assertEqual(mint_res.status_code, 200)
            mint_data = mint_res.get_json()['data']
            raw_token = mint_data['device_token']
            token_id = mint_data['token_record']['token_id']
            self.assertEqual(mint_data['token_record']['status'], 'active')
            self.assertIsNone(mint_data['token_record']['last_used_at'])
            self.assertIn(
                f'/cdeadmin/designs/kiosk/{pub_id}#token={raw_token}',
                mint_data['kiosk_url'],
            )

            # Verify raw token is NEVER stored in SQLite, only SHA-256 hash
            raw_conn = sqlite3.connect(db_path)
            try:
                reg_rows = raw_conn.execute(
                    'SELECT token_id, token_hash FROM bi_device_token_registry'
                ).fetchall()
                self.assertEqual(len(reg_rows), 1)
                expected_hash = hashlib.sha256(
                    raw_token.encode('utf-8')
                ).hexdigest()
                self.assertEqual(reg_rows[0][1], expected_hash)
                dump_text = '\n'.join(raw_conn.iterdump())
                self.assertNotIn(raw_token, dump_text)
            finally:
                raw_conn.close()

            # 3. Kiosk GET with no query/header token serves #token= shell
            shell_res = client.get(f'/cdeadmin/designs/kiosk/{pub_id}')
            self.assertEqual(shell_res.status_code, 200)
            shell_html = shell_res.get_data(as_text=True)
            self.assertIn('SR-F-030034', shell_html)
            self.assertIn('window.location.hash', shell_html)

            # 4. Kiosk GET with valid narrowing filter succeeds & stamps SR-F-030034
            valid_res = client.get(
                f'/cdeadmin/designs/kiosk/{pub_id}?filter_region=North',
                headers={'Authorization': f'Bearer {raw_token}'},
            )
            self.assertEqual(valid_res.status_code, 200)
            valid_html = valid_res.get_data(as_text=True)
            self.assertIn('SR-F-030034', valid_html)
            self.assertIn('Sales Wallboard', valid_html)
            self.assertIn('lobby-wallboard-1', valid_html)
            self.assertIn('Accessible Data Table', valid_html)
            self.assertIn('$4,200.50', valid_html)
            # Zero write-back or edit buttons in kiosk view
            self.assertNotIn('Approve Order', valid_html)

            # Verify last_used_at was updated on view
            after_view = client.get(
                f'/cdeadmin/api/projects/p1/designs/{d_id}/bi/devices'
            ).get_json()['data']['tokens']
            self.assertEqual(len(after_view), 1)
            self.assertIsNotNone(after_view[0]['last_used_at'])

            # 5. Kiosk GET attempting to widen filter ('East') returns 403
            widen_res = client.get(
                f'/cdeadmin/designs/kiosk/{pub_id}?filter_region=East',
                headers={'X-ScratchRobin-Device-Token': raw_token},
            )
            self.assertEqual(widen_res.status_code, 403)
            self.assertIn('SR-F-030034', widen_res.get_data(as_text=True))

            # 6. Revoke token and confirm status=='revoked' and kiosk returns 403
            rev_res = client.post(
                f'/cdeadmin/api/projects/p1/designs/{d_id}/bi/devices',
                json={'action': 'revoke', 'token_id': token_id},
            )
            self.assertEqual(rev_res.status_code, 200)
            rev_data = rev_res.get_json()['data']
            self.assertEqual(rev_data['revoked']['status'], 'revoked')
            self.assertIsNotNone(rev_data['revoked']['revoked_at'])

            revoked_kiosk = render_bi_kiosk_html_response(
                store,
                None,
                publication_id=pub_id,
                query_args={'token': raw_token},
                headers={},
                app=app,
            )
            self.assertEqual(revoked_kiosk[1], 403)

            revoked_http = client.get(
                f'/cdeadmin/designs/kiosk/{pub_id}?token={raw_token}'
            )
            self.assertEqual(revoked_http.status_code, 403)

            # 7. Collector read-only panel handles invalid/unregistered target gracefully
            class _InvalidTargetHost:
                def snapshot(self, _owner, _sid, _target):
                    raise ValueError('Invalid PostgreSQL database target')

            dash_col = sync.create_dashboard(
                project_id='p1',
                key='ops-collector-dash',
                title='Ops Collector Dash',
                actor_id=1,
                dashboard=default_dashboard_model(
                    name='Ops Collector Dash',
                    cards=[
                        {
                            'id': 'c_col',
                            'tab_id': 'main',
                            'type': 'metric_panel',
                            'title': 'Ops Collector',
                            'metric_panel': {
                                'snapshot_mode': 'collector_read_only',
                                'collector_binding': {
                                    'engine': 'postgresql',
                                    'server_id': 99,
                                    'target_id': 'ops-db-01',
                                    'metric_group': 'summary',
                                    'metric_keys': ['tps'],
                                    'freshness_budget_seconds': 60,
                                },
                            },
                        }
                    ],
                ),
            )
            missing_snap = sync.read_collector_metric_panel(
                dash_col['design']['id'],
                card_id='c_col',
                actor_id=1,
                monitoring_hosts={'postgresql': _InvalidTargetHost()},
            )
            self.assertEqual(missing_snap['collector_state'], 'unavailable')
            self.assertEqual(missing_snap['freshness_status'], 'target_not_found')
            self.assertFalse(missing_snap['collector_mutated'])


if __name__ == '__main__':
    unittest.main()

##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Verification of multi-engine Server, Database, and Table Dashboards,
Rich Object Properties, churn-protected Tier-3 Deep Statistics, and
encrypted historic time-series storage in FirebirdSQL Embedded
`UserConfigurationDatabase`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import duckdb
import pytest
from flask import Flask

import pgadmin.cdeadmin.user_config_db.service as ucfg_service
from pgadmin.cdeadmin.user_config_db import UserConfigurationDatabase
from pgadmin.cdeadmin.workspace.object_dashboard_host import (
    ObjectDashboardHost,
    init_app as init_object_dashboard,
)


def test_historic_metrics_rollups_epoch_rates_encryption_and_retention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv('PGADMIN_TESTING_MODE', raising=False)
    fdb_path = tmp_path / 'metrics_vault.fdb'

    ucfg = UserConfigurationDatabase(db_path=fdb_path, kdf_iterations=12_000)
    user = ucfg.unlock_and_authenticate('dba', 'StrongPass!42', 'VaultSecretKey#99')
    uid = user['user_id']

    # Verify default retention policy (24h raw, 30d 5m, 365d 1h)
    default_ret = ucfg.get_metrics_retention_policy(uid)
    assert default_ret == {'raw_hours': 24, 'rollup_5m_days': 30, 'rollup_1h_days': 365}

    base_ts = 1_795_500_000_000  # aligned epoch ms

    # Sample 1: initial counter baseline + gauge observation
    r1 = ucfg.record_object_metric_observations(
        user_id=uid,
        engine_id='postgresql',
        server_id=10,
        database_target_id='sales_db',
        object_kind='database',
        object_key='database:10:sales_db',
        observed_at_ms=base_ts,
        epoch_id='postmaster-boot-1',
        observations=[
            {
                'metric_key': 'sessions.total',
                'label': 'Active Connections',
                'group': 'sessions',
                'kind': 'gauge',
                'unit': 'count',
                'value': 14,
            },
            {
                'metric_key': 'tx.commits_per_sec',
                'label': 'Commits / sec',
                'group': 'transactions',
                'kind': 'counter_rate',
                'unit': 'per_sec',
                'raw_counter': 1000,
            },
            {
                'metric_key': 'secret_canary_gauge',
                'label': 'PlaintextCanaryLabel987654',
                'group': 'memory',
                'kind': 'gauge',
                'unit': 'bytes',
                'value': 987654321,
            },
        ],
    )
    # First counter sample sets baseline without inventing a bogus spike
    assert r1['recorded_count'] == 2
    assert 'tx.commits_per_sec' not in r1['computed_rates']

    # Sample 2 (+10s, same epoch): 250 new commits -> 25.0 commits/sec!
    r2 = ucfg.record_object_metric_observations(
        user_id=uid,
        engine_id='postgresql',
        server_id=10,
        database_target_id='sales_db',
        object_kind='database',
        object_key='database:10:sales_db',
        observed_at_ms=base_ts + 10_000,
        epoch_id='postmaster-boot-1',
        observations=[
            {
                'metric_key': 'sessions.total',
                'label': 'Active Connections',
                'group': 'sessions',
                'kind': 'gauge',
                'unit': 'count',
                'value': 22,
            },
            {
                'metric_key': 'tx.commits_per_sec',
                'label': 'Commits / sec',
                'group': 'transactions',
                'kind': 'counter_rate',
                'unit': 'per_sec',
                'raw_counter': 1250,
            },
        ],
    )
    assert pytest.approx(r2['computed_rates']['tx.commits_per_sec'], rel=1e-4) == 25.0

    # Sample 3 (+20s, NEW server restart epoch with lower counter 40): NO negative spike!
    r3 = ucfg.record_object_metric_observations(
        user_id=uid,
        engine_id='postgresql',
        server_id=10,
        database_target_id='sales_db',
        object_kind='database',
        object_key='database:10:sales_db',
        observed_at_ms=base_ts + 20_000,
        epoch_id='postmaster-boot-2',
        observations=[
            {
                'metric_key': 'tx.commits_per_sec',
                'label': 'Commits / sec',
                'group': 'transactions',
                'kind': 'counter_rate',
                'unit': 'per_sec',
                'raw_counter': 40,
            },
        ],
    )
    assert 'tx.commits_per_sec' not in r3['computed_rates']

    # Query 1h RAW window, 30d 5M rollup window, and 365d 1H rollup window
    h_raw = ucfg.query_object_metric_history(
        user_id=uid,
        object_kind='database',
        object_key='database:10:sales_db',
        window='1h',
        now_ms=base_ts + 30_000,
    )
    assert h_raw['resolution'] == 'raw'
    by_key_raw = {s['metric_key']: s for s in h_raw['series']}
    assert [p['value'] for p in by_key_raw['sessions.total']['points']] == [14.0, 22.0]
    assert [p['value'] for p in by_key_raw['tx.commits_per_sec']['points']] == [25.0]

    h_5m = ucfg.query_object_metric_history(
        user_id=uid,
        object_kind='database',
        object_key='database:10:sales_db',
        window='30d',
        now_ms=base_ts + 30_000,
    )
    assert h_5m['resolution'] == '5m'
    sess_5m = next(s for s in h_5m['series'] if s['metric_key'] == 'sessions.total')
    assert len(sess_5m['points']) == 1
    assert sess_5m['points'][0]['min'] == 14.0
    assert sess_5m['points'][0]['max'] == 22.0
    assert sess_5m['points'][0]['value'] == 18.0  # exact mean of 14 and 22

    h_1h = ucfg.query_object_metric_history(
        user_id=uid,
        object_kind='database',
        object_key='database:10:sales_db',
        window='365d',
        now_ms=base_ts + 30_000,
    )
    assert h_1h['resolution'] == '1h'

    # Advance 26 hours (> 24h raw retention): raw sample at base_ts is pruned,
    # while 5m and 1h rollups retain the historical bucket!
    later_ts = base_ts + 26 * 3_600_000
    ucfg.record_object_metric_observations(
        user_id=uid,
        engine_id='postgresql',
        server_id=10,
        database_target_id='sales_db',
        object_kind='database',
        object_key='database:10:sales_db',
        observed_at_ms=later_ts,
        epoch_id='postmaster-boot-2',
        observations=[
            {
                'metric_key': 'sessions.total',
                'label': 'Active Connections',
                'group': 'sessions',
                'kind': 'gauge',
                'unit': 'count',
                'value': 30,
            }
        ],
    )
    raw_after_prune = ucfg.query_object_metric_history(
        user_id=uid,
        object_kind='database',
        object_key='database:10:sales_db',
        window='24h',
        now_ms=later_ts,
    )
    sess_raw_after = next(s for s in raw_after_prune['series'] if s['metric_key'] == 'sessions.total')
    assert [p['value'] for p in sess_raw_after['points']] == [30.0]

    rollup_after_prune = ucfg.query_object_metric_history(
        user_id=uid,
        object_kind='database',
        object_key='database:10:sales_db',
        window='30d',
        now_ms=later_ts,
    )
    sess_30d_after = next(s for s in rollup_after_prune['series'] if s['metric_key'] == 'sessions.total')
    assert len(sess_30d_after['points']) == 2  # both yesterday's bucket and today's bucket preserved!

    # Verify encryption at rest in .fdb file
    raw_bytes = fdb_path.read_bytes()
    assert b'PlaintextCanaryLabel987654' not in raw_bytes
    assert b'987654321' not in raw_bytes


def test_sqlite_and_duckdb_dashboards_deep_refresh_and_flask_endpoints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    fdb_path = tmp_path / 'dashboard_routes.fdb'
    ucfg = UserConfigurationDatabase(db_path=fdb_path, kdf_iterations=12_000)
    ucfg.unlock_and_authenticate('admin', 'AdminPass!1', 'VaultKey!2026')
    monkeypatch.setattr(
        'pgadmin.cdeadmin.workspace.object_dashboard_host.get_user_config_db',
        lambda: ucfg,
    )

    # Create a real SQLite database with a table comment preserved in sqlite_schema and rows
    sqlite_file = tmp_path / 'inventory.sqlite'
    with sqlite3.connect(sqlite_file) as con:
        con.execute(
            'CREATE TABLE assets (\n'
            '  -- Core equipment inventory table\n'
            '  id INTEGER PRIMARY KEY, tag TEXT NOT NULL, status TEXT\n'
            ')'
        )
        con.executemany(
            'INSERT INTO assets (tag, status) VALUES (?, ?)',
            [('PUMP-01', 'active'), ('VALVE-02', 'maintenance'), ('METER-03', 'active')],
        )
        con.commit()

    # Create a real DuckDB database with database/table comments and data
    duck_file = tmp_path / 'analytics.duckdb'
    with duckdb.connect(str(duck_file)) as dcon:
        dcon.execute('CREATE TABLE ledger (account VARCHAR, amount DOUBLE)')
        dcon.execute("COMMENT ON TABLE ledger IS 'General ledger postings'")
        dcon.execute("INSERT INTO ledger VALUES ('1000-CASH', 1250.50), ('2000-AP', -420.00)")

    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['SERVER_MODE'] = False
    host = init_object_dashboard(app, workspace_service=None)

    def make_sqlite_runner():
        con = sqlite3.connect(sqlite_file)
        con.row_factory = sqlite3.Row

        def run_sql(sql: str, params: Any = None, max_rows: int = 100):
            cur = con.execute(sql, params or ())
            rows = cur.fetchmany(max_rows)
            return [dict(r) for r in rows]

        return run_sql, con.close, None, None

    def make_duckdb_runner():
        dcon = duckdb.connect(str(duck_file), read_only=True)

        def run_sql(sql: str, params: Any = None, max_rows: int = 100):
            rel = dcon.execute(sql)
            cols = [d[0] for d in (rel.description or [])]
            return [dict(zip(cols, r)) for r in rel.fetchmany(max_rows)]

        return run_sql, dcon.close, None, None

    # 1. Test SQLite Database + Table Tier-1 Snapshot & Tier-3 Deep Refresh via Flask Client
    monkeypatch.setattr(
        host,
        '_resolve_SqliteOrDuck',
        None,
        raising=False,
    )
    monkeypatch.setattr(
        'pgadmin.cdeadmin.workspace.object_dashboard_host._resolve_engine_info',
        lambda srv, fallback_engine_id='': {
            'engine_id': fallback_engine_id or 'sqlite',
            'engine_label': 'DuckDB' if fallback_engine_id == 'duckdb' else 'SQLite',
            'profile_id': f'{fallback_engine_id or "sqlite"}-native',
            'workflow': 'provider_endpoint',
            'route_cfg': {'path': str(duck_file if fallback_engine_id == 'duckdb' else sqlite_file)},
            'verified': True,
            'verified_version': '3.53.0',
        },
    )
    monkeypatch.setattr(
        host,
        '_open_ephemeral_provider_runner',
        lambda srv, db_target: (
            make_duckdb_runner() if db_target == 'duck_target' else make_sqlite_runner()
        ),
    )

    client = app.test_client()

    # SQLite Database Snapshot (Tier 1: NO deep stats cached yet!)
    resp = client.get(
        '/cdeadmin/api/object_dashboard/snapshot',
        query_string={
            'node_type': 'cde_database_target',
            'engine_id': 'sqlite',
            'server_id': 5,
            'database_target_id': 'sqlite_target',
            'object_name': 'inventory',
            'window': '1h',
        },
    )
    assert resp.status_code == 200
    snap = resp.get_json()
    assert snap['object_identity']['connected'] is True
    assert any(k['id'] == 'db_size' for k in snap['kpis'])
    assert snap['ddn']['scene'] is not None
    assert snap['deep_stats']['cached'] is None  # churn-protected!
    assert len(snap['history']['series']) >= 1

    # Explicit Tier-3 Deep Refresh on SQLite Table (`COUNT(*)` + `dbstat`)
    deep_resp = client.post(
        '/cdeadmin/api/object_dashboard/deep_refresh',
        json={
            'node_type': 'cde_resource',
            'object_kind': 'table',
            'engine_id': 'sqlite',
            'server_id': 5,
            'database_target_id': 'sqlite_target',
            'object_name': 'assets',
            'window': '1h',
        },
    )
    assert deep_resp.status_code == 200
    deep_json = deep_resp.get_json()
    assert deep_json['deep_stats']['cached']['stats']['exact_row_count'] == 3

    # Subsequent Table Snapshot returns both comment AND cached deep stats!
    tbl_snap_resp = client.get(
        '/cdeadmin/api/object_dashboard/snapshot',
        query_string={
            'node_type': 'cde_resource',
            'object_kind': 'table',
            'engine_id': 'sqlite',
            'server_id': 5,
            'database_target_id': 'sqlite_target',
            'object_name': 'assets',
        },
    )
    tbl_snap = tbl_snap_resp.get_json()
    assert 'Core equipment inventory table' in tbl_snap['comment']['text']
    assert tbl_snap['deep_stats']['cached']['stats']['exact_row_count'] == 3

    # 2. DuckDB Table Snapshot, Rich Properties & Deep Refresh (`SUMMARIZE` + `COUNT(*)`)
    duck_snap = client.get(
        '/cdeadmin/api/object_dashboard/snapshot',
        query_string={
            'node_type': 'cde_resource',
            'object_kind': 'table',
            'engine_id': 'duckdb',
            'server_id': 6,
            'database_target_id': 'duck_target',
            'object_name': 'ledger',
        },
    ).get_json()
    assert duck_snap['comment']['text'] == 'General ledger postings'

    duck_deep = client.post(
        '/cdeadmin/api/object_dashboard/deep_refresh',
        json={
            'node_type': 'cde_resource',
            'object_kind': 'table',
            'engine_id': 'duckdb',
            'server_id': 6,
            'database_target_id': 'duck_target',
            'object_name': 'ledger',
        },
    ).get_json()
    assert duck_deep['deep_stats']['cached']['stats']['exact_row_count'] == 2
    assert any(
        t['id'] == 'duckdb_summarize'
        for t in duck_deep['deep_stats']['cached']['stats']['tables']
    )

    duck_props = client.get(
        '/cdeadmin/api/object_dashboard/properties',
        query_string={
            'node_type': 'cde_resource',
            'object_kind': 'table',
            'engine_id': 'duckdb',
            'server_id': 6,
            'database_target_id': 'duck_target',
            'object_name': 'ledger',
        },
    ).get_json()
    assert duck_props['comment']['text'] == 'General ledger postings'
    assert duck_props['ddl']['available'] is True
    assert 'CREATE TABLE ledger' in duck_props['ddl']['sql']

    # 3. Preferences GET & POST round-trip in Firebird Embedded Vault
    pref_post = client.post(
        '/cdeadmin/api/object_dashboard/preferences',
        json={
            'dashboard': {'show_ddn_topology': False, 'default_window': '30d'},
            'properties': {'show_empty_attributes': True},
            'retention_policy': {'raw_hours': 48, 'rollup_5m_days': 60, 'rollup_1h_days': 730},
        },
    )
    assert pref_post.status_code == 200
    pref_json = pref_post.get_json()
    assert pref_json['dashboard']['show_ddn_topology'] is False
    assert pref_json['dashboard']['default_window'] == '30d'
    assert pref_json['properties']['show_empty_attributes'] is True
    assert pref_json['retention_policy'] == {
        'raw_hours': 48,
        'rollup_5m_days': 60,
        'rollup_1h_days': 730,
    }

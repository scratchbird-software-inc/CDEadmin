##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""End-to-end verification of the encrypted FirebirdSQL Embedded
UserConfigurationDatabase, 3-field login/unlock gate, multi-user isolation,
per-column display preferences, table/view revisit restore, and templates.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from pgadmin.cdeadmin.user_config_db import (
    UserConfigAuthError,
    UserConfigKeyError,
    UserConfigLockedError,
    UserConfigurationDatabase,
)
from pgadmin.cdeadmin.workspace.data_surface_host import (
    DataSurfaceHostService,
    SurfaceLayoutStore,
)
from pgadmin.cdeadmin.workspace.sql_surface_host import (
    QuickQueryStore,
    SqlSnippetsStore,
    SqlSurfaceHostService,
)


def test_firebird_embedded_vault_encryption_key_enforcement_and_multi_user(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv('PGADMIN_TESTING_MODE', raising=False)
    fdb_path = tmp_path / 'user_configuration.fdb'

    ucfg = UserConfigurationDatabase(db_path=fdb_path, kdf_iterations=12_000)
    assert ucfg.engine_name == 'firebird-embedded'
    assert ucfg.is_vault_initialized() is False
    assert ucfg.is_unlocked() is False

    with pytest.raises(UserConfigLockedError):
        ucfg.get_specific_layout(1, 'data-edit-surface', '1:default:public.orders')

    # First-time provisioning creates encrypted Firebird database + initial user
    alice = ucfg.unlock_and_authenticate('alice', 'AlicePass!99', 'MasterDbKey#2026')
    assert alice['vault_created'] is True
    assert alice['user_id'] == 1
    assert alice['username'] == 'alice'
    assert fdb_path.is_file()
    assert ucfg.is_vault_initialized() is True
    assert ucfg.is_unlocked() is True

    # Provision second user in shared configuration database
    bob = ucfg.create_or_update_user('bob', 'BobPass!88', roles=['Standard'])
    assert bob['user_id'] == 2

    # Save connection parameters, preferences, per-column display layout, template, and metrics
    ucfg.save_connection_parameters(
        alice['user_id'],
        'server:10',
        'postgresql',
        {'host': 'db-prod.internal', 'port': 5432, 'password_secret': 'top-secret-pg'},
    )
    ucfg.save_user_preference(alice['user_id'], 'sqleditor', 'tab_size', 4)
    ucfg.save_specific_layout(
        alice['user_id'],
        'data-edit-surface',
        '10:sales:public.customers',
        {
            'displayMode': 'grid',
            'gridColPrefs': {
                'notes': {
                    'font': 'serif',
                    'fontSize': 'md',
                    'color': '#1d4ed8',
                    'bgColor': '#eff6ff',
                    'hAlign': 'left',
                    'vAlign': 'top',
                    'wrapMode': 'clamp',
                    'maxWrapLines': 5,
                    'minWidth': 140,
                    'maxWidth': 420,
                    'width': 500,  # clamped to maxWidth=420
                }
            },
        },
    )
    ucfg.save_specific_layout(
        bob['user_id'],
        'data-edit-surface',
        '10:sales:public.customers',
        {
            'displayMode': 'grid',
            'gridColPrefs': {'notes': {'font': 'mono', 'hAlign': 'right'}},
        },
    )
    tpl = ucfg.save_template(
        alice['user_id'],
        'data-edit-surface',
        'Compact Financial Grid',
        {
            'gridColPrefs': {
                'amount': {
                    'font': 'mono',
                    'color': '#047857',
                    'hAlign': 'right',
                    'minWidth': 110,
                    'maxWidth': 220,
                }
            }
        },
    )
    ucfg.save_metrics_history_record(
        record_id='metric:srv10:1',
        user_id=alice['user_id'],
        record_kind='server_metric',
        server_id=10,
        engine_id='postgresql',
        payload={'tps': 1482.5, 'active_backends': 19},
    )

    # Inspect raw Firebird tables directly to prove payloads are AES-256-GCM ciphertext
    with ucfg._open_or_create_connection(create_if_missing=False) as raw_con:
        cur = raw_con.cursor()
        cur.execute('SELECT PARAMS_ENC FROM UCFG_CONNECTIONS')
        raw_conn_ct = str(cur.fetchone()[0])
        assert raw_conn_ct.startswith('enc:v1:')
        assert 'top-secret-pg' not in raw_conn_ct
        assert 'db-prod.internal' not in raw_conn_ct

        cur.execute('SELECT LAYOUT_ENC FROM UCFG_OBJECT_DISPLAY_LAYOUTS')
        raw_layout_ct = str(cur.fetchone()[0])
        assert raw_layout_ct.startswith('enc:v1:')
        assert '#1d4ed8' not in raw_layout_ct

    # Lock and reopen in a fresh instance: wrong database_key MUST fail
    ucfg.lock()
    assert ucfg.is_unlocked() is False

    reopened = UserConfigurationDatabase(db_path=fdb_path, kdf_iterations=12_000)
    with pytest.raises(UserConfigKeyError, match='Invalid database key'):
        reopened.unlock_and_authenticate('alice', 'AlicePass!99', 'WrongDatabaseKey!')

    # Valid database_key + wrong user password MUST fail
    with pytest.raises(UserConfigAuthError, match='Incorrect user name or password'):
        reopened.unlock_and_authenticate('alice', 'WrongUserPass!', 'MasterDbKey#2026')

    # Valid credentials for both Alice and Bob unlock and isolate user preferences/layouts
    auth_alice = reopened.unlock_and_authenticate(
        'alice', 'AlicePass!99', 'MasterDbKey#2026'
    )
    assert auth_alice['vault_created'] is False
    alice_layout = reopened.get_specific_layout(
        alice['user_id'], 'data-edit-surface', '10:sales:public.customers'
    )
    assert alice_layout is not None
    notes_prefs = alice_layout['gridColPrefs']['notes']
    assert notes_prefs == {
        'font': 'serif',
        'fontSize': 'md',
        'color': '#1d4ed8',
        'bgColor': '#eff6ff',
        'hAlign': 'left',
        'vAlign': 'top',
        'wrapMode': 'clamp',
        'maxWrapLines': 5,
        'minWidth': 140,
        'maxWidth': 420,
        'width': 420,
    }
    bob_layout = reopened.get_specific_layout(
        bob['user_id'], 'data-edit-surface', '10:sales:public.customers'
    )
    assert bob_layout['gridColPrefs']['notes'] == {'font': 'mono', 'hAlign': 'right'}

    # Shared templates visible to Bob as well
    templates = reopened.list_templates('data-edit-surface', user_id=bob['user_id'])
    assert any(
        t['template_id'] == tpl['template_id']
        and t['name'] == 'Compact Financial Grid'
        and t['layout']['gridColPrefs']['amount']['color'] == '#047857'
        for t in templates
    )

    conns = reopened.list_connection_parameters(alice['user_id'])
    assert len(conns) == 1
    assert conns[0]['parameters']['password_secret'] == 'top-secret-pg'
    assert reopened.get_user_preference(alice['user_id'], 'sqleditor', 'tab_size') == 4

    metrics = reopened.list_metrics_history_records(
        'server_metric', user_id=alice['user_id'], server_id=10
    )
    assert len(metrics) == 1
    assert metrics[0]['payload']['tps'] == 1482.5


def test_legacy_sqlite_migration_and_revisit_layout_restore_across_surfaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv('PGADMIN_TESTING_MODE', raising=False)

    # Seed legacy SQLite files in tmp_path before creating Firebird vault
    legacy_layouts = tmp_path / 'surface_layouts.db'
    with sqlite3.connect(str(legacy_layouts)) as conn:
        conn.executescript(
            """
            CREATE TABLE surface_specific_layout (
                user_id INTEGER NOT NULL,
                surface_kind TEXT NOT NULL,
                object_key TEXT NOT NULL,
                layout_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, surface_kind, object_key)
            );
            CREATE TABLE surface_layout_template (
                template_id TEXT PRIMARY KEY,
                surface_kind TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                author_user_id INTEGER NOT NULL,
                layout_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            'INSERT INTO surface_specific_layout VALUES (1, ?, ?, ?, ?)',
            (
                'data-edit-surface',
                '7:main:public.invoices',
                json.dumps(
                    {
                        'gridColPrefs': {
                            'total': {
                                'font': 'mono',
                                'color': '#047857',
                                'hAlign': 'right',
                                'minWidth': 100,
                                'maxWidth': 240,
                            }
                        }
                    }
                ),
                '2026-11-23T00:00:00Z',
            ),
        )

    ucfg = UserConfigurationDatabase(
        db_path=tmp_path / 'user_configuration.fdb', kdf_iterations=10_000
    )
    ucfg.unlock_and_authenticate(
        'dcalford', 'RobinSecret!1', 'VaultKey!2026', legacy_data_dir=tmp_path
    )

    store = SurfaceLayoutStore(ucfg)
    snippets = SqlSnippetsStore(ucfg)
    quick_queries = QuickQueryStore(ucfg)

    # Migrated invoice layout is immediately available in Firebird Embedded!
    migrated = store.get_specific_layout(1, 'data-edit-surface', '7:main:public.invoices')
    assert migrated['gridColPrefs']['total']['color'] == '#047857'
    assert migrated['gridColPrefs']['total']['minWidth'] == 100
    assert migrated['gridColPrefs']['total']['maxWidth'] == 240

    # Verify SqlSurfaceHostService save_template and DataSurfaceHostService shared store
    data_host = DataSurfaceHostService(layout_store=store)
    sql_host = SqlSurfaceHostService(
        snippets_store=snippets,
        quick_query_store=quick_queries,
        layout_store=store,
    )

    class _FakeServer:
        id = 7
        user_id = 1

    tpl_res = sql_host.dispatch(
        object(),
        _FakeServer(),
        {
            'sub_action': 'save_template',
            'template_name': 'Audit Wrap Template',
            'layout': {
                'gridColPrefs': {
                    'audit_log': {
                        'font': 'mono',
                        'color': '#b91c1c',
                        'wrapMode': 'clamp',
                        'maxWrapLines': 6,
                        'minWidth': 180,
                        'maxWidth': 520,
                    }
                }
            },
        },
    )
    assert tpl_res['saved'] == 'template'

    listed = data_host.layout_store.list_templates('data-edit-surface')
    assert any(
        t['name'] == 'Audit Wrap Template'
        and t['layout']['gridColPrefs']['audit_log']['maxWrapLines'] == 6
        for t in listed
    )


def test_flask_web_and_electron_splash_three_field_login_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import builtins
    import config as pg_config
    from pgadmin import create_app
    from pgadmin.cdeadmin.user_config_db import reset_default_user_config_db_for_tests

    builtins.SERVER_MODE = False
    monkeypatch.setattr(pg_config, 'SERVER_MODE', False)
    monkeypatch.setattr(pg_config, 'DATA_DIR', str(tmp_path))
    monkeypatch.setattr(pg_config, 'SQLITE_PATH', str(tmp_path / 'cdeadmin.db'))
    monkeypatch.setattr(pg_config, 'TEST_SQLITE_PATH', str(tmp_path / 'cdeadmin.db'))
    monkeypatch.setattr(pg_config, 'SESSION_DB_PATH', str(tmp_path / 'sessions'))
    monkeypatch.setattr(pg_config, 'STORAGE_DIR', str(tmp_path / 'storage'))
    monkeypatch.setattr(pg_config, 'LOG_FILE', str(tmp_path / 'cdeadmin.log'))
    monkeypatch.setattr(
        pg_config,
        'USER_CONFIGURATION_DATABASE_PATH',
        str(tmp_path / 'user_configuration.fdb'),
    )
    monkeypatch.setenv('PGADMIN_TESTING_MODE', '1')

    ucfg = UserConfigurationDatabase(
        db_path=tmp_path / 'user_configuration.fdb', kdf_iterations=10_000
    )
    reset_default_user_config_db_for_tests(ucfg)
    try:
        app = create_app('ScratchRobin-Test')
        app.config['USER_CONFIG_LOGIN_REQUIRED'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        app.PGADMIN_INT_KEY = 'desktop-int-key-123'

        client = app.test_client()

        # 1. Unauthenticated /browser/ redirects to /login instead of auto-logging DESKTOP_USER
        r_browser = client.get('/browser/?key=desktop-int-key-123')
        assert r_browser.status_code in (302, 401)
        if r_browser.status_code == 302:
            assert '/login' in r_browser.headers['Location']

        r_login_get = client.get('/login?key=desktop-int-key-123')
        assert r_login_get.status_code == 200
        assert b'vaultInitialized' in r_login_get.data

        # 2. /authenticate/vault_status reports uninitialized Firebird Embedded vault
        r_status = client.get('/authenticate/vault_status?key=desktop-int-key-123')
        assert r_status.status_code == 200
        status_data = r_status.get_json()['data']
        assert status_data['vault_initialized'] is False
        assert status_data['engine'] == 'firebird-embedded'

        # 3. Electron splash desktop_unlock initializes vault & returns handoff ticket
        r_unlock = client.post(
            '/authenticate/desktop_unlock?key=desktop-int-key-123',
            json={
                'username': 'dcalford',
                'password': 'DesktopPassword!2026',
                'database_key': 'EncryptedVaultKey#2026',
            },
        )
        assert r_unlock.status_code == 200
        unlock_data = r_unlock.get_json()['data']
        assert unlock_data['vault_created'] is True
        assert unlock_data['username'] == 'dcalford'
        ticket = unlock_data['ticket']
        assert ticket

        # Wrong database key is rejected with 401
        r_bad_key = client.post(
            '/authenticate/desktop_unlock?key=desktop-int-key-123',
            json={
                'username': 'dcalford',
                'password': 'DesktopPassword!2026',
                'database_key': 'WrongKey!',
            },
        )
        assert r_bad_key.status_code == 401
        assert 'Invalid database key' in r_bad_key.get_json()['errormsg']

        # Handoff ticket authenticates a fresh BrowserWindow client
        win_client = app.test_client()
        r_handoff = win_client.get(
            f'/authenticate/desktop_handoff?key=desktop-int-key-123&ticket={ticket}'
        )
        assert r_handoff.status_code == 302
        assert '/browser/' in r_handoff.headers['Location']

        # Single-use ticket cannot be replayed
        r_replay = app.test_client().get(
            f'/authenticate/desktop_handoff?key=desktop-int-key-123&ticket={ticket}'
        )
        assert '/login' in r_replay.headers['Location']

        # 4. Web first-form POST /authenticate/login with User name, User password, Database key
        ucfg.lock()
        web_client = app.test_client()
        r_web_bad = web_client.post(
            '/authenticate/login?key=desktop-int-key-123',
            data={
                'email': 'dcalford',
                'password': 'DesktopPassword!2026',
                'database_key': 'BadKey',
                'internal_button': 'Login',
            },
        )
        assert r_web_bad.status_code == 200
        assert not ucfg.is_unlocked()

        r_web_ok = web_client.post(
            '/authenticate/login?key=desktop-int-key-123',
            data={
                'email': 'dcalford',
                'password': 'DesktopPassword!2026',
                'database_key': 'EncryptedVaultKey#2026',
                'internal_button': 'Login',
            },
        )
        assert r_web_ok.status_code == 302
        assert ucfg.is_unlocked() is True
    finally:
        reset_default_user_config_db_for_tests(None)

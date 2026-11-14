##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

from __future__ import annotations

import os
from flask import Flask

import config as app_config_module
from pgadmin.cdeadmin.workspace.shell_authority import init_app


def _build_test_app(tmp_path):
    app = Flask(__name__)
    app.secret_key = 'test-shell-authority-secret'
    app.config['TESTING'] = True
    app.config['DATA_DIR'] = str(tmp_path)
    app_config_module.SERVER_MODE = False
    store = init_app(app, db_path=os.path.join(str(tmp_path), 'shell_settings.db'))
    return app, store


def test_shell_authorization_and_data_navigator_first(tmp_path):
    app, _store = _build_test_app(tmp_path)
    client = app.test_client()

    resp = client.get('/cdeadmin/api/shell/authorization')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['schema'] == 'cdeadmin.shell-authorization.v1'
    assert data['applications'][0]['id'] == 'data-navigator'
    assert data['applications'][0]['authorized'] is True

    # Disable cube-designer and set an action override; data-navigator cannot be disabled
    put_resp = client.put(
        '/cdeadmin/api/shell/authorization',
        json={
            'disabled_applications': ['cube-designer', 'data-navigator'],
            'action_overrides': {
                'erd.designer.accept': 'disabled',
                'bi.designer.outward_review': 'invisible',
            },
        },
    )
    assert put_resp.status_code == 200
    updated = put_resp.get_json()
    by_id = {item['id']: item for item in updated['applications']}
    assert by_id['data-navigator']['authorized'] is True
    assert by_id['cube-designer']['authorized'] is False
    assert by_id['cube-designer']['status'] == 'invisible'
    assert updated['action_overrides']['erd.designer.accept'] == 'disabled'
    assert updated['action_overrides']['bi.designer.outward_review'] == 'invisible'


def test_global_and_application_settings_with_drawer_reset(tmp_path):
    app, _store = _build_test_app(tmp_path)
    client = app.test_client()

    # Resize drawers & set per-application panel_gap + area_zoom for erd-designer
    put_resp = client.put(
        '/cdeadmin/api/shell/settings',
        json={
            'application_id': 'erd-designer',
            'left_drawer_width': 410,
            'right_drawer_width': 460,
            'show_tabbed_icon_bar': False,
            'panel_gap': 10,
            'area_zoom': {'area_3b': 115, 'area_3e': 125},
        },
    )
    assert put_resp.status_code == 200
    saved = put_resp.get_json()['settings']
    assert saved['left_drawer_width'] == 410
    assert saved['right_drawer_width'] == 460
    assert saved['show_tabbed_icon_bar'] is False
    assert saved['panel_gap'] == 10
    assert saved['area_zoom'] == {'area_3b': 115, 'area_3e': 125}

    # Global panel_gap & per-area zoom
    g_resp = client.put(
        '/cdeadmin/api/shell/settings',
        json={
            'global': {
                'panel_gap': 8,
                'area_zoom': {'area_1': 110, 'area_2': 120, 'area_3e': 105},
            }
        },
    )
    assert g_resp.status_code == 200
    g_saved = g_resp.get_json()['settings']
    assert g_saved['panel_gap'] == 8
    assert g_saved['area_zoom']['area_1'] == 110
    assert g_saved['area_zoom']['area_2'] == 120
    assert g_saved['area_zoom']['area_3e'] == 105
    assert g_saved['area_zoom']['area_3a'] == 100

    # Reset drawers back to default
    reset_resp = client.post('/cdeadmin/api/shell/settings/erd-designer/reset-drawers')
    assert reset_resp.status_code == 200
    reset_cfg = reset_resp.get_json()['settings']
    assert reset_cfg['left_drawer_width'] == reset_cfg['default_left_drawer_width']
    assert reset_cfg['right_drawer_width'] == reset_cfg['default_right_drawer_width']
    assert reset_cfg['drawer_reset_revision'] == 1


def test_session_lock_unlock_and_server_actions_and_reference(tmp_path):
    app, store = _build_test_app(tmp_path)
    store.register_server_action(
        'erd.test.ping',
        lambda payload, actor: {'echo': payload.get('msg'), 'actor': actor},
    )
    client = app.test_client()

    status0 = client.get('/cdeadmin/api/shell/session/status').get_json()
    assert status0['locked'] is False

    lock_resp = client.post('/cdeadmin/api/shell/session/lock')
    assert lock_resp.status_code == 200
    assert client.get('/cdeadmin/api/shell/session/status').get_json()['locked'] is True

    unlock_resp = client.post('/cdeadmin/api/shell/session/unlock', json={'password': ''})
    assert unlock_resp.status_code == 200
    assert client.get('/cdeadmin/api/shell/session/status').get_json()['locked'] is False

    # Reference endpoints
    for topic in ('sql', 'engines', 'glossary'):
        ref_resp = client.get(f'/cdeadmin/api/shell/reference/{topic}')
        assert ref_resp.status_code == 200
        assert len(ref_resp.get_json()['entries']) >= 3

    # Server action invocation & authorization enforcement
    act_resp = client.post(
        '/cdeadmin/api/shell/actions/erd.test.ping/invoke',
        json={'msg': 'hello'},
    )
    assert act_resp.status_code == 200
    assert act_resp.get_json()['result']['echo'] == 'hello'

    client.put(
        '/cdeadmin/api/shell/authorization',
        json={'action_overrides': {'erd.test.ping': 'disabled'}},
    )
    denied = client.post(
        '/cdeadmin/api/shell/actions/erd.test.ping/invoke',
        json={'msg': 'blocked'},
    )
    assert denied.status_code == 403


def test_color_schemes_typography_placements_engines_and_security(tmp_path):
    app, _store = _build_test_app(tmp_path)
    client = app.test_client()

    # 1. Save custom colour scheme, typography, and menu/iconbar placements
    custom_scheme = {
        'id': 'custom_midnight_amber',
        'label': 'Midnight Amber',
        'baseTone': 'dark',
        'backdropA': '#0b101b',
        'stripB': '#121929',
        'islandBg': '#182136',
        'drawerBg': '#141c2e',
        'fg': '#f8fafc',
        'muted': '#94a3b8',
        'border': '#334155',
        'accent': '#f59e0b',
    }
    save_resp = client.put(
        '/cdeadmin/api/shell/settings',
        json={
            'global': {
                'active_color_scheme': 'custom_midnight_amber',
                'custom_color_schemes': [custom_scheme],
                'enabled_scheme_ids': ['light', 'dark', 'nord_dark', 'custom_midnight_amber'],
                'typography': {
                    'ui_font_family': '"Atkinson Hyperlegible", sans-serif',
                    'mono_font_family': '"JetBrains Mono", monospace',
                    'diagram_font_family': '"IBM Plex Sans", sans-serif',
                    'ui_font_size': 15,
                    'mono_font_size': 13,
                    'line_height': 1.5,
                    'mono_ligatures': True,
                },
                'quick_access': ['shell.quick.new', 'shell.quick.save'],
                'menu_placements': {'window': {'visible': True, 'index': 70}},
                'icon_assignments': {'action.refresh': 'action.sync'},
            },
            'applications': {
                'sql-editor': {
                    'notebookbar_placements': {
                        'tabs': [{'id': 'sql-main', 'label': 'SQL', 'actions': ['sql.execute', 'sql.cancel']}],
                    },
                    'quick_access': ['shell.quick.new', 'sql.execute'],
                },
            },
        },
    )
    assert save_resp.status_code == 200
    payload = save_resp.get_json()
    assert payload['settings']['active_color_scheme'] == 'custom_midnight_amber'
    assert payload['settings']['typography']['ui_font_size'] == 15
    assert payload['settings']['typography']['mono_font_family'] == '"JetBrains Mono", monospace'
    assert payload['applications']['sql-editor']['quick_access'] == ['shell.quick.new', 'sql.execute']

    # 2. Database Engines registry GET & PUT
    eng_get = client.get('/cdeadmin/api/shell/engines')
    assert eng_get.status_code == 200
    engines_data = eng_get.get_json()
    assert len(engines_data['engines']) >= 10
    assert all('local_detected' in row and 'local_available' in row for row in engines_data['engines'])

    eng_put = client.put(
        '/cdeadmin/api/shell/engines',
        json={'enabled_engines': ['postgresql', 'firebird', 'duckdb']},
    )
    assert eng_put.status_code == 200
    assert eng_put.get_json()['enabled_engine_ids'] == ['duckdb', 'firebird', 'postgresql']

    # 3. Security configuration: groups, users, and application availability
    sec0 = client.get('/cdeadmin/api/shell/security').get_json()
    assert sec0['schema'] == 'cdeadmin.shell-security.v1'
    assert any(g['id'] == 'administrators' for g in sec0['groups'])

    # Create a custom group that revokes erd-designer & schema-compare
    grp_resp = client.post(
        '/cdeadmin/api/shell/security/groups',
        json={
            'id': 'readonly-viewers',
            'name': 'Read-Only Viewers',
            'description': 'May inspect catalogs and BI dashboards only.',
            'enabled_applications': ['data-navigator', 'bi-designer'],
            'disabled_applications': ['erd-designer', 'schema-compare', 'sql-editor'],
            'permissions': [],
        },
    )
    assert grp_resp.status_code == 200

    # Create a user assigned to readonly-viewers
    usr_resp = client.post(
        '/cdeadmin/api/shell/security/users',
        json={
            'username': 'alice',
            'email': 'alice@example.org',
            'active': True,
            'groups': ['readonly-viewers'],
        },
    )
    assert usr_resp.status_code == 200

    alice_authz = _store.resolve_user_authorization('alice')
    alice_apps = {a['id']: a['authorized'] for a in alice_authz['applications']}
    assert alice_apps['data-navigator'] is True
    assert alice_apps['bi-designer'] is True
    assert alice_apps['erd-designer'] is False
    assert alice_apps['schema-compare'] is False

    # System-wide disable bi-designer overrides group enablement
    client.put('/cdeadmin/api/shell/security', json={'system_disabled_applications': ['bi-designer']})
    alice_authz2 = _store.resolve_user_authorization('alice')
    alice_apps2 = {a['id']: a['authorized'] for a in alice_authz2['applications']}
    assert alice_apps2['bi-designer'] is False

    # 4. Live language switching returns merged UI translation catalog immediately
    lang_post = client.post('/cdeadmin/api/shell/language', json={'language': 'fr'})
    assert lang_post.status_code == 200
    lang_payload = lang_post.get_json()
    assert lang_payload['current'] == 'fr'
    assert isinstance(lang_payload.get('catalog'), dict)
    assert lang_payload['catalog'].get('Properties') == 'Propriétés'
    assert lang_payload['catalog'].get('Verify Endpoint') == 'Vérifier le point de terminaison'

    lang_get = client.get('/cdeadmin/api/shell/languages')
    assert lang_get.status_code == 200
    lang_get_payload = lang_get.get_json()
    assert lang_get_payload['current'] == 'fr'
    assert lang_get_payload['catalog'].get('Connectors (%s)') == 'Connecteurs (%s)'

##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Comprehensive verification suite for the Unified Security Authority,
Engine-Scoped Tree/Context-Menu Placement, and Provider Security Catalogs.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from flask import Flask

from pgadmin.browser.server_groups.servers import (
    _CDE_SERVER_SCOPE_TARGET,
    _endpoint_server_security_groups,
    _native_create_kinds,
    _server_scope_security_specs,
)
from pgadmin.cdeadmin.context_menu import (
    _declared_tools,
    database_target_context_actions,
    endpoint_context_actions,
    resource_group_context_actions,
)
from pgadmin.cdeadmin.endpoints import registration_profile
from pgadmin.cdeadmin.navigator import resource_children
from pgadmin.cdeadmin.providers.firebird import users as fb_users
from pgadmin.cdeadmin.providers.postgresql import (
    cluster as pg_cluster,
    routines as pg_routines,
    schemas as pg_schemas,
    sequences as pg_sequences,
    tables as pg_tables,
    views as pg_views,
)
from pgadmin.cdeadmin.ui_descriptors import SHELL_PRIMITIVES, UIDescriptorService
from pgadmin.cdeadmin.user_config_db import UserConfigurationDatabase
from pgadmin.cdeadmin.user_config_db.service import _load_firebird_driver
from pgadmin.cdeadmin.workspace.object_dashboard_host import init_app as init_object_dashboard
from pgadmin.cdeadmin.workspace.security_authority import (
    SecurityAuthorityError,
    compile_object_grants_plan,
    compile_principal_plan,
    init_app as init_security_authority,
    quote_identifier,
    quote_literal,
)


# ---------------------------------------------------------------------------
# 1. UI Descriptors, SHELL_PRIMITIVES, Form & Context-Menu Contracts
# ---------------------------------------------------------------------------


def test_shell_primitives_preserve_privileges_tabs_except_embedded_omitted():
    assert 'privileges' in SHELL_PRIMITIVES
    svc = UIDescriptorService()

    pg_bundle = svc.engine('postgresql')
    pg_table_tabs = [t['tab'] for t in pg_bundle['forms']['table']['tabs']]
    assert 'Security' in pg_table_tabs or 'Privileges' in pg_table_tabs

    fb_bundle = svc.engine('firebird')
    fb_table_tabs = [t['tab'] for t in fb_bundle['forms']['table']['tabs']]
    assert 'Security' in fb_table_tabs or 'Privileges' in fb_table_tabs

    my_bundle = svc.engine('mysql')
    my_role_tabs = [t['tab'] for t in my_bundle['forms']['role']['tabs']]
    assert 'Privileges' in my_role_tabs or 'Security' in my_role_tabs

    sqlite_bundle = svc.engine('sqlite')
    sqlite_table_tabs = [t['tab'] for t in sqlite_bundle['forms']['table']['tabs']]
    assert 'Security' not in sqlite_table_tabs
    assert 'Privileges' not in sqlite_table_tabs

    duck_bundle = svc.engine('duckdb')
    duck_table_tabs = [t['tab'] for t in duck_bundle['forms']['table']['tabs']]
    assert 'Security' not in duck_table_tabs
    assert 'Privileges' not in duck_table_tabs


def test_firebird_role_form_alter_password_user_fields_tags_and_admin_visibility():
    svc = UIDescriptorService()
    fb_role = svc.engine('firebird')['forms']['role']
    fields_by_id = {
        field['field_id']: field
        for tab in fb_role['tabs']
        for field in tab.get('fields', [])
    }

    assert fields_by_id['password']['required'] is False
    for uid_field in ('first_name', 'middle_name', 'last_name'):
        assert uid_field in fields_by_id
        assert fields_by_id[uid_field]['visible_when'] == {
            'field': 'variant',
            'equals': 'user',
        }

    assert fields_by_id['administrator']['visible_when'] == {
        'field': 'variant',
        'equals': 'user',
    }
    assert set(fields_by_id['description']['visible_when']['in']) == {'user', 'role'}

    tags_field = fields_by_id['tags']
    assert tags_field['control'] == 'grid'
    col_ids = [c['field_id'] for c in tags_field['columns']]
    assert col_ids == ['name', 'value', 'drop']


def test_security_manager_context_menus_across_server_and_database_scopes():
    # Firebird <Server> vs <Database>
    fb_prof = registration_profile('firebird-native')
    fb_server_actions = endpoint_context_actions(fb_prof, 'verified')
    fb_server_sec = [a for a in fb_server_actions if a.get('menu_group') == 'security']
    assert any(
        a['label'] == 'Manage Server Users...'
        and a['handler'] == 'open_tool'
        and a['arguments'].get('surface') == 'security.manager'
        and a['arguments'].get('scope') == 'server'
        and a['arguments'].get('initial_kind') == 'user'
        for a in fb_server_sec
    )

    fb_db_actions = database_target_context_actions(
        fb_prof,
        {'target_id': 'db1', 'database': '/var/db/app.fdb', 'display_name': 'app.fdb', 'active': True},
    )
    fb_db_labels = {a['label']: a for a in fb_db_actions}
    assert 'Manage Firebird users...' not in fb_db_labels
    assert fb_db_labels['Manage Firebird roles...']['handler'] == 'open_tool'
    assert fb_db_labels['Manage Firebird roles...']['arguments']['surface'] == 'security.manager'
    assert fb_db_labels['Manage Firebird roles...']['arguments']['scope'] == 'database'
    assert fb_db_labels['Manage Firebird roles...']['arguments']['initial_kind'] == 'role'
    assert fb_db_labels['Manage Firebird grants and privileges...']['arguments']['surface'] == 'security.manager'
    assert fb_db_labels['Manage Firebird grants and privileges...']['arguments']['scope'] == 'database'
    assert fb_db_labels['Manage Firebird grants and privileges...']['arguments']['initial_kind'] == 'role'

    # PostgreSQL <Server>
    pg_tools = _declared_tools('postgresql')
    assert any(
        t['label'] == 'Manage Cluster Roles...'
        and t['handler'] == 'open_tool'
        and t['arguments'] == {
            'surface': 'security.manager',
            'scope': 'server',
            'initial_kind': 'role',
        }
        for t in pg_tools
    )

    # MySQL & MariaDB <Server> vs <Database>
    for profile_id in ('mysql-native', 'mariadb-native'):
        prof = registration_profile(profile_id)
        srv_actions = endpoint_context_actions(prof, 'verified')
        assert any(
            a['label'] == 'Manage Users & Roles...'
            and a['arguments'].get('surface') == 'security.manager'
            and a['arguments'].get('scope') == 'server'
            and a['arguments'].get('initial_kind') == 'user'
            for a in srv_actions
        )
        db_actions = database_target_context_actions(
            prof,
            {'target_id': 'db1', 'database': 'sales', 'display_name': 'sales', 'active': True},
        )
        assert any(
            a['label'] == 'Manage Database Privileges...'
            and a['arguments'].get('surface') == 'security.manager'
            and a['arguments'].get('scope') == 'database'
            and a['arguments'].get('initial_kind') == 'privilege'
            for a in db_actions
        )

    # Server-scope resource group context actions include open_tool security.manager
    grp_actions = resource_group_context_actions(
        registration_profile('mysql-native'),
        'user',
        None,
        database_target_id=_CDE_SERVER_SCOPE_TARGET,
    )
    assert any(a['handler'] == 'open_tool' for a in grp_actions)


# ---------------------------------------------------------------------------
# 2. Server-vs-Database Tree Placement & Navigator Deduplication
# ---------------------------------------------------------------------------


def test_server_scope_security_group_nodes_and_native_create_kinds(monkeypatch):
    monkeypatch.setattr(
        'pgadmin.browser.server_groups.servers._cde_navigator_url',
        lambda gid, sid, state: f'/fake/{gid}/{sid}/{state["resource_kind"]}',
    )
    monkeypatch.setattr(
        'pgadmin.browser.server_groups.servers.gettext',
        lambda s: s,
    )
    fake_server = SimpleNamespace(name='prod-srv')

    # Firebird network vs embedded
    fb_net = registration_profile('firebird-native')
    assert [k for k, _ in _server_scope_security_specs(fb_net)] == [
        'user',
        'global-authentication-mapping',
    ]
    fb_nodes = _endpoint_server_security_groups(1, 10, fb_net, fake_server)
    assert [n['label'] for n in fb_nodes] == ['Users', 'Global authentication mappings']
    assert all(n['cde_database_target_id'] == _CDE_SERVER_SCOPE_TARGET for n in fb_nodes)

    fb_emb = registration_profile('firebird-embedded')
    assert _server_scope_security_specs(fb_emb) == ()
    assert _endpoint_server_security_groups(1, 11, fb_emb, fake_server) == []

    # MySQL, MariaDB, TiDB, Dolt -> Users & Roles at server scope
    for eng in ('mysql', 'mariadb', 'tidb', 'dolt'):
        prof = {'engine_id': eng, 'profile_id': f'{eng}-native', 'route_kind': 'network'}
        assert [k for k, _ in _server_scope_security_specs(prof)] == ['user', 'role']

    # CockroachDB, YugabyteDB -> Roles at server scope
    for eng in ('cockroachdb', 'yugabytedb'):
        prof = {'engine_id': eng, 'profile_id': f'{eng}-native', 'route_kind': 'network'}
        assert [k for k, _ in _server_scope_security_specs(prof)] == ['role']

    # SQLite, DuckDB -> No SQL user/role nodes
    for eng in ('sqlite', 'duckdb'):
        prof = {'engine_id': eng, 'profile_id': f'{eng}-embedded', 'route_kind': 'embedded_file'}
        assert _server_scope_security_specs(prof) == ()
        assert _endpoint_server_security_groups(1, 12, prof, fake_server) == []

    # _native_create_kinds: Firebird <Database> MUST allow creating database-scoped `role`!
    sample_va = {
        'objects': [
            {
                'resource_kind': kind,
                'operations': [
                    {
                        'operation_id': 'create',
                        'execution_route': 'provider-visual-admin',
                        'form': {'fields': [{'id': 'name'}]},
                    }
                ],
            }
            for kind in ('table', 'role', 'user')
        ]
    }
    assert 'role' in _native_create_kinds(sample_va, engine_id='firebird')
    assert 'user' not in _native_create_kinds(sample_va, engine_id='firebird')
    assert 'role' not in _native_create_kinds(sample_va, engine_id='mysql')
    assert 'role' not in _native_create_kinds(sample_va, engine_id='postgresql')


def test_navigator_omits_server_users_and_roles_inside_database_but_keeps_db_privileges():
    mysql_resources = [
        {
            'resource_id': 'user:alice@%',
            'resource_kind': 'user',
            'display_name': "'alice'@'%'",
            'display_path': ["'alice'@'%'"],
            'is_virtual': False,
            'extensions': {'cdeadmin': {'navigator_scope': 'server'}},
        },
        {
            'resource_id': 'role:app_read@%',
            'resource_kind': 'role',
            'display_name': "'app_read'@'%'",
            'display_path': ["'app_read'@'%'"],
            'is_virtual': False,
            'extensions': {'cdeadmin': {'navigator_scope': 'server'}},
        },
        {
            'resource_id': 'priv:global:root',
            'resource_kind': 'privilege',
            'display_name': "'root'@'localhost' SUPER",
            'display_path': ["'root'@'localhost' SUPER"],
            'is_virtual': False,
            'extensions': {'cdeadmin': {'navigator_scope': 'server'}, 'native': {'scope': 'global'}},
        },
        {
            'resource_id': 'priv:db:sales:alice',
            'resource_kind': 'privilege',
            'display_name': "'alice'@'%' SELECT",
            'display_path': ['sales', "'alice'@'%' SELECT"],
            'is_virtual': False,
            'extensions': {'cdeadmin': {'navigator_scope': 'database'}, 'native': {'scope': 'database'}},
        },
        {
            'resource_id': 'binlog:0001',
            'resource_kind': 'binary-log',
            'display_name': 'binlog.000001',
            'display_path': ['binlog.000001'],
            'is_virtual': False,
            'extensions': {'cdeadmin': {'navigator_scope': 'server'}},
        },
    ]

    db_children = resource_children(
        mysql_resources,
        {
            'scope': 'database',
            'target_id': 't-sales',
            'database': 'sales',
            'display_name': 'sales',
            'parent_path': [],
        },
    )
    child_kinds = {c['resource_kind'] for c in db_children}
    assert 'user' not in child_kinds
    assert 'role' not in child_kinds
    assert 'privilege' in child_kinds
    assert 'binary-log' in child_kinds

    # Server-scope kind expansion returns server-scoped users cleanly
    srv_users = resource_children(
        mysql_resources,
        {
            'scope': 'kind',
            'target_id': _CDE_SERVER_SCOPE_TARGET,
            'display_name': 'localhost',
            'parent_path': [],
            'resource_kind': 'user',
        },
    )
    assert [u['label'] for u in srv_users] == ["'alice'@'%'"]


# ---------------------------------------------------------------------------
# 3. Provider User/Role Compilation & ACL Normalization
# ---------------------------------------------------------------------------


def test_firebird_users_lifecycle_compilation_and_server_sec_discovery():
    create_spec = fb_users.compile_lifecycle_operation(
        'create',
        {
            'name': 'FB_ANALYST',
            'password': "Top'Secret!99",
            'plugin': 'Srp',
            'first_name': 'Ada',
            'middle_name': 'M.',
            'last_name': 'Lovelace',
            'administrator': True,
            'active': True,
            'description': 'Primary analytics account',
            'tags': [{'name': 'dept', 'value': 'bi'}, {'name': 'legacy', 'drop': True}],
        },
    )
    exec_sql = ';\n'.join(s['source'] for s in create_spec['statements'])
    prev_sql = ';\n'.join(s['preview_source'] for s in create_spec['statements'])
    assert "PASSWORD 'Top''Secret!99'" in exec_sql
    assert '<redacted>' in prev_sql
    assert "Top'Secret!99" not in prev_sql
    assert "FIRSTNAME 'Ada'" in prev_sql
    assert 'GRANT ADMIN ROLE' in prev_sql
    assert 'TAGS ("dept" = \'bi\', DROP "legacy")' in prev_sql
    assert 'COMMENT ON USER "FB_ANALYST" USING PLUGIN "Srp" IS \'Primary analytics account\'' in prev_sql

    # Alter without password succeeds cleanly
    alter_spec = fb_users.compile_lifecycle_operation(
        'alter',
        {
            'password': '',
            'last_name': 'Byron',
            'active': False,
            'administrator': False,
            'description': '',
        },
        target={'resource_kind': 'user', 'display_name': 'FB_ANALYST', 'native': {'plugin': 'Srp'}},
    )
    alter_prev = ';\n'.join(s['preview_source'] for s in alter_spec['statements'])
    assert 'PASSWORD' not in alter_prev
    assert 'REVOKE ADMIN ROLE' in alter_prev
    assert 'INACTIVE' in alter_prev
    assert 'COMMENT ON USER "FB_ANALYST" USING PLUGIN "Srp" IS NULL' in alter_prev


def test_postgresql_cluster_role_password_redaction_and_acl_parsers():
    created = pg_cluster.compile_operation(
        'role',
        'create',
        {},
        {
            'rolname': 'pg_auditor',
            'rolcanlogin': True,
            'rolpassword': "S3cr3t'Pass",
            'rolmembership': [{'role': 'pg_read_all_data', 'admin': False}],
        },
    )
    assert "PASSWORD '<redacted>'" in created['preview_statement']
    assert 'S3cr3t' not in created['preview_statement']
    assert "PASSWORD 'S3cr3t''Pass'" in created['statement']

    altered = pg_cluster.compile_operation(
        'role',
        'alter',
        {'name': 'pg_auditor', 'catalog_metadata': {'rolcanlogin': True}},
        {
            'rolname': 'pg_auditor',
            'rolpassword': 'Rotated!Password',
        },
    )
    assert "PASSWORD '<redacted>'" in altered['preview_statement']
    assert 'Rotated!Password' not in altered['preview_statement']
    assert "PASSWORD 'Rotated!Password'" in altered['statement']

    # Minimal dict backward compatibility vs enriched role_facts
    minimal_input = {
        'name': 'app_owner',
        'catalog_metadata': {'rolcanlogin': True, 'rolsuper': False, 'description': 'owns'},
    }
    assert pg_cluster.role_facts(minimal_input) == {
        'rolname': 'app_owner',
        'rolcanlogin': True,
        'rolsuper': False,
        'description': 'owns',
    }

    enriched = pg_cluster.role_facts(
        {
            'name': 'app_owner',
            'catalog_metadata': {
                'rolcanlogin': True,
                'rolsuper': False,
                'rolmembership': [{'role': 'readers', 'admin_option': True}],
                'rolmembers': [{'role': 'alice', 'admin_option': False}],
                'rolconfig': ['search_path=service, public', 'work_mem=64MB'],
            },
        }
    )
    assert enriched['rolmembership'][0]['role'] == 'readers'
    assert enriched['rolmembership'][0]['admin_option'] is True
    assert enriched['rolmembers'][0]['role'] == 'alice'
    assert enriched['variables'] == [
        {'name': 'search_path', 'value': 'service, public'},
        {'name': 'work_mem', 'value': '64MB'},
    ]

    # ACL explosion across PG object modules
    acl_sample = ['=r/postgres', 'cde_app=arwd*/postgres']
    tbl_privs = pg_tables.privileges({'relacl': acl_sample})
    assert any(p['grantee'] == 'PUBLIC' and p['privilege'] == 'SELECT' for p in tbl_privs)
    assert any(
        p['grantee'] == 'cde_app' and p['privilege'] == 'DELETE' and p['with_grant'] is True
        for p in tbl_privs
    )
    assert pg_views.privileges({'relacl': ['reader=r/postgres']})[0]['privilege'] == 'SELECT'
    assert pg_routines.privileges({'proacl': ['exec_role=X/postgres']})[0]['privilege'] == 'EXECUTE'
    assert pg_sequences.privileges({'relacl': ['seq_role=U/postgres']})[0]['privilege'] == 'USAGE'
    assert pg_schemas.privileges({'nspacl': ['dev_role=UC/postgres']})[0]['grantee'] == 'dev_role'


# ---------------------------------------------------------------------------
# 4. Security Authority SQL Compilation, Escaping & Injection Rejection
# ---------------------------------------------------------------------------


def test_compile_principal_plan_across_postgresql_mysql_and_mariadb():
    # PostgreSQL role create + alter
    pg_p = compile_principal_plan(
        'postgresql',
        'user',
        'create',
        None,
        {
            'name': 'bob',
            'password': 'Pg!Password9',
            'system_privileges': ['CREATEDB', 'INHERIT'],
            'connection_limit': 5,
            'valid_until': '2027-12-31 23:59:59+00',
            'grant_roles': [{'role': 'app_read', 'admin_option': False}],
            'comment': 'Reporting user',
        },
    )
    assert "PASSWORD '<redacted>'" in pg_p['preview_sql']
    assert 'Pg!Password9' not in pg_p['preview_sql']
    assert any("PASSWORD 'Pg!Password9'" in s for s in pg_p['exec_statements'])
    assert 'CONNECTION LIMIT 5' in pg_p['preview_sql']
    assert 'GRANT "app_read" TO "bob"' in pg_p['preview_sql']

    # MySQL 9.7 vs MariaDB 12.2 syntax differences
    my_p = compile_principal_plan(
        'mysql',
        'user',
        'create',
        None,
        {
            'name': 'svc_api',
            'host': '10.0.%',
            'password': 'My!Password7',
            'plugin': 'caching_sha2_password',
            'connection_limit': 20,
            'comment': 'API worker',
            'grant_roles': [{'role': 'app_rw', 'default_role': True}],
        },
    )
    assert "IDENTIFIED WITH `caching_sha2_password` BY '<redacted>'" in my_p['preview_sql']
    assert 'My!Password7' not in my_p['preview_sql']
    assert "SET DEFAULT ROLE 'app_rw'@'%' TO 'svc_api'@'10.0.%'" in my_p['preview_sql']

    maria_p = compile_principal_plan(
        'mariadb',
        'user',
        'create',
        None,
        {
            'name': 'svc_maria',
            'host': '%',
            'password': 'Maria!Password8',
            'plugin': 'mysql_native_password',
            'grant_roles': [{'role': 'etl_role', 'default_role': True}],
        },
    )
    assert "IDENTIFIED VIA `mysql_native_password` USING PASSWORD('<redacted>')" in maria_p['preview_sql']
    assert 'Maria!Password8' not in maria_p['preview_sql']
    assert "SET DEFAULT ROLE `etl_role` FOR 'svc_maria'@'%'" in maria_p['preview_sql']


def test_compile_object_grants_and_strict_sql_injection_rejection():
    # PostgreSQL table + column grant + grant-option-only revoke
    pg_g = compile_object_grants_plan(
        'postgresql',
        'table',
        'service',
        'customers',
        [
            {
                'action': 'grant',
                'grantee': 'app_role',
                'grantee_kind': 'role',
                'privileges': ['SELECT', 'UPDATE'],
                'columns': ['name', 'region'],
                'grant_option': True,
            },
            {
                'action': 'revoke',
                'grantee': 'app_role',
                'grantee_kind': 'role',
                'privileges': ['DELETE'],
                'grant_option_only': True,
            },
        ],
    )
    assert pg_g['statements'] == [
        'GRANT SELECT ("name", "region"), UPDATE ("name", "region") ON TABLE "service"."customers" TO "app_role" WITH GRANT OPTION',
        'REVOKE GRANT OPTION FOR DELETE ON TABLE "service"."customers" FROM "app_role"',
    ]

    # MariaDB sequence & MySQL routine grants
    maria_seq = compile_object_grants_plan(
        'mariadb',
        'sequence',
        'billing',
        'seq_inv',
        [{'action': 'grant', 'grantee': 'etl_role', 'grantee_kind': 'role', 'privileges': ['SELECT', 'ALTER']}],
    )
    assert maria_seq['statements'] == ['GRANT SELECT, ALTER ON `billing`.`seq_inv` TO `etl_role`']

    my_proc = compile_object_grants_plan(
        'mysql',
        'procedure',
        'billing',
        'recalc_totals',
        [{'action': 'revoke', 'grantee': 'svc_api', 'grantee_kind': 'user', 'grantee_host': '10.%', 'privileges': ['EXECUTE']}],
    )
    assert my_proc['statements'] == ["REVOKE EXECUTE ON PROCEDURE `billing`.`recalc_totals` FROM 'svc_api'@'10.%'"]

    # Strict SQL injection & invalid input defenses
    with pytest.raises(SecurityAuthorityError):
        compile_object_grants_plan(
            'postgresql',
            'table',
            'public',
            't1',
            [{'action': 'grant', 'grantee': 'bob', 'privileges': ['SELECT; DROP TABLE t1 --']}],
        )
    with pytest.raises(SecurityAuthorityError):
        quote_identifier('bad\nident', 'mysql')
    with pytest.raises(SecurityAuthorityError):
        quote_literal('nul\x00byte', 'postgresql')
    with pytest.raises(SecurityAuthorityError):
        compile_principal_plan(
            'postgresql',
            'user',
            'alter',
            {'name': 'bob'},
            {'valid_until': "2027-01-01'; SUPERUSER; --"},
        )


# ---------------------------------------------------------------------------
# 5. Stateful DB-API Harnesses & Flask Endpoint End-to-End Verification
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, handler):
        self._handler = handler
        self.description = ()
        self._rows = []

    def execute(self, sql: str, params: tuple = ()):
        cols, rows = self._handler(sql, params)
        self.description = [(c,) for c in cols]
        self._rows = list(rows)

    def fetchall(self):
        return list(self._rows)

    def close(self):
        pass


class _FakeConnection:
    def __init__(self, handler, executed_log: list[str]):
        self._handler = handler
        self.executed_log = executed_log
        self.committed = False

    def cursor(self):
        def dispatch(sql: str, params: tuple = ()):
            s_up = sql.strip().upper()
            if s_up.startswith(('CREATE ', 'ALTER ', 'DROP ', 'GRANT ', 'REVOKE ', 'COMMENT ', 'SET DEFAULT ROLE')):
                self.executed_log.append(sql)
                return (), []
            return self._handler(sql, params)

        return _FakeCursor(dispatch)

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


def _build_test_security_app():
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['SERVER_MODE'] = False
    host = init_security_authority(app)
    return app, host


def test_flask_security_endpoints_sqlite_duckdb_and_four_sql_engines_roundtrip():
    app, host = _build_test_security_app()
    client = app.test_client()

    # 1. SQLite & DuckDB return supported: False cleanly
    host.register_test_server(101, 'sqlite', route_kind='embedded_file')
    host.register_test_server(102, 'duckdb', route_kind='embedded_file')

    for sid, eng in ((101, 'sqlite'), (102, 'duckdb')):
        p_res = client.get(f'/cdeadmin/api/security/principals?sid={sid}&scope=database')
        assert p_res.status_code == 200
        p_json = p_res.get_json()
        assert p_json['engine'] == eng
        assert p_json['supported'] is False
        assert p_json['users'] == []
        assert p_json['roles'] == []

        og_res = client.get(
            f'/cdeadmin/api/security/object_grants?sid={sid}&object_kind=table&object_name=items'
        )
        assert og_res.status_code == 200
        assert og_res.get_json()['supported'] is False

        bad_plan = client.post(
            '/cdeadmin/api/security/principal/plan',
            json={'sid': sid, 'principal_kind': 'user', 'operation': 'create', 'draft': {'name': 'x'}},
        )
        assert bad_plan.status_code == 400

    # 2. PostgreSQL 18 round-trip
    pg_executed: list[str] = []

    def pg_handler(sql: str, params: tuple):
        if 'SELECT current_user' in sql:
            return ('u',), [('postgres',)]
        if 'FROM pg_catalog.pg_roles r' in sql:
            return (
                'oid', 'rolname', 'rolsuper', 'rolinherit', 'rolcreaterole',
                'rolcreatedb', 'rolcanlogin', 'rolreplication', 'rolbypassrls',
                'rolconnlimit', 'rolvaliduntil', 'comment',
            ), [
                (10, 'postgres', True, True, True, True, True, True, True, -1, None, 'Superuser'),
                (16384, 'analytics_reader', False, True, False, False, False, False, False, -1, None, 'Read role'),
            ]
        if 'FROM pg_catalog.pg_auth_members' in sql:
            return ('role_name', 'member_name', 'admin_option', 'inherit_option', 'set_option'), [
                ('analytics_reader', 'postgres', True, True, True)
            ]
        if 'SELECT rolname, rolcanlogin FROM pg_catalog.pg_roles' in sql:
            return ('rolname', 'rolcanlogin'), [('postgres', True), ('analytics_reader', False)]
        if 'FROM pg_catalog.pg_attribute a' in sql and 'aclexplode' not in sql:
            return ('cname',), [('customer_id',), ('email',)]
        if 'aclexplode(c.relacl)' in sql:
            return ('grantor', 'grantee', 'grantee_kind', 'privilege', 'grant_option'), [
                ('postgres', 'analytics_reader', 'role', 'SELECT', False)
            ]
        if 'aclexplode(a.attacl)' in sql:
            return ('column', 'grantor', 'grantee', 'grantee_kind', 'privilege', 'grant_option'), []
        return (), []

    host.register_test_server(
        202, 'postgresql', lambda _db: _FakeConnection(pg_handler, pg_executed)
    )

    pg_p = client.get('/cdeadmin/api/security/principals?sid=202&scope=server').get_json()
    assert pg_p['capabilities']['visibility_state'] == 'full'
    assert pg_p['users'][0]['name'] == 'postgres'
    assert pg_p['roles'][0]['name'] == 'analytics_reader'
    assert pg_p['roles'][0]['members'][0]['principal'] == 'postgres'

    pg_og_apply = client.post(
        '/cdeadmin/api/security/object_grants/apply',
        json={
            'sid': 202,
            'object_kind': 'table',
            'schema': 'public',
            'object_name': 'customers',
            'changes': [
                {
                    'action': 'grant',
                    'grantee': 'analytics_reader',
                    'grantee_kind': 'role',
                    'privileges': ['SELECT'],
                }
            ],
        },
    ).get_json()
    assert pg_og_apply['applied'] is True
    assert pg_executed[-1] == 'GRANT SELECT ON TABLE "public"."customers" TO "analytics_reader"'

    # 4. MySQL 9.7 & MariaDB 12.2 round-trips
    my_executed: list[str] = []

    def my_handler(sql: str, params: tuple):
        if 'CURRENT_USER()' in sql:
            return ('cu',), [('root@localhost',)]
        if 'USER_PRIVILEGES' in sql:
            return ('g', 'p'), [("'root'@'localhost'", 'SUPER')]
        if 'FROM mysql.user' in sql:
            return ('u', 'h', 'plugin', 'account_locked', 'max_user_connections', 'comment'), [
                ('root', 'localhost', 'caching_sha2_password', 'N', 0, ''),
                ('app_role', '%', 'caching_sha2_password', 'Y', 0, 'Role'),
            ]
        if 'FROM mysql.default_roles' in sql:
            return ('u', 'h', 'dru', 'drh'), [('root', 'localhost', 'app_role', '%')]
        if 'FROM mysql.role_edges' in sql:
            return ('fu', 'fh', 'tu', 'th', 'adm'), [('app_role', '%', 'root', 'localhost', 'Y')]
        if 'TABLE_PRIVILEGES' in sql:
            return ('grantee', 'priv', 'gopt'), [("'app_role'@'%'", 'SELECT', 'NO')]
        if 'COLUMN_PRIVILEGES' in sql or 'information_schema.COLUMNS' in sql:
            return (), []
        return (), []

    host.register_test_server(
        203, 'mysql', lambda _db: _FakeConnection(my_handler, my_executed)
    )
    # MySQL principals are administered through its provider operations (design Decision 21): this
    # endpoint refuses them rather than writing to the same accounts. MariaDB, which has no descriptor
    # of its own, still uses this host.
    refused = client.get('/cdeadmin/api/security/principals?sid=203&scope=server')
    assert refused.status_code == 400
    assert 'provider operations' in str(refused.get_json())

    maria_executed: list[str] = []

    def maria_handler(sql: str, params: tuple):
        if 'CURRENT_USER()' in sql:
            return ('cu',), [('root@localhost',)]
        if 'USER_PRIVILEGES' in sql:
            return ('g', 'p'), [("'root'@'localhost'", 'SUPER')]
        if 'FROM mysql.user' in sql:
            return ('u', 'h', 'is_role', 'plugin', 'max_user_connections', 'default_role'), [
                ('root', 'localhost', 'N', 'mysql_native_password', 0, 'reporting_role'),
                ('reporting_role', '', 'Y', '', 0, ''),
            ]
        if 'FROM mysql.global_priv' in sql:
            return ('u', 'h', 'lk'), [('root', 'localhost', 'false')]
        if 'FROM mysql.roles_mapping' in sql:
            return ('h', 'u', 'r', 'adm'), [('localhost', 'root', 'reporting_role', 'Y')]
        return (), []

    host.register_test_server(
        204, 'mariadb', lambda _db: _FakeConnection(maria_handler, maria_executed)
    )
    maria_p = client.get('/cdeadmin/api/security/principals?sid=204&scope=server').get_json()
    assert maria_p['roles'][0]['name'] == 'reporting_role'
    assert maria_p['users'][0]['member_of'][0]['default_role'] is True


def test_non_dba_graceful_degradation_for_postgresql():
    app, host = _build_test_security_app()
    client = app.test_client()

    # MySQL is served by its provider; this endpoint refuses it (the denied-visibility state it used to
    # report is the server's own answer, shown by the Security Manager).
    host.register_test_server(301, 'mysql', lambda _db: _FakeConnection(lambda sql, params: ((), []), []))
    assert client.get('/cdeadmin/api/security/principals?sid=301&scope=server').status_code == 400

    # PostgreSQL non-superuser -> HTTP 200 visibility_state='limited'
    def pg_non_dba(sql: str, params: tuple):
        if 'SELECT current_user' in sql:
            return ('u',), [('app_viewer',)]
        if 'FROM pg_catalog.pg_roles' in sql:
            return (
                'oid', 'rolname', 'rolsuper', 'rolinherit', 'rolcreaterole',
                'rolcreatedb', 'rolcanlogin', 'rolreplication', 'rolbypassrls',
                'rolconnlimit', 'rolvaliduntil', 'comment',
            ), [(20001, 'app_viewer', False, True, False, False, True, False, False, -1, None, '')]
        return (), []

    host.register_test_server(302, 'postgresql', lambda _db: _FakeConnection(pg_non_dba, []))
    res_pg = client.get('/cdeadmin/api/security/principals?sid=302&scope=server')
    assert res_pg.status_code == 200
    body_pg = res_pg.get_json()
    assert body_pg['capabilities']['visibility_state'] == 'limited'
    assert body_pg['capabilities']['can_manage_roles'] is False


def test_object_dashboard_properties_surfaces_normalized_permissions(monkeypatch, tmp_path):
    ucfg = UserConfigurationDatabase(db_path=tmp_path / 'sec_dash.fdb', kdf_iterations=12_000)
    ucfg.unlock_and_authenticate('admin', 'AdminPass!1', 'VaultKey!2026')
    monkeypatch.setattr(
        'pgadmin.cdeadmin.workspace.object_dashboard_host.get_user_config_db',
        lambda: ucfg,
    )

    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['SERVER_MODE'] = False
    dash = init_object_dashboard(app, workspace_service=None)

    monkeypatch.setattr(
        'pgadmin.cdeadmin.workspace.object_dashboard_host._resolve_engine_info',
        lambda srv, fallback_engine_id='': {
            'engine_id': 'postgresql',
            'engine_label': 'PostgreSQL',
            'profile_id': 'postgresql-preserved',
            'workflow': 'provider_endpoint',
            'route_cfg': {},
            'verified': True,
            'verified_version': '18.0',
        },
    )
    monkeypatch.setattr(
        dash,
        '_load_provider_snapshot_safe',
        lambda srv, db_target: {
            'resources': [
                {
                    'resource_id': 'tbl:orders',
                    'resource_kind': 'table',
                    'display_name': 'orders',
                    'extensions': {
                        'relational': {
                            'native': {
                                'comment': 'Customer orders',
                                'privileges': [
                                    {
                                        'grantee': 'app_reader',
                                        'grantee_kind': 'role',
                                        'grantor': 'postgres',
                                        'privilege': 'SELECT',
                                        'with_grant': False,
                                    }
                                ],
                            }
                        }
                    },
                }
            ]
        },
    )
    monkeypatch.setattr(
        dash,
        '_open_ephemeral_provider_runner',
        lambda srv, db_target: (None, lambda: None, None, None),
    )

    resp = app.test_client().get(
        '/cdeadmin/api/object_dashboard/properties',
        query_string={
            'node_type': 'cde_resource',
            'object_kind': 'table',
            'engine_id': 'postgresql',
            'server_id': 9,
            'object_name': 'orders',
        },
    )
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['permissions'] == [
        {
            'grantee': 'app_reader',
            'grantee_kind': 'role',
            'grantor': 'postgres',
            'privilege': 'SELECT',
            'with_grant': False,
            'column_name': None,
        }
    ]
    assert any(sec['id'] == 'privileges' for sec in payload['sections'])


def test_an_engine_administered_through_its_provider_is_refused_by_every_legacy_endpoint():
    """Decision 21: security.json status complete means one writer, the provider's operations.

    The refusal follows the descriptor, not an engine name, on all six host methods
    and over HTTP; an engine whose descriptor is still a draft stays on this path.
    """
    app, host = _build_test_security_app()
    client = app.test_client()
    host.register_test_server(601, 'firebird', route_kind='network')
    host.register_test_server(602, 'postgresql', route_kind='network')
    for sid, status in ((601, 'complete'), (602, 'draft')):
        assert UIDescriptorService().engine(host._resolve_target_info(sid)['engine_id'])['security']['status'] == status

    calls = (
        lambda: host.get_principals(601, None, 'server'),
        lambda: host.plan_principal({'sid': 601, 'principal_kind': 'role', 'operation': 'create', 'draft': {'name': 'x'}}),
        lambda: host.apply_principal({'sid': 601, 'principal_kind': 'role', 'operation': 'create', 'draft': {'name': 'x'}}),
        lambda: host.get_object_grants({'sid': 601, 'object_kind': 'table', 'object_name': 'T'}),
        lambda: host.plan_object_grants({'sid': 601, 'object_kind': 'table', 'object_name': 'T', 'changes': []}),
        lambda: host.apply_object_grants({'sid': 601, 'object_kind': 'table', 'object_name': 'T', 'changes': []}),
    )
    for call in calls:
        with pytest.raises(SecurityAuthorityError, match='administered through its provider operations'):
            call()

    refused = client.get('/cdeadmin/api/security/principals?sid=601&scope=server')
    assert refused.status_code == 400
    assert 'provider operations' in refused.get_json()['error']
    # A draft engine is not refused by the guard (it fails later for want of a connection, not by policy).
    with pytest.raises(Exception) as excinfo:
        host.get_principals(602, None, 'server')
    assert 'provider operations' not in str(excinfo.value)


def test_the_legacy_compilers_no_longer_know_firebird():
    with pytest.raises(SecurityAuthorityError):
        compile_principal_plan('firebird', 'role', 'create', None, {'name': 'AUDITOR'})
    with pytest.raises(SecurityAuthorityError):
        compile_object_grants_plan('firebird', 'table', None, 'T1',
                                   [{'action': 'grant', 'grantee': 'A', 'privileges': ['SELECT']}])


def test_security_routes_return_401_credential_required_when_endpoint_unverified():
    class SecretAccessError(Exception):
        pass

    app = Flask(__name__)
    app.config['SERVER_MODE'] = False
    host = init_security_authority(app)
    host.get_principals = lambda *_a, **_kw: (_ for _ in ()).throw(
        SecretAccessError('Endpoint credentials are required; verify this server connection')
    )
    resp = app.test_client().get('/cdeadmin/api/security/principals?sid=1&scope=server')
    assert resp.status_code == 401
    assert resp.get_json()['code'] == 'CREDENTIAL_REQUIRED'

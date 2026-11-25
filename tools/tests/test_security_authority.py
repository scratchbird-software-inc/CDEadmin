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


def test_compile_principal_plan_across_firebird_postgresql_mysql_and_mariadb():
    # Firebird user & role with system privileges
    fb_u = compile_principal_plan(
        'firebird',
        'user',
        'create',
        None,
        {
            'name': 'ALICE',
            'password': ' secret123 ',
            'plugin': 'Srp',
            'first_name': 'Alice',
            'is_admin': False,
            'tags': [{'name': 'team', 'value': 'ops'}],
            'grant_roles': [{'role': 'CDEADMIN_OPERATOR', 'admin_option': True, 'default_role': True}],
        },
    )
    assert '<redacted>' in fb_u['preview_sql']
    assert 'secret123' not in fb_u['preview_sql']
    assert any('secret123' in s for s in fb_u['exec_statements'])
    assert 'GRANT DEFAULT "CDEADMIN_OPERATOR" TO USER "ALICE" WITH ADMIN OPTION' in fb_u['preview_sql']

    fb_r = compile_principal_plan(
        'firebird',
        'role',
        'create',
        None,
        {
            'name': 'AUDITOR_ROLE',
            'system_privileges': ['MONITOR_ANY_ATTACHMENT', 'TRACE_ANY_ATTACHMENT'],
            'comment': 'Diagnostics role',
            'grant_members': [{'principal': 'ALICE', 'principal_type': 'user', 'admin_option': False}],
        },
    )
    assert 'CREATE ROLE "AUDITOR_ROLE" SET SYSTEM PRIVILEGES TO MONITOR_ANY_ATTACHMENT, TRACE_ANY_ATTACHMENT' in fb_r['preview_sql']
    assert 'GRANT "AUDITOR_ROLE" TO USER "ALICE"' in fb_r['preview_sql']

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

    # Firebird table and database DDL grant
    fb_g = compile_object_grants_plan(
        'firebird',
        'table',
        None,
        'INVOICES',
        [
            {
                'action': 'grant',
                'grantee': 'CDEADMIN_OPERATOR',
                'grantee_kind': 'role',
                'privileges': ['UPDATE'],
                'columns': ['STATUS'],
                'grant_option': False,
            }
        ],
    )
    assert fb_g['statements'] == [
        'GRANT UPDATE ("STATUS") ON TABLE "INVOICES" TO ROLE "CDEADMIN_OPERATOR"'
    ]

    fb_db = compile_object_grants_plan(
        'firebird',
        'database',
        None,
        'app.fdb',
        [{'action': 'grant', 'grantee': 'ALICE', 'grantee_kind': 'user', 'privileges': ['ALTER']}],
    )
    assert fb_db['statements'] == ['GRANT ALTER DATABASE TO USER "ALICE"']

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
        compile_object_grants_plan(
            'firebird',
            'table',
            None,
            'INVOICES',
            [{'action': 'grant', 'grantee': 'ALICE', 'grantee_kind': 'user', 'privileges': ['SELECT'], 'columns': ['ID']}],
        )
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

    # 2. Firebird 5 round-trip
    fb_executed: list[str] = []

    def fb_handler(sql: str, params: tuple):
        if 'FROM RDB$DATABASE' in sql:
            return ('u', 'r'), [('SYSDBA', 'NONE')]
        if "RDB$PRIVILEGE = 'M'" in sql:
            return ('grantee', 'role_name', 'def_flag', 'grant_opt', 'utype'), [
                ('SYSDBA', 'CDEADMIN_OPERATOR', 'D', 1, 8)
            ]
        if 'FROM SEC$USER_ATTRIBUTES' in sql:
            return ('u', 'p', 'k', 'v'), [('SYSDBA', 'Srp', 'env', 'prod')]
        if 'FROM SEC$USERS' in sql:
            if 'DISTINCT' in sql:
                return ('u',), [('SYSDBA',)]
            return (
                'uname', 'plugin', 'first_name', 'middle_name',
                'last_name', 'active', 'is_admin', 'description',
            ), [('SYSDBA', 'Srp', 'System', '', 'Admin', True, True, 'DBA account')]
        if 'FROM RDB$ROLES' in sql:
            if 'RDB$SYSTEM_FLAG' in sql and 'sys_privs' not in sql:
                return ('r',), [('CDEADMIN_OPERATOR',)]
            return ('rname', 'owner_name', 'description', 'sys_privs', 'sys_flag'), [
                ('CDEADMIN_OPERATOR', 'SYSDBA', 'Ops role', b'\x02\x00\x00\x00\x00\x00\x00\x00', 0)
            ]
        if 'FROM RDB$RELATION_FIELDS' in sql:
            return ('cname',), [('ID',), ('AMOUNT',)]
        if 'FROM RDB$USER_PRIVILEGES' in sql:
            return ('grantee', 'fname', 'priv', 'grantor', 'gopt', 'utype'), [
                ('CDEADMIN_OPERATOR', None, 'S', 'SYSDBA', 0, 13),
                ('CDEADMIN_OPERATOR', 'AMOUNT', 'U', 'SYSDBA', 1, 13),
            ]
        return (), []

    host.register_test_server(
        201, 'firebird', lambda _db: _FakeConnection(fb_handler, fb_executed), route_kind='network'
    )

    fb_p = client.get('/cdeadmin/api/security/principals?sid=201&scope=server').get_json()
    assert fb_p['supported'] is True
    assert fb_p['capabilities']['users_at_server_scope'] is True
    assert fb_p['capabilities']['roles_at_server_scope'] is False
    assert fb_p['users'][0]['name'] == 'SYSDBA'
    assert fb_p['users'][0]['attributes'] == {'env': 'prod'}
    assert fb_p['roles'][0]['name'] == 'CDEADMIN_OPERATOR'
    assert 'USER_MANAGEMENT' in fb_p['roles'][0]['system_privileges']

    fb_plan = client.post(
        '/cdeadmin/api/security/principal/plan',
        json={
            'sid': 201,
            'scope': 'server',
            'principal_kind': 'user',
            'operation': 'create',
            'draft': {'name': 'NEW_FB_USER', 'password': 'RawPassword!1', 'plugin': 'Srp'},
        },
    ).get_json()
    assert '<redacted>' in fb_plan['preview_sql']
    assert 'RawPassword!1' not in fb_plan['preview_sql']

    fb_apply = client.post(
        '/cdeadmin/api/security/principal/apply',
        json={
            'sid': 201,
            'scope': 'server',
            'principal_kind': 'user',
            'operation': 'create',
            'draft': {'name': 'NEW_FB_USER', 'password': 'RawPassword!1', 'plugin': 'Srp'},
        },
    ).get_json()
    assert fb_apply['applied'] is True
    assert any("PASSWORD 'RawPassword!1'" in s for s in fb_executed)

    fb_og = client.get(
        '/cdeadmin/api/security/object_grants?sid=201&object_kind=table&object_name=LEDGER'
    ).get_json()
    assert fb_og['capabilities']['columns'] == ['ID', 'AMOUNT']
    op_grant = fb_og['grants'][0]
    assert op_grant['grantee'] == 'CDEADMIN_OPERATOR'
    assert op_grant['privileges']['SELECT']['granted'] is True
    assert op_grant['privileges']['UPDATE']['columns'] == ['AMOUNT']

    # 3. PostgreSQL 18 round-trip
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
    my_p = client.get('/cdeadmin/api/security/principals?sid=203&scope=server').get_json()
    assert my_p['supported'] is True
    assert any(r['name'] == 'app_role' for r in my_p['roles'])
    root_user = next(u for u in my_p['users'] if u['name'] == 'root')
    assert root_user['member_of'][0]['default_role'] is True

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


def test_non_dba_graceful_degradation_across_mysql_postgresql_and_firebird():
    app, host = _build_test_security_app()
    client = app.test_client()

    # MySQL 1142 SELECT command denied on mysql.user -> HTTP 200 visibility_state='denied'
    class MySQL1142Error(Exception):
        errno = 1142

    def mysql_non_dba(sql: str, params: tuple):
        if 'CURRENT_USER()' in sql:
            return ('cu',), [('readonly@10.0.0.5',)]
        if 'FROM mysql.user' in sql:
            raise MySQL1142Error("SELECT command denied to user 'readonly'@'10.0.0.5' for table 'user'")
        return (), []

    host.register_test_server(301, 'mysql', lambda _db: _FakeConnection(mysql_non_dba, []))
    res_my = client.get('/cdeadmin/api/security/principals?sid=301&scope=server')
    assert res_my.status_code == 200
    body_my = res_my.get_json()
    assert body_my['capabilities']['visibility_state'] == 'denied'
    assert '1142' in body_my['capabilities']['visibility_message']
    assert body_my['capabilities']['can_manage_users'] is False

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

    # Firebird non-admin user -> HTTP 200 visibility_state='limited'
    def fb_non_dba(sql: str, params: tuple):
        if 'FROM RDB$DATABASE' in sql:
            return ('u', 'r'), [('ALICE', 'NONE')]
        if 'FROM SEC$USERS' in sql:
            return (
                'uname', 'plugin', 'first_name', 'middle_name',
                'last_name', 'active', 'is_admin', 'description',
            ), [('ALICE', 'Srp', 'Alice', '', '', True, False, '')]
        return (), []

    host.register_test_server(303, 'firebird', lambda _db: _FakeConnection(fb_non_dba, []), route_kind='network')
    res_fb = client.get('/cdeadmin/api/security/principals?sid=303&scope=server')
    assert res_fb.status_code == 200
    body_fb = res_fb.get_json()
    assert body_fb['capabilities']['visibility_state'] == 'limited'
    assert body_fb['capabilities']['can_manage_users'] is False


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


def test_live_firebird_embedded_role_and_object_grants_roundtrip(tmp_path):
    """Execute real Firebird 5 DCL via `/cdeadmin/api/security` against a temporary database."""
    fbd = _load_firebird_driver(tmp_path / 'fb_locks')
    fdb_file = tmp_path / 'live_security_verify.fdb'

    conn = fbd.create_database(str(fdb_file), user='SYSDBA', charset='UTF8')
    try:
        cur = conn.cursor()
        cur.execute(
            'CREATE TABLE "CUSTOMERS" ("CUSTOMER_ID" INTEGER NOT NULL PRIMARY KEY, "NAME" VARCHAR(80), "REGION" VARCHAR(40))'
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()

    app, host = _build_test_security_app()
    host.register_test_server(
        401,
        'firebird',
        lambda _db: fbd.connect(str(fdb_file), user='SYSDBA', charset='UTF8'),
        route_kind='embedded_file',
    )
    client = app.test_client()

    # 1. Create a real SQL ROLE with system privileges and comment on live Firebird 5
    apply_role = client.post(
        '/cdeadmin/api/security/principal/apply',
        json={
            'sid': 401,
            'scope': 'database',
            'principal_kind': 'role',
            'operation': 'create',
            'draft': {
                'name': 'CDEADMIN_OPERATOR',
                'system_privileges': ['MONITOR_ANY_ATTACHMENT'],
                'comment': 'Live verified role',
            },
        },
    )
    assert apply_role.status_code == 200
    assert apply_role.get_json()['applied'] is True

    principals = client.get('/cdeadmin/api/security/principals?sid=401&scope=database').get_json()
    created_role = next(r for r in principals['roles'] if r['name'] == 'CDEADMIN_OPERATOR')
    assert created_role['comment'] == 'Live verified role'
    assert 'MONITOR_ANY_ATTACHMENT' in created_role['system_privileges']

    # 2. Apply real GRANT SELECT + column UPDATE ("REGION") on CUSTOMERS to ROLE CDEADMIN_OPERATOR
    apply_grant = client.post(
        '/cdeadmin/api/security/object_grants/apply',
        json={
            'sid': 401,
            'object_kind': 'table',
            'object_name': 'CUSTOMERS',
            'changes': [
                {
                    'action': 'grant',
                    'grantee': 'CDEADMIN_OPERATOR',
                    'grantee_kind': 'role',
                    'privileges': ['SELECT'],
                    'grant_option': True,
                },
                {
                    'action': 'grant',
                    'grantee': 'CDEADMIN_OPERATOR',
                    'grantee_kind': 'role',
                    'privileges': ['UPDATE'],
                    'columns': ['REGION'],
                },
            ],
        },
    )
    assert apply_grant.status_code == 200
    assert apply_grant.get_json()['applied'] is True

    grants_view = client.get(
        '/cdeadmin/api/security/object_grants?sid=401&object_kind=table&object_name=CUSTOMERS'
    ).get_json()
    assert grants_view['capabilities']['columns'] == ['CUSTOMER_ID', 'NAME', 'REGION']
    op_row = next(g for g in grants_view['grants'] if g['grantee'] == 'CDEADMIN_OPERATOR')
    assert op_row['privileges']['SELECT']['granted'] is True
    assert op_row['privileges']['SELECT']['grant_option'] is True
    assert op_row['privileges']['UPDATE']['columns'] == ['REGION']

    # 3. Granular REVOKE SELECT on CUSTOMERS from ROLE CDEADMIN_OPERATOR
    revoke_res = client.post(
        '/cdeadmin/api/security/object_grants/apply',
        json={
            'sid': 401,
            'object_kind': 'table',
            'object_name': 'CUSTOMERS',
            'changes': [
                {
                    'action': 'revoke',
                    'grantee': 'CDEADMIN_OPERATOR',
                    'grantee_kind': 'role',
                    'privileges': ['SELECT'],
                }
            ],
        },
    )
    assert revoke_res.status_code == 200
    after_revoke = client.get(
        '/cdeadmin/api/security/object_grants?sid=401&object_kind=table&object_name=CUSTOMERS'
    ).get_json()
    op_after = next(g for g in after_revoke['grants'] if g['grantee'] == 'CDEADMIN_OPERATOR')
    assert op_after['privileges']['SELECT']['granted'] is False
    assert op_after['privileges']['UPDATE']['columns'] == ['REGION']


def test_firebird_network_server_scope_avoids_remote_security_db_and_supports_service_mgr_fallback():
    """Network Firebird server scope must never attach remotely to `security.db` (GDS 335544352)."""
    connected_routes: list[dict] = []

    class _FakeUserInfo:
        def __init__(self, user_name: str, admin: bool = False):
            self.user_name = user_name
            self.first_name = 'System'
            self.middle_name = ''
            self.last_name = 'Admin'
            self.admin = admin

    class _FakeServiceUserMgr:
        def __init__(self):
            self.added = []
            self.deleted = []

        def get_all(self):
            return [_FakeUserInfo('SYSDBA', admin=True)]

        def add(self, **kwargs):
            self.added.append(kwargs)

        def update(self, *args, **kwargs):
            pass

        def delete(self, uname):
            self.deleted.append(uname)

    class _FakeServiceConn:
        def __init__(self):
            self.user = _FakeServiceUserMgr()

        def close(self):
            pass

    svc_conn = _FakeServiceConn()

    class _FakeProviderClient:
        def _connect(self, payload):
            r = dict(payload.get('route') or {})
            connected_routes.append(r)
            if r.get('database') == 'security.db':
                raise RuntimeError('Firebird connection failed (DatabaseError); Firebird status codes: 335544352')
            if r.get('database') == '/var/lib/firebird/data/cdeadmin_demo.fdb':
                def _fb_handler(sql: str, _params: tuple = ()):
                    up = sql.upper()
                    if 'FROM RDB$DATABASE' in up:
                        return ('u', 'r'), [('SYSDBA', 'RDB$ADMIN')]
                    if 'FROM SEC$USERS' in up:
                        return (
                            'uname', 'plugin', 'first_name', 'middle_name',
                            'last_name', 'active', 'is_admin', 'description',
                        ), [('SYSDBA', 'Srp', '', '', '', True, True, '')]
                    return (), []

                return _FakeConnection(_fb_handler, [])
            return svc_conn

        def _forget_and_close(self, conn):
            pass

    class _FakeProvider:
        attachment_mode = 'network'
        client = _FakeProviderClient()

        def _resolve_server_security_database_candidates(self, route):
            return []

    fake_provider = _FakeProvider()

    class _FakeEndpointService:
        def __init__(self, target_db: str | None):
            self.target_db = target_db
            self.provider_registry = SimpleNamespace(
                resolve=lambda _ctx: SimpleNamespace(instance=fake_provider)
            )

        def workspace(self, server, database_target_id=Ellipsis):
            if database_target_id == 'dbt-1' and self.target_db:
                return (
                    'ctx-db',
                    {'route': {'host': '127.0.0.1', 'port': 53050, 'user': 'SYSDBA', 'database': self.target_db}},
                    {},
                )
            return (
                'ctx-srv',
                {'route': {'host': '127.0.0.1', 'port': 53050, 'user': 'SYSDBA'}},
                {},
            )

    app = Flask(__name__)
    app.config['SERVER_MODE'] = False

    # Case 1: Network server with an active `.fdb` target attaches to that `.fdb` and reads SEC$USERS
    ws_with_db = SimpleNamespace(
        endpoint_service=_FakeEndpointService('/var/lib/firebird/data/cdeadmin_demo.fdb'),
        resource_service=SimpleNamespace(invalidate=lambda _ctx: None),
    )
    host_db = init_security_authority(app, workspace_service=ws_with_db)
    srv_with_db = SimpleNamespace(
        id=1,
        name='localhost',
        host='127.0.0.1',
        port=53050,
        username='SYSDBA',
        maintenance_db='',
        endpoint_profile=SimpleNamespace(
            profile_id='firebird',
            database_targets=[SimpleNamespace(id='dbt-1', database='/var/lib/firebird/data/cdeadmin_demo.fdb', active=True)],
        ),
    )
    host_db._resolve_target_info = lambda sid: {
        'sid': sid,
        'server': srv_with_db,
        'engine_id': 'firebird',
        'workflow': 'provider',
        'route_kind': 'network',
    }
    with app.app_context():
        res = host_db.get_principals(1, None, 'server')
    assert [u['name'] for u in res['users']] == ['SYSDBA']
    assert res['users'][0]['plugin'] == 'Srp'
    assert all(r.get('database') != 'security.db' for r in connected_routes)

    # Case 2: Network server with zero `.fdb` targets falls back to Firebird Services Manager
    connected_routes.clear()
    app2 = Flask(__name__)
    app2.config['SERVER_MODE'] = False
    ws_zero_db = SimpleNamespace(
        endpoint_service=_FakeEndpointService(None),
        resource_service=SimpleNamespace(invalidate=lambda _ctx: None),
    )
    host_svc = init_security_authority(app2, workspace_service=ws_zero_db)
    srv_zero_db = SimpleNamespace(
        id=2,
        name='empty-fb',
        host='127.0.0.1',
        port=53050,
        username='SYSDBA',
        maintenance_db='',
        endpoint_profile=SimpleNamespace(profile_id='firebird', database_targets=[]),
    )
    host_svc._resolve_target_info = lambda sid: {
        'sid': sid,
        'server': srv_zero_db,
        'engine_id': 'firebird',
        'workflow': 'provider',
        'route_kind': 'network',
    }
    with app2.app_context():
        res_svc = host_svc.get_principals(2, None, 'server')
        host_svc.apply_principal({
            'sid': 2,
            'scope': 'server',
            'principal_kind': 'user',
            'operation': 'create',
            'draft': {'name': 'SVC_USER', 'password': 'Strong!Password9', 'is_admin': False},
        })
    assert [u['name'] for u in res_svc['users']] == ['SYSDBA']
    assert svc_conn.user.added[0]['user_name'] == 'SVC_USER'
    assert all(r.get('database') != 'security.db' for r in connected_routes)


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

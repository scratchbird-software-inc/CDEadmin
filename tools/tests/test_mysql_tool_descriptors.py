"""Declared tools preserve source access, outage access and exact scope."""
import json
from pathlib import Path

import pytest

from test_cdeadmin_context_menu import profile
from pgadmin.cdeadmin.context_menu import (
    database_target_context_actions, endpoint_context_actions,
)

ROOT = Path(__file__).resolve().parents[2]
DOCUMENT = json.loads((ROOT / 'web/pgadmin/cdeadmin/ui_descriptors/mysql/tools.json').read_text())


@pytest.mark.parametrize('verified', ['verified', 'unverified', 'failed'])
@pytest.mark.parametrize('owner', [True, False])
def test_source_diagnostics_and_collectors_require_verification_and_ownership(verified, owner):
    actions = {row['command_id']: row for row in endpoint_context_actions(
        profile('mysql', multiple=True), verified, can_manage=owner)}
    for name in ['data_drift', 'spatial', 'content_search', 'workload',
                 'monitoring', 'monitoring_policy', 'server_catalog']:
        row = actions['endpoint.mysql.' + name]
        assert row['enabled'] is (verified == 'verified' and owner)
        if verified != 'verified':
            assert row['disabled_reason'] == 'Verify this endpoint before using it.'
        elif not owner:
            assert 'owner' in row['disabled_reason']


@pytest.mark.parametrize('owner', [True, False])
def test_native_job_and_host_tools_can_reopen_during_sql_outage_only_for_owner(owner):
    actions = {row['command_id']: row for row in endpoint_context_actions(
        profile('mysql', multiple=True), 'failed', can_manage=owner)}
    for name in ['host', 'routers', 'physical', 'raw_binlogs', 'binlogs', 'binlog_replay',
                 'instance_backups', 'instance_restores',
                 'sandboxes', 'topologies', 'local_clone']:
        row = actions['endpoint.mysql.' + name]
        assert row['enabled'] is owner and row['mutation_class'] == 'admin'
        assert 'database_target_id' not in row['arguments']


@pytest.mark.parametrize('target', ['database-one', "database 雪'2"])
def test_database_tools_keep_exact_selected_scope_and_viewer_collector_editor_separation(target):
    actions = {row['command_id']: row for row in database_target_context_actions(
        profile('mysql', multiple=True), {'target_id': target})}
    for name in ['monitoring', 'monitoring_policy', 'spatial', 'dashboard_editor', 'catalog_ddn', 'test_data']:
        row = actions['database.mysql.' + name]
        assert row['arguments']['resource_id'] == target
        assert row['arguments']['database_target_id'] == target
    viewer = actions['database.mysql.monitoring']
    collector = actions['database.mysql.monitoring_policy']
    editor = actions['database.mysql.dashboard_editor']
    assert viewer['handler'] == collector['handler'] == 'open_workspace'
    assert viewer['arguments']['tab'] == 'monitoring' and viewer['mutation_class'] == 'read'
    assert collector['arguments']['tab'] == 'monitoring_policy' and collector['mutation_class'] == 'admin'
    assert editor['handler'] == 'open_mysql_dashboard_editor' and editor['mutation_class'] == 'write'


def test_tools_are_openers_with_unique_ids_and_do_not_duplicate_native_operation_descriptors():
    rows = DOCUMENT['tools']; ids = [row['command_id'] for row in rows]
    assert len(rows) == len(set(ids)) == 25
    assert all('operation_id' not in row.get('arguments', {}) for row in rows)
    assert all('MySQL' not in row['label'] for row in rows)
    for engine in ['mysql', 'mariadb']:
        resolved = endpoint_context_actions(profile(engine), 'verified')
        assert len({row['command_id'] for row in resolved}) == len(resolved)
        if engine == 'mariadb':
            assert not any(row['command_id'] in ids for row in resolved)

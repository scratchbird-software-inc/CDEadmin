"""Permissions are identified by their values (2026-11-08).

pgAdmin's own permissions have the same attribute name and value
('tools_query_tool'); ScratchRobin's use dotted values
('project.asset.edit'). AllPermissionTypes.list() returned the attribute
names, so the Administrator's permissions, the User role seeded from it and
current_user.permissions carried 'project_asset_edit' while commands, the
role editor and the constants use 'project.asset.edit': every command that
requires a dotted permission was hidden from every user. Values are now used
throughout, and names stored by older databases are read as values.
"""
from pathlib import Path
import sqlite3
import sys

WEB = Path(__file__).resolve().parents[2] / 'web'
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))

from tools.tests.test_config_db_first_build import _start  # noqa: E402
from pgadmin.model import Role  # noqa: E402
from pgadmin.tools.user_management.PgAdminPermissions import (  # noqa: E402
    AllPermissionTypes, PgAdminPermissions)


def test_the_list_holds_values_only():
    values = AllPermissionTypes.list()
    assert 'project.asset.edit' in values and 'tools_query_tool' in values
    assert 'project_asset_edit' not in values
    # The old list also returned its own method name as a permission.
    assert 'list' not in values and 'canonical' not in values
    assert len(values) == len(set(values))
    # The role editor offers exactly these.
    offered = {item['name'] for item in PgAdminPermissions().all_permissions}
    assert offered == set(values)


def test_stored_names_are_read_as_values():
    assert AllPermissionTypes.canonical(
        ['project_asset_edit', 'tools_query_tool', 'project.asset.edit',
         'custom']) == ['project.asset.edit', 'tools_query_tool', 'custom']
    assert AllPermissionTypes.canonical(None) == []
    role = Role(name='User', description='',
                permissions=['project_asset_edit', 'schema_compare_view'])
    assert role.get_permissions() == {'project.asset.edit',
                                      'schema_compare.view'}
    administrator = Role(name='Administrator', description='')
    assert administrator.get_permissions() == set(AllPermissionTypes.list())


def test_a_new_configuration_database_stores_values(tmp_path):
    database, _ = _start(tmp_path)
    with sqlite3.connect(database) as connection:
        stored = connection.execute(
            "SELECT permissions FROM role WHERE name = 'User'").fetchone()[0]
    stored = set(stored.split(','))
    assert {'project.asset.edit', 'schema_compare.view',
            'tools_query_tool'} <= stored
    assert not stored & {'project_asset_edit', 'schema_compare_view', 'list'}

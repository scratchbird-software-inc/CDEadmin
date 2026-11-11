"""The inherited PostgreSQL database actions are declared for the
provider tree (M2, owner direction 2026-11-08 / decision 2026-11-10)."""
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.context_menu import (  # noqa: E402
    database_target_context_actions,
)
sys.path.insert(0, str(ROOT / 'tools/tests'))
from test_cdeadmin_context_menu import profile  # noqa: E402

MENU_JS = ROOT / 'web/pgadmin/browser/static/js/ProviderContextMenu.js'
SERVER_JS = (ROOT / 'web/pgadmin/browser/server_groups/servers/static/js/'
             'server.js')

EXPECTED = {
    'database.postgresql.monitoring': 'PostgreSQL dashboard...',
    'database.postgresql.monitoring_policy':
        'Configure PostgreSQL monitoring...',
    'database.postgresql.dashboard_editor': 'Edit PostgreSQL dashboard...',
    'database.postgresql.catalog_ddn': 'PostgreSQL catalog DDN...',
    'database.postgresql.test_data': 'Generate PostgreSQL test data...',
    'database.postgresql.large_object_files':
        'PostgreSQL large-object files...',
    'database.postgresql.advanced_objects': 'PostgreSQL advanced objects...',
}


def actions():
    return {item['command_id']: item for item in
            database_target_context_actions(
                profile('postgresql'),
                {'target_id': 'postgresql-database:16384',
                 'display_name': 'demo'})}


def test_every_inherited_database_action_is_declared_with_its_label():
    found = actions()
    for command_id, label in EXPECTED.items():
        assert command_id in found, command_id
        assert found[command_id]['label'] == label, command_id


def test_openers_carry_the_database_target_and_their_tab():
    found = actions()
    for command_id in EXPECTED:
        arguments = found[command_id]['arguments']
        assert arguments['database_target_id'] == 'postgresql-database:16384'
    assert found['database.postgresql.catalog_ddn']['arguments'][
        'tab'] == 'export'
    assert found['database.postgresql.test_data']['arguments'][
        'tab'] == 'postgresql-test-data'
    assert found['database.postgresql.large_object_files']['arguments'][
        'tab'] == 'postgresql-large-object-files'
    advanced = found['database.postgresql.advanced_objects']['arguments']
    assert advanced['tab'] == 'administration'
    assert advanced['resource_kind'] == 'access-method'
    assert found['database.postgresql.monitoring_policy']['arguments'][
        'policy_mode'] is True
    assert 'policy_mode' not in found[
        'database.postgresql.monitoring']['arguments']


def test_dashboard_handlers_are_distinct_and_mutations_declared():
    found = actions()
    assert found['database.postgresql.monitoring'][
        'handler'] == 'open_postgresql_monitor'
    assert found['database.postgresql.dashboard_editor'][
        'handler'] == 'open_postgresql_dashboard_editor'
    assert found['database.postgresql.dashboard_editor'][
        'mutation_class'] == 'write'
    assert found['database.postgresql.test_data'][
        'mutation_class'] == 'write'
    assert found['database.postgresql.monitoring_policy'][
        'mutation_class'] == 'admin'


def test_client_accepts_the_monitor_handler_and_the_workspace_tabs():
    menu = MENU_JS.read_text(encoding='utf-8')
    assert "'open_postgresql_monitor'" in menu
    assert "case 'open_postgresql_monitor':" in menu
    server = SERVER_JS.read_text(encoding='utf-8')
    gate = server.split('const postgresReady = ')[1].split(';')[0]
    for tab in ('export', 'postgresql-test-data',
                'postgresql-large-object-files', 'administration'):
        assert f"'{tab}'" in gate, tab

"""SQLite dashboard drafts are stored like every other engine's.

The SQLite monitoring host (2026-10-14) serves dashboard definitions through
the shared DashboardDefinitions adapter, but the adapter's engine list stopped
at DuckDB, so every SQLite draft, save and published-layout read was refused
with "Unknown dashboard engine" (shown as "Invalid dashboard draft"). Found in
the 2026-11-08 live check of the DDN screens.
"""
import pytest

from tools.tests.test_cdeadmin_project_assets import MemoryRepository
from tools.tests.test_dashboard_definitions import payload
from pgadmin.cdeadmin.workspace.assets import (
    ProjectAssetService, ProjectAssetError)
from pgadmin.cdeadmin.workspace.dashboard_definitions import (
    DashboardDefinitions, ENGINE_NAMES)
from pgadmin.cdeadmin.workspace.duckdb_monitoring_host import (
    DuckDBMonitoringHost)
from pgadmin.cdeadmin.workspace.sqlite_monitoring_host import (
    SQLiteMonitoringHost)


def _definitions(assets, engine):
    def authorize(owner, sid, target):
        return {'engine': engine, 'owner': owner, 'server_id': sid,
                'target_id': target,
                'kind': 'database' if target else 'server'}
    return DashboardDefinitions(assets, authorize)


def test_sqlite_drafts_are_scoped_and_separate_from_duckdb():
    assets = ProjectAssetService(MemoryRepository())
    sqlite = _definitions(assets, 'sqlite')
    duckdb = _definitions(assets, 'duckdb')
    initial = sqlite.read(1, 7, 'file')
    reference = initial['assetRef']
    assert reference['projectId'] == 'sqlite-dashboard-drafts-1'
    assert reference['displayName'] == 'SQLite database dashboard draft'
    saved = sqlite.save(1, 7, 'file', payload(reference))
    assert saved['assetRef']['assetVersion'] == 1
    assert sqlite.read(1, 7, 'file')['snapshot'] == saved['snapshot']
    assert duckdb.read(1, 7, 'file')['snapshot'] is None
    assert sqlite.read(2, 7, 'file')['snapshot'] is None
    assert sqlite.read(1, 7, None)['snapshot'] is None
    with pytest.raises(ProjectAssetError):
        duckdb.save(1, 7, 'file', payload(saved['assetRef']))


def test_the_file_monitoring_hosts_have_dashboard_definitions():
    engines = {DuckDBMonitoringHost.engine, SQLiteMonitoringHost.engine}
    assert engines <= set(ENGINE_NAMES)
    assets = ProjectAssetService(MemoryRepository())
    with pytest.raises(ProjectAssetError, match='Unknown dashboard engine'):
        _definitions(assets, 'redis').read(1, 7, None)

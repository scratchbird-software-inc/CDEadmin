"""MariaDB dashboard assets remain native-engine, owner and target scoped."""
from tools.tests.test_cdeadmin_project_assets import MemoryRepository
from tools.tests.test_dashboard_definitions import payload
from pgadmin.cdeadmin.workspace.assets import ProjectAssetService, ProjectAssetError
from pgadmin.cdeadmin.workspace.dashboard_definitions import DashboardDefinitions
import pytest


def test_native_dashboard_assets_are_persistent_and_separate_from_mysql():
    assets = ProjectAssetService(MemoryRepository())
    def authorize(engine):
        return lambda owner, sid, target: {'engine': engine, 'owner': owner, 'server_id': sid,
            'target_id': target, 'kind': 'database' if target else 'server'}
    maria = DashboardDefinitions(assets, authorize('mariadb'))
    mysql = DashboardDefinitions(assets, authorize('mysql'))
    initial = maria.read(1, 7, 'db')
    assert initial['assetRef']['projectId'] == 'mariadb-dashboard-drafts-1'
    assert initial['assetRef']['displayName'] == 'MariaDB database dashboard draft'
    saved = maria.save(1, 7, 'db', payload(initial['assetRef']))
    assert saved['assetRef']['assetVersion'] == 1
    assert maria.read(1, 7, 'db')['snapshot'] == saved['snapshot']
    assert mysql.read(1, 7, 'db')['snapshot'] is None
    assert maria.read(2, 7, 'db')['snapshot'] is None
    assert maria.read(1, 7, 'other')['snapshot'] is None
    with pytest.raises(ProjectAssetError): mysql.save(1, 7, 'db', payload(saved['assetRef']))
    with pytest.raises(ProjectAssetError): maria.save(1, 7, 'other', payload(saved['assetRef']))

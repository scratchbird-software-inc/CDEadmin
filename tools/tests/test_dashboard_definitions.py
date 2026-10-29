"""Scoped persistent dashboard drafts use the real project-asset service."""
import copy
import pytest
from tools.tests.test_cdeadmin_project_assets import MemoryRepository
from pgadmin.cdeadmin.workspace.assets import (
    ProjectAssetService, ProjectAssetError, ProjectAssetConflict, ProjectAssetForbidden,
)
from pgadmin.cdeadmin.workspace.dashboard_definitions import DashboardDefinitions


def setup():
    assets = ProjectAssetService(MemoryRepository())
    def authorize(owner, sid, target):
        if owner != 1 or sid not in (None, 7) or target not in (None, 'db'):
            raise PermissionError('Denied')
        return {'kind': 'engine' if sid is None else 'database' if target else 'server',
                'endpoint_id': sid, 'target_id': target, 'owner': owner}
    return DashboardDefinitions(assets, authorize), assets


def payload(reference):
    return {'schema': 'cdeadmin.ddn-asset.v1', 'assetRef': reference,
            'snapshot': {'format': 'ddn-source-workspace@1', 'entry': 'dashboard.ddn',
                         'view': 'dashboard', 'files': {'dashboard.ddn':
                            'version ddn-next-1\nview dashboard as table.records@1\n'}}}


def test_get_has_no_write_and_scope_identity_never_collapses():
    definitions, assets = setup()
    refs = [definitions.read(1, sid, target)['assetRef']
            for sid, target in [(None, None), (7, None), (7, 'db')]]
    assert len({r['assetId'] for r in refs}) == 3
    assert assets.repository.commits == 0
    with pytest.raises(PermissionError):
        definitions.read(2, 7, 'db')


def test_roundtrip_revisions_and_stale_editor_conflict():
    definitions, assets = setup()
    initial = definitions.read(1, 7, 'db')
    request = payload(initial['assetRef'])
    saved = definitions.save(1, 7, 'db', request)
    assert saved['state'] == 'draft'
    assert saved['assetRef']['assetVersion'] == 1
    assert definitions.read(1, 7, 'db') == saved
    with pytest.raises(ProjectAssetConflict):
        definitions.save(1, 7, 'db', request)
    next_request = copy.deepcopy(request)
    next_request['assetRef'] = saved['assetRef']
    next_request['snapshot']['files']['dashboard.ddn'] += '\n// changed layout'
    latest = definitions.save(1, 7, 'db', next_request)
    assert latest['assetRef']['assetVersion'] == 2
    old = assets.get_asset(1, (), saved['assetRef']['projectId'], saved['assetRef']['assetId'], 1)
    assert old['content'] == request['snapshot']


def test_invalid_or_cross_scope_save_does_not_create_project():
    definitions, assets = setup()
    request = payload(definitions.read(1, 7, 'db')['assetRef'])
    with pytest.raises(ProjectAssetError):
        definitions.save(1, 7, None, request)
    request['snapshot']['files'] = {'../invalid.ddn': 'bad'}
    with pytest.raises(ProjectAssetError):
        definitions.save(1, 7, 'db', request)
    assert assets.repository.commits == 0


def test_colliding_project_name_never_grants_another_owner_access():
    definitions, assets = setup()
    assets.create_project(2, 'firebird-dashboard-drafts-1', {'name': 'Foreign'})
    with pytest.raises(ProjectAssetForbidden):
        definitions.read(1)

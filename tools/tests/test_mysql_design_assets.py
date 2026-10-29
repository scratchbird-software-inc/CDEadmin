"""MySQL design revisions stay independent of database execution and Firebird."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from tools.tests.test_cdeadmin_project_assets import MemoryRepository
from pgadmin.cdeadmin.workspace.assets import ProjectAssetService, ProjectAssetError, ProjectAssetConflict
from pgadmin.cdeadmin.workspace.firebird_design_assets import NativeDesignAssets

SCOPE={'endpoint_id':'endpoint','database_target_id':'db'}
SNAPSHOT={'format':'ddn-source-workspace@1','entry':'relations.ddn','view':'relations',
 'files':{'relations.ddn':'version ddn-next-1\nerd relations\n    with\n        id relations\n    Table\n'}}


def test_native_design_revision_cas_baseline_and_engine_namespaces():
    assets=ProjectAssetService(MemoryRepository())
    mysql,firebird=NativeDesignAssets(assets,engine='mysql'),NativeDesignAssets(assets)
    initial=mysql.apply(1,SCOPE,'read',{'kind':'relations'})
    assert initial['assetRef']['projectId']=='mysql-designs-1'
    body={'kind':'relations','assetRef':initial['assetRef'],'snapshot':deepcopy(SNAPSHOT),'baseline':deepcopy(SNAPSHOT)}
    saved=mysql.apply(1,SCOPE,'save',body)
    assert saved['version']==1 and saved['baseline']==SNAPSHOT
    for owner,scope,store in [(2,SCOPE,mysql),(1,{**SCOPE,'database_target_id':'other'},mysql),(1,SCOPE,firebird)]:
        with pytest.raises(ProjectAssetError):store.apply(owner,scope,'save',body)
    with pytest.raises(ProjectAssetConflict):mysql.apply(1,SCOPE,'save',body)
    body['assetRef']=saved['assetRef'];body['snapshot']['files']['relations.ddn']+='\n// manual layout'
    mysql.apply(1,SCOPE,'save',body)
    previous=mysql.apply(1,SCOPE,'read',{'kind':'relations','version':1})
    assert previous['snapshot']==previous['baseline']==SNAPSHOT
    assert previous['assetRef']['assetVersion']==2
    assert firebird.apply(1,SCOPE,'read',{'kind':'relations'})['snapshot'] is None
    content=assets.get_asset(1,(),'mysql-designs-1',initial['assetRef']['assetId'])['content']
    assert content['mysqlDesign']['baseline']==SNAPSHOT and 'firebirdDesign' not in content


def test_mysql_design_host_uses_owned_registered_route_before_storage():
    import config
    from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService, ProviderWorkspaceError
    service=object.__new__(ProviderWorkspaceService)
    service.firebird_design_assets=NativeDesignAssets(ProjectAssetService(MemoryRepository()))
    service._principal_id=Mock(return_value=1)
    service._mysql_catalog_context=Mock(return_value=(SimpleNamespace(endpoint_id='endpoint'),{},None))
    server=object()
    result=service.mysql_design_asset(server,'read',{'kind':'relations','database_target_id':'db'})
    assert result['assetRef']['projectId']=='mysql-designs-1'
    service._mysql_catalog_context.assert_called_once_with(server,'db')
    service._mysql_catalog_context.side_effect=ProviderWorkspaceError('Not owned')
    with pytest.raises(ProviderWorkspaceError,match='Not owned'):
        service.mysql_design_asset(server,'save',{'kind':'relations','database_target_id':'db'})
    assert service.firebird_design_assets.assets.repository.commits==0

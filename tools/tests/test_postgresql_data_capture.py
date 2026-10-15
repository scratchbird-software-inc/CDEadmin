"""Explicit relation data capture rejects ambiguous or unbounded requests."""
from unittest.mock import Mock
import pytest
from pgadmin.cdeadmin.providers.postgresql.data_capture import capture


@pytest.mark.parametrize('resource,mode,limit,database', [
    ('postgresql:pg_class:0','sample',10,42),
    ('postgresql:pg_class:042','sample',10,42),
    ('postgresql:pg_class:4294967296','sample',10,42),
    ('postgresql:pg_class:42; SELECT 1','sample',10,42),
    ('postgresql:pg_proc:42','sample',10,42),
    ('postgresql:pg_class:42','random',10,42),
    ('postgresql:pg_class:42','sample',True,42),
    ('postgresql:pg_class:42','sample',0,42),
    ('postgresql:pg_class:42','full',6001,42),
    ('postgresql:pg_class:42','sample',10,None),
    ('postgresql:pg_class:42','sample',10,True),
])
def test_invalid_capture_does_not_connect(resource, mode, limit, database):
    provider=Mock()
    with pytest.raises(ValueError):
        capture(provider,{'database_id':database},'endpoint',resource,mode=mode,row_limit=limit)
    provider.open_session.assert_not_called()


def test_explicit_data_permissions_precede_any_connection():
    provider=Mock()
    provider.permissions.require.side_effect=PermissionError('denied')
    with pytest.raises(PermissionError):
        capture(provider,{'database_id':42},'endpoint','postgresql:pg_class:12')
    provider.open_session.assert_not_called()


def test_installed_manifest_scopes_admit_the_explicit_read_boundary():
    import json
    from pathlib import Path
    from pgadmin.cdeadmin.core.registry import PermissionGuard, PermissionGrant
    manifest=json.loads((Path(__file__).resolve().parents[2]/'web/pgadmin/cdeadmin/providers/postgresql/provider_manifest.json').read_text())
    grants={item['permission_id']:PermissionGrant(item['permission_id'],frozenset(item['scope']))
            for item in manifest['permissions'] if item['granted']}
    provider=Mock()
    provider.permissions=PermissionGuard(grants,frozenset(grants))
    class AttachmentBoundary(Exception):pass
    provider.open_session.side_effect=AttachmentBoundary
    with pytest.raises(AttachmentBoundary):
        capture(provider,{'database_id':42},'endpoint','postgresql:pg_class:12')
    provider.open_session.assert_called_once()

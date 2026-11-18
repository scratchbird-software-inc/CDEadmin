from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import config  # noqa: F401
import pytest

from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService, ProviderWorkspaceError


def service(profile='firebird-native', **changes):
    owner = object.__new__(ProviderWorkspaceService)
    route = {
        'host': '::1', 'port': 3051, 'database': '/server/file name.fdb',
        'user': 'Account', 'charset': 'UTF8', 'role': 'Role',
        'password': 'must-not-leave-server', 'credential_reference_id': 'sealed',
        **changes,
    }
    owner.endpoint_service = SimpleNamespace(
        workspace=Mock(return_value=(None, {'route': route}, None)),
        provider_registry=None,
    )
    server = SimpleNamespace(endpoint_profile=SimpleNamespace(profile_id=profile))
    return owner, server


def test_exact_owner_scoped_connection_description_has_no_secrets():
    owner, server = service()
    result = owner.firebird_isql_context(server, {'database_target_id': 'owned'})
    assert result == {
        'schema': 'scratchrobin.firebird.isql-context@1',
        'database_target_id': 'owned',
        'dsn': 'inet://[::1]:3051//server/file name.fdb',
        'user': 'Account',
        'role': 'Role',
        'charset': 'UTF8',
        'sql_dialect': 3,
    }
    owner.endpoint_service.workspace.assert_called_once_with(server, database_target_id='owned')


def test_embedded_same_host_context_binds_boot_id_and_inode_without_secrets(tmp_path, monkeypatch):
    db_file = tmp_path / 'owned 雪.fdb'
    db_file.write_bytes(b'owned embedded db')
    lock_dir = tmp_path / 'lock'
    lock_dir.mkdir()
    monkeypatch.setenv('FIREBIRD_LOCK', str(lock_dir))
    release_idle = Mock()
    provider = SimpleNamespace(client=SimpleNamespace(_release_idle_catalog=release_idle))
    registry = SimpleNamespace(resolve=Mock(return_value=SimpleNamespace(instance=provider)))
    owner = object.__new__(ProviderWorkspaceService)
    route = {
        'attachment_mode': 'embedded',
        'database': str(db_file),
        'filesystem_root': str(tmp_path),
        'user': 'SYSDBA',
        'role': 'RDB$ADMIN',
        'charset': 'UTF8',
        'sql_dialect': 3,
    }
    ctx = SimpleNamespace(endpoint_id='emb-1')
    owner.endpoint_service = SimpleNamespace(
        workspace=Mock(return_value=(ctx, {'route': route}, None)),
        provider_registry=registry,
    )
    server = SimpleNamespace(endpoint_profile=SimpleNamespace(profile_id='firebird-embedded'))
    result = owner.firebird_isql_context(server, {'database_target_id': 'owned-emb'})
    st = db_file.stat()
    assert result['schema'] == 'scratchrobin.firebird.isql-context@1'
    assert result['attachment_mode'] == 'embedded'
    assert result['database'] == str(db_file)
    assert result['filesystem_root'] == str(tmp_path.resolve())
    assert result['native_provider'] == 'Engine13'
    assert result['password_required'] is False
    assert 'dsn' not in result and 'password' not in result
    auth = result['same_host_authority']
    assert auth['platform'] == 'linux'
    assert auth['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    assert auth['database_identity'] == {'device': str(st.st_dev), 'inode': str(st.st_ino)}
    assert auth['firebird_lock_directory'] == str(lock_dir.resolve())
    release_idle.assert_called_once()


def test_embedded_context_refuses_network_secrets_missing_files_and_outside_paths(tmp_path):
    db_file = tmp_path / 'owned.fdb'
    db_file.write_bytes(b'owned')
    for bad_route in (
        {'attachment_mode': 'embedded', 'database': str(db_file), 'filesystem_root': str(tmp_path), 'credential_reference_id': 'net'},
        {'attachment_mode': 'embedded', 'database': str(tmp_path / 'missing.fdb'), 'filesystem_root': str(tmp_path)},
        {'attachment_mode': 'embedded', 'database': '/etc/passwd', 'filesystem_root': str(tmp_path)},
        {'attachment_mode': 'network', 'database': str(db_file), 'filesystem_root': str(tmp_path)},
    ):
        owner = object.__new__(ProviderWorkspaceService)
        owner.endpoint_service = SimpleNamespace(
            workspace=Mock(return_value=(None, {'route': bad_route}, None)),
            provider_registry=None,
        )
        server = SimpleNamespace(endpoint_profile=SimpleNamespace(profile_id='firebird-embedded'))
        with pytest.raises(ProviderWorkspaceError):
            owner.firebird_isql_context(server, {'database_target_id': 'owned'})


@pytest.mark.parametrize('payload', [{}, {'database_target_id': ''}, {'database_target_id': 'owned', 'password': 'bad'}, None])
def test_invalid_scope_is_refused_before_route_access(payload):
    owner, server = service()
    with pytest.raises(ProviderWorkspaceError):
        owner.firebird_isql_context(server, payload)
    owner.endpoint_service.workspace.assert_not_called()


@pytest.mark.parametrize('changes', [{'profile': 'postgresql-native'}, {'host': ''}, {'protocol': 'XNET'}, {'sql_dialect': 2}])
def test_unsupported_targets_are_not_reinterpreted(changes):
    owner, server = service(**changes)
    with pytest.raises(ProviderWorkspaceError):
        owner.firebird_isql_context(server, {'database_target_id': 'owned'})

"""Repair admits a damaged approved file without a preliminary SQL attach."""
from unittest.mock import Mock
from threading import RLock
from types import SimpleNamespace
import json

import pytest

from pgadmin.cdeadmin.providers.firebird import local_services as local
from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
from pgadmin.cdeadmin.providers.firebird import repair
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine


@pytest.mark.parametrize('action', repair.ACTIONS)
def test_repair_uses_canonical_native_path_without_sql_probe(tmp_path, action):
    path = tmp_path/'damaged 雪.fdb'; path.write_bytes(b'not a SQL-readable database')
    route = {'attachment_mode': 'embedded', 'database': str(path),
             'filesystem_root': str(tmp_path), 'user': 'SYSDBA'}
    options = {'repair_action': action}
    selected = local.validate_operation(route, 'repair_database', str(path), options)
    client = Mock()
    with local.service_filename(client, selected, local.file_identity(selected),
                                'repair_database', options) as fenced:
        assert fenced is False
        assert local.dispatch_target(str(path)) == str(path)
        client._connect.assert_not_called()
    assert path.read_bytes() == b'not a SQL-readable database'
    assert not list(tmp_path.glob('.scratchrobin-*'))


@pytest.mark.parametrize('options', [
    {'repair_action': 'MEND_DB', 'repair_modifiers': ['FULL', 'CHECK_DB']},
    {'repair_action': 'ICU', 'parallel_workers': 0, 'no_linger': True},
    {'repair_action': 'ICU', 'parallel_workers': 32767},
])
def test_typed_local_repair_preserves_native_options(tmp_path, options):
    path = tmp_path/'owned.fdb'; path.touch()
    route = {'attachment_mode': 'embedded', 'database': str(path), 'filesystem_root': str(tmp_path)}
    assert local.validate_operation(route, 'repair_database', str(path), options)
    with pytest.raises(RelationalClientError):
        local.validate_operation(route, 'repair_database', str(path), {**options, 'host': 'remote'})


def test_repair_keeps_attachment_free_shared_form_and_native_warnings():
    catalog = embedded.ADMINISTRATION.catalog(catalog_for_engine('firebird'))
    task = next(op for row in catalog['objects'] if row['resource_kind'] == 'database'
                for op in row['operations'] if op['operation_id'] == 'repair_database')
    assert task['workspace_scope'] == 'server_service'
    assert {f['field_id'] for f in task['form']['fields']} == {
        'repair_action', 'repair_modifiers', 'parallel_workers', 'no_linger', 'role'}
    assert 'ScratchRobin host' in task['form']['notes']
    assert 'discard damaged records' in ' '.join(repair.warnings({'repair_action': 'MEND_DB'}))


def test_upgrade_admits_only_the_existing_approved_file_without_sql(tmp_path):
    path = tmp_path/'legacy.fdb'; path.write_bytes(b'owned old ODS fixture')
    route = {'attachment_mode': 'embedded', 'database': str(path), 'filesystem_root': str(tmp_path)}
    selected = local.validate_operation(route, 'upgrade_database', str(path), {})
    client = Mock()
    with local.service_filename(client, selected, local.file_identity(selected), 'upgrade_database', {}) as fenced:
        assert not fenced
        client._connect.assert_not_called()
    with pytest.raises(RelationalClientError):
        local.validate_operation(route, 'upgrade_database', str(path), {'repair_action': 'MEND_DB'})


@pytest.mark.parametrize('active', [True, False])
def test_exclusive_maintenance_releases_only_selected_idle_catalog_handles(active):
    from pgadmin.cdeadmin.providers.firebird.provider import FirebirdProvider
    provider = object.__new__(FirebirdProvider)
    owned = Mock(); owned.main_transaction.is_active.return_value = active
    unrelated = Mock(); session = Mock()
    key = json.dumps({'database': '/approved/selected.fdb'})
    other = json.dumps({'database': '/approved/other.fdb'})
    provider._catalog_pool = {key: owned, other: unrelated}
    provider._catalog_pool_lock = RLock()
    provider.client = SimpleNamespace(_admission=RLock(), _connections=[session], _forget_and_close=Mock())
    if active:
        with pytest.raises(RelationalClientError, match='not idle'):
            provider._release_idle_catalog_for_service({'database': '/approved/selected.fdb'})
        assert provider._catalog_pool[key] is owned
        provider.client._forget_and_close.assert_not_called()
    else:
        provider._release_idle_catalog_for_service({'database': '/approved/selected.fdb'})
        provider.client._forget_and_close.assert_called_once_with(owned)
        assert provider._catalog_pool == {other: unrelated}
        assert session in provider.client._connections
    owned.rollback.assert_not_called(); owned.commit.assert_not_called()
    unrelated.close.assert_not_called(); session.close.assert_not_called()


@pytest.mark.parametrize('active_second', [True, False])
def test_maintenance_releases_all_idle_slots_without_losing_other_pool_handles(active_second):
    from pgadmin.cdeadmin.providers.firebird.provider import FirebirdProvider
    provider = object.__new__(FirebirdProvider)
    first, second, unrelated = Mock(), Mock(), Mock()
    first.main_transaction.is_active.return_value = False
    second.main_transaction.is_active.return_value = active_second
    key = json.dumps({'database': '/approved/selected.fdb'})
    other = json.dumps({'database': '/approved/other.fdb'})
    bucket = [first, second]
    provider._catalog_pool = {key: bucket, other: [unrelated]}
    provider._catalog_pool_lock = RLock()
    provider.client = SimpleNamespace(_admission=RLock(), _connections=[], _forget_and_close=Mock())
    if active_second:
        with pytest.raises(RelationalClientError, match='not idle'):
            provider._release_idle_catalog_for_service({'database': '/approved/selected.fdb'})
        assert bucket == [first, second]
        provider.client._forget_and_close.assert_not_called()
    else:
        provider._release_idle_catalog_for_service({'database': '/approved/selected.fdb'})
        assert key not in provider._catalog_pool
        assert [call.args[0] for call in provider.client._forget_and_close.call_args_list] == [first, second]
    assert provider._catalog_pool[other] == [unrelated]
    for handle in (first, second, unrelated):
        handle.rollback.assert_not_called()
        handle.commit.assert_not_called()

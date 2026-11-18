"""Local physical backup (nbackup) validates canonical paths and never overwrites files."""
from pathlib import Path
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.firebird import local_physical_backup as backup
from pgadmin.cdeadmin.providers.firebird import local_services as local
from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
from pgadmin.cdeadmin.providers.firebird.provider import _create_client
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.visual_admin import ProviderVisualAdministration


def inputs(tmp_path):
    source = tmp_path / "source 雪's.fdb"
    source.write_bytes(b'owned primary database')
    route = {
        'attachment_mode': 'embedded',
        'database': str(source),
        'filesystem_root': str(tmp_path),
        'user': 'SYSDBA',
    }
    options = {'backup_file': str(tmp_path / 'level0 雪.nbk'), 'backup_level': 0}
    return route, options


def test_selection_and_execution_verify_parent_and_observe_canonical_output(tmp_path):
    route, options = inputs(tmp_path)
    selected = local.validate_operation(route, 'backup_physical', route['database'], options)
    assert selected['database'] == route['database']
    reviewed = backup.selection(selected, options)
    assert len(reviewed) == 1 and reviewed[0]['filename'] == options['backup_file']
    with backup.execution(selected, options, reviewed) as records:
        Path(options['backup_file']).write_bytes(b'owned native nbackup bytes')
        rows = backup.observations(records)
        assert rows[0]['requested_path_names_regular_file'] is True
        assert rows[0]['parent_identity_unchanged'] is True
        assert rows[0]['bytes_observed'] == 26
        assert rows[0]['output_inode_pinned'] is False
        assert rows[0]['native_exclusive_create'] is True
        assert rows[0]['rename_race_fenced'] is False
        assert rows[0]['restore_verified'] is False


def test_existing_file_and_source_aliases_are_refused_without_overwrite(tmp_path):
    route, options = inputs(tmp_path)
    reviewed = backup.selection(route, options)
    target = Path(options['backup_file'])
    target.hardlink_to(route['database'])
    with pytest.raises(RelationalClientError) as error:
        with backup.execution(route, options, reviewed):
            pytest.fail('Existing physical backup output admitted')
    assert error.value.rejected and error.value.nothing_changed
    assert target.read_bytes() == b'owned primary database'
    for candidate in (route['database'], str(target)):
        with pytest.raises(RelationalClientError):
            backup.selection(route, {'backup_file': candidate})


@pytest.mark.parametrize('filename', ['relative.nbk', '/proc/self/fd/0', 'stdout', '../outside.nbk'])
def test_noncanonical_or_unapproved_physical_backup_paths_are_refused(tmp_path, filename):
    route, _ = inputs(tmp_path)
    with pytest.raises(RelationalClientError):
        backup.selection(route, {'backup_file': filename})


def test_replaced_output_parent_directory_is_refused_before_dispatch(tmp_path):
    route, _ = inputs(tmp_path)
    parent = tmp_path / 'nbak-out'
    parent.mkdir()
    options = {'backup_file': str(parent / 'b0.nbk')}
    reviewed = backup.selection(route, options)
    parent.rename(tmp_path / 'retained-nbak-out')
    parent.mkdir()
    with pytest.raises(RelationalClientError) as error:
        with backup.execution(route, options, reviewed):
            pytest.fail('Replaced physical backup directory admitted')
    assert error.value.rejected and error.value.nothing_changed
    assert not list(parent.iterdir())


def test_visual_validate_admits_level_guid_direct_io_and_clean_history_options(tmp_path):
    route, options = inputs(tmp_path)
    client = _create_client(
        Mock(), attachment_mode='embedded',
        profile=embedded.PROFILE, administration=embedded.ADMINISTRATION,
    )
    context = SimpleNamespace(
        endpoint_id='owned', mode='provider_native',
        runtime_verification_state='verified',
        declared_runtime_family='firebird', verified_runtime_family='firebird',
    )
    visual = ProviderVisualAdministration(
        context, SimpleNamespace(require=Mock(), allows=lambda *_: True),
        'firebird', '5.0.4', client,
    )
    try:
        draft = {
            **options,
            'database_guid': '{11111111-2222-3333-4444-555555555555}',
            'backup_level': None,
            'direct_io_mode': 'OFF',
            'backup_flags': ['NO_TRIGGERS'],
            'clean_history': True,
            'history_keep_unit': 'ROWS',
            'history_keep_value': 5,
        }
        result = visual.validate({
            'resource_kind': 'database',
            'operation_id': 'backup_physical',
            '_provider_route': route,
            'target_resource': {'resource_kind': 'database', 'display_name': 'Owned'},
            'draft': draft,
        })
        assert result['valid'], result
        assert result['draft']['direct_io_mode'] == 'OFF'

        planned = embedded.ADMINISTRATION.plan({
            'resource_kind': 'database',
            'operation_id': 'backup_physical',
            '_provider_route': route,
            'target_resource': {'resource_kind': 'database', 'display_name': 'Owned'},
            'draft': result['draft'],
        })
        compiled_opts = planned['provider_payload']['compiled']['options']
        assert compiled_opts['direct_io'] is False
        assert 'direct_io_mode' not in compiled_opts

        Path(options['backup_file']).write_bytes(b'already here')
        conflict = visual.validate({
            'resource_kind': 'database',
            'operation_id': 'backup_physical',
            '_provider_route': route,
            'target_resource': {'resource_kind': 'database', 'display_name': 'Owned'},
            'draft': options,
        })
        assert not conflict['valid']
        assert any(err['code'] == 'invalid_local_backup' for err in conflict['errors'])
    finally:
        client.close()

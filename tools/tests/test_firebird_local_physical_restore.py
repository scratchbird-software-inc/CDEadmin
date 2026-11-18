"""Local physical restore (nrestore) pins backup inodes and validates native modes."""
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.firebird import local_physical_restore as restore
from pgadmin.cdeadmin.providers.firebird import local_services as local
from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
from pgadmin.cdeadmin.providers.firebird.provider import _create_client
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.visual_admin import ProviderVisualAdministration


def inputs(tmp_path):
    b0 = tmp_path / "full 雪's.nbk"
    b1 = tmp_path / 'inc1.nbk'
    b0.write_bytes(b'owned native level 0 backup bytes')
    b1.write_bytes(b'owned native level 1 backup bytes')
    route = {
        'attachment_mode': 'embedded',
        'database': str(tmp_path / 'missing-parent' / 'old.fdb'),
        'filesystem_root': str(tmp_path),
        'user': 'SYSDBA',
    }
    options = {
        'backup_files': [str(b0), str(b1)],
        'restore_database': str(tmp_path / 'restored.fdb'),
    }
    return route, options


def test_new_database_restore_pins_ordered_inputs_without_pre_restore_sql(tmp_path):
    route, options = inputs(tmp_path)
    grid_options = {
        **options,
        'backup_files': [{'value': path, '_id': idx} for idx, path in enumerate(options['backup_files'])],
    }
    selected = local.validate_operation(route, 'restore_physical', options['restore_database'], grid_options)
    assert selected['database'] == options['restore_database']
    reviewed = restore.selection(selected, grid_options)
    assert reviewed['in_place'] is False
    assert reviewed['outputs'][0]['existing'] is None
    assert reviewed['inputs'][0]['sha256'] == hashlib.sha256(Path(options['backup_files'][0]).read_bytes()).hexdigest()
    assert reviewed['inputs'][1]['sha256'] == hashlib.sha256(Path(options['backup_files'][1]).read_bytes()).hexdigest()

    with restore.execution(selected, options, reviewed) as records, local.restore_target(selected):
        native = restore.dispatch_options(options)
        assert len(native['backup_files']) == 2
        assert Path(native['backup_files'][0]).read_bytes() == b'owned native level 0 backup bytes'
        assert Path(native['backup_files'][1]).read_bytes() == b'owned native level 1 backup bytes'
        assert native['restore_database'] == options['restore_database']
        assert local.dispatch_target(options['restore_database']) == options['restore_database']
        obs = restore.observations(records, reviewed)
        assert obs['inputs_unchanged'] is True
        assert obs['data_readback_verified'] is False
    assert not Path(native['backup_files'][0]).exists()
    assert not Path(options['restore_database']).exists()


@pytest.mark.parametrize('change', ['content', 'inode', 'destination', 'directory'])
def test_stale_physical_inputs_or_targets_refuse_before_dispatch(tmp_path, change):
    route, options = inputs(tmp_path)
    directory = tmp_path / 'dest'
    directory.mkdir()
    options['restore_database'] = str(directory / 'new.fdb')
    reviewed = restore.selection(route, options)
    first_input = Path(options['backup_files'][0])
    if change == 'content':
        first_input.write_bytes(b'mutated bytes')
    elif change == 'inode':
        first_input.rename(tmp_path / 'retained.nbk')
        first_input.write_bytes(b'owned native level 0 backup bytes')
    elif change == 'destination':
        Path(options['restore_database']).write_bytes(b'foreign database')
    else:
        directory.rename(tmp_path / 'retained-dir')
        directory.mkdir()
    with pytest.raises(RelationalClientError) as error:
        with restore.execution(route, options, reviewed):
            pytest.fail('Changed physical restore selection admitted')
    assert error.value.rejected and error.value.nothing_changed


def test_input_filename_replacement_cannot_redirect_pinned_physical_read(tmp_path):
    route, options = inputs(tmp_path)
    reviewed = restore.selection(route, options)
    with restore.execution(route, options, reviewed) as records:
        native = restore.dispatch_options(options)
        first = Path(options['backup_files'][0])
        first.rename(tmp_path / 'retained.nbk')
        first.write_bytes(b'foreign replacement')
        assert Path(native['backup_files'][0]).read_bytes() == b'owned native level 0 backup bytes'
        obs = restore.observations(records, reviewed)
        assert not obs['inputs_unchanged']
        assert not obs['backup_inputs'][0]['requested_path_still_names_input']
        assert obs['backup_inputs'][1]['requested_path_still_names_input']
    assert Path(options['backup_files'][0]).read_bytes() == b'foreign replacement'


def test_in_place_restore_requires_existing_database_exact_confirmation_and_no_input_overlap(tmp_path):
    route, options = inputs(tmp_path)
    dest = Path(options['restore_database'])
    in_place_base = {**options, 'restore_flags': ['IN_PLACE']}
    with pytest.raises(RelationalClientError):
        restore.selection(route, {**in_place_base, 'confirmation': str(dest)})

    dest.write_bytes(b'owned offline target database')
    with pytest.raises(RelationalClientError):
        restore.selection(route, options)
    for bad in (in_place_base, {**in_place_base, 'confirmation': 'wrong'}):
        with pytest.raises(RelationalClientError):
            restore.selection(route, bad)

    confirmed = {**in_place_base, 'confirmation': str(dest)}
    reviewed = restore.selection(route, confirmed)
    assert reviewed['in_place'] is True
    assert reviewed['outputs'][0]['existing']['bytes'] == len(b'owned offline target database')
    with restore.execution(route, confirmed, reviewed):
        native = restore.dispatch_options(confirmed)
        assert 'confirmation' not in native

    dest.unlink()
    dest.hardlink_to(options['backup_files'][0])
    with pytest.raises(RelationalClientError):
        restore.selection(route, confirmed)


def test_duplicate_or_empty_backup_inputs_are_refused(tmp_path):
    route, options = inputs(tmp_path)
    alias = tmp_path / 'alias.nbk'
    alias.hardlink_to(options['backup_files'][0])
    with pytest.raises(RelationalClientError):
        restore.selection(route, {**options, 'backup_files': [options['backup_files'][0], str(alias)]})
    empty = tmp_path / 'empty.nbk'
    empty.write_bytes(b'')
    with pytest.raises(RelationalClientError):
        restore.selection(route, {**options, 'backup_files': [str(empty)]})


def test_missing_in_place_confirmation_is_a_field_error_before_planning(tmp_path):
    route, options = inputs(tmp_path)
    Path(options['restore_database']).write_bytes(b'owned offline target database')
    client = _create_client(
        Mock(), attachment_mode='embedded',
        profile=embedded.PROFILE, administration=embedded.ADMINISTRATION,
    )
    visual = ProviderVisualAdministration(
        SimpleNamespace(
            endpoint_id='owned', mode='provider_native',
            runtime_verification_state='verified',
            declared_runtime_family='firebird', verified_runtime_family='firebird',
        ),
        SimpleNamespace(require=Mock(), allows=lambda *_: True),
        'firebird', '5.0.4', client,
    )
    try:
        result = visual.validate({
            'resource_kind': 'database',
            'operation_id': 'restore_physical',
            '_provider_route': route,
            'draft': {**options, 'restore_flags': ['IN_PLACE']},
        })
        assert not result['valid']
        assert any(error['field_id'] == 'confirmation' for error in result['errors'])
    finally:
        client.close()

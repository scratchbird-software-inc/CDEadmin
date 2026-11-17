"""Local gbak cannot overwrite files or follow browser-supplied output aliases."""
from pathlib import Path
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.firebird import local_backup as backup
from pgadmin.cdeadmin.sdk import RelationalClientError


def inputs(tmp_path):
    source = tmp_path/'source.fdb'; source.write_bytes(b'owned database')
    route = {'attachment_mode': 'embedded', 'database': str(source), 'filesystem_root': str(tmp_path)}
    options = {'backup_file': str(tmp_path/'output 雪.fbk')}
    return route, options


def test_reserved_native_descriptor_is_pinned_to_new_output_inode(tmp_path):
    route, options = inputs(tmp_path)
    reviewed = backup.selection(route, options)
    with backup.reserve(route, options, reviewed) as records:
        native = backup.dispatch_options(options)
        assert native['backup_file'] != options['backup_file']
        with open(native['backup_file'], 'wb') as stream: stream.write(b'owned native bytes')
        assert Path(options['backup_file']).stat().st_mode & 0o777 == 0o600
        rows = backup.observations(records)
        assert rows[0]['requested_path_still_names_output'] and rows[0]['bytes_observed'] == 18
        assert rows[0]['restore_verified'] is False
        descriptor_path = native['backup_file']
    assert Path(options['backup_file']).read_bytes() == b'owned native bytes'
    assert not Path(descriptor_path).exists()


def test_new_file_after_review_and_existing_source_hardlink_are_never_overwritten(tmp_path):
    route, options = inputs(tmp_path); reviewed = backup.selection(route, options)
    target = Path(options['backup_file']); target.hardlink_to(route['database'])
    with pytest.raises(RelationalClientError):
        with backup.reserve(route, options, reviewed): pytest.fail('Existing output admitted')
    assert target.read_bytes() == b'owned database'
    for name in (route['database'], str(target)):
        with pytest.raises(RelationalClientError): backup.selection(route, {'backup_file': name})


@pytest.mark.parametrize('filename', ['relative.fbk', '/proc/self/fd/0', 'stdout', '../outside.fbk'])
def test_noncanonical_and_unapproved_output_paths_are_refused(tmp_path, filename):
    route, _ = inputs(tmp_path)
    with pytest.raises(RelationalClientError): backup.selection(route, {'backup_file': filename})


def test_replaced_output_parent_is_refused_before_any_reservation(tmp_path):
    route, _ = inputs(tmp_path)
    parent = tmp_path/'output'; parent.mkdir()
    options = {'backup_file': str(parent/'backup.fbk')}
    reviewed = backup.selection(route, options)
    parent.rename(tmp_path/'retained-parent'); parent.mkdir()
    with pytest.raises(RelationalClientError) as error:
        with backup.reserve(route, options, reviewed): pytest.fail('Replacement parent admitted')
    assert error.value.nothing_changed is True
    assert not list(parent.iterdir())


def test_output_path_replacement_does_not_redirect_native_writes(tmp_path):
    route, options = inputs(tmp_path)
    with backup.reserve(route, options, backup.selection(route, options)) as records:
        native = backup.dispatch_options(options)
        requested = Path(options['backup_file']); retained = tmp_path/'retained.fbk'
        requested.rename(retained); requested.write_bytes(b'foreign replacement')
        with open(native['backup_file'], 'wb') as stream: stream.write(b'actual backup')
        assert backup.observations(records)[0]['requested_path_still_names_output'] is False
        assert requested.read_bytes() == b'foreign replacement'
        assert retained.read_bytes() == b'actual backup'


def test_order_and_capacities_survive_native_mapping_and_partial_files_remain(tmp_path):
    route, _ = inputs(tmp_path)
    options = {'split_backup': True, 'backup_volumes': [
        {'filename': str(tmp_path/'first.fbk'), 'size_bytes': 2048},
        {'filename': str(tmp_path/'last.fbk')}]}
    with pytest.raises(RuntimeError):
        with backup.reserve(route, options, backup.selection(route, options)):
            native = backup.dispatch_options(options)
            assert native['backup_volumes'][0]['size_bytes'] == 2048
            assert native['backup_volumes'][0]['filename'] != native['backup_volumes'][1]['filename']
            raise RuntimeError('owned interrupted operation')
    assert (tmp_path/'first.fbk').exists() and (tmp_path/'last.fbk').exists()
    with pytest.raises(RelationalClientError): backup.dispatch_options(options)


def test_single_backup_path_is_admitted_when_split_controller_uses_declared_default(tmp_path):
    from pgadmin.cdeadmin.providers.firebird.provider import _create_client
    from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
    from pgadmin.cdeadmin.visual_admin import ProviderVisualAdministration
    route, options = inputs(tmp_path)
    client = _create_client(Mock(), attachment_mode='embedded', profile=embedded.PROFILE, administration=embedded.ADMINISTRATION)
    context = SimpleNamespace(endpoint_id='owned', mode='provider_native', runtime_verification_state='verified',
        declared_runtime_family='firebird', verified_runtime_family='firebird')
    visual = ProviderVisualAdministration(context, SimpleNamespace(require=Mock(), allows=lambda *_:True), 'firebird','5.0.4',client)
    try:
        result = visual.validate({'resource_kind':'database','operation_id':'backup_logical',
            '_provider_route':route, 'target_resource':{'resource_kind':'database','display_name':'Owned'}, 'draft':options})
        assert result['valid'], result
        assert result['draft']['backup_file'] == options['backup_file']
        assert result['draft']['split_backup'] is False
    finally: client.close()


def test_reservation_failure_after_first_file_does_not_claim_nothing_changed(tmp_path, monkeypatch):
    route, _ = inputs(tmp_path)
    options = {'split_backup':True, 'backup_volumes':[
        {'filename':str(tmp_path/'first.fbk'),'size_bytes':2048},
        {'filename':str(tmp_path/'last.fbk')}]}
    reviewed = backup.selection(route, options)
    native_open = os.open
    def race(path, *args, **kwargs):
        if path == 'last.fbk':
            (tmp_path/'last.fbk').write_bytes(b'foreign raced output')
        return native_open(path, *args, **kwargs)
    monkeypatch.setattr(backup.os, 'open', race)
    with pytest.raises(RelationalClientError) as error:
        with backup.reserve(route, options, reviewed): pytest.fail('Raced reservation admitted')
    assert getattr(error.value, 'nothing_changed', False) is not True
    assert (tmp_path/'first.fbk').read_bytes() == b''
    assert (tmp_path/'last.fbk').read_bytes() == b'foreign raced output'

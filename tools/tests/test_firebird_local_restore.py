"""Local restore binds exact backup bytes and explicit native destinations."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import hashlib

import pytest

from pgadmin.cdeadmin.providers.firebird import local_restore as restore
from pgadmin.cdeadmin.providers.firebird import local_services as local
from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
from pgadmin.cdeadmin.providers.firebird.provider import _create_client
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.visual_admin import ProviderVisualAdministration


def inputs(tmp_path):
    backup = tmp_path/"input 雪's.fbk"; backup.write_bytes(b'owned native backup bytes')
    route = {'attachment_mode':'embedded','database':str(tmp_path/'missing-parent'/'old.fdb'),
             'filesystem_root':str(tmp_path),'user':'SYSDBA'}
    options = {'backup_file':str(backup),'restore_database':str(tmp_path/'restored.fdb')}
    return route, options


def test_restore_admits_absent_destination_and_original_without_sql(tmp_path):
    route, options = inputs(tmp_path)
    selected = local.validate_operation(route, 'restore_logical', options['restore_database'], options)
    assert selected['database'] == options['restore_database']
    reviewed = restore.selection(selected, options)
    assert reviewed['outputs'][0]['existing'] is None
    assert reviewed['inputs'][0]['sha256'] == hashlib.sha256(Path(options['backup_file']).read_bytes()).hexdigest()
    with restore.execution(selected, options, reviewed) as records, local.restore_target(selected):
        native = restore.dispatch_options(options)
        assert Path(native['backup_file']).read_bytes() == b'owned native backup bytes'
        assert native['restore_database'] == options['restore_database']
        assert local.dispatch_target(options['restore_database']) == options['restore_database']
        assert not restore.observations(records, reviewed)['data_readback_verified']
    assert not Path(native['backup_file']).exists()
    assert not Path(options['restore_database']).exists()


@pytest.mark.parametrize('change', ['content','inode','destination','directory'])
def test_stale_inputs_or_output_targets_refuse_before_native_dispatch(tmp_path, change):
    route, options = inputs(tmp_path)
    directory = tmp_path/'dest'; directory.mkdir(); options['restore_database'] = str(directory/'new.fdb')
    reviewed = restore.selection(route, options)
    path = Path(options['backup_file'])
    if change == 'content': path.write_bytes(b'other bytes')
    elif change == 'inode': path.rename(tmp_path/'retained.fbk'); path.write_bytes(b'owned native backup bytes')
    elif change == 'destination': Path(options['restore_database']).write_bytes(b'foreign database')
    else: directory.rename(tmp_path/'retained-dir'); directory.mkdir()
    with pytest.raises(RelationalClientError) as error:
        with restore.execution(route, options, reviewed): pytest.fail('Changed restore selection admitted')
    assert error.value.rejected and error.value.nothing_changed


def test_input_filename_replacement_cannot_redirect_pinned_native_read(tmp_path):
    route, options = inputs(tmp_path); reviewed = restore.selection(route, options)
    with restore.execution(route, options, reviewed) as records:
        native = restore.dispatch_options(options)
        path = Path(options['backup_file']); path.rename(tmp_path/'retained.fbk'); path.write_bytes(b'foreign backup')
        assert Path(native['backup_file']).read_bytes() == b'owned native backup bytes'
        observation = restore.observations(records, reviewed)
        # Renaming the held input changes its ctime. Report that uncertainty
        # even though the descriptor still reads the exact original bytes.
        assert not observation['inputs_unchanged']
        assert not observation['backup_inputs'][0]['requested_path_still_names_input']
    assert Path(options['backup_file']).read_bytes() == b'foreign backup'


def test_replacement_requires_exact_confirmation_and_never_overwrites_input_inode(tmp_path):
    route, options = inputs(tmp_path); destination = Path(options['restore_database']); destination.write_bytes(b'owned primary')
    for draft in (options, {**options,'replace_existing':True}, {**options,'replace_existing':True,'confirmation':'wrong'}):
        with pytest.raises(RelationalClientError): restore.selection(route, draft)
    draft = {**options,'replace_existing':True,'confirmation':str(destination)}
    assert restore.selection(route, draft)['outputs'][0]['existing']
    destination.unlink(); destination.hardlink_to(options['backup_file'])
    with pytest.raises(RelationalClientError): restore.selection(route, draft)


def test_ordered_native_volumes_retain_bytes_and_database_file_page_allocations(tmp_path):
    route, options = inputs(tmp_path); extra = tmp_path/'extra.fbk'; extra.write_bytes(b'ordered volume two')
    draft = {**options,'additional_backup_files':[str(extra)],'multiple_database_files':True,
             'primary_file_pages':512,'database_file_volumes':[{'filename':str(tmp_path/'secondary.fdb')}]}
    reviewed = restore.selection(route,draft)
    with restore.execution(route,draft,reviewed):
        native = restore.dispatch_options(draft)
        assert Path(native['additional_backup_files'][0]).read_bytes() == b'ordered volume two'
        assert native['primary_file_pages'] == 512 and native['database_file_volumes'] == draft['database_file_volumes']
    alias = tmp_path/'alias.fbk'; alias.hardlink_to(extra)
    with pytest.raises(RelationalClientError): restore.selection(route,{**draft,'additional_backup_files':[str(extra),str(alias)]})


def test_missing_replacement_confirmation_is_a_field_error_before_planning(tmp_path):
    route, options = inputs(tmp_path); Path(options['restore_database']).write_bytes(b'owned primary')
    client = _create_client(Mock(),attachment_mode='embedded',profile=embedded.PROFILE,administration=embedded.ADMINISTRATION)
    visual = ProviderVisualAdministration(SimpleNamespace(endpoint_id='owned',mode='provider_native',
        runtime_verification_state='verified',declared_runtime_family='firebird',verified_runtime_family='firebird'),
        SimpleNamespace(require=Mock(),allows=lambda *_:True),'firebird','5.0.4',client)
    try:
        result = visual.validate({'resource_kind':'database','operation_id':'restore_logical',
            '_provider_route':route,'draft':{**options,'replace_existing':True}})
        assert not result['valid'] and any(error['field_id']=='confirmation'for error in result['errors'])
    finally: client.close()

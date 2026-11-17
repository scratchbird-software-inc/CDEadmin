"""Local recovery admits the explicit shadow, independently of the old primary."""
from pathlib import Path
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.firebird import local_services as local
from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine


def inputs(tmp_path):
    shadow = tmp_path/'recovery 雪.shd'; shadow.write_bytes(b'owned test header')
    route = {'attachment_mode': 'embedded', 'database': str(tmp_path/'missing-parent'/'primary.fdb'),
             'filesystem_root': str(tmp_path), 'user': 'SYSDBA'}
    options = {'shadow_filename': str(shadow), 'confirmation': str(shadow), 'original_isolated': True}
    return route, shadow, options


def test_recovery_binds_existing_shadow_with_absent_original_and_parent(tmp_path):
    route, shadow, options = inputs(tmp_path)
    selected = local.validate_operation(route, 'activate_shadow', str(shadow), options)
    assert selected['database'] == str(shadow) and selected['filesystem_root'] == route['filesystem_root']
    assert not Path(route['database']).parent.exists()
    client = Mock()
    with local.service_filename(client, selected, local.file_identity(selected), 'activate_shadow', options) as fenced:
        assert not fenced
        assert local.dispatch_target(str(shadow)) == str(shadow)
        client._connect.assert_not_called()
    assert shadow.read_bytes() == b'owned test header'
    assert not list(tmp_path.glob('.scratchrobin-*'))


@pytest.mark.parametrize('changed', [
    {'original_isolated': False}, {'original_isolated': 1}, {'confirmation': 'different'},
    {'shadow_filename': 'relative.shd'}, {'password': 'never acquired'}, {'host': 'remote'},
])
def test_unsafe_or_unconfirmed_targets_are_rejected_without_native_access(tmp_path, changed):
    route, shadow, options = inputs(tmp_path)
    with pytest.raises(RelationalClientError):
        local.validate_operation(route, 'activate_shadow', str(shadow), {**options, **changed})


def test_primary_hardlink_and_symlink_substitutions_are_not_recovery_targets(tmp_path):
    route, shadow, options = inputs(tmp_path)
    primary = tmp_path/'primary.fdb'; primary.write_bytes(b'primary')
    route['database'] = str(primary)
    alias = tmp_path/'same-primary.shd'; alias.hardlink_to(primary)
    for target in (primary, alias):
        with pytest.raises(RelationalClientError):
            local.validate_operation(route, 'activate_shadow', str(target), {
                **options, 'shadow_filename': str(target), 'confirmation': str(target)})
    link = tmp_path/'shadow-link'; link.symlink_to(shadow)
    with pytest.raises(RelationalClientError):
        local.validate_operation(route, 'activate_shadow', str(link), {
            **options, 'shadow_filename': str(link), 'confirmation': str(link)})


def test_root_escape_network_credentials_and_compiled_target_mismatch_are_refused(tmp_path):
    route, shadow, options = inputs(tmp_path)
    for invalid in ({**route, 'host': 'remote'}, {**route, 'credential_reference_id': 'other'},
                    {**route, 'database': str(tmp_path.parent/'outside.fdb')}):
        with pytest.raises(RelationalClientError):
            local.validate_operation(invalid, 'activate_shadow', str(shadow), options)
    with pytest.raises(RelationalClientError):
        local.validate_operation(route, 'activate_shadow', str(tmp_path/'different.shd'), options)


def test_local_recovery_keeps_attachment_free_shared_form_and_native_warning():
    catalog = embedded.ADMINISTRATION.catalog(catalog_for_engine('firebird'))
    operation = next(op for kind in catalog['objects'] if kind['resource_kind'] == 'database'
                     for op in kind['operations'] if op['operation_id'] == 'activate_shadow')
    assert operation['workspace_scope'] == 'server_service' and operation['target_required'] is False
    assert {field['field_id'] for field in operation['form']['fields']} == {
        'shadow_filename', 'confirmation', 'original_isolated', 'role'}
    assert 'original' in operation['form']['fields'][0]['help'].lower()

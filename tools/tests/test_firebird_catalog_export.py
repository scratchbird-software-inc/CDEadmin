"""Documentary DDN export scope, exact metadata and generation admission."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import _create_client  # noqa: F401
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService, ProviderWorkspaceError


def resource(key, kind='table', **native):
    return {'resource_id': key, 'resource_kind': kind, 'display_name': key,
            'display_path': [key], 'extensions': {'firebird': {'native': native}}}


def export(items, **options):
    return build_export(items, endpoint_id='endpoint', target_id='target',
                        generation='generation', **options)


def test_metadata_exactness_and_coverage_survive_documentary_mapping():
    result = export([resource('db', 'database', catalog_observations=[
        {'section': 'tables', 'available': True}, {'section': 'users', 'available': False}],
        catalog_warnings=['Users unavailable']), resource('"T ü', ddl='CREATE TABLE "T ü" (V INT128)',
        sequence_value=2**100)])
    source = result['snapshot']['files']['catalog.ddn']
    assert str(2**100) in source
    assert 'CREATE TABLE' in source
    assert result['provenance']['coverage'] == 'partial'
    assert result['provenance']['warnings'] == ['Users unavailable']
    assert result['provenance']['deployment'] == 'documentary-only'
    assert 'unknown' == export([])['provenance']['coverage']
    assert json.loads(json.dumps(result)) == result


def test_branch_uses_native_parent_identity_not_ambiguous_names():
    rows = [resource('table'), resource('column', 'column', navigator_parent_resource_id='table'),
            resource('unrelated', 'domain'), resource('system', system_object=True),
            resource('backup-task', 'service-operation')]
    selected = export(rows, resource_id='table')
    assert selected['provenance']['objects'] == 2
    assert export(rows)['provenance']['objects'] == 3
    assert export(rows, include_system=True)['provenance']['objects'] == 4
    with pytest.raises(ValueError):
        export(rows, resource_id='foreign')
    with pytest.raises(ValueError):
        export([rows[0], rows[0]])


def test_view_bound_does_not_drop_source_objects_and_large_export_fails(monkeypatch):
    rows = [resource(str(i)) for i in range(205)]
    result = export(rows)
    source = result['snapshot']['files']['catalog.ddn']
    assert source.count('element "catalog_') == 205
    assert len(result['views']) == 3
    assert source.count('id "catalog_1.o_') == 300
    assert source.count('id "catalog_2.o_') == 300
    assert source.count('id "catalog_3.o_') == 15
    monkeypatch.setattr('pgadmin.cdeadmin.workspace.firebird_catalog_export.MAX_BYTES', 10)
    with pytest.raises(ValueError, match='8 MiB'):
        export(rows)


def service():
    instance = object.__new__(ProviderWorkspaceService)
    instance.endpoint_service = Mock()
    instance.resource_service = Mock()
    instance.endpoint_service.database_catalog.return_value = {
        'targets': [{'target_id': 'target', 'database': 'demo.fdb'}]}
    instance.endpoint_service.workspace.return_value = (
        SimpleNamespace(endpoint_id='88239846-0810-44a3-a28c-aaec7aa25bab'),
        {'route': {'database': 'demo.fdb', 'credential_reference_id': 'SECRET-REFERENCE'}}, {})
    instance.resource_service.list_page.return_value.to_dict.return_value = {
        'generation': 'current', 'items': [resource('table')], 'next_cursor': None}
    server = SimpleNamespace(endpoint_profile=SimpleNamespace(profile_id='firebird-native'))
    return instance, server


def test_host_binds_target_and_preserves_generation_and_no_route_leak():
    value, server = service()
    result = value.export_firebird_catalog(server, {'generation': 'current', 'database_target_id': 'target'})
    assert result['provenance']['database_target_id'] == 'target'
    assert 'SECRET-REFERENCE' not in str(result)
    value.endpoint_service.workspace.assert_called_once_with(server, database_target_id='target')
    assert value.resource_service.list_page.call_args.kwargs['expected_generation'] == 'current'
    value.resource_service.invalidate.assert_not_called()
    for request in ({'generation': 'current', 'refresh': 'true'},
                    {'generation': 'current', 'route': {}}, {}):
        with pytest.raises(ProviderWorkspaceError):
            value.export_firebird_catalog(server, request)


def test_stale_generation_is_refused_before_refresh_and_no_partial_export():
    value, server = service()
    value.resource_service.list_page.side_effect = RuntimeError('stale')
    with pytest.raises(RuntimeError, match='stale'):
        value.export_firebird_catalog(server, {'generation': 'old', 'refresh': True})
    value.resource_service.invalidate.assert_not_called()


def test_explicit_refresh_keeps_selected_native_identity():
    value, server = service()
    value.export_firebird_catalog(server, {'generation': 'current', 'database_target_id': 'target',
                                         'refresh': True, 'resource_id': 'table'})
    value.resource_service.inspect.assert_called_once()
    value.resource_service.invalidate.assert_called_once()
    assert value.resource_service.list_page.call_count == 2


def test_public_ddn_parser_preserves_quoted_unicode_and_large_integer_metadata():
    import subprocess
    from pathlib import Path
    rows = [resource('"quoted\\name ü𝟘', value=2**100,
                     ddl='CREATE TABLE "quoted" (V VARCHAR(5));\n-- statement source')]
    rows.extend(resource(str(i), position=i) for i in range(205))
    result = export(rows)
    checked = subprocess.run(['node', str(Path(__file__).with_name('check_firebird_catalog_ddn.mjs'))],
                             input=json.dumps(result), capture_output=True, text=True,
                             timeout=20, check=True)
    from pgadmin.cdeadmin.workspace.firebird_catalog_export import native_metadata
    recovered = {key: json.loads(value) for key, value in json.loads(checked.stdout).items()}
    assert recovered == {row['resource_id']: native_metadata(row) for row in rows}


def test_default_target_provenance_matches_captured_route_not_changed_active_target():
    value, server = service()
    value.endpoint_service.database_catalog.return_value = {
        'active_target_id': 'new-active', 'targets': [
            {'target_id': 'captured', 'database': 'demo.fdb'},
            {'target_id': 'new-active', 'database': 'other.fdb'}]}
    result = value.export_firebird_catalog(server, {'generation': 'current'})
    assert result['provenance']['database_target_id'] == 'captured'
    value.endpoint_service.database_catalog.return_value['targets'] = []
    with pytest.raises(ProviderWorkspaceError, match='registered database'):
        value.export_firebird_catalog(server, {'generation': 'current'})


def test_visual_identity_includes_registered_database_not_just_endpoint():
    one = build_export([resource('table')], endpoint_id='server', target_id='db-one', generation='g')
    two = build_export([resource('table')], endpoint_id='server', target_id='db-two', generation='g')
    assert 'firebird:server:db-one:table' in one['snapshot']['files']['catalog.ddn']
    assert 'firebird:server:db-two:table' in two['snapshot']['files']['catalog.ddn']


def test_host_native_capture_does_not_require_a_large_visual_document():
    from decimal import Decimal
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog, compare_catalogs
    rows = [resource('large', exact=2**100, decimal=0.125, definition='x' * 2100000)]
    with pytest.raises(ValueError, match='paired DDN per-file limit'):
        export(rows)
    captured = export(rows, native_model=True)
    assert captured['rows']['large']['native']['exact'] == 2**100
    assert captured['rows']['large']['native']['decimal'] == Decimal('0.125')
    assert captured['format'] == 'scratchrobin.firebird.native-capture@1'
    small = [resource('ordinary', exact=2**100, decimal=0.125)]
    source = export(small)['snapshot']['files']['catalog.ddn']
    compared = compare_catalogs(read_catalog(source), export(small, native_model=True))
    assert compared['counts']['equal'] == 1
    assert compared['current_hash_format'] == captured['format']


def test_multifile_workspace_roundtrip_and_every_view():
    import hashlib
    import subprocess
    from pathlib import Path
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
    rows = [resource(str(i), definition='ü😀' * 18000, exact=2**100) for i in range(42)]
    result = export(rows)
    assert len(result['snapshot']['files']) > 1
    assert result['filename'].endswith('.ddn-workspace.json')
    source = result['download_text']
    assert result['sha256'] == hashlib.sha256(source.encode()).hexdigest()
    parsed = read_catalog(source)
    assert parsed['sha256'] == result['sha256']
    assert len(parsed['rows']) == len(rows)
    for row in rows:
        recovered = parsed['rows'][row['resource_id']]
        assert recovered['native'] == row['extensions']['firebird']['native']
        assert recovered['source_location']['file'] in result['snapshot']['files']
    checker = Path(__file__).with_name('check_firebird_catalog_ddn.mjs')
    run = subprocess.run(['node', str(checker)], input=json.dumps(result),
                         text=True, capture_output=True, timeout=30)
    assert run.returncode == 0, run.stderr
    assert len(json.loads(run.stdout)) == len(rows)


@pytest.mark.parametrize('mutation', ['duplicate', 'path', 'entry', 'view', 'extra', 'provenance'])
def test_workspace_rejects_ambiguous_or_unsupported_envelopes(mutation):
    from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
    snapshot = export([resource('one')])['snapshot']
    if mutation == 'duplicate':
        source = json.dumps(snapshot).replace('"format":', '"format":"duplicate","format":', 1)
    else:
        if mutation == 'path':
            snapshot['files']['../catalog.ddn'] = snapshot['files'].pop('catalog.ddn')
            snapshot['entry'] = '../catalog.ddn'
        elif mutation == 'entry':
            snapshot['entry'] = 'missing.ddn'
        elif mutation == 'view':
            snapshot['view'] = 'missing'
        elif mutation == 'extra':
            snapshot['url'] = 'https://example.invalid/'
        elif mutation == 'provenance':
            snapshot['files']['catalog-2.ddn'] = snapshot['files']['catalog.ddn']
        source = json.dumps(snapshot)
    with pytest.raises(ValueError):
        read_catalog(source)

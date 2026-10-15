"""Public-parser import, exact documentary comparisons and scope rejection."""
import json
from unittest.mock import patch

import pytest

from tools.tests.test_firebird_catalog_export import export, resource, service
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog, compare_catalogs
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceError


def source(rows):
    return export(rows)['snapshot']['files']['catalog.ddn']


def test_exact_roundtrip_pages_empty_and_large_integers():
    items = [resource('"quoted ü', number=2**100, ddl='CREATE TABLE "x" (v INT128);')]
    items.extend(resource(str(i), ordinal=i) for i in range(205))
    document = read_catalog(source(items))
    assert len(document['rows']) == 206
    assert document['rows']['"quoted ü']['native']['number'] == 2**100
    assert compare_catalogs(document, document)['counts']['equal'] == 206
    assert read_catalog(source([]))['rows'] == {}


def test_comparison_keeps_types_missing_null_and_array_order():
    old = read_catalog(source([resource('change', number=2**100, flag=True, values=[1, 2], optional=None),
                               resource('old'), resource('same')]))
    new = read_catalog(source([resource('change', number=2**100 + 1, flag=1, values=[2, 1]),
                               resource('new'), resource('same')]))
    result = compare_catalogs(old, new)
    assert result['counts'] == {'equal': 1, 'changed': 1, 'document-only': 1, 'current-only': 1}
    assert result['changes'][0]['fields'] == ['native.flag', 'native.number', 'native.optional', 'native.values']
    assert result['mode'] == 'documentary-only'
    assert 'sql' not in result
    new['provenance']['database_target_id'] = 'other'
    with pytest.raises(ValueError, match='different endpoint'):
        compare_catalogs(old, new)


@pytest.mark.parametrize('mutate', [
    lambda text: text.replace('scratchrobin.firebird.catalog@1', 'scratchrobin.firebird.catalog@2'),
    lambda text: text.replace('firebird:endpoint:target:', 'firebird:endpoint:other:'),
    lambda text: text.replace('catalog_1', 'unrelated'),
    lambda text: text + ' data hidden {record a {}}',
    lambda text: text.replace('data catalog_1', 'import "file:///private.ddn" as remote; data catalog_1'),
    lambda text: text.replace('native_json:"{}"', 'native_json:"{\\"a\\":1,\\"a\\":2}"'),
    lambda text: text.replace('native_json:"{}"', 'native_json:"{\\"a\\":NaN}"'),
    lambda text: text.replace('native_json:"{}"', 'native_json:"[]"'),
    lambda text: text.replace('path_json:"[\\"table\\"]"', 'path_json:"[42]"'),
    lambda text: text.replace('system:"unknown"', 'system:"true"'),
    lambda text: text.replace('\\"objects\\":1', '\\"objects\\":0'),
])
def test_malformed_or_inconsistent_documents_are_rejected(mutate):
    text = source([resource('table')])
    altered = mutate(text)
    assert altered != text
    with pytest.raises(ValueError):
        read_catalog(altered)


def test_duplicate_records_and_resource_identity_are_rejected():
    text = source([resource('table'), resource('other')])
    with pytest.raises(ValueError):
        read_catalog(text.replace('resource_id:"other"', 'resource_id:"table"'))
    start, end = text.index('record o_'), text.index('\nview ')
    with pytest.raises(ValueError):
        read_catalog(text[:start] + text[start:end] + text[start:])


def test_host_authorization_precedes_untrusted_parser_and_route_comes_from_host():
    value, server = service()
    captured = value.export_firebird_catalog(server, {'generation': 'current'})
    text = captured['snapshot']['files']['catalog.ddn']
    result = value.compare_firebird_catalog(server, {'source': text, 'generation': 'current'})
    assert result['counts']['equal'] == 1
    with pytest.raises(ProviderWorkspaceError):
        value.compare_firebird_catalog(server, {'source': text, 'generation': 'current', 'route': {}})
    value.endpoint_service.workspace.side_effect = RuntimeError('Unauthorized')
    with patch('pgadmin.cdeadmin.workspace.firebird_catalog_import.read_catalog') as parser:
        with pytest.raises(RuntimeError, match='Unauthorized'):
            value.compare_firebird_catalog(server, {'source': text, 'generation': 'current'})
        parser.assert_not_called()


def test_source_bounds_and_parser_unavailability():
    for value in ('', None, 'x' * (8 * 1024 * 1024 + 1)):
        with pytest.raises(ValueError):
            read_catalog(value)
    with pytest.raises(ValueError, match='could not admit'):
        read_catalog(source([]), node='/nonexistent/catalog-node')


def test_paired_parser_character_limit_is_checked_before_starting_a_process():
    with patch('pgadmin.cdeadmin.workspace.firebird_catalog_import.subprocess.run') as runner:
        with pytest.raises(ValueError, match='paired DDN per-file limit'):
            read_catalog('x' * 2000001)
        # Astral characters occupy two UTF-16 units, as counted by the public JS parser.
        with pytest.raises(ValueError, match='paired DDN per-file limit'):
            read_catalog('𝟘' * 1000001)
        runner.assert_not_called()


def imported_workspace(text):
    start = text.index('view inventory_1')
    model, view = text[:start], text[start:]
    model = model.replace('module "scratchrobin.firebird.catalog"', 'module "scratchrobin.firebird.catalog.model"')
    view = 'ddn "0.7"; import "../models/native.ddn" as native; module "scratchrobin.firebird.catalog.views";\n' + view.replace('@catalog_', '@native.catalog_')
    return {'format': 'ddn-workspace@1', 'entry': 'views/catalog.ddn', 'view': 'inventory_1',
            'files': {'models/native.ddn': model, 'views/catalog.ddn': view}}


def test_workspace_imports_preserve_native_records_and_file_locations():
    snapshot = imported_workspace(source([resource('exact ü', number=2**100)]))
    value = read_catalog(json.dumps(snapshot))
    assert value['rows']['exact ü']['native']['number'] == 2**100
    assert value['rows']['exact ü']['source_location']['file'] == 'models/native.ddn'
    assert compare_catalogs(value, value)['counts']['equal'] == 1


@pytest.mark.parametrize('path', ['../../private.ddn', 'https://example.org/native.ddn', 'file:///etc/native.ddn', '../missing.ddn'])
def test_imports_cannot_leave_the_admitted_file_set(path):
    snapshot = imported_workspace(source([resource('table')]))
    snapshot['files']['views/catalog.ddn'] = snapshot['files']['views/catalog.ddn'].replace('../models/native.ddn', path)
    with pytest.raises(ValueError):
        read_catalog(json.dumps(snapshot))


def test_invalid_hidden_view_and_import_cycle_are_rejected():
    snapshot = imported_workspace(source([resource('table')]))
    snapshot['files']['views/catalog.ddn'] += '\nview broken {data:[@native.missing];}'
    with pytest.raises(ValueError):
        read_catalog(json.dumps(snapshot))
    snapshot = imported_workspace(source([resource('table')]))
    snapshot['files']['models/native.ddn'] += '\nimport "../views/catalog.ddn" as cycle;'
    with pytest.raises(ValueError):
        read_catalog(json.dumps(snapshot))


def test_invalid_source_retains_coded_file_offset_without_source_text():
    with pytest.raises(ValueError) as failure:
        read_catalog('ddn "0.7"; module "scratchrobin.firebird.catalog"; invalid_secret_source')
    assert 'DDN_PARSE' in str(failure.value)
    assert 'catalog.ddn' in str(failure.value)
    assert 'offset' in str(failure.value)
    assert 'invalid_secret_source' not in str(failure.value)

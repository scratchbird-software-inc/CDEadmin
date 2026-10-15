"""Static DDN data preserves native typed values and cannot execute metadata."""
from copy import deepcopy
import json
import pytest
from tools.cdeadmin_firebird_admin_mapping_gate import _create_client  # noqa: F401
from pgadmin.cdeadmin.workspace.firebird_data_ddn import build, read
from pgadmin.cdeadmin.workspace.firebird_data_import import preview
from tools.tests.test_firebird_data_import import fixture


def test_exact_values_and_metadata_roundtrip_through_public_ddn_records():
    document, _ = fixture()
    document['tables'][0]['rows'] = [{'ID': str(2**100), 'VALUE': '123.4500', 'CALCULATED': None,
        'BIN': {'encoding': 'base64', 'data': 'AP8=', 'byte_length': 2},
        'ARR': ['-1', '0', '1'], 'TXT': 'é\r\n', 'EMPTY': '', 'FLOAT': '-0.0'}]
    result = build(document)
    decoded = json.loads(read(result['download_text']))
    assert decoded == document
    assert result['binding'] == 'static-export'
    assert result['row_identity'] == 'export ordinal, not a native key'


def test_import_review_uses_destination_facts_and_never_embedded_ddl():
    document, current = fixture()
    result = preview(read(build(document)['download_text']), current)
    assert result['metadata_execution'] is False
    assert result['operations'][0]['values'] == {'ID': 42, 'VALUE': 7}
    assert 'DROP DATABASE' not in json.dumps(result)


def test_paged_sources_preserve_all_rows_and_omission_is_not_empty():
    document, _ = fixture()
    document['tables'][0]['rows'] *= 205
    document['row_count'] = 205
    result = build(document)
    assert len(result['views']) == 3
    assert len(json.loads(read(result['download_text']))['tables'][0]['rows']) == 205
    edited = deepcopy(result['snapshot'])
    source = edited['files']['data.ddn']
    start = source.index('record r_0_0 ')
    end = source.index('record r_0_1 ')
    edited['files']['data.ddn'] = source[:start]+source[end:]
    with pytest.raises(ValueError):
        read(json.dumps(edited))


def test_empty_data_tables_keep_columns_and_static_provenance():
    document, _ = fixture()
    document['tables'][0]['rows'] = []
    document['row_count'] = 0
    assert json.loads(read(build(document)['download_text'])) == document


def test_native_import_accepts_the_ddn_workspace_directly():
    document, current = fixture()
    result = preview(build(document)['download_text'], current)
    assert result['metadata_execution'] is False
    assert result['operations'][0]['values'] == {'ID': 42, 'VALUE': 7}


def test_row_uid_must_agree_with_canonical_export_ordinal():
    document, _ = fixture()
    result = build(document)
    edited = deepcopy(result['snapshot'])
    edited['files']['data.ddn'] = edited['files']['data.ddn'].replace('firebird-data:0:0', 'firebird-data:0:999')
    with pytest.raises(ValueError):
        read(json.dumps(edited))


def test_single_source_ddn_header_accepts_legal_line_break():
    document, current = fixture()
    source = build(document)['snapshot']['files']['data.ddn'].replace('ddn "0.7";', 'ddn\n"0.7";')
    result = preview(source, current)
    assert result['operations'][0]['values'] == {'ID':42, 'VALUE':7}

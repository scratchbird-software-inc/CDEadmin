"""DuckDB file administration exposes native options and real logical roundtrip."""

import os
from pathlib import Path

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.provider import ADMINISTRATION
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.visual_admin import catalog_for_engine


def request(operation, root, database, directory=None, **draft):
    return {'operation_id': operation, 'target_resource': {'display_name': Path(database).stem},
        '_provider_route': {'database': str(database), 'filesystem_root': str(root)},
        'draft': ({'directory': str(directory), **draft} if directory else draft)}


def test_native_file_forms_have_only_supported_options():
    export = ADMINISTRATION._form('database', 'export_database')
    imported = ADMINISTRATION._form('database', 'import_database')
    assert [field['field_id'] for field in export['fields']] == ['directory', 'format']
    assert [item['value'] for item in export['fields'][1]['options']] == ['PARQUET', 'CSV']
    assert [field['field_id'] for field in imported['fields']] == ['directory']
    for operation in ('checkpoint', 'force_checkpoint', 'vacuum', 'analyze'):
        assert ADMINISTRATION._form('database', operation)['fields'] == []
    catalog = ADMINISTRATION.catalog(catalog_for_engine('duckdb'))
    database = next(item for item in catalog['objects'] if item['resource_kind'] == 'database')
    operations = {item['operation_id']: item for item in database['operations']}
    assert [field['field_id'] for field in operations['export_database']['form']['fields']] == ['directory', 'format']
    assert [field['field_id'] for field in operations['import_database']['form']['fields']] == ['directory']


def test_native_export_import_and_maintenance_roundtrip(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    origin, target, directory = tmp_path/'origin.duckdb', tmp_path/'target.duckdb', tmp_path/'export'
    source = duckdb.connect(str(origin))
    try:
        source.execute('CREATE TABLE facts(id INTEGER PRIMARY KEY, label VARCHAR)')
        source.execute("INSERT INTO facts VALUES (1, 'first')")
        for operation in ('analyze', 'vacuum', 'checkpoint', 'force_checkpoint'):
            compiled = ADMINISTRATION._compile_duckdb_database_operation(request(operation, tmp_path, origin))
            assert len(duckdb.extract_statements(compiled['statements'][0]['source'])) == 1
            source.execute(compiled['statements'][0]['source'])
        exported = ADMINISTRATION._compile_duckdb_database_operation(
            request('export_database', tmp_path, origin, directory, format='PARQUET'))
        assert any('not a physical backup' in text for text in exported['warnings'])
        source.execute(exported['statements'][0]['source'])
        assert (directory/'schema.sql').is_file() and (directory/'load.sql').is_file()
    finally:
        source.close()
    destination = duckdb.connect(str(target))
    try:
        imported = ADMINISTRATION._compile_duckdb_database_operation(
            request('import_database', tmp_path, target, directory))
        assert any('does not replace' in text for text in imported['warnings'])
        destination.execute(imported['statements'][0]['source'])
        assert destination.execute('SELECT * FROM facts').fetchall() == [(1, 'first')]
    finally:
        destination.close()
    assert origin.is_file() and target.is_file()


def test_file_paths_and_unreviewed_control_symlinks_are_refused(tmp_path):
    root = tmp_path/'owned'; root.mkdir()
    outside = tmp_path/'outside'; outside.mkdir()
    database = root/'origin.duckdb'
    with pytest.raises(RelationalClientError, match='escapes'):
        ADMINISTRATION._compile_duckdb_database_operation(
            request('export_database', root, database, outside, format='PARQUET'))
    export = root/'export'; export.mkdir()
    (export/'load.sql').write_text('-- empty')
    outside_file = outside/'schema.sql'; outside_file.write_text('CREATE TABLE stolen(x INT);')
    os.symlink(outside_file, export/'schema.sql')
    with pytest.raises(RelationalClientError, match='reviewed directory'):
        ADMINISTRATION._compile_duckdb_database_operation(
            request('import_database', root, database, export))

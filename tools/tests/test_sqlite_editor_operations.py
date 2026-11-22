"""Typed descriptor drafts reach existing native original-session controls."""
import pytest
from pgadmin.cdeadmin.workspace.sqlite_editor_operations import compile_request, contract
from pgadmin.cdeadmin.data_studio.models import DataStudioAccessError
from test_sqlite_extensions import native, libraries  # noqa: F401 (owned native fixture)


def test_extension_descriptor_review_load_and_receipt(native):
    n = native
    def run(operation, **draft):
        transport, request = compile_request('editor_extension_' + operation, draft)
        assert transport == 'sqlite_extensions'
        return n.studio.sqlite_extension_action(n.context, n.session.session_id, request)
    inventory = run('inventory')
    assert inventory['loader_available'] and all('path' not in row for row in inventory['extensions'])
    review = run('review', extension_id='success')
    receipt = run('load', review_id=review['review_id'], confirmed=True)
    assert receipt['state'] == 'loaded' and receipt['loader_cleanup_confirmed']
    assert n.connection.execute('SELECT cde_native_probe()').fetchone() == ('native extension: 雪',)
    assert run('receipt', review_id=review['review_id']) == receipt
    # Existing review is final: repeat means receipt retrieval, never replay.
    assert run('load', review_id=review['review_id'], confirmed=True) == receipt
    assert len(n.connection._cdeadmin_extension_directories) == 1


@pytest.mark.parametrize('identity,draft', [
    ('editor_extension_review', {'extension_id': 'success', 'path': '/unapproved'}),
    ('editor_extension_load', {'review_id': 'x', 'confirmed': 1}),
    ('editor_extension_load', {'confirmed': True}),
    ('sqlite_extensions', {'operation': 'load'}),
])
def test_descriptor_cannot_forward_arbitrary_authority(identity, draft):
    with pytest.raises(ValueError):
        compile_request(identity, draft)


def test_descriptor_contract_matches_registered_native_transports():
    value = contract()
    assert not value['automatic_replay']
    assert value['envelope_fields'] == ['database_target_id', 'session_id']
    for row in value['operations']:
        assert row['descriptor']['operation_id'] == row['operation_id']
        assert row['descriptor']['status'] == 'draft'
        assert row['original_session_required'] == (
            row['transport'] not in {'sqlite_retained_schema_receipts', 'sqlite_changeset', 'workspace_form_download', 'sqlite_capture_export'} or
            row['operation_id'] in {'editor_export_review', 'editor_diff_catalog', 'editor_diff_tables', 'editor_diff_review'})


def test_array_descriptor_lossless_values_bind_and_release(native, monkeypatch):
    import config
    import os
    if 'CDEADMIN_SQLITE_ARRAY_LIBRARY' not in os.environ:
        pytest.skip('CDEADMIN_SQLITE_ARRAY_LIBRARY requires SQLite 3.53.0+')
    monkeypatch.setattr(config, 'CDEADMIN_SQLITE_ARRAY_LIBRARY', os.environ['CDEADMIN_SQLITE_ARRAY_LIBRARY'])
    n = native
    def run(operation, **draft):
        transport, request = compile_request('editor_array_' + operation, draft)
        assert transport == 'sqlite_native_arrays'
        return n.studio.sqlite_native_array_action(n.context, n.session.session_id, request)
    assert run('inventory')['helper_available']
    n.connection.execute('CREATE TABLE pending(id)')
    n.connection.execute('INSERT INTO pending VALUES(17)')
    created = run('create', type='int64', values=[{'encoding': 'scalar', 'value': '9007199254740993'}, {'encoding': 'scalar', 'value': '9223372036854775807'}])['array']
    from pgadmin.cdeadmin.providers.sqlite.array_bindings import bind_arrays
    from pgadmin.cdeadmin.providers.sqlite.values import parameters
    sql, bound = bind_arrays(n.connection, 'SELECT value FROM carray(?)', parameters([created['binding']]))
    assert n.connection.execute(sql, bound).fetchall() == [(9007199254740993,), (9223372036854775807,)]
    assert run('status', array_id=created['array_id'])['array']['binding'] == created['binding']
    assert run('close', array_id=created['array_id'], confirmed=True)['closed']
    assert n.connection.in_transaction and n.connection.execute('SELECT * FROM pending').fetchall() == [(17,)]
    with pytest.raises(DataStudioAccessError, match='another or closed'):
        run('status', array_id=created['array_id'])


@pytest.mark.parametrize('kind,values,expected', [
    ('text', [{'encoding': 'scalar', 'value': '雪'}, {'encoding': 'null'}], ['雪', None]),
    ('blob', [{'encoding': 'base64', 'value': 'AP8='}, {'encoding': 'null'}], [{'encoding': 'base64', 'data': 'AP8='}, None]),
    ('double', [{'encoding': 'scalar', 'value': 'NaN'}], ['NaN']),
])
def test_array_descriptor_maps_typed_native_envelopes(kind, values, expected):
    _, request = compile_request('editor_array_create', {'type': kind, 'values': values})
    assert request['values'] == expected


@pytest.mark.parametrize('kind,row', [
    ('int64', {'encoding': 'null'}), ('int32', {'encoding': 'scalar', 'value': '2147483648'}),
    ('blob', {'encoding': 'scalar', 'value': 'not bytes'}),
    ('text', {'encoding': 'base64', 'value': 'AA=='}),
    ('blob', {'encoding': 'base64', 'value': '!'}),
    ('text', {'encoding': 'null', 'value': 'discarded'}),
])
def test_array_descriptor_refuses_lossy_or_incompatible_cells(kind, row):
    with pytest.raises(ValueError):
        compile_request('editor_array_create', {'type': kind, 'values': [row]})


def test_preupdate_descriptor_generations_observe_rollback_without_committing(native, monkeypatch):
    import config
    import os
    if 'CDEADMIN_SQLITE_PREUPDATE_LIBRARY' not in os.environ:
        pytest.skip('CDEADMIN_SQLITE_PREUPDATE_LIBRARY requires SQLite 3.45.1+')
    monkeypatch.setattr(config, 'CDEADMIN_SQLITE_PREUPDATE_LIBRARY', os.environ['CDEADMIN_SQLITE_PREUPDATE_LIBRARY'])
    n = native
    def run(operation, **draft):
        transport, request = compile_request('editor_preupdate_' + operation, draft)
        assert transport == 'sqlite_native_preupdate'
        return n.studio.sqlite_native_preupdate_action(n.context, n.session.session_id, request)
    assert run('inventory')['helper_available']
    n.connection.execute('CREATE TABLE seen(id INTEGER, data BLOB)')
    status = run('start', max_events=2, max_json_bytes='1048576')['status']
    n.connection.execute("INSERT INTO seen VALUES(9007199254740993, x'00FF')")
    n.connection.rollback()
    page = run('events', run_id=status['run_id'])
    assert page['events'][0]['new_values'][0]['data'] == '9007199254740993'
    assert page['events'][0]['new_values'][1]['data']['data'] == 'AP8='
    assert 'do not establish' in page['scope']
    assert n.connection.execute('SELECT * FROM seen').fetchall() == []
    status = run('clear', run_id=status['run_id'], confirmed=True)['status']
    assert run('status')['status']['run_id'] == status['run_id']
    assert run('stop', run_id=status['run_id'])['status']['enabled'] is False


@pytest.mark.parametrize('draft', [{'max_events': True}, {'max_json_bytes': '01'}, {'max_events': 0}])
def test_preupdate_descriptor_invalid_native_limits_refuse(native, monkeypatch, draft):
    import config
    import os
    if 'CDEADMIN_SQLITE_PREUPDATE_LIBRARY' not in os.environ:
        pytest.skip('CDEADMIN_SQLITE_PREUPDATE_LIBRARY requires SQLite 3.45.1+')
    monkeypatch.setattr(config, 'CDEADMIN_SQLITE_PREUPDATE_LIBRARY', os.environ['CDEADMIN_SQLITE_PREUPDATE_LIBRARY'])
    with pytest.raises((ValueError, DataStudioAccessError)):
        _, request = compile_request('editor_preupdate_start', draft)
        native.studio.sqlite_native_preupdate_action(native.context, native.session.session_id, request)
    assert native.connection._cdeadmin_preupdate_api is None


def test_schema_descriptor_native_review_apply_rediscovery_leaves_caller_transaction(native, tmp_path):
    import json
    import time
    from pgadmin.cdeadmin.workspace.sqlite_retained_applications import SQLiteRetainedApplications
    n = native
    archive = SQLiteRetainedApplications(tmp_path / 'retained-reviews.json')
    n.connection.execute('CREATE TABLE original(id INTEGER PRIMARY KEY)')
    n.connection.execute('BEGIN')
    n.connection.execute('INSERT INTO original VALUES(17)')
    n.connection.execute('SAVEPOINT caller')
    captured = n.studio.session_catalog(n.context, n.session.session_id)
    baseline = json.dumps(captured['document']['snapshot'])
    resource = next(row['resource_id'] for row in captured['resources'] if row['resource_kind'] == 'table' and row['display_name'] == 'original')
    def run(operation, **draft):
        transport, request = compile_request('editor_schema_' + operation, draft)
        assert transport == 'sqlite_retained_schema'
        return n.studio.sqlite_retained_schema_action(n.context, n.session.session_id, request, archive, 'owner', 'binding', 'target')
    changes = [{'action': 'rename-table', 'resource_id': resource, 'name': 'renamed'}]
    altered = run('alter', baseline=baseline, alterations=changes)
    alter_preview = run('preview', baseline=baseline, desired=json.dumps(altered['snapshot']), alterations=changes)
    assert alter_preview['operations'][0]['source'].endswith('RENAME TO "renamed"')
    generated = run('columns', baseline=baseline, resource_id=resource, columns=[{'name': 'body', 'data_type': 'TEXT', 'default': "'retained 雪'", 'default_constraint_name': 'body_default'}])
    desired = json.dumps(generated['snapshot'])
    preview = run('preview', baseline=baseline, desired=desired)
    assert preview['operations'] and preview['execution_sha256']
    reviewed = run('review', baseline=baseline, desired=desired, execution_sha256=preview['execution_sha256'])
    value = run('start', review_id=reviewed['review_id'], review_digest=reviewed['review_digest'], confirmed=True)
    deadline = time.monotonic() + 10
    while value.get('worker_active') or value['state'] in {'reviewed', 'unknown_outcome'}:
        assert time.monotonic() < deadline, value
        time.sleep(.02)
        value = archive.get(reviewed['review_id'], 'owner', 'binding')
    assert value['state'] == 'applied_pending_caller_transaction', value
    assert value['outcome']['rediscovery_verified'] and not value['outcome']['commit_dispatched']
    assert value['native_session_release_confirmed']
    assert n.connection.execute('SELECT * FROM original').fetchall() == [(17, 'retained 雪')]
    n.connection.execute('ROLLBACK TO caller')
    n.connection.execute('RELEASE caller')
    assert n.connection.in_transaction
    assert n.connection.execute('SELECT * FROM original').fetchall() == [(17,)]
    # Final review returns its receipt; it never repeats stages after caller rollback.
    assert run('start', review_id=reviewed['review_id'], review_digest=reviewed['review_digest'], confirmed=True)['state'] == value['state']
    assert n.connection.execute('SELECT * FROM original').fetchall() == [(17,)]


def test_schema_descriptor_exact_mappings_and_no_invented_native_controls():
    _, request = compile_request('editor_schema_columns', {'baseline': 'ddn', 'resource_id': 'table', 'columns': [{'name': 'v', 'generated_expression': 'id+1', 'generated_storage': 'virtual', 'generated_constraint_name': 'v_gen'}, {'name': 'fk', 'data_type': 'INTEGER', 'nullable': False, 'references_table': 'parent', 'references_column': 'id', 'references_deferrable': False}]})
    assert request['columns'][0] == {'name': 'v', 'generated': {'expression': 'id+1', 'storage': 'virtual'}, 'constraint_names': {'generated': 'v_gen'}}
    assert request['columns'][1]['references']['deferrable'] is False
    transport, request = compile_request('editor_schema_capture', {})
    assert transport == 'source_catalog' and request == {}
    transport, request = compile_request('editor_schema_alter', {'baseline': 'ddn', 'alterations': [{'action': 'rename-table', 'resource_id': 'table', 'name': 'new', 'column': '', 'expression': ''}]})
    assert request['alterations'] == [{'action': 'rename-table', 'resource_id': 'table', 'name': 'new'}]


@pytest.mark.parametrize('identity,draft', [
    ('editor_schema_columns', {'baseline': 'ddn', 'resource_id': 'table', 'columns': [{'name': 'x', 'generated_expression': '1'}]}),
    ('editor_schema_columns', {'baseline': 'ddn', 'resource_id': 'table', 'columns': [{'name': 'x', 'nullable': 'false'}]}),
    ('editor_schema_alter', {'baseline': 'ddn', 'alterations': [{'action': 'drop-column', 'resource_id': 'table', 'column': 'x', 'name': 'ignored'}]}),
    ('editor_schema_preview', {'baseline': 'ddn', 'desired': 'ddn', 'deletions': [{'resource_id': 'x'}]}),
])
def test_schema_descriptor_refuses_incomplete_or_ignored_properties(identity, draft):
    with pytest.raises(ValueError):
        compile_request(identity, draft)


def test_archive_descriptor_does_not_require_or_revive_native_session():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from pgadmin.cdeadmin.workspace.sqlite_editor_operations import serve
    service = SimpleNamespace(language_tool_action=Mock(return_value={'archived_read_only': True}))
    server = SimpleNamespace(endpoint_profile=SimpleNamespace(profile_id='sqlite-native', provider_id='org.cdeadmin.sqlite'))
    result = serve(service, server, {'database_target_id': 'owned', 'request': {'operation_id': 'editor_schema_receipt_receipt', 'draft': {'review_id': 'saved'}}})
    assert result == {'archived_read_only': True}
    service.language_tool_action.assert_called_once_with(server, 'sqlite_retained_schema_receipts', {'database_target_id': 'owned', 'session_id': None, 'request': {'operation': 'receipt', 'review_id': 'saved'}})
    service.language_tool_action.reset_mock()
    with pytest.raises(ValueError, match='original query connection'):
        serve(service, server, {'database_target_id': 'owned', 'request': {'operation_id': 'editor_schema_capture', 'draft': {}}})
    service.language_tool_action.assert_not_called()
    with pytest.raises(ValueError, match='owned registered'):
        serve(service, server, {'request': {'operation_id': 'describe'}})
    server.endpoint_profile.profile_id = 'duckdb-native'
    with pytest.raises(ValueError, match='native SQLite registration'):
        serve(service, server, {'database_target_id': 'owned', 'request': {'operation_id': 'describe'}})


def test_archive_descriptor_removal_requires_true_confirmation():
    with pytest.raises(ValueError, match='Confirm removing'):
        compile_request('editor_schema_receipt_remove', {'review_id': 'saved', 'confirmed': False})

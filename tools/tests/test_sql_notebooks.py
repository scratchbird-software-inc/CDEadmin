"""Notebook persistence/privacy contracts; no history-store qualification."""
import copy
import pytest
from pgadmin.cdeadmin.workspace.assets import (
    ProjectAssetService, ProjectAssetError, ProjectAssetConflict,
    ProjectAssetForbidden, ProjectAssetNotFound)
from pgadmin.cdeadmin.workspace.sql_notebooks import ASSET_TYPE, FORMAT, validate
from tools.tests.test_cdeadmin_project_assets import MemoryRepository

SCOPE = {'engine': 'mysql', 'endpoint_id': 'endpoint', 'database_target_id': 'target'}


def document():
    return {'format': FORMAT, 'scope': copy.deepcopy(SCOPE), 'cells': [
        {'id': 'note', 'kind': 'note', 'source': 'Investigation <script>inert text</script>'},
        {'id': 'query', 'kind': 'sql', 'source': 'SELECT id, note FROM evidence', 'snapshot': None}]}


def request(content):
    return {'asset_type': ASSET_TYPE, 'schema_name': ASSET_TYPE, 'schema_version': 1,
            'name': 'Investigation', 'path': 'notebooks/investigation.json',
            'expected_version': 0, 'content': content}


def test_saved_revisions_shared_viewer_and_concurrent_edit_controls():
    assets = ProjectAssetService(MemoryRepository())
    assets.create_project(1, 'investigations', {'name': 'Investigations'})
    body = request(document())
    first = assets.save_asset(1, (), 'investigations', 'test', body)
    assert first['content'] == body['content'] and first['version'] == 1
    assets.set_member(1, (), 'investigations', {'principal_type': 'user', 'principal_id': 2, 'access_level': 'viewer'})
    assert assets.get_asset(2, (), 'investigations', 'test')['access'] == 'viewer'
    with pytest.raises(ProjectAssetForbidden):
        assets.save_asset(2, (), 'investigations', 'test', body)
    with pytest.raises(ProjectAssetNotFound):
        assets.get_asset(3, (), 'investigations', 'test')
    with pytest.raises(ProjectAssetConflict):
        assets.save_asset(1, (), 'investigations', 'test', body)
    body['expected_version'] = 1
    body['content']['cells'][0]['source'] = 'Updated notes'
    assets.save_asset(1, (), 'investigations', 'test', body)
    restarted = ProjectAssetService(assets.repository)
    assert restarted.get_asset(2, (), 'investigations', 'test', 1)['content']['cells'][0]['source'].startswith('Investigation')
    assert restarted.get_asset(2, (), 'investigations', 'test')['version'] == 2


@pytest.mark.parametrize('text', [
    'mysql://operator:private@host/db', "CREATE USER x IDENTIFIED BY 'private'",
    "CREATE USER x IDENTIFIED WITH caching_sha2_password BY 'private'",
    'password = private', 'access_token: private', 'api_key=private',
    '-----BEGIN PRIVATE KEY-----', '-----BEGIN ENCRYPTED PRIVATE KEY-----',
    "CREATE USER x IDENTIFIED WITH caching_sha2_password AS 'credential-hash'", "SET PASSWORD = 'private'"])
def test_credentials_in_sql_notes_or_snapshot_are_refused(text):
    for kind in ('note', 'sql'):
        value = document()
        value['cells'][0 if kind == 'note' else 1]['source'] = text
        with pytest.raises(ValueError, match='credential'):
            validate(value)
    value = with_snapshot()
    value['cells'][1]['snapshot']['rows'][0][0] = text
    with pytest.raises(ValueError, match='credential'):
        validate(value)


def with_snapshot():
    value = document()
    value['cells'][1]['snapshot'] = {'columns': ['id', 'note'], 'rows': [['18446744073709551615', '[REDACTED]']],
        'source': value['cells'][1]['source'], 'scope': copy.deepcopy(SCOPE), 'captured_at': '2026-10-22T18:00:00Z', 'limited': True}
    return value


def test_snapshot_scope_source_and_limits_are_enforced_without_native_payloads():
    value = with_snapshot()
    assert validate(value) == value
    for update in ({'rows': [['x', 'y']] * 101}, {'columns': ['id', 'id']},
                   {'rows': [[{} , 'x']]}, {'rows': [['x' * 8193, 'x']]},
                   {'scope': {**SCOPE, 'database_target_id': 'other'}},
                   {'source': 'SELECT other'}, {'limited': 'true'}, {'native': {'password': 'private'}}):
        changed = copy.deepcopy(value)
        changed['cells'][1]['snapshot'].update(update)
        with pytest.raises(ValueError):
            validate(changed)
    portable = copy.deepcopy(value)
    portable['scope'] = portable['cells'][1]['snapshot']['scope'] = None
    assert validate(portable) == portable


@pytest.mark.parametrize('field', ['session_id', 'parameters', 'password', 'route', 'auto_execute'])
def test_unknown_document_fields_fail_before_storage_mutation(field):
    assets = ProjectAssetService(MemoryRepository())
    assets.create_project(1, 'p', {})
    before = assets.repository.commits
    content = document()
    content[field] = 'not-permitted'
    with pytest.raises(ProjectAssetError):
        assets.save_asset(1, (), 'p', 'asset', request(content))
    assert assets.repository.commits == before


def test_schema_and_duplicate_cell_constraints():
    malformed = document(); malformed['cells'][0]['kind'] = []
    with pytest.raises(ValueError):
        validate(malformed)
    value = document()
    value['cells'].append(copy.deepcopy(value['cells'][0]))
    with pytest.raises(ValueError, match='Duplicate'):
        validate(value)
    assets = ProjectAssetService(MemoryRepository())
    assets.create_project(1, 'p', {})
    for field, change in [('schema_version', 2), ('schema_name', 'other')]:
        body = request(document()); body[field] = change
        with pytest.raises(ProjectAssetError):
            assets.save_asset(1, (), 'p', 'asset', body)

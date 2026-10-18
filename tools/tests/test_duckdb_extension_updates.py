"""Extension update intent, exact catalog facts and native outcome boundaries."""
from unittest.mock import Mock, patch
import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.provider import ADMINISTRATION, _create_client, _resources
from pgadmin.cdeadmin.providers.duckdb import extension_updates as updates
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.visual_admin import catalog_for_engine


@pytest.fixture
def fixture(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    path = tmp_path/'owned.duckdb';configuration = {'extension_directory': str(tmp_path/'extension-cache')}
    connection = duckdb.connect(str(path), config=configuration)
    client = _create_client();route = {'database': str(path), 'filesystem_root': str(tmp_path), 'config': configuration}
    try:
        yield connection, client, route
    finally:
        client.close();connection.close()


def request(resource, route, **draft):
    return {'resource_kind': resource['resource_kind'],
        'operation_id': 'update' if resource['resource_kind'] == 'extension' else 'update_extensions',
        'target_resource': resource, '_provider_route': route,
        'draft': {'confirmation': resource['display_name'], 'filesystem_effects_acknowledged': True, **draft}}


def test_catalog_preserves_every_native_extension_field(fixture):
    connection, _, _ = fixture
    rows = _resources(connection, {})
    columns = [row[0] for row in connection.execute('SELECT * FROM duckdb_extensions()').description]
    expected = sorted([dict(zip(columns, row)) for row in connection.fetchall()], key=lambda row: row['extension_name'])
    actual = sorted([row['native']['catalog_metadata'] for row in rows if row['resource_kind'] == 'extension'], key=lambda row: row['extension_name'])
    assert actual == expected and set(columns) == set(updates.FIELDS)
    database = next(row for row in rows if row['resource_kind'] == 'database')
    assert database['native']['extension_inventory'] == actual


@pytest.mark.parametrize('draft', [{'confirmation': 'different'},
    {'filesystem_effects_acknowledged': False}, {'source': 'INSTALL unsigned'}])
def test_native_file_effects_require_exact_review(fixture, draft):
    connection, _, route = fixture
    target = next(row for row in _resources(connection, {}) if row['resource_kind'] == 'database')
    with pytest.raises(RelationalClientError):
        ADMINISTRATION.plan(request(target, route, **draft))


def test_builtin_or_uninstalled_code_has_no_updateable_native_file(fixture):
    connection, _, route = fixture
    targets = [row for row in _resources(connection, {}) if row['resource_kind'] == 'extension']
    assert targets
    for target in targets:
        if not target['native']['installed'] or target['native']['catalog_metadata']['install_mode'] == 'STATICALLY_LINKED':
            assert 'update' not in target['native']['administration']['allowed_operations']
            with pytest.raises(RelationalClientError, match='installed native extension file'):
                ADMINISTRATION.plan(request(target, route))


def test_empty_native_update_does_not_decide_a_retained_transaction(fixture):
    owner, client, route = fixture
    owner.execute('CREATE TABLE pending(id INT)')
    retained = client.open_session({'route': route})
    retained.execute('INSERT INTO pending VALUES (42)');retained.execute('CREATE TEMP TABLE private(id INT)')
    resource = next(row for row in _resources(retained, {'session_catalog': True}) if row['resource_kind'] == 'database')
    result = ADMINISTRATION.apply(client, ADMINISTRATION.plan(request(resource, route)), retained)
    assert result['extension_update_observation']['native_results'] == []
    assert result['commit_requested'] is False and result['rollback_requested'] is False
    assert retained.execute('SELECT id FROM pending').fetchall() == [(42,)]
    assert owner.execute('SELECT id FROM pending').fetchall() == []
    retained.rollback()
    assert owner.execute('SELECT id FROM pending').fetchall() == []


def test_changed_native_directory_is_refused_before_update(fixture):
    connection, client, route = fixture
    target = next(row for row in _resources(connection, {}) if row['resource_kind'] == 'database')
    target['native']['extension_update_context']['extension_directory'] += '-different'
    with pytest.raises(RelationalClientError, match='directory changed') as failure:
        ADMINISTRATION.apply(client, ADMINISTRATION.plan(request(target, route)))
    assert not failure.value.native_dispatched


def test_post_acknowledgement_failure_keeps_possible_file_effects(fixture):
    connection, _, route = fixture
    resource = next(row for row in _resources(connection, {}) if row['resource_kind'] == 'database')
    planned = ADMINISTRATION.plan(request(resource, route));client = Mock();handle = client._connect.return_value
    handle.description = [('extension_name',)];handle.fetchall.return_value = []
    with patch('pgadmin.cdeadmin.providers.duckdb.provider._resources', return_value=[resource]), \
            patch.object(updates, 'inventory', side_effect=[resource['native']['extension_inventory'], OSError('post-update observation failed')]), \
            patch.object(updates, 'context', return_value=resource['native']['extension_update_context']):
        with pytest.raises(RelationalClientError) as failure:
            updates.apply(ADMINISTRATION, client, planned)
    assert failure.value.native_dispatched and failure.value.native_acknowledged
    assert failure.value.native_filesystem_effects_possible and failure.value.automatic_retry is False
    handle.execute.assert_called_once_with('UPDATE EXTENSIONS')
    client._forget_and_close.assert_called_once_with(handle)


def test_native_update_controls_are_discoverable():
    catalog = ADMINISTRATION.catalog(catalog_for_engine('duckdb'))
    for kind, operation in updates.OPERATIONS:
        item = next(row for row in catalog['objects'] if row['resource_kind'] == kind)
        action = next(row for row in item['operations'] if row['operation_id'] == operation)
        assert action['target_required'] and action['confirmation_required']
        assert {row['field_id'] for row in action['form']['fields']} == {'confirmation', 'filesystem_effects_acknowledged'}


def test_repository_credentials_are_not_catalog_facts():
    connection = Mock()
    row = ['httpfs', True, True, '/owned/httpfs.duckdb_extension', 'Native HTTP',
        ['http'], 'version', 'REPOSITORY', 'https://operator:canary-password@repo.invalid/path?token=canary-token']
    connection.execute.return_value.fetchall.return_value = [row]
    result = updates.inventory(connection)
    assert result[0]['extension_name'] == 'httpfs' and result[0]['installed'] is True
    assert 'canary-password' not in str(result) and 'canary-token' not in str(result)
    assert '[REDACTED]' in result[0]['installed_from']

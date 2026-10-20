"""Real native storage identities, caller transactions and expression admission."""
import json

import pytest

from test_duckdb_secret_values import native  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.provider import ADMINISTRATION, _resources
from pgadmin.cdeadmin.sdk import RelationalClientError


def request(native, draft, operation='create', target=None):
    return {'resource_kind': 'secret', 'operation_id': operation, 'draft': draft,
            '_provider_route': native.route, 'target_resource': target}


def create(native, name='same . " é', mode='TEMPORARY', **fields):
    value = request(native, {'name': name, 'secret_type': 'HTTP', 'persistence_mode': mode,
        'properties': {'bearer_token': 'private native token'}, **fields})
    assert ADMINISTRATION.validate(value)['errors'] == []
    plan = ADMINISTRATION.plan(value)
    assert 'private native token' not in json.dumps(plan['command_preview'])
    return ADMINISTRATION.apply(native.client, plan, connection=native.handle)


def targets(native):
    return [row for row in _resources(native.handle, {'session_catalog': True}) if row['resource_kind'] == 'secret']


def test_same_name_storage_identities_drop_exactly_one_and_preserve_pending_rows(native):
    create(native); create(native, mode='PERSISTENT')
    native.client.control_transaction(native.handle, 'commit')
    resources = targets(native)
    assert len(resources) == len({row['resource_id'] for row in resources}) == 2
    assert {row['native']['storage'] for row in resources} == {'memory', 'local_file'}
    assert all('private native token' not in json.dumps(row) for row in resources)
    native.handle.execute('INSERT INTO pending VALUES (42)')
    for resource in sorted(resources, key=lambda row: row['native']['persistent']):
        plan = ADMINISTRATION.plan(request(native, {'confirmation': resource['display_name']}, 'drop', resource))
        assert ' FROM ' in plan['command_preview']['statements'][0]['source']
        result = ADMINISTRATION.apply(native.client, plan, connection=native.handle)
        assert result['accepted'] and not result['commit_requested'] and not result['rollback_requested']
        assert all(row['storage'] != resource['native']['storage'] for row in result['native_storage_observation']['observation']['objects'])
        assert native.handle.execute('SELECT * FROM pending').fetchall() == [(42,)]
    assert targets(native) == []
    native.client.control_transaction(native.handle, 'rollback')
    assert native.handle.execute('SELECT * FROM pending').fetchall() == []
    assert len(targets(native)) == 2
    import duckdb
    observer = duckdb.connect(config=native.route['config'])
    try:
        # The rolled-back DROP restores the current catalog, but it cannot
        # restore the persistent file which the storage backend removed.
        assert observer.execute('SELECT name FROM duckdb_secrets()').fetchall() == []
    finally:observer.close()


def test_retained_catalog_accepts_native_secret_scope_lists_and_preserves_pending_work(native):
    from pgadmin.cdeadmin.providers.embedded_session_catalog import duckdb_catalog
    create(native, properties={'scope': ['https://first.example.test/', 'https://second.example.test/']})
    native.handle.execute('INSERT INTO pending VALUES (42)')
    result = duckdb_catalog(native.client, native.handle, 'owned-session')
    secret = next(row for row in result['resources'] if row['resource_kind'] == 'secret')
    assert secret['native']['scope'] == ['https://first.example.test/', 'https://second.example.test/']
    assert result['transaction_preserved']
    assert native.handle.execute('SELECT * FROM pending').fetchall() == [(42,)]


def test_stale_storage_target_refuses_before_dispatch_and_cannot_drop_other_storage(native):
    create(native); create(native, mode='PERSISTENT')
    resource = next(row for row in targets(native) if not row['native']['persistent'])
    plan = ADMINISTRATION.plan(request(native, {'confirmation': resource['display_name']}, 'drop', resource))
    native.handle.execute('DROP SECRET ' + ADMINISTRATION._quote(resource['display_name']) + ' FROM memory')
    with pytest.raises(RelationalClientError, match='metadata changed'):
        ADMINISTRATION.apply(native.client, plan, connection=native.handle)
    assert [(row['native']['storage'], row['native']['persistent']) for row in targets(native)] == [('local_file', True)]


def test_native_conflict_modes_and_original_connection_are_required(native):
    create(native, properties={'scope': ['https://original.example.test/']})
    native.client.control_transaction(native.handle, 'commit')
    refused = request(native, {'name': 'same . " é', 'secret_type': 'HTTP', 'persistence_mode': 'TEMPORARY'})
    plan = ADMINISTRATION.plan(refused)
    with pytest.raises(RelationalClientError, match='original editor session'):
        ADMINISTRATION.apply(native.client, plan)
    with pytest.raises(RelationalClientError, match='InvalidInputException'):
        ADMINISTRATION.apply(native.client, plan, connection=native.handle)
    native.client.control_transaction(native.handle, 'rollback')
    ignored = create(native, on_conflict='IF NOT EXISTS', properties={'scope': ['https://replacement.example.test/']})
    assert ignored['statement_results'][0]['rows'] == [(True,)]
    assert ignored['native_storage_observation']['observation']['objects'][0]['scope'] == ['https://original.example.test/']
    replaced = create(native, on_conflict='OR REPLACE', properties={'scope': ['https://replacement.example.test/']})
    assert replaced['statement_results'][0]['rows'] == [(True,)]
    assert replaced['native_storage_observation']['observation']['objects'][0]['scope'] == ['https://replacement.example.test/']
    assert len(targets(native)) == 1


@pytest.mark.parametrize('mode,storage,persistent', [
    ('DEFAULT', 'memory', False), ('DEFAULT', 'local_file', True),
    ('TEMPORARY', 'memory', False), ('PERSISTENT', 'local_file', True)])
def test_native_persistence_mode_resolves_actual_storage(native, mode, storage, persistent):
    result = create(native, mode=mode, storage=storage)
    row = result['native_storage_observation']['observation']['objects'][0]
    assert row['storage'] == storage and row['persistent'] is persistent


@pytest.mark.parametrize('mode,storage', [('TEMPORARY', 'local_file'), ('PERSISTENT', 'memory')])
def test_native_persistence_storage_mismatch_requires_caller_rollback(native, mode, storage):
    native.handle.execute('INSERT INTO pending VALUES (42)')
    with pytest.raises(RelationalClientError):create(native, mode=mode, storage=storage)
    assert native.client.describe_transaction(native.handle)['native_transaction_viability'] == 'aborted'
    with pytest.raises(Exception, match='Current transaction is aborted'):
        native.handle.execute('SELECT * FROM pending').fetchall()
    native.client.control_transaction(native.handle, 'rollback')
    assert native.handle.execute('SELECT * FROM pending').fetchall() == []
    assert targets(native) == []


def test_explicit_expressions_use_original_variables_and_literals_are_never_inferred(native):
    native.handle.execute("SET VARIABLE owned_scope = ['https://first.example.test/', 'https://second.example.test/']")
    value = request(native, {'name': 'expression', 'secret_type': 'HTTP', 'persistence_mode': 'TEMPORARY',
        'properties': {'bearer_token': "getvariable('never evaluate literal')"},
        'property_expressions': {'scope': "getvariable('owned_scope')", 'verify_ssl': 'true'}})
    assert ADMINISTRATION.validate(value)['errors'] == []
    plan = ADMINISTRATION.plan(value)
    assert 'owned_scope' not in json.dumps(plan['command_preview'])
    result = ADMINISTRATION.apply(native.client, plan, connection=native.handle)
    assert result['native_storage_observation']['observation']['objects'][0]['scope'] == [
        'https://first.example.test/', 'https://second.example.test/']
    assert create(native, name='')['native_storage_observation']['observation']['objects'][0]['name'] == '__default_http'
    typed = request(native, {'name': 'typed', 'persistence_mode': 'TEMPORARY',
        'property_expressions': {'TYPE': "'HTTP'", 'scope': "['https://type.example.test/']"}})
    assert ADMINISTRATION.apply(native.client, ADMINISTRATION.plan(typed), connection=native.handle)['accepted']


@pytest.mark.parametrize('expressions', [
    {'scope': '1,2'}, {'scope': '1; SELECT 2'}, {'scope': "error('private expression detail')"},
    {'scope': "'a'", 'SCOPE': "'b'"}])
def test_expression_parse_does_not_execute_functions_or_echo_private_source(native, expressions):
    value = request(native, {'name': 'parse_only', 'secret_type': 'HTTP', 'property_expressions': expressions})
    errors = ADMINISTRATION.validate(value)['errors']
    # A function call parses successfully without being evaluated.
    if 'error(' in next(iter(expressions.values())):
        assert errors == []
        with pytest.raises(RelationalClientError) as caught:
            ADMINISTRATION.apply(native.client, ADMINISTRATION.plan(value), connection=native.handle)
        assert 'private expression detail' not in str(caught.value)
    else:
        assert errors and 'SELECT 2' not in json.dumps(errors)


def test_expression_statement_budget_is_aggregate_and_malformed_property_maps_are_refused(native):
    value = request(native, {'name': 'bounded', 'secret_type': 'HTTP',
        'property_expressions': {'bearer_token': repr('x' * 550000), 'proxy_password': repr('y' * 550000)}})
    assert 'byte budget' in ADMINISTRATION.validate(value)['errors'][0]['message']
    for field in ('properties', 'property_expressions', 'options'):
        value = request(native, {'name': 'invalid', 'secret_type': 'HTTP', field: []})
        assert ADMINISTRATION.validate(value)['errors']


def test_native_persistent_file_survives_rollback_while_current_catalog_does_not(native):
    native.handle.execute('INSERT INTO pending VALUES (42)')
    create(native, name='rollback_file', mode='PERSISTENT')
    native.client.control_transaction(native.handle, 'rollback')
    assert targets(native) == []
    assert native.handle.execute('SELECT * FROM pending').fetchall() == []
    import duckdb
    observer = duckdb.connect(config=native.route['config'])
    try:
        assert observer.execute('SELECT name,persistent,storage FROM duckdb_secrets()').fetchall() == [
            ('rollback_file', True, 'local_file')]
    finally:observer.close()

"""Descriptor drafts preserve native retained-session authority and outcomes."""
from types import SimpleNamespace
from unittest.mock import Mock
import json
import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from test_duckdb_attachment_actions import fixture  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.provider import DuckDBPilotProvider
from pgadmin.cdeadmin.workspace.duckdb_editor_operations import compile_request, contract


def attachment(fixture, operation, **draft):
    client, handle, route, _ = fixture
    provider = DuckDBPilotProvider(SimpleNamespace(endpoint_id='owned'), SimpleNamespace(require=Mock()), client)
    provider._sessions['original'] = SimpleNamespace(handle=handle)
    transport, request = compile_request('editor_attachment_' + operation, draft)
    assert transport == 'duckdb_attachments'
    return provider.attachment_action({'session_id': 'original', 'language_profile': 'duckdb-sql', **request}, route)


def test_attachment_descriptor_review_apply_and_release_private_key(fixture):
    client, handle, _, other = fixture
    alias = 'typed . " 雪'
    destination = other.parent / 'typed-encrypted.duckdb'
    key = 'owned typed private key 20261115'
    reviewed = attachment(fixture, 'review_attach', alias=alias, path=str(destination), read_only=False, create_if_missing=True,
        block_size='262144', row_group_size='122880', storage_version='latest', key_mode='SUPPLIED', encryption_key=key, encryption_cipher='GCM')
    assert key not in json.dumps(reviewed) and reviewed['key_bound']
    applied = attachment(fixture, 'apply', review_id=reviewed['review_id'], review_digest=reviewed['review_digest'], confirmation=alias, confirmed=True)
    assert applied['native_acknowledged'] and applied['rediscovery_verified'], applied
    assert key not in json.dumps(applied)
    actual = next(row for row in attachment(fixture, 'inventory')['catalogs'] if row['name'] == alias)
    assert actual['encrypted'] and actual['cipher'] == 'GCM'
    assert not client._attachment_key_timers
    assert attachment(fixture, 'receipt', review_id=reviewed['review_id']) == applied
    assert attachment(fixture, 'apply', review_id=reviewed['review_id'], review_digest=reviewed['review_digest'], confirmation=alias, confirmed=True) == applied
    client.control_transaction(handle, 'commit')
    detached = attachment(fixture, 'review_detach', alias=alias)
    result = attachment(fixture, 'apply', review_id=detached['review_id'], review_digest=detached['review_digest'], confirmation=alias, confirmed=True)
    assert result['rediscovery_verified']
    client.control_transaction(handle, 'commit')
    import duckdb
    observer = duckdb.connect()
    try:
        observer.execute("ATTACH '" + str(destination).replace("'", "''") + "' AS independent (ENCRYPTION_KEY ?)", [key])
        assert observer.execute("SELECT encrypted FROM duckdb_databases() WHERE database_name='independent'").fetchone() == (True,)
    finally:
        observer.close()


def test_attachment_descriptor_discard_releases_key_without_dispatch(fixture):
    _, _, _, other = fixture
    reviewed = attachment(fixture, 'review_attach', alias='discarded', path=str(other.parent / 'not-created.duckdb'), read_only=False,
        create_if_missing=True, key_mode='SUPPLIED', encryption_key='owned disposable key')
    result = attachment(fixture, 'discard', review_id=reviewed['review_id'], review_digest=reviewed['review_digest'])
    assert result['state'] == 'discarded' and not result['native_dispatched']
    assert not other.with_name('not-created.duckdb').exists()


@pytest.mark.parametrize('draft', [
    {'read_only': 1}, {'source_sql': 'ATTACH arbitrary'}, {'encryption_key': 'ignored'},
    {'key_mode': 'SUPPLIED'}, {'encryption_cipher': 'GCM'}, {'compress_mode': 'unknown'},
])
def test_attachment_descriptor_does_not_ignore_or_forward_extra_controls(draft):
    with pytest.raises(ValueError):
        compile_request('editor_attachment_review_attach', {'alias': 'a', 'path': ':memory:', **draft})


def test_editor_contract_matches_registered_descriptors():
    value = contract()
    assert value['automatic_replay'] is False
    for row in value['operations']:
        assert row['descriptor']['operation_id'] == row['operation_id']


from test_duckdb_extension_actions import fixture as extension_fixture  # noqa: E402,F401


def extension(extension_fixture, operation, **draft):
    client, handle, route = extension_fixture
    provider = DuckDBPilotProvider(SimpleNamespace(endpoint_id='owned'), SimpleNamespace(require=Mock()), client)
    provider._sessions['original'] = SimpleNamespace(handle=handle)
    transport, request = compile_request('editor_extension_' + operation, draft)
    assert transport == 'duckdb_extensions'
    return provider.extension_action({'session_id': 'original', 'language_profile': 'duckdb-sql', **request}, route)


def test_extension_descriptor_load_and_native_inventory_preserve_pending_work(extension_fixture):
    client, handle, _ = extension_fixture
    assert extension(extension_fixture, 'inventory')['context']['runtime_version'] == 'v1.5.2'
    handle.execute('INSERT INTO pending VALUES(29)')
    review = extension(extension_fixture, 'review_load', extension_name='json')
    applied = extension(extension_fixture, 'apply', review_id=review['review_id'], review_digest=review['review_digest'], confirmation='json', confirmed=True)
    assert applied['native_acknowledged'] and applied['rediscovery_verified']
    assert handle.execute("SELECT json_extract('{\"native\":7}', '$.native')").fetchone() == ('7',)
    assert handle.execute('SELECT * FROM pending').fetchall() == [(29,)]
    assert extension(extension_fixture, 'receipt', review_id=review['review_id']) == applied
    assert extension(extension_fixture, 'apply', review_id=review['review_id'], review_digest=review['review_digest'], confirmation='json', confirmed=True) == applied
    client.control_transaction(handle, 'rollback')
    assert handle.execute('SELECT * FROM pending').fetchall() == []


def test_extension_descriptor_installer_options_reach_native_compiler(tmp_path):
    from pgadmin.cdeadmin.providers.duckdb.extension_actions import compile_operation
    transport, request = compile_request('editor_extension_review_install', {'extension_name': 'httpfs', 'force': True,
        'repository_kind': 'ALIAS', 'repository': 'core', 'version': '13e18b3', 'expected_http_secret': 'owned'})
    assert transport == 'duckdb_extensions'
    compiled = compile_operation({}, request['draft'])
    assert compiled['source'] == 'FORCE INSTALL \'httpfs\' FROM "core" VERSION \'13e18b3\''
    assert compiled['draft']['expected_http_secret'] == 'owned'
    file = tmp_path / 'signed-at-native-dispatch.duckdb_extension'
    file.write_bytes(b'native signature check stays at dispatch')
    _, request = compile_request('editor_extension_review_load', {'extension_name': 'httpfs', 'source_kind': 'FILE', 'source': str(file)})
    assert compile_operation({'filesystem_root': str(tmp_path)}, request['draft'])['file_identity']['sha256']


@pytest.mark.parametrize('identity,draft', [
    ('editor_extension_review_load', {'extension_name': 'json', 'force': True}),
    ('editor_extension_review_install', {'extension_name': 'httpfs', 'source_kind': 'URL', 'source': 'https://user:private@example.test/ext'}),
    ('editor_extension_review_install', {'extension_name': 'httpfs', 'source_kind': 'URL', 'source': 'https://example.test/ext', 'version': 'ignored'}),
])
def test_extension_descriptor_native_refusals_do_not_gain_alternate_routes(identity, draft):
    from pgadmin.cdeadmin.providers.duckdb.extension_actions import compile_operation
    with pytest.raises(ValueError):
        _, request = compile_request(identity, draft)
        compile_operation({}, request['draft'])


from test_duckdb_database_copy import native as copy_fixture  # noqa: E402,F401


def copying(native, operation, **draft):
    transport, request = compile_request('editor_copy_' + operation, draft)
    assert transport == 'duckdb_database_copy'
    result = native.provider.database_copy_action({'session_id': 'original', 'language_profile': 'duckdb-sql', **request}, native.route)
    if result.get('phase') != 'finished' and operation in {'review', 'apply'}:
        native.client._database_copy_reviews[result['review_id']]['worker'].join(timeout=20)
        return copying(native, 'receipt', review_id=result['review_id'])
    return result


def test_copy_descriptor_uses_native_encrypted_destination_and_caller_commit(copy_fixture):
    n = copy_fixture
    key = 'owned copy private key 20261115'
    destination = n.destination.parent / 'typed-copy-encrypted.duckdb'
    alias = 'Encrypted . 雪'
    args = (n.client, n.handle, n.route, n.destination)
    reviewed = attachment(args, 'review_attach', alias=alias, path=str(destination), read_only=False, create_if_missing=True,
        key_mode='SUPPLIED', encryption_key=key, encryption_cipher='CTR')
    assert attachment(args, 'apply', review_id=reviewed['review_id'], review_digest=reviewed['review_digest'], confirmation=alias, confirmed=True)['rediscovery_verified']
    n.client.control_transaction(n.handle, 'commit')
    n.handle.execute('CREATE TEMP TABLE private_rows AS SELECT 37 id')
    review = copying(n, 'review', source_catalog=n.aliases[0], destination_catalog=alias, mode='ALL')
    assert review['state'] == 'reviewed' and review['storage']['destination']['encrypted']
    result = copying(n, 'apply', review_id=review['review_id'], review_digest=review['review_digest'], confirmation=alias, confirmed=True)
    assert result['native_acknowledged'] and result['rediscovery_verified'], result
    assert result['storage_observation']['verified'] and result['storage']['destination']['cipher'] == 'CTR'
    assert n.handle.execute('SELECT * FROM private_rows').fetchall() == [(37,)]
    assert key not in json.dumps(result)
    assert copying(n, 'apply', review_id=review['review_id'], review_digest=review['review_digest'], confirmation=alias, confirmed=True) == result
    assert copying(n, 'cancel', review_id=review['review_id']) == result
    n.client.control_transaction(n.handle, 'commit')
    detached = attachment(args, 'review_detach', alias=alias)
    attachment(args, 'apply', review_id=detached['review_id'], review_digest=detached['review_digest'], confirmation=alias, confirmed=True)
    n.client.control_transaction(n.handle, 'commit')
    import duckdb
    observer = duckdb.connect()
    try:
        # Native CTR reopening requires the intended cipher to be explicit.
        with pytest.raises(duckdb.CatalogException, match='encryption cipher'):
            observer.execute("ATTACH '" + str(destination).replace("'", "''") + "' AS independent (ENCRYPTION_KEY ?)", [key])
        observer.execute("ATTACH '" + str(destination).replace("'", "''") + "' AS independent (ENCRYPTION_KEY ?, ENCRYPTION_CIPHER 'CTR')", [key])
        assert observer.execute('SELECT count(*) FROM independent."area . é".rows').fetchone() == (3,)
    finally:
        observer.close()


def test_copy_descriptor_discard_and_native_same_catalog_refusal(copy_fixture):
    n = copy_fixture
    assert copying(n, 'inventory')['catalogs']
    review = copying(n, 'review', source_catalog=n.aliases[0], destination_catalog=n.aliases[1], mode='SCHEMA')
    discarded = copying(n, 'discard', review_id=review['review_id'], review_digest=review['review_digest'])
    assert discarded['state'] == 'discarded'
    with pytest.raises(ValueError, match='must differ'):
        copying(n, 'review', source_catalog=n.aliases[0], destination_catalog=n.aliases[0], mode='DATA')


@pytest.mark.parametrize('draft', [
    {'mode': 'REKEY'}, {'encryption_key': 'must-use-attachment-review'}, {'source_sql': 'COPY arbitrary'},
])
def test_copy_descriptor_refuses_invented_inplace_encryption_or_sql(draft):
    with pytest.raises(ValueError):
        compile_request('editor_copy_review', {'source_catalog': 'source', 'destination_catalog': 'destination', **draft})


from test_duckdb_secret_values import native as secret_fixture  # noqa: E402,F401


def secret_service(native):
    from test_cdeadmin_relational_providers import context
    from pgadmin.cdeadmin.providers.duckdb.provider import PROFILE, _resources
    from pgadmin.cdeadmin.workspace.duckdb_editor_operations import secret_action
    from dataclasses import replace
    assert native.handle.execute('SELECT version()').fetchone() == ('v1.5.2',)
    verified = replace(context(PROFILE), runtime_verification_state='verified')
    provider = DuckDBPilotProvider(verified, SimpleNamespace(require=Mock(), allows=lambda *_: True), native.client)
    provider._sessions['original'] = SimpleNamespace(handle=native.handle)
    service = SimpleNamespace(
        plan_visual_admin=lambda _server, value: provider.plan_visual_admin({**value, '_provider_route': native.route}),
        apply_visual_admin=lambda _server, value: provider.apply_visual_admin({**value, '_provider_route': native.route}),
        language_tool_action=lambda _server, action, _data: {'resources': _resources(native.handle, {'session_catalog': True})},
        visual_admin_operation_action=lambda _server, _action, value: provider.list_visual_admin_operations(value))
    def call(operation, **draft):
        transport, request = compile_request('editor_secret_' + operation, draft)
        assert transport == 'native_secret_administration'
        return secret_action(service, object(), 'owned', 'original', request)
    return call


def private_nodes(token):
    return [
        {'node_id': 'token', 'key': 'bearer_token', 'kind': 'TEXT', 'value': token},
        {'node_id': 'scope', 'key': 'scope', 'kind': 'LIST'},
        {'node_id': 'first', 'parent_id': 'scope', 'kind': 'TEXT', 'value': 'https://owned.example.test/'},
        {'node_id': 'headers', 'key': 'extra_http_headers', 'kind': 'MAP'},
        {'node_id': 'header', 'parent_id': 'headers', 'key': 'X-Owned', 'kind': 'TEXT', 'value': token},
        {'node_id': 'ssl', 'key': 'verify_ssl', 'kind': 'BOOLEAN', 'boolean_value': 'TRUE'},
    ]


def test_secret_descriptor_common_facade_preserves_private_values_and_storage_identities(secret_fixture):
    n = secret_fixture
    call = secret_service(n)
    token = "private token is literal getvariable('never')"
    n.handle.execute('INSERT INTO pending VALUES(43)')
    for mode in ['TEMPORARY', 'PERSISTENT']:
        reviewed = call('review_create', name='paired', persistence_mode=mode, property_nodes=private_nodes(token))
        assert reviewed['state'] == 'ready', reviewed
        assert token not in json.dumps(reviewed)
        result = call('apply', plan_id=reviewed['plan_id'], plan_digest=reviewed['plan_digest'], confirmed=True)
        assert result['provider_result']['accepted'] and token not in json.dumps(result)
    resources = call('inventory')['resources']
    assert len(resources) == 2 and len({row['resource_id'] for row in resources}) == 2
    assert {row['native']['storage'] for row in resources} == {'memory', 'local_file'}
    assert n.handle.execute('SELECT * FROM pending').fetchall() == [(43,)]
    for row in resources:
        reviewed = call('review_drop', resource_id=row['resource_id'], confirmation=row['display_name'])
        result = call('apply', plan_id=reviewed['plan_id'], plan_digest=reviewed['plan_digest'], confirmed=True)
        assert result['provider_result']['accepted']
    assert call('inventory')['resources'] == []
    assert all(row['resource_kind'] == 'secret' for row in call('receipts')['items'])
    n.client.control_transaction(n.handle, 'rollback')
    assert n.handle.execute('SELECT * FROM pending').fetchall() == []


def test_secret_descriptor_type_expression_and_native_default_name(secret_fixture):
    n = secret_fixture
    call = secret_service(n)
    n.handle.execute("SET VARIABLE private_scope = ['https://expression.example.test/']")
    reviewed = call('review_create', name='explicit_expression', secret_type='', property_expressions=[
        {'name': 'TYPE', 'expression': "'HTTP'"}, {'name': 'scope', 'expression': "getvariable('private_scope')"}])
    assert 'private_scope' not in json.dumps(reviewed)
    result = call('apply', plan_id=reviewed['plan_id'], plan_digest=reviewed['plan_digest'], confirmed=True)
    assert result['provider_result']['accepted']
    assert n.handle.execute("SELECT scope FROM duckdb_secrets() WHERE name='explicit_expression'").fetchone() == (['https://expression.example.test/'],)
    reviewed = call('review_create')
    assert call('apply', plan_id=reviewed['plan_id'], plan_digest=reviewed['plan_digest'], confirmed=True)['provider_result']['accepted']
    assert n.handle.execute("SELECT name FROM duckdb_secrets() WHERE name='__default_http'").fetchone() == ('__default_http',)


@pytest.mark.parametrize('nodes', [
    [{'node_id': 'a', 'parent_id': 'missing', 'key': 'scope', 'kind': 'TEXT', 'value': 'private'}],
    [{'node_id': 'a', 'parent_id': 'a', 'key': 'scope', 'kind': 'LIST'}],
    [{'node_id': 'a', 'key': 'scope', 'kind': 'DOUBLE', 'value': 'private-nonnumeric-value'}],
    [{'node_id': 'a', 'key': 'scope', 'kind': 'INTEGER', 'value': '01'}],
    [{'node_id': 'a', 'key': 'scope', 'kind': 'LIST', 'value': 'private-discarded-value'}],
    [{'node_id': 'a', 'key': 'scope', 'kind': 'TEXT', 'value': 'private'}, {'node_id': 'b', 'key': 'scope', 'kind': 'NULL'}],
])
def test_secret_descriptor_private_tree_refuses_without_echoing_values(nodes):
    with pytest.raises(ValueError) as caught:
        compile_request('editor_secret_review_create', {'property_nodes': nodes})
    assert 'private' not in str(caught.value).lower() or 'private secret' in str(caught.value).lower()
    assert 'private-nonnumeric-value' not in str(caught.value) and 'private-discarded-value' not in str(caught.value)


def test_secret_descriptor_exact_numeric_and_null_tree():
    _, request = compile_request('editor_secret_review_create', {'property_nodes': [
        {'node_id': 'i', 'key': 'int', 'kind': 'INTEGER', 'value': '9007199254740993'},
        {'node_id': 'd', 'key': 'double', 'kind': 'DOUBLE', 'value': '1.25'},
        {'node_id': 'n', 'key': 'nullable', 'kind': 'NULL'},
    ]})
    assert request['draft']['properties'] == {'int': 9007199254740993, 'double': 1.25, 'nullable': None}


def test_receipt_descriptor_reads_native_archive_after_release_without_connecting(copy_fixture, tmp_path):
    from pgadmin.cdeadmin.workspace.duckdb_session_receipts import DuckDBSessionReceipts, action
    n = copy_fixture
    import uuid
    archive = DuckDBSessionReceipts(tmp_path / 'archive', 1, str(uuid.uuid4()), 'owned-target')
    n.client.bind_receipt_archive(n.handle, archive, n.route)
    reviewed = copying(n, 'review', source_catalog=n.aliases[0], destination_catalog=n.aliases[1], mode='SCHEMA')
    applied = copying(n, 'apply', review_id=reviewed['review_id'], review_digest=reviewed['review_digest'], confirmation=n.aliases[1], confirmed=True)
    assert applied['native_acknowledged']
    # Caller rollback is independent of the retained acknowledgement.
    n.handle.rollback()
    closed = n.client.close_session(n.handle)
    assert closed['receipt_release_recorded'] and closed['connection_released']
    reconstructed = DuckDBSessionReceipts(*archive.binding)
    from unittest.mock import patch
    with patch.object(n.client, '_connect', side_effect=AssertionError('Archive must not open a native connection')):
        transport, request = compile_request('editor_receipt_get', {'review_id': reviewed['review_id']})
        assert transport == 'duckdb_session_receipts'
        receipt = action(reconstructed, request)
        assert receipt['archived_read_only'] and not receipt['transaction_finality_inferred']
        assert receipt['original_session']['state'] == 'released' and not receipt['live_session_observed']
        _, request = compile_request('editor_receipt_list', {'limit': 1})
        assert action(reconstructed, request)['total'] == 1
        with pytest.raises(ValueError):
            action(reconstructed, {'operation': 'apply', 'review_id': reviewed['review_id']})


def test_receipt_adapter_requires_no_session_for_archive_but_confirmed_live_release():
    from pgadmin.cdeadmin.workspace.duckdb_editor_operations import serve
    server = SimpleNamespace(endpoint_profile=SimpleNamespace(profile_id='duckdb-native', provider_id='org.cdeadmin.duckdb'))
    service = SimpleNamespace(language_tool_action=Mock(return_value={'archived_read_only': True}), close_session=Mock(return_value={'provider_closed': True}))
    result = serve(service, server, {'database_target_id': 'owned', 'request': {'operation_id': 'editor_receipt_get', 'draft': {'review_id': 'saved'}}})
    assert result['archived_read_only']
    service.language_tool_action.assert_called_once_with(server, 'duckdb_session_receipts', {'database_target_id': 'owned', 'session_id': None, 'request': {'operation': 'get', 'review_id': 'saved'}})
    assert serve(service, server, {'database_target_id': 'owned', 'session_id': 'original', 'request': {'operation_id': 'editor_receipt_release', 'draft': {'confirmed': True}}})['provider_closed']
    service.close_session.assert_called_once_with(server, 'original', database_target_id='owned')
    with pytest.raises(ValueError, match='Confirm releasing'):
        compile_request('editor_receipt_release', {'confirmed': False})
    with pytest.raises(ValueError, match='original DuckDB query connection'):
        serve(service, server, {'database_target_id': 'owned', 'request': {'operation_id': 'editor_receipt_release', 'draft': {'confirmed': True}}})

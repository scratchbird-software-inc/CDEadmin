"""Connection-local settings must not succeed on a discarded attachment."""
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.provider import _create_client, SQLiteProvider
from pgadmin.cdeadmin.providers.sqlite.connection_settings import action
from pgadmin.cdeadmin.sdk import RelationalClientError


@pytest.fixture
def native(tmp_path):
    path = tmp_path / 'settings.db'
    sqlite3.connect(path).close()
    client = _create_client()
    route = {'database': str(path), 'filesystem_root': str(tmp_path)}
    source = client.open_session({'route': route})
    provider = SimpleNamespace(client=client, _require=Mock(), _editor_session=lambda request: source)
    try:
        yield path, route, client, source, provider
    finally:
        client.close()


@pytest.mark.parametrize('mode,code', [('OFF',0),('NORMAL',1),('FULL',2),('EXTRA',3)])
def test_original_provider_change_is_read_back_and_never_claims_file_or_future_defaults(native, mode, code):
    path, route, client, source, provider = native
    before = SQLiteProvider.native_connection_settings_action(provider, {'operation': 'inspect'})
    result = SQLiteProvider.native_connection_settings_action(provider, {'operation': 'set_connection_synchronous',
        'value': mode, 'expected_code': before['effective_code'], 'confirmed': True})
    assert result['scope'] == 'original-connection-main' and result['effective_code'] == code
    assert source.execute('PRAGMA synchronous').fetchone()[0] == code
    assert not any(result[key] for key in ['file_persisted', 'future_connection_defaults_changed',
                                          'commit_requested', 'rollback_requested'])
    provider._require.assert_any_call('administer')
    with sqlite3.connect(path) as observer:
        assert observer.execute('PRAGMA synchronous').fetchone()[0] == 2
    future = client.open_session({'route': route})
    assert future.execute('PRAGMA synchronous').fetchone()[0] == 2


def test_disposable_alter_refuses_before_any_native_statement(native):
    _, route, client, _, _ = native
    with pytest.raises(RelationalClientError, match='connection-local'):
        client.plan_admin_operation({'resource_kind': 'database', 'operation_id': 'alter',
            '_provider_route': route, 'draft': {'synchronous': 'OFF'},
            'target_resource': {'display_name': 'main', 'display_path': ['main']}})


def test_stale_and_pending_transaction_refusal_preserves_caller_savepoint_and_data(native):
    _, _, _, source, _ = native
    before = action(source, {'operation': 'inspect'})['effective_code']
    with pytest.raises(RelationalClientError, match='changed'):
        action(source, {'operation': 'set_connection_synchronous', 'value': 'OFF',
            'expected_code': (before + 1) % 4, 'confirmed': True})
    source.execute('CREATE TABLE owned(id INTEGER)')
    source.execute('SAVEPOINT owned_pending')
    source.execute('INSERT INTO owned VALUES (7)')
    with pytest.raises(RelationalClientError, match='caller transaction'):
        action(source, {'operation': 'set_connection_synchronous', 'value': 'OFF',
            'expected_code': before, 'confirmed': True})
    assert source.in_transaction and source.execute('SELECT id FROM owned').fetchone()[0] == 7
    source.execute('ROLLBACK TO owned_pending')
    source.execute('RELEASE owned_pending')
    assert source.execute('SELECT count(*) FROM owned').fetchone()[0] == 0
    assert action(source, {'operation': 'inspect'})['effective_code'] == before


@pytest.mark.parametrize('change', [{'value': []}, {'value': 'OFF; VACUUM'},
    {'expected_code': True}, {'confirmed': 'true'}, {'schema': 'attached'}])
def test_typed_refusals_do_not_mutate(native, change):
    source = native[3]
    before = action(source, {'operation': 'inspect'})['effective_code']
    request = {'operation': 'set_connection_synchronous', 'value': 'OFF',
               'expected_code': before, 'confirmed': True, **change}
    with pytest.raises(RelationalClientError):
        action(source, request)
    assert action(source, {'operation': 'inspect'})['effective_code'] == before


def test_descriptor_declares_exact_original_session_draft(native):
    from ui_descriptor_roundtrip import engine_operations, operation_draft
    op = engine_operations('sqlite')['set_connection_synchronous@database']
    source = native[3]
    before = action(source, {'operation': 'inspect'})['effective_code']
    draft = operation_draft(op, {'value': 'NORMAL', 'expected_code': before, 'confirmed': True})
    result = action(source, {'operation': op['operation_id'], **draft})
    assert result['effective_code'] == 1


def test_file_property_task_retains_only_durable_settings(native):
    path, route, client, source, _ = native
    planned = client.plan_admin_operation({'resource_kind': 'database', 'operation_id': 'alter',
        '_provider_route': route, 'draft': {'journal_mode': 'DELETE', 'user_version': 53},
        'target_resource': {'display_name': 'main', 'display_path': ['main']}})
    statements = [row['source'] for row in planned['provider_payload']['compiled']['statements']]
    assert statements == ['PRAGMA journal_mode = DELETE', 'PRAGMA user_version = 53']
    assert client.apply_admin_operation(planned)['accepted']
    with sqlite3.connect(path) as observer:
        assert observer.execute('PRAGMA user_version').fetchone()[0] == 53
        assert observer.execute('PRAGMA synchronous').fetchone()[0] == 2
    assert source.execute('PRAGMA synchronous').fetchone()[0] == 2


def test_review_is_parse_free_native_sql_preview_and_does_not_change_policy(native):
    source = native[3]
    before = action(source, {'operation': 'inspect'})['effective_code']
    review = action(source, {'operation': 'review', 'value': 'EXTRA'})
    assert review['native_statement'] == 'PRAGMA main.synchronous=EXTRA'
    assert review['expected_code'] == before and review['ready_to_apply']
    assert action(source, {'operation': 'inspect'})['effective_code'] == before


def test_unavailable_native_pragma_is_not_a_default_or_success():
    cursor = Mock()
    cursor.execute.return_value.fetchone.return_value = None
    connection = SimpleNamespace(cursor=lambda: cursor, in_transaction=False)
    with pytest.raises(RelationalClientError, match='observation unavailable'):
        action(connection, {'operation': 'set_connection_synchronous', 'value': 'OFF',
                            'expected_code': 2, 'confirmed': True})
    cursor.execute.assert_called_once_with('PRAGMA main.synchronous')
    cursor.close.assert_called_once()


def test_studio_binds_server_session_and_only_mutations_invalidate_native_review(native):
    import threading
    from pgadmin.cdeadmin.data_studio.studio import DataStudioService
    provider = native[4]
    calls = []
    def dispatch(request):
        calls.append(request)
        return SQLiteProvider.native_connection_settings_action(provider, request)
    session = SimpleNamespace(language_profile='sqlite-sql',
        provider_session={'session_id': 'server-private-binding'}, provider_isolation_key='owned', native_work_revision=0)
    context = SimpleNamespace(provider_id='org.cdeadmin.sqlite', isolation_key='owned')
    service = SimpleNamespace(scripts=SimpleNamespace(lock=threading.RLock(), check_execution=Mock()),
        _sessions={'public-session': session},
        _operational_session=lambda *_: (session, SimpleNamespace(instance=SimpleNamespace(native_connection_settings_action=dispatch))))
    inspect = DataStudioService.sqlite_connection_settings_action(service, context, 'public-session',
        {'operation': 'inspect', 'session_id': 'forged', 'language_profile': 'forged'})
    assert calls[-1]['session_id'] == 'server-private-binding' and calls[-1]['language_profile'] == 'sqlite-sql'
    assert session.native_work_revision == 0
    DataStudioService.sqlite_connection_settings_action(service, context, 'public-session',
        {'operation': 'review', 'value': 'NORMAL'})
    assert session.native_work_revision == 0
    DataStudioService.sqlite_connection_settings_action(service, context, 'public-session',
        {'operation': 'set_connection_synchronous', 'value': 'NORMAL',
         'expected_code': inspect['effective_code'], 'confirmed': True})
    assert session.native_work_revision == 1

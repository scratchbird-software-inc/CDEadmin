"""Schema review authorization, durable claim, native outcomes and replay refusal."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
from contextlib import nullcontext

import pytest
from pgadmin.cdeadmin.operations.fileio import has_private_file_permissions

from tools.tests.test_firebird_schema_plan import document, seq
from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan
from pgadmin.cdeadmin.workspace.firebird_schema_apply import SchemaApplications, SchemaApplyError
from pgadmin.cdeadmin.providers.firebird import schema_application as native


def documents():
    base, desired = document([seq()]), document([seq(increment=2)])
    for value in (base, desired):
        value['rows']['database:database']['native'].update(guid='native-guid', file_id='native-file')
    return base, desired


def review(tmp_path, clock=lambda: 100):
    base, desired = documents()
    plan = build_plan(base, desired, base)
    store = SchemaApplications(tmp_path / 'schema.json', clock)
    result = store.review(plan, base, desired, 7, 'route-binding', 'db.fdb')
    return store, result, base, desired


def request(review):
    return {'review_id': review['review_id'], 'review_digest': review['review_digest'], 'confirmed': True}


def test_review_does_not_expose_owner_binding_or_source_documents(tmp_path):
    store, result, _base, _desired = review(tmp_path)
    assert result['state'] == 'reviewed' and result['expires_at'] == 400
    assert not {'owner', 'binding', 'baseline', 'desired'} & result.keys()
    for owner, binding in [(8, 'route-binding'), (7, 'different')]:
        with pytest.raises(SchemaApplyError):
            store.get(result['review_id'], owner, binding)
    assert has_private_file_permissions(tmp_path / 'schema.json')


def test_durable_review_preserves_creation_order_and_execution_fingerprint(tmp_path):
    from tools.tests.test_firebird_schema_plan import obj
    base, _ = documents()
    desired = deepcopy(base)
    addition = document([obj('exception', 'E_NEW', message='new message',
                            creation_dependencies=['sequence:S'])])['rows']['exception:E_NEW']
    desired['rows'][addition['resource_id']] = addition
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    store = SchemaApplications(tmp_path / 'ordered-review.json')
    reviewed = store.review(plan, base, desired, 7, 'binding', 'db.fdb')
    def execute(record):
        assert record['desired']['rows']['exception:E_NEW']['native']['creation_dependencies'] == ['sequence:S']
        rebuilt = build_plan(record['baseline'], record['desired'], base)
        assert rebuilt['execution_sha256'] == plan['execution_sha256']
        return {'state': 'not_executed'}
    # Assertions raised by the native callback would be retained as uncertainty.
    result = SchemaApplications(store.path).apply(request(reviewed), 7, 'binding', execute)
    assert result['state'] == 'not_executed', result


def test_explicit_confirmation_digest_expiry_and_owner_precede_dispatch(tmp_path):
    now = [100]
    store, result, *_ = review(tmp_path, lambda: now[0])
    execute = Mock()
    for change in [{'confirmed': False}, {'review_digest': 'wrong'}, {'source': 'DROP DATABASE'}]:
        with pytest.raises(SchemaApplyError):
            store.apply({**request(result), **change}, 7, 'route-binding', execute)
    now[0] = 401
    with pytest.raises(SchemaApplyError, match='expired'):
        store.apply(request(result), 7, 'route-binding', execute)
    execute.assert_not_called()


def test_two_store_instances_race_and_restart_never_repeat_native_call(tmp_path):
    store, result, *_ = review(tmp_path)
    execute = Mock(return_value={'state': 'native_commit_returned'})
    another = SchemaApplications(store.path, lambda: 100)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda item: item.apply(request(result), 7, 'route-binding', execute),
                                 [store, another]))
    assert execute.call_count == 1
    assert all(item['state'] in {'unknown_outcome', 'native_commit_returned'} for item in outcomes)
    reopened = SchemaApplications(store.path, lambda: 100)
    assert reopened.apply(request(result), 7, 'route-binding', execute)['state'] == 'native_commit_returned'
    assert execute.call_count == 1


def test_interrupted_dispatch_retains_uncertainty_without_replay(tmp_path):
    store, result, *_ = review(tmp_path)
    def terminate(_record):
        raise SystemExit('simulated process exit')
    with pytest.raises(SystemExit):
        store.apply(request(result), 7, 'route-binding', terminate)
    execute = Mock()
    restarted = SchemaApplications(store.path, lambda: 100)
    assert restarted.apply(request(result), 7, 'route-binding', execute)['state'] == 'unknown_outcome'
    execute.assert_not_called()


def native_setup(monkeypatch, base, desired):
    connection = Mock()
    cursor = Mock()
    connection.cursor.return_value = nullcontext(cursor)
    client = SimpleNamespace(_temporary_operation=lambda: nullcontext(),
        _connect=Mock(return_value=connection), _release_attachment=Mock())
    provider = SimpleNamespace(client=client, permissions=SimpleNamespace(require=Mock()), _admit_transport=Mock())
    monkeypatch.setattr(native, 'capture', Mock(side_effect=[base, desired]))
    return provider, connection, cursor, {'plan': build_plan(base, desired, base), 'baseline': base, 'desired': desired}


def test_native_commit_then_fresh_rediscovery_and_release(monkeypatch):
    base, desired = documents()
    provider, connection, cursor, record = native_setup(monkeypatch, base, desired)
    result = native.apply_review(provider, {'database': 'db', 'transaction_auto_commit': True}, record)
    assert result['state'] == 'native_commit_returned' and result['attachment_released']
    assert result['rediscovery']['objects'][0]['matches_reviewed_properties']
    connection.commit.assert_called_once_with()
    cursor.execute.assert_called_once_with('ALTER SEQUENCE "S" INCREMENT BY 2')
    route = provider.client._connect.call_args.args[0]['route']
    assert route['transaction_auto_commit'] is False
    assert route['transaction_isolation'] == 'SNAPSHOT'


@pytest.mark.parametrize('commit_failure', [False, True])
def test_statement_rollback_and_commit_uncertainty_remain_distinct(monkeypatch, commit_failure):
    base, desired = documents()
    provider, connection, cursor, record = native_setup(monkeypatch, base, desired)
    (connection.commit if commit_failure else cursor.execute).side_effect = RuntimeError('lost response')
    result = native.apply_review(provider, {'database': 'db'}, record)
    assert result['state'] == ('unknown_outcome' if commit_failure else 'native_rollback_returned')
    assert result['native_rollback_returned'] and not result['native_commit_returned']
    assert result['attachment_released']


def test_preflight_drift_executes_nothing(monkeypatch):
    base, desired = documents()
    provider, connection, cursor, record = native_setup(monkeypatch, base, desired)
    changed = deepcopy(base)
    changed['rows']['sequence:S']['native']['description'] = 'concurrent comment'
    native.capture.side_effect = [changed]
    result = native.apply_review(provider, {'database': 'db'}, record)
    assert result['state'] == 'not_executed'
    cursor.execute.assert_not_called()
    connection.commit.assert_not_called()
    assert result['attachment_released']


def test_release_or_rediscovery_failure_does_not_erase_commit(monkeypatch):
    base, desired = documents()
    provider, connection, cursor, record = native_setup(monkeypatch, base, desired)
    native.capture.side_effect = [base, RuntimeError('read failed')]
    provider.client._release_attachment.side_effect = RuntimeError('release failed')
    result = native.apply_review(provider, {'database': 'db'}, record)
    assert result['state'] == 'native_commit_returned'
    assert not result['rediscovery']['available'] and not result['attachment_released']


def test_host_review_apply_and_receipt_are_owner_route_and_target_bound(tmp_path, monkeypatch):
    from dataclasses import dataclass
    from tools.tests.test_firebird_catalog_export import service
    from tools.tests.test_firebird_schema_plan import source, obj
    from pgadmin.cdeadmin.providers.firebird.provider import FirebirdProvider
    from pgadmin.cdeadmin.operations.store import JsonOperationStore
    from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceError
    @dataclass
    class Context:
        endpoint_id: str = 'endpoint'
        effective_permissions: frozenset = frozenset({'administer'})
    value, server = service()
    server.user_id = 7
    context = Context()
    route = {'database': 'db.fdb', 'credential_reference_id': 'SECRET-REFERENCE'}
    value.endpoint_service.workspace.return_value = (context, {'route': route}, {})
    provider = object.__new__(FirebirdProvider)
    provider.attachment_mode = 'network'
    provider.permissions = SimpleNamespace(require=Mock())
    value.endpoint_service.provider_registry.resolve.return_value.instance = provider
    value.operation_bus = SimpleNamespace(store=JsonOperationStore(tmp_path / 'operations.json'))
    rows = [obj('server', 'Firebird', version='5.0.4'),
            obj('database', 'database', sql_dialect='3', guid='native-guid', file_id='native-file'), seq()]
    value.resource_service.list_page.return_value.to_dict.return_value['items'] = rows
    options = {'database_target_id': 'target', 'generation': 'current',
               'baseline': source([seq()]), 'desired': source([seq(increment=2)])}
    plan = value.plan_firebird_schema(server, options)
    ticket = value.firebird_schema_application(server, 'firebird_schema_review',
                                               {**options, 'execution_sha256': plan['execution_sha256']})
    assert 'SECRET-REFERENCE' not in str(ticket)
    dispatch = Mock(return_value={'state': 'native_commit_returned'})
    monkeypatch.setattr(native, 'apply_review', dispatch)
    applied = value.firebird_schema_application(server, 'firebird_schema_apply',
                          {**request(ticket), 'database_target_id': 'target'})
    assert applied['state'] == 'native_commit_returned'
    dispatch.assert_called_once()
    receipt_request = {'database_target_id': 'target', 'review_id': ticket['review_id']}
    assert value.firebird_schema_application(server, 'firebird_schema_receipt', receipt_request) == applied
    for key, change in [('database', 'different.fdb'), ('credential_reference_id', 'ROTATED')]:
        old = route[key]
        route[key] = change
        with pytest.raises(ProviderWorkspaceError):
            value.firebird_schema_application(server, 'firebird_schema_receipt', receipt_request)
        route[key] = old
    server.user_id = 8
    with pytest.raises(ProviderWorkspaceError):
        value.firebird_schema_application(server, 'firebird_schema_receipt', receipt_request)
    server.user_id = 7
    provider.permissions.require.side_effect = PermissionError('denied')
    with pytest.raises(PermissionError):
        value.firebird_schema_application(server, 'firebird_schema_receipt', receipt_request)
    dispatch.assert_called_once()

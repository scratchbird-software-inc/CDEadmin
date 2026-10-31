"""Durable recovery dispatch, independent authority and uncertain outcomes."""

from concurrent.futures import ThreadPoolExecutor
import copy
import threading

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION  # noqa
from pgadmin.cdeadmin.operations.store import JsonOperationStore
from pgadmin.cdeadmin.providers.firebird.recovery_groups import (
    RecoveryGroups, RecoveryGroupError,
)


class JsonResponse(dict):
    """make_json_response's payload, with headers the handler can set."""

    def __init__(self, **value):
        super().__init__(**value)
        self.headers = {}


@pytest.fixture
def setup(tmp_path):
    store = JsonOperationStore(tmp_path / 'operations.json')
    groups = RecoveryGroups(store, clock=lambda: 100)
    calls = []

    def resolve(selection):
        identifier = selection['server_id']

        def dispatch(decision):
            # A different reader must see intent before the native call.
            state = JsonOperationStore(store.path).read()
            assert any(p['state'] == 'unknown_outcome'
                       for g in state['firebird_recovery_groups'].values()
                       for p in g['participants'])
            calls.append((identifier, decision))
            return {'native_decision_returned': True,
                    'native_decision_requested': decision,
                    'attachment_released': True}

        return {'database': f'/owned/{identifier}.fdb',
                'server_name': f'Endpoint {identifier}',
                'database_identity': {'guid': str(identifier), 'file_id': '1'},
                'binding': str(identifier),
                'observation': {'transaction_id': selection['transaction_id'],
                                'local_inventory_state': 'limbo'},
                'dispatch': dispatch}

    request = {'decision': 'commit', 'participants': [
        {'server_id': n, 'database_target_id': str(n),
         'transaction_id': str(n + 100)} for n in (1, 2)]}
    review = groups.preview(request, 1, 7, resolve)
    confirmation = {
        'group_id': review['group_id'],
        'review_digest': review['review_digest'],
        'decision': 'commit', 'coordinator_reviewed': True,
        'confirmations': [{'database': p['database'],
                           'transaction_id': p['transaction_id']}
                          for p in review['participants']]}
    return groups, store, resolve, calls, request, review, confirmation


def test_success_is_per_participant_and_never_replayed_after_restart(setup):
    groups, store, resolve, calls, _, review, confirmation = setup
    result = groups.apply(confirmation, 1, 7, resolve)
    assert result['state'] == 'native_calls_returned'
    assert result['global_outcome_inferred'] is False
    assert result['atomicity'] == 'not-claimed'
    assert calls == [(1, 'commit'), (2, 'commit')]
    restarted = RecoveryGroups(JsonOperationStore(store.path))
    again = restarted.apply(confirmation, 1, 7, resolve)
    assert again['state'] == result['state']
    assert len(calls) == 2
    assert 'binding' not in review['participants'][0]


def test_uncertain_first_response_stops_later_decisions(setup):
    groups, _, resolve, calls, _, _, confirmation = setup

    def uncertain(selection):
        result = resolve(selection)

        def dispatch(_decision):
            calls.append(selection['server_id'])
            raise OSError('credential material must not be retained')

        result['dispatch'] = dispatch
        return result

    result = groups.apply(confirmation, 1, 7, uncertain)
    assert result['state'] == 'needs_review'
    assert [p['state'] for p in result['participants']] == [
        'unknown_outcome', 'not_dispatched']
    assert 'credential material' not in str(result)
    groups.apply(confirmation, 1, 7, uncertain)
    assert calls == [1]


@pytest.mark.parametrize(
    'key', ['binding', 'database_identity', 'observation'])
def test_stale_participant_prevents_every_decision(setup, key):
    groups, _, resolve, calls, _, _, confirmation = setup

    def changed(selection):
        result = resolve(selection)
        if selection['server_id'] == 2:
            result[key] = 'changed'
        return result

    with pytest.raises(RecoveryGroupError, match='changed'):
        groups.apply(confirmation, 1, 7, changed)
    assert not calls


def test_independent_denial_prevents_every_decision(setup):
    groups, _, resolve, calls, _, _, confirmation = setup

    def denied(selection):
        if selection['server_id'] == 2:
            raise PermissionError('denied')
        return resolve(selection)

    with pytest.raises(PermissionError):
        groups.apply(confirmation, 1, 7, denied)
    assert not calls


def test_duplicate_native_identity_rejected_across_registrations(setup):
    groups, _, resolve, calls, request, _, _ = setup
    request = copy.deepcopy(request)
    request['participants'][1]['transaction_id'] = '101'

    def alias(selection):
        result = resolve(selection)
        result['database_identity'] = {'guid': 'same', 'file_id': 'same'}
        return result

    with pytest.raises(RecoveryGroupError, match='Duplicate'):
        groups.preview(request, 1, 7, alias)
    assert not calls


@pytest.mark.parametrize('owner,coordinator', [(2, 7), (1, 8)])
def test_group_cannot_cross_owner_or_coordinator(setup, owner, coordinator):
    groups, _, resolve, calls, _, review, confirmation = setup
    with pytest.raises(RecoveryGroupError):
        groups.get(review['group_id'], owner, coordinator)
    with pytest.raises(RecoveryGroupError):
        groups.apply(confirmation, owner, coordinator, resolve)
    assert not calls


def test_dispatch_write_failure_prevents_native_call(setup, monkeypatch):
    groups, store, resolve, calls, _, _, confirmation = setup
    original = store._commit

    def fail(candidate):
        if any(p['state'] == 'unknown_outcome'
               for g in candidate['firebird_recovery_groups'].values()
               for p in g['participants']):
            raise OSError('disk full')
        original(candidate)

    monkeypatch.setattr(store, '_commit', fail)
    with pytest.raises(OSError):
        groups.apply(confirmation, 1, 7, resolve)
    assert not calls
    restarted = RecoveryGroups(JsonOperationStore(store.path))
    assert restarted.apply(confirmation, 1, 7, resolve)['state'] == (
        'unknown_outcome')
    assert not calls


def test_concurrent_apply_claims_group_once(setup):
    groups, _, resolve, calls, _, _, confirmation = setup
    barrier = threading.Barrier(2, timeout=5)

    def concurrent(selection):
        result = resolve(selection)
        if selection['server_id'] == 2:
            barrier.wait()
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(groups.apply, confirmation, 1, 7, concurrent)
                   for _ in range(2)]
        for future in futures:
            future.result()
    assert calls == [(1, 'commit'), (2, 'commit')]


@pytest.mark.parametrize(
    'change', ['confirmation', 'decision', 'review', 'expiry'])
def test_unconfirmed_or_expired_review_cannot_dispatch(setup, change):
    groups, _, resolve, calls, _, _, confirmation = setup
    if change == 'confirmation':
        confirmation['confirmations'][1]['database'] = 'wrong'
    elif change == 'decision':
        confirmation['decision'] = 'rollback'
    elif change == 'review':
        confirmation['coordinator_reviewed'] = False
    else:
        groups.clock = lambda: 401
    with pytest.raises(RecoveryGroupError):
        groups.apply(confirmation, 1, 7, resolve)
    assert not calls


def test_receipt_persistence_failure_retains_unknown_without_replay(
        setup, monkeypatch):
    groups, store, resolve, calls, _, _, confirmation = setup
    commit = store._commit

    def fail(candidate):
        if any(p['state'] == 'native_decision_returned'
               for g in candidate['firebird_recovery_groups'].values()
               for p in g['participants']):
            raise OSError('Receipt storage unavailable')
        return commit(candidate)

    monkeypatch.setattr(store, '_commit', fail)
    with pytest.raises(OSError):
        groups.apply(confirmation, 1, 7, resolve)
    assert calls == [(1, 'commit')]
    restarted = RecoveryGroups(JsonOperationStore(store.path))
    result = restarted.apply(confirmation, 1, 7, resolve)
    assert result['state'] == 'unknown_outcome'
    assert result['participants'][0]['state'] == 'unknown_outcome'
    assert result['participants'][1]['state'] == 'not_dispatched'
    assert calls == [(1, 'commit')]


def test_known_receipt_with_unconfirmed_cleanup_stops_group(setup):
    groups, _, resolve, calls, _, _, confirmation = setup

    def unresolved(selection):
        result = resolve(selection)
        dispatch = result['dispatch']

        def incomplete(decision):
            return {**dispatch(decision), 'attachment_released': False}

        return {**result, 'dispatch': incomplete}

    result = groups.apply(confirmation, 1, 7, unresolved)
    assert result['state'] == 'needs_review'
    assert result['participants'][0]['state'] == 'native_decision_returned'
    assert result['participants'][1]['state'] == 'not_dispatched'
    groups.apply(confirmation, 1, 7, unresolved)
    assert calls == [(1, 'commit')]


def test_expiration_during_preflight_prevents_dispatch(setup):
    groups, _, resolve, calls, _, _, confirmation = setup

    def slow(selection):
        result = resolve(selection)
        groups.clock = lambda: 401
        return result

    with pytest.raises(RecoveryGroupError, match='expired'):
        groups.apply(confirmation, 1, 7, slow)
    assert not calls


def test_workspace_preserves_receipt_when_refresh_fails(setup, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from tools.cdeadmin_relational_provider_live_verify import _context
    from pgadmin.cdeadmin.providers.firebird.provider import (
        FirebirdProvider, PROFILE,
    )
    from pgadmin.cdeadmin.providers.firebird import recovery_groups
    from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService

    _, store, _, _, request, _, _ = setup
    context = _context(PROFILE)
    provider = Mock(spec=FirebirdProvider)
    provider.client = Mock()
    provider.client.run_limbo_operation.return_value = {
        'native_decision_requested': 'commit',
        'native_decision_returned': True, 'attachment_released': True}
    monkeypatch.setattr(recovery_groups, 'inspect_participant',
                        lambda p, r, t: ({'guid': r['database']}, {'id': t}))
    endpoints = SimpleNamespace(
        workspace=lambda s, database_target_id: (
            context, {'route': {'database': str(s.id)}}, None),
        provider_registry=SimpleNamespace(
            resolve=lambda c: SimpleNamespace(instance=provider)))
    resources = Mock()
    resources.invalidate.side_effect = RuntimeError('credential-canary')
    service = ProviderWorkspaceService(
        endpoints, resources, None, None,
        operation_bus=SimpleNamespace(store=store))
    servers = {i: SimpleNamespace(
        id=i, user_id=1, name=str(i),
        endpoint_profile=SimpleNamespace(profile_id='firebird-native'))
        for i in (1, 2)}
    preview = service.firebird_recovery_action(
        servers[1], 'firebird_recovery_preview', request, servers.get)
    confirmation = {key: preview[key] for key in (
        'group_id', 'review_digest', 'decision')}
    confirmation.update(coordinator_reviewed=True, confirmations=[
        {key: p[key] for key in ('database', 'transaction_id')}
        for p in preview['participants']])
    result = service.firebird_recovery_action(
        servers[1], 'firebird_recovery_apply', confirmation, servers.get)
    assert result['state'] == 'native_calls_returned'
    assert provider.client.run_limbo_operation.call_count == 2
    assert 'credential-canary' not in str(result)
    for item in result['participants']:
        assert item['receipt']['workspace_follow_up'] == {
            'refresh_required': True, 'error_type': 'RuntimeError'}


def test_process_exit_during_dispatch_is_not_replayed(setup):
    import json
    import os
    from pathlib import Path
    import subprocess
    import sys

    groups, store, resolve, calls, _, review, confirmation = setup
    # The child dies after dispatch is recorded, before a receipt returns.
    # Native success is independently covered by the live gate.
    program = '''
import json, os, sys
from tools.cdeadmin_firebird_recovery_group_gate import JsonOperationStore
from pgadmin.cdeadmin.providers.firebird.recovery_groups import RecoveryGroups

path, request = json.loads(sys.stdin.read())
store = JsonOperationStore(path)
groups = RecoveryGroups(store, clock=lambda: 100)
def resolve(selection):
    record = next(iter(store.read()['firebird_recovery_groups'].values()))
    item = next(p for p in record['participants']
                if p['server_id'] == selection['server_id'])
    return {**item, 'dispatch': lambda decision: os._exit(73)}
groups.apply(request, 1, 7, resolve)
'''
    child = subprocess.run(
        [sys.executable, '-B', '-c', program],
        input=json.dumps([str(store.path), confirmation]), text=True,
        capture_output=True, timeout=30,
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
    assert child.returncode == 73, child.stderr
    reopened = RecoveryGroups(JsonOperationStore(store.path))
    result = reopened.get(review['group_id'], 1, 7)
    assert result['state'] == 'unknown_outcome'
    assert [p['state'] for p in result['participants']] == [
        'unknown_outcome', 'not_dispatched']
    reopened.apply(confirmation, 1, 7, resolve)
    assert not calls


@pytest.mark.parametrize('action', [
    'firebird_recovery_preview', 'firebird_recovery_apply',
    'firebird_recovery_status', 'firebird_recovery_targets'])
def test_workspace_http_dispatch_uses_owned_endpoints(action):
    import ast
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import Mock
    from flask import Flask, request

    source = Path(__file__).resolve().parents[2] / (
        'web/pgadmin/browser/server_groups/servers/__init__.py')
    syntax = ast.parse(source.read_text())
    function = next(n for n in ast.walk(syntax)
                    if isinstance(n, ast.FunctionDef) and
                    n.name == 'cde_workspace')
    function.decorator_list = []
    candidate = SimpleNamespace(id=2, user_id=11, name='Owned peer',
                                endpoint_profile=SimpleNamespace(
                                    profile_id='firebird-native'))
    query = Mock()
    query.filter_by.return_value = query
    query.first.return_value = candidate
    query.all.return_value = [candidate, SimpleNamespace(
        endpoint_profile=SimpleNamespace(profile_id='mysql-native'))]
    service = Mock()
    service.endpoint_service.database_catalog.return_value = {'targets': [{
        'target_id': 'owned-target', 'display_name': 'Owned database',
        'database': 'database-alias'}]}
    service.firebird_recovery_action.return_value = {'state': 'reviewed'}
    server = SimpleNamespace(id=1, user_id=11)
    app = Flask(__name__)
    namespace = {
        'get_server': Mock(return_value=server),
        '_is_non_owner': lambda _: False,
        '_cde_registration': lambda _: {
            'workflow': 'provider_endpoint', 'profile_id': 'firebird-native'},
        'provider_workspace_for_app': lambda _: service,
        'current_app': app, 'current_user': SimpleNamespace(id=11),
        'request': request, 'Server': SimpleNamespace(query=query),
        'gettext': lambda value: value,
        'make_json_response': JsonResponse,
        'bad_request': lambda **value: value,
    }
    # Module constants the handler reads come from the real source, so a
    # handler that gains one is tested with its actual value.
    referenced = {name.id for name in ast.walk(function)
                  if isinstance(name, ast.Name)}
    for node in syntax.body:
        if isinstance(node, ast.Assign) and all(
                isinstance(target, ast.Name) and target.id.isupper() and
                target.id in referenced and target.id not in namespace
                for target in node.targets):
            exec(compile(ast.Module(body=[node], type_ignores=[]),
                         str(source), 'exec'), namespace)
    for node in ast.walk(function):
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            for name in ast.walk(node.type):
                if isinstance(name, ast.Name) and name.id not in namespace:
                    namespace[name.id] = type(name.id, (Exception,), {})
    exec(compile(ast.Module(body=[function], type_ignores=[]),
                 str(source), 'exec'), namespace)
    with app.test_request_context('/', method='POST', json={
            'action': action, 'request': {'group_id': 'owned-group'}}):
        response = namespace['cde_workspace'](Mock(), 1, 1)
        if action == 'firebird_recovery_targets':
            assert response['data'] == {'endpoints': [{
                'server_id': 2, 'name': 'Owned peer', 'targets': [{
                    'target_id': 'owned-target',
                    'display_name': 'Owned database',
                    'database': 'database-alias'}]}]}
            query.filter_by.assert_called_once_with(user_id=11)
        else:
            args = service.firebird_recovery_action.call_args.args
            assert args[:3] == (server, action, {'group_id': 'owned-group'})
            assert args[3](2) is candidate
            query.filter_by.assert_called_once_with(id=2, user_id=11)

"""Stateful backend boundaries for the remaining Group9 work."""
import base64
import json
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION
from pgadmin.cdeadmin.providers.mysql_family.mysql_connections import Connector
from pgadmin.cdeadmin.providers.mysql_family import mysql_session_catalog as sessions
from pgadmin.cdeadmin.report_scheduler.crypto import WorkerKeyRing
from pgadmin.cdeadmin.security.generated_passwords import PasswordResults
from pgadmin.cdeadmin.security import SecretAccessError, SecretLease
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.visual_admin import VisualAdminAccessError, VisualAdminValidationError
from pgadmin.cdeadmin.visual_admin.refusals import response


def results(tmp_path, endpoint=None, principal='user:7', clock=lambda: 100):
    return PasswordResults(tmp_path, WorkerKeyRing({'owned': base64.b64encode(b'x' * 32).decode()}, 'owned'),
        endpoint or str(uuid4()), principal, str(uuid4()), ttl=60, clock=clock)


def publish(store, value='private-password-canary', factor=1):
    reservation = store.reserve('native-user', '%', (1, 2))
    with SecretLease(value) as lease:
        reference = store.publish(reservation, factor, lease)
    return reservation, reference


def test_encrypted_partial_results_survive_restart_without_replay_and_expire(tmp_path):
    now = [100]
    store = results(tmp_path, clock=lambda: now[0])
    plan, reference = publish(store)
    store.release(plan)
    restarted = results(tmp_path, store.endpoint, clock=lambda: now[0])
    recovered = restarted.recover(plan)
    assert recovered['state'] == 'partially_published' and recovered['automatic_retry'] is False
    assert recovered['passwords'] == [{'factor': 1, 'secret_reference_id': reference.reference_id}]
    with restarted.acquire(reference.reference_id) as lease:
        assert lease.use(bytes) == b'private-password-canary'
    assert 'private-password-canary' not in (store.root / 'results.json').read_text() + str(recovered)
    with pytest.raises(SecretAccessError):
        store.reserve('native-user', '%', (1,))
    now[0] = 160
    with pytest.raises(SecretAccessError):
        restarted.acquire(reference.reference_id)
    assert not json.loads((store.root / 'results.json').read_text())['provider_audit']


def test_references_cannot_cross_owner_endpoint_or_authenticated_envelope(tmp_path):
    store = results(tmp_path)
    plan, reference = publish(store)
    for other in (results(tmp_path), results(tmp_path, store.endpoint, 'user:8')):
        with pytest.raises(SecretAccessError):
            other.recover(plan)
        with pytest.raises(SecretAccessError):
            other.acquire(reference.reference_id)
    path = store.root / 'results.json'
    data = json.loads(path.read_text())
    data['provider_audit'][plan]['user'] = 'substituted-user'
    path.write_text(json.dumps(data))
    with pytest.raises(Exception):
        store.acquire(reference.reference_id)


def test_source_overlay_shadows_base_columns_and_is_invalidated():
    client = SimpleNamespace(_session_catalogs={})
    handle = object()
    snapshot = {'active_role': '`selected`@`%`', 'selected_temporary_tables': [['d', 't']],
        'resources': [{'resource_kind': 'column', 'display_path': ['d', 't', 'temporary_column']}],
        'original_diagnostics_preserved': False}
    client._session_catalogs[id(handle)] = snapshot
    result = {'context': {}, 'resources': [{'resource_kind': 'column', 'display_path': ['d', 't', 'base_column']}],
        'observations': [{'section': 'retained-session-overlays'}]}
    sessions.overlay(result, snapshot)
    assert result['resources'] == snapshot['resources'] and result['context']['original_active_roles_observed']
    sessions.invalidate(client, handle)
    assert not client._session_catalogs


def test_native_constraint_actions_and_check_enforcement_are_not_discarded():
    foreign = {'kind': 'FOREIGN KEY', 'columns': ['child'], 'references_table': ['d', 'parent'],
        'references_columns': ['id'], 'on_delete': 'CASCADE', 'on_update': 'SET NULL'}
    assert MYSQL_ADMINISTRATION._constraint_definition(foreign).endswith(' ON DELETE CASCADE ON UPDATE SET NULL')
    assert MYSQL_ADMINISTRATION._constraint_definition({'kind': 'CHECK', 'expression': 'id>0', 'enforced': False}).endswith(' NOT ENFORCED')
    for invalid in ({**foreign, 'on_delete': 'CASCADE;DROP TABLE p'}, {'kind': 'CHECK', 'expression': 'id>0', 'enforced': 'false'}):
        with pytest.raises(RelationalClientError):
            MYSQL_ADMINISTRATION._constraint_definition(invalid)
    draft = MYSQL_ADMINISTRATION._normalize_draft('table', 'create', {'name': 'owned', 'parent': 'd',
        'columns': [{'name': 'id', 'type': 'INT'}], 'temporary': True})
    compiled = MYSQL_ADMINISTRATION._compile({'resource_kind': 'table', 'operation_id': 'create', 'draft': draft})
    assert compiled['statements'][0]['source'].startswith('CREATE TEMPORARY TABLE ')
    assert 'mysql_session_catalog' in compiled
    nested = MYSQL_ADMINISTRATION._normalize_draft('table', 'create', {
        'name': 'owned', 'columns': [{'name': 'id', 'type': 'INT'}], 'options': {'temporary': True}})
    assert nested['options']['temporary'] is True
    with pytest.raises(RelationalClientError):
        MYSQL_ADMINISTRATION._normalize_draft('table', 'create', {
            'name': 'owned', 'temporary': False, 'options': {'temporary': True}})


def test_target_pool_credentials_are_leased_and_pools_are_independently_owned(monkeypatch):
    class NativeError(Exception): pass
    leases = []
    def acquire(reference, principal, purpose, kind):
        assert principal == 'user:7' and purpose == 'connect' and kind == 'password'
        lease = SecretLease(reference); leases.append(lease); return lease
    connector = Connector(SimpleNamespace(Error=NativeError, InterfaceError=NativeError), acquire)
    calls = []
    def native(**options):
        assert not {'pool_name', 'pool_size', 'failover', 'credential_reference_id'} & options.keys()
        calls.append(options)
        if options['host'] == 'unavailable': raise NativeError()
        return Mock()
    connector._native_connect = native
    targets = [ {'host': 'unavailable', 'priority': 100, 'credential_reference_id': 'first', 'credential_kind': 'password', 'pool_name': 'same', 'pool_size': 1},
        {'host': 'available', 'priority': 50, 'credential_reference_id': 'second', 'credential_kind': 'password', 'pool_name': 'same', 'pool_size': 1} ]
    first = connector.connect('user:7', failover=targets)
    second = connector.connect('user:7', failover=[{**targets[0], 'host': 'another'}, targets[1]])
    assert len(connector._pools) == 2 and first._pool is not second._pool
    assert all(lease.closed for lease in leases)
    assert calls[0]['password'] == 'first' and calls[1]['password'] == 'second'
    first.close(); second.close(); connector.close()
    assert all(pool.retired for _signature, pool in connector._pools.values())


def test_failover_does_not_retry_missing_credentials_or_plain_nested_passwords():
    module = SimpleNamespace(Error=OSError, InterfaceError=OSError)
    acquire = Mock(side_effect=SecretAccessError('denied'))
    connector = Connector(module, acquire); connector._native_connect = Mock()
    for target in ({'password': 'must-not-be-stored'}, {'credential_reference_id': 'unknown'}):
        with pytest.raises((SecretAccessError, RelationalClientError)):
            connector.connect('user:7', failover=[{**target, 'priority': 100}, {'host': 'fallback', 'priority': 0}])
    connector._native_connect.assert_not_called()


def test_temporary_management_discards_the_physical_pool_session_even_without_reset():
    connector = Connector(SimpleNamespace())
    native = Mock(); connector._native_connect = Mock(return_value=native)
    handle = connector(pool_size=1, pool_reset_session=False)
    handle._cdeadmin_temporary_management_used = True
    handle.close()
    native.close.assert_called_once()
    assert not next(iter(connector._pools.values()))[1].idle


def test_failover_pool_state_cannot_cross_application_principals():
    connector = Connector(SimpleNamespace(Error=OSError, InterfaceError=OSError))
    connector._native_connect = Mock(side_effect=lambda **_: Mock())
    target = [{'host': 'same-native-account', 'pool_name': 'same', 'pool_size': 1, 'pool_reset_session': False}]
    first = connector.connect('user:7', failover=target); pool = first._pool; first.close()
    second = connector.connect('user:8', failover=target)
    assert second._pool is not pool and connector._native_connect.call_count == 2
    second.close(); connector.close()


def test_refusals_are_typed_and_do_not_return_drafts_or_sensitive_messages():
    error = VisualAdminValidationError('secret-canary', [{'field_id': 'authentication_mode',
        'code': 'protected_password_delivery_unavailable', 'message': 'secret-canary', 'value': 'secret-canary'}])
    value = response(error)
    assert value['status'] == 422 and value['data']['refusal']['native_dispatched'] is False
    assert value['data']['refusal']['errors'][0]['code'] == 'protected_password_delivery_unavailable'
    assert 'secret-canary' not in str(value)
    assert response(VisualAdminAccessError('stale', 'VISUAL_ADMIN_PLAN_STALE', 409))['status'] == 409


def test_contract_compaction_preserves_the_original_diagnostic_inventory_digest():
    path = Path(__file__).resolve().parents[2] / 'web/pgadmin/cdeadmin/providers/mysql_family/mysql_dialect_9_7_0.json'
    contract = json.loads(path.read_text())
    for kind, field, default in [('diagnostics', 'sqlstate', None), ('data_types', 'lexical_source', 'sql/lex.h'),
            ('statements', 'production', 'simple_statement')]:
        rows = [{**row, field: row.get(field, default)} for row in contract['inventories'][kind]]
        digest = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        assert digest == contract['source_inventory_reconciliation']['inventory_sha256'][kind]

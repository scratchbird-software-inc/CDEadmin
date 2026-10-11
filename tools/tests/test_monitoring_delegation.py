"""Encrypted, scope-bound background credentials never reuse browser leases."""

import base64
from dataclasses import replace
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tools.cdeadmin_firebird_admin_mapping_gate import _create_client  # noqa: F401
from pgadmin.cdeadmin.report_scheduler.crypto import WorkerKeyRing
from pgadmin.cdeadmin.security.secrets import SecretLease
from pgadmin.cdeadmin.workspace.monitoring import MonitoringPolicy
from pgadmin.cdeadmin.workspace.monitoring_delegation import (
    MonitoringGrant, MonitoringGrantError,
)


def setup_grant(**options):
    policy = MonitoringPolicy(1, 'endpoint', 'database')
    route = {'database': 'demo.fdb', 'host': 'localhost', 'port': 3050,
             'credential_reference_id': 'owner-reference',
             'principal_reference': 'owner:1'}
    keys = WorkerKeyRing({'key': base64.b64encode(os.urandom(32)).decode()}, 'key')
    leases = []

    def acquire(*_):
        lease = SecretLease('test-only-password')
        leases.append(lease)
        return lease

    permissions = SimpleNamespace(acquire_secret=Mock(side_effect=acquire))
    authorize = options.pop('authorize', Mock(return_value=True))
    grant = MonitoringGrant.issue(policy, route, 'generation', permissions,
                                  keys, authorize, **options)
    return grant, policy, permissions, leases, authorize


def test_capture_lease_is_closed_and_worker_uses_only_its_sealed_grant():
    grant, policy, permissions, leases, _ = setup_grant()
    assert all(lease.closed for lease in leases)
    assert 'test-only-password' not in str(grant._credentials)
    permissions.acquire_secret.side_effect = AssertionError('No browser in worker')
    factory = Mock(return_value=Mock())
    source = grant.open_source(policy, source_factory=factory)
    delegated, route = factory.call_args.args
    assert route['principal_reference'] != 'owner:1'
    with delegated.acquire_secret(route['credential_reference_id'],
                                  route['principal_reference'], 'connect',
                                  'database_password') as lease:
        assert lease.use(bytes) == b'test-only-password'
    assert lease.closed
    permissions.acquire_secret.assert_called_once()
    source.close()


@pytest.mark.parametrize('change', ['owner', 'target', 'generation', 'envelope'])
def test_scope_changes_or_envelope_tampering_cannot_reuse_credentials(change):
    grant, policy, _, _, _ = setup_grant()
    reference = next(iter(grant._credentials))
    if change == 'owner':
        grant.policy = replace(policy, owner_id=2)
    elif change == 'target':
        grant.policy = replace(policy, target_id='other')
    elif change == 'generation':
        grant.generation = 'other'
    else:
        grant._credentials[reference] = ('database_password', '{}')
    with pytest.raises(MonitoringGrantError):
        grant._acquire(reference, 'monitor:' + grant.id,
                       'connect', 'database_password')


def test_revocation_during_sample_discards_result_but_can_release_source():
    grant, policy, _, _, authorize = setup_grant()
    native = Mock()

    def sample():
        authorize.return_value = False
        return {'status': 'available', 'private': 'must-not-be-published'}

    native.sample.side_effect = sample
    source = grant.open_source(policy, source_factory=Mock(return_value=native))
    with pytest.raises(MonitoringGrantError):
        source.sample()
    source.close()
    native.close.assert_called_once()


def test_expiration_and_explicit_revocation_stop_reconnect():
    now = [0]
    grant, policy, _, _, _ = setup_grant(clock=lambda: now[0])
    now[0] = policy.lease_seconds
    with pytest.raises(MonitoringGrantError):
        grant.open_source(policy)
    now[0] = 0
    grant.revoke()
    assert grant._credentials == {}
    with pytest.raises(MonitoringGrantError):
        grant.open_source(policy)


def test_collection_does_not_grant_view_or_policy_change_rights():
    grant, policy, _, _, authorize = setup_grant()
    authorize.side_effect = lambda _, purpose, *args: purpose == 'collect'
    assert grant.require(policy, 'collect')
    for purpose in ('view', 'configure'):
        with pytest.raises(MonitoringGrantError):
            grant.require(policy, purpose)


def test_secret_cannot_be_acquired_for_another_principal_purpose_or_kind():
    grant, _, _, _, _ = setup_grant()
    reference = next(iter(grant._credentials))
    for principal, purpose, kind in (
            ('owner:1', 'connect', 'database_password'),
            ('monitor:' + grant.id, 'export', 'database_password'),
            ('monitor:' + grant.id, 'connect', 'other')):
        with pytest.raises(MonitoringGrantError):
            grant._acquire(reference, principal, purpose, kind)


def test_dedicated_account_is_sealed_without_accessing_registration_password():
    grant, policy, permissions, _, _ = setup_grant(credentials={
        'username': 'COLLECTOR', 'password': 'dedicated-secret', 'role': 'MONITOR'})
    permissions.acquire_secret.assert_not_called()
    factory = Mock(return_value=Mock())
    grant.open_source(policy, source_factory=factory)
    delegated, route = factory.call_args.args
    assert route['user'] == 'COLLECTOR'
    assert route['role'] == 'MONITOR'
    assert route['trusted_auth'] is False
    assert 'dedicated-secret' not in repr(grant.__dict__)
    with delegated.acquire_secret(route['credential_reference_id'],
                                  route['principal_reference'], 'connect',
                                  'database_password') as lease:
        assert lease.use(bytes) == b'dedicated-secret'
    grant.authentication['username'] = 'OTHER'
    with pytest.raises(MonitoringGrantError):
        delegated.acquire_secret(route['credential_reference_id'],
                                 route['principal_reference'], 'connect',
                                 'database_password')


@pytest.mark.parametrize('credentials', [
    {}, {'username': 'monitor'}, {'username': 'monitor', 'password': ''},
    {'username': 'monitor', 'password': 'secret', 'host': 'elsewhere'},
    {'username': 'monitor', 'password': 'secret', 'role': None},
    {'username': 'monitor', 'password': 'secret', 'role': 'x' * 256},
])
def test_invalid_dedicated_credentials_are_refused(credentials):
    with pytest.raises(ValueError):
        setup_grant(credentials=credentials)

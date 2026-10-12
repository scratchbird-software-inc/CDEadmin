"""Credential binding shared by owned MySQL qualification fixtures."""
from types import SimpleNamespace

from pgadmin.cdeadmin.security import SecretLease


def provider_access(route, password=None):
    request_route = dict(route)
    if password is None:
        return request_route, SimpleNamespace(acquire_secret=None)
    request_route.update(credential_reference_id='owned-gate-password',
                         principal_reference='owned-gate-principal')

    def acquire(reference, principal, purpose, kind):
        if (reference, principal, purpose, kind) != (
                'owned-gate-password', 'owned-gate-principal', 'connect',
                'database_password'):
            raise ValueError('Unexpected fixture credential request')
        return SecretLease(password.encode('utf8'))

    return request_route, SimpleNamespace(acquire_secret=acquire)

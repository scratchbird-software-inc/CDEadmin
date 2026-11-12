"""The endpoint service's route envelope.

The endpoint service and the servers API add bookkeeping to every provider
route beside the fields a registration contract declares: the selected
route's id, the generic host, port, user and database, the legacy
connection timeout, the database target it browses, and the credential
kinds and references it bound. Providers that validate their routes
strictly admit these keys without reading them (owner direction
2026-11-11: one registration path for every engine), so a registration
verified through the service reaches the provider exactly as a direct call
would.
"""
ROUTE_ENVELOPE_KEYS = frozenset({
    'route_id', 'host', 'port', 'user', 'database', 'database_target_id',
    'connection_timeout', 'credential_kind', 'credential_kinds',
    'credential_references', 'credential_reference_id',
    'principal_reference',
})


def unknown_route_keys(route, accepted):
    """Keys of ``route`` that neither the provider nor the envelope admit."""
    return sorted(set(route).difference(accepted).difference(
        ROUTE_ENVELOPE_KEYS))

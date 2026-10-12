"""Resolve the initial PostgreSQL database separately from server identity."""


def initial_database(server):
    """Prefer an explicit connection database, then one unambiguous target.

    Do not guess a database name or pick the first of multiple targets.
    Other providers must not inherit PostgreSQL connection semantics.
    """
    if server.maintenance_db:
        return server.maintenance_db
    endpoint = getattr(server, 'endpoint_profile', None)
    if endpoint is None or endpoint.profile_id != 'postgresql-native':
        return None
    targets = {
        target.database for target in endpoint.database_targets
        if target.active and target.database
    }
    return next(iter(targets)) if len(targets) == 1 else None


def database_oid(target):
    """Decode an explicit server-scoped target without guessing a database."""
    if target is None or target is Ellipsis:
        return None
    prefix = 'postgresql-database:'
    if not isinstance(target, str) or not target.startswith(prefix):
        raise ValueError('Invalid PostgreSQL database target')
    value = target[len(prefix):]
    if (not value.isascii() or not value.isdecimal() or
            not value or value.startswith('0') or len(value) > 10):
        raise ValueError('Invalid PostgreSQL database OID')
    result = int(value)
    if not 1 <= result <= 4294967295:
        raise ValueError('Invalid PostgreSQL database OID')
    return result

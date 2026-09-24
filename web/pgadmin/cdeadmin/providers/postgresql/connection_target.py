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

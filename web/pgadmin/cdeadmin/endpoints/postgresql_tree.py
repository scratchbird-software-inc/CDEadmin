"""Per-server choice: browse a PostgreSQL registration with the provider tree.

Owner decision, 2026-11-10 (M2, option 1): a PostgreSQL registration keeps
its preserved workflow (inherited Connect, driver, saved password and every
inherited tool) and can, per server, be browsed through the provider tree
instead of the inherited object tree. The choice is presentation only; it
never changes how the server connects. A survey the same day found that
registering PostgreSQL as a provider endpoint cannot verify today, so the
opt-in lives on the preserved registration.

The flag is kept in the endpoint's extension profile (the one free-form
per-endpoint slot, precedent: the MySQL recovery binding) under the key
below, so no schema change is needed and the flag is cleared with the
endpoint.
"""
import json
from datetime import datetime, timezone

PROVIDER_TREE_KEY = 'postgresql_provider_tree'
EXTENSION_SCHEMA = 'cdeadmin.endpoint.extensions.v1'


def _extension(server):
    endpoint = getattr(server, 'endpoint_profile', None)
    extension = getattr(endpoint, 'extension_profile', None)
    if extension is None or getattr(
            extension, 'schema_reference', None) != EXTENSION_SCHEMA:
        return None
    return extension


def _data(extension):
    try:
        data = json.loads(extension.profile_data or '{}')
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def is_preserved_postgresql(server):
    """Whether this registration is the preserved PostgreSQL workflow."""
    from .service import EndpointService
    return EndpointService._is_preserved_postgresql(server)


def provider_tree_enabled(server):
    """Whether the server is browsed through the provider tree."""
    extension = _extension(server)
    if extension is None:
        return False
    return _data(extension).get(PROVIDER_TREE_KEY) is True


def set_provider_tree(server, enabled):
    """Record the choice on the endpoint's extension profile.

    Returns the stored value. The caller commits the session. Raises
    ``ValueError`` when the registration is not preserved PostgreSQL or
    its extension profile holds another schema's data.
    """
    if not is_preserved_postgresql(server):
        raise ValueError(
            'Only a PostgreSQL registration can choose the provider tree')
    extension = _extension(server)
    if extension is None:
        raise ValueError(
            'This registration has no extension profile to record the '
            'choice in')
    data = _data(extension)
    if enabled:
        data[PROVIDER_TREE_KEY] = True
    else:
        data.pop(PROVIDER_TREE_KEY, None)
    extension.profile_data = json.dumps(
        data, sort_keys=True, separators=(',', ':'))
    return bool(enabled)


INHERITED_CONNECT_EVIDENCE = 'postgresql-inherited-connect'


def record_inherited_connect(server, native_version, session):
    """Record the runtime the inherited Connect observed.

    Under the owner's option 1 (2026-11-10) endpoint verification for a
    PostgreSQL registration is the inherited Connect, so the version
    gates that read the endpoint's verified runtime (the provider tree's
    node fields and descriptor gates) must learn the version here. The
    version is rendered as PostgreSQL's public ``major.minor``; the
    survey's B6 finding (the provider reports ``engine``/``server_version``
    while verification records ``engine_id``/``version``) is sidestepped
    by writing the identity directly. Returns the recorded version, or
    ``None`` when the registration is not preserved PostgreSQL or has no
    runtime identity. ``session`` is committed by this function.
    """
    from pgadmin.cdeadmin.providers.postgresql.support_policy import (
        public_version,
    )
    if not is_preserved_postgresql(server):
        return None
    runtime = getattr(getattr(server, 'endpoint_profile', None),
                      'runtime_identity', None)
    if runtime is None:
        return None
    version = public_version(native_version)
    runtime.verified_runtime_family = 'postgresql'
    runtime.verified_runtime_version = version
    runtime.verification_state = 'verified'
    runtime.verification_evidence_reference = INHERITED_CONNECT_EVIDENCE
    runtime.verified_at = datetime.now(timezone.utc).replace(tzinfo=None)
    session.commit()
    return version

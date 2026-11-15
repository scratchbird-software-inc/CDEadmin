"""Committed-catalog completion without commands on the retained session."""
from copy import deepcopy
import hashlib
import json

from ...sdk.relational import RelationalClientError

IDENTITY_SQL = 'SELECT @@server_uid,CURRENT_USER(),VERSION(),CONNECTION_ID()'


def identity(handle):
    cursor = handle.cursor()
    try:
        cursor.execute(IDENTITY_SQL)
        row = cursor.fetchone()
        if (not row or len(row) != 4 or not all(row[:3])
                or type(row[3]) is not int or row[3] != handle.connection_id):
            raise RelationalClientError('MariaDB editor identity is unavailable')
        return tuple(row)
    finally:
        cursor.close()


def admit(client, handle):
    """Capture native identity before returning a new session to its caller."""
    try:
        observed = identity(handle)
    except Exception:
        raise RelationalClientError('MariaDB editor identity admission failed') from None
    client._completion_identities[id(handle)] = (handle, observed)


def complete(client, handle):
    from ..native_editor import metadata
    from .mariadb_connections import POOL_ARGUMENTS

    peer = None
    try:
        # The caller holds session_access: no concurrent user command or close.
        client._executions.sessions.get(handle)
        entry = client._completion_identities.get(id(handle))
        if entry is None or entry[0] is not handle or handle.connection_id != entry[1][3]:
            raise RelationalClientError('MariaDB source identity is unconfirmed')
        request = deepcopy(client._session_requests[id(handle)])
        for key in POOL_ARGUMENTS:
            request['route'].pop(key, None)
        request['route']['reconnect'] = False
        peer = client._connect(request)
        if peer is handle or peer.connection_id == entry[1][3]:
            peer = None  # Never release a source handle returned by a broken connector.
            raise RelationalClientError('MariaDB completion requires a private connection')
        observed = identity(peer)
        if observed[:3] != entry[1][:3] or observed[3] == entry[1][3]:
            raise RelationalClientError('MariaDB private catalog identity changed')
        result = metadata(peer, 'mariadb')
        context = result['context']
        if context.get('version') != observed[2]:
            raise RelationalClientError('MariaDB private catalog version changed')
        # Peer settings are not observations of the caller's active context.
        context['metadata_peer_context'] = {key: context.pop(key) for key in (
            'default_schema', 'sql_mode', 'character_set_client', 'active_role')
            if key in context}
        context['original_session_context_observed'] = False
        result['observations'].append({
            'section': 'retained-session-overlays', 'available': False,
            'reason': 'source-role-settings-temporary-and-uncommitted-catalog-unobserved'})
        result.update(complete=False, observation_source='private-native-peer',
            original_session_commands_sent=0, original_diagnostics_preserved=True,
            original_session_catalog_binding_validated=False,
            original_active_roles_observed=False, original_temporary_objects_observed=False,
            coverage='Committed catalog on a separate same-server authenticated connection. '
                     'Source role, settings, temporary objects and uncommitted DDL are unobserved.')
        context.pop('context_revision', None)
        context['context_revision'] = hashlib.sha256(json.dumps({
            'context': context, 'resources': result['resources'],
            'observations': result['observations'],
            'visible_resource_count': result['visible_resource_count']},
            sort_keys=True, default=str).encode()).hexdigest()
        return result
    except Exception:
        error = RelationalClientError('Private MariaDB completion is unavailable; '
            'no original-session metadata command was substituted')
        error.original_session_commands_sent = 0
        error.original_diagnostics_preserved = True
        raise error from None
    finally:
        if peer is not None:
            try:
                released = client._close_idle_session(peer)
                if not released.get('connection_released'):
                    raise RelationalClientError('Private completion release is unconfirmed')
            except Exception:
                error = RelationalClientError('Private MariaDB completion release is unconfirmed; '
                    'the original session was not used for metadata')
                error.original_session_commands_sent = 0
                error.original_diagnostics_preserved = True
                raise error from None

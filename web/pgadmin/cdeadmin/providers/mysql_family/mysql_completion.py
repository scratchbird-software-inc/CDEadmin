"""Independent committed-catalog completion without clearing source diagnostics."""
import hashlib
import json

from ...sdk.relational import RelationalClientError
from .mysql_session_variables import SessionVariables, SourceIdentityUnavailable, prepare


def complete(client, handle):
    from ..native_editor import metadata
    observer = getattr(handle, '_cdeadmin_session_variable_observer', None)
    if not isinstance(observer, SessionVariables):
        result = metadata(handle, 'mysql')
        result.update(original_diagnostics_preservation_qualified=False,
            observation_profile=getattr(handle, '_cdeadmin_session_variable_observer_status', {'admitted': False}))
        return result
    try:
        prepare(handle)
        with observer.parser_session() as (peer, observation):
            result = metadata(peer, 'mysql')
            context = result['context']
            if context['version'] != observation['version'] or context['sql_mode'] != observation['variables']['sql_mode']:
                raise RelationalClientError('The private completion language identity changed')
            context.update(character_set_client=observation['variables']['character_set_client'],
                metadata_peer_active_role=context.pop('active_role'), active_role=None,
                original_active_roles_observed=False, original_temporary_objects_observed=False)
            result['observations'].append({'section': 'retained-session-overlays', 'available': False,
                'reason': 'original-active-roles-and-temporary-objects-unobserved'})
            result.update(complete=False, original_diagnostics_preservation_qualified=True,
                original_diagnostics_preserved=True, original_session_commands_sent=0,
                original_session_catalog_binding_validated=False,
                metadata_observation={**observation, 'thread_id': str(observation['thread_id']),
                    'connection_id': str(observation['connection_id'])},
                coverage='Committed native catalog on a private same-instance authenticated peer. Source database, SQL mode and client charset are independently observed. Original active-role and temporary-object overlays are unconfirmed.')
            context.pop('context_revision', None)
            context['context_revision'] = hashlib.sha256(json.dumps({'context': context,
                'resources': result['resources'], 'observations': result['observations'],
                'visible_resource_count': result['visible_resource_count']}, sort_keys=True, default=str).encode()).hexdigest()
            return result
    except SourceIdentityUnavailable:
        client._uncertain_sessions.add(id(handle))
        raise RelationalClientError('The original MySQL session identity is unconfirmed; close this session') from None
    except Exception:
        raise RelationalClientError('Private MySQL completion is unavailable; no original-session metadata command was substituted') from None

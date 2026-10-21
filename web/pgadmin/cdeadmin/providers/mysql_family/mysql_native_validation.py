"""Same-server native syntax checking without querying the user's session."""
from ...sdk.relational import RelationalClientError
from .mysql_session_variables import SessionVariables, SourceIdentityUnavailable, prepare


def validate(client, handle, source, script=False):
    from ..native_editor import validate_mysql
    observer = getattr(handle, '_cdeadmin_session_variable_observer', None)
    if not isinstance(observer, SessionVariables):
        result = validate_mysql(client, handle, source, 'mysql', script)
        profile = getattr(handle, '_cdeadmin_session_variable_observer_status', None)
        result.update(original_diagnostics_preservation_qualified=False,
            observation_profile=profile if isinstance(profile, dict) else {'admitted': False})
        return result
    peer = None
    try:
        prepare(handle)  # Authenticated request path, including credential renewal.
        with observer.parser_session() as (peer, observation):
            result = validate_mysql(client, peer, source, 'mysql', script)
            if result['parser_version'] != observation['version'] or result['sql_mode'] != observation['variables']['sql_mode']:
                raise RelationalClientError('The private MySQL parser language identity changed')
            result.update(authority='mysql-native-independent-prepare',
                scope='Native nonexecuting preparation on a private authenticated session of the same MySQL instance. Original-session catalog binding is reported separately.',
                original_diagnostics_preservation_qualified=True, original_session_commands_sent=0,
                original_diagnostics_preserved=True, original_session_catalog_binding_validated=False,
                external_language_bodies_parsed=False,
                parser_observation={**observation, 'thread_id': str(observation['thread_id']),
                    'connection_id': str(observation['connection_id'])},
                script_ready=bool(script and result.get('grammar_valid') is True))
            return result
    except Exception as error:
        if isinstance(error, SourceIdentityUnavailable):
            client._uncertain_sessions.add(id(handle))
            raise RelationalClientError('The original MySQL session identity is unconfirmed; close this session') from None
        raise RelationalClientError('Private MySQL syntax validation is unavailable; no original-session metadata command was substituted') from None
    finally:
        if peer is not None:
            client._uncertain_sessions.discard(id(peer))

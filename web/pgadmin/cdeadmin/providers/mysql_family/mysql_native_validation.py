"""Same-server native syntax checking without querying the user's session."""
from ...sdk.relational import RelationalClientError
from .mysql_session_variables import SourceIdentityUnavailable, prepare, editor_observer


class ModeCanonicalizer:
    """Fixed, bound settings queries on the owned private observer only."""
    def __init__(self, observer):
        self.observer=observer;self.used=False

    def read(self, sql, parameters=()):
        cursor=self.observer.connection.cursor()
        try:
            cursor.execute(sql,parameters or None)
            value=cursor.fetchone()[0]
            if isinstance(value,bytes):value=value.decode('ascii')
            if not isinstance(value,str) or len(value)>4096:raise ValueError('Native SQL mode is unavailable')
            return value
        finally:cursor.close()

    def __call__(self, value):
        if not isinstance(value,(str,int)) or type(value) is bool or isinstance(value,str) and len(value)>4096:
            raise ValueError('A bounded deterministic SQL mode value is required')
        self.used=True;self.observer.escaping_context=None
        cursor=self.observer.connection.cursor()
        try:cursor.execute('SET SESSION sql_mode=%s',(value,))
        finally:cursor.close()
        mode=self.read('SELECT @@SESSION.sql_mode')
        self.observer.connection._sql_mode=mode
        return mode

    def default_mode(self):
        return self.read('SELECT @@GLOBAL.sql_mode')


def validate(client, handle, source, script=False):
    from ..native_editor import validate_mysql
    observer = editor_observer(client, handle)
    peer = None
    try:
        prepare(handle)  # Authenticated request path, including credential renewal.
        from . import mysql_parser
        grammar = mysql_parser.library(client)
        if grammar is not None:
            try:
                with observer.lock:
                    observer.cached = None
                    observation = observer.observe()
            except BaseException:
                observer.needs_connection_refresh = True
                try: observer.close()
                except Exception: pass
                raise
            if not script:return mysql_parser.validate(grammar, source, observation, False)
            with observer.lock:
                canonicalize=ModeCanonicalizer(observer)
                try:return mysql_parser.validate(grammar,source,observation,True,canonicalize)
                finally:
                    if canonicalize.used:
                        observer.escaping_context=None
                        try:observer.connection.sql_mode=observation['variables']['sql_mode']
                        except Exception:
                            observer.needs_connection_refresh=True
                            try:observer.close()
                            except Exception:pass
                            raise RelationalClientError('Private MySQL mode restoration is unconfirmed; no original-session setting was changed') from None
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

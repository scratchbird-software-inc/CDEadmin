"""Owned database attachment with independent UTF8 parameter block text."""
import re

from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from .attachment_dpb import build


CONFIG_FIELDS = (
    'trusted_auth', 'timeout', 'cache_size', 'no_linger',
    'dummy_packet_interval', 'config', 'set_bind', 'decfloat_round',
    'decfloat_traps', 'parallel_workers',
)


def connect(module, core, *, database, failed_owner, user=None, password=None,
            role=None, no_gc=None, no_db_triggers=None, dbkey_scope=None,
            crypt_callback=None, charset=None, auth_plugin_list=None,
            session_time_zone=None):
    if not isinstance(database, str) or not re.fullmatch(
            r'cde_database_[0-9a-f]{24}', database):
        raise RelationalClientError(
            'Firebird attachment configuration invalid')
    config = module.driver_config.get_database(database)
    if config is None:
        raise RelationalClientError(
            'Firebird attachment configuration missing')
    server = module.driver_config.get_server(config.server.value)
    if server is None:
        raise RelationalClientError(
            'Firebird private server configuration missing')

    def resolved(value, name, fallback=None):
        if value is not None:
            return value
        value = getattr(config, name).value
        return fallback if value is None else value

    charset = resolved(charset, 'charset')
    if charset:
        charset = charset.upper()
    dsn = core._connect_helper(
        config.dsn.value, server.host.value, server.port.value,
        config.database.value, config.protocol.value)
    options = {name: getattr(config, name).value for name in CONFIG_FIELDS}
    options.update(
        user=resolved(user, 'user', server.user.value),
        password=resolved(password, 'password', server.password.value),
        role=resolved(role, 'role'), charset=charset, utf8filename=True,
        auth_plugin_list=resolved(auth_plugin_list, 'auth_plugin_list'),
        session_time_zone=resolved(session_time_zone, 'session_time_zone'),
        sql_dialect=config.sql_dialect.value, no_gc=no_gc,
        no_db_triggers=no_db_triggers, dbkey_scope=dbkey_scope)
    buffer = build(core, options)
    for callback in core.get_callbacks(
            core.ConnectionHook.ATTACH_REQUEST, core.Connection):
        connection = callback(dsn, buffer)
        if connection is not None:
            connection._cdeadmin_attached_pending = True
            return connection
    # Allocate an owner before acquiring the native interface. If the Python
    # constructor fails, the client retains even a failed detach for retry.
    connection = core.Connection.__new__(core.Connection)
    connection._att = None
    try:
        with module.get_api().master.get_dispatcher() as dispatcher:
            if crypt_callback is not None:
                dispatcher.set_dbcrypt_callback(crypt_callback)
            connection._att = dispatcher.attach_database(dsn, buffer, 'utf-8')
            core.Connection.__init__(connection, connection._att, dsn, buffer,
                                     config.sql_dialect.value, charset)
        connection._cdeadmin_attached_pending = True
        return connection
    except BaseException:
        if connection._att is not None:
            failed_owner(connection)
        raise


def notify_attached(core, connection):
    if getattr(connection, '_cdeadmin_attached_pending', False) is not True:
        return
    connection._cdeadmin_attached_pending = False
    for callback in core.get_callbacks(
            core.ConnectionHook.ATTACHED, connection):
        callback(connection)

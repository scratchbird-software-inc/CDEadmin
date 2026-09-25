"""Provider-owned Unicode Firebird Services API attachments.

Firebird 5's dispatcher uses isc_spb_utf8_filename to distinguish UTF-8
attachment/start text from client-local encoding (why.cpp, IntlSpb). The
installed driver exposes the native builder and Server, but its connect_server
does not emit that marker. Do not patch driver globals or its installation.
"""

from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def security_context(value):
    """An ordinary database's configuration selects its security store.

    Linux qualified; Windows/macOS teams must repeat path/alias/Unicode and
    environment-isolation checks with their native clients. This is not the
    security database filename and does not change the operation target.
    """
    if value is None:
        return None
    if not isinstance(value, str) or any(ord(char) < 32 for char in value):
        raise RelationalClientError(
            'Firebird service authentication database must be text '
            'without control characters')
    return value.strip() or None


def validate_service_role(role):
    """Reject roles that native service argv construction cannot preserve."""
    if role is not None:
        if not isinstance(role, str) or any(ord(char) <= 32 for char in role):
            # Service::start concatenates this attachment value into utility
            # switches; parseSwitches does not recognize shell/SQL quoting.
            # Do not let a role become another utility argument or silently
            # change a delimited role name. SQL database roles are unaffected.
            raise RelationalClientError(
                'Firebird service role transport cannot safely preserve '
                'whitespace or control characters in a role name')
    return role


def effective_service_role(task_role, default_role=None):
    """Resolve a task override without mutating the saved endpoint role."""
    if task_role is not None and (
            not isinstance(task_role, str) or '\x00' in task_role):
        raise RelationalClientError('Firebird service role is invalid')
    validate_service_role(task_role)
    role = task_role or default_role
    if role is not None and (not isinstance(role, str) or '\x00' in role):
        raise RelationalClientError('Firebird service role is invalid')
    validate_service_role(role)
    return role or None


def service_authentication(route, options):
    """Describe a requested identity scope, never infer native permission.

    Linux qualification covers native service attachment transport. Windows
    and macOS must repeat role/Unicode/denial tests with their client runtimes.
    The database task target is intentionally not an authentication DB default.
    """
    role = effective_service_role(options.get('role'), route.get('role'))
    return {
        'requested_role': role,
        'role_source': ('task' if options.get('role') else
                        'connection' if role else 'none'),
        'authentication_database': security_context(
            route.get('service_expected_database')),
        'role_transport': 'service_attachment',
        'authorization_verified': False,
        'authorization_authority': 'native_service_action',
        'saved_profile_modified': False,
    }


def connect_service(module, core, *, server, user=None, password=None,
                    expected_db=None, role=None, crypt_callback=None,
                    connect_timeout=None):
    if connect_timeout is not None and (
            type(connect_timeout) is not int or
            not 0 <= connect_timeout <= 2147483647):
        raise RelationalClientError(
            'Firebird connection timeout must be a non-negative integer')
    validate_service_role(role)
    expected_db = security_context(expected_db)
    config = module.driver_config.get_server(server)
    if config is None:
        raise RelationalClientError(
            'Firebird service configuration is missing')
    host = config.host.value
    if not isinstance(host, str) or not host.endswith('service_mgr'):
        raise RelationalClientError('Firebird service address is invalid')
    api = module.get_api()
    # Always use UTF-8/strict for native service text, independently of a
    # database SQL attachment's character set. Secrets remain leased only.
    buffer = core.SPB_ATTACH(
        user=user if user is not None else config.user.value,
        password=password, trusted_auth=config.trusted_auth.value,
        config=config.config.value,
        auth_plugin_list=config.auth_plugin_list.value,
        # Explicit empty SPB prevents yvalve setLogin() from importing an
        # unrelated process-wide FB_EXPECTED_DB. Never mutate os.environ:
        # concurrent routes must retain independent authentication contexts.
        expected_db=expected_db or '', role=role,
        encoding='utf-8', errors='strict',
    ).get_buffer()
    with api.util.get_xpb_builder(core.XpbKind.SPB_ATTACH, buffer) as builder:
        builder.insert_tag(core.SPBItem.UTF8_FILENAME)
        if connect_timeout is not None:
            # Native REMOTE_get_timeout_params reads isc_spb_connect_timeout.
            # Linux qualified; Windows/macOS repeat stalled-handshake tests.
            builder.insert_int(core.SPBItem.CONNECT_TIMEOUT, connect_timeout)
        buffer = builder.get_buffer()
    # Allocate the Python owner before obtaining the native attachment.
    # Publish driver ATTACHED hooks only after the client records ownership.
    connection = core.Server(None, buffer, host, 'utf-8', 'strict')
    with api.master.get_dispatcher() as dispatcher:
        if crypt_callback is not None:
            dispatcher.set_dbcrypt_callback(crypt_callback)
        connection._svc = dispatcher.attach_service_manager(host, buffer)
    return connection


def notify_attached(core, connection):
    for callback in core.get_callbacks(core.ServerHook.ATTACHED, connection):
        callback(connection)

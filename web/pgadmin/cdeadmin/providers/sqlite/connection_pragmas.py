"""Typed native connection flags; never independent-file PRAGMA assignments."""
from ...sdk import RelationalClientError
from .connection_tuning import NAMES as NUMERIC_NAMES
from .schema_settings import SPECS as SCHEMA_SETTINGS, CONNECTION_NAMES
from .heap_settings import NAMES as HEAP_NAMES

FLAGS = (
    'full_column_names',
    'short_column_names',
    'count_changes',
    'empty_result_callbacks',
    'fullfsync',
    'checkpoint_fullfsync',
    'defer_foreign_keys',

    'foreign_keys',
    'cell_size_check',
    'legacy_alter_table',
    'trusted_schema',
    'ignore_check_constraints',
    'automatic_index',
    'reverse_unordered_selects',
    'read_uncommitted',
    'recursive_triggers',
    'query_only',
)


DEBUG_FLAGS = ('sql_trace','vdbe_listing','vdbe_trace','vdbe_addoptrace','vdbe_debug','vdbe_eqp','parser_trace')

CONTROL_NAMES = FLAGS + DEBUG_FLAGS + NUMERIC_NAMES + ('case_sensitive_like','temp_store_directory','data_store_directory','lock_proxy_file') + CONNECTION_NAMES + HEAP_NAMES

def action(connection, request, *, native_work_revision=None, host_authorized=False, startup_policy_file=None, filesystem_root=None, principal=None, endpoint_id=None):
    if not isinstance(request, dict):
        raise RelationalClientError('Select a typed original-connection PRAGMA')
    if request.get('pragma') == 'lock_proxy_file':
        from .lock_proxy import action as proxy_action
        return proxy_action(connection,request,native_work_revision=native_work_revision,filesystem_root=filesystem_root)
    from .startup_policy import NAMES as STARTUP_NAMES
    if (isinstance(request.get('pragma'),str) and request['pragma'] in STARTUP_NAMES and
            request.get('operation') in {'inspect','review','set_connection_pragma'}):
        from .startup_policy import action as startup_action
        return startup_action(connection,request,native_work_revision=native_work_revision,
            host_authorized=host_authorized,filename=startup_policy_file,filesystem_root=filesystem_root,principal=principal,endpoint_id=endpoint_id)
    if isinstance(request.get('pragma'),str) and request['pragma'] in HEAP_NAMES:
        from .heap_settings import action as heap_action
        return heap_action(connection,request)
    if isinstance(request.get('pragma'),str) and request['pragma'] in SCHEMA_SETTINGS:
        from .schema_settings import action as schema_action
        return schema_action(connection,request,native_work_revision=native_work_revision)
    if request.get('pragma') == 'case_sensitive_like':
        from .like_policy import action as like_action
        return like_action(connection,request,native_work_revision)
    if request.get('operation') == 'pragma_inspection_capabilities':
        from .pragma_inspection import capabilities
        return capabilities(request)
    if request.get('operation') == 'inspect_pragma_value':
        from .pragma_inspection import inspect
        return inspect(connection,request)
    if isinstance(request.get('pragma'), str) and request['pragma'] in NUMERIC_NAMES:
        from .connection_tuning import action as numeric_action
        return numeric_action(connection, request)
    operation = request.get('operation')
    allowed = {
        'inspect': {'operation', 'pragma'},
        'review': {'operation', 'pragma', 'value'},
        'set_connection_pragma': {'operation', 'pragma', 'value', 'expected_value', 'confirmed'},
    }
    name = request.get('pragma')
    debugging = isinstance(name,str) and name in DEBUG_FLAGS
    if debugging:
        allowed['set_connection_pragma'] |= {'sensitive_output_confirmed'}
    if not isinstance(operation, str) or operation not in allowed or set(request) - allowed[operation]:
        raise RelationalClientError('Select an admitted connection PRAGMA operation')
    name = request.get('pragma')
    if not isinstance(name, str) or name not in FLAGS + DEBUG_FLAGS:
        raise RelationalClientError('Connection PRAGMA is not admitted')
    if operation != 'inspect' and type(request.get('value')) is not bool:
        raise RelationalClientError('Connection PRAGMA value must be boolean')
    if operation == 'set_connection_pragma':
        if request.get('confirmed') is not True:
            raise RelationalClientError('Confirm the original connection PRAGMA change')
        if type(request.get('expected_value')) is not bool:
            raise RelationalClientError('Refresh the original native PRAGMA value')
    if debugging and operation == 'set_connection_pragma' and request.get('value') is True and request.get('sensitive_output_confirmed') is not True:
        raise RelationalClientError('Confirm potentially sensitive SQL/value output to application-host diagnostics')
    cursor = connection.cursor()
    try:
        if debugging:
            options={row[0] for row in cursor.execute('PRAGMA compile_options').fetchall()}
            names={row[0] for row in cursor.execute('PRAGMA pragma_list').fetchall()}
            if 'DEBUG' not in options or name not in names:
                raise RelationalClientError('This debug flag requires an actual SQLITE_DEBUG native build and PRAGMA entry')
        def read():
            row = cursor.execute('PRAGMA ' + name).fetchone()
            if not row or type(row[0]) is not int or row[0] not in (0, 1):
                raise RelationalClientError('Native PRAGMA unavailable or unrecognized on this runtime/build')
            return bool(row[0])
        try:
            before = read()
        except Exception as error:
            failure = RelationalClientError('Native PRAGMA observation unavailable or refused; setter not dispatched')
            failure.native_outcome = 'not_dispatched'
            raise failure from error
        ready = not (name == 'foreign_keys' and connection.in_transaction)
        statement = 'PRAGMA ' + name + '=' + ('ON' if request.get('value') else 'OFF')
        if operation == 'set_connection_pragma':
            if before != request['expected_value']:
                raise RelationalClientError('Original PRAGMA changed; inspect and review again')
            if not ready:
                raise RelationalClientError('End the caller transaction before changing foreign_keys')
            try:
                cursor.execute(statement)
                after = read()
            except Exception as error:
                failure = RelationalClientError('Native PRAGMA outcome is unconfirmed; inspect before retrying')
                failure.native_outcome = 'unknown_outcome'
                raise failure from error
            if after != request['value']:
                failure = RelationalClientError('Native PRAGMA postcondition is unconfirmed; inspect before retrying')
                failure.native_outcome = 'unknown_outcome'
                raise failure
        else:
            after = before
        result = {
            'pragma': name, 'scope': 'original-connection', 'before_value': before,
            'effective_value': after, 'transaction_open': connection.in_transaction,
            'file_persisted': False, 'future_connection_defaults_changed': False,
            'commit_requested': False, 'rollback_requested': False, 'automatic_retry': False,
            'reset_on_transaction_end': name == 'defer_foreign_keys',
        }
        if operation != 'inspect':
            result.update(requested_value=request['value'], expected_value=before, native_statement=statement)
        if operation == 'review':
            result.update(ready_to_apply=ready,
                warning=('SQLite resets defer_foreign_keys at full COMMIT or ROLLBACK.' if name == 'defer_foreign_keys' else 'Connection state is not restored by rollback; native flag semantics and build support apply.'))
        if debugging:
            result.update(debug_build_only=True,sensitive_host_output_possible=True,
                warning='Native debug output can contain SQL and values in application-host diagnostics. vdbe_debug changes several VDBE flags together. No trace/progress/authorizer hook is replaced or restored; rollback does not restore flags.')
        if operation == 'set_connection_pragma':
            result['outcome'] = 'applied'
        return result
    finally:
        cursor.close()

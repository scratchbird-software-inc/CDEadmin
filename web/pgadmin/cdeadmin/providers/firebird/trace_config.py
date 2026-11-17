"""Database-bound native user-trace configuration, distinct from system audit."""
from collections.abc import Mapping

BOOLEAN_OPTIONS = frozenset({
    'log_connections', 'log_transactions', 'log_statement_prepare',
    'log_statement_free', 'log_statement_start', 'log_statement_finish',
    'log_procedure_compile', 'log_procedure_start', 'log_procedure_finish',
    'log_function_compile', 'log_function_start', 'log_function_finish',
    'log_trigger_compile', 'log_trigger_start', 'log_trigger_finish',
    'log_context', 'log_errors', 'log_warnings', 'log_initfini', 'log_sweep',
    'print_plan', 'explain_plan', 'print_perf', 'log_blr_requests', 'print_blr',
    'log_dyn_requests', 'print_dyn',
})
INTEGER_OPTIONS = {
    'connection_id': (0, 4294967295), 'time_threshold': (0, 4294967295),
    'max_sql_length': (0, 4294967295), 'max_blr_length': (0, 4294967295),
    'max_dyn_length': (0, 4294967295), 'max_arg_length': (0, 4294967295),
    'max_arg_count': (0, 4294967295),
}
FILTER_OPTIONS = frozenset({'include_filter', 'exclude_filter',
                           'include_gds_codes', 'exclude_gds_codes'})
SAFE_FLAGS = frozenset({'log_connections', 'log_transactions', 'log_initfini',
                        'log_sweep', 'print_perf'})
DEFAULTS = {'log_connections': True, 'log_initfini': True,
            'max_sql_length': 256, 'max_arg_length': 64, 'max_arg_count': 8,
            'max_blr_length': 256, 'max_dyn_length': 256,
            'time_threshold': 0}


def descriptor():
    fields = [{'field_id': key, 'control': 'checkbox', 'default': DEFAULTS.get(key, False)}
              for key in sorted(BOOLEAN_OPTIONS)]
    fields += [{'field_id': key, 'control': 'number', 'minimum': bounds[0],
                'maximum': bounds[1], 'default': DEFAULTS.get(key, 0),
                'zero_semantics': ('no attachment filter' if key == 'connection_id' else
                                   'no duration threshold' if key == 'time_threshold' else 'native unlimited')}
               for key, bounds in sorted(INTEGER_OPTIONS.items())]
    fields += [{'field_id': key, 'control': 'text', 'maximum_utf8_bytes': 4096, 'default': ''}
               for key in sorted(FILTER_OPTIONS)]
    fields.append({'field_id': 'capture_sensitive', 'control': 'checkbox', 'default': False})
    return {'schema': 'scratchrobin.firebird.trace-api@1', 'engine_version': '5.0.4',
            'scope': 'managed user trace of one verified database filename and registered attachment selector',
            'workspace_action': 'firebird_trace', 'option_fields': fields,
            'actions': ['describe', 'review', 'apply', 'get', 'list', 'poll'],
            'review_operations': ['start', 'suspend', 'resume', 'stop', 'release', 'forget'],
            'review_expiry_seconds': 300, 'captured_output_persisted': False,
            'native_scope_is_filename_not_permanent_inode_lock': True,
            'system_audit_and_service_capture': 'not implemented in this database-scoped workflow',
            'configuration_text_restrictions': ['double quotes', 'control characters', 'configuration macros']}


def text(value, maximum=4096):
    if (not isinstance(value, str) or len(value.encode('utf-8')) > maximum
            or any(ord(char) < 32 for char in value) or '"' in value):
        raise ValueError(
            'Native trace configuration text cannot contain double quotes or control characters')
    # Native configuration macro expansion must never reinterpret input.
    if '$(' in value:
        raise ValueError('Native configuration macros are not admitted in trace text')
    return value


def normalize(options):
    if not isinstance(options, Mapping) or set(options) - (
            BOOLEAN_OPTIONS | INTEGER_OPTIONS.keys() | FILTER_OPTIONS | {'capture_sensitive'}):
        raise ValueError('Unknown native trace option')
    result = {**DEFAULTS, **options}
    sensitive = result.pop('capture_sensitive', False)
    if type(sensitive) is not bool:
        raise ValueError('Sensitive capture approval must be boolean')
    for key, value in result.items():
        if key in BOOLEAN_OPTIONS and type(value) is not bool:
            raise ValueError('Native trace switches must be boolean')
        if key in INTEGER_OPTIONS:
            minimum, maximum = INTEGER_OPTIONS[key]
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError('Native trace integer is outside its declared bound')
        if key in FILTER_OPTIONS:
            text(value)
    if not sensitive and (any(result.get(key) for key in BOOLEAN_OPTIONS - SAFE_FLAGS)
                          or any(result.get(key) for key in FILTER_OPTIONS)):
        raise ValueError(
            'Explicit sensitive-capture approval is required for SQL, plans, arguments or filters')
    return {**result, 'capture_sensitive': sensitive}


def render(database, options, attachment_names=()):
    database = text(database)
    if not database:
        raise ValueError('Trace requires the observed native database filename')
    options = normalize(options)
    # Firebird SIMILAR TO, not Python/PCRE. Wrapping prevents the engine's
    # preliminary filename/alias comparison from treating this as a path.
    special = set('\\^-_%[](){}|?+*')
    if not isinstance(attachment_names, (list, tuple)) or len(attachment_names) > 2:
        raise ValueError('Trace attachment selectors must be supplied by verified backend scope')
    selectors = sorted({database, *(text(value) for value in attachment_names)})
    if any(not value for value in selectors):
        raise ValueError('Empty native trace attachment selector')
    pattern = '(' + '|'.join(''.join(('\\' if char in special else '') + char
                                     for char in value) for value in selectors) + ')'
    # Braces are escaped separately for the native configuration parser.
    pattern = pattern.replace('{', '{{').replace('}', '}}')
    lines = ['database', '{', 'enabled = false', '}', 'services', '{',
             'enabled = false', '}', 'database = "' + pattern + '"', '{', 'enabled = true']
    for key, value in sorted(options.items()):
        if key == 'capture_sensitive':
            continue
        if key in FILTER_OPTIONS:
            value = '"' + value.replace('{', '{{').replace('}', '}}') + '"'
        elif type(value) is bool:
            value = str(value).lower()
        lines.append(key + ' = ' + str(value))
    return '\n'.join([*lines, '}', ''])


def observe_scope(client, route):
    """Observe the server-native filename, including network alias resolution."""
    from .metadata_guard import observe
    selected = {'resource_kind': 'database', 'path': [route['database']]}
    probe = {**route, 'transaction_access': 'READ', 'transaction_isolation': 'SNAPSHOT',
             'transaction_auto_commit': False, 'transaction_no_auto_undo': False,
             'transaction_ignore_limbo': False, 'transaction_lock_timeout': 0}
    with client._temporary_operation():
        connection = client._connect({'route': probe})
        try:
            binding = observe(connection, selected)
            cursor = connection.cursor()
            try:
                cursor.execute(
                    "SELECT MON$DATABASE_NAME, RDB$GET_CONTEXT('SYSTEM','ENGINE_VERSION') FROM MON$DATABASE")
                database, version = cursor.fetchone()
            finally:
                cursor.close()
            if version != '5.0.4':
                raise ValueError('Native trace configuration is qualified for Firebird 5.0.4 only')
            # TraceInitInfo uses att_filename (the attachment alias when one
            # was used), whereas MON$DATABASE reports the physical filename.
            # This alias comes from the server-owned route whose connection
            # just supplied the same native GUID/file identity, not a browser
            # trace pattern. Other aliases are not guessed or enumerated.
            names = sorted({database, text(route['database'])})
            render(database, {}, names)
            result = {'database': database, 'version': version, 'attachment_names': names,
                      'native_identity': {'guid': binding['database_guid'],
                                          'file_id': binding['database_file_id']}}
            if route.get('attachment_mode') == 'embedded':
                import sys
                from .local_services import file_identity
                identity = file_identity(route)
                result['local_file_identity'] = identity
                if sys.platform == 'linux':
                    expected = (int(identity['device']).to_bytes(8, sys.byteorder) +
                                int(identity['inode']).to_bytes(8, sys.byteorder)).hex()
                    if binding['database_file_id'].lower() != expected:
                        raise ValueError(
                            'Native cached attachment differs from the approved filesystem target')
            return result
        finally:
            client._forget_and_close(connection)

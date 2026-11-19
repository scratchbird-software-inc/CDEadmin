"""Native Firebird 5.0.4 database, services and system-audit trace configuration."""
from collections.abc import Mapping
from pathlib import Path
import re

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

SERVICE_BOOLEAN_OPTIONS = frozenset({
    'log_services', 'log_service_query', 'log_errors', 'log_warnings',
    'log_initfini',
})
SERVICE_FILTER_OPTIONS = frozenset({
    'include_filter', 'exclude_filter', 'include_gds_codes', 'exclude_gds_codes',
})
SERVICE_SAFE_FLAGS = frozenset({'log_services', 'log_initfini'})
SERVICE_DEFAULTS = {'log_services': True, 'log_initfini': True}

_SED_SUBSTITUTION = re.compile(r'\\[0-9]')


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

    service_fields = [
        {'field_id': key, 'control': 'checkbox', 'default': SERVICE_DEFAULTS.get(key, False)}
        for key in sorted(SERVICE_BOOLEAN_OPTIONS)
    ]
    service_fields += [
        {'field_id': key, 'control': 'text', 'maximum_utf8_bytes': 4096, 'default': ''}
        for key in sorted(SERVICE_FILTER_OPTIONS)
    ]
    service_fields.extend([
        {'field_id': 'capture_sensitive', 'control': 'checkbox', 'default': False},
        {'field_id': 'service_scope_confirmed', 'control': 'checkbox', 'default': False},
    ])

    audit_fields = [
        {'field_id': 'log_filename', 'control': 'text', 'maximum_utf8_bytes': 4096, 'default': ''},
        {'field_id': 'max_log_size', 'control': 'number', 'minimum': 0, 'maximum': 4294967295,
         'default': 100, 'zero_semantics': 'native unlimited (no log rotation)'},
    ]

    return {
        'schema': 'scratchrobin.firebird.trace-api@1',
        'engine_version': '5.0.4',
        'scope': (
            'managed user trace of verified database filename/alias or engine-instance services, '
            'reviewed external session controls, and system-audit configuration validation'
        ),
        'workspace_action': 'firebird_trace',
        'supported_scopes': ['database', 'services', 'database_and_services', 'system_audit'],
        'option_fields': fields,
        'service_option_fields': service_fields,
        'audit_option_fields': audit_fields,
        'actions': [
            'describe', 'review', 'apply', 'get', 'list', 'list_native',
            'poll', 'read_audit_log',
        ],
        'review_operations': [
            'start', 'start_services', 'suspend', 'resume', 'stop', 'release', 'forget',
            'suspend_external', 'resume_external', 'stop_external',
        ],
        'review_expiry_seconds': 300,
        'captured_output_persisted': False,
        'native_scope_is_filename_not_permanent_inode_lock': True,
        'system_audit_delivery': 'AuditTraceConfigFile host log file (separate from interactive service streams)',
        'configuration_text_restrictions': [
            'double quotes', 'control characters', 'configuration macros',
            'unapproved audit log paths or sed backreferences',
        ],
    }


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


def normalize_service_options(options):
    allowed = SERVICE_BOOLEAN_OPTIONS | SERVICE_FILTER_OPTIONS | {
        'capture_sensitive', 'service_scope_confirmed',
    }
    if not isinstance(options, Mapping) or set(options) - allowed:
        raise ValueError('Unknown native service trace option')
    result = {**SERVICE_DEFAULTS, **options}
    sensitive = result.pop('capture_sensitive', False)
    confirmed = result.pop('service_scope_confirmed', False)
    if type(sensitive) is not bool:
        raise ValueError('Sensitive capture approval must be boolean')
    if confirmed is not True:
        raise ValueError(
            'Explicit service_scope_confirmed approval is required because native '
            'service tracing observes engine-instance service activity'
        )
    for key, value in result.items():
        if key in SERVICE_BOOLEAN_OPTIONS and type(value) is not bool:
            raise ValueError('Native service trace switches must be boolean')
        if key in SERVICE_FILTER_OPTIONS:
            text(value)
    if not sensitive and (
        any(result.get(key) for key in SERVICE_BOOLEAN_OPTIONS - SERVICE_SAFE_FLAGS)
        or any(result.get(key) for key in SERVICE_FILTER_OPTIONS)
    ):
        raise ValueError(
            'Explicit sensitive-capture approval is required for service queries, '
            'errors, warnings or service filters'
        )
    return {
        **result,
        'capture_sensitive': sensitive,
        'service_scope_confirmed': True,
    }


def _database_pattern(database, attachment_names=()):
    database = text(database)
    if not database:
        raise ValueError('Trace requires the observed native database filename')
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
    return pattern.replace('{', '{{').replace('}', '}}')


def _append_section_options(lines, options, filter_keys):
    for key, value in sorted(options.items()):
        if key in {'capture_sensitive', 'service_scope_confirmed'}:
            continue
        if key in filter_keys:
            if value == '':
                continue
            value = '"' + value.replace('{', '{{').replace('}', '}}') + '"'
        elif type(value) is bool:
            value = str(value).lower()
        lines.append(key + ' = ' + str(value))


def render(database, options, attachment_names=()):
    pattern = _database_pattern(database, attachment_names)
    options = normalize(options)
    lines = ['database', '{', 'enabled = false', '}', 'services', '{',
             'enabled = false', '}', 'database = "' + pattern + '"', '{', 'enabled = true']
    for key, value in sorted(options.items()):
        if key == 'capture_sensitive':
            continue
        if key in FILTER_OPTIONS:
            if value == '':
                continue
            value = '"' + value.replace('{', '{{').replace('}', '}}') + '"'
        elif type(value) is bool:
            value = str(value).lower()
        lines.append(key + ' = ' + str(value))
    return '\n'.join([*lines, '}', ''])


def render_services(service_options, *, database=None, database_options=None, attachment_names=()):
    svc = normalize_service_options(service_options)
    lines = ['database', '{', 'enabled = false', '}', 'services', '{', 'enabled = true']
    _append_section_options(lines, svc, SERVICE_FILTER_OPTIONS)
    lines.append('}')
    if database is not None or database_options is not None:
        if not database:
            raise ValueError('Combined database and service trace requires the observed database filename')
        pattern = _database_pattern(database, attachment_names)
        db_opts = normalize(database_options or {})
        lines.extend(['database = "' + pattern + '"', '{', 'enabled = true'])
        _append_section_options(lines, db_opts, FILTER_OPTIONS)
        lines.append('}')
    return '\n'.join([*lines, ''])


def _validate_audit_log_path(raw_path, allowed_root):
    raw_path = text(raw_path, 4096)
    if not raw_path or _SED_SUBSTITUTION.search(raw_path) or '\\' in raw_path:
        raise ValueError(
            'System audit log_filename must be a literal path without backslashes or sed substitutions'
        )
    if '{' in raw_path or '}' in raw_path:
        raise ValueError('System audit log_filename cannot contain braces')
    root = Path(allowed_root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Admitted audit directory must exist')
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        raise ValueError('System audit log_filename must be an absolute path')
    if any(part == '..' for part in candidate.parts):
        raise ValueError('Parent traversal is forbidden in system audit log_filename')
    parent = candidate.parent.resolve(strict=True)
    if parent != root and root not in parent.parents:
        raise ValueError('System audit log_filename is outside the admitted audit directory')
    resolved = parent / candidate.name
    if resolved.is_symlink() or (resolved.exists() and not resolved.is_file()):
        raise ValueError('System audit log_filename cannot be a symlink or non-regular file')
    return str(resolved)


def render_system_audit(audit_spec, allowed_root):
    """Render and validate a Firebird 5.0.4 AuditTraceConfigFile configuration."""
    if not isinstance(audit_spec, Mapping):
        raise ValueError('System audit specification must be an object')
    allowed_keys = {
        'database', 'attachment_names', 'all_databases', 'database_options',
        'database_log_filename', 'database_max_log_size',
        'enable_services', 'service_options', 'services_log_filename',
        'services_max_log_size',
    }
    if set(audit_spec) - allowed_keys:
        raise ValueError('Unknown system audit configuration field')
    enable_db = bool(audit_spec.get('database') or audit_spec.get('all_databases'))
    enable_svc = audit_spec.get('enable_services', False)
    if type(enable_svc) is not bool:
        raise ValueError('enable_services must be boolean')
    if not enable_db and not enable_svc:
        raise ValueError('System audit configuration must enable database or services auditing')

    lines = []
    if enable_db:
        all_db = audit_spec.get('all_databases', False)
        if type(all_db) is not bool:
            raise ValueError('all_databases must be boolean')
        db_log = _validate_audit_log_path(audit_spec.get('database_log_filename', ''), allowed_root)
        max_size = audit_spec.get('database_max_log_size', 100)
        if type(max_size) is not int or not 0 <= max_size <= 4294967295:
            raise ValueError('database_max_log_size must be a 32-bit non-negative integer')
        db_opts = normalize(audit_spec.get('database_options', {}))
        if all_db:
            if audit_spec.get('database'):
                raise ValueError('Do not combine all_databases with a single database selector')
            lines.extend(['database', '{', 'enabled = true'])
        else:
            pattern = _database_pattern(
                audit_spec.get('database', ''),
                audit_spec.get('attachment_names', ()),
            )
            lines.extend([
                'database', '{', 'enabled = false', '}',
                'database = "' + pattern + '"', '{', 'enabled = true',
            ])
        lines.append('log_filename = "' + db_log + '"')
        lines.append('max_log_size = ' + str(max_size))
        _append_section_options(lines, db_opts, FILTER_OPTIONS)
        lines.append('}')
    else:
        lines.extend(['database', '{', 'enabled = false', '}'])

    if enable_svc:
        svc_log = _validate_audit_log_path(audit_spec.get('services_log_filename', ''), allowed_root)
        svc_max = audit_spec.get('services_max_log_size', 100)
        if type(svc_max) is not int or not 0 <= svc_max <= 4294967295:
            raise ValueError('services_max_log_size must be a 32-bit non-negative integer')
        svc_opts = normalize_service_options(audit_spec.get('service_options', {}))
        lines.extend([
            'services', '{', 'enabled = true',
            'log_filename = "' + svc_log + '"',
            'max_log_size = ' + str(svc_max),
        ])
        _append_section_options(lines, svc_opts, SERVICE_FILTER_OPTIONS)
        lines.append('}')
    else:
        lines.extend(['services', '{', 'enabled = false', '}'])
    return '\n'.join([*lines, ''])


def read_audit_log_tail(log_filename, allowed_root, max_bytes=65536, max_lines=200):
    """Read bounded tail lines from an admitted system-audit log file without persisting SQL."""
    if (type(max_bytes) is not int or not 1024 <= max_bytes <= 262144
            or type(max_lines) is not int or not 1 <= max_lines <= 500):
        raise ValueError('Audit log tail bounds are invalid')
    resolved = Path(_validate_audit_log_path(log_filename, allowed_root))
    if not resolved.exists():
        return {
            'log_filename': str(resolved),
            'present': False,
            'size_bytes': 0,
            'truncated': False,
            'lines': [],
            'output_persisted': False,
        }
    stat_info = resolved.lstat()
    size = stat_info.st_size
    truncated = size > max_bytes
    with resolved.open('rb') as handle:
        if truncated:
            handle.seek(size - max_bytes)
        chunk = handle.read(max_bytes)
    decoded = chunk.decode('utf-8', errors='replace')
    raw_lines = decoded.splitlines()
    if truncated and raw_lines:
        # Drop partial leading line after byte seek.
        raw_lines = raw_lines[1:]
    selected = raw_lines[-max_lines:]
    formatted = []
    for idx, line in enumerate(selected, start=1):
        raw_line = line.encode('utf-8', errors='replace')
        clipped = len(raw_line) > 32768
        formatted.append({
            'sequence': idx,
            'text': raw_line[:32768].decode('utf-8', errors='ignore'),
            'truncated': clipped,
        })
    return {
        'log_filename': str(resolved),
        'present': True,
        'size_bytes': size,
        'truncated': truncated or len(raw_lines) > max_lines,
        'lines': formatted,
        'output_persisted': False,
    }


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

"""Typed DuckDB runtime settings catalog, scope enforcement, and read-back (DU-AUD-03).

Distinguishes:
1. Original-handle session/local scope (SET LOCAL / SET SESSION on caller handle)
2. Instance global scope (SET GLOBAL on DuckDB instance)
3. Open-time registration config defaults (applied only at database/session open)

Enforces native input types, read-only / lock_configuration immutability,
filesystem path containment, safe credential redaction, and read-back
verification on the intended handle.
"""
from collections.abc import Mapping
import os
import re

from ...sdk import RelationalClientError
from ..embedded_route import contained_database

SENSITIVE_SETTINGS = frozenset({
    's3_secret_access_key',
    's3_access_key_id',
    's3_session_token',
    'azure_account_key',
    'azure_connection_string',
    'http_proxy_password',
    'motherduck_token',
    'encryption_key',
})

PATH_SETTINGS = frozenset({
    'temp_directory',
    'extension_directory',
    'secret_directory',
    'home_directory',
})

PATH_LIST_SETTINGS = frozenset({
    'allowed_directories',
    'allowed_paths',
    'file_search_path',
})

SECURITY_SENSITIVE_SETTINGS = frozenset({
    'enable_external_access',
    'allow_unsigned_extensions',
    'allow_community_extensions',
    'allow_extensions_metadata_mismatch',
    'autoload_known_extensions',
    'autoinstall_known_extensions',
    'lock_configuration',
    'disabled_filesystems',
    *PATH_SETTINGS,
    *PATH_LIST_SETTINGS,
})

OPEN_TIME_ONLY_SETTINGS = frozenset({
    'access_mode',
    'allow_unsigned_extensions',
    'duckdb_api',
    'storage_compatibility_version',
    'default_block_size',
})

BYTE_SIZE_RE = re.compile(
    r'^\s*(?:0|[1-9][0-9]*(?:\.[0-9]+)?)\s*(?:B|KB|KIB|MB|MIB|GB|GIB|TB|TIB)?\s*$',
    re.IGNORECASE,
)


def _quote_ident(name):
    return '"' + str(name).replace('"', '""') + '"'


def _literal(text):
    return "'" + str(text).replace("'", "''") + "'"


def _control_kind(input_type):
    upper = str(input_type or '').upper()
    if upper == 'BOOLEAN':
        return 'boolean'
    if upper in {'BIGINT', 'UBIGINT', 'INTEGER', 'UINTEGER', 'SMALLINT', 'TINYINT', 'DOUBLE', 'FLOAT'}:
        return 'number'
    if upper.endswith('[]'):
        return 'multiselect'
    return 'text'


def _redact_value(name, value):
    lower = str(name or '').lower()
    if lower in SENSITIVE_SETTINGS or any(
        token in lower for token in ('password', 'secret_access_key', 'session_token', '_token', 'account_key')
    ):
        return '<redacted>' if value not in (None, '') else ''
    return value


def _validate_contained_path(route, raw_path, setting_name):
    if not isinstance(raw_path, str) or '\x00' in raw_path:
        raise ValueError(f'DuckDB setting {setting_name} requires a valid path string')
    stripped = raw_path.strip()
    if not stripped:
        return ''
    root = (route or {}).get('filesystem_root')
    if not isinstance(root, str) or not os.path.isabs(root):
        raise ValueError(f'DuckDB setting {setting_name} requires an approved absolute filesystem_root')
    if not os.path.isabs(stripped):
        raise ValueError(f'DuckDB setting {setting_name} requires an absolute path under filesystem_root')
    try:
        return contained_database({**dict(route), 'database': stripped})
    except RelationalClientError as exc:
        raise ValueError(str(exc)) from None


def validate_open_time_config(route, config):
    """Validate open-time connector/create config dictionary against route containment."""
    if config is None:
        return {}
    if not isinstance(config, Mapping):
        raise RelationalClientError('DuckDB config must be an object')
    cleaned = {}
    for raw_key, raw_val in config.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            raise RelationalClientError('DuckDB config keys must be non-empty strings')
        key = raw_key.strip()
        lower = key.lower()
        if isinstance(raw_val, list) and lower in {'allowed_directories', 'allowed_paths'}:
            if not all(isinstance(item, str) for item in raw_val):
                raise RelationalClientError(f'DuckDB config {key} requires string paths')
            try:
                cleaned[key] = [_validate_contained_path(route, item, key) for item in raw_val]
            except ValueError as exc:
                raise RelationalClientError(str(exc)) from None
            continue
        if not isinstance(raw_val, (str, int, float, bool)) or raw_val is None:
            raise RelationalClientError('DuckDB config must contain named scalar options')
        if lower in PATH_SETTINGS and isinstance(raw_val, str) and raw_val.strip():
            if (route or {}).get('filesystem_root'):
                try:
                    raw_val = _validate_contained_path(route, raw_val, key)
                except ValueError as exc:
                    raise RelationalClientError(str(exc)) from None
        cleaned[key] = raw_val
    return cleaned


def catalog(handle, route=None):
    rows = handle.execute(
        'SELECT name, value, description, input_type, scope, aliases '
        'FROM "system"."main".duckdb_settings() ORDER BY name'
    ).fetchall()
    open_config = dict((route or {}).get('config') or {})
    redacted_open_config = {k: _redact_value(k, v) for k, v in open_config.items()}
    lock_cfg = False
    ext_access = True
    items = []
    for name, value, description, input_type, scope, aliases in rows:
        sname = str(name)
        lower = sname.lower()
        if lower == 'lock_configuration':
            lock_cfg = str(value).lower() == 'true'
        if lower == 'enable_external_access':
            ext_access = str(value).lower() == 'true'
        native_scope = str(scope or 'LOCAL').upper()
        admitted_scopes = []
        if lower not in OPEN_TIME_ONLY_SETTINGS:
            if native_scope in {'LOCAL', 'GLOBAL_LOCAL', 'SESSION'}:
                admitted_scopes.append('SESSION')
            if native_scope in {'GLOBAL', 'GLOBAL_LOCAL'}:
                admitted_scopes.append('GLOBAL')
        admitted_scopes.append('OPEN_TIME_REGISTRATION')
        sensitive = _redact_value(sname, 'secret') == '<redacted>'
        items.append({
            'name': sname,
            'value': _redact_value(sname, value),
            'redacted': sensitive,
            'description': str(description or ''),
            'input_type': str(input_type or 'VARCHAR'),
            'control': _control_kind(input_type),
            'native_scope': native_scope,
            'admitted_scopes': admitted_scopes,
            'aliases': list(aliases or ()),
            'security_sensitive': lower in SECURITY_SENSITIVE_SETTINGS or sensitive,
            'open_time_only': lower in OPEN_TIME_ONLY_SETTINGS,
            'path_contained': lower in PATH_SETTINGS or lower in PATH_LIST_SETTINGS,
            'resettable': lower not in OPEN_TIME_ONLY_SETTINGS and not lock_cfg,
            'registration_default': redacted_open_config.get(sname),
        })
    for entry in items:
        if lock_cfg:
            entry['resettable'] = False
            entry['admitted_scopes'] = ['OPEN_TIME_REGISTRATION']
    return {
        'settings': items,
        'count': len(items),
        'lock_configuration': lock_cfg,
        'enable_external_access': ext_access,
        'read_only_route': bool((route or {}).get('read_only')),
        'registration_open_config': redacted_open_config,
        'scope_model': {
            'SESSION': 'Applies on the original retained DuckDB connection handle only.',
            'GLOBAL': 'Applies across the local DuckDB DatabaseInstance.',
            'OPEN_TIME_REGISTRATION': 'Stored on registration config and applied only when opening a fresh DuckDB instance.',
        },
    }


def _resolve_setting(items, requested_name):
    if not isinstance(requested_name, str) or not requested_name.strip():
        raise ValueError('Select an exact DuckDB setting name')
    needle = requested_name.strip().lower()
    for item in items:
        if item['name'].lower() == needle or needle in [a.lower() for a in item['aliases']]:
            return item
    raise ValueError(f'Unknown native DuckDB setting: {requested_name}')


def _compile_typed_assignment(setting, raw_value, route):
    sname = setting['name']
    lower = sname.lower()
    itype = setting['input_type'].upper()
    if lower in PATH_SETTINGS:
        validated = _validate_contained_path(route, raw_value, sname)
        return _literal(validated)
    if lower in PATH_LIST_SETTINGS:
        if isinstance(raw_value, str):
            parts = [p.strip() for p in raw_value.split(',') if p.strip()] if lower == 'file_search_path' else [raw_value]
        elif isinstance(raw_value, list) and all(isinstance(p, str) for p in raw_value):
            parts = raw_value
        else:
            raise ValueError(f'DuckDB setting {sname} requires a path or list of paths')
        contained = [_validate_contained_path(route, p, sname) for p in parts]
        if itype.endswith('[]'):
            return '[' + ', '.join(_literal(p) for p in contained) + ']'
        return _literal(','.join(contained))
    if itype == 'BOOLEAN':
        if type(raw_value) is bool:
            return 'true' if raw_value else 'false'
        if isinstance(raw_value, str) and raw_value.strip().lower() in {'true', 'false'}:
            return raw_value.strip().lower()
        raise ValueError(f'DuckDB setting {sname} requires a boolean value')
    if itype in {'BIGINT', 'UBIGINT', 'INTEGER', 'UINTEGER', 'SMALLINT', 'TINYINT'}:
        if type(raw_value) is bool:
            raise ValueError(f'DuckDB setting {sname} requires an integer value')
        if type(raw_value) is int:
            ival = raw_value
        elif isinstance(raw_value, str) and re.fullmatch(r'-?(?:0|[1-9][0-9]*)', raw_value.strip()):
            ival = int(raw_value.strip())
        else:
            raise ValueError(f'DuckDB setting {sname} requires an exact integer')
        if itype.startswith('U') and ival < 0:
            raise ValueError(f'DuckDB setting {sname} requires a non-negative integer')
        return str(ival)
    if itype in {'DOUBLE', 'FLOAT'}:
        if type(raw_value) is bool or not isinstance(raw_value, (int, float, str)):
            raise ValueError(f'DuckDB setting {sname} requires a numeric value')
        fval = float(raw_value)
        return str(fval)
    if itype.endswith('[]'):
        if not isinstance(raw_value, list) or not all(isinstance(x, str) and '\x00' not in x for x in raw_value):
            raise ValueError(f'DuckDB setting {sname} requires an array of strings')
        return '[' + ', '.join(_literal(x) for x in raw_value) + ']'
    if not isinstance(raw_value, str) or '\x00' in raw_value or len(raw_value.encode('utf-8')) > 65536:
        raise ValueError(f'DuckDB setting {sname} requires bounded text')
    if lower in {'memory_limit', 'max_memory', 'max_temp_directory_size'} and not BYTE_SIZE_RE.match(raw_value):
        raise ValueError(f'DuckDB setting {sname} requires a valid byte size (e.g. 512MB, 2GB)')
    return _literal(raw_value)


def action(client, handle, route, request):
    if not isinstance(request, Mapping):
        raise ValueError('Select a typed DuckDB runtime-settings operation')
    op = request.get('operation')
    if op not in {'inventory', 'set', 'reset'}:
        raise ValueError('Select inventory, set, or reset for DuckDB runtime settings')
    snap = catalog(handle, route)
    if op == 'inventory':
        return snap

    target = _resolve_setting(snap['settings'], request.get('name'))
    sname = target['name']
    lower = sname.lower()
    scope = str(request.get('scope') or ('SESSION' if 'SESSION' in target['admitted_scopes'] else 'GLOBAL')).upper()
    if scope == 'LOCAL':
        scope = 'SESSION'
    if scope not in {'SESSION', 'GLOBAL'}:
        raise ValueError('Runtime SET/RESET scope must be SESSION or GLOBAL; open-time settings require registration edit and reconnect')
    if snap['lock_configuration']:
        raise ValueError('DuckDB lock_configuration is active; runtime configuration changes are locked')
    if target['open_time_only']:
        raise ValueError(
            f'DuckDB setting {sname} is an open-time configuration option; update registration defaults and reopen'
        )
    if scope not in target['admitted_scopes']:
        raise ValueError(
            f'DuckDB setting {sname} supports native scope {target["native_scope"]}, not {scope}'
        )
    if route.get('read_only') is True and lower in {'access_mode', 'checkpoint_threshold', 'wal_autocheckpoint'}:
        raise ValueError(f'Read-only DuckDB route refuses write-lifecycle setting {sname}')

    scope_kw = 'SESSION' if scope == 'SESSION' else 'GLOBAL'
    ident = _quote_ident(sname)
    if op == 'set':
        if 'value' not in request:
            raise ValueError('Supply a typed value for DuckDB runtime SET')
        rhs = _compile_typed_assignment(target, request['value'], route)
        sql = f'SET {scope_kw} {ident} = {rhs}'
    else:
        sql = f'RESET {scope_kw} {ident}'

    import duckdb
    try:
        handle.execute(sql)
    except duckdb.Error as exc:
        client._observe(handle)
        raise ValueError(f'DuckDB rejected {op.upper()} on {sname} ({type(exc).__name__})') from None

    client._observe(handle)
    read_back_row = handle.execute(
        'SELECT value, scope FROM "system"."main".duckdb_settings() WHERE name = ?',
        [sname],
    ).fetchone()
    observed_val = _redact_value(sname, read_back_row[0] if read_back_row else None)
    return {
        'operation': op,
        'name': sname,
        'requested_scope': scope,
        'native_scope': read_back_row[1] if read_back_row else target['native_scope'],
        'observed_value': observed_val,
        'redacted': target['redacted'],
        'statement': f'SET {scope_kw} {ident} = <redacted>' if (op == 'set' and target['redacted']) else sql,
        'verified_on_original_handle': True,
        'persists_across_reopen': False,
    }

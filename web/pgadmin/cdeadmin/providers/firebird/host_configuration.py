"""Reviewed Firebird 5.0.4 host configuration management and daemon reload/rollback.

Covers firebird.conf, databases.conf, replication.conf and plugins.conf on an
admitted application-host runtime with generation CAS, atomic backups, native
RDB$CONFIG validation, secret-free previews/receipts and failed-restart recovery.
"""
from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time

from ...operations.fileio import exclusive_file_lock
from .configuration import KEYS
from .host_runtime_grant import verify_same_host

CONFIG_FILES = ('firebird.conf', 'databases.conf', 'replication.conf', 'plugins.conf')
_KEY_BY_LOWER = {name.lower(): (name, meta) for name, meta in KEYS.items()}
_IDENT_RE = re.compile(r'^[A-Za-z0-9_.\-\u0080-\uffff]{1,128}$')
_GUID_RE = re.compile(r'^\{[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}\}$')
_ALLOWED_REPL_MACROS = frozenset({'$(filename)', '$(pathname)', '$(archivepathname)'})
_MACRO_RE = re.compile(r'\$\([^)]*\)')

REPLICATION_BOOL_KEYS = frozenset({
    'log_errors', 'report_errors', 'disable_on_error',
    'verbose_logging', 'cascade_replication',
})
REPLICATION_INT_KEYS = {
    'buffer_size': (65536, 1073741824),
    'journal_segment_size': (65536, 2147483647),
    'journal_segment_count': (0, 65535),
    'journal_group_flush_delay': (0, 60000),
    'journal_archive_timeout': (0, 86400),
    'apply_idle_timeout': (1, 86400),
    'apply_error_timeout': (1, 86400),
}
REPLICATION_PATH_KEYS = frozenset({
    'journal_directory', 'journal_archive_directory', 'journal_source_directory',
})
REPLICATION_TEXT_KEYS = frozenset({
    'plugin', 'include_filter', 'exclude_filter', 'journal_file_prefix',
    'journal_archive_command', 'source_guid',
})


def descriptor():
    return {
        'schema': 'scratchrobin.firebird.host-configuration-api@1',
        'engine_version': '5.0.4',
        'supported_platforms': ['linux'],
        'managed_files': list(CONFIG_FILES),
        'known_firebird_conf_keys': len(KEYS),
        'requires_permissions': ['administer', 'maintenance_admin'],
        'actions': ['describe', 'inspect', 'review', 'apply', 'get', 'list'],
        'lifecycle_actions': ['write_only', 'restart_managed_daemon'],
        'notes': (
            'Validates Firebird 5.0.4 host configuration files against native '
            'key types and scopes, enforces generation compare-and-set, writes '
            'atomic backups, probes native Engine13 RDB$CONFIG parsing, and '
            'rolls back automatically if native validation or managed daemon '
            'restart fails.'
        ),
    }


def _clean_single_line(value, label, max_bytes=4096):
    if (not isinstance(value, str)
            or len(value.encode('utf-8')) > max_bytes
            or any(ord(ch) < 32 or ch == '\x7f' for ch in value)):
        raise ValueError(f'{label} must be valid single-line UTF-8 text without control characters')
    return value


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def validate_setting_value(raw_key, raw_value, *, database_scope_only=False):
    if not isinstance(raw_key, str) or raw_key.lower() not in _KEY_BY_LOWER:
        raise ValueError(f'Unknown Firebird 5.0.4 configuration key: {raw_key!r}')
    canonical_key, meta = _KEY_BY_LOWER[raw_key.lower()]
    if database_scope_only and meta['configuration_scope'] != 'database-overridable':
        raise ValueError(
            f'{canonical_key} has global scope and cannot be overridden per-database in databases.conf'
        )
    if isinstance(raw_value, bool):
        val_str = 'true' if raw_value else 'false'
    elif isinstance(raw_value, int):
        val_str = str(raw_value)
    elif isinstance(raw_value, str):
        val_str = _clean_single_line(raw_value.strip(), canonical_key)
    else:
        raise ValueError(f'Invalid value type for {canonical_key}')

    if not val_str or '"' in val_str or '#' in val_str or '$(' in val_str or '{' in val_str or '}' in val_str:
        raise ValueError(
            f'{canonical_key} value cannot be empty or contain quotes, comments, braces or macros'
        )
    if canonical_key.lower() == 'include':
        raise ValueError('Configuration include directives are forbidden')

    native_type = meta['native_type']
    if native_type == 'boolean':
        if val_str.lower() not in {'true', 'false', 'yes', 'no', 'y', 'n', '0', '1'}:
            raise ValueError(f'{canonical_key} requires a boolean value')
    elif native_type == 'integer':
        match = re.fullmatch(r'(-?[0-9]{1,15})([kKmMgG]?)', val_str)
        if not match:
            raise ValueError(f'{canonical_key} requires an integer value (optional K/M/G suffix)')
        mult = {'': 1, 'k': 1024, 'm': 1024 ** 2, 'g': 1024 ** 3}[match.group(2).lower()]
        numeric = int(match.group(1)) * mult
        if not -9223372036854775808 <= numeric <= 9223372036854775807:
            raise ValueError(f'{canonical_key} integer is out of 64-bit range')
        if canonical_key == 'RemoteServicePort' and not 1 <= numeric <= 65535:
            raise ValueError('RemoteServicePort must be between 1 and 65535')
        if canonical_key != 'ProcessPriorityLevel' and numeric < 0:
            raise ValueError(f'{canonical_key} cannot be negative')
    else:
        if canonical_key == 'WireCrypt' and val_str.lower() not in {'disabled', 'enabled', 'required'}:
            raise ValueError('WireCrypt must be Disabled, Enabled or Required')
        if canonical_key == 'ServerMode' and val_str.lower() not in {'super', 'superclassic', 'classic'}:
            raise ValueError('ServerMode must be Super, SuperClassic or Classic')
    return canonical_key, val_str, meta


def parse_firebird_conf(text):
    entries = {}
    for lineno, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if line.lower().startswith('include '):
            raise ValueError(f'firebird.conf line {lineno}: include directives are not admitted')
        match = re.fullmatch(
            r'([A-Za-z][A-Za-z0-9]*)\s*=\s*(?:"([^"\r\n]*)"|([^"#\r\n]*?))\s*(?:#.*)?',
            line,
        )
        if not match:
            raise ValueError(f'firebird.conf line {lineno}: invalid assignment syntax')
        raw_val = (match.group(2) if match.group(2) is not None else match.group(3)).strip()
        key, norm_val, meta = validate_setting_value(match.group(1), raw_val)
        entries[key] = {
            'value': norm_val,
            'native_type': meta['native_type'],
            'configuration_scope': meta['configuration_scope'],
        }
    return entries


def render_firebird_conf(entries_map):
    lines = ['# Managed by ScratchRobin Firebird 5.0.4 host configuration adapter']
    for key in sorted(entries_map):
        val = entries_map[key]['value'] if isinstance(entries_map[key], Mapping) else entries_map[key]
        canonical_key, norm_val, _ = validate_setting_value(key, val)
        if ' ' in norm_val or '\t' in norm_val:
            lines.append(f'{canonical_key} = "{norm_val}"')
        else:
            lines.append(f'{canonical_key} = {norm_val}')
    return '\n'.join(lines) + '\n'


def parse_databases_conf(text):
    """Parse databases.conf aliases and optional per-database override blocks."""
    aliases = {}
    lines = text.splitlines()
    idx = 0
    total = len(lines)
    while idx < total:
        line = lines[idx].strip()
        idx += 1
        if not line or line.startswith('#'):
            continue
        inline_brace = False
        if line.endswith('{'):
            inline_brace = True
            line = line[:-1].strip()
        match = re.fullmatch(
            r'([^=\s#{}]+)\s*=\s*(?:"([^"\r\n]*)"|([^"#\r\n{}]*?))\s*(?:#.*)?',
            line,
        )
        if not match:
            raise ValueError(f'databases.conf line {idx}: invalid alias assignment')
        alias = _clean_single_line(match.group(1).strip(), 'Database alias', 256)
        db_path = _clean_single_line(
            (match.group(2) if match.group(2) is not None else match.group(3)).strip(),
            'Database alias path',
            4096,
        )
        if '$(' in db_path and not db_path.startswith('$(dir_'):
            raise ValueError(f'databases.conf line {idx}: unsupported macro in alias path')
        overrides = {}
        # Check if next non-empty non-comment line opens '{'
        probe = idx
        while not inline_brace and probe < total:
            peek = lines[probe].strip()
            if not peek or peek.startswith('#'):
                probe += 1
                continue
            if peek == '{':
                inline_brace = True
                idx = probe + 1
            break
        if inline_brace:
            closed = False
            while idx < total:
                bline = lines[idx].strip()
                idx += 1
                if not bline or bline.startswith('#'):
                    continue
                if bline == '}':
                    closed = True
                    break
                kv = re.fullmatch(
                    r'([A-Za-z][A-Za-z0-9]*)\s*=\s*(?:"([^"\r\n]*)"|([^"#\r\n]*?))\s*(?:#.*)?',
                    bline,
                )
                if not kv:
                    raise ValueError(f'databases.conf line {idx}: invalid per-database override')
                raw_v = (kv.group(2) if kv.group(2) is not None else kv.group(3)).strip()
                ckey, nval, _ = validate_setting_value(kv.group(1), raw_v, database_scope_only=True)
                overrides[ckey] = nval
            if not closed:
                raise ValueError(f'databases.conf alias {alias!r}: unclosed override block')
        aliases[alias] = {'path': db_path, 'overrides': overrides}
    return aliases


def render_databases_conf(aliases):
    lines = ['# Managed by ScratchRobin Firebird 5.0.4 databases.conf adapter']
    for alias in sorted(aliases):
        if not _IDENT_RE.match(alias):
            raise ValueError(f'Invalid database alias name: {alias!r}')
        spec = aliases[alias]
        db_path = _clean_single_line(spec['path'], 'Database path', 4096)
        if not Path(db_path).is_absolute() or '..' in Path(db_path).parts or '"' in db_path:
            raise ValueError(f'Database alias {alias!r} requires a canonical absolute path without quotes')
        quoted_path = f'"{db_path}"' if ' ' in db_path else db_path
        overrides = spec.get('overrides') or {}
        if not overrides:
            lines.append(f'{alias} = {quoted_path}')
        else:
            lines.append(f'{alias} = {quoted_path}')
            lines.append('{')
            for raw_k, raw_v in sorted(overrides.items()):
                ckey, nval, _ = validate_setting_value(raw_k, raw_v, database_scope_only=True)
                qval = f'"{nval}"' if ' ' in nval else nval
                lines.append(f'  {ckey} = {qval}')
            lines.append('}')
    return '\n'.join(lines) + '\n'


def _validate_archive_command(cmd):
    cmd = _clean_single_line(cmd, 'journal_archive_command', 2048)
    if '"' in cmd or any(ch in cmd for ch in (';', '|', '`', '>', '<')):
        raise ValueError(
            'journal_archive_command cannot contain quotes, pipes, redirections, backticks or command separators'
        )
    for macro in _MACRO_RE.findall(cmd):
        if macro not in _ALLOWED_REPL_MACROS:
            raise ValueError(f'Unsupported replication archive macro: {macro}')
    return cmd


def _render_replication_section(header, section, allowed_roots):
    if not isinstance(section, Mapping):
        raise ValueError('Replication section must be an object')
    allowed = (
        REPLICATION_BOOL_KEYS
        | set(REPLICATION_INT_KEYS)
        | REPLICATION_PATH_KEYS
        | REPLICATION_TEXT_KEYS
        | {'sync_replicas'}
    )
    unknown = set(section) - allowed
    if unknown:
        raise ValueError('Unknown replication.conf options: ' + ', '.join(sorted(unknown)))
    lines = [header, '{']
    for key in sorted(section):
        if key == 'sync_replicas':
            continue
        val = section[key]
        if key in REPLICATION_BOOL_KEYS:
            if type(val) is not bool:
                raise ValueError(f'{key} must be boolean')
            lines.append(f'  {key} = {str(val).lower()}')
        elif key in REPLICATION_INT_KEYS:
            lo, hi = REPLICATION_INT_KEYS[key]
            if type(val) is not int or not lo <= val <= hi:
                raise ValueError(f'{key} must be an integer between {lo} and {hi}')
            lines.append(f'  {key} = {val}')
        elif key in REPLICATION_PATH_KEYS:
            p_str = _clean_single_line(val, key, 4096)
            p_obj = Path(p_str)
            if not p_obj.is_absolute() or '..' in p_obj.parts or '"' in p_str or '$(' in p_str:
                raise ValueError(f'{key} must be a canonical absolute directory path')
            if allowed_roots:
                resolved_parent = p_obj.parent.resolve(strict=True)
                target_dir = resolved_parent / p_obj.name
                if not any(
                    target_dir == Path(r) or Path(r) in target_dir.parents
                    for r in allowed_roots
                ):
                    raise ValueError(f'{key} is outside admitted replication journal directories')
            qpath = f'"{p_str}"' if ' ' in p_str else p_str
            lines.append(f'  {key} = {qpath}')
        elif key == 'journal_archive_command':
            cmd = _validate_archive_command(val)
            lines.append(f'  journal_archive_command = "{cmd}"')
        elif key == 'source_guid':
            guid = _clean_single_line(val, 'source_guid', 64)
            if not _GUID_RE.match(guid):
                raise ValueError('source_guid must match "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}"')
            lines.append(f'  source_guid = "{guid}"')
        else:
            txt = _clean_single_line(val, key, 1024)
            if '"' in txt or '$(' in txt or '{' in txt or '}' in txt:
                raise ValueError(f'{key} cannot contain quotes, braces or macros')
            lines.append(f'  {key} = "{txt}"' if ' ' in txt else f'  {key} = {txt}')

    replicas = section.get('sync_replicas') or []
    if not isinstance(replicas, list):
        raise ValueError('sync_replicas must be a list')
    for rep in replicas:
        if not isinstance(rep, Mapping):
            raise ValueError('Each sync_replica entry must be an object')
        if set(rep) - {'dsn', 'username', 'username_env', 'username_file', 'password_env', 'password_file'}:
            raise ValueError('sync_replica entry contains unsupported or inline-secret fields (use password_file/password_env)')
        dsn = _clean_single_line(rep.get('dsn', ''), 'sync_replica.dsn', 2048)
        if not dsn or '@' in dsn or '"' in dsn or '{' in dsn or '}' in dsn or '$(' in dsn:
            raise ValueError('sync_replica.dsn must not embed inline credentials (@) or macros')
        qdsn = f'"{dsn}"' if ' ' in dsn else dsn
        lines.append(f'  sync_replica = {qdsn}')
        lines.append('  {')
        for subkey in ('username', 'username_env', 'username_file', 'password_env', 'password_file'):
            if subkey in rep and rep[subkey] is not None:
                sval = _clean_single_line(rep[subkey], f'sync_replica.{subkey}', 1024)
                if '"' in sval or '$(' in sval or '{' in sval or '}' in sval:
                    raise ValueError(f'sync_replica.{subkey} contains forbidden characters')
                if subkey.endswith('_file'):
                    fp = Path(sval)
                    if not fp.is_absolute() or '..' in fp.parts:
                        raise ValueError(f'sync_replica.{subkey} must be an absolute path without ..')
                lines.append(f'    {subkey} = "{sval}"' if ' ' in sval else f'    {subkey} = {sval}')
        lines.append('  }')
    lines.append('}')
    return lines


def render_replication_conf(spec, host_scope):
    if not isinstance(spec, Mapping) or set(spec) - {'default_section', 'databases'}:
        raise ValueError('replication.conf specification allows only default_section and databases')
    allowed_roots = list(host_scope.get('journal_directories') or ()) + [host_scope['firebird_runtime_root']]
    lines = ['# Managed by ScratchRobin Firebird 5.0.4 replication.conf adapter']
    if spec.get('default_section'):
        lines.extend(_render_replication_section('database', spec['default_section'], allowed_roots))
    db_sections = spec.get('databases') or {}
    if not isinstance(db_sections, Mapping):
        raise ValueError('replication.conf databases must map canonical database path to section options')
    for db_path in sorted(db_sections):
        clean_db = _clean_single_line(db_path, 'Replication database path', 4096)
        if not Path(clean_db).is_absolute() or '..' in Path(clean_db).parts or '"' in clean_db:
            raise ValueError('Replication database path must be canonical and absolute')
        header = f'database = "{clean_db}"' if ' ' in clean_db else f'database = {clean_db}'
        lines.extend(_render_replication_section(header, db_sections[db_path], allowed_roots))
    return '\n'.join(lines) + '\n'


def _validate_plugin_macro_path(value, label):
    val = _clean_single_line(value, label, 1024)
    if '"' in val or '..' in val or '{' in val or '}' in val:
        raise ValueError(f'{label} cannot contain quotes, braces or parent traversal')
    for macro in _MACRO_RE.findall(val):
        if macro != '$(dir_plugins)':
            raise ValueError(f'{label} admits only $(dir_plugins), not {macro}')
    if not val.startswith('$(dir_plugins)/'):
        raise ValueError(f'{label} must reference a module or file under $(dir_plugins)/')
    return val


def render_plugins_conf(spec):
    if not isinstance(spec, Mapping) or set(spec) - {'plugins', 'configs'}:
        raise ValueError('plugins.conf specification allows only plugins and configs')
    plugins = spec.get('plugins') or []
    configs = spec.get('configs') or []
    if not isinstance(plugins, list) or not isinstance(configs, list):
        raise ValueError('plugins and configs must be lists')
    lines = ['# Managed by ScratchRobin Firebird 5.0.4 plugins.conf adapter']
    seen_plugins = set()
    for item in plugins:
        if not isinstance(item, Mapping) or set(item) - {'name', 'module', 'register_name', 'config', 'config_file'}:
            raise ValueError('Plugin block contains unknown fields')
        name = _clean_single_line(item.get('name', ''), 'Plugin name', 128)
        if not _IDENT_RE.match(name) or name in seen_plugins:
            raise ValueError(f'Invalid or duplicate plugin entry: {name!r}')
        seen_plugins.add(name)
        module = _validate_plugin_macro_path(item.get('module', ''), 'Plugin Module')
        lines.append(f'Plugin = {name} {{')
        if item.get('register_name'):
            reg = _clean_single_line(item['register_name'], 'RegisterName', 128)
            if not _IDENT_RE.match(reg):
                raise ValueError('Invalid RegisterName')
            lines.append(f'  RegisterName = {reg}')
        lines.append(f'  Module = {module}')
        if item.get('config'):
            cfg_name = _clean_single_line(item['config'], 'Config', 128)
            if not _IDENT_RE.match(cfg_name):
                raise ValueError('Invalid Config section reference')
            lines.append(f'  Config = {cfg_name}')
        if item.get('config_file'):
            cfg_file = _validate_plugin_macro_path(item['config_file'], 'ConfigFile')
            lines.append(f'  ConfigFile = {cfg_file}')
        lines.append('}')

    seen_configs = set()
    for cfg in configs:
        if not isinstance(cfg, Mapping) or set(cfg) - {'name', 'entries'}:
            raise ValueError('Config block contains unknown fields')
        cname = _clean_single_line(cfg.get('name', ''), 'Config name', 128)
        if not _IDENT_RE.match(cname) or cname in seen_configs:
            raise ValueError(f'Invalid or duplicate Config block: {cname!r}')
        seen_configs.add(cname)
        entries = cfg.get('entries') or {}
        if not isinstance(entries, Mapping) or not entries:
            raise ValueError(f'Config {cname!r} requires at least one key/value entry')
        lines.append(f'Config = {cname} {{')
        for k, v in sorted(entries.items()):
            ck = _clean_single_line(str(k), 'Config key', 128)
            if not _IDENT_RE.match(ck):
                raise ValueError(f'Invalid Config key: {ck!r}')
            cv = _clean_single_line(str(v), f'Config.{ck}', 1024)
            if '"' in cv or '..' in cv or '{' in cv or '}':
                if '{' in cv or '}' in cv or '"' in cv or '..' in cv:
                    raise ValueError(f'Config.{ck} contains forbidden characters')
            for macro in _MACRO_RE.findall(cv):
                if macro != '$(dir_plugins)':
                    raise ValueError(f'Config.{ck} admits only $(dir_plugins)')
            lines.append(f'  {ck} = {cv}')
        lines.append('}')
    return '\n'.join(lines) + '\n'


def _read_file_state(runtime_root, filename):
    path = Path(runtime_root) / filename
    if not path.exists():
        return {'exists': False, 'generation_sha256': '', 'size_bytes': 0, 'raw_text': ''}
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'{filename} must not be a symlink or non-regular file')
    raw = path.read_bytes()
    return {
        'exists': True,
        'generation_sha256': _sha256_bytes(raw),
        'size_bytes': len(raw),
        'raw_text': raw.decode('utf-8', errors='replace'),
    }


def inspect_host_configuration(host_scope, client=None, route=None):
    runtime_root = host_scope['firebird_runtime_root']
    files = {}
    for name in CONFIG_FILES:
        state = _read_file_state(runtime_root, name)
        summary = {
            'exists': state['exists'],
            'generation_sha256': state['generation_sha256'],
            'size_bytes': state['size_bytes'],
        }
        if name == 'firebird.conf' and state['exists']:
            try:
                summary['entries'] = parse_firebird_conf(state['raw_text'])
            except ValueError as err:
                summary['parse_warning'] = str(err)
        elif name == 'databases.conf' and state['exists']:
            try:
                summary['aliases'] = parse_databases_conf(state['raw_text'])
            except ValueError as err:
                summary['parse_warning'] = str(err)
        files[name] = summary

    live_config = None
    pending_restart_keys = []
    if client is not None and route is not None and route.get('database'):
        try:
            conn = client._connect({'route': route})
            try:
                cur = conn.cursor()
                try:
                    cur.execute(
                        'SELECT TRIM(TRAILING FROM RDB$CONFIG_NAME), RDB$CONFIG_VALUE, RDB$CONFIG_IS_SET '
                        'FROM RDB$CONFIG ORDER BY 1'
                    )
                    live_config = {
                        row[0]: {'value': row[1], 'is_set': bool(row[2])}
                        for row in cur.fetchall()
                    }
                finally:
                    cur.close()
                conn.rollback()
            finally:
                client._forget_and_close(conn)
            fb_entries = files.get('firebird.conf', {}).get('entries') or {}
            for key, meta in fb_entries.items():
                if key in live_config and str(live_config[key]['value']).lower() != str(meta['value']).lower():
                    pending_restart_keys.append(key)
        except Exception as err:
            live_config = {'available': False, 'error_type': type(err).__name__}

    return {
        'schema': 'scratchrobin.firebird.host-configuration-snapshot@1',
        'runtime_root': runtime_root,
        'managed_daemon_configured': host_scope.get('managed_daemon') is not None,
        'files': files,
        'live_rdb_config': live_config,
        'pending_restart_keys': sorted(pending_restart_keys),
    }


def prepare_configuration_review(host_scope, request):
    if not isinstance(request, Mapping):
        raise ValueError('Configuration review request must be an object')
    allowed = {
        'target_file', 'expected_generation_sha256', 'lifecycle_action',
        'set_options', 'unset_options', 'upsert_aliases', 'remove_aliases',
        'confirmation', 'replication_spec', 'plugins_spec',
    }
    if set(request) - allowed:
        raise ValueError('Unknown host configuration review fields')
    target_file = request.get('target_file')
    if target_file not in CONFIG_FILES:
        raise ValueError('target_file must be one of ' + ', '.join(CONFIG_FILES))
    expected_gen = request.get('expected_generation_sha256')
    if not isinstance(expected_gen, str):
        raise ValueError('expected_generation_sha256 is required for concurrency protection')
    lifecycle_action = request.get('lifecycle_action', 'write_only')
    if lifecycle_action not in {'write_only', 'restart_managed_daemon'}:
        raise ValueError('Invalid lifecycle_action')
    if lifecycle_action == 'restart_managed_daemon' and not host_scope.get('managed_daemon'):
        raise ValueError('restart_managed_daemon requires a managed_daemon grant for this host runtime')

    current = _read_file_state(host_scope['firebird_runtime_root'], target_file)
    if current['generation_sha256'] != expected_gen:
        raise ValueError('Configuration file generation changed; inspect and review again')

    restart_required = False
    preserved_siblings = []
    if target_file == 'firebird.conf':
        entries = parse_firebird_conf(current['raw_text']) if current['exists'] else {}
        set_opts = request.get('set_options') or {}
        unset_opts = request.get('unset_options') or []
        if not isinstance(set_opts, Mapping) or not isinstance(unset_opts, list):
            raise ValueError('set_options must be an object and unset_options a list')
        if not set_opts and not unset_opts:
            raise ValueError('Specify at least one setting to set or unset in firebird.conf')
        for rem in unset_opts:
            ckey, _, meta = validate_setting_value(rem, '0' if KEYS.get(rem, {}).get('native_type') != 'boolean' else 'false')
            if ckey in entries:
                if meta['configuration_scope'] == 'global':
                    restart_required = True
                entries.pop(ckey, None)
        for raw_k, raw_v in set_opts.items():
            ckey, nval, meta = validate_setting_value(raw_k, raw_v)
            prev = entries.get(ckey, {}).get('value')
            if prev != nval and meta['configuration_scope'] == 'global':
                restart_required = True
            entries[ckey] = {
                'value': nval,
                'native_type': meta['native_type'],
                'configuration_scope': meta['configuration_scope'],
            }
        rendered = render_firebird_conf(entries)
    elif target_file == 'databases.conf':
        aliases = parse_databases_conf(current['raw_text']) if current['exists'] else {}
        upserts = request.get('upsert_aliases') or {}
        removals = request.get('remove_aliases') or []
        if not isinstance(upserts, Mapping) or not isinstance(removals, list):
            raise ValueError('upsert_aliases must be an object and remove_aliases a list')
        if not upserts and not removals:
            raise ValueError('Specify at least one alias upsert or removal for databases.conf')
        if removals:
            expected_confirm = ', '.join(sorted(str(x) for x in removals))
            if request.get('confirmation') != expected_confirm:
                raise ValueError(f'Confirm removed alias names exactly: {expected_confirm}')
            for rem in removals:
                aliases.pop(rem, None)
        for alias_name, spec in upserts.items():
            if not isinstance(spec, Mapping) or set(spec) - {'path', 'overrides'}:
                raise ValueError(f'Alias {alias_name!r} specification requires path and optional overrides')
            aliases[alias_name] = {
                'path': spec.get('path', ''),
                'overrides': dict(spec.get('overrides') or {}),
            }
        preserved_siblings = sorted(set(aliases) - set(upserts))
        rendered = render_databases_conf(aliases)
    elif target_file == 'replication.conf':
        rendered = render_replication_conf(request.get('replication_spec'), host_scope)
        restart_required = True
    else:
        rendered = render_plugins_conf(request.get('plugins_spec'))
        restart_required = True

    return {
        'scope': host_scope,
        'target_file': target_file,
        'expected_generation_sha256': expected_gen,
        'proposed_generation_sha256': _sha256_bytes(rendered.encode('utf-8')),
        'rendered_text': rendered,
        'lifecycle_action': lifecycle_action,
        'restart_required': restart_required,
        'preserved_sibling_aliases': preserved_siblings,
    }


def _probe_native_config_subprocess(runtime_root, lock_dir):
    """Run an isolated Engine13 probe verifying Firebird 5.0.4 accepts the runtime config."""
    script = (
        'import json, os, sys, tempfile\n'
        'from pathlib import Path\n'
        'import firebird.driver as fb\n'
        'rt = Path(sys.argv[1])\n'
        'fb.driver_config.fb_client_library.value = str(rt / "lib/libfbclient.so.5.0.4")\n'
        'with tempfile.TemporaryDirectory(prefix="fb-cfg-probe-") as d:\n'
        '    dbp = Path(d) / "probe.fdb"\n'
        '    cfg = fb.driver_config.register_database("cfg_probe")\n'
        '    cfg.database.value = str(dbp)\n'
        '    cfg.config.value = "ServerMode = SuperClassic\\nProviders = Engine13"\n'
        '    con = fb.create_database("cfg_probe", user="SYSDBA")\n'
        '    try:\n'
        '        cur = con.cursor()\n'
        '        cur.execute("SELECT TRIM(TRAILING FROM RDB$CONFIG_NAME), RDB$CONFIG_VALUE, RDB$CONFIG_IS_SET FROM RDB$CONFIG")\n'
        '        rows = {r[0]: {"value": r[1], "is_set": bool(r[2])} for r in cur.fetchall()}\n'
        '        cur.close()\n'
        '        con.rollback()\n'
        '        con.drop_database()\n'
        '    finally:\n'
        '        if not con.is_closed():\n'
        '            con.close()\n'
        'print(json.dumps({"ok": True, "rdb_config": rows}))\n'
    )
    Path(lock_dir).mkdir(parents=True, exist_ok=True)
    env = {
        k: v for k, v in os.environ.items()
        if k not in {'ISC_PASSWORD', 'ISC_USER', 'ISC_DATABASE', 'ISC_ROLE'}
    }
    env.update(
        FIREBIRD=str(runtime_root),
        FIREBIRD_LOCK=str(lock_dir),
        LD_LIBRARY_PATH=str(Path(runtime_root) / 'lib'),
    )
    proc = subprocess.run(
        [sys.executable, '-c', script, str(runtime_root)],
        env=env, capture_output=True, text=True, timeout=20, check=False,
    )
    if proc.returncode != 0:
        return {'ok': False, 'stderr': (proc.stderr or proc.stdout)[-600:]}
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip().startswith('{')]
    if not lines:
        return {'ok': False, 'stderr': 'Missing JSON output from native config probe'}
    return json.loads(lines[-1])


def apply_host_configuration(record):
    from .runtime_lifecycle import restart_managed_daemon_process

    payload = record['payload']
    host_scope = payload['scope']
    verify_same_host(host_scope)
    runtime_root = Path(host_scope['firebird_runtime_root'])
    target_file = payload['target_file']
    target_path = runtime_root / target_file
    lock_fd = os.open(str(runtime_root / '.cdeadmin_host_config.lock'), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        with exclusive_file_lock(lock_fd):
            current = _read_file_state(runtime_root, target_file)
            if current['generation_sha256'] != payload['expected_generation_sha256']:
                return {
                    'state': 'rejected',
                    'native_dispatched': False,
                    'reason': 'Configuration file generation changed since review; inspect and review again',
                }
            backup_dir = runtime_root / '.cdeadmin_backups' / record['review_id']
            backup_dir.mkdir(parents=True, exist_ok=True)
            backup_path = backup_dir / (target_file + '.bak')
            had_original = current['exists']
            if had_original:
                backup_path.write_bytes(target_path.read_bytes())
                os.chmod(backup_path, 0o600)

            def restore_backup():
                if had_original and backup_path.exists():
                    tmp_restore = target_path.with_suffix('.restore.tmp')
                    tmp_restore.write_bytes(backup_path.read_bytes())
                    os.replace(tmp_restore, target_path)
                elif not had_original and target_path.exists():
                    target_path.unlink()

            tmp_write = target_path.with_suffix('.write.tmp')
            tmp_write.write_bytes(payload['rendered_text'].encode('utf-8'))
            os.chmod(tmp_write, 0o644)
            os.replace(tmp_write, target_path)

            probe = _probe_native_config_subprocess(
                runtime_root, host_scope['firebird_lock_directory'],
            )
            if not probe.get('ok'):
                restore_backup()
                return {
                    'state': 'rolled_back_after_validation_failure',
                    'native_dispatched': True,
                    'rolled_back': True,
                    'backup_path': str(backup_path) if had_original else None,
                    'reason': probe.get('stderr', 'Native Firebird config probe failed'),
                }

            daemon_receipt = None
            if payload['lifecycle_action'] == 'restart_managed_daemon':
                restart_res = restart_managed_daemon_process(host_scope)
                if not restart_res.get('ok'):
                    restore_backup()
                    recovery = restart_managed_daemon_process(host_scope)
                    return {
                        'state': 'rolled_back_after_failed_restart',
                        'native_dispatched': True,
                        'rolled_back': True,
                        'backup_path': str(backup_path) if had_original else None,
                        'failed_restart_reason': restart_res.get('reason'),
                        'daemon_recovered': bool(recovery.get('ok')),
                        'recovery_pid': recovery.get('pid'),
                    }
                daemon_receipt = restart_res

            final_bytes = target_path.read_bytes()
            return {
                'state': 'applied',
                'native_dispatched': True,
                'rolled_back': False,
                'target_file': target_file,
                'new_generation_sha256': _sha256_bytes(final_bytes),
                'backup_path': str(backup_path) if had_original else None,
                'restart_required': payload['restart_required'],
                'restart_performed': daemon_receipt is not None,
                'daemon_receipt': daemon_receipt,
                'preserved_sibling_aliases': payload['preserved_sibling_aliases'],
                'native_rdb_config_verified': True,
                'observed_rdb_config': {
                    k: probe['rdb_config'][k]
                    for k in ('WireCrypt', 'DefaultDbCachePages', 'StatementTimeout', 'ConnectionIdleTimeout', 'AuditTraceConfigFile', 'KeyHolderPlugin')
                    if k in (probe.get('rdb_config') or {})
                },
            }
    finally:
        os.close(lock_fd)

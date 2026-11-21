"""PostgreSQL persistent ALTER SYSTEM, effective-vs-file/pending-restart inspection,
and authorized database-host configuration/HBA/TLS lifecycle helpers (PG-AUDIT-CONFIG-01).
"""
from __future__ import annotations

from pathlib import Path
import os
import re
import shutil
import stat
import subprocess

from .native_admin import (
    PostgreSQLNativeAdminError, _flag, _identifier, _literal, _name, _required_text,
)

_PARAM_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,62}(?:\.[A-Za-z_][A-Za-z0-9_]{0,62})?')
PROTECTED_PARAMETERS = frozenset({
    'ssl_passphrase_command',
    'archive_command',
    'restore_command',
    'recovery_end_command',
    'archive_cleanup_command',
    'primary_conninfo',
})


def _param_ident(raw: str) -> tuple[str, str]:
    name = _required_text(raw, 'parameter').lower()
    if not _PARAM_RE.fullmatch(name):
        raise PostgreSQLNativeAdminError('Invalid PostgreSQL configuration parameter name')
    if name in PROTECTED_PARAMETERS:
        raise PostgreSQLNativeAdminError(
            f'Parameter {name!r} carries shell commands or connection secrets; manage it through the authorized host file workflow'
        )
    quoted = '.'.join(_identifier(part, 'parameter') for part in name.split('.'))
    return name, quoted


def observation_query(param_name: str | None = None) -> str:
    where = f' WHERE s.name = {_literal(param_name, "parameter")}' if param_name else ''
    return (
        'SELECT s.name, s.setting AS effective_value, s.unit, s.context, s.vartype, '
        's.source, s.sourcefile, s.sourceline, s.boot_val, s.reset_val, s.pending_restart, '
        'COALESCE((SELECT jsonb_agg(jsonb_build_object('
        "'sourcefile', f.sourcefile, 'sourceline', f.sourceline, 'seqno', f.seqno, "
        "'value', f.setting, 'applied', f.applied, 'error', f.error"
        ') ORDER BY f.seqno) FROM pg_catalog.pg_file_settings f WHERE f.name = s.name), \'[]\'::jsonb) AS file_entries '
        f'FROM pg_catalog.pg_settings s{where} ORDER BY s.pending_restart DESC, s.name LIMIT 500'
    )


def compile_operation(operation: str, _native: dict, draft: dict) -> dict:
    if operation == 'inspect-configuration':
        category = str(draft.get('scope') or 'settings').strip().lower()
        param_filter = str(draft.get('parameter') or '').strip().lower() or None
        if param_filter and not _PARAM_RE.fullmatch(param_filter):
            raise PostgreSQLNativeAdminError('Invalid parameter filter')
        if category == 'settings':
            stmt = observation_query(param_filter)
        elif category == 'pending_restart':
            stmt = (
                'SELECT name, setting AS effective_value, unit, context, sourcefile, sourceline, pending_restart '
                'FROM pg_catalog.pg_settings WHERE pending_restart = true ORDER BY name'
            )
        elif category == 'file_errors':
            stmt = (
                'SELECT sourcefile, sourceline, seqno, name, setting, applied, error '
                'FROM pg_catalog.pg_file_settings WHERE error IS NOT NULL OR NOT applied ORDER BY seqno'
            )
        elif category == 'hba_rules':
            stmt = (
                'SELECT rule_number, file_name, line_number, type, database, user_name, address, netmask, auth_method, options, error '
                'FROM pg_catalog.pg_hba_file_rules ORDER BY rule_number'
            )
        elif category == 'ident_mappings':
            stmt = (
                'SELECT map_number, file_name, line_number, map_name, sys_name, pg_username, error '
                'FROM pg_catalog.pg_ident_file_mappings ORDER BY map_number'
            )
        else:
            raise PostgreSQLNativeAdminError('Select settings, pending_restart, file_errors, hba_rules, or ident_mappings')
        return {'statement': stmt, 'read_only': True, 'returns_rows': True}

    if operation == 'alter-system-set':
        canon, quoted = _param_ident(draft.get('parameter'))
        value_mode = str(draft.get('value_mode') or 'VALUE').strip().upper()
        if value_mode not in {'VALUE', 'DEFAULT'}:
            raise PostgreSQLNativeAdminError('value_mode must be VALUE or DEFAULT')
        if value_mode == 'DEFAULT':
            stmt = f'ALTER SYSTEM SET {quoted} TO DEFAULT'
        else:
            val = draft.get('value')
            if val is None or isinstance(val, (dict, list)):
                raise PostgreSQLNativeAdminError('Supply a scalar parameter value')
            if isinstance(val, bool):
                rhs = 'on' if val else 'off'
            elif isinstance(val, int):
                rhs = str(val)
            else:
                rhs = _literal(str(val), 'value')
            stmt = f'ALTER SYSTEM SET {quoted} = {rhs}'
        reload_after = _flag(draft, 'reload_after')
        obs = observation_query(canon)
        out = {
            'statement': stmt,
            'read_only': False,
            'autocommit': True,
            'observation_statement': obs,
            'maintenance': {
                'action': 'alter-system-set',
                'object_kind': 'server',
                'object': canon,
                'options': ['RELOAD'] if reload_after else [],
                'transaction_mode': 'autocommit',
            },
        }
        if reload_after:
            out['reload_conf'] = True
        return out

    if operation == 'alter-system-reset':
        canon, quoted = _param_ident(draft.get('parameter'))
        if _name(draft.get('confirmation'), 'confirmation').lower() != canon:
            raise PostgreSQLNativeAdminError('Confirm the exact parameter name to reset')
        reload_after = _flag(draft, 'reload_after')
        out = {
            'statement': f'ALTER SYSTEM RESET {quoted}',
            'read_only': False,
            'autocommit': True,
            'observation_statement': observation_query(canon),
            'maintenance': {
                'action': 'alter-system-reset',
                'object_kind': 'server',
                'object': canon,
                'options': ['RELOAD'] if reload_after else [],
                'transaction_mode': 'autocommit',
            },
        }
        if reload_after:
            out['reload_conf'] = True
        return out

    if operation == 'alter-system-reset-all':
        if draft.get('confirmation') != 'RESET ALL':
            raise PostgreSQLNativeAdminError('Type RESET ALL to confirm clearing postgresql.auto.conf')
        reload_after = _flag(draft, 'reload_after')
        out = {
            'statement': 'ALTER SYSTEM RESET ALL',
            'read_only': False,
            'autocommit': True,
            'maintenance': {
                'action': 'alter-system-reset-all',
                'object_kind': 'server',
                'object': 'postgresql.auto.conf',
                'options': ['RELOAD'] if reload_after else [],
                'transaction_mode': 'autocommit',
            },
        }
        if reload_after:
            out['reload_conf'] = True
        return out

    raise PostgreSQLNativeAdminError(f'Unsupported PostgreSQL configuration operation: {operation!r}')


def form(operation: str, field) -> dict:
    if operation == 'inspect-configuration':
        return {
            'form_id': 'postgresql-server-inspect-configuration',
            'form_key': 'native:postgresql:server:configuration',
            'title': 'Inspect server configuration, pending restarts & HBA rules',
            'fields': [
                field('scope', 'Inspection view', 'select', default='settings', options=[
                    {'value': 'settings', 'label': 'Effective vs file settings (pg_settings + pg_file_settings)'},
                    {'value': 'pending_restart', 'label': 'Parameters pending postmaster restart'},
                    {'value': 'file_errors', 'label': 'Configuration file errors & unapplied entries'},
                    {'value': 'hba_rules', 'label': 'Client authentication rules (pg_hba_file_rules)'},
                    {'value': 'ident_mappings', 'label': 'User-name maps (pg_ident_file_mappings)'},
                ]),
                field('parameter', 'Filter by parameter name (optional)'),
            ],
        }
    if operation == 'alter-system-set':
        return {
            'form_id': 'postgresql-server-alter-system-set',
            'form_key': 'native:postgresql:server:configuration',
            'title': 'Persist parameter via ALTER SYSTEM SET',
            'fields': [
                field('parameter', 'Parameter name', required=True),
                field('value_mode', 'Value mode', 'select', default='VALUE', options=[
                    {'value': 'VALUE', 'label': 'Explicit value'},
                    {'value': 'DEFAULT', 'label': 'Reset to compiled/file DEFAULT'},
                ]),
                field('value', 'Value', visible_when={'field': 'value_mode', 'field_id': 'value_mode', 'equals': 'VALUE'}),
                field('reload_after', 'Reload server configuration (pg_reload_conf) after write', 'boolean', default=True),
            ],
        }
    if operation == 'alter-system-reset':
        return {
            'form_id': 'postgresql-server-alter-system-reset',
            'form_key': 'native:postgresql:server:configuration',
            'title': 'Reset persisted parameter (ALTER SYSTEM RESET)',
            'fields': [
                field('parameter', 'Parameter name', required=True),
                field('reload_after', 'Reload server configuration (pg_reload_conf) after reset', 'boolean', default=True),
                field('confirmation', 'Type the parameter name to confirm', required=True),
            ],
        }
    return {
        'form_id': 'postgresql-server-alter-system-reset-all',
        'form_key': 'native:postgresql:server:configuration',
        'title': 'Clear all persisted parameters (ALTER SYSTEM RESET ALL)',
        'fields': [
            field('reload_after', 'Reload server configuration (pg_reload_conf) after reset', 'boolean', default=True),
            field('confirmation', 'Type RESET ALL to confirm', required=True),
        ],
    }


# -- Authorized host configuration / HBA / TLS file helpers -------------------

ADMITTED_CLUSTER_FILES = frozenset({
    'postgresql.conf',
    'postgresql.auto.conf',
    'pg_hba.conf',
    'pg_ident.conf',
    'server.crt',
    'server.key',
    'root.crt',
})


def resolve_cluster_file(cluster_dir: str | Path, file_kind: str) -> Path:
    if file_kind not in ADMITTED_CLUSTER_FILES:
        raise PostgreSQLNativeAdminError(f'Unsupported PostgreSQL cluster file kind: {file_kind!r}')
    cdir = Path(cluster_dir)
    if not cdir.is_absolute() or cdir.resolve(strict=True) != cdir:
        raise PostgreSQLNativeAdminError('Cluster directory must be an exact canonical path without symlinks')
    if not (cdir / 'PG_VERSION').is_file():
        raise PostgreSQLNativeAdminError('Target directory is not an initialized PostgreSQL data directory')
    target = cdir / file_kind
    if target.exists() and target.is_symlink():
        raise PostgreSQLNativeAdminError('Symlinked PostgreSQL configuration/certificate files are refused')
    return target


def validate_host_file_content(
    postgres_binary: str,
    cluster_dir: str | Path,
    file_kind: str,
    content: str,
) -> dict:
    if not isinstance(content, str) or '\x00' in content or len(content.encode('utf-8')) > 2 * 1024 * 1024:
        raise PostgreSQLNativeAdminError('Supply NUL-free UTF-8 configuration/PEM text up to 2 MiB')
    if file_kind in {'server.crt', 'root.crt'}:
        if '-----BEGIN CERTIFICATE-----' not in content or '-----END CERTIFICATE-----' not in content:
            raise PostgreSQLNativeAdminError(f'{file_kind} must contain a valid PEM X.509 certificate block')
        return {'valid': True, 'validator': 'pem-x509-envelope', 'file_kind': file_kind}
    if file_kind == 'server.key':
        if 'PRIVATE KEY-----' not in content:
            raise PostgreSQLNativeAdminError('server.key must contain a PEM private key block')
        return {'valid': True, 'validator': 'pem-private-key-envelope', 'file_kind': file_kind, 'mode_required': '0600'}
    if file_kind == 'postgresql.conf':
        # Validate GUC names/syntax via `postgres -C shared_buffers --config-file=<staged>`
        import tempfile
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', suffix='.conf', delete=False) as tf:
            os.chmod(tf.name, 0o600)
            tf.write(content if content.endswith('\n') else content + '\n')
            tmp_conf = tf.name
        try:
            proc = subprocess.run(
                [postgres_binary, '-D', str(cluster_dir), f'--config-file={tmp_conf}', '-C', 'data_directory'],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or 'postgres -C rejected configuration').strip()
                raise PostgreSQLNativeAdminError(f'Native postgres -C rejected postgresql.conf: {err}')
            return {'valid': True, 'validator': 'postgres -C', 'file_kind': file_kind}
        finally:
            Path(tmp_conf).unlink(missing_ok=True)
    # pg_hba.conf / pg_ident.conf basic line syntax check (non-comment lines have >= 3 or >= 4 tokens)
    min_tokens = 3 if file_kind == 'pg_ident.conf' else 4
    for lineno, raw_line in enumerate(content.splitlines(), 1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith('#') or stripped.startswith('include'):
            continue
        if len(stripped.split()) < min_tokens:
            raise PostgreSQLNativeAdminError(f'{file_kind} line {lineno} has fewer than {min_tokens} fields')
    return {'valid': True, 'validator': f'{file_kind}-syntax', 'file_kind': file_kind}


def deploy_cluster_file_with_backup(
    cluster_dir: str | Path,
    file_kind: str,
    content: str,
    backup_dir: str | Path,
) -> dict:
    target = resolve_cluster_file(cluster_dir, file_kind)
    bdir = Path(backup_dir)
    bdir.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup_path = bdir / f'{file_kind}.prev'
    existed = target.exists()
    if existed:
        shutil.copy2(target, backup_path)
        os.chmod(backup_path, 0o600)
    (bdir / 'meta.txt').write_text(f'{target}\n{"1" if existed else "0"}\n', encoding='utf-8')
    tmp = target.parent / f'.sr-tmp-{os.getpid()}-{file_kind}'
    data = (content if content.endswith('\n') else content + '\n').encode('utf-8')
    with tmp.open('wb') as fh:
        os.chmod(tmp, 0o600)
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, target)
    os.chmod(target, 0o600 if file_kind == 'server.key' else 0o600)
    return {
        'deployed_path': str(target),
        'existed_before': existed,
        'backup_path': str(backup_path) if existed else None,
        'mode_octal': oct(stat.S_IMODE(target.stat().st_mode)),
    }


def rollback_cluster_file(backup_dir: str | Path) -> dict:
    bdir = Path(backup_dir)
    meta_file = bdir / 'meta.txt'
    if not meta_file.is_file():
        raise PostgreSQLNativeAdminError('No configuration deployment backup metadata found for this job')
    lines = meta_file.read_text(encoding='utf-8').splitlines()
    target = Path(lines[0])
    existed = lines[1] == '1'
    backup_path = bdir / f'{target.name}.prev'
    if existed:
        if not backup_path.is_file():
            raise PostgreSQLNativeAdminError('Saved previous configuration file is missing')
        shutil.copy2(backup_path, target)
        os.chmod(target, 0o600)
        return {'rolled_back_path': str(target), 'restored_previous': True}
    target.unlink(missing_ok=True)
    return {'rolled_back_path': str(target), 'removed_newly_created': True}

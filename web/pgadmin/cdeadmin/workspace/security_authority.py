##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Unified Multi-Engine Principal & Object-Grant Security Authority.

Mounts ``/cdeadmin/api/security`` with 5 endpoints:
- ``GET  /cdeadmin/api/security/principals``
- ``POST /cdeadmin/api/security/principal/plan``
- ``POST /cdeadmin/api/security/principal/apply``
- ``GET  /cdeadmin/api/security/object_grants``
- ``POST /cdeadmin/api/security/object_grants/plan``
- ``POST /cdeadmin/api/security/object_grants/apply``

Enforces native server-vs-database principal placement, strict per-dialect
identifier/literal escaping, password redaction in all plan/preview responses,
and graceful non-DBA visibility degradation instead of HTTP 500 errors.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from typing import Any, Callable, Mapping

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user

SECURITY_AUTHORITY_EXTENSION_KEY = 'cdeadmin_security_authority_host'
_SERVER_SCOPE_SENTINEL = 'cdeadmin-server-scope'

EMBEDDED_UNSUPPORTED_ENGINES = frozenset({'sqlite', 'duckdb'})

FIREBIRD_SYSTEM_PRIVILEGES = (
    'USER_MANAGEMENT',
    'READ_RAW_PAGES',
    'CREATE_USER_TYPES',
    'USE_NBACKUP_UTILITY',
    'CHANGE_SHUTDOWN_MODE',
    'TRACE_ANY_ATTACHMENT',
    'MONITOR_ANY_ATTACHMENT',
    'ACCESS_SHUTDOWN_DATABASE',
    'CREATE_DATABASE',
    'DROP_DATABASE',
    'USE_GBAK_UTILITY',
    'USE_GSTAT_UTILITY',
    'USE_GFIX_UTILITY',
    'IGNORE_DB_TRIGGERS',
    'CHANGE_HEADER_SETTINGS',
    'SELECT_ANY_OBJECT_IN_DATABASE',
    'ACCESS_ANY_OBJECT_IN_DATABASE',
    'MODIFY_ANY_OBJECT_IN_DATABASE',
    'CHANGE_MAPPING_RULES',
    'USE_GRANTED_BY_CLAUSE',
    'GRANT_REVOKE_ON_ANY_OBJECT',
    'GRANT_REVOKE_ANY_DDL_RIGHT',
    'CREATE_PRIVILEGED_ROLES',
    'GET_DBCRYPT_INFO',
    'MODIFY_EXT_CONN_POOL',
    'REPLICATE_INTO_DATABASE',
    'PROFILE_ANY_ATTACHMENT',
)

POSTGRESQL_SYSTEM_PRIVILEGES = (
    'SUPERUSER',
    'CREATEDB',
    'CREATEROLE',
    'INHERIT',
    'LOGIN',
    'REPLICATION',
    'BYPASSRLS',
)

MYSQL_SYSTEM_PRIVILEGES = (
    'SELECT',
    'INSERT',
    'UPDATE',
    'DELETE',
    'CREATE',
    'DROP',
    'RELOAD',
    'SHUTDOWN',
    'PROCESS',
    'FILE',
    'REFERENCES',
    'INDEX',
    'ALTER',
    'SHOW DATABASES',
    'SUPER',
    'CREATE TEMPORARY TABLES',
    'LOCK TABLES',
    'EXECUTE',
    'REPLICATION SLAVE',
    'REPLICATION CLIENT',
    'CREATE VIEW',
    'SHOW VIEW',
    'CREATE ROUTINE',
    'ALTER ROUTINE',
    'CREATE USER',
    'EVENT',
    'TRIGGER',
    'CREATE TABLESPACE',
    'CREATE ROLE',
    'DROP ROLE',
)

_PRIVILEGE_TOKEN_RE = re.compile(r'^[A-Z][A-Z0-9_]*(?: [A-Z][A-Z0-9_]*)*$')
_VALID_UNTIL_RE = re.compile(r'^[0-9A-Za-z :+./T_-]{1,64}$')

OBJECT_GRANT_PRIVILEGES: dict[str, dict[str, tuple[str, ...]]] = {
    'postgresql': {
        'table': ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER', 'MAINTAIN'),
        'view': ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'),
        'sequence': ('USAGE', 'SELECT', 'UPDATE'),
        'function': ('EXECUTE',),
        'procedure': ('EXECUTE',),
        'type': ('USAGE',),
        'domain': ('USAGE',),
        'schema': ('USAGE', 'CREATE'),
        'database': ('CREATE', 'CONNECT', 'TEMPORARY'),
    },
    'firebird': {
        'table': ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'REFERENCES'),
        'view': ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'REFERENCES'),
        'procedure': ('EXECUTE',),
        'function': ('EXECUTE',),
        'package': ('EXECUTE',),
        'sequence': ('USAGE',),
        'database': ('CREATE', 'ALTER', 'DROP'),
    },
    'mysql': {
        'database': (
            'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP',
            'REFERENCES', 'INDEX', 'ALTER', 'CREATE TEMPORARY TABLES',
            'LOCK TABLES', 'EXECUTE', 'CREATE VIEW', 'SHOW VIEW',
            'CREATE ROUTINE', 'ALTER ROUTINE', 'EVENT', 'TRIGGER',
        ),
        'schema': (
            'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP',
            'REFERENCES', 'INDEX', 'ALTER', 'CREATE TEMPORARY TABLES',
            'LOCK TABLES', 'EXECUTE', 'CREATE VIEW', 'SHOW VIEW',
            'CREATE ROUTINE', 'ALTER ROUTINE', 'EVENT', 'TRIGGER',
        ),
        'table': (
            'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP',
            'REFERENCES', 'INDEX', 'ALTER', 'CREATE VIEW', 'SHOW VIEW', 'TRIGGER',
        ),
        'view': (
            'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP',
            'REFERENCES', 'ALTER', 'SHOW VIEW',
        ),
        'procedure': ('EXECUTE', 'ALTER ROUTINE'),
        'function': ('EXECUTE', 'ALTER ROUTINE'),
    },
    'mariadb': {
        'database': (
            'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP',
            'REFERENCES', 'INDEX', 'ALTER', 'CREATE TEMPORARY TABLES',
            'LOCK TABLES', 'EXECUTE', 'CREATE VIEW', 'SHOW VIEW',
            'CREATE ROUTINE', 'ALTER ROUTINE', 'EVENT', 'TRIGGER',
        ),
        'schema': (
            'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP',
            'REFERENCES', 'INDEX', 'ALTER', 'CREATE TEMPORARY TABLES',
            'LOCK TABLES', 'EXECUTE', 'CREATE VIEW', 'SHOW VIEW',
            'CREATE ROUTINE', 'ALTER ROUTINE', 'EVENT', 'TRIGGER',
        ),
        'table': (
            'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP',
            'REFERENCES', 'INDEX', 'ALTER', 'CREATE VIEW', 'SHOW VIEW', 'TRIGGER',
        ),
        'view': (
            'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP',
            'REFERENCES', 'ALTER', 'SHOW VIEW',
        ),
        'sequence': ('SELECT', 'INSERT', 'DELETE', 'ALTER', 'DROP'),
        'procedure': ('EXECUTE', 'ALTER ROUTINE'),
        'function': ('EXECUTE', 'ALTER ROUTINE'),
        'package': ('EXECUTE', 'ALTER ROUTINE'),
    },
}

COLUMN_PRIVILEGE_SUPPORT: dict[str, dict[str, frozenset[str]]] = {
    'postgresql': {
        'table': frozenset({'SELECT', 'INSERT', 'UPDATE', 'REFERENCES'}),
        'view': frozenset({'SELECT', 'INSERT', 'UPDATE', 'REFERENCES'}),
    },
    'firebird': {
        'table': frozenset({'UPDATE', 'REFERENCES'}),
        'view': frozenset({'UPDATE', 'REFERENCES'}),
    },
    'mysql': {
        'table': frozenset({'SELECT', 'INSERT', 'UPDATE', 'REFERENCES'}),
        'view': frozenset({'SELECT', 'INSERT', 'UPDATE', 'REFERENCES'}),
    },
    'mariadb': {
        'table': frozenset({'SELECT', 'INSERT', 'UPDATE', 'REFERENCES'}),
        'view': frozenset({'SELECT', 'INSERT', 'UPDATE', 'REFERENCES'}),
    },
}


class SecurityAuthorityError(ValueError):
    """Raised when a security DCL compilation or validation fails."""


def _dialect_family(engine: str) -> str:
    eng = str(engine or '').strip().lower()
    if eng in {'postgresql', 'cockroachdb', 'yugabytedb'}:
        return 'postgresql'
    if eng in {'mysql', 'tidb', 'dolt'}:
        return 'mysql'
    if eng == 'mariadb':
        return 'mariadb'
    if eng == 'firebird':
        return 'firebird'
    return eng


def _require_non_empty_text(value: Any, label: str, max_len: int = 255) -> str:
    if not isinstance(value, str) or not value or '\x00' in value:
        raise SecurityAuthorityError(f'{label} must be a non-empty string without NUL bytes')
    if len(value) > max_len:
        raise SecurityAuthorityError(f'{label} exceeds maximum length ({max_len})')
    return value


def quote_identifier(ident: Any, engine: str, label: str = 'identifier') -> str:
    """Strictly quote a SQL identifier for the target engine dialect."""
    fam = _dialect_family(engine)
    max_len = 63 if fam == 'firebird' else 128
    raw = _require_non_empty_text(ident, label, max_len=max_len)
    if fam in {'mysql', 'mariadb'}:
        if '\n' in raw or '\r' in raw:
            raise SecurityAuthorityError(f'{label} must not contain newline characters')
        return '`' + raw.replace('`', '``') + '`'
    return '"' + raw.replace('"', '""') + '"'


def quote_literal(value: Any, engine: str, label: str = 'literal') -> str:
    """Strictly quote a SQL text literal for the target engine dialect."""
    if not isinstance(value, str) or '\x00' in value:
        raise SecurityAuthorityError(f'{label} must be text without NUL bytes')
    fam = _dialect_family(engine)
    if fam == 'postgresql':
        if '\\' in value:
            return "E'" + value.replace('\\', '\\\\').replace("'", "''") + "'"
        return "'" + value.replace("'", "''") + "'"
    if fam in {'mysql', 'mariadb'}:
        escaped = (
            value
            .replace('\\', '\\\\')
            .replace("'", "''")
            .replace('\n', '\\n')
            .replace('\r', '\\r')
        )
        return "'" + escaped + "'"
    # Firebird standard SQL literal
    return "'" + value.replace("'", "''") + "'"


def parse_mysql_grantee_string(grantee: str, default_host: str = '%') -> tuple[str, str]:
    """Parse `'user'@'host'`, `user@host`, or bare `user` safely."""
    raw = str(grantee or '').strip()
    if not raw or '\x00' in raw:
        raise SecurityAuthorityError('Grantee name is required')
    if raw.startswith("'") and '@' in raw:
        try:
            from pgadmin.cdeadmin.providers.mysql_grants import grantee as decode_grantee
            return decode_grantee(raw)
        except Exception:
            pass
    if '@' in raw and raw.count('@') == 1:
        u, h = raw.split('@', 1)
        return u.strip("'`"), (h.strip("'`") or default_host)
    return raw, default_host


def format_mysql_account(user: Any, host: Any = '%', engine: str = 'mysql') -> str:
    u = _require_non_empty_text(user, 'account user', max_len=96)
    h = _require_non_empty_text(host if host not in (None, '') else '%', 'account host', max_len=255)
    return f"{quote_literal(u, engine, 'user')}@{quote_literal(h, engine, 'host')}"


def _is_permission_denied_error(exc: Exception) -> bool:
    errno = getattr(exc, 'errno', None)
    sqlstate = str(getattr(exc, 'sqlstate', '') or '')
    sqlcode = getattr(exc, 'sqlcode', None)
    msg = str(exc).lower()
    if errno in {1044, 1045, 1142, 1143, 1227}:
        return True
    if sqlstate in {'42501', '28000'}:
        return True
    if sqlcode == -551:
        return True
    for marker in (
        'command denied', 'permission denied', 'no permission for',
        'insufficient privilege', 'access denied', 'lack of privilege',
    ):
        if marker in msg:
            return True
    return False


def _decode_firebird_role_privs(raw_value: Any) -> list[str]:
    if not raw_value:
        return []
    if isinstance(raw_value, (bytes, bytearray, memoryview)):
        buf = bytes(raw_value)
    elif isinstance(raw_value, str):
        try:
            buf = bytes.fromhex(raw_value)
        except ValueError:
            buf = raw_value.encode('latin1', errors='ignore')
    else:
        return []
    found = []
    for bit_index, priv_name in enumerate(FIREBIRD_SYSTEM_PRIVILEGES, start=1):
        byte_idx = bit_index // 8
        bit_mask = 1 << (bit_index % 8)
        if byte_idx < len(buf) and (buf[byte_idx] & bit_mask):
            found.append(priv_name)
    return found


def compile_principal_plan(
    engine: str,
    principal_kind: str,
    operation: str,
    target: Mapping[str, Any] | None,
    draft: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Compile native principal DCL returning executable & redacted preview SQL.

    Returns ``{'exec_statements': [...], 'preview_statements': [...], 'preview_sql': '...', 'warnings': [...]}``.
    """
    fam = _dialect_family(engine)
    if fam in EMBEDDED_UNSUPPORTED_ENGINES:
        raise SecurityAuthorityError(f'{engine} does not support SQL users or roles')
    kind = str(principal_kind or '').strip().lower()
    if kind not in {'user', 'role'}:
        raise SecurityAuthorityError('principal_kind must be user or role')
    op = str(operation or '').strip().lower()
    if op not in {'create', 'alter', 'drop'}:
        raise SecurityAuthorityError('operation must be create, alter, or drop')
    target_map = dict(target or {})
    draft_map = dict(draft or {})

    exec_stmts: list[str] = []
    prev_stmts: list[str] = []
    warnings: list[str] = []

    def emit(exec_sql: str, prev_sql: str | None = None) -> None:
        exec_stmts.append(exec_sql)
        prev_stmts.append(exec_sql if prev_sql is None else prev_sql)

    # ------------------------------------------------------------------
    # Firebird 5
    # ------------------------------------------------------------------
    if fam == 'firebird':
        if kind == 'user':
            raw_name = draft_map.get('name') if op == 'create' else (target_map.get('name') or draft_map.get('name'))
            q_user = quote_identifier(raw_name, 'firebird', 'user name')
            plugin = (
                draft_map.get('plugin')
                if op == 'create'
                else (target_map.get('plugin') or draft_map.get('plugin'))
            )
            plugin_sql = (
                ' USING PLUGIN ' + quote_identifier(str(plugin).strip(), 'firebird', 'plugin')
                if isinstance(plugin, str) and plugin.strip()
                else ''
            )
            if op == 'drop':
                emit(f'DROP USER {q_user}{plugin_sql}')
            else:
                exec_clauses: list[str] = []
                prev_clauses: list[str] = []
                pwd = draft_map.get('password')
                if op == 'create':
                    if not isinstance(pwd, str) or not pwd:
                        raise SecurityAuthorityError('Firebird CREATE USER requires a non-empty password')
                    exec_clauses.append('PASSWORD ' + quote_literal(pwd, 'firebird', 'password'))
                    prev_clauses.append("PASSWORD '<redacted>'")
                elif isinstance(pwd, str) and pwd != '':
                    exec_clauses.append('PASSWORD ' + quote_literal(pwd, 'firebird', 'password'))
                    prev_clauses.append("PASSWORD '<redacted>'")

                for field_key, kw in (
                    ('first_name', 'FIRSTNAME'),
                    ('middle_name', 'MIDDLENAME'),
                    ('last_name', 'LASTNAME'),
                ):
                    if field_key in draft_map and draft_map[field_key] is not None:
                        val_str = str(draft_map[field_key])
                        if op == 'create' and val_str == '':
                            continue
                        q_val = quote_literal(val_str, 'firebird', field_key)
                        exec_clauses.append(f'{kw} {q_val}')
                        prev_clauses.append(f'{kw} {q_val}')

                if op == 'create':
                    if draft_map.get('is_admin'):
                        exec_clauses.append('GRANT ADMIN ROLE')
                        prev_clauses.append('GRANT ADMIN ROLE')
                    act = 'ACTIVE' if draft_map.get('active', True) else 'INACTIVE'
                    exec_clauses.append(act)
                    prev_clauses.append(act)
                else:
                    if 'is_admin' in draft_map and draft_map['is_admin'] is not None:
                        adm_kw = 'GRANT ADMIN ROLE' if draft_map['is_admin'] else 'REVOKE ADMIN ROLE'
                        exec_clauses.append(adm_kw)
                        prev_clauses.append(adm_kw)
                    if 'active' in draft_map and draft_map['active'] is not None:
                        act_kw = 'ACTIVE' if draft_map['active'] else 'INACTIVE'
                        exec_clauses.append(act_kw)
                        prev_clauses.append(act_kw)

                tags = draft_map.get('tags')
                if isinstance(tags, list) and tags:
                    tag_parts: list[str] = []
                    for tag in tags:
                        if not isinstance(tag, Mapping):
                            raise SecurityAuthorityError('Each Firebird user tag must be an object')
                        tname = str(tag.get('name') or '').strip()
                        if not tname or any(ch in tname for ch in '\r\n='):
                            raise SecurityAuthorityError('Invalid Firebird tag name')
                        qt = quote_identifier(tname, 'firebird', 'tag name')
                        if tag.get('drop'):
                            tag_parts.append(f'DROP {qt}')
                        else:
                            tval = str(tag.get('value') or '')
                            if '\r' in tval or '\n' in tval:
                                raise SecurityAuthorityError('Firebird tag values cannot contain CR or LF')
                            tag_parts.append(f"{qt} = {quote_literal(tval, 'firebird', 'tag value')}")
                    if tag_parts:
                        tag_clause = 'TAGS (' + ', '.join(tag_parts) + ')'
                        exec_clauses.append(tag_clause)
                        prev_clauses.append(tag_clause)

                if exec_clauses:
                    verb = 'CREATE USER' if op == 'create' else 'ALTER USER'
                    emit(
                        f"{verb} {q_user} {' '.join(exec_clauses)}{plugin_sql}",
                        f"{verb} {q_user} {' '.join(prev_clauses)}{plugin_sql}",
                    )

                if 'comment' in draft_map and (op == 'alter' or draft_map.get('comment')):
                    cval = draft_map.get('comment')
                    rhs = 'NULL' if cval in (None, '') else quote_literal(str(cval), 'firebird', 'comment')
                    emit(f'COMMENT ON USER {q_user}{plugin_sql} IS {rhs}')

                for rev_role in draft_map.get('revoke_roles') or ():
                    rname = rev_role.get('role') if isinstance(rev_role, Mapping) else rev_role
                    qr = quote_identifier(rname, 'firebird', 'role')
                    emit(f'REVOKE {qr} FROM USER {q_user}')

                for gr in draft_map.get('grant_roles') or ():
                    rname = gr.get('role') if isinstance(gr, Mapping) else gr
                    admin_opt = bool(gr.get('admin_option')) if isinstance(gr, Mapping) else False
                    def_opt = bool(gr.get('default_role')) if isinstance(gr, Mapping) else False
                    qr = quote_identifier(rname, 'firebird', 'role')
                    default_kw = 'DEFAULT ' if def_opt else ''
                    adm_kw = ' WITH ADMIN OPTION' if admin_opt else ''
                    emit(f'GRANT {default_kw}{qr} TO USER {q_user}{adm_kw}')
        else:
            raw_name = draft_map.get('name') if op == 'create' else (target_map.get('name') or draft_map.get('name'))
            q_role = quote_identifier(raw_name, 'firebird', 'role name')
            if op == 'drop':
                emit(f'DROP ROLE {q_role}')
            else:
                sys_privs = draft_map.get('system_privileges')
                priv_clause = ''
                if isinstance(sys_privs, list):
                    cleaned_privs = []
                    for sp in sys_privs:
                        sp_up = str(sp or '').strip().upper()
                        if sp_up not in FIREBIRD_SYSTEM_PRIVILEGES:
                            raise SecurityAuthorityError(f'Unsupported Firebird system privilege: {sp!r}')
                        cleaned_privs.append(sp_up)
                    if cleaned_privs:
                        priv_clause = ' SET SYSTEM PRIVILEGES TO ' + ', '.join(cleaned_privs)
                    elif op == 'alter':
                        priv_clause = ' DROP SYSTEM PRIVILEGES'
                if op == 'create':
                    emit(f'CREATE ROLE {q_role}{priv_clause}')
                elif priv_clause:
                    emit(f'ALTER ROLE {q_role}{priv_clause}')

                if 'comment' in draft_map and (op == 'alter' or draft_map.get('comment')):
                    cval = draft_map.get('comment')
                    rhs = 'NULL' if cval in (None, '') else quote_literal(str(cval), 'firebird', 'comment')
                    emit(f'COMMENT ON ROLE {q_role} IS {rhs}')

                for rev_m in draft_map.get('revoke_members') or ():
                    mname = rev_m.get('principal', rev_m.get('name')) if isinstance(rev_m, Mapping) else rev_m
                    mkind = (
                        str(rev_m.get('principal_type') or 'USER').upper()
                        if isinstance(rev_m, Mapping) else 'USER'
                    )
                    if mkind not in {'USER', 'ROLE'}:
                        mkind = 'USER'
                    qm = quote_identifier(mname, 'firebird', 'member')
                    emit(f'REVOKE {q_role} FROM {mkind} {qm}')

                for gm in draft_map.get('grant_members') or ():
                    mname = gm.get('principal', gm.get('name')) if isinstance(gm, Mapping) else gm
                    mkind = (
                        str(gm.get('principal_type') or 'USER').upper()
                        if isinstance(gm, Mapping) else 'USER'
                    )
                    if mkind not in {'USER', 'ROLE'}:
                        mkind = 'USER'
                    adm = bool(gm.get('admin_option')) if isinstance(gm, Mapping) else False
                    qm = quote_identifier(mname, 'firebird', 'member')
                    adm_kw = ' WITH ADMIN OPTION' if adm else ''
                    emit(f'GRANT {q_role} TO {mkind} {qm}{adm_kw}')

    # ------------------------------------------------------------------
    # PostgreSQL / CockroachDB / YugabyteDB
    # ------------------------------------------------------------------
    elif fam == 'postgresql':
        raw_name = draft_map.get('name') if op == 'create' else (target_map.get('name') or draft_map.get('name'))
        q_role = quote_identifier(raw_name, engine, 'role name')
        if op == 'drop':
            emit(f'DROP ROLE {q_role}')
        else:
            if op == 'alter' and draft_map.get('name') and draft_map['name'] != raw_name:
                q_new = quote_identifier(draft_map['name'], engine, 'new role name')
                emit(f'ALTER ROLE {q_role} RENAME TO {q_new}')
                q_role = q_new

            sys_set = {
                str(p).strip().upper()
                for p in (draft_map.get('system_privileges') or ())
                if str(p).strip()
            }
            unknown_pg = sys_set - set(POSTGRESQL_SYSTEM_PRIVILEGES)
            if unknown_pg:
                raise SecurityAuthorityError(f'Unsupported PostgreSQL role attribute(s): {sorted(unknown_pg)}')

            exec_opts: list[str] = []
            prev_opts: list[str] = []
            if op == 'create':
                can_login = bool(
                    draft_map.get('active', True) if kind == 'user'
                    else ('LOGIN' in sys_set or draft_map.get('can_login', False))
                )
                if draft_map.get('locked') is True:
                    can_login = False
                exec_opts.append('LOGIN' if can_login else 'NOLOGIN')
                if engine == 'postgresql':
                    is_super = bool(draft_map.get('is_admin') or 'SUPERUSER' in sys_set)
                    exec_opts.append('SUPERUSER' if is_super else 'NOSUPERUSER')
                exec_opts.append('CREATEDB' if 'CREATEDB' in sys_set else 'NOCREATEDB')
                exec_opts.append('CREATEROLE' if 'CREATEROLE' in sys_set else 'NOCREATEROLE')
                if engine == 'postgresql':
                    exec_opts.append('INHERIT' if ('INHERIT' in sys_set or 'system_privileges' not in draft_map) else 'NOINHERIT')
                    exec_opts.append('REPLICATION' if 'REPLICATION' in sys_set else 'NOREPLICATION')
                    exec_opts.append('BYPASSRLS' if 'BYPASSRLS' in sys_set else 'NOBYPASSRLS')
                prev_opts.extend(exec_opts)
            else:
                if 'active' in draft_map and kind == 'user':
                    kw = 'LOGIN' if (draft_map['active'] and not draft_map.get('locked')) else 'NOLOGIN'
                    exec_opts.append(kw)
                    prev_opts.append(kw)
                elif 'locked' in draft_map and draft_map['locked'] is not None:
                    kw = 'NOLOGIN' if draft_map['locked'] else 'LOGIN'
                    exec_opts.append(kw)
                    prev_opts.append(kw)
                if 'is_admin' in draft_map and draft_map['is_admin'] is not None and engine == 'postgresql':
                    kw = 'SUPERUSER' if draft_map['is_admin'] else 'NOSUPERUSER'
                    exec_opts.append(kw)
                    prev_opts.append(kw)
                if 'system_privileges' in draft_map and isinstance(draft_map['system_privileges'], list):
                    for attr_kw in ('CREATEDB', 'CREATEROLE', 'INHERIT', 'REPLICATION', 'BYPASSRLS'):
                        if engine != 'postgresql' and attr_kw in {'INHERIT', 'REPLICATION', 'BYPASSRLS'}:
                            continue
                        kw = attr_kw if attr_kw in sys_set else f'NO{attr_kw}'
                        exec_opts.append(kw)
                        prev_opts.append(kw)

            if 'connection_limit' in draft_map and draft_map['connection_limit'] not in (None, ''):
                conn_lim = int(draft_map['connection_limit'])
                if conn_lim < -1:
                    raise SecurityAuthorityError('connection_limit must be >= -1')
                if op == 'alter' or conn_lim != -1:
                    exec_opts.append(f'CONNECTION LIMIT {conn_lim}')
                    prev_opts.append(f'CONNECTION LIMIT {conn_lim}')

            valid_until = draft_map.get('valid_until')
            if isinstance(valid_until, str) and valid_until.strip():
                vu = valid_until.strip()
                if not _VALID_UNTIL_RE.fullmatch(vu):
                    raise SecurityAuthorityError('Invalid valid_until timestamp format')
                q_vu = quote_literal(vu, engine, 'valid_until')
                exec_opts.append(f'VALID UNTIL {q_vu}')
                prev_opts.append(f'VALID UNTIL {q_vu}')

            pwd = draft_map.get('password')
            if isinstance(pwd, str) and pwd != '':
                exec_opts.append('PASSWORD ' + quote_literal(pwd, engine, 'password'))
                prev_opts.append("PASSWORD '<redacted>'")

            if op == 'create':
                emit(
                    f"CREATE ROLE {q_role} WITH {' '.join(exec_opts)}",
                    f"CREATE ROLE {q_role} WITH {' '.join(prev_opts)}",
                )
            elif exec_opts:
                emit(
                    f"ALTER ROLE {q_role} WITH {' '.join(exec_opts)}",
                    f"ALTER ROLE {q_role} WITH {' '.join(prev_opts)}",
                )

            for rev_r in draft_map.get('revoke_roles') or ():
                rname = rev_r.get('role') if isinstance(rev_r, Mapping) else rev_r
                qr = quote_identifier(rname, engine, 'role')
                emit(f'REVOKE {qr} FROM {q_role}')

            for gr in draft_map.get('grant_roles') or ():
                rname = gr.get('role') if isinstance(gr, Mapping) else gr
                adm = bool(gr.get('admin_option')) if isinstance(gr, Mapping) else False
                qr = quote_identifier(rname, engine, 'role')
                adm_kw = ' WITH ADMIN OPTION' if adm else ''
                emit(f'GRANT {qr} TO {q_role}{adm_kw}')

            for rev_m in draft_map.get('revoke_members') or ():
                mname = rev_m.get('principal', rev_m.get('name')) if isinstance(rev_m, Mapping) else rev_m
                qm = quote_identifier(mname, engine, 'member')
                emit(f'REVOKE {q_role} FROM {qm}')

            for gm in draft_map.get('grant_members') or ():
                mname = gm.get('principal', gm.get('name')) if isinstance(gm, Mapping) else gm
                adm = bool(gm.get('admin_option')) if isinstance(gm, Mapping) else False
                qm = quote_identifier(mname, engine, 'member')
                adm_kw = ' WITH ADMIN OPTION' if adm else ''
                emit(f'GRANT {q_role} TO {qm}{adm_kw}')

            if 'comment' in draft_map and (op == 'alter' or draft_map.get('comment')):
                cval = draft_map.get('comment')
                rhs = 'NULL' if cval in (None, '') else quote_literal(str(cval), engine, 'comment')
                emit(f'COMMENT ON ROLE {q_role} IS {rhs}')

    # ------------------------------------------------------------------
    # MySQL / MariaDB / TiDB / Dolt
    # ------------------------------------------------------------------
    elif fam in {'mysql', 'mariadb'}:
        is_mariadb = fam == 'mariadb'
        raw_name = draft_map.get('name') if op == 'create' else (target_map.get('name') or draft_map.get('name'))
        raw_host = (
            draft_map.get('host', '%')
            if op == 'create'
            else (target_map.get('host') if target_map.get('host') is not None else draft_map.get('host', '%'))
        )
        if kind == 'role' and is_mariadb:
            principal_sql = quote_identifier(raw_name, engine, 'role name')
        else:
            principal_sql = format_mysql_account(raw_name, raw_host, engine)

        if op == 'drop':
            kw = 'ROLE' if kind == 'role' else 'USER'
            emit(f'DROP {kw} {principal_sql}')
        elif kind == 'role':
            if op == 'create':
                emit(f'CREATE ROLE {principal_sql}')
            sys_privs = draft_map.get('system_privileges') or []
            if sys_privs:
                validated_sp = _validate_privilege_list(sys_privs, MYSQL_SYSTEM_PRIVILEGES)
                emit(f"GRANT {', '.join(validated_sp)} ON *.* TO {principal_sql}")
            for rev_r in draft_map.get('revoke_roles') or ():
                r_sql = _format_mysql_role_ref(rev_r, engine, is_mariadb)
                emit(f'REVOKE {r_sql} FROM {principal_sql}')
            for gr in draft_map.get('grant_roles') or ():
                r_sql = _format_mysql_role_ref(gr, engine, is_mariadb)
                adm = bool(gr.get('admin_option')) if isinstance(gr, Mapping) else False
                emit(f'GRANT {r_sql} TO {principal_sql}' + (' WITH ADMIN OPTION' if adm else ''))
            for rev_m in draft_map.get('revoke_members') or ():
                m_sql = _format_mysql_member_ref(rev_m, engine, is_mariadb)
                emit(f'REVOKE {principal_sql} FROM {m_sql}')
            for gm in draft_map.get('grant_members') or ():
                m_sql = _format_mysql_member_ref(gm, engine, is_mariadb)
                adm = bool(gm.get('admin_option')) if isinstance(gm, Mapping) else False
                emit(f'GRANT {principal_sql} TO {m_sql}' + (' WITH ADMIN OPTION' if adm else ''))
        else:
            exec_parts: list[str] = []
            prev_parts: list[str] = []
            pwd = draft_map.get('password')
            plugin = draft_map.get('plugin')
            q_plugin = (
                quote_identifier(str(plugin).strip(), engine, 'plugin')
                if isinstance(plugin, str) and plugin.strip() else None
            )
            if isinstance(pwd, str) and pwd != '':
                q_pwd = quote_literal(pwd, engine, 'password')
                if is_mariadb and q_plugin:
                    exec_parts.append(f'IDENTIFIED VIA {q_plugin} USING PASSWORD({q_pwd})')
                    prev_parts.append(f"IDENTIFIED VIA {q_plugin} USING PASSWORD('<redacted>')")
                elif q_plugin:
                    exec_parts.append(f'IDENTIFIED WITH {q_plugin} BY {q_pwd}')
                    prev_parts.append(f"IDENTIFIED WITH {q_plugin} BY '<redacted>'")
                else:
                    exec_parts.append(f'IDENTIFIED BY {q_pwd}')
                    prev_parts.append("IDENTIFIED BY '<redacted>'")
            elif op == 'create' and q_plugin:
                kw = 'VIA' if is_mariadb else 'WITH'
                exec_parts.append(f'IDENTIFIED {kw} {q_plugin}')
                prev_parts.append(f'IDENTIFIED {kw} {q_plugin}')

            conn_lim = draft_map.get('connection_limit')
            if conn_lim not in (None, '', -1):
                c_int = int(conn_lim)
                if c_int < 0:
                    raise SecurityAuthorityError('MySQL/MariaDB max_user_connections must be >= 0')
                exec_parts.append(f'WITH MAX_USER_CONNECTIONS {c_int}')
                prev_parts.append(f'WITH MAX_USER_CONNECTIONS {c_int}')

            locked_flag: bool | None = None
            if 'locked' in draft_map and draft_map['locked'] is not None:
                locked_flag = bool(draft_map['locked'])
            elif 'active' in draft_map and draft_map['active'] is not None:
                locked_flag = not bool(draft_map['active'])
            if locked_flag is not None and (op == 'alter' or locked_flag is True):
                lock_kw = 'ACCOUNT LOCK' if locked_flag else 'ACCOUNT UNLOCK'
                exec_parts.append(lock_kw)
                prev_parts.append(lock_kw)

            if not is_mariadb and 'comment' in draft_map and (op == 'alter' or draft_map.get('comment')):
                c_txt = str(draft_map.get('comment') or '')
                q_c = quote_literal(c_txt, engine, 'comment')
                exec_parts.append(f'COMMENT {q_c}')
                prev_parts.append(f'COMMENT {q_c}')

            if op == 'create':
                suffix_e = (' ' + ' '.join(exec_parts)) if exec_parts else ''
                suffix_p = (' ' + ' '.join(prev_parts)) if prev_parts else ''
                emit(
                    f'CREATE USER {principal_sql}{suffix_e}',
                    f'CREATE USER {principal_sql}{suffix_p}',
                )
            elif exec_parts:
                emit(
                    f"ALTER USER {principal_sql} {' '.join(exec_parts)}",
                    f"ALTER USER {principal_sql} {' '.join(prev_parts)}",
                )

            sys_privs = draft_map.get('system_privileges') or []
            if sys_privs:
                validated_sp = _validate_privilege_list(sys_privs, MYSQL_SYSTEM_PRIVILEGES)
                adm_kw = ' WITH GRANT OPTION' if draft_map.get('is_admin') else ''
                emit(f"GRANT {', '.join(validated_sp)} ON *.* TO {principal_sql}{adm_kw}")

            for rev_r in draft_map.get('revoke_roles') or ():
                r_sql = _format_mysql_role_ref(rev_r, engine, is_mariadb)
                emit(f'REVOKE {r_sql} FROM {principal_sql}')

            default_roles: list[str] = []
            for gr in draft_map.get('grant_roles') or ():
                r_sql = _format_mysql_role_ref(gr, engine, is_mariadb)
                adm = bool(gr.get('admin_option')) if isinstance(gr, Mapping) else False
                is_def = bool(gr.get('default_role')) if isinstance(gr, Mapping) else False
                emit(f'GRANT {r_sql} TO {principal_sql}' + (' WITH ADMIN OPTION' if adm else ''))
                if is_def:
                    default_roles.append(r_sql)
            if default_roles:
                if is_mariadb:
                    emit(f'SET DEFAULT ROLE {default_roles[0]} FOR {principal_sql}')
                else:
                    emit(f"SET DEFAULT ROLE {', '.join(default_roles)} TO {principal_sql}")
    else:
        raise SecurityAuthorityError(f'Unsupported security engine: {engine!r}')

    if not exec_stmts:
        raise SecurityAuthorityError('Principal security plan contains no changes')

    preview_sql = ';\n'.join(prev_stmts) + ';'
    return {
        'exec_statements': exec_stmts,
        'preview_statements': prev_stmts,
        'statements': list(prev_stmts),
        'preview_sql': preview_sql,
        'warnings': warnings,
    }


def _format_mysql_role_ref(item: Any, engine: str, is_mariadb: bool) -> str:
    if isinstance(item, Mapping):
        rname = str(item.get('role') or item.get('name') or '').strip()
        rhost = item.get('host')
    else:
        rname = str(item or '').strip()
        rhost = None
    if is_mariadb:
        if '@' in rname:
            rname = rname.split('@', 1)[0]
        return quote_identifier(rname, engine, 'role')
    u, h = parse_mysql_grantee_string(rname, default_host=str(rhost or '%'))
    return format_mysql_account(u, h, engine)


def _format_mysql_member_ref(item: Any, engine: str, is_mariadb: bool) -> str:
    if isinstance(item, Mapping):
        pname = str(item.get('principal') or item.get('name') or '').strip()
        phost = item.get('host')
        ptype = str(item.get('principal_type') or 'user').lower()
    else:
        pname = str(item or '').strip()
        phost = None
        ptype = 'user'
    if is_mariadb and ptype == 'role' and '@' not in pname and not phost:
        return quote_identifier(pname, engine, 'role')
    u, h = parse_mysql_grantee_string(pname, default_host=str(phost or '%'))
    return format_mysql_account(u, h, engine)


def _validate_privilege_list(privs: Any, allowed: tuple[str, ...] | frozenset[str]) -> list[str]:
    if not isinstance(privs, (list, tuple)) or not privs:
        raise SecurityAuthorityError('At least one privilege must be specified')
    allowed_set = {p.upper() for p in allowed} | {'ALL', 'ALL PRIVILEGES'}
    cleaned: list[str] = []
    for p in privs:
        token = str(p or '').strip().upper()
        if not token or not _PRIVILEGE_TOKEN_RE.fullmatch(token) or token not in allowed_set:
            raise SecurityAuthorityError(f'Unsupported or invalid privilege: {p!r}')
        if token not in cleaned:
            cleaned.append(token)
    return cleaned


def compile_object_grants_plan(
    engine: str,
    object_kind: str,
    schema: str | None,
    object_name: str,
    changes: list[Mapping[str, Any]],
    *,
    routine_signature: str | None = None,
) -> dict[str, Any]:
    """Compile granular native GRANT / REVOKE statements for one object."""
    fam = _dialect_family(engine)
    if fam in EMBEDDED_UNSUPPORTED_ENGINES:
        raise SecurityAuthorityError(f'{engine} does not support SQL GRANT/REVOKE')
    kind = str(object_kind or '').strip().lower()
    allowed_by_kind = OBJECT_GRANT_PRIVILEGES.get(fam, {})
    if kind not in allowed_by_kind:
        raise SecurityAuthorityError(f'{engine} does not support object grants on {object_kind!r}')
    if not isinstance(changes, list) or not changes:
        raise SecurityAuthorityError('changes must be a non-empty list of grant/revoke actions')

    allowed_privs = allowed_by_kind[kind]
    col_allowed = COLUMN_PRIVILEGE_SUPPORT.get(fam, {}).get(kind, frozenset())
    statements: list[str] = []

    # Build target clause
    target_clause = _compile_object_target_clause(
        fam, engine, kind, schema, object_name, routine_signature=routine_signature
    )

    for change in changes:
        if not isinstance(change, Mapping):
            raise SecurityAuthorityError('Each grant change entry must be an object')
        action = str(change.get('action') or '').strip().lower()
        if action not in {'grant', 'revoke'}:
            raise SecurityAuthorityError('Grant change action must be grant or revoke')
        privs = _validate_privilege_list(change.get('privileges'), allowed_privs)
        cols_raw = change.get('columns') or []
        if not isinstance(cols_raw, list):
            raise SecurityAuthorityError('columns must be a list')
        quoted_cols: list[str] = []
        if cols_raw:
            for p in privs:
                if p not in col_allowed:
                    raise SecurityAuthorityError(
                        f'Column-level {p} is not supported on {engine} {kind}'
                    )
            quoted_cols = [quote_identifier(c, engine, 'column') for c in cols_raw]

        grantee_sql = _compile_grantee_clause(
            fam,
            engine,
            change.get('grantee'),
            change.get('grantee_kind'),
            change.get('grantee_host'),
        )
        grant_opt = bool(change.get('grant_option', False))
        grant_opt_only = bool(change.get('grant_option_only', False))

        col_suffix = f" ({', '.join(quoted_cols)})" if quoted_cols else ''
        priv_items = [f'{p}{col_suffix}' for p in privs]
        priv_sql = ', '.join(priv_items)

        if fam == 'firebird' and kind == 'database':
            # Firebird DDL database syntax: GRANT ALTER DATABASE TO USER "x"
            verb = 'GRANT' if action == 'grant' else 'REVOKE'
            prep = 'TO' if action == 'grant' else 'FROM'
            statements.append(f'{verb} {priv_sql} DATABASE {prep} {grantee_sql}')
            continue

        if action == 'grant':
            wgo = ' WITH GRANT OPTION' if grant_opt else ''
            statements.append(f'GRANT {priv_sql} ON {target_clause} TO {grantee_sql}{wgo}')
        else:
            if grant_opt_only:
                if fam in {'mysql', 'mariadb'}:
                    statements.append(f'REVOKE GRANT OPTION ON {target_clause} FROM {grantee_sql}')
                else:
                    statements.append(f'REVOKE GRANT OPTION FOR {priv_sql} ON {target_clause} FROM {grantee_sql}')
            else:
                statements.append(f'REVOKE {priv_sql} ON {target_clause} FROM {grantee_sql}')

    preview_sql = ';\n'.join(statements) + ';'
    return {
        'statements': statements,
        'preview_sql': preview_sql,
    }


def _compile_object_target_clause(
    fam: str,
    engine: str,
    kind: str,
    schema: str | None,
    object_name: str,
    *,
    routine_signature: str | None = None,
) -> str:
    if fam == 'postgresql':
        if kind == 'database':
            return f"DATABASE {quote_identifier(object_name, engine, 'database')}"
        if kind == 'schema':
            return f"SCHEMA {quote_identifier(object_name or schema, engine, 'schema')}"
        q_name = quote_identifier(object_name, engine, 'object_name')
        qualified = (
            f"{quote_identifier(schema, engine, 'schema')}.{q_name}"
            if isinstance(schema, str) and schema.strip()
            else q_name
        )
        if kind in {'table', 'view'}:
            return f'TABLE {qualified}'
        if kind == 'sequence':
            return f'SEQUENCE {qualified}'
        if kind in {'type', 'domain'}:
            return f'TYPE {qualified}'
        if kind in {'function', 'procedure'}:
            kw = kind.upper()
            sig = f'({routine_signature})' if isinstance(routine_signature, str) else ''
            return f'{kw} {qualified}{sig}'
    if fam == 'firebird':
        if kind == 'database':
            return 'DATABASE'
        q_obj = quote_identifier(object_name, 'firebird', 'object_name')
        fb_kw = 'TABLE' if kind in {'table', 'view'} else kind.upper()
        return f'{fb_kw} {q_obj}'
    if fam in {'mysql', 'mariadb'}:
        if kind in {'database', 'schema'}:
            db_ident = quote_identifier(object_name or schema, engine, 'database')
            return f'{db_ident}.*'
        if not isinstance(schema, str) or not schema.strip():
            raise SecurityAuthorityError('MySQL/MariaDB object grants require schema/database name')
        q_db = quote_identifier(schema.strip(), engine, 'schema')
        q_obj = quote_identifier(object_name, engine, 'object_name')
        if kind in {'procedure', 'function', 'package'}:
            return f'{kind.upper()} {q_db}.{q_obj}'
        return f'{q_db}.{q_obj}'
    raise SecurityAuthorityError(f'Unsupported target clause for {engine} {kind}')


def _compile_grantee_clause(
    fam: str,
    engine: str,
    grantee: Any,
    grantee_kind: Any,
    grantee_host: Any,
) -> str:
    g_name = _require_non_empty_text(grantee, 'grantee')
    g_kind = str(grantee_kind or 'role').strip().lower()
    if fam in {'postgresql', 'firebird'}:
        if g_kind == 'special' or g_name.upper() == 'PUBLIC':
            return 'PUBLIC'
        if fam == 'firebird':
            fb_prefix = 'ROLE' if g_kind == 'role' else 'USER'
            return f"{fb_prefix} {quote_identifier(g_name, 'firebird', 'grantee')}"
        return quote_identifier(g_name, engine, 'grantee')
    if fam == 'mariadb' and g_kind == 'role' and not grantee_host and '@' not in g_name:
        return quote_identifier(g_name, engine, 'grantee role')
    u, h = parse_mysql_grantee_string(
        g_name,
        default_host=str(grantee_host if grantee_host not in (None, '') else '%'),
    )
    return format_mysql_account(u, h, engine)


def normalize_grants_matrix(
    raw_entries: list[Mapping[str, Any]],
    supported_privileges: tuple[str, ...] | list[str],
) -> list[dict[str, Any]]:
    """Aggregate flat privilege rows into per-grantee privilege matrices."""
    by_grantee: dict[tuple[str, str, str | None], dict[str, Any]] = {}
    supported_list = [str(p).upper() for p in supported_privileges]

    for row in raw_entries:
        grantee = str(row.get('grantee') or '').strip()
        if not grantee:
            continue
        g_kind = str(row.get('grantee_kind') or ('special' if grantee.upper() == 'PUBLIC' else 'role'))
        g_host = row.get('grantee_host')
        grantor = str(row.get('grantor') or '')
        priv = str(row.get('privilege') or '').strip().upper()
        if not priv:
            continue
        grant_opt = bool(row.get('grant_option', False))
        col = row.get('column')

        key = (grantee, g_kind, g_host)
        if key not in by_grantee:
            by_grantee[key] = {
                'grantee': grantee,
                'grantee_kind': g_kind,
                'grantee_host': g_host,
                'grantor': grantor,
                'privileges': {
                    sp: {'granted': False, 'grant_option': False, 'columns': []}
                    for sp in supported_list
                },
            }
        entry = by_grantee[key]
        if grantor and not entry['grantor']:
            entry['grantor'] = grantor
        cell = entry['privileges'].setdefault(
            priv, {'granted': False, 'grant_option': False, 'columns': []}
        )
        if col:
            if col not in cell['columns']:
                cell['columns'].append(str(col))
            if grant_opt:
                cell['grant_option'] = True
        else:
            cell['granted'] = True
            if grant_opt:
                cell['grant_option'] = True

    return sorted(by_grantee.values(), key=lambda g: (g['grantee'].casefold(), str(g['grantee_host'] or '')))


# --------------------------------------------------------------------------
# SecurityAuthorityHost
# --------------------------------------------------------------------------


def _actor_user_id() -> int:
    try:
        if current_user and getattr(current_user, 'is_authenticated', False):
            return int(current_user.id)
    except Exception:
        pass
    return 1


def _resolve_server_record(sid: int):
    if not sid or int(sid) <= 0:
        return None
    try:
        from pgadmin.model import Server
        uid = _actor_user_id()
        srv = Server.query.filter_by(id=int(sid), user_id=uid).first()
        if srv is not None:
            return srv
        srv = Server.query.filter_by(id=int(sid)).first()
        if srv is not None and getattr(srv, 'shared', False):
            return srv
    except Exception:
        pass
    return None


class SecurityAuthorityHost:
    """Backend service backing `/cdeadmin/api/security`."""

    def __init__(self, app, workspace_service=None):
        self.app = app
        self.workspace_service = workspace_service
        self._test_servers: dict[int, dict[str, Any]] = {}

    def register_test_server(
        self,
        sid: int,
        engine_id: str,
        connect_fn: Callable[[str | None], Any] | None = None,
        *,
        route_kind: str = 'network',
    ) -> None:
        """Register an in-memory/mocked or live test server adapter by sid."""
        self._test_servers[int(sid)] = {
            'engine_id': engine_id.lower(),
            'route_kind': route_kind,
            'connect_fn': connect_fn,
        }

    def _resolve_target_info(self, sid: int) -> dict[str, Any]:
        if int(sid) in self._test_servers:
            spec = self._test_servers[int(sid)]
            return {
                'sid': int(sid),
                'engine_id': spec['engine_id'],
                'route_kind': spec['route_kind'],
                'workflow': 'test',
                'server': None,
                'connect_fn': spec['connect_fn'],
            }
        server = _resolve_server_record(sid)
        if server is None:
            raise LookupError(f'Server {sid} was not found or is not accessible')
        ep = getattr(server, 'endpoint_profile', None)
        if ep is not None and getattr(ep, 'provider_version', None) is not None:
            from pgadmin.cdeadmin.endpoints import registration_profile_for_endpoint
            prof = registration_profile_for_endpoint(ep)
            if prof.get('workflow') == 'provider_endpoint' and str(prof.get('engine_id') or '').lower() != 'postgresql':
                return {
                    'sid': int(sid),
                    'engine_id': str(prof['engine_id']).lower(),
                    'route_kind': str(prof.get('route_kind') or 'network'),
                    'workflow': 'provider_endpoint',
                    'server': server,
                    'profile': prof,
                }
        return {
            'sid': int(sid),
            'engine_id': 'postgresql',
            'route_kind': 'network',
            'workflow': 'legacy_pg',
            'server': server,
        }

    @contextmanager
    def _open_connection(self, info: Mapping[str, Any], database_target_id: str | None, *, write: bool = False):
        """Yield a `(query_fn, exec_fn)` pair against the target server/database."""
        norm_target = (
            None
            if database_target_id in (None, '', _SERVER_SCOPE_SENTINEL)
            else str(database_target_id)
        )
        if info['workflow'] == 'test':
            connect_fn = info.get('connect_fn')
            if connect_fn is None:
                raise RuntimeError('No connection factory configured for test server')
            conn = connect_fn(norm_target)
            try:
                yield self._wrap_dbapi_connection(conn, info['engine_id'], write=write)
            finally:
                close = getattr(conn, 'close', None)
                if callable(close):
                    close()
            return

        server = info['server']
        if write and getattr(server, 'shared', False) and getattr(server, 'user_id', None) != _actor_user_id():
            raise PermissionError('Only the server owner may apply security changes')

        if info['workflow'] == 'legacy_pg':
            from config import PG_DEFAULT_DRIVER
            from pgadmin.utils.driver import get_driver
            manager = get_driver(PG_DEFAULT_DRIVER).connection_manager(info['sid'])
            did = None
            if norm_target:
                if norm_target.startswith('postgresql-database:'):
                    did = int(norm_target.split(':', 1)[1])
                elif norm_target.isdigit():
                    did = int(norm_target)
            conn = manager.connection(did=did) if did is not None else manager.connection()
            if not conn.connected():
                ok, msg = conn.connect()
                if not ok:
                    raise RuntimeError(str(msg))

            def pg_query(sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
                status, res = conn.execute_dict(sql, list(params) if params else None)
                if not status:
                    err = RuntimeError(str(res))
                    m = re.search(r'SQL state:\s*([0-9A-Z]{5})', str(res))
                    if m:
                        err.sqlstate = m.group(1)  # type: ignore[attr-defined]
                    raise err
                return [dict(r) for r in (res.get('rows') or ())]

            def pg_exec(statements: list[str]) -> None:
                for stmt in statements:
                    status, res = conn.execute_void(stmt)
                    if not status:
                        raise RuntimeError(str(res))

            yield pg_query, pg_exec
            return

        # Provider endpoint workflow
        from pgadmin.cdeadmin.endpoints import service_for_app as endpoint_service_for_app
        ep_service = (
            self.workspace_service.endpoint_service
            if self.workspace_service is not None
            else endpoint_service_for_app(current_app)
        )
        context, endpoint, _root = ep_service.workspace(
            server, database_target_id=norm_target
        )
        binding = ep_service.provider_registry.resolve(context)
        provider = binding.instance
        route = dict(endpoint['route'])
        raw_conn = None
        if info['engine_id'] == 'firebird' and not (route.get('database') or '').strip():
            ep_model = getattr(server, 'endpoint_profile', None)
            targets = sorted(
                list(getattr(ep_model, 'database_targets', ()) or ()),
                key=lambda t: (not bool(getattr(t, 'active', False)), str(getattr(t, 'id', ''))),
            )
            for target in targets:
                t_id = getattr(target, 'id', None)
                if not t_id:
                    continue
                try:
                    t_ctx, t_ep, _ = ep_service.workspace(server, database_target_id=t_id)
                    t_binding = ep_service.provider_registry.resolve(t_ctx)
                    t_provider = t_binding.instance
                    t_route = dict(t_ep['route'])
                    if (t_route.get('database') or '').strip():
                        raw_conn = t_provider.client._connect({'route': t_route})
                        context = t_ctx
                        provider = t_provider
                        route = t_route
                        break
                except Exception:
                    continue
            if raw_conn is None:
                for cand in provider._resolve_server_security_database_candidates(route):
                    try:
                        cand_route = {**route, 'database': cand}
                        raw_conn = provider.client._connect({'route': cand_route})
                        route = cand_route
                        break
                    except Exception:
                        continue
            if raw_conn is None:
                svc_route = {k: v for k, v in route.items() if k != 'database'}
                raw_conn = provider.client._connect({'route': svc_route})
                route = svc_route
        else:
            raw_conn = provider.client._connect({'route': route})
        try:
            if info['engine_id'] in {'mysql', 'mariadb', 'tidb', 'dolt'}:
                try:
                    raw_conn.autocommit = True
                except Exception:
                    pass
            if (
                info['engine_id'] == 'firebird'
                and not callable(getattr(raw_conn, 'cursor', None))
                and hasattr(raw_conn, 'user')
            ):
                yield self._wrap_firebird_service_connection(raw_conn, route)
            else:
                yield self._wrap_dbapi_connection(raw_conn, info['engine_id'], write=write)
            if write and self.workspace_service is not None:
                try:
                    self.workspace_service.resource_service.invalidate(context)
                except Exception:
                    pass
        finally:
            if not write and info['engine_id'] == 'firebird':
                try:
                    tx = getattr(raw_conn, 'main_transaction', None)
                    if tx is not None and tx.is_active() is True:
                        raw_conn.rollback()
                except Exception:
                    pass
            forget = getattr(provider.client, '_forget_and_close', None)
            if callable(forget):
                forget(raw_conn)
            else:
                raw_conn.close()

    @staticmethod
    def _wrap_firebird_service_connection(srv_conn: Any, route: Mapping[str, Any]):
        """Adapt a Firebird Services Manager (`service_mgr`) handle when no `.fdb` target exists."""
        eff_user = str(route.get('user') or 'SYSDBA').strip()
        eff_role = str(route.get('role') or '').strip()

        def svc_query_fn(sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
            upper_sql = sql.upper()
            if 'FROM RDB$DATABASE' in upper_sql:
                return [{'u': eff_user, 'r': eff_role}]
            if 'FROM SEC$USERS' in upper_sql:
                out = []
                for uinfo in srv_conn.user.get_all() or ():
                    uname = str(getattr(uinfo, 'user_name', '') or '').strip()
                    if not uname:
                        continue
                    out.append({
                        'uname': uname,
                        'plugin': None,
                        'first_name': getattr(uinfo, 'first_name', None) or '',
                        'middle_name': getattr(uinfo, 'middle_name', None) or '',
                        'last_name': getattr(uinfo, 'last_name', None) or '',
                        'active': True,
                        'is_admin': bool(getattr(uinfo, 'admin', False)),
                        'description': '',
                    })
                return out
            return []

        def svc_exec_fn(_statements: list[str]) -> None:
            raise SecurityAuthorityError(
                'Direct SQL DCL requires an attached database; use Services Manager user lifecycle.'
            )

        svc_exec_fn._firebird_service_conn = srv_conn  # type: ignore[attr-defined]
        return svc_query_fn, svc_exec_fn

    @staticmethod
    def _wrap_dbapi_connection(raw_conn: Any, engine_id: str, *, write: bool = False):
        def query_fn(sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
            cur = raw_conn.cursor()
            try:
                if params:
                    cur.execute(sql, tuple(params))
                else:
                    cur.execute(sql)
                cols = [str(d[0]).lower() for d in (cur.description or ())]
                rows = []
                for raw_row in cur.fetchall():
                    item: dict[str, Any] = {}
                    for idx, cname in enumerate(cols):
                        val = raw_row[idx]
                        if callable(getattr(val, 'read', None)):
                            try:
                                val = val.read()
                            finally:
                                try:
                                    raw_row[idx].close()
                                except Exception:
                                    pass
                        item[cname] = val
                    rows.append(item)
                return rows
            finally:
                cur.close()

        def exec_fn(statements: list[str]) -> None:
            cur = raw_conn.cursor()
            try:
                for stmt in statements:
                    cur.execute(stmt)
                if write and engine_id in {'firebird', 'postgresql', 'cockroachdb', 'yugabytedb'}:
                    commit = getattr(raw_conn, 'commit', None)
                    if callable(commit):
                        commit()
            except Exception:
                rollback = getattr(raw_conn, 'rollback', None)
                if callable(rollback):
                    try:
                        rollback()
                    except Exception:
                        pass
                raise
            finally:
                cur.close()

        return query_fn, exec_fn

    # ------------------------------------------------------------------
    # 1. GET /principals
    # ------------------------------------------------------------------
    def get_principals(self, sid: int, database_target_id: str | None, scope: str) -> dict[str, Any]:
        info = self._resolve_target_info(sid)
        engine_id = info['engine_id']
        fam = _dialect_family(engine_id)
        norm_scope = 'database' if scope == 'database' else 'server'

        if engine_id in EMBEDDED_UNSUPPORTED_ENGINES:
            return {
                'engine': engine_id,
                'scope': norm_scope,
                'supported': False,
                'capabilities': {
                    'effective_user': None,
                    'can_manage_users': False,
                    'can_manage_roles': False,
                    'can_grant': False,
                    'users_at_server_scope': False,
                    'roles_at_server_scope': False,
                    'visibility_state': 'denied',
                    'visibility_message': f'{engine_id} is an embedded file engine without native SQL users or roles.',
                },
                'users': [],
                'roles': [],
                'available_system_privileges': [],
            }

        with self._open_connection(info, database_target_id, write=False) as (query_fn, _exec_fn):
            if fam == 'firebird':
                return self._collect_firebird_principals(info, query_fn, norm_scope)
            if fam == 'postgresql':
                return self._collect_postgresql_principals(engine_id, query_fn, norm_scope)
            if fam in {'mysql', 'mariadb'}:
                return self._collect_mysql_family_principals(engine_id, fam == 'mariadb', query_fn, norm_scope)
        raise SecurityAuthorityError(f'Unsupported engine: {engine_id}')

    def _collect_firebird_principals(
        self, info: Mapping[str, Any], query_fn: Callable, scope: str
    ) -> dict[str, Any]:
        embedded = info.get('route_kind') == 'embedded_file'
        eff_rows = query_fn('SELECT TRIM(TRAILING FROM CURRENT_USER) AS u, TRIM(TRAILING FROM CURRENT_ROLE) AS r FROM RDB$DATABASE')
        effective_user = str(eff_rows[0]['u']).strip() if eff_rows else ''
        effective_role = str(eff_rows[0]['r']).strip() if eff_rows else ''
        is_dba = effective_user.upper() == 'SYSDBA' or effective_role.upper() == 'RDB$ADMIN'

        visibility_state = 'full'
        visibility_message = ''

        # Read role memberships from RDB$USER_PRIVILEGES
        user_memberships: dict[str, list[dict[str, Any]]] = {}
        role_members: dict[str, list[dict[str, Any]]] = {}
        role_member_of: dict[str, list[dict[str, Any]]] = {}
        try:
            m_rows = query_fn(
                "SELECT TRIM(TRAILING FROM RDB$USER) AS grantee, "
                "TRIM(TRAILING FROM RDB$RELATION_NAME) AS role_name, "
                "TRIM(TRAILING FROM RDB$FIELD_NAME) AS def_flag, "
                "RDB$GRANT_OPTION AS grant_opt, RDB$USER_TYPE AS utype "
                "FROM RDB$USER_PRIVILEGES "
                "WHERE RDB$PRIVILEGE = 'M' AND RDB$OBJECT_TYPE = 13 "
                "ORDER BY 1, 2"
            )
            for mr in m_rows:
                grantee = str(mr.get('grantee') or '').strip()
                rname = str(mr.get('role_name') or '').strip()
                adm = bool(mr.get('grant_opt') in (1, 2))
                is_def = bool(str(mr.get('def_flag') or '').strip())
                utype = mr.get('utype')
                entry = {
                    'role': rname,
                    'admin_option': adm,
                    'default_role': is_def,
                    'inherit_option': True,
                    'set_option': True,
                }
                if utype == 13:
                    role_member_of.setdefault(grantee, []).append(entry)
                    role_members.setdefault(rname, []).append({
                        'principal': grantee,
                        'principal_type': 'role',
                        'admin_option': adm,
                    })
                else:
                    user_memberships.setdefault(grantee, []).append(entry)
                    role_members.setdefault(rname, []).append({
                        'principal': grantee,
                        'principal_type': 'user',
                        'admin_option': adm,
                    })
        except Exception:
            pass

        users_out: list[dict[str, Any]] = []
        if not embedded:
            attr_map: dict[tuple[str, str], list[dict[str, str]]] = {}
            try:
                for ar in query_fn(
                    'SELECT TRIM(TRAILING FROM SEC$USER_NAME) AS u, '
                    'TRIM(TRAILING FROM SEC$PLUGIN) AS p, '
                    'TRIM(TRAILING FROM SEC$KEY) AS k, SEC$VALUE AS v '
                    'FROM SEC$USER_ATTRIBUTES ORDER BY 1, 2, 3'
                ):
                    uk = (str(ar.get('u') or '').strip(), str(ar.get('p') or '').strip())
                    attr_map.setdefault(uk, []).append({
                        'name': str(ar.get('k') or '').strip(),
                        'value': str(ar.get('v') or ''),
                    })
            except Exception:
                pass
            try:
                u_rows = query_fn(
                    'SELECT TRIM(TRAILING FROM SEC$USER_NAME) AS uname, '
                    'TRIM(TRAILING FROM SEC$PLUGIN) AS plugin, '
                    'SEC$FIRST_NAME AS first_name, SEC$MIDDLE_NAME AS middle_name, '
                    'SEC$LAST_NAME AS last_name, SEC$ACTIVE AS active, '
                    'SEC$ADMIN AS is_admin, SEC$DESCRIPTION AS description '
                    'FROM SEC$USERS ORDER BY 1, 2'
                )
                for ur in u_rows:
                    uname = str(ur.get('uname') or '').strip()
                    plug = str(ur.get('plugin') or '').strip() or None
                    adm = bool(ur.get('is_admin'))
                    if uname.upper() == effective_user.upper() and adm:
                        is_dba = True
                    tags = attr_map.get((uname, plug or ''), [])
                    users_out.append({
                        'id': f'{uname}:{plug}' if plug else uname,
                        'name': uname,
                        'host': None,
                        'plugin': plug,
                        'active': True if ur.get('active') is None else bool(ur.get('active')),
                        'locked': False if ur.get('active') is None else not bool(ur.get('active')),
                        'is_admin': adm,
                        'first_name': str(ur.get('first_name') or ''),
                        'middle_name': str(ur.get('middle_name') or ''),
                        'last_name': str(ur.get('last_name') or ''),
                        'valid_until': None,
                        'connection_limit': -1,
                        'comment': str(ur.get('description') or ''),
                        'attributes': {t['name']: t['value'] for t in tags},
                        'tags': tags,
                        'member_of': user_memberships.get(uname, []),
                        'system_privileges': ['RDB$ADMIN'] if adm else [],
                    })
                if not is_dba:
                    visibility_state = 'limited'
                    visibility_message = (
                        'Non-administrator Firebird sessions only observe their own SEC$USERS account.'
                    )
            except Exception as exc:
                if _is_permission_denied_error(exc):
                    visibility_state = 'denied'
                    visibility_message = 'Current session is not authorized to read SEC$USERS.'
                else:
                    visibility_state = 'limited'
                    visibility_message = f'SEC$USERS is unavailable in this attachment ({type(exc).__name__}).'

        roles_out: list[dict[str, Any]] = []
        try:
            r_rows = query_fn(
                'SELECT TRIM(TRAILING FROM RDB$ROLE_NAME) AS rname, '
                'TRIM(TRAILING FROM RDB$OWNER_NAME) AS owner_name, '
                'RDB$DESCRIPTION AS description, RDB$SYSTEM_PRIVILEGES AS sys_privs, '
                'COALESCE(RDB$SYSTEM_FLAG, 0) AS sys_flag '
                'FROM RDB$ROLES ORDER BY 1'
            )
            for rr in r_rows:
                rname = str(rr.get('rname') or '').strip()
                if int(rr.get('sys_flag') or 0) != 0 and rname.upper() != 'RDB$ADMIN':
                    continue
                sys_p = _decode_firebird_role_privs(rr.get('sys_privs'))
                roles_out.append({
                    'id': rname,
                    'name': rname,
                    'host': None,
                    'can_login': False,
                    'is_admin': rname.upper() == 'RDB$ADMIN',
                    'owner': str(rr.get('owner_name') or '').strip(),
                    'comment': str(rr.get('description') or ''),
                    'members': role_members.get(rname, []),
                    'member_of': role_member_of.get(rname, []),
                    'system_privileges': sys_p,
                })
        except Exception as exc:
            if _is_permission_denied_error(exc):
                visibility_state = 'denied'
                visibility_message = 'Current session is not authorized to read RDB$ROLES.'

        return {
            'engine': 'firebird',
            'scope': scope,
            'supported': True,
            'capabilities': {
                'effective_user': effective_user,
                'can_manage_users': bool(is_dba and not embedded),
                'can_manage_roles': True,
                'can_grant': True,
                'users_at_server_scope': not embedded,
                'roles_at_server_scope': False,
                'visibility_state': visibility_state,
                'visibility_message': visibility_message,
            },
            'users': users_out,
            'roles': roles_out,
            'available_system_privileges': list(FIREBIRD_SYSTEM_PRIVILEGES),
        }

    def _collect_postgresql_principals(
        self, engine_id: str, query_fn: Callable, scope: str
    ) -> dict[str, Any]:
        eff_rows = query_fn('SELECT current_user AS u')
        effective_user = str(eff_rows[0]['u']) if eff_rows else ''

        try:
            role_rows = query_fn(
                "SELECT r.oid, r.rolname, r.rolsuper, r.rolinherit, r.rolcreaterole, "
                "r.rolcreatedb, r.rolcanlogin, r.rolreplication, r.rolbypassrls, "
                "r.rolconnlimit, CASE WHEN r.rolvaliduntil IS NULL THEN NULL "
                "ELSE r.rolvaliduntil::text END AS rolvaliduntil, "
                "pg_catalog.shobj_description(r.oid, 'pg_authid') AS comment "
                "FROM pg_catalog.pg_roles r "
                "WHERE r.rolname NOT LIKE 'pg\\_%' ESCAPE '\\' "
                "ORDER BY r.rolname"
            )
        except Exception as exc:
            if _is_permission_denied_error(exc):
                return {
                    'engine': engine_id,
                    'scope': scope,
                    'supported': True,
                    'capabilities': {
                        'effective_user': effective_user,
                        'can_manage_users': False,
                        'can_manage_roles': False,
                        'can_grant': False,
                        'users_at_server_scope': True,
                        'roles_at_server_scope': True,
                        'visibility_state': 'denied',
                        'visibility_message': 'Current session lacks permission to query pg_roles.',
                    },
                    'users': [],
                    'roles': [],
                    'available_system_privileges': list(POSTGRESQL_SYSTEM_PRIVILEGES),
                }
            raise

        member_of_map: dict[str, list[dict[str, Any]]] = {}
        members_map: dict[str, list[dict[str, Any]]] = {}
        login_by_name = {str(r['rolname']): bool(r.get('rolcanlogin')) for r in role_rows}
        try:
            try:
                edges = query_fn(
                    'SELECT pr.rolname AS role_name, pm.rolname AS member_name, '
                    'am.admin_option, am.inherit_option, am.set_option '
                    'FROM pg_catalog.pg_auth_members am '
                    'JOIN pg_catalog.pg_roles pr ON pr.oid = am.roleid '
                    'JOIN pg_catalog.pg_roles pm ON pm.oid = am.member '
                    'ORDER BY pr.rolname, pm.rolname'
                )
            except Exception:
                edges = query_fn(
                    'SELECT pr.rolname AS role_name, pm.rolname AS member_name, '
                    'am.admin_option, true AS inherit_option, true AS set_option '
                    'FROM pg_catalog.pg_auth_members am '
                    'JOIN pg_catalog.pg_roles pr ON pr.oid = am.roleid '
                    'JOIN pg_catalog.pg_roles pm ON pm.oid = am.member '
                    'ORDER BY pr.rolname, pm.rolname'
                )
            for e in edges:
                rn = str(e['role_name'])
                mn = str(e['member_name'])
                adm = bool(e.get('admin_option'))
                inh = bool(e.get('inherit_option', True))
                set_o = bool(e.get('set_option', True))
                member_of_map.setdefault(mn, []).append({
                    'role': rn,
                    'admin_option': adm,
                    'default_role': inh,
                    'inherit_option': inh,
                    'set_option': set_o,
                })
                members_map.setdefault(rn, []).append({
                    'principal': mn,
                    'principal_type': 'user' if login_by_name.get(mn) else 'role',
                    'admin_option': adm,
                })
        except Exception:
            pass

        can_manage = False
        users_out: list[dict[str, Any]] = []
        roles_out: list[dict[str, Any]] = []
        for r in role_rows:
            rname = str(r['rolname'])
            can_login = bool(r.get('rolcanlogin'))
            is_super = bool(r.get('rolsuper'))
            can_createrole = bool(r.get('rolcreaterole'))
            if rname == effective_user and (is_super or can_createrole):
                can_manage = True
            sys_privs = [
                kw for col, kw in (
                    ('rolsuper', 'SUPERUSER'),
                    ('rolcreatedb', 'CREATEDB'),
                    ('rolcreaterole', 'CREATEROLE'),
                    ('rolinherit', 'INHERIT'),
                    ('rolcanlogin', 'LOGIN'),
                    ('rolreplication', 'REPLICATION'),
                    ('rolbypassrls', 'BYPASSRLS'),
                )
                if r.get(col)
            ]
            if can_login:
                users_out.append({
                    'id': rname,
                    'name': rname,
                    'host': None,
                    'plugin': None,
                    'active': True,
                    'locked': False,
                    'is_admin': is_super,
                    'first_name': '',
                    'middle_name': '',
                    'last_name': '',
                    'valid_until': r.get('rolvaliduntil'),
                    'connection_limit': int(r.get('rolconnlimit') if r.get('rolconnlimit') is not None else -1),
                    'comment': str(r.get('comment') or ''),
                    'attributes': {},
                    'tags': [],
                    'member_of': member_of_map.get(rname, []),
                    'system_privileges': sys_privs,
                })
            else:
                roles_out.append({
                    'id': rname,
                    'name': rname,
                    'host': None,
                    'can_login': False,
                    'is_admin': is_super,
                    'owner': '',
                    'comment': str(r.get('comment') or ''),
                    'members': members_map.get(rname, []),
                    'member_of': member_of_map.get(rname, []),
                    'system_privileges': sys_privs,
                })

        return {
            'engine': engine_id,
            'scope': scope,
            'supported': True,
            'capabilities': {
                'effective_user': effective_user,
                'can_manage_users': can_manage,
                'can_manage_roles': can_manage,
                'can_grant': True,
                'users_at_server_scope': True,
                'roles_at_server_scope': True,
                'visibility_state': 'full' if can_manage else 'limited',
                'visibility_message': '' if can_manage else 'Current role lacks SUPERUSER or CREATEROLE privileges; viewing read-only role catalog.',
            },
            'users': users_out,
            'roles': roles_out,
            'available_system_privileges': list(POSTGRESQL_SYSTEM_PRIVILEGES),
        }

    def _collect_mysql_family_principals(
        self, engine_id: str, is_mariadb: bool, query_fn: Callable, scope: str
    ) -> dict[str, Any]:
        eff_rows = query_fn('SELECT CURRENT_USER() AS cu')
        effective_user = str(eff_rows[0]['cu']) if eff_rows else ''

        global_priv_map: dict[str, list[str]] = {}
        try:
            for gpr in query_fn(
                'SELECT GRANTEE AS g, PRIVILEGE_TYPE AS p '
                'FROM information_schema.USER_PRIVILEGES ORDER BY 1, 2'
            ):
                global_priv_map.setdefault(str(gpr.get('g') or ''), []).append(str(gpr.get('p') or '').upper())
        except Exception:
            pass

        try:
            if is_mariadb:
                acct_rows = query_fn(
                    'SELECT User AS u, Host AS h, is_role, plugin, '
                    'max_user_connections, default_role '
                    'FROM mysql.user ORDER BY User, Host'
                )
            else:
                acct_rows = query_fn(
                    'SELECT User AS u, Host AS h, plugin, account_locked, '
                    'max_user_connections, '
                    "JSON_UNQUOTE(JSON_EXTRACT(User_attributes, '$.metadata.comment')) AS comment "
                    'FROM mysql.user ORDER BY User, Host'
                )
        except Exception as exc:
            if _is_permission_denied_error(exc):
                errno = getattr(exc, 'errno', None)
                detail = f' (errno {errno})' if errno else ''
                return {
                    'engine': engine_id,
                    'scope': scope,
                    'supported': True,
                    'capabilities': {
                        'effective_user': effective_user,
                        'can_manage_users': False,
                        'can_manage_roles': False,
                        'can_grant': False,
                        'users_at_server_scope': True,
                        'roles_at_server_scope': True,
                        'visibility_state': 'denied',
                        'visibility_message': (
                            f'Current session lacks SELECT permission on mysql.user{detail}; '
                            'server principal directory requires administrative privileges.'
                        ),
                    },
                    'users': [],
                    'roles': [],
                    'available_system_privileges': list(MYSQL_SYSTEM_PRIVILEGES),
                }
            raise

        users_out: list[dict[str, Any]] = []
        roles_out: list[dict[str, Any]] = []

        if is_mariadb:
            locked_map: dict[tuple[str, str], bool] = {}
            try:
                for lr in query_fn(
                    "SELECT User AS u, Host AS h, "
                    "COALESCE(JSON_VALUE(Priv, '$.account_locked'), 'false') AS lk "
                    "FROM mysql.global_priv"
                ):
                    locked_map[(str(lr['u']), str(lr['h']))] = str(lr.get('lk')).lower() in {'true', '1'}
            except Exception:
                pass
            m_of: dict[tuple[str, str], list[dict[str, Any]]] = {}
            r_members: dict[str, list[dict[str, Any]]] = {}
            try:
                for mr in query_fn('SELECT Host AS h, User AS u, Role AS r, Admin_option AS adm FROM mysql.roles_mapping'):
                    mu, mh, mr_name = str(mr['u']), str(mr['h']), str(mr['r'])
                    adm = str(mr.get('adm') or '').upper() == 'Y'
                    m_of.setdefault((mu, mh), []).append({
                        'role': mr_name, 'admin_option': adm, 'default_role': False,
                        'inherit_option': True, 'set_option': True,
                    })
                    r_members.setdefault(mr_name, []).append({
                        'principal': f'{mu}@{mh}' if mh else mu,
                        'principal_type': 'role' if not mh else 'user',
                        'admin_option': adm,
                    })
            except Exception:
                pass
            for ar in acct_rows:
                u, h = str(ar.get('u') or ''), str(ar.get('h') or '')
                is_role = str(ar.get('is_role') or '').upper() == 'Y'
                grantee_key = f"'{u}'@'{h}'"
                sys_p = global_priv_map.get(grantee_key, [])
                def_r = str(ar.get('default_role') or '')
                entries_m = [
                    {**e, 'default_role': bool(def_r and e['role'] == def_r)}
                    for e in m_of.get((u, h), ())
                ]
                if is_role:
                    roles_out.append({
                        'id': u,
                        'name': u,
                        'host': None,
                        'can_login': False,
                        'is_admin': 'SUPER' in sys_p or 'ALL PRIVILEGES' in sys_p,
                        'owner': '',
                        'comment': '',
                        'members': r_members.get(u, []),
                        'member_of': entries_m,
                        'system_privileges': sys_p,
                    })
                else:
                    lk = locked_map.get((u, h), False)
                    users_out.append({
                        'id': f'{u}@{h}',
                        'name': u,
                        'host': h,
                        'plugin': str(ar.get('plugin') or '') or None,
                        'active': not lk,
                        'locked': lk,
                        'is_admin': 'SUPER' in sys_p or 'CREATE USER' in sys_p or 'ALL PRIVILEGES' in sys_p,
                        'first_name': '',
                        'middle_name': '',
                        'last_name': '',
                        'valid_until': None,
                        'connection_limit': int(ar.get('max_user_connections') or 0),
                        'comment': '',
                        'attributes': {},
                        'tags': [],
                        'member_of': entries_m,
                        'system_privileges': sys_p,
                    })
        else:
            def_pairs: dict[tuple[str, str], set[tuple[str, str]]] = {}
            try:
                for dr in query_fn(
                    'SELECT USER AS u, HOST AS h, DEFAULT_ROLE_USER AS dru, DEFAULT_ROLE_HOST AS drh '
                    'FROM mysql.default_roles'
                ):
                    def_pairs.setdefault((str(dr['u']), str(dr['h'])), set()).add(
                        (str(dr['dru']), str(dr['drh']))
                    )
            except Exception:
                pass
            role_identities: set[tuple[str, str]] = set()
            m_of_my: dict[tuple[str, str], list[dict[str, Any]]] = {}
            r_members_my: dict[tuple[str, str], list[dict[str, Any]]] = {}
            try:
                for er in query_fn(
                    'SELECT FROM_USER AS fu, FROM_HOST AS fh, TO_USER AS tu, TO_HOST AS th, '
                    'WITH_ADMIN_OPTION AS adm FROM mysql.role_edges'
                ):
                    fu, fh, tu, th = str(er['fu']), str(er['fh']), str(er['tu']), str(er['th'])
                    adm = str(er.get('adm') or '').upper() == 'Y'
                    role_identities.add((fu, fh))
                    m_of_my.setdefault((tu, th), []).append({
                        'role': f'{fu}@{fh}',
                        'admin_option': adm,
                        'default_role': (fu, fh) in def_pairs.get((tu, th), set()),
                        'inherit_option': True,
                        'set_option': True,
                    })
                    r_members_my.setdefault((fu, fh), []).append({
                        'principal': f'{tu}@{th}',
                        'principal_type': 'user',
                        'admin_option': adm,
                    })
            except Exception:
                pass

            for ar in acct_rows:
                u, h = str(ar.get('u') or ''), str(ar.get('h') or '%')
                lk = str(ar.get('account_locked') or '').upper() == 'Y'
                plug = str(ar.get('plugin') or '') or None
                grantee_key = f"'{u}'@'{h}'"
                sys_p = global_priv_map.get(grantee_key, [])
                is_role_like = (u, h) in role_identities or (lk and plug == 'caching_sha2_password' and not sys_p and (u, h) in role_identities)
                if is_role_like:
                    roles_out.append({
                        'id': f'{u}@{h}',
                        'name': u,
                        'host': h,
                        'can_login': not lk,
                        'is_admin': 'SUPER' in sys_p or 'SYSTEM_USER' in sys_p,
                        'owner': '',
                        'comment': str(ar.get('comment') or ''),
                        'members': r_members_my.get((u, h), []),
                        'member_of': m_of_my.get((u, h), []),
                        'system_privileges': sys_p,
                    })
                users_out.append({
                    'id': f'{u}@{h}',
                    'name': u,
                    'host': h,
                    'plugin': plug,
                    'active': not lk,
                    'locked': lk,
                    'is_admin': 'SUPER' in sys_p or 'CREATE USER' in sys_p or 'SYSTEM_USER' in sys_p,
                    'first_name': '',
                    'middle_name': '',
                    'last_name': '',
                    'valid_until': None,
                    'connection_limit': int(ar.get('max_user_connections') or 0),
                    'comment': str(ar.get('comment') or ''),
                    'attributes': {},
                    'tags': [],
                    'member_of': m_of_my.get((u, h), []),
                    'system_privileges': sys_p,
                })

        return {
            'engine': engine_id,
            'scope': scope,
            'supported': True,
            'capabilities': {
                'effective_user': effective_user,
                'can_manage_users': True,
                'can_manage_roles': True,
                'can_grant': True,
                'users_at_server_scope': True,
                'roles_at_server_scope': True,
                'visibility_state': 'full',
                'visibility_message': '',
            },
            'users': users_out,
            'roles': roles_out,
            'available_system_privileges': list(MYSQL_SYSTEM_PRIVILEGES),
        }

    # ------------------------------------------------------------------
    # 2. POST /principal/plan & /principal/apply
    # ------------------------------------------------------------------
    def plan_principal(self, body: Mapping[str, Any]) -> dict[str, Any]:
        sid = int(body.get('sid') or 0)
        info = self._resolve_target_info(sid)
        compiled = compile_principal_plan(
            info['engine_id'],
            str(body.get('principal_kind') or 'role'),
            str(body.get('operation') or 'create'),
            body.get('target'),
            body.get('draft'),
        )
        return {
            'statements': compiled['statements'],
            'preview_sql': compiled['preview_sql'],
            'warnings': compiled['warnings'],
        }

    def apply_principal(self, body: Mapping[str, Any]) -> dict[str, Any]:
        sid = int(body.get('sid') or 0)
        info = self._resolve_target_info(sid)
        compiled = compile_principal_plan(
            info['engine_id'],
            str(body.get('principal_kind') or 'role'),
            str(body.get('operation') or 'create'),
            body.get('target'),
            body.get('draft'),
        )
        db_target = body.get('database_target_id')
        if body.get('scope') == 'server' and info['engine_id'] != 'firebird':
            db_target = None
        with self._open_connection(info, db_target, write=True) as (_query_fn, exec_fn):
            svc_conn = getattr(exec_fn, '_firebird_service_conn', None)
            if svc_conn is not None and str(body.get('principal_kind') or 'user').lower() == 'user':
                op = str(body.get('operation') or 'create').lower()
                draft = body.get('draft') or {}
                target = body.get('target') or {}
                uname = str((target.get('name') if op != 'create' else draft.get('name')) or '').strip()
                if op == 'create':
                    svc_conn.user.add(
                        user_name=uname,
                        password=str(draft.get('password') or ''),
                        first_name=draft.get('first_name') or None,
                        middle_name=draft.get('middle_name') or None,
                        last_name=draft.get('last_name') or None,
                        admin=bool(draft.get('is_admin', False)),
                    )
                elif op == 'alter':
                    svc_conn.user.update(
                        uname,
                        password=draft.get('password') or None,
                        first_name=draft.get('first_name') if 'first_name' in draft else None,
                        middle_name=draft.get('middle_name') if 'middle_name' in draft else None,
                        last_name=draft.get('last_name') if 'last_name' in draft else None,
                        admin=bool(draft['is_admin']) if 'is_admin' in draft else None,
                    )
                elif op == 'drop':
                    svc_conn.user.delete(uname)
                else:
                    raise SecurityAuthorityError(f'Unsupported operation: {op}')
            else:
                exec_fn(compiled['exec_statements'])
        return {
            'applied': True,
            'preview_sql': compiled['preview_sql'],
            'statement_count': len(compiled['exec_statements']),
        }

    # ------------------------------------------------------------------
    # 3. GET /object_grants
    # ------------------------------------------------------------------
    def get_object_grants(self, params: Mapping[str, Any]) -> dict[str, Any]:
        sid = int(params.get('sid') or 0)
        info = self._resolve_target_info(sid)
        engine_id = info['engine_id']
        fam = _dialect_family(engine_id)
        obj_kind = str(params.get('object_kind') or 'table').strip().lower()
        schema = str(params.get('schema') or '').strip() or None
        obj_name = str(params.get('object_name') or '').strip()
        db_target = params.get('database_target_id')

        if engine_id in EMBEDDED_UNSUPPORTED_ENGINES:
            return {
                'engine': engine_id,
                'supported': False,
                'object': {'kind': obj_kind, 'schema': schema, 'name': obj_name},
                'capabilities': {
                    'can_edit': False,
                    'reason': f'{engine_id} is an embedded file engine without SQL GRANT/REVOKE privileges.',
                    'supported_privileges': [],
                    'supports_grant_option': False,
                    'supports_column_privileges': False,
                    'columns': [],
                },
                'principals': [],
                'grants': [],
            }

        allowed_by_kind = OBJECT_GRANT_PRIVILEGES.get(fam, {})
        if obj_kind not in allowed_by_kind:
            return {
                'engine': engine_id,
                'supported': False,
                'object': {'kind': obj_kind, 'schema': schema, 'name': obj_name},
                'capabilities': {
                    'can_edit': False,
                    'reason': f'{engine_id} does not support per-object GRANT/REVOKE on {obj_kind}.',
                    'supported_privileges': [],
                    'supports_grant_option': False,
                    'supports_column_privileges': False,
                    'columns': [],
                },
                'principals': [],
                'grants': [],
            }

        supported_privs = list(allowed_by_kind[obj_kind])
        supports_col_privs = bool(COLUMN_PRIVILEGE_SUPPORT.get(fam, {}).get(obj_kind))

        with self._open_connection(info, db_target, write=False) as (query_fn, _exec_fn):
            if fam == 'firebird':
                return self._collect_firebird_object_grants(
                    info, query_fn, obj_kind, schema, obj_name, supported_privs, supports_col_privs
                )
            if fam == 'postgresql':
                return self._collect_postgresql_object_grants(
                    engine_id, query_fn, obj_kind, schema, obj_name, supported_privs, supports_col_privs
                )
            if fam in {'mysql', 'mariadb'}:
                return self._collect_mysql_family_object_grants(
                    engine_id, fam == 'mariadb', query_fn, obj_kind, schema, obj_name, supported_privs, supports_col_privs
                )
        raise SecurityAuthorityError(f'Unsupported engine: {engine_id}')

    def _collect_firebird_object_grants(
        self,
        info: Mapping[str, Any],
        query_fn: Callable,
        obj_kind: str,
        schema: str | None,
        obj_name: str,
        supported_privs: list[str],
        supports_col_privs: bool,
    ) -> dict[str, Any]:
        columns: list[str] = []
        if obj_kind in {'table', 'view'} and obj_name:
            try:
                c_rows = query_fn(
                    'SELECT TRIM(TRAILING FROM RDB$FIELD_NAME) AS cname '
                    'FROM RDB$RELATION_FIELDS WHERE TRIM(TRAILING FROM RDB$RELATION_NAME) = ? '
                    'ORDER BY RDB$FIELD_POSITION',
                    (obj_name,),
                )
                columns = [str(r['cname']).strip() for r in c_rows if r.get('cname')]
            except Exception:
                pass

        principals: list[dict[str, Any]] = [{'name': 'PUBLIC', 'kind': 'special'}]
        if info.get('route_kind') != 'embedded_file':
            try:
                for ur in query_fn('SELECT DISTINCT TRIM(TRAILING FROM SEC$USER_NAME) AS u FROM SEC$USERS ORDER BY 1'):
                    if ur.get('u'):
                        principals.append({'name': str(ur['u']).strip(), 'kind': 'user'})
            except Exception:
                pass
        try:
            for rr in query_fn('SELECT TRIM(TRAILING FROM RDB$ROLE_NAME) AS r FROM RDB$ROLES WHERE COALESCE(RDB$SYSTEM_FLAG, 0) = 0 ORDER BY 1'):
                if rr.get('r'):
                    principals.append({'name': str(rr['r']).strip(), 'kind': 'role'})
        except Exception:
            pass

        fb_priv_map = {
            'S': 'SELECT', 'I': 'INSERT', 'U': 'UPDATE',
            'D': 'DELETE', 'R': 'REFERENCES', 'X': 'EXECUTE', 'G': 'USAGE',
        }
        fb_obj_type = {
            'table': 0, 'view': 0, 'procedure': 5, 'function': 15,
            'package': 18, 'sequence': 14, 'database': 21,
        }.get(obj_kind, 0)
        target_rel = 'SQL$DATABASE' if obj_kind == 'database' else obj_name

        raw_grants: list[dict[str, Any]] = []
        g_rows = query_fn(
            'SELECT TRIM(TRAILING FROM RDB$USER) AS grantee, '
            'TRIM(TRAILING FROM RDB$FIELD_NAME) AS fname, '
            'TRIM(TRAILING FROM RDB$PRIVILEGE) AS priv, '
            'TRIM(TRAILING FROM RDB$GRANTOR) AS grantor, '
            'RDB$GRANT_OPTION AS gopt, RDB$USER_TYPE AS utype '
            'FROM RDB$USER_PRIVILEGES '
            'WHERE TRIM(TRAILING FROM RDB$RELATION_NAME) = ? AND RDB$OBJECT_TYPE = ? '
            'ORDER BY 1, 3',
            (target_rel, fb_obj_type),
        )
        for gr in g_rows:
            code = str(gr.get('priv') or '').strip().upper()
            pname = fb_priv_map.get(code, code)
            grantee = str(gr.get('grantee') or '').strip()
            utype = gr.get('utype')
            g_kind = 'special' if grantee.upper() == 'PUBLIC' else ('role' if utype == 13 else 'user')
            col_name = str(gr.get('fname') or '').strip() or None
            raw_grants.append({
                'grantee': grantee,
                'grantee_kind': g_kind,
                'grantee_host': None,
                'grantor': str(gr.get('grantor') or '').strip(),
                'privilege': pname,
                'grant_option': bool(gr.get('gopt') in (1, 2)),
                'column': col_name,
            })

        return {
            'engine': 'firebird',
            'supported': True,
            'object': {'kind': obj_kind, 'schema': None, 'name': obj_name},
            'capabilities': {
                'can_edit': True,
                'reason': '',
                'supported_privileges': supported_privs,
                'supports_grant_option': obj_kind != 'database',
                'supports_column_privileges': supports_col_privs,
                'columns': columns,
            },
            'principals': principals,
            'grants': normalize_grants_matrix(raw_grants, supported_privs),
        }

    def _collect_postgresql_object_grants(
        self,
        engine_id: str,
        query_fn: Callable,
        obj_kind: str,
        schema: str | None,
        obj_name: str,
        supported_privs: list[str],
        supports_col_privs: bool,
    ) -> dict[str, Any]:
        eff_schema = schema or 'public'
        principals: list[dict[str, Any]] = [{'name': 'PUBLIC', 'kind': 'special'}]
        try:
            for rr in query_fn(
                "SELECT rolname, rolcanlogin FROM pg_catalog.pg_roles "
                "WHERE rolname NOT LIKE 'pg\\_%' ESCAPE '\\' ORDER BY rolname"
            ):
                principals.append({
                    'name': str(rr['rolname']),
                    'kind': 'user' if rr.get('rolcanlogin') else 'role',
                })
        except Exception:
            pass

        columns: list[str] = []
        raw_grants: list[dict[str, Any]] = []

        if obj_kind in {'table', 'view', 'sequence'}:
            c_rows = query_fn(
                'SELECT a.attname AS cname '
                'FROM pg_catalog.pg_attribute a '
                'JOIN pg_catalog.pg_class c ON c.oid = a.attrelid '
                'JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace '
                'WHERE n.nspname = %s AND c.relname = %s AND a.attnum > 0 AND NOT a.attisdropped '
                'ORDER BY a.attnum',
                (eff_schema, obj_name),
            )
            columns = [str(r['cname']) for r in c_rows if r.get('cname')]
            acl_rows = query_fn(
                "SELECT pg_catalog.pg_get_userbyid(x.grantor) AS grantor, "
                "CASE WHEN x.grantee = 0 THEN 'PUBLIC' ELSE pg_catalog.pg_get_userbyid(x.grantee) END AS grantee, "
                "CASE WHEN x.grantee = 0 THEN 'special' "
                "WHEN EXISTS(SELECT 1 FROM pg_catalog.pg_roles r WHERE r.oid = x.grantee AND r.rolcanlogin) THEN 'user' "
                "ELSE 'role' END AS grantee_kind, "
                "x.privilege_type AS privilege, x.is_grantable AS grant_option "
                "FROM pg_catalog.pg_class c "
                "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace, "
                "LATERAL pg_catalog.aclexplode(c.relacl) x "
                "WHERE n.nspname = %s AND c.relname = %s",
                (eff_schema, obj_name),
            )
            raw_grants.extend(acl_rows)
            if supports_col_privs:
                col_acl_rows = query_fn(
                    "SELECT a.attname AS column, "
                    "pg_catalog.pg_get_userbyid(x.grantor) AS grantor, "
                    "CASE WHEN x.grantee = 0 THEN 'PUBLIC' ELSE pg_catalog.pg_get_userbyid(x.grantee) END AS grantee, "
                    "CASE WHEN x.grantee = 0 THEN 'special' "
                    "WHEN EXISTS(SELECT 1 FROM pg_catalog.pg_roles r WHERE r.oid = x.grantee AND r.rolcanlogin) THEN 'user' "
                    "ELSE 'role' END AS grantee_kind, "
                    "x.privilege_type AS privilege, x.is_grantable AS grant_option "
                    "FROM pg_catalog.pg_attribute a "
                    "JOIN pg_catalog.pg_class c ON c.oid = a.attrelid "
                    "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace, "
                    "LATERAL pg_catalog.aclexplode(a.attacl) x "
                    "WHERE n.nspname = %s AND c.relname = %s AND a.attnum > 0 AND NOT a.attisdropped",
                    (eff_schema, obj_name),
                )
                raw_grants.extend(col_acl_rows)
        elif obj_kind in {'function', 'procedure'}:
            acl_rows = query_fn(
                "SELECT pg_catalog.pg_get_userbyid(x.grantor) AS grantor, "
                "CASE WHEN x.grantee = 0 THEN 'PUBLIC' ELSE pg_catalog.pg_get_userbyid(x.grantee) END AS grantee, "
                "CASE WHEN x.grantee = 0 THEN 'special' "
                "WHEN EXISTS(SELECT 1 FROM pg_catalog.pg_roles r WHERE r.oid = x.grantee AND r.rolcanlogin) THEN 'user' "
                "ELSE 'role' END AS grantee_kind, "
                "x.privilege_type AS privilege, x.is_grantable AS grant_option "
                "FROM pg_catalog.pg_proc p "
                "JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace, "
                "LATERAL pg_catalog.aclexplode(p.proacl) x "
                "WHERE n.nspname = %s AND p.proname = %s",
                (eff_schema, obj_name),
            )
            raw_grants.extend(acl_rows)
        elif obj_kind in {'type', 'domain'}:
            acl_rows = query_fn(
                "SELECT pg_catalog.pg_get_userbyid(x.grantor) AS grantor, "
                "CASE WHEN x.grantee = 0 THEN 'PUBLIC' ELSE pg_catalog.pg_get_userbyid(x.grantee) END AS grantee, "
                "CASE WHEN x.grantee = 0 THEN 'special' "
                "WHEN EXISTS(SELECT 1 FROM pg_catalog.pg_roles r WHERE r.oid = x.grantee AND r.rolcanlogin) THEN 'user' "
                "ELSE 'role' END AS grantee_kind, "
                "x.privilege_type AS privilege, x.is_grantable AS grant_option "
                "FROM pg_catalog.pg_type t "
                "JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace, "
                "LATERAL pg_catalog.aclexplode(t.typacl) x "
                "WHERE n.nspname = %s AND t.typname = %s",
                (eff_schema, obj_name),
            )
            raw_grants.extend(acl_rows)
        elif obj_kind == 'schema':
            target_nsp = obj_name or eff_schema
            acl_rows = query_fn(
                "SELECT pg_catalog.pg_get_userbyid(x.grantor) AS grantor, "
                "CASE WHEN x.grantee = 0 THEN 'PUBLIC' ELSE pg_catalog.pg_get_userbyid(x.grantee) END AS grantee, "
                "CASE WHEN x.grantee = 0 THEN 'special' "
                "WHEN EXISTS(SELECT 1 FROM pg_catalog.pg_roles r WHERE r.oid = x.grantee AND r.rolcanlogin) THEN 'user' "
                "ELSE 'role' END AS grantee_kind, "
                "x.privilege_type AS privilege, x.is_grantable AS grant_option "
                "FROM pg_catalog.pg_namespace n, "
                "LATERAL pg_catalog.aclexplode(n.nspacl) x "
                "WHERE n.nspname = %s",
                (target_nsp,),
            )
            raw_grants.extend(acl_rows)
        elif obj_kind == 'database':
            acl_rows = query_fn(
                "SELECT pg_catalog.pg_get_userbyid(x.grantor) AS grantor, "
                "CASE WHEN x.grantee = 0 THEN 'PUBLIC' ELSE pg_catalog.pg_get_userbyid(x.grantee) END AS grantee, "
                "CASE WHEN x.grantee = 0 THEN 'special' "
                "WHEN EXISTS(SELECT 1 FROM pg_catalog.pg_roles r WHERE r.oid = x.grantee AND r.rolcanlogin) THEN 'user' "
                "ELSE 'role' END AS grantee_kind, "
                "x.privilege_type AS privilege, x.is_grantable AS grant_option "
                "FROM pg_catalog.pg_database d, "
                "LATERAL pg_catalog.aclexplode(d.datacl) x "
                "WHERE d.datname = %s",
                (obj_name,),
            )
            raw_grants.extend(acl_rows)

        return {
            'engine': engine_id,
            'supported': True,
            'object': {
                'kind': obj_kind,
                'schema': None if obj_kind in {'database', 'schema'} else eff_schema,
                'name': obj_name,
            },
            'capabilities': {
                'can_edit': True,
                'reason': '',
                'supported_privileges': supported_privs,
                'supports_grant_option': True,
                'supports_column_privileges': supports_col_privs,
                'columns': columns,
            },
            'principals': principals,
            'grants': normalize_grants_matrix(raw_grants, supported_privs),
        }

    def _collect_mysql_family_object_grants(
        self,
        engine_id: str,
        is_mariadb: bool,
        query_fn: Callable,
        obj_kind: str,
        schema: str | None,
        obj_name: str,
        supported_privs: list[str],
        supports_col_privs: bool,
    ) -> dict[str, Any]:
        db_name = schema or obj_name
        principals: list[dict[str, Any]] = []
        try:
            if is_mariadb:
                for pr in query_fn('SELECT User AS u, Host AS h, is_role FROM mysql.user ORDER BY User, Host'):
                    if str(pr.get('is_role') or '').upper() == 'Y':
                        principals.append({'name': str(pr['u']), 'kind': 'role', 'host': None})
                    else:
                        principals.append({'name': str(pr['u']), 'kind': 'user', 'host': str(pr['h'])})
            else:
                for pr in query_fn('SELECT User AS u, Host AS h FROM mysql.user ORDER BY User, Host'):
                    principals.append({'name': str(pr['u']), 'kind': 'user', 'host': str(pr['h'])})
        except Exception:
            pass

        columns: list[str] = []
        if obj_kind in {'table', 'view'} and db_name and obj_name:
            try:
                c_rows = query_fn(
                    'SELECT COLUMN_NAME AS cname FROM information_schema.COLUMNS '
                    'WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION',
                    (db_name, obj_name),
                )
                columns = [str(r['cname']) for r in c_rows if r.get('cname')]
            except Exception:
                pass

        raw_grants: list[dict[str, Any]] = []
        if obj_kind in {'database', 'schema'}:
            g_rows = query_fn(
                'SELECT GRANTEE AS grantee, PRIVILEGE_TYPE AS priv, IS_GRANTABLE AS gopt '
                'FROM information_schema.SCHEMA_PRIVILEGES WHERE TABLE_SCHEMA = %s',
                (obj_name or db_name,),
            )
            for gr in g_rows:
                u, h = parse_mysql_grantee_string(str(gr.get('grantee') or ''))
                raw_grants.append({
                    'grantee': u,
                    'grantee_kind': 'role' if (is_mariadb and h == '') else 'user',
                    'grantee_host': None if (is_mariadb and h == '') else h,
                    'grantor': '',
                    'privilege': str(gr.get('priv') or '').upper(),
                    'grant_option': str(gr.get('gopt') or '').upper() == 'YES',
                })
        elif obj_kind in {'table', 'view', 'sequence'}:
            g_rows = query_fn(
                'SELECT GRANTEE AS grantee, PRIVILEGE_TYPE AS priv, IS_GRANTABLE AS gopt '
                'FROM information_schema.TABLE_PRIVILEGES '
                'WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s',
                (db_name, obj_name),
            )
            for gr in g_rows:
                u, h = parse_mysql_grantee_string(str(gr.get('grantee') or ''))
                raw_grants.append({
                    'grantee': u,
                    'grantee_kind': 'role' if (is_mariadb and h == '') else 'user',
                    'grantee_host': None if (is_mariadb and h == '') else h,
                    'grantor': '',
                    'privilege': str(gr.get('priv') or '').upper(),
                    'grant_option': str(gr.get('gopt') or '').upper() == 'YES',
                })
            if supports_col_privs:
                cg_rows = query_fn(
                    'SELECT GRANTEE AS grantee, COLUMN_NAME AS cname, PRIVILEGE_TYPE AS priv, IS_GRANTABLE AS gopt '
                    'FROM information_schema.COLUMN_PRIVILEGES '
                    'WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s',
                    (db_name, obj_name),
                )
                for cgr in cg_rows:
                    u, h = parse_mysql_grantee_string(str(cgr.get('grantee') or ''))
                    raw_grants.append({
                        'grantee': u,
                        'grantee_kind': 'role' if (is_mariadb and h == '') else 'user',
                        'grantee_host': None if (is_mariadb and h == '') else h,
                        'grantor': '',
                        'privilege': str(cgr.get('priv') or '').upper(),
                        'grant_option': str(cgr.get('gopt') or '').upper() == 'YES',
                        'column': str(cgr.get('cname') or ''),
                    })
        elif obj_kind in {'procedure', 'function', 'package'}:
            try:
                p_rows = query_fn(
                    'SELECT User AS u, Host AS h, Grantor AS grantor, Proc_priv AS ppriv '
                    'FROM mysql.procs_priv WHERE Db = %s AND Routine_name = %s AND Routine_type = %s',
                    (db_name, obj_name, obj_kind.upper()),
                )
                for pr in p_rows:
                    u, h = str(pr.get('u') or ''), str(pr.get('h') or '')
                    parts = {s.strip().lower() for s in str(pr.get('ppriv') or '').split(',') if s.strip()}
                    gopt = 'grant' in parts
                    for token, priv_label in (('execute', 'EXECUTE'), ('alter routine', 'ALTER ROUTINE')):
                        if token in parts:
                            raw_grants.append({
                                'grantee': u,
                                'grantee_kind': 'role' if (is_mariadb and h == '') else 'user',
                                'grantee_host': None if (is_mariadb and h == '') else h,
                                'grantor': str(pr.get('grantor') or ''),
                                'privilege': priv_label,
                                'grant_option': gopt,
                            })
            except Exception:
                pass

        return {
            'engine': engine_id,
            'supported': True,
            'object': {'kind': obj_kind, 'schema': db_name, 'name': obj_name},
            'capabilities': {
                'can_edit': True,
                'reason': '',
                'supported_privileges': supported_privs,
                'supports_grant_option': True,
                'supports_column_privileges': supports_col_privs,
                'columns': columns,
            },
            'principals': principals,
            'grants': normalize_grants_matrix(raw_grants, supported_privs),
        }

    # ------------------------------------------------------------------
    # 4. POST /object_grants/plan & /object_grants/apply
    # ------------------------------------------------------------------
    def plan_object_grants(self, body: Mapping[str, Any]) -> dict[str, Any]:
        sid = int(body.get('sid') or 0)
        info = self._resolve_target_info(sid)
        return compile_object_grants_plan(
            info['engine_id'],
            str(body.get('object_kind') or 'table'),
            body.get('schema'),
            str(body.get('object_name') or ''),
            list(body.get('changes') or []),
            routine_signature=body.get('routine_signature'),
        )

    def apply_object_grants(self, body: Mapping[str, Any]) -> dict[str, Any]:
        sid = int(body.get('sid') or 0)
        info = self._resolve_target_info(sid)
        compiled = compile_object_grants_plan(
            info['engine_id'],
            str(body.get('object_kind') or 'table'),
            body.get('schema'),
            str(body.get('object_name') or ''),
            list(body.get('changes') or []),
            routine_signature=body.get('routine_signature'),
        )
        with self._open_connection(info, body.get('database_target_id'), write=True) as (_query_fn, exec_fn):
            exec_fn(compiled['statements'])
        return {
            'applied': True,
            'preview_sql': compiled['preview_sql'],
            'statement_count': len(compiled['statements']),
        }


def init_app(app, workspace_service=None) -> SecurityAuthorityHost:
    existing = app.extensions.get(SECURITY_AUTHORITY_EXTENSION_KEY)
    if existing is not None:
        return existing

    host = SecurityAuthorityHost(app, workspace_service)
    app.extensions[SECURITY_AUTHORITY_EXTENSION_KEY] = host

    bp = Blueprint(
        'cdeadmin_security_authority',
        __name__,
        url_prefix='/cdeadmin/api/security',
    )

    try:
        from pgadmin import pgCSRFProtect
        csrf_exempt = pgCSRFProtect.exempt
    except Exception:
        def csrf_exempt(fn):
            return fn

    def _require_auth():
        if not current_app.config.get('SERVER_MODE', True):
            return None
        if current_user and getattr(current_user, 'is_authenticated', False):
            return None
        return jsonify({'error': 'Authentication required', 'code': 'unauthenticated'}), 401

    def _is_credential_required_exception(exc: BaseException) -> bool:
        cls_name = exc.__class__.__name__
        msg = str(exc).lower()
        if cls_name == 'SecretAccessError':
            return True
        if cls_name == 'EndpointRegistrationError' and 'verified' in msg:
            return True
        if 'no password supplied' in msg or 'endpoint credentials are required' in msg:
            return True
        return False

    @bp.route('/principals', methods=['GET'])
    @csrf_exempt
    def get_principals_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        try:
            sid = int(request.args.get('sid') or 0)
            db_target = request.args.get('database_target_id') or None
            scope = str(request.args.get('scope') or 'server').strip().lower()
            return jsonify(host.get_principals(sid, db_target, scope))
        except LookupError as exc:
            return jsonify({'error': str(exc), 'code': 'not_found'}), 404
        except SecurityAuthorityError as exc:
            return jsonify({'error': str(exc), 'code': 'invalid_request'}), 400
        except Exception as exc:
            if _is_credential_required_exception(exc):
                return jsonify({'error': str(exc), 'code': 'CREDENTIAL_REQUIRED'}), 401
            return jsonify({'error': str(exc), 'code': 'security_error'}), 400

    @bp.route('/principal/plan', methods=['POST'])
    @csrf_exempt
    def post_principal_plan_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        body = request.get_json(silent=True) or {}
        try:
            return jsonify(host.plan_principal(body))
        except LookupError as exc:
            return jsonify({'error': str(exc), 'code': 'not_found'}), 404
        except SecurityAuthorityError as exc:
            return jsonify({'error': str(exc), 'code': 'validation_error'}), 400
        except Exception as exc:
            return jsonify({'error': str(exc), 'code': 'plan_failed'}), 400

    @bp.route('/principal/apply', methods=['POST'])
    @csrf_exempt
    def post_principal_apply_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        body = request.get_json(silent=True) or {}
        try:
            return jsonify(host.apply_principal(body))
        except LookupError as exc:
            return jsonify({'error': str(exc), 'code': 'not_found'}), 404
        except PermissionError as exc:
            return jsonify({'error': str(exc), 'code': 'forbidden'}), 403
        except SecurityAuthorityError as exc:
            return jsonify({'error': str(exc), 'code': 'validation_error'}), 400
        except Exception as exc:
            if _is_credential_required_exception(exc):
                return jsonify({'error': str(exc), 'code': 'CREDENTIAL_REQUIRED'}), 401
            return jsonify({'error': str(exc), 'code': 'apply_failed'}), 400

    @bp.route('/object_grants', methods=['GET'])
    @csrf_exempt
    def get_object_grants_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        try:
            return jsonify(host.get_object_grants(request.args))
        except LookupError as exc:
            return jsonify({'error': str(exc), 'code': 'not_found'}), 404
        except SecurityAuthorityError as exc:
            return jsonify({'error': str(exc), 'code': 'invalid_request'}), 400
        except Exception as exc:
            if _is_credential_required_exception(exc):
                return jsonify({'error': str(exc), 'code': 'CREDENTIAL_REQUIRED'}), 401
            return jsonify({'error': str(exc), 'code': 'grants_error'}), 400

    @bp.route('/object_grants/plan', methods=['POST'])
    @csrf_exempt
    def post_object_grants_plan_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        body = request.get_json(silent=True) or {}
        try:
            return jsonify(host.plan_object_grants(body))
        except LookupError as exc:
            return jsonify({'error': str(exc), 'code': 'not_found'}), 404
        except SecurityAuthorityError as exc:
            return jsonify({'error': str(exc), 'code': 'validation_error'}), 400
        except Exception as exc:
            return jsonify({'error': str(exc), 'code': 'plan_failed'}), 400

    @bp.route('/object_grants/apply', methods=['POST'])
    @csrf_exempt
    def post_object_grants_apply_route():
        denied = _require_auth()
        if denied is not None:
            return denied
        body = request.get_json(silent=True) or {}
        try:
            return jsonify(host.apply_object_grants(body))
        except LookupError as exc:
            return jsonify({'error': str(exc), 'code': 'not_found'}), 404
        except PermissionError as exc:
            return jsonify({'error': str(exc), 'code': 'forbidden'}), 403
        except SecurityAuthorityError as exc:
            return jsonify({'error': str(exc), 'code': 'validation_error'}), 400
        except Exception as exc:
            if _is_credential_required_exception(exc):
                return jsonify({'error': str(exc), 'code': 'CREDENTIAL_REQUIRED'}), 401
            return jsonify({'error': str(exc), 'code': 'apply_failed'}), 400

    if 'cdeadmin_security_authority' not in app.blueprints:
        app.register_blueprint(bp)

    return host

"""PostgreSQL pg_init_privs extension privilege-baseline capture and delta reconstruction (PG-AUDIT-EXTACL-01).

PostgreSQL records initial privileges of extension-member objects in `pg_catalog.pg_init_privs`
(`privtype = 'e'`). Reconstructing or migrating post-installation security changes on extension
objects requires diffing the object's current ACL (`relacl`, `proacl`, `typacl`, `nspacl`, or
column `attacl` for `objsubid > 0`) against `initprivs` so built-in extension grants are never
duplicated and post-install `REVOKE`/`GRANT` customizations are preserved accurately.
"""
from __future__ import annotations

from typing import Iterable

from .native_admin import _identifier

PRIV_MAP_RELATION = {
    'r': 'SELECT',
    'a': 'INSERT',
    'w': 'UPDATE',
    'd': 'DELETE',
    'D': 'TRUNCATE',
    'x': 'REFERENCES',
    't': 'TRIGGER',
    'm': 'MAINTAIN',
}
PRIV_MAP_SEQUENCE = {
    'r': 'SELECT',
    'w': 'UPDATE',
    'U': 'USAGE',
}
PRIV_MAP_COLUMN = {
    'r': 'SELECT',
    'a': 'INSERT',
    'w': 'UPDATE',
    'x': 'REFERENCES',
}
PRIV_MAP_ROUTINE = {'X': 'EXECUTE'}
PRIV_MAP_TYPE = {'U': 'USAGE'}
PRIV_MAP_SCHEMA = {'U': 'USAGE', 'C': 'CREATE'}


def _unquote_acl_role(raw: str) -> str:
    if raw == '':
        return 'PUBLIC'
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        out = []
        i = 1
        while i < len(raw) - 1:
            if raw[i] == '\\' and i + 1 < len(raw) - 1:
                out.append(raw[i + 1])
                i += 2
            elif raw[i] == '"' and i + 1 < len(raw) - 1 and raw[i + 1] == '"':
                out.append('"')
                i += 2
            else:
                out.append(raw[i])
                i += 1
        return ''.join(out)
    return raw


def _split_unquoted(text: str, sep: str) -> tuple[str, str]:
    in_quotes = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '\\' and in_quotes:
            i += 2
            continue
        if ch == '"':
            in_quotes = not in_quotes
        elif ch == sep and not in_quotes:
            return text[:i], text[i + 1:]
        i += 1
    raise ValueError(f'Invalid PostgreSQL aclitem {text!r}: missing {sep!r}')


def parse_acl_array(acl_items: Iterable[str] | None, code_map: dict[str, str]) -> dict[tuple[str, str], bool]:
    """Return {(grantee, privilege_word): is_grantable} for a PostgreSQL aclitem[] list."""
    grants: dict[tuple[str, str], bool] = {}
    if not acl_items:
        return grants
    for item in acl_items:
        if not isinstance(item, str) or '=' not in item:
            continue
        grantee_raw, rest = _split_unquoted(item, '=')
        privs_raw, _grantor_raw = _split_unquoted(rest, '/')
        grantee = _unquote_acl_role(grantee_raw)
        i = 0
        while i < len(privs_raw):
            code = privs_raw[i]
            grantable = (i + 1 < len(privs_raw) and privs_raw[i + 1] == '*')
            i += 2 if grantable else 1
            word = code_map.get(code)
            if word:
                grants[(grantee, word)] = grantable
    return grants


def _format_grantee(grantee: str) -> str:
    return 'PUBLIC' if grantee == 'PUBLIC' else _identifier(grantee, 'grantee')


def _code_map_and_target(row: dict, subid: int = 0) -> tuple[dict[str, str], str, str] | None:
    kind = row.get('kind') or row.get('resource_kind')
    native = row.get('native') or {}
    schema = native.get('schema')
    crow = native.get('catalog_row') or {}

    if subid > 0:
        if kind not in {'table', 'partitioned-table', 'view', 'materialized-view', 'foreign-table'}:
            return None
        attrs = (native.get('children') or {}).get('pg_attribute') or []
        col = next((a for a in attrs if int(a.get('attnum', 0)) == subid), None)
        if not col or not schema or not crow.get('relname'):
            return None
        col_q = _identifier(col['attname'], 'column')
        tbl_q = f'{_identifier(schema, "schema")}.{_identifier(crow["relname"], "table")}'
        return PRIV_MAP_COLUMN, f'({col_q}) ON TABLE {tbl_q}', col.get('attacl')

    if kind in {'table', 'partitioned-table', 'view', 'materialized-view', 'foreign-table'}:
        if not schema or not crow.get('relname'):
            return None
        return PRIV_MAP_RELATION, f'TABLE {_identifier(schema, "schema")}.{_identifier(crow["relname"], "table")}', crow.get('relacl')
    if kind == 'sequence':
        if not schema or not crow.get('relname'):
            return None
        return PRIV_MAP_SEQUENCE, f'SEQUENCE {_identifier(schema, "schema")}.{_identifier(crow["relname"], "sequence")}', crow.get('relacl')
    if kind in {'function', 'procedure', 'window-function'}:
        ident = native.get('sql_identity')
        if not ident:
            return None
        kw = 'PROCEDURE' if kind == 'procedure' else 'FUNCTION'
        return PRIV_MAP_ROUTINE, f'{kw} {ident}', crow.get('proacl')
    if kind in {'type', 'domain'}:
        ident = native.get('sql_identity') or (f'{_identifier(schema, "schema")}.{_identifier(crow.get("typname", ""), "type")}' if schema and crow.get('typname') else None)
        if not ident:
            return None
        kw = 'DOMAIN' if kind == 'domain' else 'TYPE'
        return PRIV_MAP_TYPE, f'{kw} {ident}', crow.get('typacl')
    if kind == 'schema':
        nsp = crow.get('nspname') or row.get('name') or row.get('display_name')
        if not nsp:
            return None
        return PRIV_MAP_SCHEMA, f'SCHEMA {_identifier(nsp, "schema")}', crow.get('nspacl')
    return None


def _diff_acl_maps(base_map: dict[tuple[str, str], bool], target_map: dict[tuple[str, str], bool], target_clause: str, is_column: bool = False) -> list[str]:
    statements: list[str] = []
    # 1. Revocations or grant-option downgrades
    for (grantee, word), base_go in sorted(base_map.items()):
        if (grantee, word) not in target_map:
            if is_column:
                col_part, on_part = target_clause.split(' ON ', 1)
                statements.append(f'REVOKE {word} {col_part} ON {on_part} FROM {_format_grantee(grantee)}')
            else:
                statements.append(f'REVOKE {word} ON {target_clause} FROM {_format_grantee(grantee)}')
        elif base_go and not target_map[(grantee, word)]:
            if is_column:
                col_part, on_part = target_clause.split(' ON ', 1)
                statements.append(f'REVOKE GRANT OPTION FOR {word} {col_part} ON {on_part} FROM {_format_grantee(grantee)}')
            else:
                statements.append(f'REVOKE GRANT OPTION FOR {word} ON {target_clause} FROM {_format_grantee(grantee)}')
    # 2. Additions or grant-option upgrades
    for (grantee, word), target_go in sorted(target_map.items()):
        if (grantee, word) not in base_map or (target_go and not base_map[(grantee, word)]):
            wgo = ' WITH GRANT OPTION' if target_go else ''
            if is_column:
                col_part, on_part = target_clause.split(' ON ', 1)
                statements.append(f'GRANT {word} {col_part} ON {on_part} TO {_format_grantee(grantee)}{wgo}')
            else:
                statements.append(f'GRANT {word} ON {target_clause} TO {_format_grantee(grantee)}{wgo}')
    return statements


def reconstruct_extension_acl_deltas(row: dict) -> list[str]:
    """Emit post-extension GRANT/REVOKE statements comparing current ACLs against pg_init_privs."""
    native = row.get('native') or {}
    init_records = native.get('initial_privileges') or []
    if not init_records:
        return []
    statements: list[str] = []
    for rec in sorted(init_records, key=lambda r: int(r.get('objsubid', 0))):
        if rec.get('privtype') != 'e':
            continue
        subid = int(rec.get('objsubid', 0))
        info = _code_map_and_target(row, subid)
        if info is None:
            continue
        code_map, target_clause, current_acl = info
        init_acl = rec.get('initprivs') or []
        # Note: if current_acl is None after an object had non-empty initprivs, all grants were revoked or reset;
        # when current_acl is explicitly present (including '{}'), compare exact ACL sets.
        eff_current = [] if current_acl == [] else (current_acl if current_acl is not None else init_acl)
        base_map = parse_acl_array(init_acl, code_map)
        curr_map = parse_acl_array(eff_current, code_map)
        statements.extend(_diff_acl_maps(base_map, curr_map, target_clause, is_column=subid > 0))
    return statements


def diff_row_acl_transition(before_row: dict, after_row: dict) -> list[str]:
    """Emit GRANT/REVOKE statements transitioning an object (including extension members) from before_row to after_row."""
    statements: list[str] = []
    info_before = _code_map_and_target(before_row, 0)
    info_after = _code_map_and_target(after_row, 0)
    if info_before is not None and info_after is not None:
        code_map, target_clause, acl_b = info_before
        _, _, acl_a = info_after
        if acl_b != acl_a and acl_b is not None and acl_a is not None:
            statements.extend(
                _diff_acl_maps(parse_acl_array(acl_b, code_map), parse_acl_array(acl_a, code_map), target_clause, False)
            )
    return statements

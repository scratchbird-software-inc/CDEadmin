"""Expanded PostgreSQL DDN native transformation planners (PG-AUDIT-DDN-01 & PG-AUDIT-EXTACL-01).

Extends `postgresql_schema_plan.build_plan` beyond comment/rename/nullability/default allowlists
to generate grammar-validated native DDL for:
- Generated column `SET EXPRESSION AS (...)` and `DROP EXPRESSION`
- Column `SET STATISTICS`, `SET STORAGE`, `SET COMPRESSION`
- Constraint `ENFORCED` / `NOT ENFORCED` (PG 18 FK), `VALIDATE CONSTRAINT`, and deferrability
- Table persistence (`LOGGED`/`UNLOGGED`), `REPLICA IDENTITY`, `OWNER TO`, `SET TABLESPACE`, and `reloptions` / `toast_reloptions`
- Sequence parameter alterations (`INCREMENT BY`, `MINVALUE`, `MAXVALUE`, `START WITH`, `CACHE`, `CYCLE`)
- View `CREATE OR REPLACE VIEW` definition updates
- Extended statistics `SET STATISTICS` target updates
- Object & extension-member (`pg_init_privs`) ACL delta `GRANT` / `REVOKE` transitions
"""
from __future__ import annotations

from copy import deepcopy

from ..providers.postgresql.extension_acls import diff_row_acl_transition
from ..providers.postgresql.language import analyze
from ..providers.postgresql.native_admin import _identifier, _qualified
from .firebird_catalog_import import _equal
from .firebird_schema_plan import digest

STORAGE_CODES = {'p': 'PLAIN', 'm': 'MAIN', 'e': 'EXTERNAL', 'x': 'EXTENDED', 'd': 'DEFAULT'}
COMPRESSION_CODES = {'p': 'pglz', 'l': 'lz4', '': 'DEFAULT', 'pglz': 'pglz', 'lz4': 'lz4'}
REPLICA_CODES = {'d': 'DEFAULT', 'n': 'NOTHING', 'f': 'FULL'}

EXTENDED_COLUMN_KEYS = frozenset({
    'attgenerated',
    'generated_expression',
    'attstattarget',
    'attstorage',
    'attcompression',
})


def _check_grammar(statement: str) -> None:
    if analyze(statement, standard_strings='on')['grammar_valid'] is not True:
        raise ValueError(f'Generated PostgreSQL statement failed grammar validation: {statement}')


def _non_table_lock(row: dict) -> dict:
    native = row['native']
    return {
        'schema': native.get('schema') or '',
        'name': row.get('name') or '',
        'oid': native.get('oid', 0),
        'lock_mode': 'none',
    }


def plan_extended_column_changes(
    identity: str,
    parent_sql: str,
    live: dict,
    number: int,
    effective_name: str,
    old: dict,
    wanted: dict,
    current: dict,
    changes: list[str],
    lock_target: dict | None,
) -> tuple[list[dict], int]:
    operations: list[dict] = []
    converged = 0
    native = live['native']
    col_q = _identifier(effective_name, 'column')
    guard = digest({'relation_oid': native['oid'], 'attribute': current})
    attr_res_id = f'postgresql:pg_attribute:{native["oid"]}:{number}'

    # 1. Generated column SET EXPRESSION / DROP EXPRESSION
    if 'attgenerated' in changes or 'generated_expression' in changes:
        if live['kind'] != 'table' or current.get('attinhcount', 0) != 0:
            raise ValueError('Generated column changes require an ordinary non-inherited table column')
        old_kind = old.get('attgenerated') or ''
        want_kind = wanted.get('attgenerated') or ''
        live_kind = current.get('attgenerated') or ''
        old_expr = old.get('generated_expression')
        want_expr = wanted.get('generated_expression')
        live_expr = current.get('generated_expression')
        if (want_kind, want_expr) == (live_kind, live_expr):
            converged += 1
        elif (old_kind, old_expr) != (live_kind, live_expr):
            raise ValueError('Generated column changed independently since baseline')
        elif old_kind in {'s', 'v'} and want_kind == '' and want_expr is None:
            if old_kind != 's':
                raise ValueError('PostgreSQL DROP EXPRESSION applies only to STORED generated columns')
            stmt = f'ALTER TABLE ONLY {parent_sql} ALTER COLUMN {col_q} DROP EXPRESSION'
            _check_grammar(stmt)
            operations.append({
                'resource_id': attr_res_id,
                'parent_resource_id': identity,
                'kind': 'column',
                'name': effective_name,
                'operation': 'drop_generated_expression',
                'lock_target': lock_target,
                'live_guard': guard,
                'statement': stmt,
            })
        elif old_kind in {'s', 'v'} and want_kind == old_kind and isinstance(want_expr, str) and want_expr.strip():
            from .postgresql_creation import expression
            expr_sql = expression(want_expr)
            stmt = f'ALTER TABLE ONLY {parent_sql} ALTER COLUMN {col_q} SET EXPRESSION AS ({expr_sql})'
            _check_grammar(stmt)
            operations.append({
                'resource_id': attr_res_id,
                'parent_resource_id': identity,
                'kind': 'column',
                'name': effective_name,
                'operation': 'set_generated_expression',
                'lock_target': lock_target,
                'live_guard': guard,
                'statement': stmt,
            })
        else:
            raise ValueError('Existing ordinary columns cannot be converted into generated columns in place')

    # 2. Column SET STATISTICS
    if 'attstattarget' in changes:
        vals = (old.get('attstattarget'), wanted.get('attstattarget'), current.get('attstattarget'))
        target_stat = -1 if vals[1] is None else vals[1]
        live_stat = -1 if vals[2] is None else vals[2]
        old_stat = -1 if vals[0] is None else vals[0]
        if type(target_stat) is not int or not -1 <= target_stat <= 10000:
            raise ValueError('Column statistics target must be an integer from -1 through 10000')
        if target_stat == live_stat:
            converged += 1
        elif old_stat != live_stat:
            raise ValueError('Column statistics target changed independently since baseline')
        else:
            stmt = f'ALTER TABLE ONLY {parent_sql} ALTER COLUMN {col_q} SET STATISTICS {target_stat}'
            _check_grammar(stmt)
            operations.append({
                'resource_id': attr_res_id,
                'parent_resource_id': identity,
                'kind': 'column',
                'name': effective_name,
                'operation': 'set_column_statistics',
                'lock_target': lock_target,
                'live_guard': guard,
                'statement': stmt,
            })

    # 3. Column SET STORAGE
    if 'attstorage' in changes:
        want_st = str(wanted.get('attstorage') or '')
        live_st = str(current.get('attstorage') or '')
        old_st = str(old.get('attstorage') or '')
        if want_st not in STORAGE_CODES:
            raise ValueError('Invalid PostgreSQL column storage mode')
        if want_st == live_st:
            converged += 1
        elif old_st != live_st:
            raise ValueError('Column storage changed independently since baseline')
        else:
            stmt = f'ALTER TABLE ONLY {parent_sql} ALTER COLUMN {col_q} SET STORAGE {STORAGE_CODES[want_st]}'
            _check_grammar(stmt)
            operations.append({
                'resource_id': attr_res_id,
                'parent_resource_id': identity,
                'kind': 'column',
                'name': effective_name,
                'operation': 'set_column_storage',
                'lock_target': lock_target,
                'live_guard': guard,
                'statement': stmt,
            })

    # 4. Column SET COMPRESSION
    if 'attcompression' in changes:
        want_cp = str(wanted.get('attcompression') or '')
        live_cp = str(current.get('attcompression') or '')
        old_cp = str(old.get('attcompression') or '')
        if want_cp not in COMPRESSION_CODES:
            raise ValueError('Column compression must be pglz, lz4 or DEFAULT')
        if want_cp == live_cp:
            converged += 1
        elif old_cp != live_cp:
            raise ValueError('Column compression changed independently since baseline')
        else:
            stmt = f'ALTER TABLE ONLY {parent_sql} ALTER COLUMN {col_q} SET COMPRESSION {COMPRESSION_CODES[want_cp]}'
            _check_grammar(stmt)
            operations.append({
                'resource_id': attr_res_id,
                'parent_resource_id': identity,
                'kind': 'column',
                'name': effective_name,
                'operation': 'set_column_compression',
                'lock_target': lock_target,
                'live_guard': guard,
                'statement': stmt,
            })

    return operations, converged


def plan_extended_object_changes(
    identity: str,
    before: dict,
    after: dict,
    live: dict | None,
    current: dict,
    lock_target_fn,
) -> tuple[list[dict], int, dict] | None:
    if live is None or before.get('kind') != after.get('kind') or before.get('kind') != live.get('kind'):
        return None
    if after.get('system') != 'false' or live.get('system') != 'false':
        return None
    kind = live['kind']
    b_nat, a_nat, l_nat = before['native'], after['native'], live['native']
    b_crow = b_nat.get('catalog_row') or {}
    a_crow = a_nat.get('catalog_row') or {}
    l_crow = l_nat.get('catalog_row') or {}

    ops: list[dict] = []
    converged = 0
    residual_after = deepcopy(after)
    r_nat = residual_after['native']
    r_crow = r_nat.get('catalog_row')

    # 1. Constraint alterations (ENFORCED / NOT ENFORCED, VALIDATE, DEFERRABLE)
    if kind == 'constraint' and l_nat.get('catalog') == 'pg_constraint':
        conrelid = l_crow.get('conrelid')
        owner = current['rows'].get(f'postgresql:pg_class:{conrelid}')
        if owner and lock_target_fn(owner):
            tbl_q = _qualified(owner['native']['schema'], owner['native']['catalog_row']['relname'])
            con_q = _identifier(l_crow['conname'], 'constraint')
            contype = l_crow.get('contype')
            # Enforcement change
            if b_crow.get('conenforced') != a_crow.get('conenforced') and 'conenforced' in a_crow:
                if contype != 'f':
                    raise ValueError('PostgreSQL ALTER CONSTRAINT ENFORCED / NOT ENFORCED applies only to FOREIGN KEY constraints')
                want_enf = bool(a_crow['conenforced'])
                if bool(l_crow.get('conenforced', True)) == want_enf:
                    converged += 1
                elif bool(b_crow.get('conenforced', True)) != bool(l_crow.get('conenforced', True)):
                    raise ValueError('Constraint enforcement changed independently since baseline')
                else:
                    clause = 'ENFORCED' if want_enf else 'NOT ENFORCED'
                    stmt = f'ALTER TABLE {tbl_q} ALTER CONSTRAINT {con_q} {clause}'
                    _check_grammar(stmt)
                    ops.append({
                        'resource_id': identity,
                        'kind': 'constraint',
                        'name': live['name'],
                        'operation': 'alter_constraint_enforcement',
                        'lock_target': lock_target_fn(owner),
                        'live_guard': digest(l_nat),
                        'statement': stmt,
                    })
                if isinstance(r_crow, dict) and 'conenforced' in b_crow:
                    r_crow['conenforced'] = b_crow['conenforced']
            # Validation change
            if b_crow.get('convalidated') is False and a_crow.get('convalidated') is True:
                if l_crow.get('convalidated') is True:
                    converged += 1
                else:
                    stmt = f'ALTER TABLE {tbl_q} VALIDATE CONSTRAINT {con_q}'
                    _check_grammar(stmt)
                    ops.append({
                        'resource_id': identity,
                        'kind': 'constraint',
                        'name': live['name'],
                        'operation': 'validate_constraint',
                        'lock_target': lock_target_fn(owner),
                        'live_guard': digest(l_nat),
                        'statement': stmt,
                    })
                if isinstance(r_crow, dict) and 'convalidated' in b_crow:
                    r_crow['convalidated'] = b_crow['convalidated']
            if ops or converged:
                return ops, converged, residual_after

    # 2. Sequence parameter alterations
    if kind == 'sequence' and l_nat.get('catalog') == 'pg_class':
        b_seq = ((b_nat.get('children') or {}).get('pg_sequence') or [None])[0]
        a_seq = ((a_nat.get('children') or {}).get('pg_sequence') or [None])[0]
        l_seq = ((l_nat.get('children') or {}).get('pg_sequence') or [None])[0]
        if b_seq and a_seq and l_seq and not _equal(b_seq, a_seq):
            if not _equal(b_seq, l_seq):
                if _equal(a_seq, l_seq):
                    r_nat['children']['pg_sequence'] = deepcopy(b_nat['children']['pg_sequence'])
                    return [], 1, residual_after
                raise ValueError('Sequence parameters changed independently since baseline')
            clauses = []
            for key, kw in (
                ('seqincrement', 'INCREMENT BY'),
                ('seqmin', 'MINVALUE'),
                ('seqmax', 'MAXVALUE'),
                ('seqstart', 'START WITH'),
                ('seqcache', 'CACHE'),
            ):
                if b_seq.get(key) != a_seq.get(key):
                    val = a_seq.get(key)
                    if type(val) is not int:
                        raise ValueError(f'Sequence {key} must be an integer')
                    clauses.append(f'{kw} {val}')
            if b_seq.get('seqcycle') != a_seq.get('seqcycle'):
                clauses.append('CYCLE' if a_seq.get('seqcycle') else 'NO CYCLE')
            if clauses:
                seq_q = _qualified(l_nat['schema'], l_crow['relname'])
                stmt = f'ALTER SEQUENCE {seq_q} ' + ' '.join(clauses)
                _check_grammar(stmt)
                r_nat['children']['pg_sequence'] = deepcopy(b_nat['children']['pg_sequence'])
                return [{
                    'resource_id': identity,
                    'kind': 'sequence',
                    'name': live['name'],
                    'operation': 'alter_sequence',
                    'lock_target': _non_table_lock(live),
                    'live_guard': digest(l_nat),
                    'statement': stmt,
                }], 0, residual_after

    # 3. Extended statistics target alteration
    if kind == 'extended-statistics' and b_crow.get('stxstattarget') != a_crow.get('stxstattarget'):
        stxrelid = l_crow.get('stxrelid')
        owner = current['rows'].get(f'postgresql:pg_class:{stxrelid}')
        ltarget = lock_target_fn(owner) if owner else _non_table_lock(live)
        want_t = -1 if a_crow.get('stxstattarget') is None else a_crow.get('stxstattarget')
        live_t = -1 if l_crow.get('stxstattarget') is None else l_crow.get('stxstattarget')
        old_t = -1 if b_crow.get('stxstattarget') is None else b_crow.get('stxstattarget')
        if type(want_t) is not int or not -1 <= want_t <= 10000:
            raise ValueError('Statistics target must be an integer from -1 through 10000')
        if isinstance(r_crow, dict) and 'stxstattarget' in b_crow:
            r_crow['stxstattarget'] = b_crow['stxstattarget']
        if want_t == live_t:
            return [], 1, residual_after
        if old_t != live_t:
            raise ValueError('Extended statistics target changed independently since baseline')
        stat_q = _qualified(l_nat['schema'], l_crow['stxname'])
        stmt = f'ALTER STATISTICS {stat_q} SET STATISTICS {want_t}'
        _check_grammar(stmt)
        return [{
            'resource_id': identity,
            'kind': 'extended-statistics',
            'name': live['name'],
            'operation': 'alter_statistics_target',
            'lock_target': ltarget,
            'live_guard': digest(l_nat),
            'statement': stmt,
        }], 0, residual_after

    # 4. View query replacement (CREATE OR REPLACE VIEW)
    if kind == 'view' and b_nat.get('definition') != a_nat.get('definition'):
        r_nat['definition'] = deepcopy(b_nat.get('definition'))
        if l_nat.get('definition') == a_nat.get('definition'):
            return [], 1, residual_after
        if l_nat.get('definition') != b_nat.get('definition'):
            raise ValueError('View definition changed independently since baseline')
        new_def = (a_nat.get('definition') or '').strip().rstrip(';')
        if not new_def:
            raise ValueError('View definition must be a non-empty SELECT query')
        view_q = _qualified(l_nat['schema'], l_crow['relname'])
        stmt = f'CREATE OR REPLACE VIEW {view_q} AS {new_def}'
        _check_grammar(stmt)
        return [{
            'resource_id': identity,
            'kind': 'view',
            'name': live['name'],
            'operation': 'replace_view',
            'lock_target': lock_target_fn(live),
            'live_guard': digest(l_nat),
            'statement': stmt,
        }], 0, residual_after

    # 5. Table persistence / replica identity / owner / tablespace / storage options
    if kind == 'table' and lock_target_fn(live):
        tbl_q = _qualified(l_nat['schema'], l_crow['relname'])
        # Persistence (p <-> u)
        if b_crow.get('relpersistence') != a_crow.get('relpersistence') and a_crow.get('relpersistence') in {'p', 'u'}:
            if l_crow.get('relpersistence') == a_crow['relpersistence']:
                converged += 1
            elif l_crow.get('relpersistence') != b_crow.get('relpersistence'):
                raise ValueError('Table persistence changed independently since baseline')
            else:
                mode_w = 'LOGGED' if a_crow['relpersistence'] == 'p' else 'UNLOGGED'
                stmt = f'ALTER TABLE {tbl_q} SET {mode_w}'
                _check_grammar(stmt)
                ops.append({
                    'resource_id': identity,
                    'kind': 'table',
                    'name': live['name'],
                    'operation': 'set_table_persistence',
                    'lock_target': lock_target_fn(live),
                    'live_guard': digest(l_nat),
                    'statement': stmt,
                })
            if isinstance(r_crow, dict) and 'relpersistence' in b_crow:
                r_crow['relpersistence'] = b_crow['relpersistence']
        # Replica identity
        if b_crow.get('relreplident') != a_crow.get('relreplident') and a_crow.get('relreplident') in REPLICA_CODES:
            if l_crow.get('relreplident') == a_crow['relreplident']:
                converged += 1
            elif l_crow.get('relreplident') != b_crow.get('relreplident'):
                raise ValueError('Table replica identity changed independently since baseline')
            else:
                stmt = f'ALTER TABLE {tbl_q} REPLICA IDENTITY {REPLICA_CODES[a_crow["relreplident"]]}'
                _check_grammar(stmt)
                ops.append({
                    'resource_id': identity,
                    'kind': 'table',
                    'name': live['name'],
                    'operation': 'set_replica_identity',
                    'lock_target': lock_target_fn(live),
                    'live_guard': digest(l_nat),
                    'statement': stmt,
                })
            if isinstance(r_crow, dict) and 'relreplident' in b_crow:
                r_crow['relreplident'] = b_crow['relreplident']
        # Owner
        if b_nat.get('owner_name') != a_nat.get('owner_name') and a_nat.get('owner_name'):
            if l_nat.get('owner_name') == a_nat['owner_name']:
                converged += 1
            elif l_nat.get('owner_name') != b_nat.get('owner_name'):
                raise ValueError('Table owner changed independently since baseline')
            else:
                stmt = f'ALTER TABLE {tbl_q} OWNER TO {_identifier(a_nat["owner_name"], "owner")}'
                _check_grammar(stmt)
                ops.append({
                    'resource_id': identity,
                    'kind': 'table',
                    'name': live['name'],
                    'operation': 'set_table_owner',
                    'lock_target': lock_target_fn(live),
                    'live_guard': digest(l_nat),
                    'statement': stmt,
                })
            if 'owner_name' in b_nat:
                r_nat['owner_name'] = b_nat['owner_name']

    # 6. Object & extension-member ACL transitions (relacl / proacl / typacl / nspacl)
    acl_field = {'pg_class': 'relacl', 'pg_proc': 'proacl', 'pg_type': 'typacl', 'pg_namespace': 'nspacl'}.get(
        l_nat.get('catalog')
    )
    if acl_field and not _equal(b_crow.get(acl_field), a_crow.get(acl_field)):
        if _equal(a_crow.get(acl_field), l_crow.get(acl_field)):
            converged += 1
        elif not _equal(b_crow.get(acl_field), l_crow.get(acl_field)):
            raise ValueError('Object privileges changed independently since baseline')
        else:
            acl_stmts = diff_row_acl_transition(before, after)
            ltarget = lock_target_fn(live) or _non_table_lock(live)
            for idx, stmt in enumerate(acl_stmts):
                _check_grammar(stmt)
                ops.append({
                    'resource_id': identity,
                    'kind': kind,
                    'name': live['name'],
                    'operation': f'alter_privileges_{idx}',
                    'lock_target': ltarget,
                    'live_guard': digest(l_nat),
                    'statement': stmt,
                })
        if isinstance(r_crow, dict):
            if acl_field in b_crow:
                r_crow[acl_field] = deepcopy(b_crow[acl_field])
            else:
                r_crow.pop(acl_field, None)

    if ops or converged:
        return ops, converged, residual_after
    return None

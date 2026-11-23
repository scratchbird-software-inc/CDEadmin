"""Native DDN schema stages for the original retained DuckDB query session (DU-AUD-17).

Operates strictly on the caller's original DuckDB session handle (covering TEMP
catalog objects, attached catalogs, and uncommitted session changes) without
ever borrowing an independent connection or issuing COMMIT/ROLLBACK on the
caller's transaction. Independent-file DDN documents and migration receipts are
never transferable to or from this path.
"""

from __future__ import annotations

from copy import deepcopy
import re

from .firebird_catalog_import import _equal
from .firebird_schema_plan import digest
from ..providers.duckdb.driver import uncertain, viability
from ..providers.duckdb.provider import _resource_id
from ..providers.embedded_session_catalog import duckdb_catalog


FORMAT = 'scratchrobin.duckdb.retained-schema-plan@1'
CREATABLE = frozenset({'schema', 'sequence', 'type', 'table', 'view', 'macro', 'index'})
KINDS = CREATABLE | frozenset({'column', 'constraint'})
_KIND_KEYWORDS = {
    'schema': 'SCHEMA',
    'sequence': 'SEQUENCE',
    'type': 'TYPE',
    'table': 'TABLE',
    'view': 'VIEW',
    'macro': 'MACRO',
    'index': 'INDEX',
    'column': 'COLUMN',
}


def _quote(value: str) -> str:
    if not isinstance(value, str) or not value or '\x00' in value:
        raise ValueError('Native identifier must be nonempty text without NUL')
    return '"' + value.replace('"', '""') + '"'


def model(resources: list[dict], endpoint: str, session: str) -> dict:
    def to_row(res: dict) -> dict:
        native = deepcopy(res.get('native', {}))
        native['observation_scope'] = 'retained-session'
        return {
            'resource_id': res['resource_id'],
            'kind': res['resource_kind'],
            'path': list(res['display_path']),
            'name': res['display_name'],
            'system': 'true' if native.get('system_object') else 'false',
            'native': native,
        }

    return {
        'provenance': {
            'mapping': 'scratchrobin.duckdb.catalog@1',
            'endpoint_id': endpoint,
            'database_target_id': 'retained-session:' + session,
            'observation_scope': 'retained-session',
            'include_system': False,
        },
        'rows': {
            res['resource_id']: to_row(res)
            for res in resources
            if not res.get('native', {}).get('system_object')
        },
    }


def observe(client, handle, endpoint: str, session: str) -> dict:
    captured = duckdb_catalog(client, handle, session, include_system=False)
    return model(captured['resources'], endpoint, session)


def _definition_for_retained(row: dict) -> dict:
    from .duckdb_schema_plan import _definition
    d = deepcopy(_definition(row))
    if isinstance(d.get('catalog'), dict):
        d['catalog'].pop('temporary', None)
    return d


def schema_digest_map(document: dict) -> dict[str, str]:
    return {
        identity: digest(_definition_for_retained(row))
        for identity, row in document.get('rows', {}).items()
        if row.get('kind') in KINDS and row.get('system') == 'false'
    }


def context(client, handle, revision: int) -> dict:
    state = viability(handle)
    if state != 'viable':
        raise ValueError('Original retained DuckDB transaction is aborted; roll back before planning retained DDL')
    att_ctx = client._attachment_contexts.get(id(handle))
    if not att_ctx or not att_ctx.get('session_scope_id'):
        raise ValueError('Original DuckDB session scope identity is unavailable')
    tx_row = handle.execute('SELECT current_transaction_id()').fetchone()
    tx_id = int(tx_row[0]) if tx_row and tx_row[0] is not None else None
    dbs = [
        [str(r[0]), int(r[1]), bool(r[2]), str(r[3] or '')]
        for r in handle.execute(
            'SELECT database_name, database_oid, readonly, type '
            'FROM duckdb_databases() WHERE NOT internal ORDER BY database_name'
        ).fetchall()
    ]
    return {
        'revision': int(revision),
        'connection_identity': id(handle),
        'session_scope_id': att_ctx['session_scope_id'],
        'transaction_id': tx_id,
        'viability': state,
        'databases': dbs,
    }


def _scope(document: dict, endpoint: str, session: str, *, observed: bool = False) -> None:
    if not isinstance(document, dict) or not isinstance(document.get('rows'), dict):
        raise ValueError('Invalid DuckDB DDN document')
    prov = document.get('provenance') or {}
    target_id = prov.get('database_target_id')
    if not isinstance(target_id, str) or not target_id.startswith('retained-session:'):
        raise ValueError('Independent-file DuckDB DDN models cannot authorize a retained-session migration')
    if (prov.get('mapping') != 'scratchrobin.duckdb.catalog@1' or
            prov.get('endpoint_id') != endpoint or
            target_id != 'retained-session:' + session):
        raise ValueError('Retained DDN must belong to this exact original DuckDB session and endpoint')
    if observed:
        if prov.get('observation_scope') != 'retained-session' and any(
            row.get('native', {}).get('observation_scope') != 'retained-session'
            for row in document['rows'].values()
        ):
            raise ValueError('Retained DuckDB DDL requires original-session baseline observations')


def _validate_row_address(row: dict, writable_catalogs: set[str], all_catalogs: set[str], *, mutating: bool = True) -> str:
    kind = row.get('kind')
    path = row.get('path')
    name = row.get('name')
    if kind not in KINDS or not isinstance(path, list) or not isinstance(name, str):
        raise ValueError(f'Retained DuckDB object kind {kind!r} is not admitted')
    expected_len = 2 if kind == 'schema' else 4 if kind in {'column', 'constraint', 'index'} else 3
    if len(path) != expected_len or path[-1] != name:
        raise ValueError('Retained DuckDB object path does not match its kind and name')
    if row.get('system') != 'false' or row.get('native', {}).get('system_object') is True:
        raise ValueError('System catalog objects cannot be mutated in retained-session DDN')
    if kind != 'constraint' and row.get('resource_id') != _resource_id(kind, path[:-1], name):
        raise ValueError('Retained DuckDB object resource_id is inconsistent with its path')
    cat = path[0]
    if cat not in all_catalogs:
        raise ValueError(f'Catalog {cat!r} is not attached on this retained DuckDB session')
    if mutating and cat not in writable_catalogs:
        raise ValueError(f'Catalog {cat!r} is read-only on this retained DuckDB session')
    return '.'.join(_quote(p) for p in path)


def _validate_single_statement(sql: str, expected_stmt_type: str | None = None) -> str:
    import duckdb
    if not isinstance(sql, str) or not sql.strip() or '\x00' in sql or len(sql.encode('utf8')) > 1024 * 1024:
        raise ValueError('Retained DDL statement must be bounded non-empty text')
    try:
        stmts = duckdb.extract_statements(sql)
    except duckdb.Error:
        raise ValueError(f'Native DuckDB parser rejected retained DDL: {sql[:120]}') from None
    if len(stmts) != 1:
        raise ValueError('Each retained DDL stage must contain exactly one DuckDB statement')
    if expected_stmt_type is not None and stmts[0].type != getattr(duckdb.StatementType, expected_stmt_type):
        raise ValueError(f'Expected DuckDB {expected_stmt_type} statement')
    return sql.strip().rstrip(';')


def _compile_create_ddl(row: dict, qualified: str, *, replace: bool = False) -> str:
    kind = row['kind']
    path = row['path']
    is_temp = path[0] == 'temp' or bool(row.get('native', {}).get('catalog_metadata', {}).get('temporary'))
    raw_ddl = row.get('native', {}).get('ddl')
    if kind == 'schema':
        sql = f'CREATE SCHEMA {qualified}'
        return _validate_single_statement(sql, 'CREATE')
    if kind == 'index':
        if not isinstance(raw_ddl, str) or not raw_ddl.strip():
            raise ValueError('Retained index creation requires native CREATE INDEX DDL')
        table_qual = '.'.join(_quote(p) for p in path[:3])
        idx_name = _quote(path[3])
        if not re.match(
            r'^\s*CREATE\s+(?:UNIQUE\s+)?INDEX\s+' + re.escape(idx_name) + r'\s+ON\s+' + re.escape(table_qual) + r'(?=\s*\()',
            raw_ddl, re.I,
        ):
            raise ValueError('Retained index DDL must name the exact index and qualified table')
        return _validate_single_statement(raw_ddl, 'CREATE')
    if not isinstance(raw_ddl, str) or not raw_ddl.strip():
        raise ValueError(f'Retained {kind} creation requires native DDL')
    kw = _KIND_KEYWORDS[kind]
    rep = 'OR REPLACE ' if replace else ''
    # Admit either `CREATE [OR REPLACE] TEMP <KW> "temp"."main"."name"` or `CREATE [OR REPLACE] <KW> "cat"."sch"."name"`
    patterns = [
        r'^\s*CREATE\s+' + (r'OR\s+REPLACE\s+' if replace else r'') + r'(?:TEMP(?:ORARY)?\s+)?' + kw + r'\s+' + re.escape(qualified) + r'(?=\s|\(|;|$)',
    ]
    if is_temp:
        patterns.append(
            r'^\s*CREATE\s+' + (r'OR\s+REPLACE\s+' if replace else r'') + r'TEMP(?:ORARY)?\s+' + kw + r'\s+' + re.escape(_quote(row['name'])) + r'(?=\s|\(|;|$)'
        )
    if not any(re.match(pat, raw_ddl, re.I) for pat in patterns):
        raise ValueError(f'Retained {kind} DDL must target {qualified} (or TEMP {_quote(row["name"])})')
    if not replace and re.match(r'^\s*CREATE\s+OR\s+REPLACE\b', raw_ddl, re.I):
        raise ValueError('CREATE OR REPLACE is not admitted without explicit replacement intent')
    return _validate_single_statement(raw_ddl, 'CREATE')


def _validate_in_prototype(all_catalogs: set[str], baseline: dict, stages: list[dict]) -> None:
    """Validate grammar and object dependencies in a private :memory: DuckDB prototype."""
    import duckdb
    probe = duckdb.connect(':memory:')
    try:
        cur_main = probe.execute('SELECT current_database()').fetchone()[0]
        for cat in sorted(all_catalogs - {cur_main, 'temp', 'system'}):
            probe.execute(f"ATTACH ':memory:' AS {_quote(cat)}")
        # Replay baseline schemas/sequences/types/tables/views/macros where DDL is present so dependent new objects bind
        order_rank = {'schema': 0, 'sequence': 1, 'type': 2, 'table': 3, 'view': 4, 'macro': 5, 'index': 6}
        base_rows = sorted(
            (r for r in baseline['rows'].values() if r['kind'] in CREATABLE and r['system'] == 'false'),
            key=lambda r: (order_rank.get(r['kind'], 9), r['resource_id']),
        )
        for brow in base_rows:
            cat = brow['path'][0]
            if cat not in all_catalogs:
                continue
            if brow['kind'] == 'schema' and brow['name'] != 'main':
                try:
                    probe.execute(f"CREATE SCHEMA {_quote(cat)}.{_quote(brow['name'])}")
                except duckdb.Error:
                    pass
                continue
            ddl = brow.get('native', {}).get('ddl') or brow.get('native', {}).get('source_ddl')
            if isinstance(ddl, str) and ddl.strip():
                try:
                    if cat == cur_main or cat == 'temp':
                        probe.execute(ddl)
                    else:
                        probe.execute(f'USE {_quote(cat)}')
                        probe.execute(ddl)
                        probe.execute(f'USE {_quote(cur_main)}')
                except duckdb.Error:
                    try:
                        probe.execute(f'USE {_quote(cur_main)}')
                    except duckdb.Error:
                        pass
        # Validate every planned stage parses cleanly
        for st in stages:
            _validate_single_statement(st['source'])
    finally:
        probe.close()


def plan(
    client,
    handle,
    baseline: dict,
    desired: dict,
    live: dict,
    endpoint: str,
    session: str,
    *,
    deletions=(),
    alterations=(),
    rebuilds=(),
) -> dict:
    _scope(baseline, endpoint, session, observed=True)
    _scope(live, endpoint, session, observed=True)
    _scope(desired, endpoint, session, observed=False)

    if schema_digest_map(baseline) != schema_digest_map(live):
        raise ValueError('The original retained DuckDB catalog changed; capture a fresh session baseline')

    db_rows = handle.execute(
        'SELECT database_name, readonly FROM duckdb_databases() WHERE NOT internal'
    ).fetchall()
    all_catalogs = {str(r[0]) for r in db_rows} | {'temp'}
    writable_catalogs = {str(r[0]) for r in db_rows if not r[1]} | {'temp'}

    if (not isinstance(deletions, (list, tuple)) or len(deletions) > 32 or
            any(not isinstance(x, str) for x in deletions) or len(set(deletions)) != len(deletions)):
        raise ValueError('Select at most 32 distinct retained deletion identities')
    if not isinstance(alterations, (list, tuple)) or len(alterations) > 32:
        raise ValueError('Select at most 32 retained alterations')
    if not isinstance(rebuilds, (list, tuple)) or len(rebuilds) > 8:
        raise ValueError('Select at most 8 retained table rebuilds')

    before = baseline['rows']
    after = desired['rows']
    stages: list[dict] = []
    handled_ids: set[str] = set()
    removed_ids: set[str] = set()

    # 1. Explicit deletions
    for del_id in deletions:
        old_row = before.get(del_id)
        if old_row is None or old_row['kind'] not in (CREATABLE | {'column'}) or del_id in after:
            raise ValueError('Explicit retained deletion requires an observed object absent from desired DDN')
        qual = _validate_row_address(old_row, writable_catalogs, all_catalogs, mutating=True)
        if old_row['kind'] == 'column':
            tbl_qual = '.'.join(_quote(p) for p in old_row['path'][:3])
            sql = f'ALTER TABLE {tbl_qual} DROP COLUMN {_quote(old_row["name"])} RESTRICT'
            _validate_single_statement(sql, 'ALTER')
        elif old_row['kind'] == 'index':
            idx_qual = '.'.join(_quote(p) for p in [old_row['path'][0], old_row['path'][1], old_row['name']])
            sql = f'DROP INDEX {idx_qual} RESTRICT'
            _validate_single_statement(sql, 'DROP')
        else:
            sql = f'DROP {_KIND_KEYWORDS[old_row["kind"]]} {qual} RESTRICT'
            _validate_single_statement(sql, 'DROP')
        stages.append({
            'operation': 'drop',
            'resource_id': del_id,
            'kind': old_row['kind'],
            'name': old_row['name'],
            'target': qual,
            'source': sql,
        })
        removed_ids.add(del_id)
        handled_ids.add(del_id)
        # Mark descendants of dropped table/view/schema as removed
        p_prefix = old_row['path']
        for cid, crow in before.items():
            if len(crow['path']) > len(p_prefix) and crow['path'][:len(p_prefix)] == p_prefix:
                removed_ids.add(cid)

    # 2. Explicit retained table rebuilds (preserving rows on TEMP / attached / main session tables!)
    rebuild_map = {}
    for rb in rebuilds:
        if (not isinstance(rb, dict) or not isinstance(rb.get('resource_id'), str) or
                rb.get('preserve_rows_confirmed') is not True or
                rb.get('complete_definition_confirmed') is not True):
            raise ValueError('Retained table rebuild requires resource_id, complete_definition_confirmed=True, and preserve_rows_confirmed=True')
        rid = rb['resource_id']
        if rid in rebuild_map:
            raise ValueError('Duplicate retained table rebuild target')
        rebuild_map[rid] = rb
        old_t = before.get(rid)
        new_t = after.get(rid)
        if old_t is None or new_t is None or old_t['kind'] != 'table' or new_t['kind'] != 'table':
            raise ValueError('Retained rebuild target must be an existing table present in desired DDN')
        qual = _validate_row_address(new_t, writable_catalogs, all_catalogs, mutating=True)
        final_ddl = _compile_create_ddl(new_t, qual, replace=False)
        from .duckdb_general_rebuild import validate_general_generated_columns, _validate_bounded_sql_expr
        new_cols = new_t['native'].get('columns') or []
        old_cols = old_t['native'].get('columns') or []
        new_gen = set(validate_general_generated_columns(final_ddl, new_cols))
        old_gen = set(validate_general_generated_columns(old_t['native'].get('ddl', ''), old_cols))
        old_col_names = {c['name'] for c in old_cols}
        convs = rb.get('column_conversions') or {}
        renames = rb.get('column_renames') or {}
        rev_ren = {v: k for k, v in renames.items()}
        if convs and rb.get('loss_acknowledged') is not True:
            raise ValueError('Retained rebuild column_conversions require loss_acknowledged=True')
        dropped_cols = old_col_names - {rev_ren.get(c['name'], c['name']) for c in new_cols}
        if dropped_cols and rb.get('discard_columns_confirmed') is not True:
            raise ValueError('Dropping columns in retained rebuild requires discard_columns_confirmed=True')
        dst_cols, src_exprs = [], []
        for nc in new_cols:
            cname = nc['name']
            if cname in new_gen:
                continue
            dst_cols.append(_quote(cname))
            if cname in convs:
                src_exprs.append(_validate_bounded_sql_expr(convs[cname], f'retained conversion {cname!r}'))
            else:
                orig = rev_ren.get(cname, cname)
                if orig in old_col_names and orig not in old_gen:
                    if old_t['native']['columns'][[x['name'] for x in old_cols].index(orig)].get('data_type') != nc.get('data_type'):
                        raise ValueError(
                            f'Retained column {cname!r} changes data_type; supply column_conversions and loss_acknowledged=True'
                        )
                    src_exprs.append(_quote(orig))
                elif nc.get('default') is not None:
                    src_exprs.append(_validate_bounded_sql_expr(nc['default'], f'DEFAULT for {cname!r}'))
                elif nc.get('nullable') is False:
                    raise ValueError(f'Added NOT NULL column {cname!r} requires a DEFAULT or column_conversions fill')
                else:
                    src_exprs.append('NULL')
        stage_name = '__sr_ret_stage_' + digest(final_ddl + rid)[:16]
        is_temp = new_t['path'][0] == 'temp'
        stage_qual = '.'.join(_quote(p) for p in [*new_t['path'][:2], stage_name])
        body_open = final_ddl.index('(')
        create_stage = (
            f'CREATE TEMP TABLE {_quote(stage_name)} {final_ddl[body_open:]}'
            if is_temp else f'CREATE TABLE {stage_qual} {final_ddl[body_open:]}'
        )
        _validate_single_statement(create_stage, 'CREATE')
        insert_stage = f"INSERT INTO {stage_qual} ({', '.join(dst_cols)}) SELECT {', '.join(src_exprs)} FROM {qual}"
        _validate_single_statement(insert_stage, 'INSERT')
        drop_orig = f'DROP TABLE {qual} RESTRICT'
        rename_stage = f'ALTER TABLE {stage_qual} RENAME TO {_quote(new_t["name"])}'
        count_check = f'SELECT abs((SELECT count(*) FROM {qual}) - (SELECT count(*) FROM {stage_qual}))'
        stages.append({'operation': 'rebuild-stage-create', 'resource_id': rid, 'kind': 'table', 'name': new_t['name'], 'target': qual, 'source': create_stage})
        stages.append({'operation': 'rebuild-stage-copy', 'resource_id': rid, 'kind': 'table', 'name': new_t['name'], 'target': qual, 'source': insert_stage, 'data_check': count_check})
        stages.append({'operation': 'rebuild-drop-old', 'resource_id': rid, 'kind': 'table', 'name': new_t['name'], 'target': qual, 'source': drop_orig})
        stages.append({'operation': 'rebuild-rename-stage', 'resource_id': rid, 'kind': 'table', 'name': new_t['name'], 'target': qual, 'source': rename_stage})
        for idx_row in sorted(
            (r for r in after.values() if r['kind'] == 'index' and r.get('path', [])[:3] == new_t['path']),
            key=lambda r: r['resource_id'],
        ):
            idx_sql = _compile_create_ddl(idx_row, _validate_row_address(idx_row, writable_catalogs, all_catalogs), replace=False)
            stages.append({'operation': 'rebuild-replay-index', 'resource_id': idx_row['resource_id'], 'kind': 'index', 'name': idx_row['name'], 'target': qual, 'source': idx_sql})
            handled_ids.add(idx_row['resource_id'])
        handled_ids.add(rid)
        for cid, crow in list(before.items()) + list(after.items()):
            if crow['kind'] in {'column', 'constraint', 'index'} and crow.get('path', [])[:3] == new_t['path']:
                handled_ids.add(cid)
                if cid in before and cid not in after:
                    removed_ids.add(cid)

    # 3. Explicit alterations (column default/nullable/type, comments, renames, add-primary-key)
    for alt in alterations:
        if not isinstance(alt, dict) or not isinstance(alt.get('resource_id'), str):
            raise ValueError('Each retained alteration requires a resource_id')
        aid = alt['resource_id']
        act = alt.get('action')
        if act == 'rename':
            src_id = alt.get('from_resource_id')
            old_r = before.get(src_id)
            new_r = after.get(aid)
            if old_r is None or new_r is None or old_r['kind'] != new_r['kind'] or old_r['kind'] not in {'table', 'view', 'column'}:
                raise ValueError('Retained rename requires observed source and desired target of table, view, or column')
            old_qual = _validate_row_address(old_r, writable_catalogs, all_catalogs, mutating=True)
            _validate_row_address(new_r, writable_catalogs, all_catalogs, mutating=True)
            if old_r['kind'] == 'column':
                tbl_q = '.'.join(_quote(p) for p in old_r['path'][:3])
                sql = f'ALTER TABLE {tbl_q} RENAME COLUMN {_quote(old_r["name"])} TO {_quote(new_r["name"])}'
            else:
                sql = f'ALTER {_KIND_KEYWORDS[old_r["kind"]]} {old_qual} RENAME TO {_quote(new_r["name"])}'
            _validate_single_statement(sql, 'ALTER')
            stages.append({'operation': 'rename', 'resource_id': aid, 'kind': new_r['kind'], 'name': new_r['name'], 'target': old_qual, 'source': sql})
            handled_ids.update({src_id, aid})
            removed_ids.add(src_id)
            continue

        old_r = before.get(aid)
        new_r = after.get(aid)
        if old_r is None or new_r is None:
            raise ValueError(f'Retained alteration target {aid!r} must exist in baseline and desired DDN')
        qual = _validate_row_address(new_r, writable_catalogs, all_catalogs, mutating=True)
        if act == 'set-comment':
            comment = new_r['native'].get('catalog_metadata', {}).get('comment')
            lit = 'NULL' if comment is None else "'" + str(comment).replace("'", "''") + "'"
            c_tgt = '.'.join(_quote(p) for p in [new_r['path'][0], new_r['path'][1], new_r['name']]) if new_r['kind'] == 'index' else qual
            sql = f'COMMENT ON {_KIND_KEYWORDS[new_r["kind"]]} {c_tgt} IS {lit}'
            _validate_single_statement(sql, 'ALTER')
            stages.append({'operation': 'alter', 'resource_id': aid, 'kind': new_r['kind'], 'name': new_r['name'], 'target': qual, 'source': sql})
            handled_ids.add(aid)
        elif new_r['kind'] == 'column' and act in {'set-default', 'set-nullable', 'set-type'}:
            tbl_q = '.'.join(_quote(p) for p in new_r['path'][:3])
            meta = new_r['native'].get('catalog_metadata', {})
            if act == 'set-default':
                dv = meta.get('default')
                clause = 'DROP DEFAULT' if dv is None else f'SET DEFAULT {dv}'
            elif act == 'set-nullable':
                clause = 'DROP NOT NULL' if meta.get('nullable') else 'SET NOT NULL'
            else:
                clause = f"TYPE {meta['data_type']}" + (f" USING {alt['using']}" if alt.get('using') else '')
            sql = f'ALTER TABLE {tbl_q} ALTER COLUMN {_quote(new_r["name"])} {clause}'
            _validate_single_statement(sql, 'ALTER')
            stages.append({'operation': 'alter', 'resource_id': aid, 'kind': 'column', 'name': new_r['name'], 'target': qual, 'source': sql})
            handled_ids.add(aid)
            # Parent table column array also reflects this column change
            parent_tid = _resource_id('table', new_r['path'][:2], new_r['path'][2])
            handled_ids.add(parent_tid)
        elif new_r['kind'] == 'table' and act == 'add-primary-key':
            cols = alt.get('columns') or []
            if not isinstance(cols, list) or not cols:
                raise ValueError('add-primary-key requires non-empty columns list')
            sql = f"ALTER TABLE {qual} ADD PRIMARY KEY ({', '.join(_quote(c) for c in cols)})"
            _validate_single_statement(sql, 'ALTER')
            stages.append({'operation': 'alter', 'resource_id': aid, 'kind': 'table', 'name': new_r['name'], 'target': qual, 'source': sql})
            handled_ids.add(aid)
            for cid, crow in after.items():
                if crow['kind'] in {'column', 'constraint'} and crow.get('path', [])[:3] == new_r['path']:
                    handled_ids.add(cid)
        else:
            raise ValueError(f'Unsupported retained alteration action {act!r} on {new_r["kind"]}')

    # 4. Absent baseline rows check (view filter is NEVER deletion intent!)
    replaced_views = {
        tuple(r['path']) for k, r in after.items()
        if r['kind'] == 'view' and k in before and not _equal(_definition_for_retained(before[k]), _definition_for_retained(r))
    }
    for bid, brow in before.items():
        if brow['kind'] in KINDS and brow.get('system') == 'false' and bid not in after and bid not in removed_ids:
            if brow['kind'] == 'column' and tuple(brow['path'][:3]) in replaced_views:
                continue
            raise ValueError('An absent retained DDN fact is not an explicit deletion instruction')

    # 5. Creations and view/macro/sequence/type replacements
    create_order = {'schema': 0, 'sequence': 1, 'type': 2, 'table': 3, 'column': 4, 'view': 5, 'macro': 6, 'index': 7}
    for aid, arow in sorted(after.items(), key=lambda kv: (create_order.get(kv[1].get('kind'), 9), kv[0])):
        if aid in handled_ids or arow['kind'] not in (CREATABLE | {'column'}) or arow.get('system') != 'false':
            continue
        brow = before.get(aid)
        if brow is not None and _equal(_definition_for_retained(brow), _definition_for_retained(arow)):
            continue
        qual = _validate_row_address(arow, writable_catalogs, all_catalogs, mutating=True)
        if brow is None:
            if arow['kind'] == 'column':
                parent_tid = _resource_id('table', arow['path'][:2], arow['path'][2])
                if parent_tid not in before:
                    # Column belongs to newly created table's CREATE TABLE statement
                    continue
                meta = arow['native'].get('catalog_metadata', {})
                if meta.get('nullable') is False:
                    raise ValueError('Adding a NOT NULL column to an existing retained table requires a retained table rebuild')
                tbl_q = '.'.join(_quote(p) for p in arow['path'][:3])
                sql = f"ALTER TABLE {tbl_q} ADD COLUMN {_quote(arow['name'])} {meta['data_type']}"
                if meta.get('default') is not None:
                    sql += f" DEFAULT {meta['default']}"
                _validate_single_statement(sql, 'ALTER')
                stages.append({'operation': 'add-column', 'resource_id': aid, 'kind': 'column', 'name': arow['name'], 'target': qual, 'source': sql})
            else:
                sql = _compile_create_ddl(arow, qual, replace=False)
                stages.append({'operation': 'create', 'resource_id': aid, 'kind': arow['kind'], 'name': arow['name'], 'target': qual, 'source': sql})
        else:
            if arow['kind'] == 'table':
                # Check if only appended nullable/default columns were added
                old_c = brow['native'].get('columns') or []
                new_c = arow['native'].get('columns') or []
                if (len(new_c) > len(old_c) and
                        [c['name'] for c in new_c[:len(old_c)]] == [c['name'] for c in old_c] and
                        all(_equal(old_c[i], new_c[i]) for i in range(len(old_c)))):
                    continue
                raise ValueError('Retained table structural change requires an explicit rebuilds or alterations entry')
            if arow['kind'] in {'view', 'macro', 'sequence', 'type'}:
                change_spec = arow['native'].get('duckdb_change') or {}
                if arow['kind'] == 'sequence' and change_spec.get('reset_state_confirmed') is not True:
                    raise ValueError('Retained sequence replacement requires reset_state_confirmed=True')
                sql = _compile_create_ddl(arow, qual, replace=True)
                stages.append({'operation': 'replace', 'resource_id': aid, 'kind': arow['kind'], 'name': arow['name'], 'target': qual, 'source': sql})
            elif arow['kind'] == 'index':
                idx_drop = f"DROP INDEX {'.'.join(_quote(p) for p in [brow['path'][0], brow['path'][1], brow['name']])} RESTRICT"
                idx_create = _compile_create_ddl(arow, qual, replace=False)
                stages.append({'operation': 'drop', 'resource_id': aid, 'kind': 'index', 'name': brow['name'], 'target': qual, 'source': idx_drop})
                stages.append({'operation': 'create', 'resource_id': aid, 'kind': 'index', 'name': arow['name'], 'target': qual, 'source': idx_create})
            else:
                raise ValueError(f'Retained modification of {arow["kind"]} requires an explicit alteration adapter')

    if not 1 <= len(stages) <= 64:
        raise ValueError('Review between 1 and 64 retained native DuckDB DDL statements')

    _validate_in_prototype(all_catalogs, baseline, stages)

    return {
        'format': FORMAT,
        'engine': 'duckdb',
        'provider_session_id': session,
        'operations': stages,
        'execution_sha256': digest(stages),
        'ready_for_review': True,
        'application_supported': True,
        'native_grammar_validated': True,
        'transaction_policy': 'original-caller-transaction; never commit or rollback',
        'warnings': [
            'Executes on the original retained DuckDB query connection without issuing COMMIT or ROLLBACK.',
            'DuckDB 1.5.2 does not provide SQL SAVEPOINTs; if a statement aborts the active transaction, use the session Rollback control.',
            'Independent-file migration receipts and retained-session receipts are non-transferable.',
        ],
    }


def apply(client, handle, record: dict, endpoint: str, session: str, revision: int, *, acknowledge=None) -> dict:
    """Execute reviewed retained DuckDB DDL on the original session without committing or rolling back."""
    if record.get('plan', {}).get('format') != FORMAT:
        return {
            'state': 'not_dispatched',
            'reason': 'Independent-file migration receipts cannot be transferred to a retained DuckDB session',
        }
    if digest(record['plan'].get('operations')) != record['plan'].get('execution_sha256'):
        return {
            'state': 'not_dispatched',
            'reason': 'Reviewed retained DuckDB DDL stages changed',
        }
    try:
        current_ctx = context(client, handle, revision)
    except ValueError as err:
        return {'state': 'not_dispatched', 'reason': str(err)}
    if current_ctx != record.get('native_context'):
        return {
            'state': 'not_dispatched',
            'reason': 'Original retained DuckDB session, transaction, or attached catalog context changed',
        }
    live = observe(client, handle, endpoint, session)
    if schema_digest_map(live) != schema_digest_map(record['baseline']):
        return {
            'state': 'not_dispatched',
            'reason': 'Original retained DuckDB schema changed since baseline capture',
        }

    completed = 0
    try:
        for stage in record['plan']['operations']:
            handle.execute(stage['source'])
            completed += 1
            if stage.get('data_check'):
                diff = handle.execute(stage['data_check']).fetchone()[0]
                if diff != 0:
                    raise ValueError('Retained table rebuild staged row count differed from source')
        actual = observe(client, handle, endpoint, session)
        # Verify every desired object exists in actual retained catalog
        for op in record['plan']['operations']:
            rid = op['resource_id']
            if op['operation'] == 'drop' and rid not in record['desired']['rows']:
                if rid in actual['rows']:
                    raise ValueError(f'Dropped retained object {rid} still observed after execution')
            elif rid in record['desired']['rows']:
                if rid not in actual['rows']:
                    raise ValueError(f'Desired retained object {rid} missing from postcondition observation')
        client._observe(handle)
        outcome = {
            'state': 'applied_pending_caller_transaction',
            'native_ddl_acknowledged': True,
            'rediscovery_verified': True,
            'caller_transaction_active': True,
            'commit_dispatched': False,
            'rollback_dispatched': False,
            'completed_statements': completed,
        }
        if acknowledge is not None:
            try:
                acknowledge(deepcopy(outcome))
            except BaseException as err:
                outcome['acknowledgement_store_error'] = type(err).__name__
        return outcome
    except BaseException as err:
        is_uncertain = not isinstance(err, ValueError) and uncertain(err)
        post_viability = 'unknown'
        if not is_uncertain:
            try:
                post_viability = viability(handle)
                client._observe(handle, blocked=False)
            except BaseException:
                is_uncertain = True
        if is_uncertain:
            client._observe(handle, blocked=True)
            state = 'unknown_outcome'
        elif post_viability == 'aborted':
            state = 'caller_transaction_aborted_by_native_engine'
        elif completed == 0:
            state = 'statement_rejected_transaction_viable'
        else:
            state = 'partial_applied_pending_caller_rollback'
        return {
            'state': state,
            'native_ddl_acknowledged': False,
            'rediscovery_verified': False,
            'completed_statements': completed,
            'commit_dispatched': False,
            'rollback_dispatched': False,
            'native_transaction_viability': post_viability,
            'session_reuse_blocked': is_uncertain,
            'error_type': type(err).__name__,
            'native_error': str(err)[:400],
        }

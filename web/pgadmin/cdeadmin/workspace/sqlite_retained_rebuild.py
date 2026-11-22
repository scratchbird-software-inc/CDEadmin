"""Complex table rebuilds and FTS-preserved transformations on an original retained SQLite connection (SQ-AUD-05).

Executes strictly inside the caller's original open transaction using nested SAVEPOINTs across
main, temp or attached namespaces without opening substitute connections, without auto-committing,
and without promoting retained/uncommitted/memory/TEMP observations to independent-file authority.
"""
from __future__ import annotations

from copy import deepcopy
import re
import sqlite3
from types import SimpleNamespace

from .firebird_schema_plan import digest
from . import sqlite_retained_schema as retained
from ..providers.sqlite import ddl_prepare
from ..providers.sqlite.declarations import quote
from ..providers.sqlite.provider import _resource_id, _resources


def _autoincrement_in_namespace(ddl: str, namespace: str) -> bool:
    probe = sqlite3.connect(':memory:')
    try:
        clean = re.sub(
            r'^(\s*CREATE\s+(?:TEMP(?:ORARY)?\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)' + re.escape(quote(namespace)) + r'\.',
            r'\1',
            ddl,
            count=1,
            flags=re.I,
        )
        clean = re.sub(r'^(\s*CREATE\s+)TEMP(?:ORARY)?(\s+TABLE\b)', r'\1\2', clean, count=1, flags=re.I)
        probe.execute(clean)
        return probe.execute("SELECT 1 FROM main.sqlite_schema WHERE name='sqlite_sequence'").fetchone() is not None
    finally:
        probe.close()


def _qualify_create_table(ddl: str, namespace: str, old_name: str, new_name: str) -> str:
    q_ns = quote(namespace)
    q_new = quote(new_name)
    # Match CREATE [TEMP|TEMPORARY] TABLE [IF NOT EXISTS] ["ns".]<old_name>
    pat = re.compile(
        r'^(\s*CREATE\s+)(?:TEMP(?:ORARY)?\s+)?(TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)(?:'
        + re.escape(q_ns) + r'\.|' + re.escape(namespace) + r'\.)?(?:'
        + re.escape(quote(old_name)) + r'|' + re.escape(old_name) + r')',
        re.I,
    )
    replaced = pat.sub(lambda m: f'{m.group(1)}{m.group(2)}{q_ns}.{q_new}', ddl, count=1)
    if replaced == ddl:
        raise ValueError('Retained SQLite rebuild DDL must name the exact target table')
    return replaced


def plan_retained_rebuilds(client, handle, baseline, desired, live, endpoint, session, rebuilds):
    retained._scope(baseline, endpoint, session, observed=True)
    retained._scope(live, endpoint, session, observed=True)
    retained._scope(desired, endpoint, session)
    if not isinstance(rebuilds, (list, tuple)) or not 1 <= len(rebuilds) <= 16:
        raise ValueError('Select one to sixteen explicit retained SQLite table rebuild specs')

    namespaces = {row[1] for row in handle.execute('PRAGMA database_list')} | {'temp'}
    probe = retained._prototype(baseline, namespaces, live_handle=handle)
    try:
        storage = set(probe._cdeadmin_module_storage)
        if retained.schema(baseline, storage) != retained.schema(live, storage):
            raise ValueError('The original retained SQLite schema changed; capture a fresh baseline')
        actual_storage = retained._storage_shape(live, storage)

        seen_ids = set()
        stages = []
        for spec in rebuilds:
            if not isinstance(spec, dict) or not isinstance(spec.get('resource_id'), str):
                raise ValueError('Each retained rebuild spec requires resource_id')
            rid = spec['resource_id']
            if rid in seen_ids:
                raise ValueError('Duplicate retained rebuild target: ' + rid)
            seen_ids.add(rid)
            if set(spec) - {'resource_id', 'column_renames', 'child_deletions'}:
                raise ValueError('Retained rebuild spec contains unsupported keys')

            before = baseline['rows'].get(rid)
            after = desired['rows'].get(rid)
            if before is None or after is None or before['kind'] != 'table' or after['kind'] != 'table':
                raise ValueError('Retained rebuild requires an ordinary table present in both baseline and desired DDN')
            retained._valid(before, namespaces, live_handle=handle)
            retained._valid(after, namespaces, live_handle=handle)
            namespace, table_name = before['path'][0], before['name']
            if after['path'] != before['path'] or (namespace, table_name) in storage:
                raise ValueError('Retained rebuild preserves namespace/table path and excludes virtual-module shadow storage')

            old_ddl = ddl_prepare.source(before)
            new_ddl = ddl_prepare.source(after)
            if old_ddl == new_ddl and not spec.get('child_deletions'):
                raise ValueError('Retained rebuild requires a changed table or child definition')

            col_renames = spec.get('column_renames') or {}
            if not isinstance(col_renames, dict) or len(col_renames) > 32 or len(set(col_renames.values())) != len(col_renames):
                raise ValueError('Invalid retained rebuild column_renames mapping')
            child_deletions = list(spec.get('child_deletions') or ())
            if len(child_deletions) != len(set(child_deletions)):
                raise ValueError('Duplicate child_deletions in retained rebuild')

            temp_name = '__cde_ret_rebuild_' + digest({'rid': rid, 'before': old_ddl, 'after': new_ddl})[:28]
            staging_ddl = _qualify_create_table(new_ddl, namespace, table_name, temp_name)

            # Inspect target table columns & options on an isolated namespace probe
            check_probe = retained._prototype(baseline, namespaces, live_handle=handle)
            try:
                check_probe.execute(staging_ddl)
                q_ns = quote(namespace)
                wanted = check_probe.execute(f'PRAGMA {q_ns}.table_xinfo({quote(temp_name)})').fetchall()
                tlist = check_probe.execute(f'PRAGMA {q_ns}.table_list').fetchall()
                t_opts = next((r for r in tlist if str(r[0]) == namespace and str(r[1]) == temp_name), None)
                if t_opts is not None and len(t_opts) >= 5:
                    target_without_rowid = bool(t_opts[4])
                else:
                    col_set = {str(r[1]) for r in wanted}
                    alias = next((a for a in ('_rowid_', 'rowid', 'oid') if a not in col_set), None)
                    if alias is not None:
                        try:
                            check_probe.execute(f'SELECT {quote(alias)} FROM {q_ns}.{quote(temp_name)} LIMIT 0')
                            target_without_rowid = False
                        except sqlite3.OperationalError:
                            target_without_rowid = True
                    else:
                        target_without_rowid = 'WITHOUT ROWID' in new_ddl.upper()
            finally:
                check_probe.close()

            prev_cols = {c['name']: c for c in before['native'].get('columns', ())}
            new_cols = {
                str(r[1]): {
                    'type': str(r[2] or ''),
                    'pk': int(r[5] or 0),
                    'hidden': int(r[6] or 0),
                }
                for r in wanted
            }
            for src_col, dst_col in col_renames.items():
                if src_col not in prev_cols or dst_col not in new_cols or new_cols[dst_col]['hidden']:
                    raise ValueError('Retained rebuild column_renames must map an existing source column to a writable desired column')
            common = [c for c in prev_cols if c in new_cols and not new_cols[c]['hidden'] and c not in col_renames]
            source_names = common + list(col_renames)
            target_names = common + [col_renames[c] for c in col_renames]
            if not source_names:
                raise ValueError('Retained rebuild requires at least one preserved or mapped writable column')

            old_without_rowid = bool(before['native'].get('catalog_metadata', {}).get('without_rowid'))
            old_pks = [(c['name'], c.get('data_type', ''), c.get('primary_key_position', 0)) for c in before['native'].get('columns', ()) if c.get('primary_key_position')]
            new_pks = [(str(r[1]), str(r[2] or ''), int(r[5] or 0)) for r in wanted if r[5]]
            preserve_rowid = (not old_without_rowid and not target_without_rowid and old_pks == new_pks)
            rowid_alias = None
            if preserve_rowid:
                rowid_alias = next((a for a in ('rowid', '_rowid_', 'oid') if a not in prev_cols and a not in new_cols), None)
                if rowid_alias is None:
                    raise ValueError('Physical rowid is shadowed by declared column names')

            q_ns = quote(namespace)
            q_table = f'{q_ns}.{quote(table_name)}'
            q_temp = (quote(temp_name) if namespace.lower() == 'temp' else f'{q_ns}.{quote(temp_name)}')
            q_temp_full = f'{q_ns}.{quote(temp_name)}'
            tgt_proj = ', '.join(([quote(rowid_alias)] if rowid_alias else []) + [quote(c) for c in target_names])
            src_proj = ', '.join(([quote(rowid_alias)] if rowid_alias else []) + [quote(c) for c in source_names])
            copy_sql = f'INSERT INTO {q_temp_full} ({tgt_proj}) SELECT {src_proj} FROM {q_table}'

            src_autoinc = _autoincrement_in_namespace(old_ddl, namespace)
            tgt_autoinc = _autoincrement_in_namespace(new_ddl, namespace)

            # Dependent views/triggers on other tables stay intact across DROP + RENAME inside the transaction;
            # explicit indexes & triggers owned by this table are recreated after RENAME unless in child_deletions.
            before_children = {
                cid: baseline['rows'][cid]
                for cid in retained._children(before, baseline['rows'])
                if baseline['rows'][cid]['kind'] in {'index', 'trigger'}
            }
            after_children = {
                cid: desired['rows'][cid]
                for cid in retained._children(after, desired['rows'])
                if desired['rows'][cid]['kind'] in {'index', 'trigger'}
            }
            if set(child_deletions) != (set(before_children) - set(after_children)):
                raise ValueError('Removing an index or trigger during retained rebuild requires its exact child_deletions identity')

            table_stages = [
                {'operation': 'rebuild-create-temp', 'resource_id': rid, 'kind': 'table', 'name': temp_name, 'row': after, 'source': staging_ddl},
                {'operation': 'rebuild-copy-data', 'resource_id': rid, 'kind': 'table', 'name': table_name, 'row': before, 'source': copy_sql, 'rebuild_data_step': True},
            ]
            if src_autoinc and tgt_autoinc:
                seq_save = (
                    f'CREATE TEMP TABLE IF NOT EXISTS __cde_seq_hold_{temp_name} AS '
                    f'SELECT seq FROM {q_ns}.sqlite_sequence WHERE name = ' + "'" + table_name.replace("'", "''") + "'"
                )
                table_stages.append({'operation': 'rebuild-save-seq', 'resource_id': rid, 'kind': 'table', 'name': table_name, 'row': before, 'source': seq_save, 'rebuild_data_step': True})

            table_stages.extend([
                {'operation': 'drop', 'resource_id': rid, 'kind': 'table', 'name': table_name, 'row': before, 'source': f'DROP TABLE {q_table}'},
                {'operation': 'rebuild-rename-temp', 'resource_id': rid, 'kind': 'table', 'name': table_name, 'row': after, 'source': f'ALTER TABLE {q_temp_full} RENAME TO {quote(table_name)}'},
            ])
            if src_autoinc and tgt_autoinc:
                lit_tbl = "'" + table_name.replace("'", "''") + "'"
                seq_restore_1 = f'DELETE FROM {q_ns}.sqlite_sequence WHERE name = {lit_tbl}'
                seq_restore_2 = f'INSERT INTO {q_ns}.sqlite_sequence(name, seq) SELECT {lit_tbl}, seq FROM temp.__cde_seq_hold_{temp_name}'
                seq_drop_hold = f'DROP TABLE temp.__cde_seq_hold_{temp_name}'
                for st_sql in (seq_restore_1, seq_restore_2, seq_drop_hold):
                    table_stages.append({'operation': 'rebuild-restore-seq', 'resource_id': rid, 'kind': 'table', 'name': table_name, 'row': after, 'source': st_sql, 'rebuild_data_step': True})

            for cid, crow in sorted(after_children.items(), key=lambda kv: (0 if kv[1]['kind'] == 'index' else 1, kv[0])):
                retained._valid(crow, namespaces, live_handle=handle)
                table_stages.append({
                    'operation': 'create',
                    'resource_id': cid,
                    'kind': crow['kind'],
                    'name': crow['name'],
                    'row': crow,
                    'source': ddl_prepare.source(crow),
                })

            for st in table_stages:
                probe.execute(st['source'])
            stages.extend(table_stages)

        proposed = retained.model(_resources(probe, {}), endpoint, session)
        if retained.schema(proposed, storage) != retained.schema(desired, storage):
            raise ValueError('Desired retained DDN facts differ from the complete native rebuilt schema')
        if retained._storage_shape(proposed, storage) != actual_storage:
            raise ValueError('Native virtual-module storage schema cannot be preserved across this rebuild')

        return {
            'format': retained.FORMAT,
            'engine': 'sqlite',
            'authority_scope': 'retained-original-session-only',
            'independent_file_authority_claimed': False,
            'provider_session_id': session,
            'operations': stages,
            'rebuilds': deepcopy(list(rebuilds)),
            'module_storage': [list(k) for k in sorted(storage)],
            'module_storage_schema': actual_storage,
            'module_storage_after_schema': actual_storage,
            'execution_sha256': digest(stages),
            'ready_for_review': True,
            'application_supported': True,
            'native_grammar_validated': True,
            'transaction_policy': 'original-caller-transaction; savepoint-fenced; never commit',
            'warnings': [
                'Rebuild executes inside a nested SAVEPOINT on the original caller connection, preserving uncommitted rows, rowids and caller savepoints.',
                'Retained, uncommitted, in-memory and TEMP observations remain scoped to this session and are never promoted to independent-file authority.',
                'Foreign-key invariants on rebuilt tables are checked before releasing the savepoint; any stage failure restores exact prior session state.',
            ],
        }
    finally:
        probe.close()

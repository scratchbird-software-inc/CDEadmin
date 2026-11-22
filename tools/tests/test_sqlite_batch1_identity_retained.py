"""End-to-end regression tests for SQLite Batch 1 audit items:
SQ-AUD-01, SQ-AUD-05, SQ-AUD-06, SQ-AUD-07, SQ-AUD-08, and SQ-AUD-14.
"""
from __future__ import annotations

from contextlib import closing
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.sqlite import extensions as sqlite_ext
from pgadmin.cdeadmin.providers.sqlite.custom_virtual_modules import (
    compile_custom_arguments,
    inspect_module_capabilities,
)
from pgadmin.cdeadmin.providers.sqlite.driver import SQLiteConnection
from pgadmin.cdeadmin.providers.sqlite.provider import (
    ADMINISTRATION,
    SQLiteProvider,
    _create_client,
    _resource_id,
    _resources,
)
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.workspace import (
    sqlite_rename,
    sqlite_retained_alter as alter,
    sqlite_retained_schema as retained,
)
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.sqlite_retained_applications import SQLiteRetainedApplications


def _provider(tmp_path: Path, db_path: Path):
    ctx = SimpleNamespace(
        endpoint_id='ep-sqlite-b1',
        provider_id='org.cdeadmin.sqlite',
        profile_id='sqlite-native',
    )
    client = _create_client()
    guard = SimpleNamespace(require=Mock())
    prov = SQLiteProvider(ctx, guard, client)
    route = {'database': str(db_path), 'filesystem_root': str(tmp_path)}
    return prov, route


def test_sq_aud_01_destructive_plan_refuses_replacement_object_and_schema_drift(tmp_path: Path):
    db_path = tmp_path / 'aud01.sqlite'
    with closing(sqlite3.connect(db_path)) as conn:
        conn.executescript(
            """
            CREATE TABLE items(id INTEGER PRIMARY KEY, label TEXT, obsolete TEXT);
            CREATE VIEW items_v AS SELECT id, label FROM items;
            CREATE INDEX idx_items_label ON items(label);
            CREATE TRIGGER trg_items AFTER INSERT ON items BEGIN SELECT 1; END;
            CREATE VIRTUAL TABLE items_fts USING fts5(label);
            CREATE VIRTUAL TABLE items_rt USING rtree(id, x0, x1);
            INSERT INTO items(id, label, obsolete) VALUES (1, 'original', 'old');
            """
        )
        conn.commit()

    prov, route = _provider(tmp_path, db_path)
    try:
        catalog = {r['resource_id']: r for r in prov.capture_catalog(route, include_system=False)['resources']}

        # 1) Plan table.drop, then replace table with a new table of the same name -> apply MUST fail closed!
        tbl_res = catalog[_resource_id('table', ['main'], 'items')]
        drop_req = {
            '_provider_route': route,
            'resource_kind': 'table',
            'operation_id': 'drop',
            'target_resource': tbl_res,
            'draft': {},
        }
        drop_plan = ADMINISTRATION.plan(drop_req)
        assert 'sqlite_target_identity' in drop_plan['provider_payload']

        with closing(sqlite3.connect(db_path)) as conn:
            conn.executescript(
                """
                DROP TRIGGER trg_items;
                DROP VIEW items_v;
                DROP TABLE items;
                CREATE TABLE items(id INTEGER PRIMARY KEY, replacement_secret TEXT NOT NULL);
                INSERT INTO items VALUES (99, 'DO_NOT_DELETE');
                """
            )
            conn.commit()

        with pytest.raises(RelationalClientError, match='target identity|DDL|columns|rootpage|schema_version|replaced|modified'):
            ADMINISTRATION.apply(prov.client, {**drop_req, 'provider_payload': drop_plan['provider_payload']})

        with closing(sqlite3.connect(db_path)) as conn:
            assert conn.execute('SELECT * FROM items').fetchall() == [(99, 'DO_NOT_DELETE')]

        # 2) Pre-plan stale catalog snapshot replacement also fails closed at plan time!
        with pytest.raises(RelationalClientError, match='changed before planning|DDL|stale|replaced'):
            ADMINISTRATION.plan(drop_req)

        # 3) Happy-path exact-bound destructive operations succeed when untouched
        fresh = {r['resource_id']: r for r in prov.capture_catalog(route, include_system=False)['resources']}
        fts_res = fresh[_resource_id('fts-table', ['main'], 'items_fts')]
        fts_req = {'_provider_route': route, 'resource_kind': 'fts-table', 'operation_id': 'drop', 'target_resource': fts_res, 'draft': {}}
        fts_drop = ADMINISTRATION.plan(fts_req)
        ADMINISTRATION.apply(prov.client, {**fts_req, 'provider_payload': fts_drop['provider_payload']})

        rt_res = fresh[_resource_id('virtual-table', ['main'], 'items_rt')]
        rt_req = {'_provider_route': route, 'resource_kind': 'virtual-table', 'operation_id': 'rename', 'target_resource': rt_res, 'draft': {'new_name': 'items_rt_v2'}}
        rt_ren = ADMINISTRATION.plan(rt_req)
        ADMINISTRATION.apply(prov.client, {**rt_req, 'provider_payload': rt_ren['provider_payload']})

        with closing(sqlite3.connect(db_path)) as conn:
            names = {r[0] for r in conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
            assert 'items_fts' not in names
            assert 'items_rt_v2' in names
    finally:
        prov.close()


def test_sq_aud_05_retained_session_rebuild_across_main_temp_and_attached(tmp_path: Path):
    main_db = tmp_path / 'aud05_main.sqlite'
    att_db = tmp_path / 'aud05_att.sqlite'
    with closing(sqlite3.connect(main_db)) as conn:
        conn.execute('CREATE TABLE orders(id INTEGER PRIMARY KEY AUTOINCREMENT, old_code TEXT, qty INTEGER)')
        conn.execute("INSERT INTO orders(id, old_code, qty) VALUES (10, 'A-10', 2)")
        conn.commit()
    with closing(sqlite3.connect(att_db)) as conn:
        conn.execute('CREATE TABLE ledger(id INTEGER PRIMARY KEY, note TEXT, amount INTEGER)')
        conn.execute("INSERT INTO ledger VALUES (5, 'committed-att', 50)")
        conn.commit()

    client = _create_client()
    handle = sqlite3.connect(main_db, factory=SQLiteConnection, isolation_level=None)
    handle.set_authorizer(lambda *_args: sqlite3.SQLITE_OK)
    try:
        att_escaped = str(att_db).replace("'", "''")
        handle.execute(f"ATTACH DATABASE '{att_escaped}' AS \"branch.雪\"")
        handle.execute('PRAGMA foreign_keys=ON')
        handle.execute('CREATE TEMP TABLE scratch(id INTEGER PRIMARY KEY, raw_val TEXT)')
        handle.execute('BEGIN')
        handle.execute("INSERT INTO main.orders(old_code, qty) VALUES ('UNCOMMITTED-11', 4)")
        handle.execute("INSERT INTO temp.scratch VALUES (7, 'temp-uncommitted')")
        handle.execute('INSERT INTO "branch.雪".ledger VALUES (6, \'att-uncommitted\', 75)')
        handle.execute('SAVEPOINT caller_outer')

        for ns, tbl, new_ddl, renames in [
            (
                'main',
                'orders',
                'CREATE TABLE "main"."orders"(id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL, qty INTEGER CHECK(qty > 0))',
                {'old_code': 'code'},
            ),
            (
                'temp',
                'scratch',
                'CREATE TABLE "temp"."scratch"(id INTEGER PRIMARY KEY, clean_val TEXT NOT NULL)',
                {'raw_val': 'clean_val'},
            ),
            (
                'branch.雪',
                'ledger',
                'CREATE TABLE "branch.雪"."ledger"(id INTEGER PRIMARY KEY, summary TEXT NOT NULL, amount INTEGER NOT NULL)',
                {'note': 'summary'},
            ),
        ]:
            baseline = retained.observe(client, handle, 'ep', 'sess-05')
            rid = _resource_id('table', [ns], tbl)
            # Build desired schema via isolated prototype
            probe = retained._prototype(baseline, {'main', 'temp', 'branch.雪'}, live_handle=handle)
            try:
                probe.execute(f'DROP TABLE "{ns}"."{tbl}"')
                probe.execute(new_ddl)
                proposed = retained.model(_resources(probe, {}), 'ep', 'sess-05')
            finally:
                probe.close()
            desired = deepcopy(baseline)
            desired['rows'] = {k: v for k, v in desired['rows'].items() if v['kind'] not in retained.KINDS}
            for k, v in proposed['rows'].items():
                if v['kind'] in retained.KINDS:
                    v['native']['observation_scope'] = 'retained-session-design'
                    desired['rows'][k] = v

            live = retained.observe(client, handle, 'ep', 'sess-05')
            plan = retained.plan(
                client,
                handle,
                baseline,
                desired,
                live,
                'ep',
                'sess-05',
                rebuilds=[{'resource_id': rid, 'column_renames': renames}],
            )
            assert plan['ready_for_review'] is True
            assert plan['authority_scope'] == 'retained-original-session-only'
            assert plan['independent_file_authority_claimed'] is False

            record = {
                'plan': plan,
                'baseline': baseline,
                'desired': desired,
                'native_context': retained.context(handle, 1),
            }
            outcome = retained.apply(client, handle, record, 'ep', 'sess-05', 1)
            assert outcome['state'] == 'applied_pending_caller_transaction', outcome
            assert handle.in_transaction is True

        assert handle.execute('SELECT id, code, qty FROM main.orders ORDER BY id').fetchall() == [
            (10, 'A-10', 2),
            (11, 'UNCOMMITTED-11', 4),
        ]
        assert handle.execute("SELECT seq FROM main.sqlite_sequence WHERE name='orders'").fetchone() == (11,)
        assert handle.execute('SELECT id, clean_val FROM temp.scratch').fetchall() == [(7, 'temp-uncommitted')]
        assert handle.execute('SELECT id, summary, amount FROM "branch.雪".ledger ORDER BY id').fetchall() == [
            (5, 'committed-att', 50),
            (6, 'att-uncommitted', 75),
        ]

        # Independent file must NOT see uncommitted retained rebuild or rows
        with closing(sqlite3.connect(main_db)) as outside:
            assert outside.execute('SELECT id, old_code, qty FROM orders').fetchall() == [(10, 'A-10', 2)]

        # Caller savepoint rollback restores everything cleanly
        handle.execute('ROLLBACK TO caller_outer')
        handle.execute('RELEASE caller_outer')
        assert handle.execute('SELECT id, old_code, qty FROM main.orders ORDER BY id').fetchall() == [
            (10, 'A-10', 2),
            (11, 'UNCOMMITTED-11', 4),
        ]
        handle.execute('ROLLBACK')
    finally:
        handle.close()


def test_sq_aud_06_retained_external_content_fts_rebinding_across_namespaces_and_views(tmp_path: Path):
    main_db = tmp_path / 'aud06_main.sqlite'
    att_db = tmp_path / 'aud06_att.sqlite'
    wide = 9007199254740993
    with closing(sqlite3.connect(main_db)) as conn:
        conn.commit()
    with closing(sqlite3.connect(att_db)) as conn:
        conn.commit()

    client = _create_client()
    handle = sqlite3.connect(main_db, factory=SQLiteConnection, isolation_level=None)
    handle.set_authorizer(lambda *_args: sqlite3.SQLITE_OK)
    try:
        att_escaped = str(att_db).replace("'", "''")
        handle.execute(f"ATTACH DATABASE '{att_escaped}' AS \"fts_att\"")
        handle.execute('BEGIN')

        # 1) External-content FTS5 + FTS4 across main, temp, and attached with wide rowids & languageid
        for ns in ('main', 'temp', 'fts_att'):
            sfx = ns
            handle.execute(f'CREATE TABLE "{ns}"."docs5_{sfx}"(doc_id INTEGER PRIMARY KEY, body TEXT)')
            handle.execute(f'INSERT INTO "{ns}"."docs5_{sfx}" VALUES (?, ?)', (wide, f'hello {ns} world'))
            handle.execute(
                f"CREATE VIRTUAL TABLE \"{ns}\".\"idx5_{sfx}\" USING fts5(body, content='docs5_{sfx}', content_rowid='doc_id')"
            )
            handle.execute(f'INSERT INTO "{ns}"."idx5_{sfx}"("idx5_{sfx}") VALUES (\'rebuild\')')

            handle.execute(f'CREATE TABLE "{ns}"."docs4_{sfx}"(id INTEGER PRIMARY KEY, body TEXT, lang INTEGER DEFAULT 2)')
            handle.execute(f'INSERT INTO "{ns}"."docs4_{sfx}" VALUES (42, \'bonjour {ns}\', 2)')
            handle.execute(
                f"CREATE VIRTUAL TABLE \"{ns}\".\"idx4_{sfx}\" USING fts4(body, content='docs4_{sfx}', languageid='lang')"
            )
            handle.execute(f'INSERT INTO "{ns}"."idx4_{sfx}"("idx4_{sfx}") VALUES (\'rebuild\')')

        for ns in ('main', 'temp', 'fts_att'):
            sfx = ns
            baseline = retained.observe(client, handle, 'ep', 'sess-06')
            changes = [
                {'action': 'rename-column', 'resource_id': _resource_id('table', [ns], f'docs5_{sfx}'), 'column': 'body', 'name': 'content_text'},
                {'action': 'rename-table', 'resource_id': _resource_id('table', [ns], f'docs5_{sfx}'), 'name': f'articles5_{sfx}'},
                {'action': 'rename-column', 'resource_id': _resource_id('table', [ns], f'docs4_{sfx}'), 'column': 'lang', 'name': 'locale_id'},
            ]
            fts_ids = [
                _resource_id('fts-table', [ns], f'idx5_{sfx}'),
                _resource_id('fts-table', [ns], f'idx4_{sfx}'),
            ]
            desired = alter.generate(client, handle, baseline, 'ep', 'sess-06', changes, fts_rebindings=fts_ids)[0]
            live = retained.observe(client, handle, 'ep', 'sess-06')
            plan = retained.plan(
                client, handle, baseline, desired, live, 'ep', 'sess-06',
                alterations=changes, fts_rebindings=fts_ids,
            )
            assert plan['ready_for_review'] is True
            record = {
                'plan': plan,
                'baseline': baseline,
                'desired': desired,
                'native_context': retained.context(handle, 1),
            }
            res = retained.apply(client, handle, record, 'ep', 'sess-06', 1)
            assert res['state'] == 'applied_pending_caller_transaction', res
            assert handle.execute(
                f'SELECT rowid, content_text FROM "{ns}"."idx5_{sfx}" WHERE "idx5_{sfx}" MATCH \'hello\''
            ).fetchall() == [(wide, f'hello {ns} world')]
            assert handle.execute(
                f'SELECT rowid, body FROM "{ns}"."idx4_{sfx}" WHERE "idx4_{sfx}" MATCH \'bonjour\' AND locale_id=2'
            ).fetchall() == [(42, f'bonjour {ns}')]

        # 2) Content-view backed FTS5 where underlying table column is renamed -> view projection frozen!
        handle.execute('CREATE TABLE main.raw_notes(id INTEGER PRIMARY KEY, msg TEXT)')
        handle.execute("INSERT INTO main.raw_notes VALUES (77, 'view backed search')")
        handle.execute('CREATE VIEW main.notes_v AS SELECT id, msg FROM raw_notes')
        handle.execute("CREATE VIRTUAL TABLE main.notes_fts USING fts5(msg, content='notes_v', content_rowid='id')")
        handle.execute("INSERT INTO main.notes_fts(notes_fts) VALUES ('rebuild')")

        baseline = retained.observe(client, handle, 'ep', 'sess-06')
        v_changes = [{'action': 'rename-column', 'resource_id': _resource_id('table', ['main'], 'raw_notes'), 'column': 'msg', 'name': 'message_body'}]
        v_fts = [_resource_id('fts-table', ['main'], 'notes_fts')]
        v_desired = alter.generate(client, handle, baseline, 'ep', 'sess-06', v_changes, fts_rebindings=v_fts)[0]
        v_live = retained.observe(client, handle, 'ep', 'sess-06')
        v_plan = retained.plan(client, handle, baseline, v_desired, v_live, 'ep', 'sess-06', alterations=v_changes, fts_rebindings=v_fts)
        v_res = retained.apply(
            client, handle,
            {'plan': v_plan, 'baseline': baseline, 'desired': v_desired, 'native_context': retained.context(handle, 2)},
            'ep', 'sess-06', 2,
        )
        assert v_res['state'] == 'applied_pending_caller_transaction', v_res
        assert handle.execute("SELECT rowid, msg FROM main.notes_fts WHERE notes_fts MATCH 'backed'").fetchall() == [
            (77, 'view backed search')
        ]

        # 3) TEMP shadowing of external-content target in main is refused
        handle.execute('CREATE TEMP TABLE articles5_main(id INTEGER)')
        shadow_base = retained.observe(client, handle, 'ep', 'sess-06')
        with pytest.raises(ValueError, match='shadows external-content FTS target'):
            alter.generate(
                client, handle, shadow_base, 'ep', 'sess-06',
                [{'action': 'rename-table', 'resource_id': _resource_id('table', ['main'], 'articles5_main'), 'name': 'articles5_v2'}],
                fts_rebindings=[_resource_id('fts-table', ['main'], 'idx5_main')],
            )
        handle.execute('ROLLBACK')
    finally:
        handle.close()


def test_sq_aud_07_attached_environment_rename_adapter_and_temp_masking(tmp_path: Path):
    main_db = tmp_path / 'aud07_main.sqlite'
    att1_db = tmp_path / 'aud07_att1.sqlite'
    att2_db = tmp_path / 'aud07_att2.sqlite'
    for p in (main_db, att1_db, att2_db):
        with closing(sqlite3.connect(p)) as c:
            c.commit()

    client = _create_client()
    handle = sqlite3.connect(main_db, factory=SQLiteConnection, isolation_level=None)
    handle.set_authorizer(lambda *_args: sqlite3.SQLITE_OK)
    try:
        handle.execute(f"ATTACH DATABASE '{str(att1_db)}' AS att_one")
        handle.execute(f"ATTACH DATABASE '{str(att2_db)}' AS att_two")
        handle.execute('CREATE TABLE main.accounts(id INTEGER PRIMARY KEY, code TEXT)')
        handle.execute('CREATE TABLE att_one.invoices(id INTEGER PRIMARY KEY, total INTEGER)')
        handle.execute('CREATE VIEW att_one.invoices_v AS SELECT id, total FROM invoices')
        handle.execute('CREATE TABLE att_two.audit_log(id INTEGER PRIMARY KEY, msg TEXT)')
        handle.execute(
            'CREATE TEMP TRIGGER trg_att_inv AFTER INSERT ON att_one.invoices BEGIN INSERT INTO audit_log(msg) VALUES (\'ins\'); END'
        )
        baseline = build_export(
            _resources(handle, {}),
            endpoint_id='ep',
            target_id='main-target',
            generation='g07',
            engine='sqlite',
            native_model=True,
        )

        # Without attachment_policy -> must keep exact refusal
        with pytest.raises(ValueError, match='attachment adapter'):
            sqlite_rename.generate(baseline, [{'kind': 'table', 'table': 'invoices', 'to': 'bills'}])

        # With explicit attachment_policy targeting att_one -> succeeds, rewrites view & TEMP trigger, discloses non_carried_namespaces
        renames = [
            {'kind': 'table', 'table': 'invoices', 'to': 'bills'},
            {'kind': 'column', 'table': 'bills', 'from': 'total', 'to': 'amount_cents'},
        ]
        policy = {'target_namespace': 'att_one'}
        desired, selected, stages = sqlite_rename.generate(baseline, renames, attachment_policy=policy)
        assert any('ALTER TABLE "att_one"."invoices" RENAME TO "bills"' in s for s in stages)
        plan = sqlite_rename.plan(baseline, desired, baseline, renames, attachment_policy=policy)
        assert plan['ready_for_review'] is True
        assert plan['application_supported'] is False  # non-carried namespaces require retained session apply
        assert plan['attachment_report']['target_namespace'] == 'att_one'
        assert plan['attachment_report']['non_carried_namespaces'] == ['att_two', 'main', 'temp']
        assert plan['attachment_report']['attachment_authority'] == 'retained-session-only'

        # TEMP masking of rename target in att_one is refused
        handle.execute('CREATE TEMP TABLE invoices(id INTEGER)')
        masked_baseline = build_export(
            _resources(handle, {}),
            endpoint_id='ep',
            target_id='main-target',
            generation='g07m',
            engine='sqlite',
            native_model=True,
        )
        with pytest.raises(ValueError, match='TEMP object shadows rename target'):
            sqlite_rename.generate(
                masked_baseline,
                [{'kind': 'table', 'table': 'invoices', 'to': 'bills'}],
                attachment_policy=policy,
            )
    finally:
        handle.close()


@pytest.mark.skipif(shutil.which('cc') is None, reason='C compiler unavailable')
def test_sq_aud_08_custom_virtual_module_constructor_and_retained_reproduction(tmp_path: Path):
    # Verify eponymous-only & csv filename_ref refusals immediately
    with pytest.raises(RelationalClientError, match='eponymous-only'):
        compile_custom_arguments('carray', [], {})
    with pytest.raises(RelationalClientError, match='eponymous-only'):
        compile_custom_arguments('generate_series', [], {})
    with pytest.raises(RelationalClientError, match='filename= host path constructor is refused'):
        compile_custom_arguments('csv', [], {'filename_ref': '/etc/passwd'})

    csv_args = compile_custom_arguments('csv', [], {'data': 'a,b\n1,2\n', 'header': True})
    assert "data='a,b\n1,2\n'" in csv_args and 'header' in csv_args

    # Compile a tiny SQLite loadable extension implementing `cde_kv_vtab` (with optional shadow table!)
    headers_dir = os.environ.get('CDEADMIN_SQLITE_HEADERS') or str(
        Path(__file__).resolve().parents[1] / 'reference_engine_demos/runtime/sqlite-tracked/3.53.0/include'
    )
    if not Path(headers_dir, 'sqlite3ext.h').is_file():
        pytest.skip('SQLite headers not present')

    c_src = tmp_path / 'cde_kv_vtab.c'
    so_path = tmp_path / 'libcde_kv_vtab.so'
    c_src.write_text(
        r"""
#include "sqlite3ext.h"
SQLITE_EXTENSION_INIT1
#include <string.h>
#include <stdio.h>

typedef struct KvTab { sqlite3_vtab base; } KvTab;
typedef struct KvCur { sqlite3_vtab_cursor base; int eof; } KvCur;

static int kvCreate(sqlite3 *db, void *pAux, int argc, const char *const*argv, sqlite3_vtab **ppVtab, char **pzErr){
  int rc = sqlite3_declare_vtab(db, "CREATE TABLE x(k TEXT, v TEXT)");
  if( rc!=SQLITE_OK ) return rc;
  for(int i=3; i<argc; i++){
    if( strcmp(argv[i], "with_shadow=1")==0 ){
      char *zSql = sqlite3_mprintf("CREATE TABLE IF NOT EXISTS \"%w\".\"%w_kv_shadow\"(id INTEGER PRIMARY KEY, payload BLOB)", argv[1], argv[2]);
      rc = sqlite3_exec(db, zSql, 0, 0, pzErr);
      sqlite3_free(zSql);
      if( rc!=SQLITE_OK ) return rc;
    }
  }
  KvTab *p = sqlite3_malloc(sizeof(KvTab));
  if( !p ) return SQLITE_NOMEM;
  memset(p, 0, sizeof(KvTab));
  *ppVtab = &p->base;
  return SQLITE_OK;
}
static int kvConnect(sqlite3 *db, void *pAux, int argc, const char *const*argv, sqlite3_vtab **ppVtab, char **pzErr){
  int rc = sqlite3_declare_vtab(db, "CREATE TABLE x(k TEXT, v TEXT)");
  if( rc!=SQLITE_OK ) return rc;
  KvTab *p = sqlite3_malloc(sizeof(KvTab));
  if( !p ) return SQLITE_NOMEM;
  memset(p, 0, sizeof(KvTab));
  *ppVtab = &p->base;
  return SQLITE_OK;
}
static int kvBestIndex(sqlite3_vtab *pVTab, sqlite3_index_info *pIdxInfo){ return SQLITE_OK; }
static int kvDisconnect(sqlite3_vtab *pVTab){ sqlite3_free(pVTab); return SQLITE_OK; }
static int kvDestroy(sqlite3_vtab *pVTab){ sqlite3_free(pVTab); return SQLITE_OK; }
static int kvOpen(sqlite3_vtab *p, sqlite3_vtab_cursor **ppCursor){
  KvCur *c = sqlite3_malloc(sizeof(KvCur));
  if( !c ) return SQLITE_NOMEM;
  memset(c, 0, sizeof(KvCur));
  *ppCursor = &c->base;
  return SQLITE_OK;
}
static int kvClose(sqlite3_vtab_cursor *cur){ sqlite3_free(cur); return SQLITE_OK; }
static int kvFilter(sqlite3_vtab_cursor *cur, int idxNum, const char *idxStr, int argc, sqlite3_value **argv){
  ((KvCur*)cur)->eof = 0; return SQLITE_OK;
}
static int kvNext(sqlite3_vtab_cursor *cur){ ((KvCur*)cur)->eof = 1; return SQLITE_OK; }
static int kvEof(sqlite3_vtab_cursor *cur){ return ((KvCur*)cur)->eof; }
static int kvColumn(sqlite3_vtab_cursor *cur, sqlite3_context *ctx, int i){
  sqlite3_result_text(ctx, i==0 ? "key1" : "val1", -1, SQLITE_STATIC);
  return SQLITE_OK;
}
static int kvRowid(sqlite3_vtab_cursor *cur, sqlite_int64 *pRowid){ *pRowid = 1; return SQLITE_OK; }

static sqlite3_module kvModule = {
  0, kvCreate, kvConnect, kvBestIndex, kvDisconnect, kvDestroy,
  kvOpen, kvClose, kvFilter, kvNext, kvEof, kvColumn, kvRowid,
  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
};

int sqlite3_cdekvvtab_init(sqlite3 *db, char **pzErrMsg, const sqlite3_api_routines *pApi){
  SQLITE_EXTENSION_INIT2(pApi);
  return sqlite3_create_module(db, "cde_kv_vtab", &kvModule, 0);
}
""",
        encoding='utf-8',
    )
    subprocess.run(
        ['cc', '-O2', '-fPIC', '-shared', f'-I{headers_dir}', str(c_src), '-o', str(so_path)],
        check=True,
    )
    sha = hashlib.sha256(so_path.read_bytes()).hexdigest()
    manifest_path = tmp_path / 'ext_manifest.json'
    manifest_path.write_text(
        json.dumps({
            'format': 'scratchrobin.sqlite.extensions@1',
            'extensions': [{
                'id': 'cde_kv_vtab',
                'path': str(so_path),
                'sha256': sha,
                'entrypoint': 'sqlite3_cdekvvtab_init',
            }],
        }),
        encoding='utf-8',
    )

    db_path = tmp_path / 'aud08.sqlite'
    prov_08, route_vtab = _provider(tmp_path, db_path)
    client = prov_08.client
    handle = client.open_session({'route': route_vtab, 'language_profile': 'sqlite-sql'})
    handle.set_authorizer(lambda *_args: sqlite3.SQLITE_OK)
    try:
        rev = sqlite_ext.action(client, handle, {'operation': 'review', 'extension_id': 'cde_kv_vtab'}, str(manifest_path))
        loaded = sqlite_ext.action(
            client, handle,
            {'operation': 'load', 'review_id': rev['review_id'], 'confirmed': True},
            str(manifest_path),
        )
        assert loaded['state'] == 'loaded', loaded
        caps = inspect_module_capabilities(handle)
        assert caps['custom_creatable_modules']['cde_kv_vtab']['installed'] is True

        vtab_req = {
            '_provider_route': route_vtab,
            '_provider_session_handle': handle,
            'resource_kind': 'virtual-table',
            'operation_id': 'create',
            'target_resource': None,
            'draft': {
                'parent': 'main',
                'name': 'kv_items',
                'module': 'cde_kv_vtab',
                'columns': ['k', 'v'],
                'module_options': {'namespace_tag': 'demo', 'with_shadow': True},
            },
        }
        vtab_plan = ADMINISTRATION.plan(vtab_req)
        ADMINISTRATION.apply(
            client,
            {**vtab_req, 'provider_payload': vtab_plan['provider_payload']},
            connection=handle,
        )
        handle.commit()
        assert handle.execute('SELECT k, v FROM kv_items').fetchall() == [('key1', 'val1')]

        # Verify retained DDL reproduces cde_kv_vtab and identifies kv_items_kv_shadow as module storage!
        handle.execute('CREATE TABLE main.regular(id INTEGER PRIMARY KEY)')
        handle.commit()
        handle.execute('BEGIN')
        baseline = retained.observe(client, handle, 'ep', 'sess-08')
        desired = retained.generate_columns(
            client, handle, baseline, 'ep', 'sess-08',
            _resource_id('table', ['main'], 'regular'),
            [{'name': 'added_col', 'data_type': 'TEXT'}],
        )
        live = retained.observe(client, handle, 'ep', 'sess-08')
        plan = retained.plan(client, handle, baseline, desired, live, 'ep', 'sess-08')
        assert ['main', 'kv_items_kv_shadow'] in plan['module_storage']
        out = retained.apply(
            client, handle,
            {'plan': plan, 'baseline': baseline, 'desired': desired, 'native_context': retained.context(handle, 1)},
            'ep', 'sess-08', 1,
        )
        assert out['state'] == 'applied_pending_caller_transaction', out
        handle.execute('ROLLBACK')
    finally:
        client.close_session(handle)
        prov_08.close()


def test_sq_aud_14_retained_receipt_store_sharding_scales_o1(tmp_path: Path):
    store_file = tmp_path / 'retained_receipts.json'
    archive = SQLiteRetainedApplications(store_file)

    big_rows = {
        f'sqlite:["table","main","tbl_{i}"]': {
            'resource_id': f'sqlite:["table","main","tbl_{i}"]',
            'kind': 'table',
            'path': ['main', f'tbl_{i}'],
            'name': f'tbl_{i}',
            'system': 'false',
            'native': {'ddl': f'CREATE TABLE tbl_{i}(id INTEGER, pad TEXT DEFAULT \'{"x" * 600}\')'},
        }
        for i in range(60)
    }
    baseline = {'provenance': {'mapping': 'scratchrobin.sqlite.catalog@1'}, 'rows': big_rows}
    desired = deepcopy(baseline)

    review_ids = []
    for idx in range(35):
        ops = [{'operation': 'create', 'kind': 'table', 'name': f'add_{idx}', 'source': f'CREATE TABLE add_{idx}(id INT)'}]
        from pgadmin.cdeadmin.workspace.firebird_schema_plan import digest
        plan = {
            'format': retained.FORMAT,
            'engine': 'sqlite',
            'provider_session_id': 'sess-scale',
            'operations': ops,
            'execution_sha256': digest(ops),
            'ready_for_review': True,
            'application_supported': True,
            'native_grammar_validated': True,
        }
        rev = archive.review(plan, baseline, desired, {'revision': idx, 'in_transaction': True}, 'owner-1', 'bind-1', 'target-1', 'sess-scale')
        review_ids.append(rev['review_id'])

    # Index file stays compact (< 64 KiB for 35 large reviews, instead of 20+ MiB!)
    index_bytes = store_file.stat().st_size
    assert index_bytes < 65536, f'Expected compact index file, got {index_bytes} bytes'

    sidecar = Path(str(store_file) + '.records') / f'{review_ids[0]}.json'
    assert sidecar.is_file()
    assert stat.S_IMODE(sidecar.stat().st_mode) == 0o600

    listed = archive.list('owner-1', 'bind-1', offset=0, limit=10)
    assert listed['total'] == 35 and len(listed['receipts']) == 10
    detail = archive.get(review_ids[-1], 'owner-1', 'bind-1')
    assert len(detail['plan']['operations']) == 1
    archive.remove(review_ids[0], 'owner-1', 'bind-1', confirmed=True)
    assert not sidecar.exists()
    assert archive.list('owner-1', 'bind-1')['total'] == 34

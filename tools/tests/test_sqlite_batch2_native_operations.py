"""End-to-end HTTP and provider tests for SQLite Batch 2 native operations:
SQ-AUD-09 (RBU), SQ-AUD-10 (Expert Index Advisor), SQ-AUD-11 (Incremental Integrity Check),
SQ-AUD-12 (Incremental Large-BLOB Transfer), SQ-AUD-13 (External Shell & Matching CLI),
and SQ-AUD-15 (Database-Wide Native SQL Script Exchange).
"""
from __future__ import annotations

import base64
import builtins
from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import uuid

import pytest


@pytest.fixture(scope='module')
def _sqlite_flask_app(tmp_path_factory):
    app_root = tmp_path_factory.mktemp('sqlite_b2_app')
    builtins.SERVER_MODE = None
    import config

    config.SERVER_MODE = False
    config.TESTING = True
    config.WTF_CSRF_ENABLED = False
    config.MASTER_PASSWORD_REQUIRED = False
    config.USE_OS_SECRET_STORAGE = False
    for key, rel in {
        'DATA_DIR': 'app',
        'SQLITE_PATH': 'app/app.db',
        'SESSION_DB_PATH': 'app/sessions',
        'STORAGE_DIR': 'app/storage',
        'LOG_FILE': 'app/app.log',
        'AZURE_CREDENTIAL_CACHE_DIR': 'app/azure',
        'CDEADMIN_OPERATION_STORE_PATH': 'app/operations.json',
    }.items():
        setattr(config, key, str(app_root / rel))
    for env_key in (
        'CDEADMIN_SQLITE_BINARY',
        'CDEADMIN_SQLITE_RBU_LIBRARY',
        'CDEADMIN_SQLITE_EXPERT_LIBRARY',
        'CDEADMIN_SQLITE_INTCK_LIBRARY',
    ):
        if os.environ.get(env_key):
            setattr(config, env_key, os.environ[env_key])

    import importlib.util
    import sys

    pg_mod = sys.modules.get('pgadmin')
    if pg_mod is not None and not hasattr(pg_mod, 'create_app'):
        init_py = Path(__file__).resolve().parents[2] / 'web/pgadmin/__init__.py'
        spec = importlib.util.spec_from_file_location(
            'pgadmin', init_py, submodule_search_locations=[str(init_py.parent)]
        )
        pg_mod.__file__ = str(init_py)
        pg_mod.__spec__ = spec
        pg_mod.__loader__ = spec.loader
        spec.loader.exec_module(pg_mod)

    from pgadmin import create_app
    app = create_app('ScratchRobin SQLite Batch 2 Test')
    app.PGADMIN_RUNTIME = False
    app.PGADMIN_INT_KEY = ''
    # The tests authenticate through the session, not the encrypted user-configuration login.
    app.config['USER_CONFIG_LOGIN_REQUIRED'] = False
    app.run_before_app_start()
    return app


@pytest.fixture()
def sqlite_http_env(_sqlite_flask_app, tmp_path: Path):
    from flask import url_for
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.model import EndpointDatabaseTarget, Server, ServerGroup, User, db

    app = _sqlite_flask_app
    client = app.test_client()

    db_dir = tmp_path / 'databases'
    db_dir.mkdir(parents=True, exist_ok=True)
    main_db = db_dir / 'primary.sqlite'
    restore_db = db_dir / 'restored.sqlite'
    with closing(sqlite3.connect(main_db)) as conn:
        conn.commit()
    with closing(sqlite3.connect(restore_db)) as conn:
        conn.commit()

    target_main = str(uuid.uuid4())
    target_restore = str(uuid.uuid4())
    with app.test_request_context('/'):
        owner = User.query.first().id
        group = ServerGroup.query.filter_by(user_id=owner).first()
        server = Server(
            user_id=owner,
            servergroup_id=group.id,
            name='SQLite Batch 2 Registration ' + uuid.uuid4().hex[:8],
            host=None,
            port=1,
            username='',
            maintenance_db=str(main_db),
            save_password=0,
        )
        server._cde_endpoint_registration = registration_profile('sqlite-native')
        server._cde_endpoint_route_configuration = {
            'database': str(main_db),
            'filesystem_root': str(db_dir),
        }
        db.session.add(server)
        db.session.commit()
        for tid, path in ((target_main, main_db), (target_restore, restore_db)):
            db.session.add(
                EndpointDatabaseTarget(
                    id=tid,
                    endpoint_id=server.endpoint_profile.id,
                    display_name=path.name,
                    database=str(path),
                    configuration='{}',
                    active=1,
                )
            )
        db.session.commit()
        ws_url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=server.id)
        verify_url = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=server.id)

    with client.session_transaction() as login:
        login['_user_id'] = str(owner)
        login['_fresh'] = True
    assert bool(client.post(verify_url, json={}).get_json()['success'])

    def call(action: str, req: dict, *, target: str = target_main, expect_error: bool = False):
        resp = client.post(
            ws_url,
            json={'action': action, 'request': {'database_target_id': target, **req}},
        )
        body = resp.get_json()
        if expect_error:
            assert resp.status_code in {400, 403, 409}, body
            return body
        assert resp.status_code == 200 and bool(body.get('success')), body
        return body['data']

    return {
        'call': call,
        'main_db': main_db,
        'restore_db': restore_db,
        'db_dir': db_dir,
        'target_main': target_main,
        'target_restore': target_restore,
    }


def test_sq_aud_09_rbu_resumable_bulk_update_and_vacuum(sqlite_http_env):
    if not os.environ.get('CDEADMIN_SQLITE_RBU_LIBRARY'):
        pytest.skip('CDEADMIN_SQLITE_RBU_LIBRARY not configured for this interpreter')
    call = sqlite_http_env['call']
    main_db = sqlite_http_env['main_db']

    with closing(sqlite3.connect(main_db)) as conn:
        conn.executescript(
            """
            CREATE TABLE accounts(id INTEGER PRIMARY KEY, holder TEXT, balance INTEGER);
            CREATE INDEX idx_accounts_holder ON accounts(holder);
            INSERT INTO accounts VALUES (1, 'Alice', 100), (2, 'Bob', 200), (3, 'Obsolete', 50);
            """
        )
        conn.commit()

    cat = call('sqlite_ops_rbu_catalog', {})
    assert cat['runtime']['available'] is True

    opened = call(
        'sqlite_ops_rbu_open_update',
        {
            'tables': [{
                'table': 'accounts',
                'operations': [
                    {'op': 'insert', 'values': {'id': 4, 'holder': 'Diana', 'balance': 400}},
                    {'op': 'insert', 'values': {'id': 5, 'holder': 'Evan', 'balance': 500}},
                    {'op': 'update', 'set_columns': ['balance'], 'values': {'id': 1, 'balance': 175}},
                    {'op': 'delete', 'values': {'id': 3}},
                ],
            }],
        },
    )
    job_id = opened['job_id']
    assert opened['state'] == 'open'

    step1 = call('sqlite_ops_rbu_step', {'job_id': job_id, 'step_budget': 2})
    if step1['state'] != 'completed':
        paused = call('sqlite_ops_rbu_pause', {'job_id': job_id})
        assert paused['state'] == 'paused'
        # Stepping while paused is refused until explicit resume
        call('sqlite_ops_rbu_step', {'job_id': job_id, 'step_budget': 5}, expect_error=True)
        done = call('sqlite_ops_rbu_resume', {'job_id': job_id, 'step_budget': 5000})
    else:
        done = step1
    assert done['state'] == 'completed'

    with closing(sqlite3.connect(main_db)) as conn:
        rows = conn.execute('SELECT id, holder, balance FROM accounts ORDER BY id').fetchall()
        assert rows == [(1, 'Alice', 175), (2, 'Bob', 200), (4, 'Diana', 400), (5, 'Evan', 500)]

    # Resumable RBU Vacuum lifecycle
    vac = call('sqlite_ops_rbu_open_vacuum', {})
    vac_done = call('sqlite_ops_rbu_step', {'job_id': vac['job_id'], 'step_budget': 10000})
    assert vac_done['state'] == 'completed'


def test_sq_aud_10_expert_index_advisor_preview_only(sqlite_http_env):
    if not os.environ.get('CDEADMIN_SQLITE_EXPERT_LIBRARY'):
        pytest.skip('CDEADMIN_SQLITE_EXPERT_LIBRARY not configured for this interpreter')
    call = sqlite_http_env['call']
    main_db = sqlite_http_env['main_db']

    with closing(sqlite3.connect(main_db)) as conn:
        conn.executescript(
            """
            CREATE TABLE shipments(id INTEGER PRIMARY KEY, region TEXT, carrier TEXT, weight INTEGER);
            INSERT INTO shipments(region, carrier, weight) VALUES ('NA', 'DHL', 10), ('EU', 'UPS', 25), ('NA', 'DHL', 18);
            """
        )
        conn.commit()
        before_indexes = conn.execute("SELECT name FROM sqlite_schema WHERE type='index'").fetchall()

    st = call('sqlite_ops_expert_status', {})
    assert st['available'] is True and st['indexes_applied_automatically'] is False

    report = call(
        'sqlite_ops_expert_analyze',
        {
            'queries': ["SELECT id, weight FROM shipments WHERE region = 'NA' AND carrier = 'DHL' ORDER BY weight"],
            'sample_percent': 100,
        },
    )
    assert report['indexes_applied'] is False
    assert report['schema_version_before'] == report['schema_version_after']
    assert report['statement_count'] == 1
    assert any('CREATE INDEX' in idx.upper() for idx in report['statements'][0]['recommended_indexes'])

    with closing(sqlite3.connect(main_db)) as conn:
        after_indexes = conn.execute("SELECT name FROM sqlite_schema WHERE type='index'").fetchall()
        assert after_indexes == before_indexes


def test_sq_aud_11_incremental_integrity_check_and_corruption_detection(sqlite_http_env):
    if not os.environ.get('CDEADMIN_SQLITE_INTCK_LIBRARY'):
        pytest.skip('CDEADMIN_SQLITE_INTCK_LIBRARY not configured for this interpreter')
    call = sqlite_http_env['call']
    main_db = sqlite_http_env['main_db']

    with closing(sqlite3.connect(main_db)) as conn:
        conn.executescript(
            """
            CREATE TABLE ledger_items(id INTEGER PRIMARY KEY, code TEXT NOT NULL, amount INTEGER);
            CREATE INDEX idx_ledger_code ON ledger_items(code);
            """
        )
        conn.executemany(
            'INSERT INTO ledger_items(code, amount) VALUES (?, ?)',
            [(f'CODE-{i:04d}', i * 10) for i in range(80)],
        )
        conn.commit()

    ck = call('sqlite_ops_intck_open', {'schema_name': 'main', 'unlock_interval': 3})
    assert 'does not repair or recover' in ck['disclaimer'] or 'never repairs or recovers' in ck['disclaimer']
    b1 = call('sqlite_ops_intck_step', {'job_id': ck['job_id'], 'max_steps': 2})
    if b1['state'] != 'completed':
        call('sqlite_ops_intck_pause', {'job_id': ck['job_id']})
        call('sqlite_ops_intck_step', {'job_id': ck['job_id'], 'max_steps': 2}, expect_error=True)
        b_done = call('sqlite_ops_intck_resume', {'job_id': ck['job_id'], 'max_steps': 5000})
    else:
        b_done = b1
    assert b_done['state'] == 'completed'
    assert b_done['corrupt_detected'] is False
    assert b_done['unlock_count'] >= 1

    # Introduce an index/table desynchronization via writable_schema + PRAGMA ignore_check_constraints / index corruption
    # Create a shadow index, insert row without updating index by corrupting index rootpage or mismatched index via sqlite_dbpage!
    with closing(sqlite3.connect(main_db)) as conn:
        has_dbpage = conn.execute("SELECT 1 FROM pragma_module_list WHERE name='sqlite_dbpage'").fetchone() is not None
        if has_dbpage:
            idx_root = conn.execute("SELECT rootpage FROM sqlite_schema WHERE name='idx_ledger_code'").fetchone()[0]
            page_bytes = bytearray(conn.execute('SELECT data FROM sqlite_dbpage WHERE pgno=?', (idx_root,)).fetchone()[0])
            # Corrupt cell count / header bytes in the index page
            page_bytes[3] = 0xFF
            page_bytes[4] = 0xFF
            conn.execute('UPDATE sqlite_dbpage SET data=? WHERE pgno=?', (bytes(page_bytes), idx_root))
            conn.commit()

            ck_bad = call('sqlite_ops_intck_open', {'schema_name': 'main', 'unlock_interval': 4})
            # Either corrupter triggers corruption_messages or SQLITE_CORRUPT error — both prove corruption detection!
            resp = None
            try:
                resp = call('sqlite_ops_intck_step', {'job_id': ck_bad['job_id'], 'max_steps': 5000})
            except AssertionError:
                resp = call('sqlite_ops_intck_step', {'job_id': ck_bad['job_id'], 'max_steps': 5000}, expect_error=True)
            assert (isinstance(resp, dict) and (resp.get('corrupt_detected') is True or 'errormsg' in resp)), resp


def test_sq_aud_12_incremental_large_blob_transfer_and_abort_guards(sqlite_http_env):
    call = sqlite_http_env['call']
    main_db = sqlite_http_env['main_db']

    with closing(sqlite3.connect(main_db)) as conn:
        conn.executescript(
            """
            CREATE TABLE media_store(id INTEGER PRIMARY KEY, title TEXT, payload BLOB);
            CREATE TABLE no_rowid_tbl(k TEXT PRIMARY KEY, payload BLOB) WITHOUT ROWID;
            INSERT INTO media_store VALUES (1, 'null-row', NULL), (2, 'zero-row', zeroblob(0)), (3, 'text-row', 'not-a-blob');
            INSERT INTO no_rowid_tbl VALUES ('k1', X'ABCD');
            """
        )
        conn.commit()

    # WITHOUT ROWID refused
    call('sqlite_ops_blob_inspect', {'table_name': 'no_rowid_tbl', 'column_name': 'payload', 'rowid': 1}, expect_error=True)

    # NULL vs zeroblob(0) vs TEXT distinguished
    c_null = call('sqlite_ops_blob_inspect', {'table_name': 'media_store', 'column_name': 'payload', 'rowid': 1})
    assert c_null['is_null'] is True and c_null['streamable_blob'] is False
    call('sqlite_ops_blob_read_chunk', {'table_name': 'media_store', 'column_name': 'payload', 'rowid': 1}, expect_error=True)

    c_zero = call('sqlite_ops_blob_inspect', {'table_name': 'media_store', 'column_name': 'payload', 'rowid': 2})
    assert c_zero['is_empty_zeroblob'] is True and c_zero['streamable_blob'] is True and c_zero['byte_length'] == 0

    c_txt = call('sqlite_ops_blob_inspect', {'table_name': 'media_store', 'column_name': 'payload', 'rowid': 3})
    assert c_txt['typeof'] == 'text' and c_txt['streamable_blob'] is False

    # Allocate 200 KiB zeroblob on row 1, stream-write two 100 KiB chunks, stream-read back and verify SHA-256
    part1 = bytes((i % 251 for i in range(100_000)))
    part2 = bytes(((i * 7) % 253 for i in range(100_000)))
    full_expected = part1 + part2

    alloc_rev = call(
        'sqlite_ops_blob_allocate_review',
        {'table_name': 'media_store', 'column_name': 'payload', 'rowid': 1, 'byte_length': len(full_expected)},
    )
    alloc_out = call(
        'sqlite_ops_blob_allocate_apply',
        {'review_id': alloc_rev['review_id'], 'review_digest': alloc_rev['review_digest'], 'confirmed': True},
    )
    assert alloc_out['state'] == 'committed'

    for offset, chunk in ((0, part1), (len(part1), part2)):
        w_rev = call(
            'sqlite_ops_blob_write_review',
            {
                'table_name': 'media_store',
                'column_name': 'payload',
                'rowid': 1,
                'offset': offset,
                'encoding': 'base64',
                'data': base64.b64encode(chunk).decode('ascii'),
            },
        )
        w_out = call(
            'sqlite_ops_blob_write_apply',
            {'review_id': w_rev['review_id'], 'review_digest': w_rev['review_digest'], 'confirmed': True},
        )
        assert w_out['state'] == 'committed'

    read1 = call(
        'sqlite_ops_blob_read_chunk',
        {'table_name': 'media_store', 'column_name': 'payload', 'rowid': 1, 'offset': 0, 'length': 120_000, 'encoding': 'base64'},
    )
    read2 = call(
        'sqlite_ops_blob_read_chunk',
        {'table_name': 'media_store', 'column_name': 'payload', 'rowid': 1, 'offset': 120_000, 'length': 120_000, 'encoding': 'base64'},
    )
    assembled = base64.b64decode(read1['data']) + base64.b64decode(read2['data'])
    assert hashlib.sha256(assembled).hexdigest() == hashlib.sha256(full_expected).hexdigest()
    assert read2['eof'] is True


def test_sq_aud_13_and_15_external_shell_dot_commands_and_sql_script_exchange(sqlite_http_env):
    if not os.environ.get('CDEADMIN_SQLITE_BINARY'):
        pytest.skip('CDEADMIN_SQLITE_BINARY not configured for this interpreter')
    call = sqlite_http_env['call']
    main_db = sqlite_http_env['main_db']
    restore_db = sqlite_http_env['restore_db']
    target_restore = sqlite_http_env['target_restore']

    with closing(sqlite3.connect(main_db)) as conn:
        conn.executescript(
            """
            CREATE TABLE customers(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, notes TEXT, avatar BLOB);
            CREATE INDEX idx_cust_name ON customers(name);
            CREATE VIEW customers_v AS SELECT id, name FROM customers;
            CREATE TRIGGER trg_cust AFTER INSERT ON customers BEGIN SELECT 1; END;
            CREATE VIRTUAL TABLE cust_fts USING fts5(name, notes);
            """
        )
        conn.execute(
            'INSERT INTO customers(name, notes, avatar) VALUES (?, ?, ?)',
            ('Ada\nLovelace', 'first\nprogrammer', b'\x00\xff\x10\x20sqlite'),
        )
        conn.execute("INSERT INTO cust_fts(name, notes) VALUES ('Ada Lovelace', 'analytical engine')")
        conn.commit()

    # SQ-AUD-13: Matching CLI provenance + read-only dot-commands + unsafe command refusal
    prov = call('sqlite_ops_shell_provenance', {})
    assert prov['matched'] is True
    assert prov['python_runtime'] == prov['cli_runtime']

    for cmd in ('dbinfo', 'schema', 'tables', 'indexes'):
        out = call('sqlite_ops_shell_inspect', {'command': cmd})
        assert out['sql_execute_dispatched'] is False
        assert out['read_only_safe_mode'] is True
        assert len(out['output']) > 0

    call('sqlite_ops_shell_inspect', {'command': 'shell'}, expect_error=True)

    # Verify fail-closed mismatch refusal when binary path does not match runtime
    from pgadmin.cdeadmin.providers.sqlite.shell_tool import SQLiteShellError, verify_matching_cli
    with pytest.raises(SQLiteShellError, match='unavailable|failed|mismatch|JSON'):
        verify_matching_cli('/bin/echo')

    # SQ-AUD-15: Full database SQL dump + artifact read + reviewed import into restore_db
    exported = call('sqlite_ops_dump_export', {'preserve_newlines': True})
    assert exported['fidelity']['contains_blob_values'] is True
    assert exported['fidelity']['contains_embedded_newlines'] is True
    dump_read = call('sqlite_ops_dump_read', {'dump_id': exported['dump_id']})
    assert dump_read['sha256'] == exported['sha256']

    imp_rev = call('sqlite_ops_dump_import_review', {'sql_text': dump_read['sql_text']}, target=target_restore)
    imp_out = call(
        'sqlite_ops_dump_import_apply',
        {'review_id': imp_rev['review_id'], 'review_digest': imp_rev['review_digest'], 'confirmed': True},
        target=target_restore,
    )
    assert imp_out['state'] == 'committed'
    assert imp_out['outcome']['rediscovery_verified'] is True

    with closing(sqlite3.connect(restore_db)) as reader:
        row = reader.execute('SELECT name, notes, avatar FROM customers').fetchone()
        assert row == ('Ada\nLovelace', 'first\nprogrammer', b'\x00\xff\x10\x20sqlite')
        assert reader.execute('SELECT id, name FROM customers_v').fetchall() == [(1, 'Ada\nLovelace')]
        assert reader.execute("SELECT name FROM cust_fts WHERE cust_fts MATCH 'analytical'").fetchall() == [('Ada Lovelace',)]

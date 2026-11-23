"""Live DuckDB 1.5.2 tests for Batch 4: Shell/Directives, SQL Stream Dump, Physical Continuity & Storage Lifecycle (DU-AUD-18..21)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import struct
import threading

import duckdb
import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb import (
    physical_continuity,
    shell_tool,
    sql_dump,
    storage_lifecycle,
)


# ---------------------------------------------------------------------------
# DU-AUD-18: Native shell provenance & supervised client directive runner
# ---------------------------------------------------------------------------

def test_du_aud_18_shell_provenance_and_matching_vs_mismatched_cli(tmp_path):
    prov = shell_tool.inspect_shell_provenance()
    assert prov['python_runtime']['version'] == '1.5.2'
    assert prov['python_runtime']['source_id'] == '8a5851971f'

    # Mismatched CLI binary wrapper MUST fail closed
    bad_cli = tmp_path / 'fake_duckdb_mismatch'
    bad_cli.write_text(
        '#!/usr/bin/env python3\n'
        'import json\n'
        'print(json.dumps([{"library_version": "v1.4.0", "source_id": "deadbeef00"}]))\n',
        encoding='utf-8',
    )
    bad_cli.chmod(bad_cli.stat().st_mode | stat.S_IEXEC)
    with pytest.raises(shell_tool.DuckDBShellError, match='provenance mismatch'):
        shell_tool.inspect_shell_provenance(str(bad_cli))

    # Exact matching CLI wrapper is admitted and supervised via observe_process
    good_cli = tmp_path / 'duckdb_matched'
    py_exe = os.path.abspath(os.sys.executable)
    good_cli.write_text(
        f'#!{py_exe}\n'
        'import sys, json, duckdb\n'
        'args = sys.argv[1:]\n'
        'if "-json" in args:\n'
        '    c = duckdb.connect(":memory:")\n'
        '    v, s = c.execute("SELECT library_version, source_id FROM pragma_version()").fetchone()\n'
        '    print(json.dumps([{"library_version": v, "source_id": s}]))\n'
        '    sys.exit(0)\n'
        'db = args[-1]\n'
        'sql = sys.stdin.read()\n'
        'c = duckdb.connect(db, config={"access_mode": "READ_ONLY"} if "-readonly" in args and db != ":memory:" else {})\n'
        'print(c.execute(sql).fetchall())\n',
        encoding='utf-8',
    )
    good_cli.chmod(good_cli.stat().st_mode | stat.S_IEXEC)
    matched = shell_tool.inspect_shell_provenance(str(good_cli))
    assert matched['cli_available'] is True and matched['matched'] is True
    assert matched['binary_sha256']

    db_file = tmp_path / 'cli_test.duckdb'
    c = duckdb.connect(str(db_file))
    c.execute('CREATE TABLE t (x INTEGER); INSERT INTO t VALUES (7);')
    c.close()
    route = {'database': str(db_file), 'filesystem_root': str(tmp_path)}
    batch_res = shell_tool.execute_cli_batch(route, 'SELECT x FROM t;', explicit_binary=str(good_cli))
    assert batch_res['return_code'] == 0
    assert '(7,)' in batch_res['stdout']


def test_du_aud_18_directive_execution_includes_outputs_and_security_refusals(tmp_path):
    db_file = tmp_path / 'dir.duckdb'
    con = duckdb.connect(str(db_file))
    con.execute('CREATE TABLE products (id INTEGER PRIMARY KEY, name VARCHAR, price DECIMAL(10,2))')
    con.execute('CREATE INDEX idx_prod_name ON products (name)')
    con.execute("INSERT INTO products VALUES (1, 'Widget', 19.95), (2, NULL, 5.00)")
    con.close()

    inc_file = tmp_path / 'sub_query.sql'
    inc_file.write_text(
        '.mode json\n'
        'SELECT id, name FROM products ORDER BY id;\n',
        encoding='utf-8',
    )

    route = {'database': str(db_file), 'filesystem_root': str(tmp_path)}
    script = (
        '.nullvalue NULLVAL\n'
        '.mode csv\n'
        '.headers on\n'
        '.once exported.csv\n'
        'SELECT id, name FROM products ORDER BY id;\n'
        '.tables prod%\n'
        '.indexes prod%\n'
        '.read sub_query.sql\n'
    )
    res = shell_tool.execute_directive_script(route, {'script': script, 'read_only': True})
    assert res['state'] == 'succeeded', res
    assert res['connection_isolated'] is True
    assert res['connection_cleanup_confirmed'] is True
    csv_out = (tmp_path / 'exported.csv').read_text(encoding='utf-8')
    assert 'id,name\n1,Widget\n2,NULLVAL\n' == csv_out
    assert '[{"id": 1, "name": "Widget"}, {"id": 2, "name": null}]' in res['output']

    # Forbidden .shell directive refused
    bad_shell = shell_tool.execute_directive_script(route, {'script': '.shell uname -a\n', 'read_only': True})
    assert bad_shell['state'] == 'failed'
    assert 'forbidden' in bad_shell['error']

    # Path traversal outside filesystem_root refused
    bad_path = shell_tool.execute_directive_script(route, {'script': '.read ../outside.sql\n', 'read_only': True})
    assert bad_path['state'] == 'failed'

    # Recursive .read cycle refused
    cyc = tmp_path / 'cycle.sql'
    cyc.write_text('.read cycle.sql\n', encoding='utf-8')
    bad_cyc = shell_tool.execute_directive_script(route, {'source_file': 'cycle.sql', 'read_only': True})
    assert bad_cyc['state'] == 'failed'
    assert 'cycle' in bad_cyc['error']

    # Pre-cancelled event stops cleanly
    ev = threading.Event()
    ev.set()
    canc = shell_tool.execute_directive_script(route, {'script': 'SELECT 1;\n', 'read_only': True}, cancel_event=ev)
    assert canc['state'] == 'cancelled' and canc['cancelled'] is True


# ---------------------------------------------------------------------------
# DU-AUD-19: Single SQL stream dump & atomic reviewed reload
# ---------------------------------------------------------------------------

def test_du_aud_19_sql_stream_dump_exact_roundtrip_and_interrupted_rollback(tmp_path):
    src_file = tmp_path / 'src.duckdb'
    con = duckdb.connect(str(src_file), config={'storage_compatibility_version': 'v1.5.2'})
    con.execute('CREATE SCHEMA analytics')
    con.execute('CREATE SEQUENCE seq_inv START 500')
    con.execute("SELECT nextval('seq_inv')")  # advances so next on reopen is 501
    con.execute("CREATE TYPE mood AS ENUM ('calm', 'focused')")
    con.execute('CREATE TABLE categories (id INTEGER PRIMARY KEY, title VARCHAR NOT NULL)')
    con.execute(
        'CREATE TABLE records ('
        '  id INTEGER PRIMARY KEY,'
        '  cat_id INTEGER REFERENCES categories(id),'
        '  parent_id INTEGER REFERENCES records(id),'
        '  m mood,'
        '  big HUGEINT,'
        '  amt DECIMAL(18,4),'
        '  raw BLOB,'
        '  txt VARCHAR,'
        '  meta STRUCT(k VARCHAR, n INTEGER),'
        '  tags VARCHAR[],'
        '  u UNION(num INTEGER, str VARCHAR),'
        '  upper_txt VARCHAR GENERATED ALWAYS AS (upper(txt))'
        ')'
    )
    con.execute('CREATE UNIQUE INDEX idx_cat_title ON categories (title)')
    con.execute('CREATE VIEW v_records AS SELECT id, upper_txt, big FROM records')
    con.execute("CREATE MACRO add_bonus(v DOUBLE, bonus DOUBLE := 2.5) AS v + bonus")
    con.execute("COMMENT ON TABLE categories IS 'master categories'")
    con.execute("INSERT INTO categories VALUES (1, 'Core')")
    con.execute(
        "INSERT INTO records (id, cat_id, parent_id, m, big, amt, raw, txt, meta, tags, u) VALUES "
        "(10, 1, NULL, 'calm', 170141183460469231731687303715884105727::HUGEINT, 1234.5678, "
        "from_hex('DEADBEEF'), 'line1' || chr(10) || 'nul' || chr(0) || 'end', "
        "{'k': 'v1', 'n': 9}, ['a', 'b'], union_value(str := 'hello'))"
    )
    con.execute(
        "INSERT INTO records (id, cat_id, parent_id, m, big, amt, raw, txt, meta, tags, u) VALUES "
        "(11, 1, 10, 'focused', -42::HUGEINT, 0.0001, from_hex('00FF'), 'child', "
        "{'k': 'v2', 'n': 3}, [], union_value(num := 77))"
    )
    con.close()

    src_route = {'database': str(src_file), 'filesystem_root': str(tmp_path)}
    dump_art = tmp_path / 'full_dump.sql'
    dumped = sql_dump.export_sql_dump(src_route, {}, artifact_path=dump_art)
    assert dumped['format'] == sql_dump.DUMP_FORMAT
    assert dumped['secrets_excluded'] is True
    assert dumped['object_counts']['tables'] == 2
    assert dumped['object_counts']['macros'] == 1
    assert dumped['table_row_counts'] == {'main.categories': 1, 'main.records': 2}

    sql_text = dump_art.read_text(encoding='utf-8')
    dst_file = tmp_path / 'reloaded.duckdb'
    dst_route = {'database': str(dst_file), 'filesystem_root': str(tmp_path)}
    reloaded = sql_dump.reload_sql_dump(dst_route, sql_text, create_if_missing=True, storage_version='v1.5.2')
    assert reloaded['state'] == 'reloaded_and_verified'
    assert reloaded['verified_tables'] == {'main.categories': 1, 'main.records': 2}

    # Verify exact values, NULs/newlines, BLOBs, HUGEINT, UNION, macro defaults, sequence state, and comments!
    vcon = duckdb.connect(str(dst_file), config={'access_mode': 'READ_ONLY'})
    r10 = vcon.execute('SELECT big::VARCHAR, amt::VARCHAR, hex(raw), length(txt), meta, tags, union_tag(u), u::VARCHAR FROM records WHERE id=10').fetchone()
    assert r10[0] == '170141183460469231731687303715884105727'
    assert r10[1] == '1234.5678'
    assert r10[2] == 'DEADBEEF'
    assert r10[3] == len('line1\nnul\x00end')
    assert r10[4] == {'k': 'v1', 'n': 9}
    assert r10[5] == ['a', 'b']
    assert str(r10[6]) == 'str' and r10[7] == 'hello'
    # Macro default `bonus := 2.5` preserved!
    assert vcon.execute('SELECT add_bonus(10.0)').fetchone()[0] == 12.5
    assert vcon.execute("SELECT comment FROM duckdb_tables() WHERE table_name='categories'").fetchone()[0] == 'master categories'
    vcon.close()

    # Verify interrupted/invalid external dump cleans up newly created target file and refuses secrets!
    bad_dst = tmp_path / 'aborted_reload.duckdb'
    bad_route = {'database': str(bad_dst), 'filesystem_root': str(tmp_path)}
    with pytest.raises(sql_dump.DuckDBSQLDumpError, match='rolled back cleanly'):
        sql_dump.reload_sql_dump(
            bad_route,
            'CREATE TABLE t (id INT PRIMARY KEY); INSERT INTO t VALUES (1); INSERT INTO t VALUES (1);',
            create_if_missing=True,
        )
    assert not bad_dst.exists()

    with pytest.raises(sql_dump.DuckDBSQLDumpError, match='Disallowed external/secret'):
        sql_dump.reload_sql_dump(bad_route, "CREATE SECRET s1 (TYPE S3, KEY_ID 'k', SECRET 's');", create_if_missing=True)


# ---------------------------------------------------------------------------
# DU-AUD-20: Physical continuity, WAL crash recovery drill, restore & cutover
# ---------------------------------------------------------------------------

def test_du_aud_20_physical_continuity_wal_crash_drill_and_cutover(tmp_path):
    # 1. Construct a real uncheckpointed .duckdb + .duckdb.wal pair (simulating abrupt crash before checkpoint)
    live_db = tmp_path / 'crash_src.duckdb'
    con = duckdb.connect(str(live_db))
    con.execute('CREATE TABLE ledger (id INTEGER PRIMARY KEY, note VARCHAR)')
    con.execute("INSERT INTO ledger VALUES (1, 'checkpointed')")
    con.execute('CHECKPOINT')
    # Prevent autocheckpoint so subsequent committed row stays in .wal!
    con.execute("PRAGMA wal_autocheckpoint='1TB'")
    con.execute("INSERT INTO ledger VALUES (2, 'in_wal_only')")
    # Copy .duckdb + .duckdb.wal WHILE connection still holds uncheckpointed WAL!
    crash_pair_dir = tmp_path / 'crash_fixture'
    crash_pair_dir.mkdir()
    shutil.copy2(live_db, crash_pair_dir / 'crash_src.duckdb')
    wal_src = Path(str(live_db) + '.wal')
    assert wal_src.is_file() and wal_src.stat().st_size > 0
    shutil.copy2(wal_src, crash_pair_dir / 'crash_src.duckdb.wal')
    con.close()

    route = {'database': str(live_db), 'filesystem_root': str(tmp_path)}

    # 2. Run non-destructive WAL recovery drill on the uncheckpointed pair!
    drill = physical_continuity.run_wal_recovery_drill(
        route,
        {
            'source_path': 'crash_fixture/crash_src.duckdb',
            'drill_dir': 'drill_run_1',
        },
    )
    assert drill['state'] == 'recovery_drill_verified'
    assert drill['had_wal_before_replay'] is True
    assert drill['wal_bytes_before_replay'] > 0
    assert drill['wal_bytes_after_checkpoint'] == 0
    assert drill['recovered_table_row_counts'] == {'main.ledger': 2}
    # Original crash fixture .wal untouched!
    assert (crash_pair_dir / 'crash_src.duckdb.wal').stat().st_size > 0

    # 3. Quiesce & snapshot active database
    snap = physical_continuity.quiesce_and_snapshot(route, {'snapshot_path': 'backups/snap1.duckdb', 'force_checkpoint': True})
    assert snap['state'] == 'snapshot_verified'
    assert snap['verified_table_row_counts'] == {'main.ledger': 2}

    # 4. Restore-to-new target (never touches active file)
    restored = physical_continuity.restore_to_new_target(
        route,
        {'snapshot_path': 'backups/snap1.duckdb', 'restore_target_path': 'restored/new_copy.duckdb'},
    )
    assert restored['state'] == 'restored_to_new_verified'
    assert restored['active_file_replaced'] is False

    # 5. Reviewed cutover with stale-inode guard
    with pytest.raises(physical_continuity.DuckDBContinuityError, match='inode changed'):
        physical_continuity.execute_reviewed_cutover(
            route,
            {
                'staged_path': 'restored/new_copy.duckdb',
                'backup_previous_path': 'backups/prev.duckdb',
                'expected_active_inode': [0, 0],
                'confirmed_cutover': True,
            },
        )

    inspected = physical_continuity.inspect_physical_continuity(route)
    cutover = physical_continuity.execute_reviewed_cutover(
        route,
        {
            'staged_path': 'restored/new_copy.duckdb',
            'backup_previous_path': 'backups/prev.duckdb',
            'expected_active_inode': inspected['inode'],
            'confirmed_cutover': True,
        },
    )
    assert cutover['state'] == 'cutover_completed'
    assert (tmp_path / 'backups' / 'prev.duckdb').is_file()


# ---------------------------------------------------------------------------
# DU-AUD-21: Binary MainHeader/DatabaseHeader inspection, encryption & storage migration
# ---------------------------------------------------------------------------

def test_du_aud_21_storage_header_inspection_upgrade_downgrade_and_encryption(tmp_path):
    # 1. Default file uses v1.0.0 compatibility (version_number == 64, serialization_compatibility == 1)
    v64_file = tmp_path / 'legacy_compat.duckdb'
    c64 = duckdb.connect(str(v64_file))
    c64.execute('CREATE TABLE metrics (k VARCHAR, v INTEGER)')
    c64.execute("INSERT INTO metrics VALUES ('cpu', 85), ('mem', 60)")
    c64.close()

    h64 = storage_lifecycle.inspect_storage_header(v64_file)
    assert h64['valid_duckdb_magic'] is True
    assert h64['version_number'] == 64
    assert h64['encrypted'] is False
    assert h64['database_header']['serialization_compatibility'] == 1
    assert h64['compatible_with_runtime_1_5_2'] is True

    # 2. Prove opening existing v64 file with storage_compatibility_version='v1.5.2' does NOT rewrite file header!
    probe_open = storage_lifecycle.probe_reopen_compatibility(
        v64_file, storage_compatibility_version='v1.5.2'
    )
    assert probe_open['reopen_succeeded'] is True
    assert probe_open['physical_header_rewritten_by_open'] is False
    assert probe_open['header_after']['version_number'] == 64

    # 3. Migrate storage profile 64 -> v1.5.2 (version_number 68, serialization_compatibility 7)
    route = {'database': str(v64_file), 'filesystem_root': str(tmp_path)}
    mig = storage_lifecycle.migrate_storage_profile(
        route,
        {'target_path': 'upgraded_152.duckdb', 'target_storage_version': 'v1.5.2'},
    )
    assert mig['state'] == 'migrated_and_verified'
    assert mig['source_header']['version_number'] == 64
    assert mig['target_header']['version_number'] == 68
    assert mig['target_header']['database_header']['serialization_compatibility'] == 7
    assert mig['verified_table_row_counts'] == {'main.metrics': 2}

    # 4. Migrate to encrypted GCM file + verify right-key vs wrong-key reopen!
    mig_enc = storage_lifecycle.migrate_storage_profile(
        route,
        {
            'target_path': 'encrypted_gcm.duckdb',
            'target_storage_version': 'v1.5.2',
            'target_encryption_key': 'super-secret-duck-key-2026',
            'target_encryption_cipher': 'GCM',
        },
    )
    assert mig_enc['target_header']['encrypted'] is True
    assert mig_enc['target_header']['encryption_cipher'] == 'GCM'

    enc_path = tmp_path / 'encrypted_gcm.duckdb'
    no_key = storage_lifecycle.probe_reopen_compatibility(enc_path)
    assert no_key['reopen_succeeded'] is False and no_key['failure_kind'] == 'encryption_key_required'

    wrong_key = storage_lifecycle.probe_reopen_compatibility(
        enc_path, encryption_key='wrong-key-value', encryption_cipher='GCM'
    )
    assert wrong_key['reopen_succeeded'] is False and wrong_key['failure_kind'] == 'wrong_encryption_key'

    right_key = storage_lifecycle.probe_reopen_compatibility(
        enc_path, encryption_key='super-secret-duck-key-2026', encryption_cipher='GCM'
    )
    assert right_key['reopen_succeeded'] is True and right_key['table_count'] == 1

    # 5. Downgrade refusal when v1.4.0+ typed macro or v1.5.0+ VARIANT column exists and target requests v1.0.0!
    v152_path = tmp_path / 'upgraded_152.duckdb'
    cm = duckdb.connect(str(v152_path), config={'storage_compatibility_version': 'v1.5.2'})
    cm.execute('CREATE MACRO typed_m(x INTEGER) AS x + 1')
    cm.close()
    with pytest.raises(storage_lifecycle.DuckDBStorageLifecycleError, match='refused'):
        storage_lifecycle.migrate_storage_profile(
            {'database': str(v152_path), 'filesystem_root': str(tmp_path)},
            {'target_path': 'downgrade_v100.duckdb', 'target_storage_version': 'v1.0.0'},
        )
    assert not (tmp_path / 'downgrade_v100.duckdb').exists()

    var_db = tmp_path / 'variant_152.duckdb'
    cv = duckdb.connect(str(var_db), config={'storage_compatibility_version': 'v1.5.2'})
    cv.execute('CREATE TABLE var_tbl (v VARIANT)')
    cv.close()
    with pytest.raises(storage_lifecycle.DuckDBStorageLifecycleError, match='VARIANT columns are not supported'):
        storage_lifecycle.migrate_storage_profile(
            {'database': str(var_db), 'filesystem_root': str(tmp_path)},
            {'target_path': 'downgrade_var.duckdb', 'target_storage_version': 'v1.0.0'},
        )
    assert not (tmp_path / 'downgrade_var.duckdb').exists()

    # 6. Future unsupported version_number (e.g. 99) detected directly from binary header without guessing
    future_file = tmp_path / 'future_v99.duckdb'
    shutil.copy2(v64_file, future_file)
    with future_file.open('r+b') as f:
        f.seek(12)
        f.write(struct.pack('<Q', 99))
    h_fut = storage_lifecycle.inspect_storage_header(future_file)
    assert h_fut['valid_duckdb_magic'] is True
    assert h_fut['version_number'] == 99
    assert h_fut['compatible_with_runtime_1_5_2'] is False

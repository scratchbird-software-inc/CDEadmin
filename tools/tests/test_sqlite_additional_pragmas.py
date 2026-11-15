"""Native behavioural acceptance for five further audited SQLite flags."""
import sqlite3
from test_sqlite_connection_pragmas import native, set_flag, run  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.provider import _create_client
from types import SimpleNamespace
import pytest


def test_automatic_index_changes_native_join_plan_without_changing_results(native):
    source=native[2]
    source.executescript('CREATE TABLE outer_rows(value); CREATE TABLE inner_rows(value);')
    source.executemany('INSERT INTO outer_rows VALUES(?)',[(i,)for i in range(80)])
    source.executemany('INSERT INTO inner_rows VALUES(?)',[(i,)for i in range(80)])
    source.commit()
    query='SELECT count(*) FROM outer_rows JOIN inner_rows USING(value)'
    set_flag(native,'automatic_index',False)
    off=[row[3]for row in source.execute('EXPLAIN QUERY PLAN '+query)]
    assert not any('AUTOMATIC' in row for row in off)
    assert source.execute(query).fetchone()==(80,)
    set_flag(native,'automatic_index',True)
    on=[row[3]for row in source.execute('EXPLAIN QUERY PLAN '+query)]
    assert any('AUTOMATIC' in row for row in on)
    assert source.execute(query).fetchone()==(80,)


def test_ignore_check_constraints_native_acceptance_and_no_retroactive_cleanup(native):
    source=native[2]
    source.execute('CREATE TABLE guarded(value INTEGER CHECK(value>0))');source.commit()
    set_flag(native,'ignore_check_constraints',False)
    with pytest.raises(sqlite3.IntegrityError):source.execute('INSERT INTO guarded VALUES(-1)')
    source.rollback()
    set_flag(native,'ignore_check_constraints',True)
    source.execute('INSERT INTO guarded VALUES(-1)')
    assert source.execute('SELECT * FROM guarded').fetchall()==[(-1,)]
    set_flag(native,'ignore_check_constraints',False)
    assert source.execute('SELECT * FROM guarded').fetchall()==[(-1,)]
    with pytest.raises(sqlite3.IntegrityError):source.execute('INSERT INTO guarded VALUES(-2)')
    assert source.in_transaction
    source.rollback()


def test_trusted_schema_blocks_noninnocuous_schema_function_but_not_direct_invocation(native):
    source=native[2]
    source.create_function('host_fn',1,lambda value:value+1,deterministic=True)
    source.execute('CREATE VIEW application_view AS SELECT host_fn(1) AS result')
    set_flag(native,'trusted_schema',True)
    assert source.execute('SELECT * FROM application_view /* trusted */').fetchone()==(2,)
    set_flag(native,'trusted_schema',False)
    with pytest.raises(sqlite3.OperationalError,match='unsafe'):
        source.execute('SELECT * FROM application_view /* untrusted */').fetchall()
    assert source.execute('SELECT host_fn(1)').fetchone()==(2,)
    set_flag(native,'trusted_schema',True)
    assert source.execute('SELECT * FROM application_view /* restored */').fetchone()==(2,)


def test_legacy_alter_table_native_view_rebinding_and_explicit_repair(native):
    source=native[2]
    source.executescript('CREATE TABLE modern(value); INSERT INTO modern VALUES(7); '
        'CREATE VIEW modern_view AS SELECT * FROM modern; '
        'CREATE TABLE legacy(value); INSERT INTO legacy VALUES(9); '
        'CREATE VIEW legacy_view AS SELECT * FROM legacy;')
    set_flag(native,'legacy_alter_table',False)
    source.execute('ALTER TABLE modern RENAME TO modern_renamed')
    assert source.execute('SELECT * FROM modern_view').fetchall()==[(7,)]
    assert 'modern_renamed' in source.execute("SELECT sql FROM sqlite_schema WHERE name='modern_view'").fetchone()[0]
    set_flag(native,'legacy_alter_table',True)
    source.execute('ALTER TABLE legacy RENAME TO legacy_renamed')
    sql=source.execute("SELECT sql FROM sqlite_schema WHERE name='legacy_view'").fetchone()[0]
    assert 'legacy_renamed' not in sql
    with pytest.raises(sqlite3.OperationalError):source.execute('SELECT * FROM legacy_view').fetchall()
    set_flag(native,'legacy_alter_table',False)
    with pytest.raises(sqlite3.OperationalError):source.execute('SELECT * FROM legacy_view').fetchall()
    # Native legacy mode permits renaming back without trying to bind the
    # deliberately dangling view. The flag alone never repairs that view.
    set_flag(native,'legacy_alter_table',True)
    source.execute('ALTER TABLE legacy_renamed RENAME TO legacy')
    assert source.execute('SELECT * FROM legacy_view').fetchall()==[(9,)]


def test_cell_size_check_native_valid_and_corrupt_leaf_reads_preserve_original(native,tmp_path):
    source=native[2]
    source.executescript("CREATE TABLE checked(id INTEGER PRIMARY KEY,payload TEXT); INSERT INTO checked VALUES(1,'kept');")
    set_flag(native,'cell_size_check',True)
    assert source.execute('SELECT * FROM checked').fetchall()==[(1,'kept')]
    size=source.execute('PRAGMA page_size').fetchone()[0]
    root=source.execute("SELECT rootpage FROM sqlite_schema WHERE name='checked'").fetchone()[0]
    original=native[0].read_bytes();damaged=bytearray(original);offset=(root-1)*size
    # Official SQLite file format: table leaf 0x0d, eight-byte header,
    # followed by the two-byte cell-pointer array. Corrupt an owned COPY only.
    assert root>1 and damaged[offset]==0x0d
    assert int.from_bytes(damaged[offset+3:offset+5],'big')==1
    damaged[offset+8:offset+10]=bytes(2)
    target=tmp_path/'damaged-copy.db';target.write_bytes(damaged)
    client=_create_client()
    try:
        handle=client.open_session({'route':{'database':str(target),'filesystem_root':str(tmp_path)}})
        provider=SimpleNamespace(client=client,_require=lambda *_:None,_editor_session=lambda request:handle)
        selected=(target,client,handle,provider)
        set_flag(selected,'cell_size_check',True)
        with pytest.raises(sqlite3.DatabaseError) as error:handle.execute('SELECT * FROM checked').fetchall()
        assert error.value.sqlite_errorcode & 255 == sqlite3.SQLITE_CORRUPT
    finally:client.close()
    assert native[0].read_bytes()==original
    assert source.execute('SELECT * FROM checked').fetchall()==[(1,'kept')]

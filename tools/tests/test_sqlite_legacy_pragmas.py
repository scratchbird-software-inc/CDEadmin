"""Legacy scalar flags and native deferred-FK transaction lifetime."""
import sqlite3
import pytest
from test_sqlite_connection_pragmas import native,set_flag,run  # noqa: F401


def test_native_column_naming_policies_change_wildcard_projection_names(native):
    source=native[2];source.executescript('CREATE TABLE a(value);CREATE TABLE b(value);INSERT INTO a VALUES(1);INSERT INTO b VALUES(2);')
    set_flag(native,'short_column_names',False);set_flag(native,'full_column_names',True)
    cursor=source.execute('SELECT * FROM a CROSS JOIN b')
    assert [column[0]for column in cursor.description]==['a.value','b.value']
    assert cursor.fetchall()==[(1,2)]
    set_flag(native,'full_column_names',False);set_flag(native,'short_column_names',True)
    cursor=source.execute('SELECT * FROM a CROSS JOIN b')
    assert [column[0]for column in cursor.description]==['value','value']
    assert cursor.fetchall()==[(1,2)]


def test_native_count_changes_returns_native_affected_row_set(native):
    source=native[2];source.execute('CREATE TABLE counted(value)')
    set_flag(native,'count_changes',True)
    assert source.execute('INSERT INTO counted VALUES(1),(2)').fetchall()==[(2,)]
    set_flag(native,'count_changes',False)
    assert source.execute('UPDATE counted SET value=value+1').description is None
    assert source.execute('SELECT * FROM counted ORDER BY value').fetchall()==[(2,),(3,)]


def test_native_deferred_foreign_keys_failed_commit_and_reset_lifetime(native):
    source=native[2];source.executescript('CREATE TABLE parent(id PRIMARY KEY);CREATE TABLE child(id REFERENCES parent(id));')
    set_flag(native,'foreign_keys',True);set_flag(native,'defer_foreign_keys',True)
    source.execute('INSERT INTO child VALUES(7)')
    with pytest.raises(sqlite3.IntegrityError):source.commit()
    assert source.in_transaction and run(native,'inspect',pragma='defer_foreign_keys')['effective_value'] is True
    source.rollback()
    assert run(native,'inspect',pragma='defer_foreign_keys')['effective_value'] is False
    set_flag(native,'defer_foreign_keys',True)
    source.execute('INSERT INTO parent VALUES(8)');source.execute('INSERT INTO child VALUES(8)');source.commit()
    assert run(native,'inspect',pragma='defer_foreign_keys')['effective_value'] is False
    assert source.execute('SELECT * FROM child').fetchall()==[(8,)]

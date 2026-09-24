"""Private, consistent configuration snapshots for Firebird live UI gates."""

import sqlite3
import stat
from contextlib import closing

import pytest

from tools.cdeadmin_firebird_ui_completed_orchestrator import _snapshot_config


@pytest.mark.parametrize('journal', ['delete', 'wal'])
def test_snapshot_includes_commits_but_not_pending_writes(tmp_path, journal):
    source = tmp_path / 'source ? # config.db'
    target = tmp_path / 'snapshot.db'
    with closing(sqlite3.connect(source)) as writer:
        writer.execute(f'PRAGMA journal_mode={journal}')
        writer.execute('PRAGMA wal_autocheckpoint=0')
        writer.execute('CREATE TABLE example (value TEXT)')
        writer.execute("INSERT INTO example VALUES ('committed')")
        writer.commit()
        writer.execute("INSERT INTO example VALUES ('pending')")
        before = source.read_bytes()
        _snapshot_config(source, target)
        assert source.read_bytes() == before
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
        with closing(sqlite3.connect(target)) as snapshot:
            assert snapshot.execute('SELECT * FROM example').fetchall() == [
                ('committed',)]
            assert snapshot.execute('PRAGMA integrity_check').fetchone() == (
                'ok',)
            snapshot.execute("UPDATE example SET value='isolated'")
            snapshot.commit()
        writer.rollback()
        assert writer.execute('SELECT * FROM example').fetchall() == [
            ('committed',)]


def test_snapshot_does_not_create_missing_source(tmp_path):
    source, target = tmp_path / 'missing.db', tmp_path / 'snapshot.db'
    with pytest.raises(sqlite3.OperationalError):
        _snapshot_config(source, target)
    assert not source.exists()
    assert not target.exists()


def test_snapshot_does_not_overwrite_existing_destination(tmp_path):
    source, target = tmp_path / 'source.db', tmp_path / 'existing.db'
    target.write_bytes(b'preserve existing file')
    with pytest.raises(FileExistsError):
        _snapshot_config(source, target)
    assert target.read_bytes() == b'preserve existing file'


def test_snapshot_removes_invalid_partial_copy(tmp_path):
    source, target = tmp_path / 'source.db', tmp_path / 'snapshot.db'
    source.write_bytes(b'not a SQLite database')
    with pytest.raises(sqlite3.DatabaseError):
        _snapshot_config(source, target)
    assert not target.exists()
    assert source.read_bytes() == b'not a SQLite database'

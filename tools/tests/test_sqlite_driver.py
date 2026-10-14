"""SQLite native storage, ownership, interruption and artifact regressions."""
import sqlite3
import os
from contextlib import closing
import threading
import time
from unittest.mock import Mock

import pytest

# Reuse only the established package bootstrap, not a fake SQLite driver.
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.sqlite.provider import _create_client
from pgadmin.cdeadmin.providers.sqlite.backup import database_operation
from pgadmin.cdeadmin.providers.sqlite.values import parameters
from pgadmin.cdeadmin.providers.embedded_route import sqlite_arguments


@pytest.fixture
def client():
    value = _create_client()
    yield value
    value.close()


def open_database(client, tmp_path, **options):
    route = dict(database=str(tmp_path / 'active.sqlite'),
                 filesystem_root=str(tmp_path), **options)
    return client.open_session({'route': route}), route


def execute(client, handle, source, bindings=None):
    token = client.execute(handle, {'source': source, 'parameters': bindings})
    deadline = time.monotonic() + 5
    pages = []
    while time.monotonic() < deadline:
        result = client.describe_result(token)
        pages.append(result)
        if result['complete']:
            return pages
    raise AssertionError('SQLite execution did not terminate')


def rows(pages):
    assert not pages[-1]['payload'].get('error'), pages[-1]
    return [row for page in pages for row in page['payload']['rows']]


def test_exact_storage_and_bindings(client, tmp_path):
    handle, _ = open_database(client, tmp_path)
    pages = execute(
        client, handle, 'SELECT :i AS same, :b AS same, :t, NULL, 1.25', {
            'i': {
                'encoding': 'integer', 'data': '9223372036854775807'}, 'b': {
                'encoding': 'base64', 'data': 'AP8='}, 't': 'Grüße 🌲'})
    assert rows(pages) == [['9223372036854775807',
                            {'encoding': 'base64',
                             'data': 'AP8=',
                             'byte_length': 2},
                            'Grüße 🌲',
                            None,
                            '1.25']]
    columns = pages[0]['schema']['columns']
    assert columns[0]['name'] == columns[1]['name'] == 'same'
    assert columns[0]['key'] != columns[1]['key']
    assert rows(execute(client, handle, 'SELECT ?', [42])) == [[42]]


def test_native_statement_metrics_report_measured_scope(client, tmp_path):
    handle, _ = open_database(client, tmp_path)
    pages = execute(client, handle, 'SELECT 1 UNION ALL SELECT 2')
    metrics = pages[-1]['payload']['statement_metrics']
    assert metrics['rows_buffered'] == 2
    assert metrics['prepare_ms'] is None
    assert metrics['plan'] is None
    assert metrics['dispatch_ms'] >= 0
    assert metrics['fetch_ms'] >= 0
    assert metrics['execute_ms'] >= metrics['dispatch_ms']
    assert 'Preparation is not separately measured' in metrics[
        'measurement_scope']


def test_unsafe_integer_rejected_before_any_sql():
    for binding in [[2**60], [{'encoding': 'integer', 'data': str(2**63)}],
                    [{'encoding': 'decimal', 'data': '1.23'}]]:
        with pytest.raises(RuntimeError):
            parameters(binding)


def test_pages_bounded_and_all_rows_preserved(client, tmp_path):
    handle, _ = open_database(client, tmp_path)
    pages = execute(
        client, handle, 'WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL '
        'SELECT x+1 FROM n WHERE x<777) SELECT x FROM n')
    assert len(rows(pages)) == 777
    assert max(len(p['payload']['rows']) for p in pages) <= 256
    assert [p['payload']['row_offset'] for p in pages
            if p['payload']['has_page']] == [0, 256, 512, 768]


def test_real_cancel_and_exclusive_owner(client, tmp_path):
    handle, _ = open_database(client, tmp_path)
    started = threading.Event()

    def signal():
        started.set()
        return 1

    handle.create_function('owned_signal', 0, signal)
    token = client.execute(
        handle, {
            'source': 'WITH RECURSIVE n(x) AS '
            '(VALUES(owned_signal()) UNION ALL SELECT x+1 FROM n '
            'WHERE x<100000000) '
            'SELECT sum(x) FROM n'})
    assert started.wait(2)
    with pytest.raises(RuntimeError, match='execution is active'):
        client.control_transaction(handle, 'commit')
    with pytest.raises(RuntimeError, match='execution is active'):
        client.execute(handle, {'source': 'SELECT 2'})
    assert client.cancel(token)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        page = client.describe_result(token)
        if page['complete']:
            break
    assert page['complete']
    code = page['payload']['error']['sqlite_errorcode']
    assert code == sqlite3.SQLITE_INTERRUPT
    assert not page['payload']['session_reuse_blocked']
    assert not client.cancel(token)
    assert rows(execute(client, handle, 'SELECT 3')) == [[3]]


def test_busy_commit_retains_transaction_for_explicit_retry(client, tmp_path):
    handle, route = open_database(client, tmp_path, timeout=.01)
    handle.execute('CREATE TABLE t(id INTEGER)')
    handle.commit()
    reader = sqlite3.connect(route['database'])
    try:
        reader.execute('BEGIN')
        reader.execute('SELECT * FROM t').fetchall()
        rows(execute(client, handle, 'INSERT INTO t VALUES(1)'))
        with pytest.raises(RuntimeError, match='SQLITE_BUSY'):
            client.control_transaction(handle, 'commit')
        assert handle.in_transaction
        assert not client.describe_transaction(handle)['session_reuse_blocked']
        reader.rollback()
        client.control_transaction(handle, 'commit')
        assert reader.execute('SELECT * FROM t').fetchall() == [(1,)]
    finally:
        reader.close()


def test_close_cancels_backpressure_and_rolls_back(client, tmp_path):
    handle, route = open_database(client, tmp_path)
    handle.execute('CREATE TABLE t(id INTEGER)')
    handle.commit()
    handle.execute('INSERT INTO t VALUES(1)')
    token = client.execute(
        handle, {
            'source': 'WITH RECURSIVE n(x) AS '
            '(VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<10000) '
            'SELECT x FROM n'})
    deadline = time.monotonic() + 2
    while token.pages.qsize() < 2 and time.monotonic() < deadline:
        time.sleep(.01)
    receipt = client.close_session(handle)
    assert receipt['connection_released'] and token.finished.is_set()
    with closing(sqlite3.connect(route['database'])) as observer:
        assert observer.execute('SELECT * FROM t').fetchall() == []


def test_read_only_route_and_attachments(client, tmp_path):
    handle, route = open_database(client, tmp_path)
    handle.execute('CREATE TABLE t(id)')
    handle.commit()
    client.close_session(handle)
    attached = tmp_path / 'attached.sqlite'
    with closing(sqlite3.connect(attached)) as c:
        c.execute('CREATE TABLE t(id)')
    read_only = dict(route, read_only=True, attached_databases=[{
        'name': 'archive', 'database': str(attached)}])
    handle = client.open_session({'route': read_only})
    for source in [
        'INSERT INTO t VALUES(1)',
            'INSERT INTO archive.t VALUES(1)']:
        result = execute(client, handle, source)
        code = result[-1]['payload']['error']['sqlite_errorcode']
        assert code == sqlite3.SQLITE_READONLY
    assert sqlite_arguments(read_only)['uri']


def test_backup_restore_special_filename_and_page_size(client, tmp_path):
    handle, route = open_database(client, tmp_path)
    handle.execute('PRAGMA page_size=8192')
    handle.execute('CREATE TABLE t(value)')
    handle.execute('INSERT INTO t VALUES(42)')
    handle.commit()
    target = tmp_path / ('backup #% 漢字.sqlite' if os.name == 'nt'
                         else 'backup ?#% 漢字.sqlite')
    receipt = client.run_database_operation(handle, route, 'backup', {
        'backup_path': str(target)})
    assert receipt['atomic_publication']
    with closing(sqlite3.connect(target)) as copy:
        assert copy.execute('PRAGMA page_size').fetchone() == (8192,)
        assert copy.execute('SELECT * FROM t').fetchall() == [(42,)]
    handle.execute('DELETE FROM t')
    handle.commit()
    client.run_database_operation(handle, route, 'restore', {
        'backup_path': str(target)})
    assert handle.execute('SELECT * FROM t').fetchall() == [(42,)]
    assert not list(tmp_path.glob('.cdeadmin-backup-*'))


def test_failed_backup_keeps_old_artifact_and_removes_staging(tmp_path):
    source = sqlite3.connect(tmp_path / 'source.sqlite')
    source.execute('CREATE TABLE t(id)')
    target = tmp_path / 'backup.sqlite'
    with closing(sqlite3.connect(target)) as destination:
        destination.execute('CREATE TABLE original(id)')
    original = target.read_bytes()
    broken = Mock(in_transaction=False)
    broken.backup.side_effect = OSError('injected I/O failure')
    route = {'database': str(tmp_path / 'source.sqlite'),
             'filesystem_root': str(tmp_path)}
    try:
        with pytest.raises(OSError):
            database_operation(broken, route, 'backup', {
                'backup_path': str(target), 'overwrite': True})
        assert target.read_bytes() == original
        assert not list(tmp_path.glob('.cdeadmin-backup-*'))
    finally:
        source.close()


def test_backup_alias_and_active_transaction_refused(client, tmp_path):
    handle, route = open_database(client, tmp_path)
    handle.execute('CREATE TABLE t(id)')
    alias = tmp_path / 'hardlink.sqlite'
    alias.hardlink_to(route['database'])
    with pytest.raises(RuntimeError, match='must differ'):
        client.run_database_operation(handle, route, 'backup', {
            'backup_path': str(alias), 'overwrite': True})
    handle.execute('BEGIN')
    with pytest.raises(RuntimeError, match='commit or roll back'):
        client.run_database_operation(handle, route, 'backup', {
            'backup_path': str(tmp_path / 'backup.sqlite')})


def test_busy_backup_deadline_preserves_existing_file(client, tmp_path):
    handle, route = open_database(client, tmp_path, timeout=.01)
    handle.execute('CREATE TABLE t(id)')
    handle.commit()
    target = tmp_path / 'saved.sqlite'
    client.run_database_operation(handle, route, 'backup', {
        'backup_path': str(target)})
    previous = target.read_bytes()
    lock = sqlite3.connect(route['database'])
    try:
        lock.execute('BEGIN EXCLUSIVE')
        started = time.monotonic()
        with pytest.raises(RuntimeError, match='TimeoutError'):
            client.run_database_operation(handle, route, 'backup', {
                'backup_path': str(target), 'overwrite': True,
                'backup_timeout': .05})
        assert time.monotonic() - started < 1
        assert previous == target.read_bytes()
    finally:
        lock.rollback()
        lock.close()


def test_wal_backup_and_exclusive_publication(client, tmp_path):
    handle, route = open_database(client, tmp_path)
    assert handle.execute('PRAGMA journal_mode=WAL').fetchone() == ('wal',)
    handle.execute('CREATE TABLE t(id)')
    handle.execute('INSERT INTO t VALUES(42)')
    handle.commit()
    target = tmp_path / 'wal-backup.sqlite'
    client.run_database_operation(handle, route, 'backup', {
        'backup_path': str(target)})
    with closing(sqlite3.connect(target)) as copy:
        assert copy.execute('SELECT * FROM t').fetchall() == [(42,)]
    with pytest.raises(RuntimeError, match='overwrite is disabled'):
        client.run_database_operation(handle, route, 'backup', {
            'backup_path': str(target)})
    other = client.open_session({'route': dict(route, database=str(target))})
    with pytest.raises(RuntimeError, match='destination is attached'):
        client.run_database_operation(handle, route, 'backup', {
            'backup_path': str(target), 'overwrite': True})
    client.close_session(other)


def test_close_failure_keeps_owner_and_rollback_error_still_closes(client):
    native = Mock(in_transaction=True)
    native.rollback.side_effect = OSError
    native.close.side_effect = OSError
    client._connections.append(native)
    with pytest.raises(RuntimeError, match='release failed'):
        client.close_session(native)
    assert native in client._connections
    native.close.side_effect = None
    result = client.close_session(native)
    assert result['outcome_unknown'] and result['connection_released']
    assert native not in client._connections


def test_nonfinite_busy_timeout_and_conflicting_read_modes_refused(tmp_path):
    route = {'database': str(tmp_path / 'test.sqlite'),
             'filesystem_root': str(tmp_path)}
    for timeout in [float('nan'), float('inf'), -1, True]:
        with pytest.raises(RuntimeError):
            sqlite_arguments(dict(route, timeout=timeout))
    with pytest.raises(RuntimeError, match='conflicts'):
        sqlite_arguments(dict(route, read_only=True, uri_mode='rwc'))


def test_invalid_utf8_text_is_preserved(client, tmp_path):
    handle, _ = open_database(client, tmp_path)
    assert rows(execute(client, handle, "SELECT CAST(x'ff00' AS TEXT)")) == [[{
        'encoding': 'base64', 'data': '/wA=', 'byte_length': 2,
        'native_storage_class': 'text'}]]


def test_attachment_names_are_quoted_native_identifiers(client, tmp_path):
    handle, _ = open_database(client, tmp_path, attached_databases=[{
        'name': 'quoted " archive 漢字',
        'database': str(tmp_path / 'archive.sqlite')}])
    assert 'quoted " archive 漢字' in [
        row[1] for row in handle.execute('PRAGMA database_list')]


def test_long_backup_does_not_lock_other_sessions(client, tmp_path):
    from unittest.mock import patch
    handle, route = open_database(client, tmp_path)
    other_route = dict(route, database=str(tmp_path / 'other.sqlite'))
    other = client.open_session({'route': other_route})
    entered, release = threading.Event(), threading.Event()
    failures = []

    def runner(*_args):
        entered.set()
        assert release.wait(2)
        return {'complete': True}

    def backup():
        try:
            client.run_database_operation(handle, route, 'backup', {
                'backup_path': str(tmp_path / 'backup.sqlite')})
        except Exception as exc:
            failures.append(type(exc).__name__)

    base = type(client).__mro__[1]
    with patch.object(base, 'run_database_operation', runner):
        worker = threading.Thread(target=backup)
        worker.start()
        try:
            assert entered.wait(1)
            with pytest.raises(RuntimeError, match='operation is active'):
                client.close_session(handle)
            assert rows(execute(client, other, 'SELECT 7')) == [[7]]
        finally:
            release.set()
            worker.join(3)
    assert not failures


@pytest.mark.skipif(os.name == 'nt', reason='Native Windows filename rules')
def test_exact_filename_whitespace_is_not_redirected(client, tmp_path):
    from pgadmin.cdeadmin.providers.embedded_route import contained_database
    root = tmp_path / 'root with trailing space '
    root.mkdir()
    name = root / 'database.sqlite '
    route = {'database': str(name), 'filesystem_root': str(root)}
    assert contained_database(route) == str(name)
    handle = client.open_session({'route': route})
    rows(execute(client, handle, 'CREATE TABLE t(id)'))
    assert name.is_file()
    assert not (root / 'database.sqlite').exists()


def test_wal_page_size_mismatch_preserves_native_refusal(client, tmp_path):
    source = tmp_path / 'different-page-size.sqlite'
    with closing(sqlite3.connect(source)) as connection:
        connection.execute('PRAGMA page_size=8192')
        connection.execute('CREATE TABLE copied(id)')
    handle, route = open_database(client, tmp_path)
    handle.execute('PRAGMA page_size=4096')
    handle.execute('PRAGMA journal_mode=WAL')
    handle.execute('CREATE TABLE original(id)')
    handle.execute('INSERT INTO original VALUES(42)')
    handle.commit()
    with pytest.raises(RuntimeError, match='SQLITE_READONLY, code=8'):
        client.run_database_operation(handle, route, 'restore', {
            'backup_path': str(source), 'backup_timeout': .1})
    assert handle.execute('PRAGMA page_size').fetchone() == (4096,)
    assert handle.execute('SELECT * FROM original').fetchall() == [(42,)]


def test_deadline_validation_is_owned_by_sqlite():
    from pgadmin.cdeadmin.providers.sqlite.provider import ADMINISTRATION
    validate = ADMINISTRATION._validate_sqlite_database_operation
    draft = {'backup_path': '/owned/backup.sqlite', 'backup_timeout': .5}
    assert validate('backup', draft, {}) == []
    for value in [False, 0, -1, float('inf'), float('nan'), '30']:
        errors = validate('backup', dict(draft, backup_timeout=value), {})
        codes = [error['code'] for error in errors]
        assert 'invalid_sqlite_backup_timeout' in codes

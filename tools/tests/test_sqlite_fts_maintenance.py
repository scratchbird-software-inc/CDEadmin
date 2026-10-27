"""Real FTS index work, native preservation, refusals and cancellation receipts."""
from contextlib import closing
from copy import deepcopy
import sqlite3
import threading
import time
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.sqlite.provider import ADMINISTRATION, _create_client, _resources
from pgadmin.cdeadmin.providers.sqlite.fts_configuration import capture
from pgadmin.cdeadmin.providers.sqlite import fts_maintenance


def fixture(tmp_path, module='fts5', options=''):
    path = tmp_path / 'live.sqlite'
    with closing(sqlite3.connect(path)) as seed:
        seed.execute('CREATE TABLE pending(value)')
        seed.execute('CREATE TABLE owner(id INTEGER PRIMARY KEY,body TEXT)')
        seed.execute('CREATE VIRTUAL TABLE search USING ' + module + '(body' + options + ')')
        for value in range(30):
            seed.execute('INSERT INTO search(rowid,body) VALUES(?,?)', (value + 1, 'native token ' + str(value))); seed.commit()
        if module == 'fts5': seed.execute("INSERT INTO search(search,rank) VALUES('automerge',6)")
        else: seed.execute("INSERT INTO search(search) VALUES('automerge=6')")
        seed.commit()
    client = _create_client()
    route = {'database': str(path), 'filesystem_root': str(tmp_path), 'timeout': .05}
    with closing(sqlite3.connect(path)) as observer:
        resource = next(row for row in _resources(observer, {'route': route}) if row['resource_kind'] == 'fts-table' and row['display_name'] == 'search')
    return path, client, route, resource


def plan(route, resource, operation, **draft):
    return ADMINISTRATION.plan({'resource_kind': 'fts-table', 'operation_id': operation,
        'target_resource': resource, '_provider_route': route, 'draft': {'timeout_seconds': 30, **draft}})


@pytest.mark.parametrize('module', ['fts3', 'fts4', 'fts5'])
@pytest.mark.parametrize('operation', ['fts_optimize', 'fts_rebuild', 'fts_integrity_check', 'fts_merge'])
def test_native_index_maintenance_settings_and_queries(tmp_path, module, operation):
    path, client, route, resource = fixture(tmp_path, module)
    try:
        planned = plan(route, resource, operation)
        result = ADMINISTRATION.apply(client, planned)
        receipt = result['native_fts_maintenance']
        assert result['accepted'] and receipt['native_outcome'] == 'committed', result
        assert receipt['native_integrity_verified'] and dict(receipt['configuration']['commands'])['automerge'] == 6
        assert ADMINISTRATION.inspect_operation(client, planned) == receipt
        with pytest.raises(Exception, match='already been dispatched'):
            ADMINISTRATION.apply(client, planned)
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute("SELECT count(*) FROM search WHERE search MATCH 'native'").fetchone() == (30,)
            assert dict(capture(observer, 'main', 'search', module)['commands'])['automerge'] == 6
    finally: client.close()


@pytest.mark.parametrize('module', ['fts3', 'fts4', 'fts5'])
def test_native_session_flush_and_failed_task_preserve_pending_work(tmp_path, module):
    path, client, route, resource = fixture(tmp_path, module)
    try:
        connection = client._connect({'route': route})
        connection.execute('INSERT INTO pending VALUES(42)'); connection.execute('SAVEPOINT caller')
        connection.execute("INSERT INTO search(rowid,body) VALUES(9007199254740993,'pending native token')")
        callback = Mock(return_value=0); connection.set_progress_handler(callback, 200)
        original_busy = connection.execute('PRAGMA busy_timeout').fetchone()[0]
        authorizer = lambda *_: sqlite3.SQLITE_OK
        connection.set_authorizer(authorizer)
        planned = plan(route, resource, 'fts_flush')
        result = ADMINISTRATION.apply(client, planned, connection=connection)
        assert result['native_fts_maintenance']['native_outcome'] == 'staged', result
        assert connection._cdeadmin_progress_handler == (callback, 200) and connection._cdeadmin_authorizer is authorizer
        assert connection.execute('PRAGMA busy_timeout').fetchone()[0] == original_busy
        connection.execute('ROLLBACK TO caller')
        assert connection.execute('SELECT * FROM pending').fetchall() == [(42,)]
        assert connection.execute("SELECT count(*) FROM search WHERE search MATCH 'native'").fetchone() == (30,)
        connection.rollback()
        assert connection.execute('SELECT * FROM pending').fetchall() == []
        refused = ADMINISTRATION.apply(client, plan(route, resource, 'fts_flush'))
        assert refused['native_fts_maintenance']['native_outcome'] == 'not_dispatched'
    finally: client.close()


@pytest.mark.parametrize('content', ['', 'owner'])
def test_native_fts5_delete_all_preserves_external_content_and_settings(tmp_path, content):
    path, client, route, resource = fixture(tmp_path, options=",content='" + content + "'" + (",content_rowid='id'" if content else ''))
    try:
        with closing(sqlite3.connect(path)) as observer:
            observer.execute("INSERT INTO owner VALUES(1,'native token')"); observer.commit()
        result = ADMINISTRATION.apply(client, plan(route, resource, 'fts_delete_all', confirmation='search'))
        receipt = result['native_fts_maintenance']
        assert receipt['native_outcome'] == 'committed' and receipt['index_terms_verified_empty'], result
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute("SELECT count(*) FROM search WHERE search MATCH 'native'").fetchone() == (0,)
            assert observer.execute('SELECT * FROM owner').fetchall() == [(1, 'native token')]
            assert dict(capture(observer, 'main', 'search', 'fts5')['commands'])['automerge'] == 6
    finally: client.close()


def test_native_fts5_external_rebuild_and_content_comparison(tmp_path):
    path, client, route, resource = fixture(tmp_path, options=",content='owner',content_rowid='id'")
    try:
        with closing(sqlite3.connect(path)) as observer:
            observer.execute("INSERT INTO owner VALUES(9007199254740993,'native 雪')"); observer.commit()
        mismatch = ADMINISTRATION.apply(client, plan(route, resource, 'fts_integrity_check', external_content=True))
        assert mismatch['native_fts_maintenance']['native_outcome'] == 'rolled_back'
        assert mismatch['native_fts_maintenance']['native_error']['name'].startswith('SQLITE_CORRUPT')
        rebuilt = ADMINISTRATION.apply(client, plan(route, resource, 'fts_rebuild'))
        assert rebuilt['native_fts_maintenance']['native_outcome'] == 'committed'
        checked = ADMINISTRATION.apply(client, plan(route, resource, 'fts_integrity_check', external_content=True))
        assert checked['native_fts_maintenance']['native_integrity_verified']
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute("SELECT rowid,body FROM search WHERE search MATCH 'native'").fetchall() == [(9007199254740993, 'native 雪')]
    finally: client.close()


@pytest.mark.parametrize('module,options,operation,draft', [
    ('fts3', '', 'fts_delete_all', {'confirmation': 'search'}),
    ('fts4', '', 'fts_delete_all', {'confirmation': 'search'}),
    ('fts5', '', 'fts_delete_all', {'confirmation': 'search'}),
    ('fts5', ",content=''", 'fts_rebuild', {}),
    ('fts5', '', 'fts_integrity_check', {'external_content': True}),
    ('fts5', '', 'fts_merge', {'pages': True}),
    ('fts4', '', 'fts_merge', {'pages': -1}),
])
def test_native_mode_admission_and_object_operations(tmp_path, module, options, operation, draft):
    _path, client, route, resource = fixture(tmp_path, module, options)
    try:
        with pytest.raises(Exception): plan(route, resource, operation, **draft)
        if operation in {'fts_delete_all', 'fts_rebuild'}:
            assert operation not in resource['native']['administration']['allowed_operations']
    finally: client.close()


def test_real_native_vm_timeout_restores_the_original_progress_policy(tmp_path):
    path, client, route, resource = fixture(tmp_path)
    planned = plan(route, resource, 'fts_rebuild', timeout_seconds=.025)
    reference = planned['provider_payload']['compiled']['sqlite_fts_maintenance']['reference']
    connect = client._connect
    def connected(request):
        connection = connect(request)
        def prior():
            entry = getattr(client, '_cde_fts_maintenance', {}).get(reference)
            if entry and entry['public']['stage'] == 'executing': time.sleep(.005)
            return 0
        connection.set_progress_handler(prior, 1)
        return connection
    client._connect = connected
    try:
        result = ADMINISTRATION.apply(client, planned)['native_fts_maintenance']
        assert result['native_outcome'] == 'rolled_back' and result['timeout_expired'], result
        assert result['native_error']['code'] == sqlite3.SQLITE_INTERRUPT
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute("SELECT count(*) FROM search WHERE search MATCH 'native'").fetchone() == (30,)
    finally: client.close()


def test_busy_retained_connection_admission_cannot_release_another_task(tmp_path):
    _path, client, route, resource = fixture(tmp_path)
    connection = client._connect({'route': route})
    try:
        client._busy.add(id(connection))
        receipt = ADMINISTRATION.apply(client, plan(route, resource, 'fts_optimize'), connection=connection)['native_fts_maintenance']
        assert receipt['native_outcome'] == 'not_dispatched'
        assert id(connection) in client._busy
    finally:
        client._busy.discard(id(connection)); client.close()


@pytest.mark.parametrize('failure', ['stale', 'denied', 'lost_commit', 'postimage', 'busy'])
def test_native_maintenance_failure_and_once_only_outcomes(tmp_path, monkeypatch, failure):
    path, client, route, resource = fixture(tmp_path)
    planned = plan(route, resource, 'fts_rebuild'); connect = client._connect; writer = None
    try:
        if failure == 'stale':
            with closing(sqlite3.connect(path)) as observer:
                observer.execute("INSERT INTO search(search,rank) VALUES('automerge',8)"); observer.commit()
        if failure == 'busy':
            writer = sqlite3.connect(path); writer.execute('INSERT INTO pending VALUES(99)')
        if failure in {'denied', 'lost_commit'}:
            class Injected:
                def __init__(self, connection):
                    self.connection = connection
                    if failure == 'denied': connection.set_authorizer(lambda code, name, *_: sqlite3.SQLITE_DENY if code == sqlite3.SQLITE_INSERT and name == 'search' else sqlite3.SQLITE_OK)
                def __getattr__(self, key): return getattr(self.connection, key)
                def commit(self):
                    self.connection.commit()
                    if failure == 'lost_commit': raise ConnectionError('Actual native commit; reply lost')
            client._connect = lambda request: Injected(connect(request))
            client._require_idle = Mock()
        if failure == 'postimage':
            actual = fts_maintenance.capture; calls = []
            def wrong(*args):
                value = actual(*args); calls.append(True)
                if len(calls) > 1:
                    value = deepcopy(value); value['commands'] = [['automerge', 99]]
                return value
            monkeypatch.setattr(fts_maintenance, 'capture', wrong)
        result = ADMINISTRATION.apply(client, planned)['native_fts_maintenance']
        expected = 'not_dispatched' if failure in {'stale', 'busy'} else 'unknown_outcome' if failure == 'lost_commit' else 'rolled_back'
        assert result['native_outcome'] == expected, result
        if writer:
            assert writer.in_transaction and writer.execute('SELECT * FROM pending').fetchall() == [(99,)]; writer.rollback()
        assert ADMINISTRATION.inspect_operation(client, planned) == result
        assert not ADMINISTRATION.cancel_operation(client, planned)['cancel_requested']
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute("SELECT count(*) FROM search WHERE search MATCH 'native'").fetchone() == (30,)
    finally:
        if writer: writer.close()
        client.close()


def test_native_cancellation_observation_and_rollback(tmp_path):
    path, client, route, resource = fixture(tmp_path)
    planned = plan(route, resource, 'fts_rebuild'); connect = client._connect
    entered = threading.Event(); release = threading.Event(); outcome = []
    def connected(request):
        connection = connect(request)
        def authorizer(code, name, *_):
            if code == sqlite3.SQLITE_INSERT and name == 'search': entered.set(); release.wait(5)
            return sqlite3.SQLITE_OK
        connection.set_authorizer(authorizer)
        return connection
    client._connect = connected
    thread = threading.Thread(target=lambda: outcome.append(ADMINISTRATION.apply(client, planned)))
    try:
        thread.start(); assert entered.wait(5)
        observed = ADMINISTRATION.inspect_operation(client, planned)
        assert observed['stage'] == 'executing'
        assert ADMINISTRATION.cancel_operation(client, planned)['cancel_requested']
        release.set(); thread.join(10); assert not thread.is_alive()
        receipt = outcome[0]['native_fts_maintenance']
        assert receipt['native_outcome'] == 'rolled_back' and receipt['cancellation_requested'], receipt
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute("SELECT count(*) FROM search WHERE search MATCH 'native'").fetchone() == (30,)
    finally:
        release.set(); thread.join(10); client.close()

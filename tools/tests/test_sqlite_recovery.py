"""Owned native recovery, exact storage classes and publication failure fences."""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import time
from unittest.mock import patch
import uuid

import pytest

from pgadmin.cdeadmin.providers.sqlite.recovery import options, program, source_state, digest_file, RecoveryError
from pgadmin.cdeadmin.workspace.sqlite_recovery_jobs import SQLiteRecoveryJobs, ACTIVE


@pytest.fixture
def native(tmp_path):
    library = os.environ.get('CDEADMIN_SQLITE_RECOVERY_LIBRARY')
    if not library: pytest.skip('Set CDEADMIN_SQLITE_RECOVERY_LIBRARY to the qualified native build')
    assert sqlite3.sqlite_version == '3.53.0'
    runtime = program(library, tmp_path)
    source, target = tmp_path / 'source.sqlite', tmp_path / 'recovered.sqlite'
    jobs = SQLiteRecoveryJobs(tmp_path / 'receipts.json', tmp_path / 'jobs')
    fixture = {'source': source, 'target': target, 'jobs': jobs, 'runtime': runtime,
        'endpoint': str(uuid.uuid4()), 'target_id': str(uuid.uuid4()),
        'route': {'database': str(source), 'filesystem_root': str(tmp_path)}}
    yield fixture
    jobs.close()


def review(fixture):
    selected = options({'output_path': str(fixture['target']), 'source_isolated': True})
    receipt = fixture['jobs'].review(1, fixture['endpoint'], fixture['target_id'], fixture['route'],
        source_state(fixture['route'], selected), fixture['runtime'], selected, 'qualified-fixture')
    return receipt, {'job_id': receipt['job_id'], 'review_digest': receipt['review_digest'], 'confirmed': True}


def start(fixture, request):
    return fixture['jobs'].start(request, 1, fixture['endpoint'], fixture['target_id'], 'qualified-fixture')


def finish(fixture, receipt):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        current = fixture['jobs'].get(receipt['job_id'], 1, fixture['endpoint'], fixture['target_id'])
        if current['state'] not in ACTIVE: return current
        time.sleep(.05)
    raise AssertionError('Native recovery did not reach a terminal receipt')


def create(path, *, wal=False):
    connection = sqlite3.connect(path)
    if wal: assert connection.execute('PRAGMA journal_mode=WAL').fetchone() == ('wal',)
    connection.executescript('''
        CREATE TABLE effects(n INTEGER); INSERT INTO effects VALUES(0);
        CREATE TABLE data(id INTEGER PRIMARY KEY,v TEXT,p BLOB);
        CREATE TRIGGER count_insert AFTER INSERT ON data BEGIN UPDATE effects SET n=n+1; END;
        CREATE VIEW projected AS SELECT id,hex(v) AS value_bytes FROM data;
        CREATE TABLE derived(id INTEGER PRIMARY KEY,a TEXT,b TEXT GENERATED ALWAYS AS(upper(a)) STORED) STRICT;
        CREATE TABLE composite(a TEXT,b BLOB,c ANY,PRIMARY KEY(a,b)) STRICT,WITHOUT ROWID;
        CREATE TABLE child(id INTEGER PRIMARY KEY,parent_id INTEGER REFERENCES data(id));
        CREATE VIRTUAL TABLE search USING fts5(body);
    ''')
    connection.executemany('INSERT INTO data VALUES(?,?,?)', [
        (9007199254740993, 'é 雪\x00end', b'\x00\xff'),
        (-9223372036854775808, '😀' * 1024, bytes(range(256)) * 32),
        (9223372036854775807, '', b''), (4, None, None)])
    connection.execute("INSERT INTO data VALUES(5,CAST(x'ff00aa' AS TEXT),x'00')")
    connection.execute("INSERT INTO derived(id,a) VALUES(1,'native')")
    connection.execute('INSERT INTO composite VALUES(?,?,?)', ("key'雪", b'\x00\xff', .125))
    connection.execute('INSERT INTO child VALUES(1,9007199254740993)')
    connection.execute("INSERT INTO search(rowid,body) VALUES(9007199254740993,'native term')")
    connection.commit()
    return connection


def observations(path):
    with closing(sqlite3.connect(Path(path).as_uri() + '?mode=ro', uri=True)) as connection:
        return {
            'data': connection.execute('SELECT id,typeof(v),hex(CAST(v AS BLOB)),typeof(p),hex(p) FROM data ORDER BY id').fetchall(),
            'derived': connection.execute('SELECT * FROM derived').fetchall(),
            'composite': connection.execute('SELECT * FROM composite').fetchall(),
            'child': connection.execute('SELECT * FROM child').fetchall(),
            'effects': connection.execute('SELECT * FROM effects').fetchall(),
            'view': connection.execute('SELECT * FROM projected ORDER BY id').fetchall(),
            'fts': connection.execute("SELECT rowid,body FROM search WHERE search MATCH 'native'").fetchall(),
        }


@pytest.mark.parametrize('wal', [False, True])
def test_native_typed_recovery_preserves_wal_storage_and_trigger_effects(native, wal):
    connection = create(native['source'], wal=wal)
    try:
        before = observations(native['source'])
        receipt, request = review(native)
        source_hashes = {suffix: digest_file(str(native['source']) + suffix) for suffix in receipt['source']['files']}
        start(native, request); current = finish(native, receipt)
        assert current['state'] == 'completed', current
        assert current['result']['integrity_check'] == 'ok'
        assert current['result']['application_data_verified'] is False
        assert observations(native['target']) == before
        assert all(digest_file(str(native['source']) + suffix) == checksum for suffix, checksum in source_hashes.items())
        assert start(native, request)['state'] == 'completed'
        with pytest.raises(RecoveryError): native['jobs'].get(receipt['job_id'], 2, native['endpoint'], native['target_id'])
        with pytest.raises(RecoveryError): native['jobs'].get(receipt['job_id'], 1, native['endpoint'], 'another-file')
        restored = SQLiteRecoveryJobs(native['jobs'].path, native['jobs'].root)
        assert restored.get(receipt['job_id'], 1, native['endpoint'], native['target_id'])['state'] == 'completed'
        reconciled = restored.reconcile(receipt['job_id'], 1, native['endpoint'], native['target_id'])
        assert reconciled['current_artifact']['matches_expected']
        restored.remove_images(receipt['job_id'], 1, native['endpoint'], native['target_id'], receipt['job_id'])
        assert observations(native['target']) == before
        assert native['source'].is_file()
    finally: connection.close()


def test_native_corrupt_page_salvage_retains_independent_healthy_records(native):
    connection = sqlite3.connect(native['source'])
    connection.execute('CREATE TABLE healthy(id INTEGER PRIMARY KEY,v TEXT)')
    connection.execute('INSERT INTO healthy VALUES(9007199254740993,?)', ('é 雪\x00end',))
    connection.execute('CREATE TABLE damaged(id INTEGER PRIMARY KEY,v BLOB)')
    connection.executemany('INSERT INTO damaged(v) VALUES(?)', [(b'corruption fixture' * 50,)] * 100)
    connection.commit()
    page_size = connection.execute('PRAGMA page_size').fetchone()[0]
    page = connection.execute("SELECT pageno FROM dbstat WHERE name='damaged' AND pagetype='leaf' ORDER BY pageno LIMIT 1").fetchone()[0]
    connection.close()
    with native['source'].open('r+b') as stream:
        stream.seek((page - 1) * page_size); stream.write(b'\x00')
    with closing(sqlite3.connect(native['source'])) as observer:
        with pytest.raises(sqlite3.DatabaseError): observer.execute('SELECT * FROM damaged').fetchall()
    before = digest_file(native['source'])
    receipt, request = review(native); start(native, request); current = finish(native, receipt)
    assert current['state'] == 'completed', current
    assert digest_file(native['source']) == before
    with closing(sqlite3.connect(native['target'])) as observer:
        assert observer.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert observer.execute('SELECT * FROM healthy').fetchall() == [(9007199254740993, 'é 雪\x00end')]


@pytest.mark.parametrize('failure', ['source-change', 'output-exists',
    pytest.param('source-denied', marks=pytest.mark.skipif(os.name == 'nt',
        reason='POSIX chmod refusal fixture; native Windows ACL refusal is platform-team qualification'))])
def test_native_file_admission_does_not_overwrite_or_replay(native, failure):
    connection = create(native['source']); connection.close()
    receipt, request = review(native)
    if failure == 'source-change':
        with closing(sqlite3.connect(native['source'])) as observer:
            observer.execute("INSERT INTO data VALUES(7,'external change',x'01')"); observer.commit()
    elif failure == 'output-exists': native['target'].write_bytes(b'owned existing output')
    else: native['source'].chmod(0)
    try:
        start(native, request); current = finish(native, receipt)
        assert current['state'] == 'failed', current
        assert current['output_published'] is False
        assert start(native, request)['state'] == 'failed'
        if failure == 'output-exists': assert native['target'].read_bytes() == b'owned existing output'
        else: assert not native['target'].exists()
    finally: native['source'].chmod(0o600)


@pytest.mark.skipif(os.name == 'nt', reason='Native Windows publication uses rename; platform fault adapter is separate')
def test_native_lost_publication_acknowledgement_is_reconciled_without_replay(native):
    connection = create(native['source']); connection.close(); expected = observations(native['source'])
    receipt, request = review(native)
    link = os.link
    def lost_reply(source, target):
        link(source, target)
        raise ConnectionError('Owned loss after actual native file publication')
    with patch('pgadmin.cdeadmin.workspace.sqlite_recovery_jobs.os.link', side_effect=lost_reply):
        start(native, request); current = finish(native, receipt)
    assert current['state'] == 'unknown_outcome' and current['output_published'] is None, current
    assert observations(native['target']) == expected
    assert start(native, request)['state'] == 'unknown_outcome'
    current = native['jobs'].reconcile(receipt['job_id'], 1, native['endpoint'], native['target_id'])
    assert current['state'] == 'artifact_verified' and current['publication_acknowledgement_unknown']


def test_native_cancellation_prevents_publication(native):
    connection = sqlite3.connect(native['source'])
    connection.execute('CREATE TABLE large(id INTEGER PRIMARY KEY,v BLOB)')
    connection.executemany('INSERT INTO large(v) VALUES(?)', ((b'x' * 2048,) for _index in range(50000)))
    connection.commit(); connection.close()
    original = digest_file(native['source']); receipt, request = review(native)
    start(native, request)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        current = native['jobs'].get(receipt['job_id'], 1, native['endpoint'], native['target_id'])
        if current.get('progress', {}).get('process', {}).get('pid'): break
        assert current['state'] in ACTIVE, current
        time.sleep(.01)
    assert current.get('progress', {}).get('process', {}).get('pid'), current
    native['jobs'].cancel(receipt['job_id'], 1, native['endpoint'], native['target_id'])
    current = finish(native, receipt)
    assert current['state'] == 'cancelled' and current['output_published'] is False, current
    assert digest_file(native['source']) == original and not native['target'].exists()


@pytest.mark.parametrize('attachment', ['literal', 'expression'])
def test_native_corrupt_schema_cannot_attach_or_modify_another_file(native, attachment):
    marker = native['source'].parent / 'owned-marker.sqlite'
    with closing(sqlite3.connect(marker)) as observer:
        observer.execute('CREATE TABLE marker(value TEXT)')
        observer.execute("INSERT INTO marker VALUES('original')"); observer.commit()
    path = "'" + str(marker).replace("'", "''") + "'"
    if attachment == 'expression': path = "substr('x'||" + path + ',2)'
    with closing(sqlite3.connect(native['source'])) as connection:
        connection.execute('CREATE TABLE data(id INTEGER PRIMARY KEY,v TEXT)')
        connection.execute("INSERT INTO data VALUES(1,'native data')")
        original = connection.execute("SELECT sql FROM sqlite_schema WHERE name='data'").fetchone()[0]
        connection.execute('PRAGMA writable_schema=ON')
        connection.execute("UPDATE sqlite_schema SET sql=? WHERE name='data'", (
            original + '; ATTACH ' + path + " AS outside; UPDATE outside.marker SET value='modified';",))
        connection.commit()
    checksum = digest_file(marker)
    receipt, request = review(native); start(native, request); current = finish(native, receipt)
    assert current['state'] == 'failed' and current['output_published'] is False, current
    assert digest_file(marker) == checksum
    with closing(sqlite3.connect(marker)) as observer:
        assert observer.execute('SELECT value FROM marker').fetchone() == ('original',)

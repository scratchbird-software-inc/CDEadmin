#!/usr/bin/env python3
"""Portable SQLite provider qualification in a new, owned fixture directory."""
import argparse
import hashlib
import json
import platform
from pathlib import Path
import shutil
import sqlite3
import os
from contextlib import closing
import sys
import threading
import time
import traceback
import uuid
from types import ModuleType, SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.providers.sqlite.provider import (  # noqa: E402
    PROFILE, create_provider,
)


def run(evidence):
    evidence = Path(evidence).resolve()
    if evidence == ROOT or ROOT in evidence.parents:
        raise ValueError('Evidence must be outside the repository')
    evidence.mkdir(parents=True, exist_ok=False)
    fixture = evidence / 'owned-fixture'
    fixture.mkdir()
    receipt = {
        'complete': False,
        'checks': [],
        'failures': [],
        'platform': platform.platform(),
        'python': platform.python_version(),
        'sqlite': sqlite3.sqlite_version,
        'cleanup_complete': False,
        'scope': 'SQLite native driver, not native platform UX acceptance'}
    package = ROOT / 'web/pgadmin/cdeadmin/providers/sqlite'
    files = list(package.glob('*.py')) + [
        Path(__file__),
        ROOT / 'web/pgadmin/cdeadmin/providers/embedded_route.py']
    receipt['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(
        p.read_bytes()).hexdigest() for p in files}
    context = SimpleNamespace(
        endpoint_id=str(
            uuid.uuid4()),
        session_namespace='owned-sqlite-proof',
        pool_namespace='owned-sqlite-proof',
        cache_namespace='owned-sqlite-proof',
        provider_id=PROFILE.provider_id,
        profile_id=PROFILE.profile_id,
        profile_version=PROFILE.exact_version,
        provider_version='0.1.0')
    provider = None
    route = {'database': str(fixture / 'active.sqlite'),
             'filesystem_root': str(fixture), 'timeout': .05}
    try:
        provider = create_provider(
            context, SimpleNamespace(require=lambda *_: None))
        client = provider.client
        assert sqlite3.sqlite_version == PROFILE.exact_version
        session = provider.open_session({'route': route})
        handle = provider._sessions[session['session_id']].handle
        receipt['source_id'] = handle.execute(
            'SELECT sqlite_source_id()').fetchone()[0]
        receipt['compile_options'] = [
            row[0] for row in handle.execute('PRAGMA compile_options')]
        receipt['checks'].append('exact-provider-runtime-admission')

        def observe(operation):
            deadline = time.monotonic() + 30
            pages = []
            while time.monotonic() < deadline:
                result = provider.describe_result(operation)
                pages.append(result)
                if result['complete']:
                    return pages
            raise AssertionError('SQLite query did not terminate')

        def query(source, parameters=None):
            result = observe(provider.execute(dict(session, source=source,
                                                   parameters=parameters)))
            assert not result[-1]['extensions']['sqlite']['payload'].get(
                'error')
            return [row for page in result for row in page[
                'extensions']['sqlite']['payload']['rows']]

        query('PRAGMA page_size=8192')
        assert query('SELECT :i AS same, :b AS same, :t, 1.25, NULL', {
            'i': {'encoding': 'integer', 'data': '9223372036854775807'},
            'b': {'encoding': 'base64', 'data': 'AP8='}, 't': 'Grüße 🌲'}) == [[
                '9223372036854775807',
                {'encoding': 'base64', 'data': 'AP8=', 'byte_length': 2},
                'Grüße 🌲', '1.25', None]]
        assert query('SELECT ?', [42]) == [[42]]
        receipt['checks'].append('exact-native-values-and-bindings')
        source = ('WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL '
                  'SELECT x+1 FROM n WHERE x<777) SELECT x FROM n')
        pages = observe(provider.execute(dict(session, source=source)))
        payloads = [p['extensions']['sqlite']['payload'] for p in pages]
        assert sum(len(p['rows']) for p in payloads) == 777
        assert max(len(p['rows']) for p in payloads) <= 256
        receipt['checks'].append('bounded-complete-native-fetch')
        query('CREATE TABLE owned(id INTEGER PRIMARY KEY, value TEXT)')
        query('INSERT INTO owned VALUES(1, ?)', ['uncommitted'])
        with closing(sqlite3.connect(route['database'])) as observer:
            assert observer.execute('SELECT * FROM owned').fetchall() == []
        provider.control_transaction(dict(session, action='rollback'))
        assert query('SELECT count(*) FROM owned') == [[0]]
        query('INSERT INTO owned VALUES(1, ?)', ['committed'])
        provider.control_transaction(dict(session, action='commit'))
        query('SAVEPOINT owned_savepoint')
        query('UPDATE owned SET value=?', ['changed'])
        query('ROLLBACK TO owned_savepoint')
        query('RELEASE owned_savepoint')
        assert query('SELECT value FROM owned') == [['committed']]
        receipt['checks'].append('retained-decisions-and-savepoints')
        query('CREATE VIRTUAL TABLE text_index USING fts5(body)')
        query('INSERT INTO text_index VALUES(?)', ['native SQLite text'])
        found = query("SELECT count(*) FROM text_index "
                      "WHERE text_index MATCH 'SQLite'")
        assert found == [[1]]
        query('CREATE VIRTUAL TABLE spatial USING rtree(id,x0,x1)')
        query('INSERT INTO spatial VALUES(1,0,1)')
        assert query(
            'SELECT count(*) FROM spatial WHERE x0<=0 AND x1>=0') == [[1]]
        assert query("SELECT json_extract('{\"a\":42}', '$.a')") == [[42]]
        provider.control_transaction(dict(session, action='commit'))
        receipt['checks'].append('native-fts5-rtree-json')
        started = threading.Event()
        handle.create_function('owned_signal', 0,
                               lambda: (started.set() or 1))
        source = ('WITH RECURSIVE n(x) AS (VALUES(owned_signal()) UNION ALL '
                  'SELECT x+1 FROM n WHERE x<100000000) SELECT sum(x) FROM n')
        operation = provider.execute(dict(session, source=source))
        assert started.wait(2)
        provider.cancel(operation)
        cancelled = observe(operation)[-1]['extensions']['sqlite']['payload']
        code = cancelled['error']['sqlite_errorcode']
        assert code == sqlite3.SQLITE_INTERRUPT
        assert query('SELECT 7') == [[7]]
        receipt['checks'].append('native-interruption-and-reuse')
        assert query('PRAGMA journal_mode=WAL') == [['wal']]
        backup = fixture / ('backup #% 漢字.sqlite' if os.name == 'nt'
                            else 'backup ?#% 漢字.sqlite')
        receipt_backup = client.run_database_operation(
            handle, route, 'backup', {'backup_path': str(backup)})
        assert receipt_backup['atomic_publication']
        with closing(sqlite3.connect(backup)) as copy:
            assert copy.execute('PRAGMA page_size').fetchone() == (8192,)
            assert copy.execute('SELECT value FROM owned').fetchall() == [
                ('committed',)]
        query('DELETE FROM owned')
        provider.control_transaction(dict(session, action='commit'))
        client.run_database_operation(handle, route, 'restore', {
            'backup_path': str(backup)})
        assert query('SELECT value FROM owned') == [['committed']]
        receipt['checks'].append('native-wal-backup-restore-and-page-size')
        read_only = provider.open_session(
            {'route': dict(route, read_only=True)})
        rejected = observe(
            provider.execute(
                dict(
                    read_only,
                    source='INSERT INTO owned VALUES(2, NULL)')))
        assert rejected[-1]['extensions']['sqlite']['payload'][
            'error']['sqlite_errorcode'] == sqlite3.SQLITE_READONLY
        provider.close_session(read_only)
        receipt['checks'].append('read-only-native-enforcement')
        provider.close_session(session)
        assert not client._connections
        receipt['checks'].append('native-session-release')
    except Exception as exc:
        receipt['failures'].append({'type': type(exc).__name__, 'locations': [
            {'file': Path(frame.filename).name, 'line': frame.lineno}
            for frame in traceback.extract_tb(exc.__traceback__)]})
    finally:
        try:
            if provider is not None:
                provider.close()
            shutil.rmtree(fixture)
            receipt['cleanup_complete'] = True
        except Exception as exc:
            receipt['failures'].append({'cleanup': type(exc).__name__})
        receipt['complete'] = (not receipt['failures'] and
                               receipt['cleanup_complete'])
        (evidence / 'summary.json').write_text(
            json.dumps(receipt, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', required=True, type=Path)
    args = parser.parse_args()
    receipt = run(args.evidence)
    print(json.dumps({'complete': receipt['complete'],
                      'checks': receipt['checks'],
                      'failures': receipt['failures']}))
    return 0 if receipt['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

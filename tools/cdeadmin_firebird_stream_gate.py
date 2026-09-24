#!/usr/bin/env python3
"""Streaming verification in a uniquely owned database; never mutate demos."""
import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
import threading
import time
import tracemalloc
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.cdeadmin_firebird_admin_mapping_gate import (  # noqa: E402
    _create_client, _route_arguments,
)


def run(profiles):
    import firebird.driver as driver
    document = json.loads(profiles.read_text())
    route = next(dict(item) for item in document['profiles']
                 if item['engine'] == 'firebird')
    route.setdefault('host', document.get('host', '127.0.0.1'))
    route['database'] = str(PurePosixPath(route['database']).parent /
                            ('cde_stream_owned_' + uuid.uuid4().hex + '.fdb'))
    password = route.pop('password')
    client = _create_client(SimpleNamespace(acquire_secret=None))
    connection = None
    checks = []
    try:
        connection = driver.create_database(
            password=password, **_route_arguments(route, driver))
        client._connections.append(connection)
        cursor = connection.cursor()
        cursor.execute('CREATE TABLE STREAM_TEST (ID INTEGER PRIMARY KEY, '
                       'PAYLOAD BLOB SUB_TYPE BINARY, TXT BLOB SUB_TYPE TEXT)')
        connection.commit()
        for start in range(0, 10000, 100):
            cursor.executemany('INSERT INTO STREAM_TEST (ID) VALUES (?)',
                               [(i,) for i in range(start, start + 100)])
        connection.commit()
        cursor.close()

        def request(**values):
            return client.query_stream(connection, {
                **values, 'owner_id': 'owned-live-stream-gate',
            })
        page = request(stream_action='open',
                       source='SELECT ID FROM STREAM_TEST ORDER BY ID')
        total = 0
        while True:
            assert len(page['rows']) <= 100
            assert page['rows'] == [[i] for i in range(
                total, total + len(page['rows']))]
            total += len(page['rows'])
            if page['end_of_cursor']:
                break
            page = request(stream_action='next',
                           stream_reference=page['stream_reference'],
                           sequence=page['sequence'] + 1)
        assert total == 10000
        assert connection.main_transaction.is_active()
        request(stream_action='close')
        checks.append('10000 rows pulled without gaps; no implicit finality')

        # Raw UTF-8 bytes deliberately cross chunk boundaries.
        raw = ('é漢🙂' * 400000).encode('utf-8')
        expected = hashlib.sha256(raw).hexdigest()
        for column in ('PAYLOAD', 'TXT'):
            upload = request(stream_action='upload_begin')['blob_upload']
            for offset in range(0, len(raw), 65536):
                request(stream_action='upload_chunk', blob_upload=upload,
                        offset=offset, data=base64.b64encode(
                            raw[offset:offset + 65536]).decode('ascii'))
            request(stream_action='upload_finish', blob_upload=upload)
            request(stream_action='open',
                    source=f'UPDATE STREAM_TEST SET {column}=? WHERE ID=0',
                    parameters=[{'blob_upload': upload}])
            request(stream_action='close')
            page = request(stream_action='open',
                           source=f'SELECT {column} FROM STREAM_TEST '
                           'WHERE ID=0')
            reference = page['rows'][0][0]['blob_reference']
            digest, offset = hashlib.sha256(), 0
            tracemalloc.start()
            while True:
                part = request(stream_action='blob',
                               stream_reference=page['stream_reference'],
                               blob_reference=reference, offset=offset)
                digest.update(base64.b64decode(part['data']))
                offset = part['next_offset']
                if part['complete']:
                    break
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            assert peak < 2 * 1024 * 1024, peak
            assert offset == len(raw) and digest.hexdigest() == expected
            request(stream_action='close')
            checks.append(column + ': 3.6 MB upload/read SHA-256 roundtrip')
        connection.rollback()
        page = request(stream_action='open',
                       source='SELECT PAYLOAD, TXT FROM STREAM_TEST '
                       'WHERE ID=0')
        assert page['rows'] == [[None, None]]
        request(stream_action='close')
        checks.append('explicit rollback undoes both streamed writes')
        outcome = []

        def expensive_query():
            try:
                request(stream_action='open', source=(
                    'SELECT COUNT(*) FROM STREAM_TEST A '
                    'CROSS JOIN STREAM_TEST B CROSS JOIN STREAM_TEST C'))
                outcome.append('returned')
            except Exception as exc:
                outcome.append(type(exc).__name__)

        worker = threading.Thread(target=expensive_query, daemon=True)
        worker.start()
        deadline = time.monotonic() + 10
        while not client._state(connection).stream_running:
            if time.monotonic() > deadline or not worker.is_alive():
                raise AssertionError('Native cancellation target unavailable')
            time.sleep(0.01)
        time.sleep(0.05)
        assert request(stream_action='cancel')['cancel_request_accepted']
        worker.join(15)
        assert not worker.is_alive(), 'Native cancellation did not finish'
        assert outcome != ['returned'], outcome
        request(stream_action='close')
        connection.rollback()
        checks.append('native running request cancellation and cleanup')
    finally:
        if connection is not None:
            client._close_result_stream(connection)
            connection.drop_database()
            client._connections.remove(connection)
        client.close()
    return {'passed': True, 'checks': checks, 'owned_database_removed': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--profiles', type=Path, required=True)
    options = parser.parse_args()
    print(json.dumps(run(options.profiles), indent=2))

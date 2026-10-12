#!/usr/bin/env python3
"""Native materialization admission, side effects and streaming alternative."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.cdeadmin_firebird_stream_gate import (
    _create_client, _route_arguments,
)
from tools.cdeadmin_firebird_local_fixture import run_local
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.providers.firebird import scalar_arrays
from firebird.driver.core import BlobReader


def qualify(native, admin, route, accounts, evidence, root):
    user, password = accounts['Srp'][0]
    selected = dict(route, user=user, database=str(root / 'budget.fdb'))
    client = _create_client(SimpleNamespace(acquire_secret=None))
    connection = native.create_database(
        password=password, **_route_arguments(selected, native))
    client._connections.append(connection)
    checks = []
    try:
        connection.execute_immediate(
            'CREATE TABLE LARGE_VALUES (ID INTEGER PRIMARY KEY, B BLOB, '
            'A INTEGER[1:400,1:250])')
        connection.commit()
        binary = bytes(range(256)) * (3*1024*1024//256)
        with connection.cursor() as setup:
            setup.execute('INSERT INTO LARGE_VALUES VALUES (?, ?, ?)',
                          [1, binary, [list(range(i*250, (i+1)*250))
                                       for i in range(400)]])
        connection.commit()
        with patch.object(BlobReader, 'read', side_effect=AssertionError(
                'Oversized BLOB was materialized')) as read:
            try:
                client.execute(connection, {
                    'source': 'UPDATE LARGE_VALUES SET ID=2 RETURNING B'})
            except RelationalClientError as error:
                assert 'Run streaming' in str(error)
            else:
                raise AssertionError('Oversized result accepted')
            read.assert_not_called()
        with connection.cursor() as observe:
            observe.execute('SELECT ID FROM LARGE_VALUES')
            assert observe.fetchone()[0] == 2
        with native.connect(password=password, **_route_arguments(
                selected, native)) as observer:
            with observer.cursor() as query:
                query.execute('SELECT ID FROM LARGE_VALUES')
                assert query.fetchone()[0] == 1
        connection.rollback()
        with connection.cursor() as observe:
            observe.execute('SELECT ID FROM LARGE_VALUES')
            assert observe.fetchone()[0] == 1
        checks.append('BLOB refused before read; DML pending until rollback')
        failure = AssertionError('Oversized ARRAY was materialized')
        with patch.object(scalar_arrays, 'rectangle',
                          side_effect=failure) as read:
            try:
                client.execute(connection, {
                    'source': 'SELECT A FROM LARGE_VALUES'})
            except RelationalClientError as error:
                assert 'Run streaming' in str(error)
            else:
                raise AssertionError('Oversized ARRAY accepted')
            read.assert_not_called()
        checks.append('ARRAY refused from metadata before any native slice')
        from tools.cdeadmin_firebird_admin_mapping_gate import (
            ADMINISTRATION,
        )
        try:
            ADMINISTRATION.read_rows(client, {
                '_provider_route': selected, 'session_id': 'budget-grid',
                'resource_kind': 'table', 'target_resource': {
                    'resource_kind': 'table',
                    'display_path': ['LARGE_VALUES']},
            }, connection=connection)
        except RelationalClientError as error:
            assert 'Run streaming' in str(error)
        else:
            raise AssertionError('Grid bypassed materialization admission')
        checks.append('Native grid shares materialization admission')

        source = ('SELECT FIRST 60000 CAST(\'x\' AS CHAR(100)) '
                  'FROM RDB$TYPES A CROSS JOIN RDB$TYPES B')
        try:
            client.execute(connection, {'source': source})
        except RelationalClientError as error:
            assert 'Run streaming' in str(error)
        else:
            raise AssertionError('Accumulated result budget not enforced')
        token = client.execute(connection, {
            'source': source, 'output_policy': {'max_rows': 10}})
        assert len(client.describe_result(token)['payload']['rows']) == 10
        checks.append('Rows accumulate charge; smaller query succeeds')

        def request(action, **values):
            return client.query_stream(connection, {
                'stream_action': action, 'owner_id': 'budget-gate', **values})

        page = request('open', source='SELECT B, A FROM LARGE_VALUES')
        stream_id = page['stream_reference']
        blob, array = page['rows'][0]
        digest, offset = hashlib.sha256(), 0
        while True:
            chunk = request('blob', stream_reference=stream_id,
                            blob_reference=blob['blob_reference'],
                            offset=offset)
            data = base64.b64decode(chunk['data'])
            assert len(data) <= 65536
            digest.update(data)
            offset = chunk['next_offset']
            if chunk['complete']:
                break
        assert digest.digest() == hashlib.sha256(binary).digest()
        chunk = request('array', stream_reference=stream_id,
                        array_reference=array['array_reference'], offset=0)
        assert chunk['values'] == list(range(250))
        request('close', stream_reference=stream_id)
        checks.append('Full BLOB streaming hash and bounded ARRAY pull pass')
    finally:
        client.close()
    (evidence / 'checks.json').write_text(json.dumps(checks, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    options = parser.parse_args()
    result = run_local(options.runtime, options.evidence, qualify)
    raise SystemExit(0 if result['complete'] else 1)

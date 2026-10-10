#!/usr/bin/env python3
"""Native typed ARRAY pulls, copied row identities and bounded buffers."""
import argparse
import base64
from datetime import date, datetime, time
from decimal import Decimal
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.cdeadmin_firebird_stream_gate import (
    _create_client, _route_arguments,
)
from tools.cdeadmin_firebird_local_fixture import run_local
from pgadmin.cdeadmin.providers.firebird import (
    array_upload, scalar_arrays, varying_arrays,
)
from pgadmin.cdeadmin.providers.firebird.temporal_arrays import cursor
from pgadmin.cdeadmin.providers.firebird.query_values import normalize_value
from pgadmin.cdeadmin.providers.firebird.zoned_values import parse as zoned
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def qualify(native, admin, route, accounts, evidence, root,
            embedded_mode=False, wide_bounds=False, portable_files=False):
    user, password = (('OWNED_LOCAL', None) if embedded_mode else
                      accounts['Srp'][0])
    if embedded_mode:
        route = {'attachment_mode': 'embedded', 'filesystem_root': str(root)}
    selected = dict(route, user=user, database=str(root / 'arrays.fdb'))
    client = _create_client(SimpleNamespace(acquire_secret=None))
    connection = native.create_database(
        password=password, **_route_arguments(selected, native))
    client._connections.append(connection)
    cases = [
        ('SMALLINT', [0, -32768, 32767]),
        ('INTEGER', [0, -2147483648, 2147483647]),
        ('BIGINT', [0, -(2**63), 2**63-1]),
        ('INT128', [0, -(2**127), 2**127-1]),
        ('NUMERIC(38,4)', [Decimal('-123456789012345678901234.1234')]),
        ('DECFLOAT(16)', [Decimal('1.234567890123456')]),
        ('DECFLOAT(34)', [Decimal('1.234567890123456789012345678901234')]),
        ('FLOAT', [0., -0., -1.5, 1.5, float('nan'),
                   float('inf'), -float('inf')]),
        ('DOUBLE PRECISION', [0., -0., -1.5, 1.5, float('nan'),
                              float('inf'), -float('inf')]),
        ('BOOLEAN', [True, False]),
        ('DATE', [date(1, 1, 1), date(1858, 11, 16), date(9999, 12, 31)]),
        ('TIME', [time(0), time(23, 59, 59, 999900)]),
        ('TIMESTAMP', [datetime(1, 1, 1), datetime(9999, 12, 31)]),
        ('TIME WITH TIME ZONE', [zoned({
            'encoding': 'firebird-time-tz', 'utc': '23:59:59.999900',
            'time_zone': 'America/New_York'})]),
        ('TIMESTAMP WITH TIME ZONE', [zoned({
            'encoding': 'firebird-timestamp-tz',
            'utc': '2025-11-02 ' + clock + ':00.000100',
            'time_zone': 'America/New_York'})
            for clock in ('05:30', '06:30')]),
        ('CHAR(8)|UTF8', ['é漢🙂', '', 'a\0b']),
        ('VARCHAR(8)|UTF8', ['é漢🙂', '', 'a\0b', ' trailing '[:8]]),
        ('VARCHAR(8)|WIN1252', ['é', '', 'a\0b', ' x ']),
        ('VARCHAR(8)|ISO8859_1', ['é', '', 'a\0b']),
        ('VARCHAR(8)|ASCII', ['ascii', '', 'a\0b']),
        ('CHAR(8)|OCTETS', [b'\0\xff\0 ', b'', b' \0 ']),
        ('VARCHAR(8)|OCTETS', [b'\0\xff\0 ', b'', b' \0 ']),
        ('VARCHAR(8000)|UTF8', ['é漢🙂' * 1000, '', 'a\0b']),
    ]
    checks = []

    def request(action, **values):
        return client.query_stream(connection, {
            'stream_action': action, 'owner_id': 'array-gate', **values})

    try:
        if embedded_mode:
            with connection.cursor() as probe:
                probe.execute(
                    "SELECT MON$REMOTE_PROTOCOL, MON$SERVER_PID, "
                    "RDB$GET_CONTEXT('SYSTEM','ENGINE_VERSION') "
                    'FROM MON$ATTACHMENTS WHERE '
                    'MON$ATTACHMENT_ID=CURRENT_CONNECTION')
                protocol, pid, version = probe.fetchone()
            assert protocol is None and pid == os.getpid()
            assert version == '5.0.4'
            connection.rollback()
        for index, (declaration, samples) in enumerate(cases):
            (evidence / 'active-case.json').write_text(json.dumps({
                'declaration': declaration, 'completed': checks}, indent=2))
            parts = declaration.split('|')
            inner = 20 if '8000' in declaration else 600
            low0, low1 = ((65536, 2147483648-inner) if wide_bounds else
                          (-2, 3))
            bounds = [[low0, low0+1], [low1, low1+inner-1]]
            field = f'{parts[0]}[{low0}:{low0+1},{low1}:{low1+inner-1}]'
            column = '区域'*20 if wide_bounds else 'A'
            if len(parts) == 2:
                field += ' CHARACTER SET ' + parts[1]
            table = f'ARRAY_TEST_{index}' + ('_LONG_' + 'X'*35
                                             if wide_bounds else '')
            connection.execute_immediate(
                f'CREATE TABLE {table} (ID INTEGER, "{column}" {field})')
            connection.commit()
            values = [[samples[(i * inner+j) % len(samples)]
                       for j in range(inner)] for i in range(2)]
            with cursor(connection) as query:
                query.execute(f'INSERT INTO {table} VALUES (?, ?)',
                              [1, values])
                query.execute(f'INSERT INTO {table} VALUES (?, ?)',
                              [2, list(reversed(values))])
                query.execute(f'INSERT INTO {table} VALUES (3, NULL)')
                query.execute(
                    f'SELECT "{column}" AS A FROM {table} ORDER BY ID')
                ordinary = [normalize_value(row[0])
                            for row in query.fetchall()]
            # The normal query path still reconstructs complete arrays.
            expected = values
            if declaration == 'INT128':
                expected = [[Decimal(v) for v in row] for row in values]
            if declaration.startswith('CHAR('):
                padding = b'\0' if parts[1] == 'OCTETS' else ' '
                expected = [[v.ljust(8, padding) for v in row]
                            for row in values]
            if ordinary[0] != normalize_value(expected):
                (evidence / 'value-difference.json').write_text(json.dumps({
                    'actual': ordinary[0][0][:3],
                    'expected': normalize_value(expected)[0][:3]}, indent=2))
            assert ordinary[0] == normalize_value(expected), declaration
            assert ordinary[1] == normalize_value(list(reversed(expected)))
            assert ordinary[2] is None
            allocations = []
            allocate = scalar_arrays.create_string_buffer

            def bounded(size, *args):
                length = size if isinstance(size, int) else len(size)
                allocations.append(length)
                assert length <= 65536, (declaration, length)
                return allocate(size, *args)

            pulls = 0
            with patch.object(scalar_arrays, 'create_string_buffer',
                              bounded), \
                    patch.object(varying_arrays, 'create_string_buffer',
                                 bounded):
                page = request('open', source=(
                    f'SELECT "{column}" AS A FROM {table} ORDER BY ID'))
                assert not allocations, 'Opening materialized ARRAY data'
                assert page['rows'][2][0] is None
                assert page['end_of_cursor']
                exported = []
                for number, row in enumerate(page['rows'][:2]):
                    reference = row[0]['array_reference']
                    if number == 0:
                        exported.append({
                            'format': 'cdeadmin.firebird-array.v1',
                            **{key: value for key, value in row[0].items()
                               if key != 'array_reference'},
                        })
                    assert row[0]['bounds'] == bounds
                    assert row[0]['element_count'] == inner * 2
                    offset, collected = 0, []
                    while offset < inner * 2:
                        args = {'stream_reference': page['stream_reference'],
                                'array_reference': reference, 'offset': offset}
                        chunk = request('array', **args)
                        count = len(allocations)
                        assert request('array', **args) == chunk
                        assert len(allocations) == count, 'Native retry read'
                        assert chunk['coordinates'] == [
                            low0 + offset // inner, low1 + offset % inner]
                        assert 1 <= len(chunk['values']) <= 256
                        collected.extend(chunk['values'])
                        if number == 0:
                            exported.append({key: chunk[key] for key in (
                                'offset', 'coordinates', 'values')})
                        offset = chunk['next_offset']
                        pulls += 1
                    assert chunk['complete']
                    assert collected == sum(ordinary[number], []), declaration
                exported.append({'complete': True, 'element_count': inner * 2})
            request('close')
            assert connection.main_transaction.is_active()
            try:
                request('array', **args)
            except RelationalClientError:
                pass
            else:
                raise AssertionError('Closed ARRAY reference was accepted')
            raw = ''.join(json.dumps(record) + '\n'
                          for record in exported).encode('utf8')
            if portable_files:
                page = request('open', source=(
                    f'SELECT "{column}" AS A FROM {table} WHERE ID=1'))
                descriptor = page['rows'][0][0]
                binding = {'stream_reference': page['stream_reference']}
                delivery = request(
                    'download_begin', **binding, value_kind='array',
                    value_reference=descriptor['array_reference'])
                binding['download_id'] = delivery['download_id']
                request('download_open', **binding)
                chunks = []
                sequence = 0
                with patch.object(scalar_arrays, 'create_string_buffer',
                                  bounded), \
                        patch.object(varying_arrays, 'create_string_buffer',
                                     bounded):
                    while True:
                        chunk = request('download_chunk', **binding,
                                        sequence=sequence)
                        content = base64.b64decode(
                            chunk['data'], validate=True)
                        assert len(content) <= 1048576
                        chunks.append(content)
                        if chunk['complete']:
                            break
                        sequence += 1
                # Fixture-only accumulation supplies an independent import
                # oracle. Product delivery remains one bounded chunk at a time.
                raw = b''.join(chunks)
                assert [json.loads(line) for line in raw.splitlines()] == (
                    exported), declaration
                assert request('download_finish', **binding)['state'] == 'sent'
                request('close')
            token = request('upload_begin', value_kind='array')
            for start in range(0, len(raw), 65536):
                request('upload_chunk', **token, offset=start,
                        data=base64.b64encode(raw[start:start+65536]).decode())
            request('upload_finish', **token)
            with patch.object(array_upload, 'create_string_buffer', bounded):
                changed = request('open', source=(
                    f'UPDATE {table} SET "{column}"=? WHERE ID=2'),
                    parameters=[token])
            assert changed['end_of_cursor']
            assert client._state(connection).blob_upload is None
            request('close')
            with cursor(connection) as query:
                query.execute(
                    f'SELECT "{column}" AS A FROM {table} WHERE ID=2')
                assert normalize_value(query.fetchone()[0]) == ordinary[0]
            client.control_transaction(connection, 'rollback')
            with cursor(connection) as query:
                query.execute(f'SELECT COUNT(*) FROM {table}')
                assert query.fetchone()[0] == 0
            connection.rollback()
            checks.append({'declaration': declaration, 'native_pulls': pulls,
                           'largest_native_buffer': max(allocations),
                           'normal_path_fidelity': True,
                           'streamed_fidelity': True,
                           'retry_avoids_native_read': True,
                           'staged_file_update_roundtrip': True,
                           'portable_file_roundtrip': portable_files,
                           'explicit_rollback_verified': True})
    finally:
        client.close()
    (evidence / 'array-checks.json').write_text(json.dumps(
        {'checks': checks, 'embedded_same_process_verified': embedded_mode},
        indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--embedded', action='store_true')
    parser.add_argument('--wide-bounds', action='store_true')
    parser.add_argument('--portable-files', action='store_true')
    options = parser.parse_args()
    if options.embedded:
        from tools.cdeadmin_firebird_recovery_group_gate import run_embedded
    fixture = run_embedded if options.embedded else run_local
    result = fixture(options.runtime, options.evidence,
                     lambda *args: qualify(
                         *args, embedded_mode=options.embedded,
                         wide_bounds=options.wide_bounds,
                         portable_files=options.portable_files))
    raise SystemExit(0 if result['complete'] else 1)

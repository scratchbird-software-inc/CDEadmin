#!/usr/bin/env python3
"""Observe stock-driver zoned metadata and ambiguous-time decoding."""
import argparse
from ctypes import sizeof
import json
from pathlib import Path
from types import SimpleNamespace

from tools.cdeadmin_firebird_stream_gate import (
    _create_client, _route_arguments,
)
from tools.cdeadmin_firebird_local_fixture import run_local
from firebird.driver import fbapi


def qualify(native, admin, route, accounts, evidence, root):
    user, password = accounts['Srp'][0]
    selected = dict(route, user=user, database=str(root / 'zones.fdb'))
    client = _create_client(SimpleNamespace(acquire_secret=None))
    connection = native.create_database(
        password=password, **_route_arguments(selected, native))
    client._connections.append(connection)
    observations = {'native_time_tz_bytes': sizeof(fbapi.ISC_TIME_TZ),
                    'native_timestamp_tz_bytes': sizeof(
                        fbapi.ISC_TIMESTAMP_TZ),
                    'scalar': [], 'array_ddl': []}
    try:
        for instant in ('2025-11-02 05:30:00 UTC', '2025-11-02 06:30:00 UTC'):
            query = connection.cursor()
            try:
                query.execute(
                    'SELECT CAST(? AS TIMESTAMP WITH TIME ZONE) '
                    "AT TIME ZONE 'America/New_York', "
                    "CAST('12:34:56.1234 America/New_York' "
                    "AS TIME WITH TIME ZONE) "
                    'FROM RDB$DATABASE', [instant])
                row = query.fetchone()
                observations['scalar'].append({
                    'input_utc': instant,
                    'decoded_timestamp': row[0].isoformat(),
                    'decoded_fold': row[0].fold,
                    'timestamp_zone': getattr(
                        row[0].tzinfo, '_timezone_', None),
                    'decoded_time': row[1].isoformat(),
                    'time_zone': getattr(row[1].tzinfo, '_timezone_', None),
                    'metadata': [
                        {'datatype': int(d.datatype), 'length': d.length,
                         'offset': d.offset} for d in query._stmt._out_desc],
                    'native_buffer_hex': query._stmt._out_buffer.raw.hex(),
                })
            finally:
                query.close()
        for index, declaration in enumerate((
                'TIME WITH TIME ZONE', 'TIMESTAMP WITH TIME ZONE')):
            try:
                connection.execute_immediate(
                    f'CREATE TABLE AZ_{index} (A {declaration}[1:2])')
                connection.commit()
                accepted = True
            except native.DatabaseError:
                connection.rollback()
                accepted = False
            observations['array_ddl'].append({
                'declaration': declaration, 'native_accepted': accepted})
    finally:
        client.close()
    (evidence / 'observations.json').write_text(
        json.dumps(observations, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    options = parser.parse_args()
    result = run_local(options.runtime, options.evidence, qualify)
    raise SystemExit(0 if result['complete'] else 1)

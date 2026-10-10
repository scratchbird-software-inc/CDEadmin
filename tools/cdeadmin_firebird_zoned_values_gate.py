#!/usr/bin/env python3
"""Native DST identity and bindings against SQL UTC oracles."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from tools.cdeadmin_firebird_stream_gate import (
    _create_client, _route_arguments,
)
from tools.cdeadmin_firebird_local_fixture import run_local
from pgadmin.cdeadmin.providers.firebird.temporal_arrays import cursor
from pgadmin.cdeadmin.providers.firebird.query_values import normalize_value
from pgadmin.cdeadmin.providers.firebird.query_parameters import (
    normalize_parameters,
)
from pgadmin.cdeadmin.providers.firebird.grid_values import (
    bind_value, input_kinds,
)


def qualify(native, admin, route, accounts, evidence, root):
    user, password = accounts['Srp'][0]
    selected = dict(route, user=user, database=str(root / 'zones.fdb'))
    client = _create_client(SimpleNamespace(acquire_secret=None))
    connection = native.create_database(
        password=password, **_route_arguments(selected, native))
    client._connections.append(connection)
    checks = []
    try:
        connection.execute_immediate(
            'CREATE TABLE ZONED (ID INTEGER PRIMARY KEY, '
            'T TIME WITH TIME ZONE, '
            'S TIMESTAMP WITH TIME ZONE)')
        connection.commit()
        with connection.cursor() as setup:
            for index, instant in enumerate((
                    '2025-11-02 05:30:00.0001 UTC',
                    '2025-11-02 06:30:00.0001 UTC')):
                setup.execute(
                    'INSERT INTO ZONED VALUES (?, '
                    "CAST('12:34:56.1234 America/New_York' AS TIME "
                    'WITH TIME ZONE), CAST(? AS TIMESTAMP WITH TIME ZONE) '
                    "AT TIME ZONE 'America/New_York')", [index, instant])
        connection.commit()
        with cursor(connection) as query:
            query.execute('SELECT T, S FROM ZONED ORDER BY ID')
            assert input_kinds(query) == (
                'firebird-time-tz', 'firebird-timestamp-tz')
            rows = [normalize_value(row) for row in query.fetchall()]
            assert rows[0][1]['utc'] == '2025-11-02 05:30:00.000100'
            assert rows[1][1]['utc'] == '2025-11-02 06:30:00.000100'
            assert all(v['time_zone'] == 'America/New_York'
                       for row in rows for v in row)
            for index, row in enumerate(rows):
                query.execute('INSERT INTO ZONED VALUES (?, ?, ?)',
                              (index+10, *normalize_parameters(row)))
                query.execute('SELECT T, S FROM ZONED WHERE ID=?', [index+10])
                assert normalize_value(query.fetchone()) == row
                query.execute('UPDATE ZONED SET T=?, S=? WHERE ID=?',
                              [bind_value(v) for v in row]+[index+10])
            # Zoned-to-plain CAST uses the session zone. Pin it for the
            # independent SQL oracle, never assume AT TIME ZONE strips it.
            query.execute("SET TIME ZONE 'UTC'")
            query.execute(
                "SELECT CAST(S AT TIME ZONE 'UTC' AS TIMESTAMP) "
                'FROM ZONED ORDER BY ID')
            utc = [v[0].isoformat(sep=' ') for v in query.fetchall()]
            (evidence / 'utc-oracle.json').write_text(json.dumps(
                {'actual': utc, 'expected': [r[1]['utc'] for r in rows]*2},
                indent=2))
            assert utc == [rows[0][1]['utc'], rows[1][1]['utc']]*2
            checks.append({'case': 'DST fold query/grid envelope round trip',
                           'rows': rows, 'native_utc': utc})
            for zone in ('+00:00', '+14:00', '-14:00', '+05:45',
                         'America/New_York', 'Asia/Kathmandu'):
                for kind, declaration, value in (
                        ('firebird-time-tz', 'TIME WITH TIME ZONE',
                         '23:59:59.999900'),
                        ('firebird-timestamp-tz', 'TIMESTAMP WITH TIME ZONE',
                         '1858-11-16 23:59:59.999900')):
                    envelope = {'encoding': kind, 'utc': value,
                                'time_zone': zone}
                    query.execute(f'SELECT CAST(? AS {declaration}) '
                                  'FROM RDB$DATABASE',
                                  normalize_parameters([envelope]))
                    assert normalize_value(query.fetchone()[0]) == envelope
                    checks.append({'case': kind, 'zone': zone})
            query.execute('SELECT CAST(NULL AS TIME WITH TIME ZONE), '
                          'CAST(NULL AS TIMESTAMP WITH TIME ZONE) '
                          'FROM RDB$DATABASE')
            assert query.fetchone() == (None, None)
        connection.rollback()
        with connection.cursor() as check:
            check.execute('SELECT COUNT(*) FROM ZONED')
            assert check.fetchone()[0] == 2
        checks.append({'case': 'Explicit rollback preserved committed rows'})
        connection.commit()
        connection.execute_immediate(
            'CREATE VIEW ZONED_VIEW AS SELECT * FROM ZONED')
        connection.commit()
        from tools.cdeadmin_firebird_admin_mapping_gate import (
            ADMINISTRATION,
        )
        for kind, name in (('table', 'ZONED'), ('view', 'ZONED_VIEW')):
            request = {'_provider_route': selected,
                       'session_id': 'zones-'+kind,
                       'resource_kind': kind, 'target_resource': {
                           'resource_kind': kind, 'display_path': [name]}}
            page = ADMINISTRATION.read_rows(client, request,
                                            connection=connection)
            assert [c['input_kind'] for c in page['columns']] == [
                'integer', 'firebird-time-tz', 'firebird-timestamp-tz']
            row = page['rows'][0]
            changed = {
                'encoding': 'firebird-timestamp-tz',
                'utc': '2025-11-02 06:30:00.000100',
                'time_zone': 'America/New_York'}
            plan = ADMINISTRATION.plan({
                **request, 'operation_id': 'update', 'draft': {
                    'selector': {'identity_token': row['identity_token']},
                    'changes': {'S': changed}}})
            ADMINISTRATION.apply(client, plan, connection=connection)
            page = ADMINISTRATION.read_rows(client, request,
                                            connection=connection)
            assert page['rows'][0]['values']['S'] == changed
            connection.rollback()
            page = ADMINISTRATION.read_rows(client, request,
                                            connection=connection)
            assert page['rows'][0]['values']['S'] == rows[0][1]
            checks.append({'case': 'native grid '+kind,
                           'update_and_rollback': True})

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

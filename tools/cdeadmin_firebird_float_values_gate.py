#!/usr/bin/env python3
"""Native IEEE bindings, grid identities and transaction outcome."""
import argparse
import json
import math
from pathlib import Path
from types import SimpleNamespace

from tools.cdeadmin_firebird_stream_gate import (
    _create_client, _route_arguments,
)
from tools.cdeadmin_firebird_local_fixture import run_local
from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION
from pgadmin.cdeadmin.providers.firebird.temporal_arrays import cursor
from pgadmin.cdeadmin.providers.firebird.query_parameters import (
    normalize_parameters,
)


def qualify(native, admin, route, accounts, evidence, root):
    user, password = accounts['Srp'][0]
    selected = dict(route, user=user, database=str(root / 'ieee.fdb'))
    client = _create_client(SimpleNamespace(acquire_secret=None))
    connection = native.create_database(
        password=password, **_route_arguments(selected, native))
    client._connections.append(connection)
    checks = []
    try:
        connection.execute_immediate(
            'CREATE TABLE IEEE_VALUES (ID INTEGER PRIMARY KEY, F FLOAT, '
            'D DOUBLE PRECISION, A FLOAT[1:3], B DOUBLE PRECISION[1:3], '
            'V INTEGER)')
        connection.commit()
        for index, text in enumerate(('NaN', 'Infinity', '-Infinity',
                                      '-0.0', '1.5')):
            values = [dict(encoding=kind, data=text)
                      for kind in ('float32', 'float64')]
            expected = repr(float(text))
            result = client.execute(connection, {
                'source': 'SELECT CAST(? AS FLOAT) AS F, '
                'CAST(? AS DOUBLE PRECISION) AS D FROM RDB$DATABASE',
                'parameters': values})
            payload = client.describe_result(result)['payload']
            json.dumps(payload, allow_nan=False)
            actual = payload['rows'][0]
            assert all(str(value) == expected for value in actual)
            with cursor(connection) as query:
                query.execute('INSERT INTO IEEE_VALUES VALUES '
                              '(?, ?, ?, ?, ?, 1)',
                              [index, *normalize_parameters(values),
                               ['nan', 'inf', '-inf'],
                               ['nan', 'inf', '-inf']])
            connection.commit()
            request = {
                '_provider_route': selected, 'session_id': 'ieee-'+str(index),
                'resource_kind': 'table', 'target_resource': {
                    'resource_kind': 'table', 'display_path': ['IEEE_VALUES']}}
            page = ADMINISTRATION.read_rows(client, request,
                                            connection=connection)
            row = next(row for row in page['rows']
                       if row['values']['ID'] == index)
            assert row['values']['F'] == row['values']['D'] == expected
            assert row['values']['A'] == ['nan', 'inf', '-inf']
            plan = ADMINISTRATION.plan({
                **request, 'operation_id': 'update', 'draft': {
                    'selector': {'identity_token': row['identity_token']},
                    'changes': {'F': values[0], 'D': values[1], 'V': 2}}})
            ADMINISTRATION.apply(client, plan, connection=connection)
            assert connection.main_transaction.is_active()
            with cursor(connection) as query:
                query.execute('SELECT F, D, V FROM IEEE_VALUES WHERE ID=?',
                              [index])
                first, second, changed = query.fetchone()
                assert changed == 2
                for value in (first, second):
                    assert math.isnan(value) if text == 'NaN' else (
                        value == float(text) and
                        math.copysign(1, value) ==
                        math.copysign(1, float(text)))
            connection.rollback()
            with connection.cursor() as query:
                query.execute('SELECT V FROM IEEE_VALUES WHERE ID=?', [index])
                assert query.fetchone()[0] == 1
            connection.rollback()
            checks.append({'value': text, 'query_and_grid': True,
                           'array_classes_preserved': True,
                           'native_sign_and_class': True,
                           'explicit_rollback': True})
    finally:
        client.close()
        (evidence / 'checks.json').write_text(
            json.dumps(checks, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    options = parser.parse_args()
    result = run_local(options.runtime, options.evidence, qualify)
    raise SystemExit(0 if result['complete'] else 1)

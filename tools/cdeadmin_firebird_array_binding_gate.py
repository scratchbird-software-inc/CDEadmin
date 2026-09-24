#!/usr/bin/env python3
"""Native array input boundaries, denied writes, and transaction visibility."""
import argparse
import json
from pathlib import Path

if __package__:
    from . import cdeadmin_firebird_grid_array_rows_gate as arrays
else:
    import cdeadmin_firebird_grid_array_rows_gate as arrays

base = arrays.base


def verify(connection, client, route, password, result):
    arrays.verify(connection, client, route, password, result)
    checks = result['array_binding_checks'] = []
    cases = [
        ('SMALLINT', ['-32768', '32767'], '32768'),
        ('INTEGER', ['-2147483648', '2147483647'], '2147483648'),
        ('BIGINT', ['-9223372036854775808', '9223372036854775807'],
         '9223372036854775808'),
        ('INT128', [str(-(1 << 127)), str((1 << 127)-1)], str(1 << 127)),
        ('NUMERIC(4,2)', ['-327.68', '327.67'], '327.68'),
        ('DECIMAL(9,2)', ['-21474836.48', '21474836.47'], '1.001'),
        ('FLOAT', ['-0.0', '3.4028234663852886e38'], '1e100'),
        ('DOUBLE PRECISION', ['-0.0', '1.7976931348623157e308'], '1e400'),
        ('BOOLEAN', [False, True], 1),
    ]
    from decimal import Decimal
    from pgadmin.cdeadmin.sdk.relational import RelationalClientError
    from pgadmin.cdeadmin.providers.firebird.grid_arrays import convert
    for number, (native, values, invalid) in enumerate(cases):
        for action in ('commit', 'rollback'):
            handle = client.open_session({'route': route})
            observer = client.open_session({'route': route})
            name = f'GAB_{number}_{action.upper()}'
            case = f'{native}:{action}'
            try:
                with handle.cursor() as cursor:
                    cursor.execute(
                        f'CREATE TABLE {name} '
                        f'(ID INTEGER PRIMARY KEY, A {native}[0:1])')
                client.control_transaction(handle, 'commit')
                request = {'_provider_route': route, 'session_id': case,
                           'resource_kind': 'table', 'target_resource': {
                               'resource_kind': 'table',
                               'display_path': [name]}}

                def insert(key, elements):
                    plan = base.ADMINISTRATION.plan({
                        **request, 'operation_id': 'insert', 'draft': {
                            'values': {'ID': key, 'A': elements}}})
                    return base.ADMINISTRATION.apply(
                        client, plan, connection=handle)

                insert(1, values)
                page = base.ADMINISTRATION.read_rows(
                    client, request, connection=handle)
                assert len(page['rows']) == 1
                # Verify actual stored native values, not only wire rendering.
                with handle.cursor() as cursor:
                    cursor.execute(f'SELECT A FROM {name}')
                    actual = cursor.fetchone()[0]
                if native in ('FLOAT', 'DOUBLE PRECISION'):
                    import math
                    assert math.copysign(1, actual[0]) == -1
                    code = 10 if native == 'FLOAT' else 27
                    assert actual == convert(values, dict(
                        type=code, subtype=0, scale=0, bounds=[(0, 1)]))
                elif native == 'BOOLEAN':
                    assert actual == values
                else:
                    assert actual == [Decimal(item) for item in values]
                from pgadmin.cdeadmin.providers.firebird.grid_values import (
                    normalize_value,
                )
                assert page['rows'][0]['values']['A'] == normalize_value(
                    actual)
                plan = base.ADMINISTRATION.plan({
                    **request, 'operation_id': 'update', 'draft': {
                        'selector': {'identity_token': page['rows'][0][
                            'identity_token']},
                        'changes': {'A': list(reversed(values))}}})
                base.ADMINISTRATION.apply(client, plan, connection=handle)
                with handle.cursor() as cursor:
                    cursor.execute(f'SELECT A FROM {name}')
                    assert cursor.fetchone()[0] == list(reversed(actual))
                for elements in ([invalid, values[1]], [], [None, values[1]]):
                    try:
                        insert(2, elements)
                    except RelationalClientError:
                        pass
                    else:
                        raise AssertionError('Invalid array write succeeded')
                    with handle.cursor() as cursor:
                        cursor.execute(f'SELECT COUNT(*) FROM {name}')
                        assert cursor.fetchone()[0] == 1
                    current = base.ADMINISTRATION.read_rows(
                        client, request, connection=handle)
                    plan = base.ADMINISTRATION.plan({
                        **request, 'operation_id': 'update', 'draft': {
                            'selector': {'identity_token': current['rows'][0][
                                'identity_token']},
                            'changes': {'A': elements}}})
                    try:
                        base.ADMINISTRATION.apply(
                            client, plan, connection=handle)
                    except RelationalClientError:
                        pass
                    else:
                        raise AssertionError('Invalid array update succeeded')
                    with handle.cursor() as cursor:
                        cursor.execute(f'SELECT A FROM {name}')
                        assert cursor.fetchone()[0] == list(reversed(actual))
                with observer.cursor() as cursor:
                    cursor.execute(f'SELECT COUNT(*) FROM {name}')
                    assert cursor.fetchone()[0] == 0
                client.control_transaction(observer, 'rollback')
                client.control_transaction(handle, action)
                with observer.cursor() as cursor:
                    cursor.execute(f'SELECT A FROM {name}')
                    expected = [(list(reversed(actual)),)] if (
                        action == 'commit') else []
                    assert cursor.fetchall() == expected
                checks.append({'case': case, 'passed': True})
            except Exception as exc:
                result['failures'].append({
                    'case': case, 'message': str(exc).replace(
                        password, '<redacted>')})
            finally:
                client.close_session(observer)
                client.close_session(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; preserve previous evidence')
    result = base.run(extra_checks=verify)
    result['complete'] = bool(result['complete'] and
                              len(result.get('array_binding_checks', [])) == 18
                              and not result['failures'])
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'complete': result['complete'],
                      'failures': result['failures']}))
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

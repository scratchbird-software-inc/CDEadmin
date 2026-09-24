#!/usr/bin/env python3
"""Temporal array ranges, views and transaction finality."""
import argparse
import json
from pathlib import Path

if __package__:
    from . import cdeadmin_firebird_decfloat_arrays_gate as decimals
else:
    import cdeadmin_firebird_decfloat_arrays_gate as decimals

base = decimals.base


def verify(connection, client, route, password, result):
    decimals.verify(connection, client, route, password, result)
    checks = result['temporal_array_checks'] = []
    from datetime import date, datetime, time
    from pgadmin.cdeadmin.sdk.relational import RelationalClientError
    from pgadmin.cdeadmin.providers.firebird.grid_values import normalize_value
    from pgadmin.cdeadmin.providers.firebird.temporal_arrays import cursor
    from firebird.driver import core
    for action in ('commit', 'rollback'):
        handle = client.open_session({'route': route})
        probe = cursor(handle)
        try:
            probe.execute('SELECT CURRENT_DATE FROM RDB$DATABASE')
            assert isinstance(probe.fetchone()[0], date)
            client.control_transaction(handle, action)
            assert not probe._executed
            with handle.cursor() as ordinary:
                assert type(ordinary) is core.Cursor
        finally:
            probe.close()
            client.close_session(handle)
    result['temporal_cursor_ownership_verified'] = True
    cases = [
        ('DATE', date, ['0001-01-01', '1858-11-16', '1858-11-17',
                        '9999-12-31'],
         '2023-02-29'),
        ('TIME', time, ['00:00:00', '00:00:00.0001', '12:34:56.1234',
                        '23:59:59.9999'], '00:00:00.00001'),
        ('TIMESTAMP', datetime, [
            '0001-01-01 00:00:00', '1858-11-16 23:59:59.9999',
            '1858-11-17 00:00:00.0001', '9999-12-31 23:59:59.9999'],
         '2000-01-01 00:00:00+01:00'),
    ]

    def sql(handle, source):
        with handle.cursor() as cursor:
            cursor.execute(source)
            return cursor.fetchall() if cursor.description else []

    for number, (native, value_type, values, invalid) in enumerate(cases):
        admin = client.open_session({'route': route})
        table, view = f'GTA_{number}', f'GTAV_{number}'
        try:
            sql(admin, f'CREATE TABLE {table} (ID INTEGER PRIMARY KEY, '
                f'A {native}[-1:0,2:3])')
            client.control_transaction(admin, 'commit')
            sql(admin, f'CREATE VIEW {view} AS SELECT ID, A FROM {table}')
            client.control_transaction(admin, 'commit')
        finally:
            client.close_session(admin)
        for kind, name in (('table', table), ('view', view)):
            for action in ('commit', 'rollback'):
                for index, value in enumerate(values):
                    handle = client.open_session({'route': route})
                    observer = client.open_session({'route': route})
                    case = f'{native}:{kind}:{action}:{value}'
                    request = {'_provider_route': route, 'session_id': case,
                               'resource_kind': kind, 'target_resource': {
                                   'resource_kind': kind,
                                   'display_path': [name]}}

                    def page():
                        return base.ADMINISTRATION.read_rows(
                            client, request, connection=handle)

                    def apply(operation, draft):
                        plan = base.ADMINISTRATION.plan({
                            **request, 'operation_id': operation,
                            'draft': draft})
                        base.ADMINISTRATION.apply(
                            client, plan, connection=handle)

                    try:
                        initial = page()
                        column = next(item for item in initial['columns']
                                      if item['name'] == 'A')
                        assert column['array_spec'][
                            'element_kind'] == native.lower()
                        original = [[value, values[0]], [values[-1], value]]
                        expected = [[value_type.fromisoformat(item)
                                     for item in row] for row in original]
                        apply('insert', {
                            'values': {'ID': index, 'A': original},
                            'options': {'identity_token': initial[
                                'insert_identity_token']}})
                        current = page()
                        json.dumps(current)
                        row = current['rows'][0]
                        assert row['values']['A'] == normalize_value(expected)
                        assert sql(handle, f'SELECT A FROM {table}')[0][0] == (
                            expected)
                        changed = list(reversed(original))
                        expected.reverse()
                        apply('update', {'selector': {'identity_token': row[
                            'identity_token']}, 'changes': {'A': changed}})
                        row = page()['rows'][0]
                        apply('update', {'selector': {'identity_token': row[
                            'identity_token']}, 'changes': {'A': None}})
                        row = page()['rows'][0]
                        assert row['values']['A'] is None
                        apply('update', {'selector': {'identity_token': row[
                            'identity_token']}, 'changes': {'A': changed}})
                        for bad in (invalid, None):
                            row = page()['rows'][0]
                            try:
                                apply('update', {
                                    'selector': {'identity_token':
                                                 row['identity_token']},
                                    'changes': {'A': [[bad, value],
                                                      [value, value]]}})
                            except RelationalClientError:
                                pass
                            else:
                                raise AssertionError('Invalid array accepted')
                            actual = sql(handle, f'SELECT A FROM {table}')
                            assert actual[0][0] == expected
                        assert sql(observer, f'SELECT A FROM {table}') == []
                        client.control_transaction(observer, 'rollback')
                        client.control_transaction(handle, action)
                        observed = sql(observer, f'SELECT A FROM {table}')
                        if action == 'commit':
                            assert observed == [(expected,)]
                            row = page()['rows'][0]
                            apply('delete', {'selector': {
                                'identity_token': row['identity_token']}})
                            client.control_transaction(handle, 'commit')
                            client.control_transaction(observer, 'rollback')
                            assert not sql(observer,
                                           f'SELECT A FROM {table}')
                        else:
                            assert observed == []
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
    parser.add_argument('--slice-bytes', type=int, default=1024 * 1024)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; preserve previous evidence')
    if not 16 <= args.slice_bytes <= 1024 * 1024:
        parser.error('Slice bytes must be between 16 and 1048576')
    from pgadmin.cdeadmin.providers.firebird import varying_arrays
    varying_arrays.SLICE_BYTES = args.slice_bytes
    result = base.run(extra_checks=verify)
    result['slice_bytes'] = args.slice_bytes
    checks = result.get('temporal_array_checks', [])
    result['complete'] = bool(result['complete'] and not result['failures'] and
                              len(checks) == 48 and result.get(
                                  'temporal_cursor_ownership_verified'))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'complete': result['complete'],
                      'failures': result['failures']}))
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

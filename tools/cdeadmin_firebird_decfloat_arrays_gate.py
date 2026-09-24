#!/usr/bin/env python3
"""Exact native DECFLOAT array mutations, special values, and finality."""
import argparse
import json
from pathlib import Path

if __package__:
    from . import cdeadmin_firebird_array_binding_gate as binding
else:
    import cdeadmin_firebird_array_binding_gate as binding

base = binding.base


def verify(connection, client, route, password, result):
    binding.verify(connection, client, route, password, result)
    checks = result['decfloat_array_checks'] = []
    from decimal import Decimal
    from pgadmin.cdeadmin.sdk.relational import RelationalClientError

    def sql(handle, source):
        with handle.cursor() as cursor:
            cursor.execute(source)
            return cursor.fetchall() if cursor.description else []

    def equivalent(actual, expected):
        assert len(actual) == len(expected)
        for left, right in zip(actual, expected):
            assert len(left) == len(right)
            for actual_value, expected_value in zip(left, right):
                assert actual_value.compare_total(Decimal(expected_value)) == 0

    for precision in (16, 34):
        admin = client.open_session({'route': route})
        table, view = f'GDA_{precision}', f'GDAV_{precision}'
        try:
            sql(admin, f'CREATE TABLE {table} (ID INTEGER PRIMARY KEY, '
                f'A DECFLOAT({precision})[-1:0,2:3])')
            client.control_transaction(admin, 'commit')
            sql(admin, f'CREATE VIEW {view} AS SELECT ID, A FROM {table}')
            client.control_transaction(admin, 'commit')
        finally:
            client.close_session(admin)
        values = ['-0', 'NaN', '-NaN', 'sNaN', '-sNaN', 'Infinity',
                  '-Infinity', '1234567890123456' if precision == 16 else
                  '1234567890123456789012345678901234',
                  '1e-398' if precision == 16 else '1e-6176',
                  '9.999999999999999e384' if precision == 16 else
                  '9.999999999999999999999999999999999e6144']
        for kind, name in (('table', table), ('view', view)):
            for action in ('commit', 'rollback'):
                for index, value in enumerate(values):
                    handle = client.open_session({'route': route})
                    observer = client.open_session({'route': route})
                    case = f'{precision}:{kind}:{action}:{value}'
                    key = index + (100 if kind == 'view' else 0)
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
                        assert column['array_spec']['precision'] == precision
                        assert column['array_spec'][
                            'element_kind'] == 'decfloat'
                        original = [[value, '1'], ['-0', '2']]
                        apply('insert', {'values': {'ID': key, 'A': original},
                                         'options': {'identity_token': initial[
                                             'insert_identity_token']}})
                        current = page()
                        json.dumps(current)
                        row = next(row for row in current['rows']
                                   if row['values']['ID'] == key)
                        equivalent(sql(handle, f'SELECT A FROM {table} '
                                       f'WHERE ID={key}')[0][0], original)
                        changed = list(reversed(original))
                        apply('update', {'selector': {'identity_token': row[
                            'identity_token']}, 'changes': {'A': changed}})
                        equivalent(sql(handle, f'SELECT A FROM {table} '
                                       f'WHERE ID={key}')[0][0], changed)
                        for invalid in ('1e385' if precision == 16 else
                                        '1e6145', 'not-a-number'):
                            current = page()
                            row = next(row for row in current['rows']
                                       if row['values']['ID'] == key)
                            try:
                                apply('update', {'selector': {'identity_token':
                                      row['identity_token']}, 'changes': {
                                          'A': [[invalid, '1'], ['0', '2']]}})
                            except RelationalClientError:
                                pass
                            else:
                                raise AssertionError('Invalid array accepted')
                        assert sql(observer, f'SELECT A FROM {table} '
                                   f'WHERE ID={key}') == []
                        client.control_transaction(observer, 'rollback')
                        client.control_transaction(handle, action)
                        observed = sql(observer, f'SELECT A FROM {table} '
                                       f'WHERE ID={key}')
                        if action == 'commit':
                            equivalent(observed[0][0], changed)
                            current = page()
                            row = next(row for row in current['rows']
                                       if row['values']['ID'] == key)
                            apply('delete', {'selector': {
                                'identity_token': row['identity_token']}})
                            client.control_transaction(handle, 'commit')
                            client.control_transaction(observer, 'rollback')
                            assert sql(observer, f'SELECT A FROM {table} '
                                       f'WHERE ID={key}') == []
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
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; preserve previous evidence')
    result = base.run(extra_checks=verify)
    checks = result.get('decfloat_array_checks', [])
    result['complete'] = bool(result['complete'] and not result['failures'] and
                              len(checks) == 80)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'complete': result['complete'],
                      'failures': result['failures']}))
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

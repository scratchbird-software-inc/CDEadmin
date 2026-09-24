#!/usr/bin/env python3
"""Native temporal grid transport with independent transaction observers."""
import argparse
import json
from pathlib import Path

if __package__:
    from . import cdeadmin_firebird_views_gate as base
else:
    import cdeadmin_firebird_views_gate as base


def verify(connection, client, route, password, result):
    from pgadmin.cdeadmin.sdk.relational import RelationalClientError
    checks = result['temporal_grid_checks'] = []
    admin = client.open_session({'route': route})

    def sql(handle, source, params=()):
        with handle.cursor() as cursor:
            cursor.execute(source, params)
            return cursor.fetchall() if cursor.description else []

    def wire(row):
        from pgadmin.cdeadmin.providers.firebird.grid_values import (
            normalize_value,
        )
        return tuple(normalize_value(value) for value in row)

    def observe():
        handle = client.open_session({'route': route})
        try:
            return [wire(row) for row in sql(
                handle, 'SELECT D, T, TS FROM GT_BASE ORDER BY ID')]
        finally:
            client.close_session(handle)

    try:
        sql(admin, 'CREATE TABLE GT_BASE (ID INTEGER GENERATED ALWAYS AS '
            'IDENTITY PRIMARY KEY, D DATE, T TIME, TS TIMESTAMP)')
        client.control_transaction(admin, 'commit')
        sql(admin, 'CREATE VIEW GT_VIEW AS SELECT * FROM GT_BASE')
        client.control_transaction(admin, 'commit')
        examples = [
            ('2024-02-29', '23:59:59.9999',
             '2024-02-29 23:59:59.9999'),
            ('0001-01-01', '00:00:00', '0001-01-01 00:00:00'),
            ('9999-12-31', '12:34:56.1234',
             '9999-12-31 12:34:56.1234'),
            (None, None, None),
        ]
        for kind, name in (('table', 'GT_BASE'), ('view', 'GT_VIEW')):
            for action in ('commit', 'rollback'):
                for index, example in enumerate(examples):
                    handle = client.open_session({'route': route})
                    case = f'{kind}:{action}:{index}'
                    request = {'_provider_route': route, 'session_id': case,
                               'resource_kind': kind, 'target_resource': {
                                   'resource_kind': kind,
                                   'display_path': [name]}}
                    try:
                        before = observe()
                        page = base.ADMINISTRATION.read_rows(
                            client, request, connection=handle)
                        assert [c['input_kind'] for c in page['columns']] == [
                            'integer', 'text', 'text', 'text']
                        assert [c['native_type'] for c in page['columns']] == [
                            'INTEGER', 'DATE', 'TIME', 'TIMESTAMP']
                        plan = base.ADMINISTRATION.plan({
                            **request, 'operation_id': 'insert', 'draft': {
                                'values': dict(zip(('D', 'T', 'TS'), example)),
                                'options': {'identity_token': page[
                                    'insert_identity_token']}}})
                        base.ADMINISTRATION.apply(
                            client, plan, connection=handle)
                        page = base.ADMINISTRATION.read_rows(
                            client, request, connection=handle)
                        row = page['rows'][-1]
                        assert tuple(row['values'][key]
                                     for key in ('D', 'T', 'TS')) == example
                        assert observe() == before
                        changes = {'D': '2000-02-29', 'T': '01:02:03.0001',
                                   'TS': '2000-02-29 01:02:03.0001'}
                        plan = base.ADMINISTRATION.plan({
                            **request, 'operation_id': 'update', 'draft': {
                                'selector': {'identity_token': row[
                                    'identity_token']}, 'changes': changes}})
                        base.ADMINISTRATION.apply(
                            client, plan, connection=handle)
                        page = base.ADMINISTRATION.read_rows(
                            client, request, connection=handle)
                        assert {key: page['rows'][-1]['values'][key]
                                for key in changes} == changes
                        assert observe() == before
                        denied = []
                        for invalid in ({'D': '1900-02-29'},
                                        {'T': '25:00:00'},
                                        {'TS': '2000-02-29 01:02:03.000001'}):
                            page = base.ADMINISTRATION.read_rows(
                                client, request, connection=handle)
                            transaction = handle.main_transaction.info.id
                            plan = base.ADMINISTRATION.plan({
                                **request, 'operation_id': 'update', 'draft': {
                                    'selector': {'identity_token': page[
                                        'rows'][-1]['identity_token']},
                                    'changes': invalid}})
                            try:
                                base.ADMINISTRATION.apply(
                                    client, plan, connection=handle)
                            except RelationalClientError:
                                denied.append(next(iter(invalid)))
                            else:
                                raise AssertionError(
                                    'Invalid temporal value accepted')
                            assert handle.main_transaction.info.id == (
                                transaction)
                            page = base.ADMINISTRATION.read_rows(
                                client, request, connection=handle)
                            assert {key: page['rows'][-1]['values'][key]
                                    for key in changes} == changes
                        client.control_transaction(handle, action)
                        expected = (before + [tuple(changes.values())]
                                    if action == 'commit' else before)
                        assert observe() == expected
                        checks.append({'case': case, 'passed': True,
                                       'invalid_values_rejected': denied})
                    except Exception as exc:
                        checks.append({'case': case, 'passed': False})
                        result['failures'].append({
                            'case': case, 'message': str(exc).replace(
                                password, '<redacted>')})
                    finally:
                        client.close_session(handle)
    finally:
        client.close_session(admin)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; preserve previous evidence')
    result = base.run(extra_checks=verify)
    checks = result.get('temporal_grid_checks', [])
    result['complete'] = (result['complete'] and len(checks) == 16 and
                          all(check['passed'] for check in checks))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'complete': result['complete'],
                      'failures': result['failures']}))
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

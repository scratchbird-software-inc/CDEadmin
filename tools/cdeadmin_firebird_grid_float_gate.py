#!/usr/bin/env python3
"""Qualify native approximate numeric grid inputs without browser rounding."""
import argparse
import json
from pathlib import Path
import struct

if __package__:
    from . import cdeadmin_firebird_views_gate as base
    from .cdeadmin_firebird_grid_binary_gate import provider_for
else:
    import cdeadmin_firebird_views_gate as base
    from cdeadmin_firebird_grid_binary_gate import provider_for


def verify(connection, client, route, password, result):
    from pgadmin.cdeadmin.sdk.relational import RelationalClientError
    checks = result['float_grid_checks'] = []
    admin = client.open_session({'route': route})

    def sql(handle, source):
        with handle.cursor() as cursor:
            cursor.execute(source)
            return cursor.fetchall() if cursor.description else []

    def observe():
        handle = client.open_session({'route': route})
        try:
            return sql(handle, 'SELECT F, D FROM GFL_BASE ORDER BY ID')
        finally:
            client.close_session(handle)

    def encode(value, field):
        return None if value is None else {
            'encoding': 'float32' if field == 'F' else 'float64',
            'data': value}

    try:
        sql(admin, 'CREATE TABLE GFL_BASE (ID INTEGER GENERATED ALWAYS AS '
            'IDENTITY PRIMARY KEY, F FLOAT, D DOUBLE PRECISION)')
        client.control_transaction(admin, 'commit')
        sql(admin, 'CREATE VIEW GFL_VIEW AS SELECT * FROM GFL_BASE')
        client.control_transaction(admin, 'commit')
        examples = [('0.1', '0.1'), ('3.4028234663852886e38',
                                     '1.7976931348623157e308'),
                    ('1.1754943508222875e-38', '2.2250738585072014e-308'),
                    ('1.401298464324817e-45', '4.9406564584124654e-324'),
                    ('-0.0', '-0.0'), (None, None)]
        for kind, name in (('table', 'GFL_BASE'), ('view', 'GFL_VIEW')):
            for action in ('commit', 'rollback'):
                for index, example in enumerate(examples):
                    case = f'{kind}:{action}:{index}'
                    handle = client.open_session({'route': route})
                    request = {'_provider_route': route, 'session_id': case,
                               'resource_kind': kind, 'target_resource': {
                                   'resource_kind': kind,
                                   'display_path': [name]}}
                    try:
                        before = observe()
                        page = base.ADMINISTRATION.read_rows(
                            client, request, connection=handle)
                        assert [c['input_kind'] for c in page['columns']] == [
                            'integer', 'float32', 'float64']
                        assert [c['native_type'] for c in page['columns']] == [
                            'INTEGER', 'FLOAT', 'DOUBLE PRECISION']
                        plan = base.ADMINISTRATION.plan({
                            **request, 'operation_id': 'insert', 'draft': {
                                'values': {key: encode(value, key)
                                           for key, value in zip(
                                               ('F', 'D'), example)},
                                'options': {'identity_token': page[
                                    'insert_identity_token']}}})
                        base.ADMINISTRATION.apply(
                            client, plan, connection=handle)
                        page = base.ADMINISTRATION.read_rows(
                            client, request, connection=handle)
                        row = page['rows'][-1]
                        expected = (tuple(None for _ in example)
                                    if example[0] is None else (
                                        struct.unpack('f', struct.pack(
                                            'f', float(example[0])))[0],
                                        float(example[1])))
                        for field, value in zip(('F', 'D'), expected):
                            actual = row['values'][field]
                            assert actual is None or isinstance(actual, str)
                            actual = None if actual is None else float(actual)
                            assert actual == value, (field, actual, value)
                            if value is not None:
                                assert struct.pack('d', actual) == struct.pack(
                                    'd', value)
                        assert observe() == before
                        changes = {'F': '-1.25', 'D': '1.2345678901234567'}
                        plan = base.ADMINISTRATION.plan({
                            **request, 'operation_id': 'update', 'draft': {
                                'selector': {'identity_token': row[
                                    'identity_token']}, 'changes': {
                                        key: encode(value, key) for key, value
                                        in changes.items()}}})
                        base.ADMINISTRATION.apply(
                            client, plan, connection=handle)
                        for invalid in ({'F': '1e100'}, {'D': '1e400'},
                                        {'F': '1e-100'}, {'D': '1e-400'}):
                            page = base.ADMINISTRATION.read_rows(
                                client, request, connection=handle)
                            transaction = handle.main_transaction.info.id
                            try:
                                plan = base.ADMINISTRATION.plan({
                                    **request, 'operation_id': 'update',
                                    'draft': {
                                        'selector': {'identity_token': page[
                                            'rows'][-1]['identity_token']},
                                        'changes': {key: encode(value, key)
                                                    for key, value
                                                    in invalid.items()}}})
                                base.ADMINISTRATION.apply(
                                    client, plan, connection=handle)
                            except RelationalClientError as exc:
                                assert ('range' in str(exc) or
                                        'OverflowError' in str(exc) or
                                        getattr(exc, 'gds_codes', ())), (
                                            str(exc))
                                assert not getattr(
                                    exc, 'task_rollback_unconfirmed', False)
                            else:
                                raise AssertionError('Overflow was admitted')
                            assert handle.main_transaction.info.id == (
                                transaction)
                            page = base.ADMINISTRATION.read_rows(
                                client, request, connection=handle)
                            actual = tuple(float(page['rows'][-1]['values'][k])
                                           for k in changes)
                            assert actual == tuple(float(v) for v in
                                                   changes.values())
                        assert observe() == before
                        client.control_transaction(handle, action)
                        assert observe() == (before + [tuple(
                            float(v) for v in changes.values())]
                            if action == 'commit' else before)
                        checks.append({'case': case, 'passed': True})
                    except Exception as exc:
                        checks.append({'case': case, 'passed': False})
                        result['failures'].append({
                            'case': case, 'message': str(exc).replace(
                                password, '<redacted>')})
                    finally:
                        client.close_session(handle)
    finally:
        client.close_session(admin)
    verify_provider(client, route, password, result)


def verify_provider(client, route, password, result):
    provider = provider_for(client, result)
    checks = result['provider_float_checks'] = []
    for kind, name in (('table', 'GFL_BASE'), ('view', 'GFL_VIEW')):
        for action in ('commit', 'rollback'):
            case = f'provider:{kind}:{action}'
            sid = provider.open_session({'route': route})['session_id']
            observer = client.open_session({'route': route})

            def observe():
                with observer.cursor() as cursor:
                    cursor.execute('SELECT F, D FROM GFL_BASE ORDER BY ID')
                    rows = cursor.fetchall()
                client.control_transaction(observer, 'rollback')
                return rows

            request = {'_provider_route': route, 'session_id': sid,
                       'resource_kind': kind, 'target_resource': {
                           'resource_kind': kind, 'display_path': [name]}}
            try:
                before = observe()
                page = provider.read_visual_admin_rows(request)
                values = {'F': {'encoding': 'float32', 'data': '-0.0'},
                          'D': {'encoding': 'float64',
                                'data': '1.7976931348623157e308'}}
                payload = {**request, 'operation_id': 'insert', 'draft': {
                    'values': values, 'options': {'identity_token': page[
                        'insert_identity_token']}}}
                assert provider.validate_visual_admin(payload)['valid']
                plan = provider.plan_visual_admin(payload)
                assert plan['state'] == 'ready'
                json.dumps(plan)
                receipt = provider.apply_visual_admin({
                    'session_id': sid, 'plan_id': plan['plan_id'],
                    'plan_digest': plan['plan_digest']})
                assert receipt['provider_result']['staged_in_provider_session']
                page = json.loads(json.dumps(provider.read_visual_admin_rows(
                    request)))
                assert [col['input_kind'] for col in page['columns']] == [
                    'integer', 'float32', 'float64']
                assert page['rows'][-1]['values']['F'] == '-0.0'
                assert page['rows'][-1]['values']['D'] == repr(
                    1.7976931348623157e308)
                assert observe() == before
                provider.control_transaction({'session_id': sid,
                                              'action': action})
                expected = (before + [(-0.0, 1.7976931348623157e308)]
                            if action == 'commit' else before)
                assert observe() == expected
                checks.append({'case': case, 'passed': True})
            except Exception as exc:
                checks.append({'case': case, 'passed': False})
                result['failures'].append({
                    'case': case, 'message': str(exc).replace(
                        password, '<redacted>')})
            finally:
                provider.close_session({'session_id': sid})
                client.close_session(observer)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; preserve previous evidence')
    result = base.run(extra_checks=verify)
    checks = result.get('float_grid_checks', [])
    provider_checks = result.get('provider_float_checks', [])
    result['complete'] = (result['complete'] and len(checks) == 24 and
                          all(check['passed'] for check in checks) and
                          len(provider_checks) == 4 and
                          all(check['passed'] for check in provider_checks))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'complete': result['complete'],
                      'failures': result['failures']}))
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""Fixed/variable OCTETS array native fidelity and transaction finality."""
import argparse
import json
from itertools import product
from pathlib import Path

if __package__:
    from . import cdeadmin_firebird_character_array_buffers_gate as characters
else:
    import cdeadmin_firebird_character_array_buffers_gate as characters

base = characters.base


def verify(connection, client, route, password, result, *, binary_only=False):
    if not binary_only:
        characters.verify(connection, client, route, password, result,
                          cross_charset=True)
    from pgadmin.cdeadmin.providers.firebird.temporal_arrays import cursor
    from pgadmin.cdeadmin.providers.firebird.grid_values import normalize_value
    from pgadmin.cdeadmin.sdk.relational import RelationalClientError
    checks = result['octets_array_checks'] = []

    def sql(handle, source):
        with cursor(handle) as query:
            query.execute(source)
            return query.fetchall() if query.description else []

    for width, native in product((8, 256), ('CHAR', 'VARCHAR')):
        table, view = f'OCTA_{width}_{native}', f'OCTAV_{width}_{native}'
        sql(connection, f'CREATE TABLE {table}(ID INTEGER PRIMARY KEY, '
            f'A {native}({width})[-1:0,2:3] CHARACTER SET OCTETS)')
        connection.commit()
        sql(connection, f'CREATE VIEW {view} AS SELECT ID,A FROM {table}')
        connection.commit()
        for kind, name in (('table', table), ('view', view)):
            for action in ('commit', 'rollback'):
                handle = client.open_session({'route': route})
                observer = client.open_session({'route': route})
                case = f'{native}:{width}:{kind}:{action}'
                request = {'_provider_route': route, 'session_id': case,
                           'resource_kind': kind, 'target_resource': {
                               'resource_kind': kind, 'display_path': [name]}}

                def page():
                    return base.ADMINISTRATION.read_rows(
                        client, request, connection=handle)

                def apply(operation, draft):
                    plan = base.ADMINISTRATION.plan({
                        **request, 'operation_id': operation, 'draft': draft})
                    base.ADMINISTRATION.apply(client, plan, connection=handle)

                def leaves(session):
                    return sql(session, f'SELECT A[-1,2],A[-1,3],'
                               f'A[0,2],A[0,3] FROM {table}')

                try:
                    original = [[bytes(range(width)), b' \0\xff \0'],
                                [b'', bytes(reversed(range(width)))]]
                    expected = [[item.ljust(width, b'\0') if native == 'CHAR'
                                 else item for item in row]
                                for row in original]
                    initial = page()
                    column = next(c for c in initial['columns']
                                  if c['name'] == 'A')
                    assert column['input_kind'] == 'array'
                    assert column['array_spec']['element_kind'] == 'binary'
                    assert column['array_spec']['length'] == width
                    assert column['array_spec']['charset'] == 'OCTETS'
                    assert column['array_spec']['type'] == (
                        14 if native == 'CHAR' else 37)
                    apply('insert', {'values': {
                        'ID': 1, 'A': normalize_value(original)},
                                     'options': {'identity_token': initial[
                                         'insert_identity_token']}})
                    assert leaves(handle) == [tuple(sum(expected, []))]
                    assert page()['rows'][0]['values']['A'] == normalize_value(
                        expected)
                    for dialect in (1, 3):
                        query = client._query_cursor(handle, {
                            'output_policy': {'client_sql_dialect': dialect}})
                        try:
                            query.execute(f'SELECT ID,A FROM {table}')
                            assert query.fetchall() == [(1, expected)]
                        finally:
                            query.close()
                    changed = list(reversed(original))
                    expected = list(reversed(expected))
                    row = page()['rows'][0]
                    apply('update', {'selector': {'identity_token': row[
                        'identity_token']}, 'changes': {
                            'A': normalize_value(changed)}})
                    assert leaves(handle) == [tuple(sum(expected, []))]
                    for bad in ('text', None, b'x' * (width + 1)):
                        row = page()['rows'][0]
                        try:
                            invalid = normalize_value([[bad, b''], [b'', b'']])
                            apply('update', {'selector': {
                                'identity_token': row['identity_token']},
                                'changes': {'A': invalid}})
                        except RelationalClientError:
                            pass
                        else:
                            raise AssertionError('Invalid OCTETS accepted')
                        assert leaves(handle) == [tuple(sum(expected, []))]
                    row = page()['rows'][0]
                    apply('update', {'selector': {'identity_token': row[
                        'identity_token']}, 'changes': {'A': None}})
                    row = page()['rows'][0]
                    assert row['values']['A'] is None
                    apply('update', {'selector': {'identity_token': row[
                        'identity_token']}, 'changes': {
                            'A': normalize_value(changed)}})
                    assert leaves(observer) == []
                    client.control_transaction(observer, 'rollback')
                    client.control_transaction(handle, action)
                    observed = leaves(observer)
                    assert observed == ([tuple(sum(expected, []))]
                                        if action == 'commit' else [])
                    if action == 'commit':
                        row = page()['rows'][0]
                        apply('delete', {'selector': {'identity_token': row[
                            'identity_token']}})
                        client.control_transaction(handle, 'commit')
                        client.control_transaction(observer, 'rollback')
                        assert leaves(observer) == []
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
    parser.add_argument('--binary-only', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; preserve prior evidence')
    result = base.run(extra_checks=lambda *values: verify(
        *values, binary_only=args.binary_only))
    result['binary_only'] = args.binary_only
    result['complete'] = bool(result['complete'] and not result['failures'] and
                              len(result.get('octets_array_checks', [])) == 16)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'complete': result['complete'],
                      'failures': result['failures']}))
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""Native character-array write fidelity and transaction/savepoint checks."""
import argparse
import json
from pathlib import Path

if __package__:
    from . import cdeadmin_firebird_temporal_arrays_gate as temporal
else:
    import cdeadmin_firebird_temporal_arrays_gate as temporal

base = temporal.base


def verify(connection, client, route, password, result, *,
           cross_charset=False, character_only=False):
    if not character_only:
        temporal.verify(connection, client, route, password, result)
    checks = result['character_array_buffer_checks'] = []
    from pgadmin.cdeadmin.sdk.relational import RelationalClientError

    def sql(handle, source):
        with handle.cursor() as cursor:
            cursor.execute(source)
            return cursor.fetchall() if cursor.description else []

    for number, (kind, charset) in enumerate([
            ('CHAR', 'ASCII'), ('VARCHAR', 'ASCII'),
            ('CHAR', 'UTF8'), ('VARCHAR', 'UTF8')]):
        table, view = f'GCAB_{number}', f'GCABV_{number}'
        sql(connection, f'CREATE TABLE {table}(ID INT PRIMARY KEY, '
            f'A {kind}(8)[-1:0,2:3] CHARACTER SET {charset})')
        connection.commit()
        sql(connection, f'CREATE VIEW {view} AS SELECT ID,A FROM {table}')
        connection.commit()
        profile = dict(route, charset='UTF8' if cross_charset else charset)
        for resource, name in (('table', table), ('view', view)):
            for action in ('commit', 'rollback'):
                case = f'{kind}:{charset}:{resource}:{action}'
                handle = client.open_session({'route': profile})
                observer = client.open_session({'route': profile})
                request = {'_provider_route': profile, 'session_id': case,
                           'resource_kind': resource, 'target_resource': {
                               'resource_kind': resource,
                               'display_path': [name]}}

                def page():
                    # Keep native diagnostics if the stock ARRAY decoder fails.
                    sql(handle, f'SELECT A FROM {name}')
                    return base.ADMINISTRATION.read_rows(
                        client, request, connection=handle)

                def apply(operation, draft):
                    plan = base.ADMINISTRATION.plan({
                        **request, 'operation_id': operation, 'draft': draft})
                    base.ADMINISTRATION.apply(client, plan, connection=handle)

                def leaves(session):
                    # Scalar subscripts are an independent native oracle;
                    # never round-trip through the driver's array decoder.
                    return sql(session, f'SELECT A[-1,2], A[-1,3], '
                               f'A[0,2], A[0,3] FROM {table}')

                try:
                    special = 'é🐦' if charset == 'UTF8' else 'xy'
                    original = [['abcdefgh', 'x'], ['', special]]
                    expected = tuple(item.ljust(8) if kind == 'CHAR' else item
                                     for row in original for item in row)
                    initial = page()
                    apply('insert', {'values': {'ID': 1, 'A': original},
                                     'options': {'identity_token': initial[
                                         'insert_identity_token']}})
                    assert leaves(handle) == [expected], leaves(handle)
                    changed = [[special, ''], ['x', 'abcdefgh']]
                    row = page()['rows'][0]
                    apply('update', {'selector': {'identity_token': row[
                        'identity_token']}, 'changes': {'A': changed}})
                    expected = tuple(item.ljust(8) if kind == 'CHAR' else item
                                     for row in changed for item in row)
                    assert leaves(handle) == [expected], leaves(handle)
                    for bad in ('z' * 100, None) + (
                            ('a\0b',) if kind == 'VARCHAR' else ()):
                        row = page()['rows'][0]
                        try:
                            apply('update', {'selector': {
                                'identity_token': row['identity_token']},
                                'changes': {
                                    'A': [[bad, ''], ['', '']]}})
                        except RelationalClientError:
                            pass
                        else:
                            raise AssertionError('Lossy input accepted')
                        assert leaves(handle) == [expected]
                    assert leaves(observer) == []
                    client.control_transaction(observer, 'rollback')
                    client.control_transaction(handle, action)
                    assert leaves(observer) == (
                        [expected] if action == 'commit' else [])
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
    parser.add_argument('--cross-charset', action='store_true',
                        help='Use UTF8 attachments also for ASCII arrays')
    parser.add_argument('--character-only', action='store_true',
                        help='Target character checks plus base view gate')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; preserve previous evidence')
    result = base.run(extra_checks=lambda *values: verify(
        *values, cross_charset=args.cross_charset,
        character_only=args.character_only))
    result['cross_charset'] = args.cross_charset
    result['character_only'] = args.character_only
    result['complete'] = bool(result['complete'] and not result['failures']
                              and len(result.get(
                                  'character_array_buffer_checks', [])) == 16)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'complete': result['complete'],
                      'failures': result['failures']}))
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

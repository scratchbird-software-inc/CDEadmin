#!/usr/bin/env python3
"""Native multi-attachment grid conflict and task-savepoint qualification."""
import argparse
import itertools
import json
from pathlib import Path

if __package__:
    from . import cdeadmin_firebird_views_gate as base
else:
    import cdeadmin_firebird_views_gate as base


def verify(connection, client, route, password, result):
    from pgadmin.cdeadmin.sdk.relational import RelationalClientError
    from pgadmin.cdeadmin.providers.firebird.transaction_state import (
        observe_transaction,
    )
    checks = result['cross_attachment_checks'] = []
    bounded = {**route, 'transaction_lock_timeout': 0}
    admin = client.open_session({'route': bounded})

    def sql(handle, source, params=()):
        with handle.cursor() as cursor:
            cursor.execute(source, params)
            return cursor.fetchall() if cursor.description else []

    try:
        sql(admin, 'CREATE TABLE GF_BASE (ID INTEGER PRIMARY KEY, V INTEGER)')
        sql(admin, 'CREATE TABLE GF_SIDE (ID INTEGER PRIMARY KEY, V INTEGER)')
        client.control_transaction(admin, 'commit')
        sql(admin, 'CREATE VIEW GF_VIEW AS SELECT * FROM GF_BASE')
        client.control_transaction(admin, 'commit')
        cases = itertools.product(
            ('SNAPSHOT', 'READ_COMMITTED', 'READ_COMMITTED_RECORD_VERSION',
             'READ_COMMITTED_NO_RECORD_VERSION',
             'READ_COMMITTED_READ_CONSISTENCY'),
            (('table', 'GF_BASE'), ('view', 'GF_VIEW')),
            ('update', 'delete'),
            ('committed-update', 'committed-delete', 'locked-rollback',
             'locked-commit'))
        for row_id, case_values in enumerate(cases, 1):
            isolation, (kind, name), operation, competing = case_values
            reader = writer = observer = None
            case = ':'.join((isolation, kind, operation, competing))
            try:
                sql(admin, 'INSERT INTO GF_BASE VALUES (?, 1)', (row_id,))
                client.control_transaction(admin, 'commit')
                selected_route = {**bounded,
                                  'transaction_isolation': isolation}
                reader = client.open_session({'route': selected_route})
                writer = client.open_session({'route': bounded})
                request = {'_provider_route': selected_route,
                           'session_id': case, 'resource_kind': kind,
                           'target_resource': {'resource_kind': kind,
                                               'display_path': [name]},
                           'limit': 100}
                page = base.ADMINISTRATION.read_rows(
                    client, request, connection=reader)
                row = next(item for item in page['rows']
                           if item['values']['ID'] == row_id)
                sql(reader, 'INSERT INTO GF_SIDE VALUES (?, 7)', (row_id,))
                transaction = reader.main_transaction.info.id
                state = observe_transaction(reader)
                plan = base.ADMINISTRATION.plan({
                    **request, 'operation_id': operation, 'draft': {
                        'selector': {'identity_token': row['identity_token']},
                        'changes': {'V': 99}}})
                if competing == 'committed-delete':
                    sql(writer, 'DELETE FROM GF_BASE WHERE ID = ?', (row_id,))
                else:
                    sql(writer, 'UPDATE GF_BASE SET V = 2 WHERE ID = ?',
                        (row_id,))
                if not competing.startswith('locked-'):
                    client.control_transaction(writer, 'commit')
                try:
                    base.ADMINISTRATION.apply(client, plan, connection=reader)
                except RelationalClientError as exc:
                    codes = list(getattr(exc, 'gds_codes', ()))
                    assert ('exactly one row' in str(exc) or
                            set(codes) & {335544336, 335544345, 335544451}), (
                                str(exc), codes)
                    assert not getattr(
                        exc, 'task_rollback_unconfirmed', False)
                else:
                    raise AssertionError('Concurrent mutation was overwritten')
                assert reader.main_transaction.info.id == transaction
                assert sql(reader, 'SELECT V FROM GF_SIDE WHERE ID = ?',
                           (row_id,)) == [(7,)]
                if competing == 'locked-rollback':
                    client.control_transaction(writer, 'rollback')
                elif competing == 'locked-commit':
                    client.control_transaction(writer, 'commit')
                # The failed row operation must not prevent committing earlier
                # unrelated work or overwrite the other attachment's change.
                client.control_transaction(reader, 'commit')
                observer = client.open_session({'route': bounded})
                assert sql(observer, 'SELECT V FROM GF_SIDE WHERE ID = ?',
                           (row_id,)) == [(7,)]
                expected = ([] if competing == 'committed-delete' else
                            [(1,)] if competing == 'locked-rollback' else
                            [(2,)])
                assert sql(observer, 'SELECT V FROM GF_BASE WHERE ID = ?',
                           (row_id,)) == expected
                checks.append({'case': case, 'passed': True,
                               'native_status_codes': codes,
                               'transaction_state': state})
            except Exception as exc:
                checks.append({'case': case, 'passed': False})
                result['failures'].append({
                    'case': case, 'message': str(exc).replace(
                        password, '<redacted>')})
            finally:
                for handle in (observer, writer, reader):
                    if handle is not None:
                        client.close_session(handle)
    finally:
        client.close_session(admin)
    verify_serializable(client, bounded, password, result)


def verify_serializable(client, route, password, result):
    """Qualify table-stability conflicts separately from row snapshots."""
    checks = result['serializable_checks'] = []

    def sql(handle, source, params=()):
        with handle.cursor() as cursor:
            cursor.execute(source, params)
            return cursor.fetchall() if cursor.description else []

    cases = itertools.product((('table', 'GF_BASE'), ('view', 'GF_VIEW')),
                              ('update', 'delete'), ('commit', 'rollback'))
    for row_id, ((kind, name), operation, action) in enumerate(cases, 1001):
        reader = writer = observer = None
        case = ':'.join(('SERIALIZABLE', kind, operation, action))
        try:
            writer = client.open_session({'route': route})
            sql(writer, 'INSERT INTO GF_BASE VALUES (?, 1)', (row_id,))
            client.control_transaction(writer, 'commit')
            selected = {**route, 'transaction_isolation': 'SERIALIZABLE'}
            reader = client.open_session({'route': selected})
            request = {'_provider_route': selected, 'session_id': case,
                       'resource_kind': kind, 'limit': 500,
                       'target_resource': {'resource_kind': kind,
                                           'display_path': [name]}}
            page = base.ADMINISTRATION.read_rows(
                client, request, connection=reader)
            row = next(item for item in page['rows']
                       if item['values']['ID'] == row_id)
            sql(writer, 'INSERT INTO GF_SIDE VALUES (?, 7)', (row_id,))
            transaction = writer.main_transaction.info.id
            try:
                sql(writer, 'UPDATE GF_BASE SET V = 2 WHERE ID = ?', (row_id,))
            except Exception as exc:
                codes = list(base.status_codes(exc))
                assert set(codes) & {335544336, 335544345, 335544451}, codes
            else:
                raise AssertionError('Table-stability lock was bypassed')
            assert writer.main_transaction.info.id == transaction
            assert sql(writer, 'SELECT V FROM GF_SIDE WHERE ID = ?',
                       (row_id,)) == [(7,)]
            client.control_transaction(writer, 'commit')
            client.close_session(writer)
            writer = None
            plan = base.ADMINISTRATION.plan({
                **request, 'operation_id': operation, 'draft': {
                    'selector': {'identity_token': row['identity_token']},
                    'changes': {'V': 99}}})
            base.ADMINISTRATION.apply(client, plan, connection=reader)
            client.control_transaction(reader, action)
            client.close_session(reader)
            reader = None
            observer = client.open_session({'route': route})
            expected = ([(1,)] if action == 'rollback' else
                        [] if operation == 'delete' else [(99,)])
            assert sql(observer, 'SELECT V FROM GF_BASE WHERE ID = ?',
                       (row_id,)) == expected
            assert sql(observer, 'SELECT V FROM GF_SIDE WHERE ID = ?',
                       (row_id,)) == [(7,)]
            checks.append({'case': case, 'passed': True,
                           'native_status_codes': codes})
        except Exception as exc:
            checks.append({'case': case, 'passed': False})
            result['failures'].append({
                'case': case, 'message': str(exc).replace(
                    password, '<redacted>')})
        finally:
            for handle in (observer, writer, reader):
                if handle is not None:
                    client.close_session(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; preserve previous evidence')
    result = base.run(extra_checks=verify)
    checks = result.get('cross_attachment_checks', [])
    serializable = result.get('serializable_checks', [])
    result['complete'] = (result['complete'] and len(checks) == 80 and
                          all(check['passed'] for check in checks) and
                          len(serializable) == 8 and
                          all(check['passed'] for check in serializable))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'complete': result['complete'],
                      'failures': result['failures']}))
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

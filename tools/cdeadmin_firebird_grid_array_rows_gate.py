#!/usr/bin/env python3
"""Array-bearing relation grid mutations and stale-array conflict gates."""
import argparse
import json
from pathlib import Path

if __package__:
    from . import cdeadmin_firebird_views_gate as base
    from .cdeadmin_firebird_grid_binary_gate import provider_for
else:
    import cdeadmin_firebird_views_gate as base
    from cdeadmin_firebird_grid_binary_gate import provider_for


def verify(connection, client, route, password, result):
    from pgadmin.cdeadmin.sdk.relational import RelationalClientError
    checks = result['array_row_checks'] = []
    route = {**route, 'transaction_lock_timeout': 0,
             'transaction_isolation': 'READ_COMMITTED_RECORD_VERSION'}
    admin = client.open_session({'route': route})

    def sql(handle, source, parameters=()):
        with handle.cursor() as cursor:
            cursor.execute(source, parameters)
            return cursor.fetchall() if cursor.description else None

    def observe():
        handle = client.open_session({'route': route})
        try:
            return sql(handle, 'SELECT A, B, V FROM GAR_BASE ORDER BY ID')
        finally:
            client.close_session(handle)

    try:
        sql(admin, 'CREATE TABLE GAR_BASE (ID INTEGER GENERATED ALWAYS AS '
            'IDENTITY PRIMARY KEY, A INTEGER[0:2], '
            'B INTEGER[-1:0,2:3], V INTEGER)')
        sql(admin, 'CREATE TABLE GAR_SIDE (ID INTEGER PRIMARY KEY, V INTEGER)')
        client.control_transaction(admin, 'commit')
        sql(admin, 'CREATE VIEW GAR_VIEW AS SELECT ID, A, B, V FROM GAR_BASE')
        client.control_transaction(admin, 'commit')
        for kind, name in (('table', 'GAR_BASE'), ('view', 'GAR_VIEW')):
            for action in ('commit', 'rollback'):
                for initial in ('array', 'null'):
                    handle = client.open_session({'route': route})
                    case = f'{kind}:{action}:{initial}'
                    request = {'_provider_route': route, 'session_id': case,
                               'resource_kind': kind, 'target_resource': {
                                   'resource_kind': kind,
                                   'display_path': [name]}}
                    try:
                        before = observe()
                        page = base.ADMINISTRATION.read_rows(
                            client, request, connection=handle)
                        values = {'A': [1, 2, 3] if initial == 'array'
                                  else None,
                                  'B': [[4, 5], [6, 7]] if initial == 'array'
                                  else None, 'V': 1}
                        plan = base.ADMINISTRATION.plan({
                            **request, 'operation_id': 'insert', 'draft': {
                                'values': values, 'options': {
                                    'identity_token': page[
                                        'insert_identity_token']}}})
                        base.ADMINISTRATION.apply(
                            client, plan, connection=handle)
                        page = base.ADMINISTRATION.read_rows(
                            client, request, connection=handle)
                        json.dumps(page)
                        row = page['rows'][-1]
                        assert {k: row['values'][k] for k in values} == values
                        changed = {'A': [9, 8, 7], 'B': [[6, 5], [4, 3]],
                                   'V': 2}
                        plan = base.ADMINISTRATION.plan({
                            **request, 'operation_id': 'update', 'draft': {
                                'selector': {'identity_token': row[
                                    'identity_token']}, 'changes': changed}})
                        base.ADMINISTRATION.apply(
                            client, plan, connection=handle)
                        page = base.ADMINISTRATION.read_rows(
                            client, request, connection=handle)
                        assert {k: page['rows'][-1]['values'][k]
                                for k in changed} == changed
                        assert observe() == before
                        if initial == 'null':
                            plan = base.ADMINISTRATION.plan({
                                **request, 'operation_id': 'delete', 'draft': {
                                    'selector': {'identity_token': page[
                                        'rows'][-1]['identity_token']}}})
                            base.ADMINISTRATION.apply(
                                client, plan, connection=handle)
                        client.control_transaction(handle, action)
                        assert observe() == (before + [tuple(changed.values())]
                                             if action == 'commit' and initial
                                             == 'array' else before)
                        checks.append({'case': case, 'passed': True})
                    except Exception as exc:
                        result['failures'].append({
                            'case': case, 'message': str(exc).replace(
                                password, '<redacted>')})
                    finally:
                        client.close_session(handle)
        for kind, name in (('table', 'GAR_BASE'), ('view', 'GAR_VIEW')):
            for writer_kind in ('same-attachment', 'other-attachment'):
                for operation in ('update', 'delete'):
                    handle = writer = None
                    case = f'{kind}:{writer_kind}:{operation}'
                    try:
                        row_id = sql(admin, 'INSERT INTO GAR_BASE (A, B, V) '
                                     'VALUES (?, ?, 1) RETURNING ID',
                                     ([1, 2, 3], [[4, 5], [6, 7]]))[0][0]
                        client.control_transaction(admin, 'commit')
                        handle = client.open_session({'route': route})
                        sql(handle, 'INSERT INTO GAR_SIDE VALUES (?, 7)',
                            (row_id,))
                        local = writer_kind == 'same-attachment'
                        if local:
                            sql(handle, 'UPDATE GAR_BASE SET V = 2 '
                                'WHERE ID = ?', (row_id,))
                        request = {'_provider_route': route,
                                   'session_id': case,
                                   'resource_kind': kind, 'target_resource': {
                                       'resource_kind': kind,
                                       'display_path': [name]}}
                        page = base.ADMINISTRATION.read_rows(
                            client, request, connection=handle)
                        row = next(row for row in page['rows']
                                   if row['values']['ID'] == row_id)
                        plan = base.ADMINISTRATION.plan({
                            **request, 'operation_id': operation, 'draft': {
                                'selector': {'identity_token': row[
                                    'identity_token']}, 'changes': {'V': 99}}})
                        transaction = handle.main_transaction.info.id
                        writer = (handle if local else
                                  client.open_session({'route': route}))
                        sql(writer, 'UPDATE GAR_BASE SET A = ? WHERE ID = ?',
                            ([8, 8, 8], row_id))
                        if not local:
                            client.control_transaction(writer, 'commit')
                        try:
                            base.ADMINISTRATION.apply(
                                client, plan, connection=handle)
                        except RelationalClientError as exc:
                            assert 'unchanged array row' in str(exc), str(exc)
                        else:
                            raise AssertionError('Changed array overwritten')
                        assert handle.main_transaction.info.id == transaction
                        assert sql(handle, 'SELECT V FROM GAR_SIDE WHERE '
                                   'ID = ?', (row_id,)) == [(7,)]
                        assert sql(handle, 'SELECT A, V FROM GAR_BASE WHERE '
                                   'ID = ?', (row_id,)) == [
                                       ([8, 8, 8], 2 if local else 1)]
                        client.control_transaction(handle, 'commit')
                        checks.append({'case': case, 'passed': True})
                    except Exception as exc:
                        result['failures'].append({
                            'case': case, 'message': str(exc).replace(
                                password, '<redacted>')})
                    finally:
                        if writer is not None and writer is not handle:
                            client.close_session(writer)
                        if handle is not None:
                            client.close_session(handle)
    finally:
        client.close_session(admin)
    verify_provider(client, route, password, result)
    verify_races(client, route, password, result)


def verify_races(client, route, password, result):
    """Commit a competitor specifically between array preflight and DML."""
    from pgadmin.cdeadmin.sdk.relational import RelationalClientError
    checks = result['array_race_checks'] = []

    def sql(handle, source, parameters=()):
        with handle.cursor() as cursor:
            cursor.execute(source, parameters)
            return cursor.fetchall() if cursor.description else None

    for isolation in ('SNAPSHOT', 'READ_COMMITTED_RECORD_VERSION'):
        for kind, name in (('table', 'GAR_BASE'), ('view', 'GAR_VIEW')):
            for operation in ('update', 'delete'):
                case = f'race:{isolation}:{kind}:{operation}'
                selected = {**route, 'transaction_isolation': isolation}
                reader = writer = None
                try:
                    writer = client.open_session({'route': route})
                    row_id = sql(writer, 'INSERT INTO GAR_BASE (A, B, V) '
                                 'VALUES (?, ?, 1) RETURNING ID',
                                 ([1, 2, 3], [[4, 5], [6, 7]]))[0][0]
                    client.control_transaction(writer, 'commit')
                    reader = client.open_session({'route': selected})
                    sql(reader, 'INSERT INTO GAR_SIDE VALUES (?, 7)',
                        (row_id,))
                    request = {'_provider_route': selected, 'session_id': case,
                               'resource_kind': kind, 'target_resource': {
                                   'resource_kind': kind,
                                   'display_path': [name]}}
                    page = base.ADMINISTRATION.read_rows(
                        client, request, connection=reader)
                    row = next(item for item in page['rows']
                               if item['values']['ID'] == row_id)
                    plan = base.ADMINISTRATION.plan({
                        **request, 'operation_id': operation, 'draft': {
                            'selector': {'identity_token': row[
                                'identity_token']}, 'changes': {'V': 99}}})
                    statement = plan['provider_payload']['compiled'][
                        'statements'][0]
                    state = {'guard_seen': False, 'writer_committed': False}

                    class RaceCursor:
                        def __init__(self, cursor):
                            self.native = cursor

                        def __getattr__(self, attr):
                            return getattr(self.native, attr)

                        def execute(self, source, parameters=()):
                            if source == statement['source']:
                                assert state['guard_seen']
                                sql(writer, 'UPDATE GAR_BASE SET A = ? '
                                    'WHERE ID = ?', ([8, 8, 8], row_id))
                                client.control_transaction(writer, 'commit')
                                state['writer_committed'] = True
                            returned = self.native.execute(source, parameters)
                            if source == statement['firebird_array_guard'][
                                    'source']:
                                state['guard_seen'] = True
                            return returned

                    class RaceConnection:
                        def __getattr__(self, attr):
                            return getattr(reader, attr)

                        def cursor(self):
                            return RaceCursor(reader.cursor())

                    transaction = reader.main_transaction.info.id
                    try:
                        base.ADMINISTRATION.apply(
                            client, plan, connection=RaceConnection())
                    except RelationalClientError as exc:
                        codes = set(getattr(exc, 'gds_codes', ()))
                        assert ('exactly one row' in str(exc) or
                                codes & {335544336, 335544345, 335544451}), (
                                    str(exc))
                        assert not getattr(
                            exc, 'task_rollback_unconfirmed', False)
                    else:
                        raise AssertionError(
                            'Post-preflight change overwritten')
                    assert all(state.values()), state
                    assert reader.main_transaction.info.id == transaction
                    assert sql(reader, 'SELECT V FROM GAR_SIDE WHERE ID = ?',
                               (row_id,)) == [(7,)]
                    client.control_transaction(reader, 'commit')
                    assert sql(writer, 'SELECT A, V FROM GAR_BASE '
                               'WHERE ID = ?',
                               (row_id,)) == [([8, 8, 8], 1)]
                    assert sql(writer, 'SELECT V FROM GAR_SIDE WHERE ID = ?',
                               (row_id,)) == [(7,)]
                    checks.append({'case': case, 'passed': True, **state})
                except Exception as exc:
                    result['failures'].append({
                        'case': case, 'message': str(exc).replace(
                            password, '<redacted>')})
                finally:
                    for handle in (writer, reader):
                        if handle is not None:
                            client.close_session(handle)


def verify_provider(client, route, password, result):
    provider = provider_for(client, result)
    checks = result['provider_array_checks'] = []
    for kind, name in (('table', 'GAR_BASE'), ('view', 'GAR_VIEW')):
        for action in ('commit', 'rollback'):
            case = f'provider:{kind}:{action}'
            sid = provider.open_session({'route': route})['session_id']
            observer = client.open_session({'route': route})

            def observe():
                with observer.cursor() as cursor:
                    cursor.execute('SELECT A, B, V FROM GAR_BASE ORDER BY ID')
                    rows = cursor.fetchall()
                client.control_transaction(observer, 'rollback')
                return rows

            request = {'_provider_route': route, 'session_id': sid,
                       'resource_kind': kind, 'target_resource': {
                           'resource_kind': kind, 'display_path': [name]}}

            def apply(operation, draft):
                payload = {**request, 'operation_id': operation,
                           'draft': draft}
                assert provider.validate_visual_admin(payload)['valid']
                plan = provider.plan_visual_admin(payload)
                assert plan['state'] == 'ready'
                json.dumps(plan)
                receipt = provider.apply_visual_admin({
                    'session_id': sid, 'plan_id': plan['plan_id'],
                    'plan_digest': plan['plan_digest']})
                assert receipt['provider_result']['staged_in_provider_session']

            try:
                before = observe()
                page = provider.read_visual_admin_rows(request)
                values = {'A': [1, 2, 3], 'B': [[4, 5], [6, 7]], 'V': 1}
                apply('insert', {'values': values, 'options': {
                    'identity_token': page['insert_identity_token']}})
                page = json.loads(json.dumps(provider.read_visual_admin_rows(
                    request)))
                row = page['rows'][-1]
                assert {k: row['values'][k] for k in values} == values
                changed = {'A': [3, 2, 1], 'B': [[7, 6], [5, 4]], 'V': 2}
                apply('update', {'changes': changed, 'selector': {
                    'identity_token': row['identity_token']}})
                page = provider.read_visual_admin_rows(request)
                assert {k: page['rows'][-1]['values'][k]
                        for k in changed} == changed
                assert observe() == before
                provider.control_transaction({'session_id': sid,
                                              'action': action})
                assert observe() == (before + [tuple(changed.values())]
                                     if action == 'commit' else before)
                checks.append({'case': case, 'passed': True})
            except Exception as exc:
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
    checks = result.get('array_row_checks', [])
    provider_checks = result.get('provider_array_checks', [])
    race_checks = result.get('array_race_checks', [])
    result['complete'] = (result['complete'] and len(checks) == 16 and
                          all(check['passed'] for check in checks) and
                          len(provider_checks) == 4 and
                          all(check['passed'] for check in provider_checks) and
                          len(race_checks) == 8 and
                          all(check['passed'] for check in race_checks))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'complete': result['complete'],
                      'failures': result['failures']}))
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""Native duplicate-row edits, exact original values and owner fencing."""
import argparse
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.cdeadmin_firebird_stream_gate import (
    _create_client, _route_arguments,
)
from tools.cdeadmin_firebird_local_fixture import run_local
from tools.cdeadmin_firebird_admin_mapping_gate import ADMINISTRATION
from pgadmin.cdeadmin.providers.firebird.temporal_arrays import cursor
from pgadmin.cdeadmin.providers.firebird import grid_array_identity
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def qualify(native, admin, route, accounts, evidence, root,
            embedded_mode=False):
    user, password = (('OWNED_LOCAL', None) if embedded_mode else
                      accounts['Srp'][0])
    if embedded_mode:
        route = {'attachment_mode': 'embedded', 'filesystem_root': str(root)}
    selected = dict(route, user=user, database=str(root / 'physical.fdb'))
    client = _create_client(SimpleNamespace(acquire_secret=None))
    connection = native.create_database(
        password=password, **_route_arguments(selected, native))
    client._connections.append(connection)
    policy = native.tpb(native.Isolation.READ_COMMITTED_RECORD_VERSION,
                        lock_timeout=0)
    connection.default_tpb = connection.main_transaction.default_tpb = policy
    checks = []

    def sql(handle, source, parameters=()):
        with cursor(handle) as query:
            query.execute(source, parameters)
            return query.fetchall() if query.description else None

    def request(name, kind='table'):
        return {'_provider_route': selected, 'session_id': 'physical-'+name,
                'resource_kind': kind, 'target_resource': {
                    'resource_kind': kind, 'display_path': [name]}}

    def page(name='DUPLICATES', kind='table'):
        return ADMINISTRATION.read_rows(client, request(name, kind),
                                        connection=connection)

    def plan(current, operation='update', name='DUPLICATES', kind='table'):
        return ADMINISTRATION.plan({
            **request(name, kind), 'operation_id': operation, 'draft': {
                'selector': {'identity_token':
                             current['rows'][0]['identity_token']},
                'changes': {'V': 9}}})

    def reset():
        if connection.main_transaction.is_active():
            connection.rollback()
        sql(connection, 'DELETE FROM DUPLICATES')
        for _ in range(2):
            sql(connection, 'INSERT INTO DUPLICATES VALUES(7,0,?,?,?)',
                [[1, 2], 'same', b'\0\xfforiginal'])
        connection.commit()

    try:
        if embedded_mode:
            protocol, pid = sql(
                connection, 'SELECT MON$REMOTE_PROTOCOL,MON$SERVER_PID '
                'FROM MON$ATTACHMENTS WHERE MON$ATTACHMENT_ID='
                'CURRENT_CONNECTION')[0]
            assert protocol is None and pid == os.getpid()
            connection.rollback()
            checks.append('same-process-embedded-attachment')
        sql(connection, 'CREATE TABLE DUPLICATES (V INTEGER, F DOUBLE '
            'PRECISION, A INTEGER[1:2], S VARCHAR(20) CHARACTER SET UTF8 '
            'COLLATE UNICODE_CI_AI, B BLOB SUB_TYPE -42)')
        sql(connection, 'CREATE TABLE SIDE_WORK(V INTEGER)')
        connection.commit()
        for source in ('CREATE VIEW DIRECT_VIEW AS SELECT * FROM DUPLICATES',
                       'CREATE VIEW NESTED_VIEW AS SELECT * FROM DIRECT_VIEW'):
            sql(connection, source)
            connection.commit()
        for kind, name in (('table', 'DUPLICATES'), ('view', 'DIRECT_VIEW'),
                           ('view', 'NESTED_VIEW')):
            for operation in ('update', 'delete'):
                reset()
                current = page(name, kind)
                assert current['identity_policy'] == (
                    'provider-native-db-key-and-original-values')
                assert [column['name'] for column in current['columns']] == [
                    'V', 'F', 'A', 'S', 'B']
                assert current['columns'][-1]['input_kind'] == 'binary'
                tokens = [row['identity_token'] for row in current['rows']]
                assert len(set(tokens)) == 2 and all(tokens)
                assert current['rows'][0]['values'] == (
                    current['rows'][1]['values'])
                ADMINISTRATION.apply(client, plan(current, operation,
                                                  name, kind),
                                     connection=connection)
                values = sql(connection, 'SELECT V FROM DUPLICATES ORDER BY V')
                assert values == ([(7,), (9,)] if operation == 'update'
                                  else [(7,)])
                with native.connect(password=password, **_route_arguments(
                        selected, native)) as observer:
                    assert sql(observer, 'SELECT V FROM DUPLICATES') == [
                        (7,), (7,)]
                connection.rollback()
                assert sql(connection, 'SELECT V FROM DUPLICATES') == [
                    (7,), (7,)]
                checks.append(kind+':'+name+':'+operation)
        for change in ('F=?', 'S=?', 'A=?', 'B=?'):
            reset()
            sql(connection, 'UPDATE DUPLICATES SET V=8')
            current = page()
            mutation = plan(current)
            key = sql(connection, 'SELECT FIRST 1 RDB$DB_KEY FROM DUPLICATES '
                      'ORDER BY RDB$DB_KEY')[0][0]
            value = {'F=?': -0.0, 'S=?': 'SAME', 'A=?': [2, 1],
                     'B=?': b'changed'}[change]
            sql(connection, 'UPDATE DUPLICATES SET '+change +
                ' WHERE RDB$DB_KEY=?', [value, key])
            sql(connection, 'INSERT INTO SIDE_WORK VALUES(5)')
            transaction = connection.main_transaction.info.id
            try:
                ADMINISTRATION.apply(client, mutation, connection=connection)
            except RelationalClientError as error:
                assert 'unchanged' in str(error)
            else:
                raise AssertionError('Same-transaction value change lost')
            assert connection.main_transaction.info.id == transaction
            assert sql(connection, 'SELECT V FROM SIDE_WORK') == [(5,)]
            checks.append('same-transaction:'+change)
        for outcome in ('commit', 'rollback', 'replacement'):
            reset()
            mutation = plan(page())
            getattr(connection, 'rollback' if outcome == 'replacement' else
                    outcome)()
            if outcome == 'replacement':
                sql(connection, 'INSERT INTO SIDE_WORK VALUES(6)')
                transaction = connection.main_transaction.info.id
            try:
                ADMINISTRATION.apply(client, mutation, connection=connection)
            except RelationalClientError as error:
                assert 'row identity' in str(error)
            else:
                raise AssertionError('Expired native owner accepted')
            if outcome == 'replacement':
                assert connection.main_transaction.info.id == transaction
                assert sql(connection, 'SELECT V FROM SIDE_WORK') == [(6,)]
            else:
                assert not connection.main_transaction.is_active()
            checks.append('owner-fence:'+outcome)
        reset()
        mutation = plan(page())
        with native.connect(password=password, **_route_arguments(
                selected, native)) as other:
            sql(other, 'INSERT INTO SIDE_WORK VALUES(8)')
            transaction = other.main_transaction.info.id
            try:
                ADMINISTRATION.apply(client, mutation, connection=other)
            except RelationalClientError as error:
                assert 'row identity' in str(error)
            else:
                raise AssertionError('Another attachment accepted identity')
            assert other.main_transaction.info.id == transaction
            assert sql(other, 'SELECT V FROM SIDE_WORK') == [(8,)]
            other.rollback()
        checks.append('owner-fence:other-attachment')
        for timing in ('before-preflight', 'after-preflight'):
            reset()
            mutation = plan(page())
            key = sql(connection, 'SELECT FIRST 1 RDB$DB_KEY FROM DUPLICATES '
                      'ORDER BY RDB$DB_KEY')[0][0]
            with native.connect(password=password, **_route_arguments(
                    selected, native)) as other:
                def change():
                    sql(other, 'UPDATE DUPLICATES SET S=? WHERE RDB$DB_KEY=?',
                        ['SAME', key])
                    other.commit()
                original = grid_array_identity.verify

                def race(*args):
                    original(*args)
                    change()

                if timing == 'before-preflight':
                    change()
                with patch.object(grid_array_identity, 'verify',
                                  race if timing == 'after-preflight' else
                                  original):
                    try:
                        ADMINISTRATION.apply(client, mutation,
                                             connection=connection)
                    except RelationalClientError as error:
                        assert ('unchanged' in str(error) or
                                'exactly one row' in str(error))
                    else:
                        raise AssertionError('Competing row change lost')
            checks.append('competing-commit:'+timing)
        connection.rollback()
        for mode in ('PRESERVE', 'DELETE'):
            name = 'TEMP_'+mode
            view = 'VIEW_'+mode
            sql(connection, f'CREATE GLOBAL TEMPORARY TABLE {name} '
                f'(ID INTEGER PRIMARY KEY,V INTEGER) ON COMMIT {mode} ROWS')
            connection.commit()
            sql(connection, f'CREATE VIEW {view} AS SELECT * FROM {name}')
            connection.commit()
            sql(connection, f'INSERT INTO {view} VALUES(1,7)')
            current = page(view, 'view')
            assert current['identity_policy'] == (
                'provider-view-primary-key-and-original-values')
            ADMINISTRATION.apply(client, plan(current, name=view, kind='view'),
                                 connection=connection)
            assert sql(connection, f'SELECT V FROM {view}') == [(9,)]
            connection.rollback()
            assert not sql(connection, f'SELECT V FROM {view}')
            connection.rollback()
            sql(connection, f'INSERT INTO {view} VALUES(2,7)')
            connection.commit()
            assert sql(connection, f'SELECT V FROM {view}') == (
                [(7,)] if mode == 'PRESERVE' else [])
            with native.connect(password=password, **_route_arguments(
                    selected, native)) as observer:
                assert not sql(observer, f'SELECT V FROM {view}')
            connection.rollback()
            checks.append('temporary-view:'+mode)
    finally:
        client.close()
        (evidence / 'checks.json').write_text(
            json.dumps(checks, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--embedded', action='store_true')
    options = parser.parse_args()
    if options.embedded:
        from tools.cdeadmin_firebird_recovery_group_gate import run_embedded
    fixture = run_embedded if options.embedded else run_local
    result = fixture(options.runtime, options.evidence,
                     lambda *args: qualify(
                         *args, embedded_mode=options.embedded))
    raise SystemExit(0 if result['complete'] else 1)

#!/usr/bin/env python3
"""Native prepared plans preserve pending work and report truncation."""
import argparse
import json
from pathlib import Path
import secrets
from types import SimpleNamespace

from tools.cdeadmin_firebird_local_fixture import run_local
from tools.cdeadmin_firebird_stream_gate import (
    _create_client, _route_arguments,
)
from pgadmin.cdeadmin.providers.firebird.query_plans import read_plan


def qualify(native, admin, route, accounts, evidence, root, embedded=False):
    user, password = (('OWNED_LOCAL', None)
                      if embedded else accounts['Srp'][0])
    if embedded:
        route = {'attachment_mode': 'embedded', 'filesystem_root': str(root)}
    selected = dict(route, user=user, database=str(root / 'plans.fdb'))
    client = _create_client(SimpleNamespace(acquire_secret=None))
    results = []

    def explain(connection, source):
        query = client.submit_query(connection, {
            'source': source, 'parameters': [], 'output_policy': {
                'firebird_plan': True, 'client_sql_dialect': 3}})
        query.worker.join(20)
        if query.worker.is_alive():
            client.cancel(query)
            query.worker.join(10)
            raise AssertionError('Owned plan worker exceeded deadline')
        return client.describe_result(query)['payload']

    try:
        with native.create_database(password=password, **_route_arguments(
                selected, native)) as owner:
            with owner.cursor() as cursor:
                cursor.execute('CREATE TABLE "café"(ID INTEGER PRIMARY KEY)')
            owner.commit()
            for charset in ('UTF8', 'ISO8859_1'):
                connection = native.connect(password=password, charset=charset,
                                            **{key: value for key, value in
                                               _route_arguments(
                                                   selected, native).items()
                                                if key != 'charset'})
                client._connections.append(connection)
                idle = explain(connection, 'SELECT * FROM "café" WHERE ID=?')
                assert idle['execution_state'] == 'succeeded'
                assert idle['query_plan']['transaction_started']
                assert idle['query_plan']['parameter_count'] == 1
                with connection.cursor() as cursor:
                    cursor.execute('INSERT INTO "café" VALUES(1)')
                identity = connection.main_transaction.info.id
                for sql in ('SELECT * FROM "café" WHERE ID=?',
                            'DELETE FROM "café" WHERE ID=?', 'COMMIT',
                            'ROLLBACK', 'CREATE TABLE NEVER_CREATED(ID INT)'):
                    result = explain(connection, sql)
                    assert result['execution_state'] == 'succeeded'
                    assert connection.main_transaction.info.id == identity
                    plan = result['query_plan']
                    assert plan['statement_execution_requested'] is False
                    assert plan['transaction_action_requested'] is False
                    if sql.startswith(('SELECT', 'DELETE')):
                        assert 'café' in plan['legacy']['text']
                        assert 'café' in plan['detailed']['text']
                    results.append({'charset': charset, 'query_plan': plan})
                if charset == 'UTF8':
                    large = ' UNION ALL '.join(
                        'SELECT ID FROM "café" "' + '漢' * 59 + str(index) +
                        '" WHERE ID BETWEEN ? AND ?' for index in range(200))
                    large_result = explain(connection, large)
                    (evidence / 'large-plan.json').write_text(
                        json.dumps(large_result, indent=2) + '\n')
                    assert large_result['execution_state'] == 'succeeded'
                    assert large_result['query_plan']['detailed']['truncated']
                result = explain(connection, 'SELECT * FROM MISSING_TABLE')
                assert result['execution_state'] == 'failed'
                assert connection.main_transaction.info.id == identity
                with connection.cursor() as cursor:
                    cursor.execute('SELECT COUNT(*) FROM "café"')
                    assert cursor.fetchone() == (1,)
                    cursor.execute("SELECT COUNT(*) FROM RDB$RELATIONS WHERE "
                                   "RDB$RELATION_NAME='NEVER_CREATED'")
                    assert cursor.fetchone() == (0,)
                statement = connection._att.prepare(
                    connection.main_transaction._tra,
                    'SELECT * FROM "café" WHERE ID=?', 3)
                try:
                    for code in (22, 26):
                        part = read_plan(statement, code, connection._encoding,
                                         buffer_size=32)
                        assert part['truncated'] and not part['complete']
                finally:
                    statement.free()
                client.control_transaction(connection, 'rollback')
                client.close_session(connection)
            denied_password = None
            if not embedded:
                denied_password = secrets.token_urlsafe(24)
                admin.execute_immediate(
                    "CREATE USER OWNED_PLAN_DENIED PASSWORD '" +
                    denied_password + "' USING PLUGIN Srp")
                admin.commit()
            denied_route = dict(selected, user='OWNED_PLAN_DENIED')
            denied = native.connect(password=denied_password,
                                    **_route_arguments(denied_route, native))
            client._connections.append(denied)
            result = explain(denied, 'SELECT * FROM "café"')
            assert result['execution_state'] == 'failed'
            assert result['error']['native_status_codes']
            results.append({'denied_prepare': result})
            client.close_session(denied)
    finally:
        client.close()
    (evidence / 'checks.json').write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--embedded', action='store_true')
    options = parser.parse_args()
    if options.embedded:
        from tools.cdeadmin_firebird_recovery_group_gate import run_embedded
        fixture = run_embedded
    else:
        fixture = run_local
    result = fixture(options.runtime, options.evidence,
                     lambda *args: qualify(*args, embedded=options.embedded))
    raise SystemExit(0 if result['complete'] else 1)

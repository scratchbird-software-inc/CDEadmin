#!/usr/bin/env python3
"""Native retained-session script outcomes, auxiliary DDL and rollback."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import time

from tools.cdeadmin_firebird_stream_gate import (
    _create_client, _route_arguments,
)
from tools.cdeadmin_firebird_local_fixture import run_local


def qualify(native, admin, route, accounts, evidence, root,
            embedded_mode=False):
    user, password = (('OWNED_LOCAL', None) if embedded_mode else
                      accounts['Srp'][0])
    if embedded_mode:
        route = {'attachment_mode': 'embedded', 'filesystem_root': str(root)}
    selected = dict(route, user=user, database=str(root / 'scripts.fdb'))
    client = _create_client(SimpleNamespace(acquire_secret=None))
    connection = native.create_database(
        password=password, **_route_arguments(selected, native))
    client._connections.append(connection)
    checks = []

    def sql(source):
        with connection.cursor() as cursor:
            cursor.execute(source)
            return cursor.fetchall() if cursor.description else []

    def script(source, label, max_rows=100):
        query = client.submit_query(connection, {
            'source': source, 'parameters': [], 'output_policy': {
                'firebird_script': True, 'client_sql_dialect': 3,
                'max_rows': max_rows}})
        query.worker.join(20)
        if query.worker.is_alive():
            client.cancel(query)
            query.worker.join(10)
            raise AssertionError('Owned script worker exceeded gate deadline')
        result = client.describe_result(query)['payload']
        (evidence / (label + '.json')).write_text(
            json.dumps(result, indent=2) + '\n')
        return result

    try:
        sql('CREATE TABLE PENDING (ID INTEGER PRIMARY KEY)')
        connection.commit()
        result = script('''SET TERM ^ ;
CREATE PROCEDURE OWNED_P RETURNS (V VARCHAR(40)) AS
BEGIN V = q'{a; '' literal}'; SUSPEND; END^
SET TERM ; ^
SELECT * FROM OWNED_P;
INSERT INTO PENDING VALUES (1);
ROLLBACK;
''', 'manual')
        assert result['execution_state'] == 'succeeded'
        assert result['script']['entries'][3]['result']['payload']['rows'] == [
            ("a; '' literal",)]
        assert not connection.main_transaction.is_active()
        assert sql('SELECT COUNT(*) FROM PENDING') == [(0,)]
        assert sql("SELECT COUNT(*) FROM RDB$PROCEDURES WHERE "
                   "RDB$PROCEDURE_NAME='OWNED_P'") == [(0,)]
        connection.rollback()
        checks.append('manual-PSQL-values-explicit-rollback')

        sql('INSERT INTO PENDING VALUES (7)')
        original = connection.main_transaction.info.id
        result = script('''SET AUTODDL ON;
CREATE TABLE OWNED_AUTO (ID INTEGER);
INSERT INTO OWNED_AUTO VALUES (1);
CREATE SEQUENCE OWNED_SEQUENCE;
SET GENERATOR OWNED_SEQUENCE TO 17;
''', 'autoddl')
        assert result['execution_state'] == 'succeeded'
        assert connection.main_transaction.info.id == original
        ddl = [entry['ddl_transaction']
               for entry in result['script']['entries']
               if entry.get('ddl_transaction')]
        assert len(ddl) == 3
        assert all(item['observation'] == 'driver method returned'
                   for item in ddl)
        with native.connect(password=password, **_route_arguments(
                selected, native)) as observer:
            with observer.cursor() as cursor:
                cursor.execute('SELECT COUNT(*) FROM PENDING')
                assert cursor.fetchone()[0] == 0
                cursor.execute('SELECT COUNT(*) FROM OWNED_AUTO')
                assert cursor.fetchone()[0] == 0
                cursor.execute('SELECT GEN_ID(OWNED_SEQUENCE, 0) '
                               'FROM RDB$DATABASE')
                assert cursor.fetchone()[0] == 17
        checks.append('auxiliary-DDL-preserves-main-pending-work-and-identity')

        result = script('''SET BAIL OFF; SET AUTODDL ON;
CREATE FUNCTION OWNED_MISSING(X INTEGER) RETURNS INTEGER
EXTERNAL NAME 'cdeadmin_missing_module!absent' ENGINE UDR;
INSERT INTO PENDING VALUES (99);
''', 'deferred-commit-error')
        assert result['execution_state'] == 'failed'
        records = result['script']['entries']
        assert records[-1]['state'] == 'not_run'
        receipt = records[-2]['ddl_transaction']
        assert receipt['observation'] == 'unavailable'
        assert receipt['rollback_after_failed_commit']['observation'] == (
            'driver method returned')
        assert connection.main_transaction.info.id == original
        assert sql('SELECT ID FROM PENDING ORDER BY ID') == [(7,)]
        client.control_transaction(connection, 'rollback')
        checks.append(
            'failed-auxiliary-commit-rollback-does-not-finalize-main')

        sql('INSERT INTO PENDING VALUES (8)')
        original = connection.main_transaction.info.id
        wide = ("SELECT CAST(RPAD('x', 6000, 'x') AS VARCHAR(6000) "
                "CHARACTER SET ASCII) AS V FROM RDB$TYPES ROWS 100;\n")
        result = script('SET BAIL OFF;\n' + wide * 5 +
                        'INSERT INTO PENDING VALUES (100);', 'shared-budget')
        assert result['execution_state'] == 'failed'
        assert result['script']['entries'][-1]['state'] == 'not_run'
        assert connection.main_transaction.info.id == original
        assert sql('SELECT ID FROM PENDING') == [(8,)]
        client.control_transaction(connection, 'rollback')
        checks.append('shared-materialization-budget-stops-later-DML')

        for automatic in ('OFF', 'ON'):
            sql('INSERT INTO PENDING VALUES (9)')
            original = connection.main_transaction.info.id
            query = client.submit_query(connection, {
                'source': 'SET BAIL OFF; SET AUTODDL ' + automatic +
                '; SET TERM ^ ; EXECUTE BLOCK AS DECLARE N BIGINT; '
                'BEGIN N = 0; WHILE (N < 9000000000000) DO '
                'BEGIN N = N + 1; END END^ SET TERM ; ^ '
                'INSERT INTO PENDING VALUES (101);',
                'parameters': [], 'output_policy': {'firebird_script': True}})
            time.sleep(0.4)
            assert query.worker.is_alive()
            client.cancel(query)
            query.worker.join(10)
            assert not query.worker.is_alive()
            result = client.describe_result(query)['payload']
            (evidence / ('cancel-' + automatic + '.json')).write_text(
                json.dumps(result, indent=2) + '\n')
            assert result['execution_state'] == 'cancelled'
            assert result['script']['entries'][-1]['state'] == 'not_run'
            assert connection.main_transaction.info.id == original
            assert sql('SELECT ID FROM PENDING') == [(9,)]
            client.control_transaction(connection, 'rollback')
            checks.append('native-cancel-BAIL-OFF-AUTODDL-' + automatic)
    finally:
        client.close()
    (evidence / 'checks.json').write_text(json.dumps(checks, indent=2) + '\n')


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
    result = fixture(options.runtime, options.evidence, lambda *args: qualify(
        *args, embedded_mode=options.embedded))
    raise SystemExit(0 if result['complete'] else 1)

"""Native MariaDB protocol ownership, multiple results and cancellation proof.
"""
import argparse
import json
import secrets
import time
from types import SimpleNamespace
from pathlib import Path

from tools.cdeadmin_mariadb_driver_gate import run
from pgadmin.cdeadmin.providers.mysql_family.provider import (
    MARIADB_PROFILE, _create_client,
)
from pgadmin.cdeadmin.sdk import RelationalClientError
from tools.mysql_reply_loss_fixture import CommitReplyLoss
from tools.mysql_driver_gate_support import provider_access


def collect(client, token, timeout=30):
    pages = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        page = client.describe_result(token)
        if page['payload']['has_page'] or page['complete']:
            pages.append(page)
        if page['complete']:
            return pages
    raise AssertionError('MySQL execution did not finish before gate deadline')


def qualify(route, evidence, *, password=None, reply_loss=True):
    import mariadb as native
    evidence.mkdir(parents=True, exist_ok=False)
    proof = {'complete': False, 'checks': []}
    owner = native.connect(**route, **(
        {'password': password} if password is not None else {}))
    provider_route, permissions = provider_access(route, password)
    cursor = owner.cursor()
    schema = 'owned_stream_' + secrets.token_hex(8)
    client = _create_client(
        MARIADB_PROFILE, permissions, SimpleNamespace(pool_namespace="gate"))
    try:
        cursor.execute(f'CREATE DATABASE `{schema}`')
        handle = client.open_session({'route': dict(
            provider_route, database=schema, autocommit=False)})

        def sql(source):
            return collect(client, client.execute(handle, {'source': source}))

        def rows(pages):
            return [row for page in pages for row in page['payload']['rows']]

        sql('CREATE PROCEDURE batch_results() BEGIN '
            'SELECT 11 AS one; SELECT 22 AS two; END')
        batch = sql('CALL batch_results()')
        assert rows(batch) == [(11,), (22,)]
        assert [p['payload']['result_set_index'] for p in batch
                if p['payload']['rows']] == [0, 1]
        assert rows(sql('SELECT 33')) == [(33,)]
        proof['checks'].append('multiple_results_and_following_reuse')
        sql('CREATE PROCEDURE p() BEGIN SELECT 41; SELECT 42; END')
        procedure = sql('CALL p()')
        assert rows(procedure) == [(41,), (42,)]
        assert len([p for p in procedure if p['payload']['has_page']]) == 3
        assert rows(sql('SELECT 43')) == [(43,)]
        proof['checks'].append('procedure_results_and_trailing_ok')
        sql('CREATE TABLE pending (id INT)')
        sql('CREATE PROCEDURE late_failure() BEGIN '
            'INSERT INTO pending VALUES (1); '
            'SELECT id FROM pending; SELECT * FROM absent_table; END')
        failed = sql('CALL late_failure()')
        assert rows(failed) == [(1,)]
        assert failed[-1]['payload']['error']['errno'] == 1146
        assert client.describe_transaction(handle)['in_transaction'] is True
        client.control_transaction(handle, 'rollback')
        assert rows(sql('SELECT COUNT(*) FROM pending')) == [(0,)]
        proof['checks'].append('later_error_preserves_results_and_native_work')
        many = sql('SELECT a.id FROM '
                   '(SELECT 1 id UNION ALL SELECT 2 UNION ALL SELECT 3 '
                   'UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL '
                   'SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8) a '
                   'CROSS JOIN (SELECT 1 UNION ALL SELECT 2 UNION ALL '
                   'SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL '
                   'SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8) b '
                   'CROSS JOIN (SELECT 1 UNION ALL SELECT 2 UNION ALL '
                   'SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL '
                   'SELECT 6 UNION ALL SELECT 7 UNION ALL SELECT 8) c')
        assert len(rows(many)) == 512
        assert all(len(p['payload']['rows']) <= 256 for p in many)
        assert [p['payload']['row_offset'] for p in many
                if p['payload']['has_page']] == [0, 256]
        proof['checks'].append('bounded_pages_preserve_every_row')
        sql('INSERT INTO pending VALUES (7)')
        token = client.execute(handle, {'source': 'SELECT SLEEP(20)'})
        deadline = time.monotonic() + 5
        while token.identity is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert client.describe_transaction(handle)['state'] == 'executing'
        for action in ('commit', 'rollback'):
            try:
                client.control_transaction(handle, action)
            except RelationalClientError:
                pass
            else:
                raise AssertionError('Transaction raced active execution')
        assert client.cancel(token) is True
        cancelled = collect(client, token, timeout=5)
        assert cancelled[-1]['payload']['cancelled'] is True
        assert not cancelled[-1]['payload']['session_reuse_blocked']
        assert rows(sql('SELECT id FROM pending')) == [(7,)]
        client.control_transaction(handle, 'rollback')
        proof['checks'].append('native_cancel_retains_prior_transaction_work')
        if reply_loss:
            relay = CommitReplyLoss(route['host'], route['port'])
            try:
                lost = client.open_session({'route': dict(
                    provider_route, host='127.0.0.1', port=relay.port,
                    database=schema, autocommit=False, ssl=False)})
                inserted = collect(client, client.execute(lost, {
                    'source': 'INSERT INTO pending VALUES (99)'}))
                assert not inserted[-1]['payload']['error']
                try:
                    client.control_transaction(lost, 'commit')
                except Exception:
                    pass
                else:
                    raise AssertionError('Lost COMMIT reply reported success')
                assert relay.commit_acknowledged.wait(2)
                assert client.describe_transaction(lost)['state'] == 'unknown'
                assert client.close_session(lost)['state'] == 'unknown'
                cursor.execute(f'SELECT id FROM `{schema}`.pending')
                assert cursor.fetchall() == [(99,)]
                owner.rollback()
                proof['checks'].append(
                    'lost_commit_reply_unknown_despite_commit')
            finally:
                relay.close()
        closing = client.execute(handle, {'source': 'SELECT SLEEP(20)'})
        deadline = time.monotonic() + 5
        while closing.identity is None and time.monotonic() < deadline:
            time.sleep(0.01)
        client.close()
        assert closing.finished.is_set()
        assert not client._connections
        proof['checks'].append(
            'shutdown_joins_worker_before_connection_release')
        proof['complete'] = True
    finally:
        client.close()
        cursor.execute(f'DROP DATABASE IF EXISTS `{schema}`')
        cursor.close()
        owner.close()
        (evidence / 'summary.json').write_text(json.dumps(proof, indent=2))
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='mariadb:12.2.2')
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.image, args.evidence, qualify)
    raise SystemExit(0 if result['complete'] else 1)

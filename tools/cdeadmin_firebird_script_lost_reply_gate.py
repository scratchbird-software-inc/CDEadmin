#!/usr/bin/env python3
"""Withhold an owned script commit reply without recording wire contents."""
import argparse
import json
from pathlib import Path
import time
from types import SimpleNamespace

from tools.cdeadmin_firebird_stream_gate import (
    _create_client, _route_arguments,
)
from tools.cdeadmin_firebird_network_timing_gate import observed_relay
from tools.cdeadmin_firebird_local_fixture import run_local


def qualify(native, admin, route, accounts, evidence, root):
    user, password = accounts['Srp'][0]
    selected = dict(route, user=user, database=str(root / 'script-loss.fdb'))
    client = _create_client(SimpleNamespace(acquire_secret=None))
    connection = None
    try:
        with native.create_database(password=password, **_route_arguments(
                selected, native)) as observer:
            with observer.cursor() as cursor:
                cursor.execute(
                    'CREATE TABLE EFFECTS(ID INTEGER PRIMARY KEY)')
            observer.commit()
            with observed_relay((route['host'], route['port'])) as link:
                connection = native.connect(
                    password=password, **_route_arguments(
                        dict(selected, host=link.host, port=link.port), native))
                client._connections.append(connection)
                client.execute(connection, {
                    'source': 'INSERT INTO EFFECTS VALUES(1)'})
                link.sent.clear()
                link.hold.set()
                query = client.submit_query(connection, {
                    'source': 'COMMIT; INSERT INTO EFFECTS VALUES(2);',
                    'parameters': [],
                    'output_policy': {'firebird_script': True}})
                assert link.sent.wait(5)
                deadline = time.monotonic() + 5
                while True:
                    with observer.cursor() as cursor:
                        cursor.execute('SELECT ID FROM EFFECTS')
                        rows = cursor.fetchall()
                    observer.rollback()
                    if rows == [(1,)]:
                        break
                    assert time.monotonic() < deadline
                    time.sleep(0.02)
                assert query.worker.is_alive(), 'Reply was not withheld'
            query.worker.join(10)
            assert not query.worker.is_alive()
            result = client.describe_result(query)['payload']
            (evidence / 'outcome.json').write_text(
                json.dumps(result, indent=2) + '\n')
            assert result['script']['unknown_outcome']
            assert [e['state'] for e in result['script']['entries']] == [
                'unknown', 'not_run']
            assert result['session_reuse_blocked']
            with observer.cursor() as cursor:
                cursor.execute('SELECT ID FROM EFFECTS')
                assert cursor.fetchall() == [(1,)]
            observer.rollback()
            (evidence / 'outcome.json').write_text(
                json.dumps(result, indent=2) + '\n')
    finally:
        if connection is not None and not connection.is_closed():
            try:
                connection.close()
            except native.DatabaseError:
                pass
        assert connection is None or connection.is_closed()
        client._forget_connection(connection)
        client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    options = parser.parse_args()
    result = run_local(options.runtime, options.evidence, qualify)
    raise SystemExit(0 if result['complete'] else 1)

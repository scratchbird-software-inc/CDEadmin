#!/usr/bin/env python3
"""Owned loopback transport loss after independently observed native commit.

The relay discards an encrypted response; it never records wire payloads.
This is an application/native-driver failure test, not a physical-network test.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import time
import traceback
from types import SimpleNamespace

from tools.cdeadmin_firebird_stream_gate import (
    _create_client, _route_arguments,
)
from tools.cdeadmin_firebird_network_timing_gate import observed_relay
from tools.cdeadmin_firebird_local_fixture import run_local
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def observe_live(client, connection, active):
    transaction = connection.main_transaction
    assert transaction.is_active() is active
    identity = transaction.info.id if active else None
    state = client.describe_transaction(connection)
    assert state['attachment_live'] is True
    assert state['state'] == ('active' if active else 'idle')
    assert transaction.is_active() is active
    if active:
        assert state['fields']['transaction_id']['value'] == identity
        assert transaction.info.id == identity
    return {'state': state['state'], 'same_transaction': True}


def _qualify(native, admin, route, accounts, evidence, root):
    user, password = accounts['Srp'][0]
    selected = dict(route, user=user, database=str(root / 'lost-reply.fdb'))
    checks = []
    with native.create_database(
            password=password, **_route_arguments(selected, native)) as owner:
        with owner.cursor() as query:
            query.execute('CREATE TABLE EFFECTS(ID INTEGER PRIMARY KEY)')
        owner.commit()
        owner.default_tpb = owner.main_transaction.default_tpb = native.tpb(
            native.Isolation.READ_COMMITTED_RECORD_VERSION, lock_timeout=0)

        def count():
            with owner.cursor() as query:
                query.execute('SELECT COUNT(*) FROM EFFECTS')
                result = query.fetchone()[0]
            owner.rollback()
            return result

        for action in ('commit', 'rollback'):
            client = _create_client(SimpleNamespace(acquire_secret=None))
            connection = None
            try:
                upstream = (route['host'], route['port'])
                with ThreadPoolExecutor(max_workers=1) as pool:
                    with observed_relay(upstream) as link:
                        relayed = dict(selected, host=link.host,
                                       port=link.port)
                        connection = native.connect(
                            password=password,
                            **_route_arguments(relayed, native))
                        client._connections.append(connection)
                        observe_live(client, connection, False)
                        token = client.execute(connection, {
                            'source': 'INSERT INTO EFFECTS VALUES(?)',
                            'parameters': [1 if action == 'commit' else 2]})
                        client.describe_result(token)
                        observe_live(client, connection, True)
                        expected = 1
                        link.sent.clear()
                        link.hold.set()
                        future = pool.submit(client.control_transaction,
                                             connection, action)
                        assert link.sent.wait(5), 'Native command was not sent'
                        if action == 'commit':
                            deadline = time.monotonic() + 5
                            while count() != expected:
                                assert time.monotonic() < deadline
                                time.sleep(0.02)
                        else:
                            # NO WAIT insertion succeeds only after the
                            # original transaction releases its row.
                            deadline = time.monotonic() + 5
                            while True:
                                try:
                                    with owner.cursor() as query:
                                        query.execute(
                                            'INSERT INTO EFFECTS VALUES(2)')
                                    owner.rollback()
                                    break
                                except native.DatabaseError:
                                    owner.rollback()
                                    assert time.monotonic() < deadline
                                    time.sleep(0.02)
                        assert not future.done(), 'Reply was not withheld'
                    try:
                        receipt = future.result(timeout=5)
                    except RelationalClientError as error:
                        assert 'outcome is unavailable' in str(error)
                        assert password not in str(error)
                        assert error.gds_codes
                        codes = list(error.gds_codes)
                    else:
                        assert action == 'rollback', (
                            'Lost commit reported success')
                        assert receipt['observation'] == (
                            'driver method returned')
                        assert receipt['native_call_made'] is True
                        codes = []
                assert count() == expected
                observation = client.describe_transaction(connection)
                assert observation['state'] == 'unknown'
                assert observation['attachment_live'] is False
                observation_unavailable = True
                try:
                    client.execute(connection, {'source': 'SELECT 1 FROM '
                                                'RDB$DATABASE'})
                except RelationalClientError as error:
                    assert 'liveness check failed' in str(error)
                else:
                    raise AssertionError('Dead attachment reuse accepted')
                cleanup = None
                try:
                    cleanup = client.close_session(connection)
                except Exception as error:
                    cleanup = {'error_type': type(error).__name__,
                               'handle_retained': connection in
                               client._connections}
                checks.append({'action': action, 'native_codes': codes,
                               'independent_committed_rows': count(),
                               'reply_withheld_until_native_completion': True,
                               'cleanup': cleanup,
                               'native_observation_unavailable':
                               observation_unavailable})
                (evidence / 'checks.json').write_text(
                    json.dumps(checks, indent=2, default=str) + '\n')
            finally:
                # The fixture owns these dead native handles. Explicit local
                # release is not interpreted as confirmed transaction rollback.
                if connection is not None and not connection.is_closed():
                    try:
                        connection.close()
                    except native.DatabaseError:
                        pass
                assert connection is None or connection.is_closed(), (
                    'Owned native handle leaked')
                client._forget_connection(connection)
                client.close()


def qualify(native, admin, route, accounts, evidence, root):
    try:
        return _qualify(native, admin, route, accounts, evidence, root)
    except Exception as error:
        (evidence / 'failure.json').write_text(json.dumps({
            'type': type(error).__name__,
            'native_codes': list(getattr(error, 'gds_codes', ())),
            'locations': [{'file': Path(frame.filename).name,
                           'line': frame.lineno} for frame in
                          traceback.extract_tb(error.__traceback__)]},
            indent=2) + '\n')
        raise


def embedded_observation(native, admin, route, accounts, evidence, root):
    selected = {'attachment_mode': 'embedded', 'filesystem_root': str(root),
                'user': 'OWNED_LOCAL', 'database': str(root / 'liveness.fdb')}
    client = _create_client(SimpleNamespace(acquire_secret=None))
    with native.create_database(**_route_arguments(selected, native)) as con:
        client._connections.append(con)
        try:
            with con.cursor() as query:
                query.execute('CREATE TABLE EFFECTS(ID INTEGER)')
            con.commit()
            idle = observe_live(client, con, False)
            with con.cursor() as query:
                query.execute('INSERT INTO EFFECTS VALUES(1)')
                query.execute('SELECT MON$REMOTE_PROTOCOL,MON$SERVER_PID '
                              'FROM MON$ATTACHMENTS WHERE MON$ATTACHMENT_ID='
                              'CURRENT_CONNECTION')
                protocol, pid = query.fetchone()
            assert protocol is None and pid == os.getpid()
            active = observe_live(client, con, True)
            con.rollback()
            with con.cursor() as query:
                query.execute('SELECT COUNT(*) FROM EFFECTS')
                assert query.fetchone()[0] == 0
            con.rollback()
            (evidence / 'checks.json').write_text(json.dumps({
                'idle': idle, 'active': active, 'same_process': True,
                'explicit_rollback_preserved': True}, indent=2) + '\n')
        finally:
            client.close_session(con)
            client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--embedded-observation', action='store_true')
    options = parser.parse_args()
    if options.embedded_observation:
        from tools.cdeadmin_firebird_recovery_group_gate import run_embedded
        result = run_embedded(options.runtime, options.evidence,
                              fixture_check=embedded_observation)
    else:
        result = run_local(options.runtime, options.evidence, qualify)
    raise SystemExit(0 if result['complete'] else 1)

#!/usr/bin/env python3
"""Native background expiry: pending work remains explicitly resolvable."""
import argparse
import json
from pathlib import Path
import time
from types import SimpleNamespace

from tools.cdeadmin_firebird_stream_gate import (
    _create_client, _route_arguments,
)
from tools.cdeadmin_firebird_local_fixture import run_local
from pgadmin.cdeadmin.providers.firebird import stream_leases
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def qualify(native, admin, route, accounts, evidence, root):
    user, password = accounts['Srp'][0]
    selected = dict(route, user=user, database=str(root / 'lease.fdb'))
    client = _create_client(SimpleNamespace(acquire_secret=None))
    connection = native.create_database(
        password=password, **_route_arguments(selected, native))
    client._connections.append(connection)
    connection.execute_immediate('CREATE TABLE LEASE_TEST (ID INTEGER)')
    connection.commit()
    previous = stream_leases.IDLE_SECONDS, stream_leases.SWEEP_SECONDS
    stream_leases.IDLE_SECONDS, stream_leases.SWEEP_SECONDS = 0.2, 0.05
    checks = []

    def request(action, **values):
        return client.query_stream(connection, {
            'stream_action': action, 'owner_id': 'owned-lease', **values})

    def observe():
        with native.connect(password=password, **_route_arguments(
                selected, native)) as observer:
            with observer.cursor() as cursor:
                cursor.execute('SELECT COUNT(*) FROM LEASE_TEST')
                return cursor.fetchone()[0]

    def wait_expired():
        state = client._state(connection)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if state.lock.acquire(blocking=False):
                try:
                    if (state.stream_expired and
                            state.result_stream is None and
                            state.blob_upload is None):
                        assert state.stream_owner == 'owned-lease'
                        return
                finally:
                    state.lock.release()
            time.sleep(0.01)
        raise AssertionError('Background stream expiry was not observed')

    try:
        for action in ('rollback', 'commit'):
            connection.execute_immediate('INSERT INTO LEASE_TEST VALUES (1)')
            page = request('open', source='SELECT ID FROM LEASE_TEST')
            assert page['rows'] == [[1]]
            # No further owner requests or direct reaper invocation.
            wait_expired()
            assert connection.main_transaction.is_active()
            assert not connection.is_closed()
            assert observe() == 0
            try:
                request('next', stream_reference=page['stream_reference'],
                        sequence=1)
            except RelationalClientError as error:
                assert 'expired' in str(error)
            else:
                raise AssertionError('Expired cursor was resumed')
            request('close')
            client.control_transaction(connection, action)
            assert observe() == (1 if action == 'commit' else 0)
            checks.append({'explicit_outcome': action,
                           'pending_work_survived_background_expiry': True})
        request('upload_begin')
        spool = client._state(connection).blob_upload
        wait_expired()
        assert spool.closed
        assert not connection.is_closed()
        request('close')
        checks.append({'abandoned_upload_file_released': True})
    finally:
        stream_leases.IDLE_SECONDS, stream_leases.SWEEP_SECONDS = previous
        client.close()
    (evidence / 'lease-checks.json').write_text(json.dumps({
        'checks': checks, 'test_idle_seconds': 0.2,
        'test_sweep_seconds': 0.05,
        'production_idle_seconds': previous[0],
        'transaction_resolution_explicit': True,
    }, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    options = parser.parse_args()
    result = run_local(options.runtime, options.evidence, qualify)
    raise SystemExit(0 if result['complete'] else 1)

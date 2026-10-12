#!/usr/bin/env python3
"""Portable TiKV retained driver gate with an owned random key prefix."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time
import traceback
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT)]
from cdeadmin_tikv_live_verify import Permissions  # noqa: E402
from pgadmin.cdeadmin.providers.tikv.provider import create_provider  # noqa: E402


def run(route, helper, evidence):
    evidence = Path(evidence).resolve()
    if evidence == ROOT or ROOT in evidence.parents:
        raise ValueError('Evidence must be outside repository')
    evidence.mkdir(parents=True, exist_ok=False)
    proof = dict(
        complete=False,
        cleanup_complete=False,
        checks=[],
        failures=[],
        platform=platform.platform())
    directory = ROOT / 'web/pgadmin/cdeadmin/providers/tikv'
    files = list(directory.glob('*.py')) + \
        list((directory / 'go_helper').glob('*.go'))
    files += [directory / 'go_helper/go.mod',
              directory / 'go_helper/go.sum',
              ROOT / 'web/pgadmin/cdeadmin/providers/retained_native.py',
              Path(__file__)]
    proof['source_sha256'] = {str(f.relative_to(ROOT)): hashlib.sha256(
        f.read_bytes()).hexdigest() for f in files}
    proof['helper_sha256'] = hashlib.sha256(
        Path(helper).read_bytes()).hexdigest()
    os.environ['CDEADMIN_TIKV_HELPER_PATH'] = str(helper)
    provider = create_provider(
        SimpleNamespace(
            endpoint_id=str(
                uuid.uuid4()), session_namespace=str(
                uuid.uuid4())), Permissions())
    prefix = 'cde-driver-' + uuid.uuid4().hex + '/'
    raw_keys = []
    txn_keys = []
    try:
        session = provider.open_session({'route': route})
        client = provider.client
        owner = provider._sessions[session['session_id']].handle
        proof['runtime'] = client.runtime_identity({'route': route}, owner)

        def observe(token, allow_error=False):
            pages = []
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                value = provider.describe_result(token)
                page = value['extensions']['tikv']['payload']
                pages.append(page)
                if value['complete']:
                    if not allow_error:
                        assert not page.get('error'), page
                    return pages
            raise AssertionError('TiKV operation observation timeout')

        def query(command, target=None):
            pages = observe(provider.execute(dict(target or session,
                                                  source=json.dumps(command))))
            return [r for p in pages for r in p.get('entries', [])]

        key = base64.b64encode(prefix.encode() + b'\0\xff').decode()
        raw_keys.append(key)
        query(dict(operation='put', key_base64=key, value_base64='AP8='))
        rows = query(dict(operation='get', key_base64=key))
        assert rows[0]['value_base64'] == 'AP8=' and rows[0]['found']
        rows = query(dict(operation='compare_and_swap', key_base64=key,
                          previous_value_base64='AP8=', value='changed'))
        assert rows[0]['swapped']
        rows = query(
            dict(
                operation='compare_and_swap',
                key_base64=key,
                previous_value_base64='AP8=',
                value='must-not-apply'))
        assert not rows[0]['swapped']
        proof['checks'].append(
            'raw-binary-values-native-cas-applied-and-not-applied')
        for i in range(300):
            encoded = base64.b64encode(
                (prefix + 'raw/' + str(i).zfill(4)).encode()).decode()
            raw_keys.append(encoded)
            query(dict(operation='put', key_base64=encoded, value='raw-page'))
        raw_pages = observe(
            provider.execute(
                dict(
                    session,
                    source=json.dumps(
                        dict(
                            operation='scan_all',
                            start_key=prefix +
                            'raw/',
                            end_key=prefix +
                            'raw0')))))
        assert sum(len(p.get('entries', [])) for p in raw_pages) == 300
        assert max(len(p.get('entries', [])) for p in raw_pages) <= 256
        query(
            dict(
                operation='put_with_ttl',
                key_base64=key,
                value='ttl',
                ttl_seconds=60))
        assert query(dict(operation='get_key_ttl', key_base64=key))[
            0]['ttl_seconds_remaining'] > 0
        proof['checks'].append('raw-paging-and-native-ttl')

        independent = provider.open_session({'route': route})
        txn_key = prefix + 'transaction'
        txn_keys.append(txn_key)
        provider.control_transaction(dict(session, action='begin'))
        query(dict(operation='txn_set', key=txn_key, value='private'))
        assert query(dict(operation='txn_get', key=txn_key))[
            0]['value'] == 'private'
        rows = query(
            dict(
                operation='transaction',
                keys=[txn_key]),
            independent)
        assert not rows[0]['found']
        provider.control_transaction(dict(session, action='rollback'))
        provider.control_transaction(dict(session, action='begin'))
        query(dict(operation='txn_set', key=txn_key, value='committed'))
        provider.control_transaction(dict(session, action='commit'))
        assert query(
            dict(
                operation='transaction',
                keys=[txn_key]),
            independent)[0]['value'] == 'committed'
        proof['checks'].append(
            'retained-native-transaction-isolation-commit-and-rollback')
        for start in range(0, 10017, 500):
            changes = []
            for i in range(start, min(start + 500, 10017)):
                k = prefix + 'range/' + str(i).zfill(6)
                txn_keys.append(k)
                changes.append(dict(operation='set', key=k, value='native'))
            query(dict(operation='transaction', mutations=changes))
        provider.control_transaction(dict(session, action='begin'))
        command = dict(
            operation='txn_scan',
            start_key=prefix + 'range/',
            end_key=prefix + 'range0')
        pages = observe(
            provider.execute(
                dict(
                    session,
                    source=json.dumps(command))))
        assert sum(len(p.get('entries', [])) for p in pages) == 10017
        assert max(len(p.get('entries', [])) for p in pages) <= 256
        timestamps = {p['native']['start_ts']
                      for p in pages if p.get('has_page')}
        assert len(timestamps) == 1 and all(isinstance(t, str)
                                            for t in timestamps)
        provider.control_transaction(dict(session, action='rollback'))
        proof['checks'].append(
            '10017-entry-transaction-range-one-exact-native-timestamp')
        # Pessimistic mode must acquire real locks and decide natively.
        pessimistic = provider.open_session(
            {'route': dict(route, transaction_mode='pessimistic')})
        provider.control_transaction(dict(pessimistic, action='begin'))
        query(
            dict(
                operation='txn_set',
                key=txn_key,
                value='pessimistic'),
            pessimistic)
        provider.control_transaction(dict(pessimistic, action='commit'))
        assert query(
            dict(
                operation='transaction',
                keys=[txn_key]),
            independent)[0]['value'] == 'pessimistic'
        provider.close_session(pessimistic)
        proof['checks'].append('native-pessimistic-lock-and-commit')
        fault = provider.open_session({'route': route})
        fault_owner = provider._sessions[fault['session_id']].handle
        provider.control_transaction(dict(fault, action='begin'))
        query(dict(operation='txn_set', key=txn_key, value='once'), fault)
        original = client.backend._rpc
        calls = []

        def lost_reply(handle, request):
            result = original(handle, request)
            if handle is fault_owner.handle and request.get(
                    'operation') == 'commit':
                calls.append('acknowledged')
                raise OSError('injected failure after native acknowledgement')
            return result

        client.backend._rpc = lost_reply
        try:
            failed = observe(provider.execute(
                dict(fault, source='{"operation":"commit"}')), True)[-1]
            assert failed['session_reuse_blocked'] and calls == [
                'acknowledged']
            assert query(
                dict(
                    operation='transaction',
                    keys=[txn_key]),
                independent)[0]['value'] == 'once'
            provider.close_session(fault)
            assert calls == ['acknowledged']
        finally:
            client.backend._rpc = original
        proof['checks'].append('post-ack-native-commit-failure-no-replay')
        provider.control_transaction(dict(session, action='begin'))
        token = provider.execute(dict(session, source=json.dumps(command)))
        assert provider.cancel(token)
        cancelled = observe(token)[-1]
        assert cancelled['cancelled'] and cancelled['session_reuse_blocked']
        provider.close_session(session)
        proof['checks'].append('local-delivery-cancel-owned-helper-release')
        proof['complete'] = True
    except Exception:
        proof['failures'].append(traceback.format_exc())
    finally:
        try:
            cleanup = provider.open_session({'route': route})
            for key in raw_keys:
                query(dict(operation='delete', key_base64=key), cleanup)
            for start in range(0, len(txn_keys), 500):
                mutations = [dict(operation='delete', key=k)
                             for k in txn_keys[start:start + 500]]
                query(dict(operation='transaction', mutations=mutations),
                      cleanup)
            provider.close()
            proof['cleanup_complete'] = True
        except Exception:
            proof['complete'] = False
            proof['failures'].append(traceback.format_exc())
        summary = json.dumps(proof, indent=2) + '\n'
        (evidence / 'summary.json').write_text(summary)
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route', type=Path, required=True)
    parser.add_argument('--helper', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    result = run(
        json.loads(
            args.route.read_text()),
        args.helper,
        args.evidence)
    print(json.dumps(
        {'complete': result['complete'], 'failures': result['failures']}))
    raise SystemExit(0 if result['complete'] else 1)

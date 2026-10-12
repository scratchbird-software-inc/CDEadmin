#!/usr/bin/env python3
"""Qualify FoundationDB native ownership in an owned random key prefix."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import traceback
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from cdeadmin_foundationdb_live_verify import _Permissions  # noqa: E402
from pgadmin.cdeadmin.providers.foundationdb.provider import (  # noqa: E402
    create_provider,
)


def run(route, evidence):
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
    files = list(
        (ROOT / 'web/pgadmin/cdeadmin/providers/foundationdb').glob('*.py'))
    files += [ROOT / 'web/pgadmin/cdeadmin/providers/retained_native.py',
              Path(__file__)]
    proof['source_sha256'] = {str(f.relative_to(ROOT)): hashlib.sha256(
        f.read_bytes()).hexdigest() for f in files}
    provider = create_provider(
        SimpleNamespace(
            endpoint_id=str(
                uuid.uuid4()), session_namespace=str(
                uuid.uuid4())), _Permissions())
    prefix = ('cde-driver-' + uuid.uuid4().hex + '/').encode()
    database = None
    try:
        session = provider.open_session({'route': route})
        client = provider.client
        owner = provider._sessions[session['session_id']].handle
        database = owner.handle.database
        proof['runtime'] = client.runtime_identity({'route': route}, owner)

        def observe(token, allow_error=False):
            pages = []
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                value = provider.describe_result(token)
                page = value['extensions']['foundationdb']['payload']
                pages.append(page)
                if value['complete']:
                    if not allow_error:
                        assert not page.get('error'), page
                    return pages
            raise AssertionError('FoundationDB operation timeout')

        def query(command, target=None):
            pages = observe(provider.execute(dict(target or session,
                                                  source=json.dumps(command))))
            return [r for p in pages for r in p.get('entries', [])]

        def key(name):
            return base64.b64encode(prefix + name).decode()

        def set_value(name, value, target=None):
            return query(
                dict(
                    operation='set',
                    key=key(name),
                    key_encoding='base64',
                    value=base64.b64encode(value).decode(),
                    value_encoding='base64'),
                target)

        def get_value(name, target=None):
            return query(
                dict(
                    operation='get',
                    key=key(name),
                    key_encoding='base64'),
                target)[0]['value']

        set_value(b'\x00\xff', b'\x00\xff\xc3\x28')
        assert get_value(b'\x00\xff') == '00ffc328'
        provider.control_transaction(dict(session, action='begin'))
        set_value(b'rollback', b'private')
        assert get_value(b'rollback') == b'private'.hex()
        independent = provider.open_session({'route': route})
        assert get_value(b'rollback', independent) is None
        assert provider._sessions[independent['session_id']
                                  ].handle.handle is not owner.handle
        provider.control_transaction(dict(session, action='rollback'))
        assert get_value(b'rollback', independent) is None
        provider.control_transaction(dict(session, action='begin'))
        set_value(b'commit', b'visible')
        provider.control_transaction(dict(session, action='commit'))
        assert get_value(b'commit', independent) == b'visible'.hex()
        assert isinstance(client.describe_transaction(owner)
                          ['committed_version'], str)
        proof['checks'].append(
            'binary-values-session-isolation-native-commit-and-cancel')
        set_value(b'atomic', (1).to_bytes(8, 'little'))
        query(dict(operation='atomic', atomic_operation='add',
                   key=key(b'atomic'), key_encoding='base64',
                   value=base64.b64encode((2).to_bytes(8, 'little')).decode(),
                   value_encoding='base64'))
        assert get_value(b'atomic') == (3).to_bytes(8, 'little').hex()
        before = len(client.backend._databases)
        client.list_resources({'route': route})
        assert len(client.backend._databases) == before
        proof['checks'].append(
            'native-atomic-add-and-temporary-metadata-release')

        # Fixture writes use explicit native transactions; the driver
        # owns the subsequent streamed read.
        for start in range(0, 10017, 500):
            tx = database.create_transaction()
            for i in range(start, min(start + 500, 10017)):
                native_key = prefix + b'range/' + str(i).zfill(6).encode()
                tx.set(native_key, b'value')
            tx.commit().wait()
        command = dict(
            operation='range',
            begin=key(b'range/'),
            end=key(b'range0'),
            begin_encoding='base64',
            end_encoding='base64')
        pages = observe(provider.execute(
            dict(session, source=json.dumps(command))))
        assert sum(len(p.get('entries', [])) for p in pages) == 10017
        assert max(len(p.get('entries', [])) for p in pages) <= 256
        assert len({p['native']['read_version']
                   for p in pages if p.get('has_page')}) == 1
        proof['checks'].append(
            '10017-entry-range-bounded-pages-one-native-read-version')
        # Native conflict must not replay the original transaction.
        conflict = provider.open_session({'route': route})
        provider.control_transaction(dict(conflict, action='begin'))
        get_value(b'commit', conflict)
        set_value(b'commit', b'changed', independent)
        set_value(b'conflict', b'no-replay', conflict)
        failed = observe(provider.execute(
            dict(conflict, source='{"operation":"commit"}')), True)[-1]
        assert failed['session_reuse_blocked']
        assert failed['error']['native_code'] == 1020
        assert get_value(b'conflict', independent) is None
        provider.close_session(conflict)
        proof['checks'].append('native-read-conflict-without-retry')
        # Native acknowledged commit followed by client response failure.
        fault = provider.open_session({'route': route})
        fault_owner = provider._sessions[fault['session_id']].handle
        provider.control_transaction(dict(fault, action='begin'))
        set_value(b'lost', b'committed-once', fault)
        tx = fault_owner.handle.transaction
        original = tx.commit
        calls = []

        class LostReply:
            def wait(self):
                original().wait()
                calls.append('acknowledged')
                raise OSError('injected post-ack failure')

        tx.commit = lambda: LostReply()
        failed = observe(provider.execute(
            dict(fault, source='{"operation":"commit"}')), True)[-1]
        assert failed['session_reuse_blocked'] and calls == ['acknowledged']
        assert get_value(b'lost', independent) == b'committed-once'.hex()
        try:
            provider.execute(dict(fault, source='{"operation":"commit"}'))
        except Exception:
            pass
        else:
            raise AssertionError('Unknown outcome session reused')
        provider.close_session(fault)
        assert calls == ['acknowledged']
        proof['checks'].append('native-post-ack-commit-failure-no-replay')
        operation = provider.execute(dict(session, source=json.dumps(command)))
        assert provider.cancel(operation)
        cancelled = observe(operation)[-1]
        assert cancelled['cancelled'] and cancelled['session_reuse_blocked']
        provider.close_session(session)
        proof['checks'].append('local-delivery-cancellation-and-owned-release')
        proof['complete'] = True
    except Exception:
        proof['failures'].append(traceback.format_exc())
    finally:
        try:
            if database is not None:
                tx = database.create_transaction()
                tx.clear_range(prefix, prefix[:-1] + b'0')
                tx.commit().wait()
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
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    result = run(json.loads(args.route.read_text()), args.evidence)
    print(json.dumps(
        {'complete': result['complete'], 'failures': result['failures']}))
    raise SystemExit(0 if result['complete'] else 1)

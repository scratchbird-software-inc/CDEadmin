#!/usr/bin/env python3
"""Qualify retained Redis drivers in an owned random key namespace."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import platform
import re
import sys
import time
import traceback
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT)]
import cdeadmin_redis_live_gate  # noqa: E402,F401
from pgadmin.cdeadmin.providers.redis.provider import create_provider  # noqa: E402
from pgadmin.cdeadmin.security import SecretLease  # noqa: E402


def run(route, evidence, password=None):
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
    files = list((ROOT / 'web/pgadmin/cdeadmin/providers/redis').glob('*.py'))
    shared = ROOT / 'web/pgadmin/cdeadmin/providers/retained_native.py'
    files += [shared, Path(__file__)]
    proof['source_sha256'] = {str(f.relative_to(ROOT)): hashlib.sha256(
        f.read_bytes()).hexdigest() for f in files}
    if password is not None:
        route = dict(route, auth_mode='password', principal_reference='owned',
                     credential_references={'database_password': 'owned'})
    permissions = SimpleNamespace(
        require=lambda *_: None,
        acquire_secret=lambda *_: SecretLease(password.encode()))
    provider = create_provider(
        SimpleNamespace(
            endpoint_id=str(
                uuid.uuid4()), session_namespace=str(
                uuid.uuid4())), permissions)
    prefix = 'cde-driver-{' + uuid.uuid4().hex + '}:'
    native = None
    keys = []
    try:
        session = provider.open_session({'route': route})
        client = provider.client
        owner = provider._sessions[session['session_id']].handle
        native = owner.handle.client
        proof['runtime'] = client.runtime_identity({'route': route}, owner)
        proof['driver_version'] = client.backend.module.__version__

        def observe(token, allow_error=False):
            pages = []
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                value = provider.describe_result(token)
                payload = value['extensions']['redis']['payload']
                pages.append(payload)
                if value['complete']:
                    if not allow_error:
                        assert not payload.get('error'), payload
                    return pages
            raise AssertionError('Redis observation timed out')

        def query(source, target=None):
            if not isinstance(source, str):
                source = json.dumps(source)
            pages = observe(
                provider.execute(
                    dict(
                        target or session,
                        source=source)))
            return [row['value']
                    for p in pages for row in p.get('entries', [])]

        def key(name):
            result = prefix + name
            keys.append(result)
            return result

        binary = key('binary')
        query(['SET', binary, {'$binary': 'AP8='}])
        assert query(['GET', binary]) == [{'$binary': 'AP8='}]
        integer = key('integer')
        query(['SET', integer, {'$integer': '9007199254740993'}])
        assert query(['INCR', integer]) == [{'$integer': '9007199254740994'}]
        proof['checks'].append('binary-and-browser-unsafe-native-integers')
        transactional = key('transaction')
        observer = provider.open_session({'route': route})
        query(['WATCH', transactional])
        query(['MULTI'])
        query(['SET', transactional, 'must-abort'])
        query(['SET', transactional, 'other'], observer)
        assert query(['EXEC']) == [None]
        assert client.describe_transaction(
            owner)['native_state'] == 'watch-aborted'
        provider.control_transaction(dict(session, action='begin'))
        query(['SET', transactional, 'discard'])
        provider.control_transaction(dict(session, action='rollback'))
        assert query(['GET', transactional], observer) == ['other']
        provider.control_transaction(dict(session, action='begin'))
        query(['SET', transactional, 'committed'])
        query(['INCR', transactional])
        result = query(['EXEC'])
        assert result[0] in ('OK', True) and '$error' in result[1]
        assert query(['GET', transactional], observer) == ['committed']
        proof['checks'].append(
            'native-watch-abort-discard-and-exec-partial-command-error')
        # Large fixture insertion uses a native pipeline, not the driver's
        # scan.
        pipeline = native.pipeline(transaction=False)
        for i in range(10017):
            item = key('scan/' + str(i).zfill(6))
            pipeline.set(item, 'native')
        pipeline.execute()
        pages = observe(provider.execute(dict(session, source=json.dumps(
            dict(operation='scan', match=prefix + 'scan/*')))))
        found = [r['value'] for p in pages for r in p.get('entries', [])]
        assert len(found) == 10017 and len(set(found)) == 10017
        assert max(len(p.get('entries', [])) for p in pages) <= 256
        proof['checks'].append('10017-key-native-cursor-with-bounded-pages')
        channel = prefix + 'channel'
        stream = provider.execute(
            dict(
                session,
                source=json.dumps(
                    dict(
                        operation='subscribe',
                        channels=[channel],
                        limit=2,
                        timeout_seconds=5))))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            page = provider.describe_result(stream)
            payload = page['extensions']['redis']['payload']
            if payload.get('has_page'):
                break
            assert not page['complete'], payload
        else:
            raise AssertionError('Redis subscription acknowledgement missing')
        native.publish(channel, b'\0\xff')
        messages = observe(stream)
        assert 'AP8=' in json.dumps(messages)
        assert not owner.handle.pending_cleanup
        proof['checks'].append(
            'native-pubsub-binary-message-and-resource-release')
        monitor = provider.execute(dict(session, source=json.dumps(
            dict(operation='monitor', limit=1, timeout_seconds=3))))
        deadline = time.monotonic() + 3
        monitor_pages = []
        while time.monotonic() < deadline:
            native.ping()
            observed = provider.describe_result(monitor)
            monitor_pages.append(observed['extensions']['redis']['payload'])
            if observed['complete']:
                break
        assert any(p.get('has_page') for p in monitor_pages)
        events = [r['value'] for p in monitor_pages
                  for r in p.get('entries', [])]
        assert any(isinstance(v, str) and re.match(r'^\d+\.\d+ \[', v)
                   for v in events)
        proof['checks'].append('native-monitor-event-and-resource-release')

        if route.get('topology_mode', 'standalone') != 'cluster':
            # SELECT is session-local; a separate observer stays on route DB.
            query(['SELECT', 1])
            selected = key('selected')
            query(['SET', selected, 'db1'])
            assert query(['GET', selected], observer) == [None]
            query(['DEL', selected])
            query(['SELECT', 0])
            proof['checks'].append('select-stays-on-owned-connection')
        # The server acknowledges EXEC, then the client observation is lost.
        fault = provider.open_session({'route': route})
        fault_owner = provider._sessions[fault['session_id']].handle
        provider.control_transaction(dict(fault, action='begin'))
        query(['INCR', integer], fault)
        original = client.backend._command
        calls = []

        def lost_reply(handle, arguments):
            result = original(handle, arguments)
            if handle is fault_owner.handle and arguments[0].upper(
            ) == b'EXEC':
                calls.append('acknowledged')
                raise OSError('injected after native EXEC acknowledgement')
            return result

        client.backend._command = lost_reply
        try:
            final = observe(provider.execute(
                dict(fault, source='EXEC')), True)[-1]
            assert final['session_reuse_blocked'] and calls == ['acknowledged']
            assert query(['GET', integer], observer) == ['9007199254740995']
            provider.close_session(fault)
            assert calls == ['acknowledged']
        finally:
            client.backend._command = original
        proof['checks'].append('post-ack-exec-failure-no-replay')
        token = provider.execute(
            dict(
                session,
                source=json.dumps(
                    dict(
                        operation='scan',
                        match=prefix +
                        'scan/*'))))
        assert provider.cancel(token)
        cancelled = observe(token)[-1]
        assert cancelled['cancelled'] and cancelled['session_reuse_blocked']
        provider.close_session(session)
        proof['checks'].append('local-cancel-releases-owned-connection')
        proof['complete'] = True
    except Exception:
        proof['failures'].append(traceback.format_exc())
    finally:
        try:
            if native is not None and keys:
                for start in range(0, len(keys), 500):
                    native.delete(*keys[start:start + 500])
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
    parser.add_argument('--password-file', type=Path)
    args = parser.parse_args()
    result = run(
        json.loads(
            args.route.read_text()),
        args.evidence,
        args.password_file.read_text().strip() if args.password_file else None)
    print(json.dumps(
        {'complete': result['complete'], 'failures': result['failures']}))
    raise SystemExit(0 if result['complete'] else 1)

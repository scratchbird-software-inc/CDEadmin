#!/usr/bin/env python3
"""Portable source-bound YCQL driver qualification on an owned keyspace."""
import argparse
import hashlib
import getpass
import json
from pathlib import Path
import platform
import sys
import time
import traceback
from types import ModuleType, SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'web'))
sys.path.insert(0, str(ROOT))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package
from pgadmin.cdeadmin.providers.yugabytedb_ycql.provider import (  # noqa: E402
    create_provider, PROFILE,
)


def run(route, evidence, reply_loss=False, password=None):
    import cassandra
    evidence = Path(evidence).resolve()
    if evidence == ROOT or ROOT in evidence.parents:
        raise ValueError('Evidence must be outside repository')
    evidence.mkdir(parents=True, exist_ok=False)
    proof = dict(
        complete=False,
        cleanup_complete=False,
        checks=[],
        failures=[],
        platform=platform.platform(),
        python=platform.python_version(),
        cassandra_driver=cassandra.__version__)
    provider_dir = ROOT / 'web/pgadmin/cdeadmin/providers/yugabytedb_ycql'
    files = list(provider_dir.glob('*.py')) + [
        ROOT / 'web/pgadmin/cdeadmin/providers/cql_native.py',
        ROOT / 'web/pgadmin/cdeadmin/results/renderers.py',
        ROOT / 'tools/ycql_reply_loss_fixture.py',
        ROOT / 'web/pgadmin/cdeadmin/providers/postgresql/execution.py',
        Path(__file__)]
    proof['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(
        p.read_bytes()).hexdigest() for p in files}
    keyspace = 'cde_driver_' + uuid.uuid4().hex
    provider, session, handle = None, None, None
    owned = False
    proxy = None
    try:
        permissions = SimpleNamespace(require=lambda *_: None,
                                      acquire_secret=None)
        context = SimpleNamespace(endpoint_id=str(uuid.uuid4()),
                                  session_namespace=keyspace,
                                  pool_namespace=keyspace,
                                  cache_namespace=keyspace,
                                  provider_id=PROFILE.provider_id,
                                  profile_id=PROFILE.profile_id,
                                  profile_version=PROFILE.exact_version,
                                  provider_version='0.1.0')
        if password is not None:
            from pgadmin.cdeadmin.security import SecretLease
            route = dict(route, principal_reference='owned-ycql-gate',
                         credential_references={
                             'database_password': 'owned-ycql-password'})

            def acquire(reference, principal, purpose, kind):
                if (principal, purpose, kind) != (
                        'owned-ycql-gate', 'connect', 'database_password'):
                    raise ValueError('Invalid gate credential request')
                value = password if reference == 'owned-ycql-password' else (
                    'invalid-' + uuid.uuid4().hex)
                return SecretLease(value.encode('utf8'))

            permissions.acquire_secret = acquire
        provider = create_provider(context, permissions)
        session = provider.open_session({'route': route})
        client = provider.client
        handle = provider._sessions[session['session_id']].handle
        proof['runtime'] = client.runtime_identity({'route': route}, handle)
        proof['checks'].append('exact-ycql-native-and-version-api-identity')

        def observe(operation):
            pages = []
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                page = provider.describe_result(operation)
                pages.append(page)
                if page['complete']:
                    return pages
            raise AssertionError('YCQL operation did not terminate')

        def query(source, parameters=None):
            pages = observe(provider.execute(dict(session, source=source,
                                                  parameters=parameters)))
            payloads = [p['extensions']['yugabytedb']['payload']
                        for p in pages]
            if payloads[-1].get('error'):
                proof['native_error'] = payloads[-1]['error']
                raise AssertionError('Native YCQL execution failed')
            return [row for p in payloads for row in p['rows']]

        query('CREATE KEYSPACE ' + keyspace +
              " WITH replication = {'class':'SimpleStrategy',"
              "'replication_factor':1}")
        owned = True
        table = keyspace + '.owned'
        query('CREATE TABLE ' + table + '(tenant int, id int, i bigint, '
              'd decimal, b blob, t text, '
              'attrs map<int,text>, tags set<text>, '
              "PRIMARY KEY((tenant),id)) "
              "WITH transactions={'enabled':true}")
        values = [
            1, 1, {
                'type': 'integer', 'value': '9223372036854775807'}, {
                'type': 'decimal', 'value': '1234567890.123456789123456789'}, {
                'type': 'binary', 'value': 'AP8='}, 'Grüße 🌲', {
                    'type': 'map', 'value': [
                        [
                            7, 'seven']]}, {
                                'type': 'set', 'value': [
                                    'a', 'b']}]
        query('INSERT INTO ' + table +
              '(tenant,id,i,d,b,t,attrs,tags) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',
              values)
        row = query('SELECT i,d,b,t,attrs,tags FROM ' + table +
                    ' WHERE tenant=%s AND id=%s', [1, 1])[0]
        assert row['0'] == {'$integer': '9223372036854775807'}
        assert row['1'] == {'$decimal': '1234567890.123456789123456789'}
        assert row['2']['$binary'] == 'AP8=' and row['3'] == 'Grüße 🌲'
        assert row['4'] == {'$map': [[7, 'seven']]}
        assert row['5'] == {'$set': ['a', 'b']}
        proof['checks'].append('exact-scalar-and-collection-roundtrip')
        duplicate = query('SELECT i,i FROM ' + table + ' WHERE tenant=1')
        assert duplicate[0]['0'] == duplicate[0]['1']
        applied = query(
            'INSERT INTO ' +
            table +
            '(tenant,id,t) VALUES(1,1,\'duplicate\') IF NOT EXISTS')
        assert applied[0]['0'] is False
        proof['checks'].append(
            'ordinal-duplicate-columns-and-native-conditional')
        from cassandra.concurrent import execute_concurrent_with_args
        fill = handle.session.prepare(
            'INSERT INTO ' + table + '(tenant,id) VALUES(?,?)')
        outcomes = execute_concurrent_with_args(
            handle.session, fill, [(2, i) for i in range(10017)],
            concurrency=32, raise_on_first_error=False)
        assert all(success for success, _ in outcomes)
        pages = observe(
            provider.execute(
                dict(
                    session,
                    source='SELECT id FROM ' +
                    table +
                    ' WHERE tenant=2')))
        payloads = [p['extensions']['yugabytedb']['payload'] for p in pages]
        assert not payloads[-1].get('error')
        rows = [row for p in payloads for row in p['rows']]
        assert len(rows) == 10017
        assert len({r['0'] for r in rows}) == 10017
        assert max(len(p['rows']) for p in payloads) <= 256
        proof['checks'].append('native-paging-beyond-old-ten-thousand-cutoff')
        operation = provider.execute(
            dict(
                session,
                source='SELECT id FROM ' +
                table +
                ' WHERE tenant=2'))
        provider.cancel(operation)
        stopped = observe(operation)[-1]['extensions']['yugabytedb']['payload']
        assert stopped['local_delivery_stopped']
        assert stopped['server_cancellation_confirmed'] is False
        assert query('SELECT count(*) FROM ' + table +
                     ' WHERE tenant=2')[0]['0'] == 10017
        proof['checks'].append('local-stop-does-not-infer-server-rollback')
        from cassandra.policies import FallthroughRetryPolicy
        assert isinstance(handle.cluster.default_retry_policy,
                          FallthroughRetryPolicy)
        proof['checks'].append('native-fallthrough-policy-no-mutation-retry')
        if reply_loss:
            if route.get('tls_mode') != 'disabled':
                raise ValueError('Fault injection needs explicit plaintext')
            from tools.ycql_reply_loss_fixture import YCQLReplyLoss
            statement = 'INSERT INTO ' + table + \
                "(tenant,id,t) VALUES(3,1,'once')"
            proxy = YCQLReplyLoss(route['host'], route['port'], statement)
            fault_route = dict(route, host='127.0.0.1', port=proxy.port,
                               compression='none')
            fault = provider.open_session({'route': fault_route})
            failure = observe(provider.execute(dict(fault, source=statement)))
            payload = failure[-1]['extensions']['yugabytedb']['payload']
            assert payload['session_reuse_blocked']
            assert proxy.acknowledged.wait(5) and proxy.dispatches == 1
            assert query('SELECT count(*) FROM ' + table +
                         ' WHERE tenant=3')[0]['0'] == 1
            try:
                provider.execute(dict(fault, source=statement))
            except RuntimeError:
                pass
            else:
                raise AssertionError('Unknown YCQL outcome was replayable')
            provider.close_session(fault)
            proxy.close()
            proxy = None
            proof['checks'].append(
                'decoded-mutation-reply-loss-without-replay')
        if password is not None:
            try:
                unexpected = provider.open_session({'route': dict(
                    route, credential_references={
                        'database_password': 'owned-invalid-password'})})
            except RuntimeError:
                pass
            else:
                provider.close_session(unexpected)
                raise AssertionError('Invalid password accepted')
            proof['checks'].append(
                'native-password-authentication-and-refusal')
        query('DROP TABLE ' + table)
        query('DROP KEYSPACE ' + keyspace)
        owned = False
        provider.close_session(session)
        session = None
        assert not client._sessions and not client._owned_operations
        proof['checks'].append('native-session-and-cluster-release')
        proof['complete'] = True
    except Exception as exc:
        proof['failures'].append(dict(type=type(exc).__name__, locations=[
            dict(file=Path(f.filename).name, line=f.lineno)
            for f in traceback.extract_tb(exc.__traceback__)]))
    finally:
        try:
            try:
                if owned and handle is not None:
                    for token in provider.client._owned_operations:
                        token.cancel()
                        token.worker.join(20)
                    handle.session.execute(
                        'DROP TABLE IF EXISTS ' + keyspace + '.owned')
                    handle.session.execute('DROP KEYSPACE ' + keyspace)
            finally:
                try:
                    if provider is not None:
                        provider.client.close()
                finally:
                    if proxy is not None:
                        proxy.close()
            proof['cleanup_complete'] = True
        except Exception as exc:
            proof['complete'] = False
            proof['failures'].append(dict(phase='cleanup',
                                          type=type(exc).__name__))
        (evidence / 'summary.json').write_text(
            json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--reply-loss', action='store_true')
    parser.add_argument('--password-prompt', action='store_true')
    args = parser.parse_args()
    receipt = run(json.loads(args.route.read_text()), args.evidence,
                  args.reply_loss,
                  getpass.getpass('Password: ')
                  if args.password_prompt else None)
    sys.exit(0 if receipt['complete'] else 1)

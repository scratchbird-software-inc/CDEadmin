#!/usr/bin/env python3
"""Portable native Vitess driver qualification on an owned keyspace."""
import argparse
import getpass
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import traceback
from types import ModuleType, SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web')]
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package
from pgadmin.cdeadmin.providers.vitess.provider import (  # noqa: E402
    create_provider, PROFILE,
)
from tools.mysql_driver_gate_support import provider_access  # noqa: E402


def run(route, evidence, password=None, reply_loss=False):
    import mysql.connector as mysql
    from pgadmin.cdeadmin.providers.distributed_sql import mysql_route
    if not route.get('database') or 'password' in route:
        raise ValueError('Supply an owned keyspace route without password')
    evidence = Path(evidence).resolve()
    if evidence == ROOT or ROOT in evidence.parents:
        raise ValueError('Evidence must be outside repository')
    evidence.mkdir(parents=True, exist_ok=False)
    proof = dict(complete=False, cleanup_complete=False,
                 checks=[], failures=[],
                 platform=platform.platform(),
                 python=platform.python_version(),
                 mysql_connector=mysql.__version__)
    files = list((ROOT / 'web/pgadmin/cdeadmin/providers/vitess').glob('*.py'))
    files += [ROOT / ('web/pgadmin/cdeadmin/providers/' + name) for name in [
        'mysql_wire_driver.py', 'mysql_family/mysql_values.py',
        'mysql_family/mysql_connections.py', 'postgresql/execution.py',
        'distributed_sql.py']]
    files += [Path(__file__), ROOT / 'tools/mysql_reply_loss_fixture.py']
    proof['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(
        p.read_bytes()).hexdigest() for p in files}
    database = route['database']
    table = 'cde_driver_' + uuid.uuid4().hex
    admin, provider, proxy = None, None, None
    owned = False
    try:
        admin = mysql.connect(**dict(mysql_route(route),
                                     use_pure=route.get('use_pure', True),
                                     password=password or '',
                                     autocommit=True))
        cursor = admin.cursor()
        cursor.execute('CREATE TABLE ' + table +
                       '(id INT PRIMARY KEY, value VARCHAR(100))')
        owned = True
        cursor.close()
        request_route, permissions = provider_access(
            dict(route, database=database, autocommit=False), password)
        permissions.require = lambda *_: None
        context = SimpleNamespace(endpoint_id=str(uuid.uuid4()),
                                  session_namespace=database,
                                  pool_namespace=database,
                                  cache_namespace=database,
                                  provider_id=PROFILE.provider_id,
                                  profile_id=PROFILE.profile_id,
                                  profile_version=PROFILE.exact_version,
                                  provider_version='0.1.0')
        provider = create_provider(context, permissions)
        session = provider.open_session({'route': request_route})
        client = provider.client
        handle = provider._sessions[session['session_id']].handle
        proof['runtime'] = client.runtime_identity(
            {'route': request_route}, handle)
        if route.get('ssl_verify_identity'):
            cipher = handle._socket.sock.cipher()
            assert cipher
            proof['tls_cipher'] = cipher[0]
        proof['checks'].append('exact-native-runtime')

        def observe(operation):
            pages = []
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                page = provider.describe_result(operation)
                pages.append(page)
                if page['complete']:
                    return pages
            raise AssertionError('Vitess operation did not terminate')

        def payloads(pages):
            return [p['extensions']['vitess']['payload'] for p in pages]

        def query(source, parameters=None, target=None):
            source = source.replace('owned', table)
            pages = payloads(observe(provider.execute(dict(
                target or session, source=source, parameters=parameters))))
            if pages[-1].get('error'):
                proof['native_error'] = pages[-1]['error']
                raise AssertionError('Native query failed')
            return [list(row) for p in pages for row in p['rows']]

        result = query('SELECT CAST(%s AS UNSIGNED) AS same, '
                       'CAST(%s AS DECIMAL(38,18)) AS same, '
                       'CAST(%s AS BINARY), %s, NULL', [
                           {'encoding': 'integer',
                            'data': '18446744073709551615'},
                           {'encoding': 'decimal',
                            'data': '1234567890.123456789123456789'},
                           {'encoding': 'base64', 'data': 'AP8='}, 'Grüße 🌲'])
        assert result[0] == ['18446744073709551615',
                             '1234567890.123456789123456789',
                             {'encoding': 'base64', 'data': 'AP8=',
                              'byte_length': 2}, 'Grüße 🌲', None]
        assert query('SELECT %(n)s', {'n': 7}) == [[7]]
        pages = payloads(observe(provider.execute(dict(session, source=(
            'SELECT 1; SELECT a.n FROM (' + ' UNION ALL '.join(
                'SELECT '+str(i)+' AS n' for i in range(777)) + ') a')))))
        assert sum(len(p['rows']) for p in pages) == 778
        assert max(len(p['rows']) for p in pages) <= 256
        proof['checks'].append('exact-bindings-and-ordered-bounded-pages')
        query("INSERT INTO owned VALUES(1,'retained')")
        client.list_resources({'route': request_route,
                               '_provider_session_handle': handle})
        assert query('SELECT count(*) FROM owned') == [[1]]
        provider.control_transaction(dict(session, action='commit'))
        query("UPDATE owned SET value='discarded'")
        provider.control_transaction(dict(session, action='rollback'))
        assert query('SELECT value FROM owned') == [['retained']]
        provider.control_transaction(dict(session, action='rollback'))
        proof['checks'].append('decisions-and-metadata-preserve-user-work')
        failed = payloads(observe(provider.execute(dict(
            session, source='INSERT INTO '+table +
            " VALUES(1,'duplicate')"))))[-1]
        assert failed['error']['errno'] == 1062
        assert not failed['session_reuse_blocked']
        provider.control_transaction(dict(session, action='rollback'))
        proof['checks'].append('decoded-native-error-without-driver-replay')
        operation = provider.execute(
            dict(session, source='SELECT SLEEP(20) FROM '+table))
        token = provider._operations[operation['operation_id']].token
        deadline = time.monotonic() + 5
        while token.identity is None and time.monotonic() < deadline:
            time.sleep(.01)
        assert token.identity is not None
        time.sleep(.1)
        receipt = provider.cancel(operation)
        assert receipt['provider_receipt']['cancel_request_accepted']
        cancelled = payloads(observe(operation))[-1]
        assert cancelled['session_reuse_blocked']
        assert cancelled['outcome_unknown']
        provider.close_session(session)
        session = provider.open_session({'route': request_route})
        proof['checks'].append('retained-socket-abort-and-unknown-outcome')
        if reply_loss:
            if not route.get('ssl_disabled') or route['host'] not in {
                    '127.0.0.1', 'localhost', '::1'}:
                raise ValueError('Fault injection requires plaintext loopback')
            from tools.mysql_reply_loss_fixture import CommitReplyLoss
            proxy = CommitReplyLoss(route['host'], route['port'])
            fault = provider.open_session({'route': dict(
                request_route, host='127.0.0.1', port=proxy.port)})
            query("INSERT INTO owned VALUES(2,'lost reply')", target=fault)
            try:
                provider.control_transaction(dict(fault, action='commit'))
            except RuntimeError:
                pass
            else:
                raise AssertionError('Lost decision claimed success')
            assert proxy.commit_acknowledged.wait(5)
            assert provider.describe_transaction(fault)[
                'provider_payload']['session_reuse_blocked']
            observer = admin.cursor()
            try:
                observer.execute('SELECT count(*) FROM ' + table +
                                 ' WHERE id=2')
                assert observer.fetchone()[0] == 1
            finally:
                observer.close()
            try:
                provider.execute(dict(fault, source='SELECT 1'))
            except RuntimeError:
                pass
            else:
                raise AssertionError('Uncertain Vitess session was reusable')
            provider.close_session(fault)
            proxy.close()
            proxy = None
            proof['checks'].append(
                'decoded-commit-reply-loss-and-unknown-outcome')
        provider.close_session(session)
        pooled_route = dict(request_route, pool_name='owned', pool_size=1,
                            pool_reset_session=True)
        pooled = provider.open_session({'route': pooled_route})
        query('SET @private_owned_marker=17', target=pooled)
        provider.close_session(pooled)
        reused = provider.open_session({'route': pooled_route})
        assert query('SELECT @private_owned_marker', target=reused) == [[None]]
        provider.close_session(reused)
        assert not client._connections
        proof['checks'].append(
            'native-pool-physical-discard-and-fresh-session')
        proof['complete'] = True
    except Exception as exc:
        proof['failures'].append(dict(type=type(exc).__name__, locations=[
            dict(file=Path(f.filename).name, line=f.lineno)
            for f in traceback.extract_tb(exc.__traceback__)]))
    finally:
        try:
            try:
                if provider is not None:
                    provider.client.close()
            finally:
                if proxy is not None:
                    proxy.close()
            if owned:
                cursor = admin.cursor()
                cursor.execute('DROP TABLE ' + table)
                cursor.close()
            if admin is not None:
                admin.close()
            proof['cleanup_complete'] = True
        except Exception as exc:
            proof['complete'] = False
            proof['failures'].append(
                dict(
                    phase='cleanup',
                    type=type(exc).__name__))
        (evidence / 'summary.json').write_text(
            json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--no-password', action='store_true')
    parser.add_argument('--reply-loss', action='store_true')
    args = parser.parse_args()
    receipt = run(json.loads(args.route.read_text()), args.evidence,
                  None if args.no_password else getpass.getpass('Password: '),
                  args.reply_loss)
    sys.exit(0 if receipt['complete'] else 1)

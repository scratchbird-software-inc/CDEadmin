#!/usr/bin/env python3
"""Portable native TiDB driver qualification on an owned database."""
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
from pgadmin.cdeadmin.providers.tidb.provider import (  # noqa: E402
    create_provider, PROFILE,
)
from tools.mysql_driver_gate_support import provider_access  # noqa: E402


def run(route, evidence, password=None, reply_loss=False):
    import mysql.connector as mysql
    if any(k in route for k in ('database', 'password')):
        raise ValueError('Supply server route without database or password')
    evidence = Path(evidence).resolve()
    if evidence == ROOT or ROOT in evidence.parents:
        raise ValueError('Evidence must be outside repository')
    evidence.mkdir(parents=True, exist_ok=False)
    proof = dict(complete=False, cleanup_complete=False,
                 checks=[], failures=[],
                 platform=platform.platform(),
                 python=platform.python_version(),
                 mysql_connector=mysql.__version__)
    files = list((ROOT / 'web/pgadmin/cdeadmin/providers/tidb').glob('*.py'))
    files += [ROOT / ('web/pgadmin/cdeadmin/providers/' + name) for name in [
        'mysql_wire_driver.py', 'mysql_family/mysql_values.py',
        'mysql_family/mysql_connections.py', 'postgresql/execution.py',
        'distributed_sql.py']]
    files += [Path(__file__), ROOT / 'tools/mysql_reply_loss_fixture.py']
    proof['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(
        p.read_bytes()).hexdigest() for p in files}
    database = 'cde_driver_' + uuid.uuid4().hex
    admin, provider, proxy = None, None, None
    owned = False
    try:
        admin = mysql.connect(**dict(route, password=password or '',
                                     autocommit=True))
        cursor = admin.cursor()
        cursor.execute('CREATE DATABASE ' + database)
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
        status_cursor = handle.cursor()
        try:
            status_cursor.execute("SHOW SESSION STATUS LIKE 'Ssl_cipher'")
            row = status_cursor.fetchone()
            proof['tls_cipher'] = row[1] if row else None
            if route.get('ssl_verify_identity'):
                assert proof['tls_cipher']
        finally:
            status_cursor.close()
        proof['checks'].append('exact-native-runtime')

        def observe(operation):
            pages = []
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                page = provider.describe_result(operation)
                pages.append(page)
                if page['complete']:
                    return pages
            raise AssertionError('TiDB operation did not terminate')

        def payloads(pages):
            return [p['extensions']['tidb']['payload'] for p in pages]

        def query(source, parameters=None, target=None):
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
            'SELECT 1; WITH RECURSIVE seq AS (SELECT 1 AS n UNION ALL '
            'SELECT n+1 FROM seq WHERE n<777) SELECT n FROM seq')))))
        assert sum(len(p['rows']) for p in pages) == 778
        assert max(len(p['rows']) for p in pages) <= 256
        proof['checks'].append('exact-bindings-and-ordered-bounded-pages')
        query('CREATE TABLE owned(id INT PRIMARY KEY, value VARCHAR(100))')
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
        query("SET tidb_txn_mode='optimistic'")
        query('SET tidb_disable_txn_auto_retry=ON')
        query('SET tidb_retry_limit=0')
        query('BEGIN')
        query('SELECT value FROM owned WHERE id=1')
        other = mysql.connect(**dict(route, database=database,
                                     password=password or '', autocommit=True))
        try:
            cur = other.cursor()
            cur.execute("UPDATE owned SET value='concurrent' WHERE id=1")
            cur.close()
        finally:
            other.close()
        failed = payloads(observe(provider.execute(dict(
            session,
            source="UPDATE owned SET value='must not replay' "
                   "WHERE id=1"))))[-1]
        if failed.get('error'):
            assert failed['error']['transaction_retry_required']
        else:
            try:
                provider.control_transaction(dict(session, action='commit'))
            except RuntimeError:
                observation = provider.describe_transaction(session)[
                    'provider_payload']
                assert observation['transaction_retry_required']
                assert not observation['session_reuse_blocked']
            else:
                raise AssertionError('Expected native optimistic conflict')
        provider.control_transaction(dict(session, action='rollback'))
        assert query('SELECT value FROM owned') == [['concurrent']]
        proof['checks'].append(
            'native-optimistic-conflict-without-driver-replay')
        operation = provider.execute(dict(session, source='SELECT SLEEP(20)'))
        token = provider._operations[operation['operation_id']].token
        deadline = time.monotonic() + 5
        while token.identity is None and time.monotonic() < deadline:
            time.sleep(.01)
        assert token.identity is not None
        time.sleep(.1)
        receipt = provider.cancel(operation)
        assert receipt['provider_receipt']['cancel_request_accepted']
        cancelled = payloads(observe(operation))[-1]
        assert not cancelled['session_reuse_blocked']
        provider.control_transaction(dict(session, action='rollback'))
        assert query('SELECT 7') == [[7]]
        proof['checks'].append('native-origin-checked-tidb-query-cancellation')
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
                observer.execute('SELECT count(*) FROM ' + database +
                                 '.owned WHERE id=2')
                assert observer.fetchone()[0] == 1
            finally:
                observer.close()
            try:
                provider.execute(dict(fault, source='SELECT 1'))
            except RuntimeError:
                pass
            else:
                raise AssertionError('Uncertain TiDB session was reusable')
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
        proof['checks'].append('native-pool-reset-and-release')
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
                cursor.execute('DROP DATABASE ' + database)
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

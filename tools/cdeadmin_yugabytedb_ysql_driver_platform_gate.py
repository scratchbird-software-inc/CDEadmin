#!/usr/bin/env python3
"""Portable YugabyteDB YSQL driver proof through its real provider."""
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
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.providers.yugabytedb.provider import (  # noqa: E402
    create_provider, PROFILE,
)
from tools.mysql_driver_gate_support import provider_access  # noqa: E402


def run(route, evidence, password=None, reply_loss=False):
    import psycopg
    from psycopg import sql
    if any(k in route for k in ('database', 'dbname', 'password')):
        raise ValueError('Supply server options without database or password')
    evidence = Path(evidence).resolve()
    if evidence == ROOT or ROOT in evidence.parents:
        raise ValueError('Evidence must be outside the repository')
    evidence.mkdir(parents=True, exist_ok=False)
    proof = dict(
        complete=False,
        checks=[],
        failures=[],
        cleanup_complete=False,
        platform=platform.platform(),
        python=platform.python_version(),
        psycopg=psycopg.__version__,
        libpq=psycopg.pq.version())
    files = list(
        (ROOT / 'web/pgadmin/cdeadmin/providers/yugabytedb').glob('*.py'))
    files += [ROOT / 'web/pgadmin/cdeadmin/providers/distributed_sql.py',
              ROOT / 'web/pgadmin/cdeadmin/providers/pgwire_driver.py',
              ROOT / 'web/pgadmin/cdeadmin/providers/pgwire_catalog.py',
              ROOT / 'web/pgadmin/cdeadmin/providers/postgresql/execution.py',
              Path(__file__)]
    proof['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(
        p.read_bytes()).hexdigest() for p in files}
    database = 'cde_driver_' + uuid.uuid4().hex
    owned = False
    provider = None
    admin = None
    proxy = None
    try:
        admin = psycopg.connect(**dict(route, dbname='yugabyte',
                                       password=password, autocommit=True))
        admin.execute(sql.SQL('CREATE DATABASE {}').format(
            sql.Identifier(database)))
        owned = True
        request_route, permissions = provider_access(
            dict(route, database=database), password)
        permissions.require = lambda *_: None
        context = SimpleNamespace(
            endpoint_id=str(
                uuid.uuid4()),
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
        proof['checks'].append('exact-runtime-and-retained-session')

        def observe(operation):
            pages = []
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                result = provider.describe_result(operation)
                pages.append(result)
                if result['complete']:
                    return pages
            raise AssertionError('YugabyteDB YSQL result did not complete')

        def query(source, parameters=None, target=None):
            pages = observe(
                provider.execute(
                    dict(
                        target or session,
                        source=source,
                        parameters=parameters)))
            payloads = [p['extensions']['yugabytedb']['payload']
                        for p in pages]
            assert not payloads[-1].get('error'), payloads[-1].get('error')
            return [row for p in payloads for row in p['rows']]

        exact = query(
            'SELECT %(i)s::INT8 AS same, %(d)s::DECIMAL AS same, '
            '%(b)s::BYTEA, %(s)s::TEXT, NULL', {
                'i': {
                    'type': 'integer', 'value': '9223372036854775807'}, 'd': {
                    'type': 'decimal',
                    'value': '12345678901234567890.123456789'},
                'b': {
                    'type': 'binary', 'value': 'AP8='}, 's': 'Grüße 🌲'})
        assert exact == [
            ['9223372036854775807', '12345678901234567890.123456789',
             '\\x00ff', 'Grüße 🌲', None]]
        assert query('SELECT %s::INT', [42]) == [['42']]
        pages = observe(
            provider.execute(
                dict(
                    session,
                    source='SELECT 1; SELECT generate_series(1,777)')))
        payloads = [p['extensions']['yugabytedb']['payload'] for p in pages]
        assert sum(len(p['rows']) for p in payloads) == 778
        assert max(len(p['rows']) for p in payloads) <= 256
        proof['checks'].append('exact-bindings-and-ordered-bounded-pages')
        query('CREATE TABLE owned(id INT PRIMARY KEY, value TEXT)')
        provider.control_transaction(dict(session, action='commit'))
        query("INSERT INTO owned VALUES(1,'retained')")
        from pgadmin.cdeadmin.providers.pgwire_catalog import (
            CatalogConnection,
        )
        cursor = CatalogConnection(handle).cursor()
        try:
            assert cursor.cde_optional_rows(
                'SELECT * FROM nonexistent_owned_catalog') == []
        finally:
            cursor.close()
        resources = client.list_resources({
            'route': request_route, '_provider_session_handle': handle})
        assert any(r.get('native_name') == 'owned' or
                   r.get('display_name') == 'owned' for r in resources)
        assert query('SELECT count(*) FROM owned') == [['1']]
        provider.control_transaction(dict(session, action='commit'))
        query("UPDATE owned SET value='discarded'")
        provider.control_transaction(dict(session, action='rollback'))
        assert query('SELECT value FROM owned') == [['retained']]
        provider.control_transaction(dict(session, action='rollback'))
        proof['checks'].append(
            'decisions-and-metadata-do-not-rollback-user-work')
        query('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        query('SELECT value FROM owned WHERE id=1')
        with psycopg.connect(**dict(route, dbname=database,
                                    password=password)) as competitor:
            competitor.execute('SET statement_timeout=5000')
            competitor.execute(
                "UPDATE owned SET value='concurrent' WHERE id=1")
        failed = observe(provider.execute(dict(
            session,
            source="UPDATE owned SET value='must not replay' WHERE id=1")))
        failure = failed[-1]['extensions']['yugabytedb']['payload']
        assert failure['error']['sqlstate'] == '40001'
        assert failure['error']['transaction_retry_required']
        assert not failure['session_reuse_blocked']
        provider.control_transaction(dict(session, action='rollback'))
        assert query('SELECT count(*) FROM owned') == [['1']]
        proof['checks'].append('native-serialization-error-without-replay')
        operation = provider.execute(
            dict(session, source='SELECT pg_sleep(20)'))
        time.sleep(.2)
        provider.cancel(operation)
        cancellation = observe(
            operation)[-1]['extensions']['yugabytedb']['payload']
        assert cancellation['error']['sqlstate'] == '57014'
        provider.control_transaction(dict(session, action='rollback'))
        assert query('SELECT 7') == [['7']]
        proof['checks'].append('native-backend-key-cancellation')
        if reply_loss:
            if route.get('sslmode') != 'disable':
                raise ValueError(
                    'Reply loss requires explicit plaintext owned fixture')
            from tools.postgresql_reply_loss_fixture import CommitReplyLoss
            proxy = CommitReplyLoss(route['host'], route['port'])
            fault = provider.open_session(
                {'route': dict(request_route, host='127.0.0.1',
                               port=proxy.port)})
            query("INSERT INTO owned VALUES(2,'lost reply')", target=fault)
            try:
                provider.control_transaction(dict(fault, action='commit'))
                raise AssertionError('Lost commit response claimed success')
            except RuntimeError:
                pass
            assert proxy.acknowledged.wait(5)
            observation = provider.describe_transaction(fault)[
                'provider_payload']
            assert observation['session_reuse_blocked']
            try:
                provider.execute(
                    dict(fault, source='INSERT INTO owned VALUES(3,NULL)'))
                raise AssertionError('Uncertain session was reused')
            except RuntimeError:
                pass
            with psycopg.connect(**dict(
                    route, dbname=database, password=password)) as observer:
                assert observer.execute(
                    'SELECT count(*) FROM owned WHERE id=2').fetchone()[0] == 1
            provider.close_session(fault)
            proxy.close()
            proxy = None
            proof['checks'].append(
                'decoded-commit-reply-loss-and-no-duplicate-effects')
        provider.close_session(session)
        pooled_route = dict(request_route, pool_enabled=True, pool_min_size=1,
                            pool_max_size=1, pool_acquisition_timeout=2)
        pooled = provider.open_session({'route': pooled_route})
        query("SET application_name='private_previous_lease'", target=pooled)
        provider.control_transaction(dict(pooled, action='commit'))
        provider.close_session(pooled)
        reused = provider.open_session({'route': pooled_route})
        assert query('SHOW application_name', target=reused) != [
            ['private_previous_lease']]
        assert query('SELECT 11', target=reused) == [['11']]
        provider.close_session(reused)
        proof['checks'].append('pooled-lease-session-reset-and-reuse')
        if route.get('sslmode') == 'verify-full':
            assert admin.pgconn.ssl_in_use
            hostaddr = admin.info.hostaddr
            refusals = [
                dict(host='cde-driver-wrong-host.invalid', hostaddr=hostaddr),
                dict(user='cde_missing_' + uuid.uuid4().hex),
            ]
            if route.get('sslcert'):
                refusals.append(dict(sslrootcert=route['sslcert']))
            for changed in refusals:
                try:
                    unexpected = provider.open_session({
                        'route': dict(request_route, **changed)})
                except RuntimeError:
                    pass
                else:
                    provider.close_session(unexpected)
                    raise AssertionError('Invalid TLS/auth route accepted')
            proof['checks'].append('verified-tls-and-native-route-refusals')
        assert not client._connections
        proof['checks'].append('native-release')
        proof['complete'] = True
    except Exception as exc:
        locations = [{'file': Path(f.filename).name, 'line': f.lineno}
                     for f in traceback.extract_tb(exc.__traceback__)]
        proof['failures'].append({'type': type(exc).__name__,
                                  'locations': locations})
    finally:
        try:
            if provider is not None:
                provider.client.close()
            if proxy is not None:
                proxy.close()
            if owned:
                admin.execute(sql.SQL('DROP DATABASE {}').format(
                    sql.Identifier(database)))
            if admin is not None:
                admin.close()
            proof['cleanup_complete'] = True
        except Exception as exc:
            proof['complete'] = False
            proof['failures'].append(
                {'phase': 'cleanup', 'type': type(exc).__name__})
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
    result = run(json.loads(args.route.read_text()), args.evidence,
                 None if args.no_password else getpass.getpass('Password: '),
                 args.reply_loss)
    sys.exit(0 if result['complete'] else 1)

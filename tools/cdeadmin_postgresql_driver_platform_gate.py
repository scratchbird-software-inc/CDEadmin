#!/usr/bin/env python3
"""Portable PostgreSQL driver proof using the real application manager.

Creates only an isolated application configuration and temporary SQL objects.
Connection settings come from an explicit route file; password from a named
process environment variable or prompt. Never emits SQL or credential values.
"""
import argparse
import builtins
import hashlib
import json
import os
import platform
from pathlib import Path
import sys
import time
import traceback
import uuid
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'web'))


def qualify(route, password, evidence, *, reply_loss=False):
    evidence = Path(evidence).resolve()
    if evidence == ROOT or ROOT in evidence.parents:
        raise ValueError('Evidence must be outside the repository')
    evidence.mkdir(parents=True, exist_ok=False)
    receipt = {
        'complete': False,
        'checks': [],
        'failures': [],
        'platform': platform.platform(),
        'python': platform.python_version(),
        'scope': 'PostgreSQL native provider; platform UX separate'}
    builtins.SERVER_MODE = None
    import config
    config.SERVER_MODE = False
    config.TESTING = True
    config.DATA_DIR = str(evidence / 'app')
    config.SQLITE_PATH = str(evidence / 'app/application.db')
    config.SESSION_DB_PATH = str(evidence / 'app/sessions')
    config.STORAGE_DIR = str(evidence / 'app/storage')
    config.LOG_FILE = str(evidence / 'app/application.log')
    config.AZURE_CREDENTIAL_CACHE_DIR = str(evidence / 'app/azure')
    from pgadmin import create_app
    from pgadmin.model import db, User, ServerGroup, Server
    from flask_login import login_user
    from pgadmin.utils.driver import get_driver
    from pgadmin.cdeadmin.security import SecretLease
    from pgadmin.cdeadmin.providers.postgresql.provider import (
        PostgreSQLProvider,
    )
    import psycopg
    receipt['psycopg'] = psycopg.__version__
    receipt['libpq'] = psycopg.pq.version()
    files = list(
        (ROOT / 'web/pgadmin/cdeadmin/providers/postgresql').glob('*.py'))
    files += list((ROOT / 'web/pgadmin/utils/driver/psycopg3').glob('*.py'))
    files += [Path(__file__)]
    receipt['source_sha256'] = {str(p.relative_to(ROOT)): hashlib.sha256(
        p.read_bytes()).hexdigest() for p in files}
    app = create_app('CDEadmin-postgresql-driver-proof')
    app.PGADMIN_RUNTIME = False
    provider = None
    try:
        with app.test_request_context('/'):
            user = User.query.first()
            login_user(user)
            group = ServerGroup(user_id=user.id, name='Owned driver proof')
            db.session.add(group)
            db.session.flush()
            server = Server(
                user_id=user.id,
                servergroup_id=group.id,
                name='Owned proof',
                host=route['host'],
                port=route['port'],
                username=route['user'],
                maintenance_db=route.get(
                    'database',
                    'postgres'),
                save_password=0,
                connection_params=route.get(
                    'connection_params',
                    {}))
            db.session.add(server)
            db.session.commit()
            driver = get_driver('psycopg3', app)
            context = SimpleNamespace(
                endpoint_id=str(
                    uuid.uuid4()),
                cache_namespace='owned-gate',
                session_namespace='owned-gate',
                provider_id='org.pgadmin.postgresql',
                provider_version='9.17.0',
                profile_id='postgresql-native',
                profile_version='18.3')

            def acquire(reference, principal, purpose, kind):
                assert (
                    reference,
                    principal,
                    purpose,
                    kind) == (
                    'proof-password',
                    'worker:proof',
                    'connect',
                    'database_password')
                return SecretLease(password.encode('utf8'))

            provider = PostgreSQLProvider(context, SimpleNamespace(
                require=lambda *_args: None, acquire_secret=acquire), driver)
            session = provider.open_session({'route': {
                'server_id': server.id, 'owner_id': user.id,
                'principal_reference': 'worker:proof',
                'credential_reference_id': 'proof-password'}})
            raw = provider._sessions[session['session_id']].connection.conn
            receipt['server_version'] = raw.info.server_version
            assert raw.info.server_version == 180003

            def execute(source, parameters=None):
                op = provider.execute(dict(session, source=source,
                                           parameters=parameters))
                pages = observe(op)
                assert not pages[-1].get('error')
                return [page for page in pages if page.get('has_page')]

            def observe(op):
                pages = []
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    result = provider.describe_result(op)
                    pages.append(result['extensions']['postgresql'])
                    if result['complete']:
                        return pages
                raise AssertionError('Native execution did not finish')

            pages = execute(
                "SELECT 9223372036854775807::bigint AS duplicate, "
                "1.234567890123456789::numeric AS duplicate, "
                "'infinity'::timestamp, '1 month 2 days'::interval, "
                "ARRAY[1,NULL,3], '[1,3)'::int4range, "
                "'{\"large\":9223372036854775807}'::jsonb, "
                "decode('00ff','hex'), NULL")
            row = pages[0]['rows'][0]
            assert row[:4] == ['9223372036854775807', '1.234567890123456789',
                               'infinity', '1 mon 2 days']
            assert row[4] == '{1,NULL,3}' and row[5] == '[1,3)'
            assert '9223372036854775807' in row[6]
            assert row[7] == r'\x00ff' and row[8] is None
            receipt['checks'].append(
                'exact-native-values-and-duplicate-columns')
            pages = execute(
                'SELECT generate_series(1,777); SELECT 42 AS answer')
            assert sum(len(p['rows']) for p in pages) == 778
            offsets = [p['row_offset'] for p in pages if p.get('has_page')]
            assert offsets[:4] == [
                0, 256, 512, 768]
            assert pages[-1]['rows'] == [['42']]
            receipt['checks'].append('bounded-ordered-multiple-results')
            pages = execute(
                'SELECT %(number)s::numeric, %(bytes)s::bytea', {
                    'number': {
                        'type': 'decimal', 'value': '12345678901234567890.01'},
                    'bytes': {
                        'type': 'binary', 'value': 'AP8='}})
            assert pages[0]['rows'] == [['12345678901234567890.01', r'\x00ff']]
            receipt['checks'].append('exact-bound-parameters')
            execute('CREATE TEMP TABLE owned_driver_proof (id integer)')
            execute('BEGIN; INSERT INTO owned_driver_proof VALUES(1)')
            provider.control_transaction(dict(session, action='rollback'))
            observed = execute('SELECT count(*) FROM owned_driver_proof')
            assert observed[0]['rows'] == [['0']]
            execute('BEGIN; INSERT INTO owned_driver_proof VALUES(2)')
            provider.control_transaction(dict(session, action='commit'))
            observed = execute('SELECT count(*) FROM owned_driver_proof')
            assert observed[0]['rows'] == [['1']]
            receipt['checks'].append('retained-commit-and-rollback')
            execute('BEGIN')
            failed = provider.execute(dict(session, source='SELECT 1/0'))
            assert observe(failed)[-1]['error']['sqlstate'] == '22012'
            decision = provider.control_transaction(
                dict(session, action='commit'))
            assert decision['provider_payload']['command_status'] == 'ROLLBACK'
            receipt['checks'].append('aborted-commit-reports-native-rollback')
            execute('BEGIN')
            op = provider.execute(dict(session, source='SELECT pg_sleep(20)'))
            deadline = time.monotonic() + 5
            active = psycopg.pq.TransactionStatus.ACTIVE
            while raw.info.transaction_status != active:
                if time.monotonic() > deadline:
                    raise AssertionError('Native query did not become active')
                time.sleep(.01)
            try:
                provider.execute(dict(session, source='SELECT 999'))
            except RuntimeError:
                pass
            else:
                raise AssertionError('Concurrent command was admitted')
            provider.cancel(op)
            pages = observe(op)
            assert pages[-1]['error']['sqlstate'] == '57014'
            assert not pages[-1]['session_reuse_blocked']
            provider.control_transaction(dict(session, action='rollback'))
            assert execute('SELECT 7')[0]['rows'] == [['7']]
            receipt['checks'].append('native-cancel-with-retained-session')
            # COPY uses the same native connection; existing PostgreSQL UI owns
            # import/export selection. Exercise both directions without files.
            with psycopg.Cursor(raw) as cur:
                with cur.copy('COPY owned_driver_proof FROM STDIN') as copier:
                    copier.write_row((3,))
                with cur.copy('COPY owned_driver_proof TO STDOUT') as copier:
                    output = b''.join(bytes(block) for block in copier)
                assert b'2\n' in output and b'3\n' in output
            receipt['checks'].append('native-copy-both-directions')
            manager = provider._sessions[session['session_id']].manager
            provider.close_session(session)
            assert not manager.connections
            receipt['checks'].append('delegated-manager-release')
            from pgadmin.utils.driver.psycopg3.connection import Connection
            captured = []
            original_initialize = Connection._initialize

            def fail_initialize(connection, *_args, **_kwargs):
                captured.append((connection.conn, connection.manager))
                raise RuntimeError('owned initialization fault')

            # Delegated managers are newly allocated for each session. Inject
            # on the actual connection class rather than an earlier manager.
            Connection._initialize = fail_initialize
            try:
                try:
                    provider.open_session({'route': {
                        'server_id': server.id, 'owner_id': user.id,
                        'principal_reference': 'worker:proof',
                        'credential_reference_id': 'proof-password'}})
                except RuntimeError:
                    pass
                else:
                    raise AssertionError('Initialization failure was ignored')
            finally:
                Connection._initialize = original_initialize
            assert len(captured) == 1 and captured[0][0].closed
            assert not captured[0][1].connections
            receipt['checks'].append('failed-initialization-attachment-closed')
            if reply_loss:
                qualify_reply_loss(provider, session, route, password, server,
                                   user, db, receipt)
            provider.close()
            receipt['complete'] = True
    except Exception as exc:
        receipt['failures'].append({'type': type(exc).__name__, 'locations': [
            {'file': Path(f.filename).name, 'line': f.lineno}
            for f in traceback.extract_tb(exc.__traceback__)]})
        if provider:
            try:
                with app.test_request_context('/'):
                    provider.close()
            except Exception as cleanup:
                receipt['failures'].append({'cleanup': type(cleanup).__name__})
    finally:
        (evidence / 'summary.json').write_text(
            json.dumps(receipt, indent=2) + '\n')
    return receipt


def qualify_reply_loss(provider, session, route, password, server, user, db,
                       receipt):
    import psycopg
    from postgresql_reply_loss_fixture import CommitReplyLoss
    if route.get('connection_params', {}).get('sslmode') != 'disable':
        raise ValueError('Reply loss requires explicitly disabled TLS')
    table = 'cdeadmin_reply_loss_' + uuid.uuid4().hex
    observer = psycopg.connect(host=route['host'], port=route['port'],
                               user=route['user'], password=password,
                               dbname=route.get('database', 'postgres'),
                               sslmode='disable', autocommit=True)
    proxy = CommitReplyLoss(route['host'], route['port'])
    failed_session = None
    try:
        observer.execute('CREATE TABLE ' + table + ' (id integer PRIMARY KEY)')
        # New registered endpoint routes only this owned session through the
        # fixture. Existing application servers/configuration are untouched.
        from pgadmin.model import Server
        isolated = Server(
            user_id=user.id,
            servergroup_id=server.servergroup_id,
            name='Reply loss fixture',
            host='127.0.0.1',
            port=proxy.port,
            username=route['user'],
            maintenance_db=route.get(
                'database',
                'postgres'),
            save_password=0,
            connection_params={
                'sslmode': 'disable'})
        db.session.add(isolated)
        db.session.commit()
        failed_session = provider.open_session({'route': {
            'server_id': isolated.id, 'owner_id': user.id,
            'principal_reference': 'worker:proof',
            'credential_reference_id': 'proof-password'}})
        raw = provider._sessions[failed_session['session_id']].connection.conn
        raw.execute('BEGIN')
        raw.execute('INSERT INTO ' + table + ' VALUES (1)')
        try:
            provider.control_transaction(dict(failed_session, action='commit'))
        except RuntimeError:
            pass
        else:
            raise AssertionError('Lost COMMIT reply reported success')
        assert proxy.acknowledged.wait(2)
        assert observer.execute(
            'SELECT count(*)::integer FROM ' +
            table).fetchone() == (
            1,
        )
        assert provider.describe_transaction(failed_session)[
            'provider_payload']['session_reuse_blocked']
        try:
            provider.execute(
                dict(
                    failed_session,
                    source='INSERT INTO ' +
                    table +
                    ' VALUES (1)'))
        except RuntimeError:
            pass
        else:
            raise AssertionError('Unknown session admitted a replay')
        provider.close_session(failed_session)
        failed_session = None
        receipt['checks'].append('committed-response-lost-no-replay')
    finally:
        if failed_session:
            provider.close_session(failed_session)
        proxy.close()
        observer.execute('DROP TABLE IF EXISTS ' + table)
        observer.close()


def main():
    import getpass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route', required=True, type=Path)
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--password-env')
    parser.add_argument('--reply-loss', action='store_true')
    args = parser.parse_args()
    route = json.loads(args.route.read_text())
    if set(route) - {'host', 'port', 'user', 'database', 'connection_params'}:
        parser.error('Route contains unknown or credential fields')
    password = (os.environ[args.password_env] if args.password_env else
                getpass.getpass('PostgreSQL password: '))
    result = qualify(
        route,
        password,
        args.evidence,
        reply_loss=args.reply_loss)
    print(json.dumps({'complete': result['complete'],
                      'checks': result['checks'],
                      'failures': result['failures']}))
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

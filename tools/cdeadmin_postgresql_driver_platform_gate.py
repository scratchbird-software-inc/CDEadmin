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


def qualify(route, password, evidence, *, reply_loss=False, multi_database=False, catalog_ddn=False, native_transform=False):
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
    files += list((ROOT / 'web/pgadmin/utils/sqlautocomplete').rglob('*.py'))
    files += list((ROOT / 'web/pgadmin/misc/templates/sqlautocomplete').rglob('*.sql'))
    files += list((ROOT / 'web/pgadmin/cdeadmin/results').glob('*.py'))
    files += [Path(__file__)]
    files += [ROOT / 'tools' / name for name in (
        'cdeadmin_postgresql_operator_qualification.py',
        'cdeadmin_postgresql_aggregate_qualification.py',
        'cdeadmin_postgresql_ssh_qualification.py')]
    if native_transform:
        files += [ROOT / 'tools/cdeadmin_postgresql_transform_qualification.py']
    if catalog_ddn:
        workspace = ROOT / 'web/pgadmin/cdeadmin/workspace'
        files += list(workspace.glob('postgresql*.py'))
        files += [workspace / name for name in ('firebird_catalog_export.py', 'firebird_catalog_import.py',
            'firebird_schema_plan.py', 'firebird_schema_apply.py', 'firebird_relational_review.py')]
        files += list((workspace / 'ddn').glob('*.mjs'))
        files += [ROOT / 'tools/cdeadmin_postgresql_catalog_qualification.py',
                  ROOT / 'web/pgadmin/static/vendor/ddn/current/resource-manifest.json']
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
            before_status = raw.info.transaction_status
            before_pid = raw.info.backend_pid
            checked = provider.validate_source_without_execution(dict(
                session, language_profile='postgresql-sql', script=True,
                source='CREATE FUNCTION never_executed() RETURNS integer '
                       'LANGUAGE SQL BEGIN ATOMIC SELECT 1; END; SELECT 2;'))
            assert checked['script_ready'] and len(checked['statements']) == 2
            assert raw.info.transaction_status == before_status
            assert raw.info.backend_pid == before_pid
            assert not provider.validate_source_without_execution(dict(
                session, language_profile='postgresql-sql', source='SELCT 1'))['grammar_valid']
            assert not raw.execute("SELECT EXISTS (SELECT 1 FROM pg_proc WHERE proname='never_executed')").fetchone()[0]
            raw.execute('SET standard_conforming_strings=off')
            assert not provider.validate_source_without_execution(dict(
                session, language_profile='postgresql-sql', script=True,
                source='SELECT 1'))['script_ready']
            raw.execute('SET standard_conforming_strings=on')
            receipt['checks'].append('offline-native-grammar-and-session-framing-no-execution')
            from pgadmin.cdeadmin.providers.postgresql.monitoring import PostgreSQLMonitor
            collector = PostgreSQLMonitor(provider.permissions, {
                **route, 'principal_reference': 'worker:proof',
                'credential_reference_id': 'proof-password',
            }, scope='database')
            try:
                first = collector.sample()
                second = collector.sample()
                assert first['transaction_completed'] and second['transaction_completed']
                assert first['transaction_refresh']['status'] == second['transaction_refresh']['status'] == 'completed'
                assert collector._connection.info.transaction_status == 0
                assert int(second['identity']['collector_pid']) != raw.info.backend_pid
                counters = second['groups']['database']['rows'][0]
                assert counters['rate_state'] == 'available'
                assert isinstance(counters['xact_commit'], str)
                assert isinstance(counters['rates_per_second']['xact_commit'], str)
                assert first['source_epoch'] == second['source_epoch']
                receipt['checks'].append('independent-monitoring-native-rates-with-host-type-loaders-and-completed-transactions')
            finally:
                collector.close()

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
                    pages.append({**result['extensions']['postgresql'], 'columns': result['schema']['columns']})
                    if result['complete']:
                        return pages
                raise AssertionError('Native execution did not finish')

            policy_table = 'scratchrobin_policy_' + uuid.uuid4().hex
            completion_schema = "srb_completion'\\\"" + uuid.uuid4().hex
            observer = psycopg.connect(host=route['host'], port=route['port'],
                user=route['user'], password=password, dbname=route['database'],
                autocommit=True, **route.get('connection_params', {}))
            try:
                observer.execute('CREATE TABLE ' + policy_table + ' (id integer)')
                from psycopg import sql
                observer.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(completion_schema)))
                observer.execute(sql.SQL('CREATE TABLE {}.quoted_item (value integer)').format(sql.Identifier(completion_schema)))
                assert provider.describe_transaction(session)['provider_payload']['autocommit'] is True
                execute('INSERT INTO ' + policy_table + ' VALUES (1)')
                assert int(observer.execute('SELECT count(*) FROM ' + policy_table).fetchone()[0]) == 1
                provider.control_transaction(dict(session, action='autocommit_off'))
                execute('INSERT INTO ' + policy_table + ' VALUES (2)')
                assert int(observer.execute('SELECT count(*) FROM ' + policy_table).fetchone()[0]) == 1
                try:
                    provider.control_transaction(dict(session, action='autocommit_on'))
                except Exception as error:
                    assert 'pending transaction' in str(error)
                else:
                    raise AssertionError('Policy change silently resolved pending work')
                assert raw.autocommit is False
                raw.execute(sql.SQL('SET LOCAL search_path TO {}, public').format(sql.Identifier(completion_schema)))
                completion = provider.complete(dict(session, full_source='SELECT * FROM scratchrobin_policy_',
                    source_before_cursor='SELECT * FROM scratchrobin_policy_'))
                assert any(policy_table in label for label in completion), 'Native table completion missing'
                qualified_prefix = sql.SQL('SELECT * FROM {}.quoted_').format(sql.Identifier(completion_schema)).as_string(raw)
                quoted = provider.complete(dict(session, full_source=qualified_prefix, source_before_cursor=qualified_prefix))
                assert any('quoted_item' in label for label in quoted), 'Quoted-schema completion missing'
                assert int(observer.execute('SELECT count(*) FROM ' + policy_table).fetchone()[0]) == 1
                assert int(raw.info.transaction_status) == 2
                receipt['checks'].append('native-shared-completion-preserves-pending-transaction-and-observer-isolation')
                provider.control_transaction(dict(session, action='rollback'))
                assert int(observer.execute('SELECT count(*) FROM ' + policy_table).fetchone()[0]) == 1
                execute('INSERT INTO ' + policy_table + ' VALUES (3)')
                provider.control_transaction(dict(session, action='commit'))
                assert int(observer.execute('SELECT count(*) FROM ' + policy_table).fetchone()[0]) == 2
                provider.control_transaction(dict(session, action='autocommit_on'))
                assert raw.autocommit is True
                receipt['checks'].append('shared-provider-autocommit-acknowledged-pending-refusal-native-visibility-commit-rollback')
            finally:
                if raw.info.transaction_status != 0:
                    raw.rollback()
                raw.autocommit = True
                observer.execute('DROP TABLE IF EXISTS ' + policy_table)
                observer.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(completion_schema)))
                observer.close()

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
            from pgadmin.cdeadmin.results.ddn_export import export_workspace
            import subprocess
            snapshot = export_workspace({'result_id':'native-proof', 'execution_id':'native-proof',
                'schema':{'columns':pages[0]['columns']}, 'complete':True,
                'export_coverage':{'stored_records':1,'exported_records':1}}, [row])
            runtime = (ROOT / 'web/pgadmin/static/vendor/ddn/current/ddn.mjs').as_uri()
            script = "import runtime from " + json.dumps(runtime) + ";" + """
              let text='';for await(const chunk of process.stdin) text+=chunk;
              const snapshot=JSON.parse(text),source=snapshot.files[snapshot.entry];
              const parsed=runtime.parse(source,snapshot.entry);
              const rows=parsed.declarations.find(x=>x.id==='rows').children;
              const workspace=runtime.createWorkspace(snapshot.files);
              try {const rendered=workspace.renderSync({entry:snapshot.entry,view:snapshot.view});
                if(rendered.diagnostics.some(x=>x.severity==='error')) throw new Error('DDN rendering failed');
              } finally {workspace.destroy();}
              process.stdout.write(rows[0].props.x_record.values_json);
            """
            exported = subprocess.run(['node','--input-type=module','-e',script],input=snapshot,
                capture_output=True,timeout=15,check=True)
            assert json.loads(exported.stdout) == row
            receipt['checks'].append('native-buffered-result-ddn-exact-values-duplicate-columns-and-public-renderer')
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
            if catalog_ddn:
                from cdeadmin_postgresql_catalog_qualification import qualify as qualify_catalog
                qualify_catalog(provider, route, password, server, user, receipt, evidence)
            original_admin_apply = provider.apply_admin_operation
            def record_admin_apply(plan):
                result = original_admin_apply(plan)
                payload = plan['provider_payload']
                receipt.setdefault('native_admin_task_proofs', []).append({
                    'task_id': payload['resource_kind'] + ':' + payload['operation_id'],
                    'statement': payload['statement'], 'read_only': payload['read_only'],
                    'native_execution_returned': True,
                    'transaction_outcome': result.get('transaction_outcome'),
                    'release_status': result.get('release_status'),
                })
                return result
            provider.apply_admin_operation = record_admin_apply
            try:
                qualify_admin_transactions(provider, driver, route, password, server, receipt)
                from cdeadmin_postgresql_operator_qualification import qualify as qualify_operator
                qualify_operator(provider, route, password, server, receipt)
                from cdeadmin_postgresql_aggregate_qualification import qualify as qualify_aggregate
                qualify_aggregate(provider, route, password, server, receipt)
                if native_transform:
                    from cdeadmin_postgresql_transform_qualification import qualify as qualify_transform
                    qualify_transform(provider, route, password, server, receipt)
            finally:
                provider.apply_admin_operation = original_admin_apply
            qualify_monitoring_service(provider, route, password, evidence, receipt)
            from cdeadmin_postgresql_ssh_qualification import qualify as qualify_ssh
            qualify_ssh(route, password, receipt)
            if multi_database:
                qualify_multiple_databases(provider, route, password, server, user, receipt)
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


def qualify_monitoring_service(provider, route, password, evidence, receipt):
    """An admitted collector never follows a subsequently changed service alias."""
    import psycopg
    from pgadmin.cdeadmin.workspace.postgresql_monitoring_host import PostgreSQLMonitoringHost
    from pgadmin.cdeadmin.providers.postgresql.monitoring import PostgreSQLMonitor
    service_file = evidence / 'owned-service.conf'
    original = os.environ.get('PGSERVICEFILE')
    raw = collector = None
    parameters = {'host': route['host'], 'port': route['port'], 'dbname': route['database'],
                  'user': route['user'], 'password': password, **route.get('connection_params', {})}
    assert all('\n' not in str(value) and '\r' not in str(value) for value in parameters.values())
    try:
        fd = os.open(service_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, 'w') as stream:
            stream.write('[scratchrobin_qa]\n' + '\n'.join(key + '=' + str(value) for key, value in parameters.items()))
        os.environ['PGSERVICEFILE'] = str(service_file)
        raw = psycopg.connect(service='scratchrobin_qa', autocommit=True)
        selected_oid = int(raw.execute('SELECT oid FROM pg_database WHERE datname=current_database()').fetchone()[0])
        resolved = PostgreSQLMonitoringHost._resolved_service(SimpleNamespace(conn=raw, db=route['database']))
        assert password not in json.dumps(resolved) and 'scratchrobin_qa' not in json.dumps(resolved)
        service_file.write_text('[scratchrobin_qa]\nhost=127.0.0.1\nport=1\ndbname=wrong\n')
        collector = PostgreSQLMonitor(provider.permissions, {**resolved, 'database_oid': selected_oid,
            'principal_reference': 'worker:proof', 'credential_reference_id': 'proof-password'})
        sample = collector.sample()
        assert sample['transaction_completed']
        assert int(sample['identity']['collector_pid']) != raw.info.backend_pid
        assert raw.info.transaction_status == 0 and collector._connection.info.transaction_status == 0
        receipt['checks'].append('native-service-monitoring-selected-peer-frozen-independent-attachment')
    finally:
        try:
            if collector:collector.close()
        finally:
            if raw:raw.close()
            if original is None:os.environ.pop('PGSERVICEFILE', None)
            else:os.environ['PGSERVICEFILE'] = original
            if service_file.exists():service_file.unlink()


def qualify_admin_transactions(provider, driver, route, password, server, receipt):
    """Administrative DDL must not settle the Explorer's pending changes."""
    import secrets
    import psycopg
    from psycopg import sql
    from unittest.mock import patch
    from pgadmin.utils.crypto import encrypt
    from pgadmin.utils.master_password import set_crypt_key, get_crypt_key
    from pgadmin.cdeadmin.providers.postgresql.provider import native_control
    set_crypt_key(secrets.token_urlsafe(32))
    present, key = get_crypt_key()
    assert present
    manager = driver.connection_manager(server.id)
    explorer = manager.connection()
    table = 'sr_admin_' + uuid.uuid4().hex
    families = [table + '_family', table + '_lost']
    class_name = table + '_é class'
    spaced_names = [' ' + table + '_space ', ' ' + table + '_renamed ']
    access_names = [table + '_index', table + '_heap']
    observer = psycopg.connect(host=route['host'], port=route['port'],
        user=route['user'], password=password, dbname=route.get('database', 'postgres'),
        autocommit=True, **route.get('connection_params', {}))
    try:
        status, _ = explorer.connect(password=encrypt(password, key))
        assert status
        oid = int(observer.execute('SELECT oid FROM pg_database WHERE datname=current_database()').fetchone()[0])
        observer.execute(sql.SQL('CREATE TABLE public.{} (value integer)').format(sql.Identifier(table)))
        explorer.conn.execute('BEGIN')
        explorer.conn.execute(sql.SQL('INSERT INTO public.{} VALUES (1)').format(sql.Identifier(table)))
        for index, family in enumerate(families):
            plan = provider.plan_admin_operation({'resource_kind': 'operator-family',
                'operation_id': 'create', 'draft': {'schema': 'public', 'name': family,
                'index_method': 'btree'}, '_provider_route': {'server_id': server.id, 'database_id': oid}})
            controls = []
            def control(raw, command):
                assert raw.info.backend_pid != explorer.conn.info.backend_pid
                controls.append(command)
                result = native_control(raw, command)
                if index and command == 'COMMIT':
                    raise OSError('owned lost administrative commit reply')
                return result
            with patch('pgadmin.cdeadmin.providers.postgresql.provider.native_control', side_effect=control):
                if index:
                    try:
                        provider.apply_admin_operation(plan)
                    except RuntimeError as exc:
                        assert 'outcome is unknown; do not replay' in str(exc)
                    else:
                        raise AssertionError('Lost commit was reported as known')
                    assert controls == ['BEGIN', 'SET LOCAL standard_conforming_strings = on', 'COMMIT']
                else:
                    result = provider.apply_admin_operation(plan)
                    assert result['transaction_outcome'] == 'committed'
                    assert result['release_status'] == 'confirmed'
            assert int(observer.execute('SELECT count(*) FROM pg_opfamily WHERE opfname=%s', (family,)).fetchone()[0]) == 1
            assert explorer.conn.info.transaction_status == 2
            assert int(observer.execute(sql.SQL('SELECT count(*) FROM public.{}').format(sql.Identifier(table))).fetchone()[0]) == 0
        explorer.conn.execute('ROLLBACK')
        assert int(observer.execute(sql.SQL('SELECT count(*) FROM public.{}').format(sql.Identifier(table))).fetchone()[0]) == 0
        class_plan = provider.plan_admin_operation({'resource_kind': 'operator-class',
            'operation_id': 'create', '_provider_route': {'server_id': server.id, 'database_id': oid},
            'draft': {'schema': 'public', 'name': class_name, 'index_method': 'btree',
                'data_type': 'pg_catalog.int4', 'family': 'public.' + families[0],
                'operators': [{'strategy': i, 'operator': 'pg_catalog.' + operator,
                    'operand_types': ['pg_catalog.int4', 'pg_catalog.int4']}
                    for i, operator in enumerate(['<', '<=', '=', '>=', '>'], 1)],
                'functions': [{'support': 1, 'function': 'pg_catalog.btint4cmp',
                    'argument_types': ['pg_catalog.int4', 'pg_catalog.int4']}]}})
        assert provider.apply_admin_operation(class_plan)['transaction_outcome'] == 'committed'
        observer.execute(sql.SQL('CREATE INDEX ON public.{} (value public.{})').format(
            sql.Identifier(table), sql.Identifier(class_name)))
        observer.execute(sql.SQL('INSERT INTO public.{} VALUES (2), (1)').format(sql.Identifier(table)))
        observer.execute('SET enable_seqscan=off')
        assert [row[0] for row in observer.execute(sql.SQL('SELECT value FROM public.{} ORDER BY value').format(sql.Identifier(table))).fetchall()] == [1, 2]
        native = {'schema': 'public', 'name': spaced_names[0], 'index_method': 'btree'}
        def spaced_action(action, draft):
            plan = provider.plan_admin_operation({'resource_kind': 'operator-family', 'operation_id': action,
                'draft': draft, '_provider_route': {'server_id': server.id, 'database_id': oid},
                'target_resource': {'extensions': {'postgresql': {'native': native}}}})
            return provider.apply_admin_operation(plan)
        spaced_action('create', native)
        spaced_action('alter', {'action': 'add_members', 'operators': [
            {'strategy': 1, 'operator': 'pg_catalog.<', 'operand_types': ['pg_catalog.int4', 'pg_catalog.int4']}]})
        assert int(observer.execute('SELECT count(*) FROM pg_amop m JOIN pg_opfamily f ON f.oid=m.amopfamily WHERE f.opfname=%s', (spaced_names[0],)).fetchone()[0]) == 1
        spaced_action('alter', {'action': 'drop_members', 'members': [
            {'kind': 'OPERATOR', 'number': 1, 'operand_types': ['pg_catalog.int4', 'pg_catalog.int4']}]})
        assert int(observer.execute('SELECT count(*) FROM pg_amop m JOIN pg_opfamily f ON f.oid=m.amopfamily WHERE f.opfname=%s', (spaced_names[0],)).fetchone()[0]) == 0
        spaced_action('alter', {'action': 'add_members', 'operators': [
            {'strategy': 1, 'operator': 'pg_catalog.<', 'operand_types': ['double precision', 'double precision']}]})
        spaced_action('alter', {'action': 'drop_members', 'members': [
            {'kind': 'OPERATOR', 'number': 1, 'operand_types': ['double precision', 'double precision']}]})
        receipt['checks'].append('native-multiword-type-operator-family-members')
        receipt['checks'].append('native-operator-family-add-drop-members')
        assert spaced_action('inspect', {})['result']['rows'][0]['name'] == spaced_names[0]
        spaced_action('alter', {'action': 'rename', 'value': spaced_names[1]})
        native['name'] = spaced_names[1]
        assert spaced_action('inspect', {})['result']['rows'][0]['name'] == spaced_names[1]
        spaced_action('drop', {'confirmation': spaced_names[1]})
        for access_name, method_type, handler in zip(access_names, ('INDEX', 'TABLE'),
                ('pg_catalog.bthandler', 'pg_catalog.heap_tableam_handler')):
            def access_action(operation, draft):
                plan = provider.plan_admin_operation({'resource_kind': 'access-method',
                    'operation_id': operation, 'draft': draft,
                    '_provider_route': {'server_id': server.id, 'database_id': oid},
                    'target_resource': {'extensions': {'postgresql': {'native': {'name': access_name}}}}})
                return provider.apply_admin_operation(plan)
            access_action('create', {'name': access_name, 'method_type': method_type, 'handler': handler})
            assert access_action('inspect', {})['result']['rows'][0]['name'] == access_name
            catalog_rows = provider._catalog.read('access-method', {'server_id': server.id, 'database_id': oid})
            discovered = next(row for row in catalog_rows if row['name'] == access_name)
            resources = provider.list_resources({'resource_kind': 'server',
                'resource_id': 'endpoint:qualification', 'authority_path': ['qualification'],
                'route': {'server_id': server.id, 'database_id': oid}, 'extensions': {'postgresql': {}}})
            selected = next(row for row in resources if row['resource_kind'] == 'access-method' and row['display_name'] == access_name)
            assert provider.inspect_resource(selected)['resource_id'] == selected['resource_id']
            assert int(discovered['oid']) > 0

            if method_type == 'INDEX':
                observer.execute(sql.SQL('CREATE OPERATOR CLASS public.{} DEFAULT FOR TYPE int4 USING {} AS '
                    'OPERATOR 1 pg_catalog.< (int4,int4), OPERATOR 2 pg_catalog.<= (int4,int4), '
                    'OPERATOR 3 pg_catalog.= (int4,int4), OPERATOR 4 pg_catalog.>= (int4,int4), '
                    'OPERATOR 5 pg_catalog.> (int4,int4), FUNCTION 1 pg_catalog.btint4cmp(int4,int4)').format(
                        sql.Identifier(access_name), sql.Identifier(access_name)))
                observer.execute(sql.SQL('CREATE INDEX {} ON public.{} USING {} (value)').format(
                    sql.Identifier(access_name), sql.Identifier(table), sql.Identifier(access_name)))
                observer.execute(sql.SQL('DROP INDEX public.{}').format(sql.Identifier(access_name)))
                observer.execute(sql.SQL('DROP OPERATOR CLASS public.{} USING {}').format(
                    sql.Identifier(access_name), sql.Identifier(access_name)))
                observer.execute(sql.SQL('DROP OPERATOR FAMILY public.{} USING {}').format(
                    sql.Identifier(access_name), sql.Identifier(access_name)))
            else:
                observer.execute(sql.SQL('CREATE TABLE public.{} (value int) USING {}').format(
                    sql.Identifier(access_name), sql.Identifier(access_name)))
                observer.execute(sql.SQL('INSERT INTO public.{} VALUES (7)').format(sql.Identifier(access_name)))
                assert observer.execute(sql.SQL('SELECT value FROM public.{}').format(sql.Identifier(access_name))).fetchone()[0] == 7
                observer.execute(sql.SQL('DROP TABLE public.{}').format(sql.Identifier(access_name)))
            access_action('drop', {'confirmation': access_name})
        receipt['checks'].append('native-index-and-table-access-method-create-use-inspect-drop')
        qualify_conversion_and_class_changes(provider, observer, server.id, oid, class_name, receipt)
        receipt['checks'].extend(['native-admin-independent-commit-preserves-explorer-transaction',
                                  'native-admin-lost-commit-reply-no-replay',
                                  'native-operator-class-signatures-quoted-name-and-index-execution',
                                  'native-admin-significant-whitespace-create-inspect-rename-drop'])
    finally:
        try:
            manager.release()
        finally:
            try:
                observer.execute(sql.SQL('DROP TABLE IF EXISTS public.{}').format(sql.Identifier(table)))
                observer.execute(sql.SQL('DROP OPERATOR CLASS IF EXISTS public.{} USING btree').format(sql.Identifier(class_name)))
                for access_name in access_names:
                    observer.execute(sql.SQL('DROP ACCESS METHOD IF EXISTS {} CASCADE').format(sql.Identifier(access_name)))
                for family in families + spaced_names:
                    observer.execute(sql.SQL('DROP OPERATOR FAMILY IF EXISTS public.{} USING btree').format(sql.Identifier(family)))
            finally:
                observer.close()


def qualify_conversion_and_class_changes(provider, observer, server_id, database_id, class_name, receipt):
    from psycopg import sql
    token = uuid.uuid4().hex
    schemas = ['sr_convert_' + token, 'sr_move_' + token]
    role = 'sr_owner_' + token
    conversion = {'schema': schemas[0], 'name': ' Conversion ü '}
    opclass = {'schema': 'public', 'name': class_name, 'index_method': 'btree'}
    def action(kind, operation, target, draft):
        plan = provider.plan_admin_operation({'resource_kind': kind, 'operation_id': operation,
            'draft': draft, '_provider_route': {'server_id': server_id, 'database_id': database_id},
            'target_resource': {'extensions': {'postgresql': {'native': dict(target)}}}})
        return provider.apply_admin_operation(plan)
    created_schemas, created_role = [], False
    try:
        for schema in schemas:
            observer.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            created_schemas.append(schema)
        observer.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
        created_role = True
        result = action('conversion', 'create', conversion, {**conversion, 'source_encoding':'UTF8',
            'target_encoding':'LATIN1', 'function':'pg_catalog.utf8_to_iso8859_1', 'default':True})
        assert result['transaction_outcome'] == 'committed'
        inspected = action('conversion','inspect',conversion,{})['result']['rows'][0]
        assert inspected['name'] == conversion['name'] and inspected['is_default'] is True
        observer.execute(sql.SQL('SET search_path={},pg_catalog').format(sql.Identifier(schemas[0])))
        try:
            assert observer.execute("SELECT encode(convert(decode('c3bc','hex'),'UTF8','LATIN1'),'hex')").fetchone()[0] == 'fc'
        finally:
            observer.execute('RESET search_path')
        for kind, target in [('conversion', conversion), ('operator-class', opclass)]:
            action(kind, 'alter', target, {'action':'rename','value':target['name']+'_renamed'})
            target['name'] += '_renamed'
            action(kind, 'alter', target, {'action':'schema','value':schemas[1]})
            target['schema'] = schemas[1]
            action(kind, 'alter', target, {'action':'owner','value':role})
            assert action(kind,'inspect',target,{})['result']['rows'][0]['name'] == target['name']
            catalog, name_field, namespace_field, owner_field = (
                ('pg_conversion','conname','connamespace','conowner') if kind == 'conversion' else
                ('pg_opclass','opcname','opcnamespace','opcowner'))
            query = sql.SQL('SELECT pg_get_userbyid(c.{owner}) FROM pg_catalog.{catalog} c '
                'JOIN pg_namespace n ON n.oid=c.{namespace} WHERE c.{name}=%s AND n.nspname=%s').format(
                owner=sql.Identifier(owner_field),catalog=sql.Identifier(catalog),
                namespace=sql.Identifier(namespace_field),name=sql.Identifier(name_field))
            assert observer.execute(query,(target['name'],target['schema'])).fetchone()[0] == role
            result = action(kind,'drop',target,{'confirmation':target['name'],'cascade':kind=='operator-class'})
            assert result['transaction_outcome']=='committed'
            assert action(kind,'inspect',target,{})['result']['rows']==[]
        receipt['checks'].append('native-conversion-create-default-encoding-use-inspect-rename-move-owner-drop')
        receipt['checks'].append('native-operator-class-inspect-rename-move-owner-explicit-cascade-drop')
    finally:
        for schema in reversed(created_schemas):
            observer.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
        # A failed move may have left the owned class in its original schema.
        for name in (class_name, class_name+'_renamed'):
            observer.execute(sql.SQL('DROP OPERATOR CLASS IF EXISTS public.{} USING btree CASCADE').format(sql.Identifier(name)))
        if created_role:
            observer.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))


def qualify_multiple_databases(provider, route, password, server, user, receipt):
    """Prove OID binding and independent decisions using native observers."""
    import psycopg
    from psycopg import sql
    admin = psycopg.connect(host=route['host'], port=route['port'],
        user=route['user'], password=password, dbname=route.get('database', 'postgres'),
        autocommit=True, **route.get('connection_params', {}))
    databases, sessions, observers = [], [], []
    def execute(session, statement):
        operation = provider.execute(dict(session, source=statement))
        deadline, rows = time.monotonic() + 15, []
        while time.monotonic() < deadline:
            result = provider.describe_result(operation)
            payload = result['extensions']['postgresql']
            if payload.get('error'):
                raise AssertionError('Unexpected native statement failure')
            rows.extend(payload.get('rows') or [])
            if result['complete']:
                return rows
            time.sleep(.01)
        raise AssertionError('Independent session did not complete')
    try:
        for suffix in ('a', 'b'):
            name = 'scratchrobin_qualification_' + uuid.uuid4().hex + suffix
            admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
            databases.append(name)
            oid = admin.execute('SELECT oid FROM pg_catalog.pg_database WHERE datname=%s', (name,)).fetchone()[0]
            observer = psycopg.connect(host=route['host'], port=route['port'],
                user=route['user'], password=password, dbname=name,
                autocommit=True, **route.get('connection_params', {}))
            observers.append(observer)
            observer.execute('CREATE TABLE public.owned_outcome (value integer)')
            session = provider.open_session({'route': {'server_id': server.id,
                'database_id': oid, 'owner_id': user.id,
                'principal_reference': 'worker:proof', 'credential_reference_id': 'proof-password'}})
            sessions.append(session)
            assert execute(session, 'SELECT current_database()') == [[name]]
        a, b = sessions
        assert a['provider_state']['connection_id'] != b['provider_state']['connection_id']
        execute(a, 'BEGIN; INSERT INTO public.owned_outcome VALUES (11)')
        execute(b, 'BEGIN; INSERT INTO public.owned_outcome VALUES (22)')
        assert all(observer.execute('SELECT count(*)::integer FROM public.owned_outcome').fetchone() == (0,)
                   for observer in observers)
        provider.control_transaction(dict(a, action='commit'))
        assert observers[0].execute('SELECT value FROM public.owned_outcome').fetchall() == [(11,)]
        assert observers[1].execute('SELECT count(*)::integer FROM public.owned_outcome').fetchone() == (0,)
        provider.control_transaction(dict(b, action='rollback'))
        assert execute(b, 'SELECT count(*) FROM public.owned_outcome') == [['0']]
        receipt['checks'].append('two-databases-independent-session-decisions')
        pending = provider.execute(dict(a, source='SELECT pg_sleep(20)'))
        raw = provider._sessions[a['session_id']].connection.conn
        deadline = time.monotonic() + 5
        while raw.info.transaction_status != psycopg.pq.TransactionStatus.ACTIVE:
            assert time.monotonic() < deadline
            time.sleep(.01)
        assert execute(b, 'SELECT 29') == [['29']]
        provider.cancel(pending)
        while time.monotonic() < deadline + 5:
            result = provider.describe_result(pending)
            if result['complete']:
                assert result['extensions']['postgresql']['error']['sqlstate'] == '57014'
                break
            time.sleep(.01)
        else:
            raise AssertionError('Independent cancellation did not complete')
        provider.control_transaction(dict(a, action='rollback'))
        observers[0].execute('SELECT pg_terminate_backend(%s)', (raw.info.backend_pid,))
        operation = provider.execute(dict(a, source='SELECT 31'))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            result = provider.describe_result(operation)
            if result['complete']:
                assert result['extensions']['postgresql']['session_reuse_blocked']
                break
            time.sleep(.01)
        else:
            raise AssertionError('Lost connection did not resolve to unavailable')
        assert execute(b, 'SELECT 37') == [['37']]
        receipt['checks'].append('database-session-cancel-and-loss-isolation')
        qualify_restricted_account(provider, route, admin, databases[1], user, receipt, observers[1])
    finally:
        try:
            for session in sessions:
                provider.close_session(session)
        finally:
            for observer in observers:
                observer.close()
            try:
                for name in databases:
                    admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
            finally:
                admin.close()


def qualify_restricted_account(provider, route, admin, database, user, receipt, catalog_admin):
    import secrets
    from psycopg import sql
    from pgadmin.model import db, Server
    from pgadmin.cdeadmin.security import SecretLease
    role = 'scratchrobin_qa_' + uuid.uuid4().hex
    password = secrets.token_urlsafe(32)
    endpoint = None
    restricted = None
    created = False
    try:
        admin.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(
            sql.Identifier(role), sql.Literal(password)))
        created = True
        endpoint = Server(user_id=user.id, servergroup_id=Server.query.first().servergroup_id,
            name='Owned restricted qualification', host=route['host'], port=route['port'],
            username=role, maintenance_db=database, save_password=0,
            connection_params=route.get('connection_params', {}))
        db.session.add(endpoint)
        db.session.commit()
        restricted = type(provider)(SimpleNamespace(**{**vars(provider.context),
            'endpoint_id': str(uuid.uuid4())}), SimpleNamespace(
                require=lambda *_: None,
                acquire_secret=lambda *_: SecretLease(password.encode('utf8'))), provider._driver)
        session = restricted.open_session({'route': {'server_id': endpoint.id, 'owner_id': user.id,
            'principal_reference': 'worker:restricted-proof', 'credential_reference_id': 'restricted-secret'}})
        operation = restricted.execute(dict(session, source='SELECT * FROM public.owned_outcome'))
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            result = restricted.describe_result(operation)
            if result['complete']:
                assert result['extensions']['postgresql']['error']['sqlstate'] == '42501'
                break
            time.sleep(.01)
        else:
            raise AssertionError('Permission failure did not complete')
        restricted.control_transaction(dict(session, action='rollback'))
        operation = restricted.execute(dict(session, source='SELECT current_user'))
        rows = []
        while time.monotonic() < deadline:
            result = restricted.describe_result(operation)
            rows.extend(result['extensions']['postgresql'].get('rows') or [])
            if result['complete']:
                assert rows == [[role]]
                break
            time.sleep(.01)
        else:
            raise AssertionError('Restricted session did not remain usable')
        receipt['checks'].append('native-permission-denial-without-privilege-fallback')
        # This privilege change is confined to the owned qualification database.
        # It cannot affect the registered demo database or another team's work.
        oid = admin.execute('SELECT oid FROM pg_catalog.pg_database WHERE datname=%s', (database,)).fetchone()[0]
        catalog_admin.execute('REVOKE SELECT ON pg_catalog.pg_proc FROM PUBLIC')
        try:
            observed = restricted.capture_catalog({'server_id': endpoint.id, 'owner_id': user.id,
                'database_id': oid, 'principal_reference': 'worker:restricted-proof',
                'credential_reference_id': 'restricted-secret'})
            unavailable = next(item for item in observed['observations'] if item['section'] == 'pg_proc')
            assert unavailable['available'] is False and unavailable['sqlstate'] == '42501'
            assert any(item['section'] == 'pg_class' and item['available'] for item in observed['observations'])
            assert any(item['resource_kind'] == 'table' for item in observed['resources'])
            assert not any(item['native'].get('catalog') == 'pg_proc' for item in observed['resources'])
        finally:
            catalog_admin.execute('GRANT SELECT ON pg_catalog.pg_proc TO PUBLIC')
        receipt['checks'].append('native-ddn-catalog-permission-isolation-and-explicit-incomplete-coverage')
    finally:
        try:
            if restricted:
                restricted.close()
        finally:
            if endpoint:
                db.session.delete(endpoint)
                db.session.commit()
            if created:
                admin.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))


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
    parser.add_argument('--native-transform', action='store_true', help='Qualify real PL/Python jsonb transforms; requires matching optional server libraries')
    parser.add_argument('--catalog-ddn', action='store_true', help='Qualify native DDN capture using an owned temporary schema')
    parser.add_argument('--multi-database', action='store_true',
                        help='Qualify two isolated databases; requires CREATEDB')
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
        reply_loss=args.reply_loss, multi_database=args.multi_database, catalog_ddn=args.catalog_ddn, native_transform=args.native_transform)
    print(json.dumps({'complete': result['complete'],
                      'checks': result['checks'],
                      'failures': result['failures']}))
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

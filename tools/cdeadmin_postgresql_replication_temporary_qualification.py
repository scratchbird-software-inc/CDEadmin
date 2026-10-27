"""Original replication backend, exported snapshots and authenticated receipts."""
import argparse
import builtins
import base64
import hashlib
import json
from pathlib import Path
import secrets
from decimal import Decimal
import sys
import time
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def qualify(output, *, browser_binary=None, driver_binary=None):
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    builtins.SERVER_MODE = None
    import config
    config.SERVER_MODE = False; config.TESTING = True; config.WTF_CSRF_ENABLED = False
    config.MASTER_PASSWORD_REQUIRED = False; config.USE_OS_SECRET_STORAGE = False
    for key, value in {'DATA_DIR': 'app', 'SQLITE_PATH': 'app/application.db', 'SESSION_DB_PATH': 'app/sessions',
                       'STORAGE_DIR': 'app/storage', 'LOG_FILE': 'app/application.log',
                       'AZURE_CREDENTIAL_CACHE_DIR': 'app/azure', 'CDEADMIN_OPERATION_STORE_PATH': 'app/operations.json'}.items():
        setattr(config, key, str(output / value))
    import psycopg
    from psycopg import sql
    from postgresql_qualification_support import server
    from pgadmin import create_app
    from pgadmin.model import db, User, ServerGroup, Server
    from pgadmin.cdeadmin.workspace import service_for_app
    from pgadmin.cdeadmin.workspace.postgresql_replication_temporary_jobs import ReplicationTemporaryCommands, ReplicationTemporaryResources
    from flask import url_for
    paths = [str(Path(__file__).relative_to(ROOT)),
             'web/pgadmin/cdeadmin/providers/postgresql/replication_temporary_slots.py',
             'web/pgadmin/cdeadmin/workspace/postgresql_replication_temporary_jobs.py',
             'web/pgadmin/cdeadmin/workspace/postgresql_replication_temporary_service.py',
             'web/pgadmin/cdeadmin/workspace/postgresql_replication_stream.py',
             'web/pgadmin/cdeadmin/providers/postgresql/replication_stream_options.py',
             'web/pgadmin/cdeadmin/providers/postgresql/replication_snapshot_copy.py',
             'web/pgadmin/cdeadmin/providers/postgresql/replication_snapshot_import.py',
             'web/pgadmin/cdeadmin/workspace/postgresql_snapshot_copy.py',
             'web/pgadmin/cdeadmin/workspace/postgresql_temporary_slot_jobs.py',
             'web/pgadmin/cdeadmin/workspace/service.py',
             'web/pgadmin/browser/server_groups/servers/__init__.py',
             'web/pgadmin/cdeadmin/providers/postgresql/replication_admission.py',
             'web/pgadmin/static/js/Dialogs/PostgresqlReplicationTemporarySlots.jsx',
             'web/pgadmin/static/js/Dialogs/PostgresqlContinuity.jsx']
    proof = {'complete': False, 'full_product_complete': False, 'history_testing': 'not run',
             'checks': [], 'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in paths}}
    app = create_app('ScratchRobin native retained replication snapshots')
    app.PGADMIN_RUNTIME = False; app.PGADMIN_INT_KEY = ''; app.run_before_app_start()
    client = app.test_client(); service = service_for_app(app); resources = []; flow_finished = False
    try:
        with server(output / 'fixture', server_options=('-c', 'wal_level=logical', '-c', 'wal_sender_timeout=5s'),
                    initdb_options=('--auth-host=scram-sha-256',)) as (route, password, owned):
            original_connect = psycopg.connect
            parameters = {'host': route['host'], 'port': route['port'], 'user': 'postgres',
                          'password': password, 'dbname': 'postgres', 'autocommit': True}
            database = "Native retained database ü '"; principal = 'owned_repl'; secret = secrets.token_urlsafe(32)
            with original_connect(**parameters) as control:
                control.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
                control.execute(sql.SQL('CREATE ROLE {} LOGIN REPLICATION PASSWORD {}').format(sql.Identifier(principal), sql.Literal(secret)))
            with original_connect(**{**parameters, 'dbname': database}) as observer:
                observer.execute('CREATE TABLE snapshot_rows(id INTEGER PRIMARY KEY)')
                observer.execute('INSERT INTO snapshot_rows VALUES(1)')
                with app.test_request_context('/'):
                    uid = User.query.first().id; group = ServerGroup.query.filter_by(user_id=uid).first()
                    app.blueprints['NODE-engine_type'].connector_visibility['postgresql'].set(True, user_id=uid)
                    registered = Server(user_id=uid, servergroup_id=group.id, name='Owned retained replication',
                        host=route['host'], port=route['port'], username=principal, maintenance_db=database,
                        save_password=0, connection_params={'sslmode': 'disable'})
                    db.session.add(registered); db.session.commit(); sid = registered.id
                    url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=sid)
                with client.session_transaction() as login:
                    login['_user_id'] = str(uid); login['_fresh'] = True
                connections = []; protocol_commands = []; blocked_imports = set()
                def replication_only(*args, **kwargs):
                    assert kwargs.get('replication') == 'database', 'Application attempted ordinary SQL admission'
                    connections.append({'replication': kwargs['replication'], 'database': kwargs.get('dbname'),
                                        'application_name': kwargs.get('application_name')})
                    return original_connect(*args, **kwargs)
                native_execute = psycopg.ClientCursor.execute
                native_copy = psycopg.ClientCursor.copy
                def replication_copy(cursor, command, *args, **kwargs):
                    if cursor.connection.info.get_parameters().get('replication') == 'database':
                        assert cursor.connection.info.transaction_status.name == 'INTRANS'
                        text = command.as_string(cursor.connection) if isinstance(command, sql.Composable) else str(command)
                        assert text.startswith('COPY (') and secret not in text
                        protocol_commands.append('COPY')
                    return native_copy(cursor, command, *args, **kwargs)
                def replication_command(cursor, command, *args, **kwargs):
                    if cursor.connection.info.get_parameters().get('replication') == 'database':
                        text = command.as_string(cursor.connection) if isinstance(command, sql.Composable) else str(command)
                        kind = text.lstrip().split(None, 1)[0]
                        assert kind in {'IDENTIFY_SYSTEM', 'SHOW', 'CREATE_REPLICATION_SLOT', 'DROP_REPLICATION_SLOT',
                                        'BEGIN', 'COMMIT', 'ROLLBACK', 'SELECT', 'LOCK', 'WITH', 'SET'}, text
                        if kind in {'SELECT', 'LOCK', 'COMMIT', 'ROLLBACK', 'WITH'}:
                            exporter_observation = text.startswith('SELECT datname, usename, application_name,')
                            assert cursor.connection.info.transaction_status.name == 'INTRANS' or exporter_observation
                        if kind == 'SET':
                            assert text == 'SET TRANSACTION SNAPSHOT %s'
                            assert cursor.connection.info.transaction_status.name == 'INTRANS'
                        if kind == 'BEGIN':
                            assert cursor.connection.info.transaction_status.name == 'IDLE'
                        assert secret not in text
                        protocol_commands.append(kind)
                        if (kind == 'SELECT' and text.startswith('SELECT datname, usename, application_name,') and
                                cursor.connection.info.get_parameters().get('application_name') in blocked_imports):
                            # Deliberately block this native metadata query to
                            # exercise cancellation while consumer opening is
                            # still in progress, before BEGIN or import.
                            command = text.replace('FROM pg_catalog.pg_stat_activity',
                                                   'FROM pg_catalog.pg_stat_activity, pg_catalog.pg_sleep(30)')
                    return native_execute(cursor, command, *args, **kwargs)
                target = 'postgresql-replication-database:' + database.encode('utf8').hex()
                def http(action, *, refused=False, selected_target=target, **fields):
                    request = {'database_target_id': selected_target, **fields}
                    if action in {'scope', 'review', 'start'}:
                        request['replication_access'] = {'password': secret}
                    response = client.post(url, json={'action': 'postgresql_replication_temporary_' + action, 'request': request})
                    value = response.get_json(); assert secret not in json.dumps(value)
                    if refused:
                        assert response.status_code < 500 and (response.status_code != 200 or not value.get('success')), value
                        return value
                    assert response.status_code == 200 and value.get('success'), (action, value)
                    return value['data']
                def wait_resource(identity, predicate):
                    deadline = time.monotonic() + 30
                    while True:
                        result = http('status', job_id=identity)
                        if predicate(result):
                            return result
                        assert time.monotonic() < deadline, result
                        time.sleep(.03)
                def wait_child(resource, identity, states):
                    deadline = time.monotonic() + 30
                    while True:
                        result = http('command_status', resource_id=resource, job_id=identity)
                        parent = http('status', job_id=resource)
                        if result['state'] in states and not parent.get('pending_command'):
                            return result
                        assert time.monotonic() < deadline, result
                        time.sleep(.03)
                def open_resource(import_from=None):
                    selected = {'max_lifetime_seconds': 300}
                    if import_from is not None:
                        selected['import_from_resource_id'] = import_from
                    reviewed = http('review', options=selected)
                    identity = reviewed['job_id']; resources.append(identity)
                    http('start', job_id=identity, review_digest=reviewed['review_digest'], confirmed=True)
                    return wait_resource(identity, lambda result: result.get('ready'))
                def run(resource, operation, options, *, failed=False):
                    if operation == 'snapshot_copy':
                        inspected = run(resource, 'snapshot_inspect', {'relation_oid': options['relation_oid']})
                        assert inspected['state'] == 'completed'
                    reviewed = http('command_review', resource_id=resource, operation=operation, options=options)
                    reviewed = wait_child(resource, reviewed['job_id'], {'reviewed'})
                    request = {'resource_id': resource, 'job_id': reviewed['job_id'], 'review_digest': reviewed['review_digest'], 'confirmed': True}
                    http('command_start', **request)
                    result = wait_child(resource, reviewed['job_id'], {'failed', 'unknown'} if failed else {'completed', 'unknown'})
                    before = len(connections)
                    again = http('command_start', **request)
                    assert again['state'] == result['state'] and len(connections) == before
                    return result
                def import_snapshot(snapshot, expected):
                    with observer.transaction():
                        observer.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
                        observer.execute(sql.SQL('SET TRANSACTION SNAPSHOT {}').format(sql.Literal(snapshot)))
                        assert observer.execute('SELECT id FROM snapshot_rows ORDER BY id').fetchall() == expected
                with patch.object(service.endpoint_service, 'workspace', side_effect=AssertionError('Ordinary SQL bootstrap forbidden')), \
                        patch('psycopg.connect', side_effect=replication_only), \
                        patch.object(psycopg.ClientCursor, 'execute', replication_command), \
                        patch.object(psycopg.ClientCursor, 'copy', replication_copy):
                    scope = http('scope')
                    assert scope['database_target_id'] == target and scope['sql_admission_performed'] is False
                    opened = open_resource(); resource = opened['job_id']
                    assert opened['sql_admission_performed'] is False
                    created = run(resource, 'logical_create', {'slot': 'sr_original', 'plugin': 'test_decoding', 'snapshot': 'export'})
                    assert created['state'] == 'completed' and created['native_command_acknowledged']
                    snapshot = created['native_acknowledgement']['snapshot']['snapshot_name']
                    observer.execute('INSERT INTO snapshot_rows VALUES(2)')
                    observed_commands = len(protocol_commands)
                    time.sleep(6)
                    for _ in range(2):
                        page = http('inventory', resource_id=resource, offset=0, limit=25)
                        page = wait_child(resource, page['job_id'], {'completed'})
                        assert not page['result']['slot_catalog_observed'] and page['result']['snapshot']['snapshot_name'] == snapshot
                    assert len(protocol_commands) == observed_commands
                    import_snapshot(snapshot, [(1,)])
                    proof['checks'].append('native-export-and-initial-view-survive-background-status-and-acknowledgement-reads')
                    refused = http('command_review', resource_id=resource, operation='physical_create', options={'slot': 'sr_blocked'})
                    refused = wait_child(resource, refused['job_id'], {'failed'})
                    assert not refused.get('native_dispatch_admitted')
                    import_snapshot(snapshot, [(1,)])
                    proof['checks'].append('unconfirmed-snapshot-invalidation-refused-without-a-native-command')
                    http('status', selected_target='postgresql-replication-database:' + b'other'.hex(), job_id=resource, refused=True)
                    scoped = client.post(url + '?database_target_id=postgresql-database:1', json={
                        'action': 'postgresql_replication_temporary_status', 'request': {'database_target_id': target, 'job_id': resource}})
                    assert scoped.status_code == 400
                    with app.test_request_context('/'):
                        row = db.session.get(Server, sid); original_namespace = row.endpoint_profile.cache_namespace
                        row.endpoint_profile.cache_namespace = str(uuid.uuid4()); db.session.commit()
                    http('command_review', resource_id=resource, operation='drop', options={'slot': 'sr_original', 'invalidate_snapshot': True}, refused=True)
                    with app.test_request_context('/'):
                        row = db.session.get(Server, sid); row.endpoint_profile.cache_namespace = original_namespace; db.session.commit()
                    import_snapshot(snapshot, [(1,)])
                    proof['checks'].append('native-database-interface-and-complete-provider-isolation-guards-preserve-original-snapshot')
                    run(resource, 'physical_create', {'slot': 'sr_reused', 'reserve_wal': True, 'invalidate_snapshot': True})
                    try:
                        import_snapshot(snapshot, [])
                    except psycopg.Error as error:
                        assert error.sqlstate == '42704'
                    else:
                        raise AssertionError('Native snapshot survived its next command')
                    run(resource, 'drop', {'slot': 'sr_reused'})
                    observer.execute("SELECT pg_create_physical_replication_slot('sr_reused')")
                    rejected = http('command_review', resource_id=resource, operation='drop', options={'slot': 'sr_reused'})
                    wait_child(resource, rejected['job_id'], {'failed'})
                    assert observer.execute("SELECT temporary FROM pg_replication_slots WHERE slot_name='sr_reused'").fetchone() == (False,)
                    proof['checks'].append('confirmed-command-invalidates-export-and-historical-name-cannot-drop-foreign-permanent-slot')
                    original_update = ReplicationTemporaryCommands.update; injected = []
                    def fail_after_ack(commands, record, **values):
                        if values.get('state') == 'completed' and not injected:
                            injected.append(True); raise OSError('owned publication failure after native acknowledgement')
                        return original_update(commands, record, **values)
                    with patch.object(ReplicationTemporaryCommands, 'update', fail_after_ack):
                        uncertain = run(resource, 'logical_create', {'slot': 'sr_acknowledged', 'plugin': 'test_decoding', 'snapshot': 'nothing'})
                    assert injected and uncertain['state'] == 'unknown' and uncertain['native_command_acknowledged']
                    assert observer.execute("SELECT temporary,active_pid::text FROM pg_replication_slots WHERE slot_name='sr_acknowledged'").fetchone() == (True, opened['backend_pid'])
                    proof['checks'].append('durable-native-acknowledgement-survives-later-storage-failure-without-replay')
                    failed = run(resource, 'logical_create', {'slot': 'sr_invalid', 'plugin': 'sr_plugin_missing', 'snapshot': 'nothing'}, failed=True)
                    assert not failed.get('native_command_acknowledged') and failed.get('native_error_sqlstate')
                    closed = wait_resource(resource, lambda result: result.get('worker_io_closed'))
                    assert closed['native_owner_connection_close_returned'] and not closed.get('remote_cleanup_inferred')
                    deadline = time.monotonic() + 10
                    while int(observer.execute('SELECT count(*) FROM pg_replication_slots WHERE temporary AND active_pid=%s', (int(opened['backend_pid']),)).fetchone()[0]):
                        assert time.monotonic() < deadline; time.sleep(.03)
                    assert observer.execute("SELECT temporary FROM pg_replication_slots WHERE slot_name='sr_reused'").fetchone() == (False,)
                    proof['checks'].append('native-error-ends-original-owner-removes-temporaries-and-preserves-foreign-slot')
                    fresh = open_resource(); fresh_id = fresh['job_id']
                    exported = run(fresh_id, 'logical_create', {'slot': 'sr_close_export', 'plugin': 'test_decoding', 'snapshot': 'export'})
                    final_snapshot = exported['native_acknowledgement']['snapshot']['snapshot_name']
                    http('release', job_id=fresh_id, confirmation=fresh_id)
                    wait_resource(fresh_id, lambda result: result.get('worker_io_closed'))
                    deadline = time.monotonic() + 10
                    while int(observer.execute("SELECT count(*) FROM pg_replication_slots WHERE slot_name='sr_close_export'").fetchone()[0]):
                        assert time.monotonic() < deadline; time.sleep(.03)
                    try:
                        import_snapshot(final_snapshot, [])
                    except psycopg.Error as error:
                        assert error.sqlstate == '42704'
                    else:
                        raise AssertionError('Snapshot remained usable after its owner ended')
                    before = len(connections)
                    receipts = http('command_list', resource_id=fresh_id, offset=0, limit=25)
                    assert receipts['jobs'] and http('status', job_id=fresh_id)['worker_io_closed']
                    assert len(connections) == before
                    proof['checks'].append('explicit-release-invalidates-native-export-and-offline-receipts-do-not-reconnect')
                    observer.execute("SELECT pg_drop_replication_slot('sr_reused')")
                    observer.execute('CREATE TABLE native_independent_snapshot_rows(id integer PRIMARY KEY)')
                    observer.execute('INSERT INTO native_independent_snapshot_rows VALUES(1)')
                    observer.execute(sql.SQL('GRANT SELECT ON native_independent_snapshot_rows TO {}').format(sql.Identifier(principal)))
                    independent_oid = observer.execute("SELECT 'native_independent_snapshot_rows'::regclass::oid::text").fetchone()[0]
                    exporter = open_resource(); exporter_id = exporter['job_id']
                    run(exporter_id, 'logical_create', {'slot': 'sr_independent', 'plugin': 'test_decoding', 'snapshot': 'export'})
                    consumer = open_resource(exporter_id); consumer_id = consumer['job_id']
                    assert consumer['backend_pid'] != exporter['backend_pid']
                    assert consumer['native_resource_id'] != exporter['native_resource_id']
                    assert consumer['snapshot_transaction_begin_acknowledged'] and consumer['snapshot_import_acknowledged']
                    assert consumer['snapshot_exporter_preverified'] and consumer['snapshot_exporter_postverified'] and consumer['snapshot_import_verified']
                    assert consumer['latest_native_inventory']['used_snapshot']['source_slot'] == 'sr_independent'
                    assert consumer['latest_native_inventory']['acknowledged_owned_slot_count'] == 0
                    observer.execute('INSERT INTO native_independent_snapshot_rows VALUES(2)')
                    http('release', job_id=exporter_id, confirmation=exporter_id)
                    wait_resource(exporter_id, lambda value: value.get('worker_io_closed'))
                    deadline = time.monotonic() + 10
                    while int(observer.execute("SELECT count(*) FROM pg_replication_slots WHERE slot_name='sr_independent'").fetchone()[0]):
                        assert time.monotonic() < deadline; time.sleep(.03)
                    page = run(consumer_id, 'snapshot_tables', {'schema': 'public', 'limit': 100})
                    assert any(row['relation_oid'] == independent_oid for row in page['native_acknowledgement']['native_result']['relations'])
                    copied = run(consumer_id, 'snapshot_copy', {'relation_oid': independent_oid})
                    response = client.post(url, data={'action': 'postgresql_replication_temporary_copy_download',
                        'payload': json.dumps({'database_target_id': target, 'resource_id': consumer_id, 'job_id': copied['job_id']})})
                    assert response.status_code == 200
                    raw = response.data; response.close()
                    assert hashlib.sha256(raw).hexdigest() == copied['snapshot_copy_artifact']['sha256']
                    observer.execute('CREATE TEMP TABLE independent_snapshot_delivered(id integer)')
                    with observer.cursor().copy('COPY independent_snapshot_delivered FROM STDIN (FORMAT binary)') as loading:
                        loading.write(raw)
                    assert observer.execute('SELECT id FROM independent_snapshot_delivered').fetchall() == [(1,)]
                    assert observer.execute('SELECT id FROM native_independent_snapshot_rows ORDER BY id').fetchall() == [(1,), (2,)]
                    assert http('status', job_id=consumer_id)['ready']
                    proof['checks'].append('independent-native-consumer-retains-import-and-exact-binary-copy-after-exporter-release-and-concurrent-commit')
                    run(consumer_id, 'snapshot_end', {'decision': 'commit'})
                    refused = http('command_review', resource_id=consumer_id, operation='drop', options={'slot': 'sr_independent'})
                    refused = wait_child(consumer_id, refused['job_id'], {'failed'})
                    assert not refused.get('native_dispatch_admitted')
                    http('release', job_id=consumer_id, confirmation=consumer_id)
                    wait_resource(consumer_id, lambda value: value.get('worker_io_closed'))
                    proof['checks'].append('independent-consumer-transaction-end-never-acquires-or-drops-the-exporters-source-slot')
                    exporter = open_resource(); exporter_id = exporter['job_id']
                    run(exporter_id, 'logical_create', {'slot': 'sr_import_expired', 'plugin': 'test_decoding', 'snapshot': 'export'})
                    reviewed_consumer = http('review', options={'max_lifetime_seconds': 300, 'import_from_resource_id': exporter_id})
                    http('review', options={'max_lifetime_seconds': 300, 'snapshot_import': reviewed_consumer['options']['snapshot_import']}, refused=True)
                    http('review', options={'max_lifetime_seconds': 300, 'import_from_resource_id': str(uuid.uuid4())}, refused=True)
                    http('release', job_id=exporter_id, confirmation=exporter_id)
                    wait_resource(exporter_id, lambda value: value.get('worker_io_closed'))
                    http('start', job_id=reviewed_consumer['job_id'], review_digest=reviewed_consumer['review_digest'], confirmed=True, refused=True)
                    assert http('status', job_id=reviewed_consumer['job_id'])['state'] == 'reviewed'
                    proof['checks'].append('consumer-start-rechecks-live-original-export-and-rejects-arbitrary-snapshot-metadata-and-foreign-resource-identities')
                    exporter = open_resource(); exporter_id = exporter['job_id']
                    run(exporter_id, 'logical_create', {'slot': 'sr_import_race', 'plugin': 'test_decoding', 'snapshot': 'export'})
                    reviewed_consumer = http('review', options={'max_lifetime_seconds': 300, 'import_from_resource_id': exporter_id})
                    from pgadmin.cdeadmin.providers.postgresql.replication_snapshot_import import install as native_install
                    def expire_after_begin(native, selected, acknowledge, dispatching):
                        def record_phase(values):
                            acknowledge(values)
                            if values.get('snapshot_transaction_begin_acknowledged'):
                                with original_connect(**{**parameters, 'dbname': database}) as control:
                                    control.execute('SELECT pg_terminate_backend(%s)', (int(selected['exporter_backend_pid']),))
                                    deadline = time.monotonic() + 10
                                    while int(control.execute('SELECT count(*) FROM pg_stat_activity WHERE pid=%s', (int(selected['exporter_backend_pid']),)).fetchone()[0]):
                                        assert time.monotonic() < deadline; time.sleep(.03)
                        return native_install(native, selected, record_phase, dispatching)
                    with patch('pgadmin.cdeadmin.providers.postgresql.replication_snapshot_import.install', expire_after_begin):
                        http('start', job_id=reviewed_consumer['job_id'], review_digest=reviewed_consumer['review_digest'], confirmed=True)
                        refused = wait_resource(reviewed_consumer['job_id'], lambda value: value.get('worker_io_closed'))
                    assert refused['snapshot_transaction_begin_acknowledged'] and refused['native_error_sqlstate'] == '42704'
                    assert not refused.get('snapshot_import_acknowledged') and not refused['ready']
                    http('release', job_id=exporter_id, confirmation=exporter_id)
                    wait_resource(exporter_id, lambda value: value.get('worker_io_closed'))
                    proof['checks'].append('native-expiration-after-BEGIN-preserves-42704-and-separate-BEGIN-ack-without-import-or-replay')
                    exporter = open_resource(); exporter_id = exporter['job_id']
                    exported = run(exporter_id, 'logical_create', {'slot': 'sr_import_publish', 'plugin': 'test_decoding', 'snapshot': 'export'})
                    reviewed_consumer = http('review', options={'max_lifetime_seconds': 300, 'import_from_resource_id': exporter_id})
                    resource_update = ReplicationTemporaryResources.update
                    def fail_import_publication(jobs, record, **values):
                        if record['job_id'] == reviewed_consumer['job_id'] and values.get('snapshot_import_verified'):
                            raise OSError('owned post-import publication failure')
                        return resource_update(jobs, record, **values)
                    with patch.object(ReplicationTemporaryResources, 'update', fail_import_publication):
                        http('start', job_id=reviewed_consumer['job_id'], review_digest=reviewed_consumer['review_digest'], confirmed=True)
                        uncertain = wait_resource(reviewed_consumer['job_id'], lambda value: value.get('worker_io_closed'))
                    assert uncertain['state'] == 'unknown' and uncertain['snapshot_import_acknowledged']
                    assert not uncertain.get('snapshot_import_verified') and not uncertain['ready']
                    assert http('status', job_id=exporter_id)['ready']
                    import_snapshot(exported['native_acknowledgement']['snapshot']['snapshot_name'], [(1,), (2,)])
                    before = len(connections)
                    repeated = http('start', job_id=uncertain['job_id'], review_digest=uncertain['review_digest'], confirmed=True)
                    assert repeated['state'] == 'unknown' and len(connections) == before
                    http('release', job_id=exporter_id, confirmation=exporter_id)
                    wait_resource(exporter_id, lambda value: value.get('worker_io_closed'))
                    proof['checks'].append('native-import-ack-survives-postverification-publication-failure-with-original-export-preserved-and-no-automatic-retry')
                    exporter = open_resource(); exporter_id = exporter['job_id']
                    exported = run(exporter_id, 'logical_create', {'slot': 'sr_import_cancel', 'plugin': 'test_decoding', 'snapshot': 'export'})
                    reviewed_consumer = http('review', options={'max_lifetime_seconds': 300, 'import_from_resource_id': exporter_id})
                    opening_id = reviewed_consumer['job_id']
                    blocked_imports.add('ScratchRobin repl temp ' + opening_id)
                    http('start', job_id=opening_id, review_digest=reviewed_consumer['review_digest'], confirmed=True)
                    deadline = time.monotonic() + 10
                    while True:
                        opening = http('status', job_id=opening_id)
                        if opening.get('backend_pid') and observer.execute('SELECT wait_event FROM pg_stat_activity WHERE pid=%s',
                                (int(opening['backend_pid']),)).fetchone() == ('PgSleep',):
                            break
                        assert time.monotonic() < deadline; time.sleep(.03)
                    http('release', job_id=opening_id, confirmation=opening_id)
                    cancelled_import = wait_resource(opening_id, lambda value: value.get('worker_io_closed'))
                    blocked_imports.clear()
                    assert cancelled_import['native_error_sqlstate'] == '57014'
                    assert not cancelled_import.get('snapshot_transaction_begin_acknowledged')
                    assert not cancelled_import.get('snapshot_import_acknowledged') and not cancelled_import['ready']
                    assert cancelled_import['native_owner_connection_close_returned']
                    assert http('status', job_id=exporter_id)['ready']
                    import_snapshot(exported['native_acknowledgement']['snapshot']['snapshot_name'], [(1,), (2,)])
                    http('release', job_id=exporter_id, confirmation=exporter_id)
                    wait_resource(exporter_id, lambda value: value.get('worker_io_closed'))
                    proof['checks'].append('independently-observed-native-metadata-block-during-consumer-opening-is-cancelled-with-57014-without-ending-the-exporter')
                    streamed = open_resource(); stream_id = streamed['job_id']
                    run(stream_id, 'logical_create', {'slot': 'sr_stream', 'plugin': 'test_decoding', 'snapshot': 'nothing'})
                    observer.execute('INSERT INTO snapshot_rows VALUES(3)')
                    before_flush = observer.execute("SELECT confirmed_flush_lsn::text FROM pg_replication_slots WHERE slot_name='sr_stream'").fetchone()[0]
                    def captured(value):
                        artifact = value['protocol_stream_artifact']
                        response = client.post(url, data={'action': 'postgresql_replication_temporary_stream_download',
                            'payload': json.dumps({'database_target_id': target, 'resource_id': stream_id, 'job_id': value['job_id']})})
                        assert response.status_code == 200 and response.mimetype == 'application/x-ndjson'
                        raw = response.data
                        response.close()
                        assert hashlib.sha256(raw).hexdigest() == artifact['sha256']
                        return [base64.b64decode(json.loads(line)['wire_base64'], validate=True) for line in raw.splitlines()]
                    selected = {'slot': 'sr_stream', 'max_messages': 3, 'max_duration_seconds': 3,
                                'plugin_options': [{'name': 'include-xids', 'value': '0'}]}
                    first = run(stream_id, 'logical_stream', selected)
                    assert first['state'] == 'completed' and first['native_command_acknowledged']
                    frames = captured(first)
                    assert len(frames) == 3 and all(frame[:1] == b'w' for frame in frames)
                    assert any(b'snapshot_rows' in frame[25:] and b'id[integer]:3' in frame[25:] for frame in frames)
                    assert first['native_acknowledgement']['capture']['native_command_completions'] == 2
                    assert observer.execute("SELECT confirmed_flush_lsn::text,active_pid::text FROM pg_replication_slots WHERE slot_name='sr_stream'").fetchone() == (before_flush, streamed['backend_pid'])
                    repeated = run(stream_id, 'logical_stream', selected)
                    assert captured(repeated) == []
                    assert repeated['protocol_stream_artifact']['stop_reason'] == 'native_stream_end'
                    proof['checks'].append('original-backend-COPY-BOTH-native-frame-capture-and-two-command-completions-without-replay-or-default-flush-advance')
                    http('release', job_id=stream_id, confirmation=stream_id)
                    wait_resource(stream_id, lambda value: value.get('worker_io_closed'))
                    streamed = open_resource(); stream_id = streamed['job_id']
                    run(stream_id, 'logical_create', {'slot': 'sr_stream_flush', 'plugin': 'test_decoding', 'snapshot': 'nothing'})
                    observer.execute('INSERT INTO snapshot_rows VALUES(4)')
                    selected['slot'] = 'sr_stream_flush'
                    flushed = run(stream_id, 'logical_stream', {**selected, 'acknowledge_flush': True})
                    flush_frames = captured(flushed)
                    receipt = flushed['native_acknowledgement']['capture']
                    positions = [int.from_bytes(frame[1:9], 'big') for frame in flush_frames]
                    maximum = max(positions)
                    assert receipt['last_sent_flush_lsn'] == f'{maximum >> 32:X}/{maximum & 0xffffffff:X}'
                    assert receipt['last_sent_flush_lsn'] == receipt['last_durable_data_start_lsn'] and receipt['application_apply_lsn'] == '0/0'
                    assert observer.execute("SELECT confirmed_flush_lsn >= %s::pg_lsn FROM pg_replication_slots WHERE slot_name='sr_stream_flush'", (receipt['last_sent_flush_lsn'],)).fetchone() == (True,)
                    preview = http('stream_preview', resource_id=stream_id, job_id=flushed['job_id'], offset='0', limit=1)
                    assert base64.b64decode(preview['rows'][0]['payload_base64']) == flush_frames[0][25:25 + 3072]
                    assert preview['next_offset']
                    next_page = http('stream_preview', resource_id=stream_id, job_id=flushed['job_id'], offset=preview['next_offset'], limit=1)
                    assert base64.b64decode(next_page['rows'][0]['payload_base64']) == flush_frames[1][25:25 + 3072]
                    refused = client.post(url + '?database_target_id=postgresql-database:1', data={
                        'action': 'postgresql_replication_temporary_stream_download',
                        'payload': json.dumps({'database_target_id': target, 'resource_id': stream_id, 'job_id': flushed['job_id']})})
                    assert refused.status_code == 400
                    http('release', job_id=stream_id, confirmation=stream_id)
                    wait_resource(stream_id, lambda value: value.get('worker_io_closed'))
                    streamed = open_resource(); stream_id = streamed['job_id']
                    run(stream_id, 'logical_create', {'slot': 'sr_stream_bounds', 'plugin': 'test_decoding', 'snapshot': 'nothing'})
                    observer.execute('INSERT INTO snapshot_rows VALUES(5)')
                    selected['slot'] = 'sr_stream_bounds'
                    bounded = run(stream_id, 'logical_stream', {**selected, 'max_capture_bytes': 1})
                    assert bounded['protocol_stream_artifact']['messages'] == '0'
                    assert bounded['protocol_stream_artifact']['stop_reason'] == 'byte_bound_before_frame'
                    assert captured(bounded) == []
                    http('stream_remove', resource_id=stream_id, job_id=bounded['job_id'], confirmation='not-this-capture', refused=True)
                    removed = http('stream_remove', resource_id=stream_id, job_id=bounded['job_id'], confirmation=bounded['job_id'])
                    assert removed['artifact_removed']
                    assert http('stream_remove', resource_id=stream_id, job_id=bounded['job_id'], confirmation=bounded['job_id'])['artifact_removed']
                    http('stream_preview', resource_id=stream_id, job_id=bounded['job_id'], offset='0', limit=1, refused=True)
                    http('release', job_id=stream_id, confirmation=stream_id)
                    wait_resource(stream_id, lambda value: value.get('worker_io_closed'))
                    proof['checks'].append('fsynced-only-flush-feedback-native-checkpoint-observation-byte-bound-exact-download-and-paged-preview')
                    publication = open_resource(); publication_id = publication['job_id']
                    run(publication_id, 'logical_create', {'slot': 'sr_stream_publication', 'plugin': 'test_decoding', 'snapshot': 'nothing'})
                    observer.execute('INSERT INTO snapshot_rows VALUES(6)')
                    with patch('pgadmin.cdeadmin.workspace.postgresql_replication_stream.durable_replace', side_effect=OSError('owned publication failure')):
                        interrupted = run(publication_id, 'logical_stream', {'slot': 'sr_stream_publication', 'max_messages': 3})
                    assert interrupted['state'] == 'unknown' and interrupted['native_command_acknowledged']
                    wait_resource(publication_id, lambda value: value.get('worker_io_closed'))
                    connections_before = len(connections)
                    inspected = http('stream_reconcile', resource_id=publication_id, job_id=interrupted['job_id'])
                    assert inspected['state'] == 'unknown' and inspected['protocol_stream_artifact']['state'] == 'verified'
                    assert len(connections) == connections_before
                    proof['checks'].append('stream-native-ack-survives-publication-failure-and-offline-inspection-never-promotes-outcome-or-replays')
                    cancelled = open_resource(); cancelled_id = cancelled['job_id']
                    run(cancelled_id, 'logical_create', {'slot': 'sr_stream_cancel', 'plugin': 'test_decoding', 'snapshot': 'nothing'})
                    queued = http('command_review', resource_id=cancelled_id, operation='logical_stream', options={
                        'slot': 'sr_stream_cancel', 'max_messages': None, 'max_duration_seconds': None, 'max_capture_bytes': None})
                    reviewed = wait_child(cancelled_id, queued['job_id'], {'reviewed'})
                    http('command_start', resource_id=cancelled_id, job_id=reviewed['job_id'], review_digest=reviewed['review_digest'], confirmed=True)
                    deadline = time.monotonic() + 10
                    while True:
                        running = http('command_status', resource_id=cancelled_id, job_id=reviewed['job_id'])
                        if running['state'] == 'active' and running.get('native_dispatch_admitted'):
                            break
                        assert time.monotonic() < deadline; time.sleep(.03)
                    http('command_cancel', resource_id=cancelled_id, job_id=reviewed['job_id'])
                    stopped = wait_child(cancelled_id, reviewed['job_id'], {'failed', 'unknown'})
                    assert not stopped.get('native_command_acknowledged')
                    wait_resource(cancelled_id, lambda value: value.get('worker_io_closed'))
                    inspected = http('stream_reconcile', resource_id=cancelled_id, job_id=stopped['job_id'])
                    assert inspected['protocol_stream_artifact']['state'] == 'partial'
                    assert not inspected.get('native_command_acknowledged')
                    deadline = time.monotonic() + 10
                    while int(observer.execute("SELECT count(*) FROM pg_replication_slots WHERE slot_name='sr_stream_cancel'").fetchone()[0]):
                        assert time.monotonic() < deadline; time.sleep(.03)
                    proof['checks'].append('native-stream-cancellation-closes-original-owner-and-partial-bytes-never-establish-command-completion')
                    schema = 'Native snapshot ü ".schema'; table = 'Rows ü ".table'
                    relation_name = sql.Identifier(schema, table)
                    observer.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
                    domain_name = sql.Identifier(schema, 'Amount domain ü')
                    enum_name = sql.Identifier(schema, 'Enum ü')
                    observer.execute(sql.SQL('CREATE DOMAIN {} AS numeric(50,10) CHECK(VALUE>=0)').format(domain_name))
                    observer.execute(sql.SQL("CREATE TYPE {} AS ENUM ('雪','plain')").format(enum_name))
                    observer.execute(sql.SQL('CREATE TABLE {} (id integer primary key,big bigint,amount numeric(50,10),payload bytea,label text,tags text[],occurred timestamptz,document jsonb,ip inet,domain_amount {},native_enum {})').format(relation_name, domain_name, enum_name))
                    observer.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO {}').format(sql.Identifier(schema), sql.Identifier(principal)))
                    observer.execute(sql.SQL('GRANT SELECT ON {} TO {}').format(relation_name, sql.Identifier(principal)))
                    materialized = sql.Identifier(schema, 'Materialized ü ".rows')
                    foreign = sql.Identifier(schema, 'Foreign ü ".rows')
                    observer.execute('CREATE EXTENSION postgres_fdw')
                    observer.execute(sql.SQL("CREATE SERVER native_snapshot_remote FOREIGN DATA WRAPPER postgres_fdw OPTIONS(host '127.0.0.1',port '5432',dbname {},sslmode 'disable')").format(sql.Literal(database)))
                    observer.execute(sql.SQL("CREATE USER MAPPING FOR {} SERVER native_snapshot_remote OPTIONS(user 'postgres',password {})").format(sql.Identifier(principal), sql.Literal(password)))
                    observer.execute(sql.SQL('GRANT USAGE ON FOREIGN SERVER native_snapshot_remote TO {}').format(sql.Identifier(principal)))
                    observer.execute(sql.SQL('CREATE FOREIGN TABLE {}(id integer,label text) SERVER native_snapshot_remote OPTIONS(schema_name {},table_name {})').format(foreign, sql.Literal(schema), sql.Literal(table)))
                    observer.execute(sql.SQL('INSERT INTO {} VALUES(%s,%s,%s,%s,%s,%s,%s::timestamptz,%s::jsonb,%s::inet,%s,%s)').format(relation_name),
                        (1, 9223372036854775807, Decimal('1234567890123456789012345678901234567890.1234567890'),
                         b'\0\xff\n,\t"\\', 'Native 雪 ü \' " \n \t \\N', ['雪', 'comma,x', None, ''],
                         '2026-10-20 12:34:56.999999-04', '{"native":[1,null,"雪"]}', '2001:db8::1/64',
                         Decimal('1234567890123456789012345678901234567890.1234567890'), '雪'))
                    expected_row = observer.execute(sql.SQL('SELECT * FROM {} WHERE id=1').format(relation_name)).fetchone()
                    observer.execute(sql.SQL('CREATE MATERIALIZED VIEW {} AS SELECT id,label FROM {}').format(materialized, relation_name))
                    observer.execute(sql.SQL('GRANT SELECT ON {},{} TO {}').format(materialized, foreign, sql.Identifier(principal)))
                    use = open_resource(); use_id = use['job_id']
                    used = run(use_id, 'logical_create', {'slot': 'sr_snapshot_use', 'plugin': 'test_decoding', 'snapshot': 'use'})
                    assert used['native_phase_acknowledgements'][0]['phase'] == 'snapshot_transaction_begin'
                    assert used['native_acknowledgement']['used_snapshot']['native_snapshot_installed']
                    assert http('status', job_id=use_id)['latest_native_inventory']['owns_snapshot_transaction']
                    observer.execute(sql.SQL('INSERT INTO {}(id,label) VALUES(2,%s)').format(relation_name), ('after original snapshot',))
                    listed = run(use_id, 'snapshot_tables', {'schema': schema, 'offset': 0, 'limit': 25})
                    page = listed['native_acknowledgement']['native_result']
                    selected_relation = next(row for row in page['relations'] if row['schema'] == schema and row['name'] == table)
                    assert selected_relation['can_select'] and not selected_relation['row_security_active'] and not page['more']
                    deliveries = []
                    for format, copy_options in [('binary', {}), ('text', {'delimiter': '|', 'null_string': '~null~'}),
                        ('csv', {'delimiter': ';', 'null_string': '~null~', 'header': True, 'force_quote': 'all', 'quote': '"', 'escape': '"', 'encoding': 'UTF8'})]:
                        copied = run(use_id, 'snapshot_copy', {'relation_oid': selected_relation['relation_oid'], 'format': format,
                                                             'copy_options': copy_options, 'include_descendants': True})
                        assert copied['state'] == 'completed' and copied['native_command_acknowledged']
                        artifact = copied['snapshot_copy_artifact']
                        assert artifact['rows'] == '1' and artifact['copy_format'] == format
                        domain_column = next(column for column in artifact['source']['columns'] if column['name'] == 'domain_amount')
                        assert domain_column['type_oid'] != domain_column['wire_type_oid'] and domain_column['wire_type_modifier'] > 0
                        response = client.post(url, data={'action': 'postgresql_replication_temporary_copy_download',
                            'payload': json.dumps({'database_target_id': target, 'resource_id': use_id, 'job_id': copied['job_id']})})
                        assert response.status_code == 200
                        raw = response.data; response.close()
                        assert hashlib.sha256(raw).hexdigest() == artifact['sha256']
                        observer.execute('CREATE TEMP TABLE delivered_snapshot (LIKE ' + relation_name.as_string(observer) + ' INCLUDING ALL)')
                        native_options = [sql.SQL('FORMAT {}').format(sql.SQL(format))]
                        for key, value in copy_options.items():
                            if key == 'force_quote':
                                continue
                            native_options.append(sql.SQL('{} {}').format(sql.SQL({'null_string': 'NULL'}.get(key, key.upper())),
                                sql.SQL('true') if value is True else sql.Literal(value)))
                        with observer.cursor().copy(sql.SQL('COPY delivered_snapshot FROM STDIN ({})').format(sql.SQL(', ').join(native_options))) as loading:
                            loading.write(raw)
                        assert observer.execute('SELECT * FROM delivered_snapshot').fetchall() == [expected_row]
                        observer.execute('DROP TABLE delivered_snapshot')
                        sample = http('copy_preview', resource_id=use_id, job_id=copied['job_id'], offset='0', length=16)
                        assert base64.b64decode(sample['data_base64']) == raw[:16]
                        deliveries.append({'format': format, 'rows': artifact['rows'], 'exact_native_import_verified': True})
                    for native_kind, name, expected in [('m', 'Materialized ü ".rows', [(1, expected_row[4])]),
                        ('f', 'Foreign ü ".rows', [(1, expected_row[4]), (2, 'after original snapshot')])]:
                        source = next(row for row in page['relations'] if row['name'] == name)
                        assert source['native_kind'] == native_kind
                        copied = run(use_id, 'snapshot_copy', {'relation_oid': source['relation_oid']})
                        assert copied['state'] == 'completed'
                        response = client.post(url, data={'action': 'postgresql_replication_temporary_copy_download',
                            'payload': json.dumps({'database_target_id': target, 'resource_id': use_id, 'job_id': copied['job_id']})})
                        assert response.status_code == 200
                        raw = response.data; response.close()
                        observer.execute('CREATE TEMP TABLE delivered_snapshot_aux(id integer,label text)')
                        with observer.cursor().copy('COPY delivered_snapshot_aux FROM STDIN (FORMAT binary)') as loading:
                            loading.write(raw)
                        assert observer.execute('SELECT * FROM delivered_snapshot_aux ORDER BY id').fetchall() == expected
                        observer.execute('DROP TABLE delivered_snapshot_aux')
                        deliveries.append({'native_kind': native_kind, 'format': 'binary', 'rows': copied['snapshot_copy_artifact']['rows'],
                            'exact_native_import_verified': True, 'remote_snapshot_synchronization_observed': False if native_kind == 'f' else None})
                    ended = run(use_id, 'snapshot_end', {'decision': 'commit'})
                    assert ended['native_command_acknowledged'] and not ended['native_acknowledgement']['used_snapshot']
                    assert not http('status', job_id=use_id)['latest_native_inventory']['owns_snapshot_transaction']
                    assert observer.execute("SELECT active_pid::text FROM pg_replication_slots WHERE slot_name='sr_snapshot_use'").fetchone() == (use['backend_pid'],)
                    bridge = run(use_id, 'logical_stream', {'slot': 'sr_snapshot_use', 'max_messages': 3})
                    assert bridge['state'] == 'completed' and bridge['native_command_acknowledged']
                    bridged = http('stream_preview', resource_id=use_id, job_id=bridge['job_id'], offset='0', limit=25)
                    assert any(b'id[integer]:2' in base64.b64decode(row['payload_base64']) for row in bridged['rows'])
                    http('release', job_id=use_id, confirmation=use_id)
                    wait_resource(use_id, lambda value: value.get('worker_io_closed'))
                    proof['snapshot_copy_formats'] = deliveries
                    proof['checks'].append('owned-SNAPSHOT-USE-first-command-native-type-exact-binary-text-CSV-initial-copies-and-same-backend-WAL-bridge')
                    observer.execute('CREATE TABLE native_snapshot_rls(id integer)')
                    observer.execute('INSERT INTO native_snapshot_rls VALUES(1),(2)')
                    observer.execute('ALTER TABLE native_snapshot_rls ENABLE ROW LEVEL SECURITY')
                    observer.execute(sql.SQL('CREATE POLICY selected_native_rows ON native_snapshot_rls TO {} USING(id=1)').format(sql.Identifier(principal)))
                    observer.execute(sql.SQL('GRANT SELECT ON native_snapshot_rls TO {}').format(sql.Identifier(principal)))
                    observer.execute('CREATE TABLE native_snapshot_denied(id integer)')
                    observer.execute('INSERT INTO native_snapshot_denied VALUES(999)')
                    rls = open_resource(); rls_id = rls['job_id']
                    run(rls_id, 'logical_create', {'slot': 'sr_snapshot_rls', 'plugin': 'test_decoding', 'snapshot': 'use'})
                    listed = run(rls_id, 'snapshot_tables', {'schema': 'public', 'offset': 0, 'limit': 100})
                    public = listed['native_acknowledgement']['native_result']['relations']
                    secured = next(row for row in public if row['name'] == 'native_snapshot_rls')
                    denied = next(row for row in public if row['name'] == 'native_snapshot_denied')
                    assert secured['row_security_active'] and not denied['can_select']
                    copied = run(rls_id, 'snapshot_copy', {'relation_oid': secured['relation_oid'], 'format': 'text'})
                    response = client.post(url, data={'action': 'postgresql_replication_temporary_copy_download',
                        'payload': json.dumps({'database_target_id': target, 'resource_id': rls_id, 'job_id': copied['job_id']})})
                    assert response.status_code == 200 and response.data == b'1\n'; response.close()
                    assert copied['snapshot_copy_artifact']['source']['row_security_active']
                    run(rls_id, 'snapshot_end', {'decision': 'rollback'})
                    assert observer.execute("SELECT temporary,active_pid::text FROM pg_replication_slots WHERE slot_name='sr_snapshot_rls'").fetchone() == (True, rls['backend_pid'])
                    proof['checks'].append('native-RLS-filters-copy-without-hiding-denied-catalog-objects-and-explicit-rollback-keeps-session-slot')
                    run(rls_id, 'logical_create', {'slot': 'sr_snapshot_denied', 'plugin': 'test_decoding', 'snapshot': 'use'})
                    refused = run(rls_id, 'snapshot_copy', {'relation_oid': denied['relation_oid']}, failed=True)
                    assert refused['native_error_sqlstate'] == '42501' and not refused.get('native_command_acknowledged')
                    wait_resource(rls_id, lambda value: value.get('worker_io_closed'))
                    inspected = http('copy_reconcile', resource_id=rls_id, job_id=refused['job_id'])
                    assert inspected['snapshot_copy_artifact']['state'] == 'partial' and inspected['snapshot_copy_artifact']['artifact_bytes'] == '0'
                    proof['checks'].append('native-COPY-permission-denial-preserves-SQLSTATE-closes-owner-and-never-publishes-hidden-row-data')
                    phase = open_resource(); phase_id = phase['job_id']
                    native_update = ReplicationTemporaryCommands.update
                    def fail_after_begin(commands, record, **values):
                        result = native_update(commands, record, **values)
                        if values.get('native_phase_acknowledgements'):
                            raise OSError('owned publication failure after native BEGIN acknowledgement')
                        return result
                    with patch.object(ReplicationTemporaryCommands, 'update', fail_after_begin):
                        uncertain_begin = run(phase_id, 'logical_create', {'slot': 'sr_before_create_failure', 'snapshot': 'use'})
                    assert uncertain_begin['state'] == 'unknown' and not uncertain_begin.get('native_command_acknowledged')
                    assert uncertain_begin['native_phase_acknowledgements'][0]['phase'] == 'snapshot_transaction_begin'
                    wait_resource(phase_id, lambda value: value.get('worker_io_closed'))
                    assert int(observer.execute("SELECT count(*) FROM pg_replication_slots WHERE slot_name='sr_before_create_failure'").fetchone()[0]) == 0
                    proof['checks'].append('durable-native-BEGIN-ack-is-distinct-from-never-dispatched-slot-creation-and-owner-ends-without-replay')
                    observer.execute('CREATE TABLE native_snapshot_reused(id integer)')
                    observer.execute('INSERT INTO native_snapshot_reused VALUES(1)')
                    observer.execute(sql.SQL('GRANT SELECT ON native_snapshot_reused TO {}').format(sql.Identifier(principal)))
                    old_oid = observer.execute("SELECT 'native_snapshot_reused'::regclass::oid::text").fetchone()[0]
                    reused = open_resource(); reused_id = reused['job_id']
                    run(reused_id, 'logical_create', {'slot': 'sr_snapshot_reused', 'snapshot': 'use', 'plugin': 'test_decoding'})
                    run(reused_id, 'snapshot_inspect', {'relation_oid': old_oid})
                    queued = http('command_review', resource_id=reused_id, operation='snapshot_copy', options={'relation_oid': old_oid})
                    reviewed = wait_child(reused_id, queued['job_id'], {'reviewed'})
                    observer.execute('ALTER TABLE native_snapshot_reused RENAME TO native_snapshot_reused_moved')
                    observer.execute('CREATE TABLE native_snapshot_reused(id integer)')
                    observer.execute('INSERT INTO native_snapshot_reused VALUES(999)')
                    observer.execute(sql.SQL('GRANT SELECT ON native_snapshot_reused TO {}').format(sql.Identifier(principal)))
                    assert observer.execute("SELECT 'native_snapshot_reused'::regclass::oid::text").fetchone()[0] != old_oid
                    http('command_start', resource_id=reused_id, job_id=reviewed['job_id'], review_digest=reviewed['review_digest'], confirmed=True)
                    changed = wait_child(reused_id, reviewed['job_id'], {'failed', 'unknown'})
                    assert not changed.get('native_command_acknowledged')
                    wait_resource(reused_id, lambda value: value.get('worker_io_closed'))
                    assert observer.execute('SELECT id FROM native_snapshot_reused').fetchall() == [(999,)]
                    assert observer.execute('SELECT id FROM native_snapshot_reused_moved').fetchall() == [(1,)]
                    proof['checks'].append('current-locked-regclass-OID-rejects-a-reused-name-even-when-the-original-snapshot-sees-old-catalog-facts')
                    copy_publication = open_resource(); copy_publication_id = copy_publication['job_id']
                    run(copy_publication_id, 'logical_create', {'slot': 'sr_snapshot_copy_publication', 'snapshot': 'use', 'plugin': 'test_decoding'})
                    with patch('pgadmin.cdeadmin.workspace.postgresql_snapshot_copy.durable_replace', side_effect=OSError('owned snapshot COPY publication failure')):
                        uncertain_copy = run(copy_publication_id, 'snapshot_copy', {'relation_oid': selected_relation['relation_oid']})
                    assert uncertain_copy['state'] == 'unknown' and uncertain_copy['native_command_acknowledged']
                    wait_resource(copy_publication_id, lambda value: value.get('worker_io_closed'))
                    before = len(connections)
                    inspected = http('copy_reconcile', resource_id=copy_publication_id, job_id=uncertain_copy['job_id'])
                    assert inspected['state'] == 'unknown' and inspected['snapshot_copy_artifact']['state'] == 'verified'
                    assert len(connections) == before
                    http('copy_remove', resource_id=copy_publication_id, job_id=uncertain_copy['job_id'], confirmation='other', refused=True)
                    removed = http('copy_remove', resource_id=copy_publication_id, job_id=uncertain_copy['job_id'], confirmation=uncertain_copy['job_id'])
                    assert removed['artifact_removed']
                    assert http('copy_remove', resource_id=copy_publication_id, job_id=uncertain_copy['job_id'], confirmation=uncertain_copy['job_id'])['artifact_removed']
                    http('copy_preview', resource_id=copy_publication_id, job_id=uncertain_copy['job_id'], offset='0', length=16, refused=True)
                    proof['checks'].append('native-COPY-ack-and-exact-offline-publication-recovery-keep-unknown-outcome-with-confirmed-idempotent-removal')
                    observer.execute('CREATE VIEW native_snapshot_slow AS SELECT id,pg_sleep(30)::text AS paused FROM snapshot_rows')
                    observer.execute(sql.SQL('GRANT SELECT ON native_snapshot_slow,snapshot_rows TO {}').format(sql.Identifier(principal)))
                    slow_oid = observer.execute("SELECT 'native_snapshot_slow'::regclass::oid::text").fetchone()[0]
                    slow = open_resource(); slow_id = slow['job_id']
                    run(slow_id, 'logical_create', {'slot': 'sr_snapshot_copy_cancel', 'snapshot': 'use', 'plugin': 'test_decoding'})
                    run(slow_id, 'snapshot_inspect', {'relation_oid': slow_oid})
                    queued = http('command_review', resource_id=slow_id, operation='snapshot_copy', options={'relation_oid': slow_oid})
                    reviewed = wait_child(slow_id, queued['job_id'], {'reviewed'})
                    http('command_start', resource_id=slow_id, job_id=reviewed['job_id'], review_digest=reviewed['review_digest'], confirmed=True)
                    deadline = time.monotonic() + 10
                    while observer.execute('SELECT wait_event FROM pg_stat_activity WHERE pid=%s', (int(slow['backend_pid']),)).fetchone() != ('PgSleep',):
                        assert time.monotonic() < deadline; time.sleep(.03)
                    http('command_cancel', resource_id=slow_id, job_id=reviewed['job_id'])
                    cancelled_copy = wait_child(slow_id, reviewed['job_id'], {'failed', 'unknown'})
                    assert not cancelled_copy.get('native_command_acknowledged') and cancelled_copy['native_error_sqlstate'] == '57014'
                    wait_resource(slow_id, lambda value: value.get('worker_io_closed'))
                    inspected = http('copy_reconcile', resource_id=slow_id, job_id=cancelled_copy['job_id'])
                    assert inspected['snapshot_copy_artifact']['state'] == 'partial' and not inspected.get('native_command_acknowledged')
                    deadline = time.monotonic() + 10
                    while int(observer.execute("SELECT count(*) FROM pg_replication_slots WHERE slot_name='sr_snapshot_copy_cancel'").fetchone()[0]):
                        assert time.monotonic() < deadline; time.sleep(.03)
                    proof['checks'].append('independently-observed-active-native-COPY-cancellation-retains-57014-and-partial-bytes-never-prove-completion')
                    if browser_binary:
                        observer.execute('TRUNCATE snapshot_rows')
                        observer.execute('INSERT INTO snapshot_rows VALUES(1),(2)')
                        def verify_browser_copy(resource_id, command_id, expected_rows):
                            value = http('command_status', resource_id=resource_id, job_id=command_id)
                            assert value['native_command_acknowledged'] and value['snapshot_copy_artifact']['copy_format'] == 'binary'
                            response = client.post(url, data={'action': 'postgresql_replication_temporary_copy_download',
                                'payload': json.dumps({'database_target_id': target, 'resource_id': resource_id, 'job_id': command_id})})
                            assert response.status_code == 200
                            raw = response.data; response.close()
                            assert hashlib.sha256(raw).hexdigest() == value['snapshot_copy_artifact']['sha256']
                            observer.execute('CREATE TEMP TABLE browser_snapshot_delivered(id integer)')
                            with observer.cursor().copy('COPY browser_snapshot_delivered FROM STDIN (FORMAT binary)') as loading:
                                loading.write(raw)
                            assert observer.execute('SELECT id FROM browser_snapshot_delivered ORDER BY id').fetchall() == expected_rows
                            observer.execute('DROP TABLE browser_snapshot_delivered')
                        proof['browser'] = qualify_browser(app, output, browser_binary, driver_binary, sid,
                            secret, database, lambda identity: http('status', job_id=identity),
                            lambda snapshot: import_snapshot(snapshot, [(1,), (2,)]),
                            lambda: observer.execute('INSERT INTO snapshot_rows SELECT COALESCE(max(id),0)+1 FROM snapshot_rows'),
                            lambda: observer.execute('SELECT id FROM snapshot_rows ORDER BY id').fetchall(),
                            verify_browser_copy)
                    proof['application_connections'] = connections
                    proof['native_protocol_command_kinds'] = protocol_commands
        proof['owned_server_stopped'] = owned['owned_server_stopped']
        flow_finished = True
    finally:
        managers = getattr(service, 'postgresql_replication_temporary_resources', {})
        closed = [manager.close(timeout=10) for manager in managers.values()]
        if 'owned' in locals():
            proof['owned_server_stopped'] = owned.get('owned_server_stopped', False)
        proof['owned_workers_closed'] = all(closed)
        proof['complete'] = bool(flow_finished and proof.get('owned_server_stopped') and
                                 proof.get('owned_workers_closed') and len(proof['checks']) == 24)
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    proof['owned_server_stopped'] = owned['owned_server_stopped']
    proof['complete'] &= proof['owned_server_stopped']
    (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    assert proof['complete']
    return proof


def qualify_browser(app, output, binary, driver_binary, sid, password, database, resource_status, import_snapshot, produce_changes,
                    expected_rows, verify_copy):
    import re
    import threading
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import StaleElementReferenceException, ElementClickInterceptedException
    from werkzeug.serving import make_server
    from cdeadmin_ui_evidence import ensure_data_explorer, expand, invoke_context_action
    http = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
    driver = None; completed = False; result = {'complete': False}
    try:
        options = webdriver.ChromeOptions(); options.binary_location = binary
        for flag in ('--headless=new', '--no-sandbox', '--disable-dev-shm-usage', '--window-size=1800,1400'):
            options.add_argument(flag)
        options.add_argument('--user-data-dir=' + str(output / 'browser-profile'))
        options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
        driver = webdriver.Chrome(options=options, service=Service(driver_binary) if driver_binary else Service())
        wait = WebDriverWait(driver, 90, ignored_exceptions=(StaleElementReferenceException, ElementClickInterceptedException))
        def button(label):
            def click(browser):
                node = next((node for node in browser.find_elements(By.TAG_NAME, 'button')
                    if node.is_displayed() and node.is_enabled() and node.text.strip() == label), None)
                if node is None:
                    return False
                browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});', node); node.click(); return True
            wait.until(click)
        def control(label):
            node = wait.until(lambda browser: next((node for node in browser.find_elements(By.TAG_NAME, 'label')
                if node.is_displayed() and node.text.strip().rstrip('*').strip() == label), None))
            identifier = node.get_attribute('for')
            value = driver.find_element(By.ID, identifier) if identifier else node.find_element(By.CSS_SELECTOR, 'input')
            driver.execute_script('arguments[0].scrollIntoView({block:"nearest"});', value)
            return value
        def details(label):
            def reveal(browser):
                summary = next((node for node in browser.find_elements(By.TAG_NAME, 'summary') if node.text.strip() == label), None)
                if summary is None:
                    return False
                if summary.find_element(By.XPATH, '..').get_attribute('open') is not None:
                    return True
                browser.execute_script('arguments[0].scrollIntoView({block:"nearest"});', summary); summary.click(); return True
            wait.until(reveal)
        def choose(label, text, *, prefix=False):
            control(label).click()
            wait.until(lambda browser: next((node for node in browser.find_elements(By.CSS_SELECTOR, '[role="option"]')
                if node.is_displayed() and (node.text.strip().startswith(text) if prefix else node.text.strip() == text)), None)).click()
        def replace(label, value):
            node = control(label)
            modifier = Keys.COMMAND if driver.capabilities.get('platformName', '').lower() == 'mac' else Keys.CONTROL
            # Native keystrokes update React's controlled state. WebDriver's
            # clear() can leave the old state restored on a later render.
            node.send_keys(modifier, 'a'); node.send_keys(Keys.BACKSPACE)
            node.send_keys(str(value))
        def run_command():
            button('Review retained replication command')
            wait.until(lambda browser: 'Confirm retained replication command' in browser.find_element(By.TAG_NAME, 'body').text)
            control('Confirm retained replication command').click(); button('Run reviewed replication command')
            def complete(browser):
                for node in browser.find_elements(By.CSS_SELECTOR, '[role="alert"]'):
                    match = re.search(r'Retained replication command ([0-9a-f-]{36}): completed', node.text)
                    if match:
                        return match[1]
                return False
            return wait.until(complete)
        def workspace():
            ensure_data_explorer(wait); expand(wait, 'Connectors'); expand(wait, 'PostgreSQL')
            node = wait.until(lambda browser: next((node for node in browser.find_elements(By.CSS_SELECTOR, '.file-name')
                if node.is_displayed() and browser.execute_script(
                    'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);', node, sid)), None))
            invoke_context_action(wait, driver, node, ('PostgreSQL physical backup and verification...',), handle_endpoint_prompt=False)
            details('Temporary replication slots and exported snapshots')
        driver.get('http://127.0.0.1:' + str(http.server_port) + '/browser/')
        workspace(); details('Registered replication credentials')
        replace('Temporary replication password', password)
        replace('Replication resource maximum seconds', '300')
        button('Review temporary replication resource')
        wait.until(lambda browser: 'Confirm original replication resource' in browser.find_element(By.TAG_NAME, 'body').text)
        control('Confirm original replication resource').click(); button('Open reviewed replication resource')
        replace('Exact retained replication slot', 'sr_ui_export')
        button('Review retained replication command')
        wait.until(lambda browser: 'Confirm retained replication command' in browser.find_element(By.TAG_NAME, 'body').text)
        control('Confirm retained replication command').click(); button('Run reviewed replication command')
        def snapshot(browser):
            node = next((node for node in browser.find_elements(By.CSS_SELECTOR,
                '[aria-label="Retained replication snapshot acknowledgement"]') if node.is_displayed()), None)
            if node is None:
                return False
            value = json.loads(node.text)
            return (value.get('snapshot') or {}).get('snapshot_name')
        exported = wait.until(snapshot)
        def identity(browser):
            for node in browser.find_elements(By.CSS_SELECTOR, '[role="alert"]'):
                match = re.search(r'Replication resource ([0-9a-f-]{36}): active', node.text)
                if match:
                    return match[1]
            return False
        resource = wait.until(identity)
        driver.save_screenshot(str(output / 'replication-snapshot-active.png'))
        driver.refresh(); workspace()
        replace('Retained replication database name', database)
        button('Load retained replication resources'); control('Retained replication resource').click()
        wait.until(lambda browser: next((node for node in browser.find_elements(By.CSS_SELECTOR, '[role="option"]')
            if node.is_displayed() and resource in node.text), None)).click()
        assert wait.until(snapshot) == exported
        time.sleep(6)
        assert resource_status(resource)['ready']
        import_snapshot(exported)
        details('Registered replication credentials')
        replace('Temporary replication password', password)
        button('Review independent snapshot consumer')
        wait.until(lambda browser: 'Confirm original replication resource' in browser.find_element(By.TAG_NAME, 'body').text)
        control('Confirm original replication resource').click(); button('Open reviewed replication resource')
        wait.until(lambda browser: 'This independent backend owns an imported read-only repeatable-read snapshot transaction' in browser.find_element(By.TAG_NAME, 'body').text)
        independent_resource = wait.until(identity)
        assert independent_resource != resource
        assert resource_status(independent_resource)['snapshot_import_verified']
        button('Load retained replication resources')
        choose('Retained replication resource', resource, prefix=True)
        wait.until(lambda browser: identity(browser) == resource)
        produce_changes()
        control('Retained replication command').click()
        wait.until(lambda browser: next((node for node in browser.find_elements(By.CSS_SELECTOR, '[role="option"]')
            if node.is_displayed() and node.text.strip() == 'Capture original temporary logical stream'), None)).click()
        replace('Exact retained replication slot', 'sr_ui_export')
        replace('Retained stream maximum messages', '3')
        control('Allow invalidation of the current exported snapshot').click()
        button('Review retained replication command')
        wait.until(lambda browser: 'Confirm retained replication command' in browser.find_element(By.TAG_NAME, 'body').text)
        control('Confirm retained replication command').click(); button('Run reviewed replication command')
        button('Preview original replication frames')
        wait.until(lambda browser: next((node for node in browser.find_elements(By.CSS_SELECTOR,
            '[aria-label="Original replication frame preview"]') if node.is_displayed() and 'payload_base64' in node.text), None))
        driver.save_screenshot(str(output / 'replication-stream-preview.png'))
        control('Release this replication backend and snapshot').click(); button('Release retained replication resource')
        wait.until(lambda browser: 'Local replication connection close returned.' in browser.find_element(By.TAG_NAME, 'body').text)
        deadline = time.monotonic() + 15
        while not resource_status(resource).get('worker_io_closed'):
            assert time.monotonic() < deadline; time.sleep(.05)
        driver.save_screenshot(str(output / 'replication-snapshot-released.png'))
        button('Load retained replication resources')
        choose('Retained replication resource', independent_resource, prefix=True)
        wait.until(lambda browser: identity(browser) == independent_resource)
        choose('Retained replication command', 'Read original snapshot relation catalog')
        replace('Original snapshot schema name (empty for all)', 'public')
        run_command()
        choose('Retained replication command', 'Inspect original snapshot relation')
        choose('Original snapshot relation', 'public.snapshot_rows — OID ', prefix=True)
        run_command()
        choose('Retained replication command', 'Copy relation from original snapshot')
        independent_copy = run_command()
        verify_copy(independent_resource, independent_copy, [(1,), (2,)])
        button('Preview original snapshot COPY bytes')
        wait.until(lambda browser: next((node for node in browser.find_elements(By.CSS_SELECTOR,
            '[aria-label="Original snapshot COPY byte preview"]') if node.is_displayed() and 'data_base64' in node.text), None))
        driver.save_screenshot(str(output / 'independent-import-copy-after-exporter-release.png'))
        choose('Retained replication command', 'End owned snapshot transaction')
        run_command()
        control('Release this replication backend and snapshot').click(); button('Release retained replication resource')
        deadline = time.monotonic() + 15
        while not resource_status(independent_resource).get('worker_io_closed'):
            assert time.monotonic() < deadline; time.sleep(.05)
        details('Registered replication credentials')
        replace('Temporary replication password', password)
        replace('Replication resource maximum seconds', '300')
        button('Review temporary replication resource')
        wait.until(lambda browser: 'Confirm original replication resource' in browser.find_element(By.TAG_NAME, 'body').text)
        control('Confirm original replication resource').click(); button('Open reviewed replication resource')
        use_resource = wait.until(identity)
        choose('Retained replication command', 'Create temporary logical slot')
        replace('Exact retained replication slot', 'sr_ui_use')
        choose('Native replication snapshot', 'Use snapshot in an owned read-only transaction')
        run_command()
        wait.until(lambda browser: 'The original backend owns a read-only repeatable-read SNAPSHOT USE' in browser.find_element(By.TAG_NAME, 'body').text)
        expected = expected_rows()
        produce_changes()
        choose('Retained replication command', 'Read original snapshot relation catalog')
        replace('Original snapshot schema name (empty for all)', 'public')
        run_command()
        wait.until(lambda browser: 'Native snapshot relation page:' in browser.find_element(By.TAG_NAME, 'body').text)
        choose('Retained replication command', 'Inspect original snapshot relation')
        choose('Original snapshot relation', 'public.snapshot_rows — OID ', prefix=True)
        run_command()
        choose('Retained replication command', 'Copy relation from original snapshot')
        copied_command = run_command()
        button('Preview original snapshot COPY bytes')
        wait.until(lambda browser: next((node for node in browser.find_elements(By.CSS_SELECTOR,
            '[aria-label="Original snapshot COPY byte preview"]') if node.is_displayed() and 'data_base64' in node.text), None))
        verify_copy(use_resource, copied_command, expected)
        driver.save_screenshot(str(output / 'snapshot-use-native-copy.png'))
        choose('Retained replication command', 'End owned snapshot transaction')
        run_command()
        wait.until(lambda browser: 'The original backend owns a read-only repeatable-read SNAPSHOT USE' not in browser.find_element(By.TAG_NAME, 'body').text)
        choose('Retained replication command', 'Capture original temporary logical stream')
        run_command(); button('Preview original replication frames')
        wait.until(lambda browser: next((node for node in browser.find_elements(By.CSS_SELECTOR,
            '[aria-label="Original replication frame preview"]') if node.is_displayed() and 'payload_base64' in node.text), None))
        control('Release this replication backend and snapshot').click(); button('Release retained replication resource')
        deadline = time.monotonic() + 15
        while not resource_status(use_resource).get('worker_io_closed'):
            assert time.monotonic() < deadline; time.sleep(.05)
        completed = True
        result.update(complete=True, browser_version=driver.capabilities['browserVersion'],
            driver_version=driver.capabilities.get('chrome', {}).get('chromedriverVersion'),
            original_backend_preserved_after_reload=True, native_snapshot_import_verified=True,
            original_backend_stream_captured_and_previewed=True,
            independent_application_consumer_import_verified=True,
            independent_consumer_copy_after_exporter_release_verified=True,
            owned_snapshot_use_native_copy_import_verified=True, explicit_snapshot_transaction_end=True,
            original_backend_stream_after_initial_copy=True,
            explicit_release_completed=True, sql_bootstrap_performed=False)
    finally:
        if driver is not None:
            if not completed:
                driver.save_screenshot(str(output / 'replication-browser-failure.png'))
                (output / 'replication-browser-failure.txt').write_text(driver.find_element(By.TAG_NAME, 'body').text.replace(password, '<redacted>'))
            (output / 'replication-browser-console.json').write_text(json.dumps(driver.get_log('browser'), indent=2).replace(password, '<redacted>') + '\n')
            driver.quit()
        http.shutdown(); http.server_close(); thread.join(5)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--browser-binary')
    parser.add_argument('--driver-binary')
    arguments = parser.parse_args()
    print(json.dumps(qualify(arguments.output, browser_binary=arguments.browser_binary, driver_binary=arguments.driver_binary), indent=2))

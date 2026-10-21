"""Original replication backend, exported snapshots and authenticated receipts."""
import argparse
import builtins
import base64
import hashlib
import json
from pathlib import Path
import secrets
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
    from pgadmin.cdeadmin.workspace.postgresql_replication_temporary_jobs import ReplicationTemporaryCommands
    from flask import url_for
    paths = [str(Path(__file__).relative_to(ROOT)),
             'web/pgadmin/cdeadmin/providers/postgresql/replication_temporary_slots.py',
             'web/pgadmin/cdeadmin/workspace/postgresql_replication_temporary_jobs.py',
             'web/pgadmin/cdeadmin/workspace/postgresql_replication_temporary_service.py',
             'web/pgadmin/cdeadmin/workspace/postgresql_replication_stream.py',
             'web/pgadmin/cdeadmin/providers/postgresql/replication_stream_options.py',
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
        with server(output / 'fixture', server_options=('-c', 'wal_level=logical', '-c', 'wal_sender_timeout=5s')) as (route, password, owned):
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
                connections = []; protocol_commands = []
                def replication_only(*args, **kwargs):
                    assert kwargs.get('replication') == 'database', 'Application attempted ordinary SQL admission'
                    connections.append({'replication': kwargs['replication'], 'database': kwargs.get('dbname'),
                                        'application_name': kwargs.get('application_name')})
                    return original_connect(*args, **kwargs)
                native_execute = psycopg.ClientCursor.execute
                def replication_command(cursor, command, *args, **kwargs):
                    if cursor.connection.info.get_parameters().get('replication') == 'database':
                        text = command.as_string(cursor.connection) if isinstance(command, sql.Composable) else str(command)
                        kind = text.lstrip().split(None, 1)[0]
                        assert kind in {'IDENTIFY_SYSTEM', 'SHOW', 'CREATE_REPLICATION_SLOT', 'DROP_REPLICATION_SLOT'}, text
                        assert secret not in text
                        protocol_commands.append(kind)
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
                def open_resource():
                    reviewed = http('review', options={'max_lifetime_seconds': 300})
                    identity = reviewed['job_id']; resources.append(identity)
                    http('start', job_id=identity, review_digest=reviewed['review_digest'], confirmed=True)
                    return wait_resource(identity, lambda result: result.get('ready'))
                def run(resource, operation, options, *, failed=False):
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
                        patch.object(psycopg.ClientCursor, 'execute', replication_command):
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
                    if browser_binary:
                        observer.execute('TRUNCATE snapshot_rows')
                        observer.execute('INSERT INTO snapshot_rows VALUES(1),(2)')
                        proof['browser'] = qualify_browser(app, output, browser_binary, driver_binary, sid,
                            secret, database, lambda identity: http('status', job_id=identity),
                            lambda snapshot: import_snapshot(snapshot, [(1,), (2,)]),
                            lambda: observer.execute('INSERT INTO snapshot_rows VALUES(4)'))
                    proof['application_connections'] = connections
                    proof['native_protocol_command_kinds'] = protocol_commands
        proof['owned_server_stopped'] = owned['owned_server_stopped']
        flow_finished = True
    finally:
        managers = getattr(service, 'postgresql_replication_temporary_resources', {})
        closed = [manager.close(timeout=10) for manager in managers.values()]
        proof['owned_workers_closed'] = all(closed)
        proof['complete'] = bool(flow_finished and proof.get('owned_server_stopped') and
                                 proof.get('owned_workers_closed') and len(proof['checks']) == 11)
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    proof['owned_server_stopped'] = owned['owned_server_stopped']
    proof['complete'] &= proof['owned_server_stopped']
    (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    assert proof['complete']
    return proof


def qualify_browser(app, output, binary, driver_binary, sid, password, database, resource_status, import_snapshot, produce_changes):
    import re
    import threading
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
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
        def workspace():
            ensure_data_explorer(wait); expand(wait, 'Connectors'); expand(wait, 'PostgreSQL')
            node = wait.until(lambda browser: next((node for node in browser.find_elements(By.CSS_SELECTOR, '.file-name')
                if node.is_displayed() and browser.execute_script(
                    'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);', node, sid)), None))
            invoke_context_action(wait, driver, node, ('PostgreSQL physical backup and verification...',), handle_endpoint_prompt=False)
            details('Temporary replication slots and exported snapshots')
        driver.get('http://127.0.0.1:' + str(http.server_port) + '/browser/')
        workspace(); details('Registered replication credentials')
        control('Temporary replication password').send_keys(password)
        limit = control('Replication resource maximum seconds'); limit.clear(); limit.send_keys('300')
        button('Review temporary replication resource')
        wait.until(lambda browser: 'Confirm original replication resource' in browser.find_element(By.TAG_NAME, 'body').text)
        control('Confirm original replication resource').click(); button('Open reviewed replication resource')
        control('Exact retained replication slot').send_keys('sr_ui_export')
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
        control('Retained replication database name').send_keys(database)
        button('Load retained replication resources'); control('Retained replication resource').click()
        wait.until(lambda browser: next((node for node in browser.find_elements(By.CSS_SELECTOR, '[role="option"]')
            if node.is_displayed() and resource in node.text), None)).click()
        assert wait.until(snapshot) == exported
        time.sleep(6)
        assert resource_status(resource)['ready']
        import_snapshot(exported)
        produce_changes()
        control('Retained replication command').click()
        wait.until(lambda browser: next((node for node in browser.find_elements(By.CSS_SELECTOR, '[role="option"]')
            if node.is_displayed() and node.text.strip() == 'Capture original temporary logical stream'), None)).click()
        control('Exact retained replication slot').send_keys('sr_ui_export')
        count = control('Retained stream maximum messages'); count.clear(); count.send_keys('3')
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
        completed = True
        result.update(complete=True, browser_version=driver.capabilities['browserVersion'],
            driver_version=driver.capabilities.get('chrome', {}).get('chromedriverVersion'),
            original_backend_preserved_after_reload=True, native_snapshot_import_verified=True,
            original_backend_stream_captured_and_previewed=True,
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

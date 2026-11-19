"""Qualify managed native Firebird trace via owned Engine13 and authenticated HTTP.

Captured data comes only from disposable fixtures. This is not network,
system-audit/service tracing, browser or other-platform qualification.
"""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def qualify(runtime, output):
    from pathlib import Path
    from types import SimpleNamespace
    import sys
    import os
    import json
    import uuid
    import hashlib
    import tempfile
    W = Path(output).resolve()
    R = ROOT
    if sys.platform != 'linux' or W == R or R in W.parents:
        raise ValueError('Linux runtime and evidence outside source required')
    W.mkdir(parents=True, exist_ok=True)
    import builtins
    builtins.SERVER_MODE = None
    import pgadmin
    from tools.cdeadmin_firebird_object_live_orchestrator import _stage_runtime, _runtime_fingerprint
    runtime = Path(runtime).resolve()
    before = _runtime_fingerprint(runtime)
    proof = {'complete': False, 'scope': (
        'Owned Engine13 Firebird 5.0.4 authenticated desktop HTTP managed database trace, '
        'service-scope trace, and external native trace-session controls; no browser/platform acceptance.'
    ), 'checks': [], 'source_sha256': {p: hashlib.sha256((R/p).read_bytes()).hexdigest(
    )for p in ['web/pgadmin/cdeadmin/providers/firebird/local_services.py', 'web/pgadmin/cdeadmin/providers/firebird/embedded_provider.py', 'web/pgadmin/cdeadmin/providers/firebird/provider.py', 'web/pgadmin/cdeadmin/providers/firebird/query_client.py', 'web/pgadmin/cdeadmin/providers/firebird/service_connection.py', 'web/pgadmin/cdeadmin/providers/firebird/firebird_embedded_dialect_5_0_4.json', 'web/pgadmin/cdeadmin/providers/firebird/firebird_embedded_metrics_5_0_4.json', 'web/pgadmin/cdeadmin/ui_descriptors/firebird/capabilities.json']}}
    for name in ('web/pgadmin/cdeadmin/providers/firebird/trace_config.py', 'web/pgadmin/cdeadmin/providers/firebird/trace_sessions.py', 'web/pgadmin/cdeadmin/workspace/firebird_trace_actions.py', 'web/pgadmin/cdeadmin/workspace/service.py', 'web/pgadmin/browser/server_groups/servers/__init__.py', 'web/pgadmin/cdeadmin/ui_descriptors/firebird/tools.json'):
        proof['source_sha256'][name] = hashlib.sha256((R/name).read_bytes()).hexdigest()
    proof['runner_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    proof['history_tests'] = 'not run'
    proof['not_qualified'] = ['Windows/macOS', 'human UI acceptance']
    try:
        from contextlib import ExitStack
        with tempfile.TemporaryDirectory(prefix='firebird-trace-http-', dir=W)as area, ExitStack() as owners:
            root = Path(area)
            stage = root/'runtime'
            _stage_runtime(runtime, stage)
            (stage/'firebird.conf').write_text(
                'ServerMode = SuperClassic\nProviders = Engine13\nSecurityDatabase = ' +
                str(stage/'security5.fdb')+'\n')
            (stage/'databases.conf').write_text('')
            os.environ.update(FIREBIRD=str(stage), FIREBIRD_LOCK=str(stage/'lock'),
                              CDEADMIN_FIREBIRD_CLIENT_LIBRARY=str(stage/'lib/libfbclient.so.5.0.4'))
            import firebird.driver as module
            module.driver_config.fb_client_library.value = str(stage/'lib/libfbclient.so.5.0.4')
            from tools.cdeadmin_mysql_dump_verification_qualification import setup_application
            app = setup_application(root)

            def close_app():
                from pgadmin.cdeadmin.workspace.service import service_for_app
                with app.app_context():
                    service = service_for_app(app)
                    assert service.firebird_traces.close()
                    service.endpoint_service.provider_registry.close()
            owners.callback(close_app)
            from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
            from pgadmin.cdeadmin.providers.firebird.provider import _create_client, _resources
            from pgadmin.cdeadmin.endpoints.profiles import registration_profile
            from pgadmin.model import db, User, ServerGroup, Server, EndpointDatabaseTarget
            from flask import url_for
            data = root/'data'
            data.mkdir()
            path = data/"HTTP%_[x]{q}|+*?^ 雪#.fdb"
            route = {'attachment_mode': 'embedded', 'database': str(
                path), 'filesystem_root': str(data), 'user': 'SYSDBA', 'charset': 'UTF8'}
            native_client = _create_client(SimpleNamespace(require=lambda *_: None, acquire_secret=lambda *_: (_ for _ in ()).throw(
                AssertionError('Secret requested'))), attachment_mode='embedded', profile=embedded.PROFILE, administration=embedded.ADMINISTRATION)
            c = native_client.config.database_creator(
                **native_client.config.database_create_arguments(route, str(path), {}))
            try:
                c.execute_immediate('CREATE TABLE HTTP_STATS(ID INTEGER)')
                c.commit()
                target = next(x for x in _resources(
                    c, {'route': route})if x['resource_kind'] == 'database')
                c.rollback()
            finally:
                c.close()
                native_client.close()
            with app.test_request_context('/'):
                user = User.query.first()
                uid = user.id
                group = ServerGroup.query.filter_by(user_id=uid).first()
                for name, pref in app.blueprints['NODE-engine_type'].connector_visibility.items():
                    if 'firebird' in name:
                        pref.set(True, user_id=uid)
                server = Server(user_id=uid, servergroup_id=group.id, name='Owned local statistics',
                                host=None, port=1, username='SYSDBA', maintenance_db=str(path), save_password=0)
                server._cde_endpoint_registration = registration_profile('firebird-embedded')
                server._cde_endpoint_route_configuration = route
                db.session.add(server)
                db.session.commit()
                tid = str(uuid.uuid4())
                db.session.add(EndpointDatabaseTarget(id=tid, endpoint_id=server.endpoint_profile.id,
                               display_name=path.name, database=str(path), configuration='{}', active=1))
                db.session.commit()
                url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=server.id)
                verify = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=server.id)
            client = app.test_client()
            with client.session_transaction()as session:
                session['_user_id'] = str(uid)
                session['_fresh'] = True
            verified = client.post(verify, json={}).get_json()
            assert verified['success'], verified

            def post(action, request, denied=False):
                response = client.post(url, json={'action': action, 'database_target_id': tid, 'request': {
                                       'database_target_id': tid, **request}})
                value = response.get_json()
                if denied:
                    assert not value.get('success')
                    return value
                assert response.status_code == 200 and value.get('success'), (action, value)
                assert response.headers['Cache-Control'] == 'no-store'
                return value['data']
            import time
            from pgadmin.cdeadmin.providers.firebird import trace_sessions

            def trace(action, **request): return post('firebird_trace',
                                                      {'action': action, **request})

            def reviewed(operation, **request):
                plan = trace('review', operation=operation, **request)
                apply_request = {'review_id': plan['review_id'],
                                 'review_digest': plan['review_digest'], 'confirmed': True}
                result = trace('apply', **apply_request)
                assert trace('apply', **apply_request) == result
                return result
            post('firebird_trace', {'action': 'review', 'operation': 'start',
                 'options': {'log_statement_finish': True}}, denied=True)
            assert trace('describe')['schema'] == 'scratchrobin.firebird.trace-api@1'
            started = reviewed('start', name='Owned trace', options={
                               'log_statement_finish': True, 'capture_sensitive': True,
                               'include_gds_codes': '335544344', 'exclude_gds_codes': '335544569'})
            assert started['outcome']['native_started'], started
            identity = started['outcome']['trace_id']
            native_client = _create_client(SimpleNamespace(require=lambda *_: None, acquire_secret=None),
                                           attachment_mode='embedded', profile=embedded.PROFILE, administration=embedded.ADMINISTRATION)
            held = native_client._connect({'route': route})
            try:
                held.execute_immediate('INSERT INTO HTTP_STATS VALUES(23)')
                transaction = held.main_transaction.info.id
                assert trace('list')['items'][0]['native_list_observation']['present']
                assert reviewed('suspend', trace_id=identity)['outcome']['state'] == 'suspended'
                q = held.cursor()
                q.execute("SELECT 'paused_marker_QA' FROM RDB$DATABASE")
                q.fetchone()
                q.close()
                assert reviewed('resume', trace_id=identity)['outcome']['state'] == 'started'
                q = held.cursor()
                q.execute("SELECT 'active_marker_QA' FROM RDB$DATABASE")
                q.fetchone()
                q.close()
                sibling = data/'sibling'
                sibling.mkdir()
                other_route = {**route, 'database': str(sibling/path.name)}
                other = native_client.config.database_creator(
                    **native_client.config.database_create_arguments(other_route, other_route['database'], {}))
                try:
                    q = other.cursor()
                    q.execute("SELECT 'foreign_marker_QA' FROM RDB$DATABASE")
                    q.fetchone()
                    q.close()
                    other.commit()
                finally:
                    other.close()
                lines = []
                after = 0
                deadline = time.monotonic()+10
                while time.monotonic() < deadline:
                    page = trace('poll', trace_id=identity, after=after)
                    lines.extend(x['text']for x in page['lines'])
                    after = page['next_sequence']
                    if 'active_marker_QA' in ''.join(lines):
                        break
                    time.sleep(0.05)
                output = ''.join(lines)
                assert 'active_marker_QA' in output and 'paused_marker_QA' not in output and 'foreign_marker_QA' not in output, output
                for _ in range(800):
                    q = held.cursor()
                    q.execute('SELECT 17 FROM RDB$DATABASE')
                    q.fetchone()
                    q.close()
                deadline = time.monotonic()+10
                while time.monotonic() < deadline:
                    page = trace('poll', trace_id=identity, after=0)
                    if page['delivery_gap']:
                        break
                    time.sleep(0.05)
                assert page['delivery_gap'] and page['dropped_lines'] > 0
                stopped = reviewed('stop', trace_id=identity)['outcome']
                assert stopped['native_stop_acknowledged'] and stopped['cleanup_confirmed'], stopped
                assert held.main_transaction.info.id == transaction
                q = held.cursor()
                q.execute('SELECT ID FROM HTTP_STATS')
                assert q.fetchall() == [(23,)]
                q.close()
                held.rollback()
            finally:
                native_client._forget_and_close(held)
                native_client.close()
            from pgadmin.cdeadmin.workspace.service import service_for_app
            with app.app_context():
                service = service_for_app(app)
                service.firebird_traces._get(
                    'user:'+str(uid), next(iter(service.firebird_traces.items.values())).binding, identity).done.wait(2)
                journal = Path(app.config['DATA_DIR'])/'firebird-trace-operations.json'
                assert journal.exists(), journal
                assert 'active_marker_QA' not in journal.read_text() and 'paused_marker_QA' not in journal.read_text()
            assert reviewed('forget', trace_id=identity)['outcome']['state'] == 'forgotten'
            restored = trace('poll', trace_id=identity)
            assert not restored['output_available'] and not restored['live_handle_available'] and restored['cleanup_confirmed']

            # Service-scope trace over HTTP + Engine13
            post('firebird_trace', {
                'action': 'review',
                'operation': 'start_services',
                'service_options': {'log_services': True},
            }, denied=True)
            svc_started = reviewed('start_services', name='Owned service trace', service_options={
                'service_scope_confirmed': True,
                'capture_sensitive': True,
                'log_services': True,
                'log_service_query': True,
                'include_filter': 'Database Stats',
            })
            assert svc_started['outcome']['native_started'] and svc_started['outcome']['trace_scope'] == 'services'
            svc_id = svc_started['outcome']['trace_id']
            svc_probe_client = _create_client(
                SimpleNamespace(require=lambda *_: None, acquire_secret=None),
                attachment_mode='embedded', profile=embedded.PROFILE, administration=embedded.ADMINISTRATION,
            )
            svc_srv = svc_probe_client._connect_server({'route': route})
            try:
                svc_srv.database.get_statistics(
                    database=str(path),
                    flags=module.SrvStatFlag.HDR_PAGES,
                    callback=lambda *_: None,
                )
            finally:
                svc_probe_client._release_server(svc_srv)
                svc_probe_client.close()
            svc_lines = []
            svc_after = 0
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                page = trace('poll', trace_id=svc_id, after=svc_after)
                svc_lines.extend(x['text'] for x in page['lines'])
                svc_after = page['next_sequence']
                if 'Database Stats' in ''.join(svc_lines):
                    break
                time.sleep(0.05)
            assert 'Database Stats' in ''.join(svc_lines), svc_lines
            svc_stopped = reviewed('stop', trace_id=svc_id)['outcome']
            assert svc_stopped['native_stop_acknowledged'] and svc_stopped['cleanup_confirmed']
            assert reviewed('forget', trace_id=svc_id)['outcome']['state'] == 'forgotten'
            proof['checks'].append('Authenticated HTTP service-scope trace captures filtered native Database Stats service events and cleans up')

            # External native trace-session listing and reviewed suspend/resume/stop over HTTP
            ext_client = _create_client(
                SimpleNamespace(require=lambda *_: None, acquire_secret=None),
                attachment_mode='embedded', profile=embedded.PROFILE, administration=embedded.ADMINISTRATION,
            )
            ext_srv = ext_client._connect_server({'route': route})
            try:
                ext_native_id = ext_srv.trace.start(
                    config='database\n{\nenabled = false\n}\nservices\n{\nenabled = true\nlog_services = true\n}\n',
                    name='ExternalCLI',
                )
                native_items = trace('list_native')['items']
                ext_entry = next(row for row in native_items if row['native_session_id'] == ext_native_id)
                assert ext_entry['managed_by_workspace'] is False and ext_entry['name'] == 'ExternalCLI'
                assert reviewed('suspend_external', native_session_id=ext_native_id)['outcome']['state'] == 'suspended'
                assert reviewed('resume_external', native_session_id=ext_native_id)['outcome']['state'] == 'started'
                stale_ext_stop = trace('review', operation='stop_external', native_session_id=ext_native_id)
                stopped_ext = reviewed('stop_external', native_session_id=ext_native_id)['outcome']
                assert stopped_ext['state'] == 'stopped' and stopped_ext['native_acknowledged'] is True
                stale_applied = trace(
                    'apply',
                    review_id=stale_ext_stop['review_id'],
                    review_digest=stale_ext_stop['review_digest'],
                    confirmed=True,
                )['outcome']
                assert stale_applied['state'] == 'rejected' and stale_applied['native_dispatched'] is False
            finally:
                ext_client._release_server(ext_srv)
                ext_client.close()
            proof['checks'].append('Authenticated HTTP list_native and reviewed external native trace suspend/resume/stop + stale rejection qualified')
            stale = trace('review', operation='start', options={})
            retained = data/'Retained original.fdb'
            path.rename(retained)
            replacement = _create_client(SimpleNamespace(require=lambda *_: None, acquire_secret=None),
                                         attachment_mode='embedded', profile=embedded.PROFILE, administration=embedded.ADMINISTRATION)
            try:
                created = replacement.config.database_creator(
                    **replacement.config.database_create_arguments(route, str(path), {}))
                created.close()
            finally:
                replacement.close()
            rejected = trace('apply', review_id=stale['review_id'],
                             review_digest=stale['review_digest'], confirmed=True)
            assert rejected['outcome']['state'] == 'rejected' and rejected['outcome']['native_dispatched'] is False
            assert trace('list')['items'] == []
            proof['checks'].append(
                'Same-name replacement after review rejected before native trace dispatch')
            with app.app_context():
                assert service_for_app(app).firebird_traces.close()
                service_for_app(app).endpoint_service.provider_registry.close()
            proof['checks'].append('Authenticated one-use reviewed native trace start/list/suspend/resume/stop; explicit sensitive capture; SQL output and sibling isolation; bounded delivery gap; caller pending transaction preserved; private durable metadata without captured SQL; explicit output forget and durable receipt fallback')

        proof['owned_state_removed'] = not root.exists()
        proof['source_runtime_unchanged'] = _runtime_fingerprint(runtime) == before
        proof['complete'] = proof['owned_state_removed'] and proof['source_runtime_unchanged']
    finally:
        (W/'firebird-trace-http.json').write_text(json.dumps(proof, indent=2)+'\n')
    print('Authenticated managed trace passed', len(proof['checks']))

    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = qualify(args.runtime, args.output)
    raise SystemExit(0 if result['complete'] else 1)

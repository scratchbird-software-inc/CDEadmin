"""Qualify encrypted loopback user trace, registered aliases and native user isolation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def qualify(runtime, output):
    from tools.cdeadmin_firebird_object_live_orchestrator import (
        _stage_runtime, _runtime_fingerprint, _initialize_security,
        _free_port, _wait_for_server,
    )
    runtime, output = Path(runtime).resolve(), Path(output).resolve()
    if sys.platform != 'linux' or output == ROOT or ROOT in output.parents:
        raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True, exist_ok=True)
    proof = {'complete': False, 'modes': [], 'history_tests': 'not run',
             'scope': (
                 'Owned Linux loopback Firebird 5.0.4 managed database and service trace, '
                 'registered aliases, restricted users, external native trace controls, '
                 'AuditTraceConfigFile system audit, credential revocation, and listener transport loss'
             )}
    files = ['web/pgadmin/cdeadmin/providers/firebird/' + name for name in (
        'trace_config.py', 'trace_sessions.py', 'query_client.py', 'provider.py',
        'metadata_guard.py', 'service_connection.py', 'connection_opening.py', 'local_services.py')]
    files += ['web/pgadmin/cdeadmin/providers/relational_admin.py',
              'web/pgadmin/cdeadmin/sdk/relational.py',
              'tools/cdeadmin_firebird_trace_network_qualification.py']
    proof['source_sha256'] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                              for name in files}
    before = _runtime_fingerprint(runtime)
    proof['not_qualified'] = ['Windows/macOS and human UI']
    process = None
    try:
        with tempfile.TemporaryDirectory(prefix='firebird-native-target-', dir=output) as folder:
            area = Path(folder)
            stage = area / 'runtime'
            _stage_runtime(runtime, stage)
            from pgadmin.cdeadmin.providers.firebird.trace_config import (
                render_system_audit, read_audit_log_tail,
            )
            audit_dir = area / 'audit'
            audit_dir.mkdir()
            audit_conf = audit_dir / 'system_audit.conf'
            audit_db_log = audit_dir / 'db_audit.log'
            audit_svc_log = audit_dir / 'svc_audit.log'
            audit_conf.write_text(render_system_audit({
                'all_databases': True,
                'database_log_filename': str(audit_db_log),
                'database_max_log_size': 50,
                'database_options': {
                    'capture_sensitive': True,
                    'log_connections': True,
                    'log_statement_finish': True,
                },
                'enable_services': True,
                'services_log_filename': str(audit_svc_log),
                'services_max_log_size': 25,
                'service_options': {
                    'service_scope_confirmed': True,
                    'capture_sensitive': True,
                    'log_services': True,
                    'log_service_query': True,
                },
            }, audit_dir), encoding='utf-8')
            # Both explicit connection profiles share one exact client library.
            # Network transport is only the owned loopback listener below.
            (stage / 'firebird.conf').write_text(
                'Providers = Remote,Engine13\n'
                'AuditTraceConfigFile = ' + str(audit_conf) + '\n'
                'SecurityDatabase = ' + str(stage / 'security5.fdb') + '\n')
            (stage / 'databases.conf').write_text('')
            os.environ.update(FIREBIRD=str(stage), FIREBIRD_LOCK=str(stage / 'lock'),
                              CDEADMIN_FIREBIRD_CLIENT_LIBRARY=str(stage / 'lib/libfbclient.so.5.0.4'))
            password = secrets.token_urlsafe(24)
            _initialize_security(stage, password, dict(os.environ))
            port = _free_port()
            with (output / 'server.log').open('wb') as log:
                process = subprocess.Popen([str(stage / 'bin/firebird'), '-d', '-p', str(port),
                                            '-e', str(stage), '-el', str(stage / 'lock'), '-em', str(stage)],
                                           stdout=log, stderr=subprocess.STDOUT, env=dict(os.environ))
                try:
                    _wait_for_server(process, port)
                    import firebird.driver as module
                    module.driver_config.fb_client_library.value = str(
                        stage / 'lib/libfbclient.so.5.0.4')
                    from pgadmin.cdeadmin.providers.firebird import provider as network
                    from tools.mysql_driver_gate_support import provider_access
                    from pgadmin.cdeadmin.providers.firebird.trace_config import observe_scope
                    from pgadmin.cdeadmin.providers.firebird.trace_sessions import TraceSessions
                    import time
                    path = str(area/'Network %_雪.fdb')
                    sibling = area/'sibling'
                    sibling.mkdir()
                    sibling_path = str(sibling/'Network %_雪.fdb')
                    (stage/'databases.conf').write_text('TRACE_ALIAS = ' +
                                                        path+'\nTRACExALIAS = '+sibling_path+'\n')
                    base = {'host': '127.0.0.1', 'port': port, 'database': 'TRACE_ALIAS',
                            'user': 'SYSDBA', 'charset': 'UTF8', 'wire_crypt': 'Required', 'trusted_auth': False}
                    route, permissions = provider_access(base, password)
                    permissions.require = lambda *_: None
                    permissions.allows = lambda *_: True
                    admin = network._create_client(permissions, attachment_mode='network')
                    created = admin.config.database_creator(
                        **admin.config.database_create_arguments({**route, 'database': path}, path, {}))
                    created.execute_immediate('CREATE TABLE T(ID INTEGER)')
                    created.commit()
                    created.close()
                    account_password = secrets.token_urlsafe(24)
                    server = admin._connect_server({'route': route})
                    try:
                        server.user.add(user_name='TR_READER', password=account_password)
                    finally:
                        admin._release_server(server)
                    held = admin._connect({'route': route})
                    q = held.cursor()
                    q.execute(
                        "SELECT RDB$GET_CONTEXT('SYSTEM','NETWORK_PROTOCOL'), MON$SERVER_PID, MON$WIRE_ENCRYPTED FROM MON$ATTACHMENTS WHERE MON$ATTACHMENT_ID=CURRENT_CONNECTION")
                    protocol, pid, encrypted = q.fetchone()
                    q.close()
                    held.rollback()
                    assert protocol == 'TCPv4' and pid == process.pid and encrypted is True
                    held.execute_immediate('GRANT SELECT, INSERT ON T TO TR_READER')
                    held.commit()
                    reader_route, reader_permissions = provider_access(
                        {**base, 'user': 'TR_READER'}, account_password)
                    reader_permissions.require = lambda *_: None
                    reader_permissions.allows = lambda *_: True
                    reader = network._create_client(reader_permissions, attachment_mode='network')
                    manager = TraceSessions()
                    actors = []
                    try:
                        for name, selected, access, source in [('admin', route, permissions, admin), ('reader', reader_route, reader_permissions, reader)]:
                            scope = observe_scope(source, selected)
                            assert scope['database'] == path, scope
                            worker = network._create_client(access, attachment_mode='network')

                            def connect(worker=worker, selected=selected):
                                handle = worker._connect_server({'route': selected})
                                handle.spb = b''
                                return handle

                            def release(worker=worker):
                                worker.close()
                                return not worker._connections and not worker._server_handles
                            result = manager.start(name, 'alias', scope, {
                                                   'capture_sensitive': True, 'log_statement_finish': True}, 'Owned '+name, connect, release)
                            assert result['native_started'], result
                            actors.append((name, result['trace_id']))
                        admin_item = manager._get('admin', 'alias', actors[0][1])
                        reader_item = manager._get('reader', 'alias', actors[1][1])
                        visible = reader_item.controller.trace.sessions
                        assert reader_item.native_id in visible and admin_item.native_id not in visible, visible
                        denied = False
                        try:
                            reader_item.controller.trace.stop(session_id=admin_item.native_id)
                        except Exception:
                            denied = True
                        assert denied and admin_item.native_id in admin_item.controller.trace.sessions
                        peer_route = {**route, 'database': 'TRACExALIAS'}
                        peer_created = admin.config.database_creator(**admin.config.database_create_arguments(
                            {**peer_route, 'database': sibling_path}, sibling_path, {}))
                        peer_created.close()
                        peer = admin._connect({'route': peer_route})
                        try:
                            q = peer.cursor()
                            q.execute("SELECT 'foreign_database_marker' FROM RDB$DATABASE")
                            q.fetchone()
                            q.close()
                            peer.rollback()
                        finally:
                            admin._forget_and_close(peer)
                        q = held.cursor()
                        q.execute("SELECT 'admin_private_marker' FROM RDB$DATABASE")
                        q.fetchone()
                        q.close()
                        user = reader._connect({'route': reader_route})
                        try:
                            user.execute_immediate('INSERT INTO T VALUES(23)')
                            transaction = user.main_transaction.info.id
                            q = user.cursor()
                            q.execute("SELECT 'reader_own_marker' FROM RDB$DATABASE")
                            q.fetchone()
                            q.close()
                            deadline = time.monotonic()+10
                            captured = {name: []for name, _ in actors}
                            cursors = {name: 0 for name, _ in actors}
                            while time.monotonic() < deadline:
                                for name, identity in actors:
                                    page = manager.poll(name, 'alias', identity, cursors[name])
                                    cursors[name] = page['next_sequence']
                                    captured[name].extend(x['text']for x in page['lines'])
                                if 'reader_own_marker' in ''.join(captured['reader']) and 'admin_private_marker' in ''.join(captured['admin']):
                                    break
                                time.sleep(.05)

                            assert 'reader_own_marker' in ''.join(
                                captured['reader']) and 'admin_private_marker' not in ''.join(captured['reader'])
                            assert 'reader_own_marker' in ''.join(
                                captured['admin']) and 'admin_private_marker' in ''.join(captured['admin'])
                            assert all('foreign_database_marker' not in ''.join(lines)
                                       for lines in captured.values())
                            for name, identity in actors:
                                result = manager.control(name, 'alias', identity, 'stop')
                                assert result['cleanup_confirmed'] and result['native_stop_acknowledged'], result
                            assert user.main_transaction.info.id == transaction
                            q = user.cursor()
                            q.execute('SELECT ID FROM T')
                            assert q.fetchall() == [(23,)]
                            q.close()
                            user.rollback()
                        finally:
                            reader._forget_and_close(user)

                        # 1. System audit (AuditTraceConfigFile) observation & log read-back
                        adm_srv = admin._connect_server({'route': route})
                        try:
                            adm_srv.database.get_statistics(
                                database='TRACE_ALIAS',
                                flags=module.SrvStatFlag.HDR_PAGES,
                                callback=lambda *_: None,
                            )
                            native_list = manager.list_native_sessions('admin', 'alias', adm_srv)['items']
                            audit_sessions = [row for row in native_list if row['system_audit']]
                            assert audit_sessions, native_list
                            audit_stopped_denied = False
                            try:
                                manager.observe_external_target(
                                    'admin', 'alias', adm_srv, audit_sessions[0]['native_session_id'],
                                )
                            except ValueError as err:
                                audit_stopped_denied = 'System audit' in str(err)
                            assert audit_stopped_denied
                        finally:
                            admin._release_server(adm_srv)
                        db_tail = read_audit_log_tail(str(audit_db_log), audit_dir)
                        svc_tail = read_audit_log_tail(str(audit_svc_log), audit_dir)
                        assert db_tail['present'] and any('admin_private_marker' in r['text'] for r in db_tail['lines']), db_tail
                        assert svc_tail['present'] and any('Database Stats' in r['text'] for r in svc_tail['lines']), svc_tail

                        # 2. Network service-scope trace
                        svc_scope = observe_scope(admin, route)
                        svc_worker = network._create_client(permissions, attachment_mode='network')
                        def svc_connect():
                            h = svc_worker._connect_server({'route': route})
                            h.spb = b''
                            return h
                        def svc_release():
                            svc_worker.close()
                            return not svc_worker._connections and not svc_worker._server_handles
                        svc_trace = manager.start_services(
                            'admin', 'alias', svc_scope,
                            {
                                'service_scope_confirmed': True,
                                'capture_sensitive': True,
                                'log_services': True,
                                'log_service_query': True,
                                'include_filter': 'Database Stats',
                            },
                            'Network Service Trace', svc_connect, svc_release,
                        )
                        assert svc_trace['native_started'] and svc_trace['trace_scope'] == 'services'
                        probe_srv = admin._connect_server({'route': route})
                        try:
                            probe_srv.database.get_statistics(
                                database='TRACE_ALIAS',
                                flags=module.SrvStatFlag.HDR_PAGES,
                                callback=lambda *_: None,
                            )
                        finally:
                            admin._release_server(probe_srv)
                        svc_captured = []
                        svc_cursor = 0
                        deadline = time.monotonic() + 10
                        while time.monotonic() < deadline:
                            page = manager.poll('admin', 'alias', svc_trace['trace_id'], svc_cursor)
                            svc_cursor = page['next_sequence']
                            svc_captured.extend(x['text'] for x in page['lines'])
                            if 'Database Stats' in ''.join(svc_captured):
                                break
                            time.sleep(0.05)
                        assert 'Database Stats' in ''.join(svc_captured), svc_captured
                        svc_stop = manager.control('admin', 'alias', svc_trace['trace_id'], 'stop')
                        assert svc_stop['cleanup_confirmed'] and svc_stop['native_stop_acknowledged']

                        # 3. External native trace session controls & restricted-user foreign refusal
                        ext_admin_srv = admin._connect_server({'route': route})
                        ext_admin_ctrl = admin._connect_server({'route': route})
                        ext_reader_srv = reader._connect_server({'route': reader_route})
                        try:
                            ext_id = ext_admin_srv.trace.start(
                                config='database\n{\nenabled = false\n}\nservices\n{\nenabled = true\nlog_services = true\n}\n',
                                name='AdminExternalCLI',
                            )
                            reader_denied = False
                            try:
                                manager.observe_external_target('reader', 'alias', ext_reader_srv, ext_id)
                            except ValueError:
                                reader_denied = True
                            assert reader_denied
                            observed_ext = manager.observe_external_target('admin', 'alias', ext_admin_ctrl, ext_id)
                            assert manager.control_external('admin', 'alias', ext_admin_ctrl, observed_ext, 'suspend_external')['state'] == 'suspended'
                            assert manager.control_external('admin', 'alias', ext_admin_ctrl, observed_ext, 'resume_external')['state'] == 'started'
                            assert manager.control_external('admin', 'alias', ext_admin_ctrl, observed_ext, 'stop_external')['state'] == 'stopped'
                        finally:
                            reader._release_server(ext_reader_srv)
                            admin._release_server(ext_admin_ctrl)
                            admin._release_server(ext_admin_srv)

                        # 4. Credential revocation mid-trace without ending independent user transactions
                        rev_pw = secrets.token_urlsafe(24)
                        adm_srv = admin._connect_server({'route': route})
                        try:
                            adm_srv.user.add(user_name='TR_REVOKED', password=rev_pw)
                        finally:
                            admin._release_server(adm_srv)
                        held.execute_immediate('GRANT SELECT ON T TO TR_REVOKED')
                        held.commit()
                        rev_route, rev_perms = provider_access({**base, 'user': 'TR_REVOKED'}, rev_pw)
                        rev_perms.require = lambda *_: None
                        rev_perms.allows = lambda *_: True
                        rev_client = network._create_client(rev_perms, attachment_mode='network')
                        try:
                            rev_scope = observe_scope(rev_client, rev_route)
                            rev_worker = network._create_client(rev_perms, attachment_mode='network')
                            def rev_connect():
                                h = rev_worker._connect_server({'route': rev_route})
                                h.spb = b''
                                return h
                            def rev_release():
                                rev_worker.close()
                                return not rev_worker._connections and not rev_worker._server_handles
                            rev_started = manager.start(
                                'revoked', 'alias', rev_scope,
                                {'log_connections': True}, 'Revoked Trace', rev_connect, rev_release,
                            )
                            assert rev_started['native_started']
                            adm_srv = admin._connect_server({'route': route})
                            try:
                                adm_srv.user.delete(user_name='TR_REVOKED')
                            finally:
                                admin._release_server(adm_srv)
                            reauth_failed = False
                            try:
                                bad_srv = rev_client._connect_server({'route': rev_route})
                                rev_client._release_server(bad_srv)
                            except Exception as auth_exc:
                                reauth_failed = rev_pw not in str(auth_exc)
                            assert reauth_failed
                            rev_stopped = manager.control('revoked', 'alias', rev_started['trace_id'], 'stop')
                            assert rev_stopped['cleanup_confirmed']
                        finally:
                            rev_client.close()

                        # 5. Owned listener transport loss mid-trace -> conservative non-success state, no retry
                        loss_port = _free_port()
                        loss_stage = area / 'loss_runtime'
                        _stage_runtime(runtime, loss_stage)
                        (loss_stage / 'firebird.conf').write_text(
                            'Providers = Remote,Engine13\nSecurityDatabase = ' + str(loss_stage / 'security5.fdb') + '\n'
                        )
                        loss_db = str(area / 'loss_target.fdb')
                        (loss_stage / 'databases.conf').write_text('LOSS_ALIAS = ' + loss_db + '\n')
                        loss_env = {
                            **os.environ,
                            'FIREBIRD': str(loss_stage),
                            'FIREBIRD_LOCK': str(loss_stage / 'lock'),
                        }
                        _initialize_security(loss_stage, password, loss_env)
                        loss_proc = subprocess.Popen(
                            [str(loss_stage / 'bin/firebird'), '-d', '-p', str(loss_port),
                             '-e', str(loss_stage), '-el', str(loss_stage / 'lock'), '-em', str(loss_stage)],
                            stdout=log, stderr=subprocess.STDOUT, env=loss_env,
                        )
                        try:
                            _wait_for_server(loss_proc, loss_port)
                            loss_base = {**base, 'port': loss_port, 'database': 'LOSS_ALIAS'}
                            loss_route, loss_perms = provider_access(loss_base, password)
                            loss_perms.require = lambda *_: None
                            loss_perms.allows = lambda *_: True
                            loss_client = network._create_client(loss_perms, attachment_mode='network')
                            try:
                                loss_created = loss_client.config.database_creator(
                                    **loss_client.config.database_create_arguments(
                                        {**loss_route, 'database': loss_db}, loss_db, {},
                                    ),
                                    password=password,
                                )
                                loss_created.close()
                                loss_scope = observe_scope(loss_client, loss_route)
                                loss_worker = network._create_client(loss_perms, attachment_mode='network')
                                def loss_connect():
                                    h = loss_worker._connect_server({'route': loss_route})
                                    h.spb = b''
                                    return h
                                def loss_release():
                                    loss_worker.close()
                                    return not loss_worker._connections and not loss_worker._server_handles
                                loss_trace = manager.start(
                                    'admin', 'loss', loss_scope,
                                    {'log_connections': True}, 'Transport Loss Trace',
                                    loss_connect, loss_release,
                                )
                                assert loss_trace['native_started']
                                loss_proc.kill()
                                loss_proc.wait(timeout=10)
                                loss_item = manager._get('admin', 'loss', loss_trace['trace_id'])
                                assert loss_item.done.wait(10)
                                loss_snap = loss_item.snapshot()
                                assert loss_snap['state'] in {'unknown_outcome', 'ended', 'cleanup_unknown'}, loss_snap
                                assert loss_snap['capture_success_inferred'] is False
                                assert loss_snap['automatic_retry'] is False
                                if not loss_snap['cleanup_confirmed']:
                                    loss_snap = manager.control('admin', 'loss', loss_trace['trace_id'], 'release')
                                assert loss_snap['cleanup_confirmed']
                            finally:
                                loss_client.close()
                        finally:
                            if loss_proc.poll() is None:
                                loss_proc.kill()
                                loss_proc.wait(timeout=10)

                        proof['modes'].append({
                            'mode': 'network',
                            'protocol': protocol,
                            'wire_encrypted_observed': encrypted,
                            'owned_listener_pid_observed': True,
                            'alias_resolved': True,
                            'restricted_own_capture': True,
                            'cross_user_capture_excluded': True,
                            'foreign_database_excluded': True,
                            'native_foreign_stop_denied': True,
                            'admin_capture_any_observed': True,
                            'caller_transaction_preserved': True,
                            'system_audit_database_and_services_verified': True,
                            'service_scope_trace_verified': True,
                            'external_session_controls_verified': True,
                            'credential_revocation_handled': True,
                            'transport_loss_conservative_outcome_verified': True,
                        })
                    finally:
                        assert manager.close()
                        admin._forget_and_close(held)
                        reader.close()
                        admin.close()
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=10)
                    process = None
        proof['owned_state_removed'] = not area.exists()
        proof['source_runtime_unchanged'] = _runtime_fingerprint(runtime) == before
        proof['complete'] = len(
            proof['modes']) == 1 and proof['owned_state_removed'] and proof['source_runtime_unchanged']
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        (output/'network.json').write_text(json.dumps(proof, indent=2)+'\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    value = qualify(args.runtime, args.output)
    print('Native network trace complete', value['complete'])
    raise SystemExit(0 if value['complete']else 1)

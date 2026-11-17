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
             'scope': 'Owned Linux loopback Firebird5.0.4 managed database trace with alias and restricted users; no HTTP, transport-loss, platform or system-audit acceptance'}
    files = ['web/pgadmin/cdeadmin/providers/firebird/' + name for name in (
        'trace_config.py', 'trace_sessions.py', 'query_client.py', 'provider.py',
        'metadata_guard.py', 'service_connection.py', 'connection_opening.py', 'local_services.py')]
    files += ['web/pgadmin/cdeadmin/providers/relational_admin.py',
              'web/pgadmin/cdeadmin/sdk/relational.py',
              'tools/cdeadmin_firebird_trace_network_qualification.py']
    proof['source_sha256'] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                              for name in files}
    before = _runtime_fingerprint(runtime)
    proof['not_qualified'] = ['transport loss and credential revocation', 'system audit and service trace',
                              'external trace session administration', 'Windows/macOS and human UI']
    process = None
    try:
        with tempfile.TemporaryDirectory(prefix='firebird-native-target-', dir=output) as folder:
            area = Path(folder)
            stage = area / 'runtime'
            _stage_runtime(runtime, stage)
            # Both explicit connection profiles share one exact client library.
            # Network transport is only the owned loopback listener below.
            (stage / 'firebird.conf').write_text(
                'Providers = Remote,Engine13\nSecurityDatabase = ' + str(stage / 'security5.fdb') + '\n')
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
                        proof['modes'].append({'mode': 'network', 'protocol': protocol, 'wire_encrypted_observed': encrypted, 'owned_listener_pid_observed': True, 'alias_resolved': True, 'restricted_own_capture': True,
                                              'cross_user_capture_excluded': True, 'foreign_database_excluded': True,
                                               'native_foreign_stop_denied': True, 'admin_capture_any_observed': True, 'caller_transaction_preserved': True})
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

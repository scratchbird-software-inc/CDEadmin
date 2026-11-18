"""Qualify same-host embedded Firebird 5.0.4 ISQL context and desktop launch."""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]

SOURCE_PATHS = [
    'web/pgadmin/cdeadmin/workspace/service.py',
    'web/pgadmin/cdeadmin/providers/firebird/local_services.py',
    'web/pgadmin/cdeadmin/ui_descriptors/firebird/tools.json',
    'runtime/src/js/firebirdIsql.js',
    'tools/firebird_desktop_native.mjs',
    'tools/cdeadmin_firebird_embedded_isql_qualification.py',
]


def qualify(runtime, output):
    import builtins
    builtins.SERVER_MODE = None
    import pgadmin  # noqa: F401
    from tools.cdeadmin_firebird_object_live_orchestrator import (
        _stage_runtime, _runtime_fingerprint,
    )
    from tools.cdeadmin_mysql_dump_verification_qualification import setup_application

    runtime, output = Path(runtime).resolve(), Path(output).resolve()
    if sys.platform != 'linux' or output == ROOT or ROOT in output.parents:
        raise ValueError('Use Linux and keep qualification evidence outside source')
    output.mkdir(parents=True, exist_ok=True)
    before = _runtime_fingerprint(runtime)
    proof = {
        'complete': False,
        'scope': (
            'Owned Linux Firebird 5.0.4 authenticated same-host embedded ISQL '
            'context and native Engine13 desktop launch; no Windows/macOS or '
            'human UI presentation acceptance.'
        ),
        'checks': [],
        'history_tests': 'not run',
        'source_sha256': {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in SOURCE_PATHS
        },
    }
    env_keys = ('FIREBIRD', 'FIREBIRD_LOCK', 'CDEADMIN_FIREBIRD_CLIENT_LIBRARY')
    previous_env = {k: os.environ.get(k) for k in env_keys}
    root = None
    try:
        with tempfile.TemporaryDirectory(prefix='firebird-emb-isql-', dir=output) as folder, ExitStack() as owners:
            root = Path(folder)
            stage = root / 'runtime'
            _stage_runtime(runtime, stage)
            (stage / 'firebird.conf').write_text(
                'Providers = Engine13\nSecurityDatabase = ' + str(stage / 'security5.fdb') + '\n'
            )
            (stage / 'databases.conf').write_text('')
            os.environ.update(
                FIREBIRD=str(stage),
                FIREBIRD_LOCK=str(stage / 'lock'),
                CDEADMIN_FIREBIRD_CLIENT_LIBRARY=str(stage / 'lib/libfbclient.so.5.0.4'),
            )
            import firebird.driver as module
            module.driver_config.fb_client_library.value = str(stage / 'lib/libfbclient.so.5.0.4')
            app = setup_application(root)

            def close_app():
                from pgadmin.cdeadmin.workspace.service import service_for_app
                with app.app_context():
                    svc = service_for_app(app)
                    svc.endpoint_service.provider_registry.close()

            owners.callback(close_app)
            from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
            from pgadmin.cdeadmin.providers.firebird.provider import _create_client
            from pgadmin.cdeadmin.endpoints.profiles import registration_profile
            from pgadmin.model import db, User, ServerGroup, Server, EndpointDatabaseTarget
            from flask import url_for

            data = root / 'data'
            data.mkdir()
            db_path = data / 'embedded isql 雪.fdb'
            route = {
                'attachment_mode': 'embedded',
                'database': str(db_path),
                'filesystem_root': str(data),
                'user': 'SYSDBA',
                'charset': 'UTF8',
            }
            helper = _create_client(
                SimpleNamespace(
                    require=lambda *_: None,
                    acquire_secret=lambda *_: (_ for _ in ()).throw(AssertionError('Network secret')),
                ),
                attachment_mode='embedded',
                profile=embedded.PROFILE,
                administration=embedded.ADMINISTRATION,
            )
            owners.callback(helper.close)
            creator = helper.config.database_creator(
                **helper.config.database_create_arguments(route, str(db_path), {})
            )
            try:
                creator.execute_immediate('CREATE TABLE OWNED_ISQL(ID INTEGER NOT NULL PRIMARY KEY)')
                creator.commit()
                q = creator.cursor()
                q.execute('INSERT INTO OWNED_ISQL VALUES(41)')
                q.close()
                creator.commit()
            finally:
                creator.close()

            with app.test_request_context('/'):
                user = User.query.first()
                uid = user.id
                group = ServerGroup.query.filter_by(user_id=uid).first()
                for name, pref in app.blueprints['NODE-engine_type'].connector_visibility.items():
                    if 'firebird' in name:
                        pref.set(True, user_id=uid)
                server = Server(
                    user_id=uid, servergroup_id=group.id,
                    name='Owned embedded ISQL',
                    host=None, port=1, username='SYSDBA',
                    maintenance_db=str(db_path), save_password=0,
                )
                server._cde_endpoint_registration = registration_profile('firebird-embedded')
                server._cde_endpoint_route_configuration = route
                db.session.add(server)
                db.session.commit()
                tid = str(uuid.uuid4())
                db.session.add(EndpointDatabaseTarget(
                    id=tid, endpoint_id=server.endpoint_profile.id,
                    display_name=db_path.name, database=str(db_path),
                    configuration='{}', active=1,
                ))
                db.session.commit()
                url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=server.id)
                verify_url = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=server.id)

            http = app.test_client()
            with http.session_transaction() as sess:
                sess['_user_id'] = str(uid)
                sess['_fresh'] = True
            verified = http.post(verify_url, json={}).get_json()
            assert verified['success'], verified

            # Open an idle catalog observation first; firebird_isql_context must release it so Super Engine13 ISQL can attach!
            ws_resp = http.get(url, query_string={'database_target_id': tid})
            assert ws_resp.status_code == 200 and ws_resp.get_json()['success']

            ctx_resp = http.post(url, json={
                'action': 'firebird_isql_context',
                'database_target_id': tid,
                'request': {'database_target_id': tid},
            })
            ctx_body = ctx_resp.get_json()
            assert ctx_resp.status_code == 200 and ctx_body['success'], ctx_body
            assert ctx_resp.headers['Cache-Control'] == 'no-store'
            isql_ctx = ctx_body['data']
            assert isql_ctx['attachment_mode'] == 'embedded'
            assert isql_ctx['native_provider'] == 'Engine13'
            assert isql_ctx['password_required'] is False
            assert 'dsn' not in isql_ctx and 'password' not in isql_ctx
            proof['checks'].append({
                'case': 'authenticated-http-embedded-isql-context',
                'idle_catalog_released': True,
                'no_store_and_secret_free': True,
            })

            # Create an owned xterm shim that runs the exact ISQL command + SQL script and writes output atomically.
            bin_dir = root / 'shim-bin'
            bin_dir.mkdir()
            sql_script = root / 'session.sql'
            isql_out = root / 'isql_out.txt'
            isql_env_json = root / 'isql_env.json'
            sql_script.write_text(
                "SET HEADING OFF;\n"
                "SELECT ID, RDB$GET_CONTEXT('SYSTEM', 'ENGINE_VERSION'), COALESCE(MON$REMOTE_PROTOCOL, 'LOCAL_ENGINE13') "
                "FROM OWNED_ISQL CROSS JOIN MON$ATTACHMENTS WHERE MON$ATTACHMENT_ID = CURRENT_CONNECTION;\n"
                "INSERT INTO OWNED_ISQL VALUES (88);\n"
                "COMMIT;\n"
                "QUIT;\n",
                encoding='utf-8',
            )
            xterm_shim = bin_dir / 'xterm'
            xterm_shim.write_text(
                f"#!{sys.executable}\n"
                "import json, os, subprocess, sys\n"
                "assert sys.argv[1] == '-e', sys.argv\n"
                "cmd = sys.argv[2:]\n"
                f"with open({str(isql_env_json)!r}, 'w') as ef:\n"
                "    json.dump({'has_isc_password': 'ISC_PASSWORD' in os.environ, 'firebird': os.environ.get('FIREBIRD'), 'cmd': cmd}, ef)\n"
                f"sql = open({str(sql_script)!r}).read()\n"
                "res = subprocess.run(cmd, input=sql, text=True, capture_output=True, timeout=15)\n"
                f"with open({str(isql_out)!r}, 'w') as of:\n"
                "    of.write(f'RC={res.returncode}\\n' + res.stdout + '\\nERR=' + res.stderr)\n",
                encoding='utf-8',
            )
            xterm_shim.chmod(0o755)

            req_file = root / 'launch_req.json'
            receipt_file = root / 'launch_receipt.json'
            req_file.write_text(json.dumps({
                'executable': str(runtime / 'bin/isql'),
                'terminal': str(xterm_shim),
                'connection': isql_ctx,
                'hostProbe': {'stageParent': str(root)},
            }), encoding='utf-8')
            node_env = {k: v for k, v in os.environ.items() if k != 'CDEADMIN_NATIVE_FIXTURE_PASSWORD'}
            node_env['ISC_PASSWORD'] = 'must-be-stripped'
            subprocess.run(
                ['node', str(ROOT / 'tools/firebird_desktop_native.mjs'), 'isql', str(req_file), str(receipt_file)],
                env=node_env, check=True, timeout=20,
            )
            receipt = json.loads(receipt_file.read_text())
            assert receipt['state'] == 'process_started'
            assert receipt['attachment_mode'] == 'embedded'
            assert receipt['native_provider'] == 'Engine13'
            assert receipt['native_connection_confirmed'] is False
            assert receipt['transaction_outcome'] == 'owned-by-isql'

            deadline = time.monotonic() + 10.0
            while not isql_out.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            assert isql_out.exists(), 'Spawned ISQL terminal shim did not complete'
            out_text = isql_out.read_text()
            env_obs = json.loads(isql_env_json.read_text())
            assert 'RC=0' in out_text and '41' in out_text and '5.0.4' in out_text and 'LOCAL_ENGINE13' in out_text, out_text
            assert env_obs['has_isc_password'] is False

            conn = helper._connect({'route': route})
            try:
                cur = conn.cursor()
                cur.execute('SELECT ID FROM OWNED_ISQL ORDER BY ID')
                assert cur.fetchall() == [(41,), (88,)]
                cur.close()
                conn.rollback()
            finally:
                helper._forget_and_close(conn)
            proof['checks'].append({
                'case': 'native-engine13-isql-launch-and-commit-readback',
                'remote_protocol_absent': True,
                'isc_password_stripped': True,
                'committed_row_88_verified': True,
            })

            # Cross-host boot_id mismatch must refuse before spawning terminal.
            isql_out.unlink()
            cross_req = root / 'cross_host_req.json'
            cross_req.write_text(json.dumps({
                'executable': str(runtime / 'bin/isql'),
                'terminal': str(xterm_shim),
                'connection': isql_ctx,
                'hostProbe': {
                    'bootId': '00000000-0000-0000-0000-000000000000',
                    'stageParent': str(root),
                },
            }), encoding='utf-8')
            cross_run = subprocess.run(
                ['node', str(ROOT / 'tools/firebird_desktop_native.mjs'), 'isql', str(cross_req), str(root / 'cross_out.json')],
                env=node_env, capture_output=True, text=True, timeout=15,
            )
            assert cross_run.returncode != 0 and 'same host' in cross_run.stderr
            assert not isql_out.exists()
            proof['checks'].append({
                'case': 'cross-host-boot-id-refused',
                'no_process_spawned': True,
            })

            # Replaced database inode after context issuance must refuse before spawning terminal.
            db_path.rename(data / 'moved_original.fdb')
            db_path.write_bytes(b'foreign replacement file')
            inode_run = subprocess.run(
                ['node', str(ROOT / 'tools/firebird_desktop_native.mjs'), 'isql', str(req_file), str(root / 'inode_out.json')],
                env=node_env, capture_output=True, text=True, timeout=15,
            )
            assert inode_run.returncode != 0 and 'changed since the server issued' in inode_run.stderr
            assert not isql_out.exists()
            proof['checks'].append({
                'case': 'replaced-database-inode-refused',
                'no_process_spawned': True,
            })

        proof['owned_state_removed'] = root is not None and not root.exists()
        proof['source_runtime_unchanged'] = _runtime_fingerprint(runtime) == before
        proof['complete'] = (
            len(proof['checks']) == 4 and
            proof['owned_state_removed'] and
            proof['source_runtime_unchanged']
        )
    finally:
        for k, v in previous_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        (output / 'isql.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    res = qualify(args.runtime, args.output)
    print(json.dumps({'complete': res['complete'], 'checks': len(res['checks'])}))
    raise SystemExit(0 if res['complete'] else 1)

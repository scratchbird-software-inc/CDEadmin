"""Qualify native Firebird 5.0.4 fb_lock_print diagnostics (Engine13, contention, grants & HTTP)."""
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
    'web/pgadmin/cdeadmin/providers/firebird/lock_print.py',
    'web/pgadmin/cdeadmin/workspace/firebird_lock_print_actions.py',
    'web/pgadmin/cdeadmin/workspace/service.py',
    'web/pgadmin/browser/server_groups/servers/__init__.py',
    'web/pgadmin/cdeadmin/ui_descriptors/firebird/tools.json',
    'web/pgadmin/cdeadmin/providers/firebird/firebird_embedded_dialect_5_0_4.json',
    'web/pgadmin/cdeadmin/providers/firebird/firebird_embedded_metrics_5_0_4.json',
    'tools/cdeadmin_firebird_lock_print_qualification.py',
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
            'Owned Linux Firebird 5.0.4 native fb_lock_print structured diagnostics, '
            'cross-process lock contention, interactive sampling, restricted-user and '
            'remote-TCP refusals, same-host grant manifest and authenticated HTTP; '
            'no Windows/macOS or human UI acceptance.'
        ),
        'checks': [],
        'history_tests': 'not run',
        'source_sha256': {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in SOURCE_PATHS
        },
    }
    env_keys = (
        'FIREBIRD', 'FIREBIRD_LOCK', 'CDEADMIN_FIREBIRD_CLIENT_LIBRARY',
        'CDEADMIN_FIREBIRD_LOCK_PRINT_BINARY', 'CDEADMIN_FIREBIRD_HOST_TOOLS_MANIFEST',
    )
    previous_env = {k: os.environ.get(k) for k in env_keys}
    root = None
    try:
        with tempfile.TemporaryDirectory(prefix='firebird-lock-print-', dir=output) as folder, ExitStack() as owners:
            root = Path(folder)
            stage = root / 'runtime'
            _stage_runtime(runtime, stage)
            (stage / 'firebird.conf').write_text(
                'Providers = Engine13\nServerMode = Classic\nSecurityDatabase = '
                + str(stage / 'security5.fdb') + '\n'
            )
            (stage / 'databases.conf').write_text('')
            os.environ.update(
                FIREBIRD=str(stage),
                FIREBIRD_LOCK=str(stage / 'lock'),
                CDEADMIN_FIREBIRD_CLIENT_LIBRARY=str(stage / 'lib/libfbclient.so.5.0.4'),
                CDEADMIN_FIREBIRD_LOCK_PRINT_BINARY=str(stage / 'bin/fb_lock_print'),
            )
            os.environ.pop('CDEADMIN_FIREBIRD_HOST_TOOLS_MANIFEST', None)
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
            from pgadmin.cdeadmin.providers.firebird import lock_print as lp
            from pgadmin.cdeadmin.providers.firebird.provider import _create_client
            from pgadmin.cdeadmin.endpoints.profiles import registration_profile
            from pgadmin.model import db, User, ServerGroup, Server, EndpointDatabaseTarget
            from flask import url_for

            data = root / 'data'
            data.mkdir()
            db_path = data / 'locks 雪.fdb'
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
                creator.execute_immediate('CREATE TABLE LOCK_ROWS(ID INTEGER NOT NULL PRIMARY KEY, V INTEGER)')
                creator.commit()
                q = creator.cursor()
                q.execute('INSERT INTO LOCK_ROWS VALUES(1, 10)')
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
                    name='Owned embedded lock print',
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

            def post_lp(action, extra=None, expect_ok=True):
                req_body = {'database_target_id': tid, 'action': action, **(extra or {})}
                resp = http.post(url, json={
                    'action': 'firebird_lock_print',
                    'database_target_id': tid,
                    'request': req_body,
                })
                body = resp.get_json()
                assert resp.headers.get('Cache-Control') == 'no-store'
                if expect_ok:
                    assert resp.status_code == 200 and body.get('success'), (action, resp.status_code, body)
                    return body['data']
                assert not body.get('success'), body
                return body

            desc = post_lp('describe')
            assert desc['schema'] == 'scratchrobin.firebird.lock-print-api@1'
            assert desc['published_as_default_metric'] is False

            # 1. Unmapped lock table when no attachments are open.
            rev_idle = post_lp('review', {'options': {'owners': True, 'locks': True}})
            res_idle = post_lp('apply', {
                'review_id': rev_idle['review_id'],
                'review_digest': rev_idle['review_digest'],
                'confirmed': True,
            })
            assert res_idle['outcome']['parsed']['lock_table_state'] == 'unmapped_no_active_attachments'
            # Replay must be refused.
            post_lp('apply', {
                'review_id': rev_idle['review_id'],
                'review_digest': rev_idle['review_digest'],
                'confirmed': True,
            }, expect_ok=False)
            proof['checks'].append({
                'case': 'unmapped-idle-lock-table-and-replay-refusal',
                'lock_table_state': 'unmapped_no_active_attachments',
            })

            # 2. Real cross-process lock waiter contention via authenticated HTTP (redacted & confirmed raw keys).
            holder = helper._connect({'route': route})
            waiter_proc = None
            try:
                holder.execute_immediate('UPDATE LOCK_ROWS SET V = 20 WHERE ID = 1')
                isql_env = {k: v for k, v in os.environ.items() if not k.startswith('ISC_')}
                isql_env['LD_LIBRARY_PATH'] = str(stage / 'lib')
                waiter_proc = subprocess.Popen(
                    [str(stage / 'bin/isql'), '-q', '-user', 'SYSDBA', str(db_path)],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, env=isql_env,
                )
                waiter_proc.stdin.write(
                    'SET TRANSACTION READ COMMITTED RECORD_VERSION WAIT;\n'
                    'UPDATE LOCK_ROWS SET V = 30 WHERE ID = 1;\n'
                    'ROLLBACK;\nQUIT;\n'
                )
                waiter_proc.stdin.flush()
                time.sleep(0.4)

                rev_wait = post_lp('review', {'options': {
                    'owners': True, 'locks': True, 'waiting_only': True, 'pending_only': True,
                }})
                res_wait = post_lp('apply', {
                    'review_id': rev_wait['review_id'],
                    'review_digest': rev_wait['review_digest'],
                    'confirmed': True,
                })
                parsed = res_wait['outcome']['parsed']
                assert parsed['lock_table_state'] == 'active'
                assert parsed['header']['version'] > 0
                assert any(o['is_waiting'] and o['pid'] == waiter_proc.pid for o in parsed['owners']), parsed['owners']
                assert len(parsed['locks']) >= 1
                assert all(lk['key'] == '[redacted]' and lk['key_redacted'] for lk in parsed['locks'])

                # Interactive counter sample while lock table is active.
                rev_int = post_lp('review', {'options': {
                    'interactive_seconds': 1, 'interactive_interval': 1, 'interactive_counters': 'aotw', 'timeout_seconds': 10,
                }})
                res_int = post_lp('apply', {
                    'review_id': rev_int['review_id'],
                    'review_digest': rev_int['review_digest'],
                    'confirmed': True,
                })
                assert res_int['outcome']['parsed']['lock_table_state'] == 'interactive_sampled'
                assert len(res_int['outcome']['parsed']['interactive_samples']) >= 1
                assert res_int['outcome']['parsed']['interactive_average'] is not None
            finally:
                holder.rollback()
                helper._forget_and_close(holder)
                if waiter_proc is not None:
                    waiter_proc.communicate(timeout=10)
            proof['checks'].append({
                'case': 'authenticated-http-cross-process-waiter-and-interactive-sampling',
                'waiter_pid_observed': True,
                'keys_redacted_by_default': True,
                'interactive_samples_observed': True,
            })

            # Verify durable journal on disk contains zero raw lock keys/text.
            listing = post_lp('list')
            assert len(listing['items']) >= 3
            for jfile in root.rglob('firebird-lock-print-operations.json'):
                raw_disk = jfile.read_text()
                assert 'sanitized_text' not in raw_disk and 'LOCK_HEADER BLOCK' not in raw_disk

            # 3. Foreign-owner server refusal + revoked maintenance_admin refusal + remote TCP vs same-host grant manifest.
            with app.test_request_context('/'):
                other_user = User(username='restricted', email='restricted@example.invalid', password='x', active=True, auth_source='internal')
                db.session.add(other_user)
                db.session.commit()
                other_group = ServerGroup(user_id=other_user.id, name='Foreign group')
                db.session.add(other_group)
                db.session.commit()
                foreign_server = Server(
                    user_id=other_user.id, servergroup_id=other_group.id,
                    name='Foreign server', host=None, port=1, username='SYSDBA',
                    maintenance_db=str(db_path), save_password=0,
                )
                foreign_server._cde_endpoint_registration = registration_profile('firebird-embedded')
                foreign_server._cde_endpoint_route_configuration = route
                db.session.add(foreign_server)
                db.session.commit()
                foreign_url = url_for('NODE-server.cde_workspace_id', gid=other_group.id, sid=foreign_server.id)
            foreign_resp = http.post(foreign_url, json={
                'action': 'firebird_lock_print',
                'database_target_id': tid,
                'request': {'database_target_id': tid, 'action': 'describe'},
            })
            assert foreign_resp.status_code != 200 or not (foreign_resp.get_json() or {}).get('success')

            from pgadmin.cdeadmin.workspace.service import service_for_app
            with app.app_context():
                svc = service_for_app(app)
                ctx_obj, _, _ = svc.endpoint_service.workspace(
                    Server.query.filter_by(name='Owned embedded lock print').first(),
                    database_target_id=tid,
                )
                prov = svc.endpoint_service.provider_registry.resolve(ctx_obj).instance
                orig_req = prov._require

                def deny_maint(perm, *a):
                    if perm == 'maintenance_admin':
                        raise PermissionError('maintenance_admin')
                    return orig_req(perm, *a)

                prov._require = deny_maint
                try:
                    post_lp('review', {'options': {'owners': True}}, expect_ok=False)
                finally:
                    prov._require = orig_req

            # Remote TCP without host grant manifest is refused; with operator manifest it succeeds.
            tcp_route = {'host': '127.0.0.1', 'port': 3050, 'database': str(db_path)}
            try:
                lp.resolve_host_scope('ep-tcp-1', tcp_route)
            except ValueError as err:
                assert 'CDEADMIN_FIREBIRD_HOST_TOOLS_MANIFEST' in str(err)
            else:
                raise AssertionError('TCP route without host grant manifest was admitted')

            manifest_file = root / 'fb-host-grants.json'
            manifest_file.write_text(json.dumps({
                'format': 'scratchrobin.firebird.host-tools@1',
                'grants': [{
                    'endpoint_id': 'ep-tcp-1',
                    'firebird_runtime_root': str(stage),
                    'firebird_lock_directory': str(stage / 'lock'),
                    'databases': [str(db_path)],
                }],
            }), encoding='utf-8')
            os.environ['CDEADMIN_FIREBIRD_HOST_TOOLS_MANIFEST'] = str(manifest_file)
            granted_scope = lp.resolve_host_scope('ep-tcp-1', tcp_route)
            assert granted_scope['attachment_mode'] == 'same_host_granted_network'
            granted_out = lp.execute_lock_print(granted_scope, lp.normalize_options({'owners': True}))
            assert granted_out['state'] == 'completed'
            proof['checks'].append({
                'case': 'unauth-refusal-and-same-host-network-grant-manifest',
                'remote_tcp_refused_without_manifest': True,
                'granted_same_host_admitted': True,
            })

            # 4. Stale database inode after review is rejected without spawning fb_lock_print.
            stale_rev = post_lp('review', {'options': {'owners': True}})
            db_path.rename(data / 'moved_locks.fdb')
            db_path.write_bytes(b'foreign replacement')
            stale_apply = post_lp('apply', {
                'review_id': stale_rev['review_id'],
                'review_digest': stale_rev['review_digest'],
                'confirmed': True,
            })
            assert stale_apply['outcome']['state'] == 'rejected'
            assert stale_apply['outcome']['native_dispatched'] is False
            proof['checks'].append({
                'case': 'stale-inode-rejected-before-dispatch',
                'native_dispatched': False,
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
        (output / 'lock_print.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    res = qualify(args.runtime, args.output)
    print(json.dumps({'complete': res['complete'], 'checks': len(res['checks'])}))
    raise SystemExit(0 if res['complete'] else 1)

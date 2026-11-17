"""Qualify private Firebird recipe revisions via authenticated HTTP and restart.

Uses owned Engine13-only 5.0.4 fixtures and an isolated application database.
No history qualification, browser acceptance or other platform is implied.
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
    if sys.platform != 'linux':
        raise ValueError('This native runtime qualifier requires Linux')
    W = Path(output).resolve()
    R = ROOT
    if W == R or R in W.parents:
        raise ValueError('Keep evidence outside the source')
    W.mkdir(parents=True, exist_ok=True)
    import builtins
    builtins.SERVER_MODE = None
    import pgadmin
    from tools.cdeadmin_firebird_object_live_orchestrator import _stage_runtime, _runtime_fingerprint
    runtime = Path(runtime).resolve()
    before = _runtime_fingerprint(runtime)
    proof = {'complete': False, 'scope': 'Owned Engine13 Firebird5.0.4 authenticated desktop HTTP private recipe revisions and fresh-process persistence; no browser/platform acceptance.', 'checks': [], 'source_sha256': {p: hashlib.sha256((R/p).read_bytes()).hexdigest(
    )for p in ['web/pgadmin/cdeadmin/providers/firebird/local_services.py', 'web/pgadmin/cdeadmin/providers/firebird/embedded_provider.py', 'web/pgadmin/cdeadmin/providers/firebird/provider.py', 'web/pgadmin/cdeadmin/providers/firebird/query_client.py', 'web/pgadmin/cdeadmin/providers/firebird/service_connection.py', 'web/pgadmin/cdeadmin/providers/firebird/firebird_embedded_dialect_5_0_4.json', 'web/pgadmin/cdeadmin/providers/firebird/firebird_embedded_metrics_5_0_4.json', 'web/pgadmin/cdeadmin/ui_descriptors/firebird/capabilities.json']}}
    for name in ('web/pgadmin/cdeadmin/workspace/firebird_recipe_assets.py', 'web/pgadmin/cdeadmin/workspace/mysql_recipe_assets.py', 'web/pgadmin/cdeadmin/workspace/service.py', 'web/pgadmin/browser/server_groups/servers/__init__.py', 'web/pgadmin/cdeadmin/ui_descriptors/firebird/tools.json'):
        proof['source_sha256'][name] = hashlib.sha256((R/name).read_bytes()).hexdigest()
    proof['runner_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    proof['history_tests'] = 'not run'
    try:
        with tempfile.TemporaryDirectory(prefix='firebird-local-http-', dir=W)as area:
            root = Path(area)
            stage = root/'runtime'
            _stage_runtime(runtime, stage)
            (stage/'firebird.conf').write_text('Providers = Engine13\nSecurityDatabase = ' +
                                               str(stage/'security5.fdb')+'\n')
            (stage/'databases.conf').write_text('')
            os.environ.update(FIREBIRD=str(stage), FIREBIRD_LOCK=str(stage/'lock'),
                              CDEADMIN_FIREBIRD_CLIENT_LIBRARY=str(stage/'lib/libfbclient.so.5.0.4'))
            import firebird.driver as module
            module.driver_config.fb_client_library.value = str(stage/'lib/libfbclient.so.5.0.4')
            from tools.cdeadmin_mysql_dump_verification_qualification import setup_application
            app = setup_application(root)
            from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
            from pgadmin.cdeadmin.providers.firebird.provider import _create_client, _resources
            from pgadmin.cdeadmin.endpoints.profiles import registration_profile
            from pgadmin.model import db, User, ServerGroup, Server, EndpointDatabaseTarget
            from flask import url_for
            data = root/'data'
            data.mkdir()
            path = data/'HTTP 雪.fdb'
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
            empty = post('firebird_recipe_read', {'recipe_id': 'native'})
            assert empty['version'] == 0 and empty['recipe'] is None and not empty['executed']
            native_client = _create_client(SimpleNamespace(require=lambda *_: None, acquire_secret=None),
                                           attachment_mode='embedded', profile=embedded.PROFILE, administration=embedded.ADMINISTRATION)
            held = native_client.open_session({'route': route})
            held.execute_immediate('INSERT INTO HTTP_STATS VALUES(23)')
            transaction_before = held.main_transaction.info.id
            recipe = {'format': 'scratchrobin.firebird.test-data@1', 'scope': empty['scope'], 'seed': 1, 'tables': [
                {'table': 'HTTP_STATS', 'count': 2, 'columns': {'ID': {'kind': 'sequential', 'start': '9007199254740993', 'step': '1'}}}]}
            request = {'recipe_id': 'native', 'expected_version': 0, 'recipe': recipe}
            first = post('firebird_recipe_save', request)
            assert first['version'] == 1 and not first['executed'] and first['requires_native_preview'] and not first['source_control_eligible']
            response = client.post(url, json={'action': 'firebird_recipe_save', 'database_target_id': tid, 'request': {
                                   'database_target_id': tid, **request}})
            assert response.status_code == 409 and response.get_json(
            )['info'] == 'FIREBIRD_RECIPE_CONFLICT', response.get_json()
            assert response.headers['Cache-Control'] == 'no-store'
            second = post('firebird_recipe_save', {
                          **request, 'expected_version': 1, 'recipe': {**recipe, 'seed': 2}})
            assert second['version'] == 2
            old = post('firebird_recipe_read', {'recipe_id': 'native', 'version': 1})
            assert old['recipe'] == recipe and old['current_version'] == 2
            for bad in ({**recipe, 'scope': {}}, {**recipe, 'tables': [{'table': 'missing', 'count': 1, 'columns': {}}]},
                        {**recipe, 'tables': [{'table': 'HTTP_STATS', 'count': 1,
                                               'columns': {'ID': {'kind': 'constant', 'value': 0.1}}}]},
                        {**recipe, 'tables': [{'table': 'HTTP_STATS', 'count': 1, 'columns': {'ID': {'kind': 'constant', 'value': {'password': 'never stored'}}}}]}):
                post('firebird_recipe_save', {**request,
                     'expected_version': 2, 'recipe': bad}, denied=True)
            assert post('firebird_recipe_read', {'recipe_id': 'native'})['version'] == 2
            assert held.main_transaction.info.id == transaction_before
            q = held.cursor()
            q.execute('SELECT ID FROM HTTP_STATS')
            assert q.fetchall() == [(23,)]
            q.close()
            held.rollback()
            assert native_client.close_session(held)['connection_released']
            try:
                c = native_client._connect({'route': route})
                try:
                    q = c.cursor()
                    q.execute("SELECT RDB$GET_CONTEXT('SYSTEM','ENGINE_VERSION') FROM RDB$DATABASE")
                    assert q.fetchone() == ('5.0.4',)
                    q.execute('SELECT COUNT(*) FROM HTTP_STATS')
                    assert q.fetchone() == (0,)
                    q.close()
                    c.rollback()
                finally:
                    native_client._forget_and_close(c)
            finally:
                native_client.close()
            with app.app_context():
                from pgadmin.cdeadmin.workspace.service import service_for_app
                service_for_app(app).endpoint_service.provider_registry.close()
                from pgadmin.cdeadmin.workspace.assets import ProjectAssetService, ProjectAssetRepository
                from pgadmin.cdeadmin.workspace.firebird_recipe_assets import FirebirdRecipeAssets
                db.session.remove()
                db.engine.dispose()
                reopened = FirebirdRecipeAssets(ProjectAssetService(ProjectAssetRepository()))
                assert reopened.apply(uid, empty['scope'], 'read', {
                                      'recipe_id': 'native', 'version': 1})['recipe'] == recipe
                assert reopened.apply(
                    uid, {**empty['scope'], 'database_target_id': 'different'}, 'read', {'recipe_id': 'native'})['recipe'] is None
                assert reopened.apply(
                    uid+1000, empty['scope'], 'read', {'recipe_id': 'native'})['recipe'] is None
                db.session.remove()
            # A fresh process reads the same on-disk application database. It does not
            # acquire a native database attachment.
            import subprocess
            probe = root/'reopen.py'
            payload = root/'reopen.json'
            payload.write_text(json.dumps(
                {'owner': uid, 'scope': empty['scope'], 'recipe': recipe}))
            probe.write_text("from pathlib import Path\nimport sys,json\nsys.path[:0]="+repr([str(R), str(R/'web'), str(R/'tools')])+"\nfrom tools.cdeadmin_mysql_dump_verification_qualification import setup_application\napp=setup_application(Path("+repr(str(root))+"))\nfrom pgadmin.cdeadmin.workspace.assets import ProjectAssetService,ProjectAssetRepository\nfrom pgadmin.cdeadmin.workspace.firebird_recipe_assets import FirebirdRecipeAssets\nv=json.loads(Path("+repr(
                str(payload))+").read_text())\nwith app.app_context():\n r=FirebirdRecipeAssets(ProjectAssetService(ProjectAssetRepository())).apply(v['owner'],v['scope'],'read',{'recipe_id':'native','version':1})\n assert r['recipe']==v['recipe'] and r['current_version']==2 and not r['executed']\nprint('fresh-process revision1 exact read passed')\n")
            with (W/'firebird-recipe-reopen.log').open('w') as log:
                reopened_process = subprocess.run(
                    [sys.executable, '-B', str(probe)], env=os.environ, cwd=R, stdout=log, stderr=subprocess.STDOUT, timeout=180)
            assert reopened_process.returncode == 0
            proof['checks'].append(
                'Authenticated native-catalog save, private exact revisions,409 CAS conflict,no-store,invalid scope/table/number/secret refusal; source table remains empty and unrelated pending transaction preserved')
            proof['checks'].append(
                'Real SQLite-backed revisions survive disposed connections and a fresh application process; owner/target isolation')

        proof['owned_state_removed'] = not root.exists()
        proof['source_runtime_unchanged'] = _runtime_fingerprint(runtime) == before
        proof['complete'] = proof['owned_state_removed'] and proof['source_runtime_unchanged']
    finally:
        (W/'firebird-recipe-http.json').write_text(json.dumps(proof, indent=2)+'\n')
    print('Authenticated recipes passed', len(proof['checks']))

    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = qualify(args.runtime, args.output)
    raise SystemExit(0 if result['complete'] else 1)

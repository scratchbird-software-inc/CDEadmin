"""Qualify owned Engine13 recovery without opening the unavailable primary."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def qualify(runtime, output):
    from tools.cdeadmin_firebird_object_live_orchestrator import _stage_runtime, _runtime_fingerprint
    runtime, output = Path(runtime).resolve(), Path(output).resolve()
    if sys.platform != 'linux' or output == ROOT or ROOT in output.parents:
        raise ValueError('Use Linux and evidence outside source')
    output.mkdir(parents=True, exist_ok=True)
    proof = {'complete': False, 'checks': [], 'history_tests': 'not run',
             'scope': 'Owned Linux Firebird5.0.4 Engine13 shadow activation; no network/platform/UI acceptance'}
    paths = ['web/pgadmin/cdeadmin/providers/firebird/' + name for name in (
        'local_services.py', 'embedded_provider.py', 'query_client.py', 'provider.py', 'shadow_activation.py')]
    paths += ['web/pgadmin/cdeadmin/providers/relational_admin.py',
              'web/pgadmin/cdeadmin/ui_descriptors/firebird/capabilities.json',
              'web/pgadmin/cdeadmin/ui_descriptors/firebird/operations.json',
              'tools/cdeadmin_firebird_local_shadow_qualification.py']
    proof['source_sha256'] = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}
    before = _runtime_fingerprint(runtime)
    try:
        with tempfile.TemporaryDirectory(prefix='firebird-local-shadow-', dir=output) as folder:
            area = Path(folder); stage = area/'runtime'; _stage_runtime(runtime, stage)
            (stage/'firebird.conf').write_text('Providers = Engine13\nSecurityDatabase = ' + str(stage/'security5.fdb') + '\n')
            (stage/'databases.conf').write_text('')
            os.environ.update(FIREBIRD=str(stage), FIREBIRD_LOCK=str(stage/'lock'),
                CDEADMIN_FIREBIRD_CLIENT_LIBRARY=str(stage/'lib/libfbclient.so.5.0.4'))
            import firebird.driver as module
            module.driver_config.fb_client_library.value = str(stage/'lib/libfbclient.so.5.0.4')
            from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
            from pgadmin.cdeadmin.providers.firebird.provider import _create_client, _firebird_service_operation
            from pgadmin.cdeadmin.providers.firebird.shadow_activation import verify_header
            from pgadmin.cdeadmin.visual_admin import ProviderVisualAdministration, VisualAdminAccessError, VisualAdminExecutionError
            permitted = {'embedded_runtime', 'filesystem', 'data_read', 'administer', 'execute', 'maintenance_admin'}
            def require(name, *_):
                if name not in permitted: raise PermissionError(name)
            def secret(*_): raise AssertionError('Recovery acquired a network credential')
            permissions = SimpleNamespace(require=require, allows=lambda name, *_: name in permitted, acquire_secret=secret)
            client = _create_client(permissions, attachment_mode='embedded', profile=embedded.PROFILE, administration=embedded.ADMINISTRATION)
            context = SimpleNamespace(endpoint_id='owned-shadow', mode='provider_native', provider_id=embedded.PROFILE.provider_id,
                profile_id=embedded.PROFILE.profile_id, runtime_verification_state='verified', declared_runtime_family='firebird', verified_runtime_family='firebird')
            visual = ProviderVisualAdministration(context, permissions, 'firebird', '5.0.4', client)
            data = area/'data'; data.mkdir()
            def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
            def fixture(name, linger=0):
                original_folder = data/(name+'-original'); original_folder.mkdir()
                primary = original_folder/'primary.fdb'
                shadow = data/(name+" recovered 雪's.shd")
                route = {'attachment_mode': 'embedded', 'database': str(primary), 'filesystem_root': str(data), 'user': 'SYSDBA', 'charset': 'UTF8'}
                c = client.config.database_creator(**client.config.database_create_arguments(route, str(primary), {}))
                try:
                    c.execute_immediate('CREATE TABLE OWNED(ID INTEGER)'); c.commit()
                    c.execute_immediate('INSERT INTO OWNED VALUES(17)'); c.commit()
                    c.execute_immediate('ALTER DATABASE SET LINGER TO '+str(linger)); c.commit()
                    c.execute_immediate("CREATE SHADOW 1 MANUAL '"+str(shadow).replace("'", "''")+"'"); c.commit()
                finally: c.close()
                if linger: time.sleep(linger+0.2)
                archive = data/(name+' isolated primary.fdb')
                primary.rename(archive); original_folder.rmdir()
                return route, shadow, archive, digest(archive)
            def header(route, shadow):
                server = client._connect_server({'route': {**route, 'database': str(shadow)}})
                try: return _firebird_service_operation(server, 'database_statistics', str(shadow), {'statistics_flags': ['HDR_PAGES']}, module)['output']
                finally: client._release_server(server)
            def review(route, shadow):
                request = {'resource_kind': 'database', 'operation_id': 'activate_shadow', '_provider_route': route,
                    'draft': {'shadow_filename': str(shadow), 'confirmation': str(shadow), 'original_isolated': True}}
                validation = visual.validate(request); assert validation['valid'], validation
                plan = visual.plan(request)
                return {'plan_id': plan['plan_id'], 'plan_digest': plan['plan_digest'], 'confirmed': True}
            def replay_refused(request):
                try: visual.apply(request)
                except VisualAdminAccessError: pass
                else: raise AssertionError('Consumed recovery review replayed')
            try:
                for linger in (0, 1):
                    route, shadow, archive, original_hash = fixture('linger-'+str(linger), linger)
                    assert verify_header(header(route, shadow))['active_shadow_verified']
                    connections = []; connect = client._connect
                    def observed(request):
                        connections.append(request)
                        return connect(request)
                    client._connect = observed
                    try:
                        request = review(route, shadow)
                        result = visual.apply(request)['provider_result']['driver_observation']
                        replay_refused(request)
                    finally: client._connect = connect
                    assert not connections, 'Recovery attempted a SQL preflight'
                    assert result['server_completed'] and result['shadow_header_verification']['active_shadow_verified']
                    assert result['reviewed_file_identity']['path'] == str(shadow)
                    assert not result['file_identity_race_fenced'] and not result['network_authentication']
                    assert result['service_release']['connection_released'] and result['service_release']['service_handle_released']
                    assert 'active shadow' not in '\n'.join(header(route, shadow))
                    c = client._connect({'route': {**route, 'database': str(shadow)}})
                    try:
                        q = c.cursor(); q.execute('SELECT ID FROM OWNED'); assert q.fetchall() == [(17,)]; q.close(); c.rollback()
                        q = c.cursor(); q.execute('SELECT MON$DATABASE_NAME FROM MON$DATABASE'); assert q.fetchone() == (str(shadow),); q.close(); c.rollback()
                        c.execute_immediate('ALTER DATABASE BEGIN BACKUP'); c.commit()
                        c.execute_immediate('ALTER DATABASE END BACKUP'); c.commit()
                        c.execute_immediate('ALTER DATABASE SET LINGER TO 0'); c.commit()
                    finally: client._forget_and_close(c)
                    assert digest(archive) == original_hash
                    proof['checks'].append({'case': 'activate-linger-'+str(linger), 'native_active_shadow_header_observed': True,
                        'original_and_parent_absent': True, 'no_sql_preflight': True, 'row17_retained': True,
                        'native_filename_preserved': True, 'isolated_original_unchanged': True})
                route, shadow, archive, original_hash = fixture('not-shadow')
                ordinary = data/'ordinary-copy.fdb'; shutil.copyfile(archive, ordinary)
                ordinary_hash = digest(ordinary)
                request = review(route, ordinary)
                try: visual.apply(request)
                except VisualAdminExecutionError: pass
                else: raise AssertionError('Ordinary primary header accepted as active shadow')
                replay_refused(request)
                assert digest(ordinary) == ordinary_hash and digest(archive) == original_hash
                proof['checks'].append({'case': 'ordinary-header-refusal', 'both_files_unchanged': True})
                route, shadow, archive, original_hash = fixture('replaced-shadow')
                request = review(route, shadow)
                shadow.rename(data/'retained actual shadow.shd'); shutil.copyfile(archive, shadow)
                replacement_hash = digest(shadow)
                try: visual.apply(request)
                except VisualAdminExecutionError as error:
                    assert error.operation['unknown_outcome'] is False, error.operation
                else: raise AssertionError('Replacement inode accepted')
                replay_refused(request)
                assert digest(shadow) == replacement_hash and digest(archive) == original_hash
                proof['checks'].append({'case': 'replacement-before-apply', 'known_pre_dispatch_refusal': True, 'replacement_unchanged': True})
            finally: client.close()
        proof['owned_state_removed'] = not area.exists()
        proof['source_runtime_unchanged'] = _runtime_fingerprint(runtime) == before
        proof['complete'] = len(proof['checks']) == 4 and proof['owned_state_removed'] and proof['source_runtime_unchanged']
    finally: (output/'native.json').write_text(json.dumps(proof, indent=2)+'\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); result = qualify(args.runtime, args.output)
    print(json.dumps({'complete': result['complete'], 'checks': len(result['checks'])}))
    raise SystemExit(0 if result['complete'] else 1)

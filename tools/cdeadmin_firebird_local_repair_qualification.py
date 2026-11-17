"""Qualify owned Engine13 repair and real legacy ODS upgrades."""
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


def qualify(runtime, output, legacy_fixture):
    from tools.cdeadmin_firebird_object_live_orchestrator import _stage_runtime, _runtime_fingerprint
    runtime, output = Path(runtime).resolve(), Path(output).resolve()
    legacy_fixture = Path(legacy_fixture).resolve()
    legacy_hash = hashlib.sha256(legacy_fixture.read_bytes()).hexdigest()
    if sys.platform != 'linux' or output == ROOT or ROOT in output.parents:
        raise ValueError('Use Linux and evidence outside source')
    output.mkdir(parents=True, exist_ok=True)
    proof = {'complete': False, 'checks': [], 'history_tests': 'not run',
             'scope': 'Owned Linux Firebird5.0.4 Engine13 repair; no network/platform/UI acceptance'}
    paths = ['web/pgadmin/cdeadmin/providers/firebird/' + name for name in (
        'local_services.py', 'embedded_provider.py', 'query_client.py', 'provider.py', 'repair.py')]
    paths += ['web/pgadmin/cdeadmin/providers/relational_admin.py',
              'web/pgadmin/cdeadmin/ui_descriptors/firebird/capabilities.json',
              'web/pgadmin/cdeadmin/ui_descriptors/firebird/operations.json',
              'tools/cdeadmin_firebird_legacy_upgrade_fixture.py',
              'tools/cdeadmin_firebird_local_repair_qualification.py']
    proof['source_sha256'] = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}
    before = _runtime_fingerprint(runtime)
    try:
        with tempfile.TemporaryDirectory(prefix='firebird-local-repair-', dir=output) as folder:
            area = Path(folder); stage = area/'runtime'; _stage_runtime(runtime, stage)
            (stage/'firebird.conf').write_text('Providers = Engine13\nSecurityDatabase = ' + str(stage/'security5.fdb') + '\n')
            (stage/'databases.conf').write_text('')
            os.environ.update(FIREBIRD=str(stage), FIREBIRD_LOCK=str(stage/'lock'),
                CDEADMIN_FIREBIRD_CLIENT_LIBRARY=str(stage/'lib/libfbclient.so.5.0.4'))
            import firebird.driver as module
            module.driver_config.fb_client_library.value = str(stage/'lib/libfbclient.so.5.0.4')
            from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
            from pgadmin.cdeadmin.providers.firebird.provider import _create_client, _firebird_service_operation
            from pgadmin.cdeadmin.providers.firebird import repair
            from pgadmin.cdeadmin.visual_admin import ProviderVisualAdministration, VisualAdminAccessError, VisualAdminExecutionError
            permitted = {'embedded_runtime', 'filesystem', 'data_read', 'administer', 'execute', 'maintenance_admin'}
            def require(name, *_):
                if name not in permitted: raise PermissionError(name)
            def secret(*_): raise AssertionError('Recovery acquired a network credential')
            permissions = SimpleNamespace(require=require, allows=lambda name, *_: name in permitted, acquire_secret=secret)
            client = _create_client(permissions, attachment_mode='embedded', profile=embedded.PROFILE, administration=embedded.ADMINISTRATION)
            context = SimpleNamespace(endpoint_id='owned-repair', mode='provider_native', provider_id=embedded.PROFILE.provider_id,
                profile_id=embedded.PROFILE.profile_id, runtime_verification_state='verified', declared_runtime_family='firebird', verified_runtime_family='firebird')
            visual = ProviderVisualAdministration(context, permissions, 'firebird', '5.0.4', client)
            data = area/'data'; data.mkdir()
            def create(name):
                path = data/(name+" 雪's.fdb")
                route = {'attachment_mode': 'embedded', 'database': str(path),
                         'filesystem_root': str(data), 'user': 'SYSDBA', 'charset': 'UTF8'}
                c = client.config.database_creator(**client.config.database_create_arguments(route, str(path), {}))
                try:
                    c.execute_immediate('CREATE TABLE OWNED(ID INTEGER NOT NULL PRIMARY KEY)'); c.commit()
                    c.execute_immediate('INSERT INTO OWNED VALUES(17)'); c.commit()
                    c.execute_immediate('ALTER DATABASE SET LINGER TO 0'); c.commit()
                finally: c.close()
                return route
            def sql(route, source):
                c = client._connect({'route': route})
                try:
                    q = c.cursor(); q.execute(source)
                    rows = q.fetchall() if q.description else None
                    q.close(); c.commit(); return rows
                finally: client._forget_and_close(c)
            def review(route, draft, operation='repair_database'):
                request = {'resource_kind': 'database', 'operation_id': operation,
                           '_provider_route': route, 'draft': draft,
                           'target_resource': {'resource_kind': 'database',
                               'resource_id': 'owned-service-target',
                               'display_name': Path(route['database']).name}}
                validation = visual.validate(request); assert validation['valid'], validation
                plan = visual.plan(request)
                if operation == 'repair_database': assert plan['warnings'], plan
                return {'plan_id': plan['plan_id'], 'plan_digest': plan['plan_digest'], 'confirmed': True}
            def replay_refused(request):
                try: visual.apply(request)
                except VisualAdminAccessError: return
                raise AssertionError('Consumed repair review replayed')
            def apply(route, draft, operation='repair_database'):
                connections = []; connect = client._connect
                def forbidden(request):
                    connections.append(request)
                    raise AssertionError('Repair attempted SQL before its native service action')
                client._connect = forbidden
                try:
                    request = review(route, draft, operation)
                    try: result = visual.apply(request)['provider_result']['driver_observation']
                    finally: replay_refused(request)
                finally: client._connect = connect
                assert not connections
                assert result['server_completed'] and result['native_provider'] == 'Engine13'
                assert result['service_release']['connection_released'] and result['service_release']['service_handle_released']
                assert not result['file_identity_race_fenced'] and not result['network_authentication']
                assert result['database'] == route['database']
                if operation == 'repair_database':
                    assert result['repair_selection_requested']['native_flags'] == repair.flags(draft)
                return result
            try:
                for operation in ('repair_database', 'upgrade_database'):
                    dest = data/(operation+' legacy ODS13.0.fdb')
                    shutil.copyfile(legacy_fixture, dest)
                    route = {'attachment_mode': 'embedded', 'database': str(dest),
                             'filesystem_root': str(data), 'user': 'SYSDBA', 'charset': 'UTF8'}
                    assert sql(route, 'SELECT MON$ODS_MAJOR,MON$ODS_MINOR FROM MON$DATABASE') == [(13, 0)]
                    apply(route, {'repair_action': 'UPGRADE_DB'} if operation == 'repair_database' else {}, operation)
                    assert sql(route, 'SELECT MON$ODS_MAJOR,MON$ODS_MINOR FROM MON$DATABASE') == [(13, 1)]
                    assert sql(route, 'SELECT ID,LABEL FROM UPGRADE_DATA') == [(17, 'preserved across upgrade')]
                    assert sql(route, "SELECT COUNT(*) FROM RDB$RELATION_CONSTRAINTS WHERE RDB$RELATION_NAME='UPGRADE_DATA' AND RDB$CONSTRAINT_TYPE='PRIMARY KEY'") == [(1,)]
                    proof['checks'].append({'case': operation+'-actual-upgrade', 'ods_before': [13,0],
                        'ods_after': [13,1], 'legacy_row_and_metadata_preserved': True,
                        'legacy_fixture_sha256': legacy_hash})
                # Reproduce the catalog-cache blocker independently, then
                # qualify release without touching another user's transaction.
                from threading import RLock
                from pgadmin.cdeadmin.providers.firebird.provider import FirebirdProvider
                dest = data/'pooled legacy upgrade.fdb'; shutil.copyfile(legacy_fixture, dest)
                route = {'attachment_mode': 'embedded', 'database': str(dest),
                         'filesystem_root': str(data), 'user': 'SYSDBA', 'charset': 'UTF8'}
                idle = client._connect({'route': route})
                if idle.main_transaction.is_active(): idle.rollback()
                client._forget_connection(idle)
                owner = object.__new__(FirebirdProvider)
                owner.client = client; owner._catalog_pool_lock = RLock()
                owner._catalog_pool = {json.dumps(route, sort_keys=True): idle}
                try:
                    try: apply(route, {}, 'upgrade_database')
                    except VisualAdminExecutionError as error:
                        assert error.operation['unknown_outcome']
                        assert '335544453' in str(error.operation), error.operation
                    else: raise AssertionError('Native upgrade bypassed a live catalog attachment')
                    other = create('unrelated-pending')
                    pending = client._connect({'route': other})
                    try:
                        pending.execute_immediate('INSERT INTO OWNED VALUES(18)')
                        client._release_idle_catalog = owner._release_idle_catalog_for_service
                        apply(route, {}, 'upgrade_database')
                        assert idle.is_closed() is True and not owner._catalog_pool
                        assert sql(route, 'SELECT MON$ODS_MAJOR,MON$ODS_MINOR FROM MON$DATABASE') == [(13, 1)]
                        assert pending.main_transaction.is_active()
                        q = pending.cursor(); q.execute('SELECT ID FROM OWNED ORDER BY ID')
                        assert q.fetchall() == [(17,), (18,)]; q.close()
                        pending.rollback()
                    finally: client._forget_and_close(pending)
                finally:
                    client._release_idle_catalog = None
                    if idle.is_closed() is not True:
                        client._connections.append(idle); client._forget_and_close(idle)
                proof['checks'].append({'case': 'idle-catalog-upgrade-blocker',
                    'native_busy_error_reproduced_without_release': True,
                    'idle_handle_released_and_actual_upgrade_observed': True,
                    'unrelated_pending_transaction_preserved': True})
                # These are real native service actions on healthy databases.
                # Passing them does not imply recovery of arbitrary corruption.
                for action in ('VALIDATE_DB', 'MEND_DB', 'CORRUPTION_CHECK', 'REPAIR', 'ICU'):
                    route = create(action)
                    draft = {'repair_action': action}
                    if action == 'ICU': draft.update(parallel_workers=2, no_linger=True)
                    result = apply(route, draft)
                    assert sql(route, 'SELECT ID FROM OWNED') == [(17,)]
                    assert sql(route, 'SELECT MON$DATABASE_NAME FROM MON$DATABASE') == [(route['database'],)]
                    assert sql(route, 'SELECT COUNT(*) FROM RDB$INDICES WHERE RDB$INDEX_INACTIVE=0 AND RDB$RELATION_NAME=\'OWNED\'') == [(1,)]
                    proof['checks'].append({'case': action, 'row17_retained': True,
                        'native_flags': result['repair_selection_requested']['native_flags'],
                        'no_sql_preflight': True, 'successful_response_is_not_corruption_recovery_proof': True})
                route = create('missing-manual-shadow')
                shadow = data/'manual shadow.shd'
                sql(route, "CREATE SHADOW 1 MANUAL '"+str(shadow)+"'")
                shadow.rename(data/'isolated manual shadow.shd')
                try: sql(route, 'SELECT ID FROM OWNED')
                except Exception as error: assert '335544460' in str(error), str(error)
                else: raise AssertionError('Missing manual shadow still admitted SQL')
                kill_returned = False
                try:
                    apply(route, {'repair_action': 'KILL_SHADOWS'})
                    kill_returned = True
                except VisualAdminExecutionError as error:
                    # Native cleanup may remove the catalog record yet retain
                    # the original shadow-open error in its service status.
                    assert error.operation['unknown_outcome'], error.operation
                assert sql(route, 'SELECT ID FROM OWNED') == [(17,)]
                assert sql(route, 'SELECT COUNT(*) FROM RDB$FILES WHERE RDB$SHADOW_NUMBER>0') == [(0,)]
                proof['checks'].append({'case': 'KILL_SHADOWS', 'native_missing_shadow_metadata_removed': True,
                                        'sql_reopened_and_row17_retained': True,
                                        'native_returned_success': kill_returned})
                route = create('truncated-disposable-copy')
                original = Path(route['database']); broken = data/'truncated.fdb'
                broken.write_bytes(original.read_bytes()[:128]); original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
                try: apply({**route, 'database': str(broken)}, {'repair_action': 'MEND_DB'})
                except VisualAdminExecutionError as error:
                    assert error.operation['unknown_outcome'], error.operation
                else: raise AssertionError('Truncated database reported successful mend')
                assert hashlib.sha256(original.read_bytes()).hexdigest() == original_hash
                proof['checks'].append({'case': 'truncated-copy', 'native_error_retained': True,
                                        'unknown_outcome_and_no_replay': True, 'original_unchanged': True})
                route = create('stale-target')
                request = review(route, {'repair_action': 'VALIDATE_DB'})
                path = Path(route['database']); path.rename(data/'retained original.fdb')
                path.write_bytes(b'owned replacement')
                try: visual.apply(request)
                except VisualAdminExecutionError as error: assert error.operation['unknown_outcome'] is False
                else: raise AssertionError('Replaced database accepted')
                replay_refused(request); assert path.read_bytes() == b'owned replacement'
                proof['checks'].append({'case': 'replaced-inode', 'known_pre_dispatch_refusal': True})
                route = create('lost-native-response')
                request = review(route, {'repair_action': 'VALIDATE_DB', 'repair_modifiers': ['FULL', 'CHECK_DB']})
                dispatch = client.run_server_operation
                from pgadmin.cdeadmin.sdk import RelationalClientError
                observed = []
                def lose(*args, **kwargs):
                    observed.append(dispatch(*args, **kwargs))
                    raise RelationalClientError('Owned qualification lost the returned native response')
                client.run_server_operation = lose
                try:
                    try: visual.apply(request)
                    except VisualAdminExecutionError as error: assert error.operation['unknown_outcome']
                    else: raise AssertionError('Lost response reported known success')
                finally: client.run_server_operation = dispatch
                replay_refused(request)
                assert len(observed) == 1 and observed[0]['server_completed']
                assert sql(route, 'SELECT ID FROM OWNED') == [(17,)]
                proof['checks'].append({'case': 'lost-native-response', 'unknown_no_replay': True,
                                        'native_completed_independently_observed': True})
            finally: client.close()
        proof['owned_state_removed'] = not area.exists()
        proof['source_runtime_unchanged'] = _runtime_fingerprint(runtime) == before
        proof['legacy_fixture_unchanged'] = hashlib.sha256(legacy_fixture.read_bytes()).hexdigest() == legacy_hash
        proof['complete'] = len(proof['checks']) == 12 and proof['owned_state_removed'] and proof['source_runtime_unchanged'] and proof['legacy_fixture_unchanged']
        proof['not_qualified'] = ['arbitrary corruption recovery',
                                  'other native platforms and versions', 'human UI acceptance']
    finally: (output/'native.json').write_text(json.dumps(proof, indent=2)+'\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--legacy-fixture', type=Path, required=True, help='Owned real ODS13.0 database with UPGRADE_DATA sentinel')
    args = parser.parse_args(); result = qualify(args.runtime, args.output, args.legacy_fixture)
    print(json.dumps({'complete': result['complete'], 'checks': len(result['checks'])}))
    raise SystemExit(0 if result['complete'] else 1)

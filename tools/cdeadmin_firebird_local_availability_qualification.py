"""Qualify embedded availability without a network server or SQL fallback."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def qualify(runtime, output):
    from tools.cdeadmin_firebird_object_live_orchestrator import _stage_runtime, _runtime_fingerprint
    runtime, output = Path(runtime).resolve(), Path(output).resolve()
    if sys.platform != 'linux' or output == ROOT or ROOT in output.parents:
        raise ValueError('Linux qualification with evidence outside source is required')
    output.mkdir(parents=True, exist_ok=True)
    proof = {'complete': False, 'checks': [], 'history_tests': 'not run',
             'scope': 'Owned Engine13-only Firebird5.0.4 availability matrix; not network, HTTP, UI or other-platform acceptance'}
    names = ['web/pgadmin/cdeadmin/providers/firebird/' + name for name in (
        'local_services.py', 'embedded_provider.py', 'query_client.py', 'provider.py',
        'availability.py', 'service_connection.py')]
    names += ['web/pgadmin/cdeadmin/ui_descriptors/firebird/' + name for name in (
        'capabilities.json', 'operations.json')]
    names += ['tools/cdeadmin_firebird_local_availability_qualification.py']
    proof['source_sha256'] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names}
    before = _runtime_fingerprint(runtime)
    try:
        with tempfile.TemporaryDirectory(prefix='firebird-local-availability-', dir=output) as folder:
            area = Path(folder); stage = area / 'runtime'; _stage_runtime(runtime, stage)
            (stage / 'firebird.conf').write_text('Providers = Engine13\nSecurityDatabase = ' + str(stage / 'security5.fdb') + '\n')
            (stage / 'databases.conf').write_text('')
            os.environ.update(FIREBIRD=str(stage), FIREBIRD_LOCK=str(stage / 'lock'),
                CDEADMIN_FIREBIRD_CLIENT_LIBRARY=str(stage / 'lib/libfbclient.so.5.0.4'))
            import firebird.driver as native
            native.driver_config.fb_client_library.value = str(stage / 'lib/libfbclient.so.5.0.4')
            from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
            from pgadmin.cdeadmin.providers.firebird.provider import _create_client
            from pgadmin.cdeadmin.providers.firebird.error_diagnostics import status_codes
            from pgadmin.cdeadmin.visual_admin import ProviderVisualAdministration, VisualAdminAccessError, VisualAdminExecutionError
            from pgadmin.cdeadmin.sdk import RelationalClientError
            permitted = {'embedded_runtime', 'filesystem', 'data_read', 'administer', 'maintenance_admin', 'execute'}
            def require(name, *_):
                if name not in permitted: raise PermissionError(name)
            def secret(*_): raise AssertionError('Embedded availability acquired a network secret')
            permissions = SimpleNamespace(require=require, allows=lambda name, *_: name in permitted, acquire_secret=secret)
            client = _create_client(permissions, attachment_mode='embedded',
                profile=embedded.PROFILE, administration=embedded.ADMINISTRATION)
            context = SimpleNamespace(endpoint_id='owned-local-availability', mode='provider_native',
                profile_id=embedded.PROFILE.profile_id, provider_id=embedded.PROFILE.provider_id,
                runtime_verification_state='verified', declared_runtime_family='firebird', verified_runtime_family='firebird')
            visual = ProviderVisualAdministration(context, permissions, 'firebird', '5.0.4', client)
            data = area / 'data'; data.mkdir()
            route = target = None
            def sql(source):
                c = client._connect({'route': route})
                try:
                    q = c.cursor(); q.execute(source); result = q.fetchall() if q.description else None
                    q.close(); c.commit(); return result
                finally: client._forget_and_close(c)
            def create(name):
                nonlocal route, target
                route = {'attachment_mode': 'embedded', 'database': str(data / (name + ' 雪.fdb')),
                         'filesystem_root': str(data), 'user': 'SYSDBA', 'charset': 'UTF8'}
                c = client.config.database_creator(**client.config.database_create_arguments(route, route['database'], {}))
                try:
                    c.execute_immediate('CREATE TABLE OWNED(ID INTEGER)'); c.commit()
                    c.execute_immediate('INSERT INTO OWNED VALUES(17)'); c.commit()
                finally: c.close()
                target = next(row for row in client.list_resources({'route': route}) if row['resource_kind'] == 'database')
                assert sql("SELECT RDB$GET_CONTEXT('SYSTEM','ENGINE_VERSION'),RDB$GET_CONTEXT('SYSTEM','NETWORK_PROTOCOL') FROM RDB$DATABASE") == [('5.0.4', None)]
            def review(operation, draft):
                if operation == 'shutdown_database': draft = {**draft, 'confirmation': target['display_name']}
                request = {'resource_kind': 'database', 'operation_id': operation,
                    'target_resource': target, 'draft': draft, '_provider_route': route}
                validation = visual.validate(request)
                assert validation['valid'], validation['errors']
                plan = visual.plan(request)
                return {'plan_id': plan['plan_id'], 'plan_digest': plan['plan_digest'], 'confirmed': True}
            def apply(operation, draft):
                request = review(operation, draft)
                result = visual.apply(request)['provider_result']['driver_observation']
                assert result['server_completed'] and result['native_provider'] == 'Engine13'
                assert result['service_release']['connection_released'] and result['service_release']['service_handle_released']
                assert type(result['file_identity_race_fenced']) is bool and not result['network_authentication']
                try: visual.apply(request)
                except VisualAdminAccessError: pass
                else: raise AssertionError('Consumed availability review replayed')
                return result
            def state(): return sql('SELECT MON$SHUTDOWN_MODE FROM MON$DATABASE')[0][0]
            def normal(): apply('bring_online', {'mode': 'NORMAL'})
            try:
                for mode in ('MULTI', 'SINGLE', 'FULL'):
                    for method in ('FORCED', 'DENY_ATTACHMENTS', 'DENY_TRANSACTIONS'):
                        create(mode + '-' + method)
                        assert state() == 0
                        apply('shutdown_database', {'mode': mode, 'method': method, 'shutdown_timeout': 0})
                        observed = None
                        if mode == 'FULL':
                            try: sql('SELECT 1 FROM RDB$DATABASE')
                            except RelationalClientError as error:
                                assert '335544528' in str(error), str(error)
                            else: raise AssertionError('FULL shutdown admitted an ordinary SQL attachment')
                            header = apply('database_statistics', {'statistics_flags': ['HDR_PAGES']})
                            assert any('full shutdown' in line.lower() for line in header['output']), header['output']
                        else:
                            observed = state(); assert observed == {'MULTI': 1, 'SINGLE': 2}[mode]
                        transitions = []
                        for online in {'FULL': ('SINGLE', 'MULTI', 'NORMAL'), 'SINGLE': ('MULTI', 'NORMAL'), 'MULTI': ('NORMAL',)}[mode]:
                            apply('bring_online', {'mode': online})
                            current = state(); assert current == {'SINGLE': 2, 'MULTI': 1, 'NORMAL': 0}[online]
                            transitions.append({'requested': online, 'observed': current})
                        assert sql('SELECT ID FROM OWNED') == [(17,)]
                        proof['checks'].append({'case': mode + '-' + method, 'shutdown_mode': observed,
                            'full_header_and_attach_refusal': mode == 'FULL', 'online_transitions': transitions})
                for method in ('DENY_ATTACHMENTS', 'DENY_TRANSACTIONS', 'FORCED'):
                    create('pending-' + method)
                    held = client.open_session({'route': route})
                    try:
                        held.execute_immediate('INSERT INTO OWNED VALUES(29)')
                        transaction = held.main_transaction.info.id
                        try:
                            apply('shutdown_database', {'mode': 'FULL', 'method': method, 'shutdown_timeout': 0})
                        except VisualAdminExecutionError as error:
                            assert method != 'FORCED' and error.operation['unknown_outcome']
                            assert '335544557' in str(error.operation), error.operation
                            assert held.main_transaction.info.id == transaction
                            assert state() == 0
                            q = held.cursor(); q.execute('SELECT ID FROM OWNED ORDER BY ID'); assert q.fetchall() == [(17,), (29,)]; q.close()
                            held.rollback()
                            outcome = 'pending caller transaction preserved after native denial'
                        else:
                            assert method == 'FORCED'
                            normal(); assert sql('SELECT ID FROM OWNED') == [(17,)]
                            outcome = 'native force ended attachment and pending row is absent'
                        released = client.close_session(held)
                        assert released['connection_released']
                        if method == 'FORCED':
                            assert released['native_attachment_shutdown_observed']
                            assert not released['rollback_completion_confirmed']
                        proof['checks'].append({'case': 'pending-' + method, 'native_outcome': outcome, 'release': released})
                    finally:
                        if held in client._connections: client.close_session(held)
                create('physical-backup')
                sql('ALTER DATABASE BEGIN BACKUP')
                try:
                    try: apply('shutdown_database', {'mode': 'FULL', 'method': 'FORCED', 'shutdown_timeout': 0})
                    except VisualAdminExecutionError as error:
                        assert error.operation['unknown_outcome']
                        assert '335544835' in str(error.operation), error.operation
                    else: raise AssertionError('FULL shutdown admitted a physical-backup database')
                    assert state() == 0 and sql('SELECT MON$BACKUP_STATE FROM MON$DATABASE') == [(1,)]
                finally:
                    # Explicit fixture teardown, never an automatic product
                    # response to the failed shutdown request.
                    sql('ALTER DATABASE END BACKUP')
                proof['checks'].append({'case': 'physical-backup', 'native_refused': True, 'backup_not_implicitly_ended': True})
                create('linger-native-filename')
                sql('ALTER DATABASE SET LINGER TO 1')
                import time
                time.sleep(1.2)
                result = apply('set_sweep_interval', {'sweep_interval': 12345})
                assert not result['file_identity_race_fenced']
                assert sql('SELECT MON$DATABASE_NAME FROM MON$DATABASE') == [(route['database'],)]
                sql('ALTER DATABASE BEGIN BACKUP')
                try:
                    apply('shutdown_database', {'mode': 'MULTI', 'method': 'FORCED', 'shutdown_timeout': 0})
                    assert state() == 1 and sql('SELECT MON$BACKUP_STATE FROM MON$DATABASE') == [(1,)]
                    normal()
                finally:
                    sql('ALTER DATABASE END BACKUP')
                proof['checks'].append({'case': 'linger-and-backup-native-filename',
                    'canonical_cache_name': True, 'multi_shutdown_during_backup': True})
                assert not list(data.glob('.scratchrobin-*'))
            finally:
                client.close()
        proof['owned_state_removed'] = not area.exists()
        proof['source_runtime_unchanged'] = _runtime_fingerprint(runtime) == before
        proof['complete'] = len(proof['checks']) == 14 and proof['owned_state_removed'] and proof['source_runtime_unchanged']
    finally:
        (output / 'native.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); result = qualify(args.runtime, args.output)
    print(json.dumps({'complete': result['complete'], 'checks': len(result['checks'])}))
    raise SystemExit(0 if result['complete'] else 1)

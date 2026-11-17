"""Native qualification of embedded Firebird's local administration adapters.

Uses an isolated Engine13 runtime and disposable databases; never starts a
network listener or writes to the supplied runtime. Evidence is Linux-specific.
"""
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


def qualify(output, runtime):
    from tools.cdeadmin_firebird_object_live_orchestrator import (
        _stage_runtime, _runtime_fingerprint,
    )
    output, runtime = Path(output).resolve(), Path(runtime).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Keep qualification artifacts outside the source')
    output.mkdir(parents=True, exist_ok=True)
    proof = {'complete': False, 'checks': [], 'operations': [],
             'scope': 'Linux Engine13 5.0.4 local client plan/apply; no network or platform/UI acceptance'}
    names = ['web/pgadmin/cdeadmin/providers/firebird/' + name for name in (
        'local_services.py', 'embedded_provider.py', 'query_client.py', 'provider.py')]
    names += ['tools/cdeadmin_firebird_local_administration_qualification.py',
              'web/pgadmin/cdeadmin/visual_admin/provider.py',
              'web/pgadmin/cdeadmin/ui_descriptors/firebird/operations.json',
              'web/pgadmin/cdeadmin/ui_descriptors/firebird/capabilities.json']
    proof['source_sha256'] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                              for name in names}
    before = _runtime_fingerprint(runtime)
    try:
        with tempfile.TemporaryDirectory(prefix='firebird-local-admin-', dir=output) as folder:
            area = Path(folder)
            stage = area / 'runtime'
            _stage_runtime(runtime, stage)
            (stage / 'firebird.conf').write_text(
                'Providers = Engine13\nSecurityDatabase = ' + str(stage / 'security5.fdb') + '\n')
            (stage / 'databases.conf').write_text('')
            os.environ.update(FIREBIRD=str(stage), FIREBIRD_LOCK=str(stage / 'lock'),
                CDEADMIN_FIREBIRD_CLIENT_LIBRARY=str(stage / 'lib/libfbclient.so.5.0.4'))
            import firebird.driver as module
            module.driver_config.fb_client_library.value = str(stage / 'lib/libfbclient.so.5.0.4')
            from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
            from pgadmin.cdeadmin.providers.firebird.provider import _create_client
            from pgadmin.cdeadmin.sdk import RelationalClientError
            from pgadmin.cdeadmin.visual_admin import (
                ProviderVisualAdministration, VisualAdminAccessError,
                VisualAdminExecutionError,
            )
            allowed = {'embedded_runtime', 'filesystem', 'data_read', 'administer',
                       'execute', 'maintenance_admin'}
            requested = []
            def require(name, *_):
                requested.append(name)
                if name not in allowed:
                    raise PermissionError(name)
            def secret(*_):
                raise AssertionError('Network credential acquisition')
            permissions = SimpleNamespace(require=require, acquire_secret=secret,
                                          allows=lambda name, *_: name in allowed)
            client = _create_client(permissions,
                attachment_mode='embedded', profile=embedded.PROFILE,
                administration=embedded.ADMINISTRATION)
            data = area / 'data'
            data.mkdir()
            route = {'attachment_mode': 'embedded', 'database': str(data / 'Owned 雪.fdb'),
                     'filesystem_root': str(data), 'user': 'SYSDBA', 'charset': 'UTF8'}
            context = SimpleNamespace(endpoint_id='owned-local-administration',
                mode='provider_native', profile_id='firebird-embedded',
                provider_id=embedded.PROFILE.provider_id,
                runtime_verification_state='verified', experience_family='firebird',
                declared_runtime_family='firebird', verified_runtime_family='firebird',
                effective_permissions=frozenset(allowed))
            visual = ProviderVisualAdministration(context, permissions, 'firebird', '5.0.4', client)
            target = None
            def attach(selected=route):
                return client._connect({'route': selected})
            def release(c):
                client._forget_and_close(c)
            def query(sql, selected=route):
                c = attach(selected)
                try:
                    q = c.cursor(); q.execute(sql); rows = q.fetchall(); q.close(); c.rollback()
                    return rows
                finally:
                    release(c)
            def info(code):
                c = attach()
                try:
                    return c.info.get_info(code)
                finally:
                    release(c)
            def plan(op, draft):
                request = {'resource_kind': 'database', 'operation_id': op,
                           '_provider_route': route, 'draft': draft}
                validation = client.validate_admin_operation(request)
                assert not validation['errors'], validation
                return client.plan_admin_operation(request)
            def apply(op, draft):
                reviewed = visual.plan({'resource_kind': 'database', 'operation_id': op,
                                       '_provider_route': route, 'draft': draft,
                                       'target_resource': target})
                request = {'plan_id': reviewed['plan_id'], 'plan_digest': reviewed['plan_digest'],
                           'confirmed': True}
                response = visual.apply(request)
                result = response['provider_result']['driver_observation']
                try:
                    visual.apply(request)
                except VisualAdminAccessError:
                    pass
                else:
                    raise AssertionError('A consumed native review was replayed')
                assert result['server_completed'] and result['native_provider'] == 'Engine13', result
                assert not result['network_authentication']
                if op in {'remove_linger', 'sweep_database', 'validate_database'}:
                    assert not result['file_identity_race_fenced']
                else:
                    assert result['file_identity_race_fenced']
                assert result['service_release']['connection_released']
                assert result['service_release']['service_handle_released']
                return result
            try:
                c = client.config.database_creator(**client.config.database_create_arguments(
                    route, route['database'], {}))
                c.execute_immediate('CREATE TABLE OWNED (ID INTEGER)'); c.commit(); c.close()
                assert query("SELECT RDB$GET_CONTEXT('SYSTEM','ENGINE_VERSION'), "
                             "RDB$GET_CONTEXT('SYSTEM','NETWORK_PROTOCOL') FROM RDB$DATABASE") == [('5.0.4', None)]
                target = next(item for item in client.list_resources({'route': route})
                              if item['resource_kind'] == 'database')
                code = module.DbInfoCode
                # Each selection is applied and independently reopened before
                # the next issue. Reverse selections establish real setters.
                selections = [
                    ('set_access_mode', 'mode', [('READ_ONLY', 1), ('READ_WRITE', 0)], code.DB_READ_ONLY),
                    ('set_page_cache_size', 'page_buffers', [(321, 321), (512, 512)], code.SET_PAGE_BUFFERS),
                    ('set_sweep_interval', 'sweep_interval', [(12345, 12345), (20000, 20000)], code.SWEEP_INTERVAL),
                    ('set_space_reservation', 'mode', [('USE_FULL', 1), ('RESERVE', 0)], code.NO_RESERVE),
                    ('set_write_mode', 'mode', [('ASYNC', 0), ('SYNC', 1)], code.FORCED_WRITES),
                    ('set_sql_dialect', 'sql_dialect', [('1', 1), ('3', 3)], code.DB_SQL_DIALECT),
                    ('set_replica_mode', 'mode', [('READ_ONLY', 1), ('READ_WRITE', 2), ('NONE', 0)], code.REPLICA_MODE),
                ]
                for op, field, values, native_code in selections:
                    observations = []
                    for value, expected in values:
                        apply(op, {field: value})
                        actual = info(native_code)
                        assert actual == expected, (op, value, actual, expected)
                        observations.append({'requested': value, 'observed': actual})
                    proof['operations'].append({'operation_id': op, 'observations': observations})
                # no_linger is a runtime cache operation, not a persistent
                # ALTER DATABASE SET LINGER or a promise to release peer locks.
                c = attach()
                try:
                    c.execute_immediate('ALTER DATABASE SET LINGER TO 30'); c.commit()
                finally:
                    release(c)
                apply('remove_linger', {})
                assert query('SELECT RDB$LINGER FROM RDB$DATABASE') == [(30,)]
                proof['operations'].append({'operation_id': 'remove_linger',
                    'native_acknowledged': True, 'persistent_linger_preserved': 30,
                    'runtime_cache_getter_available': False})
                c = attach()
                try:
                    c.execute_immediate('ALTER DATABASE SET LINGER TO 0'); c.commit()
                    c.execute_immediate('INSERT INTO OWNED VALUES (17)')
                    apply('sweep_database', {'parallel_workers': 2})
                    assert query('SELECT COUNT(*) FROM OWNED') == [(0,)]
                    c.rollback()
                finally:
                    release(c)
                proof['operations'].append({'operation_id': 'sweep_database',
                    'parallel_workers': 2, 'caller_transaction_preserved': True})
                result = apply('validate_database', {'include_table': 'OWNED', 'lock_timeout': 0})
                assert result['output'] and not result['output_truncated'], result
                proof['operations'].append({'operation_id': 'validate_database',
                    'output': result['output']})
                # A service attachment through a hardlink must cooperate with
                # the original filename's transaction/locking identity.
                c = attach()
                try:
                    c.execute_immediate('INSERT INTO OWNED VALUES (21)')
                    apply('set_sweep_interval', {'sweep_interval': 23456})
                    assert query('SELECT COUNT(*) FROM OWNED') == [(0,)]
                    assert info(code.SWEEP_INTERVAL) == 23456
                    c.rollback()
                finally:
                    release(c)
                proof['checks'].append('Property service shares original native identity without committing a pending caller transaction')
                # Pin first, then replace the public filename immediately
                # before native action. Observe both actual database files.
                replacement = {**route, 'database': str(data / 'Replacement.fdb')}
                c = client.config.database_creator(**client.config.database_create_arguments(
                    replacement, replacement['database'], {})); c.close()
                replacement_before = query('SELECT MON$SWEEP_INTERVAL FROM MON$DATABASE', replacement)
                reviewed = plan('set_sweep_interval', {'sweep_interval': 34567})
                original = Path(route['database']); retained = data / 'Pinned original.fdb'
                native_path = client._server_operation_database
                swapped = []
                def replace_during_dispatch(database):
                    if not swapped:
                        assert '/.scratchrobin-local-service-' in database
                        original.rename(retained)
                        Path(replacement['database']).rename(original)
                        swapped.append(True)
                    return native_path(database)
                client._server_operation_database = replace_during_dispatch
                try:
                    result = client.apply_admin_operation(reviewed)['driver_observation']
                    assert result['server_completed'] and swapped
                    assert query('SELECT MON$SWEEP_INTERVAL FROM MON$DATABASE') == replacement_before
                    assert query('SELECT MON$SWEEP_INTERVAL FROM MON$DATABASE',
                                 {**route, 'database': str(retained)}) == [(34567,)]
                finally:
                    client._server_operation_database = native_path
                    if swapped:
                        original.unlink(); retained.rename(original)
                proof['checks'].append('In-dispatch filename replacement changes only the pinned original inode')
                # Same filename, different inode must fail before dispatch.
                reviewed = plan('set_sweep_interval', {'sweep_interval': 999})
                original = Path(route['database']); retained = data / 'Retained.fdb'
                original.rename(retained); original.touch()
                try:
                    try:
                        client.apply_admin_operation(reviewed)
                    except RelationalClientError as error:
                        assert error.rejected and error.nothing_changed and not error.native_dispatched
                    else:
                        raise AssertionError('Stale local target admitted')
                finally:
                    original.unlink(); retained.rename(original)
                proof['checks'].append('Same-name inode replacement rejected before native action')
                for field, value in [('host', '127.0.0.1'), ('credential_reference_id', 'other')]:
                    try:
                        client.plan_admin_operation({'resource_kind': 'database',
                            'operation_id': 'remove_linger', 'draft': {},
                            '_provider_route': {**route, field: value}})
                    except RelationalClientError:
                        pass
                    else:
                        raise AssertionError('Nonlocal authority admitted')
                proof['checks'].append('Network host and secret reference rejected')
                # Authorization is rechecked on Apply, after review; denial
                # consumes the review before any actual native action.
                reviewed = visual.plan({'resource_kind': 'database',
                    'operation_id': 'set_sweep_interval', '_provider_route': route,
                    'draft': {'sweep_interval': 56789}, 'target_resource': target})
                request = {'plan_id': reviewed['plan_id'],
                           'plan_digest': reviewed['plan_digest'], 'confirmed': True}
                previous = info(code.SWEEP_INTERVAL)
                allowed.remove('maintenance_admin')
                try:
                    try:
                        visual.apply(request)
                    except PermissionError:
                        pass
                    else:
                        raise AssertionError('Revoked maintenance authority admitted')
                finally:
                    allowed.add('maintenance_admin')
                assert info(code.SWEEP_INTERVAL) == previous
                try:
                    visual.apply(request)
                except VisualAdminAccessError:
                    pass
                else:
                    raise AssertionError('Denied submitted review was reusable')
                proof['checks'].append('Revoked maintenance grant refused before action and submitted review retired')
                # Lose the response after an actual native acknowledgement.
                # The retained review stays consumed and records uncertainty;
                # observing the property later does not authorize replay.
                reviewed = visual.plan({'resource_kind': 'database',
                    'operation_id': 'set_sweep_interval', '_provider_route': route,
                    'draft': {'sweep_interval': 45678}, 'target_resource': target})
                request = {'plan_id': reviewed['plan_id'],
                           'plan_digest': reviewed['plan_digest'], 'confirmed': True}
                execute = client.apply_admin_operation
                def lose_response(value):
                    execute(value)
                    raise RuntimeError('Injected native acknowledgement loss')
                client.apply_admin_operation = lose_response
                try:
                    try:
                        visual.apply(request)
                    except VisualAdminExecutionError as error:
                        record = visual.list_operations()['items'][0]
                        assert record['unknown_outcome'] and not record['automatic_mutation_retry']
                    else:
                        raise AssertionError('Response loss was labeled successful')
                    try:
                        visual.apply(request)
                    except VisualAdminAccessError:
                        pass
                    else:
                        raise AssertionError('Uncertain native mutation replayed')
                finally:
                    client.apply_admin_operation = execute
                assert info(code.SWEEP_INTERVAL) == 45678
                proof['checks'].append('Lost actual native response remains unknown and its one-use review cannot replay')
                assert query('SELECT COUNT(*) FROM OWNED') == [(0,)]
                assert not list(data.glob('.scratchrobin-*'))
                proof['checks'].append('Native aliases removed and original data reopened')
            finally:
                client.close()
        proof['owned_state_removed'] = not area.exists()
        proof['source_runtime_unchanged'] = before == _runtime_fingerprint(runtime)
        proof['permissions_requested'] = sorted(set(requested))
        proof['complete'] = (len(proof['operations']) == 10 and proof['owned_state_removed']
                             and proof['source_runtime_unchanged'])
    finally:
        (output / 'native.json').write_text(json.dumps(proof, indent=2) + '\n')
    if not proof['complete']:
        raise RuntimeError('Local administration qualification incomplete')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    args = parser.parse_args()
    result = qualify(args.output, args.runtime)
    print(json.dumps({'complete': result['complete'], 'operations': len(result['operations'])}))

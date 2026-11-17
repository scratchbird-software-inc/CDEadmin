"""Qualify reviewed target replacement refusal on owned Firebird databases."""
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
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True, exist_ok=True)
    proof = {'complete': False, 'modes': [], 'history_tests': 'not run',
             'scope': 'Firebird5.0.4 network/embedded actual table target replacement; not all catalog operation variants or platform acceptance'}
    files = ['web/pgadmin/cdeadmin/providers/firebird/' + name for name in (
        'metadata_guard.py', 'query_client.py', 'provider.py')]
    files += ['web/pgadmin/cdeadmin/providers/relational_admin.py',
              'web/pgadmin/cdeadmin/sdk/relational.py',
              'tools/cdeadmin_firebird_metadata_guard_qualification.py']
    proof['source_sha256'] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                              for name in files}
    before = _runtime_fingerprint(runtime)
    process = None
    try:
        with tempfile.TemporaryDirectory(prefix='firebird-native-target-', dir=output) as folder:
            area = Path(folder); stage = area / 'runtime'
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
                    module.driver_config.fb_client_library.value = str(stage / 'lib/libfbclient.so.5.0.4')
                    from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
                    from pgadmin.cdeadmin.providers.firebird import provider as network
                    from pgadmin.cdeadmin.providers.firebird import metadata_guard as guard
                    from pgadmin.cdeadmin.sdk import RelationalClientError
                    from pgadmin.cdeadmin.visual_admin import (
                        ProviderVisualAdministration, VisualAdminAccessError, VisualAdminExecutionError,
                    )
                    from tools.mysql_driver_gate_support import provider_access
                    for mode in ('embedded', 'network'):
                        profile = embedded.PROFILE if mode == 'embedded' else network.PROFILE
                        administration = embedded.ADMINISTRATION if mode == 'embedded' else network.ADMINISTRATION
                        path = str(area / (mode + '.fdb'))
                        route = {'database': path, 'user': 'SYSDBA', 'charset': 'UTF8'}
                        if mode == 'embedded':
                            route.update(attachment_mode='embedded', filesystem_root=str(area))
                            permissions = SimpleNamespace(require=lambda *_: None, allows=lambda *_: True,
                                                          acquire_secret=None)
                        else:
                            route.update(host='127.0.0.1', port=port, wire_crypt='Required', trusted_auth=False)
                            route, permissions = provider_access(route, password)
                            permissions.require = lambda *_: None
                            permissions.allows = lambda *_: True
                        client = network._create_client(permissions, attachment_mode=mode,
                            profile=profile, administration=administration)
                        record = {'mode': mode, 'checks': []}
                        def sql(source):
                            c = client._connect({'route': route})
                            try:
                                q = c.cursor(); q.execute(source)
                                rows = q.fetchall() if q.description else None
                                q.close(); c.commit()
                                return rows
                            finally:
                                client._forget_and_close(c)
                        def create_table():
                            sql('CREATE TABLE OWNED (ID INTEGER)')
                            sql('INSERT INTO OWNED VALUES(17)')
                        context = SimpleNamespace(endpoint_id='owned-' + mode,
                            mode='provider_native', runtime_verification_state='verified',
                            profile_id=profile.profile_id, provider_id=profile.provider_id,
                            declared_runtime_family='firebird', verified_runtime_family='firebird')
                        visual = ProviderVisualAdministration(context, permissions, 'firebird', '5.0.4', client)
                        def review():
                            target = next(row for row in client.list_resources({'route': route})
                                          if row['resource_kind'] == 'table' and row['display_name'] == 'OWNED')
                            plan = visual.plan({'resource_kind': 'table', 'operation_id': 'drop',
                                'draft': {'confirmation': 'OWNED'}, 'target_resource': target,
                                '_provider_route': route})
                            assert plan['command_preview']['native_target_revalidation_required']
                            return {'plan_id': plan['plan_id'], 'plan_digest': plan['plan_digest'], 'confirmed': True}
                        try:
                            arguments = client.config.database_create_arguments(route, path, {})
                            if mode == 'network':
                                arguments['password'] = password
                            c = client.config.database_creator(**arguments); c.close()
                            create_table()
                            expected_protocol = None if mode == 'embedded' else 'TCPv4'
                            identity = sql("SELECT RDB$GET_CONTEXT('SYSTEM','ENGINE_VERSION'),RDB$GET_CONTEXT('SYSTEM','NETWORK_PROTOCOL') FROM RDB$DATABASE")
                            assert identity[0][0] == '5.0.4' and identity[0][1] == expected_protocol, identity
                            request = review()
                            original = sql("SELECT RDB$RELATION_ID FROM RDB$RELATIONS WHERE RDB$RELATION_NAME='OWNED'")[0][0]
                            sql('DROP TABLE OWNED'); create_table()
                            replacement = sql("SELECT RDB$RELATION_ID FROM RDB$RELATIONS WHERE RDB$RELATION_NAME='OWNED'")[0][0]
                            assert original != replacement
                            try:
                                visual.apply(request)
                            except VisualAdminExecutionError as error:
                                assert error.operation['stage'] == 'provider_rejected'
                                assert not error.operation['unknown_outcome']
                                assert 'changed since review' in error.operation['rejection']['message']
                            else:
                                raise AssertionError('Stale table replacement was mutated')
                            assert sql('SELECT ID FROM OWNED') == [(17,)]
                            try:
                                visual.apply(request)
                            except VisualAdminAccessError:
                                pass
                            else:
                                raise AssertionError('Stale review replayed')
                            record['checks'].append('Same-name replacement rejected, replacement data preserved, review retired')
                            # Move the replacement after the preflight read but
                            # before native DDL, exercising the actual engine's
                            # concurrent metadata-update conflict.
                            request = review(); verify = guard.verify; raced = []
                            def replace_after_check(connection, expected):
                                verify(connection, expected)
                                if not raced:
                                    raced.append(True); sql('DROP TABLE OWNED'); create_table()
                            guard.verify = replace_after_check
                            try:
                                try:
                                    visual.apply(request)
                                except VisualAdminExecutionError as error:
                                    assert error.operation['unknown_outcome']
                                else:
                                    raise AssertionError('Raced target replacement was accepted')
                            finally:
                                guard.verify = verify
                            assert raced and sql('SELECT ID FROM OWNED') == [(17,)]
                            record['checks'].append('Replacement after preflight survives native snapshot conflict; response stays conservative')
                            # Ordinary unchanged target still executes exactly
                            # once through the native administration pipeline.
                            response = visual.apply(review())
                            assert response['provider_result']['commit_requested']
                            assert sql("SELECT COUNT(*) FROM RDB$RELATIONS WHERE RDB$RELATION_NAME='OWNED'") == [(0,)]
                            record['checks'].append('Fresh valid native DROP commits and rereads absent')
                            # Exercise every admitted catalog selector against
                            # real native metadata, including a packaged routine
                            # and a column whose parent has its own identity.
                            create_table()
                            declarations = [
                                "CREATE SHADOW 1 MANUAL '" + str(area / (mode + '-shadow.fdb')).replace("'", "''") + "'",
                                'CREATE VIEW OWNER_VIEW AS SELECT ID FROM OWNED',
                                'CREATE DOMAIN OWNER_DOMAIN AS INTEGER',
                                'CREATE SEQUENCE OWNER_SEQ',
                                'CREATE INDEX OWNER_IDX ON OWNED(ID)',
                                'ALTER TABLE OWNED ADD CONSTRAINT OWNER_CON UNIQUE(ID)',
                                'CREATE TRIGGER OWNER_TRG FOR OWNED BEFORE INSERT AS BEGIN END',
                                'CREATE PROCEDURE OWNER_PROC AS BEGIN END',
                                'CREATE FUNCTION OWNER_FN RETURNS INTEGER AS BEGIN RETURN 1; END',
                                'CREATE PACKAGE OWNER_PKG AS BEGIN PROCEDURE P; FUNCTION F RETURNS INTEGER; END',
                                "CREATE EXCEPTION OWNER_EXC 'owned native identity'",
                                'CREATE ROLE OWNER_ROLE',
                                'CREATE COLLATION OWNER_COLL FOR UTF8 FROM UNICODE',
                                "DECLARE EXTERNAL FUNCTION OWNER_UDF INTEGER RETURNS INTEGER BY VALUE ENTRY_POINT 'abs' MODULE_NAME 'ib_udf'",
                                "DECLARE FILTER OWNER_FILTER INPUT_TYPE 101 OUTPUT_TYPE 102 ENTRY_POINT 'unused' MODULE_NAME 'ib_udf'",
                                "CREATE MAPPING OWNER_MAP USING PLUGIN Srp FROM USER 'owned_guard' TO USER SYSDBA",
                            ]
                            for declaration in declarations:
                                sql(declaration)
                            targets = {
                                'database': [path], 'table': ['OWNED'], 'view': ['OWNER_VIEW'],
                                'shadow': ['1'],
                                'index': ['OWNED', 'OWNER_IDX'], 'constraint': ['OWNED', 'OWNER_CON'],
                                'sequence': ['OWNER_SEQ'], 'domain': ['OWNER_DOMAIN'],
                                'trigger': ['OWNED', 'OWNER_TRG'], 'procedure': ['OWNER_PROC'],
                                'function': ['OWNER_FN'], 'external-function': ['OWNER_UDF'],
                                'package': ['OWNER_PKG'], 'exception': ['OWNER_EXC'],
                                'role': ['OWNER_ROLE'], 'collation': ['OWNER_COLL'],
                                'character-set': ['UTF8'], 'blob-filter': ['OWNER_FILTER'],
                                'authentication-mapping': ['OWNER_MAP'], 'column': ['OWNED', 'ID'],
                                'publication': ['RDB$DEFAULT'],
                            }
                            assert set(targets) == set(guard.CATALOGS)
                            record['native_catalog_selectors'] = []
                            for kind, target_path in targets.items():
                                c = client._connect({'route': route})
                                try:
                                    selected = {'resource_kind': kind, 'path': target_path}
                                    observed = guard.observe(c, selected)
                                    guard.verify(c, observed)
                                    assert observed['record']
                                    record['native_catalog_selectors'].append(kind)
                                finally:
                                    client._forget_and_close(c)
                            c = client._connect({'route': route})
                            try:
                                for kind, target_path in [('procedure', ['OWNER_PKG', 'P']),
                                                          ('function', ['OWNER_PKG', 'F'])]:
                                    observed = guard.observe(c, {'resource_kind': kind, 'path': target_path})
                                    assert observed['parent']
                                    guard.verify(c, observed)
                            finally:
                                client._forget_and_close(c)
                            record['checks'].append('All21 native catalog selectors and both packaged routine parent identities observed and revalidated')
                            resources = client.list_resources({'route': route})
                            view = next(row for row in resources if row['resource_kind'] == 'view' and row['display_name'] == 'OWNER_VIEW')
                            reviewed = client.plan_admin_operation({'resource_kind': 'view',
                                'operation_id': 'drop', 'target_resource': view,
                                'draft': {'confirmation': 'OWNER_VIEW'}, '_provider_route': route})
                            c = client._connect({'route': route})
                            try:
                                c.execute_immediate('INSERT INTO OWNED VALUES(29)')
                                applied = client.apply_admin_operation({**reviewed, '_provider_session_handle': c})
                                assert not applied['commit_requested'] and c.main_transaction.is_active()
                                assert sql('SELECT COUNT(*) FROM OWNED') == [(1,)]
                                c.rollback()
                            finally:
                                client._forget_and_close(c)
                            assert sql('SELECT ID FROM OWNER_VIEW') == [(17,)]
                            record['checks'].append('Borrowed SNAPSHOT DDL preserves pending caller DML and caller rollback restores view')
                            sql('CREATE TABLE GRANT_TARGET(ID INTEGER)')
                            def grant_review():
                                target = next(row for row in client.list_resources({'route': route})
                                              if row['resource_kind'] == 'table' and row['display_name'] == 'GRANT_TARGET')
                                planned = visual.plan({'resource_kind': 'table', 'operation_id': 'grant',
                                    'target_resource': target, '_provider_route': route,
                                    'draft': {'principal_kind': 'ROLE', 'principal': 'OWNER_ROLE', 'privileges': ['SELECT']}})
                                return {'plan_id': planned['plan_id'], 'plan_digest': planned['plan_digest'], 'confirmed': True}
                            request = grant_review(); verify = guard.verify; raced = []
                            def replace_grant_target(connection, expected):
                                verify(connection, expected)
                                if not raced:
                                    raced.append(True); sql('DROP TABLE GRANT_TARGET'); sql('CREATE TABLE GRANT_TARGET(ID INTEGER)')
                            guard.verify = replace_grant_target
                            try:
                                try:
                                    visual.apply(request)
                                except VisualAdminExecutionError as error:
                                    assert error.operation['unknown_outcome']
                                else:
                                    raise AssertionError('Grant unexpectedly committed after its target was replaced')
                            finally:
                                guard.verify = verify
                            read_grant = ("SELECT COUNT(*) FROM RDB$USER_PRIVILEGES WHERE RDB$USER='OWNER_ROLE' "
                                          "AND RDB$RELATION_NAME='GRANT_TARGET' AND RDB$PRIVILEGE='S'")
                            assert raced and sql(read_grant) == [(0,)]
                            assert visual.apply(grant_review())['provider_result']['commit_requested']
                            assert sql(read_grant) == [(1,)]
                            record['checks'].append('Raced native table grant is refused without granting replacement; fresh reviewed grant commits')
                            secondary = {**route, 'database': str(area / (mode + '-disposable.fdb'))}
                            for name in ('disposable', 'replacement'):
                                selected = {**secondary, 'database': str(area / (mode + '-' + name + '.fdb'))}
                                arguments = client.config.database_create_arguments(selected, selected['database'], {})
                                if mode == 'network': arguments['password'] = password
                                c = client.config.database_creator(**arguments); c.close()
                            def database_review():
                                target = next(row for row in client.list_resources({'route': secondary})
                                              if row['resource_kind'] == 'database')
                                return client.plan_admin_operation({'resource_kind': 'database', 'operation_id': 'drop',
                                    'target_resource': target, 'draft': {'confirmation': secondary['database']},
                                    '_provider_route': secondary})
                            reviewed = database_review()
                            original = Path(secondary['database']); retained = original.with_suffix('.retained')
                            original.rename(retained)
                            (area / (mode + '-replacement.fdb')).rename(original)
                            try:
                                client.apply_admin_operation(reviewed)
                            except RelationalClientError as error:
                                assert error.rejected and not error.native_dispatched
                            else:
                                raise AssertionError('Replacement database was dropped')
                            assert original.is_file() and retained.is_file()
                            applied = client.apply_admin_operation(database_review())
                            assert applied['driver_observation']['driver_returned'] and not original.exists()
                            record['checks'].append('Native database-drop API rejects replaced database and still drops a fresh reviewed target')
                            proof['modes'].append(record)
                        finally:
                            client.close()
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait(timeout=10)
            password = ''
        proof['owned_state_removed'] = not area.exists()
        proof['server_stopped'] = process.returncode is not None
        proof['source_runtime_unchanged'] = _runtime_fingerprint(runtime) == before
        proof['complete'] = len(proof['modes']) == 2 and all(proof[key] for key in (
            'owned_state_removed', 'server_stopped', 'source_runtime_unchanged'))
    finally:
        (output / 'native.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = qualify(args.runtime, args.output)
    print(json.dumps({'complete': result['complete'], 'modes': len(result['modes'])}))
    raise SystemExit(0 if result['complete'] else 1)

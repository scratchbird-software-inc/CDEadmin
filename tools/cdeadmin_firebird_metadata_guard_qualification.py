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
             'scope': (
                 'Firebird 5.0.4 network and embedded native target-identity '
                 'revalidation across all 21 RDB$ catalogs, packaged routines, '
                 'package body replacement, inspected/object privileges, '
                 'SEC$USERS/SEC$USER_ATTRIBUTES, SEC$GLOBAL_AUTH_MAPPING, '
                 'database drop and authenticated HTTP pre-dispatch conflict/no-replay'
             )}
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
                'ServerMode = SuperClassic\nProviders = Remote,Engine13\nSecurityDatabase = '
                + str(stage / 'security5.fdb') + '\n')
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

                            # Package body replacement/drop guard via RDB$PACKAGES record version.
                            sql('CREATE PACKAGE BODY OWNER_PKG AS BEGIN PROCEDURE P AS BEGIN END FUNCTION F RETURNS INTEGER AS BEGIN RETURN 1; END END')
                            pkg_target = next(
                                row for row in client.list_resources({'route': route})
                                if row['resource_kind'] == 'package' and row['display_name'] == 'OWNER_PKG'
                            )
                            pkg_plan = visual.plan({
                                'resource_kind': 'package',
                                'operation_id': 'drop_body',
                                'target_resource': pkg_target,
                                'draft': {'confirmation': 'OWNER_PKG'},
                                '_provider_route': route,
                            })
                            sql('RECREATE PACKAGE BODY OWNER_PKG AS BEGIN PROCEDURE P AS BEGIN END FUNCTION F RETURNS INTEGER AS BEGIN RETURN 2; END END')
                            try:
                                visual.apply({'plan_id': pkg_plan['plan_id'], 'plan_digest': pkg_plan['plan_digest'], 'confirmed': True})
                            except VisualAdminExecutionError as error:
                                assert error.operation['stage'] == 'provider_rejected' and not error.operation['unknown_outcome']
                            else:
                                raise AssertionError('Stale package drop_body dropped a replaced package body')
                            assert sql('SELECT OWNER_PKG.F() FROM RDB$DATABASE') == [(2,)]
                            record['checks'].append('Stale package drop_body rejected after independent body replacement; replacement body preserved')

                            # Inspected privilege row and collection object-privilege target guard.
                            priv_target = next(
                                row for row in client.list_resources({'route': route})
                                if row['resource_kind'] == 'privilege'
                                and row.get('native', {}).get('grantee') == 'OWNER_ROLE'
                                and row.get('native', {}).get('object_name') == 'GRANT_TARGET'
                            )
                            priv_plan = visual.plan({
                                'resource_kind': 'privilege',
                                'operation_id': 'revoke',
                                'target_resource': priv_target,
                                'draft': {
                                    'privilege_scope': 'object',
                                    'principal_kind': 'ROLE',
                                    'principal': 'OWNER_ROLE',
                                    'object_type': 'TABLE',
                                    'object_name': 'GRANT_TARGET',
                                    'privileges': ['SELECT'],
                                    'confirmation': 'OWNER_ROLE',
                                },
                                '_provider_route': route,
                            })
                            assert priv_plan['command_preview']['native_target_revalidation_required']
                            sql('REVOKE SELECT ON TABLE GRANT_TARGET FROM ROLE OWNER_ROLE')
                            sql('GRANT SELECT ON TABLE GRANT_TARGET TO ROLE OWNER_ROLE WITH GRANT OPTION')
                            try:
                                visual.apply({'plan_id': priv_plan['plan_id'], 'plan_digest': priv_plan['plan_digest'], 'confirmed': True})
                            except VisualAdminExecutionError as error:
                                assert error.operation['stage'] == 'provider_rejected' and not error.operation['unknown_outcome']
                            else:
                                raise AssertionError('Stale privilege revoke mutated replaced grant row')
                            assert sql("SELECT RDB$GRANT_OPTION FROM RDB$USER_PRIVILEGES WHERE RDB$USER='OWNER_ROLE' AND RDB$RELATION_NAME='GRANT_TARGET' AND RDB$PRIVILEGE='S'") == [(1,)]

                            coll_priv_plan = visual.plan({
                                'resource_kind': 'privilege',
                                'operation_id': 'grant',
                                'draft': {
                                    'privilege_scope': 'object',
                                    'principal_kind': 'ROLE',
                                    'principal': 'OWNER_ROLE',
                                    'object_type': 'TABLE',
                                    'object_name': 'GRANT_TARGET',
                                    'privileges': ['INSERT'],
                                },
                                '_provider_route': route,
                            })
                            assert coll_priv_plan['command_preview']['native_target_revalidation_required']
                            sql('DROP TABLE GRANT_TARGET')
                            sql('CREATE TABLE GRANT_TARGET(ID INTEGER)')
                            try:
                                visual.apply({'plan_id': coll_priv_plan['plan_id'], 'plan_digest': coll_priv_plan['plan_digest'], 'confirmed': True})
                            except VisualAdminExecutionError as error:
                                assert error.operation['stage'] == 'provider_rejected' and not error.operation['unknown_outcome']
                            else:
                                raise AssertionError('Collection privilege grant applied to replacement table')
                            assert sql("SELECT COUNT(*) FROM RDB$USER_PRIVILEGES WHERE RDB$USER='OWNER_ROLE' AND RDB$RELATION_NAME='GRANT_TARGET'") == [(0,)]
                            record['checks'].append('Inspected privilege row and collection object-privilege grant reject replaced targets pre-dispatch')

                            # SEC$USERS + SEC$USER_ATTRIBUTES and SEC$GLOBAL_AUTH_MAPPING target guard.
                            uname = 'GUARD_USR_' + mode.upper()
                            gmap_name = 'GUARD_GMAP_' + mode.upper()
                            user_pw = secrets.token_urlsafe(18)
                            sql(f"CREATE OR ALTER USER {uname} PASSWORD '{user_pw}' FIRSTNAME 'Initial' TAGS (team = 'alpha') USING PLUGIN Srp")
                            try:
                                user_target = next(
                                    row for row in client.list_resources({'route': route})
                                    if row['resource_kind'] == 'user' and row['display_name'] == uname
                                )
                                user_plan = visual.plan({
                                    'resource_kind': 'user',
                                    'operation_id': 'recreate',
                                    'target_resource': user_target,
                                    'draft': {
                                        'confirmation': uname,
                                        'password': secrets.token_urlsafe(18),
                                        'first_name': 'Overwritten',
                                    },
                                    '_provider_route': route,
                                })
                                assert user_plan['command_preview']['native_target_revalidation_required']
                                raw_plan = client.plan_admin_operation({
                                    'resource_kind': 'user',
                                    'operation_id': 'recreate',
                                    'target_resource': user_target,
                                    'draft': {
                                        'confirmation': uname,
                                        'password': secrets.token_urlsafe(18),
                                        'first_name': 'Overwritten',
                                    },
                                    '_provider_route': route,
                                })
                                assert 'Initial' not in json.dumps(raw_plan['provider_payload']['firebird_target_binding'])
                                assert 'alpha' not in json.dumps(raw_plan['provider_payload']['firebird_target_binding'])
                                sql(f"ALTER USER {uname} FIRSTNAME 'ExternallyUpdated' USING PLUGIN Srp")
                                try:
                                    visual.apply({'plan_id': user_plan['plan_id'], 'plan_digest': user_plan['plan_digest'], 'confirmed': True})
                                except VisualAdminExecutionError as error:
                                    assert error.operation['stage'] == 'provider_rejected' and not error.operation['unknown_outcome']
                                else:
                                    raise AssertionError('Stale user recreate overwrote externally modified user')
                                assert sql(f"SELECT TRIM(TRAILING FROM SEC$FIRST_NAME) FROM SEC$USERS WHERE TRIM(TRAILING FROM SEC$USER_NAME)='{uname}'") == [('ExternallyUpdated',)]
                            finally:
                                sql(f'DROP USER {uname} USING PLUGIN Srp')

                            sql(f"CREATE OR ALTER GLOBAL MAPPING {gmap_name} USING PLUGIN Srp FROM USER 'ext_alice' TO USER SYSDBA")
                            try:
                                gmap_target = next(
                                    row for row in client.list_resources({'route': route})
                                    if row['resource_kind'] == 'global-authentication-mapping' and row['display_name'] == gmap_name
                                )
                                gmap_plan = visual.plan({
                                    'resource_kind': 'global-authentication-mapping',
                                    'operation_id': 'drop',
                                    'target_resource': gmap_target,
                                    'draft': {'confirmation': gmap_name},
                                    '_provider_route': route,
                                })
                                assert gmap_plan['command_preview']['native_target_revalidation_required']
                                sql(f"ALTER GLOBAL MAPPING {gmap_name} USING PLUGIN Srp FROM USER 'ext_bob' TO USER SYSDBA")
                                try:
                                    visual.apply({'plan_id': gmap_plan['plan_id'], 'plan_digest': gmap_plan['plan_digest'], 'confirmed': True})
                                except VisualAdminExecutionError as error:
                                    assert error.operation['stage'] == 'provider_rejected' and not error.operation['unknown_outcome']
                                else:
                                    raise AssertionError('Stale global mapping drop deleted externally modified global mapping')
                                assert sql(f"SELECT TRIM(TRAILING FROM SEC$MAP_FROM) FROM SEC$GLOBAL_AUTH_MAPPING WHERE TRIM(TRAILING FROM SEC$MAP_NAME)='{gmap_name}'") == [('ext_bob',)]
                                fresh_gmap = next(
                                    row for row in client.list_resources({'route': route})
                                    if row['resource_kind'] == 'global-authentication-mapping' and row['display_name'] == gmap_name
                                )
                                fresh_drop = visual.plan({
                                    'resource_kind': 'global-authentication-mapping',
                                    'operation_id': 'drop',
                                    'target_resource': fresh_gmap,
                                    'draft': {'confirmation': gmap_name},
                                    '_provider_route': route,
                                })
                                assert visual.apply({'plan_id': fresh_drop['plan_id'], 'plan_digest': fresh_drop['plan_digest'], 'confirmed': True})['provider_result']['commit_requested']
                                assert sql(f"SELECT COUNT(*) FROM SEC$GLOBAL_AUTH_MAPPING WHERE TRIM(TRAILING FROM SEC$MAP_NAME)='{gmap_name}'") == [(0,)]
                            finally:
                                if sql(f"SELECT COUNT(*) FROM SEC$GLOBAL_AUTH_MAPPING WHERE TRIM(TRAILING FROM SEC$MAP_NAME)='{gmap_name}'") != [(0,)]:
                                    sql(f'DROP GLOBAL MAPPING {gmap_name}')
                            record['checks'].append('SEC$USERS/SEC$USER_ATTRIBUTES and SEC$GLOBAL_AUTH_MAPPING reject modified targets pre-dispatch without storing PII')
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


def qualify_http(runtime, output):
    import builtins
    import uuid
    from contextlib import ExitStack
    builtins.SERVER_MODE = None
    import pgadmin  # noqa: F401
    from tools.cdeadmin_firebird_object_live_orchestrator import _stage_runtime, _runtime_fingerprint
    runtime, output = Path(runtime).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    before = _runtime_fingerprint(runtime)
    proof = {
        'complete': False,
        'scope': 'Authenticated desktop HTTP Firebird 5.0.4 metadata_guard 409 conflict, no-replay and valid apply',
        'checks': [],
        'history_tests': 'not run',
    }
    try:
        with tempfile.TemporaryDirectory(prefix='firebird-guard-http-', dir=output) as folder, ExitStack() as stack:
            root = Path(folder)
            stage = root / 'runtime'
            _stage_runtime(runtime, stage)
            (stage / 'firebird.conf').write_text(
                'ServerMode = SuperClassic\nProviders = Engine13\nSecurityDatabase = '
                + str(stage / 'security5.fdb') + '\n'
            )
            (stage / 'databases.conf').write_text('')
            os.environ.update(
                FIREBIRD=str(stage),
                FIREBIRD_LOCK=str(stage / 'lock'),
                CDEADMIN_FIREBIRD_CLIENT_LIBRARY=str(stage / 'lib/libfbclient.so.5.0.4'),
            )
            import firebird.driver as module
            module.driver_config.fb_client_library.value = str(stage / 'lib/libfbclient.so.5.0.4')
            from tools.cdeadmin_mysql_dump_verification_qualification import setup_application
            app = setup_application(root)

            def close_app():
                from pgadmin.cdeadmin.workspace.service import service_for_app
                with app.app_context():
                    service_for_app(app).endpoint_service.provider_registry.close()
            stack.callback(close_app)

            from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
            from pgadmin.cdeadmin.providers.firebird.provider import _create_client
            from pgadmin.cdeadmin.endpoints.profiles import registration_profile
            from pgadmin.model import db, User, ServerGroup, Server, EndpointDatabaseTarget
            from flask import url_for

            data = root / 'data'
            data.mkdir()
            db_path = data / 'http_guard.fdb'
            route = {
                'attachment_mode': 'embedded',
                'database': str(db_path),
                'filesystem_root': str(data),
                'user': 'SYSDBA',
                'charset': 'UTF8',
            }
            native_client = _create_client(
                SimpleNamespace(require=lambda *_: None, acquire_secret=None),
                attachment_mode='embedded',
                profile=embedded.PROFILE,
                administration=embedded.ADMINISTRATION,
            )
            created = native_client.config.database_creator(
                **native_client.config.database_create_arguments(route, str(db_path), {})
            )
            try:
                created.execute_immediate('CREATE TABLE HTTP_OWNED (ID INTEGER)')
                created.commit()
                created.execute_immediate('INSERT INTO HTTP_OWNED VALUES (41)')
                created.commit()
            finally:
                created.close()
                native_client.close()

            with app.test_request_context('/'):
                user = User.query.first()
                uid = user.id
                group = ServerGroup.query.filter_by(user_id=uid).first()
                for name, pref in app.blueprints['NODE-engine_type'].connector_visibility.items():
                    if 'firebird' in name:
                        pref.set(True, user_id=uid)
                server = Server(
                    user_id=uid, servergroup_id=group.id, name='HTTP Guard Local',
                    host=None, port=1, username='SYSDBA', maintenance_db=str(db_path), save_password=0,
                )
                server._cde_endpoint_registration = registration_profile('firebird-embedded')
                server._cde_endpoint_route_configuration = route
                db.session.add(server)
                db.session.commit()
                tid = str(uuid.uuid4())
                db.session.add(EndpointDatabaseTarget(
                    id=tid, endpoint_id=server.endpoint_profile.id,
                    display_name=db_path.name, database=str(db_path), configuration='{}', active=1,
                ))
                other = User(username='foreign_owner', email='foreign@example.invalid',
                             password='x', active=True, fs_uniquifier=uuid.uuid4().hex, auth_source='internal')
                db.session.add(other)
                db.session.flush()
                other_group = ServerGroup(user_id=other.id, name='Foreign')
                db.session.add(other_group)
                db.session.flush()
                foreign_server = Server(
                    user_id=other.id, servergroup_id=other_group.id, name='Foreign Server',
                    host=None, port=1, username='SYSDBA', maintenance_db=str(db_path), save_password=0,
                )
                db.session.add(foreign_server)
                db.session.commit()
                url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=server.id)
                foreign_url = url_for('NODE-server.cde_workspace_id', gid=other_group.id, sid=foreign_server.id)
                verify_url = url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=server.id)

            http = app.test_client()
            with http.session_transaction() as sess:
                sess['_user_id'] = str(uid)
                sess['_fresh'] = True
            assert http.post(verify_url, json={}).get_json()['success']

            # Foreign endpoint denial
            denied_resp = http.post(foreign_url, json={'action': 'resource_refresh', 'database_target_id': tid, 'request': {'database_target_id': tid}})
            assert denied_resp.status_code in (401, 403, 404, 410) or not (denied_resp.get_json() or {}).get('success')
            proof['checks'].append('Cross-owner server access denied over HTTP')

            def fetch_table_target():
                initial = http.get(url, query_string={'database_target_id': tid}).get_json()
                assert initial['success'], initial
                gen = initial['data']['resource_page']['generation']
                resp = http.post(url, json={
                    'action': 'resource_refresh',
                    'database_target_id': tid,
                    'request': {'database_target_id': tid, 'generation': gen},
                })
                body = resp.get_json()
                assert resp.status_code == 200 and body['success'], body
                items = body['data']['items']
                return next(row for row in items if row['resource_kind'] == 'table' and row['display_name'] == 'HTTP_OWNED')

            target = fetch_table_target()
            plan_resp = http.post(url, json={
                'action': 'visual_admin_plan',
                'database_target_id': tid,
                'request': {
                    'database_target_id': tid,
                    'resource_kind': 'table',
                    'operation_id': 'drop',
                    'target_resource': target,
                    'draft': {'confirmation': 'HTTP_OWNED'},
                },
            })
            plan_body = plan_resp.get_json()
            assert plan_resp.status_code == 200 and plan_body['success'], plan_body
            plan = plan_body['data']
            assert plan['command_preview']['native_target_revalidation_required'] is True

            ext = _create_client(
                SimpleNamespace(require=lambda *_: None, acquire_secret=None),
                attachment_mode='embedded',
                profile=embedded.PROFILE,
                administration=embedded.ADMINISTRATION,
            )
            conn = ext._connect({'route': route})
            try:
                q = conn.cursor()
                q.execute("SELECT RDB$RELATION_ID FROM RDB$RELATIONS WHERE RDB$RELATION_NAME='HTTP_OWNED'")
                orig_rel_id = q.fetchone()[0]
                q.close()
                conn.execute_immediate('DROP TABLE HTTP_OWNED')
                conn.commit()
                conn.execute_immediate('CREATE TABLE HTTP_OWNED (ID INTEGER)')
                conn.commit()
                conn.execute_immediate('INSERT INTO HTTP_OWNED VALUES (99)')
                conn.commit()
                q = conn.cursor()
                q.execute("SELECT RDB$RELATION_ID FROM RDB$RELATIONS WHERE RDB$RELATION_NAME='HTTP_OWNED'")
                repl_rel_id = q.fetchone()[0]
                q.close()
                conn.rollback()
                assert orig_rel_id != repl_rel_id
            finally:
                ext._forget_and_close(conn)
                ext.close()

            apply_resp = http.post(url, json={
                'action': 'visual_admin_apply',
                'database_target_id': tid,
                'request': {
                    'database_target_id': tid,
                    'plan_id': plan['plan_id'],
                    'plan_digest': plan['plan_digest'],
                    'confirmed': True,
                },
            })
            apply_body = apply_resp.get_json()
            assert apply_resp.status_code == 409 and not apply_body.get('success'), (apply_resp.status_code, apply_body)
            assert apply_body['info'] == 'PROVIDER_OPERATION_REJECTED'
            receipt = apply_body['data']['control_operation']
            assert receipt['stage'] == 'provider_rejected' and receipt['unknown_outcome'] is False
            assert receipt['automatic_mutation_retry'] is False
            proof['checks'].append('HTTP visual_admin_apply returns 409 PROVIDER_OPERATION_REJECTED on replaced table and preserves replacement')

            # Replay of retired plan is refused before dispatch
            replay_resp = http.post(url, json={
                'action': 'visual_admin_apply',
                'database_target_id': tid,
                'request': {
                    'database_target_id': tid,
                    'plan_id': plan['plan_id'],
                    'plan_digest': plan['plan_digest'],
                    'confirmed': True,
                },
            })
            replay_body = replay_resp.get_json()
            assert replay_resp.status_code in (400, 409) and not replay_body.get('success')
            assert replay_body['data']['refusal']['native_dispatched'] is False
            proof['checks'].append('Retired plan replay refused over HTTP with native_dispatched=False')

            # Fresh plan against replacement succeeds and drops table
            fresh_target = fetch_table_target()
            fresh_plan = http.post(url, json={
                'action': 'visual_admin_plan',
                'database_target_id': tid,
                'request': {
                    'database_target_id': tid,
                    'resource_kind': 'table',
                    'operation_id': 'drop',
                    'target_resource': fresh_target,
                    'draft': {'confirmation': 'HTTP_OWNED'},
                },
            }).get_json()['data']
            fresh_apply = http.post(url, json={
                'action': 'visual_admin_apply',
                'database_target_id': tid,
                'request': {
                    'database_target_id': tid,
                    'plan_id': fresh_plan['plan_id'],
                    'plan_digest': fresh_plan['plan_digest'],
                    'confirmed': True,
                },
            })
            assert fresh_apply.status_code == 200 and fresh_apply.get_json()['success'], fresh_apply.get_json()

            ext = _create_client(
                SimpleNamespace(require=lambda *_: None, acquire_secret=None),
                attachment_mode='embedded',
                profile=embedded.PROFILE,
                administration=embedded.ADMINISTRATION,
            )
            conn = ext._connect({'route': route})
            try:
                q = conn.cursor()
                q.execute("SELECT COUNT(*) FROM RDB$RELATIONS WHERE RDB$RELATION_NAME='HTTP_OWNED'")
                assert q.fetchone() == (0,)
                q.close()
                conn.rollback()
            finally:
                ext._forget_and_close(conn)
                ext.close()
            proof['checks'].append('Fresh reviewed HTTP visual_admin_apply drops target cleanly')

        proof['owned_state_removed'] = not root.exists()
        proof['source_runtime_unchanged'] = _runtime_fingerprint(runtime) == before
        proof['complete'] = proof['owned_state_removed'] and proof['source_runtime_unchanged'] and len(proof['checks']) == 4
    finally:
        (output / 'http.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('all', 'native', 'http'), default='all')
    args = parser.parse_args()
    if args.mode == 'native':
        result = qualify(args.runtime, args.output)
        print(json.dumps({'complete': result['complete'], 'modes': len(result['modes'])}))
        raise SystemExit(0 if result['complete'] else 1)
    if args.mode == 'http':
        result = qualify_http(args.runtime, args.output)
        print(json.dumps({'http_complete': result['complete'], 'checks': len(result['checks'])}))
        raise SystemExit(0 if result['complete'] else 1)
    native_res = qualify(args.runtime, args.output)
    http_proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), '--runtime', str(args.runtime), '--output', str(args.output), '--mode', 'http'],
        check=False, capture_output=True, text=True,
    )
    if http_proc.returncode != 0:
        sys.stderr.write(http_proc.stdout + http_proc.stderr)
        raise SystemExit(http_proc.returncode)
    http_res = json.loads((Path(args.output).resolve() / 'http.json').read_text())
    both_ok = bool(native_res.get('complete') and http_res.get('complete'))
    print(json.dumps({'complete': both_ok, 'modes': len(native_res['modes']), 'http_checks': len(http_res['checks'])}))
    raise SystemExit(0 if both_ok else 1)

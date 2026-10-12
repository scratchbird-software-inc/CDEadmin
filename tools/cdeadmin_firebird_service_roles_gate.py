#!/usr/bin/env python3
"""FM-FB02-008 Linux service authentication/role matrix on owned databases.

Windows/macOS teams must repeat native client transport, path and UI checks.
Service errors may follow a native state change: never retry a mutation or
infer rollback from a denied role. All files here belong to one owned server.
"""

import argparse
import copy
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import secrets
import time
import traceback
from types import SimpleNamespace
import uuid

from tools.cdeadmin_firebird_logical_volumes_gate import (
    docker, published_port, remove_owned, OWNER, _route_arguments,
    _create_client, _configure_client_library, SecretLease,
)
from pgadmin.cdeadmin.providers.relational_admin import (
    _FIREBIRD_SERVICE_OPERATIONS, FIREBIRD_SYSTEM_PRIVILEGES,
)
from pgadmin.cdeadmin.providers.firebird.error_diagnostics import status_codes
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def run():
    import firebird.driver as native
    _configure_client_library(native)
    root_password, user_password = secrets.token_urlsafe(24), (
        secrets.token_urlsafe(24))
    container = root = None
    result = {'complete': False, 'checks': [], 'failures': [],
              'owned_container_removed': False,
              'credential_values_exported': False}
    bootstrap = '/var/lib/firebird/data/roles_bootstrap.fdb'

    def client(password):
        return _create_client(SimpleNamespace(
            acquire_secret=lambda *_: SecretLease(password)))

    def open_db(path, create=False):
        method = native.create_database if create else native.connect
        return method(password=root_password, **_route_arguments(
            {**route, 'database': path}, native))

    def root_action(operation, path, options):
        return root.run_server_operation({'route': route}, operation,
                                         path, options)

    try:
        container = docker(
            'run', '--detach', '--name', 'cdeadmin-service-roles-' +
            uuid.uuid4().hex[:16], '--label', 'cdeadmin-owned-gate=' + OWNER,
            '--publish', '127.0.0.1::3050', '--env', 'FIREBIRD_ROOT_PASSWORD',
            '--env', 'FIREBIRD_DATABASE', 'firebirdsql/firebird:5.0.4',
            env=dict(os.environ, FIREBIRD_ROOT_PASSWORD=root_password,
                     FIREBIRD_DATABASE=bootstrap)).decode().strip()
        route = {'host': '127.0.0.1', 'port': published_port(container),
                 'user': 'SYSDBA', 'auth_plugin_list': 'Srp256', 'timeout': 3,
                 'credential_reference_id': 'owned-service-secret',
                 'principal_reference': 'owned-service-principal'}
        deadline = time.monotonic() + 60
        while True:
            try:
                with open_db(bootstrap) as db:
                    db.execute_immediate("CREATE USER CDE_SVC_OPERATOR "
                                         "PASSWORD '" + user_password + "'")
                    db.execute_immediate(
                        'GRANT CREATE DATABASE TO USER CDE_SVC_OPERATOR')
                    db.commit()
                break
            except native.Error:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.25)
        root = client(root_password)
        defaults = {
            'set_page_cache_size': {'page_buffers': 256},
            'set_sweep_interval': {'sweep_interval': 12345},
            'set_space_reservation': {'mode': 'USE_FULL'},
            'set_write_mode': {'mode': 'SYNC'},
            'set_access_mode': {'mode': 'READ_ONLY'},
            'set_sql_dialect': {'sql_dialect': 1},
            'set_replica_mode': {'mode': 'READ_ONLY'},
            'shutdown_database': {'mode': 'FULL', 'method': 'FORCED',
                                  'shutdown_timeout': 0},
            'bring_online': {'mode': 'NORMAL'},
            'repair_database': {'repair_action': 'VALIDATE_DB'},
            'database_statistics': {'statistics_flags': ['DATA_PAGES']},
        }
        for operation in sorted(_FIREBIRD_SERVICE_OPERATIONS):
            for scope in ('administrator', 'default-role', 'task-role',
                          'unprivileged'):
                label = operation + ':' + scope
                print(label, flush=True)
                limited = None
                try:
                    path = '/var/lib/firebird/data/task_' + uuid.uuid4().hex
                    database = path + '.fdb'
                    with open_db(database, True) as db:
                        db.execute_immediate('CREATE TABLE MARKER (ID INT)')
                        privileges = ', '.join(FIREBIRD_SYSTEM_PRIVILEGES)
                        db.execute_immediate('CREATE ROLE CDE_SVC_ROLE SET '
                                             'SYSTEM PRIVILEGES TO ' +
                                             privileges)
                        db.execute_immediate('GRANT CDE_SVC_ROLE TO '
                                             'CDE_SVC_OPERATOR')
                        db.execute_immediate('CREATE ROLE CDE_NO_RIGHTS')
                        db.execute_immediate('GRANT CDE_NO_RIGHTS TO '
                                             'CDE_SVC_OPERATOR')
                        db.commit()
                        db.execute_immediate('INSERT INTO MARKER VALUES (1)')
                        if operation == 'activate_shadow':
                            db.execute_immediate("CREATE SHADOW 1 MANUAL '" +
                                                 path + ".shd'")
                        db.commit()
                    options = copy.deepcopy(defaults.get(operation, {}))
                    observe = database
                    if operation == 'backup_logical':
                        options['backup_file'] = path + '.fbk'
                    elif operation == 'backup_physical':
                        options.update(backup_file=path + '.nbk',
                                       backup_level=0)
                    elif operation in ('restore_logical', 'restore_physical'):
                        logical = operation == 'restore_logical'
                        backup = path + ('.fbk' if logical else '.nbk')
                        root_action('backup_logical' if logical else
                                    'backup_physical', database,
                                    {'backup_file': backup, 'backup_level': 0})
                        observe = path + '.restored.fdb'
                        options = {'restore_database': observe}
                        key = 'backup_file' if logical else 'backup_files'
                        options[key] = backup if logical else [backup]
                    elif operation == 'fixup_database':
                        with open_db(database) as db:
                            db.execute_immediate('ALTER DATABASE BEGIN BACKUP')
                            db.commit()
                            observe = path + '.copy.fdb'
                            docker('exec', container, 'cp', '--', database,
                                   observe)
                            db.execute_immediate('ALTER DATABASE END BACKUP')
                            db.commit()
                        database = observe
                    elif operation == 'activate_shadow':
                        docker('exec', container, 'mv', '--', database,
                               database + '.isolated')
                        observe = path + '.shd'
                        options = {'shadow_filename': observe,
                                   'confirmation': observe,
                                   'original_isolated': True}
                        database = observe
                    elif operation == 'bring_online':
                        root_action('shutdown_database', database, {
                            'mode': 'MULTI', 'method': 'FORCED',
                            'shutdown_timeout': 0})
                    selected = {**route, 'database': database}
                    if scope != 'administrator':
                        selected['user'] = 'CDE_SVC_OPERATOR'
                    if scope == 'default-role':
                        selected['role'] = 'CDE_SVC_ROLE'
                    elif scope == 'task-role':
                        selected['role'] = 'CDE_NO_RIGHTS'
                        options['role'] = 'CDE_SVC_ROLE'
                    saved = copy.deepcopy((selected, options))
                    limited = client(root_password if scope == 'administrator'
                                     else user_password)
                    error_codes = []
                    try:
                        receipt = limited.run_server_operation(
                            {'route': selected}, operation, database, options)
                    except RelationalClientError as error:
                        error_codes = list(status_codes(error))
                        if scope != 'unprivileged':
                            raise
                        assert error_codes, 'Denial must be a native outcome'
                        auth = error.service_authentication_requested
                        accepted = False
                    else:
                        assert receipt['server_completed'] is True
                        assert receipt['service_release'][
                            'service_handle_released'] is True
                        auth = receipt['service_authentication_requested']
                        accepted = True
                    assert not limited._connections
                    assert (selected, options) == saved
                    assert auth['requested_role'] == (
                        'CDE_SVC_ROLE' if scope in (
                            'default-role', 'task-role')
                        else None)
                    assert auth['role_source'] == {
                        'administrator': 'none', 'default-role': 'connection',
                        'task-role': 'task', 'unprivileged': 'none'}[scope]
                    assert auth['authorization_verified'] is False
                    if scope == 'unprivileged':
                        # Observed 5.0.4 authority boundary: these do not
                        # require a target DB role in this fixture. Logical
                        # restore uses its explicit CREATE DATABASE grant.
                        assert accepted == (operation in {
                            'fixup_database', 'restore_logical',
                            'restore_physical', 'validate_database'})
                    if operation in ('shutdown_database', 'bring_online'):
                        try:
                            root_action('bring_online', observe,
                                        {'mode': 'NORMAL'})
                        except RelationalClientError as error:
                            # Native rejects NORMAL -> NORMAL. Confirm the
                            # state independently; never infer it from error.
                            assert 335544835 in status_codes(error)
                            with open_db(observe) as db:
                                with db.cursor() as cursor:
                                    cursor.execute('SELECT MON$SHUTDOWN_MODE '
                                                   'FROM MON$DATABASE')
                                    assert cursor.fetchone() == (0,)
                    if accepted:
                        with open_db(observe) as db:
                            with db.cursor() as cursor:
                                cursor.execute('SELECT ID FROM MARKER')
                                assert cursor.fetchall() == [(1,)]
                    if operation == 'database_statistics' and (
                            scope == 'task-role'):
                        # Native UTF-8 service-role transport must preserve
                        # a granted non-ASCII identity, not just ASCII names.
                        with open_db(database) as administrator:
                            administrator.execute_immediate(
                                'CREATE ROLE "CDE_RÔLE_東京" SET '
                                'SYSTEM PRIVILEGES TO ' + privileges)
                            administrator.execute_immediate(
                                'GRANT "CDE_RÔLE_東京" TO CDE_SVC_OPERATOR')
                            administrator.commit()
                        held_route = {**selected, 'role': 'CDE_SVC_ROLE'}
                        held = limited.open_session({'route': held_route})
                        with held.cursor() as cursor:
                            cursor.execute('INSERT INTO MARKER VALUES (2)')
                            cursor.execute('SELECT CURRENT_TRANSACTION '
                                           'FROM RDB$DATABASE')
                            transaction = cursor.fetchone()[0]

                        def parallel(index):
                            role = ('CDE_SVC_ROLE' if index % 2 == 0 else
                                    'CDE_NO_RIGHTS')
                            if index in (2, 6):
                                role = 'CDE_RÔLE_東京'
                            try:
                                value = limited.run_server_operation(
                                    {'route': selected}, operation, database,
                                    {**options, 'role': role})
                            except RelationalClientError as error:
                                assert index % 2 == 1
                                assert status_codes(error)
                                auth = error.service_authentication_requested
                            else:
                                assert index % 2 == 0
                                auth = value[
                                    'service_authentication_requested']
                            assert auth['requested_role'] == role
                            return {'index': index, 'requested_role': role}

                        with ThreadPoolExecutor(max_workers=4) as pool:
                            parallel_results = list(pool.map(parallel,
                                                             range(8)))
                        assert held.main_transaction.is_active()
                        with held.cursor() as cursor:
                            cursor.execute('SELECT CURRENT_TRANSACTION '
                                           'FROM RDB$DATABASE')
                            assert cursor.fetchone()[0] == transaction
                        with open_db(database) as observer:
                            with observer.cursor() as cursor:
                                cursor.execute('SELECT ID FROM MARKER')
                                assert cursor.fetchall() == [(1,)]
                        limited.close_session(held)
                        result['concurrent_roles'] = parallel_results
                        result['pending_sql_transaction_unchanged'] = True
                    result['checks'].append({
                        'operation': operation, 'scope': scope,
                        'native_accepted': accepted,
                        'native_codes': error_codes,
                        'authentication': auth,
                        'saved_inputs_unchanged': True,
                        'handles_released': True,
                        'marker_verified': accepted})
                except Exception as error:
                    result['failures'].append({
                        'case': label, 'type': type(error).__name__,
                        'codes': list(status_codes(error)),
                        'frames': [{'file': Path(f.filename).name,
                                    'line': f.lineno} for f in
                                   traceback.extract_tb(error.__traceback__)]})
                finally:
                    if limited:
                        limited.close()
    finally:
        if root:
            root.close()
        if container:
            remove_owned(container)
            result['owned_container_removed'] = True
    result['complete'] = (len(result['checks']) == 84 and
                          len(result.get('concurrent_roles', [])) == 8 and
                          result.get('pending_sql_transaction_unchanged') and
                          not result['failures'] and
                          result['owned_container_removed'])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a new evidence file; preserve previous failures')
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    raise SystemExit(0 if result['complete'] else 1)

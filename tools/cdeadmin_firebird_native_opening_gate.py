#!/usr/bin/env python3
"""Exercise concurrent admission and real process loss on an owned server."""

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import re
import secrets
import socket
import threading
import time
from types import SimpleNamespace
import uuid

if __package__:
    from .cdeadmin_firebird_logical_volumes_gate import (
        docker, published_port, remove_owned, OWNER, _configure_client_library,
        _route_arguments, _create_client,
    )
else:
    from cdeadmin_firebird_logical_volumes_gate import (
        docker, published_port, remove_owned, OWNER, _configure_client_library,
        _route_arguments, _create_client,
    )
from pgadmin.cdeadmin.core import EndpointContext
from pgadmin.cdeadmin.endpoints.service import EndpointService
from pgadmin.cdeadmin.providers.firebird.provider import (
    FirebirdProvider, PROFILE,
)
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from pgadmin.cdeadmin.security.secrets import SecretLease


def provider_for(password):
    context = EndpointContext(
        endpoint_id=str(uuid.uuid4()), mode='legacy_native',
        experience_family=PROFILE.engine_id, provider_id=PROFILE.provider_id,
        provider_version='0.1.0', profile_id=PROFILE.profile_id,
        profile_version=PROFILE.exact_version,
        target_adapter_id=f'{PROFILE.protocol_id}-client',
        target_adapter_version='native-gate',
        pool_namespace=str(uuid.uuid4()), session_namespace=str(uuid.uuid4()),
        cache_namespace=str(uuid.uuid4()),
        diagnostic_namespace=str(uuid.uuid4()),
        effective_permissions=frozenset(PROFILE.required_permissions))
    permissions = SimpleNamespace(
        require=lambda *_args: None,
        acquire_secret=lambda *_args: SecretLease(password))
    client = _create_client(permissions)
    return FirebirdProvider(context, permissions, client), client


def wait_ready(native, route, password):
    deadline = time.monotonic() + 45
    while True:
        try:
            with native.connect(**_route_arguments(route, native),
                                password=password):
                return
        except native.Error:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.25)


def concurrent_open(native, route, password):
    provider, client = provider_for(password)
    entered, release = threading.Event(), threading.Event()
    results, failures = [], []
    original = client.config.session_initializer

    def pause(handle, selected):
        if original:
            original(handle, selected)
        entered.set()
        if not release.wait(15):
            raise RuntimeError('Native opening synchronization timed out')

    client.config = replace(client.config, session_initializer=pause)

    def open_one():
        try:
            results.append(provider.open_session({'route': route}))
        except BaseException as error:
            failures.append(type(error).__name__)

    worker = threading.Thread(target=open_one)
    worker.start()
    try:
        assert entered.wait(15)
        assert not provider._sessions
        try:
            client.close()
        except RelationalClientError as error:
            assert 'still opening' in str(error)
        else:
            raise AssertionError('Shutdown admitted an unpublished session')
        # An independent attachment remains usable while admission is paused.
        with native.connect(**_route_arguments(route, native),
                            password=password) as observer:
            with observer.cursor() as cursor:
                cursor.execute('SELECT COUNT(*) FROM MON$ATTACHMENTS '
                               'WHERE MON$SYSTEM_FLAG = 0')
                assert cursor.fetchone()[0] == 2
            observer.rollback()
    finally:
        release.set()
        worker.join(20)
    try:
        assert not worker.is_alive() and not failures and len(results) == 1
        assert len(provider._sessions) == 1 and client._opening == 0
        handle = provider._sessions[results[0]['session_id']].handle
        assert client.runtime_identity({}, handle)['version'] == '5.0.4'
    finally:
        client.close()
    assert not client._connections
    return {'unpublished_until_admitted': True,
            'close_during_open_refused': True,
            'independent_native_attachment_usable': True,
            'admitted_session_usable': True, 'native_handles_released': True}


def identity_admission(native, route, password):
    provider, client = provider_for(password)
    try:
        server_route = {key: value for key, value in route.items()
                        if key != 'database'}
        identity = client.runtime_identity({'route': server_route})
        assert identity['version'] == '5.0.4'
        assert identity['build_id'].endswith(':service-manager')
        assert not client._connections
        # Real native identity, deliberately incompatible admission policy.
        # No replacement of native version responses or native handles.
        provider.profile = replace(PROFILE, exact_version='6.0.0',
                                   minimum_version=None)
        try:
            provider.open_session({'route': route})
        except Exception as error:
            assert type(error).__name__ == 'RuntimeIdentityError'
        else:
            raise AssertionError('Mismatched native version was admitted')
        assert not provider._sessions and not client._connections
    finally:
        client.close()
    restricted = 'OWNED_IDENTITY_READER'
    with native.connect(**_route_arguments(route, native),
                        password=password) as administrator:
        administrator.execute_immediate(
            f"CREATE USER {restricted} PASSWORD '{password}'")
        administrator.commit()
    _provider, reader = provider_for(password)
    try:
        identity = reader.runtime_identity({
            'route': {**route, 'user': restricted}})
        assert identity['version'] == '5.0.4'
        assert not reader._connections
    finally:
        reader.close()
        with native.connect(**_route_arguments(route, native),
                            password=password) as administrator:
            administrator.execute_immediate(f'DROP USER {restricted}')
            administrator.commit()
    return {'server_identity_without_database': True,
            'incompatible_policy_rejects_native_version': True,
            'rejected_handle_not_published_or_leaked': True,
            'unprivileged_database_identity_read': True}


def native_failover(route, password):
    provider, client = provider_for(password)
    observed = []

    class Binding:
        def discover_endpoint(self, request):
            observed.append(request['route']['route_id'])
            assert 'database' not in request['route']
            return provider.discover_endpoint(request)

    class MemoryEndpointService(EndpointService):
        # Configuration persistence is in-memory in this native route probe.
        # Routing, credential references, identity checks and native discovery
        # are the production paths, not synthetic failed connection responses.
        @staticmethod
        def _record_verification(endpoint, state, family=None, version=None,
                                 evidence=None):
            endpoint.runtime_identity.verification_state = state
            endpoint.runtime_identity.verified_runtime_family = family
            endpoint.runtime_identity.verified_runtime_version = version

    registry = SimpleNamespace(resolve=lambda _context:
                               SimpleNamespace(instance=Binding()))
    security = SimpleNamespace(secrets=SimpleNamespace(
        register_resolver=lambda *_args: None,
        register_reference=lambda *_args: None))
    service = MemoryEndpointService(registry, security)
    context = provider.context
    values = {key: getattr(context, key) for key in (
        'endpoint_id', 'experience_family', 'provider_id', 'provider_version',
        'profile_id', 'profile_version', 'target_adapter_id',
        'target_adapter_version', 'pool_namespace', 'session_namespace',
        'cache_namespace', 'diagnostic_namespace')}
    values['id'] = values.pop('endpoint_id')
    values['endpoint_mode'] = context.mode
    endpoint = SimpleNamespace(
        **values, database_targets=[],
        runtime_identity=SimpleNamespace(
            declared_runtime_family='firebird',
            verification_state='unverified'),
        secret_references=[SimpleNamespace(
            id=str(uuid.uuid4()), secret_kind='database_password',
            storage_kind='legacy_protected_column',
            secret_reference='server:1:password')])
    server = SimpleNamespace(id=1, user_id=1, endpoint_profile=endpoint)
    with socket.socket() as failed:
        failed.bind(('127.0.0.1', 0))
        endpoint.routes = [SimpleNamespace(
            id='unavailable', priority=0, configuration=json.dumps({
                **route, 'port': failed.getsockname()[1]})), SimpleNamespace(
            id='available', priority=1, configuration=json.dumps(route))]
        try:
            result = service.verify_server(server)
            assert result['selected_route_id'] == 'available'
            assert observed == ['unavailable', 'available']
            assert not provider._sessions and not client._connections
            health = service.route_health.snapshot(endpoint.id)
            assert health['unavailable']['consecutive_failures'] == 1
            assert health['available']['consecutive_failures'] == 0
        finally:
            client.close()
    return {'real_connection_refusal': True, 'native_fallback_verified': True,
            'priority_order': observed, 'no_retained_session_during_failover':
            True, 'configuration_persistence': 'in-memory-fixture'}


def address_identity(native, route, password, container):
    alias = 'CDE_OWNED_ALIAS'
    docker('exec', '-i', container, 'tee', '-a',
           '/opt/firebird/databases.conf', input_data=(
               f'\n{alias} = {route["database"]}\n'.encode()))
    remote = docker('inspect', '--format',
                    '{{range .NetworkSettings.Networks}}'
                    '{{.IPAddress}}{{end}}', container).decode().strip()
    cases, failures = [], []
    for name, selection in (
            ('hostname', {**route, 'host': 'localhost'}),
            ('alias', {**route, 'database': alias}),
            ('bridge-server', {**route, 'host': remote, 'port': 3050})):
        try:
            if name == 'bridge-server':
                with socket.create_connection((remote, 3050), timeout=3):
                    pass
            with native.connect(**_route_arguments(selection, native),
                                password=password) as handle:
                with handle.cursor() as cursor:
                    cursor.execute(
                        "SELECT RDB$GET_CONTEXT('SYSTEM', 'DB_NAME') "
                        'FROM RDB$DATABASE')
                    assert cursor.fetchone()[0] == route['database']
                handle.rollback()
            cases.append(name)
        except Exception as error:
            failures.append({'case': name, 'type': type(error).__name__,
                             'detail': str(error).replace(
                                 password, '[redacted]')})
    # A target spelling cannot override the selected physical server.
    try:
        _route_arguments({**route, 'database': 'different-server:elsewhere'},
                         native)
    except RelationalClientError:
        pass
    else:
        raise AssertionError('Database target escaped its selected server')
    return {'complete': not failures, 'failures': failures,
            'native_target_identity_cases': cases,
            'cross_server_dsn_refused': True,
            'remote_scope': 'owned Docker bridge; not a separate host'}


def process_loss(native, route, password, container):
    provider, client = provider_for(password)
    admitted, admitted_client = provider_for(password)
    retained = admitted.open_session({'route': route})
    admitted_handle = admitted._sessions[retained['session_id']].handle
    admitted_handle.execute_immediate('CREATE TABLE OWNED_NO_REPLAY (ID INT)')
    admitted_handle.commit()
    admitted_handle.execute_immediate('INSERT INTO OWNED_NO_REPLAY VALUES (1)')
    captured = []
    original = client.config.session_initializer

    def lose_server(handle, selected):
        if original:
            original(handle, selected)
        captured.append(handle)
        handle.execute_immediate('CREATE TABLE UNPUBLISHED_WORK (ID INTEGER)')
        # The container is uniquely created by this gate. Never kill a demo.
        label = docker('inspect', '--format',
                       '{{index .Config.Labels "cdeadmin-owned-gate"}}',
                       container).decode().strip()
        assert label == OWNER
        docker('kill', container)

    client.config = replace(client.config, session_initializer=lose_server)
    try:
        try:
            provider.open_session({'route': route})
        except Exception as error:
            failure_type = type(error).__name__
        else:
            raise AssertionError('Dead server attachment was published')
        assert captured and not provider._sessions and client._opening == 0
        try:
            admitted_client.execute(admitted_handle, {
                'source': 'INSERT INTO OWNED_NO_REPLAY VALUES (2)'})
        except RelationalClientError:
            pass
        else:
            raise AssertionError(
                'Dead-session mutation unexpectedly succeeded')
        retained = bool(client._connections)
        if retained:
            try:
                client.execute(captured[0], {
                    'source': 'SELECT 1 FROM RDB$DATABASE'})
            except RelationalClientError as error:
                assert 'cleanup-only' in str(error)
            else:
                raise AssertionError('Unverified attachment allowed a query')
        client.close()
        assert not client._connections
    finally:
        admitted_client.close()
        docker('start', container)
        route['port'] = published_port(container)
        wait_ready(native, route, password)
    with native.connect(**_route_arguments(route, native),
                        password=password) as observer:
        with observer.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM RDB$RELATIONS '
                           "WHERE RDB$RELATION_NAME = 'UNPUBLISHED_WORK'")
            assert cursor.fetchone()[0] == 0
            cursor.execute('SELECT COUNT(*) FROM OWNED_NO_REPLAY')
            assert cursor.fetchone()[0] == 0
        observer.rollback()
    return {'actual_server_process_killed': True,
            'session_not_published': True,
            'native_failure_type': failure_type,
            'quarantine_needed_by_native_driver': retained,
            'established_session_mutation_not_replayed': True,
            'cleanup_completed': True, 'uncommitted_ddl_absent_after_restart':
            True}


def run(image):
    import firebird.driver as native
    _configure_client_library(native)
    result = {'complete': False, 'cases': {}, 'failures': [],
              'owned_container_removed': False}
    container = None
    password = secrets.token_urlsafe(24)
    path = '/var/lib/firebird/data/owned_opening.fdb'
    try:
        container = docker(
            'run', '--detach', '--name',
            'cdeadmin-native-opening-' + uuid.uuid4().hex[:16],
            '--label', 'cdeadmin-owned-gate=' + OWNER,
            '--publish', '127.0.0.1::3050',
            '--env', 'FIREBIRD_ROOT_PASSWORD', '--env', 'FIREBIRD_DATABASE',
            image, env=dict(os.environ, FIREBIRD_ROOT_PASSWORD=password,
                            FIREBIRD_DATABASE=path)).decode().strip()
        assert re.fullmatch('[0-9a-f]{64}', container)
        route = {'host': '127.0.0.1', 'port': published_port(container),
                 'database': path, 'user': 'SYSDBA', 'timeout': 2,
                 'credential_reference_id': 'owned-opening-secret',
                 'principal_reference': 'owned-opening-principal'}
        wait_ready(native, route, password)
        for name, operation in (
                ('address-identity', lambda: address_identity(
                    native, route, password, container)),
                ('native-failover', lambda: native_failover(route, password)),
                ('identity-admission', lambda: identity_admission(
                    native, route, password)),
                ('concurrent-open', lambda: concurrent_open(
                    native, route, password)),
                ('process-loss', lambda: process_loss(
                    native, route, password, container))):
            try:
                case_result = operation()
                result['cases'][name] = case_result
                if case_result.get('complete') is False:
                    result['failures'].append({
                        'case': name, 'type': 'IncompleteCase',
                        'detail': 'See case failure inventory'})
            except Exception as error:
                result['failures'].append({
                    'case': name, 'type': type(error).__name__,
                    'detail': str(error).replace(password, '[redacted]')})
    finally:
        if container:
            remove_owned(container)
            result['owned_container_removed'] = True
    result['complete'] = (len(result['cases']) == 5 and not result['failures']
                          and result['owned_container_removed'])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='firebirdsql/firebird:5.0.4')
    parser.add_argument('--output', required=True, type=Path)
    options = parser.parse_args()
    if options.output.exists():
        parser.error('Use a new evidence output')
    outcome = run(options.image)
    options.output.write_text(json.dumps(outcome, indent=2) + '\n')
    raise SystemExit(0 if outcome['complete'] else 1)

#!/usr/bin/env python3
"""Owned Linux native prepared-group qualification; no installed server edits.

The lost-response case injects failure after a real native decision returns.
A separate case drops an owned TCP link before reconstruction. Neither claims
coverage of every interruption timing or cross-platform qualification.
"""

import argparse
from contextlib import ExitStack
from dataclasses import replace
import json
import os
from pathlib import Path
import secrets
import tempfile
import traceback
from types import SimpleNamespace
import uuid
from unittest.mock import patch

from tools.cdeadmin_firebird_local_fixture import run_local
from tools.cdeadmin_firebird_inet_gate import relay
from tools.cdeadmin_firebird_password_gate import _route_arguments, SecretLease
from tools.cdeadmin_relational_provider_live_verify import (
    _context, _permissions,
)
from pgadmin.cdeadmin.operations.store import JsonOperationStore
from pgadmin.cdeadmin.providers.firebird.provider import (
    PROFILE, create_provider,
)
from pgadmin.cdeadmin.providers.firebird import limbo
from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService


def qualify(native, admin, route, accounts, evidence, root, peer=None,
            embedded_mode=False):
    peer_admin, peer_route, peer_root = peer or (admin, route, root)
    if embedded_mode:
        credentials = [('OWNED_LOCAL_1', None), ('OWNED_LOCAL_2', None)]
    else:
        second = ('OWNED_RECOVERY', secrets.token_urlsafe(24))
        peer_admin.execute_immediate(
            f"CREATE USER {second[0]} PASSWORD '{second[1]}' USING PLUGIN Srp")
        peer_admin.execute_immediate(
            f'GRANT CREATE DATABASE TO USER {second[0]}')
        peer_admin.commit()
        credentials = [accounts['Srp'][0], second]
    profile = embedded.PROFILE if embedded_mode else PROFILE
    factory = embedded.create_provider if embedded_mode else create_provider
    checks = []
    scenarios = ('commit', 'rollback', 'lost_response') + (
        () if embedded_mode else ('link_disconnect',))
    for scenario in scenarios:
        routes, handles, providers, contexts = {}, [], {}, {}
        for index, (user, password) in enumerate(credentials, 1):
            base, location = (route, root) if index == 1 else (
                peer_route, peer_root)
            selected = {**base, 'user': user,
                        'database': str(location / f'{scenario}-{index}.fdb')}
            if embedded_mode:
                local_root = location / f'participant-{index}'
                local_root.mkdir(exist_ok=True)
                selected = {'attachment_mode': 'embedded', 'user': user,
                            'filesystem_root': str(local_root),
                            'database': str(
                                local_root / f'{scenario}.fdb')}
            handle = native.create_database(
                password=password, **_route_arguments(selected, native))
            if embedded_mode:
                with handle.cursor() as cursor:
                    cursor.execute(
                        'SELECT MON$REMOTE_PROTOCOL, MON$SERVER_PID, '
                        "RDB$GET_CONTEXT('SYSTEM','ENGINE_VERSION') "
                        'FROM MON$ATTACHMENTS WHERE '
                        'MON$ATTACHMENT_ID=CURRENT_CONNECTION')
                    protocol, pid, version = cursor.fetchone()
                assert protocol is None and pid == os.getpid()
                assert version == '5.0.4'
                handle.rollback()
            handle.execute_immediate(
                'CREATE TABLE RECOVERY_MARKER (ID INTEGER)')
            handle.commit()
            handles.append(handle)
            routes[index] = {**selected,
                             'credential_reference_id': f'owned-{index}',
                             'principal_reference': f'principal-{index}'}
            if embedded_mode:
                routes[index].pop('credential_reference_id')
        manager = native.DistributedTransactionManager(
            handles, default_action=native.DefaultAction.ROLLBACK)
        identifiers = []
        for handle in handles:
            with manager.cursor(handle) as cursor:
                cursor.execute('INSERT INTO RECOVERY_MARKER VALUES (1)')
                cursor.execute('SELECT CURRENT_TRANSACTION FROM RDB$DATABASE')
                identifiers.append(str(cursor.fetchone()[0]))
        manager._tra.prepare()
        for handle in handles:
            handle._att.detach()
            handle._att = None
        manager._tra.release()
        manager._tra = None
        for handle in handles:
            handle.main_transaction._tra = None
        servers = {i: SimpleNamespace(
            id=i, user_id=1, name=f'Owned participant {i}',
            endpoint_profile=SimpleNamespace(profile_id=profile.profile_id))
            for i in (1, 2)}
        with ExitStack() as owned:
            if scenario == 'link_disconnect':
                proxy = owned.enter_context(relay(
                    (routes[1]['host'], routes[1]['port']), host='127.0.0.1'))
                routes[1].update(host=proxy.host, port=proxy.port)
            for index, (_, password) in enumerate(credentials, 1):
                context = replace(_context(profile),
                                  endpoint_id=str(uuid.uuid4()))
                if embedded_mode:
                    context = replace(
                        context, target_adapter_id='firebird-embedded-client')
                contexts[index] = context

                def acquire(reference, requested, principal, purpose,
                            expected_kind, *, n=index, secret=password,
                            expected=context):
                    assert not embedded_mode, 'Embedded must not read secrets'
                    assert requested == expected
                    assert reference == f'owned-{n}'
                    assert principal == f'principal-{n}'
                    assert expected_kind == 'database_password'
                    return SecretLease(secret)

                providers[index] = factory(
                    context, _permissions(
                        context, SimpleNamespace(acquire=acquire)))
            registry = SimpleNamespace(resolve=lambda context: SimpleNamespace(
                instance=next(providers[i] for i in providers
                              if contexts[i] == context)))

            def workspace(server, database_target_id):
                assert database_target_id == str(server.id)
                return contexts[server.id], {'route': routes[server.id]}, None

            endpoint_service = SimpleNamespace(
                workspace=workspace, provider_registry=registry)
            store_path = evidence / f'{scenario}-operations.json'

            def service():
                return ProviderWorkspaceService(
                    endpoint_service, SimpleNamespace(
                        invalidate=lambda _: None),
                    None, None, operation_bus=SimpleNamespace(
                        store=JsonOperationStore(store_path)))

            current = service()

            def action(name, request, target=None):
                return (target or current).firebird_recovery_action(
                    servers[1], 'firebird_recovery_' + name, request,
                    servers.get)

            try:
                review = action('preview', {
                    'decision': ('rollback' if scenario == 'rollback'
                                 else 'commit'),
                    'participants': [{
                        'server_id': i, 'database_target_id': str(i),
                        'transaction_id': identifiers[i - 1]}
                        for i in (1, 2)]})
                assert len({p['database_identity']['guid']
                            for p in review['participants']}) == 2
                request = {key: review[key] for key in (
                    'group_id', 'review_digest', 'decision')}
                request.update(coordinator_reviewed=True, confirmations=[
                    {key: p[key] for key in ('database', 'transaction_id')}
                    for p in review['participants']])
                dispatches = []
                for index, provider in providers.items():
                    original = provider.client.run_limbo_operation

                    def dispatch(*args, n=index, call=original, **kwargs):
                        dispatches.append(n)
                        result = call(*args, **kwargs)
                        if scenario == 'lost_response' and n == 1:
                            raise ConnectionError('Injected response loss')
                        return result

                    provider.client.run_limbo_operation = dispatch
                if scenario == 'link_disconnect':
                    original_run = limbo.NativeRecovery.run

                    def interrupted(recovery):
                        # Drop the owned TCP attachment after opening it,
                        # before reconstructing or deciding prepared work.
                        proxy.cut()
                        return original_run(recovery)

                    with patch.object(
                            limbo.NativeRecovery, 'run', interrupted):
                        result = action('apply', request)
                else:
                    result = action('apply', request)
                assert result['state'] == (
                    'needs_review' if scenario in {
                        'lost_response', 'link_disconnect'}
                    else 'native_calls_returned')
                before = list(dispatches)
                repeated = action('apply', request, service())
                assert repeated['state'] == result['state']
                assert dispatches == before
                observations = []
                for index, (_, password) in enumerate(credentials, 1):
                    observed_route = routes[index]
                    if scenario == 'link_disconnect' and index == 1:
                        observed_route = {
                            **observed_route, 'host': route['host'],
                            'port': route['port']}
                    with native.connect(password=password, **_route_arguments(
                            observed_route, native)) as connection:
                        inventory = limbo.inspect_attachment(
                            connection, native)
                        if scenario == 'link_disconnect' or (
                                scenario == 'lost_response' and index == 2):
                            assert identifiers[index - 1] in {
                                row['transaction_id'] for row in inventory}
                            observations.append({
                                'participant': index,
                                'independently_in_limbo': True})
                        else:
                            assert not inventory
                            with connection.cursor() as cursor:
                                cursor.execute(
                                    'SELECT COUNT(*) FROM RECOVERY_MARKER')
                                count = cursor.fetchone()[0]
                            assert count == (
                                0 if scenario == 'rollback' else 1)
                            observations.append({'participant': index,
                                                 'committed_rows': count})
                checks.append({'scenario': scenario, 'state': result['state'],
                               'dispatches': dispatches,
                               'attachment_mode': (
                                   'embedded' if embedded_mode else 'network'),
                               'distinct_server_ports': (
                                   routes[1].get('port') !=
                                   routes[2].get('port')),
                               'independent_observations': observations,
                               'reopened_store_did_not_replay': True})
                (evidence / 'recovery-checks.json').write_text(
                    json.dumps(checks, indent=2) + '\n')
            finally:
                try:
                    for provider in providers.values():
                        provider.client.close()
                finally:
                    owned.close()


def run_embedded(runtime_source, evidence, fixture_check=None,
                 shared_process_access=False):
    """Stage only local Engine13 state; never start a network server."""
    import firebird.driver as native
    from tools.cdeadmin_firebird_object_live_orchestrator import (
        _runtime_fingerprint, _stage_runtime,
    )
    from pgadmin.cdeadmin.providers.firebird.provider import (
        _configure_client_library,
    )

    evidence.mkdir(parents=True, exist_ok=False)
    before = _runtime_fingerprint(runtime_source)
    env_keys = ('FIREBIRD', 'FIREBIRD_LOCK',
                'CDEADMIN_FIREBIRD_CLIENT_LIBRARY')
    previous = {key: os.environ.get(key) for key in env_keys}
    root = None
    result = {'complete': False, 'fixture': 'local-embedded', 'failures': [],
              'runtime_sha256': before, 'server_process_started': False}
    try:
        with tempfile.TemporaryDirectory(prefix='recovery-embedded-') as tmp:
            root = Path(tmp)
            runtime = root / 'runtime'
            _stage_runtime(runtime_source, runtime)
            (runtime / 'firebird.conf').write_text(
                'Providers = Engine13\n'
                + ('ServerMode = SuperClassic\n'
                   if shared_process_access else '')
                + f'SecurityDatabase = {runtime / "security5.fdb"}\n')
            (runtime / 'databases.conf').write_text('')
            os.environ.update(FIREBIRD=str(runtime),
                              FIREBIRD_LOCK=str(runtime / 'lock'),
                              CDEADMIN_FIREBIRD_CLIENT_LIBRARY=str(
                                  runtime / 'lib/libfbclient.so.5.0.4'))
            _configure_client_library(native)
            if fixture_check is None:
                qualify(native, None, {}, None, evidence, root,
                        embedded_mode=True)
            else:
                fixture_check(native, None, {}, None, evidence, root)
    except Exception as error:
        result['failures'].append({
            'type': type(error).__name__,
            'locations': [{'file': Path(frame.filename).name,
                           'line': frame.lineno}
                          for frame in traceback.extract_tb(
                              error.__traceback__)]})
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        result['owned_state_removed'] = root is not None and not root.exists()
        result['source_runtime_unchanged'] = (
            _runtime_fingerprint(runtime_source) == before)
        result['complete'] = (not result['failures'] and
                              result['owned_state_removed'] and
                              result['source_runtime_unchanged'])
        (evidence / 'summary.json').write_text(
            json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--two-servers', action='store_true')
    mode.add_argument('--embedded', action='store_true')
    options = parser.parse_args()

    def qualify_two(native, admin, route, accounts, evidence, root):
        def with_peer(_native, peer_admin, peer_route, _accounts,
                      _evidence, peer_root):
            assert route['port'] != peer_route['port']
            qualify(native, admin, route, accounts, evidence, root,
                    peer=(peer_admin, peer_route, peer_root))

        peer_result = run_local(
            options.runtime, evidence / 'peer-fixture', with_peer)
        if not peer_result['complete']:
            raise RuntimeError('Peer fixture qualification failed')

    result = (run_embedded(options.runtime, options.evidence)
              if options.embedded else run_local(
                  options.runtime, options.evidence,
                  qualify_two if options.two_servers else qualify))
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['complete'] else 1)

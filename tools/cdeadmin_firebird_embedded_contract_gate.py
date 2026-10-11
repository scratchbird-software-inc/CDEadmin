"""Qualify embedded attachment separately from the shared SQL dialect proof.

Run in a fresh process with the exact runtime's lib directory in
LD_LIBRARY_PATH. No server is launched. Only staged configuration, lock files
and a disposable database are writable; the input runtime is fingerprinted.
This is contract admission evidence, not exhaustive Firebird feature closure.
"""

import argparse
from contextlib import ExitStack
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
import traceback

from tools.cdeadmin_firebird_object_live_orchestrator import (
    _runtime_fingerprint, _stage_runtime,
)
from tools.cdeadmin_relational_provider_live_verify import (
    _apply_editor, _context, _permissions, _verified_context,
)
from pgadmin.cdeadmin.providers.firebird import embedded_provider as embedded
from pgadmin.cdeadmin.providers.firebird.provider import (
    _configure_client_library,
)
from pgadmin.cdeadmin.security import EndpointSecretService


PACKAGE = Path(__file__).resolve().parents[1] / (
    'web/pgadmin/cdeadmin/providers/firebird')


def source_bindings():
    root = Path(__file__).resolve().parents[1]
    paths = [PACKAGE / 'firebird_dialect_5_0_4.json',
             PACKAGE / 'firebird_metrics_5_0_4.json',
             PACKAGE / 'embedded_provider.py', PACKAGE / 'provider.py',
             PACKAGE / 'query_client.py', PACKAGE / 'profiling.py',
             PACKAGE / 'query_statistics.py', PACKAGE / 'events.py',
             PACKAGE.parent / 'relational_admin.py']
    return {str(path.relative_to(root)): hashlib.sha256(
        path.read_bytes()).hexdigest() for path in paths}


def qualify(runtime_source, evidence, *, require_activation=False):
    import firebird.driver as native

    evidence.mkdir(parents=True, exist_ok=False)
    before = _runtime_fingerprint(runtime_source)
    result = {'schema': 'cdeadmin.firebird-embedded-contract-proof.v1',
              'complete': False, 'engine_version': None, 'failures': [],
              'runtime_sha256': before, 'source_bindings': source_bindings(),
              'task_ids': list(embedded.ADMINISTRATION.dialect_task_ids())}
    env_keys = ('FIREBIRD', 'FIREBIRD_LOCK',
                'CDEADMIN_FIREBIRD_CLIENT_LIBRARY')
    previous = {key: os.environ.get(key) for key in env_keys}
    root = None
    provider = None
    client = None
    try:
        with tempfile.TemporaryDirectory(
                prefix='firebird-embedded-') as tmp, ExitStack() as owners:
            root = Path(tmp)
            runtime = root / 'runtime'
            _stage_runtime(runtime_source, runtime)
            (runtime / 'firebird.conf').write_text(
                'Providers = Engine13\n'
                f'SecurityDatabase = {runtime / "security5.fdb"}\n')
            (runtime / 'databases.conf').write_text('')
            os.environ.update(FIREBIRD=str(runtime),
                              FIREBIRD_LOCK=str(runtime / 'lock'),
                              CDEADMIN_FIREBIRD_CLIENT_LIBRARY=str(
                                  runtime / 'lib/libfbclient.so.5.0.4'))
            _configure_client_library(native)
            context = replace(_context(embedded.PROFILE),
                              target_adapter_id='firebird-embedded-client')
            provider = embedded.create_provider(
                context, _permissions(context, EndpointSecretService()))
            owners.callback(provider.close)
            client = provider.client
            route = {'attachment_mode': 'embedded',
                     'filesystem_root': str(root),
                     'database': str(root / 'owned.fdb'), 'user': 'SYSDBA'}
            provider.create_initial_database({'route': route})
            connection = client.open_session({'route': route})
            observer = None
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT RDB$GET_CONTEXT('SYSTEM','ENGINE_VERSION'), "
                        'MON$REMOTE_PROTOCOL, MON$SERVER_PID '
                        'FROM MON$ATTACHMENTS '
                        'WHERE MON$ATTACHMENT_ID=CURRENT_CONNECTION')
                    version, protocol, pid = cursor.fetchone()
                assert version == '5.0.4'
                assert protocol is None and pid == os.getpid()
                result.update(engine_version=version,
                              attachment_in_current_process=True,
                              remote_protocol_absent=True)
                connection.rollback()
                plan = embedded.ADMINISTRATION.plan({
                    '_provider_route': route, 'resource_kind': 'table',
                    'operation_id': 'create', 'draft': {
                        'name': 'OWNED_CONTRACT', 'columns': [
                            {'name': 'ID', 'column_mode': 'STORED',
                             'data_type': 'INTEGER'}]}})
                embedded.ADMINISTRATION.apply(
                    client, plan, connection=connection)
                connection.commit()
                observer = client.open_session({'route': route})
                outcomes = []
                for commit, expected in ((False, 0), (True, 1)):
                    with connection.cursor() as cursor:
                        cursor.execute('INSERT INTO OWNED_CONTRACT VALUES (?)',
                                       (1,))
                    (connection.commit if commit else connection.rollback)()
                    with observer.cursor() as cursor:
                        cursor.execute('SELECT COUNT(*) FROM OWNED_CONTRACT')
                        count = cursor.fetchone()[0]
                    observer.rollback()
                    assert count == expected
                    outcomes.append({'commit': commit, 'rows': count})
                result['transaction_observations'] = outcomes
                metrics_path = PACKAGE / 'firebird_metrics_5_0_4.json'
                metrics = json.loads(metrics_path.read_text())
                observed = []
                for item in metrics['native_observations']:
                    if not item['source'].startswith('MON$'):
                        continue
                    with connection.cursor() as cursor:
                        cursor.execute(
                            f'SELECT FIRST 1 "{item["native_name"]}" '
                            f'FROM "{item["source"]}"')
                        cursor.fetchone()
                    observed.append(item['observation_id'])
                connection.rollback()
                result['monitoring_observation_ids'] = sorted(observed)
                result['provider_compiled_create'] = True
                from tools.firebird_profiler_native import qualify as qualify_profiler
                result['profiling_statistics'] = qualify_profiler(connection, client, route)
                from tools.firebird_events_native import qualify as qualify_events
                result['native_events'] = qualify_events(connection, client, route)
            finally:
                if observer is not None:
                    client.close_session(observer)
                client.close_session(connection)
                provider.close()
                provider = None
            result['all_client_handles_released'] = not client._connections
            if require_activation:
                provider = embedded.create_provider(
                    context, _permissions(context, EndpointSecretService()))
                owners.callback(provider.close)
                discovered = provider.discover_endpoint({'route': route})
                provider.close()
                context = _verified_context(context, discovered)
                provider = embedded.create_provider(
                    context, _permissions(context, EndpointSecretService()))
                owners.callback(provider.close)
                assert provider.engine_contract_descriptor()['state'] == (
                    'passed')
                catalog = provider.visual_admin_descriptor()
                table = next(item for item in catalog['objects']
                             if item['resource_kind'] == 'table')
                create = next(item for item in table['operations']
                              if item['operation_id'] == 'create')
                assert create['execution_available']
                _apply_editor(provider, route, 'table', 'create', {
                    'name': 'OWNED_ACTIVATED', 'columns': [
                        {'name': 'ID', 'column_mode': 'STORED',
                         'data_type': 'INTEGER'}]})
                resources = provider.list_resources({'route': route})
                assert any(item['resource_kind'] == 'table' and
                           item['display_name'] == 'OWNED_ACTIVATED'
                           for item in resources)
                assert not any(item['resource_kind'] in {
                    'server', 'service-operation'} for item in
                    catalog['objects'])
                provider.close()
                assert not provider.client._connections
                provider = None
                result['activated_editor_execution'] = True
    except Exception as error:
        result['failures'].append({
            'type': type(error).__name__,
            'locations': [{'file': Path(frame.filename).name,
                           'line': frame.lineno}
                          for frame in traceback.extract_tb(
                              error.__traceback__)]})
    finally:
        if provider is not None:
            provider.close()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        result['owned_state_removed'] = root is not None and not root.exists()
        result['source_runtime_unchanged'] = (
            _runtime_fingerprint(runtime_source) == before)
        result['complete'] = bool(
            not result['failures'] and result['owned_state_removed'] and
            result['source_runtime_unchanged'] and
            result.get('all_client_handles_released'))
        (evidence / 'summary.json').write_text(
            json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--require-activation', action='store_true')
    args = parser.parse_args()
    result = qualify(args.runtime_root.resolve(), args.evidence_root,
                     require_activation=args.require_activation)
    raise SystemExit(0 if result['complete'] else 1)

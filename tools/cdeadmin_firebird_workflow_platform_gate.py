"""Portable native workflow inventory in independently owned fixture databases."""
import argparse
import importlib
import json
import os
from pathlib import Path, PureWindowsPath, PurePosixPath
import sys
from types import SimpleNamespace
import uuid

import config
from pgadmin.cdeadmin.providers.firebird.provider import (
    _create_client, _database_create_arguments, _configure_client_library)
from pgadmin.cdeadmin.providers.firebird.connection_strings import database_dsn
from pgadmin.cdeadmin.security.secrets import SecretLease
from tools.firebird_release_evidence import WORKFLOWS, source_snapshot


def qualify(route, directory, evidence, *, password=None, path_style='posix', only=None):
    import firebird.driver as native
    evidence = Path(evidence)
    evidence.mkdir(parents=True, exist_ok=False)
    before = source_snapshot()
    checks = []
    path_type = PureWindowsPath if path_style == 'windows' else PurePosixPath
    parent = path_type(directory)
    if not parent.is_absolute() or str(parent) == parent.anchor:
        raise ValueError('Use an absolute dedicated fixture directory')
    if any(key in route for key in ('database', 'password', 'principal_reference', 'credential_reference_id')):
        raise ValueError('Use a credential-free route without an existing database')
    embedded = route.get('attachment_mode') == 'embedded'
    if embedded and password is not None:
        raise ValueError('Embedded mode does not use a password')
    _configure_client_library(native)
    for name in ((only,) if only else WORKFLOWS):
        item = {'check': name, 'status': 'failed', 'owned_databases_removed': False,
                'handles_released': False}
        target = evidence / name
        target.mkdir()
        permissions = SimpleNamespace(require=lambda *_: True,
                                     acquire_secret=lambda *_: SecretLease(password))
        if embedded:
            from pgadmin.cdeadmin.providers.firebird.embedded_provider import PROFILE, ADMINISTRATION
            client = _create_client(permissions, attachment_mode='embedded',
                                    profile=PROFILE, administration=ADMINISTRATION)
        else:
            client = _create_client(permissions, attachment_mode='network')
        handles = []
        routes = []
        failures = []
        try:
            for label in ('source', 'destination'):
                selected = dict(route, database=str(parent / ('sr_' + uuid.uuid4().hex + '.fdb')))
                if embedded:
                    selected['filesystem_root'] = str(parent)
                else:
                    selected.update(credential_reference_id='owned-platform-secret',
                                    principal_reference='owned-platform-principal')
                args = _database_create_arguments(selected, database_dsn(selected['database'],
                    selected.get('host'), selected.get('port'), selected.get('protocol')),
                    {'default_charset': 'UTF8'}, native)
                handle = client.config.database_creator(**args, **({'password': password} if password is not None else {}))
                client._connections.append(handle)
                handles.append(handle); routes.append(selected)
            connection, destination = handles
            module = importlib.import_module('tools.firebird_' + name + '_native')
            if name in {'editor', 'profiler', 'test_data', 'registration'}:
                proof = module.qualify(connection, client, routes[0])
            elif name == 'events':
                proof = module.qualify(connection, client, routes[0], disconnect=not embedded)
            elif name == 'blob_editor':
                proof = module.qualify(connection, client)
            elif name == 'data_export':
                proof = module.qualify(connection, routes[0], password, destination, routes[1])
            elif name == 'metadata_search':
                proof = module.qualify(connection, destination)
            elif name == 'ddn_sql':
                proof = module.qualify(native, connection, routes[0], password, target, Path(directory))
                proof['passed'] = proof.get('native_isql_replay') is True
            elif name == 'recreate':
                from tools.firebird_registration_native import retain_recreated
                replacement = str(parent / ('recreate_' + uuid.uuid4().hex + '.fdb'))
                proof = module.qualify(client, routes[0], password, path=replacement,
                    on_created=lambda path: retain_recreated(routes[0], path))
            else:
                proof = module.qualify(connection)
            assert proof.get('passed') is True, 'Native workflow proof incomplete'
            item.update(status='passed', proof=proof)
        except Exception as error:
            item.update(error_type=type(error).__name__)
            import traceback
            item['locations'] = [{'file': Path(frame.filename).name, 'line': frame.lineno}
                                 for frame in traceback.extract_tb(error.__traceback__)]
        finally:
            removed = []
            for handle in reversed(handles):
                try:
                    if handle.main_transaction.is_active():
                        handle.rollback()
                    handle.drop_database()
                    removed.append(True)
                    client.close_session(handle)
                except Exception as error:
                    failures.append(type(error).__name__);removed.append(False)
            try:
                client.close()
            except Exception as error:
                failures.append(type(error).__name__)
            item['owned_databases_removed'] = len(removed) == 2 and all(removed)
            item['handles_released'] = not client._connections
            if failures:
                item['cleanup_errors'] = failures;item['status'] = 'failed'
            if not item['owned_databases_removed'] or not item['handles_released']:
                item['status'] = 'failed'
            (target / 'receipt.json').write_text(json.dumps(item, indent=2) + '\n', encoding='utf-8')
        checks.append(item)
        print(json.dumps({'workflow': name, 'status': item['status']}), flush=True)
    after = source_snapshot()
    result = {'schema': 'cdeadmin.firebird-workflow-platform-proof.v1',
              'source': before, 'source_unchanged': before['sha256'] == after['sha256'],
              'attachment_mode': 'embedded' if embedded else 'network', 'checks': checks,
              'complete': all(item['status'] == 'passed' for item in checks) and before['sha256'] == after['sha256']}
    (evidence / 'summary.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def run(route, directory, evidence, *, password=None, path_style='posix'):
    """A native crash or hang in one workflow must preserve the rest's inventory."""
    from tools.development.native import command
    evidence = Path(evidence)
    if any(key in route for key in ('database', 'password', 'principal_reference', 'credential_reference_id')):
        raise ValueError('Use a credential-free route without an existing database')
    evidence.mkdir(parents=True, exist_ok=False)
    before = source_snapshot()
    route_file = evidence / 'route.json'
    route_file.write_text(json.dumps(route, indent=2) + '\n', encoding='utf-8')
    env = dict(os.environ, PYTHONFAULTHANDLER='1')
    if password is not None:
        env['CDEADMIN_OWNED_WORKFLOW_PASSWORD'] = password
    checks = []
    for name in WORKFLOWS:
        item = {'check': name, 'status': 'failed', 'owned_databases_removed': False,
                'handles_released': False}
        target = evidence / name
        args = [sys.executable, '-X', 'faulthandler', '-m',
                'tools.cdeadmin_firebird_workflow_platform_gate', '--route-json', route_file,
                '--fixture-directory', directory, '--path-style', path_style,
                '--evidence', target, '--case', name]
        if password is not None:
            args += ['--password-env', 'CDEADMIN_OWNED_WORKFLOW_PASSWORD']
        process_error = None
        try:
            command(args, env=env, log=evidence / (name + '.log'), timeout=300)
        except Exception as error:
            process_error = type(error).__name__
        try:
            native = json.loads((target / 'summary.json').read_text(encoding='utf-8'))
            observed = native['checks']
            if (len(observed) == 1 and observed[0]['check'] == name and
                    native['source_unchanged'] is True and native['source']['sha256'] == before['sha256']):
                item = observed[0]
                item['native_process_receipt'] = name + '/summary.json'
        except (OSError, ValueError, KeyError, TypeError):
            item['native_receipt_unavailable'] = True
        if process_error:
            item.update(status='failed', native_process_error=process_error)
        checks.append(item)
    after = source_snapshot()
    result = {'schema': 'cdeadmin.firebird-workflow-platform-proof.v1', 'source': before,
              'source_unchanged': before['sha256'] == after['sha256'],
              'attachment_mode': 'embedded' if route.get('attachment_mode') == 'embedded' else 'network',
              'checks': checks, 'complete': all(item['status'] == 'passed' for item in checks)
              and before['sha256'] == after['sha256']}
    (evidence / 'summary.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route-json', type=Path, required=True)
    parser.add_argument('--fixture-directory', required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--password-env')
    parser.add_argument('--case', choices=WORKFLOWS, help='One owned child process within the complete inventory')
    parser.add_argument('--path-style', choices=('windows', 'posix'), default='windows' if os.name == 'nt' else 'posix')
    args = parser.parse_args()
    route = json.loads(args.route_json.read_text(encoding='utf-8'))
    password = os.environ[args.password_env] if args.password_env else None
    if args.case:
        import faulthandler
        faulthandler.dump_traceback_later(120, repeat=True)
        receipt = qualify(route, args.fixture_directory, args.evidence, password=password,
                          path_style=args.path_style, only=args.case)
    else:
        receipt = run(route, args.fixture_directory, args.evidence, password=password, path_style=args.path_style)
    raise SystemExit(0 if receipt['complete'] else 1)

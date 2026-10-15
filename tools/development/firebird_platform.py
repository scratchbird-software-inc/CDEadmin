"""Qualify native Firebird on its actual host with owned runtime/server state."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools/development')]
import config
from tools.development.native import command
from tools.development import native_fixtures
from tools.firebird_release_evidence import source_snapshot, host_id, binary_identity, artifacts, WORKFLOWS


def library(runtime):
    return runtime / ('fbclient.dll' if os.name == 'nt' else
                      'lib/libfbclient.dylib' if platform.system() == 'Darwin' else 'lib/libfbclient.so.5.0.4')


def run_mode(mode, route, directory, runtime, evidence, password, *, workflows, codecs):
    target = evidence / mode
    target.mkdir()
    route_file = target / 'route.json'
    route_file.write_text(json.dumps(route, indent=2) + '\n', encoding='utf-8')
    env = dict(os.environ, FIREBIRD=str(runtime), FIREBIRD_LOCK=str(runtime / 'lock'),
               PYTHONFAULTHANDLER='1',
               CDEADMIN_FIREBIRD_CLIENT_LIBRARY=str(library(runtime)))
    # Fresh workflow processes need the same application import boundary as
    # this runner. A caller's activated venv does not add web/ to sys.path.
    env['PYTHONPATH'] = os.pathsep.join(value for value in (
        str(ROOT / 'web'), str(ROOT), env.get('PYTHONPATH')) if value)
    for key in ('ISC_USER', 'ISC_PASSWORD', 'ISC_DATABASE', 'ISC_ROLE'):
        env.pop(key, None)
    if password is not None:
        env['CDEADMIN_OWNED_FIXTURE_PASSWORD'] = password
    else:
        env.pop('CDEADMIN_OWNED_FIXTURE_PASSWORD', None)
    checks = []
    identity = binary_identity(library(runtime))
    style = 'windows' if os.name == 'nt' else 'posix'
    args = [sys.executable, '-m', 'tools.cdeadmin_firebird_driver_platform_gate',
            '--route-json', route_file, '--fixture-directory', directory,
            '--server-path-style', style, '--client-library', library(runtime),
            '--evidence', target / 'driver']
    if password is not None:
        args += ['--password-env', 'CDEADMIN_OWNED_FIXTURE_PASSWORD']
    if codecs:
        args += ['--exhaustive-codecs']
    commands = [('driver', args)]
    if workflows:
        args = [sys.executable, '-m', 'tools.cdeadmin_firebird_workflow_platform_gate',
                '--route-json', route_file, '--fixture-directory', directory,
                '--path-style', style, '--evidence', target / 'workflows']
        if password is not None:
            args += ['--password-env', 'CDEADMIN_OWNED_FIXTURE_PASSWORD']
        commands.append(('workflows', args))
    for name, args in commands:
        item = {'check': name, 'status': 'failed'}
        try:
            command(args, env=env, log=target / (name + '.log'), timeout=7200)
            item['status'] = 'passed'
        except Exception as error:
            item['error_type'] = type(error).__name__
        checks.append(item)
    return {'mode': mode, 'complete': all(item['status'] == 'passed' for item in checks),
            'checks': checks, 'client_binary': identity,
            'driver_receipt': mode + '/driver/summary.json',
            'workflow_receipt': mode + '/workflows/summary.json' if workflows else None,
            'workflows': list(WORKFLOWS) if workflows else [], 'exhaustive_codecs': codecs}


def qualify(runtime_source, evidence, *, codecs=True, workflows=True):
    runtime_source, evidence = Path(runtime_source).resolve(), Path(evidence).resolve()
    if evidence.is_relative_to(ROOT):
        raise ValueError('Keep qualification evidence outside the repository')
    evidence.mkdir(parents=True, exist_ok=False)
    source = source_snapshot()
    template_hash = hashlib.sha256((runtime_source / 'security5.fdb').read_bytes()).hexdigest()
    native_fixtures.STATE = runtime_source.parent
    # The fixture resolves STATE/firebird; a dedicated catalog alias avoids
    # changing or installing the supplied runtime or existing server services.
    modes = []
    errors = []
    try:
        command([sys.executable, ROOT / 'tools/development/native_verify.py', '--child', 'imports',
                 '--evidence', evidence], log=evidence / 'dependency-imports.log', timeout=300)
    except Exception as error:
        errors.append({'scope': 'native-dependency-imports', 'error_type': type(error).__name__})
    cleanup = True
    try:
        with tempfile.TemporaryDirectory(prefix='owned-platform-') as temporary:
            root = Path(temporary)
            catalog = root / 'kits'
            catalog.mkdir()
            try:
                (catalog / 'firebird').symlink_to(runtime_source, target_is_directory=True)
            except OSError:
                # Standard Windows accounts may lack symlink privileges.
                shutil.copytree(runtime_source, catalog / 'firebird')
            native_fixtures.STATE = catalog
            network = root / 'network';network.mkdir()
            network_evidence = evidence / 'server';network_evidence.mkdir()
            try:
                with native_fixtures.firebird(network, network_evidence, dict(os.environ),
                                              platform_routes=True) as (specification, password):
                    runtime = network / 'runtime'
                    modes.append(run_mode('network', specification['route'], network, runtime,
                                          evidence, password, workflows=workflows, codecs=codecs))
                    if os.name == 'nt':
                        route = dict(specification['route'], protocol='XNET')
                        route.pop('host');route.pop('port')
                        modes.append(run_mode('xnet', route, network, runtime, evidence,
                                              password, workflows=False, codecs=False))
                        route = dict(specification['route'], trusted_auth=True,
                                     auth_plugin_list='Win_Sspi', wire_crypt='Enabled')
                        route.pop('user')
                        modes.append(run_mode('win-sspi', route, network, runtime, evidence,
                                              None, workflows=False, codecs=False))
            except Exception as error:
                errors.append({'scope': 'network-server', 'error_type': type(error).__name__})
            embedded = root / 'embedded';embedded.mkdir()
            runtime = embedded / 'runtime'
            shutil.copytree(runtime_source, runtime)
            (runtime / 'lock').mkdir(exist_ok=True)
            (runtime / 'firebird.conf').write_text('Providers = Engine13\nSecurityDatabase = ' +
                                                  str(runtime / 'security5.fdb') + '\n', encoding='utf-8')
            (runtime / 'databases.conf').write_text('', encoding='utf-8')
            try:
                modes.append(run_mode('embedded', {'attachment_mode': 'embedded', 'user': 'SYSDBA',
                    'charset': 'UTF8'}, embedded, runtime, evidence, None, workflows=workflows, codecs=codecs))
            except Exception as error:
                errors.append({'scope': 'embedded', 'error_type': type(error).__name__})
        cleanup = not root.exists()
    except Exception as error:
        cleanup = False
        errors.append({'scope': 'fixture-cleanup', 'error_type': type(error).__name__})
    after = source_snapshot()
    required = {'network', 'embedded', 'xnet', 'win-sspi'} if os.name == 'nt' else {'network', 'embedded'}
    result = {'schema': 'cdeadmin.firebird-platform-release.v1', 'host': host_id(),
              'python': platform.python_version(), 'source': source,
              'source_unchanged': source['sha256'] == after['sha256'],
              'runtime_template_unchanged': template_hash == hashlib.sha256((runtime_source / 'security5.fdb').read_bytes()).hexdigest(),
              'modes': modes, 'failures': errors, 'owned_state_removed': cleanup,
              'github': {key: os.environ.get(key) for key in
                         ('GITHUB_REPOSITORY', 'GITHUB_SHA', 'GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT')},
              'scope': 'native driver, codecs and portable backend workflows; human forms and signed packages separate'}
    result['complete'] = bool(cleanup and not errors and result['source_unchanged'] and
        result['runtime_template_unchanged'] and {item['mode'] for item in modes} == required and
        all(item['complete'] for item in modes) and codecs and workflows)
    result['artifacts'] = artifacts(evidence)
    (evidence / 'platform.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'host': result['host'], 'complete': result['complete'],
                      'modes': [(item['mode'], item['complete']) for item in modes], 'failures': errors}), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--quick-codecs', action='store_true', help='Diagnostic only; cannot qualify a release')
    parser.add_argument('--driver-only', action='store_true', help='Native codec/transport diagnosis; cannot qualify a release')
    args = parser.parse_args()
    result = qualify(args.runtime_root, args.evidence, codecs=not args.quick_codecs, workflows=not args.driver_only)
    raise SystemExit(0 if result['complete'] else 1)

"""Run and reconcile every declared Firebird network administration task.

Native gates use isolated exact containers or owned loopback servers. This
qualifies task execution; browser/form and whole-product acceptance are separate.
Logs and receipts must live outside the implementation repository.
"""

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SPECIALIZED = (
    'mapping_matrix', 'character_metadata', 'sequences', 'packages',
    'object_privileges', 'database_storage', 'shadows', 'external_functions',
    'blob_filters', 'functions', 'procedures', 'triggers', 'exceptions',
    'user_replacement', 'table_replacement', 'views', 'view_insert',
    'view_mutability',
)
BUILD_ROOT = frozenset({
    'sequences', 'packages', 'object_privileges', 'database_storage',
    'shadows', 'external_functions', 'blob_filters',
})
PROFILE_GATES = ('columns', 'admin_mapping', 'privileges', 'column_order')


def bindings():
    paths = set((ROOT / 'web/pgadmin/cdeadmin').rglob('*.py'))
    paths.update((ROOT / 'web/pgadmin/cdeadmin/providers/firebird').glob('*.json'))
    paths.update((ROOT / 'tools').glob('cdeadmin_firebird_*.py'))
    paths.update((ROOT / 'tools').glob('firebird_*.py'))
    paths.add(ROOT / 'tools/cdeadmin_relational_provider_live_verify.py')
    return {str(path.relative_to(ROOT)): hashlib.sha256(
        path.read_bytes()).hexdigest() for path in sorted(paths)}


def declared_tasks():
    document = json.loads((ROOT / 'web/pgadmin/cdeadmin/providers/firebird/'
                           'firebird_dialect_5_0_4.json').read_text())
    return {item['task_id'] for item in document['task_templates']}


def task_evidence(document):
    """Read explicit live receipts, never infer tasks from native SQL text."""
    result = set()
    if isinstance(document, dict):
        for key, value in document.items():
            if (key.startswith('visual_admin.') and isinstance(value, dict)
                    and value.get('live_execution') == 'passed'):
                result.add(key)
            result.update(task_evidence(value))
    elif isinstance(document, list):
        for value in document:
            result.update(task_evidence(value))
    return result


def qualified_tasks(name, document, exit_code):
    if name == 'generic':
        valid = (
            document.get('engine_id') == 'firebird' and
            document.get('exact_profile') == '5.0.4' and
            document.get('server_stopped') is True and
            document.get('source_runtime_modified') is False and
            not document.get('error_type') and
            not document.get('object_experience_evidence', {}).get(
                'operation_failures') and
            all(document.get('categories', {}).get(key) == 'passed'
                for key in ('admin', 'fault', 'language_api', 'resource',
                            'result', 'security', 'transaction'))
        )
        return (set(document.get('qualified_dialect_task_ids', []))
                if valid and exit_code in (0, 1) else None)
    passed = document.get('complete', document.get(
        'passed', document.get('status') == 'passed')) is True
    if (exit_code != 0 or not passed or document.get('failures') or
            document.get('engine_version') != '5.0.4'):
        return None
    return task_evidence(document)


def profile_gate(name, runtime_root, evidence_root):
    from tools.cdeadmin_firebird_local_fixture import run_local, _route_arguments
    from pgadmin.cdeadmin.providers.firebird.provider import _create_client
    from pgadmin.cdeadmin.providers.relational_admin import RelationalAdministration
    from pgadmin.cdeadmin.security.secrets import SecretLease

    observed, nested = {}, {}
    original = RelationalAdministration.apply

    def apply(self, client, request, connection=None):
        result = original(self, client, request, connection=connection)
        action, kind = request['command_preview']['operation'].rsplit('_', 1)
        observed[f'visual_admin.{kind}.{action}'] = {
            'live_execution': 'passed', 'provider_apply_returned': True,
        }
        return result

    def check(native, admin, route, accounts, evidence, temporary):
        user, password = accounts['Srp'][0]
        admin.execute_immediate(
            'ALTER USER ' + user + ' GRANT ADMIN ROLE USING PLUGIN Srp')
        admin.commit()
        selected = {**route, 'user': user, 'credential_reference_id': name,
                    'principal_reference': user}
        if name == 'column_order':
            from tools.firebird_column_order_native import qualify
            selected['database'] = str(temporary / 'column_order.fdb')
            connection = native.create_database(
                password=password, **_route_arguments(selected, native))
            client = _create_client(SimpleNamespace(
                acquire_secret=lambda *_: SecretLease(password)))
            try:
                nested.update(qualify(connection, client, selected))
                nested['complete'] = True
            finally:
                connection.close()
                client.close()
        else:
            profile = temporary / 'profiles.json'
            descriptor = os.open(profile, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                                 0o600)
            with os.fdopen(descriptor, 'w') as stream:
                json.dump({'profiles': [{
                    'engine': 'firebird', **selected, 'password': password,
                }]}, stream)
            try:
                module = importlib.import_module(
                    'tools.cdeadmin_firebird_' + name + '_gate')
                nested.update(module.run(profile))
            finally:
                profile.unlink()
        assert nested.get('complete', nested.get(
            'passed', nested.get('status') == 'passed')) is True
        assert not nested.get('failures')

    RelationalAdministration.apply = apply
    try:
        result = run_local(runtime_root, evidence_root / 'fixture', check)
    finally:
        RelationalAdministration.apply = original
    result['native_checks'] = nested
    result['task_evidence'] = observed if result['complete'] else {}
    (evidence_root / 'result.json').write_text(
        json.dumps(result, indent=2) + '\n')
    return result


def run(runtime_root, source_root, evidence_root, ddn_work):
    if sys.version_info < (3, 14):
        raise ValueError('Current network qualification requires Python 3.14+')
    if importlib.metadata.version('firebird-driver') != '1.10.11':
        raise ValueError('Firebird qualification requires driver 1.10.11')
    evidence_root = evidence_root.resolve()
    if evidence_root == ROOT or ROOT in evidence_root.parents:
        raise ValueError('Evidence must be outside the implementation repository')
    evidence_root.mkdir(parents=True, exist_ok=False)
    before = bindings()
    expected = declared_tasks()
    result = {
        'schema': 'cdeadmin.firebird-network-tasks-proof.v1',
        'complete': False, 'engine_version': '5.0.4',
        'python': sys.version, 'driver_version': importlib.metadata.version(
            'firebird-driver'), 'source_bindings': before, 'gates': [],
        'source_revision': subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'qualified_task_ids': [], 'missing_task_ids': sorted(expected),
    }
    jobs = ['generic', *SPECIALIZED, *PROFILE_GATES, 'role_membership']
    env = dict(os.environ, PYTHONPATH=str(ROOT) + ':' + str(ROOT / 'tools') +
               ':' + str(ROOT / 'web'),
               LD_LIBRARY_PATH=str(runtime_root / 'lib'),
               CDEADMIN_FIREBIRD_CLIENT_LIBRARY=str(
                   runtime_root / 'lib/libfbclient.so.5.0.4'))
    covered = set()
    for name in jobs:
        directory = evidence_root / name
        directory.mkdir()
        output = directory / 'result.json'
        if name in PROFILE_GATES:
            command = [sys.executable, str(Path(__file__).resolve()),
                       '--worker-profile', name, '--runtime-root',
                       str(runtime_root), '--evidence-root', str(directory)]
        elif name == 'generic':
            command = [sys.executable, str(ROOT / 'tools/'
                       'cdeadmin_firebird_object_live_orchestrator.py'),
                       '--runtime-source', str(runtime_root), '--output',
                       str(output), '--object-output',
                       str(directory / 'objects.json'), '--server-log',
                       str(directory / 'server.log')]
        elif name == 'role_membership':
            command = [sys.executable, str(ROOT / 'tools/'
                       'cdeadmin_firebird_role_membership_gate.py'),
                       '--runtime-root', str(runtime_root), '--evidence-root',
                       str(directory / 'fixture')]
            output = directory / 'fixture/summary.json'
        else:
            command = [sys.executable, str(ROOT / 'tools' / (
                'cdeadmin_firebird_' + name + '_gate.py')), '--output', str(output)]
            if name in BUILD_ROOT:
                command.extend(['--build-root', str(directory / 'build')])
            if name in {'external_functions', 'blob_filters'}:
                command.extend(['--source-root', str(source_root)])
        print('START ' + name, flush=True)
        started = time.monotonic()
        gate = {'name': name, 'receipt': str(output), 'complete': False}
        with (directory / 'run.log').open('wb') as log:
            refreshed = subprocess.run([
                sys.executable, str(ROOT / 'tools/refresh_ddn.py'), '--work',
                str(ddn_work)], cwd=ROOT, env=env, stdout=log,
                stderr=subprocess.STDOUT)
            gate['ddn_refresh_exit_code'] = refreshed.returncode
            if refreshed.returncode == 0:
                ddn_manifest = ROOT / (
                    'web/pgadmin/static/vendor/ddn/current/resource-manifest.json')
                gate['ddn_manifest_sha256'] = hashlib.sha256(
                    ddn_manifest.read_bytes()).hexdigest()
                completed = subprocess.run(command, cwd=ROOT, env=env,
                                           stdout=log, stderr=subprocess.STDOUT)
                gate['exit_code'] = completed.returncode
                if output.is_file():
                    raw = output.read_bytes()
                    gate['receipt_sha256'] = hashlib.sha256(raw).hexdigest()
                    try:
                        tasks = qualified_tasks(name, json.loads(raw),
                                                completed.returncode)
                    except (ValueError, TypeError, AttributeError):
                        tasks = None
                        gate['invalid_receipt'] = True
                    gate['complete'] = tasks is not None
                    gate['qualified_task_ids'] = sorted(tasks or ())
                    covered.update(tasks or ())
        gate['seconds'] = round(time.monotonic() - started, 2)
        result['gates'].append(gate)
        result['qualified_task_ids'] = sorted(expected & covered)
        result['missing_task_ids'] = sorted(expected - covered)
        (evidence_root / 'summary.json').write_text(
            json.dumps(result, indent=2) + '\n')
        print('DONE ' + name + ' ' + str(gate['complete']), flush=True)
    result['source_unchanged'] = before == bindings()
    result['ddn_snapshot_unchanged'] = len({
        gate.get('ddn_manifest_sha256') for gate in result['gates']}) == 1
    result['complete'] = (result['source_unchanged'] and
                          result['ddn_snapshot_unchanged'] and
                          not result['missing_task_ids'] and
                          all(gate['complete'] for gate in result['gates']))
    (evidence_root / 'summary.json').write_text(
        json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', required=True, type=Path)
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--evidence-root', required=True, type=Path)
    parser.add_argument('--ddn-work', type=Path)
    parser.add_argument('--worker-profile', choices=PROFILE_GATES)
    options = parser.parse_args()
    if options.worker_profile:
        result = profile_gate(options.worker_profile,
                              options.runtime_root.resolve(), options.evidence_root)
    else:
        if not options.source_root or not options.ddn_work:
            parser.error('--source-root and --ddn-work are required')
        result = run(options.runtime_root.resolve(), options.source_root.resolve(),
                     options.evidence_root, options.ddn_work)
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

"""Reconcile explicit live receipts for every declared MySQL administration task."""
import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web')]
# Owned-server tools whose application run sends each operation through the
# authenticated visual-administration API on both the pure and C interfaces.
APPLICATION_TOOLS = ('xa', 'page_tracking', 'rewriter', 'key_cache', 'key_cache_lifecycle', 'instance',
                     'failover', 'user_keys', 'spatial_reference', 'foreign_server',
                     'column_masking', 'sdi_import', 'server_control',
                     'group9_completion')
JOBS = ('generic', 'constraints', 'object_changes', 'partition', 'role',
        'resource_group', 'tablespace', 'server_operations', 'replication', 'group_replication',
        *APPLICATION_TOOLS)


DDN_MANIFEST = 'web/pgadmin/static/vendor/ddn/current/resource-manifest.json'


def ddn_revision():
    return json.loads((ROOT / DDN_MANIFEST).read_text())['source']['revision']


def bindings():
    files = set((ROOT / 'web/pgadmin/cdeadmin').rglob('*.py'))
    files.update((ROOT / 'web/pgadmin/cdeadmin/providers/mysql_family').glob('mysql*.json'))
    files.update((ROOT / 'tools').glob('*mysql*.py'))
    files.add(ROOT / 'tools/cdeadmin_relational_provider_live_verify.py')
    values = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
    # The DDN refresh before each job can consume a newer upstream revision
    # whose vendored files are identical. Bind every manifest field (file and
    # artifact hashes, release hash) except that revision; run() records each
    # revision consumed.
    manifest = json.loads((ROOT / DDN_MANIFEST).read_text())
    manifest['source'].pop('revision')
    values[DDN_MANIFEST] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    return values


def declared():
    source = ROOT / 'web/pgadmin/cdeadmin/providers/mysql_family/mysql_dialect_9_7_0.json'
    return {row['task_id'] for row in json.loads(source.read_text())['task_templates']}


def reconcile(name, receipt, exit_code):
    if name == 'generic':
        valid = (exit_code in (0, 1) and receipt.get('engine_id') == 'mysql' and
                 receipt.get('exact_profile') == '9.7.0' and receipt.get('server_stopped') is True and
                 not receipt.get('error_type') and not receipt.get('object_experience_evidence', {}).get('operation_failures') and
                 all(receipt.get('categories', {}).get(k) == 'passed' for k in
                     ('admin', 'fault', 'language_api', 'resource', 'result', 'security', 'transaction')))
        return set(receipt.get('qualified_dialect_task_ids', [])) if valid else None
    if (exit_code != 0 or receipt.get('passed') is not True or receipt.get('failures') or
            receipt.get('engine_version') != '9.7.0' or receipt.get('owned_cleanup_confirmed') is not True):
        return None
    return {key for key, value in receipt.get('task_evidence', {}).items()
            if key.startswith('visual_admin.') and value.get('live_execution') == 'passed'}


def application_evidence(proof, fixtures, expected):
    """Translate an application tool's receipts into task evidence.

    A task passes only when its operation was acknowledged through the API on
    both interfaces and names exactly one declared task (by resource kind
    and operation when the receipt gives the kind)."""
    application = proof.get('application') if isinstance(proof.get('application'), dict) else {}
    receipts = application.get('operations') or application.get('receipts') or []
    interfaces = {}
    for receipt in receipts:
        if any(key.endswith('acknowledged') and value is True for key, value in receipt.items()):
            interfaces.setdefault((receipt.get('resource_kind'), receipt.get('operation')), set()).add(receipt.get('use_pure'))
    evidence = {}
    for (kind, operation), selected in interfaces.items():
        # A receipt naming its resource kind closes that exact task.
        tasks = ([task for task in expected if task == f'visual_admin.{kind}.{operation}'] if kind else
                 [task for task in expected if task.split('.', 2)[-1] == operation])
        if selected == {True, False} and len(tasks) == 1:
            evidence[tasks[0]] = {'live_execution': 'passed', 'interfaces': ['pure', 'c'],
                                  'operation': operation}
    # Every owned fixture the tool started must be the checked version and stopped.
    versions = {fixture.get('engine_version') for fixture in fixtures}
    return {'passed': proof.get('complete') is True and application.get('complete') is True and bool(evidence),
            'failures': [], 'engine_version': versions.pop() if len(versions) == 1 else None,
            'owned_cleanup_confirmed': bool(fixtures) and
                                       (proof.get('owned_server_stopped') is True or proof.get('owned_servers_stopped') is True) and
                                       all(fixture.get('owned_server_stopped') is True for fixture in fixtures),
            'task_evidence': evidence, 'receipt_count': len(receipts)}


def worker(name, output):
    import config  # noqa: F401
    if name in APPLICATION_TOOLS:
        module = importlib.import_module('tools.cdeadmin_mysql_' + name + '_qualification')
        tool = output / 'tool'
        try:
            module.qualify(tool, application=True)
        finally:
            found = next((tool / name for name in ('summary.json', 'proof.json') if (tool / name).is_file()), None)
            proof = json.loads(found.read_text()) if found else {}
            fixtures = [json.loads(path.read_text()) for path in sorted(tool.rglob('fixture.json'))]
            receipt = application_evidence(proof, fixtures, declared())
            (output / 'summary.json').write_text(json.dumps(receipt, indent=2) + '\n')
        return
    from tools.mysql_qualification_support import server
    from tools.cdeadmin_mysql_family_object_live_orchestrator import _run
    if name == 'group_replication':
        module = importlib.import_module('tools.cdeadmin_mysql_group_replication_qualification')
        module.qualify(output)
        receipt = json.loads((output / 'summary.json').read_text())
        receipt['owned_cleanup_confirmed'] = (receipt.get('owned_servers_stopped') is True and
                                                receipt.get('owned_network_removed') is True)
    elif name == 'replication':
        network = 'sr-replica-' + secrets.token_hex(8)
        _run(['docker', 'network', 'create', network])
        cleaned = False
        try:
            with server(output / 'source', network=network, server_id=101) as (source, host, first):
                with server(output / 'replica', network=network, server_id=102) as (replica, _, second):
                    module = importlib.import_module('tools.cdeadmin_mysql_replication_qualification')
                    module.qualify(source, replica, host, output)
            cleaned = first['owned_server_stopped'] and second['owned_server_stopped']
        finally:
            cleaned = _run(['docker', 'network', 'rm', network], check=False).returncode == 0 and cleaned
        receipt = json.loads((output / 'summary.json').read_text())
        receipt.update(engine_version='9.7.0', owned_cleanup_confirmed=bool(cleaned))
    else:
        with server(output / 'fixture') as (options, _name, fixture):
            if name == 'role':
                path = output / 'private-route.json'
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(descriptor, 'w') as stream:
                    json.dump(options, stream)
                try:
                    subprocess.run([sys.executable, str(ROOT / 'tools/cdeadmin_mysql_role_qualification.py'),
                                    '--connection-json', str(path), '--output-root', str(output)], check=True)
                finally:
                    path.unlink()
            else:
                module = importlib.import_module('tools.cdeadmin_mysql_' + name + '_qualification')
                module.qualify(options, output)
        receipt = json.loads((output / 'summary.json').read_text())
        receipt.update(engine_version=fixture['engine_version'], owned_cleanup_confirmed=fixture['owned_server_stopped'])
    (output / 'summary.json').write_text(json.dumps(receipt, indent=2) + '\n')


def run(output, ddn_work, mysqlsh=None):
    if sys.version_info < (3, 14) or importlib.metadata.version('mysql-connector-python') != '26.7.0':
        raise ValueError('Qualification requires Python 3.14+ and Connector/Python 26.7.0')
    output = output.resolve()
    if ROOT == output or ROOT in output.parents:
        raise ValueError('Evidence must be outside the implementation repository')
    output.mkdir(parents=True, exist_ok=False)
    before, expected, covered = bindings(), declared(), set()
    result = {'schema': 'scratchrobin.mysql.tasks-proof@1', 'complete': False,
              'engine_version': '9.7.0', 'python': sys.version,
              'source_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'source_bindings': before, 'gates': [], 'missing_task_ids': sorted(expected),
              'ddn_revisions_consumed': [ddn_revision()]}
    env = {**os.environ, 'PYTHONPATH': os.pathsep.join([str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')])}
    if mysqlsh is not None:
        if not mysqlsh.is_file():
            raise ValueError('Configured MySQL Shell executable is unavailable')
        env['CDEADMIN_MYSQLSH_BINARY'] = str(mysqlsh.resolve())
        result['mysql_shell_sha256'] = hashlib.sha256(mysqlsh.read_bytes()).hexdigest()
    for name in JOBS:
        directory = output / name
        directory.mkdir()
        receipt = directory / ('result.json' if name == 'generic' else 'summary.json')
        if name == 'generic':
            command = [sys.executable, str(ROOT / 'tools/cdeadmin_mysql_family_object_live_orchestrator.py'),
                       '--engine', 'mysql', '--output', str(receipt), '--object-output', str(directory / 'objects.json'),
                       '--server-log', str(directory / 'server.log'), '--dialect-qualification']
        else:
            command = [sys.executable, str(Path(__file__).resolve()), '--worker', name, '--output', str(directory)]
        print('START ' + name, flush=True)
        started = time.monotonic()
        gate = {'name': name, 'complete': False, 'receipt': str(receipt)}
        with (directory / 'run.log').open('wb') as log:
            refreshed = subprocess.run([sys.executable, str(ROOT / 'tools/refresh_ddn.py'), '--work', str(ddn_work)],
                                       cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            gate['ddn_refresh_exit_code'] = refreshed.returncode
            if ddn_revision() != result['ddn_revisions_consumed'][-1]:
                result['ddn_revisions_consumed'].append(ddn_revision())
            if refreshed.returncode == 0:
                completed = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
                gate['exit_code'] = completed.returncode
                if receipt.is_file():
                    raw = receipt.read_bytes()
                    gate['receipt_sha256'] = hashlib.sha256(raw).hexdigest()
                    try:
                        tasks = reconcile(name, json.loads(raw), completed.returncode)
                    except (ValueError, TypeError, AttributeError):
                        tasks = None
                    gate.update(complete=tasks is not None, qualified_task_ids=sorted(tasks or ()))
                    covered.update(tasks or ())
        gate['seconds'] = round(time.monotonic() - started, 2)
        result['gates'].append(gate)
        result.update(qualified_task_ids=sorted(expected & covered), missing_task_ids=sorted(expected - covered),
                      unexpected_task_ids=sorted(covered - expected))
        (output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
        print('DONE ' + name + ' ' + str(gate['complete']), flush=True)
    result['source_unchanged'] = before == bindings()
    result['complete'] = (result['source_unchanged'] and not result['missing_task_ids'] and
                          not result['unexpected_task_ids'] and all(gate['complete'] for gate in result['gates']))
    (output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ddn-work', type=Path, default=ROOT.parent / 'ChatGPT_Codex_1_Workarea/ddn-intake')
    parser.add_argument('--worker', choices=JOBS[1:])
    parser.add_argument('--mysqlsh', type=Path)
    args = parser.parse_args()
    if args.worker:
        worker(args.worker, args.output)
    else:
        sys.exit(0 if run(args.output, args.ddn_work, args.mysqlsh)['complete'] else 1)

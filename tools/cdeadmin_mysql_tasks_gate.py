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
JOBS = ('generic', 'constraints', 'object_changes', 'partition', 'role',
        'resource_group', 'tablespace', 'server_operations', 'replication', 'group_replication')


def bindings():
    files = set((ROOT / 'web/pgadmin/cdeadmin').rglob('*.py'))
    files.update((ROOT / 'web/pgadmin/cdeadmin/providers/mysql_family').glob('mysql*.json'))
    files.update((ROOT / 'tools').glob('*mysql*.py'))
    files.add(ROOT / 'tools/cdeadmin_relational_provider_live_verify.py')
    files.add(ROOT / 'web/pgadmin/static/vendor/ddn/current/resource-manifest.json')
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


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


def worker(name, output):
    import config  # noqa: F401
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
              'source_bindings': before, 'gates': [], 'missing_task_ids': sorted(expected)}
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

"""Reconcile explicit live receipts for every declared MariaDB administration task."""
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
JOBS = ('generic', 'partitions', 'server_objects')


def bindings():
    files = set((ROOT / 'web/pgadmin/cdeadmin').rglob('*.py'))
    files.update((ROOT / 'web/pgadmin/cdeadmin/providers/mysql_family').glob('mariadb*.json'))
    files.update((ROOT / 'tools').glob('*mariadb*.py'))
    files.add(ROOT / 'tools/cdeadmin_relational_provider_live_verify.py')
    files.add(ROOT / 'web/pgadmin/static/vendor/ddn/current/resource-manifest.json')
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def declared():
    source = ROOT / 'web/pgadmin/cdeadmin/providers/mysql_family/mariadb_dialect_12_2_2.json'
    return {row['task_id'] for row in json.loads(source.read_text())['task_templates']}


def reconcile(name, receipt, exit_code):
    if name == 'generic':
        valid = (exit_code in (0, 1) and receipt.get('engine_id') == 'mariadb' and
                 receipt.get('exact_profile') == '12.2.2' and receipt.get('server_stopped') is True and
                 not receipt.get('error_type') and not receipt.get('object_experience_evidence', {}).get('operation_failures') and
                 all(receipt.get('categories', {}).get(k) == 'passed' for k in
                     ('admin', 'fault', 'language_api', 'resource', 'result', 'security', 'transaction')))
        return set(receipt.get('qualified_dialect_task_ids', [])) if valid else None
    if exit_code != 0 or receipt.get('complete') is not True or receipt.get('failures'):
        return None
    return set(receipt.get('task_sources', {}))


def run(output, ddn_work):
    if sys.version_info < (3, 14) or importlib.metadata.version('mariadb') != '1.1.14':
        raise ValueError('Qualification requires Python 3.14+ and patched Connector/Python 1.1.14')
    output = output.resolve()
    if ROOT == output or ROOT in output.parents:
        raise ValueError('Evidence must be outside the implementation repository')
    output.mkdir(parents=True, exist_ok=False)
    before, expected, covered = bindings(), declared(), set()
    result = {'schema': 'scratchrobin.mariadb.tasks-proof@1', 'complete': False,
              'engine_version': '12.2.2', 'python': sys.version,
              'source_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'source_bindings': before, 'gates': [], 'missing_task_ids': sorted(expected)}
    env = {**os.environ, 'PYTHONPATH': os.pathsep.join([str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')])}
    for name in JOBS:
        directory = output / name
        directory.mkdir()
        receipt = directory / ('result.json' if name == 'generic' else 'native/summary.json')
        if name == 'generic':
            command = [sys.executable, str(ROOT / 'tools/cdeadmin_mysql_family_object_live_orchestrator.py'),
                       '--engine', 'mariadb', '--output', str(receipt), '--object-output', str(directory / 'objects.json'),
                       '--server-log', str(directory / 'server.log'), '--dialect-qualification']
        else:
            directory.rmdir()
            command = [sys.executable, '-m', 'tools.cdeadmin_mariadb_' + name + '_qualification', '--evidence', str(directory)]
        print('START ' + name, flush=True)
        started = time.monotonic()
        gate = {'name': name, 'complete': False, 'receipt': str(receipt)}
        with (output / (name + '.log')).open('wb') as log:
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
                    if name != 'generic':
                        fixture = json.loads((directory / 'fixture.json').read_text())
                        if fixture.get('owned_server_stopped') is not True or fixture.get('engine_version') != '12.2.2':
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
    args = parser.parse_args()
    sys.exit(0 if run(args.output, args.ddn_work)['complete'] else 1)

"""Qualify native server diagnostics/live plans/shutdown on one owned server.

Run after DDN intake from an immutable capture. All fixtures and evidence live
under --evidence, outside the source tree. No existing server is shut down.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from tools.mariadb_qualification_support import server, _root_connection

ROOT = Path(__file__).resolve().parents[1]
OPERATIONS = ('inspect_engine_status', 'inspect_engine_logs', 'inspect_engine_mutex',
              'inspect_live_explain', 'inspect_live_analyze', 'shutdown_server', 'inspect_prepared_xa', 'commit_prepared_xa', 'rollback_prepared_xa',
              'inspect_key_caches', 'inspect_key_cache', 'configure_key_cache', 'release_key_cache',
              'assign_index_cache', 'preload_index_cache', 'start_all_replicas', 'stop_all_replicas',
              'reset_binary_logs', 'reset_query_cache', 'reset_default_replica')


def run(evidence):
    evidence = Path(evidence).resolve()
    if evidence == ROOT or ROOT in evidence.parents:
        raise ValueError('Qualification evidence must be outside the source tree')
    evidence.mkdir(parents=True, exist_ok=False)
    (evidence / 'native').mkdir()
    (evidence / 'tmp').mkdir()
    receipt = evidence / 'native/shutdown-request.json'
    proof = {'complete': False, 'engine': 'mariadb', 'version': '12.2.2',
             'failures': [], 'task_sources': {}, 'history_qualification': 'not run'}
    try:
        with server(evidence, native_shutdown=True) as (route, _name, fixture):
            # The tasks gate uses the exact numeric profile; retain the full
            # native version separately rather than discarding its suffix.
            fixture['engine_version_raw'] = fixture['engine_version']
            fixture['engine_version'] = fixture['engine_version'].split('-')[0]
            with _root_connection('mariadb', route['port']) as handle:
                handle.autocommit = True
                cursor = handle.cursor()
                cursor.execute('CREATE DATABASE owned_management')
                cursor.close()
            settings = dict(host=route['host'], port=route['port'], user=route['user'], database='owned_management')
            py_paths = [str(ROOT / p) for p in ('', 'web', 'tools')]
            if os.environ.get('PYTHONPATH'):
                py_paths = [p for p in os.environ['PYTHONPATH'].split(os.pathsep) if p and p not in py_paths] + py_paths
            driver_rt = Path('/home/dcalford/Sandbox/codex-work-area/cdeadmin-six-engine-implementation/mariadb-driver-runtime')
            if driver_rt.is_dir() and str(driver_rt) not in py_paths:
                py_paths.insert(0, str(driver_rt))
            env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                TMPDIR=str(evidence / 'tmp'),
                CDEADMIN_SQLITE_STARTUP_POLICY=str(evidence / 'absent-startup-policy.json'),
                PYTHONPATH=os.pathsep.join(py_paths),
                CDEADMIN_MARIADB_MANAGEMENT_TEST=json.dumps(settings),
                CDEADMIN_MARIADB_SHUTDOWN_RECEIPT=str(receipt),
                CDEADMIN_MARIADB_MANAGEMENT_EXECUTIONS=str(evidence / 'native/executions.json'))
            # SHUTDOWN is the last test in the last file. All earlier owned
            # query sessions are closed before it interrupts the process.
            tests = ['test_mariadb_server_diagnostics.py', 'test_mariadb_live_plans.py',
                     'test_mariadb_binlog_events_native.py', 'test_mariadb_prepared_xa.py',
                     'test_mariadb_key_caches.py', 'test_mariadb_all_channels.py',
                     'test_mariadb_sequence_options.py', 'test_mariadb_shutdown.py']
            command = [sys.executable, '-B', '-m', 'pytest', '-p', 'no:cacheprovider', '-q', '--tb=short',
                '--basetemp=' + str(evidence / 'pytest'), '--junitxml=' + str(evidence / 'native/tests.xml'),
                *(str(ROOT / 'tools/tests' / name) for name in tests)]
            proof['test_sources'] = {name: hashlib.sha256((ROOT / 'tools/tests' / name).read_bytes()).hexdigest() for name in tests}
            with (evidence / 'native/tests.log').open('wb') as log:
                result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            proof['test_exit_code'] = result.returncode
            if receipt.is_file():
                request = json.loads(receipt.read_text())
                fixture['native_shutdown_acknowledged'] = request.get('shutdown', {}).get('native_acknowledged') is True
                proof['shutdown_request_sha256'] = hashlib.sha256(receipt.read_bytes()).hexdigest()
            if result.returncode != 0:
                proof['failures'].append({'stage': 'native-tests', 'exit_code': result.returncode})
        proof['fixture'] = fixture
        if not fixture.get('native_process_exit_observed'):
            proof['failures'].append({'stage': 'independent-native-process-exit'})
        if not fixture.get('owned_server_stopped'):
            proof['failures'].append({'stage': 'owned-fixture-cleanup'})
        if not proof['failures']:
            executions = json.loads((evidence / 'native/executions.json').read_text())
            executions.append({'operation': 'shutdown_server', 'source': 'SHUTDOWN',
                               'native_acknowledged': fixture['native_shutdown_acknowledged']})
            for row in executions:
                if row['operation'] in OPERATIONS and row['native_acknowledged']:
                    proof['task_sources'].setdefault('visual_admin.server.' + row['operation'], []).append(row['source'])
            proof['complete'] = len(proof['task_sources']) == len(OPERATIONS)
    except Exception as error:
        proof['failures'].append({'stage': 'qualification', 'error_type': type(error).__name__})
    (evidence / 'native/summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.evidence)['complete'] else 1)

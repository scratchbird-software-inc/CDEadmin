"""Collect every existing MariaDB DDN/encoding and driver workflow failure.

Supplied estates must be disposable and authorize owned schemas and accounts.
No credentials enter the route file or summary. Docker is only a default fixture.
"""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web')]
import config  # noqa: E402,F401

JOBS = ('catalog', 'schema', 'object_schema', 'relational', 'test_data', 'monitoring', 'lob', 'partitions', 'catalog_completeness')


def qualify(route, output, *, password=None):
    if any('password' in key.lower() for key in route):
        raise ValueError('Credentials must be outside route JSON')
    output.mkdir(parents=True, exist_ok=False)
    proof = {'complete': False, 'platform': platform.platform(), 'checks': [], 'failures': [],
        'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / 'web/pgadmin/cdeadmin').rglob('*.py'))}}
    for pure in (True,):
        mode = 'native'
        for name in (*JOBS, 'driver_platform'):
            directory = output / mode / name
            try:
                print('START ' + mode + ' ' + name, flush=True)
                module = importlib.import_module('tools.cdeadmin_mariadb_' + name +
                    ('_gate' if name in {'driver_platform','catalog_completeness'} else '_qualification'))
                if name == 'driver_platform':
                    receipt = module.run(route, directory, password=password)
                    passed = receipt.get('complete') is True
                else:
                    if name == 'catalog_completeness':
                        module = importlib.import_module('tools.cdeadmin_mariadb_catalog_completeness_gate')
                    module.qualify(route, directory, password=password)
                    receipt = json.loads((directory / 'summary.json').read_text())
                    passed = receipt.get('complete') is True
                if not passed:
                    raise AssertionError('Native scope did not qualify')
                proof['checks'].append({'connector': mode, 'scope': name, 'passed': True})
            except Exception as error:
                proof['failures'].append({'connector': mode, 'scope': name, 'type': type(error).__name__,
                    'error_code': getattr(error, 'errno', None), 'locations': [
                        {'file': Path(frame.filename).name, 'line': frame.lineno}
                        for frame in traceback.extract_tb(error.__traceback__)]})
                print('FAILED ' + mode + ' ' + name + ' ' + type(error).__name__, flush=True)
            (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    proof['complete'] = not proof['failures'] and len(proof['checks']) == (len(JOBS) + 1)
    (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route', type=Path)
    parser.add_argument('--password-env')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.route:
        result = qualify(json.loads(args.route.read_text()), args.output,
            password=os.environ[args.password_env] if args.password_env else None)
    else:
        from tools.cdeadmin_mariadb_driver_gate import run
        result = run('mariadb:12.2.2', args.output, lambda route, out: qualify(route, out))
    sys.exit(0 if result['complete'] else 1)

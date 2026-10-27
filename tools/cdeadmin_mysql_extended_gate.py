"""Collect every existing MySQL DDN/encoding and driver workflow failure.

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

JOBS = ('batch', 'column_rename', 'creation', 'database_ddn', 'foreign_key_ddn',
        'graphical_columns', 'graphical_foreign_key', 'graphical_rename',
        'materialized_view_ddn', 'routine_ddn', 'statement_encoding',
        'trigger_ddn', 'view_alter', 'view_ddn', 'views')


def qualify(route, output, *, password=None):
    if any('password' in key.lower() for key in route):
        raise ValueError('Credentials must be outside route JSON')
    output.mkdir(parents=True, exist_ok=False)
    proof = {'complete': False, 'platform': platform.platform(), 'checks': [], 'failures': [],
        'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / 'web/pgadmin/cdeadmin').rglob('*.py'))}}
    for pure in (True, False):
        mode = 'pure' if pure else 'cext'
        options = {**route, 'use_pure': pure, **({'password': password} if password else {})}
        for name in (*JOBS, 'driver_platform'):
            directory = output / mode / name
            try:
                print('START ' + mode + ' ' + name, flush=True)
                module = importlib.import_module('tools.cdeadmin_mysql_' + name +
                    ('_gate' if name == 'driver_platform' else '_qualification'))
                if name == 'driver_platform':
                    receipt = module.run({**route, 'use_pure': pure}, directory, password=password)
                    passed = receipt.get('complete') is True
                else:
                    module.qualify(options, directory)
                    receipt = json.loads((directory / 'summary.json').read_text())
                    passed = receipt.get('passed') is True
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
    proof['complete'] = not proof['failures'] and len(proof['checks']) == 2 * (len(JOBS) + 1)
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
        from tools.mysql_qualification_support import server
        with server(args.output.parent / (args.output.name + '-fixture')) as (route, _, fixture):
            result = qualify(route, args.output)
        result['owned_cleanup_confirmed'] = fixture['owned_server_stopped']
        result['complete'] = result['complete'] and result['owned_cleanup_confirmed']
        (args.output / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    sys.exit(0 if result['complete'] else 1)

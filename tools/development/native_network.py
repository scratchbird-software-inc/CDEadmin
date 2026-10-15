"""Run existing native network-provider gates against explicit disposable estates.

The supplied accounts must be authorized for the gates' owned test schemas,
users and databases. Credentials are read from named environment variables;
they are never stored in the route JSON or printed in the receipt.
"""
import argparse
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'web'))


def execute(engine, specification, evidence):
    import config
    if engine == 'postgresql':
        import shutil
        executable = shutil.which('pg_dump')
        if executable:
            directory = str(Path(executable).parent)
            config.DEFAULT_BINARY_PATHS.update({'pg': directory, 'pg-18': directory})
    allowed = {'route', 'password_env', 'database_directory', 'path_style'}
    if set(specification) - allowed:
        raise ValueError('Unknown network gate settings; keep credentials outside JSON')
    route = specification['route']
    if not isinstance(route, dict) or any('password' in name.lower() for name in route):
        raise ValueError('Network route must not contain passwords')
    variable = specification.get('password_env')
    password = os.environ[variable] if variable else None
    module = importlib.import_module('tools.cdeadmin_' + engine + '_driver_platform_gate')
    if engine == 'postgresql':
        receipt = module.qualify(route, password, evidence)
    elif engine == 'firebird':
        receipt = module.run(route, specification['database_directory'], evidence,
                             password=password, path_style=specification.get('path_style', 'posix'))
    else:
        receipt = module.run(route, evidence, password=password)
    print(json.dumps({'engine': engine, 'complete': receipt['complete']}))
    return 0 if receipt['complete'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--routes', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--engine', choices=('postgresql', 'firebird', 'mysql', 'mariadb'))
    args = parser.parse_args()
    specifications = json.loads(args.routes.read_text(encoding='utf-8'))
    if not isinstance(specifications, dict) or set(specifications) - {'postgresql', 'firebird', 'mysql', 'mariadb'}:
        parser.error('Expected an object keyed by supported network engine')
    if args.engine:
        return execute(args.engine, specifications[args.engine], args.evidence)
    args.evidence.mkdir(parents=True, exist_ok=False)
    results = []
    for engine in ('postgresql', 'firebird', 'mysql', 'mariadb'):
        result = {'engine': engine, 'status': 'not configured'}
        if engine in specifications:
            process = subprocess.run([sys.executable, __file__, '--routes', str(args.routes.resolve()),
                                      '--evidence', str(args.evidence / engine), '--engine', engine], cwd=ROOT)
            result['status'] = 'passed' if process.returncode == 0 else 'failed'
        results.append(result)
    receipt = {'complete': all(r['status'] == 'passed' for r in results), 'engines': results}
    (args.evidence / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt, indent=2))
    return 0 if receipt['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

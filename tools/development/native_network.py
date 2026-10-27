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
sys.path.insert(0, str(ROOT / 'tools'))


def execute(engine, specification, evidence):
    import config
    if engine == 'postgresql':
        import shutil
        executable = shutil.which('pg_dump')
        if executable:
            directory = str(Path(executable).parent)
            config.DEFAULT_BINARY_PATHS.update({'pg': directory, 'pg-18': directory})
    allowed = {'route', 'password_env', 'database_directory', 'path_style', 'server_file_tests'}
    if set(specification) - allowed:
        raise ValueError('Unknown network gate settings; keep credentials outside JSON')
    if 'server_file_tests' in specification and (engine != 'postgresql' or type(specification['server_file_tests']) is not bool):
        raise ValueError('Server file qualification requires an explicit PostgreSQL boolean')
    route = specification['route']
    if not isinstance(route, dict) or any('password' in name.lower() for name in route):
        raise ValueError('Network route must not contain passwords')
    variable = specification.get('password_env')
    password = os.environ[variable] if variable else None
    if variable == 'CDEADMIN_OWNED_FIXTURE_PASSWORD' and engine in ('mysql', 'mariadb'):
        if os.name == 'nt':
            from windows_faults import install
            fault_observer = install()  # Keep the callback alive through the native gate.
        # Owned loopback diagnostics only; external gate failures stay redacted.
        connector = importlib.import_module('mysql.connector' if engine == 'mysql' else 'mariadb')
        connect = connector.connect

        def observed_connect(*args, **kwargs):
            import psutil
            if os.name == 'nt':
                print(json.dumps({'loaded_native_libraries': [m.path for m in psutil.Process().memory_maps()
                    if any(name in m.path.lower() for name in ('libssl', 'libcrypto', 'libmysql', 'libmariadb', '_mysql_connector'))]}), flush=True)
            try:
                return connect(*args, **kwargs)
            except Exception as error:
                print(json.dumps({'owned_connect_error': type(error).__name__,
                    'message': str(error).replace(password, '[secret]')[:1024] if password else str(error)[:1024],
                    'errno': getattr(error, 'errno', None),
                    'sqlstate': getattr(error, 'sqlstate', None),
                    'option_names': sorted(kwargs)}), flush=True)
                raise
        connector.connect = observed_connect
    module = importlib.import_module('tools.cdeadmin_' + engine + '_driver_platform_gate')
    if engine == 'postgresql':
        receipt = module.qualify(route, password, evidence, server_files=specification.get('server_file_tests',False))
    elif engine == 'firebird':
        receipt = module.run(route, specification['database_directory'], evidence,
                             password=password, path_style=specification.get('path_style', 'posix'))
    else:
        receipt = module.run(route, evidence, password=password)
    if engine in {'mysql','mariadb'}:
        # Collect product failures even when the driver proof failed. Each
        # consumer gate owns and removes its uniquely named native objects.
        for name in ('completion', 'extended'):
            try:
                product = importlib.import_module('tools.cdeadmin_' + engine + '_' + name + '_gate')
                proof = product.qualify(route, evidence / name, password=password)
                if proof['complete']:
                    receipt.setdefault('checks', []).append(name)
                else:
                    receipt.setdefault('failures', []).append({'scope': name, 'type': 'NativeQualificationFailed'})
                    receipt['complete'] = False
            except Exception as error:
                receipt.setdefault('failures', []).append({'scope': name, 'type': type(error).__name__})
                receipt['complete'] = False
        (evidence / 'summary.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps({'engine': engine, 'complete': receipt['complete'],
                      'checks': receipt.get('checks', []),
                      'failures': receipt.get('failures', [])}, indent=2))
    for path in sorted(evidence.rglob('*.json')):
        try:
            nested = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if isinstance(nested, dict) and nested.get('failures'):
            # Existing platform gates deliberately redact failures to their
            # type, stage and source locations. Retain those diagnostics in CI.
            print(json.dumps({'receipt': str(path.relative_to(evidence)),
                              'failures': nested['failures']}, indent=2))
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

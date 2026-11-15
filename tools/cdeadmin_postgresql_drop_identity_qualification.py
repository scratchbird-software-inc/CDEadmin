"""Owned PostgreSQL 18.3 qualification for native reviewed table DROP guards."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'web'), str(ROOT/'tools')]


def qualify(output):
    from tools.postgresql_qualification_support import server
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Qualification artifacts belong outside source')
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    paths = ['web/pgadmin/cdeadmin/providers/postgresql/provider.py',
             'web/pgadmin/cdeadmin/providers/postgresql/destructive_identity.py',
             'web/pgadmin/cdeadmin/providers/postgresql/namespace_guard.py',
             'web/pgadmin/cdeadmin/providers/postgresql/native_admin.py',
             'web/pgadmin/cdeadmin/providers/postgresql/preserved_surface.py',
             'tools/tests/test_postgresql_drop_identity.py',
             'tools/tests/test_ui_descriptor_operations_postgresql.py',
             'tools/cdeadmin_postgresql_drop_identity_qualification.py']
    proof = {'complete': False, 'native_version': '18.3',
             'scope': 'Owned native server and actual PostgreSQL provider callback plan/apply, independent catalog/data and competing transactions. No HTTP or other-version claim.',
             'source_sha256': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}}
    try:
        with tempfile.TemporaryDirectory(prefix='postgresql-drop-', dir=output) as area:
            fixture = Path(area)/'server'
            try:
                with server(fixture) as (route, password, _fixture):
                    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', TMPDIR=str(output),
                               PYTHONPATH=f'{ROOT}:{ROOT}/web:{ROOT}/tools',
                               CDEADMIN_SQLITE_STARTUP_POLICY=str(output/'absent-startup-policy.json'))
                    env['CDEADMIN_POSTGRESQL_DROP_TEST'] = json.dumps({
                        'host': route['host'], 'port': route['port'], 'user': route['user'],
                        'password': password, 'dbname': route['database']})
                    command = [sys.executable, '-B', '-m', 'pytest', '-q', '-ra', '--tb=short',
                               '-p', 'no:cacheprovider', '--basetemp='+str(output/'pytest-postgresql-drop'),
                               '--junitxml='+str(output/'postgresql-drop.xml'),
                               str(ROOT/'tools/tests/test_postgresql_drop_identity.py')]
                    proof['command'] = command
                    with (output/'postgresql-drop-tests.log').open('w') as log:
                        result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
                    proof['exit_code'] = result.returncode
            finally:
                if (fixture/'fixture.json').exists():
                    proof['fixture'] = json.loads((fixture/'fixture.json').read_text())
                if (fixture/'server.log').exists():
                    shutil.copyfile(fixture/'server.log', output/'postgresql-drop-server.log')
        suites = ET.parse(output/'postgresql-drop.xml').getroot().findall('.//testsuite')
        proof['tests'] = {key: sum(int(suite.get(key, 0)) for suite in suites)
                          for key in ('tests', 'failures', 'errors', 'skipped')}
        proof['complete'] = (proof['exit_code'] == 0 and proof['fixture']['owned_server_stopped']
                             and proof['tests']['tests'] >= 18 and not any(proof['tests'][key]
                                 for key in ('failures', 'errors', 'skipped')))
    finally:
        (output/'postgresql-drop-native.json').write_text(json.dumps(proof, indent=2)+'\n')
    if not proof['complete']:
        raise RuntimeError('PostgreSQL DROP guard qualification is incomplete; inspect retained logs')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = qualify(args.output)
    print(json.dumps({'complete': result['complete'], 'tests': result['tests']}))

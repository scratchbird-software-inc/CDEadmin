#!/usr/bin/env python3
"""Portable owned-schema MySQL driver proof; no Docker or local server setup.

Run from the repository root with web on PYTHONPATH. Route JSON contains
connection/TLS options, never a password or an existing database. Passwords
are read interactively and supplied through the provider secret lease.
"""
import argparse
import getpass
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
import traceback

from tools.cdeadmin_mysql_execution_gate import qualify as execution
from tools.cdeadmin_mysql_query_values_gate import qualify as values
from tools.mysql_driver_gate_support import provider_access
from pgadmin.cdeadmin.providers.mysql_family.provider import (
    MYSQL_PROFILE, _create_client,
)


def run(route, evidence, *, password=None):
    if not isinstance(route, dict) or any(key in route for key in (
            'database', 'password', 'password1', 'password2', 'password3',
            'credential_reference_id', 'credential_references')):
        raise ValueError('Route must omit databases and credentials')
    if not route.get('host') and not route.get('unix_socket'):
        raise ValueError('An explicit server address is required')
    evidence = Path(evidence)
    evidence.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    package = root / 'web/pgadmin/cdeadmin/providers/mysql_family'
    receipt = {
        'schema': 'cdeadmin.mysql-driver-platform-proof.v1',
        'complete': False, 'platform': platform.platform(),
        'machine': platform.machine(), 'python': platform.python_version(),
        'driver_version': importlib.metadata.version('mysql-connector-python'),
        'checks': [], 'failures': [],
        'source_sha256': {str(p.relative_to(root)): hashlib.sha256(
            p.read_bytes()).hexdigest() for p in sorted(package.iterdir())
            if p.suffix in {'.py', '.json'}},
        'runner_sha256': hashlib.sha256(
            Path(__file__).read_bytes()).hexdigest(),
        'scope': 'native driver; no platform UX or console acceptance',
    }
    request_route, permissions = provider_access(route, password)
    client = _create_client(MYSQL_PROFILE, permissions, None)
    try:
        handle = client.open_session({'route': request_route})
        receipt['native_connection_class'] = (
            type(handle).__module__ + '.' + type(handle).__name__)
        cursor = handle.cursor()
        try:
            cursor.execute('SELECT VERSION()')
            receipt['server_version'] = cursor.fetchone()[0]
            cursor.execute("SHOW SESSION STATUS LIKE 'Ssl_version'")
            receipt['tls_version'] = cursor.fetchone()[1]
        finally:
            cursor.close()
        client.close_session(handle)
        for name, qualify in [('values', values), ('execution', execution)]:
            try:
                options = {'password': password}
                if name == 'execution':
                    # Never weaken a supplied TLS route to inject plaintext
                    # faults. Reply loss has a separate owned-container gate.
                    options['reply_loss'] = False
                proof = qualify(route, evidence / name, **options)
                if not proof['complete']:
                    raise AssertionError('Native scope did not qualify')
                receipt['checks'].append(name)
            except Exception as exc:
                receipt['failures'].append({
                    'scope': name, 'type': type(exc).__name__,
                    'locations': [{'file': Path(f.filename).name,
                                   'line': f.lineno}
                                  for f in traceback.extract_tb(
                                      exc.__traceback__)]})
        receipt['complete'] = not receipt['failures']
    except Exception as exc:
        receipt['failures'].append({'scope': 'connect',
                                    'type': type(exc).__name__})
    finally:
        try:
            client.close()
        except Exception as exc:
            receipt['complete'] = False
            receipt['failures'].append({'scope': 'release',
                                        'type': type(exc).__name__})
        (evidence / 'summary.json').write_text(json.dumps(receipt, indent=2))
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route', required=True, type=Path)
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--no-password', action='store_true',
                        help='Use an explicitly passwordless test account')
    args = parser.parse_args()
    supplied = json.loads(args.route.read_text())
    password = (None if args.no_password
                else getpass.getpass('MySQL password: '))
    result = run(supplied, args.evidence, password=password)
    raise SystemExit(0 if result['complete'] else 1)

"""Run native app, dependency and embedded-provider checks in fresh processes."""
import argparse
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))


def child(name, evidence, port):
    if name == 'imports':
        packages = ('psycopg', 'firebird.driver', 'mysql.connector', 'mariadb',
                    'duckdb', 'sqlite3', 'pyarrow', 'gssapi', 'flask',
                    'pymongo', 'cassandra', 'pymilvus', 'neo4j', 'redis',
                    'pyignite', 'fdb', 'clickhouse_connect', 'influxdb_client_3',
                    'opensearchpy')
        failures = []
        for name in packages:
            try:
                module = importlib.import_module(name)
                print(name, getattr(module, '__version__', 'imported'))
            except Exception as error:
                failures.append({'module': name, 'error': str(error)})
        # A shared-object suffix on macOS is normal; inspect file contents.
        for module in list(sys.modules.values()):
            path = getattr(module, '__file__', None)
            if path and Path(path).suffix.lower() in ('.pyd', '.so', '.dll', '.dylib'):
                with open(path, 'rb') as source:
                    if source.read(4) == b'\x7fELF':
                        failures.append({'module': str(path), 'error': 'Linux ELF binary'})
        print(json.dumps({'failures': failures}, indent=2))
        return bool(failures)
    if name == 'runtime':
        import sqlite3
        import duckdb
        import pyarrow
        import firebird.driver as firebird
        from pgadmin.cdeadmin.providers.firebird.provider import (
            _configure_client_library, _client_library_identity)
        _configure_client_library(firebird)
        identity = _client_library_identity(firebird)
        print(json.dumps(identity, indent=2))
        assert identity['client_library_version'] == '5.0.4'
        assert duckdb.__version__ == '1.5.2'
        assert pyarrow.__version__ == '25.0.1'
        assert sqlite3.sqlite_version == '3.53.0', sqlite3.sqlite_version
        with sqlite3.connect(':memory:') as connection:
            connection.execute('CREATE VIRTUAL TABLE f USING fts5(value)')
            connection.execute('CREATE VIRTUAL TABLE r USING rtree(id, lo, hi)')
            assert connection.execute("SELECT json_extract('{\"a\":1}', '$.a')").fetchone() == (1,)
        return 0
    if name == 'http':
        import config
        directory = evidence / 'application'
        directory.mkdir(parents=True, exist_ok=True)
        config.SERVER_MODE = False
        config.DEBUG = False
        config.TESTING = False
        config.DATA_DIR = str(directory)
        config.SQLITE_PATH = str(directory / 'configuration.db')
        config.LOG_FILE = str(directory / 'application.log')
        config.SESSION_DB_PATH = str(directory / 'sessions')
        config.STORAGE_DIR = str(directory / 'storage')
        config.AZURE_CREDENTIAL_CACHE_DIR = str(directory / 'azure')
        config.KERBEROS_CCACHE_DIR = str(directory / 'kerberos')
        config.DEFAULT_SERVER = '127.0.0.1'
        config.DEFAULT_SERVER_PORT = port
        config.MASTER_PASSWORD_REQUIRED = True
        config.SECRET_KEY = secrets.token_hex(32)
        import runpy
        runpy.run_path(str(ROOT / 'web/CDEadmin.py'), run_name='__main__')
        return 0
    raise ValueError(name)


def http(evidence):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    log = evidence / 'http.log'
    with log.open('w', encoding='utf-8') as output:
        process = subprocess.Popen([sys.executable, __file__, '--child', 'http',
                                    '--evidence', str(evidence), '--port', str(port)],
                                   cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Application exited before HTTP became ready')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=3) as response:
                        assert response.status == 200
                        body = response.read()
                        assert body, 'Empty application response'
                        print(f'Canonical launcher HTTP 200 ({len(body)} bytes)')
                        return
                except (OSError, urllib.error.URLError):
                    time.sleep(.5)
            raise TimeoutError('Application HTTP readiness exceeded 120 seconds')
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=15)
            print(log.read_text(encoding='utf-8', errors='replace'))


def verify(evidence):
    from native import command
    evidence.mkdir(parents=True, exist_ok=False)
    checks = []
    commands = {
        'dependency-imports': [sys.executable, __file__, '--child', 'imports', '--evidence', evidence],
        'exact-native-runtimes': [sys.executable, __file__, '--child', 'runtime', '--evidence', evidence],
        'sqlite-provider': [sys.executable, '-m', 'tools.cdeadmin_sqlite_driver_platform_gate', '--evidence', evidence / 'sqlite'],
        'duckdb-provider': [sys.executable, '-m', 'tools.cdeadmin_duckdb_driver_platform_gate', '--evidence', evidence / 'duckdb'],
        'python-contracts': [sys.executable, '-c', "import config,pytest; raise SystemExit(pytest.main(['tools/tests', '--junitxml=' + __import__('sys').argv[1]]))", evidence / 'python.xml'],
        'javascript-contracts': ['corepack', 'yarn', 'exec', 'jest', '--runInBand', '--json', '--outputFile', evidence / 'javascript.json'],
        'identity': [sys.executable, '-m', 'tools.cdeadmin_product_identity', '--source', ROOT, '--skip-inventory', '--output', evidence / 'identity.json'],
    }
    for name, args in commands.items():
        result = {'check': name, 'status': 'failed'}
        try:
            command(args, cwd=ROOT / 'web' if name == 'javascript-contracts' else ROOT,
                    log=evidence / (name + '.log'))
            result['status'] = 'passed'
        except Exception as error:
            result['error'] = str(error)
        checks.append(result)
    result = {'check': 'canonical-launcher-http', 'status': 'failed'}
    try:
        http(evidence)
        result['status'] = 'passed'
    except Exception as error:
        result['error'] = str(error)
    checks.append(result)
    receipt = {'checks': checks, 'platform': platform.platform(),
               'complete': all(c['status'] == 'passed' for c in checks),
               'network_engine_qualification': 'not executed without owned server routes',
               'scratchbird_history_qualification': 'requires native ScratchBird runtime'}
    (evidence / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt, indent=2))
    return 0 if receipt['complete'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--child', choices=('imports', 'runtime', 'http'))
    parser.add_argument('--port', type=int, default=5051)
    args = parser.parse_args()
    if args.child:
        raise SystemExit(child(args.child, args.evidence, args.port))
    raise SystemExit(verify(args.evidence))

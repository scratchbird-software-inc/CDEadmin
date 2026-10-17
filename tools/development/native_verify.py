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
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'web'))


def child(name, evidence, port):
    if name == 'imports':
        packages = ('psycopg', 'firebird.driver', 'mysql.connector', 'mariadb', 'scratchbird',
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
                    if source.read(4) == b'\x7fELF' and platform.system() != 'Linux':
                        failures.append({'module': str(path), 'error': 'Linux ELF binary'})
        print(json.dumps({'failures': failures}, indent=2))
        return bool(failures)
    if name == 'runtime':
        import config  # Initialize the inherited application import boundary.
        import sqlite3
        import duckdb
        import pyarrow
        import firebird.driver as firebird
        import mariadb
        from pglast import parser
        assert getattr(parser, 'CDEADMIN_PARSE_OPTIONS_REVISION', None) == 2, 'Build the native PostgreSQL parser options patch'
        assert hasattr(mariadb._mariadb.cursor, 'cdeadmin_exact_temporals'), 'Stock MariaDB connector is insufficient'
        from pgadmin.cdeadmin.providers.firebird.provider import (
            _configure_client_library, _client_library_identity)
        _configure_client_library(firebird)
        identity = _client_library_identity(firebird)
        print(json.dumps(identity, indent=2))
        # isc_get_client_version reports major/minor; the asset hash and
        # embedded ENGINE_VERSION observation establish the maintenance build.
        assert identity['client_library_version'] == '5.0'
        assert duckdb.__version__ == '1.5.2'
        assert pyarrow.__version__ == '25.0.1'
        assert sqlite3.sqlite_version == '3.53.0', sqlite3.sqlite_version
        with sqlite3.connect(':memory:') as connection:
            assert callable(getattr(connection, 'load_extension', None)), 'SQLite extension loader is missing from CPython'
            assert callable(getattr(connection, 'enable_load_extension', None)), 'Rebuild CPython with --enable-loadable-sqlite-extensions'
            connection.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION, True)
            connection.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION, False)
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
        config.CONFIG_DATABASE_URI = ''
        config.CDEADMIN_OPERATION_STORE_PATH = str(directory / 'operations.json')
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
                        browser(evidence, f'http://127.0.0.1:{port}/')
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


def browser(evidence, url):
    """Prove the compiled workbench actually mounts in a native browser."""
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support import expected_conditions as conditions
    from selenium.webdriver.support.ui import WebDriverWait
    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1440,1000')
    options.add_argument('--user-data-dir=' + str(evidence / 'owned-browser-profile'))
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    driver = None
    receipt = {'workbench_mounted': False, 'complete': False, 'console_errors': []}
    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(60)
        driver.get(url)
        WebDriverWait(driver, 90).until(conditions.presence_of_element_located(
            (By.CSS_SELECTOR, '[data-cdeadmin-shell="zero-grey"]')))
        WebDriverWait(driver, 30).until(conditions.presence_of_element_located(
            (By.CSS_SELECTOR, '[data-cdeadmin-qa-key="explorer-workspace"]')))
        WebDriverWait(driver, 30).until(
            lambda browser: not browser.find_elements(By.ID, 'pg-spinner'))
        receipt['workbench_mounted'] = True
        receipt['startup_overlay_removed'] = True
    finally:
        if driver is not None:
            try:
                messages = driver.get_log('browser')
                errors = [message for message in messages if message['level'] == 'SEVERE']
                receipt.update(browser=driver.capabilities.get('browserName'),
                               version=driver.capabilities.get('browserVersion'),
                               platform=driver.capabilities.get('platformName'),
                               console_errors=errors,
                               complete=receipt['workbench_mounted'] and not errors)
                driver.save_screenshot(str(evidence / 'workbench.png'))
            finally:
                driver.quit()
        (evidence / 'browser.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        print(json.dumps(receipt, indent=2))
    assert receipt['complete'], 'Native browser did not qualify; see browser.json'


def verify(evidence):
    from native import command
    evidence.mkdir(parents=True, exist_ok=False)
    checks = []
    commands = {
        'native-setup': [sys.executable, '-m', 'unittest', 'discover', '-s', 'tools/development', '-p', 'test_native.py', '-v'],
        'dependency-imports': [sys.executable, __file__, '--child', 'imports', '--evidence', evidence],
        'exact-native-runtimes': [sys.executable, __file__, '--child', 'runtime', '--evidence', evidence],
        'sqlite-provider': [sys.executable, '-m', 'tools.cdeadmin_sqlite_driver_platform_gate', '--evidence', evidence / 'sqlite'],
        'duckdb-provider': [sys.executable, '-m', 'tools.cdeadmin_duckdb_driver_platform_gate', '--evidence', evidence / 'duckdb'],
        'firebird-embedded': [sys.executable, ROOT / 'tools/development/native_firebird.py', '--evidence', evidence / 'firebird'],
        'electron-desktop': [sys.executable, ROOT / 'tools/development/native_desktop.py', '--evidence', evidence / 'desktop', '--runs', '3'],
        # Owner deferral, 2026-10-16: wire ScratchBird clients, but do not run
        # history qualification while its native engine is being developed.
        'python-contracts': [sys.executable, '-c', "import config,pytest; raise SystemExit(pytest.main(['tools/tests', '-k', 'not history', '--junitxml=' + __import__('sys').argv[1]]))", evidence / 'python.xml'],
        'javascript-contracts': ['corepack', 'yarn', 'exec', 'jest', '--maxWorkers=2',
            '--testPathIgnorePatterns=[Hh]istory', '--testNamePattern=^(?!.*[Hh]istory)',
            '--json', '--outputFile', evidence / 'javascript.json'],
        'identity': [sys.executable, '-m', 'tools.cdeadmin_product_identity', '--source', ROOT, '--skip-inventory', '--output', evidence / 'identity.json'],
    }
    for name, args in commands.items():
        result = {'check': name, 'status': 'failed'}
        try:
            command(args, cwd=ROOT / 'web' if name == 'javascript-contracts' else ROOT,
                    log=evidence / (name + '.log'),
                    timeout=3600 if name in ('python-contracts', 'javascript-contracts') else
                    900 if name == 'electron-desktop' else 300)
            result['status'] = 'passed'
        except Exception as error:
            result['error'] = str(error)
        checks.append(result)
    result = {'check': 'canonical-launcher-http-and-browser', 'status': 'failed'}
    try:
        http(evidence)
        result['status'] = 'passed'
    except Exception as error:
        result['error'] = str(error)
    checks.append(result)
    receipt = {'checks': checks, 'platform': platform.platform(),
               'complete': all(c['status'] == 'passed' for c in checks),
               'network_engine_qualification': 'not executed without owned server routes',
               'scratchbird_history_qualification': 'deferred by owner, 2026-10-16; no history tests requested'}
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

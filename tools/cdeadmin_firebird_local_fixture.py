"""Disposable loopback Firebird fixture using an existing exact runtime.

Writable configuration, security database, locks and data are isolated. Source
runtime files are fingerprinted and remain read-only. No installed server is
started, stopped or reconfigured. Callback credentials must never be logged.
For a non-installed Linux runtime, launch Python with LD_LIBRARY_PATH pointing
to that runtime's lib directory so its native dependencies can be resolved.
"""

import importlib.metadata
import json
import os
from pathlib import Path
import platform
import secrets
import subprocess
import tempfile
import traceback

from tools.cdeadmin_firebird_object_live_orchestrator import (
    _free_port, _initialize_security, _runtime_fingerprint, _stage_runtime,
    _wait_for_server,
)
from tools.cdeadmin_firebird_password_gate import (
    authenticate, reject_password, _route_arguments, _configure_client_library,
)


def run_local(runtime_source, evidence, fixture_check):
    """Run the supplied native checks; always stop and remove owned state."""
    import firebird.driver as native

    runtime_source = Path(runtime_source).resolve()
    required = ('bin/firebird', 'bin/isql', 'security5.fdb',
                'lib/libfbclient.so.5.0.4')
    if not all((runtime_source / name).is_file() for name in required):
        raise ValueError('A complete local Firebird 5.0.4 runtime is required')
    before = _runtime_fingerprint(runtime_source)
    evidence.mkdir(parents=True, exist_ok=False)
    result = {'complete': False, 'fixture': 'local-loopback',
              'platform': platform.platform(),
              'driver_version': importlib.metadata.version('firebird-driver'),
              'runtime_sha256': before, 'failures': [],
              'owned_process_stopped': False, 'owned_state_removed': False}
    previous_library = os.environ.get('CDEADMIN_FIREBIRD_CLIENT_LIBRARY')
    previous_runtime = {key: os.environ.get(key)
                        for key in ('FIREBIRD', 'FIREBIRD_LOCK')}
    root = None
    process = None
    os.environ['CDEADMIN_FIREBIRD_CLIENT_LIBRARY'] = str(
        runtime_source / 'lib/libfbclient.so.5.0.4')
    try:
        _configure_client_library(native)
        with tempfile.TemporaryDirectory(
                prefix='firebird-local-') as temporary:
            root = Path(temporary)
            runtime = root / 'runtime'
            _stage_runtime(runtime_source, runtime)
            # Do not inherit includes, aliases or absolute security paths from
            # an existing installation into this disposable fixture.
            (runtime / 'firebird.conf').write_text(
                'RemoteBindAddress = 127.0.0.1\nWireCrypt = Enabled\n'
                'AuthServer = Srp256,Srp\nUserManager = Srp\n'
                'Providers = Remote,Engine13,Loopback\n'
                f'SecurityDatabase = {runtime / "security5.fdb"}\n')
            (runtime / 'databases.conf').write_text('')
            environment = dict(os.environ, FIREBIRD=str(runtime),
                               FIREBIRD_LOCK=str(runtime / 'lock'),
                               LD_LIBRARY_PATH=str(runtime / 'lib'))
            # The Python client's plugin loader also needs the staged root;
            # selecting libfbclient alone does not select its plugin directory.
            os.environ.update({key: environment[key]
                               for key in previous_runtime})
            password = secrets.token_urlsafe(24)
            _initialize_security(runtime, password, environment)
            port = _free_port()
            with (evidence / 'server.log').open('wb') as log:
                process = subprocess.Popen([
                    str(runtime / 'bin/firebird'), '-d', '-p', str(port),
                    '-e', str(runtime), '-el', str(runtime / 'lock'),
                    '-em', str(runtime)], env=environment,
                    stdout=log, stderr=subprocess.STDOUT)
                try:
                    _wait_for_server(process, port)
                    route = {'host': '127.0.0.1', 'port': port,
                             'database': str(root / 'qualification.fdb'),
                             'user': 'SYSDBA', 'auth_plugin_list': 'Srp256',
                             'timeout': 3}
                    accounts = {'Srp': [('OWNED_CONFIG',
                                         secrets.token_urlsafe(24))]}
                    with native.create_database(
                            password=password,
                            **_route_arguments(route, native)) as admin:
                        with admin.cursor() as cursor:
                            cursor.execute(
                                "SELECT RDB$GET_CONTEXT('SYSTEM', "
                                "'ENGINE_VERSION') FROM RDB$DATABASE")
                            result['engine_version'] = cursor.fetchone()[0]
                        if result['engine_version'] != '5.0.4':
                            raise RuntimeError(
                                'Exact Firebird version mismatch')
                        for user, credential in accounts['Srp']:
                            admin.execute_immediate(
                                f"CREATE USER {user} PASSWORD '{credential}' "
                                'USING PLUGIN Srp')
                            admin.execute_immediate(
                                f'GRANT CREATE DATABASE TO USER {user}')
                        admin.commit()
                        fixture_check(native, admin, route, accounts,
                                      evidence, root)
                    user, credential = accounts['Srp'][0]
                    authenticate(native, route, user, credential, 'Srp256')
                    reject_password(route, user, 'WRONG-' + credential,
                                    'Srp256')
                    result['authentication_checked'] = True
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
                    result['owned_process_stopped'] = (
                        process.poll() is not None)
        result['owned_state_removed'] = not root.exists()
    except Exception as error:
        # Native diagnostics can include credential material; retain only
        # exception types and source locations in the qualification summary.
        result['failures'].append({
            'type': type(error).__name__,
            'locations': [{'file': Path(frame.filename).name,
                           'line': frame.lineno}
                          for frame in traceback.extract_tb(
                              error.__traceback__)]})
    finally:
        result['owned_state_removed'] = root is not None and not root.exists()
        result['owned_process_stopped'] = (
            process is None or process.poll() is not None)
        if previous_library is None:
            os.environ.pop('CDEADMIN_FIREBIRD_CLIENT_LIBRARY', None)
        else:
            os.environ['CDEADMIN_FIREBIRD_CLIENT_LIBRARY'] = previous_library
        for key, value in previous_runtime.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        result['source_runtime_unchanged'] = (
            _runtime_fingerprint(runtime_source) == before)
        result['complete'] = bool(
            not result['failures'] and result['owned_process_stopped'] and
            result['owned_state_removed'] and
            result['source_runtime_unchanged'])
        (evidence / 'summary.json').write_text(
            json.dumps(result, indent=2) + '\n')
    return result

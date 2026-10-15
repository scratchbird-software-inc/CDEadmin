"""Qualify the native Electron launcher and its canonical Python application."""
import argparse
import base64
import json
import os
import re
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.request

from native import ROOT, command

RUNTIME = ROOT / 'runtime'


def require_electron_version(evidence, env=None):
    expected = json.loads((RUNTIME / 'package.json').read_text(encoding='utf-8'))['devDependencies']['electron']
    if not re.fullmatch(r'\d+\.\d+\.\d+', expected):
        raise RuntimeError('Pin an exact Electron release before native qualification')
    log = evidence / 'electron-runtime.log'
    command(['node', RUNTIME / 'node_modules/electron/cli.js', '-p', 'process.versions.electron'],
            cwd=RUNTIME, env=dict(env or os.environ, ELECTRON_RUN_AS_NODE='1'), log=log, timeout=180)
    versions = [line.strip() for line in log.read_text(encoding='utf-8').splitlines()
                if re.fullmatch(r'\d+\.\d+\.\d+', line.strip())]
    if versions != [expected]:
        raise RuntimeError(f'Installed Electron differs from pinned {expected}: {versions}')
    return expected


def qualify(evidence):
    import websocket
    evidence.mkdir(parents=True, exist_ok=False)
    application = evidence / 'application'
    application.mkdir()
    settings = {'SERVER_MODE': False, 'DEBUG': False, 'TESTING': False,
                'DATA_DIR': str(application), 'SQLITE_PATH': str(application / 'configuration.db'),
                'CONFIG_DATABASE_URI': '',
                'CDEADMIN_OPERATION_STORE_PATH': str(application / 'operations.json'),
                'LOG_FILE': str(application / 'application.log'),
                'SESSION_DB_PATH': str(application / 'sessions'),
                'STORAGE_DIR': str(application / 'storage'),
                'AZURE_CREDENTIAL_CACHE_DIR': str(application / 'azure'),
                'KERBEROS_CCACHE_DIR': str(application / 'kerberos'),
                'MASTER_PASSWORD_REQUIRED': True}
    launcher = evidence / 'launch.py'
    launcher.write_text('import sys,runpy\n'
        f'sys.path.insert(0,{str(ROOT / "web")!r})\nimport config\n'
        f'for name,value in {settings!r}.items(): setattr(config,name,value)\n'
        f'runpy.run_path({str(ROOT / "web/CDEadmin.py")!r},run_name="__main__")\n', encoding='utf-8')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    env = dict(os.environ, CDEADMIN_DESKTOP_PYTHON=sys.executable,
               CDEADMIN_DESKTOP_LAUNCHER=str(launcher),
               CDEADMIN_DESKTOP_DATA_DIR=str(evidence / 'owned-desktop-profile'))
    receipt = {'complete': False, 'workbench_mounted': False,
               'canonical_launcher': 'web/CDEadmin.py', 'console_errors': []}
    origin = f'http://127.0.0.1:{port}'
    process = None
    connection = None
    descendants = []
    try:
        receipt['electron_version'] = require_electron_version(evidence, env)
        with (evidence / 'desktop.log').open('w', encoding='utf-8') as output:
            process = subprocess.Popen(['node', str(RUNTIME / 'node_modules/electron/cli.js'), '.',
                '--remote-debugging-port=' + str(port), '--remote-allow-origins=' + origin],
                cwd=RUNTIME, env=env, stdout=output, stderr=subprocess.STDOUT,
                start_new_session=os.name != 'nt')
            deadline = time.monotonic() + 180
            sequence = 0

            def call(method, params=None):
                nonlocal sequence
                sequence += 1
                receipt['last_command'] = method
                connection.send(json.dumps({'id': sequence, 'method': method, 'params': params or {}}))
                while True:
                    message = json.loads(connection.recv())
                    if message.get('method') == 'Runtime.exceptionThrown':
                        receipt['console_errors'].append(message['params']['exceptionDetails'].get('text', 'Uncaught exception'))
                    if message.get('method') == 'Runtime.consoleAPICalled' and message['params']['type'] == 'error':
                        receipt['console_errors'].append({
                            'message': ' '.join(str(arg.get('value', arg.get('description', arg.get('type', 'unknown'))))
                                for arg in message['params'].get('args', []))[:4096],
                            'stack': message['params'].get('stackTrace', {}).get('callFrames', [])[:8]})
                    if message.get('id') == sequence:
                        if 'error' in message:
                            raise RuntimeError('Electron debugger command failed: ' + method)
                        return message.get('result', {})

            while time.monotonic() < deadline:
                import psutil
                try:
                    descendants.extend(psutil.Process(process.pid).children(recursive=True))
                except psutil.NoSuchProcess:
                    pass
                if process.poll() is not None:
                    raise RuntimeError('Electron exited before the workbench mounted')
                if connection is None:
                    try:
                        with urllib.request.urlopen(origin + '/json', timeout=2) as response:
                            pages = json.load(response)
                        target = next((page for page in pages if page.get('type') == 'page'
                            and page.get('url', '').startswith('http://127.0.0.1:')), None)
                        if target:
                            connection = websocket.create_connection(target['webSocketDebuggerUrl'], timeout=60, origin=origin)
                            call('Runtime.enable')
                    except OSError:
                        time.sleep(.5)
                        continue
                if connection is not None:
                    result = call('Runtime.evaluate', {'expression': '''Boolean(document.querySelector('[data-cdeadmin-shell="zero-grey"]') && document.querySelector('[data-cdeadmin-qa-key="explorer-workspace"]') && !document.querySelector('#pg-spinner'))''', 'returnByValue': True})
                    if result.get('result', {}).get('value') is True:
                        receipt['workbench_mounted'] = True
                        receipt['startup_overlay_removed'] = True
                        workspace = call('Runtime.evaluate', {'expression': '''(async () => {
                          const bridge = window.electronUI.workspaceWindows;
                          const registration = await bridge.registerWindow({workspaceId: 'default_workspace', role: 'main'});
                          const displays = await bridge.listDisplays();
                          return {windowId: registration.windowId, displays: displays.length};
                        })()''', 'awaitPromise': True, 'returnByValue': True})
                        receipt['native_workspace'] = workspace.get('result', {}).get('value')
                        if not receipt['native_workspace'] or not receipt['native_workspace']['displays']:
                            raise RuntimeError('Native workspace registration/display enumeration failed')
                        receipt['chromium'] = call('Browser.getVersion').get('product')
                        shot = call('Page.captureScreenshot', {'format': 'png'})
                        (evidence / 'workbench.png').write_bytes(base64.b64decode(shot['data']))
                        receipt['complete'] = not receipt['console_errors']
                        break
                time.sleep(.5)
            if not receipt['workbench_mounted']:
                raise TimeoutError('Electron workbench did not mount within 180 seconds')
    except Exception as error:
        receipt.update(error_type=type(error).__name__, error=str(error))
    finally:
        if connection is not None:
            connection.close()
        if process is not None and process.poll() is None:
            if os.name == 'nt':
                subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, timeout=30, check=True)
            else:
                os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=30)
        import psutil
        for child in descendants:
            try:
                child.kill()  # psutil checks creation time against PID reuse.
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(descendants, timeout=15)
        if alive:
            receipt.update(complete=False, cleanup_error='Owned desktop processes did not stop')
        log_path = evidence / 'desktop.log'
        desktop_log = log_path.read_text(encoding='utf-8', errors='replace') if log_path.exists() else ''
        main_errors = [line for line in desktop_log.splitlines()
                       if 'Error occurred in handler' in line or 'Uncaught Exception' in line]
        if main_errors:
            receipt.update(complete=False, main_process_errors=main_errors)
        (evidence / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        print(json.dumps(receipt, indent=2))
        print(desktop_log)
    return 0 if receipt['complete'] else 1


def qualify_launches(evidence, runs):
    if runs == 1:
        return qualify(evidence)
    evidence.mkdir(parents=True, exist_ok=False)
    launches = []
    for number in range(1, runs + 1):
        directory = evidence / f'launch-{number}'
        qualify(directory)
        receipt = json.loads((directory / 'receipt.json').read_text(encoding='utf-8'))
        launches.append(dict(receipt, launch=number, evidence_directory=directory.name))
        if receipt.get('cleanup_error'):
            break
    aggregate = dict(launches[-1], launches=launches, requested_launches=runs,
        complete=len(launches) == runs and all(item['complete'] for item in launches),
        workbench_mounted=all(item['workbench_mounted'] for item in launches),
        startup_overlay_removed=all(item.get('startup_overlay_removed') for item in launches),
        console_errors=[error for item in launches for error in item['console_errors']])
    (evidence / 'receipt.json').write_text(json.dumps(aggregate, indent=2), encoding='utf-8')
    print(json.dumps(aggregate, indent=2))
    return 0 if aggregate['complete'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--runs', type=int, choices=range(1, 6), default=1)
    args = parser.parse_args()
    raise SystemExit(qualify_launches(args.evidence.resolve(), args.runs))

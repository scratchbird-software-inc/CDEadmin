"""Native Windows/macOS development stages and complete failure inventory.

No WSL, Docker, Linux client extraction, or fallback engine is used here.
Run with standard CPython 3.14. Native SDKs must match the interpreter ABI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / '.native'
PYTHON = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt'
                           else 'bin/python')


def command(args, *, cwd=ROOT, env=None, log=None, timeout=3600):
    """Preserve output and bound children; never invoke an implicit shell."""
    args = [str(item) for item in args]
    # Windows cannot directly spawn Corepack's .cmd shim with shell=False.
    executable = shutil.which(args[0])
    if os.name == 'nt' and executable and executable.endswith('.cmd'):
        args = ['cmd.exe', '/d', '/c', executable, *args[1:]]
    print('+ ' + ' '.join(args), flush=True)
    if log:
        with Path(log).open('w', encoding='utf-8') as output:
            result = subprocess.run(args, cwd=cwd, env=env, stdout=output,
                                    stderr=subprocess.STDOUT, timeout=timeout)
        # GitHub retains this output even when subsequent stages fail.
        print(Path(log).read_text(encoding='utf-8', errors='replace'), flush=True)
        result.check_returncode()
    else:
        subprocess.run(args, cwd=cwd, env=env, check=True, timeout=timeout)


def environment():
    env = dict(os.environ)
    env['PYTHONUTF8'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    additions = []
    if platform.system() == 'Darwin' and shutil.which('brew'):
        for formula in ('libpq', 'mariadb-connector-c', 'krb5'):
            result = subprocess.run(['brew', '--prefix', formula],
                                    capture_output=True, text=True)
            if result.returncode == 0:
                additions.append(str(Path(result.stdout.strip()) / 'bin'))
    env['PATH'] = os.pathsep.join([str(PYTHON.parent), *additions,
                                  env.get('PATH', '')])
    env['PYTHONPATH'] = str(ROOT / 'web')
    from native_assets import paths
    return paths(env)


def configure():
    target = ROOT / 'web/config_local.py'
    if target.exists():
        print('Preserved existing web/config_local.py')
        return
    source = Path(__file__).with_name('config_local.example.py')
    with target.open('x', encoding='utf-8') as output:
        output.write(source.read_text(encoding='utf-8'))
    target.chmod(0o600)


def requirements(destination):
    """Resolve the whole application and demo dependency set together.

    Retain the project's C Psycopg requirement. Platform SDK failures must be
    repaired, not hidden by silently substituting a different implementation.
    """
    destination.write_text(
        '-r ' + (ROOT / 'requirements.txt').as_posix() + '\n' +
        '-r ' + (ROOT / 'tools/reference_engine_demos/requirements.txt').as_posix()
        + '\n-r ' + (ROOT / 'web/regression/requirements.txt').as_posix()
        + '\npytest==8.4.2\n', encoding='utf-8')


def ddn(evidence):
    source = Path(os.environ.get('SCRATCHROBIN_DDN_SOURCE',
                                str(ROOT.parent / 'Diagram-Design-Notation')))
    work = Path(os.environ.get('SCRATCHROBIN_DDN_WORK',
                              str(evidence / 'ddn-intake')))
    if not source.is_dir():
        raise RuntimeError('Clone Diagram-Design-Notation and set '
                           'SCRATCHROBIN_DDN_SOURCE to that checkout')
    command(['git', '-C', source, 'rev-parse', 'HEAD'])
    command(['git', '-C', source, 'status', '--short'])
    print((source / 'website/docs/developers/tool.md').read_text(
        encoding='utf-8'), flush=True)
    command([sys.executable, ROOT / 'tools/refresh_ddn.py', '--source',
             source, '--work', work], log=evidence / 'ddn.log')


def stage(name, evidence):
    env = environment()
    if name == 'prerequisites':
        if os.environ.get('GITHUB_ACTIONS') != 'true':
            raise RuntimeError('Install host prerequisites from NATIVE.md; '
                               'automatic host changes are limited to disposable CI VMs')
        if not shutil.which('corepack'):
            command(['npm', 'install', '--global', 'corepack@0.34.1'], env=env,
                    log=evidence / 'corepack-install.log')
        if platform.system() == 'Darwin':
            command(['brew', 'install', 'libpq', 'openssl@3', 'krb5', 'pkg-config'],
                    env=env, log=evidence / 'host-prerequisites.log')
    elif name == 'doctor':
        checks = {'standard Python 3.14': sys.version_info[:2] == (3, 14)
                  and not sysconfig_free_threaded(),
                  'Windows or macOS': platform.system() in ('Windows', 'Darwin'),
                  'native architecture': (platform.machine().lower() in ('amd64', 'x86_64')
                      if platform.system() == 'Windows' else
                      platform.machine().lower() in ('arm64', 'x86_64'))}
        checks.update({tool: bool(shutil.which(tool))
                       for tool in ('git', 'node', 'corepack', 'cmake')})
        print(json.dumps(checks, indent=2))
        if not all(checks.values()):
            raise RuntimeError('Missing native development prerequisites')
    elif name == 'clients':
        ddn(evidence)
        from native_assets import clients
        clients(evidence, env)
    elif name == 'python':
        ddn(evidence)
        from native_assets import msvc, install_python_runtime_hook, download
        env = msvc(env)
        if not PYTHON.exists():
            if PYTHON.parents[1].exists():
                raise RuntimeError('Incomplete .venv; inspect before replacing')
            interpreter = STATE / 'python/bin/python3.14' if platform.system() == 'Darwin' else Path(sys.executable)
            if not interpreter.is_file():
                raise RuntimeError('Run clients successfully to build the native interpreter')
            command([interpreter, '-m', 'venv', ROOT / '.venv'], env=env)
        install_python_runtime_hook(PYTHON, env)
        command([PYTHON, '-m', 'pip', 'install', '--upgrade', 'pip',
                 'setuptools', 'wheel', 'packaging'], env=env,
                log=evidence / 'python-tools.log')
        selected = evidence / 'requirements.txt'
        requirements(selected)
        command([PYTHON, '-m', 'pip', 'install', '-r', selected], env=env,
                log=evidence / 'dependencies.log')
        archive = download('mariadb-python')
        # The build runner requires a fresh external output directory and
        # records the same-version patch and native wheel hashes.
        import tempfile
        output = Path(tempfile.mkdtemp(prefix='mariadb-parent-', dir=evidence)) / 'build'
        command([PYTHON, '-m', 'tools.cdeadmin_build_mariadb_driver',
                 '--archive', archive, '--output', output], env=env,
                log=evidence / 'mariadb-python-build.log')
        wheels = list((output / 'wheels').glob('*.whl'))
        if len(wheels) != 1:
            raise RuntimeError('Expected one patched MariaDB native wheel')
        command([PYTHON, '-m', 'pip', 'install', '--no-deps',
                 '--force-reinstall', wheels[0]], env=env,
                log=evidence / 'mariadb-python-install.log')
        command([PYTHON, '-m', 'pip', 'check'], env=env,
                log=evidence / 'pip-check.log')
        command([PYTHON, '-m', 'pip', 'freeze', '--all'], env=env,
                log=evidence / 'packages.log')
    elif name == 'ddn':
        ddn(evidence)
    elif name == 'frontend':
        ddn(evidence)
        command(['corepack', 'yarn', 'install', '--immutable'],
                cwd=ROOT / 'web', env=env, log=evidence / 'yarn-install.log')
        command(['corepack', 'yarn', 'run', 'bundle'], cwd=ROOT / 'web',
                env=env, log=evidence / 'frontend.log')
    elif name == 'configure':
        configure()
    elif name == 'init':
        command([PYTHON, ROOT / 'web/setup.py', 'setup-db'], env=env)
    elif name == 'run':
        command([PYTHON, ROOT / 'web/CDEadmin.py'], env=env, timeout=None)
    elif name == 'verify':
        ddn(evidence)
        command([PYTHON, ROOT / 'tools/development/native_verify.py',
                 '--evidence', evidence / 'verification'], env=env,
                log=evidence / 'verification.log')
    else:
        raise ValueError(name)


def sysconfig_free_threaded():
    import sysconfig
    return bool(sysconfig.get_config_var('Py_GIL_DISABLED'))


def ci(evidence):
    """Run independent stages after failures; blocked work never counts as pass."""
    steps = []
    for name in ('prerequisites', 'doctor', 'clients', 'python', 'frontend', 'verify'):
        started = time.monotonic()
        record = {'stage': name, 'status': 'failed'}
        try:
            stage(name, evidence)
            record['status'] = 'passed'
        except Exception as error:
            record.update(error_type=type(error).__name__, error=str(error))
            print(f'FAILED {name}: {error}', flush=True)
        record['elapsed_seconds'] = round(time.monotonic() - started, 3)
        steps.append(record)
    receipt = {'schema': 'cdeadmin.native-development.v1',
               'platform': platform.platform(), 'machine': platform.machine(),
               'python': sys.version, 'steps': steps,
               'complete': all(item['status'] == 'passed' for item in steps),
               'source_revision': subprocess.check_output(
                   ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               'source_status': subprocess.check_output(
                   ['git', 'status', '--porcelain'], cwd=ROOT, text=True),
               'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (evidence / 'receipt.json').write_text(json.dumps(receipt, indent=2),
                                         encoding='utf-8')
    lines = ['# Native development qualification', '',
             f"Host: {receipt['platform']} / {receipt['machine']}", '',
             '| Stage | Result |', '| --- | --- |']
    lines += [f"| {s['stage']} | {s['status']} |" for s in steps]
    lines += ['', 'Network engines and ScratchBird history require their own '
              'native integration receipts; environment checks do not qualify '
              'unconfigured servers.']
    (evidence / 'summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(receipt, indent=2), flush=True)
    return 0 if receipt['complete'] else 1


def main():
    for output in (sys.stdout, sys.stderr):
        if hasattr(output, 'reconfigure'):
            output.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('prerequisites', 'doctor', 'clients', 'python', 'ddn', 'frontend',
                                         'configure', 'init', 'run', 'verify', 'ci'))
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    if evidence == ROOT or ROOT in evidence.parents:
        parser.error('Evidence must be outside the repository')
    evidence.mkdir(parents=True, exist_ok=True)
    if args.stage == 'ci':
        return ci(evidence)
    stage(args.stage, evidence)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

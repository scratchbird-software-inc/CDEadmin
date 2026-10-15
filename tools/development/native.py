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
SCRATCHBIRD_DRIVER = ('scratchbird @ git+https://github.com/scratchbird-software-inc/ScratchBird.git'
                     '@54b029a498393de0fb6b765996cc4f7c57211049#subdirectory=project/drivers/driver/python')
FULL_STAGES = ('prerequisites', 'doctor', 'clients', 'python', 'servers',
               'frontend', 'desktop', 'verify', 'fixtures')


def command(args, *, cwd=ROOT, env=None, log=None, timeout=3600):
    """Preserve output and bound children; never invoke an implicit shell."""
    args = [str(item) for item in args]
    # Invoke Node CLIs directly. Windows can resolve an extensionless POSIX
    # shim before its .cmd sibling, and cmd.exe would add shell quoting rules.
    if platform.system() == 'Windows' and args[0] in ('corepack', 'npm'):
        executable = shutil.which(args[0] + '.cmd', path=(env or os.environ).get('PATH'))
        if not executable:
            raise FileNotFoundError(args[0] + '.cmd')
        relative = ('corepack/dist/corepack.js' if args[0] == 'corepack'
                    else 'npm/bin/npm-cli.js')
        cli = Path(executable).parent / 'node_modules' / relative
        if not cli.is_file():
            raise FileNotFoundError(cli)
        args = ['node', str(cli), *args[1:]]
    # CreateProcess searches the parent's PATH on Windows, not necessarily
    # the PATH in the child's supplied environment (notably after VsDevCmd).
    executable = shutil.which(args[0], path=(env or os.environ).get('PATH'))
    if executable:
        args[0] = executable
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
        postgres = STATE / ('postgres/pgsql/bin' if os.name == 'nt' else 'postgres/bin')
        output.write('\n# Native PostgreSQL development tools.\n'
                     f'DEFAULT_BINARY_PATHS = {{"pg": {str(postgres)!r}, '
                     f'"pg-18": {str(postgres)!r}}}\n')
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
        + '\npytest==8.4.2\n' + SCRATCHBIRD_DRIVER + '\n', encoding='utf-8')


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
    env.setdefault('SCRATCHROBIN_DDN_SOURCE', str(ROOT.parent / 'Diagram-Design-Notation'))
    env.setdefault('SCRATCHROBIN_DDN_WORK', str(evidence / 'ddn-intake'))
    if name == 'prerequisites':
        if os.environ.get('GITHUB_ACTIONS') != 'true':
            raise RuntimeError('Install host prerequisites from NATIVE.md; '
                               'automatic host changes are limited to disposable CI VMs')
        if not shutil.which('corepack'):
            command(['npm', 'install', '--global', 'corepack@0.34.1'], env=env,
                    log=evidence / 'corepack-install.log')
        if platform.system() == 'Darwin':
            command(['brew', 'install', 'libpq', 'openssl@3', 'krb5', 'pkg-config',
                     'cmake', 'bison', 'icu4c', 'libxml2', 'lz4', 'zstd', 'readline', 'zlib'],
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
    elif name == 'servers':
        ddn(evidence)
        from native_servers import servers
        servers(evidence, env)
    elif name == 'fixtures':
        ddn(evidence)
        command([PYTHON, ROOT / 'tools/development/native_fixtures.py',
                 '--evidence', evidence / 'fixtures'], env=env,
                log=evidence / 'fixtures.log', timeout=7200)
    elif name == 'python':
        ddn(evidence)
        from native_assets import msvc, install_python_runtime_hook, download
        env = msvc(env)
        if platform.system() == 'Darwin':
            env['LDFLAGS'] = (env.get('LDFLAGS', '') + ' -Wl,-rpath,' +
                              str(STATE / 'mariadb-c/lib/mariadb')).strip()
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
        command(['corepack', 'yarn', 'run', 'linter'], cwd=ROOT / 'web',
                env=env, log=evidence / 'frontend-lint.log')
        heap = int(env.get('CDEADMIN_NODE_HEAP_MB', '4608' if platform.system() == 'Darwin'
                          and platform.machine() == 'arm64' else '6144'))
        if heap < 3072:
            raise ValueError('Native production build requires at least a 3072 MB Node heap')
        build_env = dict(env, NODE_ENV='production', NODE_OPTIONS=f'--max-old-space-size={heap}')
        # bundle hardcodes 3072 MB. Preserve all its stages while providing a
        # host-appropriate heap for the complete multi-engine frontend.
        command(['corepack', 'yarn', 'run', 'webpacker'], cwd=ROOT / 'web',
                env=build_env, log=evidence / 'frontend.log')
        command(['corepack', 'yarn', 'run', 'git:hash'], cwd=ROOT / 'web', env=env,
                log=evidence / 'frontend-revision.log')
    elif name == 'desktop':
        ddn(evidence)
        command(['corepack', 'yarn', 'install', '--immutable'], cwd=ROOT / 'runtime',
                env=env, log=evidence / 'desktop-install.log')
        command(['corepack', 'yarn', 'run', 'linter'], cwd=ROOT / 'runtime',
                env=env, log=evidence / 'desktop-lint.log')
    elif name == 'run-desktop':
        env.update(CDEADMIN_DESKTOP_PYTHON=str(PYTHON),
                   CDEADMIN_DESKTOP_LAUNCHER=str(ROOT / 'web/CDEadmin.py'),
                   CDEADMIN_DESKTOP_DATA_DIR=str(ROOT / '.devstate/desktop'))
        command(['node', ROOT / 'runtime/node_modules/electron/cli.js', '.'],
                cwd=ROOT / 'runtime', env=env, timeout=None)
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
    elif name == 'network':
        ddn(evidence)
        routes = os.environ.get('CDEADMIN_NATIVE_ROUTES')
        if not routes:
            raise RuntimeError('Set CDEADMIN_NATIVE_ROUTES to the disposable network route JSON')
        command([PYTHON, ROOT / 'tools/development/native_network.py', '--routes',
                 routes, '--evidence', evidence / 'network'], env=env,
                log=evidence / 'network.log')
    else:
        raise ValueError(name)


def sysconfig_free_threaded():
    import sysconfig
    return bool(sysconfig.get_config_var('Py_GIL_DISABLED'))


def ci(evidence, stages=None):
    """Run independent stages after failures; blocked work never counts as pass."""
    selected = tuple(stages) if stages is not None else FULL_STAGES
    if not selected or len(set(selected)) != len(selected) or set(selected) - set(FULL_STAGES):
        raise ValueError('Select unique, supported CI stages')
    steps = []
    for name in selected:
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
               'selected_stages': selected,
               'complete': all(item['status'] == 'passed' for item in steps),
               'full_environment_complete': (selected == FULL_STAGES and
                    all(item['status'] == 'passed' for item in steps)),
               'source_revision': subprocess.check_output(
                   ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               'source_status': subprocess.check_output(
                   ['git', 'status', '--porcelain'], cwd=ROOT, text=True),
               'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (evidence / 'receipt.json').write_text(json.dumps(receipt, indent=2),
                                         encoding='utf-8')
    lines = ['# Native development qualification', '',
             f"Host: {receipt['platform']} / {receipt['machine']}", '',
             'Scope: ' + ('full environment' if selected == FULL_STAGES else
                          'targeted repair run: ' + ', '.join(selected)), '',
             '| Stage | Result |', '| --- | --- |']
    lines += [f"| {s['stage']} | {s['status']} |" for s in steps]
    lines += ['', 'Owned loopback network-driver receipts are under fixtures. '
              'Distributed topologies, enterprise authentication, and ScratchBird '
              'history require separate native integration receipts.']
    (evidence / 'summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(receipt, indent=2), flush=True)
    return 0 if receipt['complete'] else 1


def main():
    for output in (sys.stdout, sys.stderr):
        if hasattr(output, 'reconfigure'):
            output.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('prerequisites', 'doctor', 'clients', 'servers', 'fixtures', 'python', 'ddn', 'frontend',
                                         'desktop', 'run-desktop', 'configure', 'init', 'run', 'verify', 'network', 'ci'))
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--stages', help='Comma-separated CI stages; subsets are targeted runs')
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    if evidence == ROOT or ROOT in evidence.parents:
        parser.error('Evidence must be outside the repository')
    evidence.mkdir(parents=True, exist_ok=True)
    if args.stage == 'ci':
        return ci(evidence, args.stages.split(',') if args.stages else None)
    if args.stages:
        parser.error('--stages applies only to ci')
    stage(args.stage, evidence)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Explicit, non-destructive development setup stages for a Linux workspace."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / 'tools/reference_engine_demos'
PYTHON = ROOT / '.venv/bin/python'
NATIVE = ROOT / '.native'
TRACKED_SQLITE = DEMO / 'runtime/sqlite-tracked/3.53.0'
TEST_PYTEST = 'pytest==9.2.0'
# Profile-guided and link-time optimisation, as release CPython builds use.
PYTHON_OPTIMIZATIONS = ('--enable-optimizations', '--with-lto')
SQLITE_OPTIONS = ('ENABLE_SESSION', 'ENABLE_PREUPDATE_HOOK', 'ENABLE_CARRAY',
                  'ENABLE_DBPAGE_VTAB', 'ENABLE_DBSTAT_VTAB')
ACTIONS = ('doctor', 'interpreter', 'python', 'configure', 'frontend', 'ddn', 'clients',
           'init', 'run', 'register', 'list', 'status', 'start', 'stop',
           'seed', 'verify', 'prepare')


def run(args, cwd=ROOT, env=None):
    subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, check=True)


def doctor():
    """Collect prerequisite failures without modifying the environment."""
    failures = []
    checks = [
        ('Python 3.14+', sys.version_info >= (3, 14)),
        ('Linux x86_64 runtime', platform.system() == 'Linux' and
         platform.machine() in ('x86_64', 'amd64')),
    ]
    for name in ('docker', 'node', 'corepack', 'go', 'cc', 'make', 'git',
                 'javac', 'jar', 'pkg-config', 'pg_config', 'mariadb_config'):
        checks.append((name, bool(shutil.which(name))))
    commands = [
        ('Local Docker endpoint', ['docker', 'context', 'inspect', '--format',
                                   '{{.Endpoints.docker.Host}}']),
        ('Docker daemon', ['docker', 'info', '--format',
                           '{{.OSType}}/{{.Architecture}}']),
        ('Compose v2', ['docker', 'compose', 'version']),
        ('Node 22+', ['node', '--version']),
        ('Go 1.25.5+', ['go', 'version']),
    ]
    for name, ok in checks:
        print(f'{"OK" if ok else "MISSING"}: {name}')
        if not ok:
            failures.append(name)
    for name, args in commands:
        try:
            result = subprocess.run(args, capture_output=True, text=True,
                                    timeout=30, check=True)
            value = result.stdout.strip()
            if name == 'Local Docker endpoint':
                endpoint = os.environ.get('DOCKER_HOST') or value
                if not endpoint.startswith('unix://'):
                    raise ValueError('Run the workspace on the Docker host; '
                                     'remote bind mounts are unsupported')
            if name == 'Docker daemon' and value not in (
                    'linux/x86_64', 'linux/amd64'):
                raise ValueError('Full estate requires Linux amd64 daemon')
            if (name == 'Node 22+' and
                    int(value.lstrip('v').split('.')[0]) < 22):
                raise ValueError('Node must be at least 22')
            if name == 'Go 1.25.5+':
                version = re.search(r'go(\d+)\.(\d+)(?:\.(\d+))?', value)
                if not version or tuple(int(x or 0) for x in
                                        version.groups()) < (1, 25, 5):
                    raise ValueError('Go must be at least 1.25.5')
            print(f'OK: {name}: {value}')
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            print(f'FAILED: {name}: {error}')
            failures.append(name)
    print('Prerequisites only: does not qualify engines or VM networking.')
    return 1 if failures else 0


def configure():
    target = ROOT / 'web/config_local.py'
    source = ROOT / 'tools/development/config_local.example.py'
    # Exclusive creation preserves an existing developer's config and secrets.
    with target.open('x', encoding='utf-8') as output:
        output.write(source.read_text(encoding='utf-8'))
    target.chmod(0o600)
    print(f'Created {target}; existing configurations are never overwritten.')


def ddn():
    """Refresh the consumed DDN runtime/tool snapshot before builds."""
    run([sys.executable, ROOT / 'tools/refresh_ddn.py'])


def interpreter():
    """Build CPython whose _sqlite3 links the tracked SQLite 3.53.0 library.

    Managed interpreters embed their own SQLite, which the native helpers
    cannot share. The library is found by RUNPATH, so LD_LIBRARY_PATH can
    still select another tracked version for the version matrix.
    """
    from native_assets import ASSETS, download
    library = TRACKED_SQLITE / 'lib/libsqlite3.so.0'
    if not library.is_file():
        run([sys.executable, DEMO / 'sqlite_tracked.py', '--version', '3.53.0'])
    with library.resolve(strict=True).open('rb') as source:
        sqlite_sha256 = hashlib.file_digest(source, 'sha256').hexdigest()
    prefix = NATIVE / 'python'
    marker = prefix / '.cdeadmin-complete'
    fingerprint = json.dumps({'python': ASSETS['python'][1], 'sqlite_sha256': sqlite_sha256,
                              'machine': platform.machine(), 'loadable_sqlite_extensions': True,
                              'runpath': str(library.parent),
                              'optimizations': list(PYTHON_OPTIMIZATIONS)}, sort_keys=True)
    if marker.is_file():
        if marker.read_text(encoding='utf-8') == fingerprint:
            print(f'Interpreter is current: {prefix / "bin/python3.14"}')
            return
        raise RuntimeError('Interpreter inputs changed; stop apps and rebuild into a fresh .native/python and .venv')
    if prefix.exists():
        raise RuntimeError(f'{prefix} has no completion marker; inspect it manually')
    source = NATIVE / 'python-source'
    if not (source / 'Python-3.14.8/configure').is_file():
        source.mkdir(parents=True, exist_ok=True)
        with tarfile.open(download('python')) as archive:
            archive.extractall(source, filter='data')
    build = NATIVE / 'python-build'
    build.mkdir(exist_ok=True)
    tracked = str(TRACKED_SQLITE)
    environment = {key: value for key, value in os.environ.items() if key != 'LD_LIBRARY_PATH'}
    environment.update(LIBSQLITE3_CFLAGS=f'-I{tracked}/include',
                       LIBSQLITE3_LIBS=f'-L{tracked}/lib -lsqlite3',
                       LDFLAGS=f'-Wl,-rpath,{tracked}/lib')
    run([source / 'Python-3.14.8/configure', f'--prefix={prefix}',
         '--with-ensurepip=install', '--enable-loadable-sqlite-extensions', *PYTHON_OPTIMIZATIONS],
        build, environment)
    run(['make', f'-j{os.cpu_count() or 1}'], build, environment)
    run(['make', 'install'], build, environment)
    # Read the result back without LD_LIBRARY_PATH: exactly the tracked file
    # is mapped, at its version, with the options the helpers require.
    run([prefix / 'bin/python3.14', '-I', '-c',
         'import os, sqlite3, ssl, sys, sysconfig\n'
         'configured = sysconfig.get_config_var("CONFIG_ARGS")\n'
         'assert all(flag in configured for flag in sys.argv[2:4]), configured\n'
         'c = sqlite3.connect(":memory:")\n'
         'options = {row[0] for row in c.execute("PRAGMA compile_options")}\n'
         'missing = [name for name in sys.argv[4:] if name not in options]\n'
         'assert not missing, missing\n'
         'c.enable_load_extension(True); c.enable_load_extension(False); c.close()\n'
         'with open("/proc/self/maps") as maps:\n'
         '    loaded = {line.split()[-1] for line in maps if "/libsqlite3." in line}\n'
         'assert loaded == {os.path.realpath(sys.argv[1])}, loaded\n'
         'assert sqlite3.sqlite_version == "3.53.0", sqlite3.sqlite_version\n'
         'print(sqlite3.sqlite_version, ssl.OPENSSL_VERSION)\n',
         library, *PYTHON_OPTIMIZATIONS, *SQLITE_OPTIONS], build, environment)
    marker.write_text(fingerprint, encoding='utf-8')
    print(f'Built {prefix / "bin/python3.14"}; set SCRATCHROBIN_PYTHON to it, then run the python stage.')


def mariadb_driver():
    """Replace the stock reference pin with the patched same-version wheel."""
    from native_assets import download
    # The build tool requires a fresh output directory outside the repository.
    with tempfile.TemporaryDirectory(prefix='scratchrobin-mariadb-driver-') as temporary:
        output = Path(temporary) / 'build'
        run([PYTHON, '-B', '-m', 'tools.cdeadmin_build_mariadb_driver',
             '--archive', download('mariadb-python'), '--output', output])
        wheels = list((output / 'wheels').glob('*.whl'))
        if len(wheels) != 1:
            raise RuntimeError('Expected one patched MariaDB native wheel')
        run([PYTHON, '-m', 'pip', 'install', '--no-deps', '--force-reinstall', wheels[0]])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=ACTIONS)
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.action == 'doctor':
        return doctor()
    if sys.version_info < (3, 14):
        parser.error('Python 3.14 or later is required; set '
                     'SCRATCHROBIN_PYTHON to a supported interpreter.')
    if PYTHON.exists():
        environment_version = subprocess.run(
            [PYTHON, '-c', 'import sys; print(sys.version_info[0], '
             'sys.version_info[1])'],
            capture_output=True, text=True, check=True).stdout.strip()
        selected_version = f'{sys.version_info.major} {sys.version_info.minor}'
        if environment_version != selected_version:
            parser.error('Existing .venv uses a different Python version; '
                         'recreate it with the selected interpreter.')
    if (platform.system() != 'Linux' or
            platform.machine() not in ('x86_64', 'amd64')):
        parser.error('Use x86_64 Linux (WSL2/VM/remote). See README.md.')
    if args.action == 'configure':
        configure()
    elif args.action == 'interpreter':
        interpreter()
    elif args.action == 'python':
        if not PYTHON.exists():
            if (ROOT / '.venv').exists():
                parser.error('Existing .venv is incomplete; inspect manually.')
            run([sys.executable, '-m', 'venv', ROOT / '.venv'])
        # Resolve application, demo and test dependencies together.
        run([PYTHON, '-m', 'pip', 'install', '-r', ROOT / 'requirements.txt',
             '-r', DEMO / 'requirements.txt',
             '-r', ROOT / 'web/regression/requirements.txt', TEST_PYTEST])
        run([PYTHON, '-B', '-m', 'tools.cdeadmin_install_mysql_driver',
             '--receipt', ROOT / '.devstate/mysql-driver.json'])
        mariadb_driver()
        run([PYTHON, '-m', 'pip', 'check'])
    elif args.action == 'frontend':
        ddn()
        run(['corepack', 'yarn', 'install', '--immutable'], ROOT / 'web')
        environment = dict(os.environ, NODE_ENV='production',
                           NODE_OPTIONS='--max-old-space-size=3072')
        run(['corepack', 'yarn', 'webpacker'], ROOT / 'web', environment)
    elif args.action == 'ddn':
        ddn()
    else:
        if not PYTHON.exists():
            parser.error('Run the python stage first to create .venv.')
        if args.action in ('run', 'init', 'register') and not (
                ROOT / 'web/config_local.py').exists():
            parser.error('Run configure first to set application paths.')
        if args.action == 'clients':
            run([PYTHON, DEMO / 'bootstrap.py', *args.arguments])
        elif args.action == 'init':
            run([PYTHON, ROOT / 'web/setup.py', 'setup-db'])
        elif args.action == 'run':
            run([PYTHON, ROOT / 'web/CDEadmin.py'])
        elif args.action == 'register':
            run([PYTHON, DEMO / 'register_demo_profiles.py', *args.arguments])
        else:
            run([PYTHON, DEMO / 'demo_estate.py',
                 args.action, *args.arguments])
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
    except FileExistsError:
        print('Configuration already exists: preserved. Review it manually.',
              file=sys.stderr)
        raise SystemExit(1)
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode)

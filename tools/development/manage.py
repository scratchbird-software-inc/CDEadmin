"""Explicit, non-destructive development setup stages for a Linux workspace."""
import argparse
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / 'tools/reference_engine_demos'
PYTHON = ROOT / '.venv/bin/python'
ACTIONS = ('doctor', 'python', 'configure', 'frontend', 'clients', 'init',
           'run', 'register', 'list', 'status', 'start', 'stop', 'seed',
           'verify', 'prepare')


def run(args, cwd=ROOT, env=None):
    subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, check=True)


def doctor():
    """Collect prerequisite failures without modifying the environment."""
    failures = []
    checks = [
        ('Python 3.12+', sys.version_info >= (3, 12)),
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=ACTIONS)
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.action == 'doctor':
        return doctor()
    if (platform.system() != 'Linux' or
            platform.machine() not in ('x86_64', 'amd64')):
        parser.error('Use x86_64 Linux (WSL2/VM/remote). See README.md.')
    if args.action == 'configure':
        configure()
    elif args.action == 'python':
        if not PYTHON.exists():
            if (ROOT / '.venv').exists():
                parser.error('Existing .venv is incomplete; inspect manually.')
            run([sys.executable, '-m', 'venv', ROOT / '.venv'])
        run([PYTHON, '-m', 'pip', 'install', '-r', ROOT / 'requirements.txt',
             '-r', DEMO / 'requirements.txt'])
        run([PYTHON, '-m', 'pip', 'check'])
    elif args.action == 'frontend':
        run(['corepack', 'yarn', 'install', '--immutable'], ROOT / 'web')
        environment = dict(os.environ, NODE_ENV='production',
                           NODE_OPTIONS='--max-old-space-size=3072')
        run(['corepack', 'yarn', 'webpacker'], ROOT / 'web', environment)
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
    except FileExistsError:
        print('Configuration already exists: preserved. Review it manually.',
              file=sys.stderr)
        raise SystemExit(1)
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode)

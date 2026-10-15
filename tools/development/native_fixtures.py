"""Owned loopback native server fixtures; never touch installed server data."""
import argparse
import csv
from contextlib import contextmanager
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time

from native import ROOT, STATE, command
from native_servers import binary


def register_process(evidence, pid, executable, argument):
    (evidence / 'owned-process.json').write_text(json.dumps({
        'pid': pid, 'executable': str(Path(executable).resolve()),
        'argument': str(argument)}), encoding='utf-8')


def cleanup_crashed_fixture(evidence):
    """A native driver crash cannot leave an owned database server running."""
    import psutil
    marker = evidence / 'owned-process.json'
    if not marker.exists():
        return
    record = json.loads(marker.read_text(encoding='utf-8'))
    try:
        process = psutil.Process(record['pid'])
        if not process.is_running():
            return
        expected = os.path.normcase(str(Path(record['executable']).resolve()))
        actual = os.path.normcase(str(Path(process.exe()).resolve()))
        argument = record['argument'].replace('\\', '/').casefold()
        command_line = ' '.join(process.cmdline()).replace('\\', '/').casefold()
        if expected != actual or argument not in command_line:
            raise RuntimeError('Refusing to stop a process outside the owned fixture')
        children = process.children(recursive=True)
        for child in children:
            child.kill()
        process.kill()
        _, alive = psutil.wait_procs([process, *children], timeout=15)
        if alive:
            raise RuntimeError('Owned fixture processes did not stop')
    except psutil.NoSuchProcess:
        return


def port():
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


@contextmanager
def postgres_running(root, data, selected_port, env, evidence):
    control = binary(root, 'pg_ctl')
    try:
        command([control, '-D', data, '-w', '-t', '60', '-l', evidence / 'server.log',
                 '-o', '-h 127.0.0.1 -p ' + str(selected_port), 'start'], env=env,
                log=evidence / 'start.log')
        register_process(evidence, int((data / 'postmaster.pid').read_text().splitlines()[0]),
                         binary(root, 'postgres'), data)
        yield
        command([control, '-D', data, 'status'], env=env, log=evidence / 'status.log')
    finally:
        if (data / 'postmaster.pid').exists():
            try:
                command([control, '-D', data, '-m', 'fast', '-w', '-t', '30', 'stop'],
                        env=env, log=evidence / 'stop.log', timeout=40)
            except Exception:
                # pg_ctl uses the restricted Windows token needed by PostgreSQL.
                # Force cleanup only if the PID still names this owned data dir.
                import psutil
                pid = int((data / 'postmaster.pid').read_text().splitlines()[0])
                owner = psutil.Process(pid)
                canonical = os.path.normcase(str(data.resolve()))
                if canonical not in [os.path.normcase(os.path.realpath(a)) for a in owner.cmdline()]:
                    raise RuntimeError('Refusing to stop a process outside the owned PostgreSQL fixture')
                children = owner.children(recursive=True)
                for child in children:
                    child.kill()
                owner.kill()
                psutil.wait_procs([owner, *children], timeout=15)
                raise


@contextmanager
def running(args, selected_port, env, log, *, owner_argument):
    with log.open('w', encoding='utf-8') as output:
        process = subprocess.Popen([str(a) for a in args], env=env, stdout=output,
                                   stderr=subprocess.STDOUT,
                                   start_new_session=os.name != 'nt')
        register_process(log.parent, process.pid, args[0], owner_argument)
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Owned server exited before readiness')
                try:
                    with socket.create_connection(('127.0.0.1', selected_port), timeout=.5):
                        break
                except OSError:
                    time.sleep(.2)
            else:
                raise TimeoutError('Owned server readiness exceeded 90 seconds')
            time.sleep(.5)
            yield
            if process.poll() is not None:
                raise RuntimeError('Owned server stopped during qualification')
        finally:
            if process.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                                   stdout=output, stderr=subprocess.STDOUT, timeout=30)
                else:
                    os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                if os.name != 'nt':
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
                process.wait(timeout=15)


@contextmanager
def sql_server(engine, directory, evidence, env):
    selected_port = port()
    data = directory / 'data'
    if engine == 'postgresql':
        root = STATE / ('postgres/pgsql' if os.name == 'nt' else 'postgres')
        command([binary(root, 'initdb'), '-D', data, '--auth=trust', '--username=qa',
                 '--encoding=UTF8', '--no-locale'], env=env, log=evidence / 'init.log')
        route = {'host': '127.0.0.1', 'port': selected_port, 'user': 'qa', 'database': 'postgres'}
        manager = postgres_running(root, data, selected_port, env, evidence)
    else:
        root = STATE / engine
        if engine == 'mysql':
            command([binary(root, 'mysqld'), '--no-defaults', '--initialize-insecure',
                     '--basedir=' + str(root), '--datadir=' + str(data)], env=env,
                    log=evidence / 'init.log')
        elif os.name == 'nt':
            command([binary(root, 'mariadb-install-db'), '--datadir=' + str(data)],
                    env=env, log=evidence / 'init.log')
        else:
            command([root / 'scripts/mariadb-install-db', '--no-defaults',
                     '--basedir=' + str(root), '--datadir=' + str(data),
                     '--auth-root-authentication-method=normal', '--skip-test-db'],
                    env=env, log=evidence / 'init.log')
        args = [binary(root, 'mysqld' if engine == 'mysql' else 'mariadbd'),
                '--no-defaults', '--basedir=' + str(root), '--datadir=' + str(data),
                '--bind-address=127.0.0.1', '--port=' + str(selected_port),
                '--socket=' + str(directory / 'owned.sock')]
        if engine == 'mysql':
            args += ['--mysqlx-bind-address=127.0.0.1', '--mysqlx-port=' + str(port())]
        if os.name == 'nt':
            args.append('--console')
        route = {'host': '127.0.0.1', 'port': selected_port, 'user': 'root'}
        manager = running(args, selected_port, env, evidence / 'server.log', owner_argument=data)
    password = secrets.token_urlsafe(32)
    with manager:
        # Read the server's own data directory before allowing any gate to
        # create objects. A port race must never dispatch writes to another DB.
        if engine == 'postgresql':
            import psycopg
            with psycopg.connect(host=route['host'], port=route['port'],
                                 user=route['user'], dbname=route['database']) as connection:
                with connection.cursor() as cursor:
                    cursor.execute('SHOW data_directory')
                    observed = cursor.fetchone()[0]
                    if os.path.normcase(os.path.realpath(observed)) != os.path.normcase(str(data.resolve())):
                        raise RuntimeError('Native server data directory differs from the owned fixture')
                    from psycopg import sql
                    cursor.execute(sql.SQL('ALTER ROLE qa PASSWORD {}').format(sql.Literal(password)))
        else:
            if engine == 'mysql':
                import mysql.connector
                # Ownership is a read-only probe. Qualification below still
                # exercises the route's actual default C connector, with no
                # fallback when a native driver fails.
                connection = mysql.connector.connect(**route, use_pure=True)
            else:
                import mariadb
                connection = mariadb.connect(**route)
            try:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT @@datadir')
                    observed = cursor.fetchone()[0]
                    if os.path.normcase(os.path.realpath(observed)) != os.path.normcase(str(data.resolve())):
                        raise RuntimeError('Native server data directory differs from the owned fixture')
                    cursor.execute("ALTER USER CURRENT_USER() IDENTIFIED BY " +
                                   ("%s" if engine == 'mysql' else "?"), (password,))
                    connection.commit()
            finally:
                connection.close()
        if os.path.normcase(os.path.realpath(observed)) != os.path.normcase(str(data.resolve())):
            raise RuntimeError('Native server data directory differs from the owned fixture')
        yield {'route': route, 'password_env': 'CDEADMIN_OWNED_FIXTURE_PASSWORD'}, password


@contextmanager
def firebird(directory, evidence, env):
    source = STATE / 'firebird'
    runtime = directory / 'runtime'
    # The vendor security template belongs to this checkout. Installed server
    # security databases and services are never used by the owned fixture.
    shutil.copytree(source, runtime, ignore=shutil.ignore_patterns('security5.fdb', '*.log'))
    security = runtime / 'security5.fdb'
    shutil.copy2(source / 'security5.fdb', security)
    security.chmod(0o600)
    selected_port = port()
    password = secrets.token_urlsafe(32)
    lock = runtime / 'lock'
    lock.mkdir(exist_ok=True)
    (runtime / 'firebird.conf').write_text(
        'RemoteBindAddress = 127.0.0.1\nAuthServer = Srp256,Srp\nUserManager = Srp\n'
        'WireCrypt = Required\nSecurityDatabase = ' + str(security) + '\n', encoding='utf-8')
    (runtime / 'databases.conf').write_text('', encoding='utf-8')
    selected = dict(env, FIREBIRD=str(runtime), FIREBIRD_LOCK=str(lock))
    executable_root = runtime if os.name == 'nt' else runtime / 'bin'
    isql = executable_root / ('isql.exe' if os.name == 'nt' else 'isql')
    bootstrap = str(directory / 'bootstrap.fdb').replace("'", "''")
    sql = (f"CREATE DATABASE '{bootstrap}' USER 'SYSDBA';\n"
           f"CREATE OR ALTER USER SYSDBA PASSWORD '{password}' USING PLUGIN Srp;\n"
           'COMMIT;\nDROP DATABASE;\nQUIT;\n')
    completed = subprocess.run([str(isql), '-bail', '-user', 'SYSDBA'], input=sql,
                               text=True, env=selected, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=60)
    if completed.returncode:
        raise RuntimeError('Owned Firebird security initialization failed')
    server = executable_root / ('firebird.exe' if os.name == 'nt' else 'firebird')
    args = [server, '-a' if os.name == 'nt' else '-d', '-p', selected_port,
            '-e', runtime, '-el', lock, '-em', runtime]
    with running(args, selected_port, selected, evidence / 'server.log', owner_argument=runtime):
        route = {'host': '127.0.0.1', 'port': selected_port, 'user': 'SYSDBA',
                 'charset': 'UTF8', 'auth_plugin_list': 'Srp256,Srp', 'wire_crypt': 'Required'}
        yield {'route': route, 'password_env': 'CDEADMIN_OWNED_FIXTURE_PASSWORD',
               'database_directory': str(directory),
               'path_style': 'windows' if os.name == 'nt' else 'posix'}, password


def run_engine(engine, target):
    result = {'engine': engine, 'status': 'failed', 'owned_state_removed': False}
    try:
        with tempfile.TemporaryDirectory(prefix='owned-', dir=target) as temporary:
            directory = Path(temporary)
            if os.name == 'nt':
                # Python 3.14's private-directory ACL may grant an elevated
                # owner group. PostgreSQL deliberately drops that group;
                # explicitly grant only the current user SID on this fixture.
                user = subprocess.check_output(['whoami.exe', '/user', '/fo', 'csv', '/nh'], text=True)
                sid = next(csv.reader([user.strip()]))[1]
                if not sid.startswith('S-1-'):
                    raise RuntimeError('Cannot identify the owned fixture user SID')
                command(['icacls.exe', directory, '/grant', '*' + sid + ':(OI)(CI)F'],
                        log=target / 'fixture-acl.log')
            fixture = firebird(directory, target, dict(os.environ)) if engine == 'firebird' else sql_server(engine, directory, target, dict(os.environ))
            with fixture as (specification, password):
                routes = target / 'route.json'
                routes.write_text(json.dumps({engine: specification}), encoding='utf-8')
                selected = dict(os.environ, CDEADMIN_OWNED_FIXTURE_PASSWORD=password)
                command([sys.executable, ROOT / 'tools/development/native_network.py',
                         '--routes', routes, '--evidence', target / 'proof', '--engine', engine],
                        env=selected, log=target / 'qualification.log')
                result['status'] = 'passed'
        result['owned_state_removed'] = True
    except Exception as error:
        result.update(error_type=type(error).__name__, error=str(error))
        result['owned_state_removed'] = not any(target.glob('owned-*'))
    (target / 'fixture-receipt.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'passed' and result['owned_state_removed'] else 1


def run(evidence):
    evidence.mkdir(parents=True, exist_ok=False)
    results = []
    for engine in ('postgresql', 'mysql', 'mariadb', 'firebird'):
        target = evidence / engine
        target.mkdir()
        result = {'engine': engine, 'status': 'failed', 'owned_state_removed': False}
        try:
            command([sys.executable, '-X', 'faulthandler', __file__, '--evidence', target,
                     '--engine', engine], env=dict(os.environ, PYTHONFAULTHANDLER='1'),
                    log=target / 'orchestrator.log', timeout=1800)
            result = json.loads((target / 'fixture-receipt.json').read_text(encoding='utf-8'))
        except Exception as error:
            result.update(error_type=type(error).__name__, error=str(error))
            try:
                cleanup_crashed_fixture(target)
                for directory in target.glob('owned-*'):
                    if directory.is_dir():
                        shutil.rmtree(directory)
                result['owned_state_removed'] = True
            except Exception as cleanup:
                result['cleanup_error'] = str(cleanup)
        results.append(result)
    receipt = {'engines': results, 'complete': all(r['status'] == 'passed' and
               r['owned_state_removed'] for r in results),
               'scope': 'native loopback driver gates; distributed topologies and ScratchBird history separate'}
    (evidence / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt, indent=2))
    return 0 if receipt['complete'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--engine', choices=('postgresql', 'mysql', 'mariadb', 'firebird'))
    args = parser.parse_args()
    raise SystemExit(run_engine(args.engine, args.evidence.resolve()) if args.engine else
                     run(args.evidence.resolve()))

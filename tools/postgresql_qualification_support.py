"""Uniquely owned PostgreSQL 18.3 loopback fixtures with retained cleanup proof."""
from contextlib import contextmanager
import json
from pathlib import Path
import secrets
import hashlib
import subprocess
import time
import os
import socket


@contextmanager
def server(output, *, server_options=(), initdb_options=()):
    import psycopg
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    if (not isinstance(server_options, (tuple, list)) or len(server_options) > 32 or
            any(not isinstance(value, str) or '\x00' in value or len(value) > 4096 for value in server_options)):
        raise ValueError('Owned PostgreSQL fixture options must be bounded native arguments')
    if not isinstance(initdb_options,(tuple,list)) or len(initdb_options)>16 or any(not isinstance(value,str) or not value or any(char.isspace() for char in value) or '\x00' in value for value in initdb_options):
        raise ValueError('Owned PostgreSQL initdb options must be individual native arguments')
    name = 'scratchrobin-postgresql-' + secrets.token_hex(8)
    password = secrets.token_urlsafe(32)
    proof = {'image': 'postgres:18.3', 'owned_server_stopped': False,
        'owned_container_name': name,
        'server_options_sha256': hashlib.sha256(json.dumps(server_options).encode()).hexdigest()}
    proof['initdb_options']=list(initdb_options)
    started = False
    try:
        image = subprocess.run(['docker', 'image', 'inspect', 'postgres:18.3', '--format', '{{.Id}}'],
            check=True, capture_output=True, text=True, timeout=30)
        proof['image_id'] = image.stdout.strip()
        subprocess.run(['docker', 'run', '-d', '--rm', '--name', name,
            '--publish', '127.0.0.1::5432', '--env', 'POSTGRES_PASSWORD=' + password,
            '--env','POSTGRES_INITDB_ARGS='+' '.join(initdb_options),
            'postgres:18.3', *server_options], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        started = True
        port = subprocess.run(['docker', 'port', name, '5432/tcp'], check=True,
            capture_output=True, text=True, timeout=15).stdout.strip().rsplit(':', 1)[1]
        route = {'host': '127.0.0.1', 'port': int(port), 'user': 'postgres', 'database': 'postgres',
            'connection_params': {'sslmode': 'disable'}}
        deadline = time.monotonic() + 45
        while True:
            try:
                with psycopg.connect(host=route['host'], port=route['port'], user=route['user'], dbname=route['database'], password=password,
                        autocommit=True, connect_timeout=2) as connection:
                    version = connection.execute('SHOW server_version_num').fetchone()[0]
                    if version != '180003': raise RuntimeError('Exact native PostgreSQL version mismatch')
                break
            except psycopg.OperationalError:
                if time.monotonic() >= deadline: raise RuntimeError('Owned PostgreSQL fixture did not become ready') from None
                time.sleep(.2)
        proof['version'] = version
        yield route, password, proof
    finally:
        if started:
            logs = subprocess.run(['docker', 'logs', name], capture_output=True, timeout=15)
            # Native errors may contain SQL. Keep server logs local, never emit
            # credentials or server diagnostics in the published receipt.
            (output / 'server.log').write_bytes(logs.stdout + logs.stderr)
            stopped = subprocess.run(['docker', 'stop', name], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=45)
            proof['owned_server_stopped'] = stopped.returncode == 0
        (output / 'fixture.json').write_text(json.dumps(proof, indent=2) + '\n')
        if started and not proof['owned_server_stopped']:
            raise RuntimeError('Owned PostgreSQL server cleanup is unconfirmed')


@contextmanager
def local_server(output,binary_path):
    """Owned native host fixture for optional, exactly built server modules."""
    import psycopg
    import psutil
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False,mode=0o700)
    binary_path=Path(binary_path).resolve();suffix='.exe' if os.name=='nt' else ''
    binaries={name:binary_path/(name+suffix) for name in ('postgres','initdb','pg_ctl')}
    if any(not path.is_file() for path in binaries.values()):raise ValueError('Select a complete native PostgreSQL binary directory')
    proof={'owned_server_stopped':False,'native_binary_sha256':{name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in binaries.items()}}
    password=secrets.token_urlsafe(32);password_file=output/'initial-password';process=None;created=None
    descriptor=os.open(password_file,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(descriptor,'w') as stream:stream.write(password+'\n')
    data=output/'database'
    try:
        with (output/'initdb.log').open('wb') as log:
            subprocess.run([str(binaries['initdb']),'-D',str(data),'--username=postgres','--encoding=UTF8','--locale=C',
                '--auth-local=reject','--auth-host=scram-sha-256','--pwfile='+str(password_file),'--no-instructions'],
                stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
        password_file.unlink()
        while True:
            with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
            if port not in {5432,5434,5435,5436}:break
        with (output/'server.log').open('wb') as log:
            process=subprocess.Popen([str(binaries['postgres']),'-D',str(data),'-h','127.0.0.1','-p',str(port),'-k','',
                '-c','max_connections=30'],stdout=log,stderr=subprocess.STDOUT)
        created=psutil.Process(process.pid).create_time()
        route={'host':'127.0.0.1','port':port,'user':'postgres','database':'postgres','connection_params':{'sslmode':'disable'}}
        deadline=time.monotonic()+45
        while True:
            if process.poll() is not None:raise RuntimeError('Owned native PostgreSQL process stopped during startup')
            try:
                with psycopg.connect(host=route['host'],port=port,user='postgres',dbname='postgres',password=password,autocommit=True,connect_timeout=2) as connection:
                    if str(connection.execute('SHOW server_version_num').fetchone()[0])!='180003':raise RuntimeError('Native PostgreSQL18.3 version mismatch')
                break
            except psycopg.OperationalError:
                if time.monotonic()>deadline:raise RuntimeError('Owned native PostgreSQL startup deadline') from None
                time.sleep(.2)
        proof.update(version='18.3',owned_pid=process.pid,owned_create_time=created)
        yield route,password,proof
    finally:
        if password_file.exists():password_file.unlink()
        if process is not None:
            if process.poll() is None:
                if psutil.Process(process.pid).create_time()!=created:raise RuntimeError('Owned native PostgreSQL process identity changed')
                with (output/'stop.log').open('wb') as log:
                    stopped=subprocess.run([str(binaries['pg_ctl']),'-D',str(data),'stop','-m','fast','-w','-t','30'],stdout=log,stderr=subprocess.STDOUT,timeout=45)
                process.wait(timeout=15);proof['owned_server_stopped']=stopped.returncode==0
            else:proof['owned_server_stopped']=True
        (output/'fixture.json').write_text(json.dumps(proof,indent=2)+'\n')
        if process is not None and not proof['owned_server_stopped']:raise RuntimeError('Owned native PostgreSQL shutdown is unconfirmed')


@contextmanager
def waiting_native(directory, paths, *, orphan=False):
    """A real pg_basebackup waits on this fixture's TCP socket, never a DB."""
    import psutil
    import sys
    directory.mkdir(parents=True,exist_ok=True)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));listener.listen();listener.settimeout(10)
        arguments=[paths['pg_basebackup'],'--pgdata='+str(directory/'backup'),
                   '--host=127.0.0.1','--port='+str(listener.getsockname()[1]),'--username=owned','--no-password']
        environment={**os.environ,'PGSSLMODE':'disable','PGCONNECT_TIMEOUT':'120'}
        process=None;connection=None;child=None
        try:
            with (directory/'fixture-tool.log').open('wb') as log:
                if orphan:
                    identity=directory/'fixture-process.json'
                    program=('import json,os,pathlib,psutil,subprocess,sys; '
                             'p=subprocess.Popen(sys.argv[2:],close_fds=True); '
                             'pathlib.Path(sys.argv[1]).write_text(json.dumps({"pid":p.pid,"created":psutil.Process(p.pid).create_time()}))')
                    subprocess.run([sys.executable,'-c',program,str(identity),*arguments],cwd=directory,
                                   env=environment,stdout=log,stderr=log,check=True,timeout=10)
                    value=json.loads(identity.read_text());process=psutil.Process(value['pid'])
                    assert process.create_time()==value['created']
                else:
                    child=subprocess.Popen(arguments,cwd=directory,env=environment,stdout=log,stderr=log)
                    process=psutil.Process(child.pid)
                connection,_address=listener.accept()
                yield process
        finally:
            if process is not None:
                try:
                    if process.is_running() and process.status()!=psutil.STATUS_ZOMBIE:
                        process.kill();process.wait(timeout=5)
                except psutil.NoSuchProcess:pass
                except psutil.TimeoutExpired:
                    assert process.status()==psutil.STATUS_ZOMBIE
            if child is not None:child.wait(timeout=5)
            if connection is not None:connection.close()

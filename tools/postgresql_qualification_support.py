"""Uniquely owned PostgreSQL 18.3 loopback fixtures with retained cleanup proof."""
from contextlib import contextmanager
import json
from pathlib import Path
import secrets
import hashlib
import subprocess
import time


@contextmanager
def server(output, *, server_options=()):
    import psycopg
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    if (not isinstance(server_options, (tuple, list)) or len(server_options) > 32 or
            any(not isinstance(value, str) or '\x00' in value or len(value) > 4096 for value in server_options)):
        raise ValueError('Owned PostgreSQL fixture options must be bounded native arguments')
    name = 'scratchrobin-postgresql-' + secrets.token_hex(8)
    password = secrets.token_urlsafe(32)
    proof = {'image': 'postgres:18.3', 'owned_server_stopped': False,
        'owned_container_name': name,
        'server_options_sha256': hashlib.sha256(json.dumps(server_options).encode()).hexdigest()}
    started = False
    try:
        image = subprocess.run(['docker', 'image', 'inspect', 'postgres:18.3', '--format', '{{.Id}}'],
            check=True, capture_output=True, text=True, timeout=30)
        proof['image_id'] = image.stdout.strip()
        subprocess.run(['docker', 'run', '-d', '--rm', '--name', name,
            '--publish', '127.0.0.1::5432', '--env', 'POSTGRES_PASSWORD=' + password,
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

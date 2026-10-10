"""Native MySQL provider pool isolation in uniquely owned schemas/accounts."""
import argparse
import json
from pathlib import Path
import secrets
import subprocess
from types import SimpleNamespace

from tools.cdeadmin_mysql_family_object_live_orchestrator import (
    _image_identity, _wait_until_ready,
)
from pgadmin.cdeadmin.providers.mysql_family.provider import (
    MYSQL_PROFILE, _create_client,
)
from pgadmin.cdeadmin.security import SecretLease


def qualify(route, evidence):
    import mysql.connector as native
    from mysql.connector.pooling import _CONNECTION_POOLS

    evidence.mkdir(parents=True, exist_ok=False)
    result = {'complete': False, 'checks': [], 'failures': []}
    owner = native.connect(**route)
    clients = []
    schemas = []
    account = 'owned_' + secrets.token_hex(8)
    account_created = False
    password = secrets.token_urlsafe(24)
    cursor = owner.cursor()
    before = set(_CONNECTION_POOLS)

    def sql(connection, source):
        cur = connection.cursor()
        try:
            cur.execute(source)
            return cur.fetchall() if cur.description else []
        finally:
            cur.close()

    def client():
        permissions = SimpleNamespace(
            acquire_secret=lambda *_: SecretLease(password))
        value = _create_client(MYSQL_PROFILE, permissions, None)
        clients.append(value)
        return value

    try:
        cursor.execute('SELECT VERSION()')
        result['version'] = cursor.fetchone()[0]
        assert result['version'].split('-')[0] == '9.7.0'
        cursor.execute(f"CREATE USER '{account}'@'%' IDENTIFIED BY %s",
                       (password,))
        account_created = True
        for index in range(2):
            schema = 'owned_driver_' + secrets.token_hex(8)
            cursor.execute(f'CREATE DATABASE `{schema}`')
            schemas.append(schema)
            cursor.execute(f"GRANT ALL ON `{schema}`.* TO '{account}'@'%'")
            cursor.execute(f'CREATE TABLE `{schema}`.marker (id INT)')
            cursor.execute(f'INSERT INTO `{schema}`.marker VALUES ({index})')
        owner.commit()
        base = dict(route, user=account, database=schemas[0],
                    credential_reference_id='owned-secret',
                    principal_reference='owned-principal',
                    pool_name='same-label', pool_size=1,
                    pool_reset_session=True)
        base.pop('password', None)
        first, second = client(), client()
        a = first.open_session({'route': base})
        b = second.open_session({'route': dict(base, database=schemas[1])})
        assert sql(a, 'SELECT * FROM marker') == [(0,)]
        assert sql(b, 'SELECT * FROM marker') == [(1,)]
        assert a.connection_id != b.connection_id
        result['checks'].append('same_pool_name_separate_provider_and_schema')
        ident = a.connection_id
        sql(a, 'INSERT INTO marker VALUES (99)')
        sql(a, 'SET @owned_test = 17')
        first.close_session(a)
        a = first.open_session({'route': base})
        assert a.connection_id == ident
        assert sql(a, 'SELECT * FROM marker') == [(0,)]
        assert sql(a, 'SELECT @owned_test') == [(None,)]
        result['checks'].append('native_rollback_reset_reuse')
        first.close_session(a)
        b_id = b.connection_id
        # A changed secret must authenticate a fresh session, even if an old
        # leased session remains alive under MySQL's native account semantics.
        password = secrets.token_urlsafe(24)
        cursor.execute(f"ALTER USER '{account}'@'%' IDENTIFIED BY %s",
                       (password,))
        replacement = second.open_session({'route': base})
        assert replacement.connection_id != b_id
        assert sql(b, 'SELECT * FROM marker') == [(1,)]
        second.close_session(b)
        second.close_session(replacement)
        result['checks'].append('credential_and_route_generation_rotation')
        unpooled = dict(base)
        unpooled.pop('pool_size')
        unpooled.pop('pool_name')
        one = first.open_session({'route': unpooled})
        two = first.open_session({'route': unpooled})
        assert one.connection_id != two.connection_id
        first.close_session(one)
        first.close_session(two)
        assert set(_CONNECTION_POOLS) == before
        result['checks'].append('reset_only_unpooled_no_global_registry')
    except Exception as exc:
        result['failures'].append({'stage': 'checks',
                                   'type': type(exc).__name__})
    finally:
        for value in clients:
            value.close()
        try:
            for schema in schemas:
                cursor.execute(f'DROP DATABASE `{schema}`')
            if account_created:
                cursor.execute(f"DROP USER '{account}'@'%'")
            result['owned_objects_removed'] = True
        except Exception as exc:
            result['failures'].append({'stage': 'cleanup',
                                       'type': type(exc).__name__})
        cursor.close()
        owner.close()
    result['complete'] = not result['failures']
    (evidence / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def run(image, evidence, qualification=qualify, *, tls=False):
    evidence.mkdir(parents=True, exist_ok=False)
    name = 'cdeadmin-mysql-driver-' + secrets.token_hex(8)
    identity = _image_identity(image)
    started = False
    mounts, server_options, route_options = [], [], {}
    if tls:
        certificates = evidence.resolve() / 'certificates'
        certificates.mkdir()
        subprocess.run([
            'openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
            '-days', '2', '-subj', '/CN=owned-mysql-fixture',
            '-addext', 'subjectAltName=IP:127.0.0.1',
            '-keyout', str(certificates / 'server.key'),
            '-out', str(certificates / 'server.crt'),
        ], check=True, capture_output=True)
        # Disposable fixture key, readable by mysqld inside the owned image.
        (certificates / 'server.key').chmod(0o644)
        mounts = ['--mount',
                  f'type=bind,src={certificates},'
                  'dst=/qualification-tls,readonly']
        server_options = [
            '--ssl-ca=/qualification-tls/server.crt',
            '--ssl-cert=/qualification-tls/server.crt',
            '--ssl-key=/qualification-tls/server.key']
        route_options = {'ssl_ca': str(certificates / 'server.crt'),
                         'ssl_verify_cert': True, 'ssl_verify_identity': True}
    try:
        subprocess.run([
            'docker', 'run', '-d', '--rm', '--name', name,
            '-e', 'MYSQL_ALLOW_EMPTY_PASSWORD=yes',
            '-p', '127.0.0.1::3306', *mounts, image, *server_options,
        ], check=True, capture_output=True)
        started = True
        port = _wait_until_ready('mysql', name, 180)
        result = qualification(
            {'host': '127.0.0.1', 'port': port, 'user': 'root',
             'connection_timeout': 5, **route_options}, evidence / 'native')
        result['image'] = identity
        return result
    finally:
        if started:
            logs = subprocess.run(
                ['docker', 'logs', name], capture_output=True)
            (evidence / 'server.log').write_bytes(logs.stdout + logs.stderr)
            subprocess.run(['docker', 'rm', '-f', '-v', name], check=True,
                           capture_output=True)
        (evidence / 'image.json').write_text(json.dumps(identity, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='mysql:9.7.0')
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    proof = run(args.image, args.evidence)
    raise SystemExit(0 if proof['complete'] else 1)

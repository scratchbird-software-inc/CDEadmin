"""Owned MariaDB native driver fixtures and private-pool qualification."""
import argparse
import json
import secrets
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

from tools.cdeadmin_mysql_family_object_live_orchestrator import (
    _image_identity, _wait_until_ready,
)
from tools.mysql_driver_gate_support import provider_access
from pgadmin.cdeadmin.providers.mysql_family.provider import (
    MARIADB_PROFILE, _create_client,
)


def qualify(route, evidence, *, password=None):
    import mariadb
    evidence.mkdir(parents=True, exist_ok=False)
    owner = mariadb.connect(**route, **(
        {'password': password} if password is not None else {}))
    route, permissions = provider_access(route, password)
    cursor = owner.cursor()
    names = ['owned_maria_' + secrets.token_hex(8) for _ in range(2)]
    made, clients = [], []
    proof = {'complete': False, 'checks': []}
    registry = set(mariadb._CONNECTION_POOLS)
    try:
        for name in names:
            cursor.execute(f'CREATE DATABASE `{name}`')
            made.append(name)
        for _ in range(2):
            clients.append(_create_client(
                MARIADB_PROFILE, permissions,
                SimpleNamespace(pool_namespace='same-declared-name')))
        handles = [client.open_session({'route': dict(
            route, database=name, pool_name='shared', pool_size=2)})
            for client, name in zip(clients, names)]

        def database(handle):
            cur = handle.cursor()
            try:
                cur.execute('SELECT DATABASE()')
                return cur.fetchone()[0]
            finally:
                cur.close()

        assert [database(h) for h in handles] == names
        old = handles[0]
        replacement = clients[0].open_session({'route': dict(
            route, database=names[1], pool_name='shared', pool_size=2)})
        assert database(old) == names[0]
        assert database(replacement) == names[1]
        clients[0].close_session(old)
        clients[0].close_session(replacement)
        clients[1].close_session(handles[1])
        assert set(mariadb._CONNECTION_POOLS) == registry
        proof['checks'].append('private_names_and_live_generation_retirement')
        session = clients[0].open_session(
            {'route': dict(route, database=names[0])})

        def execute(source, parameters=()):
            token = clients[0].execute(session, {
                'source': source, 'parameters': parameters})
            pages = []
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                page = clients[0].describe_result(token)
                pages.append(page)
                if page['complete']:
                    assert not page['payload'].get('error'), page
                    return pages
            raise AssertionError('native stream did not finish')

        def rows(pages):
            return [row for page in pages for row in page['payload']['rows']]

        source = ("SELECT CAST('0000-00-00' AS DATE), "
                  "CAST('2020-00-15' AS DATE), "
                  "CAST('0000-00-00 00:00:00.000000' AS DATETIME(6)), "
                  "CAST('-838:59:59.123456' AS TIME(6)), "
                  "CAST('9007199254740993' AS UNSIGNED), "
                  "CAST('1.2300' AS DECIMAL(20,4)), NULL, ")
        expected = ('0000-00-00', '2020-00-15',
                    '0000-00-00 00:00:00.000000', '-838:59:59.123456',
                    '9007199254740993', '1.2300', None,
                    {'encoding': 'base64', 'data': '/wA=', 'byte_length': 2})
        assert rows(execute(source + "X'FF00'")) == [expected]
        assert rows(execute(source + '%s', [
            {'encoding': 'base64', 'data': '/wA='}])) == [expected]
        proof['checks'].append('exact_text_and_binary_temporals_and_values')
        assert rows(execute('SELECT %(answer)s', {'answer': 42})) == [(42,)]
        for number in ('18446744073709551615', '18446744073709551616',
                       '-9223372036854775809', '9' * 65):
            for binary in (False, True):
                bound = [{'encoding': 'integer', 'data': number}]
                if binary:
                    bound.append({'encoding': 'base64', 'data': 'AA=='})
                numeric = rows(execute('SELECT ?' + (', ?' if binary else ''),
                                       bound))
                assert numeric[0][0] == number
        proof['checks'].append('wide_integer_binding_in_both_protocols')
        execute('CREATE TABLE native_columns '
                '(txt VARCHAR(12) CHARACTER SET utf8mb4, '
                'id UUID, addr INET6, doc JSON, vec VECTOR(2))')
        execute("INSERT INTO native_columns VALUES ('été日本😀', "
                "'018f22cf-9440-7000-8000-000000000001', '2001:db8::1', "
                "'{\"n\":9007199254740993}', VEC_FromText('[1,2]'))")
        typed = execute('SELECT * FROM native_columns')
        assert rows(typed)[0][:4] == (
            'été日本😀', '018f22cf-9440-7000-8000-000000000001',
            '2001:db8::1', '{"n":9007199254740993}')
        assert rows(typed)[0][4]['byte_length'] == 8
        native_columns = next(p['schema']['columns'] for p in typed
                              if p['payload'].get('has_page'))
        assert native_columns[0]['native_metadata']['length'] == 48
        proof['checks'].append(
            'native_extended_types_unicode_and_named_bindings')

        execute('CREATE PROCEDURE driver_sets() BEGIN '
                'SELECT 1 AS duplicate, 2 AS duplicate; '
                'SELECT 3 AS other; END')
        pages = execute('CALL driver_sets()')
        populated = [p for p in pages if p['payload']['rows']]
        assert rows(pages) == [(1, 2), (3,)]
        assert [p['payload']['result_set_index'] for p in populated] == [0, 1]
        assert [c['name'] for c in populated[0]['schema']['columns']] == [
            'duplicate', 'duplicate#2']
        proof['checks'].append(
            'ordered_native_result_sets_and_duplicate_labels')
        token = clients[0].execute(session, {'source': 'SELECT SLEEP(20)'})
        deadline = time.monotonic() + 5
        while token.identity is None and not token.finished.is_set():
            assert time.monotonic() < deadline
            time.sleep(0.01)
        assert clients[0].cancel(token)
        token.worker.join(5)
        assert token.finished.is_set()
        page = clients[0].describe_result(token)
        assert page['payload']['cancelled']
        assert not page['payload'].get('session_reuse_blocked')
        assert rows(execute('SELECT 42')) == [(42,)]
        proof['checks'].append('native_cancel_and_verified_reuse')
        clients[0].close_session(session)
        cursor.execute('SELECT VERSION()')
        proof['server_version'] = cursor.fetchone()[0]
        proof['driver_version'] = mariadb.__version__
        proof['connector_c_version'] = mariadb.mariadbapi_version
        proof['complete'] = True
    finally:
        for client in clients:
            client.close()
        for name in made:
            cursor.execute(f'DROP DATABASE `{name}`')
        cursor.close()
        owner.close()
        (evidence / 'summary.json').write_text(json.dumps(proof, indent=2))
    return proof


def run(image, evidence, qualification=qualify, *, tls=False):
    evidence.mkdir(parents=True, exist_ok=False)
    name = 'cdeadmin-mariadb-driver-' + secrets.token_hex(8)
    identity = _image_identity(image)
    started = False
    mounts, server_options, route_options = [], [], {}
    if tls:
        certificates = evidence.resolve() / 'certificates'
        certificates.mkdir()
        subprocess.run([
            'openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
            '-days', '2', '-subj', '/CN=owned-mariadb-fixture',
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
                         'ssl_verify_cert': True, 'ssl': True}
    try:
        subprocess.run([
            'docker', 'run', '-d', '--rm', '--name', name,
            '-e', 'MARIADB_ALLOW_EMPTY_ROOT_PASSWORD=1',
            '-p', '127.0.0.1::3306', *mounts, image, *server_options,
        ], check=True, capture_output=True)
        started = True
        port = _wait_until_ready('mariadb', name, 180)
        return qualification(
            {'host': '127.0.0.1', 'port': port, 'user': 'root',
             'connect_timeout': 5, **route_options}, evidence / 'native')
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
    parser.add_argument('--image', default='mariadb:12.2.2')
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    proof = run(args.image, args.evidence)
    raise SystemExit(0 if proof['complete'] else 1)

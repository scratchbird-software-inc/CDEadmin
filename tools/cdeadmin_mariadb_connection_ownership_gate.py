"""Native MariaDB provider pool isolation in uniquely owned schemas/accounts.
"""
import argparse
import json
from pathlib import Path
import secrets
import traceback
from types import SimpleNamespace

from tools.cdeadmin_mysql_family_object_live_orchestrator import (
    _image_identity, _wait_until_ready,
)
from pgadmin.cdeadmin.providers.mysql_family.provider import (
    MARIADB_PROFILE, _create_client,
)
from pgadmin.cdeadmin.security import SecretLease
from tools.cdeadmin_mariadb_driver_gate import run


def qualify(route, evidence):
    import mariadb as native
    from mariadb import _CONNECTION_POOLS

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
        value = _create_client(
            MARIADB_PROFILE, permissions, SimpleNamespace(
                pool_namespace="ownership"))
        clients.append(value)
        return value

    def failure(stage, exc):
        frames = traceback.extract_tb(exc.__traceback__)
        return {'stage': stage, 'type': type(exc).__name__,
                'locations': [{'file': Path(f.filename).name, 'line': f.lineno}
                              for f in frames]}

    try:
        cursor.execute('SELECT VERSION()')
        result['version'] = cursor.fetchone()[0]
        assert result['version'].split('-')[0] == '12.2.2'
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
                    pool_reset_connection=True)
        base.pop('password', None)
        first, second = client(), client()
        a = first.open_session({'route': base})
        b = second.open_session({'route': dict(base, database=schemas[1])})
        assert sql(a, 'SELECT * FROM marker') == [(0,)]
        assert sql(b, 'SELECT * FROM marker') == [(1,)]
        assert a.thread_id != b.thread_id
        result['checks'].append('same_pool_name_separate_provider_and_schema')
        ident = a.thread_id
        sql(a, 'INSERT INTO marker VALUES (99)')
        sql(a, 'SET @owned_test = 17')
        first.close_session(a)
        a = first.open_session({'route': base})
        assert a.thread_id == ident
        assert sql(a, 'SELECT * FROM marker') == [(0,)]
        assert sql(a, 'SELECT @owned_test') == [(None,)]
        assert a.autocommit is False
        assert a.database == schemas[0]
        result['checks'].append('native_rollback_reset_reuse')
        first.close_session(a)
        b_id = b.thread_id
        # A changed secret must authenticate a fresh session, even if an old
        # leased session remains alive under MariaDB's native account
        # semantics.
        password = secrets.token_urlsafe(24)
        cursor.execute(f"ALTER USER '{account}'@'%' IDENTIFIED BY %s",
                       (password,))
        replacement = second.open_session({'route': base})
        assert replacement.thread_id != b_id
        assert sql(b, 'SELECT * FROM marker') == [(1,)]
        second.close_session(b)
        second.close_session(replacement)
        result['checks'].append('credential_and_route_generation_rotation')
        unpooled = dict(base)
        unpooled.pop('pool_size')
        unpooled.pop('pool_name')
        one = first.open_session({'route': unpooled})
        two = first.open_session({'route': unpooled})
        assert one.thread_id != two.thread_id
        first.close_session(one)
        first.close_session(two)
        assert set(_CONNECTION_POOLS) == before
        result['checks'].append('reset_only_unpooled_no_global_registry')
    except Exception as exc:
        result['failures'].append(failure('checks', exc))
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
            result['failures'].append(failure('cleanup', exc))
        cursor.close()
        owner.close()
    result['complete'] = not result['failures']
    (evidence / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='mariadb:12.2.2')
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    proof = run(args.image, args.evidence, qualify)
    raise SystemExit(0 if proof['complete'] else 1)

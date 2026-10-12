"""Owned-server qualification of MariaDB LOCAL file policy and native imports.
"""
import argparse
import json
import secrets
from pathlib import Path
from types import SimpleNamespace

from tools.cdeadmin_mariadb_driver_gate import run
from tools.cdeadmin_mariadb_execution_gate import collect
from pgadmin.cdeadmin.providers.mysql_family.provider import (
    MARIADB_PROFILE, _create_client,
)


def qualify(route, evidence):
    import mariadb as native
    evidence.mkdir(parents=True, exist_ok=False)
    directory = evidence.resolve() / 'allowed'
    directory.mkdir()
    allowed = directory / 'owned-é.tsv'
    denied = evidence.resolve() / 'outside.tsv'
    allowed.write_text('1\tété\n2\t日本\n', encoding='utf8')
    denied.write_text('3\toutside\n', encoding='utf8')
    proof = {'complete': False, 'checks': []}
    owner = native.connect(**route)
    cursor = owner.cursor()
    schema = 'owned_import_' + secrets.token_hex(8)
    client = _create_client(
        MARIADB_PROFILE, SimpleNamespace(acquire_secret=None),
        SimpleNamespace(pool_namespace="imports"))
    cursor.execute('SELECT @@GLOBAL.local_infile')
    original = int(cursor.fetchone()[0])
    created = False
    try:
        cursor.execute(f'CREATE DATABASE `{schema}`')
        created = True
        cursor.execute(f'CREATE TABLE `{schema}`.sample '
                       '(id INT, txt TEXT CHARACTER SET utf8mb4)')
        cursor.execute('SET GLOBAL local_infile=ON')
        for label, path, options, expected in (
                ('disabled', allowed, {'local_infile': False}, False),
                ('enabled', allowed, {'local_infile': True}, True)):
            handle = client.open_session({'route': dict(
                route, database=schema,
                autocommit=False, **options)})
            pages = collect(client, client.execute(handle, {
                'source': 'LOAD DATA LOCAL INFILE %s INTO TABLE sample '
                          'CHARACTER SET utf8mb4',
                'parameters': [str(path)]}))
            error = pages[-1]['payload']['error']
            assert (error is None) == expected, (label, error)
            cursor.execute(f'SELECT COUNT(*) FROM `{schema}`.sample')
            assert cursor.fetchone() == (0,)
            owner.rollback()
            if expected:
                client.control_transaction(handle, 'commit')
                cursor.execute(f'SELECT id,txt FROM `{schema}`.sample '
                               'ORDER BY id')
                assert cursor.fetchall() == [(1, 'été'), (2, '日本')]
                owner.rollback()
            client.close_session(handle)
            proof['checks'].append(label)
        proof['complete'] = True
    finally:
        client.close()
        if created:
            cursor.execute(f'DROP DATABASE `{schema}`')
        cursor.execute(f'SET GLOBAL local_infile={original}')
        cursor.close()
        owner.close()
        allowed.unlink()
        denied.unlink()
        directory.rmdir()
        (evidence / 'summary.json').write_text(json.dumps(proof, indent=2))
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='mariadb:12.2.2')
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.image, args.evidence, qualify)
    raise SystemExit(0 if result['complete'] else 1)

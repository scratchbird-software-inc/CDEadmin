"""Qualify oversized native result rows and caller-owned LOB finality."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import secrets
from types import SimpleNamespace

from tools.cdeadmin_mariadb_driver_gate import run
from tools.cdeadmin_mariadb_execution_gate import collect
from tools.mysql_driver_gate_support import provider_access
from pgadmin.cdeadmin.providers.mysql_family.provider import MARIADB_PROFILE, _create_client


def qualify(route, evidence, *, password=None):
    import mariadb
    evidence.mkdir(parents=True, exist_ok=False)
    proof = {'complete': False, 'checks': [], 'binary_bytes': 1024 * 1024}
    schema = 'owned_lob_' + secrets.token_hex(8)
    owner = mariadb.connect(**route, autocommit=True,
        **({'password': password} if password is not None else {})); cursor = owner.cursor()
    native_route, permissions = provider_access(route, password)
    client = _create_client(MARIADB_PROFILE, permissions,
                           SimpleNamespace(pool_namespace='owned-lob'))
    handle = None
    try:
        cursor.execute('CREATE DATABASE `' + schema + '`')
        cursor.execute('CREATE TABLE `' + schema + '`.lob_values '
                       '(id INT PRIMARY KEY, payload LONGBLOB, txt LONGTEXT CHARACTER SET utf8mb4)')
        handle = client.open_session({'route': {**native_route, 'database': schema, 'autocommit': False}})
        binary = bytes(range(256)) * 4096
        text = '🔥é日本' * 50000
        def execute(source, parameters=()):
            pages = collect(client, client.execute(handle, {'source': source, 'parameters': parameters}))
            assert not pages[-1]['payload'].get('error'), pages[-1]['payload'].get('error')
            return [row for page in pages for row in page['payload']['rows']]
        parameters = [1, {'encoding': 'base64', 'data': base64.b64encode(binary).decode('ascii')}, text]
        execute('INSERT INTO lob_values VALUES (?, ?, ?)', parameters)
        cursor.execute('SELECT COUNT(*) FROM `' + schema + '`.lob_values'); assert cursor.fetchone() == (0,)
        rows = execute('SELECT payload,txt FROM lob_values')
        assert len(rows) == 1 and rows[0][1] == text
        envelope = rows[0][0]
        assert envelope['byte_length'] == len(binary)
        assert base64.b64decode(envelope['data'], validate=True) == binary
        proof['checks'].append('one_oversized_row_preserves_full_mib_binary_and_unicode_text_in_native_result_buffer')
        client.control_transaction(handle, 'rollback')
        cursor.execute('SELECT COUNT(*) FROM `' + schema + '`.lob_values'); assert cursor.fetchone() == (0,)
        execute('INSERT INTO lob_values VALUES (?, ?, ?)', parameters)
        client.control_transaction(handle, 'commit')
        cursor.execute('SELECT OCTET_LENGTH(payload),SHA2(payload,256),SHA2(txt,256) FROM `' + schema + '`.lob_values')
        assert cursor.fetchone() == (len(binary), hashlib.sha256(binary).hexdigest(), hashlib.sha256(text.encode('utf8')).hexdigest())
        proof['checks'].append('independent_native_lengths_and_hashes_verify_rollback_then_commit_without_loss')
        proof['text_utf8_bytes'] = len(text.encode('utf8'))
        proof['complete'] = True
    finally:
        if handle is not None: client.close_session(handle)
        client.close(); cursor.execute('DROP DATABASE IF EXISTS `' + schema + '`')
        cursor.close(); owner.close()
        (evidence / 'summary.json').write_text(json.dumps(proof, indent=2))
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='mariadb:12.2.2')
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.image, args.evidence, qualify)
    raise SystemExit(0 if result['complete'] else 1)

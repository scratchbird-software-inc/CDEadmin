"""Owned DuckDB database-copy qualification with independent data observation."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def qualify_encryption(provider, client, sid, handle, route, directory, proof):
    """Independent native copies between stores; never replace the source file."""
    import duckdb
    from pgadmin.cdeadmin.providers.duckdb.attachments import quote
    cases = [(None, 'GCM'), ('GCM', None), ('GCM', 'CTR'), ('CTR', 'GCM')]
    for ordinal, (source_cipher, destination_cipher) in enumerate(cases):
        root = directory / ('encryption-copy-' + str(ordinal));root.mkdir()
        source_key, destination_key = 'owned source key ' + str(ordinal), 'owned destination key ' + str(ordinal)
        aliases = ['Source encrypted . " é ' + str(ordinal), 'Destination encrypted . " é ' + str(ordinal)]
        paths = [root / 'source.duckdb', root / 'destination.duckdb']
        def attachment(draft):
            value = provider.attachment_action({'session_id': sid, 'language_profile': 'duckdb-sql',
                'operation': 'review', 'draft': draft}, route)
            payload = {'session_id': sid, 'language_profile': 'duckdb-sql', 'operation': 'apply',
                'review_id': value['review_id'], 'review_digest': value['review_digest'],
                'confirmation': value['alias'], 'confirmed': True}
            result = provider.attachment_action(payload, route)
            assert result['native_acknowledged'] and result['rediscovery_verified'], result
            assert provider.attachment_action(payload, route) == result
            assert all(key not in json.dumps(result) for key in (source_key, destination_key))
            return result
        for path, alias, cipher, key in zip(paths, aliases, (source_cipher, destination_cipher), (source_key, destination_key)):
            attachment({'action': 'attach', 'alias': alias, 'path': str(path), 'read_only': False,
                'create_if_missing': True, **({'encryption_key': key, 'encryption_cipher': cipher} if cipher else {})})
        client.control_transaction(handle, 'commit')
        source, destination = map(quote, aliases)
        handle.execute('CREATE SCHEMA ' + source + '."area . é"')
        handle.execute('CREATE TABLE ' + source + '."area . é".rows(id INT, payload STRUCT("field . é" VARCHAR, values INT[]), bytes BLOB, exact DECIMAL(30,8))')
        handle.execute('INSERT INTO ' + source + '."area . é".rows VALUES '
            '(42,{\'field . é\':\'native encrypted copy payload α\',values:[1,NULL,3]},\'\\x00\\xFF\'::BLOB,12345678901234567890.12345678),'
            '(NULL,NULL,NULL,NULL)')
        expected = handle.execute('SELECT * FROM ' + source + '."area . é".rows ORDER BY id NULLS LAST').fetchall()
        client.control_transaction(handle, 'commit')
        handle.execute('CREATE TEMP TABLE "private encryption copy" AS SELECT 19 id')
        transaction = handle.execute('SELECT current_transaction_id()').fetchone()[0]
        def copy(operation, **fields):
            value = provider.database_copy_action({'session_id': sid, 'language_profile': 'duckdb-sql',
                'operation': operation, **fields}, route)
            client._database_copy_reviews[value['review_id']]['worker'].join(timeout=60)
            result = provider.database_copy_action({'session_id': sid, 'language_profile': 'duckdb-sql',
                'operation': 'receipt', 'review_id': value['review_id']}, route)
            assert result['phase'] == 'finished', result
            assert all(key not in json.dumps(result) for key in (source_key, destination_key))
            return result
        def run_copy():
            record = copy('review', draft={'source_catalog': aliases[0], 'destination_catalog': aliases[1], 'mode': 'ALL'})
            assert record['state'] == 'reviewed', record
            assert record['storage']['source']['encrypted'] == bool(source_cipher)
            assert record['storage']['destination']['encrypted'] == bool(destination_cipher)
            assert record['storage']['destination']['cipher'] == destination_cipher
            if source_cipher and not destination_cipher:
                assert any('without database encryption' in warning for warning in record['warnings'])
            payload = dict(review_id=record['review_id'], review_digest=record['review_digest'],
                confirmation=aliases[1], confirmed=True)
            result = copy('apply', **payload)
            assert result['state'] == 'acknowledged' and result['rediscovery_verified'], result
            assert result['storage_observation']['verified']
            assert copy('apply', **payload) == result
            assert handle.execute('SELECT * FROM ' + destination + '."area . é".rows ORDER BY id NULLS LAST').fetchall() == expected
            return result
        run_copy()
        assert handle.execute('SELECT current_transaction_id()').fetchone()[0] == transaction
        assert handle.execute('SELECT id FROM "private encryption copy"').fetchone() == (19,)
        observer = handle.cursor()
        try:
            assert observer.execute('SELECT count(*) FROM duckdb_tables() WHERE database_name=?', [aliases[1]]).fetchone() == (0,)
            client.control_transaction(handle, 'rollback')
            assert handle.execute('SELECT count(*) FROM duckdb_tables() WHERE database_name=?', [aliases[1]]).fetchone() == (0,)
            final = run_copy()
            client.control_transaction(handle, 'commit')
        finally:observer.close()
        for alias in aliases:
            attachment({'action': 'detach', 'alias': alias, 'if_exists': False})
        client.control_transaction(handle, 'commit')
        for path, cipher, intended_key, wrong_key in zip(paths, (source_cipher, destination_cipher),
                (source_key, destination_key), (destination_key, source_key)):
            reopened = duckdb.connect()
            try:
                options = 'READ_ONLY' + (", ENCRYPTION_KEY ?, ENCRYPTION_CIPHER '" + cipher + "'" if cipher else '')
                sql = "ATTACH '" + str(path).replace("'", "''") + "' AS verified (" + options + ')'
                reopened.execute(sql, [intended_key] if cipher else [])
                assert reopened.execute('SELECT * FROM verified."area . é".rows ORDER BY id NULLS LAST').fetchall() == expected
                assert reopened.execute("SELECT encrypted,cipher FROM duckdb_databases() WHERE database_name='verified'").fetchone() == (bool(cipher), cipher)
            finally:reopened.close()
            if cipher:
                refused = duckdb.connect()
                try:
                    try:refused.execute(sql, [wrong_key])
                    except duckdb.Error as error:
                        assert 'wrong encryption key' in str(error).lower(), type(error).__name__
                    else:raise AssertionError('An independently reopened encrypted store accepted the other store key')
                finally:refused.close()
        proof.setdefault('encrypted_copies', []).append({'root': str(directory.name),
            'source_cipher': source_cipher, 'destination_cipher': destination_cipher,
            'review_id': final['review_id'], 'native_bound_attachment_and_reviewed_copy': True,
            'original_transaction_and_rollback_preserved': True, 'no_replay': True,
            'independent_reopen_exact_rows_types_and_encryption': True,
            'source_remains_readable_with_original_key': True, 'other_store_key_refused_when_encrypted': True,
            'keys_absent_from_public_receipts': True})


def qualify(output):
    import config  # noqa: F401
    import duckdb
    from pgadmin.cdeadmin.providers.duckdb.provider import DuckDBPilotProvider, _create_client
    from pgadmin.cdeadmin.providers.duckdb.attachments import quote
    if duckdb.__version__ != '1.5.2':
        raise ValueError('Select native DuckDB 1.5.2')
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Qualification evidence belongs outside source')
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    proof = {'complete': False, 'native_version': duckdb.__version__, 'full_product_complete': False,
        'history_testing': 'not run', 'checks': [], 'source_sha256': {}}
    for name in ['tools/cdeadmin_duckdb_database_copy_qualification.py',
            'web/pgadmin/cdeadmin/providers/duckdb/database_copy.py',
            'web/pgadmin/cdeadmin/providers/duckdb/attachments.py',
            'web/pgadmin/cdeadmin/providers/duckdb/driver.py',
            'web/pgadmin/cdeadmin/providers/duckdb/provider.py',
            'web/pgadmin/cdeadmin/data_studio/studio.py',
            'web/pgadmin/cdeadmin/workspace/service.py',
            'web/pgadmin/browser/server_groups/servers/__init__.py',
            'web/pgadmin/static/js/Dialogs/DuckDBDatabaseCopy.jsx',
            'web/pgadmin/static/js/Dialogs/ProviderWorkspaceContent.jsx']:
        proof['source_sha256'][name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    try:
        for memory in (False, True):
            directory = output / ('memory' if memory else 'file')
            directory.mkdir()
            source_file = directory / 'source . é.duckdb'
            destination_file = directory / 'destination . é.duckdb'
            seed = duckdb.connect(str(source_file))
            seed.execute('CREATE SCHEMA "native . é"; CREATE TYPE "native . é".mood AS ENUM (\'calm\',\'busy\'); '
                'CREATE SEQUENCE "native . é".counter START 17; '
                'CREATE TABLE "native . é".rows(id BIGINT, payload STRUCT("field . é" VARCHAR, values INT[]), '
                'mood "native . é".mood, exact DECIMAL(30,8)); '
                'CREATE INDEX by_id ON "native . é".rows(id); '
                'CREATE VIEW "native . é".v AS SELECT id,payload FROM "native . é".rows; '
                'CREATE MACRO "native . é".twice(x) AS x*2')
            seed.execute('INSERT INTO "native . é".rows SELECT i, {\'field . é\':i::VARCHAR, values:[1,NULL,3]}, '
                '\'calm\'::"native . é".mood, 12345678901234567890.12345678 FROM range(9000) r(i)')
            expected = seed.execute('SELECT count(*),sum(id),sum(exact) FROM "native . é".rows').fetchone()
            seed.close()
            duckdb.connect(str(destination_file)).close()
            route = {'database': ':memory:' if memory else str(directory / 'primary.duckdb'),
                'filesystem_root': str(directory), 'allow_memory': True}
            client = _create_client()
            provider = DuckDBPilotProvider(SimpleNamespace(endpoint_id='owned-copy', session_namespace='owned-copy'),
                SimpleNamespace(require=lambda *_: None), client)
            handle = None
            try:
                sid = provider.open_session({'route': route})['session_id']
                handle = provider._sessions[sid].handle
                source, destination = 'Source . " é', 'Destination . " é'
                for path, alias in ((source_file, source), (destination_file, destination)):
                    handle.execute("ATTACH '" + str(path).replace("'", "''") + "' AS " + quote(alias))
                client.control_transaction(handle, 'commit')
                def request(operation, **fields):
                    return provider.database_copy_action({'session_id': sid, 'language_profile': 'duckdb-sql',
                        'operation': operation, **fields}, route)
                def finish(record):
                    client._database_copy_reviews[record['review_id']]['worker'].join(timeout=60)
                    value = request('receipt', review_id=record['review_id'])
                    assert value['phase'] == 'finished', value
                    return value
                def review(mode):
                    value = finish(request('review', draft={'source_catalog': source,
                        'destination_catalog': destination, 'mode': mode}))
                    assert value['state'] == 'reviewed', value
                    return value
                def apply(record):
                    payload = dict(review_id=record['review_id'], review_digest=record['review_digest'],
                        confirmation=destination, confirmed=True)
                    result = finish(request('apply', **payload))
                    assert request('apply', **payload) == result
                    return result
                handle.execute('CREATE TEMP TABLE private_rows AS SELECT 42 id')
                transaction = handle.execute('SELECT current_transaction_id()').fetchone()[0]
                schema = apply(review('SCHEMA'))
                assert schema['rediscovery_verified'], schema
                target = quote(destination) + '."native . é".rows'
                assert handle.execute('SELECT count(*) FROM ' + target).fetchone() == (0,)
                assert handle.execute('SELECT current_transaction_id()').fetchone()[0] == transaction
                assert handle.execute('SELECT id FROM private_rows').fetchone() == (42,)
                client.control_transaction(handle, 'commit')
                data = apply(review('DATA'))
                assert data['rediscovery_verified'], data
                observer = handle.cursor()
                try:
                    assert observer.execute('SELECT count(*) FROM ' + target).fetchone() == (0,)
                    assert handle.execute('SELECT count(*),sum(id),sum(exact) FROM ' + target).fetchone() == expected
                    client.control_transaction(handle, 'rollback')
                    assert observer.execute('SELECT count(*) FROM ' + target).fetchone() == (0,)
                    assert apply(review('DATA'))['rediscovery_verified']
                    client.control_transaction(handle, 'commit')
                    assert observer.execute('SELECT count(*),sum(id),sum(exact) FROM ' + target).fetchone() == expected
                finally:
                    observer.close()
                stale = review('DATA')
                handle.execute('UPDATE ' + target + ' SET id=99999 WHERE id=0')
                refused = apply(stale)
                assert refused['state'] == 'refused' and not refused['native_dispatched']
                client.control_transaction(handle, 'rollback')
                proof['checks'].append({'root': 'memory' if memory else 'file',
                    'schema_and_data_modes': True, 'native_rows': expected[0],
                    'exact_decimal_nested_enum_index_view_macro_sequence': True,
                    'original_transaction_and_private_temp_preserved': True,
                    'independent_pending_rollback_commit_observed': True,
                    'stale_data_refused_before_dispatch': True, 'repeated_apply_only_reads': True})
                qualify_encryption(provider, client, sid, handle, route, directory, proof)
            finally:
                if handle is not None:
                    for record in client._database_copy_reviews.values():
                        record['worker'].join(timeout=60)
                client.close()
            independent = duckdb.connect(str(destination_file), read_only=True)
            try:
                assert independent.execute('SELECT count(*),sum(id),sum(exact) FROM "native . é".rows').fetchone() == expected
                assert independent.execute('SELECT payload."field . é",payload.values FROM "native . é".rows WHERE id=8999').fetchone() == ('8999',[1,None,3])
                assert independent.execute('SELECT "native . é".twice(7)').fetchone() == (14,)
            finally:
                independent.close()
        proof['complete'] = True
    finally:
        (output / 'proof.json').write_text(json.dumps(proof, indent=2, ensure_ascii=False) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = qualify(args.output)
    print(json.dumps({'complete': result['complete'], 'checks': len(result['checks'])}))

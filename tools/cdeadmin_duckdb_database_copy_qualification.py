"""Owned DuckDB database-copy qualification with independent data observation."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


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

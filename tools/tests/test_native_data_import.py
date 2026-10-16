"""Native typed DDN restore, generated columns, rollback and durable no replay."""
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.workspace.native_data_import import preview, apply, NativeDataApplications


@pytest.mark.parametrize('engine', ['sqlite', 'duckdb'])
def test_native_capture_import_exact_types_generated_values_and_durable_receipt(tmp_path, engine):
    if engine == 'sqlite':
        import sqlite3
        from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider as Provider, _create_client, _resource_id
        native = sqlite3.connect(tmp_path / 'owned.sqlite')
        filename = tmp_path / 'owned.sqlite'
        definitions = '(id INTEGER PRIMARY KEY, big INTEGER, numeric_text TEXT, raw BLOB, invalid TEXT, calculated INTEGER GENERATED ALWAYS AS (id*2))'
        insert = "INSERT INTO source VALUES (1,9223372036854775807,'001.2300',x'0080ff',CAST(x'80ff' AS TEXT))"
        source_id, target_id = [_resource_id('table', ['main'], name) for name in ('source', 'destination')]
    else:
        import duckdb
        from pgadmin.cdeadmin.providers.duckdb.provider import DuckDBPilotProvider as Provider, _create_client, _resource_id
        filename = tmp_path / 'owned.duckdb'
        native = duckdb.connect(str(filename))
        definitions = '(id BIGINT PRIMARY KEY, big HUGEINT, amount DECIMAL(38,10), vals INTEGER[], st STRUCT("odd.key" VARCHAR,n BIGINT), m MAP(VARCHAR,DECIMAL(20,5)), u UNION(a INTEGER,b VARCHAR), ns TIMESTAMP_NS, period INTERVAL, raw BLOB, guid UUID, bits BIT, variable BIGNUM, local TIMETZ, calculated BIGINT GENERATED ALWAYS AS (id*2))'
        insert = """INSERT INTO source VALUES (1,170141183460469231731687303715884105727,12345678901234567890.1234567890,[1,NULL,3],{'odd.key':'quoted','n':9223372036854775807},MAP(['a'],[1.23456]),union_value(b := 'hello'),TIMESTAMP_NS '2026-10-16 12:13:14.123456789',INTERVAL '2 months 3 days 1 microsecond',unhex('0080ff'),UUID '0e5e95ba-27f1-45f5-8502-87bfbeac250e',BIT '001010',CAST('12345678901234567890123456789012345678901234567890' AS BIGNUM),TIMETZ '12:13:14.123456+03:00')"""
        source_id, target_id = [_resource_id('table', ['owned', 'main'], name) for name in ('source', 'destination')]
    provider = Provider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(filename), 'filesystem_root': str(tmp_path)}
    try:
        for name in ('source', 'destination'): native.execute('CREATE TABLE ' + name + definitions)
        native.execute(insert)
        if engine == 'sqlite': native.commit()
        captured = provider.capture_data(route, source_id, endpoint_id='source', target_id='source-file', mode='full')
        source = json.dumps(captured['snapshot'])
        plan = preview(provider, route, engine, source, target_id, endpoint_id='destination', target_id='destination-file')
        assert plan['columns'][-1] != 'calculated'
        assert plan['row_count'] == 1
        store_path = tmp_path / 'imports.json'
        applications = NativeDataApplications(store_path, engine)
        reviewed = applications.review(plan, 7, 'owned-target')
        request = {'review_id': reviewed['review_id'], 'review_digest': reviewed['review_digest'], 'confirmed': True}
        result = applications.apply(request, 7, 'owned-target', lambda record: apply(provider, route, engine, record))
        assert result['state'] == 'native_commit_returned', result
        # Observe from a separate native connection, with all values recomputed
        # by the source engine and recaptured through the exact DDN type path.
        restored = provider.capture_data(route, target_id, endpoint_id='destination', target_id='destination-file', mode='full')
        from pgadmin.cdeadmin.workspace.mysql_data_import import read
        original_metadata, original_rows = read(source, engine=engine)
        restored_metadata, restored_rows = read(json.dumps(restored['snapshot']), engine=engine)
        assert original_rows == restored_rows
        assert restored_rows[0][-1] == 2
        assert provider.client._connections == []
        replay = Mock(side_effect=AssertionError('Committed data must never replay'))
        restarted = NativeDataApplications(store_path, engine)
        assert restarted.apply(request, 7, 'owned-target', replay)['state'] == 'native_commit_returned'
        replay.assert_not_called()
        assert 'rows' not in json.loads(store_path.read_text())['schema_applications'][reviewed['review_id']]['plan']
        with pytest.raises(ValueError): restarted.get(reviewed['review_id'], 8, 'owned-target')
    finally:
        provider.client.close(); native.close()


def test_sqlite_constraint_failure_rolls_back_all_reviewed_rows(tmp_path):
    import sqlite3
    from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider, _create_client, _resource_id
    filename = tmp_path / 'owned.sqlite'
    native = sqlite3.connect(filename)
    native.executescript('CREATE TABLE source(id INTEGER PRIMARY KEY); CREATE TABLE destination(id INTEGER PRIMARY KEY); INSERT INTO source VALUES(1),(2); INSERT INTO destination VALUES(2);')
    provider = SQLiteProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(filename), 'filesystem_root': str(tmp_path)}
    try:
        source = provider.capture_data(route, _resource_id('table', ['main'], 'source'), endpoint_id='source', target_id='source-file', mode='full')
        plan = preview(provider, route, 'sqlite', json.dumps(source['snapshot']), _resource_id('table', ['main'], 'destination'), endpoint_id='destination', target_id='destination-file')
        result = apply(provider, route, 'sqlite', {'plan': plan})
        assert result['state'] == 'native_rollback_returned' and result['rows_completed'] == 1
        assert native.execute('SELECT id FROM destination').fetchall() == [(2,)]
    finally: provider.client.close(); native.close()

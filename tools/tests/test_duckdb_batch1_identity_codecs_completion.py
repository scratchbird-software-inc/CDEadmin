"""Batch 1 DuckDB qualification: DU-AUD-01, DU-AUD-02, DU-AUD-42, DU-AUD-43."""
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
sys.path.insert(0, str(ROOT / 'tools'))
if 'pgadmin' not in sys.modules:
    pkg = ModuleType('pgadmin')
    pkg.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = pkg

duckdb = pytest.importorskip('duckdb')
pytest.importorskip('pyarrow')

from pgadmin.cdeadmin.providers.duckdb.editor_type_rules import (  # noqa: E402
    aggregate_type_rules,
    computed_type_rules,
)
from pgadmin.cdeadmin.providers.duckdb.provider import (  # noqa: E402
    ADMINISTRATION,
    _create_client,
    _resources,
)
from pgadmin.cdeadmin.providers.duckdb.values import parameter, parameters  # noqa: E402
from pgadmin.cdeadmin.providers.native_editor import metadata  # noqa: E402
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402
from pgadmin.cdeadmin.visual_admin.provider import ProviderVisualAdministration  # noqa: E402


def _find(conn, kind, name):
    return next(
        row for row in _resources(conn, {'session_catalog': True})
        if row['resource_kind'] == kind and row['display_name'] == name
    )


def _execute_and_rows(client, handle, sql, bindings=None):
    token = client.execute(handle, {'source': sql, 'parameters': bindings})
    pages = []
    for _ in range(200):
        page = client.describe_result(token)
        pages.append(page)
        if page['complete']:
            break
    assert not pages[-1]['payload'].get('error'), pages[-1]
    return [row for p in pages for row in p['payload']['rows']]


def test_du_aud_01_table_replacement_race_preserves_replacement_and_caller_tx(tmp_path):
    db_path = tmp_path / 'owned.duckdb'
    route = {'database': str(db_path), 'filesystem_root': str(tmp_path)}
    client = _create_client()
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute('CREATE TABLE AUDIT_IDENTITY(original_col INTEGER)')
        target = _find(conn, 'table', 'AUDIT_IDENTITY')
        planned = client.plan_admin_operation({
            'resource_kind': 'table',
            'operation_id': 'drop',
            'draft': {'confirmation': 'AUDIT_IDENTITY'},
            'target_resource': target,
            '_provider_route': route,
        })
        assert planned['command_preview']['native_target_revalidation_required'] is True
        conn.execute('DROP TABLE AUDIT_IDENTITY')
        conn.execute('CREATE TABLE AUDIT_IDENTITY(replacement_col INTEGER)')
        conn.execute('INSERT INTO AUDIT_IDENTITY VALUES (99)')

        with pytest.raises(RelationalClientError) as exc_info:
            client.apply_admin_operation(planned)
        assert getattr(exc_info.value, 'code', None) == 'DUCKDB_STALE_NATIVE_TARGET'
        assert getattr(exc_info.value, 'native_dispatched', None) is False
        assert conn.execute('SELECT replacement_col FROM AUDIT_IDENTITY').fetchall() == [(99,)]

        # Also verify caller-owned session transaction survives stale-target refusal.
        session = client.open_session({'route': route})
        session.execute('CREATE TABLE tx_survivor(v INT)')
        session.execute('INSERT INTO tx_survivor VALUES (7)')
        planned['_provider_session_handle'] = session
        with pytest.raises(RelationalClientError) as exc_tx:
            client.apply_admin_operation(planned)
        assert getattr(exc_tx.value, 'code', None) == 'DUCKDB_STALE_NATIVE_TARGET'
        assert session.execute('SELECT v FROM tx_survivor').fetchall() == [(7,)]
        client.control_transaction(session, 'rollback')
    finally:
        conn.close()
        client.close()


@pytest.mark.parametrize('kind,setup_sql,replace_sql,name,op,draft', [
    ('view', 'CREATE VIEW v1 AS SELECT 1 AS a',
     'DROP VIEW v1; CREATE VIEW v1 AS SELECT 2 AS b', 'v1', 'drop', {'confirmation': 'v1'}),
    ('sequence', 'CREATE SEQUENCE s1 START 1',
     'DROP SEQUENCE s1; CREATE SEQUENCE s1 START 50', 's1', 'drop', {'confirmation': 's1'}),
    ('type', "CREATE TYPE t1 AS ENUM ('a')",
     "DROP TYPE t1; CREATE TYPE t1 AS ENUM ('b')", 't1', 'drop', {'confirmation': 't1'}),
    ('macro', 'CREATE MACRO m1(x) AS x + 1',
     'DROP MACRO m1; CREATE MACRO m1(x) AS x + 100', 'm1', 'drop', {'confirmation': 'm1'}),
    ('schema', 'CREATE SCHEMA sch1',
     'DROP SCHEMA sch1; CREATE SCHEMA sch1', 'sch1', 'drop', {'confirmation': 'sch1'}),
    ('index', 'CREATE TABLE idx_t(a INT, b INT); CREATE INDEX ix1 ON idx_t(a)',
     'DROP INDEX ix1; CREATE INDEX ix1 ON idx_t(b)', 'ix1', 'drop', {'confirmation': 'ix1'}),
])
def test_du_aud_01_all_object_kinds_refuse_same_name_replacement(
    tmp_path, kind, setup_sql, replace_sql, name, op, draft,
):
    db_path = tmp_path / f'{kind}.duckdb'
    route = {'database': str(db_path), 'filesystem_root': str(tmp_path)}
    client = _create_client()
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(setup_sql)
        target = _find(conn, kind, name)
        planned = client.plan_admin_operation({
            'resource_kind': kind,
            'operation_id': op,
            'draft': draft,
            'target_resource': target,
            '_provider_route': route,
        })
        conn.execute(replace_sql)
        with pytest.raises(RelationalClientError) as exc_info:
            client.apply_admin_operation(planned)
        assert getattr(exc_info.value, 'code', None) == 'DUCKDB_STALE_NATIVE_TARGET'
        assert any(r['display_name'] == name and r['resource_kind'] == kind
                   for r in _resources(conn, {}))
    finally:
        conn.close()
        client.close()


def test_du_aud_01_offline_database_file_replacement_refused(tmp_path):
    db_path = tmp_path / 'dropme.duckdb'
    route = {'database': str(db_path), 'filesystem_root': str(tmp_path)}
    conn = duckdb.connect(str(db_path))
    conn.execute('CREATE TABLE original(x INT)')
    target = _find(conn, 'database', 'dropme')
    target['extensions'] = {'cdeadmin': {'database_target_id': 'tgt-1'}}
    conn.close()

    client = _create_client()
    try:
        planned = client.plan_admin_operation({
            'resource_kind': 'database',
            'operation_id': 'drop',
            'draft': {'confirmation': str(db_path)},
            'target_resource': target,
            '_provider_route': route,
        })
        # Replace the physical file with a brand-new database at the same path
        replacement_tmp = tmp_path / 'replacement.duckdb'
        rep = duckdb.connect(str(replacement_tmp))
        rep.execute('CREATE TABLE keep_me(y INT)')
        rep.close()
        db_path.unlink()
        replacement_tmp.rename(db_path)

        with pytest.raises(RelationalClientError) as exc_info:
            client.apply_admin_operation(planned)
        assert getattr(exc_info.value, 'code', None) == 'DUCKDB_STALE_NATIVE_TARGET'
        assert db_path.exists()
    finally:
        client.close()


def test_du_aud_42_and_43_facade_row_read_write_delete_all_native_families(tmp_path):
    db_path = tmp_path / 'families.duckdb'
    route = {'database': str(db_path), 'filesystem_root': str(tmp_path)}
    client = _create_client()
    facade = ProviderVisualAdministration(
        SimpleNamespace(
            endpoint_id='ep1', mode='direct', runtime_verification_state='verified',
            experience_family='relational', engine_id='duckdb',
            profile_id='duckdb-native', provider_id='org.cdeadmin.duckdb',
        ),
        SimpleNamespace(require=lambda *_: None),
        'duckdb', '1.5.2', client,
    )
    handle = client.open_session({'route': route})
    try:
        handle.execute("CREATE TYPE status_enum AS ENUM ('draft', 'ready')")
        handle.execute('''
            CREATE TABLE rich_rows(
                id INTEGER PRIMARY KEY,
                ts_ns TIMESTAMP_NS,
                ts_tz TIMESTAMPTZ,
                tm_tz TIMETZ,
                dt DATE,
                tm TIME,
                iv INTERVAL,
                wide HUGEINT,
                uwide UHUGEINT,
                dec DECIMAL(38, 18),
                uid UUID,
                bits BIT,
                raw BLOB,
                st status_enum,
                arr INTEGER[2],
                lst VARCHAR[],
                rec STRUCT("Field ü" BIGINT, nested TIMESTAMP_NS),
                mp MAP(INTEGER, VARCHAR),
                un UNION(a VARCHAR, b VARCHAR),
                gen INTEGER GENERATED ALWAYS AS (id * 10)
            )
        ''')
        client.control_transaction(handle, 'commit')

        target = _find(handle, 'table', 'rich_rows')
        ctx = {'_provider_route': route, 'session_handle': handle, 'session_id': 'sess-1'}

        # Insert via structured exact envelopes
        ins_plan = client.plan_admin_operation({
            'resource_kind': 'table',
            'operation_id': 'insert',
            'target_resource': target,
            '_provider_route': route,
            '_provider_session_handle': handle,
            'session_id': 'sess-1',
            'draft': {
                'values': {
                    'id': 1,
                    'ts_ns': {'encoding': 'temporal-ticks', 'arrow_type': 'timestamp[ns]', 'ticks': '1767225600123456789'},
                    'ts_tz': {'encoding': 'temporal', 'native_type': 'TIMESTAMPTZ', 'data': '2026-01-01 00:00:00.123456+00:00'},
                    'tm_tz': {'encoding': 'temporal', 'native_type': 'TIMETZ', 'data': '12:34:56.789123+05:30'},
                    'dt': {'encoding': 'temporal-ticks', 'arrow_type': 'date32[day]', 'ticks': '2147483647'},
                    'tm': {'encoding': 'temporal-ticks', 'arrow_type': 'time64[us]', 'ticks': '45296789123'},
                    'iv': {'encoding': 'interval', 'months': 1, 'days': -2, 'nanoseconds': '3000'},
                    'wide': {'encoding': 'integer', 'data': '170141183460469231731687303715884105727'},
                    'uwide': {'encoding': 'integer', 'data': '340282366920938463463374607431768211455'},
                    'dec': {'encoding': 'decimal', 'data': '12345678901234567890.123456789012345678'},
                    'uid': {'encoding': 'uuid', 'data': 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'},
                    'bits': {'encoding': 'bit', 'data': '101001'},
                    'raw': {'encoding': 'base64', 'data': 'AP8=', 'byte_length': 2},
                    'st': 'draft',
                    'arr': [10, 20],
                    'lst': ['alpha', None],
                    'rec': {
                        'Field ü': 77,
                        'nested': {'encoding': 'temporal-ticks', 'arrow_type': 'timestamp[ns]', 'ticks': '-315619199876543211'},
                    },
                    'mp': {'encoding': 'map', 'entries': [[1, 'one'], [2, None]]},
                    'un': {'encoding': 'union', 'tag': 'b', 'value': 'second-branch'},
                },
            },
        })
        ins_plan['_provider_session_handle'] = handle
        assert client.apply_admin_operation(ins_plan)['staged_in_provider_session'] is True

        req_base = {'target_resource': target, '_provider_route': route, 'session_id': 'sess-1'}
        # Read back via facade read_rows
        page = facade.read_rows(req_base, ctx)
        gen_col = next(c for c in page['columns'] if c['name'] == 'gen')
        assert gen_col['editable'] is False and gen_col.get('generated') is True
        ts_col = next(c for c in page['columns'] if c['name'] == 'ts_ns')
        assert ts_col['input_envelope']['admitted'] is True

        row = page['rows'][0]
        vals = row['values']
        assert vals['ts_ns']['ticks'] == '1767225600123456789'
        assert vals['wide'] == '170141183460469231731687303715884105727'
        assert vals['uwide'] == '340282366920938463463374607431768211455'
        assert vals['dec'] == '12345678901234567890.123456789012345678'
        assert vals['un'] == {'tag': 'b', 'type_code': 1, 'value': 'second-branch'}
        assert vals['rec']['nested']['ticks'] == '-315619199876543211'
        assert vals['gen'] == 10

        # Optimistic update of union/status/timestamp_ns while preserving caller transaction
        upd_plan = client.plan_admin_operation({
            'resource_kind': 'table',
            'operation_id': 'update',
            'target_resource': target,
            '_provider_route': route,
            '_provider_session_handle': handle,
            'session_id': 'sess-1',
            'draft': {
                'selector': {'identity_token': row['identity_token']},
                'changes': {
                    'st': 'ready',
                    'un': {'encoding': 'union', 'tag': 'a', 'value': None},
                    'ts_ns': {'encoding': 'temporal', 'native_type': 'TIMESTAMP_NS', 'data': '2026-01-01 00:00:00.987654321'},
                },
            },
        })
        upd_plan['_provider_session_handle'] = handle
        assert client.apply_admin_operation(upd_plan)['staged_in_provider_session'] is True

        page2 = facade.read_rows(req_base, ctx)
        row2 = page2['rows'][0]
        assert row2['values']['st'] == 'ready'
        assert row2['values']['un'] == {'tag': 'a', 'type_code': 0, 'value': None}
        assert row2['values']['ts_ns']['ticks'] == '1767225600987654321'

        # Fail-closed checks: generated column write, scale truncation, sub-us interval, wrong fixed array size
        for bad_changes in (
            {'gen': 99},
            {'dec': 1.25},
            {'dec': {'encoding': 'decimal', 'data': '1.' + '9' * 25}},
            {'iv': {'encoding': 'interval', 'months': 0, 'days': 0, 'nanoseconds': '500'}},
            {'arr': [1, 2, 3]},
            {'ts_tz': {'encoding': 'temporal', 'native_type': 'TIMESTAMPTZ', 'data': '2026-01-01 00:00:00'}},
            {'bits': {'encoding': 'duckdb-arrow-opaque', 'native_type': 'bit', 'storage': 'x'}},
        ):
            fresh_page = facade.read_rows(req_base, ctx)
            with pytest.raises(RelationalClientError):
                client.plan_admin_operation({
                    'resource_kind': 'table',
                    'operation_id': 'update',
                    'target_resource': target,
                    '_provider_route': route,
                    '_provider_session_handle': handle,
                    'session_id': 'sess-1',
                    'draft': {
                        'selector': {'identity_token': fresh_page['rows'][0]['identity_token']},
                        'changes': bad_changes,
                    },
                })

        # Optimistic delete
        del_page = facade.read_rows(req_base, ctx)
        del_plan = client.plan_admin_operation({
            'resource_kind': 'table',
            'operation_id': 'delete',
            'target_resource': target,
            '_provider_route': route,
            '_provider_session_handle': handle,
            'session_id': 'sess-1',
            'draft': {'selector': {'identity_token': del_page['rows'][0]['identity_token']}},
        })
        del_plan['_provider_session_handle'] = handle
        assert client.apply_admin_operation(del_plan)['accepted'] is True
        assert handle.execute('SELECT count(*) FROM rich_rows').fetchone() == (0,)
    finally:
        client.close()


def test_du_aud_43_query_parameter_envelopes_and_fail_closed_opaque(tmp_path):
    client = _create_client()
    route = {'database': str(tmp_path / 'params.duckdb'), 'filesystem_root': str(tmp_path)}
    handle = client.open_session({'route': route})
    try:
        out = _execute_and_rows(
            client, handle,
            'SELECT epoch_ns($ns), $bit::VARCHAR, $iv, $mp, $uid, $arr',
            {
                'ns': {'encoding': 'temporal-ticks', 'arrow_type': 'timestamp[ns]', 'ticks': '-315619199876543211'},
                'bit': {'encoding': 'bit', 'data': '11001'},
                'iv': {'encoding': 'interval', 'months': -1, 'days': 4, 'microseconds': 7},
                'mp': {'encoding': 'map', 'key_type': 'INTEGER', 'value_type': 'VARCHAR', 'entries': [[5, 'five']]},
                'uid': {'encoding': 'uuid', 'data': 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'},
                'arr': {'encoding': 'array', 'element_type': 'INTEGER', 'size': 2, 'items': [8, 9]},
            },
        )[0]
        assert out[0] == '-315619199876543211'
        assert out[1] == '11001'
        assert out[2] == {'months': -1, 'days': 4, 'nanoseconds': '7000'}
        assert out[3] == {'encoding': 'map', 'entries': [[5, 'five']]}
        assert out[4] == 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'
        assert out[5] == [8, 9]

        for invalid in (
            {'encoding': 'duckdb-arrow-opaque', 'native_type': 'bit', 'storage': '10'},
            {'encoding': 'unknown-envelope', 'data': '1'},
            {'encoding': 'interval', 'months': 0, 'days': 0, 'nanoseconds': '1'},
            {'encoding': 'temporal', 'native_type': 'TIMETZ', 'data': '12:00:00'},
            {'encoding': 'map', 'key_type': 'INT', 'value_type': 'VARCHAR', 'entries': [[1, 'a'], [1, 'b']]},
            {'encoding': 'union', 'union_type': 'UNION(a VARCHAR, b VARCHAR)', 'tag': 'a', 'value': 'x'},
        ):
            with pytest.raises(RelationalClientError):
                parameter(invalid)
        with pytest.raises(RelationalClientError):
            parameters({'encoding': 'integer', 'data': '1'})
    finally:
        client.close()


def test_du_aud_02_computed_type_rules_shadowing_truncation_and_user_types():
    with duckdb.connect() as conn:
        conn.execute('CREATE TYPE user_pair AS STRUCT("Field ü" BIGINT)')
        conn.execute('CREATE TABLE t(x user_pair)')
        meta = metadata(conn, 'duckdb')
        comp = meta['context']['computed_type_rules']
        assert comp['ordered_aggregates'] is True
        assert {'arg_max', 'arg_min', 'max_by', 'min_by'} <= set(comp['keyed_aggregates'])
        assert {'list_extract', 'map_extract', 'map_extract_value', 'struct_pack', 'union_extract', 'flatten'} <= set(comp['scalar_functions'])
        assert comp['special_forms'] == {'coalesce': True, 'ifnull': True, 'casts': True, 'scalar_subquery': True}
        tp_res = next(r for r in meta['resources'] if r['resource_kind'] == 'type' and r['display_name'] == 'user_pair')
        assert tp_res['native_type']['kind'] == 'struct'
        assert tp_res['native_type']['fields'][0]['name'] == 'Field ü'

        # Shadowing list_extract and arg_max disables only those rules
        conn.execute('CREATE MACRO list_extract(a, b) AS 42')
        conn.execute('CREATE MACRO coalesce(a, b) AS 99')
        meta_shadowed = metadata(conn, 'duckdb')
        comp_shadowed = meta_shadowed['context']['computed_type_rules']
        assert 'list_extract' not in comp_shadowed['scalar_functions']
        assert 'map_extract' in comp_shadowed['scalar_functions']
        assert comp_shadowed['special_forms']['coalesce'] is False
        assert comp_shadowed['special_forms']['ifnull'] is True

        # Truncation disables computed rules conservatively
        assert computed_type_rules('1.5.2', [], True) == {}
        assert computed_type_rules('1.5.2', [], False, types_truncated=True) == {}
        assert computed_type_rules('1.5.2', [], False, columns_truncated=True) == {}
        assert aggregate_type_rules('1.5.2', [], True) == {}

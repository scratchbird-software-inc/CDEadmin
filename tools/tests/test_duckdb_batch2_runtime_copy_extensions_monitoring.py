"""Batch 2 DuckDB qualification: DU-AUD-03, DU-AUD-05, DU-AUD-06, DU-AUD-07, DU-AUD-08, DU-AUD-40."""
import json
from pathlib import Path
import sqlite3
import sys
import time
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

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

from pgadmin.cdeadmin.providers.duckdb.attachments import action as attachment_action  # noqa: E402
from pgadmin.cdeadmin.providers.duckdb.database_copy import (  # noqa: E402
    action as db_copy_action,
    conversion_preview,
)
from pgadmin.cdeadmin.providers.duckdb.extension_actions import action as ext_action  # noqa: E402
from pgadmin.cdeadmin.providers.duckdb.monitoring import DuckDBMonitor  # noqa: E402
from pgadmin.cdeadmin.providers.duckdb.provider import (  # noqa: E402
    DuckDBPilotProvider,
    _create_client,
)
from pgadmin.cdeadmin.providers.duckdb.runtime_settings import (  # noqa: E402
    action as settings_action,
    validate_open_time_config,
)
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402
from pgadmin.cdeadmin.workspace.duckdb_copy import capabilities as copy_capabilities, plan as copy_plan  # noqa: E402
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export  # noqa: E402


def _open_session(tmp_path, **route_extra):
    db_file = tmp_path / 'primary.duckdb'
    route = {'database': str(db_file), 'filesystem_root': str(tmp_path), **route_extra}
    client = _create_client()
    handle = client.open_session({'route': route})
    return client, handle, route


def test_du_aud_03_runtime_settings_scopes_containment_redaction_and_reset(tmp_path):
    temp_dir = tmp_path / 'owned_temp'
    temp_dir.mkdir()
    client, handle, route = _open_session(tmp_path, config={'threads': 2})
    try:
        inv = settings_action(client, handle, route, {'operation': 'inventory'})
        assert inv['count'] >= 50
        assert inv['registration_open_config'] == {'threads': 2}
        by_name = {s['name']: s for s in inv['settings']}
        assert 'SESSION' in by_name['search_path']['admitted_scopes']
        assert 'GLOBAL' in by_name['threads']['admitted_scopes']
        assert by_name['access_mode']['open_time_only'] is True

        # Session-scoped setting + read-back + reset
        handle.execute('CREATE SCHEMA custom_s')
        set_sp = settings_action(client, handle, route, {
            'operation': 'set', 'name': 'search_path', 'scope': 'SESSION', 'value': 'custom_s,main',
        })
        assert set_sp['verified_on_original_handle'] is True
        assert 'custom_s' in str(set_sp['observed_value'])

        rst_sp = settings_action(client, handle, route, {
            'operation': 'reset', 'name': 'search_path', 'scope': 'SESSION',
        })
        assert rst_sp['verified_on_original_handle'] is True
        assert 'custom_s' not in str(rst_sp['observed_value'])

        # Contained path setting vs escaped path refusal
        set_tmp = settings_action(client, handle, route, {
            'operation': 'set', 'name': 'temp_directory', 'scope': 'GLOBAL', 'value': str(temp_dir),
        })
        assert Path(set_tmp['observed_value']).resolve() == temp_dir.resolve()
        with pytest.raises(ValueError, match='escapes|filesystem_root'):
            settings_action(client, handle, route, {
                'operation': 'set', 'name': 'temp_directory', 'scope': 'GLOBAL',
                'value': str(tmp_path.parent / 'escaped_temp'),
            })

        # Sensitive setting scope enforcement + redaction when httpfs is loaded
        if any(r[0] == 'httpfs' and r[1] for r in handle.execute('SELECT extension_name, installed FROM duckdb_extensions()').fetchall()):
            handle.execute('LOAD httpfs')
            with pytest.raises(ValueError, match='supports native scope GLOBAL'):
                settings_action(client, handle, route, {
                    'operation': 'set', 'name': 's3_secret_access_key', 'scope': 'SESSION', 'value': 'super-secret-value',
                })
            red = settings_action(client, handle, route, {
                'operation': 'set', 'name': 's3_secret_access_key', 'scope': 'GLOBAL', 'value': 'super-secret-value',
            })
            assert red['redacted'] is True
            assert red['observed_value'] == '<redacted>'
            assert 'super-secret-value' not in red['statement']

        # Open-time-only refusal and open-time config containment
        with pytest.raises(ValueError, match='open-time'):
            settings_action(client, handle, route, {
                'operation': 'set', 'name': 'access_mode', 'scope': 'GLOBAL', 'value': 'read_only',
            })
        with pytest.raises(RelationalClientError):
            validate_open_time_config(route, {'temp_directory': '/etc'})
    finally:
        client.close()


def test_du_aud_05_copy_formats_json_parquet_csv_partition_and_ctas_reader(tmp_path):
    db_file = tmp_path / 'copy_rich.duckdb'
    conn = duckdb.connect(str(db_file))
    conn.execute("CREATE TABLE events(region VARCHAR, id INTEGER, note VARCHAR)")
    conn.execute("INSERT INTO events VALUES ('east', 1, 'hello'), ('west', 2, NULL)")
    conn.close()

    provider = DuckDBPilotProvider(SimpleNamespace(), SimpleNamespace(require=Mock()), _create_client())
    route = {'database': str(db_file), 'filesystem_root': str(tmp_path)}
    try:
        caps = copy_capabilities()
        assert caps['formats']['CSV']['available'] is True
        assert caps['formats']['PARQUET']['available'] is True
        assert caps['formats']['JSON']['available'] is True

        captured = provider.capture_catalog(route)
        model = build_export(
            captured['resources'], endpoint_id='ep', target_id='t1',
            generation=captured['generation'], engine='duckdb', native_model=True,
        )
        tbl_id = next(rid for rid, r in model['rows'].items() if r['kind'] == 'table' and r['name'] == 'events')

        # 1. JSON ARRAY export + COPY FROM import
        json_path = tmp_path / 'events.json'
        json_exp = copy_plan(model, {
            'resource_id': tbl_id, 'direction': 'to', 'format': 'JSON',
            'path': str(json_path), 'options': {'json_format': 'ARRAY'},
        }, str(tmp_path))
        assert not json_exp['executed'] and 'FORMAT JSON' in json_exp['source'] and 'ARRAY TRUE' in json_exp['source']

        live = duckdb.connect(str(db_file))
        live.execute(json_exp['source'])
        assert json_path.is_file()
        parsed_json = json.loads(json_path.read_text(encoding='utf-8'))
        assert len(parsed_json) == 2

        # 2. CSV custom delimiter/nullstr export + reader_ctas import
        csv_path = tmp_path / 'events_pipe.csv'
        csv_exp = copy_plan(model, {
            'resource_id': tbl_id, 'direction': 'to', 'format': 'CSV',
            'path': str(csv_path),
            'options': {'header': True, 'delimiter': '|', 'nullstr': '\\N', 'force_quote': ['region']},
        }, str(tmp_path))
        live.execute(csv_exp['source'])
        ctas_plan = copy_plan(model, {
            'direction': 'reader_ctas', 'format': 'CSV', 'path': str(csv_path),
            'target_schema': 'main', 'target_table': 'events_from_csv',
            'options': {'header': True, 'delimiter': '|', 'nullstr': '\\N'},
        }, str(tmp_path))
        live.execute(ctas_plan['source'])
        assert live.execute('SELECT region, id, note FROM events_from_csv ORDER BY id').fetchall() == [
            ('east', 1, 'hello'), ('west', 2, None),
        ]

        # 3. Partitioned Parquet with KV_METADATA + ROW_GROUP_SIZE + reader_insert
        part_dir = tmp_path / 'part_parquet'
        pq_part = copy_plan(model, {
            'resource_id': tbl_id, 'direction': 'to', 'format': 'PARQUET',
            'path': str(part_dir),
            'options': {
                'compression': 'ZSTD',
                'row_group_size': 512,
                'kv_metadata': {'producer': 'scratchrobin'},
                'partition_by': ['region'],
                'overwrite_or_ignore': True,
            },
        }, str(tmp_path))
        assert pq_part['partitioned'] is True
        live.execute(pq_part['source'])
        assert part_dir.is_dir()

        live.execute('DELETE FROM events')
        ins_plan = copy_plan(model, {
            'resource_id': tbl_id, 'direction': 'reader_insert', 'format': 'PARQUET',
            'path': str(part_dir), 'partitioned_source': True,
            'options': {'hive_partitioning': True},
        }, str(tmp_path))
        live.execute(ins_plan['source'])
        assert live.execute('SELECT count(*) FROM events').fetchone() == (2,)
        live.close()
    finally:
        provider.client.close()


def test_du_aud_06_07_08_extensions_attachments_and_foreign_copy_contracts(tmp_path):
    # Create an authentic SQLite3 file fixture for foreign attachment validation
    sq_path = tmp_path / 'foreign.sqlite'
    sq = sqlite3.connect(str(sq_path))
    sq.execute('CREATE TABLE sq_items(id INTEGER PRIMARY KEY, label TEXT)')
    sq.execute("INSERT INTO sq_items VALUES (1, 'from-sqlite')")
    sq.commit()
    sq.close()

    attached_duck = tmp_path / 'second.duckdb'
    d2 = duckdb.connect(str(attached_duck))
    d2.execute('CREATE TABLE d2_items(id INTEGER, name VARCHAR)')
    d2.execute("INSERT INTO d2_items VALUES (10, 'ten')")
    d2.close()

    client, handle, route = _open_session(tmp_path)
    try:
        # DU-AUD-08: Extension capabilities distinguish statically_linked, installed_not_loaded, not_installed
        ext_inv = ext_action(client, handle, route, {'operation': 'inventory'})
        caps = ext_inv['capabilities']
        by_ext = {p['extension_name']: p for p in caps['profiles']}
        assert by_ext['parquet']['runtime_state'] == 'statically_linked_loaded'
        assert 'PARQUET' in by_ext['parquet']['capabilities']['copy_formats']
        assert by_ext['json']['runtime_state'] == 'statically_linked_loaded'
        assert 'JSON' in by_ext['json']['capabilities']['copy_formats']
        assert by_ext['icu']['capabilities']['icu_collation_count'] > 10
        assert by_ext['tpch']['runtime_state'] == 'not_installed'
        assert by_ext['tpch']['bundled_source_is_not_runtime_install'] is True

        # DU-AUD-06: Source adapters & explicit refusal when optional scanner is not installed
        att_inv = attachment_action(client, handle, route, {'operation': 'inventory'})
        adapters = att_inv['source_adapters']
        assert adapters['duckdb']['available'] is True
        if not adapters['sqlite']['loaded']:
            with pytest.raises(ValueError, match='sqlite_scanner'):
                attachment_action(client, handle, route, {
                    'operation': 'review',
                    'draft': {'action': 'attach', 'alias': 'sq', 'source_type': 'sqlite', 'path': str(sq_path)},
                })
        if not adapters['postgres']['loaded']:
            with pytest.raises(ValueError, match='postgres_scanner'):
                attachment_action(client, handle, route, {
                    'operation': 'review',
                    'draft': {
                        'action': 'attach', 'alias': 'pg', 'source_type': 'postgres',
                        'foreign_options': {'host': '127.0.0.1', 'port': 5432, 'dbname': 'db'},
                    },
                })
        # Remote URI refuses writable or inline credentials
        with pytest.raises(ValueError, match='READ_ONLY'):
            attachment_action(client, handle, route, {
                'operation': 'review',
                'draft': {
                    'action': 'attach', 'alias': 'rem', 'source_type': 'httpfs',
                    'path': 'https://example.invalid/data.duckdb', 'read_only': False,
                },
            })
        with pytest.raises(ValueError, match='inline credentials'):
            attachment_action(client, handle, route, {
                'operation': 'review',
                'draft': {
                    'action': 'attach', 'alias': 'rem', 'source_type': 'httpfs',
                    'path': 'https://user:secret@example.invalid/data.duckdb', 'read_only': True,
                },
            })

        # Attach local second.duckdb and run discover_foreign + DU-AUD-07 copy inventory/conversion preview
        rev = attachment_action(client, handle, route, {
            'operation': 'review',
            'draft': {'action': 'attach', 'alias': 'sec', 'path': str(attached_duck), 'read_only': True},
        })
        app = attachment_action(client, handle, route, {
            'operation': 'apply', 'review_id': rev['review_id'],
            'review_digest': rev['review_digest'], 'confirmation': 'sec', 'confirmed': True,
        })
        assert app['state'] == 'acknowledged' and app['rediscovery_verified'] is True

        disc = attachment_action(client, handle, route, {'operation': 'discover_foreign', 'alias': 'sec'})
        assert disc['catalog_type'] == 'duckdb' and disc['advertised_as_duckdb_server'] is False
        assert disc['tables'] == [{'schema': 'main', 'name': 'd2_items', 'column_count': 2, 'estimated_rows': 1}]

        cp_inv = db_copy_action(client, handle, route, {'operation': 'inventory'})
        assert cp_inv['cutover_implied'] is False
        assert any(c['name'] == 'sec' and c['admitted_as_source'] is True for c in cp_inv['catalog_capabilities'])

        # Review database copy from 'sec' into primary catalog and inspect conversion_preview
        cp_rev = db_copy_action(client, handle, route, {
            'operation': 'review',
            'draft': {'source_catalog': 'sec', 'destination_catalog': 'primary', 'mode': 'ALL'},
        })
        for _ in range(100):
            rec = db_copy_action(client, handle, route, {'operation': 'receipt', 'review_id': cp_rev['review_id']})
            if rec['phase'] == 'finished':
                break
            time.sleep(0.02)
        assert rec['state'] == 'reviewed'
        assert rec['conversion_preview']['cutover_implied'] is False
        assert rec['conversion_preview']['tables'][0]['table'] == 'd2_items'

        # Verify foreign conversion_preview notes when source is sqlite
        fake_preview = conversion_preview(
            {'objects': {'tables': [{'schema_name': 'main', 'table_name': 'sq_items'}],
                         'columns': [{'schema_name': 'main', 'table_name': 'sq_items', 'column_name': 'id', 'data_type': 'BIGINT'}]}},
            {'objects': {'columns': [{'schema_name': 'main', 'table_name': 'sq_items', 'column_name': 'id', 'data_type': 'INTEGER'}]}},
            {'type': 'sqlite'}, {'type': 'duckdb'}, 'DATA',
        )
        assert fake_preview['foreign_involved'] is True
        assert fake_preview['cutover_implied'] is False
        assert fake_preview['tables'][0]['type_conversions'] == [
            {'column': 'id', 'source_type': 'BIGINT', 'destination_type': 'INTEGER'}
        ]
    finally:
        client.close()


def test_du_aud_40_monitoring_delivers_all_12_authoritative_metrics(tmp_path):
    metrics_contract = json.loads(
        (ROOT / 'web/pgadmin/cdeadmin/providers/duckdb/duckdb_metrics_1_5_2.json').read_text(encoding='utf-8')
    )
    expected_metric_ids = set(metrics_contract['authoritative_metric_ids'])
    assert len(expected_metric_ids) == 12

    db_path = tmp_path / 'monitored.duckdb'
    conn = duckdb.connect(str(db_path))
    conn.execute('CREATE TABLE sample_tbl(id INT, payload VARCHAR)')
    conn.execute("INSERT INTO sample_tbl SELECT i, repeat('x', 32) FROM range(50) t(i)")
    conn.execute('CHECKPOINT')
    conn.close()

    monitor = DuckDBMonitor(
        {'database': str(db_path), 'filesystem_root': str(tmp_path)},
        target_id='mon-target-1',
    )
    try:
        sample = monitor.sample()
        assert sample['contract_id'] == 'duckdb.metrics.1.5.2.v1'
        assert set(sample['metrics']) == expected_metric_ids
        assert sample['metrics']['duckdb.approx_database_count.approx_count'] >= 1
        assert sample['metrics']['duckdb.connection_count.count'] >= 1
        assert sample['metrics']['duckdb.database_size.block_size'] > 0
        assert sample['metrics']['duckdb.metadata_info.total_blocks'] > 0
        assert {
            'storage', 'database', 'databases', 'extensions',
            'instance_counts', 'memory', 'temporary_files',
            'external_file_cache', 'metadata_info', 'collector_session',
        } <= set(sample['groups'])
        assert sample['identity']['collector_scope'] == 'dedicated-policy-connection'
    finally:
        monitor.close()

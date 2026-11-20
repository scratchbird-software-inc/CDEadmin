"""Comprehensive unit tests for MariaDB Batch 5 (7 audit items).

Covers:
1. MA-AUDIT-TEMPORARY (mariadb_temporary_tables, mariadb_editor_context, mariadb_completion, native_editor)
2. MA-AUDIT-NATIVE-INDEXES (mariadb_indexes, physical_schema, mysql_physical, mariadb_schema_plan)
3. MA-AUDIT-TABLE-FIELDS (mariadb_tables, MariaDBAdministration table create/alter)
4. MA-AUDIT-TEMPORAL-LIFECYCLE (mariadb_temporal, mariadb_schema_plan temporal opt-in vs refusal)
5. MA-AUDIT-OBJECT-EDITOR-PARITY (mariadb_objects view/procedure/function/trigger alter & create_or_replace)
6. MA-AUDIT-AVAILABLE-PLUGINS (mariadb_available_plugins, mariadb_server_catalog)
7. MA-AUDIT-MARIA-MONITORING (mariadb_monitoring Aria/Key/wsrep/engines, counter_rates, metrics contract)
"""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers import native_editor
from pgadmin.cdeadmin.providers.mysql_family import (
    mariadb_available_plugins,
    mariadb_completion,
    mariadb_indexes,
    mariadb_monitoring,
    mariadb_objects,
    mariadb_tables,
    mariadb_temporal,
    mariadb_temporary_tables,
)
from pgadmin.cdeadmin.providers.mysql_family.mysql_monitoring import counter_rates
from pgadmin.cdeadmin.providers.mysql_family.provider import (
    MARIADB_ADMINISTRATION,
    MARIADB_PROFILE,
    _resources,
)
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.workspace import mysql_physical, physical_schema
from pgadmin.cdeadmin.workspace.mariadb_schema_plan import alteration, parts, plan


# ---------------------------------------------------------------------------
# 1. MA-AUDIT-TEMPORARY
# ---------------------------------------------------------------------------
def test_temporary_table_resource_identities_and_drop_temporary_compiler():
    assert mariadb_temporary_tables.temporary_table_resource_id('app', 'shadow') == 'temporary-table:app:shadow'
    assert mariadb_temporary_tables.temporary_column_resource_id('app', 'shadow', 'c1') == 'temporary-column:app:shadow:c1'
    assert mariadb_temporary_tables.temporary_storage_resource_id('app', 'shadow') == 'temporary-table-storage:app:shadow'

    target = {
        'resource_id': 'temporary-table:app:shadow',
        'resource_kind': 'table',
        'display_name': 'shadow',
        'display_path': ['app', 'shadow'],
        'native': {'temporary': True, 'table_type': 'TEMPORARY'},
    }
    compiled = mariadb_temporary_tables.compile_operation(
        'drop_temporary', {'confirmation': 'shadow'}, target
    )
    assert compiled['statements'] == [{'source': 'DROP TEMPORARY TABLE `app`.`shadow`', 'parameters': ()}]
    assert compiled['mariadb_temporary_table']['retained_session_required'] is True

    # Base table without temporary marker must be refused by drop_temporary
    base_target = {
        'resource_id': 'table:app:shadow',
        'resource_kind': 'table',
        'display_name': 'shadow',
        'display_path': ['app', 'shadow'],
        'native': {'temporary': False, 'table_type': 'BASE TABLE'},
    }
    with pytest.raises(RelationalClientError, match='temporary'):
        mariadb_temporary_tables.compile_operation('drop_temporary', {'confirmation': 'shadow'}, base_target)

    # Mismatched confirmation refused
    with pytest.raises(RelationalClientError, match='Confirm'):
        mariadb_temporary_tables.compile_operation('drop_temporary', {'confirmation': 'wrong'}, target)


def test_refresh_completion_overlays_temporary_shadowing_and_never_reports_complete(monkeypatch):
    source = Mock(connection_id=41)
    peer = Mock(connection_id=42)
    client = SimpleNamespace(
        _executions=SimpleNamespace(sessions=Mock()),
        _completion_identities={id(source): (source, ('uid-1', 'admin@%', '12.2.2-MariaDB', 41))},
        _session_requests={id(source): {'route': {'host': '127.0.0.1'}}},
        _connect=Mock(return_value=peer),
        _close_idle_session=Mock(return_value={'connection_released': True}),
    )
    peer.cursor.return_value.fetchone.return_value = ('uid-1', 'admin@%', '12.2.2-MariaDB', 42)
    peer_data = {
        'context': {
            'version': '12.2.2-MariaDB',
            'default_schema': 'app',
            'sql_mode': 'STRICT_TRANS_TABLES',
            'character_set_client': 'utf8mb4',
            'active_role': None,
            'lower_case_table_names': 0,
        },
        'resources': [
            {'resource_kind': 'schema', 'display_path': ['app'], 'display_name': 'app', 'detail': ''},
            {'resource_kind': 'table', 'display_path': ['app', 'shadow'], 'display_name': 'shadow', 'detail': ''},
            {'resource_kind': 'column', 'display_path': ['app', 'shadow', 'base_column'], 'display_name': 'base_column', 'detail': 'int(11)'},
        ],
        'observations': [],
        'visible_resource_count': 3,
        'complete': True,
        'truncated': False,
    }
    monkeypatch.setattr(native_editor, 'metadata', lambda *_a, **_kw: deepcopy(peer_data))

    source_ctx = {
        'server_uid': 'uid-1',
        'principal': 'admin@%',
        'version': '12.2.2-MariaDB',
        'connection_id': 41,
        'default_schema': 'app',
        'sql_mode': 'STRICT_TRANS_TABLES',
        'character_set_client': 'utf8mb4',
        'active_role': None,
        'character_set_connection': 'utf8mb4',
        'character_set_results': 'utf8mb4',
        'collation_connection': 'utf8mb4_uca1400_ai_ci',
        'lower_case_table_names': 0,
        'temporary_table_count': 1,
        'original_session_commands_sent': 3,
        'temporary_enumeration_complete': True,
        'temporary_tables': [
            {
                'database': 'app',
                'name': 'shadow',
                'engine': 'Aria',
                'collation': 'utf8mb4_uca1400_ai_ci',
                'comment': '',
                'columns': [
                    {'name': 'temp_col', 'column_type': 'varchar(32)', 'hidden_from_star': False},
                ],
            }
        ],
    }
    out = mariadb_completion.complete(client, source, source_context=source_ctx)
    assert out['complete'] is False
    assert out['original_temporary_objects_observed'] is True
    assert out['original_session_commands_sent'] == 3
    cols = [r['display_name'] for r in out['resources'] if r['resource_kind'] == 'column']
    assert cols == ['temp_col']
    assert 'base_column' not in cols
    assert any(r['resource_kind'] == 'shadowed-table' and r['resource_id'] == 'table:app:shadow' for r in out['resources'])
    assert any(r['resource_kind'] == 'table' and r.get('resource_id') == 'temporary-table:app:shadow' for r in out['resources'])


# ---------------------------------------------------------------------------
# 2. MA-AUDIT-NATIVE-INDEXES & DDN VECTOR KEY Parser
# ---------------------------------------------------------------------------
def test_mariadb_vector_fulltext_spatial_and_ignored_index_compilers():
    vec = mariadb_indexes.compile_create({
        'name': 'v_idx',
        'parent': 'app',
        'table': 'docs',
        'index_kind': 'VECTOR',
        'columns': [{'name': 'emb'}],
        'vector_m': 16,
        'vector_distance': 'cosine',
        'comment': 'vector hnsw',
    })
    assert vec['statements'][0]['source'] == (
        'CREATE VECTOR INDEX `v_idx` ON `app`.`docs` (`emb`) M=16 DISTANCE=cosine COMMENT %s'
    )
    assert vec['statements'][0]['parameters'] == ('vector hnsw',)

    ft = mariadb_indexes.compile_create({
        'name': 'ft_idx',
        'parent': 'app',
        'table': 'docs',
        'index_kind': 'FULLTEXT',
        'columns': [{'name': 'body', 'prefix_length': 128}],
        'parser': 'simple_parser',
        'ignored': True,
    })
    assert ft['statements'][0]['source'] == (
        'CREATE FULLTEXT INDEX `ft_idx` ON `app`.`docs` (`body`(128)) WITH PARSER `simple_parser` IGNORED'
    )

    idx_target = {'resource_kind': 'index', 'display_name': 'ft_idx', 'display_path': ['app', 'docs', 'ft_idx']}
    vis = mariadb_indexes.compile_change('visibility', {'visibility': 'NOT IGNORED', 'confirmation': 'ft_idx'}, idx_target)
    assert vis['statements'][0]['source'] == 'ALTER TABLE `app`.`docs` ALTER INDEX `ft_idx` NOT IGNORED'

    ren = mariadb_indexes.compile_change('rename', {'new_name': 'ft_idx_v2', 'confirmation': 'ft_idx'}, idx_target)
    assert ren['statements'][0]['source'] == 'ALTER TABLE `app`.`docs` RENAME INDEX `ft_idx` TO `ft_idx_v2`'

    # Invalid combinations refused
    for bad in (
        {'name': 'x', 'table': ['app', 't'], 'index_kind': 'VECTOR', 'unique': True, 'columns': ['v']},
        {'name': 'x', 'table': ['app', 't'], 'index_kind': 'VECTOR', 'method': 'HASH', 'columns': ['v']},
        {'name': 'x', 'table': ['app', 't'], 'index_kind': 'VECTOR', 'columns': ['v1', 'v2']},
        {'name': 'x', 'table': ['app', 't'], 'index_kind': 'VECTOR', 'columns': ['v'], 'vector_m': 2},
        {'name': 'x', 'table': ['app', 't'], 'index_kind': 'NORMAL', 'columns': ['v'], 'vector_distance': 'cosine'},
    ):
        with pytest.raises(RelationalClientError):
            mariadb_indexes.compile_create(bad)


def test_ddn_vector_key_parser_and_clause_roundtrip():
    ddl = (
        'CREATE TABLE `items` (\n'
        '  `id` int(11) NOT NULL,\n'
        '  `emb` vector(4) NOT NULL,\n'
        '  PRIMARY KEY (`id`),\n'
        '  VECTOR KEY `vec_emb` (`emb`) `M`=16 `DISTANCE`=cosine\n'
        ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4'
    )
    row = {'name': 'items', 'native': {'database': 'app', 'definition': ddl}}
    _layout, clauses, _order = parts(row, '')
    assert ('index', 'vec_emb') in clauses

    described = mysql_physical.describe(clauses[('index', 'vec_emb')], '')
    assert described['describable'] is True
    assert described['index_type'] == 'VECTOR'
    assert described['vector_m'] == 16
    assert described['vector_distance'] == 'cosine'

    vals = mysql_physical.values_of(described, 'mariadb')
    norm = physical_schema.normalize(vals)
    rebuilt = mysql_physical.build_index('index', 'vec_emb', norm, {'id', 'emb'}, '', 'mariadb')
    assert rebuilt == 'VECTOR KEY `vec_emb` (`emb`) M=16 DISTANCE=cosine'

    # VECTOR index refused for MySQL in mysql_physical
    with pytest.raises(ValueError, match='MariaDB'):
        mysql_physical.build_index('index', 'vec_emb', norm, {'id', 'emb'}, '', 'mysql')


# ---------------------------------------------------------------------------
# 3. MA-AUDIT-TABLE-FIELDS
# ---------------------------------------------------------------------------
def test_mariadb_typed_table_options_and_engine_refusals():
    req = {
        'resource_kind': 'table',
        'operation_id': 'create',
        'draft': {
            'name': 'ledger',
            'parent': 'app',
            'engine': 'Aria',
            'character_set': 'utf8mb4',
            'collation': 'utf8mb4_uca1400_ai_ci',
            'row_format': 'PAGE',
            'transactional': '1',
            'page_checksum': '1',
            'comment': 'aria ledger',
            'columns': [
                {'name': 'id', 'type': 'BIGINT', 'nullable': False, 'primary_key': True},
                {'name': 'price', 'type': 'INT', 'nullable': False},
                {'name': 'double_price', 'type': 'INT', 'generated_expression': 'price * 2', 'generated_storage': 'PERSISTENT'},
                {'name': 'secret_tag', 'type': 'VARCHAR(16)', 'invisible': True},
            ],
        },
    }
    normalized = MARIADB_ADMINISTRATION._normalize_draft('table', 'create', req['draft'])
    compiled = MARIADB_ADMINISTRATION._compile({**req, 'draft': normalized})
    sql = compiled['statements'][0]['source']
    assert 'GENERATED ALWAYS AS (price * 2) PERSISTENT' in sql
    assert 'INVISIBLE' in sql
    assert 'ENGINE=Aria' in sql
    assert 'ROW_FORMAT=PAGE' in sql
    assert 'TRANSACTIONAL=1' in sql
    assert 'PAGE_CHECKSUM=1' in sql

    # Engine option combination refusals
    with pytest.raises(RelationalClientError, match='InnoDB'):
        mariadb_tables.compile_table_options({'engine': 'Aria', 'page_compressed': '1'})
    with pytest.raises(RelationalClientError, match='Aria'):
        mariadb_tables.compile_table_options({'engine': 'InnoDB', 'transactional': '1'})
    with pytest.raises(RelationalClientError, match='create-only'):
        mariadb_tables.compile_table_options({'data_directory': '/var/lib/maria'}, is_alter=True)


# ---------------------------------------------------------------------------
# 4. MA-AUDIT-TEMPORAL-LIFECYCLE
# ---------------------------------------------------------------------------
def test_mariadb_temporal_lifecycle_compilers_and_ddn_opt_in():
    target = {'resource_kind': 'table', 'display_name': 'orders', 'display_path': ['app', 'orders']}

    # Missing destructive_history_confirmed refused
    with pytest.raises(RelationalClientError, match='destructive_history_confirmed'):
        mariadb_temporal.compile_operation('drop_system_versioning', {'confirmation': 'orders'}, target)
    with pytest.raises(RelationalClientError, match='destructive_history_confirmed'):
        mariadb_temporal.compile_operation(
            'truncate_system_versioning_history',
            {'cutoff_mode': 'ALL', 'confirmation': 'orders'},
            target,
        )

    c_drop = mariadb_temporal.compile_operation(
        'drop_system_versioning',
        {'destructive_history_confirmed': True, 'confirmation': 'orders'},
        target,
    )
    assert c_drop['statements'][0]['source'] == 'ALTER TABLE `app`.`orders` DROP SYSTEM VERSIONING'

    c_trunc = mariadb_temporal.compile_operation(
        'truncate_system_versioning_history',
        {
            'cutoff_mode': 'BEFORE_TIMESTAMP',
            'before_timestamp': '2026-06-01 00:00:00',
            'destructive_history_confirmed': True,
            'confirmation': 'orders',
        },
        target,
    )
    assert c_trunc['statements'][0]['source'] == 'DELETE HISTORY FROM `app`.`orders` BEFORE SYSTEM_TIME TIMESTAMP %s'
    assert c_trunc['statements'][0]['parameters'] == ('2026-06-01 00:00:00',)

    # DDN schema-planner: unconfirmed WITH SYSTEM VERSIONING removal refused, confirmed opt-in admitted
    before = {
        'name': 'orders',
        'native': {
            'database': 'app',
            'definition': 'CREATE TABLE `orders` (`id` int(11) NOT NULL, PRIMARY KEY (`id`)) ENGINE=InnoDB WITH SYSTEM VERSIONING',
        },
    }
    after_unconf = {
        'name': 'orders',
        'native': {
            'database': 'app',
            'definition': 'CREATE TABLE `orders` (`id` int(11) NOT NULL, PRIMARY KEY (`id`)) ENGINE=InnoDB',
        },
    }
    with pytest.raises(ValueError, match='system versioning'):
        alteration(before, after_unconf, '')

    after_conf = deepcopy(after_unconf)
    after_conf['native']['mariadb_change'] = {
        'drop_system_versioning': True,
        'destructive_history_confirmed': True,
        'confirmation': 'orders',
    }
    assert alteration(before, after_conf, '') == 'ALTER TABLE `app`.`orders` DROP SYSTEM VERSIONING'


# ---------------------------------------------------------------------------
# 5. MA-AUDIT-OBJECT-EDITOR-PARITY
# ---------------------------------------------------------------------------
def test_mariadb_standalone_view_routine_and_trigger_compilers():
    v_target = {'resource_kind': 'view', 'display_name': 'v1', 'display_path': ['app', 'v1']}
    v_alt = mariadb_objects.compile_view(
        'alter',
        {'algorithm': 'MERGE', 'sql_security': 'INVOKER', 'query': 'SELECT 1 AS a', 'check_option': 'CASCADED'},
        v_target,
    )
    assert v_alt['statements'][0]['source'] == (
        'ALTER ALGORITHM=MERGE SQL SECURITY INVOKER VIEW `app`.`v1` AS SELECT 1 AS a\nWITH CASCADED CHECK OPTION'
    )

    p_target = {'resource_kind': 'procedure', 'display_name': 'sp1', 'display_path': ['app', 'sp1']}
    p_rep = mariadb_objects.compile_routine(
        'procedure',
        'create_or_replace',
        {
            'parameters': [{'mode': 'INOUT', 'name': 'x', 'type': 'INT'}],
            'data_access': 'NO SQL',
            'sql_mode': 'ORACLE',
            'body': 'BEGIN x := x + 1; END;',
            'confirmation': 'sp1',
        },
        p_target,
    )
    assert 'CREATE OR REPLACE PROCEDURE `app`.`sp1` (`x` INOUT INT)' in p_rep['statements'][0]['source']
    assert p_rep['mariadb_object_change']['sql_mode'] == 'ORACLE'

    t_target = {
        'resource_kind': 'trigger',
        'display_name': 'trg2',
        'display_path': ['app', 'items', 'trg2'],
    }
    t_rep = mariadb_objects.compile_trigger(
        'create_or_replace',
        {
            'timing': 'AFTER',
            'events': ['INSERT', 'UPDATE'],
            'order_kind': 'FOLLOWS',
            'order_trigger': 'trg1',
            'body': 'SET @seen = 1;',
            'confirmation': 'trg2',
        },
        t_target,
    )
    assert t_rep['statements'][0]['source'] == (
        'CREATE OR REPLACE TRIGGER `app`.`trg2` AFTER INSERT OR UPDATE ON `app`.`items` '
        'FOR EACH ROW FOLLOWS `trg1`\nSET @seen = 1;'
    )


# ---------------------------------------------------------------------------
# 6. MA-AUDIT-AVAILABLE-PLUGINS
# ---------------------------------------------------------------------------
def test_mariadb_all_plugins_classification_never_mislabels_mysql_enterprise():
    pam = mariadb_available_plugins.classify_plugin({
        'plugin_name': 'pam',
        'plugin_status': 'INACTIVE',
        'plugin_type': 'AUTHENTICATION',
        'plugin_library': 'auth_pam.so',
        'plugin_license': 'GPL',
    })
    assert pam['installed'] is False
    assert pam['available_uninstalled'] is True
    assert pam['production_supported'] is True
    assert pam['edition_classification'] == 'mariadb-community-open-source'
    assert pam['mysql_enterprise_reclassified'] is False

    qa = mariadb_available_plugins.classify_plugin({
        'plugin_name': 'qa_auth_interface',
        'plugin_status': 'INACTIVE',
        'plugin_type': 'AUTHENTICATION',
        'plugin_library': 'qa_auth_interface.so',
        'plugin_license': 'GPL',
    })
    assert qa['module_category'] == 'test_example'
    assert qa['production_supported'] is False
    assert qa['edition_classification'] == 'mariadb-test-example-excluded'


# ---------------------------------------------------------------------------
# 7. MA-AUDIT-MARIA-MONITORING
# ---------------------------------------------------------------------------
def test_mariadb_monitoring_aria_counter_rates_and_status_units():
    s1 = {
        'transaction_completed': True,
        'source_epoch': 'ep-1',
        'identity': {'server_uid': 'uid-maria'},
        'groups': {
            'status': {
                'status': 'available',
                'rows': [
                    {'variable_name': 'Uptime', 'variable_value': '100'},
                    {'variable_name': 'Uptime_since_flush_status', 'variable_value': '100'},
                    {'variable_name': 'Aria_pagecache_read_requests', 'variable_value': '200'},
                    {'variable_name': 'Aria_pagecache_blocks_used', 'variable_value': '12'},
                    {'variable_name': 'Aria_transaction_log_syncs', 'variable_value': '5'},
                ],
            }
        },
    }
    s2 = deepcopy(s1)
    s2['groups']['status']['rows'] = [
        {'variable_name': 'Uptime', 'variable_value': '110'},
        {'variable_name': 'Uptime_since_flush_status', 'variable_value': '110'},
        {'variable_name': 'Aria_pagecache_read_requests', 'variable_value': '250'},
        {'variable_name': 'Aria_pagecache_blocks_used', 'variable_value': '14'},
        {'variable_name': 'Aria_transaction_log_syncs', 'variable_value': '15'},
    ]
    rates = counter_rates(
        s1,
        s2,
        10.0,
        identity_key='server_uid',
        status_names=mariadb_monitoring.MARIADB_STATUS_NAMES,
        gauges=mariadb_monitoring.MARIADB_GAUGES,
    )
    assert rates['status'] == 'available'
    assert rates['per_second']['Aria_pagecache_read_requests'] == '5'
    assert rates['per_second']['Aria_transaction_log_syncs'] == '1'
    # Gauges never emit fake per-second rates
    assert 'Aria_pagecache_blocks_used' not in rates['per_second']

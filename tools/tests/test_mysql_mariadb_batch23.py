"""Unit and contract tests for MySQL 9.7.0 & MariaDB 12.2.2 Batch 2 & Batch 3."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import socket
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.ui_descriptors import UIDescriptorService
from pgadmin.cdeadmin.providers import mysql_tablespaces
from pgadmin.cdeadmin.providers.mysql_family import (
    destructive_identity,
    mariadb_flush,
    mysql_flush,
    mysql_live_plans,
    mysql_monitoring,
    mysql_ndb,
    mysql_parser,
    mysql_xcollections,
    mysql_xprotocol,
)
from pgadmin.cdeadmin.providers.mysql_family.provider import (
    MARIADB_ADMINISTRATION,
    MYSQL_ADMINISTRATION,
)

UUID_A = '11111111-2222-3333-4444-555555555555'
UID_A = 'AAAAAAAAAAAAAAAAAAAAAAAAAAA='


# ---------------------------------------------------------------------------
# 1. MY-AUDIT-IDENTITY-01 & MA-AUDIT-IDENTITY (Guarded table DROP identity)
# ---------------------------------------------------------------------------
def test_destructive_identity_compiles_for_mysql_and_mariadb_table_drop():
    my_target = {
        'resource_id': 'table:app:orders',
        'resource_kind': 'table',
        'display_name': 'orders',
        'display_path': ['app', 'orders'],
        'native': {'server_uuid': UUID_A, 'engine': 'InnoDB', 'table_type': 'BASE TABLE'},
    }
    compiled_my = MYSQL_ADMINISTRATION._compile(
        {'resource_kind': 'table', 'operation_id': 'drop', 'draft': {'confirmation': 'orders'}, 'target_resource': my_target}
    )
    assert compiled_my['destructive_identity_required'] is True
    assert compiled_my['target_resource']['display_path'] == ['app', 'orders']

    ma_target = {
        'resource_id': 'table:app:orders',
        'resource_kind': 'table',
        'display_name': 'orders',
        'display_path': ['app', 'orders'],
        'native': {'server_uid': UID_A, 'engine': 'InnoDB', 'table_type': 'BASE TABLE'},
    }
    compiled_ma = MARIADB_ADMINISTRATION._compile(
        {'resource_kind': 'table', 'operation_id': 'drop', 'draft': {'confirmation': 'orders'}, 'target_resource': ma_target}
    )
    assert compiled_ma['destructive_identity_required'] is True


def test_destructive_identity_refuses_temporary_tables_and_changed_table_id():
    temp_target = {
        'resource_kind': 'table',
        'display_name': 'tmp_orders',
        'display_path': ['app', 'tmp_orders'],
        'native': {'temporary': True},
    }
    with pytest.raises(RelationalClientError, match='temporary'):
        destructive_identity.resolve_target({'target_resource': temp_target})

    unlocked = []

    def make_conn(table_ids):
        cur = MagicMock()
        ids = list(table_ids)

        def exec_sql(sql, params=()):
            cur._last = sql
            if sql == 'UNLOCK TABLES':
                unlocked.append(True)
            if sql.startswith('DROP TABLE'):
                raise AssertionError('DROP TABLE must never run on replaced TABLE_ID')

        def fetchall():
            s = cur._last
            if '@@server_uuid' in s:
                return [('9.7.0', UUID_A, 0, 'root@%', 'root@%')]
            if 'FROM information_schema.TABLES' in s:
                return [('app', 'orders', 'BASE TABLE', 'InnoDB', '2026-11-19 10:00:00', 'utf8mb4_0900_ai_ci')]
            if 'FROM information_schema.INNODB_TABLES' in s:
                val = ids.pop(0) if len(ids) > 1 else ids[0]
                return [(str(val), '42', 'app/orders')]
            return []

        cur.execute.side_effect = exec_sql
        cur.fetchall.side_effect = fetchall
        conn = MagicMock()
        conn.cursor.return_value = cur
        return conn

    # Case A: replaced before lock -> refused before LOCK TABLES; Case B: replaced while acquiring lock -> UNLOCK TABLES in finally
    conns = [make_conn([1091]), make_conn([1092]), make_conn([1091]), make_conn([1091, 1093])]
    client = SimpleNamespace(
        _connect=lambda _req: conns.pop(0),
        _forget_connection=lambda _h: None,
        _forget_and_close=lambda _h: None,
        _discard_failed_session=lambda _h: None,
    )

    def make_plan():
        return {
            'command_preview': {'statements': [{'source': 'DROP TABLE `app`.`orders`', 'parameters': ()}]},
            'provider_payload': {
                'route': {'host': '127.0.0.1', 'database': 'app'},
                'compiled': {
                    'destructive_identity_required': True,
                    'resource_kind': 'table',
                    'operation_id': 'drop',
                    'target_resource': {
                        'resource_kind': 'table',
                        'display_name': 'orders',
                        'display_path': ['app', 'orders'],
                        'native': {'server_uuid': UUID_A},
                    },
                    'statements': [{'source': 'DROP TABLE `app`.`orders`', 'parameters': ()}],
                },
            },
        }

    rev_a = destructive_identity.bind_review(client, make_plan(), 'mysql')
    with pytest.raises(RelationalClientError) as exc_a:
        destructive_identity.apply(client, rev_a, None, 'mysql')
    assert exc_a.value.stale_target_conflict is True
    assert exc_a.value.conflict_reason == 'target_replaced_before_lock'

    rev_b = destructive_identity.bind_review(client, make_plan(), 'mysql')
    with pytest.raises(RelationalClientError) as exc_b:
        destructive_identity.apply(client, rev_b, None, 'mysql')
    assert exc_b.value.stale_target_conflict is True
    assert exc_b.value.conflict_reason == 'target_replaced_under_lock'
    assert exc_b.value.native_dispatched is False
    assert unlocked == [True]


# ---------------------------------------------------------------------------
# 2. MY-AUDIT-FLUSH & MA-AUDIT-FLUSH
# ---------------------------------------------------------------------------
def test_mysql_and_mariadb_flush_compilation_and_9_7_hosts_rejection():
    my_srv = {
        'resource_id': 'server:MySQL',
        'resource_kind': 'server',
        'display_name': 'MySQL',
        'display_path': ['MySQL'],
        'native': {'server_uuid': UUID_A},
    }
    with pytest.raises(RelationalClientError) as exc_hosts:
        mysql_flush.compile_operation('flush', {'targets': ['HOSTS'], 'confirmation': 'MySQL'}, my_srv)
    assert getattr(exc_hosts.value, 'error_code', None) == 'flush_hosts_removed_in_9_7'

    compiled = mysql_flush.compile_operation(
        'flush',
        {'targets': ['STATUS', 'RELAY LOGS'], 'binlog_mode': 'NO_WRITE_TO_BINLOG', 'relay_channel': 'ch_1', 'confirmation': 'MySQL'},
        my_srv,
    )
    assert compiled['statements'][0]['source'] == "FLUSH NO_WRITE_TO_BINLOG STATUS, RELAY LOGS FOR CHANNEL 'ch_1'"

    my_tbl = {'resource_kind': 'table', 'display_name': 'items', 'display_path': ['shop', 'items'], 'native': {'server_uuid': UUID_A}}
    locked = mysql_flush.compile_operation(
        'flush', {'lock_mode': 'WITH_READ_LOCK', 'confirmation': 'items'}, my_tbl
    )
    assert locked['statements'][0]['source'] == 'FLUSH TABLES `shop`.`items` WITH READ LOCK'
    assert locked['mysql_flush']['retained_session_required'] is True

    ma_srv = {
        'resource_id': 'server:MariaDB',
        'resource_kind': 'server',
        'display_name': 'MariaDB',
        'display_path': ['MariaDB'],
        'native': {'server_uid': UID_A},
    }
    ma_compiled = mariadb_flush.compile_operation(
        'flush',
        {'targets': ['HOSTS', 'USER_STATISTICS', 'SSL'], 'binlog_mode': 'LOCAL', 'confirmation': 'MariaDB'},
        ma_srv,
    )
    assert ma_compiled['statements'][0]['source'] == 'FLUSH LOCAL HOSTS, USER_STATISTICS, SSL'


# ---------------------------------------------------------------------------
# 3. MY-AUDIT-EXPLAIN_FOR_CONNECTION
# ---------------------------------------------------------------------------
def test_mysql_explain_for_connection_compiles_server_and_session_scopes():
    srv = {
        'resource_id': 'server:MySQL',
        'resource_kind': 'server',
        'display_name': 'MySQL',
        'display_path': ['MySQL'],
        'native': {'server_uuid': UUID_A},
    }
    for fmt in ('TRADITIONAL', 'JSON', 'TREE'):
        c = mysql_live_plans.compile_operation(
            'explain_for_connection',
            {'connection_id': '42', 'output_format': fmt, 'private_data_confirmed': True, 'confirmation': 'MySQL'},
            srv,
        )
        assert c['statements'][0]['source'] == f'EXPLAIN FORMAT={fmt} FOR CONNECTION 42'

    sess = {
        'resource_kind': 'session',
        'display_name': '77',
        'display_path': ['Sessions', '77'],
        'native': {'processlist_id': '77', 'server_uuid': UUID_A},
    }
    cs = mysql_live_plans.compile_operation(
        'explain_for_connection',
        {'output_format': 'TREE', 'private_data_confirmed': True, 'confirmation': '77'},
        sess,
    )
    assert cs['statements'][0]['source'] == 'EXPLAIN FORMAT=TREE FOR CONNECTION 77'

    for bad_id in ('0', '-5', '12; DROP TABLE x', ''):
        with pytest.raises(RelationalClientError):
            mysql_live_plans.compile_operation(
                'explain_for_connection',
                {'connection_id': bad_id, 'output_format': 'JSON', 'private_data_confirmed': True, 'confirmation': 'MySQL'},
                srv,
            )


# ---------------------------------------------------------------------------
# 4. MY-AUDIT-COMPONENT-METRICS
# ---------------------------------------------------------------------------
def test_component_metrics_report_not_installed_never_fake_zeros_and_compute_rates():
    mon = mysql_monitoring.MySQLMonitor(SimpleNamespace(), {'host': 'db', 'database': 'demo'})
    mon._connection = SimpleNamespace(in_transaction=False)
    mon._client = Mock()
    mon._epoch = 'ep-1'
    id_row = {'database_name': 'demo', 'version': '9.7.0', 'server_uuid': UUID_A, 'collector_id': 9, 'account': 'mon@%'}

    installed = [False]

    def read_fn(sql, params=None):
        if sql.startswith('SELECT DATABASE()'):
            return [dict(id_row)]
        if "TABLE_SCHEMA = 'performance_schema'" in sql and 'replication_applier_metrics' in sql:
            return (
                [{'table_name': 'replication_applier_metrics'}, {'table_name': 'replication_applier_progress_by_worker'}]
                if installed[0]
                else []
            )
        if 'FROM performance_schema.replication_applier_metrics' in sql:
            return [{'channel_name': '', 'transactions_committed_count': '12', 'transactions_execution_time_sum': '5000'}]
        if 'FROM performance_schema.replication_applier_progress_by_worker' in sql:
            return [{'channel_name': '', 'worker_id': '1', 'transactions_committed_count': '12'}]
        if params and 'Gr_flow_control_throttle_count' in params:
            return (
                [
                    {'variable_name': 'Gr_flow_control_throttle_active_count', 'variable_value': '0'},
                    {'variable_name': 'Gr_flow_control_throttle_count', 'variable_value': '10'},
                    {'variable_name': 'Gr_flow_control_throttle_last_throttle_timestamp', 'variable_value': ''},
                    {'variable_name': 'Gr_flow_control_throttle_time_sum', 'variable_value': '400'},
                ]
                if installed[0]
                else []
            )
        if 'FROM performance_schema.global_status' in sql:
            return [
                {'variable_name': 'Uptime', 'variable_value': '100'},
                {'variable_name': 'Uptime_since_flush_status', 'variable_value': '100'},
                {'variable_name': 'Questions', 'variable_value': '50'},
            ]
        return []

    mon._read = Mock(side_effect=read_fn)
    absent = mon.sample()
    for gname in (
        'component_replication_applier_metrics',
        'component_replication_applier_worker_progress',
        'component_group_replication_flow_control',
    ):
        assert absent['groups'][gname]['status'] == 'not_installed'
        assert absent['groups'][gname]['reason'] == 'component-not-installed'
        assert absent['groups'][gname]['rows'] == []

    installed[0] = True
    present = mon.sample()
    assert present['groups']['component_replication_applier_metrics']['status'] == 'available'
    assert present['groups']['component_replication_applier_metrics']['rows'][0]['transactions_committed_count'] == '12'
    assert present['groups']['component_group_replication_flow_control']['status'] == 'available'
    gr_map = {
        r['variable_name']: r['variable_value']
        for r in present['groups']['component_group_replication_flow_control']['rows']
    }
    assert gr_map['Gr_flow_control_throttle_count'] == '10'

    s2 = deepcopy(present)
    s2['groups']['status']['rows'][0]['variable_value'] = '102'
    s2['groups']['status']['rows'][1]['variable_value'] = '102'
    for row in s2['groups']['component_group_replication_flow_control']['rows']:
        if row['variable_name'] == 'Gr_flow_control_throttle_count':
            row['variable_value'] = '14'
        elif row['variable_name'] == 'Gr_flow_control_throttle_time_sum':
            row['variable_value'] = '500'
    rates = mysql_monitoring.counter_rates(present, s2, 2.0)
    assert rates['per_second']['Gr_flow_control_throttle_count'] == '2'
    assert rates['per_second']['Gr_flow_control_throttle_time_sum'] == '50'
    mon.close()


# ---------------------------------------------------------------------------
# 5. MY-AUDIT-LANGUAGE-SEMANTICS
# ---------------------------------------------------------------------------
def test_mysql_language_semantics_exposes_explicit_nonexecuting_fields(monkeypatch):
    monkeypatch.setattr(
        mysql_parser,
        'native',
        lambda _lib, stmts: {
            'available': True,
            'parser_version': '9.7.0',
            'statements': [
                {'accepted': True, 'sql_syntax_valid': True, 'native_status': 0, 'diagnostics': []}
                for _ in stmts
            ],
            'sql_executed': False,
            'database_connection_opened': False,
        },
    )
    obs = {'version': '9.7.0', 'thread_id': 52, 'connection_id': 12, 'variables': {'sql_mode': ''}}
    res = mysql_parser.validate(Path('/owned'), 'SELECT * FROM nonexistent_future_table WHERE id = 1', obs, False)
    assert res['grammar_valid'] is True
    assert res['context_mode'] == 'live_session'
    assert res['catalog_binding_status'] == 'unknown'
    assert res['privilege_evaluation'] == 'not_evaluated'
    assert res['execution_verified'] is False

    empty_res = mysql_parser.validate(Path('/owned'), '   ', obs, False)
    assert empty_res['grammar_valid'] is False
    assert empty_res['execution_verified'] is False

    unconfirmed = mysql_parser.validate(Path('/owned'), 'SET sql_mode=@runtime_mode; SELECT 1', obs, True)
    assert unconfirmed['grammar_valid'] is None
    assert unconfirmed['context_mode'] == 'script_unconfirmed'
    assert unconfirmed['catalog_binding_status'] == 'unknown'
    assert unconfirmed['privilege_evaluation'] == 'not_evaluated'
    assert unconfirmed['execution_verified'] is False


# ---------------------------------------------------------------------------
# 6. MY-AUDIT-XCOLLECTIONS
# ---------------------------------------------------------------------------
def test_xprotocol_frame_encoding_and_collection_discovery_distinguishes_json_tables():
    cols = [
        {'table_schema': 'app', 'table_name': 'plain_json', 'column_name': 'id', 'data_type': 'int',
         'column_type': 'int', 'extra': 'auto_increment', 'column_key': 'PRI', 'generation_expression': ''},
        {'table_schema': 'app', 'table_name': 'plain_json', 'column_name': 'doc', 'data_type': 'json',
         'column_type': 'json', 'extra': '', 'column_key': '', 'generation_expression': ''},
        {'table_schema': 'app', 'table_name': 'orders_coll', 'column_name': 'doc', 'data_type': 'json',
         'column_type': 'json', 'extra': '', 'column_key': '', 'generation_expression': ''},
        {'table_schema': 'app', 'table_name': 'orders_coll', 'column_name': '_id', 'data_type': 'varbinary',
         'column_type': 'varbinary(32)', 'extra': 'STORED GENERATED', 'column_key': 'PRI',
         'generation_expression': "json_unquote(json_extract(`doc`,_utf8mb4'$._id'))"},
        {'table_schema': 'app', 'table_name': 'orders_coll', 'column_name': '_json_schema', 'data_type': 'json',
         'column_type': 'json', 'extra': 'VIRTUAL GENERATED', 'column_key': '',
         'generation_expression': '\'{"type":"object"}\''},
    ]
    constraints = [
        {'table_schema': 'app', 'table_name': 'orders_coll', 'constraint_name': '$val_strict_abc',
         'constraint_type': 'CHECK', 'enforced': 'YES'},
    ]
    found = mysql_xcollections.discover_collections_from_rows(cols, constraints)
    assert len(found) == 1
    assert found[0]['name'] == 'orders_coll'
    assert found[0]['validation_level'] == 'STRICT'

    parsed_path = mysql_xprotocol.parse_document_path('$.customer.tags[0].name')
    assert len(parsed_path) == 4


# ---------------------------------------------------------------------------
# 7. MY-AUDIT-NDB & UI Descriptor Completeness
# ---------------------------------------------------------------------------
def test_ndb_mgm_protocol_client_and_non_ndb_capability_gate():
    cursor = MagicMock()
    cursor.fetchall.return_value = [('ndbcluster', 'NO')]
    with pytest.raises(RelationalClientError) as exc_info:
        mysql_ndb.require_ndbcluster_engine(cursor)
    assert exc_info.value.error_code == 'ndbcluster_unavailable'

    ts = mysql_tablespaces.compile_operation(
        'create',
        {
            'name': 'ts_ndb_1',
            'space_type': 'NDB',
            'datafile': 'ts_ndb_1.dat',
            'logfile_group': 'lg_1',
            'initial_size': 33554432,
            'extent_size': 1048576,
        },
        None,
    )
    assert ts['ndb_required'] is True
    assert ts['source'] == (
        'CREATE TABLESPACE `ts_ndb_1` ADD DATAFILE %s USE LOGFILE GROUP `lg_1` '
        'EXTENT_SIZE=1048576 INITIAL_SIZE=33554432 ENGINE=NDBCLUSTER'
    )
    assert ts['parameters'] == ('ts_ndb_1.dat',)

    srv_sock, cli_sock = socket.socketpair()
    received_cmds = []

    def mgmd_loop():
        buf = b''
        replies = [
            'version\nid: 590080\nmajor: 9\nminor: 7\nbuild: 0\n\n',
            'set clientversion reply\nresult: Ok\n\n',
            'node status\nnodes: 2\nnode.1.type: MGM\nnode.1.status: CONNECTED\nnode.2.type: NDB\nnode.2.status: STARTED\n\n',
            'start backup reply\nresult: Ok\nid: 7\n\n',
        ]
        idx = 0
        while idx < len(replies):
            chunk = srv_sock.recv(4096)
            if not chunk:
                break
            buf += chunk
            while b'\n\n' in buf and idx < len(replies):
                pkt, buf = buf.split(b'\n\n', 1)
                received_cmds.append(pkt.decode('utf-8'))
                srv_sock.sendall(replies[idx].encode('utf-8'))
                idx += 1
        srv_sock.close()

    t = threading.Thread(target=mgmd_loop, daemon=True)
    t.start()
    mgm = mysql_ndb.NdbMgmClient(cli_sock)
    ver = mgm.command('get version')
    mgm.command('set clientversion', {'major': int(ver['properties']['major']), 'minor': 7, 'build': 0})
    st = mgm.get_status()
    assert st['node_count'] == 2 and st['nodes'][1]['status'] == 'STARTED'
    bk = mgm.start_backup(wait_mode='WAIT_COMPLETED')
    assert bk['backup_id'] == 7
    mgm.close()
    t.join(timeout=2)
    assert received_cmds[0] == 'get version'
    assert 'start backup' in received_cmds[3]


def test_ui_descriptors_expose_all_batch23_operations_without_json_controls():
    svc = UIDescriptorService()
    my_bundle = svc.engine('mysql')
    my_ops = {(o['resource_kind'], o['operation_id']) for o in my_bundle['operations']}
    expected_my = {
        ('server', 'flush'),
        ('table', 'flush'),
        ('server', 'explain_for_connection'),
        ('session', 'explain_for_connection'),
        ('server', 'inspect_ndb_cluster'),
        ('server', 'start_ndb_backup'),
        ('server', 'abort_ndb_backup'),
        ('logfile-group', 'create'),
        ('logfile-group', 'alter'),
        ('logfile-group', 'drop'),
        ('ndb-node', 'restart_ndb_node'),
        ('ndb-node', 'stop_ndb_node'),
        *(('x-collection', op) for op in mysql_xcollections.OPERATIONS),
    }
    assert expected_my <= my_ops

    ma_bundle = svc.engine('mariadb')
    ma_ops = {(o['resource_kind'], o['operation_id']) for o in ma_bundle['operations']}
    assert {('server', 'flush'), ('table', 'flush')} <= ma_ops

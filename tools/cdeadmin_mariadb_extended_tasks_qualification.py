"""Qualify extended MariaDB 12.2.2 dialect tasks (flush, plugins, temporary, index, temporal, object parity) on an owned container."""
import argparse
import json
from pathlib import Path
import secrets
from types import SimpleNamespace

from tools.cdeadmin_mariadb_driver_gate import run
from tools.mysql_driver_gate_support import provider_access
from pgadmin.cdeadmin.providers.mysql_family.provider import (
    MARIADB_ADMINISTRATION,
    MARIADB_PROFILE,
    _create_client,
    _resources,
)


EXPECTED_TASKS = frozenset({
    'visual_admin.server.flush',
    'visual_admin.table.flush',
    'visual_admin.server.inspect_available_plugins',
    'visual_admin.table.drop_temporary',
    'visual_admin.index.alter',
    'visual_admin.index.rename',
    'visual_admin.index.visibility',
    'visual_admin.table.add_system_versioning',
    'visual_admin.table.rotate_system_time_partitions',
    'visual_admin.table.truncate_system_versioning_history',
    'visual_admin.table.drop_system_versioning',
    'visual_admin.table.add_application_period',
    'visual_admin.table.drop_application_period',
    'visual_admin.view.alter',
    'visual_admin.view.create_or_replace',
    'visual_admin.procedure.alter',
    'visual_admin.procedure.create_or_replace',
    'visual_admin.function.alter',
    'visual_admin.function.create_or_replace',
    'visual_admin.trigger.alter',
    'visual_admin.trigger.create_or_replace',
})


def qualify(route, evidence, *, password=None):
    import mariadb

    evidence.mkdir(parents=True, exist_ok=False)
    proof = {
        'complete': False,
        'engine': 'mariadb',
        'version': '12.2.2',
        'checks': [],
        'failures': [],
        'task_sources': {},
        'task_evidence': {},
    }
    schema = 'owned_extended_' + secrets.token_hex(6)
    credentials = {'password': password} if password is not None else {}
    owner = mariadb.connect(**route, autocommit=True, **credentials)
    request_route, permissions = provider_access(route, password)
    db_route = {**request_route, 'database': schema}
    client = _create_client(
        MARIADB_PROFILE,
        permissions,
        SimpleNamespace(pool_namespace='owned-extended-tasks'),
    )
    retained = None
    try:
        with owner.cursor() as cur:
            cur.execute('SELECT @@server_uid, VERSION()')
            server_uid, server_version = cur.fetchone()
            assert str(server_version).split('-')[0] == '12.2.2', server_version
            cur.execute(f'CREATE DATABASE `{schema}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
        owner.database = schema
        with owner.cursor() as cur:
            cur.execute(
                'CREATE TABLE items ('
                'id INT PRIMARY KEY, '
                'label VARCHAR(64) NOT NULL, '
                'embedding VECTOR(4) NOT NULL'
                ') ENGINE=InnoDB'
            )
            cur.execute("INSERT INTO items VALUES (1, 'alpha', VEC_FromText('[1,0,0,0]'))")
            cur.execute('CREATE INDEX ix_items_label ON items (label(16))')
            cur.execute('CREATE VIEW v_items AS SELECT id, label FROM items')
            cur.execute('CREATE PROCEDURE p_items(IN p_id INT) BEGIN SELECT label FROM items WHERE id = p_id; END')
            cur.execute(
                'CREATE FUNCTION f_items(p_id INT) RETURNS INT DETERMINISTIC READS SQL DATA '
                'RETURN (SELECT COUNT(*) FROM items WHERE id = p_id)'
            )
            cur.execute("CREATE TRIGGER trg_anchor BEFORE INSERT ON items FOR EACH ROW SET NEW.label = TRIM(NEW.label)")
            cur.execute(
                "CREATE TRIGGER trg_items BEFORE INSERT ON items FOR EACH ROW FOLLOWS `trg_anchor` "
                "SET NEW.label = CONCAT(NEW.label, '')"
            )

        def find_resource(kind, name=None):
            rows = [r for r in _resources(owner, {'route': {'database': schema}}, MARIADB_PROFILE) if r['resource_kind'] == kind]
            if name is not None:
                rows = [r for r in rows if r['display_name'] == name]
            assert rows, (kind, name)
            return rows[0]

        def run_task(kind, operation_id, draft, target=None, session_id=None, connection=None):
            req = {
                'resource_kind': kind,
                'operation_id': operation_id,
                'target_resource': target,
                'draft': draft,
                '_provider_route': db_route,
                **({'session_id': session_id} if session_id else {}),
            }
            val = MARIADB_ADMINISTRATION.validate(req)
            assert val['errors'] == [], (kind, operation_id, val)
            planned = client.plan_admin_operation(req)
            apply_req = dict(planned)
            if connection is not None:
                apply_req['_provider_session_handle'] = connection
                if session_id:
                    apply_req['session_id'] = session_id
            result = client.apply_admin_operation(apply_req)
            assert result.get('accepted') is True, (kind, operation_id, result)
            task_id = f'visual_admin.{kind}.{operation_id}'
            stmts = planned['command_preview']['statements']
            proof['task_sources'][task_id] = [s['source'] for s in stmts]
            proof['task_evidence'][task_id] = {
                'statements': stmts,
                'live_execution': 'passed',
            }
            return planned, result

        server_target = {
            'resource_id': 'server:MariaDB',
            'resource_kind': 'server',
            'display_name': 'MariaDB',
            'display_path': ['MariaDB'],
            'native': {'server_uid': server_uid},
        }

        # 1. Server & table FLUSH + ALL_PLUGINS inspection
        run_task(
            'server',
            'flush',
            {'targets': ['STATUS', 'HOSTS'], 'binlog_mode': 'NO_WRITE_TO_BINLOG', 'lock_wait_seconds': 15, 'confirmation': 'MariaDB'},
            target=server_target,
        )
        run_task(
            'table',
            'flush',
            {'binlog_mode': 'NO_WRITE_TO_BINLOG', 'lock_mode': 'NONE', 'lock_wait_seconds': 15, 'confirmation': 'items'},
            target=find_resource('table', 'items'),
        )
        _pl, ap_res = run_task(
            'server',
            'inspect_available_plugins',
            {'status_filter': 'ALL', 'include_test_modules': False},
            target=server_target,
        )
        assert ap_res['available_plugins']['active_count'] > 0
        proof['checks'].append('server_and_table_flush_and_all_plugins_verified')

        # 2. Retained-session temporary table creation & drop_temporary preserving base table and active transaction
        retained = client.open_session({'route': dict(db_route, autocommit=False)})
        with retained.cursor() as rcur:
            rcur.execute("INSERT INTO items VALUES (2, 'pending_tx', VEC_FromText('[0,1,0,0]'))")
            rcur.execute(f'CREATE TEMPORARY TABLE `{schema}`.`items` (temp_only INT PRIMARY KEY)')
        temp_target = {
            'resource_id': f'temporary-table:{schema}:items',
            'resource_kind': 'table',
            'display_name': 'items',
            'display_path': [schema, 'items'],
            'native': {'temporary': True, 'table_type': 'TEMPORARY', 'server_uid': server_uid},
        }
        run_task(
            'table',
            'drop_temporary',
            {'confirmation': 'items'},
            target=temp_target,
            session_id='retained-ext-1',
            connection=retained,
        )
        with owner.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM items')
            # Base table still exists and uncommitted row 2 was NOT implicitly committed!
            assert cur.fetchone()[0] == 1
        retained.rollback()
        client.close_session(retained)
        retained = None
        proof['checks'].append('retained_temporary_drop_preserves_base_table_and_uncommitted_tx')

        # 3. Native MariaDB index visibility, rename & alter
        run_task(
            'index',
            'visibility',
            {'visibility': 'IGNORED', 'confirmation': 'ix_items_label'},
            target=find_resource('index', 'ix_items_label'),
        )
        with owner.cursor() as cur:
            cur.execute(
                "SELECT IGNORED FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA=? AND TABLE_NAME='items' AND INDEX_NAME='ix_items_label'",
                (schema,),
            )
            assert cur.fetchone() == ('YES',)
        run_task(
            'index',
            'rename',
            {'new_name': 'ix_items_label_v2', 'confirmation': 'ix_items_label'},
            target=find_resource('index', 'ix_items_label'),
        )
        run_task(
            'index',
            'alter',
            {'ignored': False, 'new_name': 'ix_items_label_v3'},
            target=find_resource('index', 'ix_items_label_v2'),
        )
        with owner.cursor() as cur:
            cur.execute(
                "SELECT IGNORED FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA=? AND TABLE_NAME='items' AND INDEX_NAME='ix_items_label_v3'",
                (schema,),
            )
            assert cur.fetchone() == ('NO',)
        proof['checks'].append('native_index_visibility_rename_and_alter_verified')

        # 4. System versioning & application-time period lifecycle
        run_task(
            'table',
            'add_system_versioning',
            {'start_column': 'row_s', 'end_column': 'row_e', 'invisible_period_columns': True, 'confirmation': 'items'},
            target=find_resource('table', 'items'),
        )
        with owner.cursor() as cur:
            cur.execute("UPDATE items SET label = 'beta' WHERE id = 1")
            cur.execute('SELECT COUNT(*) FROM items FOR SYSTEM_TIME ALL')
            assert cur.fetchone()[0] == 2
        run_task(
            'table',
            'rotate_system_time_partitions',
            {'rotation_action': 'PARTITION_BY_LIMIT', 'row_limit': 100, 'history_partitions': 2, 'confirmation': 'items'},
            target=find_resource('table', 'items'),
        )
        run_task(
            'table',
            'truncate_system_versioning_history',
            {'cutoff_mode': 'ALL', 'destructive_history_confirmed': True, 'confirmation': 'items'},
            target=find_resource('table', 'items'),
        )
        with owner.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM items FOR SYSTEM_TIME ALL')
            assert cur.fetchone()[0] == 1
            cur.execute('ALTER TABLE items REMOVE PARTITIONING')
        run_task(
            'table',
            'drop_system_versioning',
            {
                'drop_period_columns': True,
                'start_column': 'row_s',
                'end_column': 'row_e',
                'destructive_history_confirmed': True,
                'confirmation': 'items',
            },
            target=find_resource('table', 'items'),
        )
        with owner.cursor() as cur:
            cur.execute('CREATE TABLE period_items (id INT PRIMARY KEY, label VARCHAR(32) NOT NULL) ENGINE=InnoDB')
        run_task(
            'table',
            'add_application_period',
            {
                'period_name': 'valid_window',
                'start_column': 'valid_from',
                'end_column': 'valid_to',
                'create_boundary_columns': True,
                'boundary_type': 'DATE',
                'confirmation': 'period_items',
            },
            target=find_resource('table', 'period_items'),
        )
        with owner.cursor() as cur:
            cur.execute("INSERT INTO period_items VALUES (1, 'windowed', '2026-01-01', '2026-12-31')")
            cur.execute(
                "SELECT PERIOD FROM information_schema.PERIODS WHERE TABLE_SCHEMA=? AND TABLE_NAME='period_items'",
                (schema,),
            )
            assert cur.fetchall() == [('valid_window',)]
        run_task(
            'table',
            'drop_application_period',
            {'period_name': 'valid_window', 'destructive_history_confirmed': True, 'confirmation': 'period_items'},
            target=find_resource('table', 'period_items'),
        )
        proof['checks'].append('native_system_versioning_and_application_period_lifecycle_verified')

        # 5. View, procedure, function, and trigger alter & create_or_replace
        run_task(
            'view',
            'alter',
            {'algorithm': 'MERGE', 'sql_security': 'INVOKER', 'definition': 'SELECT id, label FROM items WHERE id > 0'},
            target=find_resource('view', 'v_items'),
        )
        run_task(
            'view',
            'create_or_replace',
            {
                'algorithm': 'UNDEFINED',
                'sql_security': 'DEFINER',
                'definition': 'SELECT id, UPPER(label) AS label FROM items',
                'confirmation': 'v_items',
            },
            target=find_resource('view', 'v_items'),
        )
        run_task(
            'procedure',
            'alter',
            {'sql_security': 'INVOKER', 'comment': 'updated proc'},
            target=find_resource('procedure', 'p_items'),
        )
        run_task(
            'procedure',
            'create_or_replace',
            {
                'parameters': [{'name': 'p_id', 'type': 'INT', 'mode': 'IN'}],
                'data_access': 'READS SQL DATA',
                'body': 'BEGIN SELECT id, label FROM items WHERE id = p_id; END',
                'confirmation': 'p_items',
            },
            target=find_resource('procedure', 'p_items'),
        )
        run_task(
            'function',
            'alter',
            {'sql_security': 'INVOKER', 'comment': 'updated fn'},
            target=find_resource('function', 'f_items'),
        )
        run_task(
            'function',
            'create_or_replace',
            {
                'parameters': [{'name': 'p_id', 'type': 'INT'}],
                'returns': 'INT',
                'deterministic': 'DETERMINISTIC',
                'data_access': 'READS SQL DATA',
                'body': 'RETURN (SELECT COUNT(*) + 10 FROM items WHERE id = p_id)',
                'confirmation': 'f_items',
            },
            target=find_resource('function', 'f_items'),
        )
        with owner.cursor() as cur:
            cur.execute('SELECT f_items(1)')
            assert cur.fetchone() == (11,)
        run_task(
            'trigger',
            'alter',
            {'body': "SET NEW.label = COALESCE(NEW.label, 'altered')"},
            target=find_resource('trigger', 'trg_items'),
        )
        run_task(
            'trigger',
            'create_or_replace',
            {'body': "SET NEW.label = COALESCE(NEW.label, 'replaced')", 'confirmation': 'trg_items'},
            target=find_resource('trigger', 'trg_items'),
        )
        with owner.cursor() as cur:
            cur.execute(
                "SELECT TRIGGER_NAME, ACTION_ORDER FROM information_schema.TRIGGERS "
                "WHERE TRIGGER_SCHEMA=? AND EVENT_OBJECT_TABLE='items' ORDER BY ACTION_ORDER",
                (schema,),
            )
            assert cur.fetchall() == [('trg_anchor', 1), ('trg_items', 2)]
        proof['checks'].append('native_view_routine_and_trigger_alter_and_replace_preserve_order_and_semantics')

        assert set(proof['task_sources']) == EXPECTED_TASKS, (
            set(proof['task_sources']) ^ EXPECTED_TASKS
        )
        proof['complete'] = True
    except Exception as error:
        proof['failures'].append({'type': type(error).__name__, 'message': str(error)})
        raise
    finally:
        if retained is not None:
            try:
                client.close_session(retained)
            except Exception:
                pass
        client.close()
        with owner.cursor() as cur:
            cur.execute(f'DROP DATABASE IF EXISTS `{schema}`')
        owner.close()
        (evidence / 'summary.json').write_text(json.dumps(proof, indent=2, sort_keys=True) + '\n')
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='mariadb:12.2.2')
    parser.add_argument('--evidence', type=Path, required=True)
    options = parser.parse_args()
    raise SystemExit(0 if run(options.image, options.evidence, qualify)['complete'] else 1)

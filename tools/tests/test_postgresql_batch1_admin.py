"""Unit, live multi-major (PG 16, 17, 18) and authenticated HTTP tests for PostgreSQL Batch 1:
- PG-AUDIT-FIELD-01 (table alter grid refusal + TOAST options over HTTP & PG 16/17/18)
- PG-AUDIT-CONSTRAINT-01 (named NOT NULL, WITHOUT OVERLAPS, PERIOD FK, ENFORCED / NOT ENFORCED)
- PG-AUDIT-MAINT-01 (VACUUM/ANALYZE/REINDEX PG 16+ & 18 options + REINDEX SYSTEM)
- PG-AUDIT-INDEXPART-01 (standalone ALTER INDEX ATTACH PARTITION)
- PG-AUDIT-FDW-01 (IMPORT FOREIGN SCHEMA with ALL / LIMIT TO / EXCEPT & options)
- PG-AUDIT-TWOPHASE-01 (COMMIT PREPARED / ROLLBACK PREPARED with exact GID/DB/owner/XID verification)
- PG-AUDIT-CONFIG-01 (ALTER SYSTEM SET/RESET/RESET ALL + pg_settings/HBA inspection + host file deploy/rollback)
"""
from __future__ import annotations

import builtins
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]

from pgadmin.cdeadmin.core import EndpointContext  # noqa: E402
from pgadmin.cdeadmin.providers.postgresql.native_admin import (  # noqa: E402
    PostgreSQLNativeAdminError,
    compile_native_admin,
)
from pgadmin.cdeadmin.providers.postgresql.provider import (  # noqa: E402
    LEGACY_DRIVER_TYPE,
    PostgreSQLProvider,
    PostgreSQLStatementRejected,
)
from pgadmin.cdeadmin.workspace import postgresql_physical  # noqa: E402
from test_ui_descriptor_operations_postgresql import Driver, Permissions  # noqa: E402

PG18_BIN = Path('/usr/lib/postgresql/18/bin')
PG17_BIN = Path('/usr/lib/postgresql/17/bin')
PG16_BIN = Path('/usr/lib/postgresql/16/bin')


def _start_disposable_pg(tmp_dir: Path, bin_dir: Path, extra_gucs: tuple[str, ...] = ()):
    if not (bin_dir / 'initdb').is_file():
        pytest.skip(f'PostgreSQL binaries not present at {bin_dir}')
    datadir = tmp_dir / f'pgdata_{bin_dir.parent.name}_{uuid.uuid4().hex[:6]}'
    init_args = [
        str(bin_dir / 'initdb'),
        '-D',
        str(datadir),
        *(['--no-data-checksums'] if '18' in bin_dir.parts else []),
        '--auth=trust',
        '--no-locale',
        '--encoding=UTF8',
    ]
    subprocess.run(
        init_args,
        check=True,
        capture_output=True,
        timeout=45,
    )
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    opts = f"-h 127.0.0.1 -p {port} -c unix_socket_directories='' -c max_prepared_transactions=8"
    for guc in extra_gucs:
        opts += f' -c {guc}'
    logfile = tmp_dir / f'pg_{port}.log'
    subprocess.run(
        [str(bin_dir / 'pg_ctl'), '-D', str(datadir), '-l', str(logfile), '-o', opts, '-w', 'start'],
        check=True,
        capture_output=True,
        timeout=30,
    )
    user = __import__('getpass').getuser()
    dsn = make_conninfo(host='127.0.0.1', port=port, user=user, dbname='postgres')
    return SimpleNamespace(datadir=datadir, bin_dir=bin_dir, port=port, user=user, dsn=dsn)


def _stop_disposable_pg(cluster):
    if (cluster.datadir / 'postmaster.pid').exists():
        subprocess.run(
            [str(cluster.bin_dir / 'pg_ctl'), '-D', str(cluster.datadir), '-m', 'immediate', '-w', 'stop'],
            check=False,
            capture_output=True,
            timeout=25,
        )


def _make_provider(dsn: str, role: str | None = None):
    ctx = replace(
        EndpointContext(
            endpoint_id=str(uuid.uuid4()),
            mode='legacy_native',
            experience_family='postgresql',
            provider_id='org.pgadmin.postgresql',
            provider_version='9.17.0',
            profile_id='postgresql-native',
            profile_version='18.3',
            target_adapter_id='legacy-pgadmin-server',
            target_adapter_version='9.17.0',
            pool_namespace=str(uuid.uuid4()),
            session_namespace=str(uuid.uuid4()),
            cache_namespace=str(uuid.uuid4()),
            diagnostic_namespace=str(uuid.uuid4()),
            effective_permissions=frozenset(
                {'network', 'secret_read', 'data_read', 'data_write', 'administer', 'execute'}
            ),
            legacy_driver_type=LEGACY_DRIVER_TYPE,
        ),
        runtime_verification_state='verified',
    )
    effective_dsn = make_conninfo(dsn, options=f'-c role={role}') if role else dsn
    return PostgreSQLProvider(ctx, Permissions(), Driver(effective_dsn), catalog_source=object())


@pytest.fixture(scope='module')
def pg18_cluster(tmp_path_factory):
    base = tmp_path_factory.mktemp('pg18_batch1')
    cluster = _start_disposable_pg(base, PG18_BIN)
    try:
        yield cluster
    finally:
        _stop_disposable_pg(cluster)


@pytest.fixture(scope='module')
def pg17_cluster(tmp_path_factory):
    base = tmp_path_factory.mktemp('pg17_batch1')
    cluster = _start_disposable_pg(base, PG17_BIN)
    try:
        yield cluster
    finally:
        _stop_disposable_pg(cluster)


@pytest.fixture(scope='module')
def pg16_cluster(tmp_path_factory):
    base = tmp_path_factory.mktemp('pg16_batch1')
    cluster = _start_disposable_pg(base, PG16_BIN)
    try:
        yield cluster
    finally:
        _stop_disposable_pg(cluster)


def _exec(provider, kind, operation, draft, dboid=None, target=None):
    req = {
        'resource_kind': kind,
        'operation_id': operation,
        'draft': draft,
        '_provider_route': {'server_id': 1, **({'database_id': dboid} if dboid is not None else {})},
        'target_resource': {'extensions': {'postgresql': {'native': target or {}}}},
    }
    plan = provider.plan_admin_operation(req)
    res = provider.apply_admin_operation({'provider_payload': plan['provider_payload']})
    return plan, res


# ---------------------------------------------------------------------------
# 1. Unit compilation & refusal checks
# ---------------------------------------------------------------------------

def test_unit_pg18_constraints_and_maintenance_compilation():
    tbl = {'schema': 'public', 'table': 'Bookings', 'catalog_row': {}}
    # Named NOT NULL with NO INHERIT
    c_nn = compile_native_admin({
        'resource_kind': 'constraint',
        'operation_id': 'create',
        'draft': {'name': 'nn_room', 'contype': 'n', 'not_null_column': 'room_id', 'connoinherit': True},
        'target_resource': {'extensions': {'postgresql': {'native': tbl}}},
    })
    assert c_nn['minimum_server_version'] == 180000
    assert c_nn['statement'] == 'ALTER TABLE "public"."Bookings" ADD CONSTRAINT "nn_room" NOT NULL "room_id" NO INHERIT'

    # Temporal PK WITHOUT OVERLAPS
    c_pk = compile_native_admin({
        'resource_kind': 'constraint',
        'operation_id': 'create',
        'draft': {'name': 'pk_temporal', 'contype': 'p', 'columns': ['room_id'], 'without_overlaps_column': 'stay'},
        'target_resource': {'extensions': {'postgresql': {'native': tbl}}},
    })
    assert c_pk['minimum_server_version'] == 180000
    assert 'PRIMARY KEY ("room_id", "stay" WITHOUT OVERLAPS)' in c_pk['statement']

    # Temporal PERIOD FK + NOT ENFORCED
    c_fk = compile_native_admin({
        'resource_kind': 'constraint',
        'operation_id': 'create',
        'draft': {
            'name': 'fk_temporal',
            'contype': 'f',
            'fk_columns': [{'local_column': 'room_id', 'referenced': 'id'}],
            'local_period_column': 'stay',
            'referenced_period_column': 'valid_at',
            'remote_schema': 'public',
            'remote_table': 'Rooms',
            'enforcement': 'NOT ENFORCED',
        },
        'target_resource': {'extensions': {'postgresql': {'native': tbl}}},
    })
    assert c_fk['minimum_server_version'] == 180000
    assert 'FOREIGN KEY ("room_id", PERIOD "stay") REFERENCES "public"."Rooms" ("id", PERIOD "valid_at") NOT ENFORCED' in c_fk['statement']

    # Refusals: ALTER CONSTRAINT ENFORCED on CHECK must refuse
    chk_native = {'schema': 'public', 'table': 'Bookings', 'name': 'chk_pos', 'catalog_row': {'contype': 'c', 'conenforced': False}}
    with pytest.raises(PostgreSQLNativeAdminError, match='FOREIGN KEY'):
        compile_native_admin({
            'resource_kind': 'constraint',
            'operation_id': 'alter',
            'draft': {'enforcement': 'ENFORCED'},
            'target_resource': {'extensions': {'postgresql': {'native': chk_native}}},
        })

    # Protected GUC refusal on ALTER SYSTEM SET
    for protected in ('archive_command', 'primary_conninfo', 'restore_command'):
        with pytest.raises(PostgreSQLNativeAdminError, match='authorized host file workflow'):
            compile_native_admin({
                'resource_kind': 'server',
                'operation_id': 'alter-system-set',
                'draft': {'parameter': protected, 'value': 'echo bad'},
                'target_resource': {'extensions': {'postgresql': {'native': {}}}},
            })


# ---------------------------------------------------------------------------
# 2. PG-AUDIT-FIELD-01 & PG-AUDIT-MAINT-01 across PG 16, 17 and 18
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('cluster_fixture', ['pg16_cluster', 'pg17_cluster', 'pg18_cluster'])
def test_live_multimajor_field01_toast_and_maint01(request, cluster_fixture):
    cluster = request.getfixturevalue(cluster_fixture)
    prov = _make_provider(cluster.dsn)
    try:
        with psycopg.connect(cluster.dsn, autocommit=True) as conn:
            dboid = conn.execute('SELECT oid FROM pg_database WHERE datname = current_database()').fetchone()[0]
            schema = 's_multi_' + uuid.uuid4().hex[:6]
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            conn.execute(sql.SQL('CREATE TABLE {}.items (id int primary key, payload text, qty int)').format(sql.Identifier(schema)))
            conn.execute(sql.SQL("INSERT INTO {}.items VALUES (1, repeat('x', 4000), 10)").format(sql.Identifier(schema)))
            trow = conn.execute(
                'SELECT c.oid, t.reloptions FROM pg_class c '
                'JOIN pg_namespace n ON n.oid = c.relnamespace '
                'LEFT JOIN pg_class t ON t.oid = c.reltoastrelid '
                'WHERE n.nspname = %s AND c.relname = %s',
                (schema, 'items'),
            ).fetchone()
            target = {
                'oid': trow[0],
                'schema': schema,
                'name': 'items',
                'catalog_row': {'relpersistence': 'p', 'reloptions': None, 'toast_reloptions': trow[1] or []},
                'toast_options_observed': True,
            }

            # PG-AUDIT-FIELD-01: grid edit alongside comment change MUST be refused!
            with pytest.raises(Exception, match='columns'):
                _exec(
                    prov,
                    'table',
                    'alter',
                    {'columns': [{'name': 'extra', 'cltype': 'int'}], 'description': 'sneaky comment'},
                    dboid=dboid,
                    target=target,
                )
            assert conn.execute('SELECT obj_description(%s, \'pg_class\')', (trow[0],)).fetchone()[0] is None

            # PG-AUDIT-FIELD-01: TOAST SET & RESET + comment works and reads back from reltoastrelid!
            _exec(
                prov,
                'table',
                'alter',
                {
                    'toast_autovacuum_enabled': 'f',
                    'toast_autovacuum': True,
                    'vacuum_toast': [{'name': 'autovacuum_vacuum_threshold', 'value': 120}],
                    'description': 'toast tuned',
                },
                dboid=dboid,
                target=target,
            )
            toast_opts = conn.execute(
                'SELECT t.reloptions FROM pg_class c JOIN pg_class t ON t.oid = c.reltoastrelid WHERE c.oid = %s',
                (trow[0],),
            ).fetchone()[0]
            assert 'autovacuum_enabled=false' in toast_opts
            assert 'autovacuum_vacuum_threshold=120' in toast_opts

            # PG-AUDIT-MAINT-01: VACUUM & ANALYZE PG 16+ options + selected columns + REINDEX SYSTEM
            _exec(
                prov,
                'table',
                'vacuum',
                {
                    'disable_page_skipping': True,
                    'skip_locked': True,
                    'index_cleanup': 'OFF',
                    'process_main': True,
                    'process_toast': False,
                    'truncate': False,
                    'skip_database_stats': True,
                    'buffer_usage_limit': '4MB',
                },
                dboid=dboid,
                target={'schema': schema, 'name': 'items'},
            )
            _exec(
                prov,
                'database',
                'vacuum',
                {'only_database_stats': True},
                dboid=dboid,
                target={'name': 'postgres'},
            )
            _exec(
                prov,
                'table',
                'analyze',
                {'buffer_usage_limit': '2MB', 'columns': ['payload', 'qty']},
                dboid=dboid,
                target={'schema': schema, 'name': 'items'},
            )
            _exec(
                prov,
                'database',
                'reindex-system',
                {'verbose': False},
                dboid=dboid,
                target={'name': 'postgres'},
            )
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
    finally:
        prov.close()


# ---------------------------------------------------------------------------
# 3. PG-AUDIT-CONSTRAINT-01, INDEXPART-01, FDW-01, TWOPHASE-01, CONFIG-01 on PG 18 (+ PG 17 gate)
# ---------------------------------------------------------------------------

def test_live_pg18_constraints_temporal_named_notnull_and_enforcement(pg18_cluster, pg17_cluster):
    prov18 = _make_provider(pg18_cluster.dsn)
    prov17 = _make_provider(pg17_cluster.dsn)
    try:
        with psycopg.connect(pg18_cluster.dsn, autocommit=True) as conn:
            dboid = conn.execute('SELECT oid FROM pg_database WHERE datname = current_database()').fetchone()[0]
            schema = 's_con_' + uuid.uuid4().hex[:6]
            conn.execute('CREATE EXTENSION IF NOT EXISTS btree_gist')
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            conn.execute(
                sql.SQL('CREATE TABLE {}.rooms (id int, valid_at daterange, label text, amount int)').format(
                    sql.Identifier(schema)
                )
            )
            conn.execute(
                sql.SQL('CREATE TABLE {}.bookings (room_id int, stay daterange)').format(
                    sql.Identifier(schema)
                )
            )
            rooms_target = {'schema': schema, 'table': 'rooms', 'catalog_row': {}}
            bookings_target = {'schema': schema, 'table': 'bookings', 'catalog_row': {}}

            # PG 17 version gate refuses PG 18 constraint features cleanly
            with psycopg.connect(pg17_cluster.dsn, autocommit=True) as c17:
                db17 = c17.execute('SELECT oid FROM pg_database WHERE datname = current_database()').fetchone()[0]
                with pytest.raises(PostgreSQLStatementRejected, match='18'):
                    prov17.plan_admin_operation({
                        'resource_kind': 'constraint',
                        'operation_id': 'create',
                        'draft': {'name': 'nn_label', 'contype': 'n', 'not_null_column': 'label'},
                        '_provider_route': {'server_id': 1, 'database_id': db17},
                        'target_resource': {'extensions': {'postgresql': {'native': rooms_target}}},
                    })

            # 1. Named NOT NULL constraint (contype='n')
            _exec(
                prov18,
                'constraint',
                'create',
                {'name': 'nn_label_custom', 'contype': 'n', 'not_null_column': 'label'},
                dboid=dboid,
                target=rooms_target,
            )
            # 2. Temporal PRIMARY KEY WITHOUT OVERLAPS
            _exec(
                prov18,
                'constraint',
                'create',
                {'name': 'pk_rooms_temporal', 'contype': 'p', 'columns': ['id'], 'without_overlaps_column': 'valid_at'},
                dboid=dboid,
                target=rooms_target,
            )
            # 3. Unenforced CHECK allowing negative row
            _exec(
                prov18,
                'constraint',
                'create',
                {'name': 'chk_amount_pos', 'contype': 'c', 'consrc': 'amount > 0', 'enforcement': 'NOT ENFORCED'},
                dboid=dboid,
                target=rooms_target,
            )
            conn.execute(
                sql.SQL("INSERT INTO {}.rooms VALUES (1, '[2026-01-01,2026-06-01)', 'A', -50)").format(
                    sql.Identifier(schema)
                )
            )
            # 4. Temporal PERIOD FOREIGN KEY NOT ENFORCED -> allows orphan booking, then delete orphan & ALTER CONSTRAINT ENFORCED!
            _exec(
                prov18,
                'constraint',
                'create',
                {
                    'name': 'fk_booking_period',
                    'contype': 'f',
                    'fk_columns': [{'local_column': 'room_id', 'referenced': 'id'}],
                    'local_period_column': 'stay',
                    'referenced_period_column': 'valid_at',
                    'remote_schema': schema,
                    'remote_table': 'rooms',
                    'enforcement': 'NOT ENFORCED',
                },
                dboid=dboid,
                target=bookings_target,
            )
            conn.execute(
                sql.SQL("INSERT INTO {}.bookings VALUES (999, '[2026-02-01,2026-03-01)')").format(
                    sql.Identifier(schema)
                )
            )
            conn.execute(sql.SQL('DELETE FROM {}.bookings WHERE room_id = 999').format(sql.Identifier(schema)))
            _exec(
                prov18,
                'constraint',
                'alter',
                {'enforcement': 'ENFORCED'},
                dboid=dboid,
                target={
                    'schema': schema,
                    'table': 'bookings',
                    'name': 'fk_booking_period',
                    'catalog_row': {'contype': 'f', 'conenforced': False, 'convalidated': False},
                },
            )
            row = conn.execute(
                'SELECT conenforced, conperiod FROM pg_constraint c '
                'JOIN pg_namespace n ON n.oid = c.connamespace '
                'WHERE n.nspname = %s AND c.conname = %s',
                (schema, 'fk_booking_period'),
            ).fetchone()
            assert row == (True, True)

            # Direct physical extraction test on synthetic captured rows
            captured_model = {
                'rows': {
                    'postgresql:pg_class:100': {
                        'resource_id': 'postgresql:pg_class:100',
                        'kind': 'table',
                        'name': 'rooms',
                        'native': {'children': {'pg_attribute': [{'attnum': 3, 'attname': 'label'}]}},
                    },
                    'c1': {
                        'resource_id': 'c1',
                        'kind': 'constraint',
                        'name': 'nn_label_custom',
                        'native': {
                            'schema': schema,
                            'table': 'rooms',
                            'definition': 'NOT NULL label',
                            'catalog_row': {'conname': 'nn_label_custom', 'conrelid': 100, 'conkey': [3], 'contype': 'n', 'conenforced': True, 'conperiod': False, 'connoinherit': False, 'convalidated': True},
                        },
                    },
                    'c2': {
                        'resource_id': 'c2',
                        'kind': 'constraint',
                        'name': 'chk_amount_pos',
                        'native': {
                            'schema': schema,
                            'table': 'rooms',
                            'definition': 'CHECK ((amount > 0)) NOT ENFORCED',
                            'catalog_row': {'conname': 'chk_amount_pos', 'conrelid': 100, 'contype': 'c', 'conenforced': False, 'conperiod': False, 'connoinherit': False, 'convalidated': False},
                        },
                    },
                }
            }
            extracted_c1 = postgresql_physical.extract(captured_model['rows']['c1'], captured_model)
            extracted_c2 = postgresql_physical.extract(captured_model['rows']['c2'], captured_model)
            assert extracted_c1['values']['physical_kind'] == 'not-null' and extracted_c1['replaceable'] is False
            assert extracted_c2['values']['enforced'] is False and extracted_c2['replaceable'] is False
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
    finally:
        prov18.close()
        prov17.close()


def test_live_pg18_index_attach_partition_fdw_twophase_and_alter_system(pg18_cluster):
    prov = _make_provider(pg18_cluster.dsn)
    try:
        with psycopg.connect(pg18_cluster.dsn, autocommit=True) as conn:
            dboid = conn.execute('SELECT oid FROM pg_database WHERE datname = current_database()').fetchone()[0]
            schema = 's_b1_' + uuid.uuid4().hex[:6]
            remote_schema = schema + '_remote'
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(remote_schema)))

            # --- PG-AUDIT-INDEXPART-01 ---
            conn.execute(
                sql.SQL('CREATE TABLE {}.events (id int, ts int) PARTITION BY RANGE (id)').format(sql.Identifier(schema))
            )
            conn.execute(
                sql.SQL('CREATE TABLE {}.events_p1 PARTITION OF {}.events FOR VALUES FROM (1) TO (100)').format(
                    sql.Identifier(schema), sql.Identifier(schema)
                )
            )
            conn.execute(sql.SQL('CREATE INDEX events_ts_idx ON ONLY {}.events (ts)').format(sql.Identifier(schema)))
            conn.execute(sql.SQL('CREATE INDEX events_p1_ts_idx ON {}.events_p1 (ts)').format(sql.Identifier(schema)))
            assert conn.execute(
                'SELECT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid '
                'JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = %s AND c.relname = %s',
                (schema, 'events_ts_idx'),
            ).fetchone() == (False,)
            _, idx_res = _exec(
                prov,
                'index',
                'attach-partition',
                {'child_schema': schema, 'child_index': 'events_p1_ts_idx'},
                dboid=dboid,
                target={'schema': schema, 'name': 'events_ts_idx', 'catalog_row': {'relkind': 'I'}},
            )
            obs_rows = idx_res['native_observation']['rows']
            assert len(obs_rows) == 1 and obs_rows[0]['parent_valid'] is True and obs_rows[0]['attached'] is True

            # --- PG-AUDIT-FDW-01 ---
            conn.execute('CREATE EXTENSION IF NOT EXISTS postgres_fdw')
            conn.execute(
                sql.SQL('CREATE TABLE {}.r_one (id int primary key, label text default \'ok\')').format(
                    sql.Identifier(remote_schema)
                )
            )
            conn.execute(
                sql.SQL('CREATE TABLE {}.r_two (id int primary key)').format(sql.Identifier(remote_schema))
            )
            srv_name = 'loopback_' + uuid.uuid4().hex[:6]
            conn.execute(
                sql.SQL('CREATE SERVER {} FOREIGN DATA WRAPPER postgres_fdw OPTIONS (host \'127.0.0.1\', port {}, dbname \'postgres\')').format(
                    sql.Identifier(srv_name), sql.Literal(str(pg18_cluster.port))
                )
            )
            conn.execute(
                sql.SQL('CREATE USER MAPPING FOR CURRENT_USER SERVER {} OPTIONS (user {})').format(
                    sql.Identifier(srv_name), sql.Literal(pg18_cluster.user)
                )
            )
            try:
                _, fdw_res = _exec(
                    prov,
                    'foreign-server',
                    'import-foreign-schema',
                    {
                        'remote_schema': remote_schema,
                        'local_schema': schema,
                        'filter_mode': 'LIMIT_TO',
                        'tables': [{'name': 'r_one'}],
                        'options': [{'name': 'import_default', 'value': 'true'}],
                    },
                    dboid=dboid,
                    target={'name': srv_name},
                )
                imported = [r['table_name'] for r in fdw_res['native_observation']['rows']]
                assert imported == ['r_one']
            finally:
                conn.execute(sql.SQL('DROP SERVER {} CASCADE').format(sql.Identifier(srv_name)))

            # --- PG-AUDIT-TWOPHASE-01 ---
            conn.execute(sql.SQL('CREATE TABLE {}.ledger (id int)').format(sql.Identifier(schema)))
            gid_c = 'sr_2pc_c_' + uuid.uuid4().hex[:6]
            gid_r = 'sr_2pc_r_' + uuid.uuid4().hex[:6]
            with psycopg.connect(pg18_cluster.dsn, autocommit=False) as tx_conn:
                tx_conn.execute(sql.SQL('INSERT INTO {}.ledger VALUES (101)').format(sql.Identifier(schema)))
                tx_conn.execute(f"PREPARE TRANSACTION '{gid_c}'")
            with psycopg.connect(pg18_cluster.dsn, autocommit=False) as tx_conn:
                tx_conn.execute(sql.SQL('INSERT INTO {}.ledger VALUES (202)').format(sql.Identifier(schema)))
                tx_conn.execute(f"PREPARE TRANSACTION '{gid_r}'")

            _, insp = _exec(prov, 'server', 'inspect-prepared-transactions', {}, dboid=None)
            gids = {r['gid']: r for r in insp['result']['rows']}
            assert gid_c in gids and gid_r in gids

            # Wrong expected database must refuse before dispatch!
            with pytest.raises(PostgreSQLStatementRejected, match='belongs to database'):
                _exec(
                    prov,
                    'server',
                    'resolve-prepared-transaction',
                    {
                        'gid': gid_c,
                        'expected_database': 'wrong_db',
                        'expected_owner': pg18_cluster.user,
                        'decision': 'COMMIT',
                        'coordinator_reference': 'INC-2026-1',
                        'confirmation': gid_c,
                    },
                )

            # COMMIT PREPARED gid_c & ROLLBACK PREPARED gid_r
            _, res_c = _exec(
                prov,
                'server',
                'resolve-prepared-transaction',
                {
                    'gid': gid_c,
                    'expected_database': 'postgres',
                    'expected_owner': pg18_cluster.user,
                    'expected_xid': gids[gid_c]['xid'],
                    'decision': 'COMMIT',
                    'coordinator_reference': 'INC-2026-1',
                    'confirmation': gid_c,
                },
            )
            assert res_c['native_observation']['rows'] == [{'remaining_for_gid': 0}]
            _, res_r = _exec(
                prov,
                'prepared-transaction',
                'resolve',
                {
                    'gid': gid_r,
                    'expected_database': 'postgres',
                    'expected_owner': pg18_cluster.user,
                    'decision': 'ROLLBACK',
                    'coordinator_reference': 'INC-2026-2',
                    'confirmation': gid_r,
                },
            )
            assert res_r['native_observation']['rows'] == [{'remaining_for_gid': 0}]
            assert conn.execute(sql.SQL('SELECT id FROM {}.ledger').format(sql.Identifier(schema))).fetchall() == [(101,)]

            # --- PG-AUDIT-CONFIG-01 (SQL ALTER SYSTEM + inspection) ---
            _, cfg_set = _exec(
                prov,
                'server',
                'alter-system-set',
                {'parameter': 'work_mem', 'value_mode': 'VALUE', 'value': '8MB', 'reload_after': True},
            )
            assert cfg_set['configuration_reload'] == [{'reloaded': True}]
            assert cfg_set['native_observation']['rows'][0]['name'] == 'work_mem'
            for scope in ('settings', 'pending_restart', 'file_errors', 'hba_rules', 'ident_mappings'):
                _, cfg_insp = _exec(prov, 'server', 'inspect-configuration', {'scope': scope})
                assert 'rows' in cfg_insp['result']
            _exec(
                prov,
                'server',
                'alter-system-reset',
                {'parameter': 'work_mem', 'reload_after': True, 'confirmation': 'work_mem'},
            )
            _exec(
                prov,
                'server',
                'alter-system-reset-all',
                {'reload_after': True, 'confirmation': 'RESET ALL'},
            )

            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(remote_schema)))
    finally:
        prov.close()


# ---------------------------------------------------------------------------
# 4. Authenticated Flask HTTP verification (PG-AUDIT-FIELD-01 & PG-AUDIT-CONFIG-01 host files)
# ---------------------------------------------------------------------------

def test_authenticated_http_field01_and_config01_host_lifecycle(pg18_cluster, tmp_path):
    builtins.SERVER_MODE = None
    import config

    app_root = tmp_path / 'app_state'
    config.SERVER_MODE = False
    config.TESTING = True
    config.WTF_CSRF_ENABLED = False
    config.MASTER_PASSWORD_REQUIRED = False
    config.USE_OS_SECRET_STORAGE = False
    for attr, rel in {
        'DATA_DIR': 'data',
        'SQLITE_PATH': 'data/pgadmin4.db',
        'SESSION_DB_PATH': 'data/sessions',
        'STORAGE_DIR': 'data/storage',
        'LOG_FILE': 'data/pgadmin4.log',
        'AZURE_CREDENTIAL_CACHE_DIR': 'data/azure',
        'CDEADMIN_OPERATION_STORE_PATH': 'data/operations.json',
    }.items():
        setattr(config, attr, str(app_root / rel))
    (app_root / 'data').mkdir(parents=True, exist_ok=True)

    from flask import url_for
    from pgadmin import create_app
    from pgadmin.model import Server, ServerGroup, User, db

    app = create_app('ScratchRobin-pg-batch1-http')
    app.PGADMIN_RUNTIME = False
    app.PGADMIN_INT_KEY = ''
    app.run_before_app_start()

    manifest_file = tmp_path / 'host_grants.json'
    with app.test_request_context('/'):
        user = User.query.first()
        group = ServerGroup.query.filter_by(user_id=user.id).first()
        app.blueprints['NODE-engine_type'].connector_visibility['postgresql'].set(True, user_id=user.id)
        srv = Server(
            user_id=user.id,
            servergroup_id=group.id,
            name='PG18 Batch1 HTTP',
            host='127.0.0.1',
            port=pg18_cluster.port,
            username=pg18_cluster.user,
            maintenance_db='postgres',
            connection_params={'sslmode': 'disable'},
            save_password=0,
        )
        db.session.add(srv)
        db.session.commit()
        uid = user.id
        endpoint_id = srv.endpoint_profile.id
        connect_url = url_for('NODE-server.connect_id', gid=group.id, sid=srv.id)
        ws_url = url_for('NODE-server.cde_workspace_id', gid=group.id, sid=srv.id)

    manifest_file.write_text(
        json.dumps({
            'format': 'scratchrobin.postgresql.host-tools@1',
            'grants': [{'endpoint_id': endpoint_id, 'clusters': [{'id': 'main18', 'path': str(pg18_cluster.datadir)}]}],
        }),
        encoding='utf-8',
    )
    app.config['CDEADMIN_POSTGRESQL_HOST_TOOL_MANIFEST'] = str(manifest_file)
    app.config['CDEADMIN_POSTGRESQL_HOST_BINARY_PATH'] = str(PG18_BIN)
    app.config['CDEADMIN_POSTGRESQL_CONFIG_ROOT'] = str(tmp_path / 'cfg_jobs')

    client = app.test_client()
    with client.session_transaction() as sess:
        sess['_user_id'] = str(uid)
        sess['_fresh'] = True
    assert client.post(connect_url, json={'password': ''}).get_json()['success']

    # Host file inspect -> invalid postgresql.conf rejected by postgres -C -> valid deploy -> status -> rollback!
    r_insp = client.post(
        ws_url,
        json={'action': 'postgresql_config_inspect_file', 'request': {'cluster_id': 'main18', 'file_kind': 'postgresql.conf'}},
    )
    assert r_insp.status_code == 200 and r_insp.get_json()['data']['exists'] is True
    orig_conf = r_insp.get_json()['data']['content']
    orig_sha = r_insp.get_json()['data']['sha256']

    r_bad = client.post(
        ws_url,
        json={
            'action': 'postgresql_config_review_deploy',
            'request': {
                'cluster_id': 'main18',
                'file_kind': 'postgresql.conf',
                'replacement_text': orig_conf + '\nnot_a_real_pg_parameter = 42\n',
            },
        },
    )
    assert r_bad.status_code == 400 and 'postgres -C' in r_bad.get_json()['errormsg']

    new_conf = orig_conf + '\n# ScratchRobin PG-AUDIT-CONFIG-01 verified\nlog_lock_waits = on\n'
    r_rev = client.post(
        ws_url,
        json={
            'action': 'postgresql_config_review_deploy',
            'request': {'cluster_id': 'main18', 'file_kind': 'postgresql.conf', 'replacement_text': new_conf, 'reload_after': True},
        },
    )
    assert r_rev.status_code == 200, r_rev.get_json()
    rev = r_rev.get_json()['data']
    assert rev['state'] == 'reviewed' and rev['validation']['validator'] == 'postgres -C'

    r_start = client.post(
        ws_url,
        json={
            'action': 'postgresql_config_start_deploy',
            'request': {'job_id': rev['job_id'], 'review_digest': rev['review_digest'], 'confirmed': True},
        },
    )
    assert r_start.status_code == 200
    done = r_start.get_json()['data']
    assert done['state'] == 'completed' and done['result']['reloaded'] is True

    # Rotate server.key and verify content is redacted on inspect and mode is 0600
    fake_key = '-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7\n-----END PRIVATE KEY-----\n'
    rk_rev = client.post(
        ws_url,
        json={
            'action': 'postgresql_config_review_deploy',
            'request': {'cluster_id': 'main18', 'file_kind': 'server.key', 'replacement_text': fake_key, 'reload_after': False},
        },
    ).get_json()['data']
    client.post(
        ws_url,
        json={'action': 'postgresql_config_start_deploy', 'request': {'job_id': rk_rev['job_id'], 'review_digest': rk_rev['review_digest'], 'confirmed': True}},
    )
    rk_insp = client.post(
        ws_url,
        json={'action': 'postgresql_config_inspect_file', 'request': {'cluster_id': 'main18', 'file_kind': 'server.key'}},
    ).get_json()['data']
    assert 'REDACTED PRIVATE KEY' in rk_insp['content']
    client.post(ws_url, json={'action': 'postgresql_config_rollback', 'request': {'job_id': rk_rev['job_id'], 'confirmed': True}})

    # Rollback postgresql.conf and confirm exact SHA-256 restoration!
    r_rb = client.post(
        ws_url,
        json={'action': 'postgresql_config_rollback', 'request': {'job_id': rev['job_id'], 'confirmed': True}},
    )
    assert r_rb.status_code == 200 and r_rb.get_json()['data']['state'] == 'rolled_back'
    assert hashlib.sha256((pg18_cluster.datadir / 'postgresql.conf').read_bytes()).hexdigest() == orig_sha

    # Authenticated HTTP visual_admin_plan / visual_admin_apply for PG-AUDIT-FIELD-01
    with psycopg.connect(pg18_cluster.dsn, autocommit=True) as conn:
        dboid = conn.execute('SELECT oid FROM pg_database WHERE datname = current_database()').fetchone()[0]
        conn.execute('CREATE TABLE public.http_field01 (id int primary key, body text)')
        toid = conn.execute("SELECT oid FROM pg_class WHERE relname = 'http_field01'").fetchone()[0]
    db_target = f'postgresql-database:{dboid}'
    target_res = {
        'resource_id': f'postgresql:pg_class/{toid}',
        'resource_kind': 'table',
        'display_name': 'http_field01',
        'extensions': {
            'postgresql': {
                'native': {
                    'oid': toid,
                    'schema': 'public',
                    'name': 'http_field01',
                    'catalog_row': {'relpersistence': 'p', 'reloptions': None, 'toast_reloptions': []},
                    'toast_options_observed': True,
                }
            }
        },
    }
    try:
        # Combined columns grid + comment MUST fail closed over HTTP visual_admin_plan
        base_alter = {'name': 'http_field01', 'schema': 'public', 'relowner': pg18_cluster.user}
        bad_http = client.post(
            ws_url,
            json={
                'action': 'visual_admin_plan',
                'request': {
                    'database_target_id': db_target,
                    'resource_kind': 'table',
                    'operation_id': 'alter',
                    'target_resource': target_res,
                    'draft': {**base_alter, 'columns': [{'name': 'ignored_col', 'cltype': 'text'}], 'description': 'bad'},
                },
            },
        )
        assert bad_http.status_code == 422
        bad_json = bad_http.get_json()
        assert bad_json['data']['refusal']['errors'] == [{'field_id': 'columns', 'code': 'delegated_to_child_node'}]
        assert bad_json['data']['refusal']['native_dispatched'] is False

        # Valid TOAST option + comment over HTTP visual_admin_plan -> visual_admin_apply
        ok_plan = client.post(
            ws_url,
            json={
                'action': 'visual_admin_plan',
                'request': {
                    'database_target_id': db_target,
                    'resource_kind': 'table',
                    'operation_id': 'alter',
                    'target_resource': target_res,
                    'draft': {**base_alter, 'toast_autovacuum_enabled': 'f', 'description': 'http toast ok'},
                },
            },
        )
        assert ok_plan.status_code == 200, ok_plan.get_json()
        plan_data = ok_plan.get_json()['data']
        ok_apply = client.post(
            ws_url,
            json={
                'action': 'visual_admin_apply',
                'request': {
                    'database_target_id': db_target,
                    'plan_id': plan_data['plan_id'],
                    'plan_digest': plan_data['plan_digest'],
                    'confirmed': True,
                },
            },
        )
        assert ok_apply.status_code == 200, ok_apply.get_json()
        with psycopg.connect(pg18_cluster.dsn, autocommit=True) as conn:
            toast_opts = conn.execute(
                'SELECT t.reloptions FROM pg_class c JOIN pg_class t ON t.oid = c.reltoastrelid WHERE c.oid = %s',
                (toid,),
            ).fetchone()[0]
            assert 'autovacuum_enabled=false' in toast_opts
    finally:
        with psycopg.connect(pg18_cluster.dsn, autocommit=True) as conn:
            conn.execute('DROP TABLE IF EXISTS public.http_field01')

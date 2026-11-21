"""Live PostgreSQL 18 qualification for Batch 3:
- PG-AUDIT-EXTACL-01 (pg_init_privs extension privilege-baseline capture & delta reconstruction)
- PG-AUDIT-DDN-01 (expanded DDN planner: generated column SET/DROP EXPRESSION, column stats/storage/compression,
  PG 18 FK ENFORCED/NOT ENFORCED, sequence params, view replacement, extended stats target, table persistence/owner/ACLs)
- PG-AUDIT-RETAINEDADMIN-01 (original-session native administration & DDN migration for pg_temp and uncommitted objects
  preserving caller transaction state without reconnecting or committing caller work)
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import socket
import subprocess
import sys
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools'), str(ROOT / 'tools/tests')]

from pgadmin.cdeadmin.core import EndpointContext  # noqa: E402
from pgadmin.cdeadmin.providers.postgresql import session_catalog  # noqa: E402
from pgadmin.cdeadmin.providers.postgresql.catalog_capture import capture  # noqa: E402
from pgadmin.cdeadmin.providers.postgresql.extension_acls import (  # noqa: E402
    reconstruct_extension_acl_deltas,
)
from pgadmin.cdeadmin.providers.postgresql.provider import (  # noqa: E402
    LEGACY_DRIVER_TYPE,
    PostgreSQLProvider,
    PostgreSQLStatementRejected,
)
from pgadmin.cdeadmin.providers.postgresql.schema_application import (  # noqa: E402
    _model,
    apply_retained_session_review,
    apply_review,
)
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export  # noqa: E402
from pgadmin.cdeadmin.workspace.postgresql_schema_apply import (  # noqa: E402
    PostgreSQLSchemaApplications,
)
from pgadmin.cdeadmin.workspace.postgresql_schema_plan import build_plan  # noqa: E402
from test_ui_descriptor_operations_postgresql import Driver, Permissions  # noqa: E402

PG18_BIN = Path('/usr/lib/postgresql/18/bin')
USER = __import__('getpass').getuser()


@pytest.fixture(scope='module')
def pg18(tmp_path_factory):
    if not (PG18_BIN / 'initdb').is_file():
        pytest.skip('PostgreSQL 18 binaries unavailable')
    base = tmp_path_factory.mktemp('pg18_batch3')
    datadir = base / 'data'
    subprocess.run(
        [str(PG18_BIN / 'initdb'), '-D', str(datadir), '--no-data-checksums', '--auth=trust', '--no-locale', '--encoding=UTF8'],
        check=True,
        capture_output=True,
    )
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        port = s.getsockname()[1]
    opts = f"-h 127.0.0.1 -p {port} -c unix_socket_directories=''"
    subprocess.run(
        [str(PG18_BIN / 'pg_ctl'), '-D', str(datadir), '-l', str(base / 'pg.log'), '-o', opts, '-w', 'start'],
        check=True,
        capture_output=True,
    )
    dsn = make_conninfo(host='127.0.0.1', port=port, user=USER, dbname='postgres')
    try:
        yield dsn
    finally:
        if (datadir / 'postmaster.pid').exists():
            subprocess.run([str(PG18_BIN / 'pg_ctl'), '-D', str(datadir), '-m', 'immediate', '-w', 'stop'], capture_output=True)


def _provider(dsn: str):
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
    return PostgreSQLProvider(ctx, Permissions(), Driver(dsn), catalog_source=object())


# ---------------------------------------------------------------------------
# 1. PG-AUDIT-EXTACL-01: Live pg_init_privs capture & post-extension ACL deltas
# ---------------------------------------------------------------------------

def test_pg_init_privs_capture_and_extension_acl_delta_reconstruction(pg18):
    with psycopg.connect(pg18, autocommit=True) as conn:
        dboid = conn.execute('SELECT oid FROM pg_database WHERE datname = current_database()').fetchone()[0]
        role = 'sr_ext_reader_' + uuid.uuid4().hex[:6]
        conn.execute(sql.SQL('CREATE ROLE {}').format(sql.Identifier(role)))
        conn.execute('CREATE EXTENSION IF NOT EXISTS pg_stat_statements')
        try:
            # Capture fresh extension state: built-in pg_stat_statements view has pg_init_privs (privtype='e')
            cap_initial = capture(conn, dboid)
            obs_sections = {o['section']: o for o in cap_initial['observations']}
            assert obs_sections['pg_init_privs']['available'] is True
            assert obs_sections['pg_init_privs']['rows'] >= 1

            ext_view = next(
                r for r in cap_initial['resources']
                if r['resource_kind'] == 'view' and r['display_name'] == 'pg_stat_statements'
            )
            assert ext_view['native'].get('initial_privileges'), ext_view
            # Before any admin customization, delta relative to pg_init_privs MUST be empty!
            assert reconstruct_extension_acl_deltas(ext_view) == []

            # Now grant SELECT to our custom role and revoke SELECT from PUBLIC on pg_stat_statements_info
            conn.execute(sql.SQL('GRANT SELECT ON public.pg_stat_statements TO {}').format(sql.Identifier(role)))
            conn.execute('REVOKE SELECT ON public.pg_stat_statements_info FROM PUBLIC')

            cap_modified = capture(conn, dboid)
            mod_view = next(
                r for r in cap_modified['resources']
                if r['resource_kind'] == 'view' and r['display_name'] == 'pg_stat_statements'
            )
            mod_info = next(
                r for r in cap_modified['resources']
                if r['resource_kind'] == 'view' and r['display_name'] == 'pg_stat_statements_info'
            )
            deltas_view = reconstruct_extension_acl_deltas(mod_view)
            deltas_info = reconstruct_extension_acl_deltas(mod_info)
            assert deltas_view == [f'GRANT SELECT ON TABLE "public"."pg_stat_statements" TO "{role}"']
            assert deltas_info == ['REVOKE SELECT ON TABLE "public"."pg_stat_statements_info" FROM PUBLIC']
        finally:
            conn.execute('DROP EXTENSION IF EXISTS pg_stat_statements CASCADE')
            conn.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(role)))


# ---------------------------------------------------------------------------
# 2. PG-AUDIT-DDN-01: Expanded DDN planner & schema_application live execution
# ---------------------------------------------------------------------------

def test_expanded_ddn_planner_live_apply_and_filter_is_never_delete(pg18, tmp_path):
    prov = _provider(pg18)
    try:
        with psycopg.connect(pg18, autocommit=True) as conn:
            dboid = conn.execute('SELECT oid FROM pg_database WHERE datname = current_database()').fetchone()[0]
            schema = 'sr_ddn_' + uuid.uuid4().hex[:6]
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            conn.execute(
                sql.SQL(
                    'CREATE TABLE {}.parent_t (id int primary key); '
                    'CREATE TABLE {}.orders ('
                    '  id int primary key, '
                    '  parent_id int, '
                    '  qty int, '
                    '  total int GENERATED ALWAYS AS (qty * 2) STORED, '
                    '  notes text, '
                    '  CONSTRAINT fk_parent FOREIGN KEY (parent_id) REFERENCES {}.parent_t(id) NOT ENFORCED'
                    '); '
                    'CREATE SEQUENCE {}.ord_seq INCREMENT BY 1 CACHE 1; '
                    'CREATE VIEW {}.ord_view AS SELECT id, qty FROM {}.orders'
                ).format(
                    sql.Identifier(schema),
                    sql.Identifier(schema),
                    sql.Identifier(schema),
                    sql.Identifier(schema),
                    sql.Identifier(schema),
                    sql.Identifier(schema),
                )
            )
            try:
                rec_stub = {'plan': {'endpoint_id': 'ep1', 'database_target_id': f'postgresql-database:{dboid}'}}
                baseline = _model(conn, rec_stub, dboid)

                # Filter-is-never-delete check: removing an object from desired produces a blocker, NEVER a DROP!
                filtered = deepcopy(baseline)
                seq_id = next(k for k, r in baseline['rows'].items() if r['kind'] == 'sequence' and r['name'] == 'ord_seq')
                filtered['rows'].pop(seq_id)
                bad_plan = build_plan(baseline, filtered, baseline)
                assert not bad_plan['ready_for_review']
                assert any('not deletion intent' in b['reason'] for b in bad_plan['blockers'])

                # Build desired model with:
                # 1) Generated column SET EXPRESSION (qty * 5) + column SET STATISTICS 250 + SET COMPRESSION lz4
                # 2) PG 18 Foreign Key NOT ENFORCED -> ENFORCED
                # 3) Sequence INCREMENT BY 10, CACHE 5, CYCLE
                # 4) View replacement (SELECT id, qty * 10 AS qty FROM ...)
                # 5) Table REPLICA IDENTITY FULL
                desired = deepcopy(baseline)
                tbl_id = next(k for k, r in desired['rows'].items() if r['kind'] == 'table' and r['name'] == 'orders')
                fk_id = next(k for k, r in desired['rows'].items() if r['kind'] == 'constraint' and r['name'] == 'fk_parent')
                vw_id = next(k for k, r in desired['rows'].items() if r['kind'] == 'view' and r['name'] == 'ord_view')

                desired['rows'][tbl_id]['native']['catalog_row']['relreplident'] = 'f'
                for attr in desired['rows'][tbl_id]['native']['children']['pg_attribute']:
                    if attr['attname'] == 'total':
                        attr['generated_expression'] = '(qty * 5)'
                    elif attr['attname'] == 'notes':
                        attr['attstattarget'] = 250
                        attr['attcompression'] = 'l'

                desired['rows'][fk_id]['native']['catalog_row']['conenforced'] = True
                desired['rows'][seq_id]['native']['children']['pg_sequence'][0]['seqincrement'] = 10
                desired['rows'][seq_id]['native']['children']['pg_sequence'][0]['seqcache'] = 5
                desired['rows'][seq_id]['native']['children']['pg_sequence'][0]['seqcycle'] = True
                desired['rows'][vw_id]['native']['definition'] = f'SELECT id, (qty * 10) AS qty FROM {schema}.orders'

                preview = build_plan(baseline, desired, baseline)
                assert preview['application_supported'], preview['blockers']
                op_kinds = {op['operation'] for op in preview['operations']}
                assert {
                    'set_replica_identity',
                    'set_generated_expression',
                    'set_column_statistics',
                    'set_column_compression',
                    'alter_constraint_enforcement',
                    'alter_sequence',
                    'replace_view',
                } <= op_kinds

                store = PostgreSQLSchemaApplications(tmp_path / 'ddn_reviews.json')
                receipt = store.review(preview, baseline, desired, 1, 'bound', f'postgresql-database:{dboid}')
                applied = store.apply(
                    {'review_id': receipt['review_id'], 'review_digest': receipt['review_digest'], 'confirmed': True},
                    1,
                    'bound',
                    lambda retained: apply_review(prov, {'server_id': 1, 'database_id': dboid}, retained),
                )
                assert applied['state'] == 'native_commit_returned', applied

                # Verify live database effects!
                conn.execute(sql.SQL('INSERT INTO {}.parent_t VALUES (1)').format(sql.Identifier(schema)))
                conn.execute(sql.SQL("INSERT INTO {}.orders (id, parent_id, qty, notes) VALUES (1, 1, 7, 'ok')").format(sql.Identifier(schema)))
                assert conn.execute(sql.SQL('SELECT total FROM {}.orders WHERE id = 1').format(sql.Identifier(schema))).fetchone() == (35,)
                assert conn.execute(sql.SQL('SELECT qty FROM {}.ord_view WHERE id = 1').format(sql.Identifier(schema))).fetchone() == (70,)
                assert conn.execute(
                    'SELECT conenforced FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace WHERE n.nspname = %s AND c.conname = %s',
                    (schema, 'fk_parent'),
                ).fetchone() == (True,)
                seq_row = conn.execute(
                    'SELECT seqincrement, seqcache, seqcycle FROM pg_sequence s JOIN pg_class c ON c.oid = s.seqrelid JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = %s AND c.relname = %s',
                    (schema, 'ord_seq'),
                ).fetchone()
                assert (int(seq_row[0]), int(seq_row[1]), seq_row[2]) == (10, 5, True)
            finally:
                conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
    finally:
        prov.close()


# ---------------------------------------------------------------------------
# 3. PG-AUDIT-RETAINEDADMIN-01: Original-session native admin & DDN migration
# ---------------------------------------------------------------------------

def test_retained_session_native_admin_and_ddn_temp_uncommitted_lifecycle(pg18, tmp_path):
    prov = _provider(pg18)
    try:
        with psycopg.connect(pg18, autocommit=True) as admin_conn:
            dboid = admin_conn.execute('SELECT oid FROM pg_database WHERE datname = current_database()').fetchone()[0]

        # Open two distinct retained sessions to verify temp-object isolation and savepoint semantics
        s1 = prov.open_session({'route': {'server_id': 1, 'database_id': dboid}})
        s2 = prov.open_session({'route': {'server_id': 1, 'database_id': dboid}})
        sid1, sid2 = s1['session_id'], s2['session_id']
        try:
            state1 = prov._sessions[sid1]
            state2 = prov._sessions[sid2]
            prov._ensure_native_connection(state1)
            prov._ensure_native_connection(state2)
            c1 = state1.connection.conn
            c2 = state2.connection.conn
            c1.autocommit = False

            # Start caller transaction on session 1 with a TEMP table and uncommitted row!
            c1.execute('CREATE TEMP TABLE sr_temp_orders (id int primary key, note text)')
            c1.execute("INSERT INTO sr_temp_orders VALUES (1, 'caller_uncommitted')")
            temp_nsp, temp_oid = c1.execute(
                "SELECT n.nspname, c.oid FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relname = 'sr_temp_orders'"
            ).fetchone()

            # 1) Nontransactional VACUUM inside active caller transaction MUST be refused without committing caller work!
            with pytest.raises(PostgreSQLStatementRejected, match='Nontransactional'):
                prov.plan_admin_operation({
                    'session_id': sid1,
                    'resource_kind': 'table',
                    'operation_id': 'vacuum',
                    'draft': {},
                    '_provider_route': {'server_id': 1, 'database_id': dboid},
                    'target_resource': {'extensions': {'postgresql': {'native': {'schema': temp_nsp, 'name': 'sr_temp_orders'}}}},
                })

            # 2) Native column creation on pg_temp table on original session 1 via savepoint (caller stays INTRANS!)
            col_plan = prov.plan_admin_operation({
                'session_id': sid1,
                'resource_kind': 'column',
                'operation_id': 'create',
                'draft': {'name': 'extra_tag', 'cltype': 'text'},
                '_provider_route': {'server_id': 1, 'database_id': dboid},
                'target_resource': {'extensions': {'postgresql': {'native': {'schema': temp_nsp, 'table': 'sr_temp_orders'}}}},
            })
            assert col_plan['command_preview']['retained_session']['session_id'] == sid1
            col_res = prov.apply_admin_operation({'provider_payload': col_plan['provider_payload']})
            assert col_res['independent_attachment'] is False
            assert col_res['caller_transaction_committed'] is False
            assert col_res['transaction_outcome'] == 'savepoint_released_pending_caller_commit'
            assert c1.info.transaction_status == psycopg.pq.TransactionStatus.INTRANS

            # Session 2 cannot see session 1's temp table
            prov._ensure_native_connection(state2)
            assert c2.execute("SELECT to_regclass('pg_temp.sr_temp_orders')").fetchone() == (None,)

            # 3) Retained-session DDN observation -> independent build_plan still refuses, allow_retained_session=True plans & applies!
            obs_cap = session_catalog.observe(state1)
            base_doc = build_export(
                obs_cap['resources'],
                endpoint_id='ep1',
                target_id=f'postgresql-database:{dboid}',
                generation=obs_cap['generation'],
                engine='postgresql',
                native_model=True,
            )
            desired_doc = deepcopy(base_doc)
            temp_key = f'postgresql:pg_class:{temp_oid}'
            desired_doc['rows'][temp_key]['native']['comment'] = 'temp comment via retained DDN'

            with pytest.raises(ValueError, match='Retained-session catalog observations cannot be applied as independent'):
                build_plan(base_doc, desired_doc, base_doc)

            ret_plan = build_plan(base_doc, desired_doc, base_doc, allow_retained_session=True)
            assert ret_plan['application_supported'], ret_plan['blockers']

            store = PostgreSQLSchemaApplications(tmp_path / 'ret_ddn.json')
            rev = store.review(ret_plan, base_doc, desired_doc, 1, 'bound', f'postgresql-database:{dboid}')
            app_res = store.apply(
                {'review_id': rev['review_id'], 'review_digest': rev['review_digest'], 'confirmed': True},
                1,
                'bound',
                lambda retained: apply_retained_session_review(prov, sid1, dboid, retained),
            )
            assert app_res['state'] == 'native_commit_returned' or app_res['outcome']['state'] == 'savepoint_released_pending_caller_commit'
            assert c1.execute('SELECT obj_description(%s, \'pg_class\')', (temp_oid,)).fetchone() == ('temp comment via retained DDN',)
            assert c1.info.transaction_status == psycopg.pq.TransactionStatus.INTRANS

            # 4) Caller ROLLBACK undoes the entire uncommitted temp creation + column + DDN comment cleanly!
            c1.rollback()
            assert c1.execute("SELECT to_regclass('pg_temp.sr_temp_orders')").fetchone() == (None,)
        finally:
            prov.close_session(s1)
            prov.close_session(s2)
    finally:
        prov.close()

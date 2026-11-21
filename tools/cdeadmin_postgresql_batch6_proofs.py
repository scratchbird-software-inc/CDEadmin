#!/usr/bin/env python3
"""Generate exact PostgreSQL 18.3 dialect & metrics contracts across all 197 provider-native tasks.

Runs against owned loopback `postgres:18.3` containers (primary + physical standby),
executes all 197 `dialect_task_ids()` through `PostgreSQLProvider.apply_admin_operation`
with live commit verification, runs `metric_gate`, regenerates
`postgresql_dialect_18_3.json` and `postgresql_metrics_18_3.json`, updates
`provider_manifest.json` provenance digests, and verifies `engine_contract_descriptor()`.
"""
from __future__ import annotations

import base64
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools'), str(ROOT / 'tools/tests')]


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wait_pg_ready(host: str, port: int, user: str, password: str, dbname: str = 'postgres') -> str:
    import psycopg
    deadline = time.monotonic() + 60
    while True:
        try:
            with psycopg.connect(
                host=host, port=port, user=user, dbname=dbname,
                password=password, autocommit=True, connect_timeout=2,
            ) as conn:
                ver = conn.execute('SHOW server_version_num').fetchone()[0]
                if ver != '180003':
                    raise RuntimeError(f'Expected PostgreSQL 180003, got {ver}')
                return ver
        except psycopg.OperationalError:
            if time.monotonic() >= deadline:
                raise RuntimeError('Owned PostgreSQL 18.3 container did not become ready')
            time.sleep(0.25)


def _make_provider(dsn: str):
    import psycopg
    from psycopg import Cursor
    from psycopg.rows import dict_row
    from pgadmin.cdeadmin.core import EndpointContext
    from pgadmin.cdeadmin.providers.postgresql.provider import LEGACY_DRIVER_TYPE, PostgreSQLProvider

    class _Permissions:
        @staticmethod
        def require(*_args, **_kwargs):
            return None

    class _NativeConn:
        def __init__(self, dsn_str: str):
            self._dsn = dsn_str
            self.conn = None

        def connected(self):
            return self.conn is not None and not self.conn.closed

        def connect(self, **_kwargs):
            self.conn = psycopg.connect(self._dsn, autocommit=True)
            return True, None

        def transaction_status(self):
            return int(self.conn.info.transaction_status) if self.conn is not None else 0

        def execute_void(self, sql_text: str, **_kwargs):
            try:
                with Cursor(self.conn) as cur:
                    cur.execute(sql_text)
                return True, None
            except psycopg.Error as exc:
                return False, f'{exc}\nSQL state: {exc.sqlstate}' if exc.sqlstate else str(exc)

        def execute_dict(self, sql_text: str, parameters=None, **_kwargs):
            try:
                with Cursor(self.conn, row_factory=dict_row) as cur:
                    cur.execute(sql_text, parameters)
                    rows = list(cur.fetchall()) if cur.description else []
                return True, {'rows': rows}
            except psycopg.Error as exc:
                return False, f'{exc}\nSQL state: {exc.sqlstate}' if exc.sqlstate else str(exc)

    class _Manager:
        version = 180003
        server_type = 'pg'

        def __init__(self, dsn_str: str):
            self._dsn = dsn_str
            self.connections = {}
            self.ver = 180003
            self.sversion = 180003

        def connection(self, did=None, conn_id=None, **_kwargs):
            conn = self.connections[conn_id] = _NativeConn(self._dsn)
            return conn

        def release(self, conn_id=None, **_kwargs):
            existing = self.connections.pop(conn_id, None)
            if existing is not None and existing.conn is not None and not existing.conn.closed:
                existing.conn.close()

    class _Driver:
        def __init__(self, dsn_str: str):
            self._mgr = _Manager(dsn_str)

        def connection_manager(self, _sid):
            return self._mgr

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
            effective_permissions=frozenset({
                'network', 'secret_read', 'data_read', 'data_write', 'administer', 'execute',
            }),
            legacy_driver_type=LEGACY_DRIVER_TYPE,
        ),
        runtime_verification_state='verified',
    )
    return PostgreSQLProvider(ctx, _Permissions(), _Driver(dsn), catalog_source=object())


def _run_extra_tasks(host: str, port: int, password: str, standby_port: int) -> None:
    import psycopg
    dsn = f'host={host} port={port} user=postgres password={password} dbname=postgres sslmode=disable'
    provider = _make_provider(dsn)
    with psycopg.connect(dsn, autocommit=True) as conn:
        db_oid = int(conn.execute("SELECT oid FROM pg_database WHERE datname='postgres'").fetchone()[0])
        route = {'server_id': 1, 'database_id': db_oid}
        server_route = {'server_id': 1, 'database_id': None}

        def apply_task(kind: str, op: str, draft: dict | None = None, native: dict | None = None, use_server: bool = False, prov=provider):
            req = {
                'resource_kind': kind,
                'operation_id': op,
                'draft': draft or {},
                '_provider_route': server_route if use_server else route,
            }
            if native is not None:
                req['target_resource'] = {'extensions': {'postgresql': {'native': native}}}
            plan = prov.plan_admin_operation(req)
            res = prov.apply_admin_operation({'provider_payload': plan['provider_payload']})
            assert res.get('transaction_outcome') in {'committed', 'not_applicable'}, (kind, op, res)
            return res

        schema = 'sr_b6_' + secrets.token_hex(4)
        schema2 = schema + '_mv'
        role = 'sr_b6_role_' + secrets.token_hex(4)
        conn.execute(f'CREATE SCHEMA "{schema}"')
        conn.execute(f'CREATE SCHEMA "{schema2}"')
        conn.execute(f'CREATE ROLE "{role}"')
        try:
            # 1. large-object remaining tasks (create, inspect, alter, grant, revoke, drop)
            lo_res = apply_task('large-object', 'create', {
                'large_object_data_base64': base64.b64encode(b'batch6-lo').decode('ascii'),
            })
            lo_oid = int(lo_res['result']['rows'][0]['oid'])
            lo_nat = {'oid': lo_oid, 'name': str(lo_oid)}
            apply_task('large-object', 'inspect', {}, lo_nat)
            apply_task('large-object', 'alter', {'action': 'comment', 'value': 'batch6 comment'}, lo_nat)
            apply_task('large-object', 'grant', {'role': role, 'privileges': ['SELECT']}, lo_nat)
            apply_task('large-object', 'revoke', {'role': role, 'privileges': ['SELECT']}, lo_nat)
            apply_task('large-object', 'drop', {'confirmation': str(lo_oid)}, lo_nat)

            # 2. access-method (create, inspect, drop)
            am_name = 'sr_am_' + secrets.token_hex(4)
            apply_task('access-method', 'create', {'name': am_name, 'method_type': 'TABLE', 'handler': 'pg_catalog.heap_tableam_handler'})
            apply_task('access-method', 'inspect', {}, {'name': am_name})
            apply_task('access-method', 'drop', {'confirmation': am_name}, {'name': am_name})

            # 3. conversion (create, inspect, alter, drop)
            conv_name = 'sr_conv_' + secrets.token_hex(4)
            apply_task('conversion', 'create', {
                'schema': schema, 'name': conv_name,
                'source_encoding': 'UTF8', 'target_encoding': 'LATIN1',
                'function': 'pg_catalog.utf8_to_iso8859_1',
            })
            apply_task('conversion', 'inspect', {}, {'schema': schema, 'name': conv_name})
            apply_task('conversion', 'alter', {'action': 'rename', 'value': conv_name + '_r'}, {'schema': schema, 'name': conv_name})
            apply_task('conversion', 'drop', {'confirmation': conv_name + '_r'}, {'schema': schema, 'name': conv_name + '_r'})

            # 4. operator (create, inspect, alter, drop)
            conn.execute(f'CREATE FUNCTION "{schema}".op_eq(int4, int4) RETURNS bool LANGUAGE sql IMMUTABLE AS \'SELECT $1 = $2\'')
            op_sym = '==='
            apply_task('operator', 'create', {
                'schema': schema, 'name': op_sym,
                'left_type': 'integer', 'right_type': 'integer',
                'function': f'{schema}.op_eq',
            })
            op_nat = {'schema': schema, 'name': op_sym, 'left_type': 'integer', 'right_type': 'integer'}
            apply_task('operator', 'inspect', {}, op_nat)
            apply_task('operator', 'alter', {'action': 'comment', 'value': 'op comment'}, op_nat)
            apply_task('operator', 'drop', {'confirmation': op_sym}, op_nat)

            # 5. operator-family & operator-class (create, inspect, alter, drop)
            conn.execute(f'CREATE TYPE "{schema}".boxint AS (v int4)')
            conn.execute(f'CREATE FUNCTION "{schema}".box_lt("{schema}".boxint, "{schema}".boxint) RETURNS bool LANGUAGE sql IMMUTABLE AS \'SELECT ($1).v < ($2).v\'')
            conn.execute(f'CREATE FUNCTION "{schema}".box_cmp("{schema}".boxint, "{schema}".boxint) RETURNS int4 LANGUAGE sql IMMUTABLE AS \'SELECT btint4cmp(($1).v, ($2).v)\'')
            conn.execute(f'CREATE OPERATOR "{schema}".<<< (LEFTARG = "{schema}".boxint, RIGHTARG = "{schema}".boxint, FUNCTION = "{schema}".box_lt)')
            opf = 'sr_opf_' + secrets.token_hex(4)
            opc = 'sr_opc_' + secrets.token_hex(4)
            apply_task('operator-family', 'create', {'schema': schema, 'name': opf, 'index_method': 'btree'})
            opf_nat = {'schema': schema, 'name': opf, 'index_method': 'btree'}
            apply_task('operator-family', 'inspect', {}, opf_nat)
            apply_task('operator-family', 'alter', {'action': 'rename', 'value': opf + '_r'}, opf_nat)
            opf_nat_r = {'schema': schema, 'name': opf + '_r', 'index_method': 'btree'}
            apply_task('operator-class', 'create', {
                'schema': schema, 'name': opc, 'index_method': 'btree',
                'data_type': f'{schema}.boxint', 'family': f'{schema}.{opf}_r',
                'operators': [{'strategy': 1, 'operator': f'{schema}.<<<'}],
                'functions': [{'support': 1, 'function': f'{schema}.box_cmp', 'argument_types': [f'{schema}.boxint', f'{schema}.boxint']}],
            })
            opc_nat = {'schema': schema, 'name': opc, 'index_method': 'btree'}
            apply_task('operator-class', 'inspect', {}, opc_nat)
            apply_task('operator-class', 'alter', {'action': 'rename', 'value': opc + '_r'}, opc_nat)
            apply_task('operator-class', 'drop', {'confirmation': opc + '_r', 'cascade': True}, {'schema': schema, 'name': opc + '_r', 'index_method': 'btree'})
            apply_task('operator-family', 'drop', {'confirmation': opf + '_r', 'cascade': True}, opf_nat_r)

            # 6. aggregate (create, inspect, alter, drop)
            agg_name = 'sr_agg_' + secrets.token_hex(4)
            agg_def = f'CREATE AGGREGATE "{schema}"."{agg_name}" (int4) (SFUNC = int4pl, STYPE = int4, INITCOND = \'0\')'
            apply_task('aggregate', 'create', {'schema': schema, 'name': agg_name, 'definition': agg_def})
            agg_oid = int(conn.execute(
                'SELECT p.oid FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=%s AND p.proname=%s',
                (schema, agg_name),
            ).fetchone()[0])
            agg_nat = {'oid': agg_oid, 'schema': schema, 'name': agg_name, 'identity_arguments': 'integer'}
            apply_task('aggregate', 'inspect', {}, agg_nat)
            apply_task('aggregate', 'alter', {'action': 'comment', 'value': 'agg comment'}, agg_nat)
            apply_task('aggregate', 'drop', {'confirmation': agg_name}, agg_nat)

            # 7. transform (create, inspect, drop) using core internal support function
            apply_task('transform', 'create', {
                'data_type': f'{schema}.boxint',
                'language': 'sql',
                'from_sql': {'function': 'pg_catalog.text_starts_with_support', 'argument_types': ['internal']},
            })
            trf_nat = {'data_type': f'{schema}.boxint', 'language': 'sql'}
            apply_task('transform', 'inspect', {}, trf_nat)
            apply_task('transform', 'drop', {'confirmation': f'{schema}.boxint / sql'}, trf_nat)

            # 8. default-privileges (grant, inspect, revoke)
            dp_base = {
                'object_type': 'TABLES',
                'owner_mode': 'CURRENT_ROLE',
                'owner_kind': 'ROLE',
                'scope': 'SCHEMAS',
                'schemas': [{'schema': schema}],
            }
            apply_task('default-privileges', 'grant', {
                **dp_base,
                'privileges': [{'privilege': 'SELECT'}],
                'grantees': [{'role': role}],
            }, {})
            apply_task('default-privileges', 'inspect', dp_base, {})
            apply_task('default-privileges', 'revoke', {
                **dp_base,
                'privileges': [{'privilege': 'SELECT'}],
                'grantees': [{'role': role}],
            }, {})

            # 9. parameter-acl (grant, inspect, revoke)
            apply_task('parameter-acl', 'grant', {
                'parameter': 'work_mem',
                'privileges': [{'privilege': 'SET'}],
                'roles': [{'role': role}],
            }, {}, use_server=True)
            apply_task('parameter-acl', 'inspect', {'parameter': 'work_mem'}, {}, use_server=True)
            apply_task('parameter-acl', 'revoke', {
                'parameter': 'work_mem',
                'privileges': [{'privilege': 'SET'}],
                'roles': [{'role': role}],
            }, {}, use_server=True)

            # 10. extended-statistics (create, inspect, alter, drop)
            conn.execute(f'CREATE TABLE "{schema}".st_tbl (a int, b int)')
            st_name = 'sr_st_' + secrets.token_hex(4)
            apply_task('extended-statistics', 'create', {
                'schema': schema, 'name': st_name,
                'table_schema': schema, 'table': 'st_tbl',
                'elements': [{'kind': 'column', 'value': 'a'}, {'kind': 'column', 'value': 'b'}],
                'kinds': [{'kind': 'dependencies'}],
            }, {})
            st_oid = int(conn.execute(
                'SELECT s.oid FROM pg_statistic_ext s JOIN pg_namespace n ON n.oid=s.stxnamespace WHERE n.nspname=%s AND s.stxname=%s',
                (schema, st_name),
            ).fetchone()[0])
            st_nat = {'oid': st_oid, 'schema': schema, 'name': st_name}
            apply_task('extended-statistics', 'inspect', {}, st_nat)
            apply_task('extended-statistics', 'alter', {'target': 120, 'comment': 'stats comment'}, st_nat)
            apply_task('extended-statistics', 'drop', {'confirmation': st_name}, st_nat)

            # 11. foreign-server:import-foreign-schema (via postgres_fdw loopback)
            conn.execute('CREATE EXTENSION IF NOT EXISTS postgres_fdw')
            fs_name = 'sr_fs_' + secrets.token_hex(4)
            conn.execute(f'CREATE TABLE "{schema2}".remote_tbl (id int PRIMARY KEY, label text)')
            conn.execute(f"CREATE SERVER \"{fs_name}\" FOREIGN DATA WRAPPER postgres_fdw OPTIONS (host '127.0.0.1', port '5432', dbname 'postgres')")
            conn.execute(f"CREATE USER MAPPING FOR CURRENT_USER SERVER \"{fs_name}\" OPTIONS (password '{password}')")
            try:
                apply_task('foreign-server', 'import-foreign-schema', {
                    'remote_schema': schema2,
                    'local_schema': schema,
                    'table_filter_mode': 'limit_to',
                    'table_names': 'remote_tbl',
                }, {'name': fs_name})
            finally:
                conn.execute(f'DROP SERVER IF EXISTS "{fs_name}" CASCADE')

            # 12. index:attach-partition, partitioned-index:{attach-partition, reindex}
            conn.execute(f'CREATE TABLE "{schema}".pt (k int, v text) PARTITION BY RANGE (k)')
            conn.execute(f'CREATE TABLE "{schema}".pt_1 PARTITION OF "{schema}".pt FOR VALUES FROM (0) TO (100)')
            conn.execute(f'CREATE TABLE "{schema}".pt_2 PARTITION OF "{schema}".pt FOR VALUES FROM (100) TO (200)')
            conn.execute(f'CREATE INDEX pt_idx ON ONLY "{schema}".pt (k)')
            conn.execute(f'CREATE INDEX pt_1_idx ON "{schema}".pt_1 (k)')
            conn.execute(f'CREATE INDEX pt_2_idx ON "{schema}".pt_2 (k)')
            apply_task('index', 'attach-partition', {
                'child_schema': schema, 'child_index': 'pt_1_idx',
            }, {'schema': schema, 'name': 'pt_idx'})
            apply_task('partitioned-index', 'attach-partition', {
                'child_schema': schema, 'child_index': 'pt_2_idx',
            }, {'schema': schema, 'name': 'pt_idx'})
            apply_task('partitioned-index', 'reindex', {'concurrently': False}, {'schema': schema, 'name': 'pt_idx'})

            # 13. database:install-drop-namespace-guard & database:reindex-system
            scratch_db = 'sr_b6_db_' + secrets.token_hex(4)
            conn.execute(f'CREATE DATABASE "{scratch_db}"')
            try:
                scratch_oid = int(conn.execute('SELECT oid FROM pg_database WHERE datname=%s', (scratch_db,)).fetchone()[0])
                scratch_dsn = f'host={host} port={port} user=postgres password={password} dbname={scratch_db} sslmode=disable'
                scratch_prov = _make_provider(scratch_dsn)
                plan_g = scratch_prov.plan_admin_operation({
                    'resource_kind': 'database',
                    'operation_id': 'install-drop-namespace-guard',
                    'draft': {'confirmation': 'INSTALL DROP NAMESPACE GUARD'},
                    '_provider_route': {'server_id': 1, 'database_id': scratch_oid},
                    'target_resource': {'extensions': {'postgresql': {'native': {'oid': scratch_oid, 'name': scratch_db}}}},
                })
                res_g = scratch_prov.apply_admin_operation({'provider_payload': plan_g['provider_payload']})
                assert res_g.get('transaction_outcome') == 'committed'
                plan_rs = scratch_prov.plan_admin_operation({
                    'resource_kind': 'database',
                    'operation_id': 'reindex-system',
                    'draft': {'concurrently': False},
                    '_provider_route': {'server_id': 1, 'database_id': scratch_oid},
                    'target_resource': {'extensions': {'postgresql': {'native': {'oid': scratch_oid, 'name': scratch_db}}}},
                })
                res_rs = scratch_prov.apply_admin_operation({'provider_payload': plan_rs['provider_payload']})
                assert res_rs.get('transaction_outcome') == 'committed'
            finally:
                conn.execute(f'DROP DATABASE IF EXISTS "{scratch_db}" WITH (FORCE)')

            # 14. prepared-transaction:{inspect, resolve} & server:{inspect-prepared-transactions, resolve-prepared-transaction}
            gid1 = 'sr_b6_gid1_' + secrets.token_hex(4)
            gid2 = 'sr_b6_gid2_' + secrets.token_hex(4)
            with psycopg.connect(dsn, autocommit=False) as tx1:
                tx1.execute('SELECT 1')
                tx1.execute(f"PREPARE TRANSACTION '{gid1}'")
            with psycopg.connect(dsn, autocommit=False) as tx2:
                tx2.execute('SELECT 1')
                tx2.execute(f"PREPARE TRANSACTION '{gid2}'")
            apply_task('prepared-transaction', 'inspect', {}, {}, use_server=True)
            apply_task('server', 'inspect-prepared-transactions', {}, {}, use_server=True)
            apply_task('prepared-transaction', 'resolve', {
                'gid': gid1,
                'expected_database': 'postgres',
                'expected_owner': 'postgres',
                'coordinator_reference': 'batch6-coordinator-rollback',
                'decision': 'ROLLBACK',
                'confirmation': gid1,
            }, {'gid': gid1, 'name': gid1, 'database': 'postgres', 'owner': 'postgres'}, use_server=True)
            apply_task('server', 'resolve-prepared-transaction', {
                'gid': gid2,
                'expected_database': 'postgres',
                'expected_owner': 'postgres',
                'coordinator_reference': 'batch6-coordinator-commit',
                'decision': 'COMMIT',
                'confirmation': gid2,
            }, {}, use_server=True)

            # 15. server:{inspect-configuration, alter-system-set, alter-system-reset, alter-system-reset-all, checkpoint}
            apply_task('server', 'inspect-configuration', {'scope': 'settings'}, {}, use_server=True)
            apply_task('server', 'alter-system-set', {
                'parameter': 'log_min_duration_statement',
                'value_mode': 'VALUE',
                'value': '250ms',
                'reload_after': True,
            }, {}, use_server=True)
            apply_task('server', 'alter-system-reset', {
                'parameter': 'log_min_duration_statement',
                'reload_after': True,
                'confirmation': 'log_min_duration_statement',
            }, {}, use_server=True)
            apply_task('server', 'alter-system-reset-all', {
                'reload_after': True,
                'confirmation': 'RESET ALL',
            }, {}, use_server=True)
            apply_task('server', 'checkpoint', {}, {}, use_server=True)

            # 16. server:{wal-replay-pause, wal-replay-resume} on real 18.3 physical standby
            standby_dsn = f'host={host} port={standby_port} user=postgres password={password} dbname=postgres sslmode=disable'
            standby_prov = _make_provider(standby_dsn)
            apply_task('server', 'wal-replay-pause', {}, {}, use_server=True, prov=standby_prov)
            apply_task('server', 'wal-replay-resume', {}, {}, use_server=True, prov=standby_prov)

            # 17. partitioned-table:{create, alter, drop}, table:{create-partition, attach-partition}, text-search-template:alter
            from pgadmin.cdeadmin.providers.postgresql.tables import facts as tbl_facts
            from pgadmin.cdeadmin.providers.postgresql.partitions import partition_facts as part_facts
            pt_name = 'sr_pt_life_' + secrets.token_hex(4)
            apply_task('partitioned-table', 'create', {
                'schema': schema,
                'name': pt_name,
                'columns': [{'name': 'k', 'cltype': 'integer'}],
                'is_partitioned': True,
                'partition_type': 'range',
                'partition_keys': [{'key_type': 'column', 'pt_column': 'k'}],
            })
            pt_oid, pt_partkey = conn.execute(
                'SELECT c.oid::int, pg_get_partkeydef(c.oid) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relname=%s',
                (schema, pt_name),
            ).fetchone()
            pt_nat = {
                'catalog': 'pg_class',
                'oid': int(pt_oid),
                'name': pt_name,
                'schema': schema,
                'comment': None,
                'catalog_row': {
                    'relname': pt_name,
                    'relkind': 'p',
                    'relpersistence': 'p',
                    'reloptions': None,
                    'relrowsecurity': False,
                    'relforcerowsecurity': False,
                    'relreplident': 'd',
                    'owner_name': 'postgres',
                    'tablespace_name': None,
                    'access_method_name': None,
                    'relispartition': False,
                    'partition_bound_sql': None,
                    'partition_key_sql': pt_partkey,
                },
            }
            pt_nat['table_facts'] = tbl_facts(pt_nat)
            pt_nat['partition_facts'] = part_facts(pt_nat)
            apply_task('partitioned-table', 'alter', {'description': 'pt lifecycle desc'}, pt_nat)
            apply_task('table', 'create-partition', {
                'name': pt_name + '_p1',
                'schema': schema,
                'partition_value': 'FOR VALUES FROM (0) TO (10)',
            }, pt_nat)
            conn.execute(f'CREATE TABLE "{schema}"."{pt_name}_p2" (k integer)')
            apply_task('table', 'attach-partition', {
                'partition': f'{schema}.{pt_name}_p2',
                'partition_value': 'FOR VALUES FROM (10) TO (20)',
            }, pt_nat)
            apply_task('partitioned-table', 'drop', {'confirmation': pt_name, 'cascade': True}, pt_nat)

            tmpl_name = 'sr_tmpl_' + secrets.token_hex(4)
            conn.execute(f'CREATE TEXT SEARCH TEMPLATE "{schema}"."{tmpl_name}" (LEXIZE = dsimple_lexize)')
            apply_task('text-search-template', 'alter', {'description': 'tmpl comment'}, {'schema': schema, 'name': tmpl_name})
        finally:
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            conn.execute(f'DROP SCHEMA IF EXISTS "{schema2}" CASCADE')
            conn.execute(f'DROP OWNED BY "{role}"; DROP ROLE IF EXISTS "{role}"')


def main() -> None:
    import psycopg
    import pytest
    from pgadmin.cdeadmin import engine_contracts
    from pgadmin.cdeadmin.providers.postgresql.contracts import dialect_task_ids
    from pgadmin.cdeadmin.providers.postgresql.provider import PostgreSQLProvider
    from cdeadmin_postgresql_engine_contract_gate import metric_gate
    from tools.reference_engine_demos.generate_postgresql_contracts import generate
    from tools.reference_engine_demos.generate_postgresql_dialect_inventory import generate as gen_dialect_inv
    from tools.reference_engine_demos.generate_postgresql_metrics_inventory import generate as gen_metrics_inv

    donor_root = Path('/home/dcalford/Sandbox/donor_release_acquisition/postgresql/18.3')
    ref_source = donor_root / 'source'
    ref_archive = donor_root / 'source-archive/postgresql-18.3.tar.bz2'
    out_dir = Path('/home/dcalford/Sandbox/codex-work-area/cdeadmin-six-engine-implementation/postgresql-qualification')
    out_dir.mkdir(parents=True, exist_ok=True)

    tmp = Path('/home/dcalford/Sandbox/codex-work-area/cdeadmin-six-engine-implementation/.tmp-pg-batch6-' + secrets.token_hex(4))
    tmp.mkdir(parents=True, exist_ok=True)
    shared_dir = tmp / 'shared'
    shared_dir.mkdir(parents=True, exist_ok=True)
    shared_dir.chmod(0o777)
    standby_data = tmp / 'standby_pgdata'
    standby_data.mkdir(parents=True, exist_ok=True)
    standby_data.chmod(0o777)

    primary_name = 'sr-pg183-primary-' + secrets.token_hex(6)
    standby_name = 'sr-pg183-standby-' + secrets.token_hex(6)
    net_name = 'sr-pg183-net-' + secrets.token_hex(6)
    password = secrets.token_urlsafe(24)

    proofs_list: list[dict] = []
    orig_apply = PostgreSQLProvider.apply_admin_operation

    def _record_apply(self, plan):
        res = orig_apply(self, plan)
        payload = plan['provider_payload']
        if res.get('transaction_outcome') in {'committed', 'not_applicable'}:
            proofs_list.append({
                'task_id': payload['resource_kind'] + ':' + payload['operation_id'],
                **(
                    {'statement_sha256': hashlib.sha256(payload['statement'].encode('utf-8')).hexdigest()}
                    if payload['resource_kind'] == 'large-object'
                    else {'statement': payload['statement']}
                ),
                'read_only': payload['read_only'],
                'native_execution_returned': True,
                'transaction_outcome': res.get('transaction_outcome'),
                'release_status': res.get('release_status'),
            })
        return res

    PostgreSQLProvider.apply_admin_operation = _record_apply
    primary_started = False
    standby_started = False
    net_created = False
    try:
        subprocess.run([
            'docker', 'run', '-d', '--rm',
            '--name', primary_name,
            '--publish', '127.0.0.1::5432',
            '--publish', '127.0.0.1::5433',
            '-v', f'{shared_dir}:{shared_dir}',
            '--env', f'POSTGRES_PASSWORD={password}',
            'postgres:18.3',
            '-c', 'wal_level=logical',
            '-c', 'max_prepared_transactions=8',
            '-c', 'max_wal_senders=8',
            '-c', 'max_replication_slots=8',
            '-c', 'hot_standby=on',
        ], check=True, capture_output=True, timeout=120)
        primary_started = True
        primary_port = int(subprocess.run(
            ['docker', 'port', primary_name, '5432/tcp'],
            check=True, capture_output=True, text=True, timeout=15,
        ).stdout.strip().rsplit(':', 1)[1])
        standby_port = int(subprocess.run(
            ['docker', 'port', primary_name, '5433/tcp'],
            check=True, capture_output=True, text=True, timeout=15,
        ).stdout.strip().rsplit(':', 1)[1])
        _wait_pg_ready('127.0.0.1', primary_port, 'postgres', password)
        subprocess.run(
            ['docker', 'exec', '-u', 'postgres', primary_name, 'bash', '-lc',
             "mkdir -p /tmp/sr_ts && echo 'host replication all all scram-sha-256' >> \"$PGDATA/pg_hba.conf\" && psql -U postgres -c 'SELECT pg_reload_conf()'"],
            check=True, capture_output=True, timeout=15,
        )

        # 1. Generate dialect & metrics inventories on clean 18.3 primary + run metric_gate
        route = {
            'host': '127.0.0.1', 'port': primary_port,
            'user': 'postgres', 'database': 'postgres',
            'connection_params': {'sslmode': 'disable'},
        }
        with psycopg.connect(
            host='127.0.0.1', port=primary_port, user='postgres',
            dbname='postgres', password=password, autocommit=True,
        ) as inv_conn:
            di_doc = gen_dialect_inv(ref_source, inv_conn, ref_archive)
            mi_doc = gen_metrics_inv(ref_source, inv_conn)
        di_path = tmp / 'postgresql_dialect_inventory_18_3.json'
        mi_path = tmp / 'postgresql_metrics_inventory_18_3.json'
        di_path.write_text(json.dumps(di_doc, indent=2, ensure_ascii=False) + '\n')
        mi_path.write_text(json.dumps(mi_doc, indent=2, ensure_ascii=False) + '\n')

        metric_out = tmp / 'metrics_gate'
        metric_out.mkdir(parents=True, exist_ok=True)
        measured = metric_gate(route, password, mi_doc, mi_path, metric_out)
        assert measured['complete'] is True, measured
        with psycopg.connect(
            host='127.0.0.1', port=primary_port, user='postgres',
            dbname='postgres', password=password, autocommit=True,
        ) as clean_conn:
            clean_conn.execute('ALTER SYSTEM RESET primary_conninfo')
            clean_conn.execute('SELECT pg_reload_conf()')

        # 2. Bootstrap clean standby & run extra provider-native tasks first, then stop standby before tablespace tests
        sb_res = subprocess.run(
            ['docker', 'exec', '-u', 'postgres', '--env', f'PGPASSWORD={password}', primary_name, 'bash', '-c',
             "rm -rf /tmp/sr_standby && pg_basebackup -h 127.0.0.1 -p 5432 -U postgres -D /tmp/sr_standby -Fp -Xs -R && "
             "pg_ctl -D /tmp/sr_standby -o '-p 5433 -h 0.0.0.0 -c hot_standby=on -c max_prepared_transactions=8 -c max_wal_senders=8 -c max_replication_slots=8' -l /tmp/sr_standby.log start || "
             "(cat /tmp/sr_standby.log >&2; exit 1)"],
            capture_output=True, text=True, timeout=60,
        )
        if sb_res.returncode != 0:
            raise RuntimeError(f'Standby bootstrap failed: {sb_res.stdout}\n{sb_res.stderr}')
        _wait_pg_ready('127.0.0.1', standby_port, 'postgres', password)
        _run_extra_tasks('127.0.0.1', primary_port, password, standby_port)
        subprocess.run(
            ['docker', 'exec', '-u', 'postgres', primary_name, 'bash', '-c',
             'pg_ctl -D /tmp/sr_standby stop -m immediate && rm -rf /tmp/sr_standby /tmp/sr_standby.log'],
            check=True, capture_output=True, timeout=30,
        )

        # 3. Run test_ui_descriptor_operations_postgresql.py against 18.3 primary
        prev_env = os.environ.get('CDEADMIN_ROUNDTRIP_POSTGRESQL')
        os.environ['CDEADMIN_ROUNDTRIP_POSTGRESQL'] = json.dumps({
            'host': '127.0.0.1',
            'port': primary_port,
            'user': 'postgres',
            'password': password,
            'database': 'postgres',
            'server_file_dir': str(shared_dir),
            'tablespace_dir': '/tmp/sr_ts',
        })
        try:
            sys.modules.pop('test_ui_descriptor_operations_postgresql', None)
            rc = pytest.main(['-q', str(ROOT / 'tools/tests/test_ui_descriptor_operations_postgresql.py')])
            assert rc == 0, f'test_ui_descriptor_operations_postgresql exited with {rc}'
        finally:
            if prev_env is None:
                os.environ.pop('CDEADMIN_ROUNDTRIP_POSTGRESQL', None)
            else:
                os.environ['CDEADMIN_ROUNDTRIP_POSTGRESQL'] = prev_env

        expected = set(dialect_task_ids())
        seen = {'postgresql.' + r['task_id'].replace(':', '.') for r in proofs_list}
        missing = sorted(expected - seen)
        extra = sorted(seen - expected)
        print(f'EXPECTED={len(expected)} SEEN={len(seen)} MISSING={missing} EXTRA={extra}')
        assert not missing and not extra, (missing, extra)

        compiler_paths = [
            'web/pgadmin/cdeadmin/providers/postgresql/' + name
            for name in ('native_admin.py', 'large_objects.py', 'preserved_surface.py')
        ]
        source_sha256 = {name: _sha256_file(ROOT / name) for name in compiler_paths}
        summary_doc = {
            'complete': True,
            'failures': [],
            'reference_version': '18.3',
            'source_sha256': source_sha256,
            'native_admin_task_count': len(expected),
            'native_admin_task_proofs': proofs_list,
        }
        summary_path = out_dir / 'summary.json'
        metrics_receipt_path = out_dir / 'native-metrics-receipt.json'
        summary_path.write_text(json.dumps(summary_doc, indent=2) + '\n')
        shutil.copy2(metric_out / 'native-metrics-receipt.json', metrics_receipt_path)

        dialect_contract, metrics_contract = generate(
            di_path, mi_path, summary_path, metrics_receipt_path, ROOT,
        )
        pkg_dir = ROOT / 'web/pgadmin/cdeadmin/providers/postgresql'
        (pkg_dir / 'postgresql_dialect_18_3.json').write_text(
            json.dumps(dialect_contract, indent=2, ensure_ascii=False) + '\n'
        )
        (pkg_dir / 'postgresql_metrics_18_3.json').write_text(
            json.dumps(metrics_contract, indent=2, ensure_ascii=False) + '\n'
        )

        manifest_path = pkg_dir / 'provider_manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['provenance']['exact_engine_contracts'] = {
            'state': 'qualified',
            'reference_version': '18.3',
            'qualification_scope': (
                f'{len(expected)} generated native SQL compiler tasks; '
                f"{measured['family_count']} core statistics/diagnostic families and "
                f"{measured['native_observation_count']} native columns; "
                'preserved HTTP forms and full product/platform acceptance remain separate'
            ),
            'native_receipt_sha256': _sha256_file(summary_path),
            'metrics_receipt_sha256': _sha256_file(metrics_receipt_path),
        }
        manifest['provenance']['runtime_state'] = 'native_driver_and_scoped_surface_qualified'
        manifest['provenance']['object_experience_gate'] = 'qualified_18_3'
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')

        with engine_contracts._DESCRIPTOR_CACHE_LOCK:
            engine_contracts._DESCRIPTOR_CACHE.clear()
        descriptor = PostgreSQLProvider.engine_contract_descriptor()
        print('DESCRIPTOR STATE:', descriptor)
        assert descriptor['state'] == 'passed', descriptor
    finally:
        PostgreSQLProvider.apply_admin_operation = orig_apply
        if standby_started:
            subprocess.run(['docker', 'stop', standby_name], capture_output=True, timeout=45)
        if primary_started:
            subprocess.run(['docker', 'stop', primary_name], capture_output=True, timeout=45)
        if net_created:
            subprocess.run(['docker', 'network', 'rm', net_name], capture_output=True, timeout=30)
        # Ensure container-created files inside standby_data/shared_dir are removable
        subprocess.run(
            ['docker', 'run', '--rm', '-v', f'{tmp}:/cleanup', 'postgres:18.3', 'rm', '-rf', '/cleanup/standby_pgdata', '/cleanup/shared'],
            capture_output=True, timeout=30,
        )
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()

"""Unified DuckDB Native Operations Hub (DU-AUD-18, DU-AUD-19, DU-AUD-20, DU-AUD-21).

Provides durable review/apply, provenance, and private artifact state for:
- DU-AUD-18: Native Shell & Client Directive Supervisor (``shell_provenance``, ``shell_execute``)
- DU-AUD-19: Single SQL Stream Database Dump & Reviewed Reload (``dump_export``, ``dump_list``, ``dump_read``, ``dump_reload_review``, ``dump_reload_apply``)
- DU-AUD-20: Operational Physical Continuity & WAL Recovery Drills (``continuity_inspect``, ``continuity_snapshot``, ``continuity_wal_drill``, ``continuity_restore_new``, ``continuity_cutover_review``, ``continuity_cutover_apply``)
- DU-AUD-21: Runtime & Storage Lifecycle Management (``storage_inspect``, ``storage_reopen_probe``, ``storage_migrate_review``, ``storage_migrate_apply``)
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import time
import uuid

from ..operations.fileio import private_directory
from ..operations.store import JsonOperationStore
from ..providers.duckdb import (
    physical_continuity,
    shell_tool,
    sql_dump,
    storage_lifecycle,
)
from ..providers.duckdb.provider import DuckDBPilotProvider
from .firebird_schema_plan import digest


DUCKDB_OPS_ACTIONS = frozenset({
    # DU-AUD-18 Shell & Directives
    'duckdb_ops_shell_provenance',
    'duckdb_ops_shell_execute',
    # DU-AUD-19 Single SQL Stream Dump & Reload
    'duckdb_ops_dump_export',
    'duckdb_ops_dump_list',
    'duckdb_ops_dump_read',
    'duckdb_ops_dump_reload_review',
    'duckdb_ops_dump_reload_apply',
    # DU-AUD-20 Physical Continuity & WAL Recovery Drills
    'duckdb_ops_continuity_inspect',
    'duckdb_ops_continuity_snapshot',
    'duckdb_ops_continuity_wal_drill',
    'duckdb_ops_continuity_restore_new',
    'duckdb_ops_continuity_cutover_review',
    'duckdb_ops_continuity_cutover_apply',
    # DU-AUD-21 Storage Lifecycle Management
    'duckdb_ops_storage_inspect',
    'duckdb_ops_storage_reopen_probe',
    'duckdb_ops_storage_migrate_review',
    'duckdb_ops_storage_migrate_apply',
})


def _resolve_duckdb_workspace(service, server, target_id: str):
    if not isinstance(target_id, str) or not target_id:
        raise ValueError('Select an exact registered DuckDB database target')
    context, endpoint, _root = service.endpoint_service.workspace(server, database_target_id=target_id)
    provider = service.endpoint_service.provider_registry.resolve(context).instance
    if not isinstance(provider, DuckDBPilotProvider) or context.profile_id != 'duckdb-native':
        raise ValueError('Select a native DuckDB endpoint')
    store_root = getattr(service.operation_bus, 'store', None)
    if not isinstance(store_root, JsonOperationStore):
        raise ValueError('DuckDB native operations require durable receipt storage')
    hub_store = JsonOperationStore(str(store_root.path) + '.duckdb-operations-hub.json')
    artifacts_dir = Path(str(store_root.path) + '.duckdb-ops-artifacts')
    artifacts_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_directory(artifacts_dir)
    owner = service._principal_id(server)
    binding = digest({'endpoint_id': str(context.endpoint_id), 'target_id': target_id, 'owner': owner})
    return context, endpoint['route'], provider, hub_store, artifacts_dir, owner, binding


def _save_review(store: JsonOperationStore, bucket: str, owner: str, binding: str, public_payload: dict, *, private_payload: dict | None = None) -> dict:
    review_id = str(uuid.uuid4())
    now = time.time()
    rec = {
        'review_id': review_id,
        'state': 'reviewed',
        'owner': owner,
        'binding': binding,
        'created_at': now,
        'expires_at': now + 600,
        'payload': deepcopy(public_payload),
    }
    rec['review_digest'] = digest({'review_id': review_id, 'binding': binding, 'payload': public_payload})
    stored = deepcopy(rec)
    if private_payload:
        stored['_private'] = deepcopy(private_payload)

    def _mut(state):
        state.setdefault(bucket, {})[review_id] = stored

    store.change(_mut)
    return rec


def _claim_and_run_review(store: JsonOperationStore, bucket: str, owner: str, binding: str, request: dict, runner) -> dict:
    review_id = request.get('review_id')
    review_digest = request.get('review_digest')
    if not isinstance(review_id, str) or not isinstance(review_digest, str) or request.get('confirmed') is not True:
        raise ValueError('Confirm the exact review_id and review_digest before execution')

    claimed = {}

    def _claim(state):
        rec = state.get(bucket, {}).get(review_id)
        if rec is None or rec['owner'] != owner or rec['binding'] != binding:
            raise ValueError('Operation review is unavailable for this owner and database target')
        if rec['review_digest'] != review_digest:
            raise ValueError('Operation review_digest does not match')
        if rec['state'] != 'reviewed':
            claimed['existing'] = {k: deepcopy(v) for k, v in rec.items() if k != '_private'}
            claimed['existing']['replay_refused'] = True
            return
        if time.time() > rec['expires_at']:
            raise ValueError('Operation review expired; create a fresh review')
        rec['state'] = 'unknown_outcome'
        rec['dispatched_at'] = time.time()
        claimed['record'] = deepcopy(rec)

    store.change(_claim)
    if 'existing' in claimed:
        return claimed['existing']

    rec = claimed['record']
    try:
        outcome = runner(rec['payload'], rec.get('_private') or {})
        final_state = outcome.get('state', 'succeeded')
    except Exception as exc:
        outcome = {'state': 'failed', 'error_type': type(exc).__name__, 'error': str(exc)[:400]}
        final_state = 'failed'

    public_result = {}

    def _finish(state):
        stored = state[bucket][review_id]
        stored.pop('_private', None)
        stored['state'] = final_state
        stored['outcome'] = deepcopy(outcome)
        stored['finished_at'] = time.time()
        public_result.update({k: deepcopy(v) for k, v in stored.items() if k != '_private'})

    store.change(_finish)
    return public_result


def handle_operation(service, server, operation: str, request: dict, *, host_authorized: bool = False) -> dict:
    if not isinstance(request, dict):
        raise ValueError('Invalid DuckDB operation request')
    target_id = request.get('database_target_id')
    clean_req = {k: v for k, v in request.items() if k != 'database_target_id'}
    context, route, provider, hub_store, artifacts_dir, owner, binding = _resolve_duckdb_workspace(service, server, target_id)

    # DU-AUD-18: Shell & Directives
    if operation == 'shell_provenance':
        provider._require('execute')
        return shell_tool.inspect_shell_provenance()

    if operation == 'shell_execute':
        provider._require('execute')
        if not clean_req.get('read_only', True):
            provider._require('administer')
        if clean_req.get('use_cli_process') is True:
            if not host_authorized:
                raise ValueError('External CLI process execution requires host administrator authorization')
            return shell_tool.execute_cli_batch(
                route,
                str(clean_req.get('script') or ''),
                read_only=bool(clean_req.get('read_only', True)),
                timeout_seconds=float(clean_req.get('timeout_seconds', 15.0)),
            )
        req_inner = {k: v for k, v in clean_req.items() if k != 'use_cli_process'}
        return shell_tool.execute_directive_script(route, req_inner)

    # DU-AUD-19: Single SQL Stream Dump & Reload
    if operation == 'dump_export':
        provider._require('data_read', 'resource')
        dump_id = str(uuid.uuid4())
        art_file = artifacts_dir / f'{dump_id}.sql'
        exported = sql_dump.export_sql_dump(route, clean_req, artifact_path=art_file)
        meta = {
            'dump_id': dump_id,
            'owner': owner,
            'binding': binding,
            'created_at': time.time(),
            **{k: v for k, v in exported.items() if k != 'artifact_path'},
        }

        def _rec_dump(state):
            state.setdefault('sql_dumps', {})[dump_id] = meta

        hub_store.change(_rec_dump)
        return meta

    if operation == 'dump_list':
        provider._require('data_read', 'resource')
        state = hub_store.read()
        dumps = sorted(
            (d for d in state.get('sql_dumps', {}).values() if d['owner'] == owner and d['binding'] == binding),
            key=lambda d: d['created_at'],
            reverse=True,
        )
        return {'dumps': dumps}

    if operation == 'dump_read':
        provider._require('data_read', 'resource')
        dump_id = str(clean_req.get('dump_id') or '')
        state = hub_store.read()
        rec = state.get('sql_dumps', {}).get(dump_id)
        if rec is None or rec['owner'] != owner or rec['binding'] != binding:
            raise ValueError('Requested SQL dump artifact is unavailable')
        art_file = artifacts_dir / f'{dump_id}.sql'
        if not art_file.is_file():
            raise ValueError('SQL dump file payload is missing')
        return {**rec, 'sql_text': art_file.read_text(encoding='utf-8')}

    if operation == 'dump_reload_review':
        provider._require('administer', 'resource')
        provider._require('data_write', 'resource')
        sql_text = clean_req.get('sql_text')
        dump_id = clean_req.get('dump_id')
        if dump_id and not sql_text:
            art_file = artifacts_dir / f'{dump_id}.sql'
            if not art_file.is_file():
                raise ValueError('Referenced dump_id file does not exist')
            sql_text = art_file.read_text(encoding='utf-8')
        if not isinstance(sql_text, str) or not sql_text.strip():
            raise ValueError('Provide sql_text or dump_id for SQL dump reload review')
        import duckdb
        stmts = duckdb.extract_statements(sql_text)
        pub = {
            'operation': 'dump_reload',
            'statement_count': len(stmts),
            'sql_sha256': digest(sql_text),
            'target_path': clean_req.get('target_path'),
            'create_if_missing': bool(clean_req.get('create_if_missing', False)),
            'storage_version': clean_req.get('storage_version'),
        }
        return _save_review(hub_store, 'dump_reloads', owner, binding, pub, private_payload={'sql_text': sql_text})

    if operation == 'dump_reload_apply':
        provider._require('administer', 'resource')
        provider._require('data_write', 'resource')

        def _run_reload(pub, priv):
            target_route = deepcopy(route)
            if pub.get('target_path'):
                from ..providers.embedded_route import resolve_contained_path
                target_route['database'] = resolve_contained_path(route['filesystem_root'], pub['target_path'], must_exist=False)
            res = sql_dump.reload_sql_dump(
                target_route,
                priv['sql_text'],
                create_if_missing=pub['create_if_missing'],
                storage_version=pub.get('storage_version'),
            )
            service.resource_service.invalidate(context)
            return res

        return _claim_and_run_review(hub_store, 'dump_reloads', owner, binding, clean_req, _run_reload)

    # DU-AUD-20: Physical Continuity & WAL Recovery Drills
    if operation == 'continuity_inspect':
        provider._require('execute')
        return physical_continuity.inspect_physical_continuity(route)

    if operation == 'continuity_snapshot':
        provider._require('administer', 'resource')
        return physical_continuity.quiesce_and_snapshot(route, clean_req)

    if operation == 'continuity_wal_drill':
        provider._require('administer', 'resource')
        return physical_continuity.run_wal_recovery_drill(route, clean_req)

    if operation == 'continuity_restore_new':
        provider._require('administer', 'resource')
        return physical_continuity.restore_to_new_target(route, clean_req)

    if operation == 'continuity_cutover_review':
        provider._require('administer', 'resource')
        inspected = physical_continuity.inspect_physical_continuity(route)
        if not inspected.get('physical_continuity_supported'):
            raise ValueError(inspected.get('reason') or 'Cutover unsupported for this target')
        pub = {
            'operation': 'continuity_cutover',
            'staged_path': clean_req.get('staged_path'),
            'backup_previous_path': clean_req.get('backup_previous_path'),
            'expected_active_inode': inspected['inode'],
            'encryption_cipher': clean_req.get('encryption_cipher'),
            'key_supplied': bool(clean_req.get('encryption_key')),
        }
        priv = {'encryption_key': clean_req.get('encryption_key')} if clean_req.get('encryption_key') else None
        return _save_review(hub_store, 'cutovers', owner, binding, pub, private_payload=priv)

    if operation == 'continuity_cutover_apply':
        provider._require('administer', 'resource')

        def _run_cutover(pub, priv):
            req_cut = {
                'staged_path': pub['staged_path'],
                'backup_previous_path': pub['backup_previous_path'],
                'expected_active_inode': pub['expected_active_inode'],
                'confirmed_cutover': True,
            }
            if priv.get('encryption_key'):
                req_cut['encryption_key'] = priv['encryption_key']
            if pub.get('encryption_cipher'):
                req_cut['encryption_cipher'] = pub['encryption_cipher']
            res = physical_continuity.execute_reviewed_cutover(route, req_cut)
            service.resource_service.invalidate(context)
            return res

        return _claim_and_run_review(hub_store, 'cutovers', owner, binding, clean_req, _run_cutover)

    # DU-AUD-21: Storage Lifecycle Management
    if operation == 'storage_inspect':
        provider._require('execute')
        from ..providers.embedded_route import contained_database, resolve_contained_path
        target_p = (
            resolve_contained_path(route['filesystem_root'], clean_req['path'], must_exist=True)
            if clean_req.get('path') and route.get('filesystem_root')
            else contained_database(route)
        )
        if target_p == ':memory:':
            return {'is_memory': True, 'compatible_with_runtime_1_5_2': True}
        return storage_lifecycle.inspect_storage_header(target_p)

    if operation == 'storage_reopen_probe':
        provider._require('execute')
        from ..providers.embedded_route import contained_database, resolve_contained_path
        target_p = (
            resolve_contained_path(route['filesystem_root'], clean_req['path'], must_exist=True)
            if clean_req.get('path') and route.get('filesystem_root')
            else contained_database(route)
        )
        return storage_lifecycle.probe_reopen_compatibility(
            target_p,
            encryption_key=clean_req.get('encryption_key'),
            encryption_cipher=clean_req.get('encryption_cipher'),
            storage_compatibility_version=clean_req.get('storage_compatibility_version'),
        )

    if operation == 'storage_migrate_review':
        provider._require('administer', 'resource')
        pub = {
            'operation': 'storage_migrate',
            'target_path': clean_req.get('target_path'),
            'target_storage_version': clean_req.get('target_storage_version', 'v1.5.2'),
            'block_size': clean_req.get('block_size'),
            'row_group_size': clean_req.get('row_group_size'),
            'source_encryption_cipher': clean_req.get('source_encryption_cipher'),
            'target_encryption_cipher': clean_req.get('target_encryption_cipher'),
            'source_key_supplied': bool(clean_req.get('source_encryption_key')),
            'target_key_supplied': bool(clean_req.get('target_encryption_key')),
        }
        priv = {
            k: clean_req[k]
            for k in ('source_encryption_key', 'target_encryption_key')
            if clean_req.get(k)
        }
        return _save_review(hub_store, 'storage_migrations', owner, binding, pub, private_payload=priv)

    if operation == 'storage_migrate_apply':
        provider._require('administer', 'resource')

        def _run_mig(pub, priv):
            req_m = {
                k: v for k, v in {
                    'target_path': pub['target_path'],
                    'target_storage_version': pub['target_storage_version'],
                    'block_size': pub.get('block_size'),
                    'row_group_size': pub.get('row_group_size'),
                    'source_encryption_cipher': pub.get('source_encryption_cipher'),
                    'target_encryption_cipher': pub.get('target_encryption_cipher'),
                    **priv,
                }.items()
                if v is not None
            }
            return storage_lifecycle.migrate_storage_profile(route, req_m)

        return _claim_and_run_review(hub_store, 'storage_migrations', owner, binding, clean_req, _run_mig)

    raise ValueError(f'Unknown DuckDB operation: {operation}')

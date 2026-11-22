"""Unified SQLite Native Operations Hub (SQ-AUD-09, SQ-AUD-10, SQ-AUD-11, SQ-AUD-12, SQ-AUD-13, SQ-AUD-15).

Provides durable job, review/apply, provenance, and artifact state for:
- SQ-AUD-09: Resumable Bulk Update & Resumable Vacuum (`ext/rbu`)
- SQ-AUD-10: Expert Index Advisor (`ext/expert`, preview-only)
- SQ-AUD-11: Incremental Integrity Check (`ext/intck`)
- SQ-AUD-12: Incremental Large-BLOB Transfer (`sqlite3_blob_*` / `Connection.blobopen`)
- SQ-AUD-13: Declared External Shell & Matching CLI Qualification (`sqlite-shell`)
- SQ-AUD-15: Database-Wide Native SQL Script Exchange (`.dump` + reviewed import)
"""
from __future__ import annotations

import base64
from contextlib import closing
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import time
import uuid

from flask import current_app, has_app_context

from ..operations.fileio import private_directory
from ..operations.store import JsonOperationStore
from ..providers.sqlite import (
    blob_stream,
    expert as sqlite_expert,
    intck as sqlite_intck,
    rbu as sqlite_rbu,
    shell_tool,
    sql_dump,
)
from ..providers.sqlite.provider import SQLiteProvider
from .firebird_schema_plan import digest

SQLITE_OPS_ACTIONS = frozenset({
    # SQ-AUD-09 RBU
    'sqlite_ops_rbu_catalog',
    'sqlite_ops_rbu_open_update',
    'sqlite_ops_rbu_open_vacuum',
    'sqlite_ops_rbu_step',
    'sqlite_ops_rbu_pause',
    'sqlite_ops_rbu_resume',
    'sqlite_ops_rbu_abort',
    'sqlite_ops_rbu_status',
    'sqlite_ops_rbu_list',
    # SQ-AUD-10 Expert Index Advisor
    'sqlite_ops_expert_status',
    'sqlite_ops_expert_analyze',
    # SQ-AUD-11 Incremental Integrity Check
    'sqlite_ops_intck_status',
    'sqlite_ops_intck_open',
    'sqlite_ops_intck_step',
    'sqlite_ops_intck_pause',
    'sqlite_ops_intck_resume',
    'sqlite_ops_intck_close',
    # SQ-AUD-12 Incremental Large-BLOB Transfer
    'sqlite_ops_blob_inspect',
    'sqlite_ops_blob_read_chunk',
    'sqlite_ops_blob_allocate_review',
    'sqlite_ops_blob_allocate_apply',
    'sqlite_ops_blob_write_review',
    'sqlite_ops_blob_write_apply',
    # SQ-AUD-13 Declared External Shell & CLI
    'sqlite_ops_shell_provenance',
    'sqlite_ops_shell_inspect',
    # SQ-AUD-15 Database-Wide Native SQL Script Exchange
    'sqlite_ops_dump_export',
    'sqlite_ops_dump_list',
    'sqlite_ops_dump_read',
    'sqlite_ops_dump_import_review',
    'sqlite_ops_dump_import_apply',
})


def _cfg(name: str, fallback: str = '') -> str:
    if has_app_context():
        val = current_app.config.get(name)
        if val:
            return str(val)
    return os.environ.get(name) or fallback


def _resolve_sqlite_workspace(service, server, target_id: str):
    if not isinstance(target_id, str) or not target_id:
        raise ValueError('Select an exact registered SQLite database target')
    context, endpoint, _root = service.endpoint_service.workspace(server, database_target_id=target_id)
    provider = service.endpoint_service.provider_registry.resolve(context).instance
    if not isinstance(provider, SQLiteProvider) or context.profile_id != 'sqlite-native':
        raise ValueError('Select a native SQLite endpoint')
    store_root = getattr(service.operation_bus, 'store', None)
    if not isinstance(store_root, JsonOperationStore):
        raise ValueError('SQLite native operations require durable receipt storage')
    hub_store = JsonOperationStore(str(store_root.path) + '.sqlite-operations-hub.json')
    artifacts_dir = Path(str(store_root.path) + '.sqlite-ops-artifacts')
    artifacts_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_directory(artifacts_dir)
    owner = service._principal_id(server)
    binding = digest({'endpoint_id': str(context.endpoint_id), 'target_id': target_id, 'owner': owner})
    return context, endpoint['route'], provider, hub_store, artifacts_dir, owner, binding


def _save_review(store: JsonOperationStore, bucket: str, owner: str, binding: str, payload: dict) -> dict:
    review_id = str(uuid.uuid4())
    now = time.time()
    rec = {
        'review_id': review_id,
        'state': 'reviewed',
        'owner': owner,
        'binding': binding,
        'created_at': now,
        'expires_at': now + 600,
        'payload': deepcopy(payload),
    }
    rec['review_digest'] = digest({'review_id': review_id, 'binding': binding, 'payload': payload})

    def _mut(state):
        state.setdefault(bucket, {})[review_id] = rec

    store.change(_mut)
    return {'review_id': review_id, 'review_digest': rec['review_digest'], 'state': 'reviewed', 'payload': payload}


def _claim_review(store: JsonOperationStore, bucket: str, owner: str, binding: str, request: dict) -> dict:
    review_id = request.get('review_id')
    review_digest = request.get('review_digest')
    if request.get('confirmed') is not True or not isinstance(review_id, str) or not isinstance(review_digest, str):
        raise ValueError('Confirm the exact review_id and review_digest before applying')
    claimed = {}

    def _mut(state):
        rec = state.get(bucket, {}).get(review_id)
        if rec is None or rec.get('owner') != owner or rec.get('binding') != binding:
            raise ValueError('Review receipt belongs to another owner or target')
        if rec.get('review_digest') != review_digest:
            raise ValueError('Review digest mismatch')
        if rec.get('state') != 'reviewed':
            raise ValueError(f'Review {review_id} was already consumed (state={rec.get("state")})')
        if rec.get('expires_at', 0) < time.time():
            raise ValueError('Review expired; create a fresh review')
        rec['state'] = 'dispatched'
        claimed['record'] = deepcopy(rec)

    store.change(_mut)
    return claimed['record']


def _finish_review(store: JsonOperationStore, bucket: str, review_id: str, final_state: str, outcome: dict) -> None:
    def _mut(state):
        rec = state.get(bucket, {}).get(review_id)
        if rec is not None:
            rec['state'] = final_state
            rec['outcome'] = deepcopy(outcome)
            rec['completed_at'] = time.time()

    store.change(_mut)


def _decode_bytes_input(request: dict) -> bytes:
    enc = request.get('encoding', 'base64')
    raw_str = request.get('data', '')
    if not isinstance(raw_str, str):
        raise ValueError('Chunk data must be a base64 or hex string')
    try:
        return base64.b64decode(raw_str, validate=True) if enc == 'base64' else bytes.fromhex(raw_str)
    except Exception as exc:
        raise ValueError(f'Invalid {enc} chunk data') from exc


def dispatch_sqlite_operation(service, server, operation: str, request: dict, *, host_authorized: bool = True) -> dict:
    if not isinstance(request, dict):
        raise ValueError('SQLite operation request must be an object')
    target_id = request.get('database_target_id')
    context, route, provider, hub_store, artifacts_dir, owner, binding = _resolve_sqlite_workspace(service, server, target_id)

    # --- SQ-AUD-09: Native RBU (Resumable Bulk Update & Vacuum) ---
    if operation.startswith('rbu_'):
        provider._require('administer', 'resource')
        rbu_lib = _cfg('CDEADMIN_SQLITE_RBU_LIBRARY') or sqlite_rbu.installed_library()
        if operation == 'rbu_catalog':
            try:
                lib_info = sqlite_rbu.verify_library(rbu_lib)
                avail = {'available': True, 'provenance': lib_info}
            except Exception as exc:
                avail = {'available': False, 'reason': str(exc)}
            jobs = [
                v for v in hub_store.read().get('rbu_jobs', {}).values()
                if v.get('owner') == owner and v.get('binding') == binding
            ]
            jobs.sort(key=lambda j: j.get('created_at', 0), reverse=True)
            return {
                'runtime': avail,
                'jobs': jobs[:25],
                'limitations': [
                    'RBU updates do not fire triggers, enforce CHECK constraints, or check foreign keys during bulk apply.',
                    'Stage 1 accumulates changes in an *-oal file invisible to concurrent readers; Stage 2 checkpoints *-wal into the main file.',
                ],
            }

        if operation == 'rbu_list':
            jobs = [
                v for v in hub_store.read().get('rbu_jobs', {}).values()
                if v.get('owner') == owner and v.get('binding') == binding
            ]
            jobs.sort(key=lambda j: j.get('created_at', 0), reverse=True)
            return {'jobs': jobs[:50]}

        if operation == 'rbu_status':
            jid = request.get('job_id')
            job = hub_store.read().get('rbu_jobs', {}).get(jid)
            if job is None or job.get('owner') != owner or job.get('binding') != binding:
                raise ValueError('RBU job not found for this target')
            return job

        if operation in {'rbu_open_update', 'rbu_open_vacuum'}:
            lib_info = sqlite_rbu.verify_library(rbu_lib)
            target_path = sqlite_rbu.resolve_contained_target(route)
            job_id = str(uuid.uuid4())
            job_dir = artifacts_dir / 'rbu' / job_id
            job_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            private_directory(job_dir)
            state_path = job_dir / 'rbu_state.sqlite'
            temp_limit = int(request.get('temp_size_limit') or 0)
            if temp_limit < 0:
                raise ValueError('temp_size_limit must be >= 0')

            job = {
                'job_id': job_id,
                'owner': owner,
                'binding': binding,
                'mode': 'update' if operation == 'rbu_open_update' else 'vacuum',
                'state': 'open',
                'target_path': str(target_path),
                'target_identity': sqlite_rbu.file_identity(target_path),
                'state_path': str(state_path),
                'state_identity': None,
                'temp_size_limit': temp_limit,
                'total_steps': 0,
                'rbu_state': 'OPENED',
                'stage1_permyriad': 0,
                'stage2_permyriad': 0,
                'key_value_operations': 0,
                'created_at': time.time(),
                'provenance': lib_info,
            }
            if operation == 'rbu_open_update':
                pkg = sqlite_rbu.build_rbu_package(target_path, job_dir / 'rbu_package.sqlite', request.get('tables') or [])
                job.update(
                    rbu_path=pkg['rbu_path'],
                    rbu_sha256=pkg['rbu_sha256'],
                    rbu_identity=pkg['rbu_identity'],
                    package_operations=pkg['total_operations'],
                    tables=pkg['tables'],
                )

            def _save_job(st):
                st.setdefault('rbu_jobs', {})[job_id] = job

            hub_store.change(_save_job)
            return job

        if operation in {'rbu_step', 'rbu_resume'}:
            jid = request.get('job_id')
            job = deepcopy(hub_store.read().get('rbu_jobs', {}).get(jid) or {})
            if not job or job.get('owner') != owner or job.get('binding') != binding:
                raise ValueError('RBU job not found for this target')
            if job['state'] in {'completed', 'aborted', 'failed'}:
                raise ValueError(f'RBU job is already terminal ({job["state"]})')
            if operation == 'rbu_step' and job['state'] == 'paused':
                raise ValueError('RBU job is paused; invoke rbu_resume to verify saved state and continue stepping')
            lib_info = sqlite_rbu.verify_library(rbu_lib)
            budget = int(request.get('step_budget') or 50)
            reply, proc_rec = sqlite_rbu.step_rbu_job(lib_info, job, step_budget=budget)
            if proc_rec['return_code'] != 0 or not reply.get('completed'):
                err_msg = reply.get('error_message') or 'RBU step failed'

                def _fail(st):
                    st['rbu_jobs'][jid].update(state='failed', error_message=err_msg, updated_at=time.time())

                hub_store.change(_fail)
                raise ValueError(err_msg)

            state_file = Path(job['state_path'])
            new_state_id = sqlite_rbu.file_identity(state_file) if state_file.is_file() else None
            new_target_id = sqlite_rbu.file_identity(Path(job['target_path']))
            new_status = 'completed' if reply['done'] else 'active'

            def _upd(st):
                cur = st['rbu_jobs'][jid]
                cur.update(
                    state=new_status,
                    total_steps=int(cur.get('total_steps', 0)) + int(reply['steps_executed']),
                    last_batch_steps=reply['steps_executed'],
                    rbu_state=reply['rbu_state'],
                    stage1_permyriad=reply['stage1_permyriad'],
                    stage2_permyriad=reply['stage2_permyriad'],
                    key_value_operations=reply['key_value_operations'],
                    temp_bytes=reply['temp_bytes'],
                    savestate_rc=reply['savestate_rc'],
                    close_rc=reply['close_rc'],
                    state_identity=new_state_id,
                    target_identity=new_target_id,
                    last_process_receipt=proc_rec,
                    updated_at=time.time(),
                )

            hub_store.change(_upd)
            if reply['done']:
                try:
                    service.resource_service.invalidate(context)
                except Exception:
                    pass
            return hub_store.read()['rbu_jobs'][jid]

        if operation == 'rbu_pause':
            jid = request.get('job_id')
            updated = {}

            def _pause(st):
                cur = st.get('rbu_jobs', {}).get(jid)
                if cur is None or cur.get('owner') != owner or cur.get('binding') != binding:
                    raise ValueError('RBU job not found for this target')
                if cur['state'] not in {'open', 'active', 'paused'}:
                    raise ValueError(f'Cannot pause RBU job in state {cur["state"]}')
                cur['state'] = 'paused'
                cur['paused_at'] = time.time()
                updated['job'] = deepcopy(cur)

            hub_store.change(_pause)
            return updated['job']

        if operation == 'rbu_abort':
            jid = request.get('job_id')
            aborted = {}

            def _abort(st):
                cur = st.get('rbu_jobs', {}).get(jid)
                if cur is None or cur.get('owner') != owner or cur.get('binding') != binding:
                    raise ValueError('RBU job not found for this target')
                if cur['state'] == 'completed':
                    raise ValueError('Completed RBU job cannot be aborted')
                for p_str in (cur.get('state_path'), cur.get('rbu_path'), str(cur.get('target_path', '')) + '-oal'):
                    if p_str:
                        for sfx in ('', '-wal', '-shm', '-journal'):
                            try:
                                Path(p_str + sfx).unlink(missing_ok=True)
                            except OSError:
                                pass
                cur['state'] = 'aborted'
                cur['aborted_at'] = time.time()
                aborted['job'] = deepcopy(cur)

            hub_store.change(_abort)
            return aborted['job']

    # --- SQ-AUD-10: Native Expert Index Advisor ---
    if operation.startswith('expert_'):
        provider._require('data_read', 'resource')
        exp_lib = _cfg('CDEADMIN_SQLITE_EXPERT_LIBRARY') or sqlite_expert.installed_library()
        if operation == 'expert_status':
            try:
                lib_info = sqlite_expert.verify_library(exp_lib)
                return {
                    'available': True,
                    'provenance': lib_info,
                    'experimental_status': 'experimental-preview-only',
                    'indexes_applied_automatically': False,
                }
            except Exception as exc:
                return {'available': False, 'reason': str(exc)}
        if operation == 'expert_analyze':
            sub_req = {k: v for k, v in request.items() if k != 'database_target_id'}
            return sqlite_expert.analyze_queries(route, exp_lib, sub_req)

    # --- SQ-AUD-11: Native Incremental Integrity Check ---
    if operation.startswith('intck_'):
        provider._require('data_read', 'resource')
        intck_lib = _cfg('CDEADMIN_SQLITE_INTCK_LIBRARY') or sqlite_intck.installed_library()
        if operation == 'intck_status':
            try:
                lib_info = sqlite_intck.verify_library(intck_lib)
                avail = {'available': True, 'provenance': lib_info}
            except Exception as exc:
                avail = {'available': False, 'reason': str(exc)}
            jobs = [
                v for v in hub_store.read().get('intck_jobs', {}).values()
                if v.get('owner') == owner and v.get('binding') == binding
            ]
            jobs.sort(key=lambda j: j.get('created_at', 0), reverse=True)
            return {
                'runtime': avail,
                'disclaimer': sqlite_intck.NON_RECOVERY_DISCLAIMER,
                'jobs': jobs[:25],
            }

        if operation == 'intck_open':
            lib_info = sqlite_intck.verify_library(intck_lib)
            target_path = sqlite_intck.resolve_target(route)
            schema_name = str(request.get('schema_name') or 'main')
            unlock_int = int(request.get('unlock_interval') or 16)
            if not 1 <= unlock_int <= 10000:
                raise ValueError('unlock_interval must be between 1 and 10,000')
            job_id = str(uuid.uuid4())
            job = {
                'job_id': job_id,
                'owner': owner,
                'binding': binding,
                'state': 'open',
                'schema_name': schema_name,
                'target_path': str(target_path),
                'target_identity': sqlite_intck.file_identity(target_path),
                'unlock_interval': unlock_int,
                'completed_steps': 0,
                'unlock_count': 0,
                'corrupt_detected': False,
                'corruption_messages': [],
                'concurrent_drift_detected': False,
                'disclaimer': sqlite_intck.NON_RECOVERY_DISCLAIMER,
                'provenance': lib_info,
                'created_at': time.time(),
            }

            def _save_ck(st):
                st.setdefault('intck_jobs', {})[job_id] = job

            hub_store.change(_save_ck)
            return job

        if operation in {'intck_step', 'intck_resume'}:
            jid = request.get('job_id')
            job = deepcopy(hub_store.read().get('intck_jobs', {}).get(jid) or {})
            if not job or job.get('owner') != owner or job.get('binding') != binding:
                raise ValueError('Incremental integrity-check job not found for this target')
            if job['state'] in {'completed', 'closed', 'failed'}:
                raise ValueError(f'Incremental integrity-check job is already {job["state"]}')
            if operation == 'intck_step' and job['state'] == 'paused':
                raise ValueError('Job is paused; invoke intck_resume to continue')
            lib_info = sqlite_intck.verify_library(intck_lib)
            target_path = Path(job['target_path']).resolve(strict=True)
            cur_id = sqlite_intck.file_identity(target_path)
            if [cur_id['device'], cur_id['inode']] != [job['target_identity']['device'], job['target_identity']['inode']]:
                raise ValueError('Target SQLite file inode changed since intck_open')
            max_steps = int(request.get('max_steps') or 100)
            reply, proc_rec = sqlite_intck.run_batch(
                lib_info,
                target_path,
                schema_name=job['schema_name'],
                skip_steps=int(job['completed_steps']),
                max_steps=max_steps,
                unlock_interval=int(job['unlock_interval']),
            )
            if proc_rec['return_code'] != 0 or not reply.get('completed'):
                err_msg = reply.get('error_message') or 'sqlite3_intck_step failed'

                def _fail_ck(st):
                    st['intck_jobs'][jid].update(state='failed', error_message=err_msg, updated_at=time.time())

                hub_store.change(_fail_ck)
                raise ValueError(err_msg)

            def _upd_ck(st):
                cur = st['intck_jobs'][jid]
                merged_msgs = list(dict.fromkeys([*cur.get('corruption_messages', []), *reply['corruption_messages']]))[:100]
                cur.update(
                    state='completed' if reply['done'] else 'active',
                    completed_steps=reply['total_steps'],
                    last_batch_steps=reply['batch_steps'],
                    unlock_count=int(cur.get('unlock_count', 0)) + int(reply['unlock_count']),
                    corrupt_detected=len(merged_msgs) > 0,
                    corruption_messages=merged_msgs,
                    concurrent_drift_detected=bool(cur.get('concurrent_drift_detected') or reply['concurrent_drift_detected']),
                    schema_version_after=reply['schema_version_after'],
                    data_version_after=reply['data_version_after'],
                    last_process_receipt=proc_rec,
                    updated_at=time.time(),
                )

            hub_store.change(_upd_ck)
            return hub_store.read()['intck_jobs'][jid]

        if operation in {'intck_pause', 'intck_close'}:
            jid = request.get('job_id')
            res_box = {}

            def _mut_ck(st):
                cur = st.get('intck_jobs', {}).get(jid)
                if cur is None or cur.get('owner') != owner or cur.get('binding') != binding:
                    raise ValueError('Incremental integrity-check job not found for this target')
                if operation == 'intck_pause':
                    if cur['state'] not in {'open', 'active', 'paused'}:
                        raise ValueError(f'Cannot pause job in state {cur["state"]}')
                    cur['state'] = 'paused'
                else:
                    if cur['state'] != 'completed':
                        cur['state'] = 'closed'
                cur['updated_at'] = time.time()
                res_box['job'] = deepcopy(cur)

            hub_store.change(_mut_ck)
            return res_box['job']

    # --- SQ-AUD-12: Native Incremental Large-BLOB Transfer ---
    if operation.startswith('blob_'):
        schema_name = str(request.get('schema_name') or 'main')
        if operation in {'blob_inspect', 'blob_read_chunk'}:
            provider._require('data_read', 'resource')
            conn = provider.client._connect({'route': route})
            try:
                if operation == 'blob_inspect':
                    return blob_stream.inspect_cell(
                        conn,
                        schema_name=schema_name,
                        table_name=str(request.get('table_name') or ''),
                        column_name=str(request.get('column_name') or ''),
                        rowid=request.get('rowid'),
                    )
                return blob_stream.read_blob_chunk(
                    conn,
                    schema_name=schema_name,
                    table_name=str(request.get('table_name') or ''),
                    column_name=str(request.get('column_name') or ''),
                    rowid=request.get('rowid'),
                    offset=int(request.get('offset') or 0),
                    length=int(request.get('length') or 65536),
                    encoding=str(request.get('encoding') or 'base64'),
                )
            finally:
                provider.client._forget_and_close(conn)

        provider._require('data_write', 'resource')
        if operation == 'blob_allocate_review':
            conn = provider.client._connect({'route': route})
            try:
                cell = blob_stream.inspect_cell(
                    conn,
                    schema_name=schema_name,
                    table_name=str(request.get('table_name') or ''),
                    column_name=str(request.get('column_name') or ''),
                    rowid=request.get('rowid'),
                )
            finally:
                provider.client._forget_and_close(conn)
            byte_len = request.get('byte_length')
            if type(byte_len) is not int or not 0 <= byte_len <= blob_stream.MAX_ZEROBLOB_BYTES:
                raise ValueError('Invalid zeroblob byte_length')
            return _save_review(hub_store, 'blob_alloc_reviews', owner, binding, {
                'schema_name': schema_name,
                'table_name': cell['table'],
                'column_name': cell['column'],
                'rowid': cell['rowid'],
                'byte_length': byte_len,
                'previous_typeof': cell['typeof'],
                'previous_bytes': cell['byte_length'],
            })

        if operation == 'blob_allocate_apply':
            rec = _claim_review(hub_store, 'blob_alloc_reviews', owner, binding, request)
            p = rec['payload']
            conn = provider.client._connect({'route': route})
            try:
                outcome = blob_stream.allocate_zeroblob(
                    conn,
                    schema_name=p['schema_name'],
                    table_name=p['table_name'],
                    column_name=p['column_name'],
                    rowid=p['rowid'],
                    byte_length=p['byte_length'],
                    owned_transaction=True,
                )
                _finish_review(hub_store, 'blob_alloc_reviews', rec['review_id'], 'committed', outcome)
                return {'state': 'committed', 'outcome': outcome}
            except Exception as exc:
                _finish_review(hub_store, 'blob_alloc_reviews', rec['review_id'], 'rolled_back', {'error': str(exc)})
                raise
            finally:
                provider.client._forget_and_close(conn)

        if operation == 'blob_write_review':
            raw = _decode_bytes_input(request)
            offset = int(request.get('offset') or 0)
            conn = provider.client._connect({'route': route})
            try:
                cell = blob_stream.inspect_cell(
                    conn,
                    schema_name=schema_name,
                    table_name=str(request.get('table_name') or ''),
                    column_name=str(request.get('column_name') or ''),
                    rowid=request.get('rowid'),
                )
                if cell['is_null'] or not cell['streamable_blob']:
                    raise ValueError('Target cell is not an allocated BLOB; run blob_allocate first')
                if offset < 0 or offset + len(raw) > int(cell['byte_length'] or 0):
                    raise ValueError('Chunk write exceeds allocated BLOB length; resize via blob_allocate first')
            finally:
                provider.client._forget_and_close(conn)
            chunk_file = artifacts_dir / 'blob_chunks' / f'{uuid.uuid4()}.bin'
            chunk_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            chunk_file.write_bytes(raw)
            os.chmod(chunk_file, 0o600)
            return _save_review(hub_store, 'blob_write_reviews', owner, binding, {
                'schema_name': schema_name,
                'table_name': cell['table'],
                'column_name': cell['column'],
                'rowid': cell['rowid'],
                'offset': offset,
                'chunk_bytes': len(raw),
                'chunk_sha256': hashlib.sha256(raw).hexdigest(),
                'chunk_path': str(chunk_file),
            })

        if operation == 'blob_write_apply':
            rec = _claim_review(hub_store, 'blob_write_reviews', owner, binding, request)
            p = rec['payload']
            cpath = Path(p['chunk_path'])
            raw = cpath.read_bytes()
            if hashlib.sha256(raw).hexdigest() != p['chunk_sha256']:
                raise ValueError('Staged BLOB chunk digest mismatch')
            conn = provider.client._connect({'route': route})
            try:
                outcome = blob_stream.write_blob_chunk(
                    conn,
                    schema_name=p['schema_name'],
                    table_name=p['table_name'],
                    column_name=p['column_name'],
                    rowid=p['rowid'],
                    offset=p['offset'],
                    payload=raw,
                    owned_transaction=True,
                )
                cpath.unlink(missing_ok=True)
                _finish_review(hub_store, 'blob_write_reviews', rec['review_id'], 'committed', outcome)
                return {'state': 'committed', 'outcome': outcome}
            except Exception as exc:
                cpath.unlink(missing_ok=True)
                _finish_review(hub_store, 'blob_write_reviews', rec['review_id'], 'rolled_back', {'error': str(exc)})
                raise
            finally:
                provider.client._forget_and_close(conn)

    # --- SQ-AUD-13: Declared External Shell & Matching CLI ---
    if operation.startswith('shell_'):
        if not host_authorized:
            raise ValueError('Application-host SQLite CLI shell requires host administrator authorization')
        provider._require('data_read', 'resource')
        if operation == 'shell_provenance':
            return shell_tool.verify_matching_cli()
        if operation == 'shell_inspect':
            sub_req = {k: v for k, v in request.items() if k != 'database_target_id'}
            return shell_tool.run_dot_command(route, sub_req)

    # --- SQ-AUD-15: Database-Wide Native SQL Script Exchange ---
    if operation.startswith('dump_'):
        if operation == 'dump_export':
            provider._require('data_read', 'resource')
            dump_id = str(uuid.uuid4())
            art_file = artifacts_dir / 'dumps' / f'{dump_id}.sql'
            sub_req = {k: v for k, v in request.items() if k != 'database_target_id'}
            result = sql_dump.export_sql_dump(route, sub_req, artifact_path=art_file)
            entry = {
                'dump_id': dump_id,
                'owner': owner,
                'binding': binding,
                'created_at': time.time(),
                'artifact_path': str(art_file),
                'byte_length': result['byte_length'],
                'sha256': result['sha256'],
                'command': result['command'],
                'fidelity': result['fidelity'],
                'warnings': result['warnings'],
            }

            def _save_dump(st):
                st.setdefault('sql_dumps', {})[dump_id] = entry

            hub_store.change(_save_dump)
            return {**result, 'dump_id': dump_id}

        if operation == 'dump_list':
            provider._require('data_read', 'resource')
            dumps = [
                {k: v for k, v in item.items() if k != 'artifact_path'}
                for item in hub_store.read().get('sql_dumps', {}).values()
                if item.get('owner') == owner and item.get('binding') == binding
            ]
            dumps.sort(key=lambda d: d.get('created_at', 0), reverse=True)
            return {'dumps': dumps[:25]}

        if operation == 'dump_read':
            provider._require('data_read', 'resource')
            did = request.get('dump_id')
            entry = hub_store.read().get('sql_dumps', {}).get(did)
            if entry is None or entry.get('owner') != owner or entry.get('binding') != binding:
                raise ValueError('SQL dump artifact not found for this owner and target')
            apath = Path(entry['artifact_path'])
            if not apath.is_file():
                raise ValueError('SQL dump artifact file is no longer on disk')
            raw = apath.read_bytes()
            if hashlib.sha256(raw).hexdigest() != entry['sha256']:
                raise ValueError('SQL dump artifact digest changed on disk')
            return {
                'dump_id': did,
                'byte_length': len(raw),
                'sha256': entry['sha256'],
                'sql_text': raw.decode('utf-8', errors='replace'),
            }

        if operation == 'dump_import_review':
            provider._require('administer', 'resource')
            provider._require('data_write', 'resource')
            script_text = request.get('sql_text')
            if not isinstance(script_text, str) or not script_text.strip():
                raise ValueError('Provide non-empty sql_text to review before importing')
            stmts = sql_dump._strip_outer_transaction(script_text)
            script_file = artifacts_dir / 'imports' / f'{uuid.uuid4()}.sql'
            script_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            script_file.write_text(script_text, encoding='utf-8')
            os.chmod(script_file, 0o600)
            return _save_review(hub_store, 'dump_import_reviews', owner, binding, {
                'statement_count': len(stmts),
                'script_sha256': hashlib.sha256(script_text.encode('utf-8')).hexdigest(),
                'script_bytes': len(script_text.encode('utf-8')),
                'script_path': str(script_file),
                'preview_statements': stmts[:10],
            })

        if operation == 'dump_import_apply':
            provider._require('administer', 'resource')
            provider._require('data_write', 'resource')
            rec = _claim_review(hub_store, 'dump_import_reviews', owner, binding, request)
            p = rec['payload']
            spath = Path(p['script_path'])
            script_text = spath.read_text(encoding='utf-8')
            if hashlib.sha256(script_text.encode('utf-8')).hexdigest() != p['script_sha256']:
                raise ValueError('Reviewed SQL import script changed on disk')
            try:
                outcome = sql_dump.apply_sql_script_import(route, script_text)
                spath.unlink(missing_ok=True)
                _finish_review(hub_store, 'dump_import_reviews', rec['review_id'], 'committed', outcome)
                try:
                    service.resource_service.invalidate(context)
                except Exception:
                    pass
                return {'state': 'committed', 'outcome': outcome}
            except Exception as exc:
                spath.unlink(missing_ok=True)
                _finish_review(hub_store, 'dump_import_reviews', rec['review_id'], 'rolled_back', {'error': str(exc)})
                raise

    raise ValueError(f'Unknown SQLite operation {operation!r}')

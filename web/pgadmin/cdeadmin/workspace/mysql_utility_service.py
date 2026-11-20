"""Supervised workspace service for MySQL 9.7.0 native host utilities."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import threading
import time
import uuid

from ..core import EndpointContext
from ..operations.store import JsonOperationStore
from ..providers.mysql_family import mysql_utilities
from ..providers.mysql_family.provider import MySQLDBAPIClient, MySQLPilotProvider
from ..sdk import RelationalClientError
from ..security.secrets import SecretLease


def _background_client(client, planned: dict):
    route = planned.get('provider_payload', {}).get('route') or {}
    refs = dict(route.get('credential_references') or {})
    primary = route.get('credential_reference_id')
    if primary is not None:
        refs.setdefault('database_password', primary)
    ref = refs.get('database_password')
    principal = route.get('principal_reference')
    acquirer = getattr(getattr(client, 'config', None), 'secret_acquirer', None)
    if (
        ref is None
        or not isinstance(principal, str)
        or not principal.strip()
        or not callable(acquirer)
        or not hasattr(client, 'module')
    ):
        return client, None
    req_lease = acquirer(str(ref), principal.strip(), 'connect', 'database_password')
    try:
        pw_bytes = req_lease.use(lambda view: bytes(view))
    finally:
        req_lease.close()
    job_lease = SecretLease(pw_bytes)

    def _job_acquire(sel_ref, sel_principal, purpose, kind):
        if (str(sel_ref), str(sel_principal).strip(), kind) != (str(ref), principal.strip(), 'database_password'):
            raise RelationalClientError('MySQL utility job credential scope mismatch')
        if purpose not in {'connect', 'provider_tool'}:
            raise RelationalClientError('Unsupported MySQL utility job credential purpose')
        return SecretLease(job_lease.use(lambda v: bytes(v)))

    bg_client = MySQLDBAPIClient(replace(client.config, secret_acquirer=_job_acquire), module=client.module)
    return bg_client, job_lease


class MySQLUtilityJobManager:
    """Durable store and cancellation supervisor for MySQL native utility jobs."""

    def __init__(self, store_path: str):
        self._store = JsonOperationStore(store_path)
        self._lock = threading.RLock()
        self._plans: dict[str, dict] = {}
        self._active: dict[str, tuple[threading.Thread | None, threading.Event]] = {}

    def _load_all(self) -> dict:
        data = self._store.read()
        return {'jobs': data.get('operations', {})}

    def _public(self, record: dict) -> dict:
        out = deepcopy(record)
        out.pop('_internal', None)
        return out

    def review(self, owner: int, endpoint_id: str, client, route: dict, request: dict) -> dict:
        op_id = request.get('operation_id')
        target = request.get('target_resource')
        draft = request.get('draft')
        if op_id not in mysql_utilities.OPERATIONS or not isinstance(target, dict) or not isinstance(draft, dict):
            raise RelationalClientError('Supply operation_id, target_resource, and typed draft for MySQL utility review')
        plan_req = {
            'resource_kind': 'server',
            'operation_id': op_id,
            'target_resource': deepcopy(target),
            'draft': deepcopy(draft),
            '_provider_route': deepcopy(route),
        }
        planned = client.plan_admin_operation(plan_req)
        job_id = 'myutil-job-' + uuid.uuid4().hex
        digest_src = json.dumps(
            {
                'job_id': job_id,
                'operation_id': op_id,
                'command_preview': planned.get('command_preview'),
            },
            sort_keys=True,
            separators=(',', ':'),
        ).encode('utf-8')
        review_digest = hashlib.sha256(digest_src).hexdigest()
        now = time.time()
        record = {
            'job_id': job_id,
            'owner': owner,
            'endpoint_id': endpoint_id,
            'engine': 'mysql',
            'operation_id': op_id,
            'utility': mysql_utilities.OPERATION_BINARY[op_id],
            'state': 'reviewed',
            'review_digest': review_digest,
            'command_preview': deepcopy(planned.get('command_preview')),
            'warnings': deepcopy(planned.get('warnings', [])),
            'created_at': now,
            'updated_at': now,
            'cancel_requested': False,
            'result': None,
            'error': None,
        }
        with self._lock:
            self._plans[job_id] = planned
            def _save(state):
                state.setdefault('operations', {})[job_id] = deepcopy(record)
            self._store.change(_save)
        return self._public(record)

    def get(self, owner: int, endpoint_id: str, job_id: str) -> dict:
        with self._lock:
            state = self._load_all()
            rec = state.get('jobs', {}).get(job_id)
            if not rec or rec['owner'] != owner or rec['endpoint_id'] != endpoint_id:
                raise RelationalClientError('MySQL utility job was not found for this endpoint owner')
            return self._public(rec)

    def list_jobs(self, owner: int, endpoint_id: str, offset: int = 0, limit: int = 25) -> dict:
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise RelationalClientError('Invalid pagination bounds')
        with self._lock:
            state = self._load_all()
            matching = [
                self._public(r)
                for r in state.get('jobs', {}).values()
                if r.get('owner') == owner and r.get('endpoint_id') == endpoint_id
            ]
        matching.sort(key=lambda r: r.get('created_at', 0), reverse=True)
        return {
            'jobs': matching[offset: offset + limit],
            'total': len(matching),
            'offset': offset,
            'limit': limit,
        }

    def start(self, owner: int, endpoint_id: str, client, request: dict) -> dict:
        job_id = request.get('job_id')
        if not isinstance(job_id, str) or not job_id:
            raise RelationalClientError('Select a reviewed MySQL utility job_id')
        if request.get('confirmed') is not True:
            raise RelationalClientError('Confirm the reviewed MySQL utility job before starting')
        async_exec = bool(request.get('async_execution', False))

        with self._lock:
            state = self._load_all()
            rec = state.get('jobs', {}).get(job_id)
            if not rec or rec['owner'] != owner or rec['endpoint_id'] != endpoint_id:
                raise RelationalClientError('MySQL utility job was not found for this endpoint owner')
            if rec['review_digest'] != request.get('review_digest'):
                raise RelationalClientError('review_digest does not match the reviewed MySQL utility job')
            if rec['state'] != 'reviewed':
                return self._public(rec)
            planned = self._plans.pop(job_id, None)
            if planned is None:
                raise RelationalClientError('Reviewed MySQL utility plan is no longer retained; review again')
            cancel_event = threading.Event()

            def _mark_active(st):
                cur = st['operations'][job_id]
                cur['state'] = 'active'
                cur['started_at'] = time.time()
                cur['updated_at'] = time.time()

            self._store.change(_mark_active)

        exec_client, job_lease = _background_client(client, planned) if async_exec else (client, None)

        def _execute():
            try:
                res = mysql_utilities.apply(exec_client, planned, cancel_signal=cancel_event)
                with self._lock:
                    def _done(st):
                        cur = st['operations'][job_id]
                        cur['state'] = 'completed'
                        cur['result'] = deepcopy(res['mysql_utility'])
                        cur['native_acknowledged'] = bool(res.get('native_acknowledged'))
                        cur['finished_at'] = time.time()
                        cur['updated_at'] = time.time()
                    self._store.change(_done)
            except BaseException as exc:
                msg = str(exc)
                was_cancelled = cancel_event.is_set() or 'cancelled' in msg.lower()
                with self._lock:
                    def _fail(st):
                        cur = st['operations'][job_id]
                        cur['state'] = 'cancelled' if was_cancelled else 'failed'
                        cur['error'] = {'type': type(exc).__name__, 'message': msg}
                        cur['cleanup_confirmed'] = bool(getattr(exc, 'cleanup_confirmed', False))
                        cur['finished_at'] = time.time()
                        cur['updated_at'] = time.time()
                    self._store.change(_fail)
            finally:
                if job_lease is not None:
                    job_lease.close()
                if exec_client is not client:
                    exec_client.close()
                with self._lock:
                    self._active.pop(job_id, None)

        if async_exec:
            worker = threading.Thread(target=_execute, name=f'mysql-util-{job_id[:12]}', daemon=True)
            with self._lock:
                self._active[job_id] = (worker, cancel_event)
            worker.start()
            return self.get(owner, endpoint_id, job_id)

        with self._lock:
            self._active[job_id] = (None, cancel_event)
        _execute()
        final_rec = self.get(owner, endpoint_id, job_id)
        if final_rec['state'] == 'failed':
            raise RelationalClientError(final_rec['error']['message'])
        return final_rec

    def cancel(self, owner: int, endpoint_id: str, job_id: str) -> dict:
        worker = None
        with self._lock:
            state = self._load_all()
            rec = state.get('jobs', {}).get(job_id)
            if not rec or rec['owner'] != owner or rec['endpoint_id'] != endpoint_id:
                raise RelationalClientError('MySQL utility job was not found for this endpoint owner')
            if rec['state'] == 'reviewed':
                planned = self._plans.pop(job_id, None)
                if planned:
                    lease_id = planned.get('provider_payload', {}).get('compiled', {}).get(mysql_utilities.KEY, {}).get('ssh_lease_id')
                    mysql_utilities._release_ssh_secrets(lease_id)
                def _cancel_rev(st):
                    cur = st['operations'][job_id]
                    cur['state'] = 'cancelled'
                    cur['cancel_requested'] = True
                    cur['cleanup_confirmed'] = True
                    cur['finished_at'] = time.time()
                    cur['updated_at'] = time.time()
                self._store.change(_cancel_rev)
                return self.get(owner, endpoint_id, job_id)
            active_pair = self._active.get(job_id)
            if active_pair is not None:
                worker, cancel_event = active_pair
                cancel_event.set()
                def _mark_cancelling(st):
                    st['operations'][job_id]['cancel_requested'] = True
                    st['operations'][job_id]['updated_at'] = time.time()
                self._store.change(_mark_cancelling)
        if worker is not None:
            worker.join(timeout=20)
        return self.get(owner, endpoint_id, job_id)


def _manager_and_client(service, server):
    endpoint = server.endpoint_profile
    if endpoint is None or endpoint.profile_id != 'mysql-native' or endpoint.provider_id != 'org.cdeadmin.mysql':
        raise RelationalClientError('Select a native MySQL registration for utility execution')
    context, payload, _root = service.endpoint_service.workspace(server, database_target_id=None)
    if 'administer' not in service.endpoint_service.provider_registry.admitted_permissions(context):
        raise RelationalClientError('MySQL native utilities require administration authority')
    provider = service.endpoint_service.provider_registry.resolve(context).instance
    if not isinstance(provider, MySQLPilotProvider):
        raise RelationalClientError('MySQL provider instance is unavailable')
    store = getattr(service.operation_bus, 'store', None)
    if not isinstance(store, JsonOperationStore):
        raise RelationalClientError('MySQL utility jobs require durable application storage')
    with service._semantic_lock:
        mgr = getattr(service, '_mysql_utility_jobs', None)
        if mgr is None:
            mgr = service._mysql_utility_jobs = MySQLUtilityJobManager(str(store.path) + '.mysql-utilities')
    return mgr, service._principal_id(server), endpoint, provider.client, deepcopy(payload['route'])


def action(service, server, operation: str, request):
    if not isinstance(request, dict):
        raise RelationalClientError('Supply a JSON object request for MySQL utility action')
    mgr, owner, endpoint, client, route = _manager_and_client(service, server)
    if operation == 'catalog':
        return {
            'engine': 'mysql',
            'version': '9.7.0',
            'utilities': [
                {'operation_id': op_id, 'title': title, **mysql_utilities.PROVENANCE[mysql_utilities.OPERATION_BINARY[op_id]]}
                for op_id, title in mysql_utilities.OPERATIONS.items()
            ],
        }
    if operation == 'review':
        return mgr.review(owner, endpoint.id, client, route, request)
    if operation == 'start':
        return mgr.start(owner, endpoint.id, client, request)
    if operation == 'status':
        return mgr.get(owner, endpoint.id, request.get('job_id', ''))
    if operation == 'cancel':
        return mgr.cancel(owner, endpoint.id, request.get('job_id', ''))
    if operation == 'list':
        return mgr.list_jobs(owner, endpoint.id, request.get('offset', 0), request.get('limit', 25))
    raise RelationalClientError(f'Unsupported MySQL utility workspace action: {operation!r}')

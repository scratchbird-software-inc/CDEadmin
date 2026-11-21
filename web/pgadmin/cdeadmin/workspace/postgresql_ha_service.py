"""Owner-bound PostgreSQL HA topology, standby bootstrap, promotion, switchover & host pg_ctl service."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

from ..operations.fileio import exclusive_file_lock, private_directory
from ..operations.store import JsonOperationStore
from ..providers.postgresql.continuity import ContinuityError
from ..providers.postgresql.ha_topology import (
    check_host_datadir_grant,
    execute_coordinated_switchover,
    execute_host_pg_ctl,
    execute_standby_bootstrap,
    execute_standby_promotion,
    inspect_topology,
)
from .postgresql_continuity_service import artifact_context, paths_for_app
from .postgresql_monitoring_host import PostgreSQLMonitoringHost


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf8')
    ).hexdigest()


def _ha_store_call(service, owner: int, endpoint: str, fn):
    store_obj = getattr(service.operation_bus, 'store', None)
    if not isinstance(store_obj, JsonOperationStore):
        raise ContinuityError('HA orchestration requires durable application storage')
    base = Path(str(store_obj.path) + '.postgresql-ha') / str(owner) / endpoint
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_directory(base)
    path = base / 'jobs.json'
    fd = os.open(str(path) + '.lock', os.O_RDWR | os.O_CREAT, 0o600)
    try:
        with exclusive_file_lock(fd):
            return fn(JsonOperationStore(path))
    finally:
        os.close(fd)


def _server_conn_params(service, server) -> dict:
    context, payload, _root = service.endpoint_service.workspace(server, database_target_id=None)
    provider = service.endpoint_service.provider_registry.resolve(context).instance
    from ..providers.postgresql.continuity_transport import capture
    _source, transport = capture(provider, payload['route'], server=server)
    try:
        with transport.parameters() as params:
            return dict(params)
    finally:
        transport.close()


def action(service, server, operation: str, request: dict, *, host_authorized: bool = False) -> dict:
    from flask import current_app
    if not isinstance(request, dict):
        raise ContinuityError('A PostgreSQL HA request object is required')
    if not PostgreSQLMonitoringHost._native_registration(server):
        raise ContinuityError('Select a native PostgreSQL registration')
    owner = service._principal_id(server)
    endpoint = server.endpoint_profile.id
    permissions = service.endpoint_service.provider_registry.admitted_permissions(artifact_context(server))
    if 'backup_admin' not in permissions and 'administer' not in permissions:
        raise ContinuityError('PostgreSQL HA administration permission is unavailable')

    if operation == 'topology':
        if set(request) - {'datadir'}:
            raise ContinuityError('Unsupported HA topology fields')
        params = _server_conn_params(service, server)
        topo = inspect_topology(params)
        if request.get('datadir'):
            ddir = check_host_datadir_grant(current_app, request['datadir'], host_authorized)
            paths = paths_for_app(current_app)
            topo['host_pg_ctl'] = execute_host_pg_ctl(paths, ddir, 'status')
        return topo

    if operation == 'list':
        def _list(store):
            jobs = list(store.read().get('ha_jobs', {}).values())
            jobs.sort(key=lambda r: r.get('created_at', 0), reverse=True)
            return {'jobs': jobs[:50], 'total': len(jobs)}
        return _ha_store_call(service, owner, endpoint, _list)

    if operation == 'status':
        job_id = request.get('job_id')
        def _get(store):
            rec = store.read().get('ha_jobs', {}).get(job_id)
            if not rec:
                raise ContinuityError('Selected HA job receipt is unavailable')
            return deepcopy(rec)
        return _ha_store_call(service, owner, endpoint, _get)

    if operation == 'review':
        ha_op = request.get('operation')
        opts = request.get('options') or {}
        if not isinstance(opts, dict):
            raise ContinuityError('HA review options must be an object')
        if ha_op not in {'standby_bootstrap', 'promote', 'switchover', 'host_pg_ctl'}:
            raise ContinuityError('Select standby_bootstrap, promote, switchover, or host_pg_ctl')

        paths = paths_for_app(current_app)
        if ha_op in {'standby_bootstrap', 'host_pg_ctl'}:
            ddir = check_host_datadir_grant(
                current_app,
                opts.get('standby_datadir' if ha_op == 'standby_bootstrap' else 'datadir', ''),
                host_authorized,
            )
            if ha_op == 'standby_bootstrap' and ddir.exists() and any(ddir.iterdir()):
                raise ContinuityError('Standby destination directory must be empty before bootstrap')
        topo = None
        if ha_op in {'standby_bootstrap', 'promote', 'switchover'}:
            params = _server_conn_params(service, server)
            topo = inspect_topology(params)
            if ha_op == 'promote' and not topo['in_recovery'] and not opts.get('target_dsn'):
                raise ContinuityError('Registered cluster is already a primary; select a standby to promote')
            if ha_op == 'switchover':
                if topo['in_recovery']:
                    raise ContinuityError('Switchover source must be an active primary')
                if not isinstance(opts.get('standby_dsn'), str) or not opts['standby_dsn'].strip():
                    raise ContinuityError('Provide standby_dsn for coordinated switchover')

        job_id = str(uuid.uuid4())
        rec = {
            'job_id': job_id,
            'operation': ha_op,
            'options': deepcopy(opts),
            'topology_at_review': topo,
            'paths': deepcopy(paths),
            'state': 'reviewed',
            'created_at': time.time(),
            'expires_at': time.time() + 600,
            'automatic_retry': False,
        }
        rec['review_digest'] = _sha256_json({
            'job_id': job_id,
            'operation': ha_op,
            'options': opts,
            'system_identifier': (topo or {}).get('system_identifier'),
        })

        def _save(store):
            store.change(lambda s: s.setdefault('ha_jobs', {}).__setitem__(job_id, rec))
            return deepcopy(rec)
        return _ha_store_call(service, owner, endpoint, _save)

    if operation == 'start':
        if set(request) != {'job_id', 'review_digest', 'confirmed'} or request.get('confirmed') is not True:
            raise ContinuityError('Confirm HA execution with job_id, review_digest, and confirmed=True')
        job_id = request['job_id']

        def _claim(store):
            rec = store.read().get('ha_jobs', {}).get(job_id)
            if not rec:
                raise ContinuityError('HA review is unavailable')
            if rec['review_digest'] != request['review_digest']:
                raise ContinuityError('HA review digest mismatch')
            if rec['state'] != 'reviewed':
                raise ContinuityError('HA review was already dispatched; automatic replay is refused')
            if time.time() > rec['expires_at']:
                raise ContinuityError('HA review expired; prepare it again')
            def _mut(s):
                s['ha_jobs'][job_id]['state'] = 'executing'
                s['ha_jobs'][job_id]['dispatched_at'] = time.time()
            store.change(_mut)
            return deepcopy(rec)

        rec = _ha_store_call(service, owner, endpoint, _claim)
        ha_op = rec['operation']
        opts = rec['options']
        try:
            if ha_op == 'standby_bootstrap':
                ddir = check_host_datadir_grant(current_app, opts['standby_datadir'], host_authorized)
                params = _server_conn_params(service, server)
                result = execute_standby_bootstrap(
                    rec['paths'],
                    params,
                    ddir,
                    slot_name=opts.get('slot_name'),
                    create_slot=bool(opts.get('create_slot', False)),
                    standby_port=opts.get('standby_port'),
                    start_standby=bool(opts.get('start_standby', False)),
                    application_name=opts.get('application_name'),
                )
            elif ha_op == 'promote':
                target = opts.get('target_dsn') or _server_conn_params(service, server)
                result = execute_standby_promotion(target, wait_seconds=int(opts.get('wait_seconds', 30)))
            elif ha_op == 'switchover':
                params = _server_conn_params(service, server)
                result = execute_coordinated_switchover(
                    params,
                    opts['standby_dsn'],
                    max_lag_bytes=int(opts.get('max_lag_bytes', 16 * 1024 * 1024)),
                    wait_seconds=int(opts.get('wait_seconds', 30)),
                )
            elif ha_op == 'host_pg_ctl':
                ddir = check_host_datadir_grant(current_app, opts['datadir'], host_authorized)
                result = execute_host_pg_ctl(
                    rec['paths'],
                    ddir,
                    opts.get('ctl_action', 'status'),
                    stop_mode=opts.get('stop_mode', 'fast'),
                    wait_seconds=int(opts.get('wait_seconds', 30)),
                    log_file=opts.get('log_file'),
                )
            else:
                raise ContinuityError('Unsupported HA operation')
        except Exception as exc:
            def _fail(store):
                store.change(lambda s: s['ha_jobs'][job_id].update(
                    state='failed', error=str(exc), finished_at=time.time()
                ))
            _ha_store_call(service, owner, endpoint, _fail)
            raise

        def _done(store):
            def _mut(s):
                s['ha_jobs'][job_id].update(
                    state='completed',
                    result=result,
                    finished_at=time.time(),
                )
            store.change(_mut)
            return deepcopy(store.read()['ha_jobs'][job_id])
        return _ha_store_call(service, owner, endpoint, _done)

    raise ContinuityError('PostgreSQL HA action is unavailable')

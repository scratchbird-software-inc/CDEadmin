"""Workspace service for authorized PostgreSQL host configuration, HBA, ident & TLS lifecycle (PG-AUDIT-CONFIG-01)."""
from __future__ import annotations

import atexit
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time
import uuid

from ..operations.fileio import exclusive_file_lock, private_directory, private_file
from ..operations.store import JsonOperationStore
from ..providers.postgresql import configuration as native_cfg
from ..providers.postgresql.continuity import ContinuityError
from ..providers.postgresql.host_tools import grants
from ..providers.postgresql.native_admin import PostgreSQLNativeAdminError
from .postgresql_continuity_service import artifact_context, paths_for_app
from .postgresql_monitoring_host import PostgreSQLMonitoringHost


def _digest(obj: dict) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()


class PostgreSQLConfigJobStore:
    def __init__(self, store_path: str | Path, root_dir: str | Path):
        self.store_path = Path(store_path).resolve()
        self.root = Path(root_dir).resolve()
        self.store_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        private_directory(self.root)

    def close(self):
        pass

    def _with_store(self, fn):
        lock_file = self.store_path.parent / (self.store_path.name + '.lock')
        with lock_file.open('a+b') as lf:
            private_file(lock_file)
            with exclusive_file_lock(lf.fileno()):
                return fn(JsonOperationStore(self.store_path))

    def job_dir(self, owner: int, endpoint_id: str, job_id: str) -> Path:
        d = self.root / str(owner) / str(endpoint_id) / str(job_id)
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
        private_directory(d)
        return d

    def save(self, rec: dict) -> dict:
        jid = rec['job_id']

        def _w(store):
            store.change(lambda doc: doc.setdefault('jobs', {}).update({jid: deepcopy(rec)}))
            return deepcopy(store.read()['jobs'][jid])

        out = self._with_store(_w)
        out.pop('owner', None)
        out.pop('_staged_content', None)
        return out

    def load(self, job_id: str, owner: int, endpoint_id: str) -> dict:
        def _r(store):
            rec = store.read().get('jobs', {}).get(str(job_id))
            if rec is None or rec['owner'] != owner or rec['endpoint_id'] != endpoint_id:
                raise ContinuityError('Select an owned PostgreSQL configuration job')
            return deepcopy(rec)

        return self._with_store(_r)

    def list(self, owner: int, endpoint_id: str, offset: int = 0, limit: int = 25) -> dict:
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
            raise ContinuityError('Invalid PostgreSQL configuration job list bounds')

        def _r(store):
            return [
                deepcopy(r)
                for r in store.read().get('jobs', {}).values()
                if r['owner'] == owner and r['endpoint_id'] == endpoint_id
            ]

        items = sorted(self._with_store(_r), key=lambda r: (r['created_at'], r['job_id']), reverse=True)
        for it in items:
            it.pop('owner', None)
            it.pop('_staged_content', None)
        return {'jobs': items[offset:offset + limit], 'total': len(items), 'offset': offset, 'limit': limit}


def _resolve_granted_cluster(manifest_path: str | None, endpoint_id: str, cluster_id: str) -> Path:
    grant, _sha = grants(manifest_path, endpoint_id)
    for row in grant.get('clusters', []):
        if row['id'] == cluster_id:
            return Path(row['path'])
    raise ContinuityError(f'Cluster {cluster_id!r} is not in the operator host grant manifest')


def action(service, server, operation: str, request, *, host_authorized: bool = False) -> dict:
    from flask import current_app

    if host_authorized is not True:
        raise ContinuityError('Application-host Administrator authority is required')
    if not isinstance(request, dict) or not PostgreSQLMonitoringHost._native_registration(server):
        raise ContinuityError('Select a native PostgreSQL registration and typed configuration request')
    permissions = service.endpoint_service.provider_registry.admitted_permissions(artifact_context(server))
    if 'administer' not in permissions:
        raise ContinuityError('PostgreSQL administration permission is required')

    store = getattr(service.operation_bus, 'store', None)
    if not isinstance(store, JsonOperationStore):
        raise ContinuityError('PostgreSQL host configuration requires durable application storage')
    root = current_app.config.get('CDEADMIN_POSTGRESQL_CONFIG_ROOT') or str(store.path.parent / 'postgresql-config')
    with service._semantic_lock:
        jobs = getattr(service, 'postgresql_config_jobs', None)
        if jobs is None:
            jobs = service.postgresql_config_jobs = PostgreSQLConfigJobStore(
                str(store.path) + '.postgresql-config', root
            )
            atexit.register(jobs.close)

    owner = service._principal_id(server)
    endpoint_id = server.endpoint_profile.id
    manifest = current_app.config.get('CDEADMIN_POSTGRESQL_HOST_TOOL_MANIFEST')
    bin_dir = current_app.config.get('CDEADMIN_POSTGRESQL_HOST_BINARY_PATH') or str(
        Path(paths_for_app(current_app)['pg_controldata']).parent
    )
    postgres_bin = str(Path(bin_dir) / 'postgres')

    try:
        if operation == 'list':
            return jobs.list(owner, endpoint_id, request.get('offset', 0), request.get('limit', 25))

        if operation == 'status':
            rec = jobs.load(request.get('job_id', ''), owner, endpoint_id)
            rec.pop('owner', None)
            rec.pop('_staged_content', None)
            return rec

        if operation == 'inspect_file':
            cluster_dir = _resolve_granted_cluster(manifest, endpoint_id, str(request.get('cluster_id') or ''))
            file_kind = str(request.get('file_kind') or 'postgresql.conf')
            target = native_cfg.resolve_cluster_file(cluster_dir, file_kind)
            exists = target.is_file()
            text = ''
            sha = None
            if exists and file_kind != 'server.key':
                raw = target.read_bytes()
                sha = hashlib.sha256(raw).hexdigest()
                text = raw.decode('utf-8', errors='replace')
            elif exists:
                sha = hashlib.sha256(target.read_bytes()).hexdigest()
                text = '[REDACTED PRIVATE KEY — supply replacement PEM to rotate]'
            return {
                'cluster_id': request['cluster_id'],
                'file_kind': file_kind,
                'exists': exists,
                'sha256': sha,
                'content': text,
            }

        if operation == 'review_deploy':
            cluster_id = str(request.get('cluster_id') or '')
            file_kind = str(request.get('file_kind') or '')
            content = request.get('replacement_text')
            cluster_dir = _resolve_granted_cluster(manifest, endpoint_id, cluster_id)
            target = native_cfg.resolve_cluster_file(cluster_dir, file_kind)
            before_sha = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
            validation = native_cfg.validate_host_file_content(postgres_bin, cluster_dir, file_kind, content)
            new_sha = hashlib.sha256((content if content.endswith('\n') else content + '\n').encode('utf-8')).hexdigest()
            jid = 'pgcfg-' + uuid.uuid4().hex
            rec = {
                'job_id': jid,
                'owner': owner,
                'endpoint_id': endpoint_id,
                'state': 'reviewed',
                'cluster_id': cluster_id,
                'file_kind': file_kind,
                'before_sha256': before_sha,
                'replacement_sha256': new_sha,
                'reload_after': bool(request.get('reload_after', True)),
                'validation': validation,
                '_staged_content': content,
                'warnings': [
                    'Deploys atomically with a 0600 backup copy for explicit rollback; private keys are never echoed in receipts.',
                ],
                'created_at': time.time(),
                'expires_at': time.time() + 600,
                'automatic_retry': False,
            }
            rec['review_digest'] = _digest({
                'job_id': jid,
                'cluster_id': cluster_id,
                'file_kind': file_kind,
                'before_sha256': before_sha,
                'replacement_sha256': new_sha,
            })
            return jobs.save(rec)

        if operation == 'start_deploy':
            if request.get('confirmed') is not True:
                raise ContinuityError('Confirm the exact PostgreSQL host configuration review')
            rec = jobs.load(request.get('job_id', ''), owner, endpoint_id)
            if rec['review_digest'] != request.get('review_digest'):
                raise ContinuityError('PostgreSQL host configuration review_digest mismatch')
            if rec['state'] != 'reviewed':
                rec.pop('owner', None)
                rec.pop('_staged_content', None)
                return rec
            cluster_dir = _resolve_granted_cluster(manifest, endpoint_id, rec['cluster_id'])
            target = native_cfg.resolve_cluster_file(cluster_dir, rec['file_kind'])
            cur_sha = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None
            if cur_sha != rec['before_sha256']:
                raise ContinuityError('Target PostgreSQL host file changed since review; inspect and review again')
            jdir = jobs.job_dir(owner, endpoint_id, rec['job_id'])
            deployed = native_cfg.deploy_cluster_file_with_backup(
                cluster_dir, rec['file_kind'], rec['_staged_content'], jdir
            )
            reloaded = False
            if rec.get('reload_after'):
                pg_ctl = str(Path(bin_dir) / 'pg_ctl')
                if (cluster_dir / 'postmaster.pid').is_file():
                    import subprocess
                    proc = subprocess.run([pg_ctl, '-D', str(cluster_dir), 'reload'], capture_output=True, text=True, timeout=15)
                    reloaded = proc.returncode == 0
            rec.update(
                state='completed',
                result={**deployed, 'reloaded': reloaded},
                finished_at=time.time(),
            )
            rec.pop('_staged_content', None)
            return jobs.save(rec)

        if operation == 'rollback':
            if request.get('confirmed') is not True:
                raise ContinuityError('Confirm rolling back the deployed PostgreSQL host file')
            rec = jobs.load(request.get('job_id', ''), owner, endpoint_id)
            if rec['state'] != 'completed':
                raise ContinuityError('Select a completed PostgreSQL configuration deployment to roll back')
            jdir = jobs.job_dir(owner, endpoint_id, rec['job_id'])
            rb = native_cfg.rollback_cluster_file(jdir)
            rec.update(state='rolled_back', rollback_result=rb, rolled_back_at=time.time())
            return jobs.save(rec)

    except PostgreSQLNativeAdminError as exc:
        raise ContinuityError(str(exc)) from None

    raise ContinuityError(f'Unsupported PostgreSQL host configuration action: {operation!r}')

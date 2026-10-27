"""Offline-capable, explicitly authorized execution-host sandbox lifecycle."""
import atexit
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import threading
import time

from ..operations.fileio import exclusive_file_lock, private_directory
from ..operations.store import JsonOperationStore
from ..security import SecretLease
from ..providers.mysql_family import mysql_sandbox as native
from ..providers.mysql_family.provider import MySQLPilotProvider
from .mysql_binlog_jobs import ACTIVE, DurableCancellation, MySQLBinlogJobs, digest
from .mysql_topology_service import admitted_context


class SandboxJobs(MySQLBinlogJobs):
    operation = 'mysql_local_sandbox'
    review_warnings = (
        'These native testing sandboxes run on the ScratchRobin execution host under its operating-system account. This is not remote database service deployment.',
        'Delete removes the selected native sandbox directory and its data. Kill forcibly terminates the observed native process. Completed changes are not rolled back by cancellation.',
        'The original native reply, current filesystem/process state and application SQL readiness have separate meanings. Uncertain operations are never automatically repeated.',
    )

    def public(self, record):
        result = super().public(record)
        result['sandbox'] = result.pop('source')
        result['native_operation_outcome'] = record.get('native_operation_outcome',
            'unknown' if record.get('native_may_have_dispatched') else 'not_dispatched')
        result['sql_readiness_verified'] = False
        return result

    def fence_path(self, record):
        # Ports are shared across registrations and sandbox base directories.
        root = self.root / 'host-port-fences'; root.mkdir(mode=0o700, parents=True, exist_ok=True); private_directory(root)
        return root / (digest({'host': record['source']['host_id'], 'port': record['source']['port']}) + '.json')

    def fence(self, record, *, release=False):
        path = self.fence_path(record)
        with path.with_suffix('.lock').open('a+b') as lock:
            with exclusive_file_lock(lock.fileno()):
                store = JsonOperationStore(path)
                def change(state):
                    previous = state.get('job_id')
                    if release:
                        if previous == record['job_id']:
                            for key in ('job_id', 'owner', 'endpoint_id'): state.pop(key, None)
                    elif previous not in {None, record['job_id']}:
                        raise native.BinlogArchiveError('Another sandbox operation holds this execution-host port; inspect its retained receipt')
                    else: state.update(job_id=record['job_id'], owner=record['owner'], endpoint_id=record['endpoint_id'])
                store.change(change)

    def start(self, request, owner, endpoint, current, transport):
        record = self.load(request.get('job_id') if isinstance(request, dict) else None, owner, endpoint)
        claimed = False
        try:
            if record['state'] == 'reviewed': self.fence(record); claimed = True
            result = super().start(request, owner, endpoint, current, transport)
            if claimed and result['state'] in {'cancelled', 'not_dispatched'}: self.fence(record, release=True)
            return result
        except BaseException:
            if claimed and self.load(record['job_id'], owner, endpoint)['state'] in {'reviewed', 'not_dispatched'}:
                self.fence(record, release=True)
            if transport is not None: transport.close()
            raise

    def run(self, record, transport, signal):
        invoked = False
        try:
            self.update(record, state='active')
            cancel = DurableCancellation(self, record, signal)
            def boundary():
                nonlocal invoked
                invoked = True
                self.update(record, native_may_have_dispatched=True, native_operation_outcome='unknown')
            result = transport.execute(record, self.directory(record), cancel,
                lambda value: self.progress(record, value), boundary)
            control = result.get('control') or {}
            returned = control.get('returned') is True
            error_returned = isinstance(control.get('native_error'), dict)
            process = result['tool'].get('process_observation', {})
            terminated = process.get('cleanup_confirmed') is True
            outcome = 'returned' if returned else 'native_error' if error_returned else 'not_dispatched' if process.get('started') is False else 'unknown'
            self.update(record, state='operation_returned' if returned else outcome,
                native_operation_outcome=outcome, native_error=control.get('native_error'), result=result,
                native_may_have_dispatched=invoked and outcome != 'not_dispatched',
                finished_at=time.time(), native_process_termination_confirmed=terminated)
            if outcome != 'unknown' and terminated: self.fence(record, release=True)
        except BaseException as error:
            observation = getattr(error, 'observation', None) or getattr(error, 'process_observation', None)
            safe = {key: item for key, item in observation.items() if key not in {'stdout', 'stderr'}} if isinstance(observation, dict) else None
            self.update(record, state='unknown' if invoked else 'not_dispatched',
                native_operation_outcome='unknown' if invoked else 'not_dispatched',
                error_type=type(error).__name__, tool_observation=safe, finished_at=time.time(),
                native_process_termination_confirmed=False if invoked else True)
            if not invoked: self.fence(record, release=True)
        finally:
            try: transport.close()
            finally:
                with self._maps_lock:
                    known = self.workers.get(record['job_id'])
                    if known and known[0] is threading.current_thread(): self.workers.pop(record['job_id'], None)

    def reconcile_state(self, record, observation):
        if self.public(record)['state'] in ACTIVE:
            raise native.BinlogArchiveError('The sandbox worker is still active')
        self.observe_utility(record)
        current = self.load(record['job_id'], record['owner'], record['endpoint_id'])
        if not current.get('native_may_have_dispatched') and self.public(current)['state'] == 'unknown':
            self.update(record, state='not_dispatched', native_process_termination_confirmed=True)
            self.fence(record, release=True)
        elif current.get('native_operation_outcome') in {'returned', 'native_error'} and current.get('native_process_termination_confirmed') is True:
            self.fence(record, release=True)
        self.update(record, reconciliation=observation, observed_at=time.time(),
                    **({'state': 'unknown'} if current.get('native_may_have_dispatched') and self.public(current)['state'] == 'unknown' else {}))
        result = self.get(record['job_id'], record['owner'], record['endpoint_id'])
        result['observation_digest'] = digest(observation)
        return result

    def acknowledge(self, record, observation, request):
        if self.public(record)['state'] != 'unknown' or record.get('native_process_termination_confirmed') is not True:
            raise native.BinlogArchiveError('Confirm native utility termination and observe the uncertain sandbox first')
        if (request['observation_digest'] != digest(observation) or
                record.get('reconciliation') != observation or request['sandbox_confirmation'] != str(record['source']['port']) or
                observation['state']['process']['qualified'] is not True):
            raise native.BinlogArchiveError('Confirm the exact independently observed sandbox state')
        self.update(record, target_state_acknowledged_at=time.time())
        self.fence(record, release=True)
        return self.get(record['job_id'], record['owner'], record['endpoint_id'])


class SandboxTransport:
    def __init__(self, client, secret): self.client, self.secret = client, secret
    def close(self):
        if self.secret is not None:
            owned = self.secret; self.secret = None; owned.close()

    def execute(self, record, directory, cancel, progress, boundary):
        observed = native.observe(self.client, record['options'], directory.parent)
        native.admit(record['options'], observed)
        if observed['identity'] != record['source'] or observed['state'] != record['source_state']:
            raise native.BinlogArchiveError('Native sandbox state changed after review')
        result = self.secret.use(lambda view: native.execute(self.client, record['options'], directory, record['program'],
            bytes(view) if record['options']['operation'] in {'deploy', 'stop'} else None,
            expected_uuid=observed['state'].get('server_uuid'),
            cancel=cancel, progress=progress, boundary=boundary))
        try: result['sandbox_observation'] = native.observe(self.client, record['options'], directory.parent)
        except Exception as error: result['sandbox_observation'] = {'available': False, 'error_type': type(error).__name__}
        return result


def authority(service, server):
    import config
    from flask import current_app
    from flask_security import current_user
    admitted = admitted_context(service, server)
    if config.SERVER_MODE and (current_app.config.get('CDEADMIN_MYSQL_SANDBOX_ENABLED') is not True or
                               not current_user.has_role('Administrator')):
        raise native.BinlogArchiveError('Local sandbox lifecycle requires an Administrator and explicit execution-host enablement in server mode')
    owner = service._principal_id(server)
    registry = service.endpoint_service.provider_registry
    permissions = registry.admitted_permissions(admitted)
    if 'execute' not in permissions:
        raise native.BinlogArchiveError('Native sandbox utility execution permission is unavailable')
    provider = registry.resolve(replace(admitted, effective_permissions=permissions)).instance
    if not isinstance(provider, MySQLPilotProvider): raise native.BinlogArchiveError('Native MySQL sandbox client is unavailable')
    store = service.operation_bus.store
    if not isinstance(store, JsonOperationStore): raise native.BinlogArchiveError('Native sandboxes require durable application storage')
    with service._semantic_lock:
        jobs = getattr(service, 'mysql_sandbox_jobs', None)
        if jobs is None:
            root = current_app.config.get('CDEADMIN_MYSQL_SANDBOX_JOB_ROOT') or str(store.path.parent / 'mysql-sandbox-jobs')
            jobs = service.mysql_sandbox_jobs = SandboxJobs(str(store.path) + '.mysql-sandboxes', root)
            atexit.register(jobs.close)
    default = current_app.config.get('CDEADMIN_MYSQL_SANDBOX_ROOT') or str(store.path.parent / 'mysql-sandboxes')
    configured = current_app.config.get('CDEADMIN_MYSQL_SANDBOX_DIRECTORIES') or [default]
    if not isinstance(configured, (list, tuple)) or any(not isinstance(item, str) or not Path(item).is_absolute() for item in configured):
        raise native.BinlogArchiveError('Configure absolute execution-host sandbox base directories')
    directories = [str(Path(item).resolve()) for item in configured]
    # Create only the application's default managed directory. Operator-selected
    # additional directories must already exist, as required by native Shell.
    if configured == [default]: Path(default).mkdir(mode=0o700, parents=True, exist_ok=True)
    return jobs, owner, server.endpoint_profile.id, provider.client, directories


def action(service, server, operation, request):
    if not isinstance(request, dict): raise native.BinlogArchiveError('Select a native sandbox request')
    jobs, owner, endpoint, client, directories = authority(service, server)
    if operation == 'catalog' and not request:
        return {'version': '9.7.0', 'methods': native.METHODS, 'sandbox_directories': directories,
                'execution_scope': 'ScratchRobin application execution host',
                'tools': client._tool_runner.available(), 'deploy_options': sorted(native.DEPLOY_OPTIONS)}
    if operation == 'list' and not set(request) - {'offset', 'limit'}: return jobs.list(owner, endpoint, **request)
    if operation in {'status', 'cancel'} and set(request) == {'job_id'}:
        return (jobs.get if operation == 'status' else jobs.cancel)(request['job_id'], owner, endpoint)
    secret = None
    if operation in {'review', 'inspect'} and set(request) == {'options'}:
        selected = native.options(request['options']); record = None
    elif operation == 'start':
        request = dict(request); secret = request.pop('sandbox_secret', None)
        record = jobs.load(request.get('job_id'), owner, endpoint)
        if record['state'] != 'reviewed': return jobs.start(request, owner, endpoint, {}, None)
        selected = record['options']
        needs_secret = selected['operation'] in {'deploy', 'stop'}
        if needs_secret != (secret is not None) or secret is not None and (
                not isinstance(secret, dict) or set(secret) != {'password'} or not isinstance(secret['password'], str) or
                len(secret['password'].encode('utf8')) > 1024 * 1024):
            raise native.BinlogArchiveError('Supply the native root password separately at sandbox deployment or stop dispatch')
    elif operation in {'reconcile', 'acknowledge'} and set(request) == (
            {'job_id'} if operation == 'reconcile' else {'job_id', 'observation_digest', 'sandbox_confirmation'}):
        record = jobs.load(request['job_id'], owner, endpoint); selected = record['options']
    else: raise native.BinlogArchiveError('Select a native sandbox lifecycle action')
    if selected['sandbox_directory'] not in directories:
        raise native.BinlogArchiveError('Select an explicitly admitted execution-host sandbox base directory')
    workspace = jobs.prepare_scope(owner, endpoint)
    observed = native.observe(client, selected, workspace)
    if operation == 'inspect': return {**observed, 'native_mutation_dispatched': False}
    if operation in {'reconcile', 'acknowledge'}:
        if observed['identity'] != record['source']: raise native.BinlogArchiveError('Sandbox observation reached another execution host or target')
        return jobs.reconcile_state(record, observed) if operation == 'reconcile' else jobs.acknowledge(record, observed, request)
    native.admit(selected, observed)
    program = native.program(client, workspace, selected)
    configuration = digest({'directories': directories, 'root': str(jobs.root),
        'adapter_sha256': hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest()})
    if operation == 'review': return jobs.review(owner, endpoint, selected, observed, configuration, program)
    if observed['state'] != record['source_state']: raise native.BinlogArchiveError('Sandbox state changed after review; prepare another review')
    transport = SandboxTransport(client, SecretLease(native.canonical(secret or {}).encode('utf8')))
    return jobs.start(request, owner, endpoint, {'configuration': configuration, 'source': observed['identity'], 'program': program}, transport)

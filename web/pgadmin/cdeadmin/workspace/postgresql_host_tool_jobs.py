"""Durable host utility jobs with one-use reviews and process-only finality."""
from pathlib import Path
import os
import json
import socket
import shutil
import threading
import time

from .mysql_binlog_jobs import MySQLBinlogJobs, DurableCancellation
from ..operations.fileio import exclusive_file_lock, private_file, publish_private_file, private_directory
from ..providers.postgresql.host_tools import digest
from ..providers.postgresql.continuity import ContinuityError


class PostgreSQLHostToolJobs(MySQLBinlogJobs):
    operation = 'postgresql_native_host_tool'
    review_warnings = (
        'Runs a native utility on the application host, not the registered database server or a borrowed SQL session.',
        'Local process return, native success, postcondition readback and process cleanup are separate facts. No automatic replay after interruption.',
        'Host grants and snapshots are not an atomic external-writer/start fence. Offline operations require separately controlled quiescence.')

    def update(self, record, **values):
        # One native dispatch per job: independently confirmed termination is
        # monotonic, even when cancellation races a worker's exception write.
        with self.store(record['job_id']) as store:
            def change(state):
                current = self.record(state, record['job_id'], record['owner'], record['endpoint_id'])
                if current.get('native_process_termination_confirmed') is True:
                    values['native_process_termination_confirmed'] = True
                current.update(values, updated_at=time.time())
            store.change(change)

    def reconcile(self, job_id, owner, endpoint):
        record = self.load(job_id, owner, endpoint)
        if record['program']['execution_host']['hostname'] != socket.gethostname():
            raise ContinuityError('Reconcile native utility cleanup on its original application host')
        with self._maps_lock:
            known = self.workers.get(job_id)
        if known and known[0].is_alive():
            raise ContinuityError('Cancel and wait for the native utility worker before reconciliation')
        if record.get('durable_tool') and record.get('native_process_termination_confirmed') is not True:
            self.observe_utility(record)
        lock, lease = lease_paths(self, record)
        descriptor = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            with exclusive_file_lock(descriptor, blocking=False):
                if lease.exists() and json.loads(lease.read_text()).get('job_id') != job_id:
                    raise ContinuityError('This native resource lease belongs to a different job')
                release_lease(self, record, lease)
        finally:
            os.close(descriptor)
        return self.get(job_id, owner, endpoint)

    def run(self, record, transport, signal):
        cancel = DurableCancellation(self, record, signal)
        try:
            self.update(record, state='active', native_dispatch_admitted=False)
            result = transport.execute(record, self.directory(record), cancel,
                                       lambda value: self.progress(record, value))
            observed = result['native']['process_observation']
            stopped = observed.get('cleanup_confirmed') is True
            current = self.load(record['job_id'], record['owner'], record['endpoint_id'])
            complete = result['report_complete'] and result['verification_complete'] and current.get('native_temporary_cleanup_confirmed') is True and current.get('host_resource_lease_released') is True
            self.update(record, state=('completed' if result['native_success'] and complete else
                        'partial' if result['native_success'] else
                        'cancelled' if cancel.is_set() else 'failed') if stopped else 'unknown',
                        result=result, native_process_termination_confirmed=stopped,
                        finished_at=time.time())
        except BaseException as error:
            current = self.load(record['job_id'], record['owner'], record['endpoint_id'])
            observed = getattr(error, 'process_observation', None)
            process = (observed or {}).get('process_observation', {})
            dispatched = current.get('native_dispatch_admitted') is True
            self.update(record, state='unknown' if dispatched else 'cancelled' if cancel.is_set() else 'not_dispatched',
                        error_type=type(error).__name__,
                        error_message=str(error) if isinstance(error, ContinuityError) else None,
                        tool_observation=observed, native_process_termination_confirmed=(
                            True if current.get('native_process_termination_confirmed') is True else process.get('cleanup_confirmed')),
                        finished_at=time.time(), automatic_retry=False)
        finally:
            transport.close()
            with self._maps_lock:
                known = self.workers.get(record['job_id'])
                if known and known[0] is threading.current_thread():
                    self.workers.pop(record['job_id'], None)


def lease_paths(jobs, record):
    root = jobs.root / '.host-tool-locks'
    root.mkdir(parents=True, exist_ok=True, mode=0o700);private_directory(root)
    scope = (
        record['source'].get('cluster_path')
        or record['source'].get('target_pgdata')
        or record['source'].get('archive_path')
        or record['source'].get('new_datadir')
        or 'host-diagnostics'
    )
    key = digest(scope)
    return root / (key + '.lock'), root / (key + '.json')


def cleanup_temporary(jobs, record):
    temporary = record.get('native_temporary')
    if temporary is None:
        return True
    if record['program']['execution_host']['hostname'] != socket.gethostname():
        return False
    path = Path(temporary['path'])
    if not path.exists() and not path.is_symlink():
        return True
    try:
        from ..providers.postgresql.host_tools import exact_path, identity
        exact_path(str(path), True)
        facts = identity(path)
        marker = path / '.scratchrobin-host-tool'
        if facts['device'] != temporary['device'] or facts['inode'] != temporary['inode'] or marker.is_symlink() or marker.stat().st_size != len(record['job_id']) or marker.read_bytes() != record['job_id'].encode('ascii'):
            return False
        shutil.rmtree(path)
        return True
    except OSError:
        return False


def release_lease(jobs, record, path):
    current = jobs.load(record['job_id'], record['owner'], record['endpoint_id'])
    stopped = current.get('native_process_termination_confirmed') is True or not current.get('native_dispatch_admitted')
    if not stopped:
        jobs.update(record, host_resource_lease_released=False, native_temporary_cleanup_confirmed=False)
        return False
    cleaned = cleanup_temporary(jobs, current)
    if path.exists():
        if path.is_symlink() or json.loads(path.read_text()).get('job_id') != record['job_id']:
            raise ContinuityError('Native host resource lease changed')
        path.unlink()
    jobs.update(record, host_resource_lease_released=True, native_temporary_cleanup_confirmed=cleaned)
    return cleaned


class HostToolTransport:
    def __init__(self, jobs, tools, refresh):
        self.jobs, self.tools, self.refresh = jobs, tools, refresh

    def execute(self, record, workspace, cancel, progress):
        lock, lease = lease_paths(self.jobs, record)
        descriptor = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            with exclusive_file_lock(descriptor, blocking=False):
                if lease.exists():
                    raise ContinuityError('An earlier native host job requires confirmed process cleanup and lease reconciliation')
                publish_private_file(lease, json.dumps({'job_id': record['job_id']}).encode('ascii'))
                try:
                    if cancel.is_set():
                        raise InterruptedError('Native host utility cancelled before dispatch')
                    source, program, configuration = self.refresh()
                    if (source, program, configuration) != (record['source'], record['program'], record['configuration']):
                        raise ContinuityError('Native host target, grant, runtime or configuration changed; review again')
                    def admitted(temporary=None):
                        if temporary is not None:
                            self.jobs.update(record, native_temporary=temporary)
                        else:
                            self.jobs.update(record, native_dispatch_admitted=True, native_dispatch_at=time.time())
                    result = self.tools.execute(record['options']['operation'], record['options']['draft'],
                                                source, workspace, cancel, progress, admitted)
                    self.jobs.update(record, native_returned=True,
                                     native_process_termination_confirmed=result['native']['process_observation'].get('cleanup_confirmed'))
                    if result['native']['executable_sha256'] != program['executable_sha256']:
                        raise ContinuityError('Native executable changed during dispatch; inspect the unknown outcome')
                    return result
                except BaseException as error:
                    observed = getattr(error, 'process_observation', None)
                    if observed and observed.get('process_observation', {}).get('cleanup_confirmed') is True:
                        self.jobs.update(record, native_process_termination_confirmed=True)
                    raise
                finally:
                    release_lease(self.jobs, record, lease)
        finally:
            os.close(descriptor)

    def close(self):
        pass

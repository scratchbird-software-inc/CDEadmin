"""Durable instance restore outcomes with shared replay/restore target fences."""
import threading
import time

from ..providers.mysql_family import mysql_instance_dumps as dumps
from ..providers.mysql_family import mysql_instance_restores as native
from ..providers.mysql_family.mysql_binlog_archives import stage_continuation
from .mysql_binlog_jobs import MySQLBinlogJobs, DurableCancellation, digest
from .mysql_binlog_replay_jobs import MySQLBinlogReplayJobs


class InstanceRestoreJobs(MySQLBinlogReplayJobs):
    operation = 'mysql_full_instance_logical_restore'
    review_warnings = (
        'Restore changes the separately confirmed target instance. Native DDL, data, account and GTID changes can commit independently; cancellation does not undo them.',
        'Use an exclusive target maintenance window. Native GTID and identity checks do not freeze unrelated external writers.',
        'The original native reply, target inspection, recovered data/definitions and production cutover are separate facts. An unknown operation is never automatically repeated.',
    )

    def public(self, record):
        result = MySQLBinlogJobs.public(self, record)
        result['target'] = result.pop('source')
        result['source_backup'] = record['source_state']['input_reference']
        result['native_load_outcome'] = record.get('native_load_outcome', 'unknown' if record.get('native_load_may_have_dispatched') else 'not_dispatched')
        for field in ('data_recovery_verified', 'definition_recovery_verified', 'production_cutover_verified'):
            result[field] = False
        return result

    def fence_store(self, target_uuid):
        return self.replay_jobs.fence_store(target_uuid)

    def run(self, record, transport, signal):
        cancel = DurableCancellation(self, record, signal)
        dispatched = False; result = None
        try:
            self.update(record, state='active', phase='verifying_input', native_load_outcome='not_dispatched')
            def boundary():
                nonlocal dispatched
                if cancel.is_set(): raise InterruptedError('Instance restore cancelled before native dispatch')
                self.update(record, phase='native_dispatch', native_load_outcome='unknown', native_load_may_have_dispatched=True)
                dispatched = True
            result = transport.execute(record, self.directory(record), cancel,
                lambda value: self.progress(record, value), boundary)
            control = result.get('control') or {}; tool = result['tool']
            stopped = tool['process_observation'].get('cleanup_confirmed') is True
            returned = (control.get('native_load_invoked') is True and control.get('native_load_returned') is True and
                        control.get('stage') == 'returned' and control.get('native_error') is None)
            not_dispatched = control.get('native_load_invoked') is False
            outcome = 'returned' if returned else 'not_dispatched' if not_dispatched else 'unknown'
            self.update(record, state='native_load_returned' if returned else 'not_dispatched' if not_dispatched and stopped else 'unknown',
                phase='finished', result=result, native_load_outcome=outcome,
                native_process_termination_confirmed=stopped, finished_at=time.time(),
                native_error=control.get('native_error'))
            if outcome != 'unknown' and stopped: self.release_fence(record)
        except BaseException as error:
            control = getattr(error, 'control', None) or (result or {}).get('control') or {}
            observed = getattr(error, 'observation', None) or getattr(error, 'process_observation', None) or (result or {}).get('tool')
            if isinstance(observed, dict): observed = {key: value for key, value in observed.items() if key not in {'stdout', 'stderr'}}
            stopped = (observed or {}).get('process_observation', {}).get('cleanup_confirmed')
            not_dispatched = not dispatched or control.get('native_load_invoked') is False or getattr(error, 'native_preparation_refused', False)
            returned = (control.get('native_load_invoked') is True and control.get('native_load_returned') is True and
                        control.get('stage') == 'returned' and control.get('native_error') is None)
            outcome = 'returned' if returned else 'not_dispatched' if not_dispatched else 'unknown'
            self.update(record, state='native_returned_unverified' if returned else 'cancelled' if not_dispatched and cancel.is_set() else 'not_dispatched' if not_dispatched else 'unknown',
                native_load_outcome=outcome, native_control=control or None, tool_observation=observed,
                native_process_termination_confirmed=True if not dispatched else stopped,
                native_error=control.get('native_error'), error_type=type(error).__name__, finished_at=time.time(),
                **({'result': result} if result is not None else {}))
            if outcome != 'unknown' and (not dispatched or stopped is True): self.release_fence(record)
        finally:
            try: transport.close()
            finally:
                with self._maps_lock:
                    worker = self.workers.get(record['job_id'])
                    if worker and worker[0] is threading.current_thread(): self.workers.pop(record['job_id'], None)


class InstanceRestoreTransport:
    def __init__(self, client, route, credentials, connection, source_directory, source_identity):
        self.client, self.route, self.credentials, self.connection = client, route, credentials, connection
        self.source_directory, self.source_identity = source_directory, source_identity

    def close(self):
        try:
            if self.credentials is not None:
                owned = self.credentials; self.credentials = None; owned.close()
        finally:
            if self.connection is not None:
                owned = self.connection; self.connection = None; self.client._discard_failed_session(owned)

    def execute(self, record, directory, cancel, progress, boundary):
        reference = record['source_state']['input_reference']; staged = directory / 'input'
        result = None
        artifact = dumps.verify(self.source_directory, self.source_identity, cancel=cancel)
        if digest(artifact) != reference['artifact_digest']:
            raise native.BinlogArchiveError('Native instance backup changed after restore review')
        if cancel.is_set(): raise InterruptedError('Instance restore cancelled before staging')
        stage_continuation(self.source_directory, staged, artifact, self.source_identity, cancel=cancel, verify_artifact=dumps.verify)
        if native.admission(self.connection, artifact, record['options']) != record['source_state']['target']:
            raise native.BinlogArchiveError('Native instance target changed after review; prepare a new restore review')
        result = native.run_load(self.client, self.route, self.credentials, staged, record['source'],
            record['source_state']['target']['state'], record['options'], directory, record['program'],
            cancel=cancel, progress=progress, boundary=boundary)
        try:
            result['target_observation'] = native.capture(self.connection)
        except Exception as error:
            result['target_observation'] = {'available': False, 'error_type': type(error).__name__}
        return result

"""Independent acceptance jobs never issue a data/DDL/account restore."""
import threading
import time

from ..providers.mysql_family import mysql_instance_acceptance as native
from ..providers.mysql_family import mysql_instance_dumps as dumps
from ..providers.mysql_family import mysql_instance_restores as targets
from ..providers.mysql_family.mysql_binlog_archives import stage_continuation
from .mysql_binlog_jobs import MySQLBinlogJobs, DurableCancellation, digest
from .mysql_binlog_replay_jobs import MySQLBinlogReplayJobs


class InstanceAcceptanceJobs(MySQLBinlogReplayJobs):
    operation = 'mysql_instance_dump_acceptance'
    remote_database_mutation = False
    review_warnings = (
        'Independent acceptance acquires an instance backup lock and a server-wide read lock. Writes can pause for the entire row-count, checksum and definition observation.',
        'The native utility checks dumped data and re-exports definitions. It never loads DDL, data, indexes or accounts and never updates GTIDs.',
        'Only exported dump surfaces are accepted. Source exclusions, physical recovery, subsequent log replay and production cutover retain separate scopes.',
    )

    def public(self, record):
        value = MySQLBinlogJobs.public(self, record)
        value['target'] = value.pop('source')
        value['source_backup'] = record['source_state']['input_reference']
        value['acceptance_outcome'] = record.get('acceptance_outcome', 'not_observed')
        value['restore_issued'] = False
        value['production_cutover_verified'] = False
        return value

    def fence_store(self, target_uuid):
        return self.replay_jobs.fence_store(target_uuid)

    def run(self, record, transport, signal):
        cancel = DurableCancellation(self, record, signal); dispatched = False; result = None
        try:
            self.update(record, state='active', phase='verifying_input')
            def boundary():
                nonlocal dispatched
                if cancel.is_set(): raise InterruptedError('Acceptance cancelled before native checks')
                self.update(record, phase='native_checks', native_checks_may_have_started=True)
                dispatched = True
            result = transport.execute(record, self.directory(record), cancel,
                lambda value: self.update(record, progress=value), boundary)
            stopped = result['tool']['process_observation'].get('cleanup_confirmed') is True
            accepted = result['selected_dump_surfaces_verified']
            different = any(result.get(key, {}).get('matched') is False for key in ('data', 'definitions', 'accounts'))
            self.update(record, state='unknown' if not stopped else 'cancelled' if cancel.is_set() and not result['native_checks_returned'] else 'verification_observed', result=result,
                acceptance_outcome='matched' if accepted else 'not_matched' if different else 'unconfirmed',
                native_load_outcome='not_dispatched', native_process_termination_confirmed=stopped,
                recovery_fence_release_confirmed=result.get('server_locks_released') is True,
                finished_at=time.time())
            if stopped and result.get('server_locks_released') is True: self.release_fence(record)
        except BaseException as error:
            result = getattr(error, 'native_check_result', None) or result
            observed = getattr(error, 'observation', None) or getattr(error, 'process_observation', None) or (result or {}).get('tool')
            if isinstance(observed, dict): observed = {key: value for key, value in observed.items() if key not in {'stdout', 'stderr'}}
            stopped = (observed or {}).get('process_observation', {}).get('cleanup_confirmed')
            locks_safe = result is None or result.get('server_locks_released') is True or not any(
                result.get(key) for key in ('server_read_lock_acquired', 'instance_backup_lock_acquired'))
            self.update(record, state='unknown' if dispatched and stopped is not True else 'cancelled' if cancel.is_set() else 'failed',
                acceptance_outcome='unconfirmed', native_load_outcome='not_dispatched',
                native_process_termination_confirmed=stopped if dispatched else True,
                recovery_fence_release_confirmed=locks_safe,
                error_type=type(error).__name__, native_error_code=getattr(error, 'errno', None),
                tool_observation=observed, finished_at=time.time(), **({'result': result} if result is not None else {}))
            if (not dispatched or stopped is True) and locks_safe:
                self.release_fence(record)
        finally:
            try: transport.close()
            finally:
                with self._maps_lock:
                    worker = self.workers.get(record['job_id'])
                    if worker and worker[0] is threading.current_thread(): self.workers.pop(record['job_id'], None)


class InstanceAcceptanceTransport:
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
        artifact = dumps.verify(self.source_directory, self.source_identity, cancel=cancel)
        if digest(artifact) != record['source_state']['input_reference']['artifact_digest']:
            raise native.BinlogArchiveError('Native dump changed after acceptance review')
        staged = directory / 'input'
        stage_continuation(self.source_directory, staged, artifact, self.source_identity, cancel=cancel, verify_artifact=dumps.verify)
        selected = native.scopes(staged, artifact)
        if selected != record['source_state']['scopes']:
            raise native.BinlogArchiveError('Native dump acceptance coverage changed')
        result = {'selected_dump_surfaces_verified': False, 'restore_issued': False, 'production_cutover_verified': False,
            'server_read_lock_acquired': False, 'instance_backup_lock_acquired': False, 'server_locks_released': False,
            'scope': 'Exported table data with full row counts, exact selected-schema object SQL and exported account/role/grant SQL; not physical recovery, later log replay or production cutover'}
        cursor = self.connection.cursor()
        try:
            cursor.execute('SET SESSION lock_wait_timeout=5')
            cursor.execute('LOCK INSTANCE FOR BACKUP'); result['instance_backup_lock_acquired'] = True
            cursor.execute('FLUSH TABLES WITH READ LOCK'); result['server_read_lock_acquired'] = True
            before = targets.capture(self.connection)
            if before != record['source_state']['target']:
                raise native.BinlogArchiveError('Native acceptance target changed after review')
            result['row_counts'] = native.table_counts(cursor, selected)
            if cancel.is_set(): raise InterruptedError('Acceptance cancelled before native checks')
            observed = native.run_checks(self.client, self.route, self.credentials, staged, directory / 'target-definitions',
                record['source'], selected, before['state'], directory, record['program'], record['options'],
                cancel=cancel, progress=progress, boundary=boundary)
            result.update(observed)
            control = result.get('control') or {}; tool = result['tool']
            qualified = (tool['return_code'] == 0 and tool.get('stdout_truncated') is False and
                tool['process_observation'].get('cleanup_confirmed') is True and control.get('stage') == 'returned')
            result['native_checks_returned'] = qualified
            checksum_difference = qualified and any(isinstance(error, dict) and error.get('stage') == 'checksums' and
                error.get('code') == 53031 for error in control.get('errors', []))
            # The pinned native implementation identifies a checksum mismatch
            # with 53031. Privilege, launch and cancelled checks stay unconfirmed.
            data_match = (True if qualified and control.get('checksum_returned') is True and result['row_counts']['matched'] is True
                          else False if result['row_counts']['matched'] is False or checksum_difference else None)
            result['data'] = {'requested': selected['data_requested'], 'matched': data_match if selected['data_requested'] else None}
            for key in ('definitions', 'accounts'):
                result[key] = {'requested': selected[key + '_requested'], 'matched': None}
            if qualified and control.get('definition_dump_returned') is True:
                target_artifact = dumps.verify(directory / 'target-definitions', record['source'], cancel=cancel)
                result.update(native.definitions(staged, directory / 'target-definitions', selected, artifact, target_artifact))
            result['target_observation'] = targets.capture(self.connection)
            result['target_unchanged'] = before == result['target_observation']
            native.unchanged(staged, artifact)
            result['artifact_unchanged'] = True
            result['selected_dump_surfaces_verified'] = bool(qualified and result['target_unchanged'] and
                all(result[key]['matched'] is True for key in ('data', 'definitions', 'accounts') if result[key]['requested']))
            return result
        except BaseException as error:
            prior = getattr(error, 'native_check_result', None)
            if prior: result.update(prior)
            error.native_check_result = result
            raise
        finally:
            failures = []
            for acquired, statement in (('server_read_lock_acquired', 'UNLOCK TABLES'), ('instance_backup_lock_acquired', 'UNLOCK INSTANCE')):
                if not result[acquired]: continue
                try: cursor.execute(statement)
                except Exception as error: failures.append({'operation': statement, 'error_type': type(error).__name__})
            result['server_locks_released'] = not failures
            try: cursor.close()
            except Exception as error: failures.append({'operation': 'close private cursor', 'error_type': type(error).__name__})
            if failures: result['lock_cleanup_failures'] = failures

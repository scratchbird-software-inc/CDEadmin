"""Full-instance backup jobs keep native replies and file acceptance separate."""
import threading
import time
import re
import socket

from ..providers.mysql_family import mysql_instance_dumps as native
from ..providers.mysql_family.mysql_binlog_archives import seal
from .mysql_binlog_jobs import MySQLBinlogJobs, DurableCancellation, digest


class InstanceBackupJobs(MySQLBinlogJobs):
    operation = 'mysql_full_instance_logical_backup'
    native_verify = staticmethod(native.verify)
    review_warnings = (
        'Native instance dumping can pause source writes while establishing its snapshot. The utility owns consistency and account visibility checks.',
        'Optional system-table checkpoints hold a server-wide read lock throughout the native dump; they compare native state without importing system tables.',
        'Account definitions can contain authentication material. Backup files stay in the private application-host job directory.',
        'Native completion, sealed backup metadata and successful database recovery have separate receipts. Cancellation can leave partial output and does not restart this job.',
    )

    def public(self, record):
        result = super().public(record)
        artifact = (result.get('result') or {}).get('artifact')
        if artifact is not None:
            artifact.pop('native_log_count', None)
        result['native_dump_acknowledged'] = record.get('native_dump_acknowledged', False)
        result['data_recovery_verified'] = False
        result['production_cutover_verified'] = False
        return result

    def run(self, record, transport, signal):
        cancel = DurableCancellation(self, record, signal)
        result = None
        try:
            self.update(record, state='active', native_dump_acknowledged=False)
            def progress(value):
                fields = {'progress': value}
                if isinstance(value, dict) and value.get('backup_id'):
                    fields['backup_protection_id'] = value['backup_id']
                if isinstance(value, dict) and value.get('durable_tool'):
                    fields['durable_tool'] = value['durable_tool']
                if isinstance(value,dict) and value.get('server_lock_owner'):
                    fields['server_lock_owner']=value['server_lock_owner']
                self.update(record, **fields)
            result = transport.execute(record, self.directory(record), cancel, progress)
            self.update(record, state='completed', result=result,
                native_dump_acknowledged=True, native_process_termination_confirmed=True, finished_at=time.time())
        except BaseException as error:
            observed = getattr(error, 'observation', None) or getattr(error, 'process_observation', None)
            if observed is None and result is not None:
                observed = result['tool']
            if isinstance(observed, dict):
                observed = {key: value for key, value in observed.items() if key not in {'stdout', 'stderr'}}
            stopped = (observed or {}).get('process_observation', {}).get('cleanup_confirmed')
            acknowledged = getattr(error, 'native_dump_acknowledged', False) is True or bool(result and result.get('native_dump_acknowledged'))
            self.update(record, state='native_returned_unverified' if acknowledged else 'unknown' if stopped is False else
                'cancelled' if cancel.is_set() or isinstance(error, InterruptedError) else 'failed',
                native_dump_acknowledged=acknowledged, native_control=getattr(error, 'native_control', None) or (result or {}).get('native_control'),
                native_error=getattr(error, 'native_error', None),
                native_process_termination_confirmed=stopped, tool_observation=observed,
                private_script_cleanup=getattr(error, 'private_script_cleanup', None),
                error_type=type(error).__name__, finished_at=time.time(), automatic_retry=False,
                **({'result': result} if result is not None else {}))
        finally:
            try: transport.close()
            finally:
                with self._maps_lock:
                    known = self.workers.get(record['job_id'])
                    if known and known[0] is threading.current_thread():
                        self.workers.pop(record['job_id'], None)

    def reconcile(self, job_id, owner, endpoint):
        record = self.load(job_id, owner, endpoint)
        with self._maps_lock:
            known = self.workers.get(job_id)
            if known and known[0].is_alive():
                raise native.BinlogArchiveError('The native instance backup worker is still active')
        self.observe_utility(record)
        record = self.load(job_id, owner, endpoint)
        if record.get('native_process_termination_confirmed') is not True:
            raise native.BinlogArchiveError('Confirm native utility termination before accepting backup files')
        directory = self.directory(record)
        if record['options'].get('system_state_tables'):
            from ..providers.mysql_family import mysql_system_state as system
            archive=directory/('archive' if (directory/'archive').exists() else 'archive.incoming')
            checkpoint=system.read(archive,record['source']['server_uuid'])
            if [row['table'] for row in checkpoint['tables']]!=record['options']['system_state_tables']:
                raise native.BinlogArchiveError('Original reviewed system checkpoint coverage is unavailable')
        if not (directory / 'archive').exists() and (directory / 'archive.incoming').exists():
            verified = native.verify(directory / 'archive.incoming', record['source'])
            seal(directory / 'archive.incoming', directory / 'archive')
            if digest(native.verify(directory / 'archive', record['source'])) != digest(verified):
                raise native.BinlogArchiveError('Instance backup changed during explicit file reconciliation')
        super().reconcile(job_id, owner, endpoint)
        current = self.load(job_id, owner, endpoint)
        backup_id = current.get('backup_protection_id')
        if backup_id:
            from .mysql_backup_protection import Ticket
            from ..providers.mysql_family.mysql_backup_events import document
            artifact = current['result']['artifact']; hashes = {row['path']: row['sha256'] for row in artifact['files']}
            try:
                ticket = Ticket(self.backup_protection.scoped(owner, endpoint), backup_id)
                protection = ticket.completed(document(directory / 'archive/@.json', hashes['@.json']),
                    document(directory / 'archive/@.done.json', hashes['@.done.json']),
                    {'artifact_manifest': artifact['files'], 'artifact_total_bytes': artifact['total_bytes']},
                    acknowledged=record.get('native_dump_acknowledged') is True)
            except Exception as error:
                protection = {'backup_id': backup_id, 'state': 'protection_unconfirmed', 'error_type': type(error).__name__,
                              'native_backup_acknowledgement_unchanged': True}
            self.update(current, result={**current['result'], 'archive_backup_protection': protection})
        return self.get(job_id, owner, endpoint)

    def cleanup_script(self, job_id, owner, endpoint):
        from ..providers.mysql_family.mysql_binlog_archives import _file
        from .mysql_archive_retention import directory_identity
        with self._maps_lock:
            known = self.workers.get(job_id)
            if known and known[0].is_alive():
                raise native.BinlogArchiveError('Wait for the native backup worker before cleaning its private script')
        with self.store(job_id) as store:
            record = self.record(store.read(), job_id, owner, endpoint)
            cleanup = (record.get('result') or {}).get('private_script_cleanup') or record.get('private_script_cleanup')
            if not cleanup or cleanup.get('complete') is True:
                return self.public(record)
            if record.get('native_process_termination_confirmed') is not True or cleanup.get('execution_hostname') != socket.gethostname():
                raise native.BinlogArchiveError('Confirmed utility termination and its recorded execution host are required for private-script cleanup')
            name = cleanup.get('relative_file')
            if not isinstance(name, str) or not re.fullmatch(r'native-instance-dump-[0-9a-f]{32}\.js', name):
                raise native.BinlogArchiveError('Private backup script identity is unavailable')
            directory = self.directory(record); original = directory_identity(directory); path = directory / name
            if path.exists() or path.is_symlink():
                if _file(path, None)['sha256'] != cleanup['sha256'] or directory_identity(directory) != original:
                    raise native.BinlogArchiveError('Private backup script changed; cleanup refused')
                path.unlink()
            if path.exists() or path.is_symlink():
                raise native.BinlogArchiveError('Private backup script removal is unconfirmed')
            completed = {**cleanup, 'complete': True, 'absence_observed_at': time.time()}
            def change(state):
                current = self.record(state, job_id, owner, endpoint)
                current['private_script_cleanup'] = completed
                if (current.get('result') or {}).get('private_script_cleanup'):
                    current['result']['private_script_cleanup'] = completed
            store.change(change)
            return self.public(self.record(store.read(), job_id, owner, endpoint))


class InstanceBackupTransport:
    def __init__(self, client, route, credentials, protection):
        self.client, self.route, self.credentials, self.protection = client, route, credentials, protection

    def close(self):
        try:
            if self.credentials is not None:
                self.credentials.close(); self.credentials = None
        finally:
            connection=getattr(self,'system_connection',None)
            if connection is not None:
                self.system_connection=None;self.client._discard_failed_session(connection)

    def execute(self, record, directory, cancel, progress):
        result = ticket = None
        try:
            if cancel.is_set():
                raise InterruptedError('Instance backup cancelled before native dispatch')
            ticket = self.protection.begin(record['source'], 'MySQL instance', str(directory / 'archive'),
                {**record['options'], '_instance_scope': True, '_instance_job_id': record['job_id']})
            progress({'stage': 'native_dump', 'backup_id': ticket.backup_id})
            if record['options'].get('system_state_tables'):
                result=self.system_dump(record,directory,cancel,progress)
            else:
                result = native.run_dump(self.client, self.route, self.credentials, record['source'], record['options'],
                    directory / 'archive.incoming', directory, record['program'], cancel=cancel, progress=progress)
            progress({'stage': 'sealing_files', 'backup_id': ticket.backup_id, 'native_dump_acknowledged': True})
            seal(directory / 'archive.incoming', directory / 'archive', cancel=cancel)
            observed = native.verify(directory / 'archive', record['source'], cancel=cancel)
            if digest(observed) != digest(result['artifact']):
                raise native.BinlogArchiveError('Native instance backup changed while publishing its file receipt')
            result['artifact'] = observed
            from ..providers.mysql_family.mysql_backup_events import document
            try:
                hashes = {row['path']: row['sha256'] for row in observed['files']}
                protection = ticket.completed(document(directory / 'archive/@.json', hashes['@.json']), document(directory / 'archive/@.done.json', hashes['@.done.json']),
                    {'artifact_manifest': observed['files'], 'artifact_total_bytes': observed['total_bytes']})
            except Exception as error:
                try: ticket.update(state='protection_unconfirmed', native_dump_completion_acknowledged=True)
                except Exception: pass
                protection = {'backup_id': ticket.backup_id, 'state': 'protection_unconfirmed',
                              'error_type': type(error).__name__, 'native_backup_acknowledgement_unchanged': True}
            return {**result, 'archive_backup_protection': protection, 'remote_database_mutation': False}
        except BaseException as error:
            acknowledged = bool(result and result.get('native_dump_acknowledged')) or getattr(error, 'native_dump_acknowledged', False) is True
            if result is not None:
                error.observation = result['tool']; error.native_control = result['native_control']
            error.native_dump_acknowledged = acknowledged
            if ticket is not None:
                try: ticket.update(state='protection_unconfirmed' if acknowledged else 'unconfirmed_native_reply',
                                   native_dump_completion_acknowledged=acknowledged)
                except Exception: pass
            raise


    def system_dump(self,record,directory,cancel,progress):
        from ..providers.mysql_family import mysql_system_state as system
        from ..providers.mysql_family import mysql_acceptance_lock_owner as locks
        connection=self.system_connection;cursor=connection.cursor();acquired=[];result=None;failure=None
        try:
            owner=locks.acquire(connection,record['job_id'],record['source']['server_uuid'])
            progress({'server_lock_owner':owner})
            cursor.execute('SET SESSION lock_wait_timeout=5')
            for statement,release in [('LOCK INSTANCE FOR BACKUP','UNLOCK INSTANCE'),('FLUSH TABLES WITH READ LOCK','UNLOCK TABLES')]:
                cursor.execute(statement);acquired.append(release)
            expected=system.capture(connection,record['options']['system_state_tables'],cancel=cancel)
            if expected['source_uuid']!=record['source']['server_uuid']:
                raise native.BinlogArchiveError('System checkpoint reached another source')
            result=native.run_dump(self.client,self.route,self.credentials,record['source'],record['options'],
                directory/'archive.incoming',directory,record['program'],cancel=cancel,progress=progress)
            after=system.capture(connection,record['options']['system_state_tables'],cancel=cancel)
            if after!=expected:raise native.BinlogArchiveError('Native system tables changed during the expected dump')
            system.save(directory/'archive.incoming',expected)
            result['artifact']=native.verify(directory/'archive.incoming',record['source'],cancel=cancel)
            return result
        except BaseException as error:
            failure=error
            if result is not None:
                error.observation=result['tool'];error.native_dump_acknowledged=result.get('native_dump_acknowledged') is True
                error.native_control=result.get('native_control')
            raise
        finally:
            failures=[]
            for statement in reversed(acquired):
                try:cursor.execute(statement)
                except Exception as error:failures.append(type(error).__name__)
            try:cursor.close()
            except Exception as error:failures.append(type(error).__name__)
            if result is not None:result['system_source_locks_released']=not failures
            if failures and failure is None:
                error=native.BinlogArchiveError('Original system checkpoint lock release is unconfirmed')
                if result is not None:
                    error.observation=result['tool'];error.native_dump_acknowledged=result.get('native_dump_acknowledged') is True
                    error.native_control=result.get('native_control')
                raise error

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
        if record.get('native_process_termination_confirmed') is not True:
            raise native.BinlogArchiveError('Confirm native utility termination before accepting backup files')
        directory = self.directory(record)
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
        if self.credentials is not None:
            self.credentials.close(); self.credentials = None

    def execute(self, record, directory, cancel, progress):
        result = ticket = None
        try:
            if cancel.is_set():
                raise InterruptedError('Instance backup cancelled before native dispatch')
            ticket = self.protection.begin(record['source'], 'MySQL instance', str(directory / 'archive'),
                {**record['options'], '_instance_scope': True, '_instance_job_id': record['job_id']})
            progress({'stage': 'native_dump', 'backup_id': ticket.backup_id})
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

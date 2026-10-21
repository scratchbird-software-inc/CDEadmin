"""Separately scoped native reset receipts; reconciliation never replays SQL."""
import time

from ..providers.mysql_family import mysql_log_reset as native
from ..providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
from .mysql_log_purge import PurgeJobs, action as source_action


class ResetJobs(PurgeJobs):
    native_module = native
    selection_key = 'reset_selection'
    service_attribute = 'mysql_source_log_reset_jobs'
    root_setting = 'CDEADMIN_MYSQL_LOG_RESET_ROOT'
    root_name = 'mysql-source-log-reset-receipts'
    store_suffix = '.source-log-reset'
    operation = 'mysql_native_binary_logs_and_gtids_reset'
    review_warnings = (
        'Permanently removes ALL native binary logs, including the active file, and clears native GTID executed/purged history. This is not routine log retention.',
        'Use an exclusive maintenance window after checking backups, replicas and active archive receivers. Read-only and super-read-only do not protect against the native command. Native Group Replication and privilege refusals remain server decisions.',
        'This can break backup/log chains and replication assumptions. Application archives remain unchanged and are not automatically rebound to the new log generation. Backup and offline replica dependencies are not automatically discovered.',
        'Cancellation is a guarded native KILL QUERY request, not rollback. Lost replies remain unknown. Reconciliation cannot identify original log bytes from reused filenames, prove a generation epoch or authorize replay.',
    )

    def public(self, record):
        result = super().public(record)
        from .mysql_binlog_service import _public_capture
        selected = result['reset_selection']
        wide = _public_capture({'logs': selected['before_logs'], 'current': selected['before_current']})
        selected.update(before_logs=wide['logs'], before_current=wide['current'])
        return result

    def reconcile_source(self, record, observed):
        with self._maps_lock:
            known = self.workers.get(record['job_id'])
            if known and known[0].is_alive():
                raise BinlogArchiveError('The native log administration worker is still active')
        if observed['identity'] != record['source']:
            raise BinlogArchiveError('Native reconciliation reached another source or principal')
        self.update(record, reconciliation={'observed_at': time.time(), 'source': observed,
            'original_acknowledgement_unchanged': True, 'native_log_generation_attested': False,
            'filename_reuse_does_not_identify_original_log_files': True})
        return self.get(record['job_id'], record['owner'], record['endpoint_id'])


def action(service, server, archives, owner, endpoint, context, operation, request):
    return source_action(service, server, archives, owner, endpoint, context, operation, request, jobs_type=ResetJobs)

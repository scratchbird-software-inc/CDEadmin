"""Owner-bound recovery of a MariaDB receiver boundary from its sealed native archive."""
import heapq
import os
import stat

from ..providers.mysql_family.mariadb_archive_checkpoint import successor
from ..providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
from ..providers.mysql_family.continuous_binlog import ReceiverTransport
from .continuous_binlog_tails import stopped_parent
from .mysql_binlog_jobs import digest, identity


def parent(jobs, archives, job_id, owner, endpoint):
    return stopped_parent(jobs, archives, job_id, owner, endpoint)


def archived(archives, parent_record, archive_id):
    record = archives.load(archive_id, parent_record['owner'], parent_record['endpoint_id'])
    if (record['source'] != parent_record['source'] or
            (record.get('continuation') or {}).get('continuous_receiver_job_id') != parent_record['job_id']):
        raise BinlogArchiveError('Select a native MariaDB archive published by this receiver')
    if (record['state'] not in {'completed', 'artifact_verified'} or record.get('artifact_removed') or
            record.get('artifact_removal') or record.get('native_process_termination_confirmed') is not True):
        raise BinlogArchiveError('Select a retained verified MariaDB receiver archive with confirmed native cleanup')
    artifact = (record.get('result') or {}).get('artifact')
    if not isinstance(artifact, dict) or artifact.get('format') != 'mariadb-binlog@12.2.2':
        raise BinlogArchiveError('Select a verified native MariaDB 12.2.2 receiver archive')
    return record, artifact


def checkpoint(archives, parent_record, archive_id, captured, connection, *, verify=False, cancel=None):
    from .continuous_binlog_service import recollection_checkpoint
    lineage = recollection_checkpoint(parent_record, captured, connection, family='mariadb')
    record, artifact = archived(archives, parent_record, archive_id)
    directory = archives.directory(record) / 'archive'
    if verify:
        observed = archives.native_verify(directory, parent_record['source'], cancel=cancel)
        if digest(observed) != digest(artifact):
            raise BinlogArchiveError('Native MariaDB checkpoint archive bytes changed after sealing')
    boundary = successor(directory, artifact, parent_record['source'])
    if captured['status'] != 'available' or boundary['next_file'] not in {row['Log_name'] for row in captured['logs']}:
        raise BinlogArchiveError('The verified MariaDB archive successor is unavailable or purged; no later checkpoint is guessed')
    return {
        **boundary,
        'archive_job_id': record['job_id'],
        'archive_digest': digest(artifact),
        'receiver_job_id': parent_record['job_id'],
        'verification_required_before_dispatch': True,
        'native_gtid_baseline_checked': lineage['native_gtid_baseline_checked'],
        'unresolved_cursor_used': False,
        'parent_outcome_rewritten': False,
        'binary_log_epoch_verified': False,
        'database_recovery_verified': False,
        'complete_backup_log_chain_verified': False,
    }


def catalog(jobs, archives, record, request):
    if set(request) - {'job_id', 'after', 'limit'} or request.get('job_id') != record['job_id']:
        raise BinlogArchiveError('Select one MariaDB receiver checkpoint archive page')
    after, limit = request.get('after'), request.get('limit', 25)
    if after is not None:
        identity(after)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise BinlogArchiveError('Select a checkpoint archive page of at most 100 entries')
    index = jobs.directory(record) / 'snapshots'
    if index.is_symlink() or index.exists() and (
            index.resolve() != index or getattr(index.lstat(), 'st_file_attributes', 0) & 0x400):
        raise BinlogArchiveError('Receiver checkpoint index identity changed')
    names = []
    if index.is_dir():
        with os.scandir(index) as entries:
            names = heapq.nsmallest(
                limit + 1,
                (entry.name for entry in entries
                 if not entry.name.startswith('.') and (after is None or entry.name > after)),
            )
    rows = []
    for name in names[:limit]:
        identity(name)
        info = (index / name).lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise BinlogArchiveError('Receiver checkpoint index entry is invalid')
        try:
            selected, artifact = archived(archives, record, name)
        except BinlogArchiveError:
            rows.append({'job_id': name, 'available': False})
            continue
        rows.append({
            'job_id': name,
            'available': True,
            'end_at': artifact['end_at'],
            'created_at': selected['created_at'],
            'bytes': str(artifact['total_bytes']),
            'retention_pinned': bool(selected.get('retention_pinned')),
        })
    more = len(names) > limit
    return {
        'receiver_job_id': record['job_id'],
        'archives': rows,
        'more': more,
        'next_after': names[limit - 1] if more else None,
        'native_catalog_checked': False,
    }


class MariaDBArchiveCheckpointTransport(ReceiverTransport):
    def __init__(self, *args, receiver_jobs, checkpoint_parent, **kwargs):
        super().__init__(*args, **kwargs)
        self.receiver_jobs, self.checkpoint_parent = receiver_jobs, checkpoint_parent

    def execute(self, record, directory, cancel, progress):
        try:
            original = parent(
                self.receiver_jobs, self.archive_jobs, self.checkpoint_parent['job_id'],
                record['owner'], record['endpoint_id'],
            )
            progress({
                'stage': 'verifying_retained_archive_checkpoint',
                'archive_job_id': record['continuation']['archive_checkpoint']['archive_job_id'],
                'native_receiver_dispatched': False,
            })
            captured = self.native.capture(self.observer)
            verified = checkpoint(
                self.archive_jobs, original,
                record['continuation']['archive_checkpoint']['archive_job_id'],
                captured, self.observer, verify=True, cancel=cancel,
            )
            if (verified != record['continuation']['archive_checkpoint'] or
                    verified['next_file'] != record['options']['start_file']):
                raise BinlogArchiveError('The reviewed native MariaDB archive checkpoint changed; receiver dispatch refused')
            if cancel.is_set():
                raise InterruptedError('Native MariaDB archive checkpoint verification cancelled')
        except BaseException as error:
            error.observation = {'process_observation': {'cleanup_confirmed': True, 'native_receiver_dispatched': False}}
            raise
        progress({
            'stage': 'retained_archive_checkpoint_verified',
            'archive_checkpoint_verified': True,
            'archive_job_id': verified['archive_job_id'],
            'native_receiver_dispatched': False,
        })
        result = super().execute(record, directory, cancel, progress)
        return {
            **result,
            'archive_checkpoint_verified_before_dispatch': True,
            'recovered_archive_checkpoint': verified,
            'parent_outcome_rewritten': False,
        }

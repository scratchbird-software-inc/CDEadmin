"""Reviewed MySQL archive retention and restart-safe local file removal.

Native log purging and database recovery are deliberately separate operations.
Each removal first detaches its exact owned directory under a durable intent.
An interrupted deletion can only resume that intent, never a new retention scan.
"""
from copy import deepcopy
import hashlib
import heapq
import os
from pathlib import Path
import shutil
import socket
import stat
import threading
import time
import uuid

from ..operations.fileio import durable_replace
from ..providers.mysql_family.mysql_binlog_archives import BinlogArchiveError
from .mysql_binlog_jobs import ACTIVE, DurableCancellation, MySQLBinlogJobs, digest, identity

DIRECTORIES = ('archive', 'archive.incoming', 'continuation', 'verification-load')
RETAINED = {'completed', 'artifact_verified'}


def directory_identity(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if (not stat.S_ISDIR(info.st_mode) or path.resolve() != path or
            getattr(info, 'st_file_attributes', 0) & 0x400):
        raise BinlogArchiveError('Archive removal directory identity changed')
    return {'device': info.st_dev, 'inode': info.st_ino}


def tree_identity(root):
    """Bind pending deletion to existing entries, including partial cleanup."""
    result, pending = {}, [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                info = entry.stat(follow_symlinks=False)
                if getattr(info, 'st_file_attributes', 0) & 0x400:
                    raise BinlogArchiveError('Archive cleanup cannot traverse a reparse point')
                relative = Path(entry.path).relative_to(root).as_posix()
                value = {'device': info.st_dev, 'inode': info.st_ino}
                if stat.S_ISDIR(info.st_mode):
                    value['kind'] = 'directory'; pending.append(Path(entry.path))
                elif stat.S_ISREG(info.st_mode):
                    value.update(kind='file', size=info.st_size, modified_ns=info.st_mtime_ns, changed_ns=info.st_ctime_ns)
                else:
                    raise BinlogArchiveError('Archive cleanup requires regular files and directories')
                result[relative] = value
    return result


def stopped(jobs, record):
    with jobs._maps_lock:
        worker = jobs.workers.get(record['job_id'])
    if worker and worker[0].is_alive():
        raise BinlogArchiveError('Stop the archive worker before removing files')
    never_dispatched = record['state'] in {'reviewed', 'not_dispatched'} or (
        record['state'] == 'cancelled' and not record.get('started_at') and not record.get('worker_identity'))
    if (record['state'] in ACTIVE or not never_dispatched and
            record.get('native_process_termination_confirmed') is not True):
        raise BinlogArchiveError('Native archive process termination has not been confirmed')


def snapshot(record):
    return digest({key: record.get(key) for key in (
        'job_id', 'created_at', 'state', 'source', 'result',
        'native_process_termination_confirmed', 'artifact_removed',
        'retention_pinned', 'artifact_removal',
    )})


def pin(jobs, job_id, owner, endpoint, pinned):
    if type(pinned) is not bool:
        raise BinlogArchiveError('Select whether this archive is protected from removal')
    with jobs.store(job_id) as store:
        def change(state):
            record = jobs.record(state, job_id, owner, endpoint)
            if record.get('artifact_removed') or record.get('artifact_removal'):
                raise BinlogArchiveError('This archive has already entered removal')
            if record['state'] not in RETAINED or not (record.get('result') or {}).get('artifact'):
                raise BinlogArchiveError('Select a verified archive to protect')
            record.update(retention_pinned=pinned, retention_pin_updated_at=time.time())
        store.change(change)
    return jobs.get(job_id, owner, endpoint)


def _finish_removal(jobs, store, record):
    intent = record['artifact_removal']
    if intent['execution_host'] != socket.gethostname():
        raise BinlogArchiveError('Reconcile archive removal on its recorded application host')
    directory = jobs.directory(record)
    if directory_identity(directory) != intent['parent_identity']:
        raise BinlogArchiveError('Archive job directory changed after removal intent')
    for name, reviewed in intent['directories'].items():
        expected, entries = reviewed['identity'], reviewed['entries']
        original = directory / name
        detached = directory / ('.removing-' + intent['removal_id'] + '-' + name)
        observed, tombstone = directory_identity(original), directory_identity(detached)
        if observed is not None and tombstone is not None:
            raise BinlogArchiveError('Both original and detached archive directories exist; removal refused')
        if observed is not None:
            if observed != expected:
                raise BinlogArchiveError('Archive directory changed after removal intent')
            current = tree_identity(original)
            if any(entries.get(name) != value for name, value in current.items()):
                raise BinlogArchiveError('Archive entries changed after removal intent; unreviewed files are retained')
            durable_replace(original, detached)
            tombstone = directory_identity(detached)
        if tombstone is not None:
            if tombstone != expected:
                raise BinlogArchiveError('Detached archive directory changed after removal intent')
            current = tree_identity(detached)
            if any(entries.get(name) != value for name, value in current.items()):
                raise BinlogArchiveError('Detached archive entries changed after removal intent; unreviewed files are retained')
            # rmtree never traverses a directory link. Recheck the root identity
            # above, including Windows reparse points, before resuming cleanup.
            shutil.rmtree(detached)
        if original.exists() or detached.exists():
            raise BinlogArchiveError('Archive removal absence postcondition failed')
    if os.name != 'nt':
        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    def acknowledge(state):
        current = jobs.record(state, record['job_id'], record['owner'], record['endpoint_id'])
        current.update(artifact_removed=True, artifact_removed_at=time.time())
        current['artifact_removal'].update(state='completed', absence_observed_at=time.time())
    store.change(acknowledge)


def remove(jobs, job_id, owner, endpoint, confirmation, *, expected=None, reconcile=False, retention_id=None):
    if confirmation != job_id:
        raise BinlogArchiveError('Confirm the exact archive job identity before removing its files')
    jobs.scope(owner, endpoint)
    with jobs.store(job_id) as store:
        record = jobs.record(store.read(), job_id, owner, endpoint)
        if record.get('artifact_removed'):
            if expected is not None:
                raise BinlogArchiveError('A reviewed archive has already been removed; prepare a new retention review')
            return jobs.public(record)
        stopped(jobs, record)
        if record.get('retention_pinned'):
            raise BinlogArchiveError('Unprotect this archive in a separate action before removing it')
        intent = record.get('artifact_removal')
        if intent:
            if not reconcile:
                raise BinlogArchiveError('Reconcile the existing removal intent; it will not be replayed')
            if retention_id is not None and intent.get('retention_job_id') != retention_id:
                raise BinlogArchiveError('This removal intent belongs to a different retention review')
        else:
            if reconcile:
                raise BinlogArchiveError('There is no archive removal intent to reconcile')
            if expected is not None:
                if snapshot(record) != expected['snapshot']:
                    raise BinlogArchiveError('A reviewed archive receipt changed; prepare a new retention review')
                artifact = jobs.native_verify(jobs.directory(record) / 'archive', record['source'])
                if digest(artifact) != expected['artifact_digest']:
                    raise BinlogArchiveError('Reviewed archive bytes changed; removal refused')
            directory = jobs.directory(record)
            parent = directory_identity(directory)
            if parent is None:
                raise BinlogArchiveError('Archive job directory is unavailable')
            directories = {name: {'identity': observed, 'entries': tree_identity(directory / name)}
                           for name in DIRECTORIES if (observed := directory_identity(directory / name)) is not None}
            intent = {'removal_id': str(uuid.uuid4()), 'state': 'pending',
                      'retention_job_id': retention_id,
                      'execution_host': socket.gethostname(), 'parent_identity': parent,
                      'directories': directories, 'intent_recorded_at': time.time(),
                      'remote_database_mutation': False, 'receipts_removed': False}
            def prepare(state):
                current = jobs.record(state, job_id, owner, endpoint)
                current['artifact_removal'] = deepcopy(intent)
                if current['state'] == 'reviewed':
                    current['state'] = 'cancelled'
            # Persist and fsync before any directory is renamed or unlinked.
            store.change(prepare)
            record['artifact_removal'] = intent
        _finish_removal(jobs, store, record)
    return jobs.get(job_id, owner, endpoint)


def policy(value):
    if not isinstance(value, dict) or set(value) != {'retention_days', 'keep_latest'}:
        raise BinlogArchiveError('Select an archive age and a minimum retained count per native source')
    days, count = value['retention_days'], value['keep_latest']
    if type(days) is not int or not 0 <= days <= 36500 or type(count) is not int or not 1 <= count <= 2147483647:
        raise BinlogArchiveError('Archive retention age or minimum count is invalid')
    return dict(value)


def candidates(jobs, owner, endpoint, selected):
    """Scan every receipt, retaining bounded candidate and per-source heaps."""
    selected = policy(selected)
    directory = jobs.scope(owner, endpoint) / 'index'
    by_source, oldest = {}, []
    counts = {'pinned': 0, 'unavailable_or_unverified': 0, 'already_removed': 0,
              'minimum_count': 0, 'within_retention_age': 0, 'pending_removal': 0}
    cutoff = time.time() - selected['retention_days'] * 86400
    eligible_count = 0
    if directory.exists():
        directory_identity(directory)
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.name.startswith('.'):
                    continue
                info = entry.stat(follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or info.st_size or getattr(info, 'st_file_attributes', 0) & 0x400:
                    raise BinlogArchiveError('Archive retention index identity changed')
                job_id = identity(entry.name.split('_', 1)[-1])
                record = jobs.load(job_id, owner, endpoint)
                if record.get('artifact_removed'):
                    counts['already_removed'] += 1; continue
                if record.get('artifact_removal'):
                    counts['pending_removal'] += 1; continue
                if record.get('retention_pinned'):
                    counts['pinned'] += 1; continue
                if (record['state'] not in RETAINED or
                        record.get('native_process_termination_confirmed') is not True or
                        not (record.get('result') or {}).get('artifact')):
                    counts['unavailable_or_unverified'] += 1; continue
                artifact = record['result']['artifact']
                compact = {'job_id': job_id, 'created_at': record['created_at'],
                           'source': deepcopy(record['source']), 'snapshot': snapshot(record),
                           'artifact_digest': digest(artifact), 'bytes': str(artifact['total_bytes'])}
                # Keep the newest K per exact source/principal/role. Once a row
                # is displaced it cannot become one of the newest K later.
                group = by_source.setdefault(digest(record['source']), [])
                heapq.heappush(group, (record['created_at'], job_id, compact))
                if len(group) <= selected['keep_latest']:
                    continue
                _created, _job_id, candidate = heapq.heappop(group)
                if candidate['created_at'] >= cutoff:
                    counts['within_retention_age'] += 1; continue
                eligible_count += 1
                heapq.heappush(oldest, (-candidate['created_at'], -uuid.UUID(candidate['job_id']).int, candidate))
                if len(oldest) > 100:
                    heapq.heappop(oldest)
    counts['minimum_count'] = sum(len(group) for group in by_source.values())
    result = sorted((item[2] for item in oldest), key=lambda row: (row['created_at'], row['job_id']))
    return result, counts, cutoff, eligible_count


class RetentionJobs(MySQLBinlogJobs):
    operation = 'mysql_reviewed_archive_retention'
    review_warnings = (
        'Permanently remove only the listed application-host archives. Archive receipts and protected archives remain. Native server logs are unchanged.',
        'Age and minimum-count rules do not establish a recoverable backup/log chain. Protect every archive needed by your base backups and recovery targets before reviewing retention.',
        'This review removes at most 100 archives. New archives are never added to an accepted review. Interrupted removals require explicit reconciliation; they do not restart automatically.',
    )

    def public(self, record):
        result = super().public(record)
        result['native_process_dispatched'] = False
        result.pop('native_process_termination_confirmed', None)
        return result

    def run(self, record, transport, signal):
        cancel = DurableCancellation(self, record, signal)
        try:
            self.update(record, state='active')
            result = transport.execute(record, self.directory(record), cancel,
                                       lambda event: self.update(record, progress=event))
            self.update(record, state='completed', result=result, finished_at=time.time())
        except BaseException as error:
            self.update(record, state='interrupted', error_type=type(error).__name__,
                        error_message=str(error) if isinstance(error, BinlogArchiveError) else None,
                        finished_at=time.time(), automatic_retry=False)
        finally:
            with self._maps_lock:
                known = self.workers.get(record['job_id'])
                if known and known[0] is threading.current_thread():
                    self.workers.pop(record['job_id'], None)


class RetentionTransport:
    def __init__(self, archives):
        self.archives = archives

    def close(self):
        pass

    def execute(self, record, _directory, cancel, progress):
        removed = []
        for selected in record['continuation']['archives']:
            if cancel.is_set():
                raise InterruptedError('Archive retention cancelled')
            progress({'removed_job_ids': list(removed), 'current_job_id': selected['job_id']})
            remove(self.archives, selected['job_id'], record['owner'], record['endpoint_id'],
                   selected['job_id'], expected=selected, retention_id=record['job_id'])
            removed.append(selected['job_id'])
            progress({'removed_job_ids': list(removed), 'current_job_id': None})
        return {'removed_job_ids': removed, 'receipts_removed': False,
                'remote_database_mutation': False, 'database_recovery_verified': False}


def manager(service, archives):
    with service._semantic_lock:
        attribute = 'mysql_archive_retention_' + digest(str(archives.path))[:16]
        jobs = getattr(service, attribute, None)
        if jobs is None:
            jobs = RetentionJobs(str(archives.path) + '.retention', archives.root.parent / (archives.root.name + '-retention'))
            setattr(service, attribute, jobs)
            import atexit
            atexit.register(jobs.close)
        return jobs


def binding(archives):
    return {'configuration': digest({'archive_store': str(archives.path.resolve()), 'root': str(archives.root)}),
            'source': {'archive_kind': archives.operation},
            'program': {'adapter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                        'execution_host': {'kind': 'application-host', 'platform': os.name, 'hostname': socket.gethostname()}}}


def action(service, archives, owner, endpoint, operation, request):
    if operation == 'pin':
        if set(request) != {'job_id', 'pinned'}:
            raise BinlogArchiveError('Select one archive protection action')
        return pin(archives, request['job_id'], owner, endpoint, request['pinned'])
    if operation in {'remove_artifact', 'removal_reconcile'}:
        if set(request) != {'job_id', 'confirmation'}:
            raise BinlogArchiveError('Select and confirm one archive removal')
        return remove(archives, request['job_id'], owner, endpoint, request['confirmation'],
                      reconcile=operation == 'removal_reconcile')
    jobs = manager(service, archives)
    if operation == 'retention_list':
        if set(request) - {'offset', 'limit'}:
            raise BinlogArchiveError('Select one retention receipt page')
        return jobs.list(owner, endpoint, **request)
    if operation in {'retention_status', 'retention_cancel'}:
        if set(request) != {'job_id'}:
            raise BinlogArchiveError('Select one retention receipt')
        return (jobs.get if operation == 'retention_status' else jobs.cancel)(request['job_id'], owner, endpoint)
    current = binding(archives)
    if operation == 'retention_review':
        if set(request) != {'policy'}:
            raise BinlogArchiveError('Review one exact archive retention policy')
        selected = policy(request['policy'])
        eligible, counts, cutoff, total = candidates(archives, owner, endpoint, selected)
        if not eligible:
            raise BinlogArchiveError('No retained archives match this retention policy')
        plan = eligible[:100]
        for item in plan:
            record = archives.load(item['job_id'], owner, endpoint)
            if digest(archives.native_verify(archives.directory(record) / 'archive', record['source'])) != item['artifact_digest']:
                raise BinlogArchiveError('Archive bytes differ from the verification receipt; retention refused')
        return jobs.review(owner, endpoint, selected, {'identity': current['source'], 'state': {}},
                           current['configuration'], current['program'],
                           {'archives': plan, 'eligible_count': total, 'excluded': counts,
                            'cutoff_time': cutoff, 'total_bytes': str(sum(int(item['bytes']) for item in plan))})
    if operation == 'retention_start':
        return jobs.start(request, owner, endpoint, current, RetentionTransport(archives))
    if operation == 'retention_reconcile':
        if set(request) != {'job_id', 'confirmed'} or request['confirmed'] is not True:
            raise BinlogArchiveError('Confirm reconciliation of this retention receipt')
        record = jobs.load(request['job_id'], owner, endpoint)
        if record['state'] == 'reviewed':
            raise BinlogArchiveError('An unstarted retention review has no removal to reconcile')
        with jobs._maps_lock:
            worker = jobs.workers.get(record['job_id'])
        if worker and worker[0].is_alive() or jobs.get(record['job_id'], owner, endpoint)['state'] in ACTIVE:
            raise BinlogArchiveError('Stop the retention worker before reconciliation')
        if record['configuration'] != current['configuration'] or record['program'] != current['program']:
            raise BinlogArchiveError('Reconcile retention with its recorded adapter and application host')
        removed, untouched, other = [], [], []
        for item in record['continuation']['archives']:
            archived = archives.load(item['job_id'], owner, endpoint)
            intent = archived.get('artifact_removal') or {}
            if intent and intent.get('retention_job_id') != record['job_id']:
                other.append(item['job_id'])
                continue
            if archived.get('artifact_removal') and not archived.get('artifact_removed'):
                archived = remove(archives, item['job_id'], owner, endpoint, item['job_id'], reconcile=True,
                                  retention_id=record['job_id'])
            (removed if archived.get('artifact_removed') else untouched).append(item['job_id'])
        jobs.update(record, state='reconciled', result={'removed_job_ids': removed, 'unattempted_job_ids': untouched,
                    'other_removal_job_ids': other,
                    'receipts_removed': False, 'remote_database_mutation': False, 'database_recovery_verified': False},
                    reconciled_at=time.time(), automatic_retry=False)
        return jobs.get(record['job_id'], owner, endpoint)
    raise BinlogArchiveError('Archive retention action is unavailable')
